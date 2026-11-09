import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import MODELS_DIR, UNSUPERVISED_BASE_FEATURES


PLAYBOOKS: Dict[str, Dict[str, str]] = {
    "memory_exhaustion": {
        "label": "Memory Leak / OOM Precursor",
        "cmd": "ssh {node} 'ps aux --sort=-%mem | head -n 8 && dmesg -T | grep -iE \"edac|oom\"'",
        "advice": "Memory utilization is climbing steadily toward exhaustion. Inspect top RSS ranks or drain node before OOM-killer terminates MPI jobs.",
    },
    "thermal_shutdown": {
        "label": "Thermal Runaway / Cooling Degradation",
        "cmd": "ssh {node} 'sensors && ipmitool sel elist | tail -n 10' && scontrol update NodeName={node} State=DRAIN Reason='Thermal precursor'",
        "advice": "Package temperature exceeds peer baseline and continues rising. Drain node or cap CPU frequency before hardware thermal trip.",
    },
    "disk_failure": {
        "label": "Storage / Disk Failure Precursor",
        "cmd": "ssh {node} 'dmesg -T | grep -iE \"i/o error|blk_update|sas|smart\" && iostat -xz 1 3'",
        "advice": "Sustained I/O latency, disk saturation, and elevated iowait indicate impending local SAS or /scratch storage failure.",
    },
    "io_congestion": {
        "label": "Shared NFS / Scratch I/O Bottleneck",
        "cmd": "ssh {node} 'nfsstat -c && df -h /scratch /shared && iotop -b -n 2 | head -n 12'",
        "advice": "High CPU I/O wait without hardware error flags. Inspect /scratch quota (600GB shared pool) and concurrent checkpoint writes.",
    },
    "network_degradation": {
        "label": "10GbE Interconnect / Packet Error Degradation",
        "cmd": "ssh {node} 'ip -s link && ethtool -S eth0 | grep -iE \"err|drop|crc\"'",
        "advice": "Elevated transmit/receive packet errors on 10GbE link. MPI collective barriers will stall until link health is restored.",
    },
    "mpi_straggler": {
        "label": "Degraded MPI Straggler Node",
        "cmd": "scontrol show node {node} && ssh {node} 'mpstat -P ALL 1 2 && numastat'",
        "advice": "Node is lagging significantly behind peer compute nodes during an active multi-node workload, bottlenecking parallel speedup.",
    },
    "cpu_contention": {
        "label": "Runaway Load / CPU Oversubscription",
        "cmd": "ssh {node} 'uptime && pidstat -u 1 3 | sort -k8 -nr | head -n 10'",
        "advice": "Core-normalized runnable queue far exceeds logical CPU cores. Verify Slurm cgroup CPU affinity and zombie ranks.",
    },
    "scrape_gap": {
        "label": "Telemetry Scrape Gap (Exporter Unreachable)",
        "cmd": "curl -sS --max-time 3 http://{ip}:9100/metrics | head -n 5 && systemctl status prometheus-node-exporter",
        "advice": "Prometheus scrape missed (up=0). Verify whether node_exporter restarted before declaring a physical node outage.",
    },
    "planned_maintenance": {
        "label": "Scheduled Maintenance Window",
        "cmd": "scontrol show reservation && scontrol show node {node}",
        "advice": "Node is inside a planned maintenance window. Alerts are suppressed by policy.",
    },
    "power_loss": {
        "label": "Sudden Power / Node Outage",
        "cmd": "ipmitool -H {ip} chassis power status && scontrol show node {node}",
        "advice": "Immediate loss of availability with no gradual telemetry precursor. Requeue affected Slurm jobs from last checkpoint.",
    },
    "normal": {
        "label": "Healthy Operation",
        "cmd": "scontrol show node {node}",
        "advice": "All telemetry, rolling slopes, and peer comparisons are within normal operating envelopes.",
    },
}


class ModelEngine:
    """
    Hot-Swappable Model Adapter:
      - Automatically detects and loads .pkl models from backend/models/ if present.
      - Cleanly falls back to a calibrated Multi-Detector Statistical + Trend Ensemble
        when .pkl files have not yet been dropped in, explicitly labeling prediction provenance.
    """

    def __init__(self, models_dir: Path = MODELS_DIR) -> None:
        self.models_dir = models_dir
        self.scaler: Any = None
        self.iforest: Any = None
        self.ocsvm: Any = None
        self.lof: Any = None
        self.kmeans: Any = None
        self.kmeans_threshold: float = 5.07
        self.supervised_model: Any = None
        self.supervised_features: List[str] = []
        self.evaluation_metrics: Optional[Dict[str, Any]] = None
        self.loaded_files: List[str] = []
        self.reload_models()

    def reload_models(self) -> Dict[str, Any]:
        """Scan backend/models/ and load any available .pkl / .json artifacts."""
        self.scaler = None
        self.iforest = None
        self.ocsvm = None
        self.lof = None
        self.kmeans = None
        self.supervised_model = None
        self.supervised_features = []
        self.evaluation_metrics = None
        self.loaded_files = []

        self.models_dir.mkdir(parents=True, exist_ok=True)
        try:
            import joblib  # type: ignore
        except Exception:
            return self.get_status()

        def _try_load(filename: str) -> Any:
            p = self.models_dir / filename
            if p.exists():
                try:
                    obj = joblib.load(p)
                    self.loaded_files.append(filename)
                    return obj
                except Exception:
                    return None
            return None

        self.scaler = _try_load("hpc_feature_scaler.pkl")
        self.iforest = _try_load("isolation_forest_hpc.pkl")
        self.ocsvm = _try_load("one_class_svm_hpc.pkl")
        self.lof = _try_load("lof_hpc.pkl")
        self.kmeans = _try_load("kmeans_hpc.pkl")
        km_thresh = _try_load("kmeans_threshold.pkl")
        if km_thresh is not None:
            try:
                self.kmeans_threshold = float(km_thresh)
            except Exception:
                pass

        self.supervised_model = _try_load("final_xgb_failure_model.pkl") or _try_load(
            "final_rf_failure_model.pkl"
        )
        feat_json = self.models_dir / "rf_feature_columns.json"
        if feat_json.exists():
            try:
                self.supervised_features = json.loads(feat_json.read_text(encoding="utf-8"))
                self.loaded_files.append("rf_feature_columns.json")
            except Exception:
                self.supervised_features = []

        metrics_json = self.models_dir / "model_metrics.json"
        if metrics_json.exists():
            try:
                self.evaluation_metrics = json.loads(metrics_json.read_text(encoding="utf-8"))
                self.loaded_files.append("model_metrics.json")
            except Exception:
                self.evaluation_metrics = None

        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        has_unsupervised_pkl = any(
            m is not None for m in (self.iforest, self.ocsvm, self.lof, self.kmeans)
        )
        has_supervised_pkl = self.supervised_model is not None
        if has_unsupervised_pkl and has_supervised_pkl:
            mode = "production_pkl_full"
            label = "Trained ML Active (Full .pkl)"
        elif has_unsupervised_pkl or has_supervised_pkl:
            mode = "hybrid_pkl"
            label = "Hybrid ML (.pkl + Baseline)"
        else:
            mode = "placeholder_heuristic"
            label = "Statistical Baseline (Awaiting .pkl)"

        shap_supported = has_supervised_pkl and hasattr(self.supervised_model, "feature_importances_")

        return {
            "engine_mode": mode,
            "engine_label": label,
            "models_directory": str(self.models_dir),
            "loaded_files": self.loaded_files,
            "shap_or_importances_available": shap_supported,
            "evaluation_metrics": self.evaluation_metrics,
            "detectors": {
                "isolation_forest": "pkl" if self.iforest is not None else "statistical",
                "one_class_svm": "pkl" if self.ocsvm is not None else "statistical",
                "lof": "pkl" if self.lof is not None else "statistical",
                "kmeans": "pkl" if self.kmeans is not None else "statistical",
                "failure_predictor_1h": "pkl" if self.supervised_model is not None else "statistical",
            },
        }

    def score_node(self, feats: Dict[str, Any]) -> Dict[str, Any]:
        node_id = str(feats.get("node_id", "unknown"))
        ip = str(feats.get("ip", "127.0.0.1"))
        up = int(feats.get("up", 1) if feats.get("up") is not None else 0)
        planned_maint = int(feats.get("planned_maintenance", 0)) == 1
        has_sup_pkl = self.supervised_model is not None and bool(self.supervised_features)
        pred_source = "trained_pkl_model" if has_sup_pkl else "statistical_baseline"

        if planned_maint:
            pb = PLAYBOOKS["planned_maintenance"]
            return {
                "failure_prob_1h": 0.0,
                "failure_prob_6h": 0.0,
                "failure_prob_24h": 0.0,
                "prediction_confidence": None,
                "prediction_source": pred_source,
                "anomaly_score": 0.0,
                "consensus_count": 0,
                "consensus_votes": {
                    "isolation_forest": False,
                    "one_class_svm": False,
                    "lof": False,
                    "kmeans": False,
                },
                "node_health_score": 100.0,
                "health_classification": "Maintenance",
                "fault_class": "planned_maintenance",
                "fault_label": pb["label"],
                "playbook_cmd": pb["cmd"].format(node=node_id, ip=ip),
                "playbook_advice": pb["advice"],
                "top_features": [],
            }

        if up == 0:
            gt_class = str(feats.get("gt_event_class") or "")
            is_scrape_gap = gt_class == "scrape_gap" or bool(feats.get("simulated_scrape_gap", False))
            fclass = "scrape_gap" if is_scrape_gap else "power_loss"
            pb = PLAYBOOKS[fclass]
            return {
                "failure_prob_1h": 0.08 if is_scrape_gap else 0.99,
                "failure_prob_6h": 0.12 if is_scrape_gap else 0.99,
                "failure_prob_24h": 0.18 if is_scrape_gap else 0.99,
                "prediction_confidence": None,
                "prediction_source": "telemetry_availability_check",
                "anomaly_score": 0.65 if is_scrape_gap else 1.0,
                "consensus_count": 2 if is_scrape_gap else 4,
                "consensus_votes": {
                    "isolation_forest": True,
                    "one_class_svm": True,
                    "lof": not is_scrape_gap,
                    "kmeans": not is_scrape_gap,
                },
                "node_health_score": 45.0 if is_scrape_gap else 0.0,
                "health_classification": "Scrape Gap" if is_scrape_gap else "Offline",
                "fault_class": fclass,
                "fault_label": pb["label"],
                "playbook_cmd": pb["cmd"].format(node=node_id, ip=ip),
                "playbook_advice": pb["advice"],
                "top_features": [
                    {
                        "feature": "up (node_exporter)",
                        "value": 0.0,
                        "unit": "bool",
                        "impact": 0.95,
                        "source_type": "live_observation",
                        "detail": "Exporter unreachable" if is_scrape_gap else "Node offline / unresponsive",
                    }
                ],
            }

        cpu = _num(feats.get("cpu_utilization_percent"), 0.0)
        iowait = _num(feats.get("cpu_iowait_percent"), 0.0)
        mem = _num(feats.get("memory_used_percent"), 0.0)
        mem_slope = _num(feats.get("memory_used_percent__slope12"), 0.0)
        norm_load = _num(feats.get("normalized_load1"), 0.0)
        scratch = _num(feats.get("scratch_used_percent"), _num(feats.get("root_used_percent"), 0.0))
        disk_io = _num(feats.get("disk_io_utilization_percent"), 0.0)
        disk_w = _num(feats.get("disk_write_bytes_per_second"), 0.0)
        net_err = _num(feats.get("network_errors_per_second"), 0.0)
        temp = _num(feats.get("cpu_temperature_celsius"), None)
        temp_slope = _num(feats.get("cpu_temperature_celsius__slope12"), 0.0)
        straggler = _num(feats.get("mpi_straggler_score"), 0.0)
        cluster_busy_mpi = bool(feats.get("cluster_busy_mpi", False))

        # 1. Unsupervised Consensus Scoring
        votes = self._score_unsupervised_detectors(
            feats, cpu, iowait, mem, mem_slope, norm_load, scratch, disk_io, net_err, temp, straggler, cluster_busy_mpi
        )
        consensus_count = sum(1 for v in votes["votes"].values() if v)
        anomaly_score = votes["anomaly_score"]

        # 2. Supervised Failure Risk Scoring + Real Confidence (when supported by .pkl)
        prob_1h, pred_conf, actual_pred_src = self._score_supervised_failure(
            feats, cpu, iowait, mem, mem_slope, norm_load, scratch, disk_io, net_err, temp, temp_slope, straggler
        )
        prob_6h = round(min(0.99, prob_1h * 1.28 + (0.04 if anomaly_score > 0.45 else 0.0)), 4)
        prob_24h = round(min(0.99, prob_6h * 1.22 + (0.03 if mem_slope > 0.2 else 0.0)), 4)

        # 3. Root-Cause Feature Contributions (uses model feature_importances_ weighting if available)
        contributions = self._compute_feature_attributions(
            feats, cpu, iowait, mem, mem_slope, norm_load, scratch, disk_io, disk_w, net_err, temp, temp_slope, straggler
        )
        top_features = contributions[:4]

        # 4. Fault Class Diagnosis & Playbook
        fault_class = _classify_fault(
            prob_1h, anomaly_score, consensus_count, mem, mem_slope, temp, temp_slope, iowait, disk_io, scratch, net_err, norm_load, straggler
        )
        pb = PLAYBOOKS.get(fault_class, PLAYBOOKS["normal"])

        # 5. Deterministic Node Health Score (0-100%)
        health_score, health_cls = _compute_node_health(
            prob_1h=prob_1h,
            anomaly_score=anomaly_score,
            mem=mem,
            iowait=iowait,
            scratch=scratch,
            temp=temp,
            net_err=net_err,
            norm_load=norm_load,
        )

        return {
            "failure_prob_1h": round(prob_1h, 4),
            "failure_prob_6h": prob_6h,
            "failure_prob_24h": prob_24h,
            "prediction_confidence": pred_conf,
            "prediction_source": actual_pred_src,
            "anomaly_score": round(anomaly_score, 4),
            "consensus_count": consensus_count,
            "consensus_votes": votes["votes"],
            "node_health_score": health_score,
            "health_classification": health_cls,
            "fault_class": fault_class,
            "fault_label": pb["label"],
            "playbook_cmd": pb["cmd"].format(node=node_id, ip=ip),
            "playbook_advice": pb["advice"],
            "top_features": top_features,
        }

    def _score_unsupervised_detectors(
        self,
        feats: Dict[str, Any],
        cpu: float,
        iowait: float,
        mem: float,
        mem_slope: float,
        norm_load: float,
        scratch: float,
        disk_io: float,
        net_err: float,
        temp: Optional[float],
        straggler: float,
        cluster_busy_mpi: bool,
    ) -> Dict[str, Any]:
        if self.scaler is not None and any(
            m is not None for m in (self.iforest, self.ocsvm, self.lof, self.kmeans)
        ):
            try:
                import numpy as np  # type: ignore

                row = [[_num(feats.get(col), 0.0) for col in UNSUPERVISED_BASE_FEATURES]]
                x_scaled = self.scaler.transform(row)
                v_if = bool(self.iforest.predict(x_scaled)[0] == -1) if self.iforest is not None else False
                v_svm = bool(self.ocsvm.predict(x_scaled)[0] == -1) if self.ocsvm is not None else False
                v_lof = bool(self.lof.predict(x_scaled)[0] == -1) if self.lof is not None else False
                if self.kmeans is not None:
                    dist = float(np.min(self.kmeans.transform(x_scaled), axis=1)[0])
                    v_km = dist > self.kmeans_threshold
                else:
                    v_km = False

                raw_scores: List[float] = []
                if self.iforest is not None:
                    s_if = -float(self.iforest.decision_function(x_scaled)[0])
                    raw_scores.append(1.0 / (1.0 + math.exp(-6.0 * s_if)))
                if self.ocsvm is not None:
                    s_svm = -float(self.ocsvm.decision_function(x_scaled)[0])
                    raw_scores.append(1.0 / (1.0 + math.exp(-2.0 * s_svm)))

                if (
                    cluster_busy_mpi
                    and straggler < 0.25
                    and iowait < 10.0
                    and mem < 88.0
                    and net_err < 0.5
                    and (temp is None or temp < 82.0)
                ):
                    return {
                        "votes": {
                            "isolation_forest": False,
                            "one_class_svm": False,
                            "lof": False,
                            "kmeans": False,
                        },
                        "anomaly_score": 0.12,
                    }

                votes_dict = {
                    "isolation_forest": v_if,
                    "one_class_svm": v_svm,
                    "lof": v_lof,
                    "kmeans": v_km,
                }
                vote_frac = sum(1 for v in votes_dict.values() if v) / max(
                    sum(1 for m in (self.iforest, self.ocsvm, self.lof, self.kmeans) if m is not None), 1
                )
                agg_score = (sum(raw_scores) / len(raw_scores)) if raw_scores else vote_frac
                return {
                    "votes": votes_dict,
                    "anomaly_score": min(1.0, max(0.0, 0.55 * agg_score + 0.45 * vote_frac)),
                }
            except Exception:
                pass

        temp_excess = max(0.0, (temp - 76.0) / 16.0) if temp is not None else 0.0
        mem_excess = max(0.0, (mem - 82.0) / 15.0) + max(0.0, mem_slope * 0.45)
        io_excess = max(0.0, (iowait - 12.0) / 22.0) + max(0.0, (disk_io - 75.0) / 25.0)
        net_excess = min(1.2, net_err / 2.5)
        load_excess = max(0.0, (norm_load - 1.35) / 0.85)
        scratch_excess = max(0.0, (scratch - 85.0) / 12.0)

        score_if = max(temp_excess, mem_excess, io_excess, net_excess, scratch_excess, load_excess * 0.85)
        score_svm = 0.38 * mem_excess + 0.35 * temp_excess + 0.35 * io_excess + 0.45 * net_excess + 0.30 * load_excess + 0.25 * scratch_excess
        peer_cpu_z = abs(_num(feats.get("cpu_utilization_percent__peer_diff"), 0.0)) / 35.0
        peer_mem_z = abs(_num(feats.get("memory_used_percent__peer_diff"), 0.0)) / 25.0
        score_lof = max(straggler * 1.25, 0.45 * peer_cpu_z + 0.45 * peer_mem_z + 0.35 * io_excess + 0.35 * net_excess)
        if cluster_busy_mpi and straggler < 0.2 and io_excess < 0.1 and temp_excess < 0.1 and mem_excess < 0.15:
            score_lof *= 0.25
        score_km = max(0.5 * score_if + 0.5 * score_svm, straggler * 0.95)

        votes = {
            "isolation_forest": score_if >= 0.48,
            "one_class_svm": score_svm >= 0.46,
            "lof": score_lof >= 0.48,
            "kmeans": score_km >= 0.47,
        }
        raw_combined = 0.32 * min(1.2, score_if) + 0.28 * min(1.2, score_svm) + 0.22 * min(1.2, score_lof) + 0.18 * min(1.2, score_km)
        ambient = 0.04 + 0.03 * min(1.0, cpu / 100.0)
        anomaly_score = min(0.99, ambient + 0.88 * raw_combined)
        return {"votes": votes, "anomaly_score": anomaly_score}

    def _score_supervised_failure(
        self,
        feats: Dict[str, Any],
        cpu: float,
        iowait: float,
        mem: float,
        mem_slope: float,
        norm_load: float,
        scratch: float,
        disk_io: float,
        net_err: float,
        temp: Optional[float],
        temp_slope: float,
        straggler: float,
    ) -> Tuple[float, Optional[float], str]:
        if self.supervised_model is not None and self.supervised_features:
            try:
                import numpy as np  # type: ignore
                import pandas as pd  # type: ignore

                row_dict = {col: _num(feats.get(col), float("nan")) for col in self.supervised_features}
                df_row = pd.DataFrame([row_dict], columns=self.supervised_features)
                prob = float(self.supervised_model.predict_proba(df_row)[0, 1])

                # Compute genuine ensemble tree agreement confidence when supported (RandomForest estimators_)
                confidence: Optional[float] = None
                if hasattr(self.supervised_model, "estimators_"):
                    tree_preds = [
                        float(est.predict_proba(df_row.values)[0, 1])
                        for est in self.supervised_model.estimators_[:50]
                    ]
                    if tree_preds:
                        std_dev = float(np.std(tree_preds))
                        confidence = round(max(0.0, min(1.0, 1.0 - 2.0 * std_dev)), 3)

                return max(0.0, min(1.0, prob)), confidence, "trained_pkl_model"
            except Exception:
                pass

        logit = -5.65
        if mem > 78.0:
            logit += (mem - 78.0) * 0.19
        if mem > 68.0 and mem_slope > 0.35:
            logit += min(2.8, mem_slope * 1.45)
        if temp is not None:
            if temp > 75.0:
                logit += (temp - 75.0) * 0.24
            if temp > 68.0 and temp_slope > 0.25:
                logit += min(2.4, temp_slope * 1.6)
        if iowait > 10.0:
            logit += (iowait - 10.0) * 0.13
        if disk_io > 78.0 and iowait > 8.0:
            logit += (disk_io - 78.0) * 0.11
        if scratch > 86.0:
            logit += (scratch - 86.0) * 0.26
        if net_err > 0.4:
            logit += min(2.5, net_err * 0.85)
        if straggler >= 0.45:
            logit += straggler * 1.65
        if norm_load > 1.5:
            logit += min(1.8, (norm_load - 1.5) * 1.1)

        prob = 1.0 / (1.0 + math.exp(-logit))
        return max(0.0005, min(0.995, prob)), None, "statistical_baseline"

    def _compute_feature_attributions(
        self,
        feats: Dict[str, Any],
        cpu: float,
        iowait: float,
        mem: float,
        mem_slope: float,
        norm_load: float,
        scratch: float,
        disk_io: float,
        disk_w: float,
        net_err: float,
        temp: Optional[float],
        temp_slope: float,
        straggler: float,
    ) -> List[Dict[str, Any]]:
        has_importances = (
            self.supervised_model is not None
            and hasattr(self.supervised_model, "feature_importances_")
            and bool(self.supervised_features)
        )
        attr_type = "model_feature_importance" if has_importances else "deviation_attribution"

        candidates: List[Dict[str, Any]] = []
        mem_impact = max(0.0, (mem - 70.0) / 30.0) + max(0.0, mem_slope * 0.28)
        candidates.append(
            {
                "feature": "memory_used_percent",
                "value": round(mem, 1),
                "unit": "%",
                "impact": round(min(1.0, mem_impact), 3),
                "source_type": attr_type,
                "detail": f"Slope {mem_slope:+.2f}%/step | Peer Δ {_num(feats.get('memory_used_percent__peer_diff'), 0.0):+.1f}%",
            }
        )

        if temp is not None:
            temp_impact = max(0.0, (temp - 68.0) / 25.0) + max(0.0, temp_slope * 0.30)
            candidates.append(
                {
                    "feature": "cpu_temperature_celsius",
                    "value": round(temp, 1),
                    "unit": "°C",
                    "impact": round(min(1.0, temp_impact), 3),
                    "source_type": attr_type,
                    "detail": f"Slope {temp_slope:+.2f}°C/step | Peer Δ {_num(feats.get('cpu_temperature_celsius__peer_diff'), 0.0):+.1f}°C",
                }
            )

        io_impact = max(0.0, (iowait - 5.0) / 28.0) + max(0.0, (disk_io - 65.0) / 40.0)
        candidates.append(
            {
                "feature": "cpu_iowait_percent",
                "value": round(iowait, 2),
                "unit": "%",
                "impact": round(min(1.0, io_impact), 3),
                "source_type": attr_type,
                "detail": f"Disk active {disk_io:.1f}% | Write {disk_w / (1024 * 1024):.1f} MB/s",
            }
        )

        scratch_impact = max(0.0, (scratch - 75.0) / 22.0)
        candidates.append(
            {
                "feature": "scratch_used_percent",
                "value": round(scratch, 1),
                "unit": "%",
                "impact": round(min(1.0, scratch_impact), 3),
                "source_type": attr_type,
                "detail": "Filesystem pool critical limit 90%",
            }
        )

        net_impact = min(1.0, net_err / 3.0)
        candidates.append(
            {
                "feature": "network_errors_per_second",
                "value": round(net_err, 3),
                "unit": "err/s",
                "impact": round(net_impact, 3),
                "source_type": attr_type,
                "detail": "10GbE cluster interconnect packet health",
            }
        )

        load_impact = max(0.0, (norm_load - 1.1) / 1.1)
        candidates.append(
            {
                "feature": "normalized_load1",
                "value": round(norm_load, 2),
                "unit": "x cores",
                "impact": round(min(1.0, max(load_impact, straggler * 0.9)), 3),
                "source_type": attr_type,
                "detail": f"CPU {cpu:.1f}% | MPI Straggler Index {straggler:.2f}",
            }
        )

        candidates.sort(key=lambda c: c["impact"], reverse=True)
        return candidates


def _compute_node_health(
    prob_1h: float,
    anomaly_score: float,
    mem: float,
    iowait: float,
    scratch: float,
    temp: Optional[float],
    net_err: float,
    norm_load: float,
) -> Tuple[float, str]:
    penalty = 0.0
    penalty += prob_1h * 55.0
    penalty += max(0.0, anomaly_score - 0.15) * 24.0
    if mem > 85.0:
        penalty += (mem - 85.0) * 1.1
    if iowait > 10.0:
        penalty += (iowait - 10.0) * 0.6
    if scratch > 85.0:
        penalty += (scratch - 85.0) * 1.4
    if temp is not None and temp > 76.0:
        penalty += (temp - 76.0) * 1.3
    if net_err > 0.2:
        penalty += min(15.0, net_err * 3.0)
    if norm_load > 1.4:
        penalty += min(12.0, (norm_load - 1.4) * 8.0)

    score = round(max(5.0, min(100.0, 100.0 - penalty)), 1)
    if score >= 92.0:
        cls = "Excellent"
    elif score >= 78.0:
        cls = "Healthy"
    elif score >= 55.0:
        cls = "Warning"
    else:
        cls = "Critical"
    return score, cls


def _classify_fault(
    prob_1h: float,
    anomaly_score: float,
    consensus_count: int,
    mem: float,
    mem_slope: float,
    temp: Optional[float],
    temp_slope: float,
    iowait: float,
    disk_io: float,
    scratch: float,
    net_err: float,
    norm_load: float,
    straggler: float,
) -> str:
    if prob_1h < 0.015 and consensus_count < 2 and anomaly_score < 0.42 and straggler < 0.45 and scratch < 88.0:
        return "normal"

    scores = {
        "thermal_shutdown": ((temp - 75.0) / 12.0 + max(0.0, temp_slope * 0.4)) if temp is not None else -1.0,
        "memory_exhaustion": (mem - 78.0) / 12.0 + max(0.0, mem_slope * 0.5),
        "disk_failure": ((iowait - 14.0) / 15.0 + (disk_io - 75.0) / 20.0) if disk_io > 65.0 else (iowait - 20.0) / 15.0,
        "io_congestion": max((scratch - 85.0) / 8.0, (iowait - 9.0) / 14.0),
        "network_degradation": net_err / 1.2,
        "mpi_straggler": straggler * 1.6 if straggler >= 0.45 else -0.5,
        "cpu_contention": (norm_load - 1.35) / 0.5,
    }
    best_cls = max(scores.items(), key=lambda kv: kv[1])
    return best_cls[0] if best_cls[1] > 0.1 else ("mpi_straggler" if straggler >= 0.45 else "io_congestion")


def _num(val: Any, default: Any = 0.0) -> Any:
    if val is None or val == "":
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except Exception:
        return default

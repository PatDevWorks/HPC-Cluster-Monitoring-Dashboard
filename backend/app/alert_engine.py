from datetime import datetime, timedelta, timezone
import threading
from typing import Any, Dict, List, Optional

import requests

from .config import ALERT_POLICY, ALERT_WEBHOOK_URL
from .database import (
    add_system_log,
    auto_resolve_node_episodes,
    get_app_settings,
    upsert_alert_episode,
)


RECOMMENDED_CHECKS_BY_EVENT: Dict[str, str] = {
    "node_offline": "ping -c 2 {ip} && curl -sf -o /dev/null -w 'HTTP %{{http_code}}\n' http://{ip}:9100/metrics; ssh {node} 'pgrep -af node_exporter || ss -tlnp | grep 9100 || systemctl status node_exporter prometheus-node-exporter --no-pager'",
    "scrape_gap": "curl -sf -o /dev/null -w 'HTTP %{{http_code}}\n' http://{ip}:9100/metrics && ssh {node} 'pgrep -af node_exporter || ss -tlnp | grep 9100'",
    "slurm_node_down": "scontrol show node {node} && ssh {node} 'systemctl status slurmd && dmesg -T | tail -n 20'",
    "stale_telemetry": "curl -sf http://localhost:9090/api/v1/targets | grep -A 5 '{ip}:9100' && curl -sf -o /dev/null -w 'HTTP %{{http_code}}\n' http://{ip}:9100/metrics",
    "memory_pressure_critical": "ssh {node} 'free -h && ps aux --sort=-%mem | head -n 15 && dmesg -T | grep -i oom'",
    "memory_pressure_warning": "ssh {node} 'free -h && ps aux --sort=-%mem | head -n 10'",
    "scratch_pool_critical": "ssh {node} 'df -h /scratch && du -sh /scratch/* 2>/dev/null | sort -hr | head -n 10'",
    "root_fs_high": "ssh {node} 'df -h / && journalctl --disk-usage'",
    "high_iowait": "ssh {node} 'iostat -xz 1 3 && lsblk && dmesg -T | tail -n 20'",
    "cpu_saturation": "ssh {node} 'top -b -n 1 | head -n 20 && squeue -w {node}'",
    "high_load_average": "ssh {node} 'uptime && ps -eo pid,stat,pcpu,pmem,comm --sort=-pcpu | head -n 15'",
    "network_packet_errors": "ssh {node} 'ip -s link && netstat -s | grep -i retrans'",
    "mpi_straggler_detected": "Compare job CPU/network progress across sibling nodes via Slurm squeue -w {node}",
    "v7_anomaly_detected": "Inspect telemetry deltas around timestamp in AI Model Centre (V7 Isolation Forest anomaly score)",
    "lstm_v8_warning": "Inspect LSTM V8 residual_z / drift_z / forecast divergence components in AI Model Centre",
}


def _num(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


class SmartAlertEngine:
    """
    Evidence-based operational alerting and state engine.

    Separates distinct monitoring sources instead of collapsing them into a fabricated consensus:
      - availability: exporter reachability (up == 0), stale telemetry, Slurm DOWN state
      - telemetry: deterministic Prometheus threshold checks (CPU, IOWait, RAM, FS, load, net errors, MPI straggler)
      - v7: V7 Isolation Forest anomaly flag (warning signal; requires telemetry/log verification)
      - lstm_v8: LSTM V8 temporal warning score flag (early warning; requires verification)
    """

    def __init__(self) -> None:
        self.streaks: Dict[str, Dict[str, int]] = {}
        self.healthy_streaks: Dict[str, int] = {}
        self.last_webhook_sent: Dict[str, datetime] = {}
        self.last_resolved_cooldown: Dict[str, datetime] = {}

    def reset(self) -> None:
        self.streaks.clear()
        self.healthy_streaks.clear()
        self.last_webhook_sent.clear()
        self.last_resolved_cooldown.clear()

    def evaluate(
        self,
        node_sample: Dict[str, Any],
        timestamp_utc: str,
        data_mode: str,
        v7_result: Optional[Dict[str, Any]] = None,
        lstm_result: Optional[Dict[str, Any]] = None,
        telemetry_age_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        policy = dict(ALERT_POLICY)
        try:
            saved_policy = get_app_settings().get("alert_policy")
            if isinstance(saved_policy, dict):
                policy.update(saved_policy)
        except Exception:
            pass

        nid = str(node_sample["node_id"])
        ip = str(node_sample.get("ip", nid))
        up = int(node_sample.get("up", 1) if node_sample.get("up") is not None else 0)
        planned_maint = int(node_sample.get("planned_maintenance", 0)) == 1
        slurm_state = str(node_sample.get("slurm_state", "ONLINE") or "ONLINE").upper()
        fault_injected = str(node_sample.get("fault_injected") or "")
        prometheus_offline = bool(node_sample.get("prometheus_offline", False)) or (
            "PROMETHEUS OFFLINE" in slurm_state
        )

        if nid not in self.streaks:
            self.streaks[nid] = {"p1": 0, "p2": 0, "p3": 0}

        if prometheus_offline:
            self.streaks[nid] = {"p1": 0, "p2": 0, "p3": 0}
            return {
                "health_status": "offline",
                "health_classification": "Prometheus Offline",
                "status_reason": "Prometheus server unreachable (:9090); per-node exporter telemetry unavailable.",
                "alert_priority": "OK",
                "severity": "none",
                "alert_source": "availability",
                "event_type": "prometheus_offline",
                "persistence_progress": "0/0",
                "alert_active": False,
                "episode_id": None,
                "evidence": [],
                "recommended_checks": "",
            }

        if planned_maint or slurm_state in {"DRAIN", "DRAINING", "DRAINED", "MAINT"}:
            self.streaks[nid] = {"p1": 0, "p2": 0, "p3": 0}
            auto_resolve_node_episodes(nid, timestamp_utc)
            return {
                "health_status": "maintenance",
                "health_classification": "Maintenance / Drained",
                "status_reason": f"Node is in Slurm {slurm_state} / planned maintenance state.",
                "alert_priority": "OK",
                "severity": "none",
                "alert_source": "slurm",
                "event_type": "planned_maintenance",
                "persistence_progress": "0/0",
                "alert_active": False,
                "episode_id": None,
                "evidence": [],
                "recommended_checks": "",
            }

        evidence: List[Dict[str, Any]] = []

        # 1. Availability, Slurm & Freshness checks
        stale_limit = float(policy.get("stale_telemetry_seconds", 120))
        if up == 0:
            if fault_injected == "scrape_gap":
                evidence.append(
                    {
                        "source": "availability",
                        "event_type": "scrape_gap",
                        "priority": "P2",
                        "metric": "up",
                        "value": 0,
                        "threshold": 1,
                        "summary": f"Prometheus scrape gap detected (up=0) on {nid}",
                    }
                )
            else:
                evidence.append(
                    {
                        "source": "availability",
                        "event_type": "node_offline",
                        "priority": "P1",
                        "metric": "up",
                        "value": 0,
                        "threshold": 1,
                        "summary": f"Node exporter unreachable (up=0) on {nid}",
                    }
                )
        elif slurm_state in {"DOWN", "FAIL", "FAILING", "NOT_RESPONDING"}:
            evidence.append(
                {
                    "source": "slurm",
                    "event_type": "slurm_node_down",
                    "priority": "P1",
                    "metric": "slurm_state",
                    "value": slurm_state,
                    "threshold": "IDLE/ALLOC",
                    "summary": f"Slurm reports node state {slurm_state}",
                }
            )
        elif telemetry_age_seconds is not None and telemetry_age_seconds > stale_limit:
            evidence.append(
                {
                    "source": "availability",
                    "event_type": "stale_telemetry",
                    "priority": "P2",
                    "metric": "telemetry_age_seconds",
                    "value": round(telemetry_age_seconds, 1),
                    "threshold": stale_limit,
                    "summary": f"Telemetry age {telemetry_age_seconds:.0f}s exceeds freshness threshold ({stale_limit:.0f}s)",
                }
            )

        # 2. Telemetry threshold checks (only when exporter up == 1 and value present)
        if up == 1:
            mem = _num(node_sample.get("memory_used_percent"))
            scratch = _num(node_sample.get("scratch_used_percent"))
            root_fs = _num(node_sample.get("root_used_percent"))
            iowait = _num(node_sample.get("cpu_iowait_percent"))
            cpu = _num(node_sample.get("cpu_utilization_percent"))
            norm_load = _num(node_sample.get("normalized_load1"))
            net_err = _num(node_sample.get("network_errors_per_second"))
            straggler = _num(node_sample.get("mpi_straggler_score"))

            mem_crit = float(policy.get("memory_critical_percent", 95.0))
            mem_warn = float(policy.get("memory_warning_percent", 88.0))
            scratch_crit = float(policy.get("scratch_critical_percent", 90.0))
            root_crit = float(policy.get("root_critical_percent", 90.0))
            iowait_warn = float(policy.get("iowait_warning_percent", 35.0))
            cpu_warn = float(policy.get("cpu_warning_percent", 95.0))
            load_warn = float(policy.get("normalized_load_warning", 1.25))
            net_warn = float(policy.get("net_error_warning_per_sec", 1.0))
            strag_warn = float(policy.get("mpi_straggler_warning", 0.45))

            if mem is not None and mem >= mem_crit:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "memory_pressure_critical",
                        "priority": "P1",
                        "metric": "memory_used_percent",
                        "value": round(mem, 1),
                        "threshold": mem_crit,
                        "summary": f"Memory usage at {mem:.1f}% (>= {mem_crit:.0f}% critical)",
                    }
                )
            elif mem is not None and mem >= mem_warn:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "memory_pressure_warning",
                        "priority": "P2",
                        "metric": "memory_used_percent",
                        "value": round(mem, 1),
                        "threshold": mem_warn,
                        "summary": f"Memory usage at {mem:.1f}% (>= {mem_warn:.0f}% warning)",
                    }
                )

            if scratch is not None and scratch >= scratch_crit:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "scratch_pool_critical",
                        "priority": "P1",
                        "metric": "scratch_used_percent",
                        "value": round(scratch, 1),
                        "threshold": scratch_crit,
                        "summary": f"/scratch usage at {scratch:.1f}% (>= {scratch_crit:.0f}%)",
                    }
                )

            if root_fs is not None and root_fs >= root_crit:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "root_fs_high",
                        "priority": "P2",
                        "metric": "root_used_percent",
                        "value": round(root_fs, 1),
                        "threshold": root_crit,
                        "summary": f"Root filesystem at {root_fs:.1f}% (>= {root_crit:.0f}%)",
                    }
                )

            if iowait is not None and iowait >= iowait_warn:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "high_iowait",
                        "priority": "P2",
                        "metric": "cpu_iowait_percent",
                        "value": round(iowait, 1),
                        "threshold": iowait_warn,
                        "summary": f"CPU I/O wait at {iowait:.1f}% (>= {iowait_warn:.0f}%)",
                    }
                )

            if cpu is not None and cpu >= cpu_warn:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "cpu_saturation",
                        "priority": "P2",
                        "metric": "cpu_utilization_percent",
                        "value": round(cpu, 1),
                        "threshold": cpu_warn,
                        "summary": f"CPU utilization at {cpu:.1f}% (>= {cpu_warn:.0f}%)",
                    }
                )

            if norm_load is not None and norm_load >= load_warn:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "high_load_average",
                        "priority": "P2",
                        "metric": "normalized_load1",
                        "value": round(norm_load, 2),
                        "threshold": load_warn,
                        "summary": f"Normalized 1m load {norm_load:.2f}x cores (>= {load_warn:.2f}x)",
                    }
                )

            if net_err is not None and net_err >= net_warn:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "network_packet_errors",
                        "priority": "P2",
                        "metric": "network_errors_per_second",
                        "value": round(net_err, 2),
                        "threshold": net_warn,
                        "summary": f"Network errors at {net_err:.2f}/s (>= {net_warn:.1f}/s)",
                    }
                )

            if straggler is not None and straggler >= strag_warn:
                evidence.append(
                    {
                        "source": "telemetry",
                        "event_type": "mpi_straggler_detected",
                        "priority": "P2",
                        "metric": "mpi_straggler_score",
                        "value": round(straggler, 2),
                        "threshold": strag_warn,
                        "summary": f"Peer workload asymmetry index {straggler:.2f} (>= {strag_warn:.2f})",
                    }
                )

        # 3. Separate V7 Isolation Forest anomaly signal (never collapsed into consensus)
        if (
            policy.get("enable_v7_alerts", True)
            and isinstance(v7_result, dict)
            and v7_result.get("is_anomaly")
        ):
            score = _num(v7_result.get("anomaly_score"))
            thresh = _num(v7_result.get("threshold"))
            evidence.append(
                {
                    "source": "v7",
                    "event_type": "v7_anomaly_detected",
                    "priority": "P2",
                    "metric": "v7_anomaly_score",
                    "value": round(score, 4) if score is not None else None,
                    "threshold": round(thresh, 4) if thresh is not None else None,
                    "summary": (
                        f"V7 Isolation Forest anomaly score {score:.4f} >= node threshold {thresh:.4f}"
                        if score is not None and thresh is not None
                        else "V7 Isolation Forest flagged statistical anomaly relative to learned baseline"
                    ),
                }
            )

        # 4. Separate LSTM V8 temporal warning signal
        if (
            policy.get("enable_lstm_alerts", True)
            and isinstance(lstm_result, dict)
            and lstm_result.get("is_warning")
        ):
            w_score = _num(lstm_result.get("warning_score"))
            w_thresh = _num(lstm_result.get("warning_threshold"))
            evidence.append(
                {
                    "source": "lstm_v8",
                    "event_type": "lstm_v8_warning",
                    "priority": "P2",
                    "metric": "lstm_warning_score",
                    "value": round(w_score, 4) if w_score is not None else None,
                    "threshold": round(w_thresh, 4) if w_thresh is not None else None,
                    "summary": (
                        f"LSTM V8 warning score {w_score:.4f} >= threshold {w_thresh:.4f}"
                        if w_score is not None and w_thresh is not None
                        else "LSTM V8 temporal model raised an early-warning signal"
                    ),
                }
            )

        # Evaluate persistence and select primary condition
        has_p1 = any(item["priority"] == "P1" for item in evidence)
        has_p2 = any(item["priority"] == "P2" for item in evidence)

        req_ticks = max(1, int(policy.get("persistence_ticks", 2)))
        self.streaks[nid]["p1"] = (self.streaks[nid]["p1"] + 1) if has_p1 else 0
        self.streaks[nid]["p2"] = (self.streaks[nid]["p2"] + 1) if (has_p1 or has_p2) else 0

        hard_offline = up == 0 and fault_injected != "scrape_gap"
        slurm_down = slurm_state in {"DOWN", "FAIL", "FAILING", "NOT_RESPONDING"}

        triggered_priority: Optional[str] = None
        persistence_str = f"0/{req_ticks}"
        if hard_offline or slurm_down or self.streaks[nid]["p1"] >= req_ticks:
            if has_p1:
                triggered_priority = "P1"
                persistence_str = f"{max(1, self.streaks[nid]['p1'])}/{req_ticks}"
        elif self.streaks[nid]["p2"] >= req_ticks:
            triggered_priority = "P2"
            persistence_str = f"{self.streaks[nid]['p2']}/{req_ticks}"
        elif has_p1 or has_p2:
            persistence_str = f"{max(self.streaks[nid]['p1'], self.streaks[nid]['p2'])}/{req_ticks}"

        # Determine clear node operational health state
        if up == 0 and fault_injected != "scrape_gap":
            health_status = "offline"
            health_classification = "Offline"
        elif up == 0 or (telemetry_age_seconds is not None and telemetry_age_seconds > stale_limit):
            health_status = "stale"
            health_classification = "Stale Telemetry"
        elif has_p1 or slurm_down:
            health_status = "critical"
            health_classification = "Critical"
        elif has_p2:
            health_status = "warning"
            health_classification = "Warning"
        else:
            health_status = "healthy"
            health_classification = "Healthy"

        if triggered_priority and evidence:
            self.healthy_streaks[nid] = 0
            # Prioritize P1 evidence items first, then deterministic telemetry over model flags
            prio_order = {"P1": 0, "P2": 1, "P3": 2}
            ordered = sorted(evidence, key=lambda item: prio_order.get(item["priority"], 3))
            primary = ordered[0]
            event_type = str(primary["event_type"])
            alert_source = str(primary["source"])
            recommended_checks = RECOMMENDED_CHECKS_BY_EVENT.get(
                event_type, f"Inspect host logs and metrics on {nid} ({ip})"
            ).format(node=nid, ip=ip)
            summary = " | ".join(item["summary"] for item in ordered[:3]) + f" | Slurm: {slurm_state}"
            title = f"[{triggered_priority}] {nid}: {primary['summary']}"

            model_score = None
            if alert_source in ("v7", "lstm_v8"):
                model_score = _num(primary.get("value"))

            ep = upsert_alert_episode(
                node_id=nid,
                priority=triggered_priority,
                event_type=event_type,
                alert_source=alert_source,
                title=title,
                summary=summary,
                recommended_checks=recommended_checks,
                timestamp_utc=timestamp_utc,
                evidence=ordered,
                data_mode=data_mode,
                model_score=model_score,
            )

            active_types = list({item["event_type"] for item in evidence})
            auto_resolve_node_episodes(nid, timestamp_utc, keep_event_types=active_types)

            if triggered_priority in ("P1", "P2") and ep.get("alert_points", 1) == 1:
                add_system_log(
                    timestamp_utc=timestamp_utc,
                    node_id=nid,
                    source="aiops-alert-engine",
                    severity="CRITICAL" if triggered_priority == "P1" else "WARNING",
                    event_type=event_type,
                    message=f"{title} - Persistence {persistence_str} confirmed. Check: {recommended_checks}",
                )
                self._maybe_dispatch_webhook(
                    nid,
                    triggered_priority,
                    title,
                    summary,
                    int(policy.get("cooldown_minutes", 30)),
                )

            return {
                "health_status": health_status,
                "health_classification": health_classification,
                "status_reason": primary["summary"],
                "alert_priority": triggered_priority,
                "severity": "critical" if triggered_priority == "P1" else "warning",
                "alert_source": alert_source,
                "event_type": event_type,
                "persistence_progress": persistence_str,
                "alert_active": True,
                "episode_id": ep["id"],
                "evidence": ordered,
                "recommended_checks": recommended_checks,
            }

        # Either healthy or awaiting persistence ticks
        if not evidence:
            self.healthy_streaks[nid] = self.healthy_streaks.get(nid, 0) + 1
            if self.healthy_streaks[nid] >= 3:
                auto_resolve_node_episodes(nid, timestamp_utc)
            status_reason = "All monitored telemetry and availability checks within normal bounds."
        else:
            self.healthy_streaks[nid] = 0
            status_reason = f"Pending persistence ({persistence_str}): {evidence[0]['summary']}"

        return {
            "health_status": health_status,
            "health_classification": health_classification,
            "status_reason": status_reason,
            "alert_priority": "OK",
            "severity": "none" if not evidence else ("critical" if has_p1 else "warning"),
            "alert_source": evidence[0]["source"] if evidence else "none",
            "event_type": evidence[0]["event_type"] if evidence else "normal",
            "persistence_progress": persistence_str,
            "alert_active": False,
            "episode_id": None,
            "evidence": evidence,
            "recommended_checks": "",
        }

    def _maybe_dispatch_webhook(
        self, node_id: str, priority: str, title: str, summary: str, cooldown_min: int
    ) -> None:
        if not ALERT_WEBHOOK_URL:
            return
        now = datetime.now(timezone.utc)
        cooldown = timedelta(minutes=cooldown_min)
        last = self.last_webhook_sent.get(node_id)
        if last and (now - last) < cooldown:
            return
        self.last_webhook_sent[node_id] = now

        def _send() -> None:
            try:
                requests.post(
                    ALERT_WEBHOOK_URL,
                    json={"text": f"*{title}*\n{summary}", "priority": priority, "node_id": node_id},
                    timeout=4,
                )
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()

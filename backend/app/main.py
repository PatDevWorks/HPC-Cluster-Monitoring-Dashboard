import asyncio
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import statistics
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from pydantic import BaseModel, Field

from .alert_engine import SmartAlertEngine
from .cluster_connector import REPLAY_PRESETS, ClusterTelemetryConnector
from .config import APP_METADATA, FRONTEND_DIST_DIR, HPC_ADMIN_TOKEN
from .database import (
    add_system_log,
    clear_all_runtime_records,
    get_app_settings,
    get_roi_totals,
    init_db,
    list_episodes,
    list_slurm_audit,
    list_system_logs,
    query_telemetry_history,
    record_slurm_action,
    record_telemetry_batch,
    update_app_settings,
    update_episode_status,
)
from .feature_pipeline import RollingFeaturePipeline
from .logs_diagnostics import (
    LOG_CATEGORIES,
    build_cluster_diagnostic_bundle_zip,
    build_node_diagnostic_bundle_zip,
    build_selected_logs_zip,
    format_log_entries_as_text,
    retrieve_node_logs,
)
from .ml_engine import ModelEngine
from .prometheus_service import (
    RANGE_CONFIG,
    check_prometheus_health,
    query_prometheus_range_history,
)
from .reports_service import build_report_data, export_report_csv, export_report_pdf
from .slurm_service import execute_slurm_cancel_job, sanitize_reason
from .ssh_bridge import get_ssh_public_status, validate_safe_identifier
from .terminal_service import TERMINAL_PRESET_GROUPS, execute_instance_terminal_command


# Prometheus Exporter Metrics (for native Grafana scraping alongside React)
PROM_FAILURE_PROB = Gauge(
    "hpc_aiops_failure_prob_1h",
    "Predicted probability of node failure within 1 hour (0-1)",
    ["node_id", "rack_id"],
)
PROM_ANOMALY_SCORE = Gauge(
    "hpc_aiops_anomaly_score",
    "Normalized ensemble unsupervised anomaly score (0-1)",
    ["node_id", "rack_id"],
)
PROM_CONSENSUS_VOTES = Gauge(
    "hpc_aiops_consensus_votes",
    "Number of unsupervised models flagging anomaly (0-4)",
    ["node_id"],
)
PROM_ALERT_PRIORITY = Gauge(
    "hpc_aiops_alert_priority_level",
    "Active alert priority (0=OK, 1=P3_Watch, 2=P2_Warning, 3=P1_Critical)",
    ["node_id"],
)
PROM_STRAGGLER_SCORE = Gauge(
    "hpc_aiops_mpi_straggler_score",
    "Cross-node MPI straggler asymmetry index (0-1)",
    ["node_id"],
)
PROM_CLUSTER_HEALTH = Gauge(
    "hpc_aiops_cluster_health_score",
    "Overall HPC cluster health score (0-100)",
)


class ModeSwitchRequest(BaseModel):
    mode: str
    prometheus_url: Optional[str] = None
    preset_id: Optional[str] = None


class DrainRequest(BaseModel):
    node_id: str
    reason: str = "Proactive AI early-warning drain"


class ResumeRequest(BaseModel):
    node_id: str


class JobCancelRequest(BaseModel):
    job_id: str
    reason: str = "Cancelled by administrator"


class FaultInjectRequest(BaseModel):
    node_id: str
    fault_type: str


class FaultClearRequest(BaseModel):
    node_id: Optional[str] = None


class AlertActionRequest(BaseModel):
    action: str  # acknowledge | silence | resolve


class ZipLogsRequest(BaseModel):
    node_id: str
    categories: List[str] = Field(default_factory=lambda: ["system", "kernel"])
    lines: int = 250
    keyword: Optional[str] = None
    severity: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    prometheus_url: Optional[str] = None
    grafana_url: Optional[str] = None
    refresh_interval_sec: Optional[float] = None
    ssh_host: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_port: Optional[int] = None
    alert_policy: Optional[Dict[str, Any]] = None
    node_overrides: Optional[Dict[str, Any]] = None


class PrometheusTestRequest(BaseModel):
    prometheus_url: str


class TerminalExecRequest(BaseModel):
    node_id: str = "head-node"
    command: str
    confirmed: bool = False


class PipelineOrchestrator:
    def __init__(self) -> None:
        self.connector = ClusterTelemetryConnector()
        self.features = RollingFeaturePipeline(maxlen=96)
        self.ml_engine = ModelEngine()
        self.alerts = SmartAlertEngine()
        self.chart_history: Dict[str, Deque[Dict[str, Any]]] = {}
        self.cluster_history: Deque[Dict[str, Any]] = deque(maxlen=72)
        self.latest_snapshot: Dict[str, Any] = {}
        self.clients: Set[WebSocket] = set()
        self.stream_interval_sec: float = 3.0
        self.paused: bool = False
        self._tick_counter: int = 0

    def sync_interval_from_settings(self) -> None:
        try:
            s = get_app_settings()
            interval = float(s.get("refresh_interval_sec", 3.0))
            self.stream_interval_sec = max(1.0, min(60.0, interval))
        except Exception:
            pass

    def step_once(self) -> Dict[str, Any]:
        self._tick_counter += 1
        batch = self.connector.fetch_next_batch()
        ts = batch["timestamp_utc"]
        enriched_map = self.features.ingest_batch(batch["nodes"])

        scored_nodes: List[Dict[str, Any]] = []
        prio_to_num = {"OK": 0, "MAINTENANCE": 0, "P3": 1, "P2": 2, "P3_WATCH": 1, "P1": 3}

        for raw_node in batch["nodes"]:
            nid = raw_node["node_id"]
            ef = enriched_map[nid]
            ml_out = self.ml_engine.score_node(ef)
            alert_out = self.alerts.evaluate(
                node_sample=ef,
                ml_result=ml_out,
                timestamp_utc=ts,
                data_mode=self.connector.mode,
            )

            merged = {
                **ef,
                **ml_out,
                **alert_out,
            }
            scored_nodes.append(merged)

            rack = str(merged.get("rack_id", "rack-1"))
            PROM_FAILURE_PROB.labels(node_id=nid, rack_id=rack).set(ml_out["failure_prob_1h"])
            PROM_ANOMALY_SCORE.labels(node_id=nid, rack_id=rack).set(ml_out["anomaly_score"])
            PROM_CONSENSUS_VOTES.labels(node_id=nid).set(ml_out["consensus_count"])
            PROM_ALERT_PRIORITY.labels(node_id=nid).set(
                prio_to_num.get(alert_out["alert_priority"], 0)
            )
            PROM_STRAGGLER_SCORE.labels(node_id=nid).set(
                float(merged.get("mpi_straggler_score", 0.0))
            )

            if nid not in self.chart_history:
                self.chart_history[nid] = deque(maxlen=60)
            short_time = ts[11:19] if len(ts) >= 19 else ts
            self.chart_history[nid].append(
                {
                    "time": short_time,
                    "timestamp_utc": ts,
                    "up": merged.get("up", 1),
                    "health_score": merged.get("node_health_score"),
                    "failure_prob_pct": round(ml_out["failure_prob_1h"] * 100.0, 2),
                    "failure_prob_6h_pct": round(ml_out["failure_prob_6h"] * 100.0, 2),
                    "anomaly_score_pct": round(ml_out["anomaly_score"] * 100.0, 2),
                    "cpu": merged.get("cpu_utilization_percent"),
                    "iowait": merged.get("cpu_iowait_percent"),
                    "memory": merged.get("memory_used_percent"),
                    "swap": merged.get("swap_used_percent"),
                    "load1": merged.get("load1"),
                    "load5": merged.get("load5"),
                    "norm_load": merged.get("normalized_load1"),
                    "temp": merged.get("cpu_temperature_celsius"),
                    "root_fs": merged.get("root_used_percent"),
                    "scratch": merged.get("scratch_used_percent"),
                    "disk_read_mb": (
                        round(float(merged["disk_read_bytes_per_second"]) / (1024 * 1024), 2)
                        if merged.get("disk_read_bytes_per_second") is not None
                        else None
                    ),
                    "disk_write_mb": (
                        round(float(merged["disk_write_bytes_per_second"]) / (1024 * 1024), 2)
                        if merged.get("disk_write_bytes_per_second") is not None
                        else None
                    ),
                    "disk_io": merged.get("disk_io_utilization_percent"),
                    "net_rx_mb": (
                        round(float(merged["network_receive_bytes_per_second"]) / (1024 * 1024), 2)
                        if merged.get("network_receive_bytes_per_second") is not None
                        else None
                    ),
                    "net_tx_mb": (
                        round(float(merged["network_transmit_bytes_per_second"]) / (1024 * 1024), 2)
                        if merged.get("network_transmit_bytes_per_second") is not None
                        else None
                    ),
                    "net_err": merged.get("network_errors_per_second"),
                    "psi_cpu": merged.get("psi_cpu_percent"),
                    "psi_mem": merged.get("psi_memory_percent"),
                    "psi_io": merged.get("psi_io_percent"),
                    "straggler_pct": round(float(merged.get("mpi_straggler_score", 0.0)) * 100.0, 1),
                }
            )

        # Persist to SQLite every 2nd tick (keeps DB write overhead tiny while building full history)
        if self._tick_counter % 2 == 1:
            try:
                record_telemetry_batch(ts, self.connector.mode, scored_nodes)
            except Exception:
                pass

        episodes = list_episodes(limit=60)
        active_eps = [e for e in episodes if e["status"] in ("active", "acknowledged")]

        # Aggregate cluster-wide KPIs & Cluster Health Score
        online_nodes = [n for n in scored_nodes if n.get("up") == 1]
        cpu_vals = [float(n["cpu_utilization_percent"]) for n in online_nodes if n.get("cpu_utilization_percent") is not None]
        mem_vals = [float(n["memory_used_percent"]) for n in online_nodes if n.get("memory_used_percent") is not None]
        health_vals = [float(n["node_health_score"]) for n in scored_nodes if n.get("node_health_score") is not None]

        cluster_cpu = round(statistics.fmean(cpu_vals), 1) if cpu_vals else None
        cluster_mem = round(statistics.fmean(mem_vals), 1) if mem_vals else None
        avail_ratio = len(online_nodes) / max(len(scored_nodes), 1)
        raw_health = (statistics.fmean(health_vals) * avail_ratio) if health_vals else 0.0
        cluster_health_score = round(max(0.0, min(100.0, raw_health)), 1)
        PROM_CLUSTER_HEALTH.set(cluster_health_score)

        if len(online_nodes) == 0:
            health_label = "Offline"
        elif cluster_health_score >= 92.0 and not any(e["priority"] == "P1" for e in active_eps):
            health_label = "Excellent"
        elif cluster_health_score >= 78.0:
            health_label = "Healthy"
        elif cluster_health_score >= 55.0:
            health_label = "Degraded"
        else:
            health_label = "Critical"

        peak_risk_pct = round(
            max((float(n["failure_prob_1h"]) for n in scored_nodes), default=0.0) * 100.0, 2
        )
        mean_anom_pct = round(
            statistics.fmean([float(n["anomaly_score"]) for n in scored_nodes]) * 100.0, 1
        ) if scored_nodes else 0.0

        short_time = ts[11:16] if len(ts) >= 16 else ts
        self.cluster_history.append(
            {
                "time": short_time,
                "timestamp_utc": ts,
                "health_score": cluster_health_score,
                "cpu_percent": cluster_cpu,
                "memory_percent": cluster_mem,
                "failure_risk_pct": peak_risk_pct,
                "anomaly_pct": mean_anom_pct,
                "nodes_online": len(online_nodes),
            }
        )

        # Enrich Slurm jobs with blast-radius tags
        node_risk_lookup = {n["node_id"]: n for n in scored_nodes}
        enriched_jobs = []
        for job in batch.get("slurm_jobs", []):
            jc = dict(job)
            job_nodes = jc.get("nodes", [])
            max_p = max(
                (float(node_risk_lookup[nid]["failure_prob_1h"]) for nid in job_nodes if nid in node_risk_lookup),
                default=0.0,
            )
            flagged = [
                nid
                for nid in job_nodes
                if nid in node_risk_lookup
                and node_risk_lookup[nid]["alert_priority"] in ("P1", "P2")
            ]
            jc["max_node_failure_prob"] = round(max_p, 4)
            jc["at_risk_nodes"] = flagged
            jc["blast_status"] = (
                "CRITICAL_RISK"
                if max_p >= 0.40 or any(node_risk_lookup.get(nid, {}).get("alert_priority") == "P1" for nid in job_nodes)
                else ("WARNING_RISK" if flagged else "HEALTHY")
            )
            enriched_jobs.append(jc)

        settings_cur = get_app_settings()

        snapshot = {
            "timestamp_utc": ts,
            "mode": self.connector.mode,
            "mode_label": batch.get("mode_label", ""),
            "is_synthetic": bool(batch.get("is_synthetic", False)),
            "is_simulated": bool(batch.get("is_simulated", False)),
            "prometheus_connected": bool(batch.get("prometheus_connected", False)),
            "slurm_connected": bool(batch.get("slurm_connected", False)),
            "slurm_source": batch.get("slurm_source", "unavailable"),
            "preset_id": self.connector.replay_preset_id,
            "preset_description": batch.get("preset_description"),
            "replay_progress": batch.get("replay_progress"),
            "source_warning": batch.get("source_warning"),
            "paused": self.paused,
            "refresh_interval_sec": self.stream_interval_sec,
            "grafana_url": settings_cur.get("grafana_url", "http://localhost:3000"),
            "prometheus_url": self.connector.prometheus_url,
            "model_status": self.ml_engine.get_status(),
            "ssh_status": get_ssh_public_status(),
            "admin_token_required": bool(HPC_ADMIN_TOKEN),
            "active_fault_injections": self.connector.injected_faults,
            "kpis": {
                "nodes_total": len(scored_nodes),
                "nodes_online": len(online_nodes),
                "nodes_drained": sum(1 for n in scored_nodes if "DRAIN" in str(n.get("slurm_state", ""))),
                "cluster_health_score": cluster_health_score,
                "cluster_health_label": health_label,
                "cluster_cpu_percent": cluster_cpu,
                "cluster_memory_percent": cluster_mem,
                "active_episodes_total": len(active_eps),
                "p1_count": sum(1 for e in active_eps if e["priority"] == "P1"),
                "p2_count": sum(1 for e in active_eps if e["priority"] == "P2"),
                "p3_count": sum(1 for e in active_eps if e["priority"] == "P3"),
                "peak_failure_prob_pct": peak_risk_pct,
                "peak_straggler_pct": round(
                    max((float(n.get("mpi_straggler_score", 0.0)) for n in scored_nodes), default=0.0) * 100.0, 1
                ),
                **get_roi_totals(),
            },
            "cluster_history": list(self.cluster_history),
            "nodes": scored_nodes,
            "history": {nid: list(series) for nid, series in self.chart_history.items()},
            "alert_episodes": episodes,
            "slurm_jobs": enriched_jobs,
            "slurm_audit": list_slurm_audit(limit=35),
            "system_logs": list_system_logs(limit=40),
            "replay_presets": REPLAY_PRESETS,
        }
        self.latest_snapshot = snapshot
        return snapshot

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        dead: List[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


orchestrator = PipelineOrchestrator()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    orchestrator.sync_interval_from_settings()
    add_system_log(
        timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        node_id="head-node",
        source="aiops-daemon",
        severity="INFO",
        event_type="startup",
        message="Sol Plaatje A Dev Cluster Dashboard v2.0 online. Real-time telemetry & ML pipeline initialized.",
    )
    # Warm up initial ticks (1 tick if querying real live Prometheus to avoid burst requests, 14 if local sim/replay)
    warmup_ticks = 2 if orchestrator.connector.mode == "live_prometheus" else 14
    for _ in range(warmup_ticks):
        orchestrator.step_once()

    stop_event = asyncio.Event()

    async def _loop() -> None:
        while not stop_event.is_set():
            try:
                if not orchestrator.paused:
                    snap = orchestrator.step_once()
                    await orchestrator.broadcast(snap)
            except Exception:
                pass
            await asyncio.sleep(orchestrator.stream_interval_sec)

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()


app = FastAPI(
    title=APP_METADATA["name"],
    version=APP_METADATA["version"],
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_admin_role(
    x_operator_role: Optional[str] = Header(default="admin"),
    x_admin_token: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> None:
    """Enforce role-based permissions and optional HPC_ADMIN_TOKEN on administrative mutations."""
    if (x_operator_role or "admin").lower() == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Read-only Viewer role cannot execute administrative cluster operations.",
        )
    if HPC_ADMIN_TOKEN:
        supplied = (x_admin_token or token or "").strip()
        if supplied != HPC_ADMIN_TOKEN:
            raise HTTPException(
                status_code=403,
                detail="Valid administrator token required (HPC_ADMIN_TOKEN is active on server).",
            )


def require_diagnostic_access(
    x_admin_token: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> None:
    """Protect node log & diagnostic bundle download endpoints when HPC_ADMIN_TOKEN is configured."""
    if HPC_ADMIN_TOKEN:
        supplied = (x_admin_token or token or "").strip()
        if supplied != HPC_ADMIN_TOKEN:
            raise HTTPException(
                status_code=403,
                detail="Valid administrator token required to access diagnostic bundles.",
            )


# ---------------------------------------------------------------------------
# Core Pipeline & State Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/state")
def get_current_state() -> Dict[str, Any]:
    if not orchestrator.latest_snapshot:
        return orchestrator.step_once()
    return orchestrator.latest_snapshot


@app.post("/api/state/refresh")
async def force_state_refresh() -> Dict[str, Any]:
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return snap


@app.get("/api/models/status")
def get_models_status() -> Dict[str, Any]:
    return orchestrator.ml_engine.get_status()


@app.post("/api/models/reload")
async def reload_models() -> Dict[str, Any]:
    status = orchestrator.ml_engine.reload_models()
    add_system_log(
        timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        node_id="head-node",
        source="ml-adapter",
        severity="INFO",
        event_type="model_reload",
        message=f"Reloaded backend/models/ -> {status['engine_label']} ({len(status['loaded_files'])} artifacts)",
    )
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return status


@app.post("/api/mode")
async def switch_pipeline_mode(req: ModeSwitchRequest) -> Dict[str, Any]:
    if req.mode not in ("live_prometheus", "live_cluster_sim", "scc_dataset_replay"):
        raise HTTPException(status_code=400, detail="Unsupported mode")
    if req.prometheus_url:
        update_app_settings({"prometheus_url": req.prometheus_url.rstrip("/")})
    orchestrator.features.reset()
    orchestrator.alerts.reset()
    orchestrator.chart_history.clear()
    orchestrator.cluster_history.clear()
    orchestrator.connector.clear_faults()
    clear_all_runtime_records()
    orchestrator.connector.set_mode(
        mode=req.mode,
        prometheus_url=req.prometheus_url,
        preset_id=req.preset_id,
    )
    steps = 1 if req.mode == "live_prometheus" else (10 if req.mode == "scc_dataset_replay" else 8)
    snap = {}
    for _ in range(steps):
        snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return snap


@app.post("/api/stream/pause")
async def toggle_stream_pause() -> Dict[str, Any]:
    orchestrator.paused = not orchestrator.paused
    if orchestrator.latest_snapshot:
        orchestrator.latest_snapshot["paused"] = orchestrator.paused
        await orchestrator.broadcast(orchestrator.latest_snapshot)
    return {"paused": orchestrator.paused}


# ---------------------------------------------------------------------------
# Live Monitoring & Historical Prometheus Range Queries (5m..24h)
# ---------------------------------------------------------------------------

@app.get("/api/monitoring/history")
def get_monitoring_range_history(
    range_key: str = Query("1h", description="5m | 15m | 1h | 6h | 12h | 24h"),
    node_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    if range_key not in RANGE_CONFIG:
        range_key = "1h"
    minutes, _step = RANGE_CONFIG[range_key]

    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    nodes = snap.get("nodes", [])
    target_node = next((n for n in nodes if n["node_id"] == node_id), None) if node_id else None
    instance_filter = target_node.get("instance") if target_node else None

    # 1. If connected to real Prometheus, query /api/v1/query_range directly!
    if orchestrator.connector.mode == "live_prometheus" and orchestrator.connector.prometheus_connected:
        prom_series = query_prometheus_range_history(
            prometheus_url=orchestrator.connector.prometheus_url,
            range_key=range_key,
            instance=instance_filter,
        )
        if prom_series is not None:
            return {
                "range_key": range_key,
                "node_id": node_id or "cluster",
                "source": "prometheus_query_range",
                "series": prom_series,
            }

    # 2. Otherwise serve persisted SQLite telemetry_history (or live ring buffer)
    db_rows = query_telemetry_history(range_minutes=minutes, node_id=node_id, limit=720)
    if db_rows:
        # Group by timestamp if cluster-wide, or map directly if single node
        if node_id:
            mapped = [
                {
                    "timestamp_utc": r["timestamp_utc"],
                    "time": r["timestamp_utc"][11:19] if len(r["timestamp_utc"]) >= 19 else r["timestamp_utc"],
                    "up": r["up"],
                    "health_score": r["health_score"],
                    "cpu": r["cpu_percent"],
                    "iowait": r["iowait_percent"],
                    "memory": r["memory_percent"],
                    "swap": r["swap_percent"],
                    "load1": r["load1"],
                    "norm_load": r["normalized_load1"],
                    "scratch": r["scratch_percent"],
                    "disk_read_mb": r["disk_read_mb"],
                    "disk_write_mb": r["disk_write_mb"],
                    "disk_io": r["disk_io_percent"],
                    "net_rx_mb": r["net_rx_mb"],
                    "net_tx_mb": r["net_tx_mb"],
                    "net_err": r["net_err_s"],
                    "temp": r["temp_celsius"],
                    "failure_prob_pct": round(float(r["failure_prob_1h"]) * 100.0, 2) if r["failure_prob_1h"] is not None else None,
                    "anomaly_score_pct": round(float(r["anomaly_score"]) * 100.0, 2) if r["anomaly_score"] is not None else None,
                }
                for r in db_rows
            ]
        else:
            by_ts: Dict[str, List[Dict[str, Any]]] = {}
            for r in db_rows:
                by_ts.setdefault(r["timestamp_utc"], []).append(r)
            mapped = []
            for ts_k in sorted(by_ts.keys()):
                grp = by_ts[ts_k]
                cpus = [float(x["cpu_percent"]) for x in grp if x["cpu_percent"] is not None]
                mems = [float(x["memory_percent"]) for x in grp if x["memory_percent"] is not None]
                hlths = [float(x["health_score"]) for x in grp if x["health_score"] is not None]
                dws = [float(x["disk_write_mb"]) for x in grp if x["disk_write_mb"] is not None]
                nrxs = [float(x["net_rx_mb"]) for x in grp if x["net_rx_mb"] is not None]
                risks = [float(x["failure_prob_1h"]) * 100.0 for x in grp if x["failure_prob_1h"] is not None]
                mapped.append(
                    {
                        "timestamp_utc": ts_k,
                        "time": ts_k[11:19] if len(ts_k) >= 19 else ts_k,
                        "health_score": round(statistics.fmean(hlths), 1) if hlths else None,
                        "cpu": round(statistics.fmean(cpus), 2) if cpus else None,
                        "memory": round(statistics.fmean(mems), 2) if mems else None,
                        "disk_write_mb": round(sum(dws), 2) if dws else None,
                        "net_rx_mb": round(sum(nrxs), 2) if nrxs else None,
                        "failure_prob_pct": round(max(risks), 2) if risks else 0.0,
                    }
                )
        return {
            "range_key": range_key,
            "node_id": node_id or "cluster",
            "source": "recorded_telemetry_db",
            "series": mapped,
        }

    fallback_series = snap.get("history", {}).get(node_id, []) if node_id else snap.get("cluster_history", [])
    return {
        "range_key": range_key,
        "node_id": node_id or "cluster",
        "source": "in_memory_buffer",
        "series": fallback_series,
    }


# ---------------------------------------------------------------------------
# Slurm Workload & Safe Administrative Operations
# ---------------------------------------------------------------------------

@app.post("/api/slurm/drain", dependencies=[Depends(require_admin_role)])
async def slurm_drain_node(req: DrainRequest) -> Dict[str, Any]:
    if not validate_safe_identifier(req.node_id):
        raise HTTPException(status_code=400, detail="Invalid node identifier")
    outcome = orchestrator.connector.drain_node(req.node_id, req.reason)
    record_slurm_action(
        node_id=req.node_id,
        action="DRAIN",
        reason=sanitize_reason(req.reason),
        jobs_protected=outcome["jobs_protected"],
        core_hours_saved=outcome["core_hours_saved"],
        kwh_saved=outcome["kwh_saved"],
        executed_mode=outcome["executed_mode"],
    )
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return outcome


@app.post("/api/slurm/resume", dependencies=[Depends(require_admin_role)])
async def slurm_resume_node(req: ResumeRequest) -> Dict[str, Any]:
    if not validate_safe_identifier(req.node_id):
        raise HTTPException(status_code=400, detail="Invalid node identifier")
    outcome = orchestrator.connector.resume_node(req.node_id)
    record_slurm_action(
        node_id=req.node_id,
        action="RESUME",
        reason="Administrator resumed node",
        jobs_protected=0,
        core_hours_saved=0.0,
        kwh_saved=0.0,
        executed_mode=outcome.get("executed_mode", "scontrol"),
    )
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return outcome


@app.post("/api/slurm/cancel", dependencies=[Depends(require_admin_role)])
async def slurm_cancel_job_endpoint(req: JobCancelRequest) -> Dict[str, Any]:
    try:
        outcome = execute_slurm_cancel_job(req.job_id, req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    orchestrator.connector.cancelled_sim_jobs.add(req.job_id)
    record_slurm_action(
        node_id=f"job-{req.job_id}",
        action="CANCEL_JOB",
        reason=sanitize_reason(req.reason),
        jobs_protected=0,
        core_hours_saved=0.0,
        kwh_saved=0.0,
        executed_mode=outcome["source"],
    )
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return outcome


@app.get("/api/slurm/audit")
def get_slurm_audit_history() -> Dict[str, Any]:
    return {"audit": list_slurm_audit(limit=80)}


# ---------------------------------------------------------------------------
# Node Logs & Secure Diagnostic Bundles
# ---------------------------------------------------------------------------

def _resolve_node_target(node_id: str) -> Dict[str, Any]:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    for n in snap.get("nodes", []):
        if n["node_id"] == node_id:
            return n
    return {"node_id": node_id, "ip": "localhost", "ssh_target": "localhost"}


@app.get("/api/logs", dependencies=[Depends(require_diagnostic_access)])
def get_node_logs_endpoint(
    node_id: str = Query("head-node"),
    category: str = Query("system"),
    lines: int = Query(200, ge=20, le=1000),
    keyword: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        node_meta = _resolve_node_target(node_id)
        payload = retrieve_node_logs(
            node_id=node_id,
            target_ip=str(node_meta.get("ssh_target") or node_meta.get("ip") or "localhost"),
            category=category,
            lines=lines,
            keyword=keyword,
            severity=severity,
            since=since,
            until=until,
        )
        payload["available_categories"] = [
            {"id": k, "label": v["label"]} for k, v in LOG_CATEGORIES.items()
        ]
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/logs/download", dependencies=[Depends(require_diagnostic_access)])
def download_single_node_log(
    node_id: str = Query("head-node"),
    category: str = Query("system"),
    lines: int = Query(500, ge=20, le=1000),
    keyword: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
) -> Response:
    try:
        node_meta = _resolve_node_target(node_id)
        payload = retrieve_node_logs(
            node_id=node_id,
            target_ip=str(node_meta.get("ssh_target") or node_meta.get("ip") or "localhost"),
            category=category,
            lines=lines,
            keyword=keyword,
            severity=severity,
        )
        content = format_log_entries_as_text(payload)
        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = f"{node_id}_{category}_{ts_slug}.log"
        return Response(
            content=content.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/logs/download-zip", dependencies=[Depends(require_diagnostic_access)])
def download_selected_logs_zip(req: ZipLogsRequest) -> Response:
    if not validate_safe_identifier(req.node_id):
        raise HTTPException(status_code=400, detail="Invalid node identifier")
    node_meta = _resolve_node_target(req.node_id)
    zip_bytes = build_selected_logs_zip(
        node_id=req.node_id,
        target_ip=str(node_meta.get("ssh_target") or node_meta.get("ip") or "localhost"),
        categories=req.categories,
        lines=req.lines,
        keyword=req.keyword,
        severity=req.severity,
    )
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"{req.node_id}_selected_logs_{ts_slug}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/diagnostics/node/{node_id}", dependencies=[Depends(require_diagnostic_access)])
def download_node_diagnostic_bundle(node_id: str) -> Response:
    if not validate_safe_identifier(node_id):
        raise HTTPException(status_code=400, detail="Invalid node identifier")
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    node = next((n for n in snap.get("nodes", []) if n["node_id"] == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found in cluster")
    record_slurm_action(
        node_id=node_id,
        action="DIAGNOSTIC_BUNDLE",
        reason="Generated sanitized node diagnostic bundle",
        jobs_protected=0,
        core_hours_saved=0.0,
        kwh_saved=0.0,
        executed_mode="diagnostics_api",
    )
    zip_bytes = build_node_diagnostic_bundle_zip(node, orchestrator.ml_engine.get_status())
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"{node_id}_diagnostic_bundle_{ts_slug}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/diagnostics/cluster", dependencies=[Depends(require_diagnostic_access)])
def download_cluster_diagnostic_bundle() -> Response:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    record_slurm_action(
        node_id="cluster",
        action="CLUSTER_DIAGNOSTIC_BUNDLE",
        reason="Generated cluster-wide sanitized diagnostic bundle",
        jobs_protected=0,
        core_hours_saved=0.0,
        kwh_saved=0.0,
        executed_mode="diagnostics_api",
    )
    zip_bytes = build_cluster_diagnostic_bundle_zip(snap)
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"sol_plaatje_a_cluster_diagnostics_{ts_slug}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------------------
# Audited Instance Terminal Console
# ---------------------------------------------------------------------------

@app.get("/api/terminal/presets")
def get_terminal_presets() -> Dict[str, Any]:
    return {
        "preset_groups": TERMINAL_PRESET_GROUPS,
        "ssh_status": get_ssh_public_status(),
    }


@app.post("/api/terminal/exec", dependencies=[Depends(require_admin_role)])
def execute_terminal_command_endpoint(req: TerminalExecRequest) -> Dict[str, Any]:
    if not validate_safe_identifier(req.node_id):
        raise HTTPException(status_code=400, detail="Invalid node identifier")
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    nodes = snap.get("nodes", [])
    target_node = next((n for n in nodes if n["node_id"] == req.node_id), None)
    if not target_node:
        raise HTTPException(status_code=404, detail=f"Instance '{req.node_id}' not found in cluster")
    try:
        return execute_instance_terminal_command(
            node=target_node,
            all_nodes=nodes,
            slurm_jobs=snap.get("slurm_jobs", []),
            pipeline_mode=orchestrator.connector.mode,
            raw_command=req.command,
            confirmed=req.confirmed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Performance Analytics & Exportable CSV / PDF Reports
# ---------------------------------------------------------------------------

@app.get("/api/analytics/summary")
def get_performance_analytics_summary(range_key: str = Query("1h")) -> Dict[str, Any]:
    minutes, _ = RANGE_CONFIG.get(range_key, (60, 30))
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    nodes = snap.get("nodes", [])
    hist_rows = query_telemetry_history(range_minutes=minutes, limit=1500)

    # Compute per-node historical averages & availability %
    by_node: Dict[str, List[Dict[str, Any]]] = {}
    for r in hist_rows:
        by_node.setdefault(r["node_id"], []).append(r)

    node_comparisons = []
    bottlenecks = []
    for n in nodes:
        nid = n["node_id"]
        nrows = by_node.get(nid, [])
        avail_pct = (
            round((sum(1 for x in nrows if x["up"] == 1) / len(nrows)) * 100.0, 2)
            if nrows
            else (100.0 if n.get("up") == 1 else 0.0)
        )
        avg_cpu = _avg_col(nrows, "cpu_percent", n.get("cpu_utilization_percent"))
        avg_mem = _avg_col(nrows, "memory_percent", n.get("memory_used_percent"))
        avg_io = _avg_col(nrows, "iowait_percent", n.get("cpu_iowait_percent"))
        avg_dw = _avg_col(nrows, "disk_write_mb", 0.0)
        avg_nrx = _avg_col(nrows, "net_rx_mb", 0.0)

        node_comparisons.append(
            {
                "node_id": nid,
                "display_name": n.get("display_name") or nid,
                "role": n.get("role", "compute"),
                "availability_pct": avail_pct,
                "avg_cpu": avg_cpu,
                "avg_memory": avg_mem,
                "avg_iowait": avg_io,
                "avg_disk_write_mb": avg_dw,
                "avg_net_rx_mb": avg_nrx,
                "health_score": n.get("node_health_score", 100.0),
            }
        )

        # Bottleneck classification from real observed values
        if (avg_io or 0) >= 10.0:
            bottlenecks.append(
                {
                    "node_id": nid,
                    "type": "Storage / NFS I/O Wait Stall",
                    "severity": "high" if (avg_io or 0) >= 20 else "medium",
                    "detail": f"Mean CPU I/O wait is {avg_io:.1f}% over {range_key}, throttling compute throughput.",
                }
            )
        if (avg_mem or 0) >= 85.0:
            bottlenecks.append(
                {
                    "node_id": nid,
                    "type": "Memory Capacity Pressure",
                    "severity": "high" if (avg_mem or 0) >= 92 else "medium",
                    "detail": f"Mean RAM utilisation at {avg_mem:.1f}%; elevated swap/OOM risk for large MPI ranks.",
                }
            )
        if float(n.get("mpi_straggler_score") or 0) >= 0.45:
            bottlenecks.append(
                {
                    "node_id": nid,
                    "type": "MPI Collective Straggler Imbalance",
                    "severity": "medium",
                    "detail": f"Node trails peer compute median (straggler index {(float(n['mpi_straggler_score'])*100):.0f}%).",
                }
            )

    overall_avail = (
        round(statistics.fmean([c["availability_pct"] for c in node_comparisons]), 2)
        if node_comparisons
        else 100.0
    )

    return {
        "range_key": range_key,
        "overall_availability_pct": overall_avail,
        "node_comparisons": node_comparisons,
        "bottlenecks": bottlenecks,
    }


def _avg_col(rows: List[Dict[str, Any]], key: str, fallback: Any) -> Optional[float]:
    vals = [float(r[key]) for r in rows if r.get(key) is not None]
    if vals:
        return round(statistics.fmean(vals), 2)
    return round(float(fallback), 2) if fallback is not None else None


@app.get("/api/reports/preview")
def preview_report_endpoint(
    report_type: str = Query("cluster_summary"),
    range_minutes: int = Query(60, ge=5, le=10080),
) -> Dict[str, Any]:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    return build_report_data(report_type=report_type, snapshot=snap, range_minutes=range_minutes)


@app.get("/api/reports/export")
def export_report_endpoint(
    report_type: str = Query("cluster_summary"),
    format: str = Query("csv"),
    range_minutes: int = Query(60, ge=5, le=10080),
) -> Response:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    payload = build_report_data(report_type=report_type, snapshot=snap, range_minutes=range_minutes)
    if format.lower() == "pdf":
        pdf_bytes, fname = export_report_pdf(payload)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    csv_bytes, fname = export_report_csv(payload)
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------------------
# Fault Injection Demo Lab & Alert Triage
# ---------------------------------------------------------------------------

@app.post("/api/fault-inject")
async def inject_demo_fault(req: FaultInjectRequest) -> Dict[str, Any]:
    res = orchestrator.connector.inject_fault(req.node_id, req.fault_type)
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return res


@app.post("/api/fault-clear")
async def clear_demo_fault(req: FaultClearRequest) -> Dict[str, Any]:
    orchestrator.connector.clear_faults(req.node_id)
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return {"cleared": True}


@app.post("/api/alerts/{episode_id}/action")
async def alert_triage_action(episode_id: int, req: AlertActionRequest) -> Dict[str, Any]:
    if req.action not in ("acknowledge", "silence", "resolve"):
        raise HTTPException(status_code=400, detail="Unsupported alert action")
    silenced_until = None
    if req.action == "silence":
        silenced_until = (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = update_episode_status(episode_id, req.action, silenced_until)
    if not updated:
        raise HTTPException(status_code=404, detail="Episode not found")
    if orchestrator.latest_snapshot:
        orchestrator.latest_snapshot["alert_episodes"] = list_episodes(limit=60)
        await orchestrator.broadcast(orchestrator.latest_snapshot)
    return updated


# ---------------------------------------------------------------------------
# Settings & Service Health Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings_endpoint() -> Dict[str, Any]:
    settings = get_app_settings()
    prom_health = check_prometheus_health(settings.get("prometheus_url", orchestrator.connector.prometheus_url))
    return {
        "app_info": APP_METADATA,
        "settings": settings,
        "service_health": {
            "backend_api": "online",
            "websocket_clients": len(orchestrator.clients),
            "sqlite_store": "online",
            "prometheus": prom_health,
            "ssh_bridge": get_ssh_public_status(),
            "slurm_connected": orchestrator.connector.slurm_connected,
            "slurm_source": orchestrator.connector.slurm_source,
            "ml_engine": orchestrator.ml_engine.get_status(),
        },
    }


@app.put("/api/settings", dependencies=[Depends(require_admin_role)])
async def update_settings_endpoint(req: SettingsUpdateRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    saved = update_app_settings(updates)
    orchestrator.sync_interval_from_settings()
    orchestrator.connector.sync_from_settings()
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return {"saved": True, "settings": saved}


@app.post("/api/settings/test-prometheus")
def test_prometheus_connection(req: PrometheusTestRequest) -> Dict[str, Any]:
    return check_prometheus_health(req.prometheus_url, timeout=2.5)


# ---------------------------------------------------------------------------
# Prometheus Exporter & Real-Time WebSocket Stream
# ---------------------------------------------------------------------------

@app.get("/metrics")
def prometheus_metrics_export() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws/live")
async def websocket_live_stream(ws: WebSocket) -> None:
    await ws.accept()
    orchestrator.clients.add(ws)
    try:
        if orchestrator.latest_snapshot:
            await ws.send_json(orchestrator.latest_snapshot)
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        orchestrator.clients.discard(ws)
    except Exception:
        orchestrator.clients.discard(ws)


# Optional single-port production SPA static hosting when frontend/dist is built
if FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "index.html").exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_react_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST_DIR / "index.html"))

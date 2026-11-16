from dotenv import load_dotenv
load_dotenv()
import asyncio
from collections import deque
from contextlib import asynccontextmanager
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import re
from pathlib import Path
import statistics
import tempfile
from .auth_routes import router as auth_router
from typing import Any, Deque, Dict, List, Literal, Optional, Set
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from pydantic import BaseModel, Field

from .alert_engine import SmartAlertEngine
from .cluster_connector import REPLAY_PRESETS, ClusterTelemetryConnector
from .config import (
    APP_METADATA,
    FRONTEND_DIST_DIR,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    AUTH_COOKIE_NAME,
)

from .auth_dependencies import get_current_user, require_roles
from .auth_service import get_session_user, record_auth_event
from .email_service import EmailDeliveryError, send_transactional_email
from .evaluation_service import compute_model_comparison_summary
from .database import (
    add_system_log,
    append_gemini_message,
    cleanup_model_observations,
    auto_resolve_stale_offline_prometheus_episodes,
    backup_database_to_file,
    clear_all_runtime_records,
    create_experiment,
    create_ai_conversation,
    clear_ai_conversation,
    delete_ai_conversation,
    delete_experiment,
    ensure_ai_conversation,
    get_ai_conversation,
    get_ai_report,
    get_app_settings,
    get_roi_totals,
    init_db,
    list_ai_reports,
    list_auth_audit_logs,
    list_auth_invitations,
    list_auth_users,
    list_episodes,
    list_experiments,
    list_gemini_messages,
    list_ai_conversations,
    list_model_observations,
    list_slurm_audit,
    get_slurm_job_submission,
    list_slurm_job_submission_ids,
    list_system_logs,
    list_terminal_audit,
    query_telemetry_history,
    record_model_observation,
    record_slurm_action,
    record_telemetry_batch,
    record_terminal_audit,
    save_ai_report,
    save_slurm_job_submission,
    update_ai_report,
    update_app_settings,
    rename_ai_conversation,
    set_ai_conversation_provider,
    update_auth_user,
    update_episode_status,
    update_experiment,
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
from .lstm_v8_service import LSTMV8Service
from .v7_service import V7Service
from .prometheus_service import (
    RANGE_CONFIG,
    check_prometheus_health,
    query_prometheus_range_history,
)
from .gemini_service import (
    PROMPT_VERSION,
    GeminiConfigurationError,
    GeminiGenerationError,
    generate_ai_interaction,
    generate_ai_report,
    test_gemini_connection,
)
from .llm_service import LLMConfigurationError, LLMProviderError, provider_status, test_provider
from .reports_service import build_report_data, export_report_csv, export_report_pdf
from .slurm_service import execute_slurm_cancel_job, execute_slurm_submit_job, node_id_aliases, sanitize_reason
from .ssh_bridge import get_ssh_public_status, validate_safe_identifier
from .gemini_intelligence_router import router as gemini_router
from .incident_service import router as incident_router
from .model_registry_router import router as model_registry_router
from .terminal_service import TERMINAL_PRESET_GROUPS, execute_instance_terminal_command
logger = logging.getLogger(__name__)

_DASH_TO_MODEL_NODE = {
    "head-node": "headnode",
    "compute-01": "compute001",
    "compute-02": "compute002",
    "compute-03": "compute003",
}

# Prometheus Exporter Metrics (real operational metrics only; no fabricated scores)
PROM_NODE_UP = Gauge(
    "hpc_aiops_node_up",
    "Exporter availability per node (1=online, 0=offline)",
    ["node_id", "rack_id"],
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
PROM_CLUSTER_NODES_ONLINE = Gauge(
    "hpc_aiops_cluster_nodes_online",
    "Number of online cluster nodes",
)


class ModeSwitchRequest(BaseModel):
    mode: str
    prometheus_url: Optional[str] = None
    preset_id: Optional[str] = None

class AIReportGenerateRequest(BaseModel):
    report_type: str = Field(default="cluster_summary")
    range_minutes: int = Field(default=60, ge=5, le=10080)

class DrainRequest(BaseModel):
    node_id: str
    reason: str = "Proactive AI early-warning drain"


class ResumeRequest(BaseModel):
    node_id: str


class JobCancelRequest(BaseModel):
    job_id: str
    reason: str = "Cancelled by administrator"


class JobSubmitRequest(BaseModel):
    script: str = Field(min_length=1, max_length=131072)


class FaultInjectRequest(BaseModel):
    node_id: str
    fault_type: str


class FaultClearRequest(BaseModel):
    node_id: Optional[str] = None


class AlertActionRequest(BaseModel):
    action: str  # acknowledge | silence | resolve
    note: Optional[str] = None


class ExperimentCreateRequest(BaseModel):
    name: str
    category: str = "failure_injection"
    node_id: str = "cluster"
    fault_type: str = "unspecified"
    label: str = "positive_fault"
    start_utc: str
    end_utc: Optional[str] = None
    workload_condition: str = "mixed"
    notes: str = ""


class ExperimentUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    node_id: Optional[str] = None
    fault_type: Optional[str] = None
    label: Optional[str] = None
    start_utc: Optional[str] = None
    end_utc: Optional[str] = None
    workload_condition: Optional[str] = None
    notes: Optional[str] = None


class AIChatRequest(BaseModel):
    question: str
    session_id: str = "default"
    range_minutes: int = Field(default=60, ge=5, le=10080)
    provider: Literal["gemini", "openai", "groq"] = "gemini"


class AIConversationCreateRequest(BaseModel):
    provider: Literal["gemini", "openai", "groq"] = "gemini"
    title: str = Field(default="New conversation", min_length=1, max_length=120)


class AIConversationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    provider: Optional[Literal["gemini", "openai", "groq"]] = None


class AIInvestigateRequest(BaseModel):
    episode_id: Optional[int] = None
    node_id: Optional[str] = None
    question: str = "Investigate the detected anomaly or incident and summarize next checks."
    session_id: str = "default"
    provider: Literal["gemini", "openai", "groq"] = "gemini"


class AIAnalyticsQueryRequest(BaseModel):
    question: str
    range_key: str = "24h"
    session_id: str = "default"
    provider: Literal["gemini", "openai", "groq"] = "gemini"


class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


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
    v7_enabled: Optional[bool] = None
    lstm_v8_enabled: Optional[bool] = None
    restricted_terminal_enabled: Optional[bool] = None
    email_alerts_enabled: Optional[bool] = None
    alert_recipient_emails: Optional[str] = None
    alert_policy: Optional[Dict[str, Any]] = None
    node_overrides: Optional[Dict[str, Any]] = None


class PrometheusTestRequest(BaseModel):
    prometheus_url: str


class ModelToggleRequest(BaseModel):
    enabled: bool


class TerminalExecRequest(BaseModel):
    node_id: str = "head-node"
    command: str
    confirmed: bool = False



class PipelineOrchestrator:
    def __init__(self) -> None:
        self.connector = ClusterTelemetryConnector()
        self.features = RollingFeaturePipeline(maxlen=96)
        self.v7 = V7Service(poll_interval_sec=5.0)
        self.lstm_v8 = LSTMV8Service(poll_interval_sec=5.0)
        self.alerts = SmartAlertEngine()

        self.chart_history: Dict[str, Deque[Dict[str, Any]]] = {}
        self.cluster_history: Deque[Dict[str, Any]] = deque(maxlen=72)
        self.latest_snapshot: Dict[str, Any] = {}
        self.clients: Set[WebSocket] = set()

        self.stream_interval_sec: float = 3.0
        self.paused: bool = False
        self.polling_active: bool = False
        self._tick_counter: int = 0
        self._last_online_utc: Dict[str, datetime] = {}
        self._last_online_iso: Dict[str, str] = {}
        self._notified_episode_ids: Set[int] = set()

    def sync_model_flags_from_settings(self) -> Dict[str, bool]:
        try:
            settings_cur = get_app_settings()
            v7_enabled = bool(settings_cur.get("v7_enabled", True))
            lstm_enabled = bool(settings_cur.get("lstm_v8_enabled", True))
        except Exception:
            v7_enabled = self.v7.enabled
            lstm_enabled = self.lstm_v8.enabled
        self.v7.enabled = v7_enabled
        self.lstm_v8.enabled = lstm_enabled
        if not v7_enabled:
            self.v7.connected = False
        if not lstm_enabled:
            self.lstm_v8.connected = False
        return {"v7_enabled": v7_enabled, "lstm_v8_enabled": lstm_enabled}

    def sync_interval_from_settings(self) -> None:
        try:
            s = get_app_settings()
            interval = float(s.get("refresh_interval_sec", 3.0))
            self.stream_interval_sec = max(1.0, min(60.0, interval))
        except Exception:
            logger.exception("Could not synchronize dashboard refresh interval.")

    def get_models_status(self) -> Dict[str, Any]:
        self.sync_model_flags_from_settings()
        v7_status = self.v7.get_status()
        lstm_status = self.lstm_v8.get_status()
        return {
            "legacy_model_engine_removed": True,
            "v7_isolation_forest": v7_status,
            "lstm_v8": {
                "name": "LSTM V8 Temporal Forecaster",
                **lstm_status,
            },
        }

    def step_once(self) -> Dict[str, Any]:
        self._tick_counter += 1
        now_dt = datetime.now(timezone.utc)
        settings_cur = get_app_settings()
        flags = self.sync_model_flags_from_settings()
        v7_enabled = flags["v7_enabled"]
        lstm_enabled = flags["lstm_v8_enabled"]
        v7_status = self.v7.get_status()
        lstm_status = self.lstm_v8.get_status()
        lstm_nodes = (lstm_status.get("state") or {}).get("nodes") or {}

        batch = self.connector.fetch_next_batch()
        ts = batch["timestamp_utc"]
        auto_resolve_stale_offline_prometheus_episodes(ts)
        enriched_map = self.features.ingest_batch(batch["nodes"])

        scored_nodes: List[Dict[str, Any]] = []
        prio_to_num = {
            "OK": 0,
            "MAINTENANCE": 0,
            "P3": 1,
            "P2": 2,
            "P3_WATCH": 1,
            "P1": 3,
        }

        for raw_node in batch["nodes"]:
            nid = raw_node["node_id"]
            ef = enriched_map[nid]
            up_val = int(ef.get("up", 1) if ef.get("up") is not None else 0)
            if up_val == 1:
                self._last_online_utc[nid] = now_dt
                self._last_online_iso[nid] = ts
                age_sec = 0.0
            else:
                prev_dt = self._last_online_utc.get(nid)
                age_sec = (now_dt - prev_dt).total_seconds() if prev_dt else None

            model_nid = _DASH_TO_MODEL_NODE.get(nid, nid)

            # V7 Isolation Forest node payload (cached historical view kept if disabled)
            v7_cached = self.v7.get_node_score(nid)
            if v7_enabled:
                v7_node_data = {
                    "enabled": True,
                    "status": v7_status["status"],
                    "stale": v7_status["stale"],
                    "last_success_utc": v7_status["last_success_utc"],
                    "anomaly_score": None,
                    "threshold": None,
                    "is_anomaly": False,
                    "classification": None,
                    **(v7_cached or {}),
                }
                v7_alert_input = (
                    v7_cached
                    if (v7_cached and v7_status["connected"] and not v7_status["stale"])
                    else None
                )
            else:
                v7_node_data = {
                    **(v7_cached or {}),
                    "enabled": False,
                    "status": "disabled",
                    "stale": bool(v7_cached),
                    "last_success_utc": v7_status["last_success_utc"],
                    "is_anomaly": (v7_cached or {}).get("is_anomaly") if v7_cached else False,
                }
                v7_alert_input = None

            # LSTM V8 node payload (cached historical view kept if disabled)
            lstm_raw_node = lstm_nodes.get(model_nid)
            if isinstance(lstm_raw_node, dict):
                lstm_node_data = {
                    **lstm_raw_node,
                    "enabled": lstm_enabled,
                    "status": lstm_status["status"] if lstm_enabled else "disabled",
                    "stale": True if not lstm_enabled else lstm_status["stale"],
                    "last_success_utc": lstm_status["last_success_utc"],
                }
            else:
                lstm_node_data = None
            lstm_warning = (
                (lstm_raw_node or {}).get("latest_warning")
                if isinstance(lstm_raw_node, dict)
                else None
            )
            lstm_alert_input = (
                lstm_warning
                if (lstm_enabled and lstm_status["connected"] and not lstm_status["stale"])
                else None
            )

            alert_out = self.alerts.evaluate(
                node_sample=ef,
                timestamp_utc=ts,
                data_mode=self.connector.mode,
                v7_result=v7_alert_input,
                lstm_result=lstm_alert_input,
                telemetry_age_seconds=age_sec,
            )

            merged = {
                **ef,
                **alert_out,
                "telemetry_age_seconds": round(age_sec, 1) if age_sec is not None else None,
                "last_telemetry_utc": self._last_online_iso.get(nid),
                "v7_detection": v7_node_data,
                "lstm_v8_status": lstm_node_data,
            }

            scored_nodes.append(merged)

            rack = str(merged.get("rack_id", "rack-1"))
            PROM_NODE_UP.labels(node_id=nid, rack_id=rack).set(up_val)
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
                    "cpu": merged.get("cpu_utilization_percent"),
                    "iowait": merged.get("cpu_iowait_percent"),
                    "memory": merged.get("memory_used_percent"),
                    "swap": merged.get("swap_used_percent"),
                    "load1": merged.get("load1"),
                    "load5": merged.get("load5"),
                    "norm_load": merged.get("normalized_load1"),
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
                    "straggler_pct": round(
                        float(merged.get("mpi_straggler_score", 0.0)) * 100.0,
                        1,
                    ),
                }
            )

        # Persist telemetry every second tick.
        if self._tick_counter % 2 == 1:
            try:
                record_telemetry_batch(
                    ts,
                    self.connector.mode,
                    scored_nodes,
                )
            except Exception:
                logger.exception("Could not persist telemetry batch.")

        # Persist active V7 & LSTM V8 observations (deduped by model, node, timestamp).
        try:
            for sn in scored_nodes:
                nid = sn["node_id"]
                v7_d = sn.get("v7_detection") or {}
                if (
                    v7_d.get("enabled")
                    and not v7_d.get("stale")
                    and v7_d.get("anomaly_score") is not None
                ):
                    record_model_observation(
                        model_name="v7",
                        node_id=nid,
                        observation_utc=str(v7_d.get("timestamp_utc") or ts),
                        score=v7_d.get("anomaly_score"),
                        threshold=v7_d.get("threshold"),
                        flagged=bool(v7_d.get("is_anomaly")),
                        classification=v7_d.get("classification"),
                        details={"model_version": v7_d.get("model_version")},
                    )
                lstm_d = sn.get("lstm_v8_status") or {}
                lw = lstm_d.get("latest_warning") or {}
                if (
                    lstm_d.get("enabled")
                    and not lstm_d.get("stale")
                    and isinstance(lw, dict)
                    and lw.get("warning_score") is not None
                ):
                    record_model_observation(
                        model_name="lstm_v8",
                        node_id=nid,
                        observation_utc=str(lw.get("evaluated_at_timestamp_utc") or ts),
                        score=lw.get("warning_score"),
                        threshold=lw.get("warning_threshold"),
                        flagged=bool(lw.get("is_warning")),
                        classification=lw.get("status"),
                        details=lw.get("components") or {},
                    )
        except Exception:
            logger.exception("Could not persist model score observations.")

        episodes = list_episodes(limit=60)

        active_eps = [
            e for e in episodes
            if e["status"] in ("active", "acknowledged")
        ]

        # Optional email alert notification for newly opened active P1 episodes
        if settings_cur.get("email_alerts_enabled") and settings_cur.get("alert_recipient_emails"):
            recipients = [
                r.strip()
                for r in str(settings_cur.get("alert_recipient_emails", "")).split(",")
                if "@" in r
            ]
            if recipients:
                for ep in active_eps:
                    ep_id = int(ep["id"])
                    if ep["priority"] == "P1" and ep_id not in self._notified_episode_ids:
                        self._notified_episode_ids.add(ep_id)
                        for rec in recipients[:5]:
                            try:
                                send_transactional_email(
                                    to_email=rec,
                                    subject=f"[HPC Predictive Monitoring {ep['priority']}] {ep['title']}",
                                    html_content=(
                                        f"<h3>{ep['title']}</h3>"
                                        f"<p><strong>Node:</strong> {ep['node_id']} | "
                                        f"<strong>Source:</strong> {ep.get('alert_source')}</p>"
                                        f"<p>{ep.get('summary')}</p>"
                                        f"<p><strong>Recommended checks:</strong> {ep.get('recommended_checks')}</p>"
                                    ),
                                    text_content=f"{ep['title']} | Node: {ep['node_id']} | {ep.get('summary')}",
                                )
                            except Exception:
                                logger.warning("Optional incident email dispatch failed for episode %s", ep_id)

        # Aggregate cluster-wide KPIs.
        online_nodes = [
            n for n in scored_nodes
            if n.get("up") == 1
        ]

        cpu_vals = [
            float(n["cpu_utilization_percent"])
            for n in online_nodes
            if n.get("cpu_utilization_percent") is not None
        ]

        mem_vals = [
            float(n["memory_used_percent"])
            for n in online_nodes
            if n.get("memory_used_percent") is not None
        ]

        cluster_cpu = (
            round(statistics.fmean(cpu_vals), 1)
            if cpu_vals else None
        )

        cluster_mem = (
            round(statistics.fmean(mem_vals), 1)
            if mem_vals else None
        )

        PROM_CLUSTER_NODES_ONLINE.set(len(online_nodes))

        nodes_offline = sum(1 for n in scored_nodes if n.get("health_status") == "offline")
        nodes_critical = sum(1 for n in scored_nodes if n.get("health_status") == "critical")
        nodes_warning = sum(1 for n in scored_nodes if n.get("health_status") == "warning")
        nodes_stale = sum(1 for n in scored_nodes if n.get("health_status") == "stale")
        nodes_maintenance = sum(1 for n in scored_nodes if n.get("health_status") == "maintenance")
        nodes_v7_anom = sum(
            1
            for n in scored_nodes
            if (n.get("v7_detection") or {}).get("enabled")
            and not (n.get("v7_detection") or {}).get("stale")
            and (n.get("v7_detection") or {}).get("is_anomaly")
        )
        nodes_lstm_warn = sum(
            1
            for n in scored_nodes
            if (n.get("lstm_v8_status") or {}).get("enabled")
            and not (n.get("lstm_v8_status") or {}).get("stale")
            and ((n.get("lstm_v8_status") or {}).get("latest_warning") or {}).get("is_warning")
        )

        if len(online_nodes) == 0:
            cluster_status = "offline"
            cluster_status_label = "Offline"
        elif nodes_offline > 0 or nodes_critical > 0 or any(e["priority"] == "P1" for e in active_eps):
            cluster_status = "critical"
            cluster_status_label = "Critical"
        elif (
            nodes_warning > 0
            or nodes_stale > 0
            or any(e["priority"] == "P2" for e in active_eps)
            or nodes_v7_anom > 0
            or nodes_lstm_warn > 0
        ):
            cluster_status = "warning"
            cluster_status_label = "Warning"
        else:
            cluster_status = "healthy"
            cluster_status_label = "Healthy"

        short_time = ts[11:16] if len(ts) >= 16 else ts

        self.cluster_history.append(
            {
                "time": short_time,
                "timestamp_utc": ts,
                "cpu_percent": cluster_cpu,
                "memory_percent": cluster_mem,
                "nodes_online": len(online_nodes),
                "active_alerts": len(active_eps),
            }
        )

        # Enrich Slurm jobs with factual node health & active incident correlation.
        node_lookup: Dict[str, Dict[str, Any]] = {}
        for n in scored_nodes:
            for key_src in (n.get("node_id", ""), n.get("hostname", "")):
                for alias in node_id_aliases(str(key_src)):
                    node_lookup.setdefault(alias, n)
        enriched_jobs = []
        resubmittable_job_ids = list_slurm_job_submission_ids()
        active_slurm_jobs = 0
        pending_slurm_jobs = 0
        failed_slurm_jobs = 0

        for job in batch.get("slurm_jobs", []):
            jc = dict(job)
            st_upper = str(jc.get("state", "")).upper()
            if st_upper == "RUNNING":
                active_slurm_jobs += 1
            elif st_upper == "PENDING":
                pending_slurm_jobs += 1
            elif st_upper in ("FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"):
                failed_slurm_jobs += 1

            job_nodes = jc.get("nodes", [])
            affected_nodes = [
                nid
                for nid in job_nodes
                if nid in node_lookup
                and (
                    node_lookup[nid].get("health_status") in ("critical", "warning", "offline", "stale")
                    or node_lookup[nid].get("alert_priority") in ("P1", "P2")
                    or (
                        (node_lookup[nid].get("lstm_v8_status") or {}).get("enabled")
                        and not (node_lookup[nid].get("lstm_v8_status") or {}).get("stale")
                        and ((node_lookup[nid].get("lstm_v8_status") or {}).get("latest_warning") or {}).get("is_warning")
                    )
                    or (
                        (node_lookup[nid].get("v7_detection") or {}).get("enabled")
                        and not (node_lookup[nid].get("v7_detection") or {}).get("stale")
                        and (node_lookup[nid].get("v7_detection") or {}).get("is_anomaly")
                    )
                )
            ]
            has_critical = any(
                node_lookup.get(nid, {}).get("health_status") in ("critical", "offline")
                or node_lookup.get(nid, {}).get("alert_priority") == "P1"
                for nid in job_nodes
            )
            jc["at_risk_nodes"] = affected_nodes
            jc["resubmittable"] = str(jc.get("job_id", "")) in resubmittable_job_ids
            jc["node_impact_status"] = (
                "affected" if has_critical else ("degraded" if affected_nodes else "normal")
            )
            enriched_jobs.append(jc)

        models_status = self.get_models_status()
        prom_connected = bool(batch.get("prometheus_connected", False))
        prometheus_status = (
            "connected"
            if prom_connected
            else ("simulated" if batch.get("is_simulated") else "offline")
        )

        snapshot = {
            "timestamp_utc": ts,
            "mode": self.connector.mode,
            "v7": v7_status,
            "lstm_v8": lstm_status,
            "mode_label": batch.get("mode_label", ""),
            "is_synthetic": bool(batch.get("is_synthetic", False)),
            "is_simulated": bool(batch.get("is_simulated", False)),
            "prometheus_connected": prom_connected,
            "slurm_connected": bool(batch.get("slurm_connected", False)),
            "slurm_source": batch.get("slurm_source", "unavailable"),
            "slurm_error": batch.get("slurm_error"),
            "slurm_nodes": batch.get("slurm_nodes", []),
            "preset_id": self.connector.replay_preset_id,
            "preset_description": batch.get("preset_description"),
            "replay_progress": batch.get("replay_progress"),
            "source_warning": batch.get("source_warning"),
            "paused": self.paused,
            "refresh_interval_sec": self.stream_interval_sec,
            "grafana_url": settings_cur.get(
                "grafana_url",
                "http://localhost:3000",
            ),
            "prometheus_url": self.connector.prometheus_url,
            "model_status": models_status,
            "ssh_status": get_ssh_public_status(),
            "active_fault_injections": self.connector.injected_faults,
            "kpis": {
                "nodes_total": len(scored_nodes),
                "nodes_online": len(online_nodes),
                "nodes_offline": nodes_offline,
                "nodes_critical": nodes_critical,
                "nodes_warning": nodes_warning,
                "nodes_stale": nodes_stale,
                "nodes_maintenance": nodes_maintenance,
                "nodes_drained": sum(
                    1 for n in scored_nodes
                    if "DRAIN" in str(n.get("slurm_state", ""))
                ),
                "nodes_with_v7_anomaly": nodes_v7_anom,
                "nodes_with_lstm_warning": nodes_lstm_warn,
                "active_slurm_jobs": active_slurm_jobs,
                "pending_slurm_jobs": pending_slurm_jobs,
                "failed_slurm_jobs": failed_slurm_jobs,
                "cluster_status": cluster_status,
                "cluster_status_label": cluster_status_label,
                "cluster_cpu_percent": cluster_cpu,
                "cluster_memory_percent": cluster_mem,
                "active_episodes_total": len(active_eps),
                "p1_count": sum(1 for e in active_eps if e["priority"] == "P1"),
                "p2_count": sum(1 for e in active_eps if e["priority"] == "P2"),
                "p3_count": sum(1 for e in active_eps if e["priority"] == "P3"),
                "prometheus_status": prometheus_status,
                "v7_api_status": models_status["v7_isolation_forest"]["status"],
                "lstm_v8_api_status": models_status["lstm_v8"]["status"],
                "gemini_status": "configured" if GEMINI_API_KEY else "not_configured",
                "latest_telemetry_utc": ts,
                "peak_straggler_pct": round(
                    max(
                        (
                            float(n.get("mpi_straggler_score", 0.0))
                            for n in scored_nodes
                        ),
                        default=0.0,
                    ) * 100.0,
                    1,
                ),
                **get_roi_totals(),
            },
            "cluster_history": list(self.cluster_history),
            "nodes": scored_nodes,
            "history": {
                nid: list(series)
                for nid, series in self.chart_history.items()
            },
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
    try:
        retention_days = get_app_settings().get("model_observation_retention_days", 30)
        cleanup_model_observations(int(retention_days))
    except Exception:
        logger.exception("Could not clean expired model observations.")
    orchestrator.sync_interval_from_settings()

    add_system_log(
        timestamp_utc=datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        node_id="head-node",
        source="aiops-daemon",
        severity="INFO",
        event_type="startup",
        message=(
            "HPC Predictive Monitoring Dashboard v2.0 online. "
            "Real-time telemetry & ML pipeline initialized."
        ),
    )

    # Synchronize model integration flags before initial poll.
    orchestrator.sync_model_flags_from_settings()
    if orchestrator.v7.enabled:
        await orchestrator.v7.refresh_once()
    if orchestrator.lstm_v8.enabled:
        await orchestrator.lstm_v8.refresh_once()

    # Warm up the existing dashboard pipeline.
    warmup_ticks = (
        2
        if orchestrator.connector.mode == "live_prometheus"
        else 14
    )

    for _ in range(warmup_ticks):
        orchestrator.step_once()

    # Start independent model polling only for enabled integrations.
    orchestrator.polling_active = True
    if orchestrator.v7.enabled:
        await orchestrator.v7.start()
    if orchestrator.lstm_v8.enabled:
        await orchestrator.lstm_v8.start()

    stop_event = asyncio.Event()

    async def _loop() -> None:
        while not stop_event.is_set():
            try:
                if not orchestrator.paused:
                    snap = orchestrator.step_once()
                    await orchestrator.broadcast(snap)

            except Exception:
                logger.exception(
                    "Dashboard pipeline iteration failed."
                )

            await asyncio.sleep(
                orchestrator.stream_interval_sec
            )

    task = asyncio.create_task(_loop())

    try:
        yield

    finally:
        stop_event.set()
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        orchestrator.polling_active = False
        await orchestrator.v7.stop()
        await orchestrator.lstm_v8.stop()

app = FastAPI(
    title=APP_METADATA["name"],
    version=APP_METADATA["version"],
    lifespan=lifespan,
)
app.state.orchestrator = orchestrator

# Register application routers
app.include_router(auth_router)
app.include_router(gemini_router)
app.include_router(incident_router)
app.include_router(model_registry_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------------------------------------------------------
# Public Backend Health Check
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "HPC Predictive Monitoring Dashboard API",
    }


# ---------------------------------------------------------------------------
# Session-based authorization
# ---------------------------------------------------------------------------

# All authenticated users can access dashboard information.
require_authenticated_user = get_current_user

# Only administrators can perform administrative operations.
require_admin_role = require_roles("super_admin", "admin")

# All authenticated users can access logs and diagnostics.
require_diagnostic_access = get_current_user
# ---------------------------------------------------------------------------
# Core Pipeline & State Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/state",
    dependencies=[Depends(require_authenticated_user)],
)
def get_current_state() -> Dict[str, Any]:
    if not orchestrator.latest_snapshot:
        return orchestrator.step_once()
    return orchestrator.latest_snapshot


@app.post(
    "/api/state/refresh",
    dependencies=[Depends(require_admin_role)],
)
async def force_state_refresh() -> Dict[str, Any]:
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return snap


@app.get(
    "/api/models/status",
    dependencies=[Depends(require_authenticated_user)],
)
def get_models_status() -> Dict[str, Any]:
    return orchestrator.get_models_status()


@app.get(
    "/api/models/v7/scores",
    dependencies=[Depends(require_authenticated_user)],
)
def get_v7_scores() -> Dict[str, Any]:
    orchestrator.sync_model_flags_from_settings()
    return {
        "status": orchestrator.v7.get_status(),
        "history": orchestrator.v7.get_history(),
    }


@app.post(
    "/api/models/v7/toggle",
    dependencies=[Depends(require_admin_role)],
)
async def toggle_v7_integration(req: ModelToggleRequest) -> Dict[str, Any]:
    saved = update_app_settings({"v7_enabled": bool(req.enabled)})
    status = await orchestrator.v7.set_enabled(
        bool(saved["v7_enabled"]),
        start_poller=orchestrator.polling_active,
    )
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return {"saved": True, "v7_enabled": bool(saved["v7_enabled"]), "v7": status}


@app.post(
    "/api/models/v7/refresh",
    dependencies=[Depends(require_admin_role)],
)
async def refresh_v7_scores() -> Dict[str, Any]:
    orchestrator.sync_model_flags_from_settings()
    await orchestrator.v7.refresh_once()
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return orchestrator.v7.get_status()


@app.get(
    "/api/models/lstm-v8/state",
    dependencies=[Depends(require_authenticated_user)],
)
def get_lstm_v8_details() -> Dict[str, Any]:
    orchestrator.sync_model_flags_from_settings()
    return {
        "status": orchestrator.lstm_v8.get_status(),
        "history": orchestrator.lstm_v8.get_history(),
    }


@app.post(
    "/api/models/lstm-v8/toggle",
    dependencies=[Depends(require_admin_role)],
)
async def toggle_lstm_v8_integration(req: ModelToggleRequest) -> Dict[str, Any]:
    saved = update_app_settings({"lstm_v8_enabled": bool(req.enabled)})
    status = await orchestrator.lstm_v8.set_enabled(
        bool(saved["lstm_v8_enabled"]),
        start_poller=orchestrator.polling_active,
    )
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return {"saved": True, "lstm_v8_enabled": bool(saved["lstm_v8_enabled"]), "lstm_v8": status}


@app.post(
    "/api/models/lstm-v8/refresh",
    dependencies=[Depends(require_admin_role)],
)
async def refresh_lstm_v8_state() -> Dict[str, Any]:
    orchestrator.sync_model_flags_from_settings()
    await orchestrator.lstm_v8.refresh_once()
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return orchestrator.lstm_v8.get_status()


@app.post(
    "/api/mode",
    dependencies=[Depends(require_admin_role)],
)
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


@app.post(
    "/api/stream/pause",
    dependencies=[Depends(require_admin_role)],
)
async def toggle_stream_pause() -> Dict[str, Any]:
    orchestrator.paused = not orchestrator.paused
    if orchestrator.latest_snapshot:
        orchestrator.latest_snapshot["paused"] = orchestrator.paused
        await orchestrator.broadcast(orchestrator.latest_snapshot)
    return {"paused": orchestrator.paused}


# ---------------------------------------------------------------------------
# Live Monitoring & Historical Prometheus Range Queries (5m..24h)
# ---------------------------------------------------------------------------

@app.get(
    "/api/monitoring/history",
    dependencies=[Depends(require_authenticated_user)],
)
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
                dws = [float(x["disk_write_mb"]) for x in grp if x["disk_write_mb"] is not None]
                nrxs = [float(x["net_rx_mb"]) for x in grp if x["net_rx_mb"] is not None]
                mapped.append(
                    {
                        "timestamp_utc": ts_k,
                        "time": ts_k[11:19] if len(ts_k) >= 19 else ts_k,
                        "cpu": round(statistics.fmean(cpus), 2) if cpus else None,
                        "memory": round(statistics.fmean(mems), 2) if mems else None,
                        "disk_write_mb": round(sum(dws), 2) if dws else None,
                        "net_rx_mb": round(sum(nrxs), 2) if nrxs else None,
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
    orchestrator.connector.invalidate_slurm_cache()
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


async def _submit_and_record_job(script: str, parent_job_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        outcome = execute_slurm_submit_job(script)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    save_slurm_job_submission(outcome["job_id"], script, parent_job_id)
    record_slurm_action(
        node_id=f"job-{outcome['job_id']}",
        action="SUBMIT_JOB" if parent_job_id is None else "RESUBMIT_JOB",
        reason=f"Submitted from dashboard" + (f" based on job {parent_job_id}" if parent_job_id else ""),
        jobs_protected=0,
        core_hours_saved=0.0,
        kwh_saved=0.0,
        executed_mode=outcome["source"],
    )
    orchestrator.connector.invalidate_slurm_cache()
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return {**outcome, "parent_job_id": parent_job_id}


@app.post("/api/slurm/submit", dependencies=[Depends(require_admin_role)])
async def slurm_submit_job_endpoint(req: JobSubmitRequest) -> Dict[str, Any]:
    """Submit a dashboard-provided sbatch script; future resubmissions use this saved copy."""
    return await _submit_and_record_job(req.script)


@app.post("/api/slurm/jobs/{job_id}/resubmit", dependencies=[Depends(require_admin_role)])
async def slurm_resubmit_job_endpoint(job_id: str) -> Dict[str, Any]:
    if not re.fullmatch(r"[0-9]{1,24}(?:_[0-9]{1,10})?", job_id or ""):
        raise HTTPException(status_code=400, detail="Invalid Slurm Job ID format")
    saved = get_slurm_job_submission(job_id)
    if not saved:
        raise HTTPException(
            status_code=404,
            detail="This job has no saved submission script. Only jobs submitted through the dashboard can be resubmitted.",
        )
    return await _submit_and_record_job(saved["script"], parent_job_id=job_id)


@app.get(
    "/api/slurm/audit",
    dependencies=[Depends(require_authenticated_user)],
)
def get_slurm_audit_history() -> Dict[str, Any]:
    return {"audit": list_slurm_audit(limit=80)}


# ---------------------------------------------------------------------------
# Node Logs & Secure Diagnostic Bundles
# ---------------------------------------------------------------------------

def _find_node_in_snapshot(snap: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    aliases = set(node_id_aliases(node_id))
    for n in snap.get("nodes", []):
        cand = str(n.get("node_id", ""))
        if cand == node_id or aliases.intersection(node_id_aliases(cand)):
            return n
    return None


def _resolve_node_target(node_id: str) -> Dict[str, Any]:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    found = _find_node_in_snapshot(snap, node_id)
    if found:
        return found
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
    node = _find_node_in_snapshot(snap, node_id)
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
    zip_bytes = build_node_diagnostic_bundle_zip(node, orchestrator.get_models_status())
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

@app.get(
    "/api/terminal/presets",
    dependencies=[Depends(require_authenticated_user)],
)
def get_terminal_presets() -> Dict[str, Any]:
    settings_cur = get_app_settings()
    return {
        "enabled": bool(settings_cur.get("restricted_terminal_enabled", False)),
        "preset_groups": TERMINAL_PRESET_GROUPS,
        "ssh_status": get_ssh_public_status(),
    }


@app.get(
    "/api/terminal/audit",
    dependencies=[Depends(require_admin_role)],
)
def get_terminal_audit_endpoint(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    return {"entries": list_terminal_audit(limit=limit)}


@app.post("/api/terminal/exec")
def execute_terminal_command_endpoint(
    req: TerminalExecRequest,
    current_user: Dict[str, Any] = Depends(require_admin_role),
) -> Dict[str, Any]:
    settings_cur = get_app_settings()
    if not settings_cur.get("restricted_terminal_enabled", False):
        record_terminal_audit(
            user_email=current_user.get("email", ""),
            node_id=req.node_id,
            command=req.command,
            allowed=False,
            blocked_reason="Operations terminal is disabled in System Settings.",
        )
        raise HTTPException(
            status_code=403,
            detail="Operations Terminal is currently disabled in System Settings.",
        )

    if not validate_safe_identifier(req.node_id):
        raise HTTPException(status_code=400, detail="Invalid node identifier")
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    nodes = snap.get("nodes", [])
    target_node = _find_node_in_snapshot(snap, req.node_id)
    if not target_node:
        raise HTTPException(status_code=404, detail=f"Instance '{req.node_id}' not found in cluster")
    try:
        res = execute_instance_terminal_command(
            node=target_node,
            all_nodes=nodes,
            slurm_jobs=snap.get("slurm_jobs", []),
            pipeline_mode=orchestrator.connector.mode,
            raw_command=req.command,
            confirmed=req.confirmed,
        )
        record_terminal_audit(
            user_email=current_user.get("email", ""),
            node_id=req.node_id,
            command=req.command,
            allowed=True,
            exit_code=int(res.get("exit_code", 0)),
            output_preview=str(res.get("output", res.get("stdout", ""))),
        )
        return res
    except ValueError as exc:
        record_terminal_audit(
            user_email=current_user.get("email", ""),
            node_id=req.node_id,
            command=req.command,
            allowed=False,
            blocked_reason=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Performance Analytics & Exportable CSV / PDF Reports
# ---------------------------------------------------------------------------

@app.get(
    "/api/analytics/summary",
    dependencies=[Depends(require_authenticated_user)],
)
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
                "health_status": n.get("health_status", "healthy"),
                "health_classification": n.get("health_classification", "Healthy"),
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

@app.post(
    "/api/reports/ai/generate",
    dependencies=[Depends(require_admin_role)],
)
def generate_ai_report_endpoint(
    req: AIReportGenerateRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:

    allowed_types = {
        "cluster_summary",
        "ai_predictions",
        "alerts_incidents",
        "slurm_workload",
        "performance_history",
        "experiment_evaluation",
    }

    if req.report_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Unsupported report type.",
        )

    snap = orchestrator.latest_snapshot or orchestrator.step_once()

    report_data = build_report_data(
        report_type=req.report_type,
        snapshot=snap,
        range_minutes=req.range_minutes,
    )

    evidence = {
        "report_data": report_data,
        "cluster_context": {
            "mode": snap.get("mode", ""),
            "mode_label": snap.get("mode_label", ""),
            "timestamp_utc": snap.get("timestamp_utc", ""),
            "nodes": snap.get("nodes", []),
            "slurm_jobs": snap.get("slurm_jobs", []),
        },
    }

    node_ids = [
        str(node.get("node_id"))
        for node in snap.get("nodes", [])
        if node.get("node_id")
    ]

    try:
        report_id = save_ai_report(
            report_type=req.report_type,
            title=report_data["title"],
            range_minutes=req.range_minutes,
            data_mode=str(
                snap.get("mode_label")
                or snap.get("mode")
                or "unknown"
            ),
            provider="Google Gemini",
            model=GEMINI_MODEL,
            prompt_version=PROMPT_VERSION,
            node_ids=node_ids,
            evidence=evidence,
            report_text="",
            status="pending",
        )
    except Exception as exc:
        logger.exception("Could not save pending AI report.")
        raise HTTPException(
            status_code=500,
            detail="Could not create the AI report.",
        ) from exc

    background_tasks.add_task(
        _generate_ai_report_background,
        report_id,
        evidence,
    )

    return {
        "report_id": report_id,
        "status": "pending",
        "title": report_data["title"],
        "message": "AI report generation has been queued.",
    }


@app.get(
    "/api/reports/ai/archive",
    dependencies=[Depends(require_authenticated_user)],
)
def get_ai_report_archive(
    limit: int = Query(default=50, ge=1, le=200),
) -> Dict[str, Any]:

    return {
        "reports": list_ai_reports(limit=limit),
    }


@app.get(
    "/api/reports/ai/status/{report_id}",
    dependencies=[Depends(require_authenticated_user)],
)
def get_ai_report_status(
    report_id: int,
) -> Dict[str, Any]:

    report = get_ai_report(report_id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="AI report not found.",
        )

    return {
        "report_id": report_id,
        "status": report["status"],
    }


@app.get(
    "/api/reports/ai/{report_id}",
    dependencies=[Depends(require_authenticated_user)],
)
def get_ai_report_details(
    report_id: int,
) -> Dict[str, Any]:

    report = get_ai_report(report_id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="AI report not found.",
        )

    return report


@app.get(
    "/api/reports/preview",
    dependencies=[Depends(require_authenticated_user)],
)
def preview_report_endpoint(
    report_type: str = Query("cluster_summary"),
    range_minutes: int = Query(60, ge=5, le=10080),
) -> Dict[str, Any]:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    return build_report_data(report_type=report_type, snapshot=snap, range_minutes=range_minutes)


@app.get(
    "/api/reports/export",
    dependencies=[Depends(require_authenticated_user)],
)
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

def _generate_ai_report_background(
    report_id: int,
    evidence: Dict[str, Any],
) -> None:
    """
    Generate an AI report outside the original HTTP request.
    """

    try:
        update_ai_report(report_id, "generating")

        result = generate_ai_report(evidence)

        updated = update_ai_report(
            report_id,
            "completed",
            result["report_text"],
        )

        if not updated:
            logger.error(
                "AI report %s disappeared before completion.",
                report_id,
            )

    except Exception:
        logger.exception(
            "Background generation failed for AI report %s.",
            report_id,
        )

        update_ai_report(report_id, "failed")


# ---------------------------------------------------------------------------
# Fault Injection Demo Lab & Alert Triage
# ---------------------------------------------------------------------------

@app.post(
    "/api/fault-inject",
    dependencies=[Depends(require_admin_role)],
)
async def inject_demo_fault(req: FaultInjectRequest) -> Dict[str, Any]:
    res = orchestrator.connector.inject_fault(req.node_id, req.fault_type)
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return res


@app.post(
    "/api/fault-clear",
    dependencies=[Depends(require_admin_role)],
)
async def clear_demo_fault(req: FaultClearRequest) -> Dict[str, Any]:
    orchestrator.connector.clear_faults(req.node_id)
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return {"cleared": True}


@app.get(
    "/api/alerts",
    dependencies=[Depends(require_authenticated_user)],
)
def list_filtered_alerts(
    status: Optional[str] = Query(None),
    node_id: Optional[str] = Query(None),
    alert_source: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    items = list_episodes(limit=limit)
    if status:
        items = [e for e in items if e.get("status") == status]
    if node_id:
        items = [e for e in items if e.get("node_id") == node_id]
    if alert_source:
        items = [e for e in items if e.get("alert_source") == alert_source]
    if priority:
        items = [e for e in items if e.get("priority") == priority]
    return {"episodes": items, "total": len(items)}


@app.post("/api/alerts/{episode_id}/action")
async def alert_triage_action(
    episode_id: int,
    req: AlertActionRequest,
    current_user: Dict[str, Any] = Depends(require_admin_role),
) -> Dict[str, Any]:
    if req.action not in ("acknowledge", "silence", "resolve"):
        raise HTTPException(status_code=400, detail="Unsupported alert action")
    silenced_until = None
    if req.action == "silence":
        silenced_until = (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = update_episode_status(
        episode_id=episode_id,
        action=req.action,
        silenced_until_utc=silenced_until,
        acknowledged_by=current_user.get("email"),
        resolution_note=req.note,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Episode not found")
    if orchestrator.latest_snapshot:
        orchestrator.latest_snapshot["alert_episodes"] = list_episodes(limit=60)
        await orchestrator.broadcast(orchestrator.latest_snapshot)
    return updated


# ---------------------------------------------------------------------------
# Settings & Service Health Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/settings",
    dependencies=[Depends(require_authenticated_user)],
)
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
            "models": orchestrator.get_models_status(),
            "gemini": {
                "configured": bool(GEMINI_API_KEY),
                "model": GEMINI_MODEL,
            },
            "llm_providers": provider_status(),
        },
    }


@app.put("/api/settings", dependencies=[Depends(require_admin_role)])
async def update_settings_endpoint(req: SettingsUpdateRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    saved = update_app_settings(updates)
    orchestrator.sync_interval_from_settings()
    orchestrator.connector.sync_from_settings()
    if "v7_enabled" in updates:
        await orchestrator.v7.set_enabled(
            bool(saved["v7_enabled"]),
            start_poller=orchestrator.polling_active,
        )
    if "lstm_v8_enabled" in updates:
        await orchestrator.lstm_v8.set_enabled(
            bool(saved["lstm_v8_enabled"]),
            start_poller=orchestrator.polling_active,
        )
    snap = orchestrator.step_once()
    await orchestrator.broadcast(snap)
    return {"saved": True, "settings": saved}


@app.post(
    "/api/settings/test-prometheus",
    dependencies=[Depends(require_admin_role)],
)
def test_prometheus_connection(req: PrometheusTestRequest) -> Dict[str, Any]:
    return check_prometheus_health(req.prometheus_url, timeout=2.5)



@app.get(
    "/api/monitoring/export",
    dependencies=[Depends(require_authenticated_user)],
)
def export_telemetry_csv(
    range_key: str = Query("1h"),
    node_id: Optional[str] = Query(None),
) -> Response:
    minutes, _ = RANGE_CONFIG.get(range_key, (60, 30))
    rows = query_telemetry_history(range_minutes=minutes, node_id=node_id, limit=2500)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp_utc", "data_mode", "node_id", "up",
        "cpu_percent", "iowait_percent", "memory_percent", "swap_percent",
        "load1", "normalized_load1", "scratch_percent",
        "disk_read_mb", "disk_write_mb", "disk_io_percent",
        "net_rx_mb", "net_tx_mb", "net_err_s",
    ])
    for r in rows:
        writer.writerow([
            r.get("timestamp_utc", ""),
            r.get("data_mode", ""),
            r.get("node_id", ""),
            r.get("up", ""),
            r.get("cpu_percent", ""),
            r.get("iowait_percent", ""),
            r.get("memory_percent", ""),
            r.get("swap_percent", ""),
            r.get("load1", ""),
            r.get("normalized_load1", ""),
            r.get("scratch_percent", ""),
            r.get("disk_read_mb", ""),
            r.get("disk_write_mb", ""),
            r.get("disk_io_percent", ""),
            r.get("net_rx_mb", ""),
            r.get("net_tx_mb", ""),
            r.get("net_err_s", ""),
        ])
    slug = f"{node_id or 'cluster'}_{range_key}"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="telemetry_{slug}.csv"'},
    )


@app.get(
    "/api/models/evaluation",
    dependencies=[Depends(require_authenticated_user)],
)
def get_models_evaluation_comparison() -> Dict[str, Any]:
    return compute_model_comparison_summary()


@app.get(
    "/api/experiments",
    dependencies=[Depends(require_authenticated_user)],
)
def list_experiments_endpoint(category: Optional[str] = Query(None)) -> Dict[str, Any]:
    return {
        "experiments": list_experiments(category=category, limit=200),
        "evaluation": compute_model_comparison_summary(),
    }


@app.post("/api/experiments")
def create_experiment_endpoint(
    req: ExperimentCreateRequest,
    current_user: Dict[str, Any] = Depends(require_admin_role),
) -> Dict[str, Any]:
    if req.label not in ("positive_fault", "benign_workload", "normal"):
        raise HTTPException(status_code=400, detail="Invalid experiment label")
    exp_id = create_experiment(
        name=req.name,
        category=req.category,
        node_id=req.node_id,
        fault_type=req.fault_type,
        label=req.label,
        start_utc=req.start_utc,
        end_utc=req.end_utc,
        workload_condition=req.workload_condition,
        notes=req.notes,
        created_by=current_user.get("email", "admin"),
    )
    return {
        "created": True,
        "id": exp_id,
        "evaluation": compute_model_comparison_summary(),
    }


@app.put(
    "/api/experiments/{experiment_id}",
    dependencies=[Depends(require_admin_role)],
)
def update_experiment_endpoint(
    experiment_id: int,
    req: ExperimentUpdateRequest,
) -> Dict[str, Any]:
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = update_experiment(experiment_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"saved": True, "experiment": updated, "evaluation": compute_model_comparison_summary()}


@app.delete(
    "/api/experiments/{experiment_id}",
    dependencies=[Depends(require_admin_role)],
)
def delete_experiment_endpoint(experiment_id: int) -> Dict[str, Any]:
    ok = delete_experiment(experiment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"deleted": True, "evaluation": compute_model_comparison_summary()}


# ---------------------------------------------------------------------------
# Phase 4: AI Intelligence Centre (Gemini LLM)
# ---------------------------------------------------------------------------

def _build_gemini_live_evidence(
    snap: Dict[str, Any],
    range_minutes: int = 60,
    target_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    nodes = snap.get("nodes", [])
    if target_node_id:
        nodes = [n for n in nodes if n.get("node_id") == target_node_id] or nodes

    compact_nodes = [
        {
            "node_id": n.get("node_id"),
            "display_name": n.get("display_name"),
            "ip": n.get("ip"),
            "role": n.get("role"),
            "up": n.get("up"),
            "health_status": n.get("health_status"),
            "slurm_state": n.get("slurm_state"),
            "telemetry_age_seconds": n.get("telemetry_age_seconds"),
            "cpu_utilization_percent": n.get("cpu_utilization_percent"),
            "cpu_iowait_percent": n.get("cpu_iowait_percent"),
            "memory_used_percent": n.get("memory_used_percent"),
            "swap_used_percent": n.get("swap_used_percent"),
            "load1": n.get("load1"),
            "normalized_load1": n.get("normalized_load1"),
            "scratch_used_percent": n.get("scratch_used_percent"),
            "disk_io_utilization_percent": n.get("disk_io_utilization_percent"),
            "network_errors_per_second": n.get("network_errors_per_second"),
            "v7_detection": n.get("v7_detection"),
            "lstm_v8_status": n.get("lstm_v8_status"),
        }
        for n in nodes
    ]

    return {
        "timestamp_utc": snap.get("timestamp_utc"),
        "mode": snap.get("mode"),
        "kpis": snap.get("kpis"),
        "nodes": compact_nodes,
        "slurm_jobs": (snap.get("slurm_jobs") or [])[:25],
        "active_incidents": list_episodes(limit=25),
        "recent_v7_observations": list_model_observations(
            model_name="v7",
            node_id=target_node_id,
            limit=30,
        ),
        "recent_lstm_observations": list_model_observations(
            model_name="lstm_v8",
            node_id=target_node_id,
            limit=30,
        ),
        "telemetry_window_samples": query_telemetry_history(
            range_minutes=range_minutes,
            node_id=target_node_id,
            limit=120,
        )[:60],
    }


def _summarize_ai_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Return compact provenance references for an assistant answer, not an interpretation."""
    return {
        "timestamp_utc": evidence.get("timestamp_utc"),
        "data_mode": evidence.get("mode"),
        "nodes": [n.get("node_id") for n in evidence.get("nodes", []) if n.get("node_id")],
        "incident_ids": [e.get("id") for e in evidence.get("active_incidents", []) if e.get("id") is not None],
        "slurm_job_ids": [j.get("job_id") for j in evidence.get("slurm_jobs", []) if j.get("job_id") is not None],
        "v7_observation_count": len(evidence.get("recent_v7_observations", [])),
        "lstm_v8_observation_count": len(evidence.get("recent_lstm_observations", [])),
        "telemetry_sample_count": len(evidence.get("telemetry_window_samples", [])),
    }


@app.get("/api/ai/history")
def get_ai_chat_history(
    session_id: Optional[str] = Query("default"),
    limit: int = Query(80, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    email = current_user.get("email", "")
    conversation = get_ai_conversation(session_id, email) if session_id else None
    return {
        "session_id": session_id,
        "conversation": conversation,
        "messages": list_gemini_messages(session_id=session_id, limit=limit, user_email=email),
    }


@app.get("/api/ai/conversations")
def get_ai_conversations_endpoint(
    search: Optional[str] = Query(None, max_length=100),
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return {"conversations": list_ai_conversations(current_user.get("email", ""), search)}


@app.post("/api/ai/conversations", status_code=201)
def create_ai_conversation_endpoint(
    req: AIConversationCreateRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return create_ai_conversation(current_user.get("email", ""), req.provider, req.title)


@app.patch("/api/ai/conversations/{session_id}")
def update_ai_conversation_endpoint(
    session_id: str,
    req: AIConversationUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    email = current_user.get("email", "")
    if req.title is None and req.provider is None:
        raise HTTPException(status_code=422, detail="Provide a conversation title or provider to update.")
    if req.title is not None and not rename_ai_conversation(session_id, email, req.title):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if req.provider is not None and not set_ai_conversation_provider(session_id, email, req.provider):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"updated": True, "conversation": get_ai_conversation(session_id, email)}


@app.delete("/api/ai/conversations/{session_id}/messages")
def clear_ai_conversation_endpoint(
    session_id: str,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    if not clear_ai_conversation(session_id, current_user.get("email", "")):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"cleared": True}


@app.delete("/api/ai/conversations/{session_id}")
def delete_ai_conversation_endpoint(
    session_id: str,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    if not delete_ai_conversation(session_id, current_user.get("email", "")):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": True}


@app.post("/api/ai/chat")
def ai_chat_endpoint(
    req: AIChatRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    evidence = _build_gemini_live_evidence(snap, range_minutes=req.range_minutes)
    user_email = current_user.get("email", "")
    ensure_ai_conversation(req.session_id, user_email, req.provider)
    set_ai_conversation_provider(req.session_id, user_email, req.provider)
    history = list_gemini_messages(session_id=req.session_id, limit=20, user_email=user_email)
    try:
        res = generate_ai_interaction(
            mode="chat",
            question=req.question,
            evidence=evidence,
            conversation_history=history,
            provider=req.provider,
        )
    except GeminiConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (ValueError, GeminiGenerationError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 502), detail=str(exc))

    append_gemini_message(req.session_id, user_email, "user", "chat", req.question, {"range_minutes": req.range_minutes})
    evidence_summary = _summarize_ai_evidence(evidence)
    append_gemini_message(req.session_id, user_email, "assistant", "chat", res["answer"], {"model": res["model"], "provider": res["provider_key"], "evidence_summary": evidence_summary})
    return {
        **res,
        "session_id": req.session_id,
        "evidence_summary": evidence_summary,
    }


@app.post("/api/ai/investigate-incident")
def ai_investigate_incident_endpoint(
    req: AIInvestigateRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    episodes = list_episodes(limit=100)
    target_episode = next((e for e in episodes if e["id"] == req.episode_id), None) if req.episode_id else None
    if req.episode_id and not target_episode:
        raise HTTPException(status_code=404, detail="Target incident episode not found")

    target_node = req.node_id or (target_episode.get("node_id") if target_episode else None)
    evidence = _build_gemini_live_evidence(snap, range_minutes=120, target_node_id=target_node)
    evidence["target_episode"] = target_episode
    user_email = current_user.get("email", "")
    ensure_ai_conversation(req.session_id, user_email, req.provider)
    history = list_gemini_messages(session_id=req.session_id, limit=20, user_email=user_email)

    if target_node:
        try:
            logs_res = retrieve_node_logs(node_id=target_node, category="system", lines=40)
            evidence["recent_system_logs"] = logs_res.get("entries", [])[:25]
        except Exception:
            evidence["recent_system_logs"] = []

    try:
        res = generate_ai_interaction(
            mode="incident_investigation",
            question=req.question,
            evidence=evidence,
            conversation_history=history,
            provider=req.provider,
        )
    except GeminiConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (ValueError, GeminiGenerationError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 502), detail=str(exc))

    append_gemini_message(
        req.session_id,
        user_email,
        "user",
        "incident_investigation",
        f"[Episode #{req.episode_id or '-'} / Node {target_node or 'cluster'}] {req.question}",
        {"episode_id": req.episode_id, "node_id": target_node, "provider": req.provider},
    )
    append_gemini_message(
        req.session_id,
        user_email,
        "assistant",
        "incident_investigation",
        res["answer"],
        {"episode_id": req.episode_id, "node_id": target_node, "model": res["model"], "provider": res["provider_key"], "evidence_summary": _summarize_ai_evidence(evidence)},
    )
    return {
        **res,
        "target_episode": target_episode,
        "target_node": target_node,
    }


@app.post("/api/ai/query-analytics")
def ai_analytics_query_endpoint(
    req: AIAnalyticsQueryRequest,
    current_user: Dict[str, Any] = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    range_key = req.range_key if req.range_key in RANGE_CONFIG else "24h"
    minutes, _ = RANGE_CONFIG[range_key]
    snap = orchestrator.latest_snapshot or orchestrator.step_once()
    evidence = _build_gemini_live_evidence(snap, range_minutes=minutes)
    evidence["analytics_summary"] = get_performance_analytics_summary(range_key=range_key)
    evidence["model_comparison"] = compute_model_comparison_summary()
    user_email = current_user.get("email", "")
    ensure_ai_conversation(req.session_id, user_email, req.provider)
    history = list_gemini_messages(session_id=req.session_id, limit=20, user_email=user_email)

    try:
        res = generate_ai_interaction(
            mode="cluster_analytics",
            question=req.question,
            evidence=evidence,
            conversation_history=history,
            provider=req.provider,
        )
    except GeminiConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (ValueError, GeminiGenerationError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 502), detail=str(exc))

    append_gemini_message(req.session_id, user_email, "user", "cluster_analytics", f"[{range_key}] {req.question}", {"range_key": range_key})
    evidence_summary = _summarize_ai_evidence(evidence)
    append_gemini_message(req.session_id, user_email, "assistant", "cluster_analytics", res["answer"], {"range_key": range_key, "model": res["model"], "provider": res["provider_key"], "evidence_summary": evidence_summary})
    return {
        **res,
        "range_key": range_key,
        "evidence_summary": evidence_summary,
    }


@app.post(
    "/api/ai/test",
    dependencies=[Depends(require_admin_role)],
)
def test_gemini_endpoint() -> Dict[str, Any]:
    return test_gemini_connection()


@app.get("/api/ai/providers", dependencies=[Depends(require_authenticated_user)])
def get_ai_provider_status() -> Dict[str, Any]:
    return {"providers": provider_status()}


@app.post("/api/ai/providers/{provider}/test", dependencies=[Depends(require_admin_role)])
def test_ai_provider(provider: str) -> Dict[str, Any]:
    if provider not in {"gemini", "openai", "groq"}:
        raise HTTPException(status_code=404, detail="Unknown LLM provider.")
    return test_provider(provider)


# ---------------------------------------------------------------------------
# Phase 7: User Management, Audit Logs & Backups
# ---------------------------------------------------------------------------

@app.get(
    "/api/admin/users",
    dependencies=[Depends(require_admin_role)],
)
def admin_list_users() -> Dict[str, Any]:
    return {
        "users": list_auth_users(),
        "invitations": list_auth_invitations(limit=100),
    }


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(
    user_id: int,
    req: UserUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_roles("super_admin")),
) -> Dict[str, Any]:
    if req.role is not None and req.role not in ("super_admin", "admin", "viewer"):
        raise HTTPException(status_code=400, detail="Unsupported role")
    if user_id == current_user.get("id") and req.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own active account")
    if user_id == current_user.get("id") and req.role is not None and req.role != "super_admin":
        raise HTTPException(status_code=400, detail="Cannot demote your own super_admin role")

    updated = update_auth_user(user_id=user_id, role=req.role, is_active=req.is_active)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    record_auth_event(
        event_type="admin_user_updated",
        actor_user_id=current_user.get("id"),
        target_email=updated.get("email"),
        details={"role": updated.get("role"), "is_active": updated.get("is_active")},
    )
    return {"saved": True, "user": updated}


@app.get(
    "/api/admin/audit-logs",
    dependencies=[Depends(require_admin_role)],
)
def admin_get_audit_logs() -> Dict[str, Any]:
    return {
        "auth_events": list_auth_audit_logs(limit=120),
        "slurm_actions": list_slurm_audit(limit=100),
        "terminal_commands": list_terminal_audit(limit=100),
    }


@app.get(
    "/api/admin/backup/database",
    dependencies=[Depends(require_roles("super_admin"))],
)
def download_sqlite_backup() -> Response:
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / "hpc_aiops_backup.db"
        backup_database_to_file(str(dest))
        payload = dest.read_bytes()
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=payload,
        media_type="application/x-sqlite3",
        headers={"Content-Disposition": f'attachment; filename="hpc_aiops_backup_{ts_slug}.db"'},
    )


@app.get(
    "/api/admin/backup/settings",
    dependencies=[Depends(require_admin_role)],
)
def download_settings_backup() -> Response:
    bundle = {
        "exported_utc": datetime.now(timezone.utc).isoformat(),
        "settings": get_app_settings(),
        "experiments": list_experiments(limit=500),
    }
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=json.dumps(bundle, indent=2, default=str).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="hpc_aiops_config_{ts_slug}.json"'},
    )


# ---------------------------------------------------------------------------
# Prometheus Exporter & Real-Time WebSocket Stream
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Prometheus Exporter & Authenticated Real-Time WebSocket Stream
# ---------------------------------------------------------------------------

@app.get("/metrics")
def prometheus_metrics_export() -> Response:
    # Kept accessible for Prometheus scraping.
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.websocket("/ws/live")
async def websocket_live_stream(ws: WebSocket) -> None:
    # Authenticate using the same HTTP-only session cookie.
    session_token = ws.cookies.get(AUTH_COOKIE_NAME)

    if not session_token:
        await ws.close(
            code=4401,
            reason="Authentication required.",
        )
        return

    current_user = get_session_user(session_token)

    if not current_user:
        await ws.close(
            code=4401,
            reason="Session expired or invalid.",
        )
        return

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
        logger.exception("WebSocket connection error.")
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

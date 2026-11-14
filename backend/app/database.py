import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import ALERT_POLICY, DB_PATH, GRAFANA_URL, PROMETHEUS_URL

_db_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enforce foreign-key relationships between authentication tables.
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def _ensure_extended_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS model_score_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            node_id TEXT NOT NULL,
            observation_utc TEXT NOT NULL,
            score REAL,
            threshold REAL,
            flagged INTEGER NOT NULL DEFAULT 0,
            classification TEXT,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_utc TEXT NOT NULL,
            UNIQUE(model_name, node_id, observation_utc)
        );
        CREATE INDEX IF NOT EXISTS idx_model_obs_lookup
            ON model_score_observations (model_name, node_id, id DESC);

        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'failure_injection',
            node_id TEXT NOT NULL DEFAULT 'cluster',
            fault_type TEXT NOT NULL DEFAULT 'unspecified',
            label TEXT NOT NULL DEFAULT 'positive_fault',
            start_utc TEXT NOT NULL,
            end_utc TEXT,
            workload_condition TEXT NOT NULL DEFAULT 'mixed',
            notes TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT 'system',
            created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gemini_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_email TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'chat',
            content TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gemini_conv_session
            ON gemini_conversations (session_id, id DESC);

        CREATE TABLE IF NOT EXISTS terminal_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            user_email TEXT NOT NULL DEFAULT '',
            node_id TEXT NOT NULL,
            command TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            blocked_reason TEXT,
            exit_code INTEGER,
            output_preview TEXT NOT NULL DEFAULT ''
        );
        """
    )


def init_db() -> None:
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS alert_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    fault_class TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    playbook_cmd TEXT NOT NULL,
                    start_utc TEXT NOT NULL,
                    last_seen_utc TEXT NOT NULL,
                    resolved_utc TEXT,
                    alert_points INTEGER NOT NULL DEFAULT 1,
                    consensus_votes INTEGER NOT NULL DEFAULT 0,
                    max_failure_prob REAL NOT NULL DEFAULT 0.0,
                    max_anomaly_score REAL NOT NULL DEFAULT 0.0,
                    top_features_json TEXT NOT NULL DEFAULT '[]',
                    silenced_until_utc TEXT,
                    data_mode TEXT NOT NULL DEFAULT 'live_prometheus'
                );

                CREATE TABLE IF NOT EXISTS slurm_actions_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    jobs_protected INTEGER NOT NULL DEFAULT 0,
                    core_hours_saved REAL NOT NULL DEFAULT 0.0,
                    kwh_saved REAL NOT NULL DEFAULT 0.0,
                    executed_mode TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telemetry_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    data_mode TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    up INTEGER NOT NULL DEFAULT 1,
                    health_score REAL,
                    cpu_percent REAL,
                    iowait_percent REAL,
                    memory_percent REAL,
                    swap_percent REAL,
                    load1 REAL,
                    normalized_load1 REAL,
                    scratch_percent REAL,
                    disk_read_mb REAL,
                    disk_write_mb REAL,
                    disk_io_percent REAL,
                    net_rx_mb REAL,
                    net_tx_mb REAL,
                    net_err_s REAL,
                    temp_celsius REAL,
                    failure_prob_1h REAL,
                    failure_prob_6h REAL,
                    anomaly_score REAL,
                    consensus_count INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_ts_node
                    ON telemetry_history (timestamp_utc, node_id);

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_utc TEXT NOT NULL
                );

                                CREATE TABLE IF NOT EXISTS ai_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    range_minutes INTEGER NOT NULL,
                    data_mode TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    node_ids_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    report_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed'
                );

                CREATE INDEX IF NOT EXISTS idx_ai_reports_created
                    ON ai_reports (created_utc DESC);

        
                
-- ==========================================
-- Authentication: Registered dashboard users
-- ==========================================

CREATE TABLE IF NOT EXISTS auth_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,

    role TEXT NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('super_admin', 'admin', 'viewer')),

    is_active INTEGER NOT NULL DEFAULT 1,
    email_verified_utc TEXT,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    last_login_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_users_email
    ON auth_users (email);


-- ==========================================
-- Authentication: One-time passwords
-- ==========================================

CREATE TABLE IF NOT EXISTS auth_otps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    otp_hash TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT 'login',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    consumed_utc TEXT,
    invalidated_utc TEXT,

    FOREIGN KEY (user_id)
        REFERENCES auth_users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auth_otps_user
    ON auth_otps (user_id, created_utc DESC);


-- ==========================================
-- Authentication: Server-managed sessions
-- ==========================================

CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token_hash TEXT NOT NULL UNIQUE,
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    last_seen_utc TEXT,
    revoked_utc TEXT,

    FOREIGN KEY (user_id)
        REFERENCES auth_users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
    ON auth_sessions (user_id);


-- ==========================================
-- Authentication: Invitation-only registration
-- ==========================================

CREATE TABLE IF NOT EXISTS auth_invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL COLLATE NOCASE,
    token_hash TEXT NOT NULL UNIQUE,

    role TEXT NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('admin', 'viewer')),

    invited_by INTEGER,
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    accepted_utc TEXT,
    revoked_utc TEXT,

    FOREIGN KEY (invited_by)
        REFERENCES auth_users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_invitations_email
    ON auth_invitations (email);


-- ==========================================
-- Authentication: Audit log
-- ==========================================

CREATE TABLE IF NOT EXISTS auth_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    event_type TEXT NOT NULL,
    target_email TEXT,
    details_json TEXT,
    created_utc TEXT NOT NULL,

    FOREIGN KEY (actor_user_id)
        REFERENCES auth_users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_audit_created
    ON auth_audit_log (created_utc DESC);

                """
            )

            # Safe migration: add full_name to existing authentication databases.
            user_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(auth_users)"
                ).fetchall()
            }

            if "full_name" not in user_columns:
                conn.execute(
                    """
                    ALTER TABLE auth_users
                    ADD COLUMN full_name TEXT NOT NULL DEFAULT ''
                    """
                )

            # Safe migration: enrich alert_episodes with alert_source, evidence_json, actor & resolution notes.
            ep_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(alert_episodes)").fetchall()
            }
            if "alert_source" not in ep_columns:
                conn.execute(
                    "ALTER TABLE alert_episodes ADD COLUMN alert_source TEXT NOT NULL DEFAULT 'telemetry'"
                )
            if "evidence_json" not in ep_columns:
                conn.execute(
                    "ALTER TABLE alert_episodes ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "acknowledged_by" not in ep_columns:
                conn.execute(
                    "ALTER TABLE alert_episodes ADD COLUMN acknowledged_by TEXT"
                )
            if "resolution_note" not in ep_columns:
                conn.execute(
                    "ALTER TABLE alert_episodes ADD COLUMN resolution_note TEXT"
                )

            # Remove obsolete placeholder ModelEngine toggle table if present.
            conn.execute("DROP TABLE IF EXISTS ml_engine_settings")

            conn.commit()
        finally:
            conn.close()

# ---------------------------------------------------------------------------
# AI-Generated Report Storage
# ---------------------------------------------------------------------------

def save_ai_report(
    report_type: str,
    title: str,
    range_minutes: int,
    data_mode: str,
    provider: str,
    model: str,
    prompt_version: str,
    node_ids: List[str],
    evidence: Dict[str, Any],
    report_text: str,
    status: str = "completed",
) -> int:
    created_utc = _utc_now_iso()

    with _db_lock:
        conn = get_conn()
        try:
            cursor = conn.execute(
                """
                INSERT INTO ai_reports (
                    report_type,
                    title,
                    created_utc,
                    range_minutes,
                    data_mode,
                    provider,
                    model,
                    prompt_version,
                    node_ids_json,
                    evidence_json,
                    report_text,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_type,
                    title,
                    created_utc,
                    range_minutes,
                    data_mode,
                    provider,
                    model,
                    prompt_version,
                    json.dumps(node_ids),
                    json.dumps(evidence),
                    report_text,
                    status,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()


def get_ai_report(report_id: int) -> Optional[Dict[str, Any]]:
    with _db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM ai_reports WHERE id = ?",
                (report_id,),
            ).fetchone()

            if not row:
                return None

            result = dict(row)
            result["node_ids"] = json.loads(result.pop("node_ids_json"))
            result["evidence"] = json.loads(result.pop("evidence_json"))

            return result
        finally:
            conn.close()


def list_ai_reports(limit: int = 50) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 200))

    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                """
                SELECT
                    id,
                    report_type,
                    title,
                    created_utc,
                    range_minutes,
                    data_mode,
                    provider,
                    model,
                    prompt_version,
                    node_ids_json,
                    status
                FROM ai_reports
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            results = []

            for row in rows:
                item = dict(row)
                item["node_ids"] = json.loads(item.pop("node_ids_json"))
                results.append(item)

            return results
        finally:
            conn.close()

def update_ai_report(
    report_id: int,
    status: str,
    report_text: Optional[str] = None,
) -> bool:
    """
    Update the status and optionally the generated text
    of an existing AI report.
    """

    allowed_statuses = {
        "pending",
        "generating",
        "completed",
        "failed",
    }

    if status not in allowed_statuses:
        raise ValueError("Invalid AI report status.")

    with _db_lock:
        conn = get_conn()
        try:
            cursor = conn.execute(
                """
                UPDATE ai_reports
                SET status = ?,
                    report_text = COALESCE(?, report_text)
                WHERE id = ?
                """,
                (status, report_text, report_id),
            )

            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()

# ---------------------------------------------------------------------------
# Persistent Application Settings
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: Dict[str, Any] = {
    "prometheus_url": PROMETHEUS_URL,
    "grafana_url": GRAFANA_URL,
    "refresh_interval_sec": 3.0,
    "ssh_host": "",
    "ssh_user": "ubuntu",
    "ssh_port": 22,
    "v7_enabled": True,
    "lstm_v8_enabled": True,
    "restricted_terminal_enabled": False,
    "email_alerts_enabled": False,
    "alert_recipient_emails": "",
    "alert_policy": dict(ALERT_POLICY),
    "node_overrides": {},
}

_LEGACY_ALERT_POLICY_KEYS = {
    "p1_critical_prob",
    "p2_warning_prob",
    "p3_watch_prob",
    "persistence_p1_p3",
    "persistence_p2_anomaly",
    "temp_warning_celsius",
    "temp_critical_celsius",
}


def get_app_settings() -> Dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    env_prom = os.getenv("PROMETHEUS_URL", "").strip()
    if env_prom:
        merged["prometheus_url"] = env_prom
    env_grafana = os.getenv("GRAFANA_URL", "").strip()
    if env_grafana:
        merged["grafana_url"] = env_grafana
    env_ssh_host = os.getenv("HPC_SSH_HOST", "").strip()
    if env_ssh_host:
        merged["ssh_host"] = env_ssh_host
    env_ssh_user = os.getenv("HPC_SSH_USER", "").strip()
    if env_ssh_user:
        merged["ssh_user"] = env_ssh_user
    env_ssh_port = os.getenv("HPC_SSH_PORT", "").strip()
    if env_ssh_port.isdigit() and int(env_ssh_port) > 0:
        merged["ssh_port"] = int(env_ssh_port)

    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute("SELECT key, value_json FROM app_settings").fetchall()
            db_values: Dict[str, Any] = {}
            for r in rows:
                try:
                    db_values[r["key"]] = json.loads(r["value_json"])
                except Exception:
                    pass
            db_ssh_host = str(db_values.get("ssh_host") or "").strip()
            for key, val in db_values.items():
                if key == "alert_policy" and isinstance(val, dict):
                    cleaned = {
                        k: v
                        for k, v in val.items()
                        if k not in _LEGACY_ALERT_POLICY_KEYS and k in ALERT_POLICY
                    }
                    merged["alert_policy"].update(cleaned)
                elif key == "ssh_host" and isinstance(val, str) and not val.strip() and env_ssh_host:
                    continue
                elif key == "ssh_port" and not db_ssh_host and env_ssh_host and env_ssh_port.isdigit():
                    # Ignore stale default ssh_port saved with blank ssh_host when env configures target
                    continue
                else:
                    merged[key] = val
        finally:
            conn.close()
    return merged


def update_app_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    now_iso = _utc_now_iso()
    allowed_keys = {
        "prometheus_url",
        "grafana_url",
        "refresh_interval_sec",
        "ssh_host",
        "ssh_user",
        "ssh_port",
        "v7_enabled",
        "lstm_v8_enabled",
        "restricted_terminal_enabled",
        "email_alerts_enabled",
        "alert_recipient_emails",
        "alert_policy",
        "node_overrides",
    }
    with _db_lock:
        conn = get_conn()
        try:
            for key, val in updates.items():
                if key not in allowed_keys or val is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO app_settings (key, value_json, updated_utc)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_utc = excluded.updated_utc
                    """,
                    (key, json.dumps(val), now_iso),
                )
            conn.commit()
        finally:
            conn.close()
    return get_app_settings()


# ---------------------------------------------------------------------------
# Telemetry & Prediction History Recording (for Analytics & CSV/PDF Reports)
# ---------------------------------------------------------------------------

def record_telemetry_batch(
    timestamp_utc: str, data_mode: str, scored_nodes: List[Dict[str, Any]]
) -> None:
    if not scored_nodes:
        return
    rows = []
    for n in scored_nodes:
        dr = n.get("disk_read_bytes_per_second")
        dw = n.get("disk_write_bytes_per_second")
        nrx = n.get("network_receive_bytes_per_second")
        ntx = n.get("network_transmit_bytes_per_second")
        rows.append(
            (
                timestamp_utc,
                data_mode,
                str(n.get("node_id", "unknown")),
                int(n.get("up", 1) if n.get("up") is not None else 0),
                None,
                n.get("cpu_utilization_percent"),
                n.get("cpu_iowait_percent"),
                n.get("memory_used_percent"),
                n.get("swap_used_percent"),
                n.get("load1"),
                n.get("normalized_load1"),
                n.get("scratch_used_percent"),
                round(float(dr) / (1024 * 1024), 3) if dr is not None else None,
                round(float(dw) / (1024 * 1024), 3) if dw is not None else None,
                n.get("disk_io_utilization_percent"),
                round(float(nrx) / (1024 * 1024), 3) if nrx is not None else None,
                round(float(ntx) / (1024 * 1024), 3) if ntx is not None else None,
                n.get("network_errors_per_second"),
                None,
                None,
                None,
                None,
                0,
            )
        )
    with _db_lock:
        conn = get_conn()
        try:
            conn.executemany(
                """
                INSERT INTO telemetry_history (
                    timestamp_utc, data_mode, node_id, up, health_score,
                    cpu_percent, iowait_percent, memory_percent, swap_percent,
                    load1, normalized_load1, scratch_percent,
                    disk_read_mb, disk_write_mb, disk_io_percent,
                    net_rx_mb, net_tx_mb, net_err_s, temp_celsius,
                    failure_prob_1h, failure_prob_6h, anomaly_score, consensus_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            # Keep bounded to ~12,000 rows (~24h of 4-node history)
            conn.execute(
                """
                DELETE FROM telemetry_history
                WHERE id < COALESCE((SELECT MAX(id) - 12000 FROM telemetry_history), 0)
                """
            )
            conn.commit()
        finally:
            conn.close()


def query_telemetry_history(
    range_minutes: Optional[int] = 60,
    node_id: Optional[str] = None,
    limit: int = 1200,
) -> List[Dict[str, Any]]:
    with _db_lock:
        conn = get_conn()
        try:
            clauses = []
            params: List[Any] = []
            if node_id:
                clauses.append("node_id = ?")
                params.append(node_id)
            if range_minutes and range_minutes > 0:
                # Only filter by wall-clock cutoff for non-replay live modes;
                # if table has synthetic timestamps in 2026-08/09, return latest rows cleanly.
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(minutes=range_minutes)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                count_recent = conn.execute(
                    "SELECT COUNT(*) AS c FROM telemetry_history WHERE timestamp_utc >= ?",
                    (cutoff,),
                ).fetchone()["c"]
                if count_recent > 0:
                    clauses.append("timestamp_utc >= ?")
                    params.append(cutoff)

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT * FROM telemetry_history
                    {where_sql}
                    ORDER BY id DESC
                    LIMIT ?
                ) sub
                ORDER BY id ASC
                """,
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Alert Episodes, Slurm Audit & System Logs
# ---------------------------------------------------------------------------

def upsert_alert_episode(
    node_id: str,
    priority: str,
    event_type: str,
    alert_source: str,
    title: str,
    summary: str,
    recommended_checks: str,
    timestamp_utc: str,
    evidence: List[Dict[str, Any]],
    data_mode: str,
    model_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Create or update an active/acknowledged alert episode grouped by node and event_type."""
    priority_rank = {"P3": 1, "P2": 2, "P1": 3}
    with _db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM alert_episodes
                WHERE node_id = ?
                  AND fault_class = ?
                  AND status IN ('active', 'acknowledged', 'silenced')
                ORDER BY id DESC LIMIT 1
                """,
                (node_id, event_type),
            ).fetchone()

            evidence_json = json.dumps(evidence)
            score_val = float(model_score) if model_score is not None else 0.0
            if row:
                new_prio = (
                    priority
                    if priority_rank.get(priority, 1) >= priority_rank.get(row["priority"], 1)
                    else row["priority"]
                )
                new_status = row["status"]
                if priority == "P1" and row["priority"] != "P1":
                    new_status = "active"

                conn.execute(
                    """
                    UPDATE alert_episodes
                    SET priority = ?,
                        status = ?,
                        alert_source = ?,
                        fault_class = ?,
                        title = ?,
                        summary = ?,
                        playbook_cmd = ?,
                        last_seen_utc = ?,
                        alert_points = alert_points + 1,
                        max_anomaly_score = MAX(max_anomaly_score, ?),
                        evidence_json = ?,
                        top_features_json = ?
                    WHERE id = ?
                    """,
                    (
                        new_prio,
                        new_status,
                        alert_source,
                        event_type,
                        title,
                        summary,
                        recommended_checks,
                        timestamp_utc,
                        score_val,
                        evidence_json,
                        evidence_json,
                        row["id"],
                    ),
                )
                conn.commit()
                updated = conn.execute(
                    "SELECT * FROM alert_episodes WHERE id = ?", (row["id"],)
                ).fetchone()
                return _row_to_episode(updated)
            else:
                cur = conn.execute(
                    """
                    INSERT INTO alert_episodes (
                        node_id, priority, status, alert_source, fault_class, title, summary,
                        playbook_cmd, start_utc, last_seen_utc, alert_points,
                        consensus_votes, max_failure_prob, max_anomaly_score,
                        evidence_json, top_features_json, data_mode
                    ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, 1, 0, 0.0, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        priority,
                        alert_source,
                        event_type,
                        title,
                        summary,
                        recommended_checks,
                        timestamp_utc,
                        timestamp_utc,
                        score_val,
                        evidence_json,
                        evidence_json,
                        data_mode,
                    ),
                )
                conn.commit()
                created = conn.execute(
                    "SELECT * FROM alert_episodes WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
                return _row_to_episode(created)
        finally:
            conn.close()


_NODE_ID_ALIASES: Dict[str, List[str]] = {
    "headnode": ["headnode", "head-node"],
    "head-node": ["head-node", "headnode"],
    "compute001": ["compute001", "compute-01"],
    "compute-01": ["compute-01", "compute001"],
    "compute002": ["compute002", "compute-02"],
    "compute-02": ["compute-02", "compute002"],
    "compute003": ["compute003", "compute-03"],
    "compute-03": ["compute-03", "compute003"],
}


def auto_resolve_node_episodes(
    node_id: str,
    timestamp_utc: str,
    keep_event_types: Optional[List[str]] = None,
) -> None:
    aliases = _NODE_ID_ALIASES.get(node_id, [node_id])
    node_placeholders = ",".join("?" for _ in aliases)
    with _db_lock:
        conn = get_conn()
        try:
            keep = list(keep_event_types or [])
            if keep:
                placeholders = ",".join("?" for _ in keep)
                conn.execute(
                    f"""
                    UPDATE alert_episodes
                    SET status = 'resolved', resolved_utc = COALESCE(resolved_utc, ?)
                    WHERE node_id IN ({node_placeholders})
                      AND status IN ('active', 'acknowledged')
                      AND fault_class NOT IN ({placeholders})
                    """,
                    [timestamp_utc, *aliases, *keep],
                )
            else:
                conn.execute(
                    f"""
                    UPDATE alert_episodes
                    SET status = 'resolved', resolved_utc = ?
                    WHERE node_id IN ({node_placeholders}) AND status IN ('active', 'acknowledged')
                    """,
                    [timestamp_utc, *aliases],
                )
            conn.commit()
        finally:
            conn.close()


def auto_resolve_stale_offline_prometheus_episodes(timestamp_utc: str) -> int:
    """Resolve legacy node_offline episodes created when Prometheus itself was unreachable."""
    with _db_lock:
        conn = get_conn()
        try:
            cur = conn.execute(
                """
                UPDATE alert_episodes
                SET status = 'resolved',
                    resolved_utc = COALESCE(resolved_utc, ?)
                WHERE fault_class = 'node_offline'
                  AND status IN ('active', 'acknowledged')
                  AND summary LIKE '%PROMETHEUS OFFLINE%'
                """,
                (timestamp_utc,),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()


def update_episode_status(
    episode_id: int,
    action: str,
    silenced_until_utc: Optional[str] = None,
    acknowledged_by: Optional[str] = None,
    resolution_note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    status_map = {
        "acknowledge": "acknowledged",
        "investigate": "acknowledged",
        "silence": "silenced",
        "resolve": "resolved",
        "reopen": "active",
    }
    new_status = status_map.get(action, "acknowledged")
    now_iso = _utc_now_iso()
    with _db_lock:
        conn = get_conn()
        try:
            conn.execute(
                """
                UPDATE alert_episodes
                SET status = ?,
                    silenced_until_utc = COALESCE(?, silenced_until_utc),
                    resolved_utc = CASE WHEN ? = 'resolved' THEN ? ELSE NULL END,
                    acknowledged_by = COALESCE(?, acknowledged_by),
                    resolution_note = COALESCE(?, resolution_note)
                WHERE id = ?
                """,
                (
                    new_status,
                    silenced_until_utc,
                    new_status,
                    now_iso,
                    acknowledged_by,
                    resolution_note,
                    episode_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM alert_episodes WHERE id = ?", (episode_id,)
            ).fetchone()
            return _row_to_episode(row) if row else None
        finally:
            conn.close()


def list_episodes(limit: int = 100) -> List[Dict[str, Any]]:
    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM alert_episodes
                ORDER BY
                    CASE WHEN status = 'active' THEN 0
                         WHEN status = 'acknowledged' THEN 1
                         WHEN status = 'silenced' THEN 2
                         ELSE 3 END,
                    CASE priority WHEN 'P1' THEN 0 WHEN 'P2' THEN 1 ELSE 2 END,
                    id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_row_to_episode(r) for r in rows]
        finally:
            conn.close()


def record_slurm_action(
    node_id: str,
    action: str,
    reason: str,
    jobs_protected: int,
    core_hours_saved: float,
    kwh_saved: float,
    executed_mode: str,
) -> Dict[str, Any]:
    now_iso = _utc_now_iso()
    with _db_lock:
        conn = get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO slurm_actions_audit (
                    timestamp_utc, node_id, action, reason,
                    jobs_protected, core_hours_saved, kwh_saved, executed_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    node_id,
                    action,
                    reason,
                    jobs_protected,
                    round(core_hours_saved, 2),
                    round(kwh_saved, 3),
                    executed_mode,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM slurm_actions_audit WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)
        finally:
            conn.close()


def list_slurm_audit(limit: int = 60) -> List[Dict[str, Any]]:
    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM slurm_actions_audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_roi_totals() -> Dict[str, Any]:
    """Return actual recorded Slurm operator action totals without synthetic multipliers."""
    with _db_lock:
        conn = get_conn()
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_drains,
                    COALESCE(SUM(jobs_protected), 0) AS total_jobs_protected,
                    COALESCE(SUM(core_hours_saved), 0.0) AS total_core_hours_saved
                FROM slurm_actions_audit
                WHERE action = 'DRAIN'
                """
            ).fetchone()
            ep_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_incidents,
                    SUM(CASE WHEN status IN ('active', 'acknowledged') THEN 1 ELSE 0 END) AS open_incidents,
                    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved_incidents
                FROM alert_episodes
                """
            ).fetchone()
            return {
                "proactive_drains": int(row["total_drains"]),
                "jobs_protected": int(row["total_jobs_protected"]),
                "core_hours_saved": round(float(row["total_core_hours_saved"]), 1),
                "total_incidents": int(ep_row["total_incidents"] or 0),
                "open_incidents": int(ep_row["open_incidents"] or 0),
                "resolved_incidents": int(ep_row["resolved_incidents"] or 0),
                "power_metrics_available": False,
            }
        finally:
            conn.close()


def add_system_log(
    timestamp_utc: str,
    node_id: str,
    source: str,
    severity: str,
    event_type: str,
    message: str,
) -> None:
    with _db_lock:
        conn = get_conn()
        try:
            last = conn.execute(
                "SELECT message, node_id FROM system_logs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last and last["node_id"] == node_id and last["message"] == message:
                return
            conn.execute(
                """
                INSERT INTO system_logs (timestamp_utc, node_id, source, severity, event_type, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (timestamp_utc, node_id, source, severity, event_type, message),
            )
            conn.execute(
                "DELETE FROM system_logs WHERE id NOT IN (SELECT id FROM system_logs ORDER BY id DESC LIMIT 500)"
            )
            conn.commit()
        finally:
            conn.close()


def list_system_logs(limit: int = 80) -> List[Dict[str, Any]]:
    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM system_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def clear_all_runtime_records() -> None:
    with _db_lock:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM alert_episodes")
            conn.execute("DELETE FROM system_logs")
            conn.execute("DELETE FROM telemetry_history")
            conn.commit()
        finally:
            conn.close()


def _row_to_episode(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    sev_map = {"P1": "critical", "P2": "warning", "P3": "info"}
    d["severity"] = sev_map.get(d.get("priority", "P3"), "info")
    d["event_type"] = d.get("fault_class") or "unknown"
    d["alert_source"] = d.get("alert_source") or "telemetry"
    d["recommended_checks"] = d.get("playbook_cmd") or ""
    raw_ev = d.pop("evidence_json", None)
    raw_legacy = d.pop("top_features_json", "[]")
    try:
        parsed_ev = json.loads(raw_ev if raw_ev and raw_ev != "[]" else raw_legacy)
    except Exception:
        parsed_ev = []
    d["evidence"] = parsed_ev
    return d


# ---------------------------------------------------------------------------
# Model Observations, Experiments, Gemini History & Terminal Audit Logs
# ---------------------------------------------------------------------------

def record_model_observation(
    model_name: str,
    node_id: str,
    observation_utc: str,
    score: Optional[float],
    threshold: Optional[float],
    flagged: bool,
    classification: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    if not observation_utc:
        return
    created = _utc_now_iso()
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            conn.execute(
                """
                INSERT OR IGNORE INTO model_score_observations (
                    model_name, node_id, observation_utc, score, threshold,
                    flagged, classification, details_json, created_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_name,
                    node_id,
                    observation_utc,
                    float(score) if score is not None else None,
                    float(threshold) if threshold is not None else None,
                    1 if flagged else 0,
                    classification,
                    json.dumps(details or {}, default=str),
                    created,
                ),
            )
            conn.execute(
                """
                DELETE FROM model_score_observations
                WHERE id < COALESCE((SELECT MAX(id) - 10000 FROM model_score_observations), 0)
                """
            )
            conn.commit()
        finally:
            conn.close()


def list_model_observations(
    model_name: Optional[str] = None,
    node_id: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 5000))
    clauses = []
    params: List[Any] = []
    if model_name:
        clauses.append("model_name = ?")
        params.append(model_name)
    if node_id:
        clauses.append("node_id = ?")
        params.append(node_id)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            rows = conn.execute(
                f"SELECT * FROM model_score_observations {where_sql} ORDER BY observation_utc DESC, id DESC LIMIT ?",
                params,
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d["flagged"] = bool(d.get("flagged"))
                try:
                    d["details"] = json.loads(d.pop("details_json", "{}") or "{}")
                except Exception:
                    d["details"] = {}
                out.append(d)
            return out
        finally:
            conn.close()


def create_experiment(
    name: str,
    category: str,
    node_id: str,
    fault_type: str,
    label: str,
    start_utc: str,
    end_utc: Optional[str] = None,
    workload_condition: str = "mixed",
    notes: str = "",
    created_by: str = "system",
) -> int:
    created = _utc_now_iso()
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            cur = conn.execute(
                """
                INSERT INTO experiments (
                    name, category, node_id, fault_type, label,
                    start_utc, end_utc, workload_condition, notes, created_by, created_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    category.strip(),
                    node_id.strip(),
                    fault_type.strip(),
                    label.strip(),
                    start_utc.strip(),
                    end_utc.strip() if end_utc else None,
                    workload_condition.strip() or "mixed",
                    notes.strip(),
                    created_by,
                    created,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def update_experiment(experiment_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {
        "name", "category", "node_id", "fault_type", "label",
        "start_utc", "end_utc", "workload_condition", "notes",
    }
    clean = {k: v for k, v in updates.items() if k in allowed}
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            if clean:
                set_clause = ", ".join(f"{k} = ?" for k in clean)
                conn.execute(
                    f"UPDATE experiments SET {set_clause} WHERE id = ?",
                    [*clean.values(), experiment_id],
                )
                conn.commit()
            row = conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def delete_experiment(experiment_id: int) -> bool:
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            cur = conn.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def list_experiments(category: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            if category:
                rows = conn.execute(
                    "SELECT * FROM experiments WHERE category = ? ORDER BY start_utc DESC, id DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM experiments ORDER BY start_utc DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def append_gemini_message(
    session_id: str,
    user_email: str,
    role: str,
    mode: str,
    content: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> int:
    created = _utc_now_iso()
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            cur = conn.execute(
                """
                INSERT INTO gemini_conversations (
                    session_id, user_email, role, mode, content, evidence_json, created_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_email,
                    role,
                    mode,
                    content,
                    json.dumps(evidence or {}, default=str),
                    created,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def list_gemini_messages(
    session_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM gemini_conversations WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM gemini_conversations ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                try:
                    d["evidence"] = json.loads(d.pop("evidence_json", "{}") or "{}")
                except Exception:
                    d["evidence"] = {}
                out.append(d)
            return out
        finally:
            conn.close()


def record_terminal_audit(
    user_email: str,
    node_id: str,
    command: str,
    allowed: bool,
    blocked_reason: Optional[str] = None,
    exit_code: Optional[int] = None,
    output_preview: str = "",
) -> None:
    ts = _utc_now_iso()
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            conn.execute(
                """
                INSERT INTO terminal_audit_logs (
                    timestamp_utc, user_email, node_id, command,
                    allowed, blocked_reason, exit_code, output_preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    user_email,
                    node_id,
                    command[:500],
                    1 if allowed else 0,
                    blocked_reason,
                    exit_code,
                    output_preview[:800],
                ),
            )
            conn.execute(
                "DELETE FROM terminal_audit_logs WHERE id NOT IN (SELECT id FROM terminal_audit_logs ORDER BY id DESC LIMIT 500)"
            )
            conn.commit()
        finally:
            conn.close()


def list_terminal_audit(limit: int = 100) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with _db_lock:
        conn = get_conn()
        try:
            _ensure_extended_tables(conn)
            rows = conn.execute(
                "SELECT * FROM terminal_audit_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{**dict(r), "allowed": bool(r["allowed"])} for r in rows]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Team User Management, Audit Queries & SQLite Backups
# ---------------------------------------------------------------------------

def list_auth_users() -> List[Dict[str, Any]]:
    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM auth_users ORDER BY id ASC"
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d.pop("password_hash", None)
                d["is_active"] = bool(d.get("is_active", 1))
                d["email_verified"] = bool(d.get("email_verified_utc"))
                out.append(d)
            return out
        finally:
            conn.close()


def update_auth_user(
    user_id: int,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    with _db_lock:
        conn = get_conn()
        try:
            row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            new_role = role if role in ("super_admin", "admin", "viewer") else row["role"]
            new_active = (1 if is_active else 0) if is_active is not None else row["is_active"]
            conn.execute(
                "UPDATE auth_users SET role = ?, is_active = ? WHERE id = ?",
                (new_role, new_active, user_id),
            )
            conn.commit()
            updated = dict(conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone())
            updated.pop("password_hash", None)
            updated["is_active"] = bool(updated.get("is_active", 1))
            updated["email_verified"] = bool(updated.get("email_verified_utc"))
            return updated
        finally:
            conn.close()


def list_auth_invitations(limit: int = 100) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 300))
    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM auth_invitations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d.pop("token_hash", None)
                out.append(d)
            return out
        finally:
            conn.close()


def list_auth_audit_logs(limit: int = 120) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with _db_lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM auth_audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                try:
                    d["details"] = json.loads(d.pop("details_json", "{}") or "{}")
                except Exception:
                    d["details"] = {}
                out.append(d)
            return out
        finally:
            conn.close()


def backup_database_to_file(dest_path: str) -> None:
    with _db_lock:
        src_conn = get_conn()
        dest_conn = sqlite3.connect(dest_path)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            src_conn.close()

from datetime import datetime, timezone
import io
import json
import re
from typing import Any, Dict, List, Optional
import zipfile

from .database import list_episodes, list_slurm_audit, list_system_logs
from .ssh_bridge import (
    execute_restricted_cluster_command,
    redact_sensitive_text,
    validate_safe_identifier,
)

# Strictly allowlisted log categories and their read-only Linux commands
LOG_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "system": {
        "label": "System Logs (journalctl)",
        "build_cmd": lambda n: ["journalctl", "-n", str(n), "--no-pager", "-o", "short-iso"],
    },
    "kernel": {
        "label": "Kernel Logs (dmesg / journal -k)",
        "build_cmd": lambda n: ["journalctl", "-k", "-n", str(n), "--no-pager", "-o", "short-iso"],
    },
    "auth": {
        "label": "Authentication Logs (sshd)",
        "build_cmd": lambda n: ["journalctl", "-u", "ssh", "-u", "sshd", "-n", str(n), "--no-pager", "-o", "short-iso"],
    },
    "slurmctld": {
        "label": "Slurm Controller (slurmctld)",
        "build_cmd": lambda n: ["journalctl", "-u", "slurmctld", "-n", str(n), "--no-pager", "-o", "short-iso"],
    },
    "slurmd": {
        "label": "Slurm Compute Daemon (slurmd)",
        "build_cmd": lambda n: ["journalctl", "-u", "slurmd", "-n", str(n), "--no-pager", "-o", "short-iso"],
    },
    "node_exporter": {
        "label": "Node Exporter Service",
        "build_cmd": lambda n: [
            "journalctl",
            "-u",
            "prometheus-node-exporter",
            "-u",
            "node_exporter",
            "-n",
            str(n),
            "--no-pager",
            "-o",
            "short-iso",
        ],
    },
    "monitoring": {
        "label": "Monitoring Services (Prometheus / Grafana / AIOps)",
        "build_cmd": lambda n: [
            "journalctl",
            "-u",
            "prometheus",
            "-u",
            "grafana-server",
            "-n",
            str(n),
            "--no-pager",
            "-o",
            "short-iso",
        ],
    },
}

ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}([T ][0-9]{2}:[0-9]{2}(:[0-9]{2})?(Z|[+-][0-9:]+)?)?$")


def _infer_severity(line: str) -> str:
    low = line.lower()
    if any(k in low for k in ("crit", "fatal", "panic", "emerg", "oom-killer", "error", "failed", "failure")):
        return "ERROR"
    if any(k in low for k in ("warn", "throttl", "timeout", "degrad", "retry", "drain")):
        return "WARNING"
    return "INFO"


def _parse_journal_lines(raw_text: str, node_id: str, category: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for idx, line in enumerate(raw_text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("-- No entries --"):
            continue
        # short-iso format: 2026-10-31T12:01:04+0200 host unit[pid]: message
        parts = stripped.split(" ", 2)
        ts = parts[0] if len(parts) >= 1 and len(parts[0]) >= 16 and parts[0][4:5] == "-" else ""
        msg = parts[2] if ts and len(parts) >= 3 else stripped
        sev = _infer_severity(msg)
        entries.append(
            {
                "id": f"{node_id}-{category}-{idx}",
                "timestamp": ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "node_id": node_id,
                "category": category,
                "severity": sev,
                "source": category,
                "message": msg,
                "raw": stripped,
            }
        )
    return entries


def retrieve_node_logs(
    node_id: str,
    target_ip: str,
    category: str = "system",
    lines: int = 200,
    keyword: Optional[str] = None,
    severity: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Securely fetch and filter node-specific logs from the Linux cluster via SSH/local execution,
    or surface recorded AIOps SQLite logs with clear connection status if SSH is disconnected.
    """
    if not validate_safe_identifier(node_id):
        raise ValueError("Invalid node identifier")
    if category not in LOG_CATEGORIES:
        raise ValueError(f"Unsupported log category: {category}")

    bounded_lines = max(20, min(int(lines or 200), 1000))
    cmd = list(LOG_CATEGORIES[category]["build_cmd"](bounded_lines))

    if since and ISO_DATE_RE.match(since.strip()):
        cmd.extend(["--since", since.strip()])
    if until and ISO_DATE_RE.match(until.strip()):
        cmd.extend(["--until", until.strip()])

    ok, out, exec_source = execute_restricted_cluster_command(
        command_args=cmd,
        target_node_ip=target_ip or "localhost",
        timeout_sec=6.5,
    )

    entries: List[Dict[str, Any]] = []
    ssh_notice: Optional[str] = None

    if ok and out.strip():
        entries = _parse_journal_lines(out, node_id, category)
    else:
        ssh_notice = out or "Direct SSH journalctl unavailable; showing recorded AIOps telemetry & scheduler logs."
        # Pull real recorded events from SQLite matching this node (or cluster-wide for head-node)
        db_logs = list_system_logs(limit=250)
        for row in db_logs:
            if row["node_id"] in (node_id, "cluster") or (node_id == "head-node" and row["node_id"] == "head-node"):
                sev_norm = "ERROR" if row["severity"] == "CRITICAL" else row["severity"]
                raw_line = f"{row['timestamp_utc']} {row['node_id']} {row['source']}: [{row['severity']}] {row['message']}"
                entries.append(
                    {
                        "id": f"db-{row['id']}",
                        "timestamp": row["timestamp_utc"],
                        "node_id": row["node_id"],
                        "category": category,
                        "severity": sev_norm,
                        "source": row["source"],
                        "message": row["message"],
                        "raw": redact_sensitive_text(raw_line),
                    }
                )

    # Apply safe Python-side filtering (keyword, severity, date bounds)
    if severity and severity.upper() not in ("ALL", ""):
        sev_target = severity.upper()
        if sev_target in ("CRITICAL", "ERROR"):
            entries = [e for e in entries if e["severity"] in ("ERROR", "CRITICAL")]
        else:
            entries = [e for e in entries if e["severity"] == sev_target]

    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        entries = [
            e
            for e in entries
            if kw in e["message"].lower() or kw in e["source"].lower() or kw in e["raw"].lower()
        ]

    if since and since.strip():
        s_clean = since.strip()
        entries = [e for e in entries if not e["timestamp"] or e["timestamp"] >= s_clean]

    if until and until.strip():
        u_clean = until.strip()
        entries = [e for e in entries if not e["timestamp"] or e["timestamp"] <= u_clean]

    return {
        "node_id": node_id,
        "category": category,
        "category_label": LOG_CATEGORIES[category]["label"],
        "source_mode": exec_source if ok else "local_audit_db",
        "ssh_connected": ok,
        "notice": ssh_notice,
        "count": len(entries),
        "entries": entries,
    }


def format_log_entries_as_text(log_payload: Dict[str, Any]) -> str:
    header = [
        f"# Sol Plaatje A Dev Cluster Dashboard — Log Export",
        f"# Node: {log_payload['node_id']} | Category: {log_payload['category_label']}",
        f"# Source Mode: {log_payload['source_mode']} | Exported UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "#" + "-" * 78,
    ]
    body = [e["raw"] for e in log_payload.get("entries", [])]
    if not body:
        body = ["# No matching log lines for the selected criteria."]
    return redact_sensitive_text("\n".join(header + body) + "\n")


def build_selected_logs_zip(
    node_id: str,
    target_ip: str,
    categories: List[str],
    lines: int = 250,
    keyword: Optional[str] = None,
    severity: Optional[str] = None,
) -> bytes:
    buf = io.BytesIO()
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    valid_cats = [c for c in categories if c in LOG_CATEGORIES] or ["system", "kernel"]

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cat in valid_cats:
            payload = retrieve_node_logs(
                node_id=node_id,
                target_ip=target_ip,
                category=cat,
                lines=lines,
                keyword=keyword,
                severity=severity,
            )
            txt = format_log_entries_as_text(payload)
            zf.writestr(f"{node_id}_{cat}_{ts_slug}.log", txt)

    return buf.getvalue()


def _sanitize_node_snapshot(node: Dict[str, Any]) -> Dict[str, Any]:
    """Strip any internal fields and ensure zero credential metadata exists."""
    safe = dict(node)
    safe.pop("ssh_target", None)
    return safe


def build_node_diagnostic_bundle_zip(
    node: Dict[str, Any],
    model_status: Dict[str, Any],
) -> bytes:
    node_id = str(node.get("node_id", "unknown"))
    target_ip = str(node.get("ssh_target") or node.get("ip") or "localhost")
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "bundle_type": "single_node_diagnostic",
            "platform": "Sol Plaatje A Dev Cluster Dashboard",
            "generated_utc": now_iso,
            "node_id": node_id,
            "sanitized": True,
            "model_engine": {
                "engine_mode": model_status.get("engine_mode"),
                "engine_label": model_status.get("engine_label"),
                "detectors": model_status.get("detectors"),
            },
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr(
            f"{node_id}_telemetry_and_ai_prediction.json",
            json.dumps(_sanitize_node_snapshot(node), indent=2),
        )

        node_alerts = [e for e in list_episodes(limit=100) if e.get("node_id") == node_id]
        zf.writestr(f"{node_id}_alerts_history.json", json.dumps(node_alerts, indent=2))

        for cat in ("system", "kernel", "slurmd", "node_exporter"):
            payload = retrieve_node_logs(node_id=node_id, target_ip=target_ip, category=cat, lines=200)
            zf.writestr(f"logs/{node_id}_{cat}_{ts_slug}.log", format_log_entries_as_text(payload))

    return buf.getvalue()


def build_cluster_diagnostic_bundle_zip(snapshot: Dict[str, Any]) -> bytes:
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    nodes = snapshot.get("nodes", [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        summary = {
            "bundle_type": "cluster_wide_diagnostic",
            "platform": "Sol Plaatje A Dev Cluster Dashboard",
            "generated_utc": now_iso,
            "data_mode": snapshot.get("mode"),
            "cluster_health_score": snapshot.get("kpis", {}).get("cluster_health_score"),
            "kpis": snapshot.get("kpis", {}),
            "sanitized": True,
        }
        zf.writestr("cluster_manifest.json", json.dumps(summary, indent=2))
        zf.writestr(
            "nodes_telemetry_and_predictions.json",
            json.dumps([_sanitize_node_snapshot(n) for n in nodes], indent=2),
        )
        zf.writestr("alerts_and_incidents.json", json.dumps(list_episodes(limit=150), indent=2))
        zf.writestr("slurm_jobs_snapshot.json", json.dumps(snapshot.get("slurm_jobs", []), indent=2))
        zf.writestr("slurm_admin_audit.json", json.dumps(list_slurm_audit(limit=100), indent=2))

        for n in nodes[:6]:
            nid = str(n.get("node_id", "node"))
            tip = str(n.get("ssh_target") or n.get("ip") or "localhost")
            for cat in ("system", "kernel"):
                payload = retrieve_node_logs(node_id=nid, target_ip=tip, category=cat, lines=120)
                zf.writestr(f"logs/{nid}_{cat}_{ts_slug}.log", format_log_entries_as_text(payload))

    return buf.getvalue()

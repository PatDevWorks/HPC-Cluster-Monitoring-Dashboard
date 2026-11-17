import csv
from datetime import datetime, timezone
import io
from typing import Any, Dict, List, Tuple

from .database import (
    list_episodes,
    list_slurm_audit,
    query_telemetry_history,
)
from .evaluation_service import compute_model_comparison_summary


def build_report_data(
    report_type: str,
    snapshot: Dict[str, Any],
    range_minutes: int = 60,
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    nodes = snapshot.get("nodes", [])
    kpis = snapshot.get("kpis", {})

    if report_type in ("ai_predictions", "model_status"):
        title = "AI Model Status Report (V7 Isolation Forest & LSTM V8)"
        columns = [
            "Node",
            "Role",
            "Operational Status",
            "V7 Anomaly Score",
            "V7 Threshold",
            "V7 Status",
            "LSTM Warning Score",
            "LSTM Status",
        ]
        rows = []
        for n in nodes:
            v7 = n.get("v7_detection") or {}
            lstm = n.get("lstm_v8_status") or {}
            lw = lstm.get("latest_warning") or {}
            rows.append([
                n.get("display_name") or n.get("node_id"),
                n.get("role", ""),
                n.get("health_classification", n.get("health_status", "Healthy")),
                _fmt_num(v7.get("anomaly_score"), 4),
                _fmt_num(v7.get("threshold"), 4),
                str(v7.get("status", "disabled" if not v7 else "ok")),
                _fmt_num(lw.get("warning_score"), 4),
                str(lw.get("status", "unavailable" if not lstm else "ok")),
            ])
    elif report_type == "alerts_incidents":
        title = "Cluster Alerts & Incident History Report"
        episodes = list_episodes(limit=150)
        columns = [
            "ID",
            "Severity",
            "Priority",
            "Source",
            "Status",
            "Node",
            "Event Type",
            "Points",
            "Start UTC",
            "Last Seen UTC",
        ]
        rows = [
            [
                str(e.get("id")),
                str(e.get("severity", "")).upper(),
                str(e.get("priority", "")),
                str(e.get("alert_source", "telemetry")),
                str(e.get("status", "")),
                str(e.get("node_id", "")),
                str(e.get("event_type", e.get("fault_class", ""))),
                str(e.get("alert_points", 1)),
                str(e.get("start_utc", "")),
                str(e.get("last_seen_utc", "")),
            ]
            for e in episodes
        ]
    elif report_type == "slurm_workload":
        title = "Slurm Workload & Administrative Audit Report"
        jobs = snapshot.get("slurm_jobs", [])
        audit = list_slurm_audit(limit=80)
        columns = [
            "Record Type",
            "Identifier",
            "Node / Queue",
            "Owner / Action",
            "State / Mode",
            "CPUs / Saved Core-Hrs",
            "Timestamp / Duration",
            "Details",
        ]
        rows = [
            [
                "SLURM_JOB",
                str(j.get("job_id", "")),
                ",".join(j.get("nodes", [])) or str(j.get("partition", "")),
                str(j.get("user", "")),
                str(j.get("state", "")),
                str(j.get("cpus", "")),
                str(j.get("duration") or f"{j.get('elapsed_hours', 0)}h"),
                str(j.get("name", "")),
            ]
            for j in jobs
        ] + [
            [
                "ADMIN_AUDIT",
                f"AUDIT-{a.get('id')}",
                str(a.get("node_id", "")),
                str(a.get("action", "")),
                str(a.get("executed_mode", "")),
                f"{a.get('core_hours_saved', 0)} core-h",
                str(a.get("timestamp_utc", "")),
                str(a.get("reason", "")),
            ]
            for a in audit
        ]
    elif report_type == "experiment_evaluation":
        title = "Experiment & Model Comparison Evaluation Report (V7 vs LSTM V8 vs Thresholds)"
        ev = compute_model_comparison_summary()
        columns = [
            "Experiment ID",
            "Name",
            "Category",
            "Node",
            "Label",
            "Workload",
            "V7 Detected",
            "V7 Delay (min)",
            "LSTM V8 Detected",
            "LSTM Delay (min)",
            "Telemetry Detected",
            "Telemetry Delay (min)",
        ]
        rows = [
            [
                str(r.get("id", "")),
                str(r.get("name", "")),
                str(r.get("category", "")),
                str(r.get("node_id", "")),
                str(r.get("label", "")),
                str(r.get("workload_condition", "")),
                "Yes" if r.get("v7_detected") else "No",
                str(r.get("v7_delay_min")) if r.get("v7_delay_min") is not None else "-",
                "Yes" if r.get("lstm_v8_detected") else "No",
                str(r.get("lstm_delay_min")) if r.get("lstm_delay_min") is not None else "-",
                "Yes" if r.get("telemetry_detected") else "No",
                str(r.get("telemetry_delay_min")) if r.get("telemetry_delay_min") is not None else "-",
            ]
            for r in ev.get("experiment_results", [])
        ]
        summary["evaluation_summary"] = ev.get("detector_evaluation", {})
        summary["experiments_total"] = ev.get("experiments_total", 0)
    elif report_type == "performance_history":
        title = f"Historical Performance & Telemetry Report ({range_minutes}m Window)"
        hist = query_telemetry_history(range_minutes=range_minutes, limit=600)
        columns = [
            "Timestamp UTC",
            "Node",
            "Up",
            "CPU %",
            "IOWait %",
            "Memory %",
            "Load1",
            "Disk Write MB/s",
            "Net RX MB/s",
            "Disk IO %",
        ]
        rows = [
            [
                str(h.get("timestamp_utc", "")),
                str(h.get("node_id", "")),
                "ONLINE" if h.get("up", 1) == 1 else "OFFLINE",
                _fmt_num(h.get("cpu_percent"), 1),
                _fmt_num(h.get("iowait_percent"), 2),
                _fmt_num(h.get("memory_percent"), 1),
                _fmt_num(h.get("load1"), 2),
                _fmt_num(h.get("disk_write_mb"), 2),
                _fmt_num(h.get("net_rx_mb"), 2),
                _fmt_num(h.get("disk_io_percent"), 1),
            ]
            for h in hist
        ]
    else:
        title = "Executive Cluster Health & Infrastructure Summary"
        columns = [
            "Node",
            "IP Address",
            "Role",
            "Online",
            "Slurm State",
            "Status",
            "CPU %",
            "Memory %",
            "Load1",
            "Scratch %",
            "Alert Priority",
        ]
        rows = [
            [
                n.get("display_name") or n.get("node_id"),
                str(n.get("ip", "")),
                str(n.get("role", "")),
                "ONLINE" if n.get("up") == 1 else "OFFLINE",
                str(n.get("slurm_state", "")),
                str(n.get("health_classification", n.get("health_status", "Healthy"))),
                _fmt_num(n.get("cpu_utilization_percent"), 1),
                _fmt_num(n.get("memory_used_percent"), 1),
                _fmt_num(n.get("load1"), 2),
                _fmt_num(n.get("scratch_used_percent"), 1),
                str(n.get("alert_priority", "OK")),
            ]
            for n in nodes
        ]

    summary_metrics = {
        "generated_utc": now_iso,
        "data_source": snapshot.get("mode_label", snapshot.get("mode", "")),
        "cluster_status": kpis.get("cluster_status_label", "Healthy"),
        "nodes_online": f"{kpis.get('nodes_online', 0)}/{kpis.get('nodes_total', 0)}",
        "cluster_cpu_percent": kpis.get("cluster_cpu_percent"),
        "cluster_memory_percent": kpis.get("cluster_memory_percent"),
        "active_alerts": kpis.get("active_episodes_total", 0),
    }

    return {
        "report_type": report_type,
        "title": title,
        "generated_utc": now_iso,
        "summary": summary_metrics,
        "columns": columns,
        "rows": rows,
    }


def export_report_csv(report_payload: Dict[str, Any]) -> Tuple[bytes, str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["# Platform", "HPC Predictive Monitoring Dashboard"])
    writer.writerow(["# Report", report_payload["title"]])
    writer.writerow(["# Generated UTC", report_payload["generated_utc"]])
    summary = report_payload.get("summary", {})
    writer.writerow(
        [
            "# Summary",
            f"Nodes={summary.get('nodes_online')}",
            f"Status={summary.get('cluster_status')}",
            f"CPU={summary.get('cluster_cpu_percent')}%",
            f"Mem={summary.get('cluster_memory_percent')}%",
            f"ActiveAlerts={summary.get('active_alerts')}",
        ]
    )
    writer.writerow([])
    writer.writerow(report_payload["columns"])
    for row in report_payload["rows"]:
        writer.writerow(row)

    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"sol_plaatje_a_{report_payload['report_type']}_{ts_slug}.csv"
    return buf.getvalue().encode("utf-8"), filename


def export_report_pdf(report_payload: Dict[str, Any]) -> Tuple[bytes, str]:
    """
    Generate a clean, standalone multi-page PDF 1.4 document using built-in Type1 Helvetica fonts
    with zero external native dependencies.
    """
    title = _pdf_escape(report_payload["title"])
    gen_ts = _pdf_escape(report_payload["generated_utc"])
    summary = report_payload.get("summary", {})
    cols: List[str] = report_payload["columns"]
    rows: List[List[str]] = report_payload["rows"] or [["No records in selected window"]]

    # Format fixed-width tabular lines so they align cleanly in Courier/Helvetica
    col_widths = [max(len(str(c)), 8) for c in cols]
    for r in rows[:220]:
        for idx, cell in enumerate(r[: len(cols)]):
            col_widths[idx] = min(24, max(col_widths[idx], len(str(cell))))

    def _fmt_table_line(cells: List[str]) -> str:
        padded = []
        for idx, w in enumerate(col_widths):
            txt = str(cells[idx]) if idx < len(cells) else ""
            if len(txt) > w:
                txt = txt[: w - 1] + "~"
            padded.append(txt.ljust(w))
        return "  ".join(padded)[:112]

    header_line = _fmt_table_line(cols)
    sep_line = "-" * len(header_line)
    body_lines = [_fmt_table_line(r) for r in rows[:220]]

    # Paginate at 40 table rows per landscape-style page
    pages_lines: List[List[str]] = []
    chunk_size = 38
    for i in range(0, max(1, len(body_lines)), chunk_size):
        pages_lines.append(body_lines[i : i + chunk_size])

    pdf_bytes = _render_simple_pdf(
        title=title,
        subtitle=f"Sol Plaatje University | Generated {gen_ts} | Source: {_pdf_escape(str(summary.get('data_source', '')))}",
        kpi_line=(
            f"Cluster Status: {summary.get('cluster_status')}   |   "
            f"Nodes Online: {summary.get('nodes_online')}   |   "
            f"CPU: {summary.get('cluster_cpu_percent')}%   |   "
            f"Memory: {summary.get('cluster_memory_percent')}%   |   "
            f"Active Alerts: {summary.get('active_alerts')}"
        ),
        table_header=header_line,
        table_sep=sep_line,
        paginated_rows=pages_lines,
    )
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"sol_plaatje_a_{report_payload['report_type']}_{ts_slug}.pdf"
    return pdf_bytes, filename


def _pdf_escape(text: str) -> str:
    ascii_safe = (text or "").encode("ascii", errors="replace").decode("ascii")
    return ascii_safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render_simple_pdf(
    title: str,
    subtitle: str,
    kpi_line: str,
    table_header: str,
    table_sep: str,
    paginated_rows: List[List[str]],
) -> bytes:
    """Construct a valid PDF 1.4 binary with dark navy header banner and Courier data table."""
    objects: List[bytes] = []

    def _add_obj(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    # 1: Catalog, 2: Pages placeholder, 3: Helvetica-Bold, 4: Helvetica, 5: Courier
    _add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    _add_obj(b"")  # placeholder for Pages
    font_bold = _add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    font_reg = _add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_mono = _add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    page_obj_ids: List[int] = []
    total_pages = len(paginated_rows)

    for page_idx, page_rows in enumerate(paginated_rows, start=1):
        cmds = [
            # Dark Navy Header Banner
            "0.04 0.08 0.16 rg",
            "0 540 842 55 re f",
            # Cyan accent stripe
            "0.02 0.71 0.83 rg",
            "0 538 842 2 re f",
            # Header Title
            "1 1 1 rg",
            f"BT /F1 15 Tf 32 568 Td ({title}) Tj ET",
            "0.75 0.85 0.95 rg",
            f"BT /F2 9 Tf 32 551 Td ({subtitle}   [Page {page_idx}/{total_pages}]) Tj ET",
            # KPI Summary Box
            "0.94 0.96 0.99 rg",
            "32 504 778 24 re f",
            "0.08 0.15 0.28 rg",
            f"BT /F1 9 Tf 40 513 Td ({_pdf_escape(kpi_line)}) Tj ET",
            # Table Header
            "0.05 0.10 0.20 rg",
            f"BT /F3 7.5 Tf 32 486 Td ({_pdf_escape(table_header)}) Tj ET",
            f"BT /F3 7.5 Tf 32 476 Td ({_pdf_escape(table_sep)}) Tj ET",
        ]
        y = 464
        for row_str in page_rows:
            cmds.append(f"BT /F3 7.3 Tf 32 {y} Td ({_pdf_escape(row_str)}) Tj ET")
            y -= 11

        stream_bytes = "\n".join(cmds).encode("ascii", errors="replace")
        content_id = _add_obj(
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream"
        )
        page_id = _add_obj(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
            f"/Resources << /Font << /F1 {font_bold} 0 R /F2 {font_reg} 0 R /F3 {font_mono} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode("ascii")
        )
        page_obj_ids.append(page_id)

    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n")
    offsets: List[int] = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def _fmt_num(val: Any, digits: int = 1) -> str:
    if val is None or val == "":
        return "N/A"
    try:
        return f"{float(val):.{digits}f}"
    except Exception:
        return "N/A"

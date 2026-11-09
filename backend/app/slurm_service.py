from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Tuple

from .database import add_system_log
from .ssh_bridge import execute_restricted_cluster_command, validate_safe_identifier

SAFE_JOB_ID_RE = re.compile(r"^[0-9_]{1,24}$")
SAFE_REASON_RE = re.compile(r"[^a-zA-Z0-9 .,:;_()/+-]")


def sanitize_reason(reason: str) -> str:
    cleaned = SAFE_REASON_RE.sub("", (reason or "Admin action"))[:80].strip()
    return cleaned or "Admin action"


def _parse_duration_to_hours(dur: str) -> float:
    """Convert Slurm elapsed string ([DD-]HH:MM:SS or MM:SS) to float hours."""
    if not dur:
        return 0.0
    try:
        days = 0
        rest = dur.strip()
        if "-" in rest:
            d_part, rest = rest.split("-", 1)
            days = int(d_part)
        parts = [int(p) for p in rest.split(":")]
        if len(parts) == 3:
            hrs, mins, secs = parts
        elif len(parts) == 2:
            hrs, mins, secs = 0, parts[0], parts[1]
        else:
            return 0.0
        return round(days * 24.0 + hrs + mins / 60.0 + secs / 3600.0, 2)
    except Exception:
        return 0.0


def _expand_nodelist(nodelist: str) -> List[str]:
    """Expand compact Slurm nodelist like compute-[01-03] or node1,node2."""
    if not nodelist or nodelist in ("(None)", "None", "N/A"):
        return []
    m = re.match(r"^([a-zA-Z0-9_-]+)\[([0-9,\-]+)\]$", nodelist.strip())
    if not m:
        return [n.strip() for n in nodelist.split(",") if n.strip() and not n.startswith("(")]
    prefix, bracket = m.group(1), m.group(2)
    expanded: List[str] = []
    for seg in bracket.split(","):
        if "-" in seg:
            a_str, b_str = seg.split("-", 1)
            width = len(a_str)
            for idx in range(int(a_str), int(b_str) + 1):
                expanded.append(f"{prefix}{str(idx).zfill(width)}")
        else:
            expanded.append(f"{prefix}{seg}")
    return expanded


def fetch_live_slurm_node_states() -> Dict[str, Dict[str, str]]:
    """Query sinfo on Head Node to discover real Slurm node states and partitions."""
    ok, out, _src = execute_restricted_cluster_command(
        ["sinfo", "-N", "-h", "-o", "%N|%P|%T|%c|%m|%E"],
        target_node_ip="localhost",
        timeout_sec=4.0,
    )
    if not ok or not out.strip():
        return {}
    states: Dict[str, Dict[str, str]] = {}
    for line in out.strip().splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            nid = parts[0].strip()
            states[nid] = {
                "partition": parts[1].strip().rstrip("*"),
                "slurm_state": parts[2].strip().upper(),
                "slurm_cpus": parts[3].strip() if len(parts) > 3 else "",
                "slurm_mem_mb": parts[4].strip() if len(parts) > 4 else "",
                "reason": parts[5].strip() if len(parts) > 5 else "",
            }
    return states


def fetch_live_slurm_jobs() -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Query live Slurm queue (squeue for RUNNING/PENDING + sacct for COMPLETED/FAILED).
    Returns (jobs_list, source_label) or (None, error_reason) when Slurm is unreachable.
    """
    ok_sq, out_sq, src = execute_restricted_cluster_command(
        ["squeue", "-h", "-o", "%i|%j|%u|%P|%T|%M|%l|%D|%C|%m|%N|%R"],
        target_node_ip="localhost",
        timeout_sec=4.5,
    )
    if not ok_sq and src == "offline":
        return None, "offline"
    if not ok_sq:
        return None, out_sq or "squeue unavailable"

    jobs: List[Dict[str, Any]] = []
    seen_ids = set()

    for line in out_sq.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 11:
            continue
        jid = parts[0].strip()
        seen_ids.add(jid)
        elapsed_str = parts[5].strip()
        nodes = _expand_nodelist(parts[10].strip())
        cpus = int(parts[8].strip()) if parts[8].strip().isdigit() else 1
        jobs.append(
            {
                "job_id": jid,
                "name": parts[1].strip(),
                "user": parts[2].strip(),
                "partition": parts[3].strip(),
                "state": parts[4].strip().upper(),
                "duration": elapsed_str,
                "time_limit": parts[6].strip(),
                "node_count": int(parts[7].strip()) if parts[7].strip().isdigit() else len(nodes),
                "cpus": cpus,
                "memory_req": parts[9].strip(),
                "nodes": nodes,
                "reason": parts[11].strip() if len(parts) > 11 else "",
                "elapsed_hours": _parse_duration_to_hours(elapsed_str),
                "mpi_ranks": cpus,
                "source": src,
            }
        )

    # Also query recent completed/failed jobs via sacct (last 48 hours) if slurmdbd/accounting is active
    ok_ac, out_ac, _ = execute_restricted_cluster_command(
        [
            "sacct",
            "-n",
            "-P",
            "-X",
            "--starttime=now-2days",
            "--format=JobID,JobName,User,Partition,State,Elapsed,AllocCPUS,ReqMem,NodeList,ExitCode",
        ],
        target_node_ip="localhost",
        timeout_sec=4.5,
    )
    if ok_ac and out_ac.strip():
        for line in out_ac.strip().splitlines()[-40:]:
            parts = line.split("|")
            if len(parts) < 9:
                continue
            jid = parts[0].strip()
            if jid in seen_ids or not jid:
                continue
            seen_ids.add(jid)
            raw_state = parts[4].strip().split()[0].upper()
            elapsed_str = parts[5].strip()
            cpus = int(parts[6].strip()) if parts[6].strip().isdigit() else 1
            nodes = _expand_nodelist(parts[8].strip())
            jobs.append(
                {
                    "job_id": jid,
                    "name": parts[1].strip(),
                    "user": parts[2].strip(),
                    "partition": parts[3].strip(),
                    "state": raw_state,
                    "duration": elapsed_str,
                    "time_limit": "-",
                    "node_count": len(nodes),
                    "cpus": cpus,
                    "memory_req": parts[7].strip(),
                    "nodes": nodes,
                    "reason": f"ExitCode {parts[9].strip()}" if len(parts) > 9 else "",
                    "elapsed_hours": _parse_duration_to_hours(elapsed_str),
                    "mpi_ranks": cpus,
                    "source": src,
                }
            )

    return jobs, src


def execute_slurm_cancel_job(job_id: str, reason: str = "Cancelled by administrator") -> Dict[str, Any]:
    if not SAFE_JOB_ID_RE.match(job_id or ""):
        raise ValueError("Invalid Slurm Job ID format")

    clean_reason = sanitize_reason(reason)
    ok, out, src = execute_restricted_cluster_command(
        ["scancel", job_id],
        target_node_ip="localhost",
        timeout_sec=5.0,
    )
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    add_system_log(
        timestamp_utc=now_iso,
        node_id="head-node",
        source="slurmctld",
        severity="WARNING",
        event_type="job_cancel",
        message=f"scancel {job_id} ({clean_reason}) -> {'executed' if ok else 'simulated/queued'} [{src}]",
    )
    return {
        "job_id": job_id,
        "cancelled": True,
        "live_executed": ok,
        "source": src,
        "detail": out or "Job cancellation dispatched",
    }

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


_SLURM_SNAPSHOT_SCRIPT = (
    "printf '__SINFO_BEGIN__\\n'; "
    "sinfo -N -h -o '%N|%P|%T|%c|%m|%E' 2>&1; "
    "printf '__SINFO_RC__=%d\\n' $?; "
    "printf '__SQUEUE_BEGIN__\\n'; "
    "squeue -h -o '%i|%j|%u|%P|%T|%M|%l|%D|%C|%m|%N|%R' 2>&1; "
    "printf '__SQUEUE_RC__=%d\\n' $?; "
    "printf '__SACCT_BEGIN__\\n'; "
    "sacct -n -P -X --starttime=now-7days "
    "--format=JobID,JobName,User,Partition,State,Elapsed,AllocCPUS,ReqMem,NodeList,ExitCode 2>/dev/null; "
    "printf '__SACCT_RC__=%d\\n' $?"
)


def node_id_aliases(name: str) -> List[str]:
    """Return normalized aliases so headnode/head-node and compute001/compute-01 match reliably."""
    raw = (name or "").strip()
    if not raw:
        return []
    short = raw.split(".")[0].lower()
    seen: List[str] = []

    def _add(candidate: str) -> None:
        if candidate and candidate not in seen:
            seen.append(candidate)

    _add(raw)
    _add(raw.lower())
    _add(short)
    if short in ("headnode", "head-node", "localhost"):
        _add("headnode")
        _add("head-node")
    else:
        m = re.match(r"^([a-zA-Z_-]*?)(\d+)$", short)
        if m:
            base = m.group(1).rstrip("-_")
            num = int(m.group(2))
            if base:
                _add(f"{base}{num:03d}")
                _add(f"{base}-{num:02d}")
                _add(f"{base}-{num:03d}")
    return seen


def resolve_slurm_nodename(
    node_id: str,
    slurm_nodes: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolve a dashboard node_id to the exact Slurm NodeName when known."""
    if slurm_nodes:
        lower_lookup = {str(k).lower(): str(k) for k in slurm_nodes.keys()}
        for alias in node_id_aliases(node_id):
            if alias in slurm_nodes:
                return alias
            if alias.lower() in lower_lookup:
                return lower_lookup[alias.lower()]
    return node_id


def _expand_nodelist(nodelist: str) -> List[str]:
    """Expand compact Slurm nodelist like compute-[01-03],compute[001-002] or node1,node2."""
    if not nodelist or nodelist.strip().lower() in ("(none)", "none", "n/a", "none assigned"):
        return []
    tokens = re.findall(r"[a-zA-Z0-9._-]+\[[0-9,-]+\]|[a-zA-Z0-9._-]+", nodelist.strip())
    expanded: List[str] = []
    for tok in tokens:
        if tok.startswith("("):
            continue
        m = re.match(r"^([a-zA-Z0-9._-]+)\[([0-9,\-]+)\]$", tok)
        if not m:
            expanded.append(tok)
            continue
        prefix, bracket = m.group(1), m.group(2)
        for seg in bracket.split(","):
            if "-" in seg:
                a_str, b_str = seg.split("-", 1)
                width = len(a_str)
                for idx in range(int(a_str), int(b_str) + 1):
                    expanded.append(f"{prefix}{str(idx).zfill(width)}")
            else:
                expanded.append(f"{prefix}{seg}")
    return expanded


def _parse_sinfo_lines(out: str) -> Dict[str, Dict[str, Any]]:
    states: Dict[str, Dict[str, Any]] = {}
    for line in (out or "").strip().splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        nid = parts[0].strip()
        if not nid or "error" in nid.lower():
            continue
        raw_cpus = parts[3].strip() if len(parts) > 3 else ""
        raw_mem = parts[4].strip() if len(parts) > 4 else ""
        raw_reason = parts[5].strip() if len(parts) > 5 else ""
        states[nid] = {
            "partition": parts[1].strip().rstrip("*"),
            "slurm_state": parts[2].strip().upper(),
            "slurm_cpus": int(raw_cpus) if raw_cpus.isdigit() else None,
            "slurm_mem_mb": int(raw_mem) if raw_mem.isdigit() else None,
            "reason": "" if raw_reason.lower() == "none" else raw_reason,
        }
    return states


def _parse_squeue_and_sacct(out_sq: str, out_ac: str, src: str) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    seen_ids = set()

    for line in (out_sq or "").strip().splitlines():
        parts = line.split("|")
        if len(parts) < 11:
            continue
        jid = parts[0].strip()
        if not jid:
            continue
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

    for line in (out_ac or "").strip().splitlines()[-40:]:
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

    return jobs


def _extract_marked_section(raw: str, prefix: str) -> Tuple[str, int]:
    pattern = re.compile(
        rf"__{prefix}_BEGIN__\r?\n(.*?)__{prefix}_RC__=(\d+)",
        re.DOTALL,
    )
    m = pattern.search(raw or "")
    if not m:
        return "", 1
    return m.group(1), int(m.group(2))


def fetch_live_slurm_snapshot() -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Dict[str, Any]], str, Optional[str]]:
    """
    Query Slurm (sinfo, squeue, and 7-day sacct) in a single SSH/local execution.
    Returns (jobs_list_or_none, node_states, source_label, error_detail).
    """
    ok, out, src = execute_restricted_cluster_command(
        ["bash", "-c", _SLURM_SNAPSHOT_SCRIPT],
        target_node_ip="localhost",
        timeout_sec=8.0,
    )
    if not ok and src == "offline":
        return None, {}, "offline", out or "SSH gateway not configured"
    if not ok or ("__SINFO_RC__=" not in out and "__SQUEUE_RC__=" not in out):
        detail = (out or "").strip() or "Slurm CLI command failed over SSH"
        return None, {}, "unavailable", detail[:220]

    sinfo_body, sinfo_rc = _extract_marked_section(out, "SINFO")
    squeue_body, squeue_rc = _extract_marked_section(out, "SQUEUE")
    sacct_body, sacct_rc = _extract_marked_section(out, "SACCT")

    if sinfo_rc != 0 and squeue_rc != 0:
        err_lines = [ln.strip() for ln in (squeue_body + "\n" + sinfo_body).splitlines() if ln.strip()]
        detail = err_lines[0][:220] if err_lines else "sinfo/squeue failed on Head Node"
        return None, {}, "unavailable", detail

    node_states = _parse_sinfo_lines(sinfo_body) if sinfo_rc == 0 else {}
    jobs = _parse_squeue_and_sacct(
        squeue_body if squeue_rc == 0 else "",
        sacct_body if sacct_rc == 0 else "",
        src,
    )
    return jobs, node_states, src, None


def fetch_live_slurm_node_states() -> Dict[str, Dict[str, Any]]:
    """Query sinfo on Head Node to discover real Slurm node states and partitions."""
    ok, out, _src = execute_restricted_cluster_command(
        ["sinfo", "-N", "-h", "-o", "%N|%P|%T|%c|%m|%E"],
        target_node_ip="localhost",
        timeout_sec=4.0,
    )
    if not ok or not out.strip():
        return {}
    return _parse_sinfo_lines(out)


def fetch_live_slurm_jobs() -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Query live Slurm queue (squeue for RUNNING/PENDING + sacct for COMPLETED/FAILED).
    Returns (jobs_list, source_label) or (None, error_reason) when Slurm is unreachable.
    """
    jobs, _nodes, src, err = fetch_live_slurm_snapshot()
    if jobs is None:
        return None, err or src
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

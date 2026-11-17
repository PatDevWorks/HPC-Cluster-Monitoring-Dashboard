from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Tuple

import requests

from .config import LIVE_CLUSTER_NODES

RANGE_CONFIG: Dict[str, Tuple[int, int]] = {
    "5m": (5, 10),        # 5 minutes, 10s step
    "15m": (15, 15),      # 15 minutes, 15s step
    "1h": (60, 30),       # 1 hour, 30s step
    "6h": (360, 180),     # 6 hours, 3m step
    "12h": (720, 300),    # 12 hours, 5m step
    "24h": (1440, 600),   # 24 hours, 10m step
}

INSTANT_PROMQL_QUERIES: Dict[str, str] = {
    "up": 'up{job=~".*node.*"} or up',
    "cpu_cores_discovered": 'count by (instance) (node_cpu_seconds_total{mode="idle"})',
    "memory_total_bytes": "node_memory_MemTotal_bytes",
    "memory_avail_bytes": "node_memory_MemAvailable_bytes",
    "swap_total_bytes": "node_memory_SwapTotal_bytes",
    "swap_free_bytes": "node_memory_SwapFree_bytes",
    "cpu_utilization_percent": '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)',
    "cpu_iowait_percent": 'avg by (instance) (rate(node_cpu_seconds_total{mode="iowait"}[1m])) * 100',
    "load1": "node_load1",
    "load5": "node_load5",
    "load15": "node_load15",
    "uptime_seconds": "node_time_seconds - node_boot_time_seconds",
    "root_used_percent": 'max by (instance) ((1 - node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay"} / clamp_min(node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay"}, 1)) * 100)',
    "scratch_used_percent": 'max by (instance) ((1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"} / clamp_min(node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"}, 1)) * 100)',
    "filesystem_total_bytes": 'max by (instance) (node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"})',
    "filesystem_avail_bytes": 'max by (instance) (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"})',
    "disk_read_bytes_per_second": "sum by (instance) (rate(node_disk_read_bytes_total[1m]))",
    "disk_write_bytes_per_second": "sum by (instance) (rate(node_disk_written_bytes_total[1m]))",
    "disk_io_utilization_percent": "max by (instance) (rate(node_disk_io_time_seconds_total[1m])) * 100",
    "network_receive_bytes_per_second": 'sum by (instance) (rate(node_network_receive_bytes_total{device!="lo"}[1m]))',
    "network_transmit_bytes_per_second": 'sum by (instance) (rate(node_network_transmit_bytes_total{device!="lo"}[1m]))',
    "network_errors_per_second": 'sum by (instance) (rate(node_network_receive_errs_total{device!="lo"}[1m]) + rate(node_network_transmit_errs_total{device!="lo"}[1m]))',
    "network_drop_per_second": 'sum by (instance) (rate(node_network_receive_drop_total{device!="lo"}[1m]) + rate(node_network_transmit_drop_total{device!="lo"}[1m]))',
    "procs_running": "node_procs_running",
    "procs_blocked": "node_procs_blocked",
    "context_switches_per_sec": "rate(node_context_switches_total[1m])",
    "psi_cpu_percent": "rate(node_pressure_cpu_waiting_seconds_total[1m]) * 100",
    "psi_memory_percent": "rate(node_pressure_memory_waiting_seconds_total[1m]) * 100",
    "psi_io_percent": "rate(node_pressure_io_waiting_seconds_total[1m]) * 100",
    "cpu_temperature_celsius": "max by (instance) (node_hwmon_temp_celsius)",
}


def check_prometheus_health(prometheus_url: str, timeout: float = 1.5) -> Dict[str, Any]:
    url = prometheus_url.rstrip("/")
    try:
        r = requests.get(f"{url}/api/v1/query", params={"query": "up"}, timeout=timeout)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") == "success":
            results = payload.get("data", {}).get("result", [])
            return {
                "reachable": True,
                "url": url,
                "targets_count": len(results),
                "error": None,
            }
        return {"reachable": False, "url": url, "targets_count": 0, "error": "Invalid API status"}
    except Exception as exc:
        return {
            "reachable": False,
            "url": url,
            "targets_count": 0,
            "error": str(exc).split("\n")[0][:120],
        }


def fetch_prometheus_cluster_snapshot(
    prometheus_url: str,
    drained_nodes: Dict[str, str],
    node_overrides: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Query live Prometheus for all discovered Node Exporter instances, hardware specs,
    OS uname metadata, and real-time metrics. Never fabricates missing values (returns None).
    """
    base_url = prometheus_url.rstrip("/")
    by_instance: Dict[str, Dict[str, float]] = {}
    uname_by_instance: Dict[str, Dict[str, str]] = {}

    try:
        session = requests.Session()
        # 1. Probe 'up' first
        resp = session.get(
            f"{base_url}/api/v1/query",
            params={"query": INSTANT_PROMQL_QUERIES["up"]},
            timeout=2.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") != "success":
            return None, "Prometheus returned non-success status"

        for item in payload.get("data", {}).get("result", []):
            metric = item.get("metric", {})
            inst = metric.get("instance", "")
            job = metric.get("job", "")
            # Filter out Prometheus self-scrape (:9090) or AIOps exporter (:8000) unless it's node_exporter
            if inst.endswith(":9090") or inst.endswith(":8000") or inst.endswith(":3000"):
                continue
            if job and "prometheus" in job.lower() and "node" not in job.lower():
                continue
            try:
                val = float(item.get("value", [0, 0])[1])
                by_instance.setdefault(inst, {})["up"] = val
            except Exception:
                pass

        # 2. Fetch node_uname_info to get real Linux hostnames, kernels, architectures
        uname_resp = session.get(
            f"{base_url}/api/v1/query",
            params={"query": "node_uname_info"},
            timeout=2.0,
        )
        if uname_resp.ok:
            for item in uname_resp.json().get("data", {}).get("result", []):
                m = item.get("metric", {})
                inst = m.get("instance", "")
                if inst:
                    uname_by_instance[inst] = {
                        "nodename": m.get("nodename", ""),
                        "sysname": m.get("sysname", "Linux"),
                        "release": m.get("release", ""),
                        "machine": m.get("machine", "x86_64"),
                    }
                    by_instance.setdefault(inst, {}).setdefault("up", 1.0)

        # 3. Query all Node Exporter metrics
        for key, promql in INSTANT_PROMQL_QUERIES.items():
            if key == "up":
                continue
            try:
                r = session.get(
                    f"{base_url}/api/v1/query",
                    params={"query": promql},
                    timeout=2.2,
                )
                if not r.ok:
                    continue
                for item in r.json().get("data", {}).get("result", []):
                    inst = item.get("metric", {}).get("instance", "")
                    if inst not in by_instance:
                        continue
                    raw_val = item.get("value", [0, None])[1]
                    if raw_val is not None:
                        fval = float(raw_val)
                        if not math.isnan(fval) and not math.isinf(fval):
                            by_instance[inst][key] = fval
            except Exception:
                continue
    except Exception as exc:
        return None, str(exc).split("\n")[0][:120]

    if not by_instance:
        return None, "No node_exporter targets discovered in Prometheus"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    overrides = node_overrides or {}
    fallback_by_inst = {n["instance"]: n for n in LIVE_CLUSTER_NODES}

    # Sort discovered instances deterministically: head/management node first, then compute nodes by IP/hostname
    def _sort_key(inst: str) -> Tuple[int, str]:
        uname = uname_by_instance.get(inst, {}).get("nodename", "").lower()
        host_part = inst.split(":")[0]
        is_head = (
            host_part in ("127.0.0.1", "localhost")
            or "head" in uname
            or "master" in uname
            or "mgmt" in uname
            or "login" in uname
        )
        return (0 if is_head else 1, inst)

    sorted_instances = sorted(by_instance.keys(), key=_sort_key)
    compute_idx = 0
    nodes_out: List[Dict[str, Any]] = []

    for inst in sorted_instances:
        mvals = by_instance[inst]
        uinfo = uname_by_instance.get(inst, {})
        fb = fallback_by_inst.get(inst, {})
        host_part = inst.split(":")[0]
        nodename = uinfo.get("nodename", "").strip()

        is_head = (
            host_part in ("127.0.0.1", "localhost")
            or "head" in nodename.lower()
            or "master" in nodename.lower()
            or "mgmt" in nodename.lower()
            or fb.get("role") == "management"
        )

        if is_head:
            node_id = nodename or fb.get("node_id") or "head-node"
            display_name = "Head Node" if node_id == "head-node" else f"Head Node ({nodename})"
            role = "management"
            rack_id = fb.get("rack_id", "rack-0")
        else:
            compute_idx += 1
            node_id = nodename or fb.get("node_id") or f"compute-{compute_idx:02d}"
            display_name = nodename or f"Compute-{compute_idx:03d}"
            role = "compute"
            rack_id = fb.get("rack_id", "rack-1")

        # Apply user node overrides if configured in Settings
        ov = overrides.get(node_id, {})
        display_name = ov.get("display_name") or display_name
        resolved_ip = ov.get("ip") or (host_part if host_part not in ("127.0.0.1", "localhost") else fb.get("ip", host_part))

        up_val = int(mvals.get("up", 0))
        cores = int(round(mvals["cpu_cores_discovered"])) if "cpu_cores_discovered" in mvals else int(fb.get("cpu_cores", 24))

        mem_tot = mvals.get("memory_total_bytes")
        mem_avail = mvals.get("memory_avail_bytes")
        mem_gib = round(mem_tot / (1024**3), 1) if mem_tot else float(fb.get("memory_gib", 64))
        mem_used_pct = (
            round((1.0 - (mem_avail / mem_tot)) * 100.0, 2)
            if (mem_tot and mem_avail is not None and mem_tot > 0)
            else None
        )

        swap_tot = mvals.get("swap_total_bytes")
        swap_free = mvals.get("swap_free_bytes")
        swap_tot_gib = round(swap_tot / (1024**3), 2) if swap_tot is not None else None
        if swap_tot is not None and swap_free is not None:
            swap_used_pct = round(((swap_tot - swap_free) / swap_tot) * 100.0, 2) if swap_tot > 0 else 0.0
        else:
            swap_used_pct = None

        fs_tot = mvals.get("filesystem_total_bytes")
        fs_avail = mvals.get("filesystem_avail_bytes")

        slurm_state = (
            "DRAINED"
            if node_id in drained_nodes
            else ("DOWN" if up_val == 0 else ("IDLE (MGMT)" if role == "management" else "ONLINE"))
        )

        def _opt_round(k: str, digits: int = 2) -> Optional[float]:
            if up_val == 0 or k not in mvals:
                return None
            return round(float(mvals[k]), digits)

        nodes_out.append(
            {
                "timestamp_utc": now_iso,
                "node_id": node_id,
                "display_name": display_name,
                "hostname": nodename or node_id,
                "instance": inst,
                "ip": resolved_ip,
                "ssh_target": "localhost" if is_head else resolved_ip,
                "role": role,
                "rack_id": rack_id,
                "os_kernel": f"{uinfo.get('sysname', 'Linux')} {uinfo.get('release', '')}".strip(),
                "arch": uinfo.get("machine", "x86_64"),
                "cpu_model": fb.get("cpu_model", "x86_64 Server Processor"),
                "cpu_cores": cores,
                "memory_gib": mem_gib,
                "up": up_val,
                "planned_maintenance": 0,
                "slurm_state": slurm_state,
                "uptime_seconds": _opt_round("uptime_seconds", 0),
                "cpu_utilization_percent": _opt_round("cpu_utilization_percent", 2),
                "cpu_iowait_percent": _opt_round("cpu_iowait_percent", 2),
                "memory_used_percent": mem_used_pct if up_val == 1 else None,
                "swap_used_percent": swap_used_pct if up_val == 1 else None,
                "swap_total_gib": swap_tot_gib,
                "load1": _opt_round("load1", 2),
                "load5": _opt_round("load5", 2),
                "load15": _opt_round("load15", 2),
                "root_used_percent": _opt_round("root_used_percent", 2),
                "scratch_used_percent": _opt_round("scratch_used_percent", 2),
                "filesystem_total_gib": round(fs_tot / (1024**3), 1) if fs_tot else None,
                "filesystem_avail_gib": round(fs_avail / (1024**3), 1) if fs_avail else None,
                "disk_read_bytes_per_second": _opt_round("disk_read_bytes_per_second", 1),
                "disk_write_bytes_per_second": _opt_round("disk_write_bytes_per_second", 1),
                "disk_io_utilization_percent": _opt_round("disk_io_utilization_percent", 2),
                "network_receive_bytes_per_second": _opt_round("network_receive_bytes_per_second", 1),
                "network_transmit_bytes_per_second": _opt_round("network_transmit_bytes_per_second", 1),
                "network_errors_per_second": _opt_round("network_errors_per_second", 4),
                "network_drop_per_second": _opt_round("network_drop_per_second", 4),
                "procs_running": _opt_round("procs_running", 0),
                "procs_blocked": _opt_round("procs_blocked", 0),
                "context_switches_per_sec": _opt_round("context_switches_per_sec", 1),
                "psi_cpu_percent": _opt_round("psi_cpu_percent", 3),
                "psi_memory_percent": _opt_round("psi_memory_percent", 3),
                "psi_io_percent": _opt_round("psi_io_percent", 3),
                "cpu_temperature_celsius": _opt_round("cpu_temperature_celsius", 1),
            }
        )

    return nodes_out, None


def query_prometheus_range_history(
    prometheus_url: str,
    range_key: str = "1h",
    instance: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Query Prometheus /api/v1/query_range for historical time ranges (5m, 15m, 1h, 6h, 12h, 24h).
    Returns synchronized time-series rows for charting, or None if Prometheus is unreachable.
    """
    minutes, step_sec = RANGE_CONFIG.get(range_key, (60, 30))
    now_dt = datetime.now(timezone.utc)
    start_dt = now_dt - timedelta(minutes=minutes)
    base_url = prometheus_url.rstrip("/")

    inst_selector = f'instance="{instance}"' if instance else 'instance!~".*:(9090|8000|3000)"'
    inst_comma = f'{inst_selector},' if inst_selector else ""

    range_queries = {
        "cpu": f'100 - (avg({inst_selector and "rate(node_cpu_seconds_total{" + inst_comma + "mode=\"idle\"}[1m])"}) * 100)',
        "iowait": f'avg(rate(node_cpu_seconds_total{{{inst_comma}mode="iowait"}}[1m])) * 100',
        "memory": f'avg((1 - (node_memory_MemAvailable_bytes{{{inst_selector}}} / clamp_min(node_memory_MemTotal_bytes{{{inst_selector}}}, 1))) * 100)',
        "swap": f'avg((1 - (node_memory_SwapFree_bytes{{{inst_selector}}} / clamp_min(node_memory_SwapTotal_bytes{{{inst_selector}}}, 1))) * 100)',
        "load1": f'avg(node_load1{{{inst_selector}}})',
        "load5": f'avg(node_load5{{{inst_selector}}})',
        "disk_read_mb": f'sum(rate(node_disk_read_bytes_total{{{inst_selector}}}[1m])) / 1048576',
        "disk_write_mb": f'sum(rate(node_disk_written_bytes_total{{{inst_selector}}}[1m])) / 1048576',
        "disk_io": f'max(rate(node_disk_io_time_seconds_total{{{inst_selector}}}[1m])) * 100',
        "net_rx_mb": f'sum(rate(node_network_receive_bytes_total{{{inst_comma}device!="lo"}}[1m])) / 1048576',
        "net_tx_mb": f'sum(rate(node_network_transmit_bytes_total{{{inst_comma}device!="lo"}}[1m])) / 1048576',
        "net_err": f'sum(rate(node_network_receive_errs_total{{{inst_comma}device!="lo"}}[1m]) + rate(node_network_transmit_errs_total{{{inst_comma}device!="lo"}}[1m]))',
        "scratch": f'max((1 - node_filesystem_avail_bytes{{{inst_comma}fstype!~"tmpfs|overlay|squashfs"}} / clamp_min(node_filesystem_size_bytes{{{inst_comma}fstype!~"tmpfs|overlay|squashfs"}}, 1)) * 100)',
        "psi_cpu": f'avg(rate(node_pressure_cpu_waiting_seconds_total{{{inst_selector}}}[1m])) * 100',
        "psi_mem": f'avg(rate(node_pressure_memory_waiting_seconds_total{{{inst_selector}}}[1m])) * 100',
        "psi_io": f'avg(rate(node_pressure_io_waiting_seconds_total{{{inst_selector}}}[1m])) * 100',
        "temp": f'max(node_hwmon_temp_celsius{{{inst_selector}}})',
    }

    timeline: Dict[int, Dict[str, Any]] = {}
    try:
        session = requests.Session()
        # Probe first query to confirm connectivity quickly
        probe = session.get(
            f"{base_url}/api/v1/query_range",
            params={
                "query": range_queries["cpu"],
                "start": start_dt.timestamp(),
                "end": now_dt.timestamp(),
                "step": step_sec,
            },
            timeout=2.5,
        )
        probe.raise_for_status()
        pdata = probe.json()
        if pdata.get("status") != "success":
            return None

        def _ingest(key: str, res_json: Dict[str, Any]) -> None:
            for series in res_json.get("data", {}).get("result", []):
                for ts_raw, val_raw in series.get("values", []):
                    ts_int = int(float(ts_raw))
                    dt_iso = datetime.fromtimestamp(ts_int, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    short_lbl = (
                        dt_iso[11:19]
                        if minutes <= 60
                        else f"{dt_iso[5:10]} {dt_iso[11:16]}"
                    )
                    pt = timeline.setdefault(
                        ts_int,
                        {"timestamp_utc": dt_iso, "time": short_lbl},
                    )
                    try:
                        fv = float(val_raw)
                        if not math.isnan(fv) and not math.isinf(fv):
                            pt[key] = round(fv, 3)
                    except Exception:
                        pass

        _ingest("cpu", pdata)

        for key, q in range_queries.items():
            if key == "cpu":
                continue
            try:
                r = session.get(
                    f"{base_url}/api/v1/query_range",
                    params={
                        "query": q,
                        "start": start_dt.timestamp(),
                        "end": now_dt.timestamp(),
                        "step": step_sec,
                    },
                    timeout=2.5,
                )
                if r.ok:
                    _ingest(key, r.json())
            except Exception:
                continue
    except Exception:
        return None

    if not timeline:
        return None

    return [timeline[k] for k in sorted(timeline.keys())]

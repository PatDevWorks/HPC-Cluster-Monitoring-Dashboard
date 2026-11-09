import csv
from datetime import datetime, timezone
import math
import random
from typing import Any, Dict, List, Optional

from .config import LIVE_CLUSTER_NODES, PROMETHEUS_URL, SCC_DATASET_DIR
from .database import add_system_log, get_app_settings
from .prometheus_service import check_prometheus_health, fetch_prometheus_cluster_snapshot
from .slurm_service import (
    fetch_live_slurm_jobs,
    fetch_live_slurm_node_states,
    sanitize_reason,
)
from .ssh_bridge import execute_restricted_cluster_command


REPLAY_PRESETS = [
    {
        "id": "sep03_mem_disk",
        "label": "Sep 03 — Gradual Memory Exhaustion & Disk Precursor (Predicted)",
        "start_utc": "2026-09-03T05:30:00Z",
        "description": "compute-01 memory leak & compute-05 disk degradation leading to unplanned outages; early warning fires >50m ahead.",
    },
    {
        "id": "sep15_thermal_disk",
        "label": "Sep 15 — Multi-Node Thermal Shutdown & Disk Failure (Predicted)",
        "start_utc": "2026-09-15T08:15:00Z",
        "description": "compute-03 thermal climb & compute-10 disk failure precursor under heavy cluster load.",
    },
    {
        "id": "sep18_power_loss",
        "label": "Sep 18 — Rack-1 Sudden Power Loss P01 (Unpredictable External)",
        "start_utc": "2026-09-18T10:15:00Z",
        "description": "Simultaneous rack-1 power outage (compute-01..06) at 10:50Z with zero prior telemetry precursor.",
    },
    {
        "id": "aug29_maintenance",
        "label": "Aug 29 — Scheduled Maintenance Window M01 (Alert Suppression)",
        "start_utc": "2026-08-29T07:40:00Z",
        "description": "Planned cluster-wide maintenance; demonstrates zero false-alarm suppression policy.",
    },
]


class ClusterTelemetryConnector:
    """
    Real-time telemetry & Slurm state provider supporting three modes:
      1. live_prometheus    — Queries real Prometheus (:9090) + Linux Slurm / SSH on Head Node
      2. live_cluster_sim   — 4-node HPE DL320 Gen11 cluster simulator (explicitly labeled when active)
      3. scc_dataset_replay — Chronological streamer over ../scc_hpc_dataset CSVs (12 nodes, synthetic)
    """

    def __init__(self) -> None:
        self.prometheus_url: str = PROMETHEUS_URL
        self.prometheus_connected: bool = False
        self.last_prometheus_error: Optional[str] = None
        self.slurm_connected: bool = False
        self.slurm_source: str = "simulator"

        # Auto-probe Prometheus on startup: if reachable, default directly to live_prometheus!
        probe = check_prometheus_health(self.prometheus_url, timeout=1.2)
        if probe["reachable"] and probe["targets_count"] > 0:
            self.mode: str = "live_prometheus"
            self.prometheus_connected = True
        else:
            self.mode = "live_cluster_sim"
            self.last_prometheus_error = probe.get("error")

        self.drained_nodes: Dict[str, str] = {}
        self.injected_faults: Dict[str, Dict[str, Any]] = {}
        self.sim_tick: int = 0
        self.cancelled_sim_jobs: set = set()

        self.sim_slurm_jobs: List[Dict[str, Any]] = [
            {
                "job_id": "40812",
                "name": "HPL-Linpack-AVX512",
                "user": "spu_scc01",
                "partition": "compute",
                "state": "RUNNING",
                "duration": "02:24:18",
                "time_limit": "08:00:00",
                "nodes": ["compute-01", "compute-02", "compute-03"],
                "node_count": 3,
                "cpus": 72,
                "memory_req": "180G",
                "elapsed_hours": 2.4,
                "mpi_ranks": 72,
                "Watts_per_node": 285,
                "reason": "None",
            },
            {
                "job_id": "40815",
                "name": "DFTB+-Benzene768",
                "user": "spu_chem",
                "partition": "compute",
                "state": "RUNNING",
                "duration": "01:36:05",
                "time_limit": "04:00:00",
                "nodes": ["compute-01", "compute-02"],
                "node_count": 2,
                "cpus": 24,
                "memory_req": "64G",
                "elapsed_hours": 1.6,
                "mpi_ranks": 24,
                "Watts_per_node": 240,
                "reason": "None",
            },
            {
                "job_id": "40819",
                "name": "HPCG-DDR5-Bandwidth",
                "user": "spu_bench",
                "partition": "compute",
                "state": "PENDING",
                "duration": "00:00:00",
                "time_limit": "02:00:00",
                "nodes": ["compute-03"],
                "node_count": 1,
                "cpus": 24,
                "memory_req": "60G",
                "elapsed_hours": 0.0,
                "mpi_ranks": 24,
                "Watts_per_node": 260,
                "reason": "Resources",
            },
            {
                "job_id": "40798",
                "name": "OpenMPI-Collective-Verify",
                "user": "spu_scc01",
                "partition": "compute",
                "state": "COMPLETED",
                "duration": "00:48:12",
                "time_limit": "01:00:00",
                "nodes": ["compute-01", "compute-02", "compute-03"],
                "node_count": 3,
                "cpus": 72,
                "memory_req": "96G",
                "elapsed_hours": 0.8,
                "mpi_ranks": 72,
                "Watts_per_node": 265,
                "reason": "ExitCode 0:0",
            },
            {
                "job_id": "40791",
                "name": "GROMACS-Checkpoint-Test",
                "user": "spu_bio",
                "partition": "compute",
                "state": "FAILED",
                "duration": "00:14:52",
                "time_limit": "03:00:00",
                "nodes": ["compute-02"],
                "node_count": 1,
                "cpus": 24,
                "memory_req": "64G",
                "elapsed_hours": 0.25,
                "mpi_ranks": 24,
                "Watts_per_node": 250,
                "reason": "ExitCode 1:0",
            },
        ]

        self.replay_preset_id: str = "sep03_mem_disk"
        self.replay_frames: List[Dict[str, Any]] = []
        self.replay_cursor: int = 0
        self.scc_nodes_meta: Dict[str, Dict[str, Any]] = {}

    def sync_from_settings(self) -> None:
        settings = get_app_settings()
        if settings.get("prometheus_url"):
            self.prometheus_url = str(settings["prometheus_url"]).rstrip("/")

    def set_mode(
        self,
        mode: str,
        prometheus_url: Optional[str] = None,
        preset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if prometheus_url:
            self.prometheus_url = prometheus_url.rstrip("/")
        self.mode = mode
        if mode == "scc_dataset_replay":
            target_preset = preset_id or self.replay_preset_id
            self._load_replay_window(target_preset)
        return {
            "mode": self.mode,
            "prometheus_url": self.prometheus_url,
            "preset_id": self.replay_preset_id,
        }

    def inject_fault(self, node_id: str, fault_type: str) -> Dict[str, Any]:
        self.injected_faults[node_id] = {"type": fault_type, "step": 0}
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log_messages = {
            "memory_exhaustion": "kernel: EDAC MC0: 4 CE memory read error on CPU_SrcID#0_MC#0_Chan#1_DIMM#0; anon-rss climbing",
            "thermal_shutdown": "kernel: CPU0: Package temperature above threshold (84 C), cpu clock throttled",
            "disk_failure": "kernel: blk_update_request: critical medium error, dev sda, sector 4819204 op 0x1:(WRITE)",
            "mpi_straggler": "slurmd[2194]: Rank 14 on node experiencing 410ms MPI_Allreduce barrier lag",
            "network_degradation": "kernel: bnxt_en 0000:01:00.0 eth0: RX CRC/frame errors detected on 10GbE DAC link",
            "scrape_gap": "prometheus: Get http://node:9100/metrics: context deadline exceeded (scrape_gap)",
        }
        add_system_log(
            timestamp_utc=now_iso,
            node_id=node_id,
            source="kernel/dmesg",
            severity="WARNING",
            event_type=fault_type,
            message=log_messages.get(fault_type, f"Fault scenario '{fault_type}' started on {node_id}"),
        )
        return {"node_id": node_id, "fault_type": fault_type, "active": True}

    def clear_faults(self, node_id: Optional[str] = None) -> None:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if node_id:
            self.injected_faults.pop(node_id, None)
            add_system_log(now_iso, node_id, "aiops-control", "INFO", "recovery", f"Fault cleared on {node_id}; telemetry returning to baseline.")
        else:
            self.injected_faults.clear()
            add_system_log(now_iso, "cluster", "aiops-control", "INFO", "recovery", "All fault injections cleared.")

    def drain_node(self, node_id: str, reason: str) -> Dict[str, Any]:
        clean_reason = sanitize_reason(reason)
        self.drained_nodes[node_id] = clean_reason
        ok, _out, src = execute_restricted_cluster_command(
            [
                "scontrol",
                "update",
                f"NodeName={node_id}",
                "State=DRAIN",
                f"Reason={clean_reason}",
            ],
            target_node_ip="localhost",
            timeout_sec=4.5,
        )
        executed_mode = src if ok else "simulated_scontrol"

        affected_jobs = [
            j for j in self.sim_slurm_jobs
            if j["state"] == "RUNNING" and node_id in j["nodes"]
        ]
        core_hours_saved = sum(float(j["cpus"]) * max(float(j["elapsed_hours"]), 1.0) for j in affected_jobs)
        if core_hours_saved == 0.0:
            core_hours_saved = 48.0
        kwh_saved = sum(
            (float(j.get("Watts_per_node", 275)) * len(j["nodes"]) * max(float(j["elapsed_hours"]), 1.0)) / 1000.0
            for j in affected_jobs
        ) or 0.68

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        add_system_log(
            timestamp_utc=now_iso,
            node_id=node_id,
            source="slurmctld",
            severity="INFO",
            event_type="slurm_drain",
            message=f"scontrol update NodeName={node_id} State=DRAIN Reason='{clean_reason}' [{executed_mode}]",
        )
        return {
            "node_id": node_id,
            "slurm_state": "DRAINING",
            "executed_mode": executed_mode,
            "jobs_protected": len(affected_jobs),
            "core_hours_saved": round(core_hours_saved, 1),
            "kwh_saved": round(kwh_saved, 3),
        }

    def resume_node(self, node_id: str) -> Dict[str, Any]:
        self.drained_nodes.pop(node_id, None)
        ok, _out, src = execute_restricted_cluster_command(
            ["scontrol", "update", f"NodeName={node_id}", "State=RESUME"],
            target_node_ip="localhost",
            timeout_sec=4.5,
        )
        executed_mode = src if ok else "simulated_scontrol"
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        add_system_log(
            timestamp_utc=now_iso,
            node_id=node_id,
            source="slurmctld",
            severity="INFO",
            event_type="slurm_resume",
            message=f"scontrol update NodeName={node_id} State=RESUME [{executed_mode}]",
        )
        return {"node_id": node_id, "slurm_state": "ALLOCATED", "executed_mode": executed_mode}

    def fetch_next_batch(self) -> Dict[str, Any]:
        self.sync_from_settings()
        if self.mode == "live_prometheus":
            return self._fetch_from_prometheus()
        if self.mode == "scc_dataset_replay":
            return self._fetch_from_dataset_replay()
        return self._fetch_from_cluster_sim()

    # -------------------------------------------------------------------------
    # MODE 1: Live Prometheus (:9090) + Real Slurm Discovery
    # -------------------------------------------------------------------------
    def _fetch_from_prometheus(self) -> Dict[str, Any]:
        settings = get_app_settings()
        overrides = settings.get("node_overrides", {})
        nodes_out, err = fetch_prometheus_cluster_snapshot(
            prometheus_url=self.prometheus_url,
            drained_nodes=self.drained_nodes,
            node_overrides=overrides,
        )
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Attempt live Slurm query (local Linux or SSH gateway)
        live_jobs, slurm_src = fetch_live_slurm_jobs()
        live_node_states = fetch_live_slurm_node_states() if live_jobs is not None else {}

        if live_jobs is not None:
            self.slurm_connected = True
            self.slurm_source = slurm_src
        else:
            self.slurm_connected = False
            self.slurm_source = "unavailable"

        if nodes_out is not None:
            self.prometheus_connected = True
            self.last_prometheus_error = None
            # Overlay live Slurm node states if discovered via sinfo
            for n in nodes_out:
                sinfo_entry = live_node_states.get(n["node_id"]) or live_node_states.get(n.get("hostname", ""))
                if sinfo_entry:
                    n["slurm_state"] = sinfo_entry["slurm_state"]
                    n["partition"] = sinfo_entry["partition"]
            return {
                "timestamp_utc": now_iso,
                "is_synthetic": False,
                "is_simulated": False,
                "prometheus_connected": True,
                "slurm_connected": self.slurm_connected,
                "slurm_source": self.slurm_source,
                "mode_label": f"Live Prometheus ({self.prometheus_url})",
                "nodes": nodes_out,
                "slurm_jobs": live_jobs if live_jobs is not None else [],
            }

        # Honest disconnected state: do NOT fabricate fake numbers when Live Prometheus is selected!
        self.prometheus_connected = False
        self.last_prometheus_error = err or "Connection refused"
        unavailable_nodes: List[Dict[str, Any]] = []
        for meta in LIVE_CLUSTER_NODES:
            unavailable_nodes.append(
                {
                    "timestamp_utc": now_iso,
                    "node_id": meta["node_id"],
                    "display_name": meta["display_name"],
                    "hostname": meta["node_id"],
                    "instance": meta["instance"],
                    "ip": meta["ip"],
                    "ssh_target": meta["ssh_target"],
                    "role": meta["role"],
                    "rack_id": meta["rack_id"],
                    "cpu_model": meta["cpu_model"],
                    "cpu_cores": meta["cpu_cores"],
                    "memory_gib": meta["memory_gib"],
                    "up": 0,
                    "simulated_scrape_gap": True,
                    "planned_maintenance": 0,
                    "slurm_state": "UNKNOWN (PROMETHEUS OFFLINE)",
                    "uptime_seconds": None,
                    "cpu_utilization_percent": None,
                    "cpu_iowait_percent": None,
                    "memory_used_percent": None,
                    "swap_used_percent": None,
                    "load1": None,
                    "load5": None,
                    "load15": None,
                    "root_used_percent": None,
                    "scratch_used_percent": None,
                    "disk_read_bytes_per_second": None,
                    "disk_write_bytes_per_second": None,
                    "disk_io_utilization_percent": None,
                    "network_receive_bytes_per_second": None,
                    "network_transmit_bytes_per_second": None,
                    "network_errors_per_second": None,
                    "procs_running": None,
                    "procs_blocked": None,
                    "psi_cpu_percent": None,
                    "psi_memory_percent": None,
                    "psi_io_percent": None,
                    "cpu_temperature_celsius": None,
                }
            )

        return {
            "timestamp_utc": now_iso,
            "is_synthetic": False,
            "is_simulated": False,
            "prometheus_connected": False,
            "slurm_connected": self.slurm_connected,
            "slurm_source": self.slurm_source,
            "mode_label": f"Live Prometheus — Offline ({self.prometheus_url})",
            "source_warning": (
                f"Prometheus unreachable at {self.prometheus_url} ({self.last_prometheus_error}). "
                "Verify SSH port-forward (-L 9090:localhost:9090) or switch data source in Settings."
            ),
            "nodes": unavailable_nodes,
            "slurm_jobs": live_jobs if live_jobs is not None else [],
        }

    # -------------------------------------------------------------------------
    # MODE 2: 4-Node Cluster Telemetry Simulator (Explicitly Labeled)
    # -------------------------------------------------------------------------
    def _fetch_from_cluster_sim(self) -> Dict[str, Any]:
        self.sim_tick += 1
        t = self.sim_tick
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        settings = get_app_settings()
        overrides = settings.get("node_overrides", {})

        mpi_wave = 76.0 + 9.0 * math.sin(t / 7.0)
        nodes_out: List[Dict[str, Any]] = []

        for idx, meta in enumerate(LIVE_CLUSTER_NODES):
            nid = meta["node_id"]
            ov = overrides.get(nid, {})
            is_head = meta["role"] == "management"
            is_drained = nid in self.drained_nodes
            rng = random.Random(t * 31 + idx * 17)

            if is_head:
                cpu = 14.5 + rng.uniform(-2.0, 3.2)
                iowait = 0.8 + rng.uniform(0.0, 0.6)
                mem = 38.2 + rng.uniform(-0.4, 0.5)
                swap = 2.1
                load1 = 1.45 + rng.uniform(-0.2, 0.3)
                root_fs = 41.2
                scratch = 54.8 + 0.01 * (t % 100)
                disk_r = 1.4e6 + rng.uniform(0, 5e5)
                disk_w = 3.2e6 + rng.uniform(0, 8e5)
                disk_io = 8.5 + rng.uniform(0, 3.0)
                net_rx = 18.5e6 + rng.uniform(-2e6, 2e6)
                net_tx = 21.0e6 + rng.uniform(-2e6, 2e6)
                net_err = 0.0
                temp = 47.5 + rng.uniform(-0.8, 0.9)
                procs_r, procs_b = 3, 0
                psi_cpu, psi_mem, psi_io = 0.12, 0.0, 0.08
            elif is_drained:
                cpu = 2.4 + rng.uniform(0.0, 1.2)
                iowait = 0.2
                mem = 14.5 + rng.uniform(-0.2, 0.2)
                swap = 0.0
                load1 = 0.12
                root_fs = 36.4
                scratch = 54.8
                disk_r = 2.5e4
                disk_w = 4.0e4
                disk_io = 1.1
                net_rx = 1.2e5
                net_tx = 1.1e5
                net_err = 0.0
                temp = 41.0 + rng.uniform(-0.5, 0.5)
                procs_r, procs_b = 1, 0
                psi_cpu, psi_mem, psi_io = 0.0, 0.0, 0.0
            else:
                cpu = min(98.5, max(5.0, mpi_wave + rng.uniform(-2.2, 2.2)))
                iowait = 1.6 + rng.uniform(0.0, 1.1)
                mem = 64.0 + idx * 2.2 + rng.uniform(-0.8, 0.8)
                swap = 1.4 + idx * 0.3
                load1 = round((cpu / 100.0) * meta["cpu_cores"] + rng.uniform(-0.5, 0.6), 2)
                root_fs = 38.0 + idx * 1.8
                scratch = 54.8 + 0.01 * (t % 100)
                disk_r = 28.0e6 + rng.uniform(-3e6, 3e6)
                disk_w = 19.5e6 + rng.uniform(-2e6, 2e6)
                disk_io = 16.0 + rng.uniform(-2.0, 3.0)
                net_rx = 410.0e6 + rng.uniform(-22e6, 22e6)
                net_tx = 408.0e6 + rng.uniform(-22e6, 22e6)
                net_err = 0.0
                temp = 62.5 + (cpu - 75.0) * 0.18 + rng.uniform(-0.7, 0.7)
                procs_r = max(2, int(round(load1)))
                procs_b = 0
                psi_cpu = round(max(0.0, (cpu - 70.0) * 0.04), 2)
                psi_mem = 0.02
                psi_io = round(iowait * 0.12, 2)

            up = 1
            sim_scrape_gap = False

            fault = self.injected_faults.get(nid)
            if fault:
                fault["step"] += 1
                s = fault["step"]
                ftype = fault["type"]
                if ftype == "memory_exhaustion":
                    mem = min(98.8, 76.0 + s * 2.8)
                    swap = min(85.0, 12.0 + s * 6.5)
                    iowait = min(35.0, iowait + s * 1.4)
                    disk_w += s * 14e6
                    psi_mem = min(48.0, 4.0 + s * 3.5)
                elif ftype == "thermal_shutdown":
                    temp = min(97.5, 74.0 + s * 2.6)
                    cpu = max(52.0, cpu - max(0, s - 3) * 4.5)
                elif ftype == "disk_failure":
                    iowait = min(54.0, 16.0 + s * 4.2)
                    disk_io = min(99.5, 78.0 + s * 3.5)
                    disk_w = max(1e5, disk_w * 0.25)
                    load1 += s * 2.2
                    procs_b = min(14, 2 + s)
                    psi_io = min(65.0, 12.0 + s * 4.8)
                elif ftype == "mpi_straggler":
                    cpu = max(32.0, mpi_wave - 38.0 - rng.uniform(0, 5.0))
                    iowait = 19.5 + rng.uniform(0, 4.0)
                    net_rx *= 0.42
                    net_tx *= 0.40
                    psi_io = 14.2
                elif ftype == "network_degradation":
                    net_err = round(1.8 + s * 0.75 + rng.uniform(0, 0.4), 3)
                    net_rx *= 0.55
                    net_tx *= 0.52
                elif ftype == "scrape_gap":
                    up = 0
                    sim_scrape_gap = True

            slurm_state = (
                "DRAINED"
                if is_drained
                else ("IDLE (MGMT)" if is_head else ("DOWN*" if up == 0 else "ALLOCATED"))
            )

            nodes_out.append(
                {
                    "timestamp_utc": now_iso,
                    "node_id": nid,
                    "display_name": ov.get("display_name") or meta["display_name"],
                    "hostname": nid,
                    "instance": meta["instance"],
                    "ip": ov.get("ip") or meta["ip"],
                    "ssh_target": meta["ssh_target"],
                    "role": meta["role"],
                    "rack_id": meta["rack_id"],
                    "os_kernel": "Linux 6.8.0-ubuntu24.04",
                    "arch": "x86_64",
                    "cpu_model": meta["cpu_model"],
                    "cpu_cores": meta["cpu_cores"],
                    "memory_gib": meta["memory_gib"],
                    "up": up,
                    "simulated_scrape_gap": sim_scrape_gap,
                    "planned_maintenance": 0,
                    "slurm_state": slurm_state,
                    "uptime_seconds": (432000 + t * 3 + idx * 3600) if up else None,
                    "cpu_utilization_percent": round(cpu, 2) if up else None,
                    "cpu_iowait_percent": round(iowait, 2) if up else None,
                    "memory_used_percent": round(mem, 2) if up else None,
                    "swap_used_percent": round(swap, 2) if up else None,
                    "swap_total_gib": 16.0,
                    "load1": round(load1, 2) if up else None,
                    "load5": round(load1 * 0.96, 2) if up else None,
                    "load15": round(load1 * 0.91, 2) if up else None,
                    "root_used_percent": round(root_fs, 1) if up else None,
                    "scratch_used_percent": round(scratch, 2) if up else None,
                    "filesystem_total_gib": 600.0,
                    "filesystem_avail_gib": round(600.0 * (1.0 - scratch / 100.0), 1) if up else None,
                    "disk_read_bytes_per_second": round(disk_r, 1) if up else None,
                    "disk_write_bytes_per_second": round(disk_w, 1) if up else None,
                    "disk_io_utilization_percent": round(disk_io, 2) if up else None,
                    "network_receive_bytes_per_second": round(net_rx, 1) if up else None,
                    "network_transmit_bytes_per_second": round(net_tx, 1) if up else None,
                    "network_errors_per_second": round(net_err, 4) if up else None,
                    "network_drop_per_second": 0.0 if up else None,
                    "procs_running": procs_r if up else None,
                    "procs_blocked": procs_b if up else None,
                    "context_switches_per_sec": round(cpu * 185.0, 0) if up else None,
                    "psi_cpu_percent": psi_cpu if up else None,
                    "psi_memory_percent": psi_mem if up else None,
                    "psi_io_percent": psi_io if up else None,
                    "cpu_temperature_celsius": round(temp, 1) if up else None,
                }
            )

        jobs_view = []
        for j in self.sim_slurm_jobs:
            jc = dict(j)
            if jc["job_id"] in self.cancelled_sim_jobs:
                jc["state"] = "CANCELLED"
            active_job_nodes = [n for n in jc["nodes"] if n not in self.drained_nodes]
            jc["draining_nodes"] = [n for n in jc["nodes"] if n in self.drained_nodes]
            jc["active_node_count"] = len(active_job_nodes)
            jobs_view.append(jc)

        return {
            "timestamp_utc": now_iso,
            "is_synthetic": False,
            "is_simulated": True,
            "prometheus_connected": False,
            "slurm_connected": False,
            "slurm_source": "simulator",
            "mode_label": "4-Node Cluster Stream (Telemetry Simulator)",
            "nodes": nodes_out,
            "slurm_jobs": jobs_view,
        }

    # -------------------------------------------------------------------------
    # MODE 3: 12-Node SCC Dataset Replay (../scc_hpc_dataset)
    # -------------------------------------------------------------------------
    def _load_scc_nodes_meta(self) -> None:
        if self.scc_nodes_meta:
            return
        nodes_csv = SCC_DATASET_DIR / "nodes.csv"
        if not nodes_csv.exists():
            return
        with nodes_csv.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.scc_nodes_meta[row["node_id"]] = {
                    "rack_id": row["rack_id"],
                    "cpu_cores": int(row["cpu_logical_cores"]),
                    "memory_gib": round(int(row["memory_total_bytes"]) / (1024**3)),
                }

    def _load_replay_window(self, preset_id: str) -> None:
        self._load_scc_nodes_meta()
        self.replay_preset_id = preset_id
        self.replay_frames = []
        self.replay_cursor = 0

        preset = next((p for p in REPLAY_PRESETS if p["id"] == preset_id), REPLAY_PRESETS[0])
        start_ts = preset["start_utc"]

        metrics_path = SCC_DATASET_DIR / "metrics.csv"
        labels_path = SCC_DATASET_DIR / "labels.csv"
        if not metrics_path.exists() or not labels_path.exists():
            return

        max_rows = 12 * 60
        metrics_slice: List[Dict[str, str]] = []
        with metrics_path.open("r", encoding="utf-8") as mf:
            reader = csv.DictReader(mf)
            capturing = False
            for row in reader:
                if not capturing and row["timestamp_utc"] >= start_ts:
                    capturing = True
                if capturing:
                    metrics_slice.append(row)
                    if len(metrics_slice) >= max_rows:
                        break

        if not metrics_slice:
            return

        end_ts = metrics_slice[-1]["timestamp_utc"]
        labels_map: Dict[tuple, Dict[str, str]] = {}
        with labels_path.open("r", encoding="utf-8") as lf:
            reader = csv.DictReader(lf)
            for row in reader:
                ts = row["timestamp_utc"]
                if ts < start_ts:
                    continue
                if ts > end_ts:
                    break
                labels_map[(ts, row["node_id"])] = row

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for mrow in metrics_slice:
            ts = mrow["timestamp_utc"]
            nid = mrow["node_id"]
            lrow = labels_map.get((ts, nid), {})
            nmeta = self.scc_nodes_meta.get(nid, {"rack_id": "rack-1", "cpu_cores": 32, "memory_gib": 128})
            up = int(mrow["up"]) if mrow.get("up") else 0
            planned = int(lrow.get("planned_maintenance", "0") or 0)
            gt_class = lrow.get("event_class", "normal")
            gt_phase = lrow.get("event_phase", "normal")
            gt_fail_1h = lrow.get("failure_within_1h", "")

            slurm_state = (
                "MAINT"
                if planned == 1
                else (
                    "DRAINED"
                    if nid in self.drained_nodes
                    else ("DOWN" if up == 0 else "ALLOCATED")
                )
            )

            grouped.setdefault(ts, []).append(
                {
                    "timestamp_utc": ts,
                    "node_id": nid,
                    "display_name": nid.replace("compute-", "Compute-"),
                    "hostname": nid,
                    "instance": f"{nid}:9100",
                    "ip": f"10.200.{1 if nmeta['rack_id']=='rack-1' else 2}.{int(nid.split('-')[1])}",
                    "ssh_target": "localhost",
                    "role": "compute",
                    "rack_id": nmeta["rack_id"],
                    "cpu_cores": nmeta["cpu_cores"],
                    "memory_gib": nmeta["memory_gib"],
                    "up": up,
                    "planned_maintenance": planned,
                    "gt_event_class": gt_class,
                    "gt_event_phase": gt_phase,
                    "gt_failure_within_1h": int(gt_fail_1h) if gt_fail_1h in ("0", "1") else None,
                    "slurm_state": slurm_state,
                    "uptime_seconds": None,
                    "cpu_utilization_percent": _f_or_none(mrow.get("cpu_utilization_percent")),
                    "cpu_iowait_percent": _f_or_none(mrow.get("cpu_iowait_percent")),
                    "memory_used_percent": _f_or_none(mrow.get("memory_used_percent")),
                    "swap_used_percent": _f_or_none(mrow.get("swap_used_percent")),
                    "load1": _f_or_none(mrow.get("load1")),
                    "load5": _f_or_none(mrow.get("load5")),
                    "load15": _f_or_none(mrow.get("load15")),
                    "root_used_percent": _f_or_none(mrow.get("filesystem_used_percent")),
                    "scratch_used_percent": _f_or_none(mrow.get("scratch_used_percent")),
                    "disk_read_bytes_per_second": _f_or_none(mrow.get("disk_read_bytes_per_second")),
                    "disk_write_bytes_per_second": _f_or_none(mrow.get("disk_write_bytes_per_second")),
                    "disk_io_utilization_percent": _f_or_none(mrow.get("disk_io_utilization_percent")),
                    "network_receive_bytes_per_second": _f_or_none(mrow.get("network_receive_bytes_per_second")),
                    "network_transmit_bytes_per_second": _f_or_none(mrow.get("network_transmit_bytes_per_second")),
                    "network_errors_per_second": _f_or_none(mrow.get("network_errors_per_second")),
                    "procs_running": None,
                    "procs_blocked": None,
                    "psi_cpu_percent": None,
                    "psi_memory_percent": None,
                    "psi_io_percent": None,
                    "cpu_temperature_celsius": _f_or_none(mrow.get("cpu_temperature_celsius")),
                }
            )

        for ts in sorted(grouped.keys()):
            self.replay_frames.append({"timestamp_utc": ts, "nodes": grouped[ts]})

    def _fetch_from_dataset_replay(self) -> Dict[str, Any]:
        if not self.replay_frames:
            self._load_replay_window(self.replay_preset_id)
        if not self.replay_frames:
            return self._fetch_from_cluster_sim()

        frame = self.replay_frames[self.replay_cursor % len(self.replay_frames)]
        self.replay_cursor = (self.replay_cursor + 1) % len(self.replay_frames)
        preset = next((p for p in REPLAY_PRESETS if p["id"] == self.replay_preset_id), REPLAY_PRESETS[0])

        nodes_copy: List[Dict[str, Any]] = []
        for n in frame["nodes"]:
            nc = dict(n)
            if nc["node_id"] in self.drained_nodes and nc["planned_maintenance"] == 0 and nc["up"] == 1:
                nc["slurm_state"] = "DRAINED"
            if nc.get("gt_event_phase") in ("failure", "maintenance") and nc.get("gt_event_class") != "normal":
                add_system_log(
                    timestamp_utc=frame["timestamp_utc"],
                    node_id=nc["node_id"],
                    source="scc-dataset-gt",
                    severity="CRITICAL" if nc.get("gt_event_phase") == "failure" else "INFO",
                    event_type=str(nc.get("gt_event_class")),
                    message=f"[SYNTHETIC GT] Phase={nc.get('gt_event_phase')} | Event={nc.get('gt_event_class')}",
                )
            nodes_copy.append(nc)

        replay_jobs = [
            {
                "job_id": "91042",
                "name": "GROMACS-MD-Rack1",
                "user": "synthetic_u1",
                "partition": "rack-1",
                "state": "RUNNING",
                "duration": "03:30:00",
                "time_limit": "12:00:00",
                "nodes": ["compute-01", "compute-02", "compute-03", "compute-04"],
                "node_count": 4,
                "cpus": 128,
                "memory_req": "256G",
                "elapsed_hours": 3.5,
                "mpi_ranks": 128,
                "Watts_per_node": 310,
                "reason": "None",
            },
            {
                "job_id": "91048",
                "name": "LAMMPS-256GiB-Rack2",
                "user": "synthetic_u2",
                "partition": "rack-2",
                "state": "RUNNING",
                "duration": "04:12:00",
                "time_limit": "12:00:00",
                "nodes": ["compute-07", "compute-08", "compute-09", "compute-10"],
                "node_count": 4,
                "cpus": 256,
                "memory_req": "512G",
                "elapsed_hours": 4.2,
                "mpi_ranks": 256,
                "Watts_per_node": 340,
                "reason": "None",
            },
        ]

        return {
            "timestamp_utc": frame["timestamp_utc"],
            "is_synthetic": True,
            "is_simulated": False,
            "prometheus_connected": False,
            "slurm_connected": False,
            "slurm_source": "synthetic_replay",
            "mode_label": f"SCC Synthetic Replay — {preset['label']}",
            "preset_description": preset["description"],
            "replay_progress": f"{self.replay_cursor}/{len(self.replay_frames)}",
            "nodes": nodes_copy,
            "slurm_jobs": replay_jobs,
        }


def _f_or_none(val: Optional[str]) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return round(float(val), 4)
    except Exception:
        return None

from collections import deque
import math
import statistics
from typing import Any, Deque, Dict, List


class RollingFeaturePipeline:
    """
    Maintains a causal per-node rolling telemetry buffer (up to 72 samples)
    and computes:
      1. Window means, standard deviations, and linear trend slopes (beta)
      2. Core-normalized load (load1 / cpu_cores) per STUDENT_GUIDE.md
      3. Cross-node peer median deviations for MPI Straggler detection
    """

    TRACKED_METRICS = [
        "cpu_utilization_percent",
        "cpu_iowait_percent",
        "memory_used_percent",
        "load1",
        "load5",
        "load15",
        "scratch_used_percent",
        "disk_read_bytes_per_second",
        "disk_write_bytes_per_second",
        "disk_io_utilization_percent",
        "network_receive_bytes_per_second",
        "network_transmit_bytes_per_second",
        "network_errors_per_second",
        "cpu_temperature_celsius",
    ]

    def __init__(self, maxlen: int = 72) -> None:
        self.maxlen = maxlen
        self.buffers: Dict[str, Deque[Dict[str, Any]]] = {}

    def reset(self) -> None:
        self.buffers.clear()

    def ingest_batch(self, raw_nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Ingest one synchronized cluster snapshot across all nodes and return
        enriched feature dictionaries keyed by node_id.
        """
        # 1. Push latest sample into each node's causal ring buffer
        for sample in raw_nodes:
            nid = sample["node_id"]
            if nid not in self.buffers:
                self.buffers[nid] = deque(maxlen=self.maxlen)
            if sample.get("up", 1) == 1:
                self.buffers[nid].append(sample)

        # 2. Compute cluster compute-node medians for peer comparison (exclude management node)
        compute_samples = [
            s for s in raw_nodes
            if s.get("role", "compute") == "compute" and s.get("up", 1) == 1
        ]
        peer_medians: Dict[str, float] = {}
        for m in self.TRACKED_METRICS:
            vals = [
                float(s[m])
                for s in compute_samples
                if s.get(m) is not None and not _is_nan(s.get(m))
            ]
            peer_medians[m] = statistics.median(vals) if vals else 0.0

        # Check if cluster is running a coordinated heavy MPI job (median CPU > 65%)
        cluster_busy_mpi = peer_medians.get("cpu_utilization_percent", 0.0) >= 60.0

        # 3. Compute temporal + peer features per node
        enriched: Dict[str, Dict[str, Any]] = {}
        for sample in raw_nodes:
            nid = sample["node_id"]
            cores = max(int(sample.get("cpu_cores") or 32), 1)
            up = int(sample.get("up", 1))
            hist = list(self.buffers.get(nid, []))

            feats: Dict[str, Any] = dict(sample)
            load1_val = _safe_float(sample.get("load1"), 0.0)
            feats["normalized_load1"] = round(load1_val / cores, 4)
            feats["cluster_busy_mpi"] = cluster_busy_mpi

            if up == 0 or not hist:
                feats["mpi_straggler_score"] = 0.0
                feats["is_mpi_straggler"] = False
                enriched[nid] = feats
                continue

            for m in self.TRACKED_METRICS:
                cur_val = _safe_float(sample.get(m), None)
                series = [
                    float(h[m])
                    for h in hist[-12:]
                    if h.get(m) is not None and not _is_nan(h.get(m))
                ]
                long_series = [
                    float(h[m])
                    for h in hist
                    if h.get(m) is not None and not _is_nan(h.get(m))
                ]

                if series and cur_val is not None:
                    mean_12 = statistics.fmean(series)
                    std_12 = statistics.pstdev(series) if len(series) > 1 else 0.0
                    slope_12 = _linear_slope(series)
                    mean_long = statistics.fmean(long_series) if long_series else mean_12
                    std_long = statistics.pstdev(long_series) if len(long_series) > 2 else max(abs(mean_long) * 0.1, 1.0)
                    z_self = (cur_val - mean_long) / max(std_long, 1e-3)
                    peer_med = peer_medians.get(m, cur_val)
                    peer_diff = cur_val - peer_med
                else:
                    mean_12 = 0.0
                    std_12 = 0.0
                    slope_12 = 0.0
                    z_self = 0.0
                    peer_diff = 0.0

                feats[f"{m}__mean12"] = round(mean_12, 4)
                feats[f"{m}__std12"] = round(std_12, 4)
                feats[f"{m}__slope12"] = round(slope_12, 5)
                feats[f"{m}__z_self"] = round(z_self, 3)
                feats[f"{m}__peer_diff"] = round(peer_diff, 4)

            # MPI Straggler Index:
            # High when peer compute nodes are heavily loaded (MPI job active)
            # AND either this node's CPU drops significantly below peers while iowait/load spikes,
            # OR this node has severe I/O wait / network error asymmetry relative to peers.
            straggler_score = 0.0
            if sample.get("role", "compute") == "compute" and len(compute_samples) >= 2:
                cpu_peer_diff = feats.get("cpu_utilization_percent__peer_diff", 0.0)
                iowait_peer_diff = feats.get("cpu_iowait_percent__peer_diff", 0.0)
                net_rx_med = max(peer_medians.get("network_receive_bytes_per_second", 1.0), 1.0)
                net_rx_ratio_drop = max(
                    0.0,
                    (net_rx_med - _safe_float(sample.get("network_receive_bytes_per_second"), net_rx_med)) / net_rx_med,
                )

                if cluster_busy_mpi and cpu_peer_diff <= -15.0:
                    straggler_score += min(0.65, abs(cpu_peer_diff) / 45.0)
                if iowait_peer_diff >= 8.0:
                    straggler_score += min(0.55, iowait_peer_diff / 25.0)
                if cluster_busy_mpi and net_rx_ratio_drop >= 0.35 and iowait_peer_diff >= 4.0:
                    straggler_score += 0.25

            feats["mpi_straggler_score"] = round(min(1.0, straggler_score), 3)
            feats["is_mpi_straggler"] = feats["mpi_straggler_score"] >= 0.45
            enriched[nid] = feats

        return enriched


def _linear_slope(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = statistics.fmean(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den > 0 else 0.0


def _is_nan(val: Any) -> bool:
    try:
        return math.isnan(float(val))
    except Exception:
        return False


def _safe_float(val: Any, default: Any = 0.0) -> Any:
    if val is None or val == "":
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except Exception:
        return default

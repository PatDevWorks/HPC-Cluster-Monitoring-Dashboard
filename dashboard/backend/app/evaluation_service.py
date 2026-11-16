from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .database import (
    list_episodes,
    list_experiments,
    list_model_observations,
)
from fastapi import APIRouter, HTTPException
from typing import Optional
from .database import get_conn

router = APIRouter(prefix="/api/observability", tags=["Model Observability"])

@router.get("/metrics")
def get_model_observability_metrics(model_name: Optional[str] = None, days: int = 7):
    """
    Retrieves aggregated model evaluation metrics, detection trends,
    and historical observation counts for V7 and V8 models.
    """
    conn = get_conn()
    try:
        query = """
            SELECT model_name, node_id, COUNT(*) as total_observations,
                   SUM(flagged) as total_flagged,
                   AVG(score) as avg_score,
                   MAX(score) as max_score
            FROM model_score_observations
            GROUP BY model_name, node_id
        """
        rows = conn.execute(query).fetchall()
        return {
            "time_window_days": days,
            "metrics": [dict(row) for row in rows]
        }
    finally:
        conn.close()

def _parse_dt(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _episode_overlaps_window(
    ep: Dict[str, Any],
    node_id: str,
    win_start: datetime,
    win_end: datetime,
) -> Optional[datetime]:
    if node_id != "cluster" and ep.get("node_id") != node_id:
        return None
    ep_start = _parse_dt(ep.get("start_utc") or ep.get("started_utc"))
    ep_end = _parse_dt(ep.get("resolved_utc")) or _parse_dt(ep.get("last_seen_utc")) or ep_start
    if ep_start is None:
        return None
    if ep_end is None:
        ep_end = ep_start
    if ep_start <= win_end and ep_end >= win_start:
        return ep_start
    return None


def _obs_overlaps_window(
    obs: Dict[str, Any],
    node_id: str,
    win_start: datetime,
    win_end: datetime,
) -> Optional[datetime]:
    if not obs.get("flagged"):
        return None
    if node_id != "cluster" and obs.get("node_id") != node_id:
        return None
    obs_dt = _parse_dt(obs.get("observation_utc"))
    if obs_dt is None:
        return None
    if win_start <= obs_dt <= win_end:
        return obs_dt
    return None


def _match_detector_in_window(
    source_key: str,
    exp_node: str,
    start_dt: datetime,
    end_dt: datetime,
    episodes: List[Dict[str, Any]],
    v7_obs: List[Dict[str, Any]],
    lstm_obs: List[Dict[str, Any]],
    pad_minutes: float = 5.0,
) -> Tuple[bool, Optional[float]]:
    win_start = start_dt - timedelta(minutes=pad_minutes)
    win_end = end_dt + timedelta(minutes=pad_minutes)
    earliest_hit: Optional[datetime] = None

    for ep in episodes:
        if ep.get("alert_source", "telemetry") != source_key:
            continue
        hit_dt = _episode_overlaps_window(ep, exp_node, win_start, win_end)
        if hit_dt and (earliest_hit is None or hit_dt < earliest_hit):
            earliest_hit = hit_dt

    obs_list = v7_obs if source_key == "v7" else (lstm_obs if source_key == "lstm_v8" else [])
    for obs in obs_list:
        hit_dt = _obs_overlaps_window(obs, exp_node, win_start, win_end)
        if hit_dt and (earliest_hit is None or hit_dt < earliest_hit):
            earliest_hit = hit_dt

    if earliest_hit is None:
        return False, None
    delay_min = round((earliest_hit - start_dt).total_seconds() / 60.0, 2)
    return True, delay_min


def compute_model_comparison_summary() -> Dict[str, Any]:
    """Compare V7 Isolation Forest, LSTM V8, and simple telemetry thresholds without fabricating metrics."""
    episodes = list_episodes(limit=500)
    experiments = list_experiments(limit=200)
    v7_obs = list_model_observations(model_name="v7", limit=2000)
    lstm_obs = list_model_observations(model_name="lstm_v8", limit=2000)

    detectors = ("v7", "lstm_v8", "telemetry")
    runtime_burden: Dict[str, Dict[str, Any]] = {}
    for src in detectors:
        src_eps = [e for e in episodes if (e.get("alert_source") or "telemetry") == src]
        active = [e for e in src_eps if e.get("status") in ("active", "acknowledged", "silenced")]
        durations = []
        for e in src_eps:
            st = _parse_dt(e.get("start_utc") or e.get("started_utc"))
            en = _parse_dt(e.get("resolved_utc")) or _parse_dt(e.get("last_seen_utc"))
            if st and en and en >= st:
                durations.append((en - st).total_seconds())
        runtime_burden[src] = {
            "active_episodes": len(active),
            "total_episodes": len(src_eps),
            "affected_nodes": sorted({e.get("node_id") for e in active if e.get("node_id")}),
            "mean_episode_duration_sec": round(sum(durations) / len(durations), 1) if durations else None,
            "persisted_observations": len(v7_obs) if src == "v7" else (len(lstm_obs) if src == "lstm_v8" else None),
            "flagged_observations": (
                sum(1 for o in v7_obs if o.get("flagged"))
                if src == "v7"
                else (sum(1 for o in lstm_obs if o.get("flagged")) if src == "lstm_v8" else None)
            ),
        }

    now_dt = datetime.now(timezone.utc)
    positive_exps = [e for e in experiments if e.get("label") == "positive_fault"]
    negative_exps = [e for e in experiments if e.get("label") in ("benign_workload", "normal")]

    detector_stats: Dict[str, Dict[str, Any]] = {}
    workload_groups: Dict[str, Dict[str, Any]] = {}
    per_experiment_rows: List[Dict[str, Any]] = []

    for exp in experiments:
        st_dt = _parse_dt(exp.get("start_utc"))
        en_dt = _parse_dt(exp.get("end_utc")) or now_dt
        if st_dt is None:
            continue
        row: Dict[str, Any] = {
            "id": exp["id"],
            "name": exp["name"],
            "category": exp["category"],
            "node_id": exp["node_id"],
            "fault_type": exp["fault_type"],
            "label": exp["label"],
            "workload_condition": exp["workload_condition"],
            "start_utc": exp["start_utc"],
            "end_utc": exp["end_utc"],
        }
        for src in detectors:
            matched, delay_min = _match_detector_in_window(
                src,
                exp["node_id"],
                st_dt,
                en_dt,
                episodes,
                v7_obs,
                lstm_obs,
            )
            row[f"{src}_detected"] = matched
            row[f"{src}_delay_min"] = delay_min
        per_experiment_rows.append(row)

    for src in detectors:
        tp = 0
        fn = 0
        delays: List[float] = []
        fp = 0

        for exp_row in per_experiment_rows:
            wl = exp_row.get("workload_condition") or "mixed"
            grp = workload_groups.setdefault(
                wl,
                {
                    "workload_condition": wl,
                    "positive_events": 0,
                    "benign_windows": 0,
                    "v7_detected": 0,
                    "lstm_v8_detected": 0,
                    "telemetry_detected": 0,
                    "v7_false_alarms": 0,
                    "lstm_v8_false_alarms": 0,
                    "telemetry_false_alarms": 0,
                },
            )
            matched = bool(exp_row.get(f"{src}_detected"))
            delay_val = exp_row.get(f"{src}_delay_min")

            if exp_row["label"] == "positive_fault":
                if src == "v7":
                    grp["positive_events"] += 1
                if matched:
                    tp += 1
                    grp[f"{src}_detected"] += 1
                    if delay_val is not None:
                        delays.append(delay_val)
                else:
                    fn += 1
            elif exp_row["label"] in ("benign_workload", "normal"):
                if src == "v7":
                    grp["benign_windows"] += 1
                if matched:
                    fp += 1
                    grp[f"{src}_false_alarms"] += 1

        total_pos = tp + fn
        total_neg = len(negative_exps)
        precision = (tp / (tp + fp)) if (tp + fp) > 0 else None
        recall = (tp / total_pos) if total_pos > 0 else None
        f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
        fpr = (fp / total_neg) if total_neg > 0 else None

        detector_stats[src] = {
            "positive_events": total_pos,
            "detected_events": tp,
            "missed_events": fn,
            "detection_coverage_pct": round(recall * 100.0, 1) if recall is not None else None,
            "mean_detection_delay_min": round(sum(delays) / len(delays), 2) if delays else None,
            "min_detection_delay_min": round(min(delays), 2) if delays else None,
            "benign_windows": total_neg,
            "false_positive_windows": fp,
            "false_positive_rate_pct": round(fpr * 100.0, 1) if fpr is not None else None,
            "event_precision": round(precision, 3) if precision is not None else None,
            "event_recall": round(recall, 3) if recall is not None else None,
            "event_f1": round(f1, 3) if f1 is not None else None,
        }

    return {
        "has_labelled_experiments": len(experiments) > 0,
        "experiments_total": len(experiments),
        "positive_experiments_count": len(positive_exps),
        "benign_experiments_count": len(negative_exps),
        "methodology_note": (
            "Model comparison evaluates V7 Isolation Forest, LSTM V8, and simple telemetry thresholds "
            "independently against labelled failure/degradation and benign workload windows. "
            "Raw alert counts are shown separately as operational burden metrics and must not be used alone as accuracy claims."
        ),
        "runtime_burden": runtime_burden,
        "detector_evaluation": detector_stats,
        "workload_breakdown": list(workload_groups.values()),
        "experiment_results": per_experiment_rows,
    }

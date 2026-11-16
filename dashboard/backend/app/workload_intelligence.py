from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from .database import get_conn

router = APIRouter(prefix="/api/workloads", tags=["Workload & Infrastructure Intelligence"])

@router.get("/node-correlation/{node_id}")
def get_node_workload_correlation(node_id: str, limit: int = 10):
    """
    Retrieves recent infrastructure metrics alongside Slurm workload audit/job data 
    for a specific compute node to assist operators and Gemini in root-cause analysis.
    """
    conn = get_conn()
    try:
        # 1. Fetch latest infrastructure telemetry for the node
        telemetry = conn.execute(
            """
            SELECT timestamp_utc, up, health_score, cpu_percent, iowait_percent,
                   memory_percent, swap_percent, load1, disk_io_percent, net_err_s, temp_celsius
            FROM telemetry_history
            WHERE node_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (node_id, limit)
        ).fetchall()

        # 2. Fetch recent Slurm actions/job events associated with this node
        slurm_events = conn.execute(
            """
            SELECT timestamp_utc, action, reason, jobs_protected, core_hours_saved, executed_mode
            FROM slurm_actions_audit
            WHERE node_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (node_id, limit)
        ).fetchall()

        # 3. Fetch any active or recent V7/V8 model flags on this node
        model_flags = conn.execute(
            """
            SELECT model_name, observation_utc, score, threshold, flagged, classification
            FROM model_score_observations
            WHERE node_id = ? AND flagged = 1
            ORDER BY id DESC LIMIT 5
            """,
            (node_id,)
        ).fetchall()

        return {
            "node_id": node_id,
            "infrastructure_telemetry": [dict(r) for r in telemetry],
            "slurm_workload_context": [dict(r) for r in slurm_events],
            "recent_model_anomalies": [dict(r) for r in model_flags],
            "analytical_note": "Temporal overlap indicates correlation; inspect job cgroups/PIDs before confirming causation."
        }
    finally:
        conn.close()
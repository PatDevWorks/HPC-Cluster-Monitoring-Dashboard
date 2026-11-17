from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from .database import get_conn
from .auth_dependencies import get_current_user

router = APIRouter(
    prefix="/api/incidents",
    tags=["Incident Management"],
    dependencies=[Depends(get_current_user)],
)

@router.get("/", response_model=List[Dict[str, Any]])
def list_incidents(status: Optional[str] = None, limit: int = 20):
    """Retrieves recorded incident episodes with related metadata."""
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM alert_episodes WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alert_episodes ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@router.get("/{incident_id}/evidence")
def get_incident_evidence(incident_id: int):
    """
    Correlates a specific incident with related V7/V8 model observations, 
    telemetry snapshots, and Slurm workload context.
    """
    conn = get_conn()
    try:
        incident = conn.execute(
            "SELECT * FROM alert_episodes WHERE id = ?", (incident_id,)
        ).fetchone()
        
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found.")

        incident_dict = dict(incident)
        node_id = incident_dict.get("node_id")

        # Gather correlated V7/V8 model observations around this incident node
        model_obs = conn.execute(
            """
            SELECT * FROM model_score_observations 
            WHERE node_id = ? 
            ORDER BY id DESC LIMIT 5
            """,
            (node_id,)
        ).fetchall()

        # Gather related Slurm audit actions
        slurm_context = conn.execute(
            """
            SELECT * FROM slurm_actions_audit 
            WHERE node_id = ? 
            ORDER BY id DESC LIMIT 5
            """,
            (node_id,)
        ).fetchall()

        return {
            "incident": incident_dict,
            "evidence_correlation": {
                "model_observations": [dict(r) for r in model_obs],
                "slurm_workload_actions": [dict(r) for r in slurm_context]
            }
        }
    finally:
        conn.close()

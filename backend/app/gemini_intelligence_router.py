from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from .database import append_gemini_message, ensure_ai_conversation, get_conn, list_gemini_messages
from .auth_dependencies import get_current_user
from .gemini_service import GeminiConfigurationError, GeminiGenerationError, generate_ai_interaction

router = APIRouter(
    prefix="/api/gemini",
    tags=["Gemini Intelligence"],
    dependencies=[Depends(get_current_user)],
)

class GeminiQueryRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = "default-session"
    node_filter: Optional[str] = None

@router.post("/query")
def query_gemini_intelligence(req: GeminiQueryRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Receives an operator query, gathers authenticated context from FastAPI (Prometheus, V7, V8, Slurm),
    and queries Gemini with strict grounding instructions to prevent hallucination.
    """
    # 1. Gather live context from database or internal connectors
    conn = get_conn()
    try:
        recent_telemetry = conn.execute(
            "SELECT * FROM telemetry_history ORDER BY id DESC LIMIT 5"
        ).fetchall()
        recent_anomalies = conn.execute(
            "SELECT * FROM model_score_observations ORDER BY id DESC LIMIT 5"
        ).fetchall()
    finally:
        conn.close()

    # 2. Build grounded system context for Gemini
    evidence = {
        "recent_telemetry": [dict(r) for r in recent_telemetry],
        "recent_model_observations": [dict(r) for r in recent_anomalies],
        "node_filter": req.node_filter,
    }
    session_id = req.session_id or "default-session"
    email = current_user.get("email", "")
    ensure_ai_conversation(session_id, email, "gemini")
    history = list_gemini_messages(session_id=session_id, limit=16, user_email=email)
    try:
        result = generate_ai_interaction(
            mode="chat", question=req.prompt, evidence=evidence,
            conversation_history=history, provider="gemini",
        )
    except GeminiConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GeminiGenerationError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 502), detail=str(exc)) from exc

    append_gemini_message(session_id, email, "user", "chat", req.prompt, {"node_filter": req.node_filter})
    append_gemini_message(session_id, email, "assistant", "chat", result["answer"], {"model": result["model"], "provider": "gemini"})

    return {
        "session_id": session_id,
        "query": req.prompt,
        "response": result["answer"],
        "provider": result["provider"],
        "model": result["model"],
        "evidence_used": {
            "telemetry_count": len(recent_telemetry),
            "anomaly_observations_count": len(recent_anomalies)
        }
    }

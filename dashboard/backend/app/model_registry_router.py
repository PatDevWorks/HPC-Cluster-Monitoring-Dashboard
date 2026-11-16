import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .auth_dependencies import get_current_user, require_roles
from .config import GEMINI_API_KEY, GEMINI_MODEL
from .database import cleanup_model_observations, get_app_settings, get_conn, list_model_observations, update_app_settings
from .llm_service import provider_status

router = APIRouter(prefix="/api/models", tags=["Model Registry"])
require_admin = require_roles("super_admin", "admin")

_DEFAULT_MODELS = [
    {"model_key": "v7", "model_name": "V7 Isolation Forest", "version": None,
     "model_type": "Unsupervised anomaly detection", "purpose": "Detect anomalous observations across HPC telemetry.",
     "provider": "V7 inference service", "nodes_monitored": ["headnode", "compute001", "compute002", "compute003"],
     "features": [], "lookback_window": None},
    {"model_key": "lstm_v8", "model_name": "LSTM V8", "version": None,
     "model_type": "Time-series forecasting", "purpose": "Forecast telemetry and report early-warning signals.",
     "provider": "LSTM V8 inference service", "nodes_monitored": ["headnode", "compute001", "compute002", "compute003"],
     "features": [], "lookback_window": "See runtime schema when available"},
    {"model_key": "gemini", "model_name": "Gemini Intelligence", "version": GEMINI_MODEL,
     "model_type": "Large language model", "purpose": "Interpret cluster evidence and generate operational assistance.",
     "provider": "Google Gemini", "nodes_monitored": ["cluster-wide"], "features": [], "lookback_window": "On demand"},
]


class ModelRegistration(BaseModel):
    model_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    model_name: str = Field(min_length=1, max_length=120)
    version: Optional[str] = Field(default=None, max_length=120)
    model_type: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=1000)
    provider: Optional[str] = Field(default=None, max_length=120)
    nodes_monitored: List[str] = Field(default_factory=list, max_length=100)
    features: List[str] = Field(default_factory=list, max_length=200)
    lookback_window: Optional[str] = Field(default=None, max_length=200)


class RetentionUpdate(BaseModel):
    retention_days: int


def _ensure_seed_registry() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    try:
        for item in _DEFAULT_MODELS:
            conn.execute(
                """INSERT OR IGNORE INTO model_registry (
                    model_key, model_name, version, model_type, purpose, provider,
                    nodes_monitored_json, features_json, lookback_window, created_utc, updated_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item["model_key"], item["model_name"], item["version"], item["model_type"],
                 item["purpose"], item["provider"], json.dumps(item["nodes_monitored"]),
                 json.dumps(item["features"]), item["lookback_window"], now, now),
            )
        conn.commit()
    finally:
        conn.close()


def _decode_registry_row(row: Any) -> Dict[str, Any]:
    item = dict(row)
    item["nodes_monitored"] = json.loads(item.pop("nodes_monitored_json") or "[]")
    item["features"] = json.loads(item.pop("features_json") or "[]")
    return item


def _runtime_status(request: Request, model_key: str) -> Dict[str, Any]:
    orch = getattr(request.app.state, "orchestrator", None)
    now = datetime.now(timezone.utc)
    if model_key == "gemini":
        gemini = provider_status()["gemini"]
        return {"enabled": True, "configured": bool(GEMINI_API_KEY), "api_reachable": None,
                "model_loaded": None, "pipeline_running": None, "recent_inference_success": None,
                "observation_fresh": None, "last_success_utc": gemini.get("last_success_utc"),
                "status": "configured" if GEMINI_API_KEY else "not_configured", "model": GEMINI_MODEL}

    if model_key not in {"v7", "lstm_v8"}:
        return {"enabled": None, "configured": None, "api_reachable": None,
                "model_loaded": None, "pipeline_running": None,
                "recent_inference_success": None, "observation_fresh": None,
                "last_success_utc": None, "status": "integration_not_connected"}

    service = getattr(orch, "v7", None) if model_key == "v7" else getattr(orch, "lstm_v8", None)
    if service is None:
        return {"status": "unavailable", "api_reachable": None, "observation_fresh": False}
    status = service.get_status()
    enabled = bool(status.get("enabled"))
    last_success = status.get("last_success_utc")
    threshold = float(getattr(service, "stale_after_sec", 60.0))
    age = None
    if last_success:
        try:
            stamp = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age = max(0.0, (now - stamp).total_seconds())
        except ValueError:
            pass
    state = status.get("state") or {}
    loaded = state.get("model_loaded") if isinstance(state, dict) else None
    version = status.get("model_version") if model_key == "v7" else (state.get("model_version") if isinstance(state, dict) else None)
    nodes = sorted((status.get("nodes") or {}).keys()) if model_key == "v7" else (sorted((state.get("nodes") or {}).keys()) if isinstance(state, dict) else [])
    stored = list_model_observations(model_name=model_key, limit=1)
    latest_observation_utc = stored[0].get("observation_utc") if stored else None
    observation_age = None
    if latest_observation_utc:
        try:
            obs_stamp = datetime.fromisoformat(str(latest_observation_utc).replace("Z", "+00:00"))
            if obs_stamp.tzinfo is None:
                obs_stamp = obs_stamp.replace(tzinfo=timezone.utc)
            observation_age = max(0.0, (now - obs_stamp).total_seconds())
        except ValueError:
            pass
    return {
        **status,
        "api_reachable": bool(status.get("connected")),
        "model_loaded": loaded,
        "pipeline_running": bool(orch and orch.polling_active and enabled),
        "recent_inference_success": bool(last_success and status.get("connected") and not status.get("stale")),
        "observation_fresh": bool(observation_age is not None and observation_age <= threshold),
        "latest_observation_utc": latest_observation_utc,
        "last_success_utc": last_success,
        "model_version": version,
        "nodes_with_current_results": nodes,
        "runtime_schema": status.get("schema") or {},
    }


def _latest_observation(model_key: str) -> Optional[Dict[str, Any]]:
    rows = list_model_observations(model_name=model_key, limit=1)
    return rows[0] if rows else None


@router.get("/registry", response_model=List[Dict[str, Any]])
def get_model_registry(request: Request, _user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    _ensure_seed_registry()
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM model_registry ORDER BY model_key").fetchall()
    finally:
        conn.close()
    models = []
    for row in rows:
        item = _decode_registry_row(row)
        runtime = _runtime_status(request, item["model_key"])
        item["runtime"] = runtime
        item["status"] = runtime.get("status", "unknown")
        item["readiness"] = ("ready" if runtime.get("observation_fresh") is True else
                             "degraded" if runtime.get("api_reachable") is True else
                             "unavailable" if runtime.get("configured") is False or runtime.get("api_reachable") is False else "unknown")
        item["last_success_utc"] = runtime.get("last_success_utc")
        item["latest_observation"] = _latest_observation(item["model_key"])
        if item["model_key"] == "v7" and runtime.get("model_version"):
            item["version"] = runtime["model_version"]
        elif item["model_key"] == "gemini":
            item["version"] = GEMINI_MODEL
        models.append(item)
    return models


@router.get("/health")
def get_model_health(request: Request, _user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    models = get_model_registry(request, _user)
    return {"models": [{"model_key": m["model_key"], "model_name": m["model_name"], **m["runtime"]} for m in models]}


@router.get("/summary")
def get_model_summary(request: Request, _user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    models = get_model_registry(request, _user)
    conn = get_conn()
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM model_score_observations").fetchone()[0])
        latest = conn.execute("SELECT model_name, node_id, observation_utc, score, classification FROM model_score_observations ORDER BY observation_utc DESC, id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    healthy = sum(1 for m in models if m.get("readiness") == "ready")
    degraded = sum(1 for m in models if m.get("readiness") in {"degraded", "unavailable"})
    return {"total_registered_models": len(models), "healthy_models": healthy,
            "degraded_or_unavailable_models": degraded,
            "unknown_health_models": len(models) - healthy - degraded,
            "total_stored_observations": total, "latest_observation": dict(latest) if latest else None}


@router.get("/observations")
def get_observation_history(
    model_name: Optional[str] = None, node_id: Optional[str] = None,
    since_utc: Optional[str] = None, until_utc: Optional[str] = None,
    classification: Optional[str] = None, flagged: Optional[bool] = None,
    limit: int = Query(500, ge=1, le=5000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    return list_model_observations(model_name, node_id, limit, since_utc, until_utc, classification, flagged)


@router.get("/observations/{model_name}")
def get_model_observations(
    model_name: str, limit: int = Query(50, ge=1, le=5000), node_id: Optional[str] = None,
    since_utc: Optional[str] = None, until_utc: Optional[str] = None,
    classification: Optional[str] = None, flagged: Optional[bool] = None,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    aliases = {"v7": "v7", "v7 isolation forest": "v7", "lstm v8": "lstm_v8", "lstm_v8": "lstm_v8"}
    key = aliases.get(model_name.strip().lower(), model_name)
    return list_model_observations(key, node_id, limit, since_utc, until_utc, classification, flagged)


@router.get("/retention")
def get_observation_retention(_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    settings = get_app_settings()
    return {"retention_days": settings.get("model_observation_retention_days", 30),
            "last_cleanup_utc": settings.get("model_observation_last_cleanup_utc"), "supported_days": [15, 30]}


@router.put("/retention")
def update_observation_retention(payload: RetentionUpdate, _admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    if payload.retention_days not in (15, 30):
        raise HTTPException(status_code=422, detail="Retention must be 15 or 30 days.")
    update_app_settings({"model_observation_retention_days": payload.retention_days})
    return {"saved": True, **cleanup_model_observations(payload.retention_days)}


@router.post("/registry", status_code=201)
def register_model(payload: ModelRegistration, _admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    _ensure_seed_registry()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO model_registry (
                model_key, model_name, version, model_type, purpose, provider,
                nodes_monitored_json, features_json, lookback_window, created_utc, updated_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.model_key, payload.model_name, payload.version, payload.model_type,
             payload.purpose, payload.provider, json.dumps(payload.nodes_monitored),
             json.dumps(payload.features), payload.lookback_window, now, now),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Model key is already registered.") from exc
        raise
    finally:
        conn.close()
    return {"registered": True, "model_key": payload.model_key}

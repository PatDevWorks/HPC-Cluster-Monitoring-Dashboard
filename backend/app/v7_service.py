import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from .v7_client import V7Client

logger = logging.getLogger(__name__)

_NODE_ALIASES: Dict[str, str] = {
    "headnode": "headnode",
    "head-node": "headnode",
    "head_node": "headnode",
    "compute001": "compute001",
    "compute-01": "compute001",
    "compute_01": "compute001",
    "compute002": "compute002",
    "compute-02": "compute002",
    "compute_02": "compute002",
    "compute003": "compute003",
    "compute-03": "compute003",
    "compute_03": "compute003",
}

_MODEL_TO_DASH: Dict[str, str] = {
    "headnode": "head-node",
    "compute001": "compute-01",
    "compute002": "compute-02",
    "compute003": "compute-03",
}


def canonical_model_node(node_id: Any) -> str:
    raw = str(node_id or "").strip().lower()
    return _NODE_ALIASES.get(raw, str(node_id or "").strip())


def _safe_float(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN check
        return None
    return round(num, 6)


def _safe_int(val: Any) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _safe_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(int(val))
    if isinstance(val, str):
        low = val.strip().lower()
        if low in ("true", "1", "yes", "anomaly", "anomalous"):
            return True
        if low in ("false", "0", "no", "normal", "ok"):
            return False
    return None


def _parse_iso_age_seconds(iso_str: Optional[str]) -> Optional[float]:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return None


def normalize_v7_entry(
    raw_entry: Dict[str, Any],
    fallback_node_id: Optional[str] = None,
    default_model_version: Optional[str] = None,
    default_feature_count: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_entry, dict):
        return None

    node_raw = (
        raw_entry.get("node_id")
        or raw_entry.get("node")
        or raw_entry.get("hostname")
        or raw_entry.get("host")
        or fallback_node_id
    )
    if not node_raw:
        return None

    model_node = canonical_model_node(node_raw)
    dash_node = _MODEL_TO_DASH.get(model_node, str(node_raw))

    score = _safe_float(
        raw_entry.get("anomaly_score")
        if raw_entry.get("anomaly_score") is not None
        else raw_entry.get("score")
    )
    threshold = _safe_float(
        raw_entry.get("threshold")
        if raw_entry.get("threshold") is not None
        else raw_entry.get("node_threshold")
    )

    flag = None
    for flag_key in ("is_anomaly", "predicted_anomaly", "anomaly"):
        if flag_key in raw_entry and raw_entry[flag_key] is not None:
            flag = _safe_bool(raw_entry[flag_key])
            if flag is not None:
                break
    if flag is None and score is not None and threshold is not None:
        flag = bool(score >= threshold)

    classification_raw = (
        raw_entry.get("classification")
        or raw_entry.get("label")
        or raw_entry.get("status")
    )
    classification = str(classification_raw) if classification_raw is not None else (
        ("anomaly" if flag else "normal") if flag is not None else None
    )

    ts = (
        raw_entry.get("timestamp_utc")
        or raw_entry.get("scored_at_utc")
        or raw_entry.get("minute_utc")
        or raw_entry.get("timestamp")
        or raw_entry.get("created_at")
    )

    model_version = raw_entry.get("model_version") or raw_entry.get("version") or default_model_version
    feature_count = _safe_int(
        raw_entry.get("feature_count")
        if raw_entry.get("feature_count") is not None
        else (
            raw_entry.get("n_features")
            if raw_entry.get("n_features") is not None
            else (
                raw_entry.get("features_count")
                if raw_entry.get("features_count") is not None
                else default_feature_count
            )
        )
    )

    return {
        "node_id": dash_node,
        "model_node_id": model_node,
        "timestamp_utc": str(ts) if ts is not None else None,
        "anomaly_score": score,
        "threshold": threshold,
        "is_anomaly": flag,
        "classification": classification,
        "model_version": str(model_version) if model_version is not None else None,
        "feature_count": feature_count,
        "threshold_source": raw_entry.get("threshold_source"),
    }


def normalize_v7_payload(raw_payload: Any) -> Dict[str, Any]:
    """Normalize supported GET /scores/latest response shapes without fabricating scores."""
    top_model_version: Optional[str] = None
    top_feature_count: Optional[int] = None
    top_timestamp: Optional[str] = None

    items_by_model_node: Dict[str, Dict[str, Any]] = {}

    if isinstance(raw_payload, dict):
        top_model_version = raw_payload.get("model_version") or raw_payload.get("version")
        top_feature_count = _safe_int(
            raw_payload.get("feature_count")
            if raw_payload.get("feature_count") is not None
            else raw_payload.get("n_features")
        )
        top_timestamp = (
            raw_payload.get("generated_at_utc")
            or raw_payload.get("updated_at_utc")
            or raw_payload.get("timestamp_utc")
        )

        container = None
        for key in ("nodes", "scores", "latest_scores", "items", "data"):
            if key in raw_payload and raw_payload[key] is not None:
                container = raw_payload[key]
                break

        if isinstance(container, dict):
            for k, v in container.items():
                if isinstance(v, dict):
                    norm = normalize_v7_entry(
                        v,
                        fallback_node_id=str(k),
                        default_model_version=top_model_version,
                        default_feature_count=top_feature_count,
                    )
                    if norm:
                        items_by_model_node[norm["model_node_id"]] = norm
        elif isinstance(container, list):
            for row in container:
                norm = normalize_v7_entry(
                    row,
                    default_model_version=top_model_version,
                    default_feature_count=top_feature_count,
                )
                if norm:
                    items_by_model_node[norm["model_node_id"]] = norm
        elif container is None:
            # Handle flat dict keyed directly by node names
            for k, v in raw_payload.items():
                if isinstance(v, dict) and ("anomaly_score" in v or "score" in v or "threshold" in v or "is_anomaly" in v):
                    norm = normalize_v7_entry(
                        v,
                        fallback_node_id=str(k),
                        default_model_version=top_model_version,
                        default_feature_count=top_feature_count,
                    )
                    if norm:
                        items_by_model_node[norm["model_node_id"]] = norm
    elif isinstance(raw_payload, list):
        for row in raw_payload:
            norm = normalize_v7_entry(row)
            if norm:
                items_by_model_node[norm["model_node_id"]] = norm

    # Ensure discovered model_version / feature_count propagate cleanly at summary level
    discovered_version = top_model_version
    discovered_features = top_feature_count
    for item in items_by_model_node.values():
        if not discovered_version and item.get("model_version"):
            discovered_version = item["model_version"]
        if discovered_features is None and item.get("feature_count") is not None:
            discovered_features = item["feature_count"]

    return {
        "nodes": items_by_model_node,
        "model_version": discovered_version,
        "feature_count": discovered_features if discovered_features is not None else 28,
        "generated_at_utc": str(top_timestamp) if top_timestamp else None,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }


class V7Service:
    """Polls the cluster V7 Isolation Forest API and manages persistent enable/disable state."""

    def __init__(
        self,
        poll_interval_sec: float = 5.0,
        stale_after_sec: float = 120.0,
        client: Optional[V7Client] = None,
    ) -> None:
        self.client = client or V7Client()
        self.poll_interval_sec = max(2.0, float(poll_interval_sec))
        self.stale_after_sec = max(15.0, float(stale_after_sec))

        self.enabled: bool = True
        self.latest_state: Optional[Dict[str, Any]] = None
        self.last_success_utc: Optional[str] = None
        self.last_error: Optional[str] = None
        self.connected: bool = False

        self.history: Dict[str, Deque[Dict[str, Any]]] = {}
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._last_logged_unconfigured: Optional[str] = None

    def _record_history(self, normalized: Dict[str, Any]) -> None:
        nodes = normalized.get("nodes") or {}
        fetched = normalized.get("fetched_at_utc")
        for model_nid, entry in nodes.items():
            buf = self.history.setdefault(model_nid, deque(maxlen=180))
            point_ts = entry.get("timestamp_utc") or fetched
            if buf and entry.get("timestamp_utc") and buf[-1].get("timestamp_utc") == point_ts:
                continue
            buf.append(
                {
                    "timestamp_utc": point_ts,
                    "anomaly_score": entry.get("anomaly_score"),
                    "threshold": entry.get("threshold"),
                    "is_anomaly": entry.get("is_anomaly"),
                    "classification": entry.get("classification"),
                }
            )

    def get_node_score(self, node_id: str) -> Optional[Dict[str, Any]]:
        if not self.latest_state:
            return None
        nodes = self.latest_state.get("nodes") or {}
        canon = canonical_model_node(node_id)
        item = nodes.get(canon) or nodes.get(node_id)
        return dict(item) if isinstance(item, dict) else None

    def get_history(self) -> Dict[str, List[Dict[str, Any]]]:
        return {k: list(v) for k, v in self.history.items()}

    def get_status(self) -> Dict[str, Any]:
        configured, config_error = self.client.configuration_status()
        age_seconds = _parse_iso_age_seconds(self.last_success_utc)
        has_cached = self.latest_state is not None
        stale_by_age = age_seconds is not None and age_seconds > self.stale_after_sec

        if not self.enabled:
            status = "disabled"
            connected = False
            stale = has_cached
            error = None
        elif not configured:
            status = "not_configured"
            connected = False
            stale = has_cached
            error = config_error
        elif self.connected:
            stale = stale_by_age
            status = "stale" if stale_by_age else "connected"
            connected = True
            error = None
        elif self.last_error:
            status = "error"
            connected = False
            stale = has_cached
            error = self.last_error
        else:
            status = "connecting"
            connected = False
            stale = False
            error = None

        latest = self.latest_state or {}
        return {
            "name": "V7 Isolation Forest",
            "enabled": self.enabled,
            "configured": configured,
            "connected": connected,
            "status": status,
            "stale": stale,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "last_success_utc": self.last_success_utc,
            "last_error": error,
            "model_version": latest.get("model_version") or "v7_global_iforest_per_node_thresholds",
            "feature_count": latest.get("feature_count") or 28,
            "nodes": latest.get("nodes") or {},
            "interpretation_note": (
                "Higher anomaly score indicates observation is further from learned normal behaviour "
                "relative to the per-node threshold. V7 does not diagnose root cause, compute remaining "
                "useful life, or prescribe remediation."
            ),
        }

    async def refresh_once(self) -> None:
        if not self.enabled:
            return

        configured, config_error = self.client.configuration_status()
        if not configured:
            self.connected = False
            self.last_error = config_error
            if self._last_logged_unconfigured != config_error:
                logger.info("V7 polling skipped: %s", config_error)
                self._last_logged_unconfigured = config_error
            return

        self._last_logged_unconfigured = None
        try:
            raw = await asyncio.to_thread(self.client.get_latest_scores)
            normalized = normalize_v7_payload(raw)
            self.latest_state = normalized
            self.last_success_utc = normalized["fetched_at_utc"]
            self.last_error = None
            self.connected = True
            self._record_history(normalized)
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            logger.warning("V7 /scores/latest refresh failed: %s", exc)

    async def _poll_loop(self) -> None:
        stop_ev = self._stop_event
        if stop_ev is None:
            return
        while not stop_ev.is_set():
            if self.enabled:
                await self.refresh_once()
            try:
                await asyncio.wait_for(
                    stop_ev.wait(),
                    timeout=self.poll_interval_sec,
                )
            except asyncio.TimeoutError:
                pass

    async def start(self) -> None:
        if not self.enabled:
            return
        running_loop = asyncio.get_running_loop()
        if self._task and not self._task.done() and self._task.get_loop() is running_loop:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        running_loop = asyncio.get_running_loop()
        if self._stop_event is not None:
            try:
                self._stop_event.set()
            except Exception:
                pass
        if self._task is not None:
            if not self._task.done() and self._task.get_loop() is running_loop:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        self.connected = False

    async def set_enabled(self, enabled: bool, start_poller: bool = True) -> Dict[str, Any]:
        target = bool(enabled)
        self.enabled = target
        if target:
            await self.refresh_once()
            if start_poller:
                await self.start()
        else:
            await self.stop()
            self.last_error = None
        return self.get_status()

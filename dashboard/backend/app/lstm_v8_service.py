import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from .lstm_v8_client import LSTMV8Client

logger = logging.getLogger(__name__)


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


class LSTMV8Service:
    """Polls LSTM V8 independently, caches its latest state, and enforces enable/disable state."""

    SCHEMA_INFO: Dict[str, Any] = {
        "endpoint": "GET /dashboard/state",
        "lookback_minutes": 60,
        "horizons_minutes": [1, 15, 30, 60],
        "feature_count": 8,
        "features": [
            "cpu_utilisation_pct_mean",
            "memory_used_pct_mean",
            "network_rx_mib_s_mean",
            "network_tx_mib_s_mean",
            "disk_read_mib_s_mean",
            "disk_write_mib_s_mean",
            "node_load1_per_core_mean",
            "iowait_pct_mean",
        ],
        "warning_components": [
            "stress_60m",
            "residual_z",
            "residual_z_threshold",
            "residual_z_exceeded",
            "drift_z",
        ],
        "semantics_note": (
            "Outputs short-horizon telemetry forecasts (1m/15m/30m/60m) and a combined residual/drift "
            "warning score; does not represent failure probability."
        ),
    }

    def __init__(
        self,
        poll_interval_sec: float = 5.0,
        stale_after_sec: float = 60.0,
        client: Optional[LSTMV8Client] = None,
    ) -> None:
        self.client = client or LSTMV8Client()
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

    def _record_history(self, state: Dict[str, Any], fetched_at: str) -> None:
        nodes = state.get("nodes") if isinstance(state, dict) else None
        if not isinstance(nodes, dict):
            return
        for node_id, payload in nodes.items():
            if not isinstance(payload, dict):
                continue
            warning = payload.get("latest_warning") or {}
            comp = warning.get("components") or {}
            eval_ts = warning.get("evaluated_at_timestamp_utc") or fetched_at
            buf = self.history.setdefault(node_id, deque(maxlen=180))
            if buf and warning.get("evaluated_at_timestamp_utc") and buf[-1].get("timestamp_utc") == eval_ts:
                continue
            buf.append(
                {
                    "timestamp_utc": eval_ts,
                    "warning_score": warning.get("warning_score"),
                    "warning_threshold": warning.get("warning_threshold"),
                    "is_warning": warning.get("is_warning"),
                    "status": warning.get("status"),
                    "stress_60m": comp.get("stress_60m"),
                    "residual_z": comp.get("residual_z"),
                    "drift_z": comp.get("drift_z"),
                }
            )

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

        return {
            "enabled": self.enabled,
            "configured": configured,
            "connected": connected,
            "status": status,
            "stale": stale,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "last_success_utc": self.last_success_utc,
            "last_error": error,
            "state": self.latest_state,
            "schema": self.SCHEMA_INFO,
        }

    async def refresh_once(self) -> None:
        if not self.enabled:
            return

        configured, config_error = self.client.configuration_status()
        if not configured:
            self.connected = False
            self.last_error = config_error
            if self._last_logged_unconfigured != config_error:
                logger.info("LSTM V8 polling skipped: %s", config_error)
                self._last_logged_unconfigured = config_error
            return

        self._last_logged_unconfigured = None
        try:
            state = await asyncio.to_thread(self.client.get_dashboard_state)
            now_iso = datetime.now(timezone.utc).isoformat()
            self.latest_state = state
            self.last_success_utc = now_iso
            self.last_error = None
            self.connected = True
            self._record_history(state, now_iso)
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            logger.warning("LSTM V8 state refresh failed: %s", exc)

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

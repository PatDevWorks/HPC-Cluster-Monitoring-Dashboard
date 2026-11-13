
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .lstm_v8_client import LSTMV8Client

logger = logging.getLogger(__name__)


class LSTMV8Service:
    """Polls LSTM V8 independently and caches its latest successful state."""

    def __init__(self, poll_interval_sec: float = 5.0) -> None:
        self.client = LSTMV8Client()
        self.poll_interval_sec = max(2.0, poll_interval_sec)

        self.latest_state: Optional[Dict[str, Any]] = None
        self.last_success_utc: Optional[str] = None
        self.last_error: Optional[str] = None

        self.connected = False
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "last_success_utc": self.last_success_utc,
            "last_error": self.last_error,
            "state": self.latest_state,
        }

    async def refresh_once(self) -> None:
        try:
            state = await asyncio.to_thread(
                self.client.get_dashboard_state
            )

            self.latest_state = state
            self.last_success_utc = datetime.now(
                timezone.utc
            ).isoformat()

            self.last_error = None
            self.connected = True

        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)

            logger.warning(
                "LSTM V8 state refresh failed: %s",
                exc,
            )

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.refresh_once()

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.poll_interval_sec,
                )
            except asyncio.TimeoutError:
                pass

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._poll_loop()
        )

    async def stop(self) -> None:
        self._stop_event.set()

        if self._task:
            await self._task
            self._task = None

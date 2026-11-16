import os
from typing import Any, Dict, Optional, Tuple
import requests

from .config import LSTM_V8_API_KEY, LSTM_V8_API_URL, LSTM_V8_TIMEOUT


class LSTMV8Client:
    """Read-only client for the deployed LSTM V8 inference API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._explicit_base_url = base_url
        self._explicit_api_key = api_key
        self._explicit_timeout = timeout

    @property
    def base_url(self) -> str:
        raw = self._explicit_base_url if self._explicit_base_url is not None else os.getenv("LSTM_V8_API_URL", LSTM_V8_API_URL or "http://127.0.0.1:8102")
        return str(raw or "http://127.0.0.1:8102").strip().rstrip("/")

    @property
    def api_key(self) -> str:
        raw = self._explicit_api_key if self._explicit_api_key is not None else os.getenv("LSTM_V8_API_KEY", LSTM_V8_API_KEY)
        return str(raw or "").strip()

    @property
    def timeout(self) -> float:
        if self._explicit_timeout is not None:
            return float(self._explicit_timeout)
        raw = os.getenv("LSTM_V8_TIMEOUT", "").strip()
        return float(raw) if raw else float(LSTM_V8_TIMEOUT)

    def configuration_status(self) -> Tuple[bool, Optional[str]]:
        if not self.base_url:
            return False, "LSTM_V8_API_URL is not configured"
        if not self.api_key:
            return False, "LSTM_V8_API_KEY is not configured"
        return True, None

    def get_dashboard_state(self) -> Dict[str, Any]:
        configured, err = self.configuration_status()
        if not configured:
            raise RuntimeError(err or "LSTM V8 client is not configured")

        response = requests.get(
            f"{self.base_url}/dashboard/state",
            headers={"X-API-Key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("LSTM V8 API returned an invalid response")
        return data

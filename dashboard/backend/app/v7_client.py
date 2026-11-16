import os
from typing import Any, Dict, Optional, Tuple
import requests

from .config import V7_API_KEY, V7_API_URL, V7_TIMEOUT


class V7Client:
    """Protected read-only client for the cluster-side V7 Isolation Forest API."""

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
        raw = self._explicit_base_url if self._explicit_base_url is not None else os.getenv("V7_API_URL", V7_API_URL)
        return str(raw or "").strip().rstrip("/")

    @property
    def api_key(self) -> str:
        raw = self._explicit_api_key if self._explicit_api_key is not None else os.getenv("V7_API_KEY", V7_API_KEY)
        return str(raw or "").strip()

    @property
    def timeout(self) -> float:
        if self._explicit_timeout is not None:
            return float(self._explicit_timeout)
        raw = os.getenv("V7_TIMEOUT", "").strip()
        return float(raw) if raw else float(V7_TIMEOUT)

    def configuration_status(self) -> Tuple[bool, Optional[str]]:
        if not self.base_url:
            return False, "V7_API_URL is not configured"
        if not self.api_key:
            return False, "V7_API_KEY is not configured"
        return True, None

    def get_latest_scores(self) -> Any:
        configured, err = self.configuration_status()
        if not configured:
            raise RuntimeError(err or "V7 API client is not configured")

        response = requests.get(
            f"{self.base_url}/scores/latest",
            headers={"X-API-Key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, (dict, list)):
            raise ValueError("V7 API /scores/latest returned an unexpected JSON type")
        return data


import os
import requests
from typing import Any, Dict


class LSTMV8Client:
    """Read-only client for the deployed LSTM V8 inference API."""

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "LSTM_V8_API_URL",
            "http://127.0.0.1:8102",
        ).rstrip("/")

        self.api_key = os.getenv("LSTM_V8_API_KEY", "").strip()
        self.timeout = float(os.getenv("LSTM_V8_TIMEOUT", "5"))

    def get_dashboard_state(self) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("LSTM_V8_API_KEY is not configured")

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

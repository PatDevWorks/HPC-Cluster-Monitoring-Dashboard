import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database
from app.main import (
    app,
    orchestrator,
    require_admin_role,
    require_authenticated_user,
    require_diagnostic_access,
)
from app.v7_client import V7Client
from app.v7_service import V7Service, normalize_v7_payload
from app.lstm_v8_client import LSTMV8Client
from app.lstm_v8_service import LSTMV8Service


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class Phase2ModelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._orig_db_path = database.DB_PATH
        database.DB_PATH = Path(cls._tmpdir.name) / "test_phase2.db"
        database.init_db()
        app.dependency_overrides[require_authenticated_user] = lambda: {
            "id": 1,
            "email": "admin@spu.local",
            "role": "super_admin",
        }
        app.dependency_overrides[require_admin_role] = lambda: {
            "id": 1,
            "email": "admin@spu.local",
            "role": "super_admin",
        }
        app.dependency_overrides[require_diagnostic_access] = lambda: {
            "id": 1,
            "email": "admin@spu.local",
            "role": "super_admin",
        }
        cls.orig_v7 = orchestrator.v7
        cls.orig_lstm = orchestrator.lstm_v8
        cls.orig_connector_mode = orchestrator.connector.mode
        cls.orig_connector_mode_explicit = orchestrator.connector.mode_explicitly_set
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        orchestrator.v7 = cls.orig_v7
        orchestrator.lstm_v8 = cls.orig_lstm
        orchestrator.connector.mode = cls.orig_connector_mode
        orchestrator.connector.mode_explicitly_set = cls.orig_connector_mode_explicit
        cls.client.close()
        app.dependency_overrides.clear()
        database.DB_PATH = cls._orig_db_path
        cls._tmpdir.cleanup()

    def setUp(self) -> None:
        database.update_app_settings({"v7_enabled": True, "lstm_v8_enabled": True})
        orchestrator.v7 = V7Service(
            poll_interval_sec=5.0,
            client=V7Client(base_url="http://127.0.0.1:8103", api_key="secret-v7-key", timeout=2.0),
        )
        orchestrator.lstm_v8 = LSTMV8Service(
            poll_interval_sec=5.0,
            client=LSTMV8Client(base_url="http://127.0.0.1:8102", api_key="secret-lstm-key", timeout=2.0),
        )

    def test_v7_payload_normalization_variants(self) -> None:
        list_payload = {
            "model_version": "v7_global_iforest_per_node_thresholds",
            "feature_count": 28,
            "scores": [
                {
                    "node": "headnode",
                    "timestamp_utc": "2026-11-13T01:00:00Z",
                    "anomaly_score": 0.7123,
                    "threshold": 0.65,
                    "is_anomaly": 1,
                    "classification": "anomaly",
                },
                {
                    "node": "compute001",
                    "timestamp_utc": "2026-11-13T01:00:00Z",
                    "anomaly_score": 0.412,
                    "threshold": 0.62,
                    "is_anomaly": 0,
                    "classification": "normal",
                },
            ],
        }
        norm_a = normalize_v7_payload(list_payload)
        self.assertEqual(norm_a["feature_count"], 28)
        self.assertEqual(norm_a["nodes"]["headnode"]["node_id"], "head-node")
        self.assertTrue(norm_a["nodes"]["headnode"]["is_anomaly"])
        self.assertEqual(norm_a["nodes"]["compute001"]["node_id"], "compute-01")
        self.assertFalse(norm_a["nodes"]["compute001"]["is_anomaly"])

        dict_payload = {
            "nodes": {
                "compute002": {
                    "scored_at_utc": "2026-11-13T01:05:00Z",
                    "score": 0.68,
                    "threshold": 0.64,
                }
            }
        }
        norm_b = normalize_v7_payload(dict_payload)
        self.assertTrue(norm_b["nodes"]["compute002"]["is_anomaly"])
        self.assertEqual(norm_b["nodes"]["compute002"]["classification"], "anomaly")

    def test_v7_and_lstm_clients_and_secret_redaction(self) -> None:
        v7_sample = {
            "model_version": "v7_global_iforest_per_node_thresholds",
            "feature_count": 28,
            "scores": [
                {
                    "node_id": "headnode",
                    "timestamp_utc": "2026-11-13T02:10:00Z",
                    "anomaly_score": 0.73,
                    "threshold": 0.64,
                    "is_anomaly": True,
                    "classification": "anomaly",
                }
            ],
        }
        lstm_sample = {
            "nodes": {
                "compute001": {
                    "history_count": 60,
                    "required_observations": 60,
                    "forecast_pending_validation": False,
                    "latest_forecast": {
                        "generated_at_utc": "2026-11-13T02:10:00Z",
                        "horizons": [
                            {"horizon_minutes": 15, "predicted_metrics": {"cpu_utilisation_pct_mean": 54.2}}
                        ],
                    },
                    "latest_warning": {
                        "status": "WARNING",
                        "is_warning": True,
                        "warning_score": 3.42,
                        "warning_threshold": 3.0,
                        "evaluated_at_timestamp_utc": "2026-11-13T02:10:00Z",
                        "components": {"stress_60m": 0.7, "residual_z": 3.42, "drift_z": 1.1},
                    },
                }
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/scores/latest"):
                self.assertEqual(headers.get("X-API-Key"), "secret-v7-key")
                return _FakeResponse(v7_sample)
            if url.endswith("/dashboard/state"):
                self.assertEqual(headers.get("X-API-Key"), "secret-lstm-key")
                return _FakeResponse(lstm_sample)
            raise AssertionError(f"Unexpected URL {url}")

        with patch("app.v7_client.requests.get", side_effect=fake_get), patch(
            "app.lstm_v8_client.requests.get", side_effect=fake_get
        ):
            r1 = self.client.post("/api/models/v7/refresh")
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r1.json()["status"], "connected")

            r2 = self.client.post("/api/models/lstm-v8/refresh")
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r2.json()["status"], "connected")

        # Make the fixture deterministic even if a local Prometheus server is reachable.
        orchestrator.connector.mode = "live_cluster_sim"
        orchestrator.connector.mode_explicitly_set = True
        orchestrator.latest_snapshot = {}
        snap = self.client.get("/api/state").json()
        self.assertEqual(snap["kpis"]["nodes_with_v7_anomaly"], 1)
        self.assertEqual(snap["kpis"]["nodes_with_lstm_warning"], 1)

        hn = next(n for n in snap["nodes"] if n["node_id"] == "head-node")
        self.assertEqual(hn["v7_detection"]["anomaly_score"], 0.73)
        self.assertTrue(hn["v7_detection"]["is_anomaly"])

        c1 = next(n for n in snap["nodes"] if n["node_id"] == "compute-01")
        self.assertTrue(c1["lstm_v8_status"]["latest_warning"]["is_warning"])

        # Credentials never leaked to API consumers
        raw_settings_txt = self.client.get("/api/settings").text
        raw_models_txt = self.client.get("/api/models/status").text
        self.assertNotIn("secret-v7-key", raw_settings_txt)
        self.assertNotIn("secret-lstm-key", raw_settings_txt)
        self.assertNotIn("secret-v7-key", raw_models_txt)
        self.assertNotIn("secret-lstm-key", raw_models_txt)

        # Disabling stops active anomaly reporting while preserving cached data as stale/disabled
        r_off_v7 = self.client.post("/api/models/v7/toggle", json={"enabled": False})
        self.assertEqual(r_off_v7.status_code, 200)
        self.assertFalse(r_off_v7.json()["v7_enabled"])
        self.assertEqual(r_off_v7.json()["v7"]["status"], "disabled")
        self.assertTrue(r_off_v7.json()["v7"]["stale"])

        r_off_lstm = self.client.post("/api/models/lstm-v8/toggle", json={"enabled": False})
        self.assertEqual(r_off_lstm.status_code, 200)
        self.assertFalse(r_off_lstm.json()["lstm_v8_enabled"])
        self.assertEqual(r_off_lstm.json()["lstm_v8"]["status"], "disabled")

        snap_off = self.client.get("/api/state").json()
        self.assertEqual(snap_off["kpis"]["nodes_with_v7_anomaly"], 0)
        self.assertEqual(snap_off["kpis"]["nodes_with_lstm_warning"], 0)
        self.assertEqual(snap_off["kpis"]["v7_api_status"], "disabled")
        self.assertEqual(snap_off["kpis"]["lstm_v8_api_status"], "disabled")

        # Persistence verified in database settings
        settings_after = database.get_app_settings()
        self.assertFalse(settings_after["v7_enabled"])
        self.assertFalse(settings_after["lstm_v8_enabled"])

    def test_poller_starts_and_stops_on_toggle(self) -> None:
        async def _run():
            v7 = V7Service(
                poll_interval_sec=2.0,
                client=V7Client(base_url="http://127.0.0.1:8103", api_key="k", timeout=1.0),
            )
            with patch("app.v7_client.requests.get", return_value=_FakeResponse({"scores": []})):
                await v7.set_enabled(True, start_poller=True)
                self.assertIsNotNone(v7._task)
                self.assertFalse(v7._task.done())
                self.assertTrue(v7.connected)
                await v7.set_enabled(False, start_poller=True)
                self.assertIsNone(v7._task)
                self.assertFalse(v7.connected)

        asyncio.run(_run())

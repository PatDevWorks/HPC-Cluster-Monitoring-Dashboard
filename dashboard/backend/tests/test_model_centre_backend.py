import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database
from app.auth_dependencies import get_current_user
from app.main import app
from app.model_registry_router import require_admin
from app.llm_service import LLMProviderError, generate_text


class ModelCentreBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.original_db_path = database.DB_PATH
        database.DB_PATH = Path(cls.tmpdir.name) / "model_centre_test.db"
        database.init_db()
        app.dependency_overrides[get_current_user] = lambda: {
            "id": 1, "email": "admin@example.test", "role": "super_admin"
        }
        app.dependency_overrides[require_admin] = lambda: {
            "id": 1, "email": "admin@example.test", "role": "super_admin"
        }
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        database.DB_PATH = cls.original_db_path
        cls.tmpdir.cleanup()

    def setUp(self):
        with contextlib.closing(database.get_conn()) as conn:
            conn.execute("DELETE FROM model_score_observations")
            conn.execute("DELETE FROM model_registry WHERE model_key NOT IN ('v7', 'lstm_v8', 'gemini')")
            conn.execute("DELETE FROM alert_episodes")
            conn.execute("DELETE FROM gemini_conversations")
            conn.execute("DELETE FROM ai_conversation_metadata")
            conn.commit()

    def test_registry_uses_runtime_fields_without_claiming_unknown_model_loaded(self):
        response = self.client.get("/api/models/registry")
        self.assertEqual(response.status_code, 200)
        by_key = {model["model_key"]: model for model in response.json()}
        self.assertIn("v7", by_key)
        self.assertIn("lstm_v8", by_key)
        self.assertIn("api_reachable", by_key["v7"]["runtime"])
        self.assertIsNone(by_key["v7"]["runtime"]["model_loaded"])

    def test_observation_filters_and_retention_preserve_incidents(self):
        old = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        database.record_model_observation("v7", "compute-01", old, 0.9, 0.7, True, "anomaly", {"x": 1})
        database.record_model_observation("v7", "compute-01", recent, 0.1, 0.7, False, "normal", {"x": 2})
        database.upsert_alert_episode(
            node_id="compute-01", priority="P2", event_type="test",
            alert_source="telemetry", title="Keep me", summary="incident",
            recommended_checks="", timestamp_utc=recent, evidence=[], data_mode="live",
        )

        filtered = self.client.get("/api/models/observations", params={"model_name": "v7", "flagged": "false"})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.json()), 1)
        self.assertFalse(filtered.json()[0]["flagged"])

        cleaned = self.client.put("/api/models/retention", json={"retention_days": 30})
        self.assertEqual(cleaned.status_code, 200)
        self.assertEqual(cleaned.json()["deleted_count"], 1)
        self.assertEqual(len(database.list_model_observations(model_name="v7")), 1)
        with contextlib.closing(database.get_conn()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM alert_episodes").fetchone()[0], 1)

    def test_retention_rejects_unsupported_window(self):
        response = self.client.put("/api/models/retention", json={"retention_days": 7})
        self.assertEqual(response.status_code, 422)

    def test_new_router_requires_authentication(self):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = self.client.get("/api/models/registry")
            self.assertEqual(response.status_code, 401)
        finally:
            app.dependency_overrides[get_current_user] = lambda: {
                "id": 1, "email": "admin@example.test", "role": "super_admin"
            }

    def test_openai_provider_uses_responses_api_and_never_logs_or_returns_key(self):
        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Evidence-based answer"}]}]}

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret", "OPENAI_MODEL": "configured-test-model"}), patch(
            "app.llm_service.requests.post", return_value=FakeResponse()
        ) as post:
            result = generate_text("openai", "Use supplied evidence only.")
        self.assertEqual(result["answer"], "Evidence-based answer")
        self.assertEqual(result["model"], "configured-test-model")
        self.assertNotIn("test-secret", str(result))
        self.assertIn("/v1/responses", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["timeout"], 30.0)

    def test_openai_rate_limit_is_reported_without_provider_response_body(self):
        class FakeResponse:
            status_code = 429

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret", "OPENAI_MODEL": "configured-test-model"}), patch(
            "app.llm_service.requests.post", return_value=FakeResponse()
        ):
            with self.assertRaises(LLMProviderError) as raised:
                generate_text("openai", "question")
        self.assertEqual(raised.exception.status_code, 429)
        self.assertNotIn("test-secret", str(raised.exception))

    def test_ai_conversation_crud_and_owner_scoping(self):
        created = self.client.post("/api/ai/conversations", json={"provider": "gemini"})
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["session_id"]
        database.append_gemini_message(session_id, "admin@example.test", "user", "chat", "Explain node health", {})
        database.append_gemini_message(session_id, "admin@example.test", "assistant", "chat", "Evidence summary", {"provider": "gemini", "model": "test-model"})

        listed = self.client.get("/api/ai/conversations").json()["conversations"]
        conversation = next(item for item in listed if item["session_id"] == session_id)
        self.assertEqual(conversation["message_count"], 2)
        self.assertEqual(conversation["provider"], "gemini")

        app.dependency_overrides[get_current_user] = lambda: {
            "id": 2, "email": "viewer@example.test", "role": "viewer"
        }
        try:
            foreign_history = self.client.get(f"/api/ai/history?session_id={session_id}").json()
            self.assertEqual(foreign_history["messages"], [])
            self.assertIsNone(foreign_history["conversation"])
            self.assertEqual(self.client.get("/api/ai/conversations").json()["conversations"], [])
        finally:
            app.dependency_overrides[get_current_user] = lambda: {
                "id": 1, "email": "admin@example.test", "role": "super_admin"
            }

        renamed = self.client.patch(f"/api/ai/conversations/{session_id}", json={"title": "Node review", "provider": "openai"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["conversation"]["title"], "Node review")
        self.assertEqual(renamed.json()["conversation"]["provider"], "openai")
        self.assertEqual(self.client.delete(f"/api/ai/conversations/{session_id}/messages").status_code, 200)
        self.assertEqual(self.client.get(f"/api/ai/history?session_id={session_id}").json()["messages"], [])
        self.assertEqual(self.client.delete(f"/api/ai/conversations/{session_id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()

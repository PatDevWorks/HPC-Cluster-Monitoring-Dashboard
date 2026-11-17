import contextlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database
from app.auth_service import hash_password
from app.main import (
    app,
    orchestrator,
    require_admin_role,
    require_authenticated_user,
    require_diagnostic_access,
)


class _FakeGeminiResponse:
    def __init__(self, text: str):
        self.text = text
        self.candidates = []


class _FakeGeminiModels:
    def __init__(self, reply: str):
        self._reply = reply

    def generate_content(self, model=None, contents=None, config=None):
        return _FakeGeminiResponse(self._reply)


class _FakeGeminiClient:
    def __init__(self, reply: str):
        self.models = _FakeGeminiModels(reply)


class Phase3To7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._orig_db_path = database.DB_PATH
        database.DB_PATH = Path(cls._tmpdir.name) / "test_phase3to7.db"
        database.init_db()
        with contextlib.closing(database.get_conn()) as conn:
            conn.execute(
                """
                INSERT INTO auth_users (
                    email, full_name, password_hash, role, is_active,
                    email_verified_utc, created_utc, updated_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "super@spu.local",
                    "Super Admin",
                    hash_password("SuperSecret123!"),
                    "super_admin",
                    1,
                    "2026-11-13T00:00:00Z",
                    "2026-11-13T00:00:00Z",
                    "2026-11-13T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO auth_users (
                    email, full_name, password_hash, role, is_active,
                    email_verified_utc, created_utc, updated_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "viewer@spu.local",
                    "Cluster Viewer",
                    hash_password("ViewerPass123!"),
                    "viewer",
                    1,
                    "2026-11-13T00:00:00Z",
                    "2026-11-13T00:00:00Z",
                    "2026-11-13T00:00:00Z",
                ),
            )
            conn.commit()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        app.dependency_overrides.clear()
        database.DB_PATH = cls._orig_db_path
        cls._tmpdir.cleanup()

    def _override_admin(self, user_id=1, role="super_admin", email="super@spu.local"):
        user = {"id": user_id, "email": email, "role": role, "full_name": "Super Admin"}
        app.dependency_overrides[require_authenticated_user] = lambda: user
        app.dependency_overrides[require_admin_role] = lambda: user
        app.dependency_overrides[require_diagnostic_access] = lambda: user

    def test_experiments_and_model_comparison_evaluation(self) -> None:
        self._override_admin()

        # Record observations and episodes inside fault and benign experiment windows
        database.record_model_observation(
            model_name="v7",
            node_id="compute-01",
            observation_utc="2026-11-10T10:02:00Z",
            score=0.74,
            threshold=0.65,
            flagged=True,
            classification="anomaly",
        )
        database.record_model_observation(
            model_name="lstm_v8",
            node_id="compute-01",
            observation_utc="2026-11-10T10:06:00Z",
            score=3.4,
            threshold=3.0,
            flagged=True,
            classification="WARNING",
        )
        database.upsert_alert_episode(
            node_id="compute-02",
            priority="P2",
            event_type="cpu_sustained_high",
            alert_source="telemetry",
            title="[P2] compute-02: High CPU",
            summary="Benign benchmark run",
            recommended_checks="top",
            timestamp_utc="2026-11-11T14:05:00Z",
            evidence=[{"source": "telemetry", "metric": "cpu_utilization_percent", "value": 93.0}],
            data_mode="live_cluster_sim",
        )

        # Positive failure injection experiment on compute-01
        r_pos = self.client.post(
            "/api/experiments",
            json={
                "name": "Nov Memory Stress Injection",
                "category": "november_experiment",
                "node_id": "compute-01",
                "fault_type": "memory_exhaustion",
                "label": "positive_fault",
                "start_utc": "2026-11-10T10:00:00Z",
                "end_utc": "2026-11-10T10:20:00Z",
                "workload_condition": "high_load",
                "notes": "Controlled stress run",
            },
        )
        self.assertEqual(r_pos.status_code, 200)

        # Benign benchmark workload on compute-02 (should measure telemetry false alarm)
        r_ben = self.client.post(
            "/api/experiments",
            json={
                "name": "HPL Benign Benchmark",
                "category": "planned_workload",
                "node_id": "compute-02",
                "fault_type": "benchmark",
                "label": "benign_workload",
                "start_utc": "2026-11-11T14:00:00Z",
                "end_utc": "2026-11-11T14:30:00Z",
                "workload_condition": "benchmark",
            },
        )
        self.assertEqual(r_ben.status_code, 200)

        ev = self.client.get("/api/models/evaluation").json()
        self.assertTrue(ev["has_labelled_experiments"])
        self.assertEqual(ev["positive_experiments_count"], 1)
        self.assertEqual(ev["benign_experiments_count"], 1)
        self.assertEqual(ev["detector_evaluation"]["v7"]["detected_events"], 1)
        self.assertEqual(ev["detector_evaluation"]["v7"]["detection_coverage_pct"], 100.0)
        self.assertEqual(ev["detector_evaluation"]["v7"]["mean_detection_delay_min"], 2.0)
        self.assertEqual(ev["detector_evaluation"]["lstm_v8"]["mean_detection_delay_min"], 6.0)
        self.assertEqual(ev["detector_evaluation"]["telemetry"]["false_positive_windows"], 1)
        self.assertEqual(ev["detector_evaluation"]["v7"]["false_positive_windows"], 0)

    def test_gemini_ai_intelligence_chat_investigate_and_analytics(self) -> None:
        self._override_admin()

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-gemini-key", "GEMINI_MODEL": "gemini-2.5-flash"}), patch(
            "app.llm_service.genai.Client",
            return_value=_FakeGeminiClient("## Observed Telemetry\nNodes nominal.\n## Hypotheses\nNone."),
        ):
            r_chat = self.client.post(
                "/api/ai/chat",
                json={"question": "Summarize current cluster status", "session_id": "test-sess"},
            )
            self.assertEqual(r_chat.status_code, 200)
            self.assertIn("Observed Telemetry", r_chat.json()["answer"])

            r_inv = self.client.post(
                "/api/ai/investigate-incident",
                json={"node_id": "head-node", "question": "Check headnode telemetry", "session_id": "test-sess"},
            )
            self.assertEqual(r_inv.status_code, 200)

            r_ana = self.client.post(
                "/api/ai/query-analytics",
                json={"question": "Compare V7 vs threshold alarms", "range_key": "24h", "session_id": "test-sess"},
            )
            self.assertEqual(r_ana.status_code, 200)

            r_hist = self.client.get("/api/ai/history?session_id=test-sess")
            self.assertEqual(r_hist.status_code, 200)
            self.assertEqual(len(r_hist.json()["messages"]), 6)

    def test_terminal_toggle_audit_monitoring_export_alerts_users_and_backups(self) -> None:
        self._override_admin()

        # Terminal disabled by default -> 403 + recorded in audit
        database.update_app_settings({"restricted_terminal_enabled": False})
        r_blk = self.client.post("/api/terminal/exec", json={"node_id": "head-node", "command": "uptime"})
        self.assertEqual(r_blk.status_code, 403)

        # Enable restricted terminal -> executes cleanly & records audit entry
        self.client.put("/api/settings", json={"restricted_terminal_enabled": True})
        r_ok = self.client.post("/api/terminal/exec", json={"node_id": "head-node", "command": "uptime"})
        self.assertEqual(r_ok.status_code, 200)
        aud = self.client.get("/api/terminal/audit").json()["entries"]
        self.assertGreaterEqual(len(aud), 2)
        self.assertFalse(aud[-1]["allowed"])
        self.assertTrue(aud[0]["allowed"])

        # CSV export & filtered alerts with resolution notes
        orchestrator.step_once()
        r_csv = self.client.get("/api/monitoring/export?range_key=1h&node_id=compute-01")
        self.assertEqual(r_csv.status_code, 200)
        self.assertIn("timestamp_utc,data_mode,node_id", r_csv.text)

        eps = self.client.get("/api/alerts").json()["episodes"]
        if eps:
            ep_id = eps[0]["id"]
            r_act = self.client.post(
                f"/api/alerts/{ep_id}/action",
                json={"action": "acknowledge", "note": "Investigating via unit test"},
            )
            self.assertEqual(r_act.status_code, 200)
            self.assertEqual(r_act.json()["resolution_note"], "Investigating via unit test")

        # User management & backups
        users = self.client.get("/api/admin/users").json()["users"]
        self.assertEqual(len(users), 2)
        viewer = next(u for u in users if u["email"] == "viewer@spu.local")
        r_patch = self.client.patch(f"/api/admin/users/{viewer['id']}", json={"role": "admin"})
        self.assertEqual(r_patch.status_code, 200)
        self.assertEqual(r_patch.json()["user"]["role"], "admin")

        r_db = self.client.get("/api/admin/backup/database")
        self.assertEqual(r_db.status_code, 200)
        self.assertTrue(r_db.content.startswith(b"SQLite format 3"))

        r_cfg = self.client.get("/api/admin/backup/settings")
        self.assertEqual(r_cfg.status_code, 200)
        self.assertIn("settings", r_cfg.json())

        # Auth check enforced on /api/reports/ai/{id}
        app.dependency_overrides.clear()
        r_unauth = self.client.get("/api/reports/ai/999")
        self.assertEqual(r_unauth.status_code, 401)

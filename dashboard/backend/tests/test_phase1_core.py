import contextlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database
from app.alert_engine import SmartAlertEngine
from app.main import (
    app,
    orchestrator,
    require_admin_role,
    require_authenticated_user,
    require_diagnostic_access,
)


class Phase1CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._orig_db_path = database.DB_PATH
        database.DB_PATH = Path(cls._tmpdir.name) / "test_hpc_aiops.db"
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
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        app.dependency_overrides.clear()
        database.DB_PATH = cls._orig_db_path
        cls._tmpdir.cleanup()

    def test_placeholder_ml_engine_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            __import__("app.ml_engine")

        with contextlib.closing(database.get_conn()) as conn:
            tbl = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ml_engine_settings'"
            ).fetchone()
            self.assertIsNone(tbl)

    def test_roi_totals_not_fabricated_on_alerts(self) -> None:
        database.upsert_alert_episode(
            node_id="compute-01",
            priority="P1",
            event_type="memory_pressure_critical",
            alert_source="telemetry",
            title="[P1] compute-01: Memory critical",
            summary="Test summary",
            recommended_checks="free -h",
            timestamp_utc="2026-11-13T02:00:00Z",
            evidence=[{"source": "telemetry", "metric": "memory_used_percent", "value": 97.2}],
            data_mode="live_cluster_sim",
        )
        roi = database.get_roi_totals()
        self.assertEqual(roi["proactive_drains"], 0)
        self.assertEqual(roi["core_hours_saved"], 0.0)
        self.assertFalse(roi["power_metrics_available"])

    def test_alert_engine_typed_sources_and_states(self) -> None:
        engine = SmartAlertEngine()
        base_node = {
            "node_id": "compute-01",
            "ip": "10.100.0.66",
            "up": 1,
            "planned_maintenance": 0,
            "slurm_state": "IDLE",
            "cpu_utilization_percent": 32.0,
            "cpu_iowait_percent": 1.2,
            "memory_used_percent": 44.0,
            "scratch_used_percent": 20.0,
            "root_used_percent": 30.0,
            "normalized_load1": 0.35,
            "network_errors_per_second": 0.0,
            "mpi_straggler_score": 0.05,
        }
        res_ok = engine.evaluate(base_node, "2026-11-13T02:00:00Z", "live_cluster_sim")
        self.assertEqual(res_ok["health_status"], "healthy")
        self.assertEqual(res_ok["alert_priority"], "OK")

        # Stale telemetry detection
        res_stale = engine.evaluate(
            base_node,
            "2026-11-13T02:02:30Z",
            "live_prometheus",
            telemetry_age_seconds=180.0,
        )
        self.assertEqual(res_stale["health_status"], "stale")

        # Maintenance state from Slurm DRAIN
        res_maint = engine.evaluate(
            {**base_node, "slurm_state": "DRAIN"},
            "2026-11-13T02:03:00Z",
            "live_prometheus",
        )
        self.assertEqual(res_maint["health_status"], "maintenance")
        self.assertFalse(res_maint["alert_active"])

        # Separate V7 + LSTM signals (2 ticks persistence)
        engine.reset()
        for ts in ("2026-11-13T02:04:00Z", "2026-11-13T02:05:00Z"):
            res_ml = engine.evaluate(
                base_node,
                ts,
                "live_prometheus",
                v7_result={"is_anomaly": True, "anomaly_score": 0.71, "threshold": 0.66},
                lstm_result={"is_warning": True, "warning_score": 0.14, "warning_threshold": 0.09},
            )
        self.assertTrue(res_ml["alert_active"])
        self.assertEqual(res_ml["alert_priority"], "P2")
        sources = {ev["source"] for ev in res_ml["evidence"]}
        self.assertEqual(sources, {"v7", "lstm_v8"})

    def test_prometheus_offline_does_not_raise_false_node_alerts_and_resolves_aliases(self) -> None:
        engine = SmartAlertEngine()
        base_offline = {
            "node_id": "compute-01",
            "ip": "10.100.0.66",
            "up": 0,
            "planned_maintenance": 0,
            "slurm_state": "UNKNOWN (PROMETHEUS OFFLINE)",
            "prometheus_offline": True,
        }
        res_prom_down = engine.evaluate(base_offline, "2026-11-13T17:05:00Z", "live_prometheus")
        self.assertEqual(res_prom_down["health_status"], "offline")
        self.assertFalse(res_prom_down["alert_active"])
        self.assertEqual(res_prom_down["alert_priority"], "OK")

        # Genuine single-node exporter failure while Prometheus is online must still raise P1
        genuine_down = {
            "node_id": "compute001",
            "ip": "10.100.0.66",
            "up": 0,
            "planned_maintenance": 0,
            "slurm_state": "ONLINE",
            "prometheus_offline": False,
        }
        res_real_down = engine.evaluate(genuine_down, "2026-11-13T17:06:00Z", "live_prometheus")
        self.assertTrue(res_real_down["alert_active"])
        self.assertEqual(res_real_down["alert_priority"], "P1")
        self.assertEqual(res_real_down["event_type"], "node_offline")
        self.assertIn("9100/metrics", res_real_down["recommended_checks"])

        # Hyphenated compute-01 episode resolves when compute001 recovers
        ep_alias = database.upsert_alert_episode(
            node_id="compute-01",
            priority="P1",
            event_type="node_offline",
            alert_source="availability",
            title="[P1] compute-01: Node exporter unreachable (up=0) on compute-01",
            summary="Node exporter unreachable (up=0) on compute-01 | Slurm: ONLINE",
            recommended_checks="curl -sf http://10.100.0.66:9100/metrics",
            timestamp_utc="2026-11-13T17:00:00Z",
            evidence=[{"source": "availability", "metric": "up", "value": 0}],
            data_mode="live_prometheus",
        )
        database.auto_resolve_node_episodes("compute001", "2026-11-13T17:07:00Z")
        # Legacy PROMETHEUS OFFLINE episode auto-resolves even before recovery streak
        ep_legacy = database.upsert_alert_episode(
            node_id="head-node",
            priority="P1",
            event_type="node_offline",
            alert_source="availability",
            title="[P1] head-node: Node exporter unreachable (up=0) on head-node",
            summary="Node exporter unreachable (up=0) on head-node | Slurm: UNKNOWN (PROMETHEUS OFFLINE)",
            recommended_checks="ping -c 2 10.100.0.198",
            timestamp_utc="2026-11-13T17:01:00Z",
            evidence=[{"source": "availability", "metric": "up", "value": 0}],
            data_mode="live_prometheus",
        )
        ep_other = database.upsert_alert_episode(
            node_id="compute003",
            priority="P2",
            event_type="lstm_v8_warning",
            alert_source="lstm_v8",
            title="[P2] compute003: LSTM V8 warning",
            summary="LSTM V8 warning score 0.0845 >= threshold 0.0667 | Slurm: ONLINE",
            recommended_checks="Inspect LSTM V8",
            timestamp_utc="2026-11-13T17:02:00Z",
            evidence=[{"source": "lstm_v8", "metric": "warning_score", "value": 0.0845}],
            data_mode="live_prometheus",
        )
        resolved_count = database.auto_resolve_stale_offline_prometheus_episodes("2026-11-13T17:08:00Z")
        self.assertGreaterEqual(resolved_count, 1)

        with contextlib.closing(database.get_conn()) as conn:
            s_alias = conn.execute("SELECT status FROM alert_episodes WHERE id = ?", (ep_alias["id"],)).fetchone()["status"]
            s_legacy = conn.execute("SELECT status FROM alert_episodes WHERE id = ?", (ep_legacy["id"],)).fetchone()["status"]
            s_other = conn.execute("SELECT status FROM alert_episodes WHERE id = ?", (ep_other["id"],)).fetchone()["status"]
        self.assertEqual(s_alias, "resolved")
        self.assertEqual(s_legacy, "resolved")
        self.assertEqual(s_other, "active")

    def test_api_endpoints_clean_schema(self) -> None:
        orchestrator.alerts.reset()
        r_state = self.client.get("/api/state")
        self.assertEqual(r_state.status_code, 200)
        snap = r_state.json()
        self.assertIn("v7_isolation_forest", snap["model_status"])
        self.assertIn("lstm_v8", snap["model_status"])
        self.assertNotIn("cluster_health_score", snap["kpis"])
        self.assertNotIn("peak_failure_prob_pct", snap["kpis"])
        for node in snap["nodes"]:
            self.assertIn(node["health_status"], {"healthy", "warning", "critical", "offline", "stale", "maintenance"})
            self.assertNotIn("failure_prob_1h", node)
            self.assertNotIn("consensus_count", node)
            self.assertNotIn("node_health_score", node)

        # Legacy model reload endpoint removed
        r_reload = self.client.post("/api/models/reload")
        self.assertIn(r_reload.status_code, (404, 405))

        # Toggle model settings persistently
        r_put = self.client.put("/api/settings", json={"v7_enabled": False, "lstm_v8_enabled": False})
        self.assertEqual(r_put.status_code, 200)
        r_models = self.client.get("/api/models/status")
        self.assertEqual(r_models.status_code, 200)
        mjson = r_models.json()
        self.assertFalse(mjson["v7_isolation_forest"]["enabled"])
        self.assertEqual(mjson["v7_isolation_forest"]["status"], "disabled")
        self.assertFalse(mjson["lstm_v8"]["enabled"])
        self.assertEqual(mjson["lstm_v8"]["status"], "disabled")

        # Restore defaults
        self.client.put("/api/settings", json={"v7_enabled": True, "lstm_v8_enabled": True})

        # Reports preview and metrics endpoint
        r_rep = self.client.get("/api/reports/preview?report_type=ai_predictions&range_minutes=60")
        self.assertEqual(r_rep.status_code, 200)
        self.assertNotIn("peak_failure_prob_pct", r_rep.json()["summary"])

        r_metrics = self.client.get("/metrics")
        self.assertEqual(r_metrics.status_code, 200)
        self.assertIn("hpc_aiops_node_up", r_metrics.text)
        self.assertNotIn("hpc_aiops_failure_prob_1h", r_metrics.text)

    def test_ssh_env_overrides_stale_blank_db_defaults(self) -> None:
        database.update_app_settings({"ssh_host": "", "ssh_port": 22})
        with patch.dict(
            os.environ,
            {"HPC_SSH_HOST": "196.24.241.73", "HPC_SSH_USER": "ubuntu", "HPC_SSH_PORT": "443"},
            clear=False,
        ):
            cfg = database.get_app_settings()
            self.assertEqual(cfg["ssh_host"], "196.24.241.73")
            self.assertEqual(cfg["ssh_port"], 443)

        # Explicit custom DB SSH configuration still wins over env defaults
        database.update_app_settings({"ssh_host": "10.10.10.5", "ssh_port": 2222})
        with patch.dict(
            os.environ,
            {"HPC_SSH_HOST": "196.24.241.73", "HPC_SSH_PORT": "443"},
            clear=False,
        ):
            cfg = database.get_app_settings()
            self.assertEqual(cfg["ssh_host"], "10.10.10.5")
            self.assertEqual(cfg["ssh_port"], 2222)
        database.update_app_settings({"ssh_host": "", "ssh_port": 22})

    def test_live_slurm_snapshot_single_call_and_aliases(self) -> None:
        from app import cluster_connector, slurm_service

        sample_out = (
            "__SINFO_BEGIN__\n"
            "compute001|debug*|idle|8|16016|none\n"
            "compute002|debug*|allocated|8|16016|none\n"
            "__SINFO_RC__=0\n"
            "__SQUEUE_BEGIN__\n"
            "205|cfd-sim|ubuntu|debug|RUNNING|00:12:10|02:00:00|1|8|16G|compute002|None\n"
            "__SQUEUE_RC__=0\n"
            "__SACCT_BEGIN__\n"
            "199|hemelb-phased|ubuntu|debug|TIMEOUT|02:30:17|24|48048M|compute[001-003]|0:0\n"
            "__SACCT_RC__=0\n"
        )
        with patch.object(
            slurm_service,
            "execute_restricted_cluster_command",
            return_value=(True, sample_out, "live_ssh_gateway"),
        ):
            jobs, nodes, src, err = slurm_service.fetch_live_slurm_snapshot()

        self.assertIsNone(err)
        self.assertEqual(src, "live_ssh_gateway")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["job_id"], "205")
        self.assertEqual(jobs[1]["nodes"], ["compute001", "compute002", "compute003"])
        self.assertEqual(nodes["compute001"]["slurm_cpus"], 8)
        self.assertEqual(
            slurm_service.resolve_slurm_nodename("compute-01", nodes),
            "compute001",
        )

        # Verify overlay attaches sinfo across alias compute-01 <-> compute001
        fake_nodes = [{"node_id": "compute-02", "hostname": "compute-02", "slurm_state": "ONLINE"}]
        cluster_connector.ClusterTelemetryConnector._overlay_slurm_sinfo(fake_nodes, nodes)
        self.assertEqual(fake_nodes[0]["slurm_state"], "ALLOCATED")
        self.assertEqual(fake_nodes[0]["partition"], "debug")

        # Verify failure surfaces real Slurm error rather than dropping reason
        err_out = (
            "__SINFO_BEGIN__\n"
            "slurm_load_node error: Unable to contact slurm controller\n"
            "__SINFO_RC__=1\n"
            "__SQUEUE_BEGIN__\n"
            "slurm_load_jobs error: Unable to contact slurm controller\n"
            "__SQUEUE_RC__=1\n"
            "__SACCT_BEGIN__\n"
            "__SACCT_RC__=0\n"
        )
        with patch.object(
            slurm_service,
            "execute_restricted_cluster_command",
            return_value=(True, err_out, "live_ssh_gateway"),
        ):
            jobs_err, nodes_err, src_err, detail_err = slurm_service.fetch_live_slurm_snapshot()
        self.assertIsNone(jobs_err)
        self.assertEqual(nodes_err, {})
        self.assertEqual(src_err, "unavailable")
        self.assertIn("Unable to contact slurm controller", detail_err)


if __name__ == "__main__":
    unittest.main()

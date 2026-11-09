from datetime import datetime, timedelta, timezone
import threading
from typing import Any, Dict, Optional

import requests

from .config import ALERT_POLICY, ALERT_WEBHOOK_URL
from .database import (
    add_system_log,
    auto_resolve_node_episodes,
    get_app_settings,
    upsert_alert_episode,
)


class SmartAlertEngine:
    """
    Multi-tier Priority, Resource Threshold & Persistence Alerting State Machine:
      - P1 Critical: node down (non-maintenance), scratch >= critical%, memory >= critical%,
        temp >= critical°C, or failure_prob_1h >= p1_critical_prob (2-of-2 persistence)
      - P2 Warning: failure_prob_1h >= p2_warning_prob (2-of-2), consensus >= 3/4 (3-of-3),
        memory/temp warning violation, or sustained MPI straggler
      - P3 Informational / Watch: early precursor failure_prob_1h >= p3_watch_prob (2-of-2)
    """

    def __init__(self) -> None:
        self.streaks: Dict[str, Dict[str, int]] = {}
        self.healthy_streaks: Dict[str, int] = {}
        self.last_webhook_sent: Dict[str, datetime] = {}

    def reset(self) -> None:
        self.streaks.clear()
        self.healthy_streaks.clear()
        self.last_webhook_sent.clear()

    def evaluate(
        self,
        node_sample: Dict[str, Any],
        ml_result: Dict[str, Any],
        timestamp_utc: str,
        data_mode: str,
    ) -> Dict[str, Any]:
        policy = dict(ALERT_POLICY)
        try:
            saved_policy = get_app_settings().get("alert_policy")
            if isinstance(saved_policy, dict):
                policy.update(saved_policy)
        except Exception:
            pass

        nid = str(node_sample["node_id"])
        up = int(node_sample.get("up", 1) if node_sample.get("up") is not None else 0)
        planned_maint = int(node_sample.get("planned_maintenance", 0)) == 1
        slurm_state = str(node_sample.get("slurm_state", "ONLINE"))

        if nid not in self.streaks:
            self.streaks[nid] = {"p1": 0, "p2": 0, "p3": 0}

        if planned_maint:
            self.streaks[nid] = {"p1": 0, "p2": 0, "p3": 0}
            return {
                "alert_priority": "MAINTENANCE",
                "persistence_progress": "0/2",
                "alert_active": False,
                "episode_id": None,
            }

        prob_1h = float(ml_result["failure_prob_1h"])
        consensus = int(ml_result["consensus_count"])
        fault_class = str(ml_result["fault_class"])
        scratch = float(
            node_sample.get("scratch_used_percent")
            or node_sample.get("root_used_percent")
            or 0.0
        )
        mem = float(node_sample.get("memory_used_percent") or 0.0)
        temp = node_sample.get("cpu_temperature_celsius")
        temp_val = float(temp) if temp is not None else None
        is_straggler = bool(node_sample.get("is_mpi_straggler", False))

        cond_p1 = (
            (up == 0 and fault_class != "scrape_gap")
            or scratch >= float(policy.get("scratch_critical_percent", 90.0))
            or mem >= float(policy.get("memory_critical_percent", 95.0))
            or (temp_val is not None and temp_val >= float(policy.get("temp_critical_celsius", 86.0)))
            or prob_1h >= float(policy.get("p1_critical_prob", 0.40))
        )
        cond_p2 = (
            cond_p1
            or prob_1h >= float(policy.get("p2_warning_prob", 0.18))
            or mem >= float(policy.get("memory_warning_percent", 88.0))
            or (temp_val is not None and temp_val >= float(policy.get("temp_warning_celsius", 78.0)))
            or consensus >= 3
            or is_straggler
            or (up == 0 and fault_class == "scrape_gap")
        )
        cond_p3 = cond_p2 or prob_1h >= float(policy.get("p3_watch_prob", 0.015)) or consensus >= 2

        st = self.streaks[nid]
        st["p1"] = st["p1"] + 1 if cond_p1 else 0
        st["p2"] = st["p2"] + 1 if cond_p2 else 0
        st["p3"] = st["p3"] + 1 if cond_p3 else 0

        req_p1_p3 = max(1, int(policy.get("persistence_p1_p3", 2)))
        req_p2_anom = max(1, int(policy.get("persistence_p2_anomaly", 3)))

        triggered_priority: Optional[str] = None
        persistence_str = f"0/{req_p1_p3}"

        if (up == 0 and fault_class != "scrape_gap") or st["p1"] >= req_p1_p3:
            triggered_priority = "P1"
            persistence_str = f"{min(st['p1'], req_p1_p3)}/{req_p1_p3}"
        elif (
            (prob_1h >= float(policy.get("p2_warning_prob", 0.18)) or mem >= float(policy.get("memory_warning_percent", 88.0)))
            and st["p2"] >= req_p1_p3
        ) or (st["p2"] >= req_p2_anom):
            triggered_priority = "P2"
            denom = req_p1_p3 if prob_1h >= float(policy.get("p2_warning_prob", 0.18)) else req_p2_anom
            persistence_str = f"{min(st['p2'], denom)}/{denom}"
        elif st["p3"] >= req_p1_p3:
            triggered_priority = "P3"
            persistence_str = f"{min(st['p3'], req_p1_p3)}/{req_p1_p3}"
        elif st["p3"] == 1:
            persistence_str = f"1/{req_p1_p3} (Verifying)"

        if triggered_priority is not None:
            self.healthy_streaks[nid] = 0
            title = f"[{triggered_priority}] {nid}: {ml_result['fault_label']}"
            summary = (
                f"1h Failure Risk {prob_1h * 100:.1f}% | "
                f"Consensus {consensus}/4 detectors | "
                f"Slurm: {slurm_state}. {ml_result['playbook_advice']}"
            )
            ep = upsert_alert_episode(
                node_id=nid,
                priority=triggered_priority,
                fault_class=fault_class,
                title=title,
                summary=summary,
                playbook_cmd=ml_result["playbook_cmd"],
                timestamp_utc=timestamp_utc,
                consensus_votes=consensus,
                failure_prob=prob_1h,
                anomaly_score=float(ml_result["anomaly_score"]),
                top_features=ml_result["top_features"],
                data_mode=data_mode,
            )

            if triggered_priority in ("P1", "P2") and ep.get("alert_points", 1) == 1:
                add_system_log(
                    timestamp_utc=timestamp_utc,
                    node_id=nid,
                    source="aiops-alert-engine",
                    severity="CRITICAL" if triggered_priority == "P1" else "WARNING",
                    event_type=fault_class,
                    message=f"{title} — Persistence {persistence_str} confirmed. Action: {ml_result['playbook_cmd']}",
                )
                self._maybe_dispatch_webhook(
                    nid,
                    triggered_priority,
                    title,
                    summary,
                    int(policy.get("cooldown_minutes", 30)),
                )

            return {
                "alert_priority": triggered_priority,
                "persistence_progress": persistence_str,
                "alert_active": True,
                "episode_id": ep["id"],
            }

        self.healthy_streaks[nid] = self.healthy_streaks.get(nid, 0) + 1
        if self.healthy_streaks[nid] >= 3:
            auto_resolve_node_episodes(nid, timestamp_utc)

        return {
            "alert_priority": "OK",
            "persistence_progress": persistence_str,
            "alert_active": False,
            "episode_id": None,
        }

    def _maybe_dispatch_webhook(
        self, node_id: str, priority: str, title: str, summary: str, cooldown_min: int
    ) -> None:
        if not ALERT_WEBHOOK_URL:
            return
        now = datetime.now(timezone.utc)
        cooldown = timedelta(minutes=cooldown_min)
        last = self.last_webhook_sent.get(node_id)
        if last and (now - last) < cooldown:
            return
        self.last_webhook_sent[node_id] = now

        def _send() -> None:
            try:
                requests.post(
                    ALERT_WEBHOOK_URL,
                    json={"text": f"*{title}*\n{summary}", "priority": priority, "node_id": node_id},
                    timeout=4,
                )
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()

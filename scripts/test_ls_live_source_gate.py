import unittest
from zoneinfo import ZoneInfo

from ls_live_source_gate import (
    decide_history_probe,
    decide_live_probe,
    find_active_source_consumers,
)

KST = ZoneInfo("Asia/Seoul")


class SourceGateTests(unittest.TestCase):
    def test_push_never_runs_live_probes_even_when_opted_in(self):
        self.assertEqual(
            decide_live_probe("push", True, True, [], []),
            (False, "scheduled_or_manual_event_required"),
        )

    def test_schedule_runs_live_probe_when_session_clear(self):
        self.assertEqual(
            decide_live_probe("schedule", False, True, [], []),
            (True, "clear"),
        )

    def test_schedule_skips_live_probe_when_production_consumer_is_active(self):
        self.assertEqual(
            decide_live_probe("schedule", False, True, ["watch#9:in_progress"], []),
            (False, "active_source_consumer_present"),
        )

    def test_schedule_fails_closed_when_consumer_scan_is_incomplete(self):
        self.assertEqual(
            decide_live_probe("schedule", False, True, [], ["run_lookup_failed"]),
            (False, "active_consumer_scan_incomplete"),
        )

    def test_manual_live_probe_requires_market_session(self):
        self.assertEqual(
            decide_live_probe("workflow_dispatch", True, False, [], []),
            (False, "outside_market_session"),
        )

    def test_active_consumer_blocks_manual_live_probe(self):
        self.assertEqual(
            decide_live_probe(
                "workflow_dispatch", True, True,
                ["KOSPI LS Realtime Derivatives Flow Watch#9:afternoon:in_progress"], [],
            ),
            (False, "active_source_consumer_present"),
        )

    def test_incomplete_consumer_scan_fails_closed(self):
        self.assertEqual(
            decide_live_probe("workflow_dispatch", True, True, [], ["run_lookup_failed"]),
            (False, "active_consumer_scan_incomplete"),
        )

    def test_manual_live_probe_allowed_only_when_session_clear(self):
        self.assertEqual(
            decide_live_probe("workflow_dispatch", True, True, [], []),
            (True, "clear"),
        )

    def test_after_hours_history_probe_is_manual_and_clear_only(self):
        self.assertEqual(
            decide_history_probe("workflow_dispatch", True, False, [], []),
            (True, "clear_after_hours"),
        )
        self.assertEqual(
            decide_history_probe("schedule", False, False, [], []),
            (True, "clear_after_hours"),
        )
        self.assertEqual(
            decide_history_probe("workflow_dispatch", True, False, [], ["unknown"]),
            (False, "active_consumer_scan_incomplete"),
        )

    def test_scan_blocks_on_known_active_source_job_and_ignores_current_run(self):
        responses = {
            "actions/runs?status=in_progress&per_page=100": {
                "workflow_runs": [
                    {"id": 10, "name": "KOSPI LS Realtime Derivatives Flow Watch", "status": "in_progress"},
                    {"id": 20, "name": "KOSPI Derivatives Flow CI", "status": "in_progress"},
                ]
            },
            "actions/runs?status=queued&per_page=100": {"workflow_runs": []},
            "actions/runs/10/jobs?per_page=100": {
                "jobs": [{"name": "afternoon", "status": "in_progress"}]
            },
        }

        def fake_fetch(_repo, _token, path):
            return responses[path]

        active, unknown, scanned = find_active_source_consumers(
            "owner/repo", "token", 20, fetch_json=fake_fetch,
        )
        self.assertEqual(scanned, 1)
        self.assertEqual(len(active), 1)
        self.assertIn("afternoon", active[0])
        self.assertEqual(unknown, [])

    def test_scan_fails_closed_when_matching_job_lookup_fails(self):
        def fake_fetch(_repo, _token, path):
            if path.startswith("actions/runs?status="):
                return {
                    "workflow_runs": [
                        {"id": 30, "name": "Korea Market Stress and Global Wave Telegram Watch", "status": "in_progress"}
                    ] if "in_progress" in path else []
                }
            raise TimeoutError("job lookup unavailable")

        active, unknown, _ = find_active_source_consumers(
            "owner/repo", "token", 99, fetch_json=fake_fetch,
        )
        self.assertEqual(active, [])
        self.assertTrue(any("job_lookup_failed" in item for item in unknown))


if __name__ == "__main__":
    unittest.main()

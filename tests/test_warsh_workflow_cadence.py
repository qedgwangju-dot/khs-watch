#!/usr/bin/env python3
import datetime as dt
import unittest
from unittest.mock import patch

import warsh_workflow_cadence as cadence


class WarshWorkflowCadenceTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 14, 10, 0, tzinfo=dt.timezone.utc)

    def test_regular_triggers_are_never_gated(self):
        for event in ("schedule", "push", "workflow_dispatch"):
            run, lag, reason = cadence.due_decision(
                event, self.now - dt.timedelta(minutes=5), self.now
            )
            self.assertTrue(run)
            self.assertIsNone(lag)
            self.assertIn("정규", reason)

    def test_workflow_run_skips_when_recent_monitor_succeeded(self):
        run, lag, reason = cadence.due_decision(
            "workflow_run", self.now - dt.timedelta(minutes=20), self.now, 55
        )
        self.assertFalse(run)
        self.assertAlmostEqual(lag, 20.0)
        self.assertIn("생략", reason)

    def test_workflow_run_fills_cron_gap(self):
        run, lag, reason = cadence.due_decision(
            "workflow_run", self.now - dt.timedelta(minutes=70), self.now, 55
        )
        self.assertTrue(run)
        self.assertAlmostEqual(lag, 70.0)
        self.assertIn("공백", reason)

    def test_missing_previous_success_fails_open_for_coverage(self):
        run, lag, reason = cadence.due_decision("workflow_run", None, self.now, 55)
        self.assertTrue(run)
        self.assertIsNone(lag)
        self.assertIn("보조 실행", reason)

    def test_latest_success_requires_monitor_job_success(self):
        runs = {
            "workflow_runs": [
                {
                    "id": 200,
                    "conclusion": "success",
                    "jobs_url": "https://api.github.test/runs/200/jobs",
                    "updated_at": "2026-10-14T09:50:00Z",
                },
                {
                    "id": 199,
                    "conclusion": "success",
                    "jobs_url": "https://api.github.test/runs/199/jobs",
                    "updated_at": "2026-10-14T09:00:00Z",
                },
            ]
        }
        jobs_200 = {"jobs": [{"name": "cadence", "conclusion": "success"}, {"name": "monitor", "conclusion": "skipped"}]}
        jobs_199 = {"jobs": [{"name": "monitor", "conclusion": "success", "completed_at": "2026-10-14T09:02:00Z"}]}

        def fake(url, token):
            if "actions/workflows/" in url:
                return runs
            if url.endswith("/200/jobs"):
                return jobs_200
            if url.endswith("/199/jobs"):
                return jobs_199
            raise AssertionError(url)

        with patch.object(cadence, "api_json", side_effect=fake):
            got = cadence.latest_monitor_success("owner/repo", "token", 201)
        self.assertEqual(got["run_id"], 199)
        self.assertEqual(got["completed_at"], dt.datetime(2026, 10, 14, 9, 2, tzinfo=dt.timezone.utc))


if __name__ == "__main__":
    unittest.main()

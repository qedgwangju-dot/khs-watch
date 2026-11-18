#!/usr/bin/env python3
"""Offline fixtures for the read-only, no-send alert operations audit."""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from scripts import alert_operations_audit as audit


class AlertOperationsAuditTest(unittest.TestCase):
    def test_static_audit_flags_templating_and_missing_delivery_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            folder = root / ".github" / "workflows"
            folder.mkdir(parents=True)
            (folder / "valid-telegram-watch.yml").write_text(
                'name: valid\non:\n  schedule:\n    - cron: "17 * * * *"\n'
                '  workflow_dispatch:\njobs:\n  watch:\n    steps:\n'
                '      - run: |\n          sendMessage\n          message_id = response["message_id"]\n',
                encoding="utf-8",
            )
            (folder / "broken-telegram-watch.yml").write_text(
                'name: broken\non:\n  schedule:\n    - cron: "bad timing"\n'
                '  workflow_run:\n    workflows: [upstream]\n'
                'concurrency:\n  cancel-in-progress: true\n'
                'jobs:\n  watch:\n    steps:\n      - run: sendMessage\n'
                '        env:\n          TOKEN: ' + chr(92) + '${{ secrets.BOT }}\n',
                encoding="utf-8",
            )
            (folder / "telegram-route-inventory-once.yml").write_text(
                'name: diagnostic once\non:\n  workflow_dispatch:\njobs:\n  test:\n'
                '    steps:\n      - run: sendMessage\n',
                encoding="utf-8",
            )
            summary = audit.audit_static(root)
            self.assertEqual(summary["workflow_files"], 3)
            self.assertEqual(summary["scheduled_files"], 2)
            self.assertEqual(summary["risk_counts"]["escaped_github_expression"], 1)
            self.assertEqual(summary["risk_counts"]["direct_send_without_message_id_check"], 1)
            self.assertEqual(summary["risk_counts"]["invalid_cron_field_count"], 1)
            self.assertEqual(summary["risk_counts"]["schedule_workflow_run_cancellation_risk"], 1)
            self.assertEqual(summary["risk_counts"]["no_manual_dispatch_for_scheduled_watch"], 1)

    def test_validated_helper_is_receipt_but_plurals_alone_are_not(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            good = base / "europe-sovereign-yield-telegram-watch.yml"
            good.write_text(
                'jobs:\\n  send:\\n    steps:\\n      - run: |\\n'
                '          result = sendMessage(data)\\n'
                '          ids.append(verified_telegram_message_id(result, chat_id))\\n',
                encoding="utf-8",
            )
            bad = base / "weak-telegram-watch.yml"
            bad.write_text(
                'jobs:\\n  send:\\n    steps:\\n      - run: |\\n'
                '          sendMessage(data)\\n'
                '          message_ids = []\\n',
                encoding="utf-8",
            )
            self.assertTrue(audit.inspect_workflow(good)["receipt_marker"])
            self.assertNotIn("direct_send_without_message_id_check",
                             audit.inspect_workflow(good)["risks"])
            self.assertFalse(audit.inspect_workflow(bad)["receipt_marker"])
            self.assertIn("direct_send_without_message_id_check",
                          audit.inspect_workflow(bad)["risks"])

    def test_all_scheduled_cancel_and_shared_group_are_review_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            folder = root / ".github" / "workflows"
            folder.mkdir(parents=True)
            for name in ("alpha-telegram-watch.yml", "beta-telegram-watch.yml"):
                (folder / name).write_text(
                    'name: existing alert\non:\n  schedule:\n'
                    '    - cron: "17 * * * *"\nconcurrency:\n'
                    '  group: shared-existing-alert\n'
                    '  cancel-in-progress: true\n',
                    encoding="utf-8",
                )
            (folder / "gamma-telegram-watch.yml").write_text(
                'name: existing isolated alert\non:\n  schedule:\n'
                '    - cron: "42 * * * *"\njobs:\n  monitor:\n'
                '    runs-on: ubuntu-latest\n',
                encoding="utf-8",
            )
            findings = audit.audit_static(root)
            by_path = {row["path"]: set(row["risks"]) for row in findings["findings"]}
            for name in ("alpha", "beta"):
                risks = by_path[f".github/workflows/{name}-telegram-watch.yml"]
                self.assertIn("scheduled_run_can_be_cancelled", risks)
                self.assertIn("shared_concurrency_group_review", risks)
            self.assertIn("scheduled_alert_without_concurrency",
                          by_path[".github/workflows/gamma-telegram-watch.yml"])
            self.assertEqual(findings["workflow_files"], 3)
            self.assertEqual(findings["risk_counts"]["shared_concurrency_group_review"], 2)
            self.assertNotIn("Telegram delivery confirmed", str(findings))

    def test_runtime_preserves_failure_cancel_and_disabled_distinction(self):
        rows = [
            {"id": 1, "path": ".github/workflows/a.yml", "event": "pull_request", "conclusion": "success", "created_at": "2026-10-12T14:00:00Z"},
            {"id": 1, "path": ".github/workflows/a.yml", "conclusion": "success", "created_at": "2026-10-12T14:00:00Z"},
            {"path": ".github/workflows/a.yml", "event": "schedule", "conclusion": "failure", "created_at": "2026-10-12T13:00:00Z"},
            {"path": ".github/workflows/b.yml", "conclusion": "cancelled", "created_at": "2026-10-12T12:00:00Z"},
        ]
        catalog = [
            {"path": ".github/workflows/a.yml", "state": "active"},
            {"path": ".github/workflows/b.yml", "state": "disabled_manually"},
        ]
        summary = audit.audit_runtime(rows, catalog, known_paths={".github/workflows/a.yml"})
        self.assertEqual(summary["runs_reviewed"], 3)
        self.assertEqual(summary["conclusions"]["success"], 1)
        self.assertEqual(summary["conclusions"]["failure"], 1)
        self.assertEqual(summary["conclusions"]["cancelled"], 1)
        self.assertEqual(summary["failure_clusters"][0]["latest_conclusion"], "success")
        self.assertEqual(summary["failure_clusters"][0]["latest_schedule_conclusion"], "failure")
        self.assertEqual(summary["registry_only_workflows"][0]["path"], ".github/workflows/b.yml")
        self.assertEqual(summary["inactive_workflows"][0]["state"], "disabled_manually")
        md = audit.make_markdown({"workflow_files": 2, "scheduled_files": 2, "inline_send_files": 1, "risk_counts": {}}, summary)
        self.assertIn("성공 1 · 실패 1 · 취소 1", md)
        self.assertIn("임의 재활성화 금지", md)
        self.assertIn("message_id", md)

    def test_schedule_silence_excludes_disabled_and_uncertain_windows(self):
        import datetime as dt

        self.assertEqual(audit.conservative_schedule_gap_hours("7,27,47 * * * *"), 3)
        self.assertEqual(audit.conservative_schedule_gap_hours("41 */2 * * *"), 6)
        self.assertEqual(audit.conservative_schedule_gap_hours("37 */3 * * *"), 9)
        self.assertEqual(audit.conservative_schedule_gap_hours("23 0 * * *"), 48)
        self.assertIsNone(audit.conservative_schedule_gap_hours("11 */2 * * 1-5"))
        self.assertIsNone(audit.conservative_schedule_gap_hours("15 9 * * 1-5"))
        self.assertIsNone(audit.conservative_schedule_gap_hours("invalid"))

        now = dt.datetime(2026, 10, 13, 12, tzinfo=dt.timezone.utc)
        records = [
            {"id": 1, "path": ".github/workflows/fast.yml", "event": "schedule",
             "created_at": "2026-10-13T06:00:00Z", "conclusion": "success",
             "html_url": "https://github.com/org/repo/actions/runs/1"},
            {"id": 2, "path": ".github/workflows/healthy.yml", "event": "schedule",
             "created_at": "2026-10-13T11:30:00Z", "conclusion": "success"},
            {"id": 3, "path": ".github/workflows/other.yml", "event": "schedule",
             "created_at": "2026-10-11T09:00:00Z", "conclusion": "success"},
        ]
        registry = [
            {"path": ".github/workflows/fast.yml", "state": "active"},
            {"path": ".github/workflows/healthy.yml", "state": "active"},
            {"path": ".github/workflows/no-runs.yml", "state": "active"},
            {"path": ".github/workflows/daily.yml", "state": "active"},
            {"path": ".github/workflows/disabled.yml", "state": "disabled_manually"},
        ]
        gaps = audit.audit_runtime(
            records, registry,
            schedule_max_gap_hours={
                ".github/workflows/fast.yml": 3,
                ".github/workflows/healthy.yml": 3,
                ".github/workflows/no-runs.yml": 3,
                ".github/workflows/daily.yml": 48,
                ".github/workflows/disabled.yml": 3,
            },
            now_utc=now,
        )["schedule_silence_candidates"]
        by_path = {row["path"]: row for row in gaps}
        self.assertEqual(by_path[".github/workflows/fast.yml"]["reason"], "scheduled_run_overdue")
        self.assertEqual(by_path[".github/workflows/no-runs.yml"]["reason"], "no_scheduled_run_in_observed_window")
        self.assertIn(".github/workflows/daily.yml", by_path)
        self.assertNotIn(".github/workflows/healthy.yml", by_path)
        self.assertNotIn(".github/workflows/disabled.yml", by_path)

        # A short partial API sample must not falsely flag a daily schedule.
        short = audit.audit_runtime(
            records[1:2], registry,
            schedule_max_gap_hours={".github/workflows/daily.yml": 48},
            now_utc=now,
        )
        self.assertFalse(short["schedule_silence_candidates"])

    def test_three_scheduled_failures_not_hidden_by_successful_manual_run(self):
        base = [
            {"id": 5, "path": ".github/workflows/bio-qlex-intismeran-watch.yml",
             "event": "workflow_dispatch", "conclusion": "success",
             "created_at": "2026-10-15T12:05:00Z"},
            {"id": 4, "path": ".github/workflows/bio-qlex-intismeran-watch.yml",
             "event": "schedule", "conclusion": "failure",
             "created_at": "2026-10-15T12:00:00Z", "html_url": "https://github.com/test/runs/4"},
            {"id": 3, "path": ".github/workflows/bio-qlex-intismeran-watch.yml",
             "event": "schedule", "conclusion": "failure",
             "created_at": "2026-10-15T11:00:00Z"},
            {"id": 2, "path": ".github/workflows/bio-qlex-intismeran-watch.yml",
             "event": "schedule", "conclusion": "failure",
             "created_at": "2026-10-15T10:00:00Z"},
            {"id": 1, "path": ".github/workflows/bio-qlex-intismeran-watch.yml",
             "event": "schedule", "conclusion": "success",
             "created_at": "2026-10-15T09:00:00Z"},
        ]
        result = audit.audit_runtime(base, [])
        streaks = result["persistent_scheduled_failures"]
        self.assertEqual(len(streaks), 1)
        self.assertEqual(streaks[0]["consecutive_schedule_failures_observed"], 3)
        summary = audit.make_markdown({
            "workflow_files": 1, "scheduled_files": 1,
            "inline_send_files": 0, "risk_counts": {}
        }, result)
        self.assertIn("연속 예약 실패 3회 이상: 1개", summary)
        self.assertIn("예약 연속 실패 3회", summary)
        recovered = [{
            "id": 6, "path": ".github/workflows/bio-qlex-intismeran-watch.yml",
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-10-15T13:00:00Z",
        }] + base
        self.assertFalse(audit.audit_runtime(recovered, [])["persistent_scheduled_failures"])

    def test_corrupt_run_input_fails_not_false_all_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.jsonl"
            path.write_text('{"valid": true}\n{broken json}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                audit.parse_jsonl(path)


if __name__ == "__main__":
    unittest.main()

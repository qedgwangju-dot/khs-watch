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
                '        env:\n          TOKEN: \${{ secrets.BOT }}\n',
                encoding="utf-8",
            )
            summary = audit.audit_static(root)
            self.assertEqual(summary["workflow_files"], 2)
            self.assertEqual(summary["scheduled_files"], 2)
            self.assertEqual(summary["risk_counts"]["escaped_github_expression"], 1)
            self.assertEqual(summary["risk_counts"]["direct_send_without_message_id_check"], 1)
            self.assertEqual(summary["risk_counts"]["invalid_cron_field_count"], 1)
            self.assertEqual(summary["risk_counts"]["schedule_workflow_run_cancellation_risk"], 1)
            self.assertEqual(summary["risk_counts"]["no_manual_dispatch_for_scheduled_watch"], 1)

    def test_runtime_preserves_failure_cancel_and_disabled_distinction(self):
        rows = [
            {"path": ".github/workflows/a.yml", "conclusion": "success", "created_at": "2026-10-12T14:00:00Z"},
            {"path": ".github/workflows/a.yml", "conclusion": "failure", "created_at": "2026-10-12T13:00:00Z"},
            {"path": ".github/workflows/b.yml", "conclusion": "cancelled", "created_at": "2026-10-12T12:00:00Z"},
        ]
        catalog = [
            {"path": ".github/workflows/a.yml", "state": "active"},
            {"path": ".github/workflows/b.yml", "state": "disabled_manually"},
        ]
        summary = audit.audit_runtime(rows, catalog)
        self.assertEqual(summary["runs_reviewed"], 3)
        self.assertEqual(summary["conclusions"]["success"], 1)
        self.assertEqual(summary["conclusions"]["failure"], 1)
        self.assertEqual(summary["conclusions"]["cancelled"], 1)
        self.assertEqual(summary["failure_clusters"][0]["latest_conclusion"], "success")
        self.assertEqual(summary["inactive_workflows"][0]["state"], "disabled_manually")
        md = audit.make_markdown({"workflow_files": 2, "scheduled_files": 2, "inline_send_files": 1, "risk_counts": {}}, summary)
        self.assertIn("성공 1 · 실패 1 · 취소 1", md)
        self.assertIn("임의 재활성화 금지", md)
        self.assertIn("message_id", md)

    def test_corrupt_run_input_fails_not_false_all_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.jsonl"
            path.write_text('{"valid": true}\n{broken json}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                audit.parse_jsonl(path)


if __name__ == "__main__":
    unittest.main()

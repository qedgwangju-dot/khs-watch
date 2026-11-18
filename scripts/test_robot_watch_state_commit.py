"""Exercise the workflow's actual merge script without Git, network or sends."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/robotis-physical-ai-telegram-watch.yml"
text = WORKFLOW.read_text(encoding="utf-8")
start = text.index('          import json, os, pathlib, sys\n')
end = text.index('          PY\n', start)
SCRIPT = "\n".join(line[10:] for line in text[start:end].splitlines())


class StateCommitTests(unittest.TestCase):
    def merge(self, confirmed, outcome, rendered=True):
        old = {"seeded": True, "updated_at": "2026-11-16T12:00:00+00:00", "seen": ["historic"], "unrelated_metadata": "keep"}
        proposed = {"seeded": True, "updated_at": "2026-11-18T04:00:00+00:00", "seen": ["historic", "first", "second"],
                    "last_selected": ["first", "second"], "last_selected_events": [{"key": "first"}, {"key": "second"}]}
        receipts = [{"message_id": 401, "chat_verification": "numeric_id_equal"}] if confirmed else []
        helper = types.SimpleNamespace(check_receipts=lambda *args: set(confirmed), route_fingerprint=lambda chat: "fixture-route")
        with tempfile.TemporaryDirectory(prefix="robot-state-merge-") as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "out").mkdir()
            target = root / "data/robotis_physical_ai_watch_state.json"
            target.write_text(json.dumps(old))
            (root / "proposed.json").write_text(json.dumps(proposed))
            (root / "out/robotis_physical_ai_watch_telegram.txt").write_text("fixture final HTML" if rendered else "")
            (root / "out/robotis_physical_ai_watch_delivery_receipts.json").write_text(json.dumps(receipts))
            script = SCRIPT.replace('/tmp/robotis_watch_final_state.json', str(root / "proposed.json"))
            cwd = Path.cwd()
            old_path = list(sys.path)
            try:
                os.chdir(root)
                with patch.dict(sys.modules, {"robot_watch_delivery": helper}), \
                     patch.dict(os.environ, {"DELIVERY_OUTCOME": outcome, "GITHUB_RUN_ID": "42", "TELEGRAM_CHAT_ID": "fixture"}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(script, str(WORKFLOW), "exec"), {})
            finally:
                os.chdir(cwd)
                sys.path[:] = old_path
            return json.loads(target.read_text()), old

    def test_confirmed_partial_articles_survive_and_unsent_remain_eligible(self):
        result, old = self.merge({"first"}, "failure")
        self.assertEqual(result["seen"], ["historic", "first"])
        self.assertEqual(result["last_selected"], ["first"])
        self.assertEqual(result["last_selected_events"], [{"key": "first"}])
        self.assertEqual(result["updated_at"], old["updated_at"], "Failed send must remain visible to recovery")
        self.assertEqual(result["last_delivery"]["outcome"], "partial_send")
        self.assertEqual(result["unrelated_metadata"], "keep")

    def test_failure_without_confirmed_receipt_consumes_nothing(self):
        result, old = self.merge(set(), "failure")
        self.assertEqual(result["seen"], old["seen"])
        self.assertEqual(result["last_selected"], [])
        self.assertEqual(result["last_delivery"]["outcome"], "send_failed")
        self.assertEqual(result["updated_at"], old["updated_at"])

    def test_full_success_advances_checkpoint(self):
        result, old = self.merge({"first", "second"}, "success")
        self.assertEqual(set(result["seen"]), {"historic", "first", "second"})
        self.assertNotEqual(result["updated_at"], old["updated_at"])
        self.assertEqual(result["last_delivery"]["outcome"], "sent")

    def test_claimed_success_without_complete_receipts_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.merge({"first"}, "success")

    def test_suppressed_report_does_not_consume_selected_events(self):
        result, _ = self.merge(set(), "success", rendered=False)
        self.assertEqual(result["seen"], ["historic"])
        self.assertEqual(result["last_delivery"]["outcome"], "normal_silence")


if __name__ == "__main__":
    unittest.main()

"""Offline checks for the morning status delivery contract."""

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preopen_daily_status as status


class PreopenDailyStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.cfg = {key: root / f"{key}.json" for key in ("status", "evidence", "saved", "factual_pending", "state", "pending", "receipt", "alert")}
        self.cfg["status"] = root / "status.md"
        self.cfg["alert"] = root / "alert.html"
        self.now = dt.datetime(2026, 11, 3, 7, 45, tzinfo=status.KST)

    def test_us_missing_run_is_not_called_unchanged(self):
        with patch.dict(status.CONFIG, {"us": {"title": "미국 증시 자금흐름", **self.cfg}}):
            message = status.build_us_message(self.now, "scheduled_check")
        self.assertIn("오늘 정기 조회 결과가 생성되지 않았습니다", message)
        self.assertNotIn("변경 없음", message)

    def test_us_unchanged_mentions_current_source_period(self):
        self.cfg["status"].write_text("- parsed sources: 2\n- updates: 0\n- ICI | October 28, 2026 | value\n", encoding="utf-8")
        with patch.dict(status.CONFIG, {"us": {"title": "미국 증시 자금흐름", **self.cfg}}):
            message = status.build_us_message(self.now, "scheduled_check")
        self.assertIn("변경 없음", message)
        self.assertIn("ICI: October 28, 2026", message)

    def test_kofia_misaligned_dates_are_explicit(self):
        self.cfg["evidence"].write_text(json.dumps({"phase": "alignment_pending", "latest_dates": {"deposit": "2026-11-02", "mmf": "2026-10-30"}}), encoding="utf-8")
        with patch.dict(status.CONFIG, {"kofia": {"title": "국내 증시 대기자금", **self.cfg}}):
            message = status.build_kofia_message(self.now, "scheduled_check")
        self.assertIn("기준일 불일치", message)
        self.assertIn("2026-11-02", message)
        self.assertIn("2026-10-30", message)

    def test_receipt_dedup_and_chat_check_without_network(self):
        expected = "Morning status"
        response = {"ok": True, "result": {"message_id": 41, "date": 1793691900, "from": {"username": "expected_bot"}, "chat": {"id": 1234}, "text": expected}}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test", "TELEGRAM_CHAT_ID": "1234", "EXPECTED_TELEGRAM_BOT_USERNAME": "expected_bot"}):
            with patch.object(status, "_telegram_json", side_effect=[{"ok": True, "result": {"username": "expected_bot"}}, response]) as api:
                status.send_message("us", self.cfg, expected, self.now)
                self.assertEqual(api.call_count, 2)
            saved = json.loads(self.cfg["receipt"].read_text(encoding="utf-8"))
            self.assertEqual(saved["message_id"], 41)
            with patch.object(status, "_telegram_json") as api:
                self.cfg["state"].write_text(json.dumps(saved), encoding="utf-8")
                status.send_message("us", self.cfg, expected, self.now)
                api.assert_not_called()

    def test_wrong_chat_cannot_create_receipt(self):
        response = {"ok": True, "result": {"message_id": 41, "date": 1793691900, "from": {"username": "expected_bot"}, "chat": {"id": 4321}, "text": "Morning status"}}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test", "TELEGRAM_CHAT_ID": "1234", "EXPECTED_TELEGRAM_BOT_USERNAME": "expected_bot"}):
            with patch.object(status, "_telegram_json", side_effect=[{"ok": True, "result": {"username": "expected_bot"}}, response]):
                with self.assertRaisesRegex(RuntimeError, "different chat id"):
                    status.send_message("us", self.cfg, "Morning status", self.now)
        self.assertFalse(self.cfg["receipt"].exists())

    def test_existing_workflow_fallback_has_family_specific_morning_window(self):
        at_early = self.now.replace(hour=7, minute=20)
        at_final = self.now.replace(hour=7, minute=45)
        after_open = self.now.replace(hour=8, minute=0)
        self.assertTrue(status.in_workflow_run_window(at_early, "us"))
        self.assertTrue(status.in_workflow_run_window(at_early, "kofia"))
        self.assertTrue(status.in_workflow_run_window(at_final, "us"))
        self.assertTrue(status.in_workflow_run_window(at_final, "kofia"))
        self.assertFalse(status.in_workflow_run_window(after_open, "us"))


if __name__ == "__main__":
    unittest.main()

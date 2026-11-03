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

    def test_us_rechecked_periods_show_horizons_but_mismatched_source_does_not(self):
        values = {
            "ICI|combined": {"period": "October 21, 2026", "fingerprint": "a" * 64, "metrics": {"domestic_flow_horizons": {"m1": {"value_bn": -491.959}, "m3": {"value_bn": None, "reason": "weekly_history_does_not_cover_target_window"}}}},
            "ICI|mmf": {"period": "October 28, 2026", "fingerprint": "b" * 64, "metrics": {"asset_balance_horizons": {"m1": {"change_bn": -35.437}, "m3": {"change_bn": 40.535}}}},
            "FINRA|margin": {"period": "Sep-26", "fingerprint": "c" * 64, "metrics": {"margin_debt_horizons": {"m1": {"change_bn": 26.222}, "m3": {"change_bn": -22.018}}}},
        }
        self.cfg["saved"].write_text(json.dumps({"values": values}), encoding="utf-8")
        self.cfg["status"].write_text(
            "- parsed sources: 3\n- updates: 0\n"
            "- ICI combined | October 21, 2026 | aaaaaaaaaaaa\n"
            "- ICI mmf | October 28, 2026 | bbbbbbbbbbbb\n"
            "- FINRA margin | Sep-26 | dddddddddddd\n"
            "- USD/KRW: 1341.0 (20261103)\n", encoding="utf-8"
        )
        with patch.dict(status.CONFIG, {"us": {"title": "미국 증시 자금흐름", **self.cfg}}):
            message = status.build_us_message(self.now, "scheduled_check")
        self.assertIn("1M -4,919.6억달러 (약 -659.7조원)", message)
        self.assertIn("3M 확인 불가 (동일 정의 주간 이력이 목표일까지 이어지지 않음)", message)
        self.assertIn("FINRA 마진부채 잔액 차이: 1M/3M 확인 불가", message)
        self.assertNotIn("+262.2억달러", message)

    def test_kofia_misaligned_dates_are_explicit(self):
        self.cfg["evidence"].write_text(json.dumps({"phase": "alignment_pending", "latest_dates": {"deposit": "2026-11-02", "mmf": "2026-10-30"}}), encoding="utf-8")
        with patch.dict(status.CONFIG, {"kofia": {"title": "국내 증시 대기자금", **self.cfg}}):
            message = status.build_kofia_message(self.now, "scheduled_check")
        self.assertIn("기준일 불일치", message)
        self.assertIn("2026-11-02", message)
        self.assertIn("2026-10-30", message)

    def test_kofia_unchanged_official_rows_show_balance_horizons_only_after_fingerprint_check(self):
        fp = "a" * 64
        rows = "".join(f"- {key} 20261102: 100 / 1M -1.2조↓ / 3M +0.3조↑\n" for key in ("deposit", "mmf", "cma", "credit"))
        self.cfg["status"].write_text(rows + f"- fingerprint {fp}\n", encoding="utf-8")
        evidence = {"phase": "validated", "changed": False, "fingerprint": fp, "latest_dates": {key: "20261102" for key in ("deposit", "mmf", "cma", "credit")}}
        self.cfg["evidence"].write_text(json.dumps(evidence), encoding="utf-8")
        self.cfg["saved"].write_text(json.dumps({"fingerprint": fp, "snapshot_date": "20261102"}), encoding="utf-8")
        with patch.dict(status.CONFIG, {"kofia": {"title": "국내 증시 대기자금", **self.cfg}}):
            message = status.build_kofia_message(self.now, "scheduled_check")
            self.assertIn("투자자예탁금 (20261102): 1M -1.2조↓ / 3M +0.3조↑", message)
            self.cfg["saved"].write_text(json.dumps({"fingerprint": "b" * 64, "snapshot_date": "20261102"}), encoding="utf-8")
            mismatched = status.build_kofia_message(self.now, "scheduled_check")
        self.assertIn("지문 대조 실패", mismatched)
        self.assertNotIn("-1.2조↓", mismatched)

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

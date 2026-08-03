from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_fx_shock as shock  # noqa: E402


class YenCarryFxShockTests(unittest.TestCase):
    def make_move(self, change15: float, change30: float = 0.0, change60: float = 0.0) -> shock.FxMove:
        latest_epoch = 1_785_700_000.0
        return shock.FxMove(
            latest_price=156.5,
            latest_epoch=latest_epoch,
            reference_15m=156.5 / (1 + change15 / 100),
            reference_15m_epoch=latest_epoch - 15 * 60,
            change_15m_pct=change15,
            reference_30m=156.5 / (1 + change30 / 100),
            reference_30m_epoch=latest_epoch - 30 * 60,
            change_30m_pct=change30,
            reference_60m=156.5 / (1 + change60 / 100),
            reference_60m_epoch=latest_epoch - 60 * 60,
            change_60m_pct=change60,
        )

    def test_thresholds_include_15_30_60_minute_windows(self):
        self.assertEqual(shock.determine_stage(self.make_move(-0.49, -0.74, -0.99)), 0)
        self.assertEqual(shock.determine_stage(self.make_move(-0.50)), 1)
        self.assertEqual(shock.determine_stage(self.make_move(-0.20, -0.75)), 1)
        self.assertEqual(shock.determine_stage(self.make_move(-0.20, -0.30, -1.00)), 1)
        self.assertEqual(shock.determine_stage(self.make_move(-1.00)), 2)
        self.assertEqual(shock.determine_stage(self.make_move(-0.20, -1.25)), 2)
        self.assertEqual(shock.determine_stage(self.make_move(-0.20, -0.30, -1.50)), 2)

    def test_calculate_move_uses_exact_rolling_windows(self):
        start = 1_785_696_400.0
        prices = [160.0 + i * 0.01 for i in range(13)]
        prices[-7] = 159.0
        prices[-4] = 158.0
        prices[-1] = 157.0
        points = [(start + i * 300, price) for i, price in enumerate(prices)]
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": [item[0] for item in points],
                        "indicators": {"quote": [{"close": [item[1] for item in points]}]},
                    }
                ],
                "error": None,
            }
        }
        move = shock.calculate_move(payload)
        self.assertAlmostEqual(move.latest_price, 157.0)
        self.assertAlmostEqual(move.reference_15m, 158.0)
        self.assertAlmostEqual(move.reference_30m, 159.0)
        self.assertAlmostEqual(move.reference_60m, 160.0)
        self.assertEqual(move.reference_15m_epoch, points[-4][0])
        self.assertEqual(move.reference_30m_epoch, points[-7][0])
        self.assertEqual(move.reference_60m_epoch, points[0][0])
        self.assertAlmostEqual(move.change_15m_pct, (157 / 158 - 1) * 100)

    def test_rebound_then_flat_is_not_labeled_as_current_drop(self):
        move = self.make_move(0.06, 0.51, -1.02)
        self.assertEqual(shock.determine_stage(move), 1)
        self.assertEqual(shock.trigger_windows(1, move), [60])
        self.assertEqual(
            shock.current_state(move),
            "반등 후 현재 보합 — 지금 재급락 중은 아님",
        )
        self.assertEqual(shock.title_state(1, move), "반등 중·60분 급락 충격 잔존")

    def test_body_marks_current_direction_and_exact_trigger_window(self):
        move = self.make_move(0.06, 0.51, -1.02)
        checked_at = dt.datetime.fromtimestamp(move.latest_epoch, tz=dt.timezone.utc)
        body = shock.build_body(1, move, checked_at)
        self.assertIn("현재 상태: 반등 후 현재 보합 — 지금 재급락 중은 아님", body)
        self.assertIn("경보 발동 근거: 60분 구간이 1단계·주의 기준 충족", body)
        self.assertIn("15분", body)
        self.assertIn("1단계 기준 -0.50% 미충족", body)
        self.assertIn("30분", body)
        self.assertIn("1단계 기준 -0.75% 미충족", body)
        self.assertIn("60분", body)
        self.assertIn("1단계 기준 -1.00% 충족 ← 이번 경보 원인", body)
        self.assertIn("지금 이 순간의 진행 방향은 위 '현재 상태'를 우선", body)

    def test_direction_labels_distinguish_yen_strength_and_weakness(self):
        self.assertEqual(shock.direction_label(-0.20), "USD/JPY 하락 = 엔화 강세")
        self.assertEqual(shock.direction_label(0.20), "USD/JPY 상승 = 엔화 약세")
        self.assertEqual(shock.direction_label(0.06), "사실상 보합")

    def test_alert_is_not_finalized_without_telegram_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = {
                "STATE_PATH": root / "state.json",
                "OUT_DIR": root / "out",
                "ALERT_TITLE_PATH": root / "out/title.txt",
                "ALERT_BODY_PATH": root / "out/body.md",
                "ALERT_JSON_PATH": root / "out/alert.json",
                "SUMMARY_PATH": root / "out/summary.md",
                "PENDING_STATE_PATH": root / "out/pending.json",
                "CONFIRMED_PATH": root / "out/confirmed.json",
            }
            patches = [mock.patch.object(shock, name, value) for name, value in paths.items()]
            for patcher in patches:
                patcher.start()
            self.addCleanup(lambda: [patcher.stop() for patcher in reversed(patches)])

            move = self.make_move(-0.60)
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertTrue(result["alerted"])
            self.assertEqual(result["trigger_windows"], [15])
            self.assertFalse(paths["STATE_PATH"].exists())
            shock.finalize()
            self.assertFalse(paths["STATE_PATH"].exists())
            paths["CONFIRMED_PATH"].write_text(json.dumps({"ok": True}), encoding="utf-8")
            shock.finalize()
            saved = json.loads(paths["STATE_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(saved["stage"], 1)
            self.assertEqual(saved["trigger_windows"], [15])

    def test_clear_resets_state_without_alert(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = {
                "STATE_PATH": root / "state.json",
                "OUT_DIR": root / "out",
                "ALERT_TITLE_PATH": root / "out/title.txt",
                "ALERT_BODY_PATH": root / "out/body.md",
                "ALERT_JSON_PATH": root / "out/alert.json",
                "SUMMARY_PATH": root / "out/summary.md",
                "PENDING_STATE_PATH": root / "out/pending.json",
                "CONFIRMED_PATH": root / "out/confirmed.json",
            }
            root.mkdir(parents=True, exist_ok=True)
            paths["STATE_PATH"].write_text(json.dumps({"stage": 1}), encoding="utf-8")
            patches = [mock.patch.object(shock, name, value) for name, value in paths.items()]
            for patcher in patches:
                patcher.start()
            self.addCleanup(lambda: [patcher.stop() for patcher in reversed(patches)])

            move = self.make_move(-0.10)
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertFalse(result["alerted"])
            saved = json.loads(paths["STATE_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(saved["stage"], 0)
            self.assertEqual(saved["trigger_windows"], [])


if __name__ == "__main__":
    unittest.main()

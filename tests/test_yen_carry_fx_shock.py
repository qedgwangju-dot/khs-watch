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
    def make_move(
        self,
        change15: float,
        change30: float = 0.0,
        change60: float = 0.0,
        *,
        price: float = 156.5,
        latest_epoch: float = 1_785_700_000.0,
        sustained_duration: float = 0.0,
        sustained_drawdown: float = 0.0,
        sustained_rebound: float = 0.0,
    ) -> shock.FxMove:
        peak_price = price / (1 + sustained_drawdown / 100) if sustained_drawdown else price
        low_price = price / (1 + sustained_rebound / 100) if sustained_rebound else price
        return shock.FxMove(
            latest_price=price,
            latest_epoch=latest_epoch,
            reference_15m=price / (1 + change15 / 100),
            reference_15m_epoch=latest_epoch - 15 * 60,
            change_15m_pct=change15,
            reference_30m=price / (1 + change30 / 100),
            reference_30m_epoch=latest_epoch - 30 * 60,
            change_30m_pct=change30,
            reference_60m=price / (1 + change60 / 100),
            reference_60m_epoch=latest_epoch - 60 * 60,
            change_60m_pct=change60,
            sustained_peak_price=peak_price,
            sustained_peak_epoch=latest_epoch - sustained_duration * 60,
            sustained_duration_minutes=sustained_duration,
            sustained_drawdown_pct=sustained_drawdown,
            sustained_low_price=low_price,
            sustained_rebound_pct=sustained_rebound,
        )

    def payload_from_prices(
        self, prices: list[float], *, start: float = 1_785_696_400.0
    ) -> dict:
        points = [(start + i * 300, price) for i, price in enumerate(prices)]
        return {
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

    def patch_paths(self, root: pathlib.Path):
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
        return paths

    def test_fast_stage_uses_15_and_30_minutes(self):
        self.assertEqual(shock.determine_fast_stage(self.make_move(-0.49, -0.74)), 0)
        self.assertEqual(shock.determine_fast_stage(self.make_move(-0.50, 0.0)), 1)
        self.assertEqual(shock.determine_fast_stage(self.make_move(0.0, -0.75)), 1)
        self.assertEqual(shock.determine_fast_stage(self.make_move(-1.00, 0.0)), 2)
        self.assertEqual(shock.determine_fast_stage(self.make_move(0.0, -1.25)), 2)

    def test_60_minute_is_context_only(self):
        move = self.make_move(0.10, 0.20, -1.02)
        self.assertEqual(shock.determine_fast_stage(move), 0)
        self.assertEqual(shock.determine_sustained_stage(move), 0)
        self.assertEqual(shock.determine_residual_stage(move), 1)
        self.assertEqual(shock.active_stage(move), 0)

    def test_calculate_move_uses_exact_rolling_windows(self):
        prices = [160.0 + i * 0.01 for i in range(13)]
        prices[-7] = 159.0
        prices[-4] = 158.0
        prices[-1] = 157.0
        payload = self.payload_from_prices(prices)
        move = shock.calculate_move(payload)
        self.assertAlmostEqual(move.latest_price, 157.0)
        self.assertAlmostEqual(move.reference_15m, 158.0)
        self.assertAlmostEqual(move.reference_30m, 159.0)
        self.assertAlmostEqual(move.reference_60m, 160.0)
        self.assertAlmostEqual(move.sustained_peak_price, 160.11)
        self.assertAlmostEqual(move.sustained_drawdown_pct, (157.0 / 160.11 - 1) * 100)

    def test_slow_90_minute_decline_is_detected_without_fast_trigger(self):
        # 90분 동안 총 1.2% 하락: 15·30분 속도는 완만하지만 누적 하락은 큼.
        prices = [158.0 - (1.9 * i / 18) for i in range(19)]
        move = shock.calculate_move(self.payload_from_prices(prices))
        self.assertGreater(move.change_15m_pct, -0.50)
        self.assertGreater(move.change_30m_pct, -0.75)
        self.assertEqual(shock.determine_fast_stage(move), 0)
        self.assertEqual(shock.determine_sustained_stage(move), 1)
        self.assertEqual(shock.active_stage(move), 1)
        self.assertIn("sustained", shock.active_lanes(move))
        self.assertAlmostEqual(move.sustained_duration_minutes, 90.0)

    def test_arbitrary_135_minute_decline_is_detected(self):
        prices = [160.0 - (2.0 * i / 27) for i in range(28)]
        move = shock.calculate_move(self.payload_from_prices(prices))
        self.assertEqual(shock.determine_fast_stage(move), 0)
        self.assertEqual(shock.determine_sustained_stage(move), 1)
        self.assertAlmostEqual(move.sustained_duration_minutes, 135.0)

    def test_sustained_severe_stage(self):
        move = self.make_move(
            -0.20,
            -0.40,
            -0.80,
            sustained_duration=150,
            sustained_drawdown=-1.60,
            sustained_rebound=0.05,
        )
        self.assertEqual(shock.determine_fast_stage(move), 0)
        self.assertEqual(shock.determine_sustained_stage(move), 2)
        self.assertEqual(shock.active_stage(move), 2)

    def test_rebound_from_low_clears_sustained_alert(self):
        move = self.make_move(
            0.10,
            0.15,
            -0.80,
            sustained_duration=120,
            sustained_drawdown=-1.30,
            sustained_rebound=0.25,
        )
        self.assertEqual(shock.determine_sustained_stage(move), 0)

    def test_recent_peak_under_45_minutes_is_fast_lane_only(self):
        move = self.make_move(
            -0.60,
            -0.80,
            -0.90,
            sustained_duration=30,
            sustained_drawdown=-1.20,
        )
        self.assertEqual(shock.determine_fast_stage(move), 1)
        self.assertEqual(shock.determine_sustained_stage(move), 0)

    def test_direction_labels(self):
        self.assertEqual(shock.direction_label(-0.20), "USD/JPY 하락 = 엔화 강세")
        self.assertEqual(shock.direction_label(0.20), "USD/JPY 상승 = 엔화 약세")
        self.assertEqual(shock.direction_label(0.06), "사실상 보합")

    def test_residual_only_does_not_create_telegram_alert(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = self.patch_paths(root)
            move = self.make_move(0.06, 0.51, -1.02)
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertFalse(result["alerted"])
            self.assertEqual(result["stage"], 0)
            self.assertEqual(result["residual_stage"], 1)
            self.assertFalse(paths["ALERT_BODY_PATH"].exists())

    def test_sustained_only_creates_telegram_alert(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = self.patch_paths(root)
            move = self.make_move(
                -0.20,
                -0.40,
                -0.80,
                sustained_duration=90,
                sustained_drawdown=-1.20,
                sustained_rebound=0.05,
            )
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertTrue(result["alerted"])
            self.assertEqual(result["fast_stage"], 0)
            self.assertEqual(result["sustained_stage"], 1)
            self.assertEqual(result["active_lanes"], ["sustained"])
            body = paths["ALERT_BODY_PATH"].read_text(encoding="utf-8")
            self.assertIn("실제 고점부터 자동 계산", body)
            self.assertIn("가변 구간 지속 하락", body)

    def test_new_sustained_lane_realerts_after_cooldown(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_698_000.0,
            "last_alert_price": 156.8,
            "last_observed_lanes": ["fast_30m"],
        }
        move = self.make_move(
            0.0,
            -0.80,
            -1.10,
            price=156.3,
            latest_epoch=1_785_700_000.0,
            sustained_duration=100,
            sustained_drawdown=-1.20,
            sustained_rebound=0.05,
        )
        lanes = shock.active_lanes(move)
        self.assertEqual(lanes, ["fast_30m", "sustained"])
        self.assertEqual(
            shock.same_stage_reason(previous, 1, move, lanes),
            "지속 하락 새로 확인",
        )

    def test_same_stage_new_low_realerts_after_cooldown(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_698_000.0,
            "last_alert_price": 157.0,
            "last_observed_lanes": ["sustained"],
        }
        move = self.make_move(
            -0.20,
            -0.40,
            -0.80,
            price=156.50,
            latest_epoch=1_785_700_000.0,
            sustained_duration=120,
            sustained_drawdown=-1.20,
            sustained_rebound=0.05,
        )
        self.assertEqual(
            shock.same_stage_reason(previous, 1, move, ["sustained"]),
            "같은 단계 새 저점 확대",
        )

    def test_same_stage_realert_blocked_by_cooldown(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_699_400.0,
            "last_alert_price": 157.0,
            "last_observed_lanes": ["fast_30m"],
        }
        move = self.make_move(
            -0.60,
            -0.80,
            -0.20,
            price=156.3,
            latest_epoch=1_785_700_000.0,
        )
        self.assertIsNone(
            shock.same_stage_reason(previous, 1, move, shock.active_lanes(move))
        )

    def test_new_lane_during_cooldown_is_not_marked_observed(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_699_400.0,
            "last_alert_price": 156.8,
            "last_observed_lanes": ["fast_30m"],
        }
        move = self.make_move(
            -0.60,
            -0.80,
            0.0,
            price=156.4,
            latest_epoch=1_785_700_000.0,
        )
        self.assertFalse(
            shock.should_persist_observed_lanes(
                previous,
                stage=1,
                lanes=["fast_15m", "fast_30m"],
                move=move,
            )
        )

    def test_alert_is_not_finalized_without_telegram_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = self.patch_paths(root)
            move = self.make_move(-0.60)
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertTrue(result["alerted"])
            self.assertFalse(paths["STATE_PATH"].exists())
            shock.finalize()
            self.assertFalse(paths["STATE_PATH"].exists())
            paths["CONFIRMED_PATH"].write_text(json.dumps({"ok": True}), encoding="utf-8")
            shock.finalize()
            saved = json.loads(paths["STATE_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(saved["stage"], 1)
            self.assertEqual(saved["last_alert_lanes"], ["fast_15m"])

    def test_clear_resets_all_active_lanes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = self.patch_paths(root)
            paths["STATE_PATH"].write_text(
                json.dumps(
                    {
                        "stage": 1,
                        "last_alert_epoch": 1_785_699_000.0,
                        "last_alert_price": 156.5,
                        "last_observed_lanes": ["sustained"],
                    }
                ),
                encoding="utf-8",
            )
            move = self.make_move(-0.10, -0.20, -0.30)
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertFalse(result["alerted"])
            self.assertEqual(result["stage"], 0)
            saved = json.loads(paths["STATE_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(saved["stage"], 0)
            self.assertEqual(saved["last_observed_lanes"], [])


if __name__ == "__main__":
    unittest.main()

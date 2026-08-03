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
    ) -> shock.FxMove:
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
        )

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

    def test_active_stage_uses_only_15_and_30_minutes(self):
        self.assertEqual(shock.determine_stage(self.make_move(-0.49, -0.74, -2.00)), 0)
        self.assertEqual(shock.determine_stage(self.make_move(-0.50, 0.0, 0.0)), 1)
        self.assertEqual(shock.determine_stage(self.make_move(0.0, -0.75, 0.0)), 1)
        self.assertEqual(shock.determine_stage(self.make_move(-1.00, 0.0, 0.0)), 2)
        self.assertEqual(shock.determine_stage(self.make_move(0.0, -1.25, 0.0)), 2)

    def test_60_minute_is_residual_only(self):
        move = self.make_move(0.10, 0.20, -1.02)
        self.assertEqual(shock.determine_stage(move), 0)
        self.assertEqual(shock.determine_residual_stage(move), 1)
        move2 = self.make_move(0.10, 0.20, -1.50)
        self.assertEqual(shock.determine_stage(move2), 0)
        self.assertEqual(shock.determine_residual_stage(move2), 2)

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
            summary = paths["SUMMARY_PATH"].read_text(encoding="utf-8")
            self.assertIn("60분 충격 잔존 참고만 기록", summary)
            self.assertIn("텔레그램 미발송", summary)

    def test_new_active_alert_body_separates_60m_context(self):
        move = self.make_move(-0.60, -0.80, -1.10)
        checked_at = dt.datetime.fromtimestamp(move.latest_epoch, tz=dt.timezone.utc)
        body = shock.build_body(1, move, checked_at, reason="신규 진행형 급락")
        self.assertIn("진행형 구간", body)
        self.assertIn("15분", body)
        self.assertIn("30분", body)
        self.assertIn("60분 충격 잔존 참고 — 단독으로는 텔레그램을 보내지 않음", body)
        self.assertIn("알림 사유: 신규 진행형 급락", body)

    def test_same_stage_new_15m_trigger_realerts_after_cooldown(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_698_000.0,
            "last_alert_price": 156.8,
            "last_observed_trigger_windows": [30],
        }
        move = self.make_move(
            -0.60,
            -0.80,
            -0.20,
            price=156.3,
            latest_epoch=1_785_700_000.0,
        )
        triggers = shock.trigger_windows(1, move)
        self.assertEqual(triggers, [15, 30])
        self.assertEqual(
            shock.same_stage_reason(previous, 1, move, triggers),
            "반등 후 15분 재급락",
        )

    def test_same_stage_new_low_realerts_after_cooldown(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_698_000.0,
            "last_alert_price": 157.0,
            "last_observed_trigger_windows": [15, 30],
        }
        move = self.make_move(
            -0.60,
            -0.80,
            -0.20,
            price=156.50,
            latest_epoch=1_785_700_000.0,
        )
        self.assertEqual(
            shock.same_stage_reason(previous, 1, move, [15, 30]),
            "같은 단계 새 저점 확대",
        )

    def test_same_stage_realert_blocked_by_cooldown(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_699_400.0,
            "last_alert_price": 157.0,
            "last_observed_trigger_windows": [30],
        }
        move = self.make_move(
            -0.60,
            -0.80,
            -0.20,
            price=156.3,
            latest_epoch=1_785_700_000.0,
        )
        self.assertIsNone(shock.same_stage_reason(previous, 1, move, [15, 30]))

    def test_new_15m_trigger_during_cooldown_is_not_marked_observed(self):
        previous = {
            "stage": 1,
            "last_alert_epoch": 1_785_699_400.0,
            "last_alert_price": 156.8,
            "last_observed_trigger_windows": [30],
        }
        move = self.make_move(
            -0.60,
            -0.80,
            0.0,
            price=156.4,
            latest_epoch=1_785_700_000.0,
        )
        self.assertFalse(
            shock.should_persist_observed_windows(
                previous,
                stage=1,
                triggers=[15, 30],
                move=move,
            )
        )

    def test_observed_trigger_change_is_persisted_without_alert(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = self.patch_paths(root)
            paths["STATE_PATH"].write_text(
                json.dumps(
                    {
                        "stage": 1,
                        "last_alert_epoch": 1_785_699_800.0,
                        "last_alert_price": 156.7,
                        "last_observed_trigger_windows": [15, 30],
                    }
                ),
                encoding="utf-8",
            )
            move = self.make_move(
                0.10,
                -0.80,
                0.0,
                price=156.6,
                latest_epoch=1_785_700_000.0,
            )
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertFalse(result["alerted"])
            saved = json.loads(paths["STATE_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(saved["last_observed_trigger_windows"], [30])

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
            self.assertEqual(saved["last_alert_trigger_windows"], [15])

    def test_clear_resets_stage_and_rearms(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = self.patch_paths(root)
            paths["STATE_PATH"].write_text(
                json.dumps(
                    {
                        "stage": 1,
                        "last_alert_epoch": 1_785_699_000.0,
                        "last_alert_price": 156.5,
                        "last_observed_trigger_windows": [15],
                    }
                ),
                encoding="utf-8",
            )
            move = self.make_move(-0.10, -0.20, -1.20)
            current = dt.datetime.fromtimestamp(move.latest_epoch + 60, tz=dt.timezone.utc)
            with mock.patch.object(shock, "fetch_move", return_value=move):
                result = shock.run(current=current)
            self.assertFalse(result["alerted"])
            self.assertEqual(result["stage"], 0)
            self.assertEqual(result["residual_stage"], 1)
            saved = json.loads(paths["STATE_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(saved["stage"], 0)
            self.assertEqual(saved["last_observed_trigger_windows"], [])


if __name__ == "__main__":
    unittest.main()

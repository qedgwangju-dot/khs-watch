from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_target_currency_confirmation as target  # noqa: E402


class YenCarryTargetCurrencyTests(unittest.TestCase):
    def move(self, code: str, ch30: float, ch60: float):
        return target.CrossMove(
            code=code,
            label=code,
            latest_jpy_per_target=10.0,
            latest_epoch=1_800_000_000.0,
            change_15m_pct=ch30 / 2,
            change_30m_pct=ch30,
            change_60m_pct=ch60,
            stressed=ch30 <= target.TARGET_30M_STRESS_PCT or ch60 <= target.TARGET_60M_STRESS_PCT,
        )

    def test_cross_series_is_jpy_per_target(self):
        usdjpy = [(1000.0 + i * 300, 160.0) for i in range(25)]
        usdmxn = [(1000.0 + i * 300, 20.0) for i in range(25)]
        result = target.cross_series(usdjpy, usdmxn)
        self.assertEqual(len(result), 25)
        self.assertAlmostEqual(result[-1][1], 8.0)

    def test_two_of_three_plus_yen_shock_confirms_spread(self):
        moves = [
            self.move("MXN", -0.40, -0.55),
            self.move("BRL", -0.38, -0.52),
            self.move("ZAR", -0.10, -0.15),
        ]
        result = target.classify_target_spread(moves, -0.55, -0.80, -0.90)
        self.assertEqual(result["stressed_count"], 2)
        self.assertTrue(result["broad_target_weakness"])
        self.assertTrue(result["yen_shock"])
        self.assertTrue(result["active_confirmation"])

    def test_target_weakness_without_yen_shock_is_not_carry_confirmation(self):
        moves = [
            self.move("MXN", -0.40, -0.55),
            self.move("BRL", -0.38, -0.52),
            self.move("ZAR", -0.10, -0.15),
        ]
        result = target.classify_target_spread(moves, -0.10, -0.15, -0.20)
        self.assertTrue(result["broad_target_weakness"])
        self.assertFalse(result["yen_shock"])
        self.assertFalse(result["active_confirmation"])


    def test_sparse_five_minute_bars_recover_from_fresh_one_minute(self):
        timestamp = 1_800_000_000
        now = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        jpy = [(float(timestamp - (89 - i) * 60), 158.0) for i in range(90)]
        brl = [(float(timestamp - (89 - i) * 60), 5.0) for i in range(90)]
        def fetch(symbol, interval="5m", range_days="5d"):
            self.assertEqual(interval, "1m")
            self.assertEqual(range_days, "1d")
            return jpy if symbol == target.fx.SYMBOL else brl
        with mock.patch.object(target, "fetch_symbol_points", side_effect=fetch):
            result = target.recover_sparse_target_cross(
                "BRL", "BRL=X", "브라질 헤알", [jpy[-1]], [brl[-1]], now
            )
        self.assertEqual(result.code, "BRL")
        self.assertFalse(result.stressed)
        self.assertAlmostEqual(result.latest_jpy_per_target, 31.6)

    def test_sparse_fallback_rejects_stale_one_minute(self):
        timestamp = 1_800_000_000
        now = dt.datetime.fromtimestamp(timestamp + 1200, dt.timezone.utc)
        jpy = [(float(timestamp - (89 - i) * 60), 158.0) for i in range(90)]
        brl = [(float(timestamp - (89 - i) * 60), 5.0) for i in range(90)]
        with mock.patch.object(
            target, "fetch_symbol_points",
            side_effect=lambda symbol, **_: jpy if symbol == target.fx.SYMBOL else brl
        ):
            with self.assertRaisesRegex(RuntimeError, "1m fallback stale"):
                target.recover_sparse_target_cross(
                    "BRL", "BRL=X", "브라질 헤알", [jpy[-1]], [brl[-1]], now
                )

    def test_sparse_fallback_rejects_cross_vendor_price_mismatch(self):
        timestamp = 1_800_000_000
        now = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        jpy = [(float(timestamp - (89 - i) * 60), 158.0) for i in range(90)]
        brl = [(float(timestamp - (89 - i) * 60), 5.0) for i in range(90)]
        with mock.patch.object(
            target, "fetch_symbol_points",
            side_effect=lambda symbol, **_: jpy if symbol == target.fx.SYMBOL else brl
        ):
            with self.assertRaisesRegex(RuntimeError, "1m/5m price mismatch"):
                target.recover_sparse_target_cross(
                    "BRL", "BRL=X", "브라질 헤알",
                    [jpy[-1]], [(float(timestamp), 4.9)], now
                )

    def test_missing_third_currency_is_explicit_in_alert(self):
        context = {
            "moves": [{"code": "MXN", "change_15m_pct": 0.0,
                       "change_30m_pct": 0.0, "change_60m_pct": 0.0,
                       "stressed": False}],
            "coverage_limited": True,
            "available_count": 1,
            "incomplete": True,
            "classification": {"active_confirmation": False},
        }
        report = target.append_context("기존 알림", context)
        self.assertIn("자료 확인 범위: 1/3개 통화", report)
        self.assertIn("누락 통화는 확인 불가", report)
        self.assertIn("위험도 계산에서 제외", report)

    def test_one_target_currency_does_not_confirm_broad_unwind(self):
        moves = [
            self.move("MXN", -0.60, -0.80),
            self.move("BRL", -0.10, -0.15),
            self.move("ZAR", -0.05, -0.10),
        ]
        result = target.classify_target_spread(moves, -0.60, -0.80, -1.10)
        self.assertEqual(result["stressed_count"], 1)
        self.assertFalse(result["broad_target_weakness"])
        self.assertFalse(result["active_confirmation"])


if __name__ == "__main__":
    unittest.main()

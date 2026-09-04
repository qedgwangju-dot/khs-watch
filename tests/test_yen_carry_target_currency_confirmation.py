from __future__ import annotations

import pathlib
import sys
import unittest

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

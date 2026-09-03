from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_structural_upgrade as structural  # noqa: E402


class YenCarryStructuralUpgradeTests(unittest.TestCase):
    def test_mof_split_separates_equity_and_long_term_debt(self):
        rows = [
            ["2026-08-02~08-08", "0", "0", "1000", "0", "0", "-5000", "-4000", "0", "0", "0", "-4000"],
            ["2026-08-09~08-15", "0", "0", "2000", "0", "0", "-4000", "-2000", "0", "0", "0", "-2000"],
            ["2026-08-16~08-22", "0", "0", "3000", "0", "0", "-3000", "0", "0", "0", "0", "0"],
            ["2026-08-23~08-29", "0", "0", "4000", "0", "0", "-2000", "2000", "0", "0", "0", "2000"],
        ]
        result = structural.parse_mof_week_split("\n".join(",".join(r) for r in rows))
        self.assertAlmostEqual(result.latest_2w_equity_trillion_yen, 0.7)
        self.assertAlmostEqual(result.latest_2w_lt_debt_trillion_yen, -0.5)
        self.assertAlmostEqual(result.prior_2w_lt_debt_trillion_yen, -0.9)
        self.assertAlmostEqual(result.ytd_lt_debt_trillion_yen, -1.4)

    def test_parse_auction_html_and_quality(self):
        html = """
        <table><tr>
        <td>10-Year</td><td>383</td><td>9/1/2026</td><td>9/2/2026</td><td>6/20/2036</td><td>2.7%</td>
        <td>6,538.5</td><td>1,989.6</td><td>97.64</td><td>3.011%</td><td>29.5%</td><td>97.76</td><td>2.995%</td>
        </tr></table>
        """
        result = structural.parse_auction_html(html, "https://example.com", 10)
        self.assertAlmostEqual(result.bid_to_cover, 6538.5 / 1989.6)
        self.assertAlmostEqual(result.tail_bp, 1.6)
        self.assertFalse(structural.is_weak_auction(result))

    def test_consecutive_three_percent_closes(self):
        rows = [("a", 2.98), ("b", 3.01), ("c", 3.02)]
        self.assertEqual(structural.consecutive_above(rows, 3.0), 2)

    def test_structural_reason_detects_boundary_and_ytd_flow_sign_change(self):
        previous = {
            "initialized": True,
            "source_dates": {"mof_week": "w1", "auction10": "a1", "auction30": "b1"},
            "values": {
                "jgb10_ge_3": False,
                "jgb10_consecutive_days_ge_3": 0,
                "mof_lt_debt_2w_trillion_yen": 0.2,
                "mof_lt_debt_ytd_trillion_yen": 1.0,
            },
        }
        pending = {
            "initialized": True,
            "source_dates": {"mof_week": "w2", "auction10": "a2", "auction30": "b1"},
            "values": {
                "jgb10_ge_3": True,
                "jgb10_consecutive_days_ge_3": 2,
                "mof_lt_debt_2w_trillion_yen": -0.3,
                "mof_lt_debt_ytd_trillion_yen": -1.0,
            },
        }
        reasons = structural.structural_reasons(previous, pending, True)
        self.assertTrue(any("3% 구조적 경계 진입" in r for r in reasons))
        self.assertTrue(any("2영업일" in r for r in reasons))
        self.assertTrue(any("연초 이후 누적 방향 전환" in r for r in reasons))
        self.assertTrue(any("10년 JGB 입찰" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()

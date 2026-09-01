from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import global_rates_structural_watch as structural  # noqa: E402
import global_rates_structural_enrich as enrich  # noqa: E402


class GlobalRatesStructuralWatchTests(unittest.TestCase):
    def test_august_ten_year_auction_is_very_weak(self) -> None:
        html = """
        <table><tr>
        <td>10-Year</td><td>383</td><td>8/4/2026</td><td>8/5/2026</td><td>6/20/2036</td>
        <td>2.7%</td><td>5,062.4</td><td>1,979.1</td><td>98.46</td><td>2.900%</td>
        <td>19.3605%</td><td>98.92</td><td>2.840%</td><td>0.719</td><td>620.0</td><td>-</td>
        </tr></table>
        """
        result = structural.parse_auction_result(html, "https://example.com")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["bid_to_cover"], 5062.4 / 1979.1, places=4)
        self.assertAlmostEqual(result["tail_bp"], 6.0, places=6)
        self.assertEqual(result["grade"], "수요 매우 약함")

    def test_september_ten_year_auction_is_recovery_vs_august(self) -> None:
        previous = {"bid_to_cover": 5062.4 / 1979.1, "tail_bp": 6.0, "grade": "수요 매우 약함"}
        current = {"bid_to_cover": 6538.5 / 1989.6, "tail_bp": 1.6, "grade": "중립"}
        self.assertTrue(enrich.recovery_signal(current, previous))
        self.assertFalse(enrich.deterioration_signal(current, previous))

    def test_june_ten_year_auction_is_strong(self) -> None:
        auction = {"bid_to_cover": 7003.1 / 1983.9, "tail_bp": 0.7}
        self.assertEqual(structural.auction_grade(auction), "수요 강함")

    def test_calendar_parser_finds_same_tenor_date(self) -> None:
        page = """
        <table>
          <tr><td>Sep. 1, 2026</td><td>10-year(383)</td><td>Detail</td></tr>
          <tr><td>Sep. 3, 2026</td><td>30-year(91)</td><td>Detail</td></tr>
        </table>
        """
        self.assertEqual(enrich.parse_calendar_same_tenor(page, "10-Year"), [enrich.dt.date(2026, 9, 1)])

    def test_gpif_latest_allocation_and_one_percent_point(self) -> None:
        page = """
        国内債券 819,976 25.59%
        外国債券 787,980 24.60%
        国内株式 784,321 24.48%
        外国株式 811,454 25.33%
        合計 3,203,732 100.00%
        """
        result = structural.parse_gpif_latest(page)
        self.assertEqual(result["actual_pct"]["domestic_bonds"], 25.59)
        self.assertEqual(result["total_oku_yen"], 3_203_732)
        self.assertAlmostEqual(result["one_pct_point_trillion_yen"], 3.203732, places=6)

    def test_gpif_policy_target_and_tolerance(self) -> None:
        page = """
        資産構成割合 25% 25% 25% 25%
        乖離許容幅 各資産 ±6% ±5% ±6% ±6%
        """
        result = structural.parse_gpif_policy(page)
        self.assertEqual(result["target_pct"]["domestic_bonds"], 25.0)
        self.assertEqual(result["target_pct"]["foreign_equities"], 25.0)
        self.assertEqual(result["tolerance_pp"]["domestic_bonds"], 6.0)
        self.assertEqual(result["tolerance_pp"]["foreign_bonds"], 5.0)

    def test_boj_survey_release_date_and_label(self) -> None:
        page = """
        <p>2026年 9月 1日</p>
        <a href="/paym/bond/bond2608.pdf">2026年8月調査</a>
        """
        result = structural.parse_boj_survey(page)
        self.assertIsNotNone(result)
        self.assertEqual(result["posted_date"], "2026-09-01")
        self.assertEqual(result["label"], "2026年8月調査")
        self.assertIn("bond2608.pdf", result["url"])

    def test_yen_amount_parser(self) -> None:
        amount = structural.parse_yen_amount("15兆3,993億円")
        self.assertEqual(amount, 15_399_300_000_000.0)

    def test_gpif_zero_sum_summary_shows_both_sides(self) -> None:
        previous = {
            "domestic_bonds": 25.0,
            "foreign_bonds": 25.0,
            "domestic_equities": 25.0,
            "foreign_equities": 25.0,
        }
        current = {
            "domestic_bonds": 26.2,
            "foreign_bonds": 24.2,
            "domestic_equities": 24.8,
            "foreign_equities": 24.8,
        }
        summary = structural.gpif_zero_sum_summary(previous, current)
        self.assertIn("국내채권 +1.20%p", summary)
        self.assertIn("외국채권 -0.80%p", summary)

    def test_krw_conversion_uses_same_date_cross_rate(self) -> None:
        fx = {"yenkrw": 8.6}
        self.assertEqual(structural.yen_to_krw(3_000_000_000_000.0, fx), 25_800_000_000_000.0)


if __name__ == "__main__":
    unittest.main()

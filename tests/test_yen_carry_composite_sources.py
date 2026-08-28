from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_composite_runner as runner  # noqa: E402
from krw_fx import JpyKrwQuote  # noqa: E402


class YenCarryCompositeSourceTests(unittest.TestCase):
    def test_cftc_tff_jpy_leveraged_fields_and_previous_are_exact(self):
        text = """
        Traders in Financial Futures - Futures Only Positions as of August 4, 2026
        JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE (CONTRACTS OF JPY 12,500,000)
        CFTC Code #097741 Open Interest is 419,393
        Positions
        112,779 81,356 16,752 72,815 115,237 19,194 75,758 136,583 7,533 78,282 1,363 1,770 34,510 39,605
        Changes from: July 28, 2026 Total Change is: -12,973
        -42,460 65,454 6,715 2,172 -38,463 -1,918 -994 -42,159 59 36,262 -334 0 -12,809 -2,327
        Percent of Open Interest Represented by Each Category of Trader
        """
        result = runner.parse_cftc_tff_html(text)
        self.assertEqual(result.report_date, "2026-08-04")
        self.assertEqual(result.previous_report_date, "2026-07-28")
        self.assertEqual(result.open_interest, 419393)
        self.assertEqual(result.leveraged_long, 75758)
        self.assertEqual(result.leveraged_short, 136583)
        self.assertEqual(result.net_short, 60825)
        self.assertEqual(result.previous_net_short, 101990)
        self.assertTrue(result.short_covering)

    def test_mof_mojibake_week_label_is_normalized_without_touching_values(self):
        rows = [
            "2026�D7�D19�`7�D25,1,1,0,1,1,0,-2000,0,0,0,-2000",
            "2026�D7�D26�`8�D1,1,1,0,1,1,0,-1195,0,0,0,-1195",
            "2026�D8�D2�`8�D8,1,1,0,1,1,0,24000,0,0,0,24000",
            "2026�D8�D9�`8�D15,1,1,0,1,1,0,26905,0,0,0,26905",
        ]
        result = runner.parse_mof_week_csv("\n".join(rows))
        self.assertEqual(result.latest_week, "2026-08-09~08-15")
        self.assertEqual(result.previous_week, "2026-08-02~08-08")
        self.assertAlmostEqual(result.latest_two_week_trillion_yen, 5.0905)
        self.assertAlmostEqual(result.previous_two_week_trillion_yen, -0.3195)

    def test_cftc_source_is_official_current_tff_page(self):
        self.assertEqual(runner.base.CFTC_TFF_API, "https://www.cftc.gov/dea/futures/financial_lf.htm")

    def test_mof_yen_money_is_always_paired_with_krw(self):
        mof = runner.base.MofOutwardFlow(
            latest_week="2026-08-09~08-15",
            previous_week="2026-08-02~08-08",
            latest_two_week_trillion_yen=5.0905,
            previous_two_week_trillion_yen=-0.3195,
            outward_buying=True,
            outward_accelerating=True,
        )
        quote = JpyKrwQuote("2026-08-21", 1385.01, 158.91, 1385.01 / 158.91)
        body = "\n".join([
            "포지션·자금",
            "- 일본 거주자 해외주식+장기채: 최근 2주 +5.09조엔 / 직전 2주 -0.32조엔 (순매수 +)",
            "",
            "출처",
            "- Japan MOF 해외증권투자: https://www.mof.go.jp/example.csv",
        ])
        enriched = runner.enrich_krw_lines(body, mof, quote)
        self.assertIn("+5.09조엔 (약", enriched)
        self.assertIn("-0.32조엔 (약 -", enriched)
        self.assertIn("원화 환산 기준", enriched)
        self.assertIn("FRED USD/KRW", enriched)
        self.assertIn("FRED USD/JPY", enriched)


if __name__ == "__main__":
    unittest.main()

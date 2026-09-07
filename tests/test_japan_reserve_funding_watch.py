from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import japan_reserve_funding_watch as watch  # noqa: E402


class DummyQuote:
    usdkrw = 1346.09
    krw_per_yen = 9.10


class JapanReserveFundingTests(unittest.TestCase):
    def test_parse_reserve_page_keeps_total_and_fx_reserves_separate(self):
        sample = """
        <html><body>
        <h1>International Reserves/Foreign Currency Liquidity (as of the end of August 2026)</h1>
        <div>September 7, 2026</div>
        <table>
          <tr><td>A. Official reserve assets</td><td>1,207,524</td></tr>
          <tr><td>(1) Foreign currency reserves</td><td>994,976</td></tr>
          <tr><td>(a) Securities</td><td>839,559</td></tr>
          <tr><td>(b) Deposits with</td><td>155,417</td></tr>
          <tr><td>(4) Gold</td><td>124,103</td></tr>
        </table>
        </body></html>
        """
        out = watch.parse_reserve_page(sample, "https://example.com/e0808.html")
        self.assertEqual(out.period, "August 2026")
        self.assertAlmostEqual(out.official_reserve_bn, 1207.524)
        self.assertAlmostEqual(out.fx_reserve_bn, 994.976)
        self.assertAlmostEqual(out.securities_bn, 839.559)
        self.assertAlmostEqual(out.deposits_bn, 155.417)
        self.assertAlmostEqual(out.gold_bn, 124.103)

    def test_parse_japanese_intervention_amount(self):
        sample = "外国為替平衡操作額 15兆3,993億円"
        self.assertAlmostEqual(watch._parse_japanese_yen_amount(sample), 15.3993)
        self.assertAlmostEqual(watch._parse_japanese_yen_amount("外国為替平衡操作額 0円"), 0.0)

    def test_tic_parser_reads_japan_monthly_holdings(self):
        sample = """
        <table>
        <tr><th>Country</th><th>2026-06</th><th>2026-05</th><th>2026-04</th></tr>
        <tr><td>Japan</td><td>1116.7</td><td>1143.1</td><td>1209.9</td></tr>
        </table>
        """
        out = watch.parse_tic_table5(sample)
        self.assertEqual(out.latest_month, "2026-06")
        self.assertAlmostEqual(out.latest_bn_usd, 1116.7)
        self.assertAlmostEqual(out.change_bn_usd, -26.4)

    def test_h41_custody_parser_reads_weekly_change(self):
        sample = """
        <table><tr>
        <td>Marketable U.S. Treasury securities</td><td>2,609,138</td><td>+ 7,211</td><td>- 228,137</td><td>2,601,241</td>
        </tr></table>
        """
        out = watch.parse_h41_treasury_custody(sample)
        self.assertAlmostEqual(out.level_bn_usd, 2609.138)
        self.assertAlmostEqual(out.weekly_change_bn_usd or 0, 7.211)

    def test_bootstrap_material_event_sends_critical_combo(self):
        current = watch.ReserveSnapshot(
            "August 2026", "September 7, 2026", "cur", 1207.524, 994.976, 839.559, 155.417, 124.103
        )
        previous = watch.ReserveSnapshot(
            "July 2026", "August 7, 2026", "prev", 1287.099, 1089.617, 927.332, 162.285, 109.521
        )
        intervention = watch.InterventionSnapshot("period", "release", "intervention", 15.3993)
        events = watch.classify_events(
            first=True,
            state={},
            current=current,
            previous=previous,
            intervention=intervention,
            tic=None,
            fima_level_bn=0.0,
            fima_release_date="September 3, 2026",
            custody=None,
        )
        kinds = {x["kind"] for x in events}
        self.assertIn("fx_reserve_below_1t", kinds)
        self.assertIn("official_reserve_drop", kinds)
        self.assertIn("securities_drop", kinds)
        self.assertIn("large_intervention", kinds)
        self.assertIn("funding_supply_combo", kinds)
        self.assertTrue(any(x["severity"] == "CRITICAL" for x in events))

    def test_alert_text_explicitly_corrects_one_trillion_denominator(self):
        current = watch.ReserveSnapshot(
            "August 2026", "September 7, 2026", "cur", 1207.524, 994.976, 839.559, 155.417, 124.103
        )
        previous = watch.ReserveSnapshot(
            "July 2026", "August 7, 2026", "prev", 1287.099, 1089.617, 927.332, 162.285, 109.521
        )
        intervention = watch.InterventionSnapshot("period", "release", "intervention", 15.3993)
        tic = watch.TicJapan("2026-06", "2026-05", 1116.7, 1143.1)
        title, body = watch.build_alert(
            now=dt.datetime(2026, 9, 8, 6, 30, tzinfo=watch.KST),
            events=[{"kind": "funding_supply_combo", "severity": "CRITICAL"}],
            current=current,
            previous=previous,
            intervention=intervention,
            tic=tic,
            fima_level_bn=0.0,
            fima_release_date="September 3, 2026",
            custody=watch.ForeignCustody(2609.138, 7.211),
            quote=DummyQuote(),
        )
        self.assertIn("1조달러 하회 아님", body)
        self.assertIn("<b>1조달러 하회</b>", body)
        self.assertIn("미국채 매도액", body)
        self.assertIn("TIC", body)
        self.assertIn("3단계 · 위험", title)


if __name__ == "__main__":
    unittest.main()

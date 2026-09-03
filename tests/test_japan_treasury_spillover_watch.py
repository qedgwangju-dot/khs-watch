from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import japan_treasury_spillover_watch as watch  # noqa: E402


class JapanTreasurySpilloverTests(unittest.TestCase):
    def test_mof_parser_separates_long_term_debt_from_equity_subtotal(self):
        rows = [
            "2026�D8�D16�`8�D22,100,80,20,500,800,-300,-280,10,20,-10,-290",
            "2026�D8�D23�`8�D29,100,80,20,400,1000,-600,-580,10,20,-10,-590",
        ]
        out = watch.parse_mof_week_csv("\n".join(rows))
        self.assertEqual(out.latest_week, "2026-08-23~08-29")
        self.assertAlmostEqual(out.latest_lt_debt_trillion_yen, -0.06)
        self.assertAlmostEqual(out.latest_equity_plus_lt_trillion_yen, -0.058)
        self.assertAlmostEqual(out.two_week_lt_debt_trillion_yen, -0.09)

    def test_h41_foreign_official_repo_proxy(self):
        sample = """
        <html><body><div>Release Date: September 3, 2026</div><table>
        <tr><td>Repurchase agreements 6</td><td>2</td><td>1</td></tr>
        <tr><td>Foreign official</td><td>1,500</td><td>+ 1,500</td><td>0</td><td>1,500</td></tr>
        <tr><td>Others</td><td>1</td><td>0</td></tr>
        </table></body></html>
        """
        out = watch.parse_h41_foreign_official_repo(sample)
        self.assertEqual(out.release_date, "September 3, 2026")
        self.assertAlmostEqual(out.level_bn_usd, 1.5)
        self.assertAlmostEqual(out.weekly_change_bn_usd or 0, 1.5)

    def test_two_year_auction_weakness_uses_same_rule_as_long_end(self):
        state = {
            "initialized": True,
            "source_dates": {},
            "snapshot": {},
            "auctions": {"2": {"date": "7/30/2026"}},
        }
        auctions = {
            "2": {
                "date": "8/28/2026",
                "btc": 2.966,
                "btc_drop_pct": -18.2,
                "tail_bp": 1.7,
                "tail_widen_bp": 1.3,
            }
        }
        events = watch.classify_events(
            first=False, state=state, flow=None, yields=None, auctions=auctions, fima=None, market=None
        )
        self.assertTrue(any(x["kind"] == "jgb_auction" and x["tenor"] == 2 for x in events))


if __name__ == "__main__":
    unittest.main()

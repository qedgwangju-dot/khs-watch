from __future__ import annotations

import pathlib
import datetime as dt
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


    def test_november_18_alert_does_not_call_lagged_market_live(self):
        now = dt.datetime(2026, 11, 18, 19, 13, tzinfo=watch.KST)
        flow = watch.MofFlow(
            "2026-11-01~11-07", "2026-10-25~10-31",
            -0.5376, 1.312, 0.7744, -1.1816,
        )
        market = {
            "market_date": "2026-11-16",
            "dgs10_date": "2026-11-16", "dgs30_date": "2026-11-16",
            "dgs10": 5.12, "dgs30": 5.46,
            "dgs10_change_bp": -3.0, "dgs30_change_bp": -1.0,
            "usdjpy_date": "2026-11-13",
            "usdjpy": 159.93, "usdjpy_change_pct": 0.21,
            "sofr_iorb_date": "2026-11-16",
            "sofr_iorb_bp": 3.0, "sofr_iorb_change_bp": 3.0,
        }
        auctions = {"20": {
            "date": "11/18/2026", "url": "https://www.mof.go.jp/example",
            "btc": 3.640, "prev_btc": 5.844, "btc_drop_pct": -37.7,
            "tail_bp": 2.6, "tail_widen_bp": 2.0,
        }}
        events = [{"kind": "jgb_auction", "severity": "WATCH", "tenor": 20}]
        title, body = watch.build_brief_alert(
            events, flow, None, auctions, None, market, None, now, live_fx=None
        )
        self.assertIn("일본 20년물 입찰 경계", title)
        self.assertIn("미국채 전이 현재 판정 보류", body)
        self.assertIn("2026-11-16", body)
        self.assertIn("참고 FRED 2026-11-13", body)
        self.assertIn("현재 청산·재구축 판정 보류", body)
        self.assertIn("1주 매도지만 2주 순매수", body)
        self.assertIn("직전 5.84배", body)
        self.assertIn("앞으로 어떻게 될까", body)
        self.assertLess(len(body), 2500)

    def test_stale_market_cannot_create_spillover_or_repatriation(self):
        now = dt.datetime(2026, 11, 18, 19, 13, tzinfo=watch.KST)
        flow = watch.MofFlow("2026-11-01~11-07", "prior", -1.2, -0.2, -1.4, -1.4)
        market = {
            "market_date": "2026-11-16",
            "dgs10_date": "2026-11-16", "dgs30_date": "2026-11-16",
            "usdjpy_date": "2026-11-13",
            "dgs10_change_bp": 15.0, "dgs30_change_bp": 12.0,
            "sofr_iorb_bp": 12.0, "sofr_iorb_change_bp": 6.0,
            "usdjpy_change_pct": -2.0,
        }
        events = watch.classify_events(
            first=False, state={"initialized": True, "source_dates": {}, "snapshot": {}},
            flow=flow,
            yields=({"jgb2": 1.80}, {"jgb2": 1.86}),
            auctions={}, fima=None, market=market, now=now,
        )
        kinds = {event["kind"] for event in events}
        self.assertIn("lt_debt_sale", kinds)
        self.assertNotIn("repatriation_combo", kinds)
        self.assertNotIn("ust_spillover", kinds)
        self.assertNotIn("basis_proxy", kinds)

    def test_40y_dutch_auction_without_average_yield_is_not_skipped(self):
        cells = [
            "40-Year", "19", "11/25/2026", "11/26/2026", "3/20/2066",
            "3.8%", "846.7", "299.8", "98.68", "3.865%",
            "28.8888%", "-", "-", "-",
        ]
        content = "<table><tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr></table>"
        parsed = watch.parse_auction(content, "https://mof.go.jp/test", 40)
        self.assertAlmostEqual(parsed.btc, 846.7 / 299.8)
        self.assertIsNone(parsed.tail_bp)
        self.assertIn("미공개", watch.fchr_tail(parsed.tail_bp))
        auction = {"40": {
            "date": parsed.date, "btc": parsed.btc, "btc_drop_pct": -15.2,
            "tail_bp": None, "tail_widen_bp": None,
        }}
        events = watch.classify_events(
            first=False, state={"initialized": True, "source_dates": {}, "snapshot": {},
                                "auctions": {"40": {"date": "7/22/2026"}}},
            flow=None, yields=None, auctions=auction, fima=None, market=None,
        )
        self.assertTrue(any(e["kind"] == "jgb_auction" and e["tenor"] == 40 for e in events))

    def test_new_current_market_can_show_direction_without_claiming_causality(self):
        now = dt.datetime(2026, 11, 18, 19, 13, tzinfo=watch.KST)
        flow = watch.MofFlow("2026-11-01~11-07", "prior", -0.6, -0.9, -1.5, -1.5)
        market = {
            "market_date": "2026-11-17",
            "dgs10_date": "2026-11-17", "dgs30_date": "2026-11-17",
            "usdjpy_date": "2026-11-17",
            "dgs10_change_bp": 8.0, "dgs30_change_bp": 7.0,
            "dgs10": 5.2, "dgs30": 5.5,
            "sofr_iorb_date": "2026-11-17",
            "sofr_iorb_bp": 11.0, "sofr_iorb_change_bp": 6.0,
            "usdjpy_change_pct": -1.2, "usdjpy": 157.0,
        }
        events = watch.classify_events(
            first=False, state={"initialized": True, "source_dates": {}, "snapshot": {}},
            flow=flow, yields=({"jgb2": 1.80}, {"jgb2": 1.86}),
            auctions={}, fima=None, market=market, now=now,
        )
        kinds = {event["kind"] for event in events}
        self.assertIn("repatriation_combo", kinds)
        self.assertIn("basis_proxy", kinds)
        title, body = watch.build_brief_alert(
            events, flow, None, {}, None, market, None, now, live_fx=None,
        )
        self.assertIn("전이 위험 상승(원인 미확정)", body)

    def test_h41_is_not_japan_specific_critical_overreaction(self):
        state = {"initialized": True, "source_dates": {}, "snapshot": {}}
        flow = watch.MofFlow("new-week", "prior-week", -0.8, -0.5, -1.3, -1.3)
        fima = watch.FimaProxy("November 12, 2026", 1.5, 1.5)
        events = watch.classify_events(
            first=False, state=state, flow=flow, yields=None,
            auctions={}, fima=fima, market=None,
        )
        overlap = [x for x in events if x["kind"] == "official_private_overlap"]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0]["severity"], "WATCH")


if __name__ == "__main__":
    unittest.main()

# Keep a path-matched push trigger so the live workflow validates after installation.

"""Financial-investment display from preserved/provider-defined fields; no network."""
from collections import deque
import copy
import html
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import requests
import kospi_shock_episode_watch as watch
import market_flow_channels as channels
import market_namuh_flow as namuh
import market_kiwoom_flow as kiwoom
from market_investors import ALERT_ACTORS, DISPLAY_ACTORS, SUBGROUP_NOTE, subgroup_value
from test_market_investment_trust import NOW, START, future_body, snap
from test_market_kiwoom_flow import cash, NOW as KIWOOM_NOW


def future(market="KOSDAQ", value=-55, volume=-11, code="0001"):
    body = future_body(market)
    body["t8463OutBlock"]["stocode"] = code
    body["t8463OutBlock1"][0].update(stomsamt=value, stomsvol=volume)
    return body


def snapshot(ts, market, financial=0, selling=False):
    row = snap(ts, market, -3 if selling else 0, selling)
    for channel in ("현물", "선물", "지수선물"):
        row[channel]["금융투자"] = financial
    row["지수선물"]["summary"]["stocode"] = "0001"
    row["지수선물"]["source_row"].update(stomsamt=financial, stomsvol=financial)
    return row


class FinancialInvestment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"MARKET_SOURCE_OFFLINE": "1", "MARKET_SOURCE_EVIDENCE_DIR": self.temp.name}).start()
        patch.object(requests.sessions.Session, "request", side_effect=AssertionError("network forbidden")).start()
        patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")).start()

    def test_official_contract_uses_securities_fields_and_code(self):
        contract = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/market_financial_source_contract_20261026.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["t1602"]["sv_01"], "증권순매수")
        self.assertEqual(contract["t8463"]["stomsamt"], "증권순매수거래대금")
        self.assertEqual(contract["t8463"]["stocode_example"], "0001")

    def test_both_spot_markets_keep_exact_field_with_one_existing_query(self):
        for market, code in [("1", "001"), ("3", "301")]:
            body = {"t1602OutBlock": {"ex_upcode": "U"+code}, "t1602OutBlock1": [
                {"time": "141000", "sv_17": 10, "sv_18": 40, "sv_08": -50, "sv_03": -3, "sv_01": -12}]}
            with patch.object(watch, "ls_post", return_value=body) as post, patch.object(watch.time, "time", return_value=NOW):
                row = watch.investor_current("unused", market, code, "U")
            self.assertEqual(row["금융투자"], -12)
            self.assertEqual(row["기관"], 40)
            post.assert_called_once()

    def test_missing_spot_financial_does_not_become_parent_or_zero(self):
        for value in (None, "", "NaN", "inf"):
            block = {"source_tr": "t1602", "기관": 100, "금융투자": value, "source_row": {"sv_01": value}}
            self.assertIsNone(subgroup_value(block, "금융투자"))

    def test_exact_future_code_amount_and_integer_volume_in_both_markets(self):
        for market in ("KOSPI", "KOSDAQ"):
            row = channels.parse_futures(future(market), market, NOW+1)
            self.assertEqual(subgroup_value(row, "금융투자"), -55)
            self.assertFalse(row["unit_verified"])
            self.assertNotIn("금융투자", channels.futures_investor_quality(row["summary"], row["source_row"])["amounts"])

    def test_bad_optional_financial_only_holds_subgroup(self):
        for changes in ({"code": "0003"}, {"value": None}, {"volume": None}, {"volume": 1.5}):
            row = channels.parse_futures(future(**changes), "KOSDAQ", NOW+1)
            self.assertIsNone(row["금융투자"])
            self.assertEqual(row["기관"], -10)
            self.assertTrue(row["investor_quality"]["verified"])

    def test_explicit_zero_and_tampered_cached_values(self):
        row = channels.parse_futures(future(value=0, volume=0), "KOSDAQ", NOW+1)
        self.assertEqual(subgroup_value(row, "금융투자"), 0)
        row["금융투자"] = 100
        self.assertIsNone(subgroup_value(row, "금융투자"))

    def test_old_endpoint_missing_financial_keeps_delta_missing(self):
        self.assertIsNone(watch._actor_delta({"기관": 20}, {"기관": 30, "금융투자": -50})["금융투자"])
        self.assertEqual(watch._actor_delta({"금융투자": 0}, {"금융투자": 0})["금융투자"], 0)

    def test_every_crash_stage_in_both_markets_shows_parent_and_two_subgroups(self):
        w = watch.Watch("unused", [], "", False)
        w.flows = deque([snapshot(START, "KOSPI"), snapshot(NOW, "KOSPI", -75, True)])
        w.kosdaq_flows = deque([snapshot(START, "KOSDAQ"), snapshot(NOW, "KOSDAQ", -75, True)])
        for market in ("KOSPI", "KOSDAQ"):
            ep = {"start_ts": START, "start_price": 100, "low_ts": NOW, "low_price": 99, "market": market}
            for stage in ("start", "expand", "end", "close"):
                with self.subTest(market=market, stage=stage):
                    if market == "KOSDAQ":
                        text = w.build_kosdaq_drop_alert(stage, ep, NOW+20, 99.5)
                    elif stage in ("end", "close"):
                        text = w.build_end(ep, NOW+20, 99.5, session_close=stage=="close")
                    else:
                        text = w.build_alert(stage, ep, NOW+20, 99.5)
                    for name in ("기관", "투신(기관 내)", "금융투자(기관 내)"):
                        self.assertIn(name, text)
                    self.assertIn("금융투자(기관 내) <b>-75억원</b>", text)
                    self.assertIn("금융투자(기관 내) <b>-75</b>", text)
                    self.assertIn(SUBGROUP_NOTE, text)
                    self.assertLessEqual(len(html.unescape(re.sub("<[^>]+>", "", text))), 4096)
            att = w._market_attribution(START, NOW, market)
            self.assertEqual(att["spot_leader"], "외국인")
            self.assertNotIn("금융투자", att["cross_sellers"])
            self.assertNotIn("금융투자", att["verdict"])

    def test_display_addition_does_not_enable_new_surge_actor(self):
        self.assertIn("금융투자", DISPLAY_ACTORS)
        self.assertNotIn("금융투자", ALERT_ACTORS)

    def test_preserved_namuh_values_render_financial_without_changing_units(self):
        captures = json.loads((Path(__file__).parent / "test_fixtures/namuh_market_readback_20261020.json").read_text(encoding="utf-8"))["captures"]
        for market, capture in captures.items():
            result = namuh.derive_capture(capture)
            result["evidence"] = namuh.retain_capture(capture)
            cash_raw = capture["sources"]["cash"]["response"]["Output_0"][0]["scrt_val"]
            future_raw = capture["sources"]["futures"]["response"]["Output_0"][0]["scrt_val"]
            self.assertEqual(result["components"]["cash"]["values"]["금융투자"], int(cash_raw)/100)
            self.assertEqual(result["components"]["futures"]["values"]["금융투자"], int(future_raw))
            text = "\n".join(namuh.lines(result, market, result["received_ts"]+1))
            self.assertIn("금융투자", text)
            self.assertIn("투신·금융투자⊂기관", text)
            self.assertLessEqual(len(html.unescape(re.sub("<[^>]+>", "", text))), 290)

    def test_kiwoom_verified_zero_financial_value_is_visible(self):
        for market in ("KOSPI", "KOSDAQ"):
            entry = cash(market)
            entry["retained_evidence"] = kiwoom._retain(entry)
            result = kiwoom.parse_cash(entry, market)
            text = "\n".join(kiwoom.cash_lines(result, market, KIWOOM_NOW))
            self.assertIn("금융투자(기관 내)", text)
            self.assertEqual(result["values"]["금융투자"], 0)
            self.assertLessEqual(len(html.unescape(re.sub("<[^>]+>", "", text))), 280)


if __name__ == "__main__":
    unittest.main()

"""Scope, dated-clock, missingness and symmetric incident regressions."""
import copy
import datetime as dt
import unittest
from collections import deque
from unittest.mock import patch

import market_flow_channels as channels
import kospi_shock_episode_watch as watch

NOW = dt.datetime(2026, 10, 14, 14, 30, 25, tzinfo=channels.KST).timestamp()


def response(market="KOSDAQ", **row_changes):
    row = {"date": "20261014", "time": "143000", "datetime": "20261014143000",
           "indmsamt": "30", "formsamt": "-20", "sysmsamt": "-10",
           "indmsvol": 9000, "formsvol": -8000, "sysmsvol": -1000}
    row.update(row_changes)
    return {"t8463OutBlock": {"tm_rng": "D", "fot_clsf_cd": "F",
                             "bsc_asts_id": channels.MARKET_SPECS[market]["asset"]},
            "t8463OutBlock1": [row]}


def snapshot(ts, market, selling=False):
    actors = {"외국인": -100, "기관": -10, "개인": 110} if selling else {"외국인": 0, "기관": 0, "개인": 0}
    spot = {"sample_ts": ts, "market": market, "source_tr": "t1602", **actors}
    fut = {**spot, "asset": channels.MARKET_SPECS[market]["asset"], "source_tr": "t8463",
           "source_scope_verified": True, "unit": "LS_raw_amount", "unit_verified": False}
    total = -60 if selling else 0
    pgm = {"sample_ts": ts, "market": market, "source_tr": "t1640", "unit": "LS_raw_amount",
           "전체": total, "차익": total / 3, "비차익": total * 2 / 3, "표본시차초": 3,
           "source_time_verified": False, "timestamp_basis": "query_interval"}
    return {"ts": ts, "market": market, "현물": spot, "지수선물": fut, "프로그램": pgm}


class SourceContract(unittest.TestCase):
    def test_exact_product_requests(self):
        for market, asset in (("KOSPI", "K2I"), ("KOSDAQ", "KQI")):
            query = channels.futures_request(market)["t8463InBlock"]
            self.assertEqual(query["bsc_asts_id"], asset)
            self.assertEqual(query["tm_rng"], "D")
            self.assertEqual(query["fot_clsf_cd"], "F")

    def test_amounts_are_neither_volume_nor_currency_conversion(self):
        block = channels.parse_futures(response(), "KOSDAQ", NOW)
        self.assertEqual(block["외국인"], -20)
        self.assertEqual(block["unit"], "LS_raw_amount")
        self.assertFalse(block["unit_verified"])
        self.assertEqual(block["received_ts"] - block["sample_ts"], 25)

    def test_day_only_datetime_example_is_supported(self):
        self.assertEqual(channels.parse_futures(response(datetime="20261014"), "KOSDAQ", NOW)["time"], "143000")

    def test_other_market_echo_is_rejected(self):
        with self.assertRaises(ValueError):
            channels.parse_futures(response("KOSPI"), "KOSDAQ", NOW)

    def test_missing_echo_is_rejected(self):
        body = response()
        body["t8463OutBlock"].pop("bsc_asts_id")
        with self.assertRaises(ValueError):
            channels.parse_futures(body, "KOSDAQ", NOW)

    def test_option_or_night_echo_is_rejected(self):
        for field, bad in (("fot_clsf_cd", "P"), ("tm_rng", "N"), ("tm_rng", "U")):
            body = response()
            body["t8463OutBlock"][field] = bad
            with self.assertRaises(ValueError):
                channels.parse_futures(body, "KOSDAQ", NOW)

    def test_row_product_conflict_is_rejected(self):
        with self.assertRaises(ValueError):
            channels.parse_futures(response(bsc_asts_id="K2I"), "KOSDAQ", NOW)

    def test_prior_day_missing_clock_and_nonfinite_values_held(self):
        for changes in ({"date": "20261013"}, {"time": ""}, {"formsamt": None},
                        {"formsamt": "nan"}, {"formsamt": "inf"}, {"time": "153000"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                channels.parse_futures(response(**changes), "KOSDAQ", NOW)

    def test_conflicting_clock_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            channels.parse_futures(response(datetime="20261014142959"), "KOSDAQ", NOW)

    def test_latest_source_row_is_selected_not_response_order(self):
        body = response()
        body["t8463OutBlock1"].append({**body["t8463OutBlock1"][0], "time": "142930", "datetime": "20261014142930"})
        self.assertEqual(channels.parse_futures(body, "KOSDAQ", NOW)["time"], "143000")

    def test_latest_missing_amount_cannot_use_older_complete_row(self):
        body = response(formsamt=None)
        body["t8463OutBlock1"].append({**response()["t8463OutBlock1"][0], "time": "142930", "datetime": "20261014142930"})
        with self.assertRaises(ValueError):
            channels.parse_futures(body, "KOSDAQ", NOW)

    def test_correct_program_market_components_and_receipt_interval(self):
        for market, expected in (("KOSPI", ("11", "12", "13")), ("KOSDAQ", ("21", "22", "23"))):
            calls = []
            def post(token, path, tr, query, **kw):
                calls.append(query["t1640InBlock"])
                return {"t1640OutBlock": {"value": [-90, -30, -60][len(calls)-1]}}
            with patch.object(channels.time, "time", side_effect=[100, 101, 102, 103, 104, 105]):
                pgm = channels.program_current("unused", market, post)
            self.assertEqual(tuple(x["gubun"] for x in calls), expected)
            self.assertTrue(all(x["exchgubun"] == "U" for x in calls))
            self.assertEqual(pgm["sample_ts"], 105)
            self.assertEqual(pgm["표본시차초"], 5)
            self.assertEqual(pgm["전체대비차이"], 0)
            self.assertFalse(pgm["source_time_verified"])

    def test_program_missing_component_not_zero_filled(self):
        with self.assertRaises(ValueError):
            channels.program_current("unused", "KOSDAQ", lambda *a, **k: {"t1640OutBlock": {"value": None}})

    def test_program_conflicting_response_selector_is_rejected(self):
        with self.assertRaises(ValueError):
            channels.program_current("unused", "KOSDAQ", lambda *a, **k: {"t1640OutBlock": {"value": 5, "gubun": "11"}})


class IncidentSymmetry(unittest.TestCase):
    def setUp(self):
        self.w = watch.Watch("unused", [], "", False)
        self.w.session_open_ts = 900
        self.w.flows = deque([snapshot(995, "KOSPI"), snapshot(1995, "KOSPI", True)])
        self.w.kosdaq_flows = deque([snapshot(995, "KOSDAQ"), snapshot(1995, "KOSDAQ", True)])

    def get(self, market):
        return self.w._market_attribution(1000, 2000, market)

    def test_identical_channel_logic_and_actor_verdict(self):
        first, second = self.get("KOSPI"), self.get("KOSDAQ")
        for field in ("spot", "futures", "program", "cross_sellers", "spot_leader", "futures_leader",
                      "confidence", "verdict", "program_quality", "channel_status"):
            self.assertEqual(first[field], second[field], field)
        self.assertTrue(first["available"])
        self.assertEqual(first["confidence"], "중간")
        self.assertFalse(first["program_quality"])

    def test_program_without_source_clock_never_high_confidence(self):
        for market in channels.MARKET_SPECS:
            att = self.get(market)
            self.assertFalse(att["program_source_time_verified"])
            self.assertIn("원천 공표시각 미제공", watch.program_quality_label(att))
            self.assertNotEqual(att["confidence"], "높음")

    def test_same_rendered_sections_without_cross_market_ambiguity(self):
        for market in channels.MARKET_SPECS:
            text = "\n".join(watch.market_attribution_lines(self.get(market), market))
            for label in ("현물(통합)", "선물:", "현물 최다매도", "선물 최다매도", "현물·선물 동시매도",
                          "프로그램 전체(차익+비차익)", "합계 차이 1%"):
                self.assertIn(label, text)
            self.assertNotIn("양시장 동시매도", text)
            self.assertIn("환산 단위 미확인", text)

    def test_kospi_data_never_rescues_missing_kosdaq_futures(self):
        self.w.kosdaq_flows[-1]["지수선물"] = None
        att = self.get("KOSDAQ")
        self.assertFalse(att["available"])
        self.assertIsNone(att["futures"])
        self.assertIsNotNone(att["spot"])
        self.assertIn("선물", att["reason"])

    def test_wrong_asset_or_market_block_not_attributed(self):
        for wrong in ("asset", "market"):
            with self.subTest(wrong=wrong):
                w = copy.deepcopy(list(self.w.kosdaq_flows))
                w[-1]["지수선물"][wrong] = "K2I" if wrong == "asset" else "KOSPI"
                self.w.kosdaq_flows = deque(w)
                self.assertFalse(self.get("KOSDAQ")["available"])

    def test_same_thirty_second_alignment_gate(self):
        for market, rows in (("KOSPI", self.w.flows), ("KOSDAQ", self.w.kosdaq_flows)):
            rows[-1]["지수선물"]["sample_ts"] = 1969.9
            att = self.get(market)
            self.assertFalse(att["available"])
            self.assertIn("30초", att["reason"])
            self.assertIsNotNone(att["spot"])

    def test_legacy_handoff_keeps_spot_and_never_invents_kosdaq_futures(self):
        for snap in self.w.kosdaq_flows:
            snap.pop("지수선물")
            snap.pop("프로그램")
        att = self.get("KOSDAQ")
        self.assertFalse(att["available"])
        self.assertEqual(att["spot"]["외국인"], -100)
        self.assertIsNone(att["futures"])

    def test_new_exact_product_not_mixed_with_old_kospi_series(self):
        old = snapshot(995, "KOSPI")
        old["선물"] = old.pop("지수선물")
        self.w.flows[0] = old
        self.assertFalse(self.get("KOSPI")["available"])

    def test_program_eight_second_and_one_percent_gates_both_markets(self):
        for rows, market in ((self.w.flows, "KOSPI"), (self.w.kosdaq_flows, "KOSDAQ")):
            for snap in rows:
                snap["프로그램"]["source_time_verified"] = True
            self.assertTrue(self.get(market)["program_quality"])
            rows[-1]["프로그램"]["표본시차초"] = 8.1
            self.assertFalse(self.get(market)["program_quality"])
            rows[-1]["프로그램"]["표본시차초"] = 3
            rows[-1]["프로그램"]["전체"] -= 2
            self.assertFalse(self.get(market)["program_quality"])

    def test_missing_and_zero_are_distinct_in_render(self):
        self.w.kosdaq_flows[-1]["프로그램"] = None
        text = "\n".join(watch.market_attribution_lines(self.get("KOSDAQ"), "KOSDAQ"))
        self.assertIn("프로그램 전체·차익·비차익: 확인 보류", text)
        self.assertNotIn("+0억원", text)

    def test_same_sample_cannot_establish_event_flow(self):
        self.w.kosdaq_flows = deque([snapshot(995, "KOSDAQ")])
        att = self.w._kosdaq_attribution(1000, 1001)
        self.assertFalse(att["available"])
        self.assertIn("표본 동일", att["reason"])

    def test_crash_fields_do_not_change_kospi_surge_scale(self):
        rows = [snapshot(1000, "KOSPI"), snapshot(1300, "KOSPI", True)]
        for row in rows:
            row["선물"] = {"sample_ts": row["ts"], "외국인": 0, "기관": 0, "개인": 0}
        self.assertEqual(watch._flow_surge_channel_pair(rows, "선물", 1305)["deltas"]["외국인"], 0)
        self.assertEqual(rows[-1]["지수선물"]["외국인"], -100)


if __name__ == "__main__":
    unittest.main()

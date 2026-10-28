"""Offline fixtures only: never contact LS or Telegram."""
import asyncio
import datetime as dt
import hashlib
import json
import os
import sys
import types
import re
import textwrap
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import kospi_shock_episode_watch as watcher
from kosdaq_surge_industries import KST, industry_buy_context, industry_context_lines
from kospi_shock_enrichment import direct_industry_interval


OPEN = dt.datetime(2026, 10, 14, 9, tzinfo=KST).timestamp()
START = OPEN + 74 * 60
END = START + 300
ACTORS = {"개인": "0008", "외국인": "0017", "기관": "0018"}


def tick(code, name, source_point, value, actor="개인", **changes):
    row = {"ts": source_point, "received_ts": source_point, "source_ts": source_point,
           "source_time": dt.datetime.fromtimestamp(source_point, KST).strftime("%H%M%S") + "00",
           "upcode": code, "industry": name, "investor": actor,
           "investor_code": ACTORS[actor], "msval": value, "ex_upcode": "U" + code}
    row.update(changes)
    return row


def pair(code, name, before, after, actor="개인", start=START, end=END):
    return [tick(code, name, start, before, actor), tick(code, name, end, after, actor)]


def coverage(items, ts=OPEN - 100):
    return {"record_type": "subscription_coverage", "source_tr": "UBM", "market": "KOSDAQ",
            "ts": ts, "expected": [{"code": c, "name": n} for c, n in items]}


def native(code="319", name="화학", before=0, after=5, received=END + 30):
    rows = []
    for point, value in [(START, before), (END, after)]:
        stamp = dt.datetime.fromtimestamp(point, KST).strftime("%Y%m%d%H%M%S")
        rows.append({"datetime": stamp, "date": stamp[:8], "time": stamp[8:],
                     "indmsamt": value, "formsamt": -value, "sysmsamt": 0})
    return {"record_type": "industry_history_snapshot", "source_tr": "t1621", "market": "KOSDAQ",
            "upcode": code, "industry": name, "received_ts": received, "status": "success",
            "request": {"t1621InBlock": {"upcode": code, "nmin": 1, "cnt": 10,
                                         "bgubun": "0", "exchgubun": "U"}},
            "response": {"t1621OutBlock": {"indcode": "0008", "forcode": "0017", "syscode": "0018",
                                            "ex_upcode": "U" + code}, "t1621OutBlock1": rows}}


class IndustryFixture:
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "industry.jsonl"

    def load(self, rows, actor="개인", **kwargs):
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return industry_buy_context(START, END, actor, path=self.path, session_open_ts=OPEN, **kwargs)


class IndustryContextTests(IndustryFixture, unittest.TestCase):
    def test_rank_delta_not_cumulative_and_limit_three(self):
        rows = (pair("319", "화학", 10000, 10002) + pair("320", "제약", -100, -60)
                + pair("321", "비금속", 0, 30) + pair("322", "금속", 100, 120)
                + pair("323", "기계", 0, -2) + pair("324", "전기전자", 0, 0))
        result = self.load(rows)
        self.assertEqual([x["code"] for x in result["top"]], ["320", "321", "322"])
        self.assertEqual([x["delta_raw"] for x in result["top"]], [40, 30, 20])
        self.assertEqual(result["rows"][-1]["delta_raw"], -2)

    def test_same_actor_only(self):
        result = self.load(pair("319", "화학", 0, 5) + pair("320", "제약", 0, 99999, "외국인"))
        self.assertEqual([x["code"] for x in result["top"]], ["319"])
        self.assertTrue(all(x["investor"] == "개인" for x in result["rows"]))

    def test_investor_code_contradiction_is_excluded(self):
        rows = pair("319", "화학", 0, 5)
        rows[-1]["investor_code"] = "0017"
        self.assertFalse(self.load(rows)["available"])

    def test_kospi_and_krx_only_and_program_are_excluded(self):
        rows = pair("013", "전기전자", 0, 99999) + pair("319", "화학", 0, 5)
        rows += pair("320", "제약", 0, 99999)
        rows[-2]["ex_upcode"] = rows[-1]["ex_upcode"] = "K320"
        rows += pair("321", "비금속", 0, 99999)
        rows[-2]["source_tr"] = rows[-1]["source_tr"] = "UPM"
        self.assertEqual([x["code"] for x in self.load(rows)["top"]], ["319"])

    def test_aggregate_indices_are_not_industries(self):
        rows = pair("301", "코스닥", 0, 9999) + pair("303", "제조업", 0, 9999)
        rows += pair("315", "코스닥150", 0, 9999) + pair("319", "화학", 0, 5)
        self.assertEqual([x["code"] for x in self.load(rows)["top"]], ["319"])

    def test_future_receipt_with_old_clock_cannot_backfill_boundary(self):
        rows = pair("319", "화학", 0, 5)
        rows += [tick("319", "화학", END, 900, received_ts=END + 1, ts=END + 1)]
        self.assertEqual(self.load(rows)["top"][0]["delta_raw"], 5)

    def test_future_source_clock_cannot_contribute(self):
        rows = pair("319", "화학", 0, 5)
        rows[-1].update(source_time="10190100", source_ts=END + 1)
        self.assertFalse(self.load(rows)["available"])

    def test_stale_source_is_not_fresh_by_heartbeat(self):
        rows = pair("319", "화학", 0, 5)
        rows[-1].update(source_time="10180000", source_ts=END - 60)
        self.assertFalse(self.load(rows)["available"])

    def test_missing_source_clock_never_uses_receipt_fallback(self):
        rows = pair("319", "화학", 0, 5)
        for bad in ["", "1019", "25610000", "not-a-time"]:
            with self.subTest(clock=bad):
                rows[-1]["source_time"] = bad
                self.assertFalse(self.load(rows)["available"])

    def test_saved_source_clock_must_match_raw_clock(self):
        rows = pair("319", "화학", 0, 5)
        rows[-1]["source_ts"] = END - 1
        self.assertFalse(self.load(rows)["available"])

    def test_nonfinite_missing_or_boolean_amount_is_not_zero(self):
        for bad in [float("nan"), float("inf"), None, "", True]:
            with self.subTest(value=bad):
                result = self.load(pair("319", "화학", 0, bad))
                self.assertFalse(result["available"])
                self.assertEqual(result["rows"], [])

    def test_invalid_latest_does_not_substitute_older_good_value(self):
        rows = pair("319", "화학", 0, 5, end=END - 5)
        rows.append(tick("319", "화학", END, None))
        result = self.load(rows)
        self.assertFalse(result["available"])
        self.assertEqual(result["excluded"]["invalid_latest_boundary"], 1)

    def test_latest_missing_name_is_not_replaced_by_old_name(self):
        rows = pair("319", "화학", 0, 5, end=END - 5)
        rows.append(tick("319", "", END, 9))
        self.assertFalse(self.load(rows)["available"])

    def test_latest_actor_code_conflict_is_not_replaced_by_old_value(self):
        rows = pair("319", "화학", 0, 5, end=END - 5)
        rows.append(tick("319", "화학", END, 9, investor_code="0017"))
        self.assertFalse(self.load(rows)["available"])

    def test_preconverted_units_are_never_mixed_with_raw_msval(self):
        rows = pair("319", "화학", 0, 5, end=END - 5)
        rows.append(tick("319", "화학", END, 900, source_unit="억원"))
        self.assertFalse(self.load(rows)["available"])

    def test_same_receive_timestamp_conflicting_values_are_held(self):
        rows = pair("319", "화학", 0, 5) + [tick("319", "화학", END, 6)]
        self.assertFalse(self.load(rows)["available"])

    def test_repeated_source_clock_is_allowed_only_before_boundary(self):
        rows = pair("319", "화학", 0, 5, end=END - 10)
        rows += [tick("319", "화학", END - 10, 7, received_ts=END - 2, ts=END - 2)]
        self.assertEqual(self.load(rows)["top"][0]["delta_raw"], 7)

    def test_alignment_limit_and_actual_times(self):
        result = self.load(pair("319", "화학", 0, 5, start=START - 30, end=END - 30))
        self.assertTrue(result["available"])
        self.assertEqual(result["top"][0]["start_gap_sec"], 30)
        lines = "\n".join(industry_context_lines(result, "개인", START, END))
        self.assertIn("10:13:30~10:18:30", lines)
        self.assertFalse(self.load(pair("319", "화학", 0, 5, end=END - 31))["available"])

    def test_preopen_and_cross_date_and_invalid_window_are_held(self):
        self.path.write_text("", encoding="utf-8")
        for start, end in [(OPEN - 1, OPEN + 299), (START, START + 299),
                           (START, START + 331), (START, START + 86400),
                           (float("nan"), END)]:
            with self.subTest(window=(start, end)):
                self.assertFalse(industry_buy_context(start, end, "개인", path=self.path,
                                                     session_open_ts=OPEN)["available"])
        self.assertFalse(industry_buy_context(START, END, "개인", path=self.path)["available"])

    def test_fewer_than_three_positive_industries_and_no_positive(self):
        result = self.load(pair("319", "화학", 0, 5) + pair("320", "제약", 0, -5))
        self.assertEqual(len(result["top"]), 1)
        self.assertIn("상위 1개", "\n".join(industry_context_lines(result, "개인", START, END)))
        result = self.load(pair("319", "화학", 0, 0))
        self.assertFalse(result["available"])
        self.assertIn("순매수 증가 없음", result["reason"])

    def test_unknown_unit_is_never_converted_to_eok(self):
        result = self.load(pair("319", "화학", 0, 100))
        text = "\n".join(industry_context_lines(result, "개인", START, END))
        self.assertFalse(result["unit_verified"])
        self.assertIsNone(result["display_unit"])
        self.assertIn("금액: 원자료 단위 미확인으로 표시 보류", text)
        self.assertNotIn("억원", text)
        self.assertNotIn("100", text)

    def test_partial_coverage_never_claims_whole_market_rank(self):
        rows = [coverage([("319", "화학"), ("320", "제약")])] + pair("319", "화학", 0, 5)
        result = self.load(rows)
        self.assertEqual(result["expected_industries"], 2)
        self.assertFalse(result["coverage_complete"])
        text = "\n".join(industry_context_lines(result, "개인", START, END))
        self.assertIn("확인 1개 / 수집 대상 2개", text)
        self.assertIn("전체 업종 순위 확정 보류", text)

    def test_master_coverage_and_tie_break_are_deterministic(self):
        rows = [coverage([("319", "화학"), ("320", "제약")])]
        rows += pair("320", "제약", 0, 5) + pair("319", "화학", 0, 5)
        result = self.load(rows)
        self.assertTrue(result["coverage_complete"])
        self.assertEqual([x["code"] for x in result["top"]], ["319", "320"])

    def test_corrupt_complete_record_prevents_complete_coverage(self):
        self.load([coverage([("319", "화학")])] + pair("319", "화학", 0, 5))
        with self.path.open("ab") as fp:
            fp.write(b"not-json\n")
        result = industry_buy_context(START, END, "개인", path=self.path, session_open_ts=OPEN)
        self.assertTrue(result["available"])
        self.assertFalse(result["coverage_complete"])

    def test_incomplete_append_tail_is_excluded_and_journal_hash_preserved(self):
        self.load(pair("319", "화학", 0, 5))
        with self.path.open("ab") as fp:
            fp.write(b'{"upcode":')
        result = industry_buy_context(START, END, "개인", path=self.path, session_open_ts=OPEN)
        self.assertTrue(result["available"])
        self.assertEqual(result["excluded"]["incomplete_tail"], 1)
        self.assertEqual(result["journal_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_html_escaping_and_scope_mismatch(self):
        result = self.load(pair("319", "화학<&>", 0, 5))
        text = "\n".join(industry_context_lines(result, "개인", START, END))
        self.assertIn("화학&lt;&amp;&gt;", text)
        self.assertNotIn("화학<&>", text)
        for actor, start in [("외국인", START), ("개인", START + 1)]:
            self.assertIn("확인 보류", industry_context_lines(result, actor, start, END)[0])

    def test_missing_file_holds_only_industry_section(self):
        result = industry_buy_context(START, END, "개인", path=self.path, session_open_ts=OPEN)
        self.assertFalse(result["available"])
        self.assertIn("자료 없음", result["reason"])

    def test_metadata_does_not_change_existing_crash_parser(self):
        rows = pair("319", "화학", 20, 5)
        self.load(rows)
        before = direct_industry_interval(START, END, "개인", self.path, market="KOSDAQ")
        self.load([coverage([("319", "화학")])] + rows)
        after = direct_industry_interval(START, END, "개인", self.path, market="KOSDAQ")
        self.assertEqual(before, after)


class WatchIntegrationTests(IndustryFixture, unittest.TestCase):
    # Use only the fixture file and a mocked sender. None of these tests send.
    def watch(self):
        w = watcher.Watch("unused", [], "", False)
        w.session_open_ts = OPEN
        w.session_close_ts = OPEN + 6.5 * 3600
        w.session_continuous_end_ts = w.session_close_ts - 600
        self.receipts = []
        w._record_delivery = lambda stage, mid, ep, ts, **kw: self.receipts.append((stage, mid, kw))
        for ts in (START - 20, START):
            self.market_tick(w, ts, 0)
        self.market_tick(w, END - 20, 150)
        return w

    @staticmethod
    def market_tick(w, ts, individual):
        w.kosdaq_flows.append({"ts": ts, "market": "KOSDAQ", "현물": {
            "sample_ts": ts, "외국인": 0., "기관": 0., "개인": individual,
        }})

    def test_existing_alert_has_same_actor_window_and_receipt_evidence(self):
        self.load(pair("319", "화학", 0, 30) + pair("320", "제약", 0, 20))
        w = self.watch()
        with patch.dict(os.environ, {"KOSPI_INDUSTRY_FLOW_PATH": str(self.path)}), \
                patch.object(watcher, "telegram_send", return_value=80001) as send:
            asyncio.run(w.maybe_alert_kosdaq_surge(END - 17))
            send.assert_not_called()
            self.market_tick(w, END, 163)
            asyncio.run(w.maybe_alert_kosdaq_surge(END + 3))
            send.assert_called_once()
            text = send.call_args.args[0]
            self.assertIn("+163억원", text)
            self.assertIn("개인 업종 순매수 증가 상위 2개", text)
            self.assertIn("10:14:00~10:19:00", text)
            evidence = self.receipts[0][2]["evidence"]
            self.assertEqual(evidence["industry_context"]["requested_window"], [START, END])
            self.assertEqual(evidence["industry_context"]["investor"], "개인")
            self.assertIn("market=3 upcode=301 exchgubun=U", evidence["source"])
            self.assertEqual(evidence["message_sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.market_tick(w, END + 20, 400)
            asyncio.run(w.maybe_alert_kosdaq_surge(END + 23))
            self.market_tick(w, END + 40, 500)
            asyncio.run(w.maybe_alert_kosdaq_surge(END + 43))
            send.assert_called_once()
            self.assertFalse(w.surge_sent_at)

    def test_reader_failure_preserves_confirmed_market_alert(self):
        w = self.watch()
        with patch.object(watcher, "industry_buy_context", side_effect=OSError("fixture")), \
                patch.object(watcher, "telegram_send", return_value=80002) as send:
            asyncio.run(w.maybe_alert_kosdaq_surge(END - 17))
            self.market_tick(w, END, 163)
            asyncio.run(w.maybe_alert_kosdaq_surge(END + 3))
            send.assert_called_once()
            self.assertIn("+163억원", send.call_args.args[0])
            self.assertIn("업종 수급 자료 처리 실패", send.call_args.args[0])

    def test_failed_send_does_not_claim_delivery_or_advance_cooldown(self):
        w = self.watch()
        with patch.object(watcher, "industry_buy_context", return_value=None), \
                patch.object(watcher, "telegram_send", side_effect=RuntimeError("fixture")):
            asyncio.run(w.maybe_alert_kosdaq_surge(END - 17))
            self.market_tick(w, END, 163)
            with self.assertRaises(RuntimeError):
                asyncio.run(w.maybe_alert_kosdaq_surge(END + 3))
        self.assertFalse(self.receipts)
        self.assertFalse(w.kosdaq_surge_sent_at)
        self.assertNotIn("last_kosdaq_surge_alert", w.raw)


class NativeHistoryTests(IndustryFixture, unittest.TestCase):
    def test_actual_ls_date_alias_uses_explicit_response_date_time(self):
        row = native()
        for point in row["response"]["t1621OutBlock1"]:
            point["datetime"] = point["date"]
        self.assertTrue(self.load([row])["available"])

    def test_conflicting_date_alias_is_not_treated_as_date_time(self):
        row = native()
        row["response"]["t1621OutBlock1"][-1]["datetime"] = "20261013"
        self.assertFalse(self.load([row])["available"])

    def test_dated_history_retrieved_after_boundary_is_accepted(self):
        result = self.load([coverage([("319", "화학")]), native()])
        self.assertEqual(result["source_tr"], "t1621")
        self.assertTrue(result["available"])
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["top"][0]["delta_raw"], 5)
        self.assertGreater(result["top"][0]["end"]["received_ts"], END)

    def test_native_and_ubm_units_are_not_mixed(self):
        result = self.load(pair("320", "제약", 0, 99999) + [native()])
        self.assertEqual([x["code"] for x in result["rows"]], ["319"])
        self.assertFalse(result["unit_verified"])
        self.assertNotIn("억원", "\n".join(industry_context_lines(result, "개인", START, END)))

    def test_size_company_and_manufacturing_aggregates_are_excluded(self):
        rows = [native()] + [native(c, n, after=99999) for c, n in
                              [("306", "제조"), ("340", "KOSDAQ MID 300"), ("341", "KOSDAQ SMALL"),
                               ("342", "우량기업"), ("343", "벤처기업"), ("344", "중견기업"),
                               ("345", "기술성장기업"), ("346", "KOSDAQ 글로벌")]]
        self.assertEqual([x["code"] for x in self.load(rows)["top"]], ["319"])

    def test_failed_latest_response_does_not_use_old_history_or_ubm(self):
        failed = native(received=END + 40)
        failed.update(status="request_failed", response={})
        result = self.load([native(), failed] + pair("319", "화학", 0, 99999))
        self.assertFalse(result["available"])
        self.assertEqual(result["excluded"]["invalid_history_response"], 1)

    def test_exchange_and_investor_echo_must_match(self):
        for key, value in [("ex_upcode", "K319"), ("indcode", "0017")]:
            with self.subTest(field=key):
                row = native(); row["response"]["t1621OutBlock"][key] = value
                self.assertFalse(self.load([row])["available"])

    def test_native_timestamp_does_not_infer_request_day(self):
        row = native()
        for point in row["response"]["t1621OutBlock1"]:
            point.pop("datetime"); point.pop("date")
        self.assertFalse(self.load([row])["available"])

    def test_contradictory_date_time_is_held(self):
        row = native()
        row["response"]["t1621OutBlock1"][-1]["time"] = "102000"
        self.assertFalse(self.load([row])["available"])

    def test_missing_latest_amount_does_not_replace_with_prior_value(self):
        row = native()
        row["response"]["t1621OutBlock1"][-1]["indmsamt"] = None
        point = END - 20
        stamp = dt.datetime.fromtimestamp(point, KST).strftime("%Y%m%d%H%M%S")
        row["response"]["t1621OutBlock1"].append({"datetime": stamp, "indmsamt": 5})
        self.assertFalse(self.load([row])["available"])

    def test_dated_history_covers_same_actor_with_half_minute_alignment(self):
        row = native()
        for item in row["response"]["t1621OutBlock1"]:
            ts = dt.datetime.strptime(item["datetime"], "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp() - 30
            item["datetime"] = dt.datetime.fromtimestamp(ts, KST).strftime("%Y%m%d%H%M%S")
            item["date"], item["time"] = item["datetime"][:8], item["datetime"][8:]
        result = self.load([row], actor="외국인")
        self.assertEqual(result["rows"][0]["delta_raw"], -5)
        self.assertFalse(result["available"])
        self.assertEqual(result["rows"][0]["end_gap_sec"], 30)


class KOSPIIndustryTests(IndustryFixture, unittest.TestCase):
    def load(self, rows, actor="외국인", **kwargs):
        return super().load(rows, actor, market="KOSPI", **kwargs)

    @staticmethod
    def history(code="013", name="전기전자", before=500, after=530):
        row = native(code, name, before, after)
        row["market"] = "KOSPI"
        for point, value in zip(row["response"]["t1621OutBlock1"], (before, after)):
            point.update(formsamt=value, indmsamt=-value, sysmsamt=value * 2)
        return row

    @staticmethod
    def master(items):
        row = coverage(items)
        row["market"] = "KOSPI"
        return row

    def test_same_market_actor_and_interval_cumulative_difference(self):
        rows = [self.master([("013", "전기전자"), ("018", "건설")]),
                self.history(), self.history("018", "건설", 10000, 10010), native()]
        result = self.load(rows)
        self.assertEqual([(x["name"], x["delta_raw"]) for x in result["top"]],
                         [("전기전자", 30), ("건설", 10)])
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["source_amount_field"], "formsamt")
        self.assertFalse(result["unit_verified"])
        self.assertIsNone(result["display_unit"])
        institution = self.load(rows, "기관")
        self.assertEqual(institution["top"][0]["delta_raw"], 60)
        self.assertEqual(institution["source_amount_field"], "sysmsamt")
        self.assertFalse(self.load(rows, "개인")["top"])

    def test_kosdaq_history_cannot_hide_valid_kospi_ubm(self):
        result = self.load(pair("013", "전기전자", 10, 20, "외국인") + [native()])
        self.assertEqual(result["source_tr"], "UBM")
        self.assertEqual(result["top"][0]["delta_raw"], 10)

    def test_index_manufacturing_and_other_market_never_rank(self):
        rows = [self.history(c, n, 0, 100000) for c, n in
                [("001", "종합"), ("002", "대형주"), ("026", "제조업"),
                 ("306", "제조"), ("319", "화학"), ("901", "기타지수")]]
        result = self.load(rows + [self.history()])
        self.assertEqual([x["code"] for x in result["top"]], ["013"])

    def test_partial_rank_and_opposite_market_render_guard(self):
        result = self.load([self.master([("013", "전기전자"), ("018", "건설")]), self.history()])
        lines = "\n".join(industry_context_lines(result, "외국인", START, END, market="KOSPI"))
        self.assertIn("확인 1개 / 수집 대상 2개", lines)
        self.assertIn("전체 업종 순위 확정 보류", lines)
        self.assertIn("금액: 원자료 단위 미확인", lines)
        self.assertNotIn("전기전자", "\n".join(industry_context_lines(result, "외국인", START, END)))
        self.assertNotIn("전기전자", "\n".join(industry_context_lines(result, "기관", START, END, market="KOSPI")))
        self.assertNotIn("전기전자", "\n".join(industry_context_lines(result, "외국인", START + 1, END, market="KOSPI")))

    def test_latest_failure_or_converted_amount_does_not_fallback(self):
        old = self.history()
        for changes in ({"status": "request_failed"}, {"source_unit": "억원"}):
            latest = self.history()
            latest.update(received_ts=END + 31, **changes)
            result = self.load([old, latest] + pair("013", "전기전자", 0, 99999, "외국인"))
            self.assertFalse(result["available"])
            self.assertEqual(result["excluded"]["invalid_history_response"], 1)

    def test_kospi_same_boundary_skew_and_negative_changes(self):
        row = self.history()
        for point in row["response"]["t1621OutBlock1"]:
            stamp = dt.datetime.strptime(point["datetime"], "%Y%m%d%H%M%S") - dt.timedelta(seconds=31)
            point.update(time=stamp.strftime("%H%M%S"), datetime=stamp.strftime("%Y%m%d%H%M%S"))
        self.assertFalse(self.load([row])["available"])
        self.assertFalse(self.load([self.history(before=1000, after=999)])["available"])

    def test_kospi_renderer_uses_spot_context_and_keeps_futures_separate(self):
        w = watcher.Watch("fixture", [], "", False)
        result = self.load([self.history()])
        cand = {"actor": "외국인", "mode": "현물·선물 동시", "spot": 550,
                "futures": 720, "confidence": "중간", "spot_window": (START, END),
                "futures_window": (START + 10, END + 10)}
        text = w.build_flow_surge_alert(cand, END + 5, result)
        self.assertIn("전기전자", text)
        self.assertIn("선물·프로그램의 업종별 자금 배분을 뜻하지", text)
        self.assertIn("KOSPI200 선물 +720억원", text)
        cand["spot"] = -10
        text = w.build_flow_surge_alert(cand, END + 5, result)
        self.assertNotIn("전기전자", text)
        self.assertIn("현물 순매수 증가 없음", text)

    def test_confirmed_kospi_alert_loads_exact_window_and_preserves_receipt(self):
        w = watcher.Watch("fixture", [], "", False)
        w.session_open_ts, w.session_close_ts = OPEN, END + 3600
        w.session_continuous_end_ts = END + 1800
        w.flows.append({"ts": END + 20})
        w.surge_pending["외국인"] = {"sample_ts": END, "seen_at": END, "end_values": {"spot": 999}}
        cand = {"actor": "외국인", "mode": "현물 중심", "spot": 1001, "futures": -20,
                "confidence": "단독 신호", "spot_window": (START + 20, END + 20),
                "futures_window": (START + 10, END + 10), "sample_ts": END + 20,
                "spot_end_cumulative": 1001}
        result = self.load([self.history()])
        result["requested_window"] = list(cand["spot_window"])
        receipts = []
        w._record_delivery = lambda *a, **kw: receipts.append((a, kw))
        with patch.object(watcher, "flow_surge_candidates", return_value=[cand]), \
                patch.object(watcher, "industry_buy_context", return_value=result) as load_context, \
                patch.object(watcher, "telegram_send", return_value=987) as send:
            asyncio.run(w.maybe_alert_flow_surge(END + 25))
            load_context.assert_called_once_with(*cand["spot_window"], "외국인", session_open_ts=OPEN, market="KOSPI")
            self.assertEqual(w.msg_ids, [987])
            evidence = receipts[0][1]["evidence"]
            self.assertEqual(evidence["spot_window"], cand["spot_window"])
            self.assertEqual(evidence["industry_context"], result)
            self.assertEqual(evidence["message_sha256"], hashlib.sha256(send.call_args.args[0].encode()).hexdigest())
            asyncio.run(w.maybe_alert_flow_surge(END + 26))
            self.assertEqual(send.call_count, 1)


class MarketSurgeParityTests(IndustryFixture, unittest.TestCase):
    """A change in one market must satisfy the same source/display safeguards."""
    @staticmethod
    def watch():
        w = watcher.Watch("fixture", [], "", False)
        w.session_open_ts, w.session_close_ts = OPEN, END + 3600
        w.session_continuous_end_ts = END + 1800
        w._record_delivery = lambda *a, **kw: None
        return w

    @staticmethod
    def add_tick(w, market, point, value, actor="외국인"):
        row = {"ts": point, "market": market, "현물": {
            "sample_ts": point, **{who: value if who == actor else 0 for who in ACTORS}}}
        (w.flows if market == "KOSPI" else w.kosdaq_flows).append(row)

    @staticmethod
    def evaluate(w, market, point):
        callback = w.maybe_alert_flow_surge if market == "KOSPI" else w.maybe_alert_kosdaq_surge
        asyncio.run(callback(point))

    def render(self, w, market, actor, context, delta=1000):
        if market == "KOSPI":
            cand = {"actor": actor, "mode": "현물 중심", "confidence": "단독 신호",
                    "spot": delta, "futures": None, "spot_window": (START, END)}
            return w.build_flow_surge_alert(cand, END + 3, context)
        return w.build_kosdaq_flow_surge_alert(actor, delta, {"start_ts": START, "end_ts": END}, END + 3, context)

    def context(self, market, actor):
        code, name = ("013", "전기전자") if market == "KOSPI" else ("319", "화학")
        master = coverage([(code, name), ("018", "건설") if market == "KOSPI" else ("320", "제약")])
        master["market"] = market
        return self.load([master] + pair(code, name, -100, -70, actor), actor, market=market)

    def test_all_six_market_investor_bodies_share_field_order_and_partial_limits(self):
        for actor in ACTORS:
            bodies = []
            for market in ("KOSPI", "KOSDAQ"):
                with self.subTest(market=market, actor=actor):
                    context = self.context(market, actor)
                    text = self.render(self.watch(), market, actor, context)
                    self.assertIn(f"{actor} 업종 순매수 증가 상위 1개", text)
                    self.assertIn("확인 1개 / 수집 대상 2개 · 전체 업종 순위 확정 보류", text)
                    self.assertIn("업종 금액: 원자료 단위 미확인으로 표시 보류", text)
                    self.assertIn("누적 순매수의 5분 변화량", text)
                    self.assertIn("두 차례 연속 확인", text)
                    self.assertIn("주가 상승 확정값이 아닙니다", text)
                    self.assertIn("현물 10:14:00~10:19:00", text)
                    # Market-specific thresholds/channels remain explicit extras.
                    common = [line for line in text.splitlines() if not any(key in line for key in
                              ("감지 기준:", "프로그램:", "KOSPI200 선물", "프로그램 교차검증:", "href="))]
                    normalized = "\n".join(common).replace("코스피", "시장").replace("코스닥", "시장")
                    normalized = normalized.replace("전기전자", "업종").replace("화학", "업종")
                    bodies.append(normalized)
            self.assertEqual(bodies[0], bodies[1])

    def test_wrong_market_actor_or_window_is_held_for_both_markets(self):
        for market in ("KOSPI", "KOSDAQ"):
            original = self.context(market, "외국인")
            for change in ({"market": "other"}, {"investor": "기관"}, {"requested_window": [START - 1, END]}):
                with self.subTest(market=market, change=change):
                    text = self.render(self.watch(), market, "외국인", {**original, **change})
                    self.assertIn("같은 투자자·구간의 자료 없음", text)
                    self.assertNotIn("순매수 증가 상위", text)

    def test_no_positive_spot_does_not_borrow_industry_ranks(self):
        for market in ("KOSPI", "KOSDAQ"):
            for delta in (-10, 0, None):
                text = self.render(self.watch(), market, "외국인", self.context(market, "외국인"), delta)
                self.assertIn("현물 순매수 증가 없음 또는 표본 부족", text)
                self.assertNotIn("순매수 증가 상위", text)

    def test_industry_reader_exception_is_identical_for_both_markets(self):
        for market in ("KOSPI", "KOSDAQ"):
            w = self.watch()
            with patch.object(watcher, "industry_buy_context", side_effect=OSError("fixture")) as load:
                context = asyncio.run(w._surge_industry_context(market, "기관", 1000, (START, END), OPEN))
            load.assert_called_once_with(START, END, "기관", session_open_ts=OPEN, market=market)
            text = self.render(w, market, "기관", context)
            self.assertIn("업종 수급 자료 처리 실패", text)
            self.assertIn("+1,000억원", text)
            self.assertIn("업종 확인 범위: 확인 0개", text)

    def test_new_clock_same_cumulative_cannot_confirm_either_market(self):
        for market in ("KOSPI", "KOSDAQ"):
            for actor in ACTORS:
                with self.subTest(market=market, actor=actor):
                    w = self.watch()
                    with patch.object(watcher, "telegram_send", return_value=100) as send, \
                            patch.object(watcher, "industry_buy_context", return_value=None):
                        for ts, value in ((START - 20, 0), (START, 0), (END - 20, 1000), (END, 1000)):
                            self.add_tick(w, market, ts, value, actor)
                            self.evaluate(w, market, ts + 3)
                        send.assert_not_called()
                        self.add_tick(w, market, END + 20, 1050, actor)
                        self.evaluate(w, market, END + 23)
                        send.assert_called_once()
                        for step, value in ((40, 1100), (60, 1200)):
                            self.add_tick(w, market, END + step, value, actor)
                            self.evaluate(w, market, END + step + 3)
                        send.assert_called_once()  # shared twenty-minute cooldown

    def test_cumulative_reversal_requires_a_fresh_confirmation(self):
        for market in ("KOSPI", "KOSDAQ"):
            w = self.watch()
            with patch.object(watcher, "telegram_send", return_value=100) as send, \
                    patch.object(watcher, "industry_buy_context", return_value=None):
                for ts, value in ((START - 20, 0), (START, 0), (END - 20, 1200), (END, 1100)):
                    self.add_tick(w, market, ts, value)
                    self.evaluate(w, market, ts + 3)
                send.assert_not_called()
                self.add_tick(w, market, END + 20, 1150)
                self.evaluate(w, market, END + 23)
                send.assert_called_once()

    def test_changed_trigger_channels_and_declining_combined_channel_do_not_confirm(self):
        pending = {}
        confirm = watcher.confirm_flow_surge
        self.assertFalse(confirm(pending, "외국인", END, END + 3, {"spot": 1200}))
        self.assertFalse(confirm(pending, "외국인", END + 20, END + 23, {"futures": 1500}))
        self.assertFalse(confirm(pending, "외국인", END + 40, END + 43, {"spot": 1200, "futures": 1500}))
        self.assertFalse(confirm(pending, "외국인", END + 60, END + 63, {"spot": 1199, "futures": 1600}))
        self.assertTrue(confirm(pending, "외국인", END + 80, END + 83, {"spot": 1200, "futures": 1600}))

    def test_legacy_kospi_pending_without_values_does_not_confirm(self):
        pending = {"외국인": {"sample_ts": END, "seen_at": END + 3}}
        self.assertFalse(watcher.confirm_flow_surge(pending, "외국인", END + 20, END + 23, {"spot": 1000}))
        self.assertTrue(watcher.confirm_flow_surge(pending, "외국인", END + 40, END + 43, {"spot": 1050}))

    def test_legacy_kosdaq_endpoint_and_new_handoff_values_are_preserved(self):
        w = self.watch()
        w.surge_pending["외국인"] = {"sample_ts": END, "seen_at": END + 3,
                                     "end_values": {"spot": 1000, "futures": 1500}}
        w.kosdaq_surge_pending["기관"] = {"sample_ts": END, "seen_at": END + 3, "end_value": 160}
        path = Path(self.directory.name) / "handoff.json"
        w.save_handoff(path)
        restored = self.watch()
        restored.load_handoff(path)
        self.assertEqual(restored.surge_pending, w.surge_pending)
        self.assertEqual(restored.kosdaq_surge_pending["기관"]["end_value"], 160)
        self.assertTrue(watcher.confirm_flow_surge(restored.kosdaq_surge_pending, "기관", END + 20,
                                                  END + 23, {"spot": 170}))

    def test_sender_failure_does_not_advance_either_market(self):
        for market in ("KOSPI", "KOSDAQ"):
            w = self.watch()
            receipts = []
            w._record_delivery = lambda *a, **kw: receipts.append((a, kw))
            with patch.object(watcher, "telegram_send", side_effect=RuntimeError("fixture")), \
                    patch.object(watcher, "industry_buy_context", return_value=None):
                for ts, value in ((START - 20, 0), (START, 0), (END - 20, 1000)):
                    self.add_tick(w, market, ts, value)
                    self.evaluate(w, market, ts + 3)
                self.add_tick(w, market, END, 1050)
                with self.assertRaises(RuntimeError): self.evaluate(w, market, END + 3)
            self.assertFalse(w.surge_sent_at)
            self.assertFalse(w.kosdaq_surge_sent_at)
            self.assertFalse(w.msg_ids)
            self.assertFalse(receipts)

    def test_same_delivery_contract_and_actual_body_digest_for_both_markets(self):
        for market in ("KOSPI", "KOSDAQ"):
            w = self.watch()
            receipts = []
            w._record_delivery = lambda *a, **kw: receipts.append((a, kw))
            with patch.object(watcher, "telegram_send", return_value=123) as send, \
                    patch.object(watcher, "industry_buy_context", return_value=None):
                for ts, value in ((START - 20, 0), (START, 0), (END - 20, 1000), (END, 1050)):
                    self.add_tick(w, market, ts, value)
                    self.evaluate(w, market, ts + 3)
            evidence = receipts[0][1]["evidence"]
            self.assertEqual(evidence["market"], market)
            self.assertEqual(evidence["actor"], "외국인")
            self.assertEqual(evidence["alert_contract"], watcher.FLOW_SURGE_ALERT_CONTRACT)
            self.assertEqual(evidence["display_unit"], "억원")
            self.assertEqual(evidence["spot_start_cumulative"], 0)
            self.assertEqual(evidence["spot_end_cumulative"], 1050)
            self.assertEqual(evidence["spot_delta_eok"], 1050)
            self.assertEqual(evidence["confirmation_first"]["end_values"], {"spot": 1000})
            self.assertEqual(evidence["confirmation_second"]["end_values"], {"spot": 1050})
            self.assertEqual(list(evidence["spot_window"]), [START, END])
            self.assertEqual(evidence["message_sha256"], hashlib.sha256(send.call_args.args[0].encode()).hexdigest())


class CollectorHistoryTests(unittest.TestCase):
    def exercise(self, fail=False, dual=False):
        class Signal:
            def connect(self, fn): self.fn = fn

        class API:
            def __init__(self): self.on_realtime = Signal(); self.last_message = "fixture"
            async def login(self, *args): return True
            async def request(self, tr, query):
                if tr == "t8424":
                    rows = [{"upcode": "319", "hname": "화학"}]
                    if dual:
                        rows += [{"upcode": "013", "hname": "전기전자"}]
                    return types.SimpleNamespace(body={"t8424OutBlock": rows})
                if fail: raise RuntimeError("fixture")
                return types.SimpleNamespace(body=native(query["t1621InBlock"]["upcode"])["response"])
            async def add_realtime(self, tr, key):
                self.on_realtime.fn(self, tr, key, {"upcode": "319", "tjjcode": "0008", "msval": 1,
                                                  "msvol": 1, "tjjtime": dt.datetime.now(KST).strftime("%H%M%S"),
                                                  "ex_upcode": "U319"})
                return True
            async def remove_realtime(self, *args): pass
            async def close(self): pass

        with patch.dict(sys.modules, {"ebest": types.SimpleNamespace(OpenApi=API)}):
            import kospi_unified_industry_collector as collector
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(collector, "ebest", types.SimpleNamespace(OpenApi=API)), \
                patch.dict(os.environ, {"LS_OPENAPI_APP_KEY": "fixture", "LS_OPENAPI_APP_SECRET": "fixture"}):
            p = Path(directory) / "journal.jsonl"
            asyncio.run(collector.main(p, dt.time(15, 32), test_seconds=3 if dual else 1))
            return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]

    def test_sampler_preserves_ubm_and_writes_dated_history(self):
        rows = self.exercise()
        self.assertTrue(any(x.get("investor") == "개인" for x in rows))
        self.assertTrue(any(x.get("record_type") == "industry_history_snapshot" and x["status"] == "success" for x in rows))

    def test_sampler_failure_is_recorded_without_stopping_ubm(self):
        rows = self.exercise(fail=True)
        self.assertTrue(any(x.get("investor") == "개인" for x in rows))
        self.assertTrue(any(x.get("status") == "request_failed" and x["error_type"] == "RuntimeError" for x in rows))

    def test_sampler_retains_two_separate_market_populations_and_responses(self):
        rows = self.exercise(dual=True)
        masters = {x["market"]: x for x in rows if x.get("record_type") == "subscription_coverage"}
        self.assertEqual([x["code"] for x in masters["KOSPI"]["expected"]], ["013"])
        self.assertEqual([x["code"] for x in masters["KOSDAQ"]["expected"]], ["319"])
        snapshots = [x for x in rows if x.get("record_type") == "industry_history_snapshot"]
        self.assertEqual({(x["market"], x["upcode"]) for x in snapshots}, {("KOSPI", "013"), ("KOSDAQ", "319")})
        for row in snapshots:
            self.assertEqual(row["response"]["t1621OutBlock"]["ex_upcode"], "U" + row["upcode"])
        from kosdaq_surge_industries import _industry
        self.assertTrue(_industry("327", "기타제조"))


class ProductionAuditTests(unittest.TestCase):
    def test_actual_morning_and_afternoon_checks_distinguish_expansion_points(self):
        workflow = (Path(__file__).parent.parent / ".github/workflows/kospi-derivatives-flow-ls-realtime.yml").read_text(encoding="utf-8")
        scripts = [textwrap.dedent(x) for x in re.findall(r"          python - <<'PY'\n(.*?)          PY", workflow, re.S)
                   if "duplicate episode stage" in x]
        self.assertEqual(len(scripts), 2)
        row = {"stage": "kosdaq_shock_expand", "market": "KOSDAQ", "actor": "",
               "event_start_ts": START - 60, "event_low_ts": END, "message_id": 101}
        good = [row, {**row, "event_low_ts": END + 250, "message_id": 102}]
        bad_point = [row, {**row, "message_id": 102}]
        bad_receipt = [row, {**row, "event_low_ts": END + 250}]
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                Path("out").mkdir()
                Path("out/kospi_shock_episode_raw.json").write_text(json.dumps({"last_price_snapshot": {"KOSPI": {"price": 1}}}), encoding="utf-8")
                Path("out/kospi_shock_handoff.json").write_text(json.dumps({"date": dt.datetime.now(KST).strftime("%Y-%m-%d")}), encoding="utf-8")
                for script in scripts:
                    for rows, rejected in [(good, False), (bad_point, True), (bad_receipt, True)]:
                        Path("out/kospi_shock_delivery_log.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
                        if rejected:
                            with self.assertRaises(AssertionError): exec(script, {})
                        else:
                            exec(script, {})
            finally:
                os.chdir(original)


class KOSDAQPrealertTierTests(unittest.TestCase):
    """Offline checks: neither LS nor Telegram is contacted."""

    def new_watch(self):
        w = watcher.Watch("unused", [], "", False)
        w.session_open_ts = OPEN
        w.session_close_ts = OPEN + 6.5 * 3600
        w.session_continuous_end_ts = w.session_close_ts - 600
        w._surge_industry_context = AsyncMock(return_value=None)
        w._try_send_event = AsyncMock(side_effect=[81001, 81002, 81003, 81004])
        w._record_delivery = Mock()
        w._checkpoint_handoff = Mock()
        for ts in (START - 20, START, START + 20, START + 40, START + 60):
            self.add_tick(w, ts)
        return w

    @staticmethod
    def add_tick(w, ts, actor=None, value=0.0, *, bad_financial=False):
        values = {"외국인": 0.0, "기관": 0.0, "개인": 0.0,
                  "투신": 0.0, "금융투자": 0.0}
        if actor:
            values[actor] = float(value)
        source_row = {"sv_03": values["투신"],
                      "sv_01": values["금융투자"] + (1 if bad_financial else 0)}
        w.kosdaq_flows.append({"ts": ts, "market": "KOSDAQ", "현물": {
            "sample_ts": ts, "source_tr": "t1602", "unit": "억원",
            "source_row": source_row, **values,
        }})

    def process(self, w, ts, actor, value, *, bad_financial=False):
        self.add_tick(w, ts, actor, value, bad_financial=bad_financial)
        asyncio.run(w.maybe_alert_kosdaq_prealert(ts + 3))
        asyncio.run(w.maybe_alert_kosdaq_surge(ts + 3))

    def test_institution_trust_and_financial_investment_generate_prealerts(self):
        for actor in ("기관", "투신", "금융투자"):
            with self.subTest(actor=actor):
                w = self.new_watch()
                self.process(w, END - 20, actor, 110)
                w._try_send_event.assert_not_awaited()
                self.process(w, END, actor, 120)
                self.assertEqual(w._try_send_event.await_count, 1)
                stage, event, _, text = w._try_send_event.await_args.args
                self.assertEqual(stage, "kosdaq_flow_prealert")
                self.assertEqual(event["actor"], actor)
                self.assertIn("예비 경보", text)
                self.assertIn("100억원 이상", text)
                if actor in ("투신", "금융투자"):
                    self.assertIn(actor + "(기관 내)", text)
                if actor == "금융투자":
                    self.assertIn("기관과 하위 항목을 합산하거나", text)
                else:
                    self.assertIn("기관·투신을 합산하거나", text)

    def test_prealert_cooldown_does_not_hide_confirmed_alert(self):
        w = self.new_watch()
        self.process(w, END - 20, "금융투자", 110)
        self.process(w, END, "금융투자", 120)
        self.process(w, END + 20, "금융투자", 160)
        self.assertEqual(w._try_send_event.await_count, 1)
        self.process(w, END + 40, "금융투자", 170)
        self.assertEqual([call.args[0] for call in w._try_send_event.await_args_list],
                         ["kosdaq_flow_prealert", "kosdaq_flow_surge"])
        self.assertEqual(w._try_send_event.await_args_list[1].args[1]["actor"], "금융투자")
        self.assertIn("150억원 이상", w._try_send_event.await_args_list[1].args[3])

    def test_confirmed_tier_requires_two_samples_above_150(self):
        w = self.new_watch()
        self.process(w, END - 20, "기관", 120)
        self.process(w, END, "기관", 160)
        w._try_send_event.assert_not_awaited()
        self.process(w, END + 20, "기관", 170)
        self.assertEqual(w._try_send_event.await_count, 1)
        self.assertEqual(w._try_send_event.await_args.args[0], "kosdaq_flow_surge")

    def test_invalid_financial_source_is_not_a_candidate(self):
        w = self.new_watch()
        self.process(w, END - 20, "금융투자", 110, bad_financial=True)
        self.process(w, END, "금융투자", 120, bad_financial=True)
        w._try_send_event.assert_not_awaited()
        self.assertNotIn("금융투자", w.kosdaq_prealert_pending)

    def test_recent_confirmed_alert_suppresses_lower_prealert(self):
        w = self.new_watch()
        w.kosdaq_surge_sent_at["기관"] = END - 60
        self.process(w, END - 20, "기관", 110)
        self.process(w, END, "기관", 120)
        w._try_send_event.assert_not_awaited()

    def test_financial_state_survives_handoff(self):
        w = self.new_watch()
        now = watcher.time.time()
        w.kosdaq_prealert_sent_at["금융투자"] = now - 20
        w.kosdaq_surge_sent_at["금융투자"] = now - 30
        pending = {"sample_ts": now - 15, "seen_at": now - 10,
                   "end_value": 120.0, "end_values": {"spot": 120.0}}
        w.kosdaq_prealert_pending["금융투자"] = dict(pending)
        w.kosdaq_surge_pending["금융투자"] = dict(pending)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            w.save_handoff(path)
            restored = watcher.Watch("unused", [], "", False)
            restored.load_handoff(path)
        self.assertEqual(restored.kosdaq_prealert_sent_at["금융투자"], now - 20)
        self.assertEqual(restored.kosdaq_surge_sent_at["금융투자"], now - 30)
        self.assertEqual(restored.kosdaq_prealert_pending["금융투자"]["end_value"], 120.0)
        self.assertEqual(restored.kosdaq_surge_pending["금융투자"]["end_value"], 120.0)

    def test_uncertain_prealert_does_not_block_confirmed_delivery(self):
        w = watcher.Watch("unused", [], "", False)
        w._checkpoint_handoff = Mock()
        event = {"market": "KOSDAQ", "actor": "금융투자", "start_ts": START}
        with patch.object(watcher, "telegram_send",
                          side_effect=[watcher.DeliveryUncertain("offline uncertain"), 81005]), \
                patch.object(watcher.time, "time", return_value=END):
            pre = asyncio.run(w._try_send_event("kosdaq_flow_prealert", event, END, "prealert"))
            confirmed = asyncio.run(w._try_send_event("kosdaq_flow_surge", event, END + 20, "confirmed"))
        self.assertIsNone(pre)
        self.assertEqual(confirmed, 81005)
        self.assertEqual(w._surge_delivery_hold_at("KOSDAQ", "금융투자", "kosdaq_flow_prealert"), END)
        self.assertEqual(w._surge_delivery_hold_at("KOSDAQ", "금융투자"), 0.0)

    def test_unverified_financial_industry_data_is_held(self):
        w = watcher.Watch("unused", [], "", False)
        with patch.object(watcher, "industry_buy_context", side_effect=AssertionError("must not query")):
            context = asyncio.run(w._surge_industry_context(
                "KOSDAQ", "금융투자", 120.0, (START, END), OPEN))
        self.assertFalse(context["available"])
        self.assertEqual(context["requested_window"], [START, END])
        self.assertIn("금융투자 업종 원자료 확인 불가", context["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

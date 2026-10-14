"""Offline fixtures only: never contact LS or Telegram."""
import asyncio
import datetime as dt
import hashlib
import json
import os
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            self.assertIn("market=2 upcode=301 exchgubun=U", evidence["source"])
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


class CollectorHistoryTests(unittest.TestCase):
    def exercise(self, fail=False):
        class Signal:
            def connect(self, fn): self.fn = fn

        class API:
            def __init__(self): self.on_realtime = Signal(); self.last_message = "fixture"
            async def login(self, *args): return True
            async def request(self, tr, query):
                if tr == "t8424":
                    return types.SimpleNamespace(body={"t8424OutBlock": [{"upcode": "319", "hname": "화학"}]})
                if fail: raise RuntimeError("fixture")
                return types.SimpleNamespace(body=native()["response"])
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
            asyncio.run(collector.main(p, dt.time(15, 32), test_seconds=1))
            return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]

    def test_sampler_preserves_ubm_and_writes_dated_history(self):
        rows = self.exercise()
        self.assertTrue(any(x.get("investor") == "개인" for x in rows))
        self.assertTrue(any(x.get("record_type") == "industry_history_snapshot" and x["status"] == "success" for x in rows))

    def test_sampler_failure_is_recorded_without_stopping_ubm(self):
        rows = self.exercise(fail=True)
        self.assertTrue(any(x.get("investor") == "개인" for x in rows))
        self.assertTrue(any(x.get("status") == "request_failed" and x["error_type"] == "RuntimeError" for x in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Offline source/clock/scale/render regressions; no Telegram or market HTTP calls."""
import asyncio
import base64
from collections import deque
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import market_program_close as program
import kospi_shock_episode_watch as monitor

FIXTURE = json.loads((Path(__file__).parent / "test_fixtures/program_close_readback_20261016.json").read_text(encoding="utf-8"))
CLOSE = FIXTURE["close_ts"]
NOW = CLOSE + 120


def inputs(market="KOSPI"):
    case = copy.deepcopy(FIXTURE["markets"][market])
    return case["ls"], case["references"]


def receipt(body, **extra):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return {"http_status": 200, "query_started_ts": CLOSE + 1, "received_ts": CLOSE + 2,
            "raw_base64": base64.b64encode(raw).decode("ascii"),
            "raw_sha256": hashlib.sha256(raw).hexdigest(), **extra}


def sealed(market="KOSPI"):
    ls, refs = inputs(market)
    ls["transport"] = receipt(ls["response"], endpoint="/stock/program", tr_cd="t1662", request=ls["request"])
    for ref in refs.values():
        ref.update(receipt(ref["response"]))
    return {"schema": "program_close_cumulative_v1", "market": market, "close_ts": CLOSE,
            "query_started_ts": CLOSE + 1, "received_ts": CLOSE + 3, "status": "verified",
            "unit_contract": program.UNIT_CONTRACT, "ls": ls, "references": refs,
            "derived": program.derive(market, CLOSE, ls, refs)}


class ProgramClose(unittest.TestCase):
    def setUp(self):
        self.patches = [patch("requests.get", side_effect=AssertionError("network disabled")),
                        patch("requests.post", side_effect=AssertionError("network disabled")),
                        patch.object(monitor, "telegram_send", side_effect=AssertionError("send disabled"))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def derive(self, ls, refs, market="KOSPI"):
        return program.derive(market, CLOSE, ls, refs)

    def test_saved_later_readbacks_are_not_production_responses(self):
        self.assertFalse(FIXTURE["original_production_response"])
        for market in ("KOSPI", "KOSDAQ"):
            ls, refs = inputs(market)
            self.assertEqual(self.derive(ls, refs, market), FIXTURE["markets"][market]["expected"])

    def test_direct_cumulative_row_not_intraday_sum_or_event_delta(self):
        ls, refs = inputs()
        result = self.derive(ls, refs)
        self.assertEqual(result["amounts_won"]["전체"], -21_021_000_000)
        self.assertNotEqual(result["amounts_won"]["전체"], sum(row["tot3"] for row in ls["response"]["t1662OutBlock"]) * 1_000_000)
        self.assertNotEqual(result["amounts_won"]["전체"], -36593 * 1_000_000)

    def test_each_market_keeps_its_own_amount(self):
        ls, refs = inputs("KOSDAQ")
        result = self.derive(ls, refs, "KOSDAQ")
        self.assertEqual(result["amounts_won"]["전체"], -95_360_000_000)
        self.assertTrue(result["close_amount_independently_checked"])

    def test_missing_independent_close_clock_does_not_become_close_crosscheck(self):
        result = self.derive(*inputs())
        self.assertTrue(result["unit_verified"])
        self.assertFalse(result["close_amount_independently_checked"])
        self.assertEqual(result["unit_calibration_clocks"], ["152600"])

    def test_wrong_market_request_rejected(self):
        ls, refs = inputs()
        ls["request"]["t1662InBlock"]["gubun"] = "1"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_wrong_venue_request_rejected(self):
        ls, refs = inputs()
        ls["request"]["t1662InBlock"]["exchgubun"] = "K"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_previous_day_request_rejected(self):
        ls, refs = inputs()
        ls["request"]["t1662InBlock"]["gubun3"] = "1"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_quantity_request_rejected(self):
        ls, refs = inputs()
        ls["request"]["t1662InBlock"]["gubun1"] = "1"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_reference_previous_date_rejected(self):
        ls, refs = inputs()
        refs["KRX"]["response"]["content"][0]["bizdate"] = "20261015"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_reference_market_or_venue_conflict_rejected(self):
        for key, value in (("krxMarketType", "KOSDAQ"), ("tradeType", "NXT")):
            ls, refs = inputs()
            refs["KRX"]["request"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.derive(ls, refs)

    def test_exact_close_row_required_no_before_or_after_substitution(self):
        for clock in ("152900", "153100"):
            ls, refs = inputs()
            next(row for row in ls["response"]["t1662OutBlock"] if row["time"] == "153000")["time"] = clock
            with self.subTest(clock=clock), self.assertRaisesRegex(ValueError, "장마감 시각 원표 없음"):
                self.derive(ls, refs)

    def test_special_session_uses_calendar_close(self):
        ls, refs = inputs("KOSDAQ")
        for row in ls["response"]["t1662OutBlock"]: row["time"] = "163000"
        for ref in refs.values():
            for row in ref["response"]["content"]: row["time"] = "163000"
        close = dt.datetime(2026, 10, 16, 16, 30, tzinfo=program.KST).timestamp()
        result = program.derive("KOSDAQ", close, ls, refs)
        self.assertEqual(result["source_time"], "163000")

    def test_duplicate_clock_rejected(self):
        ls, refs = inputs()
        ls["response"]["t1662OutBlock"].append(copy.deepcopy(ls["response"]["t1662OutBlock"][0]))
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_missing_or_invalid_money_never_becomes_zero(self):
        for value in (None, "", True, "NaN", "Infinity", "1.5"):
            ls, refs = inputs()
            ls["response"]["t1662OutBlock"][0]["tot3"] = value
            with self.subTest(value=value), self.assertRaises(ValueError): self.derive(ls, refs)

    def test_latest_raw_row_wrong_date_rejected(self):
        ls, refs = inputs()
        ls["response"]["t1662OutBlock"][0]["date"] = "20261015"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_source_arithmetic_tampering_rejected(self):
        ls, refs = inputs()
        ls["response"]["t1662OutBlock"][0]["tot3"] += 10
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_reference_arithmetic_tampering_rejected(self):
        ls, refs = inputs()
        refs["NXT"]["response"]["content"][0]["totalDiffPureBuyAmt"] = "1"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_wrong_scale_rejected_even_if_internal_arithmetic_balances(self):
        ls, refs = inputs()
        for row in ls["response"]["t1662OutBlock"]:
            for field in program.FIELDS: row[field] *= 100
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_all_zero_is_ambiguous_not_unit_proof(self):
        ls, refs = inputs()
        for row in ls["response"]["t1662OutBlock"]:
            for field in program.FIELDS: row[field] = 0
        for ref in refs.values():
            for row in ref["response"]["content"]:
                for field in program.FIELDS.values(): row[field] = "0"
        with self.assertRaises(ValueError): self.derive(ls, refs)

    def test_direct_total_retains_source_rounding_difference(self):
        result = self.derive(*inputs())
        self.assertEqual(result["net_component_residual_won"], 1_000_000)
        self.assertNotEqual(result["amounts_won"]["전체"], result["amounts_won"]["차익"] + result["amounts_won"]["비차익"])

    def test_render_only_eok_keeps_close_scope_and_precision(self):
        for market, total, residual in (("KOSPI", "-210.21억원", "+0.01억원"),
                                        ("KOSDAQ", "-953.60억원", "-0.01억원")):
            with self.subTest(market=market):
                case = sealed(market)
                text = "\n".join(program.render(case, market, NOW))
                for required in (total, residual, "KRX 마감 기준", "KRX+NXT", "15:30:00", "백만원", "단위: 억원", "NXT 하루 최종값은 아닙니다"):
                    self.assertIn(required, text)
                for value in case["derived"]["amounts_won"].values():
                    self.assertNotIn(f"{value:+,}원", text)
                self.assertNotRegex(text, r"[+-][\d,]+(?:\.\d+)?원")
                self.assertNotIn("단위: 원·억원", text)
                self.assertNotIn("최종 확정", text)
        self.assertIn("마감 금액의 독립 대조", "\n".join(program.render(sealed(), "KOSPI", NOW)))

    def test_held_has_reason_and_no_fake_zero_amount(self):
        text = "\n".join(program.render({"status": "held", "reason": "원화 원표 날짜 불일치"}, "KOSPI", NOW))
        self.assertIn("확인 보류", text)
        self.assertIn("날짜 불일치", text)
        self.assertNotIn("0.00억원", text)

    def test_missing_evidence_has_visible_hold(self):
        self.assertIn("확인 보류", "\n".join(program.render(None, "KOSPI", NOW)))

    def test_reject_stale_future_wrong_date_render(self):
        for now in (CLOSE - 20, NOW + 86400, NOW + 1000):
            with self.subTest(now=now):
                self.assertIn("확인 보류", "\n".join(program.render(sealed(), "KOSPI", now)))

    def test_rederive_detects_normalized_amount_tampering(self):
        case = sealed(); case["derived"]["amounts_won"]["전체"] = 0
        self.assertIn("확인 보류", "\n".join(program.render(case, "KOSPI", NOW)))

    def test_original_hash_or_bytes_tampering_held(self):
        for side in ("ls", "KRX", "NXT"):
            case = sealed()
            entry = case["ls"]["transport"] if side == "ls" else case["references"][side]
            entry["raw_sha256"] = "0" * 64
            with self.subTest(side=side):
                self.assertIn("확인 보류", "\n".join(program.render(case, "KOSPI", NOW)))

    def test_response_cannot_be_replaced_while_original_unchanged(self):
        case = sealed();case["ls"]["response"]["rsp_cd"] = "ERROR"
        self.assertIn("확인 보류", "\n".join(program.render(case, "KOSPI", NOW)))

    def test_receipt_clock_tampering_held(self):
        case = sealed();case["references"]["KRX"]["received_ts"] = CLOSE - 1
        self.assertIn("확인 보류", "\n".join(program.render(case, "KOSPI", NOW)))

    def test_collector_failure_is_local_held_and_retains_error(self):
        def failed(*args, **kwargs): raise RuntimeError("source unavailable")
        with patch.object(program.time, "time", return_value=NOW), patch.object(program, "_pace"):
            case = program.collect("redacted", "KOSPI", CLOSE, failed)
        self.assertEqual(case["status"], "held")
        self.assertIn("source unavailable", case["reason"])

    def test_collector_cannot_run_before_close_or_on_later_day(self):
        def forbidden(*args, **kwargs): raise AssertionError("not reached")
        for now in (CLOSE - 1, NOW + 86400):
            with self.subTest(now=now), patch.object(program.time, "time", return_value=now):
                case = program.collect("redacted", "KOSPI", CLOSE, forbidden)
                self.assertEqual(case["status"], "held")
                self.assertIn("조회 날짜", case["reason"])

    def test_real_close_message_only_and_both_markets(self):
        ep = {"start_ts": CLOSE - 1800, "low_ts": CLOSE - 600, "start_price": 1000, "low_price": 980}
        w = monitor.Watch.__new__(monitor.Watch)
        w.raw = {"program_close": {market: sealed(market) for market in ("KOSPI", "KOSDAQ")}}
        w.attribution = lambda *args: {}
        w._kosdaq_attribution = lambda *args: {}
        with patch.object(program.time, "time", return_value=NOW), patch.object(monitor, "market_attribution_lines", return_value=["• 기존 사건 구간 수급"]), patch.object(monitor, "market_attribution_footer", return_value="기존 사건 기준"):
            for market in ("KOSPI", "KOSDAQ"):
                ordinary = w.build_end(ep, NOW, 985) if market == "KOSPI" else w.build_kosdaq_drop_alert("end", ep, NOW, 985)
                close = w.build_end(ep, NOW, 985, session_close=True) if market == "KOSPI" else w.build_kosdaq_drop_alert("close", ep, NOW, 985, session_close=True)
                self.assertNotIn("당일 누적 프로그램", ordinary)
                self.assertIn("기존 사건 구간 수급", close)
                self.assertIn("당일 누적 프로그램", close)
                self.assertNotIn("확인 보류", close)
                visible = re.sub("<[^>]+>", "", close)
                self.assertLess(len(visible), 4096)

    def test_noon_test_run_no_episode_do_not_query(self):
        w = monitor.Watch.__new__(monitor.Watch)
        w.raw = {};w.token = "redacted"
        w.episode = {};w.idx = deque([(CLOSE - 1, 1)])
        w.kosdaq_episode = {};w.kosdaq_idx = deque([(CLOSE - 1, 1)])
        close = dt.datetime.fromtimestamp(CLOSE, program.KST)
        def forbidden(*args, **kwargs): raise AssertionError("collection not due")
        with patch.object(monitor, "collect_program_close", side_effect=forbidden):
            asyncio.run(w._prepare_program_close(close, None, close - dt.timedelta(hours=3)))
            asyncio.run(w._prepare_program_close(close, 15, close + dt.timedelta(minutes=2)))
            w.episode = None;w.kosdaq_episode = None
            asyncio.run(w._prepare_program_close(close, None, close + dt.timedelta(minutes=2)))
        self.assertEqual(w.raw, {})

    def test_only_existing_active_close_market_collected(self):
        w = monitor.Watch.__new__(monitor.Watch)
        w.raw = {};w.token = "redacted"
        w.episode = {};w.idx = deque([(CLOSE - 1, 1)])
        w.kosdaq_episode = None;w.kosdaq_idx = deque()
        close = dt.datetime.fromtimestamp(CLOSE, program.KST)
        with patch.object(monitor, "collect_program_close", return_value={"status": "held"}) as collect:
            asyncio.run(w._prepare_program_close(close, None, close + dt.timedelta(minutes=2)))
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(collect.call_args.args[1], "KOSPI")
        self.assertEqual(set(w.raw["program_close"]), {"KOSPI"})


if __name__ == "__main__":
    unittest.main()

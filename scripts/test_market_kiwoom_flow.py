"""Network-blocked source, currency, timestamp and provider-switch boundaries."""
from __future__ import annotations
import base64
import copy
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import market_kiwoom_flow as flow
from market_program_close import FIELDS, reference_request
from market_flow_channels import block_scope_matches

DAY = "20261020"
NOW = dt.datetime(2026, 10, 20, 10, 0, 1, tzinfo=flow.KST).timestamp()


def sealed(api, market, response, **changes):
    raw = json.dumps(response, ensure_ascii=False).encode()
    value = dict(api_id=api, request=(flow.cash_request if api == "ka10051" else flow.program_request)(market, DAY),
                 query_started_ts=NOW-1, received_ts=NOW, http_status=200, response=response,
                 raw_base64=base64.b64encode(raw).decode(), raw_sha256=flow.digest(raw), cont_yn="N")
    value.update(changes)
    return value


def cash(market="KOSPI"):
    values = {key: "0" for key in flow.ACTORS.values()}
    values.update(ind_netprps="50", frgnr_netprps="-20", orgn_netprps="-30", invtrt_netprps="-30")
    row = dict(inds_cd=flow.CODES[market][1], inds_nm="종합("+market+")", **values)
    return sealed("ka10051", market, dict(return_code=0, inds_netprps=[row]))


def program(market="KOSPI", negative="-60"):
    # Synthetic independently dated KRW originals; not actual operating bytes.
    amounts = dict(tot1=1000, tot2=1060, tot3=-60, cha1=400, cha2=380, cha3=20,
                   bcha1=600, bcha2=680, bcha3=-80)
    row = {flow.PROGRAM_FIELDS[k]: str(v) for k, v in amounts.items()}
    row.update(cntr_tm="100000", all_netprps=negative)
    entry = sealed("ka90005", market, dict(return_code=0, prm_trde_trnsn=[row]), cont_yn="Y")
    refs = {}
    for venue, multiplier in (("KRX", 1000000), ("NXT", 0)):
        body = {"content": [dict(bizdate=DAY, time="100000", **{FIELDS[k]: v*multiplier for k, v in amounts.items()})]}
        raw = json.dumps(body).encode()
        refs[venue] = dict(request=reference_request(market, DAY, venue), http_status=200, response=body,
                           raw_base64=base64.b64encode(raw).decode(), raw_sha256=flow.digest(raw))
    return entry, refs


class KiwoomSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"MARKET_SOURCE_EVIDENCE_DIR": self.temp.name})
        self.env.start()
        flow._CACHE.clear()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_both_market_cash_aggregates_and_institution_subset(self):
        for market in flow.CODES:
            value = flow.parse_cash(cash(market), market)
            self.assertEqual(value["values"]["투신"], -30)
            self.assertEqual(value["investor_residual_eok"], 0)
            self.assertEqual(value["institution_subgroup_residual_eok"], 0)
            self.assertFalse(value["interval_eligible"])
            self.assertFalse(value["source_time_verified"])

    def test_missing_trust_is_held_not_zero(self):
        entry = cash(); del entry["response"]["inds_netprps"][0]["invtrt_netprps"]
        value = flow.parse_cash(sealed("ka10051", "KOSPI", entry["response"]), "KOSPI")
        self.assertIsNone(value["values"]["투신"])

    def test_valid_zero_not_missing(self):
        entry = cash(); row = entry["response"]["inds_netprps"][0]
        row.update({key: "0" for key in flow.ACTORS.values()})
        self.assertEqual(flow.parse_cash(sealed("ka10051", "KOSPI", entry["response"]), "KOSPI")["values"]["투신"], 0)

    def test_wrong_cash_request_market_unit_venue_day_continuation_rejected(self):
        for key, value in (("mrkt_tp", "1"), ("amt_qty_tp", "1"), ("stex_tp", "1"), ("base_dt", "20261019")):
            entry = cash(); entry["request"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): flow.parse_cash(entry, "KOSPI")
        with self.assertRaises(ValueError): flow.parse_cash(dict(cash(), cont_yn="Y"), "KOSPI")
        with self.assertRaises(ValueError): flow.parse_cash(dict(cash(), cont_yn=None), "KOSPI")

    def test_wrong_cash_row_name_or_code_rejected(self):
        for key, value in (("inds_cd", "001"), ("inds_nm", "종합(KOSDAQ)")):
            entry = cash(); entry["response"]["inds_netprps"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                flow.parse_cash(sealed("ka10051", "KOSPI", entry["response"]), "KOSPI")

    def test_cash_duplicates_missing_population_and_bad_sum_rejected(self):
        for mode in ("duplicate", "missing", "residual", "subgroup", "date"):
            entry = cash(); body = entry["response"]; row = body["inds_netprps"][0]
            if mode == "duplicate": body["inds_netprps"].append(copy.deepcopy(row))
            if mode == "missing": del row["frgnr_netprps"]
            if mode == "residual": row["etc_corp_netprps"] = "100"
            if mode == "subgroup": row["invtrt_netprps"] = "100"
            if mode == "date": body["date"] = "20261019"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                flow.parse_cash(sealed("ka10051", "KOSPI", body), "KOSPI")

    def test_bad_raw_http_return_code_or_stored_json_rejected(self):
        for key, value in (("http_status", 403), ("raw_sha256", "0"*64), ("raw_base64", "%%%")):
            with self.subTest(key=key), self.assertRaises(ValueError): flow.parse_cash(dict(cash(), **{key: value}), "KOSPI")
        entry = cash(); entry["response"]["return_code"] = 1
        with self.assertRaises(ValueError): flow.parse_cash(entry, "KOSPI")
        with self.assertRaises(ValueError): flow.parse_cash(sealed("ka10051", "KOSPI", dict(return_code=1)), "KOSPI")

    def test_cash_query_interval_cannot_be_forged(self):
        with self.assertRaises(ValueError): flow.parse_cash(dict(cash(), query_started_ts=NOW+1), "KOSPI")

    def test_raw_proof_recomputed_before_cash_render(self):
        entry = cash(); entry["retained_evidence"] = flow._retain(entry)
        value = flow.parse_cash(entry, "KOSPI")
        text = "\n".join(flow.cash_lines(value, "KOSPI", NOW))
        self.assertIn("투신(기관 내)", text)
        self.assertIn("사건 구간·5분 수급을 대신하지 않습니다", text)
        for key, wrong in (("values", {"개인": 999}), ("date", "20261019"), ("interval_eligible", True)):
            rendered = "\n".join(flow.cash_lines(dict(value, **{key: wrong}), "KOSPI", NOW))
            self.assertIn("확인 보류", rendered)
            self.assertNotIn("999억원", rendered)

    def test_cash_evidence_missing_tampered_or_stale_held(self):
        entry = cash(); entry["retained_evidence"] = flow._retain(entry)
        value = flow.parse_cash(entry, "KOSPI")
        self.assertIn("확인 보류", "\n".join(flow.cash_lines(value, "KOSPI", NOW+121)))
        Path(value["evidence"]["path"]).write_text("{}")
        self.assertIn("확인 보류", "\n".join(flow.cash_lines(value, "KOSPI", NOW)))

    def test_cache_preserves_original_receipt_timestamp(self):
        with patch.object(flow.time, "time", return_value=NOW):
            first = flow.cash_current("KOSPI", call=lambda *a: cash())
        with patch.object(flow.time, "time", return_value=NOW+30):
            second = flow.cash_current("KOSPI", call=lambda *a: self.fail("cached query repeated"))
        self.assertIs(first, second)
        self.assertEqual(second["received_ts"], NOW)

    def test_both_program_markets_independently_reconcile_nine_fields(self):
        for market in flow.CODES:
            entry, refs = program(market)
            value = flow.parse_program(entry, market, refs)
            self.assertEqual(value["전체"], -.6)
            self.assertEqual(value["차익"], .2)
            self.assertEqual(value["비차익"], -.8)
            self.assertTrue(block_scope_matches(value, market, "프로그램"))
            self.assertFalse(block_scope_matches(value, market, "현물"))
            self.assertFalse(block_scope_matches(value, "KOSDAQ" if market == "KOSPI" else "KOSPI", "프로그램"))

    def test_actual_repeated_negative_sign_is_negative_not_positive(self):
        entry, refs = program(negative="--60")
        self.assertEqual(flow.parse_program(entry, "KOSPI", refs)["전체"], -.6)
        for value in (None, True, "---1", "1.5", "nan", "--1"):
            with self.subTest(value=value), self.assertRaises(ValueError): flow.integer(value)

    def test_program_missing_actor_or_wrong_buy_sell_rejected(self):
        for key, value in (("all_netprps", "60"), ("all_buy", None), ("all_buy", "--1000")):
            entry, refs = program(); entry["response"]["prm_trde_trnsn"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                flow.parse_program(sealed("ka90005", "KOSPI", entry["response"]), "KOSPI", refs)

    def test_program_market_date_currency_reference_and_clock_boundaries(self):
        for mode in ("request", "future", "duplicate", "reference_scope", "reference_hash", "reference_date", "reference_clock", "missing_reference"):
            entry, refs = program()
            if mode == "request": entry["request"]["mrkt_tp"] = "P001_AL02"
            if mode == "future": entry["received_ts"] = NOW-60
            if mode == "duplicate": entry = sealed("ka90005", "KOSPI", dict(return_code=0, prm_trde_trnsn=entry["response"]["prm_trde_trnsn"]*2))
            if mode == "reference_scope": refs["KRX"]["request"]["tradeType"] = "NXT"
            if mode == "reference_hash": refs["KRX"]["raw_sha256"] = "0"*64
            if mode in ("reference_date", "reference_clock"):
                refs["KRX"]["response"]["content"][0]["bizdate" if mode == "reference_date" else "time"] = "20261019" if mode == "reference_date" else "095900"
                raw = json.dumps(refs["KRX"]["response"]).encode()
                refs["KRX"].update(raw_base64=base64.b64encode(raw).decode(), raw_sha256=flow.digest(raw))
            if mode == "missing_reference": del refs["NXT"]
            with self.subTest(mode=mode), self.assertRaises(ValueError): flow.parse_program(entry, "KOSPI", refs)

    def test_only_public_read_tr_allowlist_and_offline_config(self):
        with patch.object(flow, "_token", side_effect=AssertionError("auth must not be called")):
            with self.assertRaises(ValueError): flow.request("kt10000", {})
        with patch.dict(os.environ, {"MARKET_SOURCE_OFFLINE": "1", "KIWOOM_APPKEY": "fake", "KIWOOM_SECRETKEY": "fake"}):
            self.assertFalse(flow.configured())

    def test_optional_failure_keeps_ls_values_and_no_false_futures_fill(self):
        original = {"현물": {"source_tr": "t1602"}, "프로그램": {"source_tr": "t1640"}, "지수선물": None, "errors": {"지수선물": "missing"}}
        with patch.object(flow, "configured", return_value=True), patch.object(flow, "cash_current", side_effect=ValueError("sensitive details")), patch.object(flow, "program_current", side_effect=ValueError("sensitive details")):
            result = flow.enrich_snapshot(copy.deepcopy(original), "KOSDAQ")
        self.assertEqual(result["프로그램"], original["프로그램"])
        self.assertIsNone(result["지수선물"])
        self.assertFalse(result["source_coverage"]["kiwoom_index_futures_available"])
        self.assertNotIn("sensitive details", json.dumps(result))

    def test_fresh_program_replaces_ls_and_stale_program_does_not(self):
        entry, refs = program(); verified = flow.parse_program(entry, "KOSPI", refs)
        for at, expected in ((NOW, "ka90005"), (NOW+100, "t1640")):
            flow._CACHE.clear()
            with patch.object(flow, "configured", return_value=True), patch.object(flow, "cash_current", return_value=flow.parse_cash(cash(), "KOSPI")), patch.object(flow, "program_current", return_value=verified), patch.object(flow.time, "time", return_value=at):
                got = flow.enrich_snapshot({"프로그램": {"source_tr": "t1640"}, "errors": {}}, "KOSPI")
            self.assertEqual(got["프로그램"]["source_tr"], expected)

    def test_source_or_currency_switch_cannot_create_surge_delta(self):
        import kospi_shock_episode_watch as watch
        first, refs = program(); block = flow.parse_program(first, "KOSPI", refs)
        rows = [{"프로그램": dict(block, sample_ts=NOW-300, source_tr="t1640", unit="LS_raw_amount")}, {"프로그램": dict(block, sample_ts=NOW)}]
        self.assertIsNone(watch._flow_surge_program(rows, NOW))
        rows[0]["프로그램"].update(source_tr="ka90005", unit="억원")
        value = watch._flow_surge_program(rows, NOW)
        self.assertEqual(value["unit"], "억원")

    def test_preserved_actual_cash_responses_replay_both_markets(self):
        fixture = json.loads((Path(__file__).parent / "test_fixtures/kiwoom_cash_readback_20261020.json").read_text(encoding="utf-8"))
        self.assertFalse(fixture["operating_delivery"])
        for market, record in fixture["cash"].items():
            value = flow.parse_cash(record["entry"], market)
            self.assertEqual(value["values"], record["expected_values"])
            self.assertFalse(value["interval_eligible"])

    def test_fallback_cash_supplement_is_separate_from_missing_incident(self):
        import kospi_rapid_fallback_watch as fallback
        entry = cash(); entry["retained_evidence"] = flow._retain(entry)
        value = flow.parse_cash(entry, "KOSPI")
        with patch.object(fallback.time, "time", return_value=NOW):
            text = fallback.build_alert(dt.datetime.fromtimestamp(NOW-10, flow.KST), 3000, 3100, -3.2,
                                        -1.0, -1.2, ["가격 조건"], None, "구간 미확보", cash_supplement=value)
        self.assertIn("원인 주체 확정 보류", text)
        self.assertIn("키움 당일 누적 현물 수급", text)
        self.assertIn("사건 구간·5분 수급을 대신하지 않습니다", text)

    def test_verified_cash_tail_fits_structured_enrichment_message_budget(self):
        import html
        import re
        entry = cash(); entry["retained_evidence"] = flow._retain(entry)
        block = flow.parse_cash(entry, "KOSPI")
        rendered = "\n".join(flow.cash_lines(block, "KOSPI", NOW))
        visible = html.unescape(re.sub(r"<[^>]+>", "", rendered))
        self.assertLessEqual(len(visible), 280)
        self.assertLessEqual(3800 + 1 + len(visible), 4096)
        body = cash()["response"]; row = body["inds_netprps"][0]
        row.update(ind_netprps=str(10**120), frgnr_netprps=str(-(10**120)), orgn_netprps="0", invtrt_netprps="0")
        huge = sealed("ka10051", "KOSPI", body); huge["retained_evidence"] = flow._retain(huge)
        self.assertIn("확인 보류", "\n".join(flow.cash_lines(flow.parse_cash(huge, "KOSPI"), "KOSPI", NOW)))


if __name__ == "__main__":
    unittest.main()

"""Offline identity/unit/evidence regressions; every network route is blocked."""

import base64
import copy
import hashlib
import json
import os
import pathlib
import socket
import sys
import tempfile
import unittest
import urllib.request
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_trade_integrity as trade


HS = "8542323000"


def row(**changes):
    result = {"year": "202609", "hsCode": HS, "expDlr": "15010000000", "expWgt": "123600"}
    result.update(changes)
    return result


class OfflineTests(unittest.TestCase):
    def setUp(self):
        # Pure helpers must never make a source request or send Telegram.
        for target in ((socket, "socket"), (socket, "create_connection"), (urllib.request, "urlopen")):
            guard = patch.object(*target, side_effect=AssertionError("network forbidden in integrity tests"))
            guard.start()
            self.addCleanup(guard.stop)


class MonthAndNumberTests(OfflineTests):
    def test_month_allows_only_one_calendar_month(self):
        for value in ("202609", 202609, "2026-09", "2026.09", "2026/9", " 2026 - 09 ", "2026년 9월"):
            with self.subTest(value=value):
                self.assertEqual(trade.normalize_month(value), "202609")

    def test_month_rejects_cumulative_totals_ranges_and_daily_dates(self):
        for value in ("총계", "누계 202609", "202601~202609", "2026.01~2026.09", "20260901", "2026-09-01", "2026", "202609누계", "202609 총계", "202609/202609", "2026 09", True, 202609.0, None, "202600", "202613", "000009"):
            with self.subTest(value=value):
                self.assertIsNone(trade.normalize_month(value))

    def test_number_keeps_reported_zero_and_valid_grouping(self):
        for value, expected in ((0, 0), ("0.0", 0), ("1,234,567.89", 1234567.89), (Decimal("2.5"), 2.5), ("1e3", 1000)):
            with self.subTest(value=value):
                self.assertEqual(trade.finite_number(value), expected)

    def test_number_rejects_nonfinite_negative_missing_and_malformed(self):
        for value in ("NaN", float("nan"), "Infinity", float("inf"), "-Infinity", -1, "-1", True, False, "-", "", None, "12,34", "1,2,3", "1,000달러", {}, "1e9999", "1e-9999"):
            with self.subTest(value=value):
                self.assertIsNone(trade.finite_number(value))


class ExactRowTests(OfflineTests):
    def choose(self, rows, **kwargs):
        return trade.choose_exact_row(rows, "202609", HS, **kwargs)

    def test_national_exact_response_operands_and_weight(self):
        source = row(year="2026.09", hsCode="8542.32-3000")
        selected, error = self.choose([source], unit_proof={"official_field_unit": "USD"})
        self.assertEqual(error, "")
        self.assertEqual(selected["amount_usd"], 15_010_000_000)
        self.assertEqual(selected["weight_kg"], 123_600)
        self.assertEqual(selected["raw_amount_text"], "15010000000")
        self.assertEqual(selected["selected_row"], source)
        self.assertEqual(selected["identity_proof"]["month"]["response_fields"], {"year": "2026.09"})
        self.assertEqual(selected["unit_proof"]["status"], "caller_declared_contract")

    def test_empty_response_is_missing_but_wrong_response_is_invalid(self):
        self.assertEqual(self.choose([]), (None, "missing:no_rows"))
        for source in (row(year="202608"), row(hsCode="854232"), {}, None, row(year="2026.01~2026.09")):
            with self.subTest(source=source):
                selected, error = self.choose([source])
                self.assertIsNone(selected)
                self.assertTrue(error.startswith("invalid:"))

    def test_missing_month_or_hs_is_never_filled_from_request(self):
        for missing_field, reason in (("year", "response_month_missing"), ("hsCode", "response_hs_missing")):
            source = row()
            del source[missing_field]
            self.assertEqual(self.choose([source]), (None, "invalid:" + reason))

    def test_range_and_total_are_not_selected_by_substring(self):
        for period in ("202601~202609", "2026.09 누계", "총계", "20260901"):
            self.assertIsNone(self.choose([row(year=period)])[0])
        selected, error = self.choose([row(year="총계", expDlr="999999999999"), row()])
        self.assertEqual(error, "")
        self.assertEqual(selected["amount_usd"], 15_010_000_000)
        self.assertEqual(selected["identity_proof"]["selection"]["row_index"], 1)

    def test_two_matching_rows_are_ambiguous_even_when_values_agree(self):
        for second in (row(), row(expDlr="1"), row(expDlr="NaN")):
            self.assertEqual(self.choose([row(), second]), (None, "invalid:duplicate_target_rows"))

    def test_valid_row_is_selected_after_an_explicit_different_row(self):
        selected, error = self.choose([row(year="202608", expDlr="1"), row()])
        self.assertEqual(error, "")
        self.assertEqual(selected["amount_usd"], 15_010_000_000)
        self.assertEqual(selected["identity_proof"]["selection"]["rejected_rows"][0]["reason"], "different_month_or_hs")

    def test_incomplete_second_identity_cannot_hide_a_duplicate(self):
        ambiguous = row()
        del ambiguous["year"]
        self.assertEqual(self.choose([row(), ambiguous]), (None, "invalid:ambiguous_target_identity"))

    def test_conflicting_echo_aliases_do_not_choose_the_first(self):
        for source in (row(priodTitle="202608"), row(hsCd="854232")):
            self.assertEqual(self.choose([source]), (None, "invalid:conflicting_identity"))

    def test_same_echo_aliases_are_compatible(self):
        selected, error = self.choose([row(priodTitle="2026-09", hsCd=HS)])
        self.assertEqual(error, "")
        self.assertEqual(selected["month"], "202609")

    def test_province_missing_echo_has_explicit_request_scope_only(self):
        selected, error = self.choose([row()], region={"sido": "44", "name": "충남"})
        self.assertEqual(error, "")
        proof = selected["identity_proof"]["region"]
        self.assertEqual(proof["status"], "request_scoped_no_response_echo")
        self.assertEqual(proof["response_fields"], {})
        self.assertNotIn("sidoCd", selected["selected_row"])

    def test_province_present_code_and_name_must_both_match(self):
        selected, error = self.choose([row(sidoCd="44", sidoNm="충청남도")], region={"sido": "44", "name": "충남"})
        self.assertEqual(error, "")
        self.assertEqual(selected["identity_proof"]["region"]["status"], "response_echo_matched")
        for source in (row(sidoCd="43"), row(sidoNm="충북"), row(sidoCd="44", sidoNm="충북")):
            self.assertEqual(self.choose([source], region="44"), (None, "invalid:region_mismatch"))

    def test_contradictory_requested_region_is_invalid(self):
        self.assertEqual(self.choose([row(sidoNm="충북")], region={"sido": "44", "name": "충북"}), (None, "invalid:invalid_requested_region"))

    def test_country_is_not_invented_from_request(self):
        self.assertEqual(self.choose([row()], country="MY"), (None, "invalid:response_country_missing"))
        self.assertEqual(self.choose([row(statCd="US")], country="MY"), (None, "invalid:country_mismatch"))
        selected, error = self.choose([row(statCd="MY", statCdCntnKor1="말레이시아")], country="MY")
        self.assertEqual(error, "")
        self.assertEqual(selected["country_code"], "MY")
        self.assertEqual(selected["identity_proof"]["country"]["response_fields"]["statCd"], "MY")

    def test_country_name_only_echo_is_retained_and_conflict_is_invalid(self):
        self.assertEqual(self.choose([row(countryName="Malaysia")], country="MY")[1], "")
        self.assertEqual(self.choose([row(statCd="MY", countryName="USA")], country="MY"), (None, "invalid:country_mismatch"))

    def test_no_amount_size_heuristic_on_either_side_of_old_boundary(self):
        for amount in ("1", "99999999", "100000000", "15010000000"):
            selected, error = self.choose([row(expDlr=amount)], unit="usd")
            self.assertEqual(error, "")
            self.assertEqual(selected["amount_usd"], float(amount))

    def test_explicit_thousand_unit_does_not_depend_on_amount_field(self):
        source = {"year": "202609", "hsCode": HS, "expUsdAmt": "7840000"}
        usd, error = self.choose([source], value_fields=("expUsdAmt",), unit="usd")
        thousand, second_error = self.choose([source], value_fields=("expUsdAmt",), unit="thousand_usd", factor=1000)
        self.assertEqual((error, second_error), ("", ""))
        self.assertEqual(usd["amount_usd"], 7_840_000)
        self.assertEqual(thousand["amount_usd"], 7_840_000_000)
        self.assertEqual(thousand["unit_proof"]["factor_to_usd"], "1000")

    def test_unresolved_unit_keeps_raw_operands_without_usd_claim(self):
        selected, error = self.choose([row()], unit="unverified", unit_proof={"status": "docs_conflict"})
        self.assertEqual(error, "")
        self.assertEqual(selected["raw_amount"], 15_010_000_000)
        self.assertIsNone(selected["amount_usd"])
        self.assertEqual(selected["unit_proof"]["status"], "unverified")
        self.assertEqual(selected["unit_proof"]["contract"], {"status": "docs_conflict"})

    def test_conflicting_or_unknown_unit_contract_is_invalid(self):
        for options, reason in (({"unit": "usd", "factor": 1000}, "unit_factor_conflict"), ({"unit": "unverified", "factor": 1}, "unit_factor_conflict"), ({"unit": "EUR"}, "unit_contract")):
            self.assertEqual(self.choose([row()], **options), (None, "invalid:" + reason))

    def test_amount_and_weight_invalidity_never_becomes_zero(self):
        for source in (row(expDlr="NaN"), row(expDlr="-1"), row(expDlr="Infinity"), row(expWgt="-1"), row(expWgt="NaN")):
            self.assertIsNone(self.choose([source])[0])
        self.assertEqual(self.choose([row(expDlr="0", expWgt="0")])[0]["amount_usd"], 0)

    def test_multiple_amount_aliases_and_conflicting_weights_are_invalid(self):
        self.assertEqual(self.choose([row(expUsdAmt="15010000000")], value_fields=("expDlr", "expUsdAmt")), (None, "invalid:ambiguous_amount_fields"))
        self.assertEqual(self.choose([row(expTtwg="1")]), (None, "invalid:conflicting_weight_fields"))

    def test_conversion_overflow_is_held(self):
        self.assertEqual(self.choose([row(expDlr="1e308")], unit="thousand_usd"), (None, "invalid:converted_amount_not_finite"))

    def test_missing_optional_weight_is_distinct_from_zero(self):
        source = row()
        del source["expWgt"]
        selected, error = self.choose([source])
        self.assertEqual(error, "")
        self.assertIsNone(selected["weight_kg"])
        self.assertEqual(selected["weight_status"], "not_returned")

    def test_selection_is_detached_and_does_not_mutate_inputs(self):
        source, contract = row(), {"source": ["official unit definition"]}
        before = copy.deepcopy(source)
        selected, _ = self.choose([source], unit_proof=contract)
        selected["selected_row"]["expDlr"] = "1"
        selected["unit_proof"]["contract"]["source"].append("tampered")
        self.assertEqual(source, before)
        self.assertEqual(contract, {"source": ["official unit definition"]})


class TradeEvidenceTests(OfflineTests):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = pathlib.Path(temporary.name) / "evidence.json"

    def test_exact_bytes_hash_length_and_metadata_are_saved(self):
        raw = b'<response>\r\n<value>15010000000</value>\n</response>\x00'
        with patch.dict(os.environ, {"GITHUB_SHA": "header-sha", "GITHUB_RUN_ID": "38727642051", "GITHUB_RUN_ATTEMPT": "1"}):
            ledger = trade.TradeEvidence(self.path, code_sha="actual-checkout")
        attempt = ledger.record_attempt("GET", "https://example.test/trade", params={"strtYymm": "202609"}, status=200, raw_bytes=raw, started_at="2026-10-16T03:49:00+09:00", completed_at="2026-10-16T03:49:01+09:00")
        selected, error = trade.choose_exact_row([row()], "202609", HS)
        ledger.mark_selection(attempt, selected, error)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["code_sha"], "actual-checkout")
        self.assertEqual(document["github_sha"], "header-sha")
        self.assertEqual(document["run_id"], "38727642051")
        saved = document["attempts"][0]
        self.assertEqual(saved["started_at"], "2026-10-16T03:49:00+09:00")
        self.assertEqual(saved["completed_at"], "2026-10-16T03:49:01+09:00")
        self.assertEqual(base64.b64decode(saved["response"]["raw_base64"]), raw)
        self.assertEqual(saved["response"]["raw_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(saved["response"]["raw_bytes_length"], len(raw))
        self.assertTrue(saved["response"]["raw_preserved"])
        self.assertEqual(saved["selection"]["normalized"]["selected_row"], row())

    def test_every_retry_is_preserved_without_network_or_error_message(self):
        ledger = trade.TradeEvidence(self.path)
        ledger.record_attempt("GET", "https://example.test/trade", status=429, raw_bytes=b"rate limited")
        ledger.record_attempt("GET", "https://example.test/trade", error_type=TimeoutError("https://secret:private@example.test/?serviceKey=private"))
        ledger.record_attempt("GET", "https://example.test/trade", status=200, raw_bytes=b"ok")
        attempts = ledger.as_dict()["attempts"]
        self.assertEqual([item["attempt_id"] for item in attempts], ["1", "2", "3"])
        self.assertEqual(attempts[1]["error_type"], "TimeoutError")
        self.assertEqual(attempts[1]["response"]["raw_not_preserved_reason"], "no_response_bytes")
        self.assertNotIn("private", self.path.read_text(encoding="utf-8"))

    def test_secret_values_never_enter_url_params_headers_or_selection(self):
        secret = "synthetic-secret+/=42"
        with patch.dict(os.environ, {"TRADE_TEST_SECRET": secret}):
            ledger = trade.TradeEvidence(self.path, credential_env_names=("TRADE_TEST_SECRET",))
        attempt = ledger.record_attempt("GET", "https://name:password@example.test/trade?serviceKey=" + quote(secret, safe="") + "&strtYymm=202609#ignored", params={"serviceKey": secret, "strtYymm": "202609", "nested": {"api_key": "other-unknown-secret"}}, status=200, raw_bytes=b"<empty />", response_headers={"Set-Cookie": "session-private", "Date": "Fri, 16 Oct 2026 00:00:00 GMT"})
        selected, error = trade.choose_exact_row([row(comment=secret)], "202609", HS)
        ledger.mark_selection(attempt, selected, error)
        text = self.path.read_text(encoding="utf-8")
        for forbidden in (secret, quote(secret, safe=""), "name:password", "other-unknown-secret", "session-private", "#ignored"):
            self.assertNotIn(forbidden, text)
        saved = ledger.as_dict()["attempts"][0]
        self.assertEqual(saved["request"]["params"]["serviceKey"], "[REDACTED]")
        self.assertEqual(saved["selection"]["normalized"]["selected_row"]["comment"], "[REDACTED]")
        self.assertTrue(saved["selection"]["metadata_redacted"])
        self.assertEqual(base64.b64decode(saved["response"]["raw_base64"]), b"<empty />")

    def test_response_with_secret_is_withheld_not_redacted_as_raw(self):
        secret = "synthetic-credential+/=42"
        for raw in (secret.encode(), quote(secret, safe="").lower().encode(), secret.encode("utf-16-le"), b'{"key":"synthetic-credential+\\u002f=42"}'):
            with self.subTest(raw=raw), patch.dict(os.environ, {"TRADE_TEST_SECRET": secret}):
                ledger = trade.TradeEvidence(self.path, credential_env_names=("TRADE_TEST_SECRET",))
                ledger.record_attempt("GET", "https://example.test", status=403, raw_bytes=raw)
                response = ledger.as_dict()["attempts"][0]["response"]
                self.assertFalse(response["raw_preserved"])
                self.assertIsNone(response["raw_base64"])
                self.assertIsNone(response["raw_sha256"])
                self.assertEqual(response["raw_bytes_length"], len(raw))
                self.assertEqual(response["raw_not_preserved_reason"], "credential_detected_in_response")

    def test_credential_named_response_is_withheld_even_without_env_value(self):
        for raw in (b'{"serviceKey":"unknown-key"}', b"<url>https://example.test?serviceKey=unknown-key&amp;x=1</url>", b"<serviceKey>unknown-key</serviceKey>"):
            ledger = trade.TradeEvidence(self.path, credential_env_names=())
            ledger.record_attempt("GET", "https://example.test", raw_bytes=raw)
            self.assertFalse(ledger.as_dict()["attempts"][0]["response"]["raw_preserved"])

    def test_encoded_environment_key_covers_decoded_response(self):
        secret = "test-key+/=not-real"
        with patch.dict(os.environ, {"TRADE_TEST_SECRET": quote(secret, safe="")}):
            ledger = trade.TradeEvidence(self.path, credential_env_names=("TRADE_TEST_SECRET",))
        ledger.record_attempt("GET", "https://example.test", raw_bytes=secret.encode())
        self.assertFalse(ledger.as_dict()["attempts"][0]["response"]["raw_preserved"])

    def test_held_selection_and_unit_unverified_are_not_verified(self):
        ledger = trade.TradeEvidence(self.path)
        first = ledger.record_attempt("GET", "https://example.test", raw_bytes=b"empty")
        ledger.mark_selection(first, None, "missing:no_rows")
        second = ledger.record_attempt("GET", "https://example.test", raw_bytes=b"row")
        selected, error = trade.choose_exact_row([row()], "202609", HS, unit="unverified")
        ledger.mark_selection(second, selected, error)
        self.assertEqual([item["selection"]["status"] for item in ledger.as_dict()["attempts"]], ["missing", "identity_matched_unit_unverified"])

    def test_detached_document_and_atomic_save_leave_no_temporary_files(self):
        ledger = trade.TradeEvidence(self.path)
        ledger.record_attempt("GET", "https://example.test", raw_bytes=b"raw")
        snapshot = ledger.as_dict()
        snapshot["attempts"][0]["response"]["raw_sha256"] = "changed"
        self.assertEqual(ledger.as_dict()["attempts"][0]["response"]["raw_sha256"], hashlib.sha256(b"raw").hexdigest())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        with self.assertRaisesRegex(ValueError, "unknown trade evidence attempt id"):
            ledger.mark_selection("unknown")

    def test_short_secret_does_not_rewrite_safe_response_encoding(self):
        # b'hello' encodes as aGVsbG8=, which contains the unrelated token bG8.
        with patch.dict(os.environ, {"TRADE_TEST_SECRET": "bG8"}):
            ledger = trade.TradeEvidence(self.path, credential_env_names=("TRADE_TEST_SECRET",))
        ledger.record_attempt("GET", "https://example.test", raw_bytes=b"hello")
        response = ledger.as_dict()["attempts"][0]["response"]
        self.assertEqual(base64.b64decode(response["raw_base64"]), b"hello")
        self.assertEqual(response["raw_sha256"], hashlib.sha256(b"hello").hexdigest())

    def test_nonbytes_are_explicitly_not_raw_evidence(self):
        ledger = trade.TradeEvidence(self.path)
        ledger.record_attempt("GET", "https://example.test", raw_bytes="pretend raw")
        response = ledger.as_dict()["attempts"][0]["response"]
        self.assertFalse(response["raw_preserved"])
        self.assertEqual(response["raw_not_preserved_reason"], "invalid_response_bytes_type")
        self.assertIsNone(response["raw_sha256"])


if __name__ == "__main__":
    unittest.main()

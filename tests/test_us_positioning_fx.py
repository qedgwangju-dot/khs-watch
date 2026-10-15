"""Offline boundary and tamper checks for exact-date ECOS conversion evidence."""
from copy import deepcopy
import datetime as dt
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import us_positioning_fx as fx


def observation():
    # Synthetic ECOS schema fixture; no claim that this test queries the server.
    return {"StatisticSearch": {"list_total_count": 1, "row": [{
        "STAT_CODE": "731Y001", "STAT_NAME": "주요국 통화의 대원화환율",
        "ITEM_CODE1": "0000001", "ITEM_NAME1": "원/미국달러(매매기준율)",
        "ITEM_CODE2": None, "ITEM_NAME2": None, "UNIT_NAME": "원",
        "TIME": "20261014", "DATA_VALUE": "1340.50",
    }]}}


class Reader:
    def __init__(self, payload=None, error=None):
        self.payload = json.dumps(observation() if payload is None else payload, ensure_ascii=False).encode()
        self.error = error
        self.calls = []

    def get(self, url, *, evidence_url):
        self.calls.append((url, evidence_url))
        if self.error:
            raise self.error
        return self.payload


class FxTests(unittest.TestCase):
    target = dt.date(2026, 10, 14)

    def parse(self, payload=None, target=None):
        return fx.parse_ecos_usdkrw(observation() if payload is None else payload,
                                   self.target if target is None else target)

    def test_exact_date_decimal_operands_and_conversion(self):
        value = self.parse()
        self.assertEqual(value["status"], "verified")
        self.assertEqual(value["date"], "2026-10-14")
        self.assertEqual(value["krw_per_usd"], "1340.50")
        self.assertEqual(Decimal("1234567.89") * Decimal(value["krw_per_usd"]), Decimal("1654938256.5450"))
        self.assertEqual(value["operands"]["StatisticSearch"]["row"][0]["DATA_VALUE"], "1340.50")
        self.assertIs(fx.checked_fx(value, self.target), value)
        self.assertIs(fx.checked_fx(value), value)
        self.assertNotIn("fetched_at", value)
        self.assertNotIn("sha256", value)

    def test_utf8_raw_response_and_iso_target(self):
        raw = json.dumps(observation(), ensure_ascii=False).encode("utf-8")
        self.assertEqual(self.parse(raw, "2026-10-14"), self.parse())

    def test_wrong_and_missing_series_fields_are_unavailable(self):
        for key, value in (("STAT_CODE", "731Y002"), ("ITEM_CODE1", "0000002"),
                           ("ITEM_NAME1", "원/미국달러(종가)"), ("ITEM_NAME1", "엔/미국달러(매매기준율)"),
                           ("ITEM_CODE2", "unexpected")):
            payload = observation()
            payload["StatisticSearch"]["row"][0][key] = value
            result = self.parse(payload)
            self.assertEqual(result["reason_code"], "series", (key, value))
            self.assertNotIn("krw_per_usd", result)
        for key in ("STAT_CODE", "ITEM_CODE1", "ITEM_NAME1"):
            payload = observation()
            del payload["StatisticSearch"]["row"][0][key]
            self.assertEqual(self.parse(payload)["status"], "unavailable")

    def test_exact_won_unit_required(self):
        for unit in (None, "", "원/달러", "달러", "100원", "KRW", "원화"):
            payload = observation()
            payload["StatisticSearch"]["row"][0]["UNIT_NAME"] = unit
            self.assertEqual(self.parse(payload)["reason_code"], "unit")

    def test_no_previous_or_later_observation_substitution(self):
        for date in ("20261013", "20261015", "2026-10-14", "20260230", None, 20261014):
            payload = observation()
            payload["StatisticSearch"]["row"][0]["TIME"] = date
            self.assertEqual(self.parse(payload)["reason_code"], "observation_date")

    def test_duplicate_missing_partial_or_false_row_count_rejected(self):
        for count, rows in ((0, []), (2, observation()["StatisticSearch"]["row"] * 2),
                            (2, observation()["StatisticSearch"]["row"]),
                            (1, []), (1, observation()["StatisticSearch"]["row"] * 2),
                            (True, observation()["StatisticSearch"]["row"]),
                            ("1", observation()["StatisticSearch"]["row"])):
            self.assertEqual(self.parse({"StatisticSearch": {"list_total_count": count, "row": rows}})["reason_code"], "row_count")

    def test_invalid_numeric_types_nonfinite_and_nonpositive_rejected(self):
        for rate in (None, "", "NaN", "Infinity", "-Infinity", "-1", "0", "0.000", True,
                     1340.50, 1340, "1_340.50", "1,340.50", " 1340.50", "1e3"):
            payload = observation()
            payload["StatisticSearch"]["row"][0]["DATA_VALUE"] = rate
            result = self.parse(payload)
            self.assertEqual(result["reason_code"], "rate", rate)
            self.assertNotIn("krw_per_usd", result)

    def test_invalid_request_date_is_not_echoed_or_queried(self):
        for target in ("https://secret@example.com", "20261014", "2026-02-30", None,
                       dt.datetime(2026, 10, 14), True):
            reader = Reader()
            result = fx.collect_fx(reader, target)
            self.assertEqual(result["reason_code"], "requested_date")
            self.assertIsNone(result["requested_date"])
            self.assertEqual(reader.calls, [])

    def test_upstream_error_message_and_unrelated_fields_not_copied(self):
        secret = "very-sensitive-key"
        result = self.parse({"RESULT": {"CODE": "ERROR-100", "MESSAGE": secret}})
        self.assertEqual(result["reason_code"], "response_error")
        self.assertNotIn(secret, json.dumps(result))
        payload = observation()
        payload["extra"] = secret
        payload["StatisticSearch"]["row"][0]["unused_metadata"] = secret
        self.assertNotIn(secret, json.dumps(self.parse(payload)))

    def test_malformed_json_and_duplicate_field_are_unavailable(self):
        for payload in (b"<html>unavailable</html>", b"\xff", [], {"StatisticSearch": []}):
            self.assertEqual(self.parse(payload)["status"], "unavailable")
        raw = json.dumps(observation()).replace('"DATA_VALUE": "1340.50"', '"DATA_VALUE":"1000", "DATA_VALUE":"1340.50"')
        self.assertEqual(self.parse(raw)["reason_code"], "duplicate_fields")

    def test_default_sample_uses_exact_date_and_ten_row_limit(self):
        reader = Reader()
        with patch.dict(os.environ, {}, clear=True):
            result = fx.collect_fx(reader, self.target)
        expected = "https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/1/10/731Y001/D/20261014/20261014/0000001"
        self.assertEqual(reader.calls, [(expected, expected)])
        self.assertEqual(result, self.parse())

    def test_authenticated_endpoint_is_encoded_and_evidence_redacted(self):
        reader = Reader()
        key = "secret/key?and=value"
        with patch.dict(os.environ, {"ECOS_API_KEY": key, "BOK_ECOS_API_KEY": "lower-priority"}, clear=True):
            result = fx.collect_fx(reader, self.target)
        request, evidence = reader.calls[0]
        self.assertIn("/secret%2Fkey%3Fand%3Dvalue/", request)
        self.assertIn("/[REDACTED]/json/kr/1/10/", evidence)
        self.assertNotIn("secret", evidence)
        self.assertNotIn(key, json.dumps(result))
        self.assertNotIn("lower-priority", request)

    def test_bok_key_alias_and_blank_primary(self):
        reader = Reader()
        with patch.dict(os.environ, {"ECOS_API_KEY": " ", "BOK_ECOS_API_KEY": "alias-secret"}, clear=True):
            self.assertEqual(fx.collect_fx(reader, self.target)["status"], "verified")
        self.assertIn("/alias-secret/", reader.calls[0][0])
        self.assertNotIn("alias-secret", reader.calls[0][1])

    def test_http_exception_never_leaks_url_credential(self):
        reader = Reader(error=RuntimeError("https://ecos.bok.or.kr/api/StatisticSearch/top-secret/json/kr"))
        with patch.dict(os.environ, {"ECOS_API_KEY": "top-secret"}, clear=True):
            result = fx.collect_fx(reader, self.target)
        self.assertEqual(result["reason_code"], "collection")
        self.assertNotIn("top-secret", json.dumps(result))
        self.assertNotIn("http", result["reason"])
        self.assertNotIn("krw_per_usd", result)

    def test_tampered_semantic_or_operand_values_are_rejected(self):
        valid = self.parse()
        for key, changed in (("krw_per_usd", "1340.51"), ("date", "2026-10-13"),
                             ("requested_date", "2026-10-13"), ("unit", "달러/원"),
                             ("source", "Yahoo"), ("source_url", "https://secret@example.com"),
                             ("base_currency", "JPY"), ("basis", "intraday"),
                             ("fetched_at", "always-changing")):
            altered = deepcopy(valid)
            altered[key] = changed
            self.assertIsNone(fx.checked_fx(altered), key)
        altered = deepcopy(valid)
        altered["operands"]["StatisticSearch"]["row"][0]["DATA_VALUE"] = "999"
        self.assertIsNone(fx.checked_fx(altered))
        self.assertIsNone(fx.checked_fx(valid, dt.date(2026, 10, 13)))
        self.assertIsNone(fx.checked_fx({"status": "unavailable"}))


if __name__ == "__main__":
    unittest.main()

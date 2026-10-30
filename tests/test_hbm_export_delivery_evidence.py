"""Offline source-to-delivery-gate integration; this file never sends an alert.

The K-stat form/sheet are preserved public fixtures.  All Customs API responses
below are SYNTHETIC operands for integration testing, not new source evidence.
Only the HTTP transport is replaced: production retries, selection, unit
reconciliation, ledger writing and final payload validation all run normally.
"""

import base64
import copy
import hashlib
import json
import pathlib
import re
import socket
import sys
import tempfile
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_trade_unit_reference as reference
import samsung_hbm_watch as watch
from hbm_trade_integrity import TradeEvidence


FIXTURES = pathlib.Path(__file__).parent / "fixtures"
HS = "8542323000"
CODE_SHA = "1234567890abcdef1234567890abcdef12345678"
RATE = 1336.79
FX_BASIS = "오프라인 합성 환율; 외부 전송 없음"
# Values are test operands.  The reference month's two provincial operands
# deliberately correspond to the separately preserved K-stat USD fixture.
MONTHS = {
    "202609": {"national": "15013987000", "44": "7840000000", "43": "2800000000", "MY": "1609624385", "kg": "147860", "MYkg": "4756"},
    "202608": {"national": "12225340203", "44": "7496336046", "43": "1404330188", "MY": "1624540000", "kg": "123653", "MYkg": "3800"},
    "202606": {"national": "12682181416", "44": "7107917859", "43": "2105178009", "MY": "1113400000", "kg": "134717", "MYkg": "3500"},
    "202509": {"national": "5233972000", "44": "3156200000", "43": "1156000000", "MY": "63950000", "kg": "126526", "MYkg": "1000"},
}


def api_xml(row):
    response = ET.Element("response")
    header = ET.SubElement(response, "header")
    ET.SubElement(header, "resultCode").text = "00"
    ET.SubElement(header, "resultMsg").text = "NORMAL SERVICE"
    item = ET.SubElement(ET.SubElement(ET.SubElement(response, "body"), "items"), "item")
    for name, value in row.items():
        ET.SubElement(item, name).text = str(value)
    return ET.tostring(response, encoding="utf-8", xml_declaration=True)


def kstat_xml(chungnam_amount, chungbuk_amount, *, omit_region=None):
    root = ET.Element("SHEET")
    data = ET.SubElement(root, "DATA")
    regions = (("44", "31", "충남", chungnam_amount), ("43", "36", "충북", chungbuk_amount))
    for rank, customs, code, name, amount in ((i + 1, *row) for i, row in enumerate(regions)):
        if customs == omit_region:
            continue
        values = {column: "" for column in reference.COLUMNS}
        values.update(RN=str(rank), ROW_CODE=code, KOR_NAME=name, THIS_EXP_AMT=str(amount))
        tr = ET.SubElement(data, "TR")
        for column in reference.COLUMNS:
            ET.SubElement(tr, "TD").text = values[column]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def form_with_september(form):
    form, count = re.subn(
        rb'(<select name="s_month"[^>]*>.*?<option[^>]*value="08"[^>]*>8</option>)',
        rb'\1\n<option value="09">9</option>', form, count=1, flags=re.S,
    )
    if count != 1:
        raise AssertionError("fixture month selector contract not found")
    return form.replace(b"setSelect(f.s_month, '08');", b"setSelect(f.s_month, '09');")


class Response:
    def __init__(self, content, content_type="application/xml"):
        self.content = content
        self.status_code = 200
        self.headers = {"Content-Type": content_type}
        self.text = content.decode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self.content)


class ExportDeliveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.out = pathlib.Path(temporary.name)
        self.now = datetime(2026, 10, 16, 1, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        self.form = form_with_september((FIXTURES / "hbm_kstat_province_form_20261016.html").read_bytes())
        self.sheet = (FIXTURES / "hbm_kstat_province_202608.xml").read_bytes()
        self.kstat_amount_override = {}
        self.kstat_omit_region = {}
        self.row_mutator = None
        self.calls = []
        self.state_path = watch.STATE
        self.state_before = self.state_path.read_bytes() if self.state_path.exists() else None
        self.addCleanup(self.assert_operating_state_preserved)
        self.ledger = TradeEvidence(
            self.out / "hbm_export_source_evidence.json",
            credential_env_names=(), code_sha=CODE_SHA, run_id="offline-delivery-evidence",
        )
        self.ledger.write()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(watch, "OUT", self.out))
        stack.enter_context(patch.object(watch, "_TRADE_EVIDENCE", self.ledger))
        stack.enter_context(patch.object(watch, "_SIDO_SOURCE_RESULT", None))
        stack.enter_context(patch.object(watch, "_SIDO_KSTAT_REFERENCE_CACHE", {}))
        stack.enter_context(patch.object(watch, "DATA_GO_KEY", "offline-key-never-used-on-network"))
        stack.enter_context(patch.object(watch, "save_state", side_effect=AssertionError("operating state writes forbidden")))
        stack.enter_context(patch.object(watch, "load_state", side_effect=AssertionError("operating state reads forbidden")))
        # The only allowed transport serves in-memory fixtures.  Other routes,
        # including Telegram and GitHub, fail before a socket can be created.
        stack.enter_context(patch("requests.sessions.Session.request", side_effect=self.transport))
        for module, name in ((socket, "socket"), (socket, "create_connection"), (urllib.request, "urlopen")):
            stack.enter_context(patch.object(module, name, side_effect=AssertionError("external network forbidden")))

    def assert_operating_state_preserved(self):
        after = self.state_path.read_bytes() if self.state_path.exists() else None
        self.assertEqual(after, self.state_before)

    def transport(self, method, url, **kwargs):
        method = method.upper()
        params = kwargs.get("params") or {}
        data = kwargs.get("data") or {}
        self.calls.append((method, url, copy.deepcopy(params), copy.deepcopy(data)))
        if method == "GET" and url == reference.FORM_URL:
            return Response(self.form, "text/html; charset=utf-8")
        if method == "POST" and url == reference.SHEET_URL:
            month = str(data["s_year"]) + str(data["s_month"])
            self.assertEqual(data["p_cond_in_gb"], "2")
            self.assertEqual(data["s_item_type"], "HS")
            self.assertEqual(data["s_item_value"], HS)
            self.assertEqual(data["s_field"], "AMT")
            self.assertEqual(data["s_monthsum_gb"], "1")
            self.assertEqual(data["s_measure"], "1")
            values = MONTHS[month]
            amounts = {code: self.kstat_amount_override.get((month, code), values[code])
                       for code in ("44", "43")}
            return Response(kstat_xml(amounts["44"], amounts["43"],
                                      omit_region=self.kstat_omit_region.get(month)),
                            "text/xml; charset=utf-8")
        if method == "POST" and url == watch.KCS_REGION_URL:
            # Optional Icheon HS6 is explicitly unavailable in this fixture.
            self.assertEqual(data["hsSgn"], watch.REGION_HS6)
            return Response(b'{"count":0,"searchPaging":"0","items":[]}', "application/json")
        if method != "GET" or url not in (
            watch.DATA_GO_ITEM_URL, watch.DATA_GO_SIDO_ITEM_URL, watch.DATA_GO_COUNTRY_ITEM_URL,
        ):
            raise AssertionError("unexpected fixture route: " + method + " " + url)
        month = params["strtYymm"]
        self.assertEqual(params["endYymm"], month)
        self.assertEqual(params["hsSgn"], HS)
        values = MONTHS[month]
        if url == watch.DATA_GO_ITEM_URL:
            row = {"year": month, "hsCode": HS, "expDlr": values["national"], "expWgt": values["kg"]}
        elif url == watch.DATA_GO_SIDO_ITEM_URL:
            raise AssertionError("regional HSK10 must use the exact K-stat request scope")
        else:
            self.assertEqual(params["cntyCd"], "MY")
            row = {"year": month, "hsCd": HS, "statCd": "MY", "statCdCntnKor1": "말레이시아",
                   "expDlr": values["MY"], "expWgt": values["MYkg"]}
        if self.row_mutator is not None:
            row = self.row_mutator(url, month, dict(params), row)
        return Response(api_xml(row))

    def prepared(self):
        official, errors = watch.fetch_official_hbm_pack(self.now)
        self.assertIsNotNone(official, errors)
        self.assertEqual(errors, [])
        proof, error = watch._resolve_sido_source()
        self.assertEqual(error, "")
        self.assertEqual(proof["status"], "official_kstat_request_scoped_source")
        self.assertIn(proof["month"], MONTHS)
        binding = watch._write_trade_validation(self.now, official, errors, True, RATE, FX_BASIS)
        candidate = {"monthly_due": True, "last_official_alert_snapshot": watch.official_snapshot(official),
                     "official_export_evidence": binding}
        text = watch.build_monthly(self.now, RATE, FX_BASIS, official)
        return official, candidate, text

    def read_documents(self):
        return (json.loads((self.out / "hbm_export_source_evidence.json").read_bytes()),
                json.loads((self.out / "hbm_export_validation.json").read_bytes()))

    def replace_documents_and_outer_binding(self, ledger, validation, candidate):
        """Leave internal raw-byte hashes alone to exercise their independent gate."""
        source_path = self.out / "hbm_export_source_evidence.json"
        validation_path = self.out / "hbm_export_validation.json"
        source_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
        validation["source_evidence_sha256"] = source_sha
        validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        candidate["official_export_evidence"].update(
            source_evidence_sha256=source_sha,
            validation_sha256=hashlib.sha256(validation_path.read_bytes()).hexdigest(),
        )

    def test_complete_preserved_core_annual_and_country_pack_passes_final_gate(self):
        official, candidate, text = self.prepared()
        self.assertEqual(set(official["series"]), set(MONTHS))
        for month, values in MONTHS.items():
            self.assertEqual(official["series"][month]["national_amount"], float(values["national"]))
            self.assertEqual(official["series"][month]["samsung_region_amount"], float(values["44"]))
            self.assertEqual(official["series"][month]["hynix_chungbuk_amount"], float(values["43"]))
            self.assertEqual(official["series"][month]["malaysia_amount"], float(values["MY"]))
        ledger, validation = self.read_documents()
        self.assertEqual(validation["phase"], "verified_core")
        for month in MONTHS:
            for role in ("national_hsk10", "samsung_chungnam", "hynix_chungbuk", "malaysia_hsk10"):
                attempt_id = validation["bindings"][month][role]
                attempt = next(a for a in ledger["attempts"] if a["attempt_id"] == attempt_id)
                self.assertTrue(attempt["response"]["raw_preserved"])
                self.assertEqual(attempt["selection"]["normalized"]["month"], month)
        # This is the production final gate, not a mocked approval result.
        self.assertIsNone(watch.validate_monthly_payload(text, candidate, self.out))

    def test_source_completion_after_midnight_preserves_decision_month_and_gate(self):
        official, candidate, _ = self.prepared()
        tz = ZoneInfo("Asia/Seoul")
        decision = datetime(2026, 10, 31, 23, 59, 20, tzinfo=tz)
        completed = datetime(2026, 11, 1, 0, 0, 31, tzinfo=tz)
        candidate["official_export_evidence"] = watch._write_trade_validation(
            decision, official, [], True, RATE, FX_BASIS, observed_at=completed
        )
        text = watch.build_monthly(decision, RATE, FX_BASIS, official, observed_at=completed)
        proof = json.loads((self.out / "hbm_export_validation.json").read_bytes())
        self.assertEqual(proof["decision_at_kst"], decision.isoformat(timespec="seconds"))
        self.assertEqual(proof["checked_at_kst"], completed.isoformat(timespec="seconds"))
        self.assertIn("<b>조회</b>: 2026-11-01 00:00 KST", text)
        self.assertIsNone(watch.validate_monthly_payload(text, candidate, self.out))

    def test_exact_kstat_request_scope_supplies_same_month_regional_usd_values(self):
        official, candidate, text = self.prepared()
        proof, error = watch._resolve_sido_source()
        self.assertEqual(error, "")
        self.assertEqual(proof["status"], "official_kstat_request_scoped_source")
        self.assertEqual(proof["factor_to_usd"], "1")
        self.assertEqual(official["month"], "202609")
        self.assertEqual(official["series"]["202609"]["samsung_region_amount"], 7_840_000_000)
        self.assertEqual(official["series"]["202608"]["samsung_region_amount"], 7_496_336_046)
        self.assertTrue(all("K-stat" in official["series"][m]["regional_sources"]["samsung_chungnam"]["source"]
                            for m in MONTHS))
        self.assertTrue(all("K-stat" in official["series"][m]["regional_sources"]["hynix_chungbuk"]["source"]
                            for m in MONTHS))
        self.assertEqual(candidate["last_official_alert_snapshot"]["month"], "202609")
        self.assertIn("2026년 9월", text)
        self.assertIn("K-stat 한국무역협회(제공기관: 관세청)", text)
        self.assertIn("응답 본문은 월·HS 코드를 회신하지 않아 요청 범위가 식별 근거입니다.", text)
        self.assertEqual(sum(url == reference.SHEET_URL for _, url, _, _ in self.calls), len(MONTHS))
        self.assertFalse(any(url == watch.DATA_GO_SIDO_ITEM_URL for _, url, _, _ in self.calls))
        self.assertIsNone(watch.validate_monthly_payload(text, candidate, self.out))

    def test_swapping_province_amounts_between_sections_is_rejected(self):
        _, candidate, text = self.prepared()
        first, second = watch._fmt_usd(7_840_000_000), watch._fmt_usd(2_800_000_000)
        lines = text.splitlines()
        targets = []
        for heading, old in (("[삼성전자 방향 — 충남]", first),
                              ("[SK하이닉스 관련 지역 — 충북]", second)):
            start = next(i for i, line in enumerate(lines) if heading in line)
            target = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("• HSK10"))
            self.assertIn(old, lines[target])
            targets.append(target)
        # Swap the complete USD/KRW amount lines so a global multiset of
        # correctly formatted source lines still agrees with the original.
        lines[targets[0]], lines[targets[1]] = lines[targets[1]], lines[targets[0]]
        changed = "\n".join(lines)
        self.assertIn(first, changed)
        self.assertIn(second, changed)
        # The comparison operands and direction lines remain correct; both
        # source amounts are still present elsewhere in the same payload.
        prefixes = ("• 비교월:", "• 변화:", "• 판정:")
        self.assertEqual([line for line in text.splitlines() if line.startswith(prefixes)],
                         [line for line in changed.splitlines() if line.startswith(prefixes)])
        with self.assertRaisesRegex(ValueError, "rendered section amount mismatch"):
            watch.validate_monthly_payload(changed, candidate, self.out)

    def test_tampered_candidate_evidence_binding_is_rejected(self):
        _, candidate, text = self.prepared()
        candidate["official_export_evidence"]["source_evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source evidence binding invalid"):
            watch.validate_monthly_payload(text, candidate, self.out)

    def test_tampered_source_document_is_rejected_before_replay(self):
        _, candidate, text = self.prepared()
        source_path = self.out / "hbm_export_source_evidence.json"
        source_path.write_bytes(source_path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "source evidence binding invalid"):
            watch.validate_monthly_payload(text, candidate, self.out)

    def test_internal_raw_hash_is_checked_even_after_outer_hashes_are_rebound(self):
        _, candidate, text = self.prepared()
        ledger, validation = self.read_documents()
        attempt_id = validation["bindings"]["202609"]["samsung_chungnam"]
        attempt = next(a for a in ledger["attempts"] if a["attempt_id"] == attempt_id)
        raw = base64.b64decode(attempt["response"]["raw_base64"])
        changed = raw.replace(b"7840000", b"9840000")
        self.assertNotEqual(raw, changed)
        attempt["response"]["raw_base64"] = base64.b64encode(changed).decode()
        self.replace_documents_and_outer_binding(ledger, validation, candidate)
        with self.assertRaisesRegex(ValueError, "response bytes/hash invalid"):
            watch.validate_monthly_payload(text, candidate, self.out)

    def test_current_raw_operands_are_replayed_against_snapshot(self):
        _, candidate, text = self.prepared()
        ledger, validation = self.read_documents()
        attempt_id = validation["bindings"]["202609"]["malaysia_hsk10"]
        attempt = next(a for a in ledger["attempts"] if a["attempt_id"] == attempt_id)
        changed = base64.b64decode(attempt["response"]["raw_base64"]).replace(b"1609624385", b"1609624386")
        attempt["response"].update(raw_base64=base64.b64encode(changed).decode(),
                                   raw_sha256=hashlib.sha256(changed).hexdigest(), raw_bytes_length=len(changed))
        self.replace_documents_and_outer_binding(ledger, validation, candidate)
        with self.assertRaisesRegex(ValueError, "exact response operands mismatch"):
            watch.validate_monthly_payload(text, candidate, self.out)

    def test_regional_series_never_mixes_data_go_and_kstat_amounts(self):
        self.kstat_amount_override[("202609", "44")] = "7000000000"
        official, _, _ = self.prepared()
        self.assertEqual(official["series"]["202609"]["samsung_region_amount"], 7_000_000_000)
        self.assertFalse(any(url == watch.DATA_GO_SIDO_ITEM_URL for _, url, _, _ in self.calls))

    def test_kstat_source_usd_values_are_never_scaled_by_amount_magnitude(self):
        self.kstat_amount_override[("202609", "44")] = "1"
        self.kstat_amount_override[("202609", "43")] = "1"
        row, error = watch.fetch_kstat_sido_month("202609", "44")
        self.assertEqual(error, "")
        self.assertEqual(row["raw_amount_decimal"], "1")
        self.assertEqual(row["amount_usd"], 1.0)

    def test_missing_current_province_row_holds_and_preserves_raw_response(self):
        self.kstat_omit_region["202609"] = "44"
        row, error = watch.fetch_kstat_sido_month("202609", "44")
        self.assertIsNone(row)
        self.assertIn("province_rows_missing", error)
        target = [a for a in self.ledger.as_dict()["attempts"]
                  if a["request"]["url"] == reference.SHEET_URL
                  and a["request"]["data"].get("s_year") == "2026"
                  and a["request"]["data"].get("s_month") == "09"]
        self.assertEqual(len(target), 1)
        self.assertTrue(target[0]["response"]["raw_preserved"])
        self.assertIn("202609", target[0]["request"]["data"]["s_year"] + target[0]["request"]["data"]["s_month"])


if __name__ == "__main__":
    unittest.main()

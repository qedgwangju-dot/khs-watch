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
        self.form = (FIXTURES / "hbm_kstat_province_form_20261016.html").read_bytes()
        self.sheet = (FIXTURES / "hbm_kstat_province_202608.xml").read_bytes()
        self.unit_raw_override = {}
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
        stack.enter_context(patch.object(watch, "_SIDO_UNIT_RESULT", None))
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
            self.assertEqual(data["s_month"], "08")
            self.assertEqual(data["s_monthsum_gb"], "1")
            self.assertEqual(data["s_measure"], "1")
            return Response(self.sheet, "text/xml; charset=utf-8")
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
            code = params["sidoCd"]
            amount = self.unit_raw_override.get(code) if month == "202608" else None
            if amount is None:
                amount = str(Decimal(values[code]) / Decimal(1000))
            row = {"priodTitle": month, "hsSgn": HS, "sidoCd": code, "expUsdAmt": amount}
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
        proof, error = watch._resolve_sido_unit()
        self.assertEqual(error, "")
        self.assertEqual(proof["month"], "202608")
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

    def test_reference_month_only_proves_unit_and_never_replaces_current_month(self):
        official, candidate, text = self.prepared()
        proof, error = watch._resolve_sido_unit()
        self.assertEqual(error, "")
        self.assertEqual(proof["factor_to_usd"], "1000")
        self.assertEqual(official["month"], "202609")
        self.assertEqual(official["series"]["202609"]["samsung_region_amount"], 7_840_000_000)
        self.assertNotEqual(official["series"]["202609"]["samsung_region_amount"], 7_496_336_046)
        self.assertEqual(candidate["last_official_alert_snapshot"]["month"], "202609")
        self.assertIn("2026년 9월", text)
        self.assertEqual(sum(url == reference.FORM_URL for _, url, _, _ in self.calls), 1)
        self.assertEqual(sum(url == reference.SHEET_URL for _, url, _, _ in self.calls), 1)
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

    def test_mismatched_reference_scale_holds_without_current_month_fetch(self):
        self.unit_raw_override["44"] = "7"
        proof, error = watch._resolve_sido_unit()
        self.assertIsNone(proof)
        self.assertIn("unit_cross_provider_mismatch", error)
        calls = len(self.calls)
        row, held = watch.fetch_data_go_sido_month("202609", "44")
        self.assertIsNone(row)
        self.assertEqual(held, error)
        self.assertEqual(len(self.calls), calls)
        binding = watch._write_trade_validation(self.now, None, [error], False, RATE, FX_BASIS)
        self.assertEqual(self.read_documents()[1]["phase"], "held")
        with self.assertRaisesRegex(ValueError, "source evidence binding invalid"):
            watch.validate_monthly_payload("삼성전자 vs SK하이닉스 HBM 수출 방향", {"monthly_due": True, "official_export_evidence": binding}, self.out)

    def test_ambiguous_reference_scale_is_held_instead_of_guessed(self):
        # Synthetic small-value variant deliberately makes both 1 and 1000
        # satisfy the tolerance; neither may become the operating contract.
        self.sheet = self.sheet.replace(b"7496336046", b"1").replace(b"1404330188", b"1")
        self.unit_raw_override = {"44": "1", "43": "1"}
        proof, error = watch._resolve_sido_unit()
        self.assertIsNone(proof)
        self.assertIn("unit_factor_not_unique", error)
        self.assertEqual(watch._SIDO_UNIT_RESULT, (None, error))

    def test_missing_current_response_identity_prevents_full_pack(self):
        def remove_month(url, month, params, row):
            if url == watch.DATA_GO_SIDO_ITEM_URL and month == "202609" and params["sidoCd"] == "44":
                row.pop("priodTitle")
            return row
        self.row_mutator = remove_month
        official, errors = watch.fetch_official_hbm_pack(self.now)
        self.assertIsNone(official)
        self.assertTrue(any("response_month_missing" in error for error in errors))
        target = [a for a in self.ledger.as_dict()["attempts"]
                  if a["request"]["url"] == watch.DATA_GO_SIDO_ITEM_URL
                  and a["request"]["params"].get("strtYymm") == "202609"
                  and a["request"]["params"].get("sidoCd") == "44"]
        self.assertEqual(len(target), 1)
        self.assertTrue(target[0]["response"]["raw_preserved"])
        self.assertEqual(target[0]["selection"]["status"], "invalid")
        self.assertIsNone(target[0]["selection"]["normalized"])


if __name__ == "__main__":
    unittest.main()

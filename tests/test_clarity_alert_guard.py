import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_alert_guard", ROOT / "scripts" / "clarity_alert_guard.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityAlertGuardTest(unittest.TestCase):
    def test_unrelated_pay_to_play_document_is_rejected(self):
        event = {
            "source": "SEC Federal Register 제안규칙",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "title": "Political Contributions by Certain Investment Advisers",
            "url": "https://www.federalregister.gov/documents/2026/09/10/2026-18424/political-contributions-by-certain-investment-advisers",
            "date": "2026-09-10",
            "detail": "",
        }
        meta = {
            "document_number": "2026-18424",
            "type": "Proposed Rule",
            "title": "Political Contributions by Certain Investment Advisers",
            "abstract": "The Securities and Exchange Commission is proposing to rescind rule 206(4)-5 under the Investment Advisers Act of 1940.",
            "publication_date": "2026-09-10",
            "html_url": event["url"],
        }
        with mock.patch.object(MOD, "fetch_json", return_value=meta):
            checked, reason = MOD.validate_federal_register_event(event)
        self.assertIsNone(checked)
        self.assertIn("irrelevant_federal_register_document", reason)

    def test_exact_json_xml_mods_urls_are_constructed(self):
        urls = MOD.source_urls("2026-18424", "2026-09-10", {})
        self.assertEqual(
            urls["json"],
            "https://www.federalregister.gov/api/v1/documents/2026-18424?publication_date=2026-09-10",
        )
        self.assertEqual(
            urls["xml"],
            "https://www.federalregister.gov/documents/full_text/xml/2026/09/10/2026-18424.xml",
        )
        self.assertEqual(
            urls["mods"],
            "https://www.govinfo.gov/metadata/granule/FR-2026-09-10/2026-18424/mods.xml",
        )

    def test_crypto_proposed_rule_is_kept_as_proposed_not_final_and_preserves_exact_sources(self):
        event = {
            "source": "SEC Federal Register 제안규칙",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "title": "Regulation Crypto Assets",
            "url": "https://www.federalregister.gov/documents/2026/09/20/2026-19999/regulation-crypto-assets",
            "date": "2026-09-20",
            "detail": "",
        }
        meta = {
            "document_number": "2026-19999",
            "type": "Proposed Rule",
            "title": "Regulation Crypto Assets",
            "abstract": "The Commission proposes a framework for certain investment contracts involving crypto assets.",
            "publication_date": "2026-09-20",
            "html_url": event["url"],
        }
        with mock.patch.object(MOD, "fetch_json", return_value=meta), mock.patch.object(MOD, "url_works", return_value=True):
            checked, reason = MOD.validate_federal_register_event(event)
        self.assertEqual(reason, "validated")
        self.assertEqual(checked["event_type"], "SEC·CFTC 제안규칙")
        self.assertEqual(checked["federal_register_type"], "Proposed Rule")
        self.assertEqual(
            checked["source_json_url"],
            "https://www.federalregister.gov/api/v1/documents/2026-19999?publication_date=2026-09-20",
        )
        self.assertEqual(
            checked["source_xml_url"],
            "https://www.federalregister.gov/documents/full_text/xml/2026/09/20/2026-19999.xml",
        )
        self.assertEqual(
            checked["source_mods_url"],
            "https://www.govinfo.gov/metadata/granule/FR-2026-09-20/2026-19999/mods.xml",
        )
        self.assertEqual(checked["source_link_kind"], "html")
        self.assertEqual(checked["source_checks"], {"json": True, "xml": True, "mods": True})

    def test_fallback_order_is_html_then_json_then_xml_then_mods(self):
        meta = {
            "html_url": "https://www.federalregister.gov/documents/2026/09/20/2026-19999/example",
            "publication_date": "2026-09-20",
        }
        results = {
            meta["html_url"]: False,
            "https://www.federalregister.gov/api/v1/documents/2026-19999?publication_date=2026-09-20": True,
            "https://www.federalregister.gov/documents/full_text/xml/2026/09/20/2026-19999.xml": True,
            "https://www.govinfo.gov/metadata/granule/FR-2026-09-20/2026-19999/mods.xml": True,
        }
        with mock.patch.object(MOD, "url_works", side_effect=lambda url: results.get(url, False)):
            url, kind, _ = MOD.best_authoritative_url(meta, "2026-19999", "2026-09-20")
        self.assertEqual(kind, "json")
        self.assertEqual(url, "https://www.federalregister.gov/api/v1/documents/2026-19999?publication_date=2026-09-20")


if __name__ == "__main__":
    unittest.main()

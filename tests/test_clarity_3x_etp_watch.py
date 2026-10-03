import importlib.util
import json
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_watch", ROOT / "scripts" / "clarity_watch.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class Clarity3xEtpWatchTest(unittest.TestCase):
    def test_recent_submission_rows_aligns_parallel_arrays(self):
        payload = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001", "0002"],
                    "filingDate": ["2026-08-17", "2026-10-05"],
                    "form": ["S-1", "EFFECT"],
                    "fileNumber": ["333-999999", "333-999999"],
                    "primaryDocument": ["s1.htm", "effect.xml"],
                    "primaryDocDescription": ["Registration Statement", "Notice of Effectiveness"],
                }
            }
        }
        rows = MOD.recent_submission_rows(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["form"], "EFFECT")
        self.assertEqual(rows[1]["fileNumber"], "333-999999")

    def test_effect_is_emitted_only_for_verified_bith_ethk_registration(self):
        payload = {
            "filings": {
                "recent": {
                    "accessionNumber": [
                        "0001213900-26-090839",
                        "0001213900-26-120000",
                    ],
                    "filingDate": ["2026-08-17", "2026-10-05"],
                    "form": ["S-1", "EFFECT"],
                    "fileNumber": ["333-999999", "333-999999"],
                    "primaryDocument": ["s1.htm", "effect.xml"],
                    "primaryDocDescription": ["Registration Statement", "Notice of Effectiveness"],
                }
            }
        }

        def fake_fetch(url, timeout=30):
            if url == MOD.VS_TRUST_SUBMISSIONS_URL:
                return json.dumps(payload).encode("utf-8")
            if url.endswith("/s1.htm"):
                return b"<html><body>VS Trust BITH 3x Bitcoin ETF ETHK 3x Ether ETF</body></html>"
            if url.endswith("/effect.xml"):
                return b"<effectiveDate>20261005</effectiveDate>"
            raise AssertionError(url)

        errors = []
        with patch.object(MOD, "fetch", side_effect=fake_fetch):
            events = MOD.collect_vs_trust_3x_registration_milestones(errors)

        effect = [e for e in events if "등록 효력 발생" in e.event_type]
        self.assertEqual(len(effect), 1)
        self.assertEqual(effect[0].date, "2026-10-05")
        self.assertIn("Form EFFECT", effect[0].detail)
        self.assertEqual(errors, [])

    def test_sec_archives_fallback_can_verify_s1_and_effect_when_data_sec_blocks(self):
        root_payload = {
            "directory": {
                "item": [
                    {"name": "000121390026120000", "type": "dir", "last-modified": "2026-10-05 12:00:00"},
                    {"name": "000121390026090839", "type": "dir", "last-modified": "2026-08-17 12:00:00"},
                ]
            }
        }
        s1_index = """
        <html><body>
        Filing Type S-1 Filing Date 2026-08-17 File Number 333-999999
        <table><tr><td>S-1</td><td><a href="s1.htm">s1.htm</a></td></tr></table>
        </body></html>
        """
        effect_index = """
        <html><body>
        Filing Type EFFECT Filing Date 2026-10-05 File Number 333-999999
        <table><tr><td>EFFECT</td><td><a href="primary_doc.xml">primary_doc.xml</a></td></tr></table>
        </body></html>
        """

        def fake_fetch(url, timeout=30):
            if url == MOD.VS_TRUST_SUBMISSIONS_URL:
                raise RuntimeError("403")
            if url == MOD.VS_TRUST_ARCHIVE_INDEX_URL:
                return json.dumps(root_payload).encode("utf-8")
            if url.endswith("0001213900-26-090839-index.html"):
                return s1_index.encode("utf-8")
            if url.endswith("0001213900-26-120000-index.html"):
                return effect_index.encode("utf-8")
            if url.endswith("/s1.htm"):
                return b"<html><body>VS Trust BITH 3x Bitcoin ETF ETHK 3x Ether ETF</body></html>"
            if url.endswith("/primary_doc.xml"):
                return b"<effectiveDate>20261005</effectiveDate>"
            raise AssertionError(url)

        errors = []
        with patch.object(MOD, "fetch", side_effect=fake_fetch):
            events = MOD.collect_vs_trust_3x_registration_milestones(errors)

        effect = [e for e in events if "등록 효력 발생" in e.event_type]
        self.assertEqual(len(effect), 1)
        self.assertEqual(effect[0].date, "2026-10-05")
        self.assertTrue(any("VS Trust SEC submissions" in e for e in errors))

    def test_final_prospectus_is_separate_launch_readiness_event(self):
        payload = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001213900-26-130000"],
                    "filingDate": ["2026-10-06"],
                    "form": ["424B3"],
                    "fileNumber": ["333-999999"],
                    "primaryDocument": ["prospectus.htm"],
                    "primaryDocDescription": ["Prospectus"],
                }
            }
        }

        def fake_fetch(url, timeout=30):
            if url == MOD.VS_TRUST_SUBMISSIONS_URL:
                return json.dumps(payload).encode("utf-8")
            if url.endswith("/prospectus.htm"):
                return b"<html><body>VS Trust BITH 3x Bitcoin ETF ETHK 3x Ether ETF</body></html>"
            raise AssertionError(url)

        errors = []
        with patch.object(MOD, "fetch", side_effect=fake_fetch):
            events = MOD.collect_vs_trust_3x_registration_milestones(errors)

        prospectus = [e for e in events if "최종 투자설명서" in e.event_type]
        self.assertEqual(len(prospectus), 1)
        self.assertEqual(prospectus[0].date, "2026-10-06")
        self.assertIn("Form 424B3", prospectus[0].detail)


if __name__ == "__main__":
    unittest.main()

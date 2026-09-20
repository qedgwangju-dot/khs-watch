import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

WATCH_SPEC = importlib.util.spec_from_file_location(
    "clarity_watch", ROOT / "scripts" / "clarity_watch.py"
)
WATCH = importlib.util.module_from_spec(WATCH_SPEC)
WATCH_SPEC.loader.exec_module(WATCH)

FORMAT_SPEC = importlib.util.spec_from_file_location(
    "clarity_alert_formatter", ROOT / "scripts" / "clarity_alert_formatter.py"
)
FORMAT = importlib.util.module_from_spec(FORMAT_SPEC)
FORMAT_SPEC.loader.exec_module(FORMAT)


class ClarityReginfoWatchTest(unittest.TestCase):
    def test_parse_cftc_oira_prerule_card(self):
        sample = (
            "AGENCY: CFTC RIN: 3038-AF80 Status: Pending Review "
            "TITLE:Regulation Crypto Asset Transactions and Regulation Crypto Asset Markets "
            "STAGE: Prerule Economically Significant: "
            "This term refers to a regulatory action under E.O. 12866 No "
            "** RECEIVED DATE: 09/17/2026 LEGAL DEADLINE: None"
        )
        rows = WATCH.parse_reginfo_review_text(sample)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["rin"], "3038-AF80")
        self.assertEqual(row["status"], "Pending Review")
        self.assertEqual(row["stage"], "Prerule")
        self.assertEqual(row["economically_significant"], "No")
        self.assertEqual(row["received_date"], "09/17/2026")
        self.assertEqual(row["legal_deadline"], "None")
        self.assertIn("Crypto Asset Transactions", row["title"])

    def test_oira_prerule_alert_does_not_call_it_proposed_or_final(self):
        event = {
            "source": "OIRA/RegInfo — CFTC",
            "event_type": "CFTC OIRA 규제검토 — Prerule",
            "title": "Regulation Crypto Asset Transactions and Regulation Crypto Asset Markets",
            "url": "https://www.reginfo.gov/public/do/eoReviewSearch?agencyCode=3038",
            "date": "09/17/2026",
            "detail": "RIN 3038-AF80 | Status: Pending Review | Stage: Prerule | Economically Significant: No | Legal Deadline: None",
        }
        rendered = "\n".join(FORMAT.build_chunks([event]))
        self.assertIn("RIN 3038-AF80", rendered)
        self.assertIn("Pending Review", rendered)
        self.assertIn("Prerule", rendered)
        self.assertIn("아직 Prerule이고 규칙 본문이 공개되지 않았으며", rendered)
        self.assertIn("규칙 본문도 비공개", rendered)
        self.assertNotIn("이 문서는 제안규칙입니다", rendered)
        self.assertNotIn("이번 조치는 최종규칙으로", rendered)


if __name__ == "__main__":
    unittest.main()

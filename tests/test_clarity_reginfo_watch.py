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
        self.assertIn("Pending Review(검토 중)", rendered)
        self.assertIn("Prerule(사전규칙 단계)", rendered)
        self.assertIn("아직 Prerule(사전규칙 단계)이고 규칙 본문이 공개되지 않았으며", rendered)
        self.assertIn("규칙 본문도 비공개", rendered)
        self.assertNotIn("이 문서는 제안규칙입니다", rendered)
        self.assertNotIn("이번 조치는 최종규칙으로", rendered)


    def test_nested_layout_table_does_not_mix_an66_with_an48(self):
        html = """
        <table><tr><td><table>
        <tr><td>11/25/2026</td><td><a href="/public/do/eoDetails?rrid=1610112">3235-AN66</a></td><td>3235-SEC</td><td>Amendments to Investment Adviser Recordkeeping Rule</td><td>Pending Review</td><td></td><td></td></tr>
        <tr><td>11/03/2026</td><td><a href="/public/do/eoDetails?rrid=1571318">3235-AN48</a></td><td>3235-SEC</td><td>Amendments to Broker-Dealer Financial Responsibility and Recordkeeping and Reporting Rules Regarding Crypto Assets</td><td>Pending Review</td><td></td><td></td></tr>
        </table></td></tr></table>
        """
        rows = WATCH.parse_reginfo_table_rows(WATCH.BeautifulSoup(html, "html.parser"))
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["rin"] for r in rows if WATCH.reginfo_relevant(r["title"])], ["3235-AN48"])
        self.assertEqual(rows[1]["received_date"], "11/03/2026")
        self.assertEqual(rows[1]["detail_url"], "https://www.reginfo.gov/public/do/eoDetails?rrid=1571318")

    def test_incomplete_card_cannot_borrow_next_records_date(self):
        sample = (
            "AGENCY: SEC RIN: 3235-AN48 Status: Pending Review TITLE: Crypto Assets "
            "STAGE: Proposed Rule Economically Significant: Yes "
            "AGENCY: SEC RIN: 3235-AN66 Status: Pending Review TITLE: Investment Adviser Recordkeeping "
            "STAGE: Proposed Rule Economically Significant: Yes RECEIVED DATE: 11/25/2026 LEGAL DEADLINE: None"
        )
        rows = WATCH.parse_reginfo_review_text(sample)
        self.assertEqual([r["rin"] for r in rows], ["3235-AN66"])

    def test_direct_detail_must_match_all_review_fields(self):
        page = """
        <h1>Pending EO 12866 Regulatory Review</h1>
        <div>RIN: 3235-AN48 View EO 12866 Meetings Received Date: 11/03/2026</div>
        <div>Title: Amendments to Broker-Dealer Financial Responsibility and Recordkeeping and Reporting Rules Regarding Crypto Assets</div>
        <div>Agency/Subagency: SEC Stage: Proposed Rule Legal Deadline: None Economically Significant: Yes</div>
        """
        record = WATCH.parse_reginfo_detail(WATCH.BeautifulSoup(page, "html.parser"))
        row = dict(record)
        self.assertTrue(WATCH.reginfo_source_match(row, record, "SEC", "3235"))
        for field, wrong in (("rin", "3235-AN66"), ("received_date", "11/25/2026"), ("title", "Other rule"),
                             ("status", "Concluded"), ("stage", "Final Rule")):
            self.assertFalse(WATCH.reginfo_source_match(dict(row, **{field: wrong}), record, "SEC", "3235"))

    def test_verified_review_has_stable_identity_and_legacy_alias(self):
        source = "OIRA/RegInfo — SEC"
        title = "Amendments to Broker-Dealer Financial Responsibility and Recordkeeping and Reporting Rules Regarding Crypto Assets"
        old = WATCH.Event(source, "SEC OIRA 규제검토 — OIRA review", title,
            "https://www.reginfo.gov/public/Forward?Image61.x=0&Image61.y=0&SearchTarget=RegReview&textfield=3235",
            "11/03/2026", "RIN 3235-AN48 | Status: Pending Review | Stage: OIRA review")
        new = WATCH.Event(source, "SEC OIRA 규제검토 — Proposed Rule", title,
            "https://www.reginfo.gov/public/do/eoDetails?rrid=1571318", "11/03/2026",
            "RIN 3235-AN48 | Status: Pending Review | Stage: Proposed Rule | Received Date: 11/03/2026 | Verified EO review: Yes")
        keys, aliases = WATCH.reginfo_event_keys(new)
        self.assertIn(old.key, aliases)
        changed = WATCH.Event(new.source, new.event_type, new.title, new.url, new.date,
                             new.detail.replace("Verified EO review: Yes", "Legal Deadline: None | Verified EO review: Yes"))
        self.assertTrue(keys.intersection(WATCH.reginfo_event_keys(changed)[0]))
        concluded = WATCH.Event(new.source, new.event_type, new.title, new.url, "11/25/2026",
            new.detail.replace("Pending Review", "Concluded").replace("Verified EO review: Yes", "Concluded Date: 11/25/2026 | Verified EO review: Yes"))
        self.assertFalse(keys.intersection(WATCH.reginfo_event_keys(concluded)[0]))

    def test_an48_rendering_retains_identity_on_translation_failure(self):
        from unittest import mock
        event = {"source": "OIRA/RegInfo — SEC", "event_type": "SEC OIRA 규제검토 — Proposed Rule",
                 "title": "Amendments to Broker-Dealer Financial Responsibility and Recordkeeping and Reporting Rules Regarding Crypto Assets",
                 "url": "https://www.reginfo.gov/public/do/eoDetails?rrid=1571318", "date": "11/03/2026",
                 "detail": "RIN 3235-AN48 | Status: Pending Review | Stage: Proposed Rule | Received Date: 11/03/2026 | Economically Significant: Yes | Legal Deadline: None | Verified EO review: Yes"}
        with mock.patch.object(FORMAT, "translate_ko", return_value=""):
            title, body = FORMAT.localize_event(event)
            output = "\n".join([title, body, FORMAT.easy_meaning(event, body), *FORMAT.investment_lines(event)])
        self.assertIn("3235-AN48", output)
        self.assertIn("증권중개업자", output)
        self.assertIn("2026년 11월 3일", output)
        self.assertIn("검토 중", output)
        self.assertNotIn("제안규칙을 공개했습니다", output)
        self.assertNotIn("상원 표결", output)

    def test_af80_conclusion_is_not_rendered_as_old_pending_review(self):
        event = {"source": "OIRA/RegInfo — CFTC", "event_type": "CFTC OIRA 규제검토 — Prerule",
                 "title": "Regulation Crypto Asset Transactions and Regulation Crypto Asset Markets",
                 "date": "10/02/2026",
                 "detail": "RIN 3038-AF80 | Status: Concluded | Stage: Prerule | Received Date: 09/17/2026 | Concluded Date: 10/02/2026 | Concluded Action: Consistent with Change | Verified EO review: Yes"}
        title, body = FORMAT.localize_event(event)
        self.assertIn("검토 종료", title)
        self.assertIn("2026년 10월 2일", body)
        self.assertIn("수정 후 적합", body)
        self.assertNotIn("검토 중", title)


if __name__ == "__main__":
    unittest.main()

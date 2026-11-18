import datetime as dt
import html
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import khs_ndaa_ai_policy as watch

NOW = dt.datetime(2026, 11, 18, 15, tzinfo=ZoneInfo("Asia/Seoul"))
RASA = watch.BILL_SPECS[0]
NDAA = watch.BILL_SPECS[-2]
BASELINE = """<h1>Chairmen Mast, Moolenaar, and Crawford Send Second Request to
Jensen Huang and NVIDIA to Brief Congress on the Chinese Intelligence Asset</h1>
<time>November 12, 2026</time><p>This situation is a prime example of why Congress
must immediately pass the AI OVERWATCH Act, Chip Security Act, MATCH Act, and
Remote Access Security Act in the NDAA.</p>"""


def status_xml(spec=RASA, date="2026-11-16", action="Passed House.", code="H37100",
               title="Remote Access Security Act", extra="", version="", update="2026-11-17"):
    return f"""<billStatus><bill><congress>119</congress><type>{spec.bill_type.upper()}</type>
    <number>{spec.number}</number><title>{html.escape(title)}</title><updateDate>{update}</updateDate>
    <latestAction><actionDate>{date}</actionDate><text>{html.escape(action)}</text></latestAction>
    <actions><item><actionDate>{date}</actionDate><actionCode>{code}</actionCode>
    <sourceSystem><name>House floor actions</name></sourceSystem><text>{html.escape(action)}</text>
    </item></actions>{extra}{version}</bill></billStatus>"""


def collect_fixture(raw, spec=RASA):
    def fetch(url, timeout):
        assert timeout == 8
        return BASELINE if url == watch.BASELINE_URL else raw
    with patch.object(watch, "BILL_SPECS", (spec,)):
        return watch.collect_ndaa_items(NOW, fetch)


class NdaaPolicyTests(unittest.TestCase):
    def test_baseline_is_urging_not_enactment(self):
        item = watch.baseline_item(BASELINE, NOW)
        self.assertEqual(item["ndaa_event_key"], "package-urged-2026-11-12")
        self.assertIn("촉구", item["ndaa_profile"]["stage"])
        self.assertIn("제정 확인 아님", item["ndaa_profile"]["stage"])
        self.assertIsNone(watch.classify_action("Congress must immediately pass these bills in the NDAA."))

    def test_baseline_requires_all_four_bills_and_exact_date(self):
        for old, new in (("Remote Access Security Act", "another bill"),
                         ("November 12, 2026", "November 12, 2025"),
                         ("must immediately pass", "has now passed")):
            with self.assertRaises(ValueError):
                watch.baseline_item(BASELINE.replace(old, new), NOW)

    def test_baseline_does_not_assert_chip_hardware_or_gps_mandate(self):
        text = " ".join(watch.baseline_item(BASELINE, NOW)["ndaa_profile"]["actual_bullets"])
        self.assertNotIn("GPS 의무", text)
        self.assertIn("일률적 의무화로 단정하지 않습니다", text)

    def test_submission_does_not_equal_adoption(self):
        self.assertEqual(watch.classify_action("Amendment SA 6683 submitted and ordered to lie on the table."), "amendment-submitted")
        self.assertEqual(watch.classify_action("Amendment SA 6683 agreed to in Senate."), "amendment-adopted")
        self.assertIsNone(watch.classify_action("Amendment SA 6683 not agreed to."))

    def test_an_act_and_enacting_clause_do_not_prove_enactment(self):
        doc = watch.parse_bill_status(status_xml(action="Referred to the Senate Committee.", code="", title="AN ACT",
            extra="<summaries><text>Be it enacted by the Senate and House</text></summaries>"), RASA, NOW)
        self.assertEqual(doc["action"]["stage"], "committee-referred")
        self.assertIsNone(watch.classify_action("Be it enacted by the Senate and House of Representatives"))

    def test_wrong_bill_and_nested_related_bill_cannot_contaminate(self):
        with self.assertRaises(ValueError):
            watch.parse_bill_status(status_xml(spec=NDAA), RASA, NOW)
        nested = "<relatedBills><item><actions><item><actionDate>2026-11-18</actionDate><text>Became Public Law No: 119-999.</text></item></actions></item></relatedBills>"
        doc = watch.parse_bill_status(status_xml(extra=nested), RASA, NOW)
        self.assertEqual(doc["action"]["stage"], "passed-house")

    def test_same_action_key_survives_metadata_update_and_late_text(self):
        first = collect_fixture(status_xml())
        later = collect_fixture(status_xml(update="2026-11-18",
            version="<textVersions><item><type>Engrossed in House</type><date>2026-11-16T05:00:00Z</date></item></textVersions>"))
        self.assertEqual(first[0]["ndaa_event_key"], later[0]["ndaa_event_key"])

    def test_new_stage_has_independent_key(self):
        before = collect_fixture(status_xml())[0]
        after = collect_fixture(status_xml(date="2026-11-17", action="Passed Senate.", code=""))[0]
        self.assertNotEqual(before["ndaa_event_key"], after["ndaa_event_key"])

    def test_explicit_law_number_required_for_became_law(self):
        self.assertEqual(watch.classify_action("Became Public Law No: 119-123."), "enacted")
        self.assertIsNone(watch.classify_action("Became Public Law"))
        item = collect_fixture(status_xml(action="Became Public Law No: 119-123."))[0]
        self.assertIn("119-123", item["ndaa_event_key"])
        self.assertIn("조항별 시행", " ".join(item["ndaa_profile"]["actual_bullets"]))

    def test_old_actions_not_replayed_and_future_actions_rejected(self):
        old = watch.parse_bill_status(status_xml(date="2026-01-13"), RASA, NOW)
        self.assertIsNone(old["action"])
        with self.assertRaisesRegex(ValueError, "future"):
            watch.parse_bill_status(status_xml(date="2026-11-19"), RASA, NOW)
        self.assertIsNone(watch.baseline_item(BASELINE, NOW - dt.timedelta(days=8)))
        self.assertIsNone(watch.baseline_item(BASELINE, NOW + dt.timedelta(days=22)))

    def test_http_and_identity_failures_are_visible_not_no_change(self):
        def fail(url, timeout):
            raise TimeoutError("probe timeout")
        with patch.object(watch, "BILL_SPECS", (RASA,)):
            self.assertEqual(watch.collect_ndaa_items(NOW, fail), [])
        failures = watch.get_source_failures()
        self.assertEqual(len(failures), 2)
        self.assertIn("TimeoutError", failures[0]["error"])
        collect_fixture(status_xml(spec=NDAA))
        self.assertIn("identity mismatch", watch.get_source_failures()[0]["error"])

    def test_ndaa_passage_without_body_does_not_claim_package_inclusion(self):
        item = collect_fixture(status_xml(spec=NDAA), NDAA)[0]
        self.assertEqual(item["ndaa_included_topics"], [])
        self.assertIn("편입 확정 아님", item["ndaa_profile"]["scope_note"])
        self.assertIn("모두 포함됐다고 판단하지 않습니다", " ".join(item["ndaa_profile"]["actual_bullets"]))

    def test_body_requires_operative_short_title_not_contents_or_reference(self):
        self.assertEqual(watch._inclusion("<bill><toc>Chip Security Act</toc><section><text>Congress should pass the MATCH Act.</text></section></bill>"), [])
        raw = '<bill><section><header>Short title</header><text>This subtitle may be cited as the “Chip Security Act”.</text></section></bill>'
        self.assertEqual(watch._inclusion(raw), ["chip_security"])

    def test_body_identity_and_failed_reads_preserve_inclusion_uncertainty(self):
        raw = '<bill><form><congress>119th CONGRESS</congress><legis-num>H. R. 2683</legis-num></form><section><text>This subtitle may be cited as the “Chip Security Act”.</text></section></bill>'
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            watch._inclusion(raw, NDAA)
        with self.assertRaisesRegex(ValueError, "not an official"):
            watch._inclusion('<html><body>Access denied</body></html>')
        url = 'https://www.govinfo.gov/content/pkg/BILLS-119hr8800eh/xml/BILLS-119hr8800eh.xml'
        doc = watch.parse_bill_status(status_xml(spec=NDAA), NDAA, NOW)
        doc['versions'] = [{'type': 'Engrossed in House', 'date': '2026-11-16', 'urls': [url]}]
        def fail(url, timeout):
            raise TimeoutError('body fetch timeout')
        item, failure = watch._action_item(doc, fail)
        self.assertEqual(item['ndaa_included_topics'], [])
        self.assertIn('조회 실패', item['ndaa_profile']['scope_note'])
        self.assertIn('TimeoutError', failure['error'])

    def test_body_short_title_check_does_not_upgrade_legislative_stage(self):
        url = 'https://www.govinfo.gov/content/pkg/BILLS-119hr8800eh/xml/BILLS-119hr8800eh.xml'
        doc = watch.parse_bill_status(status_xml(spec=NDAA), NDAA, NOW)
        doc['versions'] = [{'type': 'Engrossed in House', 'date': '2026-11-16', 'urls': [url]}]
        raw = '<bill><form><congress>119th CONGRESS</congress><legis-num>H. R. 8800</legis-num></form><section><text>This subtitle may be cited as the “Chip Security Act”.</text></section></bill>'
        item, failure = watch._action_item(doc, lambda url, timeout: raw)
        self.assertIsNone(failure)
        self.assertEqual(item['ndaa_stage'], 'passed-house')
        self.assertEqual(item['ndaa_included_topics'], ['chip_security'])
        self.assertIn('하원 통과본', item['ndaa_profile']['scope_note'])

    def test_unrelated_ndaa_amendments_are_excluded(self):
        doc = watch.parse_bill_status(status_xml(spec=NDAA, action="Amendment SA 9999 agreed to in Senate."), NDAA, NOW)
        self.assertIsNone(doc["action"])
        doc = watch.parse_bill_status(status_xml(spec=NDAA, action="Amendment SA 6683 submitted in Senate."), NDAA, NOW)
        self.assertEqual(doc["action"]["stage"], "amendment-submitted")

    def test_cloture_and_failed_passage_do_not_become_passage(self):
        self.assertEqual(watch.classify_action("Cloture motion on the motion to proceed not invoked in Senate by Yea-Nay Vote. 50 - 46."), "cloture-failed")
        self.assertEqual(watch.classify_action("On passage Failed by the Yeas and Nays: 210 - 220."), "passage-failed")
        self.assertEqual(watch.classify_action("Ordered to be Reported in the Nature of a Substitute by the Yeas and Nays: 42 - 0."), "committee-approved")

    def test_correct_bulk_endpoint_and_bounded_workers(self):
        self.assertTrue(RASA.url.endswith("/BILLSTATUS-119hr2683.xml"))
        with patch.object(watch, "ThreadPoolExecutor", wraps=watch.ThreadPoolExecutor) as executor:
            collect_fixture(status_xml())
        executor.assert_called_once_with(max_workers=4)


if __name__ == "__main__":
    unittest.main()

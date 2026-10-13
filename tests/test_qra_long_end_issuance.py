"""Offline guards for existing QRA's long-bond supply and dealer-question lane."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import qra_long_end_issuance as issuance
import qra_recurring_alert as qra


def sample_table():
    rows=[
        ("Aug-26",16,25),("Sep-26",13,22),("Oct-26",13,22),
        ("Nov-26",13,22),("Dec-26",10,19),("Jan-27",10,19)
    ]
    return "<table><tr><th></th><th>20-Year</th><th>30-Year</th></tr>"+ "".join(
        f"<tr><td>{month}</td><td>{a}</td><td>{b}</td></tr>"
        for month,a,b in rows
    )+"</table>"


class TreasuryLongEndQraTests(unittest.TestCase):
    def test_monthly_20y_30y_table_and_18b_reallocation(self):
        table=issuance.nominal_long_end_table(sample_table())
        self.assertEqual(table["2026-08"]["20y"],16.0)
        self.assertEqual(table["2027-01"]["30y"],19.0)
        compared=issuance.summarize_long_end_supply(table,fx=1341.49)
        self.assertTrue(compared["available"])
        self.assertEqual(compared["before_bn"],111)
        self.assertEqual(compared["after_bn"],93)
        self.assertEqual(compared["delta_bn"],-18)
        self.assertTrue(compared["citi_base_case_matches"])
        label=issuance.expectation_comparison(compared)
        self.assertIn("1,110억달러",label)
        self.assertIn("930억달러",label)
        self.assertIn("-180억달러",label)
        self.assertIn("24조",label)

    def test_six_months_are_required(self):
        data=issuance.nominal_long_end_table(sample_table())
        self.assertFalse(issuance.summarize_long_end_supply(dict(list(data.items())[:5]))["available"])
        broken=dict(data); del broken["2026-10"]
        self.assertFalse(issuance.summarize_long_end_supply(broken)["available"])

    def test_dealer_release_time_is_separate_from_qra(self):
        parser=qra.ReleaseParser()
        parser.feed("""
        <h3>DOCUMENTS RELEASED at 12:00 PM Friday, October 16, 2026</h3>
        <a href="/agenda.pdf">Primary Dealer Meeting Agenda: 2026 - 4th Quarter</a>
        <h3>DOCUMENTS RELEASED at 8:30 AM Wednesday, August 5, 2026</h3>
        <a href="/policy">Policy Statement: 2026 - 3rd Quarter</a>""")
        self.assertEqual(len(parser.sections),2)
        ordered=sorted(parser.sections,key=qra.section_date_key,reverse=True)
        self.assertIn("October 16",ordered[0].heading)
        self.assertEqual(qra.section_date_key(ordered[0]),("2026-10-16",12))

    def test_dealer_document_must_have_long_end_question(self):
        self.assertFalse(issuance.dealer_agenda_mentions_long_end(
            "Welcome primary dealers. Discussion of cash management." ))
        self.assertFalse(issuance.dealer_agenda_mentions_long_end(
            "The 20-year and 30-year securities are listed on the routine meeting agenda." ))
        self.assertFalse(issuance.dealer_agenda_mentions_long_end(
            "A routine 20-year Treasury security was mentioned. "
            + ("Unrelated administrative matters. " * 50)
            + "The auction size for short-dated bills may change." ))
        self.assertTrue(issuance.dealer_agenda_mentions_long_end(
            "Should Treasury reduce the size of 20-year bond auctions?" ))
        official=qra.ReleaseSection(
            heading="DOCUMENTS RELEASED at 12:00 PM Friday, October 16, 2026",
            links=[qra.LinkItem("Primary Dealer Meeting Agenda", "https://home.treasury.gov/a.pdf")],
        )
        with patch.object(qra,"official_dealer_document_text",return_value="General policy agenda only"):
            self.assertIsNone(qra.build_dealer_survey_alert(official))
        with patch.object(qra,"official_dealer_document_text",
                          return_value="20-year bonds and hyperscaler corporate issuance"):
            title,body,detail=qra.build_dealer_survey_alert(official)
        self.assertIn("장기국채 공급 검토",title)
        self.assertIn("결정이 아닙니다",body)
        self.assertEqual(detail["decision_status"],"survey_not_final_policy")

    def test_second_dealer_document_is_examined_if_first_not_relevant(self):
        agenda=qra.ReleaseSection(
            heading="DOCUMENTS RELEASED at 12:00 PM Friday, October 16, 2026",
            links=[
                qra.LinkItem("Primary Dealer Meeting Agenda","https://home.treasury.gov/agenda.pdf"),
                qra.LinkItem("Primary Dealer Auction Size Survey","https://home.treasury.gov/survey.pdf"),
            ],
        )
        def read(link):
            if link.url.endswith("agenda.pdf"):
                return "Routine non-market opening agenda."
            return "Is investor demand for 20-year bonds affected by hyperscaler issuance?"
        with patch.object(qra,"official_dealer_document_text",side_effect=read):
            title,body,detail=qra.build_dealer_survey_alert(agenda)
        self.assertIn("장기국채",title)
        self.assertEqual(detail["official_url"],"https://home.treasury.gov/survey.pdf")

    def test_scenario_is_not_a_government_announcement(self):
        compared=issuance.summarize_long_end_supply(
            issuance.nominal_long_end_table(sample_table()))
        self.assertTrue(compared["available"])
        self.assertNotIn("재무부 확정",issuance.expectation_comparison(compared))
        self.assertTrue(issuance.CITI_20261009.startswith("https://www.bloomberg.com"))

if __name__=="__main__":
    unittest.main()

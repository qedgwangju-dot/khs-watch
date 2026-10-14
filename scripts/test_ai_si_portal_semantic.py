#!/usr/bin/env python3
"""Regression tests for official SI.gov link discovery and silent baselines."""
from __future__ import annotations
import datetime as dt
import unittest
from ai_si_portal_semantic import canonical_url, extract_portal_links, advance_portal_state, category_for_link

BASE = """<!doctype html><html><body><main>
<h1>Super Intelligence</h1><p>Genesis Mission, Data Center Infrastructure, American SI Stack</p>
<a href="/initiatives/education">SI Education</a>
<a href="/initiatives/presidential-challenge">Presidential SI Challenge</a>
<a href="https://www.whitehouse.gov/presidential-actions/2025/11/genesis-mission/">Genesis Mission</a>
</main></body></html>"""


class Tests(unittest.TestCase):
    def setUp(self):
        self.t0 = dt.datetime(2026,10,14,4,0,tzinfo=dt.timezone.utc)

    def test_authority_and_no_external_links(self):
        self.assertIsNone(canonical_url("https://example.com/initiatives/fake"))
        self.assertIsNone(canonical_url("javascript:alert(1)"))
        self.assertIsNone(canonical_url("https://www.si.gov.attacker.example/initiatives/fake"))
        self.assertEqual(
            canonical_url("https://si.gov/initiatives/education?ref=menu"),
            "https://www.si.gov/initiatives/education",
        )

    def test_page_baseline_and_layout_noise(self):
        links = extract_portal_links(BASE)
        self.assertEqual(len(links),3)
        noisy = BASE.replace("Genesis Mission, Data", "Genesis Mission, Data").replace(
            "<main>","<main><span>12,987 visitors</span>"
        )
        self.assertEqual(extract_portal_links(noisy),links)
        with self.assertRaises(ValueError):
            extract_portal_links("<html><h1>New discounts</h1></html>")

    def test_two_observations_and_no_duplicate(self):
        links = extract_portal_links(BASE)
        state,found = advance_portal_state(None,links,self.t0)
        self.assertEqual(found,[])
        new_url = "https://www.whitehouse.gov/fact-sheets/2026/10/new-si-investment/"
        links2=dict(links)
        links2[new_url]="New SI Investment"
        state,found=advance_portal_state(state,links2,self.t0+dt.timedelta(minutes=1))
        self.assertEqual(found,[])
        self.assertEqual(len(state["candidates"]),1)
        state,found=advance_portal_state(state,links2,self.t0+dt.timedelta(minutes=12))
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["category"],"SI 공식 정책·사업 문서 변화")
        state,found=advance_portal_state(state,links2,self.t0+dt.timedelta(minutes=20))
        self.assertEqual(found,[])

    def test_disappearance_does_not_signal_or_reset(self):
        links=extract_portal_links(BASE)
        state,_=advance_portal_state(None,links,self.t0)
        new_url="https://www.si.gov/initiatives/energy-grid"
        later={**links,new_url:"Data Center Infrastructure"}
        state,found=advance_portal_state(state,later,self.t0+dt.timedelta(minutes=1))
        self.assertFalse(found)
        state,found=advance_portal_state(state,links,self.t0+dt.timedelta(minutes=4))
        self.assertFalse(found)
        state,found=advance_portal_state(state,later,self.t0+dt.timedelta(minutes=12))
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["category"],"SI 데이터센터·전력·인허가 변화")

    def test_categorization(self):
        self.assertEqual(category_for_link("https://www.si.gov/initiatives/american-si-stack","Exports"),"SI 기술 생태계·해외 수출 변화")
        self.assertEqual(category_for_link("https://www.si.gov/initiatives/presidential-challenge","Challenge"),"SI 교육·인재 육성 변화")
        self.assertEqual(category_for_link("https://www.si.gov/initiatives/energy-grid","Data Center"),"SI 데이터센터·전력·인허가 변화")


if __name__=="__main__":
    unittest.main(verbosity=2)

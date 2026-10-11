#!/usr/bin/env python3
"""Regression tests: prevent Apple M8 server and HBM procurement false positives."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo

import apple_enterprise_server_memory_watch as w

KST = ZoneInfo("Asia/Seoul")
PUB = "2026-10-11T13:00:00+09:00"

def item(title, publisher="Reuters", description="", published=PUB):
    return {
        "title": title,
        "source": publisher,
        "source_url": "",
        "link": "https://example.com/article/" + str(abs(hash((title,publisher)))),
        "description": description,
        "published": published,
    }

def state():
    return {
        "schema_version": 2,
        "baseline_at_utc": "2026-09-16T13:45:00+00:00",
        "seen": [], "seen_event_keys": list(w.BASELINE_KEYS),
        "observations": [], "metrics": {},
    }

class AppleServerWatchTests(unittest.TestCase):

    def test_original_reuters_information_story_is_baseline_not_new(self):
        row = item("Apple considers return to server market with Nvidia NVLink Fusion",
                   description="Apple plans 2 or 4 M8 Ultra chips for a 2029 enterprise server, according to The Information.")
        self.assertEqual(w.classify(row), [])

    def test_publisher_date_is_not_new_launch_target(self):
        row = item("Apple M8 Ultra enterprise server plans 2029 launch; report 2026",
                   description="The 2026 article describes the planned 2029 server launch.")
        self.assertEqual(w.classify(row), [])

    def test_new_launch_delay_2030_is_detected(self):
        row = item("Apple M8 Ultra enterprise server delayed until 2030")
        result = w.classify(row)
        self.assertIn("schedule:2030", [e["key"] for e in result])

    def test_nvidia_nvhbm_other_customer_not_apple_order(self):
        row = item("NVIDIA NVLink Fusion NVHBM announced for Amazon's Annapurna Labs",
                   "NVIDIA Blog", "Apple mac demand rises in other news")
        self.assertEqual(w.classify(row), [])

    def test_apple_nvlink_talks_not_equated_adoption(self):
        row = item("Apple M8 Ultra enterprise server in talks to use Nvidia NVLink Fusion")
        self.assertEqual(w.classify(row), [])

    def test_apple_nvlink_adoption_report_is_not_hbm_order(self):
        row = item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion")
        result = w.classify(row)
        self.assertIn("nvlink:reported-adoption", [e["key"] for e in result])
        self.assertFalse(any(e["kind"] == "memory-order" for e in result))

    def test_mobile_dram_contract_not_server_hbm(self):
        row = item("Apple accepted Samsung mobile LPDDR5X DRAM price for iPhone")
        self.assertEqual(w.classify(row), [])

    def test_real_order_worded_with_named_supplier_is_candidate_not_confirmed(self):
        row = item("Apple placed an order for Micron HBM4 for its M8 Ultra enterprise server")
        result = w.classify(row)
        self.assertIn("memory-order:Micron:HBM", [e["key"] for e in result])
        self.assertIn("원문", result[0]["caution"])

    def test_speculative_memory_buy_not_an_order(self):
        row = item("Analysts: Apple may order Micron HBM4 for M8 Ultra enterprise server")
        self.assertEqual(w.classify(row), [])

    def test_internal_private_cloud_server_doesnt_trigger(self):
        row = item("Apple ships Private Cloud Compute servers from Houston factory")
        self.assertEqual(w.classify(row), [])

    def test_apple_insider_is_not_apple_official(self):
        self.assertEqual(w.source_tier("Apple Insider", "https://appleinsider.com"), "기타매체")
        self.assertEqual(w.source_tier("Apple", "https://www.apple.com/newsroom"), "회사발표색인")

    def test_copy_of_the_information_cannot_corroborate_original(self):
        original=item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion",
                      "The Information", description="Exclusive enterprise M8 server report.")
        copied=item("Nvidia's NVLink Fusion adopted by Apple M8 Ultra enterprise server",
                    "Reuters", description="The Information reports Apple has adopted technology.")
        self.assertEqual(w.origin_family(original), w.origin_family(copied))
        events, nextstate = w.process([original,copied],state())
        self.assertEqual(len(events),1)  # high-grade first report still alerts; 2 copies not 2 confirmations
        self.assertIn("원보도 계열 1곳", events[0]["significance"])

    def test_duplicate_story_same_claim_one_alert(self):
        first=item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion",
                   "Reuters")
        later=item("Apple server based on M8 Ultra has adopted Nvidia NVLink Fusion",
                   "The Information")
        found, stored=w.process([first,later],state())
        self.assertEqual(len(found),1)
        again,_=w.process([first,later],stored)
        self.assertEqual(again,[])

    def test_one_low_grade_unverified_story_suppressed(self):
        low=item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion",
                 "UnverifiedBlog")
        found,stored=w.process([low],state())
        self.assertEqual(found,[])
        self.assertEqual(stored["seen_event_keys"],sorted(set(w.BASELINE_KEYS)))

    def test_low_grade_many_reprints_without_primary_suppressed(self):
        a=item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion","UnverifiedA")
        b=item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion","UnverifiedB")
        found,_=w.process([a,b],state())
        self.assertEqual(found,[])

    def test_late_primary_corrob_of_suppressed_report(self):
        low=item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion","MacRumors")
        first,s1=w.process([low],state())
        self.assertEqual(first,[])
        high=item("Apple M8 Ultra enterprise server has adopted Nvidia NVLink Fusion","Reuters",
                  description="Separate reporting.")
        next_events,_=w.process([high],s1)
        self.assertEqual(len(next_events),1)

    def test_old_news_with_new_pub_after_baseline_doesnt_trigger(self):
        old=item("Apple M8 Ultra server project planned for 2029 with NVLink Fusion in talks",
                 "Reuters",published="2026-09-15T12:00:00+09:00")
        found,_=w.process([old],state())
        self.assertEqual(found,[])

    def test_apple_server_cancel_positive_and_mere_risk_negative(self):
        self.assertTrue(any(x["key"]=="project:canceled" for x in
                            w.classify(item("Apple canceled its M8 Ultra server project"))))
        self.assertFalse(w.classify(item("Apple M8 Ultra enterprise server could still be canceled")))

    def test_monthly_year_2027_without_release_change_is_not_schedule(self):
        row=item("Apple M8 Ultra enterprise server projected to use 2027 memory pricing")
        self.assertEqual(w.classify(row),[])

if __name__ == "__main__":
    unittest.main(verbosity=2)

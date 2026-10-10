"""Offline regression checks for the existing QRA workflow's fiscal-policy lane."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime

from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import treasury_fiscal_plan_watch as watch


class FiscalPolicyTests(unittest.TestCase):
    def test_debt_is_403_not_41_on_oct8(self):
        x = {
            "data": [{
                "record_date": "2026-10-08",
                "tot_pub_debt_out_amt": "40305316210829.72",
                "debt_held_public_amt": "32454086117711.20",
                "intragov_hold_amt": "7851230093118.52",
            }],
        }
        d = watch.parse_debt(x)
        self.assertLess(int(float(d["total"]) // 1_000_000_000_000), 41)
        self.assertEqual(d["record_date"], "2026-10-08")

    def test_debt_components_must_add_up(self):
        raw = {"data": [{
            "record_date": "2026-10-08",
            "tot_pub_debt_out_amt": "41000000000000.00",
            "debt_held_public_amt": "33000000000000.00",
            "intragov_hold_amt": "7000000000000.00",
        }]}
        with self.assertRaises(ValueError):
            watch.parse_debt(raw)

    def test_41_trillion_threshold(self):
        self.assertEqual(int(41_000_000_000_000 // 1_000_000_000_000), 41)
        self.assertEqual(int(40_999_999_999_999 // 1_000_000_000_000), 40)

    def test_official_only_links(self):
        html_text = """
        <a href="https://home.treasury.gov/news/press-releases/sb1234">
          U.S. Federal Deficit Reduction Plan
        </a>
        <a href="https://news.example.org/politics/fiscal-plan">
          Federal Deficit Reduction Plan
        </a>
        """
        r = watch.official_plan_links({watch.SOURCE_INDEXES[0]: html_text})
        self.assertEqual(len(r), 1)
        self.assertIn("home.treasury.gov", r[0][1])

    def test_global_navigation_does_not_count_as_press_release(self):
        nav = '<a href="/about/budget-financial-reporting-planning-and-performance/">Budget and Finance</a>'
        urls = watch.official_plan_links({watch.SOURCE_INDEXES[0]: nav})
        self.assertEqual(urls, [])

    def test_past_generic_budget_never_triggers(self):
        html_page = '''
        <meta property="article:published_time" content="2026-06-01T09:00:00Z">
        <h1>U.S. Federal Fiscal Consolidation Plan</h1>
        <p>United States Treasury released a federal deficit reduction plan.</p>
        '''
        self.assertIsNone(watch.classify_plan("Federal Fiscal Consolidation Plan", html_page,
                           "https://home.treasury.gov/news/press-releases/sb8888"))

    def test_future_only_interview_not_adopted_plan(self):
        future = '''
        <script type="application/ld+json">{"datePublished":"2026-10-10T00:00:00Z"}</script>
        <article>The United States federal government is working on a
        fiscal consolidation plan and will unveil the deficit reduction plan
        right after the midterms.</article>
        '''
        self.assertIsNone(watch.classify_plan("Fiscal consolidation plan expected", future,
                            "https://home.treasury.gov/news/press-releases/sb8889"))

    def test_official_published_plan_produces_discovery(self):
        fresh = '''
        <script type="application/ld+json">{"datePublished":"2026-11-06T16:00:00Z"}</script>
        <h1>U.S. Treasury announces Federal Deficit Reduction Plan</h1>
        <p>Today the United States Treasury released its federal fiscal consolidation
        plan to reduce the deficit over five years. New details explain spending cuts.
        </p>
        '''
        x = watch.classify_plan("Federal Deficit Reduction Plan", fresh,
            "https://home.treasury.gov/news/press-releases/sb9999")
        self.assertIsNotNone(x)
        self.assertEqual(x["published_date"], "2026-11-06")
        self.assertEqual(x["stage"], "공식안 공개(입법·집행 전)")

    def test_foreign_debt_plan_not_ours(self):
        page = '''
        <script>{"datePublished":"2026-11-06"}</script>
        <p>Republic of Kenya announced a fiscal consolidation plan for Kenya.
        Its ministers will reduce its debt.</p>
        '''
        self.assertIsNone(watch.classify_plan("Kenya fiscal consolidation plan", page,
                           "https://home.treasury.gov/news/press-releases/sb9998"))

    def test_fiscal_state_merge_keeps_newest_and_deduplicates(self):
        from treasury_fiscal_plan_state_commit import merge_state
        remote = {"seen_events":["old"],"last_event_id":"old",
                  "last_sent_at_kst":"2026-11-07T10:00:00+09:00"}
        stale = {"seen_events":["new"],"last_event_id":"new",
                 "last_sent_at_kst":"2026-11-06T10:00:00+09:00"}
        merged = merge_state(remote,stale)
        self.assertEqual(merged["last_event_id"],"old")
        self.assertEqual(merged["seen_events"],["old","new"])

    def test_currency_scale(self):
        from decimal import Decimal
        v = Decimal("41000000000000")
        self.assertIn("경", watch.fmt_krw(v, Decimal("1341.49")))


if __name__ == "__main__":
    unittest.main()

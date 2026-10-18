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
        second = watch.classify_plan(
            "President releases Federal Deficit Reduction Plan", fresh,
            "https://www.whitehouse.gov/releases/2026/11/fiscal-plan/"
        )
        self.assertEqual(x["id"], second["id"])

        self.assertEqual(x["stage"], "공식 재정계획 문서 공개(입법·집행 여부 별도 확인)")

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


    def _budget_fixture(self, missing: str | None = None):
        from datetime import date, timedelta
        records = []
        for fy, total_deficit_m in ((2025, 1775000), (2026, 1993000)):
            for index in range(12):
                month = 10 + index
                year = fy - 1
                if month > 12:
                    month -= 12
                    year = fy
                end = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
                deficit_m = total_deficit_m // 12 + (total_deficit_m % 12 if index == 11 else 0)
                receipts_m = 450000 if fy == 2026 else 436000
                values = {
                    "Receipts": receipts_m,
                    "Outlays": receipts_m + deficit_m,
                    "Deficit/Surplus (-)": deficit_m,
                }
                for name, value in values.items():
                    if missing == end.isoformat() + "|" + name:
                        continue
                    records.append({
                        "record_date": end.isoformat(), "record_fiscal_year": str(fy),
                        "amt_category": name, "mil_amt": str(value),
                    })
        return {"data": records, "meta": {"total-pages": 1}}

    def test_official_mts_ytd_and_prior_year_are_distinct(self):
        from datetime import date
        from decimal import Decimal
        result = watch.parse_mts_budget(self._budget_fixture(), date(2026, 10, 18))
        self.assertEqual(result["record_date"], "2026-09-30")
        self.assertEqual(result["months_elapsed"], 12)
        self.assertEqual(Decimal(result["current"]["deficit"]), Decimal("1993000000000"))
        self.assertEqual(Decimal(result["previous"]["deficit"]), Decimal("1775000000000"))
        self.assertEqual(Decimal(result["current"]["receipts"]), Decimal("5400000000000"))

    def test_mts_missing_prior_month_fails_closed(self):
        from datetime import date
        with self.assertRaises(ValueError):
            watch.parse_mts_budget(self._budget_fixture("2025-06-30|Outlays"), date(2026, 10, 18))

    def test_mts_conflicting_revisions_fail_closed(self):
        from datetime import date
        fixture = self._budget_fixture()
        duplicate = dict(fixture["data"][-1])
        duplicate["mil_amt"] = "99999999"
        fixture["data"].append(duplicate)
        with self.assertRaises(ValueError):
            watch.parse_mts_budget(fixture, date(2026, 10, 18))

    def test_mts_ignores_future_month_and_checks_freshness(self):
        from datetime import date
        fixture = self._budget_fixture()
        for category in ("Receipts", "Outlays", "Deficit/Surplus (-)"):
            fixture["data"].append({
                "record_date": "2026-10-31", "record_fiscal_year": "2027",
                "amt_category": category, "mil_amt": "900",
            })
        result = watch.parse_mts_budget(fixture, date(2026, 10, 18))
        self.assertEqual(result["record_date"], "2026-09-30")
        with self.assertRaises(ValueError):
            watch.parse_mts_budget(fixture, date(2027, 3, 5))

    def test_tariff_refunds_not_additional_to_net_revenue(self):
        from decimal import Decimal
        payload = {"data": [{
            "record_date": "2026-09-30", "classification_desc": "Customs Duties",
            "current_fytd_gross_rcpt_amt": "318000000000",
            "current_fytd_refund_amt": "145000000000",
            "current_fytd_net_rcpt_amt": "173000000000",
        }]}
        v = watch.parse_mts_tariffs(payload, "2026-09-30")
        self.assertEqual(Decimal(v["gross"]) - Decimal(v["refund"]), Decimal(v["net"]))
        payload["data"][0]["current_fytd_net_rcpt_amt"] = "318000000000"
        with self.assertRaises(ValueError):
            watch.parse_mts_tariffs(payload, "2026-09-30")

    def test_budget_korean_message_separates_cash_flow_and_qra(self):
        from datetime import date
        from decimal import Decimal
        budget = watch.parse_mts_budget(self._budget_fixture(), date(2026, 10, 18))
        title, message = watch.report_mts_budget(
            budget,
            {"gross": "318000000000", "refund": "145000000000", "net": "173000000000"},
            "1100000000000", Decimal("1332.10"), "ECB 2026-10-16",
        )
        self.assertIn("1조9930억달러", message)
        self.assertIn("관세 환급", message)
        self.assertIn("순이자 지출", message)
        self.assertIn("국채", message)
        self.assertIn("재정적자", title)
        self.assertIn("원", message)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import date
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from us_positioning_delivery import daily_digest_due, daily_event_label, parse_aaii_allocation, parse_conference_board_confidence, evaluate_retail_crowding, update_retail_survey_overlay, AAII_ALLOCATIONS_URL, BOARD_CONFIDENCE_URL, AAII_OFFICIAL_ARCHIVE, parse_aaii_monthly_article, aaii_latest_official_article_links, fetch_current_aaii_allocation


class DailyDigestDeliveryTests(unittest.TestCase):
    def test_daily_digest_is_due_when_no_delivery_was_recorded(self):
        self.assertTrue(daily_digest_due({}, date(2026, 10, 24)))

    def test_retry_does_not_send_twice_on_the_same_korea_date(self):
        state = {"daily_digest_sent_date_kst": "2026-10-24"}
        self.assertFalse(daily_digest_due(state, date(2026, 10, 24)))
        self.assertTrue(daily_digest_due(state, date(2026, 10, 25)))

    def test_unchanged_daily_digest_is_not_mislabeled_as_new(self):
        self.assertEqual(daily_event_label([]), "일일 정기 현황")

    def test_daily_digest_labels_new_changes_and_corrections(self):
        self.assertEqual(
            daily_event_label([{"source": "SOX"}]),
            "일일 정기 현황 · 신규 변화",
        )
        self.assertEqual(
            daily_event_label([{"source": "SOX"}], correction=True),
            "일일 정기 현황 · 정정·보강",
        )


AAII_SAMPLE = ("Asset Allocation Results for September 2026 : Current percentage "
    "Stock Funds Image 38.35% (+0.73%) Stocks Image 33.44% (0.00%) "
    "Stocks Total 71.79% Bonds Image 5.74% Bond Funds Image 9.13% "
    "Bonds Total 14.87% Cash Image 13.35% (-0.95%)")
CB_SAMPLE = ("US Consumer Confidence Increased in October Latest Press Release "
    "Updated: Tuesday, October 27, 2026 "
    "The Conference Board Consumer Confidence Index® rose by 7.5 points "
    "to 91.7 (1985=100) in October, up from 84.2 in September. "
    "The Expectations Index recovered by 6.9 points to 72.6. "
    "Overall, more consumers in October expected stock prices to increase "
    "rather than decrease in the next 12 months.")

class RetailSentimentSurveyTests(unittest.TestCase):
    def snapshots(self):
        return parse_aaii_allocation(AAII_SAMPLE), parse_conference_board_confidence(CB_SAMPLE)

    def test_aaii_monthly_allocation_checksum(self):
        a, b = self.snapshots()
        self.assertEqual(a["period"], "2026-09")
        self.assertAlmostEqual(a["stocks_pct"], 71.79)
        self.assertAlmostEqual(a["cash_pct"], 13.35)
        self.assertAlmostEqual(a["direct_stock_pct"] + a["stock_funds_pct"], a["stocks_pct"])

    def test_cb_index_and_qualitative_equity_expectation_separate(self):
        a,b = self.snapshots()
        self.assertEqual(b["period"], "2026-10")
        self.assertAlmostEqual(b["confidence_index"], 91.7)
        self.assertAlmostEqual(b["expectations_index"], 72.6)
        self.assertIs(b["stock_up_vs_down_majority"], True)
        self.assertNotIn("stock_up_pct", b)

    def test_aaii_wrong_components_or_weekly_survey_rejected(self):
        with self.assertRaises(ValueError):
            parse_aaii_allocation(AAII_SAMPLE.replace("Stocks Total 71.79%", "Stocks Total 81.79%"))
        with self.assertRaises(ValueError):
            parse_aaii_allocation("AAII weekly bullish sentiment 71.79%")

    def test_cb_missing_stock_direction_remains_unknown(self):
        text=CB_SAMPLE.replace(
            "more consumers in October expected stock prices to increase rather than decrease",
            "stock data not published")
        b=parse_conference_board_confidence(text)
        self.assertIsNone(b["stock_up_vs_down_majority"])

    def test_first_month_is_silent_baseline_and_second_new_month_once(self):
        a,b = self.snapshots()
        first=evaluate_retail_crowding({},a,b,"2026-10-28")
        self.assertTrue(first["baseline"])
        self.assertFalse(first["alert"])
        self.assertEqual(first["state"]["regime"],"동반 높은 주식노출·상승기대")
        next_a={**a,"period":"2026-10","stocks_pct":72.0,"cash_pct":13.0}
        second=evaluate_retail_crowding(first["state"],next_a,b,"2026-11-02")
        self.assertTrue(second["alert"])
        self.assertFalse(evaluate_retail_crowding(second["state"],next_a,b,"2026-11-02")["alert"])

    def test_month_rollback_and_future_date_fail_closed(self):
        a,b = self.snapshots()
        first=evaluate_retail_crowding({},a,b,"2026-10-28")["state"]
        with self.assertRaisesRegex(ValueError,"rolled back"):
            evaluate_retail_crowding(first,{**a,"period":"2026-08"},b,"2026-10-28")
        with self.assertRaisesRegex(ValueError,"stale or future"):
            evaluate_retail_crowding(first,a,b,"2026-10-25")

    def test_no_shares_numeric_is_invented_and_missing_cb_no_alert(self):
        a,b = self.snapshots()
        result=evaluate_retail_crowding({},a,{**b,"stock_up_vs_down_majority":None},"2026-10-28")
        self.assertFalse(result["alert"])
        self.assertIn("확인 대기", result["state"]["regime"])




class RetailMonthlyOverlayRouteTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "out").mkdir()
        self.saved = self.root / "data" / "us_fund_flow_state.json"
        self.pending = self.root / "out" / "us_fund_flow_pending_state.json"
        self.alert = self.root / "out" / "us_fund_flow_alert.html"
        self.original = {"seen":{"ICI|mmf":"already-delivered"}, "values":{"ICI|mmf":{"period":"October 21, 2026"}},
                         "derived":{"hartnett_10y_pct":5.0}}
        self.saved.write_text(__import__("json").dumps(self.original), encoding="utf-8")

    def fetch(self, url):
        if url == AAII_ALLOCATIONS_URL:
            return AAII_SAMPLE
        if url == BOARD_CONFIDENCE_URL:
            return CB_SAMPLE
        raise AssertionError("unexpected source URL")

    def test_first_month_baselines_silently_without_erasing_other_state(self):
        result = update_retail_survey_overlay(
            repo_root=self.root, fetch=self.fetch, on_date=date(2026, 10, 28))
        self.assertEqual(result["status"], "baseline_saved")
        self.assertFalse(result["telegram_sent"])
        self.assertFalse(self.alert.exists())
        data = __import__("json").loads(self.pending.read_text())
        self.assertEqual(data["seen"], self.original["seen"])
        self.assertEqual(data["derived"]["hartnett_10y_pct"], 5.0)
        self.assertEqual(data["derived"]["retail_survey"]["pair"], "2026-09|2026-10")

    def test_following_month_can_emit_single_dated_existing_route_alert(self):
        update_retail_survey_overlay(repo_root=self.root, fetch=self.fetch, on_date=date(2026,10,28))
        self.saved.write_text(self.pending.read_text(encoding="utf-8"), encoding="utf-8")
        self.pending.unlink()
        def next_month(url):
            page = self.fetch(url)
            return page.replace("Results for September 2026", "Results for October 2026")
        result=update_retail_survey_overlay(
            repo_root=self.root, fetch=next_month, on_date=date(2026,11,2))
        self.assertEqual(result["status"], "alert_ready")
        alert = self.alert.read_text()
        self.assertIn("AAII 2026-10", alert)
        self.assertIn("2026-10", alert)
        self.assertIn("기준월", alert)
        self.assertIn(AAII_ALLOCATIONS_URL, alert)
        self.assertIn(BOARD_CONFIDENCE_URL, alert)
        self.saved.write_text(self.pending.read_text(encoding="utf-8"), encoding="utf-8")
        self.pending.unlink()
        self.alert.unlink()
        again=update_retail_survey_overlay(
            repo_root=self.root, fetch=next_month, on_date=date(2026,11,2))
        self.assertEqual(again["status"], "unchanged")
        self.assertFalse(self.alert.exists())

    def test_primary_source_failure_cannot_advance_pending_or_alert(self):
        result=update_retail_survey_overlay(
            repo_root=self.root,
            fetch=lambda url: (_ for _ in ()).throw(TimeoutError("official source offline")),
            on_date=date(2026,10,28))
        self.assertEqual(result["status"], "source_withheld")
        self.assertFalse(self.pending.exists())
        self.assertFalse(self.alert.exists())
        self.assertEqual(__import__("json").loads(self.saved.read_text()), self.original)



AAII_ARTICLE_PUBLIC = (
    "September AAII Asset Allocation Survey: Cash Allocations Fall "
    "by AAII Staff | October 01, 2026 "
    "Individual investors' allocations to cash decreased. "
    "September AAII Asset Allocation Survey results: "
    "Stocks and Stock Funds: 71.8%, up 0.7 percentage points "
    "Bonds and Bond Funds: 14.9%, up 0.2 percentage points "
    "Cash: 13.3%, down 1.0 percentage points "
    "September AAII Asset Allocation Details: "
    "Stocks: 33.4%, down 0.0 percentage points "
    "Stocks Funds: 38.3%, up 0.7 percentage points "
    "Bonds: 5.7% Bond Funds: 9.1%"
)
AAII_MAIN_WITH_LINK = (
    '<html><body><h2>Asset Allocation Survey</h2>'
    '<a href="/latest/article/548658-september-aaii-asset-allocation-survey-cash-allocations-fall">'
    'September AAII Asset Allocation Survey: Cash Allocations Fall</a>'
    '</body></html>'
)


class AAIIPrimaryArticleRecoveryTests(unittest.TestCase):
    def test_article_keeps_one_decimal_precision_and_month_year(self):
        data = parse_aaii_monthly_article(AAII_ARTICLE_PUBLIC)
        self.assertEqual(data["period"], "2026-09")
        self.assertEqual(data["stocks_pct"], 71.8)
        self.assertEqual(data["cash_pct"], 13.3)
        self.assertIn("소수 첫째", data["source_precision"])

    def test_dynamic_overview_link_resolves_aaaii_only(self):
        links = aaii_latest_official_article_links(
            AAII_MAIN_WITH_LINK
            + '<a href="https://evil.example/latest/article/12-steal">September AAII Asset Allocation Survey: Fake</a>')
        self.assertEqual(links, [
            "https://www.aaii.com/latest/article/548658-september-aaii-asset-allocation-survey-cash-allocations-fall"
        ])

    def test_live_style_page_without_table_uses_verified_official_article(self):
        requests = []
        url = "https://www.aaii.com/latest/article/548658-september-aaii-asset-allocation-survey-cash-allocations-fall"
        def fetch(request):
            requests.append(request)
            if request == AAII_ALLOCATIONS_URL:
                return AAII_MAIN_WITH_LINK
            if request == url:
                return AAII_ARTICLE_PUBLIC
            raise AssertionError("Unnecessary fallback archive request")
        data=fetch_current_aaii_allocation(fetch,date(2026,10,28))
        self.assertEqual(data["period"],"2026-09")
        self.assertEqual(data["source_url"],url)
        self.assertEqual(len(requests),2)

    def test_old_official_article_must_not_be_called_current(self):
        old = AAII_ARTICLE_PUBLIC.replace("September 2026","July 2026").replace(
            "September AAII Asset Allocation","July AAII Asset Allocation").replace(
            "October 01, 2026","August 01, 2026")
        # An old official link is found but cannot qualify as a fresh basis.
        url = "https://www.aaii.com/latest/article/548658-september-aaii-asset-allocation-survey-cash-allocations-fall"
        def fetch(req):
            if req == AAII_ALLOCATIONS_URL or req == AAII_OFFICIAL_ARCHIVE:
                return AAII_MAIN_WITH_LINK
            if req == url:
                return old
            raise AssertionError(req)
        with self.assertRaisesRegex(ValueError,"unavailable"):
            fetch_current_aaii_allocation(fetch,date(2026,10,28))

    def test_article_bad_total_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"totals"):
            parse_aaii_monthly_article(
                AAII_ARTICLE_PUBLIC.replace("Stocks and Stock Funds: 71.8%", "Stocks and Stock Funds: 78.8%"))


if __name__ == "__main__":
    unittest.main()

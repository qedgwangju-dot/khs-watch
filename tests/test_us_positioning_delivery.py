import unittest
from datetime import date
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from us_positioning_delivery import daily_digest_due, daily_event_label, parse_aaii_allocation, parse_conference_board_confidence, evaluate_retail_crowding


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


if __name__ == "__main__":
    unittest.main()

import unittest

from global_rates_freshness_guard import apply_guard, annotate_report


class GlobalRatesFreshnessGuardTest(unittest.TestCase):
    def base(self):
        pending = {
            "last_values": {"jgb2": 1.719, "ust2": 4.34, "us_jp_2y_spread": 2.621, "usdjpy": 159.97, "usdjpy_daily_change_pct": 0.45},
            "last_source_dates": {"jgb2": "2026/8/28", "ust2": "2026-08-31", "usdjpy": "2026-08-28"},
            "active": {"us_jp_2y_spread:below:2.0": False, "usdjpy:below:155.0": False, "usdjpy:daily_change:below:-2.0": False},
        }
        alert = {"events": [{"metric": "us_jp_2y_spread", "type": "trigger"}, {"metric": "usdjpy", "type": "trigger"}, {"metric": "ust10", "type": "trigger"}]}
        return pending, alert

    def live(self):
        return {"price": 158.25, "change_pct": -0.60, "timestamp_epoch": 1788238800.0, "timestamp_utc": "2026-09-01T09:00:00Z", "age_seconds": 45.0, "source": "Yahoo query1/query2 5분 데이터 교차확인"}

    def test_mismatched_2y_dates_are_not_compared(self):
        pending, alert = self.base()
        pending, alert, freshness = apply_guard(pending, alert, live_fx=self.live())
        self.assertIsNone(pending["last_values"]["us_jp_2y_spread"])
        self.assertFalse(freshness["same_2y_date"])
        self.assertEqual([e["metric"] for e in alert["events"]], ["ust10"])

    def test_live_fx_replaces_daily_fred_for_current_signal(self):
        pending, alert = self.base()
        pending, alert, freshness = apply_guard(pending, alert, live_fx=self.live())
        self.assertTrue(freshness["live_fx_signal_eligible"])
        self.assertEqual(pending["last_values"]["usdjpy"], 158.25)
        self.assertEqual(freshness["fred_usdjpy_reference"], 159.97)

    def test_live_fx_failure_does_not_reuse_fred_as_current(self):
        pending, alert = self.base()
        pending, alert, freshness = apply_guard(pending, alert, live_fx=None, live_fx_error="timeout")
        self.assertFalse(freshness["live_fx_signal_eligible"])
        self.assertIsNone(pending["last_values"]["usdjpy"])
        self.assertEqual(freshness["fred_usdjpy_reference"], 159.97)

    def test_non_zero_padded_dates_are_supported(self):
        pending, alert = self.base()
        pending["last_source_dates"]["jgb2"] = "2026/8/31"
        pending["last_source_dates"]["ust2"] = "2026-08-31"
        _, _, freshness = apply_guard(pending, alert, live_fx=self.live())
        self.assertTrue(freshness["same_2y_date"])

    def test_report_explains_withheld_spread(self):
        text = "[글로벌 금리·엔캐리 경보] 🟢\n판정: 관찰\n조회: 2026-09-01 18:05:00 KST\n\n⬜ 미·일 2Y 금리차 축소: 확인 불가\n⬜ 엔화 급등: 확인 불가\n"
        freshness = {"same_2y_date": False, "jgb2_date": "2026/8/28", "ust2_date": "2026-08-31", "live_fx_signal_eligible": True, "live_fx_price": 158.25, "live_fx_change_pct": -0.60, "live_fx_timestamp_utc": "2026-09-01T09:00:00Z", "live_fx_age_seconds": 45.0}
        out = annotate_report(text, freshness)
        self.assertIn("기준일 불일치 — 계산 보류", out)
        self.assertIn("USD/JPY 158.250", out)
        self.assertIn("query1/query2 5분 교차확인", out)


if __name__ == "__main__":
    unittest.main()

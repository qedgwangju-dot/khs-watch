import unittest

from global_rates_freshness_guard import (
    annotate_report,
    apply_guard,
    calculate_final_risk,
    classify_live_fx,
)


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

    def test_price_below_155_is_level_not_yen_surge(self):
        fx = classify_live_fx(154.269, 0.42)
        self.assertTrue(fx["strong_level"])
        self.assertFalse(fx["surge"])
        self.assertEqual(fx["direction"], "엔화 약세")

    def test_directional_drop_triggers_yen_surge(self):
        fx = classify_live_fx(154.269, -2.10)
        self.assertTrue(fx["strong_level"])
        self.assertTrue(fx["surge"])
        self.assertEqual(fx["direction"], "엔화 강세")

    def test_false_level_signal_cannot_promote_risk_to_orange(self):
        level, label, emoji, leading, confirm = calculate_final_risk({
            "jgb10_3": False,
            "jgb_curve_up": True,
            "us_jp_2y_spread_narrow": False,
            "us_2y_down": False,
            "yen_surge": False,
            "vix_spike": False,
            "nikkei_nasdaq_joint_weakness": False,
        })
        self.assertEqual(level, 0)
        self.assertEqual(label, "관찰")
        self.assertEqual(emoji, "🟢")
        self.assertEqual(leading, 1)
        self.assertEqual(confirm, 0)

    def test_real_yen_surge_plus_curve_promotes_risk_to_orange(self):
        level, label, _, leading, _ = calculate_final_risk({
            "jgb10_3": False,
            "jgb_curve_up": True,
            "us_jp_2y_spread_narrow": False,
            "us_2y_down": False,
            "yen_surge": True,
            "vix_spike": False,
            "nikkei_nasdaq_joint_weakness": False,
        })
        self.assertEqual(level, 2)
        self.assertEqual(label, "엔캐리 청산 경계 강화")
        self.assertEqual(leading, 2)

    def test_report_explains_withheld_spread(self):
        text = "[글로벌 금리·엔캐리 경보] 🟢\n판정: 관찰\n조회: 2026-09-01 18:05:00 KST\n\n⬜ 미·일 2Y 금리차 축소: 확인 불가\n⬜ 엔화 급등: 확인 불가\n"
        freshness = {"same_2y_date": False, "jgb2_date": "2026/8/28", "ust2_date": "2026-08-31", "live_fx_signal_eligible": True, "live_fx_price": 158.25, "live_fx_change_pct": -0.60, "live_fx_timestamp_utc": "2026-09-01T09:00:00Z", "live_fx_age_seconds": 45.0}
        out = annotate_report(text, freshness)
        self.assertIn("기준일 불일치 — 계산 보류", out)
        self.assertIn("USD/JPY 158.250", out)
        self.assertIn("query1/query2 5분 교차확인", out)

    def test_report_does_not_call_positive_usdjpy_move_yen_surge(self):
        text = "[글로벌 금리·엔캐리 경보] 🟠\n판정: 엔캐리 청산 경계 강화\n조회: 2026-09-15 07:55:32 KST\n\n✅ 엔화 급등: 확인 불가\n"
        freshness = {"same_2y_date": True, "jgb2_date": "2026/9/14", "live_fx_signal_eligible": True, "live_fx_price": 154.269, "live_fx_change_pct": 0.42, "live_fx_timestamp_utc": "2026-09-14T22:55:24Z", "live_fx_age_seconds": 1.0}
        out = annotate_report(text, freshness)
        self.assertIn("⬜ 엔화 급등: USD/JPY 154.269 / 기준변화 +0.42% / 현재 방향 엔화 약세", out)
        self.assertIn("엔화 강세 수준: ✅ USD/JPY 154.269", out)


if __name__ == "__main__":
    unittest.main()

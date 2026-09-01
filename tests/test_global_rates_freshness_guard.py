import unittest

from global_rates_freshness_guard import apply_guard, annotate_report


class GlobalRatesFreshnessGuardTest(unittest.TestCase):
    def base(self):
        pending = {
            "last_values": {
                "jgb2": 1.719,
                "ust2": 4.34,
                "us_jp_2y_spread": 2.621,
                "usdjpy": 159.97,
                "usdjpy_daily_change_pct": 0.45,
            },
            "last_source_dates": {
                "jgb2": "2026/8/28",
                "ust2": "2026-08-31",
                "usdjpy": "2026-08-28",
            },
            "active": {
                "us_jp_2y_spread:below:2.0": False,
                "usdjpy:below:155.0": False,
                "usdjpy:daily_change:below:-2.0": False,
            },
        }
        alert = {
            "events": [
                {"metric": "us_jp_2y_spread", "type": "trigger"},
                {"metric": "ust10", "type": "trigger"},
            ]
        }
        return pending, alert

    def test_mismatched_2y_dates_are_not_compared(self):
        pending, alert = self.base()
        pending, alert, freshness = apply_guard(pending, alert)
        self.assertIsNone(pending["last_values"]["us_jp_2y_spread"])
        self.assertFalse(freshness["same_2y_date"])
        self.assertEqual([e["metric"] for e in alert["events"]], ["ust10"])

    def test_lagged_fred_fx_is_reference_only(self):
        pending, alert = self.base()
        pending, alert, freshness = apply_guard(pending, alert)
        self.assertFalse(freshness["fx_signal_eligible"])
        self.assertIsNone(pending["last_values"]["usdjpy"])
        self.assertEqual(freshness["usdjpy_reference"], 159.97)

    def test_same_date_values_remain_eligible(self):
        pending, alert = self.base()
        pending["last_source_dates"] = {
            "jgb2": "2026/8/31",
            "ust2": "2026-08-31",
            "usdjpy": "2026-08-31",
        }
        pending, alert, freshness = apply_guard(pending, alert)
        self.assertTrue(freshness["same_2y_date"])
        self.assertTrue(freshness["fx_signal_eligible"])
        self.assertEqual(pending["last_values"]["us_jp_2y_spread"], 2.621)
        self.assertEqual(pending["last_values"]["usdjpy"], 159.97)

    def test_report_explains_why_comparison_is_withheld(self):
        text = "\n".join([
            "[글로벌 금리·엔캐리 경보] 🟢",
            "판정: 관찰",
            "조회: 2026-09-01 06:56:44 KST",
            "",
            "⬜ 미·일 2Y 금리차 축소: 확인 불가",
            "⬜ 엔화 급등: 확인 불가",
        ])
        freshness = {
            "same_2y_date": False,
            "jgb2_date": "2026/8/28",
            "ust2_date": "2026-08-31",
            "fx_signal_eligible": False,
            "usdjpy_reference": 159.97,
            "usdjpy_date": "2026-08-28",
        }
        out = annotate_report(text, freshness)
        self.assertIn("기준일 불일치 — 계산 보류", out)
        self.assertIn("최신성 부족으로 현재 신호 판정 제외", out)
        self.assertIn("159.970", out)


if __name__ == "__main__":
    unittest.main()

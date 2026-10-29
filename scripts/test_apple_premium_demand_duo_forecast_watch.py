#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "apple_premium_demand_duo_forecast_watch.py"
spec = importlib.util.spec_from_file_location("apple_premium_demand_duo_forecast_watch", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


class ApplePremiumDemandForecastTests(unittest.TestCase):
    def state(self):
        return {"metrics": dict(m.BASELINE)}

    def item(self, title, description="", source="Counterpoint Research"):
        return {
            "title": title,
            "description": description,
            "source": source,
            "published_at_kst": "2026-09-30T09:00:00+09:00",
            "link": "https://counterpointresearch.com/en/insights/test" if source=="Counterpoint Research" else "https://example.com",
        }

    def test_official_counterpoint_published_summary_preserved(self):
        self.assertEqual(m.BASELINE["iphone18pro_china_yoy_pct"], 12.0)
        self.assertEqual(m.BASELINE["apple_china_week38_share_pct"], 33.0)
        self.assertIn("공식 공개 해설", m.BASELINE["iphone18pro_confirmation"])
        self.assertIn("counterpointresearch.com", m.COUNTERPOINT_CHINA_PRO_OFFICIAL)

    def test_counterpoint_panel_tracker_is_separate_metric(self):
        self.assertEqual(m.BASELINE["iphone18pro_panel_cumulative_through_oct_yoy_pct"], 2.0)
        self.assertIn("패널", m.BASELINE["iphone18pro_panel_confirmation"])
        self.assertIn("실판매가 아닌", m.BASELINE["iphone18pro_panel_confirmation"])

    def test_official_baseline_alert_does_not_call_panels_sales(self):
        alert = m._baseline_alert(m.BASELINE)
        self.assertIn("패널 조달", alert)
        self.assertIn("Counterpoint 2026-09-30 공식 공개", alert)
        self.assertNotIn("공개 원표는 현재 열람하지 못했습니다", alert)

    def test_same_premium_baseline_does_not_realert(self):
        item = self.item(
            "iPhone 18 Pro China sales rose 12% YoY; Apple share reached 33%",
            "Counterpoint week 38 China sell-through sales and market share.",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_premium_growth_change_alerts_without_becoming_duo_direct_demand(self):
        item = self.item(
            "iPhone 18 Pro China sales rose 18% YoY",
            "Counterpoint China week 38 first three days sales tracker.",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertIn("iphone18pro_china_yoy_pct", signal["changes"])
        self.assertTrue(all("Duo 직접" not in r for r in signal["reasons"]))

    def test_share_change_three_points_alerts(self):
        item = self.item(
            "Apple China weekly smartphone market share reached 37%",
            "iPhone 18 Pro drove share in China week 38.",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertEqual(signal["changes"]["apple_china_week38_share_pct"], 37.0)

    def test_same_counterpoint_duo_6m_is_baseline_repeat(self):
        item = self.item(
            "Counterpoint forecasts iPhone Duo sales of 6 million units in 2026",
            "Analysts expect 6 million units.",
            "Reuters",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_duo_forecast_8m_is_orange_rerating(self):
        item = self.item(
            "Counterpoint raises iPhone Duo forecast to 8 million units",
            "Forecast for 2026 sales rises to 8 million units.",
            "Reuters",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertGreaterEqual(signal["stage"], 2)
        self.assertEqual(signal["changes"]["counterpoint_duo_forecast_m"], 8.0)

    def test_twelve_month_target_not_counterpoint_calendar_forecast(self):
        item = self.item(
            "DigiTimes: Apple iPhone Duo 12-month shipment target 14 million, up 44%",
            "Counterpoint 2026 estimated 6 million units; Foxconn raised target from 9.7 million.",
            "Reuters",
        )
        self.assertIsNone(m._million_forecast(item["title"] + " " + item["description"]))
        self.assertIsNone(m._signal(item, self.state()))

    def test_low_source_cannot_trigger(self):
        item = self.item(
            "iPhone 18 Pro China sales jump 30%",
            "China market sales surged.",
            "notebookcheck.net",
        )
        self.assertIsNone(m._signal(item, self.state()))


    def test_applemagazine_must_not_rank_as_apple_official(self):
        self.assertEqual(m._source_rank("AppleMagazine"),1)
        self.assertEqual(m._source_rank("Apple"),3)
        self.assertEqual(m._source_rank("Counterpoint Research"),3)

    def test_wrong_global_3_1_not_china_launch_12(self):
        article=self.item(
            "iPhone 18 Pro Series Sales Rise 3.1% as China Drives Growth",
            "Global iPhone 18 Pro sales increased 3.1% during the first three weeks after launch. "
            "China grew 29% YoY.",
            "AppleMagazine",
        )
        article["link"]="https://news.google.com/rss/articles/example"
        blob=article["title"]+" "+article["description"]
        self.assertIsNone(m._premium_yoy(blob))
        self.assertEqual(m._premium_three_week_yoy(blob,"global"),3.1)
        self.assertEqual(m._premium_three_week_yoy(blob,"china"),29.0)
        self.assertIsNone(m._signal(article,self.state()))

    def test_direct_counterpoint_china_three_week_change_has_own_series(self):
        article=self.item(
            "iPhone 18 Pro China and global sales after launch",
            "During the first three weeks after launch, global iPhone 18 Pro sales "
            "increased 3.1% YoY. China grew 35% YoY.",
            "Counterpoint Research",
        )
        article["link"]=m.COUNTERPOINT_THREE_WEEK_OFFICIAL
        sig=m._signal(article,self.state())
        self.assertIsNotNone(sig)
        self.assertEqual(sig["changes"]["iphone18pro_china_first3weeks_yoy_pct"],35.0)
        self.assertNotIn("iphone18pro_china_yoy_pct",sig["changes"])
        self.assertNotIn("iphone18pro_global_first3weeks_yoy_pct",sig["changes"])

    def test_google_news_redirect_cannot_replace_regional_sales_data(self):
        article=self.item(
            "iPhone 18 Pro China first three weeks sales growth 40%",
            "During the first three weeks, iPhone 18 Pro China sales grew 40% YoY.",
        )
        article["link"]="https://news.google.com/rss/articles/example"
        self.assertIsNone(m._signal(article,self.state()))

    def test_pro_max_share_56_does_not_replace_china_market_share_33(self):
        article=self.item(
            "iPhone 18 Pro first three weeks China sales increase",
            "During the first three weeks China grew 29% YoY. "
            "iPhone 18 Pro Max accounted for 56% of series sales.",
        )
        article["link"]=m.COUNTERPOINT_THREE_WEEK_OFFICIAL
        self.assertIsNone(m._premium_share(article["title"]+" "+article["description"]))
        self.assertIsNone(m._signal(article,self.state()))

    def test_original_bad_state_requires_one_correction_only(self):
        old={"metrics":dict(m.BASELINE,iphone18pro_china_yoy_pct=3.1),
             "false_china_scope_correction_sent":False}
        self.assertTrue(m._needs_scope_correction(old))
        self.assertIn("메시지 ID 352",m._scope_correction_alert())
        old["false_china_scope_correction_sent"]=True
        self.assertFalse(m._needs_scope_correction(old))

    def test_corrupt_persisted_state_fails_closed(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/"bad.json"
            path.write_text("{bad json",encoding="utf-8")
            with patch.object(m,"STATE_PATH",path):
                with self.assertRaises(RuntimeError):
                    m._load_state()

    def test_week_38_and_first_three_weeks_never_compared_directly(self):
        self.assertEqual(m._premium_yoy(
            "iPhone 18 Pro China week 38 first three days sales rose 12% YoY"
        ),12.0)
        later="Global iPhone 18 Pro sales grew 3.1% first three weeks. China grew 29%."
        self.assertIsNone(m._premium_yoy(later))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ApplePremiumDemandForecastTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)

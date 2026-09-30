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
            "link": "https://example.com",
        }

    def test_baseline_preserves_paid_tracker_status(self):
        self.assertEqual(m.BASELINE["iphone18pro_china_yoy_pct"], 12.0)
        self.assertEqual(m.BASELINE["apple_china_week38_share_pct"], 33.0)
        self.assertIn("공개 원표 미열람", m.BASELINE["iphone18pro_confirmation"])

    def test_same_premium_baseline_does_not_realert(self):
        item = self.item(
            "iPhone 18 Pro China sales rose 12% YoY; Apple share reached 33%",
            "Counterpoint week 38 China sell-through sales and market share.",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_premium_growth_change_alerts_without_becoming_duo_direct_demand(self):
        item = self.item(
            "iPhone 18 Pro China sales rose 18% YoY",
            "Counterpoint China weekly sales tracker.",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertIn("iphone18pro_china_yoy_pct", signal["changes"])
        self.assertTrue(all("Duo 직접" not in r for r in signal["reasons"]))

    def test_share_change_three_points_alerts(self):
        item = self.item(
            "Apple China weekly smartphone market share reached 37%",
            "iPhone 18 Pro drove share in China week 39.",
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

    def test_low_source_cannot_trigger(self):
        item = self.item(
            "iPhone 18 Pro China sales jump 30%",
            "China market sales surged.",
            "notebookcheck.net",
        )
        self.assertIsNone(m._signal(item, self.state()))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ApplePremiumDemandForecastTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)

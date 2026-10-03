import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import ai_server_physical_bottleneck_watch as m


class AIServerPhysicalBottleneckTests(unittest.TestCase):
    def test_aec_means_active_electrical_not_optical(self):
        cats = m.classify_categories("800G Active Electrical Cable AEC customer shipments begin")
        self.assertIn("AEC", cats)
        self.assertNotIn("AEC", m.classify_categories("800G active optical cable AOC shipments begin"))

    def test_elite_material_ccl_is_not_aec(self):
        cats = m.classify_categories("AI server copper-clad laminate CCL production capacity expands 20%")
        self.assertIn("PCB_CCL", cats)
        self.assertNotIn("AEC", cats)

    def test_forecast_penetration_only_does_not_alert(self):
        text = "Liquid cooling penetration is projected to reach 53% in 2026."
        event = m.parse_event(
            text,
            "https://www.trendforce.com/presscenter/news/example.html",
            "Liquid cooling penetration forecast",
            "2026-10-03T10:00:00+09:00",
        )
        self.assertEqual(event, {})

    def test_psu_supply_constraint_with_number_alerts(self):
        text = "AI server power supply PSU supply constraints cap output; lead times extended to 26 weeks."
        event = m.parse_event(
            text,
            "https://www.trendforce.com/presscenter/news/example.html",
            "AI server power supply constraints",
            "2026-10-03T10:00:00+09:00",
        )
        self.assertIn("POWER", event["categories"])
        self.assertIn("26 weeks", event["metrics"])


    def test_unrelated_article_number_is_not_attached_to_bottleneck(self):
        text = (
            "AI server power supply PSU supply constraints are limiting output. "
            "Elsewhere, liquid cooling penetration is projected to reach 53% in 2026. "
            "A separate business segment grew 90%."
        )
        event = m.parse_event(
            text,
            "https://www.trendforce.com/presscenter/news/example.html",
            "AI server power supply constraints",
            "2026-10-03T10:00:00+09:00",
        )
        self.assertIn("POWER", event["categories"])
        self.assertNotIn("90%", event["metrics"])

    def test_odm_rack_shipment_guidance_alerts(self):
        text = "AI server rack shipments are expected to grow more than double as production capacity expands."
        event = m.parse_event(
            text,
            "https://www.honhai.com/en-us/example",
            "AI rack shipment update",
            "2026-10-03T10:00:00+09:00",
        )
        self.assertIn("ODM_RACK", event["categories"])
        self.assertTrue(event["metrics"])

    def test_nonofficial_source_is_not_alert_source(self):
        event = m.parse_event(
            "AI server PSU shortage lead time 30 weeks.",
            "https://example.com/story",
            "rumor",
            "2026-10-03T10:00:00+09:00",
        )
        self.assertEqual(event, {})

    def test_baseline_does_not_claim_universal_six_month_shortage(self):
        self.assertFalse(m.BASELINE["facts"]["universal_six_month_shortage_confirmed"])

    def test_alert_is_compact(self):
        event = {
            "categories": ["POWER"],
            "company": "Delta Electronics",
            "title": "AI power update",
            "published_at_kst": "2026-10-03T10:00:00+09:00",
            "metrics": ["26 weeks"],
            "stage": "공급 병목",
            "url": "https://www.deltaww.com/en-US/example",
        }
        alert = m.build_alert([event])
        self.assertIn("<b>변화</b>", alert)
        self.assertIn("<b>의미</b>", alert)
        self.assertIn("<b>관련 기업</b>", alert)
        self.assertIn("<b>다음 확인</b>", alert)
        self.assertNotIn("강한 알림 기준", alert)
        self.assertNotIn("숨은 역풍", alert)


if __name__ == "__main__":
    unittest.main()

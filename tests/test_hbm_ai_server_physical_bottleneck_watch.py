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
        self.assertNotIn("53%", event["metrics"])
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


    def test_named_supplier_official_domains_are_covered(self):
        self.assertTrue(m.is_official("https://www.avc.co/en-us/example"))
        self.assertTrue(m.is_official("https://www.liteon.com/en/news/example"))
        self.assertTrue(m.is_official("https://www.tuc.com.tw/example"))


    def test_uqd_and_manifold_sources_are_covered(self):
        self.assertTrue(m.is_official("https://www.parker.com/example"))
        self.assertTrue(m.is_official("https://www.nvent.com/example"))
        self.assertTrue(m.is_official("https://www.vertiv.com/example"))
        self.assertTrue(m.is_official("https://www.coolitsystems.com/example"))
        self.assertTrue(m.is_official("https://www.opencompute.org/example"))
        self.assertTrue(m.is_trusted("https://www.digitimes.com/news/example"))

    def test_uqd_shortage_is_separate_bottleneck_category(self):
        event = m.parse_event(
            "Universal Quick Disconnect UQD supply shortage has extended lead time to 20 weeks.",
            "https://www.digitimes.com/news/example",
            "UQD supply remains tight",
            "2026-10-04T10:00:00+09:00",
        )
        self.assertIn("UQD_MANIFOLD", event["categories"])
        self.assertNotIn("LIQUID_COOLING", event["categories"])
        self.assertIn("20 weeks", event["metrics"])

    def test_static_uqd_product_page_does_not_alert(self):
        event = m.parse_event(
            "The Parker UQDB is a stainless steel non-spill Universal Quick Disconnect for data center liquid cooling.",
            "https://www.parker.com/example",
            "Parker UQDB product",
            "2026-10-04T10:00:00+09:00",
        )
        self.assertEqual(event, {})

    def test_non_uqd_digitimes_story_does_not_enter_route(self):
        event = m.parse_event(
            "AI server PSU supply shortage has extended lead time to 20 weeks.",
            "https://www.digitimes.com/news/example",
            "PSU supply tight",
            "2026-10-04T10:00:00+09:00",
        )
        self.assertEqual(event, {})

    def test_baseline_rejects_monopoly_and_five_micron_claims(self):
        facts = m.BASELINE["facts"]
        self.assertFalse(facts["parker_uqd_exclusive_supply_confirmed"])
        self.assertTrue(facts["parker_uqd_multi_vendor_interchangeable"])
        self.assertFalse(facts["five_micron_manifold_tolerance_confirmed"])
        self.assertFalse(facts["uqd_current_2026_shortage_confirmed"])

    def test_uqd_alert_names_direct_suppliers(self):
        event = {
            "categories": ["UQD_MANIFOLD"],
            "company": "Parker Hannifin",
            "title": "UQD capacity update",
            "published_at_kst": "2026-10-04T10:00:00+09:00",
            "metrics": ["20 weeks"],
            "stage": "공급 부족",
            "url": "https://www.parker.com/example",
        }
        alert = m.build_alert([event])
        self.assertIn("Parker Hannifin", alert)
        self.assertIn("nVent", alert)
        self.assertIn("Vertiv", alert)
        self.assertIn("CoolIT Systems", alert)
        self.assertIn("UQD/BMQC", alert)

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

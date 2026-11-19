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


    def test_semicap_equipment_bottleneck_parses_current_lead_time(self):
        event = m.parse_event(
            "Semiconductor equipment component shortage has stretched lead time to 40 months for a key laser-processing tool component.",
            "https://www.trendforce.com/news/2026/09/18/example",
            "Chip equipment component lead times stretch to 40 months",
            "2026-10-04T10:00:00+09:00",
        )
        self.assertIn("SEMICAP_EQUIPMENT", event["categories"])
        self.assertIn("40 months", event["metrics"])

    def test_reuters_semicap_capacity_event_is_allowed_but_other_reuters_story_is_not(self):
        semicap = m.parse_event(
            "ASML chipmaking equipment production capacity expansion is 30% as AI demand fills EUV capacity.",
            "https://www.reuters.com/business/example",
            "ASML expands chipmaking equipment capacity",
            "2026-10-04T10:00:00+09:00",
        )
        self.assertIn("SEMICAP_EQUIPMENT", semicap["categories"])
        other = m.parse_event(
            "AI server PSU shortage has extended lead time to 30 weeks.",
            "https://www.reuters.com/business/example",
            "PSU shortage",
            "2026-10-04T10:00:00+09:00",
        )
        self.assertEqual(other, {})

    def test_semicap_structural_baseline_is_kept_separate(self):
        facts = m.BASELINE["facts"]
        self.assertEqual(facts["ubs_semicap_project_leadtime_months_min"], 12.0)
        self.assertEqual(facts["ubs_semicap_project_leadtime_months_max"], 24.0)
        self.assertTrue(facts["ubs_semicap_metric_is_project_leadtime"])
        self.assertEqual(facts["trendforce_major_semicap_tool_delivery_max_months"], 12.0)
        self.assertEqual(facts["trendforce_semicap_component_max_leadtime_months"], 40.0)
        self.assertEqual(facts["asml_euv_capacity_booked_through_year"], 2027)

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

    def test_gea_one_time_alert_is_scope_locked_and_deduplicated(self):
        import copy
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo("Asia/Seoul")
        previous = copy.deepcopy(m.BASELINE)
        now = datetime(2026, 11, 19, 20, 0, tzinfo=kst)
        ev = m.pcb_alert_event(previous, now, {"status": "verified"})
        self.assertIsNotNone(ev)
        self.assertEqual(ev["facts"]["na_ytd_period"], "2026-01_to_2026-09")
        self.assertEqual(ev["facts"]["high_layer_pcb_lead_time_weeks_min"], 16)
        self.assertNotIn("ABF", ev["facts"])
        notice = m.pcb_alert_text(ev)
        for term in ("12층", "40~60층", "+56.1%", "+13.3%", "북미", "16~20주",
                     "ABF", "2028년 중반", "100억달러(약 13조3,110억원)"):
            self.assertIn(term, notice)
        previous["pcb_association"] = {"delivered_fact_keys": [m.PCB_ALERT_KEY]}
        self.assertIsNone(m.pcb_alert_event(previous, now, {"status": "verified"}))
        self.assertIsNone(m.pcb_alert_event(m.BASELINE, datetime(
            2026, 11, 19, 13, 0, tzinfo=kst), {"status": "verified"}))
        self.assertIsNone(m.pcb_alert_event(m.BASELINE, datetime(
            2026, 12, 12, 9, 0, tzinfo=kst), {"status": "verified"}))

    def test_gea_source_probe_distinguishes_verified_and_lookup_failed(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from unittest import mock
        now = datetime(2026, 11, 19, 20, tzinfo=ZoneInfo("Asia/Seoul"))
        issuer = (
            "Global Electronics Association warns that PCB supply chains face shortages. "
            "Bookings grew 56.1% while shipments increased 13.3% and relief before 2028 is unlikely."
        )
        with mock.patch.object(m, "fetch", return_value=issuer.encode()):
            ok = m.pcb_publisher_probe(now)
        self.assertEqual(ok["status"], "verified")
        with mock.patch.object(m, "fetch", side_effect=TimeoutError("blocked")):
            failed = m.pcb_publisher_probe(now)
        self.assertEqual(failed["status"], "lookup_failed")
        self.assertEqual(len(failed["observations"]), 2)
        self.assertTrue(all(o["status"] == "lookup_failed" for o in failed["observations"]))

    def test_official_pcb_issuer_is_not_discarded_due_to_delayed_indexing(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from unittest import mock
        now = datetime(2026, 11, 19, 20, tzinfo=ZoneInfo("Asia/Seoul"))
        item = {
            "title": "Official PCB supply update",
            "link": "https://www.electronics.org/news-release/new-ai-pcb-material-supply-update",
            "description": "PCB shortage lead times now 24 weeks.",
            "published_at_kst": "2026-11-19T15:00:00+09:00",
        }
        previous = {"last_checked_at_kst": "2026-11-19T18:00:00+09:00",
                    "seen_urls": [], "seen_signatures": []}
        health = {}
        feed = lambda query: [item] if "electronics.org" in query else []
        with mock.patch.object(m, "read_rss", side_effect=feed), \
             mock.patch.object(m, "article_text", return_value=""):
            events = m.discover(previous, now, health)
        self.assertEqual(len(events), 1)
        self.assertIn("PCB_CCL", events[0]["categories"])
        self.assertEqual(health["status"], "checked")
        again = {"last_checked_at_kst": previous["last_checked_at_kst"],
                 "seen_urls": [item["link"]], "seen_signatures": []}
        with mock.patch.object(m, "read_rss", side_effect=feed), \
             mock.patch.object(m, "article_text", return_value=""):
            self.assertEqual(m.discover(again, now), [])

    def test_rss_lookup_failure_is_not_reported_as_no_new_official_release(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from unittest import mock
        now = datetime(2026, 11, 19, 20, tzinfo=ZoneInfo("Asia/Seoul"))
        health = {}
        with mock.patch.object(m, "read_rss", side_effect=TimeoutError("timeout")):
            self.assertEqual(m.discover(m.BASELINE, now, health), [])
        self.assertEqual(health["status"], "lookup_failed")
        self.assertEqual(health["rss_success_count"], 0)
        self.assertGreater(health["rss_failure_count"], 0)

    def test_gea_backfill_keeps_other_state_and_requires_live_ack_promotion(self):
        import copy
        import json
        import tempfile
        from datetime import datetime
        from unittest import mock
        from zoneinfo import ZoneInfo
        class Clock(m.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 19, 20, 0, tzinfo=ZoneInfo("Asia/Seoul"))
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            state, pending, alert = (
                root / "state.json", root / "pending.json", root / "alert.html"
            )
            original = copy.deepcopy(m.BASELINE)
            original["last_checked_at_kst"] = "2026-11-19T18:37:26+09:00"
            original["other_route"] = {"preserved": True}
            state.write_text(json.dumps(original), encoding="utf-8")
            with mock.patch.object(m, "datetime", Clock), \
                 mock.patch.object(m, "STATE_PATH", state), \
                 mock.patch.object(m, "PENDING_PATH", pending), \
                 mock.patch.object(m, "ALERT_PATH", alert), \
                 mock.patch.object(m, "discover", return_value=[]), \
                 mock.patch.object(m, "pcb_publisher_probe", return_value={"status": "lookup_failed"}):
                m.main()
                staged = json.loads(pending.read_text(encoding="utf-8"))
                self.assertEqual(staged["pcb_association"]["delivered_fact_keys"], [m.PCB_ALERT_KEY])
                self.assertEqual(staged["other_route"], {"preserved": True})
                self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["other_route"], {"preserved": True})
                self.assertTrue(alert.exists())
                # The test promotes only a simulated acknowledged state; production
                # sends are exclusively managed by the pre-existing delivery gate.
                state.write_text(json.dumps(staged), encoding="utf-8")
                alert.unlink()
                m.main()
                self.assertFalse(alert.exists())




if __name__ == "__main__":
    unittest.main()

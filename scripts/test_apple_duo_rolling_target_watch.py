#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("apple_duo_rolling_target_watch",
    ROOT/"scripts"/"apple_duo_rolling_target_watch.py")
m=importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)

class DuoRollingTargetTests(unittest.TestCase):
    def state(self):return {
        "seen_fact_keys":[m.BASELINE_FACT],"metrics":dict(m.BASELINE)}
    def item(self,title,desc="",source="DIGITIMES",domain="https://www.digitimes.com"):
        return {"title":title,"description":desc,"source":source,"source_url":domain,
                "published_at_kst":"2026-10-22T12:00:00+09:00",
                "link":"https://example.org/news"}

    def test_rolling_english_9_7_to_14(self):
        text=("Apple raises iPhone Duo shipment target from 9.7 million to "
              "14 million units over 12 months, DigiTimes says")
        d=m._typed_target(text)
        self.assertEqual((d["old"],d["target"]),(9.7,14))
    def test_korean_970_to_1400(self):
        text="아이폰 듀오 첫 12개월 생산 목표 기존 970만 대에서 1400만 대로 상향"
        d=m._typed_target(text)
        self.assertEqual((d["old"],d["target"]),(9.7,14))
    def test_korean_provided_44_pct_not_parsed_as_target(self):
        text="아이폰 듀오 12개월 목표 970만 대→1400만 대 44% 상향"
        self.assertEqual(m._typed_target(text)["target"],14)
    def test_2026_calendar_5m_is_not_12mo(self):
        self.assertIsNone(m._typed_target(
            "TrendForce projects iPhone Duo shipments of 5 million units for calendar 2026"))
    def test_2026_calendar_6m_is_not_12mo(self):
        self.assertIsNone(m._typed_target(
            "Counterpoint forecasts 6 million iPhone Duo units in 2026"))
    def test_delivery_wait_january_not_target(self):
        self.assertIsNone(m._typed_target(
            "Apple iPhone Duo shipping estimates slip to January 25, 2027 after preorders"))
    def test_idc_worldwide_foldable_growth_not_duo_target(self):
        self.assertIsNone(m._typed_target(
            "DIGITIMES sees global foldable shipments rising 25.7% in 2026 and 59.1% in 2027"))
    def test_basic_reprint_14m_rolling_is_not_new(self):
        row=self.item(
            "Apple raises iPhone Duo 12-month target to 14 million units",
            "Supply orders increased 44% from 9.7 million, according to DigiTimes.",
            "MacRumors","https://www.macrumors.com")
        self.assertIsNone(m._signal(row,self.state()))
    def test_new_rolling_15m_revision_high_source(self):
        row=self.item(
            "Apple raises iPhone Duo 12-month production target to 15 million units",
            "Updated Foxconn order targets reflect higher planned shipment volume.",
            "DIGITIMES")
        s=m._signal(row,self.state())
        self.assertIsNotNone(s)
        self.assertEqual(s["data"]["target"],15.0)
        self.assertEqual(s["stage"],2)
    def test_rolling_16m_never_replaces_calendar_in_state(self):
        row=self.item(
            "Apple raises iPhone Duo 12-month shipment target to 16 million units",
            "Foxconn orders and supply chain target revised.",
            "Reuters","https://www.reuters.com")
        s=m._signal(row,self.state())
        self.assertNotIn("calendar_2026",s["data"])
    def test_14m_rolling_not_independent_2026_14m(self):
        self.assertEqual(m.BASELINE["period_basis"],"rolling_first_12_months")
        self.assertEqual(m.BASELINE["calendar_2026_counterpoint_forecast_m"],6.0)
        self.assertEqual(m.BASELINE["calendar_2026_trendforce_forecast_m"],5.0)
    def test_rolling_target_not_oled_panel_units(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "duo_panel_guard", ROOT / "scripts" / "apple_duo_panel_leading_watch.py"
        )
        panel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(panel)
        row = self.item(
            "DigiTimes iPhone Duo 12-month build target 14 million up 44%",
            "Foxconn suppliers include Samsung Display OLED panels.",
        )
        self.assertEqual(panel._extract_metrics(row), {})

    def test_source_root_is_not_independent_media(self):
        row=self.item("DigiTimes iPhone Duo 14 million 12 months","44%","MacRumors")
        self.assertEqual(m._original_root(row),"digitimes_2026-10-22")
    def test_apple_store_homepage_not_official_supplier_guidance(self):
        row=self.item(
            "Apple raises iPhone Duo 12-month target to 15 million units",
            "Production target revised per report.","Apple",
            "https://www.macrumors.com")
        self.assertFalse(m._official(row))
    def test_source_verified_apple_domain_can_confirm(self):
        row=self.item(
            "Apple confirms iPhone Duo 12-month shipment target raised to 14 million units",
            "Original 9.7 million unit target for Foxconn revised.",
            "Apple Newsroom","https://www.apple.com/newsroom")
        s=m._signal(row,self.state())
        self.assertIsNotNone(s)
        self.assertEqual(s["stage"],3)
    def test_no_duo_pro_cross_product(self):
        self.assertIsNone(m._typed_target(
            "Apple iPhone 18 Pro target 14 million units over 12 months orders revised"))
    def test_two_no_change_scans_never_resend_baseline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            current={
                "schema_version":1,"initial_alert_sent":True,
                "seen":[],"seen_fact_keys":[m.BASELINE_FACT],
                "metrics":dict(m.BASELINE),"last_alert":{"at_kst":"2026-10-23T10:00:00+09:00","kind":"first_baseline"},
            }
            data=root/"state.json"
            data.write_text(__import__("json").dumps(current),encoding="utf-8")
            item=self.item(
                "Apple iPhone Duo 12-month target 14 million after 44% boost",
                "DigiTimes repeats its earlier supplier forecast from 9.7 million units.",
                "MacRumors","https://www.macrumors.com",
            )
            with (patch.object(m,"DATA",data),
                  patch.object(m,"PENDING",root/"pending.json"),
                  patch.object(m,"STATUS",root/"status.md"),
                  patch.object(m,"FRAGMENT",root/"alert.html"),
                  patch.object(m,"TELEGRAM",root/"telegram.txt"),
                  patch.object(m,"collect",return_value=([item],[]))):
                for _ in range(2):
                    m.main()
                    result=__import__("json").loads((root/"pending.json").read_text(encoding="utf-8"))
                    self.assertEqual(result["last_new_signals"],0)
                    self.assertEqual(result["metrics"]["reported_target_m"],14.0)
                    self.assertFalse((root/"telegram.txt").exists())
                    self.assertFalse((root/"alert.html").exists())
                    data.write_text(__import__("json").dumps(result),encoding="utf-8")

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as path:
            file=pathlib.Path(path)/"state.json"
            file.write_text("{bad",encoding="utf-8")
            with patch.object(m,"DATA",file):
                with self.assertRaises(RuntimeError):
                    m._load()
    def test_selling_more_is_not_done_when_target_14m(self):
        self.assertIsNone(m.BASELINE["actual_shipments_m"])
        self.assertEqual(m.BASELINE["named_suppliers_with_verified_incremental_po"],[])
        self.assertFalse(m.BASELINE["apple_officially_confirmed"])

if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DuoRollingTargetTests))
    if not result.wasSuccessful():sys.exit(1)

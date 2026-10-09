#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apple_iphone18_pro_orders_watch",
    ROOT / "scripts" / "apple_iphone18_pro_orders_watch.py"
)
m = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)

class IPhone18ProOrderTests(unittest.TestCase):
    def item(self, title, desc="", source="Reuters", when="2026-10-09T15:05:00+09:00"):
        return {
            "title": title, "description": desc, "source": source,
            "published_at_kst": when, "link": "https://example.org/report"
        }
    def state(self):
        return {"initial_alert_sent": True, "seen_fact_keys": [m.BASELINE_FACT],
                "metrics": {"reported_baseline": dict(m.BASELINE)}}

    def test_nikkei_oct_order_cut_range(self):
        text = ("Apple cuts iPhone 18 Pro and iPhone 18 Pro Max component orders "
                "for October by 15%-20% compared with originally requested volumes.")
        self.assertEqual(
            m._extract_cut(text),
            {"period": "2026-10", "low": 15.0, "high": 20.0,
             "basis": "original_supplier_request"},
        )
    def test_english_oct_at_least_15_is_same_baseline(self):
        row = self.item(
            "Apple cuts iPhone 18 Pro component orders for October",
            "Initial supplier requests cut at least 15% for components, Nikkei reports.")
        data = m._extract_cut(row["title"]+" "+row["description"])
        self.assertIsNotNone(data)
        self.assertTrue(m._known_baseline_repeat(data,row))
        self.assertIsNone(m._relevant_news(row,self.state()))

    def test_nikkei_20pct_repost_is_same_fact(self):
        for value in ("15%", "20%", "15%-20%"):
            row = self.item(
                f"Nikkei: iPhone 18 Pro October component orders cut {value}",
                "Suppliers say production and original planned orders reduced.",
                "investing.com")
            self.assertIsNone(m._relevant_news(row,self.state()))

    def test_china_early_sell_through_12pct_not_component_cut(self):
        headline = "iPhone 18 Pro China week 38 sales up 12% YoY, Apple share 33%"
        self.assertIsNone(m._extract_cut(headline))
        self.assertIsNone(m._relevant_news(self.item(headline),self.state()))

    def test_idc_market_annual_decline_not_iphone_order_cut(self):
        text = "IDC 2026 global smartphone shipments -16.7%, ASP +27.6%."
        self.assertIsNone(m._extract_cut(text))

    def test_pro_vs_duo_is_separate_product(self):
        text = "iPhone Duo 2026 shipments outlook cut 20% due to component shortages."
        self.assertIsNone(m._extract_cut(text))

    def test_no_period_or_comparison_basis_never_fires(self):
        text = "Apple cuts iPhone 18 Pro supplier component orders 25%"
        self.assertIsNone(m._extract_cut(text))

    def test_specific_november_further_cut_can_alert(self):
        row = self.item(
            "Apple iPhone 18 Pro component orders for November cut 25%",
            "Suppliers say original planned production orders have been lowered 25%.",
            "Nikkei Asia")
        signal = m._relevant_news(row,self.state())
        self.assertIsNotNone(signal)
        self.assertEqual(signal["cut"]["period"],"2026-11")

    def test_material_october_change_can_alert(self):
        row = self.item(
            "Apple iPhone 18 Pro component orders for October cut 30%",
            "Suppliers say initial planned orders for October were reduced 30%.",
            "Reuters")
        self.assertIsNotNone(m._relevant_news(row,self.state()))

    def test_small_oct_revision_is_not_new_fact(self):
        row = self.item(
            "Apple iPhone 18 Pro October component orders cut 17%",
            "Original planned supplier production orders trimmed 17%, Nikkei report.",
            "Reuters")
        self.assertIsNone(m._relevant_news(row,self.state()))

    def test_low_trust_source_cannot_alert(self):
        row=self.item(
            "iPhone 18 Pro November component orders cut 30%",
            "Original planned supplier production orders reduced 30%",
            "notebookcheck.net"
        )
        self.assertIsNone(m._relevant_news(row,self.state()))

    def test_reuters_and_investing_share_nikkei_information_root(self):
        a=self.item(
            "Nikkei: iPhone 18 Pro October component orders cut 30%",
            "Original planned supplier production orders reduced 30%", "Reuters")
        b=self.item(
            "Nikkei iPhone 18 Pro October orders cut 30%",
            "Suppliers original planned component production orders cut 30%", "investing.com")
        self.assertEqual(m._root(a),m.SOURCE_ROOT)
        self.assertEqual(m._root(b),m.SOURCE_ROOT)
        self.assertEqual(m._fact_key(m._extract_cut(a["title"]+" "+a["description"]),a),
                         m._fact_key(m._extract_cut(b["title"]+" "+b["description"]),b))

    def test_apple_price_is_official_not_order_cut(self):
        text="Apple iPhone 18 Pro starts at $1,199 and Pro Max at $1,299, up $100."
        self.assertIsNone(m._extract_cut(text))

    def test_reported_supplier_scope_does_not_name_lgi_or_sdc(self):
        self.assertEqual(m.BASELINE["named_supplier_orders_confirmed"],[])
        self.assertFalse(m.BASELINE["actual_finished_device_sales_cut_confirmed"])
        self.assertFalse(m.BASELINE["reuters_independent_confirmation"])

    def test_fx_failure_keeps_unconverted_usd_out(self):
        with patch.dict(sys.modules, {"fx_api": None}):
            line, result=m._fx_info()
            self.assertNotIn("1,199달러",line)
            self.assertNotEqual(result,"confirmed")

    def test_initial_alert_names_idc_forecast_and_uncertainty(self):
        text=m._baseline_alert("• 환율 테스트")
        self.assertIn("8월 26일 전망치",text)
        self.assertIn("Apple 공식 확인",text)
        self.assertIn("니케이",text)
        self.assertNotIn("iPhone Duo 부품 발주 감축",text)

    def test_corrupt_existing_state_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/"state.json"
            path.write_text("{bad",encoding="utf-8")
            with patch.object(m,"STATE_PATH",path):
                with self.assertRaises(RuntimeError):
                    m._load_state()

if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(IPhone18ProOrderTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)

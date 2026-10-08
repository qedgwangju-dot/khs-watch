#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "smartphone_memory_price_pass_through_watch.py"
spec = importlib.util.spec_from_file_location("smartphone_memory_price_pass_through_watch", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


class SmartphoneMemoryPricePassThroughTests(unittest.TestCase):
    def state(self):
        return {"metrics": dict(m.BASELINE)}

    def item(self, title, description="", source="Android Authority"):
        return {
            "title": title,
            "description": description,
            "source": source,
            "published_at_kst": "2026-10-05T12:00:00+09:00",
            "link": "https://example.com",
        }

    def test_s27_baseline_is_rumor_not_confirmed(self):
        self.assertIn("공식 미확정", m.BASELINE["s27_status"])
        self.assertEqual(m.BASELINE["s27_korea_hike_low_krw"], 100000)
        self.assertEqual(m.BASELINE["s27_korea_hike_high_krw"], 130000)

    def test_same_s27_10_to_13_manwon_repeat_does_not_alert(self):
        item = self.item(
            "Galaxy S27 price hike tipped at 100,000 won to 130,000 won",
            "Memory prices and LPDDR6 costs are blamed.",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_material_s27_price_hike_revision_alerts(self):
        item = self.item(
            "Galaxy S27 price hike now tipped at 150,000 won to 180,000 won",
            "Memory prices and LPDDR6 costs are blamed.",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertGreaterEqual(signal["stage"], 2)

    def test_low_source_cannot_trigger(self):
        item = self.item(
            "Galaxy S27 price hike 200,000 won due to memory",
            "LPDDR6 and NAND prices surge.",
            "notebookcheck.net",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_price_pass_through_requires_memory_cost_link(self):
        self.assertFalse(
            m._is_price_pass_through("Samsung raises Galaxy phone price for tax reasons")
        )
        self.assertTrue(
            m._is_price_pass_through(
                "Samsung raises Galaxy smartphone price as memory prices and component costs rise"
            )
        )

    def test_dram_and_nand_outlook_are_not_collapsed(self):
        self.assertTrue(m.BASELINE["dram_2027_tight"])
        self.assertTrue(m.BASELINE["nand_2h27_easing"])

    def test_s27_lpddr6_ufs51_remains_rumor_baseline(self):
        self.assertEqual(m.BASELINE["s27_lpddr6_ufs51_some_models_status"], "루머")

    def test_smartphone_production_cut_does_not_become_shipment_revision(self):
        article = (
            "Samsung smartphone production cut 30% in Q4 due to memory prices. "
            "DRAM cost rose 175% and IDC expects 52 million smartphones."
        )
        self.assertIsNone(m._shipment_revision_pct(article))
        self.assertFalse(m._is_shipment_revision(article))
        self.assertFalse(m._is_price_pass_through(article))

    def test_actual_shipment_forecast_revision_is_signed(self):
        article = "Samsung smartphone shipment forecast cut 12% due to memory cost increases."
        self.assertEqual(m._shipment_revision_pct(article), -12.0)

    def test_reuters_quote_does_not_make_s27_price_official(self):
        item = self.item(
            "Galaxy S27 Samsung price hike reportedly 100000 won to 130000 won",
            "Rising memory cost was cited.",
            "Reuters",
        )
        self.assertFalse(m._is_official_samsung_item(item))
        self.assertIsNone(m._signal(item, self.state()))

    def test_direct_official_link_is_required_for_confirmation(self):
        item = self.item(
            "Galaxy S27 price hike 100000 won to 130000 won due to memory",
            "Samsung news release",
            "Samsung Global Newsroom",
        )
        self.assertFalse(m._is_official_samsung_item(item))
        item["link"] = "https://news.samsung.com/global/galaxy-s27-pricing-release"
        self.assertTrue(m._is_official_samsung_item(item))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SmartphoneMemoryPricePassThroughTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)

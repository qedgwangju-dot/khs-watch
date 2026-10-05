#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "smartphone_memory_pass_through_watch.py"
spec = importlib.util.spec_from_file_location("smartphone_memory_pass_through_watch", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


class SmartphoneMemoryPassThroughTests(unittest.TestCase):
    def state(self):
        return {"metrics": dict(m.BASELINE)}

    def item(self, title, description="", source="Android Authority"):
        return {
            "title": title,
            "description": description,
            "source": source,
            "published_at_kst": "2026-10-05T09:00:00+09:00",
            "link": "https://example.com",
        }

    def test_committed_state_is_valid_json(self):
        state_path = ROOT / "data" / "smartphone_memory_pass_through_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIsInstance(state, dict)
        self.assertIn("initial_alert_sent", state)

    def test_baseline_is_krw_rumor_not_official(self):
        self.assertEqual(m.BASELINE["s27_korea_hike_low_krw"], 100000)
        self.assertEqual(m.BASELINE["s27_korea_hike_high_krw"], 130000)
        self.assertIn("공식 미확인", m.BASELINE["s27_status"])

    def test_same_s27_100k_130k_rumor_does_not_realert(self):
        item = self.item(
            "Galaxy S27 price hike leak says 100,000 to 130,000 won",
            "Tipster Lanzuk says all models may get more expensive due to LPDDR6 and NAND.",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_material_s27_rumor_change_alerts_as_rumor(self):
        item = self.item(
            "Galaxy S27 price hike leak rises to 180,000 won",
            "Tipster says prices may rise 180,000 won due to memory costs.",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertEqual(signal["stage"], 1)
        self.assertEqual(signal["status"], "루머·공식 미확인")

    def test_samsung_official_price_can_be_red(self):
        item = self.item(
            "Samsung officially announces Galaxy S27 launch price",
            "Samsung announced the Galaxy S27 price starts higher as memory costs rise.",
            "Samsung Newsroom",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertGreaterEqual(signal["stage"], 3)
        self.assertEqual(signal["status"], "공식 가격 확인")

    def test_udn_1400_is_not_baseline_metric(self):
        self.assertNotIn("s27_usd_start_price", m.BASELINE)
        self.assertNotIn("s26_usd_start_price", m.BASELINE)

    def test_component_memory_pct_is_not_phone_price_pct(self):
        item = self.item(
            "Samsung memory prices rise 80% QoQ",
            "LPDDR memory price increased 80%, pressuring smartphone makers.",
            "Counterpoint Research",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_explicit_phone_retail_price_pct_can_trigger(self):
        item = self.item(
            "Samsung smartphone retail price rises 8% as memory costs climb",
            "Samsung smartphone price increased 8% due to DRAM and NAND costs.",
            "Reuters",
        )
        signal = m._signal(item, self.state())
        self.assertIsNotNone(signal)
        self.assertGreaterEqual(signal["stage"], 2)

    def test_low_source_cannot_trigger(self):
        item = self.item(
            "Galaxy S27 price may jump 300,000 won",
            "memory shortage rumor",
            "notebookcheck.net",
        )
        self.assertIsNone(m._signal(item, self.state()))

    def test_fact_key_dedupes_same_s27_range(self):
        key = m._s27_fact_key("Galaxy S27 leak says 100,000 to 130,000 won")
        self.assertEqual(key, "s27_korea_hike_100000_130000")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SmartphoneMemoryPassThroughTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)

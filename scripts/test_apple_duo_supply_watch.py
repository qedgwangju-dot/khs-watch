#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "apple_duo_supply_watch.py"
spec = importlib.util.spec_from_file_location("apple_duo_supply_watch", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


class AppleDuoSupplyRegressionTests(unittest.TestCase):
    def state(self):
        return {
            "metrics": {
                "finished_units_low_m": 5.0,
                "finished_units_high_m": 7.0,
                "stocking_target_low_m": 6.0,
                "stocking_target_high_m": 8.0,
                "panel_units_m": 8.0,
                "daily_output_units": 500,
                "assembly_yield_pct": 60.0,
                "hinge_yield_pct": 65.0,
            },
            "seen_fact_keys": ["assembly_yield_60", "sep17_assembly_bottleneck"],
        }

    def test_unknown_republisher_cannot_alert_alone(self):
        item = {
            "title": "iPhone Duo manufacturing delayed as Foxconn struggles with low yield and defective parts",
            "description": "",
            "source": "Jablíčkář.cz",
        }
        meaningful, _, _ = m._meaningful(item, self.state())
        self.assertFalse(meaningful)
        self.assertEqual(m._source_rank(item["source"]), 0)

    def test_mid_tier_republication_of_same_60pct_yield_is_not_new_change(self):
        item = {
            "title": "iPhone Duo reportedly facing production problems ahead of launch",
            "description": "Foxconn final assembly yield is just over 60% and production is delayed.",
            "source": "MacRumors",
        }
        meaningful, _, _ = m._meaningful(item, self.state())
        self.assertFalse(meaningful)

    def test_assembly_yield_is_separate_from_hinge_yield(self):
        blob = "Foxconn assembly yield for iPhone Duo is 60%"
        topics = m._classify(blob)
        self.assertIn("assembly", topics)
        self.assertIn("yield", topics)
        self.assertNotIn("hinge", topics)

    def test_new_assembly_yield_change_can_alert_from_mid_source(self):
        item = {
            "title": "iPhone Duo Foxconn assembly yield improves to 72%",
            "description": "Production ramp improves as final assembly yield reaches 72%.",
            "source": "MacRumors",
        }
        meaningful, verdict, reason = m._meaningful(item, self.state())
        self.assertTrue(meaningful)
        self.assertIn("최종 조립 수율 개선", verdict)
        self.assertIn("60%→72%", reason)

    def test_high_trust_qualitative_bottleneck_can_alert_without_number(self):
        item = {
            "title": "Apple iPhone Duo production delayed by new Foxconn assembly issue",
            "description": "A new assembly bottleneck is delaying production ramp.",
            "source": "Reuters",
        }
        meaningful, verdict, reason = m._meaningful(item, self.state())
        self.assertTrue(meaningful)
        self.assertEqual(verdict, "생산 램프 병목 변화")
        self.assertIn("고신뢰", reason)

    def test_fact_key_dedupes_same_assembly_yield(self):
        keys = m._fact_keys("Foxconn assembly yield for iPhone Duo is 60%")
        self.assertIn("assembly_yield_60", keys)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AppleDuoSupplyRegressionTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)

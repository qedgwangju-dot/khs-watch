import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import ai_inference_structure_watch as m


class InferenceStructureWatchTests(unittest.TestCase):
    def test_coreweave_power_change_is_material(self):
        previous = {"neocloud": {"CoreWeave": {"active_power_gw": 1.5, "contracted_power_gw": 4.2}}}
        update = {"company": "CoreWeave", "metrics": {"active_power_gw": 1.7}, "negative": False}
        events = m.compare_neocloud(previous, update)
        self.assertTrue(any(e["label"] == "활성 전력" for e in events))

    def test_revenue_per_mw_ten_percent_is_material(self):
        previous = {"neocloud": {"CoreWeave": {"annualized_revenue_per_mw_usd_m": 40.0}}}
        update = {"company": "CoreWeave", "metrics": {"annualized_revenue_per_mw_usd_m": 44.1}, "negative": False}
        events = m.compare_neocloud(previous, update)
        self.assertTrue(any(e["label"] == "MW당 연환산 매출" for e in events))

    def test_edge_outlook_only_is_not_event(self):
        text = "We expect the edge AI inference market to grow rapidly across regional locations."
        self.assertEqual(m.parse_edge_actual(text, "https://www.att.com/example", "outlook"), {})

    def test_edge_actual_requires_commercial_scale_evidence(self):
        text = "We signed an agreement to deploy AI inference at regional edge sites with 120 MW of capacity."
        event = m.parse_edge_actual(text, "https://www.att.com/example", "regional AI inference")
        self.assertEqual(event["kind"], "edge_actual")

    def test_upstream_bootstrap_is_silent(self):
        after = {"agentic_ratio": "1:1", "samsung_server_cpu_fcbga_mass_production": True}
        self.assertEqual(m.upstream_events({}, after), [])

    def test_upstream_ratio_change_is_event(self):
        before = {"agentic_ratio": "1:2"}
        after = {"agentic_ratio": "1:1"}
        events = m.upstream_events(before, after)
        self.assertTrue(any(e["label"] == "에이전트형 CPU:GPU 비율" for e in events))

    def test_nebius_guidance_not_misread_as_actual(self):
        text = "We are raising our contracted power guidance to more than 4 GW by year-end."
        parsed = m.parse_nebius(text, "https://nebius.com/newsroom/example")
        self.assertEqual(parsed["metrics"].get("contracted_power_guidance_gw"), 4.0)
        self.assertNotIn("contracted_power_gw", parsed["metrics"])

    def test_contractual_termination_right_is_not_downside_event(self):
        text = "Microsoft has the right to terminate a GPU Service if delivery dates are missed."
        parsed = m.parse_nebius(text, "https://nebius.com/newsroom/example")
        self.assertEqual(parsed, {})

    def test_cpu_ratio_parser_prefers_agentic_one_to_one(self):
        text = "Agentic AI changes the CPU and GPU equation from 1 CPU to 8 GPU to 1:1 or better."
        parsed = m.parse_cpu_ratio(text, "https://www.intel.com/example")
        self.assertEqual(parsed["company"], "Intel")
        self.assertEqual(parsed["cpu_per_gpu"], 1.0)


if __name__ == "__main__":
    unittest.main()

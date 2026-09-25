import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import agentic_cpu_watch as w


class AgenticCpuParseTests(unittest.TestCase):
    def test_parse_bofa_210_snapshot(self):
        text = """
        BofA raises its CY30E server CPU total addressable market forecast to $210.6bn
        from ~$170bn, representing a 36.1% CAGR from CY26.
        Server CPU TAM 210.6 USD billion.
        AI CPU TAM 180.4 USD billion.
        split roughly 50/50 between compute/head nodes ($90.2bn)
        and agentic AI nodes ($90.2bn).
        about $30bn for traditional/IaaS.
        """
        m = w.parse_forecast(text)
        self.assertAlmostEqual(m["server_cpu_tam_2030_usd_bn"], 210.6)
        self.assertAlmostEqual(m["ai_cpu_2030_usd_bn"], 180.4)
        self.assertAlmostEqual(m["agentic_2030_usd_bn"], 90.2)
        self.assertAlmostEqual(m["compute_head_2030_usd_bn"], 90.2)
        self.assertAlmostEqual(m["agentic_share_pct"], 90.2 / 210.6 * 100)

    def test_parse_requires_agentic_server_cpu_context(self):
        self.assertEqual(w.parse_forecast("GPU TAM $500bn by 2030"), {})

    def test_ratio_extract(self):
        text = "Agentic AI is moving from a 1 CPU : 4-8 GPUs pattern toward a 1:1 ratio."
        self.assertEqual(w.extract_ratio(text), "1:1")


class AgenticCpuThresholdTests(unittest.TestCase):
    def test_tam_ten_percent_triggers(self):
        old = {"server_cpu_tam_2030_usd_bn": 210.6}
        new = {"server_cpu_tam_2030_usd_bn": 232.0}
        changes = w.material_forecast_changes(old, new)
        self.assertEqual(len(changes), 1)

    def test_subthreshold_tam_is_quiet(self):
        old = {"server_cpu_tam_2030_usd_bn": 210.6}
        new = {"server_cpu_tam_2030_usd_bn": 230.0}
        self.assertEqual(w.material_forecast_changes(old, new), [])

    def test_share_five_percentage_points_triggers(self):
        old = {"agentic_share_pct": 42.8}
        new = {"agentic_share_pct": 48.0}
        changes = w.material_forecast_changes(old, new)
        self.assertEqual(changes[0]["mode"], "pp")

    def test_ratio_structure_change(self):
        self.assertTrue(w.ratio_changed("1:1", "1:2"))
        self.assertFalse(w.ratio_changed("1:1", "1 : 1"))


class AgenticCpuAlertTests(unittest.TestCase):
    def test_snapshot_contains_requested_axes(self):
        state = w.BASELINE
        block = w.snapshot_block(
            state,
            1371.0,
            "2026-09-25",
            [],
            None,
            [],
            standalone=False,
        )
        self.assertIn("CPU·에이전트형 AI 수요축", block)
        self.assertIn("2,106억달러", block)
        self.assertIn("902억달러", block)
        self.assertIn("42.8%", block)
        self.assertIn("1,804억달러", block)
        self.assertIn("85.7%", block)
        self.assertIn("1,250억달러 → 1,700억달러 → 2,106억달러", block)
        self.assertIn("DDR5 RDIMM", block)
        self.assertIn("기업용 SSD", block)
        self.assertIn("ABF", block)
        self.assertIn("삼성전기·Ibiden·Unimicron·Nan Ya PCB", block)
        self.assertIn("±10%", block)
        self.assertIn("±5%p", block)

    def test_material_forecast_alert_shows_old_and_new(self):
        latest = dict(w.BASELINE)
        latest["metrics"] = dict(w.BASELINE["metrics"])
        latest["metrics"]["server_cpu_tam_2030_usd_bn"] = 240.0
        changes = w.material_forecast_changes(
            w.BASELINE["metrics"], latest["metrics"]
        )
        block = w.snapshot_block(latest, None, "", changes, None, [], standalone=True)
        self.assertIn("전망 변화 감지", block)
        self.assertIn("210.6bn달러 → 240.0bn달러", block)


if __name__ == "__main__":
    unittest.main()

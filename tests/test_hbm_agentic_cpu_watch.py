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
    def test_snapshot_is_compact_but_keeps_key_axes(self):
        state = w.BASELINE
        block = w.snapshot_block(
            state,
            1371.0,
            "2026-09-25",
            [{"key": "server_cpu_tam_2030_usd_bn", "label": "2030 서버 CPU 시장", "before": 190.0, "after": 210.6, "delta": 10.8, "mode": "pct"}],
            None,
            [],
            standalone=False,
        )
        self.assertIn("<b>CPU·에이전트형 AI</b>", block)
        self.assertIn("• 변화:", block)
        self.assertIn("• 기준:", block)
        self.assertIn("• 의미:", block)
        self.assertIn("• 다음:", block)
        self.assertNotIn("<b>변화</b>", block)
        self.assertNotIn("<b>현재 기준선</b>", block)
        self.assertIn("2,106억달러(", block)
        self.assertIn("902억달러(", block)
        self.assertIn("42.8%", block)
        self.assertIn("1:4~8", block)
        self.assertIn("1:1", block)
        self.assertIn("DDR5 RDIMM", block)
        self.assertIn("기업용 SSD", block)
        self.assertIn("FC-BGA/ABF", block)
        self.assertNotIn("<b>관련 기업 지도</b>", block)
        self.assertNotIn("<b>숨은 역풍·실패모드</b>", block)
        self.assertNotIn("<b>알림 기준</b>", block)
        self.assertLess(len(block), 950)

    def test_material_forecast_alert_shows_old_and_new(self):
        latest = dict(w.BASELINE)
        latest["metrics"] = dict(w.BASELINE["metrics"])
        latest["metrics"]["server_cpu_tam_2030_usd_bn"] = 240.0
        changes = w.material_forecast_changes(
            w.BASELINE["metrics"], latest["metrics"]
        )
        block = w.snapshot_block(latest, None, "", changes, None, [], standalone=True)
        self.assertIn("2,106억달러", block)
        self.assertIn("2,400억달러", block)
        self.assertIn("+14.0%", block)


class AgenticCpuStructureTests(unittest.TestCase):
    def test_baselines_preserve_institution_and_source_scope(self):
        sources = w.CPU_STRUCTURE_BASELINE
        self.assertEqual(sources["bnpp_public"]["market_2025_usd_bn"], 26.0)
        self.assertEqual(sources["bnpp_public"]["market_2030_usd_bn"], 220.0)
        self.assertIn("AMD 추정치", sources["bnpp_public"]["source_kind"])
        self.assertEqual(sources["bnpp_analyst"]["market_2030_usd_bn"], 245.0)
        self.assertFalse(sources["bnpp_analyst"]["market_2025_official_confirmed"])
        self.assertEqual(sources["bnpp_analyst"]["amd_target_usd"], 960.0)
        self.assertFalse(sources["bnpp_analyst"]["arm_target_confirmed"])
        self.assertEqual(sources["digitimes"]["ai_server_cpu_2027_million"], 9.845)
        self.assertEqual(sources["digitimes"]["arm_all_server_cpu_2027_share_pct"], 32.5)
        self.assertEqual(sources["amd_system"]["helios_venice_cpus"], 18)
        self.assertEqual(sources["amd_system"]["helios_mi455x_gpus"], 72)

    def test_other_market_republication_cannot_overwrite_bnp_public(self):
        url = "https://example.org/2026/bnp-says-cpu-300b"
        provider, value = w.cpu_structure_observation(
            "BNP Paribas agentic CPUs market", "from USD30 billion in 2025 to USD245 billion in 2030",
            url,
        )
        self.assertEqual((provider, value), ("", {}))
        provider, value = w.cpu_structure_observation(
            "BNP Paribas agentic CPUs market",
            "AMD estimates suggest the data centre CPU market could rise from around USD26 billion in 2025 to around USD220 billion in 2030.",
            w.CPU_STRUCTURE_BASELINE["bnpp_public"]["source_url"],
        )
        self.assertEqual(provider, "bnpp_public")
        self.assertEqual(value["market_2025_usd_bn"], 26.0)
        self.assertEqual(value["market_2030_usd_bn"], 220.0)

    def test_digitimes_typed_nearly_double_is_not_exact_socket_ratio(self):
        url = w.CPU_STRUCTURE_BASELINE["digitimes"]["per_accelerator_source_url"]
        provider, value = w.cpu_structure_observation(
            "AI servers will carry nearly twice as many CPUs per accelerator by 2027",
            "",
            url,
        )
        self.assertEqual(provider, "digitimes")
        self.assertEqual(value["per_accelerator_cpu_2027"], "nearly_double")
        self.assertEqual(w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE["digitimes"], value, provider), [])
        provider, value = w.cpu_structure_observation(
            "AI servers will carry three times as many CPUs per accelerator by 2027",
            "",
            url,
        )
        self.assertEqual(w.cpu_structure_changes(w.CPU_STRUCTURE_BASELINE["digitimes"], value, provider), [
            "DIGITIMES 2027 가속기당 CPU 전망 변경: nearly_double→triple"
        ])

    def test_bnp_2030_revision_only_compares_same_provider(self):
        old = w.CPU_STRUCTURE_BASELINE["bnpp_public"]
        self.assertEqual(w.cpu_structure_changes(old, {"market_2030_usd_bn": 235}, "bnpp_public"), [])
        self.assertEqual(
            w.cpu_structure_changes(old, {"market_2030_usd_bn": 250}, "bnpp_public"),
            ["BNP 공개자료의 AMD 인용 CPU 시장 전망: 220→250십억달러"],
        )
        self.assertEqual(w.cpu_structure_changes(old, {"market_2030_usd_bn": 245}, "bnpp_analyst"), [])

    def test_one_shot_cpu_alert_has_separate_official_and_broker_provenance(self):
        a = w.cpu_structure_block(w.CPU_STRUCTURE_BASELINE, 1400.0, [])
        self.assertIn("260억달러(약", a)
        self.assertIn("2,200억달러(약", a)
        self.assertIn("2,450억달러(약", a)
        self.assertIn("BNP 애널리스트 별도 보도", a)
        self.assertIn("AMD 목표주가", a)
        self.assertIn("Arm 목표주가 $405", a)
        self.assertIn("가속기당 CPU 거의 2배 전망", a)
        self.assertIn("984.5만개(+84.1%", a)
        self.assertIn("Arm 계열 전체 서버 CPU 1,580만개(32.5%)", a)
        self.assertIn("Venice CPU 18개·MI455X GPU 72개(물리 1:4)", a)
        self.assertNotIn("목표주가 $405(공식 확인)", a)
        self.assertIn("2nm 수율·ABF", a)
        self.assertLess(len(a), 2600)


if __name__ == "__main__":
    unittest.main()

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import abf_cpu_monetization_watch as w


class AbfCpuMonetizationParseTests(unittest.TestCase):
    def test_official_ibiden_capex_and_sap(self):
        text = (
            "IBIDEN will invest approximately JPY 500 billion from FY2026 to FY2028. "
            "Gama Plant investment amount approximately JPY 220 billion. "
            "Mass production will commence from fiscal year 2027. "
            "SAP capacity will more than double by the end of FY2027."
        )
        parsed = w.parse_official_update(text, "https://www.ibiden.com/example")
        self.assertEqual(parsed["ibiden_capex_fy2026_2028_jpy_bn"], 500.0)
        self.assertEqual(parsed["ibiden_gama_capex_jpy_bn"], 220.0)
        self.assertEqual(parsed["ibiden_gama_mass_production_start_fy"], 2027)
        self.assertEqual(parsed["ibiden_sap_capacity_fy2027_multiple_min"], 2.0)

    def test_customer_sales_are_not_abf_share(self):
        text = (
            "Intel Corp. ¥ 76,709 million. "
            "Advanced Micro Devices Inc. ¥ 40,707 million. "
            "NVIDIA Corp. ¥ 75,077 million."
        )
        parsed = w.parse_official_update(text, "https://www.ibiden.com/example")
        sales = parsed["customer_sales_jpy_bn"]
        self.assertAlmostEqual(sales["Intel"], 76.709)
        self.assertAlmostEqual(sales["NVIDIA"], 75.077)
        self.assertNotIn("official_intel_abf_share_pct", parsed)

    def test_untrusted_macquarie_recap_does_not_parse(self):
        text = "Ibiden Intel 30% AMD 15% NVIDIA CPU substrate shipment started"
        self.assertEqual(w.parse_research_update(text, "https://example.com/foo"), {})

    def test_official_nvidia_cpu_confirmation(self):
        text = "Ibiden began mass production and shipment of package substrates for NVIDIA CPU."
        parsed = w.parse_official_update(text, "https://www.ibiden.com/example")
        self.assertTrue(parsed["official_nvidia_cpu_substrate_confirmed"])

    def test_area_structure_baseline_uses_area_layers_not_unit_count(self):
        base = w.ABF_AREA_STRUCTURE_BASELINE
        off = base["official"]
        self.assertEqual(off["ajinomoto_pc_substrate_area_index"], 1.0)
        self.assertEqual(off["ajinomoto_hpc_substrate_area_index"], 3.5)
        self.assertEqual(off["ajinomoto_pc_abf_layers"], 6)
        self.assertEqual(off["ajinomoto_hpc_abf_layers"], 18)
        self.assertEqual(off["ajinomoto_hpc_abf_use_multiple_min"], 10.0)
        self.assertTrue(off["ibiden_area_multilayer_increases_sap_load"])
        self.assertFalse(base["comparison_guard"]["like_for_like_comparison_confirmed"])

    def test_goldman_supply_gap_parser_keeps_source_specific_numbers(self):
        text = (
            "Goldman Sachs says the ABF substrate supply-demand gap is 34% in 2027 "
            "and the supply shortfall is 51% in 2028."
        )
        parsed = w.parse_research_update(text, "https://www.skis.com.tw/Report/industry/example.html")
        self.assertEqual(parsed["goldman_abf_shortfall_2027_pct"], 34.0)
        self.assertEqual(parsed["goldman_abf_shortfall_2028_pct"], 51.0)

    def test_feynman_area_parser_requires_research_scope(self):
        text = "Feynman 2028 ABF substrate area is estimated at 3-5 times the 2026 level."
        parsed = w.parse_research_update(text, "https://www.edaily.co.kr/example")
        self.assertEqual(parsed["feynman_2028_area_vs_2026_min_multiple"], 3.0)
        self.assertEqual(parsed["feynman_2028_area_vs_2026_max_multiple"], 5.0)


class AbfCpuMonetizationMaterialityTests(unittest.TestCase):
    def test_sap_ten_percent_change_triggers(self):
        previous = w.BASELINE
        updates = [{
            "url": "https://www.ibiden.com/new",
            "parsed": {
                "kind": "official_update",
                "ibiden_sap_capacity_fy2027_multiple_min": 2.3,
            }
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["key"] == "ibiden_sap_capacity_fy2027_multiple_min" for x in ev))

    def test_research_share_five_pp_change_triggers(self):
        previous = w.BASELINE
        updates = [{
            "url": "https://www.reuters.com/example",
            "parsed": {
                "kind": "research_update",
                "macquarie_intel_abf_share_pct": 36.0,
            }
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["type"] == "research_share" for x in ev))

    def test_same_research_baseline_is_quiet(self):
        previous = w.BASELINE
        updates = [{
            "url": "https://www.reuters.com/example",
            "parsed": {
                "kind": "research_update",
                "macquarie_intel_abf_share_pct": 30.0,
                "macquarie_amd_abf_share_pct": 15.0,
                "macquarie_nvidia_cpu_substrate_shipping": True,
            }
        }]
        self.assertEqual(w.material_events(previous, updates), [])

    def test_goldman_2028_five_pp_revision_triggers(self):
        previous = {**w.BASELINE, "area_structure": w.ABF_AREA_STRUCTURE_BASELINE}
        updates = [{
            "url": "https://www.skis.com.tw/Report/industry/example.html",
            "parsed": {
                "kind": "research_update",
                "goldman_abf_shortfall_2028_pct": 57.0,
            },
        }]
        ev = w.material_events(previous, updates)
        self.assertTrue(any(x["type"] == "supply_gap_forecast" for x in ev))


class AbfCpuMonetizationAlertTests(unittest.TestCase):
    def test_alert_has_required_sections_and_fact_separation(self):
        state = w.BASELINE
        events = [{
            "type": "official_confirmation",
            "key": "official_nvidia_cpu_substrate_confirmed",
            "url": "https://www.ibiden.com/example",
        }]
        alert = w.build_alert(events, state)
        self.assertIn("CPU·ABF 공급사 수익화 게이트", alert)
        self.assertIn("<b>수익구조</b>", alert)
        self.assertIn("<b>1단계 현재 숫자 추적</b>", alert)
        self.assertIn("<b>2단계 미래 재평가 요인 발굴</b>", alert)
        self.assertIn("<b>관련 기업 지도</b>", alert)
        self.assertIn("<b>공정 병목 후보</b>", alert)
        self.assertIn("<b>숨은 역풍·실패모드</b>", alert)
        self.assertIn("<b>결론</b>", alert)
        self.assertIn("<b>핵심 한 줄 요약</b>", alert)
        self.assertIn("Macquarie 추정 기준선", alert)
        self.assertIn("공식 확인 전 추정", alert)

        self.assertIn("기판 개수보다 면적×층수·SAP 부하", alert)
        self.assertIn("동일 범위 직접비교 금지", alert)
        self.assertIn("Goldman 2028 전망 51%", alert)

    def test_area_structure_upgrade_event_is_explicit(self):
        state = {**w.BASELINE, "area_structure": w.ABF_AREA_STRUCTURE_BASELINE}
        alert = w.build_alert([{
            "type": "area_structure_baseline",
            "key": "area_structure_v1",
            "url": w.ABF_AREA_STRUCTURE_BASELINE["official"]["ajinomoto_source"],
        }], state)
        self.assertIn("기판 병목 기준 업그레이드", alert)
        self.assertIn("면적×층수·SAP 공정부하", alert)
        self.assertIn("2021 역사 기준", alert)


if __name__ == "__main__":
    unittest.main()

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as r
import hbm_delivery as d


class RubinHBMUpgradeTests(unittest.TestCase):
    def base_event(self, category, text):
        return {
            "category": category,
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": "",
            "source": "TrendForce",
            "origin_source": "TrendForce",
            "quality": "신뢰 리서치·보도",
            "direct_link": "https://www.trendforce.com/example",
            "published_at_kst": "2026-09-29T20:00:00+09:00",
        }

    def test_bernstein_rubin_model_1024_to_640_is_distinct_from_official_spec(self):
        e = self.base_event(
            "rubin_broker_model",
            "Bernstein Rubin Ultra HBM assumption cut from 1,024GB to 640GB; half uses 8-Hi and half 12-Hi HBM",
        )
        x = r.make_fact(e)
        self.assertIsNotNone(x)
        self.assertEqual(x["fact_key"], "bernstein_rubin_ultra_model_1024_to_640_8hi50_12hi50")
        bullets = " ".join(x["fact_bullets"])
        self.assertIn("-37.5%", bullets)
        self.assertIn("+60.0%", bullets)
        self.assertIn("NVIDIA 공식 최종 사양과 분리", bullets)

    def test_bernstein_supplier_relative_change_uses_hbm_assumption_not_target_only(self):
        e = self.base_event(
            "hbm_supplier_relative",
            "Bernstein sees Samsung gaining HBM share and uses more conservative assumptions on SK Hynix HBM progress and pricing",
        )
        x = r.make_fact(e)
        self.assertIsNotNone(x)
        self.assertEqual(x["fact_key"], "bernstein_hbm_supplier_relative_samsung_up_skhynix_down")
        self.assertIn("목표주가 변경만으로는 발송하지 않습니다", x["verdict"])

    def test_current_bernstein_facts_are_seeded_to_prevent_retro_alert(self):
        self.assertEqual(r.STRUCTURE_BASELINE_VERSION, 3)
        self.assertIn("bernstein_rubin_ultra_model_1024_to_640_8hi50_12hi50", r.KNOWN_STRUCTURE_FACT_KEYS)
        self.assertIn("bernstein_hbm_supplier_relative_samsung_up_skhynix_down", r.KNOWN_STRUCTURE_FACT_KEYS)
        self.assertIn("bernstein_hbm_supplier_relative_samsung_up", r.KNOWN_STRUCTURE_FACT_KEYS)
        self.assertIn("bernstein_hbm_supplier_relative_skhynix_down", r.KNOWN_STRUCTURE_FACT_KEYS)

    def test_contract_signed_without_percentage_alerts(self):
        e = self.base_event("hbm_2027_contract", "TrendForce: 2027 HBM contract signed and pricing agreement finalized")
        x = r.make_fact(e)
        self.assertIsNotNone(x)
        self.assertIn("signed", x["fact_key"])
        self.assertIn("계약 체결", " ".join(x["fact_bullets"]))

    def test_rubin_final_8hi_spec_without_capacity_alerts(self):
        e = self.base_event("rubin_spec", "NVIDIA Rubin Ultra final specification confirmed with 8-Hi HBM4E")
        x = r.make_fact(e)
        self.assertIsNotNone(x)
        self.assertIn("final", x["fact_key"])
        self.assertIn("8hi", x["fact_key"])

    def test_hbm4e_yield_bottleneck_alerts(self):
        e = self.base_event("hbm4e_validation", "Samsung HBM4E low yield bottleneck at 62%")
        x = r.make_fact(e)
        self.assertIsNotNone(x)
        self.assertIn("yield", x["fact_key"])
        self.assertIn("62", " ".join(x["fact_bullets"]))

    def test_wafer_economics_direction_alerts(self):
        e = self.base_event("hbm_wafer_economics", "TrendForce HBM wafer revenue fell below DDR5 64GB RDIMM profitability")
        x = r.make_fact(e)
        self.assertIsNotNone(x)
        self.assertIn("hbm_below_ddr5", x["fact_key"])

    def test_memory_migration_is_independent_telegram_message_when_mixed(self):
        a = self.base_event("rubin_spec", "NVIDIA Rubin Ultra final specification confirmed with 8-Hi HBM4E")
        a = r.make_fact(a)
        a["verification"] = "신뢰자료 확인"
        b = self.base_event("memory_migration", "TrendForce HBM capacity reduction drives KV cache offload; 8-Hi mainstream and enterprise SSD demand")
        b = r.make_fact(b)
        b["verification"] = "신뢰자료 확인"
        text = r.build_alert(r.datetime(2026,9,29,20,0,tzinfo=r.ZoneInfo("Asia/Seoul")), [a,b], {"rate":1350.0,"date":"test"})
        parts = d.chunks(text)
        self.assertGreaterEqual(len(parts), 2)
        self.assertIn("Rubin/HBM 구조 변화 감시", parts[0])
        self.assertTrue(any("KV 캐시 외부 메모리 전환" in p for p in parts[1:]))


if __name__ == "__main__":
    unittest.main()

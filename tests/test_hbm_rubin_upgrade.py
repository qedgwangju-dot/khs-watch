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

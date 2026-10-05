import copy
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import solidigm_ipo_watch as w


class SolidigmIPOTests(unittest.TestCase):
    def test_reuters_baseline_stage_and_amounts(self):
        text = (
            "Solidigm is considering an initial public offering as early as 2027 that could value "
            "the unit at up to $150 billion. Solidigm held pitch meetings with investment banks "
            "in a bake-off. The company could raise $15 billion in the IPO."
        )
        self.assertEqual(w.stage_from_text(text), "bank_bakeoff")
        self.assertEqual(w.usd_amount(text, r"(?:valu(?:e|ed|ation)|기업가치)"), 150_000_000_000)
        self.assertEqual(w.usd_amount(text, r"(?:raise|raising|proceeds|조달)"), 15_000_000_000)

    def test_stage_progression_is_material(self):
        old = {"stage": "bank_bakeoff", "target_year": 2027, "valuation_max_usd": 150_000_000_000,
               "raise_target_usd": 15_000_000_000, "evidence_state": "top_tier_report"}
        new = copy.deepcopy(old)
        new["stage"] = "underwriters_selected"
        reasons = w.material_changes(old, new)
        self.assertTrue(any("상장 단계" in x for x in reasons))

    def test_sparse_report_does_not_erase_known_values(self):
        old = {"stage": "bank_bakeoff", "target_year": 2027, "valuation_max_usd": 150_000_000_000,
               "raise_target_usd": 15_000_000_000, "evidence_state": "top_tier_report"}
        patch = {"stage": "bank_bakeoff", "evidence_state": "reported", "source_url": "https://example.com"}
        merged = w.merge_state(old, patch)
        self.assertEqual(merged["valuation_max_usd"], 150_000_000_000)
        self.assertEqual(merged["raise_target_usd"], 15_000_000_000)
        self.assertEqual(merged["target_year"], 2027)

    def test_official_confirmation_is_material(self):
        old = {"stage": "bank_bakeoff", "evidence_state": "top_tier_report"}
        new = {"stage": "bank_bakeoff", "evidence_state": "official"}
        self.assertTrue(any("공식 확인" in x for x in w.material_changes(old, new)))

    def test_lower_stage_does_not_regress(self):
        old = {"stage": "bank_bakeoff"}
        merged = w.merge_state(old, {"stage": "exploring"})
        self.assertEqual(merged["stage"], "bank_bakeoff")

    def test_withdrawal_overrides_progress_stage(self):
        old = {"stage": "public_filing"}
        merged = w.merge_state(old, {"stage": "withdrawn"})
        self.assertEqual(merged["stage"], "withdrawn")

    def test_unrelated_delay_language_is_not_solidigm_postponement(self):
        text = (
            "Solidigm is considering an IPO as early as 2027. "
            "Separately, another semiconductor project was delayed by market conditions."
        )
        self.assertEqual(w.stage_from_text(text), "exploring")

    def test_lower_tier_report_cannot_override_reuters_baseline(self):
        old = {
            "stage": "bank_bakeoff",
            "evidence_state": "top_tier_report",
            "source_url": "https://www.reuters.com/example",
            "source_name": "Reuters",
            "valuation_max_usd": 150_000_000_000,
        }
        patch = {
            "stage": "postponed",
            "evidence_state": "reported",
            "source_url": "https://example.com/secondary",
            "source_name": "Secondary",
            "underwriters": ["UBS"],
        }
        merged = w.merge_state(old, patch)
        self.assertEqual(merged["stage"], "bank_bakeoff")
        self.assertEqual(merged["evidence_state"], "top_tier_report")
        self.assertEqual(merged["source_name"], "Reuters")

    def test_manufacturing_article_extracts_taiwan_odm_without_fake_customer(self):
        item = {
            "title": "AI 서버 붐 탄 솔리다임, 대만 SSD 위탁생산 거점 확대",
            "description": "Solidigm adds a Taiwan ODM manufacturing site for data center SSDs.",
            "source": "아주경제",
            "published_at_kst": "2026-10-05T16:09:00+09:00",
            "direct_link": "https://www.ajunews.com/view/20261005160404868",
        }
        body = (
            "솔리다임은 대만 내 데이터센터용 SSD 위탁생산(ODM) 제조 거점을 신규 추가한다. "
            "새 거점 제품은 기존 품질 표준을 유지한 채 오는 12월부터 글로벌 고객사로 출하될 예정이다. "
            "파워텍테크놀로지(PTI), 페가트론 등 현지 파트너사를 활용해 위탁생산을 진행해왔다. "
            "폭스콘, 콴타, 위스트론은 대만의 주요 AI 서버 업체다."
        )
        with patch.object(w, "article_text", return_value=body):
            data = w.extract_manufacturing_patch(item)
        self.assertEqual(data["reported_site_country"], "Taiwan")
        self.assertEqual(data["reported_manufacturing_model"], "ODM")
        self.assertEqual(data["reported_ship_start_month"], "2026-12")
        self.assertTrue(data["reported_quality_standard_unchanged"])
        self.assertEqual(set(data["reported_existing_odm_partners"]), {"PTI", "Pegatron"})
        self.assertEqual(data.get("confirmed_direct_server_customers", []), [])
        self.assertEqual(data["manufacturing_scope"], "ssd_manufacturing_not_nand_wafer_fab")

    def test_official_pcn_scope_is_all_datacenter_ssds(self):
        item = {
            "title": "Additional Manufacturing Site for all Solidigm Datacenter SSDs",
            "description": "PCN 0000048112-00",
            "source": "Solidigm",
            "published_at_kst": "2026-09-25T00:00:00+09:00",
            "direct_link": "https://www.solidigm.com/products/document-management-system.html",
        }
        data = w.manufacturing_patch_from_text(
            item,
            "Solidigm PCN 0000048112-00 Additional Manufacturing Site for all Solidigm Datacenter SSDs",
        )
        self.assertEqual(data["pcn_number"], "0000048112-00")
        self.assertEqual(data["affected_scope"], "all_solidigm_datacenter_ssds")

    def test_manufacturing_baseline_current_story_is_silent(self):
        old = dict(w.MANUFACTURING_BASELINE)
        new = dict(old)
        self.assertEqual(w.manufacturing_material_changes(old, new), [])

    def test_actual_shipping_is_material(self):
        old = dict(w.MANUFACTURING_BASELINE)
        new = dict(old, stage="shipping")
        reasons = w.manufacturing_material_changes(old, new)
        self.assertTrue(any("출하 시작" in x for x in reasons))

    def test_capacity_first_disclosure_is_material(self):
        old = dict(w.MANUFACTURING_BASELINE)
        new = dict(old, capacity_units_per_month=250000)
        reasons = w.manufacturing_material_changes(old, new)
        self.assertTrue(any("생산능력" in x and "최초 공개" in x for x in reasons))

    def test_generic_ai_ssd_business_text_is_not_use_of_proceeds(self):
        item = {
            "title": "Solidigm weighs IPO",
            "description": "Solidigm sells AI data-center SSDs and may raise capital.",
            "source": "Reuters",
            "published_at_kst": "2026-09-26T01:47:00+09:00",
            "direct_link": "https://www.reuters.com/example",
        }
        with patch.object(w, "article_text", return_value="Solidigm sells enterprise SSDs for AI data centers."):
            patch_data = w.extract_patch(item)
        self.assertNotIn("use_of_proceeds", patch_data)


if __name__ == "__main__":
    unittest.main()

import copy
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import solidigm_ipo_watch as w
import hbm_delivery as delivery


class SolidigmIPOTests(unittest.TestCase):

    def _bloomberg_selected_event(self):
        return {
            "id": "solidigm_bloomberg_banks_20261008",
            "title": "Bloomberg: Solidigm selected Goldman Sachs and Morgan Stanley to lead IPO",
            "description": (
                "Solidigm selected Goldman Sachs and Morgan Stanley as lead underwriters "
                "for its potential US IPO. JPMorgan Chase, Citigroup and UBS join the syndicate. "
                "The IPO could raise $10 billion and value Solidigm at up to $100 billion. "
                "It could happen as soon as 2027. Pre-IPO financing being considered, "
                "its precise amount unconfirmed; no company IPO decision confirmed."
            ),
            "source": "Bloomberg 보도(이데일리·연합뉴스·Investing.com 재인용)",
            "published_at_kst": "2026-10-08T07:48:01+09:00",
            "direct_link": w.REPORT_EDAILY_URL,
            "is_curated_reported_milestone": True,
        }

    def test_bloomberg_selection_is_reported_not_official(self):
        event = self._bloomberg_selected_event()
        with patch.object(w, "article_text", return_value=""):
            out = w.extract_patch(event)
        self.assertEqual(out["stage"], "underwriters_selected")
        self.assertEqual(out["evidence_state"], "top_tier_report")
        self.assertEqual(out["reported_original"], "Bloomberg")
        self.assertEqual(out["independent_origin_count"], 1)
        self.assertFalse(out["ipo_officially_confirmed"])
        self.assertFalse(out["underwriter_officially_confirmed"])
        self.assertEqual(out["lead_underwriters"], ["Goldman Sachs", "Morgan Stanley"])
        self.assertEqual(out["other_syndicate_banks"], ["JPMorgan Chase", "Citigroup", "UBS"])
        self.assertEqual(out["raise_target_usd"], 10_000_000_000)
        self.assertEqual(out["valuation_max_usd"], 100_000_000_000)
        self.assertNotIn("pre_ipo_raise_usd", out)
        self.assertEqual(out["user_original_url"], w.REPORT_YONHAP_URL)

    def test_baseline_stage_is_upgraded_only_once(self):
        old = {
            "stage": "bank_bakeoff",
            "target_year": 2027,
            "valuation_max_usd": 150_000_000_000,
            "raise_target_usd": 15_000_000_000,
            "pre_ipo_raise_usd": 3_600_000_000,
            "source_name": "Reuters",
            "source_url": w.CANONICAL_REUTERS_URL,
            "evidence_state": "top_tier_report",
            "underwriters": [],
        }
        with patch.object(w, "article_text", return_value=""):
            patch_data = w.extract_patch(self._bloomberg_selected_event())
        upgraded = w.merge_state(old, patch_data)
        self.assertEqual(upgraded["stage"], "underwriters_selected")
        self.assertEqual(upgraded["raise_target_usd"], 10_000_000_000)
        self.assertEqual(upgraded["valuation_max_usd"], 100_000_000_000)
        self.assertEqual(upgraded["source_url"], w.REPORT_EDAILY_URL)
        self.assertIn("대표주관사", " / ".join(w.material_changes(old, upgraded)))
        self.assertEqual(w.material_changes(upgraded, w.merge_state(upgraded, patch_data)), [])
        alert = w.alert_text(old, upgraded, w.material_changes(old, upgraded), w.now_kst())
        self.assertIn("대표주관사(블룸버그 보도)", alert)
        self.assertIn("확정 공모금액 감액이 아니라", alert)
        self.assertIn("별개 독립 확인 3건이 아닙니다", alert)
        self.assertIn("신주·구주 비율", alert)
        self.assertIn("연합뉴스", alert)
        self.assertIn("SK하이닉스 공식 입장", alert)
        self.assertTrue(delivery.chunks(alert))

    def test_reposted_article_not_three_independent_sources(self):
        event = self._bloomberg_selected_event()
        with patch.object(w, "article_text", return_value=""):
            rec = w.extract_patch(event)
        self.assertEqual(rec["independent_origin_count"], 1)
        self.assertEqual(rec["crosscheck_url"], w.REPORT_INVESTING_URL)

    def test_older_bakeoff_cannot_replace_new_bank_selection_estimates(self):
        chosen = {
            "stage": "underwriters_selected",
            "valuation_max_usd": 100_000_000_000,
            "raise_target_usd": 10_000_000_000,
            "evidence_state": "top_tier_report",
            "source_name": "Bloomberg",
        }
        older = {
            "stage": "bank_bakeoff",
            "valuation_max_usd": 150_000_000_000,
            "raise_target_usd": 15_000_000_000,
            "evidence_state": "official",
            "source_name": "Generic SK hynix no-decision statement",
        }
        self.assertEqual(w.merge_state(chosen, older), chosen)

    def test_official_no_decision_does_not_confirm_ipo(self):
        statement = {
            "title": "SK hynix clarification: Solidigm IPO no definitive funding plan",
            "description": "Solidigm is reviewing options. No concrete plans have been confirmed.",
            "source": "SK hynix",
            "direct_link": w.OFFICIAL_SK_REPLY,
            "published_at_kst": "2026-10-01T13:00:00+09:00",
        }
        with patch.object(w, "article_text", return_value="IPO capital plans are undecided"):
            self.assertEqual(w.extract_patch(statement), {})

    def test_korean_yonhap_company_name_is_supported(self):
        event = {
            "title": "블룸버그, 솔리다임 IPO 대표주관사 선정",
            "description": "골드만삭스와 모건스탠리를 대표주관사로 선정한 것으로 보도됐다.",
            "source": "연합뉴스",
            "published_at_kst": "2026-10-08T08:00:00+09:00",
            "direct_link": w.REPORT_YONHAP_URL,
        }
        with patch.object(w, "article_text", return_value=""):
            rec = w.extract_patch(event)
        self.assertEqual(rec["stage"], "underwriters_selected")
        self.assertEqual(rec["lead_underwriters"], ["Goldman Sachs", "Morgan Stanley"])
        self.assertNotEqual(rec["evidence_state"], "official")

    def test_full_page_unrelated_ipo_does_not_change_stage(self):
        event = {
            "title": "Solidigm weighs an IPO",
            "description": "Solidigm IPO is under review.",
            "source": "Reuters",
            "direct_link": w.CANONICAL_REUTERS_URL,
        }
        page = "Another unrelated issuer's IPO was postponed and then priced at $30 billion."
        with patch.object(w, "article_text", return_value=page):
            rec = w.extract_patch(event)
        self.assertEqual(rec.get("stage"), "exploring")
        self.assertNotIn("valuation_max_usd", rec)

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

    def test_quality_failure_is_material(self):
        old = dict(w.MANUFACTURING_BASELINE)
        new = dict(old, quality_issue_status="reported")
        reasons = w.manufacturing_material_changes(old, new)
        self.assertTrue(any("품질 상태" in x and "이슈 발생" in x for x in reasons))

    def test_customer_qualification_pass_is_material(self):
        old = dict(w.MANUFACTURING_BASELINE)
        new = dict(old, customer_qualification_stage="passed")
        reasons = w.manufacturing_material_changes(old, new)
        self.assertTrue(any("고객 검증 단계" in x and "통과" in x for x in reasons))

    def test_explicit_quality_failure_parser(self):
        item = {
            "title": "Solidigm Taiwan data center SSD ODM qualification update",
            "description": "",
            "source": "Solidigm",
            "published_at_kst": "2026-11-02T10:00:00+09:00",
            "direct_link": "https://www.solidigm.com/example",
        }
        data = w.manufacturing_patch_from_text(
            item,
            "Solidigm data center SSD ODM manufacturing site reports a quality issue and customer qualification failed.",
        )
        self.assertEqual(data["quality_issue_status"], "reported")
        self.assertEqual(data["customer_qualification_stage"], "failed")

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

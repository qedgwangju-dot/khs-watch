import copy
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import tsmc_advanced_packaging_watch as w


def event(title, desc="", source="LTN", url=w.LTN_CANONICAL_URL):
    return {
        "title": title,
        "description": desc,
        "source": source,
        "published_at_kst": "2026-09-27T03:41:00+09:00",
        "direct_link": url,
    }


class TSMCAdvancedPackagingTests(unittest.TestCase):
    def test_current_ltn_report_locks_ten_total_and_five_additional(self):
        item = event("獨家》一共10座！嘉科三期起跑 台積電再加碼5座先進封裝廠")
        with patch.object(w, "article_text", return_value=""):
            p = w.extract_patch(item)
        self.assertEqual(p["chiayi_total_fabs"], 10)
        self.assertEqual(p["chiayi_additional_fabs"], 5)
        self.assertEqual(p["fab_count_evidence_state"], "supply_chain_report")

    def test_public_comment_plan_is_not_hbm_cross_trigger(self):
        old = {"chiayi_total_fabs": 10, "chiayi_additional_fabs": 5, "chiayi_phase3_status": "reported_intent"}
        new = copy.deepcopy(old)
        new["chiayi_phase3_status"] = "public_comment"
        self.assertEqual(w.hbm_cross_reasons(old, new), [])

    def test_tool_move_in_is_hbm_cross_trigger(self):
        old = {"fabs": {"P3": {"status": "construction", "evidence_state": "official"}}}
        new = {"fabs": {"P3": {"status": "tool_move_in", "evidence_state": "official"}}}
        reasons = w.hbm_cross_reasons(old, new)
        self.assertTrue(any("P3" in r and "장비 반입" in r for r in reasons))

    def test_cowos_capacity_change_is_hbm_cross_trigger(self):
        old = {"cowos_capacity_wpm": 120000}
        new = {"cowos_capacity_wpm": 140000}
        reasons = w.hbm_cross_reasons(old, new)
        self.assertTrue(any("120,000→140,000" in r for r in reasons))

    def test_future_guidance_does_not_promote_fab_to_current_mass_production(self):
        text = "台積電嘉義 P2 廠預計明年量產，工程目前依計畫進行。"
        fabs = w.parse_fab_statuses(text, "top_tier_report", "https://example.com")
        self.assertNotIn("P2", fabs)

    def test_official_same_count_upgrade_is_package_material_but_not_hbm_cross(self):
        old = {"chiayi_total_fabs": 10, "fab_count_evidence_state": "supply_chain_report"}
        new = {"chiayi_total_fabs": 10, "fab_count_evidence_state": "official"}
        self.assertTrue(any("공식 확인" in r for r in w.material_changes(old, new)))
        self.assertEqual(w.hbm_cross_reasons(old, new), [])

    def test_lower_evidence_cannot_overwrite_official_phase(self):
        old = {"chiayi_phase3_status": "approved", "phase3_evidence_state": "official"}
        merged = w.merge_state(old, {
            "chiayi_phase3_status": "construction",
            "phase3_evidence_state": "reported",
            "last_evidence_state": "reported",
        })
        self.assertEqual(merged["chiayi_phase3_status"], "approved")

    def test_package_alert_translates_hanja_to_korean(self):
        state = {
            "chiayi_total_fabs": 10,
            "chiayi_additional_fabs": 5,
            "chiayi_phase3_status": "public_comment",
            "fab_count_evidence_state": "supply_chain_report",
            "phase3_evidence_state": "official",
            "last_source_name": "自由時報",
            "last_source_url": "https://example.com/嘉義",
        }
        reasons = ["자이 첨단패키징 공장 총계 5→10개", "자이 과학단지 확대 단계 공급망 투자 의향 보도→부지 확대 의견수렴"]
        text = w.package_alert_text(state, reasons, w.now_kst())
        self.assertNotRegex(text, w.HAN_RE)
        self.assertIn("TSMC 첨단패키징·자이 상태 변화", text)
        self.assertIn("자이 과학단지 확대 단계", text)
        self.assertIn("LTN", text)

    def test_hanja_guard_blocks_unknown_untranslated_text(self):
        with self.assertRaises(ValueError):
            w.koreanize_alert_text("알림 본문 未翻譯")

    def test_material_change_reasons_are_korean(self):
        old = {"chiayi_total_fabs": 5, "chiayi_phase3_status": "reported_intent"}
        new = {"chiayi_total_fabs": 10, "chiayi_phase3_status": "public_comment"}
        reasons = w.material_changes(old, new)
        self.assertTrue(any("자이 첨단패키징" in x for x in reasons))
        self.assertTrue(any("자이 과학단지 확대 단계" in x for x in reasons))
        self.assertFalse(any(w.HAN_RE.search(x) for x in reasons))

    def test_foundry_ai_capacity_change_cross_triggers_hbm(self):
        old = {"n2_2026ye_wpm": 100000, "reservation_min_pct": 10, "reservation_max_pct": 20, "ai_hbm_customers": ["NVIDIA", "AMD"], "n2_fabs_2026": 5}
        new = {"n2_2026ye_wpm": 120000, "reservation_min_pct": 10, "reservation_max_pct": 20, "ai_hbm_customers": ["NVIDIA", "AMD"], "n2_fabs_2026": 5}
        reasons = w._foundry_hbm_cross_reasons(old, new)
        self.assertTrue(any("100,000→120,000" in x for x in reasons))

    def test_apple_only_foundry_change_does_not_cross_trigger_hbm(self):
        old = {"n2_2026ye_wpm": 100000, "reservation_min_pct": 10, "reservation_max_pct": 20, "ai_hbm_customers": []}
        new = {"n2_2026ye_wpm": 120000, "reservation_min_pct": 20, "reservation_max_pct": 30, "ai_hbm_customers": []}
        self.assertEqual(w._foundry_hbm_cross_reasons(old, new), [])

    def test_cross_alert_shows_front_back_memory_bottleneck_map(self):
        package = {"bottlenecks": {"cowos": {"status": "easing"}, "substrate": {"status": "tight"}, "hbm": {"status": "easing"}}}
        foundry = {"n2_2026ye_wpm": 120000, "ai_hbm_customers": ["AMD", "NVIDIA"]}
        out = w.hbm_alert_text(package, ["AI 고객 연계 N2 월 생산능력 변화"], w.now_kst(), foundry)
        self.assertIn("앞단", out)
        self.assertIn("후단", out)
        self.assertIn("메모리", out)
        self.assertIn("NVIDIA", out)


if __name__ == "__main__":
    unittest.main()

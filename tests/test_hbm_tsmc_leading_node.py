import copy
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import tsmc_leading_node_watch as w


def event(text, source="경제일보"):
    return {
        "id": "e1",
        "title": "TSMC 2nm capacity update",
        "description": text,
        "source": source,
        "published_at_kst": "2026-09-28T02:06:00+09:00",
        "direct_link": w.UDN_BASELINE,
        "evidence_state": "supply_chain_report",
    }


class TSMCLeadingNodeTests(unittest.TestCase):
    def test_current_udn_extracts_120k_and_customer_additional_booking(self):
        text = (
            "台積電2奈米家族今年底月產能將衝刺12萬片。"
            "蘋果、輝達、超微、高通、聯發科近期追加預訂2奈米產能，增幅達10%至20%。"
        )
        e = event(text)
        with patch.object(w, "article_text", return_value=""):
            p = w.extract_patch(e)
        self.assertEqual(p["capacity_targets"]["N2|2026YE"]["value"], 120000)
        self.assertEqual(p["customer_reservation"]["min_pct"], 10)
        self.assertEqual(p["customer_reservation"]["max_pct"], 20)
        self.assertEqual(p["customer_reservation"]["ai_hbm_customers"], ["AMD", "NVIDIA"])

    def test_old_90_100k_reference_does_not_override_new_120k_target(self):
        text = (
            "市場原本預估今年底2奈米月產能約9萬至10萬片。"
            "業界傳出今年底2奈米月產能將衝刺12萬片。"
        )
        caps = w._capacity_targets(text, event(text))
        self.assertEqual(caps["N2|2026YE"]["value"], 120000)

    def test_capacity_threshold_is_10k_or_10pct(self):
        old = {"capacity_targets": {"N2|2026YE": {"value": 120000, "evidence_state": "supply_chain_report"}}}
        small = {"capacity_targets": {"N2|2026YE": {"value": 125000, "evidence_state": "supply_chain_report"}}}
        big = {"capacity_targets": {"N2|2026YE": {"value": 132000, "evidence_state": "supply_chain_report"}}}
        self.assertEqual(w.material_changes(old, small), [])
        self.assertTrue(any("120,000→132,000" in x for x in w.material_changes(old, big)))

    def test_customer_booking_10pp_change_alerts(self):
        old = {"customer_reservation": {"min_pct": 10.0, "max_pct": 20.0, "customers": ["AMD", "NVIDIA"], "evidence_state": "supply_chain_report"}}
        new = {"customer_reservation": {"min_pct": 20.0, "max_pct": 30.0, "customers": ["AMD", "NVIDIA"], "evidence_state": "supply_chain_report"}}
        self.assertTrue(any("10~20%→20~30%" in x for x in w.material_changes(old, new)))

    def test_wafer_price_five_percent_change_alerts(self):
        old = {"wafer_prices": {"N2": {"value_usd": 30000, "evidence_state": "supply_chain_report"}}}
        new = {"wafer_prices": {"N2": {"value_usd": 31500, "evidence_state": "supply_chain_report"}}}
        self.assertTrue(any("N2 웨이퍼 가격 +5.0%" in x for x in w.material_changes(old, new)))

    def test_same_baseline_stays_silent(self):
        cur = {
            "capacity_targets": {"N2|2026YE": {"value": 120000, "evidence_state": "supply_chain_report"}},
            "customer_reservation": {"min_pct": 10.0, "max_pct": 20.0, "customers": ["AMD", "Apple", "NVIDIA"], "evidence_state": "supply_chain_report"},
        }
        self.assertEqual(w.material_changes(cur, copy.deepcopy(cur)), [])

    def test_terafab_musk_confirmation_is_discussion_not_deal(self):
        e = {
            "title": "Elon Musk confirms TSMC-Terafab talks",
            "description": "",
            "source": "Culpium",
            "published_at_kst": "2026-10-03T07:51:00+09:00",
            "direct_link": w.TERAFAB_CULPIUM_URL,
            "evidence_state": "reported",
        }
        text = (
            "TSMC is exploring ways to work with Elon Musk's Terafab in Texas. "
            "Terafab may become an anchor customer for a future TSMC Texas factory. "
            "The most likely scenario is for TSMC to own and operate the new factory. "
            "Musk wrote: Just discussions, but something may come of it."
        )
        p = w.terafab_patch_from_text(e, text)
        self.assertEqual(p["stage"], "confirmed_discussions")
        self.assertTrue(p["musk_confirmed_discussions"])
        self.assertEqual(p["evidence_state"], "founder_confirmation")
        self.assertEqual(p["terafab_anchor_customer_stage"], "reported_option")
        self.assertEqual(p["tsmc_factory_role"], "reported_possible_owner_operator")
        self.assertFalse(p.get("definitive_agreement", False))
        self.assertFalse(p.get("tsmc_official_confirmation", False))

    def test_terafab_baseline_same_state_is_silent(self):
        old = copy.deepcopy(w.TERAFAB_BASELINE)
        self.assertEqual(w.terafab_material_changes(old, copy.deepcopy(old)), [])

    def test_tsmc_official_definitive_agreement_is_material(self):
        old = copy.deepcopy(w.TERAFAB_BASELINE)
        e = {
            "title": "TSMC and Terafab sign definitive agreement",
            "description": "",
            "source": "TSMC",
            "published_at_kst": "2026-11-01T10:00:00+09:00",
            "direct_link": "https://www.tsmc.com/english/news/terafab",
            "evidence_state": "official",
        }
        p = w.terafab_patch_from_text(
            e,
            "TSMC and Terafab signed a definitive agreement for a Texas facility. TSMC will build and operate the fab."
        )
        new = w.merge_terafab_state(old, p)
        reasons = w.terafab_material_changes(old, new)
        self.assertTrue(new["tsmc_official_confirmation"])
        self.assertTrue(new["definitive_agreement"])
        self.assertEqual(new["stage"], "definitive_agreement")
        self.assertTrue(any("본계약" in x for x in reasons))
        self.assertTrue(any("TSMC 공식 확인" in x for x in reasons))

    def test_arizona_265b_is_not_reused_as_texas_capex(self):
        e = {
            "title": "TSMC Texas discussion",
            "description": "",
            "source": "Reuters",
            "published_at_kst": "2026-10-05T10:00:00+09:00",
            "direct_link": w.TERAFAB_REUTERS_TEXAS_URL,
            "evidence_state": "top_tier_report",
        }
        text = (
            "TSMC is evaluating a Texas collaboration with Terafab. "
            "Separately, TSMC has committed $265 billion to Arizona."
        )
        p = w.terafab_patch_from_text(e, text)
        self.assertNotIn("tsmc_texas_capex_usd", p)

    def test_intel_14a_context_does_not_become_tsmc_node_or_replacement(self):
        e = {
            "title": "TSMC-Terafab talks",
            "description": "",
            "source": "Culpium",
            "published_at_kst": "2026-10-05T10:00:00+09:00",
            "direct_link": w.TERAFAB_CULPIUM_URL,
            "evidence_state": "reported",
        }
        p = w.terafab_patch_from_text(
            e,
            "TSMC is in discussions with Terafab in Texas. Intel remains an existing Terafab partner using Intel 14A. "
            "TSMC may supplement Intel rather than replace it."
        )
        self.assertEqual(p["intel_role"], "existing_14A_partner")
        self.assertEqual(p["intel_displacement_status"], "not_confirmed_supplementary")
        self.assertNotIn("tsmc_terafab_process_node", p)

    def test_terafab_capacity_and_process_first_disclosure_alert(self):
        old = copy.deepcopy(w.TERAFAB_BASELINE)
        e = {
            "title": "TSMC confirms Texas Terafab capacity",
            "description": "",
            "source": "TSMC",
            "published_at_kst": "2026-12-01T10:00:00+09:00",
            "direct_link": "https://www.tsmc.com/english/news/terafab",
            "evidence_state": "official",
        }
        p = w.terafab_patch_from_text(
            e,
            "TSMC and Terafab will build a Texas N2 fab. TSMC Texas Terafab capacity will be 40,000 wafers per month."
        )
        new = w.merge_terafab_state(old, p)
        reasons = w.terafab_material_changes(old, new)
        self.assertEqual(new["tsmc_terafab_process_node"], "N2")
        self.assertEqual(new["tsmc_texas_capacity_wpm"], 40000)
        self.assertTrue(any("TSMC 적용 공정" in x for x in reasons))
        self.assertTrue(any("월 생산능력" in x and "최초 공개" in x for x in reasons))

    def test_node_and_terafab_alerts_are_separate_telegram_messages(self):
        payload = w.compose_alerts("<b>node</b>", "<b>terafab</b>")
        self.assertIn("<<<TELEGRAM_MESSAGE_BREAK>>>", payload)

    def test_alert_has_no_hanja(self):
        state = {
            "capacity_targets": {"N2|2026YE": {"value": 120000}, "N3|2026Q4": {"value": 180000}, "N3|2027": {"min": 200000, "max": 210000}},
            "customer_reservation": {"min_pct": 10.0, "max_pct": 20.0, "customers": ["Apple", "NVIDIA", "AMD"]},
            "n2_fabs_2026": 5,
            "n2_first_year_vs_n3_pct": 45,
            "n2_cagr_2026_2028_pct": 70,
            "n2_gross_margin_dilution": {"min_pp": 2.0, "max_pp": 3.0},
            "last_source_url": w.UDN_BASELINE,
            "last_source_name": "經濟日報",
        }
        out = w.alert_text(state, ["N2|2026YE 월 생산능력 100,000→120,000장 (+20.0%)"], w.now_kst())
        self.assertNotRegex(out, w.HAN_RE)
        self.assertIn("경제일보", out)


if __name__ == "__main__":
    unittest.main()

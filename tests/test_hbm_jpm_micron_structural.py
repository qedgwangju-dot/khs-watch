import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


class JPMHBMStructuralTests(unittest.TestCase):
    def event(self, text, category, source):
        return {
            "category": category,
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": source,
            "origin_source": source,
            "published_at_kst": "2026-09-23T14:55:00+09:00",
            "direct_link": "https://example.com/source",
        }

    def test_jpm_baseline_extracts_periods_without_fake_2027_bit_growth(self):
        text = (
            "JPMorgan says HBM bit demand CAGR from 2026 to 2028 reaches 63%. "
            "Cumulative bit demand is 163 billion GB. HBM average selling price rises 54% in 2027 "
            "and 25% in 2028, reaching $3.8 per GB in 2028. "
            "The supply-demand gap improves from -20% to -16%. "
            "58% of new DRAM capacity from 2025 to 2028 will be directed toward HBM. "
            "HBM share of total DRAM capacity rises from 19% to 31%. "
            "16-Hi is delayed until at least 2029. "
            "By 2027 ASIC HBM demand share rises to 48% and NVIDIA falls to 43%."
        )
        obs = w.extract_jpm_hbm_structural(self.event(text, "jpm_hbm_structural", "GMT Eight"))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["demand_cagr_2026_2028_pct"], 63.0)
        self.assertEqual(obs["demand_cagr_period"], "2026-2028")
        self.assertNotIn("bit_growth_2027_pct", obs)
        self.assertEqual(obs["asp_2027_yoy_pct"], 54.0)
        self.assertEqual(obs["asp_2028_yoy_pct"], 25.0)
        self.assertEqual(obs["asp_2028_usd_per_gb"], 3.8)
        self.assertEqual(obs["hbm_share_dram_capacity_start_pct"], 19.0)
        self.assertEqual(obs["hbm_share_dram_capacity_2028_pct"], 31.0)
        self.assertEqual(obs["new_dram_capacity_to_hbm_pct_2025_2028"], 58.0)
        self.assertEqual(obs["sixteen_hi_earliest_year"], 2029)
        self.assertEqual(obs["asic_hbm_demand_share_2027_pct"], 48.0)
        self.assertEqual(obs["nvidia_hbm_demand_share_2027_pct"], 43.0)

    def test_jpm_same_baseline_is_silent(self):
        old = dict(w.JPM_HBM_STRUCTURAL_BASELINE)
        self.assertEqual(w.jpm_hbm_structural_changes(old, dict(old)), [])

    def test_jpm_material_revision_alerts(self):
        old = dict(w.JPM_HBM_STRUCTURAL_BASELINE)
        new = dict(old, asp_2027_yoy_pct=62.0, hbm_share_dram_capacity_2028_pct=34.0)
        reasons = w.jpm_hbm_structural_changes(old, new)
        self.assertTrue(any("2027 HBM 평균판매단가" in x for x in reasons))
        self.assertTrue(any("2028 HBM의 DRAM 생산능력 비중" in x for x in reasons))


class MicronSCAVisibilityTests(unittest.TestCase):
    def event(self, text, source="Micron Technology"):
        return {
            "category": "micron_sca_visibility",
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": source,
            "origin_source": source,
            "published_at_kst": "2026-09-30T16:30:00-04:00",
            "direct_link": "https://stockanalysis.com/stocks/mu/transcripts/699706-q4-2026/",
        }

    def test_micron_contract_baseline_semantics(self):
        text = (
            "Micron has signed 26 SCAs in total. Remaining performance obligations, or RPO, "
            "are approximately $150 billion. All SCAs have take-or-pay contracted volumes, "
            "and RPO is based on committed volumes and minimum pricing. "
            "The SCAs cover over 35% of revenue through 2030. Three-quarters of this estimated revenue "
            "has a defined pricing framework. Financial commitments from customers increased to $32 billion, "
            "the vast majority of which are cash deposits. "
            "In 2027 more than 75% of our output is already committed for 2027. "
            "We completed agreements for the vast majority of our calendar 2027 HBM bit supply. "
            "A majority of discussions with our customers today are already around 2028. "
            "SCAs extend into 2031."
        )
        obs = w.extract_micron_sca_visibility(self.event(text))
        self.assertIsNotNone(obs)
        self.assertEqual(obs["sca_count"], 26)
        self.assertEqual(obs["rpo_usd_bn"], 150.0)
        self.assertEqual(obs["financial_commitments_usd_bn"], 32.0)
        self.assertTrue(obs["financial_commitments_majority_cash_deposits"])
        self.assertTrue(obs["take_or_pay"])
        self.assertEqual(obs["output_committed_2027_min_pct"], 75.0)
        self.assertEqual(obs["output_committed_scope"], "total_output_sca_and_non_sca")
        self.assertEqual(obs["hbm_2027_bit_supply_stage"], "vast_majority_agreements_completed")
        self.assertEqual(obs["customer_discussion_focus_year"], 2028)
        self.assertEqual(obs["sca_max_year"], 2031)
        self.assertTrue(obs["rpo_and_financial_commitments_are_separate"])

    def test_micron_same_baseline_is_silent(self):
        old = dict(w.MICRON_SCA_BASELINE)
        self.assertEqual(w.micron_sca_visibility_changes(old, dict(old)), [])

    def test_micron_rpo_and_commitment_changes_alert_separately(self):
        old = dict(w.MICRON_SCA_BASELINE)
        new = dict(old, rpo_usd_bn=175.0, financial_commitments_usd_bn=40.0)
        reasons = w.micron_sca_visibility_changes(old, new)
        self.assertTrue(any("RPO" in x and "175" in x for x in reasons))
        self.assertTrue(any("고객 금융약정" in x and "40" in x for x in reasons))


if __name__ == "__main__":
    unittest.main()

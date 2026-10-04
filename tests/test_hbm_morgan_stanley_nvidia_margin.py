import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rubin_hbm_watch as w


class MorganStanleyNvidiaHBMMarginTests(unittest.TestCase):
    def event(self, text, source="MT Newswires"):
        return {
            "category": "morgan_stanley_nvidia_hbm_margin",
            "title": text,
            "description": "",
            "article_title": "",
            "article_description": "",
            "article_text": text,
            "source": source,
            "origin_source": source,
            "published_at_kst": "2026-10-04T10:00:00+09:00",
            "direct_link": "https://example.com/ms-nvidia-hbm-margin",
        }

    def test_exact_bundle_parses_and_despec_math_crosschecks(self):
        text = (
            "Morgan Stanley said NVIDIA Rubin HBM unit price increase tolerance is 91.7% "
            "while defending a gross margin floor of 72%. With de-spec to 192GB from the standard 288GB HBM, "
            "the HBM unit price tolerance expands to 187.5%."
        )
        obs = w.extract_morgan_stanley_nvidia_hbm_margin(self.event(text))
        self.assertAlmostEqual(obs["base_hbm_unit_price_tolerance_pct_reported"], 91.7)
        self.assertAlmostEqual(obs["despec_hbm_unit_price_tolerance_pct_reported"], 187.5)
        self.assertAlmostEqual(obs["gross_margin_floor_pct_reported"], 72.0)
        self.assertAlmostEqual(obs["full_spec_hbm_gb"], 288.0)
        self.assertAlmostEqual(obs["despec_hbm_gb"], 192.0)
        self.assertTrue(obs["despec_math_consistent"])
        self.assertAlmostEqual(obs["derived_despec_tolerance_pct"], 187.55, places=2)

    def test_187_5_is_not_accepted_if_capacity_math_breaks(self):
        text = (
            "Morgan Stanley said NVIDIA Rubin HBM unit price increase tolerance is 91.7% at a gross margin floor of 72%. "
            "With de-spec to 256GB from the standard 288GB HBM, the HBM price tolerance is 187.5%."
        )
        obs = w.extract_morgan_stanley_nvidia_hbm_margin(self.event(text))
        self.assertFalse(obs["despec_math_consistent"])

    def test_memory_line_is_never_promoted_to_hbm_only_cost(self):
        text = (
            "Morgan Stanley VR200 NVL72 rack is $7.8 million. Memory is $2.0 million and increased 435%."
        )
        obs = w.extract_morgan_stanley_nvidia_hbm_margin(self.event(text))
        self.assertEqual(obs["vr200_memory_line_scope"], "public_recaps_conflict_on_hbm_inclusion_not_hbm_only_confirmed")
        self.assertNotIn("hbm_cost_usd", obs)

    def test_public_verification_upgrade_is_material(self):
        old = dict(w.MORGAN_STANLEY_NVIDIA_HBM_MARGIN_BASELINE)
        new = dict(old, exact_tolerance_public_source_verified=True)
        reasons = w.morgan_stanley_nvidia_hbm_margin_changes(old, new)
        self.assertTrue(any("exact 수치" in x and "검증 완료" in x for x in reasons))

    def test_despec_formula_uses_quantity_ratio_not_percent_addition(self):
        derived = w._ms_nvidia_margin_math(91.7, 288, 192)
        self.assertAlmostEqual(derived, 187.55, places=2)
        self.assertNotAlmostEqual(derived, 91.7 + 33.3, places=1)

    def test_baseline_is_not_claimed_publicly_verified(self):
        self.assertFalse(w.MORGAN_STANLEY_NVIDIA_HBM_MARGIN_BASELINE["exact_tolerance_public_source_verified"])
        self.assertEqual(w.MORGAN_STANLEY_NVIDIA_HBM_MARGIN_BASELINE["vr200_memory_line_scope"],
                         "public_recaps_conflict_on_hbm_inclusion_not_hbm_only_confirmed")


if __name__ == "__main__":
    unittest.main()

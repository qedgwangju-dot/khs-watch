import copy
import pathlib
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()

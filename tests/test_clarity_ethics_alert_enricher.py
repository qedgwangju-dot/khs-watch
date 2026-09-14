import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_ethics_alert_enricher", ROOT / "scripts" / "clarity_ethics_alert_enricher.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityEthicsAlertEnricherTest(unittest.TestCase):
    def test_ethics_breakthrough_replaces_generic_policy_interpretation(self):
        text = MOD.GENERIC_EASY + "\n" + MOD.GENERIC_INVEST + "\n" + MOD.GENERIC_CORE
        enriched = MOD.enrich_text(text)
        self.assertIn("약 80%", enriched)
        self.assertIn("주 검찰총장", enriched)
        self.assertIn("9월 15일", enriched)
        self.assertIn("stablecoin rewards", enriched)
        self.assertNotIn("공개 촉구만으로", enriched)


if __name__ == "__main__":
    unittest.main()

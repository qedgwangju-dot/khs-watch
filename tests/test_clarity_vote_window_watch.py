import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("clarity_vote_window_watch", ROOT / "scripts" / "clarity_vote_window_watch.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityVoteWindowWatchTest(unittest.TestCase):
    def test_official_vote_time_converts_to_kst_0315(self):
        self.assertEqual(MOD.SCHEDULE_KST.strftime("%Y-%m-%d %H:%M"), "2026-09-16 03:15")
        self.assertEqual(MOD.VOTES_REQUIRED, 60)

    def test_official_schedule_text_tolerates_senate_superscript_spacing(self):
        sample = "The cloture motion with respect to Cal. #423, H.R.3633 - Digital Asset Market Clarity Act will ripen on Tuesday, September 15 th at 2:15pm."
        self.assertTrue(MOD.schedule_text_matches(sample))

    def test_lummis_risk_is_not_treated_as_actual_vote_count(self):
        text = "Lummis says some Democrats will never agree and keep the bill hostage after 126 changes"
        self.assertTrue(MOD.LUMMIS_RE.search(text))
        self.assertTrue(MOD.LUMMIS_RISK_RE.search(text))

    def test_bessent_circuit_breaker_signal_is_detected(self):
        text = "Bessent says community banks will be fully protected if stablecoin deposit outflows worsen under a circuit breaker"
        self.assertTrue(MOD.BESSENT_RE.search(text))
        self.assertTrue(MOD.BESSENT_BANK_RE.search(text))

    def test_market_pct_change(self):
        self.assertAlmostEqual(MOD.pct_change(100, 109), 9.0, places=6)

    def test_market_reaction_keeps_price_change_and_volume_when_available(self):
        before = {"COIN": {"price": 100, "regular_market_volume": 10}}
        after = {"COIN": {"price": 105, "regular_market_volume": 20}}
        row = MOD.market_reaction(before, after)["COIN"]
        self.assertAlmostEqual(row["change_pct"], 5.0, places=6)
        self.assertEqual(row["volume_before"], 10)
        self.assertEqual(row["volume_after"], 20)


if __name__ == "__main__":
    unittest.main()

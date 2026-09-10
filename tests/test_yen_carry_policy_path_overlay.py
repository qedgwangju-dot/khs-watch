from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_policy_path_overlay as overlay  # noqa: E402


def state(*, jgb2=1.80, ust2=4.20, spread=2.40, vol=0.90, net_short=50000, net_short_pct=12.5,
          ch15=0.0, ch30=0.0, ch60=0.0, jgb_date="2026-09-09", ust_date="2026-09-09", cftc_date="2026-09-01"):
    return {
        "initialized": True,
        "source_dates": {"jgb2": jgb_date, "ust2": ust_date, "cftc": cftc_date},
        "values": {
            "jgb2": jgb2,
            "ust2": ust2,
            "us_jp_2y_spread": spread,
            "fx_vol_ratio": vol,
            "cftc_net_short": net_short,
            "cftc_net_short_pct_oi": net_short_pct,
            "usdjpy_15m_pct": ch15,
            "usdjpy_30m_pct": ch30,
            "usdjpy_60m_pct": ch60,
        },
    }


class YenCarryPolicyPathOverlayTests(unittest.TestCase):
    def test_gradual_tightening_can_be_absorbed_when_spread_wide_and_vol_calm(self):
        previous = state()
        pending = state()
        result = overlay.classify_context(previous, pending)
        self.assertTrue(result["gradual_absorption"])
        self.assertEqual(result["regime"], "평온하지만 레버리지 취약성 누적")
        self.assertEqual(result["risk_floor"], 1)

    def test_quiet_short_rebuild_is_vulnerability_not_active_unwind(self):
        previous = state(net_short=40000, net_short_pct=9.0, cftc_date="2026-09-01")
        pending = state(net_short=65000, net_short_pct=16.0, cftc_date="2026-09-08", vol=0.85)
        result = overlay.classify_context(previous, pending)
        self.assertTrue(result["quiet_releveraging_event"])
        self.assertTrue(result["quiet_crowded_vulnerability"])
        self.assertFalse(result["yen_shock"])
        self.assertEqual(result["risk_floor"], 1)

    def test_hawkish_repricing_plus_yen_shock_sets_orange_floor(self):
        previous = state(jgb2=1.75, spread=2.45, jgb_date="2026-09-09")
        pending = state(jgb2=1.87, spread=2.33, jgb_date="2026-09-10", ch15=-0.60, ch30=-0.82)
        result = overlay.classify_context(previous, pending)
        self.assertTrue(result["hawkish_repricing_proxy"])
        self.assertTrue(result["policy_shock_with_yen"])
        self.assertEqual(result["risk_floor"], 2)

    def test_hawkish_repricing_without_yen_shock_is_only_yellow(self):
        previous = state(jgb2=1.75, spread=2.45, jgb_date="2026-09-09")
        pending = state(jgb2=1.86, spread=2.34, jgb_date="2026-09-10")
        result = overlay.classify_context(previous, pending)
        self.assertTrue(result["hawkish_repricing_proxy"])
        self.assertFalse(result["policy_shock_with_yen"])
        self.assertEqual(result["risk_floor"], 1)

    def test_missing_vol_does_not_invent_quiet_releveraging(self):
        previous = state(net_short=40000, cftc_date="2026-09-01")
        pending = state(net_short=70000, net_short_pct=18.0, cftc_date="2026-09-08")
        pending["values"]["fx_vol_ratio"] = None
        result = overlay.classify_context(previous, pending)
        self.assertFalse(result["quiet_crowded_vulnerability"])
        self.assertFalse(result["quiet_releveraging_event"])


if __name__ == "__main__":
    unittest.main()

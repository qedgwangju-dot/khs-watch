import unittest

from japan_treasury_regime_overlay import FlowRegime, LiveMarket, parse_flow_regime, signal_levels


class JapanTreasuryRegimeOverlayTests(unittest.TestCase):
    def test_parse_flow_regime_uses_long_term_debt_only(self):
        rows = []
        for i in range(1, 13):
            # row[6] is long-term debt in 100 million yen; -1000 => -0.1 trillion yen
            value = -1000 if i >= 10 else 500
            row = [f"2026/08/{i:02d}-2026/08/{i+1:02d}", "0", "0", "0", "0", "0", str(value), "999999", "0", "0", "0", "0"]
            rows.append(",".join(row))
        flow = parse_flow_regime("\n".join(rows))
        self.assertAlmostEqual(flow.one_week, -0.1)
        self.assertEqual(flow.negative_streak, 3)
        self.assertAlmostEqual(flow.four_week, -0.25)

    def test_official_funding_becomes_critical_without_visible_fima(self):
        levels = signal_levels(
            sec_drop_bn=-87.773,
            intervention_trn=15.3993,
            funding_ratio=0.89,
            fima_bn=0.0,
            flow=None,
            market=None,
            today=__import__("datetime").date(2026, 9, 8),
        )
        self.assertEqual(levels["official_funding"], 3)

    def test_structural_repatriation_uses_4w_or_12w(self):
        flow = FlowRegime("2026-09-04", -0.8, -1.5, -2.2, -5.4, 3)
        levels = signal_levels(
            sec_drop_bn=None,
            intervention_trn=None,
            funding_ratio=None,
            fima_bn=None,
            flow=flow,
            market=None,
            today=__import__("datetime").date(2026, 9, 8),
        )
        self.assertEqual(levels["structural_repatriation"], 2)

    def test_japan_long_end_fingerprint_requires_yen_and_quiet_front_end(self):
        market = LiveMarket(
            observed_at_utc="2026-09-08T14:00:00Z",
            usdjpy=153.5,
            usdjpy_change_pct=-1.1,
            ust2=4.37,
            ust2_change_bp=2.0,
            ust10=4.84,
            ust10_change_bp=8.0,
            ust30=5.30,
            ust30_change_bp=9.0,
        )
        levels = signal_levels(
            sec_drop_bn=None,
            intervention_trn=None,
            funding_ratio=None,
            fima_bn=None,
            flow=None,
            market=market,
            today=__import__("datetime").date(2026, 9, 8),
        )
        self.assertEqual(levels["japan_long_end_fingerprint"], 3)
        self.assertEqual(levels["event_long_end_breakout"], 3)

    def test_front_end_jump_marks_fed_repricing_not_japan_fingerprint(self):
        market = LiveMarket(
            observed_at_utc="2026-09-08T14:00:00Z",
            usdjpy=154.8,
            usdjpy_change_pct=-0.2,
            ust2=4.47,
            ust2_change_bp=10.0,
            ust10=4.86,
            ust10_change_bp=9.0,
            ust30=5.31,
            ust30_change_bp=8.0,
        )
        levels = signal_levels(
            sec_drop_bn=None,
            intervention_trn=None,
            funding_ratio=None,
            fima_bn=None,
            flow=None,
            market=market,
            today=__import__("datetime").date(2026, 9, 8),
        )
        self.assertEqual(levels["japan_long_end_fingerprint"], 0)
        self.assertEqual(levels["fed_repricing_dominant"], 1)


if __name__ == "__main__":
    unittest.main()

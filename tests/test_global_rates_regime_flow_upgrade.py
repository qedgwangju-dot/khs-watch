import unittest
from unittest.mock import patch

import global_rates_regime_flow_upgrade as m


class RegimeFlowUpgradeTest(unittest.TestCase):
    def test_global_sync_not_fiscal_when_us_and_japan_rise_together(self):
        prev_j = {"date": "2026/9/1", "jgb2": 1.80, "jgb5": 2.25, "jgb10": 2.95, "jgb30": 3.55}
        cur_j = {"date": "2026/9/2", "jgb2": 1.82, "jgb5": 2.27, "jgb10": 3.01, "jgb30": 3.60}
        prev_u = {"date": "2026-09-01", "ust10": 4.72}
        cur_u = {"date": "2026-09-02", "ust10": 4.79}
        fx = {"live_fx_price": 159.0, "live_fx_change_pct": 0.05}
        out = m.classify_regime(prev_j, cur_j, prev_u, cur_u, fx)
        self.assertEqual(out["label"], "글로벌 금리 동조형")

    def test_fiscal_risk_requires_long_end_and_weak_yen(self):
        prev_j = {"date": "2026/9/1", "jgb2": 1.80, "jgb5": 2.20, "jgb10": 3.00, "jgb30": 3.50}
        cur_j = {"date": "2026/9/2", "jgb2": 1.81, "jgb5": 2.22, "jgb10": 3.03, "jgb30": 3.62}
        prev_u = {"date": "2026-09-01", "ust10": 4.75}
        cur_u = {"date": "2026-09-02", "ust10": 4.77}
        fx = {"live_fx_price": 160.2, "live_fx_change_pct": 0.60}
        out = m.classify_regime(prev_j, cur_j, prev_u, cur_u, fx)
        self.assertEqual(out["label"], "재정 위험 프리미엄형")

    def test_policy_normalisation_requires_front_end_and_yen_strength(self):
        prev_j = {"date": "2026/9/1", "jgb2": 1.75, "jgb5": 2.15, "jgb10": 2.98, "jgb30": 3.55}
        cur_j = {"date": "2026/9/2", "jgb2": 1.82, "jgb5": 2.22, "jgb10": 3.00, "jgb30": 3.57}
        prev_u = {"date": "2026-09-01", "ust10": 4.75}
        cur_u = {"date": "2026-09-02", "ust10": 4.76}
        fx = {"live_fx_price": 158.5, "live_fx_change_pct": -0.70}
        out = m.classify_regime(prev_j, cur_j, prev_u, cur_u, fx)
        self.assertEqual(out["label"], "BOJ 정상화형")

    def test_three_percent_with_good_auction_is_counter_signal(self):
        regime = {"jgb10": 3.01}
        structural = {"auction": {"tenor": "10-Year", "auction_date": "9/1/2026", "bid_to_cover": 3.286, "tail_bp": 1.6, "grade": "중립"}}
        out = m.absorption_signal(regime, structural)
        self.assertEqual(out["label"], "3%대에서도 입찰 흡수력 양호")
        self.assertTrue(out["key"].startswith("good:"))

    def test_weekly_flow_sign_convention_and_krw(self):
        rows = [
            {"period": "w1", "equity_net_100m_yen": 1000, "long_term_net_100m_yen": 3000, "equity_long_subtotal_100m_yen": 4000},
            {"period": "w2", "equity_net_100m_yen": 2000, "long_term_net_100m_yen": 5000, "equity_long_subtotal_100m_yen": 7000},
            {"period": "w3", "equity_net_100m_yen": 3000, "long_term_net_100m_yen": 5000, "equity_long_subtotal_100m_yen": 8000},
            {"period": "w4", "equity_net_100m_yen": -1000, "long_term_net_100m_yen": -3000, "equity_long_subtotal_100m_yen": -4000},
        ]
        out = m.flow_signal(rows, 8.5)
        self.assertIn("순매도", out["label"])
        self.assertTrue(out["material"])
        self.assertIn("-0.40조엔", out["subtotal_display"])
        self.assertIn("-3.4조원", out["subtotal_display"])

    def test_week_csv_parser_uses_outward_assets_table_only(self):
        sample = """1. Portfolio Investment Assets,,,,,,,,,,\nPeriod,eq acq,eq disp,eq net,lt acq,lt disp,lt net,subtotal,st acq,st disp,st net,total\nAugust 16 - August 22 2026,10,5,5,20,10,10,15,2,1,1,16\nAugust 23 - August 29 2026,10,15,-5,20,25,-5,-10,2,1,1,-9\n2. Portfolio Investment Liabilities,,,,,,,,,,\nAugust 23 - August 29 2026,100,0,100,100,0,100,200,0,0,0,200\n""".encode()
        with patch.object(m, "get_bytes", return_value=sample):
            rows = m.fetch_weekly_outward_flows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["equity_long_subtotal_100m_yen"], -10)


if __name__ == "__main__":
    unittest.main()

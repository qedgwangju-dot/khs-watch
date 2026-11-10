"""Regression checks for the three new signals in the existing HBM Telegram route."""
import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hbm_memory_axes as w


class HBMCycleSignalsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 15, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        self.item = {
            "direct_link": "https://www.trendforce.com/presscenter/news/test",
            "title": "DRAM memory outlook",
            "source": "TrendForce",
            "published_at_kst": "2026-11-10T09:00:00+09:00",
        }

    def records(self, body):
        return w.parse_hbm_cycle_signals(self.item, body)

    def test_server_contract_price_actual_vs_forecast(self):
        actual = self.records("TrendForce reported 2027 Q1 server DRAM contract prices rose 12% QoQ.")
        forecast = self.records("TrendForce forecasts that 2027 Q1 server DRAM contract prices will rise 12% QoQ.")
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]["value"]["qoq_change_pct"], 12)
        self.assertEqual(actual[0]["value"]["stage"], "reported_change")
        self.assertEqual(len(forecast), 1)
        self.assertEqual(forecast[0]["value"]["stage"], "forecast")
        self.assertNotEqual(actual[0]["key"], forecast[0]["key"])

    def test_no_unqualified_spot_or_mixed_numeric_claim(self):
        self.assertEqual(self.records("TrendForce says server DRAM spot price rose 12% QoQ."), [])
        self.assertEqual(self.records("TrendForce reports server DRAM contract prices rose 12% QoQ but inventory fell 5%."), [])

    def test_hbm_renegotiation_is_not_firm_contract(self):
        negotiating = self.records("SK hynix is renegotiating HBM4 supply contracts for 2027 with customers.")
        signed = self.records("SK hynix completed HBM4 contract renewal with customers for 2027.")
        self.assertEqual(negotiating[0]["value"]["stage"], "negotiation")
        self.assertEqual(signed[0]["value"]["stage"], "signed")
        self.assertEqual(negotiating[0]["key"], signed[0]["key"])
        self.assertTrue(w.comparison(negotiating[0], signed[0]))

    def test_fab_plan_is_not_physical_operation(self):
        planned = self.records("SK hynix plans to raise M15X DRAM utilization to 90% by 2027.")
        actual = self.records("SK hynix M15X DRAM equipment installation completed and utilization reached 87% in 2026.")
        self.assertEqual(planned[0]["value"]["stage"], "planned")
        self.assertEqual(actual[0]["value"]["stage"], "in_operation")
        self.assertEqual(actual[0]["value"]["utilization_pct"], 87)
        self.assertTrue(w.comparison(planned[0], actual[0]))

    def test_new_forecast_baseline_does_not_alert(self):
        baseline = self.records("TrendForce forecasts 2027 Q1 server DRAM contract prices to rise 12% QoQ.")
        state = w.update_state({}, baseline, self.now)
        self.assertEqual(state["pending"], {})
        self.assertIn(baseline[0]["key"], state["last_notified"])
        state2 = w.update_state(state, baseline, self.now)
        self.assertEqual(state2["pending"], {})


if __name__ == "__main__":
    unittest.main()

import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as w


class SamsungHBMBrokerForecastTests(unittest.TestCase):
    def sample_event(self, text):
        return {
            "id": "evt1",
            "title": "J.P. Morgan Samsung Electronics 3Q preview HBM ASP",
            "description": text,
            "source": "J.P. Morgan",
            "published_at_kst": "2026-09-18T09:00:00+09:00",
            "direct_link": "https://example.com/jpm",
        }

    def test_jpmorgan_report_extracts_asp_period_and_stack_mix(self):
        text = (
            "Samsung Electronics HBM ASP negotiation is in the final stage. "
            "We see upside risk to our previous estimate (+48% y/y) and now forecast "
            "a 64% blended ASP increase in FY27E, driving HBM OPM expansion. "
            "We see 12Hi sales mix continuing to be mainstream for the company. "
            "Near-term FX headwinds remain."
        )
        e = self.sample_event(text)
        with patch.object(w, "_broker_page_text", return_value=text):
            rows = w.extract_broker_hbm_forecasts(e)
        self.assertEqual(len(rows), 1)
        obs = rows[0]
        self.assertEqual(obs["key"], "jpmorgan|samsung|2027")
        self.assertEqual(obs["asp_yoy_pct"], 64.0)
        self.assertEqual(obs["previous_asp_yoy_pct"], 48.0)
        self.assertEqual(obs["stack_mainstream"], "12hi")
        self.assertEqual(obs["contract_stage"], "final_stage")
        self.assertTrue(obs["fx_headwind"])

    def test_current_baseline_does_not_realert_same_jpmorgan_report(self):
        old = dict(w.BROKER_FORECAST_BASELINES["jpmorgan|samsung|2027"])
        obs = {
            "asp_yoy_pct": 64.0,
            "stack_mainstream": "12hi",
        }
        material, reasons = w._broker_material_change(old, obs)
        self.assertFalse(material)
        self.assertEqual(reasons, [])

    def test_contract_final_to_signed_alerts_without_asp_change(self):
        old = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi", "contract_stage": "final_stage"}
        obs = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi", "contract_stage": "signed"}
        material, reasons = w._broker_material_change(old, obs)
        self.assertTrue(material)
        self.assertTrue(any("협상 마무리 단계→계약·가격 확정" in x for x in reasons))

    def test_contract_regression_does_not_realert(self):
        old = {"contract_stage": "signed"}
        obs = {"contract_stage": "negotiation"}
        material, reasons = w._broker_material_change(old, obs)
        self.assertFalse(material)
        self.assertEqual(reasons, [])

    def test_asp_revision_five_points_or_more_alerts(self):
        old = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi"}
        obs = {"asp_yoy_pct": 70.0, "stack_mainstream": "12hi"}
        material, reasons = w._broker_material_change(old, obs)
        self.assertTrue(material)
        self.assertTrue(any("+6.0%p" in x for x in reasons))

    def test_small_asp_revision_stays_silent(self):
        old = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi"}
        obs = {"asp_yoy_pct": 67.0, "stack_mainstream": "12hi"}
        material, reasons = w._broker_material_change(old, obs)
        self.assertFalse(material)
        self.assertEqual(reasons, [])

    def test_stack_mainstream_change_alerts_even_without_big_asp_revision(self):
        old = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi"}
        obs = {"asp_yoy_pct": 66.0, "stack_mainstream": "8hi"}
        material, reasons = w._broker_material_change(old, obs)
        self.assertTrue(material)
        self.assertTrue(any("12단→8단" in x for x in reasons))

    def test_eps_revision_alone_does_not_trigger_hbm_alert(self):
        old = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi", "eps_revision_pct": {"2027": -4.6}}
        obs = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi", "eps_revision_pct": {"2027": -8.0}}
        material, reasons = w._broker_material_change(old, obs)
        self.assertFalse(material)
        self.assertEqual(reasons, [])

    def test_partial_stack_update_preserves_known_asp(self):
        old = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi", "source": "old"}
        obs = {"stack_mainstream": "8hi", "source": "new", "published_at_kst": "2026-10-01T09:00:00+09:00"}
        candidate = w._broker_state_candidate(old, obs)
        self.assertEqual(candidate["asp_yoy_pct"], 64.0)
        self.assertEqual(candidate["stack_mainstream"], "8hi")
        self.assertEqual(candidate["source"], "new")

    def test_summary_separates_hbm_business_from_eps_and_fx(self):
        obs = {
            "key": "jpmorgan|samsung|2027",
            "institution": "jpmorgan",
            "company": "samsung",
            "period": "2027",
            "asp_yoy_pct": 70.0,
            "previous_asp_yoy_pct": 64.0,
            "stack_mainstream": "12hi",
            "eps_revision_pct": {"2027": -4.6},
            "fx_headwind": True,
            "source": "J.P. Morgan",
            "published_at_kst": "2026-10-01T09:00:00+09:00",
            "direct_link": "https://example.com/jpm2",
            "title": "Samsung HBM outlook",
        }
        old = {"asp_yoy_pct": 64.0, "stack_mainstream": "12hi"}
        e = w.broker_forecast_change_event(obs, old, ["HBM 혼합 평균판매단가 전망 +64.0%→+70.0% YoY (+6.0%p)"])
        out = "\n".join(w.broker_forecast_event_summary(e))
        self.assertIn("HBM 본업", out)
        self.assertIn("전체 EPS 수정", out)
        self.assertIn("환율 분리", out)
        self.assertIn("2027E -4.6%", out)
        self.assertIn("기존 가격 레벨 대비", out)


if __name__ == "__main__":
    unittest.main()

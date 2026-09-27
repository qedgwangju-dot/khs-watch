import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import us_ai_grid_bottleneck_watch as w


class GridMetricParseTests(unittest.TestCase):
    def test_lbnl_2030_demand(self):
        text = "U.S. data center electricity use in 2030 is 649 TWh, representing 11.8% of total U.S. electricity."
        m = w.parse_metrics(text)
        self.assertEqual(m["dc_electricity_2030_twh"], 649.0)
        self.assertEqual(m["dc_share_2030_pct"], 11.8)

    def test_nerc_transformer_leads(self):
        text = "Lead times for transformers remain virtually unchanged, averaging 120 weeks in 2024. Large transformer lead times averaged 80–210 weeks."
        m = w.parse_metrics(text)
        self.assertEqual(m["transformer_avg_lead_weeks"], 120.0)
        self.assertEqual(m["large_transformer_low_weeks"], 80.0)
        self.assertEqual(m["large_transformer_high_weeks"], 210.0)

    def test_queue_parse(self):
        text = "At the end of 2025, approximately 8,200 active projects representing 2,060 GW were in interconnection queues."
        m = w.parse_metrics(text)
        self.assertEqual(m["queue_projects"], 8200.0)
        self.assertEqual(m["queue_gw"], 2060.0)


class GridMaterialityTests(unittest.TestCase):
    def test_transformer_ten_weeks_triggers(self):
        old = dict(w.BASELINE["metrics"])
        new = dict(old)
        new["transformer_avg_lead_weeks"] = 131.0
        ch = w.material_metric_changes(old, new)
        self.assertTrue(any(x["key"] == "transformer_avg_lead_weeks" for x in ch))

    def test_queue_subthreshold_is_quiet(self):
        old = dict(w.BASELINE["metrics"])
        new = dict(old)
        new["queue_gw"] = 2200.0
        ch = w.material_metric_changes(old, new)
        self.assertFalse(any(x["key"] == "queue_gw" for x in ch))

    def test_dc_ten_percent_triggers(self):
        old = dict(w.BASELINE["metrics"])
        new = dict(old)
        new["dc_electricity_2030_twh"] = 720.0
        ch = w.material_metric_changes(old, new)
        self.assertTrue(any(x["key"] == "dc_electricity_2030_twh" for x in ch))


class GridEventTests(unittest.TestCase):
    def test_transformer_factory_event(self):
        text = "Hitachi Energy breaks ground on a new transformer factory expansion in the United States."
        event = w.structural_event(text, "https://www.hitachienergy.com/example")
        self.assertIn("변압기", event)

    def test_untrusted_event_does_not_trigger(self):
        text = "New transformer factory expansion announced."
        self.assertEqual(w.structural_event(text, "https://example.com/foo"), "")


class GridAlertTests(unittest.TestCase):
    def test_alert_has_required_sections(self):
        changes = [{
            "key": "transformer_avg_lead_weeks",
            "label": "변압기 평균 납기",
            "mode": "abs",
            "before": 120.0,
            "after": 135.0,
            "delta": 15.0,
        }]
        alert = w.build_alert(changes, [], w.BASELINE)
        self.assertIn("미국 AI 전력망 병목 감시", alert)
        self.assertIn("1단계 현재 숫자 추적", alert)
        self.assertIn("2단계 미래 재평가 요인 발굴", alert)
        self.assertIn("관련 기업 지도", alert)
        self.assertIn("공정 병목 후보", alert)
        self.assertIn("숨은 역풍·실패모드", alert)
        self.assertIn("핵심 한 줄 요약", alert)
        self.assertIn("8,200개", alert)
        self.assertIn("2,060GW", alert)


if __name__ == "__main__":
    unittest.main()

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


    def test_cushman_2026_equipment_ranges_parse(self):
        text = (
            "Pad-mounted transformers 68 to 113 weeks. "
            "Generators 60 to 100 weeks. "
            "Medium-voltage switchgear 38 to 63 weeks. "
            "Low-voltage switchgear 36 to 60 weeks. "
            "UPS systems 36 to 42 weeks."
        )
        m = w.parse_metrics(text)
        self.assertEqual((m["cw_padmount_transformer_low_weeks"], m["cw_padmount_transformer_high_weeks"]), (68.0, 113.0))
        self.assertEqual((m["cw_generator_low_weeks"], m["cw_generator_high_weeks"]), (60.0, 100.0))
        self.assertEqual((m["cw_mv_switchgear_low_weeks"], m["cw_mv_switchgear_high_weeks"]), (38.0, 63.0))
        self.assertEqual((m["cw_lv_switchgear_low_weeks"], m["cw_lv_switchgear_high_weeks"]), (36.0, 60.0))
        self.assertEqual((m["cw_ups_low_weeks"], m["cw_ups_high_weeks"]), (36.0, 42.0))


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


    def test_switchgear_six_week_change_triggers(self):
        old = dict(w.BASELINE["metrics"])
        new = dict(old)
        new["cw_mv_switchgear_high_weeks"] = 70.0
        ch = w.material_metric_changes(old, new)
        self.assertTrue(any(x["key"] == "cw_mv_switchgear_high_weeks" for x in ch))


class GridEventTests(unittest.TestCase):
    def test_transformer_factory_event(self):
        text = "Hitachi Energy breaks ground on a new transformer factory expansion in the United States."
        event = w.structural_event(text, "https://www.hitachienergy.com/example")
        self.assertIn("변압기", event)

    def test_untrusted_event_does_not_trigger(self):
        text = "New transformer factory expansion announced."
        self.assertEqual(w.structural_event(text, "https://example.com/foo"), "")


    def test_switchgear_factory_production_event(self):
        text = "Eaton opens new factory and production begins for medium-voltage switchgear serving data centers."
        event = w.structural_event(text, "https://www.eaton.com/us/en-us/example")
        self.assertIn("전력기기", event)

    def test_supply_capacity_agreement_event(self):
        text = "Schneider Electric signs a supply capacity agreement for data center UPS and switchgear."
        event = w.structural_event(text, "https://www.se.com/us/en/example")
        self.assertIn("공급능력 계약", event)


class GridAlertTests(unittest.TestCase):
    def test_alert_is_compact_and_keeps_equipment_bottlenecks(self):
        changes = [{
            "key": "cw_mv_switchgear_high_weeks",
            "label": "데이터센터 중압배전반 최장 납기",
            "mode": "abs",
            "before": 63.0,
            "after": 70.0,
            "delta": 7.0,
        }]
        alert = w.build_alert(changes, [], w.BASELINE)
        self.assertIn("AI 데이터센터 전력기기·전원 병목 변화", alert)
        self.assertIn("<b>변화</b>", alert)
        self.assertIn("<b>현재 병목</b>", alert)
        self.assertIn("지상형 변압기 68~113주", alert)
        self.assertIn("발전기 60~100주", alert)
        self.assertIn("중압배전반 38~63주", alert)
        self.assertIn("저압배전반 36~60주", alert)
        self.assertIn("UPS 36~42주", alert)
        self.assertIn("계통대기 8,200개·2,060GW", alert)
        self.assertIn("Schneider Electric·Eaton·ABB·Vertiv", alert)
        self.assertIn("Caterpillar·Cummins·Rolls-Royce mtu", alert)
        self.assertNotIn("1단계 현재 숫자 추적", alert)
        self.assertNotIn("공정 병목 후보", alert)
        self.assertNotIn("숨은 역풍·실패모드", alert)
        self.assertNotIn("알림 기준", alert)
        self.assertLess(len(alert), 2100)


if __name__ == "__main__":
    unittest.main()

import io
import pathlib
import sys
import unittest
import zipfile

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


class TransformerImportWatchTests(unittest.TestCase):
    @staticmethod
    def _line(commodity, cty_code, port_code, year, month, value):
        chars = [" "] * 230
        def put(start, end, text):
            text = str(text)
            width = end - start
            chars[start:end] = list(text.rjust(width))
        chars[0:6] = list(commodity)
        chars[6:10] = list(cty_code)
        chars[10:14] = list(port_code)
        chars[14:18] = list(f"{year:04d}")
        chars[18:20] = list(f"{month:02d}")
        put(20, 35, value)
        return "".join(chars)

    def test_census_port_hs6_zip_aggregates_country_across_ports(self):
        rows = [
            self._line("850423", "5700", "2704", 2026, 8, 10_000_000),
            self._line("850423", "5700", "3001", 2026, 8, 5_000_000),
            self._line("850423", "5800", "2704", 2026, 8, 30_000_000),
            self._line("850423", "2010", "2304", 2026, 8, 55_000_000),
            self._line("850422", "5700", "2704", 2026, 8, 20_000_000),
            self._line("850422", "5800", "2704", 2026, 8, 10_000_000),
            self._line("850421", "2010", "2304", 2026, 8, 70_000_000),
            self._line("850434", "5700", "2704", 2026, 8, 7_000_000),
        ]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("PORTHS6MM2608.TXT", "\n".join(rows) + "\n")
        parsed = w.parse_census_port_hs6_zip(buf.getvalue(), 2026, 8)
        large = w.summarize_trade_scope(parsed, w.TRANSFORMER_PRIMARY_HS6)
        liquid = w.summarize_trade_scope(parsed, w.TRANSFORMER_LIQUID_HS6)
        self.assertEqual(large["china_usd"], 15_000_000)
        self.assertEqual(large["korea_usd"], 30_000_000)
        self.assertAlmostEqual(large["china_share_pct"], 15.0)
        self.assertAlmostEqual(large["korea_share_pct"], 30.0)
        self.assertEqual(liquid["world_usd"], 200_000_000)
        self.assertEqual(liquid["china_usd"], 35_000_000)
        self.assertEqual(liquid["korea_usd"], 40_000_000)

    def test_substitution_signal_requires_china_down_and_korea_up(self):
        prev = {"china_share_pct": 8.0, "korea_share_pct": 18.0}
        cur = {"china_share_pct": 6.5, "korea_share_pct": 19.5}
        self.assertTrue(w.trade_substitution_signal(cur, prev))
        self.assertFalse(w.trade_substitution_signal({"china_share_pct": 6.5, "korea_share_pct": 18.4}, prev))

    def test_august_2026_never_claims_policy_causality(self):
        history = {"2026-08": {"liquid_850421_23": {"china_share_pct": 4.0, "korea_share_pct": 20.0}}}
        status = w.transformer_policy_effect_status("2026-08", history)
        self.assertIn("판단 보류", status)
        self.assertIn("8월 26일", status)

    def test_two_consecutive_post_order_substitution_is_association_not_causation(self):
        history = {
            "2026-08": {"liquid_850421_23": {"china_share_pct": 5.0, "korea_share_pct": 18.0}},
            "2026-09": {"liquid_850421_23": {"china_share_pct": 3.5, "korea_share_pct": 19.5}},
            "2026-10": {"liquid_850421_23": {"china_share_pct": 2.0, "korea_share_pct": 21.0}},
        }
        status = w.transformer_policy_effect_status("2026-10", history)
        self.assertIn("2개월 연속", status)
        self.assertIn("인과관계는 미확정", status)

    def test_trade_alert_has_hts_scope_and_policy_guard(self):
        trade_state = {
            **w.TRANSFORMER_IMPORT_BASELINE,
            "latest_month": "2026-08",
            "history": {
                "2026-07": {
                    "liquid_850421_23": {"china_share_pct": 5.0, "korea_share_pct": 18.0},
                },
                "2025-08": {
                    "liquid_850421_23": {"china_share_pct": 4.0, "korea_share_pct": 17.0},
                },
                "2026-08": {
                    "source_url": "https://www.census.gov/example.zip",
                    "primary_850423": {
                        "china_share_pct": 2.0, "korea_share_pct": 25.0,
                        "china_usd": 2_000_000, "korea_usd": 25_000_000,
                    },
                    "liquid_850421_23": {
                        "china_share_pct": 3.0, "korea_share_pct": 20.0,
                        "china_usd": 6_000_000, "korea_usd": 40_000_000,
                        "top_origins": [
                            {"name": "멕시코", "share_pct": 30.0},
                            {"name": "한국", "share_pct": 20.0},
                        ],
                    },
                },
            },
        }
        alert = w.build_transformer_import_alert(
            {"type": "bootstrap", "month": "2026-08"},
            trade_state,
        )
        self.assertIn("HS 850423", alert)
        self.assertIn("HS 850421~850423", alert)
        self.assertIn("EO 14421", alert)
        self.assertIn("일괄 금지가 아닙니다", alert)
        self.assertIn("효성중공업·HD현대일렉트릭·LS ELECTRIC", alert)


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

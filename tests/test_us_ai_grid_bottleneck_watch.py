import io
import pathlib
import sys
import unittest
import zipfile
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

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

    def test_bps_policy_change_is_structural_event(self):
        text = (
            "Bulk-Power System rule for a Covered Foreign Entity may prohibit "
            "foreign electric equipment transactions."
        )
        event = w.structural_event(text, "https://www.whitehouse.gov/example")
        self.assertIn("BPS", event)

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
        self.assertEqual(w.COUNTRY_NAMES["5490"], "태국")
        self.assertEqual(w.COUNTRY_NAMES["4791"], "크로아티아")

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

    def test_trade_alert_does_not_overclaim_large_transformer_substitution(self):
        trade_state = {
            **w.TRANSFORMER_IMPORT_BASELINE,
            "latest_month": "2026-08",
            "history": {
                "2026-07": {
                    "primary_850423": {"china_share_pct": 10.2, "korea_share_pct": 17.0},
                    "liquid_850421_23": {"china_share_pct": 8.1, "korea_share_pct": 16.6},
                },
                "2025-08": {
                    "liquid_850421_23": {"china_share_pct": 7.2, "korea_share_pct": 21.5},
                },
                "2026-08": {
                    "source_url": "https://www.census.gov/example.zip",
                    "primary_850423": {
                        "china_share_pct": 4.3, "korea_share_pct": 14.3,
                        "china_usd": 16_000_000, "korea_usd": 53_000_000,
                    },
                    "liquid_850421_23": {
                        "china_share_pct": 5.5, "korea_share_pct": 18.3,
                        "china_usd": 35_000_000, "korea_usd": 116_000_000,
                        "top_origins": [],
                    },
                },
            },
        }
        alert = w.build_transformer_import_alert({"type": "bootstrap", "month": "2026-08"}, trade_state)
        self.assertIn("HS 850423 전월 대비", alert)
        self.assertIn("HS 850421~850423 전월 대비", alert)
        self.assertIn("10,000kVA 초과 HS 850423에서는 같은 대체 패턴이 확인되지 않아", alert)
        self.assertIn("확대해석하지 않습니다", alert)



class KoreanTransformerExportTests(unittest.TestCase):
    def _response(self, hs, period="2026.09", us_dlr=100, kg=5, children=False, response_code="00"):
        if children:
            item = (f"<item><hsCd>{hs}0000</hsCd><year>{period}</year><statCd>US</statCd>"
                    f"<expDlr>{us_dlr}</expDlr><expWgt>{kg}</expWgt></item>")
        else:
            item = (f"<item><hsCd>{hs}</hsCd><year>{period}</year><statCd>US</statCd>"
                    f"<expDlr>{us_dlr}</expDlr><expWgt>{kg}</expWgt></item>")
        return (f"<response><header><resultCode>{response_code}</resultCode></header>"
                f"<body><items>{item}</items></body></response>").encode()

    def test_official_hs6_only_exact_period_country_and_unit(self):
        result = w.parse_korea_kcs_hs6_response(
            self._response("850423", us_dlr=123450, kg=1025), "850423", "202609")
        self.assertEqual(result["export_usd"], 123450)
        self.assertEqual(result["net_weight_kg"], 1025)
        self.assertEqual(result["month"], "2026-09")
        with self.assertRaises(LookupError):
            w.parse_korea_kcs_hs6_response(self._response("850423", period="2026.08"), "850423", "202609")

    def test_kcs_rejects_auth_error_instead_of_treating_zero(self):
        with self.assertRaises(ValueError):
            w.parse_korea_kcs_hs6_response(self._response("850423", response_code="20"), "850423", "202609")
        with self.assertRaises(ValueError):
            w.parse_korea_kcs_hs6_response(b"invalid xml", "850423", "202609")

    def test_kcs_parent_and_children_never_double_count(self):
        xml = self._response("850423", us_dlr=100, kg=20)
        xml = xml.replace(b"</items>", (
            b"<item><hsCd>8504230000</hsCd><year>2026.09</year>"
            b"<statCd>US</statCd><expDlr>100</expDlr><expWgt>20</expWgt></item></items>"
        ))
        result = w.parse_korea_kcs_hs6_response(xml, "850423", "202609")
        self.assertEqual(result["export_usd"], 100)
        self.assertEqual(result["level"], "HS6")

    def test_kcs_child_only_and_duplicate_guards(self):
        result = w.parse_korea_kcs_hs6_response(
            self._response("850434", children=True), "850434", "202609")
        self.assertEqual(result["level"], "HSK10_SUM")
        xml = self._response("850434", children=True)
        duplicate = xml.replace(b"</items>", (
            b"<item><hsCd>8504340000</hsCd><year>2026.09</year>"
            b"<statCd>US</statCd><expDlr>100</expDlr><expWgt>10</expWgt></item></items>"
        ))
        with self.assertRaises(ValueError):
            w.parse_korea_kcs_hs6_response(duplicate, "850434", "202609")

    def test_assembler_requires_all_codes_and_same_destination(self):
        rows = [
            w.parse_korea_kcs_hs6_response(self._response(c), c, "202609")
            for c in w.KOREA_EXPORT_HS6
        ]
        result = w.assemble_korea_export_month(rows, "2026-09")
        self.assertEqual(result["export_usd"], 300)
        self.assertEqual(result["net_weight_kg"], 15)
        self.assertEqual(result["average_usd_per_kg"], 20)
        with self.assertRaises(ValueError):
            w.assemble_korea_export_month(rows[:2], "2026-09")
        rows[-1]["country"] = "CN"
        with self.assertRaises(ValueError):
            w.assemble_korea_export_month(rows, "2026-09")

    def test_reported_value_price_decomposition(self):
        r = w.KOREA_EXPORT_REFERENCE
        self.assertAlmostEqual(
            w.korea_claim_implied_weight_growth(r["yoy_pct"], r["unit_price_yoy_pct"]), 53.57142857, places=4)
        self.assertAlmostEqual(
            w.korea_claim_implied_weight_growth(r["mom_pct"], r["unit_price_mom_pct"]), 33.84798099, places=4)
        with self.assertRaises(ValueError):
            w.korea_claim_implied_weight_growth(10, -100)

    def test_korea_us_customs_comparison_uses_exact_matching_hs_and_country(self):
        prev = {"hs_codes": list(w.KOREA_EXPORT_HS6), "destination": "US",
                "export_usd": 1000, "net_weight_kg": 100, "average_usd_per_kg": 10}
        cur = {"hs_codes": list(w.KOREA_EXPORT_HS6), "destination": "US",
               "export_usd": 1500, "net_weight_kg": 125, "average_usd_per_kg": 12}
        g = w.korea_export_growth(cur, prev)
        self.assertAlmostEqual(g["value_pct"], 50)
        self.assertAlmostEqual(g["weight_pct"], 25)
        self.assertAlmostEqual(g["unit_value_pct"], 20)
        self.assertIsNone(w.korea_export_growth({**cur, "destination": "KR"}, prev))
        self.assertIsNone(w.korea_export_growth({**cur, "hs_codes": ["850423"]}, prev))

    def test_bootstrap_missing_key_never_promotes_official_or_resends(self):
        now = datetime(2026, 10, 9, 19, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        with mock.patch.dict(w.os.environ, {"KCS_DATA_GO_SERVICE_KEY": ""}):
            state, events = w.update_korea_export_watch(now, {})
            self.assertEqual([x["kind"] for x in events], ["article_reference"])
            self.assertEqual(state["last_status"], "kcs_key_missing")
            self.assertEqual(state["official_us_by_month"], {})
            next_state, other_events = w.update_korea_export_watch(now, state)
            self.assertEqual(other_events, [])
            self.assertTrue(next_state["baseline_notified"])

    def test_same_day_key_recovery_retries_missing_key_state(self):
        now = datetime(2026, 10, 9, 21, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        cached = {
            **w.KOREA_EXPORT_BASELINE,
            "baseline_notified": True,
            "last_attempt_day": "2026-10-09",
            "last_status": "kcs_key_missing",
        }
        def fake_fetch(hs, ym, country="US"):
            return {"hs6": hs, "month": ym[:4] + "-" + ym[4:],
                    "country": country, "export_usd": 1_000_000, "net_weight_kg": 50_000}
        with mock.patch.dict(w.os.environ, {"KCS_DATA_GO_SERVICE_KEY": "new-key"}):
            with mock.patch.object(w, "fetch_korea_kcs_hs6_month", side_effect=fake_fetch) as spy:
                later, events = w.update_korea_export_watch(now, cached)
        self.assertEqual(spy.call_count, 9)
        self.assertEqual(later["last_status"], "verified")
        self.assertIn("2026-09", later["official_us_by_month"])
        self.assertEqual([x["kind"] for x in events], ["official_us_month"])

    def test_actions_rerun_rechecks_credentials_despite_same_day_denial(self):
        now = datetime(2026, 10, 9, 22, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        previous = {
            **w.KOREA_EXPORT_BASELINE,
            "baseline_notified": True,
            "last_status": "kcs_access_denied",
            "last_attempt_day": "2026-10-09",
            "last_attempt_at_kst": "2026-10-09T21:35:36+09:00",
            "fetch_revision": w.KOREA_EXPORT_FETCH_REVISION,
            "source_blocker_notified": True,
        }
        self.assertFalse(w.kcs_retry_due(now, previous, True))
        self.assertTrue(w.kcs_retry_due(now, previous, True, force=True))
        # Missing credentials must still record the missing-key state once.
        self.assertTrue(w.kcs_retry_due(now, previous, False, force=True))
        with mock.patch.dict(w.os.environ, {
            "GITHUB_RUN_ATTEMPT": "2",
            "KCS_DATA_GO_SERVICE_KEY": "dummy",
        }):
            def fake_fetch(hs, ym, country="US"):
                return {
                    "hs6": hs, "month": ym[:4] + "-" + ym[4:],
                    "country": country, "export_usd": 100000,
                    "net_weight_kg": 1000,
                }
            with mock.patch.object(w, "fetch_korea_kcs_hs6_month", side_effect=fake_fetch) as spy:
                state, events = w.update_korea_export_watch(now, previous)
            self.assertEqual(spy.call_count, 9)
            self.assertEqual(state["last_status"], "verified")
            self.assertEqual([e["kind"] for e in events], ["official_us_month"])

    def test_kcs_restored_old_months_clear_access_blocker_once(self):
        now = datetime(2026, 10, 9, 22, 10, tzinfo=ZoneInfo("Asia/Seoul"))
        snapshot = {
            "month": "2026-08", "destination": "US",
            "hs_codes": list(w.KOREA_EXPORT_HS6), "export_usd": 152378128,
            "net_weight_kg": 9561809, "average_usd_per_kg": 15.936,
        }
        previous = {
            **w.KOREA_EXPORT_BASELINE, "baseline_notified": True,
            "source_blocker_notified": True,
            "last_status": "month_unpublished",
            "last_error_kind": "kcs_no_official_rows",
            "last_attempt_day": "2026-10-09",
            "last_attempt_at_kst": "2026-10-09T21:59:09+09:00",
            "fetch_revision": w.KOREA_EXPORT_FETCH_REVISION,
            "latest_official_us_month": "2026-08",
            "official_us_by_month": {"2026-08": snapshot},
        }
        with mock.patch.dict(w.os.environ, {
            "GITHUB_RUN_ATTEMPT": "1",
            "KCS_DATA_GO_SERVICE_KEY": "not-a-real-key",
        }):
            with mock.patch.object(w, "fetch_korea_kcs_hs6_month") as fetch:
                restored, first_events = w.update_korea_export_watch(now, previous)
                self.assertEqual([x["kind"] for x in first_events], ["kcs_connection_restored"])
                self.assertFalse(restored["source_blocker_notified"])
                self.assertTrue(restored["connection_restored_notified"])
                self.assertEqual(restored["last_status"], "month_unpublished")
                quiet, second_events = w.update_korea_export_watch(now, restored)
                self.assertEqual(second_events, [])
                fetch.assert_not_called()
        rendered = w.build_korea_export_alert(first_events[0], restored, {"latest_month": "2026-08"})
        self.assertIn("API 연결 확인", rendered)
        self.assertIn("2026-08", rendered)
        self.assertIn("아직 완전한 품목별 조회 결과가 없어", rendered)

    def test_kcs_stale_connection_does_not_claim_fresh_recovery(self):
        now = datetime(2026, 10, 9, 22, 10, tzinfo=ZoneInfo("Asia/Seoul"))
        state = {
            "last_status": "month_unpublished",
            "last_attempt_at_kst": "2026-10-01T08:00:00+09:00",
            "source_blocker_notified": True,
            "official_us_by_month": {"2026-08": {"export_usd": 100}},
            "latest_official_us_month": "2026-08",
        }
        events = []
        w.record_kcs_connection_recovery(now, state, events)
        self.assertFalse(state["source_blocker_notified"])
        self.assertEqual(events, [])

    def test_kcs_network_failure_classification_is_safe(self):
        import urllib.error
        import socket
        self.assertEqual(
            w.kcs_error_category(urllib.error.URLError(socket.gaierror(-2, "name resolution"))),
            "kcs_dns_unavailable",
        )
        self.assertEqual(
            w.kcs_error_category(urllib.error.HTTPError("https://example.org", 403, "denied", {}, None)),
            "kcs_http_access_denied",
        )
        self.assertEqual(
            w.kcs_error_category(urllib.error.URLError(TimeoutError("timed out"))),
            "kcs_network_timeout",
        )

    def test_kcs_transient_errors_retry_after_90_minutes_only(self):
        now = datetime(2026, 10, 9, 22, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        state = {
            "last_attempt_day": "2026-10-09",
            "last_attempt_at_kst": "2026-10-09T21:00:00+09:00",
            "last_status": "api_inaccessible_or_unpublished",
            "last_error_kind": "kcs_dns_unavailable",
            "fetch_revision": w.KOREA_EXPORT_FETCH_REVISION,
        }
        self.assertFalse(w.kcs_retry_due(now, state, True))
        later = datetime(2026, 10, 9, 22, 35, tzinfo=ZoneInfo("Asia/Seoul"))
        self.assertTrue(w.kcs_retry_due(later, state, True))
        state["last_error_kind"] = "kcs_http_access_denied"
        self.assertFalse(w.kcs_retry_due(later, state, True))
        state["fetch_revision"] = -1
        self.assertTrue(w.kcs_retry_due(now, state, True))
        state["last_status"] = "kcs_key_missing"
        self.assertTrue(w.kcs_retry_due(now, state, True))

    def test_existing_access_denial_one_time_alert_even_when_retry_backed_off(self):
        now = datetime(2026, 10, 9, 21, 45, tzinfo=ZoneInfo("Asia/Seoul"))
        cached = {
            **w.KOREA_EXPORT_BASELINE,
            "baseline_notified": True,
            "last_status": "api_inaccessible_or_unpublished",
            "last_error_kind": "kcs_http_access_denied",
            "last_attempt_day": "2026-10-09",
            "last_attempt_at_kst": "2026-10-09T21:35:00+09:00",
            "fetch_revision": w.KOREA_EXPORT_FETCH_REVISION,
        }
        with mock.patch.dict(w.os.environ, {"KCS_DATA_GO_SERVICE_KEY": "secret"}):
            with mock.patch.object(w, "fetch_korea_kcs_hs6_month") as fetch:
                latest, events = w.update_korea_export_watch(now, cached)
                self.assertEqual([x["kind"] for x in events], ["kcs_access_blocker"])
                self.assertEqual(latest["last_status"], "kcs_access_denied")
                self.assertTrue(latest["source_blocker_notified"])
                fetch.assert_not_called()
                next_state, events2 = w.update_korea_export_watch(now, latest)
                self.assertEqual(events2, [])
                fetch.assert_not_called()

    def test_permission_denial_emits_exactly_one_operator_notice(self):
        import urllib.error
        now = datetime(2026, 10, 9, 21, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        previous = {**w.KOREA_EXPORT_BASELINE, "baseline_notified": True}
        err = urllib.error.HTTPError("https://redacted.example", 403, "Forbidden", {}, None)
        with mock.patch.dict(w.os.environ, {"KCS_DATA_GO_SERVICE_KEY": "secret-never-display"}):
            with mock.patch.object(w, "fetch_korea_kcs_hs6_month", side_effect=err):
                state, events = w.update_korea_export_watch(now, previous)
                self.assertEqual(state["last_status"], "kcs_access_denied")
                self.assertEqual(state["last_error_kind"], "kcs_http_access_denied")
                self.assertTrue(state["source_blocker_notified"])
                self.assertEqual([x["kind"] for x in events], ["kcs_access_blocker"])
                quiet, events2 = w.update_korea_export_watch(now, state)
                self.assertEqual(events2, [])
                tomorrow = datetime(2026, 10, 10, 21, 0, tzinfo=ZoneInfo("Asia/Seoul"))
                again, events3 = w.update_korea_export_watch(tomorrow, quiet)
                self.assertEqual(events3, [])
                self.assertEqual(again["last_status"], "kcs_access_denied")
        message = w.build_korea_export_alert(events[0], state, {"latest_month": "2026-08"})
        self.assertIn("접근 권한 확인 필요", message)
        self.assertIn("활용신청", message)
        self.assertNotIn("secret-never-display", message)
        self.assertNotIn("미국향 3개 HS 합계", message)

    def test_kcs_auth_xml_error_codes_are_not_unpublished(self):
        self.assertEqual(w.kcs_error_category(ValueError("kcs_result_20")), "kcs_service_access_denied")
        self.assertEqual(w.kcs_error_category(ValueError("kcs_result_30")), "kcs_key_unregistered")
        self.assertEqual(w.kcs_error_category(ValueError("kcs_result_31")), "kcs_key_expired")
        self.assertEqual(w.kcs_error_category(ValueError("kcs_result_22")), "kcs_http_retryable")

    def test_fetched_usa_customs_month_alert_once(self):
        now = datetime(2026, 10, 9, 19, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        def fake_fetch(hs, ym, country="US"):
            return {"hs6": hs, "month": ym[:4] + "-" + ym[4:],
                    "country": country, "export_usd": 100_000_000, "net_weight_kg": 5_000_000}
        with mock.patch.dict(w.os.environ, {"KCS_DATA_GO_SERVICE_KEY": "dummy-token"}):
            with mock.patch.object(w, "fetch_korea_kcs_hs6_month", side_effect=fake_fetch):
                state, events = w.update_korea_export_watch(now, {})
                self.assertEqual([x["kind"] for x in events], ["article_reference", "official_us_month"])
                self.assertIn("2026-09", state["official_us_by_month"])
                self.assertEqual(state["official_us_by_month"]["2026-09"]["export_usd"], 300_000_000)
                state2, again = w.update_korea_export_watch(now, state)
                self.assertEqual(again, [])
                self.assertEqual(state2["latest_official_us_month"], "2026-09")
        with mock.patch.object(w, "usdkrw_rate", return_value=(1400.0, "2026-10-08")):
            text = w.build_korea_export_alert(events[0], state, {"latest_month": "2026-08"})
            self.assertIn("기사 잠정치, 공식 HS 원자료 미대조", text)
            self.assertIn("10,000kVA 초과", text)
            self.assertIn("관세청 통계 API 명세", text)
            self.assertNotIn("미국향 단독 실적이 아님", w.build_korea_export_alert(events[1], state, {}))

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

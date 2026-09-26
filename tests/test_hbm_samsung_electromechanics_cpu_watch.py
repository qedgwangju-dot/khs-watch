import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_electromechanics_cpu_watch as w


class SamsungElectroMechanicsCpuParserTests(unittest.TestCase):
    def test_parse_krw_amount(self):
        self.assertEqual(w.parse_krw_100m("3조 8,200억"), 38200.0)
        self.assertEqual(w.parse_krw_100m("6,571억"), 6571.0)
        self.assertEqual(w.parse_krw_100m("1조 722억"), 10722.0)

    def test_parse_q3_actual_requires_official(self):
        text = "삼성전기 2026년 3분기 경영실적 매출 3조 9,000억 원, 영업이익 7,000억 원을 기록했다."
        self.assertEqual(w.parse_q3_result(text, False), {})
        actual = w.parse_q3_result(text, True)
        self.assertEqual(actual["revenue_krw_100m"], 39000.0)
        self.assertEqual(actual["operating_profit_krw_100m"], 7000.0)
        self.assertAlmostEqual(actual["opm_pct"], 7000 / 39000 * 100)

    def test_target_price_only_does_not_trigger(self):
        text = "삼성전기 메리츠 목표주가를 220만원에서 240만원으로 상향하고 투자의견 매수를 유지했다."
        self.assertEqual(w.parse_research_update(text, True), {})

    def test_material_research_thresholds(self):
        small = {
            "kind": "research_update",
            "q3_revenue_forecast_krw_100m": 40000.0,
            "q3_operating_profit_forecast_krw_100m": 7100.0,
        }
        changes = w.material_research_changes(w.BASELINE["metrics"], small)
        self.assertFalse(any(x["key"] == "q3_revenue_forecast_krw_100m" for x in changes))
        self.assertFalse(any(x["key"] == "q3_operating_profit_forecast_krw_100m" for x in changes))

        large = {
            "kind": "research_update",
            "q3_revenue_forecast_krw_100m": 40500.0,
            "q3_operating_profit_forecast_krw_100m": 7300.0,
            "cpu_abf_share_pct": 51.0,
        }
        changes = w.material_research_changes(w.BASELINE["metrics"], large)
        keys = {x["key"] for x in changes}
        self.assertIn("q3_revenue_forecast_krw_100m", keys)
        self.assertIn("q3_operating_profit_forecast_krw_100m", keys)
        self.assertIn("cpu_abf_share_pct", keys)

    def test_mlcc_contract_requires_official_and_amount(self):
        text = "삼성전기가 글로벌 고객과 MLCC 장기공급계약을 체결했다. 공급계약 금액은 1조 2,000억 원이다."
        self.assertEqual(w.mlcc_contract_signal(text, False), {})
        event = w.mlcc_contract_signal(text, True)
        self.assertEqual(event["amount_krw_100m"], 12000.0)

    def test_named_customer_signal_requires_official(self):
        text = "삼성전기 FCBGA가 AMD 서버 CPU에 공급된다."
        self.assertEqual(w.named_cpu_customer_signal(text, False), "")
        self.assertIn("AMD", w.named_cpu_customer_signal(text, True))

    def test_venice_validation_signal(self):
        text = "Meta is validating 6th Gen EPYC Venice platforms and preparing to deploy at scale."
        self.assertIn("Venice", w.venice_deployment_signal(text, True))


class SamsungElectroMechanicsCpuAlertTests(unittest.TestCase):
    def test_actual_vs_forecast(self):
        actual = {
            "revenue_krw_100m": 40110.0,
            "operating_profit_krw_100m": 7228.1,
        }
        comp = w.actual_vs_forecast(actual, w.BASELINE)
        self.assertAlmostEqual(comp["revenue_delta_pct"], 5.0, places=1)
        self.assertAlmostEqual(comp["operating_profit_delta_pct"], 10.0, places=1)

    def test_alert_has_required_sections_and_fact_separation(self):
        events = [{
            "kind": "q3_actual",
            "revenue_krw_100m": 39000.0,
            "operating_profit_krw_100m": 7000.0,
            "opm_pct": 7000 / 39000 * 100,
        }]
        alert = w.build_alert(events, w.BASELINE, "https://www.samsungsem.com/example", "2026-10-30T09:00:00+09:00")
        self.assertIn("삼성전기 CPU 매출 실현 게이트", alert)
        self.assertIn("현재 기준선", alert)
        self.assertIn("매출 연결", alert)
        self.assertIn("확정·추정 구분", alert)
        self.assertIn("숨은 역풍·실패모드", alert)
        self.assertIn("알림 기준", alert)
        self.assertIn("3조8,200억원", alert)
        self.assertIn("6,571억원", alert)
        self.assertIn("1조722억원", alert)
        self.assertIn("목표주가만 바뀌거나", alert)


if __name__ == "__main__":
    unittest.main()

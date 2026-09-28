import copy
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import tsmc_leading_node_watch as w


def event(text, source="경제일보"):
    return {
        "id": "e1",
        "title": "TSMC 2nm capacity update",
        "description": text,
        "source": source,
        "published_at_kst": "2026-09-28T02:06:00+09:00",
        "direct_link": w.UDN_BASELINE,
        "evidence_state": "supply_chain_report",
    }


class TSMCLeadingNodeTests(unittest.TestCase):
    def test_current_udn_extracts_120k_and_customer_additional_booking(self):
        text = (
            "台積電2奈米家族今年底月產能將衝刺12萬片。"
            "蘋果、輝達、超微、高通、聯發科近期追加預訂2奈米產能，增幅達10%至20%。"
        )
        e = event(text)
        with patch.object(w, "article_text", return_value=""):
            p = w.extract_patch(e)
        self.assertEqual(p["capacity_targets"]["N2|2026YE"]["value"], 120000)
        self.assertEqual(p["customer_reservation"]["min_pct"], 10)
        self.assertEqual(p["customer_reservation"]["max_pct"], 20)
        self.assertEqual(p["customer_reservation"]["ai_hbm_customers"], ["AMD", "NVIDIA"])

    def test_old_90_100k_reference_does_not_override_new_120k_target(self):
        text = (
            "市場原本預估今年底2奈米月產能約9萬至10萬片。"
            "業界傳出今年底2奈米月產能將衝刺12萬片。"
        )
        caps = w._capacity_targets(text, event(text))
        self.assertEqual(caps["N2|2026YE"]["value"], 120000)

    def test_capacity_threshold_is_10k_or_10pct(self):
        old = {"capacity_targets": {"N2|2026YE": {"value": 120000, "evidence_state": "supply_chain_report"}}}
        small = {"capacity_targets": {"N2|2026YE": {"value": 125000, "evidence_state": "supply_chain_report"}}}
        big = {"capacity_targets": {"N2|2026YE": {"value": 132000, "evidence_state": "supply_chain_report"}}}
        self.assertEqual(w.material_changes(old, small), [])
        self.assertTrue(any("120,000→132,000" in x for x in w.material_changes(old, big)))

    def test_customer_booking_10pp_change_alerts(self):
        old = {"customer_reservation": {"min_pct": 10.0, "max_pct": 20.0, "customers": ["AMD", "NVIDIA"], "evidence_state": "supply_chain_report"}}
        new = {"customer_reservation": {"min_pct": 20.0, "max_pct": 30.0, "customers": ["AMD", "NVIDIA"], "evidence_state": "supply_chain_report"}}
        self.assertTrue(any("10~20%→20~30%" in x for x in w.material_changes(old, new)))

    def test_wafer_price_five_percent_change_alerts(self):
        old = {"wafer_prices": {"N2": {"value_usd": 30000, "evidence_state": "supply_chain_report"}}}
        new = {"wafer_prices": {"N2": {"value_usd": 31500, "evidence_state": "supply_chain_report"}}}
        self.assertTrue(any("N2 웨이퍼 가격 +5.0%" in x for x in w.material_changes(old, new)))

    def test_same_baseline_stays_silent(self):
        cur = {
            "capacity_targets": {"N2|2026YE": {"value": 120000, "evidence_state": "supply_chain_report"}},
            "customer_reservation": {"min_pct": 10.0, "max_pct": 20.0, "customers": ["AMD", "Apple", "NVIDIA"], "evidence_state": "supply_chain_report"},
        }
        self.assertEqual(w.material_changes(cur, copy.deepcopy(cur)), [])

    def test_alert_has_no_hanja(self):
        state = {
            "capacity_targets": {"N2|2026YE": {"value": 120000}, "N3|2026Q4": {"value": 180000}, "N3|2027": {"min": 200000, "max": 210000}},
            "customer_reservation": {"min_pct": 10.0, "max_pct": 20.0, "customers": ["Apple", "NVIDIA", "AMD"]},
            "n2_fabs_2026": 5,
            "n2_first_year_vs_n3_pct": 45,
            "n2_cagr_2026_2028_pct": 70,
            "n2_gross_margin_dilution": {"min_pp": 2.0, "max_pp": 3.0},
            "last_source_url": w.UDN_BASELINE,
            "last_source_name": "經濟日報",
        }
        out = w.alert_text(state, ["N2|2026YE 월 생산능력 100,000→120,000장 (+20.0%)"], w.now_kst())
        self.assertNotRegex(out, w.HAN_RE)
        self.assertIn("경제일보", out)


if __name__ == "__main__":
    unittest.main()

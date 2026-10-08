#!/usr/bin/env python3
"""Regression tests for Samsung MX production/order cuts and provenance."""
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "samsung_mx_production_watch",
    ROOT / "scripts" / "samsung_mx_production_watch.py",
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class SamsungMXProductionWatchTests(unittest.TestCase):
    date = m.dt.datetime(2026, 10, 8, 10, tzinfo=m.KST)

    def item(self, text, source="머니투데이", url="https://www.mt.co.kr/test"):
        return {
            "title": text, "description": "", "source": source,
            "link": url, "published_at_kst": self.date.isoformat(),
        }

    def state(self):
        return {
            "metrics": dict(m.BASELINE),
            "seen_fact_keys": list(m.BASE_FACTS),
        }

    def test_article_scope_only_q4_not_full_year(self):
        text = "삼성전자 2026년 4분기 스마트폰 생산량 최대 30% 줄인다"
        got = m._production_metrics(text, self.date)
        self.assertEqual(got["finished_production"], (30, 30))
        self.assertNotIn("annual", got)

    def test_supplier_20_to_30_is_not_finished_device(self):
        text = "삼성 MX 4분기 스마트폰 협력사 부품 납품량 20~30% 줄여달라"
        got = m._production_metrics(text, self.date)
        self.assertEqual(got["supplier_orders"], (20, 30))
        self.assertNotIn("finished_production", got)

    def test_175_pct_memory_price_rise_is_not_production_cut(self):
        text = (
            "삼성전자 2026년 4분기 스마트폰 메모리 가격 175% 상승;"
            "IDC 출하량 5200만대 전망."
        )
        self.assertEqual(m._production_metrics(text, self.date), {})

    def test_30pct_price_rise_does_not_steal_cut_signal(self):
        text = (
            "Samsung 2026 Q4 smartphone memory prices rose 30%; "
            "Samsung may cut smartphone production but gave no percentage."
        )
        self.assertEqual(m._production_metrics(text, self.date), {})

    def test_same_original_reporting_is_not_new_event(self):
        text = "삼성전자 4분기 스마트폰 생산량 최대 30% 줄인다"
        self.assertIsNone(m._event(self.item(text), self.state()))

    def test_changed_production_cut_can_notify_as_report_only(self):
        text = "삼성전자 4분기 스마트폰 생산량 최대 45% 줄인다"
        event = m._event(self.item(text), self.state())
        self.assertIsNotNone(event)
        self.assertEqual(event["stage"], 2)
        self.assertFalse(event["official"])

    def test_reuters_story_is_not_samsung_official(self):
        item = self.item(
            "Samsung Q4 smartphone production to be cut by 45%",
            "Reuters", "https://www.reuters.com/world/samsung-story"
        )
        event = m._event(item, self.state())
        self.assertIsNotNone(event)
        self.assertFalse(event["official"])
        self.assertLess(event["stage"], 3)

    def test_samsung_named_in_title_does_not_imply_official(self):
        item = self.item(
            "Samsung says Q4 smartphone production cut 45%",
            "머니투데이", "https://news.google.com/rss/articles/xyz"
        )
        self.assertFalse(m._official_url(item))

    def test_samsung_newsroom_direct_domain_counts_official(self):
        item = self.item(
            "Samsung Q4 smartphone production cut 30%",
            "Samsung Global Newsroom",
            "https://news.samsung.com/global/mx-official-release"
        )
        event = m._event(item, self.state())
        self.assertIsNotNone(event)
        self.assertTrue(event["official"])
        self.assertEqual(event["stage"], 3)

    def test_low_trust_republication_does_not_notify(self):
        item = self.item(
            "Samsung Q4 smartphone production cut 50%",
            "notebookcheck.net", "https://www.notebookcheck.net/repost"
        )
        self.assertIsNone(m._event(item, self.state()))

    def test_different_year_not_mislabeled_2026(self):
        date = m.dt.datetime(2027, 10, 8, 10, tzinfo=m.KST)
        self.assertEqual(
            m._production_metrics("Samsung 2027 Q4 smartphone production cut 30%", date),
            {},
        )

    def test_no_q4_period_is_not_assumed(self):
        self.assertEqual(
            m._production_metrics("Samsung smartphone production cut 30% this year", self.date),
            {},
        )

    def test_correct_baselines_are_separate(self):
        self.assertEqual(m.BASELINE["idc_q2_actual_shipments_m"], 62.7)
        self.assertEqual(m.BASELINE["q4_forecast_m_article"], 52.0)
        self.assertEqual(m.BASELINE["production_cut_max_pct"], 30.0)
        self.assertEqual(m.BASELINE["supplier_order_cut_min_pct"], 20.0)

    def test_initial_alert_labels_provenance(self):
        text = m._baseline_alert()
        self.assertIn("공식 확정 생산계획", text)
        self.assertIn("전망치", text)
        self.assertIn("복수 관계자", text)

    def test_old_baseline_fact_keys_are_stable(self):
        self.assertIn("samsung_2026q4_production_cut_30_reported", m.BASE_FACTS)

    def test_q4_idc_forecast_52m_repeat_does_not_alert(self):
        item = self.item("IDC forecasts Samsung 2026 Q4 smartphone shipments at 52 million units", "IDC")
        self.assertIsNone(m._event(item, self.state()))

    def test_q4_idc_forecast_45m_can_alert_not_as_production(self):
        item = self.item("IDC cuts Samsung 2026 Q4 smartphone shipments forecast from 52 million units to 45 million units", "IDC")
        signal = m._event(item, self.state())
        self.assertIsNotNone(signal)
        self.assertEqual(signal["changes"]["q4_forecast_m_latest"], 45)
        self.assertNotIn("production_cut_max_pct", signal["changes"])
        self.assertIn("출하전망", signal["reasons"][0])

    def test_2027_idc_q4_actual_is_not_the_q4_forecast(self):
        item = self.item(
            "IDC Samsung 2026 Q4 actual smartphone shipments reached 48 million units",
            "IDC",
            "https://www.idc.com/research/samsung-2026-q4-results",
        )
        item["published_at_kst"] = "2027-01-15T09:00:00+09:00"
        signal = m._event(item, self.state())
        self.assertIsNotNone(signal)
        self.assertEqual(signal["changes"]["q4_actual_shipments_m"], 48)
        self.assertNotIn("q4_forecast_m_latest", signal["changes"])

    def test_multiple_ambiguous_q4_volumes_are_not_guessed(self):
        blob = "IDC Samsung 2026 Q4 smartphone shipments forecast at 52 million units or 45 million units"
        self.assertIsNone(m._quarter_volume_m(blob, self.date))

    def test_annual_samsung_270m_not_mislabeled_q4(self):
        blob = "IDC Samsung full-year 2026 smartphone shipments forecast 270 million units"
        self.assertIsNone(m._quarter_volume_m(blob, self.date))

    def test_apple_volume_not_attributed_to_samsung_mention_elsewhere(self):
        blob = "Samsung smartphone market outlook | Apple 2026 Q4 smartphone shipments forecast 45 million units"
        self.assertIsNone(m._quarter_volume_m(blob, self.date))
        self.assertEqual(m._production_metrics(
            "Samsung market update | Apple Q4 2026 smartphone production cut 40%", self.date
        ), {})

if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SamsungMXProductionWatchTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)

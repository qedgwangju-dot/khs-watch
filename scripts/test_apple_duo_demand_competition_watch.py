#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "apple_duo_demand_competition_watch.py"
spec = importlib.util.spec_from_file_location("apple_duo_demand_competition_watch", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


class AppleDuoDemandRegressionTests(unittest.TestCase):
    def base_state(self):
        return {
            "metrics": {
                "fold8_korea_wow_pct": 10.0,
                "duo_256_price_krw": 3290000,
                "fold8_256_price_krw": 2278100,
                "price_gap_krw": 1011900,
            }
        }

    def test_fold8_percent_not_reused_as_duo_direct_demand(self):
        blob = (
            "Galaxy Z Fold 8 sales in South Korea rose 10% week on week "
            "after Apple unveiled iPhone Duo."
        )
        comp = m._sales_pct_for_entity(blob, m.COMPETITOR_MARKERS, m.APPLE_MARKERS)
        duo = m._sales_pct_for_entity(blob, m.APPLE_MARKERS, m.COMPETITOR_MARKERS)
        self.assertEqual(comp, 10.0)
        self.assertIsNone(duo)

    def test_no_direct_commercial_demand_before_preorder(self):
        item = {
            "title": "iPhone Duo sales rise 20% in Korea",
            "description": "Strong sales after unveil",
            "source": "Reuters",
            "published_at_kst": "2026-09-20T09:00:00+09:00",
            "link": "https://example.com/a",
        }
        self.assertIsNone(m._signal(item, self.base_state()))

    def test_direct_preorder_signal_allowed_after_official_preorder(self):
        item = {
            "title": "iPhone Duo preorders rise 20% in Korea",
            "description": "Carrier preorder demand increased 20%",
            "source": "Reuters",
            "published_at_kst": "2026-10-17T09:00:00+09:00",
            "link": "https://example.com/b",
        }
        signal = m._signal(item, self.base_state())
        self.assertIsNotNone(signal)
        self.assertTrue(any("iPhone Duo 직접 수요 지표 +20%" in x for x in signal["reasons"]))

    def test_mixed_article_attributes_each_percentage_to_correct_product(self):
        blob = (
            "Galaxy Z Fold 8 sales rose 10% while iPhone Duo preorders fell 15% "
            "after preorder launch."
        )
        comp = m._sales_pct_for_entity(blob, m.COMPETITOR_MARKERS, m.APPLE_MARKERS)
        duo = m._sales_pct_for_entity(blob, m.APPLE_MARKERS, m.COMPETITOR_MARKERS)
        self.assertEqual(comp, 10.0)
        self.assertEqual(duo, -15.0)

    def test_initial_stockout_is_not_actual_sales(self):
        item = {"title": "iPhone Duo preorders sell out in minutes; shipping slips to November 23", "description": "Apple iPhone Duo production and delivery plans",
                "source": "Reuters", "link": "https://example.com",
                "published_at_kst": "2026-10-16T21:10:00+09:00"}
        self.assertIsNone(m._signal(item, self.base_state()))

    def test_shipping_backorder_is_not_actual_sales(self):
        item = {"title": "iPhone Duo shipping estimates slip to 2027; first allocation sold out", "description": "Apple iPhone Duo production and delivery plans",
                "source": "Reuters", "link": "https://example.com",
                "published_at_kst": "2026-10-16T21:10:00+09:00"}
        self.assertIsNone(m._signal(item, self.base_state()))

    def test_production_growth_not_duo_preorder_growth(self):
        item = {"title": "iPhone Duo preorders start; production up 30% following ramp", "description": "Apple iPhone Duo production and delivery plans",
                "source": "Reuters", "link": "https://example.com",
                "published_at_kst": "2026-10-16T21:10:00+09:00"}
        self.assertIsNone(m._signal(item, self.base_state()))

    def test_forecast_millions_not_actual_orders(self):
        item = {"title": "iPhone Duo preorders open; production target forecast 10 million units", "description": "Apple iPhone Duo production and delivery plans",
                "source": "Reuters", "link": "https://example.com",
                "published_at_kst": "2026-10-16T21:10:00+09:00"}
        self.assertIsNone(m._signal(item, self.base_state()))

    def test_44percent_duo_build_target_not_direct_preorder_sales(self):
        item = {
            "title": "Apple iPhone Duo 12-month build target boosted 44% to 14 million",
            "description": "After strong preorders, Foxconn supplier component orders from 9.7 million.",
            "source": "Reuters",
            "published_at_kst": "2026-10-22T12:00:00+09:00",
            "link": "https://example.org/duo",
        }
        self.assertIsNone(m._signal(item, self.base_state()))

    def test_notebookcheck_cannot_trigger_demand_alert_alone(self):
        item = {
            "title": "Surprise! Galaxy Z Fold 8 sees 10% sales jump after Apple's iPhone Duo launch",
            "description": "Galaxy Z Fold 8 sales in South Korea rose roughly 10 percent week on week.",
            "source": "notebookcheck.net",
            "published_at_kst": "2026-09-17T23:41:00+09:00",
            "link": "https://www.notebookcheck.net/example",
        }
        self.assertEqual(m._source_rank(item["source"]), 0)
        self.assertIsNone(m._signal(item, self.base_state()))


    def test_applemagazine_cannot_trigger_duo_direct_demand_as_official(self):
        self.assertEqual(m._source_rank("AppleMagazine"),1)
        self.assertEqual(m._source_rank("Apple"),3)
        self.assertEqual(m._source_rank("Apple Newsroom"),3)
        item={
            "title":"iPhone Duo Korea preorders rise 29% from launch",
            "description":"China Pro sales and premium demand shifted",
            "source":"AppleMagazine",
            "link":"https://news.google.com/rss/articles/syndicated",
            "published_at_kst":"2026-10-29T09:00:00+09:00",
        }
        self.assertIsNone(m._signal(item,self.base_state()))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AppleDuoDemandRegressionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)

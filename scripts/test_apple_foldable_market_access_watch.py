#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest

FILE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "apple_foldable_market_access_watch.py"
spec = importlib.util.spec_from_file_location("foldable_market_access", FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FoldableMarketAccessTests(unittest.TestCase):
    def item(self, text, source="Forbes"):
        return {"title":text,"description":"","source":source,"link":"https://example.com","id":"abc"}

    def test_korea_official_notice(self):
        v="<div>온라인으로 구입하고, Apple Store에서 픽업하세요. iPhone Duo 및 iPhone 18 Pro Max는 현재 Apple Store에서 현장 구매를 할 수 없습니다.</div>"
        self.assertEqual(m._official_access(v,"한국"),"reservation_only")

    def test_japan_official_notice(self):
        v="<div>しばらくの期間、お近くのApple Storeでは、最新のiPhone DuoとiPhone 18 Pro Maxを予約せずに購入することはできません。</div>"
        self.assertEqual(m._official_access(v,"일본"),"reservation_only")

    def test_japanese_official_notice_with_nonbreaking_spaces(self):
        t="近くのApple Storeでは、iPhone DuoとiPhone 18 Pro Maxを予約せずに購入することはできません。"
        self.assertEqual(m._official_access("<p>"+t+"</p>", "일본"), "reservation_only")

    def test_japan_unavailable_does_not_mask_korean_policy_or_fold8_demand(self):
        msg=m._initial_alert({"한국":"reservation_only","일본":"unknown"})
        self.assertIn("日本",msg.replace("일본","日本"))
        self.assertIn("공식 페이지 직접 확인 불가",msg)
        self.assertIn("고객 수요 출시 이후",msg)

    def test_missing_official_notice_never_means_reopened(self):
        v="<div>iPhone Duo available October 23. Free pickup available.</div>"
        self.assertEqual(m._official_access(v,"한국"),"unknown")
        self.assertEqual(m._official_access(v,"일본"),"unknown")

    def test_search_interest_is_not_unit_sales(self):
        blob="Samsung foldables registered a 300% increase in active Google searches in the last month."
        self.assertEqual(m._metric_quote(blob,"search"),300)
        self.assertIsNone(m._metric_quote(blob,"fold8"))

    def test_corporate_demand_quote_is_not_google_search(self):
        blob="Customer demand for the Galaxy Z Fold8 family has increased 16% since launch."
        self.assertEqual(m._metric_quote(blob,"fold8"),16)
        self.assertIsNone(m._metric_quote(blob,"search"))

    def test_same_forbes_quote_republication_is_not_new(self):
        t=("Samsung executive Richard Chang said Customer demand for Galaxy Z Fold8 family "
           "has increased 16% since launch and Google searches for Samsung foldables increased 300%.")
        self.assertIsNone(m._fold8_signal(self.item(t),dict(m.BASELINE)))

    def test_fold8_demand_revised_not_google_upsell(self):
        t="Samsung executive Richard Chang said customer demand for Galaxy Z Fold8 family has increased 23% since launch."
        x=m._fold8_signal(self.item(t),dict(m.BASELINE))
        self.assertIsNotNone(x)
        self.assertEqual(x["kind"],"demand")
        self.assertEqual(x["value"],23)

    def test_secondary_publisher_without_direct_quote_is_not_alertable(self):
        t="Galaxy Z Fold8 search interest jumped 400% according to rumors."
        self.assertIsNone(m._fold8_signal(self.item(t,"notebookcheck.net"),dict(m.BASELINE)))

    def test_unverified_percent_not_customer_demand(self):
        t="Samsung executive Richard Chang said Galaxy Z Fold8 sales accounted for 23% of Samsung revenue."
        self.assertIsNone(m._fold8_signal(self.item(t),dict(m.BASELINE)))

    def test_independent_forecasts_preserved(self):
        v=m.BASELINE
        self.assertEqual((v["idc_2026_foldable_m"],v["idc_2026_foldable_yoy_pct"]),(22.9,12.6))
        self.assertEqual((v["trendforce_2026_foldable_m"],v["trendforce_2026_foldable_yoy_pct"]),(20.2,0.5))

    def test_concurrent_checkpoint_preserves_alert_history(self):
        old={"updated_at_kst":"2026-10-20T20:00:00+09:00", "initial_alert_sent":True,
             "seen_ids":["abc"], "metrics":{"fold8_demand_change_pct":16},
             "access":{"한국":"reservation_only"},
             "last_alert":{"at_kst":"2026-10-20T20:00:00+09:00"}}
        new={"updated_at_kst":"2026-10-20T19:00:00+09:00", "initial_alert_sent":False,
             "seen_ids":["def"], "metrics":{"fold8_demand_change_pct":21},
             "access":{"일본":"reservation_only"}}
        merged=m._merge_market_state(old,new)
        self.assertTrue(merged["initial_alert_sent"])
        self.assertEqual(merged["metrics"]["fold8_demand_change_pct"],16)
        self.assertEqual(set(merged["seen_ids"]),{"abc","def"})


if __name__ == "__main__":
    tests=unittest.defaultTestLoader.loadTestsFromTestCase(FoldableMarketAccessTests)
    result=unittest.TextTestRunner(verbosity=2).run(tests)
    if not result.wasSuccessful():
        sys.exit(1)

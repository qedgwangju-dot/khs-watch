#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo
import datetime as dt

FILE=pathlib.Path(__file__).resolve().parents[1]/"scripts"/"apple_duo_preorder_delivery_watch.py"
spec=importlib.util.spec_from_file_location("duo_preorder",FILE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class DuoPreorderTests(unittest.TestCase):
    def pub(self):
        return dt.datetime(2026,10,16,22,30,tzinfo=ZoneInfo("Asia/Seoul"))

    def test_preorder_before_launch_not_direct_sales_evidence(self):
        x=m._shipping_event("iPhone Duo delivery November 23 in the U.S.",dt.datetime(2026,10,15,21,tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertIsNone(x)

    def test_initial_november_delay(self):
        text="iPhone Duo U.S. preorders shipping dates slipped to November 16, then November 23."
        x=m._shipping_event(text,self.pub())
        self.assertEqual(x["month"],"2026-11")
        self.assertEqual(x["market"],"미국")

    def test_december_macrumors_shipping_range(self):
        text="iPhone Duo on Apple's U.S. online store. Delivery estimates December 15 to December 22."
        x=m._shipping_event(text,self.pub())
        self.assertEqual(x["month"],"2026-12")
        self.assertIn("22일",x["label"])

    def test_late_january_without_invented_day(self):
        x=m._shipping_event("iPhone Duo U.S. online orders: shipping has slipped to late January 2027.",self.pub())
        self.assertEqual(x["month"],"2027-01")
        self.assertIn("정확한 일자 확인 불가",x["label"])

    def test_launch_october_23_is_not_delivery_delay(self):
        self.assertIsNone(m._shipping_event("iPhone Duo shipping begins October 23 in the U.S.",self.pub()))

    def test_no_region_no_us_assertion(self):
        x=m._shipping_event("iPhone Duo shipping delivery now March 10, 2027.",self.pub())
        self.assertEqual(x["market"],"지역 미확인")

    def test_notebookcheck_not_good_enough(self):
        self.assertEqual(m._rank("notebookcheck.net"),0)
        self.assertEqual(m._rank("AppleInsider"),2)

    def test_same_fact_repost_suppressed(self):
        row={"title":"iPhone Duo USA delivery November 23 after preorder","description":"iPhone Duo shipping delayed to November 23 in the U.S.","source":"AppleInsider","link":"https://example.com","published_at_kst":self.pub().isoformat()}
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":["미국:2026-11","미국:2026-12","미국:2027-01"]}
        changes,_=m._new_delivery_signals([row],st)
        self.assertFalse(changes)

    def test_new_february_material_extension(self):
        row={"title":"iPhone Duo U.S. shipping delivery now February 2027","description":"iPhone Duo orders now shipping in February 2027 in the U.S.","source":"The Verge","link":"https://example.com","published_at_kst":self.pub().isoformat()}
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":[]}
        changes,_=m._new_delivery_signals([row],st)
        self.assertEqual(len(changes),1)
        self.assertEqual(st["market_latest"]["미국"],"2027-02")

    def test_single_sku_attribution_and_multiple_sku_unknown(self):
        solo=m._shipping_event(
            "iPhone Duo U.S. Star White 256GB delivery February 14, 2027.",self.pub()
        )
        self.assertEqual(solo["capacity"],"256GB")
        self.assertEqual(solo["colour"],"star white")
        mixed=m._shipping_event(
            "iPhone Duo U.S. 256GB and 512GB delivery February 14, 2027.",self.pub()
        )
        self.assertEqual(mixed["capacity"],"구성 미확인")

    def test_direct_article_reading_never_uses_google_redirect(self):
        from unittest.mock import patch
        with patch.object(m,"_request") as fake:
            self.assertEqual(m._publisher_article_text(
                "https://news.google.com/rss/articles/example","MacRumors"
            ),"")
            fake.assert_not_called()

    def test_korea_and_us_dates_not_mixed(self):
        row={"title":"아이폰 듀오 한국 배송 11월 20일","description":"아이폰 듀오 국내 신규 주문 배송은 11월 20일 예정","source":"연합뉴스","link":"https://example.com","published_at_kst":self.pub().isoformat()}
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":[]}
        changes,_=m._new_delivery_signals([row],st)
        self.assertEqual(len(changes),1)
        self.assertEqual(st["market_latest"]["한국"],"2026-11")
        self.assertEqual(st["market_latest"]["미국"],"2027-01")

    def test_preorder_sold_out_is_not_actual_volume(self):
        first=m._initial_alert()
        self.assertIn("실제 판매 대수",first)
        self.assertIn("총주문 마감 아님",first)
        self.assertIn("공식 출시일",first)

    def test_apple_msrp_and_shipping_not_confused(self):
        x=m._shipping_event("iPhone Duo U.S. costs $1999, launches October 23.",self.pub())
        self.assertIsNone(x)

if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DuoPreorderTests))
    if not result.wasSuccessful():
        sys.exit(1)

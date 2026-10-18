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

    def test_same_month_seven_day_delay_is_alertable(self):
        row={"title":"iPhone Duo U.S. Star White 256GB delivery February 18, 2027",
             "description":"Shipping delivery February 18 for U.S. iPhone Duo 256GB",
             "source":"The Verge","link":"https://example.com",
             "published_at_kst":self.pub().isoformat()}
        st={"market_latest":{"미국":"2027-02"},
            "market_sku_latest":{"미국|256GB|star white":"2027-02"},
            "market_sku_day_latest":{"미국|256GB|star white":"2027-02-09"},
            "seen_ids":[],"seen_fact_keys":[]}
        changes,_=m._new_delivery_signals([row],st)
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]["exact_date"],"2027-02-18")

    def test_same_month_four_day_shift_is_not_material(self):
        row={"title":"iPhone Duo U.S. Star White 256GB delivery February 12, 2027",
             "description":"Shipping delivery February 12 for U.S. iPhone Duo 256GB",
             "source":"The Verge","link":"https://example.com",
             "published_at_kst":self.pub().isoformat()}
        st={"market_latest":{"미국":"2027-02"},
            "market_sku_latest":{"미국|256GB|star white":"2027-02"},
            "market_sku_day_latest":{"미국|256GB|star white":"2027-02-09"},
            "seen_ids":[],"seen_fact_keys":[]}
        changes,_=m._new_delivery_signals([row],st)
        self.assertFalse(changes)

    def test_november_range_latest_day_is_23(self):
        info=m._shipping_event("iPhone Duo U.S. shipping November 16–23, 2026.",self.pub())
        self.assertEqual(info["exact_date"],"2026-11-23")

    def test_unknown_day_does_not_invent_seven_day_extension(self):
        row={"title":"iPhone Duo U.S. delivery still late January 2027",
             "description":"Shipping currently scheduled for late January 2027 in the U.S.",
             "source":"The Verge","link":"https://example.com",
             "published_at_kst":self.pub().isoformat()}
        st={"market_latest":{"미국":"2027-01"},
            "market_day_latest":{},"seen_ids":[],"seen_fact_keys":[]}
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

    def test_august_2027_misread_is_blocked(self):
        x=m._shipping_event("iPhone Duo U.S. shipping now August 2027.",self.pub())
        self.assertIsNone(x)

    def test_january_2027_delivery_still_parsed(self):
        x=m._shipping_event("iPhone Duo U.S. delivery January 25, 2027.",self.pub())
        self.assertEqual(x["exact_date"],"2027-01-25")

    def test_apple_msrp_and_shipping_not_confused(self):
        x=m._shipping_event("iPhone Duo U.S. costs $1999, launches October 23.",self.pub())
        self.assertIsNone(x)


    def test_macrumors_walkins_article_has_jan25_not_august(self):
        article = (
            "iPhone Duo U.S. sales launch October 23. Apple online store says "
            "check back on October 24 for pickup availability. In early September, "
            "Nikkei Asia said production reached a few hundred per day in late August. "
            "Delivery estimates moved beyond launch day within minutes, and within "
            "30 minutes all configurations in Apple's U.S. online store showed "
            "January 25 shipping estimates."
        )
        event=m._shipping_event(article,dt.datetime(2026,10,17,23,30,tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertIsNotNone(event)
        self.assertEqual(event["exact_date"],"2027-01-25")
        self.assertEqual(event["market"],"미국")
        self.assertEqual(event["capacity"],"구성 미확인")

    def test_late_august_production_history_without_delivery_is_not_eta(self):
        text="iPhone Duo U.S. manufacturing in late August had production issues. Shipping launch is October 23."
        self.assertIsNone(m._shipping_event(text,self.pub()))

    def test_explicit_august_2026_is_not_august_2027(self):
        text="iPhone Duo U.S. shipping in August 2026 during old tests, launching October 23."
        self.assertIsNone(m._shipping_event(text,self.pub()))

    def test_pickup_oct24_is_not_new_order_delivery_eta(self):
        text="iPhone Duo U.S. preorders. Check back on October 24 for in-store pickup availability."
        self.assertIsNone(m._shipping_event(text,self.pub()))

    def test_following_year_january_without_year_still_resolves(self):
        info=m._shipping_event("iPhone Duo U.S. delivery estimates now January 25.",self.pub())
        self.assertEqual(info["exact_date"],"2027-01-25")

    def test_fake_google_news_redirect_cannot_raise_delivery_alert(self):
        row={
            "title":"iPhone Duo U.S. shipping now February 18, 2027",
            "description":"iPhone Duo delivery estimates February 18, 2027",
            "source":"MacRumors",
            "link":"https://news.google.com/rss/articles/fake",
            "publisher_direct":False,
            "published_at_kst":self.pub().isoformat(),
        }
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":[]}
        new,_=m._new_delivery_signals([row],st)
        self.assertFalse(new)
        self.assertFalse(m._direct_publisher_link(row))

    def test_valid_direct_publisher_link_allowed(self):
        row={
            "source":"MacRumors",
            "link":"https://www.macrumors.com/2026/10/17/staff-warn-against-iphone-duo-walk-ins/"
        }
        self.assertTrue(m._direct_publisher_link(row))

    def test_wrong_august_fact_key_is_removed_even_after_prior_month_reset(self):
        val={
            "market_latest":{"미국":"2027-01"},"market_day_latest":{},
            "market_sku_latest":{},"market_sku_day_latest":{},
            "seen_fact_keys":["미국|구성 미확인|색상 미확인:2027-08","미국:2027-01"],
        }
        result=m._sanitize_delivery_state(val)
        self.assertEqual(result["seen_fact_keys"],["미국:2027-01"])

    def test_concurrent_merge_cannot_restore_false_august_delivery(self):
        remote={
            "updated_at_kst":"2026-10-18T14:45:00+09:00",
            "market_latest":{"미국":"2027-08"},
            "seen_fact_keys":["미국|구성 미확인|색상 미확인:2027-08"],
        }
        local={
            "updated_at_kst":"2026-10-18T14:43:00+09:00",
            "market_latest":{"미국":"2027-01"},
            "seen_fact_keys":["미국:2027-01"],
            "quarantined_delivery_claims":[{"market":"미국","reported_month":"2027-08","reason":"test"}],
        }
        merged=m._merge_delivery_state(remote,local)
        self.assertEqual(merged["market_latest"]["미국"],"2027-01")
        self.assertNotIn("미국|구성 미확인|색상 미확인:2027-08",merged["seen_fact_keys"])
        self.assertTrue(merged["quarantined_delivery_claims"])

    def test_unknown_region_cannot_mutate_known_us_eta(self):
        row={
            "title":"iPhone Duo shipping now February 18, 2027",
            "description":"Shipping delivery February 18, 2027",
            "source":"The Verge",
            "publisher_direct":True,
            "link":"https://www.theverge.com/news/example",
            "published_at_kst":self.pub().isoformat(),
        }
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":[]}
        changes,_=m._new_delivery_signals([row],st)
        self.assertFalse(changes)
        self.assertEqual(st["market_latest"]["미국"],"2027-01")


if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DuoPreorderTests))
    if not result.wasSuccessful():
        sys.exit(1)

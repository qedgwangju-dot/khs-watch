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



    def test_correction_notice_is_due_once_for_quarantined_false_august(self):
        st = {
            "quarantined_delivery_claims": [
                {"market":"미국","reported_month":"2027-08","reason":"unverified"}
            ],
            "false_august_correction_sent":False,
        }
        self.assertTrue(m._needs_august_correction(st))
        st["false_august_correction_sent"]=True
        self.assertFalse(m._needs_august_correction(st))
        notice=m._august_correction_alert()
        self.assertIn("2027년 1월 25일",notice)
        self.assertIn("잘못된 날짜 추출",notice)

    def test_concurrent_merge_keeps_confirmed_correction_receipt(self):
        remote={
            "updated_at_kst":"2026-10-18T15:20:00+09:00",
            "market_latest":{"미국":"2027-01"},
            "false_august_correction_sent":True,
        }
        local={
            "updated_at_kst":"2026-10-18T15:22:00+09:00",
            "market_latest":{"미국":"2027-01"},
            "false_august_correction_sent":False,
        }
        merged=m._merge_delivery_state(remote,local)
        self.assertTrue(merged["false_august_correction_sent"])



    def test_oct19_improved_delivery_is_not_labeled_added_delay(self):
        row={
            "title":"Apple Starts Moving Up iPhone Duo Delivery Dates",
            "description":(
                "iPhone Duo U.S. Star White 512GB delivery estimate was December. "
                "The preordered device now arrives November 20 to November 30, 2026. "
                "Other U.S. customers shifted from December 1–8 to November 16–23."
            ),
            "source":"MacRumors",
            "link":"https://www.macrumors.com/2026/10/19/apple-starts-moving-up-iphone-duo-delivery-dates/",
            "publisher_direct":True,
            "published_at_kst":"2026-10-20T04:31:00+09:00",
        }
        state={"market_latest":{"미국":"2027-01"},"market_day_latest":{},
               "market_sku_latest":{},"market_sku_day_latest":{},
               "seen_ids":[],"seen_fact_keys":[]}
        changes,_=m._new_delivery_signals([row],state)
        self.assertFalse(changes)
        self.assertEqual(state["market_latest"]["미국"],"2027-01")

    def test_walkins_article_past_august_and_oct24_cannot_extend_to_aug2027(self):
        row={
            "title":"Apple Retail Staff Told to Warn Against iPhone Duo Walk-In Purchases",
            "description":(
                "Apple staff warns about October 23 launch day walk-ins and "
                "October 24 pickup availability. In late August production was a "
                "few hundred per day. Within 30 minutes the U.S. online store "
                "showed January 25 shipping estimates for iPhone Duo."
            ),
            "source":"MacRumors",
            "publisher_direct":True,
            "link":"https://www.macrumors.com/2026/10/17/staff-warn-against-iphone-duo-walk-ins/",
            "published_at_kst":"2026-10-18T06:30:45+09:00",
        }
        state={"market_latest":{"미국":"2027-01"},"market_day_latest":{},
               "market_sku_latest":{},"market_sku_day_latest":{},
               "seen_ids":[],"seen_fact_keys":[]}
        changes,_=m._new_delivery_signals([row],state)
        self.assertFalse(changes)

    def test_same_macrumors_january25_article_after_correction_does_not_repeat(self):
        row={
            "title":"Apple Retail Staff Told to Warn Against iPhone Duo Walk-In Purchases",
            "description":(
                "iPhone Duo U.S. check back October 24 for pickup. "
                "Last August production was very low. Within 30 minutes "
                "all configurations in the U.S. store showed January 25 shipping estimates."
            ),
            "source":"MacRumors",
            "link":"https://www.macrumors.com/2026/10/17/staff-warn-against-iphone-duo-walk-ins/",
            "publisher_direct":True,
            "published_at_kst":"2026-10-18T06:30:45+09:00",
        }
        state={
            "initial_alert_sent":True,
            "false_august_correction_sent":True,
            "market_latest":{"미국":"2027-01"},
            "market_day_latest":{},
            "seen_ids":[],"seen_fact_keys":["미국:2027-01"],
        }
        changes,_=m._new_delivery_signals([row],state)
        self.assertEqual(changes,[])
        self.assertEqual(state["market_latest"]["미국"],"2027-01")
        self.assertFalse(m._needs_august_correction(state))


    def test_existing_preorder_advances_are_distinct_from_new_order_delay(self):
        row={
            "title":"Apple Starts Moving Up iPhone Duo Delivery Dates",
            "description":(
                "In the U.S., a customer said his iPhone Duo pre-order initially "
                "showed a December delivery estimate, but the store now shows an "
                "earlier delivery estimate of between November 20 and November 30. "
                "In Japan, a customer says an iPhone Duo is now estimated to be "
                "delivered on October 24. The original delivery estimate was "
                "December 3 to December 10."
            ),
            "source":"MacRumors",
            "link":"https://www.macrumors.com/2026/10/19/apple-starts-moving-up-iphone-duo-delivery-dates/",
            "publisher_direct":True,
            "published_at_kst":"2026-10-20T04:31:00+09:00",
        }
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":[]}
        changes=m._new_preorder_improvements([row],st)
        self.assertEqual({x["market"] for x in changes},{"미국","일본"})
        self.assertEqual(m._new_preorder_improvements([row],st),[])
        delays,_=m._new_delivery_signals([row],st)
        self.assertEqual(delays,[])
        self.assertEqual(st["market_latest"]["미국"],"2027-01")

    def test_advance_requires_direct_source_and_two_date_estimates(self):
        row={"title":"Apple Starts Moving Up iPhone Duo Delivery Dates",
             "description":"In the U.S., a pre-order is now arriving November 20.",
             "source":"MacRumors","publisher_direct":True,
             "link":"https://www.macrumors.com/2026/10/19/apple-starts-moving-up-iphone-duo-delivery-dates/",
             "published_at_kst":"2026-10-20T04:31:00+09:00"}
        self.assertEqual(m._new_preorder_improvements([row],{}),[])
        row["description"]=(
            "In the U.S., initial December 1 to December 8 delivery "
            "estimate; now seeing November 16 to November 23."
        )
        row["publisher_direct"]=False
        self.assertEqual(m._new_preorder_improvements([row],{}),[])
        row["publisher_direct"]=True
        changes=m._new_preorder_improvements([row],{})
        self.assertEqual(len(changes),1)
        self.assertIn("12월 1~8일",changes[0]["old"])
        self.assertIn("11월 16~23일",changes[0]["new"])

    def test_advance_state_receipts_union_across_concurrent_runs(self):
        r={"updated_at_kst":"2026-10-23T12:00:00+09:00",
           "seen_improvement_fact_keys":["advance:미국:A->B"]}
        l={"updated_at_kst":"2026-10-23T12:01:00+09:00",
           "seen_improvement_fact_keys":["advance:일본:C->D"]}
        merged=m._merge_delivery_state(r,l)
        self.assertEqual(len(merged["seen_improvement_fact_keys"]),2)


    def test_future_eta_requires_two_independent_direct_sources(self):
        title="iPhone Duo U.S. new online orders shipping August 15, 2027."
        a={"title":title,"description":"new online orders shipping August 15, 2027.",
           "source":"MacRumors","publisher_direct":True,
           "link":"https://www.macrumors.com/2026/10/24/future/",
           "published_at_kst":"2026-10-24T00:30:00+09:00"}
        b=dict(a,source="The Verge",link="https://www.theverge.com/tech/future")
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":[]}
        single,_=m._new_delivery_signals([a],st)
        self.assertEqual(single,[])
        self.assertEqual(st["market_latest"]["미국"],"2027-01")
        st={"market_latest":{"미국":"2027-01"},"seen_ids":[],"seen_fact_keys":[]}
        two,_=m._new_delivery_signals([a,b],st)
        self.assertEqual(len(two),1)
        self.assertEqual(st["market_latest"]["미국"],"2027-08")
        self.assertIn("미국:2027-08",st["verified_extended_months"])
        m._sanitize_delivery_state(st)
        self.assertEqual(st["market_latest"]["미국"],"2027-08")

    def test_prior_august_misread_stays_quarantined(self):
        st={"market_latest":{"미국":"2027-08"},
            "seen_fact_keys":["미국:2027-08"],"quarantined_delivery_claims":[]}
        m._sanitize_delivery_state(st)
        self.assertEqual(st["market_latest"]["미국"],"2027-01")
        self.assertTrue(st["quarantined_delivery_claims"])

    def test_future_evidence_survives_concurrent_state_merge(self):
        old={"updated_at_kst":"2026-10-24T00:30:00+09:00",
             "verified_extended_months":["미국:2027-08"]}
        new={"updated_at_kst":"2026-10-24T00:31:00+09:00",
             "verified_extended_months":[]}
        self.assertIn("미국:2027-08",m._merge_delivery_state(old,new)["verified_extended_months"])


    def test_historical_improvement_recovery_requires_direct_publisher_article(self):
        from unittest.mock import patch
        direct=(
            "In the U.S., a customer's iPhone Duo pre-order initially showed "
            "December delivery, but the store now shows November 20 to November 30. "
            "In Japan, original December 3 to December 10 delivery is now October 24."
        )
        with patch.object(m, "_publisher_article_text", side_effect=lambda url,source: direct if source=="MacRumors" else "") as original:
            rows=m._recover_verified_oct19_advance([], [])
        original.assert_any_call(m.OCT19_IMPROVEMENT,"MacRumors")
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["publisher_direct"])
        self.assertTrue(rows[0]["historical_recovery"])
        self.assertEqual(rows[0]["link"],m.OCT19_IMPROVEMENT)
        changes=m._new_preorder_improvements(rows,{})
        self.assertGreaterEqual(len(changes),1)
        self.assertIn("2026년 10월 19일 기보도",m._preorder_improvement_alert(changes))

    def test_historical_improvement_recovery_fails_closed_when_unreadable(self):
        from unittest.mock import patch
        errors=[]
        with patch.object(m,"_publisher_article_text",return_value=""):
            rows=m._recover_verified_oct19_advance([],errors)
        self.assertEqual(rows,[])
        self.assertEqual(len(errors),1)


    def test_launch_day_delivery_is_valid_only_for_existing_preorder_advances(self):
        pub=self.pub()
        self.assertIsNone(m._month_and_day("October 23, 2026",pub))
        self.assertEqual(m._month_and_day("October 23, 2026",pub,allow_launch=True)[2],
                         "2026-10-23")
        row={
            "title":"Some iPhone Duo orders getting moved up to earlier dates",
            "description":"In Japan, original delivery December 3 to December 10. Now delivery October 23, 2026.",
            "source":"9to5Mac","publisher_direct":True,
            "link":"https://9to5mac.com/2026/10/19/some-iphone-duo-orders-getting-moved-up-to-earlier-dates/",
            "published_at_kst":"2026-10-20T04:31:00+09:00",
        }
        changes=m._new_preorder_improvements([row],{})
        self.assertEqual(len(changes),1)
        self.assertIn("10월 23일",changes[0]["new"])

    def test_9to5mac_first_party_articles_are_not_google_redirects(self):
        self.assertTrue(m._direct_publisher_link({
            "source":"9to5Mac",
            "link":"https://9to5mac.com/2026/10/19/some-iphone-duo-orders-getting-moved-up-to-earlier-dates/",
        }))
        self.assertFalse(m._direct_publisher_link({
            "source":"9to5Mac","link":"https://news.google.com/rss/articles/example",
        }))


if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DuoPreorderTests))
    if not result.wasSuccessful():
        sys.exit(1)

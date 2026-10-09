"""Regression tests for Rebellions Telegram partner watcher event deduplication."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from scripts.rebellions_partner_watch import (
    capital_event_kind,
    classify,
    domestic_candidate,
    event_signature,
    find_duplicate_event,
    material_stage,
    norm_title,
)


class RebellionsWatcherRegressionTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 9, 17, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    def prior(self, title, url="https://publisher.example/a", stage=None, stored_signature=None):
        return {
            "title": title,
            "url": url,
            "first_seen_kst": self.now.isoformat(timespec="seconds"),
            "material_stage": material_stage(title) if stage is None else stage,
            "event_signature": stored_signature or event_signature(title),
            "alerted": True,
        }

    def item(self, title, url="https://publisher.example/b"):
        return {"title": title, "url": url, "summary": ""}

    def test_kepco_mou_and_same_day_poc_are_one_event(self):
        a = "한전, 리벨리온·TTA와 국산 NPU 기반 AI 영상분석 협력 - 뉴스락"
        b = "한전 변전소 AI 관제에 국산 NPU 투입...리벨리온 현장 실증 - zdnet.co.kr"
        self.assertEqual(event_signature(a), event_signature(b))
        self.assertEqual(event_signature(a), "kepco|npu|power_video")
        self.assertTrue(find_duplicate_event(self.item(b), {"a": self.prior(a)}, self.now).startswith("same_event:"))

    def test_cck_existing_mou_is_not_new_equity_investment(self):
        mou = "리벨리온, CCK솔루션과 국산 NPU 협력 업무협약"
        investment = "리벨리온, CCK솔루션에 전략적 투자 참여 - 머니투데이"
        self.assertNotEqual(event_signature(mou), event_signature(investment))
        self.assertEqual(event_signature(investment), "cck|capital|equity")
        self.assertEqual(material_stage(investment), 5)
        self.assertEqual(classify(investment), "투자·지분")
        self.assertIsNone(find_duplicate_event(self.item(investment), {"mou": self.prior(mou)}, self.now))

    def test_different_outlet_same_new_investment_is_suppressed(self):
        first = "리벨리온, CCK솔루션에 전략적 투자 참여 - 머니투데이"
        second = "CCK솔루션, 리벨리온 투자 유치…국산 AI 풀스택 강화 - 이데일리"
        old = self.prior(first, stored_signature="cck|general|general", stage=0)
        self.assertEqual(event_signature(second), "cck|capital|equity")
        self.assertEqual(find_duplicate_event(self.item(second), {"first": old}, self.now), "same_event:cck|capital|equity")

    def test_identical_google_news_link_different_publisher_names(self):
        same_url = "https://news.google.com/rss/articles/example-id?oc=5"
        a = "리벨리온, CCK솔루션에 전략적 투자 참여 - 머니투데이"
        b = "리벨리온, CCK솔루션에 전략적 투자 참여 - mt.co.kr"
        self.assertEqual(norm_title(a), norm_title(b))
        self.assertEqual(find_duplicate_event(self.item(b, same_url), {"a": self.prior(a, same_url)}, self.now), "same_url")

    def test_stale_duplicate_older_than_14_days_does_not_block_new_event(self):
        title = "리벨리온, CCK솔루션에 전략적 투자 참여"
        entry = self.prior(title)
        entry["first_seen_kst"] = (self.now - dt.timedelta(days=15)).isoformat()
        different = "CCK솔루션, 리벨리온 투자 유치 완료"
        self.assertIsNone(find_duplicate_event(self.item(different), {"a": entry}, self.now))

    def test_investment_proposal_is_not_alertable(self):
        title = "리벨리온, CCK솔루션 전략적 투자 추진"
        self.assertFalse(domestic_candidate(title))
        self.assertIsNone(capital_event_kind(title))

    def test_second_equity_round_is_distinct(self):
        first = "리벨리온, CCK솔루션에 전략적 투자 참여"
        follow_on = "리벨리온, CCK솔루션에 후속 투자 단행"
        self.assertNotEqual(event_signature(first), event_signature(follow_on))
        self.assertIsNone(find_duplicate_event(self.item(follow_on), {"first": self.prior(first)}, self.now))


if __name__ == "__main__":
    unittest.main()

"""Regression suite: NVIDIA startup roundtables vs actual commercial events."""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo
import scripts.nvidia_kstartup_global_watch as m


class NvidiaKoreaStartupTests(unittest.TestCase):
    def item(self, title, url="https://news.google.com/rss/articles/sample", *, tier="신뢰보도", time="2026-11-05T18:00+09:00"):
        obj = {"title": title, "url": url, "source": "한국경제",
               "source_url": "https://www.hankyung.com", "summary": "",
               "tier": tier, "published_kst": time}
        kind, stage, label = m.classify(title, tier)
        obj.update(kind=kind, stage=stage, label=label, event_id=m.event_id(obj))
        return obj

    def test_user_article_is_reported_meeting_not_contract(self):
        self.assertTrue(m.is_relevant(m.USER_HEADLINE))
        kind, stage, _ = m.classify(m.USER_HEADLINE)
        self.assertEqual((kind, stage), ("meeting", 1))
        self.assertEqual(m.event_id(self.item(m.USER_HEADLINE)), "nvidia_korea|meeting|2026-11")

    def test_baseline_contains_june_aug_nov_and_nvidia_ai_day(self):
        self.assertIn("nvidia_korea|meeting|2026-06", m.SEED_EVENTS)
        self.assertIn("rebellions|deal_talk|2026-08", m.SEED_EVENTS)
        self.assertIn("nvidia_korea|meeting|2026-11", m.SEED_EVENTS)
        self.assertIn("nvidia_korea|ai_day_schedule|2026-11", m.SEED_EVENTS)

    def test_official_ai_day_not_confirmed_rebellions_participant(self):
        seed = m.SEED_EVENTS["nvidia_korea|ai_day_schedule|2026-11"]
        self.assertEqual(seed["stage"], 1)
        self.assertIn("미확정", seed["evidence"])

    def test_meeting_attendance_news_not_investment(self):
        title = "리벨리온, 엔비디아 간담회 참석…해외 진출 논의"
        kind, stage, _ = m.classify(title)
        self.assertEqual((kind, stage), ("meeting_reported", 2))
        self.assertNotEqual(kind, "capital_signed")

    def test_official_meeting_confirmed_is_distinct_upgrade(self):
        title = "NVIDIA, 한국 리벨리온 간담회 참석 공식 발표"
        report = self.item(title)
        report["tier"] = "공식"
        report["event_id"], report["stage"], report["label"] = (*m.classify(title, "공식"),)
        self.assertEqual((report["kind"] if "kind" in report else "unused"), "meeting_reported")
        self.assertEqual((report["event_id"], report["stage"]),
                         ("nvidia_korea|meeting_confirmed|2026-11", 2))

    def test_investment_talk_not_signed_deal(self):
        kind, stage, _ = m.classify("엔비디아, 리벨리온 투자 인수 논의")
        self.assertNotEqual(kind, "capital_signed")
        self.assertLess(stage, 6)

    def test_signed_investment_is_stage_six(self):
        kind, stage, _ = m.classify("엔비디아 리벨리온 지분 투자 확정")
        self.assertEqual((kind, stage), ("capital_signed", 6))

    def test_global_customer_requires_explicit_contract(self):
        self.assertNotEqual(m.classify("리벨리온, 엔비디아 통해 미국 고객 진출 기대")[0], "global_customer")
        self.assertEqual(m.classify("엔비디아 협력 리벨리온 미국 고객 납품")[0], "global_customer")

    def test_signed_mou_requires_completed_language(self):
        self.assertNotEqual(m.classify("리벨리온 엔비디아 업무협약 추진")[0], "partnership_signed")
        self.assertEqual(m.classify("리벨리온 엔비디아 업무협약 체결")[0], "partnership_signed")

    def test_other_nvidia_product_announcement_is_filtered(self):
        self.assertFalse(m.is_relevant("엔비디아 신형 GPU 출하량 2배 증가"))

    def test_june_and_november_meetings_are_separate(self):
        june = self.item("젠슨 황 국내 AI 스타트업 간담회", time="2026-06-08T20:00+09:00")
        november = self.item("엔비디아 국내 AI 스타트업 간담회", time="2026-11-05T18:00+09:00")
        self.assertNotEqual(m.event_id(june), m.event_id(november))

    def test_google_news_url_tracking_ignores_query_suffix(self):
        a = self.item("리벨리온 엔비디아 간담회", url="https://news.google.com/rss/articles/abc?oc=5")
        b = self.item("리벨리온 엔비디아 간담회", url="https://news.google.com/rss/articles/abc?oc=7")
        self.assertEqual(m.article_key(a), m.article_key(b))

    def test_unknown_source_is_not_official(self):
        self.assertEqual(m.source_tier("한국경제", "https://www.hankyung.com"), "신뢰보도")
        self.assertEqual(m.source_tier("NVIDIA", "https://blogs.nvidia.co.kr"), "공식")
        self.assertEqual(m.source_tier("unknown blogger", "https://spam.example"), "기타")

    def test_corrupted_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"state.json"
            p.write_text("{broken", encoding="utf-8")
            with mock.patch.object(m, "STATE", p):
                with self.assertRaises(RuntimeError):
                    m.read_state()

    def test_end_to_end_baseline_suppresses_existing_meeting_and_new_signed_deal_alerts_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)
            t1=dt.datetime(2026,11,5,18,10,tzinfo=ZoneInfo("Asia/Seoul"))
            t2=dt.datetime(2026,11,6,10,10,tzinfo=ZoneInfo("Asia/Seoul"))
            t3=dt.datetime(2026,11,6,10,25,tzinfo=ZoneInfo("Asia/Seoul"))
            meeting=self.item(m.USER_HEADLINE,url="https://news.google.com/rss/articles/nov5",
                              time="2026-11-05T17:00+09:00")
            signed=self.item("리벨리온 엔비디아 기술제휴 계약 체결",
                             url="https://news.google.com/rss/articles/deal1",
                             time="2026-11-06T09:00+09:00")
            duplicate=self.item("엔비디아 리벨리온 기술제휴 계약 체결 - 뉴스핌",
                                url="https://news.google.com/rss/articles/deal2",
                                time="2026-11-06T09:10+09:00")
            health={"rss_ok":14,"rss_total":14,"official_ok":2,"errors":[]}
            with contextlib.ExitStack() as stack:
                for nm,path in (("STATE",p/"state.json"),("PENDING",p/"pending.json"),
                                ("ALERT",p/"alert.html"),("STATUS",p/"status.md")):
                    stack.enter_context(mock.patch.object(m,nm,path))
                stack.enter_context(mock.patch.object(m,"now_kst",side_effect=[t1,t2,t3]))
                stack.enter_context(mock.patch.object(m,"collect",side_effect=[
                    ([meeting],health),([meeting,signed,duplicate],health),([meeting,signed,duplicate],health)
                ]))
                stack.enter_context(mock.patch.object(m,"direct_url",
                                                     side_effect=lambda url: (url,"기사 보기(구글뉴스 경유)")))
                m.main()
                self.assertFalse(m.ALERT.exists())
                first=json.loads(m.PENDING.read_text(encoding="utf-8"))
                self.assertTrue(first["initialized"])
                self.assertTrue(first["events"]["nvidia_korea|meeting|2026-11"]["baseline"])
                m.STATE.write_bytes(m.PENDING.read_bytes())
                m.main()
                msg=m.ALERT.read_text(encoding="utf-8")
                self.assertIn("신규 사건 1건",msg)
                self.assertIn("계약 체결",msg)
                data=json.loads(m.PENDING.read_text(encoding="utf-8"))
                self.assertEqual(len([x for x in data["seen"].values() if x.get("alerted")]),1)
                self.assertEqual(len([x for x in data["seen"].values() if x.get("suppressed_duplicate")]),1)
                m.STATE.write_bytes(m.PENDING.read_bytes())
                m.main()
                self.assertFalse(m.ALERT.exists())

    def test_new_official_attendance_can_be_reported_separately_from_unverified_meeting(self):
        a=self.item("NVIDIA, 한국 리벨리온 간담회 참석 공식 확인",tier="공식")
        self.assertEqual(a["event_id"],"nvidia_korea|meeting_confirmed|2026-11")
        self.assertNotEqual(a["event_id"],"nvidia_korea|meeting|2026-11")

    def test_multiple_publisher_headlines_cluster_in_one_roundtable(self):
        a=self.item("[단독] 리벨리온 등 엔비디아와 간담회…AI 스타트업 해외진출 길 열리나",
                    time="2026-11-05T17:15+09:00")
        b=self.item("엔비디아 한국 AI 스타트업과 간담회…해외 진출 기대",
                    time="2026-11-05T20:15+09:00")
        self.assertEqual(a["event_id"],b["event_id"])


if __name__ == "__main__":
    unittest.main()

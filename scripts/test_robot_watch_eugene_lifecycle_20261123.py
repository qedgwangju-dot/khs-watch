#!/usr/bin/env python3
"""Scoped Eugene humanoid lifecycle alert, source grading, and anti-replay tests."""
from __future__ import annotations
import datetime as dt
import hashlib
import unittest
from types import SimpleNamespace
import robot_watch_eugene_lifecycle_20261123 as ex

class EugeneLensTest(unittest.TestCase):
    def setUp(self):
        self.legacy_queries=["existing_unchanged"]
        self.oldkey=lambda i: hashlib.sha256((str(i.get("title"))+"|"+str(i.get("source"))).encode()).hexdigest()
        self.base=SimpleNamespace(
            NOW=dt.datetime(2026,11,23,12,1,tzinfo=dt.timezone.utc),
            QUERIES=self.legacy_queries[:],
            query_news=lambda q:[],
            topic_group=lambda t:None,
            score=lambda i:7,
            key=self.oldkey,
            category=lambda t,g:"legacy category",
            meaning=lambda c:"legacy meaning",
            risk=lambda c:"legacy risk",
            verification=lambda item,group,text:"legacy verification",
            tag_for=lambda group:"legacy tag",
        )
        ex.install(self.base)

    def test_report_once_no_numeric_conversion_to_market_data(self):
        rows=self.base.query_news(ex.BACKFILL)
        self.assertEqual(len(rows),1)
        x=rows[0]
        self.assertEqual(self.base.key(x),ex.REPORT_KEY)
        self.assertEqual(self.base.score(x),46)
        self.assertEqual(self.base.topic_group(x["title"]+" "+x["description"]),ex.GROUP)
        self.assertIn("정성적 선호도",x["description"])
        self.assertIn("누적 설치 대수",x["description"])
        self.assertIn("2030년 약 13만대",x["description"])
        self.assertIn("2040년 787만대",x["description"])
        self.assertIn("2040년 서비스 매출",x["description"])
        cat=self.base.category(x["title"],ex.GROUP)
        self.assertIn("선호도 전망",cat)
        self.assertIn("확정",self.base.risk(cat))
        self.assertIn("원보고서 PDF 전체 본문",self.base.verification(x,ex.GROUP,""))
        self.assertNotIn("계약 확정",self.base.meaning(cat))

    def test_stale_report_expires_and_reprints_stay_seen(self):
        a={"title":"유진투자증권, 휴머노이드 2040년 787만대 전망",
           "description":"2030년 약 13만대", "source":"로봇신문",
           "published":"2026-11-23T12:00:00+09:00"}
        self.assertEqual(self.base.key(a),ex.REPORT_KEY)
        self.assertEqual(self.base.score(a),0)
        revised=dict(a,title="유진투자증권, 2040년 787만대 전망 상향",
                     published="2026-12-01T12:00:00+09:00")
        self.assertNotEqual(self.base.key(revised),ex.REPORT_KEY)
        self.base.NOW=dt.datetime(2026,11,28,0,0,tzinfo=ex.KST)
        self.assertEqual(self.base.query_news(ex.BACKFILL),[])
        self.assertEqual(self.base.score({"eugene_lifecycle_report":True}),0)

    def test_existing_lanes_keep_same_id_and_score(self):
        x={"title":"Samsung Semiconductor 3Q earnings", "source":"official",
           "description":"company numbers"}
        self.assertEqual(self.base.key(x),self.oldkey(x))
        self.assertEqual(self.base.score(x),7)
        self.assertEqual(self.base.topic_group("general nonrobot query"),None)
        self.assertEqual(self.base.category("a","b"),"legacy category")
        self.assertEqual(self.base.verification(x,"legacy",""),"legacy verification")
        self.assertEqual(self.base.QUERIES[0],"existing_unchanged")
        self.assertEqual(len(self.base.QUERIES),4)
        old=self.base.score
        ex.install(self.base)
        self.assertIs(old,self.base.score)
        self.assertEqual(len(self.base.QUERIES),4)

    def test_lifecycle_is_not_calendar_based_contract(self):
        self.assertIn("시제품",ex.lifecycle_lens("로보티즈 개발용 로봇 시제품 수요"))
        self.assertIn("병목 부품",ex.lifecycle_lens("로보티즈 로봇손 촉각 센서"))
        self.assertIn("현장 운영",ex.lifecycle_lens("휴머노이드 현장 운영 계약 체결"))
        self.assertIn("계획",ex.lifecycle_lens("휴머노이드 현장 운영 계약 추진"))
        self.assertIn("미체결",ex.lifecycle_lens("휴머노이드 운영 계약 미체결"))
        self.assertEqual(ex.lifecycle_lens("반도체 고대역폭 메모리 호조"),"")

    def test_official_source_title_is_only_discovery_stage(self):
        official={
            "title":"삼성SDS, 휴머노이드 로봇 시스템통합 본계약 체결",
            "description":"고객 현장 구축 및 설치",
            "source":"삼성SDS",
            "source_url":"https://www.samsungsds.com/kr/news/",
            "published":"2026-11-24T09:00:00+09:00",
        }
        self.assertEqual(self.base.topic_group(" ".join([official["title"],official["description"],official["source"]])),ex.SI_GROUP)
        self.assertEqual(ex._official_si(official),"integration_installation_contract")
        self.assertEqual(self.base.score(official),36)
        self.assertNotEqual(self.base.key(official),ex.REPORT_KEY)
        self.assertIn("원문",self.base.verification(official,ex.SI_GROUP,official["title"]))
        for source,url in [("경제신문","https://news.example.com"),("삼성SDS","https://fake-samsungsds.com")]:
            row=dict(official,source=source,source_url=url)
            self.assertEqual(ex._official_si(row),"")
            self.assertEqual(self.base.score(row),0)
        for title in [
            "삼성SDS, 휴머노이드 로봇 시스템통합 계약 추진",
            "삼성SDS, 휴머노이드 로봇 시스템통합 계약 미체결",
            "삼성SDS, 휴머노이드 로봇 시스템통합 업무협약",
        ]:
            row=dict(official,title=title)
            self.assertEqual(ex._official_si(row),"")
            self.assertEqual(self.base.score(row),0)
        previous=dict(official,published="2026-11-16T00:00:00+09:00")
        self.assertEqual(ex._official_si(previous),"")
        self.assertEqual(self.base.score(previous),0)

if __name__=="__main__":
    unittest.main()

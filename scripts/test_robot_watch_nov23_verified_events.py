"""Only-this-watch offline regressions for Nov23 reviewed events and receipt-key aliases."""
from __future__ import annotations
import datetime as dt
import hashlib
from types import SimpleNamespace
import unittest

import robot_watch_nov23_verified_events as fix

class ScopeTest(unittest.TestCase):
    def setUp(self):
        self.original_seen=[fix.POLLEN_DELIVERED,fix.GF_DELIVERED,fix.JSLINK_EXISTING]
        def upstream(row):
            return hashlib.sha256((str(row.get("title"))+"|"+str(row.get("source"))).encode()).hexdigest()
        self.upstream=upstream
        self.base=SimpleNamespace(
            NOW=dt.datetime(2026,11,23,2,55,tzinfo=dt.timezone.utc),
            QUERIES=["original preserved"],
            load_state=lambda:{"seen":self.original_seen.copy()},
            query_news=lambda q:[],
            topic_group=lambda text:None,
            key=upstream,
            score=lambda item:10,
            category=lambda text,g:"upstream",
            meaning=lambda cat:"upstream",
            risk=lambda cat:"upstream",
            verification=lambda item,g,t:"upstream",
            tag_for=lambda g:"upstream",
            clean_title=lambda title,source:title,
        )
        self.before=self.base.__dict__.copy()
        fix.install(self.base)

    def test_pinned_six_represent_distinct_events_with_existing_seen_mou(self):
        rows=self.base.query_news(fix.SENTINEL)
        self.assertEqual(len(rows),6)
        self.assertEqual(len({self.base.key(row) for row in rows}),6)
        self.assertEqual(set(r["nov23_event"] for r in rows),set(fix.STORIES))
        self.assertEqual(len([r for r in rows if self.base.key(r) not in self.original_seen]),5)
        mou=next(r for r in rows if r["nov23_event"]=="jslink_mou")
        self.assertEqual(self.base.key(mou),fix.JSLINK_EXISTING)
        h=next(r for r in rows if r["nov23_event"]=="hurim_contract")
        self.assertIn("3사 본계약",self.base.category(h["title"],self.base.topic_group(h["title"])))
        self.assertIn("직접 구매계약",self.base.risk("로봇 후속 확인 · 3사 본계약"))
        self.assertIn("급여",self.base.meaning("로봇 후속 확인 · 투자 검토·유동성 위험"))
        self.assertTrue(all(self.base.score(r)>=40 for r in rows))

    def test_pollen_reprints_fold_to_one_previously_delivered_key(self):
        rows=[
            "로보티즈, 39.8억 규모 공급계약 체결 - 이데일리",
            "로보티즈, 프랑스 Pollen Robotics와 39억7813만원 규모 DYNAMIXEL-X 공급계약 - 디지털투데이",
            "로보티즈, 폴렌로보틱스와 40억원 부품 공급계약 - 이데일리",
            "로보티즈, 39억원 규모 DYNAMIXEL-X 공급계약 - 데이터투자",
            "로보티즈 수주 39억7812만원, 매출 대비 10.22% - 데일리인베스트",
        ]
        for title in rows:
            with self.subTest(title=title):
                item={"title":title,"source":"뉴스","published":"2026-11-20T10:00:00+09:00"}
                self.assertEqual(self.base.key(item),fix.POLLEN_DELIVERED)
        self.assertIn(fix.POLLEN_DELIVERED,self.original_seen)

    def test_material_followup_is_not_hidden_by_reprint_alias(self):
        ordinary={"title":"로보티즈, 폴렌로보틱스와 40억원 부품 공급계약 - 이데일리",
                  "source":"이데일리","published":"2026-11-20T10:00:00+09:00"}
        for desc in ["추가 수주 계약을 체결했다.","초도 출하 완료를 발표했다.","계약 변경으로 60억원으로 증액했다.",
                     "신규 고객은 A기업이다."]:
            with self.subTest(description=desc):
                changed=dict(ordinary,description=desc)
                self.assertEqual(self.base.key(changed),self.upstream(changed))
        for title in ["한국피아이엠 휴머노이드 공급 계약","로보티즈, 북미 신규 고객 39억원 신규 계약"]:
            ordinary=dict(ordinary,title=title)
            self.assertEqual(self.base.key(ordinary),self.upstream(ordinary))

    def test_atlas_reprint_keeps_old_verified_key_but_completed_trial_is_new(self):
        for title in [
            "현대차 아틀라스, 자동차 밖 첫 시험대는 ‘美 반도체 공장’",
            "현대차그룹 휴머노이드 ‘아틀라스’, 내년부터 반도체 공장 첫 투입",
            "보스턴다이내믹스·GlobalFoundries, 4개 팹 Spot 확대·2027년 초 Atlas 시험 계획",
        ]:
            self.assertEqual(self.base.key({"title":title,"source":"기사","published":"2026-11-20T12:00:00+09:00"}),fix.GF_DELIVERED)
        changed={"title":"Boston Dynamics Atlas, GlobalFoundries first completed field trial",
                 "description":"현장 시험 완료","source":"공식","published":"2026-11-23T12:00:00+09:00"}
        self.assertEqual(self.base.key(changed),self.upstream(changed))

    def test_dates_and_old_methods_and_no_unrelated_edits(self):
        date_mismatch={"title":"로보티즈, 폴렌로보틱스와 40억원 부품 공급계약",
                       "published":"2026-12-20T12:00:00+09:00","source":"뉴스"}
        self.assertEqual(self.base.key(date_mismatch),self.upstream(date_mismatch))
        self.assertEqual(self.base.QUERIES,["original preserved",fix.SENTINEL])
        self.assertEqual(self.base.query_news("original preserved"),[])
        self.assertEqual(self.base.category("unknown","unknown"),"upstream")
        for k in ("load_state","NOW"):
            self.assertIs(getattr(self.base,k),self.before[k])
        original=self.base.key
        fix.install(self.base)
        self.assertIs(self.base.key,original)
        self.assertEqual(len(self.base.QUERIES),2)
        self.base.NOW=dt.datetime(2026,12,1,tzinfo=dt.timezone.utc)
        self.assertEqual(self.base.query_news(fix.SENTINEL),[])
        self.assertEqual(self.base.score({"nov23_event":"hurim_contract"}),0)

if __name__=="__main__": unittest.main()

#!/usr/bin/env python3
"""Offline no-send regression for 2026-10/11 robot source corrections.

Only synthetic input data, no RSS, DART, Telegram, or state writes.
"""
from __future__ import annotations

import datetime as dt

import physical_ai_watch_airan_guard as watcher
import robot_watch_nov02_stage_lanes as update

base=watcher.base

def sample(title,body,source="일반언론",published="2026-11-02T00:00:00+00:00"):
    return {"title":title,"description":body,"source":source,
            "published":published,"link":"https://example.invalid/test"}

def classify(x):
    t=" ".join(str(x.get(k) or "") for k in ("title","description","source"))
    g=base.topic_group(t)
    return g,base.score(x),base.key(x),base.category(t,g)

def run():
    oldnow=base.NOW
    oldload=base.load_state
    expected=set(v["group"] for v in update.EVENTS.values())
    assert len(expected)==len(update.EVENTS)
    try:
        base.NOW=dt.datetime(2026,11,2,0,0,tzinfo=dt.timezone.utc)
        base.load_state=lambda:{"seeded":True,"seen":[update.OLD_WRONG_MICRODUCK_KEY]}
        all_keys=set()
        for name,item in update.EVENTS.items():
            rows=base.query_news("DIRECT_ROBOT_NOV02_"+name)
            assert len(rows)==1,(name,rows)
            g,s,k,c=classify(rows[0])
            assert g==item["group"],(name,g,item["group"])
            assert s>=11 and len(k)==64 and k not in all_keys,(name,s,k)
            assert c==item["category"],(name,c,item["category"])
            assert base.meaning(c) and base.risk(c)
            all_keys.add(k)
        assert len(all_keys)==len(update.EVENTS)
        assert update.OLD_WRONG_MICRODUCK_KEY not in all_keys

        # The company-issued Oct28 denial is a genuine separate event, not
        # a stale Oct26 procurement agreement. Do not rewrite prior seen keys.
        old_claim=dict(watcher.MICRODUCK_OCT26_EVENT,
                       microduck_oct26_verified=True,published=None)
        assert base.score(old_claim)==0, "Known-false contract cannot be re-alerted"
        assert watcher._md_key(old_claim)==update.OLD_WRONG_MICRODUCK_KEY

        base.load_state=lambda:{"seeded":True,"seen":[]}
        assert base.query_news("DIRECT_ROBOT_NOV02_microduck_official_correction")==[],(
            "No retroactive correction if the old false alert is absent"
        )
        base.load_state=lambda:{"seeded":True,"seen":[update.OLD_WRONG_MICRODUCK_KEY]}

        base.NOW=dt.datetime(2026,11,7,0,0,tzinfo=dt.timezone.utc)
        for name in update.EVENTS:
            assert base.query_news("DIRECT_ROBOT_NOV02_"+name)==[],name

        baselines=(
            sample("LG전자 클로이드 자체 조립",
                   "LG전자 CLOiD 양재 데이터팩토리 연구용 수작업 조립 단계, 아직 양산 아님",
                   "ZDNet Korea"),
            sample("LG전자 50만시간 로봇 데이터팩토리 목표",
                   "LG전자 로봇 데이터팩토리 연말 50만 시간 확보 목표 계획",
                   "LG전자"),
            sample("원익로보틱스 로봇 손 촉각 센서",
                   "원익로보틱스 로봇 손 액추에이터 연말 시제품 출시 예정",
                   "원익로보틱스"),
            sample("대동기어 EYOU 합작법인 설립 추진",
                   "대동기어 EYOU 2027년 1월 합작법인 설립 목표 및 생산 계획",
                   "대동기어"),
            sample("아이엘 로봇 매출 27억원",
                   "아이엘 3분기 휴머노이드 로봇 매출 27억원이라고 보도",
                   "일반언론"),
        )
        for x in baselines:
            g,s,k,c=classify(x)
            assert g in expected and s==0,(g,s,x["title"])

        actual=sample("대동기어 EYOU 합작법인 설립 완료",
                      "대동기어 EYOU 중국 JV 합작법인 설립 완료 등기",
                      "대동기어")
        g,s,k,c=classify(actual)
        assert g=="daedong_eyou_robot_actuator" and s>=11,(g,s,c)
        assert "실제 설립" in c,c

        confirmed_lg=sample("LG전자 클로이드 양재 양산 개시",
                 "LG전자 CLOiD 양재 데이터팩토리 생산라인 가동 양산 개시",
                 "LG전자")
        g,s,k,c=classify(confirmed_lg)
        assert g=="lg_cloid_inhouse_assembly" and s>=11,(g,s,c)
        assert "양산라인" in c,c

        actual_hours=sample("LG전자 로봇 데이터팩토리 50만시간 확보 완료",
                 "LG전자 로봇 학습 데이터 50만 시간 확보 완료",
                 "LG전자")
        g,s,k,c=classify(actual_hours)
        assert g=="lg_robot_learning_hours_target" and s>=11,(g,s,c)
        assert "실제 확보" in c,c

        # MOU/article repeat should stay silent; no additional jobs or bot.
        assert all(q in base.QUERIES for q in update.EXTRA_QUERIES)
        assert len(base.QUERIES)==len(set(base.QUERIES))
    finally:
        base.NOW=oldnow
        base.load_state=oldload

if __name__=="__main__":
    run()
    print("Robot Nov02 stage/correction regression: PASS")

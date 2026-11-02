#!/usr/bin/env python3
"""No-send regression for AGIBOT/Qualcomm/Hyundai monitored milestones."""
from __future__ import annotations
import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import robot_watch_2026_nov_material_milestones as mod

def make_base():
 return SimpleNamespace(
  NOW=dt.datetime(2026,11,2,0,0,tzinfo=dt.timezone.utc),
  KST=ZoneInfo("Asia/Seoul"), QUERIES=["previous-topic"],
  query_news=lambda q:[],
  topic_group=lambda s:"old-category",
  score=lambda v:0,key=lambda v:"old-key",
  category=lambda t,g:"old-label",
  meaning=lambda t:"old-meaning",risk=lambda t:"old-risk",
  verification=lambda r,g,t:"old-verification",
  tag_for=lambda t:"old-tag",select_diverse=lambda a,b,c,d:[],
 )

def classify(base, item):
 t=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
 g=base.topic_group(t)
 return g,base.score(item),base.key(item),base.category(t,g)

def item(title,desc,source,pub="2026-11-02T00:00:00+00:00"):
 return {"title":title,"description":desc,"source":source,
         "link":"https://example.invalid/no-real-send","published":pub}

def run():
 b=make_base()
 mod.install(b)
 assert mod.AGIBOT_ONESHOT in b.QUERIES
 assert len(b.QUERIES)==len(set(b.QUERIES))
 event=b.query_news(mod.AGIBOT_ONESHOT)
 assert len(event)==1
 g,s,k,cat=classify(b,event[0])
 assert g==mod.AGIBOT_GROUP and s>=11 and len(k)==64,(g,s,cat)
 assert "Worken" in cat,cat
 assert "9월" in b.meaning(cat),cat
 assert b.select_diverse([dict(event[0],key=k,group=g,score=s)],set(),False,8)[0]["key"]==k
 assert b.select_diverse([dict(event[0],key=k,group=g,score=s)],{k},False,8)==[]

 historic=item(
  "AGIBOT reached its 20000th robot in September",
  "AGIBOT unveils Worken in October; the 20,000th robot had rolled off in September.",
  "AGIBOT",
 )
 assert classify(b,historic)[0]==mod.AGIBOT_GROUP
 assert classify(b,historic)[1]==0,"old cumulative production is not a new sale"
 agi_real=item(
  "AGIBOT Worken independent customer test",
  "AGIBOT Worken actual measured on factory floor with customer validated work hours.",
  "AGIBOT",
 )
 assert classify(b,agi_real)[0]==mod.AGIBOT_GROUP
 assert classify(b,agi_real)[1]>=11
 assert classify(b,agi_real)[2]!=k

 qualcomm_old=item(
  "Qualcomm Dragonwing IQ10 robotics demo",
  "Qualcomm and Figure collaborating on new humanoid IQ10 robotics processor.",
  "Qualcomm",
  "2026-01-05T00:00:00+00:00",
 )
 assert classify(b,qualcomm_old)[0]==mod.QUALCOMM_GROUP
 assert classify(b,qualcomm_old)[1]==0
 qualcomm_new=item(
  "Qualcomm Dragonwing IQ10 customer production",
  "Qualcomm Dragonwing IQ10 customer production started in robots.",
  "Qualcomm",
 )
 assert classify(b,qualcomm_new)[0]==mod.QUALCOMM_GROUP
 assert classify(b,qualcomm_new)[1]>=11

 hyundai_press=item(
  "현대차 로보틱스랩 모베드 에너지 효율 강조",
  "현대자동차 로보틱스랩 모베드 배터리 에너지 효율 개선이 중요한 목표이다.",
  "머니투데이",
  "2026-10-29T00:00:00+00:00",
 )
 assert classify(b,hyundai_press)[0]==mod.HYUNDAI_GROUP
 assert classify(b,hyundai_press)[1]==0
 hyundai_achieved=item(
  "현대차 로보틱스랩 모베드 전력소비 검증 완료",
  "현대자동차 로보틱스랩 모베드 전력소비 독립 검증 완료.",
  "현대자동차",
 )
 assert classify(b,hyundai_achieved)[0]==mod.HYUNDAI_GROUP
 assert classify(b,hyundai_achieved)[1]>=11
 denied=dict(hyundai_achieved,description="현대차 로보틱스랩 모베드 전력소비 독립 검증 완료는 미확인",source="블로그")
 assert classify(b,denied)[1]==0
 unrelated=item("Tesla Optimus hand production","Tesla Optimus hand assembly.", "Tesla")
 assert classify(b,unrelated)[0]=="old-category"
 assert classify(b,unrelated)[1]==0

 b.NOW=dt.datetime(2026,11,7,0,0,tzinfo=dt.timezone.utc)
 assert b.query_news(mod.AGIBOT_ONESHOT)==[]
 assert classify(b,agi_real)[1]>=11

if __name__=="__main__":
 run()
 print("AGIBOT Qualcomm Hyundai robot milestones: PASS")

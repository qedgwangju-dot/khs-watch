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

 # Actual delivered message 320 contained this previously announced Q3
 # earning result. Syndicated rewrites must retain its existing seen key,
 # without suppressing official company corrections/new contracts.
 sdi_repeat=item(
  '"ESS 수요 개선" 삼성SDI, 3분기 영업익 4078억… 전년比 20.9%↑',
  "Samsung SDI prior 2026 Q3 earnings report reprinted.",
  "더퍼블릭","2026-10-29T07:02:00+00:00",
 )
 assert classify(b,sdi_repeat)[1]==0
 assert classify(b,sdi_repeat)[2]==mod.SDI_Q3_EARNINGS_DELIVERED_KEY
 sdi_contract=item(
  '삼성SDI, 3분기 영업익 4078억 외 신규 공급계약 체결',
  "New binding ESS customer order announced separately.",
  "연합뉴스",
 )
 assert classify(b,sdi_contract)[2]!=mod.SDI_Q3_EARNINGS_DELIVERED_KEY


 # 2026-11-11 coverage extension is offline-only, no getMe, no sendMessage
 # and no writes to previously delivered dedup keys.
 import robot_watch_missing_milestones as missing
 n=make_base()
 missing.install(n)
 assert len(missing.NOV_2026_SIGNAL_TOPICS)==30
 assert len(n.QUERIES)==len(set(n.QUERIES))
 assert len(missing.NOV_2026_QUERIES)==16
 google=n.query_news("DIRECT_NOV10_GEMINI_ROBOTICS_25")
 wonik=n.query_news("DIRECT_NOV10_WONIK_CPS_SHA_SIGNED")
 assert len(google)==len(wonik)==1
 gg,gs,gk,gc=classify(n,google[0])
 wg,ws,wk,wc=classify(n,wonik[0])
 assert gg=="google_gemini_robotics" and gs>=11 and len(gk)==64,(gg,gs,gc)
 assert wg=="wonik_robot_financing" and ws>=11 and len(wk)==64,(wg,ws,wc)
 assert "공식" in n.verification(google[0],gg,google[0]["title"])
 assert "직접 열람 실패" in n.verification(wonik[0],wg,wonik[0]["title"])
 assert gk!=wk
 company_pilot=item(
  "Google DeepMind Gemini Robotics 2.5 Apollo 2",
  "Google DeepMind Gemini Robotics 2.5, Apollo 2 96% 성공 현장 실증 완료",
  "Google DeepMind",
 )
 assert classify(n,company_pilot)[0]=="google_gemini_robotics"
 assert classify(n,company_pilot)[1]>=11
 assert classify(n,company_pilot)[2]==gk,"Same Google pilot across first-party releases must dedup"
 analyst_only=item(
  "삼성SDI Atlas 70셀 공급 가능",
  "보스턴다이내믹스 아틀라스 삼성SDI 2170 배터리 70개 공급 전망",
  "로봇신문",
 )
 assert classify(n,analyst_only)[0]=="atlas_sdi_2170"
 assert classify(n,analyst_only)[1]==0,"Report-stage Atlas supplier must not become binding contract"
 baseline_wonik=item(
  "원익홀딩스 원익로보틱스 유상증자 국민성장펀드",
  "원익로보틱스 유상증자 3500억원 정부 지원 승인, 납입 11월20일 예정",
  "금융위원회",
 )
 assert classify(n,baseline_wonik)[1]==0,"Funding approval is not payment"
 rumour_hanwha=item(
  "한화시스템 라이온로보틱스",
  "한화 라이온로보틱스 700억원 지분투자 협상 추진",
  "조선비즈",
 )
 assert classify(n,rumour_hanwha)[1]==0,"Negotiations cannot become signed investment"
 media_spg=item(
  "에스피지 SDD 로봇 구동기",
  "에스피지 SDD 12월 양산 시작 예정",
  "파이낸스스코프",
 )
 assert classify(n,media_spg)[1]==0,"2026-12 plans must not be production achievements"
 future_spg=item(
  "에스피지 SDD 첫 양산 개시",
  "에스피지 SDD 첫 양산 개시 및 고객 테스트",
  "에스피지",
 )
 assert classify(n,future_spg)[0]=="spg_sdd"
 assert classify(n,future_spg)[1]>=11
 select=[dict(google[0],key=gk,group=gg,score=gs),dict(wonik[0],key=wk,group=wg,score=ws)]
 assert len(n.select_diverse(select,set(),False,8))==2
 assert n.select_diverse(select,{gk,wk},False,8)==[]
 n.NOW=dt.datetime(2026,11,14,0,0,tzinfo=dt.timezone.utc)
 assert n.query_news("DIRECT_NOV10_GEMINI_ROBOTICS_25")==[]
 assert n.query_news("DIRECT_NOV10_WONIK_CPS_SHA_SIGNED")==[]

 b.NOW=dt.datetime(2026,11,7,0,0,tzinfo=dt.timezone.utc)
 assert b.query_news(mod.AGIBOT_ONESHOT)==[]
 assert classify(b,agi_real)[1]>=11

if __name__=="__main__":
 run()
 print("AGIBOT Qualcomm Hyundai robot milestones: PASS")

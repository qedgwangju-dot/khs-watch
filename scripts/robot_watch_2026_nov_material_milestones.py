#!/usr/bin/env python3
"""AGIBOT, Qualcomm and Hyundai efficiency milestones on EXISTING physical-AI route.

No independent workflow, bot, receiver, or state. One dated first-party Oct 29
AGIBOT innovation release; its Sept 24 20,000th unit remains PRIOR baseline.
Qualcomm's Jan/Jun IQ10 launch and Hyundai's Oct29 energy-efficiency presentation
are baselines, not newly achieved purchase orders / endurance achievements.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re

AGIBOT_ONESHOT = "DIRECT_AGIBOT_WORKEN_AHA3_GO3_LINKU_OCT29_2026"
END_DATE = dt.date(2026,11,6)
AGIBOT_GROUP = "agibot_worken_hardware_model"
QUALCOMM_GROUP = "qualcomm_iq10_robot_commercial"
HYUNDAI_GROUP = "hyundai_robot_efficiency_proven"
AGIBOT_SRC = "https://www.agibot.com/article/231/detail/131.html"
QUALCOMM_SRC = "https://www.qualcomm.com/news/releases/2026/01/qualcomm-introduces-a-full-suite-of-robotics-technologies-power"
HYUNDAI_SRC = "https://www.mt.co.kr/index.php/industry/2026/10/29/2026102913175930896"

DATEROW = {
 "title": "AGIBOT 10월 29일 Worken 제안·AHA3·GO-3·G2 Max·Link-U OS 공식 공개",
 "description": (
  "2026-10-29 AGIBOT 회사 공식 Innovation Day 발표: Worken은 로봇의 "
  "유효 자율작업시간과 결과물로 생산성을 평가하자는 회사 제안이며 "
  "업계 공인 표준·공인 인증을 받은 지표가 아니다. "
  "회사 AHA3 통합 하드웨어 플랫폼과 GO-3 Preview·WITA-Omni 모델을 공개, "
  "G2 Max와 Link-U OS 1.0을 발표했다. "
  "Link-U OS 1.0은 이미 양산 로봇에서 검증했다고 설명했으나 일부 생태계 "
  "협력사가 시험 중이며 2026년 말 완전 오픈소스 공개는 향후 계획이다. "
  "AGIBOT 2만번째 로봇 생산은 2026년 9월 회사가 발표한 이전 사실이다. "
  "2만대가 모두 10월 신규 생산량 또는 현재 유료 가동 대수라는 뜻이 아니다. "
  "개별 고객의 작업시간·성공률·판매대수·매출은 별도 확인한다."
 ),
 "source":"AGIBOT",
 "link":AGIBOT_SRC,
 "published":None,
 "official_release_oct29":True,
}
AGIBOT_ID = re.compile(r"\bAGIBOT\b|智元机器人|智元|애지봇|지위안",re.I)
AGIBOT_TECH = re.compile(r"\bWorken\b|워켄|AHA3|GO[- ]?3|G2\s*Max|Link[- ]?U|WITA[- ]?Omni|Genie\s*Studio|AGIBOT\s*WORLD",re.I)
QUALCOMM_ID = re.compile(r"\bQualcomm\b|퀄컴",re.I)
QUALCOMM_TECH = re.compile(r"Dragonwing|IQ[- ]?10|IQ[- ]?9|robotics?\s*(?:compute|processor|SoC)|로봇\s*(?:칩|연산|프로세서)",re.I)
HYUNDAI_ID = re.compile(r"현대자동차|현대차|Hyundai\s*Motor|Hyundai\s*Robotics\s*Lab",re.I)
HYUNDAI_TECH = re.compile(r"MobED|모베드|로보틱스랩|robotics?\s*lab|로봇\s*에너지|물리\s*AI\s*전력",re.I)
ENERGY = re.compile(r"energy|전력|배터리|에너지|사용\s*시간|operating\s*hours?|효율|watt|Wh",re.I)
ACTUAL = {
 AGIBOT_GROUP:[
  ("measured_worken_onsite",r"(?:Worken|워켄).{0,85}(?:actual\s*measured|customer\s*validated|independently\s*validated|실제\s*고객\s*측정|현장\s*측정\s*완료)"),
  ("real_paid_linku_deployment",r"(?:Link[- ]?U|G2\s*Max|GO[- ]?3).{0,80}(?:binding\s*purchase\s*order|first\s*commercial\s*delivery|paid\s*customer\s*deployment|구매\s*계약\s*체결|초도\s*유상\s*인도)"),
  ("linku_full_open_release",r"Link[- ]?U.{0,60}(?:fully\s*open[- ]sourced|actual\s*source\s*code\s*released|완전\s*오픈소스\s*공개\s*완료)"),
 ],
 QUALCOMM_GROUP:[
  ("iq10_actual_customer_shipments",r"(?:IQ[- ]?10|Dragonwing).{0,95}(?:first\s*commercial\s*shipment|actual\s*customer\s*deliver(?:y|ies)|customer\s*production\s*started|고객\s*양산\s*시작|초도\s*공급\s*완료)"),
  ("iq10_robot_design_win_contract",r"(?:IQ[- ]?10|Dragonwing).{0,95}(?:binding\s*production\s*contract|confirmed\s*purchase\s*order|양산\s*계약\s*체결|확정\s*구매\s*발주)"),
 ],
 HYUNDAI_GROUP:[
  ("robot_energy_independent_test",r"(?:MobED|모베드|로봇).{0,80}(?:사용시간|운전시간|energy\s*per\s*task|Wh\s*per\s*task|전력소비).{0,60}(?:검증\s*완료|독립\s*검증|test\s*passed|independently\s*measured)"),
  ("mobed_paid_customer_delivery",r"(?:MobED|모베드).{0,75}(?:정식\s*공급계약\s*체결|실제\s*고객\s*인도|first\s*commercial\s*shipment|signed\s*paid\s*customer\s*contract)"),
 ],
}
OFFICIAL = {
 AGIBOT_GROUP:{"AGIBOT","AGIBOT Official","AGIBOT Newsroom","智元机器人"},
 QUALCOMM_GROUP:{"Qualcomm","Qualcomm Newsroom","Qualcomm Technologies","Figure","NEURA Robotics"},
 HYUNDAI_GROUP:{"현대자동차","Hyundai Motor Group","Hyundai Robotics Lab","현대차그룹","현대자동차그룹"},
}
REJECT = re.compile(
 r"\b(?:not|no|denied|unverified|unconfirmed|would|could|may|will|plans?|"
 r"planning|expected|aims?|targets?|scheduled)\b|"
 r"미확인|예정|계획|목표|기대|검토|추진|협상|부인|미체결|전망|"
 r"완료하지|확정하지|아직", re.I
)
SEARCH = (
 '(AGIBOT OR 智元机器人 OR 애지봇) (Worken OR AHA3 OR GO-3 OR G2 Max OR Link-U OS OR WITA-Omni) '
 '(고객 작업시간 OR customer deployment OR 실제 양산 OR 채택 OR launch OR 발표)',
 '(AGIBOT OR 애지봇) (Link-U OS OR Genie Studio OR AGIBOT WORLD) '
 '(official release OR open source OR software adoption OR first commercial deployment)',
 '(Qualcomm OR 퀄컴) (Dragonwing IQ10 OR IQ10 robotics OR Figure OR NEURA) '
 '(actual production OR robot customer OR shipments OR binding purchase order OR 양산계약)',
 '(현대차 로보틱스랩 OR Hyundai Robotics Lab OR MobED OR 모베드) '
 '(에너지 효율 OR power per task OR battery runtime OR low power AI OR 유상 공급계약 OR 실제 출하)',
)

def identity(text: str) -> str:
 if AGIBOT_ID.search(text) and AGIBOT_TECH.search(text):
  return AGIBOT_GROUP
 if QUALCOMM_ID.search(text) and QUALCOMM_TECH.search(text) and re.search(r"robot|로봇|휴머노이드|humanoid|Figure|NEURA",text,re.I):
  return QUALCOMM_GROUP
 if HYUNDAI_ID.search(text) and HYUNDAI_TECH.search(text) and ENERGY.search(text):
  return HYUNDAI_GROUP
 return ""

def achieved(item: dict, group: str) -> str:
 if (item.get("source") or "") not in OFFICIAL.get(group,set()):
  return ""
 text=" ".join(str(item.get(k) or "") for k in ("title","description"))
 for stage,p in ACTUAL.get(group,[]):
  for m in re.finditer(p,text,re.I):
   near=text[max(0,m.start()-32):min(len(text),m.end()+22)]
   if not REJECT.search(near):
    return stage
 return ""

def install(base) -> None:
 prev={s:getattr(base,s) for s in ("query_news","topic_group","score","key","category","meaning","risk","verification","tag_for","select_diverse")}
 groups={
  AGIBOT_GROUP:"애지봇 · 실제 Worken·로봇 플랫폼 상용화 검증",
  QUALCOMM_GROUP:"퀄컴 Dragonwing IQ10 · 실제 로봇 고객 채택",
  HYUNDAI_GROUP:"현대차 로보틱스랩 · 로봇 전력효율·고객 인도",
 }
 def query(q):
  if q==AGIBOT_ONESHOT:
   if base.NOW.astimezone(base.KST).date()>END_DATE:return []
   return [dict(DATEROW)]
  return prev["query_news"](q)
 def group(text):
  return identity(text) or prev["topic_group"](text)
 def score(row):
  if row.get("official_release_oct29"):return 47
  g=identity(" ".join(str(row.get(k) or "") for k in ("title","description","source")))
  if not g:return prev["score"](row)
  return 38 if achieved(row,g) else 0
 def key(row):
  if row.get("official_release_oct29"):
   return hashlib.sha256(b"agibot|2026-10-29|Worken-AHA3-GO3-G2Max-LinkU|official-announcement").hexdigest()
  g=identity(" ".join(str(row.get(k) or "") for k in ("title","description","source")))
  if not g:return prev["key"](row)
  stage=achieved(row,g) or "background"
  return hashlib.sha256(f"2026-robot-commercial|{g}|{stage}".encode()).hexdigest()
 def category(text,g):
  if g==AGIBOT_GROUP:
   if "Worken" in text and "2026-10-29" in text:
    return "애지봇 · Worken 제안·차세대 하드웨어·모델 신규 공개"
   return groups[g]
  return groups[g] if g in groups else prev["category"](text,g)
 def meaning(cat):
  if cat=="애지봇 · Worken 제안·차세대 하드웨어·모델 신규 공개":
   return ("애지봇의 10월 29일 공식 Worken 생산성 지표 제안과 AHA3·GO-3·G2 Max·Link-U OS 신규 발표입니다. "
           "2만 번째 로봇 생산은 9월 회사 발표의 기존 기준선이며 10월 신규 출하가 아닙니다. "
           "고객 유상 작업시간·현장 도입·매출은 별도.")
  if cat in groups.values():
   return ("로봇 제품/칩의 실제 완료 이정표와 기존 기술 발표·시장 전망을 구분합니다. "
           "공식 고객·검수·출하·상용화 매출과 테스트 성능을 별도 확인해야 합니다.")
  return prev["meaning"](cat)
 def risk(cat):
  if cat=="애지봇 · Worken 제안·차세대 하드웨어·모델 신규 공개":
   return ("Worken은 회사 제안 기준으로 산업 공식 표준이 아니며, 2만대 누적 생산과 "
           "실제 2만대 유료 가동/2026년 10월 신규 생산을 혼동하지 않습니다. "
           "장비 신뢰성·작업당 에너지·자율성·고객 계약을 검증합니다.")
  if cat in groups.values():
   return ("협력·출시 기사와 확정 양산/상용 출하를 구분합니다. "
           "전력소모·지연시간·손 조작 신뢰성·고객 인증·수율이 실패 경로입니다.")
  return prev["risk"](cat)
 def verification(row,g,text):
  if g in groups:
   if row.get("official_release_oct29"):
    return ("AGIBOT 회사 공식 2026-10-29 Innovation Day 자료·동일 회사 보도자료 대조; "
            "20,000번째 로봇 생산은 9월 기존 성과, Worken은 신규 제안")
   return ("회사/고객 공식 단계 판정: " + (achieved(row,g) or "기존 사업 방향")
           + " · 독립 실적·계약 확인은 별도")
  return prev["verification"](row,g,text)
 def tag(g):
  return {AGIBOT_GROUP:"애지봇 생산·Worken",QUALCOMM_GROUP:"퀄컴 로봇 IQ10",HYUNDAI_GROUP:"현대차 로봇 전력효율"}.get(g) or prev["tag_for"](g)
 def select(items,seen,force,limit):
  result=prev["select_diverse"](items,seen,force,limit)
  candidates=items if force else [v for v in items if v.get("key") not in seen]
  hit=next((v for v in candidates if v.get("official_release_oct29") and v.get("score",0)>=11),None)
  if hit and not any(v.get("key")==hit.get("key") for v in result):
   return [hit,*result][:limit]
  return result
 base.query_news=query
 base.topic_group=group
 base.score=score
 base.key=key
 base.category=category
 base.meaning=meaning
 base.risk=risk
 base.verification=verification
 base.tag_for=tag
 base.select_diverse=select
 for q in (AGIBOT_ONESHOT,*SEARCH):
  if q not in base.QUERIES:base.QUERIES.append(q)

#!/usr/bin/env python3
"""Additional user-supplied 2026 robotics coverage for the EXISTING alert route.

Preserves all prior workflows, recipients, timestamps and seen keys.
Reported exhibitions, RFQs, demos, policy R&D and recruiting are baselines.
Alert ONLY on new issuer/partner-source achievements, never on old promises
or unconfirmed supply-chain guesses. No dated backfills and no new bot.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re

# The input requires both identity and the industrial/application context.
TOPICS = {
 "surgery_robot_hospital": {
   "match": (r"삼성서울병원|Samsung\s*Medical\s*Center",
             r"휴머노이드|로봇|robot", r"수술|surg"),
   "official": {"삼성서울병원","Samsung Medical Center","보건복지부","Ministry of Health and Welfare","식품의약품안전처"},
   "steps": (
      ("clinical_approval",r"임상시험\s*(?:계획\s*)?(?:승인|허가)|IRB\s*(?:approval|approved)|clinical\s*trial\s*(?:approved|authorized)"),
      ("first_patient_actual",r"첫\s*환자.{0,24}(?:수술|적용|투입)\s*(?:완료|실시|시작)|first\s*patient.{0,35}(?:treated|performed|procedure)"),
      ("clinical_trial_started",r"임상(?:시험)?\s*(?:개시|착수)|clinical\s*trial\s*(?:began|started)"),
   ),
   "tag":"삼성서울병원 수술 보조 로봇",
   "watch":"임상 승인·첫 환자 실제 사용·도구 전달 성능",
 },
 "bigwave_rainbow_northamerica": {
   "match": (r"빅웨이브로보틱스|BIGWAVE\s*Robotics",
             r"레인보우로보틱스|Rainbow\s*Robotics",
             r"북미|미국|North\s*America|US\s*customer|미시간|Detroit"),
   "official":{"빅웨이브로보틱스","BIGWAVE ROBOTICS","레인보우로보틱스","Rainbow Robotics"},
   "steps": (
     ("paid_pilot_completed",r"유료.{0,24}(?:실증|검증|PoC).{0,25}(?:완료|통과)|paid\s*pilot\s*(?:completed|passed)"),
     ("signed_customer_order",r"정식\s*(?:공급|구매)\s*계약\s*체결|구매\s*발주서\s*확정|signed\s*(?:supply|purchase)\s*(?:agreement|contract)"),
     ("first_customer_delivery",r"북미.{0,35}(?:초도|첫)\s*(?:납품|인도|출하)\s*(?:완료|개시)|first\s*(?:US|North\s*American)\s*shipment"),
   ),
   "tag":"빅웨이브·레인보우 북미 실증",
   "watch":"350건 전시 상담→유료 현장 검증→구매주문→출하",
 },
 "neoauto_rover": {
   "match":(r"네오오토|Neoauto|Neo\s*Auto",r"로버|rover|행성\s*탐사",r"감속기|actuator|구동\s*부품|gear"),
   "official":{"네오오토","Neoauto","Neo Auto","산업통상자원부","한국산업기술기획평가원","KEIT"},
   "steps": (
     ("government_rnd_test_pass",r"1\s*단계.{0,30}(?:시험|검증)\s*(?:완료|통과)|1\s*세부.{0,30}(?:검증|시험)\s*통과|국책과제.{0,55}평가\s*통과"),
     ("customer_validation_passed",r"(?:고객|우주\s*환경).{0,30}(?:성능|신뢰성)\s*(?:검증|시험)\s*통과"),
     ("binding_order",r"(?:정식\s*)?(?:공급|구매)\s*계약\s*체결|확정\s*발주서"),
   ),
   "tag":"네오오토 로버 감속기",
   "watch":"실물 조립 후 국책 1단계 통과·신뢰성 시험·실제 고객 계약",
 },
 "almec_boston": {
   "match":(r"알멕|Almac|ALMAC",r"보스턴다이내믹스|Boston\s*Dynamics|Atlas|아틀라스",r"로봇|robot|RFQ|견적|프레임"),
   "official":{"알멕","ALMAC","Boston Dynamics"},
   "steps":(
     ("customer_qualified",r"(?:고객|보스턴다이내믹스).{0,38}(?:공급업체|품질|신뢰성)\s*(?:승인|검증\s*통과)"),
     ("binding_robot_order",r"(?:보스턴다이내믹스|Boston\s*Dynamics).{0,75}(?:공급계약\s*체결|정식\s*발주|purchase\s*order)|(?:공급계약\s*체결|정식\s*발주).{0,70}(?:보스턴다이내믹스|Boston\s*Dynamics)"),
     ("first_robot_shipment",r"(?:보스턴다이내믹스|Boston\s*Dynamics).{0,75}(?:초도\s*납품|첫\s*출하)\s*(?:완료|개시)"),
   ),
   "tag":"알멕·보스턴다이내믹스",
   "watch":"견적요청서→정식 공급사 선정→구속력 있는 구매주문→초도 출하",
 },
 "cps_rainbow_robokit": {
   "match":(r"씨피시스템|CP\s*System",r"로보킷|Robokit|케이블\s*(?:보호|체인)|cable",
            r"레인보우로보틱스|Rainbow\s*Robotics|협동로봇"),
   "official":{"씨피시스템","CP System","레인보우로보틱스","Rainbow Robotics"},
   "steps":(
     ("production_contract",r"양산용.{0,35}(?:공급계약\s*체결|정식\s*발주)|정식\s*공급\s*계약\s*체결"),
     ("first_mass_shipment",r"양산용.{0,40}(?:초도\s*납품|첫\s*출하)\s*(?:완료|개시)|실제\s*양산.{0,35}납품\s*(?:완료|시작)"),
     ("repeat_order",r"후속\s*(?:수주|발주)\s*(?:확정|체결)|반복\s*발주\s*확정"),
   ),
   "tag":"씨피시스템·레인보우 케이블",
   "watch":"기존 1월 로보킷 시제품→양산 계약·실물 납품·반복 수주",
 },
 "hatchtec_encoder_hand": {
   "match":(r"해치텍|Hatchtec|Hatch\s*Tech",r"인코더|encoder|관절\s*(?:위치|정밀)",r"로봇|robot|휴머노이드"),
   "official":{"해치텍","Hatchtec","Hatch Tech"},
   "steps":(
     ("customer_qualified",r"(?:고객|휴머노이드).{0,35}(?:검증|인증|평가)\s*(?:완료|통과)"),
     ("volume_contract",r"(?:인코더|encoder).{0,45}(?:공급계약\s*체결|대량\s*발주\s*확정|양산\s*공급\s*개시)"),
   ),
   "tag":"해치텍 로봇 인코더 IC",
   "watch":"기술 적합성→고객 검증 완료→양산 물량·실제 매출",
 },
 "bytedance_robot_hardware": {
   "match":(r"바이트댄스|ByteDance|字节跳动",r"로봇|robot|휴머노이드"),
   "official":{"ByteDance","바이트댄스","字节跳动"},
   "steps":(
     ("actual_production",r"휴머노이드.{0,50}(?:양산\s*(?:시작|개시)|production\s*(?:started|commenced))"),
     ("first_customer_delivery",r"휴머노이드.{0,50}(?:첫\s*고객\s*인도\s*완료|first\s*customer\s*delivery)"),
     ("signed_customer_deal",r"휴머노이드.{0,50}(?:공급계약\s*체결|signed\s*customer\s*contract)"),
   ),
   "tag":"바이트댄스 휴머노이드",
   "watch":"Seed 팀 채용과 실제 로봇 양산·고객 유상 공급은 별개",
 },
 "amogreentech_robot_magnets": {
   "match":(r"아모그린텍|Amogreentech",r"로봇|robot|휴머노이드",r"자성|magnetic|자석|motor|모터"),
   "official":{"아모그린텍","Amogreentech"},
   "steps":(
     ("robot_customer_qualified",r"(?:로봇|휴머노이드).{0,45}(?:고객\s*승인|실제\s*고객\s*검증\s*통과)"),
     ("robot_binding_order",r"(?:로봇|휴머노이드).{0,45}(?:공급계약\s*체결|정식\s*발주|양산\s*납품\s*개시)"),
   ),
   "tag":"아모그린텍 로봇 자성소재",
   "watch":"사업 관련성→로봇 고객 실명·제품·실제 납품 계약",
 },
 "openai_data_center_robots": {
   "match":(r"OpenAI|오픈AI|오픈에이아이",r"데이터\s*센터|data\s*center",r"로봇|robot"),
   "official":{"OpenAI","OpenAI Newsroom"},
   "steps":(
     ("deployed_on_construction_site",r"실제\s*(?:건설\s*현장|데이터센터).{0,45}로봇.{0,25}(?:투입|배치)\s*(?:완료|개시)|robots?\s*(?:deployed|working)\s*on\s*data\s*center\s*construction"),
     ("paid_construction_deal",r"데이터센터.{0,45}로봇.{0,25}(?:유상\s*계약\s*체결|공급계약\s*체결)"),
   ),
   "tag":"OpenAI 데이터센터 건설 로봇",
   "watch":"올트먼의 장기 구상→실제 건설 현장 투입·계약 확인",
 },
}
RESEARCH_ONLY = re.compile(
 r"\b(?:not|no|without|not yet|unconfirmed|denied|would|could|may|"
 r"plans?|planning|planned|expect(?:s|ed)?|target(?:s|ed)?|aims?|"
 r"considering|proposed)\b|미확인|아직|부인|미체결|계획|목표|예정|"
 r"전망|추진|검토|협의|가능성|관심|시연|견적요청|채용",
 re.I)
# Keep source exact: scraped media headlines never masquerade as an
# issuer-issued first-party contract or clinical decision.
QUERIES = (
 '(삼성서울병원 OR "Samsung Medical Center") '
 '(휴머노이드 OR 로봇수술 OR surgical robot) '
 '(IRB 승인 OR 임상시험 개시 OR first patient OR 로봇 수술 실제 투입)',
 '(빅웨이브로보틱스 OR "BIGWAVE Robotics" OR 씨피시스템) '
 '(레인보우로보틱스 OR "Rainbow Robotics") '
 '(유료 실증 OR signed contract OR 로보킷 양산 OR 미국 납품 OR 반복 발주)',
 '(네오오토 OR Neoauto OR 알멕 OR ALMAC) '
 '(감속기 OR 로버 OR Boston Dynamics OR 보스턴다이내믹스) '
 '(신뢰성 시험 통과 OR 공급사 선정 OR 정식 발주 OR 공급계약 OR 첫 출하)',
 '(해치텍 OR Hatchtec OR 아모그린텍 OR Amogreentech OR ByteDance OR 바이트댄스) '
 '(인코더 OR 로봇 관절 OR 휴머노이드 OR 자성소재) '
 '(고객 인증 OR 양산 계약 OR first shipment OR production started)',
 '(OpenAI OR 오픈AI) (data center OR 데이터센터) (robot OR 로봇) '
 '(deployed OR 실제 투입 OR construction contract OR 유상 계약)',
)

def topic(text: str) -> str:
    for label,spec in TOPICS.items():
        if all(re.search(pattern,text,re.I) for pattern in spec["match"]):
            return label
    return ""

def achieved(item: dict, group: str) -> str:
    spec=TOPICS.get(group)
    if not spec or str(item.get("source") or "").strip() not in spec["official"]:
        return ""
    text=" ".join(str(item.get(k) or "") for k in ("title","description"))
    for stage,pattern in spec["steps"]:
        for found in re.finditer(pattern,text,re.I):
            near=text[max(0,found.start()-30):found.end()+22]
            if RESEARCH_ONLY.search(near):
                continue
            return stage
    return ""

def install(base) -> None:
    prev={f:getattr(base,f) for f in (
        "topic_group","score","key","category","meaning","risk",
        "verification","tag_for","select_diverse"
    )}
    labels={g:f"{spec['tag']} · 공식 단계 진전" for g,spec in TOPICS.items()}
    def group(text):
        return topic(text) or prev["topic_group"](text)
    def score(item):
        body=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
        t=topic(body)
        return (38 if achieved(item,t) else 0) if t else prev["score"](item)
    def key(item):
        body=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
        t=topic(body)
        if not t:return prev["key"](item)
        stage=achieved(item,t) or "baseline"
        raw=f"robot-coverage-v1|{t}|{stage}"
        return hashlib.sha256(raw.encode()).hexdigest()
    def category(text,t):
        return labels[t] if t in TOPICS else prev["category"](text,t)
    def meaning(cat):
        t=next((g for g,v in labels.items() if v==cat),None)
        if t:
            return ("기업·기관의 공식 새 이정표 확인 단계. " + TOPICS[t]["watch"]
                    + " / 계획·시연·고객 검증·계약·양산·인식 매출은 구분합니다.")
        return prev["meaning"](cat)
    def risk(cat):
        if cat in labels.values():
            return ("업계 보도를 확정 계약·매출로 오인하지 않습니다. "
                    "고객 검수·정밀도·수율·내구성·실제 출하·대금 회수 및 인증을 점검합니다.")
        return prev["risk"](cat)
    def verification(item,t,text):
        if t in TOPICS:
            return ("기업·기관 명의 공식 신규 단계 보도에 한정한 기계판정 / "
                    "고객·금액·원문·시험 조건 독립 확인 전")
        return prev["verification"](item,t,text)
    def tag(t):
        return TOPICS[t]["tag"] if t in TOPICS else prev["tag_for"](t)
    def select(items,seen,force,limit):
        selected=prev["select_diverse"](items,seen,force,limit)
        candidates=items if force else [x for x in items if x.get("key") not in seen]
        new=next((x for x in candidates if x.get("group") in TOPICS
                  and x.get("score",0)>=11),None)
        if new and not any(x.get("key")==new.get("key") for x in selected):
            return [new,*selected][:limit]
        return selected
    base.topic_group=group
    base.score=score
    base.key=key
    base.category=category
    base.meaning=meaning
    base.risk=risk
    base.verification=verification
    base.tag_for=tag
    base.select_diverse=select
    for q in QUERIES:
        if q not in base.QUERIES:base.QUERIES.append(q)
    # Pure no-network / no-send invariants to prevent accidental claims
    # of orders from historical demo, engineering and recruiting stories.
    for text in (
        "빅웨이브로보틱스 레인보우로보틱스 미국 350건 시연 상담",
        "삼성서울병원 수술 보조 로봇 2029년 임상시험 계획",
        "네오오토 로버 감속기 실물 조립 착수",
        "알멕 보스턴다이내믹스 RFQ 견적요청서",
        "씨피시스템 레인보우로보틱스 로보킷 케이블 시제품 공급",
        "해치텍 로봇 관절 인코더 기술 적용 가능성",
        "바이트댄스 휴머노이드 로봇 대규모 인력 채용",
    ):
        t=topic(text)
        if t:
            row={"title":text,"description":"계약·실제 양산 확정 미확인","source":"일반언론"}
            assert score(row)==0,(text,t,score(row))

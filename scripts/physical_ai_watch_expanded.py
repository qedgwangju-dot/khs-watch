#!/usr/bin/env python3
"""Expanded high-signal layer for the physical-AI Telegram watcher.

Adds high-signal lanes for:
- Samhyun humanoid actuator customer / prototype / mass-production funnel
- XPENG IRON production-line -> supplier nomination -> SOP -> delivery milestones
- General robot-foundation-model commercialization beyond generic RFM explainers
- Agility Robotics wheeled-platform productization beyond concept renders
- LG Electronics AXIUM / Bear Robotics commercialization and valuation events
- Frontier-AI -> robotics only when an explicit robot integration / action-model link exists

Generic RFM/frontier-model explainers and concept-only robot renders are deliberately excluded from alerts.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_readable as readable

ext = readable.ext
base = readable.base

base.QUERIES.extend([
    '(삼현 OR SAMHYUN) (휴머노이드 OR humanoid OR 로봇 OR robot) (액추에이터 OR actuator OR 모터 OR 감속기 OR 제어기) (20곳 OR 20개 OR 4건 OR 프로토타입 OR prototype OR 양산 OR 수주 OR 고객 OR 공급)',
    '(삼현 OR SAMHYUN) (액추에이터 OR actuator) (생산능력 OR capacity OR 50만 OR 100만 OR 150만 OR 창원 2공장 OR 5PPM)',
    '(삼현 OR SAMHYUN) (AXLON OR 액슬론 OR 휴머노이드) (초도 양산 OR 양산 수주 OR 북미 OR 12월 OR 첫 출하 OR 후속 발주 OR 추가 수주)',
    '(XPENG OR 샤오펑 OR 小鹏) (IRON OR 휴머노이드 OR humanoid OR 人形机器人) (양산 OR mass production OR 생산라인 OR production line OR 출하 OR delivery OR 2026 OR 2027)',
    '(XPENG OR 샤오펑 OR 小鹏) (IRON OR 机器人 OR robot) (审厂 OR supplier audit OR factory audit OR 공급망 심사 OR 核心零部件定点 OR 定点 OR supplier nomination OR 공급사 선정 OR core component supplier)',
    '(XPENG OR 샤오펑 OR 小鹏) (IRON OR 人形机器人 OR humanoid) (量产 OR mass production OR SOP OR 平台 OR platform OR 交付 OR delivery OR 中国 OR China OR 海外 OR overseas OR global OR 延期 OR delay)',
    '("robot foundation model" OR RFM OR "cross-embodiment" OR "cross embodiment" OR "Open X-Embodiment" OR "Open X Embodiment" OR π0 OR "Physical Intelligence" OR "Isaac GR00T" OR GR00T) (robot OR robotics OR 로봇 OR 휴머노이드) (release OR benchmark OR success rate OR deployment OR pilot OR customer OR contract OR license OR 공개 OR 벤치마크 OR 성공률 OR 배치 OR 실증 OR 고객 OR 계약)',
    '("NC AI" OR 엔씨AI OR "POSCO DX" OR 포스코DX) (RFM OR "robot foundation model" OR 로봇 파운데이션 모델 OR VLA) (공동개발 OR MOU OR 모델 공개 OR release OR 실증 OR 현장 OR 고객 OR 계약 OR 배치 OR benchmark OR 성능)',
    '(Agility Robotics OR 애질리티 로보틱스 OR "Jonathan Hurst") (wheeled OR wheels OR wheel OR 바퀴형 OR 휠 OR 이동 플랫폼) (concept OR explore OR prototype OR product OR launch OR customer OR order OR deployment OR mass production OR 컨셉 OR 검토 OR 시제품 OR 제품 OR 출시 OR 고객 OR 수주 OR 배치 OR 양산)',
    '(LG전자 OR "LG Electronics") (AXIUM OR 악시움 OR 액추에이터 OR actuator) (빅테크 OR "Big Tech" OR 수주 OR 공급 OR 고객 OR 10월 OR October OR 양산 OR mass production)',
    '(베어로보틱스 OR "Bear Robotics") (상장 OR IPO OR Nasdaq OR 나스닥 OR 프리IPO OR pre-IPO OR 투자유치 OR valuation)',
    '(GPT-6 Astra OR OpenAI OR "Gemini Robotics" OR "frontier AI" OR 프런티어AI) (robotics OR 로보틱스 OR robot OR 로봇 OR humanoid OR 휴머노이드 OR embodied AI OR 피지컬AI) (planning OR reasoning OR action model OR 행동모델 OR VLA OR RFM OR robot foundation model OR 배치 OR deployment OR integration OR 통합)',
    '("Google DeepMind" OR DeepMind OR "Gemini Robotics") (robot OR robotics OR humanoid OR 로봇 OR 휴머노이드) ("new partner" OR partnership OR "general availability" OR "public API" OR pricing OR license OR "customer deployment" OR 신규 파트너 OR 파트너십 OR 정식 출시 OR 공개 API OR 가격 OR 사용권 OR 고객 배치)',
])

base.TRUSTED.update({
    '이데일리', 'EDAILY', '뉴스핌', 'Investors Business Daily', 'Reuters',
    'The Robot Report', '澎湃新闻', 'The Paper', '第一财经', 'IT之家',
})
base.OFFICIAL_OR_PRIMARY.update({
    'XPENG', 'XPeng', '小鹏汽车', 'LG전자', 'LG Electronics',
    'Google DeepMind', 'DeepMind', 'Physical Intelligence', 'NVIDIA', 'NVIDIA Developer',
    'POSCO DX', '포스코DX', 'NC AI', '엔씨AI', 'Agility Robotics',
})
base.MAX_ALERTS = 8

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_same_event = ext._same_event


SAMHYUN_INITIAL_MASS_ORDER = re.compile(
    r'초도\s*양산.{0,30}(?:수주|물량|공급)|양산\s*물량.{0,30}수주|'
    r'양산\s*수주|초도\s*수주|mass[-\s]*production.{0,24}(?:order|award)|'
    r'(?:order|award).{0,24}mass[-\s]*production',
    re.I,
)
SAMHYUN_FIRST_SHIPMENT = re.compile(
    r'첫\s*출하|초도\s*출하|출하\s*(?:시작|개시|완료)|공급\s*(?:개시|완료)|'
    r'납품\s*(?:시작|개시|완료)|first\s*shipment|shipments?\s*(?:started|began)|'
    r'deliver(?:y|ies)\s*(?:started|began)',
    re.I,
)
SAMHYUN_REPEAT_ORDER = re.compile(
    r'후속\s*(?:발주|수주|주문)|추가\s*(?:발주|수주|주문)|반복\s*발주|'
    r'follow[-\s]*on\s*order|repeat\s*order|additional\s*order',
    re.I,
)
SAMHYUN_PROTO = re.compile(r'프로토타입|prototype|샘플\s*발주|sample\s*order|\bAward\b|Spec[-\s]*in', re.I)
SAMHYUN_CAPA = re.compile(r'생산\s*능력|capacity|창원\s*2공장|50만|100만|150만|5\s*PPM|자동화\s*생산라인', re.I)

XPENG_ID = re.compile(r'XPENG|샤오펑|小鹏', re.I)
XPENG_IRON = re.compile(r'\bIRON\b|휴머노이드|humanoid|人形机器人|机器人', re.I)
XPENG_LINE_BASELINE = re.compile(
    r'(?:production\s*line|生产线|생산\s*라인).{0,100}(?:commission|operation|启用|가동|정식\s*가동)|'
    r'(?:walked|walks|rolls)\s+off.{0,80}(?:production\s*line|line)|'
    r'(?:生产线|생산\s*라인).{0,100}(?:自主|자율).{0,40}(?:走下|보행)|'
    r'(?:core\s*process|핵심\s*공정).{0,50}(?:80\s*%|80%)',
    re.I,
)
XPENG_SUPPLIER_AUDIT = re.compile(r'审厂|supplier\s*audit|factory\s*audit|공급망\s*심사|공급사\s*실사', re.I)
XPENG_SUPPLIER_NOMINATION = re.compile(
    r'核心零部件定点|核心供应商定点|定点(?:协议)?|supplier\s*(?:nomination|nominated|selected)|'
    r'core\s+component\s+supplier.{0,40}(?:selected|nominated)|핵심\s*부품.{0,30}공급사\s*선정|공급사\s*선정',
    re.I,
)
XPENG_SUPPLIER_20260922_BASELINE = re.compile(
    r'首届机器人供应链合作伙伴大会|first\s+robot(?:ics)?\s+supply\s+chain\s+partner\s+conference|'
    r'已完成供应链审厂及核心零部件定点|완료.{0,30}공급망\s*심사.{0,30}핵심\s*부품\s*공급사\s*선정',
    re.I,
)
XPENG_ACTUAL_SOP = re.compile(
    r'正式量产|量产(?:正式)?(?:开始|启动)|进入量产|批量生产(?:正式)?(?:开始|启动)|'
    r'mass[-\s]*production\s*(?:started|began|commenced)|(?:started|began|commenced)\s+mass[-\s]*production|'
    r'SOP.{0,20}(?:started|began|개시|시작)|양산.{0,20}(?:개시|시작|돌입)',
    re.I,
)
XPENG_PLATFORM_LAUNCH = re.compile(
    r'(?:首个|첫|first).{0,30}(?:商业|상용|commercial).{0,30}(?:平台|플랫폼|platform).{0,25}(?:发布|출시|공개|launch|released)|'
    r'(?:平台|플랫폼|platform).{0,25}(?:正式发布|정식\s*출시|launched|released)',
    re.I,
)
XPENG_CHINA_DELIVERY = re.compile(
    r'(?:中国|중국|China).{0,80}(?:交付|인도|delivery|deliveries).{0,30}(?:开始|启动|개시|시작|began|started)|'
    r'(?:交付|인도|delivery|deliveries).{0,30}(?:中国|중국|China).{0,50}(?:开始|개시|started|began)',
    re.I,
)
XPENG_GLOBAL_DELIVERY = re.compile(
    r'(?:海外|global|overseas|international|글로벌|해외).{0,80}(?:交付|delivery|deliveries|인도|出口|export).{0,30}(?:开始|启动|개시|시작|began|started)|'
    r'(?:首批|first).{0,30}(?:海外|global|overseas|international|해외).{0,30}(?:交付|delivery|shipment|인도)',
    re.I,
)
XPENG_DELAY = re.compile(r'(?:IRON|机器人|humanoid).{0,120}(?:延期|延后|推迟|delay|postpon|push[-\s]*back|지연|연기|미뤄)', re.I)
XPENG_PLAN_ONLY = re.compile(r'计划|目标|预计|拟|will|target|plan|planned|expected|예정|계획|목표|전망|예상', re.I)

RFM_ID = re.compile(
    r'robot\s*foundation\s*model|로봇\s*파운데이션\s*모델|\bRFM\b|cross[-\s]*embodiment|'
    r'Open\s*X[-\s]*Embodiment|\bπ0\b|\bpi0\b|Physical\s*Intelligence|Isaac\s*GR00T|\bGR00T\b',
    re.I,
)
RFM_NC_POSCO = re.compile(r'(?:NC\s*AI|엔씨\s*AI).{0,80}(?:POSCO\s*DX|포스코DX)|(?:POSCO\s*DX|포스코DX).{0,80}(?:NC\s*AI|엔씨\s*AI)', re.I)
RFM_BASELINE = re.compile(
    r'(?:22\s*(?:robot|로봇).{0,80}(?:Open\s*X|X[-\s]*Embodiment)|'
    r'Open\s*X[-\s]*Embodiment.{0,100}22\s*(?:robot|embodiment)|'
    r'(?:MOU|업무협약|공동개발).{0,80}(?:NC\s*AI|엔씨\s*AI).{0,80}(?:POSCO\s*DX|포스코DX)|'
    r'(?:NC\s*AI|엔씨\s*AI).{0,80}(?:POSCO\s*DX|포스코DX).{0,80}(?:MOU|공동개발))',
    re.I,
)
RFM_MODEL_RELEASE = re.compile(
    r'(?:RFM|robot\s*foundation\s*model|로봇\s*파운데이션\s*모델|π0|pi0|GR00T).{0,100}(?:released|launched|공개|출시|오픈소스|weights|checkpoint)|'
    r'(?:released|launched|공개|출시|오픈소스).{0,80}(?:RFM|robot\s*foundation\s*model|π0|pi0|GR00T)',
    re.I,
)
RFM_BENCHMARK = re.compile(
    r'(?:cross[-\s]*embodiment|different\s+robot|multiple\s+robot|다종\s*로봇|서로\s*다른\s*로봇).{0,160}(?:success\s*rate|benchmark|성공률|벤치마크|\d+(?:\.\d+)?\s*%)|'
    r'(?:success\s*rate|benchmark|성공률|벤치마크).{0,160}(?:cross[-\s]*embodiment|different\s+robot|multiple\s+robot|다종\s*로봇)',
    re.I,
)
RFM_MULTI_ROBOT = re.compile(
    r'(?:humanoid|휴머노이드).{0,100}(?:quadruped|사족|robot\s*arm|로봇팔)|'
    r'(?:quadruped|사족).{0,100}(?:humanoid|휴머노이드|robot\s*arm|로봇팔)|'
    r'(?:2|two|두)\s*(?:종|types?).{0,40}(?:robot|로봇)',
    re.I,
)
RFM_FIELD = re.compile(r'factory|industrial\s*site|production\s*site|현장|공장|산업\s*현장|pilot|실증|deployment|배치', re.I)
RFM_COMMERCIAL = re.compile(r'customer|고객|contract|계약|license|라이선스|paid|유료|commercial|상용|order|수주', re.I)
RFM_MEASURED = re.compile(r'success\s*rate|성공률|latency|지연|benchmark|벤치마크|\d+(?:\.\d+)?\s*%', re.I)
RFM_EXPLAINER = re.compile(r'부상|떠오르|경쟁\s*본격화|전망|주목|핵심\s*기술|what\s+is|explainer|overview', re.I)

AGILITY_ID = re.compile(r'Agility\s*Robotics|애질리티\s*로보틱스|Jonathan\s*Hurst|조너선\s*허스트', re.I)
AGILITY_WHEEL = re.compile(r'wheeled|wheels?|wheel[-\s]*base|바퀴형|바퀴|휠|wheeled\s*base', re.I)
AGILITY_CONCEPT = re.compile(r'explor|consider|concept|render|animation|illustrative|검토|컨셉|개념|렌더|애니메이션|가능성|구상', re.I)
AGILITY_PROTOTYPE = re.compile(r'physical\s*prototype|working\s*prototype|prototype.{0,30}(?:shown|unveiled|demonstrated)|실물\s*시제품|시제품.{0,30}(?:공개|시연)', re.I)
AGILITY_PRODUCT = re.compile(r'(?:product\s*name|named|specification|specs?|제품명|사양).{0,50}(?:wheeled|wheel|바퀴|휠)|(?:wheeled|wheel|바퀴|휠).{0,50}(?:제품명|사양|specification|specs?)', re.I)
AGILITY_LAUNCH = re.compile(r'(?:wheeled|wheel|바퀴|휠).{0,80}(?:launched|released|available|orderable|출시|판매\s*개시|주문\s*가능)', re.I)
AGILITY_CUSTOMER = re.compile(
    r'(?:wheeled|wheel|바퀴|휠).{0,140}(?:first\s+customer|customer\s+(?:selected|named|deployment)|contract\s+(?:signed|awarded)|order\s+(?:received|booked)|deployed|deployment\s+(?:started|began)|'
    r'첫\s*고객|고객\s*(?:선정|확정)|계약\s*(?:체결|수주)|수주\s*(?:확보|완료)|배치\s*(?:시작|개시))',
    re.I,
)
AGILITY_NEGATIVE = re.compile(
    r'no\s+(?:product|prototype|launch\s+date|price|customer)|not\s+(?:a\s+)?(?:product|prototype)|'
    r'has\s+not\s+announced|not\s+announced|미확정|제품\s*아님|시제품\s*아님|출시일\s*없|고객\s*없|발표하지\s*않',
    re.I,
)
AGILITY_MASS = re.compile(r'(?:wheeled|wheel|바퀴|휠).{0,120}(?:mass\s*production|series\s*production|양산|production\s*start|생산\s*개시)', re.I)


def _samhyun_stage(text: str) -> str:
    if SAMHYUN_REPEAT_ORDER.search(text) and not re.search(r'추진|기대|예상|전망|가능성|계획|예정|이어질|목표|검토|hope|expect|plan|possible|potential', text, re.I):
        return 'follow_on_order'
    if SAMHYUN_FIRST_SHIPMENT.search(text) and not re.search(r'예정|계획|오는\s*12월|12월부터|will\s+(?:start|begin)|scheduled', text, re.I):
        return 'first_shipment'
    if SAMHYUN_INITIAL_MASS_ORDER.search(text):
        return 'initial_mass_production_order'
    if SAMHYUN_CAPA.search(text):
        return 'capacity_ramp'
    if SAMHYUN_PROTO.search(text):
        return 'prototype_award'
    return 'pipeline'


def _xpeng_stage(text: str) -> str:
    if not (XPENG_ID.search(text) and XPENG_IRON.search(text)):
        return ''
    if XPENG_DELAY.search(text):
        return 'schedule_delay'
    if XPENG_SUPPLIER_20260922_BASELINE.search(text):
        return 'supplier_20260922_baseline'
    if XPENG_GLOBAL_DELIVERY.search(text):
        return 'global_delivery'
    if XPENG_CHINA_DELIVERY.search(text):
        return 'china_delivery'
    if XPENG_PLATFORM_LAUNCH.search(text) and not XPENG_PLAN_ONLY.search(text):
        return 'commercial_platform_launch'
    if XPENG_ACTUAL_SOP.search(text) and not XPENG_PLAN_ONLY.search(text):
        return 'mass_production_start'
    if XPENG_SUPPLIER_NOMINATION.search(text):
        return 'supplier_nomination'
    if XPENG_SUPPLIER_AUDIT.search(text):
        return 'supplier_audit'
    if XPENG_LINE_BASELINE.search(text):
        return 'line_commissioned_baseline'
    if XPENG_PLAN_ONLY.search(text) and re.search(r'2026|2027|12月|12월|Q1|Q2|Q4|1분기|2분기|4분기', text, re.I):
        return 'schedule_baseline'
    return 'background'


def _rfm_stage(text: str, source: str = '') -> str:
    if not RFM_ID.search(text):
        return ''
    if RFM_BASELINE.search(text) or (RFM_EXPLAINER.search(text) and not (RFM_FIELD.search(text) or RFM_COMMERCIAL.search(text) or RFM_BENCHMARK.search(text))):
        return 'baseline'
    if RFM_COMMERCIAL.search(text) and (RFM_FIELD.search(text) or RFM_MULTI_ROBOT.search(text)):
        return 'commercial'
    if RFM_FIELD.search(text) and (RFM_MULTI_ROBOT.search(text) or RFM_MEASURED.search(text)):
        return 'field_pilot'
    if RFM_BENCHMARK.search(text):
        return 'cross_embodiment_benchmark'
    if RFM_MODEL_RELEASE.search(text) and source in base.OFFICIAL_OR_PRIMARY:
        return 'model_release'
    return 'background'


def _agility_stage(text: str) -> str:
    if not (AGILITY_ID.search(text) and AGILITY_WHEEL.search(text)):
        return ''
    if AGILITY_NEGATIVE.search(text) and AGILITY_CONCEPT.search(text):
        return 'concept'
    if AGILITY_MASS.search(text):
        return 'mass_production'
    if AGILITY_CUSTOMER.search(text):
        return 'customer_deployment'
    if AGILITY_LAUNCH.search(text):
        return 'product_launch'
    if AGILITY_PRODUCT.search(text):
        return 'product_spec'
    if AGILITY_PROTOTYPE.search(text):
        return 'prototype'
    if AGILITY_CONCEPT.search(text):
        return 'concept'
    return 'background'


GEMINI_PLATFORM = re.compile(r'Google\s*DeepMind|DeepMind|Gemini\s*Robotics', re.I)
GEMINI_PLATFORM_SIGNAL = re.compile(
    r'new\s+(?:research\s+|hardware\s+)?partner|announc(?:ed|es)?\s+(?:a\s+)?(?:new\s+)?partnership|'
    r'general\s+availability|generally\s+available|public\s+API|pricing|license\s+agreement|'
    r'customer\s+deployment|production\s+deployment|'
    r'신규\s*파트너|새\s*파트너|파트너십\s*(?:체결|발표)|정식\s*출시|공개\s*API|가격\s*공개|사용권\s*계약|고객\s*배치|양산\s*배치',
    re.I,
)
GEMINI_CURRENT_BASELINE = re.compile(
    r'intelligence\s*layer|100\+?\s*(?:trusted\s*)?testers|'
    r'Agile\s*Robots|Apptronik|Boston\s*Dynamics|'
    r'Gemini\s*Robotics\s*2|Gemini\s*Robotics\s*ER\s*2|Gemini\s*Robotics\s*On[-\s]*Device\s*2',
    re.I,
)
GEMINI_GA = re.compile(r'general\s+availability|generally\s+available|\bGA\b|정식\s*출시|일반\s*공개', re.I)
GEMINI_PUBLIC_PREVIEW = re.compile(r'public\s+preview|공개\s*프리뷰|퍼블릭\s*프리뷰', re.I)
GEMINI_PRIVATE_PREVIEW = re.compile(r'private\s+preview|early[-\s]*access|trusted\s*tester|select\s+group|프라이빗\s*프리뷰|얼리\s*액세스|신뢰\s*테스터', re.I)
GEMINI_PUBLIC_API = re.compile(r'public\s+API|Gemini\s+API|Google\s+AI\s+Studio|공개\s*API', re.I)
GEMINI_ER2 = re.compile(r'Gemini\s*Robotics\s*ER\s*2', re.I)
GEMINI_VLA2 = re.compile(r'Gemini\s*Robotics\s*2(?!\s*ER|\s*On[-\s]*Device)', re.I)
GEMINI_ON_DEVICE2 = re.compile(r'Gemini\s*Robotics\s*On[-\s]*Device\s*2', re.I)
GEMINI_COMMERCIAL = re.compile(r'pricing|paid|commercial\s+contract|license\s+agreement|customer\s+deployment|production\s+deployment|가격\s*공개|유료|상용\s*계약|사용권\s*계약|고객\s*배치|양산\s*배치', re.I)
GEMINI_NEW_PARTNER = re.compile(r'new\s+(?:research\s+|hardware\s+)?partner|announc(?:ed|es)?\s+(?:a\s+)?(?:new\s+)?partnership|신규\s*파트너|새\s*파트너|파트너십\s*(?:체결|발표)', re.I)


def _gemini_current_preview_baseline(text: str) -> bool:
    er2_public = bool(
        GEMINI_ER2.search(text)
        and (GEMINI_PUBLIC_PREVIEW.search(text) or GEMINI_PUBLIC_API.search(text))
        and not GEMINI_GA.search(text)
    )
    vla_private = bool(GEMINI_VLA2.search(text) and GEMINI_PRIVATE_PREVIEW.search(text))
    ondevice_private = bool(GEMINI_ON_DEVICE2.search(text) and GEMINI_PRIVATE_PREVIEW.search(text))
    return er2_public or vla_private or ondevice_private


def _gemini_preview_expansion(text: str) -> bool:
    # Current baseline: ER 2 is already in public preview / Gemini API; the VLA
    # and On-Device 2 models are still private-preview / early-access. Alert only
    # when those latter models materially widen access or ER 2 advances beyond
    # its current public-preview state.
    if _gemini_current_preview_baseline(text):
        return False
    if (GEMINI_VLA2.search(text) or GEMINI_ON_DEVICE2.search(text)) and (
        GEMINI_PUBLIC_PREVIEW.search(text) or GEMINI_PUBLIC_API.search(text)
    ):
        return True
    return False


def _gemini_platform_stage(text: str) -> str:
    if not (GEMINI_PLATFORM.search(text) and re.search(r'robotics|robot|humanoid|로봇|휴머노이드', text, re.I)):
        return ''
    if GEMINI_COMMERCIAL.search(text):
        return 'commercial'
    if GEMINI_GA.search(text):
        return 'ga'
    if _gemini_preview_expansion(text):
        return 'preview_expansion'
    if GEMINI_NEW_PARTNER.search(text):
        return 'new_partner'
    if _gemini_current_preview_baseline(text) or GEMINI_CURRENT_BASELINE.search(text):
        return 'baseline'
    return 'monitor'


def topic_group(text: str) -> str | None:
    if _gemini_platform_stage(text) in {'new_partner','preview_expansion','ga','commercial'}:
        return 'frontier_ai'
    if re.search(r'삼현|SAMHYUN', text, re.I) and re.search(r'휴머노이드|humanoid|로봇|robot|액추에이터|actuator', text, re.I):
        return 'samhyun'
    if XPENG_ID.search(text) and XPENG_IRON.search(text):
        return 'xpeng'
    if RFM_ID.search(text):
        return 'rfm_general_intelligence'
    if AGILITY_ID.search(text) and AGILITY_WHEEL.search(text):
        return 'agility_platform'
    if re.search(r'LG전자|LG Electronics|베어로보틱스|Bear Robotics', text, re.I) and re.search(r'AXIUM|악시움|액추에이터|actuator|베어로보틱스|Bear Robotics|상장|IPO|프리IPO|pre-IPO', text, re.I):
        return 'lg_robotics'
    if re.search(r'GPT-6\s*Astra|OpenAI|Gemini Robotics|frontier AI|프런티어\s*AI', text, re.I):
        robot = re.search(r'robotics|로보틱스|robot|로봇|humanoid|휴머노이드|embodied AI|피지컬\s*AI', text, re.I)
        action = re.search(r'planning|reasoning|action\s*model|행동\s*모델|VLA|RFM|robot\s*foundation\s*model|배치|deployment|integration|통합|제어', text, re.I)
        if robot and action:
            return 'frontier_ai'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    source = item.get('source') or ''

    if group == 'samhyun':
        s = 10
        stage = _samhyun_stage(text)
        if base.NUMERIC.search(text): s += 3
        if re.search(r'20\s*(?:곳|개|companies)|20곳\s*이상', text, re.I): s += 4
        if stage == 'prototype_award': s += 5
        if stage == 'capacity_ramp': s += 6
        if stage == 'initial_mass_production_order': s += 14
        if stage == 'first_shipment': s += 15
        if stage == 'follow_on_order': s += 16
        if re.search(r'AXLON|액슬론|3[-\s]*in[-\s]*1|12종|북미|North\s*America', text, re.I): s += 4
        if source in base.OFFICIAL_OR_PRIMARY: s += 5
        elif source in base.TRUSTED: s += 2
        return s

    if group == 'xpeng':
        stage = _xpeng_stage(text)
        if stage in {'line_commissioned_baseline', 'supplier_20260922_baseline', 'schedule_baseline', 'background'}:
            return 0
        s = 18
        if base.NUMERIC.search(text): s += 3
        s += {
            'supplier_audit': 8,
            'supplier_nomination': 12,
            'mass_production_start': 16,
            'commercial_platform_launch': 13,
            'china_delivery': 16,
            'global_delivery': 18,
            'schedule_delay': 14,
        }.get(stage, 0)
        if source in base.OFFICIAL_OR_PRIMARY: s += 6
        elif source in base.TRUSTED: s += 3
        return s

    if group == 'rfm_general_intelligence':
        stage = _rfm_stage(text, source)
        if stage in {'baseline', 'background'}:
            return 0
        s = 17
        if base.NUMERIC.search(text): s += 3
        s += {
            'model_release': 8,
            'cross_embodiment_benchmark': 12,
            'field_pilot': 14,
            'commercial': 17,
        }.get(stage, 0)
        if source in base.OFFICIAL_OR_PRIMARY: s += 7
        elif source in base.TRUSTED: s += 3
        return s

    if group == 'agility_platform':
        stage = _agility_stage(text)
        if stage in {'concept', 'background'}:
            return 0
        s = 17
        s += {
            'prototype': 8,
            'product_spec': 9,
            'product_launch': 13,
            'customer_deployment': 16,
            'mass_production': 17,
        }.get(stage, 0)
        if source in base.OFFICIAL_OR_PRIMARY: s += 7
        elif source in base.TRUSTED: s += 3
        return s

    if group == 'lg_robotics':
        s = 10
        if base.NUMERIC.search(text): s += 3
        if re.search(r'AXIUM|악시움|액추에이터|actuator', text, re.I): s += 3
        if re.search(r'빅테크|Big Tech|10월|October|수주|공급|고객|양산|mass production', text, re.I): s += 5
        if re.search(r'베어로보틱스|Bear Robotics', text, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥|결정된\s*바\s*없', text, re.I): s += 4
        if source in base.OFFICIAL_OR_PRIMARY: s += 4
        elif source in base.TRUSTED: s += 2
        return s

    if group == 'frontier_ai':
        gemini_stage = _gemini_platform_stage(text)
        if gemini_stage == 'baseline':
            return 0
        if gemini_stage in {'new_partner','preview_expansion','ga','commercial'}:
            s = 18 + {'new_partner': 10, 'preview_expansion': 11, 'ga': 12, 'commercial': 15}[gemini_stage]
            if source in base.OFFICIAL_OR_PRIMARY: s += 7
            elif source in base.TRUSTED: s += 3
            return s
        # A model launch by itself is NOT a robot signal. Require an explicit
        # robot action/planning/deployment/integration link in the story text.
        robot = re.search(r'robotics|로보틱스|robot|로봇|humanoid|휴머노이드|embodied AI|피지컬\s*AI', text, re.I)
        action = re.search(r'planning|reasoning|action\s*model|행동\s*모델|VLA|RFM|robot\s*foundation\s*model|배치|deployment|integration|통합|제어', text, re.I)
        if not (robot and action):
            return -30
        s = 9
        if re.search(r'실제\s*로봇|real[- ]world|현장|deployment|배치|통합|integration|채택|adopt', text, re.I): s += 5
        if re.search(r'성공률|success rate|비용|cost|latency|지연|benchmark|벤치마크', text, re.I): s += 3
        if source in base.OFFICIAL_OR_PRIMARY or source in base.TRUSTED: s += 3
        return s

    return _orig_score(item)


def _raw_cat(text: str, group: str) -> str:
    if group == 'samhyun':
        stage = _samhyun_stage(text)
        if stage == 'follow_on_order':
            return '후속 양산 발주·물량 확대'
        if stage == 'first_shipment':
            return '첫 양산 출하·공급 개시'
        if stage == 'initial_mass_production_order':
            return '글로벌 휴머노이드 초도 양산 수주'
        if stage == 'capacity_ramp':
            return '생산능력·양산 준비'
        return '고객 파이프라인·양산 프로토타입'
    if group == 'xpeng':
        return {
            'supplier_audit': 'IRON 공급망 양산심사',
            'supplier_nomination': 'IRON 핵심부품 공급사 선정',
            'mass_production_start': 'IRON 실제 양산 개시',
            'commercial_platform_launch': 'IRON 상용 플랫폼 출시',
            'china_delivery': 'IRON 중국 고객 인도 개시',
            'global_delivery': 'IRON 해외 고객 인도 개시',
            'schedule_delay': 'IRON 양산·인도 일정 지연',
        }.get(_xpeng_stage(text), 'IRON 생산라인·양산 전환')
    if group == 'rfm_general_intelligence':
        return {
            'model_release': '범용 RFM 신규 모델 공개',
            'cross_embodiment_benchmark': '크로스 임바디먼트 정량 검증',
            'field_pilot': 'RFM 다종 로봇 현장 실증',
            'commercial': 'RFM 고객·계약 상용화',
        }.get(_rfm_stage(text), '범용 RFM 산업 구조')
    if group == 'agility_platform':
        return {
            'prototype': '바퀴형 플랫폼 실물 시제품',
            'product_spec': '바퀴형 플랫폼 제품·사양 확정',
            'product_launch': '바퀴형 플랫폼 정식 출시',
            'customer_deployment': '바퀴형 플랫폼 첫 고객·배치',
            'mass_production': '바퀴형 플랫폼 양산 개시',
        }.get(_agility_stage(text), '바퀴형 플랫폼 검토')
    if group == 'lg_robotics':
        if re.search(r'베어로보틱스|Bear Robotics', text, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥', text, re.I):
            return '베어로보틱스 가치·상장 상태'
        return 'AXIUM 고객·수주 전환'
    if group == 'frontier_ai':
        gemini_stage = _gemini_platform_stage(text)
        if gemini_stage == 'new_partner':
            return 'Gemini Robotics 신규 하드웨어 파트너'
        if gemini_stage == 'preview_expansion':
            return 'Gemini Robotics 모델 공개 범위 확대'
        if gemini_stage == 'ga':
            return 'Gemini Robotics 모델·API 일반 공개'
        if gemini_stage == 'commercial':
            return 'Gemini Robotics 유료계약·상용 배치'
        return '프런티어AI→로봇 지능'
    return _orig_category(text, group).split(' · ', 1)[-1]


def _lane(group: str) -> str:
    return {
        'samhyun': '삼현',
        'xpeng': '샤오펑 IRON',
        'rfm_general_intelligence': '범용 로봇 지능',
        'agility_platform': 'Agility Robotics',
        'lg_robotics': 'LG 로보틱스',
        'frontier_ai': '프런티어 AI',
    }.get(group, '')


def category(text: str, group: str) -> str:
    if group in {'samhyun','xpeng','rfm_general_intelligence','agility_platform','lg_robotics','frontier_ai'}:
        return f"{_lane(group)} · {_raw_cat(text, group)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        '고객 파이프라인·양산 프로토타입': '삼현이 단순 샘플 협의를 넘어 양산 프로토타입 계약과 다수 글로벌 고객 파이프라인을 확보하는지 봅니다. 4건의 Award가 실제 양산 수주·납품 물량으로 전환되는지가 핵심입니다.',
        '생산능력·양산 준비': '고객 요청에 앞서 액추에이터·모터 생산능력을 선제 확대하는 단계입니다. 가동률과 수율이 동반되면 외부 휴머노이드 OEM 주문을 빠르게 매출로 전환할 수 있습니다.',
        '글로벌 휴머노이드 초도 양산 수주': '삼현이 프로토타입·고객 검증 단계를 넘어 실제 글로벌 휴머노이드 고객사의 초도 양산 물량을 확보한 단계 변화입니다. 고객 실명·수량·단가는 NDA로 비공개이므로 12월 첫 출하와 후속 발주가 실제 매출 규모를 가르는 다음 확인점입니다.',
        '첫 양산 출하·공급 개시': '양산 수주가 실제 출하와 매출 인식으로 넘어가는 단계입니다. 출하 수량·인식 매출·초기 수율·불량률·고객 재주문을 함께 확인합니다.',
        '후속 양산 발주·물량 확대': '초도 공급이 반복 주문으로 전환돼 고객 검증이 상업적 확대로 이어지는 가장 강한 신호입니다. 후속 발주 규모와 납기, 생산라인 가동률을 확인합니다.',
        'IRON 생산라인·양산 전환': '샤오펑 IRON 생산라인 가동은 이미 기준선입니다. 앞으로 공급망 심사·핵심부품 공급사 선정→실제 양산→상용 플랫폼→중국·해외 고객 인도처럼 상태가 한 단계씩 바뀌는지만 추적합니다.',
        'IRON 공급망 양산심사': '생산라인 구축에서 공급망 양산 검증으로 이동하는 단계입니다. 액추에이터·로봇핸드·센서·AI칩 업체의 심사 통과와 실제 생산배정이 뒤따르는지 확인합니다.',
        'IRON 핵심부품 공급사 선정': '공급망 후보가 실제 지정 공급사로 좁혀지는 매출 선행 신호입니다. 공급사 실명·부품·배정 물량·납기와 실제 출하를 확인합니다.',
        'IRON 실제 양산 개시': '연말 양산 목표가 실제 SOP로 전환된 단계입니다. 월 생산량·직행수율·재작업률과 내부·외부 배치대수를 확인합니다.',
        'IRON 상용 플랫폼 출시': '로봇 생산 자체를 넘어 외부 고객이 사용할 상용 제품·소프트웨어 플랫폼이 실제 출시되는 신호입니다. 가격·사용권·서비스 범위와 고객 계약을 확인합니다.',
        'IRON 중국 고객 인도 개시': '내부 생산에서 중국 외부 고객 매출로 넘어가는 첫 실수요 신호입니다. 고객 실명·인도 대수·평균판매단가·반복 주문을 추적합니다.',
        'IRON 해외 고객 인도 개시': '중국 내 상용화가 해외 수출·배치로 확장되는 신호입니다. 국가별 인증·서비스망·판매가격·초기 가동률을 함께 봅니다.',
        'IRON 양산·인도 일정 지연': '기존 12월 양산·2027년 중국/해외 인도 시간표가 뒤로 밀리는 역방향 신호입니다. 수율·부품·AI·인증 중 지연 원인을 구분합니다.',
        '범용 RFM 신규 모델 공개': '일반 설명이나 기존 Open X-Embodiment 재인용이 아니라 실제 신규 RFM/정책 모델이 공개되는 신호입니다. 지원 로봇 종류·가중치 공개·추론비용·성능을 확인합니다.',
        '크로스 임바디먼트 정량 검증': '한 로봇에서 다른 로봇으로 지능을 옮길 때 성공률이 실제로 개선되는지 숫자로 확인하는 핵심 기술 신호입니다. 로봇 종류별 성능·미세조정 데이터량·실환경 재현성을 봅니다.',
        'RFM 다종 로봇 현장 실증': '휴머노이드·사족·로봇팔 등 둘 이상의 형태가 같은 RFM을 실제 산업현장에서 공유하는지 확인하는 단계입니다. 작업 성공률·사람 개입률·전환시간을 추적합니다.',
        'RFM 고객·계약 상용화': 'RFM 연구개발이 고객계약·사용권·유료 배치로 전환되는 매출 신호입니다. 고객 실명·로봇 대수·계약금액·사용권 갱신 구조를 확인합니다.',
        '바퀴형 플랫폼 실물 시제품': 'Digit 5 영상 속 렌더를 넘어 실제 작동하는 바퀴형 시제품이 공개되는 단계입니다. 적재량·속도·배터리·안전성·공용 부품률을 확인합니다.',
        '바퀴형 플랫폼 제품·사양 확정': '검토 중인 폼팩터가 제품명과 사양을 가진 상용 후보로 구체화되는 신호입니다. 기존 Digit와 AI·손·상체·서비스 부품을 얼마나 공유하는지 봅니다.',
        '바퀴형 플랫폼 정식 출시': '바퀴형 컨셉이 실제 주문 가능한 제품으로 전환되는 신호입니다. 가격·납기·서비스 계약·생산능력을 확인합니다.',
        '바퀴형 플랫폼 첫 고객·배치': '제품화가 제조·물류 고객의 실제 계약과 현장 배치로 이어지는 가장 강한 수요 검증 신호입니다. 고객 실명·대수·가동률·반복 주문을 확인합니다.',
        '바퀴형 플랫폼 양산 개시': '시제품에서 반복 가능한 제조로 넘어가는 단계입니다. 월 생산량·수율·공용 부품률·가동률과 주문잔고를 확인합니다.',
        'AXIUM 고객·수주 전환': 'LG전자가 AXIUM을 기술 공개 단계에서 글로벌 고객 수주 단계로 옮기는 신호입니다. 10월 빅테크 기술·생산 미팅 이후 고객 실명·계약 물량이 나오는지가 핵심입니다.',
        '베어로보틱스 가치·상장 상태': '베어로보틱스의 외부 가치평가·자금조달·상장 상태가 LG전자 로봇 자산의 시장가치 기준점으로 작용할 수 있습니다.',
        'Gemini Robotics 신규 하드웨어 파트너': '기존 Agile Robots·Apptronik·Boston Dynamics 밖의 새 로봇 제조사가 Gemini Robotics를 채택하면 Android식 지능 레이어의 하드웨어 커버리지가 실제로 넓어지는 신호입니다. 로봇 모델명, 탑재 모델, 고객 검증·유료 여부를 확인합니다.',
        'Gemini Robotics 모델 공개 범위 확대': '현재 ER 2는 Google AI Studio·Gemini API의 공개 프리뷰, VLA와 On-Device 2는 프라이빗 프리뷰·얼리액세스가 기준선입니다. VLA·On-Device가 공개 프리뷰/API로 확대되면 개발자·로봇업체의 접근성이 한 단계 올라가는 신호입니다.',
        'Gemini Robotics 모델·API 일반 공개': '현재 얼리액세스·프라이빗 프리뷰 범위를 넘어 VLA·On-Device·API가 일반 기업에 공개되는 상용화 단계입니다. 가격, 사용권, 온디바이스 요구사양과 반복 사용료 구조를 확인합니다.',
        'Gemini Robotics 유료계약·상용 배치': '연구 파트너십이 실제 고객 계약·생산현장 배치·사용권 매출로 전환되는 가장 중요한 수익화 신호입니다. 고객 실명, 로봇 대수, 계약금액과 반복매출을 확인합니다.',
        '프런티어AI→로봇 지능': '프런티어 모델 자체 성능이 아니라 실제 로봇의 계획·추론·행동모델·현장 배치에 연결되는지를 봅니다. 로봇 성공률·시도비용·지연시간이 개선될 때만 구조 변화로 판단합니다.',
    }
    return mapping.get(raw, _orig_meaning(cat))


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        '고객 파이프라인·양산 프로토타입': '프로토타입 계약은 대량 양산 계약과 다릅니다. 고객 실명·단가·납기·반복 발주와 실제 양산 수주 전환을 확인해야 합니다.',
        '생산능력·양산 준비': '증설이 주문보다 앞서면 가동률·감가상각 부담이 먼저 커질 수 있습니다. 생산능력보다 실제 양산 수주가 더 중요합니다.',
        '글로벌 휴머노이드 초도 양산 수주': '수주금액·공급수량·고객명이 NDA로 비공개라 실적 민감도를 아직 계산할 수 없습니다. 가장 현실적인 실패 경로는 12월 초도 공급 이후 수율·품질 또는 고객 일정 문제로 후속 발주가 늦어지는 경우입니다.',
        '첫 양산 출하·공급 개시': '첫 출하는 안정 양산과 다릅니다. 초기 수율·재작업·반품·교환 접수와 보증비용이 높으면 매출 증가보다 원가 부담이 먼저 나타날 수 있습니다.',
        '후속 양산 발주·물량 확대': '반복 발주가 한 고객에 집중되면 고객 의존도가 커질 수 있습니다. 복수 고객사 양산 전환과 평균판매단가·마진 유지 여부를 같이 봅니다.',
        'IRON 생산라인·양산 전환': '생산라인 가동과 대량 판매는 다릅니다. 기존 80%+ 자동화율은 직행수율이 아니므로 실제 월 생산량·재작업률·인도 대수를 확인합니다.',
        'IRON 공급망 양산심사': '심사 완료가 곧 양산매출은 아닙니다. 부품사별 수율·품질·원가가 기준을 못 맞추면 공급사 재선정과 SOP 지연이 발생할 수 있습니다.',
        'IRON 핵심부품 공급사 선정': '공급사 지정 뒤에도 배정 물량·단가·실제 출하가 확인되지 않으면 실적 민감도를 확정할 수 없습니다. 익명 공급사를 임의로 특정하지 않습니다.',
        'IRON 실제 양산 개시': 'SOP와 안정 양산은 다릅니다. 초기 수율·재작업·반품·안전 검증이 나쁘면 생산량 확대가 지연될 수 있습니다.',
        'IRON 상용 플랫폼 출시': '플랫폼 출시가 유료 고객 채택을 보장하지 않습니다. 가격·기능 제한·지원 비용과 실제 계약을 확인합니다.',
        'IRON 중국 고객 인도 개시': '첫 인도는 반복 수요가 아닙니다. 고객별 PoC인지 본구매인지와 재주문·가동률을 분리합니다.',
        'IRON 해외 고객 인도 개시': '해외 인증·원격지원·부품 서비스·보험 비용이 높으면 중국 내 경제성이 그대로 재현되지 않을 수 있습니다.',
        'IRON 양산·인도 일정 지연': '일정 지연은 생산 수율·부품 공급·AI 범용화·인증 중 어느 병목인지 분리해야 합니다. 새 일정과 원인을 확인할 때만 재평가합니다.',
        '범용 RFM 신규 모델 공개': '모델 공개만으로 범용성이 입증되지는 않습니다. 특정 벤치마크 과적합이나 데모 선택 편향이 있을 수 있어 다종 로봇 실환경 성능이 필요합니다.',
        '크로스 임바디먼트 정량 검증': '평균 성능 개선이 모든 로봇에 동일하게 적용되지는 않습니다. 로봇별 편차·미세조정 필요량·센서/제어기 차이로 전이효과가 약해질 수 있습니다.',
        'RFM 다종 로봇 현장 실증': '실증 1회와 반복 상용운용은 다릅니다. 작업 성공률·사람 개입률·연속 가동시간·안전성을 확인합니다.',
        'RFM 고객·계약 상용화': 'RFM 계약도 하드웨어 판매 없이 연구개발비·용역에 그칠 수 있습니다. 사용권·반복매출·실제 로봇 배치대수를 분리합니다.',
        '바퀴형 플랫폼 실물 시제품': '시제품 공개가 제품 출시를 보장하지 않습니다. 바퀴형이 기존 Digit 고객의 새로운 수요인지 단순 연구용인지 확인해야 합니다.',
        '바퀴형 플랫폼 제품·사양 확정': '제품군 확대가 개발비·재고·서비스 복잡성을 키울 수 있습니다. 기존 Digit와의 부품 공용률이 낮으면 규모의 경제가 약해질 수 있습니다.',
        '바퀴형 플랫폼 정식 출시': '출시 후에도 주문량이 작으면 별도 생산라인·서비스망 비용이 수익성을 압박할 수 있습니다.',
        '바퀴형 플랫폼 첫 고객·배치': '바퀴형은 평탄한 제조·물류 환경에서는 효율적이지만 계단·복잡 지형에는 적용범위가 좁습니다. 실제 고객 작업범위와 가동률을 확인합니다.',
        '바퀴형 플랫폼 양산 개시': '양산이 기존 Digit 수요를 잠식하거나 부품 공용화가 낮으면 총자산이익률 개선 없이 자산만 늘 수 있습니다.',
        'AXIUM 고객·수주 전환': '현재는 수주 협의 단계이며 특정 빅테크 계약은 아직 확정되지 않았습니다. 10월 미팅 이후 고객 인증·납품 단가·수량을 확인해야 합니다.',
        '베어로보틱스 가치·상장 상태': '상장 보도와 확정 일정은 구분해야 합니다. LG전자는 해외 상장에 대해 결정된 바 없다고 공시한 만큼 실제 이사회·공시·투자조건을 우선합니다.',
        'Gemini Robotics 신규 하드웨어 파트너': '파트너 발표는 실제 양산 탑재·유료계약과 다릅니다. 센서·제어기 차이와 미세조정 데이터, 안전 검증 때문에 특정 로봇에서 범용성이 약해질 수 있습니다.',
        'Gemini Robotics 모델 공개 범위 확대': '공개 프리뷰 확대는 정식 상용화와 다릅니다. 가격·서비스수준협약·지연시간·지원 하드웨어·안전 제한이 확정되지 않으면 실제 생산현장 채택은 늦어질 수 있습니다.',
        'Gemini Robotics 모델·API 일반 공개': 'API 공개가 생산로봇 배치를 보장하지 않습니다. 지연시간·온디바이스 연산비·네트워크 의존성·안전 인증이 채택 속도를 제한할 수 있습니다.',
        'Gemini Robotics 유료계약·상용 배치': '초기 고객 배치가 PoC에 그치면 반복매출이 작을 수 있습니다. 계약 갱신·로봇 대수 확대·작업 성공률·사람 개입률을 확인합니다.',
        '프런티어AI→로봇 지능': 'GPT-6 Astra 같은 모델의 일반 추론 성능만으로 로봇 상용화를 확정할 수 없습니다. 실제 로봇 통합·행동 성공률·지연·안전 검증이 없으면 알림하지 않습니다.',
    }
    return mapping.get(raw, _orig_risk(cat))


def verification(item: dict, group: str, text: str) -> str:
    source = item.get('source') or ''
    if group == 'samhyun':
        stage = _samhyun_stage(text)
        if stage in {'initial_mass_production_order','first_shipment','follow_on_order'}:
            return '삼현 회사 발표 기반 보도 · 고객사·수주액·공급수량은 NDA 비공개 · 공식 공시/첫 출하 후속 확인'
        return 'CEO 간담회·증권사 기반 보도 · 양산 수주 전환 확인 필요'
    if group == 'xpeng':
        stage = _xpeng_stage(text)
        if source in base.OFFICIAL_OR_PRIMARY:
            return 'XPENG 공식자료 · 생산라인/양산/출시/인도 단계 직접 확인'
        if stage in {'supplier_audit','supplier_nomination'}:
            return '澎湃新闻·第一财经 등 공급망 보도 · XPENG/공급사 공식 수주·선정 공시 전'
        return '신뢰 매체 보도 · XPENG 공식 일정과 교차확인'
    if group == 'rfm_general_intelligence':
        if source in base.OFFICIAL_OR_PRIMARY:
            return '기업·연구기관 공식자료 · 모델/벤치마크/현장 적용 직접 확인'
        return '신뢰 매체 보도 · 모델 개발사·고객사 공식자료 교차확인'
    if group == 'agility_platform':
        stage = _agility_stage(text)
        if stage == 'concept':
            return 'The Robot Report의 Jonathan Hurst 직접 답변 · 바퀴형 제품·시제품·출시일은 미확정'
        if source in base.OFFICIAL_OR_PRIMARY:
            return 'Agility Robotics 공식자료'
        return '신뢰 매체 보도 · Agility Robotics 제품/고객 공식자료 교차확인'
    if group == 'lg_robotics':
        if re.search(r'결정된\s*바\s*없', text, re.I):
            return 'LG전자 해명공시 기반'
        if re.search(r'AXIUM|악시움|액추에이터|actuator', text, re.I):
            return 'LG전자 임원 발언·복수 보도 · 계약 전'
    if group == 'frontier_ai':
        return '로봇 적용 근거가 명시된 자료만 통과'
    return _orig_verification(item, group, text)


def same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != b.get('group'):
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    g = a.get('group')
    if g == 'samhyun':
        sa, sb = _samhyun_stage(ta), _samhyun_stage(tb)
        if sa != sb:
            return False
        nums_a = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|대|개|건|월)', ta))
        nums_b = set(re.findall(r'\d[\d,.]*\s*(?:억원|억|만원|원|%|대|개|건|월)', tb))
        if nums_a and nums_b:
            return bool(nums_a.intersection(nums_b))
        return True
    if g == 'xpeng':
        sa, sb = _xpeng_stage(ta), _xpeng_stage(tb)
        return bool(sa and sb and sa == sb)
    if g == 'rfm_general_intelligence':
        sa, sb = _rfm_stage(ta, a.get('source') or ''), _rfm_stage(tb, b.get('source') or '')
        if sa != sb:
            return False
        actors = [
            r'Google\s*DeepMind|DeepMind|Open\s*X[-\s]*Embodiment',
            r'Physical\s*Intelligence|\bπ0\b|\bpi0\b',
            r'NVIDIA|GR00T',
            r'NC\s*AI|엔씨\s*AI|POSCO\s*DX|포스코DX',
        ]
        return any(re.search(p, ta, re.I) and re.search(p, tb, re.I) for p in actors) or sa in {'cross_embodiment_benchmark','field_pilot','commercial'}
    if g == 'frontier_ai':
        sa, sb = _gemini_platform_stage(ta), _gemini_platform_stage(tb)
        if sa in {'new_partner','preview_expansion','ga','commercial'} or sb in {'new_partner','preview_expansion','ga','commercial'}:
            return bool(sa and sb and sa == sb)
    if g == 'agility_platform':
        sa, sb = _agility_stage(ta), _agility_stage(tb)
        return bool(sa and sb and sa == sb)
    if g == 'lg_robotics':
        ax_a = re.search(r'AXIUM|악시움|액추에이터|actuator', ta, re.I)
        ax_b = re.search(r'AXIUM|악시움|액추에이터|actuator', tb, re.I)
        if ax_a and ax_b and re.search(r'빅테크|Big Tech|10월|October|수주', ta, re.I) and re.search(r'빅테크|Big Tech|10월|October|수주', tb, re.I):
            return True
        bear_a = re.search(r'베어로보틱스|Bear Robotics', ta, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥', ta, re.I)
        bear_b = re.search(r'베어로보틱스|Bear Robotics', tb, re.I) and re.search(r'상장|IPO|프리IPO|pre-IPO|Nasdaq|나스닥', tb, re.I)
        if bear_a and bear_b:
            return True
    return False


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    group = base.topic_group(text)
    if group == 'samhyun':
        stage = _samhyun_stage(text)
        return hashlib.sha256(f'samhyun|humanoid-actuator|{stage}'.encode()).hexdigest()
    if group == 'xpeng':
        stage = _xpeng_stage(text)
        return hashlib.sha256(f'xpeng|iron|{stage}'.encode()).hexdigest()
    if group == 'rfm_general_intelligence':
        stage = _rfm_stage(text, item.get('source') or '')
        actor = 'generic'
        for name, pat in [
            ('deepmind', r'Google\s*DeepMind|DeepMind|Open\s*X[-\s]*Embodiment'),
            ('physical-intelligence', r'Physical\s*Intelligence|\bπ0\b|\bpi0\b'),
            ('nvidia', r'NVIDIA|GR00T'),
            ('ncai-poscodx', r'NC\s*AI|엔씨\s*AI|POSCO\s*DX|포스코DX'),
        ]:
            if re.search(pat, text, re.I):
                actor = name
                break
        return hashlib.sha256(f'rfm|{actor}|{stage}'.encode()).hexdigest()
    if group == 'agility_platform':
        stage = _agility_stage(text)
        return hashlib.sha256(f'agility|wheeled-platform|{stage}'.encode()).hexdigest()
    if group == 'frontier_ai':
        stage = _gemini_platform_stage(text)
        if stage in {'new_partner','preview_expansion','ga','commercial'}:
            partners = ','.join(sorted(set(re.findall(r'Agility\s*Robotics|Figure\s*AI|Unitree|ROBOTIS|로보티즈|Boston\s*Dynamics|Apptronik|Agile\s*Robots', text, re.I)))) or 'generic'
            return hashlib.sha256(f'gemini-robotics-platform|{stage}|{partners}'.encode()).hexdigest()
    return _orig_key(item)


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    candidates = items if force else [x for x in items if x['key'] not in seen]
    candidates = ext._dedupe_events(candidates)
    if not candidates:
        return []
    chosen: list[dict] = []
    used: set[str] = set()
    priority = ['tesla','xpeng','global_battery_capacity','solid_state_material','rfm_general_intelligence','agility_platform','samhyun','lg_robotics','robotis','battery','ess_battery','frontier_ai','wonik','byd_paxini']
    for group in priority:
        for x in candidates:
            if x.get('group') == group and x['key'] not in used:
                chosen.append(x); used.add(x['key']); break
        if len(chosen) >= limit:
            return chosen
    for x in candidates:
        if x['key'] in used:
            continue
        chosen.append(x); used.add(x['key'])
        if len(chosen) >= limit:
            break
    return chosen

# Dynamic hooks used by base.main() and ext._dedupe_events().
ext._same_event = same_event
base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.key = key
base.select_diverse = select_diverse

if __name__ == '__main__':
    base.main()

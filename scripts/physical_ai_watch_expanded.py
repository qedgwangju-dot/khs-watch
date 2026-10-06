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
    '("FieldAI" OR "Field AI") (funding OR financing OR valuation OR investor OR "$700 million" OR "$10 billion" OR 투자유치 OR 기업가치 OR 투자자 OR 조달)',
    '("FieldAI" OR "Field AI") (revenue OR contracts OR backlog OR bookings OR customers OR deployments OR ARR OR 매출 OR 계약 OR 수주잔고 OR 고객 OR 배치) (30 OR "$135 million" OR "$100 million" OR expansion OR production OR multi-site OR enterprise OR 확대 OR 신규)',
    '("FieldAI" OR "Field AI") (Hyundai OR 현대차 OR 기아 OR "Boston Dynamics" OR Caterpillar OR Certis OR NVIDIA) (investment OR partnership OR contract OR Atlas OR RMAC OR HMGMA OR deployment OR licensing OR 투자 OR 협력 OR 계약 OR 배치 OR 사용권)',
    '("Jensen Huang" OR "Jensen" OR 젠슨황 OR "젠슨 황") (robotics OR robot OR humanoid OR "physical AI" OR 로보틱스 OR 로봇 OR 휴머노이드 OR 피지컬AI) ("ChatGPT moment" OR "within a year" OR "within 12 months" OR "within two years" OR timeline OR inflection OR "general-purpose brain" OR "general purpose brain" OR "범용 두뇌" OR "1년 이내")',
    '(NVIDIA OR 엔비디아) (robotics OR humanoid OR "physical AI" OR 로보틱스 OR 휴머노이드 OR 피지컬AI) ("general-purpose brain" OR "general purpose brain" OR "ChatGPT moment" OR fleet OR deployment OR production OR shipments OR customers OR "12 months" OR "within a year")',
    '(NVIDIA OR 엔비디아) (Foxconn OR "Hon Hai" OR 폭스콘 OR 홍하이) (GB300 OR NVL72 OR "tester tray" OR 테스터트레이) (robot OR robotics OR automation OR 로봇 OR 자동화) ("95%" OR "99.5%" OR "success rate" OR "cycle time" OR busbar OR connector OR 성공률 OR 수율 OR 사이클타임 OR 버스바 OR 커넥터)',
    '(NVIDIA OR 엔비디아) (Foxconn OR "Hon Hai" OR 폭스콘 OR 홍하이) (Houston OR 휴스턴) (GR00T OR Isaac OR robot OR robotics OR 로봇) (assembly OR manufacturing OR 조립 OR 생산) ("success rate" OR "cycle time" OR 성공률 OR 수율 OR 사이클타임)',
    '("The Machines that Make the Machines" OR "GB300 tester tray") (NVIDIA OR 엔비디아) (Foxconn OR "Hon Hai" OR 폭스콘)',
])

base.TRUSTED.update({
    '이데일리', 'EDAILY', '뉴스핌', 'Investors Business Daily', 'Reuters',
    'The Robot Report', '澎湃新闻', 'The Paper', '第一财经', 'IT之家',
    'Business Insider', '조선비즈', 'ChosunBiz', '연합뉴스', '전자신문',
    'Orange County Business Journal', 'Focus Taiwan', 'Central News Agency', 'CNA', 'Tech Times',
})
base.OFFICIAL_OR_PRIMARY.update({
    'XPENG', 'XPeng', '小鹏汽车', 'LG전자', 'LG Electronics',
    'Google DeepMind', 'DeepMind', 'Physical Intelligence', 'NVIDIA', 'NVIDIA Developer', 'NVIDIA Technical Blog',
    'POSCO DX', '포스코DX', 'NC AI', '엔씨AI', 'Agility Robotics',
    'FieldAI', 'Field AI',
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

FIELD_AI_ID = re.compile(r'\bFieldAI\b|\bField\s+AI\b|Field\s+Foundation\s+Models?', re.I)
FIELD_AI_FUNDING = re.compile(r'funding|financing|fundraise|raise|raised|valuation|투자\s*유치|자금\s*조달|기업\s*가치|밸류에이션', re.I)
FIELD_AI_CURRENT_FUNDING = re.compile(
    r'(?:\$?\s*700\s*million|\$?700M|7\s*억\s*달러).{0,140}(?:\$?\s*10\s*billion|\$?10B|100\s*억\s*달러)|'
    r'(?:\$?\s*10\s*billion|\$?10B|100\s*억\s*달러).{0,140}(?:\$?\s*700\s*million|\$?700M|7\s*억\s*달러)',
    re.I,
)
FIELD_AI_PROPOSED = re.compile(
    r'set\s+to\s+raise|raising|seeking|in\s+talks|proposed|not\s+(?:yet\s+)?(?:closed|finalized)|'
    r'not\s+formally\s+closed|추진\s*중|유치\s*추진|협의\s*중|최종\s*(?:계약|투자).{0,30}(?:전|아니)|확정\s*전',
    re.I,
)
FIELD_AI_CLOSED = re.compile(
    r'funding\s+(?:round\s+)?(?:closed|completed|finalized)|closed\s+(?:a\s+)?(?:funding\s+)?round|'
    r'completed\s+(?:a\s+)?(?:funding\s+)?round|조달\s*(?:완료|종결)|투자\s*유치\s*(?:완료|확정)|납입\s*(?:완료|종료)',
    re.I,
)
FIELD_AI_FUNDING_REVERSE = re.compile(
    r'funding.{0,80}(?:cancel|withdraw|delay|down\s*round|lower\s+valuation)|'
    r'(?:cancel|withdraw|delay|down\s*round|lower\s+valuation).{0,80}funding|'
    r'투자\s*유치.{0,80}(?:취소|철회|지연|연기)|기업\s*가치.{0,40}(?:하향|삭감)',
    re.I,
)
FIELD_AI_CURRENT_COMMERCIAL = re.compile(
    r'(?:\$?\s*135\s*million|\$?135M|1억\s*3500만\s*달러).{0,180}(?:30\+?|30개|30\s*customers?|30\s*clients?)|'
    r'(?:30\+?|30개|30\s*customers?|30\s*clients?).{0,180}(?:\$?\s*135\s*million|\$?135M|1억\s*3500만\s*달러)',
    re.I,
)
FIELD_AI_COMMERCIAL_METRIC = re.compile(
    r'(?:revenue|매출|ARR|bookings?|계약\s*규모|contracted\s+backlog|customer\s+contracts?|수주\s*잔고|수주잔고).{0,100}'
    r'(?:\$\s*\d|\d[\d,.]*\s*(?:million|billion|억\s*달러|만\s*달러))|'
    r'(?:\$\s*\d|\d[\d,.]*\s*(?:million|billion|억\s*달러|만\s*달러)).{0,100}'
    r'(?:revenue|매출|ARR|bookings?|계약\s*규모|contracted\s+backlog|customer\s+contracts?|수주\s*잔고|수주잔고)',
    re.I,
)
FIELD_AI_CUSTOMER_COUNT = re.compile(r'\b\d{2,4}\+?\s*(?:customers?|clients?)\b|\d{2,4}\+?\s*(?:개|곳)\s*(?:고객|고객사)', re.I)
FIELD_AI_HYUNDAI = re.compile(r'Hyundai|현대차|현대자동차|기아|Kia', re.I)
FIELD_AI_ATLAS = re.compile(r'Atlas|아틀라스|RMAC|HMGMA|Robot\s*Metaplant\s*Application\s*Center', re.I)
FIELD_AI_HYUNDAI_STAKE = re.compile(
    r'(?:Hyundai|현대차|현대자동차|기아|Kia).{0,140}(?:follow[-\s]*on\s+investment|additional\s+investment|increased\s+investment|추가\s*투자|후속\s*투자|투자\s*확대)|'
    r'(?:follow[-\s]*on\s+investment|additional\s+investment|increased\s+investment|추가\s*투자|후속\s*투자|투자\s*확대).{0,140}(?:Hyundai|현대차|현대자동차|기아|Kia)|'
    r'(?:Hyundai|현대차|현대자동차|기아|Kia).{0,140}(?:stake|equity|ownership|지분|지분율).{0,80}(?:\d+(?:\.\d+)?\s*%|disclosed|acquired|owns?|공개|확보|취득|보유)|'
    r'(?:\d+(?:\.\d+)?\s*%|disclosed|acquired|owns?|공개|확보|취득|보유).{0,80}(?:stake|equity|ownership|지분|지분율).{0,140}(?:Hyundai|현대차|현대자동차|기아|Kia)',
    re.I,
)
FIELD_AI_HYUNDAI_BASELINE = re.compile(
    r'(?:Hyundai|현대차|현대자동차|기아|Kia).{0,180}(?:financial\s+investment|invested|investment|수백만\s*달러|투자).{0,180}(?:FieldAI|Field\s+AI)|'
    r'(?:FieldAI|Field\s+AI).{0,180}(?:Hyundai|현대차|현대자동차|기아|Kia).{0,180}(?:financial\s+investment|invested|investment|수백만\s*달러|투자)',
    re.I,
)
FIELD_AI_CURRENT_PARTNERS = re.compile(r'Boston\s*Dynamics|Caterpillar|Certis|Big[-\s]*D\s*Construction|DPR\s*Construction|NVIDIA', re.I)
FIELD_AI_PARTNER_EVENT = re.compile(
    r'new\s+(?:strategic\s+)?partnership|partner(?:s|ed)?\s+with|strategic\s+partnership|customer\s+contract|'
    r'production\s+deployment|enterprise[-\s]*scale\s+deployment|multi[-\s]*site\s+deployment|'
    r'신규\s*(?:전략적\s*)?파트너|파트너십\s*(?:체결|발표)|고객\s*계약|생산\s*배치|전사\s*배치',
    re.I,
)
FIELD_AI_NEGATIVE = re.compile(
    r'customer\s+(?:loss|termination)|contract\s+(?:terminated|cancelled|canceled)|deployment\s+(?:halted|suspended)|'
    r'partnership\s+(?:ended|terminated)|고객\s*이탈|계약\s*(?:해지|취소)|배치\s*(?:중단|정지)|파트너십\s*(?:종료|해지)',
    re.I,
)

NVIDIA_ROBOTICS_EXEC = re.compile(r'NVIDIA|엔비디아|Jensen\s*Huang|젠슨\s*황|젠슨황', re.I)
NVIDIA_ROBOTICS_CONTEXT = re.compile(r'robotics|robot|humanoid|physical\s*AI|로보틱스|로봇|휴머노이드|피지컬\s*AI|피지컬AI', re.I)
NVIDIA_CHATGPT_MOMENT = re.compile(r'ChatGPT\s*moment|ChatGPT\s*모먼트|챗GPT\s*모먼트', re.I)
NVIDIA_CES2026_BASELINE = re.compile(r'ChatGPT\s*moment.{0,40}(?:for\s+robotics|robotics).{0,30}(?:is\s+here|has\s+arrived)|(?:robotics).{0,40}ChatGPT\s*moment.{0,30}(?:is\s+here|has\s+arrived)', re.I)
NVIDIA_PRIOR_BASELINE = re.compile(r'ChatGPT\s*moment.{0,60}(?:coming|around\s+the\s+corner)|(?:coming|around\s+the\s+corner).{0,60}ChatGPT\s*moment', re.I)
NVIDIA_WITHIN_YEAR = re.compile(r'within\s+(?:a|one)\s+year|within\s+12\s+months|next\s+12\s+months|1년\s*(?:이내|안에)|향후\s*1년', re.I)
NVIDIA_LONGER_HORIZON = re.compile(r'within\s+(?:two|2|three|3)\s+years?|few\s+years|18\s+months|24\s+months|2년\s*이내|3년\s*이내', re.I)
NVIDIA_ROADSHOW_NOTE = re.compile(r'roadshow|road\s+show|NDR|non[-\s]*deal\s+roadshow|investor\s+meeting|미팅\s*코멘트|로드쇼|기관\s*미팅', re.I)
NVIDIA_GENERAL_BRAIN = re.compile(r'general[-\s]*purpose\s+brain|generalist\s+robot|범용\s*(?:로봇\s*)?두뇌|범용\s*로봇\s*모델', re.I)
NVIDIA_EXEC_METRIC = re.compile(
    r'\d[\d,.]*\s*(?:robots?|units?|customers?|sites?|factories|대|개|곳)|'
    r'(?:fleet|production|shipment|deployment|customer|배치|생산|출하|고객).{0,80}\d[\d,.]*',
    re.I,
)
NVIDIA_EXEC_CONFIRM = re.compile(r'official|announced|confirmed|said|stated|발표|확인|직접\s*언급|말했다', re.I)


NVIDIA_FACTORY_ID = re.compile(
    r'(?:NVIDIA|엔비디아).{0,220}(?:Foxconn|Hon\s*Hai|폭스콘|홍하이).{0,260}'
    r'(?:GB300|NVL72|tester\s*tray|테스터\s*트레이)|'
    r'(?:Foxconn|Hon\s*Hai|폭스콘|홍하이).{0,220}(?:NVIDIA|엔비디아).{0,260}'
    r'(?:GB300|NVL72|tester\s*tray|테스터\s*트레이)',
    re.I | re.S,
)
NVIDIA_FACTORY_TASK = re.compile(
    r'busbar|버스바|connector(?:s)?|커넥터|tester\s*tray|테스터\s*트레이|assembly|조립',
    re.I,
)
NVIDIA_FACTORY_CURRENT_KPI = re.compile(
    r'(?:95\s*%|90\s*(?:-|~|–|to)\s*95\s*%).{0,220}'
    r'(?:160\s*(?:seconds?|sec|s|초)|124\s*(?:seconds?|sec|s|초)|99\.5\s*%)|'
    r'(?:160\s*(?:seconds?|sec|s|초)|124\s*(?:seconds?|sec|s|초)|99\.5\s*%).{0,220}'
    r'(?:95\s*%|90\s*(?:-|~|–|to)\s*95\s*%)',
    re.I | re.S,
)
NVIDIA_FACTORY_SUCCESS = re.compile(
    r'(?:success\s*rate|task\s*success|성공률|작업\s*성공률|수율).{0,60}'
    r'(\d{2,3}(?:\.\d+)?)\s*%|'
    r'(\d{2,3}(?:\.\d+)?)\s*%.{0,60}(?:success\s*rate|성공률|수율)',
    re.I,
)
NVIDIA_FACTORY_CYCLE = re.compile(
    r'(?:cycle\s*time|사이클\s*타임|작업\s*시간|소요\s*시간).{0,80}'
    r'(\d{2,4})\s*(?:seconds?|sec|s|초)|'
    r'(\d{2,4})\s*(?:seconds?|sec|s|초).{0,80}(?:cycle\s*time|사이클\s*타임|작업\s*시간|소요\s*시간)',
    re.I,
)
NVIDIA_FACTORY_TARGET = re.compile(
    r'(?:target|goal|목표).{0,80}(?:99\.5\s*%|124\s*(?:seconds?|sec|s|초)|72\s*(?:seconds?|sec|s|초))|'
    r'(?:99\.5\s*%|124\s*(?:seconds?|sec|s|초)|72\s*(?:seconds?|sec|s|초)).{0,80}(?:target|goal|목표)',
    re.I,
)
NVIDIA_FACTORY_TARGET_HIT = re.compile(
    r'(?:achiev|reach|hit|meet|attain|달성|도달|충족).{0,100}99\.5\s*%|'
    r'99\.5\s*%.{0,100}(?:achiev|reach|hit|meet|attain|달성|도달|충족)|'
    r'(?:cycle\s*time|사이클\s*타임).{0,100}(?:124\s*(?:seconds?|sec|s|초).{0,40}(?:or\s*less|under|이하|미만)|'
    r'72\s*(?:seconds?|sec|s|초).{0,40}(?:or\s*less|under|이하|미만))',
    re.I | re.S,
)
NVIDIA_FACTORY_KPI_CHANGE = re.compile(
    r'(?:improv|increase|rise|better|reduc|shorten|faster|worsen|declin|drop|개선|상승|향상|단축|감소|악화|하락).{0,120}'
    r'(?:success\s*rate|성공률|cycle\s*time|사이클\s*타임|\d{2,3}(?:\.\d+)?\s*%|\d{2,4}\s*(?:seconds?|sec|s|초))',
    re.I,
)
NVIDIA_FACTORY_SOURCE_OK = re.compile(
    r'NVIDIA|NVIDIA\s*Developer|NVIDIA\s*Technical\s*Blog|Focus\s*Taiwan|Central\s*News\s*Agency|\bCNA\b|Tech\s*Times',
    re.I,
)


def _nvidia_exec_source_ok(source: str) -> bool:
    low = (source or '').lower()
    if any(x in low for x in (
        'nvidia', 'reuters', 'bloomberg', 'cnbc', 'financial times', 'ft.com',
        'the information', 'focus taiwan', 'central news agency', 'tech times'
    )):
        return True
    return False


def _nvidia_factory_source_ok(source: str) -> bool:
    return bool(NVIDIA_FACTORY_SOURCE_OK.search(source or ''))


def _nvidia_robotics_exec_stage(text: str, source: str = '') -> str:
    if not (NVIDIA_ROBOTICS_EXEC.search(text) and NVIDIA_ROBOTICS_CONTEXT.search(text)):
        return ''
    if NVIDIA_FACTORY_ID.search(text) and NVIDIA_FACTORY_TASK.search(text):
        if not _nvidia_factory_source_ok(source):
            return 'factory_kpi_unverified'
        if NVIDIA_FACTORY_TARGET_HIT.search(text):
            return 'factory_target_achieved'
        if NVIDIA_FACTORY_CURRENT_KPI.search(text):
            return 'factory_kpi_initial'
        if (NVIDIA_FACTORY_SUCCESS.search(text) or NVIDIA_FACTORY_CYCLE.search(text)) and NVIDIA_FACTORY_KPI_CHANGE.search(text):
            return 'factory_kpi_change'
        if NVIDIA_FACTORY_SUCCESS.search(text) or NVIDIA_FACTORY_CYCLE.search(text):
            return 'factory_kpi_measured'
    if NVIDIA_CES2026_BASELINE.search(text) or NVIDIA_PRIOR_BASELINE.search(text):
        return 'official_rhetoric_baseline'
    if NVIDIA_ROADSHOW_NOTE.search(text) and NVIDIA_WITHIN_YEAR.search(text) and not _nvidia_exec_source_ok(source):
        return 'roadshow_within_year_unverified'
    if NVIDIA_WITHIN_YEAR.search(text):
        return 'within_year_confirmed' if _nvidia_exec_source_ok(source) else 'within_year_unverified'
    if NVIDIA_LONGER_HORIZON.search(text) and (NVIDIA_CHATGPT_MOMENT.search(text) or NVIDIA_GENERAL_BRAIN.search(text)):
        return 'timeline_change' if _nvidia_exec_source_ok(source) else 'timeline_unverified'
    if NVIDIA_GENERAL_BRAIN.search(text) and NVIDIA_EXEC_METRIC.search(text):
        return 'general_brain_execution'
    if NVIDIA_EXEC_METRIC.search(text) and re.search(r'fleet|deployment|production|shipment|배치|생산|출하', text, re.I):
        return 'quantified_deployment'
    return 'background'


def _fieldai_stage(text: str, source: str = '') -> str:
    if not FIELD_AI_ID.search(text):
        return ''
    official = bool(re.search(r'\bFieldAI\b|\bField\s+AI\b', source or '', re.I))
    if FIELD_AI_FUNDING_REVERSE.search(text) or FIELD_AI_NEGATIVE.search(text):
        return 'reverse'
    if FIELD_AI_HYUNDAI.search(text) and FIELD_AI_ATLAS.search(text) and (
        FIELD_AI_PARTNER_EVENT.search(text) or re.search(r'integrat|deploy|license|탑재|통합|배치|사용권|적용', text, re.I)
    ):
        return 'hyundai_atlas_integration'
    if FIELD_AI_HYUNDAI_STAKE.search(text):
        return 'hyundai_followon_or_stake'
    if FIELD_AI_FUNDING.search(text) and FIELD_AI_CLOSED.search(text):
        return 'funding_closed_official' if official else 'funding_closed_reported'
    if FIELD_AI_COMMERCIAL_METRIC.search(text) or FIELD_AI_CUSTOMER_COUNT.search(text):
        if FIELD_AI_CURRENT_COMMERCIAL.search(text):
            return 'commercial_baseline'
        if re.search(r'new|added|grew|growth|increased|surpassed|exceeded|crossed|since|신규|추가|증가|돌파|넘어|상회', text, re.I):
            return 'commercial_metric_change'
    if FIELD_AI_FUNDING.search(text):
        if FIELD_AI_CURRENT_FUNDING.search(text) and (FIELD_AI_PROPOSED.search(text) or not FIELD_AI_CLOSED.search(text)):
            return 'funding_proposed_baseline'
        if re.search(r'\$\s*\d|\d[\d,.]*\s*(?:million|billion|억\s*달러)', text, re.I):
            return 'funding_terms_change'
    if FIELD_AI_HYUNDAI_BASELINE.search(text) and not FIELD_AI_HYUNDAI_STAKE.search(text):
        return 'hyundai_investment_baseline'
    if FIELD_AI_PARTNER_EVENT.search(text):
        if FIELD_AI_CURRENT_PARTNERS.search(text) and not re.search(
            r'Atlas|아틀라스|RMAC|HMGMA|Hyundai|현대차|Kia|기아|Figure\s*AI|Agility\s*Robotics|Unitree|XPENG|ROBOTIS|로보티즈',
            text,
            re.I,
        ):
            return 'partner_baseline'
        return 'new_partner_or_deployment'
    if FIELD_AI_CURRENT_PARTNERS.search(text):
        return 'partner_baseline'
    return 'background'


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
    nvidia_robotics_stage = _nvidia_robotics_exec_stage(text)
    if nvidia_robotics_stage and nvidia_robotics_stage != 'background':
        return 'nvidia_robotics_exec'
    if _fieldai_stage(text):
        return 'fieldai'
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

    if group == 'nvidia_robotics_exec':
        stage = _nvidia_robotics_exec_stage(text, source)
        if stage in {'official_rhetoric_baseline','roadshow_within_year_unverified','within_year_unverified','timeline_unverified','factory_kpi_unverified','background'}:
            return 0
        s = 20
        s += {
            'within_year_confirmed': 18,
            'timeline_change': 14,
            'general_brain_execution': 17,
            'quantified_deployment': 17,
            'factory_kpi_initial': 22,
            'factory_kpi_measured': 18,
            'factory_kpi_change': 20,
            'factory_target_achieved': 24,
        }.get(stage, 0)
        if base.NUMERIC.search(text): s += 3
        if source in base.OFFICIAL_OR_PRIMARY or _nvidia_exec_source_ok(source): s += 7
        elif source in base.TRUSTED: s += 3
        return s

    if group == 'fieldai':
        stage = _fieldai_stage(text, source)
        if stage in {'funding_proposed_baseline','commercial_baseline','hyundai_investment_baseline','partner_baseline','background'}:
            return 0
        s = 20
        if base.NUMERIC.search(text): s += 3
        s += {
            'funding_closed_official': 18,
            'funding_closed_reported': 13,
            'funding_terms_change': 12,
            'commercial_metric_change': 15,
            'new_partner_or_deployment': 15,
            'hyundai_atlas_integration': 19,
            'hyundai_followon_or_stake': 17,
            'reverse': 18,
        }.get(stage, 0)
        if source in base.OFFICIAL_OR_PRIMARY: s += 7
        elif source in base.TRUSTED: s += 3
        return s

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
    if group == 'nvidia_robotics_exec':
        return {
            'official_rhetoric_baseline': '로보틱스 ChatGPT 모먼트 공식 수사 기준선',
            'roadshow_within_year_unverified': '로드쇼 1년 이내 코멘트 미확인 기준선',
            'within_year_unverified': '1년 이내 로보틱스 변곡점 시간표',
            'within_year_confirmed': '1년 이내 로보틱스 변곡점 시간표',
            'timeline_change': '로보틱스 변곡점 시간표 변경',
            'timeline_unverified': '로보틱스 변곡점 시간표 변경',
            'general_brain_execution': '범용 로봇 두뇌 실행지표',
            'quantified_deployment': '로봇 배치·생산·고객 정량 확대',
            'factory_kpi_initial': '폭스콘 GB300 실제 조립 KPI 첫 정량화',
            'factory_kpi_measured': '폭스콘 GB300 로봇 조립 KPI 정량 공개',
            'factory_kpi_change': '폭스콘 GB300 로봇 조립 KPI 개선·악화',
            'factory_target_achieved': '폭스콘 GB300 로봇 조립 99.5%·사이클타임 목표 달성',
        }.get(_nvidia_robotics_exec_stage(text), 'NVIDIA 로보틱스 전망')
    if group == 'fieldai':
        return {
            'funding_proposed_baseline': '기업가치 100억달러·7억달러 조달 추진 기준선',
            'funding_closed_official': '투자유치 종결',
            'funding_closed_reported': '투자유치 종결',
            'funding_terms_change': '투자유치 금액·기업가치 조건 변경',
            'commercial_baseline': '고객 30곳+·매출+계약 1.35억달러 기준선',
            'commercial_metric_change': '매출·계약·수주잔고·고객수 증가',
            'partner_baseline': '기존 산업 파트너·배치 기준선',
            'new_partner_or_deployment': '신규 고객·전략 파트너·생산배치',
            'hyundai_investment_baseline': '현대차그룹 초기 투자 기준선',
            'hyundai_atlas_integration': '현대차·Atlas·RMAC 직접 통합',
            'hyundai_followon_or_stake': '현대차 추가투자·지분 공개',
            'reverse': '투자·계약·배치 후퇴',
        }.get(_fieldai_stage(text), 'FieldAI 사업 배경')
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
        'nvidia_robotics_exec': 'NVIDIA 로보틱스',
        'fieldai': 'FieldAI',
        'samhyun': '삼현',
        'xpeng': '샤오펑 IRON',
        'rfm_general_intelligence': '범용 로봇 지능',
        'agility_platform': 'Agility Robotics',
        'lg_robotics': 'LG 로보틱스',
        'frontier_ai': '프런티어 AI',
    }.get(group, '')


def category(text: str, group: str) -> str:
    if group in {'nvidia_robotics_exec','fieldai','samhyun','xpeng','rfm_general_intelligence','agility_platform','lg_robotics','frontier_ai'}:
        return f"{_lane(group)} · {_raw_cat(text, group)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    mapping = {
        '로보틱스 ChatGPT 모먼트 공식 수사 기준선': 'NVIDIA는 2025년에는 로보틱스의 ChatGPT 모먼트가 다가온다고 했고, 2026년 CES에서는 이미 왔다고 공식 표현했습니다. 따라서 비슷한 낙관론의 반복은 새 신호가 아니며 실제 시간표·배치·생산 숫자가 붙을 때만 재평가합니다.',
        '로드쇼 1년 이내 코멘트 미확인 기준선': '사용자가 전달한 로드쇼 미팅의 within a year 표현은 현재 공개된 NVIDIA 원문·영상·공식 보도에서 직접 확인되지 않았습니다. 공개 1차자료 또는 신뢰 매체의 직접 인용으로 재확인될 때만 확정 시간표로 승격합니다.',
        '1년 이내 시간표 미확인': '1년 이내라는 구체적 시간표가 2차 전언에만 존재하는 단계입니다. 발언자·날짜·장소·원문을 확인하기 전에는 공식 가이던스로 취급하지 않습니다.',
        '1년 이내 로보틱스 변곡점 공식 확인': 'Jensen Huang 또는 NVIDIA의 공개 1차자료·신뢰 매체 직접 인용에서 12개월 이내 로보틱스 변곡점이 명시되는 단계입니다. 이후 GR00T·Cosmos·Jetson 기반 실제 고객배치와 로봇 수량으로 검증합니다.',
        '1년 이내 로보틱스 변곡점 시간표': '12개월 이내라는 구체적 로보틱스 변곡점 시간표입니다. 실제 알림 여부는 출처 검증 단계에서 결정하며, NVIDIA 1차자료나 신뢰 매체의 직접 인용일 때만 고신호로 통과합니다.',
        '로보틱스 변곡점 시간표 변경': '기존 near-term 로보틱스 전망이 18~36개월 등 더 긴 시간으로 바뀌거나 반대로 앞당겨지는 신호입니다. 모델 성능·데이터 부족·하드웨어 신뢰성·안전 규제 중 시간표를 움직인 원인을 분리합니다.',
        '로보틱스 시간표 미확인': '구체적인 시간표가 비공개 전언이나 출처 불명 상태라면 참고만 하고 알림하지 않습니다.',
        '범용 로봇 두뇌 실행지표': '범용 로봇 두뇌가 수사에서 실제 모델·고객·작업수·현장배치 숫자로 내려오는 신호입니다. 지원 로봇 종류, 작업 성공률, 사람 개입률, 추론지연과 온디바이스 연산구성을 확인합니다.',
        '로봇 배치·생산·고객 정량 확대': 'NVIDIA 생태계 로봇이 실제 배치·생산·고객 숫자로 확대되는 단계입니다. 데모 숫자와 유료 생산배치, 파트너 발표와 실출하를 구분합니다.',
        '폭스콘 GB300 실제 조립 KPI 첫 정량화': '데모가 아니라 Foxconn 휴스턴의 GB300 NVL72 테스터 트레이 실제 제조공정에서 로봇 성능이 수치로 내려온 단계입니다. 버스바 조립 작업 성공률 95% 초과, 멀티커넥터 삽입 90~95%, 버스바 사이클타임 약 160초를 기준선으로 고정하고 99.5% 성공률·124초 목표와의 격차를 추적합니다. 이 수치는 GB300 전체 생산수율이 아니라 개별 조립작업 성공률입니다.',
        '폭스콘 GB300 로봇 조립 KPI 정량 공개': 'NVIDIA·Foxconn 제조현장의 로봇 자동화가 작업 성공률·사이클타임으로 정량화되는 단계입니다. 제품 전체 수율과 로봇 작업 성공률을 분리하고 재작업·처리량·사람 개입률을 함께 확인합니다.',
        '폭스콘 GB300 로봇 조립 KPI 개선·악화': '초기 95%+·160초 기준선에서 성공률이나 사이클타임이 실제로 변하는 후속 신호입니다. 99.5%와 124초에 얼마나 가까워지는지, 커넥터 72초 목표까지 포함해 생산성 개선 속도를 봅니다.',
        '폭스콘 GB300 로봇 조립 99.5%·사이클타임 목표 달성': '작업 성공률과 처리량이 전자 제조 목표 수준에 도달해 유연 자동화의 상업적 확장성이 한 단계 올라가는 신호입니다. 다른 GB300 공정·타 공장·차세대 랙으로 복제되는지와 실제 인력·원가 절감 폭을 확인합니다.',

        '기업가치 100억달러·7억달러 조달 추진 기준선': '2026년 10월 2일 Business Insider 보도의 100억달러 기업가치·7억달러 신규 자금조달 추진은 아직 종결된 투자유치가 아닌 현재 기준선으로 고정합니다. 같은 숫자의 재보도는 알리지 않습니다.',
        '7억달러 투자유치 공식 종결': 'FieldAI가 직접 투자유치 종결을 발표하면 실제 납입금액·기업가치·신주 조건·리드 투자자·기존주주 희석을 확인합니다. 현대차그룹의 보유지분이 공개되지 않았으므로 단순 5배 투자수익률로 계산하지 않습니다.',
        '투자유치 종결 보도': '신뢰 매체가 투자유치 종결을 명확히 보도했지만 FieldAI 공식 확인 전인 단계입니다. 보도 금액·기업가치·리드 투자자를 회사 발표로 재확인합니다.',
        '투자유치 종결': '투자유치 추진이 실제 클로징 단계로 넘어간 신호입니다. 공식 발표 여부를 검증 문구로 구분하고 납입금액·기업가치·리드 투자자·신주 조건·희석을 확인합니다.',
        '투자유치 금액·기업가치 조건 변경': '현재 7억달러·100억달러 기준선에서 조달액이나 기업가치가 달라지는 신호입니다. 업라운드·다운라운드 여부와 희석률, 신규 투자자 구성을 확인합니다.',
        '고객 30곳+·매출+계약 1.35억달러 기준선': '현재 1억3500만달러는 순수 인식매출이 아니라 매출과 고객계약을 합친 보도 수치입니다. 30곳 이상의 고객이라는 현재 기준선과 함께 고정하고 같은 숫자의 재보도는 침묵합니다.',
        '매출·계약·수주잔고·고객수 증가': 'FieldAI의 소프트웨어 지능이 실제 상업계약으로 확장되는 핵심 신호입니다. 인식매출·ARR·계약가치·수주잔고를 섞지 않고 각각 분리하며, 고객수 증가와 장기 생산배치 전환을 확인합니다.',
        '기존 산업 파트너·배치 기준선': 'Boston Dynamics·NVIDIA·Caterpillar·Certis·Big-D·DPR 등 기존 공개 협업은 기준선입니다. 같은 파트너십 재보도는 새 이벤트로 보지 않습니다.',
        '신규 고객·전략 파트너·생산배치': '새 고객 실명이나 다수 사업장·생산현장 배치가 확인되면 범용 로봇 지능의 하드웨어·산업 확장성을 검증하는 신호입니다. PoC와 장기 유료계약·반복배치를 구분합니다.',
        '현대차그룹 초기 투자 기준선': '현대차그룹의 수백만달러 규모 초기 투자는 확인됐지만 정확한 투자금액·지분율은 공개되지 않았습니다. 같은 투자 사실 재보도는 침묵합니다.',
        '현대차·Atlas·RMAC 직접 통합': 'FieldAI의 FFM이 Atlas·RMAC·HMGMA에 실제 통합되면 현대차그룹의 하드웨어와 외부 범용 로봇 지능이 직접 연결되는 중요한 사업 단계입니다. 로봇 대수·작업·사용권·데이터 귀속·계약금액을 확인합니다.',
        '현대차 추가투자·지분 공개': '현대차그룹의 후속 투자나 실제 보유지분이 공개되면 FieldAI 가치상승이 현대차 재무가치에 얼마나 연결되는지 처음으로 계산할 수 있습니다. 투자금·지분율·희석·회계처리를 확인합니다.',
        '투자·계약·배치 후퇴': '투자유치 취소·기업가치 하향·고객계약 해지·현장배치 중단은 범용 로봇 지능의 상업화 속도가 예상보다 느리다는 역방향 신호입니다.',

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
        '로보틱스 ChatGPT 모먼트 공식 수사 기준선': 'ChatGPT 모먼트라는 표현은 기술·시장 방향을 설명하는 수사이며 출하량·매출·고객승인 숫자가 아닙니다. 같은 표현이 반복돼도 실적 상향으로 자동 연결하지 않습니다.',
        '로드쇼 1년 이내 코멘트 미확인 기준선': '비공개 미팅 전언은 문맥·주어·범위가 잘릴 수 있습니다. within a year가 모델 성능, 특정 제품, 산업 확산 중 무엇을 가리키는지 확인되지 않아 공식 일정으로 저장하지 않습니다.',
        '1년 이내 시간표 미확인': '출처가 불명확한 시간표는 투자 판단에서 과도한 기대를 만들 수 있습니다. 공식 원문 또는 신뢰 매체 직접 인용 전까지 침묵합니다.',
        '1년 이내 로보틱스 변곡점 공식 확인': '공식 12개월 전망도 로봇 양산을 보장하지 않습니다. 데이터 부족, 손 조작 신뢰성, 배터리·액추에이터·배선, 안전인증과 현장 통합이 늦으면 상업화는 뒤로 밀릴 수 있습니다.',
        '1년 이내 로보틱스 변곡점 시간표': '시간표가 확인돼도 로봇 양산을 보장하지 않습니다. 데이터·조작 신뢰성·배터리·액추에이터·배선·안전인증·현장 통합 병목이 12개월 안에 해결되는지 별도로 검증합니다.',
        '로보틱스 변곡점 시간표 변경': '시간표 후퇴가 실제 기술 실패인지 보수적 커뮤니케이션인지 구분해야 합니다. GR00T 벤치마크·실환경 성공률·고객배치와 함께 확인합니다.',
        '로보틱스 시간표 미확인': '비공개 코멘트 재전파만으로 모델·하드웨어 공급망 수혜를 확정하지 않습니다.',
        '범용 로봇 두뇌 실행지표': '벤치마크 개선이 실환경 반복작업으로 그대로 이어지지 않을 수 있습니다. 작업 분포, 실패복구, 연속가동시간, 안전성과 로봇별 미세조정량을 확인합니다.',
        '로봇 배치·생산·고객 정량 확대': '파트너가 늘어도 NVIDIA 매출은 Jetson·DGX·Omniverse·소프트웨어 사용량에 따라 다릅니다. 로봇 대수와 NVIDIA 콘텐츠 비중을 곱해 실제 매출경로를 확인합니다.',
        '폭스콘 GB300 실제 조립 KPI 첫 정량화': '가장 큰 오판은 95%를 GB300 전체 제조수율로 읽는 것입니다. 이는 특정 조립작업 성공률입니다. 95%에서 99.5%로 가려면 실패율을 약 5%에서 0.5%로 낮춰 약 10분의 1로 줄여야 하며, 버스바 160초는 124초 목표보다 약 29% 느립니다. 현재 수치는 NVIDIA 내부 보고 기반이며 제3자 독립 감사가 확인되지 않았습니다.',
        '폭스콘 GB300 로봇 조립 KPI 정량 공개': '성공률만 높고 사이클타임이 느리면 같은 생산량을 맞추기 위해 병렬화·추가 설비·사람 재작업이 필요할 수 있습니다. 나사 체결·고정밀 커넥터 삽입의 위치오차·힘제어·충돌 손상이 먼저 드러날 병목입니다.',
        '폭스콘 GB300 로봇 조립 KPI 개선·악화': '단일 작업 개선이 전체 랙 조립 생산성 향상을 보장하지 않습니다. 다른 공정으로 병목이 이동하거나 제품 설계 변경 때 재학습·재검증 시간이 늘 수 있습니다.',
        '폭스콘 GB300 로봇 조립 99.5%·사이클타임 목표 달성': '목표 달성도 한 라인·한 제품에서의 결과일 수 있습니다. 다른 공장·Vera Rubin 세대·다른 커넥터 형상에서 같은 성공률과 처리량이 재현되는지를 확인해야 합니다.',

        '기업가치 100억달러·7억달러 조달 추진 기준선': '현재 라운드는 보도상 진행 중이며 최종 투자계약·납입이 확정된 단계가 아닙니다. 100억달러 기업가치를 FieldAI의 확정 거래가치나 현대차의 실현 투자수익으로 계산하지 않습니다.',
        '7억달러 투자유치 공식 종결': '기업가치 급등이 실제 매출·현금흐름 증가보다 앞설 수 있습니다. 새 자금의 신주 비중·청산우선권·전환권·희석과 현금소진 속도를 확인합니다.',
        '투자유치 종결 보도': '보도상 종결과 법적 클로징·자금납입은 다를 수 있습니다. FieldAI 공식 발표와 투자자 확인 전까지 잠정 상태로 둡니다.',
        '투자유치 종결': '언론 보도상 종결과 회사 공식 클로징은 구분해야 합니다. 검증 문구에서 소스 수준을 표시하고 실제 자금납입·조건을 확인합니다.',
        '투자유치 금액·기업가치 조건 변경': '조건 변경이 상향만 뜻하지 않습니다. 투자자 협상 지연·다운라운드·구조화 우선주로 표면 기업가치와 경제적 조건이 달라질 수 있습니다.',
        '고객 30곳+·매출+계약 1.35억달러 기준선': '1억3500만달러는 순수 매출이 아니라 매출+계약 합산 수치입니다. 이 금액을 연매출·ARR·수주잔고로 단정하거나 기업가치 배수를 계산하지 않습니다.',
        '매출·계약·수주잔고·고객수 증가': '고객 수 증가가 저마진 서비스·파일럿 위주일 수 있습니다. 인식매출, 계약기간, 소프트웨어 사용권 반복매출, 고객 유지율과 현장당 로봇 대수를 확인합니다.',
        '기존 산업 파트너·배치 기준선': '파트너 수가 많아도 FieldAI가 하드웨어 판매매출을 직접 가져가는 것은 아닙니다. 실제 소프트웨어 가격·계약기간·갱신·지원비가 공개돼야 수익구조를 계산할 수 있습니다.',
        '신규 고객·전략 파트너·생산배치': '파트너십 발표와 유료 생산배치는 다릅니다. 실제 로봇 대수·가동률·작업 성공률·사람 개입률·갱신계약이 따라오지 않으면 매출 확장이 제한됩니다.',
        '현대차그룹 초기 투자 기준선': '투자금과 지분율이 비공개여서 현대차의 평가이익을 계산할 수 없습니다. 20억달러 가치평가 직전·직후 어느 가격에 투자했는지도 공개되지 않았습니다.',
        '현대차·Atlas·RMAC 직접 통합': 'Atlas에 외부 지능을 붙이는 것이 장기 표준 채택을 뜻하지 않을 수 있습니다. Boston Dynamics 자체 소프트웨어·Google DeepMind 등과의 중복, 데이터 소유권, 안전검증과 지연시간이 경쟁 변수입니다.',
        '현대차 추가투자·지분 공개': '후속 투자로 지분가치가 커져도 비상장주식은 유동성이 낮고 추가 희석·평가손익 변동이 있습니다. 실현수익과 장부평가를 분리합니다.',
        '투자·계약·배치 후퇴': '가장 현실적인 실패 경로는 자금조달 자체보다 현장 확장 속도가 둔화되면서 높은 기업가치 대비 매출 전환이 늦어지는 경우입니다. 고객 유지·계약갱신·현장당 배치대수가 먼저 악화됩니다.',

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
    if group == 'nvidia_robotics_exec':
        stage = _nvidia_robotics_exec_stage(text, source)
        if stage == 'official_rhetoric_baseline':
            return 'NVIDIA 공식 기준선 · 2025 coming / 2026 CES is here 반복 수사는 새 시간표 아님'
        if stage in {'roadshow_within_year_unverified','within_year_unverified','timeline_unverified'}:
            return '비공개·2차 전언 단계 · NVIDIA 원문/영상/직접 인용 공개자료에서 동일 문구 재확인 전'
        if stage == 'within_year_confirmed':
            return 'NVIDIA 공식자료 또는 Reuters·Bloomberg·CNBC·FT·The Information의 직접 인용으로 12개월 이내 시간표 확인'
        if stage == 'timeline_change':
            return 'NVIDIA/Jensen 직접 인용이 포함된 신뢰 자료 · 기존 near-term 기준선 대비 시간표 변경'
        if stage in {'factory_kpi_initial','factory_kpi_measured','factory_kpi_change','factory_target_achieved'}:
            if source in base.OFFICIAL_OR_PRIMARY or re.search(r'NVIDIA', source, re.I):
                return 'NVIDIA 기술자료 기반 · Foxconn GB300 테스터트레이 작업 성공률·사이클타임 확인 · 전체 제조수율과 구분'
            if re.search(r'Focus\s*Taiwan|Central\s*News\s*Agency|\bCNA\b', source, re.I):
                return 'Focus Taiwan/CNA가 NVIDIA 10월 2일 기술보고서를 인용 · 작업 성공률·사이클타임 교차확인 · 제3자 감사 아님'
            return 'Tech Times 등 2차 보도 · Focus Taiwan/CNA와 NVIDIA 기술자료 인용 내용 교차확인 · 작업 성공률을 전체 제조수율로 해석 금지'
        if stage in {'general_brain_execution','quantified_deployment'}:
            if source in base.OFFICIAL_OR_PRIMARY:
                return 'NVIDIA 공식자료 · 범용 로봇 두뇌/배치/생산 정량지표 직접 확인'
            return '신뢰 매체 보도 · NVIDIA 및 로봇 파트너 공식자료 교차확인'
        return 'NVIDIA 로보틱스 관련 보도 · 1차자료 추가확인'
    if group == 'fieldai':
        stage = _fieldai_stage(text, source)
        if stage == 'funding_proposed_baseline':
            return 'Business Insider 소식통 보도 기준선 · 100억달러 기업가치·7억달러 조달은 아직 공식 클로징 전'
        if stage == 'funding_closed_official':
            return 'FieldAI 공식 투자유치 발표 · 납입액·기업가치·투자자·신주조건 직접 확인'
        if stage == 'funding_closed_reported':
            return '신뢰 매체의 투자유치 종결 보도 · FieldAI 공식 발표·투자자 확인 전'
        if stage == 'commercial_baseline':
            return 'Business Insider 보도 · 1.35억달러는 인식매출 단독이 아니라 매출+고객계약 합산, 30곳+ 고객 기준선'
        if stage == 'hyundai_investment_baseline':
            return '연합뉴스·전자신문·FieldAI 공개자료 교차확인 · 투자금 수백만달러 수준, 정확한 금액·지분율 비공개'
        if stage == 'partner_baseline':
            return 'FieldAI 공식 파트너십 기준선 · 반복 보도는 새 이벤트 아님'
        if stage in {'commercial_metric_change','new_partner_or_deployment','hyundai_atlas_integration','hyundai_followon_or_stake'}:
            if source in base.OFFICIAL_OR_PRIMARY:
                return 'FieldAI·당사자 공식자료 · 고객·계약·배치·투자 단계 직접 확인'
            return '신뢰 매체 보도 · FieldAI·고객·투자자 공식자료 교차확인'
        if stage == 'funding_terms_change':
            return '신뢰 매체·회사자료로 기존 7억달러·100억달러 조건 대비 변경 확인'
        if stage == 'reverse':
            return '계약·투자·배치 후퇴 보도 · 당사자 공식자료 교차확인'
        return 'FieldAI 관련 보도 · 회사·고객·투자자 1차자료 추가확인'
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
    if g == 'nvidia_robotics_exec':
        sa, sb = _nvidia_robotics_exec_stage(ta, a.get('source') or ''), _nvidia_robotics_exec_stage(tb, b.get('source') or '')
        if sa != sb:
            return False
        if sa in {'official_rhetoric_baseline','roadshow_within_year_unverified','within_year_unverified'}:
            return True
        nums_a = set(re.findall(r'\d[\d,.]*\s*(?:months?|years?|robots?|units?|customers?|sites?|%|seconds?|sec|s|대|개|곳|개월|년|초)', ta, re.I))
        nums_b = set(re.findall(r'\d[\d,.]*\s*(?:months?|years?|robots?|units?|customers?|sites?|%|seconds?|sec|s|대|개|곳|개월|년|초)', tb, re.I))
        if nums_a and nums_b:
            return bool(nums_a & nums_b)
        return True
    if g == 'fieldai':
        sa, sb = _fieldai_stage(ta, a.get('source') or ''), _fieldai_stage(tb, b.get('source') or '')
        if sa != sb:
            return False
        if sa in {'funding_proposed_baseline','funding_closed_official','funding_closed_reported','commercial_baseline','hyundai_investment_baseline'}:
            return True
        nums_a = set(re.findall(r'\$?\s*\d[\d,.]*\s*(?:million|billion|M|B|달러)|\d[\d,.]*\s*(?:customers?|clients?|고객|고객사)', ta, re.I))
        nums_b = set(re.findall(r'\$?\s*\d[\d,.]*\s*(?:million|billion|M|B|달러)|\d[\d,.]*\s*(?:customers?|clients?|고객|고객사)', tb, re.I))
        if nums_a and nums_b:
            return bool(nums_a & nums_b)
        return True
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
    if group == 'nvidia_robotics_exec':
        stage = _nvidia_robotics_exec_stage(text, item.get('source') or '')
        if stage == 'official_rhetoric_baseline':
            return hashlib.sha256(b'nvidia-robotics|chatgpt-moment|official-rhetoric-baseline|ces2026-here').hexdigest()
        if stage == 'roadshow_within_year_unverified':
            return hashlib.sha256(b'nvidia-robotics|roadshow|within-a-year|unverified-user-baseline').hexdigest()
        if stage == 'factory_kpi_initial':
            return hashlib.sha256(b'nvidia-foxconn|gb300-nvl72|tester-tray|robot-assembly-kpi|2026-10|95plus|90-95|160s|124s|72s|99.5target').hexdigest()
        nums = '|'.join(sorted(set(re.findall(r'\d[\d,.]*\s*(?:months?|years?|robots?|units?|customers?|sites?|%|seconds?|sec|s|대|개|곳|개월|년|초)', text, re.I)))[:10]) or 'no-number'
        horizon = '12m' if NVIDIA_WITHIN_YEAR.search(text) else ('longer' if NVIDIA_LONGER_HORIZON.search(text) else 'no-horizon')
        return hashlib.sha256(f'nvidia-robotics|{stage}|{horizon}|{nums}'.encode()).hexdigest()
    if group == 'fieldai':
        stage = _fieldai_stage(text, item.get('source') or '')
        if stage == 'funding_proposed_baseline':
            return hashlib.sha256(b'fieldai|funding|2026-10-02|proposed|700m|10b').hexdigest()
        if stage == 'commercial_baseline':
            return hashlib.sha256(b'fieldai|commercial|2026-10|135m-revenue-plus-contracts|30-plus-customers').hexdigest()
        if stage == 'hyundai_investment_baseline':
            return hashlib.sha256(b'fieldai|hyundai|2026-02|initial-investment|amount-undisclosed').hexdigest()
        if stage == 'partner_baseline':
            partners = '-'.join(sorted(set(re.findall(r'Boston\s*Dynamics|Caterpillar|Certis|Big[-\s]*D\s*Construction|DPR\s*Construction|NVIDIA', text, re.I)))) or 'known-partner'
            return hashlib.sha256(f'fieldai|partner-baseline|{partners}'.encode()).hexdigest()
        nums = '|'.join(sorted(set(re.findall(r'\$?\s*\d[\d,.]*\s*(?:million|billion|M|B|달러)|\d[\d,.]*\s*(?:customers?|clients?|고객|고객사)', text, re.I)))[:6]) or 'no-number'
        partners = '-'.join(sorted(set(re.findall(r'Hyundai|현대차|기아|Kia|Boston\s*Dynamics|Caterpillar|Certis|NVIDIA|Atlas|RMAC|HMGMA', text, re.I)))) or 'no-partner'
        return hashlib.sha256(f'fieldai|{stage}|{partners}|{nums}'.encode()).hexdigest()
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
    priority = ['tesla','nvidia_robotics_exec','fieldai','xpeng','global_battery_capacity','solid_state_material','rfm_general_intelligence','agility_platform','samhyun','lg_robotics','robotis','battery','ess_battery','frontier_ai','wonik','byd_paxini']
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

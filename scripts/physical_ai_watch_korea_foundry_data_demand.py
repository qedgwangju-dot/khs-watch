#!/usr/bin/env python3
"""Add Korea physical-AI infrastructure and ROBOTIS excess-demand lanes.

Tracks three monetization chains:
1) Pohang/Neuromeka robot foundry: MOU -> regional investment fund/financing ->
   permits/groundbreaking -> factory/data-foundry/inference-AI build -> OEM
   contract manufacturing orders -> utilization/revenue.
2) Hyundai Motor robot data factory: announced collection/validation facility ->
   site/robot-count/equipment awards -> operation -> measured data/robot
   performance -> external deployment.
3) ROBOTIS actuator demand: backlog > installed capacity -> Uzbekistan ramp ->
   yield/monthly output -> shipments/ASP -> additional OEM orders.

Guardrails:
- Pohang KRW 180bn is a staged project plan, not fully secured/spent cash.
- MOU, fund application and targeted groundbreaking are separated from final
  fund selection, financing close, permits and actual construction.
- Hyundai Motor officially says it plans a factory-like robot data collection
  and performance-validation facility; media estimates of Seoul-area location,
  hundreds of robots and detailed timing remain estimates until confirmed.
- Analyst wording such as ROBOTIS being the industry's only excess-demand name
  is not promoted to a company-official fact.
- Capacity/backlog are not shipments; yield, output and customer orders are
  tracked separately.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_hyundai_mobis_atlas as hm

base = hm.base
ext = hm.ext

base.QUERIES.extend([
    '(포항 OR 영일만 OR "Yeongilman") (뉴로메카 OR Neuromeka) (로봇 파운드리 OR "robot foundry" OR 피지컬AI OR "physical AI") (1800억 OR 1,800억 OR 400억 OR 1400억 OR 1,400억 OR MOU OR 펀드 OR 착공 OR 준공)',
    '(포항 OR 영일만 OR "Yeongilman") (뉴로메카 OR Neuromeka) (지역활성화투자펀드 OR "지역 활성화 투자 펀드" OR 투자펀드 OR 정책금융 OR 금융약정 OR 선정 OR 승인 OR 인허가 OR 착공 OR 준공 OR 가동)',
    '(포항 OR 영일만 OR "Yeongilman") (로봇 파운드리 OR "robot foundry") (위탁생산 OR "contract manufacturing" OR OEM OR 고객 OR 수주 OR order OR 가동률 OR utilization OR 생산량 OR output)',
    '(포항 OR 영일만 OR "Yeongilman") (데이터 파운드리 OR "data foundry" OR 추론 OR inference) (AI 데이터센터 OR "AI data center" OR 로봇 데이터 OR robot data OR 2단계 OR phase 2) (뉴로메카 OR Neuromeka)',
    '(현대자동차 OR 현대차 OR "Hyundai Motor") (로봇 데이터 팩토리 OR "robot data factory" OR 로봇 데이터 수집 OR "robot data collection" OR 성능 검증 OR "performance validation") (부지 OR site OR 수도권 OR 서울 OR 로봇 OR robot OR 수백 OR hundreds OR 구축 OR build OR 가동 OR operation)',
    '(현대자동차 OR 현대차 OR "Hyundai Motor") (로봇 OR robotics OR 피지컬AI OR "physical AI") (데이터 팩토리 OR "data factory") (설비 발주 OR equipment OR 계약 OR contract OR 고객 OR vendor OR 데이터 업체 OR data provider OR 한국 OR Korea OR 미국 OR US)',
    '(로보티즈 OR ROBOTIS) (액추에이터 OR actuator OR DYNAMIXEL) (수주잔고 OR backlog OR 초과수요 OR "excess demand" OR 생산능력 OR capacity OR 우즈베키스탄 OR Uzbekistan OR 공장 OR plant)',
    '(로보티즈 OR ROBOTIS) (액추에이터 OR actuator) (수율 OR yield OR 가동률 OR utilization OR 월 생산량 OR monthly output OR 출하 OR shipment OR 납기 OR lead time OR 평균판매단가 OR ASP)',
    '(로보티즈 OR ROBOTIS) (Microduck OR 마이크로덕 OR Reachy OR 리치미니 OR Hugging Face OR 허깅페이스 OR Pollen Robotics) (액추에이터 OR actuator OR 공급 OR supply OR 주문 OR order OR 판매량 OR units)',
])

base.TRUSTED.update({
    '전자신문', 'ZDNet Korea', 'ZDNet', '뉴시스', 'Newsis', '뉴스핌',
    '파이낸셜뉴스', '이투데이', '한국경제', '매일경제', '연합뉴스',
})
base.OFFICIAL_OR_PRIMARY.update({
    '포항시', '경상북도', '뉴로메카', 'Neuromeka',
    '현대자동차', '현대자동차그룹', 'Hyundai Motor', 'Hyundai Motor Group',
    '로보티즈', 'ROBOTIS',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event

POHANG = re.compile(r'포항|영일만|Yeongilman', re.I)
NEUROMEKA = re.compile(r'뉴로메카|Neuromeka', re.I)
ROBOT_FOUNDRY = re.compile(r'로봇\s*파운드리|robot\s*foundry|피지컬\s*AI\s*로봇\s*자동화\s*글로벌\s*허브', re.I)
FUNDING = re.compile(r'지역\s*활성화\s*투자\s*펀드|지역활성화투자펀드|투자\s*펀드|정책\s*금융|민간\s*자본|SPC|금융\s*약정|financing|fund|선정|selected|승인|approval', re.I)
BUILD = re.compile(r'인허가|permit|착공|groundbreaking|준공|completion|장비\s*반입|equipment|가동|operation|ramp|11월|2027년\s*12월', re.I)
FOUNDRY_CUSTOMER = re.compile(r'위탁\s*생산|contract\s*manufacturing|OEM|고객|customer|수주|order|계약|contract|가동률|utilization|생산량|output', re.I)
DATA_FOUNDRY = re.compile(r'데이터\s*파운드리|data\s*foundry|추론\s*(?:전용)?\s*AI\s*데이터센터|inference.*data\s*center|2단계|phase\s*2', re.I)

HYUNDAI = re.compile(r'현대자동차|현대차|Hyundai\s*Motor', re.I)
ROBOT_DATA_FACTORY = re.compile(r'로봇\s*데이터\s*팩토리|robot\s*data\s*factory|데이터\s*팩토리|data\s*factory|로봇\s*데이터\s*수집|robot\s*data\s*collection|성능\s*검증|performance\s*validation', re.I)
SITE_SCALE = re.compile(r'부지|site|수도권|서울\s*근교|서울|수백\s*대|hundreds?\s+of\s+robots|로봇\s*대수|robot\s*count|면적|square\s*meter|㎡', re.I)
EQUIPMENT_OPERATION = re.compile(r'설비\s*발주|equipment\s*(?:order|award)|착공|groundbreaking|준공|completion|가동|operation|운영|배치|deployment', re.I)
DATA_VENDOR = re.compile(r'데이터\s*업체|data\s*provider|vendor|알체라|Alchera|외부\s*업체|external\s*(?:provider|vendor)', re.I)
MEASURED_ROBOT = re.compile(r'작업\s*성공률|task\s*success|사람\s*개입|human\s*intervention|가동률|uptime|실제\s*사용\s*데이터|real[- ]world\s*data', re.I)

ROBOTIS = re.compile(r'로보티즈|ROBOTIS', re.I)
ACTUATOR = re.compile(r'액추에이터|actuator|DYNAMIXEL', re.I)
DEMAND = re.compile(r'수주\s*잔고|backlog|초과\s*수요|excess\s*demand|주문|orders?', re.I)
ROBOTIS_CAPACITY = re.compile(r'생산\s*능력|capacity|30만|300,?000|150만|1,?500,?000|우즈베키스탄|Uzbekistan|공장|plant|증설|expansion', re.I)
RAMP_QUALITY = re.compile(r'수율|yield|가동률|utilization|월\s*생산량|monthly\s*output|출하|shipment|납기|lead\s*time|평균판매단가|\bASP\b', re.I)
HUGGINGFACE = re.compile(r'Microduck|마이크로덕|Reachy|리치미니|Hugging\s*Face|허깅페이스|Pollen\s*Robotics', re.I)
ANALYST_ONLY = re.compile(r'증권|research|리포트|목표주가|투자의견|한국투자|analyst', re.I)
PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가|stock\s*price|shares?\s*(?:jump|rise|surge)', re.I)


def _is_pohang_foundry(text: str) -> bool:
    return bool(POHANG.search(text) and NEUROMEKA.search(text) and (ROBOT_FOUNDRY.search(text) or DATA_FOUNDRY.search(text)))


def _is_hyundai_data_factory(text: str) -> bool:
    return bool(HYUNDAI.search(text) and ROBOT_DATA_FACTORY.search(text) and re.search(r'로봇|robot|피지컬\s*AI|physical\s*AI|제조|factory', text, re.I))


def _is_robotis_demand(text: str) -> bool:
    return bool(ROBOTIS.search(text) and ACTUATOR.search(text) and (DEMAND.search(text) or ROBOTIS_CAPACITY.search(text) or RAMP_QUALITY.search(text) or HUGGINGFACE.search(text)))


def topic_group(text: str) -> str | None:
    if _is_pohang_foundry(text):
        return 'pohang_robot_foundry'
    if _is_hyundai_data_factory(text):
        return 'hyundai_robot_data_factory'
    if _is_robotis_demand(text):
        return 'robotis_excess_demand'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    if group not in {'pohang_robot_foundry', 'hyundai_robot_data_factory', 'robotis_excess_demand'}:
        return _orig_score(item)

    source = item.get('source') or ''
    operational = FUNDING.search(text) or BUILD.search(text) or FOUNDRY_CUSTOMER.search(text) or SITE_SCALE.search(text) or EQUIPMENT_OPERATION.search(text) or DEMAND.search(text) or ROBOTIS_CAPACITY.search(text) or RAMP_QUALITY.search(text)
    if PRICE_ONLY.search(title) and not operational:
        return -20

    s = 18
    if base.NUMERIC.search(text): s += 3
    if source in base.OFFICIAL_OR_PRIMARY: s += 7
    elif source in base.TRUSTED: s += 3

    if group == 'pohang_robot_foundry':
        if re.search(r'1,?800억|1800억|400억|1,?400억|1400억', text, re.I): s += 4
        if FUNDING.search(text): s += 6
        if re.search(r'선정|selected|금융\s*약정|financing\s*close|투자\s*확정|final\s*approval', text, re.I): s += 8
        if BUILD.search(text): s += 7
        if FOUNDRY_CUSTOMER.search(text): s += 8
        if DATA_FOUNDRY.search(text): s += 5
    elif group == 'hyundai_robot_data_factory':
        if SITE_SCALE.search(text): s += 7
        if EQUIPMENT_OPERATION.search(text): s += 8
        if DATA_VENDOR.search(text): s += 4
        if MEASURED_ROBOT.search(text): s += 7
        if re.search(r'확정|confirmed|공식|official|선정|selected|계약|contract|발주|award', text, re.I): s += 6
    else:
        if DEMAND.search(text): s += 7
        if re.search(r'50만|500,?000', text, re.I): s += 5
        if ROBOTIS_CAPACITY.search(text): s += 7
        if RAMP_QUALITY.search(text): s += 9
        if HUGGINGFACE.search(text): s += 5
        if re.search(r'390만|3,?900,?000|22만|220,?000|150만|1,?500,?000|30만|300,?000', text, re.I): s += 4
    return s


def _subcat(group: str, text: str) -> str:
    if group == 'pohang_robot_foundry':
        if FOUNDRY_CUSTOMER.search(text): return '로봇 파운드리 위탁생산·가동률'
        if DATA_FOUNDRY.search(text) and BUILD.search(text): return '데이터 파운드리·추론 인프라 구축'
        if BUILD.search(text): return '로봇 파운드리 착공·준공·가동'
        if FUNDING.search(text): return '지역활성화 투자펀드·금융확정'
        return '포항 피지컬AI 로봇 파운드리'
    if group == 'hyundai_robot_data_factory':
        if MEASURED_ROBOT.search(text): return '로봇 데이터 성능·현장 검증'
        if EQUIPMENT_OPERATION.search(text): return '데이터 팩토리 설비·가동'
        if SITE_SCALE.search(text): return '데이터 팩토리 부지·로봇 대수'
        if DATA_VENDOR.search(text): return '외부 데이터 업체·계약'
        return '현대차 로봇 데이터 팩토리'
    if RAMP_QUALITY.search(text): return '액추에이터 수율·월생산·출하'
    if ROBOTIS_CAPACITY.search(text): return '액추에이터 생산능력·신공장'
    if HUGGINGFACE.search(text): return '허깅페이스향 액추에이터 물량'
    return '액추에이터 초과수요·수주잔고'


def category(text: str, group: str) -> str:
    if group in {'pohang_robot_foundry', 'hyundai_robot_data_factory', 'robotis_excess_demand'}:
        prefix = {'pohang_robot_foundry':'뉴로메카·포항', 'hyundai_robot_data_factory':'현대차 피지컬AI', 'robotis_excess_demand':'로보티즈'}[group]
        return f"{prefix} · {_subcat(group, text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    m = {
        '지역활성화 투자펀드·금융확정': 'MOU 단계의 1,800억원 계획이 실제 자금조달로 넘어가는 문턱입니다. 1단계 400억원과 2단계 1,400억원을 분리하고 펀드 선정·SPC 자기자본·대출약정·민간자금 비중이 확인될 때만 확정 설비투자로 승격합니다.',
        '로봇 파운드리 착공·준공·가동': '계획이 실제 제조자산으로 전환되는 단계입니다. 11월 착공 목표와 2027년 12월 준공 목표를 실제 인허가·착공·장비 반입·전원 인가·가동 시점으로 교체해 추적합니다.',
        '데이터 파운드리·추론 인프라 구축': '2단계 로봇 현장 데이터 파운드리와 추론 전용 AI 인프라가 제조 수수료 외 데이터·컴퓨팅 반복매출로 이어지는지 확인하는 신호입니다.',
        '로봇 파운드리 위탁생산·가동률': '뉴로메카 자체 로봇 생산을 넘어 외부 OEM 위탁생산 고객·수주·가동률이 붙는 시점이 파운드리 사업의 실제 매출 검증 구간입니다.',
        '포항 피지컬AI 로봇 파운드리': '로봇 제조·실증·데이터를 한 장소에 묶는 계획입니다. 금액 자체보다 금융확정→착공→외부고객→가동률 순으로 실제 사업화를 봅니다.',
        '데이터 팩토리 부지·로봇 대수': '현대차의 공식 시설 구축 계획이 실제 부지와 로봇 물량으로 구체화되는 신호입니다. 수백대·서울 근교 등 보도 추정은 회사 확인 전까지 추정으로 표시합니다.',
        '데이터 팩토리 설비·가동': '부지 계획에서 설비 발주·착공·가동으로 넘어가면 로봇 데이터 생산능력이 실제 자산으로 바뀝니다. 로봇 대수와 데이터 생성시간을 함께 추적합니다.',
        '외부 데이터 업체·계약': '기밀 제조데이터는 내부, 범용 데이터는 외부 조달하는 구조가 구체화되는 신호입니다. 업체 실명은 계약·공식자료가 확인될 때만 고객으로 확정합니다.',
        '로봇 데이터 성능·현장 검증': '데이터 양이 실제 작업 성공률·사람 개입률·가동률 개선으로 바뀌는지 보는 핵심 구간입니다. 데이터 생성량보다 현장 성능 개선을 우선합니다.',
        '현대차 로봇 데이터 팩토리': '공장과 유사한 조건의 데이터 수집·성능검증 시설을 통해 제조 현장 데이터를 피지컬AI 학습과 외부 배치로 연결하는 현대차의 데이터 선순환을 추적합니다.',
        '액추에이터 초과수요·수주잔고': '로보티즈 수요가 설치 생산능력을 넘어서는지 확인하는 신호입니다. 증권사 초과수요 평가는 공식 사실과 분리하고 수주잔고·출하·납기를 숫자로 검증합니다.',
        '액추에이터 생산능력·신공장': '우즈베키스탄 신공장과 증설이 수주잔고를 실제 출하로 전환하는 문턱입니다. 명목 생산능력보다 수율·월 생산량·가동률을 우선합니다.',
        '액추에이터 수율·월생산·출하': '초과수요 국면의 가장 중요한 실적 연결 지표입니다. 수율 안정화와 월 생산량 상승이 확인돼야 생산능력 숫자가 매출로 전환됩니다.',
        '허깅페이스향 액추에이터 물량': 'Microduck·Reachy 계열 판매량을 대당 액추에이터 수와 평균판매단가에 연결해 실제 로보티즈 매출 민감도를 추적합니다.',
    }
    return m[raw] if raw in m else _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    r = {
        '지역활성화 투자펀드·금융확정': 'MOU와 펀드 신청은 자금확정이 아닙니다. 선정·손실분담·민간자금·대출약정이 늦어지면 11월 착공 목표부터 밀릴 수 있습니다.',
        '로봇 파운드리 착공·준공·가동': '인허가·장비 반입·전력 인입이 늦어지면 준공과 매출 시작이 순연되고 감가상각·금융비용 부담이 먼저 나타날 수 있습니다.',
        '데이터 파운드리·추론 인프라 구축': '데이터·컴퓨팅 설비를 먼저 깔고 외부 고객이 늦게 붙으면 저가동률과 운영비가 먼저 발생할 수 있습니다.',
        '로봇 파운드리 위탁생산·가동률': '파운드리는 외부 OEM 고객이 없으면 자체 생산공장에 그칩니다. 고객 실명·계약물량·라인 가동률이 없으면 반복매출로 보지 않습니다.',
        '포항 피지컬AI 로봇 파운드리': '1,800억원 전체를 이미 확정·집행된 예산으로 표시하지 않습니다. 단계별 자금확정과 착공을 따로 확인합니다.',
        '데이터 팩토리 부지·로봇 대수': '서울 근교·수백대는 현재 보도 관측입니다. 현대차가 위치·규모를 확정하기 전에는 확정 수치로 알림하지 않습니다.',
        '데이터 팩토리 설비·가동': '대규모 데이터 수집시설도 로봇 가동률·안전·정비시간이 낮으면 데이터 생산성이 떨어집니다. 발열·고장·사람 개입률을 함께 봅니다.',
        '외부 데이터 업체·계약': '기사에서 업체가 언급돼도 공식 계약이 없으면 현대차 고객으로 확정하지 않습니다. 제조 공정 데이터 보안과 외부 반출 제한도 병목입니다.',
        '로봇 데이터 성능·현장 검증': '데이터 양 증가가 모델 성능 개선을 보장하지 않습니다. 작업 일반화·성공률·실패복구가 개선되지 않으면 데이터 팩토리가 비용센터에 머물 수 있습니다.',
        '현대차 로봇 데이터 팩토리': '시설 구축 계획은 공식이지만 위치·규모·로봇 대수·운영 일정의 일부는 아직 미확정입니다. 확정과 관측을 분리합니다.',
        '액추에이터 초과수요·수주잔고': '수주잔고는 매출이 아닙니다. 증권사의 업종 유일 초과수요 표현은 분석 의견이므로 회사 공식 수주·출하 데이터와 분리합니다.',
        '액추에이터 생산능력·신공장': '생산능력 150만대가 확보돼도 초기 수율이 낮으면 출하가 따라오지 않습니다. 증설 고정비와 재고가 먼저 늘 수 있습니다.',
        '액추에이터 수율·월생산·출하': '수율 안정화가 지연되면 납기·품질·반품·교환 접수와 보증비용이 먼저 악화될 수 있습니다.',
        '허깅페이스향 액추에이터 물량': '로봇 판매량 전망과 실제 발주는 다릅니다. 대당 탑재량·단가·실제 주문을 확인한 뒤 매출로 환산합니다.',
    }
    return r[raw] if raw in r else _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group == 'pohang_robot_foundry':
        src = item.get('source') or ''
        if src in {'포항시','경상북도','뉴로메카','Neuromeka'}:
            return '당사자 공식자료 · 단계별 자금확정/착공 여부 확인'
        return '신뢰 매체 보도 · 포항시·경상북도·뉴로메카 공식자료 교차확인'
    if group == 'hyundai_robot_data_factory':
        src = item.get('source') or ''
        if src in {'현대자동차','현대자동차그룹','Hyundai Motor','Hyundai Motor Group'}:
            return '현대자동차그룹 공식자료'
        if SITE_SCALE.search(text):
            return '보도 단계 · 현대차 공식 계획은 확인, 부지·규모·로봇 대수는 추가확인 필요'
        return '신뢰 매체 보도 · 현대자동차그룹 공식자료 교차확인'
    if group == 'robotis_excess_demand':
        src = item.get('source') or ''
        if src in {'로보티즈','ROBOTIS'}:
            return '로보티즈 공식자료'
        if ANALYST_ONLY.search(text) or re.search(r'초과\s*수요|excess\s*demand', text, re.I):
            return '증권사 분석 · 수주잔고·생산능력·출하 숫자 별도 검증'
        return '신뢰 매체 보도 · 로보티즈 공시/회사자료 교차확인'
    return _orig_verification(item, group, text)


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != b.get('group'):
        return False
    g = a.get('group')
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    if g == 'pohang_robot_foundry':
        # Initial MOU/180bn story is one event across syndicated articles.
        initial = r'1,?800억|1800억|MOU|양해각서'
        if re.search(initial, ta, re.I) and re.search(initial, tb, re.I): return True
        # Later fund/groundbreaking/customer milestones remain separate unless same milestone family.
        for sig in [r'지역\s*활성화\s*투자\s*펀드|지역활성화투자펀드|금융\s*약정', r'착공|groundbreaking', r'위탁\s*생산|contract\s*manufacturing|OEM']:
            if re.search(sig, ta, re.I) and re.search(sig, tb, re.I): return True
    elif g == 'hyundai_robot_data_factory':
        # Current Seoul-area/hundreds-of-robots report is one event across rewrites.
        current = r'서울\s*근교|수도권|수백\s*대|hundreds?\s+of\s+robots|데이터\s*팩토리|data\s*factory'
        if re.search(current, ta, re.I) and re.search(current, tb, re.I):
            # Do not merge a future confirmed site/equipment/order milestone into today's estimate story.
            future = r'부지\s*확정|site\s*confirmed|설비\s*발주|equipment\s*(?:order|award)|착공|groundbreaking|가동\s*개시|operation\s*start'
            if not (re.search(future, ta, re.I) or re.search(future, tb, re.I)): return True
    elif g == 'robotis_excess_demand':
        # Same analyst excess-demand note across media rewrites.
        excess = r'초과\s*수요|excess\s*demand'
        if re.search(excess, ta, re.I) and re.search(excess, tb, re.I): return True
        # Same capacity/backlog milestone; numeric changes remain new events.
        for sig in [r'우즈베키스탄|Uzbekistan', r'수주\s*잔고|backlog', r'수율|yield']:
            if re.search(sig, ta, re.I) and re.search(sig, tb, re.I):
                nums_a = set(re.findall(r'\d[\d,.]*\s*(?:만\s*대|대|개|%|억원|억)', ta))
                nums_b = set(re.findall(r'\d[\d,.]*\s*(?:만\s*대|대|개|%|억원|억)', tb))
                if nums_a == nums_b or not nums_a or not nums_b: return True
    return False


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()

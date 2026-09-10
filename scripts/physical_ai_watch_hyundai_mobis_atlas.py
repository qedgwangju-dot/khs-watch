#!/usr/bin/env python3
"""Add Hyundai Mobis × Boston Dynamics Atlas actuator commercialization lane.

Tracks the value chain rather than generic humanoid headlines:
Atlas supply agreement -> physical actuator reveal -> PPAP/ISIR/reliability and
production-line validation -> actuator capacity/plant ramp -> additional robot
components and external OEM customers.

Guardrails:
- Hyundai Mobis and Boston Dynamics officially confirm actuator supply for Atlas.
- Media/analyst wording such as "all/100%/exclusive actuator supply" is NOT
  promoted to an official fact unless an official source explicitly says so.
- A concept or R&D Tech Day reveal is not mass production revenue.
- PPAP/ISIR/reliability/line validation are pre-mass-production milestones, not
  customer acceptance or booked revenue by themselves.
- Production capacity is not shipment volume; capacity additions are separated
  from actual Atlas build/deployment and external OEM orders.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_lg_factory_loop as lg

base = lg.base
ext = lg.ext

base.QUERIES.extend([
    '("현대모비스" OR "Hyundai Mobis") (아틀라스 OR Atlas OR "Boston Dynamics" OR 보스턴다이내믹스) (액추에이터 OR actuator) (공급 OR supply OR 공개 OR unveil OR 테크데이 OR "Tech Day" OR 양산 OR "mass production")',
    '("현대모비스" OR "Hyundai Mobis") (액추에이터 OR actuator) (PPAP OR ISIR OR "고객 승인" OR qualification OR 신뢰성 OR reliability OR 검증 OR validation OR 수율 OR yield OR 양산라인 OR "production line") (로봇 OR robot OR 아틀라스 OR Atlas)',
    '("현대모비스" OR "Hyundai Mobis") (아틀라스 OR Atlas OR 휴머노이드 OR humanoid) (35만 OR 350000 OR 350,000 OR 93만 OR 930000 OR 생산능력 OR capacity OR 공장 OR plant OR 라인 OR line OR 증설 OR expansion)',
    '("현대모비스" OR "Hyundai Mobis") (로보틱스 OR robotics OR 휴머노이드 OR humanoid) (그리퍼 OR gripper OR 센서 OR sensor OR 제어기 OR controller OR 배터리팩 OR "battery pack") (공급 OR supply OR 고객 OR customer OR 양산 OR mass production OR 개발 OR development)',
    '("현대모비스" OR "Hyundai Mobis") (액추에이터 OR actuator OR 로봇부품 OR "robot components") (신규 고객 OR "new customer" OR 외부 고객 OR "external customer" OR OEM OR 수주 OR order OR contract OR 계약 OR award) (로봇 OR robot OR humanoid OR 휴머노이드)',
    '("Boston Dynamics" OR 보스턴다이내믹스) (Atlas OR 아틀라스) ("Hyundai Mobis" OR 현대모비스) (actuator OR 액추에이터 OR supply OR 공급 OR production OR 양산 OR validation OR 검증)',
])

base.TRUSTED.update({
    '아주경제', '서울경제', '조선비즈', '머니투데이', '연합뉴스', '한국경제',
    '매일경제', '전자신문', '이데일리', 'Reuters',
})
base.OFFICIAL_OR_PRIMARY.update({
    '현대모비스', 'Hyundai Mobis', 'MOBIS Newsroom', 'Hyundai Mobis Newsroom',
    'Boston Dynamics', '현대자동차그룹', 'Hyundai Motor Group',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_same_event = ext._same_event

MOBIS = re.compile(r'현대모비스|Hyundai\s*Mobis', re.I)
ATLAS = re.compile(r'아틀라스|\bAtlas\b|Boston\s*Dynamics|보스턴\s*다이내믹스|보스턴다이내믹스', re.I)
ACTUATOR = re.compile(r'액추에이터|actuator', re.I)
TECH_DAY = re.compile(r'R&D\s*테크데이|테크데이|R&D\s*Tech\s*Day|Tech\s*Day|최초\s*공개|첫\s*공개|unveil|reveal', re.I)
SUPPLY = re.compile(r'공급|supply|supplier|납품|shipment|customer|고객|계약|contract|수주|order|award', re.I)
VALIDATION = re.compile(r'\bPPAP\b|\bISIR\b|고객\s*승인|qualification|신뢰성|reliability|검증|validation|시험|test|수율|yield|양산\s*라인|production\s*line|초기\s*양산|initial\s*production', re.I)
CAPACITY = re.compile(r'35만|350,?000|93만|930,?000|생산\s*능력|capacity|공장|plant|라인|line|증설|expansion|착공|groundbreaking|장비\s*반입|equipment\s*move-in|가동|ramp', re.I)
COMPONENT_EXPANSION = re.compile(r'그리퍼|gripper|센서|sensor|제어기|controller|배터리\s*팩|battery\s*pack|robot\s*components?|로봇\s*부품', re.I)
EXTERNAL_CUSTOMER = re.compile(r'신규\s*고객|new\s*customer|외부\s*고객|external\s*customer|\bOEM\b|고객사|customer', re.I)
MASS_PRODUCTION = re.compile(r'양산|mass\s*production|본격\s*생산|series\s*production', re.I)
ALL_SUPPLY = re.compile(r'전량|100\s*%|전부|모든\s*액추에이터|all\s+(?:of\s+the\s+)?actuators?|exclusive|독점|sole\s*supplier', re.I)
PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가|stock\s*price|shares?\s*(?:jump|rise|surge)', re.I)


def _is_mobis_atlas(text: str) -> bool:
    if not MOBIS.search(text):
        return False
    atlas_act = ATLAS.search(text) and ACTUATOR.search(text)
    validation = ACTUATOR.search(text) and VALIDATION.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드|Atlas|아틀라스', text, re.I)
    capacity = ACTUATOR.search(text) and CAPACITY.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드|Atlas|아틀라스', text, re.I)
    expansion = COMPONENT_EXPANSION.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드|Atlas|아틀라스', text, re.I)
    ext_customer = ACTUATOR.search(text) and EXTERNAL_CUSTOMER.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드', text, re.I)
    return bool(atlas_act or validation or capacity or expansion or ext_customer)


def topic_group(text: str) -> str | None:
    if _is_mobis_atlas(text):
        return 'hyundai_mobis_atlas'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'hyundai_mobis_atlas':
        return _orig_score(item)

    # Block pure stock-price/valuation headlines unless they contain a new operating milestone.
    operational = TECH_DAY.search(text) or VALIDATION.search(text) or CAPACITY.search(text) or SUPPLY.search(text) or COMPONENT_EXPANSION.search(text)
    if PRICE_ONLY.search(title) and not operational:
        return -20

    source = item.get('source') or ''
    s = 18
    if base.NUMERIC.search(text):
        s += 3
    if source in base.OFFICIAL_OR_PRIMARY:
        s += 7
    elif source in base.TRUSTED:
        s += 3

    # Atlas supply agreement/customer evidence.
    if ATLAS.search(text) and ACTUATOR.search(text) and SUPPLY.search(text):
        s += 8
    # Physical prototype/reveal is a step beyond concept-only collaboration news.
    if TECH_DAY.search(text) and ACTUATOR.search(text):
        s += 8
    # Customer-quality / reliability / production-line validation is the key pre-SOP gate.
    if VALIDATION.search(text):
        s += 9
    # Capacity/plant ramp is the volume-monetization gate.
    if CAPACITY.search(text):
        s += 9
    if re.search(r'35만|350,?000|93만|930,?000|3만\s*대|30,?000', text, re.I):
        s += 5
    # Expansion beyond actuators or beyond Atlas raises addressable content/customer base.
    if COMPONENT_EXPANSION.search(text):
        s += 6
    if EXTERNAL_CUSTOMER.search(text) and re.search(r'신규|new|외부|external|\bOEM\b|수주|order|contract|계약', text, re.I):
        s += 7
    if MASS_PRODUCTION.search(text):
        s += 5
    return s


def _subcat(text: str) -> str:
    if CAPACITY.search(text) and ACTUATOR.search(text):
        return '액추에이터 생산능력·공장 증설'
    if VALIDATION.search(text) and ACTUATOR.search(text):
        return '고객 승인·신뢰성·양산검증'
    if COMPONENT_EXPANSION.search(text) or (EXTERNAL_CUSTOMER.search(text) and re.search(r'신규|new|외부|external|\bOEM\b', text, re.I)):
        return '로봇부품 확장·외부 고객'
    if TECH_DAY.search(text) and ACTUATOR.search(text):
        return '아틀라스 액추에이터 실물 공개'
    if ATLAS.search(text) and ACTUATOR.search(text) and SUPPLY.search(text):
        return '아틀라스 액추에이터 공급'
    return '아틀라스 액추에이터 양산 전환'


def category(text: str, group: str) -> str:
    if group == 'hyundai_mobis_atlas':
        return f"현대모비스 · {_subcat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '아틀라스 액추에이터 공급':
        return '현대모비스가 보스턴다이내믹스 Atlas를 첫 로보틱스 고객으로 확보해 자동차 부품 양산 역량을 휴머노이드 핵심 구동부품 매출로 옮기는 신호입니다. 공식자료가 확인하는 것은 Atlas 액추에이터 공급이며 전량·독점 여부는 별도 원문이 필요합니다.'
    if raw == '아틀라스 액추에이터 실물 공개':
        return '공급 합의·컨셉에서 실제 개발 하드웨어 공개로 한 단계 진전한 신호입니다. 다음 재평가 지점은 고객 품질 승인, 신뢰성 시험, 양산라인 검증과 실제 생산능력 구축입니다.'
    if raw == '고객 승인·신뢰성·양산검증':
        return 'PPAP·ISIR·신뢰성 시험·양산라인 검증은 개발품을 양산 매출로 바꾸는 핵심 문턱입니다. 승인 완료일, 초기 수율, 검사 시간과 첫 양산 납품이 확인되면 매출 가시성이 크게 높아집니다.'
    if raw == '액추에이터 생산능력·공장 증설':
        return '액추에이터 생산능력이 Atlas 실제 생산대수와 맞물리는 단계입니다. 생산능력 숫자와 대당 탑재량을 곱해 대응 가능한 로봇 대수와 잠재 매출을 다시 계산하고, 장비 반입·가동 시점까지 추적합니다.'
    if raw == '로봇부품 확장·외부 고객':
        return 'Atlas 액추에이터를 시작점으로 그리퍼·센서·제어기·배터리팩이나 Boston Dynamics 이외 OEM까지 고객·부품 범위가 확장되는 신호입니다. 고객 실명과 양산 계약이 확인될 때 재평가 폭이 커집니다.'
    if raw == '아틀라스 액추에이터 양산 전환':
        return '현대모비스의 Atlas 액추에이터가 개발·검증에서 실제 양산·납품으로 이동하는지 확인하는 신호입니다. 고객 승인, 생산능력, 수율, 첫 출하를 순서대로 봅니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '아틀라스 액추에이터 공급':
        return '공식 공급 합의와 전량·독점 공급은 다릅니다. 보도나 증권사에서 전량·100%를 언급해도 현대모비스·Boston Dynamics 공식 원문에 같은 범위가 없으면 확정 사실로 승격하지 않습니다.'
    if raw == '아틀라스 액추에이터 실물 공개':
        return 'R&D 테크데이 실물 공개는 양산 승인이나 매출 발생이 아닙니다. 설계변경, 감속기 수명·백래시, 모터 발열, 센서 보정과 고객 검증에서 일정이 밀릴 수 있습니다.'
    if raw == '고객 승인·신뢰성·양산검증':
        return '가장 현실적인 실패 경로는 성능은 충족하지만 신뢰성·PPAP 또는 초기 수율이 목표에 못 미쳐 양산 승인이 지연되는 경우입니다. 재시험 횟수, 불량·재작업률, 승인 완료 시점이 먼저 악화됩니다.'
    if raw == '액추에이터 생산능력·공장 증설':
        return '생산능력은 실제 출하량이 아닙니다. 주문보다 증설이 앞서면 감가상각·운전자본 부담이 먼저 커지고, Atlas 생산 일정이 늦어지면 가동률이 낮아질 수 있습니다.'
    if raw == '로봇부품 확장·외부 고객':
        return '개발 범위 확대나 고객 협의는 양산 계약과 다릅니다. 고객 실명·부품 규격·수량·평균판매단가·양산 시작일이 없으면 기대 단계로 분리합니다.'
    if raw == '아틀라스 액추에이터 양산 전환':
        return '양산 전환의 핵심 위험은 수율·발열·내구성·인증 지연입니다. 2027~2028년 생산라인 램프와 Atlas 실제 배치 일정이 어긋나는지 확인합니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group != 'hyundai_mobis_atlas':
        return _orig_verification(item, group, text)
    src = item.get('source') or ''
    all_claim = bool(ALL_SUPPLY.search(text) and ACTUATOR.search(text))
    if src in {'현대모비스', 'Hyundai Mobis', 'MOBIS Newsroom', 'Hyundai Mobis Newsroom'}:
        return '현대모비스 공식자료' + (' · 전량/독점 범위 문구 직접 확인' if all_claim else '')
    if src == 'Boston Dynamics':
        return 'Boston Dynamics 공식자료 · 현대모비스 자료 교차확인'
    if src in {'현대자동차그룹', 'Hyundai Motor Group'}:
        return '현대자동차그룹 공식자료 · 현대모비스/Boston Dynamics 교차확인'
    if src in base.TRUSTED:
        if all_claim:
            return '신뢰 매체 보도 · 공식자료는 Atlas 액추에이터 공급까지만 확인, 전량·독점 여부 원문 추가확인 필요'
        if TECH_DAY.search(text):
            return '신뢰 매체 현장보도 · 현대모비스 공식 공급자료와 교차확인'
        return '신뢰 매체 보도 · 현대모비스/Boston Dynamics 공식자료 교차확인'
    return '보도 단계 · 현대모비스/Boston Dynamics 공식 원문 재확인 필요'


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'hyundai_mobis_atlas' or b.get('group') != 'hyundai_mobis_atlas':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"

    # Sep. 2026 R&D Tech Day / first physical actuator reveal syndicated across media.
    reveal = r'R&D\s*테크데이|테크데이|Tech\s*Day|최초\s*공개|첫\s*공개|unveil|reveal'
    if ACTUATOR.search(ta) and ACTUATOR.search(tb) and re.search(reveal, ta, re.I) and re.search(reveal, tb, re.I):
        return True

    # CES 2026 Atlas actuator supply agreement rewrites.
    supply_sig = r'CES\s*2026|공급(?:키로|하기로|계약|합의)|supply\s+(?:agreement|actuators?)|first\s+robotics\s+customer|첫\s*고객'
    if ATLAS.search(ta) and ATLAS.search(tb) and ACTUATOR.search(ta) and ACTUATOR.search(tb) and re.search(supply_sig, ta, re.I) and re.search(supply_sig, tb, re.I):
        return True

    # Same quality-validation milestone across job-posting/news rewrites.
    qual_sig = r'\bPPAP\b|\bISIR\b|고객\s*승인|qualification|신뢰성|reliability|양산\s*라인|production\s*line'
    if ACTUATOR.search(ta) and ACTUATOR.search(tb) and re.search(qual_sig, ta, re.I) and re.search(qual_sig, tb, re.I):
        return True

    # Same capacity milestone when both mention the same anchor quantity.
    for sig in [r'35만|350,?000', r'93만|930,?000', r'3만\s*대|30,?000']:
        if re.search(sig, ta, re.I) and re.search(sig, tb, re.I) and ACTUATOR.search(ta) and ACTUATOR.search(tb):
            return True
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

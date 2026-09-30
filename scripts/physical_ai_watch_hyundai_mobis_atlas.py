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

import hashlib
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
    '("현대모비스" OR "Hyundai Mobis") (Atlas OR 아틀라스) (액추에이터 OR actuator) (수주 OR 발주 OR order OR "purchase order" OR 계약금액 OR contract OR volume OR 물량 OR ASP OR 단가 OR 첫출하 OR "first shipment")',
    '("현대모비스" OR "Hyundai Mobis") (램프 OR lamp OR lighting OR 조명) ("OPmobility" OR "OP Mobility" OR "Plastic Omnium") (매각 OR sale OR disposal OR divest OR acquisition OR 인수 OR 본계약 OR SPA OR closing OR 종결 OR 완료 OR 분할 OR "spin-off" OR 주주총회 OR 기업결합 OR antitrust OR 가처분 OR injunction OR 소송 OR litigation)',
    '("현대모비스" OR "Hyundai Mobis") ("OPmobility" OR "OP Mobility") (주주총회 OR shareholder OR 기업결합 OR antitrust OR regulatory OR 분할 OR spin-off OR closing OR 종결 OR 완료 OR 매각대금 OR proceeds OR 처분이익 OR disposal gain OR 지연 OR delay OR 가처분 OR injunction OR termination)',
    'site:opmobility.com ("Hyundai Mobis" OR 현대모비스) (lighting OR lamp) (acquisition OR acquire OR closing OR completion OR regulatory OR 600)',
    'site:mobis.com (OPmobility OR 램프 OR lighting) (매각 OR 분할 OR 주주총회 OR 기업결합 OR 종결 OR 완료 OR 반도체 OR 로보틱스 OR 전동화 OR 설비투자)',
])

base.TRUSTED.update({
    '아주경제', '서울경제', '조선비즈', '머니투데이', '연합뉴스', '한국경제',
    '매일경제', '전자신문', '이데일리', 'SBS Biz', 'Reuters',
})
base.OFFICIAL_OR_PRIMARY.update({
    '현대모비스', 'Hyundai Mobis', 'MOBIS Newsroom', 'Hyundai Mobis Newsroom',
    'Boston Dynamics', '현대자동차그룹', 'Hyundai Motor Group',
    'OPmobility', 'OP Mobility',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_tag_for = base.tag_for
_orig_select_diverse = base.select_diverse
_orig_clean_title = base.clean_title
_orig_same_event = ext._same_event

MOBIS = re.compile(r'현대모비스|Hyundai\s*Mobis', re.I)
ATLAS = re.compile(r'아틀라스|Atlas(?:용)?|Boston\s*Dynamics|보스턴\s*다이내믹스|보스턴다이내믹스', re.I)
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
FIRST_SHIPMENT = re.compile(r'첫\s*(?:양산\s*)?(?:납품|출하)|초도\s*(?:납품|출하)|first\s+(?:production\s+)?(?:shipment|delivery)', re.I)
ACTUAL_SOP = re.compile(r'양산\s*(?:개시|시작|돌입|착수)|mass\s*production\s*(?:started|began|commenced)|series\s*production\s*(?:started|began|commenced)|\bSOP\b', re.I)
ATLAS_DELAY = re.compile(r'(?:양산|SOP|고객\s*승인|신뢰성|수율).{0,50}(?:연기|지연|실패|문제|미달)|(?:production|SOP|qualification|reliability|yield).{0,50}(?:delay|postpone|fail|issue)', re.I)
ATLAS_FORMAL_ORDER = re.compile(r'수주|발주|purchase\s*order|production\s*order|양산\s*계약|mass\s*production\s*contract|공급\s*계약|supply\s*contract|contract\s*(?:signed|awarded)|계약\s*금액|contract\s*value', re.I)
ATLAS_ORDER_EVIDENCE = re.compile(r'\d[\d,.]*\s*(?:개|대|억원|억|조원|원|USD|달러|units?|actuators?)|물량|volume|quantity|평균판매단가|ASP|계약\s*금액|contract\s*value|수주|발주|purchase\s*order|production\s*order|양산\s*계약', re.I)

LAMP = re.compile(r'램프|lamp|lighting|조명', re.I)
OPMOBILITY = re.compile(r'OP\s*mobility|OPmobility|Plastic\s*Omnium|플라스틱\s*옴니엄', re.I)
DIVEST = re.compile(r'매각|sale|sell|disposal|divest|acquir|인수|본계약|SPA|주식매매계약', re.I)
LAMP_BASELINE = re.compile(r'6,?000\s*억|600\s*(?:billion|bn)\s*(?:KRW|won)|100\s*%|본계약|\bSPA\b|definitive\s+agreement|final\s+agreement|acquire\s+100', re.I)
SPINOFF = re.compile(r'물적\s*분할|분할\s*법인|spin[-\s]?off|carve[-\s]?out|신설\s*법인', re.I)
SPINOFF_COMPLETE = re.compile(r'(?:물적\s*분할|분할\s*법인|spin[-\s]?off).{0,70}(?:완료|효력\s*발생|등기\s*완료|completed|effective)|(?:완료|효력\s*발생|completed|effective).{0,70}(?:물적\s*분할|spin[-\s]?off)', re.I)
SHAREHOLDER_APPROVED = re.compile(r'(?:주주총회|shareholders?).{0,70}(?:가결|승인(?:했다|함|완료)|approved)|(?:가결|승인(?:했다|함|완료)|approved).{0,70}(?:주주총회|shareholders?)', re.I)
REGULATORY_APPROVED = re.compile(r'(?:기업결합|공정거래위원회|antitrust|merger\s+control|competition\s+authority|regulatory).{0,90}(?:승인(?:했다|함|완료)|approved|clearance|cleared)|(?:승인(?:했다|함|완료)|approved|clearance|cleared).{0,90}(?:기업결합|antitrust|merger\s+control|competition\s+authority|regulatory)', re.I)
CLOSING = re.compile(r'거래\s*(?:종결|완료)(?:했다|됨|됐다|\b)|매각\s*완료|인수\s*완료|closing\s*(?:completed|complete|closed)|transaction\s*(?:completed|closed)|completion\s+of\s+the\s+transaction', re.I)
PROCEEDS = re.compile(r'매각\s*대금|현금\s*유입|대금\s*수령|proceeds|cash\s+proceeds|payment\s+received', re.I)
DISPOSAL_RESULT = re.compile(r'처분\s*(?:이익|손실)|매각\s*(?:이익|손실)|disposal\s*(?:gain|loss)|gain\s+on\s+sale|loss\s+on\s+sale', re.I)
REINVEST_TARGET = re.compile(r'차량용\s*반도체|automotive\s*semiconductor|로보틱스|robotics|전동화|electrification', re.I)
REINVEST_ACTION = re.compile(r'투자\s*(?:결정|공시|집행|확정|착수)|신규\s*시설|시설\s*투자|설비\s*투자|capex|investment\s*(?:approved|announced|committed)', re.I)
ADVERSE = re.compile(r'가처분.{0,80}(?:신청|소송).{0,40}(?:접수|제기|냈|신청했다|인용|기각|각하)|가처분.{0,40}(?:인용|기각|각하)|injunction.{0,40}(?:filed|granted|denied|blocked)|소송.{0,60}(?:제기(?:했다|됨|됐다)|접수(?:했다|됨|됐다)|filed)|litigation.{0,40}(?:filed|commenced)|(?:일정|종결|closing).{0,40}(?:연기|지연|postpone|delay)|조건부\s*승인|conditional\s+approval|가격\s*(?:조정|인하)|purchase\s*price\s*adjust|해지|termination|terminated|철회|withdraw|불승인|rejected|blocked', re.I)


def _atlas_stage(text: str) -> str:
    if ATLAS_DELAY.search(text):
        return 'delay'
    if FIRST_SHIPMENT.search(text) and ACTUATOR.search(text):
        return 'first_shipment'
    if ACTUAL_SOP.search(text) and ACTUATOR.search(text):
        return 'mass_production'
    if ATLAS_FORMAL_ORDER.search(text) and ATLAS_ORDER_EVIDENCE.search(text) and ACTUATOR.search(text):
        return 'formal_order'
    if VALIDATION.search(text) and ACTUATOR.search(text):
        return 'validation'
    if CAPACITY.search(text) and ACTUATOR.search(text):
        return 'capacity'
    if ACTUATOR.search(text) and EXTERNAL_CUSTOMER.search(text) and re.search(r'신규|new|외부|external|\bOEM\b|수주|order|contract|계약', text, re.I):
        return 'external_customer'
    if COMPONENT_EXPANSION.search(text) and re.search(r'공급|납품|수주|계약|양산|supply|shipment|order|contract|mass\s*production|customer|고객', text, re.I):
        return 'component_expansion'
    if TECH_DAY.search(text) and ACTUATOR.search(text):
        return 'baseline_reveal'
    if ATLAS.search(text) and ACTUATOR.search(text) and SUPPLY.search(text):
        return 'baseline_supply'
    return 'monitor'


def _lamp_stage(text: str) -> str:
    if ADVERSE.search(text):
        return 'adverse'
    if CLOSING.search(text):
        return 'closing'
    if DISPOSAL_RESULT.search(text):
        return 'disposal_result'
    if PROCEEDS.search(text) and re.search(r'수령|유입|received|입금|납입', text, re.I):
        return 'proceeds'
    if SPINOFF_COMPLETE.search(text):
        return 'spinoff_complete'
    if REGULATORY_APPROVED.search(text):
        return 'regulatory_approval'
    if SHAREHOLDER_APPROVED.search(text):
        return 'shareholder_approval'
    if REINVEST_TARGET.search(text) and REINVEST_ACTION.search(text):
        return 'reinvestment'
    if LAMP_BASELINE.search(text) and DIVEST.search(text):
        return 'baseline_spa'
    if SPINOFF.search(text) and re.search(r'예정|계획|will|expected|plan|2027', text, re.I):
        return 'baseline_plan'
    return 'monitor'


def _is_mobis_atlas(text: str) -> bool:
    if not MOBIS.search(text):
        return False
    atlas_act = ATLAS.search(text) and ACTUATOR.search(text)
    validation = ACTUATOR.search(text) and VALIDATION.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드|Atlas|아틀라스', text, re.I)
    capacity = ACTUATOR.search(text) and CAPACITY.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드|Atlas|아틀라스', text, re.I)
    expansion = COMPONENT_EXPANSION.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드|Atlas|아틀라스', text, re.I)
    ext_customer = ACTUATOR.search(text) and EXTERNAL_CUSTOMER.search(text) and re.search(r'로봇|robot|humanoid|휴머노이드', text, re.I)
    return bool(atlas_act or validation or capacity or expansion or ext_customer)


def _is_mobis_lamp(text: str) -> bool:
    if not MOBIS.search(text):
        return False
    lamp_named = LAMP.search(text) and (OPMOBILITY.search(text) or DIVEST.search(text) or SPINOFF.search(text))
    deal_named = OPMOBILITY.search(text) and (DIVEST.search(text) or PROCEEDS.search(text) or REINVEST_TARGET.search(text) or ADVERSE.search(text) or CLOSING.search(text))
    return bool(lamp_named or deal_named)


def topic_group(text: str) -> str | None:
    if _is_mobis_lamp(text):
        return 'mobis_lamp_divestiture'
    if _is_mobis_atlas(text):
        return 'hyundai_mobis_atlas'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)

    if group == 'mobis_lamp_divestiture':
        stage = _lamp_stage(text)
        # 2026-09-30 SPA (100%, EV KRW 600bn) and the announced spin-off plan are baselines.
        if stage in {'baseline_spa', 'baseline_plan', 'monitor'}:
            return 0
        if PRICE_ONLY.search(title):
            return -20
        source = item.get('source') or ''
        s = 20
        if base.NUMERIC.search(text):
            s += 3
        if source in base.OFFICIAL_OR_PRIMARY:
            s += 8
        elif source in base.TRUSTED:
            s += 4
        s += {
            'shareholder_approval': 8,
            'regulatory_approval': 10,
            'spinoff_complete': 11,
            'closing': 15,
            'proceeds': 12,
            'disposal_result': 12,
            'reinvestment': 11,
            'adverse': 14,
        }.get(stage, 0)
        return s

    if group != 'hyundai_mobis_atlas':
        return _orig_score(item)

    stage = _atlas_stage(text)
    # CES supply agreement and Sep-2026 Tech Day reveal are baselines, not fresh alerts.
    if stage in {'baseline_supply', 'baseline_reveal', 'monitor'}:
        return 0
    if PRICE_ONLY.search(title):
        return -20

    source = item.get('source') or ''
    s = 18
    if base.NUMERIC.search(text):
        s += 3
    if source in base.OFFICIAL_OR_PRIMARY:
        s += 7
    elif source in base.TRUSTED:
        s += 3
    s += {
        'validation': 10,
        'capacity': 10,
        'formal_order': 14,
        'mass_production': 16,
        'first_shipment': 17,
        'external_customer': 13,
        'component_expansion': 11,
        'delay': 14,
    }.get(stage, 0)
    return s


def _subcat(text: str) -> str:
    stage = _atlas_stage(text)
    return {
        'baseline_supply': '아틀라스 액추에이터 공급',
        'baseline_reveal': '아틀라스 액추에이터 실물 공개',
        'validation': '고객 승인·신뢰성·양산검증',
        'capacity': '액추에이터 생산능력·공장 증설',
        'formal_order': '아틀라스 액추에이터 양산계약·수주',
        'mass_production': '아틀라스 액추에이터 실제 양산 개시',
        'first_shipment': '아틀라스 액추에이터 첫 양산 출하',
        'external_customer': '액추에이터 외부 OEM 신규 고객',
        'component_expansion': '로봇부품 공급 범위 확대',
        'delay': '아틀라스 액추에이터 양산·검증 지연',
    }.get(stage, '아틀라스 액추에이터 양산 전환')


def category(text: str, group: str) -> str:
    if group == 'hyundai_mobis_atlas':
        return f"현대모비스 · {_subcat(text)}"
    if group == 'mobis_lamp_divestiture':
        return {
            'baseline_spa': '현대모비스 램프 매각 · 2026-09-30 SPA 기준선',
            'baseline_plan': '현대모비스 램프 매각 · 분할·종결 계획 기준선',
            'shareholder_approval': '현대모비스 램프 매각 · 주주총회 승인',
            'regulatory_approval': '현대모비스 램프 매각 · 기업결합·규제 승인',
            'spinoff_complete': '현대모비스 램프 매각 · 물적분할 완료',
            'closing': '현대모비스 램프 매각 · 거래 종결',
            'proceeds': '현대모비스 램프 매각 · 실제 매각대금 유입',
            'disposal_result': '현대모비스 램프 매각 · 처분손익 확정',
            'reinvestment': '현대모비스 램프 매각 · 미래사업 자금 재배치',
            'adverse': '현대모비스 램프 매각 · 소송·지연·조건변경',
        }.get(_lamp_stage(text), '현대모비스 램프 매각 · 후속 절차')
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if cat.startswith('현대모비스 램프 매각'):
        mapping = {
            '주주총회 승인': 'SPA 이후 내부 승인 절차가 실제로 통과한 단계입니다. 다음 확인은 물적분할 효력 발생과 기업결합·규제 승인입니다.',
            '기업결합·규제 승인': '거래 종결의 외부 규제 조건이 해소되는 단계입니다. 승인 조건과 남은 선행조건, 실제 종결일을 확인합니다.',
            '물적분할 완료': '램프 사업을 매각 가능한 별도 법인으로 떼어내는 법적 실행 단계가 끝났다는 신호입니다. 신설법인 자산·부채 범위와 종결 조건을 확인합니다.',
            '거래 종결': '본계약이 실제 소유권 이전으로 바뀐 단계입니다. 기업가치 6,000억원과 실제 지분매각대금의 차이, 순차입금·운전자본 조정을 확인합니다.',
            '실제 매각대금 유입': '기업가치가 아니라 현대모비스가 실제로 받은 현금이 확인되는 단계입니다. 금액과 수령일, 자금 사용처를 추적합니다.',
            '처분손익 확정': '램프 매각이 손익계산서와 자본효율에 실제로 반영되는 단계입니다. 장부가·거래비용을 분리해 일회성 처분손익과 본업 이익을 구분합니다.',
            '미래사업 자금 재배치': '매각 명분이 차량용 반도체·로보틱스·전동화의 실제 설비투자·연구개발 집행으로 바뀌는 단계입니다. 투자액·생산능력·양산일·예상 매출을 확인합니다.',
            '소송·지연·조건변경': 'SPA 체결 뒤 남은 노조·법원·규제·가격조정·종결 조건에서 일정이나 현금회수가 나빠지는 역방향 신호입니다.',
        }
        return mapping.get(raw, '2026-09-30 SPA는 기준선입니다. 이후 승인·분할·종결·현금유입·재투자처럼 실제 사업 상태가 바뀔 때만 알립니다.')
    if raw == '아틀라스 액추에이터 공급':
        return '현대모비스가 보스턴다이내믹스 Atlas를 첫 로보틱스 고객으로 확보한 2026년 기준선입니다. 같은 공급 합의 반복기사는 침묵합니다.'
    if raw == '아틀라스 액추에이터 실물 공개':
        return '2026년 R&D 테크데이 실물 공개는 개발 기준선입니다. 고객 승인·실제 양산·첫 출하가 확인될 때 다음 단계로 올립니다.'
    if raw == '고객 승인·신뢰성·양산검증':
        return 'PPAP·ISIR·신뢰성 시험·양산라인 검증은 개발품을 양산 매출로 바꾸는 핵심 문턱입니다. 승인 완료일, 초기 수율, 검사 시간과 첫 양산 납품을 추적합니다.'
    if raw == '액추에이터 생산능력·공장 증설':
        return '실제 액추에이터 생산능력 확대로 이동한 신호입니다. Atlas 생산대수와 대당 탑재량, 장비 반입·가동률을 연결합니다.'
    if raw == '아틀라스 액추에이터 양산계약·수주':
        return 'CES 공급 협력이라는 기준선에서 실제 양산 발주·수주 또는 계약금액·물량이 확인되는 단계입니다. 물량×단가와 납기, 매출 인식 시점을 추적합니다.'
    if raw == '아틀라스 액추에이터 실제 양산 개시':
        return '공급 합의와 개발 공개를 넘어 실제 SOP가 시작된 단계입니다. 초기 수율·가동률·출하량과 매출 인식 시점을 확인합니다.'
    if raw == '아틀라스 액추에이터 첫 양산 출하':
        return '현대모비스 Atlas 액추에이터가 처음으로 실제 고객 출하에 연결된 단계입니다. 수량·단가·반복 주문 여부를 확인합니다.'
    if raw == '액추에이터 외부 OEM 신규 고객':
        return 'Boston Dynamics 외부 로봇 OEM으로 고객 기반이 확장되는 재평가 신호입니다. 고객 실명·계약물량·양산일을 확인합니다.'
    if raw == '로봇부품 공급 범위 확대':
        return '액추에이터 외 그리퍼·센서·제어기·배터리팩 등으로 실제 공급 범위가 넓어지는 신호입니다. 단순 개발과 양산 공급을 구분합니다.'
    if raw == '아틀라스 액추에이터 양산·검증 지연':
        return 'Atlas 액추에이터의 고객 승인·수율·신뢰성·양산 일정이 후퇴하는 역방향 신호입니다. 지연 원인과 새 SOP 일정을 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if cat.startswith('현대모비스 램프 매각'):
        if raw == '소송·지연·조건변경':
            return '가처분·기업결합 조건·가격조정·종결 연기가 실제 closing과 현금 유입을 늦출 수 있습니다. 법원 결정·규제 승인 조건·변경 SPA를 우선 확인합니다.'
        if raw in {'거래 종결', '실제 매각대금 유입', '처분손익 확정'}:
            return '기업가치 6,000억원과 실제 현금수령액·처분이익은 같은 숫자가 아닙니다. 순차입금·운전자본·장부가·거래비용을 분리합니다.'
        if raw == '미래사업 자금 재배치':
            return '매각대금이 미래사업에 실제 투입돼도 고객 승인·가동률·수익성이 따라오지 않으면 총자산이익률 개선이 늦어질 수 있습니다.'
        return 'SPA 체결은 종결이 아닙니다. 주총·분할·기업결합 승인·소송·종결 조건을 통과해야 실제 현금 회수로 이어집니다.'
    if raw == '아틀라스 액추에이터 공급':
        return '공식 공급 합의와 전량·독점 공급은 다릅니다. 2026년 공급 발표 반복만으로 새 알림을 보내지 않습니다.'
    if raw == '아틀라스 액추에이터 실물 공개':
        return '실물 공개는 양산 승인이나 매출 발생이 아닙니다. 설계변경, 감속기 수명·백래시, 모터 발열, 센서 보정과 고객 검증이 남습니다.'
    if raw == '고객 승인·신뢰성·양산검증':
        return '가장 현실적인 실패 경로는 신뢰성·PPAP 또는 초기 수율 미달로 SOP가 밀리는 경우입니다. 재시험·불량·재작업률이 먼저 악화됩니다.'
    if raw == '액추에이터 생산능력·공장 증설':
        return '생산능력은 실제 출하량이 아닙니다. 주문보다 증설이 앞서면 감가상각·운전자본 부담이 먼저 커질 수 있습니다.'
    if raw == '아틀라스 액추에이터 양산계약·수주':
        return '공급 협력 발표와 실제 양산 발주는 다릅니다. 계약 상대·물량·단가·납기 중 최소 하나의 새 증거가 없으면 기준선 반복으로 처리합니다.'
    if raw == '아틀라스 액추에이터 실제 양산 개시':
        return 'SOP와 안정 양산은 다릅니다. 초기 수율·발열·내구성·가동률이 낮으면 매출 램프가 지연될 수 있습니다.'
    if raw == '아틀라스 액추에이터 첫 양산 출하':
        return '첫 출하는 반복 주문을 보장하지 않습니다. 후속 월별 출하량·고객 배치·보증 이슈를 확인합니다.'
    if raw in {'액추에이터 외부 OEM 신규 고객', '로봇부품 공급 범위 확대'}:
        return '협의·공동개발은 양산 계약이 아닙니다. 고객 실명·수량·평균판매단가·양산 시작일이 없으면 기대 단계로 남깁니다.'
    if raw == '아틀라스 액추에이터 양산·검증 지연':
        return '지연이 Atlas 본체 일정인지 현대모비스 부품 수율·신뢰성 문제인지 분리해야 합니다. 새 일정과 원인 공개가 다음 핵심 신호입니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    src = item.get('source') or ''
    if group == 'mobis_lamp_divestiture':
        if src in {'OPmobility', 'OP Mobility'}:
            return 'OPmobility 공식자료 · 현대모비스/규제기관 자료 교차확인'
        if src in {'현대모비스', 'Hyundai Mobis', 'MOBIS Newsroom', 'Hyundai Mobis Newsroom'}:
            return '현대모비스 공식자료 · OPmobility 자료 교차확인'
        if src in base.TRUSTED:
            return '신뢰 매체 보도 · 현대모비스·OPmobility·규제기관 공식자료 재확인'
        return '보도 단계 · 현대모비스·OPmobility 공식 원문 재확인 필요'
    if group != 'hyundai_mobis_atlas':
        return _orig_verification(item, group, text)
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
        return '신뢰 매체 보도 · 현대모비스/Boston Dynamics 공식자료 교차확인'
    return '보도 단계 · 현대모비스/Boston Dynamics 공식 원문 재확인 필요'


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    if group == 'hyundai_mobis_atlas':
        stage = _atlas_stage(text)
        return hashlib.sha256(f"hyundai-mobis-atlas|{stage}".encode()).hexdigest()
    if group == 'mobis_lamp_divestiture':
        stage = _lamp_stage(text)
        if stage == 'reinvestment':
            lanes = []
            for lane, pat in [('semiconductor', r'반도체|semiconductor'), ('robotics', r'로보틱스|robotics'), ('electrification', r'전동화|electrification')]:
                if re.search(pat, text, re.I):
                    lanes.append(lane)
            nums = '|'.join(sorted(set(re.findall(r'\d[\d,.]*\s*(?:억원|억|조원|원|%|KRW|won)', text, re.I)))[:4])
            sig = f"{','.join(lanes)}|{nums}"
        elif stage == 'adverse':
            if re.search(r'가처분|injunction|소송|litigation', text, re.I):
                sig = 'litigation'
            elif re.search(r'가격\s*(?:조정|인하)|purchase\s*price', text, re.I):
                sig = 'price-adjustment'
            elif re.search(r'해지|termination|terminated|철회|withdraw|불승인|rejected|blocked', text, re.I):
                sig = 'termination-or-rejection'
            else:
                sig = 'delay-or-conditions'
        else:
            sig = 'event'
        return hashlib.sha256(f"hyundai-mobis-lamp|{stage}|{sig}".encode()).hexdigest()
    return _orig_key(item)


def tag_for(group: str) -> str:
    if group == 'hyundai_mobis_atlas':
        return '현대모비스Atlas'
    if group == 'mobis_lamp_divestiture':
        return '현대모비스램프'
    return _orig_tag_for(group)


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    for group in ('mobis_lamp_divestiture', 'hyundai_mobis_atlas'):
        hit = next((x for x in candidates if x.get('group') == group), None)
        if not hit or any(x.get('key') == hit.get('key') for x in chosen):
            continue
        if len(chosen) < limit:
            chosen = [hit, *chosen]
        else:
            chosen = [hit, *chosen[:-1]]
    return chosen


def clean_title(title: str, source: str) -> str:
    text = f"{title} {source}"
    if _is_mobis_lamp(text):
        stage = _lamp_stage(text)
        return {
            'shareholder_approval': '현대모비스 램프 매각, 주주총회 승인 단계 통과',
            'regulatory_approval': '현대모비스 램프 매각, 기업결합·규제 승인 진전',
            'spinoff_complete': '현대모비스 램프사업 물적분할 완료',
            'closing': '현대모비스-OPmobility 램프사업 거래 종결',
            'proceeds': '현대모비스 램프 매각대금 실제 유입 확인',
            'disposal_result': '현대모비스 램프사업 처분손익 확정',
            'reinvestment': '현대모비스, 램프 매각재원 미래사업 실제 투자',
            'adverse': '현대모비스 램프 매각, 소송·지연·조건변경 발생',
        }.get(stage, _orig_clean_title(title, source))
    if _is_mobis_atlas(text):
        stage = _atlas_stage(text)
        return {
            'validation': '현대모비스 Atlas 액추에이터 고객 승인·신뢰성 검증 진전',
            'capacity': '현대모비스 로봇 액추에이터 생산능력 확대',
            'formal_order': '현대모비스 Atlas 액추에이터 양산계약·수주 확인',
            'mass_production': '현대모비스 Atlas 액추에이터 실제 양산 개시',
            'first_shipment': '현대모비스 Atlas 액추에이터 첫 양산 출하',
            'external_customer': '현대모비스 로봇 액추에이터 외부 OEM 신규 고객 확보',
            'component_expansion': '현대모비스 로봇부품 공급 범위 확대',
            'delay': '현대모비스 Atlas 액추에이터 양산·검증 일정 후퇴',
        }.get(stage, _orig_clean_title(title, source))
    return _orig_clean_title(title, source)


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
base.key = key
base.tag_for = tag_for
base.select_diverse = select_diverse
base.clean_title = clean_title
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()

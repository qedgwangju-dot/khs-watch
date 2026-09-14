#!/usr/bin/env python3
"""Add Hyundai Motor Group Atlas factory-rollout and Boston Dynamics capital-market lane.

Tracks two linked commercialization axes without creating a separate watcher:
1) Atlas site discussion -> pilot/test -> named process/deployment schedule -> robot count/capex -> operating validation -> broader rollout.
2) Boston Dynamics capital-market state -> IPO/valuation/ownership/losses -> external customers -> commercial scale/profitability.

Guardrails:
- A site discussion is not a deployment order.
- Production capacity is not shipment volume or booked robotics revenue.
- IPO timing or valuation commentary is not an official filing unless the company confirms it.
- Loss figures, ownership changes and external-customer milestones are tracked separately from factory rollout.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_humanoid_component_policy as policy

base = policy.base
ext = policy.ext

base.QUERIES.extend([
    '(현대자동차 OR 현대차 OR "Hyundai Motor" OR "Hyundai Motor Group") (아틀라스 OR Atlas OR "Boston Dynamics" OR 보스턴다이내믹스) (체코 OR Czech OR 노쇼비체 OR Nosovice OR Nošovice OR 유럽 OR Europe) (도입 OR 투입 OR 배치 OR 시험 OR 테스트 OR 논의 OR 협의 OR deploy OR deployment OR testing OR trial OR discuss OR rollout)',
    '("Hyundai Motor Manufacturing Czech" OR HMMC OR 노쇼비체 OR Nosovice OR Nošovice) (아틀라스 OR Atlas) ("Boston Dynamics" OR 보스턴다이내믹스 OR 본사 OR headquarters) (논의 OR 협의 OR 테스트 OR 시험 OR 운영 OR deployment OR discuss OR test OR operation)',
    '("Hyundai Motor Group" OR 현대자동차그룹) (아틀라스 OR Atlas) (글로벌 공장 OR 글로벌 생산기지 OR 해외 공장 OR global plants OR manufacturing sites) (확대 OR 확장 OR 배치 OR 적용 OR deployment OR rollout OR scale)',
    '(HMGMA OR 조지아 OR Georgia OR Savannah) (아틀라스 OR Atlas) (2028 OR 2030 OR 시퀀싱 OR sequencing OR 조립 OR assembly OR 배치 OR deployment)',
    '("Hyundai Motor Group" OR 현대자동차그룹 OR "Hyundai Motor") (아틀라스 OR Atlas) (3만대 OR 30,000 OR 30000 OR RMAC OR "Robot Metaplant Application Center") (생산 OR 양산 OR capacity OR 확대 OR expansion OR validation)',
    '("Boston Dynamics" OR 보스턴다이내믹스) (IPO OR "initial public offering" OR 기업공개 OR 상장 OR valuation OR 기업가치 OR 적자 OR 손실 OR loss OR losses OR profitability OR 수익성 OR 흑자 OR funding OR 자금조달 OR SoftBank OR 소프트뱅크 OR 지분 OR ownership)',
    '("Boston Dynamics" OR 보스턴다이내믹스) (Atlas OR 아틀라스) (external customer OR external customers OR 외부 고객 OR customer OR 고객 OR order OR 주문 OR sales OR 판매 OR commercial OR 상용화 OR deployment OR 배치) (2027 OR 2028 OR 2029 OR 2030 OR scale OR 양산)',
])

base.TRUSTED.update({
    '뉴시스', 'Newsis', '연합뉴스', '전자신문', '서울경제', '한국경제',
    '매일경제', '머니투데이', '조선비즈', 'Reuters', 'AutoSAP',
})
base.OFFICIAL_OR_PRIMARY.update({
    '현대자동차', 'Hyundai Motor', '현대자동차그룹', 'Hyundai Motor Group',
    'Boston Dynamics', 'Hyundai Motor Manufacturing Czech', 'HMMC',
    'AutoSAP', 'Sdružení automobilového průmyslu',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_clean_title = base.clean_title
_orig_same_event = ext._same_event

HMG = re.compile(
    r'현대자동차그룹|현대차그룹|현대자동차|현대차|Hyundai\s*Motor\s*Group|Hyundai\s*Motor|'
    r'Hyundai\s*Motor\s*Manufacturing\s*Czech|\bHMMC\b|\bHMGMA\b',
    re.I,
)
BOSTON = re.compile(r'Boston\s*Dynamics|보스턴\s*다이내믹스|보스턴다이내믹스', re.I)
ATLAS = re.compile(r'아틀라스|\bAtlas\b|Boston\s*Dynamics|보스턴\s*다이내믹스|보스턴다이내믹스', re.I)
PLANT = re.compile(
    r'공장|생산\s*기지|생산\s*라인|plant|factory|manufacturing\s*(?:site|plant|line)|'
    r'노쇼비체|Nosovice|Nošovice|체코|Czech|유럽|Europe|HMGMA|조지아|Georgia|Savannah',
    re.I,
)
ROLLOUT = re.compile(
    r'도입|투입|배치|적용|확대|확장|시험|테스트|검증|운영|논의|협의|검토|'
    r'deploy|deployment|rollout|trial|test|testing|validation|operation|adoption|'
    r'discuss|talks?|consider|scale',
    re.I,
)
DISCUSSION = re.compile(
    r'논의|협의|검토|도입\s*논의|가능한\s*한\s*빨리|희망|원한다|'
    r'discuss|talks?|consider|would\s+like|as\s+soon\s+as\s+possible',
    re.I,
)
PILOT = re.compile(r'시험|테스트|실증|검증|pilot|trial|test|testing|validation', re.I)
SCHEDULE = re.compile(
    r'2027|2028|2029|2030|시작|개시|도입\s*시기|투입\s*시점|배치\s*시점|'
    r'begin|starting|from\s+2028|by\s+2028|by\s+2030|scheduled|timeline',
    re.I,
)
PROCESS = re.compile(
    r'부품\s*시퀀싱|시퀀싱|sequencing|부품\s*배열|component\s*assembly|조립|assembly|'
    r'반복\s*작업|중량물|heavy\s*loads?|repetitive',
    re.I,
)
UNITS_CAPEX = re.compile(
    r'3만\s*대|30,?000|대\s*투입|대\s*배치|units?|설비\s*투자|투자액|capex|capacity|생산\s*능력',
    re.I,
)
EUROPE = re.compile(r'체코|Czech|노쇼비체|Nosovice|Nošovice|유럽|Europe|\bHMMC\b', re.I)
HMGMA = re.compile(r'HMGMA|조지아|Georgia|Savannah|메타플랜트\s*아메리카|Metaplant\s*America', re.I)
GLOBAL = re.compile(r'글로벌|해외|전\s*세계|global|worldwide|additional\s+plants?|manufacturing\s+sites?', re.I)
PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가|stock\s*price|shares?\s*(?:jump|rise|surge)', re.I)
IPO = re.compile(r'\bIPO\b|initial\s+public\s+offering|기업공개|상장', re.I)
IPO_DELAY = re.compile(r'unlikely|not\s+easy|difficult|delay|delayed|postpone|미뤄|연기|쉽지\s*않|가능성\s*낮', re.I)
VALUATION = re.compile(r'valuation|기업\s*가치|value\s+at|valued\s+at|조\s*원|trillion', re.I)
LOSS = re.compile(r'loss(?:es)?|손실|적자|unprofitable|profitability|수익성|흑자|break[- ]even|cash\s*burn|현금\s*소진', re.I)
OWNERSHIP = re.compile(r'SoftBank|소프트뱅크|ownership|지분|stake|full\s+ownership|완전\s*자회사|buyout|인수', re.I)
FUNDING = re.compile(r'funding|fundraise|capital\s+raise|자금\s*조달|증자|투자\s*유치', re.I)
EXTERNAL_CUSTOMER = re.compile(
    r'external\s+customers?|outside\s+customers?|외부\s*고객|고객\s*실명|customer|customers|'
    r'order|orders|주문|수주|sales|판매|commercial\s+sale|상용\s*판매',
    re.I,
)
CAPITAL = re.compile(
    r'\bIPO\b|initial\s+public\s+offering|기업공개|상장|valuation|기업\s*가치|'
    r'loss(?:es)?|손실|적자|unprofitable|profitability|수익성|흑자|funding|fundraise|'
    r'capital\s+raise|자금\s*조달|SoftBank|소프트뱅크|ownership|지분|stake|완전\s*자회사',
    re.I,
)
ATLAS_CATEGORY_PREFIX = '현대차그룹 · 아틀라스 '


def _is_atlas_rollout(text: str) -> bool:
    return bool(HMG.search(text) and ATLAS.search(text) and PLANT.search(text) and ROLLOUT.search(text))


def _is_boston_capital_or_commercial(text: str) -> bool:
    return bool(BOSTON.search(text) and (CAPITAL.search(text) or EXTERNAL_CUSTOMER.search(text)))


def topic_group(text: str) -> str | None:
    if _is_boston_capital_or_commercial(text) or _is_atlas_rollout(text):
        return 'hyundai_atlas_rollout'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'hyundai_atlas_rollout':
        return _orig_score(item)

    operational = (
        DISCUSSION.search(text) or PILOT.search(text) or SCHEDULE.search(text) or PROCESS.search(text)
        or UNITS_CAPEX.search(text) or CAPITAL.search(text) or EXTERNAL_CUSTOMER.search(text)
    )
    if PRICE_ONLY.search(title) and not operational:
        return -20

    src = item.get('source') or ''
    s = 18
    if base.NUMERIC.search(text):
        s += 3
    if src in base.OFFICIAL_OR_PRIMARY:
        s += 7
    elif src in base.TRUSTED:
        s += 3
    if EUROPE.search(text) or HMGMA.search(text):
        s += 5
    if DISCUSSION.search(text):
        s += 4
    if PILOT.search(text):
        s += 7
    if SCHEDULE.search(text):
        s += 6
    if PROCESS.search(text):
        s += 6
    if UNITS_CAPEX.search(text):
        s += 7
    if GLOBAL.search(text):
        s += 4
    if BOSTON.search(text) and IPO.search(text):
        s += 9
    if IPO_DELAY.search(text):
        s += 5
    if VALUATION.search(text):
        s += 5
    if LOSS.search(text):
        s += 5
    if OWNERSHIP.search(text) or FUNDING.search(text):
        s += 4
    if EXTERNAL_CUSTOMER.search(text):
        s += 6
    return s


def _subcat(text: str) -> str:
    if BOSTON.search(text) and IPO.search(text):
        return '기업공개·기업가치 시간표'
    if BOSTON.search(text) and OWNERSHIP.search(text):
        return '지분·완전자회사화'
    if BOSTON.search(text) and LOSS.search(text):
        return '손익·현금소진'
    if BOSTON.search(text) and (VALUATION.search(text) or FUNDING.search(text)):
        return '기업가치·자금조달'
    if BOSTON.search(text) and EXTERNAL_CUSTOMER.search(text):
        return '외부 고객·상용화 전환'
    if EUROPE.search(text) and DISCUSSION.search(text) and not PILOT.search(text):
        return '유럽 생산기지 도입 논의'
    if PILOT.search(text):
        return '현지 시험·검증'
    if HMGMA.search(text) and SCHEDULE.search(text):
        return '미국 생산라인 배치 계획'
    if PROCESS.search(text) and SCHEDULE.search(text):
        return '생산공정 확대'
    if UNITS_CAPEX.search(text):
        return '로봇 양산능력·투입물량'
    if GLOBAL.search(text):
        return '글로벌 생산기지 확장'
    return '생산기지 도입 단계 진전'


def category(text: str, group: str) -> str:
    if group == 'hyundai_atlas_rollout':
        return f"{ATLAS_CATEGORY_PREFIX}{_subcat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    if not cat.startswith(ATLAS_CATEGORY_PREFIX):
        return _orig_meaning(cat)
    raw = cat[len(ATLAS_CATEGORY_PREFIX):]
    if raw == '기업공개·기업가치 시간표':
        return '보스턴다이내믹스의 가치 현실화 시점이 실제 현장 배치·외부 고객·수익성 검증과 연결되는 신호입니다. 기업공개 일정만 보지 않고 2027년 외부 고객, 2028년 HMGMA 배치, 연 3만대 생산능력의 실제 출하 전환을 함께 추적합니다.'
    if raw == '지분·완전자회사화':
        return '소프트뱅크 잔여 지분 인수와 완전자회사화 여부는 현대차그룹의 추가 자금부담과 향후 기업공개 지분구조를 바꾸는 신호입니다. 계약 체결, 거래 종결, 지분율을 구분해 확인합니다.'
    if raw == '손익·현금소진':
        return '매출 성장보다 손실 축소와 현금소진 속도가 기업공개 가능 시점과 추가 자금부담을 좌우하는 단계입니다. 연구개발비, 생산준비비, 실제 로봇 판매 증가가 손익 개선으로 이어지는지 봅니다.'
    if raw == '기업가치·자금조달':
        return '기업가치 재평가나 외부 자금조달이 실제 고객·배치대수·수익성 개선에 근거하는지 확인합니다. 단순 시장 추정 기업가치와 회사 공식 거래가치를 분리합니다.'
    if raw == '외부 고객·상용화 전환':
        return '현대차그룹 내부 실증에서 외부 고객 판매로 넘어가는 가장 중요한 상용화 신호입니다. 고객 실명, 주문 대수, 단가, 반복 주문과 실제 매출 인식 시점을 확인합니다.'
    if raw == '유럽 생산기지 도입 논의':
        return '미국 HMGMA 이후 아틀라스의 글로벌 공장 확장 경로가 특정 유럽 생산법인까지 좁혀진 신호입니다. 다만 현지 논의만으로는 주문·대수·설비투자·매출이 확정되지 않으며, 시험 시작일과 투입 공정이 다음 재평가 지점입니다.'
    if raw == '현지 시험·검증':
        return '아틀라스가 그룹 차원의 확장 의향에서 실제 현지 생산환경 검증으로 이동하는 단계입니다. 공정명, 시험 대수, 작업 주기, 안전성·가동률과 정식 생산라인 전환 시점을 확인해야 합니다.'
    if raw == '미국 생산라인 배치 계획':
        return 'HMGMA 2028년 부품 시퀀싱 배치는 아틀라스 상용화의 기준 일정입니다. 이 일정이 지켜져야 유럽·기타 글로벌 공장 확대와 현대모비스 액추에이터 등 그룹 공급망의 물량 가시성이 높아집니다.'
    if raw == '생산공정 확대':
        return '시퀀싱에서 조립 등 더 복잡한 공정으로 범위가 넓어지는 신호입니다. 같은 로봇 대수라도 작업시간·가동률·공정당 배치대수가 늘면 로봇 및 후속 유지보수 수요가 커질 수 있습니다.'
    if raw == '로봇 양산능력·투입물량':
        return '연간 생산능력과 실제 투입 대수의 연결이 보이기 시작하는 단계입니다. 생산능력은 출하량이 아니므로 공장별 배치대수, 평균판매단가, 가동률과 외부 고객 주문을 분리해 추적합니다.'
    if raw == '글로벌 생산기지 확장':
        return '아틀라스가 단일 미국 공장 프로젝트가 아니라 현대차그룹의 글로벌 제조망을 내부 초기 고객으로 활용하는 상용화 구조로 확장되는 신호입니다. 구체 공장명과 일정이 붙을수록 반복 가능한 내부 수요의 가시성이 높아집니다.'
    return '아틀라스의 생산현장 상용화가 다음 단계로 이동하는 신호입니다. 논의, 시험, 정식 배치, 물량과 매출을 분리해 확인합니다.'


def risk(cat: str) -> str:
    if not cat.startswith(ATLAS_CATEGORY_PREFIX):
        return _orig_risk(cat)
    raw = cat[len(ATLAS_CATEGORY_PREFIX):]
    if raw == '기업공개·기업가치 시간표':
        return '가장 현실적인 실패 경로는 대규모 현장 배치와 외부 고객 확대가 늦어져 적자가 지속되고 기업공개가 추가 연기되는 경우입니다. 6~12개월에는 외부 고객·배치대수, 24개월에는 HMGMA 가동률·손실 축소를 먼저 확인합니다.'
    if raw == '지분·완전자회사화':
        return '잔여 지분 인수 추진과 거래 종결은 다릅니다. 인수대금, 최종 지분율, 회계상 연결 영향과 향후 기업공개 시 신주·구주매출 구조를 확인해야 합니다.'
    if raw == '손익·현금소진':
        return '적자 축소가 늦으면 현대차그룹의 추가 출자와 연구개발비 부담이 길어질 수 있습니다. 매출 증가보다 영업현금흐름·순손실·로봇당 원가 개선 여부가 먼저 드러나는 경보입니다.'
    if raw == '기업가치·자금조달':
        return '시장 추정 기업가치가 실제 거래가치보다 앞서갈 수 있습니다. 외부 고객과 손익 개선 없이 높은 가치평가만 확대되면 향후 기업공개 가격 조정 위험이 커집니다.'
    if raw == '외부 고객·상용화 전환':
        return '시범 배치와 반복 가능한 상업 판매는 다릅니다. 고객 실명·주문 대수·작업 성공률·가동률·유지보수 비용이 확인되지 않으면 외부 고객 확대가 지연될 수 있습니다.'
    if raw == '유럽 생산기지 도입 논의':
        return '가장 현실적인 실패 경로는 현지 도입 논의가 시험 일정·예산·대수 확정으로 이어지지 않는 경우입니다. 유럽의 기계류 규정과 인간-로봇 협업 안전 검증으로 미국 검증 뒤 도입 시차가 길어질 수 있습니다.'
    if raw == '현지 시험·검증':
        return '시험 성공과 양산라인 상시 운영은 다릅니다. 충돌·끼임 안전, 작업속도, 배터리 교환, 고장률, 공정 사이클타임이 목표를 못 맞추면 정식 배치가 지연될 수 있습니다.'
    if raw == '미국 생산라인 배치 계획':
        return '2028년은 계획 일정이며 실제 양산 개시가 아닙니다. HMGMA에서 부품 시퀀싱의 안전성·가동률·품질 개선이 확인되지 않으면 이후 글로벌 공장 배치도 순차 지연될 수 있습니다.'
    if raw == '생산공정 확대':
        return '조립 공정은 단순 시퀀싱보다 위치정밀도, 힘 제어, 공구 교환, 사람과의 협업 안전 요구가 높습니다. 검사·재작업 증가나 공정 사이클타임 미달이 먼저 드러날 수 있습니다.'
    if raw == '로봇 양산능력·투입물량':
        return '생산능력이 실제 수요보다 먼저 늘면 감가상각과 고정비 부담이 커질 수 있습니다. 공장별 실제 배치대수와 외부 주문 없이 생산능력만으로 매출을 환산하지 않습니다.'
    return '그룹 차원의 글로벌 확대 방향과 개별 공장의 확정 배치는 다릅니다. 공장명, 공정, 시험일, 배치대수, 설비투자와 상용 운영 시작일을 확인해야 합니다.'


def verification(item: dict, group: str, text: str) -> str:
    if group != 'hyundai_atlas_rollout':
        return _orig_verification(item, group, text)
    src = item.get('source') or ''
    if src in {'Hyundai Motor Manufacturing Czech', 'HMMC', 'AutoSAP', 'Sdružení automobilového průmyslu'}:
        return '체코 생산법인 책임자 원인터뷰·산업협회 1차자료 · 현대차그룹 공식 일정 교차확인'
    if src in {'현대자동차', 'Hyundai Motor', '현대자동차그룹', 'Hyundai Motor Group'}:
        return '현대차그룹 공식자료 · 공장별 실행 단계와 기업공개 일정 별도 확인'
    if src == 'Boston Dynamics':
        return '보스턴다이내믹스 공식자료 · 현대차그룹 배치·소유구조 일정 교차확인'
    if src == 'Reuters' and BOSTON.search(text) and CAPITAL.search(text):
        return '로이터 고위 관계자 발언 보도 · 현대차그룹/보스턴다이내믹스 공식 배치·생산 계획 교차확인 · 기업공개 일정은 회사 공식 확정 전'
    if src in base.TRUSTED:
        if DISCUSSION.search(text):
            return '신뢰 매체 보도 · 현지 원인터뷰와 현대차그룹 공식 2028 배치계획 교차확인, 현지 일정·대수는 미확정'
        return '신뢰 매체 보도 · 현대차그룹/보스턴다이내믹스 공식자료 교차확인'
    return '보도 단계 · 현대차그룹·현지 생산법인·보스턴다이내믹스 원문 재확인 필요'


def clean_title(title: str, source: str) -> str:
    t = _orig_clean_title(title, source)
    if BOSTON.search(t):
        if IPO.search(t) and re.search(r'2027', t) and IPO_DELAY.search(t):
            return '보스턴다이내믹스, 2027년 기업공개 가능성 낮아'
        if IPO.search(t):
            return '보스턴다이내믹스 기업공개 일정·조건 변화'
        if OWNERSHIP.search(t):
            return '보스턴다이내믹스 지분·완전자회사화 변화'
        if LOSS.search(t):
            return '보스턴다이내믹스 손익·수익성 변화'
        if VALUATION.search(t) or FUNDING.search(t):
            return '보스턴다이내믹스 기업가치·자금조달 변화'
        if EXTERNAL_CUSTOMER.search(t):
            return '보스턴다이내믹스 아틀라스 외부 고객·상용화 변화'
    return t


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'hyundai_atlas_rollout' or b.get('group') != 'hyundai_atlas_rollout':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"

    # Collapse rewrites of the same 2027 IPO-delay event, but do not hide a later filing/listing milestone.
    if BOSTON.search(ta) and BOSTON.search(tb) and IPO.search(ta) and IPO.search(tb):
        if re.search(r'2027', ta) and re.search(r'2027', tb) and IPO_DELAY.search(ta) and IPO_DELAY.search(tb):
            return True
    if BOSTON.search(ta) and BOSTON.search(tb) and OWNERSHIP.search(ta) and OWNERSHIP.search(tb):
        if re.search(r'SoftBank|소프트뱅크', ta, re.I) and re.search(r'SoftBank|소프트뱅크', tb, re.I):
            return True
    if EUROPE.search(ta) and EUROPE.search(tb) and DISCUSSION.search(ta) and DISCUSSION.search(tb):
        return True
    if HMGMA.search(ta) and HMGMA.search(tb) and re.search(r'2028', ta) and re.search(r'2028', tb):
        return True
    if re.search(r'3만\s*대|30,?000', ta) and re.search(r'3만\s*대|30,?000', tb):
        return True
    return False


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.clean_title = clean_title
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()

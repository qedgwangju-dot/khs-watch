#!/usr/bin/env python3
"""Hyundai Atlas rollout + Boston Dynamics commercialization/capital-market lane.

Articles, filings and interviews are discovery sources. The alert unit is the
underlying business-state change, not a publisher headline.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_humanoid_component_policy as policy

base = policy.base
ext = policy.ext
BOSTON_CAPITAL_EN_SENTINEL = 'DIRECT_BOSTON_DYNAMICS_CAPITAL_EN_NEWS'
BOSTON_RMAC_SENTINEL = 'DIRECT_BOSTON_DYNAMICS_RMAC_20260921'

base.QUERIES.extend([
    '(현대자동차 OR 현대차 OR "Hyundai Motor" OR "Hyundai Motor Group") (아틀라스 OR Atlas OR "Boston Dynamics" OR 보스턴다이내믹스) (체코 OR Czech OR 노쇼비체 OR Nosovice OR Nošovice OR 유럽 OR Europe) (도입 OR 투입 OR 배치 OR 시험 OR 테스트 OR 논의 OR 협의 OR deploy OR deployment OR testing OR trial OR discuss OR rollout)',
    '("Hyundai Motor Manufacturing Czech" OR HMMC OR 노쇼비체 OR Nosovice OR Nošovice) (아틀라스 OR Atlas) ("Boston Dynamics" OR 보스턴다이내믹스 OR 본사 OR headquarters) (논의 OR 협의 OR 테스트 OR 시험 OR 운영 OR deployment OR discuss OR test OR operation)',
    '("Hyundai Motor Group" OR 현대자동차그룹) (아틀라스 OR Atlas) (글로벌 공장 OR 글로벌 생산기지 OR 해외 공장 OR global plants OR manufacturing sites) (확대 OR 확장 OR 배치 OR 적용 OR deployment OR rollout OR scale)',
    '(HMGMA OR 조지아 OR Georgia OR Savannah) (아틀라스 OR Atlas) (2028 OR 2030 OR 시퀀싱 OR sequencing OR 조립 OR assembly OR 배치 OR deployment)',
    '("Hyundai Motor Group" OR 현대자동차그룹 OR "Hyundai Motor") (아틀라스 OR Atlas) (3만대 OR 30,000 OR 30000 OR RMAC OR "Robot Metaplant Application Center") (생산 OR 양산 OR capacity OR 확대 OR expansion OR validation)',
    '("Boston Dynamics" OR 보스턴다이내믹스) (IPO OR "initial public offering" OR 기업공개 OR 상장 OR "S-1" OR SEC OR prospectus OR underwriter OR 주관사 OR 상장예비심사 OR valuation OR 기업가치 OR 적자 OR 손실 OR loss OR losses OR profitability OR 수익성 OR 흑자 OR funding OR 자금조달 OR SoftBank OR 소프트뱅크 OR 지분 OR ownership)',
    '("Boston Dynamics" OR 보스턴다이내믹스) (프리IPO OR "pre-IPO" OR "pre IPO" OR "상장 전 투자유치") (JP모건 OR JPMorgan OR "Goldman Sachs" OR 골드만삭스 OR 10억달러 OR "$1 billion" OR "1 billion")',
    '("Boston Dynamics" OR 보스턴다이내믹스) (프리IPO OR "pre-IPO") (주관사 OR underwriter OR advisor OR 자금조달 OR fundraise OR 투자유치)',
    '("Boston Dynamics" OR 보스턴다이내믹스) (Atlas OR 아틀라스) (external customer OR external customers OR 외부 고객 OR customer OR 고객 OR order OR 주문 OR sales OR 판매 OR commercial OR 상용화 OR deployment OR 배치) (2027 OR 2028 OR 2029 OR 2030 OR scale OR 양산)',
    BOSTON_CAPITAL_EN_SENTINEL,
    '("Boston Dynamics" OR 보스턴다이내믹스) (RMAC OR "Robot Metaplant Application Center") (Atlas OR 아틀라스) (training OR 훈련 OR sequencing OR 시퀀싱 OR data OR 데이터 OR manufacturing OR 제조)',
    '("Boston Dynamics" OR 보스턴다이내믹스 OR "Hyundai Motor Group" OR 현대차그룹) (RMAC OR "Robot Metaplant Application Center") (10배 OR tenfold OR 2027 OR 이전 OR 확장 OR expansion OR new building OR 신축)',
    BOSTON_RMAC_SENTINEL,
])

base.TRUSTED.update({'뉴시스','Newsis','연합뉴스','전자신문','서울경제','한국경제','매일경제','머니투데이','조선비즈','Reuters','AutoSAP'})
base.OFFICIAL_OR_PRIMARY.update({
    '현대자동차','Hyundai Motor','현대자동차그룹','Hyundai Motor Group',
    'Boston Dynamics','Hyundai Motor Manufacturing Czech','HMMC','AutoSAP',
    'Sdružení automobilového průmyslu','U.S. Securities and Exchange Commission','SEC',
})

_orig_key = base.key
_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_clean_title = base.clean_title
_orig_query_news = base.query_news
_orig_same_event = ext._same_event

HMG = re.compile(r'현대자동차그룹|현대차그룹|현대자동차|현대차|Hyundai\s*Motor\s*Group|Hyundai\s*Motor|Hyundai\s*Motor\s*Manufacturing\s*Czech|\bHMMC\b|\bHMGMA\b', re.I)
BOSTON = re.compile(r'Boston\s*Dynamics|보스턴\s*다이내믹스|보스턴다이내믹스', re.I)
ATLAS = re.compile(r'아틀라스|\bAtlas\b|Boston\s*Dynamics|보스턴\s*다이내믹스|보스턴다이내믹스', re.I)
PLANT = re.compile(r'공장|생산\s*기지|생산\s*라인|plant|factory|manufacturing\s*(?:site|plant|line)|노쇼비체|Nosovice|Nošovice|체코|Czech|유럽|Europe|HMGMA|조지아|Georgia|Savannah', re.I)
ROLLOUT = re.compile(r'도입|투입|배치|적용|확대|확장|시험|테스트|검증|운영|논의|협의|검토|deploy|deployment|rollout|trial|test|testing|validation|operation|adoption|discuss|talks?|consider|scale', re.I)
DISCUSSION = re.compile(r'논의|협의|검토|도입\s*논의|가능한\s*한\s*빨리|희망|원한다|discuss|talks?|consider|would\s+like|as\s+soon\s+as\s+possible', re.I)
PILOT = re.compile(r'시험|테스트|실증|검증|pilot|trial|test|testing|validation', re.I)
SCHEDULE = re.compile(r'2027|2028|2029|2030|시작|개시|도입\s*시기|투입\s*시점|배치\s*시점|begin|starting|from\s+2028|by\s+2028|by\s+2030|scheduled|timeline', re.I)
PROCESS = re.compile(r'부품\s*시퀀싱|시퀀싱|sequencing|부품\s*배열|component\s*assembly|조립|assembly|반복\s*작업|중량물|heavy\s*loads?|repetitive', re.I)
UNITS_CAPEX = re.compile(r'3만\s*대|30,?000|대\s*투입|대\s*배치|units?|설비\s*투자|투자액|capex|capacity|생산\s*능력', re.I)
EUROPE = re.compile(r'체코|Czech|노쇼비체|Nosovice|Nošovice|유럽|Europe|\bHMMC\b', re.I)
HMGMA = re.compile(r'HMGMA|조지아|Georgia|Savannah|메타플랜트\s*아메리카|Metaplant\s*America', re.I)
RMAC = re.compile(r'RMAC|Robot\s*Metaplant\s*Application\s*Center|로봇\s*메타플랜트\s*애플리케이션\s*센터', re.I)
RMAC_ALIAS = re.compile(r'로봇\s*학교|robot\s*school|제조\s*훈련|manufacturing\s*training|공장\s*투입\s*준비|현장\s*훈련|factory\s*training', re.I)
RMAC_ACTIVE = re.compile(r'open(?:ed|s)?|개소|운영\s*개시|training|train|훈련|data\s*collection|데이터\s*수집|sequencing|시퀀싱|validation|검증', re.I)
RMAC_EXPAND = re.compile(r'10\s*배|ten[- ]?fold|2027|신축|new\s*building|move|relocat|이전|확장|expansion', re.I)
RMAC_EXPANSION_COMPLETE = re.compile(r'(?:10\s*배|ten[- ]?fold).{0,30}(?:확장\s*(?:완료|개소)|가동|이전\s*완료|opened|operational|completed)|(?:new\s*building|신축\s*건물).{0,30}(?:opened|operational|가동|개소|이전\s*완료)', re.I)
RMAC_EXTERNAL_PILOT = re.compile(r'(?:aerospace|항공우주|semiconductor|반도체|logistics|물류|food|beverage|식음료|life\s*science|생명과학).{0,80}(?:pilot|trial|training|deployment|data\s*collection\s*(?:started|began)|실증|훈련\s*시작|배치\s*시작|데이터\s*수집\s*(?:시작|개시))', re.I)
RMAC_OTHER_INDUSTRIES = re.compile(r'aerospace|항공우주|semiconductor|반도체|logistics|물류|food|beverage|식음료|life\s*science|생명과학|Spot|Stretch', re.I)
GLOBAL = re.compile(r'글로벌|해외|전\s*세계|global|worldwide|additional\s+plants?|manufacturing\s+sites?', re.I)
PRICE_ONLY = re.compile(r'주가|급등|상한가|특징주|수혜주|목표주가|stock\s*price|shares?\s*(?:jump|rise|surge)', re.I)
IPO = re.compile(r'\bIPO\b|initial\s+public\s+offering|기업공개|상장|\bS-1\b|registration\s+statement|prospectus|underwriter|주관사|상장예비심사|listing\s+application', re.I)
PREIPO = re.compile(r'pre[-\s]?IPO|프리\s*IPO|상장\s*전\s*투자\s*유치', re.I)
PREIPO_UNDERWRITER = re.compile(r'(?:JP\s*Morgan|JPMorgan|JP모건|Goldman\s*Sachs|골드만삭스).{0,80}(?:underwriter|advisor|주관사|선정)|(?:underwriter|advisor|주관사|선정).{0,80}(?:JP\s*Morgan|JPMorgan|JP모건|Goldman\s*Sachs|골드만삭스)', re.I)
PREIPO_AMOUNT = re.compile(r'\$?\s*1\s*(?:billion|bn)|10\s*억\s*달러|1조\s*4,?000억|1\.4\s*조', re.I)
IPO_FILING = re.compile(r'\bS-1\b|registration\s+statement|prospectus|underwriter|주관사|상장예비심사|listing\s+application|filed|filing|제출|신고서', re.I)
IPO_DELAY = re.compile(r'unlikely|not\s+easy|difficult|delay|delayed|postpone|미뤄|연기|쉽지\s*않|가능성\s*낮|no\s+(?:specific\s+)?(?:timeline|timetable)', re.I)
IPO_COMMENTARY = re.compile(r'2027|2028|2029|2030|unlikely|not\s+easy|difficult|timeline|timetable|valuation|unprofitable|loss|가능성|일정|기업가치|손실|적자|30,?000|3만', re.I)
VALUATION = re.compile(r'valuation|기업\s*가치|value\s+at|valued\s+at|조\s*원|trillion', re.I)
LOSS = re.compile(r'loss(?:es)?|손실|적자|unprofitable|profitability|수익성|흑자|break[- ]even|cash\s*burn|현금\s*소진', re.I)
OWNERSHIP = re.compile(r'SoftBank|소프트뱅크|ownership|지분|stake|full\s+ownership|완전\s*자회사|buyout|인수', re.I)
FUNDING = re.compile(r'funding|fundraise|capital\s+raise|자금\s*조달|증자|투자\s*유치', re.I)
EXTERNAL_CUSTOMER = re.compile(r'external\s+customers?|outside\s+customers?|외부\s*고객|고객\s*실명|customer|customers|order|orders|주문|수주|sales|판매|commercial\s+sale|상용\s*판매', re.I)
CAPITAL = re.compile(r'\bIPO\b|pre[-\s]?IPO|프리\s*IPO|상장\s*전\s*투자\s*유치|initial\s+public\s+offering|기업공개|상장|\bS-1\b|registration\s+statement|prospectus|underwriter|주관사|상장예비심사|valuation|기업\s*가치|loss(?:es)?|손실|적자|unprofitable|profitability|수익성|흑자|funding|fundraise|capital\s+raise|자금\s*조달|SoftBank|소프트뱅크|ownership|지분|stake|완전\s*자회사', re.I)
ATLAS_CATEGORY_PREFIX = '현대차그룹 · 아틀라스 '


def _query_boston_rmac_recovery() -> list[dict]:
    event_time = dt.datetime(2026, 9, 21, 0, 0, tzinfo=dt.timezone.utc)
    if base.NOW - event_time > dt.timedelta(hours=120):
        return []
    return [{
        'title': '보스턴다이내믹스, RMAC서 Atlas 제조 현장 훈련 본격화',
        'link': 'https://bostondynamics.com/news/boston-dynamics-opens-robotics-metaplant-application-center-to-train-humanoid-robots-for-manufacturing-tasks/',
        'description': (
            'Boston Dynamics RMAC at HMGMA is training Atlas on automotive parts logistics and sequencing. '
            'The task roadmap expands toward component assembly by 2030. Hyundai Motor Group plans more than 25,000 Atlas deployments, '
            'with a U.S. robotics production facility targeting 30,000 units of annual capacity from 2028. '
            'RMAC expansion and broader data collection discussions also cover existing Spot and Stretch customers in aerospace, semiconductor, logistics, food and beverage, and life sciences.'
        ),
        'published': None,
        'source': 'Boston Dynamics',
        'rmac_operational': True,
    }]


def _is_rmac_operational(text: str) -> bool:
    center = RMAC.search(text) or RMAC_ALIAS.search(text)
    active = RMAC_ACTIVE.search(text) or RMAC_ALIAS.search(text)
    return bool((BOSTON.search(text) or HMG.search(text)) and ATLAS.search(text) and center and active)

def _rmac_stage(text: str) -> str:
    if RMAC_EXPANSION_COMPLETE.search(text):
        return 'expansion_completed'
    if RMAC_EXTERNAL_PILOT.search(text):
        return 'external_industry_pilot'
    if _is_rmac_operational(text):
        return 'training_operational'
    return ''


def _query_boston_capital_english_news() -> list[dict]:
    q = '"Boston Dynamics" (IPO OR "initial public offering" OR "S-1" OR SEC OR prospectus OR underwriter OR valuation OR loss OR profitability OR SoftBank OR funding OR "external customer" OR Atlas)'
    params = urllib.parse.urlencode({'q': q, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    root = ET.fromstring(base.fetch(f'https://news.google.com/rss/search?{params}'))
    out: list[dict] = []
    for it in root.findall('./channel/item')[:50]:
        title = base.norm(it.findtext('title')); link = base.norm(it.findtext('link')); desc = base.norm(it.findtext('description'))
        pub = base.parse_date(it.findtext('pubDate')); src_node = it.find('source'); src = base.norm(src_node.text if src_node is not None else '')
        if title and link:
            out.append({'title':title,'link':link,'description':desc,'published':pub.isoformat() if pub else None,'source':src})
    return out


def query_news(q: str) -> list[dict]:
    if q == BOSTON_RMAC_SENTINEL:
        return _query_boston_rmac_recovery()
    if q == BOSTON_CAPITAL_EN_SENTINEL:
        return _query_boston_capital_english_news()
    return _orig_query_news(q)


def _is_atlas_rollout(text: str) -> bool:
    return bool(HMG.search(text) and ATLAS.search(text) and PLANT.search(text) and ROLLOUT.search(text))


def _is_boston_capital_or_commercial(text: str) -> bool:
    return bool(BOSTON.search(text) and (CAPITAL.search(text) or EXTERNAL_CUSTOMER.search(text)))


def topic_group(text: str) -> str | None:
    if _is_rmac_operational(text): return 'hyundai_atlas_rollout'
    if _is_boston_capital_or_commercial(text) or _is_atlas_rollout(text): return 'hyundai_atlas_rollout'
    return _orig_topic_group(text)


def _ipo_stage(text: str) -> str:
    if not BOSTON.search(text): return ''
    if PREIPO.search(text):
        if PREIPO_UNDERWRITER.search(text) and PREIPO_AMOUNT.search(text): return 'preipo_underwriter_fundraise'
        if PREIPO_UNDERWRITER.search(text): return 'preipo_underwriter'
        if FUNDING.search(text) or PREIPO_AMOUNT.search(text): return 'preipo_fundraise'
        return 'preipo'
    if not IPO.search(text): return ''
    if IPO_FILING.search(text):
        if re.search(r'underwriter|주관사', text, re.I): return 'underwriter'
        if re.search(r'\bS-1\b|registration\s+statement|filed|filing|신고서|제출', text, re.I): return 'filing'
        return 'formal_process'
    if IPO_DELAY.search(text): return 'delay'
    return 'commentary'


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')}"
    rmac_stage = _rmac_stage(text)
    if rmac_stage == 'expansion_completed':
        return hashlib.sha256(b'boston-dynamics|rmac|expansion-completed|10x').hexdigest()
    if rmac_stage == 'external_industry_pilot':
        return hashlib.sha256(b'boston-dynamics|rmac|external-industry-pilot').hexdigest()
    if rmac_stage == 'training_operational':
        return hashlib.sha256(b'boston-dynamics|rmac|operational-training|2026-09-21').hexdigest()
    stage = _ipo_stage(text)
    if stage in {'preipo_underwriter_fundraise','preipo_underwriter','preipo_fundraise','preipo'}:
        return hashlib.sha256(b'boston-dynamics|2026-09-22|preipo|jpmorgan-goldman|1b-plus').hexdigest()
    if stage in {'delay','commentary'} and IPO_COMMENTARY.search(text):
        years = sorted(set(re.findall(r'20(?:27|28|29|30)', text)))
        # Semantic event key: publisher rewrites of the same timing narrative collapse,
        # while a changed target year or formal filing/underwriter milestone stays new.
        anchor = years[0] if years else 'timing'
        direction = 'delay' if stage == 'delay' else 'commentary'
        return hashlib.sha256(f'boston-dynamics|ipo|{anchor}|{direction}'.encode()).hexdigest()
    return _orig_key(item)


def score(item: dict) -> int:
    title = item.get('title',''); text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'hyundai_atlas_rollout': return _orig_score(item)
    operational = DISCUSSION.search(text) or PILOT.search(text) or SCHEDULE.search(text) or PROCESS.search(text) or UNITS_CAPEX.search(text) or CAPITAL.search(text) or EXTERNAL_CUSTOMER.search(text)
    if PRICE_ONLY.search(title) and not operational: return -20
    src = item.get('source') or ''; s = 18
    if base.NUMERIC.search(text): s += 3
    if src in base.OFFICIAL_OR_PRIMARY: s += 7
    elif src in base.TRUSTED: s += 3
    if EUROPE.search(text) or HMGMA.search(text): s += 5
    if DISCUSSION.search(text): s += 4
    if PILOT.search(text): s += 7
    if SCHEDULE.search(text): s += 6
    if PROCESS.search(text): s += 6
    if UNITS_CAPEX.search(text): s += 7
    if GLOBAL.search(text): s += 4
    if _is_rmac_operational(text): s += 14
    if RMAC_EXPAND.search(text): s += 5
    if RMAC_OTHER_INDUSTRIES.search(text): s += 4
    if BOSTON.search(text) and (IPO.search(text) or PREIPO.search(text)): s += 9
    if _ipo_stage(text) in {'preipo_underwriter_fundraise','preipo_underwriter'}: s += 12
    if _ipo_stage(text) in {'preipo_underwriter_fundraise','preipo_fundraise'} and PREIPO_AMOUNT.search(text): s += 7
    if IPO_FILING.search(text): s += 8
    if IPO_DELAY.search(text): s += 5
    if VALUATION.search(text): s += 5
    if LOSS.search(text): s += 5
    if OWNERSHIP.search(text) or FUNDING.search(text): s += 4
    if EXTERNAL_CUSTOMER.search(text): s += 6
    return s


def _subcat(text: str) -> str:
    if _rmac_stage(text) == 'expansion_completed': return 'RMAC 10배 확장 완료·가동'
    if _rmac_stage(text) == 'external_industry_pilot': return 'RMAC 타 산업 고객 실증·데이터 확장'
    if _rmac_stage(text) == 'training_operational': return 'RMAC 제조현장 훈련·데이터 플라이휠'
    if _ipo_stage(text) == 'preipo_underwriter_fundraise': return '프리IPO 주관사·10억달러+ 자금조달'
    if _ipo_stage(text) == 'preipo_underwriter': return '프리IPO 주관사 선정'
    if _ipo_stage(text) in {'preipo_fundraise','preipo'}: return '프리IPO 자금조달'
    if BOSTON.search(text) and IPO_FILING.search(text): return '기업공개 절차 진전'
    if BOSTON.search(text) and IPO.search(text): return '기업공개·기업가치 시간표'
    if BOSTON.search(text) and OWNERSHIP.search(text): return '지분·완전자회사화'
    if BOSTON.search(text) and LOSS.search(text): return '손익·현금소진'
    if BOSTON.search(text) and (VALUATION.search(text) or FUNDING.search(text)): return '기업가치·자금조달'
    if BOSTON.search(text) and EXTERNAL_CUSTOMER.search(text): return '외부 고객·상용화 전환'
    if EUROPE.search(text) and DISCUSSION.search(text) and not PILOT.search(text): return '유럽 생산기지 도입 논의'
    if PILOT.search(text): return '현지 시험·검증'
    if HMGMA.search(text) and SCHEDULE.search(text): return '미국 생산라인 배치 계획'
    if PROCESS.search(text) and SCHEDULE.search(text): return '생산공정 확대'
    if UNITS_CAPEX.search(text): return '로봇 양산능력·투입물량'
    if GLOBAL.search(text): return '글로벌 생산기지 확장'
    return '생산기지 도입 단계 진전'


def category(text: str, group: str) -> str:
    return f"{ATLAS_CATEGORY_PREFIX}{_subcat(text)}" if group == 'hyundai_atlas_rollout' else _orig_category(text, group)


def meaning(cat: str) -> str:
    if not cat.startswith(ATLAS_CATEGORY_PREFIX): return _orig_meaning(cat)
    raw = cat[len(ATLAS_CATEGORY_PREFIX):]
    m = {
        'RMAC 제조현장 훈련·데이터 플라이휠':'RMAC이 실제 제조환경을 재현해 Atlas의 자동차 부품 물류·시퀀싱을 훈련하고 현장 데이터를 축적하는 단계입니다. 2028년 HMGMA 배치 전 검증센터가 실제 가동되는 것이 핵심이며, 이후 조립 공정·타 산업 고객 데이터로 확장되는지 추적합니다.',
        '기업공개 절차 진전':'시장 기대나 관계자 발언을 넘어 실제 기업공개 절차가 시작되는 신호입니다. S-1·SEC 제출, 주관사 선정, 공모 구조와 일정, 신주·구주매출을 확인합니다.',
        '기업공개·기업가치 시간표':'보스턴다이내믹스의 가치 현실화 시점이 실제 현장 배치·외부 고객·수익성 검증과 연결되는 신호입니다. 기업공개 일정만 보지 않고 2027년 외부 고객, 2028년 HMGMA 배치, 연 3만대 생산능력의 실제 출하 전환을 함께 추적합니다.',
        '지분·완전자회사화':'소프트뱅크 잔여 지분 인수와 완전자회사화 여부는 현대차그룹의 추가 자금부담과 향후 기업공개 지분구조를 바꾸는 신호입니다. 계약 체결, 거래 종결, 지분율을 구분해 확인합니다.',
        '손익·현금소진':'매출 성장보다 손실 축소와 현금소진 속도가 기업공개 가능 시점과 추가 자금부담을 좌우하는 단계입니다. 연구개발비, 생산준비비, 실제 로봇 판매 증가가 손익 개선으로 이어지는지 봅니다.',
        '기업가치·자금조달':'기업가치 재평가나 외부 자금조달이 실제 고객·배치대수·수익성 개선에 근거하는지 확인합니다. 단순 시장 추정 기업가치와 회사 공식 거래가치를 분리합니다.',
        '외부 고객·상용화 전환':'현대차그룹 내부 실증에서 외부 고객 판매로 넘어가는 가장 중요한 상용화 신호입니다. 고객 실명, 주문 대수, 단가, 반복 주문과 실제 매출 인식 시점을 확인합니다.',
        '유럽 생산기지 도입 논의':'미국 HMGMA 이후 아틀라스의 글로벌 공장 확장 경로가 특정 유럽 생산법인까지 좁혀진 신호입니다. 현지 논의만으로 주문·대수·설비투자·매출이 확정되지는 않으며 시험 시작일과 투입 공정이 다음 재평가 지점입니다.',
        '현지 시험·검증':'아틀라스가 그룹 차원의 확장 의향에서 실제 현지 생산환경 검증으로 이동하는 단계입니다. 공정명, 시험 대수, 작업 주기, 안전성·가동률과 정식 생산라인 전환 시점을 확인합니다.',
        '미국 생산라인 배치 계획':'HMGMA 2028년 부품 시퀀싱 배치는 아틀라스 상용화의 기준 일정입니다. 이 일정이 지켜져야 유럽·기타 글로벌 공장 확대와 현대모비스 액추에이터 등 그룹 공급망의 물량 가시성이 높아집니다.',
        '생산공정 확대':'시퀀싱에서 조립 등 더 복잡한 공정으로 범위가 넓어지는 신호입니다. 같은 로봇 대수라도 작업시간·가동률·공정당 배치대수가 늘면 로봇 및 후속 유지보수 수요가 커질 수 있습니다.',
        '로봇 양산능력·투입물량':'연간 생산능력과 실제 투입 대수의 연결이 보이기 시작하는 단계입니다. 생산능력은 출하량이 아니므로 공장별 배치대수, 평균판매단가, 가동률과 외부 고객 주문을 분리해 추적합니다.',
        '글로벌 생산기지 확장':'아틀라스가 단일 미국 공장 프로젝트가 아니라 현대차그룹의 글로벌 제조망을 내부 초기 고객으로 활용하는 상용화 구조로 확장되는 신호입니다. 구체 공장명과 일정이 붙을수록 반복 가능한 내부 수요의 가시성이 높아집니다.',
    }
    return m.get(raw, '아틀라스의 생산현장 상용화가 다음 단계로 이동하는 신호입니다. 논의, 시험, 정식 배치, 물량과 매출을 분리해 확인합니다.')


def risk(cat: str) -> str:
    if not cat.startswith(ATLAS_CATEGORY_PREFIX): return _orig_risk(cat)
    raw = cat[len(ATLAS_CATEGORY_PREFIX):]
    m = {
        'RMAC 10배 확장 완료·가동':'시설 면적 확대가 곧 Atlas 출하량 증가를 뜻하지는 않습니다. 훈련 슬롯·로봇 대수·작업 성공률과 HMGMA 실제 배치가 따라오지 않으면 설비 확대가 선행비용으로 남을 수 있습니다.',
        'RMAC 타 산업 고객 실증·데이터 확장':'타 산업 데이터 수집이 상용 판매로 연결되지 않을 수 있습니다. 파일럿 반복 여부, 고객별 작업 성공률·가동률·유지보수 비용과 실제 계약을 확인합니다.',
        'RMAC 제조현장 훈련·데이터 플라이휠':'훈련센터 개소와 실제 생산라인 상시 배치는 다릅니다. 먼저 봐야 할 실패 경로는 작업 성공률·사이클타임·안전 검증이 기준을 못 맞춰 2028년 현장 배치가 늦어지는 경우이며, RMAC 확대가 실제 배치대수와 출하로 연결되는지 확인합니다.',
        '기업공개 절차 진전':'신고서 제출이나 주관사 선정은 상장 완료가 아닙니다. 심사·시장상황·공모가 조정·철회 가능성을 분리해 보고 실제 상장일과 공모 구조를 확인해야 합니다.',
        '기업공개·기업가치 시간표':'가장 현실적인 실패 경로는 대규모 현장 배치와 외부 고객 확대가 늦어져 적자가 지속되고 기업공개가 추가 연기되는 경우입니다. 6~12개월에는 외부 고객·배치대수, 24개월에는 HMGMA 가동률·손실 축소를 먼저 확인합니다.',
        '지분·완전자회사화':'잔여 지분 인수 추진과 거래 종결은 다릅니다. 인수대금, 최종 지분율, 회계상 연결 영향과 향후 기업공개 시 신주·구주매출 구조를 확인해야 합니다.',
        '손익·현금소진':'적자 축소가 늦으면 현대차그룹의 추가 출자와 연구개발비 부담이 길어질 수 있습니다. 매출 증가보다 영업현금흐름·순손실·로봇당 원가 개선 여부가 먼저 드러나는 경보입니다.',
        '기업가치·자금조달':'시장 추정 기업가치가 실제 거래가치보다 앞서갈 수 있습니다. 외부 고객과 손익 개선 없이 높은 가치평가만 확대되면 향후 기업공개 가격 조정 위험이 커집니다.',
        '외부 고객·상용화 전환':'시범 배치와 반복 가능한 상업 판매는 다릅니다. 고객 실명·주문 대수·작업 성공률·가동률·유지보수 비용이 확인되지 않으면 외부 고객 확대가 지연될 수 있습니다.',
        '유럽 생산기지 도입 논의':'가장 현실적인 실패 경로는 현지 도입 논의가 시험 일정·예산·대수 확정으로 이어지지 않는 경우입니다. 유럽의 기계류 규정과 인간-로봇 협업 안전 검증으로 미국 검증 뒤 도입 시차가 길어질 수 있습니다.',
        '현지 시험·검증':'시험 성공과 양산라인 상시 운영은 다릅니다. 충돌·끼임 안전, 작업속도, 배터리 교환, 고장률, 공정 사이클타임이 목표를 못 맞추면 정식 배치가 지연될 수 있습니다.',
        '미국 생산라인 배치 계획':'2028년은 계획 일정이며 실제 양산 개시가 아닙니다. HMGMA에서 부품 시퀀싱의 안전성·가동률·품질 개선이 확인되지 않으면 이후 글로벌 공장 배치도 순차 지연될 수 있습니다.',
        '생산공정 확대':'조립 공정은 단순 시퀀싱보다 위치정밀도, 힘 제어, 공구 교환, 사람과의 협업 안전 요구가 높습니다. 검사·재작업 증가나 공정 사이클타임 미달이 먼저 드러날 수 있습니다.',
        '로봇 양산능력·투입물량':'생산능력이 실제 수요보다 먼저 늘면 감가상각과 고정비 부담이 커질 수 있습니다. 공장별 실제 배치대수와 외부 주문 없이 생산능력만으로 매출을 환산하지 않습니다.',
    }
    return m.get(raw, '그룹 차원의 글로벌 확대 방향과 개별 공장의 확정 배치는 다릅니다. 공장명, 공정, 시험일, 배치대수, 설비투자와 상용 운영 시작일을 확인해야 합니다.')


def verification(item: dict, group: str, text: str) -> str:
    if group != 'hyundai_atlas_rollout': return _orig_verification(item, group, text)
    src = item.get('source') or ''
    if src in {'Hyundai Motor Manufacturing Czech','HMMC','AutoSAP','Sdružení automobilového průmyslu'}: return '체코 생산법인 책임자 원인터뷰·산업협회 1차자료 · 현대차그룹 공식 일정 교차확인'
    if src in {'현대자동차','Hyundai Motor','현대자동차그룹','Hyundai Motor Group'}: return '현대차그룹 공식자료 · 공장별 실행 단계와 기업공개 일정 별도 확인'
    if src == 'Boston Dynamics' and _is_rmac_operational(text): return '보스턴다이내믹스 공식자료 · RMAC 실제 훈련·검증 단계, 25,000대 배치·연 30,000대 생산능력은 현대차그룹 공식 계획과 구분'
    if src == 'Boston Dynamics': return '보스턴다이내믹스 공식자료 · 현대차그룹 배치·소유구조 일정 교차확인'
    if src in {'U.S. Securities and Exchange Commission','SEC'}: return '미국 증권거래위원회 공식 상장서류'
    if src == 'Reuters' and BOSTON.search(text) and CAPITAL.search(text): return '로이터 고위 관계자 발언 보도 · 현대차그룹/보스턴다이내믹스 공식 배치·생산 계획 교차확인 · 기업공개 일정은 회사 공식 확정 전'
    if src in base.TRUSTED:
        if DISCUSSION.search(text): return '신뢰 매체 보도 · 현지 원인터뷰와 현대차그룹 공식 2028 배치계획 교차확인, 현지 일정·대수는 미확정'
        return '신뢰 매체 보도 · 현대차그룹/보스턴다이내믹스 공식자료 교차확인'
    return '보도 단계 · 현대차그룹·현지 생산법인·보스턴다이내믹스 원문 재확인 필요'


def clean_title(title: str, source: str) -> str:
    t = _orig_clean_title(title, source)
    if RMAC.search(t) or re.search(r'Metaplant Application Center|제조 현장 훈련|manufacturing tasks', t, re.I):
        return '보스턴다이내믹스, RMAC서 Atlas 제조 현장 훈련 본격화'
    if BOSTON.search(t):
        if IPO_FILING.search(t): return '보스턴다이내믹스 기업공개 절차 진전'
        if IPO.search(t) and re.search(r'2027', t) and IPO_DELAY.search(t): return '보스턴다이내믹스, 2027년 기업공개 가능성 낮아'
        if IPO.search(t): return '보스턴다이내믹스 기업공개 일정·조건 변화'
        if OWNERSHIP.search(t): return '보스턴다이내믹스 지분·완전자회사화 변화'
        if LOSS.search(t): return '보스턴다이내믹스 손익·수익성 변화'
        if VALUATION.search(t) or FUNDING.search(t): return '보스턴다이내믹스 기업가치·자금조달 변화'
        if EXTERNAL_CUSTOMER.search(t): return '보스턴다이내믹스 아틀라스 외부 고객·상용화 변화'
    return t


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a,b): return True
    if a.get('group') != 'hyundai_atlas_rollout' or b.get('group') != 'hyundai_atlas_rollout': return False
    ta = f"{a.get('title','')} {a.get('description','')}"; tb = f"{b.get('title','')} {b.get('description','')}"
    rmac_a, rmac_b = _rmac_stage(ta), _rmac_stage(tb)
    if rmac_a and rmac_b:
        return rmac_a == rmac_b
    if BOSTON.search(ta) and BOSTON.search(tb) and IPO.search(ta) and IPO.search(tb):
        fa, fb = bool(IPO_FILING.search(ta)), bool(IPO_FILING.search(tb))
        if not fa and not fb and IPO_COMMENTARY.search(ta) and IPO_COMMENTARY.search(tb): return True
        if fa and fb:
            for pat in [r'\bS-1\b|registration\s+statement|filed|filing|신고서|제출', r'underwriter|주관사', r'prospectus|상장예비심사|listing\s+application']:
                if re.search(pat,ta,re.I) and re.search(pat,tb,re.I): return True
    if BOSTON.search(ta) and BOSTON.search(tb) and OWNERSHIP.search(ta) and OWNERSHIP.search(tb) and re.search(r'SoftBank|소프트뱅크',ta,re.I) and re.search(r'SoftBank|소프트뱅크',tb,re.I): return True
    if EUROPE.search(ta) and EUROPE.search(tb) and DISCUSSION.search(ta) and DISCUSSION.search(tb): return True
    if HMGMA.search(ta) and HMGMA.search(tb) and re.search(r'2028',ta) and re.search(r'2028',tb): return True
    if re.search(r'3만\s*대|30,?000',ta) and re.search(r'3만\s*대|30,?000',tb): return True
    return False


base.query_news = query_news
base.key = key
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

#!/usr/bin/env python3
"""Separate ESS-battery market/policy lane for the physical-AI Telegram watcher.

This keeps humanoid-battery stories in the existing battery lane, while routing
stationary ESS/BESS supply, Chinese capacity policy, cell prices, tax changes,
and MLCC power-control bottlenecks into an independent 'ESS 배터리' lane.

MLCC guardrails:
- ESS/BESS must be explicitly present; generic AI-server/automotive MLCC news is
  not promoted into the ESS lane by itself.
- Media/analyst wording such as "price could double" remains a forecast until a
  supplier notice, filing, contract, or customer transaction confirms it.
- A component shortage is not booked revenue for Samsung Electro-Mechanics or
  another supplier unless the customer/contract/volume/price path is confirmed.
- Repeated articles about the same ESS-MLCC shortage/price event are deduped,
  while a later confirmed price, LTA, capacity, lead-time or customer change is
  treated as a new event.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_expanded_safe as safe

expanded = safe.expanded
base = safe.base
ext = expanded.ext

base.QUERIES.extend([
    '(중국 OR China OR 中国) (ESS OR BESS OR 에너지저장 OR 储能) (배터리셀 OR 배터리 셀 OR cell OR 电芯 OR 공장 OR factory) (승인 중단 OR 승인 보류 OR 신규 승인 OR pause approvals OR approval pause OR 产能 OR 审批)',
    '(CATL OR 宁德时代 OR EVE Energy OR 亿纬锂能 OR 이브에너지) (ESS OR BESS OR storage OR 储能) (314Ah OR 0.414 OR 0.423 OR 가격 인상 OR price hike OR 提价 OR 소비세 OR consumption tax)',
    '(중국 OR China OR 中国) (배터리 OR battery OR 电池) (소비세 OR consumption tax OR 消费税) (2% OR 4% OR 2026 OR 2027) (ESS OR BESS OR 에너지저장 OR 储能)',
    '(LG에너지솔루션 OR 삼성SDI OR SK온 OR "LG Energy Solution" OR "Samsung SDI" OR "SK On") (ESS OR BESS OR 에너지저장) (수주 OR 계약 OR 공급 OR 생산능력 OR 가격 OR LFP OR 미국 OR 북미)',
    '(삼성SDI OR "Samsung SDI") (ESS OR UPS OR BBU OR "energy storage") (매출비중 OR "매출 비중" OR 영업이익률 OR margin OR AMPC OR 관세환급 OR "관세 환급" OR "tariff refund" OR 본업 OR 실적 OR earnings) (3분기 OR 3Q OR Q3 OR 확정 OR actual OR results OR 발표 OR 전망 OR 추정 OR 컨센서스)',
    '(삼성SDI OR "Samsung SDI") (SynergyCells OR "Synergy Cells" OR 시너지셀즈 OR "New Carlisle" OR 뉴칼라일 OR 인디애나) (ESS OR LFP OR "energy storage") (준공 OR completion OR 장비 OR equipment OR 반입 OR 설치 OR 시험생산 OR trial OR SOP OR 양산 OR capacity OR 생산능력 OR GWh OR 가동률 OR utilization OR 고객 OR customer OR 수주 OR contract)',
    '(삼성SDI OR "Samsung SDI") (ESS OR LFP OR "energy storage") (미국 OR 북미 OR "StarPlus Energy" OR SynergyCells) (신규수주 OR 공급계약 OR 장기계약 OR 고객 OR GWh OR 생산능력 OR 가동률 OR 양산 OR SOP)',
    '(에코프로비엠 OR 포스코퓨처엠 OR 엘앤에프 OR EcoPro BM OR POSCO Future M) (ESS OR BESS OR 에너지저장) (LFP OR 양극재 OR 공급 OR 수주 OR 가격)',
    '(ESS OR BESS OR 에너지저장장치 OR energy storage) (MLCC OR 적층세라믹커패시터 OR multilayer ceramic capacitor) (공급난 OR 부족 OR shortage OR allocation OR 납기 OR lead time OR 생산 차질 OR bottleneck)',
    '(ESS OR BESS OR 에너지저장장치 OR energy storage) (MLCC OR 적층세라믹커패시터) (가격 인상 OR price hike OR 가격 상승 OR 두 배 OR 2배 OR average selling price OR ASP)',
    '(삼성전기 OR Samsung Electro-Mechanics OR Murata OR 무라타 OR Taiyo Yuden OR 다이요유덴 OR TDK OR Yageo) (ESS OR BESS OR energy storage) (MLCC OR capacitor) (장기공급계약 OR LTA OR 공급계약 OR contract OR 증설 OR capacity OR 가동률 OR utilization OR 납기 OR lead time)',
    '(ESS OR BESS OR energy storage) (MLCC OR 적층세라믹커패시터) (이중조달 OR dual sourcing OR 재고조정 OR inventory correction OR 공급 정상화 OR normalization OR 가격 하락 OR price cut)',
    '(ESS OR BESS OR energy storage) (MLCC OR 적층세라믹커패시터) (고전압 OR high voltage OR 고신뢰성 OR high reliability OR 고온 OR high temperature OR 검사 OR test OR 수율 OR yield)',
    '(전력거래소 OR KPX) ("ESS 중앙계약시장" OR "에너지저장장치 중앙계약시장") (입찰공고 OR 공고문 OR 확정 OR 선정 OR 우선협상 OR 낙찰)',
    '(전력거래소 OR KPX OR ESS) (25년 OR 15년 OR 장기계약 OR 계약기간) (잔존용량 OR 보증수명 OR 90% OR 70% OR 730회 OR 18250회 OR 1만8250회)',
    '("Solar Energy Industries Association" OR SEIA) ("energy storage" OR ESS OR BESS) (Q1 OR Q2 OR Q3 OR Q4 OR quarter OR quarterly OR 상반기 OR 하반기) (installed OR installations OR "new capacity" OR 신규설치 OR 신규 설치 OR GWh)',
    '("U.S. Energy Storage Coalition" OR "US Energy Storage Coalition" OR "Energy Storage Coalition" OR ESC) ("energy storage" OR ESS) (225 GW OR 1 TWh OR 2032 OR terawatt-hour) (target OR goal OR pace OR revised OR raised OR lowered OR 목표 OR 상향 OR 하향 OR 연기)',
    '(미국 OR "United States" OR "U.S.") (ESS OR "energy storage" OR BESS) (forecast OR outlook OR 전망) (revised OR raised OR lowered OR upgraded OR downgraded OR 상향 OR 하향 OR 수정) (GWh OR TWh OR GW)',
    '(미국 OR "United States" OR "U.S.") (ESS OR "energy storage" OR BESS) (FEOC OR "tax credit" OR 세액공제 OR tariff OR 관세 OR interconnection OR 계통접속 OR "fire code" OR 화재규정 OR permitting OR 인허가) (final rule OR rule change OR enacted OR effective OR 승인 OR 확정 OR 시행 OR 변경)',
])

base.TRUSTED.update({
    'Energy-Storage.News', 'ESS News', 'Benchmark Mineral Intelligence',
    'Reuters', 'Caixin', '전자신문', '이데일리', '연합뉴스', '한국경제',
    'Wood Mackenzie', 'Utility Dive', 'Canary Media',
})
base.OFFICIAL_OR_PRIMARY.update({
    '국가세무총국', '중국 재정부', 'Ministry of Finance of China',
    'State Taxation Administration of China',
    '삼성전기', 'Samsung Electro-Mechanics', 'Murata', '무라타',
    'Taiyo Yuden', '다이요유덴', 'TDK', 'Yageo',
    '전력거래소', 'KPX', '한국전력거래소',
    'SEIA', 'Solar Energy Industries Association',
    'U.S. Energy Storage Coalition', 'US Energy Storage Coalition', 'Energy Storage Coalition',
    'American Clean Power Association', 'ACP',
    'SK온', 'SK On', '엘앤에프', 'L&F', 'DART', '금융감독원 전자공시시스템',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_same_event = ext._same_event

ESS_RE = re.compile(r'\bESS\b|\bBESS\b|energy storage|battery storage|에너지저장|에너지 저장|에너지저장장치|储能', re.I)
BATTERY_RE = re.compile(r'배터리|battery|cell|셀|电池|电芯|CATL|EVE Energy|宁德时代|亿纬锂能|LG에너지솔루션|삼성SDI|SK온', re.I)
MLCC_RE = re.compile(r'\bMLCC\b|적층\s*세라믹\s*커패시터|multilayer ceramic capacitor|삼성전기|Samsung Electro-Mechanics|Murata|무라타|Taiyo Yuden|다이요유덴|TDK|Yageo', re.I)
MLCC_SHORTAGE = re.compile(r'공급난|공급\s*부족|부족|shortage|allocation|배정|납기|lead\s*time|생산\s*차질|bottleneck|병목', re.I)
MLCC_PRICE = re.compile(r'가격\s*인상|가격\s*상승|price\s*hike|price\s*increase|두\s*배|2\s*배|double|ASP|average\s*selling\s*price', re.I)
MLCC_CONTRACT = re.compile(r'장기\s*공급\s*계약|장기공급계약|LTA|공급\s*계약|supply\s*contract|contract|수주|order', re.I)
MLCC_CAPACITY = re.compile(r'증설|생산\s*능력|capacity|가동률|utilization|신규\s*라인|new\s*line|생산량|output', re.I)
MLCC_RELIEF = re.compile(r'이중\s*조달|dual\s*sourcing|재고\s*조정|inventory\s*correction|공급\s*정상화|normalization|가격\s*하락|price\s*cut|lead\s*time.*shorten|납기.*단축', re.I)
MLCC_RELIABILITY = re.compile(r'고전압|high\s*voltage|고신뢰성|high\s*reliability|고온|high\s*temperature|검사|test|수율|yield|절연|insulation', re.I)
HUMANOID_RE = re.compile(r'휴머노이드|humanoid|로봇용 배터리|robot battery|robotics battery', re.I)
SDI_RE = re.compile(r'삼성SDI|Samsung\s*SDI', re.I)
SDI_STORAGE_RE = re.compile(r'\bESS\b|\bBESS\b|energy\s*storage|에너지저장|\bUPS\b|\bBBU\b|무정전전원장치|배터리백업유닛', re.I)
SDI_ESS_MIX_MARGIN = re.compile(r'매출\s*비중|revenue\s*mix|sales\s*mix|영업이익률|operating\s*margin|margin|AMPC|관세\s*환급|tariff\s*refund|본업\s*(?:흑자|이익)', re.I)
SDI_FORECAST = re.compile(r'증권가|전망|예상|추정|컨센서스|forecast|estimate|expected|projected', re.I)
SDI_ACTUAL_EARNINGS = re.compile(r'실적\s*(?:발표|확정)|분기\s*실적|earnings\s*(?:results|release)|results\s*for|actual|확정치|reported', re.I)
SYNERGYCELLS_RE = re.compile(r'SynergyCells|Synergy\s*Cells|시너지셀즈|New\s*Carlisle|뉴\s*칼라일|인디애나', re.I)
SYNERGY_COMPLETE = re.compile(r'준공|공장\s*완공|construction\s*(?:completed|complete)|plant\s*(?:completed|complete)', re.I)
SYNERGY_EQUIPMENT = re.compile(r'장비\s*(?:발주|반입|설치)|equipment\s*(?:order|move[-\s]*in|install)|생산\s*설비\s*(?:반입|설치)', re.I)
SYNERGY_TRIAL = re.compile(r'시험\s*생산|시생산|trial\s*production|pilot\s*production|qualification\s*run', re.I)
SYNERGY_SOP = re.compile(r'양산\s*(?:개시|시작|돌입)|SOP\s*(?:개시|시작)|mass\s*production\s*(?:started|began|commenced)|commercial\s*production\s*(?:started|began)', re.I)
SYNERGY_CAPACITY = re.compile(r'(?:생산\s*능력|capacity).{0,50}\d[\d,.]*\s*(?:GWh|MWh)|\d[\d,.]*\s*(?:GWh|MWh).{0,80}(?:SynergyCells|New\s*Carlisle|시너지셀즈|뉴\s*칼라일)', re.I)
SYNERGY_UTILIZATION = re.compile(r'가동률|utilization|ramp[-\s]*rate|run[-\s]*rate', re.I)
SYNERGY_CONTRACT = re.compile(r'신규\s*수주|공급\s*계약|장기\s*계약|고객\s*확정|customer\s*(?:award|named|selected)|contract|order', re.I)
SYNERGY_BASELINE = re.compile(r'49\.99\s*%|지분\s*전량\s*인수|wholly[-\s]*owned|단독\s*법인|under\s*construction|건설\s*중', re.I)
ESS3_RE = re.compile(
    r'(?:제\s*)?3차.{0,40}(?:ESS|에너지저장장치).{0,50}중앙계약시장|'
    r'(?:ESS|에너지저장장치).{0,50}(?:제\s*)?3차.{0,40}중앙계약시장|'
    r'3차\s*ESS.{0,30}(?:입찰|수주전|시장)',
    re.I,
)
ESS3_PREVIEW = re.compile(
    r'예상|전망|임박|앞두고|수주전|경쟁(?:\s*막)?\s*(?:올라|격화|재점화)|'
    r'나올\s*것으로|공고\s*예정|개설\s*예정|몰두|승부|검토|가능성|관측',
    re.I,
)
ESS3_ACTUAL = re.compile(
    r'입찰\s*공고(?:문)?(?:을|가)?\s*(?:게시|발표|공고|확정)|'
    r'공고(?:를|가)?\s*(?:냈다|게시했다|발표했다|확정했다)|'
    r'공고\s*제\s*\d+|우선협상(?:대상자)?\s*선정|낙찰|입찰\s*마감|'
    r'접수\s*(?:개시|시작)|물량.{0,20}확정|평가(?:기준|방식).{0,20}(?:확정|변경)',
    re.I,
)
KPX_SOURCE_RE = re.compile(r'전력거래소|한국전력거래소|\bKPX\b', re.I)
ESS_LONG_LIFE = re.compile(r'25\s*년|15\s*년|장기\s*계약|계약\s*기간|보증\s*수명|잔존\s*용량|730\s*회|18,?250\s*회|1만\s*8,?250\s*회|90\s*%|70\s*%', re.I)
ESS_LIFETIME_RULE = re.compile(r'(?:25\s*년|15\s*년).{0,80}(?:계약|운전|충.?방전|보증)|(?:잔존\s*용량|보증\s*수명).{0,60}(?:90\s*%|85\s*%|80\s*%|75\s*%|70\s*%)|730\s*회|18,?250\s*회|1만\s*8,?250\s*회', re.I)

US_MARKET_RE = re.compile(r'미국|United\s+States|U\.S\.|\bUS\b|American', re.I)
US_STORAGE_RE = re.compile(r'\bESS\b|\bBESS\b|energy\s+storage|battery\s+storage|에너지저장|에너지\s*저장', re.I)
US_INSTALL_ACTUAL = re.compile(
    r'installed|installations?|added|adds|new\s+capacity|deployment|deployed|'
    r'신규\s*설치|설치\s*규모|새로\s*설치|신규\s*용량|배치',
    re.I,
)
US_PERIOD = re.compile(r'\bQ[1-4]\b|[1-4](?:st|nd|rd|th)\s+quarter|분기|상반기|하반기|first\s+half|second\s+half', re.I)
US_GWH = re.compile(r'\d[\d,.]*\s*GWh', re.I)
US_RECORD = re.compile(r'record|largest\s+quarter|all[-\s]*time\s+high|역대\s*최대|사상\s*최대|신기록', re.I)
US_INSTALL_BASELINE_Q2_2026 = re.compile(
    r'(?:Q2|2분기|second\s+quarter).{0,120}(?:20(?:\.2)?\s*GWh)|'
    r'(?:20(?:\.2)?\s*GWh).{0,120}(?:Q2|2분기|second\s+quarter)',
    re.I,
)
US_H1_BASELINE_2026 = re.compile(
    r'(?:상반기|first\s+half|H1).{0,120}30\.8\s*GWh|30\.8\s*GWh.{0,120}(?:상반기|first\s+half|H1)',
    re.I,
)
US_TARGET_CONTEXT = re.compile(r'target|goal|on\s+pace|deploy|deployment|목표|달성|구축|확대', re.I)
US_TARGET_BASELINE = re.compile(
    r'(?:225\s*GW.{0,120}1\s*TWh|1\s*TWh.{0,120}225\s*GW|'
    r'1\s*terawatt[-\s]*hour|1\s*TWh).{0,160}2032|'
    r'2032.{0,160}(?:225\s*GW|1\s*TWh|1\s*terawatt[-\s]*hour)',
    re.I,
)
US_TARGET_REVISION_WORDS = re.compile(r'revis|raise|lower|increase|decrease|accelerat|delay|push\s+back|extend|상향|하향|수정|변경|앞당|연기|늦춰', re.I)
US_FORECAST = re.compile(r'forecast|outlook|projection|전망|예측', re.I)
US_FORECAST_CHANGE = re.compile(r'revis|raise|lower|upgrade|downgrade|increase|decrease|상향|하향|수정|변경', re.I)
US_POLICY = re.compile(r'FEOC|foreign\s+entity|tax\s+credit|세액공제|tariff|관세|interconnection|계통\s*접속|fire\s+code|화재\s*규정|permitting|인허가|domestic\s+content|현지\s*조달', re.I)
US_POLICY_CHANGE = re.compile(r'final\s+rule|rule\s+change|effective|enacted|adopted|approved|확정|시행|발효|개정|변경|승인', re.I)


def _extract_us_target(text: str) -> tuple[float | None, float | None, int | None]:
    twh = None
    gw = None
    year = None
    m = re.search(r'(\d+(?:\.\d+)?)\s*TWh|([0-9]+(?:\.[0-9]+)?)\s*terawatt[-\s]*hours?', text, re.I)
    if m:
        try:
            twh = float(m.group(1) or m.group(2))
        except Exception:
            pass
    m = re.search(r'(\d+(?:\.\d+)?)\s*GW', text, re.I)
    if m:
        try:
            gw = float(m.group(1))
        except Exception:
            pass
    years = [int(x) for x in re.findall(r'\b20(?:2[6-9]|3\d)\b', text)]
    if years:
        year = max(years)
    return twh, gw, year


def _us_ess_stage(text: str, source: str = '') -> str:
    source_text = f'{text} {source}'
    if not (US_STORAGE_RE.search(source_text) and US_MARKET_RE.search(source_text)):
        return ''
    official_install = bool(
        re.search(r'SEIA|Solar\s+Energy\s+Industries\s+Association|Benchmark\s+Mineral', source_text, re.I)
    )
    if official_install and US_INSTALL_ACTUAL.search(text) and US_PERIOD.search(text) and US_GWH.search(text):
        if US_INSTALL_BASELINE_Q2_2026.search(text) or US_H1_BASELINE_2026.search(text):
            return 'us_install_baseline'
        return 'us_install_actual'
    target_source = bool(
        re.search(r'U\.S\.\s+Energy\s+Storage\s+Coalition|US\s+Energy\s+Storage\s+Coalition|Energy\s+Storage\s+Coalition|\bESC\b', source_text, re.I)
    )
    if target_source and US_TARGET_CONTEXT.search(text) and re.search(r'203\d|TWh|terawatt[-\s]*hour|\b\d+\s*GW\b', text, re.I):
        twh, gw, year = _extract_us_target(text)
        changed = US_TARGET_REVISION_WORDS.search(text)
        if (twh is not None and abs(twh - 1.0) > 1e-9) or (gw is not None and abs(gw - 225.0) > 1e-9) or (year is not None and year != 2032):
            changed = True
        if changed:
            return 'us_target_revision'
        if US_TARGET_BASELINE.search(text):
            return 'us_target_baseline'
    if US_FORECAST.search(text) and US_FORECAST_CHANGE.search(text) and re.search(r'\d[\d,.]*\s*(?:GWh|TWh|GW)', text, re.I):
        return 'us_forecast_revision'
    if US_POLICY.search(text) and US_POLICY_CHANGE.search(text):
        return 'us_policy_change'
    return ''


def _ess3_stage(text: str, source: str = '') -> str:
    if not ESS3_RE.search(text):
        return ''
    if re.search(r'우선협상|낙찰|선정', text, re.I):
        return 'award'
    if re.search(r'평가(?:기준|방식).{0,20}(?:확정|변경)', text, re.I):
        return 'rules'
    if re.search(r'물량.{0,20}확정|(?:\d[\d,.]*)\s*(?:MW|GW).{0,30}확정', text, re.I):
        return 'volume'
    if ESS3_ACTUAL.search(text) and (KPX_SOURCE_RE.search(source) or not ESS3_PREVIEW.search(text)):
        return 'notice'
    return 'preview'

KOREA_CONTRACT_RE = re.compile(r'계약|공급|수주|purchase|supply|contract|order', re.I)
LFP_RE = re.compile(r'\bLFP\b|리튬인산철|磷酸铁锂', re.I)
SKON_RE = re.compile(r'SK온|SK\s*On|에스케이온', re.I)
LNF_RE = re.compile(r'엘앤에프|L&F|L\s*and\s*F', re.I)

def _skon_lnf_lfp_contract(text: str) -> bool:
    return bool(SKON_RE.search(text) and LNF_RE.search(text) and LFP_RE.search(text) and KOREA_CONTRACT_RE.search(text))

SKON_LNF_LFP_KEY = 'ess|skon-lnf|lfp-cathode|2026-09-17|1617eok'

ESS_COMPANIES = [
    ('skon', re.compile(r'SK온|SK\\s*On|에스케이온', re.I)),
    ('lnf', re.compile(r'엘앤에프|L&F|L\\s*and\\s*F', re.I)),
    ('lges', re.compile(r'LG에너지솔루션|LG\\s*Energy\\s*Solution', re.I)),
    ('samsungsdi', re.compile(r'삼성SDI|Samsung\\s*SDI', re.I)),
    ('ecoprobm', re.compile(r'에코프로비엠|EcoPro\\s*BM', re.I)),
    ('poscofuturem', re.compile(r'포스코퓨처엠|POSCO\\s*Future\\s*M', re.I)),
]
MATERIAL_TAGS = [
    ('lfp-cathode', re.compile(r'\\bLFP\\b.{0,40}양극재|양극재.{0,40}\\bLFP\\b|리튬인산철.{0,20}양극재', re.I)),
    ('lfp-cell', re.compile(r'\\bLFP\\b.{0,40}(?:셀|cell)|(?:셀|cell).{0,40}\\bLFP\\b', re.I)),
    ('cathode', re.compile(r'양극재|cathode', re.I)),
    ('cell', re.compile(r'배터리\\s*셀|battery\\s*cell|전지', re.I)),
]

def _company_tags(text: str) -> list[str]:
    return sorted(name for name, rx in ESS_COMPANIES if rx.search(text))

def _material_tag(text: str) -> str:
    for name, rx in MATERIAL_TAGS:
        if rx.search(text):
            return name
    return 'ess-material'

def _contract_amount_bucket(text: str) -> str:
    vals = []
    for m in re.finditer(r'(\\d[\\d,]*(?:\\.\\d+)?)\\s*억원', text):
        try:
            vals.append(float(m.group(1).replace(',', '')))
        except Exception:
            pass
    if not vals:
        return 'amount-unknown'
    v = max(vals)
    if v >= 1000:
        return f'{round(v / 100) * 100:.0f}eok'
    if v >= 100:
        return f'{round(v / 10) * 10:.0f}eok'
    return f'{round(v):.0f}eok'

def _generic_korean_supply_contract(text: str) -> bool:
    return bool(
        ESS_RE.search(text)
        and KOREA_CONTRACT_RE.search(text)
        and len(_company_tags(text)) >= 2
        and re.search(r'양극재|cathode|\\bLFP\\b|배터리\\s*셀|battery\\s*cell', text, re.I)
    )



def _is_mlcc_ess(text: str) -> bool:
    return bool(ESS_RE.search(text) and MLCC_RE.search(text) and not HUMANOID_RE.search(text))


def _sdi_ess_stage(text: str, source: str = '') -> str:
    if not SDI_RE.search(text):
        return ''
    if SYNERGYCELLS_RE.search(text):
        if SYNERGY_CONTRACT.search(text):
            return 'synergy_contract'
        if SYNERGY_SOP.search(text):
            return 'synergy_sop'
        if SYNERGY_TRIAL.search(text):
            return 'synergy_trial'
        if SYNERGY_EQUIPMENT.search(text):
            return 'synergy_equipment'
        if SYNERGY_COMPLETE.search(text):
            return 'synergy_complete'
        if SYNERGY_CAPACITY.search(text):
            return 'synergy_capacity'
        if SYNERGY_UTILIZATION.search(text):
            return 'synergy_utilization'
        if SYNERGY_BASELINE.search(text):
            return 'synergy_baseline'
    if SDI_STORAGE_RE.search(text) and SDI_ESS_MIX_MARGIN.search(text):
        official = source in base.OFFICIAL_OR_PRIMARY
        if SDI_FORECAST.search(text) and not (official and SDI_ACTUAL_EARNINGS.search(text)):
            return 'earnings_forecast'
        if official or SDI_ACTUAL_EARNINGS.search(text):
            return 'earnings_actual'
        return 'earnings_unconfirmed'
    return ''


def _is_ess_battery(text: str) -> bool:
    ess = ESS_RE.search(text)
    supply_component = BATTERY_RE.search(text) or MLCC_RE.search(text)
    sdi_storage = bool(SDI_RE.search(text) and SDI_STORAGE_RE.search(text))
    us_market = bool(_us_ess_stage(text))
    # Official KPX market-design/lifetime rules are themselves battery-demand
    # state changes even when the headline says only "ESS" and does not repeat
    # a cell-maker name. Keep them in the ESS-battery lane so the primary source
    # can outrank derivative media coverage.
    official_lifetime_rule = bool(
        ess and ESS_LIFETIME_RULE.search(text) and KPX_SOURCE_RE.search(text)
    )
    return bool(
        (ess and supply_component and not HUMANOID_RE.search(text))
        or sdi_storage
        or us_market
        or official_lifetime_rule
    )


def topic_group(text: str) -> str | None:
    if _is_ess_battery(text):
        return 'ess_battery'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) != 'ess_battery':
        return _orig_score(item)

    source = item.get('source') or ''
    us_stage = _us_ess_stage(text, source)
    if us_stage == 'us_install_actual':
        if source in base.OFFICIAL_OR_PRIMARY:
            return 'SEIA 등 공식 원자료 · 분기/누적 GWh 실제 설치량과 기준기간 확인'
        return 'SEIA·Benchmark 원자료를 인용한 보도 · 실제 설치 GWh를 공식자료로 교차확인'
    if us_stage == 'us_target_revision':
        return 'U.S. Energy Storage Coalition 공식 목표 · 225GW/1TWh/2032 기준선 대비 변경 확인'
    if us_stage == 'us_forecast_revision':
        return 'SEIA·Benchmark 등 공식/신뢰 전망자료 · 수정 전후 GWh·기준연도 비교'
    if us_stage == 'us_policy_change':
        return '미국 공식 정책·규정 원문 우선 · FEOC/세액공제/관세/계통접속/화재안전 시행조건 교차확인'
    if us_stage in {'us_install_baseline', 'us_target_baseline'}:
        return '기준선 등록 · 새 단계 변화 아님'
    sdi_stage = _sdi_ess_stage(text, source)
    us_stage = _us_ess_stage(text, source)
    if sdi_stage in {'earnings_forecast', 'earnings_unconfirmed', 'synergy_baseline'}:
        return 0
    if us_stage in {'us_install_baseline', 'us_target_baseline'}:
        return 0
    ess3_stage = _ess3_stage(text, source)
    # Generic "3rd ESS market is coming / competition heats up" articles are
    # background repeats, not a new state change. Alert only when a notice,
    # confirmed volume/rule change, or award materially advances the process.
    if ess3_stage == 'preview':
        return 0

    s = 9
    if us_stage:
        s = 21
        s += {
            'us_install_actual': 13,
            'us_target_revision': 12,
            'us_forecast_revision': 11,
            'us_policy_change': 13,
        }.get(us_stage, 0)
        if US_RECORD.search(text):
            s += 4
    if sdi_stage:
        s = max(s, 19)
        s += {
            'earnings_actual': 12,
            'synergy_complete': 10,
            'synergy_equipment': 11,
            'synergy_trial': 13,
            'synergy_sop': 16,
            'synergy_capacity': 11,
            'synergy_utilization': 10,
            'synergy_contract': 15,
        }.get(sdi_stage, 0)
    if base.NUMERIC.search(text):
        s += 3
    if re.search(r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause|신규\s*공장|greenfield|미착공|产能|审批', text, re.I):
        s += 6
    if re.search(r'소비세|consumption tax|消费税|2%|4%', text, re.I):
        s += 5
    if re.search(r'314\s*Ah|0\.414|0\.423|가격\s*인상|price\s*hike|提价|Wh당|/Wh', text, re.I):
        s += 6
    if re.search(r'수주|계약|공급|order|contract|supply|생산능력|capacity', text, re.I):
        s += 4
    if ESS_LIFETIME_RULE.search(text):
        s += 10

    if _is_mlcc_ess(text):
        s += 8
        if MLCC_SHORTAGE.search(text):
            s += 8
        if MLCC_PRICE.search(text):
            s += 6
        if MLCC_CONTRACT.search(text):
            s += 8
        if MLCC_CAPACITY.search(text):
            s += 7
        if MLCC_RELIEF.search(text):
            s += 7
        if MLCC_RELIABILITY.search(text):
            s += 4

    if source in base.OFFICIAL_OR_PRIMARY:
        s += 5
    elif source in base.TRUSTED:
        s += 3
    return s


def _raw_cat(text: str) -> str:
    us_stage = _us_ess_stage(text)
    if us_stage == 'us_install_actual':
        return '미국 실설치·수요'
    if us_stage == 'us_target_revision':
        return '미국 2032 목표 변경'
    if us_stage == 'us_forecast_revision':
        return '미국 설치 전망 변경'
    if us_stage == 'us_policy_change':
        return '미국 정책·계통·안전 조건 변경'
    sdi_stage = _sdi_ess_stage(text)
    if sdi_stage == 'earnings_actual':
        return '삼성SDI 실적 질·본업 수익성'
    if sdi_stage in {'synergy_complete', 'synergy_equipment', 'synergy_trial', 'synergy_sop', 'synergy_capacity', 'synergy_utilization', 'synergy_contract'}:
        return '삼성SDI SynergyCells 가동 전환'
    if _is_mlcc_ess(text):
        if MLCC_RELIEF.search(text):
            return 'MLCC 공급완화·재고조정'
        if MLCC_CONTRACT.search(text) or MLCC_CAPACITY.search(text):
            return 'MLCC 장기계약·생산능력'
        if MLCC_PRICE.search(text):
            return 'MLCC 가격·납기 병목'
        if MLCC_SHORTAGE.search(text):
            return 'MLCC 공급 병목'
        if MLCC_RELIABILITY.search(text):
            return 'MLCC 고전압·신뢰성 병목'
        return 'MLCC 수급 구조'
    if re.search(r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause|신규\s*공장|greenfield|미착공|审批', text, re.I):
        return '중국 증설·승인 규제'
    if re.search(r'314\s*Ah|0\.414|0\.423|가격\s*인상|price\s*hike|提价|소비세|consumption tax|消费税', text, re.I):
        return '셀 가격·소비세'
    if ESS_LIFETIME_RULE.search(text):
        return '장기계약·수명보증'
    if re.search(r'LG에너지솔루션|삼성SDI|SK온|LG Energy Solution|Samsung SDI|SK On|에코프로비엠|포스코퓨처엠|엘앤에프', text, re.I):
        return '한국 공급망·수주'
    return '수급·가격 구조'


def category(text: str, group: str) -> str:
    if group == 'ess_battery':
        return f"ESS 배터리 · {_raw_cat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '미국 실설치·수요':
        return '미국 ESS의 실제 분기 신규 설치 GWh와 누적 설치량이 바뀌는 수요 확인 신호입니다. 업계 목표나 증권사 전망보다 실제 설치량을 우선하고, 전년동기 성장률·분기 신기록 여부를 한국 배터리 3사의 북미 생산능력·수주·가동률과 연결해 추적합니다.'
    if raw == '미국 2032 목표 변경':
        return 'U.S. Energy Storage Coalition의 225GW·1TWh·2032 기준선이 상향·하향되거나 일정이 바뀌는 구조적 수요 신호입니다. 목표 변경 폭과 필요한 연평균 성장률, 미국 현지 셀·시스템 생산능력의 격차를 함께 봅니다.'
    if raw == '미국 설치 전망 변경':
        return 'SEIA·Benchmark 등 신뢰 가능한 원천의 미국 ESS 설치 전망이 공식적으로 상향·하향되는 신호입니다. 전망 반복이 아니라 기준 연도·GWh가 실제로 수정됐을 때만 알립니다.'
    if raw == '미국 정책·계통·안전 조건 변경':
        return 'FEOC·세액공제·관세·계통접속·화재안전·인허가 규칙이 실제 ESS 설치 속도와 현지생산 경쟁력을 바꾸는 신호입니다. 정책 발표가 프로젝트 지연·원가·한국 3사 수주에 연결되는지를 확인합니다.'
    if raw == '삼성SDI 실적 질·본업 수익성':
        return '증권가의 ESS 매출비중·마진 전망이 아니라 회사 분기 실적에서 실제 ESS/UPS/BBU 비중과 수익성이 확인되는 단계입니다. AMPC·관세환급 등 일회성/정책성 이익을 분리해 반복 가능한 본업 영업이익과 현금창출력을 추적합니다.'
    if raw == '삼성SDI SynergyCells 가동 전환':
        return 'GM 지분 인수와 건설 중이라는 기준선을 넘어 New Carlisle SynergyCells가 준공→장비 반입→시험생산→SOP→GWh 생산능력·가동률→고객 수주로 전환되는 단계입니다. 각 단계가 북미 ESS 매출과 감가상각·총자산이익률에 실제로 연결되는지 봅니다.'
    if raw == '장기계약·수명보증':
        return 'ESS 중앙계약시장의 계약기간이 최대 25년으로 길어지고 충·방전 횟수·잔존용량 평가가 강화되면 초기 셀 가격보다 장기 열화율·배터리관리시스템·열관리·교체비용이 수주 경쟁력을 좌우합니다. 25년형의 연 730회, 총 1만8,250회 운전과 종료 시 잔존용량 평가를 실제 보증조건·시스템 설계에 연결해 추적합니다.'
    if raw == 'MLCC 공급 병목':
        return 'ESS 전력 제어에 필요한 MLCC가 부족해지면 원가 비중이 작아도 전체 ESS 출하가 지연될 수 있습니다. 가격 자체보다 공급 배정·납기·실제 생산차질을 우선 추적합니다.'
    if raw == 'MLCC 가격·납기 병목':
        return 'ESS용 MLCC 가격 인상과 납기 장기화가 동시에 나타나는지 추적합니다. 기사상의 가격 2배 가능성은 전망으로 두고 실제 공급사 공지·계약·거래단가 확인 시에만 확정으로 승격합니다.'
    if raw == 'MLCC 장기계약·생산능력':
        return '공급 부족이 장기공급계약·선구매·증설로 이어지는 단계입니다. 고객 실명, 계약금액, 생산능력, 가동률과 실제 ESS향 물량이 확인될 때 공급사 매출 연결 강도를 높입니다.'
    if raw == 'MLCC 공급완화·재고조정':
        return '이중조달, 납기 단축, 재고조정, 공급 정상화는 MLCC 가격·가동률 고점이 꺾이는 반대 신호입니다. ESS 수요 둔화와 공급사 증설 효과를 함께 확인합니다.'
    if raw == 'MLCC 고전압·신뢰성 병목':
        return 'ESS용 MLCC는 고전압·고온·장시간 운전 신뢰성이 중요합니다. 고전압 검사시간, 절연 불량, 수율과 고객 인증이 생산능력의 실제 병목인지 추적합니다.'
    if raw == 'MLCC 수급 구조':
        return 'AI 서버·자동차·ESS가 동시에 고사양 MLCC 생산능력을 사용하면서 공급 우선순위가 바뀌는지 추적합니다. ESS향 실제 공급·납기 변화가 확인돼야 배터리 공급망 신호로 승격합니다.'
    if raw == '중국 증설·승인 규제':
        return '중국의 미착공 ESS 배터리 신규 생산능력 확대가 제동되면 장기간의 공급과잉·가격하락 압력이 완화될 수 있습니다. 한국 배터리의 반사이익은 북미·유럽 ESS 수주와 현지 생산 가동률이 실제로 늘어나는지까지 확인합니다.'
    if raw == '셀 가격·소비세':
        return '중국 ESS 셀 가격이 하락 일변도에서 반등하는지 추적합니다. 314Ah 셀 가격·소비세 전가·중소업체 후속 인상이 시스템통합업체 원가와 프로젝트 견적에 어떻게 전달되는지가 핵심입니다.'
    if raw == '한국 공급망·수주':
        return '중국 공급조절·가격 반등이 한국 셀·소재 업체의 실제 ESS 주문, 생산능력 가동, 평균판매단가 개선으로 연결되는지 확인합니다.'
    if raw == '수급·가격 구조':
        return 'ESS 셀의 공급량·가격·세금·증설 정책이 동시에 바뀌는지 보고 한국 배터리의 가격 경쟁력과 수주 환경 재평가 가능성을 확인합니다.'
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw == '미국 실설치·수요':
        return '분기 설치량 신기록이 곧 한국 배터리 3사의 매출을 뜻하지 않습니다. 중국산·미국산 공급 비중, 프로젝트 지연, 셀 가격, 고객별 계약과 실제 가동률을 분리해야 합니다. 먼저 볼 지표는 다음 분기 GWh, 전년동기 성장률, 북미 공장 가동률입니다.'
    if raw == '미국 2032 목표 변경':
        return '1TWh는 산업계 목표이지 연방정부의 의무 설치량이 아닙니다. 계통접속·인허가·화재보험·정책 불확실성으로 실제 설치가 목표에 못 미칠 수 있습니다.'
    if raw == '미국 설치 전망 변경':
        return '전망치 상향은 실제 설치가 아닙니다. 프로젝트 취소·접속 지연·금리·셀 가격 변화로 전망이 다시 하향될 수 있으므로 이후 분기 실설치량으로 검증합니다.'
    if raw == '미국 정책·계통·안전 조건 변경':
        return '정책이 한국 업체에 유리해 보여도 현지조달 비용과 인증·보험 비용이 함께 상승할 수 있습니다. 규정 시행일·과도기·예외조항과 실제 프로젝트 착공 지연을 확인합니다.'
    if raw == '삼성SDI 실적 질·본업 수익성':
        return 'AMPC를 뺐다고 곧바로 순수 본업 이익이 되는 것은 아닙니다. 관세환급·환율·평가손익·일회성 비용을 추가 분리하고, ESS 매출비중이 올라가도 실제 영업이익률·가동률·운전자본·영업현금흐름이 동반 개선되는지 확인합니다.'
    if raw == '삼성SDI SynergyCells 가동 전환':
        return '공장 준공이나 명목 GWh 생산능력만으로 매출을 확정할 수 없습니다. 고객 수주·시험생산 수율·가동률이 늦으면 감가상각과 운전자본 부담이 먼저 커져 총자산이익률이 악화될 수 있습니다.'
    if raw == '장기계약·수명보증':
        return '25년 계약은 배터리 셀이 25년 동안 교체 없이 동일 성능을 유지한다는 뜻이 아닙니다. 셀 편차·열관리·자연열화·보증충당금·유지보수 비용이 누적될 수 있고, 기사상 평가조건과 실제 낙찰 프로젝트별 보증·교체 책임을 구분해야 합니다.'
    if raw == 'MLCC 공급 병목':
        return 'MLCC 공급난이 곧 삼성전기 등 특정 업체의 ESS 매출 확정을 뜻하지 않습니다. 고객·규격·물량·단가가 확인되지 않으면 직접 수혜는 후보 단계로 유지합니다.'
    if raw == 'MLCC 가격·납기 병목':
        return '언론의 두 배 가격 가능성은 확정 단가가 아닙니다. 선구매·중복주문이 섞이면 실제 최종수요보다 부족이 과장될 수 있어 공급사 공지와 고객 거래조건을 재확인합니다.'
    if raw == 'MLCC 장기계약·생산능력':
        return 'AI 서버용 장기계약이나 증설을 ESS향 매출로 자동 치환하지 않습니다. ESS 고객과 적용 규격이 확인돼야 직접 연결로 분류하며, 증설 후 공급과잉·가동률 하락 위험도 같이 봅니다.'
    if raw == 'MLCC 공급완화·재고조정':
        return '공급 정상화가 빠르면 가격 인상과 장기계약의 협상력이 약해질 수 있습니다. 재고 증가와 평균판매단가 하락이 동시에 나타나는지 확인합니다.'
    if raw == 'MLCC 고전압·신뢰성 병목':
        return '고사양 MLCC는 범용 설비 증설만으로 바로 공급이 늘지 않을 수 있습니다. 고전압 검사·절연·적층 수율이 낮으면 생산능력 숫자보다 실제 출하가 뒤처질 수 있습니다.'
    if raw == 'MLCC 수급 구조':
        return 'AI 서버 수요만 강하고 ESS향 실제 물량이 확인되지 않으면 ESS 공급망 수혜로 확대해석하지 않습니다. 고객 이중조달과 신규 공급사 인증도 기존 업체 점유율을 낮출 수 있습니다.'
    if raw == '중국 증설·승인 규제':
        return '현재 신규 승인 중단은 중앙정부의 공개된 공식 전면 금지령이 아니라 업계·현지 매체를 통해 확인되는 잠정 조치입니다. 이미 건설 중인 프로젝트는 계속될 수 있어 즉각적인 공급부족으로 해석하면 안 됩니다.'
    if raw == '셀 가격·소비세':
        return 'CATL의 0.414→0.423위안/Wh 인상과 EVE의 2% 할증은 중국 내수 중심입니다. 수출은 세금 환급 구조가 달라 글로벌 수출가격이 같은 폭으로 오르는 것은 아닙니다.'
    if raw == '한국 공급망·수주':
        return '중국의 공급조절만으로 한국 업체 매출이 자동 증가하지 않습니다. 고객 실명·GWh 수주·단가·현지 생산 가동률이 확인되지 않으면 반사이익은 기대감 단계입니다.'
    if raw == '수급·가격 구조':
        return '단기 세금 전가와 구조적인 공급 부족을 구분해야 합니다. 중국 내수 가격 반등이 수출 가격과 글로벌 ESS 프로젝트 가격까지 이어지는지 확인해야 합니다.'
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group != 'ess_battery':
        return _orig_verification(item, group, text)
    source = item.get('source') or ''
    sdi_stage = _sdi_ess_stage(text, source)
    if sdi_stage == 'earnings_actual':
        if source in base.OFFICIAL_OR_PRIMARY:
            return '삼성SDI 공식 실적·IR · ESS/UPS/BBU 실제 비중과 AMPC·관세환급·본업 이익을 분리 확인'
        return '실적 보도 단계 · 삼성SDI 공식 분기실적/IR로 실제 비중·마진·일회성 항목 교차확인'
    if sdi_stage in {'synergy_complete', 'synergy_equipment', 'synergy_trial', 'synergy_sop', 'synergy_capacity', 'synergy_utilization', 'synergy_contract'}:
        if source in base.OFFICIAL_OR_PRIMARY:
            return '삼성SDI 공식자료 · SynergyCells 준공/장비/시험생산/SOP/생산능력/가동률/수주 단계 확인'
        return '보도 단계 · 삼성SDI·고객사 공식자료로 SynergyCells 단계 변화 교차확인'
    if sdi_stage in {'earnings_forecast', 'earnings_unconfirmed', 'synergy_baseline'}:
        return '기준선·추정 단계 · 새 확정 실적/가동 단계 아님'
    if ESS_LIFETIME_RULE.search(text):
        return '전력거래소 조건을 인용한 보도 · 계약기간·충방전·잔존용량 평가조건은 KPX 공고 원문으로 교차확인'
    if _is_mlcc_ess(text):
        if source in base.OFFICIAL_OR_PRIMARY:
            return '공급사 공식자료 · ESS 적용·고객·물량·단가를 별도 확인'
        if MLCC_PRICE.search(text):
            return '신뢰 매체 보도 · 가격 인상은 공급사 공지/계약 확인 전 전망 단계'
        if MLCC_SHORTAGE.search(text):
            return '신뢰 매체 보도 · ESS 생산차질·납기·공급배정 교차확인'
        if source in base.TRUSTED:
            return '신뢰 매체 보도 · 공급사/고객사 공식자료 교차확인'
        return '보도 단계 · ESS 적용과 공급사 직접 연결 추가확인 필요'
    if re.search(r'소비세|consumption tax|消费税', text, re.I) and source in base.OFFICIAL_OR_PRIMARY:
        return '중국 세무·재정 공식자료'
    if re.search(r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause', text, re.I):
        return 'Reuters·중국 매체 교차보도 · 중앙정부 공식 공고는 미확인'
    if re.search(r'0\.414|0\.423|314\s*Ah|가격\s*인상|price\s*hike', text, re.I):
        return '전문매체·업계 가격자료 · 업체 공지/세금 정책 교차확인'
    if source in base.OFFICIAL_OR_PRIMARY:
        return '공식자료'
    if source in base.TRUSTED:
        return '신뢰 매체 보도 · 공식자료 교차확인'
    return '보도 단계 · 추가 교차검증 필요'


def _numbers(text: str) -> set[str]:
    return set(re.findall(r'\d[\d,.]*\s*(?:조원|억원|억|만원|원|%|배|개월|주|일|GWh|MWh|GW|MW)', text, re.I))


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'ess_battery' or b.get('group') != 'ess_battery':
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    if ESS_LIFETIME_RULE.search(ta) and ESS_LIFETIME_RULE.search(tb):
        return True

    sa3, sb3 = _ess3_stage(ta, a.get('source') or ''), _ess3_stage(tb, b.get('source') or '')
    if sa3 and sb3 and sa3 == sb3:
        return True

    usa, usb = _us_ess_stage(ta, a.get('source') or ''), _us_ess_stage(tb, b.get('source') or '')
    if usa and usb and usa == usb:
        na, nb = _numbers(ta), _numbers(tb)
        if na and nb:
            return bool(na & nb)
        return True

    sda, sdb = _sdi_ess_stage(ta, a.get('source') or ''), _sdi_ess_stage(tb, b.get('source') or '')
    if sda and sdb and sda == sdb:
        nums_a, nums_b = _numbers(ta), _numbers(tb)
        if nums_a and nums_b:
            return bool(nums_a & nums_b)
        return True

    if _skon_lnf_lfp_contract(ta) and _skon_lnf_lfp_contract(tb):
        return True
    if _generic_korean_supply_contract(ta) and _generic_korean_supply_contract(tb):
        if _company_tags(ta) == _company_tags(tb) and _material_tag(ta) == _material_tag(tb):
            aa, ab = _contract_amount_bucket(ta), _contract_amount_bucket(tb)
            if aa == ab or 'amount-unknown' in {aa, ab}:
                return True

    if _is_mlcc_ess(ta) and _is_mlcc_ess(tb):
        axes = [MLCC_SHORTAGE, MLCC_PRICE, MLCC_CONTRACT, MLCC_CAPACITY, MLCC_RELIEF, MLCC_RELIABILITY]
        same_axis = any(rx.search(ta) and rx.search(tb) for rx in axes)
        if not same_axis:
            return False
        na, nb = _numbers(ta), _numbers(tb)
        # Same figures across different outlets are the same event. A later
        # changed price/lead-time/capacity/contract figure remains a new event.
        if na and nb:
            return bool(na & nb)
        return True

    approval = r'승인\s*(?:중단|보류)|pause.*approval|approval.*pause|미착공|greenfield'
    price = r'314\s*Ah|0\.414|0\.423|가격\s*인상|price\s*hike|2%\s*(?:소비세|할증)|소비세.*2%'
    if re.search(approval, ta, re.I) and re.search(approval, tb, re.I):
        return True
    if re.search(price, ta, re.I) and re.search(price, tb, re.I):
        # Keep approval-pause and price/tax as two separate ESS events.
        if not (re.search(approval, ta, re.I) or re.search(approval, tb, re.I)):
            return True
    return False



def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    import hashlib
    source = item.get('source') or ''
    us_stage = _us_ess_stage(text, source)
    sdi_stage = _sdi_ess_stage(text, source)
    stage3 = _ess3_stage(text, source)
    if us_stage:
        nums = sorted(_numbers(text))
        q = re.search(r'\bQ[1-4]\b|[1-4]분기|상반기|하반기|first\s+half|second\s+half', text, re.I)
        period = re.sub(r'\s+', '-', q.group(0).lower()) if q else 'no-period'
        suffix = '|'.join(nums[:4]) if nums else 'no-number'
        return hashlib.sha256(f'us-ess|{us_stage}|{period}|{suffix}'.encode()).hexdigest()
    if sdi_stage:
        nums = sorted(_numbers(text))
        suffix = '|'.join(nums[:3]) if nums else 'no-number'
        return hashlib.sha256(f'samsung-sdi|ess|{sdi_stage}|{suffix}'.encode()).hexdigest()
    if ESS_LIFETIME_RULE.search(text):
        return hashlib.sha256(b'ess|kpx-central-market|2026|25y-lifetime-rules').hexdigest()
    if stage3:
        return hashlib.sha256(f'ess-central-market-3|2026|{stage3}'.encode()).hexdigest()
    if _skon_lnf_lfp_contract(text):
        return hashlib.sha256(SKON_LNF_LFP_KEY.encode()).hexdigest()
    if _generic_korean_supply_contract(text):
        parties = '-'.join(_company_tags(text))
        material = _material_tag(text)
        amount = _contract_amount_bucket(text)
        return hashlib.sha256(f'ess-contract|{parties}|{material}|{amount}'.encode()).hexdigest()
    return _orig_key(item)


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.key = key
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()

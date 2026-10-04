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
    '(CATL OR 宁德时代) (Debrecen OR 德布勒森 OR 데브레첸 OR 헝가리 OR Hungary) (cell OR 电芯 OR 배터리셀 OR battery cell) (trial production OR 试生产 OR series production OR mass production OR 正式量产 OR 양산 OR 시험생산 OR 출하 OR shipment OR utilization OR 가동률 OR 100GWh OR 100 GWh OR 중단 OR shutdown OR permit OR 许可)',
    '(이수스페셜티케미컬 OR "ISU Specialty Chemical") (황화리튬 OR Li2S OR "lithium sulfide") (상업생산 OR commercial production OR 양산 OR 생산 OR 가동 OR 납품 OR shipment OR 공급계약 OR contract OR 고객 OR sample OR 샘플 OR 150톤 OR 150t OR 500톤 OR 500t OR 증설 OR 확대 OR 지연 OR 연기 OR 황화수소 OR H2S OR 안전 OR 사고 OR IR OR 기업설명회 OR "Analyst Day")',
    '("46시리즈" OR "46 시리즈" OR "46-series" OR "46 series" OR 4680 OR 4695 OR 46100 OR 46120) (LG에너지솔루션 OR "LG Energy Solution" OR 삼성SDI OR "Samsung SDI" OR Tesla OR Rivian OR BMW OR Mercedes-Benz OR Mercedes OR 벤츠 OR Chery OR 체리 OR Volvo OR 볼보 OR indiGOtech) (수주 OR 계약 OR 공급 OR GWh OR 고객 OR 양산 OR SOP OR 생산능력 OR capacity OR 공장 OR line OR 라인 OR 장비 OR equipment OR 모듈 OR BMA OR 지연 OR 취소)',
    '(LG에너지솔루션 OR "LG Energy Solution") ("46시리즈" OR "46-series" OR 4680 OR 4695 OR 46100 OR 46120) (440GWh OR 100GWh OR 수주잔고 OR backlog OR 신규수주 OR new orders OR 퀸크릭 OR Queen Creek OR 애리조나 OR Arizona OR 폴란드 OR Poland OR 브로츠와프 OR Wroclaw OR 오창 OR Ochang) (양산 OR SOP OR equipment OR 장비 OR line OR 라인 OR GWh OR yield OR 수율 OR utilization OR 가동률)',
    '(삼성SDI OR "Samsung SDI") ("46시리즈" OR "46-series" OR 4680 OR 4695 OR 46100 OR 46120) (EV OR 전기차 OR 고객 OR customer OR supply OR 공급 OR order OR 수주 OR production OR 양산 OR capacity OR GWh OR BMW OR KGM)',
    '(Volvo OR 볼보 OR Mercedes-Benz OR Mercedes OR 벤츠 OR BMW OR Rivian OR 리비안 OR Chery OR 체리 OR Tesla OR 테슬라) ("46 mm" OR 46mm OR "46시리즈" OR "46-series" OR 4680 OR 4695 OR 46100 OR 46120) (confirm OR confirmed OR contract OR supplier OR supply OR award OR 채택 OR 확정 OR 계약 OR 공급사 OR 수주)',
    '(에코프로비엠 OR "EcoPro BM" OR 케이엔에스 OR KNS OR 엠오티 OR MOT OR "Wonik PNE" OR 원익피앤이) ("46시리즈" OR "46-series" OR 4680 OR 4695 OR 46100 OR 46120) (수주 OR 공급 OR contract OR order OR 장비 OR equipment OR 양극재 OR cathode OR 고객 OR customer)',
    '(삼성SDI OR "Samsung SDI") ("46시리즈" OR "46-series" OR "46-phi") ("European global EV" OR "global EV" OR 유럽 글로벌 OR 프리미엄 전기차 OR premium EV OR 헝가리 OR Hungary) (수주 OR order OR customer OR 고객 OR 2028 OR 장비 OR equipment OR 양산 OR SOP OR GWh)',
    '(삼성SDI OR "Samsung SDI") (KGM OR "KG Mobility" OR KG모빌리티) ("46시리즈" OR "46-series") (MOU OR 공동개발 OR 공급계약 OR 양산 OR 적용 OR 탑재 OR SOP)',
    '(SK온 OR "SK On") ("46시리즈" OR "46-series" OR 4680 OR 4695 OR 46120) (개발완료 OR development complete OR prototype OR 시제품 OR Changzhou OR 창저우 OR 300000 OR 300,000 OR 고객 OR customer OR 수주 OR order OR 공급계약 OR 양산 OR SOP OR 장비 OR equipment)',
    '("46시리즈" OR "46-series" OR 4680 OR 4695 OR 46100 OR 46120) ("SNE Research" OR SNE리서치) (155GWh OR 650GWh OR 33% OR 2030 OR 전망 OR forecast OR revised OR 상향 OR 하향)',
    '(LG에너지솔루션 OR "LG Energy Solution") (원통형 OR cylindrical) ("46시리즈" OR "46-series") (1.5배 OR 1.5x OR shipment OR 출하 OR utilization OR 가동률 OR yield OR 수율 OR Q2 OR 2분기)',
])

base.TRUSTED.update({
    'Energy-Storage.News', 'ESS News', 'Benchmark Mineral Intelligence',
    'Reuters', 'Caixin', '전자신문', '이데일리', '연합뉴스', '한국경제',
    'Wood Mackenzie', 'Utility Dive', 'Canary Media',
    '한국경제TV', 'WOWTV', '뉴시스', 'Newsis', 'TrendForce', '集邦咨询',
    '中国基金报', '中国基金报社', '中国基金报·机会宝',
    '디일렉', 'TheElec', 'THE ELEC', 'SNE Research', 'SNE리서치',
    'Korea Herald', 'The Korea Herald', 'Korea JoongAng Daily',
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
    'CATL', '宁德时代', 'CATL Debrecen',
    '이수스페셜티케미컬', 'ISU Specialty Chemical', '이수그룹',
    'SK온', 'SK On', '엘앤에프', 'L&F', 'DART', '금융감독원 전자공시시스템',
    'LG에너지솔루션', 'LG Energy Solution', '삼성SDI', 'Samsung SDI',
    'BMW Group', 'BMW', 'Rivian', 'Tesla', 'Mercedes-Benz', 'Chery Automobile',
    'Chery', 'indiGOtech', '에코프로비엠', 'EcoPro BM',
    'KGM', 'KG Mobility', 'KG모빌리티', 'Samsung SDI Europe GmbH',
})

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_select_diverse = base.select_diverse
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

EV46_RE = re.compile(r'46\s*시리즈|46시리즈|46[-\s]*series|46[-\s]*phi|46phi|46\s*mm|46mm|\b4680\b|\b4695\b|\b46100\b|\b46120\b|46파이', re.I)
EV46_CELLMAKER = re.compile(r'LG에너지솔루션|LG\s*Energy\s*Solution|삼성SDI|Samsung\s*SDI|Tesla|테슬라|SK온|SK\s*On', re.I)
EV46_OEM = re.compile(r'Rivian|리비안|BMW|Mercedes[-\s]*Benz|Mercedes|벤츠|Chery|체리|Volvo|볼보|indiGOtech|인디고테크|Tesla|테슬라|KGM|KG\s*Mobility', re.I)
EV46_GWH = re.compile(r'\d[\d,.]*\s*GWh', re.I)
EV46_CONTRACT = re.compile(r'공급\s*계약|계약\s*체결|수주|본계약|supply\s*(?:agreement|contract)|contract|purchase\s*order|award|order', re.I)
EV46_MOU = re.compile(r'\bMOU\b|업무\s*협약|양해\s*각서|nonbinding|non[-\s]*binding|explore|협의', re.I)
EV46_FORMAT_CONFIRM = re.compile(r'(?:adopt|adopted|confirmed|confirm|selected|채택|확정|선정).{0,80}(?:4680|4695|46100|46120|46\s*mm|46mm|46시리즈|46[-\s]*series)|(?:4680|4695|46100|46120|46\s*mm|46mm|46시리즈|46[-\s]*series).{0,80}(?:adopt|adopted|confirmed|confirm|selected|채택|확정|선정)', re.I)
EV46_BACKLOG = re.compile(r'수주\s*잔고|수주잔고|order\s*backlog|backlog|신규\s*수주|new\s*orders?', re.I)
EV46_BASELINE_BACKLOG = re.compile(r'(?:440\s*GWh|100\s*GWh).{0,100}(?:수주|order|backlog)|(?:수주|order|backlog).{0,100}(?:440\s*GWh|100\s*GWh)', re.I)
EV46_RIVIAN_BASE = re.compile(r'(?:Rivian|리비안).{0,140}(?:4695).{0,140}(?:67\s*GWh|5\s*년|five\s*years?)|(?:67\s*GWh).{0,180}(?:Rivian|리비안)', re.I)
EV46_CHERY_BASE = re.compile(r'(?:Chery|체리).{0,140}(?:46[-\s]*series|46시리즈).{0,140}(?:8\s*GWh|6\s*년|six\s*years?)|(?:8\s*GWh).{0,180}(?:Chery|체리)', re.I)
EV46_BMW_BASE = re.compile(r'(?:BMW).{0,180}(?:46\s*mm|46mm).{0,180}(?:95\s*mm|120\s*mm)|(?:95\s*mm|120\s*mm).{0,180}(?:BMW).{0,180}(?:46\s*mm|46mm)', re.I)
EV46_TESLA_BASE = re.compile(r'(?:Tesla|테슬라).{0,180}(?:4680).{0,180}(?:40\s*GWh|production|양산)|(?:40\s*GWh).{0,180}(?:4680)', re.I)
EV46_SDI_BASE = re.compile(r'(?:Samsung\s*SDI|삼성SDI).{0,180}(?:4695).{0,180}(?:micro\s*mobility|마이크로\s*모빌리티|first\s*shipment|초도\s*공급|양산)|(?:4695).{0,180}(?:삼성SDI|Samsung\s*SDI)', re.I)
EV46_MERCEDES_BASE = re.compile(r'(?:Mercedes[-\s]*Benz|Mercedes|벤츠).{0,180}(?:46100).{0,180}(?:2028|Poland|폴란드|Wroclaw|브로츠와프)|(?:46100).{0,180}(?:Mercedes[-\s]*Benz|Mercedes|벤츠)', re.I)
EV46_INDIGO_BASE = re.compile(r'(?:indiGOtech|인디고테크).{0,180}(?:46[-\s]*series|46시리즈).{0,180}(?:2027|2030|MOU|협의|nonbinding)|(?:46[-\s]*series|46시리즈).{0,180}(?:indiGOtech|인디고테크)', re.I)
EV46_ARIZONA_PLAN = re.compile(r'(?:Queen\s*Creek|퀸크릭|Arizona|애리조나).{0,180}(?:4680|4695|46100|46120|46[-\s]*series|46시리즈).{0,160}(?:2026|year[-\s]*end|연말|\bplan(?:s|ned)?\b|예정|계획)', re.I)
EV46_POLAND_PLAN = re.compile(r'(?:Poland|폴란드|Wroclaw|브로츠와프|Ochang|오창).{0,180}(?:46100).{0,160}(?:line|라인|build|구축|convert|개조|2027|2028)', re.I)
EV46_EQUIPMENT = re.compile(r'장비\s*(?:발주|반입|설치)|설비\s*(?:발주|반입|설치)|equipment\s*(?:order|move[-\s]*in|install)|tooling\s*(?:order|install)|생산라인\s*(?:설치|구축)|line\s*(?:installation|build[-\s]*out)', re.I)
EV46_CONSTRUCTION = re.compile(r'착공|공사\s*(?:시작|개시)|groundbreak|construction\s*(?:start|began|underway)|인허가\s*(?:승인|완료)|permit\s*(?:approved|issued)', re.I)
EV46_SOP = re.compile(r'양산\s*(?:개시|시작|돌입)|상업\s*생산\s*(?:개시|시작)|mass\s*production\s*(?:started|began|commenced)|(?:started|starts|began|commenced)\s+(?:46[-\s]*series\s+)?mass\s*production|commercial\s*production\s*(?:started|began)|(?:started|began)\s+commercial\s*production|SOP\s*(?:started|began|개시|시작)', re.I)
EV46_SHIPMENT = re.compile(r'첫\s*출하|초도\s*출하|납품\s*(?:시작|개시)|first\s*shipment|shipments?\s*(?:started|began)|delivery\s*(?:started|began)', re.I)
EV46_RAMP = re.compile(r'(?:가동률|수율|실제\s*생산량|월\s*생산량|출하량|utilization|yield|actual\s*output|monthly\s*output).{0,80}\d[\d,.]*\s*(?:%|GWh|MWh|개|대)|\d[\d,.]*\s*(?:%|GWh|MWh).{0,80}(?:가동률|수율|실제\s*생산량|utilization|yield|output)', re.I)
EV46_BMA = re.compile(r'BMA|battery\s*module\s*assembly|배터리\s*모듈\s*어셈블리|모듈\s*조립|module\s*assembly', re.I)
EV46_BMA_EXEC = re.compile(r'(?:BMA|battery\s*module\s*assembly|배터리\s*모듈\s*어셈블리|모듈\s*조립).{0,120}(?:투자\s*확정|investment\s*(?:approved|confirmed)|장비\s*발주|equipment\s*order|설치|install|양산|production)|(?:투자\s*확정|장비\s*발주|equipment\s*order|install|양산).{0,120}(?:BMA|battery\s*module\s*assembly|배터리\s*모듈\s*어셈블리|모듈\s*조립)', re.I)
EV46_COMPONENT = re.compile(r'에코프로비엠|EcoPro\s*BM|케이엔에스|\bKNS\b|엠오티|\bMOT\b|원익피앤이|Wonik\s*PNE|양극재|cathode|리벳|rivet|용접|weld|검사\s*장비|inspection\s*equipment', re.I)
EV46_COMPONENT_ORDER = re.compile(r'수주|공급\s*계약|계약|order|contract|award|납품|shipment|장비\s*발주|equipment\s*order', re.I)
EV46_REVERSE = re.compile(r'(?:46[-\s]*series|46시리즈|4680|4695|46100|46120).{0,140}(?:cancel|terminate|delay|postpone|cut|reduce|중단|취소|해지|지연|연기|축소|감산)|(?:cancel|terminate|delay|postpone|중단|취소|해지|지연|연기|축소).{0,140}(?:46[-\s]*series|46시리즈|4680|4695|46100|46120)', re.I)
EV46_MARKET_BASE = re.compile(
    r'(?:155\s*GWh).{0,180}(?:650\s*GWh).{0,120}(?:2030|33\s*%)|'
    r'(?:650\s*GWh).{0,180}(?:155\s*GWh).{0,120}(?:2030|33\s*%)|'
    r'(?:33\s*%).{0,120}(?:155\s*GWh|650\s*GWh).{0,120}2030',
    re.I,
)
EV46_MARKET_FORECAST = re.compile(r'SNE\s*Research|SNE리서치', re.I)
EV46_FORECAST_CHANGE = re.compile(r'revis|raise|lower|upgrade|downgrade|상향|하향|수정|변경|새\s*전망|new\s*forecast', re.I)
EV46_LGES_CYL_15X_BASE = re.compile(
    r'(?:LG\s*Energy\s*Solution|LG에너지솔루션).{0,180}(?:cylindrical|원통형).{0,180}(?:46[-\s]*Series|46시리즈).{0,180}(?:1\.5\s*x|1\.5\s*times|1\.5배).{0,80}(?:year[-\s]*on[-\s]*year|YoY|전년\s*동기)|'
    r'(?:1\.5\s*x|1\.5\s*times|1\.5배).{0,180}(?:cylindrical|원통형).{0,180}(?:LG\s*Energy\s*Solution|LG에너지솔루션)',
    re.I,
)
EV46_SHIPMENT_METRIC = re.compile(
    r'(?:shipment|shipments|출하량|출하).{0,100}(?:\d+(?:\.\d+)?\s*(?:x|배|%|GWh)|전년\s*동기)|'
    r'(?:\d+(?:\.\d+)?\s*(?:x|배|%|GWh)).{0,100}(?:shipment|shipments|출하량|출하)',
    re.I,
)
EV46_SDI_EU_ORDER_BASE = re.compile(
    r'(?:Samsung\s*SDI|삼성SDI).{0,180}(?:European\s+global\s+EV|유럽\s*글로벌\s*(?:전기차|EV)|premium\s+EV|프리미엄\s*전기차).{0,180}'
    r'(?:46[-\s]*phi|46[-\s]*series|46시리즈).{0,220}(?:2028).{0,120}(?:Hungary|헝가리)|'
    r'(?:Samsung\s*SDI|삼성SDI).{0,180}(?:46[-\s]*phi|46[-\s]*series|46시리즈).{0,180}(?:2028).{0,120}(?:Hungary|헝가리).{0,120}(?:order|수주)',
    re.I,
)
EV46_SDI_EU_ORDER_CTX = re.compile(
    r'(?:Samsung\s*SDI|삼성SDI).{0,180}(?:46[-\s]*phi|46[-\s]*series|46시리즈).{0,180}(?:2028|Hungary|헝가리)',
    re.I,
)
EV46_EXACT_FORMAT = re.compile(r'\b4680\b|\b4695\b|\b46100\b|\b46120\b', re.I)
EV46_SDI_ORDER_DETAIL = re.compile(
    r'customer\s*(?:is|named|identified)|고객사\s*(?:실명|공개|확인)|공급\s*물량\s*\d|'
    r'contract\s*(?:volume|size)|계약\s*물량|\d[\d,.]*\s*GWh',
    re.I,
)
EV46_SDI_KGM_BASE = re.compile(
    r'(?:Samsung\s*SDI|삼성SDI).{0,160}(?:KGM|KG\s*Mobility|KG모빌리티).{0,180}(?:46[-\s]*series|46시리즈).{0,160}(?:MOU|공동\s*개발|joint\s*develop)|'
    r'(?:KGM|KG\s*Mobility|KG모빌리티).{0,160}(?:Samsung\s*SDI|삼성SDI).{0,180}(?:46[-\s]*series|46시리즈).{0,160}(?:MOU|공동\s*개발|joint\s*develop)',
    re.I,
)
EV46_SKON_DEV_BASE = re.compile(
    r'(?:SK\s*On|SK온).{0,180}(?:46[-\s]*series|46시리즈).{0,160}(?:development\s*(?:is\s*)?complete|completed\s+development|개발\s*완료)|'
    r'(?:SK\s*On|SK온).{0,180}(?:Changzhou|창저우).{0,180}(?:prototype|시제품).{0,120}(?:300,?000|30만)',
    re.I,
)
EV46_SKON_QUALIFICATION = re.compile(r'customer\s*(?:qualification|validation|approval)|고객\s*(?:검증|인증|승인)|sample\s*(?:approved|qualification)|샘플\s*(?:승인|검증)', re.I)
EV46_ANON_OEM = re.compile(r'European\s+global\s+(?:EV|automaker)|global\s+(?:EV|automaker|OEM)|유럽\s*글로벌\s*(?:완성차|전기차)|글로벌\s*(?:완성차|OEM)|U\.S\.\s*start[-\s]*up|미국\s*스타트업', re.I)
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

CATL_DEB_ID = re.compile(r'(?:CATL|宁德时代).{0,120}(?:Debrecen|德布勒森|데브레첸|Hungary|헝가리)|(?:Debrecen|德布勒森|데브레첸|Hungary|헝가리).{0,120}(?:CATL|宁德时代)', re.I)
CATL_DEB_TRIAL = re.compile(r'trial\s*(?:production|operation|run)|test\s*production|试生产|试运行|시험\s*생산|시운전|생산\s*검증', re.I)
CATL_DEB_KNOWN_REWRITE = re.compile(
    r'100\s*GWh.{0,180}(?:73\.4\s*亿欧元|7\.34\s*billion\s*euros?|73\.4\s*억\s*유로|73억|221\s*(?:hectare|ha|公顷|헥타르))|'
    r'(?:73\.4\s*亿欧元|7\.34\s*billion\s*euros?|73\.4\s*억\s*유로|73억|221\s*(?:hectare|ha|公顷|헥타르)).{0,180}100\s*GWh',
    re.I,
)
CATL_DEB_SERIES = re.compile(
    r'series\s*production\s*(?:starts?|started|begins?|began|commences?|commenced)|'
    r'(?:starts?|started|begins?|began|commences?|commenced)\s+(?:officially\s+)?series\s*production|'
    r'mass\s*production\s*(?:starts?|started|begins?|began|commences?|commenced)|'
    r'(?:starts?|started|begins?|began|commences?|commenced)\s+(?:officially\s+)?mass\s*production|'
    r'commercial\s*production\s*(?:starts?|started|begins?|began|commences?|commenced)|'
    r'(?:starts?|started|begins?|began|commences?|commenced)\s+(?:officially\s+)?commercial\s*production|'
    r'正式量产|量产(?:正式)?(?:开始|启动)|'
    r'양산\s*(?:개시|시작|돌입)|상업\s*생산\s*(?:개시|시작)',
    re.I,
)
CATL_DEB_SHIPMENT = re.compile(
    r'(?:cell|battery\s*cell|电芯|배터리셀).{0,100}(?:first\s*shipment|shipment\s*(?:started|began)|delivered|delivery\s*(?:started|began)|首批交付|开始交付|첫\s*출하|출하\s*(?:시작|개시)|납품\s*(?:시작|개시))',
    re.I,
)
CATL_DEB_RAMP = re.compile(
    r'(?:utilization|run[-\s]*rate|yield|output|产能利用率|良率|实际产量|가동률|수율|실제\s*생산량).{0,80}\d[\d,.]*\s*(?:%|GWh|MWh)|'
    r'\d[\d,.]*\s*(?:%|GWh|MWh).{0,80}(?:utilization|run[-\s]*rate|yield|output|产能利用率|良率|实际产量|가동률|수율|실제\s*생산량)',
    re.I,
)
CATL_DEB_EXPANSION = re.compile(
    r'(?:phase\s*(?:2|II|3|III)|二期|三期|2단계|3단계).{0,100}(?:construction|start|capacity|GWh|착공|증설|생산능력)|'
    r'(?:expansion|capacity\s*increase|扩产|증설).{0,100}\d[\d,.]*\s*GWh',
    re.I,
)
CATL_DEB_STOP = re.compile(
    r'(?:production|operation|cell\s*plant|电芯|공장|생산).{0,100}(?:shutdown|halt|suspend|stop|permit\s*(?:revoked|suspended)|停产|暂停|停工|中止|가동\s*중단|생산\s*중단|허가\s*(?:취소|정지)|안전\s*사고|nickel\s*exposure|니켈\s*노출)|'
    r'(?:shutdown|halt|suspend|停产|暂停|가동\s*중단|생산\s*중단|허가\s*(?:취소|정지)).{0,100}(?:Debrecen|德布勒森|데브레첸)',
    re.I,
)

ISU_LI2S_ID = re.compile(r'(?:이수스페셜티케미컬|ISU\s*Specialty\s*Chemical).{0,120}(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide)|(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide).{0,120}(?:이수스페셜티케미컬|ISU\s*Specialty\s*Chemical)', re.I)
ISU_LI2S_BASELINE = re.compile(
    r'(?:10월|October).{0,140}(?:상업\s*생산|commercial\s*production|공장\s*가동|plant\s*operation|생산\s*돌입)|'
    r'(?:상업\s*생산|commercial\s*production).{0,100}(?:다음\s*달|next\s*month|10월|넷째\s*주|fourth\s*week)|'
    r'(?:준공|completed).{0,100}(?:150\s*(?:톤|t|ton)).{0,100}(?:시운전|quality\s*stabilization|품질\s*안정화)|'
    r'(?:150\s*(?:톤|t|ton)).{0,120}(?:500\s*(?:톤|t|ton)).{0,120}(?:마더\s*플랜트|mother\s*plant|상업화\s*공장)',
    re.I,
)
ISU_LI2S_COMMERCIAL = re.compile(
    r'(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide).{0,140}(?:상업\s*생산|commercial\s*production|양산).{0,50}(?:개시했다|시작했다|돌입했다|가동에\s*들어갔다|started|began|commenced)|'
    r'(?:상업\s*생산|commercial\s*production|양산).{0,50}(?:개시했다|시작했다|돌입했다|가동에\s*들어갔다|started|began|commenced).{0,140}(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide)|'
    r'(?:공장|plant).{0,80}(?:가동을\s*시작했다|가동에\s*들어갔다|started\s*operations).{0,100}(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide)',
    re.I,
)
ISU_LI2S_SHIPMENT = re.compile(
    r'(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide).{0,140}(?:첫\s*납품을?\s*(?:시작했다|완료했다)|초도\s*납품을?\s*(?:시작했다|완료했다)|'
    r'납품을?\s*(?:개시했다|시작했다)|공급을?\s*(?:개시했다|시작했다)|first\s*shipment\s*(?:completed|delivered)|deliveries?\s*(?:started|began)|shipment\s*(?:started|began))|'
    r'(?:첫\s*납품을?\s*(?:시작했다|완료했다)|초도\s*납품을?\s*(?:시작했다|완료했다)|납품을?\s*(?:개시했다|시작했다)|공급을?\s*(?:개시했다|시작했다)|'
    r'first\s*shipment\s*(?:completed|delivered)|deliveries?\s*(?:started|began)|shipment\s*(?:started|began)).{0,140}(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide)',
    re.I,
)
ISU_LI2S_CONTRACT = re.compile(
    r'(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide).{0,140}(?:공급\s*계약|본계약|장기\s*계약|수주|customer\s*(?:selected|named)|supply\s*contract|purchase\s*order)|'
    r'(?:공급\s*계약|본계약|장기\s*계약|수주|supply\s*contract|purchase\s*order).{0,140}(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide)',
    re.I,
)
ISU_LI2S_CAPACITY = re.compile(
    r'(?:증설\s*투자\s*결정|증설\s*(?:착공|시작|개시)|설비\s*(?:발주|반입)|라인\s*증설\s*(?:시작|개시)|'
    r'capacity\s*expansion\s*(?:approved|started|began)|construction\s*start|investment\s*approved|equipment\s*order).{0,120}(?:500\s*(?:톤|t|ton)|\d[\d,.]*\s*(?:톤|t|ton))|'
    r'(?:500\s*(?:톤|t|ton)|\d[\d,.]*\s*(?:톤|t|ton)).{0,120}(?:증설\s*투자\s*결정|증설\s*(?:착공|시작|개시)|설비\s*(?:발주|반입)|'
    r'라인\s*증설\s*(?:시작|개시)|capacity\s*expansion\s*(?:approved|started|began)|construction\s*start|investment\s*approved|equipment\s*order)',
    re.I,
)
ISU_LI2S_RAMP = re.compile(
    r'(?:가동률|수율|실제\s*생산량|출하량|판매량|utilization|yield|actual\s*output|shipments?|sales\s*volume).{0,80}\d[\d,.]*\s*(?:%|톤|t|ton)|'
    r'\d[\d,.]*\s*(?:톤|t|ton).{0,80}(?:가동률|수율|실제\s*생산량|출하량|판매량|utilization|yield|actual\s*output|shipments?|sales\s*volume)',
    re.I,
)
ISU_LI2S_DELAY = re.compile(
    r'(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide).{0,120}(?:지연|연기|중단|delay|postpon|suspend|halt|shutdown|가동\s*중단|생산\s*중단)|'
    r'(?:지연|연기|중단|delay|postpon|suspend|halt|shutdown).{0,120}(?:황화리튬|Li2S|Li₂S|lithium\s*sulfide)',
    re.I,
)
ISU_LI2S_SAFETY = re.compile(
    r'(?:황화수소|H2S|hydrogen\s*sulfide).{0,120}(?:누출|leak|폭발|explosion|화재|fire|사고|incident|방폭|permit|인허가|shutdown|중단)|'
    r'(?:누출|leak|폭발|explosion|화재|fire|사고|incident|shutdown|중단).{0,120}(?:황화수소|H2S|hydrogen\s*sulfide)',
    re.I,
)


EV46_NEW_EVENT = re.compile(r'new\s+(?:order|contract|customer|award|capacity)|additional|expanded|increase|revised|renewed|second\s+contract|신규\s*(?:수주|계약|고객)|추가\s*(?:수주|계약|물량)|후속\s*(?:수주|계약|발주)|증액|확대|상향|재계약', re.I)
EV46_PLAN_ONLY = re.compile(r'계획|예정|검토|협의|전망|목표|추진|plan(?:s|ned)?|expected|target|consider|explore|reportedly|전해졌|파악됐', re.I)


def _ev46_known_baseline(text: str, source: str = '') -> bool:
    official = source in base.OFFICIAL_OR_PRIMARY
    if EV46_MARKET_BASE.search(text):
        return True
    if EV46_LGES_CYL_15X_BASE.search(text):
        return True
    if (
        SDI_RE.search(text)
        and EV46_RE.search(text)
        and EV46_ANON_OEM.search(text)
        and re.search(r'2028', text, re.I)
        and re.search(r'Hungary|헝가리', text, re.I)
        and EV46_CONTRACT.search(text)
        and not EV46_GWH.search(text)
        and not EV46_EXACT_FORMAT.search(text)
        and not EV46_OEM.search(text)
    ):
        return True
    if EV46_SDI_KGM_BASE.search(text):
        return True
    if EV46_SKON_DEV_BASE.search(text):
        return True
    # User already surfaced the Mercedes 46100 / Poland 2027-line / 2028-supply
    # report. Keep the media report silent, but allow a later official Mercedes
    # or LGES confirmation to advance the state.
    if (
        EV46_MERCEDES_BASE.search(text)
        and not official
        and not EV46_BMA_EXEC.search(text)
        and not EV46_FORMAT_CONFIRM.search(text)
        and not EV46_CONTRACT.search(text)
        and not EV46_SOP.search(text)
        and not EV46_SHIPMENT.search(text)
        and not EV46_RAMP.search(text)
    ):
        return True
    if EV46_INDIGO_BASE.search(text) and EV46_MOU.search(text):
        return True
    if EV46_RIVIAN_BASE.search(text) and not EV46_NEW_EVENT.search(text):
        return True
    if EV46_CHERY_BASE.search(text) and not EV46_NEW_EVENT.search(text):
        return True
    if EV46_BMW_BASE.search(text) and not EV46_NEW_EVENT.search(text):
        return True
    if EV46_TESLA_BASE.search(text) and not EV46_NEW_EVENT.search(text):
        return True
    if EV46_SDI_BASE.search(text) and not EV46_NEW_EVENT.search(text):
        return True
    if EV46_ARIZONA_PLAN.search(text) and not (EV46_SOP.search(text) or EV46_SHIPMENT.search(text) or EV46_RAMP.search(text)):
        return True
    if EV46_POLAND_PLAN.search(text) and not (EV46_EQUIPMENT.search(text) or EV46_CONSTRUCTION.search(text) or EV46_SOP.search(text)):
        return True
    if EV46_BASELINE_BACKLOG.search(text):
        gwh = {m.replace(' ', '').lower() for m in re.findall(r'\d[\d,.]*\s*GWh', text, re.I)}
        known = {'100gwh', '440gwh'}
        if gwh and gwh.issubset(known):
            return True
    return False


def _ev46_stage(text: str, source: str = '') -> str:
    if not EV46_RE.search(text):
        return ''
    # Require a named cell maker/OEM/component supplier, otherwise generic
    # 46-series market-growth explainers remain discovery-only.
    actor = bool(
        EV46_CELLMAKER.search(text)
        or EV46_OEM.search(text)
        or EV46_COMPONENT.search(text)
        or EV46_MARKET_FORECAST.search(text)
    )
    if not actor:
        return ''

    if EV46_REVERSE.search(text):
        return 'reverse'

    if _ev46_known_baseline(text, source):
        return 'known_baseline'

    if EV46_MARKET_FORECAST.search(text) and EV46_FORECAST_CHANGE.search(text) and re.search(r'\d[\d,.]*\s*(?:GWh|%|CAGR)', text, re.I):
        return 'market_forecast_revision'

    if EV46_SDI_EU_ORDER_CTX.search(text) and (
        EV46_SDI_ORDER_DETAIL.search(text)
        or EV46_EXACT_FORMAT.search(text)
        or EV46_OEM.search(text)
    ):
        return 'sdi_order_detail'

    if re.search(r'SK\s*On|SK온', text, re.I) and EV46_SKON_QUALIFICATION.search(text):
        return 'skon_customer_qualification'

    if re.search(r'SK\s*On|SK온', text, re.I) and EV46_CONTRACT.search(text) and (
        EV46_OEM.search(text) or EV46_ANON_OEM.search(text) or EV46_GWH.search(text)
    ):
        return 'skon_order'

    if EV46_SHIPMENT_METRIC.search(text) and re.search(r'LG\s*Energy\s*Solution|LG에너지솔루션', text, re.I):
        return 'shipment_metric'

    if EV46_ANON_OEM.search(text) and EV46_CONTRACT.search(text) and EV46_CELLMAKER.search(text):
        return 'anonymous_oem_order'

    if EV46_COMPONENT.search(text) and EV46_COMPONENT_ORDER.search(text):
        return 'component_order'

    if EV46_BMA_EXEC.search(text):
        return 'bma_integration'

    if EV46_SHIPMENT.search(text):
        return 'first_shipment'

    if EV46_SOP.search(text):
        return 'sop'

    if EV46_RAMP.search(text):
        return 'ramp_metrics'

    if EV46_EQUIPMENT.search(text):
        return 'equipment_execution'

    if EV46_CONSTRUCTION.search(text):
        return 'construction_execution'

    if EV46_BACKLOG.search(text) and EV46_GWH.search(text):
        return 'backlog_change'

    # A non-binding MOU is not a firm order. The current indiGOtech MOU is
    # baseline; future MOUs remain low-priority discovery unless converted to a
    # binding agreement.
    if EV46_MOU.search(text) and not EV46_CONTRACT.search(text):
        return 'mou'

    if EV46_CONTRACT.search(text) and (EV46_OEM.search(text) and EV46_CELLMAKER.search(text)):
        return 'oem_contract'

    if EV46_FORMAT_CONFIRM.search(text) and EV46_OEM.search(text):
        return 'format_confirmation'

    return 'background'


def _ev46_customer_tags(text: str) -> list[str]:
    out = []
    for name, pat in [
        ('tesla', r'Tesla|테슬라'),
        ('rivian', r'Rivian|리비안'),
        ('bmw', r'\bBMW\b'),
        ('mercedes', r'Mercedes[-\s]*Benz|Mercedes|벤츠'),
        ('chery', r'Chery|체리'),
        ('volvo', r'Volvo|볼보'),
        ('indigotech', r'indiGOtech|인디고테크'),
        ('kgm', r'KGM|KG\s*Mobility'),
    ]:
        if re.search(pat, text, re.I):
            out.append(name)
    return out


def _ev46_cellmaker_tags(text: str) -> list[str]:
    out = []
    for name, pat in [
        ('lges', r'LG에너지솔루션|LG\s*Energy\s*Solution'),
        ('sdi', r'삼성SDI|Samsung\s*SDI'),
        ('tesla', r'Tesla|테슬라'),
        ('skon', r'SK온|SK\s*On'),
    ]:
        if re.search(pat, text, re.I):
            out.append(name)
    return out


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
    if US_INSTALL_ACTUAL.search(text) and US_PERIOD.search(text) and US_GWH.search(text):
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


def _catl_debrecen_stage(text: str, source: str = '') -> str:
    if not CATL_DEB_ID.search(text):
        return ''
    if CATL_DEB_STOP.search(text):
        return 'regulatory_or_operational_stop'
    if CATL_DEB_SHIPMENT.search(text):
        return 'first_commercial_shipment'
    if CATL_DEB_SERIES.search(text):
        return 'series_production_start'
    if CATL_DEB_EXPANSION.search(text):
        return 'capacity_expansion'
    if CATL_DEB_RAMP.search(text):
        return 'ramp_metrics'
    if CATL_DEB_TRIAL.search(text):
        return 'trial_production_baseline'
    if CATL_DEB_KNOWN_REWRITE.search(text):
        return 'trial_production_baseline'
    return 'background'


def _isu_li2s_stage(text: str, source: str = '') -> str:
    if not ISU_LI2S_ID.search(text):
        return ''
    if ISU_LI2S_SAFETY.search(text):
        return 'safety_or_permit_risk'
    if ISU_LI2S_DELAY.search(text):
        return 'schedule_delay'
    if ISU_LI2S_SHIPMENT.search(text):
        return 'first_customer_shipment'
    if ISU_LI2S_CONTRACT.search(text) and not re.search(r'\bMOU\b|업무협약|협약', text, re.I):
        return 'customer_contract'
    if ISU_LI2S_COMMERCIAL.search(text) and not re.search(r'예정|계획|목표|expected|planned|next\s*month|다음\s*달', text, re.I):
        return 'commercial_production_start'
    if ISU_LI2S_CAPACITY.search(text):
        return 'capacity_expansion'
    if ISU_LI2S_RAMP.search(text) and not re.search(r'추정|전망|예상|안팎|estimate|estimated|forecast|expected|around|approximately', text, re.I):
        return 'ramp_metrics'
    if ISU_LI2S_BASELINE.search(text):
        return 'commercial_production_plan_baseline'
    if re.search(r'150\s*(?:톤|t|ton)', text, re.I) and re.search(r'준공|completed|마더\s*플랜트|mother\s*plant', text, re.I):
        return 'commercial_production_plan_baseline'
    return 'background'


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
    ev46_stage = _ev46_stage(text)
    if ev46_stage and ev46_stage != 'background':
        return 'ev_46_series'
    if _catl_debrecen_stage(text):
        return 'global_battery_capacity'
    if _isu_li2s_stage(text):
        return 'solid_state_material'
    if _is_ess_battery(text):
        return 'ess_battery'
    return _orig_topic_group(text)


def score(item: dict) -> int:
    title = item.get('title', '')
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    source = item.get('source') or ''

    if group == 'ev_46_series':
        stage = _ev46_stage(text, source)
        if stage in {'known_baseline','background','mou'}:
            return 0
        s = 20
        s += {
            'oem_contract': 17,
            'anonymous_oem_order': 16,
            'sdi_order_detail': 16,
            'skon_customer_qualification': 12,
            'skon_order': 17,
            'format_confirmation': 13,
            'backlog_change': 12,
            'shipment_metric': 12,
            'market_forecast_revision': 10,
            'construction_execution': 12,
            'equipment_execution': 14,
            'sop': 17,
            'first_shipment': 17,
            'ramp_metrics': 13,
            'bma_integration': 14,
            'component_order': 15,
            'reverse': 17,
        }.get(stage, 0)
        if base.NUMERIC.search(text): s += 3
        if source in base.OFFICIAL_OR_PRIMARY: s += 7
        elif source in base.TRUSTED: s += 3
        return s

    if group == 'global_battery_capacity':
        stage = _catl_debrecen_stage(text, source)
        if stage in {'trial_production_baseline', 'background'}:
            return 0
        s = 20
        s += {
            'series_production_start': 16,
            'first_commercial_shipment': 16,
            'ramp_metrics': 12,
            'capacity_expansion': 12,
            'regulatory_or_operational_stop': 15,
        }.get(stage, 0)
        if base.NUMERIC.search(text): s += 3
        if source in base.OFFICIAL_OR_PRIMARY: s += 7
        elif source in base.TRUSTED: s += 3
        return s

    if group == 'solid_state_material':
        stage = _isu_li2s_stage(text, source)
        if stage in {'commercial_production_plan_baseline', 'background'}:
            return 0
        s = 20
        s += {
            'commercial_production_start': 16,
            'first_customer_shipment': 16,
            'customer_contract': 17,
            'ramp_metrics': 12,
            'capacity_expansion': 13,
            'schedule_delay': 14,
            'safety_or_permit_risk': 16,
        }.get(stage, 0)
        if base.NUMERIC.search(text): s += 3
        if source in base.OFFICIAL_OR_PRIMARY: s += 7
        elif source in base.TRUSTED: s += 3
        return s

    if group != 'ess_battery':
        return _orig_score(item)

    us_stage = _us_ess_stage(text, source)
    sdi_stage = _sdi_ess_stage(text, source)
    if sdi_stage in {'earnings_forecast', 'earnings_unconfirmed', 'synergy_baseline'}:
        return 0
    if us_stage in {'us_install_baseline', 'us_target_baseline'}:
        return 0
    if us_stage and source not in base.OFFICIAL_OR_PRIMARY and source not in base.TRUSTED:
        if not re.search(r'SEIA|Solar\s+Energy\s+Industries\s+Association|Benchmark\s+Mineral|U\.S\.\s+Energy\s+Storage\s+Coalition|Energy\s+Storage\s+Coalition', text, re.I):
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
    if group == 'ev_46_series':
        stage = _ev46_stage(text)
        raw = {
            'known_baseline': '현재 계약·양산 기준선',
            'mou': '비구속 협의·MOU',
            'oem_contract': '완성차 공급계약·GWh 수주',
            'anonymous_oem_order': '익명 완성차 46파이 본수주',
            'sdi_order_detail': '삼성SDI 유럽 46파이 고객·물량·규격 공개',
            'skon_customer_qualification': 'SK온 46파이 고객 검증·승인',
            'skon_order': 'SK온 46파이 본수주',
            'format_confirmation': '완성차 46파이 규격 공식 채택',
            'backlog_change': '46시리즈 수주잔고·신규수주 변화',
            'shipment_metric': '원통형·46시리즈 출하량 변화',
            'market_forecast_revision': '46시리즈 시장전망 수정',
            'construction_execution': '46시리즈 공장·라인 착공',
            'equipment_execution': '46시리즈 장비발주·반입·라인 구축',
            'sop': '46시리즈 실제 양산 개시',
            'first_shipment': '46시리즈 첫 고객 출하',
            'ramp_metrics': '46시리즈 가동률·수율·실생산',
            'bma_integration': '46시리즈 모듈조립 내재화·투자',
            'component_order': '46시리즈 소재·장비 직접 수주',
            'reverse': '46시리즈 계약·양산 일정 후퇴',
        }.get(stage, '46시리즈 시장 배경')
        return f"46파이 EV 배터리 · {raw}"
    if group == 'global_battery_capacity':
        stage = _catl_debrecen_stage(text)
        raw = {
            'series_production_start': 'CATL Debrecen 셀 양산 개시',
            'first_commercial_shipment': 'CATL Debrecen 첫 상업 출하',
            'ramp_metrics': 'CATL Debrecen 가동률·수율·실생산',
            'capacity_expansion': 'CATL Debrecen 후속 증설',
            'regulatory_or_operational_stop': 'CATL Debrecen 규제·가동중단',
        }.get(stage, 'CATL Debrecen 시험생산 기준선')
        return f"글로벌 배터리 생산능력 · {raw}"
    if group == 'solid_state_material':
        stage = _isu_li2s_stage(text)
        raw = {
            'commercial_production_start': '이수스페셜티 황화리튬 상업생산 개시',
            'first_customer_shipment': '이수스페셜티 황화리튬 첫 고객 납품',
            'customer_contract': '이수스페셜티 황화리튬 공급계약',
            'ramp_metrics': '이수스페셜티 황화리튬 가동률·출하',
            'capacity_expansion': '이수스페셜티 황화리튬 증설',
            'schedule_delay': '이수스페셜티 황화리튬 일정 지연',
            'safety_or_permit_risk': '이수스페셜티 황화리튬 안전·인허가 리스크',
        }.get(stage, '이수스페셜티 황화리튬 상업생산 계획 기준선')
        return f"전고체 소재 · {raw}"
    if group == 'ess_battery':
        return f"ESS 배터리 · {_raw_cat(text)}"
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if cat.startswith('46파이 EV 배터리 · '):
        return {
            '현재 계약·양산 기준선': 'LG에너지솔루션 46시리즈 수주잔고 440GWh+, Rivian 4695 67GWh/5년, Chery 8GWh/6년, BMW 46mm 95·120mm, Tesla 4680 40GWh 생산, 삼성SDI 4695 초도양산, Mercedes-Benz 46100 보도, indiGOtech 비구속 MOU를 현재 기준선으로 고정합니다. 같은 내용 재보도는 침묵합니다.',
            '비구속 협의·MOU': '업무협약·공급협의는 확정 수주가 아닙니다. 최종 본계약, GWh, 공급기간, SOP와 실제 출하가 확인될 때 상업 매출 단계로 승격합니다.',
            '완성차 공급계약·GWh 수주': '46파이 시장이 기술 기대에서 실제 주문으로 넘어가는 가장 직접적인 수요 신호입니다. 완성차 실명, 정확한 46xx 규격, GWh, 기간, 공급공장과 매출 인식 시점을 연결합니다.',
            '완성차 46파이 규격 공식 채택': 'Volvo처럼 아직 공개 확정이 약한 고객이 4680·4695·46100·46120 중 실제 규격을 공식 채택하거나 기존 고객이 정확한 규격을 확정하는 단계입니다. 공급사 선정과 별개로 차량 설계가 고정되는 선행 신호입니다.',
            '46시리즈 수주잔고·신규수주 변화': 'LG에너지솔루션의 440GWh+ 기준선처럼 수주잔고가 실제로 늘거나 줄어드는 신호입니다. 신규 GWh에서 기존 계약 취소·중복 물량을 분리하고 공급연도별 매출 전환 속도를 추적합니다.',
            '46시리즈 공장·라인 착공': '계획 생산능력이 실제 건설·인허가 단계로 넘어가는 신호입니다. 투자액, 라인 수, 규격, 생산능력과 SOP까지 남은 공정 시차를 확인합니다.',
            '46시리즈 장비발주·반입·라인 구축': '셀 매출보다 먼저 움직이는 설비투자 단계입니다. 전극·조립·탭리스 용접·리벳·검사·충방전·에이징 장비의 공급사, 발주액과 장비반입 시점을 확인합니다.',
            '46시리즈 실제 양산 개시': '계획·시험생산에서 반복 가능한 상업생산으로 넘어가는 핵심 단계입니다. 명목 GWh보다 초기 수율·실제 월 생산량·고객 승인과 첫 출하를 우선 확인합니다.',
            '46시리즈 첫 고객 출하': '양산설비가 실제 완성차 고객 매출로 전환되는 첫 현금창출 신호입니다. 출하 GWh, 셀 평균판매단가, 고객 차량 SOP와 반복 출하를 확인합니다.',
            '46시리즈 가동률·수율·실생산': '신규 공장의 총자산이익률을 가르는 단계입니다. 명목 생산능력과 실제 가동률·수율·생산 GWh를 분리해 감가상각·고정비 흡수 여부를 확인합니다.',
            '46시리즈 모듈조립 내재화·투자': '셀 업체가 BMA·모듈 조립까지 가져가면 셀 외 추가 가치와 반복매출을 확보할 수 있지만 기존 외주 조립사에는 물량 이탈 신호입니다. 투자액·장비·모듈 단가와 고객 범위를 분리합니다.',
            '46시리즈 소재·장비 직접 수주': '46파이 증설이 에코프로비엠·조립/리벳/용접/검사 장비사 등의 실제 수주로 내려오는 선행 실적 신호입니다. 고객 실명·계약액·납기·46파이 전용 비중을 확인합니다.',
            '46시리즈 계약·양산 일정 후퇴': '계약 취소·고객 일정 연기·생산능력 축소는 수주잔고와 선행 설비투자의 회수기간을 악화시키는 역방향 신호입니다. 취소 GWh·감산폭·새 SOP와 공급망 발주 취소를 함께 확인합니다.',
        }.get(raw, '46파이 EV 배터리의 계약→설비→양산→출하 경로를 추적합니다.')
    if raw == 'CATL Debrecen 셀 양산 개시':
        return '9월 22일 첫 2개 라인의 시험생산과 구분해 실제 series/mass production이 시작되는 단계입니다. 100GWh는 완공 후 계획 생산능력이므로 현재 실가동 GWh·수율·고객 출하를 따로 확인합니다.'
    if raw == 'CATL Debrecen 첫 상업 출하':
        return '시험생산·양산 개시가 실제 유럽 완성차 고객 매출로 전환되는 단계입니다. 고객 실명·셀 물량·납기·매출 인식과 반복 출하를 확인합니다.'
    if raw == 'CATL Debrecen 가동률·수율·실생산':
        return '명목 100GWh가 아니라 실제 가동률·수율·GWh 생산량으로 유럽 현지 생산기지의 실효 생산능력을 확인하는 신호입니다.'
    if raw == 'CATL Debrecen 후속 증설':
        return 'Debrecen의 후속 단계·라인 증설이 실제 착공·장비반입·생산능력 증가로 이어지는 신호입니다. 100GWh 최종계획과 현재 가동 캐파를 분리합니다.'
    if raw == 'CATL Debrecen 규제·가동중단':
        return '환경·산업안전·허가 문제가 생산 일정과 유럽 고객 공급에 직접 영향을 주는 역방향 신호입니다. 중단 범위·기간·재가동 조건을 확인합니다.'
    if raw == '이수스페셜티 황화리튬 상업생산 개시':
        return '6월 준공·시운전과 10월 넷째 주 상업생산 계획을 넘어 황화리튬이 실제 상업생산으로 전환되는 단계입니다. 초기 150톤 생산능력보다 양품 생산량·수율·고객 납품을 우선 확인합니다.'
    if raw == '이수스페셜티 황화리튬 첫 고객 납품':
        return '샘플 테스트가 실제 유상 납품과 매출 인식으로 넘어가는 첫 상업화 신호입니다. 고객 실명·톤수·단가·반복 주문을 확인합니다.'
    if raw == '이수스페셜티 황화리튬 공급계약':
        return '10여개 고객 샘플 테스트 중 일부가 실제 공급계약으로 전환되는 단계입니다. 계약 물량·기간·단가·전고체 셀 고객의 양산 일정까지 연결해 봅니다.'
    if raw == '이수스페셜티 황화리튬 가동률·출하':
        return '연 150톤 명목 생산능력이 실제 판매량·가동률·수율로 매출화되는지 보는 신호입니다. 올해 20톤 안팎 판매 추정과 실제 출하를 구분합니다.'
    if raw == '이수스페셜티 황화리튬 증설':
        return '초기 150톤에서 최대 500톤 설계능력으로 넘어가는 실제 증설 결정·착공 신호입니다. 고객계약보다 설비가 앞서면 감가상각·가동률 부담이 커질 수 있습니다.'
    if raw == '이수스페셜티 황화리튬 일정 지연':
        return '10월 상업생산 또는 고객검증 일정이 뒤로 밀리는 역방향 신호입니다. 공정 수율·품질 안정화·고객 승인·설비 문제 중 원인을 분리합니다.'
    if raw == '이수스페셜티 황화리튬 안전·인허가 리스크':
        return '황화수소 취급·방폭·안전·인허가 문제가 상업생산과 출하를 지연시킬 수 있는 공정 리스크입니다. 사고·허가정지·중단 기간과 재가동 조건을 추적합니다.'
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
    if cat.startswith('46파이 EV 배터리 · '):
        return {
            '현재 계약·양산 기준선': '46파이 시장 확대가 모든 셀 업체의 즉시 이익 증가를 뜻하지 않습니다. 신규 라인의 초기 수율·감가상각·고객 SOP 시차 때문에 수주잔고가 큰데도 영업현금흐름과 총자산이익률이 늦게 개선될 수 있습니다.',
            '비구속 협의·MOU': 'MOU는 수량·단가·구매의무가 없는 경우가 많습니다. 최종계약이 늦거나 취소되면 매출이 0일 수 있으므로 확정 수주로 계산하지 않습니다.',
            '완성차 공급계약·GWh 수주': 'GWh 계약도 고객 차량 출시 지연·최소구매 조건·가격조정 조항으로 실제 연도별 출하가 달라질 수 있습니다. 계약 총량을 한 해 매출로 환산하지 않습니다.',
            '완성차 46파이 규격 공식 채택': '규격 채택은 특정 셀 업체 공급 확정을 뜻하지 않습니다. 멀티벤더·현지조달·가격경쟁으로 공급사 점유율이 나뉠 수 있습니다.',
            '46시리즈 수주잔고·신규수주 변화': '수주잔고는 매출이 아니며 취소·연기·가격 재협상 위험이 있습니다. 공급연도별 출하와 고객별 SOP가 따라오는지 확인합니다.',
            '46시리즈 공장·라인 착공': '수요보다 설비가 먼저 늘면 저가동률·감가상각으로 총자산이익률이 악화될 수 있습니다. 착공 뒤 장비반입·고객승인·SOP 지연이 가장 현실적인 실패 경로입니다.',
            '46시리즈 장비발주·반입·라인 구축': '장비 매출은 선행하지만 고객 SOP가 밀리면 셀 업체는 장비가 놀고, 장비사는 검수·잔금 인식이 지연될 수 있습니다. 설치·인수시험·고객 승인 시점을 확인합니다.',
            '46시리즈 실제 양산 개시': '양산 개시와 안정 양산은 다릅니다. 탭리스 접합, 리벳·미세부품, 충방전·에이징, 열관리에서 초기 수율과 검사시간이 악화될 수 있습니다.',
            '46시리즈 첫 고객 출하': '첫 출하는 반복수요가 아닙니다. 반품·교환 접수, 보증충당금, 차량 출시 속도와 후속 월 출하량이 확인돼야 실적 체력을 판단할 수 있습니다.',
            '46시리즈 가동률·수율·실생산': '가동률만 높고 수율이 낮으면 스크랩·재작업 비용이 커질 수 있습니다. 가동률·직행수율·에이징 통과율과 실제 판매 GWh를 같이 봅니다.',
            '46시리즈 모듈조립 내재화·투자': 'BMA 내재화는 부가가치를 늘릴 수 있지만 모듈 안전·냉각·검수·보증 책임도 셀 업체가 더 부담합니다. 외주사 매출 감소와 셀 업체 설비투자 증가를 동시에 봅니다.',
            '46시리즈 소재·장비 직접 수주': '장비·소재 수주가 셀 양산 성공을 보장하지 않습니다. 고객 설계변경, 라인 검수 지연, 수율 문제로 납기·매출 인식이 뒤로 밀릴 수 있습니다.',
            '46시리즈 계약·양산 일정 후퇴': '이미 선행 집행된 장비·건물·재고가 남아 감가상각·운전자본 부담이 먼저 커질 수 있습니다. 취소 GWh와 설비 취소비용, 신규 고객 대체 가능성을 확인합니다.',
        }.get(raw, '대형 셀은 셀당 에너지가 커져 열폭주·배기·방폭·냉각·보험과 탭리스 접합 수율을 함께 확인해야 합니다.')
    if raw.startswith('CATL Debrecen'):
        return '중국 매체의 “정식 생산” 표현을 그대로 양산으로 승격하지 않습니다. CATL 공식자료는 9월 22일 첫 2개 라인이 시험생산에 들어갔다고 명시하며 100GWh는 전체 시설 완공 후 계획치입니다. 먼저 볼 지표는 series production 공식 발표·실제 GWh·수율·첫 고객 출하입니다.'
    if raw.startswith('이수스페셜티 황화리튬'):
        return '준공·시운전·상업생산 계획과 실제 유상 판매는 다릅니다. 황화리튬은 고순도·수율·황화수소 안전·고객 인증이 병목이며, kg당 약 700달러 현 가격은 양산 확대 시 하락할 수 있어 150톤×현 단가를 확정 매출로 보지 않습니다.'
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
    source = item.get('source') or ''
    if group == 'ev_46_series':
        stage = _ev46_stage(text, source)
        if stage == 'known_baseline':
            if EV46_MERCEDES_BASE.search(text) and source not in base.OFFICIAL_OR_PRIMARY:
                return '디일렉 업계 취재 기준선 · Mercedes-Benz/LG에너지솔루션 공식 46100 확인 전'
            return '기업·완성차 공식자료 기준선 · 같은 계약·양산 숫자 재보도는 새 이벤트 아님'
        if stage == 'mou':
            return '기업 공식 MOU라도 비구속 협의 단계 · 최종 공급계약/GWh/SOP 전'
        if stage in {'oem_contract','format_confirmation','backlog_change','sop','first_shipment','ramp_metrics','bma_integration'}:
            if source in base.OFFICIAL_OR_PRIMARY:
                return '셀 업체·완성차 공식자료 · 규격/계약/GWh/양산/출하 단계 직접 확인'
            return '신뢰 매체 보도 · 셀 업체·완성차 공식자료로 고객·규격·물량·일정 교차확인'
        if stage in {'construction_execution','equipment_execution','component_order'}:
            if source in base.OFFICIAL_OR_PRIMARY:
                return '기업 공식자료 · 46파이 전용 설비/장비/소재 수주와 납기 직접 확인'
            return '보도 단계 · 고객사 공시·수주공시·설비 발주자료 교차확인'
        if stage == 'reverse':
            return '계약·공장·고객 일정의 역방향 변화 · 당사자 공식자료와 취소/지연 물량 교차확인'
        return '46파이 관련 보도 · 고객·규격·GWh·공장·SOP를 공식자료로 추가 확인'
    if group == 'global_battery_capacity':
        stage = _catl_debrecen_stage(text, source)
        if stage == 'trial_production_baseline':
            return 'CATL 공식자료 기준 2026-09-22 첫 2개 라인 시험생산 · 100GWh는 전체 완공 후 계획 생산능력 · 정식 양산 아님'
        if source in base.OFFICIAL_OR_PRIMARY:
            return 'CATL 공식자료 · 시험생산/series production/출하/가동률 단계 직접 확인'
        return '보도 단계 · CATL 공식자료와 헝가리 허가·가동 상태 교차확인'
    if group == 'solid_state_material':
        stage = _isu_li2s_stage(text, source)
        if stage == 'commercial_production_plan_baseline':
            return '2026-06 준공 150톤·최대 500톤 설계 + 2026-10 넷째 주 상업생산 계획 기준선 · 실제 상업생산/납품 전'
        if source in base.OFFICIAL_OR_PRIMARY:
            return '이수스페셜티케미컬·공시 1차자료 · 상업생산/고객/물량/증설 직접 확인'
        return '한국경제TV·뉴시스 등 보도 · 회사 공시/고객사 공식자료 교차확인'
    if group != 'ess_battery':
        return _orig_verification(item, group, text)
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
    if a.get('group') != b.get('group'):
        return False
    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"
    if a.get('group') == 'ev_46_series':
        sa = _ev46_stage(ta, a.get('source') or '')
        sb = _ev46_stage(tb, b.get('source') or '')
        if sa != sb:
            return False
        ca, cb = set(_ev46_customer_tags(ta)), set(_ev46_customer_tags(tb))
        ma, mb = set(_ev46_cellmaker_tags(ta)), set(_ev46_cellmaker_tags(tb))
        if ca and cb and not (ca & cb):
            return False
        if ma and mb and not (ma & mb):
            return False
        na, nb = _numbers(ta), _numbers(tb)
        if na and nb:
            return bool(na & nb)
        return True
    if a.get('group') == 'global_battery_capacity':
        sa = _catl_debrecen_stage(ta, a.get('source') or '')
        sb = _catl_debrecen_stage(tb, b.get('source') or '')
        if sa != sb:
            return False
        na, nb = _numbers(ta), _numbers(tb)
        return bool((not na and not nb) or (na & nb))
    if a.get('group') == 'solid_state_material':
        sa = _isu_li2s_stage(ta, a.get('source') or '')
        sb = _isu_li2s_stage(tb, b.get('source') or '')
        if sa != sb:
            return False
        na, nb = _numbers(ta), _numbers(tb)
        return bool((not na and not nb) or (na & nb))
    if a.get('group') != 'ess_battery':
        return False
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
    group = topic_group(text)
    catl_stage = _catl_debrecen_stage(text, source)
    isu_stage = _isu_li2s_stage(text, source)
    us_stage = _us_ess_stage(text, source)
    sdi_stage = _sdi_ess_stage(text, source)
    stage3 = _ess3_stage(text, source)
    ev46_stage = _ev46_stage(text, source)
    if group == 'ev_46_series' and ev46_stage:
        customers = '-'.join(_ev46_customer_tags(text)) or 'no-oem'
        makers = '-'.join(_ev46_cellmaker_tags(text)) or 'no-maker'
        formats = '-'.join(sorted(set(re.findall(r'\b(?:4680|4695|46100|46120)\b|46\s*mm|46mm', text, re.I)))) or 'no-format'
        nums = sorted(_numbers(text))
        suffix = '|'.join(nums[:5]) if nums else 'no-number'
        if ev46_stage == 'known_baseline':
            # Collapse the user-visible current market state to durable semantic
            # baseline keys so publisher rewrites cannot re-alert.
            if EV46_MERCEDES_BASE.search(text): return hashlib.sha256(b'ev46|mercedes|46100|2028|poland-baseline').hexdigest()
            if EV46_RIVIAN_BASE.search(text): return hashlib.sha256(b'ev46|rivian|4695|67gwh|5y-baseline').hexdigest()
            if EV46_CHERY_BASE.search(text): return hashlib.sha256(b'ev46|chery|8gwh|6y-baseline').hexdigest()
            if EV46_BMW_BASE.search(text): return hashlib.sha256(b'ev46|bmw|46mm|95-120mm-baseline').hexdigest()
            if EV46_TESLA_BASE.search(text): return hashlib.sha256(b'ev46|tesla|4680|40gwh-baseline').hexdigest()
            if EV46_SDI_BASE.search(text): return hashlib.sha256(b'ev46|sdi|4695|micromobility-baseline').hexdigest()
            if EV46_INDIGO_BASE.search(text): return hashlib.sha256(b'ev46|indigotech|2027-2030|mou-baseline').hexdigest()
            if EV46_BASELINE_BACKLOG.search(text): return hashlib.sha256(b'ev46|lges|440gwh-backlog|q1-2026-baseline').hexdigest()
            if EV46_ARIZONA_PLAN.search(text): return hashlib.sha256(b'ev46|lges|arizona|year-end-2026-plan-baseline').hexdigest()
            if EV46_POLAND_PLAN.search(text): return hashlib.sha256(b'ev46|lges|poland|46100|2027-line-plan-baseline').hexdigest()
        return hashlib.sha256(f'ev46|{ev46_stage}|{customers}|{makers}|{formats}|{suffix}'.encode()).hexdigest()
    if group == 'global_battery_capacity' and catl_stage:
        return hashlib.sha256(f'catl|debrecen|{catl_stage}'.encode()).hexdigest()
    if group == 'solid_state_material' and isu_stage:
        return hashlib.sha256(f'isu-specialty|li2s|{isu_stage}'.encode()).hexdigest()
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


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    ev46 = next((x for x in candidates if x.get('group') == 'ev_46_series'), None)
    if not ev46 or any(x.get('key') == ev46.get('key') for x in chosen):
        return chosen
    if len(chosen) < limit:
        return [ev46, *chosen]
    return [ev46, *chosen[:-1]]


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.key = key
base.select_diverse = select_diverse
ext._same_event = _same_event

if __name__ == '__main__':
    base.main()

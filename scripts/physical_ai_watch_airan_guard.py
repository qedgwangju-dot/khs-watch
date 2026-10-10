#!/usr/bin/env python3
"""AI-RAN / Physical-AI edge-infrastructure lane for the existing watcher.

This extends the current Physical-AI alert route. It does not create a new bot,
workflow or state file. Articles, press releases and operator announcements are
discovery sources; the alert unit is a material AI-RAN commercialization or
physical-AI deployment milestone.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

import physical_ai_watch_us_autowarcom as defense

qty = defense.qty
base = defense.base

# Nickel-plated battery-can steel: verified 2026-09 qualification is a
# baseline; reported October shipments are an unconfirmed new milestone.
# Never infer Tesla Optimus / Boston Dynamics Atlas as a Dongkuk customer.
DONGKUK_NPS_RECOVERY = 'DIRECT_DONGKUK_NPS_OCT_FIRST_SHIPMENT_REPORT_20261008'
DONGKUK_NAME = re.compile(r'동국산업|Dongkuk\s*Industr(?:y|ies)', re.I)
DONGKUK_NPS = re.compile(r'니켈\s*도금\s*강판|니켈도금강판|nickel[-\s]*plated\s*(?:steel|sheet)|\bDiKel\b', re.I)
DONGKUK_46 = re.compile(r'46\s*시리즈|46시리즈|46\s*파이|46[-\s]*series|46\s*mm|46mm|4680|4695|46120', re.I)
DONGKUK_SHIP_ACTUAL = re.compile(
    r'(?:10\s*월|October).{0,100}(?:초도\s*납품|첫\s*납품|첫\s*출하|initial\s*shipments?|first\s*deliveries?).{0,70}'
    r'(?:시작|개시|완료|진행|출하|전해|보도|started|began|commenced|delivered)|'
    r'(?:초도\s*납품|첫\s*출하).{0,65}(?:10\s*월|October).{0,70}(?:시작|개시|완료|보도|전해|started|began)',
    re.I,
)
DONGKUK_QUAL = re.compile(r'품질\s*(?:인증|승인).{0,30}(?:완료|통과|마쳤|성공)|(?:고객|고객사).{0,50}(?:품질\s*승인|인증).{0,40}(?:완료|통과|마쳤)', re.I)
DONGKUK_CONTRACT = re.compile(r'(?:공급\s*계약|확정\s*발주|구매\s*계약|납품\s*계약|contract\s*signed|purchase\s*order).{0,80}(?:체결|확정|서명|signed|confirmed)|(?:체결|확정).{0,60}(?:공급\s*계약|구매\s*계약)', re.I)
DONGKUK_ROBOT_LINK = re.compile(
    r'(?:Optimus|옵티머스|Atlas|아틀라스|Boston\s*Dynamics|보스턴다이내믹스).{0,90}'
    r'(?:직접\s*납품|직접\s*공급|공급계약\s*체결|직접\s*공급사)|'
    r'(?:직접\s*납품|직접\s*공급|공급계약\s*체결).{0,90}'
    r'(?:Optimus|옵티머스|Atlas|아틀라스|Boston\s*Dynamics|보스턴다이내믹스)',
    re.I,
)
DONGKUK_OFFICIAL_SOURCES = {'동국산업', 'Dongkuk Industries', 'Dongkuk Industry'}
DONGKUK_REPORT_TITLE = '동국산업 북미 46시리즈 소재 10월 초도 납품 시작 보도…공식 출하 확인 전'


def _is_dongkuk_nps(text: str) -> bool:
    return bool(DONGKUK_NAME.search(text) and DONGKUK_NPS.search(text) and DONGKUK_46.search(text))


def _dongkuk_stage(text: str, source: str = '') -> str:
    if not _is_dongkuk_nps(text):
        return ''
    if DONGKUK_SHIP_ACTUAL.search(text):
        return 'official_first_shipment' if source in DONGKUK_OFFICIAL_SOURCES else 'reported_first_shipment'
    if DONGKUK_CONTRACT.search(text) and source in DONGKUK_OFFICIAL_SOURCES:
        return 'official_contract'
    if DONGKUK_QUAL.search(text):
        return 'qualification_baseline'
    return 'background'


def _dongkuk_report_recovery() -> list[dict]:
    # Identical NewsScene article reprinted by ITInsight; original knpp URL may
    # be inaccessible. 10/08 first-delivery claim is from unnamed analyst notes,
    # whereas 09/14 qualification was announced by the company.
    return [{
        'title': DONGKUK_REPORT_TITLE,
        'link': 'https://www.itinsight.kr/news/517649',
        'description': (
            '2026-10-08 뉴스씬 정민재 보도: 동국산업 46시리즈용 니켈도금강판의 '
            '북미 고객 품질 승인 완료는 2026-09-14 회사 발표·2026-09-22 이원휘 대표 인터뷰의 기존 사실이다. '
            '새로운 증권가 탐방 전언에는 10월부터 초도 납품을 시작한 것으로 전해졌다고 기재됐다. '
            '이는 동국산업 공식 실제 출하/매출 인식 확인은 아니다. '
            '연간 판매량 2026년 약 2,000톤, 2027년 약 20,000톤(10배)은 애널리스트 예상치이며 '
            '연간 설비능력 80,000톤과 증설 가능 130,000톤, 기존 설비투자 약 1,300억원과 구별한다. '
            '북미 고객 실명과 배터리 캔 가공업체 실명 모두 비공개다. '
            '테슬라 Optimus·보스턴다이내믹스 Atlas 원통형 배터리 언급은 생태계 가능성에 불과하며 '
            '동국산업이 두 로봇에 니켈도금강판을 직접 납품한다는 계약·양산 근거가 없다.'
        ),
        'source': '뉴스씬',
        'published': '2026-10-08T00:35:00+00:00',
        'direct_recovery': True,
        'dongkuk_reported_shipment': True,
    }]



# DKT humanoid battery module: retrospectively restore an important reported
# production milestone, without turning the July ESS-BMS discussion into sales.
# Company releases, broker research and anonymous customer identities stay separate.
DKT_HUMANOID_RECOVERY = 'DIRECT_DKT_HUMANOID_BATTERY_MODULE_HANA_20260909'
DKT_COMPANY = re.compile(r'디케이티|\bDKT\b|Dongkuk Tech', re.I)
DKT_ROBOT = re.compile(r'휴머노이드|humanoid|로보틱스|robotics|로봇|robot', re.I)
DKT_BATTERY = re.compile(
    r'(?:배터리|battery).{0,45}(?:모듈|module|팩|pack)|'
    r'(?:BMS|배터리관리시스템|배터리\s*관리\s*시스템|battery\s*management)|'
    r'(?:이머전시|비상장치|emergency).{0,45}(?:배터리|battery)',
    re.I,
)
DKT_REPORTED_SOP = re.compile(
    r'(?:8\s*월\s*말|late\s+Aug(?:ust)?).{0,95}(?:승인|approval|approved?).{0,140}'
    r'(?:양산\s*공급[이가은을\s]*(?:시작|개시)|양산\s*(?:공급\s*)?(?:시작|개시)|'
    r'mass[-\s]*production\s*(?:supply\s*)?(?:started|began)|'
    r'(?:started|began)\s+mass[-\s]*production)',
    re.I,
)
DKT_COMPANY_DIRECT = {'디케이티', 'DKT', 'DKT Official', '디케이티 공식 발표'}
DKT_BROKER_SOURCES = {'하나증권', 'Hana Securities', 'IBK투자증권', '교보증권'}
DKT_REPORT_SOURCES = DKT_BROKER_SOURCES | {'프라임경제', '아시아경제', '뉴스프라임', '연합뉴스'}
DKT_DIRECT_CONTRACT = re.compile(
    r'(?:휴머노이드|humanoid).{0,100}(?:BMS|배터리|battery).{0,110}'
    r'(?:정식\s*공급계약|구매\s*계약\s*체결|양산\s*수주\s*확정)|'
    r'(?:BMS|배터리|battery).{0,110}(?:휴머노이드|humanoid).{0,100}'
    r'(?:공급계약\s*체결|정식\s*수주)',
    re.I,
)


def _is_dkt_humanoid(text: str) -> bool:
    return bool(DKT_COMPANY.search(text) and DKT_ROBOT.search(text) and DKT_BATTERY.search(text))


def _dkt_stage(text: str, source: str = '') -> str:
    if not _is_dkt_humanoid(text):
        return ''
    if source in DKT_COMPANY_DIRECT and DKT_DIRECT_CONTRACT.search(text) and not re.search(
        r'기사|증권사|리포트|업계\s*보도|추정', text, re.I
    ):
        return 'official_robot_bms_contract'
    if DKT_REPORTED_SOP.search(text):
        if source in DKT_COMPANY_DIRECT and not re.search(r'증권사|하나증권|파악|보도|추정', text, re.I):
            return 'official_robot_module_sop'
        if source in DKT_REPORT_SOURCES:
            return 'reported_robot_module_sop'
    return 'old_discussion_or_plan'


def _dkt_humanoid_recovery() -> list[dict]:
    # One-time recovery of the past 2026-09 report; expire the backfill so
    # a dedupe-state rollover cannot resend old news as a new event.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 15):
        return []
    return [{
        'title': '디케이티 휴머노이드 비상장치용 배터리 모듈, 8월 말 양산 공급 시작 보도',
        'link': 'https://t.me/s/hanasmallcap',
        'description': (
            '2026년 9월 9일 하나증권 권태우·김진우 리포트: 북미 전기차 고객사향 '
            '휴머노이드 이머전시 디바이스 배터리 모듈은 주당 1,500~2,000대의 초기 공급으로 '
            '검증을 마쳤고 8월 말 승인과 함께 양산 공급이 시작된 것으로 파악했다. '
            '이 고객 실명과 실제 현재 주간 출하량, 계약금액 및 인식매출은 비공개다. '
            '회사 8월 18일 공개자료에는 해당 휴머노이드 소형 배터리팩 모듈을 '
            '9월부터 양산할 예정이라고 기재됐다. '
            '2026년 7월 13일 전자신문의 휴머노이드용 BMS 협력 논의와는 제품·단계가 다르다. '
            '8월 19일 북미 LFP ESS용 BMS 첫 출하는 또 다른 실제 양산 사업이며 '
            '휴머노이드용 BMS 양산을 증명하지 않는다. '
            '테슬라 또는 보스턴다이내믹스가 이번 북미 배터리 모듈의 '
            '확정 구매 고객이라는 공식 양방향 발표는 확인되지 않았다.'
        ),
        'source': '하나증권',
        # The original report date is stated in text. Do not fabricate an
        # exact intraday timestamp; the item is an explicitly recovered
        # earlier milestone, not a new 2026-10-08 announcement.
        'published': None,
        'direct_recovery': True,
        'dkt_reported_robot_module_sop': True,
    }]



# Tesla 3D tactile-array patent PUBLICATION (A1), not a granted patent and
# not proof of an installed Optimus component. This lane uses the patent
# number, not the media headline, as the event identity. The first-page
# publication supplied by the user is evidence for the title/date/applicant;
# it is not a substitute for examining granted claims or physical shipments.
TESLA_TOUCH_PATENT_RECOVERY = 'DIRECT_TESLA_TACTILE_PATENT_US20260310299A1_20261008'
TESLA_TOUCH_PATENT_OFFICIAL = {'USPTO', 'United States Patent and Trademark Office'}
TESLA_TOUCH_PATENT_TITLE = (
    '테슬라, 3차원 유연 촉각센서·대량 제조공정 특허출원 공개 '
    '(US 2026/0310299 A1)'
)
TESLA_TOUCH_PATENT_PUBLICATION_URL = (
    'https://eletric-vehicles.com/tesla/'
    'tesla-seeks-patent-for-touch-sensitive-skin-for-humanoid-robot-optimus/'
)
TESLA_TOUCH_SENSOR_TOPIC = re.compile(
    r'촉각|센서|유연\s*피부|전자\s*피부|tactile|touch|sensor|compliant|robot\s*skin',
    re.I,
)
TESLA_TOUCH_PATENT_PUBLICATION_MARKER = re.compile(
    r'published|publication|공개|공표|'
    r'(?:Oct(?:ober)?\s*8,?\s*2026|2026[-./]10[-./]08|2026년\s*10월\s*8일)',
    re.I,
)
TESLA_TOUCH_PATENT_GRANT = re.compile(
    r'\bpatent\s+(?:was\s+|has\s+been\s+)?granted\b|'
    r'\bpatent\s+issued\b|특허\s*등록\s*완료|특허\s*등록\s*확정',
    re.I,
)
TESLA_TOUCH_PATENT_GRANT_DENIAL = re.compile(
    r'not\s+(?:yet\s+)?granted|not\s+issued|'
    r'특허\s*(?:등록|승인)\s*(?:전|미확인|아님|아니다)',
    re.I,
)


def _tesla_touch_patent_match(text: str) -> bool:
    no_punctuation = re.sub(r'[\s/.,:_\-]', '', text).upper()
    return bool(
        '20260310299A1' in no_punctuation
        and ('TESLA' in no_punctuation or '테슬라' in text)
        and TESLA_TOUCH_SENSOR_TOPIC.search(text)
    )


def _tesla_touch_patent_stage(text: str, source: str = '') -> str:
    if not _tesla_touch_patent_match(text):
        return ''
    if TESLA_TOUCH_PATENT_GRANT.search(text) and not TESLA_TOUCH_PATENT_GRANT_DENIAL.search(text):
        if source in TESLA_TOUCH_PATENT_OFFICIAL:
            return 'official_grant'
        # Media speculation that A1 has been granted is not another alert.
        return 'unverified_grant'
    if TESLA_TOUCH_PATENT_PUBLICATION_MARKER.search(text):
        return 'application_publication'
    return 'background'


def _tesla_touch_patent_recovery() -> list[dict]:
    # One-time recovery only: the 2026-10-08 A1 publication is an event
    # distinct from 2025 filing/provisional dates, patent grant, or SOP.
    # A date-only source does not justify inventing an hourly timestamp.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 12):
        return []
    return [{
        'title': TESLA_TOUCH_PATENT_TITLE,
        'link': TESLA_TOUCH_PATENT_PUBLICATION_URL,
        'description': (
            '사용자 제공 미국 특허공개문서 표지 기준: 공개번호 US 2026/0310299 A1, '
            '공개일 2026-10-08, 출원인 Tesla Inc., 정규 출원일 2025-09-11, '
            '가출원일 2025-04-04. 발명 제목은 THREE-DIMENSIONAL SOFT COMPLIANT '
            'ARRAY TACTILE SENSOR WITH MULTI-MODAL SENSING AND SCALABLE '
            'MANUFACTURING METHODS. 사용자 제공 동일 기사 전문에 따르면 출원 청구항은 '
            '20개이며 특허 본문에 Optimus 제품명이 직접 기재되지 않았다. '
            '감지점 개수·간격, 측정 가능한 힘의 범위, 내구성 수치는 기재되지 않았다. '
            '다중 모드 명칭에도 불구하고 정전용량식 또는 저항식 구조를 설명할 뿐 '
            '전단력·미끄러짐·온도를 별개로 감지한다고 입증하지 않는다. '
            '제조 방식은 평판 도체 인쇄 후 적층·열성형, 또는 기판 선성형 후 '
            '곡면 직접 인쇄·정밀 도포의 두 경로이다. '
            'Tesla 공식 Optimus 채용공고는 손 생산에서 열성형·정밀 도포·적층, '
            '시운전과 수율 개선을 기술개발 과제로 언급한다. 다만 해당 특허의 '
            'Optimus Gen 3 실제 탑재, 양산 완료, 고객 출하, 공급사, 수율 및 '
            '매출을 확정할 수 없고 A1 공개는 B2 등록이 아니다. '
            '기사 전문은 사용자가 직접 제공했으며 기사 웹페이지·USPTO 전체 공개문서 '
            '직접 열람은 완료하지 못했다. 청구항 수 및 수치 부재는 기사 서술에 근거한다.'
        ),
        'source': '사용자제공 특허표지·기사 전문',
        'published': None,
        'direct_recovery': True,
        'user_supplied_publication': True,
    }]


# Digital Optimus is a screen-driven software agent. It is not the
# electromechanical Optimus humanoid, and a CEO gaming-progress statement
# is not an independently reproduced robot or general-computer benchmark.
DIGITAL_OPTIMUS_GAME_RECOVERY = 'DIRECT_DIGITAL_OPTIMUS_GAME_MUSK_2108823477071303109_20261010'
DIGITAL_OPTIMUS_POST_ID = '2108823477071303109'
DIGITAL_OPTIMUS_CANONICAL_URL = 'https://x.com/elonmusk/status/2108823477071303109'
DIGITAL_OPTIMUS_ID = re.compile(r'Digital\s+Optimus|디지털\s*옵티머스|\bMacrohard\b', re.I)
DIGITAL_OPTIMUS_GAMES = re.compile(
    r'\bgames?\b|게임|게임\s*에이전트|'
    r'\bDiablo\b|디아블로|Counter[-\s]*Strike|카운터\s*스트라이크|'
    r'League\s+of\s+Legends|리그\s*오브\s*레전드|'
    r'(?:real[-\s]*time|실시간).{0,30}(?:games?|게임)|'
    r'(?:games?|게임).{0,50}(?:agent|에이전트|play|플레이|학습)',
    re.I,
)
DIGITAL_OPTIMUS_TESLA_SOURCES = {'Tesla', 'Tesla AI', 'Tesla Official', '테슬라'}
DIGITAL_OPTIMUS_CEO_SOURCES = {'Elon Musk (X)', '일론 머스크 (X)'}
DIGITAL_OPTIMUS_BENCHMARK = re.compile(
    r'(?:benchmark|벤치마크|실험\s*검증|평가\s*시험).{0,150}'
    r'(?:\d{1,3}(?:\.\d+)?\s*%|성공률|episodes?|에피소드|지연시간|latency)|'
    r'(?:\d{1,3}(?:\.\d+)?\s*%|성공률|episodes?|에피소드).{0,150}'
    r'(?:benchmark|벤치마크|재현|reproduced|independent|독립)',
    re.I,
)
DIGITAL_OPTIMUS_BENCHMARK_NOT = re.compile(
    r'(?:no|without|not|없음|미공개|아직).{0,35}(?:benchmark|벤치마크|성공률|실험\s*검증)|'
    r'(?:benchmark|벤치마크|성공률).{0,35}(?:없음|미공개|미확인|not\s+available)',
    re.I,
)
DIGITAL_OPTIMUS_COMMERCIAL = re.compile(
    r'(?:Digital\s+Optimus|디지털\s*옵티머스).{0,100}'
    r'(?:paid\s+customer|commercial\s+launch|production\s+deployment|'
    r'유료\s*고객|정식\s*상용\s*출시|상용\s*계약|매출\s*발생)|'
    r'(?:정식\s*상용\s*출시|commercial\s+launch).{0,90}'
    r'(?:Digital\s+Optimus|디지털\s*옵티머스)',
    re.I,
)


def _is_digital_optimus_game(text: str) -> bool:
    return bool(
        DIGITAL_OPTIMUS_ID.search(text)
        and (DIGITAL_OPTIMUS_GAMES.search(text) or
             (DIGITAL_OPTIMUS_POST_ID in text))
    )


def _digital_optimus_stage(text: str, source: str = '') -> str:
    if not _is_digital_optimus_game(text):
        return ''
    if DIGITAL_OPTIMUS_COMMERCIAL.search(text) and source in DIGITAL_OPTIMUS_TESLA_SOURCES:
        return 'commercial_launch'
    if (DIGITAL_OPTIMUS_BENCHMARK.search(text)
            and not DIGITAL_OPTIMUS_BENCHMARK_NOT.search(text)
            and source in DIGITAL_OPTIMUS_TESLA_SOURCES):
        return 'tesla_benchmark'
    if (DIGITAL_OPTIMUS_POST_ID in text and
            source in DIGITAL_OPTIMUS_CEO_SOURCES and
            re.search(r'halfway|half\s*the|절반|50\s*%', text, re.I)):
        return 'musk_game_progress'
    return 'background'


def _digital_optimus_game_recovery() -> list[dict]:
    # A single 2026-10-10 Musk post, reported as CEO's progress claim.
    # Verified via unchanged X post ID in public tweet archive and Tesla's
    # official Digital Optimus recruiting; not a formal independent benchmark.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 14):
        return []
    return [{
        'title': '일론 머스크 Digital Optimus 게임 진행 발언: Diablo 절반·Counter-Strike',
        'link': DIGITAL_OPTIMUS_CANONICAL_URL,
        'description': (
            '2026-10-10 16:34 KST Elon Musk X 게시글 '
            '2108823477071303109 아카이브 확인. Digital Optimus는 사람이 보듯 '
            '게임 화면만 보고 Diablo 캠페인의 약 절반까지 진행한다고 머스크가 주장했고, '
            'Counter-Strike와 반응이 빠른 다른 게임에서도 플레이 능력이 좋다고 언급했다. '
            'League of Legends는 아직 학습 중이며 여러 게임으로 일반화가 목표다. '
            '이 수치는 경영진의 자기보고이고 독립 검증된 승률·정량 벤치마크는 아니다. '
            '테슬라의 공식 채용목록에 실시간 게임용 Digital Optimus 머신러닝 엔지니어가 '
            '올라와 있으며 장기 기억·실시간 제어·다른 게임으로의 성능 전이와 '
            '일반 컴퓨터 사용을 개발과제로 명시한다. '
            'Digital Optimus는 화면·소프트웨어 조작 에이전트이며 '
            '물리 휴머노이드 Optimus의 공장 투입·작업 성공률·양산 실적과 다르다. '
            '모델 구조, 지연시간, 인간 개입률, 학습비, 상용 계약·매출은 공개되지 않았다. '
            'X 직접 열람은 제한되었고 같은 게시물 번호를 공개 아카이브로 대조했다.'
        ),
        'source': 'Elon Musk (X)',
        'published': '2026-10-10T07:34:00+00:00',
        'direct_recovery': True,
        'ceo_reported_gameplay': True,
    }]


_orig_query_news = base.query_news


def query_news(q: str) -> list[dict]:
    if q == DONGKUK_NPS_RECOVERY:
        return _dongkuk_report_recovery()
    if q == DKT_HUMANOID_RECOVERY:
        return _dkt_humanoid_recovery()
    if q == TESLA_TOUCH_PATENT_RECOVERY:
        return _tesla_touch_patent_recovery()
    if q == DIGITAL_OPTIMUS_GAME_RECOVERY:
        return _digital_optimus_game_recovery()
    return _orig_query_news(q)


base.query_news = query_news
if DONGKUK_NPS_RECOVERY not in base.QUERIES:
    base.QUERIES.append(DONGKUK_NPS_RECOVERY)
if DKT_HUMANOID_RECOVERY not in base.QUERIES:
    base.QUERIES.append(DKT_HUMANOID_RECOVERY)
if TESLA_TOUCH_PATENT_RECOVERY not in base.QUERIES:
    base.QUERIES.append(TESLA_TOUCH_PATENT_RECOVERY)
if DIGITAL_OPTIMUS_GAME_RECOVERY not in base.QUERIES:
    base.QUERIES.append(DIGITAL_OPTIMUS_GAME_RECOVERY)
for q in (
    '("Digital Optimus" OR "Macrohard" OR 디지털옵티머스) '
    '(Diablo OR 디아블로 OR "Counter Strike" OR Counter-Strike OR 게임 OR games) '
    '(Elon Musk OR 일론머스크 OR CEO OR Tesla)',
    '("Digital Optimus" OR 디지털옵티머스) '
    '(게임 간 성능 전이 OR 벤치마크 OR 성공률 OR 독립평가 OR 유료고객 OR 매출 OR 출시 '
    'OR transfer OR benchmark OR commercial launch)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
for q in (
    '(Tesla OR 테슬라) ("US 2026/0310299" OR US20260310299A1 '
    'OR "three-dimensional soft compliant array tactile sensor") '
    '(patent OR publication OR 특허 OR 촉각센서)',
    '(Tesla OR 테슬라) (Optimus OR 옵티머스) '
    '(촉각센서 OR "tactile sensor" OR "robot skin") '
    '(실제 양산 OR 고객 승인 OR 생산 수율 OR 내구성 OR 출하 OR 설계 변경)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
for q in (
    '(디케이티 OR DKT) (휴머노이드 OR humanoid OR 로보틱스) '
    '(BMS OR 배터리팩 OR 배터리모듈 OR 충전모듈) '
    '(공급계약 OR 고객승인 OR 양산공급 OR 본계약 OR 출하 OR 수율 OR 납기 OR 연기)',
    '(디케이티 OR DKT) (이머전시 디바이스 OR 소형 배터리팩 OR 휴머노이드 BMS) '
    '(북미 OR 미국 OR 로봇) (공급확대 OR 검증 OR 실제 출하 OR 매출 OR 수주)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
for q in (
    '(동국산업 OR "Dongkuk Industries") (니켈도금강판 OR "nickel plated steel" OR DiKel) '
    '(46시리즈 OR 4680 OR "46 series") (초도납품 OR 출하 OR 고객승인 OR 품질인증 OR 공급계약 OR 양산 OR 납품지연)',
    '(동국산업 OR "Dongkuk Industries") (원통형 배터리 OR 니켈도금강판 OR 46파이) '
    '(북미 OR 로봇 OR 휴머노이드 OR 피지컬AI) (공급계약 OR 본계약 OR 실제출하 OR 매출 OR 양산수율)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_clean_title = base.clean_title
_orig_tag_for = base.tag_for
_orig_key = base.key
_orig_select_diverse = base.select_diverse

AIRAN_ID = re.compile(r'AI[-\s]?RAN|Aerial\s+RAN|ARC[-\s]?Pro|AI[-\s]?native\s+(?:RAN|6G)|AI\s+RAN', re.I)
PHYSICAL = re.compile(
    r'physical\s+AI|robot(?:ics)?|humanoid|vision\s+AI|drone|autonomous|edge\s+AI|'
    r'피지컬\s*AI|로봇|휴머노이드|드론|자율|엣지\s*AI',
    re.I,
)
COMMERCIAL = re.compile(
    r'pilot|trial|field\s+test|deployment|deploy|commercial|customer|operator|contract|order|'
    r'base\s+station|cell\s+site|mobile\s+switching\s+office|edge\s+site|general\s+availability|'
    r'실증|시험|현장\s*검증|배치|상용|고객|통신사|계약|수주|기지국|사이트|출시',
    re.I,
)
QUANT = re.compile(
    r'\b\d+(?:\.\d+)?\s*(?:ms|Gbps|Mbps|%|x|배|site|sites|기지국|개소|GPU|GPUs)\b|'
    r'latency|throughput|uplink|CAPEX|revenue|매출|지연시간|처리량|업링크|설비투자',
    re.I,
)
ACTORS = re.compile(r'NVIDIA|엔비디아|T-Mobile|Nokia|노키아|SK텔레콤|SKT|SoftBank|소프트뱅크|Dell|Siemens', re.I)

for q in [
    '("AI-RAN" OR "AI RAN" OR "Aerial RAN") ("physical AI" OR robotics OR robot OR humanoid OR edge AI) (NVIDIA OR T-Mobile OR Nokia OR operator OR deployment OR pilot)',
    '("AI-RAN" OR "AI RAN") (deployment OR pilot OR field trial OR commercial OR contract OR customer OR base station OR latency OR throughput)',
    '(엔비디아 OR NVIDIA) ("AI-RAN" OR "AI RAN") (피지컬AI OR 로봇 OR 휴머노이드 OR 엣지AI OR 통신사 OR 기지국 OR 실증 OR 상용화)',
]:
    if q not in base.QUERIES:
        base.QUERIES.append(q)

base.OFFICIAL_OR_PRIMARY.update({'NVIDIA', 'T-Mobile', 'Nokia', 'SK텔레콤', 'SK Telecom'})
base.TRUSTED.update({'Reuters', 'Bloomberg', 'The Robot Report', 'Light Reading', 'Fierce Network'})


def _is_airan(text: str) -> bool:
    return bool(AIRAN_ID.search(text) and (PHYSICAL.search(text) or COMMERCIAL.search(text)) and ACTORS.search(text))


def topic_group(text: str) -> str | None:
    if _is_digital_optimus_game(text):
        return 'digital_optimus_games'
    if _tesla_touch_patent_match(text):
        return 'tesla_touch_patent'
    if _is_dkt_humanoid(text):
        return 'dkt_humanoid'
    if _is_dongkuk_nps(text):
        return 'dongkuk_nps'
    if _is_airan(text):
        return 'airan'
    return _orig_topic_group(text)


def _stage(text: str) -> str:
    if re.search(r'contract|order|commercial\s+agreement|revenue|paid|수주|계약|매출|유료', text, re.I):
        return 'commercial'
    if re.search(r'deployment|deploy|field\s+test|pilot|trial|실증|현장\s*검증|배치', text, re.I):
        return 'field'
    if QUANT.search(text):
        return 'quantified'
    return 'platform'


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) == 'digital_optimus_games':
        return {
            'musk_game_progress': 43,
            'tesla_benchmark': 55,
            'commercial_launch': 60,
            'background': 0,
        }.get(_digital_optimus_stage(text, item.get('source') or ''), 0)
    if topic_group(text) == 'tesla_touch_patent':
        stage = _tesla_touch_patent_stage(text, item.get('source') or '')
        return {
            'application_publication': 40,
            'official_grant': 48,
            'unverified_grant': 0,
        }.get(stage, 0)
    if topic_group(text) == 'dkt_humanoid':
        stage = _dkt_stage(text, item.get('source') or '')
        return {'reported_robot_module_sop': 44, 'official_robot_module_sop': 52,
                'official_robot_bms_contract': 56, 'old_discussion_or_plan': 0}.get(stage, 0)
    if topic_group(text) == 'dongkuk_nps':
        stage = _dongkuk_stage(text, item.get('source') or '')
        return {'reported_first_shipment': 33, 'official_first_shipment': 46,
                'official_contract': 44, 'qualification_baseline': 0,
                'background': 0}.get(stage, 0)
    if topic_group(text) != 'airan':
        return _orig_score(item)
    s = 18
    if item.get('source') in base.OFFICIAL_OR_PRIMARY:
        s += 8
    elif item.get('source') in base.TRUSTED:
        s += 4
    stage = _stage(text)
    if stage == 'commercial':
        s += 12
    elif stage == 'field':
        s += 9
    elif stage == 'quantified':
        s += 7
    if PHYSICAL.search(text):
        s += 7
    if QUANT.search(text):
        s += 5
    return s


def category(text: str, group: str) -> str:
    if group == 'digital_optimus_games':
        # The renderer has no source argument, while score() does. The unique
        # 2026-10-10 CEO post must never be promoted into a benchmark merely
        # because its text discusses *missing* measurements.
        if DIGITAL_OPTIMUS_POST_ID in text:
            return 'Digital Optimus · 게임 수행 경영진 진전 발언'
        if DIGITAL_OPTIMUS_COMMERCIAL.search(text):
            return 'Digital Optimus · 정식 상용화·유료 계약'
        if DIGITAL_OPTIMUS_BENCHMARK.search(text) and not DIGITAL_OPTIMUS_BENCHMARK_NOT.search(text):
            return 'Digital Optimus · 회사 공식 다중게임 성능 검증'
        return 'Digital Optimus · 개발 단계'
    if group == 'tesla_touch_patent':
        # Renderer omits item['source'], while score() verifies source.
        # A press claim of "grant" scores zero; only an official source can
        # result in a rendered grant-stage event.
        if TESLA_TOUCH_PATENT_GRANT.search(text) and not TESLA_TOUCH_PATENT_GRANT_DENIAL.search(text):
            return '테슬라 촉각센서 · 특허 등록 공식확인 단계'
        return '테슬라 촉각센서 · 미국 특허출원 공개 A1'
    if group == 'dkt_humanoid':
        # The legacy renderer deliberately calls category(title + description)
        # WITHOUT item['source']. Re-evaluate evidence from the visible prose;
        # never downgrade a broker-confirmed alert to an old-plan label.
        if DKT_REPORTED_SOP.search(text):
            if (re.search(r'(?:회사\s*공식\s*(?:발표|확인)|'
                          r'디케이티.{0,130}직접\s*발표)', text, re.I)
                    and not re.search(r'하나증권|증권사|파악|업계\s*보도', text, re.I)):
                return '디케이티 로보틱스 · 배터리 모듈 양산 회사 공식 확인'
            return '디케이티 로보틱스 · 배터리 모듈 양산 공급 증권사 확인'
        if DKT_DIRECT_CONTRACT.search(text) and re.search(
            r'디케이티.{0,150}(?:계약.{0,70}체결|체결.{0,70}발표)', text, re.I
        ):
            return '디케이티 로보틱스 · 휴머노이드용 BMS 정식 계약'
        return '디케이티 로보틱스 · 협의·양산계획 기존 기준선'
    if group == 'dongkuk_nps':
        official_source = next(
            (name for name in DONGKUK_OFFICIAL_SOURCES if text.endswith(' ' + name)), ''
        )
        stage = _dongkuk_stage(text, official_source)
        return {
            'reported_first_shipment': '동국산업 46시리즈 · 10월 초도 납품 보도',
            'official_first_shipment': '동국산업 46시리즈 · 첫 출하 공식 확인',
            'official_contract': '동국산업 46시리즈 · 정식 공급계약',
        }.get(stage, '동국산업 46시리즈 · 품질 인증 기존 기준선')
    if group == 'airan':
        stage = _stage(text)
        if stage == 'commercial':
            return '엔비디아 AI-RAN · 상용계약·매출'
        if stage == 'field':
            return '엔비디아 AI-RAN · Physical AI 현장 실증·배치'
        if stage == 'quantified':
            return '엔비디아 AI-RAN · 지연시간·처리량 정량 개선'
        return '엔비디아 AI-RAN · Physical AI 엣지 인프라'
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    if cat == 'Digital Optimus · 게임 수행 경영진 진전 발언':
        return (
            '10/10 머스크 X: 게임 화면을 보며 Diablo 캠페인의 약 절반까지 진행한다고 주장. '
            'Counter-Strike는 좋은 플레이 능력을 언급했지만 수치가 없고 '
            'League of Legends는 학습 단계입니다. '
            '테슬라의 게임용 실시간 에이전트 채용도 확인되지만 '
            '이는 독립 성능 검증도 물리 Optimus 양산도 아닙니다. '
            '게임 간 범용성·실시간 행동 제어의 연구개발 진전 가능성을 보는 초기 지표입니다.'
        )
    if cat == 'Digital Optimus · 회사 공식 다중게임 성능 검증':
        return (
            '경영진 자기보고에서 회사의 재현 가능한 평가 지표 단계로 상승한 신호입니다. '
            '훈련·평가 게임 분리, 성공률·지연시간·사람 개입·학습비용·평가 반복횟수를 검증합니다.'
        )
    if cat == 'Digital Optimus · 정식 상용화·유료 계약':
        return (
            'Digital Optimus가 연구개발을 넘어 실제 고객·사용료·계약 매출로 이동한 경우입니다. '
            '판매량·반복 사용권·운영비·계약 기간·매출 인식을 검증합니다.'
        )
    if cat == 'Digital Optimus · 개발 단계':
        return '현재 단계는 연구개발이며 아직 유료 계약과 독립 성능 검증을 뜻하지 않습니다.'
    if cat == '테슬라 촉각센서 · 특허 등록 공식확인 단계':
        return (
            '미국 특허청의 후속 등록 상태 변화가 2026-10-08 공개출원 A1과 '
            '별도로 확인된 단계입니다. 등록번호·청구항·등록일을 반드시 다시 확인하고, '
            '제품 채택이나 판매 실적과는 분리합니다.'
        )
    if cat == '테슬라 촉각센서 · 미국 특허출원 공개 A1':
        return (
            '2026-10-08 미국 특허출원 공개 US 2026/0310299 A1. '
            '정규 출원 2025-09-11·가출원 2025-04-04입니다. '
            '손가락·손바닥 곡면에 밀착하는 유연 촉각 배열의 '
            '평판 인쇄 후 열성형 또는 곡면 직접 인쇄 제조법이 핵심입니다. '
            '제공 기사에 따르면 청구항은 20개이지만 감지점 수·간격, '
            '힘 범위, 내구성 실측치는 없습니다. 특허 본문에는 Optimus가 직접 등장하지 '
            '않으며 별도 전단력·미끄러짐·온도 감지도 확인되지 않았습니다. '
            '정전용량식·저항식 구조와 Tesla 공식 채용자료는 제조 연구개발을 뒷받침하지만 '
            '해당 특허의 Optimus 양산 적용·부품 계약·매출을 증명하지 않습니다.'
        )
    if cat.startswith('디케이티 로보틱스 · '):
        if '증권사 확인' in cat:
            return ('7/13 휴머노이드용 BMS 협의 보도→8/18 회사의 소형 배터리팩 모듈 '
                    '9월 양산 계획→9/9 하나증권의 8월 말 양산 공급 시작 파악으로 단계가 바뀌었습니다. '
                    '주당 1,500~2,000대는 초기 고객 검증용 공급 규모이지 현재 정규 출하량 확정치가 아닙니다. '
                    '북미 고객 실명·단가·계약액·인식매출 미공개. '
                    '8/19 북미 LFP ESS용 BMS 실제 첫 출하는 이 휴머노이드 모듈과 별도 사업입니다.')
        if '양산 회사 공식 확인' in cat:
            return ('회사 직접 확인으로 북미 휴머노이드용 배터리 모듈의 양산 공급이 '
                    '보도 단계를 넘어 공식 단계로 이동했습니다. '
                    '실제 출하 대수·평균판매단가·정규 구매계약·반복 발주·분기 인식매출을 분리해 검증합니다.')
        if 'BMS 정식 계약' in cat:
            return ('협의 중이던 휴머노이드용 BMS의 계약이 별도 공식 확인된 단계입니다. '
                    '기존 비상장치용 배터리 모듈, ESS용 BMS와 구분하고 고객·계약액·첫 출하를 확인합니다.')
        return '7/13 협력 논의·8/18 양산 계획의 과거 기준선입니다. 반복 기사만으로 계약·매출을 확정하지 않습니다.'
    if cat.startswith('동국산업 46시리즈 · '):
        if '초도 납품 보도' in cat:
            return ('9월 14일 고객 품질인증 완료·4분기 공급 예정은 기존 회사 발표입니다. '
                    '10월 8일 신규 내용은 10월 초도 납품을 시작했다는 증권가 탐방 전언으로, '
                    '회사 확인 출하·매출은 아직 아닙니다. 2026년 약 2,000톤→2027년 약 2만톤은 '
                    '애널리스트 전망이며, 기존 1,300억원 설비·연산 8만톤과 구분합니다. '
                    '실제 출하량×검증된 톤당 평균판매단가가 매출로 연결되는지가 핵심입니다.')
        if '첫 출하 공식 확인' in cat:
            return ('동국산업이 북미 46시리즈 소재 첫 실제 출하를 자체 발표한 단계입니다. '
                    '출하 톤수·배터리 캔 가공업체·원화 단가·매출 인식 분기를 확인합니다.')
        if '정식 공급계약' in cat:
            return ('기존 품질인증을 넘어 신규 공급계약의 실제 체결·구매 물량·기간이 '
                    '회사 공식자료로 확인된 단계입니다. 계약금액과 기인식 매출을 분리합니다.')
        return '기존 고객 품질인증·4분기 양산 계획의 재보도는 신규 상업 매출로 인정하지 않습니다.'
    if not cat.startswith('엔비디아 AI-RAN'):
        return _orig_meaning(cat)
    if '상용계약' in cat:
        return ('AI-RAN이 통신 연구개발을 넘어 실제 통신사·산업 고객의 상용 인프라 매출로 전환되는 신호입니다. '
                '기지국·엣지 사이트 수, GPU/서버 물량, 계약금액과 반복 매출을 확인합니다.')
    if '현장 실증' in cat:
        return ('로봇·비전 AI의 무거운 추론을 단말에서 통신망 엣지로 일부 이전하는 Physical AI 배치 인프라 신호입니다. '
                '통신사 실명, 실제 현장, 지연시간·업링크와 이후 상용 전환 여부를 추적합니다.')
    if '정량 개선' in cat:
        return ('AI-RAN의 투자 논리가 실제 저지연·고업링크·엣지 추론 효율 개선으로 검증되는 신호입니다. '
                '같은 장비·같은 트래픽 조건에서의 지연시간·처리량과 사이트당 경제성을 봅니다.')
    return ('AI-RAN이 통신망을 단순 연결망이 아니라 분산 AI 추론 인프라로 전환하는지 보는 신호입니다. '
            'Physical AI 고객·사이트·GPU 물량과 Edge Computing 매출 연결을 확인합니다.')


def risk(cat: str) -> str:
    if cat.startswith('Digital Optimus · '):
        return (
            '실패 경로는 게임별 단기 시연에는 성공해도 새로운 게임·긴 작업·일반 컴퓨터 '
            '환경에서 기억·계획·반응지연·오작동 문제가 드러나는 경우입니다. '
            'Diablo 약 절반은 검증된 성공률 50%가 아니며 게임 난이도·재시도·'
            '사람 개입량이 공개되지 않았습니다. Counter-Strike도 승률·평균 지연시간은 '
            '미공개이고 League는 학습 중입니다. 6~12개월 동안 독립 평가·'
            '처음 보는 게임 성능·사람 개입률·작업 완료시간과 실제 고객 결제를 확인합니다. '
            '디지털 에이전트의 성능이 물리적 Optimus 손·이동·안전 성능으로 '
            '즉시 이전된다는 근거도 없습니다.'
        )
    if cat == '테슬라 촉각센서 · 특허 등록 공식확인 단계':
        return (
            '등록돼도 어떤 청구항이 유지됐는지, 권리범위가 실제 제품을 덮는지 '
            '확인해야 합니다. 특허 등록과 수율·고객납품·현금매출은 별개의 사건입니다.'
        )
    if cat == '테슬라 촉각센서 · 미국 특허출원 공개 A1':
        return (
            'A1 공개는 B2 특허등록도, Optimus 손 양산 탑재도, 외부부품 공급계약도 아닙니다. 다중 모드라는 제목만으로 전단력·미끄러짐·온도 별도 감지를 확정할 수 없습니다. '
            '열성형 후 전극 단선·인쇄 저항 편차·층간 박리·촉각센서 드리프트·'
            '반복 접촉 내구성·정밀 검사시간이 양산 병목 후보입니다. '
            '향후 6~12개월 동안 Tesla 공식 적용 공개, 반복 접촉시험, '
            '센서 양품률, 작업 성공률, 교체주기와 실제 손 출하가 확인되는지 추적합니다.'
        )
    if cat.startswith('디케이티 로보틱스 · '):
        return ('최대 오판은 북미 익명 고객을 테슬라로 확정하거나 '
                '휴머노이드 배터리 모듈과 휴머노이드용 BMS·ESS용 BMS를 같은 공급계약으로 보는 것입니다. '
                '소형 팩은 발열·고출력 순간 방전·배선 진동·충격·열폭주 전파·보호회로 신뢰성 검증이 병목입니다. '
                '향후 6~12개월의 조기경보는 실제 주간 출하·재작업률·반품·교환 접수·고객 승인 및 분기 매출입니다.')
    if cat.startswith('동국산업 46시리즈 · '):
        return ('테슬라 Optimus·보스턴다이내믹스 Atlas의 원통형 배터리 언급은 '
                '동국산업의 두 로봇 직접 공급 증거가 아닙니다. 북미 실제 고객·캔 공급사도 비공개입니다. '
                '연산 8만톤 대비 올해 예상 2,000톤은 2.5%, 내년 2만톤 전망은 25%에 해당합니다(판매량/설비능력 단순비교). '
                '니켈도금 두께 불균일·캔 성형 균열·밀봉 불량은 누액·발열·열폭주·화재 위험과 수율·보험·보증충당금 부담으로 이어질 수 있습니다. '
                '6~12개월 위험구간의 조기 지표는 고객 검수·불량률과 4분기 실제 출하 톤수·원화 매출입니다.')
    if not cat.startswith('엔비디아 AI-RAN'):
        return _orig_risk(cat)
    return ('AI-RAN과 휴머노이드 직접 채택은 아직 같은 의미가 아닙니다. 현재 공식 실증은 비전 AI·도시·유틸리티·드론 등도 포함하므로 '
            '테슬라·피겨 같은 휴머노이드 고객이 AI-RAN을 실제 사용하는지는 별도로 확인합니다. '
            '현장 지연시간·사이트당 비용·통신사 설비투자와 상용 계약이 먼저 드러나는 조기 지표입니다.')


def verification(item: dict, group: str, text: str) -> str:
    if group == 'digital_optimus_games':
        stage = _digital_optimus_stage(text, item.get('source') or '')
        if stage == 'musk_game_progress':
            return (
                '10/10 일론 머스크 X 게시물 번호·공개 아카이브 교차확인 · '
                'X 직접 열람 제한 · Tesla 공식 채용자료 별도 확인 · '
                '게임 성능·범용성은 경영진 자기보고이며 독립 검증 없음'
            )
        if stage == 'tesla_benchmark':
            return 'Tesla 공식 평가자료 기반 · 평가 조건·독립 재현·게임 간 전이 별도 확인'
        if stage == 'commercial_launch':
            return 'Tesla 공식 상용화 발표 · 유료 고객·실제 매출 별도 확인'
        return '개발·채용 단계 보도, 정량 성능 미확인'
    if group == 'tesla_touch_patent':
        if _tesla_touch_patent_stage(text, item.get('source') or '') == 'official_grant':
            return 'USPTO 공식자료의 등록 상태 · 등록번호·청구항·제품 채택 별도 확인 필요'
        if item.get('user_supplied_publication'):
            return (
                '사용자 제공 A1 특허표지·영어 기사 전문 확인 · Tesla 공식 채용자료로 '
                '제조기술 방향 교차확인 · 기사 웹페이지·USPTO 문서 전체 직접 열람 미완료 · '
                'Optimus 직접 명시·특허 등록·실제 제품 탑재·매출 미확인'
            )
        return '특허 공개번호와 보도 내용 확인 · USPTO 원문·Tesla 실제 탑재 여부 후속 검증'
    if group == 'dkt_humanoid':
        stage = _dkt_stage(text, item.get('source') or '')
        if stage == 'reported_robot_module_sop':
            return ('9/9 하나증권 확인 보고·프라임경제 교차 보도 · '
                    '8/18 회사 양산 계획 공개 · 회사 직접 출하·인식매출·익명 고객 실명은 미확인')
        if stage == 'official_robot_module_sop':
            return '회사 직접 양산 확인 · 실제 공급계약·판매수량·매출인식 별도 확인'
        if stage == 'official_robot_bms_contract':
            return '회사 직접 휴머노이드용 BMS 공급계약 확인 · ESS용 BMS와 다른 계약'
        return '기존 개발 협의·양산 계획 단계 · 현재 신규 양산 증빙 아님'
    if group == 'dongkuk_nps':
        stage = _dongkuk_stage(text, item.get('source') or '')
        if stage == 'reported_first_shipment':
            return '10/08 뉴스씬 증권가 전언 · 실제 10월 출하 회사 미확인 · 9/14 회사발표·9/22 대표인터뷰로 고객 인증만 검증'
        if stage in {'official_first_shipment', 'official_contract'}:
            return '동국산업 1차자료 단계 · 계약·검수·실적 반영 별도 확인'
        return '9월 기존 인증 기준선 · 신규 출하 아님'
    if group != 'airan':
        return _orig_verification(item, group, text)
    source = item.get('source') or ''
    if source in base.OFFICIAL_OR_PRIMARY:
        return '엔비디아·통신사 공식자료'
    if source in base.TRUSTED:
        return '신뢰 매체 보도 · 엔비디아/통신사 공식자료 교차확인'
    return '보도 단계 · 엔비디아·통신사 1차 자료 후속 확인'


def clean_title(title: str, source: str) -> str:
    text = f'{title} {source}'
    if _is_digital_optimus_game(text):
        if DIGITAL_OPTIMUS_POST_ID in text or source in DIGITAL_OPTIMUS_CEO_SOURCES:
            return '머스크: Digital Optimus 게임 수행 진전…Diablo 캠페인 약 절반'
        if source in DIGITAL_OPTIMUS_TESLA_SOURCES:
            return 'Tesla Digital Optimus 게임 수행·컴퓨터 사용 성능 후속 진전'
    if _tesla_touch_patent_match(text):
        if source in TESLA_TOUCH_PATENT_OFFICIAL and TESLA_TOUCH_PATENT_GRANT.search(text) and not TESLA_TOUCH_PATENT_GRANT_DENIAL.search(text):
            return '테슬라, US 2026/0310299 A1 관련 특허 등록 상태 공식 확인'
        return TESLA_TOUCH_PATENT_TITLE
    if _is_dkt_humanoid(text):
        # clean_title receives only title + source (NOT description).
        if source in DKT_BROKER_SOURCES and re.search(
            r'8\s*월\s*말|late\s*Aug|양산\s*공급\s*시작', title, re.I
        ):
            return '정정: 디케이티, 9/9 하나증권 휴머노이드 배터리 모듈 양산 공급 시작 보도'
        stage = _dkt_stage(text, source)
        if stage == 'reported_robot_module_sop':
            return '디케이티, 휴머노이드 배터리 모듈 양산 공급 보도'
        if stage == 'official_robot_module_sop':
            return '디케이티, 휴머노이드용 배터리 모듈 양산 회사 직접 확인'
        if stage == 'official_robot_bms_contract':
            return '디케이티, 휴머노이드용 BMS 정식 공급계약 공식 확인'
    # Headlines can name Tesla/Atlas and "cylindrical" while omitting the
    # actual material and 46-series details. Do not repeat this clickbait as
    # proof of direct customer delivery.
    if (source not in DONGKUK_OFFICIAL_SOURCES and DONGKUK_NAME.search(text)
            and re.search(r'원통형|46\s*시리즈|46시리즈|cylindrical', text, re.I)
            and re.search(r'Optimus|옵티머스|Atlas|아틀라스|테슬라|Tesla|보스턴다이내믹스|Boston\s*Dynamics|휴머노이드', text, re.I)):
        return '동국산업 북미 46시리즈 소재 품질 인증…테슬라·아틀라스 직접 공급 미확인'
    if _is_dongkuk_nps(text):
        stage = _dongkuk_stage(text, source)
        if stage == 'reported_first_shipment':
            return DONGKUK_REPORT_TITLE
        if stage == 'official_first_shipment':
            return '동국산업, 북미 46시리즈 니켈도금강판 첫 출하 공식 확인'
        if stage == 'official_contract':
            return '동국산업, 북미 46시리즈 니켈도금강판 정식 공급계약'
    if _is_airan(text):
        stage = _stage(text)
        if stage == 'commercial':
            return '엔비디아 AI-RAN, Physical AI 상용계약·매출 단계 변화'
        if stage == 'field':
            return '엔비디아 AI-RAN, Physical AI 현장 실증·배치 확대'
        if stage == 'quantified':
            return '엔비디아 AI-RAN, 지연시간·처리량 정량 개선'
        return '엔비디아 AI-RAN, Physical AI 엣지 인프라 신규 변화'
    return _orig_clean_title(title, source)


def tag_for(group: str) -> str:
    if group == 'digital_optimus_games':
        return '테슬라 디지털 에이전트'
    if group == 'tesla_touch_patent':
        return '테슬라 촉각센서 특허'
    if group == 'dkt_humanoid':
        return '디케이티 휴머노이드 배터리'
    if group == 'dongkuk_nps':
        return '동국산업 46시리즈 소재'
    if group == 'airan':
        return '엔비디아AI-RAN'
    return _orig_tag_for(group)


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if topic_group(text) == 'digital_optimus_games':
        stage = _digital_optimus_stage(text, item.get('source') or '')
        if stage == 'musk_game_progress':
            return hashlib.sha256(b'digital-optimus|musk-x|2108823477071303109|games-self-report').hexdigest()
        return hashlib.sha256(
            f'digital-optimus|{stage}|{item.get("link", "")}|2026'.encode()
        ).hexdigest()
    if topic_group(text) == 'tesla_touch_patent':
        stage = _tesla_touch_patent_stage(text, item.get('source') or '')
        return hashlib.sha256(
            f'tesla|tactile-array|US20260310299A1|{stage}|2026-10-08'.encode()
        ).hexdigest()
    if topic_group(text) == 'dkt_humanoid':
        stage = _dkt_stage(text, item.get('source') or '')
        return hashlib.sha256(
            f'dkt|humanoid|emergency-battery-module|{stage}|2026-08|{("render-corrected-v2" if stage == "reported_robot_module_sop" else "stable")}'.encode()
        ).hexdigest()
    if topic_group(text) == 'dongkuk_nps':
        stage = _dongkuk_stage(text, item.get('source') or '')
        # Event + evidence tier, not publisher/article or unrelated robot claims.
        return hashlib.sha256(f'dongkuk-nps|north-america-46|{stage}|2026-10'.encode()).hexdigest()
    # Final semantic-key guard for Samsung SDI SolidStack humanoid milestones.
    # Later Figure/other wrappers may otherwise fall back to publisher/title keys.
    if getattr(base, '_is_sdi_solidstack_robot', lambda _t: False)(text):
        stage = base._sdi_solidstack_stage(text)
        context = base._sdi_solidstack_context(text)
        return hashlib.sha256(f"samsung-sdi|solidstack-humanoid|{stage}|{context}".encode()).hexdigest()
    if topic_group(text) != 'airan':
        return _orig_key(item)
    try:
        pub = dt.datetime.fromisoformat(item.get('published') or '')
        day = pub.astimezone(base.KST).strftime('%Y-%m-%d')
    except Exception:
        day = base.NOW.astimezone(base.KST).strftime('%Y-%m-%d')
    actors = []
    for name, pat in [
        ('tmobile', r'T-Mobile'),
        ('nokia', r'Nokia|노키아'),
        ('skt', r'SK텔레콤|SK\s*Telecom|\bSKT\b'),
        ('softbank', r'SoftBank|소프트뱅크'),
        ('nvidia', r'NVIDIA|엔비디아'),
    ]:
        if re.search(pat, text, re.I):
            actors.append(name)
    return hashlib.sha256(f"airan|{_stage(text)}|{day}|{','.join(actors)}".encode()).hexdigest()


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    digital = next((x for x in candidates if x.get('group') == 'digital_optimus_games'), None)
    if digital and not any(x.get('key') == digital.get('key') for x in chosen):
        chosen = ([digital, *chosen] if len(chosen) < limit else [digital, *chosen[:-1]])
    patent = next((x for x in candidates if x.get('group') == 'tesla_touch_patent'), None)
    if patent and not any(x.get('key') == patent.get('key') for x in chosen):
        chosen = ([patent, *chosen] if len(chosen) < limit else [patent, *chosen[:-1]])
    dkt = next((x for x in candidates if x.get('group') == 'dkt_humanoid'), None)
    if dkt and not any(x.get('key') == dkt.get('key') for x in chosen):
        chosen = ([dkt, *chosen] if len(chosen) < limit else [dkt, *chosen[:-1]])
    dongkuk = next((x for x in candidates if x.get('group') == 'dongkuk_nps'), None)
    if dongkuk and not any(x.get('key') == dongkuk.get('key') for x in chosen):
        chosen = ([dongkuk, *chosen] if len(chosen) < limit else [dongkuk, *chosen[:-1]])
    airan = next((x for x in candidates if x.get('group') == 'airan'), None)
    if not airan or any(x.get('key') == airan.get('key') for x in chosen):
        return chosen
    if len(chosen) < limit:
        return [airan, *chosen]
    return [airan, *chosen[:-1]]


base.topic_group = topic_group
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.clean_title = clean_title
base.tag_for = tag_for
base.key = key
base.select_diverse = select_diverse


def _finalize_airan_criteria() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    marker = '<b>판정 기준</b>'
    if marker in text:
        body = text.split(marker, 1)[0].rstrip()
        text = (
            body
            + '\n'
            + '<b>판정 기준</b>  실적·수급·시간표를 바꾸는 새 사실만 알림. '
              '단순 주가·ETF·테마 반복은 제외.'
        )
    base.ALERT_PATH.write_text(text.strip(), encoding='utf-8')


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    qty.current.opt.current.fig.legacy.repair_pending_seen(pre_state)
    qty.current.opt._finalize_alert_text()
    qty.current._append_value_estimate()
    qty.enrich_quantity_values()
    _finalize_airan_criteria()

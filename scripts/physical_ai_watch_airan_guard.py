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



# Counterpoint humanoid BRAIN-DRAM demand, 2026-10-10 primary-source forecast.
# 19/39 GB are a blended DRAM forecast PER robot, not installed production
# measurements, NAND capacity, HBM capacity, or a confirmed OEM memory order.
HUMANOID_DRAM_RECOVERY = 'DIRECT_COUNTERPOINT_HUMANOID_BRAIN_DRAM_20261010_19GB_39GB'
HUMANOID_DRAM_URL = 'https://counterpointresearch.com/ko/insights/robot-dram-demand-samsung-sk-hynix'
HUMANOID_DRAM_OFFICIAL = {'Counterpoint Research', '카운터포인트리서치', 'Counterpoint'}
HUMANOID_DRAM_FORECAST_REVISION = re.compile(
    r'(?:revised?|revision|revises?|raises?\s+forecast|cuts?\s+forecast|'
    r'전망\s*(?:상향|하향|수정|변경)|전망치\s*(?:상향|하향|수정|변경))',
    re.I,
)
HUMANOID_DRAM_COMPANY = re.compile(r'Counterpoint|카운터포인트', re.I)
HUMANOID_DRAM_SUBJECT = re.compile(r'휴머노이드|humanoid|robot(?:s|ic)?|로봇', re.I)
HUMANOID_DRAM_MEMORY = re.compile(r'DRAM|D\s*램|디램|LPDDR|저전력\s*메모리', re.I)

# A signed named-robot OEM low-power DRAM deal is a stronger FUTURE
# upgrade than a market forecast. Press speculation or a loose MOU is not.
HUMANOID_DRAM_VENDOR_SOURCES = {
    '삼성전자', 'Samsung Electronics',
    'SK하이닉스', 'SK hynix',
    '마이크론', 'Micron', 'Micron Technology',
}
HUMANOID_DRAM_VENDOR = re.compile(
    r'삼성전자|Samsung\s*Electronics|SK\s*hynix|SK하이닉스|'
    r'Micron(?:\s*Technology)?|마이크론', re.I
)
HUMANOID_DRAM_NAMED_BUYER = re.compile(
    r'NVIDIA|엔비디아|Tesla|테슬라|XPENG|샤오펑|Boston\s*Dynamics|'
    r'보스턴다이내믹스|Agility\s*Robotics|Unitree|유니트리|Figure\s*AI|피겨',
    re.I
)
HUMANOID_DRAM_SIGNED_ORDER = re.compile(
    r'(?:(?:정식|확정|양산)\s*)?(?:공급|납품|구매)\s*계약\s*(?:체결|확정)|'
    r'(?:(?:양산|초도)\s*)?(?:첫\s*)?출하\s*(?:시작|개시|완료)|'
    r'signed\s+(?:(?:production|supply)\s+)?(?:purchase|supply)\s+(?:agreement|contract)|'
    r'first\s+(?:production\s+)?shipments?\s+(?:began|started|completed)',
    re.I
)
HUMANOID_DRAM_UNCONFIRMED_ORDER = re.compile(
    r'(?:계약|납품|수주)\s*(?:추진|검토|논의|예정|미확정|설)|'
    r'(?:아직|미)\s*(?:계약|수주)|rumou?r|unconfirmed|planned|'
    r'not\s+(?:yet\s+)?(?:signed|confirmed)',
    re.I
)


def _humanoid_dram_oem_order(text: str) -> bool:
    return bool(
        HUMANOID_DRAM_VENDOR.search(text)
        and HUMANOID_DRAM_NAMED_BUYER.search(text)
        and HUMANOID_DRAM_SIGNED_ORDER.search(text)
        and not HUMANOID_DRAM_UNCONFIRMED_ORDER.search(text)
    )

HUMANOID_DRAM_19 = re.compile(r'(?<!\d)19\s*(?:GB|기가\s*바이트)', re.I)
HUMANOID_DRAM_39 = re.compile(r'(?<!\d)39\s*(?:GB|기가\s*바이트)', re.I)
HUMANOID_DRAM_8300 = re.compile(r'(?<!\d)8[,]?\s*300\s*(?:Tbit|테라\s*비트)', re.I)
HUMANOID_DRAM_172000 = re.compile(r'(?<!\d)172[,]?\s*000\s*(?:Tbit|테라\s*비트)|17\s*만\s*2[,]?\s*000\s*(?:Tbit|테라\s*비트)', re.I)
HUMANOID_DRAM_BASELINE = (
    '카운터포인트리서치: 휴머노이드 두뇌용 D램 19GB→39GB, '
    '산업 총량 8,300→172,000Tbit 전망'
)


def _is_humanoid_dram(text: str) -> bool:
    if not (HUMANOID_DRAM_SUBJECT.search(text) and HUMANOID_DRAM_MEMORY.search(text)):
        return False
    return bool(
        HUMANOID_DRAM_COMPANY.search(text)
        or (HUMANOID_DRAM_19.search(text) and HUMANOID_DRAM_39.search(text))
        or _humanoid_dram_oem_order(text)
    )


def _humanoid_dram_stage(text: str, source: str = '') -> str:
    if not _is_humanoid_dram(text):
        return ''
    if source in HUMANOID_DRAM_VENDOR_SOURCES and _humanoid_dram_oem_order(text):
        return 'confirmed_named_oem_order'
    if (source in HUMANOID_DRAM_OFFICIAL
            and HUMANOID_DRAM_FORECAST_REVISION.search(text)
            and (re.search(r'2030', text) and re.search(r'Tbit|테라\s*비트|GB', text, re.I))):
        return 'official_forecast_revision'
    if ((HUMANOID_DRAM_19.search(text) and HUMANOID_DRAM_39.search(text))
            and (HUMANOID_DRAM_8300.search(text)
                 and HUMANOID_DRAM_172000.search(text)
                 or HUMANOID_DRAM_COMPANY.search(text))):
        return 'initial_research_forecast'
    return 'background'


def _humanoid_dram_recovery() -> list[dict]:
    # The research note reports a DATE (2026-10-10), not a verified time.
    # published=None prevents manufacturing a publication hour.
    # Historical recovery expires, so dedup-state rotation cannot replay news.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 18):
        return []
    return [{
        'title': HUMANOID_DRAM_BASELINE,
        'link': HUMANOID_DRAM_URL,
        'description': (
            '카운터포인트리서치 2026-10-10 공식 휴머노이드 로봇 인사이트 기준: '
            '2026년 로봇 한 대당 블렌디드 D램 평균 19GB, 산업 연간 총수요 '
            '약 8,300Tbit 전망; 2030년 평균 39GB, 산업 연간 총수요 '
            '약 172,000Tbit 전망. 이는 각 연도 전체 출하 제품의 메모리 '
            '비트 수요 예측이지 현재 양산품 측정이나 확정 고객 주문이 아니다. '
            '2026년→2030년 총량 약 20.72배, 대당 용량 약 2.05배. '
            '십진 환산 1Tbit=125GB를 적용하면 연간 D램 총량 '
            '2026년 1,037,500GB, 2030년 21,500,000GB. '
            '연간 출하대수 단순 역산은 각각 약 54,605대·551,282대이지만 '
            '실제 OEM 출하량 직접 발표가 아니며 예측 평균의 혼합제품 영향이 있다. '
            '가격 미공개로 실제 원화 매출 추정 금지. '
            '원화 민감도: 출하 D램 1GB당 실현 평균판매단가가 1,000원 달라질 경우 '
            '2030년 산업 전체 가상 매출 변동은 215억원, 2026년은 '
            '약 10억 3,750만원이며 이것은 실제 판매가격·계약금액 예측이 아니다. '
            '저전력 D램 LPDDR과 낸드 저장장치는 서로 분리하고 '
            '고대역폭메모리 HBM도 로봇 탑재량 39GB에 더하지 않는다. '
            'Micron CEO가 말한 향후 휴머노이드 200GB 이상 메모리 가능성은 '
            '별도 고사양 시나리오이지 본 조사기관의 2030 평균과 같지 않다. '
            '고객사별 공급·출하·실제 평균판매단가·수율·이익률은 공개되지 않았다. '
            '카운터포인트 원문·연합뉴스·뉴스1 보도로 숫자를 교차확인했다.'
        ),
        'source': '카운터포인트리서치',
        'published': None,
        'direct_recovery': True,
        'robot_memory_forecast': True,
    }]



# 2026-10-10 X Takeover: Musk discussed fine-motor force/precision and
# retrospectively described a 2025 Chinese motor-magnet export restriction.
# This is a new management DISCLOSURE of an old disruption, not a new V3 delay.
OPTIMUS_HAND_MAGNET_RECOVERY = 'DIRECT_XTAKEOVER_OPTIMUS_HAND_MAGNET_RETROSPECTIVE_20261010'
OPTIMUS_HAND_MAGNET_URL = 'https://x.com/tslaming/status/2109093140477231416'
OPTIMUS_HAND_MAGNET_ID = re.compile(
    r'X\s*Takeover|XTakeover|2109093140477231416|'
    r'자석.{0,60}(?:Optimus|옵티머스)|motor\s*magnets?',
    re.I,
)
OPTIMUS_HAND_MAGNET_CEO = re.compile(r'Elon\s*Musk|일론\s*머스크|머스크', re.I)
OPTIMUS_HAND_MAGNET_PRECISION = re.compile(
    r'self[-\s]*tapping|셀프\s*태핑|나사|dexterous\s*hand|손.{0,30}정밀|precision.{0,35}force',
    re.I,
)
OPTIMUS_HAND_MAGNET_RETRO = re.compile(
    r'(?:지난해|작년|last\s*year|2025).{0,140}(?:자석|magnet)|'
    r'(?:자석|magnet).{0,120}(?:지난해|작년|last\s*year|2025)',
    re.I,
)
OPTIMUS_HAND_MAGNET_FRESH = re.compile(
    r'(?:new|current|additional|further|추가|새로운|이번|현재).{0,80}'
    r'(?:export\s*ban|magnet\s*ban|자석\s*수출\s*금지|생산\s*지연|일정\s*지연)|'
    r'(?:2026|2027).{0,60}(?:새로운\s*지연|추가\s*지연)',
    re.I,
)
OPTIMUS_HAND_MAGNET_SOURCES = {'Elon Musk (X Takeover)', '일론 머스크 (X Takeover)'}


def _is_optimus_hand_magnet(text: str) -> bool:
    return bool(OPTIMUS_HAND_MAGNET_ID.search(text) and
                OPTIMUS_HAND_MAGNET_CEO.search(text) and
                (OPTIMUS_HAND_MAGNET_PRECISION.search(text) or
                 re.search(r'자석|magnet', text,re.I)))


def _optimus_hand_magnet_stage(text: str, source: str = '') -> str:
    if not _is_optimus_hand_magnet(text):
        return ''
    if OPTIMUS_HAND_MAGNET_RETRO.search(text):
        return 'retrospective_supply_bottleneck' if source in OPTIMUS_HAND_MAGNET_SOURCES else 'background'
    # Do not infer new production slippage merely from a hand/rare-earth mention.
    if OPTIMUS_HAND_MAGNET_FRESH.search(text) and source in OPTIMUS_HAND_MAGNET_SOURCES:
        return 'new_schedule_warning'
    return 'background'


def _optimus_hand_magnet_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,16):
        return []
    return [{
        'title': 'X Takeover 머스크 Optimus 손 정밀·힘 제어와 자석 수출 제한 2025년 차질 회고',
        'link': OPTIMUS_HAND_MAGNET_URL,
        'description': (
            '2026년 10월 10일 X Takeover 원격 대담: 일론 머스크는 '
            '작은 셀프태핑 나사를 나무에 박는 예를 들며 손의 정밀 조작과 '
            '축방향 힘을 동시에 제어하는 난도를 설명했다. '
            '처음 보는 작업에 적응하는 범용성은 목표이며 달성 시연이 아니다. '
            '2025년 중국 모터용 희토류 영구자석 수출 제한으로 '
            'Optimus 개발이 2~3개월 지연됐었다고 회고했다. '
            '이는 2026년 10월 신규 2~3개월 생산 지연 발표가 아니다. '
            '2026년 2분기 실적발표에서 이미 설명한 '
            '신규 로봇 부품 공급망 구축·내재화의 실제 실패 사례에 해당한다. '
            'Tesla의 실제 신규 부품 주문, 미국 영구자석 신규 증설 금액, '
            '희토류 자석 공급사 선정, V3 새 공개일 또는 납품 계약은 '
            '이번 대담에서 발표된 사실로 확인되지 않았다. '
            '실제 원대담 전체를 직접 재생·전사하지 못했고 주최 행사자료, '
            '대담 영상 재게시, 2026-10-11 The Last Daily의 구체적 인용 '
            '및 Tesla 2분기 실적발표로 교차확인했다.'
        ),
        'source': 'Elon Musk (X Takeover)',
        'published': None,
        'direct_recovery': True,
        'historical_2025_supply_delay': True,
    }]


# Verified Benchmark Q3-2026 LFP 314Ah EXW/CIF price observation; tariff
# 40.9% is media's hypothetical illustration, not customs clearance proof.
LFP_NA_CIF_PRICE_RECOVERY = 'DIRECT_BMI_Q3_2026_LFP314_EXW5162_CIF6199'
LFP_NA_CIF_PRICE_URL = (
    'https://source.benchmarkminerals.com/article/'
    'lithium-cost-pass-through-drives-volatile-quarter-for-energy-storage-cells-cell-price-review-q3-2026'
)
LFP_NA_CIF_PRIMARY = {'Benchmark Mineral Intelligence','Benchmark Minerals','BMI'}
LFP_NA_CIF_TRUSTED = LFP_NA_CIF_PRIMARY | {'디일렉','THE ELEC','The Elec'}
LFP_NA_314 = re.compile(r'314\s*(?:Ah|암페어시)',re.I)
LFP_NA_LFP = re.compile(r'LFP|리튬인산철|lithium\s*iron\s*phosphate',re.I)
LFP_NA_LOC = re.compile(r'북미|North\s*America|미국|CIF\s*NA',re.I)
LFP_NA_EXW = re.compile(r'(?<!\d)51[.]62(?!\d)')
LFP_NA_PRICE = re.compile(r'(?<!\d)61[.]99(?!\d)')
BATT_ROADMAP_POLICY = re.compile(
    r'배터리\s*산업기술\s*로드맵|K[-\s]*배터리.{0,60}(?:초협력|나트륨|전고체)|'
    r'초협력\s*생태계.{0,40}배터리',re.I
)
BATT_POLICY_SIZE = re.compile(
    r'3[,]?000\s*억|4[,]?000\s*억|3000\s*억|4000\s*억|8\s*조|'
    r'2027[~～\-]2031|27[~～\-]31',re.I
)
EV_ESS_OLD_NEWS = re.compile(
    r'(?:275\s*GWh|275기가와트시).{0,160}(?:182\s*GWh|182기가와트시)|'
    r'(?:182\s*GWh|182기가와트시).{0,160}(?:275\s*GWh|275기가와트시)|'
    r'1[,]?000\s*억\s*달러.{0,100}(?:배터리|ESS)|'
    r'(?:배터리|ESS).{0,100}1[,]?000\s*억\s*달러',re.I
)



# Editorial earnings-expectation rewrites are NOT actual quarterly results,
# contracts, price observations, utilization, or customer orders. A live
# run erroneously sent an Oct 12 "3분기 실적 기대감↑" story alongside the
# true 314Ah CIF measurement. Filter this before inherited ESS scoring.

STOCK_ONLY_REACTION = re.compile(
    r'^\s*(?:\[(?:특징주|급등주|급락주|증시)\]|【(?:特征股|股价)】)|'
    r'(?:주가|종목|주식).{0,30}(?:강세|상승|급등|약세|하락|급락)|'
    r'(?:강세|상승|급등|약세|하락|급락).{0,30}(?:주가|주식)|'
    # 2026-10-13 real failure: "24만4500원…양산 기대 속 4.86% 조정"
    # was scored as a supply-chain alert with no new order or shipment.
    r'^\s*\d+(?:,\d{3})*(?:만\d{1,4})?원.{0,100}'
    r'\d+(?:\.\d+)?\s*%\s*(?:조정|하락|상승|급등|반등|급락|등락)|'
    r'^\s*\d+(?:\.\d+)?\s*%\s*(?:조정|하락|상승|급등|반등|급락|등락)|'
    # Run #584 item 1: "삼성SDI 5% 오르며 2차전지株 강세" had a
    # price-action verb instead of "주가"/"상승". It is not new business.
    r'\d+(?:\.\d+)?\s*%\s*(?:대\s*)?(?:오르|올랐|내리|내렸|뛰|반등|상승|강세|급등|하락|급락)|'
    r'주가.{0,55}(?:오르|올랐|내리|내렸|뛰어|폭등|급등|강세|약세|하락|급락)',
    re.I,
)
EDITORIAL_ONLY_HEADLINE = re.compile(
    r'^\s*\[\s*(?:심층\s*분석|기획\s*진단|증시\s*진단)\s*\]', re.I
)
EDITORIAL_MATERIAL_EVENT = re.compile(
    r'신규\s*(?:수주|계약|투자|실증\s*승인)|'
    r'공급\s*계약\s*체결|고객\s*계약\s*확정|'
    r'실제\s*(?:배치|출하)\s*(?:개시|완료)|'
    r'양산\s*(?:개시|시작)|공식\s*실적\s*발표', re.I
)



# Editorial source quality != a commercial event. The same ESS sector theme
# must not be elevated by a target price, bullish headline, or rewritten
# "Japan ESS market" positioning piece. This pre-score filter is shared by
# all topic groups; a genuine dated, explicit binding award is exempt.
OCT15_PRICE_TARGET_HEADLINE = re.compile(
    r'목표\s*(?:주가|가|가격)|적정\s*주가|price\s*target|'
    r'target\s*price|리포트\s*브리핑|투자\s*의견\s*상향',
    re.I,
)
OCT15_JAPAN_ESS_MARKET = re.compile(
    r'일본|日\s*ESS|日\s*배터리|Japanese?\s*(?:ESS|BESS|battery)',
    re.I,
)
OCT15_EDITORIAL_NARRATIVE = re.compile(
    r'대공세|선봉|투트랙|공략|판도\s*변화|수혜\s*기대|'
    r'기대감|주도권\s*(?:쟁탈|탈환)|경쟁력\s*부각',
    re.I,
)
OCT15_REAL_EVENT_HEADLINE = re.compile(
    r'(?:신규|정식|구속력\s*있는).{0,45}'
    r'(?:공급\s*계약|구매\s*계약|발주|수주|설비\s*투자\s*결정)|'
    r'(?:공급|구매)\s*계약.{0,15}(?:체결|서명|확정)|'
    r'(?:초도|첫|실제)\s*(?:출하|납품|양산|가동)\s*(?:개시|완료|시작)|'
    r'공식\s*실적\s*발표|잠정\s*실적\s*공시',
    re.I,
)


def _is_oct15_market_noise(item: dict) -> bool:
    if item.get('direct_recovery') or item.get('oct15_high_signal_key'):
        return False
    headline = item.get('title') or ''
    source = item.get('source') or ''
    if source in base.OFFICIAL_OR_PRIMARY:
        return False
    # Only a genuine explicit new commercial event can override editorial
    # price commentary, never the vague "expects big orders" in its body.
    if OCT15_REAL_EVENT_HEADLINE.search(headline):
        return False
    if OCT15_PRICE_TARGET_HEADLINE.search(headline):
        return True
    if (OCT15_JAPAN_ESS_MARKET.search(headline)
            and OCT15_EDITORIAL_NARRATIVE.search(headline)
            and re.search(r'ESS|BESS|에너지\s*저장|배터리|battery', headline, re.I)):
        return True
    return False


def _is_stock_reaction_only(item: dict) -> bool:
    if item.get('correction_for_false_stock_alerts') and item.get('source') == 'VNET':
        return False  # Explicit one-time correction from issuer, not a market story.
    headline = item.get('title') or ''
    source = item.get('source') or ''
    # Reliable publishers may report stock movement: editorial trust does
    # not turn a price reaction into a new order or earnings release.
    if source in base.OFFICIAL_OR_PRIMARY:
        return False
    if EDITORIAL_ONLY_HEADLINE.search(headline) and not EDITORIAL_MATERIAL_EVENT.search(headline):
        return True  # Commentary is not a dated commercial/operational milestone.
    if STOCK_ONLY_REACTION.search(headline):
        # Retain a headline with a genuinely new explicit commercial event;
        # stock-price movement alone is never enough to send the alert.
        return not EDITORIAL_MATERIAL_EVENT.search(headline)
    return False


ESS_GENERIC_DEMAND_HEADLINE = re.compile(
    r'(?:ESS|BESS|에너지저장|배터리|battery).{0,38}'
    r'수요\s*(?:폭증|급증|폭발|확대|성장)|'
    r'수요\s*(?:폭증|급증|폭발|확대).{0,38}'
    r'(?:ESS|BESS|에너지저장|배터리|battery)|'
    r'전고체.{0,85}(?:잡는\s*자|시장.{0,18}(?:선점|경쟁)|'
    r'기술.{0,18}경쟁|주도권.{0,18}경쟁|선점\s*경쟁\s*치열)',
    re.I,
)
ESS_CONCRETE_NEW_EVENT = re.compile(
    r'(?:신규|정식|첫|초도|확정|최초).{0,50}'
    r'(?:공급\s*계약|수주|발주|납품|출하|양산|실증\s*승인)|'
    r'(?:공급|구매)\s*계약\s*체결|'
    r'실제\s*(?:출하|생산|설치)\s*(?:완료|개시)',
    re.I,
)


def _is_generic_ess_demand_story(item: dict) -> bool:
    title = item.get('title') or ''
    if item.get('source') in base.OFFICIAL_OR_PRIMARY:
        return False
    # Message 214 was a recycled market narrative, not a signed order.
    if ESS_GENERIC_DEMAND_HEADLINE.search(title):
        return not ESS_CONCRETE_NEW_EVENT.search(title)
    return False


ESS_EXPECTATION_ONLY_TITLE = re.compile(
    r'실적.{0,25}기대감|실적.{0,20}기대\s*(?:↑|증가|확대|커져)|'
    r'3\s*분기.{0,28}기대감|분기.{0,35}실적.{0,20}전망',
    re.I,
)
ESS_EXPECTATION_TOPIC = re.compile(
    r'ESS|BESS|에너지저장|LFP|배터리|battery', re.I
)
ESS_OFFICIAL_QUARTERLY = re.compile(
    r'잠정\s*실적\s*(?:발표|공시)|(?:분기|누적)\s*실적\s*확정|'
    r'실제\s*매출\s*(?:발표|공시)|신규\s*공급계약\s*체결|'
    r'신규\s*수주\s*공시|첫\s*출하\s*공식\s*확인|'
    r'official\s*(?:quarterly\s*)?results|binding\s*agreement',
    re.I,
)


def _is_ess_expectation_only(item: dict) -> bool:
    headline = item.get('title') or ''
    source = item.get('source') or ''
    if source in base.OFFICIAL_OR_PRIMARY:
        return False
    if not (ESS_EXPECTATION_ONLY_TITLE.search(headline)
            and ESS_EXPECTATION_TOPIC.search(headline)):
        return False
    # A headline stating a newly completed agreement or official result is
    # not the same as a news outlet's generic "3Q earnings hopes."
    return not ESS_OFFICIAL_QUARTERLY.search(headline)


def _is_lfp_na_314_price(text: str) -> bool:
    return bool(LFP_NA_314.search(text) and LFP_NA_LFP.search(text)
                and LFP_NA_LOC.search(text) and LFP_NA_EXW.search(text)
                and LFP_NA_PRICE.search(text))


def _is_2026_roadmap_rewrite(text: str) -> bool:
    return bool(BATT_ROADMAP_POLICY.search(text) and BATT_POLICY_SIZE.search(text))


def _is_legacy_ev_ess_pivot(text: str) -> bool:
    return bool(EV_ESS_OLD_NEWS.search(text) and
                re.search(r'ESS|에너지저장|BESS',text,re.I) and
                re.search(r'전기차|EV|배터리|battery',text,re.I))


def _lfp_na_price_recovery() -> list[dict]:
    # Assessment date is 2026-09; primary-source story released 2026-10-09.
    # Do not invent an exact publication time or store this as a new tax law.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,18):
        return []
    return [{
        'title': 'Benchmark 9월 314Ah LFP 가격: 중국 51.62·북미 CIF 61.99달러/kWh',
        'link': LFP_NA_CIF_PRICE_URL,
        'description': (
            '2026-10-09 Benchmark Mineral Intelligence 3분기 배터리 셀 가격평가와 '
            '2026-10-12 디일렉 교차검증. 9월 314Ah LFP 각형셀 중국 출고가격 EXW '
            '51.62 USD/kWh, 북미 도착가격 CIF 61.99 USD/kWh, 유럽 CIF '
            '59.18 USD/kWh. 중국 EXW→북미 CIF 차이 10.37달러/kWh '
            '(20.09%)는 운송·보험·거래조건 차이이고 북미 CIF에는 '
            '미국 수입관세가 아직 포함되지 않는다. '
            '디일렉 인용 최대 40.9% 관세를 CIF에 단순 곱하면 '
            '87.34391 USD/kWh이나 실제 신고세율·과세가격이 확정된 금액이 아닌 '
            '조건부 시나리오다. 1 USD=1340.88원(2026-10-12 03:20 KST 제공값) '
            '환산 시 EXW 약 69,216원/kWh, CIF 약 83,121원/kWh, '
            '관세 조건부 약 117,118원/kWh이다. '
            '1GWh=1,000,000kWh, CIF 중국산 셀 구매비용 약 831.21억원, '
            '관세 시나리오 약 1171.18억원, 추가 부담 약 339.97억원. '
            '중국 EXW→북미 CIF 격차는 GWh당 약 139.05억원, '
            '중국 EXW→관세 가정 총 격차는 GWh당 약 479.01억원이다. '
            '관세 품목분류·원산지·유효일·면제·실제 수입신고가격을 '
            '미국 USITC·CBP 자료로 추가 확인해야 하며 40.9%를 '
            '모든 수입 셀에 적용되는 법정세율이라고 단정하지 않는다. '
            '공식 HiTHIUM 314Ah 셀은 표준전압 3.2V·정격에너지 1004.8Wh지만 '
            '가격조사 대상 모두가 동일 회사·형번이라는 뜻은 아니다. '
            'LG에너지솔루션 2026년 말 북미 ESS 50GWh 이상 생산능력 목표와 '
            '삼성SDI 2028년 하반기 50GWh 이상 전망은 서로 다른 일정이다. '
            '현지 셀 제조원가·고객 수주가격·공급계약·수율·보험은 '
            'CIF 가격 관측만으로 확정할 수 없다.'
        ),
        'source': 'Benchmark Mineral Intelligence',
        'published': None,
        'direct_recovery': True,
        'price_observation': True,
    }]



# VNET's strategic shareholder links and AIDC energy collaboration do NOT
# constitute CATL sodium-ion ESS captive purchase orders.
VNET_EQUITY_RECOVERY = 'DIRECT_VNET_PJ_MILLENNIUM_CATL_AFFILIATE_20260921'
VNET_OFFICIAL = {'VNET', 'VNET Group', 'VNET IR', 'CATL', '宁德时代'}
VNET_ID = re.compile(r'VNET|21Vianet|世纪互联',re.I)
VNET_CATL = re.compile(r'CATL|宁德时代|닝더스다이',re.I)
VNET_EQUITY_CLOSED = re.compile(
    r'650[,]?424[,]?192.{0,280}38[.]1\s*%|'
    r'38[.]1\s*%.{0,280}(?:September 21|2026-09-21|closing|종결|완료)',re.I)
VNET_SODIUM = re.compile(r'sodium[-\s]*ion|나트륨이온|钠离子',re.I)
VNET_ORDER = re.compile(r'(?:정식\s*)?(?:공급계약|구매계약)\s*체결|'
                        r'signed\s+(?:binding\s+)?(?:supply|purchase)\s+(?:contract|agreement)',re.I)
VNET_ESS_QTY = re.compile(r'\d+(?:[.]\d+)?\s*(?:GWh|MWh)',re.I)
VNET_HYPERSTRONG_BASE = re.compile(r'(?:HyperStrong|海博思创).{0,250}60\s*GWh|60\s*GWh.{0,250}(?:HyperStrong|海博思创)',re.I)


def _is_vnet_catl(text: str) -> bool:
    return bool(VNET_ID.search(text) and VNET_CATL.search(text))


def _vnet_catl_stage(text: str, source: str = '') -> str:
    if not _is_vnet_catl(text) or source not in VNET_OFFICIAL:
        return 'background'
    if (VNET_SODIUM.search(text) and VNET_ORDER.search(text)
            and VNET_ESS_QTY.search(text) and not VNET_HYPERSTRONG_BASE.search(text)
            and re.search(r'VNET.{0,230}(?:sodium|나트륨).{0,230}(?:GWh|MWh)',text,re.I)):
        return 'signed_vnet_sodium_contract'
    if VNET_EQUITY_CLOSED.search(text):
        return 'equity_closing_baseline_recovery'
    return 'background'


def _vnet_equity_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,19):
        return []
    return [{
        'title': '정정: 10/12 ESS 주가 상승 기사 2건 제외 — CATL 관계사·VNET 9/21 지분거래만 확인',
        'link': 'https://ir.vnet.com/news-releases/news-release-details/vnet-announces-closing-previously-announced-strategic-investment',
        'description': (
            '앞서 발송한 Telegram message_id=208의 1번(아이뉴스24)과 3번(이투데이)은 주가 반응·ESS 수주 기대감 기사이므로 신규 계약이나 실적 고신호가 아니었습니다. 두 건은 제외하며 이후 같은 성격의 뉴스는 조용히 무시합니다. 2번 VNET 사실관계는 유지합니다. ' 
            'VNET 2026-09-21 회사 보도자료·미 SEC 공시: CATL의 비지배·비연결 '
            '관계사와 연관된 PJ Millennium 투자기구가 기존 주주로부터 '
            'Class A 주식 650,424,192주를 취득 완료해 38.1%를 보유한다. '
            '이는 CATL 직접 보유나 VNET 신주 발행을 통한 신규 자금 조달이 아니다. '
            '주당 1.4486달러 기준 약 9억 4,220만달러의 기존 주주간 지분 양도거래다. '
            'CATL과 VNET는 별도로 8월 데이터센터 전력·컴퓨팅 통합 전략협력을 체결했다. '
            '나트륨이온 ESS 독점·전속 구매계약, 발주 물량, 신규 시공·운영 매출은 '
            '공식자료에서 확인되지 않았다. VNET 889MW는 2025년 12월 말 '
            '도매 IDC 가동 용량이며, 2026년 6월 말은 1,007MW 가동·744MW 고객 사용이다. '
            '이 수치는 나트륨 ESS 설치 MWh가 아니다. '
            'CATL–HyperStrong 3년 60GWh 나트륨 공급 협력은 '
            '2026년 4월 27일 별도 당사자간 계약이며 VNET 물량으로 합산하지 않는다.'
        ),
        'source':'VNET',
        'published':None,
        'direct_recovery':True,
        'historical_missed_equity_event':True,
        'correction_for_false_stock_alerts':True,
    }]



# FUNDA's 2026-10-12 research note supplies an anonymous channel-check
# 3–4x estimate for 7–13B robot post-training jobs, NOT independent,
# same-hardware GPU-hour measurements or incremental GPU orders.
# Extracted original article text was inspected via web search results;
# opening its URL directly failed. It remains a silent research baseline.
# Later first-party actual robot post-training GPU-hour disclosures may alert.
ROBOT_POSTTRAIN_FUNDA_URL = 'https://fundaai.substack.com/p/deepphysical-ai-from-the-robot-data'
ROBOT_POSTTRAIN_PRIMARY = {
    'NVIDIA', 'NVIDIA Research', 'NVIDIA Technical Blog', 'Tesla', 'Tesla AI',
    'Google DeepMind', 'Physical Intelligence', 'Skild AI', 'Figure AI',
}
ROBOT_POSTTRAIN_ROBOT = re.compile(
    r'\brobot(?:ics|ic|s)?\b|\bhumanoid\b|\bVLA\b|'
    r'로봇|휴머노이드|시각.언어.행동|피지컬\s*AI', re.I
)
ROBOT_POSTTRAIN_TOPIC = re.compile(
    r'post[-\s]*train(?:ing)?|fine[-\s]*tun(?:ing|e)|'
    r'사후\s*학습|미세\s*조정', re.I
)
ROBOT_POSTTRAIN_GPU = re.compile(r'\bGPU(?:s)?\b|\bH100\b|\bB200\b|가속기',re.I)
ROBOT_POSTTRAIN_FUNDA = re.compile(r'\bFUNDA(?:AI)?\b|fundaai\.substack',re.I)
ROBOT_POSTTRAIN_RATIO = re.compile(
    r'3\s*[-~–—]\s*4\s*(?:x|배|times?)|'
    r'(?:three|3)\s*to\s*(?:four|4)\s*times',re.I
)
ROBOT_POSTTRAIN_GPU_HOURS = re.compile(
    r'\d[\d,]*\s*(?:H100|B200)?\s*'
    r'(?:GPU[-\s]*hours?|GPUh|accelerator[-\s]*hours?|'
    r'GPU\s*시간|GPU시간|가속기\s*시간)',re.I
)
ROBOT_POSTTRAIN_MEASURED = re.compile(
    # "reported", "benchmark", "verified" or "official announcement"
    # alone do NOT prove that GPU-hours were actually metered.
    r'\bmeasured\b|\binstrumented\b|\bbenchmarked\b|'
    r'\bmeasurement\s+(?:results?|data)\b|'
    r'GPU[-\s]*hours?\s*(?:were\s*)?(?:measured|recorded)|'
    r'실측|GPU\s*시간\s*(?:측정|계측)|'
    r'측정\s*(?:결과|자료|데이터|기록)|실제\s*계측',re.I
)
ROBOT_POSTTRAIN_DENIAL = re.compile(
    r'not\s+(?:yet\s+)?measured|no\s+GPU[-\s]*hours?\s+disclosed|'
    r'\bno\s+(?:independent\s+)?(?:measured|metered|actual)\b|'
    r'(?:without|no|not)\s+(?:published\s+)?(?:measured|metered)\s+(?:training\s+)?(?:logs?|results?)|'
    r'(?:published|released)\s+no\s+(?:measured|metered)\b|'
    r'GPU\s*시간\s*(?:미공개|미확인)|실측\s*(?:없음|미확인)',re.I
)

def _is_robot_posttrain_compute(text: str) -> bool:
    return bool(
        ROBOT_POSTTRAIN_ROBOT.search(text)
        and ROBOT_POSTTRAIN_TOPIC.search(text)
        and ROBOT_POSTTRAIN_GPU.search(text)
        and (ROBOT_POSTTRAIN_FUNDA.search(text)
             or ROBOT_POSTTRAIN_GPU_HOURS.search(text))
    )

def _robot_posttrain_stage(text: str, source: str = '') -> str:
    if not _is_robot_posttrain_compute(text):
        return ''
    if (source in ROBOT_POSTTRAIN_PRIMARY
            and not re.search(r'not a post[- ]training benchmark|사후학습 수치가 아님', text, re.I)
            and ROBOT_POSTTRAIN_GPU_HOURS.search(text)
            and ROBOT_POSTTRAIN_MEASURED.search(text)
            and not ROBOT_POSTTRAIN_DENIAL.search(text)):
        return 'official_measured_posttraining'
    if ROBOT_POSTTRAIN_FUNDA.search(text) and ROBOT_POSTTRAIN_RATIO.search(text):
        return 'funda_research_estimate_baseline'
    return 'unverified_or_general'



# 2026-10-13 Korean industrial-sandbox approval: Robros 20 planned
# humanoids across four NAMED trial sites. Regulatory approval is not
# commissioning, unit sales, operational KPI or blanket safety-law repeal.
ROBROS_PILOT_20261013 = 'DIRECT_ROBROS_20261013_INDUSTRIAL_SANDBOX_20_APPROVAL'
ROBROS_ID = re.compile(r'로브로스|\bRobros\b', re.I)
ROBROS_ROBOT = re.compile(r'휴머노이드|humanoid|이족보행|이동형\s*로봇|이그리스|IGRIS', re.I)
ROBROS_CLIENTS = re.compile(
    r'네패스|Nepes|성우하이텍|Sungwoo|HD현대삼호|HD\s*Hyundai\s*Samho|'
    r'딜리버리랩|Delivery\s*Lab', re.I
)
ROBROS_TWENTY = re.compile(r'(?:\b20\s*(?:대|기|units?|robots?)|스무\s*대)', re.I)
ROBROS_PILOT_APPROVAL = re.compile(
    r'(?:실증\s*특례|규제\s*특례|규제\s*샌드박스).{0,100}'
    r'(?:승인|허용|의결|approved?|authorized?)|'
    r'(?:승인|허용|의결|approved?).{0,90}(?:실증\s*특례|규제\s*특례|'
    r'실증\s*사업|industrial\s*pilot)', re.I
)
ROBROS_DEPLOYED = re.compile(
    r'(?:(?:현장|공장|실증\s*현장).{0,35})?'
    r'(?:실제\s*)?(?:투입|배치|설치|운영|가동)\s*(?:시작|개시|완료|확인)|'
    r'actual\s+(?:deployment|installation|commissioning)\s+(?:began|completed)|'
    r'(?:began|started)\s+(?:operating|work)\s+at\s+(?:site|factory)',
    re.I,
)
ROBROS_MEASURED = re.compile(
    r'(?:작업\s*성공률|사람\s*개입률|직행\s*수율|가동률|작업\s*사이클|'
    r'cycle\s*time|task\s*success\s*rate|intervention\s*rate|uptime).{0,65}'
    r'(?:\d+(?:\.\d+)?\s*(?:%|초|분|시간|s|sec|min)|실측|측정|recorded)|'
    r'(?:실측|측정|recorded).{0,65}'
    r'(?:작업\s*성공률|사람\s*개입률|가동률|cycle\s*time)',
    re.I,
)
ROBROS_ORDER = re.compile(
    r'(?:정식\s*)?(?:납품|공급|구매|양산)\s*(?:계약|발주)\s*(?:체결|확정|완료)|'
    r'(?:유상|추가|후속)\s*(?:납품|수주|구매|발주)\s*(?:완료|확정|체결)|'
    r'(?:signed|firm)\s+(?:supply|purchase|production)\s+(?:contract|order)',
    re.I,
)
ROBROS_REVERSE = re.compile(
    r'(?:실증|특례|승인|허가|운영).{0,80}(?:취소|철회|중단|정지|연기|revoked|cancelled|suspended)|'
    r'(?:취소|철회|중단|정지|연기).{0,80}(?:실증|특례|승인|운영)',
    re.I,
)
ROBROS_OFFICIAL = {
    '로브로스','Robros','네패스','Nepes','성우하이텍',
    'HD현대삼호','딜리버리랩','산업통상부','한국산업기술진흥원',
}
ROBROS_NEWS = {'파이낸셜뉴스','머니투데이','이투데이','연합뉴스','뉴시스'}
ROBROS_PILOT_GROUP = 'robros_industrial_sandbox'


def _is_robros_pilot(text: str) -> bool:
    return bool(
        ROBROS_ID.search(text) and ROBROS_ROBOT.search(text)
        and ROBROS_CLIENTS.search(text)
        and (ROBROS_PILOT_APPROVAL.search(text) or ROBROS_DEPLOYED.search(text)
             or ROBROS_MEASURED.search(text) or ROBROS_ORDER.search(text)
             or ROBROS_REVERSE.search(text)
             or ROBROS_TWENTY.search(text))
    )


def _robros_pilot_stage(text: str, source: str = '') -> str:
    if not _is_robros_pilot(text):
        return ''
    # A first-party dated operational milestone can exceed the permit.
    if source in ROBROS_OFFICIAL:
        if ROBROS_REVERSE.search(text):
            return 'official_pilot_reversal'
        if ROBROS_MEASURED.search(text):
            return 'official_site_kpi'
        if ROBROS_ORDER.search(text) and not re.search(
            r'계약\s*(?:전|미확정)|수주\s*(?:전|미확인)|'
            r'not\s+(?:a\s+)?(?:signed|firm)\s+contract',text,re.I
        ):
            return 'official_site_contract'
        if ROBROS_DEPLOYED.search(text):
            return 'official_site_deployment'
    if (source in (ROBROS_NEWS | ROBROS_OFFICIAL)
            and ROBROS_TWENTY.search(text)
            and ROBROS_PILOT_APPROVAL.search(text)):
        return 'approved_pilot_report'
    return 'existing_or_unverified_baseline'


def _robros_pilot_recovery() -> list[dict]:
    # Industrial Ministry's 2026-10-13 14-page original press release
    # was subsequently supplied by the user and checked against Yonhap.
    # Its 15:00 embargo is NOT proof of site deployment or revenue.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,20):
        return []
    return [{
        'title': '산업통상부 규제특례 승인: 로브로스 휴머노이드 20대 제조·물류 현장 실증',
        'link': 'https://www.fnnews.com/news/202610131103564249',
        'description': (
            '2026-10-13 15:00 KST 산업통상부 보도자료 보도시점. '
            '산업통상부 14쪽 공식 보도자료 2~3·9쪽을 사용자가 첨부하여 '
            '공식 실증특례 승인과 위험성평가·위험 감소 조치 전제 조건을 직접 확인. '
            '파이낸셜뉴스(15:00)·연합뉴스(15:55) 보도와 교차 검증. '
            '로브로스 휴머노이드 20대는 네패스 반도체 후공정 부품 세척, '
            '성우하이텍 자동차 차체부품 안착, HD현대삼호 조선 기자재 적재, '
            '딜리버리랩 냉장 물류포장체 적재 등에 실증 투입하는 계획이다. '
            '기존 산업용 로봇 안전펜스 규칙 때문에 어려웠던 사람과 로봇 '
            '혼재 공정의 지정 실증특례를 승인한 것이며 '
            '전국 공장에 대한 전면 규제 폐지나 무조건 무인 운전 허가가 아니다. '
            '정부 공식 보도자료는 직접 확인했지만 개별 허가증의 추가 부가조건 '
            '전문·실제 현장 운영일자·고객별 납품계약은 확인되지 않았다. '
            '이번 20대의 실제 현장 설치대수·계약금액·유상 납품 여부·'
            '고객별 배정수량·실증 시작일과 마감일·안전관리 조건·'
            '정부 신규 배정 예산은 미공개다. '
            '로브로스는 2026-08-19 과거 공식 홍보에서 실증용 '
            'IGRIS-C 9대 유상 공급, 누적 생산 36대·판매 18대라고 발표했으나 '
            '과거 9대와 이번 20대가 중복인지 확인되지 않아 합산 금지. '
            '확정 고객 실증 참여와 향후 부품 공급계약·유상 반복매출·'
            '정상 운영은 별도 증거로만 확인한다.'
        ),
        'source':'파이낸셜뉴스',
        'published':'2026-10-13T06:00:00+00:00',
        'direct_recovery':True,
        'regulatory_approval_news':True,
    }]



def _robros_213_214_correction() -> list[dict]:
    # One-time correction, preserving the real Robros conditional approval.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,16):
        return []
    return [{
        'title': '정정: Telegram 213·214 오탐 3건 제외, 로브로스 실증특례 20대 승인은 유효',
        'link': 'https://www.yna.co.kr/view/AKR20261013140800003',
        'description': (
            '로브로스 휴머노이드 20대 산업실증특례 승인 관련 사후 검증. '
            '산업통상부 2026-10-13 공식 14쪽 보도자료 2·3·9쪽과 연합뉴스 대조. '
            '로브로스 네패스·성우하이텍·HD현대삼호·딜리버리랩 산업현장 '
            '이동형 휴머노이드 20대 조건부 실증특례 승인은 유효. '
            '노동부 위험성평가·위험 감소조치가 전제이며 실제 배치완료·매출은 아니다. '
            '기존 Telegram message_id=213의 1번 로보티즈 4.86% 주가 조정은 '
            '신규 수주·출하가 아니므로 고신호에서 제외한다. '
            '같은 메시지 3번 LG전자 일반 산업화 심층분석도 '
            '신규 계약·실적 없는 전망 기사로 제외한다. '
            'Telegram message_id=214의 ESS 수요 폭증 보도도 '
            '신규 수주·가격 실측·현장 ESS 설치 없는 일반 수요 전망으로 제외한다. '
            '213번 2번 로브로스 규제특례 승인 알림은 유지한다. '
            '2025년 로브로스 IGRIS-C 사전예약가 약 1억5천만원×20대=30억원은 '
            '가상 비교금액이지 정부 예산·실제 구매계약액·발생 매출이 아니다.'
        ),
        'source': '연합뉴스',
        'published': None,
        'direct_recovery': True,
        'robros_false_alert_correction': True,
    }]



# 2026-10 CATL x INTILION sodium-ion ESS EU framework.
# This is a 3GWh DEVELOPMENT TARGET over five years, not a binding
# procurement contract, installed capacity, sales backlog, or new 10+3 GWh.
CATL_INTILION_RECOVERY = "DIRECT_CATL_INTILION_SODIUM_DACH_3GWH_20261009"
CATL_INTILION_ID = re.compile(r'\bINTILION\b|인틸리온', re.I)
CATL_INTILION_CATL = re.compile(r'\bCATL\b|닝더스다이|宁德时代', re.I)
CATL_INTILION_SODIUM = re.compile(r'sodium[-\s]*ion|나트륨\s*이온|钠离子', re.I)
CATL_INTILION_3GWH = re.compile(r'(?<!\d)3\s*GWh|3\s*기가와트시', re.I)
CATL_INTILION_5Y = re.compile(r'(?:five|5)[-\s]*(?:year|yr)|(?:5|다섯)\s*년|5년간', re.I)
CATL_INTILION_OFFICIAL = {'INTILION CEO','INTILION','INTILION GmbH','CATL'}
CATL_INTILION_TRUSTED = {'pv magazine','pv magazine Global','Energy-Storage.News','ESS News'}
CATL_INTILION_BINDING = re.compile(
    r'signed\s+(?:a\s+)?(?:binding|firm)\s+(?:purchase|supply|procurement)\s+(?:agreement|contract|order)|'
    r'(?:binding|firm)\s+(?:purchase|supply|procurement)\s+(?:agreement|contract|order)\s+(?:signed|executed)|'
    r'(?:구매|공급|발주)\s*(?:본계약|계약)\s*(?:체결|공시|확정)|'
    r'정식\s*(?:구매|공급)\s*계약\s*체결',
    re.I,
)
CATL_INTILION_NOBINDING = re.compile(
    r'not\s+(?:a\s+)?(?:binding|firm)|not\s+confirmed|'
    r'no\s+(?:firm\s+)?(?:procurement|purchase)\s+commitment|'
    r'확정\s*(?:구매|발주|납품)\s*(?:아님|전|없음)|'
    r'구매\s*의무\s*미확정|확정\s*발주\s*없음',
    re.I,
)
CATL_INTILION_DEPLOY = re.compile(
    r'(?:named|specific)\s+project.{0,120}(?:commissioned|operational)|'
    r'실제\s*(?:프로젝트|현장)\s*(?:가동|준공|전원\s*인가)|'
    r'첫\s*나트륨이온\s*(?:ESS\s*)?(?:설치|가동)\s*완료',
    re.I,
)
CATL_INTILION_REVERSE = re.compile(
    r'협약\s*(?:철회|해지|취소)|agreement\s+(?:terminated|cancelled)|'
    r'개발\s*목표\s*(?:축소|중단)',
    re.I,
)


def _is_catl_intilion_sodium(text: str) -> bool:
    return bool(CATL_INTILION_ID.search(text) and CATL_INTILION_CATL.search(text)
                and CATL_INTILION_SODIUM.search(text))


def _catl_intilion_stage(text: str, source: str = '') -> str:
    if not _is_catl_intilion_sodium(text):
        return ''
    if source in CATL_INTILION_OFFICIAL:
        if CATL_INTILION_REVERSE.search(text):
            return 'official_reversal'
        if CATL_INTILION_DEPLOY.search(text):
            return 'official_site_commissioned'
        if CATL_INTILION_BINDING.search(text) and not CATL_INTILION_NOBINDING.search(text):
            return 'official_binding_order'
    if (CATL_INTILION_3GWH.search(text) and CATL_INTILION_5Y.search(text)
            and (source in CATL_INTILION_OFFICIAL or source in CATL_INTILION_TRUSTED)):
        return 'sodium_3gwh_development_framework'
    return 'background'


def _catl_intilion_recovery() -> list[dict]:
    # First-hand evidence is CEO Hubertus Jakobi's LinkedIn update on 10/09;
    # pv magazine independently described it on 10/13. Neither reported
    # firm purchase orders, project sites, a delivery timetable or price.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,21):
        return []
    return [{
        'title': 'CATL–INTILION 나트륨이온 ESS 5년 최대 3GWh 공동개발 협약',
        'link': 'https://www.pv-magazine.com/2026/10/13/catl-intilion-target-up-to-3-gwh-of-sodium-ion-storage-in-europe/',
        'description': (
            'INTILION CEO Hubertus Jakobi 10/09 직접 게시글 및 pv magazine 10/13 '
            '독립 보도 교차확인. 독일·오스트리아·스위스(DACH)에서 '
            'CATL 나트륨이온 ESS를 향후 5년간 최대 3GWh 공동개발한다는 '
            '협약을 서명했다. 3GWh는 프로젝트 개발 목표이지 '
            '확정 구매계약·납품 GWh·기인식 매출이나 설치 완료 용량이 아니다. '
            '구체 프로젝트, 고객별 설비 용량, 조달 의무, 계약금액, '
            '착공·전원 인가·초도 납품 시기는 아직 공개되지 않았다. '
            '2025년 CATL–INTILION 기존 5년 최대 10GWh 협력과 '
            '이번 3GWh의 포함관계가 미공개이므로 13GWh로 합산하지 않는다. '
            '3GWh=3,000MWh=3,000,000kWh이며 실제 단가가 없으므로 '
            '총사업비와 확정 매출은 추정하지 않는다. '
            '가상의 시스템 판매단가가 kWh당 1만원 달라질 때 목표용량 전체 '
            '금액 민감도는 300억원이나 계약액이 아니다. '
            'INTILION은 HOPPECKE 그룹 소속 통합기업으로 프로젝트 설계, '
            '배터리 시스템 통합, 소프트웨어·시운전·유지보수 사업을 수행한다. '
            '장기 유지보수 계약은 이번 협약의 확정 조건이 아니다. '
            'INTILION CEO는 왕복효율 96.5% 초과·15,000회 이상 사이클 등을 '
            '소개했으나 CATL 공식 TENER Sodium 기준 25도 15,000회, '
            '45도 10,000회 초과, 영하20도 92% 초과 용량유지율로 시험조건을 '
            '구분한다. CATL의 유럽 국제 출하는 2027년 6월부터 계획이며 '
            '본 협약의 확정 납품시점이 아니다. 셀/랙/컨테이너 열폭주 전파, '
            '배기·방폭·냉각·화재 인증, 보험, 전력계통 연계와 전원 인가 '
            '시점이 실제 사업화 병목이다.'
        ),
        'source':'INTILION CEO',
        'published': None,
        'direct_recovery':True,
        'catl_intilion_framework':True,
    }]


# Message 246 was sent as "new" on 2026-10-20 but the 16:34
# iNews24 article only recaps CATL-INTILION's Oct-9 5-year up-to-3GWh
# project-development target, already notified in message 218. The RSS
# headline omitted INTILION, defeating the original project dedup key.
CATL_INTILION_OCT20_REPRINT = re.compile(
    r'CATL.{0,55}나트륨\s*배터리.{0,80}유럽\s*ESS.{0,80}저온.{0,35}장수명',
    re.I,
)
ALERT246_CORRECTION_ID = 'DIRECT_ROBOTIS_246_CATL_INTILION_REPEAT_20261020'
ALERT246_CORRECTION_TITLE = '정정: Telegram 246 CATL 유럽 나트륨 ESS 재보도 신규 알림 제외'


def _catl_intilion_oct20_reprint(item: dict) -> bool:
    return bool(
        CATL_INTILION_OCT20_REPRINT.search(item.get('title') or '')
        and item.get('source') not in CATL_INTILION_OFFICIAL
    )


def _alert246_correction_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 25):
        return []
    return [{
        'title': ALERT246_CORRECTION_TITLE,
        'link': 'https://www.inews24.com/view/2016628',
        'description': (
            '기존 Telegram 246번 1번 (2026-10-20 17:08 KST) '
            '아이뉴스24의 CATL 유럽 ESS 저온·장수명 기사를 '
            '신규 고신호로 보낸 것은 중복 판정 오류다. 해당 기사는 '
            '10/09 INTILION CEO 발표·10/13 pv magazine 보도의 '
            'CATL–INTILION 5년 최대 3GWh 나트륨이온 프로젝트 개발 '
            '목표를 10/20에 재보도한 것으로, 신규 고객 구매계약·'
            '셀 출하·설치 완료·매출 인식은 새롭게 확인되지 않는다. '
            '기존 Telegram 218번 2번 CATL–INTILION 협력 알림은 '
            '유효하나 신규 246번은 제외한다. '
            '3GWh=300만kWh는 개발 목표이지 확정 납품량이 아니고 '
            '기존 2025년 10GWh 협력과 중복될 가능성이 있어 '
            '단순 합산하지 않는다. 이번 중복 원인은 기사 제목에 '
            'INTILION 고객명이 빠져 기존 사건 식별을 우회한 것이다. '
            '해당 제목은 10/09 알려진 협력으로 분류·중복 제외하고 '
            '향후 당사자 공식 프로젝트 실명·확정 발주·현장 준공·'
            '실제 출하가 확인될 때만 별도 알림한다. '
            '동일 실행에서 검증한 2027~2029 전고체·나트륨 '
            '증권사 로드맵은 전망표로서 신규 양산이나 고객계약이 아니다.'
        ),
        'source': '기존 GitHub Actions 실제 검증',
        'published': None,
        'direct_recovery': True,
        'quality_correction_246': True,
    }]


# Dexmate CEO interview: distinguish a use/distribution statement and
# vendor-reported hundred-unit global deployments from a signed LG CNS
# sales contract or measured 99.99%-task success.
DEXMATE_LG_RECOVERY = 'DIRECT_DEXMATE_LGCNS_USE_DISTRIBUTION_CEO_20261014'
DEXMATE_ID = re.compile(r'\bDexmate\b|덱스메이트', re.I)
DEXMATE_LG = re.compile(r'\bLG\s*CNS\b|LG씨엔에스|\bLG\b|엘지', re.I)
DEXMATE_CEO = re.compile(r'Tao\s*Chen|타오\s*첸|최고경영자|CEO', re.I)
DEXMATE_USE = re.compile(r'유통\s*(?:지원|돕|도와)|use\s+our\s+robots|'
                         r'using\s+(?:our\s+)?robots|'
                         r'사용하고|사용\s*중|using|한국\s*유통', re.I)
DEXMATE_ACHIEVED_KPI = re.compile(
    r'(?:99[.]99\s*%).{0,45}(?:달성|실측|측정|achieved|measured)|'
    r'(?:달성|실측|측정|achieved|measured).{0,45}(?:99[.]99\s*%)', re.I
)
DEXMATE_KPI_REQUIRED = re.compile(r'필요|목표|요구|necessary|required|target', re.I)
DEXMATE_PAID = re.compile(r'정식\s*유상\s*계약|고객\s*구매\s*계약\s*체결|'
                          r'paid\s+(?:deployment|contract)|'
                          r'signed\s+(?:sales|purchase)\s+contract', re.I)
DEXMATE_PRIMARY = {'LG CNS','LG씨엔에스','Dexmate','DEXMATE'}
DEXMATE_TRUSTED = {'이데일리','EDAILY'}


def _is_dexmate_lg(text: str) -> bool:
    return bool(DEXMATE_ID.search(text) and DEXMATE_LG.search(text))


def _dexmate_lg_stage(text: str, source: str = '') -> str:
    if not _is_dexmate_lg(text):
        return ''
    if source in DEXMATE_PRIMARY:
        if DEXMATE_PAID.search(text):
            return 'official_paid_contract'
        if (DEXMATE_ACHIEVED_KPI.search(text) and not DEXMATE_KPI_REQUIRED.search(text)):
            return 'official_measured_reliability'
    if (source in DEXMATE_TRUSTED and DEXMATE_CEO.search(text)
            and DEXMATE_USE.search(text)
            and re.search(r'유통|distribution|distribut',text,re.I)):
        return 'ceo_reported_use_distribution'
    return 'known_investment_and_poc_baseline'


def _dexmate_lg_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,21):
        return []
    return [{
        'title':'Dexmate CEO: LG CNS 로봇 사용·한국 유통 지원…투자 후 현장 적용 발언',
        'link':'https://www3.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=02482966645612920',
        'description':(
            '2026-10-14 이데일리 뉴욕 현장 인터뷰에서 미국 Dexmate '
            '최고경영자 타오 첸(Tao Chen)은 LG가 자사 로봇을 실제 사용하고 '
            '한국 내 유통도 돕고 있다고 직접 발언했다. '
            'LG CNS는 2026년 3월 LG테크놀로지벤처스를 통해 '
            'Dexmate에 전략투자했으며 제조·물류 현장 개념검증 '
            '진행은 당시 LG CNS 공식 보도자료로 확인된다. '
            'CEO 발언은 기존 투자 및 검증에서 사용·유통 관계가 '
            '구체화한 보도 신호이나 LG CNS의 독점판매계약·'
            '실제 유료 판매건수·매출 공시가 아니다. '
            'CEO는 세계 여러 고객에 로봇 수백 대를 공급했다고 주장했으나 '
            '고객 실명·유상 판매 비중·구체 출하 대수는 별도 검증되지 않았다. '
            '그는 연구실 60~70% 성공률과 달리 산업현장은 '
            '99.99% 정도가 필요하다고 설명했다. 99.99%는 '
            '회사 달성 성능이나 10,000번 실험에서의 성적이 아닌 '
            '상용화 목표 수준이다. RoboStrategy CEO의 '
            '특정작업 로봇 2~3년·범용 로봇 약 5년 전망은 '
            '이 회사의 납품 시간표가 아니다. '
            'RoboStrategy 9월 말 포트폴리오에서 Standard Bots 31.3%, '
            'Dexmate 9.1%로 이해관계가 있는 투자자 전망임을 유의한다. '
            '이후 실제 유상 고객계약·설치·작업성공률·사람 개입률·가동률·'
            '고장률·정비비·보증충당금 및 구체 원화 매출을 별도 추적한다.'
        ),
        'source':'이데일리',
        'published': None,
        'direct_recovery': True,
        'dexmate_ceo_interview': True,
    }]



# One-time correction of a real sent false positive in Telegram #218 item 1.
# Do not retract the two valid CATL–INTILION and Dexmate–LG CNS items.
STOCK_218_CORRECTION = 'DIRECT_CORRECTION_STOCK_REACTION_TELEGRAM218_20261014'


def _stock_218_correction_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,18):
        return []
    return [{
        'title':'정정: Telegram 218번 1번 주가 반응 기사는 신규 고신호 아님',
        'link':'https://github.com/qedgwangju-dot/khs-watch/actions/runs/38507177438',
        'description':(
            '정정: Telegram 218번 1번 서울경제의 '
            'AI 전력發 ESS 기대·삼성SDI 5% 오르며 2차전지株 강세 기사는 '
            '주가 반응 및 일반 ESS 수요 기대에 관한 보도입니다. '
            '새로운 삼성SDI 고객 실명 공급계약·발주·실제 출하·'
            '분기 실적 공시가 없어 투자 알림 고신호에서 제외합니다. '
            '같은 message_id=218의 2번 CATL–INTILION 5년 최대 3GWh '
            '나트륨 ESS 공동개발 목표와 3번 Dexmate–LG CNS '
            '최고경영자 실사용·유통 발언은 유효합니다. '
            '증상 원인은 제목에 주가·상승 대신 5% 오르며·'
            '2차전지株 강세라는 표현이 있어 기존 주가 필터가 '
            '반응 기사를 놓친 것입니다. 정확한 금액·대수·'
            '고객사·새 사업 상태가 없는 유사 주가 보도는 '
            '앞으로 신규 사건으로 분류하지 않습니다.'
        ),
        'source':'실제 GitHub Actions 전송기록',
        'published':None,
        'direct_recovery':True,
        'correction_218_stock':True,
    }]



# Brunsbuettel Vattenfall/Fluence project, announced by Fluence via
# GlobeNewswire on 2026-10-14. Sep 10 investment decision was already
# announced by Vattenfall; the NEW event is Fluence's signed turnkey award.
# Cell supplier, amount and service tenure are not public.
FLUENCE_VATTENFALL_RECOVERY = 'DIRECT_FLUENCE_VATTENFALL_BRUNSBUETTEL_SIGNED_20261014'
FLUENCE_VATTENFALL_PRESS = 'https://via.ritzau.dk/pressemeddelelse/15224763/fluence?publisherId=90446'
FLUENCE_VATTENFALL_ORIGIN = {'Fluence (GlobeNewswire)', 'Fluence', 'Fluence Energy', 'Vattenfall'}
FLUENCE_VATTENFALL_PARTIES = re.compile(r'Fluence|플루언스',re.I)
FLUENCE_VATTENFALL_CUSTOMER = re.compile(r'Vattenfall|바텐팔',re.I)
FLUENCE_VATTENFALL_SITE = re.compile(r'Brunsb(?:ü|u)ttel|브룬스뷔텔|브룬스뷔텔',re.I)
FLUENCE_VATTENFALL_SIGNED = re.compile(
    r'signed\s+(?:an?\s+)?agreement|agreement\s+(?:has\s+been\s+)?signed|'
    r'contract\s+(?:was\s+)?signed|signed\s+contract|'
    r'공급계약\s*체결|계약을\s*체결|공급\s*계약\s*(?:확정|체결)',
    re.I,
)
FLUENCE_VATTENFALL_FID = re.compile(r'final\s+investment\s+decision|투자\s*최종\s*결정',re.I)
FLUENCE_VATTENFALL_START = re.compile(
    r'(?:construction|building\s+works).{0,60}(?:has\s+)?(?:begun|started|commenced)|'
    r'실제\s*착공|착공\s*(?:확정|완료|개시)|공사\s*(?:시작|개시)\s*완료',
    re.I,
)
FLUENCE_VATTENFALL_START_NOT = re.compile(
    r'(?:will|planned|scheduled|expected|due|to)\s+(?:begin|start|commence)|'
    r'착공\s*(?:계획|예정|목표)|2027년\s*(?:착공|공사)\s*(?:예정|목표)',
    re.I,
)
FLUENCE_VATTENFALL_ENERGIZED = re.compile(
    r'grid\s+(?:connection|energization)\s+(?:completed|commissioned)|'
    r'commercial\s+operations?\s+(?:commenced|began|started)|'
    r'전원\s*인가\s*(?:완료|확인)|상업\s*운전\s*(?:개시|시작)|준공\s*(?:완료|확정)',
    re.I,
)
FLUENCE_VATTENFALL_ENERGIZED_NOT = re.compile(
    r'(?:will|planned|scheduled|expected|due|target|aim).{0,60}'
    r'(?:operational|online|commissioning|grid\s+connection)|'
    r'(?:예정|목표|계획).{0,50}(?:준공|상업\s*운전|전원\s*인가)',
    re.I,
)
FLUENCE_VATTENFALL_REVERSE = re.compile(
    r'cancel(?:led|ation)?|terminat(?:ed|ion)|contract\s+withdrawn|'
    r'계약\s*(?:취소|해지|철회)|사업\s*(?:중단|철회)|공급사\s*변경',
    re.I,
)


def _is_fluence_vattenfall(text: str) -> bool:
    return bool(
        FLUENCE_VATTENFALL_PARTIES.search(text)
        and FLUENCE_VATTENFALL_CUSTOMER.search(text)
        and FLUENCE_VATTENFALL_SITE.search(text)
    )


def _fluence_vattenfall_stage(text: str, source: str = '') -> str:
    if not _is_fluence_vattenfall(text):
        return ''
    if source not in FLUENCE_VATTENFALL_ORIGIN:
        return 'report_only'
    if FLUENCE_VATTENFALL_REVERSE.search(text):
        return 'official_reversal'
    if (FLUENCE_VATTENFALL_ENERGIZED.search(text)
            and not FLUENCE_VATTENFALL_ENERGIZED_NOT.search(text)):
        return 'official_energized'
    if (FLUENCE_VATTENFALL_START.search(text)
            and not FLUENCE_VATTENFALL_START_NOT.search(text)):
        return 'official_construction_started'
    if FLUENCE_VATTENFALL_SIGNED.search(text):
        return 'official_signed_turnkey_award'
    return 'existing_fid_or_timeline'


def _fluence_vattenfall_recovery() -> list[dict]:
    # One-time press release recovery. The original release specifies 09:00
    # CEST, which equals 07:00 UTC / 16:00 KST on Oct 14.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,20):
        return []
    return [{
        'title':'Fluence·Vattenfall, 독일 브룬스뷔텔 254MW/1GWh ESS 턴키·장기 유지보수 계약 체결',
        'link':FLUENCE_VATTENFALL_PRESS,
        'description':(
            'Fluence가 GlobeNewswire에서 2026-10-14 직접 발표했다. '
            'Vattenfall과 독일 Brunsbüttel 배터리 에너지저장장치 사업에 '
            '배터리 시스템·전력변환장치·에너지관리시스템을 포함한 Gridstack Pro 5000 '
            '공급 및 설계·조달·시공·시운전, 장기 유지보수 계약을 체결했다. '
            '254MW, 1,000MWh 초과, 지속시간 약 4시간. '
            '2027년 착공 예정, 2028년 말 50Hertz 380kV 송전계통 연결·상업운전 목표. '
            'Vattenfall의 2026-09-10 투자 최종결정은 기존 기준선이며 '
            '새 사건은 2026-10-14 Fluence 공급사 선정과 구속력 있는 서명 계약이다. '
            '계약금액, 저장 셀 제조사·화학 조성, 장기 유지보수 기간 및 '
            '서비스 이용료는 이번 공개발표에 기재되지 않았다. '
            'Samsung SDI가 이 프로젝트의 셀 공급사라는 근거는 없다. '
            '독일 4시간 ESS 2026년 턴키 산업 비교치는 280~450유로/kWh이며 '
            '1,000MWh 용량을 단순 적용하면 2억8,000만~4억5,000만유로다. '
            '기업은행 2026-10-14 15:05:50 매매기준율 1유로=1,500.24원으로 '
            '약 4,201억~6,751억원의 전체 프로젝트 투자비 참고범위다. '
            '이 금액은 Fluence 수주액이나 Vattenfall 확정 투자비가 아니다. '
            '공사·계통접속·화재안전·보험·전원인가·유지보수 이행을 별도 추적한다.'
        ),
        'source':'Fluence (GlobeNewswire)',
        'published':'2026-10-14T07:00:00+00:00',
        'direct_recovery':True,
        'flu_vattenfall_award':True,
    }]


SDI_OCT08_PREVIEW_SOURCE = re.compile(r'DS투자증권|DS\s*Investment|최태용',re.I)
SDI_OCT08_PREVIEW_COMPANY = re.compile(r'삼성SDI|Samsung\s*SDI',re.I)
SDI_OCT08_PREVIEW_PREDICTION = re.compile(
    r'3Q26|3분기|4분기|2028|2,575|2575|AMPC|시너지셀즈',
    re.I,
)
SDI_OCT08_PREVIEW_QUALIFIER = re.compile(r'전망|추정|예상|검토|수주\s*기대|목표',re.I)


def _is_sdi_oct08_preview(text: str) -> bool:
    # Analyst assumptions are useful for monitoring but neither actual
    # filings nor signed new orders. Company earnings releases still go
    # through the original ESS stage classifier.
    if re.search(r'삼성SDI.{0,50}(?:2026년\s*3분기\s*공식\s*실적|확정실적\s*발표)', text,re.I):
        return False
    return bool(
        SDI_OCT08_PREVIEW_COMPANY.search(text)
        and SDI_OCT08_PREVIEW_SOURCE.search(text)
        and SDI_OCT08_PREVIEW_PREDICTION.search(text)
        and SDI_OCT08_PREVIEW_QUALIFIER.search(text)
    )



# 2026-10-12..15 evidence-gated robotic commercialization/research events.
# These are added to the ACTIVE workflow, not a new workflow or state store.
# Link origin and evidence level remain explicit, and each historic recovery
# expires; any later official closing, approval or shipment has a new event key.
ROBOT_OCT15_RECOVER_PREFIX = 'DIRECT_ROBOT_OCT15_'
ROBOT_OCT15_EVENTS = {
    'agility_s4_effective': {
        'title': 'Agility Robotics–Churchill XI: SEC S-4 효력발생, 11월 2일 주총 대기',
        'source': 'Agility Robotics',
        'link': 'https://www.agilityrobotics.com/content/agility-robotics-and-churchill-capital-corp-xi-s-4-registration-statement-declared-effective-by-sec-in-connection-with-proposed-business-combination',
        'description': (
            '2026-10-13 Agility Robotics 공식 발표와 미국 SEC 첨부 보도자료 확인: '
            'Churchill Capital Corp XI(CCXI)와 Agility의 합병 관련 Form S-4 효력이 발생했다. '
            '11월 2일 주주총회 승인과 거래종결 등 조건이 남아, Nasdaq AGLT 상장은 아직 완료되지 않았다. '
            '2026년 10월 15일 달러 매매기준율 1달러 1,341.50원 기준 예상 총조달 6억2,000만달러 초과 '
            '(약 8,317억원 초과), CCXI 신탁현금 약 4억2,400만달러(약 5,688억원, '
            '환매가 없을 때)와 Foxconn 주도 PIPE 약 2억달러(약 2,683억원)를 구분한다. '
            '양자 단순 합계는 6억2,400만달러로 재인용된 최소 총조달액과 다르다. '
            'Digit 5 조건부 약정 주문 3억달러 초과(약 4,025억원 초과)는 인식매출이 아니다. '
            '기존 Digit 실세계 운영 6만5,000시간 이상, 확정 배치 시설 9곳, 2027년 25곳 목표, '
            '고객후보 30곳 초과에서 약 100곳 목표, RoboFab 명목 연산 1만대와 실제 출하를 구분한다. '
            '기업가치와 조달액은 신규 매출이 아니라 자본시장 거래이고 '
            '기존 주주 180일 보호예수·주주 환매·주총 부결·제품 인증 지연이 위험이다.'
        ),
    },
    'rainbow_fcc_filed': {
        'title': '레인보우로보틱스 RB-Y1 미국 로봇 조건부 승인 신청 보도',
        'source': '전자신문',
        'link': 'https://m.etnews.com/20261012000251',
        'description': (
            '2026-10-12 전자신문 보도: 레인보우로보틱스가 9월 말 이동형 양팔로봇 RB-Y1의 '
            '미국 판매 규제에 대비해 조건부 승인 신청서 제출을 완료했다고 보도했다. '
            '제출은 승인 발급이 아니며 레인보우로보틱스 미국 확정 공급계약·첫 출하도 아니다. '
            '티로보틱스는 신청 준비 단계로 별도 기업이고 이미 제출했다고 표기하지 않는다. '
            '2026-07-28 FCC DA 26-786의 외국산 첨단 이동로봇 Covered List와 '
            '2026-09-18 DA 26-996의 전쟁부(DoW) 조건부 승인 경로를 확인했다. '
            '미국산 완제품 기준은 미국 제조 및 미국산 부품 원가비중 2028년까지 65% 초과, '
            '2029년부터 75% 초과이며 조건부 승인이라는 별도 예외가 존재한다. '
            '일례로 부품원가 100억원의 미국산 비중 기준은 65억원 초과에서 '
            '75억원 초과로 10억원포인트 늘어난다(예시, 회사 원가 아님). '
            '기존 인증모델과 신규모델, 부품 자체와 완성 이동로봇 규제를 구분한다. '
            'DoW 실제 승인 공고·승인대상 모델·미국 OEM 계약·미국 생산설비 투자를 후속 확인한다.'
        ),
    },
    'xinjian_ipo_response': {
        'title': '신젠전동 IPO 심사답변: 익명 A사 휴머노이드 볼스크류 양산발주 공개',
        'source': '21财经',
        'link': 'https://data.eastmoney.com/notices/detail/A26193/AN202610121830360984.html',
        'description': (
            '2026-10-12 신젠전동(新剑传动)이 중국 창업판 상장심사 질의서 답변을 공개했다. '
            '21财经·동방재부 공시 원문 재게시·동화순이 이를 보도했다. '
            '업체는 고객 A사로부터 휴머노이드용 스크루 부품의 양산 주문을 받았다고 밝혔다. '
            '고객 A사 실명은 공시상 비공개이므로 Tesla로 바꾸지 않는다. '
            'Tesla Optimus V3 설계안이 거의 동결됐다거나 중하중 직선 액추에이터에 '
            '행성 롤러스크루가 사실상 대체 불가라는 것은 신젠전동 경영진의 '
            'IPO 문서상 산업 판단이지 Tesla의 설계확정·양산 승인 발표가 아니다. '
            '동사의 휴머노이드 관련 스크루·액추에이터 사업 매출은 '
            '2024년 696.88만위안(약 13억9,676만원), '
            '2025년 3,110.59만위안(약 62억3,456만원), '
            '2026년 상반기 1,621.05만위안(약 32억4,907만원)으로 기간이 다르다. '
            '2026년 상반기 평균판매단가 하락, 로봇 사업 매출 비중 10% 미만, '
            '기존 자동차 사업 수익성 악화가 역풍이다. '
            '위안당 200.43원은 2026년 10월 15일 한국무역협회 공시 매매기준율로 단순 환산했다. '
            '고객 실명 검증·물량·스크루 규격·수율·첫 출하·실제 인식매출을 확인한다.'
        ),
    },
    'unichem_loomia_signed': {
        'title': '유니켐–Loomia 지분 100% 인수 본계약 보도, 2027년 1월 종결 조건',
        'source': '더벨',
        'link': 'https://www.thebell.co.kr/front/newsview.asp?code=0203&key=202610121331150840102821',
        'description': (
            '2026-10-12 유니켐은 미국 유연전자 회사 Loomia Technologies의 지분 100% '
            '인수 본계약 체결을 발표했다는 더벨 및 뉴스핌 보도. '
            '최대 인수가액 630만달러(2026-10-15 1달러=1,341.50원 적용 약 84억5,145만원). '
            '잔여 주주 서명·한국은행 외국환거래 신고수리 등 선행조건이 남아 거래는 종결되지 않았다. '
            '목표 종결일은 2027-01-04. '
            'Loomia의 유연 압력감지·접촉·발열 전자피부를 로봇 손·그리퍼와 '
            '자동차 내장재에 적용하려는 준비 단계다. HAND ERC 참여는 메타·아마존에 대한 '
            '확정 판매계약이 아니다. 2028년까지 로봇 1,000대·자동차 3,000대 양산 수주는 '
            '회사 목표이며 현재 확보한 주문이 아니다. 목표 연계 성과보상용 '
            '최대 100만달러(약 13억4,150만원) 전환사채 조건은 인수가액과 구분한다. '
            '거래종결·사업부 연결 시점·고객 소재검증·수율·로봇 OEM 유상 수주와 '
            '기존 자동차 사업 반복매출을 분리해 관찰한다.'
        ),
    },
    'atlas_protoops_goal': {
        'title': 'Boston Dynamics Atlas 시제품 제작 하루→1시간 목표 발표',
        'source': 'Humanoids Daily',
        'link': 'https://youtu.be/dP_i7hRvGpE',
        'description': (
            'Boston Dynamics의 Atlas 정밀가공·설계·조립·시험을 다룬 회사 영상과 '
            '2026-10-14 Humanoids Daily 보도: 시제품 운영팀 관계자는 '
            '현행 Atlas 시제품 1대 제작에 약 하루가 걸리며 '
            '2027년 약 1시간으로 줄이는 것이 목표라고 설명했다. '
            '일반적인 하루를 24시간 가동시간으로 보고 24배 양산이라고 계산하지 않는다. '
            '연간 완제품 생산대수·직행수율·검사 시간·상용 납품 속도는 미공개다. '
            '현대차 HMGMA RMAC는 별도 실제 현장 훈련·검증 시설이며 '
            '이번 ProtoOps 공정영상이 대량양산 수율이나 유상 출하 증거는 아니다. '
            '병목은 핵심 가공품 반복정밀도·관절 조립·최종 검사·고장수리·발열·인증이다. '
            '2027년 실제 조립 소요시간·고온 작동검사·수율·고객 공장 배치에서 '
            '목표 달성을 다시 확인해야 한다.'
        ),
    },
    'alert224225_quantity_correction': {
        'title': '정정: Telegram 224·225 수량 표기 오탐 철회',
        'source': '기존 GitHub Actions 실행기록',
        'link': 'https://github.com/qedgwangju-dot/khs-watch/actions/runs/38664269308',
        'description': (
            '2026-10-15 Run #598 Telegram message_id=224·225 발송문에서 '
            '신젠전동·RB-Y1·Atlas 제작 목표에 확인 물량 12개를 붙인 것은 '
            '원문의 6~12개월 위험 기간에서 12개를 잘못 추출한 오류입니다. '
            'Agility 9개·2027년 목표 25개는 실제 시설 운영 수와 미래 목표시설 수이며 '
            '양산 완제품 출하량이나 확정 부품 주문 개수가 아닙니다. '
            '유니켐–Loomia의 2028년 로봇 1,000대·자동차 3,000대 역시 '
            '양산 주문 목표이지 확보한 발주가 아닙니다. '
            '발송된 모든 범용 확인 물량 블록의 확인 물량 판정을 철회합니다. '
            '기존 SEC S-4 효력, RB-Y1 신청, IPO A사 양산주문 회사 진술, '
            '유니켐 본계약과 Atlas 시제품 목표는 그대로 유지합니다. '
            '범용 수량×단가 추측 출력을 제거하고 제품 실명·공식 단가와 '
            '실제 납품량이 확인된 경우에만 개별 환산을 허용합니다.'
        ),
    },
    'alert223_quality_correction': {
        'title': '정정: Telegram 223 신규 ESS 고신호 4건 중 목표가·기대 기사 오탐 제거',
        'source': '기존 GitHub Actions 실행기록',
        'link': 'https://github.com/qedgwangju-dot/khs-watch/actions/runs/38662197011',
        'description': (
            '2026-10-15 Run #595에서 전송된 Telegram message_id=223은 '
            '뉴스핌 삼성SDI 목표가 90만원 브리핑, 파이낸셜뉴스 LG에너지솔루션 '
            '목표가 51만원 기대 기사와 삼성SDI의 일본 ESS 사업 일반 분석·재보도까지 '
            '별도 고신호 4건으로 선정했다. 이 4건은 원문만으로 신규 발주·'
            '확정 공급계약·실제 생산량·공식 실적의 신규 증거로 인정할 수 없어 '
            '고신호 판정을 철회한다. 이 정정은 신규 수주 알림이 아니다. '
            '목표가·애널리스트 전망·테마 반복 제거와 '
            '실제 계약·실제 출하를 구분하는 선별 및 회귀검사를 추가했다.'
        ),
    },
}
ROBOT_OCT15_PREFIX = 'DIRECT_OCT15_ROBOT_UPDATES_'
ROBOT_OCT15_GROUPS = {
    'agility_s4_effective': 'agility_spac_2026',
    'rainbow_fcc_filed': 'rainbow_fcc_compliance',
    'xinjian_ipo_response': 'xinjian_prs_ipo',
    'unichem_loomia_signed': 'unichem_loomia_acquisition',
    'atlas_protoops_goal': 'atlas_protoops_build',
    'alert223_quality_correction': 'alert_quality_223',
    'alert224225_quantity_correction': 'alert_quality_qty_224225',
}
ROBOT_OCT15_TITLES = {
    'agility_spac_2026': 'Agility Robotics · S-4 효력 발생·주총 승인 대기',
    'rainbow_fcc_compliance': '레인보우로보틱스 · RB-Y1 미국 조건부승인 신청 보도',
    'xinjian_prs_ipo': '신젠전동 · 익명 A사 양산 발주·IPO 질의서 답변',
    'unichem_loomia_acquisition': '유니켐–Loomia · 지분 100% 인수 본계약·선행조건',
    'atlas_protoops_build': 'Boston Dynamics · Atlas 제작시간 단축 목표',
    'alert_quality_223': '알림 품질 정정 · Telegram 223 ESS 오탐 4건',
    'alert_quality_qty_224225': '알림 품질 정정 · Telegram 224·225 수량 표기 오탐',
}
ROBOT_OCT15_GROUP_REGEX = (
    ('agility_spac_2026', re.compile(r'Agility\s*Robotics|애질리티\s*로보틱스',re.I),
     re.compile(r'Churchill(?:\s*Capital)?(?:\s*Corp)?\s*XI|\bCCXI\b|\bAGLT\b|Form\s*S-4|주총\s*합병',re.I)),
    ('rainbow_fcc_compliance', re.compile(r'레인보우로보틱스|Rainbow\s*Robotics|RB[-\s]?Y1',re.I),
     re.compile(r'FCC|Covered\s*List|조건부\s*승인|미국.{0,24}규제',re.I)),
    ('xinjian_prs_ipo', re.compile(r'新剑传动|신젠전동|Xinjian\s*(?:Drive|Transmission)',re.I),
     re.compile(r'IPO|上市|问询|질의서|A사|A公司|A\s*company|첫\s*출하|양산\s*출하',re.I)),
    ('unichem_loomia_acquisition', re.compile(r'유니켐|Unichem',re.I),
     re.compile(r'(?:Loomia|루미아).{0,100}(?:인수|지분|본계약|거래\s*종결)|(?:인수|지분|본계약|거래\s*종결|acquisit).{0,100}(?:Loomia|루미아)',re.I)),
    ('atlas_protoops_build', re.compile(r'Boston\s*Dynamics|보스턴다이내믹스',re.I),
     re.compile(r'(?:Atlas|아틀라스).{0,150}(?:ProtoOps|시제품|제작\s*시간|제작시간|1\s*시간|one\s*hour|one\s*day|prototype\s*(?:shop|operation))|(?:ProtoOps|시제품|제작\s*시간|1\s*시간|one\s*hour|one\s*day).{0,150}(?:Atlas|아틀라스)',re.I)),
)
ROBOT_OCT15_PRIMARY = {
    'agility_spac_2026': {'Agility Robotics', 'SEC', 'Churchill Capital Corp XI'},
    'rainbow_fcc_compliance': {'레인보우로보틱스', 'DoW', 'FCC'},
    'xinjian_prs_ipo': {'新剑传动', '深圳证券交易所', 'SZSE'},
    'unichem_loomia_acquisition': {'유니켐', 'Loomia Technologies', 'DART'},
    'atlas_protoops_build': {'Boston Dynamics'},
}


def _oct15_group(text: str) -> str:
    if '정정: Telegram 224·225' in text:
        return 'alert_quality_qty_224225'
    if '정정: Telegram 223' in text:
        return 'alert_quality_223'
    for group, actor, subject in ROBOT_OCT15_GROUP_REGEX:
        if actor.search(text) and subject.search(text):
            return group
    return ''


def _oct15_stage(group: str, text: str, source: str = '') -> str:
    official = source in ROBOT_OCT15_PRIMARY.get(group, set())
    if group in {'alert_quality_223', 'alert_quality_qty_224225'}:
        return 'correction'
    if group == 'agility_spac_2026':
        if official and re.search(r'합병\s*(?:종결|완료)|business\s*combination\s*(?:closed|completed)|\bAGLT\b.{0,45}(?:trading\s*started|거래\s*개시)', text,re.I):
            return 'official_closed'
        if official and re.search(r'주주(?:총회)?\s*승인\s*통과|shareholders?\s*(?:approved|voted\s+to\s+approve)', text,re.I):
            return 'shareholders_approved'
        if official and re.search(r'(?:S[-\s]?4).{0,65}(?:효력|effective)|declared\s*effective.{0,90}(?:S[-\s]?4|registration)|SEC.{0,45}효력',text,re.I):
            return 's4_effective'
    if group == 'rainbow_fcc_compliance':
        # Reject negative review-process sentences even when they mention the
        # word "granted" ("not granted"). Approval needs a positive issuer act.
        if re.search(
            r'not\s+(?:yet\s+)?(?:granted|approved|issued)|'
            r'미\s*(?:승인|발급)|승인\s*(?:전|미확정|심사\s*중)|'
            r'신청\s*(?:중|단계)|(?:발급|부여)\s*되지\s*않',
            text,re.I
        ):
            return 'background'
        if official and re.search(
            r'(?:DoW|전쟁부).{0,85}(?:조건부\s*승인.{0,25}(?:발급|부여|획득)|'
            r'(?:granted|issued|approved).{0,30}conditional\s*approval|'
            r'conditional\s*approval.{0,30}(?:granted|issued|approved))|'
            r'조건부\s*승인.{0,30}(?:획득|발급|부여)',
            text,re.I
        ):
            return 'official_approval_granted'
        if source in {'전자신문','ETNews'} and re.search(r'(?:신청서|서류).{0,30}(?:제출|접수)|(?:조건부\s*승인).{0,35}신청',text,re.I):
            return 'application_reported'
    if group == 'xinjian_prs_ipo':
        if official and re.search(
            r'实际.{0,10}(?:出货|交付)|첫\s*출하|'
            r'첫\s*양산\s*출하.{0,15}(?:확인|시작|개시|완료)|'
            r'양산\s*출하\s*(?:개시|시작|완료)',text,re.I
        ):
            return 'official_shipment'
        if source in {'21财经','21世纪经济报道','동방재부'} and re.search(r'10.{0,3}12|2026-10-12|问询|질의서|IPO',text,re.I) and re.search(r'A사|A公司|A\s*company|양산\s*발주|量产\s*订单|mass\s*production\s*order',text,re.I):
            return 'ipo_order_reported'
    if group == 'unichem_loomia_acquisition':
        if official and re.search(r'인수\s*종결\s*완료|거래\s*종결\s*완료|acquisition\s*closed|closing\s*completed',text,re.I):
            return 'official_closing'
        if source in {'더벨','뉴스핌','이데일리'} and re.search(r'본계약\s*체결|binding\s*agreement\s*signed|definitive\s*agreement',text,re.I):
            return 'signed_conditional_report'
    if group == 'atlas_protoops_build':
        if official and re.search(r'실제.{0,28}1\s*시간.{0,35}(?:달성|검증)|one[-\s]*hour.{0,35}(?:achieved|verified|measured)',text,re.I):
            return 'official_one_hour_achieved'
        if source in {'Humanoids Daily','Boston Dynamics'} and re.search(r'약\s*하루|one\s*day|a\s*day',text,re.I) and re.search(r'1\s*시간|one\s*hour|an\s*hour',text,re.I) and re.search(r'목표|aim|target|goal|2027|next\s*year',text,re.I):
            return 'build_time_goal'
    return 'background'


def _oct15_recovery(group_key: str) -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,20):
        return []
    if group_key not in ROBOT_OCT15_EVENTS:
        return []
    ev = ROBOT_OCT15_EVENTS[group_key]
    return [{
        'title':ev['title'],'description':ev['description'],
        'link':ev['link'],'source':ev['source'],'published':None,
        'direct_recovery':True,'oct15_high_signal_key':group_key,
    }]


# Labels do not claim SEC approval = successful listing, application =
# government approval, vendor claim = Tesla confirmation, or prototype goal
# = achieved mass-production cycle.
def _oct15_render_category(group: str, text: str) -> str:
    if group == 'agility_spac_2026':
        if re.search(r'합병\s*종결\s*완료|merger\s*completed|business\s*combination\s*(?:closed|completed)',text,re.I):
            return 'Agility Robotics · 실제 합병 거래종결 공식확인'
        if re.search(r'주주(?:총회)?\s*승인\s*통과|주총.{0,20}승인\s*통과|shareholders?\s*approved',text,re.I):
            return 'Agility Robotics · 주주총회 승인·거래종결 대기'
    if group == 'rainbow_fcc_compliance':
        if re.search(r'조건부\s*승인.{0,20}(?:부여|발급|획득)',text,re.I):
            return '레인보우로보틱스 · DoW 조건부 승인 공식확인'
    if group == 'xinjian_prs_ipo':
        if re.search(r'신젠전동.{0,45}첫\s*양산\s*출하\s*확인',text,re.I):
            return '신젠전동 · 첫 양산 출하 공식확인'
    if group == 'unichem_loomia_acquisition':
        if re.search(r'유니켐.{0,65}(?:거래\s*종결\s*완료|인수\s*종결\s*완료)',text,re.I):
            return '유니켐–Loomia · 인수 종결 공식확인'
    if group == 'atlas_protoops_build':
        if re.search(r'Atlas.{0,75}1\s*시간.{0,30}실측\s*달성',text,re.I):
            return 'Boston Dynamics · Atlas 1시간 제조 목표 실제 달성'
    return ROBOT_OCT15_TITLES[group]


_OCT15_MEANINGS = {
    ROBOT_OCT15_TITLES['agility_spac_2026']: (
        '10/13 SEC S-4 효력발생은 실제 합병·AGLT 상장 완료가 아닙니다. '
        '11/2 Churchill XI 주총 승인·상장요건·거래종결이 남았습니다. '
        '환매가 없을 때 신탁 4억2,400만달러(약 5,688억원)와 '
        'Foxconn 주도 PIPE 약 2억달러(약 2,683억원), 총 6억2,000만달러 초과 '
        '(약 8,317억원 초과)는 예정 조달액이며 매출이 아닙니다. '
        'Digit 5 조건부 약정주문 3억달러 초과(약 4,025억원)도 인식매출과 구분합니다. '
        '기존 Digit 상용 고객·9개 시설, 6만5천시간 실운용, '
        '2027년 25개 시설 목표·연간 1만대 RoboFab 생산능력 계획은 '
        '출하 실적과 분리해 확인합니다. 기준환율은 10/15 달러 1,341.50원입니다.'
    ),
    ROBOT_OCT15_TITLES['rainbow_fcc_compliance']: (
        '전자신문 10/12: 레인보우로보틱스가 RB-Y1 미국 판매 관련 '
        '조건부 승인 신청서를 9월 말 제출했다는 보도입니다. '
        'DoW 승인·미국 공급계약·실제 출하는 아직 확인되지 않았습니다. '
        'FCC 7/28 Covered List는 신규 외국산 이동로봇 장비승인에 적용되며 '
        '미국내 제조+미국산 부품원가 65% 초과(2028년까지), '
        '75% 초과(2029년부터)라는 국내산 판정과 별도 조건부 승인 경로가 있습니다. '
        '티로보틱스는 제출 준비 보도 단계여서 신청 완료로 혼동하지 않습니다.'
    ),
    ROBOT_OCT15_TITLES['xinjian_prs_ipo']: (
        '10/12 신젠전동(新剑传动) 중국 IPO 심사 질의서 답변: 익명 A사 '
        '휴머노이드 스크루 양산발주를 회사가 주장했습니다. '
        'A사가 Tesla라는 실명은 공개되지 않았고, '
        'Optimus V3 설계 정형·행성 롤러스크루 불가역성은 신젠전동의 산업 판단으로 '
        'Tesla 공식 확정이 아닙니다. 관련 사업 매출은 '
        '2024년 696.88만위안(약 14억원), 2025년 3,110.59만위안(약 62억원), '
        '2026년 상반기 1,621.05만위안(약 32억원)이며 '
        '상반기 평균판매단가 하락·로봇 사업 비중 10% 미만도 함께 점검합니다. '
        '10/15 환율 1위안 200.43원 단순환산이며 고객·출하량·이익은 별도입니다.'
    ),
    ROBOT_OCT15_TITLES['unichem_loomia_acquisition']: (
        '유니켐은 Loomia 지분 100% 인수 본계약을 체결했다는 10/12 회사발 보도. '
        '최대 630만달러(약 84억5천만원), 2027-01-04 종결 예정이나 '
        '주주 서명·외국환 신고 등의 선행조건이 남아 있습니다. '
        '2028년 로봇 1,000대·자동차 3,000대 양산 주문은 회사 목표이며 '
        '현재 확정 고객발주가 아닙니다. 최대 100만달러(약 13억4천만원) '
        '성과연동 전환사채는 인수대금과 혼합하지 않습니다. '
        '자동차 내장재 실제 매출과 휴머노이드 전자피부 고객 검증·초도 납품을 분리합니다.'
    ),
    ROBOT_OCT15_TITLES['atlas_protoops_build']: (
        'Boston Dynamics의 ProtoOps 제조과정 영상 관련 10/14 보도에서 '
        '현재 Atlas 시제품 제작은 약 하루이며 2027년 약 1시간을 목표로 합니다. '
        '제작일 하루가 24시간 순가동이라는 근거가 없으므로 24배 양산으로 환산하지 않습니다. '
        '정밀 가공→조립→검사·재작업 단축 연구개발 목표이며 '
        '실제 정규생산 속도·출하·수율 개선 달성이 아닙니다.'
    ),
    ROBOT_OCT15_TITLES['alert_quality_qty_224225']: (
        'Telegram 224·225의 범용 확인 물량 12개·9개 시설·25개 목표 시설·1,000/3,000대 '
        '수량 표시는 실제 양산·확정 공급 수량의 근거가 아니라 전부 철회합니다. '
        '12개는 6~12개월을 잘못 해석한 것입니다. 기존 보도에 나온 계약·신청·'
        '인수 추진·제조시간 목표 판정은 유지하고, 실판매 단가·계약 물량을 '
        '확인할 때만 단위별 원화 매출을 계산합니다.'
    ),
    ROBOT_OCT15_TITLES['alert_quality_223']: (
        '10/15 실제 Telegram message_id=223의 4건은 삼성SDI·LG에너지솔루션 '
        '목표주가 및 일본 ESS 사업 일반 논평·재보도를 신규 확정 사업으로 분류한 오탐입니다. '
        '계약금액·고객 발주·양산·실적 공식 확인이 없으므로 4건을 고신호 판정에서 제외합니다. '
        '이 정정은 새로운 수주·매출이 아닙니다.'
    ),
    'Agility Robotics · 주주총회 승인·거래종결 대기': (
        '11월 2일 주주 승인 통과가 회사 공식발표로 확인된 단계이며 거래종결·'
        'AGLT 실제 Nasdaq 거래개시는 아직 별도 절차입니다. 환매·PIPE·주식희석을 검산합니다.'
    ),
    'Agility Robotics · 실제 합병 거래종결 공식확인': (
        'S-4 효력 및 주주 승인 이후 실제 합병 종결이 공식 확인된 단계입니다. '
        'SEC 8-K·AGLT 거래개시·현금 납입·환매 후 조달액을 따로 확인합니다.'
    ),
    '레인보우로보틱스 · DoW 조건부 승인 공식확인': (
        '조건부 승인 실제 발급이 확인돼 신청 단계를 넘어선 사건입니다. '
        '적용 RB-Y1 모델·승인기간·현지생산 요건·출하·미국 고객 주문을 각각 확인합니다.'
    ),
    '신젠전동 · 첫 양산 출하 공식확인': (
        '익명 A사 양산 주문이 실제 납품으로 연결됐다는 별도 공식 확인입니다. '
        '고객 실명·부품 단가·납품량·수율과 인식매출을 검증합니다.'
    ),
    '유니켐–Loomia · 인수 종결 공식확인': (
        '조건부 본계약 이후 실제 소유권·자금 이전이 완료된 단계입니다. '
        '연결 매출·차입금·주식희석과 고객별 전자피부 양산발주를 분리합니다.'
    ),
    'Boston Dynamics · Atlas 1시간 제조 목표 실제 달성': (
        'Atlas 시제품 단축 목표의 실제 측정 달성 단계입니다. '
        '정규 생산과 검수 포함 전체 사이클·연간 출하능력은 별도 점검합니다.'
    ),
}
_OCT15_RISKS = {
    ROBOT_OCT15_TITLES['agility_spac_2026']: (
        '11/2 주주총회 부결·주주 환매·거래종결 지연이 초기 6개월의 위험입니다. '
        '조건부 Digit 5 3억달러 초과 수주잔고는 사양·안전인증·고객 검수를 '
        '통과해야 출하·사용권·장기 유지보수 반복수익으로 전환됩니다. '
        '65,000시간 기존 기종 운용성과가 Digit 5 수율을 보장하지 않습니다.'
    ),
    ROBOT_OCT15_TITLES['rainbow_fcc_compliance']: (
        '신청은 승인 발급이 아니며 미국산 부품비율 계산·사이버보안 검토·'
        '설계변경·보험·공급망 인증이 6~12개월 미국 공급 지연 요인입니다. '
        '부품원가가 가정상 100억원이면 국내산 65억원 초과→75억원 초과로 '
        '2030년이 아니라 2029년 기준 10억원포인트가 더 필요합니다 '
        '(예시이며 RB-Y1 실제 원가는 공개되지 않음). '
        '기존 FCC 인증모델과 신규모델, 고정 산업용 로봇과 이동형 로봇을 구분해야 합니다.'
    ),
    ROBOT_OCT15_TITLES['xinjian_prs_ipo']: (
        '고객 익명 A사를 Tesla로 치환하는 것이 최대 오판입니다. '
        '회사의 중하중 행성 롤러스크루 주장은 업계 기술채택 독점 증명이 아닙니다. '
        '가공정밀도·볼스크루/롤러스크루 수명·백래시·고온 동작검사·수율 '
        '및 고객사 V3 설계 재변경을 6~12개월 확인해야 합니다. '
        '상반기 평균판매단가 하락과 기존 자동차 사업의 낮은 수익성이 역풍입니다.'
    ),
    ROBOT_OCT15_TITLES['unichem_loomia_acquisition']: (
        '거래종결 예정과 실제 인수완료는 다릅니다. 서명·외환신고·자금 조달 '
        '및 로봇 피부 고객 인증·접착·세척 내구성·전기 신뢰성·온도 반복성이 '
        '2027~2028년 상용화 병목입니다. 메타·아마존과 연구컨소시엄에 '
        '참여한다고 양사와 납품계약이 체결된 것은 아닙니다.'
    ),
    ROBOT_OCT15_TITLES['atlas_protoops_build']: (
        '시제품 하루는 실제 24시간 근무가 아닙니다. 제작시간 단축 목표를 '
        '연산 대수로 단순 환산할 수 없고, 검사시간·재작업률·조립수율·'
        '고장·안전인증이 6~12개월 위험입니다. '
        '양산품 적용 전에 대량생산 설비와 고객 인수 시험을 확인합니다.'
    ),
    ROBOT_OCT15_TITLES['alert_quality_qty_224225']: (
        '기간·시설·목표대수·시제품을 실제 출하량으로 잘못 표기하면 고객 수주가 과장됩니다. '
        '단위 경계검사와 제품 실명·단가 없는 범용 확인 물량 블록 제외를 적용하고, '
        '향후 실제 출하·수율·가격을 기업 공시와 대조합니다.'
    ),
    ROBOT_OCT15_TITLES['alert_quality_223']: (
        '주가·목표가 및 공급망 해설을 확정 수주와 혼동하면 알림 과밀과 '
        '수혜 과장이 발생합니다. 신규 계약·실적 원문이 없으면 '
        '향후 선별점수 0점으로 제외하고, 후속 계약이 실제 확인되면 다시 알립니다.'
    ),
}
for _later in set(_OCT15_MEANINGS)-set(_OCT15_RISKS):
    _OCT15_RISKS[_later] = (
        '이전 단계 달성과 신규 계약·출하·매출을 혼동하지 않습니다. '
        '향후 6~12개월 동안 공시·고객 검수·실제 수율·반복 발주를 확인합니다.'
    )


def _oct15_verification(group: str, text: str, source: str) -> str:
    if group == 'agility_spac_2026':
        return ('Agility Robotics 10/13 공식 보도자료와 SEC 8-K 첨부 원문 확인 · '
                'S-4 효력발생과 실제 Nasdaq 거래개시 구분')
    if group == 'rainbow_fcc_compliance':
        return ('전자신문 10/12 업체 취재에 따른 신청 제출 보도 · '
                'FCC DA 26-786·DA 26-996 규정 교차확인 · DoW 승인 미확인')
    if group == 'xinjian_prs_ipo':
        return ('신젠전동 10/12 IPO 심사 질의서 응답 동방재부 원문 재게시·'
                '21财经 보도 · A사 고객 실명 및 Tesla 공식 설계확정 미확인')
    if group == 'unichem_loomia_acquisition':
        return ('더벨·뉴스핌 회사발 본계약 보도 교차확인 · '
                '최종 거래종결과 실제 로봇 고객 매출은 미확인')
    if group == 'atlas_protoops_build':
        return ('Boston Dynamics 회사 제작 영상·Humanoids Daily 10/14 보도 대조 · '
                '제작시간은 목표, 완제품 양산 KPI 미확인')
    if group == 'alert_quality_qty_224225':
        return ('Run #598 원본 Telegram 224·225 실발송문 직접 확인 · '
                '12개월→12개·목표시설/목표물량 오인 정정')
    if group == 'alert_quality_223':
        return ('기존 Run #595 실수신 발송문·Python 선택 상태 대조 · '
                '2026-10-15 4건 모두 고신호 오탐으로 재분류')
    return '공식 추가확인 필요'



# 2026-10-15..16 high-signal events. Preserve the existing workflow, state,
# alert renderer and Telegram route. These four reports are independent:
# construction-classification policy, AMR localization plan, Hyundai RX
# organizational change, and LG robotics software integration report.
# Previously released ROBOTIS open-source control code is only a baseline.
ROBOT_OCT16_PREFIX = 'DIRECT_ROBOT_OCT16_'
ROBOT_OCT16_EVENTS = {
    'telegram233_quality_correction': {
        'group': 'alert_quality_oct18',
        'stage': 'correction',
        'source': '기존 GitHub Actions 발송문·실행기록',
        'title': '정정: Telegram 233번 ESS 일반 기사 고신호 철회·엔비디아 원화환산 오탐',
        'link': 'https://github.com/qedgwangju-dot/khs-watch/actions/runs/39101708735',
        'description': (
            '2026-10-18 Run #641 Telegram message_id=233 실제 발송문 검사 결과 '
            '1번 머니투데이 K배터리 3분기 실적 청신호·미국 ESS 설치량 일반 전망 '
            '기사를 별도 신규 수주·실적 확정 고신호로 볼 직접 계약 또는 '
            '검증된 신규 정량 설치 물량 증거가 없어 고신호 판정을 철회한다. '
            '기사에 나타난 시장 전망 자체를 부정하는 것은 아니다. '
            '같은 Telegram 233 LG전자 확인 문구에서 날짜 8/18 뒤 '
            '엔비디아를 18 엔화로 오인해 단어 중간에 원화 환산액을 '
            '삽입한 통화 인식 오류도 철회한다. '
            'LG전자의 로봇 소프트웨어 플랫폼 신설 보도와 기후부 ESS '
            '분류 지침, 브릴스 미국 현지 조립 추진, 현대차 RX사업전략팀 '
            '신설 등 나머지 네 건의 구분된 사실은 유지한다. '
            '외화 숫자 바로 뒤의 진짜 통화 단위만 변환하고 '
            '기업 고유명사·날짜와 일반 전망은 제외하는 회귀검사를 추가했다. '
            '이번 정정은 새로운 공급계약·실적 또는 사업 예산 발표가 아니다.'
        ),
    },
    'ess_outdoor_guideline': {
        'group': 'ess_outdoor_policy',
        'stage': 'official_guideline',
        'source': '기후에너지환경부',
        'title': '기후부, 옥외형 ESS 시설물 분류 지침 확정·전국 배포',
        'link': 'https://eiec.kdi.re.kr/policy/materialView.do?num=288155',
        'description': (
            '2026-10-15 기후에너지환경부·국무조정실은 국토교통부 협의를 거쳐 '
            '전국 지방정부에 옥외형 ESS 건축물·가설건축물·공작물 분류 기준을 배포했다. '
            '출입 불가 전용 외함은 공작물, 점검을 위한 제한적 출입 허용은 가설건축물, '
            '사람이 상시 출입하는 전용 건물은 건축물로 나눈다. '
            '정부 전망은 기존 대비 일부 해당 사업장에 한해 인허가 기간 최대 3개월, '
            '설치 관련 비용 최대 7,000만원 절감이며 전국 모든 현장의 실제 절감액이 아니다. '
            '사업장 100곳 모두 최고 절감액을 달성하면 이론상 70억원이지만 '
            '확정 예산·지원금·ESS 구매 계약과 다르다. '
            '정부 신규 배정 예산은 발표하지 않았다. '
            '안전·소방·열폭주·배기·방폭·냉각·보험, 부지와 송전 접속, '
            '전원 인가 시점에 필요한 별도 심사·비용은 면제하지 않는다. '
            '배터리셀·전력변환장치·에너지관리시스템·소방·전기공사 업체의 '
            '실제 수주와 지침으로 단축된 인허가 사례를 별도로 확인한다.'
        ),
    },
    'brils_us_amr_production_plan': {
        'group': 'brils_us_localization',
        'stage': 'reported_local_production_plan',
        'source': '전자신문',
        'title': '브릴스, 미시간 미국 AMR 현지 조립·생산 추진…계약·가동 전',
        'link': 'https://www.etnews.com/20261016000210?m=1',
        'description': (
            '2026-10-16 브릴스(468670) 회사 발표를 전한 전자신문·이데일리: '
            '미시간 그랜드래피즈의 BRILS USA LLC 법인을 북미 영업·기술지원에서 '
            '미국 현지 조립·생산 거점으로 확대 추진한다. '
            '우선 포크형·저상형 자율이동로봇 AMR을 현지 조립하고 '
            '피지컬 AI 로봇으로 장래 확대를 계획한다. '
            '미국 전기차·자동차부품 업체와 AMR 공급은 협의 중으로 '
            '북미 신계약 금액·확정 고객·현지 생산 시작일·출하대수는 미공개다. '
            '기존 2026년 상반기 미국 수출 371만달러, 북미 누적 수출 1,504만달러는 '
            '서로 다른 기간의 과거 수출 실적이다. '
            '2026-10-15 서울외국환중개 달러 매매기준율 1,338.60원을 '
            '단순 적용한 참고 원화는 각각 49억6,620만6,000원과 201억3,254만4,000원이며 '
            '수출 당시 회계상 실제 환산매출과 다르다. '
            '2026년 상반기 연결 매출 약 136억5,709만원, 영업이익 약 8억4,120만원, '
            '순이익 약 9억1,057만원은 과거 분기 아닌 반기 누적 실적이다. '
            '현지화 목적은 미국 FCC 규제에 따른 인증·원산지 불확실성 완화와 '
            '부품 조달·서비스 현지화다. '
            '로봇 본체 장비 일회성 매출, 자체 BRILS Navigation 및 FMS 관제·'
            '유지보수의 잠재 반복매출은 구분하며 기존 판매계약의 반복수주로 추정하지 않는다.'
        ),
    },
    'hyundai_rx_strategy_team': {
        'group': 'hyundai_robot_rx_team',
        'stage': 'company_sourced_team_report',
        'source': '머니투데이',
        'title': '현대차그룹, 미래사업전략실 산하 RX사업전략팀 신설',
        'link': 'https://www.mt.co.kr/industry/2026/10/15/2026101514482769434',
        'description': (
            '2026-10-15 머니투데이 회사 관계자 인용·이데일리 교차확인: '
            '현대자동차그룹이 미래사업전략실 산하 RX사업전략팀을 신설했다. '
            '그룹은 RX를 로보틱스 에브리싱으로 재정의해 '
            '현대차·기아 로보틱스랩, 보스턴다이내믹스, 현대모비스·현대글로비스의 '
            '로봇 사업전략·양산원가·외부 판매와 공급망을 조율하는 목적이다. '
            '2028년 미국 HMGMA Atlas 활용은 이전 발표 계획으로 '
            '이번 조직 신설이 로봇 양산 개시·외부 판매·유상 계약은 아니다. '
            '조직 예산·새 설비투자 액수·신규 고객·판매대수는 공개되지 않았다. '
            '향후 실제 조직 공식 발표와 로봇 외부 고객 유상 수주, '
            '로봇 구매·작업 가동률·인수시험·유지보수 책임을 분리해 확인한다.'
        ),
    },
    'lg_robot_software_platform_team': {
        'group': 'lge_robot_sw_platform',
        'stage': 'industry_sourced_sw_team',
        'source': 'ZDNet korea',
        'title': 'LG전자, 로봇 소프트웨어 플랫폼 통합 조직 신설 보도',
        'link': 'https://zdnet.co.kr/view/?no=20261016135133',
        'description': (
            '2026-10-16 ZDNet korea 로봇업계 취재: LG전자 로보틱스사업센터 '
            '산하에 여러 사업부의 로봇 소프트웨어 개발 인력을 모은 '
            '로봇 소프트웨어 플랫폼 조직을 신설하고 '
            'ETRI 출신 김영준 전무가 맡는다는 보도다. '
            '조직 인사·세부 업무범위에 관한 회사 공식 10월 보도자료는 확인되지 않았다. '
            '회사 2026-06-30 CEO 직속 로보틱스사업센터 신설은 이미 공식 확정됐고 '
            '8월 18일 NVIDIA 협력과 양재 1만㎡ 데이터팩토리 4개층, '
            '연내 로봇 수백 대·학습데이터 10만시간 목표는 이전 공식 발표다. '
            '7월 말 창원 AXIUM 액추에이터 시범생산 시작도 기존 사실이며 '
            '유료 고객 주문·반복 소프트웨어 사용권 매출과 혼동하지 않는다. '
            '플랫폼은 로봇 제어·계획·학습·시뮬레이션·운영체제·미들웨어를 통합해 '
            '클로이드와 산업·상업용 로봇에 적용하려는 준비 단계다. '
            '회사 직접 조직 확인, 외부 로봇 고객명, 상용 사용권·원격관제·'
            '장기 유지보수 계약과 고객 사용량을 확인한다.'
        ),
    },
}
ROBOT_OCT16_GROUPS = {k:v['group'] for k,v in ROBOT_OCT16_EVENTS.items()}
ROBOT_OCT16_TITLES = {
    'alert_quality_oct18': '알림 품질 정정 · Telegram 233 고신호·통화인식 오류',
    'ess_outdoor_policy': '기후부 · 옥외형 ESS 분류지침 전국 배포',
    'brils_us_localization': '브릴스 · 미시간 AMR 현지 생산체계 추진',
    'hyundai_robot_rx_team': '현대차그룹 · RX사업전략팀 신설',
    'lge_robot_sw_platform': 'LG전자 · 로봇 소프트웨어 플랫폼 조직 신설 보도',
    'robotis_open_source_baseline': '로보티즈 · 8월 소프트웨어 기존 공개·하드웨어 공개 예정',
    'robotis_hardware_release': '로보티즈 · 하드웨어 설계도 실제 공개 공식 확인',
}
ROBOT_OCT16_GROUP_PATS = (
    ('ess_outdoor_policy',
     re.compile(r'기후에너지환경부|기후부|옥외형\s*(?:에너지저장장치|ESS)',re.I),
     re.compile(r'(?:ESS|에너지저장장치).{0,180}(?:시설물\s*분류|공작물|가설건축물|분류\s*지침)|(?:시설물\s*분류|가설건축물|공작물).{0,180}(?:ESS|에너지저장장치)',re.I)),
    ('brils_us_localization',
     re.compile(r'브릴스|BRILS',re.I),
     re.compile(r'미시간|Grand\s*Rapids|BRILS\s*USA|미국.{0,45}(?:현지\s*생산|AMR)|북미.{0,45}(?:현지\s*생산|AMR)',re.I)),
    ('hyundai_robot_rx_team',
     re.compile(r'현대차(?:그룹)?|현대자동차(?:그룹)?|Hyundai\s*Motor',re.I),
     re.compile(r'RX사업전략팀|RX\s*사업\s*전략팀|robotics\s*everything',re.I)),
    ('lge_robot_sw_platform',
     re.compile(r'LG전자|LG\s*Electronics',re.I),
     re.compile(r'로봇\s*(?:소프트웨어|SW)\s*플랫폼\s*(?:조직|팀)|robotics\s*software\s*platform\s*(?:team|organization)',re.I)),
)
ROBOT_OCT16_PRIMARY = {
    'ess_outdoor_policy': {'기후에너지환경부','국무조정실'},
    'brils_us_localization': {'브릴스','BRILS'},
    'hyundai_robot_rx_team': {'현대자동차그룹','Hyundai Motor Group'},
    'lge_robot_sw_platform': {'LG전자','LG Electronics'},
}
ROBOT_OCT16_REPORTERS = {
    'brils_us_localization': {'전자신문','이데일리','프라임경제'},
    'hyundai_robot_rx_team': {'머니투데이','이데일리'},
    'lge_robot_sw_platform': {'ZDNet korea','지디넷코리아'},
}
ROBOT_OCT16_REVERSE = re.compile(
    r'계획\s*(?:취소|중단|철회)|사업\s*(?:취소|중단|철회)|'
    r'취소\s*확정|공식\s*철회|cancelled|terminated|abandoned',
    re.I,
)


def _oct16_group(text: str) -> str:
    if '정정: Telegram 233' in text:
        return 'alert_quality_oct18'
    for group, actor, topic in ROBOT_OCT16_GROUP_PATS:
        if actor.search(text) and topic.search(text):
            return group
    if re.search(r'로보티즈|ROBOTIS',text,re.I) and re.search(
        r'오픈\s*소스|오픈소스|전면\s*개방|핵심\s*코드|'
        r'하드웨어.{0,30}(?:설계도|CAD|회로도|오픈)',text,re.I
    ):
        if re.search(r'(?:CAD|회로도|설계도).{0,60}(?:실제\s*공개|공개\s*완료|업로드\s*완료|릴리스|released)|'
                     r'(?:실제\s*공개|공개\s*완료|release).{0,60}(?:CAD|회로도|설계도)',text,re.I):
            return 'robotis_hardware_release'
        return 'robotis_open_source_baseline'
    return ''


def _oct16_stage(group: str, text: str, source: str = '') -> str:
    if group == 'alert_quality_oct18':
        return 'correction' if source == '기존 GitHub Actions 발송문·실행기록' else 'background'
    if group == 'robotis_open_source_baseline':
        return 'already_public_baseline'
    if group == 'robotis_hardware_release':
        if source in {'ROBOTIS','로보티즈'} and not re.search(r'계획|예정|추진|will|plan',text,re.I):
            return 'official_hardware_release'
        return 'background'
    if ROBOT_OCT16_REVERSE.search(text):
        if source in ROBOT_OCT16_PRIMARY.get(group,set()):
            return 'official_reversal'
        return 'background'
    if group == 'ess_outdoor_policy':
        if source in ROBOT_OCT16_PRIMARY[group] and re.search(
            r'지침(?:서)?|가이드라인',text,re.I
        ) and re.search(r'배포|일원화|전국\s*안내|확정|published|issued',text,re.I):
            return 'official_guideline'
    if group == 'brils_us_localization':
        if source in ROBOT_OCT16_PRIMARY[group] and re.search(
            r'현지.{0,40}(?:조립|생산).{0,30}(?:가동|첫\s*출하|실제\s*생산\s*개시)|'
            r'미국.{0,30}(?:생산\s*(?:시작|개시)|첫\s*납품)|'
            r'(?:미국|미시간).{0,45}(?:실제\s*)?(?:AMR.{0,12})?생산\s*(?:시작|개시|완료)|'
            r'started\s*US\s*production',
            text,re.I
        ) and not re.search(r'예정|계획|추진|협의|논의',text,re.I):
            return 'official_us_production'
        if source in ROBOT_OCT16_PRIMARY[group] and re.search(
            r'(?:유상|확정|정식)\s*(?:공급|구매)\s*계약\s*체결|'
            r'signed\s*supply\s*contract',
            text,re.I
        ) and not re.search(r'예정|논의|협의|추진',text,re.I):
            return 'official_customer_contract'
        if source in ROBOT_OCT16_REPORTERS[group] and re.search(
            r'현지.{0,65}(?:생산|조립).{0,50}(?:추진|계획|구축)|'
            r'(?:생산|조립)\s*체제.{0,20}(?:구축|추진)|'
            r'현지\s*생산|미시간\s*생산',
            text,re.I
        ):
            return 'reported_local_production_plan'
    if group == 'hyundai_robot_rx_team':
        if source in ROBOT_OCT16_PRIMARY[group] and re.search(r'팀\s*신설|조직\s*신설|established|formed',text,re.I):
            return 'official_team_confirmation'
        if source in ROBOT_OCT16_REPORTERS[group] and re.search(r'신설|출범|조직개편',text,re.I):
            return 'company_sourced_team_report'
    if group == 'lge_robot_sw_platform':
        if source in ROBOT_OCT16_PRIMARY[group] and re.search(r'팀\s*신설|조직\s*신설|플랫폼\s*조직\s*확인|formed',text,re.I):
            return 'official_sw_team'
        if source in ROBOT_OCT16_REPORTERS[group] and re.search(r'신설|출범|통합',text,re.I):
            return 'industry_sourced_sw_team'
    return 'background'


def _oct16_recovery(event_id: str) -> list[dict]:
    # One event per semantic stage; do not manufacture publication hours.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,25):
        return []
    event=ROBOT_OCT16_EVENTS.get(event_id)
    if not event:
        return []
    return [{
        'title':event['title'], 'link':event['link'],
        'description':event['description'], 'source':event['source'],
        'published':None, 'direct_recovery':True,
        'oct16_event_id':event_id, 'oct16_stage':event['stage'],
    }]


def _oct16_render_category(group: str, text: str) -> str:
    if group == 'brils_us_localization':
        if re.search(r'미국\s*(?:실제|현지).{0,25}(?:생산\s*개시|초도\s*출하\s*완료)',text,re.I):
            return '브릴스 · 미시간 AMR 실제 생산·첫 출하 공식 확인'
        if re.search(r'미국.{0,100}공급계약\s*체결\s*공식\s*확인',text,re.I):
            return '브릴스 · 미국 고객 유상 계약 공식 확인'
    if group == 'hyundai_robot_rx_team' and re.search(r'RX사업전략팀.{0,60}회사\s*공식\s*확인',text,re.I):
        return '현대차그룹 · RX사업전략팀 회사 공식 확인'
    if group == 'lge_robot_sw_platform' and re.search(r'로봇\s*소프트웨어\s*플랫폼.{0,60}회사\s*공식\s*확인',text,re.I):
        return 'LG전자 · 로봇 소프트웨어 플랫폼 회사 공식 확인'
    return ROBOT_OCT16_TITLES[group]


ROBOT_OCT16_MEANINGS = {
    '알림 품질 정정 · Telegram 233 고신호·통화인식 오류': (
        '10/18 Telegram 233의 1번 K배터리 일반 업황 기사는 '
        '신규 고객계약·공식 실적 공시로 볼 직접 근거가 없어 별도 고신호 판정을 철회합니다. '
        'LG전자 확인문에 나온 8/18 엔비디아는 날짜와 기업명이지 '
        '18엔 통화금액이 아닌데 환산액을 넣은 오탐도 철회합니다. '
        '정부 ESS 지침·브릴스 현지 생산계획·LG 소프트웨어팀 보도·'
        '현대차 RX팀 신설의 증거 수준과 고신호 구분은 유지합니다. '
        '향후 실제 계약·출하·정량 설치 발표와 포괄 업황 기사를 분리합니다.'
    ),
    '기후부 · 옥외형 ESS 분류지침 전국 배포': (
        '정부·국무조정실은 10/15 옥외형 ESS 시설물 유형 판단 기준을 배포했습니다. '
        '출입 불가 전용 외함은 공작물, 점검용 제한적 출입은 가설건축물, '
        '상시 출입 전용 건물은 건축물입니다. '
        '정부가 제시한 절감 상한은 사업장당 인허가 최대 3개월·비용 최대 7,000만원입니다. '
        '100개 사업장이 모두 최대 절감액을 달성해야 70억원이라는 단순 상한 계산이며 '
        '국비 보조금·신규 ESS 설비투자·확정 매출이 아닙니다. '
        '향후 지자체 실제 적용건수, 전력망 접속·안전허가·착공 시점을 확인합니다.'
    ),
    '브릴스 · 미시간 AMR 현지 생산체계 추진': (
        '브릴스(468670)가 미국 미시간 BRILS USA LLC 거점에서 포크형·저상형 AMR '
        '현지 조립·생산체계를 추진하고 있습니다. '
        '기존 2026년 상반기 미국 수출 371만달러(10/15 환율 적용 약 49억6,621만원), '
        '북미 누적 수출 1,504만달러(약 201억3,254만원)는 서로 다른 과거 기간입니다. '
        '상반기 연결 매출 약 136억5,709만원·영업이익 약 8억4,120만원을 확인했습니다. '
        '미국 OEM 공급은 협의 단계이며 새 계약액·현지 실제 조립 물량은 비공개입니다. '
        '로봇 완제품 일회성 매출과 BRILS Navigation/FMS 통합관제·유지보수 '
        '잠재 반복매출을 구분해 후속 수주를 검증합니다.'
    ),
    '현대차그룹 · RX사업전략팀 신설': (
        '10/15 현대차그룹 미래사업전략실의 RX사업전략팀 출범 보도로 '
        '기존 Atlas·Spot·모베드 등 사업을 양산 원가·공급망·외부 판로와 '
        '연결하는 전략 전담 조직이 확인됐습니다. '
        '2028년 미국 HMGMA Atlas 투입 계획은 이전 발표이며 '
        '조직 신설 자체는 양산 시작·신규 주문·매출이 아닙니다. '
        '회사 공식 조직 확정·별도 신규 고객·외부 유상 주문·로봇 대수를 추적합니다.'
    ),
    'LG전자 · 로봇 소프트웨어 플랫폼 조직 신설 보도': (
        '10/16 ZDNet 업계 취재로 LG전자가 로보틱스사업센터 산하 '
        '로봇 소프트웨어 플랫폼 전담 조직을 신설하고 김영준 전무가 '
        '지휘한다고 보도됐습니다. '
        '6/30 CEO 직속 로보틱스사업센터, 7월 말 AXIUM 초도생산, '
        '8/18 양재 데이터팩토리 1만㎡·로봇 수백대·10만시간 학습 목표와 '
        'NVIDIA 협력은 회사 기존 공식 발표로 이미 새로운 계약이 아닙니다. '
        '이번 뉴스의 신규성은 조직 통합이며 유상 플랫폼 사용권·'
        '원격관제·장기 유지보수 계약은 미확인입니다.'
    ),
    '로보티즈 · 하드웨어 설계도 실제 공개 공식 확인': (
        '로보티즈의 기존 8월 로봇 구동 소프트웨어 공개와 '
        '향후 하드웨어 CAD·전자회로도 실제 배포를 구분합니다. '
        '실제 공식 파일 배포 시에는 부품 제조·액추에이터 공급·'
        '개발 생태계 유입이 새로운 단계입니다. '
        '파일·사용권 조건·실제 유상 액추에이터 주문은 별도로 확인합니다.'
    ),
}
ROBOT_OCT16_RISKS = {
    '알림 품질 정정 · Telegram 233 고신호·통화인식 오류': (
        '이번 정정 자체가 신규 수주나 공급 증거는 아닙니다. '
        '후속 알림은 회사 공시·조달·실제 설치량·계약금액을 확인하며, '
        '외화 환산은 날짜·고유명사를 분리해 검증합니다.'
    ),
    '기후부 · 옥외형 ESS 분류지침 전국 배포': (
        '건축물 분류 간소화만으로 화재·열폭주·배기·방폭·냉각·보험과 '
        '계통접속·소방검사까지 면제되지 않습니다. '
        '6~12개월 지자체 분류 적용편차, 실제 인허가 단축일수, '
        'ESS 착공·전원 인가 전력망 병목을 추적합니다.'
    ),
    '브릴스 · 미시간 AMR 현지 생산체계 추진': (
        '최대 역풍은 미국 현지 생산·부품 조달 준비가 완료돼도 '
        '원산지 규정·FCC 적합성·제품 인증·현지 검수·보험에서 '
        '지연돼 매출로 전환되지 못하는 것입니다. '
        '향후 6~12개월 실제 첫 조립대수·유상 계약·FMS 사용권 갱신과 '
        '설치·원격관제 비용을 확인합니다. '
        '중국산 부품 대체 시 원가상승·납기 변동을 분리합니다.'
    ),
    '현대차그룹 · RX사업전략팀 신설': (
        '조직만 생기고 Atlas 부품 직행수율·고온 동작 검사·'
        '양산 비용이 개선되지 않으면 실적에 연결되지 않습니다. '
        '6~24개월 RMAC 실제 작업 성공률, 안전요원·원격지원·'
        '정비비·공장 투입대수·외부 유상 주문을 확인합니다.'
    ),
    'LG전자 · 로봇 소프트웨어 플랫폼 조직 신설 보도': (
        '업계 보도 조직 신설과 회사 직접 인사·조직 공시는 구분합니다. '
        '소프트웨어 통합이 가동률·작업성공률 개선으로 연결되지 않으면 '
        '데이터팩토리·AXIUM 설비의 고정비 부담이 늘어날 수 있습니다. '
        '6~12개월 회사 공식 조직확인·고객 검증·로봇 실제 투입대수, '
        '손·촉각센서·안전·신뢰성 시험·소프트웨어 사용권 매출을 봅니다.'
    ),
    '로보티즈 · 하드웨어 설계도 실제 공개 공식 확인': (
        'CAD 공개와 실제 완성품 공급계약은 다릅니다. '
        '안전·인증·액추에이터 수율·공급망 품질·부품 원가 개선이 필요합니다.'
    ),
}


def _oct16_category(group: str, text: str) -> str:
    return _oct16_render_category(group,text)


def _oct16_score(item: dict, group: str, text: str) -> int:
    stage=_oct16_stage(group,text,item.get('source') or '')
    # Even internally seeded articles must independently satisfy source,
    # claim wording and stage rules. A wrong tag must never force an alert.
    if item.get('oct16_event_id') and item.get('oct16_stage') != stage:
        return 0
    return {
        'correction': 98,
        'official_guideline': 82,
        'reported_local_production_plan': 51,
        'official_us_production': 88,
        'official_customer_contract': 90,
        'company_sourced_team_report': 43,
        'official_team_confirmation': 71,
        'industry_sourced_sw_team': 45,
        'official_sw_team': 71,
        'official_hardware_release': 78,
        'official_reversal': 88,
    }.get(stage,0)


def _oct16_key(item: dict, group: str, text: str) -> str:
    # Canonical semantic key belongs to evidence stage, never title/publisher.
    stage=_oct16_stage(group,text,item.get('source') or '')
    return hashlib.sha256(f'robot-oct16|{group}|{stage}|2026-10'.encode()).hexdigest()


def _oct16_verification(item: dict, group: str, text: str) -> str:
    source=item.get('source') or ''
    if group == 'alert_quality_oct18':
        return (
            'Run #641 실제 Telegram 233 원문과 기업명·날짜·통화 환산 로그 확인 · '
            '신규 계약 없는 일반 업황 기사 고신호 판정 철회'
        )
    if group == 'ess_outdoor_policy':
        return (
            '기후에너지환경부 10/15 보도자료 KDI 등록본·뉴스1·아주경제 교차확인 · '
            '정식 지침 배포, 사업별 인허가·절감 실적·ESS 수주와 별개'
        )
    if group == 'brils_us_localization':
        stage=_oct16_stage(group,text,source)
        if item.get('oct16_stage'):
            stage=item['oct16_stage']
        if stage == 'reported_local_production_plan':
            return (
                '10/16 브릴스 발표를 인용한 전자신문·이데일리·프라임경제 · '
                '상반기 실적은 뉴스핌·회사 자료 인용 보도 · '
                '미국 공장 첫 가동·신규 유상 고객 계약은 미확인'
            )
        return '회사 직접 현지 가동·계약자료 별도 확인 필요'
    if group == 'hyundai_robot_rx_team':
        return (
            '10/15 머니투데이 그룹 관계자 인용·이데일리 교차확인 · '
            '별도 그룹 공식 조직 공지 미확인 · 신규 양산·계약 아님'
        )
    if group == 'lge_robot_sw_platform':
        return (
            '10/16 ZDNet 업계 인용 보도 · 회사 6/30 조직·8/18 '
            'NVIDIA/데이터팩토리 공식자료는 기존 배경 · '
            '새 하부 조직·책임자 회사 직접 공식발표 미확인'
        )
    return 'ROBOTIS 공식 설계도 배포·라이선스·실제 고객 수주 재확인'


def _oct16_clean_title(title: str, source: str) -> str:
    for event in ROBOT_OCT16_EVENTS.values():
        if title == event['title']:
            return title
    return title



# Micron EIM: an executive-described R&D direction reported on 2026-10-16,
# NOT a Micron-issued production schedule or a contracted humanoid DRAM.
# Keep this product lane separate from Counterpoint's blended 19->39GB DRAM
# demand forecast, from LPDDR today and from server-side HBM/PIM.
MICRON_EIM_RECOVERY = 'DIRECT_MICRON_EIM_SEDEX_20261016_REPORTED_RND'
MICRON_EIM_SOURCE_URL = 'https://www.thelec.kr/news/articleView.html?idxno=63825'
MICRON_EIM_MICRON_ROBOTICS_URL = (
    'https://www.micron.com/about/blog/applications/industrial/'
    'the-rise-of-smarter-robots-and-why-memory-is-becoming-their-superpower'
)
MICRON_EIM_PRIMARY_SOURCES = {'Micron', 'Micron Technology', '마이크론', 'Micron Technology Inc.'}
MICRON_EIM_TRUSTED_REPORTERS = {'디일렉', 'The Elec', 'THE ELEC'}
MICRON_EIM_ID = re.compile(
    r'\bEIM\b|Edge\s*Inference\s*Memory|엣지\s*(?:인퍼런스|추론)\s*메모리',
    re.I,
)
MICRON_EIM_VENDOR = re.compile(r'\bMicron\b|마이크론|美光', re.I)
MICRON_EIM_CONTEXT = re.compile(
    r'LPDDR|저전력\s*D램|DRAM|메모리|memory|'
    r'휴머노이드|humanoid|physical\s*AI|피지컬\s*AI|로봇|robot|추론|inference',
    re.I,
)
MICRON_EIM_RND = re.compile(
    r'develop(?:ing|ment)?|in\s+development|R&D|planning|'
    r'개발|준비|추진|협의|discuss(?:ing)?|SEDEX|논의',
    re.I,
)
MICRON_EIM_SAMPLE = re.compile(
    r'(?:EIM|엣지\s*(?:인퍼런스|추론)\s*메모리).{0,130}'
    r'(?:샘플\s*(?:납품|출하|공급\s*개시|제공\s*시작|검증\s*통과)|'
    r'(?:customer|qualification)\s*samples?\s*(?:shipped|delivered))|'
    r'(?:샘플\s*(?:납품|출하|공급\s*개시|제공\s*시작)).{0,130}\bEIM\b',
    re.I,
)
MICRON_EIM_CUSTOMER = re.compile(
    r'(?:EIM|엣지\s*(?:인퍼런스|추론)\s*메모리).{0,180}'
    r'(?:고객\s*최종\s*선정|고객\s*정식\s*채택|디자인윈|design\s*win|'
    r'구매\s*계약\s*체결|supply\s*contract\s*signed)|'
    r'(?:design\s*win|디자인윈|정식\s*공급계약).{0,180}\bEIM\b',
    re.I,
)
MICRON_EIM_SOP = re.compile(
    r'(?:EIM|엣지\s*(?:인퍼런스|추론)\s*메모리).{0,150}'
    r'(?:양산\s*(?:개시|시작|돌입|완료)|상업\s*출하\s*시작|mass\s*production\s*(?:started|began)|'
    r'first\s*commercial\s*shipments?\s*(?:started|began))|'
    r'(?:양산\s*(?:개시|시작|돌입)).{0,150}\bEIM\b',
    re.I,
)
MICRON_EIM_NEGATIVE = re.compile(
    r'양산\s*(?:예상|계획|목표|예정|검토|미확정|시점\s*전)|'
    r'(?:mass\s*production|commercial\s*shipment).{0,45}'
    r'(?:expected|target|planned|tentative|unconfirmed)|'
    r'(?:not\s*(?:yet\s*)?(?:produced|shipped|commercialized))',
    re.I,
)


def _is_micron_eim(text: str) -> bool:
    return bool(
        MICRON_EIM_ID.search(text)
        and MICRON_EIM_VENDOR.search(text)
        and MICRON_EIM_CONTEXT.search(text)
    )


def _micron_eim_primary(item: dict) -> bool:
    # Media quoting a Micron executive != Micron company-issued milestone.
    # Trust both publisher identity and an unchanged Micron-owned origin URL.
    return bool(
        (item.get('source') or '') in MICRON_EIM_PRIMARY_SOURCES
        and re.match(
            r'^https?://(?:[a-z0-9-]+\.)*micron\.com(?:/|$)',
            item.get('link') or '', re.I,
        )
    )


def _micron_eim_stage(text: str, item: dict) -> str:
    if not _is_micron_eim(text):
        return ''
    if _micron_eim_primary(item):
        if MICRON_EIM_SOP.search(text) and not MICRON_EIM_NEGATIVE.search(text):
            return 'company_confirmed_sop'
        if MICRON_EIM_CUSTOMER.search(text) and not MICRON_EIM_NEGATIVE.search(text):
            return 'company_confirmed_customer'
        if MICRON_EIM_SAMPLE.search(text) and not MICRON_EIM_NEGATIVE.search(text):
            return 'company_confirmed_sample'
        if MICRON_EIM_RND.search(text):
            return 'company_confirmed_rnd'
    if ((item.get('source') or '') in MICRON_EIM_TRUSTED_REPORTERS
            and MICRON_EIM_RND.search(text)
            and re.match(
                r'^https?://(?:www\.)?thelec\.kr/',
                item.get('link') or '', re.I,
            )):
        return 'executive_reported_rnd'
    return 'background'


def _micron_eim_display_stage(text: str) -> str:
    # The existing Telegram renderer passes title + description but drops
    # item['source']. Stage wording is therefore recovered from unambiguous
    # outcome phrases; reported 2028 targets never render as achieved SOP.
    if MICRON_EIM_SOP.search(text) and not MICRON_EIM_NEGATIVE.search(text):
        return 'company_confirmed_sop'
    if MICRON_EIM_CUSTOMER.search(text) and not MICRON_EIM_NEGATIVE.search(text):
        return 'company_confirmed_customer'
    if MICRON_EIM_SAMPLE.search(text) and not MICRON_EIM_NEGATIVE.search(text):
        return 'company_confirmed_sample'
    if re.search(r'마이크론\s*공식\s*EIM|Micron\s*official\s*EIM',text,re.I):
        return 'company_confirmed_rnd'
    return 'executive_reported_rnd'


def _micron_eim_recovery() -> list[dict]:
    # One-time backfill of the 10/16 executive presentation reported by
    # The Elec. Source gives the date, not a verified publication hour.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 24):
        return []
    return [{
        'title': '마이크론 EIM 로봇용 저전력 D램 적층 설계 개발 공개…SEDEX 2026',
        'link': MICRON_EIM_SOURCE_URL,
        'description': (
            '디일렉이 2026-10-16 서울 SEDEX 휴머노이드 반도체 세션에서 '
            '이철 마이크론 상무의 발언을 직접 보도했다. '
            '마이크론은 피지컬 AI용 엣지 추론 메모리(EIM)를 개발하고 '
            '주요 고객과 제품 요구사항을 협의 중이다. EIM은 논리 칩 위에 '
            '저전력 D램 LPDDR을 수직 적층해 AI 추론용 데이터 전송 지연을 '
            '줄이고 대역폭을 높이려는 설계다. '
            '이는 메모리 내부 연산을 뜻하는 PIM과 다르며 '
            '데이터센터용 HBM이 이미 휴머노이드에 EIM으로 양산 공급된다는 뜻도 아니다. '
            '구체적인 EIM 용량·대역폭·지연시간·전력·고온 동작 검사·수율·검증고객은 '
            '공개되지 않았다. LPDDR6 기반 EIM 2028년 하반기 양산은 '
            '회사 확정 일정이 아니라 기사에서 소개한 업계 예상이다. '
            '이철 상무는 현재 일반 서비스 로봇 12GB D램·256GB 저장장치 대비 '
            '미래 고성능 휴머노이드에는 200GB D램·4TB 저장장치가 '
            '필요할 수 있다고 전망했다. 이는 2030 산업 평균 39GB라는 '
            '카운터포인트리서치 전망과 다른 고성능 미래 시나리오다. '
            '마이크론 공식 로보틱스 블로그는 기존 휴머노이드용 '
            '16~128GB LPDDR5·5X 및 1~4TB SSD 적용 범위를 소개하지만 '
            'EIM 자체의 시제품·고객 인증·양산·계약 매출을 공식 발표하지 않았다. '
            '가정에 따른 민감도: 고사양 200GB 탑재 로봇 10만 대라면 '
            '메모리 용량 2,000만GB, 실현 가격 1GB당 1,000원 차이마다 '
            '가상 매출 200억원 변동이다. 실제 판매량이나 공급가격은 아니다.'
        ),
        'source': '디일렉',
        'published': None,
        'direct_recovery': True,
        'executive_reported_development': True,
    }]


# DIGITIMES 2026-10-19: anonymous US supply-chain statement concerning
# Chinese BESS SYSTEM INTEGRATORS, not verified Chinese cell-supplier exit.
# Never label an industry interview as a named company's completed shutdown.
CN_ESS_US_RETREAT_ID = 'DIGITIMES_CN_BESS_US_20261019_771701'
CN_ESS_US_RETREAT_URL = (
    'https://www.digitimes.com.tw/tech/dt/n/shwnws.asp?'
    'CnlID=1&Cat=90&id=0000771701_AKR6XDK313NXUP0KYL64J'
)
CN_ESS_US_RETREAT_TITLE = (
    'DIGITIMES: 중국계 ESS 시스템업체 미국 사업 집단 철수설…회사별 확인 전'
)
CN_ESS_US_CN = re.compile(r'중국|中系|中國|中国|China|Chinese|PRC',re.I)
CN_ESS_US_ESS = re.compile(r'ESS|BESS|儲能|储能|energy\s*storage|에너지\s*저장',re.I)
CN_ESS_US_AMERICA = re.compile(r'미국|美國|美国|撤美|U\.S\.|US\s+market|United\s+States|America',re.I)
CN_ESS_US_EXIT = re.compile(
    r'集體撤美|集体撤美|退出營運|退出营运|철수|철수설|'
    r'withdrawal|retreat|US\s+exit|exited\s+the\s+US|'
    r'(?:미국|US).{0,55}(?:영업\s*종료|사업\s*종료)|'
    r'(?:US|America).{0,40}(?:shutdown|exit|closure)',
    re.I,
)
CN_ESS_US_NEGATED = re.compile(
    r'철수\s*부인|철수하지\s*않|美國.{0,30}否認|'
    r'denies?\s+(?:the\s+)?(?:exit|withdrawal)|'
    r'not\s+(?:exiting|withdrawn)|considering\s+(?:withdrawal|exit)|'
    r'철수\s*(?:검토|계획|예정)|plans?\s+to\s+(?:exit|withdraw)',
    re.I,
)
CN_ESS_US_FINAL_EXIT = re.compile(
    r'(?:미국|美国|美國|US|U\.S\.).{0,110}'
    r'(?:ESS|BESS|儲能|储能|energy\s*storage|에너지저장).{0,120}'
    r'(?:사업\s*철수\s*완료|영업\s*종료|사업\s*종료\s*확정|'
    r'正式退出|已退出|終止營運|终止运营|ceased\s+operations|'
    r'completed\s+withdrawal|closed\s+its\s+US\s+operations)',
    re.I,
)
CN_ESS_US_VENDOR_DOMAINS = {
    'CATL': ('catl.com', {'CATL','宁德时代','寧德時代'}),
    'Sungrow': ('sungrowpower.com', {'Sungrow','阳光电源','陽光電源'}),
    'BYD': ('byd.com', {'BYD','比亚迪','比亞迪'}),
    'HiTHIUM': ('hithium.com', {'HiTHIUM','海辰储能','海辰儲能'}),
    'HyperStrong': ('hyperstrong.com', {'HyperStrong','海博思创','海博思創'}),
}


def _is_cn_ess_us_exit(text: str) -> bool:
    chinese = CN_ESS_US_CN.search(text) or re.search(
        r'\bCATL\b|\bSungrow\b|\bBYD\b|\bHiTHIUM\b|\bHyperStrong\b|'
        r'宁德时代|陽光電源|阳光电源|海辰储能|海博思创',text,re.I
    )
    return bool(
        chinese and CN_ESS_US_ESS.search(text)
        and CN_ESS_US_AMERICA.search(text)
        and CN_ESS_US_EXIT.search(text)
    )


def _cn_ess_official_vendor(item: dict) -> str:
    link = item.get('link') or ''
    host = re.match(r'^https?://([^/:?#]+)(?:[/:?#]|$)',link,re.I)
    if not host:
        return ''
    host=host.group(1).lower()
    source=item.get('source') or ''
    for canonical,(domain,names) in CN_ESS_US_VENDOR_DOMAINS.items():
        if source in names and (host == domain or host.endswith('.'+domain)):
            return canonical
    return ''


def _cn_ess_us_exit_stage(text: str, item: dict) -> str:
    if not _is_cn_ess_us_exit(text):
        return ''
    if (_cn_ess_official_vendor(item)
            and CN_ESS_US_FINAL_EXIT.search(text)
            and not CN_ESS_US_NEGATED.search(text)):
        return 'company_confirmed_us_exit'
    if ((item.get('source') or '') == 'DIGITIMES'
            and '0000771701_AKR6XDK313NXUP0KYL64J' in (item.get('link') or '')
            and re.search(r'DIGITIMES.{0,85}(?:업계|익명|단독|철수설)',text,re.I)
            and re.search(r'2026.{0,4}10.{0,4}19|10월\s*19',text,re.I)):
        return 'anonymous_industry_report'
    return 'unverified_rewrite'


def _cn_ess_us_retreat_recovery() -> list[dict]:
    # Public headline + first paragraph, timestamp 03:00 Asia/Taipei.
    # A paywalled article is NOT a list of verified company exits.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,23):
        return []
    return [{
        'title': CN_ESS_US_RETREAT_TITLE,
        'link': CN_ESS_US_RETREAT_URL,
        'description': (
            'DIGITIMES 2026-10-19 대만시간 03:00 단독 '
            '「雙向技術封鎖與非紅代工新賽局　傳中系儲能巨頭集體撤美」. '
            '검색 색인·공개 도입부에는 익명의 미국 공급망 관계자가 '
            '중국계 ESS 시스템 통합 대기업들이 2026년 미국 사업에서 '
            '사실상 대부분 철수했다고 주장했다고 적혔다. '
            '기사 유료 전문은 직접 읽지 못했다. 기업별 명단, 미국 법인 폐쇄 공시, '
            '해지계약, 기존 수주 취소, 새 공급사 이전계약은 확인되지 않았다. '
            '미국 IRS Notice 2026-15는 48E ESS 세액공제에서 '
            '금지 외국기업(PFE) 원가조달 제한을 설명하며, '
            '2026년 시작하는 ESS 프로젝트의 비PFE 원가 비율은 55%다. '
            '이것은 모든 중국 제품 판매를 금지하는 법률이 아니다. '
            '미국 USTR 발표의 중국산 비전기차 리튬이온배터리 Section 301 '
            '추가 관세 25% 예정 시행연도는 2026년이다. '
            'Wood Mackenzie 2026-06-29 조사에서 2025년 글로벌 '
            '중국계 ESS 시스템 통합업체 비중은 76%이며, '
            '북미 ESS 시스템 통합 1위는 Tesla로 확인된다. '
            '삼성SDI 미국 ESS 1조5천억원 2026년 3월 계약 및 2025년 '
            '2조원 초과 LFP 계약, LG에너지솔루션 기존 7.5GWh 북미 계약은 '
            '발표된 기존 사업으로 이번 보도 후 신규 발주가 아니다. '
            '셀과 시스템 통합, 세액공제 부적격과 미국 판매 불가능, '
            '신규 입찰 철수와 기존 프로젝트 유지 여부를 구분한다.'
        ),
        'source': 'DIGITIMES',
        'published': '2026-10-18T19:00:00+00:00',
        'direct_recovery': True,
        'anonymous_industry_source': True,
    }]



# Actual WORLDWIDE grid-scale BESS commissioning, not annual forecasts,
# Korea-only installations, or signed orders. The original Benchmark
# Mineral Intelligence figures were quoted by Energy-Storage.News (Oct 15)
# and reproduced by the Korean Energy Technology Evaluation agency.
BESS_SEP26_RECOVERY = 'DIRECT_BMI_GLOBAL_BESS_202609_20P4GWH_YTD208_20261015'
BESS_SEP26_TITLE = '9월 글로벌 계통용 BESS 신규 가동 20.4GWh(+61%), 1~9월 누적 208GWh(+43%)'
BESS_SEP26_URL = 'https://www.energy-storage.news/20-4gwh-grid-scale-bess-deployed-globally-in-september-up-61-ytd-installs-up-43/'
BESS_BMI_SOURCES = {
    'Energy-Storage.News', 'Benchmark Mineral Intelligence',
    '한국에너지기술평가원', 'KETEP', 'Energy Storage News'
}
BESS_BMI_MONTHS = {
    'january': '01', 'february': '02', 'march': '03',
    'april': '04', 'may': '05', 'june': '06',
    'july': '07', 'august': '08', 'september': '09',
    'october': '10', 'november': '11', 'december': '12',
}
BESS_BMI_ACTUAL = re.compile(
    r'(?:came\s+online|went\s+online|commissioned|newly\s+deployed|'
    r'deployed\s+globally|installed\s+globally|신규\s*(?:가동|설치)|'
    r'(?:실제|신규)\s*설치량|가동량|상업운전\s*개시)', re.I,
)
BESS_BMI_GRID = re.compile(
    r'grid[-\s]*scale\s*(?:BESS|battery)|계통용\s*(?:BESS|ESS|에너지저장)|'
    r'전력망용\s*(?:BESS|ESS)|그리드\s*규모|그리드\s*스케일', re.I,
)
BESS_BMI_AGENCY = re.compile(r'Benchmark\s*Mineral\s*Intelligence|\bBMI\b', re.I)


def _bess_bmi_period(text: str) -> str:
    # The period comes from the stated deployment month, never today's date.
    month = re.search(
        r'\b(January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\b|(?<!\d)(1[0-2]|[1-9])\s*월', text, re.I
    )
    if not month:
        return ''
    month_str = BESS_BMI_MONTHS[month.group(1).lower()] if month.group(1) else f'{int(month.group(2)):02d}'
    year = re.search(r'(?<!\d)(20(?:2[6-9]|3[0-9]))(?!\d)', text)
    if not year:
        return ''
    return f'{year.group(1)}-{month_str}'


def _is_bess_bmi_actual(text: str) -> bool:
    return bool(
        BESS_BMI_GRID.search(text) and BESS_BMI_AGENCY.search(text)
        and BESS_BMI_ACTUAL.search(text) and _bess_bmi_period(text)
        and re.search(r'\b\d+(?:\.\d+)?\s*GWh\b',text,re.I)
    )


def _bess_bmi_stage(text: str, source: str = '') -> str:
    if not _is_bess_bmi_actual(text):
        return ''
    if source not in BESS_BMI_SOURCES:
        return 'news_reprint_unconfirmed'
    period = _bess_bmi_period(text)
    if (period == '2026-09'
            and re.search(r'20\s*\.\s*4\s*GWh',text,re.I)
            and re.search(r'208\s*GWh',text,re.I)):
        return 'september_actual_commissioning'
    if (period != '2026-09' and re.search(r'(?:\b(?:YTD|year[-\s]*to[-\s]*date)\b|'
                                             r'연초\s*누적|누계)',text,re.I)
            and len(re.findall(r'\d+(?:\.\d+)?\s*GWh',text,re.I)) >= 2):
        return 'new_month_actual_commissioning'
    return 'background'


def _bess_bmi_recovery() -> list[dict]:
    # Full press story is date-stamped October 15, not a verified clock time.
    # An explicitly time-limited direct recovery is safer than fabricating
    # an hourly publication timestamp or replaying it after state rotation.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 23):
        return []
    return [{
        'title': BESS_SEP26_TITLE,
        'link': BESS_SEP26_URL,
        'description': (
            'Benchmark Mineral Intelligence 제공 수치를 인용한 Energy-Storage.News '
            '2026년 10월 15일 보도. 2026년 9월 전 세계 계통용 BESS 신규 가동량은 '
            '약 20.4GWh로 전년 동월 대비 61% 증가, 2026년 1~9월 누계는 '
            '208GWh로 전년 동기 대비 43% 증가했다. '
            '중국은 9월에 12GWh 이상 가동했으며, 유럽은 9월 2GWh 이상 '
            '연속 5개월 가동, 유럽 1~9월 누적은 22GWh로 전년 동기 대비 '
            '182% 증가했다. 한국에너지기술평가원 세계 에너지시장 정보도 '
            '2026년 10월 16일 동일 수치를 재확인했다. '
            '가동량은 이미 설치되어 운영에 들어간 산업 전체 물량이지 '
            '미래 신규 발주 GWh, 한국 배터리업체 수주액, AI데이터센터 전용 '
            'ESS 물량, BBU 용량을 뜻하지 않는다. '
            '1GWh=100만kWh이므로 9월 약 2,040만kWh, '
            '1~9월 누계 약 2억 800만kWh에 해당한다. '
            '배터리 셀 가격과 건설·변전·냉각·안전·소방·소프트웨어 비용의 '
            '범위가 다른 만큼 이 용량을 임의 단가로 곱해 '
            '기업 확정 원화 매출이나 총사업비로 발표하지 않는다. '
            '개별 셀 업체, 설치 장소, 계약금액은 이 글로벌 집계로 특정 불가.'
        ),
        'source': 'Energy-Storage.News',
        'published': None,
        'direct_recovery': True,
        'bess_bmi_report': True,
    }]


# Samsung SDI solid-state roadmap and September BBU display already exist.
# A new October 18 article describes an *earliest possible* Q2-2027
# Malaysian LFP-BBU production schedule. It is NOT an official SOP.
SDI_BBU_LFP_RE = re.compile(
    r'(?:삼성\s*SDI|SAMSUNG\s*SDI|Samsung\s*SDI).{0,230}'
    r'(?:BBU|배터리\s*백업(?:\s*유닛)?|배터리백업유닛).{0,180}'
    r'(?:LFP|리튬인산철|21700|원통형)', re.I
)
SDI_BBU_LFP_RE_ALT = re.compile(
    r'(?:BBU|배터리\s*백업(?:\s*유닛)?).{0,140}'
    r'(?:LFP|리튬인산철|21700).{0,200}'
    r'(?:삼성\s*SDI|SAMSUNG\s*SDI|Samsung\s*SDI)', re.I
)
SDI_BBU_OFFICIAL = {'삼성SDI','SAMSUNG SDI','Samsung SDI','삼성SDI 뉴스룸'}
SDI_BBU_SOP = re.compile(
    r'(?:BBU|21700|원통형).{0,95}(?:LFP|리튬인산철).{0,115}'
    r'(?:양산\s*(?:개시|시작|돌입|완료)|첫\s*출하\s*(?:개시|완료)|'
    r'first\s+commercial\s+shipment|mass\s+production\s+(?:started|began))|'
    r'(?:LFP|리튬인산철).{0,120}(?:BBU|21700|원통형).{0,110}'
    r'(?:양산\s*(?:개시|시작|돌입|완료)|첫\s*출하\s*(?:개시|완료))',
    re.I
)
SDI_BBU_PLAN_ONLY = re.compile(
    r'예정|계획|목표|추진|검토|이르면|가능성|보도|기대|'
    r'planned|target|expected|may\s+start|earliest',re.I
)
SDI_BBU_CONTRACT = re.compile(
    r'(?:BBU|21700).{0,120}(?:LFP|리튬인산철).{0,140}'
    r'(?:고객\s*공급계약\s*체결|확정\s*구매계약\s*체결|'
    r'signed\s+(?:binding\s+)?supply\s+contract)',re.I
)


def _is_sdi_bbu_lfp(text: str) -> bool:
    return bool(SDI_BBU_LFP_RE.search(text) or SDI_BBU_LFP_RE_ALT.search(text))


def _sdi_bbu_lfp_stage(text: str, source: str = '') -> str:
    if not _is_sdi_bbu_lfp(text):
        return ''
    if source in SDI_BBU_OFFICIAL:
        if SDI_BBU_CONTRACT.search(text) and not SDI_BBU_PLAN_ONLY.search(text):
            return 'official_customer_order'
        if SDI_BBU_SOP.search(text) and not SDI_BBU_PLAN_ONLY.search(text):
            return 'official_first_lfp_bbu_sop'
    return 'press_plan_or_existing_product'


# Verification of 2026-10-19 Run #664 / Telegram message_id=238:
# its first item was merely a Samsung SDI share-price reaction (8%대 올라),
# NOT an ESS order or company earnings disclosure. Its second item,
# Benchmark Mineral Intelligence worldwide BESS actuals, remains valid.
ALERT238_CORRECTION_ID = 'DIRECT_ROBOTIS_ALERT_238_PRICE_REACTION_CORRECTION_20261019'


def _alert238_correction() -> list[dict]:
    # A single time-limited correction is sent via the EXISTING bot.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 24):
        return []
    return [{
        'title': '정정: Telegram 238번 1번 삼성SDI 주가 기사 오탐 제외',
        'link': 'https://github.com/qedgwangju-dot/khs-watch/actions/runs/39197066558',
        'description': (
            '2026년 10월 19일 기존 알림 Telegram message_id=238 1번 '
            '비즈니스포스트의 삼성SDI 주가 장중 8%대 올라 기사에는 '
            '신규 ESS 수주·첫 출하·확정 실적이 없었습니다. '
            '주가 변동 및 기대감만으로 공급망 구조 변화로 판정한 것은 오탐입니다. '
            '기존 238번 2번 Benchmark Mineral Intelligence '
            '9월 전 세계 계통용 BESS 신규 가동 20.4GWh 및 '
            '1~9월 누적 208GWh 실측집계는 유지합니다. '
            '수정한 판정기에 %대 올라 및 주가 상승 표현을 '
            '비사업 반응으로 걸러내는 회귀검사를 추가했습니다. '
            '이 정정은 신규 공급계약이나 기업 매출이 아닙니다.'
        ),
        'source': '알림 운영검증 기록',
        'published': None,
        'quality_correction_238': True,
        'direct_recovery': True,
    }]


_orig_query_news = base.query_news


def query_news(q: str) -> list[dict]:
    if q == ALERT246_CORRECTION_ID:
        return _alert246_correction_recovery()
    if q == ALERT238_CORRECTION_ID:
        return _alert238_correction()
    if q == BESS_SEP26_RECOVERY:
        return _bess_bmi_recovery()
    if q == DONGKUK_NPS_RECOVERY:
        return _dongkuk_report_recovery()
    if q == DKT_HUMANOID_RECOVERY:
        return _dkt_humanoid_recovery()
    if q == TESLA_TOUCH_PATENT_RECOVERY:
        return _tesla_touch_patent_recovery()
    if q == DIGITAL_OPTIMUS_GAME_RECOVERY:
        return _digital_optimus_game_recovery()
    if q == HUMANOID_DRAM_RECOVERY:
        return _humanoid_dram_recovery()
    if q == OPTIMUS_HAND_MAGNET_RECOVERY:
        return _optimus_hand_magnet_recovery()
    if q == LFP_NA_CIF_PRICE_RECOVERY:
        return _lfp_na_price_recovery()
    if q == VNET_EQUITY_RECOVERY:
        return _vnet_equity_recovery()
    if q == ROBROS_PILOT_20261013:
        return _robros_pilot_recovery() + _robros_213_214_correction()
    if q == CATL_INTILION_RECOVERY:
        return _catl_intilion_recovery()
    if q == DEXMATE_LG_RECOVERY:
        return _dexmate_lg_recovery()
    if q == STOCK_218_CORRECTION:
        return _stock_218_correction_recovery()
    if q == FLUENCE_VATTENFALL_RECOVERY:
        return _fluence_vattenfall_recovery()
    if q == MICRON_EIM_RECOVERY:
        return _micron_eim_recovery()
    if q == CN_ESS_US_RETREAT_ID:
        return _cn_ess_us_retreat_recovery()
    if q.startswith(ROBOT_OCT15_PREFIX):
        return _oct15_recovery(q[len(ROBOT_OCT15_PREFIX):])
    if q.startswith(ROBOT_OCT16_PREFIX):
        return _oct16_recovery(q[len(ROBOT_OCT16_PREFIX):])
    return _orig_query_news(q)


base.query_news = query_news
if ALERT246_CORRECTION_ID not in base.QUERIES:
    base.QUERIES.append(ALERT246_CORRECTION_ID)
if ALERT238_CORRECTION_ID not in base.QUERIES:
    base.QUERIES.append(ALERT238_CORRECTION_ID)
if BESS_SEP26_RECOVERY not in base.QUERIES:
    base.QUERIES.append(BESS_SEP26_RECOVERY)
for _q in (
    '(Benchmark Mineral Intelligence OR BMI) (grid-scale BESS OR 계통용 ESS) '
    '(global OR worldwide OR 전 세계) (installed OR commissioned OR 신규 가동 OR 누적)',
    '(삼성SDI OR Samsung SDI) (BBU OR 배터리백업) (21700 OR 원통형 OR LFP) '
    '(말레이시아 OR Seremban OR 2027 OR 양산 OR 고객 계약 OR 첫 출하)',
):
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)
if CN_ESS_US_RETREAT_ID not in base.QUERIES:
    base.QUERIES.append(CN_ESS_US_RETREAT_ID)
for _q in (
    '(DIGITIMES OR 儲能 OR 储能) (集體撤美 OR 集体撤美 OR 중국계 ESS) (美國 OR 美国 OR US OR 미국) (철수 OR exit OR 撤退)',
    '(CATL OR 宁德时代 OR Sungrow OR 阳光电源 OR BYD OR 比亚迪 OR HiTHIUM OR HyperStrong) (ESS OR BESS OR 储能) (US OR 美國 OR 美国 OR 미국) (exit OR closure OR 撤退 OR 철수)',
):
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)
for q in (
    CATL_INTILION_RECOVERY,
    DEXMATE_LG_RECOVERY,
    STOCK_218_CORRECTION,
    FLUENCE_VATTENFALL_RECOVERY,
    '(Fluence OR 플루언스) (Vattenfall OR 바텐팔) (Brunsbüttel OR Brunsbuttel OR 브룬스뷔텔) (공급계약 OR signed OR turnkey OR contract OR commissioning OR 착공)',
    '(Fluence OR 플루언스) (Vattenfall OR 바텐팔) (254MW OR 1000MWh OR 1GWh) (long term service OR grid connection OR EPC OR completion OR 전원 인가)',
    '(CATL OR 宁德时代) (INTILION OR 인틸리온) (sodium-ion OR 나트륨이온) (3GWh OR 3 GWh OR 계약 OR 프로젝트 OR 납품 OR 지연)',
    '(Dexmate OR 덱스메이트) (LG CNS OR LG씨엔에스) (실제 사용 OR 유통 OR 도입 OR 납품 OR 유상계약 OR 작업 성공률)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
if ROBROS_PILOT_20261013 not in base.QUERIES:
    base.QUERIES.append(ROBROS_PILOT_20261013)
for q in (
    '(로브로스 OR Robros) (네패스 OR 성우하이텍 OR HD현대삼호 OR 딜리버리랩) '
    '(휴머노이드 OR humanoid) (실증특례 OR 규제특례 OR 승인 OR 안전펜스 OR 실증 시작)',
    '(로브로스 OR Robros) (네패스 OR 성우하이텍 OR HD현대삼호 OR 딜리버리랩) '
    '(휴머노이드 OR humanoid) (가동률 OR 작업 성공률 OR 현장 투입 완료 '
    'OR 후속 발주 OR 유상계약 OR 안전사고 OR 실증 중단)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
for q in (
    '("FUNDA" OR "FundaAI") ("Physical AI" OR 로봇) '
    '("post-training" OR 사후학습) ("3-4x" OR "3~4배" OR GPU)',
    '(NVIDIA OR "Physical Intelligence" OR "Google DeepMind" OR "Skild AI" OR Tesla) '
    '(robot OR humanoid OR VLA OR 로봇) '
    '("post-training" OR 사후학습) '
    '("GPU-hours" OR GPU시간 OR "training compute" OR 훈련비용)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
if LFP_NA_CIF_PRICE_RECOVERY not in base.QUERIES:
    base.QUERIES.append(LFP_NA_CIF_PRICE_RECOVERY)
if VNET_EQUITY_RECOVERY not in base.QUERIES:
    base.QUERIES.append(VNET_EQUITY_RECOVERY)
for q in (
    '(VNET OR 21Vianet) (CATL OR 宁德时代) (sodium-ion OR 나트륨이온 OR energy storage) (GWh OR MWh OR supply contract OR 구매계약)',
    '(VNET OR 21Vianet) (CATL OR 宁德时代) (PJ Millennium OR 38.1% OR 650424192 OR 지분 종결)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
for q in (
    '(Benchmark OR 벤치마크 OR 디일렉) (314Ah OR 314암페어시) '
    '(51.62 OR 61.99) (LFP OR 리튬인산철) (CIF OR EXW OR 북미)',
    '(314Ah OR 314암페어시) (LFP OR 리튬인산철) '
    '(미국 OR 북미 OR North America) (운송비 OR CIF OR 관세 OR 40.9%)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)

if OPTIMUS_HAND_MAGNET_RECOVERY not in base.QUERIES:
    base.QUERIES.append(OPTIMUS_HAND_MAGNET_RECOVERY)
for q in (
    '("X Takeover" OR XTakeover) (Optimus OR 옵티머스) (magnet OR 자석 OR screw OR 나사 OR hand OR 손)',
    '(Tesla OR 테슬라) (Optimus OR 옵티머스) (희토류 자석 OR 영구자석 OR motor magnets) (신규 공급계약 OR 공장 가동 OR 공급 승인 OR 지연 OR 생산량)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
if DONGKUK_NPS_RECOVERY not in base.QUERIES:
    base.QUERIES.append(DONGKUK_NPS_RECOVERY)
if DKT_HUMANOID_RECOVERY not in base.QUERIES:
    base.QUERIES.append(DKT_HUMANOID_RECOVERY)
if TESLA_TOUCH_PATENT_RECOVERY not in base.QUERIES:
    base.QUERIES.append(TESLA_TOUCH_PATENT_RECOVERY)
if DIGITAL_OPTIMUS_GAME_RECOVERY not in base.QUERIES:
    base.QUERIES.append(DIGITAL_OPTIMUS_GAME_RECOVERY)
if HUMANOID_DRAM_RECOVERY not in base.QUERIES:
    base.QUERIES.append(HUMANOID_DRAM_RECOVERY)
for q in (
    '(Counterpoint OR 카운터포인트) (휴머노이드 OR humanoid OR 로봇) '
    '(DRAM OR D램 OR LPDDR) (19GB OR 39GB OR 8300Tbit OR 172000Tbit '
    'OR 전망 수정 OR revised OR forecast)',
    '(휴머노이드 OR humanoid) (LPDDR OR 저전력 D램 OR NAND OR 낸드) '
    '(삼성전자 OR SK하이닉스 OR Micron OR 카운터포인트) '
    '(공급계약 OR 고객 승인 OR 양산 출하 OR revised forecast OR 전망 상향)',
):
    if q not in base.QUERIES:
        base.QUERIES.append(q)
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

for _key in ROBOT_OCT15_EVENTS:
    _sentinel = ROBOT_OCT15_PREFIX + _key
    if _sentinel not in base.QUERIES:
        base.QUERIES.append(_sentinel)
for _key in ROBOT_OCT16_EVENTS:
    _sentinel = ROBOT_OCT16_PREFIX + _key
    if _sentinel not in base.QUERIES:
        base.QUERIES.append(_sentinel)
for _q in (
    '(기후에너지환경부 OR 기후부) (옥외형 ESS OR 에너지저장장치) '
    '(시설물 분류 OR 건축물 OR 공작물 OR 가설건축물) (가이드라인 OR 지침 OR 지자체 실제 적용)',
    '(브릴스 OR BRILS) (미시간 OR BRILS USA OR 그랜드래피즈) '
    '(AMR OR 포크형 OR 저상형 OR 자율이동로봇) (현지 생산 OR 첫 출하 OR 유상계약 OR 규제)',
    '(현대차그룹 OR 현대자동차그룹) (RX사업전략팀 OR Robotics Everything) '
    '(조직 신설 OR 공식 확인 OR 로봇 외부 수주)',
    '(LG전자 OR LG Electronics) (로봇 소프트웨어 플랫폼 OR robotics software platform) '
    '(조직 신설 OR 공식 확인 OR 상용 사용권 OR 계약)',
    '(로보티즈 OR ROBOTIS) (AI 사피엔스 OR 휴머노이드) '
    '(하드웨어 설계도 OR 회로도 OR CAD) (실제 공개 OR GitHub OR 다운로드 OR 배포)',
):
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)
for _q in (
    '(Agility Robotics OR Churchill XI OR CCXI) (S-4 OR AGLT OR 합병) '
    '(SEC effective OR shareholder vote OR 거래 종결 OR 상장 시작)',
    '(RB-Y1 OR 레인보우로보틱스) (FCC OR 미국 규제 OR 조건부 승인) '
    '(신청 OR 승인 OR 장비 인증 OR 첫 출하 OR 수주)',
    '(新剑传动 OR 신젠전동 OR Xinjian) (Optimus OR Tesla OR 特斯拉) '
    '(IPO OR 上市审核 OR 丝杠 OR 롤러스크루 OR 量产订单)',
    '(유니켐 OR Unichem) (Loomia OR 루미아) '
    '(본계약 OR 거래 종결 OR 고객승인 OR 전자피부 OR 양산 수주)',
    '(Boston Dynamics OR 보스턴다이내믹스) (Atlas OR 아틀라스) '
    '(ProtoOps OR assembly time OR 제작시간 OR 시간 단축 OR 1시간) '
    '(actual OR 달성 OR 목표 OR 조립 OR 수율)',
):
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)

# Target EIM research and subsequent first-party validation, not generic
# high-end robot-memory capacity forecasts or ordinary HBM price articles.
if MICRON_EIM_RECOVERY not in base.QUERIES:
    base.QUERIES.append(MICRON_EIM_RECOVERY)
for _q in (
    '(마이크론 OR Micron) (EIM OR "Edge Inference Memory" OR 엣지 인퍼런스 메모리) '
    '(SEDEX OR 개발 OR LPDDR6 OR 시제품 OR 고객검증 OR design win OR 양산)',
    '("EIM" OR "Edge Inference Memory") (Micron OR 마이크론) '
    '(sample OR 고객 승인 OR bandwidth OR 전력 OR first shipment OR 양산 시작)',
):
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)

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
    if ALERT246_CORRECTION_TITLE in text:
        return 'alert_quality_246'
    if '정정: Telegram 238번 1번' in text:
        return 'alert_quality_238'
    if _is_bess_bmi_actual(text):
        return 'global_bess_commissioned'
    if _is_sdi_bbu_lfp(text):
        return 'sdi_lfp_bbu'
    if _is_cn_ess_us_exit(text):
        return 'china_ess_us_exit_report'
    if _is_micron_eim(text):
        return 'micron_eim_edge'
    _new = _oct16_group(text)
    if _new:
        return _new
    _g = _oct15_group(text)
    if _g:
        return _g
    if _is_fluence_vattenfall(text):
        return 'fluence_vattenfall_bess'
    if _is_sdi_oct08_preview(text):
        return 'sdi_oct08_broker_preview'
    if '정정: Telegram 218번 1번' in text:
        return 'alert_quality_correction'
    if _is_catl_intilion_sodium(text):
        return 'catl_intilion_sodium'
    if _is_dexmate_lg(text):
        return 'dexmate_lg_commercial'
    if _is_robros_pilot(text):
        return ROBROS_PILOT_GROUP
    if _is_robot_posttrain_compute(text):
        return 'robot_posttrain_compute'
    if _is_vnet_catl(text):
        return 'catl_vnet_infrastructure'
    if _is_lfp_na_314_price(text):
        return 'lfp_314_cif_north_america'
    if _is_2026_roadmap_rewrite(text):
        return 'battery_roadmap_2026_baseline'
    if _is_legacy_ev_ess_pivot(text):
        return 'ev_to_ess_oversupply_baseline'
    if _is_optimus_hand_magnet(text):
        return 'optimus_hand_magnet'
    if _is_humanoid_dram(text):
        return 'humanoid_brain_dram'
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
    item_text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if item.get('quality_correction_246'):
        return 99 if topic_group(item_text) == 'alert_quality_246' else 0
    if _catl_intilion_oct20_reprint(item):
        return 0
    if item.get('quality_correction_238'):
        return 98 if topic_group(item_text) == 'alert_quality_238' else 0
    if _is_bess_bmi_actual(item_text):
        stage = _bess_bmi_stage(item_text,item.get('source') or '')
        return {
            'september_actual_commissioning': 71,
            'new_month_actual_commissioning': 72,
            'news_reprint_unconfirmed': 0,
            'background': 0,
        }.get(stage, 0)
    if _is_sdi_bbu_lfp(item_text):
        stage = _sdi_bbu_lfp_stage(item_text,item.get('source') or '')
        return {
            'official_customer_order': 79,
            'official_first_lfp_bbu_sop': 85,
            'press_plan_or_existing_product': 0,
        }.get(stage,0)
    if _is_cn_ess_us_exit(item_text):
        stage = _cn_ess_us_exit_stage(item_text,item)
        return {'anonymous_industry_report':43,
                'company_confirmed_us_exit':83,
                'unverified_rewrite':0}.get(stage,0)
    if _is_micron_eim(item_text):
        stage = _micron_eim_stage(item_text,item)
        return {
            'executive_reported_rnd': 47,
            'company_confirmed_rnd': 57,
            'company_confirmed_sample': 69,
            'company_confirmed_customer': 78,
            'company_confirmed_sop': 88,
            'background': 0,
        }.get(stage,0)
    # Earnings/ESS-installation market outlook alone is not a newly signed
    # order, confirmed company result, or new installation figure.
    # Preserve credible primary quantitative releases and contract news.
    headline = item.get('title') or ''
    if (item.get('source') not in base.OFFICIAL_OR_PRIMARY
            and re.search(r'(?:K\s*배터리|K-배터리|ESS|에너지저장)', headline, re.I)
            and re.search(r'(?:실적\s*청신호|설치량.{0,24}(?:최대|최고)\s*지속)', headline, re.I)
            and not ESS_CONCRETE_NEW_EVENT.search(headline)
            and not ESS_OFFICIAL_QUARTERLY.search(headline)):
        return 0
    group_oct16=_oct16_group(item_text)
    if group_oct16:
        return _oct16_score(item,group_oct16,item_text)
    group_oct15 = _oct15_group(item_text)
    if group_oct15:
        _stage_oct15 = _oct15_stage(group_oct15, item_text, item.get('source') or '')
        return {
            's4_effective': 76,
            'shareholders_approved': 83,
            'official_closed': 91,
            'application_reported': 48,
            'official_approval_granted': 88,
            'ipo_order_reported': 57,
            'official_shipment': 81,
            'signed_conditional_report': 64,
            'official_closing': 87,
            'build_time_goal': 41,
            'official_one_hour_achieved': 84,
            'correction': 95,
            'background': 0,
        }.get(_stage_oct15, 0)
    if _is_fluence_vattenfall(item_text):
        return {
            'official_signed_turnkey_award': 76,
            'official_construction_started': 80,
            'official_energized': 88,
            'official_reversal': 90,
        }.get(_fluence_vattenfall_stage(item_text,item.get('source') or ''),0)
    if _is_sdi_oct08_preview(item_text):
        return 0
    if item.get('correction_218_stock'):
        return 95 if topic_group(
            f"{item.get('title','')} {item.get('description','')}"
        ) == 'alert_quality_correction' else 0
    if item.get('robros_false_alert_correction'):
        return 90 if _is_robros_pilot(
            f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
        ) else 0
    if (_is_stock_reaction_only(item)
            or _is_ess_expectation_only(item)
            or _is_generic_ess_demand_story(item)
            or _is_oct15_market_noise(item)):
        return 0
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)
    if group == 'catl_intilion_sodium':
        return {
            'sodium_3gwh_development_framework': 54,
            'official_binding_order': 70,
            'official_site_commissioned': 78,
            'official_reversal': 75,
            'background': 0,
        }.get(_catl_intilion_stage(text,item.get('source') or ''),0)
    if group == 'dexmate_lg_commercial':
        return {
            'ceo_reported_use_distribution': 48,
            'official_paid_contract': 75,
            'official_measured_reliability': 76,
            'known_investment_and_poc_baseline': 0,
        }.get(_dexmate_lg_stage(text,item.get('source') or ''),0)
    if group == ROBROS_PILOT_GROUP:
        return {
            'approved_pilot_report': 55,
            'official_site_deployment': 66,
            'official_site_kpi': 72,
            'official_site_contract': 76,
            'official_pilot_reversal': 80,
            'existing_or_unverified_baseline': 0,
        }.get(_robros_pilot_stage(text,item.get('source') or ''),0)
    if group == 'robot_posttrain_compute':
        return {'official_measured_posttraining':52,
                'funda_research_estimate_baseline':0,
                'unverified_or_general':0}.get(
            _robot_posttrain_stage(text,item.get('source') or ''),0
        )
    if group == 'catl_vnet_infrastructure':
        return {'equity_closing_baseline_recovery':45,'signed_vnet_sodium_contract':65,
                'background':0}.get(_vnet_catl_stage(text,item.get('source') or ''),0)
    if group == 'lfp_314_cif_north_america':
        if item.get('source') in LFP_NA_CIF_PRIMARY:
            return 46
        if item.get('source') in LFP_NA_CIF_TRUSTED:
            return 34
        return 0
    if group in {'battery_roadmap_2026_baseline','ev_to_ess_oversupply_baseline'}:
        return 0
    if group == 'optimus_hand_magnet':
        return {'retrospective_supply_bottleneck': 43, 'new_schedule_warning': 55,
                'background': 0}.get(_optimus_hand_magnet_stage(text,item.get('source') or ''),0)
    if topic_group(text) == 'humanoid_brain_dram':
        stage = _humanoid_dram_stage(text, item.get('source') or '')
        return {'initial_research_forecast': 45,
                'official_forecast_revision': 52,
                'confirmed_named_oem_order': 64,
                'background': 0}.get(stage, 0)
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
    if group == 'alert_quality_246':
        return '알림 운영 정정 · CATL–INTILION 동일 프로젝트 중복 제외'
    if group == 'alert_quality_238':
        return '알림 품질 정정 · Telegram 238번 주가 반응 오탐'
    if group == 'global_bess_commissioned':
        if _bess_bmi_period(text) == '2026-09':
            return '글로벌 계통용 BESS · 2026년 9월 신규 가동량'
        return '글로벌 계통용 BESS · 이후 월간 실제 가동량'
    if group == 'sdi_lfp_bbu':
        if SDI_BBU_CONTRACT.search(text) and not SDI_BBU_PLAN_ONLY.search(text):
            return '삼성SDI LFP BBU · 고객 공급계약 공식 확인'
        if SDI_BBU_SOP.search(text) and not SDI_BBU_PLAN_ONLY.search(text):
            return '삼성SDI LFP BBU · 양산·첫 출하 공식 확인'
        return '삼성SDI LFP BBU · 기존 제품·2027년 2분기 보도 계획'
    if group == 'china_ess_us_exit_report':
        if CN_ESS_US_FINAL_EXIT.search(text) and not CN_ESS_US_NEGATED.search(text):
            return '미국 ESS 공급망 · 중국계 개별업체 철수 공식확인'
        return '미국 ESS 공급망 · 중국계 시스템업체 집단 철수설 보도'
    if group == 'micron_eim_edge':
        stage = _micron_eim_display_stage(text)
        return {
            'executive_reported_rnd': '마이크론 EIM · SEDEX 경영진 개발·고객 협의 보도',
            'company_confirmed_rnd': '마이크론 EIM · 개발 공식 확인',
            'company_confirmed_sample': '마이크론 EIM · 고객 시제품 제공·검증',
            'company_confirmed_customer': '마이크론 EIM · 고객 정식 채택·공급계약',
            'company_confirmed_sop': '마이크론 EIM · 실제 양산·상업 출하',
        }.get(stage,'마이크론 EIM · 개발 단계')
    if group in ROBOT_OCT16_TITLES:
        return _oct16_category(group,text)
    if group in ROBOT_OCT15_TITLES.values():
        return group
    if group in ROBOT_OCT15_TITLES:
        return _oct15_render_category(group, text)
    if group == 'fluence_vattenfall_bess':
        if FLUENCE_VATTENFALL_REVERSE.search(text):
            return 'Fluence–Vattenfall · 독일 1GWh ESS 계약 후퇴'
        if (FLUENCE_VATTENFALL_ENERGIZED.search(text)
                and not FLUENCE_VATTENFALL_ENERGIZED_NOT.search(text)):
            return 'Fluence–Vattenfall · 독일 1GWh ESS 전원 인가·상업운전'
        if (FLUENCE_VATTENFALL_START.search(text)
                and not FLUENCE_VATTENFALL_START_NOT.search(text)):
            return 'Fluence–Vattenfall · 독일 1GWh ESS 실제 착공'
        if FLUENCE_VATTENFALL_SIGNED.search(text):
            return 'Fluence–Vattenfall · 독일 1GWh ESS 정식 턴키 공급계약'
        return 'Fluence–Vattenfall · 9월 투자결정 기존 기준선'
    if group == 'sdi_oct08_broker_preview':
        return '삼성SDI · 증권사 3분기 추정·4분기 수주 기대'
    if group == 'alert_quality_correction':
        return '알림 품질 정정 · Telegram 218번 1번 오탐'
    if group == 'catl_intilion_sodium':
        if CATL_INTILION_REVERSE.search(text):
            return 'CATL–INTILION · 나트륨 ESS 협약 후퇴'
        if CATL_INTILION_DEPLOY.search(text):
            return 'CATL–INTILION · 첫 현장 실제 가동'
        if CATL_INTILION_BINDING.search(text) and not CATL_INTILION_NOBINDING.search(text):
            return 'CATL–INTILION · 실제 구속력 있는 구매계약'
        return 'CATL–INTILION · 유럽 5년 최대 3GWh 공동개발 목표'
    if group == 'dexmate_lg_commercial':
        if DEXMATE_PAID.search(text) and not re.search(r'유료\s*계약.{0,20}(?:없음|미공개|아님)|not\s+signed',text,re.I):
            return 'Dexmate–LG CNS · 공식 유료 공급계약'
        if DEXMATE_ACHIEVED_KPI.search(text) and not DEXMATE_KPI_REQUIRED.search(text):
            return 'Dexmate–LG CNS · 실제 작업성공률 실측'
        return 'Dexmate–LG CNS · 사용·유통 CEO 현장발언'
    if group == ROBROS_PILOT_GROUP:
        if '정정: Telegram 213·214' in text:
            return '로브로스 실증특례 · Telegram 오탐 정정'
        # Renderer calls category(title+description) without source. Each
        # rendering class must match the corresponding scored source-tier.
        if ROBROS_REVERSE.search(text):
            return '로브로스 실증특례 · 승인 후퇴·현장 안전 역풍'
        if ROBROS_MEASURED.search(text):
            return '로브로스 제조현장 · 작업 KPI 실측'
        if ROBROS_ORDER.search(text):
            return '로브로스 제조현장 · 고객 정식 유상계약'
        if ROBROS_DEPLOYED.search(text):
            return '로브로스 제조현장 · 실제 배치 개시'
        return '로브로스 산업실증 · 이동형 휴머노이드 20대 규제특례 승인'
    if group == 'robot_posttrain_compute':
        if ROBOT_POSTTRAIN_GPU_HOURS.search(text) and ROBOT_POSTTRAIN_MEASURED.search(text):
            return '로봇 사후학습 · GPU시간 실측 공개'
        return '로봇 사후학습 · Funda AI 3~4배 추정 기준선'
    if group == 'catl_vnet_infrastructure':
        if '정정:' in text and '주가' in text:
            return 'CATL 관계사–VNET · 10/12 주가 기사 오탐 정정'
        if (VNET_SODIUM.search(text) and VNET_ORDER.search(text)
                and VNET_ESS_QTY.search(text) and not VNET_HYPERSTRONG_BASE.search(text)
                and re.search(r'VNET.{0,230}(?:sodium|나트륨).{0,230}(?:GWh|MWh)',text,re.I)):
            return 'CATL–VNET · 나트륨 ESS 실명 공급계약'
        return 'CATL 관계사–VNET · 9/21 간접지분 38.1% 인수 종결'
    if group == 'lfp_314_cif_north_america':
        return 'ESS LFP 북미 조달 · 314Ah 9월 CIF 가격·관세 가정'
    if group == 'battery_roadmap_2026_baseline':
        return '배터리 산업기술 로드맵 · 9월 정부 발표 기존 기준선'
    if group == 'ev_to_ess_oversupply_baseline':
        return '미국 EV→ESS 전환 · 기존 공장 재배치 배경'
    if group == 'optimus_hand_magnet':
        return 'Optimus 손·자석 · 2025년 공급망 차질 경영진 회고' if OPTIMUS_HAND_MAGNET_RETRO.search(text) else 'Optimus 손·자석 · 실제 신규 일정변경 확인'
    if group == 'humanoid_brain_dram':
        if _humanoid_dram_oem_order(text):
            return '휴머노이드 두뇌 D램 · 고객 실명 양산 공급계약 확인'
        # category() receives title+description without the source.
        if HUMANOID_DRAM_FORECAST_REVISION.search(text) and (
            re.search(r'2030', text) and re.search(r'Tbit|테라s*비트|GB', text, re.I)
        ):
            return '휴머노이드 두뇌 D램 · 조사기관 전망치 공식 수정'
        return '휴머노이드 두뇌 D램 · 2030년 수요 신규 전망'
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
    if cat == '알림 운영 정정 · CATL–INTILION 동일 프로젝트 중복 제외':
        return ('Telegram 246은 10/09 공개된 CATL–INTILION 나트륨 ESS 최대 3GWh 협력의 10/20 재보도입니다. 새로운 계약·출하·설치로 알리지 않고 기존 218번 원사건을 유지합니다. 확정 발주·실제 사이트 운영 개시가 다음 알림 조건입니다.')
    if cat == '알림 품질 정정 · Telegram 238번 주가 반응 오탐':
        return (
            'Telegram message_id=238의 첫 번째 삼성SDI 주가 8%대 상승 기사는 '
            '신규 ESS 공급계약·실제 출하·분기 실적 발표가 없는데도 고신호로 전송된 오탐입니다. '
            '해당 기사로부터 어떤 삼성SDI 신규 원화 매출도 확정하지 않습니다. '
            '같은 메시지의 두 번째 실제 글로벌 BESS 9월 가동량 20.4GWh(+61%)와 '
            '1~9월 누적 208GWh(+43%)는 유지합니다. '
            '신규 판정은 주가 변동 기사를 점수 0으로 걸러내며 이 정정 자체는 계약이 아닙니다.'
        )
    if cat == '글로벌 계통용 BESS · 2026년 9월 신규 가동량':
        return (
            'Benchmark Mineral Intelligence 집계를 인용한 Energy-Storage.News 10/15 신규 실측 통계입니다. '
            '2026년 9월 전 세계 신규 가동량 약 20.4GWh(+61% 전년 동월), '
            '2026년 1~9월 누적 208GWh(+43% 전년 동기)입니다. '
            '중국 9월 12GWh 이상, 유럽 1~9월 22GWh(+182%)를 구분합니다. '
            '20.4GWh는 약 2,040만kWh, 누적 208GWh는 약 2억 800만kWh입니다. '
            '이미 가동된 설비 용량으로 장래 발주·고객 수주·삼성SDI나 LG에너지솔루션 '
            '매출로 환산할 수 없습니다. 1GWh=100만kWh이며, '
            '실제 시스템 평균판매단가·설계조달시공 계약액 미공개로 '
            '원화 총사업비는 확인 불가입니다.'
        )
    if cat == '글로벌 계통용 BESS · 이후 월간 실제 가동량':
        return (
            'Benchmark Mineral Intelligence의 전 세계 실제 가동 통계가 새 기준월로 갱신된 단계입니다. '
            '기준월·1~해당월 누적·전년동기 대비·지역별 실제 가동량을 각각 검증합니다. '
            '이 통계는 가동 시점 집계이지 셀 업체 신규 수주 또는 매출 확정이 아닙니다.'
        )
    if cat == '삼성SDI LFP BBU · 고객 공급계약 공식 확인':
        return (
            '삼성SDI의 21700 LFP 서버 백업전원용 배터리가 고객과 공급계약 단계로 '
            '진입한 신호입니다. 9/29 공개 제품과 다른 단계이며 고객 실명·'
            '계약액·공급수량·첫 출하·인수시험·원화 인식매출을 별도로 검증합니다.'
        )
    if cat == '삼성SDI LFP BBU · 양산·첫 출하 공식 확인':
        return (
            '삼성SDI가 서버용 21700 LFP BBU 배터리 실제 양산 또는 첫 출하를 '
            '회사 자료로 공개한 단계입니다. 2027년 2분기 언론의 '
            '예상 일정과 구분하고, 월 생산량·초기 수율·고객 검수·매출 인식을 확인합니다.'
        )
    if cat == '삼성SDI LFP BBU · 기존 제품·2027년 2분기 보도 계획':
        return (
            '2026년 9월 29일 BBU용 21700 LFP 셀 공개는 이미 확인된 기준선이고 '
            '2027년 2분기 말레이시아 양산 가능성은 언론 계획 보도입니다. '
            '회사 실제 출하 또는 신규 정식 수주 확인 전에는 재알림하지 않습니다.'
        )
    if cat == '미국 ESS 공급망 · 중국계 시스템업체 집단 철수설 보도':
        return (
            'DIGITIMES 10/19 단독의 미국 업계 익명 관계자 발언으로, '
            '중국계 ESS 시스템 통합업체 일부가 미국 시장에서 사업을 '
            '줄이거나 철수했을 가능성이 제기됐습니다. 개별 업체 철수 공시와 '
            '취소 계약은 아직 확인되지 않았습니다. '
            '세액공제 PFE 조달제한과 관세 상승은 실제 정책이지만 '
            '중국 배터리 수입·판매 전체 금지를 뜻하지는 않습니다. '
            '삼성SDI 1조5천억원·2조원 초과 계약과 LG에너지솔루션 '
            '7.5GWh 공급계약은 과거 확정 사업이지 이 기사 후 고객이 '
            '옮겨왔다고 증명된 신규 계약은 아닙니다.'
        )
    if cat == '미국 ESS 공급망 · 중국계 개별업체 철수 공식확인':
        return (
            '해당 중국계 ESS 제조사가 공식자료로 미국 사업 종료를 확인한 '
            '별도 상위 단계입니다. 종료된 수주·고객·공장·유지보수 책임과 '
            '미국 새 발주처의 실제 대체 계약을 따로 확인해야 합니다. '
            '회사의 사업철수와 모든 중국산 셀 공급 중단은 다른 사건입니다.'
        )
    if cat.startswith('마이크론 EIM · '):
        if 'SEDEX 경영진' in cat:
            return (
                '10/16 SEDEX 2026에서 이철 마이크론 상무가 피지컬 AI용 '
                'EIM(엣지 추론 메모리)을 고객과 개발 협의 중이라고 설명한 신규 연구개발 신호입니다. '
                'EIM은 논리 칩 위 저전력 D램(LPDDR) 적층 구조로, '
                '메모리 내부 연산인 PIM·현재 서버용 HBM과 다른 설계입니다. '
                '대역폭·지연시간·전력·신뢰성 수치는 미공개입니다. '
                'LPDDR6 기반 2028년 하반기 양산은 회사 공식 일정이 아닌 업계 예상입니다. '
                '향후 고성능 휴머노이드 200GB D램·4TB 저장용량은 회사 경영진의 미래 '
                '시나리오이며 카운터포인트 2030년 산업 평균 39GB와 혼동하면 안 됩니다. '
                '가상 10만 대×200GB=2,000만GB에 실현가격 1GB당 1,000원 변화를 '
                '적용하면 원화 매출 민감도는 200억원이지만 실제 계약·매출 전망이 아닙니다.'
            )
        if '개발 공식 확인' in cat:
            return (
                'Micron 공식 발표로 EIM 연구개발 자체를 확인한 단계입니다. '
                '공개된 메모리 적층 구조·LPDDR 세대·성능 목표·시제품 일정이 '
                '10/16 경영진 보도 대비 새로 확인됐는지 판단하고, '
                '신규 생산라인 투자액과 출하·매출은 분리합니다.'
            )
        if '시제품 제공·검증' in cat:
            return (
                'EIM 실제 시제품을 로봇·칩셋 고객에게 제공해 인증·수율·성능을 '
                '측정하기 시작한 단계입니다. 고객 이름, 공급 개수, '
                '고온 동작 검사·지연시간·전력 소모량·검사 시간을 확인해야 합니다.'
            )
        if '정식 채택·공급계약' in cat:
            return (
                'Micron 공식 고객 선정 또는 서명된 공급계약으로 제품 기술이 '
                '실제 매출 파이프라인으로 진입한 단계입니다. '
                '고객 실명·계약금액·납기·평균판매단가·검수·반복 발주를 확인합니다.'
            )
        if '실제 양산·상업 출하' in cat:
            return (
                'EIM 양산이나 유상 출하를 회사가 확정한 단계입니다. '
                '실제 양품 칩 수·출하량·실현 단가·제품별 매출총이익률·'
                '고객 검수 및 반품·교환 접수를 추적합니다.'
            )
        return 'EIM 개발 내용 보도 단계이며 고객 계약·양산 매출과 다릅니다.'
    if cat in ROBOT_OCT16_MEANINGS:
        return ROBOT_OCT16_MEANINGS[cat]
    if cat in _OCT15_MEANINGS:
        return _OCT15_MEANINGS[cat]
    if cat.startswith('Fluence–Vattenfall · '):
        if '정식 턴키 공급계약' in cat:
            return (
                '10/14 Fluence 공식 발표로 Vattenfall 독일 Brunsbüttel '
                '254MW·1,000MWh 초과(약 4시간) ESS 공급계약을 확인했습니다. '
                '9/10 투자 최종결정과 달리 이번에는 공급사 계약 체결 단계입니다. '
                'Gridstack Pro 5000 배터리·전력변환장치·에너지관리시스템과 '
                '설계·조달·시공·시운전·장기 유지보수를 포함합니다. '
                '2027년 착공 예정, 2028년 말 50Hertz 380kV 계통 연결 목표입니다. '
                '계약액·셀 공급사·서비스 계약기간은 비공개입니다. '
                '독일 4시간 ESS 업계 턴키 참고단가 280~450유로/kWh를 '
                '1GWh에 적용한 전체 사업비 참고범위는 '
                '2억8,000만~4억5,000만유로(10/14 기업은행 환율 '
                '1유로 1,500.24원 적용 약 4,201억~6,751억원)이며 '
                'Fluence 계약 매출은 아닙니다.'
            )
        if '실제 착공' in cat:
            return '2027년 예정 단계에서 현장 공사 개시가 직접 확인된 후속 단계입니다. 부지·계통공사·보험·자금집행·첫 장비반입을 추적합니다.'
        if '전원 인가' in cat:
            return '공사 계획을 넘어 독일 50Hertz 380kV 송전망 전원 인가와 현장 가동이 확인된 후속 단계입니다. 성능시험·인수·반복 유지보수 매출을 추적합니다.'
        if '계약 후퇴' in cat:
            return '기존 공급계약이 취소·변경된 실제 계약 단계 후퇴입니다. 철회비용·설비·공사 진척과 재계약 조건을 확인합니다.'
        return '9월 투자 최종결정만 반복되면 새 공급계약 알림으로 인정하지 않습니다.'
    if cat == '삼성SDI · 증권사 3분기 추정·4분기 수주 기대':
        return (
            '10/08 DS투자증권의 매출 약 4조120억원·영업이익 2,575억원은 '
            '3분기 추정치, 정산이익 약 1,500억원은 예상 일회성입니다. '
            '4.5조원 삼성디스플레이 매각은 8월 기존 발표이고 '
            '2028년 2개 라인·10GWh 증설은 아직 검토 단계입니다. '
            '회사 분기실적·신규 공급계약·장비발주 확인 시만 추가 알림합니다.'
        )
    if cat == '알림 품질 정정 · Telegram 218번 1번 오탐':
        return (
            '앞서 전송된 Telegram message_id=218의 1번 '
            '삼성SDI 5% 상승 관련 서울경제 기사는 '
            'ESS 수요 기대와 주가 반응만 다룬 보도로서 신규 '
            '수주·발주·확정 실적이 아니므로 고신호에서 제외합니다. '
            '2번 CATL–INTILION 최대 3GWh 개발협약과 '
            '3번 Dexmate–LG CNS 사용·유통 CEO 발언은 유효합니다. '
            '기존 감시기가 5% 오르며라는 주가 표현을 감지하지 못한 '
            '공통 필터 문제를 수정하고 회귀검사를 추가했습니다.'
        )
    if cat == 'CATL–INTILION · 유럽 5년 최대 3GWh 공동개발 목표':
        return (
            'INTILION CEO 10/09 공개 발언과 pv magazine 10/13 기사 대조: '
            'CATL와 독일·오스트리아·스위스에서 향후 5년간 '
            '최대 3GWh 나트륨이온 ESS를 공동 개발한다는 협약입니다. '
            '3GWh=3,000MWh=300만kWh이나 확정 구매량·납품량·매출은 아닙니다. '
            '기존 2025년 최대 10GWh 계약 범위와 포함관계가 불명확해 합계 '
            '13GWh로 집계하지 않습니다. 실제 단가 미공개로 사업비 미산정. '
            '가정상 kWh당 1만원 가격 차이는 전체 목표 용량에 300억원 민감도입니다. '
            '셀·전력변환장치·현장 시공과 차후 시스템 관제·장기 유지보수 계약을 '
            '나누되 이번 협약의 서비스 매출·기간은 아직 미정입니다. '
            '프로젝트 실명·부지·구매계약→설치·시험·전원인가→실제 출하로 '
            '매출 경로를 추적합니다.'
        )
    if cat == 'CATL–INTILION · 실제 구속력 있는 구매계약':
        return (
            '공동개발 목표에서 지정 프로젝트의 실제 구매·공급 의무로 '
            '전환한 회사 공식 단계입니다. 계약규격·용량 GWh·가격·'
            '기한·철회조건·선급금·검수·설치·매출인식을 확인하고 '
            '2025년 10GWh 및 2026년 3GWh 목표와 중복 합산하지 않습니다.'
        )
    if cat == 'CATL–INTILION · 첫 현장 실제 가동':
        return (
            '공동개발 협약과 달리 유럽 현장에서 실제 전원 인가·준공을 '
            '확인한 단계입니다. 설치 MW/MWh·프로젝트·인수시험·'
            '가동률·운영·유지보수 매출 계약을 분리합니다.'
        )
    if cat == 'CATL–INTILION · 나트륨 ESS 협약 후퇴':
        return '공식 협약 취소·목표 축소·프로젝트 철회가 확인된 역방향 사건입니다. 선지출·대체수요·납품시점을 점검합니다.'
    if cat == 'Dexmate–LG CNS · 사용·유통 CEO 현장발언':
        return (
            '2026년 10월 13일 뉴욕 Dexmate CEO 타오 첸의 이데일리 현장 인터뷰: '
            'LG가 자사 로봇을 사용하고 한국에서 유통도 돕는다고 직접 발언했습니다. '
            'LG CNS의 3월 전략투자·물류 및 제조 현장 개념검증은 '
            '기존 공식 확인 사실이며, 새 발언은 실사용·유통 단계의 '
            '구체화입니다. 독점 유상 유통계약·판매 대수·LG CNS 로봇 매출은 '
            '확정되지 않았습니다. CEO가 밝힌 세계 수백 대 공급은 '
            '자기보고로, 실제 고객별 판매·사용·실증을 구분합니다. '
            '99.99%는 산업현장에서 필요한 성공률 목표이지 '
            '달성·측정된 결과가 아닙니다. '
            'RoboStrategy 투자자가 말한 특화 작업 2~3년·범용 약 5년은 '
            '회사 상용화 확정 일정이 아니라 전망입니다.'
        )
    if cat == 'Dexmate–LG CNS · 공식 유료 공급계약':
        return (
            '로봇의 현장 사용·전략투자에서 고객 실명 유상 구매·배치 '
            '계약으로 전환한 단계입니다. LG CNS 직접 매출인지 '
            'Dexmate의 로봇 출하 매출인지, 대수·평균판매단가·검수·'
            '고객 설치·장기 유지보수 계약을 별도 확인합니다.'
        )
    if cat == 'Dexmate–LG CNS · 실제 작업성공률 실측':
        return (
            '산업현장 특정 작업에서 로봇 작업 성공률·사람 개입률·'
            '연속 실패·사이클타임을 실제 측정한 공식 자료의 단계입니다. '
            '필요한 99.99% 신뢰성 목표와 실측 달성은 다른 것입니다.'
        )
    if cat == '로브로스 실증특례 · Telegram 오탐 정정':
        return (
            '10/13 Telegram 213번 1번 로보티즈 주가 4.86% 조정과 '
            '3번 LG전자 일반 심층분석, 214번 ESS 수요 폭증 전망은 '
            '신규 계약·출하·실측이 없는 오탐이므로 제외합니다. '
            '213번 2번 로브로스 휴머노이드 20대 규제특례 승인은 '
            '산업통상부 공식 보도자료 2~3·9쪽 확인으로 유효합니다. '
            '위험성평가·안전조치 전제이며 20대 실제 배치나 유상 판매가 아닙니다. '
            '30억원은 과거 공개가를 이용한 참고 계산으로 계약금액이 아닙니다.'
        )
    if cat == '로브로스 산업실증 · 이동형 휴머노이드 20대 규제특례 승인':
        return (
            '10/13 산업통상부 제6차 산업융합 규제특례 승인 보도: '
            '로브로스 이동형 휴머노이드 20대를 네패스 반도체 부품 세척, '
            '성우하이텍 차체부품 안착, HD현대삼호 조선 기자재 적재, '
            '딜리버리랩 냉장 물류 적재에 실증 투입하도록 허용했습니다. '
            '이번 20대는 설치·납품 완료나 확정 구매매출이 아니며 '
            '고객별 대수·실제 납품단가·계약액·새 정부예산도 미공개입니다. '
            '2025년 IGRIS-C 회사 공개 사전예약가 1대 약 1억5천만원을 '
            '20대에 일률 적용한 30억원은 참고 계산일 뿐 '
            '이번 계약액·정부 예산·확정 매출이 아닙니다. '
            '로브로스 8/19 유상 실증 공급 9대와의 겹침도 불명이므로 '
            '9+20을 판매·설치 합계로 표시하지 않습니다. '
            '핵심 후속은 실제 설치→안전펜스 대안 검증→'
            '작업 성공률·사람 개입률·가동률→반복 구매계약입니다.'
        )
    if cat == '로브로스 제조현장 · 실제 배치 개시':
        return (
            '규제 승인 후 지정 현장에 실제 로봇이 설치·시운전되기 시작한 '
            '회사 1차자료 신호입니다. 현장별 대수·계약액·유상 공급 여부·'
            '안전관리 조건을 확인하고 이미 발표된 승인 수량과 중복 집계하지 않습니다.'
        )
    if cat == '로브로스 제조현장 · 작업 KPI 실측':
        return (
            '로봇의 공장 투입을 넘어 실제 사람-로봇 혼재 공정에서 '
            '작업 성공률·사람 개입률·정지시간·작업 사이클을 공개한 '
            '1차 정량 성능 신호입니다. 기존 공정 대비 생산성·안전성 개선과 '
            '정비비를 확인해 다음 고객 반복 발주 가능성을 평가합니다.'
        )
    if cat == '로브로스 제조현장 · 고객 정식 유상계약':
        return (
            '실증 승인 또는 협약이 아니라 로브로스·고객사 직접 '
            '유상 구매·반복 주문 계약을 발표한 단계입니다. '
            '원화 계약액과 납품 물량, 검수 시점·유지보수 조건을 '
            '별도 확인한 후에만 매출로 환산합니다.'
        )
    if cat == '로브로스 실증특례 · 승인 후퇴·현장 안전 역풍':
        return (
            '실증 허용 범위 축소·중단 또는 현장 안전사고로 '
            '실증 일정이 늦춰진 회사·규제당국의 역방향 확인입니다. '
            '중단 사유·책임주체·재개 조건·영향받는 대수를 구분합니다.'
        )
    if cat == '로봇 사후학습 · GPU시간 실측 공개':
        return ('개발사의 실측 GPU시간 공개 단계입니다. GPU 수·경과시간·'
                '동일조건 비교·실제 활용률을 확인합니다. GPU시간은 GPU 발주나 '
                '데이터센터 증설 계약·원화 매출과 다릅니다.')
    if cat == '로봇 사후학습 · Funda AI 3~4배 추정 기준선':
        return (
            'Funda AI 2026-10-12 보고서의 익명 업계 조사로, 주로 70억~130억 '
            '파라미터급 로봇 모델의 영상·관절·행동 신호 사후학습 작업이 '
            '동일 파라미터 텍스트 사후학습보다 GPU 자원 약 3~4배를 '
            '소모할 수 있다는 비교 추정입니다. 비교 GPU 종류·입력 길이·'
            'GPU시간 원자료와 독립 재현은 공개되지 않았습니다. '
            '단일 로봇 사후학습 작업은 초대형 언어모델의 전체 사전학습보다 '
            '훨씬 작으며, 실제 산업 GPU 수요는 데이터 전처리·물리 시뮬레이션·'
            '검증·반복 학습 및 프로젝트 수가 결정합니다. '
            'Figure–Nscale 9/3 연산 서비스 약정은 별도 공식 계약으로 '
            '이번 10/12 GPU 3~4배 추정의 검증 결과나 신규 계약이 아닙니다.'
        )
    if cat == 'CATL 관계사–VNET · 10/12 주가 기사 오탐 정정':
        return (
            '이전 Telegram 208의 1·3번 ESS 주가 강세·수주 기대감 기사는 신규 수주·확정 분기 실적이 아니므로 고신호에서 제외합니다. '
            '유효 사실은 9/21 CATL 비연결 관계사 연계 투자기구의 VNET 기존주 650,424,192주 취득·38.1% 보유입니다. '
            '8월 데이터센터 전력 협력은 확인되지만 나트륨 ESS 독점계약·물량·설치·매출은 미확정입니다. '
            'VNET 889MW는 2025년 말 도매 IDC 전력 용량이며 2026년 6월 말 1,007MW 가동·744MW 이용 규모와 구분합니다. '
            '4월 CATL–HyperStrong 60GWh는 VNET 발주가 아닙니다.'
        )
    if cat == 'CATL 관계사–VNET · 9/21 간접지분 38.1% 인수 종결':
        return (
            'VNET 9/21 공식 공시로 CATL 비지배·비연결 관계사와 연결된 '
            '투자기구의 기존주 650,424,192주 매입·38.1% 보유가 확정됐습니다. '
            'VNET 신규 유상증자 자금은 아니며 CATL 직접 취득도 아닙니다. '
            '8월 CATL–VNET 데이터센터 전력 통합협력은 별도로 확인되지만 '
            '나트륨 ESS 독점 발주·설치·매출은 공개되지 않았습니다. '
            'VNET 가동 도매 IDC 용량은 2025년 말 889MW에서 '
            '2026년 6월 말 1,007MW(고객 실제 사용 744MW)로 증가했습니다. '
            '전력 MW와 배터리 MWh를 혼동하지 않습니다. '
            'CATL–HyperStrong 4월 60GWh 주문은 VNET 구매물량이 아닙니다.'
        )
    if cat == 'CATL–VNET · 나트륨 ESS 실명 공급계약':
        return (
            '지분·데이터센터 전략적 협력에서 나트륨 ESS 구매계약으로 단계가 상승한 '
            '공식 이벤트입니다. 계약 MWh·납품일·현장·단가·안전 검수·매출 인식과 '
            '장기 유지보수 계약을 확인하고 HyperStrong 60GWh와 분리합니다.'
        )
    if cat == 'ESS LFP 북미 조달 · 314Ah 9월 CIF 가격·관세 가정':
        return (
            'Benchmark 2026년 9월 실제 314Ah LFP 가격평가: 중국 EXW '
            '51.62달러/kWh(약 69,216원), 북미 CIF 61.99달러/kWh(약 83,121원). '
            '10.37달러(20.09%) 차이는 운송·보험 등을 포함한 인도조건 차이이며 '
            '북미 CIF는 관세 이전 가격입니다. '
            '디일렉이 인용한 최대 40.9%를 CIF에 단순 곱하면 '
            '87.34달러/kWh(약 117,118원)이지만 이는 실제 확정 관세가 '
            '아닌 시나리오입니다. 환산은 1달러=1,340.88원 '
            '(2026-10-12 03:20 KST 제공 환율)을 적용했습니다. '
            '1GWh=100만kWh 기준 중국산 북미 CIF 약 831.21억원, '
            '관세 가정 약 1,171.18억원, 차액 약 339.97억원입니다. '
            '미국 현지 생산 기업의 매출·원가·마진이 확정된 것은 아닙니다.'
        )
    if cat == '배터리 산업기술 로드맵 · 9월 정부 발표 기존 기준선':
        return (
            '산업통상부 2026-09-22 공식 로드맵은 연구개발 총사업비를 '
            '약 4,000억원으로 발표했습니다. 9/22 세부계획 관련 보도상 '
            '정부 민관공동개발 2,554억원·공통기술 620억원 등 국비 '
            '3,174억원, 민간 대응자금은 851억원·226억원 등 1,077억원으로 '
            '합계 4,251억원입니다. 따라서 10/12 기사 약 3,000억원 국비와 '
            '약 4,000억원 총사업비는 서로 다른 범위일 수 있습니다. '
            '민간의 별도 2026~2030년 연구개발·설비투자 계획 '
            '7조9,328억원과 중복 합산하지 않습니다. '
            '610억원 로봇·드론용 개발사업은 사업 포함·집행 관계 미확정으로 '
            '새 예산이나 새로운 계약이라고 알리지 않습니다.'
        )
    if cat == '미국 EV→ESS 전환 · 기존 공장 재배치 배경':
        return (
            '북미 전기차 배터리 공장의 ESS 전환은 이미 시행 중인 '
            '업계 전략입니다. 1000억달러 누적투자 추정, '
            '275GWh 설비 대비 182GWh 수요 전망 등을 오늘 신규 '
            '투자나 공장 가동중단 확정이라고 알리지 않습니다. '
            '기업의 신규 상업가동·공식 물량·수주·실제 매출을 분리합니다.'
        )
    if cat == 'Optimus 손·자석 · 2025년 공급망 차질 경영진 회고':
        return ('머스크는 X Takeover에서 작은 셀프태핑 나사를 집어 나무에 박는 정밀조작과 힘 제어를 동시에 달성하기 어렵다고 설명했습니다. '
                '2025년 중국의 모터용 희토류 자석 수출 제한으로 Optimus가 2~3개월 지연됐었다는 회고는 공급망 위험의 정량 근거입니다. '
                '현재 V3 일정이 2~3개월 새로 지연됐다는 뜻은 아닙니다. '
                '다음 단계는 처음 보는 작업의 자율수행 성공률·사람 개입률, 정밀 구동 부품 수율, 대체자석 고객 승인과 실제 출하입니다.')
    if cat == 'Optimus 손·자석 · 실제 신규 일정변경 확인':
        return ('최근 공급망 차질이 실제 V3 생산 일정을 새로 변경했다는 경영진 발언 단계입니다. 기존 2025년 2~3개월 차질과 분리해 새 기준일·인증기간·대체 공급사와 생산량을 확인합니다.')
    if cat == '휴머노이드 두뇌 D램 · 고객 실명 양산 공급계약 확인':
        return (
            '시장 조사기관의 19→39GB 전망과 달리 메모리 제조사가 '
            '특정 로봇·연산 플랫폼 고객과 정식 저전력 D램 납품 계약 또는 '
            '첫 양산 출하를 발표한 별도 단계입니다. '
            '계약업체·고객 실명·적용 로봇 모델·규격·출하 수량·'
            '고객 검수·평균판매단가·원화 매출인식 및 반복 납품을 '
            '각각 확인해야 하며 회사 발표만으로 시장 전체 수요를 '
            '자동 확정해서는 안 됩니다.'
        )
    if cat == '휴머노이드 두뇌 D램 · 2030년 수요 신규 전망':
        return (
            '카운터포인트리서치 10/10 전망: 로봇 1대 평균 D램은 '
            '2026년 19GB→2030년 39GB, 산업 연간 D램 수요는 '
            '8,300→172,000Tbit(약 20.72배)로 증가할 것으로 예상됩니다. '
            '물량×단위는 1Tbit=125GB의 십진 환산으로 각각 '
            '1,037,500GB→21,500,000GB입니다. '
            '대당 평균으로 나눈 역산 출하규모는 약 5만 4,605대→55만 1,282대에 '
            '해당하지만 실제 출하 실적은 아닙니다. '
            '1GB당 평균판매단가가 가정상 1,000원 변할 때 2030년 전 산업 연간 '
            '매출 민감도는 215억원(2026년 약 10억 3,750만원)입니다. '
            '이는 실거래 단가·매출 가이던스가 아닙니다. '
            '현재 로봇 주력은 저전력 D램 LPDDR과 낸드 저장장치이며 '
            '39GB를 낸드·HBM 탑재량에 그대로 적용하면 안 됩니다.'
        )
    if cat == '휴머노이드 두뇌 D램 · 조사기관 전망치 공식 수정':
        return (
            '카운터포인트 공식 원문이 과거 2026년 19GB·8,300Tbit, '
            '2030년 39GB·172,000Tbit 대비 전망을 직접 변경한 단계입니다. '
            '로봇 대당 D램과 연간 비트 수요를 다시 검산하고 수정 원인을 '
            '출하량·제품 조합·전력·가격으로 분리해 확인해야 합니다.'
        )
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
    if cat == '알림 운영 정정 · CATL–INTILION 동일 프로젝트 중복 제외':
        return ('3GWh 개발 목표를 확정 구매·매출로 오인하거나 기존 10GWh 협력과 중복 합산하는 것이 핵심 위험입니다. 기사 제목의 고객명 누락 시 동일 사건 판정이 어려워지는 문제를 수정했습니다.')
    if cat == '알림 품질 정정 · Telegram 238번 주가 반응 오탐':
        return '주가 상승·테마 기사와 신규 계약·가동·매출을 섞으면 거짓 수혜가 발생합니다. 이후 첫 신규 수주·확정 실적 공시가 있을 때만 단계 상승으로 알립니다.'
    if cat.startswith('글로벌 계통용 BESS · '):
        return (
            '세계 설치통계가 한국 배터리의 실제 수주를 보증하지 않습니다. '
            '중국이 9월 12GWh 이상을 차지하고 지역별 원산지 규제·가격이 다릅니다. '
            '열폭주·배기·방폭·냉각·보험·소방 인증과 전력망 접속·전원 인가 시점이 '
            '개별 사업의 최대 설치 병목입니다. '
            '가상의 9월 전체 가동량 20.4GWh가 25% 줄면 5.1GWh '
            '(510만kWh) 감소하지만 이는 실제 감소 예측이 아닙니다. '
            '앞으로 6~12개월은 지역별 신규 가동·프로젝트 인허가·'
            '고객별 확정 공급계약·준공 지연을 구분합니다.'
        )
    if cat.startswith('삼성SDI LFP BBU · '):
        return (
            '9/29 제품 공개와 2027년 2분기 예상은 안정 양산·고객 수주와 다릅니다. '
            '원통형 LFP 고출력 방전의 발열·충전균일성·열폭주 전파, '
            '서버 인증·신뢰성·보험·보증충당금·장비 전환 비용이 병목입니다. '
            '향후 6~12개월 확인할 지표는 실제 고객검수·첫 출하·'
            '직행수율·가격 및 데이터센터 운영가동률입니다.'
        )
    if cat.startswith('미국 ESS 공급망 · '):
        return (
            '최대 역풍은 익명 업계 보도가 실제 전면철수로 이어지지 않거나 '
            '중국산 셀의 가격 경쟁력이 유지돼 한국 기업 신규 수주가 늘지 않는 경우입니다. '
            '미국 48E ESS 세액공제 적격 비PFE 조달원가 비율은 '
            '2026년 55%이고 2030년 75%로 강화됩니다. '
            '프로젝트별 관세 분류·세액공제 적용·현지 공장 가동률, '
            '열폭주·배기·방폭·냉각·보험·인허가·전원 인가 시점을 검증해야 합니다. '
            '6~12개월 위험 구간의 조기 지표는 중국 업체 공식 종료, '
            '미국 실제 재입찰, 한국 업체 신규 공급계약, 출하 GWh입니다.'
        )
    if cat.startswith('마이크론 EIM · '):
        return (
            '핵심 실패 경로는 논리 반도체 위 LPDDR 적층의 휨·발열·층간 접속 결함으로 '
            '수율이 떨어지고 고객 신뢰성 검증이 지연되는 경우입니다. '
            '고온 동작 검사·검사 시간·전력당 대역폭·레이턴시·'
            '반품·교환 접수·설비투자 부담을 확인해야 합니다. '
            '2028년 하반기는 업계 예상일 뿐 확정 양산이 아닙니다. '
            '6~24개월 위험 구간의 조기 지표는 회사 공식 사양, '
            '고객 검증 일정, 패키징 양품률, 상업 출하 여부입니다. '
            'EIM과 HBM을 로봇에 동시 탑재한다고 단정하거나 '
            '고객 실명이 미확정인데 엔비디아·테슬라 수주로 표시하지 않습니다.'
        )
    if cat in ROBOT_OCT16_RISKS:
        return ROBOT_OCT16_RISKS[cat]
    if cat in _OCT15_RISKS:
        return _OCT15_RISKS[cat]
    if cat.startswith('Fluence–Vattenfall · '):
        return (
            '최대 역풍은 50Hertz 380kV 송전망 접속·변전설비 완공 또는 '
            '화재·열폭주·배기·방폭·냉각·보험·독일 안전 인허가 지연으로 '
            '2028년 말 전원 인가가 연기되는 경우입니다. '
            '향후 6~24개월 확인할 지표는 EPC 진척률·설비 반입·'
            '셀 품질·현장 화재안전검사·고온 동작·인수 시험·'
            '예상 설치비 대비 원화 투자원가와 준공 일정입니다. '
            '계약금액·셀 공급사 비공개이므로 삼성SDI 매출로 '
            '연결하거나 모든 예상 총사업비를 Fluence 매출로 표시하지 않습니다.'
        )
    if cat == '삼성SDI · 증권사 3분기 추정·4분기 수주 기대':
        return '애널리스트 추정이 회사 확정 분기실적·신규 계약이 아닙니다. 영업이익의 일회성 GM 정산이익 약 1,500억원과 AMPC, 관세환급을 구분합니다.'
    if cat == '알림 품질 정정 · Telegram 218번 1번 오탐':
        return (
            '이 정정은 새 계약이나 매출이 아닙니다. '
            '주가 반응 기사에 신규 사업을 혼합하면 투자 판단이 왜곡됩니다. '
            '향후 원천기사 제목뿐 아니라 본문·원 공시에서 '
            '실제 신규 계약·매출·납품 여부를 분리해 확인합니다.'
        )
    if cat.startswith('CATL–INTILION · '):
        return (
            '주요 실패경로는 5년 개발 목표가 특정 프로젝트의 인허가·'
            '자금조달·전력접속·안전 검증을 통과하지 못해 확정 발주가 '
            '지연되는 것입니다. 초기 위험구간 6~24개월 동안 첫 구체 '
            '프로젝트 실명, 선급금, 보증보험·화재보험, '
            '열폭주 전파·가스 배기·방폭·냉각·소방 인증과 '
            '실제 전원 인가 시점을 확인합니다. '
            'CATL 공식 제품은 25℃ 1만5천회·45℃ 1만회 초과인데 '
            'INTILION CEO의 고온 1만5천회 이상 설명과 '
            '동일 시험조건인지 미확인입니다. '
            '조건이 다른 사이클수명을 확정 수명·보증기간으로 환산하지 않습니다.'
        )
    if cat.startswith('Dexmate–LG CNS · '):
        return (
            '가장 현실적인 실패경로는 현장 도입 시연에서 '
            '99.99% 수준의 작업 반복 신뢰성·보험·안전·'
            '정비비가 확보되지 않아 유료 확대가 지연되는 경우입니다. '
            '성공률 99.99%는 평균 1만회당 오류 약 1회에 해당하는 '
            '요구수준이지 Dexmate의 실측 결과가 아닙니다. '
            '향후 6~12개월 동안 고객별 유상 설치 수량, '
            '사람 개입률, 작업성공률, 가동률, 보증충당금·'
            '원격지원 비용, 반복 발주 여부를 확인합니다. '
            'RoboStrategy 자산의 Standard Bots 비중 31.3%와 '
            'Dexmate 비중 9.1%는 투자자 전망의 이해관계 위험입니다.'
        )
    if cat == '로브로스 실증특례 · Telegram 오탐 정정':
        return (
            '20대 계획은 확정 납품이 아닙니다. '
            '향후 실제 설치·위험성평가·작업 성공률·유상 고객계약 변화만 재알림합니다.'
        )
    if cat.startswith('로브로스 산업실증 · ') or cat.startswith('로브로스 제조현장 · ') or cat.startswith('로브로스 실증특례 · '):
        return (
            '허가특례는 전국 상시 무인 허가가 아닙니다. '
            '가장 현실적인 6~12개월 실패 경로는 사람과 로봇의 동선 충돌, '
            '클린룸·냉장·조선 현장의 작업·지면 변화에 따른 '
            '정밀도·그립 수율 저하, 안전인증·보험·책임소재 협의 지연으로 '
            '시운전 후 정규 공정 편입과 유상 반복 주문이 늦어지는 경우입니다. '
            '20대는 사업계획 전체이므로 안전사고 1건도 전체 승인 범위에 '
            '부정적 영향을 줄 수 있습니다. '
            '조기지표는 현장별 실제 설치 대수(20대 중 몇 대인지), '
            '작업 성공률·사람 개입률·비상정지 횟수·고장수리 시간·'
            '안전관리 계획 이행과 보험 가입입니다. '
            '완화책은 구역 제한·사람 감독·비상정지·안전 검수 후 단계별 확대입니다.'
        )
    if cat.startswith('로봇 사후학습 · '):
        return (
            '동일 파라미터라도 동영상 길이·프레임률·해상도, 행동 샘플률, '
            'GPU 세대와 이용률이 다르면 3~4배를 일반화할 수 없습니다. '
            '특히 동영상 디코딩·시계열 동기화·데이터 로딩 지연이 '
            'GPU를 놀게 할 수 있어 계산량과 실제 유료 GPU시간을 구분합니다. '
            '실패 경로는 데이터 구매가 늘어도 신규 과제 성공률이 개선되지 '
            '않아 6~12개월 안에 다음 GPU 예약·집행이 늦어지는 경우입니다. '
            'GPU시간/학습 에피소드·양품 데이터 비율·검증 작업 성공률·'
            'GPU 이용률·실제 계약/전원 인가 시점을 먼저 확인합니다.'
        )
    if cat.startswith('CATL 관계사–VNET · ') or cat.startswith('CATL–VNET · '):
        return (
            '지분취득과 VNET 데이터센터용 배터리 전속 공급권은 다릅니다. '
            '전력망 접속·설치허가·배터리 열폭주·배기·방폭·냉각·보험·검수와 '
            '셀 수율이 실제 채택 병목입니다. '
            '6~12개월 조기지표는 공식 ESS 발주 MWh·인증·시공·전원 인가일, '
            '24개월은 납품 실적·반복 유지보수 현금 회수입니다.'
        )
    if cat == 'ESS LFP 북미 조달 · 314Ah 9월 CIF 가격·관세 가정':
        return (
            '40.9%를 모든 중국산 314Ah 셀의 확정 세율로 취급하면 '
            '상품분류·면제·과세가격 차이를 놓칩니다. '
            '중국 9월 리튬가격 하락이 뒤늦게 반영되거나 운임이 '
            '내리면 북미 가격차가 다시 줄어들 수 있습니다. '
            '셀 열폭주 전파·배기·방폭·소화·냉각, '
            '현지 화재인증·보험, 고객 설치 지연·검수와 '
            '배터리 수율도 실제 매출의 병목입니다. '
            '6~12개월 조기지표는 다음 CIF/EXW 가격차, '
            '관세 공식 유효일, 북미 실제 GWh 출하와 가동률입니다.'
        )
    if cat.startswith('Optimus 손·자석 · '):
        return ('손의 정밀 제어·토크·촉각·마찰·발열·반복 내구성과 희토류 자석 납기·품질·원산지 인증이 결합한 병목입니다. '
                '실패 경로는 자석 공급 지연→모터·손 액추에이터 생산 불능→조립 라인 공백→로봇 인도 지연입니다. '
                '과거 2~3개월 차질은 2025년 회고 수치이며 새로운 2026년 V3 일정 지연을 추정하지 않습니다. '
                '향후 6~12개월 조기지표는 대체자석 승인, 모터 양산수율, 실제 손 작업 성공률·재작업률, 로봇 주간 실출하입니다.')
    if cat.startswith('휴머노이드 두뇌 D램 · '):
        return (
            '가장 현실적인 실패 경로는 로봇 양산이 지연되거나 메모리 최적화로 '
            '실제 대당 탑재량이 전망보다 적어지는 것입니다. 2030년 수요 '
            '172,000Tbit의 25%만 미달해도 연간 43,000Tbit '
            '(5,375,000GB)가 줄어듭니다. '
            '저전력 D램 발열·전력소모·대역폭, 낸드 쓰기수명·저장 용량, '
            '반도체 패키징 수율·고온 동작 검사·신뢰성 검증, '
            'HBM 증설에 따른 웨이퍼 공급경쟁을 별도 병목으로 봅니다. '
            '6~24개월 조기경보는 로봇 실제 출하 대수, LPDDR 채택 용량, '
            '메모리 가격·수율, 반복 주문입니다. '
            '삼성전자·SK하이닉스·마이크론의 휴머노이드 실제 고객 실명·'
            '공급계약·매출은 조사기관 전망만으로 확인되지 않습니다.'
        )
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
    if group == 'alert_quality_246':
        return '기존 Actions Run #693 실제 메시지 246 대조 · 10/09 INTILION 1차 발언과 10/13 pv magazine · 10/20 아이뉴스24 동일 사건 교차확인'
    if group == 'alert_quality_238':
        return (
            'GitHub Run #664 실제 출력 아티팩트와 Telegram API message_id=238 '
            '대조 확인 · 비즈니스포스트 1번은 주가반응 오탐 · '
            '2번 BMI 글로벌 가동 통계는 정상 · Python 재발방지 테스트 추가'
        )
    if group == 'global_bess_commissioned':
        return (
            'Benchmark Mineral Intelligence 집계를 인용한 Energy-Storage.News '
            '10/15 기사·한국에너지기술평가원 10/16 재확인 · '
            '조사기관 원자료 전체 직접 열람은 별도 · '
            '글로벌 실제 가동량이며 기업별 계약·수주 금액 확인 아님'
        )
    if group == 'sdi_lfp_bbu':
        if _sdi_bbu_lfp_stage(text,item.get('source') or '') in (
            'official_first_lfp_bbu_sop','official_customer_order'
        ):
            return '삼성SDI 1차자료 확인 · 고객·제품·계약/출하·원화 매출 별도 검증'
        return (
            '삼성SDI 9/29 LFP BBU 21700 공개는 회사 공식 발표, '
            '2027년 2분기 말레이시아 계획은 10/18 언론보도만 존재 · '
            '회사 실제 양산·고객 납품 공식 확인 전'
        )
    if group == 'china_ess_us_exit_report':
        if _cn_ess_us_exit_stage(text,item) == 'company_confirmed_us_exit':
            return '해당 기업 공식 웹도메인 종료 발표 · 종료계약·대체 고객·매출 추가 검증'
        return (
            'DIGITIMES 10/19 원제·대만 현지 03:00·공개 도입부 검색 확인 · '
            '유료 본문 직접 열람 실패 · 익명 공급망 업계 보도 단계 · '
            '개별 중국기업 철수 공시·한국기업 대체 수주 미확인 · '
            '미 IRS Notice 2026-15·USTR 관세·Wood Mackenzie 교차 검증'
        )
    if group == 'micron_eim_edge':
        stage = _micron_eim_stage(text,item)
        if stage == 'executive_reported_rnd':
            return (
                '10/16 디일렉 SEDEX 현장 이철 상무 발언 보도 · '
                '마이크론 공식 로보틱스 제품·메모리 자료로 적용 방향 확인 · '
                '회사 명의 EIM 시제품·양산·고객계약 공식 공개 미확인 · '
                '2028년 하반기는 업계 예상'
            )
        if stage.startswith('company_confirmed'):
            return (
                'Micron 회사 도메인 1차자료 확인 · R&D/시제품/고객/양산 '
                '증거단계 분리 · 실제 제품 수율·납품금액·매출 인식 추가 확인'
            )
        return 'EIM 개발단계 불확실 · 회사 명의 신규 사양 또는 납품자료 미확인'
    if group in ROBOT_OCT16_TITLES:
        return _oct16_verification(item,group,text)
    if group in ROBOT_OCT15_TITLES:
        return _oct15_verification(group, text, item.get('source') or '')
    if group == 'fluence_vattenfall_bess':
        stage = _fluence_vattenfall_stage(text,item.get('source') or '')
        if stage=='official_signed_turnkey_award':
            return (
                'Fluence 10/14 GlobeNewswire 직접 서명계약 보도자료 · '
                'Vattenfall 9/10 공식 최종투자결정 · pv magazine 10/14 교차검증 · '
                '계약액·셀 업체·서비스 연수 비공개'
            )
        return 'Vattenfall·Fluence 1차자료 직접 확인 단계 · 기존 공급계약과 별도'
    if group == 'sdi_oct08_broker_preview':
        return 'DS투자증권 10/08 전망 · 삼성SDI 공식 실적·장비발주·신규 수주 아님'
    if group == 'alert_quality_correction':
        return (
            'Run #584 실제 Telegram 발송문·서울경제 기사 제목 대조 · '
            '1번 주가반응 오탐, 2·3번 사업 신호 유지 · '
            '기존 Python 제목 필터 원인 수정'
        )
    if group == 'catl_intilion_sodium':
        stage = _catl_intilion_stage(text,item.get('source') or '')
        if stage == 'sodium_3gwh_development_framework':
            return (
                'INTILION CEO 10/09 직접 LinkedIn 게시글·pv magazine 10/13 '
                '교차확인 · 3GWh 공동개발 목표, 확정 구매·수주·납품 아님'
            )
        return 'CATL·INTILION 1차자료 단계 · 구체 계약·실제 설치·매출 별도 확인'
    if group == 'dexmate_lg_commercial':
        stage = _dexmate_lg_stage(text,item.get('source') or '')
        if stage == 'ceo_reported_use_distribution':
            return (
                'Dexmate CEO 타오 첸 10/13 현장 인터뷰 발언 · '
                'LG CNS 3월 공식 전략투자·개념검증 교차확인 · '
                '유상판매 대수·독점 계약·99.99% 달성 미확인'
            )
        return 'LG CNS·Dexmate 직접 공시 기준 · 유상매출·정량 현장 KPI 별도 검증'
    if group == ROBROS_PILOT_GROUP:
        if item.get('robros_false_alert_correction'):
            return (
                'Telegram 213·214 실발송 기록 · 산업통상부 14쪽 공식 PDF '
                '및 연합뉴스 확인 · 일반 주가/전망 오탐 3건 정정'
            )
        stage = _robros_pilot_stage(text,item.get('source') or '')
        if stage == 'approved_pilot_report':
            return (
                '10/13 산업통상부 14쪽 공식 보도자료 2~3·9쪽 확인 · '
                '연합뉴스·파이낸셜뉴스 교차검증 · 노동부 위험성평가·위험 감소조치 전제 · '
                '개별 허가증 전문은 미확인 · 20대 계획, 실제 납품·계약매출 아님'
            )
        if stage in {'official_site_deployment','official_site_kpi','official_site_contract','official_pilot_reversal'}:
            return '로브로스·고객사·규제당국 1차자료 확인 단계 · 계획·실적 별도'
        return '기존 로브로스 실증 이력 또는 공식 승인 전 추정, 새 계약 아님'
    if group == 'robot_posttrain_compute':
        if _robot_posttrain_stage(text,item.get('source') or '') == 'official_measured_posttraining':
            return '로봇 개발사 공식 GPU시간 측정 발표 · 실측 조건·계약 별도 확인'
        return (
            'Funda AI 2026-10-12 원문 검색 결과의 본문 확인 · '
            '직접 URL 열람 실패 · 익명 업계 조사, 70억~130억 파라미터급 비교 추정 · '
            '실측 GPU시간·동일조건 독립 재현·신규 GPU 발주 미확인'
        )
    if group == 'catl_vnet_infrastructure':
        if item.get('correction_for_false_stock_alerts'):
            return '208번 메시지의 주가·수주 기대감 기사 2건 오류 정정 · VNET 9/21 공식 종결·미 SEC 공시만 유효 · 나트륨 ESS 전속 공급 미확인'
        if _vnet_catl_stage(text,item.get('source') or '') == 'signed_vnet_sodium_contract':
            return 'CATL/VNET 회사 공식 나트륨 ESS 계약 발표 · 실제 납품·매출 별도 확인'
        return ('VNET 9/21 공식 지분거래 종결 발표·미 SEC 공시 교차확인 · '
                'CATL 비지배·비연결 관계사 경유 · '
                'CATL–VNET 8월 전력협력은 확정, 나트륨 ESS 독점발주 미확인')
    if group == 'lfp_314_cif_north_america':
        return (
            'Benchmark Mineral Intelligence 2026-10-09 분기 원자료·'
            '디일렉 2026-10-12 교차확인 · 61.99달러는 관세 전 CIF · '
            '40.9%는 조건부 관세 가정, 실제 미국 통관 세율 미확정'
        )
    if group == 'optimus_hand_magnet':
        return ('2026-10-10 행사 주최 자료·영상 재게시·2026-10-11 구체적 대담 인용 보도와 Tesla Q2 실적자료 교차확인 · '
                '머스크의 2025년 자석 제한에 따른 2~3개월 과거 지연 회고 · 원대담 전체 직접 전사 미완료 · 신규 일정확정 아님')
    if group == 'humanoid_brain_dram':
        if _humanoid_dram_stage(text, item.get('source') or '') == 'confirmed_named_oem_order':
            return '메모리 제조사 직접 발표 · 로봇 고객 실명 계약·실출하 원문 확인 단계, 금액 별도 확인'
        if _humanoid_dram_stage(text, item.get('source') or '') == 'official_forecast_revision':
            return '카운터포인트리서치 직접 수정 발표 단계 · 기존 전망과 고객 확정 주문을 분리'
        return (
            '카운터포인트리서치 2026-10-10 공식 인사이트·연합뉴스·뉴스1 '
            '수치 교차확인 · 산업 전망치, 회사 실출하·공급계약 아님 · '
            'LPDDR D램/낸드/HBM별 용량 구분'
        )
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
    if title.startswith(ALERT246_CORRECTION_TITLE):
        return ALERT246_CORRECTION_TITLE
    if title.startswith('정정: Telegram 238번 1번'):
        return '정정: Telegram 238번 삼성SDI 주가 반응 오탐 제외'
    if _is_bess_bmi_actual(title+' '+source):
        if _bess_bmi_period(title) == '2026-09':
            return BESS_SEP26_TITLE
        return title
    if _is_sdi_bbu_lfp(title + ' ' + source):
        return '삼성SDI 21700 LFP BBU 실제 양산·공급계약 단계 변화'
    if _is_cn_ess_us_exit(title + ' ' + source):
        if source in {'CATL','Sungrow','BYD','HiTHIUM','HyperStrong'} and CN_ESS_US_FINAL_EXIT.search(title):
            return f'{source}, 미국 ESS 사업 철수 공식 확인…고객 이전 별도 검증'
        return CN_ESS_US_RETREAT_TITLE
    if _is_micron_eim(title + ' ' + source):
        if source in MICRON_EIM_PRIMARY_SOURCES:
            stage=_micron_eim_display_stage(title)
            if stage=='company_confirmed_sop':
                return '마이크론, 로봇용 EIM 실제 양산·상업 출하 공식 발표'
            if stage=='company_confirmed_customer':
                return '마이크론, 로봇용 EIM 고객 선정·공급계약 공식 발표'
            if stage=='company_confirmed_sample':
                return '마이크론, 로봇용 EIM 시제품 고객 검증 공식 발표'
            return '마이크론, 로봇용 EIM 연구개발 공식 사양 발표'
        return '마이크론, EIM 개발·고객 협의 공개…2028 양산은 업계 예상'
    _oct16=_oct16_group(title+' '+source)
    if _oct16 in ROBOT_OCT16_TITLES:
        return _oct16_clean_title(title,source)
    _oct15 = _oct15_group(title+' '+source)
    if _oct15 in ROBOT_OCT15_TITLES:
        return title
    if _is_fluence_vattenfall(title+' '+source):
        return 'Fluence, Vattenfall 독일 1GWh ESS 턴키·장기 유지보수 계약 확정'
    if title.startswith('정정: Telegram 218번 1번'):
        return '정정: Telegram 218번 1번 주가 반응 오탐 제외'
    if _is_catl_intilion_sodium(title + ' ' + source):
        if CATL_INTILION_BINDING.search(title) and source in CATL_INTILION_OFFICIAL:
            return 'CATL–INTILION 나트륨 ESS 정식 구매계약 공식 확인'
        return 'CATL–INTILION, 유럽 나트륨 ESS 5년 최대 3GWh 공동개발 목표'
    if _is_dexmate_lg(title + ' ' + source):
        if source in DEXMATE_PRIMARY and DEXMATE_PAID.search(title):
            return 'Dexmate–LG CNS 로봇 실제 유상 고객계약 확인'
        return 'Dexmate CEO: LG가 로봇 사용·한국 유통 지원…유상계약 별도'
    if title.startswith('정정: Telegram 213·214'):
        return '정정: 10/13 오탐 3건 제외·로브로스 승인 유지'
    if _is_robros_pilot(title + ' ' + source):
        if ROBROS_PILOT_APPROVAL.search(title):
            return '산업부, 로브로스 휴머노이드 20대·4개 현장 실증특례 승인'
        if ROBROS_DEPLOYED.search(title):
            return '로브로스 휴머노이드 실증 현장 실제 설치·가동 확인'
        if ROBROS_MEASURED.search(title):
            return '로브로스 산업현장 휴머노이드 작업 성능 실측 발표'
        if ROBROS_ORDER.search(title):
            return '로브로스 산업현장 휴머노이드 고객 유상계약 확인'
        return '로브로스 휴머노이드 산업 현장 실증 진행'
    if _is_robot_posttrain_compute(title + ' ' + source):
        if source in ROBOT_POSTTRAIN_PRIMARY and ROBOT_POSTTRAIN_GPU_HOURS.search(title):
            return '로봇 개발사 사후학습 GPU시간 실측 공개'
        return 'Funda AI 로봇 사후학습 GPU 자원 3~4배 추정'
    if _is_vnet_catl(title + ' ' + source):
        if title.startswith('정정:'):
            return title
        if (source in VNET_OFFICIAL and VNET_SODIUM.search(title) and VNET_ESS_QTY.search(title)
                and (VNET_ORDER.search(title) or re.search(r'\bnew\s+(?:supply|purchase)\s+contract\b', title, re.I))):
            return 'CATL–VNET 나트륨 ESS 공식 납품 계약 확인'
        return '9/21 공식 확인: CATL 관계사 연계 투자기구, VNET 지분 38.1% 취득'
    if _is_lfp_na_314_price(title + ' ' + source):
        return '314Ah LFP 북미 CIF 61.99달러…관세 40.9%는 별도 가정'
    if _is_optimus_hand_magnet(title + ' ' + source):
        return '머스크: Optimus 손 정밀·힘 제어 병목, 2025년 자석 제한 2~3개월 차질 회고'
    text = f'{title} {source}'
    if _is_humanoid_dram(text):
        if source in HUMANOID_DRAM_VENDOR_SOURCES and _humanoid_dram_oem_order(text):
            return f'{source}, 휴머노이드용 저전력 D램 로봇 고객 공급계약 공식 확인'
        return (
            '카운터포인트: 휴머노이드 D램 평균 19→39GB, '
            '전체 수요 8,300→172,000Tbit 전망'
        )
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
    if group == 'alert_quality_238':
        return '기존 알림 정정'
    if group == 'global_bess_commissioned':
        return '글로벌 계통용 BESS'
    if group == 'sdi_lfp_bbu':
        return '삼성SDI 서버 백업전원'
    if group == 'china_ess_us_exit_report':
        return '미국 ESS 공급망'
    if group == 'micron_eim_edge':
        return '마이크론 EIM 로봇 메모리'
    if group in ROBOT_OCT16_TITLES:
        return {
            'alert_quality_oct18':'Telegram 233 정정',
            'ess_outdoor_policy':'ESS 인허가·정책',
            'brils_us_localization':'브릴스 북미 AMR',
            'hyundai_robot_rx_team':'현대차 로봇 전략',
            'lge_robot_sw_platform':'LG 로봇 소프트웨어',
            'robotis_open_source_baseline':'로보티즈 기존 오픈소스',
            'robotis_hardware_release':'로보티즈 하드웨어 개방',
        }[group]
    if group in ROBOT_OCT15_TITLES:
        return {
            'agility_spac_2026': 'Agility IPO',
            'rainbow_fcc_compliance': 'RB-Y1 미국 규제',
            'xinjian_prs_ipo': '신젠전동 롤러스크루',
            'unichem_loomia_acquisition': '유니켐 로봇 전자피부',
            'atlas_protoops_build': 'Atlas 제조공정',
            'alert_quality_223': '알림 정정',
            'alert_quality_qty_224225': '수량 오탐 정정',
        }[group]
    if group == 'fluence_vattenfall_bess':
        return 'Fluence·Vattenfall ESS'
    if group == 'alert_quality_correction':
        return '오탐 정정'
    if group == 'catl_intilion_sodium':
        return 'CATL–INTILION 나트륨 ESS'
    if group == 'dexmate_lg_commercial':
        return 'Dexmate–LG CNS 로봇 사업'
    if group == ROBROS_PILOT_GROUP:
        return '로브로스 제조실증 규제특례'
    if group == 'robot_posttrain_compute':
        return '피지컬AI 학습 연산'
    if group == 'catl_vnet_infrastructure':
        return 'CATL–VNET 데이터센터 ESS'
    if group == 'lfp_314_cif_north_america':
        return '북미 ESS LFP 조달원가'
    if group == 'optimus_hand_magnet':
        return 'Optimus 손·자석 공급망'
    if group == 'humanoid_brain_dram':
        return '휴머노이드 메모리'
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
    if item.get('quality_correction_246'):
        return hashlib.sha256(b'physical-ai|telegram-246|catl-intilion|duplicate-correction').hexdigest()
    if _catl_intilion_oct20_reprint(item):
        return hashlib.sha256(b'catl-intilion|sodium|dach|20261009|3gwh-target|five-years').hexdigest()
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    # Multi-company media recaps of the SAME North American 30MWh sample
    # test plan may contain an unrelated later "mass production started"
    # verb. Canonicalize the unconfirmed LGES plan BEFORE nested supplier
    # wrappers compute news-dependent keys. A subsequent LGES primary
    # confirmed start or approval keeps its own upgraded event identity.
    title = item.get('title','')
    source = item.get('source') or ''
    if (topic_group(text) == 'sodium_ion_battery'
            and source not in {'LG에너지솔루션','LG Energy Solution'}
            and re.search(r'LG에너지솔루션|LG\s*Energy\s*Solution',text,re.I)
            and re.search(r'30\s*MWh',text,re.I)
            and re.search(r'소듐이온|나트륨이온|sodium[-\s]*ion',text,re.I)
            and re.search(r'ESS',text,re.I)
            and re.search(r'샘플|sample|테스트|test',text,re.I)
            and re.search(r'내년|2027|계획|예정|목표|추진',text,re.I)
            and not re.search(r'CATL|HyperStrong|SK온|삼성SDI',title,re.I)):
        return hashlib.sha256(
            b'sodium|lges|north-america|30mwh|sample-plan-2027h1'
        ).hexdigest()
    if topic_group(text) == 'alert_quality_238':
        return hashlib.sha256(
            b'robotis|telegram238|20261019|item1-stock-reaction-correction'
        ).hexdigest()
    if _is_bess_bmi_actual(text):
        period = _bess_bmi_period(text)
        if period == '2026-09':
            return hashlib.sha256(
                b'benchmark-mineral-intelligence|global-grid-bess|2026-09|20.4gwh|208gwh'
            ).hexdigest()
        # Date and the first reported GWh metric form the update identity;
        # repeated publication by a second media outlet shares the same key.
        qty = re.search(r'(d+(?:.d+)?)s*GWh',text,re.I)
        value = qty.group(1) if qty else 'unreported'
        return hashlib.sha256(
            f'benchmark-mineral-intelligence|global-grid-bess|{period}|{value}gwh'.encode()
        ).hexdigest()
    if _is_sdi_bbu_lfp(text):
        stage = _sdi_bbu_lfp_stage(text,item.get('source') or '')
        return hashlib.sha256(
            f'samsung-sdi|21700-lfp-bbu|{stage}|2026-2027'.encode()
        ).hexdigest()
    if _is_cn_ess_us_exit(text):
        stage=_cn_ess_us_exit_stage(text,item)
        if stage=='company_confirmed_us_exit':
            vendor=_cn_ess_official_vendor(item)
            return hashlib.sha256(
                f'china-ess|us-market|official-exit|{vendor}|2026'.encode()
            ).hexdigest()
        return hashlib.sha256(
            b'digitimes|chinese-bess-system-suppliers|anonymous-us-retreat|20261019|771701'
        ).hexdigest()
    if _is_micron_eim(text):
        stage = _micron_eim_stage(text,item)
        return hashlib.sha256(
            f'micron-eim|physical-ai|SEDEX-20261016|{stage}'.encode()
        ).hexdigest()
    _g16 = _oct16_group(text)
    if _g16:
        return _oct16_key(item,_g16,text)
    _g = _oct15_group(text)
    if _g in ROBOT_OCT15_TITLES:
        _stage_name = _oct15_stage(_g, text, item.get('source') or '')
        # Content-based stage ID suppresses news rewrites and differentiates
        # grant/closing from application or signed agreement stages.
        return hashlib.sha256(f'robot-oct15|{_g}|{_stage_name}|2026'.encode()).hexdigest()
    if topic_group(text) == 'fluence_vattenfall_bess':
        stage = _fluence_vattenfall_stage(text,item.get('source') or '')
        return hashlib.sha256(f'fluence-vattenfall|brunsbuettel-254mw-1gwh|{stage}|2026'.encode()).hexdigest()
    if topic_group(text) == 'sdi_oct08_broker_preview':
        return hashlib.sha256(b'sdi|dsresearch|20261008|q3-preview-q4-order-expectation-baseline').hexdigest()
    if topic_group(text) == 'alert_quality_correction':
        return hashlib.sha256(
            b'khs-physical-ai|telegram218|20261014|item1-stock-reaction-correction-v1'
        ).hexdigest()
    if topic_group(text) == 'catl_intilion_sodium':
        stage = _catl_intilion_stage(text,item.get('source') or '')
        if stage == 'sodium_3gwh_development_framework':
            return hashlib.sha256(b'catl-intilion|sodium|dach|20261009|3gwh-target|five-years').hexdigest()
        site = '-'.join(sorted(set(re.findall(
            r'(?:Jesow|Kappel|Mainz|Wiesbaden|(?:site|project)\s+[A-Z][a-z]+)',
            text,re.I
        )))) or 'undisclosed-site'
        return hashlib.sha256(f'catl-intilion|{stage}|{site}|2026'.encode()).hexdigest()
    if topic_group(text) == 'dexmate_lg_commercial':
        stage = _dexmate_lg_stage(text,item.get('source') or '')
        if stage == 'ceo_reported_use_distribution':
            return hashlib.sha256(b'dexmate-lgcns|tao-chen|20261013|lg-use-and-distribution').hexdigest()
        return hashlib.sha256(f'dexmate-lgcns|{stage}|2026'.encode()).hexdigest()
    if topic_group(text) == ROBROS_PILOT_GROUP:
        if item.get('robros_false_alert_correction'):
            return hashlib.sha256(
                b'robros|20261013|telegram213-214|false-alert-correction-v1'
            ).hexdigest()
        stage=_robros_pilot_stage(text,item.get('source') or '')
        if stage == 'approved_pilot_report':
            return hashlib.sha256(b'robros|sandbox-industrial|20261013|20units|4sites|approval').hexdigest()
        site='unknown'
        for canonical,pattern in (
            ('nepes',r'네패스|Nepes'),
            ('sungwoo',r'성우하이텍|Sungwoo'),
            ('samho',r'HD현대삼호|HD\s*Hyundai\s*Samho'),
            ('deliverylab',r'딜리버리랩|Delivery\s*Lab'),
        ):
            if re.search(pattern,text,re.I):
                site=canonical
                break
        stamp=(item.get('published') or '')[:10]
        numbers='-'.join(sorted(set(re.findall(r'\d+(?:\.\d+)?\s*(?:%|초|대|hours?|s)',text,re.I))))
        return hashlib.sha256(
            f'robros|industrial|{site}|{stage}|{stamp}|{numbers}'.encode()
        ).hexdigest()
    if topic_group(text) == 'robot_posttrain_compute':
        stage = _robot_posttrain_stage(text,item.get('source') or '')
        if stage != 'official_measured_posttraining':
            return hashlib.sha256(b'funda|robot-posttraining-3-4x|research-baseline').hexdigest()
        m = ROBOT_POSTTRAIN_GPU_HOURS.search(text)
        magnitude = re.sub(r'\s+','',m.group(0)) if m else 'unknown'
        pub = (item.get('published') or '')[:7]
        return hashlib.sha256(
            f'robot-posttrain-measured|{item.get("source")}|{magnitude}|{pub}'.encode()
        ).hexdigest()
    if topic_group(text) == 'catl_vnet_infrastructure':
        stage=_vnet_catl_stage(text,item.get('source') or '')
        if stage=='equity_closing_baseline_recovery' and item.get('correction_for_false_stock_alerts'):
            return hashlib.sha256(b'vnet|sept21-2026|secondary-equity-closing|correction-20261012-stock-articles-208').hexdigest()
        if stage=='equity_closing_baseline_recovery':
            return hashlib.sha256(b'vnet|PJ-Millennium|CATL-affiliate|20260921|38.1|650424192|SECONDARY').hexdigest()
        vals='|'.join(sorted(set(VNET_ESS_QTY.findall(text))))
        return hashlib.sha256(f'vnet|catl|{stage}|sodiumESS|{vals}'.encode()).hexdigest()
    if topic_group(text) == 'lfp_314_cif_north_america':
        return hashlib.sha256(
            b'Benchmark|LFP-314Ah|2026-09|CN-EXW-51.62|NA-CIF-61.99|EU-CIF-59.18'
        ).hexdigest()
    if topic_group(text) in {'battery_roadmap_2026_baseline','ev_to_ess_oversupply_baseline'}:
        return hashlib.sha256(
            f'old-battery-story|{topic_group(text)}|2026'.encode()
        ).hexdigest()
    if topic_group(text) == 'optimus_hand_magnet':
        stage = _optimus_hand_magnet_stage(text,item.get('source') or '')
        return hashlib.sha256(f'optimus|hand-magnet|xtakeover-20261010|{stage}'.encode()).hexdigest()
    if topic_group(text) == 'humanoid_brain_dram':
        stage = _humanoid_dram_stage(text, item.get('source') or '')
        if stage == 'confirmed_named_oem_order':
            # Canonicalize Korean/English company aliases to prevent double
            # alerts from identical vendor and buyer announcements.
            vendor = 'unknown'
            for canonical, pat in (
                ('samsung', r'삼성전자|Samsung\s*Electronics'),
                ('skhynix', r'SK\s*hynix|SK하이닉스'),
                ('micron', r'Micron(?:\s*Technology)?|마이크론'),
            ):
                if re.search(pat, text, re.I):
                    vendor = canonical
                    break
            buyer = 'unknown'
            for canonical, pat in (
                ('nvidia', r'NVIDIA|엔비디아'),
                ('tesla', r'Tesla|테슬라'),
                ('xpeng', r'XPENG|샤오펑'),
                ('boston', r'Boston\s*Dynamics|보스턴다이내믹스'),
                ('agility', r'Agility\s*Robotics'),
                ('unitree', r'Unitree|유니트리'),
                ('figure', r'Figure\s*AI|피겨'),
            ):
                if re.search(pat, text, re.I):
                    buyer = canonical
                    break
            product = 'jetson-thor' if re.search(r'Jetson\s*Thor|젯슨\s*토르',text,re.I) else 'other-robot'
            return hashlib.sha256(
                f'robot-lpddr-oem|{vendor}|{buyer}|{product}|confirmed-contract'.encode()
            ).hexdigest()
        if stage == 'initial_research_forecast':
            return hashlib.sha256(
                b'counterpoint|humanoid-brain-dram|2026-10-10|2026-19gb-8300tbit|2030-39gb-172000tbit'
            ).hexdigest()
        # Revised forecasts keep a new numeric signature but multiple media
        # copies of one change do not create fresh alerts.
        nums = '|'.join(sorted(set(re.findall(
            r'\d[\d,]*\s*(?:GB|Tbit|테라\s*비트)', text, re.I
        ))))
        return hashlib.sha256(f'counterpoint|humanoid-brain-dram|{stage}|{nums}'.encode()).hexdigest()
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
    correction246 = next((x for x in candidates if x.get('group') == 'alert_quality_246'), None)
    if correction246 and not any(x.get('key') == correction246.get('key') for x in chosen):
        chosen = ([correction246, *chosen] if len(chosen)<limit else [correction246, *chosen[:-1]])
    correction238 = next((x for x in candidates if x.get('group') == 'alert_quality_238'), None)
    if correction238 and not any(x.get('key') == correction238.get('key') for x in chosen):
        chosen = ([correction238,*chosen] if len(chosen)<limit else [correction238,*chosen[:-1]])
    # Preserve a separately verified monthly global installation metric
    # even when generic old ESS stories are numerous.
    bess_actual = next((x for x in candidates if x.get('group') == 'global_bess_commissioned'), None)
    if bess_actual and not any(x.get('key') == bess_actual.get('key') for x in chosen):
        chosen = ([bess_actual,*chosen] if len(chosen)<limit else [bess_actual,*chosen[:-1]])
    # Show distinct new status changes but do not resurrect known repeats.
    for _new_group in ('china_ess_us_exit_report','alert_quality_oct18','lge_robot_sw_platform','hyundai_robot_rx_team',
                       'brils_us_localization','ess_outdoor_policy',
                       'robotis_hardware_release'):
        _hit=next((x for x in candidates if x.get('group')==_new_group),None)
        if _hit and not any(x.get('key')==_hit.get('key') for x in chosen):
            chosen=[_hit,*chosen][:limit]
    # Promote verifiable milestones over low-quality general market articles;
    # do not resend any event key already in the persisted dedup state.
    for _group in (
        'micron_eim_edge',
        'atlas_protoops_build',
        'xinjian_prs_ipo',
        'rainbow_fcc_compliance',
        'unichem_loomia_acquisition',
        'agility_spac_2026',
        'alert_quality_223',
        'alert_quality_qty_224225',
    ):
        _candidate = next((x for x in candidates if x.get('group') == _group), None)
        if _candidate and not any(x.get('key') == _candidate.get('key') for x in chosen):
            chosen = [_candidate] + chosen
            chosen = chosen[:limit]
    fluence_contract = next((x for x in candidates if x.get('group') == 'fluence_vattenfall_bess'),None)
    if fluence_contract and not any(x.get('key')==fluence_contract.get('key') for x in chosen):
        chosen = ([fluence_contract,*chosen] if len(chosen)<limit else [fluence_contract,*chosen[:-1]])
    correction = next((x for x in candidates if x.get('group')=='alert_quality_correction'),None)
    if correction and not any(x.get('key')==correction.get('key') for x in chosen):
        chosen = ([correction,*chosen] if len(chosen)<limit else [correction,*chosen[:-1]])
    for target_group in ('catl_intilion_sodium','dexmate_lg_commercial'):
        event = next((x for x in candidates if x.get('group')==target_group),None)
        if event and not any(x.get('key')==event.get('key') for x in chosen):
            chosen = ([event,*chosen] if len(chosen)<limit else [event,*chosen[:-1]])
    industrial_pilot=next((x for x in candidates if x.get('group')==ROBROS_PILOT_GROUP),None)
    if industrial_pilot and not any(x.get('key')==industrial_pilot.get('key') for x in chosen):
        chosen=([industrial_pilot,*chosen] if len(chosen)<limit else [industrial_pilot,*chosen[:-1]])
    vnet=next((x for x in candidates if x.get('group')=='catl_vnet_infrastructure'),None)
    if vnet and not any(x.get('key')==vnet.get('key') for x in chosen):
        chosen=([vnet,*chosen] if len(chosen)<limit else [vnet,*chosen[:-1]])
    price_update = next((x for x in candidates if x.get('group') == 'lfp_314_cif_north_america'),None)
    if price_update and not any(x.get('key') == price_update.get('key') for x in chosen):
        chosen = ([price_update,*chosen] if len(chosen)<limit else [price_update,*chosen[:-1]])
    hand_magnet = next((x for x in candidates if x.get('group') == 'optimus_hand_magnet'),None)
    if hand_magnet and not any(x.get('key') == hand_magnet.get('key') for x in chosen):
        chosen = ([hand_magnet,*chosen] if len(chosen)<limit else [hand_magnet,*chosen[:-1]])
    brain_memory = next((x for x in candidates if x.get('group') == 'humanoid_brain_dram'), None)
    if brain_memory and not any(x.get('key') == brain_memory.get('key') for x in chosen):
        chosen = (
            [brain_memory, *chosen] if len(chosen) < limit else [brain_memory, *chosen[:-1]]
        )
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



# OpenAI CEO September 2026 first-person interview and official hardware R&D.
# Reporting appeared again on 2026-10-19, but the statement itself is not a
# new 10/19 corporate press release nor a 2027 product-launch commitment.
# Keep CEO goal, verified completed demonstration and paid customer contract
# as separate evidence stages. Roadster -> Optimus supplier inference is noise.
OPENAI_HUMANOID_RECOVERY = 'DIRECT_OPENAI_HUMANOID_FORTUNE_20260915_2027_DEMO_GOAL'
OPENAI_HUMANOID_FORTUNE_URL = (
    'https://www.fortune.com/2026/09/15/sam-altman-openai-ai-safety-pause-trump-xi/'
)
OPENAI_HUMANOID_NAME = re.compile(r'\bOpenAI\b|오픈\s*AI', re.I)
OPENAI_HUMANOID_KIND = re.compile(r'휴머노이드|humanoid|robotics?|로보틱스|로봇', re.I)
OPENAI_HUMANOID_FUTURE = re.compile(
    r'\b2027\b|시연|실물|demo|prototype|액추에이터|actuator|motor|'
    r'자체\s*개발|building|build|채용|hiring|'
    r'정식\s*(?:공급|구매|판매)\s*계약|유상\s*계약|'
    r'signed|supply\s+contract|customer\s+contract|'
    r'deliver(?:ies|ed)?|출하|납품|commercial\s+launch', re.I
)
OPENAI_HUMANOID_COMPLETED = re.compile(
    r'실물\s*시연\s*(?:완료|공개|실시)|'
    r'(?:humanoid|robot).{0,95}(?:demo(?:nstration)?\s+(?:completed|shown|unveiled)|'
    r'live\s+demonstration\s+(?:completed|shown))|'
    r'(?:publicly\s+demonstrated|unveiled)\s+(?:its\s+)?(?:own\s+)?humanoid',
    re.I,
)
OPENAI_HUMANOID_DELIVERY_CONTRACT = re.compile(
    r'(?:휴머노이드|humanoid).{0,120}'
    r'(?:정식\s*(?:납품|공급|판매)\s*계약\s*체결|유료\s*고객\s*계약\s*체결)|'
    r'(?:signed\s+(?:paid|commercial)\s+(?:robot\s+)?(?:supply|customer)\s+(?:contract|agreement))',
    re.I,
)
OPENAI_HUMANOID_UNFINISHED = re.compile(
    r'예정|계획|목표|전망|검토|논의|기대|'
    r'not\s+yet|expected|plan(?:ned|s)?|aim(?:s|ed)?|forecast|could',
    re.I,
)
OPENAI_HUMANOID_ROADSTER = re.compile(
    r'로드스터|\bRoadster\b|비행\s*자동차|flying\s*(?:car|roadster)', re.I
)
OPENAI_HUMANOID_ROADSTER_THEME = re.compile(
    r'Optimus|옵티머스|로봇\s*공급망|robot(?:ics)?\s*supply\s*chain', re.I
)


def _is_openai_own_humanoid(text: str) -> bool:
    return bool(OPENAI_HUMANOID_NAME.search(text)
                and OPENAI_HUMANOID_KIND.search(text)
                and OPENAI_HUMANOID_FUTURE.search(text))


def _openai_own_humanoid_stage(item: dict) -> str:
    text = f"{item.get('title', '')} {item.get('description', '')}"
    source = item.get('source') or ''
    if not _is_openai_own_humanoid(text):
        return 'background'
    if source in {'OpenAI', 'OpenAI 공식'}:
        if OPENAI_HUMANOID_DELIVERY_CONTRACT.search(text) and not OPENAI_HUMANOID_UNFINISHED.search(text):
            return 'official_paid_contract'
        if OPENAI_HUMANOID_COMPLETED.search(text) and not OPENAI_HUMANOID_UNFINISHED.search(text):
            return 'official_completed_demo'
    if source in {'Fortune', 'Fortune Magazine'}:
        # The September first-person interview is the evidence, not a
        # second-hand "official corporate 2027 launch" claim.
        if (re.search(r'2027', text)
                and re.search(r'cool\s+demo|great\s+demo|멋진\s*시연|인상적인\s*시연', text,re.I)
                and re.search(r'we\s+will\s+definitely\s+do\s+a\s+humanoid|'
                              r'휴머노이드.{0,45}(?:직접\s*)?(?:만들|개발)|'
                              r'humanoid', text,re.I)):
            return 'ceo_2027_demo_goal'
    return 'background'


def _openai_humanoid_recovery() -> list[dict]:
    # One-time retrospective alert, labelled September statement and October
    # rediscovery. Never fabricate a Sept 15 intraday announcement timestamp.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 23):
        return []
    return [{
        'title': 'OpenAI 자체 휴머노이드 개발·2027년 시연 목표, 9월 CEO 인터뷰 재확인',
        'link': OPENAI_HUMANOID_FORTUNE_URL,
        'description': (
            '2026-09-01 Sources 팟캐스트에서 CEO Sam Altman이 '
            'we will definitely do a humanoid 라고 자체 개발 계획을 밝혔고, '
            '2026-09-15 Fortune 인터뷰에서 이를 재확인하면서 2027년에 '
            'cool demo 또는 great demo를 보여줄 수 있을 것으로 '
            '기대한다고 설명했다. 이는 2026-10-19 회사 신규 보도자료가 아닌 '
            '기존 인터뷰의 재보도이며, 2027년 정식 출시·양산·판매 약속이 아니다. '
            '공공장소에 로봇이 널리 다니기까지는 몇 년 더 걸릴 수 있다고 밝혔다. '
            'OpenAI 공식 채용공고에는 로봇용 맞춤 액추에이터·모터·감속기, '
            '시험동력계와 정밀 검사, 하드웨어 시제품 조립, 실시간 동작 제어, '
            '권선·철심 적층·절연·수지 충전 공정 등 자체 연구개발과 생산 준비 과제가 존재한다. '
            '하지만 로봇 형상·2027년 데모 내용·현장 검증 대수·설비투자액·'
            '고객 납품 계약·매출과 최종 상용화 일정은 공개되지 않았다. '
            '과거 Dactyl 로봇손 연구는 실제 기존 연구 사례이며 신규 로봇 '
            '양산 실적과 다르다. 기존 Figure 등 투자·협력도 자체 로봇 출하와 구분한다.'
        ),
        'source': 'Fortune',
        'published': None,
        'direct_recovery': True,
        'openai_ceo_interview_baseline': True,
    }]


_openai_prev_query_news = base.query_news
_openai_prev_topic_group = base.topic_group
_openai_prev_score = base.score
_openai_prev_category = base.category
_openai_prev_meaning = base.meaning
_openai_prev_risk = base.risk
_openai_prev_verification = base.verification
_openai_prev_clean_title = base.clean_title
_openai_prev_tag_for = base.tag_for
_openai_prev_key = base.key
_openai_prev_select_diverse = base.select_diverse


def _openai_query_news(q: str) -> list[dict]:
    if q == OPENAI_HUMANOID_RECOVERY:
        return _openai_humanoid_recovery()
    return _openai_prev_query_news(q)


base.query_news = _openai_query_news
if OPENAI_HUMANOID_RECOVERY not in base.QUERIES:
    base.QUERIES.append(OPENAI_HUMANOID_RECOVERY)
for _openai_search in (
    '(OpenAI OR 오픈AI) (humanoid OR 휴머노이드 OR robotics) '
    '(Sam Altman OR 올트먼 OR "robot demo" OR 2027) '
    '(demonstration OR 시연 OR 출시 OR 계획 OR 완료 OR 연기)',
    '(OpenAI OR 오픈AI) (휴머노이드 OR humanoid) '
    '(실제 시연 OR demo complete OR 정식 판매 OR 고객 계약 OR 출하 OR 양산)',
):
    if _openai_search not in base.QUERIES:
        base.QUERIES.append(_openai_search)


def _openai_topic_group(text: str) -> str | None:
    if _is_openai_own_humanoid(text):
        return 'openai_own_humanoid'
    return _openai_prev_topic_group(text)


def _openai_score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')}"
    source = item.get('source') or ''
    # Do not convert Roadster showmanship into an Optimus supplier milestone.
    if (OPENAI_HUMANOID_ROADSTER.search(text)
            and OPENAI_HUMANOID_ROADSTER_THEME.search(text)
            and source not in {'Tesla', 'Tesla Official'}):
        if not re.search(r'(?:Optimus|옵티머스).{0,55}(?:정식\s*계약\s*체결|'
                         r'signed\s+supply\s+contract)',text,re.I):
            return 0
    if _is_openai_own_humanoid(text):
        stage = _openai_own_humanoid_stage(item)
        return {
            'ceo_2027_demo_goal': 47,
            'official_completed_demo': 66,
            'official_paid_contract': 70,
        }.get(stage, 0)
    return _openai_prev_score(item)


def _openai_category(text: str, group: str) -> str:
    if group == 'openai_own_humanoid':
        # Base Telegram renderer only passes (title + description), not source.
        if OPENAI_HUMANOID_DELIVERY_CONTRACT.search(text) and not OPENAI_HUMANOID_UNFINISHED.search(text):
            return 'OpenAI 휴머노이드 · 실제 고객 유상계약 공식 확인'
        if OPENAI_HUMANOID_COMPLETED.search(text) and not OPENAI_HUMANOID_UNFINISHED.search(text):
            return 'OpenAI 휴머노이드 · 실물 시연 완료 공식 확인'
        return 'OpenAI 휴머노이드 · 2027년 시연 목표 CEO 인터뷰'
    return _openai_prev_category(text, group)


def _openai_meaning(cat: str) -> str:
    if cat == 'OpenAI 휴머노이드 · 2027년 시연 목표 CEO 인터뷰':
        return (
            'Sam Altman은 9/1 Sources에서 자체 휴머노이드 개발을 밝혔고, '
            '9/15 Fortune 인터뷰에서 이를 재확인하며 '
            '2027년 인상적인 시연 가능성을 언급했습니다. 10/19 보도는 새 '
            'CEO 발표가 아닌 과거 인터뷰 재소개입니다. 실제 OpenAI 채용공고에서 '
            '모터·액추에이터 자체 설계, 시제품 제작, 제조·시험설비 인력 채용이 '
            '확인돼 연구개발이 소프트웨어에서 하드웨어로 확장되는 신호입니다. '
            '그러나 로봇 완성품 데모·상용 출시·구매고객·매출·설비투자 금액은 '
            '확정되지 않았습니다.'
        )
    if cat == 'OpenAI 휴머노이드 · 실물 시연 완료 공식 확인':
        return (
            '회사 공식 영상·제품·시연 자료로 실제 기체의 작업 능력이 확인된 '
            '단계입니다. 원격조종·안전요원 유무, 처음 보는 작업 성공률, '
            '반복 시험시간, 손 조작·전력·가동률, 시연 일자를 구분합니다. '
            '시연은 양산·고객 매출과 별개입니다.'
        )
    if cat == 'OpenAI 휴머노이드 · 실제 고객 유상계약 공식 확인':
        return (
            '연구개발·시연과 달리 로봇 실제 고객의 정식 구매·납품 계약이 '
            '공식 확인된 단계입니다. 고객 실명, 물량×단가 원화 매출, '
            '설치·검수·유지보수·원격관제의 후속 매출을 분리합니다.'
        )
    return _openai_prev_meaning(cat)


def _openai_risk(cat: str) -> str:
    if cat.startswith('OpenAI 휴머노이드 · '):
        return (
            '2027년은 목표 시연 시점이지 출시 확정일이 아닙니다. '
            '6~24개월의 가장 현실적인 실패 경로는 고토크 액추에이터의 '
            '발열·감속기 마모·손 제어 오차, 실물 학습데이터 부족, '
            '자율작업 신뢰성·안전 검증과 공급업체 검사수율이 동시에 '
            '지연되는 경우입니다. 먼저 볼 지표는 원격지원 개입률·'
            '반복 작업 성공률·가동률·교체부품 비용·2027년 시연 '
            '목표 변경입니다. 아직 로봇 양산 수량이나 판매가격이 없습니다.'
        )
    return _openai_prev_risk(cat)


def _openai_verification(item: dict, group: str, text: str) -> str:
    if group == 'openai_own_humanoid':
        stage = _openai_own_humanoid_stage(item)
        if stage == 'ceo_2027_demo_goal':
            return (
                '2026-09-01 Sources CEO 직접 발언·9/15 Fortune 재확인·OpenAI 공식 '
                '액추에이터 제조·제어·실험 채용공고 교차확인 · '
                '2027년 시연 목표, 양산·고객 계약 미확인'
            )
        if stage in {'official_completed_demo','official_paid_contract'}:
            return 'OpenAI 1차자료 단계 · 원격조종·실제 계약·고객·매출 별도 검증'
        return '채용·개발 보도 단계 · 완성 로봇 판매·시연 완료 미확인'
    return _openai_prev_verification(item, group, text)


def _openai_clean_title(title: str, source: str) -> str:
    if _is_openai_own_humanoid(f'{title} {source}'):
        if source in {'Fortune','Fortune Magazine'}:
            return 'OpenAI 자체 휴머노이드 개발·2027년 시연 목표, 9월 CEO 인터뷰 재확인'
    return _openai_prev_clean_title(title, source)


def _openai_tag_for(group: str) -> str:
    if group == 'openai_own_humanoid':
        return 'OpenAI 자체 휴머노이드'
    return _openai_prev_tag_for(group)


def _openai_key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')}"
    if _is_openai_own_humanoid(text):
        stage = _openai_own_humanoid_stage(item)
        return hashlib.sha256(
            f'openai|own-humanoid|{stage}|'
            f'{"Fortune-2026-09-15" if stage == "ceo_2027_demo_goal" else "future-official-stage"}'.encode()
        ).hexdigest()
    return _openai_prev_key(item)


def _openai_select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _openai_prev_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    hit = next((x for x in candidates
                if x.get('group') == 'openai_own_humanoid' and x.get('score',0)>=11),None)
    if hit and not any(x.get('key') == hit.get('key') for x in chosen):
        chosen = ([hit,*chosen] if len(chosen)<limit else [hit,*chosen[:-1]])
    return chosen


base.topic_group = _openai_topic_group
base.score = _openai_score
base.category = _openai_category
base.meaning = _openai_meaning
base.risk = _openai_risk
base.verification = _openai_verification
base.clean_title = _openai_clean_title
base.tag_for = _openai_tag_for
base.key = _openai_key
base.select_diverse = _openai_select_diverse


_FINAL_STOCK_ONLY_NEWS = re.compile(
    r'(?:배터리주|2차전지주|증시\s*주인공|마켓트래커|주가\s*장중|ETF\s*급등)'
    r'.{0,110}(?:들썩|강세|급등|상승|주인공|반등)|'
    r'(?:증시\s*주인공|마켓트래커).{0,110}(?:배터리주|2차전지주|강세)|'
    r'백조세탁기부터.{0,100}(?:혁신\s*영상|타임스스퀘어)',
    re.I,
)
_FINAL_SUBSTANTIVE_CHANGE = re.compile(
    r'계약\s*체결|고객\s*승인|양산\s*(?:개시|시작)|첫\s*출하|'
    r'실제\s*가동|납품\s*계약|투자\s*집행|양산\s*시작|'
    r'(?:signed|executed)\s+(?:supply|purchase)\s+contract',
    re.I,
)


def _correct_jpm_sri_krw_at_source_rate(text: str) -> str:
    """Keep ONE dated verified rate for this historical JPM milestone.

    A live currency postprocessor may have an older ECB *daily* quote than
    the 2026-10-19 19:05 KST 1,330.33 KRW rate verified for this report.
    Ensure every relevant amount is already paired before that later guard.
    Do not change amounts or FX on unrelated current news.
    """
    pieces = text.split('──────────────────')
    fixed=[]
    values={
        '1조5,000억달러':'약 1,995조4,950억원',
        '2,300억달러':'약 305조9,759억원',
        '100억달러':'약 13조3,033억원',
        '50억달러':'약 6조6,517억원',
        '5억달러':'약 6,652억원',
    }
    for piece in pieces:
        if not ('JP모건 SRI' in piece or 'JP모건 전략적 투자' in piece):
            fixed.append(piece)
            continue
        for usd,won in values.items():
            # Do not append a second conversion to correctly paired text.
            piece = re.sub(
                re.escape(usd)+r'(?!\s*\([^)]*원\))',
                lambda m, u=usd, w=won: f'{u}({w})',
                piece,
            )
        fixed.append(piece)
    return '──────────────────'.join(fixed)


def _drop_stock_price_sections(text: str) -> str:
    """Last-mile defense: strip stock-only headlines before Telegram sends.

    This protects against legacy-score wrappers and future wording variants.
    Preserve legitimate article blocks, renumber them, update the count.
    If none remain, emit an empty message rather than a false alert.
    """
    if '<b>신규 고신호 ' not in text or '━━━━━━━━━━━━━━━━━━' not in text:
        return text
    head, tail = text.split('━━━━━━━━━━━━━━━━━━', 1)
    sections = tail.split('──────────────────')
    title_rx = re.compile(r'(?m)^\s*<b>\s*\d+\.\s*([^<\n]+)</b>')
    kept = []
    removed = 0
    for section in sections:
        m = title_rx.search(section)
        if m:
            title = m.group(1)
            if (not re.search(r'정정|오탐', title)
                    and (
                        _is_stock_reaction_only(
                            {'title': title, 'source': '비공식 언론'}
                        )
                        or (_FINAL_STOCK_ONLY_NEWS.search(title)
                            and not _FINAL_SUBSTANTIVE_CHANGE.search(title))
                    )):
                print('Final Telegram stock-only/marketing headline excluded:', title)
                removed += 1
                continue
        kept.append(section)
    if not removed:
        return text
    count = sum(bool(title_rx.search(x)) for x in kept)
    if count == 0:
        return ''
    head = re.sub(
        r'(<b>신규 고신호 )\d+(건</b>)',
        lambda m: f'{m.group(1)}{count}{m.group(2)}',
        head,
        count=1,
    )
    new_body = '──────────────────'.join(kept)
    counter = [0]

    def renumber(m: re.Match) -> str:
        counter[0] += 1
        return f'{m.group(1)}{counter[0]}{m.group(2)}'

    new_body = re.sub(
        r'(?m)^(\s*<b>)\d+(\.\s+)',
        renumber,
        new_body,
    )
    if counter[0] != count:
        raise RuntimeError('Telegram alert count mismatch after stock-filter')
    return head + '━━━━━━━━━━━━━━━━━━' + new_body


def _finalize_airan_criteria() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    text = _drop_stock_price_sections(text)
    if not text:
        base.ALERT_PATH.write_text('', encoding='utf-8')
        return
    text = _correct_jpm_sri_krw_at_source_rate(text)
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


# BMW Gen6 Shenyang battery-PACK assembly SOP and JPMorgan SRI cumulative
# deployment. Both are evidence-graded milestones within the existing watcher.
# IMPORTANT: BMW assembles externally sourced cylindrical CELLS into PACKS;
# a pack SOP is not an announcement that BMW makes the battery cells itself.
# SRI $5bn was ALREADY DEPLOYED under a 2025 $10bn equity envelope; it is
# not a new $5bn national-defense appropriation or a robot-factory contract.
BMW_GEN6_PACK_RECOVERY = 'DIRECT_BMW_SHENYANG_GEN6_PACK_SOP_20261015'
BMW_GEN6_PACK_URL = (
    'https://www.press.bmwgroup.com/global/article/detail/'
    'T0461769EN/bmw-group-begins-series-production-of-gen6-high-voltage-batteries-in-shenyang'
)
JPM_SRI_DEPLOYMENT_RECOVERY = 'DIRECT_JPM_SRI_5BN_DEPLOYED_230BN_FACILITATED_20261019'

# One correction to prior sent alerts 240/241. This is OUR arithmetic
# correction, not another event or a JPMorganChase press release.
JPM_SRI_FX_CORRECTION_RECOVERY = 'DIRECT_JPM_SRI_20261019_KRW_SINGLE_BASIS_CORRECTION'

JPM_SRI_PROGRESS_URL = (
    'https://www.marketscreener.com/news/'
    'one-year-in-jpmorganchase-s-security-and-resiliency-initiative-is-helping-to-strengthen-industries-ce785cdbd888f024'
)
BMW_GEN6_PRIMARY = {'BMW Group','BMW Group Official','BMW'}
JPM_SRI_PRIMARY = {'JPMorganChase', 'JPMorgan Chase', 'Reuters'}
BMW_GEN6_ID = re.compile(r'\bBMW\b|宝马|비엠더블유',re.I)
BMW_GEN6_PROD = re.compile(r'Gen\s*6|Gen6|6\s*세대|第六代',re.I)
BMW_GEN6_LOC = re.compile(r'Shenyang|선양|沈阳',re.I)
BMW_GEN6_BAT = re.compile(r'high[-\s]*voltage\s*batter|배터리|battery|电池',re.I)
BMW_GEN6_SOP = re.compile(
    r'(?:began|begun|starts?|started|commenced)\s+(?:series|mass)\s+production|'
    r'series\s+production\s+(?:has\s+)?(?:started|begun)|'
    r'양산\s*(?:을\s*)?(?:공식\s*)?(?:개시|시작|돌입)|正式量产|量产下线',
    re.I,
)
BMW_GEN6_DELIVERY = re.compile(
    r'(?:China|중국|中国).{0,90}(?:Neue\s*Klasse|iX3|i3).{0,90}'
    r'(?:actual|first)\s+(?:customer\s+)?deliveries|'
    r'중국.{0,90}(?:Neue\s*Klasse|iX3|i3).{0,90}고객\s*인도\s*(?:완료|시작)',
    re.I,
)
JPM_SRI_ID = re.compile(r'JPMorgan\s*Chase|JPMorganChase|JP\s*모건|제이피모건',re.I)
JPM_SRI_NAME = re.compile(r'SRI\b|Security\s+and\s+Resilien|안보.{0,15}회복력|경제안보\s*회복력',re.I)
JPM_SRI_EQUITY = re.compile(
    r'(?:\$?\s*5\s*billion|50\s*억\s*달러).{0,125}'
    r'(?:deployed|invested|집행|투자\s*완료)|'
    r'(?:deployed|invested|누적\s*집행).{0,125}(?:\$?\s*5\s*billion|50\s*억\s*달러)',
    re.I,
)
JPM_SRI_FINANCED = re.compile(r'\$?\s*230\s*billion|2[, ]?300\s*억\s*달러|2,300억달러',re.I)
JPM_SRI_PLAN_ONLY = re.compile(
    r'(?:plans?\s+to\s+invest|will\s+invest|could\s+invest|'
    r'투자\s*(?:계획|검토|예정)|집행\s*목표)',
    re.I,
)


def _is_bmw_gen6_pack(text: str) -> bool:
    return bool(BMW_GEN6_ID.search(text) and BMW_GEN6_PROD.search(text)
                and BMW_GEN6_LOC.search(text) and BMW_GEN6_BAT.search(text))


def _bmw_gen6_pack_stage(text: str, source: str='') -> str:
    if not _is_bmw_gen6_pack(text): return ''
    if source not in BMW_GEN6_PRIMARY: return 'unverified'
    if BMW_GEN6_DELIVERY.search(text): return 'actual_china_vehicle_delivery'
    if BMW_GEN6_SOP.search(text): return 'shenyang_pack_sop'
    return 'prior_plan'


def _bmw_gen6_pack_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,26): return []
    return [{
        'title': 'BMW Gen6 선양 46mm 원통형 셀 기반 고전압 배터리팩 양산 공식 개시',
        'link': BMW_GEN6_PACK_URL,
        'description': (
            '2026-10-15 BMW Group 공식 보도자료: BMW가 중국 선양 Shenyang '
            '파워트레인 공장에서 Gen6 고전압 배터리팩의 실제 양산을 시작했다. '
            '이 거점은 헝가리 Debrecen, 독일 Irlbach-Straßkirchen 뒤 '
            '세 번째 생산거점이다. BMW가 원통형 배터리 셀 자체를 '
            '생산한다는 발표가 아니다. 외부에서 입고되는 셀을 '
            '전수 수입검사하고 냉각 유닛과 클러스터로 조립한 다음 '
            '레이저 세정·고정밀 용접·실시간 용접검사·발포 결합·'
            '밀봉·리벳·Energy Master 제어기 설치·배터리팩 최종검사를 거친다. '
            'Gen6 원통형 셀은 BMW가 밝힌 기존 세대 대비 에너지 밀도 20% 이상 증가, '
            '충전속도·주행거리 최대 30% 개선 사양이다. '
            'CATL과 BMW의 2022-09-09 46mm 원통형 셀 공급 기본계약은 '
            '중국·유럽 두 공장 각각 최대 연산 20GWh였으나 '
            '이번 선양 팩라인 특정 셀 공급사 실명과 출하 셀 수·GWh·'
            'BMW 배터리팩 원화 매출은 이번 보도만으로 직접 확정되지 않는다. '
            '미국 Woodruff·멕시코 San Luis Potosí 조립라인의 양산은 '
            '앞으로 수개월 내 개시 예정이며 이미 생산 중이라는 뜻이 아니다. '
            '배터리팩 생산과 현지 Neue Klasse 차종의 첫 고객 인도는 별개이다.'
        ),
        'source': 'BMW Group',
        'published': None,
        'direct_recovery': True,
        'bmw_pack_sop_fact': True,
    }]


def _is_jpm_sri(text: str) -> bool:
    return bool(JPM_SRI_ID.search(text) and JPM_SRI_NAME.search(text))


def _jpm_sri_stage(text: str, source: str='') -> str:
    if not _is_jpm_sri(text): return ''
    if source not in JPM_SRI_PRIMARY: return 'unverified'
    if JPM_SRI_EQUITY.search(text) and JPM_SRI_FINANCED.search(text):
        return 'first_year_equity_deployed'
    return 'prior_envelope'


def _jpm_sri_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,26): return []
    return [{
        'title': 'JPMorganChase 안보·공급망 SRI 1년차 지분투자 50억달러 누적 집행',
        'link': JPM_SRI_PROGRESS_URL,
        'description': (
            '2026-10-19 JPMorganChase 발행 Business Wire 1주년 성과 자료와 '
            'Reuters 보도: SRI(Security and Resiliency Initiative)의 '
            '전략적 투자그룹이 기존 계획 100억달러 중 50억달러를 '
            '지분투자로 이미 누적 집행했다. 추가 50억달러 신규 투자 결정이 아니다. '
            '금융지원·주선 실적 약 2,300억달러는 50억달러 지분투자와 '
            '성격과 집계가 다르므로 단순 합산하지 않는다. '
            '2025년 최초 SRI 장기 금융지원 계획은 10년간 '
            '총 1조5,000억달러이며 이 자금 전체가 정부 예산도 '
            'JP모건 직접 자기자본 투자도 아니다. '
            '지분투자 분야는 방산과 초음속 미사일만이 아니라 '
            '로봇·자율제조·분산형 배터리저장·첨단제조·핵심광물·에너지 등이다. '
            '약 10개 기업 투자·건당 약 5억달러는 Todd Combs의 '
            '기존 발표에 근거한 평균값이며 로봇 회사 10곳 '
            '각각에 대한 고정액 투자가 아니다. '
            '환율 기준 2026-10-19 19:05 KST 1달러=1,330.33원: '
            '50억달러(약 6조6,517억원), 100억달러(약 13조3,033억원), '
            '2,300억달러(약 305조9,759억원), '
            '1조5,000억달러(약 1,995조4,950억원). '
            '투자수혜 기업별 자금수령·계약금액·일시·로봇공장 건설 '
            '또는 미사일 생산라인 발주는 이 집계만으로 확인되지 않는다.'
        ),
        'source': 'JPMorganChase',
        'published': None,
        'direct_recovery': True,
        'sri_first_year_progress': True,
    }]



def _jpm_sri_fx_correction_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,23): return []
    return [{
        'title': '정정: JPMorganChase SRI 누적 지분투자 50억달러 원화 환산기준 일치',
        'link': JPM_SRI_PROGRESS_URL,
        'description': (
            '앞서 전송된 BMW·JP모건 통합 알림 message_id 240/241 중 '
            'JP모건 항목 일부가 다른 환율의 원화 환산액을 중복 표기한 오류를 바로잡는다. '
            '2026-10-19 19:05 KST 검증 환율 1달러=1,330.33원 단일 적용: '
            '누적 지분투자 50억달러(약 6조6,517억원), '
            '전체 예정 지분투자 100억달러(약 13조3,033억원), '
            '대출·금융지원·주선 실적 2,300억달러(약 305조9,759억원), '
            '10년 장기 금융지원 구상 1조5,000억달러(약 1,995조4,950억원). '
            '이 숫자들은 2026년 신규 예산이나 방산·로봇 공장의 수주 실적이 아니며 '
            '금융주선액·실제 지분투자액을 합산해서는 안 된다. '
            '50억달러는 이미 집행됐다는 JPMorganChase 2026-10-19 첫해 '
            '업무성과 발표를 유지하며 새로운 자금 집행 사건은 아니다.'
        ),
        'source': '원화 계산 정정',
        'published': None,
        'direct_recovery': True,
        'jpm_fx_correction': True,
    }]


_bmw_jpm_prev_query = base.query_news
_bmw_jpm_prev_group = base.topic_group
_bmw_jpm_prev_score = base.score
_bmw_jpm_prev_category = base.category
_bmw_jpm_prev_meaning = base.meaning
_bmw_jpm_prev_risk = base.risk
_bmw_jpm_prev_verify = base.verification
_bmw_jpm_prev_title = base.clean_title
_bmw_jpm_prev_tag = base.tag_for
_bmw_jpm_prev_key = base.key
_bmw_jpm_prev_select = base.select_diverse


def _bmw_jpm_query(q: str) -> list[dict]:
    if q == BMW_GEN6_PACK_RECOVERY: return _bmw_gen6_pack_recovery()
    if q == JPM_SRI_DEPLOYMENT_RECOVERY: return _jpm_sri_recovery()
    if q == JPM_SRI_FX_CORRECTION_RECOVERY: return _jpm_sri_fx_correction_recovery()
    return _bmw_jpm_prev_query(q)


def _bmw_jpm_group(text: str) -> str | None:
    if _is_bmw_gen6_pack(text): return 'bmw_gen6_pack'
    if _is_jpm_sri(text): return 'jpm_sri_2026'
    return _bmw_jpm_prev_group(text)


def _bmw_jpm_score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')}"
    g = _bmw_jpm_group(text)
    if g == 'bmw_gen6_pack':
        return {'shenyang_pack_sop':52,'actual_china_vehicle_delivery':60}.get(
            _bmw_gen6_pack_stage(text,item.get('source') or ''),0)
    if g == 'jpm_sri_2026':
        if item.get('jpm_fx_correction'): return 75
        return {'first_year_equity_deployed':48}.get(
            _jpm_sri_stage(text,item.get('source') or ''),0)
    return _bmw_jpm_prev_score(item)


def _bmw_jpm_category(text: str, group: str) -> str:
    if group == 'bmw_gen6_pack':
        if BMW_GEN6_DELIVERY.search(text):
            return 'BMW Gen6 · 중국 신세대 전기차 실제 고객 인도'
        return 'BMW Gen6 · 선양 배터리팩 양산 공식 개시'
    if group == 'jpm_sri_2026':
        if '정정:' in text and re.search(r'환산|환율',text):
            return 'JP모건 SRI · 환율 표기 정정(기존 알림)'
        return 'JP모건 SRI · 50억달러 지분투자 누적 집행'
    return _bmw_jpm_prev_category(text,group)


def _bmw_jpm_meaning(cat: str) -> str:
    if cat == 'JP모건 SRI · 환율 표기 정정(기존 알림)':
        return (
            '기존 JPMorganChase 지분투자 알림에서 환율 시점이 혼재한 '
            '원화 표기를 정정합니다. 2026-10-19 19:05 KST '
            '1달러=1,330.33원 단일 기준: '
            '누적 투자 50억달러(약 6조6,517억원), '
            '목표 지분투자 100억달러(약 13조3,033억원), '
            '금융주선·지원 2,300억달러(약 305조9,759억원), '
            '10년 금융지원 계획 1조5,000억달러(약 1,995조4,950억원). '
            '기존 50억달러 누적 집행 성과의 계산을 바로잡은 것이며 '
            '신규 투자, 로봇 공장 계약 또는 방산 발주가 아닙니다.'
        )
    if cat == 'BMW Gen6 · 선양 배터리팩 양산 공식 개시':
        return (
            'BMW는 10/15 선양에서 Gen6 고전압 배터리팩 양산을 시작했습니다. '
            'CATL과 46mm 원통형 셀 공급계약은 별도로 존재하지만 BMW 직접 '
            '원통형 셀 제조·이번 팩라인의 특정 셀 공급사 확정과는 다릅니다. '
            '셀 입고검사→냉각 클러스터→레이저 용접·실시간 검사→'
            '발포·밀봉→Energy Master 설치→최종검사까지가 새 양산 공정입니다. '
            '실제 셀 발주 GWh·팩 생산량·중국 차량 고객 인도와 '
            '공급사별 매출 인식을 따로 확인합니다.'
        )
    if cat == 'BMW Gen6 · 중국 신세대 전기차 실제 고객 인도':
        return (
            'BMW가 Gen6 배터리팩을 통합한 중국 내 생산 Neue Klasse '
            '차량의 실제 고객 인도를 자체 확인한 단계입니다. '
            '이전 팩라인 SOP와 별도이며 차량 생산·판매 물량, '
            '배터리 셀 출하 GWh, 팩 생산 수율과 보증비용을 따로 봅니다.'
        )
    if cat == 'JP모건 SRI · 50억달러 지분투자 누적 집행':
        return (
            '2025년 출범한 SRI의 첫해 누적 집행 성과입니다. '
            '전략적 투자그룹 지분투자 50억달러(약 6조6,517억원)는 '
            '100억달러(약 13조3,033억원) 지분투자 목표의 절반이며, '
            '금융지원·주선 실적 2,300억달러(약 305조9,759억원)와 '
            '장기 종합계획 1조5,000억달러(약 1,995조4,950억원)는 '
            '서로 다른 금액입니다. 신규 50억달러 발주나 '
            '방산 한 분야의 확정 구매계약이 아닙니다. '
            '고객·투자받은 기업·지분율·유입 현금·'
            '실제 공장 착공·수주 및 정비·운영 매출을 추적합니다. '
            '환율은 10/19 19:05 KST 조회 1달러=1,330.33원 기준.'
        )
    return _bmw_jpm_prev_meaning(cat)


def _bmw_jpm_risk(cat: str) -> str:
    if cat == 'JP모건 SRI · 환율 표기 정정(기존 알림)':
        return (
            '원인은 2026-10-19 실시간 확인 환율과 '
            '이전 영업일 일일 환율을 혼용한 표기였습니다. '
            '이전 원화값을 신규 자금집행 증거로 쓰지 않고 '
            '공식 투자처·투자계약·금융조건 확인을 계속합니다.'
        )
    if cat.startswith('BMW Gen6 · '):
        return (
            '6~12개월 위험은 셀 입고품질·셀당 발열, '
            '용접부 결함과 검사시간·발포 접착·기밀성·팩 조립수율·'
            '열폭주 전파·냉각 및 보증충당금입니다. '
            '셀 에너지 밀도 20% 이상 개선이 팩/차량 성능 20% '
            '개선을 동일하게 보장하지 않습니다. '
            '중국 차량 인도 대수, 팩 양품률·교환 접수, '
            '미국·멕시코 라인 실제 양산시점을 확인합니다.'
        )
    if cat == 'JP모건 SRI · 50억달러 지분투자 누적 집행':
        return (
            '6~24개월 실패 경로는 지분투자 성과를 미국 로봇 공장 '
            '수주로 과장하는 것과 투자기업의 지연·평가손실·'
            '자금소진입니다. 100억달러 초기 지분투자 한도 '
            '중 50억달러 집행으로 단순 산술상 50%가 남았지만 '
            '반드시 같은 분야에 추가 배분해야 하는 의무는 없습니다. '
            '금융주선액을 은행 직접 현금 지출이나 방산 계약으로 '
            '착각하지 말고 공시된 투자처·계약·실제 사업비·금융조건을 확인합니다.'
        )
    return _bmw_jpm_prev_risk(cat)


def _bmw_jpm_verify(item: dict, group: str, text: str) -> str:
    if item.get('jpm_fx_correction'):
        return (
            '정정 안내(회사 신규 발표가 아님) · JPMorganChase 10/19 '
            '원문은 기존 누적집행 사실 근거 · '
            '10/19 19:05 KST 조회 1달러=1,330.33원 검산'
        )
    if group == 'bmw_gen6_pack':
        return (
            'BMW Group 10/15 공식 보도자료·10/16 BMW China 공식자료·'
            'electrive.com 10/15 보도 교차 확인 · 배터리팩 양산 확정, '
            '셀 자체 양산·현지 셀 공급사·GWh·첫 차량 인도 미확인'
        )
    if group == 'jpm_sri_2026':
        return (
            '10/19 JPMorganChase 배포 Business Wire 1년 성과 발표·'
            'Reuters 당일 보도·10/13 Bloomberg 기존 집행 규모 대조 · '
            '기존 지분투자 50억달러 누적 집행 확정, '
            '신규 50억달러 방산 발주나 기업별 수주계약은 미확인'
        )
    return _bmw_jpm_prev_verify(item,group,text)


def _bmw_jpm_title(title: str, source: str) -> str:
    if source == '원화 계산 정정' and 'JPMorganChase' in title:
        return '정정: JP모건 SRI 기존 알림 원화환산 단일 기준으로 통일'
    if _is_bmw_gen6_pack(title):
        return 'BMW, 선양 Gen6 고전압 배터리팩 실제 양산 개시(셀 생산과 구분)'
    if _is_jpm_sri(title):
        return 'JP모건, 안보·로봇·제조 SRI 지분투자 50억달러 누적 집행'
    return _bmw_jpm_prev_title(title,source)


def _bmw_jpm_tag(group: str) -> str:
    if group == 'bmw_gen6_pack': return 'BMW 원통형 배터리팩'
    if group == 'jpm_sri_2026': return 'JP모건 전략적 투자'
    return _bmw_jpm_prev_tag(group)


def _bmw_jpm_key(item: dict) -> str:
    text=f"{item.get('title','')} {item.get('description','')}"
    if item.get('jpm_fx_correction'):
        return hashlib.sha256(b'jpm-sri|2026-10-19|once-only-fx-correction-1330.33').hexdigest()
    g=_bmw_jpm_group(text)
    if g == 'bmw_gen6_pack':
        stage=_bmw_gen6_pack_stage(text,item.get('source') or '')
        return hashlib.sha256(f'bmw|gen6|shenyang|{stage}|2026-10-15'.encode()).hexdigest()
    if g == 'jpm_sri_2026':
        stage=_jpm_sri_stage(text,item.get('source') or '')
        return hashlib.sha256(f'jpm|sri|first-year|5bn-deployed|230bn-facilitated|{stage}'.encode()).hexdigest()
    return _bmw_jpm_prev_key(item)


def _bmw_jpm_select(items: list[dict],seen: set[str],force: bool,limit: int) -> list[dict]:
    chosen=_bmw_jpm_prev_select(items,seen,force,limit)
    candidates=items if force else [x for x in items if x.get('key') not in seen]
    for grp in ('bmw_gen6_pack','jpm_sri_2026'):
        match=next((x for x in candidates
                    if x.get('group')==grp and x.get('score',0)>=11),None)
        if match and not any(x.get('key')==match.get('key') for x in chosen):
            chosen=([match,*chosen] if len(chosen)<limit else [match,*chosen[:-1]])
    return chosen


base.query_news=_bmw_jpm_query
base.topic_group=_bmw_jpm_group
base.score=_bmw_jpm_score
base.category=_bmw_jpm_category
base.meaning=_bmw_jpm_meaning
base.risk=_bmw_jpm_risk
base.verification=_bmw_jpm_verify
base.clean_title=_bmw_jpm_title
base.tag_for=_bmw_jpm_tag
base.key=_bmw_jpm_key
base.select_diverse=_bmw_jpm_select

for _rec in (BMW_GEN6_PACK_RECOVERY,JPM_SRI_DEPLOYMENT_RECOVERY,JPM_SRI_FX_CORRECTION_RECOVERY):
    if _rec not in base.QUERIES: base.QUERIES.append(_rec)
for _q in (
    '(BMW OR 宝马) (Gen6 OR 第六代 OR 6세대) (Shenyang OR 선양 OR 沈阳) '
    '(battery OR 배터리) (series production OR 양산 개시 OR 첫 고객 인도 OR 용접 수율)',
    '(JPMorganChase OR JPMorgan OR JP모건) (SRI OR Security and Resiliency) '
    '(equity deployed OR 5 billion OR 50억달러 OR funded company OR investee) '
    '(robotics OR autonomous manufacturing OR hypersonic OR battery storage)',
):
    if _q not in base.QUERIES: base.QUERIES.append(_q)



# Volkswagen Europe high-voltage battery recall: 2026-10 safety event.
# UK 93MF/93MV is manufacturer confirmed, while German KBA rollout remains
# pending. US 26V630/93EX (22,524 ID.4s, SK Battery America) is DIFFERENT.
# Never attribute a European cell maker using a US recall.
VW_EU_BATTERY_RECALL_RECOVERY = 'DIRECT_VW_EU_93MF_93MV_80PCT_OFFICIAL_20261019'
VW_EU_BATTERY_RECALL_URL = (
    'https://www.volkswagen.co.uk/en/owners-and-services/my-car/'
    'battery-recall-campaign.html'
)
VW_EU_OFFICIAL_SOURCES = {
    'Volkswagen UK', 'Volkswagen Vans UK', 'Volkswagen Denmark',
}
VW_EU_GERMAN_REGULATOR_SOURCES = {'KBA', 'Kraftfahrt-Bundesamt'}
VW_RECALL_NAME = re.compile(
    r'Volkswagen|폭스바겐|\bVW\b', re.I
)
VW_RECALL_BATTERY = re.compile(
    r'high[-\s]?voltage\s+batter(?:y|ies)|HV\s+batter(?:y|ies)|'
    r'고전압\s*배터리|배터리\s*셀|battery\s*cell|'
    r'배터리\s*리콜', re.I
)
VW_RECALL_EVENT = re.compile(
    r'recall|리콜|93MF|93MV|26V630|93EX|80\s*%', re.I
)
VW_RECALL_CAMPAIGN_EU = re.compile(r'\b93MF\b|\b93MV\b', re.I)
VW_RECALL_SAFETY = re.compile(
    r'80\s*%|overheat|overheating|thermal|fire|충전\s*제한|과열|화재',
    re.I,
)
VW_RECALL_GERMANY = re.compile(r'KBA|Kraftfahrt-Bundesamt|독일\s*연방|German\s*Federal',re.I)
VW_RECALL_ACTIVATED = re.compile(
    r'(?:리콜|조치).{0,25}(?:등록|개시|발효|확정)|'
    r'(?:recall|campaign).{0,30}(?:officially\s+)?(?:issued|activated|launched)',
    re.I,
)
VW_RECALL_ACTIVATION_NEGATION = re.compile(
    r'미등록|준비|예정|협의|아직|not\s+yet|pending|prepar|unconfirmed',
    re.I,
)


def _is_vw_battery_recall(text: str) -> bool:
    return bool(
        VW_RECALL_NAME.search(text)
        and VW_RECALL_BATTERY.search(text)
        and VW_RECALL_EVENT.search(text)
    )


def _vw_eu_recall_stage(text: str, source: str = '') -> str:
    if not _is_vw_battery_recall(text):
        return ''
    if (source in VW_EU_GERMAN_REGULATOR_SOURCES
            and VW_RECALL_CAMPAIGN_EU.search(text)
            and VW_RECALL_GERMANY.search(text)
            and VW_RECALL_ACTIVATED.search(text)
            and not VW_RECALL_ACTIVATION_NEGATION.search(text)):
        return 'germany_regulator_activated'
    if (source in VW_EU_OFFICIAL_SOURCES
            and VW_RECALL_CAMPAIGN_EU.search(text)
            and VW_RECALL_SAFETY.search(text)):
        return 'uk_official_safety_campaign'
    # A 2026-09-30 US filing is prior context, never a new EU campaign.
    return 'background_or_us_context'


def _vw_eu_recall_recovery() -> list[dict]:
    # Date-only manufacturer evidence: do not invent a publication hour.
    if base.NOW.astimezone(base.KST).date() > dt.date(2026, 10, 25):
        return []
    return [{
        'title': (
            '폭스바겐 유럽 고전압 배터리 리콜: 영국 93MF·93MV '
            '안전조치 80% 제한 공식 안내'
        ),
        'link': VW_EU_BATTERY_RECALL_URL,
        'description': (
            '폭스바겐 영국 공식 홈페이지는 고전압 배터리 '
            '안전 캠페인 93MF 및 93MV를 확인한다. '
            '특정 공급업체에서 2022~2025년 생산한 배터리 셀에 '
            '품질 편차 가능성이 있으며 일부 ID.3, ID.4, ID.7과 '
            'ID.Buzz 및 ID.Buzz Cargo를 점검한다. '
            '영국 ID.Buzz 차종의 80% 충전 제한 조치는 '
            '2026년 10월 12일 주간에 시작됐다고 공식 발표됐다. '
            '80%를 넘겨 충전하면 과열·최악의 경우 화재 위험이 있어 '
            '해당 차량의 충전 한도를 최대 80%로 제한한다. '
            '폭스바겐 영국 안내의 배터리 점검 소요시간은 약 1시간이며 '
            '필요에 따라 소프트웨어 조치 또는 배터리 모듈 교체가 가능하다. '
            '독일의 KBA 공식 등록·발효 및 정확한 유럽 차량 대수는 '
            '2026년 10월 19일 기준 추가 확인이 필요하다. '
            '10월 15~16일 dpa·Handelsblatt에서 독일 리콜 준비 및 '
            'Cupra Born 포함 유럽 일부 차종을 보도했으나 '
            '유럽 공급사 실명·배터리 팩 전량 교체대수·비용은 공개되지 않았다. '
            '미국 26V630/93EX 리콜의 대상인 ID.4 22,524대 '
            '(2023~2026년형)는 2026년 9월 30일 별도 신고 건이다. '
            '미국 건에서 확인된 SK Battery America 공급 사실을 '
            '유럽 대상 배터리 셀 공급사로 치환하면 안 된다. '
            '2018년 Volkswagen Group은 유럽용으로 SK이노베이션·'
            'LG화학·삼성SDI 등을 당시 협력사로 열거했으나 '
            '그 과거 다중공급 사실은 이번 결함 셀의 공급사 식별 자료가 아니다. '
            '유럽 리콜의 실제 검사·교체 대수, 셀 일련번호, '
            '보증충당금·수리비 부담자와 고객 통지·수리 완료율을 추적한다.'
        ),
        'source': 'Volkswagen UK',
        'published': None,
        'direct_recovery': True,
        'vw_europe_official_93mf_93mv': True,
    }]


_vw_recall_prev_query = base.query_news
_vw_recall_prev_group = base.topic_group
_vw_recall_prev_score = base.score
_vw_recall_prev_category = base.category
_vw_recall_prev_meaning = base.meaning
_vw_recall_prev_risk = base.risk
_vw_recall_prev_verification = base.verification
_vw_recall_prev_title = base.clean_title
_vw_recall_prev_tag = base.tag_for
_vw_recall_prev_key = base.key
_vw_recall_prev_select = base.select_diverse


def _vw_eu_recall_query(q: str) -> list[dict]:
    if q == VW_EU_BATTERY_RECALL_RECOVERY:
        return _vw_eu_recall_recovery()
    return _vw_recall_prev_query(q)


def _vw_eu_recall_group(text: str) -> str | None:
    if _is_vw_battery_recall(text):
        return 'vw_europe_battery_recall'
    return _vw_recall_prev_group(text)


def _vw_eu_recall_score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')}"
    if _is_vw_battery_recall(text):
        return {
            'uk_official_safety_campaign': 49,
            'germany_regulator_activated': 57,
            'background_or_us_context': 0,
        }.get(_vw_eu_recall_stage(text, item.get('source') or ''), 0)
    return _vw_recall_prev_score(item)


def _vw_eu_recall_category(text: str, group: str) -> str:
    if group == 'vw_europe_battery_recall':
        # The renderer loses source information; classify by the verified
        # campaign marker, not by a US SKBA name embedded for comparison.
        if (VW_RECALL_CAMPAIGN_EU.search(text)
                and VW_RECALL_GERMANY.search(text)
                and VW_RECALL_ACTIVATED.search(text)
                and not VW_RECALL_ACTIVATION_NEGATION.search(text)):
            return '폭스바겐 유럽 배터리 리콜 · 독일 KBA 공식 시행'
        return '폭스바겐 유럽 배터리 리콜 · 영국 93MF·93MV 충전 제한'
    return _vw_recall_prev_category(text, group)


def _vw_eu_recall_meaning(cat: str) -> str:
    if cat == '폭스바겐 유럽 배터리 리콜 · 영국 93MF·93MV 충전 제한':
        return (
            '영국 폭스바겐 공식 안내: 93MF·93MV 고전압 배터리 '
            '품질 점검과 최대 80% 충전 제한 조치. '
            '특정 공급업체의 2022~2025년 배터리 셀 품질 문제이며, '
            '셀 과열·열폭주·화재 위험 완화가 목적입니다. '
            '영국 ID.Buzz는 10/12 주간부터 제한을 시작했습니다. '
            '배터리 점검은 약 1시간이고 필요 시 소프트웨어 조치·'
            '모듈 교체가 이뤄질 수 있지만 실제 교체율은 미확정입니다. '
            '독일은 별도 당국 협의 단계이며 '
            '전체 유럽 대상 대수·공급사·실제 교체비는 미공개입니다. '
            '미국 ID.4 22,524대(26V630/93EX) 및 SK Battery America '
            '공급 사실은 미국 별도 리콜 자료이므로 유럽과 합산하지 않습니다.'
        )
    if cat == '폭스바겐 유럽 배터리 리콜 · 독일 KBA 공식 시행':
        return (
            '독일 KBA가 유럽 고전압 배터리 안전조치를 정식 개시한 '
            '단계입니다. 독일 공식 대상 차대번호·차종·대수, '
            '80% 충전 제한과 소프트웨어·모듈 교체 대상, '
            '결함 셀 공급사 및 예상 충당금을 확인합니다. '
            '기존 영국 93MF·93MV 조치와 실제 중복 차량을 구분합니다.'
        )
    return _vw_recall_prev_meaning(cat)


def _vw_eu_recall_risk(cat: str) -> str:
    if cat.startswith('폭스바겐 유럽 배터리 리콜 ·'):
        return (
            '가장 현실적인 실패 경로는 셀 품질 편차를 '
            '소프트웨어로 충분히 분리하지 못해 모듈 교체·'
            '정비 인력·보증충당금·보험 비용이 늘어나는 것입니다. '
            '공식 안내상 배터리 점검 약 1시간이므로 '
            '실제 점검 1만 대라면 검사 공임만 1만 정비시간입니다 '
            '(가정 예시, 공식 리콜 대상 대수 아님). '
            '셀 내부 단락·열폭주 전파·화재 안전, '
            '충전율 제한 장기화에 따른 고객 불편과 '
            '고객 검수 지연이 6~12개월 위험구간입니다. '
            '차대번호별 통지·검사 건수·불량 모듈 교체율·'
            '교체부품 납기·회사 분기 품질충당금을 추적합니다. '
            '유럽 공급업체는 공식 미공개이며 미국 SKBA 건과 분리합니다.'
        )
    return _vw_recall_prev_risk(cat)


def _vw_eu_recall_verification(item: dict, group: str, text: str) -> str:
    if group == 'vw_europe_battery_recall':
        if _vw_eu_recall_stage(text, item.get('source') or '') == 'germany_regulator_activated':
            return '독일 KBA 공식 시행 단계 · 유럽 물량·차대번호 원자료 재확인 필요'
        if _vw_eu_recall_stage(text, item.get('source') or '') == 'uk_official_safety_campaign':
            return (
                'Volkswagen UK 93MF·93MV 공식 안내·Volkswagen Vans UK '
                '10/12 주간 80% 제한·dpa 10/15 독일 준비보도 대조 · '
                '미국 NHTSA 26V630은 9/30 별도 리콜 · '
                '유럽 셀 공급사 미공개·정확한 유럽 수량 미확정'
            )
        return '언론 보도 또는 별도 미국 사건 · 유럽 공식 시행 실적 아님'
    return _vw_recall_prev_verification(item, group, text)


def _vw_eu_recall_title(title: str, source: str) -> str:
    if _is_vw_battery_recall(title):
        if source in VW_EU_GERMAN_REGULATOR_SOURCES:
            return '독일 KBA 유럽 배터리 리콜 공식 시행'
        return '영국 93MF·93MV 배터리 80% 안전조치 공식 안내'
    return _vw_recall_prev_title(title, source)


def _vw_eu_recall_tag(group: str) -> str:
    if group == 'vw_europe_battery_recall':
        return '폭스바겐 고전압 배터리'
    return _vw_recall_prev_tag(group)


def _vw_eu_recall_key(item: dict) -> str:
    text=f"{item.get('title','')} {item.get('description','')}"
    if _is_vw_battery_recall(text):
        stage=_vw_eu_recall_stage(text,item.get('source') or '')
        return hashlib.sha256(
            f'vw|europe-hv-battery|{stage}|93mf-93mv|2026-10'.encode()
        ).hexdigest()
    return _vw_recall_prev_key(item)


def _vw_eu_recall_select(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    selected = _vw_recall_prev_select(items, seen, force, limit)
    possible = items if force else [x for x in items if x.get('key') not in seen]
    candidate = next((x for x in possible if (
        x.get('group') == 'vw_europe_battery_recall' and x.get('score',0)>=11
    )),None)
    if candidate and not any(x.get('key') == candidate.get('key') for x in selected):
        selected = ([candidate, *selected] if len(selected)<limit else
                    [candidate, *selected[:-1]])
    return selected


base.query_news = _vw_eu_recall_query
base.topic_group = _vw_eu_recall_group
base.score = _vw_eu_recall_score
base.category = _vw_eu_recall_category
base.meaning = _vw_eu_recall_meaning
base.risk = _vw_eu_recall_risk
base.verification = _vw_eu_recall_verification
base.clean_title = _vw_eu_recall_title
base.tag_for = _vw_eu_recall_tag
base.key = _vw_eu_recall_key
base.select_diverse = _vw_eu_recall_select

if VW_EU_BATTERY_RECALL_RECOVERY not in base.QUERIES:
    base.QUERIES.append(VW_EU_BATTERY_RECALL_RECOVERY)
for _q in (
    '(Volkswagen OR 폭스바겐 OR VW) (93MF OR 93MV OR 93EX) '
    '(battery recall OR 고전압 배터리 리콜 OR 화재 위험 OR 80% 제한)',
    '(폭스바겐 OR Volkswagen) (유럽 OR 독일 OR UK OR Europe) '
    '(배터리 셀 OR battery cells) '
    '(리콜 등록 OR 신규 안전조치 OR 공식 대상차량 OR KBA)',
):
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)


# 2026 Dec Tesla AGM and Humanoids Summit: verified stages, not clickbait.
# Current 2026-10-19 SEC notice is primary; the original SEC HTML returned
# an access error so the Tesla IR confirmation and faithful proxy mirror
# plus Reuters were checked separately. The organizer's GENERIC LinkedIn
# company profile does not prove Tesla's specific Optimus program or V3.
TESLA_AGM26_EVENT = 'DIRECT_TESLA_AGM_DEF14A_20261019'
TESLA_AGM26_SEC = 'https://www.sec.gov/Archives/edgar/data/1318605/000110465926116700/tm267596-1_def14a.htm'
TESLA_AGM26_PRIMARY = {'Tesla IR','Tesla Investor Relations','Tesla','SEC'}
TESLA_SUMMIT26_PRIMARY = {'Humanoids Summit','HumanoidsSummit'}
TESLA_AGM26_RE = re.compile(r'2026.{0,60}(?:annual\s+(?:shareholders?|stockholders?)\s+meeting|주주총회)|TSLA2026|tm267596-1_def14a',re.I)
TESLA_AGM26_DATE = re.compile(r'Dec(?:ember)?\s*3,?\s*2026|2026[-./]12[-./]0?3|12월\s*0?3일',re.I)
TESLA_AGM26_RESULTS = re.compile(r'final\s+vot(?:e|ing)\s+results|certified\s+vote|(?:최종\s*)?표결\s*결과\s*(?:발표|공시)',re.I)
TESLA_SUMMIT26_RE = re.compile(r'Humanoids?\s*Summit|휴머노이드\s*서밋',re.I)
TESLA_SUMMIT26_DATE = re.compile(r'2026|Dec(?:ember)?\s*1\s*(?:[-–]|and|to)\s*2|12월\s*1\s*[~\-–]\s*2일',re.I)
TESLA_SUMMIT26_DEMO = re.compile(r'(?:Optimus|옵티머스).{0,120}(?:hands[- ]on|live\s+demo|실물\s*(?:전시|체험|시연)|현장\s*시연)|(?:hands[- ]on|live\s+demo|실물\s*(?:체험|시연)).{0,120}(?:Optimus|옵티머스)',re.I)
TESLA_SUMMIT26_PARTNER = re.compile(
    r'(?:Tesla|테슬라).{0,80}(?:official\s+partner|공식\s+파트너|'
    r'참가\s+확정|confirmed\s+participant)|'
    r'(?:official\s+partner|공식\s+파트너).{0,80}(?:Tesla|테슬라)',
    re.I,
)
TESLA_SUMMIT26_V3 = re.compile(r'(?:Optimus|옵티머스).{0,110}(?:V3|Gen\s*3|3세대).{0,70}(?:unveil|reveal|debut|시연|공개)|(?:V3|Gen\s*3|3세대).{0,100}(?:Optimus|옵티머스).{0,70}(?:unveil|reveal|debut|시연|공개)',re.I)
TESLA_SUMMIT26_DENIAL = re.compile(r'V3.{0,45}(?:unconfirmed|not\s+confirmed|미확정|미정|언급\s*없음|미공개)|(?:not\s+confirmed|미확정|미정|언급\s*없음).{0,45}V3',re.I)

def _agm26_match(t):
    return bool(re.search(r'Tesla|테슬라|TSLA',t,re.I) and TESLA_AGM26_RE.search(t))

def _sum26_match(t):
    return bool(TESLA_SUMMIT26_RE.search(t) and TESLA_SUMMIT26_DATE.search(t)
                and re.search(r'Tesla|테슬라|Optimus|옵티머스',t,re.I))

def _agm26_stage(item):
    t=' '.join(str(item.get(x) or '') for x in ('title','description'))
    src,link=item.get('source') or '',item.get('link') or ''
    if not _agm26_match(t):
        return ''
    primary=(src in TESLA_AGM26_PRIMARY and bool(re.match(
        r'https://(?:www\.sec\.gov/Archives/edgar/|ir\.tesla\.com/|www\.tesla\.com/)',link,re.I)))
    if primary and TESLA_AGM26_RESULTS.search(t): return 'official_vote_result'
    if primary and TESLA_AGM26_DATE.search(t): return 'official_notice'
    return 'unverified'

def _sum26_stage(item):
    t=' '.join(str(item.get(x) or '') for x in ('title','description'))
    if not _sum26_match(t): return ''
    src,link=item.get('source') or '',item.get('link') or ''
    tesla=(
        (src in {'Tesla','Tesla IR','Tesla Official'} and bool(re.match(
            r'https://(?:www\.)?tesla\.com/',link,re.I)))
        or (src in {'Tesla (X)','Elon Musk (X)','Tesla AI (X)'} and bool(re.match(
            r'https://(?:x\.com|twitter\.com)/(?:Tesla|Tesla_AI|elonmusk)/status/\d+',
            link,re.I)))
    )
    organizer=(src in TESLA_SUMMIT26_PRIMARY and bool(re.match(
        r'https://(?:www\.)?humanoidssummit\.com/|'
        r'https://(?:www\.)?linkedin\.com/posts/humanoidssummit[_\-]',link,re.I)))
    if tesla and TESLA_SUMMIT26_V3.search(t) and not TESLA_SUMMIT26_DENIAL.search(t):
        return 'official_v3'
    if TESLA_SUMMIT26_DEMO.search(t):
        if tesla: return 'tesla_confirmed_demo'
        if organizer: return 'organizer_confirmed_demo'
    if TESLA_SUMMIT26_PARTNER.search(t):
        if tesla: return 'tesla_confirmed_partner'
        if organizer: return 'organizer_confirmed_partner'
    return 'unverified_participation'

def _agm26_recovery():
    if base.NOW.astimezone(base.KST).date()>dt.date(2026,10,27): return []
    return [{
        'title':'Tesla 2026 annual shareholder meeting December 3, 2026 DEF14A',
        'link':TESLA_AGM26_SEC,
        'description':(
            'Tesla 2026 annual shareholder meeting December 3, 2026, '
            '3:00 PM Central Standard Time; December 4 06:00 KST. '
            'Venue Gigafactory Texas in Austin with limited in-person lottery '
            'attendance and a public webcast. Shareholder record date Oct 13. '
            'Tesla IR confirms SEC definitive proxy DEF14A filing Oct 19. '
            'Faithfully reproduced proxy and Reuters independently confirm '
            'three items: Class I director election Elon Musk, Robyn Denholm '
            'and JB Straubel (three-year terms), advisory vote on 2025 '
            'executive compensation, and PwC auditor appointment for 2026. '
            'This is NOT an official Optimus V3 unveil, robot sales contract '
            'or manufacturing yield release. Separately the organizer confirms '
            'Humanoids Summit at San Mateo Event Center Dec 1-2, 2026. '
            'The reported Tesla official-partner status, hands-on Optimus '
            'display and FSD test drives were NOT independently verified from '
            'a specific official event post; this report does NOT confirm V3. '
            'Official summit webpages inconsistently number the event fifth '
            'versus sixth, so no edition rank is asserted.'
        ),
        'source':'Tesla IR',
        'published':None,
        'direct_recovery':True,
        'tesla_official_agm_notice':True,
    }]

_cal26_old_query=base.query_news
_cal26_old_group=base.topic_group
_cal26_old_score=base.score
_cal26_old_category=base.category
_cal26_old_meaning=base.meaning
_cal26_old_risk=base.risk
_cal26_old_verification=base.verification
_cal26_old_title=base.clean_title
_cal26_old_tag=base.tag_for
_cal26_old_key=base.key
_cal26_old_select=base.select_diverse

def _cal26_query(q):
    if q==TESLA_AGM26_EVENT: return _agm26_recovery()
    return _cal26_old_query(q)

def _cal26_group(t):
    if _agm26_match(t): return 'tesla_agm_2026'
    if _sum26_match(t): return 'tesla_humanoids_summit_2026'
    return _cal26_old_group(t)

def _cal26_score(item):
    t=' '.join(str(item.get(x) or '') for x in ('title','description','source'))
    group=_cal26_group(t)
    if group=='tesla_agm_2026':
        return {'official_notice':43,'official_vote_result':59,'unverified':0}.get(_agm26_stage(item),0)
    if group=='tesla_humanoids_summit_2026':
        return {'organizer_confirmed_partner':35,'tesla_confirmed_partner':43,
                'organizer_confirmed_demo':47,'tesla_confirmed_demo':56,
                'official_v3':74,'unverified_participation':0}.get(_sum26_stage(item),0)
    return _cal26_old_score(item)

def _cal26_category(t,group):
    if group=='tesla_agm_2026':
        return ('테슬라 2026 주주총회 · 공식 표결 결과'
                if TESLA_AGM26_RESULTS.search(t) else
                '테슬라 2026 주주총회 · 12월 3일 공식 일정')
    if group=='tesla_humanoids_summit_2026':
        if TESLA_SUMMIT26_V3.search(t) and not TESLA_SUMMIT26_DENIAL.search(t):
            return '테슬라 Humanoids Summit · V3 공식 공개 예고'
        if TESLA_SUMMIT26_DEMO.search(t):
            return '테슬라 Humanoids Summit · Optimus 현장 시연 공식 확인'
        return '테슬라 Humanoids Summit · 파트너 참가 공식 확인'
    return _cal26_old_category(t,group)

def _cal26_meaning(cat):
    if cat=='테슬라 2026 주주총회 · 12월 3일 공식 일정':
        return ('Tesla의 10/19 SEC 위임장 제출로 12/3 중부시간 15시 '
                '(한국 12/4 오전 6시) 주주총회 일정이 확정됐습니다. '
                'Elon Musk·Robyn Denholm·JB Straubel Class I 이사 선임, '
                '2025 임원 보수 자문투표, PwC 감사인 승인 등 3개 안건입니다. '
                '이는 Optimus V3 시연·수주·실제 양산 발표가 아닙니다. '
                '12/1~2 Humanoids Summit 행사 개최는 주최 측 공식 확인이지만 '
                'Tesla 개별 파트너·Optimus 체험·V3 공개는 따로 확인해야 합니다.')
    if cat=='테슬라 2026 주주총회 · 공식 표결 결과':
        return ('회사 공식 표결 결과가 나온 단계입니다. 3개 안건의 실제 '
                '찬반·가결 여부를 초기 위임장과 분리하고 Optimus 기술 발표와 혼동하지 않습니다.')
    if cat=='테슬라 Humanoids Summit · V3 공식 공개 예고':
        return ('Tesla의 직접 공식 자료가 Optimus V3 공개 일정을 확정한 단계입니다. '
                '실제 시연·자율 작업 성공률·사람 개입·손 내구성·양산물량은 후속 검증합니다.')
    if cat=='테슬라 Humanoids Summit · Optimus 현장 시연 공식 확인':
        return ('주최 측 또는 Tesla가 특정 Optimus 시연 프로그램을 직접 확정한 단계입니다. '
                'V2 전시·기존 홍보물과 V3 공개를 혼동하지 않고 '
                '현장 자율 시연·원격지원·실제 출하를 각각 확인합니다.')
    if cat=='테슬라 Humanoids Summit · 파트너 참가 공식 확인':
        return ('Tesla의 행사 참가·파트너 지위만 주최 측 또는 Tesla가 공식 확인한 '
                '단계입니다. 이 사실로 Optimus 실물 체험, FSD 시승이나 '
                'V3 공개·실제 유상 계약까지 단정할 수 없습니다. '
                '행사 일정과 구체 시연 프로그램을 각각 추가 확인합니다.')
    return _cal26_old_meaning(cat)

def _cal26_risk(cat):
    if cat.startswith('테슬라 2026 주주총회'):
        return ('주주총회는 일정·의결권 행사이지 신규 Optimus 제품 발표를 '
                '보장하지 않습니다. 회의 후 실제 로봇 성능·판매계약·'
                '출하량 공시가 없으면 본업 매출 상향 근거가 아닙니다.')
    if cat.startswith('테슬라 Humanoids Summit'):
        return ('행사 홍보 이미지의 V2 또는 원격조종 데모를 V3 자율양산으로 '
                '오판하는 것이 핵심 실패 경로입니다. 12/1~2 실제 기종, '
                '작업의 자율성, 안전요원·원격지원 개입, 작업 성공률, '
                '손 고장과 정비비용을 확인해야 합니다. 매출 발생과도 별도입니다.')
    return _cal26_old_risk(cat)

def _cal26_verification(item,group,t):
    if group=='tesla_agm_2026':
        return ('Tesla 투자자관계 10/19 SEC 위임장 접수 확인 · '
                '위임장 공개 복제본·Reuters 일정/안건 교차확인 · '
                'SEC 원본 HTML 직접 열람 실패 · V3 안건 없음'
                if _agm26_stage(item)=='official_notice'
                else 'Tesla/SEC 공식 표결 기록 단계 또는 미검증 보도')
    if group=='tesla_humanoids_summit_2026':
        if _sum26_stage(item)=='official_v3': return 'Tesla 공식 V3 시연 예고 · 실제 공개/양산 별도'
        if _sum26_stage(item) in {'tesla_confirmed_demo','organizer_confirmed_demo'}:
            return '행사 주최 측 또는 Tesla의 개별 공식 시연 공지 확인 · V3 여부 별도'
        if _sum26_stage(item) in {'tesla_confirmed_partner','organizer_confirmed_partner'}:
            return '주최 측 또는 Tesla 공식 참가 공지 확인 · 실물 체험·FSD 시승·V3 미확정'
        return '주최 측 행사 날짜 확인 · Tesla 참가·시연 프로그램 개별 공식 확인 전'
    return _cal26_old_verification(item,group,t)

def _cal26_title(title,source):
    t=title+' '+source
    if _agm26_match(t):
        return ('2026 주주총회 공식 표결 결과' if TESLA_AGM26_RESULTS.search(t)
                else '12월 3일 공식 주주총회…한국 12월 4일 오전 6시')
    if _sum26_match(t):
        if TESLA_SUMMIT26_V3.search(t) and not TESLA_SUMMIT26_DENIAL.search(t):
            return 'Optimus V3 첫 공개 공식 예고'
        if TESLA_SUMMIT26_DEMO.search(t):
            return 'Optimus 현장 시연 공식 확인…V3 여부 별도'
        return '공식 파트너·참가 확인…시연·V3 여부 별도'
    return _cal26_old_title(title,source)

def _cal26_tag(group):
    if group=='tesla_agm_2026': return '테슬라 주주총회'
    if group=='tesla_humanoids_summit_2026': return '테슬라 로봇 서밋'
    return _cal26_old_tag(group)

def _cal26_key(item):
    t=' '.join(str(item.get(x) or '') for x in ('title','description','source'))
    group=_cal26_group(t)
    if group=='tesla_agm_2026':
        return hashlib.sha256(f'tesla|agm|20261203|{_agm26_stage(item)}'.encode()).hexdigest()
    if group=='tesla_humanoids_summit_2026':
        return hashlib.sha256(f'tesla|summit|20261201-02|{_sum26_stage(item)}'.encode()).hexdigest()
    return _cal26_old_key(item)

def _cal26_select(items,seen,force,limit):
    selected=_cal26_old_select(items,seen,force,limit)
    candidates=items if force else [i for i in items if i.get('key') not in seen]
    for group in ('tesla_agm_2026','tesla_humanoids_summit_2026'):
        event=next((i for i in candidates if i.get('group')==group and i.get('score',0)>=11),None)
        if event and not any(i.get('key')==event.get('key') for i in selected):
            selected=([event,*selected] if len(selected)<limit else [event,*selected[:-1]])
    return selected

base.query_news=_cal26_query
base.topic_group=_cal26_group
base.score=_cal26_score
base.category=_cal26_category
base.meaning=_cal26_meaning
base.risk=_cal26_risk
base.verification=_cal26_verification
base.clean_title=_cal26_title
base.tag_for=_cal26_tag
base.key=_cal26_key
base.select_diverse=_cal26_select

if TESLA_AGM26_EVENT not in base.QUERIES:
    base.QUERIES.append(TESLA_AGM26_EVENT)
for q in (
    '(Tesla OR Optimus OR 테슬라 OR 옵티머스) ("Humanoids Summit" OR 휴머노이드 서밋) '
    '(2026 OR December) (partner OR hands-on OR demo OR V3 OR official OR 시연 OR 체험)',
    '(Tesla OR 테슬라) ("2026 Annual Meeting" OR "TSLA2026" OR 2026 주주총회) '
    '(December 3 OR 12월 3일 OR official voting results OR 8-K)',
):
    if q not in base.QUERIES: base.QUERIES.append(q)


# 2026-10-20 Samsung 24-hour-duty humanoid FIELD-TEST reporting and
# 2026-10-23 Presidential regulatory committee AGENDA. Existing watcher only.
# NEVER equate a 24-hour design target or three supervised shifts with a
# verified 24-hour autonomous uptime result; policy debate is not enacted law.
S24H_20261020_RECOVERY = "DIRECT_SAMSUNG_RX_24H_FIELD_REPORT_20261020"
KREG_OCT23_RECOVERY = "DIRECT_REGULATORY_COMMITTEE_ROBOT_AGENDA_20261020"
S24H_JOONGANG = "https://www.joongang.co.kr/article/25471125"
KREG_YONHAP = "https://www.yna.co.kr/view/AKR20261020047400001"
S24H_COMPANY_SOURCES = {"삼성전자", "Samsung Electronics", "Samsung Newsroom", "삼성전자 뉴스룸"}
S24H_REPORT_SOURCES = {"중앙일보", "연합뉴스", "뉴스1", "전자신문"}
KREG_OFFICIAL_SOURCES = {"청와대", "대통령실", "국무조정실", "국무총리실", "산업통상부", "과학기술정보통신부"}
KREG_REPORT_SOURCES = {"연합뉴스", "뉴스1", "머니투데이", "한국일보"}
S24H_WORD = re.compile(r"24\s*시간|24[-\s]*hour|around[-\s]*the[-\s]*clock",re.I)
S24H_SUBJECT = re.compile(r"휴머노이드|humanoid|이족\s*보행|로봇|robot",re.I)
S24H_TEST = re.compile(r"검증|시험|실증|테스트|연구개발|testing|pilot|validation",re.I)
S24H_OFFICIAL_UPTIME = re.compile(
    r"(?:24\s*시간|24[-\s]*hour).{0,65}(?:연속|무인|continuous|autonomous).{0,65}"
    r"(?:시험\s*통과|검증\s*완료|실측|입증|달성|passed|achieved|verified)|"
    r"(?:연속|continuous).{0,40}(?:24\s*시간|24[-\s]*hour).{0,70}"
    r"(?:실증\s*완료|검증\s*완료|달성|achieved|verified)",re.I
)
S24H_CES_OFFICIAL = re.compile(
    r"(?:CES\s*2027|2027\s*CES).{0,120}"
    r"(?:로봇|휴머노이드|robot|humanoid).{0,65}(?:공식\s*공개|공식\s*시연|전시\s*확정|첫\s*공개|unveiled|confirmed\s*demo)|"
    r"(?:로봇|휴머노이드|robot|humanoid).{0,80}"
    r"(?:CES\s*2027|2027\s*CES).{0,65}(?:공식\s*공개|시연\s*확정|unveiled)",re.I
)
S24H_CONTRACT = re.compile(
    r"(?:휴머노이드|로봇|humanoid|robot).{0,100}(?:유상\s*납품|"
    r"양산\s*출하\s*개시|정식\s*공급계약\s*체결|paid\s*contract|production\s*shipments)",re.I
)
S24H_NOT_CONFIRMED = re.compile(
    r"(?:24\s*시간|24[-\s]*hour).{0,60}(?:미검증|미확인|목표|검토|미달)|"
    r"(?:CES\s*2027|2027\s*CES).{0,80}(?:검토|예정|목표|미정|미확정|논의)",re.I
)


def _s24h_match(t: str) -> bool:
    if not re.search(r"삼성전자|Samsung\s*Electronics",t,re.I):
        return False
    if not S24H_SUBJECT.search(t):
        return False
    return bool((S24H_WORD.search(t) and re.search(
        r"RX|우면|R&D|서울연구|제조.*물류|CES\s*2027",t,re.I
    )) or (re.search(r"CES\s*2027|2027\s*CES",t,re.I)
            and re.search(r"이족보행|이족\s*보행|industrial\s*humanoid",t,re.I)))


def _s24h_stage(item: dict) -> str:
    t=" ".join(str(item.get(k) or "") for k in ("title","description"))
    source=item.get("source") or ""
    if not _s24h_match(t):
        return ""
    if source in S24H_COMPANY_SOURCES:
        if S24H_CONTRACT.search(t) and not re.search(r"계약\s*(?:검토|예정|미정)|미확정|planned|expect",t,re.I):
            return "official_customer_contract"
        if S24H_OFFICIAL_UPTIME.search(t) and not S24H_NOT_CONFIRMED.search(t):
            return "official_verified_uptime"
        if S24H_CES_OFFICIAL.search(t) and not S24H_NOT_CONFIRMED.search(t):
            return "official_ces_demonstration"
    if source in S24H_REPORT_SOURCES and S24H_WORD.search(t) and S24H_TEST.search(t):
        return "reported_supervised_field_test"
    return "background"


def _s24h_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date()>dt.date(2026,10,23):
        return []
    return [{
        "title":"삼성전자 RX, 우면동 24시간 작업 목표 이족 휴머노이드 현장 시험 보도",
        "link":S24H_JOONGANG,
        "description":(
            "2026-10-20 중앙일보 단독: 삼성전자 RX사업추진실이 우면동 서울R&D캠퍼스에서 "
            "제조·물류의 이족보행 휴머노이드 반복 업무를 검증 중이라고 업계 소식통을 인용해 보도했다. "
            "24시간 3교대 운용과 현장 직원 모니터링을 언급하지만 사람이 개입하지 않은 "
            "24시간 무중단 자율 가동 실측이나 작업 성공률·가동률·정비시간·출하량은 공개하지 않았다. "
            "CES 2027은 2027-01-06~09 개최가 CTA 공식 확인되나 이 로봇의 출품은 검토 단계로 "
            "공식 프로그램 확정이 아니다. 삼성전자는 7월 RX 조직 통합과 6월 구미 휴머노이드 "
            "양산라인 구축 계획을 별도로 공개했으며 이번 기사는 실제 양산 개시 공시가 아니다. "
            "삼성SDS의 9월 공식 RX ART에서 삼성전기·세메스의 작업 사례를 로봇으로 검증한 "
            "사실은 별도 관계사 협력이지 이번 이족보행 로봇의 고객·공급계약 증거가 아니다. "
            "기사 웹페이지 직접 열람은 제한되고 검색 색인·중앙일보 기사 인용 요약으로 대조했다. "
            "양산/고객 매출 금액·실제 24시간 연속 자율가동/사람 개입률은 미공개다."
        ),
        "source":"중앙일보",
        "published":None,
        "direct_recovery":True,
        "s24h_samsung_test":True,
    }]


KREG_OCT23_ID = re.compile(
    r"규제\s*합리화\s*위원회|규제\s*합리화위|규제개혁위원회|regulatory\s*rationalization",
    re.I
)
KREG_ROBOTIC = re.compile(r"로봇|robot|휴머노이드|humanoid|AI\s*데이터센터",re.I)
KREG_MEETING = re.compile(
    r"2026[-./]10[-./]23|10\s*월\s*23\s*일|(?:23\s*일).{0,80}(?:제2차|전체회의|위원회|로봇)|"
    r"(?:제\s*2\s*차|두\s*번째).{0,65}(?:전체회의|위원회)", re.I
)
KREG_IMPLEMENTED = re.compile(
    r"(?:(?:규제특례|안전인증|실증허용|인허가|로봇\s*현장|AI\s*데이터센터).{0,100}"
    r"(?:의결|최종\s*확정|시행\s*확정|승인\s*완료|공포|시행령\s*개정\s*완료))|"
    r"(?:(?:의결|최종\s*확정|승인\s*완료).{0,90}(?:규제특례|실증허용|인허가|안전인증))",
    re.I
)
KREG_NEGATION = re.compile(
    r"논의\s*예정|발표\s*예정|논의\s*중|검토\s*중|미확정|추진\s*계획|"
    r"시행\s*예정|의결\s*전|승인\s*전|결정된\s*바\s*없",re.I
)


def _kreg_oct23_match(t: str) -> bool:
    return bool(KREG_OCT23_ID.search(t) and KREG_ROBOTIC.search(t) and KREG_MEETING.search(t))


def _kreg_oct23_stage(item: dict) -> str:
    t=" ".join(str(item.get(k) or "") for k in ("title","description"))
    source=item.get("source") or ""
    if not _kreg_oct23_match(t):
        return ""
    if source in KREG_OFFICIAL_SOURCES and KREG_IMPLEMENTED.search(t) and not KREG_NEGATION.search(t):
        return "official_specific_measure_adopted"
    if (source in KREG_REPORT_SOURCES or source in KREG_OFFICIAL_SOURCES) and re.search(
        r"23\s*일|2026-10-23|10\s*월\s*23\s*일",t
    ) and re.search(r"주재|개최|예고|회의|발표",t):
        return "announced_meeting_agenda"
    return "background"


def _kreg_oct23_recovery() -> list[dict]:
    if base.NOW.astimezone(base.KST).date()>dt.date(2026,10,23):
        return []
    return [{
        "title":"이재명 대통령 10월 23일 규제합리화위 2차 회의 예고…로봇·반도체·AI 데이터센터",
        "link":KREG_YONHAP,
        "description":(
            "연합뉴스 2026-10-20 09:36 KST와 뉴스1 09:34 KST가 청와대의 10월 20일 "
            "보도자료를 인용해 2026-10-23 규제합리화위원회 제2차 전체회의 개최 예정이라고 전했다. "
            "로봇·반도체·AI 데이터센터·자율주행·바이오 산업의 규제 해소 방향을 부처별로 "
            "발표·논의하며 국무조정실은 메가프로젝트와 5극3특 성장엔진 지원 방향을 보고한다. "
            "창업기업 규제·행정서류 개선과 민간위원 토론도 예정됐다. "
            "KTV 생중계 예정, 참석 약 100명으로 보도된다. "
            "이것은 정부 발표를 인용한 회의 일정이며 로봇 실증특례·제품 인증·AI 데이터센터 "
            "전력접속 규정이 이미 변경됐다는 뜻이 아니다. "
            "세부 시행령·시행일·예산액·특정 수혜기업/로봇 납품계약은 아직 제시되지 않았다. "
            "국무조정실 4월 첫 회의 공식 보도자료에서 위원회의 법적 구조가 확인됐지만 "
            "이번 10월 회의 청와대 보도자료 원문은 직접 확보하지 못했다."
        ),
        "source":"연합뉴스",
        "published":"2026-10-20T00:36:00+00:00",
        "direct_recovery":True,
        "kreg_oct23_agenda":True,
    }]


# Wrap only the final active Python route. Leave older lanes, state and bot as-is.
_s24h_old_query=base.query_news
_s24h_old_group=base.topic_group
_s24h_old_score=base.score
_s24h_old_category=base.category
_s24h_old_meaning=base.meaning
_s24h_old_risk=base.risk
_s24h_old_verification=base.verification
_s24h_old_title=base.clean_title
_s24h_old_tag=base.tag_for
_s24h_old_key=base.key
_s24h_old_select=base.select_diverse


def _s24h_query(q: str) -> list[dict]:
    if q==S24H_20261020_RECOVERY:
        return _s24h_recovery()
    if q==KREG_OCT23_RECOVERY:
        return _kreg_oct23_recovery()
    return _s24h_old_query(q)


def _s24h_group(t: str) -> str|None:
    if _s24h_match(t):
        return "samsung_24h_rx"
    if _kreg_oct23_match(t):
        return "robot_reg_oct23"
    return _s24h_old_group(t)


def _s24h_score(item: dict) -> int:
    t=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
    group=_s24h_group(t)
    if group=="samsung_24h_rx":
        return {
            "reported_supervised_field_test":49,
            "official_verified_uptime":85,
            "official_ces_demonstration":77,
            "official_customer_contract":90,
            "background":0
        }.get(_s24h_stage(item),0)
    if group=="robot_reg_oct23":
        return {
            "announced_meeting_agenda":50,
            "official_specific_measure_adopted":90,
            "background":0
        }.get(_kreg_oct23_stage(item),0)
    return _s24h_old_score(item)


def _s24h_category(t: str, group: str) -> str:
    if group=="samsung_24h_rx":
        if S24H_CONTRACT.search(t) and not re.search(r"계약\s*(?:검토|예정|미정)|미확정",t):
            return "삼성전자 RX · 로봇 정식 고객계약·양산 출하"
        if S24H_OFFICIAL_UPTIME.search(t) and not S24H_NOT_CONFIRMED.search(t):
            return "삼성전자 RX · 24시간 무인 연속가동 공식 검증"
        if S24H_CES_OFFICIAL.search(t) and not S24H_NOT_CONFIRMED.search(t):
            return "삼성전자 RX · CES 2027 제품 공개 공식확인"
        return "삼성전자 RX · 24시간 운용 목표 현장검증 보도"
    if group=="robot_reg_oct23":
        if KREG_IMPLEMENTED.search(t) and not KREG_NEGATION.search(t):
            return "정부 규제합리화위 · 23일 구체 제도변경 공식의결"
        return "정부 규제합리화위 · 10월 23일 개최 예고"
    return _s24h_old_category(t,group)


def _s24h_meaning(cat: str) -> str:
    if cat=="삼성전자 RX · 24시간 운용 목표 현장검증 보도":
        return (
            "중앙일보 10/20 보도에 따르면 삼성전자 RX사업추진실이 우면동에서 이족보행 "
            "휴머노이드로 물류·제조 반복 작업을 시험 중이며 3교대 모니터링을 언급했습니다. "
            "24시간 연속 무인 자율운전·가동률·작업 성공률의 실제 수치가 공개된 것은 아닙니다. "
            "CES 2027(2027-01-06~09) 출품은 검토이며 공식 확정되지 않았습니다. "
            "7월 RX 조직 정비·6월 구미 생산라인 계획보다 구체적인 기술검증 진행 보도지만, "
            "양산·납품·매출이 발생했다고 해석하지 않습니다."
        )
    if cat=="삼성전자 RX · 24시간 무인 연속가동 공식 검증":
        return (
            "삼성전자가 장시간 무인 가동·연속 작업 검증을 직접 공개한 별도 단계입니다. "
            "실제 가동률, 작업 건수·실패 복구·배터리 교체·점검시간·사람 개입률을 "
            "검산한 후 연간 납품대수×검증단가로 매출 전환을 확인합니다."
        )
    if cat=="삼성전자 RX · CES 2027 제품 공개 공식확인":
        return (
            "기존 'CES 출품 검토' 보도에서 삼성전자의 공식 시연·공개로 단계가 올라갔습니다. "
            "현장 시연의 원격지원·자율성, 실제 작업 성공률 및 양산 계약은 별도 검증해야 합니다."
        )
    if cat=="삼성전자 RX · 로봇 정식 고객계약·양산 출하":
        return (
            "제조·물류 시험에서 유상 계약·완제품 출하 단계로 올라간 경우입니다. "
            "이번 계약 제품·금액·실제 고객·검수 시점·반복 유지보수 등을 분리해서 확인합니다."
        )
    if cat=="정부 규제합리화위 · 10월 23일 개최 예고":
        return (
            "청와대가 10/20 안내한 10/23 규제합리화위원회 제2차 회의 일정입니다. "
            "로봇·반도체·AI 데이터센터·자율주행·바이오 의제를 다루지만 "
            "안전·실증·인증 규정이 이미 개정되거나 예산이 배정됐다는 뜻은 아닙니다. "
            "23일 실제 의결·공포·시행일·조달 요건과 적용 기업을 분리해 추적합니다."
        )
    if cat=="정부 규제합리화위 · 23일 구체 제도변경 공식의결":
        return (
            "정부 1차자료에서 규제특례·인허가·인증 등 구체 조치가 최종 의결된 "
            "별도 단계입니다. 적용 대상, 법적 효력과 시행일, 유예조건, "
            "예산·시설 설치비·발주처·기업 매출 시차를 각각 검증합니다."
        )
    return _s24h_old_meaning(cat)


def _s24h_risk(cat: str) -> str:
    if cat.startswith("삼성전자 RX ·"):
        return (
            "최대 실패 경로는 사내 데모가 장시간 반복 작업의 가동률·"
            "무인 작업 성공률·안전인증·교체부품비를 통과하지 못해 고객 배치가 늦어지는 것입니다. "
            "24시간 99% 가동률도 하루 정지 14.4분이 허용되는 가정일 뿐 "
            "실측치가 아니며, 실제 24시간 무중단 완성은 별도입니다. "
            "6~12개월 위험 구간에 배터리·발열·낙상/충돌·"
            "고장복구·보증충당금, 작업 성공률·사람 개입률을 확인합니다."
        )
    if cat.startswith("정부 규제합리화위 ·"):
        return (
            "가장 큰 역풍은 23일 회의가 개선 방향 발표에 그치고 법령개정·"
            "산업현장 안전인증·실증특례·지방조례·인허가까지 수개월 지연되는 것입니다. "
            "특정 산업 실증 1건 승인과 전 산업 규제해소도 다릅니다. "
            "6~12개월 동안 관보·부처별 시행일·조건부 안전요원·"
            "보험·안전책임·기업 발주/검수까지 확인합니다."
        )
    return _s24h_old_risk(cat)


def _s24h_verification(item: dict,group: str,t: str) -> str:
    if group=="samsung_24h_rx":
        stage=_s24h_stage(item)
        if stage=="reported_supervised_field_test":
            return (
                "중앙일보 10/20 기사 색인·유진투자증권 인용 기사 대조 / "
                "삼성 공식 7월 RX 조직·6월 구미 로봇 라인 계획과 구분 / "
                "원문 직접 열람 제한 / 24시간 무인 가동 KPI·CES 출품 공식 미확정"
            )
        return "삼성전자 직접 자료 우선 / 검증일·작업 KPI·실제 출하·매출 별도 확인"
    if group=="robot_reg_oct23":
        stage=_kreg_oct23_stage(item)
        if stage=="announced_meeting_agenda":
            return (
                "청와대 10/20 발표를 인용한 연합뉴스·뉴스1 일치 / "
                "국무조정실 4월 위원회 공식 보도자료로 제도 확인 / "
                "10/20 청와대 원문 직접 열람 미확인 / 의결된 규제·시행일 없음"
            )
        return "국무조정실·청와대/관련부처 공식 원문, 조문·시행일 재검증"
    return _s24h_old_verification(item,group,t)


def _s24h_title(title: str,source: str) -> str:
    t=title+" "+source
    if _s24h_match(t):
        if source in S24H_COMPANY_SOURCES and S24H_OFFICIAL_UPTIME.search(t):
            return "삼성전자, 24시간 연속 무인 작업 성능 공식 검증"
        if source in S24H_COMPANY_SOURCES and S24H_CES_OFFICIAL.search(t):
            return "삼성전자, CES 2027 로봇 시연 공식 확정"
        return "삼성전자, 우면동 '24시간 근무 목표' 이족보행 로봇 시험 보도"
    if _kreg_oct23_match(t):
        return "10월 23일 규제합리화위원회 로봇·AI 규제 논의 예고"
    return _s24h_old_title(title,source)


def _s24h_tag(group: str) -> str:
    if group=="samsung_24h_rx":
        return "삼성전자 휴머노이드"
    if group=="robot_reg_oct23":
        return "로봇 규제합리화"
    return _s24h_old_tag(group)


def _s24h_key(item: dict) -> str:
    t=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
    group=_s24h_group(t)
    if group=="samsung_24h_rx":
        stage=_s24h_stage(item)
        return hashlib.sha256(f"samsung-rx|24h-humanoid|20261020|{stage}".encode()).hexdigest()
    if group=="robot_reg_oct23":
        stage=_kreg_oct23_stage(item)
        return hashlib.sha256(f"korean-regulatory-committee|20261023|robot-ai|{stage}".encode()).hexdigest()
    return _s24h_old_key(item)


def _s24h_select(items: list[dict],seen: set[str],force: bool,limit: int) -> list[dict]:
    selected=_s24h_old_select(items,seen,force,limit)
    candidates=items if force else [x for x in items if x.get("key") not in seen]
    for g in ("samsung_24h_rx","robot_reg_oct23"):
        item=next((x for x in candidates if x.get("group")==g and x.get("score",0)>=11),None)
        if item and not any(x.get("key")==item.get("key") for x in selected):
            selected=([item,*selected] if len(selected)<limit else [item,*selected[:-1]])
    return selected


base.query_news=_s24h_query
base.topic_group=_s24h_group
base.score=_s24h_score
base.category=_s24h_category
base.meaning=_s24h_meaning
base.risk=_s24h_risk
base.verification=_s24h_verification
base.clean_title=_s24h_title
base.tag_for=_s24h_tag
base.key=_s24h_key
base.select_diverse=_s24h_select
for _query in (
    S24H_20261020_RECOVERY,
    KREG_OCT23_RECOVERY,
    '(삼성전자 OR Samsung Electronics) (우면동 OR RX사업추진실 OR 로봇) '
    '(24시간 OR 연속가동 OR CES2027) (검증 OR 시험 OR 공식 공개 OR 가동률 OR 수주)',
    '(삼성전자 OR 삼성 RX) (이족보행 휴머노이드 OR 산업용 로봇) '
    '(2027 CES OR CES 2027 OR 24시간) (작업 성공률 OR 가동률 OR 양산 OR 고객)',
    '(규제합리화위원회 OR 규제합리화위) (10월23일 OR 제2차) '
    '(로봇 OR 반도체 OR AI 데이터센터) (의결 OR 발표 OR 시행일 OR 규제특례)',
):
    if _query not in base.QUERIES:
        base.QUERIES.append(_query)


# New 2026-10-19/20 disclosures: two distinct, properly sourced upgrades
# in the EXISTING watcher. Do not confuse 70% Atlas actuator/BOM with
# finished robot price or 50,000 HMG group deployments with Atlas orders.
# Do not confuse Eka's FULL $150m funding round with Samsung Next's stake
# or the known 2025 Rainbow RB-Y1 research-platform customer relationship
# with a new paid production agreement.
ATLAS_COST_20261019_RECOVERY = "DIRECT_BD_CFO_ATLAS_ACTUATOR_BOM_70_20261019"
EKA_ROBOTICS_20261020_RECOVERY = "DIRECT_EKA_SERIESA_150M_SAMSUNG_NEXT_20261020"
ATLAS_COST_FORTUNE = "https://fortune.com/2026/10/19/how-boston-dynamics-turning-robots-into-a-real-business-cfo/"
EKA_ROBOTICS_FUNDING = "https://ekarobotics.com/blog/eka-robotics-raises-150m-to-build-superhuman-intelligence-for-the-physical-world"
_ATLAS_BD_SOURCE = {"Boston Dynamics", "보스턴다이내믹스"}
_EKA_COMPANY_SOURCES = {"Eka Robotics", "EKA Robotics"}
_EKA_RESEARCH_SOURCE = {"Rainbow Robotics", "레인보우로보틱스"}
_ATLAS_BOM_70 = re.compile(r"70\s*%|seventy\s*percent|70퍼센트", re.I)
_ATLAS_AT_COST = re.compile(r"\bat\s+cost\b|원가\s*수준|원가에\s*공급", re.I)
_ATLAS_SIGNED_NEW = re.compile(
    r"(?:Atlas|아틀라스).{0,100}(?:purchase\s+order\s+signed|binding\s+order|"
    r"양산\s*구매계약\s*체결|확정\s*발주\s*계약\s*체결)", re.I
)
_EKA_FUNDING = re.compile(
    r"(?:Series\s*A|시리즈\s*A).{0,120}"
    r"(?:\$?\s*150\s*(?:m|million)|1억\s*5[,]?000만\s*달러|1억5000만달러)|"
    r"(?:\$?\s*150\s*(?:m|million)|1억\s*5[,]?000만\s*달러).{0,120}"
    r"(?:Series\s*A|시리즈\s*A)", re.I
)
_EKA_SIGNED_CUSTOMER = re.compile(
    r"(?:Eka|에카).{0,110}(?:정식\s*공급계약\s*체결|"
    r"paid\s*production\s*contract\s*signed|"
    r"paid\s*customer\s*deployment\s*completed|"
    r"유료\s*고객\s*계약\s*체결)", re.I
)
_EKA_RB_Y1_SIGNED = re.compile(
    r"(?:Eka|에카).{0,120}RB[-\s]?Y1.{0,120}"
    r"(?:신규\s*공급계약\s*체결|구매\s*계약\s*체결|"
    r"new\s*purchase\s*order\s*signed)", re.I
)


def _atlas_eka_identify(text: str) -> str:
    # Keep source in scoring; do not classify a generic Spot price story as
    # a confirmed Atlas bill-of-materials disclosure.
    if (re.search(r"Boston\s*Dynamics|보스턴다이내믹스",text,re.I)
            and re.search(r"Atlas|아틀라스",text,re.I)
            and re.search(r"actuat|액추에이터|구동\s*장치",text,re.I)
            and (_ATLAS_BOM_70.search(text) or _ATLAS_AT_COST.search(text)
                 or _ATLAS_SIGNED_NEW.search(text))):
        return "atlas_actuator_bom"
    if (re.search(r"\bEka\s*Robotics\b|EKA\s*로보틱스|에카로보틱스",text,re.I)
            and (re.search(r"Samsung\s*Next|삼성넥스트|시리즈\s*A|Series\s*A|"
                           r"150\s*million|RB[-\s]?Y1|로봇\s*손|dexterous",text,re.I)
                 or _EKA_SIGNED_CUSTOMER.search(text))):
        return "eka_dexterous_funding"
    return ""


def _atlas_eka_stage(item: dict, group: str) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("title","description"))
    source = item.get("source") or ""
    if group == "atlas_actuator_bom":
        if source in _ATLAS_BD_SOURCE and _ATLAS_SIGNED_NEW.search(text):
            return "official_binding_atlas_order"
        if source in _ATLAS_BD_SOURCE and _ATLAS_BOM_70.search(text) and _ATLAS_AT_COST.search(text):
            return "first_party_bom_verification"
        if source == "Fortune" and _ATLAS_BOM_70.search(text) and _ATLAS_AT_COST.search(text):
            return "fortune_cfo_interview"
        return "old_contract_or_reprint"
    if group == "eka_dexterous_funding":
        if source in _EKA_COMPANY_SOURCES and _EKA_SIGNED_CUSTOMER.search(text):
            return "official_paid_robot_customer"
        if source in _EKA_RESEARCH_SOURCE and _EKA_RB_Y1_SIGNED.search(text):
            return "official_new_rb_y1_order"
        if (source in _EKA_COMPANY_SOURCES
                and _EKA_FUNDING.search(text)
                and re.search(r"Samsung\s*Next|삼성넥스트",text,re.I)):
            return "eka_company_series_a"
        return "old_research_use_or_media_report"
    return ""


def _atlas_eka_recovery(q: str) -> list[dict]:
    if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,27):
        return []
    if q == ATLAS_COST_20261019_RECOVERY:
        return [{
            "title":"보스턴다이내믹스 CFO: Atlas 액추에이터 부품원가 70%, 현대모비스 원가 수준 공급",
            "description":(
                "2026-10-19 Fortune Amanda McMaster 보스턴다이내믹스 CFO 직접 인터뷰: "
                "Atlas 액추에이터는 전체 부품·재료비(BOM)의 약 70%이며 "
                "현대모비스가 원가 수준으로 생산해 공급할 계획이라고 설명했다. "
                "2026-01 현대모비스·Boston Dynamics Atlas 액추에이터 전략적 공급 협력 "
                "공식 발표의 60% 초과 원가 비중을 더 구체화한 경영진 발언이지 "
                "10월 신규 5만개 부품 주문·양산 납품 공시는 아니다. "
                "현대차·기아 시설 내 그룹 전체 로봇 약 50,000대 배치 구상을 언급했으나 "
                "Atlas 50,000대 확정 공급계약·납품 수량으로 볼 근거는 없다. "
                "Boston Dynamics Spot 기본 플랫폼은 100,000달러, "
                "옵션 포함 최고 300,000달러 수준이라는 설명이다. "
                "이는 Spot 가격이지 Atlas 판매가격이나 Atlas 액추에이터 단가가 아니다. "
                "현대모비스 액추에이터 실제 총원가·공급단가·영업이익·공급 대수는 미공개다. "
                "원가가정: 액추에이터가 부품원가 70%라면 액추에이터 단가 10% 하락 시 "
                "로봇 전체 부품원가가 약 7% 절감될 가능성이 있다(보조 계산). "
                "Spot 현금창출사업에는 Orbit 시설 데이터·점검 소프트웨어, "
                "Spot Care 유지보수 등이 포함되지만 이번 CFO 인터뷰에서 신규 유료계약을 "
                "발표한 것은 아니다. "
                "근거: Fortune CFO 직접 인터뷰와 현대모비스 2026-01 공식 협력 발표."
            ),
            "source":"Fortune",
            "link":ATLAS_COST_FORTUNE,
            "published":None,
            "direct_recovery":True,
            "executive_cost_disclosure":True,
        }]
    if q == EKA_ROBOTICS_20261020_RECOVERY:
        return [{
            "title":"Eka Robotics 시리즈 A 1억5000만달러 투자 유치, Samsung Next 참여 공식 발표",
            "description":(
                "2026-10-20 Eka Robotics 회사 공식자료: 150 million dollars "
                "Series A(1억5000만달러)는 전체 라운드 조달액이다. "
                "a16z와 F-Prime 공동 주도, Samsung Next 투자 참여 공식 명시. "
                "삼성넥스트의 개별 투자액과 투자 지분율은 미공개이며 "
                "삼성전자 로봇 매출·삼성넥스트 단독 1,991억원 투자가 아니다. "
                "Eka Robotics는 Vision-Force-Action(VFA) 모델과 힘 감지 로봇 손을 "
                "개발하며 시뮬레이션 강화학습으로 촉각·접촉 제어를 연구한다. "
                "회사 발표 정량: 시간당 1,500회 물체 조작, 자체 비교 인간 기준 "
                "시간당 600회로 약 2.5배. 독립 평가·현장 장기간 성공률·양품률은 미확인이다. "
                "2025-07 레인보우로보틱스 회사 제공 발표를 인용한 뉴스1·월간로봇기술 자료에서 "
                "미국 Eka가 RB-Y1 이동형 양팔 로봇을 실제 연구용으로 활용하며 "
                "dexterous hand 로봇 손 연구 프로젝트가 연결된다고 보도했다. "
                "이는 과거 제품 실제 채택·연구용 공급 이력으로, "
                "이번 새 라운드에서 RB-Y1을 추가 발주했다는 뜻은 아니다. "
                "자금은 로봇 모델·고객 배치 확대를 목적으로 하지만 개별 집행액은 미공개다. "
                "TechCrunch 2026-10-20 보도에 따르면 투자 후 기업가치 14억5000만달러 "
                "는 추정 투자평가액이지 매출이 아니다. "
                "실제 유료 고객·수익·반복 사용권 금액은 확인되지 않았다."
            ),
            "source":"Eka Robotics",
            "link":EKA_ROBOTICS_FUNDING,
            "published":None,
            "direct_recovery":True,
            "company_funding_confirmation":True,
        }]
    return []


_ae_prev_query=base.query_news
_ae_prev_group=base.topic_group
_ae_prev_score=base.score
_ae_prev_category=base.category
_ae_prev_meaning=base.meaning
_ae_prev_risk=base.risk
_ae_prev_verify=base.verification
_ae_prev_title=base.clean_title
_ae_prev_tag=base.tag_for
_ae_prev_key=base.key
_ae_prev_select=base.select_diverse


def _ae_query(q: str) -> list[dict]:
    if q in (ATLAS_COST_20261019_RECOVERY,EKA_ROBOTICS_20261020_RECOVERY):
        return _atlas_eka_recovery(q)
    return _ae_prev_query(q)


def _ae_group(text: str) -> str | None:
    g=_atlas_eka_identify(text)
    return g or _ae_prev_group(text)


def _ae_score(item: dict) -> int:
    t=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
    g=_atlas_eka_identify(t)
    if not g:
        return _ae_prev_score(item)
    stage=_atlas_eka_stage(item,g)
    return {
        "fortune_cfo_interview":55,
        "first_party_bom_verification":70,
        "official_binding_atlas_order":83,
        "eka_company_series_a":78,
        "official_paid_robot_customer":87,
        "official_new_rb_y1_order":85,
        "old_contract_or_reprint":0,
        "old_research_use_or_media_report":0,
    }.get(stage,0)


def _ae_category(text: str, group: str) -> str:
    # Renderer loses item['source'] on this call, so use content not source.
    if group=="atlas_actuator_bom":
        if _ATLAS_SIGNED_NEW.search(text):
            return "Atlas 액추에이터 · 양산 구매계약 직접확인"
        if (re.search(
                r"(?:보스턴다이내믹스|Boston\s*Dynamics).{0,100}"
                r"(?:Atlas|아틀라스).{0,100}(?:BOM|액추에이터|actuator)"
                r".{0,90}(?:공식\s*발표|official\s*announcement)",text,re.I
            ) and not re.search(r"Fortune|CFO\s*직접\s*인터뷰|CFO:",text,re.I)):
            return "Atlas 액추에이터 · 제조사 직접 원가비중 확인"
        return "Atlas 액추에이터 · CFO 부품원가 70% 발언"
    if group=="eka_dexterous_funding":
        if _EKA_SIGNED_CUSTOMER.search(text):
            return "Eka Robotics · 신규 유료 고객 공급계약"
        if _EKA_RB_Y1_SIGNED.search(text):
            return "Eka Robotics–레인보우로보틱스 · RB-Y1 신규 주문"
        return "Eka Robotics · 시리즈 A 공식 조달·삼성넥스트 참여"
    return _ae_prev_category(text,group)


def _ae_meaning(cat: str) -> str:
    if cat=="Atlas 액추에이터 · CFO 부품원가 70% 발언":
        return (
            "10/19 Fortune에 보스턴다이내믹스 CFO가 Atlas 부품·재료비 중 "
            "액추에이터 약 70%, 현대모비스 원가 수준 공급을 언급했습니다. "
            "1월 공식 공급 협력의 경제성 설명이 구체화된 것이지 신규 계약은 아닙니다. "
            "그룹 내 약 5만 대 배치는 여러 로봇의 계획이며 Atlas 5만 대 확정 발주가 아닙니다. "
            "Spot 판매가는 기본 10만달러~옵션 포함 30만달러이고 "
            "Atlas 가격·부품단가로 사용할 수 없습니다. "
            "액추에이터 가격이 10% 낮아지면 다른 조건 일정 시 Atlas BOM은 "
            "약 7% 낮아지는 원가 민감도(70%×10%)입니다."
        )
    if cat=="Eka Robotics · 시리즈 A 공식 조달·삼성넥스트 참여":
        return (
            "Eka 회사 공식 발표로 시리즈 A 전체 1억5000만달러를 조달하고 "
            "Samsung Next가 공동 투자자로 참여했습니다. 개별 투자액·지분율 미공개. "
            "Eka는 힘 감지 로봇손·시각-힘-행동 VFA 모델을 연구하며 "
            "시간당 1,500회 조작(인간 기준 600회)의 2.5배는 회사 주장 성능입니다. "
            "2025년 레인보우로보틱스 RB-Y1 실제 고객·손 연구 연결은 과거 확인된 "
            "연구용 채택 이력이지 신규 발주나 양산 수익이 아닙니다. "
            "반복 유료 고객·모델 사용료·실제 제품 성능 검증이 다음 단계입니다."
        )
    if cat=="Atlas 액추에이터 · 제조사 직접 원가비중 확인":
        return "공식 비용 구조가 CFO 보도 단계를 넘어 직접 확인된 단계입니다. 부품비 원가비중과 실제 매출·공급단가는 따로 검증합니다."
    if cat=="Atlas 액추에이터 · 양산 구매계약 직접확인":
        return "Atlas용 액추에이터 확정 구매계약이 별도로 공표된 단계입니다. 계약부품 수·단가·고객 검수·매출 인식을 확인합니다."
    if cat=="Eka Robotics · 신규 유료 고객 공급계약":
        return "Eka 회사가 실제 유료 로봇 손 고객 계약을 공개한 단계입니다. 연구·투자 관계와 구분해 수주금액·출하·반복매출을 검증합니다."
    if cat=="Eka Robotics–레인보우로보틱스 · RB-Y1 신규 주문":
        return "기존 2025년 RB-Y1 연구 활용과 달리 신규 공급계약이 회사 공식 확인된 단계입니다. 신규 발주 대수·금액·검수·매출을 확인합니다."
    return _ae_prev_meaning(cat)


def _ae_risk(cat: str) -> str:
    if cat.startswith("Atlas 액추에이터 · "):
        return (
            "70%는 부품·재료비 비중이며 전체 제조원가·소비자 판매가와 다릅니다. "
            "원가 수준 공급은 높은 부품 이익률을 보장하지 않습니다. "
            "감속기·모터·제어기 통합 수율, 토크 밀도, 발열·검사시간·"
            "현장 내구성, 안전·보험·고객 인수시험이 6~24개월 병목입니다. "
            "실패는 원가 절감에 비해 양품률이 낮고 그룹 고객의 실제 "
            "Atlas 설치가 늦어지는 것입니다. 조기 지표는 첫 양산 출하·"
            "고객 검수·부품 원가와 장기 가동률입니다."
        )
    if cat.startswith("Eka Robotics") or cat.startswith("Eka Robotics–"):
        return (
            "투자금은 제품 매출이 아닙니다. 삼성넥스트 참여를 삼성전자 전사 "
            "직접 공급계약이나 레인보우 RB-Y1 새 대량발주로 간주하면 안 됩니다. "
            "시뮬레이션에서 실제 로봇으로의 성능 이전, 힘 센서 품질·"
            "과잉 파지에 따른 제품 파손, 내구성·안전 인증·보험, "
            "반복 작업시 성능 저하가 6~12개월 위험요인입니다. "
            "시간당 1,500회는 회사 발표 조작속도이며 현장 장기 고객 "
            "성공률·가동률·계약 매출이 조기경보 지표입니다."
        )
    return _ae_prev_risk(cat)


def _ae_verify(item: dict,group: str,text: str) -> str:
    if group=="atlas_actuator_bom":
        return (
            "Fortune 10/19 보스턴다이내믹스 CFO 직접 인터뷰 + "
            "현대모비스 1월 공식 액추에이터 공급협력 교차확인. "
            "70%는 Atlas 부품·재료비 비중. Spot 가격·그룹 로봇 5만대 "
            "구상은 Atlas 부품 단가·확정 발주가 아님."
        )
    if group=="eka_dexterous_funding":
        return (
            "Eka Robotics 10/20 회사 자금유치 발표 직접 확인, "
            "TechCrunch 10/20 투자후 기업가치 교차 확인, "
            "레인보우로보틱스 2025년 회사자료 기반 RB-Y1 활용 보도 교차검증. "
            "Samsung Next 투자액·지분율·신규 RB-Y1 발주는 미공개."
        )
    return _ae_prev_verify(item,group,text)


def _ae_title(title: str,source: str) -> str:
    if re.search(r"\bEka\s*Robotics\b|EKA\s*로보틱스|에카로보틱스",title,re.I):
        if source in _EKA_COMPANY_SOURCES and _EKA_SIGNED_CUSTOMER.search(title):
            return "Eka Robotics 신규 유료 로봇 손 계약 공식 확인"
        if source in _EKA_RESEARCH_SOURCE and _EKA_RB_Y1_SIGNED.search(title):
            return "레인보우로보틱스, Eka용 RB-Y1 신규 발주 공식 확인"
        return "Eka Robotics 공식 1억5000만달러 조달·Samsung Next 투자 참여"
    if re.search(r"Boston\s*Dynamics|보스턴다이내믹스",title,re.I) and re.search(r"Atlas|아틀라스",title,re.I):
        if source in _ATLAS_BD_SOURCE and _ATLAS_SIGNED_NEW.search(title):
            return "보스턴다이내믹스, Atlas 액추에이터 정식 양산 발주 발표"
        return "보스턴다이내믹스 CFO: Atlas 액추에이터 BOM 약 70%·현대모비스 원가 공급"
    return _ae_prev_title(title,source)


def _ae_tag(group: str) -> str:
    if group=="atlas_actuator_bom":
        return "Atlas 원가"
    if group=="eka_dexterous_funding":
        return "로봇 손·자금조달"
    return _ae_prev_tag(group)


def _ae_key(item: dict) -> str:
    text=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
    g=_atlas_eka_identify(text)
    if g=="atlas_actuator_bom":
        stage=_atlas_eka_stage(item,g)
        return hashlib.sha256(f"boston-atlas|20261019|bom70|mobis-atcost|{stage}".encode()).hexdigest()
    if g=="eka_dexterous_funding":
        stage=_atlas_eka_stage(item,g)
        return hashlib.sha256(f"eka|20261020|seriesa150m|samsung-next|{stage}".encode()).hexdigest()
    return _ae_prev_key(item)


def _ae_select(items: list[dict],seen: set[str],force: bool,limit: int) -> list[dict]:
    chosen=_ae_prev_select(items,seen,force,limit)
    candidates=items if force else [x for x in items if x.get("key") not in seen]
    for g in ("atlas_actuator_bom","eka_dexterous_funding"):
        hit=next((x for x in candidates if x.get("group")==g and x.get("score",0)>=11),None)
        if hit and not any(x.get("key")==hit.get("key") for x in chosen):
            chosen=([hit,*chosen] if len(chosen)<limit else [hit,*chosen[:-1]])
    return chosen


base.query_news=_ae_query
base.topic_group=_ae_group
base.score=_ae_score
base.category=_ae_category
base.meaning=_ae_meaning
base.risk=_ae_risk
base.verification=_ae_verify
base.clean_title=_ae_title
base.tag_for=_ae_tag
base.key=_ae_key
base.select_diverse=_ae_select
base.OFFICIAL_OR_PRIMARY.update({"Eka Robotics","EKA Robotics","Boston Dynamics"})
base.TRUSTED.add("Fortune")
for _q in (
    ATLAS_COST_20261019_RECOVERY,EKA_ROBOTICS_20261020_RECOVERY,
    '(Boston Dynamics OR 보스턴다이내믹스) (Atlas OR 아틀라스) '
    '(Amanda McMaster OR CFO OR 맥마스터 OR 현대모비스) '
    '(actuator cost OR 70% OR 원가 OR first production shipments OR supply order)',
    '(Eka Robotics OR 에카로보틱스) (Samsung Next OR 삼성넥스트 OR '
    'Series A OR 1억5000만달러) (funding OR VFA OR dexterous hand OR robots)',
    '(Eka Robotics OR 에카로보틱스) (Rainbow Robotics OR 레인보우로보틱스 OR RB-Y1) '
    '(new order OR purchase contract OR 신규 공급계약 OR 추가 발주 OR customer deployment)',
):
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)


# Exactly one correction for Telegram message_id=249. The funding and CFO
# events have ALREADY been sent successfully; they must not be replayed merely
# because we corrected a source-code static FX conversion. Only correction
# is new. A single formatter remains responsible for all current USD=>KRW.
FX249_CORRECTION_RECOVERY = "DIRECT_TELEGRAM_249_FX_INCONSISTENCY_20261021"


def _fx249_correction() -> list[dict]:
    if base.NOW.astimezone(base.KST).date()>dt.date(2026,10,26):
        return []
    return [{
        "title":"정정: Telegram 249번 환율 혼용으로 Eka 투자금액 표시 차이 수정",
        "description":(
            "2026-10-21 직전 Telegram 249번 1번 EKA Robotics 전체 Series A "
            "1억5000만달러는 제목에 약 1,992억원, 본문에 약 1,991억원으로 "
            "서로 다르게 출력됐다. 원인은 새 알림 본문에 과거 조회 환율을 고정해 "
            "원화값을 적고 마지막 공통 환산 단계에서 신규 환율을 이용해 제목을 "
            "다시 계산한 데 있다. Spot 기본 10만달러·옵션 최고 30만달러 "
            "표시도 구 환율이 박혀 있었다. 같은 자금조달 사실을 다시 알리는 "
            "것이 아니라 출처 기준 불일치와 재발방지 수정 사실만 정정한다. "
            "Eka 전체 투자유치액과 Samsung Next 개별 투자액은 서로 다르며 "
            "후자는 여전히 비공개다. Spot 견적은 Atlas 가격이 아니다. "
            "후속 알림은 외화 원문만 소스에 보존하고 공통 환산기에서 "
            "검증된 당일 단일 환율로 즉시 원화 환산한다. "
            "1억~10억원 이하 달러 상품은 만원 단위까지 출력 정밀도를 개선했다."
        ),
        "source":"알림 운영검증 기록",
        "link":"https://github.com/qedgwangju-dot/khs-watch/actions/runs/39514218089",
        "published":None,
        "direct_recovery":True,
        "fx_correction_249":True,
    }]


_fx249_prev_query=base.query_news
_fx249_prev_group=base.topic_group
_fx249_prev_score=base.score
_fx249_prev_category=base.category
_fx249_prev_meaning=base.meaning
_fx249_prev_risk=base.risk
_fx249_prev_verify=base.verification
_fx249_prev_title=base.clean_title
_fx249_prev_tag=base.tag_for
_fx249_prev_key=base.key
_fx249_prev_select=base.select_diverse


def _fx249_query(q):
    if q==FX249_CORRECTION_RECOVERY:
        return _fx249_correction()
    return _fx249_prev_query(q)


def _fx249_group(text):
    if "정정: Telegram 249번" in text:
        return "alert_quality_fx_249"
    return _fx249_prev_group(text)


def _fx249_score(item):
    if item.get("fx_correction_249"):
        return 98
    return _fx249_prev_score(item)


def _fx249_category(text,group):
    if group=="alert_quality_fx_249":
        return "알림 정정 · 249번 외화 환산 단일화"
    return _fx249_prev_category(text,group)


def _fx249_meaning(cat):
    if cat=="알림 정정 · 249번 외화 환산 단일화":
        return (
            "Telegram 249번에서 EKA 시리즈 A 투자 총액 1억5000만달러가 "
            "제목 약 1,992억원·본문 약 1,991억원으로 달랐습니다. "
            "하나의 환율로 계산하지 않은 출력 오류입니다. "
            "수정 후에는 기준 외화액만 보존하고 공통 환율 검증 단계가 "
            "같은 실행에서 단 한 번 원화 환산합니다. "
            "Spot 기본 10만달러·옵션 최고 30만달러 역시 같은 환율을 "
            "쓰며 1억~10억원 금액의 만원단위 표기를 복구했습니다. "
            "이미 보낸 EKA 투자 확정·Atlas 원가 발언 자체는 유지되고 "
            "신규 부품 발주·양산 매출이 발생했다는 뜻은 아닙니다."
        )
    return _fx249_prev_meaning(cat)


def _fx249_risk(cat):
    if cat=="알림 정정 · 249번 외화 환산 단일화":
        return (
            "출처별 고정 환율과 마지막 실시간 환산기를 동시에 쓰면 "
            "같은 달러금액의 원화 표시가 달라집니다. "
            "원화 환산은 발송 직전 공통 단계로 일원화했고 "
            "모의 환율 2개·중복 이벤트 회귀검사를 추가했습니다."
        )
    return _fx249_prev_risk(cat)


def _fx249_verify(item,group,text):
    if group=="alert_quality_fx_249":
        return (
            "Telegram 249 실제 아티팩트 제목·본문·환율 기준 불일치 확인 / "
            "외화 원문 보존·단일 환율 변환·만원 단위 정밀도 재검증 / "
            "신규 계약 아님"
        )
    return _fx249_prev_verify(item,group,text)


def _fx249_title(title,source):
    if title.startswith("정정: Telegram 249번"):
        return "정정: Telegram 249번 Eka 투자금 1억원 표시차이·Spot 환산 기준 일원화"
    return _fx249_prev_title(title,source)


def _fx249_tag(group):
    if group=="alert_quality_fx_249":
        return "환율 환산 정정"
    return _fx249_prev_tag(group)


def _fx249_key(item):
    if item.get("fx_correction_249"):
        return hashlib.sha256(b"physicalai|telegram249|20261021|fx-one-rate-fix").hexdigest()
    return _fx249_prev_key(item)


def _fx249_select(items,seen,force,limit):
    chosen=_fx249_prev_select(items,seen,force,limit)
    candidates=items if force else [x for x in items if x.get("key") not in seen]
    correction=next((x for x in candidates if x.get("group")=="alert_quality_fx_249"
                     and x.get("score",0)>=11),None)
    if correction and not any(x.get("key")==correction.get("key") for x in chosen):
        chosen=([correction,*chosen] if len(chosen)<limit else
                [correction,*chosen[:-1]])
    return chosen


base.query_news=_fx249_query
base.topic_group=_fx249_group
base.score=_fx249_score
base.category=_fx249_category
base.meaning=_fx249_meaning
base.risk=_fx249_risk
base.verification=_fx249_verify
base.clean_title=_fx249_title
base.tag_for=_fx249_tag
base.key=_fx249_key
base.select_diverse=_fx249_select
if FX249_CORRECTION_RECOVERY not in base.QUERIES:
    base.QUERIES.append(FX249_CORRECTION_RECOVERY)



# Oct-21 Samsung Electro-Mechanics Mexico camera plant and Samsung
# Electronics RX leadership visit: distinct evidence gates and semantic keys.
SAMSUNG_ROBOT_OCT21_RECOVERY="DIRECT_SAMSUNG_ROBOT_OCT21_"
SAMSUNG_ROBOT_OCT21_EVENTS={
 "sem_mexico": {
   "group":"sem_mexico_camera_robot",
   "source":"아시아투데이",
   "title":"삼성전기 멕시코 카메라 모듈 설비 재개·2026년 말 양산 목표",
   "link":"https://www.asiatoday.co.kr/kn/view.php?key=20261021010007137",
   "description":(
     "2026-10-21 아시아투데이 보도: 삼성전기가 멕시코 케레타로 "
     "자동차·휴머노이드 카메라 모듈 공장 설비를 구축 중이며 "
     "2023년 추진 후 일시 보류됐던 투자 재개, 2026년 말 양산 목표. "
     "삼성전기 관계자는 계획대로 진행 중이라고 설명했다. "
     "반기보고서 멕시코법인 대여 한도 4,000만달러와 상반기 누적 실행 "
     "800만달러는 실제 지출·차입과 구분해 확인해야 한다. "
     "자동차용 카메라 기존 매출·수주와 휴머노이드 공급은 별개다. "
     "Tesla Optimus V3 부품 공급 준비는 언론 전언이며 V3 확정 고객 "
     "발주·휴머노이드 첫 출하·양산 직행수율·매출 인식은 미확인이다. "
     "추가 생산비용은 공장건설·전력·광학·자동화·검사·냉각·안전·소방 "
     "등으로 나눠 실제 신규시설투자 공시·설비 검수·출하 시 확인한다."
   ),
   "stage":"reported_buildout",
 },
 "samsung_rx_visit": {
   "group":"samsung_rx_leadership_visit",
   "source":"머니투데이",
   "title":"이재용, 삼성전자 RX사업추진실 현장점검 다음 주 방문 예정 보도",
   "link":"https://www.mt.co.kr/index.php/industry/2026/10/21/2026102111544397850",
   "description":(
     "2026-10-21 머니투데이 단독 보도: 이재용 삼성전자 회장이 "
     "이르면 다음 주 우면동 RX사업추진실을 방문해 로봇 팔·손 "
     "정밀조작 시연 및 CES 2027 준비를 점검할 예정이라고 전했다. "
     "2026년 7월 조직 신설·기존 로봇 기술 검증은 별개 과거 사실이다. "
     "10월 21일 현재 실제 방문·시연·고객계약·양산·공장배치는 "
     "확인되지 않았다. 경영진 방문 예정 기사만으로 신규 실적 또는 "
     "공식 일정 확정 알림을 발생시키지 않는다."
   ),
   "stage":"visit_planned_media",
 },
}
_SRO_PRIMARY_SEM={"삼성전기","Samsung Electro-Mechanics"}
_SRO_PRIMARY_SAMSUNG={"삼성전자","Samsung Electronics"}
_SRO_SEM_ID=re.compile(r"삼성전기|Samsung\s*Electro[-\s]*Mechanics",re.I)
_SRO_RX_ID=re.compile(r"삼성전자|Samsung\s*Electronics|이재용",re.I)
_SRO_MEXICO=re.compile(r"멕시코|Mexico|케레타로|Quer[eé]taro",re.I)
_SRO_CAMERA=re.compile(r"카메라\s*모듈|camera\s*module",re.I)
_SRO_RX=re.compile(r"RX사업추진실|우면동.{0,50}(?:로봇|RX)|Robotics\s*eXperience",re.I)
_SRO_VISIT_DONE=re.compile(
 r"(?:실제|공식|현장)\s*(?:방문|점검)\s*(?:완료|실시|마쳤)|"
 r"방문해.{0,50}(?:시연|점검)\s*(?:확인|마쳤|실시)|"
 r"(?:visited|completed)\s+(?:the\s+)?RX\s+(?:robotics|lab)",re.I)
_SRO_SEM_ACTUAL=re.compile(
 r"(?:실제|첫|초도)\s*(?:양산|생산|출하)\s*(?:개시|시작|완료)|"
 r"(?:양산|생산)\s*(?:시작|개시|가동)\s*(?:공식\s*)?(?:확인|발표)|"
 r"started\s+production|first\s+shipments",re.I)
_SRO_SEM_CONTRACT=re.compile(
 r"(?:Optimus|옵티머스|휴머노이드).{0,80}(?:정식|확정)\s*(?:공급|구매)\s*계약\s*체결|"
 r"(?:signed|confirmed)\s+(?:Optimus|humanoid)\s+(?:camera\s*)?(?:supply|purchase)\s+contract",re.I)

def _sro_group(text):
    if _SRO_SEM_ID.search(text) and _SRO_MEXICO.search(text) and _SRO_CAMERA.search(text):
        return "sem_mexico_camera_robot"
    if _SRO_RX_ID.search(text) and _SRO_RX.search(text) and re.search(r"이재용|Lee\s*Jae[-\s]*yong",text,re.I):
        return "samsung_rx_leadership_visit"
    return ""

def _sro_stage(item,group):
    text=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
    source=item.get("source") or ""
    if group=="sem_mexico_camera_robot":
        if source in _SRO_PRIMARY_SEM and _SRO_SEM_CONTRACT.search(text) and not re.search(r"검토|논의|준비|예정|미확정",text,re.I):
            return "official_robot_contract"
        if source in _SRO_PRIMARY_SEM and _SRO_SEM_ACTUAL.search(text) and not re.search(r"예정|목표|계획|전망|추진",text,re.I):
            return "official_production"
        if source=="아시아투데이" and re.search(r"설비.{0,40}구축|투자.{0,25}재개|양산.{0,20}목표",text,re.I):
            return "reported_buildout"
        return "background"
    if group=="samsung_rx_leadership_visit":
        if source in _SRO_PRIMARY_SAMSUNG and _SRO_VISIT_DONE.search(text) and not re.search(r"예정|전망|계획|이르면",text,re.I):
            return "official_visit_done"
        return "visit_planned_media"
    return "background"

def _sro_recovery(which):
    # Single historical baseline. No fabricated precise time.
    if base.NOW.astimezone(base.KST).date()>dt.date(2026,10,26):
        return []
    x=SAMSUNG_ROBOT_OCT21_EVENTS[which]
    return [{
      "title":x["title"],"description":x["description"],"link":x["link"],
      "source":x["source"],"published":None,"direct_recovery":True,
      "sro_event":which,"sro_expected":x["stage"],
    }]

_sro_prev_query=base.query_news
_sro_prev_group=base.topic_group
_sro_prev_score=base.score
_sro_prev_category=base.category
_sro_prev_meaning=base.meaning
_sro_prev_risk=base.risk
_sro_prev_verify=base.verification
_sro_prev_title=base.clean_title
_sro_prev_tag=base.tag_for
_sro_prev_key=base.key
_sro_prev_select=base.select_diverse

def _sro_query(q):
    for n in SAMSUNG_ROBOT_OCT21_EVENTS:
        if q==SAMSUNG_ROBOT_OCT21_RECOVERY+n:
            return _sro_recovery(n)
    return _sro_prev_query(q)

def _sro_group_wrap(text):
    return _sro_group(text) or _sro_prev_group(text)

def _sro_score(item):
    text=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
    g=_sro_group(text)
    if not g:return _sro_prev_score(item)
    stage=_sro_stage(item,g)
    if item.get("sro_expected") and stage!=item["sro_expected"]:
        return 0
    return {
       "reported_buildout":50,
       "official_production":78,
       "official_robot_contract":86,
       "official_visit_done":66,
       "visit_planned_media":0,
       "background":0
    }.get(stage,0)

def _sro_category(text,group):
    labels={
      "sem_mexico_camera_robot":"삼성전기 · 멕시코 카메라 생산설비·로봇 공급 준비 보도",
      "samsung_rx_leadership_visit":"삼성전자 · RX사업추진실 방문 예정 보도",
    }
    if group in labels:
        return labels[group]
    return _sro_prev_category(text,group)

def _sro_meaning(cat):
    if cat.startswith("삼성전기 · 멕시코"):
        return (
          "2023년 추진·투자 보류 이후 멕시코 카메라 모듈 공장 설비 구축 "
          "재개, 2026년 말 양산 목표가 신규 단계입니다. 자동차용 매출 "
          "확대 가능성과 Optimus V3 등 휴머노이드용 초도 공급 기대는 "
          "분리합니다. 반기보고서상 4,000만달러 법인 대여 한도와 "
          "상반기 누적 800만달러 실행은 공장 전체 설비투자 확정액과 "
          "다릅니다. 휴머노이드 고객 주문·초도 출하·인식 매출은 미확인입니다."
        )
    if cat.startswith("삼성전자 · RX사업추진실"):
        return (
          "이재용 회장의 RX 방문은 10/21 현재 '다음 주 예정'이라는 "
          "언론 보도이며 실제 현장 점검과 로봇 손 정밀작업 시연은 "
          "향후 회사 발표·현장 확인이 필요한 별도 단계입니다. "
          "CES 2027은 기존 개발 시간표로 신규 수주·양산이 아닙니다."
        )
    return _sro_prev_meaning(cat)

def _sro_risk(cat):
    if cat.startswith("삼성전기 · 멕시코"):
        return (
         "가장 현실적인 실패 경로는 연말 설비 시운전·카메라 캘리브레이션·"
         "고온 동작 검사·고객 품질승인·수율 확보가 늦어지는 경우입니다. "
         "6~12개월 첫 출하 여부와 광학 검사시간·재작업률·불량률, "
         "환율·관세·원산지 조건을 추적합니다. "
         "Tesla 자동차 카메라 계약과 Optimus V3 직접 로봇 계약은 다른 사건입니다."
        )
    if cat.startswith("삼성전자 · RX사업추진실"):
        return (
          "경영진 현장 방문이 실현되어도 손 정밀조작 성공률·반복 시연·"
          "현장 안전인증·가동률·개당 제조원가 개선과 다릅니다. "
          "6~12개월 실제 방문·시연·CES 공개와 고객 유상 발주를 분리합니다."
        )
    return _sro_prev_risk(cat)

def _sro_verify(item,group,text):
    if group=="sem_mexico_camera_robot":
        return (
          "아시아투데이 10/21 업계 취재·회사 관계자 진술, "
          "삼성전기 공식 전장 카메라 제품 및 2분기 실적자료 교차확인. "
          "멕시코 대여 한도·누적 실행액은 기사상 반기보고서 인용, "
          "공장 총투자·Optimus 직접 공급·현지 양산 완료는 미확인."
        )
    if group=="samsung_rx_leadership_visit":
        return (
          "머니투데이 10/21 방문 예정 취재 · 삼성전자 7월 RX 조직과 "
          "10/19 개발현황 보도 교차확인 · 방문 완료 공식자료 미확인."
        )
    return _sro_prev_verify(item,group,text)

def _sro_title(title,source):
    return title if "삼성전기 멕시코 카메라" in title else _sro_prev_title(title,source)

def _sro_tag(group):
    if group=="sem_mexico_camera_robot":return "삼성전기 멕시코 카메라"
    if group=="samsung_rx_leadership_visit":return "삼성전자 RX 점검"
    return _sro_prev_tag(group)

def _sro_key(item):
    text=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
    g=_sro_group(text)
    if not g:return _sro_prev_key(item)
    stage=_sro_stage(item,g)
    return hashlib.sha256(
       f"samsung-robot|20261021|{g}|{stage}".encode()
    ).hexdigest()

def _sro_select(items,seen,force,limit):
    chosen=_sro_prev_select(items,seen,force,limit)
    candidates=items if force else [x for x in items if x.get("key") not in seen]
    hit=next((x for x in candidates if x.get("group")=="sem_mexico_camera_robot"
              and x.get("score",0)>=11),None)
    if hit and not any(x.get("key")==hit.get("key") for x in chosen):
        chosen=([hit,*chosen] if len(chosen)<limit else [hit,*chosen[:-1]])
    # Two Google News URLs may describe the same outlet story and stage.
    # Suppress only identical rendered titles, outlets, event groups and minutes.
    def _delivery_signature(item):
        source = str(item.get("source") or "")
        title = base.clean_title(str(item.get("title") or ""), source)
        normalize = lambda value: " ".join(str(value or "").split()).casefold()
        return (
            normalize(item.get("group")),
            normalize(title),
            normalize(source),
            str(item.get("published") or "")[:16],
        )

    delivery_signatures = set()
    unique = []
    for item in chosen:
        signature = _delivery_signature(item)
        if signature in delivery_signatures:
            continue
        delivery_signatures.add(signature)
        unique.append(item)

    # Keep the original number of slots when a distinct candidate remains.
    if len(unique) < len(chosen):
        for item in candidates:
            if len(unique) >= len(chosen):
                break
            if any(other.get("key") == item.get("key") for other in unique):
                continue
            signature = _delivery_signature(item)
            if signature in delivery_signatures:
                continue
            delivery_signatures.add(signature)
            unique.append(item)
    return unique

base.query_news=_sro_query
base.topic_group=_sro_group_wrap
base.score=_sro_score
base.category=_sro_category
base.meaning=_sro_meaning
base.risk=_sro_risk
base.verification=_sro_verify
base.clean_title=_sro_title
base.tag_for=_sro_tag
base.key=_sro_key
base.select_diverse=_sro_select
for _q in (
 SAMSUNG_ROBOT_OCT21_RECOVERY+"sem_mexico",
 SAMSUNG_ROBOT_OCT21_RECOVERY+"samsung_rx_visit",
 '(삼성전기 OR Samsung Electro-Mechanics) (멕시코 OR Queretaro) '
 '(카메라모듈 OR camera module) (공장 양산 OR 설비 재개 OR 공식 출하 OR 생산 개시)',
 '(이재용 OR Lee Jae-yong) (RX사업추진실 OR 서울R&D캠퍼스) '
 '(현장 방문 완료 OR 정밀 작업 시연 OR 공식 일정)',
):
    if _q not in base.QUERIES:base.QUERIES.append(_q)



# 2026-10-21..23 evidence-locked milestone upgrades on the EXISTING robot route.
# These are dated initial changes, not a free license to re-alert press rewrites.
# No new workflow, Telegram destination, state file or scheduling configuration.
R26_PREFIX = "DIRECT_ROBOT_OCT25_MILESTONE_"
R26_EVENTS = {
    "tesla_fremont": {
        "group": "tesla_optimus_q3_fremont",
        "stage": "production_quality_started",
        "source": "Tesla SEC filing",
        "title": "테슬라 Optimus 프리몬트 양산용 라인 생산 개시 · 판매량 미확인",
        "link": "https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/exhibit9914.htm",
        "description": (
            "2026-10-21 Tesla Q3 2026 공식 실적자료: Optimus production began "
            "on high-volume lines at Fremont; first production-quality units. "
            "이는 로봇 양산급 제조공정의 생산 개시이지 주당 2만대 달성이나 "
            "외부 고객 인도가 아니다. 생산 대수, 수율, 손의 수명, 실제 무인 "
            "작업 성공률, 고객 구매계약과 인식 매출은 미공개다. "
            "Optimus Academy 1만~2만대와 AI5 2027년 4월경 탑재, "
            "2027년 말 외부 판매는 어닝콜 전망과 계획으로 분리한다. "
            "테슬라의 2026년 CAPEX 공시 전망은 250억달러 초과에서 "
            "200억달러 초과로 낮아졌다. 새로운 확정 지출액 200억달러는 "
            "아니며 2026년 1~9월 실제 자본지출은 130억1천만달러다. "
            "한국 부품 기업의 테슬라 직접 공급계약은 별도 공식 검증 필요."
        ),
        "category": "테슬라 · 프리몬트 Optimus 양산 품질 생산 개시",
        "meaning": (
            "대량생산용 설비에서 첫 양산 품질 로봇을 제조하기 시작했습니다. "
            "2026년 설비투자 하한 전망은 250억달러(약 33조1,150억원) 초과에서 "
            "200억달러(약 26조4,920억원) 초과로 조정됐습니다. "
            "현재 로봇 생산·판매 대수와 외부 고객 매출은 확인되지 않았습니다. "
            "주당 생산량→수율→고객 검증→유상 인도의 순서로 추적합니다."
        ),
        "risk": (
            "로봇 손·액추에이터 수명, 실작업 실패·안전, 생산 수율과 검사시간이 "
            "병목입니다. 1~2만대 학습용 물량과 주당 2만대는 실적이 아닌 목표이며, "
            "AI5 및 외부 인도 일정 지연은 6~12개월 조기경보입니다."
        ),
    },
    "lge_hsb": {
        "group": "lge_nvidia_hsb_robot_sensing",
        "stage": "official_hsb_product_unveiled",
        "source": "LG이노텍",
        "title": "LG이노텍·엔비디아, HSB 탑재 300만 화소 카메라·MVS 공식 공개",
        "link": "https://news.lginnotek.com/1675",
        "description": (
            "2026-10-22 LG이노텍 공식 보도자료. GTC Berlin에서 NVIDIA "
            "Holoscan Sensor Bridge(HSB) 적용 300만 화소 카메라 및 "
            "멀티모달 비전 시스템(MVS)을 공개했다. 카메라·라이다·레이더 "
            "센서데이터를 CPU를 우회해 AI 컴퓨터로 전달한다. "
            "LG이노텍의 기존 북미 로봇 고객용 카메라 모듈 양산과 "
            "새 HSB 제품 양산은 다른 사실이다. "
            "2027년 CES·GTC 추가 솔루션 공개는 계획이고, "
            "이번 HSB 제품의 실명 고객, 양산 출하 물량, 매출은 미공개다."
        ),
        "category": "LG이노텍·엔비디아 · HSB 센싱 제품 공식 공개",
        "meaning": (
            "300만 화소 카메라와 카메라·라이다·레이더 통합 인지장치를 "
            "NVIDIA HSB에 연결한 실물 제품을 공개했습니다. "
            "기존 북미 로봇 고객 카메라 양산은 확인되지만 HSB 신제품의 "
            "확정 공급계약·납품대수·매출은 분리해 확인해야 합니다."
        ),
        "risk": (
            "센서 동기화·지연시간·발열·전력·정렬·신뢰성·고객 인증이 병목입니다. "
            "2027년 신제품 공개 계획을 2026년 고객 양산으로 승격하지 않습니다."
        ),
    },
    "mobilint_lge": {
        "group": "mobilint_lge_humanoid_npu",
        "stage": "government_rd_selected",
        "source": "한국산업기술기획평가원 보도자료 소개",
        "title": "모빌린트·LG전자·노타 휴머노이드용 NPU 국책 연구개발 과제 확인",
        "link": "https://www.keit.re.kr/board.es?act=view&bid=0007&list_no=128498&mid=a10201010000",
        "description": (
            "2026-10-22 보도와 한국산업기술기획평가원의 기사 소개. "
            "산업통상부 K-온디바이스 AI 반도체 기술개발사업의 "
            "휴머노이드용 AI 가속기 세부과제. 모빌린트가 NPU·가속기 "
            "모듈·소프트웨어를 개발하며 LG전자 휴머노이드에 적용 검증을 "
            "계획하고 노타가 AI 모델 최적화에 참여한다. "
            "연구개발 선정은 로봇 양산 납품 또는 유상 매출이 아니다. "
            "세부 과제 보조금과 고객 계약액은 확인되지 않았다."
        ),
        "category": "모빌린트·LG전자·노타 · 휴머노이드 NPU 연구개발 단계",
        "meaning": (
            "LG전자 수요 로봇 환경과 국내 NPU·모델 최적화 기업이 연결된 "
            "구체적인 국책 연구개발입니다. 향후 샘플→전력·발열 검증→"
            "로봇 제어 신뢰성→고객 승인→유상 양산계약 순서로 확인합니다."
        ),
        "risk": (
            "배터리 전력한도, NPU 발열·추론 지연, VLM·VLA 동시 실행, "
            "보행진동 신뢰성, 실시간 안전제어가 실패모드입니다. "
            "LG전자 시험 완료 전까지 매출 확정으로 보지 않습니다."
        ),
    },
    "nvidia_flora": {
        "group": "nvidia_flora_robot_data",
        "stage": "official_open_model_release",
        "source": "NVIDIA Research",
        "title": "NVIDIA Flora 로봇 학습자료 자동 주석 기술 공식 공개",
        "link": "https://research.nvidia.com/labs/gear/flora/",
        "description": (
            "NVIDIA Research 공식 Flora 공개. 로봇 학습용 영상에 "
            "시간표지 설명, 행동 성공 여부, 실패 원인 등을 주석화하는 "
            "오픈 모델 묶음이다. 회사는 GB300 가속기 512개를 활용해 "
            "하루 영상 20만 시간에 주석을 달았고 특정 비교 API 대비 "
            "약 125배 낮은 비용을 제시했다. "
            "이는 로봇 제조비 125분의 1이나 GPU 서버 512대가 아니며 "
            "유상 고객계약·상용 로봇 매출도 미공개다."
        ),
        "category": "엔비디아 · Flora 로봇 학습자료 모델 공개",
        "meaning": (
            "하루 영상 20만 시간을 GB300 가속기 512개로 주석 처리한 "
            "엔비디아 연구 성과입니다. 약 125배 비용 차이는 특정 "
            "상용 API와의 자동 주석 비용 비교로 로봇 생산비와 무관합니다."
        ),
        "risk": (
            "잘못된 행동 성공 판정·학습자료 편향·현실 작업 전이 실패와 "
            "다른 환경에서의 재현성 검증이 필요합니다. "
            "오픈소스 공개와 유상 반복매출을 분리합니다."
        ),
    },
    "shanghai_policy": {
        "group": "shanghai_physical_ai_2027_policy",
        "stage": "official_action_plan_published",
        "source": "상하이시 경제정보화위원회",
        "title": "상하이 2027~2028년 산업서비스 AI 계획 공식 공포 · 과제별 최대 2천만 위안",
        "link": "https://www.sheitc.sh.gov.cn/cyfz/20261023/60be152d6aa74cc7a4f91ce0504c4d82.html",
        "description": (
            "2026-10-23 상하이시 경제정보화위원회 공식 계획. "
            "산업서비스업 AI 도입 관련 세계모델·멀티모달 물리인지·"
            "로봇 자율의사결정 등 연구개발에 과제당 최고 2000만 위안 "
            "지원 가능. 지급 완료 금액이나 시 전체 총예산이 아니다. "
            "2028년 공장 내 휴머노이드 8000대 배치는 10월 16일 공개된 "
            "별도 차세대 지능형 제조 실행계획의 목표이며 새 확정 발주가 "
            "아니다. 향후 공고·심사·수혜기업 선정·조달·실제 배치를 추적."
        ),
        "category": "상하이 · 산업서비스 AI 2027~2028년 정책 공포",
        "meaning": (
            "물리적 AI·세계모델·산업용 AI 소프트웨어 등 해당 분야에서 "
            "과제별 지원 상한 2천만 위안(약 39억7,920만원)을 제시했습니다. "
            "8천대는 별도 기존 정책의 2028년 배치 목표이지 낙찰 대수가 아닙니다."
        ),
        "risk": (
            "정부 모집공고·자격·지방 재정 집행·기술 검증·현장 안전인증·"
            "공장 설치 시차 때문에 배정과 실제 로봇 구매는 다릅니다."
        ),
    },
    "raon_factory": {
        "group": "raon_wafer_robot_yongin_factory",
        "stage": "actual_factory_groundbreaking",
        "source": "라온로보틱스 발표·디일렉",
        "title": "라온로보틱스 용인 웨이퍼 이송로봇 신공장 실제 착공",
        "link": "https://www.thelec.kr/news/articleView.html?idxno=64213",
        "description": (
            "2026-10-20 용인공장 실제 착공, 10월 23일 회사 제공 "
            "현장사진과 복수 보도로 확인. 투자총액 약 600억원, "
            "이전 8월 공시 토지매입 약 274억원은 총액과 중복 합산하지 "
            "않는다. 연면적 23861제곱미터, 기존 수원사업장 약 3배 크기. "
            "2027년 말 준공, 2028년 초 이전은 목표. "
            "반도체 웨이퍼 이송로봇 사업이며 Tesla Optimus 공급계약 "
            "또는 휴머노이드 부품 양산과 무관하다. 향후 실제 증설 "
            "생산능력·고객수주·가동률과 차입·감가상각을 분리해 확인."
        ),
        "category": "라온로보틱스 · 용인 이송로봇 신공장 실제 착공",
        "meaning": (
            "총투자계획 약 600억원, 기존 사업장 대비 3배 규모의 "
            "웨이퍼 이송로봇 신공장을 착공했습니다. "
            "기존 토지매입 공시 약 274억원은 총액의 일부이지 추가 "
            "사업비가 아닙니다. 준공 목표는 2027년 말입니다."
        ),
        "risk": (
            "2026년 상반기 현금성자산 약 85억원 보도 대비 투자액이 "
            "크므로 차입·공사비·감가상각과 수주 대비 가동률을 봅니다. "
            "웨이퍼 이송로봇을 테슬라 휴머노이드 직접 공급으로 분류하지 않습니다."
        ),
    },
}
R26_PRIORITY = [
    "tesla_fremont", "lge_hsb", "mobilint_lge",
    "shanghai_policy", "raon_factory", "nvidia_flora",
]
R26_PRESS = {
    "tesla_fremont": {"Tesla", "Tesla Investor Relations", "Tesla SEC filing"},
    "lge_hsb": {"LG이노텍", "LG Innotek", "LG Innotek Newsroom"},
    "mobilint_lge": {"모빌린트", "Mobilint", "LG전자", "LG Electronics"},
    "nvidia_flora": {"NVIDIA", "NVIDIA Research"},
    "shanghai_policy": {"상하이시 경제정보화위원회", "上海市经济和信息化委员会"},
    "raon_factory": {"라온로보틱스", "Raon Robotics"},
}
R26_SEARCHES = [
    '(Tesla OR 테슬라) (Optimus OR 옵티머스) (Fremont OR 프리몬트) (production-quality OR 생산개시 OR 양산품질 OR 실제 출하 OR 수율)',
    '(Tesla OR 테슬라) (Optimus OR 옵티머스) (AI5 OR Academy OR 외부 고객 인도) (탑재 완료 OR 고객계약 체결 OR actually delivered OR completed)',
    '(LG이노텍 OR LG Innotek) (NVIDIA OR 엔비디아) (HSB OR Holoscan Sensor Bridge OR 멀티모달 비전) (공급계약 OR 양산 OR 고객검증 OR 2027)',
    '(모빌린트 OR Mobilint) (LG전자 OR LG Electronics) (휴머노이드 OR humanoid) (NPU OR 가속기) (검증 완료 OR 유상계약 OR 고객 승인 OR 양산)',
    '(NVIDIA OR 엔비디아) (Flora OR 플로라) (로봇 데이터 OR 주석 OR 20만시간 OR 512 GB300 OR 실제 상용)',
    '(上海 OR 상하이 OR Shanghai) (工业服务业 OR 산업서비스업 OR industrial services) (物理AI OR 피지컬AI OR 具身智能) (2000万元 OR 2천만위안 OR 实际拨付 OR 보조금)',
    '(라온로보틱스 OR Raon Robotics) (용인 OR Yongin) (신공장 OR factory OR 600억원) (착공 OR 실제 가동 OR 준공 OR 투자변경)',
]

def _r26_match(text: str) -> str:
    t = text.casefold()
    if (("tesla" in t or "테슬라" in t)
        and ("optimus" in t or "옵티머스" in t)
        and (any(k in t for k in ("fremont", "프리몬트", "production-quality"))
             or any(k in t for k in ("외부 첫 인도 완료", "first external deliveries began",
                                      "ai5 integration completed", "ai5 실제 탑재 완료")))):
        return "tesla_fremont"
    if ("lg이노텍" in t or "lg innotek" in t) and any(
            k in t for k in ("hsb", "holoscan sensor bridge", "멀티모달 비전")):
        return "lge_hsb"
    if ("모빌린트" in t or "mobilint" in t) and ("lg전자" in t or "lg electronics" in t) and any(
            k in t for k in ("npu", "휴머노이드", "humanoid")):
        return "mobilint_lge"
    if ("nvidia" in t or "엔비디아" in t) and ("flora" in t or "플로라" in t):
        return "nvidia_flora"
    if (any(k in t for k in ("上海", "상하이", "shanghai"))
        and any(k in t for k in ("工业服务业", "산업서비스", "industrial service"))
        and any(k in t for k in ("ai", "人工智能", "物理ai", "피지컬"))):
        return "shanghai_policy"
    if ("라온로보틱스" in t or "raon robotics" in t) and any(
            k in t for k in ("용인", "yongin")) and any(
            k in t for k in ("공장", "factory")):
        return "raon_factory"
    return ""

def _r26_stage(item: dict, eid: str) -> str:
    if item.get("r26_stage"):
        return item["r26_stage"]
    text = " ".join(str(item.get(k) or "") for k in ("title","description"))
    source = str(item.get("source") or "")
    if source not in R26_PRESS[eid]:
        return R26_EVENTS[eid]["stage"]
    if eid == "tesla_fremont":
        if re.search(r"first external deliveries began|외부 첫 인도 완료|외부 고객.{0,35}첫 인도 완료", text, re.I):
            return "first_customer_deliveries_actual"
        if re.search(r"AI5 integration completed|AI5 실제 탑재 완료", text, re.I):
            return "ai5_real_integration"
        if re.search(r"(?:주당 2만대|20,?000 robots per week).{0,50}(?:실제 달성|achieved)", text, re.I):
            return "weekly_20000_actually_achieved"
    if eid == "lge_hsb" and re.search(
        r"(?:HSB|Holoscan Sensor Bridge|MVS).{0,100}"
        r"(?:유상 공급계약 체결|실제 양산 시작|signed supply contract|mass production began)", text, re.I
    ):
        return "hsb_customer_order_or_sop_actual"
    if eid == "mobilint_lge" and re.search(
        r"LG전자.{0,90}(?:고객 검증 완료|성능 검증 통과|유상 납품계약 체결)"
        r"|NPU.{0,70}(?:실제 양산 시작|mass production began)", text, re.I
    ):
        return "lge_robot_npu_qualification_or_order"
    if eid == "nvidia_flora" and re.search(
        r"(?:Flora|플로라).{0,120}(?:유상 상용 계약 체결|paid production deployment confirmed)", text, re.I
    ):
        return "flora_paid_customer_actual"
    if eid == "shanghai_policy" and re.search(
        r"(?:보조금|지원금|资助).{0,65}(?:실제 지급 완료|拨付完成|grant disbursed)", text, re.I
    ):
        return "named_grant_disbursed"
    if eid == "raon_factory" and re.search(
        r"신공장.{0,65}(?:준공 완료|정식 가동 개시|공장 실제 가동 시작)"
        r"|new factory.{0,65}(?:commissioned|began operation)", text, re.I
    ):
        return "new_factory_operational_actual"
    return R26_EVENTS[eid]["stage"]

_r26_old_query = base.query_news
_r26_old_group = base.topic_group
_r26_old_score = base.score
_r26_old_category = base.category
_r26_old_key = base.key
_r26_old_meaning = base.meaning
_r26_old_risk = base.risk
_r26_old_verification = base.verification
_r26_old_tag = base.tag_for
_r26_old_select = base.select_diverse

def _r26_query(q: str) -> list[dict]:
    if q.startswith(R26_PREFIX):
        event_id = q[len(R26_PREFIX):]
        if event_id not in R26_EVENTS or base.NOW.astimezone(base.KST).date() > dt.date(2026,10,29):
            return []
        event = R26_EVENTS[event_id]
        return [dict(
            title=event["title"], description=event["description"],
            link=event["link"], source=event["source"], published=None,
            r26_verified=True, r26_stage=event["stage"],
        )]
    return _r26_old_query(q)

def _r26_group(text: str) -> str | None:
    name = _r26_match(text)
    return R26_EVENTS[name]["group"] if name else _r26_old_group(text)

def _r26_score(item: dict) -> int:
    text = " ".join(str(item.get(k) or "") for k in ("title","description","source"))
    name = _r26_match(text)
    if not name:
        return _r26_old_score(item)
    if item.get("r26_verified"):
        return 25
    if (item.get("source") in R26_PRESS[name]
        and _r26_stage(item, name) != R26_EVENTS[name]["stage"]):
        return 21
    # An article repeating an old plan or a theme name cannot be a new contract.
    return 0

def _r26_key(item: dict) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("title","description","source"))
    name = _r26_match(text)
    if not name:
        return _r26_old_key(item)
    return hashlib.sha256(
        f"robot26|{name}|{_r26_stage(item, name)}".encode("utf-8")
    ).hexdigest()

def _r26_category(text: str, group: str) -> str:
    for name, event in R26_EVENTS.items():
        if group == event["group"]:
            return event["category"]
    return _r26_old_category(text, group)

def _r26_meaning(category: str) -> str:
    for event in R26_EVENTS.values():
        if category == event["category"]:
            return event["meaning"]
    return _r26_old_meaning(category)

def _r26_risk(category: str) -> str:
    for event in R26_EVENTS.values():
        if category == event["category"]:
            return event["risk"]
    return _r26_old_risk(category)

def _r26_verification(item: dict, group: str, text: str) -> str:
    for name, event in R26_EVENTS.items():
        if group == event["group"]:
            if item.get("r26_verified"):
                return ("1차 출처 또는 회사 발표 기반 복수 매체 확인 · "
                        "계약·매출 단계는 별도 검증")
            return "회사 공식 후속 이정표 · 계획과 실제 완료 분리 확인 필요"
    return _r26_old_verification(item, group, text)

def _r26_tag(group: str) -> str:
    tags = {
        "tesla_optimus_q3_fremont": "테슬라",
        "lge_nvidia_hsb_robot_sensing": "LG이노텍",
        "mobilint_lge_humanoid_npu": "모빌린트",
        "nvidia_flora_robot_data": "엔비디아",
        "shanghai_physical_ai_2027_policy": "상하이 정책",
        "raon_wafer_robot_yongin_factory": "라온로보틱스",
    }
    return tags.get(group) or _r26_old_tag(group)

def _r26_select(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    chosen = _r26_old_select(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get("key") not in seen]
    # Prevent six confirmed dated upgrades from being buried under repeated
    # investment-commentary stories. All selections still respect seen keys.
    for name in reversed(R26_PRIORITY):
        group = R26_EVENTS[name]["group"]
        hit = next((x for x in candidates if x.get("group") == group and
                    x.get("score", 0) >= 11), None)
        if hit and not any(x.get("key") == hit.get("key") for x in chosen):
            chosen = [hit] + chosen
            chosen = chosen[:limit]
    return chosen

base.query_news = _r26_query
base.topic_group = _r26_group
base.score = _r26_score
base.key = _r26_key
base.category = _r26_category
base.meaning = _r26_meaning
base.risk = _r26_risk
base.verification = _r26_verification
base.tag_for = _r26_tag
base.select_diverse = _r26_select
for _q in [*(R26_PREFIX + k for k in R26_EVENTS), *R26_SEARCHES]:
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    qty.current.opt.current.fig.legacy.repair_pending_seen(pre_state)
    qty.current.opt._finalize_alert_text()
    qty.current._append_value_estimate()
    qty.enrich_quantity_values()
    _finalize_airan_criteria()

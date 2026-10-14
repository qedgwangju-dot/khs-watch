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
    r'^\s*\d+(?:\.\d+)?\s*%\s*(?:조정|하락|상승|급등|반등|급락|등락)',
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
    return bool(STOCK_ONLY_REACTION.search(headline))


ESS_GENERIC_DEMAND_HEADLINE = re.compile(
    r'(?:ESS|BESS|에너지저장|배터리|battery).{0,38}'
    r'수요\s*(?:폭증|급증|폭발|확대|성장)|'
    r'수요\s*(?:폭증|급증|폭발|확대).{0,38}'
    r'(?:ESS|BESS|에너지저장|배터리|battery)',
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
    return _orig_query_news(q)


base.query_news = query_news
for q in (
    CATL_INTILION_RECOVERY,
    DEXMATE_LG_RECOVERY,
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
    if item.get('robros_false_alert_correction'):
        return 90 if _is_robros_pilot(
            f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
        ) else 0
    if (_is_stock_reaction_only(item)
            or _is_ess_expectation_only(item)
            or _is_generic_ess_demand_story(item)):
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
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
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

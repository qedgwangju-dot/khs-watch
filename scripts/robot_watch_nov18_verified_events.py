"""Dated November robotics corrections within the existing watcher.

Pinned, reviewed events have one semantic key and a short recovery window.
RSS reprints never become a second source of pinned facts. Later milestones
need both an official publisher name and an official host; they are labelled
as headline discovery, not as a verified contract or a read full text.
No state, route, schedule, force flag, or selection policy is changed here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from decimal import Decimal
from urllib.parse import urlparse

KST = dt.timezone(dt.timedelta(hours=9))
BACKFILL = "__robot_watch_reviewed_events_20261118_once__"
START = dt.datetime(2026, 11, 18, tzinfo=KST)
END = dt.datetime(2026, 11, 23, tzinfo=KST)  # Exclusive; last day is Nov 22.
PREFIX = "nov18_"

# Dates are event/report dates, never collection dates. The exact publication
# minute is not invented: pinned rows carry explicit day precision for rendering.
EVENTS = {
    "bd_gf": {
        "date": "2026-11-17", "report_date": "2026-11-17", "stage": "spot_expansion_atlas_trial_plan",
        "title": "보스턴다이내믹스·GlobalFoundries, 4개 팹 Spot 확대·2027년 초 Atlas 시험 계획",
        "source": "Boston Dynamics", "url": "https://bostondynamics.com/news/boston-dynamics-globalfoundries-expand-robotics-collaboration/",
        "meaning": "11월 17일 협력 확대 발표로 미국 몰타·벌링턴, 독일 드레스덴, 싱가포르 4개 거점에 Spot 배치를 확대합니다. 싱가포르의 Spot 2대가 4월 이후 약 900km·9만 건 이상 점검·미션 성공률 99%를 기록했습니다. 이 수치는 Spot 실적이며 Atlas 성능이 아닙니다. Atlas는 자동차 외 업종으로 적용처를 넓혀 2027년 초 GlobalFoundries 시설에서 현장시험을 시작할 계획입니다.",
        "verification": "11월 17일 회사 공식 발표·독립 보도 대조; Spot 운영 실적과 Atlas 시험 계획 분리",
        "risk": "Atlas의 상용 납품·검수 완료·구매 대수·계약금액은 미공개입니다. 현장시험 계획을 양산 매출로 보지 않습니다.",
    },
    "genesis": {
        "date": "2026-11-17", "report_date": "2026-11-17", "stage": "series_a_500m",
        "title": "Genesis AI, 시리즈A 5억 달러 조달…삼성·NVIDIA·AMD 참여는 같은 투자 사건",
        "source": "Genesis AI 공식 발표·Forbes", "url": "https://www.prnewswire.com/news-releases/genesis-ai-raises-500m-series-a-at-3-5b-valuation-to-master-human-level-dexterity-in-general-purpose-robots-and-deploy-at-scale-302941249.html",
        "meaning": "11월 17일 Genesis AI가 시리즈A 5억 달러를 조달했고 투자 후 기업가치는 35억 달러로 발표했습니다. NVIDIA·AMD Ventures·Samsung Next 등의 참여는 같은 자금조달 사건으로 합쳐 집계합니다. GENE 모델·데이터 수집 장갑·Genesis World 시뮬레이터와 바퀴형 양팔 로봇 Eno를 함께 개발하며 손당 능동 자유도 20개는 Forbes 보도 기준입니다. 산업 고객 공급 확대와 2027년 고객 확대 계획은 실제 반복 매출과 구분합니다.",
        "verification": "11월 17일 자금조달 발표·Forbes 보도 기준; 참여사별 투자액과 고객별 계약금액 미공개",
        "risk": "투자 유치는 로봇 판매 매출이 아닙니다. 양산 수율·현장 신뢰성·납품과 현금회수를 별도로 확인합니다.",
    },
    "amd_worldlabs": {
        "date_label": "사건일",
        "date": "2026-11-13", "report_date": "2026-11-16", "stage": "acquisition_completed",
        "title": "AMD, World Labs 인수 완료 발표…인수 합의에서 거래 종결로 진전",
        "source": "AMD", "url": "https://newsroom.amd.com/news/amd-completes-acquisition-world-labs/",
        "meaning": "11월 16일 AMD는 World Labs 인수 완료를 발표했으며 SEC 공시의 거래 종결일은 11월 13일입니다. 인수 합의 단계에서 거래 종결로 진전한 사건입니다. 공간지능 모델과 컴퓨팅·메모리·소프트웨어의 통합이 피지컬 AI 사업 확대 경로입니다. World Labs의 Atlas 모델은 보스턴다이내믹스의 Atlas 휴머노이드와 다른 제품입니다.",
        "verification": "AMD 11월 16일 공식 발표·SEC 8-K/A(접수번호 0001193125-26-462340) 대조; 거래 완료일 11월 13일은 SEC 공시 근거",
        "risk": "인수 완료만으로 로봇 고객 수주·칩 매출 증가를 확정하지 않습니다. 통합 비용과 실제 고객 채택을 확인합니다.",
    },
    "openai_reorg": {
        "date_label": "최초 보도일",
        "date": "2026-11-13", "report_date": "2026-11-16", "stage": "robotics_reorganisation_correction",
        "title": "OpenAI 독립 로보틱스팀 재편 보도…사업 철수·실물 성능 입증과 구분",
        "source": "Fortune 보도·OpenTools 정정", "url": "https://opentools.ai/news/openai-disbands-robotics-team-general-purpose-models",
        "meaning": "독립 로보틱스팀의 연구 인력은 Mark Chen 산하, 응용·하드웨어 인력은 Greg Brockman 산하 조직으로 이동했다는 보도입니다. 회사 설명은 로보틱스 철수가 아니라 개발 가속화를 위한 재편입니다. GPT-6 Astra의 74.8%와 비교모델 51.0%는 10월 14일 연구의 시뮬레이션 지표로 11월 신규 실물 성과가 아닙니다. 자체 휴머노이드의 2027년 공개 시연은 목표 단계입니다.",
        "verification": "11월 13일 Fortune 보도의 11월 16일 재인용·정정 맥락; 조직 원문 독립 검증 한계와 시뮬레이션 조건 표시",
        "risk": "범용 모델의 시뮬레이션 우위로 실제 로봇 안전성·저지연 제어·온디바이스 동작까지 입증됐다고 해석하지 않습니다.",
    },
    "samsung_humanoid": {
        "date_label": "보도일",
        "date": "2026-11-17", "report_date": "2026-11-17", "stage": "ces_hr_he_report_design_conflict",
        "title": "삼성 휴머노이드 CES 2027 HR·HE 보도 추가…손 구동 방식은 매체 간 상충",
        "source": "한겨레·뉴스웍스", "url": "https://www.hani.co.kr/arti/economy/marketing/1287815.html",
        "meaning": "한겨레는 11월 17일 CES 2027에서 HR 기본형과 HE 상위형을 공개할 예정이라고 보도했습니다. 양손에 다섯 손가락씩이라는 설명은 있으나 뉴스웍스의 직구동 보도와 한겨레의 케이블 힘줄 구동 보도가 충돌합니다. 공식 규격 확인 전에는 직구동 채택을 확정하지 않습니다. Shadow의 35% 절전은 모터 20→13개·손목 관절 2→0인 서로 다른 손 모델 비교로, 손가락 하나나 로봇 전체 전력의 35%를 뜻하지 않습니다.",
        "verification": "뉴스웍스 직접 본문·한겨레 동일 기사 공개 대체본 확인; 삼성 공식 규격 미확인·업계 보도 단계",
        "risk": "CES 공개 계획·시제품과 양산·매출을 구분합니다. 보도 충돌이 해소되기 전 특정 구동부품 수혜를 확정하지 않습니다.",
    },
    "samhyun": {
        "date_label": "전망 보도일",
        "date": "2026-11-17", "report_date": "2026-11-17", "stage": "customer_sop_q1_to_q4_report",
        "title": "삼현 북미 고객 양산 2027년 1분기→2026년 4분기 전망…매출 200억원은 한투 추정",
        "source": "한국투자증권·이데일리", "url": "https://www4.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=02276326645646704",
        "meaning": "9월 북미 초도 양산 수주는 회사가 이미 발표한 사실입니다. 한투는 11월 12~13일 기업설명회 후 고객 양산 개시가 2027년 1분기에서 2026년 4분기로 앞당겨졌다고 설명했습니다. 2027년 로봇 매출 200억원과 2028년 1,600억원은 증권사 추정입니다. 총 1,000억원 투자와 2027년 4월 생산라인 구축·하반기 자동화 가동은 계획이며 초도 출하는 수작업 소량 생산입니다.",
        "verification": "9월 수주 회사 공지·11월 17일 한투 분석가 요약 및 이데일리 대조; 고객 실명 비공개",
        "risk": "익명 북미 고객을 특정 업체로 단정하지 않습니다. 확정 계약액·실제 출하·자동화 가동률을 확인하고 내부 조립 부품을 외부 판매량과 중복 계산하지 않습니다.",
    },
    "everybot": {
        "date_label": "보도 확인일",
        "date": "2026-11-18", "report_date": "2026-11-18", "stage": "physical_ai_unit_agibot_partner_report",
        "title": "에브리봇 사업본부 출범·AGIBOT 골드파트너 보도…누적 순이익과 본업 이익 구분",
        "source": "뉴스핌·매일경제", "url": "https://www.newspim.com/news/view/20261118000268",
        "meaning": "11월 17일 연내 개편 추진 보도에서 18일 피지컬AI사업본부 출범·AGIBOT 한국 골드파트너 선정 보도로 진전했습니다. 기존 DDT 사족보행 로봇 협력에서 휴머노이드로 협력 범위를 넓힌다는 내용입니다. 2026년 1~3분기 누적 연결 순이익 52억원은 본업 영업흑자 확인과 다릅니다. 2027년 산업·서비스 로봇 확대는 회사 계획이며 고객 계약·공급 물량은 별도 확인이 필요합니다.",
        "verification": "매일경제 실적 기사 직접 확인; 11월 18일 뉴스핌 검색색인·회사 발표 인용 보도, 해당 회사 원문 추가 확인 필요",
        "risk": "파트너 선정과 실제 고객 수주·반복 매출은 다릅니다. 누적 순이익만으로 영업이익·현금흐름 개선을 단정하지 않습니다.",
    },
    "knr": {
        "date": "2026-11-18", "report_date": "2026-11-18", "stage": "lower_body_walk_test",
        "title": "케이엔알시스템 슈퍼휴머노이드 하체 보행 성공…2톤 전신 통합은 12월 목표",
        "source": "에너지경제·뉴시스", "url": "https://ekn.kr/web/view.php?key=20261118023561209",
        "meaning": "11월 18일 발표한 성과는 하체의 전진·방향전환·측면 이족보행 시험입니다. 2.9m·2톤·양팔 가반하중 600kg은 완성체 설계 목표이며 전신 통합은 12월 목표입니다. 하체는 12관절과 1만Nm급 유압 액추에이터를 사용합니다. 시속 3~4km 보행과 경사로·계단·자율주행은 후속 개발·검증 대상입니다.",
        "verification": "에너지경제 직접 본문·뉴시스 별도 기사 대조; 회사 발표 인용, 당일 공식 시험자료 추가 확인 필요",
        "risk": "하체 시제품 성공을 완성체의 600kg 운반 실증·양산·납품으로 올리지 않습니다. 전신 안정성·안전·실제 고객 검증이 남아 있습니다.",
    },
    "lg_safety": {
        "date_label": "사건일",
        "date": "2026-11-13", "report_date": "2026-11-16", "stage": "kiria_safety_mou",
        "title": "LG전자·한국로봇산업진흥원 안전·품질 협약…2027년 1분기 이족보행 공개 목표",
        "source": "LG전자", "url": "https://www.lge.co.kr/story/newsroom/236241",
        "meaning": "LG전자는 11월 13일 한국로봇산업진흥원과 안전·품질 업무협약을 체결했다고 16일 발표했습니다. 안전인증센터 평가체계·국제 및 국가표준 개발에 참여하고 CLOiD 국내 안전 시범인증을 추진합니다. 엔비디아 기반 이족보행 로봇의 2027년 1분기 공개는 별도 언론 보도상 목표입니다. 업무협약에서 실제 인증 취득·제품 공급까지는 추가 단계가 필요합니다.",
        "verification": "LG전자 11월 16일 공식 자료·연합뉴스 대조; 협약일 11월 13일",
        "risk": "시범인증 추진을 안전인증 완료로 표현하지 않습니다. 공개 일정과 연구·교육기관 공급·양산 일정을 구분합니다.",
    },
    "robotis": {
        "date_label": "분석 공개일",
        "date": "2026-11-16", "report_date": "2026-11-16", "stage": "q3_mix_factory_delay_report",
        "title": "로보티즈 한투 3분기 분석…영업손실 26억원·신공장 2027년 2분기 순연 설명",
        "source": "한국투자증권 최건", "url": "https://t.me/s/kis_robotics",
        "meaning": "한투 분석가 요약은 2026년 3분기 매출 135억원·영업손실 26억원을 제시했습니다. 액추에이터 출하 11만~12만대와 평균판매단가 약 12만원은 분석가 추정이며 예상 약 13만원을 밑돌았습니다. 수주잔고의 80% 이상이 저단가 다이나믹셀 X이고 신공장 가동이 2027년 2분기로 순연됐다는 설명입니다. 물량 증가와 제품 구성 악화·생산 지연을 함께 추적합니다.",
        "verification": "한투 분석가 자체 공개 요약 확인; 회사 공시·보고서 전문 독립 확인 전",
        "risk": "수주잔고를 출하·매출로 보지 않습니다. 공장 가동일·수율·고단가 제품 비중·현금흐름의 공식 후속 확인이 필요합니다.",
    },
    "tesla_germany": {
        "date": "2026-11-16", "report_date": "2026-11-16", "stage": "cybercab_plant_expansion_plan",
        "title": "Tesla 독일 Cybercab 증설 계획…30억 유로·연 최대 100만대 능력 목표",
        "source": "브란덴부르크주·Reuters", "url": "https://brandenburg.de/cms/detail.php?gsid=brandenburg_06.c.918992.de",
        "meaning": "11월 16일 독일 공장에 30억 유로를 투자해 Cybercab 연 최대 100만대 생산능력을 구축하는 계획이 발표됐습니다. 연내 허가 신청→2027년 상반기 착공→2029년 생산이 제시된 시간표입니다. 생산능력 목표는 실제 생산량·판매량이 아닙니다. 주정부 발표와 Reuters 보도로 계획을 확인했으며 허가 승인·발주 완료 단계는 아닙니다.",
        "verification": "브란덴부르크주 11월 16일 발표·Reuters 대조; 투자·생산능력과 일정은 계획",
        "risk": "인허가·전력·시공과 수요 변화로 일정·가동률이 달라질 수 있습니다. 투자 총액을 특정 공급사 확정 매출로 바꾸지 않습니다.",
    },
    "hyundai_bd_ownership": {
        "date_label": "보도 확인일",
        "date": "2026-11-17", "report_date": "2026-11-17", "stage": "remaining_stake_acquired_report",
        "title": "현대차그룹·정의선, 보스턴다이내믹스 잔여지분 취득 완료 보도",
        "source": "뉴시스·분기공시 재게시본", "url": "https://m.newsis.com/view/NISX20261116_0003870194",
        "meaning": "7월 매도청구권 행사에서 3분기 모든 관련 권리 행사·소멸로 진전했다는 11월 17일 보도입니다. 보스턴다이내믹스 지분 전량은 정의선 회장과 현대차그룹 계열사들의 합계이며 현대차 단일 법인의 100% 소유를 뜻하지 않습니다. 현대글로비스 지분은 11.39%→12.47%로 늘었고 3분기 추가 취득액은 465억원입니다. 지배구조 정리와 Atlas 양산·매출은 별도 사건입니다.",
        "verification": "뉴시스 직접 본문·접수번호 20261116000562 공시 전문 재게시본 대조; DART 직접 접근 실패",
        "risk": "기존 자회사 잔여지분 취득을 신규 연결매출 발생으로 계산하지 않습니다. 투자부담·추가 자금조달·상용 납품은 별도 확인합니다.",
    },
    "foundation": {
        "date_label": "협의 보도일",
        "date": "2026-11-15", "report_date": "2026-11-15", "stage": "israel_talks_disputed_deployment",
        "title": "Foundation 이스라엘 로봇 공급 협의 보도…우크라이나 배치 주장은 반대 취재 존재",
        "source": "글로벌이코노믹·The San Francisco Standard", "url": "https://www.g-enews.com/article/Global-Biz/2026/11/2026111506455381112bd56fbc3c_1",
        "meaning": "11월 15일 국내 보도는 Foundation의 이스라엘 로봇 공급 협의를 전했으며 확정 계약 상대방·금액·수량·납품일은 확인되지 않았습니다. 11월 14일 The San Francisco Standard 취재에는 특정 우크라이나 현장 시험 주장에 대한 동행 취재자와 Brave1의 반론이 포함됐습니다. 회사 주장과 반대 증거를 함께 보존하며 실제 전선 배치와 성능을 확정하지 않습니다.",
        "verification": "국내 기사 직접 본문·The San Francisco Standard 반대 취재 대조; 협의 보도와 실제 납품 구분",
        "risk": "미체결 협의·개발 시연을 실전 배치·검증된 성능·매출로 바꾸지 않습니다. 운용기관 확인과 계약·납품 문서가 필요합니다.",
    },
}

LABELS = {
    "bd_gf": "보스턴다이내믹스·GlobalFoundries 로봇",
    "genesis": "Genesis AI 로봇",
    "amd_worldlabs": "AMD·World Labs 공간지능",
    "openai_reorg": "OpenAI 로봇 시연·재편",
    "samsung_humanoid": "삼성전자 HR·HE 휴머노이드",
    "samhyun": "삼현 북미 휴머노이드",
    "everybot": "에브리봇·AGIBOT 피지컬AI",
    "knr": "케이엔알시스템 슈퍼휴머노이드",
    "lg_safety": "LG전자 CLOiD 안전인증",
    "robotis": "로보티즈 신공장·실적",
    "tesla_germany": "Tesla 독일 Cybercab",
    "mcnex": "엠씨넥스 Atlas 계약·출하",
    "hyundai_bd_ownership": "현대차그룹·보스턴다이내믹스 지분",
    "foundation": "Foundation 이스라엘 로봇 공급",
}
# Already delivered on Nov 16 (Telegram messages 374/375). Preserve the old
# semantic key so the November review cannot retransmit the same LG MOU.
KEY_OVERRIDES = {
    "lg_safety": "df5ed2e98d898262d3f40710a990b07027c78cc9f45f9d4ec7150e5bb2b6b1c8",
}

SEARCH_QUERIES = (
    '("Boston Dynamics" OR 보스턴다이내믹스) (GlobalFoundries OR 글로벌파운드리 OR Hyundai OR 현대차) (Atlas OR Spot OR 계약 OR 시험 OR 지분 OR stake)',
    '("Genesis AI" OR 제네시스AI) (Eno OR GENE OR investment OR funding OR 계약 OR 출하)',
    '(AMD OR 리사수) ("World Labs" OR 월드랩스) (acquisition OR completed OR 인수 OR Atlas)',
    '(OpenAI OR 오픈AI) (robotics OR 휴머노이드) (reorganize OR disband OR demonstration OR 재편 OR 시연)',
    '(삼성전자 OR Samsung) (HR OR HE OR CES) (humanoid OR 휴머노이드) (공개 OR 손 OR tendon OR direct)',
    '(삼현 OR Samhyun) (휴머노이드 OR humanoid) (북미 OR OEM) (출하 OR 양산 OR contract OR shipment)',
    '(에브리봇 OR Everybot) (AGIBOT OR 피지컬AI사업본부 OR 공급계약 OR 출하)',
    '(케이엔알시스템 OR "KNR Systems") (슈퍼휴머노이드 OR humanoid) (하체 OR 전신 OR 보행 OR 납품)',
    '(LG전자 OR LG) (CLOiD OR 클로이드 OR 휴머노이드) (KIRIA OR 안전인증 OR 인증 OR 공개)',
    '(로보티즈 OR ROBOTIS OR 엠씨넥스 OR MCNEX) (신공장 OR Atlas OR 아틀라스 OR 출하 OR 수주) (완료 OR 지연 OR 계약 OR 가동)',
    '(Tesla OR 테슬라) (Cybercab OR 사이버캡) (Germany OR Brandenburg OR 독일) (permit OR construction OR production OR 허가 OR 착공 OR 생산)',
    '("Foundation Future Robotics" OR "Foundation Robotics" OR 파운데이션) (Israel OR 이스라엘 OR Brave1) (contract OR shipment OR 계약 OR 납품 OR 검증)',
)
QUERIES = (BACKFILL, *SEARCH_QUERIES)


def _has(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.I))


def _body(item: dict) -> str:
    return " ".join(str(item.get(k) or "") for k in ("title", "description"))


def identity(text: str) -> str:
    """Require named counterparties, not the ambiguous model name Atlas."""
    if _has(r"Boston Dynamics|보스턴\s*다이[내나]믹스", text) and _has(r"Global\s*Foundries|글로벌\s*파운드리", text):
        return PREFIX + "bd_gf"
    if _has(r"Boston Dynamics|보스턴\s*다이[내나]믹스", text) and _has(r"현대차|Hyundai|정의선|글로비스|Glovis", text) and _has(r"지분|ownership|stake|풋옵션|매도청구권", text):
        return PREFIX + "hyundai_bd_ownership"
    if _has(r"Foundation|파운데이션", text) and _has(r"이스라엘|Israel", text) and _has(r"로봇|robot|휴머노이드|Phantom|팬텀", text):
        return PREFIX + "foundation"
    if _has(r"Genesis\s*AI|제네시스\s*AI|제네시스에이아이", text):
        return PREFIX + "genesis"
    if _has(r"\bAMD\b|에이엠디", text) and _has(r"World\s*Labs|월드\s*랩스", text):
        return PREFIX + "amd_worldlabs"
    if _has(r"OpenAI|오픈\s*AI|오픈에이아이", text) and _has(r"robot|로봇|로보틱스|휴머노이드", text) and _has(r"재편|해체|reorg|disband|시연|demonstrat|출하|shipment|74\.8", text):
        return PREFIX + "openai_reorg"
    if _has(r"삼성전자|\bSamsung\b|삼성\s*(CES|휴머노이드)", text) and _has(r"휴머노이드|humanoid", text) and _has(r"\bHR\b|\bHE\b|CES|손|hand|구동", text):
        return PREFIX + "samsung_humanoid"
    if _has(r"삼현|\bSamhyun\b", text) and _has(r"휴머노이드|humanoid|북미|고객\s*양산", text):
        return PREFIX + "samhyun"
    if _has(r"에브리봇|\bEverybot\b", text) and _has(r"AGIBOT|피지컬\s*AI|사업본부|52\s*억|physical\s*AI", text):
        return PREFIX + "everybot"
    if _has(r"케이엔알시스템|KNR\s*Systems", text) and _has(r"슈퍼\s*휴머노이드|super.?humanoid|하체|전신", text):
        return PREFIX + "knr"
    if _has(r"LG전자|\bLG\b|엘지", text) and _has(r"CLOiD|클로이드|휴머노이드|humanoid|이족보행", text) and _has(r"안전|품질|인증|KIRIA|로봇산업진흥원|safety|certif", text):
        return PREFIX + "lg_safety"
    if _has(r"로보티즈|\bROBOTIS\b", text) and _has(r"3분기|3Q26|신공장|우즈베키스탄|Uzbekistan|new\s*factory", text):
        return PREFIX + "robotis"
    if _has(r"엠씨넥스|\bMCNEX\b", text) and _has(r"아틀라스|\bAtlas\b", text):
        return PREFIX + "mcnex"
    if _has(r"Tesla|테슬라", text) and _has(r"Cybercab|사이버캡", text) and _has(r"독일|Germany|German|Brandenburg|Gr[uü]nheide|Berlin", text):
        return PREFIX + "tesla_germany"
    return ""


def _normal_title(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


# Only reviewed, specific headlines/facts are replay baselines. Company-name
# recognition alone must never take ownership of an existing watcher lane.
KNOWN_HEADLINES = {
    "bd_gf": ("Boston Dynamics and GlobalFoundries Expand Robotics Collaboration",),
    "amd_worldlabs": ("AMD Completes Acquisition of World Labs",),
    "openai_reorg": (
        "Exclusive OpenAI disbands its stand alone robotics team as its general models start running robots",
        "OpenAI Reorganizes Robotics Team Robotics Work Continues",
    ),
    "mcnex": ("엠씨넥스 아틀라스 공급망 진입 2027년 확대 전망",),
}


def reviewed_reprint(text: str) -> str:
    normal = _normal_title(text)
    for event, spec in EVENTS.items():
        title = _normal_title(spec["title"])
        if normal == title or normal.startswith(title + " "):
            return event
    for event, titles in KNOWN_HEADLINES.items():
        if any(normal == _normal_title(title) or normal.startswith(_normal_title(title) + " ") for title in titles):
            return event
    # Investor-specific headlines refer to the one reviewed Series A only
    # when its amount/valuation is explicit; later rounds pass to old lanes.
    if identity(text) == PREFIX + "genesis" and not _has(r"series\s*[bcdef]|시리즈\s*[bcdef]|추가\s*조달|new\s+round", text):
        amount = _has(r"(?:\$\s*)?500\s*(?:million|m\b)|5\s*억\s*달러|3\.5\s*(?:billion|b\b)|35\s*억\s*달러", text)
        financing = _has(r"series\s*a|시리즈\s*a|투자|유치|invest|funding|valuation", text)
        if amount and financing:
            return "genesis"
    return ""


OFFICIAL = {
    "bd_gf": (("bostondynamics.com", r"Boston Dynamics|보스턴다이내믹스|보스턴다이나믹스"), ("gf.com", r"GlobalFoundries|글로벌파운드리")),
    "genesis": (("genesis-ai.company", r"Genesis AI"),),
    "amd_worldlabs": (("amd.com", r"AMD|AMD Newsroom"), ("worldlabs.ai", r"World Labs")),
    "openai_reorg": (("openai.com", r"OpenAI|OpenAI Newsroom|오픈AI"),),
    "samsung_humanoid": (("samsung.com", r"Samsung|Samsung Electronics|Samsung Newsroom|삼성전자|삼성전자 뉴스룸"),),
    "samhyun": (("samhyun.co.kr", r"Samhyun|삼현|주식회사 삼현"),),
    "everybot": (("everybot.co.kr", r"Everybot|에브리봇"), ("agibot.com", r"AGIBOT|Agibot")),
    "knr": (("knrsys.com", r"KNR Systems|케이엔알시스템"),),
    "lg_safety": (("lge.co.kr", r"LG전자|LG Electronics|LG전자 뉴스룸"), ("lg.co.kr", r"LG|LG전자"), ("kiria.org", r"한국로봇산업진흥원|KIRIA")),
    "robotis": (("robotis.com", r"ROBOTIS|로보티즈"),),
    "mcnex": (("mcnex.com", r"MCNEX|엠씨넥스"), ("bostondynamics.com", r"Boston Dynamics")),
    "tesla_germany": (("tesla.com", r"Tesla|Tesla Investor Relations|테슬라"), ("brandenburg.de", r"Brandenburg|Land Brandenburg|브란덴부르크주")),
    "hyundai_bd_ownership": (("hyundai.com", r"Hyundai Motor|Hyundai Motor Group|현대자동차|현대차그룹"), ("glovis.net", r"Hyundai Glovis|현대글로비스")),
    # No official Foundation domain was independently established in this
    # review. Do not invent an allowlist entry from an unverified publisher.
    "foundation": (),
}


def official(item: dict, event: str) -> bool:
    source = str(item.get("source") or "").strip()
    hosts = set()
    for field in ("source_url", "original_url", "canonical_url", "link"):
        try:
            parsed = urlparse(str(item.get(field) or ""))
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                hosts.add(parsed.hostname.lower().rstrip("."))
        except ValueError:
            continue
    return any(re.fullmatch(name, source, re.I) and any(h == domain or h.endswith("." + domain) for h in hosts)
               for domain, name in OFFICIAL.get(event, ()))


def _published(item: dict) -> dt.datetime | None:
    try:
        value = dt.datetime.fromisoformat(str(item.get("published") or "").replace("Z", "+00:00"))
        return value if value.tzinfo else None
    except ValueError:
        return None


STAGES = {
    "contract_signed": ("공급계약 체결", r"(?:정식\s*(?:공급|구매)계약|최종\s*공급계약|본계약).{0,20}(?:체결|서명)|(?:signed|signs?|executed|executes?)\s+(?:a\s+)?(?:definitive|binding)\s+(?:supply|purchase)\s+(?:agreement|contract)"),
    "shipment_completed": ("초도 출하 완료", r"(?:첫|초도)\s*(?:출하|납품).{0,12}완료|(?:first|initial)\s+shipment\s+(?:completed|delivered)"),
    "field_test_completed": ("현장시험 완료", r"현장\s*(?:시험|실증|테스트).{0,12}(?:완료|통과)|field\s+(?:tests?|trials?)\s+(?:completed|passed)"),
    "integration_completed": ("전신 통합 완료", r"(?:전신|상.?하체)\s*통합.{0,12}완료|full.?body\s+integration\s+completed"),
    "certification_obtained": ("안전인증 취득", r"안전\s*인증.{0,12}(?:취득|획득|통과)|(?:obtained|received|achieved)\s+safety\s+certification"),
    "permit_approved": ("허가 승인", r"(?:건설|공장|환경)\s*허가.{0,12}승인|(?:construction|factory|environmental)\s+permit.{0,20}(?:approved|granted)"),
    "construction_started": ("착공", r"착공(?:했다|했습니다|식|\s*완료|\s*개시)|(?:construction\s+(?:has\s+)?(?:started|begun)|broke\s+ground)"),
    "production_started": ("양산 개시", r"(?:신공장|양산).{0,12}(?:가동\s*시작|가동\s*개시|생산\s*개시|양산\s*개시)|(?:mass\s+production|new\s+factory).{0,20}(?:started|began|begun)"),
    "demonstration_completed": ("실물 시연 완료", r"실물\s*(?:로봇\s*)?(?:공개\s*)?시연.{0,12}완료|physical\s+robot\s+demonstration\s+completed"),
}
ALLOWED_STAGES = {
    "bd_gf": {"contract_signed", "shipment_completed", "field_test_completed"},
    "genesis": {"contract_signed", "shipment_completed", "production_started"},
    "amd_worldlabs": {"contract_signed", "demonstration_completed"},
    "openai_reorg": {"demonstration_completed", "shipment_completed"},
    "samsung_humanoid": {"demonstration_completed", "shipment_completed", "contract_signed"},
    "samhyun": {"contract_signed", "shipment_completed", "production_started"},
    "everybot": {"contract_signed", "shipment_completed"},
    "knr": {"integration_completed", "field_test_completed", "shipment_completed", "contract_signed"},
    "lg_safety": {"certification_obtained", "demonstration_completed", "shipment_completed"},
    "robotis": {"production_started", "shipment_completed"},
    "mcnex": {"contract_signed", "shipment_completed"},
    "tesla_germany": {"permit_approved", "construction_started", "production_started"},
    "hyundai_bd_ownership": {"contract_signed", "shipment_completed"},
    "foundation": {"contract_signed", "shipment_completed"},
}
NEGATED = r"미완료|미체결|미승인|미확인|미취득|아직|않|못|아니|부인|사실무근|\b(?:not|no|never|without|cannot|den(?:y|ies|ied|ial)|incomplete|failed|unconfirmed)\b|\b\w+n['’]t\b|[?？]"
UNCERTAIN = NEGATED + r"|계획|목표|예정|전망|예상|기대|추진|협의|검토|가능성|조건부|\b(?:plan(?:s|ned)?|expect(?:s|ed)?|target(?:s|ed)?|aims?|may|might|could|will|pending)\b"


def _headline_clauses(title: str):
    for sentence in re.split(r"[;；!?。！？]|(?<!\d)\.(?!\d)", title):
        start = 0
        for boundary in re.finditer(r"\s+(?:and|while|whereas|but|그리고|반면|한편|및)\s+", sentence, re.I):
            prefix = sentence[start:boundary.start()]
            if _has(r"\b(?:completed|approved|acquired|signed|executed|delivered|started|began)\b|완료|체결|획득|승인|착공|개시", prefix):
                yield prefix
                start = boundary.end()
        yield sentence[start:]


def future_stage(item: dict, event: str, now: dt.datetime) -> str:
    published = _published(item)
    if not published or published > now or now - published > dt.timedelta(days=4):
        return ""
    baseline = dt.date.fromisoformat(EVENTS.get(event, {}).get("report_date", "2026-10-26"))
    # A completed stage may genuinely arrive later on the same calendar day;
    # reprints are blocked by the stage vocabulary, not by a next-day delay.
    if published.astimezone(KST).date() < baseline or not official(item, event):
        return ""
    title = str(item.get("title") or "")
    # A denial/question can follow a semicolon or sentence boundary. Do not
    # discard its punctuation before evaluating the claimed completion.
    if _has(NEGATED, title):
        return ""
    for stage_name, (_, pattern) in STAGES.items():
        if stage_name not in ALLOWED_STAGES.get(event, set()):
            continue
        for clause in _headline_clauses(title):
            if identity(clause) != PREFIX + event or _has(UNCERTAIN, clause) or not _has(pattern, clause):
                continue
            # A different company's completion in a separate clause is not
            # this event, and Spot service is not an Atlas field-test result.
            if event == "bd_gf" and stage_name == "field_test_completed" and not _has(r"\bAtlas\b|아틀라스", clause):
                continue
            return stage_name
    return ""


def event_key(event: str) -> str:
    if event in KEY_OVERRIDES:
        return KEY_OVERRIDES[event]
    spec = EVENTS[event]
    return hashlib.sha256(f"robot-review|{event}|{spec['date']}|{spec['stage']}".encode()).hexdigest()


def _product_context(event: str, item: dict) -> str:
    title = str(item.get("nov18_original_title", item.get("title", "")))
    patterns = {
        "bd_gf": (("spot", r"\bSpot\b|스팟"), ("atlas", r"\bAtlas\b|아틀라스")),
        "genesis": (("eno", r"\bEno\b|이노"),),
        "amd_worldlabs": (("atlas", r"\bAtlas\b|아틀라스"),),
        "samsung_humanoid": (("hr", r"\bHR\b"), ("he", r"\bHE\b")),
        "samhyun": (("axlon", r"\bAXLON\b|액슬론"),),
        "lg_safety": (("cloid", r"\bCLOiD\b|클로이드"),),
        "mcnex": (("atlas", r"\bAtlas\b|아틀라스"),),
        "tesla_germany": (("cybercab", r"\bCybercab\b|사이버캡"),),
    }
    products = [name for name, pattern in patterns.get(event, ()) if _has(pattern, title)]
    return "+".join(products) or "unspecified"


def _material_fingerprint(item: dict) -> str:
    """Separate explicitly stated new amounts, quantities or named customers.

    Publication dates, publisher URLs and headline wording are not events.
    Unlabelled counterparties require source review rather than guessed names.
    """
    title = str(item.get("nov18_original_title", item.get("title", "")))
    facts = set()
    for match in re.finditer(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(조원|억원|원|대|units?|robots?)\b", title, re.I):
        value, unit = Decimal(match[1].replace(",", "")), match[2].lower()
        if unit in {"조원", "억원", "원"}:
            value *= {"조원": Decimal(10) ** 12, "억원": Decimal(10) ** 8, "원": Decimal(1)}[unit]
            unit = "KRW"
        else:
            unit = "units"
        facts.add(f"{unit}:{value.normalize()}")
    for match in re.finditer(r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(billion|million|bn|m)?\b", title, re.I):
        value = Decimal(match[1].replace(",", ""))
        value *= {"billion": Decimal(10) ** 9, "bn": Decimal(10) ** 9, "million": Decimal(10) ** 6, "m": Decimal(10) ** 6, "": Decimal(1)}[(match[2] or "").lower()]
        facts.add(f"USD:{value.normalize()}")
    for match in re.finditer(r"(?:고객사?|거래상대방|customer|counterparty)\s*[:=]\s*([\w -]+?)(?=[,;；]|$)", title, re.I):
        facts.add("customer:" + _normal_title(match[1]))
    return "|".join(sorted(facts))


def rows(now: dt.datetime) -> list[dict]:
    if not START <= now.astimezone(KST) < END:
        return []
    return [{"title": spec["title"], "description": spec["meaning"], "source": spec["source"],
             "link": spec["url"], "published": f"{spec['report_date']}T00:00:00+09:00",
             "published_precision": "day", "event_date": spec["date"],
             "reported_date": spec["report_date"], "nov18_event_id": name}
            for name, spec in EVENTS.items()]


def normalize_followup(source_item: dict, now: dt.datetime) -> dict:
    item = dict(source_item)
    group = identity(_body(item))
    if not group:
        return item
    event = group.removeprefix(PREFIX)
    stage = future_stage(item, event, now)
    if stage:
        item["nov18_followup_stage"] = stage
        item["nov18_original_title"] = item.get("title", "")
        item["nov18_followup_event"] = event
        label = STAGES[stage][0]
        item["title"] = f"{LABELS[event]} · 후속 {label} 공식 제목 확인"
        item["description"] = f"{item['nov18_original_title']} 공식 제목 검색색인·본문 추가 검증 필요"
    return item


def install(base) -> None:
    if getattr(base, "_nov18_verified_events_installed", False):
        return
    old = {name: getattr(base, name) for name in ("query_news", "topic_group", "score", "key", "category", "meaning", "risk", "verification", "tag_for", "clean_title")}
    categories = {name: f"{name_label} · 11월 확인 사건" for name, name_label in LABELS.items()}
    future_categories = {f"{LABELS[name]} · 후속 {label}": (name, label)
                         for name, allowed in ALLOWED_STAGES.items()
                         for stage_name, (label, _) in STAGES.items() if stage_name in allowed}
    protected_titles = {spec["title"] for spec in EVENTS.values()} | {
        cat + " 공식 제목 확인" for cat in future_categories
    }

    def query(q):
        if q == BACKFILL:
            return rows(base.NOW)
        return [normalize_followup(item, base.NOW) for item in old["query_news"](q)]

    def group(text):
        for cat, (event, _) in future_categories.items():
            if cat + " 공식 제목 확인" in text:
                return PREFIX + event
        event = reviewed_reprint(text)
        return PREFIX + event if event else old["topic_group"](text)

    def followup(item, event):
        # Recheck original metadata, rather than trusting a caller-added stage.
        if item.get("nov18_followup_event") != event or not item.get("nov18_original_title"):
            return ""
        original = dict(item, title=item.get("nov18_original_title", item.get("title", "")))
        stage = future_stage(original, event, base.NOW)
        return stage if stage == item.get("nov18_followup_stage") else ""

    def score(item):
        event = item.get("nov18_event_id")
        if event in EVENTS:
            return 46 if START <= base.NOW.astimezone(KST) < END else 0
        event = item.get("nov18_followup_event")
        if event in LABELS and followup(item, event):
            return 48
        if reviewed_reprint(str(item.get("title") or "")):
            return 0
        return old["score"](item)

    def key(item):
        event = item.get("nov18_event_id")
        if event in EVENTS:
            return event_key(event)
        event = item.get("nov18_followup_event")
        stage = followup(item, event) if event in LABELS else ""
        if stage:
            return hashlib.sha256(f"robot-followup|{event}|{stage}|{_product_context(event, item)}|{_material_fingerprint(item)}".encode()).hexdigest()
        event = reviewed_reprint(str(item.get("title") or ""))
        if event:
            return event_key(event) if event in EVENTS else hashlib.sha256(b"mcnex|atlas|2026-10-26|supply-chain-report").hexdigest()
        return old["key"](item)

    def category(text, group_name):
        if not isinstance(group_name, str) or not group_name.startswith(PREFIX):
            return old["category"](text, group_name)
        event = group_name[len(PREFIX):]
        if event not in LABELS:
            return old["category"](text, group_name)
        for cat in future_categories:
            if cat + " 공식 제목 확인" in text:
                return cat
        return categories[event]

    def meaning(cat):
        for name, known_cat in categories.items():
            if cat == known_cat and name in EVENTS:
                return EVENTS[name]["meaning"]
        if cat in future_categories:
            _, label = future_categories[cat]
            return f"공식 발행처의 새 제목에서 {label} 관련 단계를 발견했습니다. 공식 제목 검색색인·본문 추가 검증 단계이며 계약 조건·대상 제품·물량·일정의 원문 확인이 필요합니다. 과거 사건의 수치나 본문을 이번 발표에 재사용하지 않습니다."
        return old["meaning"](cat)

    def risk(cat):
        for name, known_cat in categories.items():
            if cat == known_cat and name in EVENTS:
                return EVENTS[name]["risk"]
        if cat in future_categories:
            return "제목만으로 실제 납품·검수·매출 인식을 확정하지 않습니다. 원문에서 계획·협의·완료 여부와 제품·고객을 다시 확인해야 합니다."
        return old["risk"](cat)

    def verification(item, group_name, text):
        if not isinstance(group_name, str) or not group_name.startswith(PREFIX):
            return old["verification"](item, group_name, text)
        event = item.get("nov18_event_id")
        if event in EVENTS:
            spec = EVENTS[event]
            return f"{spec.get('date_label', '발표일')} {spec['date']}·보도일 {spec['report_date']}; {spec['verification']}"
        event = item.get("nov18_followup_event")
        if event in LABELS and followup(item, event):
            return "공식 출처명·도메인 일치 확인; 공식 제목 검색색인·본문 추가 검증, 전문 직접 열람·계약 확정으로 승격하지 않음"
        return old["verification"](item, group_name, text)

    def tag(group_name):
        if not isinstance(group_name, str) or not group_name.startswith(PREFIX):
            return old["tag_for"](group_name)
        event = group_name[len(PREFIX):]
        return "로봇 후속 확인" if event in LABELS else old["tag_for"](group_name)

    def clean_title(title, source):
        # Exact reviewed/normalized titles belong to this module. A broad
        # legacy title rewriter must not replace them with another event.
        if title in protected_titles:
            return title
        return old["clean_title"](title, source)

    for name, fn in (("query_news", query), ("topic_group", group), ("score", score), ("key", key),
                     ("category", category), ("meaning", meaning), ("risk", risk), ("verification", verification), ("tag_for", tag), ("clean_title", clean_title)):
        setattr(base, name, fn)
    for q in QUERIES:
        if q not in base.QUERIES:
            base.QUERIES.append(q)
    base._nov18_verified_events_installed = True

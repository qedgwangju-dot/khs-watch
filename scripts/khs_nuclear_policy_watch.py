#!/usr/bin/env python3
"""KHS high-impact nuclear / Westinghouse / SMR policy watch."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from scripts.khs_source_fetch import fetch_text as shared_fetch_text
except ModuleNotFoundError:
    from khs_source_fetch import fetch_text as shared_fetch_text

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
OUT_DIR = Path("out")
DATA_DIR = Path("data")
SEEN_PATH = DATA_DIR / "khs_nuclear_policy_seen.json"
ALERT_PATH = OUT_DIR / "khs_nuclear_policy_alert.md"
TITLE_PATH = OUT_DIR / "khs_nuclear_policy_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_nuclear_policy_alerts.json"
MAX_SOURCE_AGE_HOURS = int(os.getenv("KHS_NUCLEAR_MAX_AGE_HOURS", "72"))
WEC_MAX_SOURCE_AGE_HOURS = int(os.getenv("KHS_WEC_MAX_AGE_HOURS", "96"))
DIRECT_FINGERPRINT_VERSION = "ko-v2"

# Westinghouse도 기사/URL 신규가 아니라 지분율·거버넌스·계약단계의 사건 상태를 감지한다.
# 전환 이전의 기사들은 최신 상태의 기준선으로만 흡수하고 소급 재발송하지 않는다.
WEC_STATE_MODEL_CUTOFF_UTC = dt.datetime(2026, 10, 2, 0, 0, tzinfo=UTC)
WEC_STATE_MODEL_VERSION = 3
# Westinghouse 지분/거버넌스 Telegram 단일 소유자는
# khs-us-investment-telegram-watch.yml 이다. 이 정책 워처는 보조 증거를
# 수집할 수 있지만 지분/이사회 기사만으로 별도 Telegram 상태변화를 만들지 않는다.
WEC_EQUITY_ALERTS_DELEGATED_TO_US_INVESTMENT = True
WEC_FIXED_BASELINE = {
    "state_key": "approval:corporate_pending|approval:due_diligence_pending|approval:regulatory_pending|stage:definitive_agreement_pending|stake_range:5~10|status:framework_nonbinding|transaction:cornerstone_equity",
    "status": "공식 프레임워크·최종계약 미체결",
    "published_utc": "2026-10-01T00:00:00+00:00",
    "title": "Westinghouse 공식 한국 지분 5~10% 잠재 투자·비구속 프레임워크",
    "source": "Westinghouse·Cameco 공식",
    "link": "https://info.westinghousenuclear.com/news/u.s.-korea-framework-advances-deployment-of-westinghouse-nuclear-technology-in-the-united-states",
}

# SMR는 새 기사 자체가 아니라 주제·사건의 구조화된 상태 변화를 감지한다.
# 이 시각 이전 검색 결과는 새 모델 전환 시 소급 알림하지 않는다.
SMR_STATE_MODEL_CUTOFF_UTC = dt.datetime(2026, 9, 20, 4, 55, tzinfo=UTC)
SMR_STATE_MODEL_VERSION = 3
# 기사·보도는 증거 수집과 교차검증용이다. SMR 알림 상태 전이는 공식 출처에서
# 동일 사건의 실제 상태 변화가 확인된 경우에만 발생시킨다.
SMR_REQUIRE_OFFICIAL_CONFIRMATION = True

# 이미 시행된 2026-09-11 특별법·시행령은 영구 기준선이다.
# 상태 파일이 손실·초기화되더라도 새 기사 재게시를 신규 사건으로 다시 보내지 않는다.
SMR_FIXED_EVENT_BASELINES = {
    "law_decree": {
        "state_key": "law_decree|effective",
        "status": "특별법·시행령 시행",
        "published_utc": "2026-09-11T00:00:00+00:00",
        "title": "SMR 특별법·시행령 시행 기준선",
        "source": "국가법령정보센터",
        "link": "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=283879",
        "official": True,
    }
}

# 미국 TVA Clinch River BWRX-300은 국내 SMR 정책축과 분리한 독립 사건축으로 추적한다.
# 2026-09-28 CPAR-2 건설허가는 이미 알림된 기준선이며 재발송하지 않는다.
BWRX_US_STATE_MODEL_VERSION = 1
BWRX_NRC_RELEASE = "https://www.nrc.gov/about-nrc/news-releases/2026/26-079"
BWRX_NRC_PROJECT = "https://www.nrc.gov/facilities-safety/new-reactors/advanced-reactors/who-were-working-with/advanced-reactor-application-projects/tva-clinch-river-cpa"
BWRX_TVA_MEDIA = "https://www.tva.com/news-media"
BWRX_TVA_PROJECT = "https://www.tva.com/energy/our-power-system/nuclear/clinch-river-small-modular-reactor"
BWRX_FIXED_BASELINE = {
    "stage": "construction_permit_issued",
    "rank": 2,
    "status": "NRC 건설허가 발급",
    "published_utc": "2026-09-29T00:00:00+00:00",
    "title": "NRC·TVA Clinch River Unit 1 BWRX-300 건설허가 발급",
    "source": "NRC·TVA 공식",
    "link": BWRX_NRC_RELEASE,
    "official": True,
}
BWRX_STAGE_RANK = {
    "construction_permit_issued": 2,
    "operating_license_application": 3,
    "capital_approval": 4,
    "major_equipment_order": 5,
    "construction_start": 6,
    "operating_license_issued": 7,
    "fuel_load": 8,
    "commissioning": 9,
    "commercial_operation": 10,
}
BWRX_STAGE_LABELS = {
    "construction_permit_issued": "NRC 건설허가 발급",
    "operating_license_application": "NRC 운영허가 신청·접수",
    "capital_approval": "TVA 최종 자본승인·투자결정",
    "major_equipment_order": "주기기·장주기 기자재 본발주",
    "construction_start": "실제 착공",
    "operating_license_issued": "NRC 운영허가 발급",
    "fuel_load": "연료장전 승인·착수",
    "commissioning": "시운전·계통연계",
    "commercial_operation": "상업운전 개시",
}
BWRX_RSS_QUERIES = [
    ("BWRX-300 미국 실행", '"BWRX-300" "Clinch River" TVA NRC construction operating license order board when:30d'),
    ("TVA Clinch River 실행", '"Clinch River" TVA "construction start" OR "operating license" OR "purchase order" OR "board approval" when:30d'),
]

# 국내 가동원전의 '규제 재가동 승인 → 실제 운전 → 발전재개/계통병입 → 100% 출력'
# 상태를 기사 신규 여부가 아니라 운전 단계로 추적한다. 한울4호기는 2026-08-19
# 자동정지를 기준선으로 잡고, 2026-10-07 재가동 승인은 교차검증된 첫 상승단계다.
HANUL4_STATE_MODEL_VERSION = 1
HANUL4_KHNP_MAIN = "https://www.khnp.co.kr/hanul/index.do"
HANUL4_KHNP_MOBILE = "https://m.khnp.co.kr/main/index.do"
HANUL4_KHNP_NPP = "https://npp.khnp.co.kr/"
HANUL4_RESTART_APPROVAL_PRIMARY = "https://www.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=04014726645610624"
HANUL4_RESTART_APPROVAL_SECONDARY = "https://mobile.newsis.com/view/NISX20261007_0003817361"
HANUL4_USER_SOURCE = "https://www.electimes.com/news/articleView.html?idxno=373171"
HANUL4_FIXED_BASELINE = {
    "kind": "domestic_reactor_operation",
    "reactor": "한울4호기",
    "stage": "automatic_trip",
    "rank": 0,
    "status": "2026-08-19 자동정지·정비",
    "published_utc": "2026-08-18T23:50:00+00:00",
    "published_kst": "2026-08-19T08:50:00+09:00",
    "title": "한울4호기 터빈발전기 정지 후 원자로 자동정지",
    "source": "한국수력원자력·한울원전환경감시센터",
    "link": HANUL4_KHNP_NPP,
    "official": True,
    "verified": True,
}
HANUL4_VERIFIED_APPROVAL = {
    "kind": "domestic_reactor_operation",
    "reactor": "한울4호기",
    "stage": "restart_approved",
    "rank": 1,
    "status": "원안위 재가동 승인",
    "published_utc": "2026-10-07T05:10:39+00:00",
    "published_kst": "2026-10-07T14:10:39+09:00",
    "title": "원안위, 한울4호기 재가동 승인",
    "source": "원안위 발표 인용 · 이데일리/뉴시스 교차확인",
    "link": HANUL4_RESTART_APPROVAL_PRIMARY,
    "secondary_link": HANUL4_RESTART_APPROVAL_SECONDARY,
    "official": False,
    "verified": True,
    "verification": "독립 언론 2곳이 원안위 2026-10-07 재가동 승인 발표를 동일하게 보도",
}
HANUL4_STAGE_RANK = {
    "automatic_trip": 0,
    "restart_approved": 1,
    "operating_status": 2,
    "generation_resumed": 3,
    "full_power": 4,
}
HANUL4_STAGE_LABELS = {
    "automatic_trip": "원자로 자동정지·정비",
    "restart_approved": "원안위 재가동 승인",
    "operating_status": "한국수력원자력 실시간 운영상태 '운전' 전환",
    "generation_resumed": "발전재개·계통병입 확인",
    "full_power": "100% 출력 도달",
}
HANUL4_RSS_QUERIES = [
    ("한울4호기 재가동 승인", '"한울 4호기" "재가동 승인" 원안위 when:7d'),
    ("한울4호기 발전재개", '"한울4호기" 발전재개 계통병입 when:14d'),
    ("한울4호기 출력회복", '"한울4호기" "100% 출력" OR "전출력" when:14d'),
    ("한울4호기 재정지", '"한울4호기" 자동정지 재정지 원자로 정지 when:14d'),
]
HANUL4_TRUSTED_OUTLETS = (
    "연합뉴스", "뉴시스", "뉴스1", "이데일리", "전기신문", "파이낸셜뉴스",
    "머니투데이", "서울경제", "한국경제", "전자신문", "조선비즈", "헤럴드경제",
)
HANUL4_OFFICIAL_OUTLETS = (
    "원자력안전위원회", "원안위", "한국수력원자력", "한수원", "정책브리핑",
)

SOURCES = [
    {"name": "Westinghouse strategic partnership", "url": "https://westinghousenuclear.com/strategic-partnership/press-releases/brookfield/"},
    {"name": "DOE Nuclear Energy", "url": "https://www.energy.gov/ne/articles/9-key-takeaways-president-trumps-executive-orders-nuclear-energy"},
]

SMR_OFFICIAL_SOURCES = [
    {
        "name": "과학기술정보통신부·정책브리핑",
        "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148971747&pWiseMinistry=ministryNews&repCode=A00033&repCodeType=%EC%A0%95%EB%B6%80%EB%B6%80%EC%B2%98",
    },
]

WEC_RSS_QUERIES = [
    ("웨스팅하우스 지분·한국 뉴스", "웨스팅하우스 지분 인수 한국전력 산업통상부 한수원 when:7d"),
    ("웨스팅하우스 최신 지분율", "웨스팅하우스 지분율 5 10 7 20 의결권 이사회 when:7d"),
    ("웨스팅하우스 지분·해외 뉴스", "Westinghouse stake Korea KEPCO KHNP Brookfield Cameco when:7d"),
    ("웨스팅하우스 지분·공식입장 추적", "웨스팅하우스 산업통상부 한국전력 공식 발표 미확정 when:14d"),
]

WEC_OFFICIAL_DIRECT_SOURCES = [
    {
        "name": "Westinghouse",
        "url": "https://info.westinghousenuclear.com/news/u.s.-korea-framework-advances-deployment-of-westinghouse-nuclear-technology-in-the-united-states",
    },
    {
        "name": "Cameco",
        "url": "https://www.cameco.com/media/news/cameco-acknowledges-united-states-and-republic-of-korea-announcement-of-framework-for",
    },
]

SMR_RSS_QUERIES = [
    ("SMR 법·제도", "SMR 소형모듈원자로 특별법 시행령 과학기술정보통신부 연구개발특구 when:14d"),
    ("SMR 사업화·실증", "SMR 소형모듈원자로 상세설계 실증 사업화 민관 공동출자 SPC 특구 when:14d"),
    ("SMR 일정·예산", "SMR 2035 2027 상세설계 비경수형 건설 예산 상용화 when:30d"),
]

NUCLEAR_TERMS = [
    "westinghouse", "ap1000", "ap300", "nuclear reactor", "nuclear reactors", "new reactors", "nuclear power", "nuclear energy",
    "uranium", "nuclear fuel", "loan guarantee", "low-cost loans", "strategic partnership", "nuclear regulatory commission", "nrc",
    "data center", "data centers", "artificial intelligence", "ai race",
]
HIGH_IMPACT_TERMS = [
    "$80 billion", "80 billion", "$17.5 billion", "17.5 billion", "10 new reactors", "10 nuclear reactors", "at least $80 billion",
    "executive order", "president trump", "department of energy", "secretary of energy", "commerce", "u.s. government",
]

WEC_CORE = ["westinghouse", "웨스팅하우스", "wec"]
WEC_TRANSACTION = [
    "지분", "인수", "투자", "공동 인수", "공동인수", "출자", "주주", "경영 참여", "stake", "equity", "acquisition", "invest",
    "shareholder", "buyout", "ipo", "상장", "기업공개", "brookfield", "브룩필드", "cameco", "카메코", "kepco", "한국전력", "한전",
    "khnp", "한수원", "산업통상부", "산업부", "미국 정부", "u.s. government", "ap1000", "지식재산", "입찰 제한",
    "이사회", "의결권", "경영권", "board seat", "board representation", "voting right", "governance",
]
WEC_MATERIAL = [
    "공식 발표", "공식 확인", "공식 부인", "사실과 다르", "부인", "합의", "계약", "loi", "mou", "양해각서", "실사", "due diligence",
    "협상 개시", "협상 착수", "본협상", "우선협상", "term sheet", "텀시트", "취득", "매각", "지분율", "인수가격", "매각가격",
    "출자액", "투자금", "경영권", "이사회", "의결권", "voting rights", "cfius", "nrc", "승인", "인가", "사업권", "설계권",
    "조달권", "시공권", "입찰 제한", "지식재산권", "상장 신청", "ipo filing", "ipo 신청",
]
WEC_COMMENTARY_OR_MARKET = [
    "고차방정식", "열쇠", "주식인가", "사업인가", "전망", "분석", "진단", "수혜", "들썩", "특징주", "상승세", "주목", "기대",
    "논란", "평가", "급등", "급락", "상승", "하락", "마감", "장중", "주가", "투자심리", "테마", "관련주",
]
WEC_STRONG_EXECUTION = [
    "공식", "합의", "계약", "loi", "mou", "양해각서", "실사", "due diligence", "협상 개시", "협상 착수", "본협상", "우선협상",
    "term sheet", "텀시트", "취득", "매각", "지분율", "인수가격", "매각가격", "출자액", "투자금", "cfius", "nrc", "승인", "인가",
    "사업권", "설계권", "조달권", "시공권", "지식재산권",
]
WEC_OFFICIAL_OUTLETS = ["산업통상부", "정책브리핑", "한국전력", "한수원", "kepco", "khnp", "westinghouse", "cameco", "brookfield"]

SMR_CORE = ["smr", "소형모듈원자로", "소형모듈원전", "소형 모듈 원자로", "소형 모듈 원전"]
SMR_MATERIAL = [
    "특별법", "시행령", "제정", "시행", "기본계획", "시행계획", "촉진위원회", "예산", "지원금", "출자", "공동출자", "공동 출자",
    "spc", "특수목적법인", "상세설계", "실증", "사업화", "연구개발특구", "특구", "건설", "상용화", "착수", "승인", "허가",
    "공모", "선정", "협약", "수주", "핵연료 공급망", "핵연료 공급계약", "표준설계인가", "표준설계승인", "건설허가",
    "주기기", "epc", "발주", "계약", "전문인력", "규제 개선", "비경수형", "경수형",
]
SMR_STRONG = [
    "특별법", "시행령", "시행", "기본계획", "시행계획", "예산", "출자", "공동출자", "공동 출자", "spc", "특수목적법인",
    "상세설계", "실증", "사업화", "연구개발특구", "특구", "표준설계인가", "표준설계승인", "건설허가", "핵연료 공급계약",
    "주기기", "epc", "발주", "계약", "건설", "상용화", "착수", "승인", "허가", "공모", "선정", "협약",
]
SMR_COMMENTARY_OR_MARKET = ["전망", "분석", "진단", "수혜", "특징주", "급등", "급락", "상승", "하락", "주가", "테마", "관련주", "기대감"]
SMR_OFFICIAL_OUTLETS = [
    "과학기술정보통신부", "과기정통부", "정책브리핑", "대한민국 정책브리핑", "국가법령정보센터", "법제처",
    "산업통상부", "기후에너지환경부", "한국원자력연구원", "한국수력원자력", "한수원", "원자력안전위원회",
]
SMR_SIGNALS = [
    "특별법", "시행령", "시행", "2035", "2030년대", "2027", "상세설계", "공동출자", "공동 출자", "spc", "특수목적법인",
    "연구개발특구", "특구", "실증", "사업화", "비경수형", "경수형", "핵연료 공급망", "핵연료 공급계약", "촉진위원회",
    "기본계획", "시행계획", "표준설계인가", "표준설계승인", "건설허가", "주기기", "epc", "발주", "계약",
]

SOURCE_LABELS = {
    "Westinghouse strategic partnership": "Westinghouse 공식 전략 파트너십 발표",
    "DOE Nuclear Energy": "미국 에너지부 원전정책 공식자료",
}
TERM_LABELS = {
    "$80 billion": "최소 800억 달러 규모", "80 billion": "800억 달러", "$17.5 billion": "175억 달러", "17.5 billion": "175억 달러",
    "10 new reactors": "신규 원전 10기", "10 nuclear reactors": "원전 10기", "at least $80 billion": "최소 800억 달러",
    "executive order": "행정명령", "president trump": "트럼프 대통령", "department of energy": "미국 에너지부",
    "secretary of energy": "미국 에너지부 장관", "commerce": "상무부", "u.s. government": "미국 정부", "westinghouse": "Westinghouse",
    "ap1000": "AP1000", "ap300": "AP300", "nuclear reactor": "원자로", "nuclear reactors": "원자로", "new reactors": "신규 원전",
    "nuclear power": "원전", "nuclear energy": "원자력 에너지", "uranium": "우라늄", "nuclear fuel": "핵연료", "loan guarantee": "대출보증",
    "low-cost loans": "저리 대출", "strategic partnership": "전략적 파트너십", "nuclear regulatory commission": "미 원자력규제위원회",
    "nrc": "미 원자력규제위원회", "data center": "데이터센터", "data centers": "데이터센터", "artificial intelligence": "인공지능", "ai race": "AI 경쟁",
}


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_text(url: str) -> str:
    text, error = shared_fetch_text(
        url,
        "KHS-nuclear-policy-watch contact=github-actions",
        timeout=20,
        attempts=2,
    )
    if error is not None or text is None:
        raise RuntimeError(error or "empty response")
    return text


def parse_date(text: str) -> dt.datetime | None:
    patterns = [
        (r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b", ("%B %d, %Y", "%b %d, %Y")),
        (r"\b20\d{2}-\d{2}-\d{2}\b", ("%Y-%m-%d",)),
        (r"\b20\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.?\b", ("%Y.%m.%d", "%Y. %m. %d.")),
    ]
    for pattern, formats in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        candidate = re.sub(r"\s+", " ", match.group(0)).strip()
        for fmt in formats:
            try:
                return dt.datetime.strptime(candidate, fmt).replace(tzinfo=KST)
            except ValueError:
                pass
    return None


def title_from_text(text: str, fallback: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
    return clean_text(match.group(1)) if match else fallback


def collect_direct_items(now: dt.datetime) -> list[dict]:
    items: list[dict] = []
    for source in SOURCES:
        try:
            raw = fetch_text(source["url"])
        except Exception as exc:
            print(f"nuclear_source_error={source['name']} {exc}")
            continue
        title = title_from_text(raw, source["name"])
        body = clean_text(raw)
        published = parse_date(body)
        if published and (now - published).total_seconds() / 3600 > MAX_SOURCE_AGE_HOURS:
            continue
        haystack = f"{title} {body}".lower()
        matched = [term for term in NUCLEAR_TERMS + HIGH_IMPACT_TERMS if term.lower() in haystack]
        if not any(term in matched for term in NUCLEAR_TERMS) or not any(term in matched for term in HIGH_IMPACT_TERMS):
            continue
        fingerprint = hashlib.sha256(f"{DIRECT_FINGERPRINT_VERSION}|{source['name']}|{title}|{source['url']}".encode("utf-8")).hexdigest()[:16]
        items.append({
            "kind": "direct_official", "fingerprint": fingerprint, "source": source["name"], "title": title, "link": source["url"],
            "published_kst": published.isoformat() if published else "확인 불가", "matched": sorted(set(matched))[:12],
        })
    return items


def _google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"


def _clean_rss_title(title: str) -> str:
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", clean_text(title)).strip()


def _is_official_outlet(outlet: str) -> bool:
    low = (outlet or "").lower()
    return any(term.lower() in low for term in WEC_OFFICIAL_OUTLETS)


def _has_numeric_terms(title: str) -> bool:
    return bool(re.search(r"(?:\$|달러|원|억원|조원|%|퍼센트).*?\d|\d[\d,.]*\s*(?:억달러|달러|억원|조원|%)", title.lower()))


def _wec_state_facts(title: str, outlet: str = "") -> tuple[str, ...]:
    low = title.lower()
    facts: list[str] = []

    # 지분 범위는 단일 퍼센트보다 먼저 정규화한다.
    range_spans: list[tuple[int, int]] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:~|∼|–|—|-)\s*(\d+(?:\.\d+)?)\s*%", low):
        facts.append(f"stake_range:{match.group(1)}~{match.group(2)}")
        range_spans.append(match.span())

    scrubbed = low
    for start, end in reversed(range_spans):
        scrubbed = scrubbed[:start] + " " * (end - start) + scrubbed[end:]

    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%?\s*\+\s*(?:α|알파|alpha)", scrubbed):
        facts.append(f"stake:{match.group(1)}+alpha")
        scrubbed = scrubbed.replace(match.group(0), " ")

    # '한국 20% 요구, 미국 7% 고수/제시'처럼 양측 숫자가 함께 나오는 경우는
    # 협상 양쪽의 상태값을 별도 슬롯으로 보존한다.
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(?:이상\s*)?(?:요구|목표|원해|희망)", scrubbed):
        facts.append(f"stake_korea_request:{match.group(1)}")
    for match in re.finditer(r"(?:미국(?:측)?[^\d%]{0,30})?(\d+(?:\.\d+)?)\s*%\s*(?:고수|제시|상한)", scrubbed):
        facts.append(f"stake_us_offer:{match.group(1)}")

    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", scrubbed):
        facts.append(f"stake:{match.group(1)}")

    # 양측 요구/제시로 역할이 명시된 숫자는 일반 지분 숫자로 이중 저장하지 않는다.
    if any(fact.startswith(("stake_korea_request:", "stake_us_offer:")) for fact in facts):
        facts = [fact for fact in facts if not fact.startswith("stake:")]

    # 지분과 직접 연결된 가격·출자액만 상태값으로 사용한다.
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(억|조)\s*달러", low):
        facts.append(f"price:{match.group(1)}{match.group(2)}달러")
    if "ipo" in low and ("할인" in low or "discount" in low):
        facts.append("pricing:ipo_discount")

    if "이사회" in low or "board seat" in low or "board representation" in low:
        # '진입 노린다/추진/가능/목표/검토'는 권리 확보가 아니라 협상 기대다.
        # 물질적 상태 변화는 실제 지명권·이사회석 확보 또는 명시적 제한이 확인될 때만 만든다.
        speculative_board = any(term in low for term in (
            "노린", "추진", "목표", "가능", "관심", "검토", "협의", "협상",
            "aim", "seek", "seeking", "target", "possible", "consider", "negotiat",
        ))
        if any(term in low for term in ("어려", "불가", "못해", "힘들", "부담", "difficult", "unlikely", "reluctant")):
            facts.append("governance:board_limited")
        elif any(term in low for term in (
            "확보", "합의", "선임", "지명권", "진입 확정",
            "secured", "agreed", "appointed", "appointment right", "nomination right",
        )) and not speculative_board:
            facts.append("governance:board")
    if "의결권" in low or "voting right" in low:
        facts.append("governance:voting_possible")

    if any(term in low for term in ("사실과 다르", "공식 부인", "부인", "정해진 바 없", "미확정", "not confirmed", "not decided")):
        facts.append("status:unconfirmed")
    elif any(term in low for term in ("최종 확정", "공식 확정", "확정 발표", "signed agreement", "officially confirmed")):
        facts.append("status:confirmed")
    elif any(term in low for term in ("non-binding", "nonbinding", "비구속")):
        facts.append("status:framework_nonbinding")

    if any(term in low for term in ("subject to definitive agreements", "definitive agreements", "final negotiations", "최종 계약 필요", "본계약 후속")):
        facts.append("stage:definitive_agreement_pending")
    elif any(term in low for term in ("실사", "due diligence")):
        facts.append("stage:due_diligence")
    elif any(term in low for term in ("loi", "mou", "양해각서", "term sheet", "텀시트")):
        facts.append("stage:pre_contract")
    elif any(term in low for term in ("본협상", "협상 개시", "협상 착수", "협의 중", "협의중", "negotiat")):
        facts.append("stage:negotiation")
    elif any(term in low for term in ("계약 체결", "합의 체결", "취득 완료", "인수 완료")):
        facts.append("stage:contracted")

    if any(term in low for term in ("due diligence", "실사 필요")) and not any(term in low for term in ("due diligence completed", "실사 완료")):
        facts.append("approval:due_diligence_pending")
    if any(term in low for term in ("regulatory approvals", "regulatory approval", "규제 승인 필요")):
        facts.append("approval:regulatory_pending")
    if any(term in low for term in ("corporate approvals", "corporate approval", "회사 승인 필요")):
        facts.append("approval:corporate_pending")
    if any(term in low for term in ("cornerstone equity investment", "potential equity investment")):
        facts.append("transaction:cornerstone_equity")

    return tuple(sorted(dict.fromkeys(facts)))


def _is_material_westinghouse(title: str, outlet: str = "") -> bool:
    low = title.lower()
    if not (any(term in low for term in WEC_CORE) and any(term in low for term in WEC_TRANSACTION)):
        return False

    facts = _wec_state_facts(title, outlet)
    if _is_official_outlet(outlet):
        # 공식 출처는 미확정·부인·확정·계약단계처럼 실제 상태를 말할 때만 통과.
        return bool(facts) or any(term in low for term in ("공식 발표", "공식 확인", "사실과 다르"))

    # 시장반응 기사에서 나온 6%·7% 등은 주가 등락률일 수 있으므로,
    # 지분율·계약·실사·가격 등 강한 거래상태 표현이 같이 있을 때만 통과시킨다.
    if any(term in low for term in WEC_COMMENTARY_OR_MARKET):
        return bool(facts) and any(term in low for term in WEC_STRONG_EXECUTION)

    # '지분율 줄다리기', '검토', '논란'처럼 숫자·거버넌스·계약단계가 없는
    # 일반 서술은 새로운 사건 상태가 아니다.
    return bool(facts)


def _self_test_material_filter() -> None:
    if _is_material_westinghouse("[특징주] 한전, 웨스팅하우스 지분투자설에 6%대 급등 마감", "연합뉴스"):
        raise RuntimeError("Westinghouse market-reaction filter regression")
    if _is_material_westinghouse("한전, 웨스팅하우스 지분확보설에 장중 7%대 급등", "연합뉴스"):
        raise RuntimeError("Westinghouse intraday-price filter regression")
    if not _is_material_westinghouse("한국전력, 웨스팅하우스 지분 인수 실사 착수…지분율 10% 협상", "연합뉴스"):
        raise RuntimeError("Westinghouse execution-state filter regression")
    if not _is_material_westinghouse("웨스팅하우스 지분 공동인수 보도는 사실과 다르다", "산업통상부"):
        raise RuntimeError("Westinghouse official-state filter regression")
    if _is_material_westinghouse("원전 투자 앞둔 정부, 미국과 웨스팅하우스 지분율 줄다리기", "news.sbs.co.kr"):
        raise RuntimeError("Westinghouse generic-stake-wording regression")
    if not _is_material_westinghouse("웨스팅하우스 지분 5~10% 인수…의결권 가능", "한국경제"):
        raise RuntimeError("Westinghouse concrete-stake-range regression")
    if _is_material_westinghouse("시공 넘어 경영 참여로… 韓 기업, 웨스팅하우스 이사회 진입 노린다", "IT조선"):
        raise RuntimeError("Westinghouse speculative-board-headline must not trigger material state change")
    if not _is_material_westinghouse("Westinghouse 공식 한국 측 이사회 지명권 확보 합의", "Westinghouse"):
        raise RuntimeError("Westinghouse confirmed-board-right must remain material")
    official_framework = _wec_state_key(
        "Westinghouse 공식 한국 지분 5~10% cornerstone equity investment terms non-binding subject to definitive agreements due diligence corporate approvals regulatory approvals",
        "Westinghouse",
    )
    for expected_fact in (
        "stake_range:5~10",
        "status:framework_nonbinding",
        "stage:definitive_agreement_pending",
        "approval:due_diligence_pending",
        "approval:corporate_pending",
        "approval:regulatory_pending",
        "transaction:cornerstone_equity",
    ):
        if expected_fact not in official_framework:
            raise RuntimeError(f"Westinghouse official framework parsing regression: {expected_fact} missing from {official_framework}")
    wec_a = _wec_state_key("웨스팅하우스 지분 5~10% 인수…의결권 가능", "한국경제")
    wec_b = _wec_state_key("웨스팅하우스 지분 5∼10% 협의, 의결권 행사 가능", "뉴시스")
    if wec_a != wec_b:
        raise RuntimeError(f"Westinghouse same-event semantic dedupe regression: {wec_a} != {wec_b}")
    alpha_state = _wec_state_key("韓 웨스팅하우스 지분 투자 7+α 타진 중…이사회 진입 어려울 듯", "한국경제")
    if "stake:7+alpha" not in alpha_state or "governance:board_limited" not in alpha_state:
        raise RuntimeError(f"Westinghouse alpha-stake parsing regression: {alpha_state}")
    split_state = _wec_state_key("웨스팅하우스 지분율 20% 요구에 미국은 7% 고수", "연합뉴스")
    if "stake_korea_request:20" not in split_state or "stake_us_offer:7" not in split_state:
        raise RuntimeError(f"Westinghouse bilateral-stake parsing regression: {split_state}")
    if _is_material_smr("[특징주] SMR 관련주 급등", "언론사"):
        raise RuntimeError("SMR market-reaction filter regression")
    if not _is_material_smr("SMR 특별법·시행령 11일 시행…민관 공동출자 지원", "정책브리핑"):
        raise RuntimeError("SMR policy-state filter regression")
    law_a = _smr_state_key("SMR 특별법 11일 시행, 정부는 2035년까지 경수형 상용화 목표", False)
    law_b = _smr_state_key("SMR 개발·상용화 속도 낸다…SMR 특별법·시행령 오늘 시행", False)
    if law_a != law_b:
        raise RuntimeError("SMR same-event article dedupe regression")
    budget_a = _smr_state_key("SMR 실증 예산 1,000억원 확정", True)
    budget_b = _smr_state_key("SMR 실증 예산 2,000억원 확정", True)
    if budget_a == budget_b:
        raise RuntimeError("SMR budget-state change regression")
    reported_only = [
        {"official": False, "published_utc": "2026-09-20T06:00:00+00:00", "title": "언론 보도"},
    ]
    if _select_smr_state_candidate(reported_only) is not None:
        raise RuntimeError("SMR reported-only evidence must not trigger alert regression")
    mixed_evidence = [
        {
            "official": False,
            "published_utc": "2026-09-20T06:00:00+00:00",
            "title": "새 기사",
            "event_family": "budget",
        },
        {
            "official": True,
            "published_utc": "2026-09-20T05:30:00+00:00",
            "title": "SMR 실증 예산안 1,000억원 정부안 확정",
            "event_family": "budget",
        },
    ]
    selected = _select_smr_state_candidate(mixed_evidence)
    if not selected or not selected.get("official"):
        raise RuntimeError("SMR official-state selection regression")
    support_only = [
        {
            "official": True,
            "published_utc": "2026-09-20T06:10:00+00:00",
            "title": "SMR 특별법 시행…표준설계인가·건설허가 지원체계 마련",
            "event_family": "standard_design_approval",
        }
    ]
    if _select_smr_state_candidate(support_only) is not None:
        raise RuntimeError("SMR support-only wording must not become approval-state alert")
    schedule_change = [
        {
            "official": True,
            "published_utc": "2026-09-20T06:20:00+00:00",
            "title": "i-SMR 표준설계인가 2028년 신청 예정",
            "event_family": "standard_design_approval",
        }
    ]
    if _select_smr_state_candidate(schedule_change) is None:
        raise RuntimeError("SMR official approval-schedule change must remain alertable")


def _wec_status(title: str, outlet: str = "") -> str:
    low = title.lower()
    if any(term in low for term in ("사실과 다르", "공식 부인", "부인", "denies", "not true")):
        return "공식 부인·정정" if _is_official_outlet(outlet) or "공식" in low else "부인 보도"
    if any(term in low for term in ("non-binding", "nonbinding", "비구속")) and any(term in low for term in ("definitive agreement", "final negotiation", "최종 계약", "본계약")):
        return "공식 프레임워크·최종계약 미체결"
    if any(term in low for term in ("계약", "합의", "agreement", "contract")):
        return "계약·합의 단계"
    if any(term in low for term in ("loi", "mou", "양해각서", "term sheet", "텀시트")):
        return "LOI·MOU·텀시트 단계"
    if any(term in low for term in ("실사", "due diligence")):
        return "실사 단계"
    if any(term in low for term in ("협상 개시", "협상 착수", "본협상", "우선협상")):
        return "협상 단계"
    if any(term in low for term in ("취득", "매각", "인수 확정", "투자 확정")):
        return "지분 거래 확정 신호"
    if any(term in low for term in ("cfius", "nrc", "승인", "인가")):
        return "규제·승인 단계"
    if any(term in low for term in ("사업권", "설계권", "조달권", "시공권", "입찰 제한", "지식재산권")):
        return "사업권·지식재산 조건 변화"
    if any(term in low for term in ("지분율", "인수가격", "매각가격", "출자액", "투자금")) or _has_numeric_terms(title):
        return "지분율·가격 등 거래조건 변화"
    if _is_official_outlet(outlet):
        return "공식 입장 변화"
    return "새 물질적 조건 확인"


def _wec_numbers(title: str) -> tuple[str, ...]:
    found = re.findall(r"\d[\d,.]*(?:\s*)?(?:%|퍼센트|억달러|달러|억원|조원|원)", title, flags=re.I)
    return tuple(dict.fromkeys(re.sub(r"\s+", "", value) for value in found))[:6]


def _wec_state_key(title: str, outlet: str = "") -> str:
    facts = _wec_state_facts(title, outlet)
    return "|".join(facts) if facts else "no-concrete-state"


def _wec_fact_slot(fact: str) -> str:
    if fact.startswith("stake:"):
        return "stake_current"
    if fact.startswith("stake_range:"):
        return "stake_range"
    if fact.startswith("stake_korea_request:"):
        return "stake_korea_request"
    if fact.startswith("stake_us_offer:"):
        return "stake_us_offer"
    if fact.startswith("governance:board"):
        return "board"
    if fact.startswith("governance:voting"):
        return "voting"
    if fact.startswith("status:"):
        return "status"
    if fact.startswith("stage:"):
        return "stage"
    if fact.startswith(("price:", "pricing:")):
        return "pricing"
    if fact.startswith("approval:due_diligence"):
        return "due_diligence"
    if fact.startswith("approval:regulatory"):
        return "regulatory_approval"
    if fact.startswith("approval:corporate"):
        return "corporate_approval"
    if fact.startswith("transaction:"):
        return "transaction_type"
    return fact


def _wec_merge_state(previous_key: str, current_key: str) -> tuple[bool, str]:
    previous_facts = [x for x in (previous_key or "").split("|") if x and x != "no-concrete-state"]
    current_facts = [x for x in (current_key or "").split("|") if x and x != "no-concrete-state"]

    previous_by_slot = {_wec_fact_slot(fact): fact for fact in previous_facts}
    current_by_slot = {_wec_fact_slot(fact): fact for fact in current_facts}

    changed = any(previous_by_slot.get(slot) != fact for slot, fact in current_by_slot.items())
    merged = dict(previous_by_slot)
    merged.update(current_by_slot)
    merged_key = "|".join(sorted(merged.values())) if merged else "no-concrete-state"
    return changed, merged_key


def collect_westinghouse_stake_items(now: dt.datetime) -> list[dict]:
    rows: list[dict] = []
    seen_story: set[str] = set()

    for source in WEC_OFFICIAL_DIRECT_SOURCES:
        try:
            raw = fetch_text(source["url"])
        except Exception as exc:
            print(f"westinghouse_official_error={source['name']} {exc}")
            continue
        body = clean_text(raw)
        low = body.lower()
        if "westinghouse" not in low or not any(term in low for term in ["5% and 10%", "5% to 10%", "5%~10%", "5-10%", "potential equity investment", "cornerstone equity investment"]):
            continue
        published = parse_date(body) or now
        if (now - published).total_seconds() / 3600 > WEC_MAX_SOURCE_AGE_HOURS:
            continue
        normalized_parts = [f"{source['name']} 공식 한국 Westinghouse 지분투자"]
        if any(term in low for term in ["5% and 10%", "5% to 10%", "5%~10%", "5-10%"]):
            normalized_parts.append("지분 5~10%")
        if "cornerstone equity investment" in low:
            normalized_parts.append("cornerstone equity investment")
        elif "potential equity investment" in low:
            normalized_parts.append("potential equity investment")
        if "non-binding" in low or "nonbinding" in low:
            normalized_parts.append("terms non-binding")
        if "subject to definitive agreements" in low or "definitive agreements" in low or "final negotiations" in low:
            normalized_parts.append("definitive agreements pending")
        if "due diligence" in low:
            normalized_parts.append("due diligence")
        if "corporate approvals" in low or "corporate approval" in low:
            normalized_parts.append("corporate approvals")
        if "regulatory approvals" in low or "regulatory approval" in low:
            normalized_parts.append("regulatory approvals")
        normalized = " ".join(normalized_parts)
        state_text = normalized
        story_key = f"official|{source['name'].lower()}|2026-09-30|westinghouse-equity-framework"
        if story_key in seen_story:
            continue
        seen_story.add(story_key)
        pub_utc = published.astimezone(UTC)
        rows.append({
            "kind": "westinghouse_stake",
            "source": source["name"],
            "title": normalized,
            "link": source["url"],
            "published_kst": pub_utc.astimezone(KST).isoformat(timespec="seconds"),
            "published_utc": pub_utc.isoformat(timespec="seconds"),
            "state_key": _wec_state_key(state_text, source["name"]),
            "status": _wec_status(state_text, source["name"]),
            "matched": ["westinghouse", "stake", "korea", "official", "5~10", "non-binding"],
            "official": True,
        })

    for source_name, query in WEC_RSS_QUERIES:
        try:
            root = ET.fromstring(fetch_text(_google_news_url(query)))
        except Exception as exc:
            print(f"westinghouse_rss_error={source_name} {exc}")
            continue
        for node in root.findall(".//item"):
            title = _clean_rss_title(node.findtext("title") or "")
            link = clean_text(node.findtext("link") or "")
            source_node = node.find("source")
            outlet = clean_text(source_node.text if source_node is not None and source_node.text else source_name)
            pub_text = clean_text(node.findtext("pubDate") or "")
            if not title or not link or not _is_material_westinghouse(title, outlet):
                continue
            try:
                published = parsedate_to_datetime(pub_text)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
                published = published.astimezone(UTC)
            except Exception:
                published = now.astimezone(UTC)
            if (now.astimezone(UTC) - published).total_seconds() / 3600 > WEC_MAX_SOURCE_AGE_HOURS:
                continue
            story_key = f"{title.lower()}|{outlet.lower()}"
            if story_key in seen_story:
                continue
            seen_story.add(story_key)
            rows.append({
                "kind": "westinghouse_stake", "source": outlet or source_name, "title": title[:500], "link": link,
                "published_kst": published.astimezone(KST).isoformat(timespec="seconds"), "published_utc": published.isoformat(timespec="seconds"),
                "state_key": _wec_state_key(title, outlet), "status": _wec_status(title, outlet), "matched": ["westinghouse", "stake", "korea"],
                "official": _is_official_outlet(outlet),
            })
    rows.sort(key=lambda item: item.get("published_utc", ""), reverse=True)
    return rows[:20]


def _is_smr_official_outlet(outlet: str) -> bool:
    low = (outlet or "").lower()
    return any(term.lower() in low for term in SMR_OFFICIAL_OUTLETS)


def _is_material_smr(text: str, outlet: str = "") -> bool:
    low = text.lower()
    if not any(term in low for term in SMR_CORE):
        return False
    if any(term in low for term in SMR_COMMENTARY_OR_MARKET):
        return any(term in low for term in SMR_STRONG)
    if _is_smr_official_outlet(outlet):
        return any(term in low for term in SMR_MATERIAL)
    return any(term in low for term in SMR_STRONG)


def _smr_status(text: str) -> str:
    low = text.lower()
    # 구체 인허가·계약 상태를 일반적인 "건설"보다 먼저 판별한다.
    if "표준설계인가" in low or "표준설계승인" in low:
        return "표준설계인가"
    if "건설허가" in low:
        return "건설허가"
    if "핵연료 공급계약" in low or ("핵연료" in low and "계약" in low):
        return "핵연료 공급망·계약"
    if ("주기기" in low or "epc" in low) and any(term in low for term in ("발주", "계약", "수주", "우선협상", "선정")):
        return "주기기·EPC 발주"
    if "특별법" in low and ("시행" in low or "시행령" in low):
        return "특별법·시행령 시행"
    if "기본계획" in low or "시행계획" in low:
        return "기본계획·시행계획"
    if "상세설계" in low and ("착수" in low or "2027" in low):
        return "상세설계 착수 일정"
    if "공동출자" in low or "공동 출자" in low or "spc" in low or "특수목적법인" in low:
        return "민관 공동출자·사업화 구조"
    if "연구개발특구" in low or "특구" in low:
        return "SMR 연구개발특구"
    if "예산" in low or "지원금" in low:
        return "예산·재정지원"
    if "실증" in low:
        return "실증 지원"
    if "상용화" in low or "건설" in low:
        return "상용화·건설 일정"
    return "SMR 정책 상태변화"


def _smr_signals(text: str) -> list[str]:
    low = text.lower()
    found = [term for term in SMR_SIGNALS if term.lower() in low]
    years = re.findall(r"20(?:2\d|3\d)(?:년대|년)?", text)
    return list(dict.fromkeys(found + years))[:12]


def _smr_event_family(text: str) -> str:
    status = _smr_status(text)
    return {
        "특별법·시행령 시행": "law_decree",
        "기본계획·시행계획": "basic_plan",
        "상세설계 착수 일정": "detailed_design",
        "민관 공동출자·사업화 구조": "joint_venture",
        "SMR 연구개발특구": "special_zone",
        "예산·재정지원": "budget",
        "실증 지원": "demonstration",
        "핵연료 공급망·계약": "nuclear_fuel",
        "표준설계인가": "standard_design_approval",
        "건설허가": "construction_permit",
        "주기기·EPC 발주": "epc_major_equipment",
        "상용화·건설 일정": "commercialization",
    }.get(status, "other")


def _smr_material_facts(text: str, family: str) -> list[str]:
    """기사 문구가 아니라 실제 상태를 바꾸는 구조화 사실만 상태키에 넣는다."""
    low = text.lower()
    facts: list[str] = []

    # 동일 법 시행을 기사별 목표연도·매체 표현 차이로 다시 알리지 않는다.
    if family == "law_decree":
        return ["effective"]

    stage_terms = [
        ("공포", "promulgated"),
        ("시행", "effective"),
        ("수립 착수", "planning_started"),
        ("착수", "started"),
        ("신청", "applied"),
        ("접수", "filed"),
        ("공모", "tender_open"),
        ("우선협상", "preferred_bidder"),
        ("선정", "selected"),
        ("지정", "designated"),
        ("의결", "approved"),
        ("승인", "approved"),
        ("인가", "approved"),
        ("허가", "permitted"),
        ("체결", "contracted"),
        ("계약", "contracted"),
        ("확정", "confirmed"),
        ("편성", "budgeted"),
        ("배정", "allocated"),
    ]
    for needle, label in stage_terms:
        if needle in low and label not in facts:
            facts.append(label)

    money = re.findall(
        r"\d[\d,.]*(?:\s*)?(?:조원|억원|만원|원|억\s*원|조\s*원|억달러|만달러|달러)",
        text,
        flags=re.I,
    )
    facts.extend(f"money:{re.sub(r'\s+', '', value)}" for value in dict.fromkeys(money))

    quantities = re.findall(r"\d[\d,.]*(?:\s*)?(?:기|MW|GW|MWe|GWe)", text, flags=re.I)
    facts.extend(f"qty:{re.sub(r'\s+', '', value)}" for value in dict.fromkeys(quantities))

    if family in {"special_zone", "demonstration", "construction_permit", "commercialization"}:
        regions = [
            "부산", "기장", "경주", "울산", "대전", "세종", "충북", "충남", "전북", "전남",
            "경북", "경남", "강원", "제주", "서울", "인천", "광주", "대구",
        ]
        facts.extend(f"region:{region}" for region in regions if region in text)

    if family in {"basic_plan", "detailed_design", "standard_design_approval", "construction_permit", "commercialization"}:
        years = re.findall(r"20(?:2\d|3\d)(?:년대|년)?", text)
        facts.extend(f"year:{year}" for year in dict.fromkeys(years))

    return facts or ["state_present"]


def _smr_state_key(text: str, official: bool) -> str:
    # official/reported, 기사 제목, 매체, URL은 증거 수준일 뿐 사건 상태 식별자에 넣지 않는다.
    family = _smr_event_family(text)
    facts = _smr_material_facts(text, family)
    return f"{family}|{'|'.join(facts)}"


def collect_smr_policy_items(now: dt.datetime) -> list[dict]:
    rows: list[dict] = []
    seen_story: set[str] = set()

    for source in SMR_OFFICIAL_SOURCES:
        try:
            raw = fetch_text(source["url"])
        except Exception as exc:
            print(f"smr_official_error={source['name']} {exc}")
            continue
        title = title_from_text(raw, source["name"])
        body = clean_text(raw)
        text = f"{title} {body}"
        published = parse_date(body)
        if not _is_material_smr(text, source["name"]):
            continue
        if published and (now - published).total_seconds() / 3600 > MAX_SOURCE_AGE_HOURS:
            continue
        pub_utc = published.astimezone(UTC) if published else now.astimezone(UTC)
        rows.append({
            "kind": "smr_policy", "source": source["name"], "title": title[:500], "link": source["url"],
            "published_kst": pub_utc.astimezone(KST).isoformat(timespec="seconds"), "published_utc": pub_utc.isoformat(timespec="seconds"),
            "status": _smr_status(text), "event_family": _smr_event_family(text),
            "state_key": _smr_state_key(text, True), "signals": _smr_signals(text), "official": True,
        })

    for source_name, query in SMR_RSS_QUERIES:
        try:
            root = ET.fromstring(fetch_text(_google_news_url(query)))
        except Exception as exc:
            print(f"smr_rss_error={source_name} {exc}")
            continue
        for node in root.findall(".//item"):
            title = _clean_rss_title(node.findtext("title") or "")
            link = clean_text(node.findtext("link") or "")
            source_node = node.find("source")
            outlet = clean_text(source_node.text if source_node is not None and source_node.text else source_name)
            pub_text = clean_text(node.findtext("pubDate") or "")
            if not title or not link or not _is_material_smr(title, outlet):
                continue
            try:
                published = parsedate_to_datetime(pub_text)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
                published = published.astimezone(UTC)
            except Exception:
                published = now.astimezone(UTC)
            if (now.astimezone(UTC) - published).total_seconds() / 86400 > 30:
                continue
            story_key = f"{title.lower()}|{outlet.lower()}"
            if story_key in seen_story:
                continue
            seen_story.add(story_key)
            official = _is_smr_official_outlet(outlet)
            rows.append({
                "kind": "smr_policy", "source": outlet or source_name, "title": title[:500], "link": link,
                "published_kst": published.astimezone(KST).isoformat(timespec="seconds"), "published_utc": published.isoformat(timespec="seconds"),
                "status": _smr_status(title), "event_family": _smr_event_family(title),
                "state_key": _smr_state_key(title, official), "signals": _smr_signals(title), "official": official,
            })

    def score(item: dict) -> tuple[str, int, int]:
        return (item.get("published_utc", ""), 1 if item.get("official") else 0, len(item.get("signals") or []))

    rows.sort(key=score, reverse=True)
    return rows[:20]


def _is_actionable_smr_state(item: dict) -> bool:
    """단순 언급·법 설명이 아니라 실제 단계/일정/금액이 움직인 공식 상태만 통과시킨다."""
    family = str(item.get("event_family") or "")
    title = str(item.get("title") or "")
    low = title.lower()

    if family == "law_decree":
        return True

    # 정책·제도 문서가 인가/허가/계약을 '지원한다'고 설명한 것만으로
    # 인가·허가·계약 완료 상태로 오인하지 않는다.
    support_only = any(term in low for term in ("지원", "근거", "절차", "제도", "촉진", "지원체계"))
    actual_verbs = any(
        term in low
        for term in (
            "확정", "의결", "공고", "공모", "착수", "신청", "접수", "체결", "서명",
            "선정", "지정", "설립", "출자액", "지분", "주주", "배정", "편성",
            "획득", "발급", "취득", "완료", "가동", "착공", "수주", "발주",
        )
    )
    has_schedule = bool(re.search(r"20(?:2\d|3\d)(?:년대|년)?", title)) and any(
        term in low for term in ("일정", "목표", "예정", "계획", "착수")
    )
    has_money = bool(
        re.search(r"\d[\d,.]*\s*(?:조원|억원|만원|원|억\s*원|조\s*원|억달러|만달러|달러)", title, re.I)
    )

    if family == "basic_plan":
        return any(term in low for term in ("수립 착수", "수립에 착수", "수립 완료", "수립 확정", "기본계획 확정", "기본계획 의결")) or has_schedule

    if family == "detailed_design":
        return any(term in low for term in ("상세설계 착수", "상세설계 계약", "상세설계 용역", "사업자 선정", "공모")) or has_schedule

    if family == "joint_venture":
        return any(term in low for term in ("법인 설립", "spc 설립", "특수목적법인 설립", "출자 확정", "출자액", "지분", "주주")) or (has_money and actual_verbs)

    if family == "special_zone":
        if any(term in low for term in ("지정 추진", "지정 검토", "지정 계획", "지정 예정")) and not has_schedule:
            return False
        return any(term in low for term in ("특구 지정", "특구 선정", "후보지 선정", "지정 공고", "공모")) and (actual_verbs or has_schedule)

    if family == "budget":
        return has_money and any(term in low for term in ("예산안", "편성", "배정", "확정", "의결", "정부안", "국회"))

    if family == "demonstration":
        return any(term in low for term in ("실증 착수", "실증부지", "실증 부지", "사업자 선정", "공모", "협약", "계약")) and (actual_verbs or has_money or has_schedule)

    if family == "nuclear_fuel":
        return any(term in low for term in ("공급계약 체결", "공급 계약 체결", "공급사 선정", "핵연료 계약 확정", "핵연료 공급 계약")) and not any(
            term in low for term in ("계약 검토", "계약 추진", "계약 계획")
        )

    if family == "standard_design_approval":
        # '표준설계인가 지원/절차'는 상태 변화가 아니다. 신청·접수·획득 또는
        # 공식 일정 변경처럼 실제 시간표가 움직였을 때만 통과한다.
        return bool(
            re.search(
                r"표준설계(?:인가|승인).{0,24}(?:신청|접수|획득|발급|취득|완료|확정|받았|받음|일정|목표|예정)",
                title,
            )
            or re.search(
                r"(?:신청|접수|획득|발급|취득|완료|확정).{0,24}표준설계(?:인가|승인)",
                title,
            )
        ) and (actual_verbs or has_schedule)

    if family == "construction_permit":
        return bool(
            re.search(
                r"건설허가.{0,24}(?:신청|접수|획득|발급|취득|완료|확정|받았|받음|일정|목표|예정)",
                title,
            )
            or re.search(
                r"(?:신청|접수|획득|발급|취득|완료|확정).{0,24}건설허가",
                title,
            )
        ) and (actual_verbs or has_schedule)

    if family == "epc_major_equipment":
        return any(term in low for term in ("발주 공고", "입찰 공고", "우선협상", "사업자 선정", "수주", "계약 체결", "epc 계약", "주기기 계약")) and not any(
            term in low for term in ("발주 검토", "발주 계획", "계약 검토", "계약 추진")
        )

    if family == "commercialization":
        return any(term in low for term in ("착공", "건설 착수", "상용운전", "상업운전", "가동", "부지 확정", "사업자 선정", "일정 확정", "목표 변경")) or has_schedule

    # 분류되지 않은 상태는 보수적으로 차단한다.
    if support_only and not (actual_verbs or has_schedule or has_money):
        return False
    return actual_verbs or has_schedule or has_money


def _select_smr_state_candidate(family_items: list[dict]) -> dict | None:
    """기사 자체가 아니라 공식 확인된 사건 상태만 알림 후보로 선택한다."""
    if not SMR_REQUIRE_OFFICIAL_CONFIRMATION:
        return next((item for item in family_items if _is_actionable_smr_state(item)), None)
    for item in family_items:
        if bool(item.get("official")) and _is_actionable_smr_state(item):
            return item
    return None


def _self_test_smr_event_state_model() -> None:
    repeated_law_articles = [
        "SMR 특별법·시행령 시행…민관 합동 상용화 착수",
        "SMR 개발·상용화 속도 낸다…SMR 특별법·시행령 오늘 시행",
    ]
    for title in repeated_law_articles:
        if _smr_event_family(title) != "law_decree":
            raise RuntimeError("SMR law/decree family regression")
        if _smr_state_key(title, False) != "law_decree|effective":
            raise RuntimeError("SMR repeated-law semantic dedupe regression")

    # 기사 출처는 증거일 뿐이다. 비공식 재보도만으로는 상태 전이 후보가 될 수 없다.
    reported = {
        "event_family": "law_decree",
        "title": repeated_law_articles[0],
        "official": False,
    }
    if _select_smr_state_candidate([reported]) is not None:
        raise RuntimeError("SMR article-only state-change gate regression")

    # 반대로 공식 기본계획의 실제 착수·일정 변화는 계속 통과해야 한다.
    official_change = {
        "event_family": "basic_plan",
        "title": "SMR 기본계획 수립 착수, 2027년 확정 목표",
        "official": True,
    }
    if _select_smr_state_candidate([official_change]) is None:
        raise RuntimeError("SMR official event-state gate regression")


def _bwrx_stage(text: str) -> str | None:
    low = clean_text(text).lower()
    if not (("bwrx-300" in low or "bwrx 300" in low) and ("clinch river" in low or "tva" in low)):
        return None

    checks = [
        ("commercial_operation", (
            "commercial operation", "commercially operating", "begins commercial operation",
            "상업운전 개시", "상업 운전 개시",
        )),
        ("commissioning", ("commissioning", "시운전", "grid synchronization", "계통연계")),
        ("fuel_load", ("fuel loading", "fuel load", "연료장전", "연료 장전")),
        ("operating_license_issued", (
            "operating license issued", "operating license granted", "operating license approved",
            "운영허가 발급", "운영허가 승인", "운전허가 발급",
        )),
        ("construction_start", (
            "construction starts", "construction started", "begins construction",
            "groundbreaking", "breaks ground", "착공", "건설 착수",
        )),
        ("major_equipment_order", (
            "purchase order", "major equipment order", "long-lead equipment order",
            "reactor pressure vessel order", "주기기 발주", "장주기 기자재 발주",
            "구매주문", "본발주",
        )),
        ("capital_approval", (
            "final investment decision", "board approves construction", "board approved construction",
            "board authorizes construction", "capital approval", "final capital approval",
            "최종투자결정", "이사회 건설 승인", "자본승인",
        )),
        ("operating_license_application", (
            "operating license application submitted", "operating license application filed",
            "operating license application received", "operating license application accepted",
            "운영허가 신청", "운영허가 접수", "운전허가 신청",
        )),
        ("construction_permit_issued", (
            "construction permit issued", "construction permit granted",
            "approves construction permit", "approved construction permit",
            "건설허가 발급", "건설허가 승인", "건설 허가",
        )),
    ]
    for stage, terms in checks:
        if any(term in low for term in terms):
            return stage
    return None


def _is_bwrx_official_source(source: str, link: str = "") -> bool:
    blob = f"{source} {link}".lower()
    return any(term in blob for term in (
        "nuclear regulatory commission", "nrc.gov", "tennessee valley authority",
        "tva.com", "ge vernova", "ge hitachi", "gevernova.com",
    ))


def collect_bwrx_us_items(now: dt.datetime) -> list[dict]:
    rows: list[dict] = [dict(BWRX_FIXED_BASELINE)]

    # 공식 페이지 직접 확인. 오래된 페이지 문구가 남아도 기존 허가 기준선보다 낮은 단계는 승격되지 않는다.
    for source, url in (
        ("NRC", BWRX_NRC_RELEASE),
        ("NRC", BWRX_NRC_PROJECT),
        ("TVA", BWRX_TVA_MEDIA),
        ("TVA", BWRX_TVA_PROJECT),
    ):
        try:
            raw = fetch_text(url)
            body = clean_text(raw)
        except Exception as exc:
            print(f"bwrx_official_error={source} {type(exc).__name__}")
            continue
        stage = _bwrx_stage(body)
        if not stage:
            continue
        rows.append({
            "kind": "bwrx300_us",
            "stage": stage,
            "rank": BWRX_STAGE_RANK[stage],
            "status": BWRX_STAGE_LABELS[stage],
            "published_utc": now.astimezone(UTC).isoformat(timespec="seconds"),
            "published_kst": now.isoformat(timespec="seconds"),
            "title": f"TVA Clinch River BWRX-300 · {BWRX_STAGE_LABELS[stage]}",
            "source": source,
            "link": url,
            "official": True,
        })

    # 공식기관 RSS 노출을 보조 탐색면으로 사용하되 비공식 기사만으로 상태를 올리지 않는다.
    for source_name, query in BWRX_RSS_QUERIES:
        try:
            root = ET.fromstring(fetch_text(_google_news_url(query)))
        except Exception as exc:
            print(f"bwrx_rss_error={source_name} {type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean_rss_title(node.findtext("title") or "")
            link = clean_text(node.findtext("link") or "")
            source_node = node.find("source")
            outlet = clean_text(source_node.text if source_node is not None and source_node.text else "")
            if not title or not _is_bwrx_official_source(outlet, link):
                continue
            stage = _bwrx_stage(title)
            if not stage:
                continue
            pub_text = clean_text(node.findtext("pubDate") or "")
            try:
                published = parsedate_to_datetime(pub_text)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
                published = published.astimezone(UTC)
            except Exception:
                published = now.astimezone(UTC)
            rows.append({
                "kind": "bwrx300_us",
                "stage": stage,
                "rank": BWRX_STAGE_RANK[stage],
                "status": BWRX_STAGE_LABELS[stage],
                "published_utc": published.isoformat(timespec="seconds"),
                "published_kst": published.astimezone(KST).isoformat(timespec="seconds"),
                "title": title,
                "source": outlet or source_name,
                "link": link,
                "official": True,
            })

    rows.sort(key=lambda x: (int(x.get("rank") or 0), str(x.get("published_utc") or "")), reverse=True)
    return rows


def _hanul4_stage(text: str) -> str | None:
    normalized = clean_text(text)
    low = normalized.lower()
    compact = re.sub(r"\s+", "", low)
    if not ("한울4호기" in compact or "hanul4" in compact or "hanulunit4" in compact):
        return None

    # 가장 높은 실제 운전단계를 먼저 판정한다.
    if any(term in compact for term in ("100%출력", "전출력도달", "100%전출력")):
        return "full_power"
    if any(term in compact for term in ("발전재개", "계통병입", "계통연결")):
        return "generation_resumed"

    # '승인 검토/예정/가능'을 실제 승인으로 오인하지 않는다.
    if "재가동승인" in compact:
        pending = any(term in compact for term in (
            "승인검토", "승인예정", "승인가능", "승인전망", "승인기대",
            "승인할수", "승인할것", "승인할예정",
        ))
        if not pending:
            return "restart_approved"

    if any(term in compact for term in ("원자로자동정지", "자동정지", "재정지")):
        return "automatic_trip"
    return None


def _hanul4_live_status(text: str) -> str | None:
    normalized = clean_text(text)
    patterns = (
        r"한울\s*(?:원자력\s*)?4호기\s*(?:현재\s*)?(운전|정비|정지)",
        r"한울\s*4호기.{0,24}?\b(운전|정비|정지)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, re.I)
        if match:
            return match.group(1)
    return None


def _hanul4_official_source(outlet: str, link: str = "") -> bool:
    low = f"{outlet} {link}".lower()
    return (
        any(term.lower() in low for term in HANUL4_OFFICIAL_OUTLETS)
        or "nssc.go.kr" in low
        or "khnp.co.kr" in low
    )


def _hanul4_trusted_source(outlet: str) -> bool:
    low = (outlet or "").lower()
    return any(term.lower() in low for term in HANUL4_TRUSTED_OUTLETS)


def _hanul4_source_key(outlet: str, link: str = "") -> str:
    low = f"{outlet} {link}".lower()
    aliases = (
        (("연합뉴스", "yna.co.kr"), "연합뉴스"),
        (("뉴시스", "newsis.com"), "뉴시스"),
        (("뉴스1", "news1.kr"), "뉴스1"),
        (("이데일리", "edaily.co.kr"), "이데일리"),
        (("전기신문", "electimes.com"), "전기신문"),
        (("파이낸셜뉴스", "fnnews.com"), "파이낸셜뉴스"),
        (("머니투데이", "mt.co.kr"), "머니투데이"),
        (("서울경제", "sedaily.com"), "서울경제"),
        (("한국경제", "hankyung.com"), "한국경제"),
        (("전자신문", "etnews.com"), "전자신문"),
        (("원자력안전위원회", "nssc.go.kr"), "원자력안전위원회"),
        (("한국수력원자력", "한수원", "khnp.co.kr"), "한국수력원자력"),
    )
    for tokens, canonical in aliases:
        if any(token in low for token in tokens):
            return canonical
    return (outlet or link or "unknown").strip().lower()


def _hanul4_parse_pub(pub_text: str, now: dt.datetime) -> dt.datetime:
    try:
        published = parsedate_to_datetime(pub_text)
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        return published.astimezone(UTC)
    except Exception:
        return now.astimezone(UTC)


def collect_hanul4_operation_items(now: dt.datetime) -> list[dict]:
    # 현재 승인 사실은 사용자가 제시한 전기신문과 독립적인 이데일리 보도로
    # 원안위 발표 내용이 교차 확인돼 있으며, 실제 발전재개 여부는 KHNP 실시간
    # 운영상태와 분리한다.
    rows: list[dict] = [dict(HANUL4_VERIFIED_APPROVAL)]
    live_status = None
    live_source = None

    # 실제 운전 여부는 사업자인 KHNP 공식 실시간 페이지를 최우선으로 본다.
    for source_name, url in (
        ("한국수력원자력 한울본부", HANUL4_KHNP_MAIN),
        ("한국수력원자력", HANUL4_KHNP_MOBILE),
        ("열린원전운영정보", HANUL4_KHNP_NPP),
    ):
        try:
            body = clean_text(fetch_text(url))
        except Exception as exc:
            print(f"hanul4_khnp_status_error={source_name} {type(exc).__name__}")
            continue
        status = _hanul4_live_status(body)
        if status and live_status is None:
            live_status = status
            live_source = url
        if status == "운전":
            rows.append({
                "kind": "domestic_reactor_operation",
                "reactor": "한울4호기",
                "stage": "operating_status",
                "rank": HANUL4_STAGE_RANK["operating_status"],
                "status": HANUL4_STAGE_LABELS["operating_status"],
                "published_utc": now.astimezone(UTC).isoformat(timespec="seconds"),
                "published_kst": now.isoformat(timespec="seconds"),
                "title": "한국수력원자력 실시간 운영현황에서 한울4호기 '운전' 상태 확인",
                "source": source_name,
                "link": url,
                "official": True,
                "verified": True,
                "live_status": "운전",
                "live_status_source": url,
            })
            break

    # RSS는 규제 승인·발전재개·100% 출력·재정지의 보조 탐색면이다.
    # 공식 출처 1곳 또는 서로 다른 신뢰매체 2곳이 같은 단계만 지지할 때 채택한다.
    support: dict[str, list[dict]] = {}
    for source_name, query in HANUL4_RSS_QUERIES:
        try:
            root = ET.fromstring(fetch_text(_google_news_url(query)))
        except Exception as exc:
            print(f"hanul4_rss_error={source_name} {type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean_rss_title(node.findtext("title") or "")
            link = clean_text(node.findtext("link") or "")
            source_node = node.find("source")
            outlet = clean_text(source_node.text if source_node is not None and source_node.text else source_name)
            stage = _hanul4_stage(title)
            if not title or not link or not stage:
                continue
            published = _hanul4_parse_pub(clean_text(node.findtext("pubDate") or ""), now)
            if (now.astimezone(UTC) - published).total_seconds() / 86400 > 14:
                continue
            # 8월 자동정지 과거기사는 현재 승인을 뒤집는 신규사건으로 취급하지 않는다.
            support.setdefault(stage, []).append({
                "title": title,
                "link": link,
                "source": outlet or source_name,
                "published": published,
                "official": _hanul4_official_source(outlet, link),
                "trusted": _hanul4_trusted_source(outlet),
            })

    for stage, evidence in support.items():
        source_keys = {
            _hanul4_source_key(item.get("source") or "", item.get("link") or "")
            for item in evidence
            if item.get("trusted") or item.get("official")
        }
        official_rows = [item for item in evidence if item.get("official")]
        trusted_rows = [item for item in evidence if item.get("trusted")]
        if not official_rows and len(source_keys) < 2:
            continue
        best = max(
            official_rows or trusted_rows or evidence,
            key=lambda item: item.get("published") or now.astimezone(UTC),
        )
        source_names = []
        for item in sorted(evidence, key=lambda x: str(x.get("source") or "")):
            key = _hanul4_source_key(item.get("source") or "", item.get("link") or "")
            if key not in source_names and (item.get("official") or item.get("trusted")):
                source_names.append(key)
        rows.append({
            "kind": "domestic_reactor_operation",
            "reactor": "한울4호기",
            "stage": stage,
            "rank": HANUL4_STAGE_RANK[stage],
            "status": HANUL4_STAGE_LABELS[stage],
            "published_utc": best["published"].isoformat(timespec="seconds"),
            "published_kst": best["published"].astimezone(KST).isoformat(timespec="seconds"),
            "title": best["title"],
            "source": "·".join(source_names[:3]) + (" 교차확인" if not official_rows else ""),
            "link": best["link"],
            "official": bool(official_rows),
            "verified": True,
            "verification": "공식 1차자료 1건 이상 또는 독립 신뢰매체 2곳 이상",
            "evidence_count": len(source_keys),
        })

    # 모든 후보에 현재 KHNP 운영상태를 함께 붙여 '승인'과 '실제 가동'을 섞지 않는다.
    for item in rows:
        item.setdefault("live_status", live_status or "미확인")
        item.setdefault("live_status_source", live_source or HANUL4_KHNP_MAIN)

    # 같은 단계는 가장 신뢰도가 높은 최신 증거 1건만 유지한다.
    dedup: dict[str, dict] = {}
    for item in rows:
        stage = str(item.get("stage") or "")
        prev = dedup.get(stage)
        score = (
            1 if item.get("official") else 0,
            1 if item.get("verified") else 0,
            int(item.get("evidence_count") or 0),
            str(item.get("published_utc") or ""),
        )
        if prev is None:
            dedup[stage] = item
            continue
        prev_score = (
            1 if prev.get("official") else 0,
            1 if prev.get("verified") else 0,
            int(prev.get("evidence_count") or 0),
            str(prev.get("published_utc") or ""),
        )
        if score > prev_score:
            dedup[stage] = item

    return sorted(
        dedup.values(),
        key=lambda x: (str(x.get("published_utc") or ""), int(x.get("rank") or 0)),
        reverse=True,
    )


def _select_hanul4_transition(previous: dict, items: list[dict]) -> dict | None:
    prev_stage = str(previous.get("stage") or "automatic_trip")
    prev_rank = int(previous.get("rank") if previous.get("rank") is not None else HANUL4_STAGE_RANK.get(prev_stage, 0))
    prev_pub = str(previous.get("published_utc") or HANUL4_FIXED_BASELINE["published_utc"])

    # 재정지는 순위가 낮아져도 가장 중요한 실패 이벤트다.
    trip_candidates = [
        item for item in items
        if item.get("stage") == "automatic_trip"
        and str(item.get("published_utc") or "") > prev_pub
        and prev_stage != "automatic_trip"
        and bool(item.get("verified"))
    ]
    if trip_candidates:
        return max(trip_candidates, key=lambda x: str(x.get("published_utc") or ""))

    forward = []
    for item in items:
        stage = str(item.get("stage") or "")
        rank = int(item.get("rank") if item.get("rank") is not None else HANUL4_STAGE_RANK.get(stage, -1))
        published = str(item.get("published_utc") or "")
        if not item.get("verified"):
            continue
        if published <= prev_pub:
            continue
        if rank > prev_rank:
            forward.append(item)
    if not forward:
        return None
    return max(forward, key=lambda x: (int(x.get("rank") or 0), str(x.get("published_utc") or "")))


def _self_test_hanul4_operating_event_model() -> None:
    if _hanul4_stage("원안위, 한울 4호기 재가동 승인…자동정지 49일 만") != "restart_approved":
        raise RuntimeError("Hanul4 restart-approval parser regression")
    if _hanul4_stage("한울4호기 재가동 승인 검토 예정") is not None:
        raise RuntimeError("Hanul4 restart-approval pending false-positive regression")
    if _hanul4_stage("한울4호기 발전재개 및 계통병입") != "generation_resumed":
        raise RuntimeError("Hanul4 generation-resumed parser regression")
    if _hanul4_stage("한울4호기 100% 출력 도달") != "full_power":
        raise RuntimeError("Hanul4 full-power parser regression")
    if _hanul4_stage("한울4호기 원자로 자동정지") != "automatic_trip":
        raise RuntimeError("Hanul4 automatic-trip parser regression")
    if _hanul4_live_status("한울 4호기 정비 4호기") != "정비":
        raise RuntimeError("Hanul4 live-maintenance parser regression")
    if _hanul4_live_status("한울 4호기 운전 4호기") != "운전":
        raise RuntimeError("Hanul4 live-operating parser regression")

    # 실제 Telegram nuclear lane의 필수 필드와도 호환되는지 회귀검사한다.
    sample = dict(HANUL4_VERIFIED_APPROVAL)
    sample["live_status"] = "정비"
    sample["live_status_source"] = HANUL4_KHNP_MAIN
    rendered = "\n".join(_render_hanul4_operation(sample, 1, now_kst()))
    for marker in (
        "- 핵심 변화:", "- 숫자:", "- 한국 기업·매출 연결:",
        "- 병목·실패모드:", "- 출처:",
    ):
        if marker not in rendered:
            raise RuntimeError(f"Hanul4 Telegram contract regression: missing {marker}")


def _render_hanul4_operation(item: dict, idx: int, now: dt.datetime) -> list[str]:
    stage = str(item.get("stage") or "")
    label = HANUL4_STAGE_LABELS.get(stage, item.get("status") or "운전 상태 변화")
    live_status = str(item.get("live_status") or "미확인")
    verification_label = "공식" if item.get("official") else "교차확인"

    if stage == "restart_approved":
        return [
            f"## {idx}. [{verification_label}] 한울 4호기 재가동",
            f"- 핵심 변화: {label}. 규제 관문은 통과했지만 재가동 승인 ≠ 실제 발전재개입니다.",
            f"- 숫자: 8월 19일 자동정지 → 10월 7일 재가동 승인(49일) · 설비용량 약 1,050MWe · 현재 한국수력원자력 실시간 상태 {live_status}.",
            "- 한국 기업·매출 연결: 한국수력원자력의 기존 한울4호기 운전 복귀 이슈이며 신규 원전 수주가 아닙니다. 발전재개·계통병입과 출력상승이 확인돼야 실제 공급 회복으로 봅니다.",
            "- 정지 원인: 발전기 차단기 단로기 접속부 전기적 결함과 원자로출력급감발계통(RPCS) 미작동이 복합 작용했습니다. RPCS 계측기 내부 이물질 유입 영향도 확인됐습니다.",
            "- 조치: 고장 기기 교체·건전성 시험과 설비 관리체계 개선 등 종합 재발방지대책 확인 후 원안위가 재가동을 승인했습니다.",
            "- 병목·실패모드: 승인 뒤에도 RPCS·발전기 차단기 계통 이상 재발, 출력상승 시험 이상, 계통병입 지연이 생기면 전력공급 정상화가 늦어질 수 있습니다.",
            f"- 출처: [{item.get('source')}]({item.get('link')}) · {item.get('published_kst')}",
            f"- 운영상태 확인: [한국수력원자력]({item.get('live_status_source') or HANUL4_KHNP_MAIN})",
            "- 다음 확인: 한국수력원자력 실시간 '운전' 전환 → 발전재개/계통병입 시각 → 출력상승 → 100% 출력 도달 → 재발방지대책 이행",
            "",
        ]

    if stage == "operating_status":
        change = "한국수력원자력 실시간 운영현황에서 한울4호기가 '운전' 상태로 전환됐습니다."
        caveat = "실제 운전 전환은 확인됐지만 계통병입 시각과 현재 출력률은 별도 공식자료로 확인합니다."
    elif stage == "generation_resumed":
        change = "한울4호기의 발전재개·계통병입이 확인됐습니다."
        caveat = "발전재개는 100% 출력 복귀와 다르므로 이후 출력상승을 별도로 추적합니다."
    elif stage == "full_power":
        change = "한울4호기가 100% 출력에 도달해 8월 자동정지 이후 출력 회복 단계까지 완료됐습니다."
        caveat = "향후에는 동일 고장 재발과 원안위 재발방지대책 이행 여부를 추적합니다."
    else:
        change = "한울4호기가 재가동 과정 이후 다시 자동정지·정지 상태로 전환됐습니다."
        caveat = "원인 확인 전에는 기존 8월 고장 재발로 단정하지 않습니다."

    return [
        f"## {idx}. [{verification_label}] 한울 4호기 운전상태",
        f"- 핵심 변화: {change}",
        f"- 숫자: 설비용량 약 1,050MWe · 현재 운영상태 {live_status}.",
        "- 한국 기업·매출 연결: 한국수력원자력 기존 발전설비의 가동률·전력판매 정상화와 연결되는 운전 이슈이며 신규 원전 수주로 계산하지 않습니다.",
        f"- 단계 구분: {caveat}",
        "- 병목·실패모드: 발전기 차단기·RPCS 계통 재고장, 출력상승 시험 이상, 재발방지대책 미이행이 확인되면 재정지 위험이 있습니다.",
        f"- 출처: [{item.get('source')}]({item.get('link')}) · {item.get('published_kst')}",
        "- 다음 확인: 실시간 운전상태 → 발전재개/계통병입 → 출력률 → 100% 출력 → 재정지 여부",
        "",
    ]


def _self_test_bwrx_us_event_model() -> None:
    permit = _bwrx_stage("TVA Clinch River BWRX-300 construction permit issued by NRC")
    if permit != "construction_permit_issued":
        raise RuntimeError(f"BWRX construction-permit regression: {permit}")

    application = _bwrx_stage("TVA Clinch River BWRX-300 operating license application submitted to NRC")
    if application != "operating_license_application":
        raise RuntimeError(f"BWRX operating-license application regression: {application}")

    start = _bwrx_stage("TVA Clinch River BWRX-300 construction started after board approval")
    if start != "construction_start":
        raise RuntimeError(f"BWRX construction-start regression: {start}")

    operation = _bwrx_stage("TVA Clinch River BWRX-300 begins commercial operation")
    if operation != "commercial_operation":
        raise RuntimeError(f"BWRX commercial-operation regression: {operation}")

    # 허가 '신청 검토' 문구는 허가 발급으로 오인하지 않는다.
    if _bwrx_stage("NRC reviews TVA Clinch River BWRX-300 construction permit application") is not None:
        raise RuntimeError("BWRX permit-application false-positive regression")


def _render_bwrx_us(item: dict, idx: int, now: dt.datetime) -> list[str]:
    stage = str(item.get("stage") or "")
    label = BWRX_STAGE_LABELS.get(stage, item.get("status") or "상태 변화")
    return [
        f"## {idx}. [확정] TVA Clinch River BWRX-300",
        f"- 핵심 변화: {label}",
        "- 현재 기준: 300MW급 BWRX-300 · NRC 건설허가(CPAR-2)는 이미 발급됐지만 건설허가 ≠ 실제 착공 ≠ 운영허가입니다.",
        "- 매출 연결: GE Vernova Hitachi의 노형·주기기와 TVA의 실제 자본집행·본발주가 확인돼야 공급망 매출이 구체화됩니다. 한국 기업의 Clinch River 직접수주는 별도 확인 전에는 확정하지 않습니다.",
        "- 병목·실패모드: TVA 최종 자본승인, 장주기 기자재 발주, 실제 착공, NRC 운영허가, 시운전·연료장전 순으로 남아 있으며 한 단계 지연되면 상업운전 시간표도 밀립니다.",
        f"- 출처: [{item.get('source') or '공식자료'}]({item.get('link') or BWRX_NRC_PROJECT}) · {item.get('published_kst') or item.get('published_utc') or '확인 불가'}",
        "- 다음 확인: TVA 자본승인/FID → 주기기·장주기 본발주 → 착공 → 운영허가 신청·발급 → 연료장전·시운전 → 상업운전",
        "",
    ]


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict, now: dt.datetime) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_direct(item: dict, idx: int, now: dt.datetime) -> list[str]:
    ko_title = "미국, Westinghouse AP1000 원전·AI 전력 정책 지원 신호"
    if "80" in " ".join(item["matched"]):
        ko_title = "미국, Westinghouse 원전 건설 대형 지원 신호"
    source_label = SOURCE_LABELS.get(item["source"], item["source"])
    evidence = ", ".join(dict.fromkeys(TERM_LABELS.get(term, term) for term in item["matched"]))
    numeric = [
        TERM_LABELS.get(term, term)
        for term in item["matched"]
        if re.search(r"\d|\$", str(term))
    ]
    numbers_text = " · ".join(dict.fromkeys(numeric)) if numeric else "신규 확정 금액·기수는 원문 추가 확인 필요"
    return [
        f"## {idx}. [확정] {ko_title}",
        f"- 핵심 변화: 미국 공식자료에서 {evidence} 관련 원전 정책 지원 신호가 확인됐습니다.",
        f"- 숫자: {numbers_text}",
        "- 한국 기업·매출 연결: 이 공식자료만으로 한국 기업의 신규 수주·매출은 확정되지 않았습니다. Westinghouse 프로젝트별 사업권·기자재 계약이 확인돼야 실제 매출로 연결됩니다.",
        "- 병목·실패모드: DOE·NRC 일정, 프로젝트별 최종 발주, 현지조달 조건, 사업권·지식재산 조건이 늦어지면 정책 신호가 실제 수주로 전환되는 시점도 밀릴 수 있습니다.",
        f"- 출처: [{source_label}]({item['link']}) · {item['published_kst']}",
        "- 다음 확인: DOE/NRC 후속 일정 · 프로젝트별 발주 · 한국 공급망 계약 공시",
        "",
    ]


def _render_westinghouse_stake(item: dict, idx: int, now: dt.datetime) -> list[str]:
    status = item.get("status") or "추가 확인 필요"
    official = bool(item.get("official")) or _is_official_outlet(str(item.get("source") or ""))
    final = status in {"지분 거래 확정 신호"}
    label = "확정" if final else ("공식·미종결" if official else "보도")
    numbers = _wec_numbers(item.get("title") or "")
    numbers_text = " · ".join(numbers) if numbers else "지분율·가격·출자액 미확정"
    if official and status == "공식 프레임워크·최종계약 미체결":
        return [
            f"## {idx}. [{label}] 한국의 Westinghouse 지분 참여",
            "- 핵심 변화: Westinghouse/Brookfield·Cameco 공식자료에서 한국의 Westinghouse 지분 5~10% 투자가 프레임워크 조건으로 직접 확인됐습니다.",
            "- 숫자: 지분 5~10% · 다만 투자금액·최종 취득지분·종결일은 아직 미확정",
            "- 확정 수준: 프레임워크 조건은 공식 확인됐지만 비구속이며, 최종계약·실사·회사 승인·규제 승인이 남아 있습니다.",
            "- 한국 기업·매출 연결: 지분투자 자체와 AP1000 설계·조달·시공·기자재 수주는 별개입니다. 개별 사업권·공급계약이 나와야 한국 기업 매출로 승격합니다.",
            "- 병목·실패모드: 최종협상에서 지분율·가격·거버넌스 권리가 바뀌거나 거래가 종결되지 않을 수 있습니다.",
            f"- 출처: [{item['source']}]({item['link']}) · {item['published_kst']}",
            "- 다음 확인: 최종계약 체결 → 실사 완료 → 회사·규제 승인 → 지분 취득 종결 → 사업권·조달권 별도 계약",
            "",
        ]
    unconfirmed = status not in {"계약·합의 단계", "지분 거래 확정 신호", "공식 부인·정정"}
    return [
        f"## {idx}. [{'보도' if unconfirmed else '확정'}] 한국의 Westinghouse 지분 참여",
        f"- 핵심 변화: {item['title']}",
        f"- 숫자: {numbers_text}",
        "- 한국 기업·매출 연결: 한국전력·한국수력원자력 등의 지분 참여가 확정되더라도 지분투자와 AP1000 설계·조달·시공·기자재 매출은 별개입니다. 사업권·조달권이 계약에 포함돼야 실적 연결이 구체화됩니다.",
        "- 병목·실패모드: 지분율·가격·경영참여권·사업권·CFIUS/NRC 승인 조건이 남아 있습니다. 조건 협상이 지연되면 투자 집행과 후속 원전 수주 시간표도 밀릴 수 있습니다.",
        f"- 출처: [{item['source']}]({item['link']}) · {item['published_kst']}",
        "- 다음 확인: 공식 발표 → LOI/MOU → 실사 → 지분율·가격 → 사업권·규제 승인",
        "",
    ]


def _render_smr_policy(item: dict, idx: int, now: dt.datetime) -> list[str]:
    status = item.get("status") or "SMR 정책 상태변화"
    official = bool(item.get("official"))
    if status == "특별법·시행령 시행":
        change_text = "SMR 특별법·시행령 시행으로 연구개발→실증·사업화, 민관협력, 연구개발특구 지원체계가 실제 시행 단계로 이동했습니다."
        source_label = "과학기술정보통신부·정책브리핑"
        source_url = SMR_OFFICIAL_SOURCES[0]["url"]
        source_time = "2026-09-11"
    else:
        change_text = item.get("title") or status
        source_label = item.get("source") or "원문"
        source_url = item.get("link") or SMR_OFFICIAL_SOURCES[0]["url"]
        source_time = item.get("published_kst") or "확인 불가"

    # Company linkage is context, not a direct award from the SMR Special Act.
    # Official sources checked in 2026-09:
    # - Hyundai E&C: TerraPower Natrium follow-on 8-unit EPC priority.
    # - HD Hyundai: target capacity for 2-3 primary Natrium components per year.
    # - Doosan Enerbility: NuScale/X-energy reactor-module forging/equipment manufacturing base.
    return [
        f"## {idx}. [{'확정' if official or status == '특별법·시행령 시행' else '보도'}] 국내 SMR 정책 상태변화",
        f"- 핵심 변화: {change_text}",
        "- 숫자: 기본계획 5년 주기 · 2027년 상세설계 착수 · 2030년대 비경수형 SMR 건설 착수 · 2035년 경수형 SMR 상용화 목표",
        "- 한국 기업·매출 연결: 현대건설은 TerraPower Natrium 후속 8기 EPC 우선권, HD현대는 주기기 연 2~3기 생산체계 목표, 두산에너빌리티는 NuScale·X-energy 원자로 모듈 제작 기반이 있습니다. 다만 특별법 시행 자체의 신규 수주·매출액은 아직 미확정입니다.",
        "- 병목·실패모드: 실제 예산액, 민관 SPC 출자사·지분, 특구·실증부지, 인허가 일정이 확정되지 않으면 제도 시행이 실제 발주·수주·매출 인식으로 이어지는 시점이 늦어질 수 있습니다.",
        f"- 근거·교차검증: [{source_label}]({source_url}) · {source_time}",
        "- 다음 확인: 제1차 기본계획 · 2027년 상세설계 예산 · SPC 출자구조 · 특구/실증부지 · 기업별 수주 공시",
        "",
    ]


def render(alerts: list[dict], now: dt.datetime) -> str:
    # The Telegram title already names this watch. Avoid repeating a second
    # banner. For the common single-event case, also drop the redundant item
    # heading so the first five body lines are the decision fields themselves.
    lines: list[str] = []
    for idx, item in enumerate(alerts, 1):
        kind = item.get("kind")
        if kind == "westinghouse_stake":
            block = _render_westinghouse_stake(item, idx, now)
        elif kind == "smr_policy":
            block = _render_smr_policy(item, idx, now)
        elif kind == "bwrx300_us":
            block = _render_bwrx_us(item, idx, now)
        elif kind == "domestic_reactor_operation":
            block = _render_hanul4_operation(item, idx, now)
        else:
            block = _render_direct(item, idx, now)
        if len(alerts) == 1 and block and block[0].startswith("## 1. "):
            block = block[1:]
        lines.extend(block)
    lines.append(f"- 조회: {now:%Y-%m-%d %H:%M KST}")
    return "\n".join(lines).rstrip() + "\n"


def clear_outputs() -> None:
    for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
        if path.exists():
            path.unlink()


def main() -> int:
    _self_test_material_filter()
    _self_test_smr_event_state_model()
    _self_test_bwrx_us_event_model()
    _self_test_hanul4_operating_event_model()
    now = now_kst()
    seen = load_seen()
    initial_seen_snapshot = json.dumps(seen, ensure_ascii=False, sort_keys=True)
    seen_map = seen.setdefault("seen", {})
    alerts: list[dict] = []

    direct_items = collect_direct_items(now)
    for item in direct_items:
        if item["fingerprint"] in seen_map:
            continue
        alerts.append(item)
        seen_map[item["fingerprint"]] = {
            "title": item["title"], "source": item["source"], "link": item["link"], "first_seen_kst": now.isoformat(timespec="seconds")
        }

    stake_items = collect_westinghouse_stake_items(now)
    if WEC_EQUITY_ALERTS_DELEGATED_TO_US_INVESTMENT:
        # 단일 소유권: 지분/거버넌스 알림은 대미투자 watcher만 송출한다.
        # 여기서는 같은 기사나 RSS가 다시 나타나도 alert 후보로 만들지 않는다.
        print(
            "westinghouse_equity_alert_delegated_to_us_investment=true "
            f"support_candidates={len(stake_items)}"
        )
        stake_items = []
    previous_state = seen.get("westinghouse_issue_state") or {}
    previous_model_version = int(seen.get("westinghouse_state_model_version") or 0)

    # 상태 파일이 손실·초기화됐거나 새 모델로 전환되는 경우,
    # 현재까지 공개된 가장 최신 사건상태를 기준선으로 흡수하고 과거 기사를 소급 발송하지 않는다.
    if previous_model_version < WEC_STATE_MODEL_VERSION or not previous_state:
        historical_candidates = []
        for candidate in stake_items:
            try:
                candidate_dt = dt.datetime.fromisoformat(
                    str(candidate.get("published_utc") or "").replace("Z", "+00:00")
                ).astimezone(UTC)
            except Exception:
                continue
            if candidate_dt <= WEC_STATE_MODEL_CUTOFF_UTC:
                historical_candidates.append(candidate)

        baseline = historical_candidates[0] if historical_candidates else dict(WEC_FIXED_BASELINE)
        seen["westinghouse_issue_state"] = {
            "state_key": baseline.get("state_key") or WEC_FIXED_BASELINE["state_key"],
            "status": baseline.get("status") or WEC_FIXED_BASELINE["status"],
            "title": baseline.get("title") or WEC_FIXED_BASELINE["title"],
            "source": baseline.get("source") or WEC_FIXED_BASELINE["source"],
            "link": baseline.get("link") or WEC_FIXED_BASELINE["link"],
            "published_utc": baseline.get("published_utc") or WEC_FIXED_BASELINE["published_utc"],
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
        seen["westinghouse_state_model_version"] = WEC_STATE_MODEL_VERSION
        previous_state = seen["westinghouse_issue_state"]
        print(
            "westinghouse_state_baselined=true "
            f"state_key={previous_state.get('state_key')} "
            f"published_utc={previous_state.get('published_utc')}"
        )

    # 전환 기준시각 이후의 후보만 새 이벤트 후보로 인정한다.
    latest_stake = None
    for candidate in stake_items:
        try:
            candidate_dt = dt.datetime.fromisoformat(
                str(candidate.get("published_utc") or "").replace("Z", "+00:00")
            ).astimezone(UTC)
        except Exception:
            continue
        if candidate_dt > WEC_STATE_MODEL_CUTOFF_UTC:
            latest_stake = candidate
            break

    if latest_stake:
        previous_published = str(previous_state.get("published_utc") or "")
        current_published = str(latest_stake.get("published_utc") or "")
        is_newer = not previous_published or current_published > previous_published
        changed, merged_state_key = _wec_merge_state(
            str(previous_state.get("state_key") or ""),
            str(latest_stake.get("state_key") or ""),
        )
        if is_newer and changed:
            latest_stake["trigger"] = "topic_event_state_change"
            alerts.append(latest_stake)
            seen["westinghouse_issue_state"] = {
                "state_key": merged_state_key,
                "status": latest_stake["status"],
                "title": latest_stake["title"],
                "source": latest_stake["source"],
                "link": latest_stake["link"],
                "published_utc": latest_stake["published_utc"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
            }

    smr_items = collect_smr_policy_items(now)
    previous_states = seen.setdefault("smr_policy_states", {})
    seen["smr_state_model_version"] = SMR_STATE_MODEL_VERSION

    # 기존 단일 상태를 새 모델의 법 시행 기준선으로 승계한다.
    # 과거 상태 파일까지 사라진 경우에도 이미 시행된 법·시행령은 고정 기준선으로 복구한다.
    legacy_smr = seen.get("smr_policy_state") or {}
    if "law_decree" not in previous_states:
        if legacy_smr.get("status") == "특별법·시행령 시행":
            previous_states["law_decree"] = {
                "state_key": "law_decree|effective",
                "status": "특별법·시행령 시행",
                "published_utc": legacy_smr.get("published_utc") or "",
                "title": legacy_smr.get("title") or "",
                "source": legacy_smr.get("source") or "",
                "link": legacy_smr.get("link") or "",
                "first_seen_kst": legacy_smr.get("first_seen_kst") or now.isoformat(timespec="seconds"),
                "official": True,
            }
        else:
            previous_states["law_decree"] = {
                **SMR_FIXED_EVENT_BASELINES["law_decree"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
            }

    # 기사 수가 아니라 사건축별 상태 연속선을 비교한다.
    items_by_family: dict[str, list[dict]] = {}
    for item in smr_items:
        family = item.get("event_family") or _smr_event_family(item.get("title") or "")
        if family == "other":
            continue
        items_by_family.setdefault(family, []).append(item)

    for family, family_items in items_by_family.items():
        latest_smr = _select_smr_state_candidate(family_items)
        if not latest_smr:
            print(
                f"smr_state_pending_official family={family} "
                f"evidence_items={len(family_items)}"
            )
            continue
        previous_smr = previous_states.get(family) or {}

        # 저장된 상태가 아직 없는 사건축은 전환 시점 이전의 가장 최근 자료를
        # 자동 기준선으로 삼는다. 따라서 전환 이후 새 기사가 같은 사실을 반복해도
        # 기사 자체가 신규 알림을 만들지 않는다.
        if not previous_smr:
            historical_baseline = None
            for candidate in family_items:
                candidate_published = str(candidate.get("published_utc") or "")
                try:
                    candidate_dt = dt.datetime.fromisoformat(candidate_published.replace("Z", "+00:00")).astimezone(UTC)
                except Exception:
                    continue
                if candidate_dt <= SMR_STATE_MODEL_CUTOFF_UTC:
                    historical_baseline = candidate
                    break
            if historical_baseline:
                previous_smr = {
                    "state_key": historical_baseline["state_key"],
                    "status": historical_baseline["status"],
                    "published_utc": historical_baseline["published_utc"],
                }

        previous_published = str(previous_smr.get("published_utc") or "")
        current_published = str(latest_smr.get("published_utc") or "")
        is_newer = not previous_published or current_published > previous_published
        changed = latest_smr["state_key"] != previous_smr.get("state_key")

        if not previous_smr:
            try:
                published_dt = dt.datetime.fromisoformat(current_published.replace("Z", "+00:00")).astimezone(UTC)
            except Exception:
                published_dt = now.astimezone(UTC)
            if published_dt <= SMR_STATE_MODEL_CUTOFF_UTC:
                continue

        if is_newer and changed:
            latest_smr["trigger"] = "topic_event_state_change"
            alerts.append(latest_smr)
            previous_states[family] = {
                "state_key": latest_smr["state_key"],
                "status": latest_smr["status"],
                "title": latest_smr["title"],
                "source": latest_smr["source"],
                "link": latest_smr["link"],
                "published_utc": latest_smr["published_utc"],
                "official": bool(latest_smr.get("official")),
                "first_seen_kst": now.isoformat(timespec="seconds"),
            }

    # 미국 BWRX-300은 2026-09 건설허가를 이미 알림한 기준선으로 고정하고,
    # 그 이후 실제 실행단계가 공식적으로 상승할 때만 새 알림을 만든다.
    seen["bwrx300_us_state_model_version"] = BWRX_US_STATE_MODEL_VERSION
    previous_bwrx = seen.get("bwrx300_us_state") or {}
    if not previous_bwrx:
        seen["bwrx300_us_state"] = {
            **BWRX_FIXED_BASELINE,
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
        previous_bwrx = seen["bwrx300_us_state"]
        print("bwrx300_us_baseline_restored=construction_permit_issued")

    bwrx_items = collect_bwrx_us_items(now)
    latest_bwrx = bwrx_items[0] if bwrx_items else None
    if latest_bwrx:
        prev_rank = int(previous_bwrx.get("rank") or BWRX_STAGE_RANK.get(str(previous_bwrx.get("stage") or ""), 0))
        new_rank = int(latest_bwrx.get("rank") or 0)
        if new_rank > prev_rank and bool(latest_bwrx.get("official")):
            latest_bwrx["trigger"] = "official_bwrx300_execution_stage_change"
            alerts.append(latest_bwrx)
            seen["bwrx300_us_state"] = {
                **latest_bwrx,
                "first_seen_kst": now.isoformat(timespec="seconds"),
            }

    # 한울4호기 운전상태는 규제 승인과 실제 발전재개를 분리해 추적한다.
    seen["hanul4_operation_state_model_version"] = HANUL4_STATE_MODEL_VERSION
    previous_hanul4 = seen.get("hanul4_operation_state") or {}
    if not previous_hanul4:
        seen["hanul4_operation_state"] = {
            **HANUL4_FIXED_BASELINE,
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
        previous_hanul4 = seen["hanul4_operation_state"]
        print("hanul4_operation_baseline_restored=automatic_trip_2026-08-19")

    hanul4_items = collect_hanul4_operation_items(now)
    latest_hanul4 = _select_hanul4_transition(previous_hanul4, hanul4_items)
    if latest_hanul4:
        latest_hanul4["trigger"] = "verified_domestic_reactor_operation_stage_change"
        alerts.append(latest_hanul4)
        seen["hanul4_operation_state"] = {
            **latest_hanul4,
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
        print(
            "hanul4_operation_state_change=true "
            f"stage={latest_hanul4.get('stage')} "
            f"live_status={latest_hanul4.get('live_status')}"
        )

    if not alerts:
        # 기준선 복구·상태모델 전환 같은 내부 상태 변화는 알림이 없어도 반드시 저장한다.
        current_seen_snapshot = json.dumps(seen, ensure_ascii=False, sort_keys=True)
        if current_seen_snapshot != initial_seen_snapshot:
            save_seen(seen, now)
            print("nuclear_policy_state_persisted_without_alert=true")
        clear_outputs()
        print(f"nuclear_policy_alerts=0 direct={len(direct_items)} westinghouse_material={len(stake_items)} smr_material={len(smr_items)}")
        return 0

    OUT_DIR.mkdir(exist_ok=True)
    ALERT_PATH.write_text(render(alerts, now), encoding="utf-8")
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if all(item.get("kind") == "smr_policy" for item in alerts):
        TITLE_PATH.write_text("한국 SMR 특별법·i-SMR 웹감시: 공식 상태 변화\n", encoding="utf-8")
    elif all(item.get("kind") == "domestic_reactor_operation" for item in alerts):
        TITLE_PATH.write_text("국내 원전 운전·재가동 웹감시: 확인된 상태 변화\n", encoding="utf-8")
    else:
        TITLE_PATH.write_text("원전·Westinghouse·SMR 웹감시: 물질적 상태 변화\n", encoding="utf-8")
    save_seen(seen, now)
    print(
        f"nuclear_policy_alerts={len(alerts)} "
        f"westinghouse_material={len(stake_items)} smr_material={len(smr_items)} "
        f"hanul4_candidates={len(hanul4_items)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

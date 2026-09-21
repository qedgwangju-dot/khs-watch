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
DIRECT_FINGERPRINT_VERSION = "ko-v2"

# SMR는 새 기사 자체가 아니라 주제·사건의 구조화된 상태 변화를 감지한다.
# 이 시각 이전 검색 결과는 새 모델 전환 시 소급 알림하지 않는다.
SMR_STATE_MODEL_CUTOFF_UTC = dt.datetime(2026, 9, 20, 4, 55, tzinfo=UTC)
SMR_STATE_MODEL_VERSION = 3
# 기사·보도는 증거 수집과 교차검증용이다. SMR 알림 상태 전이는 공식 출처에서
# 동일 사건의 실제 상태 변화가 확인된 경우에만 발생시킨다.
SMR_REQUIRE_OFFICIAL_CONFIRMATION = True

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
    ("웨스팅하우스 지분·한국 뉴스", "웨스팅하우스 지분 인수 한국전력 산업통상부 한수원 브룩필드 카메코 when:14d"),
    ("웨스팅하우스 지분·해외 뉴스", "Westinghouse stake Korea KEPCO KHNP Brookfield Cameco when:14d"),
    ("웨스팅하우스 지분·공식입장 추적", "웨스팅하우스 산업통상부 한국전력 공식 발표 when:30d"),
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


def _is_material_westinghouse(title: str, outlet: str = "") -> bool:
    low = title.lower()
    if not (any(term in low for term in WEC_CORE) and any(term in low for term in WEC_TRANSACTION)):
        return False
    if _is_official_outlet(outlet):
        return True
    if any(term in low for term in WEC_COMMENTARY_OR_MARKET):
        return any(term in low for term in WEC_STRONG_EXECUTION)
    return any(term in low for term in WEC_MATERIAL) or _has_numeric_terms(title)


def _self_test_material_filter() -> None:
    if _is_material_westinghouse("[특징주] 한전, 웨스팅하우스 지분투자설에 6%대 급등 마감", "연합뉴스"):
        raise RuntimeError("Westinghouse market-reaction filter regression")
    if _is_material_westinghouse("한전, 웨스팅하우스 지분확보설에 장중 7%대 급등", "연합뉴스"):
        raise RuntimeError("Westinghouse intraday-price filter regression")
    if not _is_material_westinghouse("한국전력, 웨스팅하우스 지분 인수 실사 착수…지분율 10% 협상", "연합뉴스"):
        raise RuntimeError("Westinghouse execution-state filter regression")
    if not _is_material_westinghouse("웨스팅하우스 지분 공동인수 보도는 사실과 다르다", "산업통상부"):
        raise RuntimeError("Westinghouse official-state filter regression")
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
    status = _wec_status(title, outlet)
    numbers = "|".join(_wec_numbers(title)) or "no-number"
    official = "official" if _is_official_outlet(outlet) else "reported"
    return f"{status}|{numbers}|{official}"


def collect_westinghouse_stake_items(now: dt.datetime) -> list[dict]:
    rows: list[dict] = []
    seen_story: set[str] = set()
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
            if (now.astimezone(UTC) - published).total_seconds() / 86400 > 30:
                continue
            story_key = f"{title.lower()}|{outlet.lower()}"
            if story_key in seen_story:
                continue
            seen_story.add(story_key)
            rows.append({
                "kind": "westinghouse_stake", "source": outlet or source_name, "title": title[:500], "link": link,
                "published_kst": published.astimezone(KST).isoformat(timespec="seconds"), "published_utc": published.isoformat(timespec="seconds"),
                "state_key": _wec_state_key(title, outlet), "status": _wec_status(title, outlet), "matched": ["westinghouse", "stake", "korea"],
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
    unconfirmed = status not in {"계약·합의 단계", "지분 거래 확정 신호", "공식 부인·정정"}
    numbers = _wec_numbers(item.get("title") or "")
    numbers_text = " · ".join(numbers) if numbers else "지분율·가격·출자액 미확정"
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
    now = now_kst()
    seen = load_seen()
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
    latest_stake = stake_items[0] if stake_items else None
    previous_state = seen.get("westinghouse_issue_state") or {}
    if latest_stake:
        previous_published = str(previous_state.get("published_utc") or "")
        current_published = str(latest_stake.get("published_utc") or "")
        is_newer = not previous_published or current_published > previous_published
        changed = latest_stake["state_key"] != previous_state.get("state_key")
        if is_newer and changed:
            alerts.append(latest_stake)
            seen["westinghouse_issue_state"] = {
                "state_key": latest_stake["state_key"], "status": latest_stake["status"], "title": latest_stake["title"], "source": latest_stake["source"],
                "link": latest_stake["link"], "published_utc": latest_stake["published_utc"], "first_seen_kst": now.isoformat(timespec="seconds"),
            }

    smr_items = collect_smr_policy_items(now)
    previous_states = seen.setdefault("smr_policy_states", {})
    seen["smr_state_model_version"] = SMR_STATE_MODEL_VERSION

    # 기존 단일 상태를 새 모델의 법 시행 기준선으로 승계한다.
    legacy_smr = seen.get("smr_policy_state") or {}
    if "law_decree" not in previous_states and legacy_smr.get("status") == "특별법·시행령 시행":
        previous_states["law_decree"] = {
            "state_key": "law_decree|effective",
            "status": "특별법·시행령 시행",
            "published_utc": legacy_smr.get("published_utc") or "",
            "title": legacy_smr.get("title") or "",
            "source": legacy_smr.get("source") or "",
            "link": legacy_smr.get("link") or "",
            "first_seen_kst": legacy_smr.get("first_seen_kst") or now.isoformat(timespec="seconds"),
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

    if not alerts:
        clear_outputs()
        print(f"nuclear_policy_alerts=0 direct={len(direct_items)} westinghouse_material={len(stake_items)} smr_material={len(smr_items)}")
        return 0

    OUT_DIR.mkdir(exist_ok=True)
    ALERT_PATH.write_text(render(alerts, now), encoding="utf-8")
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if all(item.get("kind") == "smr_policy" for item in alerts):
        TITLE_PATH.write_text("한국 SMR 특별법·i-SMR 웹감시: 공식 상태 변화\n", encoding="utf-8")
    else:
        TITLE_PATH.write_text("원전·Westinghouse·SMR 웹감시: 물질적 상태 변화\n", encoding="utf-8")
    save_seen(seen, now)
    print(f"nuclear_policy_alerts={len(alerts)} westinghouse_material={len(stake_items)} smr_material={len(smr_items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from pathlib import Path
import html
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

import janus_watch_v2 as j2
import janus_watch_v5 as j5

ROOT = Path(__file__).resolve().parents[1]
WEC_ALERT_PATH = ROOT / "out" / "westinghouse_alert.html"

# 기존 Janus·Westinghouse 지분 감시에 더해 한국 원전 수출·APR1400 미국 진출,
# 체코 원전 연계 청정수소, Holtec 자금조달·현대건설 협력까지 한 경로에서 감시한다.
RSS_QUERIES = [
    ("대미 원전·APR1400 뉴스", "APR1400 한수원 미국 원전 웨스팅하우스 8기 대미투자 when:14d", "us_nuclear_rss"),
    ("체코 원전 청정수소 뉴스", "한수원 체코 원전 청정수소 HYTEP CEZ when:30d", "nuclear_hydrogen_rss"),
    ("Holtec·현대건설 원전 뉴스", "Holtec 현대건설 SMR-300 IPO 원전 when:30d", "holtec_finance_rss"),
]
for name, query, kind in RSS_QUERIES:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": kind})

for source in [
    {
        "name": "한국수력원자력 공식 보도자료",
        "url": "https://with.khnp.co.kr/main/index.do",
        "kind": "khnp_official_nuclear",
    },
    {
        "name": "산업통상부 원전·대미투자 공식",
        "url": "https://www.motir.go.kr/",
        "kind": "motir_official_nuclear",
    },
    {
        "name": "Holtec 공식 뉴스",
        "url": "https://holtecinternational.com/news/",
        "kind": "holtec_official_nuclear",
    },
]:
    if not any(s.get("url") == source["url"] for s in j2.base.SOURCES):
        j2.base.SOURCES.append(source)

for term in [
    "APR1400", "KHNP", "HYTEP", "CEZ", "Holtec", "HNUC", "Hyundai E&C", "SMR-300", "Palisades",
]:
    if term not in j2._PROTECTED_TERMS:
        j2._PROTECTED_TERMS.append(term)


def _clean_rss_title(title: str) -> str:
    title = j2.base.norm(title)
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def _fresh(pub: str, max_days: int = 35) -> bool:
    if not pub:
        return True
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400
        return age_days <= max_days
    except Exception:
        return True


def _kind_for_title(title: str, requested_kind: str) -> str:
    low = title.lower()
    if requested_kind == "us_nuclear_rss":
        if not any(x in low for x in ["apr1400", "한수원", "khnp", "웨스팅하우스", "westinghouse", "원전"]):
            return ""
        if not any(x in low for x in ["미국", "대미", "8기", "원전", "nuclear", "u.s.", "us "]):
            return ""
        # 지분 인수 자체는 기존 Westinghouse 지분 감시에서 묶어서 처리한다.
        if any(x in low for x in ["지분", "인수", "stake", "equity", "acquisition"]):
            return ""
        return "us_nuclear_project"
    if requested_kind == "nuclear_hydrogen_rss":
        if not any(x in low for x in ["수소", "hydrogen"]):
            return ""
        if not any(x in low for x in ["한수원", "khnp", "체코", "czech", "hytep", "cez", "원전", "원자력"]):
            return ""
        return "nuclear_hydrogen"
    if requested_kind == "holtec_finance_rss":
        if "holtec" not in low and "홀텍" not in low:
            return ""
        if not any(x in low for x in ["ipo", "상장", "기업공개", "조달", "현대건설", "hyundai", "smr-300", "palisades", "팰리세이즈", "투자"]):
            return ""
        return "holtec_finance"
    return ""


def _rss_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"원전 RSS 파싱 실패 | {source['url']} | {exc}")
        return []
    rows = []
    for item in root.findall(".//item"):
        title = _clean_rss_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        source_node = item.find("source")
        outlet = j2.base.norm(source_node.text if source_node is not None and source_node.text else "")
        kind = _kind_for_title(title, source.get("kind", ""))
        if not title or not link or not kind or not _fresh(pub):
            continue
        rows.append({
            "source": outlet or source["name"],
            "title": title[:500],
            "url": link,
            "kind": kind,
            "published": pub,
        })
        if len(rows) >= 5:
            break
    return rows


def _official_title_kind(source_kind: str, title: str) -> str:
    low = title.lower()
    if source_kind == "khnp_official_nuclear":
        if any(x in low for x in ["수소", "hydrogen"]) and any(x in low for x in ["체코", "hytep", "cez", "원자력", "원전"]):
            return "nuclear_hydrogen"
        if any(x in low for x in ["apr1400", "미국", "웨스팅하우스", "westinghouse", "해외 원전", "원전 수출"]):
            return "us_nuclear_project"
        return ""
    if source_kind == "motir_official_nuclear":
        if "원전" in low and any(x in low for x in ["대미", "미국", "투자", "웨스팅하우스", "apr1400"]):
            return "us_nuclear_official"
        return ""
    if source_kind == "holtec_official_nuclear":
        if any(x in low for x in ["initial public offering", "ipo", "hyundai", "smr-300", "palisades", "loan", "funding", "investment"]):
            return "holtec_finance"
        return ""
    return ""


def _official_items(source, page_text):
    soup = BeautifulSoup(page_text, "html.parser")
    rows = []
    seen = set()
    for a in soup.find_all("a", href=True):
        title = j2.base.norm(a.get_text(" ", strip=True))
        if len(title) < 8:
            continue
        kind = _official_title_kind(source.get("kind", ""), title)
        if not kind:
            continue
        href = urljoin(source["url"], a.get("href", ""))
        key = (title.lower(), href)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"source": source["name"], "title": title[:500], "url": href, "kind": kind})
        if len(rows) >= 6:
            break
    return rows


_ORIGINAL_EXTRACT = j2.base.extract_items


def _extract_expanded(source, page_text):
    kind = source.get("kind", "")
    if kind in {"us_nuclear_rss", "nuclear_hydrogen_rss", "holtec_finance_rss"}:
        return _rss_items(source, page_text)
    if kind in {"khnp_official_nuclear", "motir_official_nuclear", "holtec_official_nuclear"}:
        return _official_items(source, page_text)
    return _ORIGINAL_EXTRACT(source, page_text)


j2.base.extract_items = _extract_expanded

_ORIGINAL_CATEGORY = j2._event_category
_ORIGINAL_MEANING = j2._event_meaning
_ORIGINAL_HIGHLIGHTS = j2._macro_highlights
_ORIGINAL_BOTTLENECKS = j2._bottleneck_lines
_ORIGINAL_NEXT_CHECK = j2._next_check


def _event_category_v6(event, resolved_title):
    kind = event.get("kind")
    if kind in {"us_nuclear_project", "us_nuclear_official"}:
        return "미국 원전·APR1400 수출"
    if kind == "nuclear_hydrogen":
        return "원전 연계 청정수소"
    if kind == "holtec_finance":
        return "SMR·자금조달·협력"
    return _ORIGINAL_CATEGORY(event, resolved_title)


def _event_meaning_v6(event, category):
    kind = event.get("kind")
    if kind in {"us_nuclear_project", "us_nuclear_official"}:
        return (
            "대미 투자 원전 프로젝트는 총 투자액보다 APR1400 적용 기수와 한국 측의 설계·기자재·시공 참여범위가 실적 연결의 핵심입니다. "
            "정부가 구체사항 미확정이라고 밝힌 동안에는 8기·노형·일정·투자금 모두 협상 단계로 분리해 봐야 합니다."
        )
    if kind == "nuclear_hydrogen":
        return (
            "체코 신규원전 협력이 발전소 건설을 넘어 원전 전력 기반 청정수소 실증으로 확장되는 신사업 신호입니다. "
            "다만 실증 부지·전해조 용량·오프테이크·EU 인증이 확정돼야 실제 매출로 이어집니다."
        )
    if kind == "holtec_finance":
        return (
            "Holtec의 자금조달과 SMR-300 사업 진척은 현대건설의 미국 원전 설계·조달·시공 파이프라인에 영향을 줄 수 있습니다. "
            "기업공개 조달금 자체와 현대건설의 확정 수주액은 별개이므로 사용처와 개별 EPC 계약을 분리해서 확인해야 합니다."
        )
    return _ORIGINAL_MEANING(event, category)


def _macro_highlights_v6(event):
    kind = event.get("kind")
    if kind == "us_nuclear_official":
        return [
            ("공식 단계", "산업통상부 확인 — 구체적인 원전 투자 사항은 아직 미확정"),
            ("확정 전 핵심", "8기 여부 · APR1400 적용 기수 · 부지 · 투자구조 · 설계·조달·시공 참여범위"),
        ]
    if kind == "us_nuclear_project":
        return [
            ("핵심 변수", "APR1400 적용 기수와 한국 설계·기자재·시공 참여범위"),
            ("현재 단계", "언론 보도·협상 단계 — 정부 공식 확정 전"),
        ]
    if kind == "nuclear_hydrogen":
        return [
            ("현재 단계", "제도·정책 검토 및 현지 실증사업 구체화 단계"),
            ("매출 전환 조건", "실증 부지 · 전해조 용량 · 오프테이크 · EU 청정수소 인증"),
        ]
    if kind == "holtec_finance":
        return [
            ("핵심 연결", "Holtec 자금조달 → SMR-300/Palisades 투자여력 → 현대건설 협력 프로젝트"),
            ("분리 확인", "Holtec 조달금과 현대건설 확정 수주액은 동일하지 않음"),
        ]
    return _ORIGINAL_HIGHLIGHTS(event)


def _bottleneck_lines_v6(event):
    kind = event.get("kind")
    if kind in {"us_nuclear_project", "us_nuclear_official"}:
        return [
            "산업통상부가 2026년 9월 7일과 9일 연속으로 대미 원전 투자 구체사항이 미확정이라고 설명",
            "APR1400의 미국 설계인증 보유와 실제 프로젝트 노형 채택·건설허가는 별개",
            "한국이 금융위험을 부담하더라도 설계·조달·시공·운영 권한과 수익 배분이 약하면 실익이 제한될 수 있음",
        ]
    if kind == "nuclear_hydrogen":
        return [
            "EU에서 원전 전력 기반 수소의 인증·지원 자격과 탄소집약도 계산방식이 사업성을 좌우",
            "전해조 전력비·가동률과 장기 오프테이크가 없으면 실증 성공이 상업 매출로 이어지지 않을 수 있음",
            "수소 저장·운송·안전 인허가와 보험 조건이 후속 투자 시점의 병목",
        ]
    if kind == "holtec_finance":
        return [
            "기업공개 가격·최종 조달액·신주 사용처가 확정돼야 SMR 투자여력을 계산할 수 있음",
            "SMR-300의 NRC 인허가와 첫 호기 일정 지연 시 현대건설의 EPC 매출 인식도 늦어질 수 있음",
            "Palisades 재가동과 신규 SMR 건설은 별도 프로젝트여서 자금·허가·공정 리스크를 분리해야 함",
        ]
    return _ORIGINAL_BOTTLENECKS(event)


def _next_check_v6(event, category):
    kind = event.get("kind")
    if kind in {"us_nuclear_project", "us_nuclear_official"}:
        return "한미 공식 MOU/발표 · 8기 확정 여부 · APR1400 적용 기수 · 부지 · 투자금 · 설계·조달·시공 분담 · NRC 프로젝트 인허가"
    if kind == "nuclear_hydrogen":
        return "체코 실증 부지 · 전해조 MW · 총사업비 · CEZ/HYTEP 역할 · EU 인증 · 수소 구매계약 · 상용화 일정"
    if kind == "holtec_finance":
        return "IPO 최종 공모가·조달액 · 자금 사용처 · SMR-300 인허가 · 현대건설 EPC 범위·수주액 · Palisades 후속 일정"
    return _ORIGINAL_NEXT_CHECK(event, category)


j2._event_category = _event_category_v6
j2._event_meaning = _event_meaning_v6
j2._macro_highlights = _macro_highlights_v6
j2._bottleneck_lines = _bottleneck_lines_v6
j2._next_check = _next_check_v6


def _render_split(events, fact_changes):
    wec_events = [e for e in events if e.get("kind") == "westinghouse_stake"]
    other_events = [e for e in events if e.get("kind") != "westinghouse_stake"]

    try:
        WEC_ALERT_PATH.unlink()
    except FileNotFoundError:
        pass

    if wec_events:
        wec_text = j5._render_wec_cluster(wec_events)
        if wec_text:
            WEC_ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
            WEC_ALERT_PATH.write_text(wec_text, encoding="utf-8")

    if other_events or fact_changes:
        return j5._ORIGINAL_RENDER(other_events, fact_changes)
    return ""


j2.base.render_alert = _render_split

if __name__ == "__main__":
    sys.exit(j2.base.main())

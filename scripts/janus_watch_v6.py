#!/usr/bin/env python3
from pathlib import Path
import hashlib
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
        palisades_terms = ["palisades", "팰리세이즈", "팰리세이드"]
        restart_terms = ["restart", "startup", "fuel loading", "fuel-loading", "fuel assembly", "mode 6", "mode 5", "nrc", "재가동", "핵연료", "연료장전", "연료 장전", "변전소", "substation"]
        finance_terms = ["initial public offering", "ipo", "상장", "기업공개", "조달", "funding", "financing", "loan", "offering", "공모", "자금"]
        partnership_terms = ["현대건설", "hyundai", "smr-300", "협력", "epc", "feed"]
        if any(x in low for x in palisades_terms) and any(x in low for x in restart_terms):
            return "palisades_restart"
        if any(x in low for x in finance_terms):
            return "holtec_finance"
        if any(x in low for x in partnership_terms):
            return "holtec_smr_partnership"
        return ""
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
        palisades_terms = ["palisades", "팰리세이즈", "팰리세이드"]
        restart_terms = ["restart", "startup", "fuel loading", "fuel-loading", "fuel assembly", "mode 6", "mode 5", "nrc", "재가동", "핵연료", "연료장전", "연료 장전", "변전소", "substation"]
        finance_terms = ["initial public offering", "ipo", "상장", "기업공개", "funding", "financing", "loan", "offering", "공모", "자금조달"]
        partnership_terms = ["hyundai", "현대건설", "smr-300", "epc", "feed", "partnership", "협력"]
        if any(x in low for x in palisades_terms) and any(x in low for x in restart_terms):
            return "palisades_restart"
        if any(x in low for x in finance_terms):
            return "holtec_finance"
        if any(x in low for x in partnership_terms):
            return "holtec_smr_partnership"
        return ""
    return ""



_ORIGINAL_FINGERPRINT = j2.base.fingerprint


def _semantic_fingerprint_v6(source: str, title: str, url: str) -> str:
    low = f"{source} {title}".lower()
    holtec_context = any(x in low for x in ["holtec", "홀텍", "palisades", "팰리세이즈", "팰리세이드", "smr-300"])
    if not holtec_context:
        return _ORIGINAL_FINGERPRINT(source, title, url)

    palisades_terms = ["palisades", "팰리세이즈", "팰리세이드"]
    restart_terms = ["restart", "startup", "fuel loading", "fuel-loading", "fuel assembly", "mode 6", "mode 5", "nrc", "재가동", "핵연료", "연료장전", "연료 장전", "변전소", "substation"]
    finance_terms = ["initial public offering", "ipo", "상장", "기업공개", "funding", "financing", "loan", "offering", "공모", "자금조달"]
    partnership_terms = ["hyundai", "현대건설", "smr-300", "epc", "feed", "partnership", "협력"]

    if any(x in low for x in palisades_terms) and any(x in low for x in restart_terms):
        kind = "palisades_restart"
        signals = [
            token for token in [
                "fuel loading", "fuel-loading", "fuel assembly", "핵연료", "연료장전", "paused", "pause", "중단",
                "resume", "resumed", "재개", "mode 6", "mode 5", "nrc", "345", "substation", "변전소", "startup", "restart", "재가동",
            ] if token in low
        ]
    elif any(x in low for x in finance_terms):
        kind = "holtec_finance"
        signals = [
            token for token in [
                "ipo", "initial public offering", "상장", "기업공개", "delay", "postpone", "연기", "pricing", "공모가",
                "funding", "financing", "loan", "자금조달",
            ] if token in low
        ]
    elif any(x in low for x in partnership_terms):
        kind = "holtec_smr_partnership"
        signals = [
            token for token in ["smr-300", "hyundai", "현대건설", "epc", "feed", "partnership", "협력", "contract", "계약"]
            if token in low
        ]
    else:
        return _ORIGINAL_FINGERPRINT(source, title, url)

    # 동일 사건을 여러 매체/URL이 재전송해도 한 상태로 묶고,
    # 재개·중단·계약 등 실제 상태 신호가 바뀔 때만 fingerprint가 달라진다.
    normalized = "|".join(sorted(set(signals))) or kind
    return hashlib.sha256(f"janus-v6-semantic|{kind}|{normalized}".encode("utf-8")).hexdigest()


j2.base.fingerprint = _semantic_fingerprint_v6

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
        return "Holtec 자금조달·기업공개"
    if kind == "holtec_smr_partnership":
        return "Holtec SMR-300·현대건설 협력"
    if kind == "palisades_restart":
        return "Palisades 재가동·NRC"
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
            "Holtec의 기업공개·대출·자금조달은 회사 전체 투자여력 변화입니다. "
            "조달금 자체를 Palisades 재가동이나 현대건설의 확정 수주액으로 연결하지 않고 실제 자금 사용처를 따로 확인합니다."
        )
    if kind == "holtec_smr_partnership":
        return (
            "Holtec SMR-300과 현대건설의 협력은 미국 신규 SMR 설계·조달·시공 파이프라인과 연결될 수 있습니다. "
            "협력 발표와 실제 FEED·EPC 계약, 수주액, 착공 일정은 분리해 확인합니다."
        )
    if kind == "palisades_restart":
        return (
            "Palisades는 기존 원전 재가동 프로젝트입니다. 핵연료 장전·NRC 조치·계통 재접속 같은 재가동 일정 변화로 판단하며, "
            "Holtec IPO·SMR-300·현대건설 신규 SMR 수주와는 별도 사건으로 분리합니다."
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
            ("현재 단계", "기업공개·대출·자금조달 조건 변화"),
            ("분리 확인", "조달금 ≠ Palisades 재가동비 ≠ 현대건설 확정 수주액"),
        ]
    if kind == "holtec_smr_partnership":
        return [
            ("핵심 연결", "Holtec SMR-300 → 현대건설 협력 → FEED/EPC 계약 가능성"),
            ("분리 확인", "협력 발표와 확정 수주·수주액·착공은 별도"),
        ]
    if kind == "palisades_restart":
        return [
            ("현재 단계", "Palisades 기존 원전 재가동 진행"),
            ("분리 확인", "Palisades 재가동 ≠ SMR-300 신규 건설 ≠ Holtec IPO"),
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
            "최종 공모가·조달액·신주/차입금 사용처가 확정돼야 실제 투자여력을 계산할 수 있음",
            "IPO 연기·축소나 차입조건 악화는 신규 프로젝트 자금조달 속도에 영향을 줄 수 있음",
            "Palisades 재가동·SMR-300·현대건설 EPC는 각각 별도 프로젝트로 자금 사용처를 확인해야 함",
        ]
    if kind == "holtec_smr_partnership":
        return [
            "SMR-300 NRC 인허가와 첫 호기 일정이 FEED/EPC 전환 시점을 좌우",
            "현대건설의 역할·공급범위·수주액·보증책임이 계약서에서 확정돼야 매출로 연결",
            "부지·전력구매계약·금융·장기납기 기자재가 신규 SMR 착공의 핵심 병목",
        ]
    if kind == "palisades_restart":
        return [
            "연료집합체 처리와 NRC 검토가 완료돼야 핵연료 장전을 재개할 수 있음",
            "장전 재개 후 Mode 5·4·3 진입, 계통동기, 상업운전까지 단계별 재가동 일정이 남아 있음",
            "Palisades 재가동 지연을 SMR-300 신규 건설 일정이나 현대건설 EPC 매출 지연으로 자동 연결하면 안 됨",
        ]
    return _ORIGINAL_BOTTLENECKS(event)


def _next_check_v6(event, category):
    kind = event.get("kind")
    if kind in {"us_nuclear_project", "us_nuclear_official"}:
        return "한미 공식 MOU/발표 · 8기 확정 여부 · APR1400 적용 기수 · 부지 · 투자금 · 설계·조달·시공 분담 · NRC 프로젝트 인허가"
    if kind == "nuclear_hydrogen":
        return "체코 실증 부지 · 전해조 MW · 총사업비 · CEZ/HYTEP 역할 · EU 인증 · 수소 구매계약 · 상용화 일정"
    if kind == "holtec_finance":
        return "IPO/대출 최종 조건 · 조달액 · 자금 사용처 · 후속 투자계획"
    if kind == "holtec_smr_partnership":
        return "SMR-300 NRC 인허가 · FEED/EPC 계약 · 현대건설 공급범위·수주액 · 부지·착공 일정"
    if kind == "palisades_restart":
        return "연료집합체 처리 · NRC 허가변경/검토 · 핵연료 장전 재개 · Mode 5→4→3 · 계통동기·상업운전"
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

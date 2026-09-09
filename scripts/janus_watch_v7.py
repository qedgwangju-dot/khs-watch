#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

import janus_watch_v2 as j2
import janus_watch_v5 as j5
import janus_watch_v6 as j6

# v7 핵심:
# 1) 미국 대형원전을 DOE AP1000 10기 / Fermi AP1000 4기 / 한미 협상 8기 3트랙으로 분리
# 2) AP1000 vs APR1400 노형별 한국 기업 매출 민감도를 물량×단가×최신 USD/KRW로 자동 계산
# 3) FEED → EPC → FID → 장납기 기자재 발주를 분리하고 계약 위험(고정가·지체상금·보증·현지화)을 추적
# 4) 단순 주가반응 기사는 신규 프로젝트 사실이 없으면 억제

US_TRACK_KINDS = {
    "us_nuclear_project",
    "us_nuclear_official",
    "doe_ap1000_track",
    "fermi_ap1000_track",
    "nuclear_contract_terms",
}

TRACK_QUERIES = [
    (
        "DOE AP1000 10기·장납기 공급망",
        "DOE AP1000 10 reactors 17.5 billion long lead fixed price Westinghouse utilities when:30d",
        "doe_ap1000_rss",
    ),
    (
        "Fermi AP1000 4기·현대건설",
        "Fermi America Hyundai E&C AP1000 four reactors FEED EPC Project Matador when:30d",
        "fermi_ap1000_rss",
    ),
    (
        "미국 원전 EPC 계약조건",
        "AP1000 APR1400 nuclear EPC fixed price cost overrun liquidated damages performance guarantee local content when:30d",
        "nuclear_contract_terms_rss",
    ),
    (
        "미국 원전 계약조건 한국 뉴스",
        "미국 원전 AP1000 APR1400 EPC 고정가 지체상금 성능보증 현지화 원가초과 when:30d",
        "nuclear_contract_terms_rss",
    ),
]

for name, query, kind in TRACK_QUERIES:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": kind})

for term in [
    "Fermi America", "Project Matador", "FEED", "EPC", "FID", "DOE", "EDF",
]:
    if term not in j2._PROTECTED_TERMS:
        j2._PROTECTED_TERMS.append(term)


def _fresh(pub: str, max_days: int = 35) -> bool:
    if not pub:
        return True
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() <= max_days * 86400
    except Exception:
        return True


def _clean_title(title: str) -> str:
    title = j2.base.norm(title)
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def _track_kind(title: str, requested_kind: str) -> str:
    low = (title or "").lower()
    if requested_kind == "doe_ap1000_rss":
        if not any(x in low for x in ["ap1000", "westinghouse", "웨스팅하우스", "원전", "nuclear"]):
            return ""
        if not any(x in low for x in ["10", "17.5", "175억", "장납기", "long lead", "long-lead", "doe", "department of energy", "공급망", "loan", "대출"]):
            return ""
        return "doe_ap1000_track"
    if requested_kind == "fermi_ap1000_rss":
        if not any(x in low for x in ["fermi", "페르미", "project matador", "마타도르"]):
            return ""
        if not any(x in low for x in ["ap1000", "hyundai", "현대건설", "feed", "epc", "원전", "nuclear"]):
            return ""
        return "fermi_ap1000_track"
    if requested_kind == "nuclear_contract_terms_rss":
        if not any(x in low for x in ["ap1000", "apr1400", "원전", "nuclear"]):
            return ""
        if not any(x in low for x in [
            "fixed price", "고정가", "cost overrun", "원가초과", "liquidated damages", "지체상금",
            "performance guarantee", "성능보증", "local content", "현지화", "cost reimburs", "원가보전",
            "escalation", "물가연동", "warranty", "보증", "epc",
        ]):
            return ""
        return "nuclear_contract_terms"
    return ""


def _rss_track_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"미국 원전 트랙 RSS 파싱 실패 | {source['url']} | {exc}")
        return []
    rows = []
    for item in root.findall(".//item"):
        title = _clean_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        src = item.find("source")
        outlet = j2.base.norm(src.text if src is not None and src.text else "")
        kind = _track_kind(title, source.get("kind", ""))
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


def _market_reaction_only(event: dict) -> bool:
    title = (event.get("title") or "").lower()
    if not any(x in title for x in ["특징주", "들썩", "급등", "상승세", "주가", "stocks rise", "shares rise"]):
        return False
    # 주가 기사라도 노형·물량·계약·발주 등 새로운 사업 사실이 제목에 있으면 살린다.
    return not any(x in title for x in [
        "ap1000", "apr1400", "8기", "10기", "4기", "노형", "계약", "수주", "epc", "feed", "fid",
        "발주", "장납기", "투자", "mou", "부지", "건설", "지분", "인수",
    ])


_PREV_EXTRACT = j2.base.extract_items


def _extract_v7(source, page_text):
    if source.get("kind") in {"doe_ap1000_rss", "fermi_ap1000_rss", "nuclear_contract_terms_rss"}:
        return _rss_track_items(source, page_text)
    rows = _PREV_EXTRACT(source, page_text)
    return [row for row in rows if not _market_reaction_only(row)]


j2.base.extract_items = _extract_v7

# 최신 환율은 공개 API 2곳을 순차 조회한다. 둘 다 실패하면 원화 환산을 만들지 않는다.
_FX_CACHE = None


def _usdkrw():
    global _FX_CACHE
    if _FX_CACHE is not None:
        return _FX_CACHE
    attempts = []
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=12, headers={"User-Agent": j2.base.UA})
        r.raise_for_status()
        data = r.json()
        rate = float((data.get("rates") or {}).get("KRW"))
        if rate > 500:
            stamp = data.get("time_last_update_utc") or datetime.now(timezone.utc).isoformat()
            _FX_CACHE = (rate, "ExchangeRate-API", stamp)
            return _FX_CACHE
    except Exception as exc:
        attempts.append(f"ExchangeRate-API={exc}")
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=KRW", timeout=12, headers={"User-Agent": j2.base.UA})
        r.raise_for_status()
        data = r.json()
        rate = float((data.get("rates") or {}).get("KRW"))
        if rate > 500:
            _FX_CACHE = (rate, "Frankfurter", data.get("date") or datetime.now(timezone.utc).date().isoformat())
            return _FX_CACHE
    except Exception as exc:
        attempts.append(f"Frankfurter={exc}")
    j2._append_error("USD/KRW 환율 조회 실패 | " + " | ".join(attempts))
    _FX_CACHE = (None, "조회 실패", "")
    return _FX_CACHE


def _krw_text(usd_billions: float, rate: float | None) -> str:
    if not rate:
        return "원화 환산 보류"
    won = usd_billions * 1_000_000_000 * rate
    eok = round(won / 100_000_000)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조{rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def _sensitivity_lines() -> list[str]:
    rate, provider, stamp = _usdkrw()
    if not rate:
        return [
            "• 환율 API 조회 실패로 이번 회차 원화 환산은 보류",
            "• 기준 단가(확정 수주 아님): 현대건설 AP1000 40억달러/기 · 한국전력기술 APR1400 5억달러/기 · 두산에너빌리티 APR1400 20억달러/기",
        ]
    specs = [
        ("AP1000 · 현대건설", 4.0),
        ("APR1400 · 한국전력기술", 0.5),
        ("APR1400 · 두산에너빌리티", 2.0),
    ]
    lines = [
        f"• 환율: <b>1달러={rate:,.2f}원</b> · {html.escape(provider)} · {html.escape(str(stamp))}",
        "• 아래는 <b>기사·증권사 추정 기준값 × 가정 기수</b>이며 확정 수주액이 아님",
    ]
    for label, unit_b in specs:
        one = _krw_text(unit_b, rate)
        two = _krw_text(unit_b * 2, rate)
        four = _krw_text(unit_b * 4, rate)
        eight = _krw_text(unit_b * 8, rate)
        lines.append(
            f"• <b>{html.escape(label)}</b>: {unit_b:g}0억달러/기 ≈ <b>{one}/기</b> | 2기 {two} | 4기 {four} | 8기 {eight}"
            if unit_b >= 1 else
            f"• <b>{html.escape(label)}</b>: 5억달러/기 ≈ <b>{one}/기</b> | 2기 {two} | 4기 {four} | 8기 {eight}"
        )
    return lines


def _role(title: str) -> str:
    low = (title or "").lower()
    if any(x in low for x in ["특징주", "들썩", "급등", "상승세", "주가"]):
        return "시장 반응·수혜구조"
    if any(x in low for x in ["fixed price", "고정가", "지체상금", "성능보증", "원가초과", "local content", "현지화"]):
        return "계약조건·실패모드"
    if any(x in low for x in ["feed", "기본설계"]):
        return "기본설계"
    if any(x in low for x in ["epc", "본계약"]):
        return "EPC"
    if any(x in low for x in ["loan", "대출", "long lead", "장납기", "공급망"]):
        return "정부금융·장납기"
    if any(x in low for x in ["8기", "대미", "apr1400", "노형"]):
        return "한미 협상·노형"
    return "프로젝트 변화"


def _event_title_ko(event: dict) -> str:
    title = j2.base.norm(event.get("title") or "")
    try:
        return j2._translate_ko(title)
    except Exception:
        # 한국어 제목 또는 식별명 위주 제목은 그대로 두되 오류 페이지는 차단
        if re.search(r"[가-힣]", title) and not j2._BAD_TITLE_RE.search(title):
            return title
        return ""


def _render_us_cluster(events: list[dict]) -> str:
    # 중복 URL/제목 제거
    uniq = []
    seen = set()
    for e in events:
        key = ((e.get("title") or "").lower(), e.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    lines = [
        "🇺🇸 <b>[미국 대형원전 3트랙 웹감시]</b>",
        "",
        "<b>DOE AP1000 10기 · Fermi AP1000 4기 · 한미 협상 8기를 분리해서 봅니다</b>",
        f"<code>노형·계약단계·매출민감도 | 신규 변화 {len(uniq)}건</code>",
        "",
        "<b>3트랙 현재 위치</b>",
        "• <b>① DOE AP1000:</b> 5개 프로젝트×2기 = <b>10기·11GW</b> · 조건부 대출 <b>175억달러</b> · 장납기 기자재 고정가 조달 구조 · 공식 정책 트랙",
        "• <b>② Fermi America:</b> 텍사스 Project Matador <b>AP1000 4기·4GW</b> · 현대건설 <b>FEED 진행</b> · EPC 본계약 전 단계",
        "• <b>③ 한미 대미투자:</b> <b>원전 8기 보도</b> · AP1000/APR1400 기수·부지·사업자·투자금 <b>공식 확정 전</b>",
        "",
        "<b>노형별 한국 기업 매출 민감도</b>",
    ]
    lines.extend(_sensitivity_lines())
    lines.extend([
        "",
        "<b>계약 단계 — 같은 '수주'로 보지 않음</b>",
        "• <b>DOE:</b> 조건부 대출 → 프로젝트 자기자본 선투입 → 장납기 기자재 조달 → 본건설",
        "• <b>Fermi:</b> FEED → <b>EPC 본계약</b> → FID·부지별 NRC 인허가 → 장납기 기자재 발주 → 착공",
        "• <b>한미 8기:</b> 정부협의 → MOU/사업자·부지·노형 확정 → 금융구조 → FID → EPC·기자재 발주",
        "",
        "<b>계약조건·실패모드</b>",
        "• <b>가격:</b> 고정가인지 원가보전·물가연동인지 확인 — 고정가 비중이 클수록 공기·원가 초과가 시공사 마진을 훼손할 수 있음",
        "• <b>책임:</b> 지체상금 · 성능보증 · 인수시험 · 보증한도 · 공사비 초과 책임 확인",
        "• <b>현지화:</b> 미국산 우선조달·현지 공급망 비율이 높아지면 한국 기자재 몫이 줄 수 있음",
        "• <b>인허가:</b> APR1400은 NRC 설계인증을 보유하지만 실제 프로젝트의 부지·건설허가는 별도",
        "",
        "<b>이번 신규 기사·발표</b>",
    ])
    shown = 0
    for event in uniq[:10]:
        title = _event_title_ko(event)
        if not title:
            continue
        source = j2.base.norm(event.get("source") or "출처 미상")
        url = event.get("url") or ""
        linked = f"<a href=\"{html.escape(url, quote=True)}\">{html.escape(title)}</a>" if url else html.escape(title)
        lines.append(f"• <b>{html.escape(_role(title))}</b> | {html.escape(source)} — {linked}")
        shown += 1
    if shown == 0:
        lines.append("• 한국어 검증을 통과한 신규 항목이 없어 기사 링크 송출 보류")
    lines.extend([
        "",
        "<b>다음 확인</b>",
        "• <b>AP1000/APR1400 기수 → 사업자·부지 → FEED/EPC/FID → 장납기 발주 → 고정가·지체상금·보증 → 현지화율 → 한국 업체 확정 수주액</b>",
    ])
    return "\n".join(lines).strip()


_PREV_RENDER = j2.base.render_alert


def _render_v7(events, fact_changes):
    us_events = [e for e in events if e.get("kind") in US_TRACK_KINDS]
    rest = [e for e in events if e.get("kind") not in US_TRACK_KINDS]
    parts = []
    if us_events:
        parts.append(_render_us_cluster(us_events))
    # v6 렌더러는 Westinghouse 지분 이슈를 별도 파일로 분리하는 부수효과도 유지한다.
    other = _PREV_RENDER(rest, fact_changes)
    if other:
        parts.append(other)
    return "\n\n──────────\n\n".join(parts).strip()


j2.base.render_alert = _render_v7

if __name__ == "__main__":
    sys.exit(j2.base.main())

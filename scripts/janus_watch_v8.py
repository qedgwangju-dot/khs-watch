#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import janus_watch_v2 as j2
import janus_watch_v7 as j7

# v8 핵심
# 1) '두산 32조/40조' 같은 헤드라인 추정치를 확정수주와 분리
# 2) 총사업비×비중(top-down)과 노형별 기자재 단가(bottom-up)를 동시에 계산
# 3) 원전 8기 물량과 두산 공시 생산능력을 비교해 '한 해 매출' 오해를 차단
# 4) 두산 생산능력·수주잔고·증설 변화도 별도 감시

DOOSAN_ESTIMATE_KINDS = {"doosan_nuclear_estimate", "doosan_nuclear_capacity"}
j7.US_TRACK_KINDS.update(DOOSAN_ESTIMATE_KINDS)

EXTRA_QUERIES = [
    (
        "두산에너빌리티 대미원전 수주 추정",
        "두산에너빌리티 미국 원전 8기 32조 40조 1200억달러 APR1400 AP1000 주기기 when:30d",
        "doosan_estimate_rss",
    ),
    (
        "두산에너빌리티 원전 생산능력·증설",
        "두산에너빌리티 원전 주기기 생산능력 수주잔고 증설 공장 APR1400 AP1000 when:30d",
        "doosan_capacity_rss",
    ),
]

for name, query, kind in EXTRA_QUERIES:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": kind})


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


def _rss_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"두산 원전 RSS 파싱 실패 | {source['url']} | {exc}")
        return []
    rows = []
    for item in root.findall(".//item"):
        title = _clean_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        src = item.find("source")
        outlet = j2.base.norm(src.text if src is not None and src.text else "")
        low = title.lower()
        if not title or not link or not _fresh(pub):
            continue
        if not any(x in low for x in ["두산에너빌", "doosan enerbility", "두산에너빌리티"]):
            continue
        kind = ""
        if source.get("kind") == "doosan_estimate_rss":
            if any(x in low for x in ["32조", "40조", "잭팟", "1200억", "8기", "수주", "주기기", "ap1000", "apr1400"]):
                kind = "doosan_nuclear_estimate"
        elif source.get("kind") == "doosan_capacity_rss":
            if any(x in low for x in ["생산능력", "생산 능력", "증설", "공장", "수주잔고", "캐파", "capa", "capacity", "주기기"]):
                kind = "doosan_nuclear_capacity"
        if not kind:
            continue
        rows.append({
            "source": outlet or source["name"],
            "title": title[:500],
            "url": link,
            "kind": kind,
            "published": pub,
        })
        if len(rows) >= 6:
            break
    return rows


_PREV_EXTRACT = j2.base.extract_items


def _extract_v8(source, page_text):
    if source.get("kind") in {"doosan_estimate_rss", "doosan_capacity_rss"}:
        return _rss_items(source, page_text)
    return _PREV_EXTRACT(source, page_text)


j2.base.extract_items = _extract_v8


def _pct_money(total_billion: float, pct: float, rate: float | None):
    usd_b = total_billion * pct
    return usd_b, j7._krw_text(usd_b, rate)


def _doosan_number_check() -> str:
    rate, provider, stamp = j7._usdkrw()
    lines = [
        "<b>두산에너빌리티 숫자 검산 — 헤드라인과 확정수주를 분리</b>",
        "• <b>사업 총액 가정:</b> 미국 대형원전 8기 · 1,200억달러 — 현재 정부 공식 확정 전",
    ]
    if rate:
        total_krw = j7._krw_text(120.0, rate)
        lines.append(f"• <b>현재 환율:</b> 1달러={rate:,.2f}원 · {html.escape(provider)} · {html.escape(str(stamp))}")
        lines.append(f"• <b>총사업비 환산:</b> 1,200억달러 ≈ <b>{total_krw}</b>")
        usd20, krw20 = _pct_money(120.0, 0.20, rate)
        usd15, krw15 = _pct_money(120.0, 0.15, rate)
        usd30, krw30 = _pct_money(120.0, 0.30, rate)
        lines.extend([
            f"• <b>기사식 20%:</b> 총사업비×20% = {usd20:.0f}0억달러 ≈ <b>{krw20}</b> → '약 32조'의 계산 근거",
            f"• <b>연구보고서 15~30%:</b> {usd15:.0f}0억~{usd30:.0f}0억달러 ≈ <b>{krw15}~{krw30}</b>",
        ])
    else:
        lines.append("• 환율 API 실패 — 원화 환산 보류")
    lines.extend([
        "• <b>주의:</b> 위 계산은 '총사업비×주기기 비중' 방식의 상단 추정이며 두산의 확정 계약금액이 아님",
        "",
        "<b>노형별 바텀업 검산</b>",
        "• <b>AP1000:</b> 두산 기자재 약 4,000억~5,000억원/기 추정",
        "• <b>APR1400:</b> 두산 기자재 약 2조5,000억~3조원/기 추정",
        "• <b>거론 조합 AP1000 6기 + APR1400 2기:</b> <b>약 7조4,000억~9조원</b>",
        "• 따라서 <b>7.4~9조원 바텀업</b>과 <b>약 32조원 이상 탑다운</b>의 간극이 크면 공급범위 확대 근거가 실제 계약으로 확인되는지 별도 추적",
        "",
        "<b>생산능력·매출 인식</b>",
        "• 두산 2026년 1분기 공시 생산능력: 원자로·증기발생기 <b>1,750MW/분기</b> · 2025년 연간 <b>7,000MW</b>",
        "• AP1000 6기(1.1GW) + APR1400 2기(1.4GW) 가정 총 <b>9.4GW</b> → 공시 연간 생산능력 7GW의 약 <b>1.34배</b>",
        "• 의미: 8기 수주가 현실화돼도 한 해에 전액 매출로 잡히는 구조가 아니라 <b>장기간 제작·진행률에 따라 분산 인식</b>",
    ])
    return "\n".join(lines)


def _capacity_bottleneck() -> str:
    return "\n".join([
        "<b>두산 추가 병목</b>",
        "• <b>공급범위:</b> AP1000에서 원자로용기·증기발생기 외 품목까지 확대되는지 확인",
        "• <b>공장 부하:</b> 미국·체코·국내 대형원전·SMR 물량이 동시에 겹칠 때 제작 슬롯과 단조품 병목 확인",
        "• <b>수익성:</b> 수주액보다 고정가·물가연동·보증·납기 지연 책임이 영업이익률을 결정",
        "• <b>조기 경보:</b> 실제 장납기 발주서 · 공급품목 목록 · 납기연장 · 생산능력 증설 · 수주잔고 증가",
    ])


_PREV_RENDER_US = j7._render_us_cluster


def _render_us_v8(events):
    text = _PREV_RENDER_US(events)
    if not any(e.get("kind") in DOOSAN_ESTIMATE_KINDS for e in events):
        return text
    insert = _doosan_number_check() + "\n\n" + _capacity_bottleneck() + "\n\n"
    marker = "<b>계약 단계 — 같은 '수주'로 보지 않음</b>"
    if marker in text:
        return text.replace(marker, insert + marker, 1)
    return text + "\n\n" + insert


j7._render_us_cluster = _render_us_v8

if __name__ == "__main__":
    sys.exit(j2.base.main())

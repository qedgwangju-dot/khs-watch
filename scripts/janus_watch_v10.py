#!/usr/bin/env python3
from __future__ import annotations

import html
import math
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import janus_watch_v2 as j2
import janus_watch_v7 as j7
import janus_watch_v9 as j9

# v10 핵심
# 1) SMR 특별법 후속 정책뿐 아니라 AI·데이터센터·산업단지·선박·국방·우주 등 실제 수요처를 별도 감시
# 2) i-SMR 공식 설계값(170MWe/모듈, 680MWe/4모듈, 목표 건설단가 3,500달러/kWe 이하)을 이용해 수요 MW/GW를 모듈수·설비비로 단순 환산
# 3) 기사에 등장하는 수요처를 PPA/오프테이크·부지·계통접속·전원인가·인허가·핵연료·EPC로 연결해 '테마→매출' 단계를 구분
# 4) 단순 정책 기대감보다 고객 실명·용량·부지·계약·전원인가 시점이 새로 확인될 때 우선 알림

SMR_DEMAND_KINDS = {
    "smr_ai_datacenter",
    "smr_industrial_demand",
    "smr_ship_defense_space",
    "smr_offtake_contract",
}

DEMAND_QUERIES = [
    (
        "SMR AI·데이터센터 수요",
        "SMR 소형모듈원자로 AI 데이터센터 전력 PPA 전력구매계약 오프테이크 when:30d",
        "smr_ai_dc_rss",
    ),
    (
        "SMR 산업단지·분산전원",
        "SMR 소형모듈원자로 산업단지 반도체 클러스터 분산전원 전력공급 when:60d",
        "smr_industrial_rss",
    ),
    (
        "SMR 선박·국방·우주",
        "SMR 소형모듈원자로 선박 해양 국방 군사 우주 원자로 when:60d",
        "smr_mobility_rss",
    ),
    (
        "SMR 전력구매·상용계약",
        "SMR microreactor power purchase agreement offtake data center contract utility when:60d",
        "smr_offtake_rss",
    ),
]

for name, query, kind in DEMAND_QUERIES:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": kind})

for term in [
    "PPA", "AI", "i-SMR", "SMR", "MWe", "MW", "GW", "데이터센터",
]:
    if term not in j2._PROTECTED_TERMS:
        j2._PROTECTED_TERMS.append(term)


def _fresh(pub: str, max_days: int = 65) -> bool:
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
    return re.sub(r"\s+-\s+[^-]{2,100}$", "", title).strip()


def _demand_kind(title: str, requested_kind: str) -> str:
    low = (title or "").lower()
    if not any(x in low for x in ["smr", "소형모듈", "마이크로원자로", "microreactor", "micro-reactor"]):
        return ""
    if requested_kind == "smr_ai_dc_rss":
        if any(x in low for x in ["ai", "데이터센터", "data center", "datacenter", "반도체"]):
            return "smr_ai_datacenter"
        return ""
    if requested_kind == "smr_industrial_rss":
        if any(x in low for x in ["산업단지", "클러스터", "공장", "분산전원", "산업용", "industrial"]):
            return "smr_industrial_demand"
        return ""
    if requested_kind == "smr_mobility_rss":
        if any(x in low for x in ["선박", "해양", "국방", "군사", "우주", "ship", "marine", "defense", "military", "space"]):
            return "smr_ship_defense_space"
        return ""
    if requested_kind == "smr_offtake_rss":
        if any(x in low for x in ["ppa", "전력구매", "오프테이크", "offtake", "contract", "계약", "customer", "고객"]):
            return "smr_offtake_contract"
        return ""
    return ""


def _rss_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"SMR 수요 RSS 파싱 실패 | {source['url']} | {exc}")
        return []
    rows = []
    for item in root.findall(".//item"):
        title = _clean_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        src = item.find("source")
        outlet = j2.base.norm(src.text if src is not None and src.text else "")
        kind = _demand_kind(title, source.get("kind", ""))
        if not title or not link or not kind or not _fresh(pub):
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


def _extract_v10(source, page_text):
    if source.get("kind") in {"smr_ai_dc_rss", "smr_industrial_rss", "smr_mobility_rss", "smr_offtake_rss"}:
        return _rss_items(source, page_text)
    return _PREV_EXTRACT(source, page_text)


j2.base.extract_items = _extract_v10


def _title_ko(event: dict) -> str:
    title = j2.base.norm(event.get("title") or "")
    try:
        return j2._translate_ko(title)
    except Exception:
        if re.search(r"[가-힣]", title) and not j2._BAD_TITLE_RE.search(title):
            return title
        return ""


def _extract_capacity_mw(text: str):
    # 제목에서 첫 MW/GW 수치를 읽어 단순 설비용량 환산에만 사용한다.
    m = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(GW|MW|MWe)\b", text or "", re.I)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).upper()
    return value * 1000.0 if unit == "GW" else value


def _krw_amount_from_usd(usd: float, rate: float | None) -> str:
    if not rate:
        return "원화 환산 보류"
    won = usd * rate
    eok = round(won / 100_000_000)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조{rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def _capacity_math(events: list[dict]) -> list[str]:
    lines = [
        "• <b>i-SMR 기준:</b> 모듈당 170MWe · 4모듈 680MWe · 설계수명 80년",
        "• <b>공식 설계 목표 건설단가:</b> 3,500달러/kWe 이하 — 실제 국내 1호기 EPC 예산과는 다름",
    ]
    rate, provider, stamp = j7._usdkrw()
    module_usd = 170_000 * 3500
    plant_usd = 680_000 * 3500
    if rate:
        lines.append(
            f"• 설계 목표단가 단순 적용: 170MW 1모듈 ≤ <b>{_krw_amount_from_usd(module_usd, rate)}</b> · 680MW 4모듈 ≤ <b>{_krw_amount_from_usd(plant_usd, rate)}</b>"
        )
        lines.append(f"• 환율: 1달러={rate:,.2f}원 · {html.escape(provider)} · {html.escape(str(stamp))}")
    found = None
    for event in events:
        found = _extract_capacity_mw(event.get("title") or "")
        if found:
            break
    if found:
        modules = math.ceil(found / 170.0)
        four_module_plants = math.ceil(found / 680.0)
        lines.append(
            f"• 기사 용량 <b>{found:,.0f}MW</b> 단순 환산 → 170MW 모듈 최소 <b>{modules}개</b> 또는 680MW급 4모듈 발전소 약 <b>{four_module_plants}식</b>"
        )
        lines.append("• 주의: 이용률·예비력·정비정지·송전제약을 제외한 단순 명목 설비용량 비교")
    return lines


def _kind_label(kind: str) -> str:
    return {
        "smr_ai_datacenter": "AI·데이터센터",
        "smr_industrial_demand": "산업단지·분산전원",
        "smr_ship_defense_space": "선박·국방·우주",
        "smr_offtake_contract": "전력구매·상용계약",
    }.get(kind, "SMR 수요")


def _render_demand_cluster(events: list[dict]) -> str:
    uniq = []
    seen = set()
    for e in events:
        key = ((e.get("title") or "").lower(), e.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    lines = [
        "⚡ <b>[SMR 실수요·AI 데이터센터 웹감시]</b>",
        "",
        "<b>특별법이 실제 수요처·계약·발주로 연결되는지를 추적합니다</b>",
        f"<code>수요처·MW/GW·오프테이크·전원인가 | 신규 변화 {len(uniq)}건</code>",
        "",
        "<b>수요처별 의미</b>",
        "• <b>AI·데이터센터:</b> 24시간 기저전력 수요 → 고객 실명·필요 MW·PPA·부지·전원인가 시점이 핵심",
        "• <b>산업단지·반도체:</b> 대규모 연속부하 → 원전 자체보다 송전망·변전소·계통접속 일정도 함께 확인",
        "• <b>선박·국방·우주:</b> 이동성·독립전원 가치가 크지만 별도 안전기준·보험·책임체계가 상용화 병목",
        "",
        "<b>i-SMR 용량·설비비 단순 환산</b>",
    ]
    lines.extend(_capacity_math(uniq))
    lines.extend([
        "",
        "<b>테마에서 매출로 넘어가는 순서</b>",
        "• <b>고객 실명 → 필요 전력 MW/GW → 부지 → PPA/오프테이크 → 계통접속·전원인가 → 인허가 → 핵연료 → FEED/EPC → 장납기 기자재 → 상업운전</b>",
        "",
        "<b>핵심 병목·실패모드</b>",
        "• <b>전력망:</b> 원자로가 준비돼도 변전소·송전선·계통접속이 늦으면 데이터센터 전원인가가 지연",
        "• <b>냉각·입지:</b> 냉각수·환경·지역수용성·비상전원·보험 조건이 부지 확정을 늦출 수 있음",
        "• <b>인허가:</b> 표준설계인가와 개별 부지 건설허가는 별도이며, 상용화 목표가 법정 기한을 보장하지 않음",
        "• <b>핵연료:</b> 농축·가공·운송·장기 공급계약이 확보되지 않으면 반복 배치가 지연될 수 있음",
        "",
        "<b>이번 신규 기사·발표</b>",
    ])
    shown = 0
    for e in uniq[:10]:
        title = _title_ko(e)
        if not title:
            continue
        source = j2.base.norm(e.get("source") or "출처 미상")
        url = e.get("url") or ""
        linked = f"<a href=\"{html.escape(url, quote=True)}\">{html.escape(title)}</a>" if url else html.escape(title)
        lines.append(f"• <b>{html.escape(_kind_label(e.get('kind') or ''))}</b> | {html.escape(source)} — {linked}")
        shown += 1
    if shown == 0:
        lines.append("• 한국어 검증을 통과한 신규 항목이 없어 기사 링크 송출 보류")
    lines.extend([
        "",
        "<b>다음 확인</b>",
        "• <b>고객 실명 · MW/GW · PPA 단가/기간 · 부지 · 전원인가 · 표준설계인가/건설허가 · 핵연료 계약 · 주기기/EPC 발주액</b>",
    ])
    return "\n".join(lines).strip()


_PREV_RENDER = j2.base.render_alert


def _render_v10(events, fact_changes):
    demand = [e for e in events if e.get("kind") in SMR_DEMAND_KINDS]
    rest = [e for e in events if e.get("kind") not in SMR_DEMAND_KINDS]
    parts = []
    if demand:
        parts.append(_render_demand_cluster(demand))
    other = _PREV_RENDER(rest, fact_changes)
    if other:
        parts.append(other)
    return "\n\n──────────\n\n".join(parts).strip()


j2.base.render_alert = _render_v10

if __name__ == "__main__":
    sys.exit(j2.base.main())

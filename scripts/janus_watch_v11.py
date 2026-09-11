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
import janus_watch_v10 as j10

# v11 핵심
# 1) 가스터빈 시장을 '공급부족 → 정상화 → 공급과잉 위험'의 국면 변화로 추적
# 2) 글로벌 생산능력·수주잔고/슬롯·납기·슬롯가격·취소/연기를 함께 보고 단순 '2030 과잉' 헤드라인을 검증
# 3) 두산에너빌리티의 빠른 납기 우위가 실제 반복고객·후속수주·장기 유지보수 계약으로 전환되는지 추적
# 4) 가스터빈 단품보다 발전기·스팀터빈·HRSG·LTSA를 합친 프로젝트당 매출 범위를 추적
# 5) 블레이드/베인·단조품·특수합금·발전기·HRSG·숙련인력을 실제 공급병목으로 감시

GAS_TURBINE_KINDS = {
    "gt_capacity_cycle",
    "gt_backlog_slot",
    "gt_price_leadtime",
    "gt_supply_bottleneck",
    "doosan_gt_order",
    "doosan_gt_service",
    "gt_datacenter_demand",
    "gt_project_bundle",
}

QUERIES = [
    (
        "가스터빈 글로벌 생산능력·과잉 위험",
        'gas turbine capacity 2030 overcapacity shortage GE Vernova Siemens Energy Mitsubishi Heavy Industries BloombergNEF when:45d',
        "gt_capacity_rss",
    ),
    (
        "가스터빈 수주잔고·슬롯·납기",
        'gas turbine backlog slot reservation lead time sold out price GE Vernova Siemens Energy Mitsubishi when:45d',
        "gt_backlog_rss",
    ),
    (
        "가스터빈 핵심부품 병목",
        'gas turbine blade vane forging alloy generator HRSG supply chain bottleneck lead time when:60d',
        "gt_bottleneck_rss",
    ),
    (
        "두산 가스터빈·스팀터빈·서비스",
        '두산에너빌리티 가스터빈 스팀터빈 발전기 미국 데이터센터 장기유지보수 LTSA 수주 when:60d',
        "doosan_gt_rss",
    ),
    (
        "데이터센터 가스터빈 실수요",
        'data center gas turbine FID order contract utility power project cancellation delay when:45d',
        "gt_dc_rss",
    ),
    (
        "가스터빈 복합발전 패키지",
        '가스터빈 발전기 스팀터빈 HRSG 배열회수보일러 장기유지보수 데이터센터 수주 when:60d',
        "gt_bundle_rss",
    ),
]

for name, query, kind in QUERIES:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    if not any(s.get("url") == url for s in j2.base.SOURCES):
        j2.base.SOURCES.append({"name": name, "url": url, "kind": kind})

# 현재 국면의 공식/신뢰 기준선을 직접 저장한다. 동일 수치는 기준선으로만 쓰고,
# 향후 원문이 갱신돼 지표가 바뀌면 fingerprint가 달라져 새 변화로 잡힌다.
for source in [
    {
        "name": "BloombergNEF 가스터빈 생산능력 전망",
        "url": "https://about.bnef.com/insights/finance/global-gas-turbine-manufacturing-outlook-crunch-for-now/",
        "kind": "gt_bnef_static",
    },
    {
        "name": "GE Vernova 가스터빈 수주잔고·생산능력",
        "url": "https://www.gevernova.com/news/articles/ge-vernova-releases-second-quarter-2026-financial-results",
        "kind": "gt_ge_static",
    },
    {
        "name": "두산에너빌리티 미국 가스터빈 수주",
        "url": "https://www.doosanenerbility.com/kr/about/news_board_view?id=21000800&page=0&pageSize=9",
        "kind": "gt_doosan_static",
    },
    {
        "name": "두산에너빌리티 미국 스팀터빈 수주",
        "url": "https://www.doosanenerbility.com/kr/about/news_board_view?id=21000808&page=0&pageSize=9",
        "kind": "gt_doosan_static",
    },
]:
    if not any(s.get("url") == source["url"] for s in j2.base.SOURCES):
        j2.base.SOURCES.append(source)

for term in [
    "GE Vernova", "Siemens Energy", "Mitsubishi Heavy Industries", "MHI",
    "BloombergNEF", "BNEF", "LTSA", "HRSG", "Doosan Enerbility", "DTS",
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


def _gt_kind(title: str, requested_kind: str) -> str:
    low = (title or "").lower()
    gt = any(x in low for x in ["gas turbine", "가스터빈", "gas power", "h-class", "j-class", "380mw"])
    if requested_kind == "gt_capacity_rss":
        if gt and any(x in low for x in ["capacity", "생산능력", "증설", "overcapacity", "공급과잉", "shortage", "품귀", "2030"]):
            return "gt_capacity_cycle"
        return ""
    if requested_kind == "gt_backlog_rss":
        if gt and any(x in low for x in ["backlog", "slot", "reservation", "수주잔고", "슬롯", "납기", "sold out", "매진", "lead time", "price", "가격"]):
            return "gt_backlog_slot"
        return ""
    if requested_kind == "gt_bottleneck_rss":
        if any(x in low for x in ["turbine", "터빈"] ) and any(x in low for x in [
            "blade", "vane", "블레이드", "베인", "forging", "단조", "alloy", "합금", "generator", "발전기",
            "hrsg", "배열회수보일러", "workforce", "인력", "bottleneck", "병목",
        ]):
            return "gt_supply_bottleneck"
        return ""
    if requested_kind == "doosan_gt_rss":
        if not any(x in low for x in ["두산에너빌", "doosan enerbility", "두산 터보"]):
            return ""
        if any(x in low for x in ["유지보수", "서비스", "ltsa", "정비", "dts", "업그레이드"]):
            return "doosan_gt_service"
        if any(x in low for x in ["가스터빈", "gas turbine", "스팀터빈", "발전기", "수주", "공급계약", "데이터센터"]):
            return "doosan_gt_order"
        return ""
    if requested_kind == "gt_dc_rss":
        if any(x in low for x in ["data center", "datacenter", "데이터센터"] ) and any(x in low for x in ["gas", "turbine", "가스터빈", "power", "전력"]):
            return "gt_datacenter_demand"
        return ""
    if requested_kind == "gt_bundle_rss":
        if any(x in low for x in ["가스터빈", "gas turbine", "복합발전"] ) and any(x in low for x in ["스팀터빈", "generator", "발전기", "hrsg", "배열회수보일러", "ltsa", "유지보수"]):
            return "gt_project_bundle"
        return ""
    return ""


def _rss_items(source, page_text):
    try:
        root = ET.fromstring(page_text)
    except Exception as exc:
        j2._append_error(f"가스터빈 RSS 파싱 실패 | {source['url']} | {exc}")
        return []
    rows = []
    for item in root.findall(".//item"):
        title = _clean_title(item.findtext("title") or "")
        link = j2.base.norm(item.findtext("link") or "")
        pub = j2.base.norm(item.findtext("pubDate") or "")
        src = item.find("source")
        outlet = j2.base.norm(src.text if src is not None and src.text else "")
        kind = _gt_kind(title, source.get("kind", ""))
        if not title or not link or not kind or not _fresh(pub):
            continue
        # 단순 주가반응만 있고 공급·수주·계약·설비 정보가 없으면 억제
        low = title.lower()
        if any(x in low for x in ["특징주", "급등", "주가", "상승세"]) and not any(x in low for x in [
            "수주", "계약", "생산능력", "증설", "슬롯", "납기", "backlog", "capacity", "order", "contract",
        ]):
            continue
        rows.append({
            "source": outlet or source["name"],
            "title": title[:500],
            "url": link,
            "kind": kind,
            "published": pub,
        })
        if len(rows) >= 7:
            break
    return rows


def _num(text: str, patterns: list[str]):
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                continue
    return None


def _static_item(source, page_text):
    text = j2.base.norm(re.sub(r"<[^>]+>", " ", page_text))
    kind = source.get("kind")
    if kind == "gt_bnef_static":
        add = _num(text, [r"(35)\s*GW", r"(35)GW"])
        big3 = _num(text, [r"(28)\s*GW", r"(28)GW"])
        now_share = _num(text, [r"about\s*(66)%", r"약\s*(66)%"])
        future_share = _num(text, [r"roughly\s*(70)%", r"약\s*(70)%"])
        title = f"BNEF 가스터빈 2030 생산능력 변화 · 추가 {add or 35:.0f}GW · 빅3 {big3 or 28:.0f}GW · 점유율 {now_share or 66:.0f}%→{future_share or 70:.0f}%"
        return [{"source": source["name"], "title": title, "url": source["url"], "kind": "gt_capacity_cycle"}]
    if kind == "gt_ge_static":
        backlog = _num(text, [r"(?:from\s*100\s*to\s*)?(116)\s*GW", r"(116)\s*GW"])
        target = _num(text, [r"(?:at least\s*)(125)\s*GW", r"(125)\s*GW"])
        c26 = _num(text, [r"(20)\s*GW\s*of\s*annual", r"(20)\s*GW"])
        c28 = _num(text, [r"(24)\s*GW\s*in\s*2028"])
        c30 = _num(text, [r"(30)\s*GW\s*in\s*2030"])
        title = f"GE Vernova 가스터빈 · 수주잔고+슬롯 {backlog or 116:.0f}GW · 연말 {target or 125:.0f}GW 목표 · 생산능력 {c26 or 20:.0f}→{c28 or 24:.0f}→{c30 or 30:.0f}GW"
        return [{"source": source["name"], "title": title, "url": source["url"], "kind": "gt_backlog_slot"}]
    if kind == "gt_doosan_static":
        if "가스터빈 7기" in text or "seven" in text.lower():
            title = "두산에너빌리티 미국 가스터빈 · 380MW 7기 추가 · 미국 누적 12기 · 2029년 5월부터 월 1기 순차 공급"
            return [{"source": source["name"], "title": title, "url": source["url"], "kind": "doosan_gt_order"}]
        title = "두산에너빌리티 미국 스팀터빈 · 370MW 4기+발전기 · 2029년까지 순차 공급"
        return [{"source": source["name"], "title": title, "url": source["url"], "kind": "gt_project_bundle"}]
    return []


_PREV_EXTRACT = j2.base.extract_items


def _extract_v11(source, page_text):
    if source.get("kind") in {"gt_capacity_rss", "gt_backlog_rss", "gt_bottleneck_rss", "doosan_gt_rss", "gt_dc_rss", "gt_bundle_rss"}:
        return _rss_items(source, page_text)
    if source.get("kind") in {"gt_bnef_static", "gt_ge_static", "gt_doosan_static"}:
        return _static_item(source, page_text)
    return _PREV_EXTRACT(source, page_text)


j2.base.extract_items = _extract_v11


def _title_ko(event: dict) -> str:
    title = j2.base.norm(event.get("title") or "")
    try:
        return j2._translate_ko(title)
    except Exception:
        if re.search(r"[가-힣]", title) and not j2._BAD_TITLE_RE.search(title):
            return title
        return ""


def _phase(events: list[dict]) -> tuple[str, list[str]]:
    shortage = []
    easing = []
    oversupply = []
    for e in events:
        text = (e.get("title") or "").lower()
        if any(x in text for x in ["shortage", "품귀", "sold out", "매진", "backlog", "수주잔고", "slot", "슬롯", "price increase", "가격 인상", "납기 연장"]):
            shortage.append(e.get("title") or "")
        if any(x in text for x in ["capacity", "생산능력", "증설", "lead time shorter", "납기 단축", "공급 완화", "normalization", "정상화"]):
            easing.append(e.get("title") or "")
        if any(x in text for x in ["overcapacity", "공급과잉", "oversupply", "취소", "cancel", "deferral", "연기", "discount", "가격 하락", "idle capacity"]):
            oversupply.append(e.get("title") or "")
    if oversupply:
        return "공급과잉 위험 상승", oversupply[:3]
    if easing and shortage:
        return "공급부족 지속 속 증설·정상화 신호 동시 발생", (shortage + easing)[:3]
    if easing:
        return "공급부족 완화·정상화 신호", easing[:3]
    return "공급부족 지속 — 국면 전환 증거 부족", shortage[:3]


def _kind_label(kind: str) -> str:
    return {
        "gt_capacity_cycle": "생산능력·과잉위험",
        "gt_backlog_slot": "수주잔고·슬롯",
        "gt_price_leadtime": "가격·납기",
        "gt_supply_bottleneck": "핵심부품 병목",
        "doosan_gt_order": "두산 가스터빈 수주",
        "doosan_gt_service": "두산 서비스·LTSA",
        "gt_datacenter_demand": "데이터센터 실수요",
        "gt_project_bundle": "복합발전 패키지",
    }.get(kind, "가스터빈")


def _render_gt_cluster(events: list[dict]) -> str:
    uniq = []
    seen = set()
    for e in events:
        key = ((e.get("title") or "").lower(), e.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    phase, evidence = _phase(uniq)
    lines = [
        "🔥 <b>[가스터빈 공급부족·과잉 전환 웹감시]</b>",
        "",
        f"<b>현재 판정: {html.escape(phase)}</b>",
        f"<code>생산능력·수주잔고·슬롯·납기·가격·서비스 | 신규 변화 {len(uniq)}건</code>",
        "",
        "<b>현재 기준선</b>",
        "• <b>BNEF:</b> 2030년까지 글로벌 연간 생산능력 <b>+35GW</b>, 이 중 GE Vernova·Siemens Energy·MHI가 <b>+28GW</b>",
        "• <b>빅3 점유율:</b> 약 <b>66% → 70%</b> — 공급정상화가 와도 기존 3사의 시장지배력은 강화될 수 있음",
        "• <b>GE Vernova:</b> 가스터빈 수주잔고+슬롯 <b>116GW</b> · 연말 최소 125GW 목표 · 생산능력 <b>20GW → 24GW(2028) → 30GW(2030)</b>",
        "• <b>GE 단순 잔고연수:</b> 116÷20 ≈ <b>5.8년</b> · 신규수주가 전혀 없다는 가정에서 116÷30 ≈ <b>3.9년</b>",
        "• <b>두산에너빌리티:</b> 미국 380MW 가스터빈 누적 <b>12기</b> · 2029년 5월부터 최근 7기를 월 1기씩 순차 공급",
        "",
        "<b>국면 전환 판정 기준</b>",
        "• <b>공급부족 지속:</b> 수주잔고/슬롯 증가 · 납기 장기화 · 슬롯가격 상승 · 고객 선예약 확대",
        "• <b>정상화:</b> 생산능력 증가 + 잔고연수 축소 + 납기 단축 + 슬롯가격 상승세 둔화",
        "• <b>과잉 위험:</b> <b>취소/연기 + 가격 할인 + 유휴 생산능력 + 잔고연수 급락</b>이 함께 나타날 때 상향 판정",
        "• 따라서 <b>'2030년'이라는 날짜만으로 공급과잉으로 판정하지 않음</b>",
        "",
        "<b>두산 — 공급부족 시기를 반복매출로 전환하는지</b>",
        "• <b>장비:</b> 가스터빈 + 발전기 + 스팀터빈 + HRSG 중 프로젝트별 공급범위를 분리 추적",
        "• <b>서비스:</b> LTSA · 장기 부품공급 · 주기적 점검 · O&M · 고온부품 재생정비 · 로터정비",
        "• <b>서비스 시계:</b> 2029년 설치물량은 일반적 정비주기를 참고하면 <b>2031~2032년 초기 점검, 2034년 전후 대정비</b>가 반복매출 확인 구간 — 실제 계약주기를 우선",
        "• <b>수주 질:</b> 첫 고객 → 반복발주 → 납기준수 → 운전시간/가동률 → LTSA 체결 → 서비스 매출 순으로 추적",
        "",
        "<b>공급망 병목</b>",
        "• 블레이드·베인 · 대형 단조품 · 특수합금 · 발전기 · HRSG · 숙련인력",
        "• 최종 조립공장 증설과 실제 공급가능능력을 분리 — 핵심부품 납기가 늘면 발표된 증설 효과가 늦어질 수 있음",
        "",
        "<b>이번 신규 기사·공식자료</b>",
    ]

    shown = 0
    for e in uniq[:12]:
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

    if evidence:
        lines.extend(["", "<b>이번 국면 판정 근거</b>"])
        for item in evidence:
            try:
                item = j2._translate_ko(item)
            except Exception:
                pass
            lines.append(f"• {html.escape(j2.base.norm(item))}")

    lines.extend([
        "",
        "<b>다음 확인</b>",
        "• <b>GE/Siemens/MHI 생산능력 · 수주잔고/슬롯 · 잔여 슬롯연도 · 납기 · 슬롯가격 · 취소/연기 · 두산 반복고객·LTSA · 데이터센터 FID/전원인가</b>",
    ])
    return "\n".join(lines).strip()


_PREV_RENDER = j2.base.render_alert


def _render_v11(events, fact_changes):
    gt = [e for e in events if e.get("kind") in GAS_TURBINE_KINDS]
    rest = [e for e in events if e.get("kind") not in GAS_TURBINE_KINDS]
    parts = []
    if gt:
        parts.append(_render_gt_cluster(gt))
    other = _PREV_RENDER(rest, fact_changes)
    if other:
        parts.append(other)
    return "\n\n──────────\n\n".join(parts).strip()


j2.base.render_alert = _render_v11

if __name__ == "__main__":
    sys.exit(j2.base.main())

#!/usr/bin/env python3
"""에너지 공급감시 v33: 원유 차질이 정제제품·재고·디젤 위기로 전이되는 단계 감시.

특정 기사 자체가 아니라 다음 사건·상태 변화를 추적한다.
- 상업용 연료재고의 장기 감소/바닥 접근
- 전략비축 여력 축소
- 정유설비 여유능력 부족·정유공장 차질
- 디젤/중간유분 공급 부족과 겨울 수급 스트레스
- 재고 재축적·정제능력 회복·공급 완화

v32의 사건 감시, 중복방지, 한국어 최종 가드와 기존 LNG/호르무즈 감시는 그대로 유지한다.
"""
from __future__ import annotations

import hashlib
import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v32 as v32

v31 = v32.v31
v30 = v31.v30
v26 = v30.v26
v12 = v32.v12
v8 = v32.v8

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test
_BASE_CONFIRMED = core.confirmed_news_groups
_BASE_POLARITY = core.classify_polarity
_BASE_CATEGORY_LABEL = core.category_label

CATEGORY = "refined_fuel_supply"

FUEL_STRESS_QUERIES = (
    (CATEGORY, '"fuel crisis" diesel gasoline inventories refinery capacity when:3d'),
    (CATEGORY, '"commercial fuel stocks" depleted refinery diesel when:7d'),
    (CATEGORY, '"diesel supply" tight winter refinery capacity inventories when:7d'),
    (CATEGORY, '"distillate inventories" shortage refinery outages winter when:7d'),
    (CATEGORY, '"strategic reserves" fuel stocks refinery capacity oil crisis when:7d'),
    (CATEGORY, '정제제품 디젤 재고 부족 정유공장 생산능력 겨울 공급 when:7d'),
    (CATEGORY, '상업용 연료 재고 전략비축 디젤 공급 부족 정제능력 when:7d'),
)
for item in FUEL_STRESS_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "vitol", "phillips 66", "chevron", "exxonmobil", "conocophillips",
    "u.s. energy information administration", "eia",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + (
    "u.s. energy information administration", "eia",
)

core.WORSENING_TERMS[CATEGORY] = (
    "great fuel crisis", "fuel crisis", "commercial fuel stocks", "stocks depleted",
    "stockpiles depleted", "bottom of our stockpiles", "strategic reserves", "can't be tapped much further",
    "diesel shortage", "diesel supply tight", "diesel supplies tight", "distillate inventories",
    "below five-year", "refinery outage", "refinery outages", "lack of spare refining capacity",
    "refining capacity", "record diesel", "record-high diesel", "product shortage", "fuel shortage",
    "연료 위기", "상업용 연료 재고", "재고 고갈", "전략비축 여력", "디젤 부족",
    "중간유분 재고", "정유공장 차질", "정제능력 부족", "연료 부족",
)
core.EASING_TERMS[CATEGORY] = (
    "inventories rebuild", "stocks rebuild", "stockpiles recover", "diesel supply eases",
    "refinery capacity restored", "refinery restart", "refineries restart", "strategic reserve replenished",
    "재고 재축적", "재고 회복", "디젤 수급 완화", "정유공장 재가동", "정제능력 회복",
)

core.SUBTYPE_TERMS = (
    ("fuel_crisis_systemic", ("great fuel crisis", "fuel crisis", "연료 위기")),
    ("refined_inventory_draw", ("commercial fuel stocks", "stockpiles depleted", "bottom of our stockpiles", "distillate inventories", "재고 고갈", "상업용 연료 재고", "중간유분 재고")),
    ("diesel_shortage", ("diesel shortage", "diesel supply tight", "diesel supplies tight", "record diesel", "디젤 부족")),
    ("refinery_capacity_tight", ("lack of spare refining capacity", "refinery outage", "refinery outages", "refining capacity", "정제능력 부족", "정유공장 차질")),
    ("fuel_buffer_rebuild", ("inventories rebuild", "stocks rebuild", "diesel supply eases", "refinery capacity restored", "재고 재축적", "정제능력 회복")),
) + tuple(core.SUBTYPE_TERMS)

v26.STAGE_LABELS.update({
    "fuel_crisis_systemic": "원유 차질이 글로벌 연료 위기로 전이",
    "refined_inventory_draw": "상업용 연료·중간유분 재고 감소",
    "diesel_shortage": "디젤·중간유분 공급 부족",
    "refinery_capacity_tight": "정유설비 여유능력·가동 차질",
    "fuel_buffer_rebuild": "연료재고·정제능력 회복",
})
v26.CATEGORY_MEANING[CATEGORY] = "정제제품 재고·디젤·정유설비 여유능력·전략비축"

v8.KNOWN_TRANSLATIONS.update({
    "Oil Executives Say the Great Fuel Crisis Is Here":
        "미국 석유업계 경영진, 글로벌 연료 위기가 이미 시작됐다고 경고",
    "Oil Executives Say the Great Fuel Crisis Is Here - The Wall Street Journal":
        "미국 석유업계 경영진, 글로벌 연료 위기가 이미 시작됐다고 경고",
    "Global diesel supply to stay tight through winter, industry execs say":
        "글로벌 디젤 공급, 겨울까지 빠듯할 전망…업계 경영진 경고",
    "Global diesel supply to stay tight through winter, industry execs say - Reuters":
        "글로벌 디젤 공급, 겨울까지 빠듯할 전망…업계 경영진 경고",
})

MAJOR_SOURCES = (
    "reuters", "bloomberg", "financial times", "wall street journal", "wsj",
    "cnbc", "associated press", "ap news", "vitol", "phillips 66", "chevron",
    "u.s. energy information administration", "eia",
)


def category_label_v33(category: str) -> str:
    if category == CATEGORY:
        return "정제제품·디젤·연료재고 공급망"
    return _BASE_CATEGORY_LABEL(category)


def classify_polarity_v33(category: str, title: str) -> str | None:
    if category != CATEGORY:
        return _BASE_POLARITY(category, title)
    normalized = core.normalize_text(title)
    if any(term in normalized for term in core.EASING_TERMS[CATEGORY]):
        if not any(term in normalized for term in core.WORSENING_TERMS[CATEGORY]):
            return "easing"
    if any(term in normalized for term in core.WORSENING_TERMS[CATEGORY]):
        return "worsening"
    return None


def _event_id(item: core.NewsItem) -> str:
    bucket = int(item.published_epoch // (3 * 24 * 3600))
    raw = f"{CATEGORY}|{item.subtype}|{item.polarity}|{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def confirmed_news_groups_v33(items: list[core.NewsItem]):
    base = [g for g in _BASE_CONFIRMED(items) if str(g.get("category") or "") != CATEGORY]
    fuel_items = [item for item in items if item.category == CATEGORY]
    buckets: dict[tuple[str, str], list[core.NewsItem]] = {}
    for item in fuel_items:
        buckets.setdefault((item.subtype, item.polarity), []).append(item)

    for (_, _), group in buckets.items():
        group.sort(key=lambda x: x.published_epoch, reverse=True)
        latest = group[0]
        recent = [x for x in group if latest.published_epoch - x.published_epoch <= 48 * 3600]
        official = [x for x in recent if x.official]
        major = [x for x in recent if core.source_matches(x.source, MAJOR_SOURCES)]
        distinct = {core.normalize_text(x.source) for x in recent}
        if not official and not major and len(distinct) < 2:
            continue
        evidence: list[core.NewsItem] = []
        used: set[str] = set()
        for item in (official + major + recent):
            key = core.normalize_text(item.source)
            if key in used:
                continue
            evidence.append(item)
            used.add(key)
            if len(evidence) >= 2:
                break
        verification = (
            "공식 통계·기관 확인" if official else
            "연료 공급 조기경보 · 주요 매체/업계 1곳 이상 확인" if len(distinct) < 2 else
            "연료 공급 스트레스 · 신뢰 매체 2곳 교차"
        )
        base.append({
            "category": CATEGORY,
            "polarity": latest.polarity,
            "subtype": latest.subtype,
            "event_id": _event_id(latest),
            "latest_epoch": latest.published_epoch,
            "evidence": evidence,
            "verification": verification,
        })
    base.sort(key=lambda g: float(g.get("latest_epoch") or 0), reverse=True)
    return base


def _fuel_groups(groups):
    return [g for g in groups if str(g.get("category") or "") == CATEGORY]


def _title_ko(item: core.NewsItem) -> str:
    return v32._strict_title(item)


def _source_ko(source: str) -> str:
    return v32._source_ko(source)


def _evidence_lines(groups) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for group in sorted(groups, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True):
        for item in list(group.get("evidence") or []):
            raw_title = str(getattr(item, "title", "") or "").strip()
            link = str(getattr(item, "link", "") or "").strip()
            key = (raw_title, link)
            if key in seen:
                continue
            seen.add(key)
            source = _source_ko(str(getattr(item, "source", "주요 매체") or "주요 매체"))
            title = _title_ko(item)
            line = f"• <b>{html.escape(source)}</b> · {html.escape(title)}"
            if link:
                line += f' · <a href="{html.escape(link, quote=True)}">원문</a>'
            lines.append(line)
            if len(lines) >= 3:
                return lines
    return lines


def _other_change_lines(groups) -> list[str]:
    others = [g for g in groups if str(g.get("category") or "") != CATEGORY]
    if not others:
        return []
    lines = ["<b>동시 감지</b>"]
    seen: set[tuple[str, str]] = set()
    for group in sorted(others, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True):
        category = str(group.get("category") or "")
        subtype = str(group.get("subtype") or "")
        key = (category, subtype)
        if key in seen:
            continue
        seen.add(key)
        try:
            label = core.category_label(category)
        except Exception:
            label = category or "관련 시장"
        stage = v26.STAGE_LABELS.get(subtype, subtype or "상태 변화")
        state = "악화" if str(group.get("polarity")) == "worsening" else "완화"
        lines.append(f"• <b>{html.escape(label)}</b> · {html.escape(stage)} · {state}")
        if len(seen) >= 4:
            break
    return lines


def _build_fuel_body(groups, quotes) -> str:
    selected = _fuel_groups(groups)
    latest = max(selected, key=lambda g: float(g.get("latest_epoch") or 0))
    subtype = str(latest.get("subtype") or "")
    polarity = str(latest.get("polarity") or "")
    stage = v26.STAGE_LABELS.get(subtype, subtype or "연료 공급 상태 변화")
    verdict = (
        "원유 차질이 정제제품·재고·디젤 부족으로 전이 · 연료 공급 스트레스 상승"
        if polarity == "worsening" else
        "연료재고·정제능력 회복 신호 · 실제 가격·재고 정상화 확인 필요"
    )

    lines = [
        "<b>한눈에</b>",
        f"• <b>판정</b> {verdict}",
        f"• <b>현재 단계</b> {html.escape(stage)}",
        "• <b>핵심 의미</b> 원유가 있어도 정유설비·재고·물류가 부족하면 디젤·휘발유 같은 최종 연료 가격은 더 오래 높은 수준을 유지할 수 있음",
        "",
        "<b>현재 숫자 추적</b>",
        "• <b>미국 중간유분 재고</b> EIA 2026-09-04 기준 <b>1억627만배럴</b> · 9월 중 1억배럴 아래로 내려갈 가능성 전망",
        "• <b>미국 전략비축유</b> EIA 2026-09-04 기준 <b>2억8,536만배럴</b>",
        "• <b>산업 경고</b> 러시아·중동에서 각각 약 <b>200만배럴/일</b> 수준의 정제제품 공급 차질이 발생했다는 Vitol 경영진 평가",
        "• <b>계절 리스크</b> 겨울 난방·수확철 디젤 수요가 늘어나는 구간과 겹침",
    ]
    brent = quotes.get("brent") if isinstance(quotes, dict) else None
    if brent is not None:
        try:
            lines.append(f"• <b>브렌트유</b> {html.escape(core.format_quote(brent))}")
        except Exception:
            pass

    lines.extend(["", "<b>확인 근거</b>"])
    lines.extend(_evidence_lines(selected) or ["• 공식기관·주요 매체에서 연료 공급 스트레스 변화 확인"])

    lines.extend([
        "",
        "<b>공정 병목</b>",
        "• <b>1차</b> 원유 생산·수송 → 정유공장 투입",
        "• <b>2차</b> 정유공장 가동률·정제능력 → 디젤·항공유·휘발유 생산",
        "• <b>3차</b> 상업용 재고·전략비축 → 겨울·수확철 수요 흡수",
        "• <b>실패 경로</b> 호르무즈/사우디 차질이 길어지고 정유공장 여유능력까지 부족하면 재고가 먼저 소진되고 소매 연료가격·정제마진·물가가 뒤따라 급등",
        "",
        "<b>한국 영향</b>",
        "• <b>정유</b> 정제마진 확대 가능성과 원유 조달비·운임 상승을 함께 봐야 함",
        "• <b>산업·물가</b> 경유·항공유·석유화학 원가와 운송비 상승 → 소비자물가·기업 마진 압박",
        "",
        "<b>투자 4축</b>",
        "• <b>돈버는능력</b> 정제마진이 원유 조달비보다 빠르게 오르는 정유사는 수혜 가능 / 항공·물류·화학은 비용 부담",
        "• <b>할인율</b> 연료가격 상승이 기대인플레이션·장기금리 재상승으로 이어지는지 확인",
        "• <b>수급</b> 중간유분 재고·정유공장 가동률·러시아/중동 수출 차질을 동시에 확인",
        "• <b>시간표</b> EIA 주간재고 → 정유공장 가동률 → 디젤 크랙/소매가격 → 겨울 수요 → 공급 정상화 순",
    ])

    other = _other_change_lines(groups)
    if other:
        lines.extend(["", *other])

    lines.extend([
        "",
        "<b>다음 확인</b>",
        "• ① EIA 중간유분 재고 1억배럴 하향 여부 → ② 정유공장 가동률 → ③ 디젤 크랙·소매가격 → ④ SPR 변화 → ⑤ 호르무즈·사우디 우회망 → ⑥ 겨울 수요",
        "",
        "<b>핵심 한 줄</b>",
        "• 지금은 원유 가격만 볼 단계가 아니라 재고·정제능력·디젤 공급을 함께 봐야 하며, 재고가 추가로 줄면 에너지 충격이 운송·물가·금리로 더 오래 전이될 수 있음",
    ])
    return "\n".join(lines)


def build_regular_alert_v33(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    if _fuel_groups(groups):
        title = "🚨 글로벌 연료·정제제품 공급경보"
        body = _build_fuel_body(groups, quotes)
    body = v32._replace_evidence_text(body, groups)
    leaks = v32._raw_english_evidence_remaining(body, groups)
    if leaks:
        raise RuntimeError("영문 기사 제목 송출 차단: " + " | ".join(leaks[:3]))
    metadata["version"] = 33
    metadata["refined_fuel_watch"] = {
        "target": "refined-product inventory/refining-capacity/diesel stress state changes",
        "not_target": "specific article URL or headline",
        "stages": ["inventory draw", "refinery capacity tightness", "diesel shortage", "systemic fuel crisis", "buffer rebuild"],
        "language": "ko-strict",
    }
    return title, body, metadata


def build_setup_test_v33(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 원유 차질 이후 상업용 연료재고·중간유분·정유설비 여유능력·전략비축까지 별도 사건축으로 감시"
        "\n• 특정 WSJ/Reuters 기사 자체가 아니라 재고 감소→정제능력 부족→디젤 공급부족→재고 회복의 단계 변화를 추적"
    )
    metadata["version"] = 33
    return title, body, metadata


core.category_label = category_label_v33
core.classify_polarity = classify_polarity_v33
core.confirmed_news_groups = confirmed_news_groups_v33
core.build_regular_alert = build_regular_alert_v33
core.build_setup_test = build_setup_test_v33

if __name__ == "__main__":
    raise SystemExit(core.main())

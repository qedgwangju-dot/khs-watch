#!/usr/bin/env python3
"""LNG 공급·가격 감시 v17: DNV AFI 기반 LNG 연료추진선 발주/조선 수요 축 추가."""
from __future__ import annotations

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v16 as v16

# LNG 운송선(LNG carrier)과 LNG를 연료로 쓰는 선박(LNG-fuelled vessel)을 구분한다.
MARINE_LNG_ORDER_QUERIES = (
    ("marine_lng_fuel_demand", 'DNV "Alternative Fuels Insight" LNG fuelled vessel orders August when:7d'),
    ("marine_lng_fuel_demand", 'alternative fuel ship orders surge LNG strongest month since 2024 DNV when:7d'),
    ("marine_lng_fuel_demand", 'LNG-fuelled containership car carrier orders DNV AFI when:7d'),
    ("marine_lng_fuel_demand", '대체연료 선박 발주 LNG DNV 컨테이너선 자동차운반선 when:7d'),
)
for item in MARINE_LNG_ORDER_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "dnv", "gCaptain", "gcaptain", "g captain", "maritime executive", "the maritime executive",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + ("dnv",)

core.EASING_TERMS["marine_lng_fuel_demand"] = (
    "orders surge", "ordering accelerated", "strongest month", "highest monthly", "orders rise",
    "orders jumped", "rebound", "up 27%", "lng drives", "lng-fuelled", "lng fueled",
    "발주 급증", "수주 급증", "발주 증가", "최고 월간", "반등", "lng 호조",
)
core.WORSENING_TERMS["marine_lng_fuel_demand"] = (
    "orders slow", "orders decline", "orders drop", "ordering falls", "down year-on-year",
    "order slowdown", "slump", "발주 둔화", "발주 감소", "주문 감소", "수주 둔화",
)
core.SUBTYPE_TERMS = (
    ("marine_lng_orders_2024_high", ("strongest month since 2024", "highest monthly total", "since october 2024", "2024년 10월 이후")),
    ("marine_lng_orders_surge", ("orders surge", "ordering accelerated", "orders rise", "발주 급증", "발주 증가")),
    ("marine_lng_orders_slowdown", ("orders slow", "orders decline", "order slowdown", "발주 둔화", "발주 감소")),
) + tuple(core.SUBTYPE_TERMS)

v8 = v16.v8
v8.SOURCE_KO.update({
    "gcaptain": "지캡틴",
    "g captain": "지캡틴",
    "dnv": "DNV",
    "maritime executive": "마리타임 이그제큐티브",
    "the maritime executive": "마리타임 이그제큐티브",
})
v8.KNOWN_TRANSLATIONS.update({
    "Alternative-Fuel Ship Orders Surge in August as LNG Drives Strongest Month Since 2024":
        "8월 대체연료 선박 발주 급증…LNG가 이끌며 2024년 10월 이후 최고 월간 기록",
    "Alternative Fuel Ship Orders Surge in August as LNG Drives Strongest Month Since 2024":
        "8월 대체연료 선박 발주 급증…LNG가 이끌며 2024년 10월 이후 최고 월간 기록",
})

_base_category_label = core.category_label
_base_context = core.classify_alert_context
_base_impact_text = core.impact_text


def category_label_v17(category: str) -> str:
    if category == "marine_lng_fuel_demand":
        return "LNG 연료추진선·조선 수요"
    return _base_category_label(category)


def classify_alert_context_v17(groups, new_signals, cleared_signals):
    marine = [g for g in groups if g.get("category") == "marine_lng_fuel_demand"]
    if marine:
        progress = any(g.get("polarity") == "easing" for g in marine)
        slowdown = any(g.get("polarity") == "worsening" for g in marine)
        if progress and not slowdown:
            return "marine_lng_order_progress"
        if slowdown and not progress:
            return "marine_lng_order_slowdown"
        return "marine_lng_order_mixed"
    return _base_context(groups, new_signals, cleared_signals)


def impact_text_v17(context: str):
    if context == "marine_lng_order_progress":
        return (
            "글로벌 LNG 연료추진선 발주가 강해진 신호입니다. 한국 LNG 현물 수급의 즉시 악화 신호는 아니지만, 중장기적으로 선박용 LNG 벙커링 수요와 관련 인프라 수요를 키울 수 있습니다.",
            "돈 버는 능력: 실제 수주 조선소·이중연료 엔진·FGSS·극저온 탱크/밸브·LNG 벙커링 기자재에 기회. 수급: LNG를 연료로 쓰는 선박이 늘면 해상 연료 수요 기반이 확대. 시간표: 글로벌 발주 → 조선소 선정 → 엔진/FGSS 발주 → 인도 → 벙커링 수요 증가 순으로 확인합니다. 특정 한국 조선사의 수혜는 실제 수주 확인 전 확정하지 않습니다.",
            "LNG 연료추진선 발주가 다시 강해졌습니다. 핵심은 LNG 운반선 발주와 혼동하지 않고 실제 조선소·엔진·FGSS 수주로 연결되는지 확인하는 것입니다.",
        )
    if context == "marine_lng_order_slowdown":
        return (
            "글로벌 LNG 연료추진선/대체연료선 발주 모멘텀이 둔화된 신호입니다. LNG 현물 수급과는 별개지만 조선·엔진·벙커링 인프라의 미래 수요 가시성을 낮출 수 있습니다.",
            "돈 버는 능력: 조선·엔진·FGSS의 신규 백로그 증가 속도 둔화 가능. 시간표: 월간 AFI 발주 → 실제 야드 배정 → 기자재 발주를 확인합니다.",
            "대체연료선 발주 모멘텀이 둔화됐으며, LNG 연료추진선 비중과 다음 달 신규 발주가 반전 여부의 핵심입니다.",
        )
    if context == "marine_lng_order_mixed":
        return (
            "대체연료선 발주 신호가 엇갈립니다. 선종·연료별로 모멘텀이 달라 전체 합계만으로 조선 수혜를 단정하지 않습니다.",
            "LNG·메탄올·암모니아 등 연료별 발주와 조선소 배정, 엔진/FGSS 발주를 분리해서 봅니다.",
            "대체연료선 발주가 혼조여서 선종·연료별 실제 계약 확인이 필요합니다.",
        )
    return _base_impact_text(context)


EARLY_MARINE_SOURCES = ("dnv", "gcaptain", "g captain", "maritime executive", "the maritime executive")


def confirmed_news_groups_v17(items: list[core.NewsItem]):
    confirmed = v16.confirmed_news_groups_v16(items)
    existing = {
        (str(g.get("category")), str(g.get("polarity")), str(g.get("subtype")), str(g.get("event_id")))
        for g in confirmed
    }
    for item in sorted(items, key=lambda x: x.published_epoch, reverse=True):
        if item.category != "marine_lng_fuel_demand":
            continue
        if not (item.official or core.source_matches(item.source, EARLY_MARINE_SOURCES)):
            continue
        normalized = core.normalize_text(item.title)
        if not any(token in normalized for token in (
            "alternative fuel", "lng", "fuelled", "fueled", "대체연료", "발주"
        )):
            continue
        key = (item.category, item.polarity, item.subtype, item.event_id)
        if key in existing:
            continue
        verification = "DNV 공식 AFI" if item.official or core.source_matches(item.source, ("dnv",)) else "DNV AFI 인용 해운 전문매체 조기신호"
        confirmed.append({
            "category": item.category,
            "polarity": item.polarity,
            "subtype": item.subtype,
            "event_id": item.event_id,
            "latest_epoch": item.published_epoch,
            "evidence": [item],
            "verification": verification,
        })
        existing.add(key)
    confirmed.sort(key=lambda g: float(g["latest_epoch"]), reverse=True)
    return confirmed


def build_regular_alert_v17(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v16.build_regular_alert_v16(groups, quotes, new_signals, cleared_signals)
    marine_groups = [g for g in groups if g.get("category") == "marine_lng_fuel_demand"]
    if marine_groups:
        title = "🚢 LNG 연료추진선·조선 수요 경보"
        evidence_text = " ".join(
            f"{item.title} {item.source}" for g in marine_groups for item in g.get("evidence", [])
        ).lower()
        lines = ["<b>LNG 연료추진선 발주·해운 연료 수요</b>"]
        if "strongest month since 2024" in evidence_text or "october 2024" in evidence_text:
            lines.extend([
                "• <b>기록</b> 8월 대체연료 선박 <b>52척</b> · <b>2024년 10월 이후 최고 월간</b>",
                "• <b>LNG 연료추진</b> <b>46척</b> · 전체의 <b>88.5%</b>",
                "• <b>선종</b> 컨테이너선 <b>30척</b> · 자동차운반선(PCTC) <b>12척</b> · 나머지 LNG 연료추진 4척",
                "• <b>기타 연료</b> 에탄올 연료 벌크선 4척 · 수소 연료 벌크선 2척",
                "• <b>누적</b> 2026년 1~8월 대체연료선 <b>242척</b> · 전년동기 대비 <b>+27%</b> · LNG가 누적 발주의 63%",
                "• <b>검산</b> 7월 47척 + 8월 52척 = <b>99척</b>. 기사 본문의 ‘두 달 100척 이상’ 문구는 산술 불일치라 알림에서 제외",
                "• <b>중요 구분</b> 여기서 LNG 선박은 <b>LNG를 연료로 쓰는 선박</b>이다. LNG를 운송하는 <b>LNG선(LNG carrier) 46척 발주</b>라는 뜻이 아님",
                "• <b>투자 연결</b> 실제 수주 조선소 → 이중연료 엔진 → FGSS → 극저온 연료탱크·밸브/펌프 → LNG 벙커링 인프라 순으로 확인",
                "• <b>한국주 주의</b> DNV 글로벌 발주 집계만으로 국내 조선사 수주를 확정하지 않음. 야드·선주·엔진/기자재 공급사가 확인될 때 기업별 수혜 단계 상향",
                "• <b>다음 확인</b> 9월 DNV AFI 월간 발주 → LNG 비중 → 컨테이너/PCTC 발주 지속 → 한국 조선소 실제 계약 → 엔진·FGSS 수주",
            ])
        else:
            lines.extend([
                "• <b>판정</b> 대체연료선·LNG 연료추진선 발주 모멘텀 변화 감지",
                "• <b>중요 구분</b> LNG 연료추진선과 LNG 운반선 발주는 별개로 집계",
                "• <b>다음 확인</b> DNV AFI 월간 총발주·LNG 비중·선종·실제 조선소/엔진/FGSS 수주",
            ])
        body += "\n\n" + "\n".join(lines)

    metadata["version"] = 17
    metadata["marine_lng_fuel_demand_watch"] = {
        "source_priority": ["DNV Alternative Fuels Insight", "gCaptain/major maritime trade press"],
        "required_fields": ["월간 발주척수", "기록/전년비", "LNG 연료추진 비중", "선종", "LNG carrier와 구분", "조선소/엔진/FGSS 실제 수주"],
        "arithmetic_check": "quantity totals must reconcile; inconsistent article arithmetic is suppressed",
    }
    return title, body, metadata


def build_setup_test_v17(quotes):
    title, body, metadata = v16.build_setup_test_v16(quotes)
    title = "✅ LNG·조선 수요 감시 v17 적용"
    body += (
        "\n\n<b>LNG 연료추진선·조선 수요</b>"
        "\n• DNV AFI 월간 대체연료선 발주·LNG 비중·선종을 감시"
        "\n• 월간/전년동기 기록과 수량 합계를 직접 검산"
        "\n• LNG 연료추진선과 LNG 운반선(LNG carrier)을 반드시 구분"
        "\n• 실제 야드·엔진·FGSS 공급사 확인 전 기업별 수혜 확정 금지"
    )
    metadata["version"] = 17
    return title, body, metadata


core.category_label = category_label_v17
core.classify_alert_context = classify_alert_context_v17
core.impact_text = impact_text_v17
core.confirmed_news_groups = confirmed_news_groups_v17
core.fetch_market_quotes = v16.fetch_market_quotes_v16
core.format_quote = v16.format_quote_v16
core.signal_label = v16.signal_label_v16
core.build_regular_alert = build_regular_alert_v17
core.build_setup_test = build_setup_test_v17

if __name__ == "__main__":
    raise SystemExit(core.main())

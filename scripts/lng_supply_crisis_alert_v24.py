#!/usr/bin/env python3
"""LNG 공급·가격 감시 v24: 한국 LNG 화물창 국산화·대형선 실증·상용화 단계 감시 추가."""
from __future__ import annotations

import hashlib

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v23 as v23

# LNG 화물창은 단순 조선 뉴스가 아니라 LNG 수송 기술주권·기자재 국산화·로열티 절감과
# 국적 LNG선 발주/실증으로 연결되는 투자 촉매이므로 별도 축으로 감시한다.
LNG_CARGO_TANK_QUERIES = (
    ("korea_supply", '한국 LNG 화물창 국산화 KC-2 가스공사 정부 대형선 실증 when:7d'),
    ("korea_supply", 'LNG 화물창 국산화 국적선 발주 KC-2 HD현대중공업 삼성중공업 한화오션 when:7d'),
    ("korea_supply", 'Korea LNG cargo containment KC-2 commercialization KOGAS when:7d'),
    ("korea_supply", 'Korea LNG cargo tank GTT royalty localization ship order when:7d'),
    ("korea_supply", 'LNG 화물창 GTT 기술료 국산화 실증선 발주 when:14d'),
    ("korea_supply", 'KC-2 한국선급 선급 승인 LNG 화물창 실증 when:14d'),
)
for item in LNG_CARGO_TANK_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "한국경제", "hankyung", "korea economic daily", "산업통상부", "산업통상자원부",
    "해양수산부", "한국가스공사", "kogas", "한국선급", "korean register",
)

core.WORSENING_TERMS["korea_supply"] = tuple(core.WORSENING_TERMS["korea_supply"]) + (
    "화물창 결함", "콜드스폿", "cold spot", "실증 지연", "국산화 실패", "배상",
    "소송", "운항 중단", "대형선 실증 실패",
)
core.EASING_TERMS["korea_supply"] = tuple(core.EASING_TERMS["korea_supply"]) + (
    "화물창 국산화", "kc-2", "대형선 실증", "실증방안 확정", "국적선 발주",
    "실증선 발주", "상용화", "형식승인", "설계승인", "기술인증", "기술료 절감",
    "cargo containment", "localization", "commercialization",
)

# 실제 상용화 단계가 높은 신호부터 먼저 분류한다.
core.SUBTYPE_TERMS = (
    ("lng_cargo_tank_commercial_order", (
        "국적선 발주", "실증선 발주", "commercial order", "first commercial order",
    )),
    ("lng_cargo_tank_certification", (
        "형식승인", "설계승인", "기술인증", "선급 승인", "type approval", "design approval", "certification",
    )),
    ("lng_cargo_tank_large_demo", (
        "대형선 실증", "대형 lng", "17만 4000", "174,000", "large-scale demonstration", "large lng carrier",
    )),
    ("lng_cargo_tank_localization", (
        "lng 화물창 국산화", "화물창 국산화", "kc-2", "cargo containment localization",
        "korean cargo containment", "gtt royalty", "기술료 절감",
    )),
) + tuple(core.SUBTYPE_TERMS)

_BASE_CONFIRMED = core.confirmed_news_groups
_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

CARGO_TANK_MAJOR_SOURCES = (
    "reuters", "bloomberg", "financial times", "연합뉴스", "yonhap", "한국경제", "hankyung",
    "산업통상부", "산업통상자원부", "해양수산부", "한국가스공사", "kogas",
)

CARGO_TANK_SUBTYPES = {
    "lng_cargo_tank_localization",
    "lng_cargo_tank_large_demo",
    "lng_cargo_tank_certification",
    "lng_cargo_tank_commercial_order",
}


def _cargo_tank_event_id(subtype: str, published_epoch: float) -> str:
    # 같은 단계의 반복 보도를 일주일 단위로 묶고, 단계 상승은 별도 사건으로 살린다.
    bucket = int(published_epoch // (7 * 24 * 3600))
    basis = f"lng_cargo_tank|{subtype}|{bucket}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def confirmed_news_groups_v24(items: list[core.NewsItem]):
    confirmed = list(_BASE_CONFIRMED(items))
    existing = {str(g.get("event_id")) for g in confirmed}

    for item in sorted(items, key=lambda x: x.published_epoch, reverse=True):
        if item.category != "korea_supply" or item.subtype not in CARGO_TANK_SUBTYPES:
            continue
        if not (item.official or core.source_matches(item.source, CARGO_TANK_MAJOR_SOURCES)):
            continue
        event_id = _cargo_tank_event_id(item.subtype, item.published_epoch)
        if event_id in existing:
            continue
        confirmed.append({
            "category": "korea_supply",
            "polarity": item.polarity,
            "subtype": item.subtype,
            "event_id": event_id,
            "latest_epoch": item.published_epoch,
            "evidence": [item],
            "verification": "LNG 화물창 국산화·실증 단계 조기신호 · 주요 매체/공식 원천 확인",
        })
        existing.add(event_id)

    confirmed.sort(key=lambda g: float(g.get("latest_epoch") or 0), reverse=True)
    return confirmed


def _cargo_tank_stage(subtype: str) -> tuple[str, int]:
    if subtype == "lng_cargo_tank_commercial_order":
        return "국적선/실증선 실제 발주", 4
    if subtype == "lng_cargo_tank_certification":
        return "형식·설계·선급 인증", 3
    if subtype == "lng_cargo_tank_large_demo":
        return "대형 LNG선 실증", 2
    return "정부·가스공사 국산화 추진", 1


def _cargo_tank_section(groups) -> list[str]:
    selected = [g for g in groups if str(g.get("subtype")) in CARGO_TANK_SUBTYPES]
    if not selected:
        return []
    best = max(selected, key=lambda g: _cargo_tank_stage(str(g.get("subtype")))[1])
    stage_name, stage_no = _cargo_tank_stage(str(best.get("subtype")))
    return [
        "<b>한국 LNG 화물창 국산화·상용화</b>",
        f"• <b>현재 단계</b> {stage_name} · <b>{stage_no}/4</b>",
        "• <b>기술 기준선</b> KC-2는 소형 LNG 벙커링선 적용으로 기본 안전성 검증을 거쳤지만, 대형 LNG 운반선 상용 실적은 별도 확인이 필요",
        "• <b>정책 기준선</b> 정부·가스공사·조선업계가 대형선 최종 실증, 신규 국적선 발주, 비용·기술리스크 분담을 검토해 온 사안",
        "• <b>왜 중요한가</b> LNG 화물창은 영하 163℃ LNG를 저장하는 핵심 기자재로, 국산화 성공 시 해외 기술 의존·기술료 부담을 낮추고 조선 기자재 부가가치를 국내에 남길 수 있음",
        "• <b>직접 확인 대상</b> 한국가스공사·KC LNG Tech·국내 조선 3사(HD현대·한화오션·삼성중공업)·국적선사·한국선급/해외 선급",
        "• <b>주의</b> 정부 재추진/워킹그룹 ≠ 대형선 실증 성공 ≠ 상용 발주. 실제 발주·인증·운항 실적이 나올 때마다 단계 상향",
        "• <b>투자 연결</b> 조선사 원가·로열티 구조 개선 가능성 → 멤브레인·보냉재·극저온 기자재 국산 공급망 확대 여부 확인",
        "• <b>다음 확인</b> 실증 방식 확정 → 대상 선박/조선소 선정 → 예산·리스크 분담 → 선급 승인 → 실제 발주 → 시운전·운항 → 상용 수주",
    ]


def build_regular_alert_v24(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    lines = _cargo_tank_section(groups)
    if lines:
        title = "⚓ 한국 LNG 화물창 국산화·실증 촉매"
        body += "\n\n" + "\n".join(lines)
    metadata["version"] = 24
    metadata["lng_cargo_tank_watch"] = {
        "stages": [
            "정부·가스공사 국산화 추진",
            "대형 LNG선 실증",
            "형식·설계·선급 인증",
            "국적선/실증선 실제 발주",
        ],
        "rule": "policy/demo/certification/order are distinct milestones; never label policy discussion as commercial order",
        "dedupe": "same stage grouped in a weekly bucket; stage upgrades alert separately",
    }
    return title, body, metadata


def build_setup_test_v24(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    title = "✅ LNG 화물창 국산화·실증 감시 v24 적용"
    body += (
        "\n\n<b>LNG 화물창 국산화</b>"
        "\n• 정부·가스공사 재추진 → 대형선 실증 → 인증 → 실제 국적선/실증선 발주를 단계별로 분리 감시"
        "\n• KC-2 소형선 적용과 대형 LNG선 상용화는 구분"
        "\n• 정부 검토를 실제 수주로 과장하지 않고, 실증·인증·발주가 나올 때만 단계 상향"
    )
    metadata["version"] = 24
    return title, body, metadata


core.confirmed_news_groups = confirmed_news_groups_v24
core.build_regular_alert = build_regular_alert_v24
core.build_setup_test = build_setup_test_v24

if __name__ == "__main__":
    raise SystemExit(core.main())

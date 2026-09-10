#!/usr/bin/env python3
"""LNG 공급·가격 감시 v23: TTF 장중 임계값 돌파(80/90/100유로) 이력 경보 추가."""
from __future__ import annotations

import datetime as dt
import hashlib

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v22 as v22

# 현재가가 임계값 아래로 되돌아온 경우에도 '장중 돌파' 자체를 놓치지 않도록
# 주요 매체의 장중 고가/돌파 보도를 별도 사건으로 감시한다.
TTF_INTRADAY_QUERIES = (
    ("europe_storage", 'Dutch TTF gas 80 euros MWh intraday high when:3d'),
    ("europe_storage", 'European gas TTF above 80 euros MWh highest since 2023 when:3d'),
    ("europe_storage", 'Dutch TTF gas 90 euros MWh intraday when:3d'),
    ("europe_storage", 'Dutch TTF gas 100 euros MWh winter when:7d'),
    ("europe_storage", '유럽 천연가스 TTF 80유로 돌파 장중 최고 when:3d'),
    ("europe_storage", '유럽 천연가스 TTF 90유로 100유로 돌파 when:7d'),
)
for item in TTF_INTRADAY_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "euronews", "sbs", "yonhap", "연합뉴스",
)

core.WORSENING_TERMS["europe_storage"] = tuple(core.WORSENING_TERMS["europe_storage"]) + (
    "above 80 euros", "over 80 euros", "surpass 80 euros", "surpasses 80 euros",
    "80 euros per megawatt-hour", "80 euro per megawatt-hour", "€80/mwh", "€80",
    "above 90 euros", "over 90 euros", "€90/mwh", "€90",
    "above 100 euros", "over 100 euros", "€100/mwh", "€100",
    "highest since january 2023", "highest since early 2023",
    "80유로 돌파", "80유로 상회", "90유로 돌파", "100유로 돌파", "3년여만",
)

# 숫자가 큰 임계값부터 분류해 100유로 보도가 80유로 subtype으로 먼저 잡히지 않게 한다.
core.SUBTYPE_TERMS = (
    ("ttf_intraday_100", (
        "above 100 euros", "over 100 euros", "100 euros per megawatt-hour", "€100/mwh", "€100", "100유로 돌파", "100유로 상회",
    )),
    ("ttf_intraday_90", (
        "above 90 euros", "over 90 euros", "90 euros per megawatt-hour", "€90/mwh", "€90", "90유로 돌파", "90유로 상회",
    )),
    ("ttf_intraday_80", (
        "above 80 euros", "over 80 euros", "surpass 80 euros", "surpasses 80 euros",
        "80 euros per megawatt-hour", "80 euro per megawatt-hour", "€80/mwh", "€80",
        "80유로 돌파", "80유로 상회", "3년여만",
    )),
) + tuple(core.SUBTYPE_TERMS)

_BASE_CONFIRMED = core.confirmed_news_groups
_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

INTRADAY_MAJOR_SOURCES = (
    "reuters", "bloomberg", "financial times", "wall street journal", "wsj",
    "associated press", "ap news", "euronews", "연합뉴스", "yonhap", "sbs",
)


def _threshold_from_subtype(subtype: str) -> int | None:
    if subtype == "ttf_intraday_80":
        return 80
    if subtype == "ttf_intraday_90":
        return 90
    if subtype == "ttf_intraday_100":
        return 100
    return None


def _milestone_event_id(threshold: int, published_epoch: float) -> str:
    # 장중 순간 돌파 뉴스가 여러 매체에서 반복돼도 월 1회 milestone으로 묶는다.
    published = dt.datetime.fromtimestamp(published_epoch, tz=dt.timezone.utc)
    basis = f"ttf_intraday_milestone|{threshold}|{published:%Y-%m}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def confirmed_news_groups_v23(items: list[core.NewsItem]):
    confirmed = list(_BASE_CONFIRMED(items))
    existing = {str(group.get("event_id")) for group in confirmed}

    for item in sorted(items, key=lambda x: x.published_epoch, reverse=True):
        threshold = _threshold_from_subtype(item.subtype)
        if threshold is None:
            continue
        if not (item.official or core.source_matches(item.source, INTRADAY_MAJOR_SOURCES)):
            continue
        milestone_id = _milestone_event_id(threshold, item.published_epoch)
        if milestone_id in existing:
            continue
        confirmed.append({
            "category": "europe_storage",
            "polarity": "worsening",
            "subtype": item.subtype,
            "event_id": milestone_id,
            "latest_epoch": item.published_epoch,
            "evidence": [item],
            "verification": f"TTF 장중 {threshold}유로/MWh 돌파 · 주요 금융/통신 매체 확인",
        })
        existing.add(milestone_id)

    confirmed.sort(key=lambda g: float(g.get("latest_epoch") or 0), reverse=True)
    return confirmed


def _ttf_intraday_section(groups, quotes) -> list[str]:
    thresholds = sorted({
        t for g in groups
        for t in [_threshold_from_subtype(str(g.get("subtype") or ""))]
        if t is not None
    })
    if not thresholds:
        return []

    lines = ["<b>TTF 장중 임계값 돌파</b>"]
    ttf = quotes.get("ttf")
    for threshold in thresholds:
        if ttf is not None:
            current = float(ttf.price)
            if current >= threshold:
                status = "장중 돌파 후 현재 공개값도 임계값 위 유지"
            else:
                status = "장중 돌파는 확인됐지만 현재 공개값은 재하회 · 돌파 이력은 유지"
            lines.append(
                f"• <b>{threshold}유로/MWh</b> 장중 돌파 · {status} · 현재 {core.format_quote(ttf)}"
            )
        else:
            lines.append(
                f"• <b>{threshold}유로/MWh</b> 장중 돌파 · 현재 TTF 공개값 검증 실패로 현재/종가 비교 보류"
            )

    lines.extend([
        "• <b>구분</b> 장중 고가 ≠ 현재가/종가. 기사에 나온 장중 최고치를 현재가격처럼 재사용하지 않음",
        "• <b>경보 단계</b> 80유로=겨울 스트레스 현실화 · 90유로=유럽의 LNG 카고 유치 경쟁 심화 · 100유로=강한 수요파괴/산업비용 압박 구간",
        "• <b>연결 판정</b> TTF 임계값 돌파와 EU 저장률 70% 미만·카타르/호르무즈·JKM 상승이 겹치면 글로벌 LNG 수급 스트레스로 단계 상향",
        "• <b>금리 연결</b> TTF 80/90/100 → 유로존 단기 인플레이션 기대 → ECB 경로 → 독일 2Y·10Y·30Y를 순서대로 확인",
        "• <b>다음 확인</b> TTF 장중 고가/종가 → GIE 저장률·주입속도 → JKM·유럽-아시아 가격차 → 카타르 실제 선적 → ECB 재가격",
    ])
    return lines


def build_regular_alert_v23(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    lines = _ttf_intraday_section(groups, quotes)
    if lines:
        title = "⚠️ 유럽 TTF·LNG 겨울 스트레스 경보"
        body += "\n\n" + "\n".join(lines)
    metadata["version"] = 23
    metadata["ttf_intraday_watch"] = {
        "thresholds_eur_mwh": [80, 90, 100],
        "rule": "intraday threshold news is a distinct milestone from current/close price state",
        "dedupe": "one milestone per threshold per calendar month; current-price hysteresis still handles re-entry",
        "source_rule": "major wire/financial outlet or official source; current TTF quote shown separately",
    }
    return title, body, metadata


def build_setup_test_v23(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    title = "✅ LNG·TTF 장중 임계값 감시 v23 적용"
    body += (
        "\n\n<b>TTF 장중 임계값</b>"
        "\n• 80·90·100유로/MWh 장중 돌파를 현재가 임계값과 별도 사건으로 기록"
        "\n• 장중 돌파 후 79유로대로 되돌아와도 80유로 돌파 이력을 놓치지 않음"
        "\n• 장중 고가와 현재/종가를 반드시 분리 표기"
        "\n• 동일 임계값의 반복 기사 중복은 월간 milestone으로 묶고 현재가 재진입은 기존 히스테리시스로 감시"
    )
    metadata["version"] = 23
    return title, body, metadata


core.confirmed_news_groups = confirmed_news_groups_v23
core.build_regular_alert = build_regular_alert_v23
core.build_setup_test = build_setup_test_v23

if __name__ == "__main__":
    raise SystemExit(core.main())

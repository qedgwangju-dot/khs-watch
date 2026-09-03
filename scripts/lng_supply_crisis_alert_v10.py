#!/usr/bin/env python3
"""LNG 공급·전략 촉매 감시 v10.

v9 규칙에 한국 뉴스 조기탐지 경로를 추가한다.
- 알래스카 LNG 관련 한국/일본 대통령·정부 발언은 한국 Google News RSS에서도 별도 검색한다.
- 연합뉴스/Reuters/Bloomberg/AP 같은 최상위 출처가 대통령의 직접 발언을 보도한 경우
  두 번째 매체를 기다리지 않고 '정책 발언 조기신호'로 경보한다.
- 실제 투자·오프테이크·FID·EPC는 기존대로 공식 원천 1곳 또는 신뢰 매체 2곳 기준을 유지한다.
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v9 as v9


EARLY_ALASKA_QUERIES = (
    '트럼프 한국 일본 알래스카 LNG when:3d',
    '"알래스카 LNG" 트럼프 한국 일본 when:3d',
    '"알래스카로 간다" 트럼프 한국 일본 when:3d',
    '"South Korea" Japan "Alaska LNG" Trump when:3d',
)

EARLY_POLICY_SOURCE_ALIASES = (
    "yonhap", "연합뉴스", "reuters", "로이터", "bloomberg", "블룸버그",
    "associated press", "ap news", "ap통신",
)

_original_fetch_news_item_set = core.fetch_news_item_set
_original_confirmed_news_groups = core.confirmed_news_groups


def _fetch_korea_alaska_items(max_age_hours: int = 84):
    cutoff = core.now_utc() - core.dt.timedelta(hours=max_age_hours)
    items: list[core.NewsItem] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()

    for query in EARLY_ALASKA_QUERIES:
        params = urllib.parse.urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        url = f"https://news.google.com/rss/search?{params}"
        try:
            root = ET.fromstring(core.fetch_bytes(url))
        except Exception as exc:
            errors.append(f"alaska_ko: {type(exc).__name__}")
            continue

        for node in root.findall(".//item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            source = (node.findtext("source") or "").strip()
            published = core.parse_date((node.findtext("pubDate") or "").strip())
            if not title or not link or not source or published is None or published < cutoff:
                continue
            if not core.source_matches(source, core.TRUSTED_SOURCE_ALIASES):
                continue
            polarity = core.classify_polarity("alaska_lng", title)
            if polarity is None:
                continue
            subtype = core.classify_subtype(title)
            key = (core.normalize_text(title), core.normalize_text(source))
            if key in seen:
                continue
            seen.add(key)
            items.append(
                core.NewsItem(
                    category="alaska_lng",
                    polarity=polarity,
                    subtype=subtype,
                    title=title,
                    source=source,
                    link=link,
                    published_utc=published.isoformat(timespec="seconds"),
                    published_epoch=published.timestamp(),
                    official=core.source_matches(source, core.OFFICIAL_SOURCE_ALIASES),
                    event_id=core.make_event_id("alaska_lng", polarity, subtype, published),
                )
            )

    items.sort(key=lambda item: item.published_epoch, reverse=True)
    return items, errors


def fetch_news_item_set_v10(max_age_hours: int = 84):
    base, errors = _original_fetch_news_item_set(max_age_hours=max_age_hours)
    alaska, alaska_errors = _fetch_korea_alaska_items(max_age_hours=max_age_hours)
    merged: list[core.NewsItem] = []
    seen: set[tuple[str, str, str]] = set()
    for item in base + alaska:
        key = (item.category, core.normalize_text(item.title), core.normalize_text(item.source))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    merged.sort(key=lambda item: item.published_epoch, reverse=True)
    return merged, errors + alaska_errors


def _is_early_policy_wire(item: core.NewsItem) -> bool:
    if item.category != "alaska_lng" or item.polarity != "easing":
        return False
    if item.subtype != "alaska_policy_signal":
        return False
    return core.source_matches(item.source, EARLY_POLICY_SOURCE_ALIASES)


def confirmed_news_groups_v10(items: list[core.NewsItem]):
    confirmed = _original_confirmed_news_groups(items)
    existing = {
        (str(group["category"]), str(group["polarity"]), str(group["subtype"]), str(group["event_id"]))
        for group in confirmed
    }

    # 대통령의 직접 정책 발언은 시장 개장 전에 의미가 있으므로 최상위 통신사 1곳이면 조기신호로 인정한다.
    # 단, 계약·오프테이크·FID·EPC는 이 예외를 적용하지 않는다.
    for item in sorted(items, key=lambda value: value.published_epoch, reverse=True):
        if not _is_early_policy_wire(item):
            continue
        key = (item.category, item.polarity, item.subtype, item.event_id)
        if key in existing:
            continue
        confirmed.append(
            {
                "category": item.category,
                "polarity": item.polarity,
                "subtype": item.subtype,
                "event_id": item.event_id,
                "latest_epoch": item.published_epoch,
                "evidence": [item],
                "verification": "정책 발언 조기신호·주요 통신사 1곳",
            }
        )
        existing.add(key)

    confirmed.sort(key=lambda group: float(group["latest_epoch"]), reverse=True)
    return confirmed


def build_setup_test_v10(quotes):
    title, body, metadata = v9.build_setup_test_v9(quotes)
    title = "✅ LNG·천연가스 감시 정확도 규칙 v10 적용"
    body += (
        "\n• 알래스카 LNG 대통령·정부 발언은 한국 뉴스 RSS도 병렬 감시"
        "\n• 연합뉴스·Reuters·Bloomberg·AP의 직접 발언 보도는 1곳만 확인돼도 '정책 발언 조기신호'로 경보"
        "\n• 실제 투자/MOU·오프테이크·SPA·FID·EPC는 공식 1곳 또는 신뢰 매체 2곳 기준 유지"
        "\n• 목표: 장 시작 전 정책 촉매를 먼저 포착하되 발언을 계약·수주로 과장하지 않음"
    )
    metadata["version"] = 10
    return title, body, metadata


core.fetch_news_item_set = fetch_news_item_set_v10
core.confirmed_news_groups = confirmed_news_groups_v10
core.category_label = v9.category_label_v9
core.classify_polarity = v9.classify_polarity_v9
core.classify_alert_context = v9.classify_alert_context_v9
core.impact_text = v9.impact_text_v9
core.fetch_market_quotes = v9.v8.v7.fetch_market_quotes_v7
core.format_quote = v9.v8.v7.v6.format_quote_v6
core.signal_label = v9.signal_label_v9
core.build_regular_alert = v9.build_regular_alert_v9
core.build_setup_test = build_setup_test_v10


if __name__ == "__main__":
    raise SystemExit(core.main())

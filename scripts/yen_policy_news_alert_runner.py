#!/usr/bin/env python3
"""Operational runner for yen policy-news alerts with major-source coverage."""

from __future__ import annotations

import sys

import yen_policy_news_alert as base

WSJ_MARKERS = (
    "wall street journal",
    "the wall street journal",
    "wsj",
    "wsj.com",
    "dow jones newswires",
)

FORECAST_MARKERS = (
    "has chance to",
    "could",
    "may",
    "might",
    "strategist",
    "analyst",
    "forecast",
    "forecasts",
    "expects",
    "expectation",
    "hsbc",
    "전망",
    "예상",
    "가능성",
)

_original_source_group = base.source_group
_original_classify = base.classify


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in markers)


def source_group(source: str, full_text: str) -> str:
    if _contains(f"{source} {full_text}", WSJ_MARKERS):
        return "Wall Street Journal"
    return _original_source_group(source, full_text)


def classify(item: base.NewsItem) -> base.ClassifiedItem | None:
    result = _original_classify(item)
    if result is None:
        return None
    if result.topic == "BOJ 9월 인상 기대·신호" and _contains(item.text, FORECAST_MARKERS):
        return base.ClassifiedItem(
            item=result.item,
            topic="BOJ 9월 인상 전망·시장 기대",
            material_score=result.material_score,
            source_level=result.source_level,
            source_group=result.source_group,
        )
    return result


def install() -> None:
    if not any("Wall Street Journal" in query for _lang, query in base.RSS_QUERIES):
        base.RSS_QUERIES = base.RSS_QUERIES + (
            ("en", '"Bank of Japan" September rate hike yen "Wall Street Journal"'),
            ("en", 'BOJ September rate hike support yen WSJ'),
        )
    for marker in WSJ_MARKERS:
        if marker not in base.MAJOR_SOURCE_MARKERS:
            base.MAJOR_SOURCE_MARKERS = base.MAJOR_SOURCE_MARKERS + (marker,)
    base.source_group = source_group
    base.classify = classify


install()


def main() -> int:
    return base.main()


if __name__ == "__main__":
    sys.exit(main())

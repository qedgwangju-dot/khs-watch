#!/usr/bin/env python3
"""Coverage extension for material yen-carry rebuild headlines.

Adds source and wording coverage that is intentionally narrow so a headline such as
"Japan's historic yen intervention has 'turbo-charged' the carry trade" is treated
as a material carry-rebuild catalyst without weakening the existing noise filters.
"""
from __future__ import annotations

import yen_carry_news_alert as base

EXTRA_RSS_QUERIES = (
    ("en", '"turbo-charged" "carry trade" yen intervention'),
    ("en", '"turbocharged" "carry trade" yen intervention'),
    ("en", 'CNBC yen intervention carry trade Japan investors overseas assets'),
    ("ko", '엔화 개입 캐리 트레이드 가속화 일본 투자자 해외 자산'),
)

EXTRA_REBUILD_MARKERS = (
    "turbo-charged",
    "turbocharged",
    "turbo charged",
    "supercharged",
    "accelerated the carry trade",
    "accelerates the carry trade",
    "캐리 트레이드 가속화",
    "캐리트레이드 가속화",
    "엔캐리 가속화",
    "캐리 트레이드 강화",
)

EXTRA_SOURCE_GROUPS = (
    (("cnbc", "씨엔비씨"), "CNBC"),
)


def _extend_unique(original: tuple, additions: tuple) -> tuple:
    rows = list(original)
    for item in additions:
        if item not in rows:
            rows.append(item)
    return tuple(rows)


def install() -> None:
    base.RSS_QUERIES = _extend_unique(base.RSS_QUERIES, EXTRA_RSS_QUERIES)
    base.REBUILD_MARKERS = _extend_unique(base.REBUILD_MARKERS, EXTRA_REBUILD_MARKERS)
    base.KOREAN_SOURCE_GROUPS = _extend_unique(base.KOREAN_SOURCE_GROUPS, EXTRA_SOURCE_GROUPS)


install()


def main() -> int:
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())

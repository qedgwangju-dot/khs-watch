#!/usr/bin/env python3
"""Execution wrapper for Treasury buyback watcher v2.

Keeps an always-present baseline Treasury signal so official schedule/results changes
can trigger an alert even when the related media reports have aged out of the 2-day RSS window.
"""
from __future__ import annotations

import treasury_buyback_media_watch_v2 as watcher

_original_news_items = watcher.news_items


def news_items_with_official_baseline() -> list[dict]:
    items = _original_news_items()
    items.append({
        "title": "Treasury official buyback execution baseline",
        "link": watcher.MARKETWATCH_TGA,
        "description": "Treasury general account TGA buyback official execution monitoring baseline",
        "source": "Treasury execution monitor",
        "pubDate": "",
    })
    return items


watcher.news_items = news_items_with_official_baseline

if __name__ == "__main__":
    raise SystemExit(watcher.main())

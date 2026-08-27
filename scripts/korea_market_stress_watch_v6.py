#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt

import korea_market_stress_watch_v5 as v5

watch = v5.watch
_original_google_news = watch.google_news


def google_news_fresh_only(query: str, limit: int = 12):
    """Keep monitoring search-based signals, but do not alert on stale back-catalog articles.

    BofA Global Wave is slower-moving, so allow 30 days.
    Hyperscaler AI capex guidance is event/news driven, so allow 7 days.
    """
    now = dt.datetime.now(watch.KST).astimezone(dt.timezone.utc)
    max_age = dt.timedelta(days=30 if "global wave" in query.lower() else 7)
    items = _original_google_news(query, limit)
    out = []
    for item in items:
        published = item.get("published_dt")
        if isinstance(published, dt.datetime):
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
            if published >= now - max_age:
                out.append(item)
    return out


watch.google_news = google_news_fresh_only

if __name__ == "__main__":
    raise SystemExit(watch.main())

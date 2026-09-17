#!/usr/bin/env python3
"""Guard layer for Figure AI first-party teaser freshness and dedupe.

Keeps the existing Figure AI lane, but prevents mirror-page context bleed from
attaching one teaser to multiple historical X status ids. A teaser is a schedule
event, not a post-id event: on each scan retain only the freshest first-party
Figure teaser, while the actual later reveal remains an independent event.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import physical_ai_watch_figure_entry as fig

base = fig.base
ext = fig.ext
_orig_query_news = base.query_news
_orig_key = base.key


def _published(item: dict) -> dt.datetime:
    try:
        value = dt.datetime.fromisoformat(item.get('published') or '')
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    except Exception:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _is_first_party_teaser(item: dict) -> bool:
    if not fig._is_figure_direct(item):
        return False
    text = f"{item.get('title','')} {item.get('description','')}"
    return bool(fig.FIGURE_PREANNOUNCE.search(text) and fig.FIGURE_BREAKTHROUGH.search(text))


def _fetch_figure_founder_guarded() -> list[dict]:
    items = fig._fetch_figure_founder_x()
    teasers = [x for x in items if _is_first_party_teaser(x)]
    if len(teasers) <= 1:
        return items

    # Mirror pages can place neighboring post text around multiple status links.
    # Keep the newest teaser only. Non-teaser posts are retained independently.
    newest = max(teasers, key=_published)
    return [x for x in items if not _is_first_party_teaser(x)] + [newest]


def query_news(q: str) -> list[dict]:
    if q == fig.FIGURE_X_SENTINEL:
        return _fetch_figure_founder_guarded()
    return _orig_query_news(q)


def key(item: dict) -> str:
    if _is_first_party_teaser(item):
        # Same-day Figure teaser rewrites/mirror copies represent one schedule
        # event. The actual reveal does not match PREANNOUNCE and gets a new key.
        day = base.NOW.astimezone(base.KST).strftime('%Y-%m-%d')
        return hashlib.sha256(f'figure-ai|first-party-teaser|{day}'.encode()).hexdigest()
    return _orig_key(item)


base.query_news = query_news
base.key = key


def _finalize_alert_text() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    text = text.replace(
        '신규 수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·수급·시간표를 바꾸는 내용만 알림.',
        '공식 사전예고·신규 AI 모델/성능 공개·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.'
    )
    base.ALERT_PATH.write_text(fig.legacy.display._inline_original_link(text), encoding='utf-8')


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    fig.legacy.repair_pending_seen(pre_state)
    _finalize_alert_text()

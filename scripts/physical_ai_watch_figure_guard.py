#!/usr/bin/env python3
"""Guard layer for Figure AI first-party teaser freshness and dedupe.

A Figure teaser is a schedule event, not a post-id event. Direct founder posts that
announce the same upcoming reveal must collapse to one semantic event even when:
- X exposes more than one teaser post;
- an older post is discovered several hours after a newer one;
- the same post is rediscovered on the following day while it is still inside the
  48-hour discovery window.

The later actual reveal remains an independent event.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

import physical_ai_watch_figure_entry as fig

base = fig.base
ext = fig.ext
_orig_query_news = base.query_news
_orig_key = base.key
_orig_load_state = base.load_state

# Two duplicate Figure teasers were already delivered on 2026-10-01 KST with
# post-id keys before semantic teaser dedupe was hardened. Keep these only as a
# migration anchor so the already-delivered event cannot fire a third time.
_LEGACY_FIGURE_TEASER_STATUS_IDS = (
    "2105322505934410007",
    "2105316680251650555",
)
_LEGACY_FIGURE_TEASER_KEYS = {
    hashlib.sha256(f"x:adcock_brett:{sid}".encode()).hexdigest()
    for sid in _LEGACY_FIGURE_TEASER_STATUS_IDS
}


def _published(item: dict) -> dt.datetime:
    try:
        value = dt.datetime.fromisoformat(item.get("published") or "")
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    except Exception:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _published_day_kst(item: dict) -> str:
    value = _published(item)
    if value == dt.datetime.min.replace(tzinfo=dt.timezone.utc):
        # Stable fallback: do not use scan time, which would create a new key
        # when an old teaser is rediscovered the next day.
        sid = str(item.get("x_status_id") or "")
        if sid:
            value = fig.legacy._tweet_time_from_id(sid) or value
    if value == dt.datetime.min.replace(tzinfo=dt.timezone.utc):
        return "unknown"
    return value.astimezone(base.KST).strftime("%Y-%m-%d")


def _teaser_signature(item: dict) -> str:
    """Separate explicitly different named reveals while collapsing generic teasers."""
    text = f"{item.get('title','')} {item.get('description','')}"
    signatures: list[str] = []
    patterns = [
        ("helix-2.5", r"\bHelix\s*2\.5\b"),
        ("helix", r"\bHelix\b"),
        ("figure-03", r"\bFigure\s*0?3\b|피겨\s*0?3"),
        ("figure-02", r"\bFigure\s*0?2\b|피겨\s*0?2"),
        ("index", r"\bIndex\b"),
        ("bmw", r"\bBMW\b"),
    ]
    for name, pat in patterns:
        if re.search(pat, text, re.I):
            signatures.append(name)
    return "+".join(signatures) if signatures else "generic"


def _is_first_party_teaser(item: dict) -> bool:
    if not fig._is_figure_direct(item):
        return False
    text = f"{item.get('title','')} {item.get('description','')}"
    # PREANNOUNCE alone is enough. The previous guard also required a
    # BREAKTHROUGH keyword, which allowed two generic teaser posts to bypass
    # semantic dedupe and alert separately.
    return bool(fig.FIGURE_PREANNOUNCE.search(text))


def _teaser_key(item: dict) -> str:
    day = _published_day_kst(item)
    sig = _teaser_signature(item)
    return hashlib.sha256(f"figure-ai|first-party-teaser|{day}|{sig}".encode()).hexdigest()


def _fetch_figure_founder_guarded() -> list[dict]:
    items = fig._fetch_figure_founder_x()
    # Collapse only the same semantic teaser event; retain genuinely different
    # named teasers and all non-teaser posts.
    newest_by_event: dict[str, dict] = {}
    other: list[dict] = []
    for item in items:
        if not _is_first_party_teaser(item):
            other.append(item)
            continue
        k = _teaser_key(item)
        prev = newest_by_event.get(k)
        if prev is None or _published(item) > _published(prev):
            newest_by_event[k] = item
    return other + list(newest_by_event.values())


def query_news(q: str) -> list[dict]:
    if q == fig.FIGURE_X_SENTINEL:
        return _fetch_figure_founder_guarded()
    return _orig_query_news(q)


def key(item: dict) -> str:
    if _is_first_party_teaser(item):
        return _teaser_key(item)
    return _orig_key(item)


def load_state() -> dict:
    state = _orig_load_state()
    seen = list(state.get("seen", []))
    seen_set = set(seen)
    if seen_set.intersection(_LEGACY_FIGURE_TEASER_KEYS):
        migrated = hashlib.sha256(
            b"figure-ai|first-party-teaser|2026-10-01|generic"
        ).hexdigest()
        if migrated not in seen_set:
            seen.append(migrated)
            seen_set.add(migrated)
        state["seen"] = seen[-3500:]
    return state


base.query_news = query_news
base.key = key
base.load_state = load_state


def _finalize_alert_text() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding="utf-8")
    text = text.replace(
        "신규 수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·수급·시간표를 바꾸는 내용만 알림.",
        "공식 사전예고·신규 AI 모델/성능 공개·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.",
    )
    base.ALERT_PATH.write_text(
        fig.legacy.display._inline_original_link(text), encoding="utf-8"
    )


if __name__ == "__main__":
    pre_state = base.load_state()
    base.main()
    fig.legacy.repair_pending_seen(pre_state)
    _finalize_alert_text()

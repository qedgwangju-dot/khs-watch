#!/usr/bin/env python3
"""Reliable independent FX monitor-health assessment.

Execution heartbeat freshness is not interchangeable with market-price freshness.
Only a fresh eligible observation (or an explicit FX-market closure) can clear an
active FX monitoring incident. No fabricated prices or success timestamps.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NEW_YORK = ZoneInfo("America/New_York")
MAX_FUTURE_SKEW_SECONDS = 120.0
MAX_AGE_SECONDS = 12 * 60


def parse_stamp(raw):
    if not raw:
        return None
    try:
        stamp = dt.datetime.fromisoformat(str(raw))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=KST)
        return stamp.astimezone(KST)
    except (TypeError, ValueError):
        return None


def fx_market_open(now: dt.datetime) -> bool:
    """Regular 24x5 retail FX week; exceptional public holidays may still close."""
    local = now.astimezone(NEW_YORK)
    weekday = local.weekday()
    return (weekday <= 3 or (weekday == 4 and local.hour < 17)
            or (weekday == 6 and local.hour >= 17))


def _eligible_record(record: dict, now: dt.datetime, source: str):
    if not isinstance(record, dict):
        return None
    stamp = parse_stamp(record.get("updated_at_kst"))
    if stamp is None:
        return None
    gap = (now - stamp).total_seconds()
    if gap < -MAX_FUTURE_SKEW_SECONDS:
        return None
    return (stamp, source, record)


def evaluate(payloads: list[tuple[str, dict]], now: dt.datetime) -> dict:
    now = now.astimezone(KST)
    records = [x for path, value in payloads if (x := _eligible_record(value, now, path)) is not None]
    records.sort(key=lambda x: x[0], reverse=True)
    market_open = fx_market_open(now)
    if not records:
        return {
            "source_path": None,
            "source_updated_at_kst": None,
            "effective_updated_at_kst": None,
            "stale_minutes": None,
            "execution_age_minutes": None,
            "price_age_minutes": None,
            "market_open": market_open,
            "fx_signal_eligible": False,
            "healthy": False,
            "issue_kind": "heartbeat_missing",
        }
    stamp, source, data = records[0]
    age_seconds = max(0., (now - stamp).total_seconds())
    raw_observed = parse_stamp(data.get("fx_observed_at_kst"))
    price_seconds = None if raw_observed is None else (now - raw_observed).total_seconds()
    if price_seconds is not None and price_seconds < -MAX_FUTURE_SKEW_SECONDS:
        price_seconds = None
        raw_observed = None
    declared_eligible = data.get("fx_signal_eligible") is True
    execution_healthy = age_seconds < 10 * 60
    price_healthy = (
        declared_eligible and price_seconds is not None
        and -MAX_FUTURE_SKEW_SECONDS <= price_seconds <= MAX_AGE_SECONDS
    )
    # During normal FX closure, successful recent polling is operationally healthy
    # but is NEVER falsely described as a fresh FX market quote.
    healthy = execution_healthy and (not market_open or price_healthy)
    if not execution_healthy:
        issue = "execution_stale"
        effective = stamp
        effective_age = age_seconds
    elif market_open and not price_healthy:
        issue = "market_data_unavailable"
        effective = raw_observed if raw_observed and raw_observed <= now else stamp
        effective_age = max(age_seconds, price_seconds if price_seconds is not None else age_seconds)
        # Missing or explicitly ineligible data is an issue even if run timestamps advance.
        if price_seconds is None:
            effective_age = max(effective_age, MAX_AGE_SECONDS)
    else:
        issue = None if market_open else "market_closed"
        effective = stamp
        effective_age = age_seconds
    return {
        "source_path": source,
        "source_updated_at_kst": stamp.isoformat(timespec="seconds"),
        "effective_updated_at_kst": effective.isoformat(timespec="seconds"),
        "stale_minutes": max(0., effective_age / 60.),
        "execution_age_minutes": age_seconds / 60.,
        "price_age_minutes": None if price_seconds is None else max(0., price_seconds / 60.),
        "market_open": market_open,
        "fx_signal_eligible": declared_eligible and price_healthy,
        "healthy": healthy,
        "issue_kind": issue,
    }


def transition(previous: dict, status: dict, *, outage_threshold_minutes: float = 45.) -> dict:
    age = status.get("stale_minutes")
    # Invalid data-source updates are not proof of monitoring recovery, even when
    # a new heartbeat file has been committed.
    outage = age is None or age >= outage_threshold_minutes
    if status.get("issue_kind") == "market_data_unavailable" and not status.get("healthy"):
        # The monitor might have just started failing. Do not misdeclare recovery
        # while a bad-price heartbeat is arriving.
        outage = outage or bool(previous.get("alert_active"))
    if not status.get("healthy") and bool(previous.get("alert_active")):
        outage = True
    was_active = bool(previous.get("alert_active"))
    return {
        "outage": outage,
        "new_outage": outage and not was_active,
        "recovered_incident": was_active and status.get("healthy") is True,
    }

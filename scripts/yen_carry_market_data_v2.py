#!/usr/bin/env python3
"""Accurate market-data reader for the yen-carry Telegram alert.

Cash indices use Yahoo's official regular-market close and immediately preceding
regular-market close when available. Five-minute candles are used only as a
fallback and for rolling USD/JPY calculations. If an exact 24-hour FX reference
is unavailable across a weekend or holiday, the current USD/JPY quote is kept
and Yahoo's official previous-close metadata is used only for the display change.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import urllib.parse
from collections import OrderedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yen_carry_alert as legacy
from khs_source_fetch import fetch_text

USER_AGENT = "Mozilla/5.0 yen-carry-alert/2.2"
YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)


def finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def valid_points(result: dict) -> list[tuple[float, float]]:
    timestamps = result.get("timestamp") or []
    rows = ((result.get("indicators") or {}).get("quote") or [])
    closes = rows[0].get("close", []) if rows else []
    points: list[tuple[float, float]] = []
    for timestamp, close in zip(timestamps, closes):
        ts_value = finite(timestamp)
        close_value = finite(close)
        if ts_value is not None and close_value is not None and close_value > 0:
            points.append((ts_value, close_value))
    points.sort(key=lambda item: item[0])
    return points


def exchange_zone(meta: dict) -> ZoneInfo:
    name = str(meta.get("exchangeTimezoneName") or "UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def rolling_reference(
    points: list[tuple[float, float]],
    seconds: int,
    *,
    max_gap_seconds: int,
) -> tuple[float, float]:
    latest_ts, latest_price = points[-1]
    target = latest_ts - seconds
    ref_ts, ref_price = min(points, key=lambda item: abs(item[0] - target))
    if abs(ref_ts - target) > max_gap_seconds or ref_price <= 0:
        raise RuntimeError("rolling reference point unavailable")
    return ref_price, ((latest_price - ref_price) / ref_price) * 100


def grouped_session_closes(points: list[tuple[float, float]], meta: dict) -> list[tuple[float, float]]:
    zone = exchange_zone(meta)
    sessions: OrderedDict[dt.date, tuple[float, float]] = OrderedDict()
    for timestamp, price in points:
        local_date = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(zone).date()
        sessions[local_date] = (timestamp, price)
    return list(sessions.values())


def fallback_previous_session(points: list[tuple[float, float]], meta: dict) -> float:
    sessions = grouped_session_closes(points, meta)
    if len(sessions) < 2:
        raise RuntimeError("two completed/local trading dates unavailable")
    previous_price = sessions[-2][1]
    if previous_price <= 0:
        raise RuntimeError("invalid previous session close")
    return previous_price


def official_previous_close(meta: dict) -> float | None:
    return (
        finite(meta.get("regularMarketPreviousClose"))
        or finite(meta.get("previousClose"))
        or finite(meta.get("chartPreviousClose"))
    )


def fx_reference(
    points: list[tuple[float, float]],
    meta: dict,
) -> tuple[float, float, float, float]:
    """Return current FX quote and a robust display reference.

    The alert stage uses only the current USD/JPY price. A missing exact 24-hour
    reference must therefore not suppress the quote. Across weekends or market
    holidays, fall back to Yahoo's official previous-close metadata for the
    display change while preserving the latest five-minute price and timestamp.
    """
    latest_ts, latest_price = points[-1]
    try:
        previous, change_pct = rolling_reference(
            points,
            86_400,
            max_gap_seconds=28_800,
        )
    except RuntimeError:
        previous = official_previous_close(meta)
        if previous is None or previous <= 0:
            previous = fallback_previous_session(points, meta)
        change_pct = ((latest_price - previous) / previous) * 100
    return latest_price, latest_ts, previous, change_pct


def official_cash_reference(
    points: list[tuple[float, float]],
    meta: dict,
) -> tuple[float, float, float, float]:
    official_price = finite(meta.get("regularMarketPrice"))
    official_time = finite(meta.get("regularMarketTime"))
    previous = finite(meta.get("regularMarketPreviousClose")) or finite(meta.get("previousClose"))

    latest_ts, latest_bar_price = points[-1]
    price = official_price if official_price is not None and official_price > 0 else latest_bar_price
    timestamp = official_time if official_time is not None and official_time > 0 else latest_ts
    if previous is None or previous <= 0:
        previous = fallback_previous_session(points, meta)
    change_pct = ((price - previous) / previous) * 100
    return price, timestamp, previous, change_pct


def futures_reference(
    points: list[tuple[float, float]],
    meta: dict,
) -> tuple[float, float, float, float]:
    official_price = finite(meta.get("regularMarketPrice"))
    official_time = finite(meta.get("regularMarketTime"))
    previous = finite(meta.get("regularMarketPreviousClose")) or finite(meta.get("previousClose"))
    latest_ts, latest_bar_price = points[-1]
    price = official_price if official_price is not None and official_price > 0 else latest_bar_price
    timestamp = official_time if official_time is not None and official_time > 0 else latest_ts
    if previous is None or previous <= 0:
        previous = fallback_previous_session(points, meta)
    return price, timestamp, previous, ((price - previous) / previous) * 100


def parse_payload(payload: dict, spec: legacy.SymbolSpec) -> legacy.Quote:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        error = chart.get("error") or {}
        raise RuntimeError(f"{spec.symbol} data missing: {error.get('description', 'unknown')}")

    result = results[0]
    meta = result.get("meta") or {}
    points = valid_points(result)
    if len(points) < 2:
        raise RuntimeError(f"{spec.symbol} valid points insufficient")

    if spec.kind == "환율":
        latest_price, latest_ts, previous_close, change_pct = fx_reference(points, meta)
    elif spec.kind == "현물":
        latest_price, latest_ts, previous_close, change_pct = official_cash_reference(points, meta)
    else:
        latest_price, latest_ts, previous_close, change_pct = futures_reference(points, meta)

    if spec.kind in {"현물", "선물"} and abs(change_pct) > 30:
        raise RuntimeError(f"{spec.symbol} implausible session move: {change_pct:.2f}%")
    if spec.kind == "환율" and abs(change_pct) > 12:
        raise RuntimeError(f"{spec.symbol} implausible reference move: {change_pct:.2f}%")

    observed = dt.datetime.fromtimestamp(latest_ts, tz=dt.timezone.utc)
    return legacy.Quote(
        symbol=spec.symbol,
        label=spec.label,
        kind=spec.kind,
        price=latest_price,
        previous_close=previous_close,
        change_pct=change_pct,
        timestamp_utc=observed.isoformat().replace("+00:00", "Z"),
        timestamp_epoch=latest_ts,
    )


def yahoo_url(base: str, symbol: str) -> str:
    params = urllib.parse.urlencode(
        {
            "interval": os.getenv("YEN_CARRY_YAHOO_INTERVAL", "5m"),
            "range": os.getenv("YEN_CARRY_YAHOO_RANGE", "5d"),
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    return f"{base}/{urllib.parse.quote(symbol, safe='')}?{params}"


def fetch_one(base: str, spec: legacy.SymbolSpec) -> legacy.Quote:
    url = yahoo_url(base, spec.symbol)
    text, error = fetch_text(
        url,
        USER_AGENT,
        timeout=18,
        attempts=2,
        accept="application/json",
    )
    if error or not text:
        raise RuntimeError(error or "empty response")
    return parse_payload(json.loads(text), spec)


def quotes_consistent(first: legacy.Quote, second: legacy.Quote) -> bool:
    price_gap_pct = abs(first.price - second.price) / max(first.price, second.price) * 100
    change_gap = abs(first.change_pct - second.change_pct)
    timestamp_gap = abs(first.timestamp_epoch - second.timestamp_epoch)
    return price_gap_pct <= 0.05 and change_gap <= 0.10 and timestamp_gap <= 1_800


def fetch_quote(spec: legacy.SymbolSpec) -> legacy.Quote:
    successes: list[legacy.Quote] = []
    errors: list[str] = []
    for base in YAHOO_BASES:
        try:
            successes.append(fetch_one(base, spec))
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}: {exc}")

    if not successes:
        raise RuntimeError(f"{spec.symbol} all routes failed: {' | '.join(errors)}")
    if len(successes) == 1:
        return successes[0]

    first, second = successes[:2]
    if not quotes_consistent(first, second):
        raise RuntimeError(
            f"{spec.symbol} provider cache mismatch: "
            f"{first.price:.4f}/{first.change_pct:.3f}% vs "
            f"{second.price:.4f}/{second.change_pct:.3f}%"
        )
    return max(successes, key=lambda quote: quote.timestamp_epoch)

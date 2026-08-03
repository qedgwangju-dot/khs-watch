#!/usr/bin/env python3
"""Verified Yahoo market-data retrieval and sector aggregation."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text
from yen_sector_config import *

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


def parse_payload(symbol: str, payload: dict) -> QuoteSeries:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        error = chart.get("error") or {}
        raise RuntimeError(error.get("description") or f"{symbol} chart missing")
    result = results[0]
    meta = result.get("meta") or {}
    points = valid_points(result)
    if len(points) < 2:
        raise RuntimeError(f"{symbol} observations insufficient")

    latest_bar_epoch, latest_bar_price = points[-1]
    latest_price = finite(meta.get("regularMarketPrice")) or latest_bar_price
    latest_epoch = finite(meta.get("regularMarketTime")) or latest_bar_epoch
    previous_close = finite(meta.get("regularMarketPreviousClose")) or finite(
        meta.get("previousClose")
    )
    if previous_close is None or previous_close <= 0:
        raise RuntimeError(f"{symbol} previous close missing")
    session_change_pct = ((latest_price - previous_close) / previous_close) * 100
    if abs(session_change_pct) > 35:
        raise RuntimeError(f"{symbol} implausible session move {session_change_pct:.2f}%")

    timezone = str(meta.get("exchangeTimezoneName") or "Asia/Tokyo")
    return QuoteSeries(
        symbol=symbol,
        latest_price=latest_price,
        latest_epoch=latest_epoch,
        previous_close=previous_close,
        session_change_pct=session_change_pct,
        points=tuple(points),
        exchange_timezone=timezone,
    )


def yahoo_url(base: str, symbol: str) -> str:
    params = urllib.parse.urlencode(
        {
            "interval": "5m",
            "range": "5d",
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    return f"{base}/{urllib.parse.quote(symbol, safe='')}?{params}"


def fetch_one(base: str, symbol: str) -> QuoteSeries:
    text, error = fetch_text(
        yahoo_url(base, symbol),
        USER_AGENT,
        timeout=18,
        attempts=2,
        accept="application/json",
    )
    if error or not text:
        raise RuntimeError(error or f"{symbol} empty response")
    return parse_payload(symbol, json.loads(text))


def quotes_consistent(first: QuoteSeries, second: QuoteSeries) -> bool:
    price_gap = abs(first.latest_price - second.latest_price) / max(
        first.latest_price, second.latest_price
    ) * 100
    return (
        price_gap <= 0.08
        and abs(first.session_change_pct - second.session_change_pct) <= 0.15
        and abs(first.latest_epoch - second.latest_epoch) <= 1_800
    )


def fetch_quote(symbol: str) -> QuoteSeries:
    successes: list[QuoteSeries] = []
    errors: list[str] = []
    for base in YAHOO_BASES:
        try:
            successes.append(fetch_one(base, symbol))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if not successes:
        raise RuntimeError(f"{symbol} failed: {' | '.join(errors)}")
    if len(successes) == 1:
        return successes[0]
    if not quotes_consistent(successes[0], successes[1]):
        raise RuntimeError(f"{symbol} query1/query2 mismatch")
    return max(successes, key=lambda item: item.latest_epoch)


def fetch_quotes(symbols: set[str]) -> tuple[dict[str, QuoteSeries], dict[str, str]]:
    quotes: dict[str, QuoteSeries] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(12, max(1, len(symbols)))) as executor:
        futures = {executor.submit(fetch_quote, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                quotes[symbol] = future.result()
            except Exception as exc:
                errors[symbol] = f"{type(exc).__name__}: {exc}"
    return quotes, errors


def nearest_price(
    points: tuple[tuple[float, float], ...], target: float, max_gap: float = 480
) -> tuple[float, float] | None:
    if not points:
        return None
    timestamp, price = min(points, key=lambda item: abs(item[0] - target))
    if abs(timestamp - target) > max_gap:
        return None
    return timestamp, price


def rolling_change(quote: QuoteSeries, minutes: int) -> float | None:
    latest_ts, latest_price = quote.points[-1]
    reference = nearest_price(quote.points, latest_ts - minutes * 60)
    if reference is None:
        return None
    ref_ts, ref_price = reference
    try:
        zone = ZoneInfo(quote.exchange_timezone)
    except Exception:
        zone = KST
    latest_date = dt.datetime.fromtimestamp(latest_ts, UTC).astimezone(zone).date()
    ref_date = dt.datetime.fromtimestamp(ref_ts, UTC).astimezone(zone).date()
    if latest_date != ref_date or ref_price <= 0:
        return None
    return ((latest_price - ref_price) / ref_price) * 100


def rolling_relative_history(
    sector: QuoteSeries, benchmark: QuoteSeries, minutes: int = 30
) -> list[float]:
    values: list[float] = []
    benchmark_points = benchmark.points
    for timestamp, price in sector.points:
        sector_ref = nearest_price(sector.points, timestamp - minutes * 60)
        bench_now = nearest_price(benchmark_points, timestamp)
        bench_ref = nearest_price(benchmark_points, timestamp - minutes * 60)
        if sector_ref is None or bench_now is None or bench_ref is None:
            continue
        _, sector_ref_price = sector_ref
        _, bench_now_price = bench_now
        _, bench_ref_price = bench_ref
        if min(sector_ref_price, bench_ref_price) <= 0:
            continue
        sector_return = ((price - sector_ref_price) / sector_ref_price) * 100
        bench_return = ((bench_now_price - bench_ref_price) / bench_ref_price) * 100
        values.append(sector_return - bench_return)
    return values


def grouped_daily_closes(quote: QuoteSeries) -> dict[str, float]:
    try:
        zone = ZoneInfo(quote.exchange_timezone)
    except Exception:
        zone = KST
    result: dict[str, float] = {}
    for timestamp, price in quote.points:
        day = dt.datetime.fromtimestamp(timestamp, UTC).astimezone(zone).date().isoformat()
        result[day] = price
    return result


def daily_relative_history(sector: QuoteSeries, benchmark: QuoteSeries) -> list[float]:
    sector_days = grouped_daily_closes(sector)
    benchmark_days = grouped_daily_closes(benchmark)
    common = sorted(set(sector_days) & set(benchmark_days))
    values: list[float] = []
    for previous_day, current_day in zip(common, common[1:]):
        s0, s1 = sector_days[previous_day], sector_days[current_day]
        b0, b1 = benchmark_days[previous_day], benchmark_days[current_day]
        if min(s0, b0) <= 0:
            continue
        values.append(((s1 / s0) - 1) * 100 - ((b1 / b0) - 1) * 100)
    return values


def local_session_open(country: str, current: dt.datetime) -> bool:
    local = current.astimezone(KST)
    if local.weekday() >= 5:
        return False
    minute = local.hour * 60 + local.minute
    if country == "JP":
        return 9 * 60 <= minute <= 11 * 60 + 30 or 12 * 60 + 30 <= minute <= 15 * 60 + 30
    return 9 * 60 <= minute <= 15 * 60 + 30


def quote_is_fresh(quote: QuoteSeries, current: dt.datetime) -> bool:
    age = max(0.0, current.timestamp() - quote.points[-1][0]) / 60
    return age <= DATA_MAX_AGE_MINUTES


def market_status(country: str, quote: QuoteSeries, current: dt.datetime) -> str:
    local = current.astimezone(KST)
    quote_date = dt.datetime.fromtimestamp(quote.latest_epoch, UTC).astimezone(KST).date()
    if local_session_open(country, current) and quote_is_fresh(quote, current):
        return "ì¥ì¤‘"
    if quote_date == local.date() and (local.hour, local.minute) >= (15, 30):
        return "ì¢…ê°€"
    return "ì§ì „ ì„¸ì…˜"


def primary_quote(spec: SectorSpec, quotes: dict[str, QuoteSeries]) -> QuoteSeries | None:
    for symbol in spec.primary:
        if symbol in quotes:
            return quotes[symbol]
    return None


def component_quotes(spec: SectorSpec, quotes: dict[str, QuoteSeries]) -> list[QuoteSeries]:
    return [quotes[symbol] for symbol in spec.components if symbol in quotes]


def aggregate_sector(
    spec: SectorSpec,
    quotes: dict[str, QuoteSeries],
    current: dt.datetime,
) -> SectorResult | None:
    benchmark = quotes.get(spec.benchmark)
    if benchmark is None:
        return None
    primary = primary_quote(spec, quotes)
    components = component_quotes(spec, quotes)
    if primary is None and not components:
        return None

    open_and_fresh = local_session_open(spec.country, current) and quote_is_fresh(
        benchmark, current
    )
    component_30 = [value for item in components if (value := rolling_change(item, 30)) is not None]
    benchmark_30 = rolling_change(benchmark, 30)
    primary_30 = rolling_change(primary, 30) if primary is not None else None

    if open_and_fresh and benchmark_30 is not None:
        sector_30 = median(component_30) if len(component_30) >= MIN_COMPONENTS_FOR_BREADTH else primary_30
    else:
        sector_30 = None

    if sector_30 is not None and benchmark_30 is not None:
        timeframe = "30ë¶„"
        sector_change = sector_30
        benchmark_change = benchmark_30
        relative = sector_change - benchmark_change
        histories: list[float] = []
        if primary is not None:
            histories.extend(rolling_relative_history(primary, benchmark))
        for item in components:
            histories.extend(rolling_relative_history(item, benchmark))
        sigma = robust_sigma(histories, 0.10)
        threshold = max(INTRADAY_MIN_RELATIVE_PCT, SIGNIFICANCE_Z * sigma)
        source = "ëŒ€í‘œì¢…ëª© ì¤‘ì•™ê°’" if len(component_30) >= MIN_COMPONENTS_FOR_BREADTH else "ì—…ì¢… ETF"
    else:
        timeframe = "ë‹¹ì¼"
        component_session = [item.session_change_pct for item in components]
        sector_session = (
            primary.session_change_pct
            if primary is not None
            else median(component_session)
        )
        if sector_session is None:
            return None
        sector_change = sector_session
        benchmark_change = benchmark.session_change_pct
        relative = sector_change - benchmark_change
        histories = []
        if primary is not None:
            histories.extend(daily_relative_history(primary, benchmark))
        for item in components:
            histories.extend(daily_relative_history(item, benchmark))
        sigma = robust_sigma(histories, 0.20)
        threshold = max(SESSION_MIN_RELATIVE_PCT, SIGNIFICANCE_Z * sigma)
        source = "ì—…ì¢… ETF""–b&–Ö'’—2æ÷BæöæRVÇ6R.¸ÈÙÎÊ(^ºª’ÊIÙY«	  ¢6–væ–f–6çBÒ'2‡&VÆF—fR’ãÒF‡&W6†öÆ@¢–b7V2æW‡V7FVE÷6–vâÓÒ ¢Æ–væVBÒæöæP¢6öçG&'’ÒæöæP¢VÇ6S ¢Æ–væVBÒ6–væ–f–6çBæB&VÆF—fR¢7V2æW‡V7FVE÷6–vââ ¢6öçG&'’Ò6–væ–f–6çBæB&VÆF—fR¢7V2æW‡V7FVE÷6–vâÂ  ¢'&VGFƒ¢fÆöBÂæöæRÒæöæP¢–bÆVâ†6ö×öæVçG2’ãÒÔ”åô4ôÕôäTåE5ôdõ%ô%$TEDƒ ¢–bF–ÖVg&ÖRÓÒ#3»hB"æB&Væ6†Ö&µó3—2æ÷BæöæS ¢6ö×öæVçE÷&VÆF—fW2Ò°¢fÇVRÒ&Væ6†Ö&µó3 ¢f÷"—FVÒ–â6ö×öæVçG0¢–b‡fÇVR£Ò&öÆÆ–æuö6†ævR†—FVÒÂ3’’—2æ÷BæöæP¢Ğ¢VÇ6S ¢6ö×öæVçE÷&VÆF—fW2Ò°¢—FVÒç6W76–öåö6†ævU÷7BÒ&Væ6†Ö&²ç6W76–öåö6†ævU÷7Bf÷"—FVÒ–â6ö×öæVçG0¢Ğ¢–b6ö×öæVçE÷&VÆF—fW3 ¢–b7V2æW‡V7FVE÷6–vâÓÒ ¢'&VGF‚Ò7VÒ‡fÇVRâf÷"fÇVR–â6ö×öæVçE÷&VÆF—fW2’òÆVâ†6ö×öæVçE÷&VÆF—fW2’¢ ¢VÇ6S ¢'&VGF‚Ò7VÒ‡fÇVR¢7V2æW‡V7FVE÷6–vââf÷"fÇVR–â6ö×öæVçE÷&VÆF—fW2’òÆVâ†6ö×öæVçE÷&VÆF—fW2’¢  ¢6ö×öæVçE÷&–6W2Ò¶—FVÒç7–Ö&öÃ¢—FVÒæÆFW7E÷&–6Rf÷"—FVÒ–â6ö×öæVçG7Ğ¢–b&–Ö'’—2æ÷BæöæS ¢6ö×öæVçE÷&–6W5·&–Ö'’ç7–Ö&öÅÒÒ&–Ö'’æÆFW7E÷&–6P¢FFöWö6‚ÒÖ‚€¢¶&Væ6†Ö&²æÆFW7EöWö6…Ğ¢²¶—FVÒæÆFW7EöWö6‚f÷"—FVÒ–â6ö×öæVçG5Ğ¢²…·&–Ö'’æÆFW7EöWö6…Ò–b&–Ö'’—2æ÷BæöæRVÇ6RµÒ¢¢&WGW&â6V7F÷%&W7VÇB€¢¶W“×7V2æ¶W’À¢æÖS×7V2ææÖRÀ¢6÷VçG'“×7V2æ6÷VçG'’À¢&öÆS×7V2ç&öÆRÀ¢W‡V7FVE÷6–vã×7V2æW‡V7FVE÷6–vâÀ¢F–ÖVg&ÖS×F–ÖVg&ÖRÀ¢6V7F÷%ö6†ævU÷7C×6V7F÷%ö6†ævRÀ¢&Væ6†Ö&µö6†ævU÷7CÖ&Væ6†Ö&µö6†ævRÀ¢&VÆF—fU÷7C×&VÆF—fRÀ¢6–vÖ÷7C×6–vÖÀ¢§66÷&S×&VÆF—fRò6–vÖ–b6–vÖâVÇ6RãÀ¢6–væ–f–6çC×6–væ–f–6çBÀ¢Æ–væVCÖÆ–væVBÀ¢6öçG&'“Ö6öçG&'’À¢'&VGF…÷7CÖ'&VGF‚À¢Ö&¶WE÷7FGW3ÖÖ&¶WE÷7FGW2‡7V2æ6÷VçG'’Â&Væ6†Ö&²Â7W'&VçB’À¢FFöWö6ƒÖFFöWö6‚À¢6ö×öæVçE÷&–6W3Ö6ö×öæVçE÷&–6W2À¢&Væ6†Ö&µ÷&–6SÖ&Væ6†Ö&²æÆFW7E÷&–6RÀ¢6÷W&6S×6÷W&6RÀ¢  ¦FVbÆÅ÷7–Ö&öÇ2‚’Óâ6WE·7G%Ó ¢7–Ö&öÇ2Ò²#““ƒCRåB"Â%äµ3'Ğ¢f÷"7V2–â4T5Dõ%3 ¢7–Ö&öÇ2çWFFR‡7V2ç&–Ö'’¢7–Ö&öÇ2çWFFR‡7V2æ6ö×öæVçG2¢&WGW&â7–Ö&öÇ0  ¦FVb6GW&U÷6æ6†÷B€¢7W'&VçC¢GBæFFWF–ÖRÀ¢’ÓâGWÆU¶Æ—7Eµ6V7F÷%&W7VÇEÒÂF–7E·7G"Â7G%ÒÂF–7E·7G"ÂV÷FU6W&–W5ÕÓ ¢V÷FW2ÂW'&÷'2ÒfWF6…÷V÷FW2†ÆÅ÷7–Ö&öÇ2‚’¢2föÆÆ÷r×W7FFRg&öÒF†R&Wf–÷W2&VÆV6RW6VBF†RÆVv7’Dõ•‚¶W’à¢2&W6W'fR—B2âÆ–2v†–ÆRfWF6†–ærF†RfW&–f–VB–†öò¦â6öFRà¢–b#““ƒCRåB"–âV÷FW3 ¢V÷FW5²%åDõ‚%ÒÒV÷FW5²#““ƒCRåB%Ğ¢&W7VÇG2Ò°¢&W7VÇ@¢f÷"7V2–â4T5Dõ%0¢–b‡&W7VÇB£Òvw&VvFU÷6V7F÷"‡7V2ÂV÷FW2Â7W'&VçB’’—2æ÷BæöæP¢Ğ¢&WGW&â&W7VÇG2ÂW'&÷'2ÂV÷FW0
#!/usr/bin/env python3
"""Verified Yahoo sector and benchmark data aggregation."""
from __future__ import annotations

import datetime as dt
import json
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
        ts_value, close_value = finite(timestamp), finite(close)
        if ts_value is not None and close_value is not None and close_value > 0:
            points.append((ts_value, close_value))
    return sorted(points)


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
    bar_epoch, bar_price = points[-1]
    latest_price = finite(meta.get("regularMarketPrice")) or bar_price
    latest_epoch = finite(meta.get("regularMarketTime")) or bar_epoch
    previous_close = (
        finite(meta.get("regularMarketPreviousClose"))
        or finite(meta.get("previousClose"))
    )
    if previous_close is None or previous_close <= 0:
        raise RuntimeError(f"{symbol} previous close missing")
    session_change = ((latest_price - previous_close) / previous_close) * 100
    if abs(session_change) > 35:
        raise RuntimeError(f"{symbol} implausible session move {session_change:.2f}%")
    timezone = str(meta.get("exchangeTimezoneName") or "Asia/Tokyo")
    return QuoteSeries(
        symbol=symbol,
        latest_price=latest_price,
        latest_epoch=latest_epoch,
        previous_close=previous_close,
        session_change_pct=session_change,
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
    price_gap = (
        abs(first.latest_price - second.latest_price)
        / max(first.latest_price, second.latest_price)
        * 100
    )
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


def fetch_quotes(
    symbols: set[str],
) -> tuple[dict[str, QuoteSeries], dict[str, str]]:
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
    points: tuple[tuple[float, float], ...],
    target: float,
    max_gap: float = 480,
) -> tuple[float, float] | None:
    if not points:
        return None
    timestamp, price = min(points, key=lambda item: abs(item[0] - target))
    return None if abs(timestamp - target) > max_gap else (timestamp, price)


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
    sector: QuoteSeries,
    benchmark: QuoteSeries,
    minutes: int = 30,
) -> list[float]:
    values: list[float] = []
    for timestamp, price in sector.points:
        sector_ref = nearest_price(sector.points, timestamp - minutes * 60)
        bench_now = nearest_price(benchmark.points, timestamp)
        bench_ref = nearest_price(benchmark.points, timestamp - minutes * 60)
        if sector_ref is None or bench_now is None or bench_ref is None:
            continue
        _, s0 = sector_ref
        _, b1 = bench_now
        _, b0 = bench_ref
        if min(s0, b0) <= 0:
            continue
        values.append(((price / s0) - 1) * 100 - ((b1 / b0) - 1) * 100)
    return values


def grouped_daily_closes(quote: QuoteSeries) -> dict[str, float]:
    try:
        zone = ZoneInfo(quote.exchange_timezone)
    except Exception:
        zone = KST
    result: dict[str, float] = {}
    for timestamp, price in quote.points:
        day = (
            dt.datetime.fromtimestamp(timestamp, UTC)
            .astimezone(zone)
            .date()
            .isoformat()
        )
        result[day] = price
    return result


def daily_relative_history(
    sector: QuoteSeries,
    benchmark: QuoteSeries,
) -> list[float]:
    sector_days = grouped_daily_closes(sector)
    benchmark_days = grouped_daily_closes(benchmark)
    common = sorted(set(sector_days) & set(benchmark_days))
    values: list[float] = []
    for previous_day, current_day in zip(common, common[1:]):
        s0, s1 = sector_days[previous_day], sector_days[current_day]
        b0, b1 = benchmark_days[previous_day], benchmark_days[current_day]
        if min(s0, b0) > 0:
            values.append((s1 / s0 - 1) * 100 - (b1 / b0 - 1) * 100)
    return values


def local_session_open(country: str, current: dt.datetime) -> bool:
    local = current.astimezone(KST)
    if local.weekday() >= 5:
        return False
    minute = local.hour * 60 + local.minute
    if country == "JP":
        return (
            9 * 60 <= minute <= 11 * 60 + 30
            or 12 * 60 + 30 <= minute <= 15 * 60 + 30
        )
    return 9 * 60 <= minute <= 15 * 60 + 30


def quote_is_fresh(quote: QuoteSeries, current: dt.datetime) -> bool:
    age_minutes = max(0.0, current.timestamp() - quote.points[-1][0]) / 60
    return age_minutes <= DATA_MAX_AGE_MINUTES


def market_status(
    country: str,
    quote: QuoteSeries,
    current: dt.datetime,
) -> str:
    local = current.astimezone(KST)
    quote_date = (
        dt.datetime.fromtimestamp(quote.latest_epoch, UTC)
        .astimezone(KST)
        .date()
    )
    if local_session_open(country, current) and quote_is_fresh(quote, current):
        return "장중"
    if quote_date == local.date() and (local.hour, local.minute) >= (15, 30):
        return "종가"
    return "직전 세션"


def primary_quote(
    spec: SectorSpec,
    quotes: dict[str, QuoteSeries],
) -> QuoteSeries | None:
    return next((quotes[symbol] for symbol in spec.primary if symbol in quotes), None)


def component_quotes(
    spec: SectorSpec,
    quotes: dict[str, QuoteSeries],
) -> list[QuoteSeries]:
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

    open_and_fresh = (
        local_session_open(spec.country, current)
        and quote_is_fresh(benchmark, current)
    )
    component_30 = [
        value
        for item in components
        if (value := rolling_change(item, 30)) is not None
    ]
    benchmark_30 = rolling_change(benchmark, 30)
    primary_30 = rolling_change(primary, 30) if primary is not None else None

    sector_30 = None
    if open_and_fresh and benchmark_30 is not None:
        if len(component_30) >= MIN_COMPONENTS_FOR_BREADTH:
            sector_30 = median(component_30)
        else:
            sector_30 = primary_30

    if sector_30 is not None and benchmark_30 is not None:
        timeframe = "30분"
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
        source = (
            "대표종목 중앙값"
            if len(component_30) >= MIN_COMPONENTS_FOR_BREADTH
            else "업종 ETF"
        )
    else:
        timeframe = "당일"
        component_session = [item.session_change_pct for item in components]
        if primary is not None:
            sector_session = primary.session_change_pct
        else:
            sector_session = median(component_session)
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
        sigma = robust_sigma(histories, 0.22)
        threshold = max(SESSION_MIN_RELATIVE_PCT, SIGNIFICANCE_Z * sigma)
        source = "업종 ETF" if primary is not None else "대표종목 중앙값"

    significant = abs(relative) >= threshold
    if spec.expected_sign == 0:
        aligned = contrary = None
    else:
        aligned = significant and relative * spec.expected_sign > 0
        contrary = significant and relative * spec.expected_sign < 0

    breadth: float | None = None
    if len(components) >= MIN_COMPONENTS_FOR_BREADTH:
        if timeframe == "30분" and benchmark_30 is not None:
            component_relatives = [
                value - benchmark_30
                for item in components
                if (value := rolling_change(item, 30)) is not None
            ]
        else:
            component_relatives = [
                item.session_change_pct - benchmark.session_change_pct
                for item in components
            ]
        if component_relatives:
            if spec.expected_sign == 0:
                breadth = (
                    sum(value > 0 for value in component_relatives)
                    / len(component_relatives)
                    * 100
                )
            else:
                breadth = (
                    sum(value * spec.expected_sign > 0 for value in component_relatives)
                    / len(component_relatives)
                    * 100
                )

    component_prices = {item.symbol: item.latest_price for item in components}
    if primary is not None:
        component_prices[primary.symbol] = primary.latest_price

    data_epoch = max(
        [benchmark.latest_epoch]
        + [item.latest_epoch for item in components]
        + ([primary.latest_epoch] if primary is not None else [])
    )
    return SectorResult(
        key=spec.key,
        name=spec.name,
        country=spec.country,
        role=spec.role,
        expected_sign=spec.expected_sign,
        timeframe=timeframe,
        sector_change_pct=sector_change,
        benchmark_change_pct=benchmark_change,
        relative_pct=relative,
        sigma_pct=sigma,
        zscore=relative / sigma if sigma > 0 else 0.0,
        significant=significant,
        aligned=aligned,
        contrary=contrary,
        breadth_pct=breadth,
        market_status=market_status(spec.country, benchmark, current),
        data_epoch=data_epoch,
        component_prices=component_prices,
        benchmark_price=benchmark.latest_price,
        source=source,
    )


def all_symbols() -> set[str]:
    # ^KS11 is retained only to finish a follow-up event created before
    # the market-specific Korean benchmark migration.
    symbols = {"^KS11"}
    for spec in SECTORS:
        symbols.add(spec.benchmark)
        symbols.update(spec.primary)
        symbols.update(spec.components)
    return symbols


def capture_snapshot(
    current: dt.datetime,
) -> tuple[list[SectorResult], dict[str, str], dict[str, QuoteSeries]]:
    quotes, errors = fetch_quotes(all_symbols())
    # Compatibility with Japanese events created before the TOPIX-code fix.
    if "1306.T" in quotes:
        quotes["^TOPX"] = quotes["1306.T"]
    results = [
        result
        for spec in SECTORS
        if (result := aggregate_sector(spec, quotes, current)) is not None
    ]
    return results, errors, quotes

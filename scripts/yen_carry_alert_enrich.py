#!/usr/bin/env python3
"""Add a verified USD/JPY 24-hour change and range line to alert output."""

from __future__ import annotations

import json
import math
import os
import pathlib
import urllib.parse

from khs_source_fetch import fetch_text

BODY_PATH = pathlib.Path("out/yen_carry_alert.md")
SYMBOL = "JPY=X"
BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)
USER_AGENT = "Mozilla/5.0 yen-carry-alert/2.0"


def finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_payload() -> dict:
    params = urllib.parse.urlencode(
        {
            "interval": os.getenv("YEN_CARRY_YAHOO_INTERVAL", "5m"),
            "range": os.getenv("YEN_CARRY_YAHOO_RANGE", "5d"),
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    errors: list[str] = []
    for base in BASES:
        url = f"{base}/{urllib.parse.quote(SYMBOL, safe='')}?{params}"
        text, error = fetch_text(
            url,
            USER_AGENT,
            timeout=18,
            attempts=2,
            accept="application/json",
        )
        if error or not text:
            errors.append(error or "empty response")
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"JSONDecodeError: {exc}")
    raise RuntimeError(" | ".join(errors) or "USD/JPY 24시간 데이터 조회 실패")


def calculate_24h(payload: dict) -> tuple[float, float, float, float]:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError("USD/JPY 차트 결과 없음")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_rows = ((result.get("indicators") or {}).get("quote") or [])
    closes = quote_rows[0].get("close", []) if quote_rows else []

    points: list[tuple[float, float]] = []
    for timestamp, close in zip(timestamps, closes):
        ts_value = finite(timestamp)
        close_value = finite(close)
        if ts_value is not None and close_value is not None and close_value > 0:
            points.append((ts_value, close_value))
    points.sort(key=lambda item: item[0])
    if len(points) < 2:
        raise RuntimeError("USD/JPY 유효 시계열 부족")

    latest_ts, latest_price = points[-1]
    target_ts = latest_ts - 86_400
    reference_ts, reference_price = min(points, key=lambda item: abs(item[0] - target_ts))
    if reference_price == 0 or abs(reference_ts - target_ts) > 28_800:
        raise RuntimeError("USD/JPY 24시간 기준점 부재")

    window = [price for timestamp, price in points if target_ts <= timestamp <= latest_ts]
    if not window:
        raise RuntimeError("USD/JPY 24시간 구간 부재")

    change_pct = ((latest_price - reference_price) / reference_price) * 100
    low = min(window)
    high = max(window)
    return change_pct, low, high, high - low


def insert_line(body: str, line: str) -> str:
    lines = body.splitlines()
    lines = [item for item in lines if not item.startswith("USD/JPY 24시간:")]
    insert_at = next(
        (index + 1 for index, item in enumerate(lines) if item.strip().startswith(("USD/JPY:", "- USD/JPY:"))),
        1 if lines else 0,
    )
    lines.insert(insert_at, line)
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    if not BODY_PATH.exists():
        print("yen_carry_24h=skipped_no_alert")
        return 0

    body = BODY_PATH.read_text(encoding="utf-8")
    try:
        change_pct, low, high, span = calculate_24h(fetch_payload())
        line = (
            f"USD/JPY 24시간: {change_pct:+.2f}% · 저가 {low:.3f} · "
            f"고가 {high:.3f} · 범위 {span:.3f}엔"
        )
        status = "added"
    except Exception as exc:
        line = f"USD/JPY 24시간: 확인 실패 ({type(exc).__name__})"
        status = "unavailable"

    BODY_PATH.write_text(insert_line(body, line), encoding="utf-8")
    print(f"yen_carry_24h={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""LNG 공급·가격 감시 v22: Bundesbank 메타데이터 날짜 오인 차단."""
from __future__ import annotations

import datetime as dt
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v20 as v20


def parse_bundesbank_csv_v22(raw: bytes) -> list[tuple[dt.date, float]]:
    text = raw.decode("utf-8-sig", errors="replace")
    out: list[tuple[dt.date, float]] = []
    # Bundesbank BBK-CSV는 메타데이터 블록 뒤 실제 관측행이 날짜로 시작한다.
    # 날짜가 줄 중간에 등장하는 메타데이터/업데이트시각은 절대 관측치로 취급하지 않는다.
    pattern = re.compile(
        r'^\s*"?(20\d{2}-\d{2}-\d{2})"?\s*;\s*"?([-+]?\d+(?:[.,]\d+)?)"?(?:\s*;|\s*$)'
    )
    for line in text.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        try:
            date = dt.date.fromisoformat(m.group(1))
            value = float(m.group(2).replace(",", "."))
        except Exception:
            continue
        # 현재 독일 현행 10년 연방채 공식 시계열의 단위가 %인지 검증하는 안전범위.
        # 범위를 벗어나면 추정/보정하지 않고 전체 bond quote를 보류한다.
        if not (-1.0 <= value <= 8.0):
            raise RuntimeError(f"Bundesbank 10Y implausible observation date={date} value={value}")
        out.append((date, value))
    dedup = {}
    for date, value in out:
        dedup[date] = value
    series = sorted(dedup.items())
    if len(series) < 3:
        raise RuntimeError("Bundesbank data rows not found after strict line-start parsing")
    return series


v20.parse_bundesbank_csv = parse_bundesbank_csv_v22


def build_setup_test_v22(quotes):
    title, body, metadata = v20.build_setup_test_v20(quotes)
    title = "✅ LNG·유럽 채권금리 전이 감시 v22 적용"
    body += (
        "\n• Bundesbank BBK-CSV에서 날짜로 시작하는 실제 관측행만 읽고 메타데이터의 날짜/시간 숫자는 전면 배제"
        "\n• 독일 10년 공식값이 단위/범위 검증에 실패하면 숫자를 보내지 않고 판정 보류"
    )
    metadata["version"] = 22
    return title, body, metadata


def build_regular_alert_v22(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v20.build_regular_alert_v20(groups, quotes, new_signals, cleared_signals)
    metadata["version"] = 22
    return title, body, metadata


core.fetch_market_quotes = v20.fetch_market_quotes_v20
core.apply_hysteresis = v20.apply_hysteresis_v20
core.format_quote = v20.format_quote_v20
core.build_regular_alert = build_regular_alert_v22
core.build_setup_test = build_setup_test_v22

if __name__ == "__main__":
    raise SystemExit(core.main())

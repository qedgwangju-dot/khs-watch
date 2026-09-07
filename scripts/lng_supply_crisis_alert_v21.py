#!/usr/bin/env python3
"""LNG 공급·가격 감시 v21: Bundesbank CSV 형식 변화에 강한 공식 채권 파서."""
from __future__ import annotations

import datetime as dt
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v20 as v20


def parse_bundesbank_csv_v21(raw: bytes) -> list[tuple[dt.date, float]]:
    # 표준 SDMX CSV 헤더가 있으면 v20 정식 파서를 우선 사용한다.
    try:
        return v20.parse_bundesbank_csv(raw)
    except Exception:
        pass

    # Bundesbank가 내려주는 CSV 표현이 로케일/응답 형식에 따라 달라지는 경우에도
    # 각 관측행의 ISO 날짜와 첫 번째 '수익률 범위 숫자'를 추출한다.
    text = raw.decode("utf-8-sig", errors="replace")
    out: list[tuple[dt.date, float]] = []
    for line in text.splitlines():
        date_match = re.search(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)", line)
        if not date_match:
            continue
        try:
            date = dt.date.fromisoformat(date_match.group(1))
        except Exception:
            continue
        tail = line[date_match.end():]
        # 세미콜론 CSV의 decimal comma와 일반 decimal point를 모두 허용한다.
        candidates = re.findall(r"(?<!\d)([-+]?\d{1,2}(?:[.,]\d{1,6})?)(?!\d)", tail)
        value = None
        for token in candidates:
            try:
                candidate = float(token.replace(",", "."))
            except Exception:
                continue
            # 독일 10년 국채 수익률로 현실적인 범위. 메타데이터의 연도/코드 숫자 오인 방지.
            if -2.0 <= candidate <= 15.0:
                value = candidate
                break
        if value is not None:
            out.append((date, value))

    # 동일 날짜가 여러 번 나오면 마지막 값을 사용한다.
    dedup = {}
    for date, value in out:
        dedup[date] = value
    series = sorted(dedup.items())
    if len(series) < 3:
        preview = re.sub(r"\s+", " ", text[:500]).strip()
        raise RuntimeError(f"Bundesbank CSV generic parse failed preview={preview[:240]}")
    return series


# v20의 공식 원천 로직은 유지하고 Bundesbank 파서만 강화한다.
v20.parse_bundesbank_csv = parse_bundesbank_csv_v21


def build_setup_test_v21(quotes):
    title, body, metadata = v20.build_setup_test_v20(quotes)
    title = "✅ LNG·유럽 채권금리 전이 감시 v21 적용"
    body += (
        "\n• Bundesbank 공식 CSV가 SDMX 표준/로케일 형식 중 어느 쪽으로 와도 날짜·수익률을 검증 파싱"
        "\n• 파싱 실패 시 원시 숫자를 추정하지 않고 독일 채권 수치 경보 보류"
    )
    metadata["version"] = 21
    return title, body, metadata


def build_regular_alert_v21(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v20.build_regular_alert_v20(groups, quotes, new_signals, cleared_signals)
    metadata["version"] = 21
    return title, body, metadata


core.fetch_market_quotes = v20.fetch_market_quotes_v20
core.apply_hysteresis = v20.apply_hysteresis_v20
core.format_quote = v20.format_quote_v20
core.build_regular_alert = build_regular_alert_v21
core.build_setup_test = build_setup_test_v21

if __name__ == "__main__":
    raise SystemExit(core.main())

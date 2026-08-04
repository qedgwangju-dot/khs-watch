#!/usr/bin/env python3
"""LNG 공급 위기 감시 v3: 가격값 정확도·시차 검증을 강화한다."""

from __future__ import annotations

import datetime as dt

import lng_supply_crisis_alert_v2 as core


MAX_PRICE_AGE = dt.timedelta(minutes=60)
MAX_ENDPOINT_TIME_GAP_SECONDS = 60
MAX_ENDPOINT_VALUE_GAP = 0.0005  # 0.05%


def fetch_verified_quote_strict(key: str) -> core.Quote:
    """같은 제공사의 두 엔드포인트가 가격·이전 종가·시각 모두 일치할 때만 채택한다."""
    first, second = [core.parse_yahoo_quote(key, base) for base in core.YAHOO_BASES]

    price_gap = abs(first.price - second.price) / max(
        abs(first.price), abs(second.price), 1e-9
    )
    previous_close_gap = abs(first.previous_close - second.previous_close) / max(
        abs(first.previous_close), abs(second.previous_close), 1e-9
    )
    time_gap = abs(first.timestamp_epoch - second.timestamp_epoch)

    if (
        price_gap > MAX_ENDPOINT_VALUE_GAP
        or previous_close_gap > MAX_ENDPOINT_VALUE_GAP
        or time_gap > MAX_ENDPOINT_TIME_GAP_SECONDS
    ):
        raise RuntimeError(
            f"{first.symbol}: Yahoo endpoint mismatch "
            f"price_gap={price_gap:.3%} "
            f"previous_close_gap={previous_close_gap:.3%} "
            f"time_gap={time_gap:.0f}s"
        )

    observed = dt.datetime.fromtimestamp(first.timestamp_epoch, core.UTC)
    age = core.now_utc() - observed
    if age < dt.timedelta(0) or age > MAX_PRICE_AGE:
        raise RuntimeError(
            f"{first.symbol}: stale quote "
            f"age={int(age.total_seconds() // 60)}m "
            f"timestamp={first.timestamp_utc}; 60분 초과 값은 알림 판정에서 제외"
        )
    return first


def build_setup_test_v3(
    quotes: dict[str, core.Quote],
) -> tuple[str, str, dict[str, object]]:
    title, body, metadata = core.build_setup_test(quotes)
    title = "✅ LNG·천연가스 감시 정확도 규칙 v3 적용"
    body = body.replace(
        "평일 4시간을 넘긴 시세는 새 신호 판정에서 제외",
        "60분을 넘긴 시세는 요일과 관계없이 새 신호 판정에서 제외",
    )
    body = body.replace(
        "Yahoo query1/query2는 동일 제공사 대조로 명시",
        "Yahoo query1/query2의 가격·이전 종가·시각이 모두 일치할 때만 사용",
    )
    body += (
        "\n• 가격에는 반드시 상품명·값·이전 종가·등락률·KST 기준시각·경과시간을 표시"
        "\n• JKM은 무료 실시간 직접값이 검증되지 않으므로 숫자를 추정하지 않고 확정 보도만 표시"
    )
    metadata["version"] = 3
    metadata["max_price_age_minutes"] = 60
    metadata["endpoint_value_tolerance_pct"] = MAX_ENDPOINT_VALUE_GAP * 100
    metadata["endpoint_time_tolerance_seconds"] = MAX_ENDPOINT_TIME_GAP_SECONDS
    return title, body, metadata


core.fetch_verified_quote = fetch_verified_quote_strict
core.build_setup_test = build_setup_test_v3


if __name__ == "__main__":
    raise SystemExit(core.main())

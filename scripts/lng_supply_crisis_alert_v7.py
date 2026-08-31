#!/usr/bin/env python3
"""LNG 공급 위기 감시 v7.

TTF는 사용자가 지정한 Trading Economics 한국 페이지를 단일 기준 원천으로 사용한다.
페이지 내부 actual/previous/표시 등락률 일치와 기준일 신선도를 검증하고,
영문/타언어 페이지의 캐시 시차 때문에 정확한 한국 기준값을 버리지 않는다.
호르무즈 군사악화 뉴스 확장 규칙은 v6를 그대로 사용한다.
"""

from __future__ import annotations

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v3 as strict
import lng_supply_crisis_alert_v4 as te
import lng_supply_crisis_alert_v5 as v5
import lng_supply_crisis_alert_v6 as v6


def fetch_te_ttf_quote_v7() -> core.Quote:
    raw_ko = te.fetch_te_html(te.TE_TTF_URLS[0])
    primary = te.parse_te_ttf(raw_ko)
    source_date = v5.parse_te_korean_source_date(raw_ko)
    v6._validate_source_date(source_date)

    # parse_te_ttf()가 actual/previous/페이지 내부 시세표/등락률의 상호 일치를 이미 검증한다.
    observed = core.now_utc()
    price = float(primary["actual"])
    previous = float(primary["previous"])
    return core.Quote(
        key="ttf",
        symbol="TE-KO:EU-GAS",
        label="Trading Economics 한국 EU Gas(TTF 추종 공개값)",
        unit="유로/MWh",
        price=price,
        previous_close=previous,
        change_pct=(price / previous - 1.0) * 100.0,
        timestamp_epoch=observed.timestamp(),
        timestamp_utc=observed.isoformat(timespec="seconds"),
        age_minutes=0,
        source_note=(
            "사용자 지정 Trading Economics 한국 페이지 직접값; "
            "actual/previous/페이지 내부 시세표 및 계산 등락률 검증; "
            f"기준일={source_date}"
        ),
    )


def fetch_market_quotes_v7() -> tuple[dict[str, core.Quote], list[str]]:
    quotes: dict[str, core.Quote] = {}
    errors: list[str] = []
    try:
        quotes["ttf"] = fetch_te_ttf_quote_v7()
    except Exception as exc:
        errors.append(f"ttf: {type(exc).__name__}: {exc}")
    try:
        quotes["brent"] = strict.fetch_verified_quote_strict("brent")
    except Exception as exc:
        errors.append(f"brent: {type(exc).__name__}: {exc}")
    return quotes, errors


def build_setup_test_v7(quotes: dict[str, core.Quote]):
    title, body, metadata = v6.build_setup_test_v6(quotes)
    title = "✅ LNG·천연가스 감시 정확도 규칙 v7 적용"
    body += (
        "\n• TTF는 사용자가 지정한 Trading Economics 한국 페이지를 최종 기준값으로 사용"
        "\n• 한국 페이지의 actual·previous·페이지 내부 시세표·직접 계산 등락률이 일치할 때만 출력"
        "\n• 타언어 페이지 캐시 지연은 참고만 하고 한국 기준값을 임의 변경하지 않음"
    )
    metadata["version"] = 7
    metadata["ttf_canonical_source"] = te.TE_TTF_URLS[0]
    return title, body, metadata


core.fetch_market_quotes = fetch_market_quotes_v7
core.format_quote = v6.format_quote_v6
core.signal_label = te.signal_label_v4
core.build_setup_test = build_setup_test_v7


if __name__ == "__main__":
    raise SystemExit(core.main())

#!/usr/bin/env python3
"""LNG 공급 위기 감시 v5: Trading Economics TTF 값의 기준일과 조회시각을 분리한다."""

from __future__ import annotations

import datetime as dt
import re
import statistics

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v3 as strict
import lng_supply_crisis_alert_v4 as te


def parse_te_korean_source_date(raw_html: str) -> str:
    text = te.visible_text(raw_html)
    patterns = (
        r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\s+EU\s*가스는",
        r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\s+유럽(?:연합)?\s*가스",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            year, month, day = (int(match.group(i)) for i in (1, 2, 3))
            return dt.date(year, month, day).isoformat()
    raise RuntimeError("Trading Economics TTF 기준일을 한글 페이지에서 확인하지 못함")


def fetch_te_ttf_quote_v5() -> core.Quote:
    raw_ko = te.fetch_te_html(te.TE_TTF_URLS[0])
    raw_en = te.fetch_te_html(te.TE_TTF_URLS[1])
    ko = te.parse_te_ttf(raw_ko)
    en = te.parse_te_ttf(raw_en)

    actuals = [ko["actual"], en["actual"]]
    previous_values = [ko["previous"], en["previous"]]
    if (max(actuals) / min(actuals) - 1.0) * 100.0 > te.TE_MAX_CROSS_PAGE_GAP_PCT:
        raise RuntimeError(f"Trading Economics Korean/English page mismatch: {actuals}")
    if (max(previous_values) / min(previous_values) - 1.0) * 100.0 > 0.05:
        raise RuntimeError(f"Trading Economics previous-value mismatch: {previous_values}")

    source_date = parse_te_korean_source_date(raw_ko)
    price = statistics.median(actuals)
    previous = statistics.median(previous_values)
    observed = core.now_utc()
    return core.Quote(
        key="ttf",
        symbol="TE:EU-GAS",
        label="Trading Economics EU Gas(TTF 추종 공개값)",
        unit="유로/MWh",
        price=price,
        previous_close=previous,
        change_pct=(price / previous - 1.0) * 100.0,
        timestamp_epoch=observed.timestamp(),
        timestamp_utc=observed.isoformat(timespec="seconds"),
        age_minutes=0,
        source_note=(
            "Trading Economics 한글·영문 페이지 actual/previous 및 내부 시세표 대조; "
            f"기준일={source_date}"
        ),
    )


def fetch_market_quotes_v5() -> tuple[dict[str, core.Quote], list[str]]:
    quotes: dict[str, core.Quote] = {}
    errors: list[str] = []
    try:
        quotes["ttf"] = fetch_te_ttf_quote_v5()
    except Exception as exc:
        errors.append(f"ttf: {type(exc).__name__}: {exc}")
    try:
        quotes["brent"] = strict.fetch_verified_quote_strict("brent")
    except Exception as exc:
        errors.append(f"brent: {type(exc).__name__}: {exc}")
    return quotes, errors


def format_quote_v5(quote: core.Quote) -> str:
    observed_kst = dt.datetime.fromtimestamp(quote.timestamp_epoch, core.UTC).astimezone(core.KST)
    if quote.key == "ttf":
        match = re.search(r"기준일=(\d{4}-\d{2}-\d{2})", quote.source_note)
        if not match:
            raise RuntimeError("TTF 기준일 없는 값은 출력하지 않음")
        source_date = match.group(1)
        return (
            f"{quote.label} {quote.price:,.2f}{quote.unit} "
            f"(이전값 {quote.previous_close:,.2f} 대비 {quote.change_pct:+.2f}%, "
            f"기준일 {source_date}, 조회 {observed_kst:%Y-%m-%d %H:%M KST})"
        )
    return te.format_quote_v4(quote)


def build_setup_test_v5(quotes: dict[str, core.Quote]):
    title, body, metadata = te.build_setup_test_v4(quotes)
    title = "✅ LNG·천연가스 감시 정확도 규칙 v5 적용"
    body += (
        "\n• TTF는 Trading Economics의 실제 데이터 기준일과 웹 조회시각을 반드시 분리 표기"
        "\n• 기준일을 파싱하지 못하면 TTF 숫자를 출력하지 않고 검증 실패로 보류"
    )
    metadata["version"] = 5
    metadata["ttf_requires_source_date"] = True
    return title, body, metadata


core.fetch_market_quotes = fetch_market_quotes_v5
core.format_quote = format_quote_v5
core.signal_label = te.signal_label_v4
core.build_setup_test = build_setup_test_v5


if __name__ == "__main__":
    raise SystemExit(core.main())

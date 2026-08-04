#!/usr/bin/env python3
"""LNG 공급 위기 감시 v4: TTF는 사용자가 지정한 Trading Economics 페이지를 우선 사용한다."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import re
import statistics
import time
import urllib.request

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v3 as strict

TE_TTF_URLS = (
    "https://ko.tradingeconomics.com/commodity/eu-natural-gas",
    "https://tradingeconomics.com/commodity/eu-natural-gas",
)
TE_MAX_INTERNAL_GAP_PCT = 0.20
TE_MAX_CROSS_PAGE_GAP_PCT = 0.20


def fetch_te_html(url: str) -> str:
    request = urllib.request.Request(
        f"{url}?v={int(time.time())}",
        headers={
            "User-Agent": "Mozilla/5.0 khs-lng-supply-crisis-alert/4.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def visible_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def number(value: str) -> float:
    return float(value.replace(",", "").strip())


def parse_te_ttf(raw_html: str) -> dict[str, float]:
    text = visible_text(raw_html)

    stats_patterns = (
        r"실제\s+이전\s+최고\s+최저\s+날짜\s+단위\s+업데이트\s*주기\s+([0-9.,]+)\s+([0-9.,]+)",
        r"Actual\s+Previous\s+Highest\s+Lowest\s+Dates\s+Unit\s+Frequency\s+([0-9.,]+)\s+([0-9.,]+)",
    )
    actual = previous = None
    for pattern in stats_patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            actual, previous = number(match.group(1)), number(match.group(2))
            break
    if actual is None or previous is None or previous <= 0:
        raise RuntimeError("Trading Economics actual/previous table not found")

    row_patterns = (
        r"(?:유럽연합 가스|유럽의 천연가스|EU 가스)\s+([0-9.,]+)\s+([+-]?[0-9.,]+)\s+([+-]?[0-9.,]+)%",
        r"(?:European Union Gas|EU Natural Gas|EU Gas)\s+([0-9.,]+)\s+([+-]?[0-9.,]+)\s+([+-]?[0-9.,]+)%",
    )
    row_values: list[tuple[float, float]] = []
    for pattern in row_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            row_values.append((number(match.group(1)), number(match.group(3))))

    calculated_pct = (actual / previous - 1.0) * 100.0
    coherent_rows = [
        (price, pct)
        for price, pct in row_values
        if abs(price / actual - 1.0) * 100.0 <= TE_MAX_INTERNAL_GAP_PCT
        and abs(pct - calculated_pct) <= 0.25
    ]
    if not coherent_rows:
        raise RuntimeError(
            "Trading Economics internal values disagree: "
            f"actual={actual}, previous={previous}, calculated_pct={calculated_pct:.2f}"
        )

    return {
        "actual": actual,
        "previous": previous,
        "change_pct": calculated_pct,
        "row_price_median": statistics.median(price for price, _ in coherent_rows),
    }


def fetch_te_ttf_quote() -> core.Quote:
    snapshots: list[dict[str, float]] = []
    for url in TE_TTF_URLS:
        snapshots.append(parse_te_ttf(fetch_te_html(url)))

    actuals = [item["actual"] for item in snapshots]
    previous_values = [item["previous"] for item in snapshots]
    if (max(actuals) / min(actuals) - 1.0) * 100.0 > TE_MAX_CROSS_PAGE_GAP_PCT:
        raise RuntimeError(f"Trading Economics Korean/English page mismatch: {actuals}")
    if (max(previous_values) / min(previous_values) - 1.0) * 100.0 > 0.05:
        raise RuntimeError(f"Trading Economics previous-value mismatch: {previous_values}")

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
        source_note="Trading Economics 한글·영문 페이지 actual/previous 및 내부 시세표 대조",
    )


def fetch_market_quotes_v4() -> tuple[dict[str, core.Quote], list[str]]:
    quotes: dict[str, core.Quote] = {}
    errors: list[str] = []
    try:
        quotes["ttf"] = fetch_te_ttf_quote()
    except Exception as exc:
        errors.append(f"ttf: {type(exc).__name__}: {exc}")
    try:
        quotes["brent"] = strict.fetch_verified_quote_strict("brent")
    except Exception as exc:
        errors.append(f"brent: {type(exc).__name__}: {exc}")
    return quotes, errors


def format_quote_v4(quote: core.Quote) -> str:
    observed_kst = dt.datetime.fromtimestamp(quote.timestamp_epoch, core.UTC).astimezone(core.KST)
    basis = "이전값" if quote.key == "ttf" else "Yahoo 이전 종가"
    return (
        f"{quote.label} {quote.price:,.2f}{quote.unit} "
        f"({basis} {quote.previous_close:,.2f} 대비 {quote.change_pct:+.2f}%, "
        f"조회 {observed_kst:%Y-%m-%d %H:%M KST})"
    )


def signal_label_v4(signal: str, cleared: bool = False) -> str:
    labels = {
        "ttf_up_5": "Trading Economics TTF 추종값 이전값 대비 +5% 이상",
        "ttf_down_5": "Trading Economics TTF 추종값 이전값 대비 -5% 이하",
        "ttf_above_50": "Trading Economics TTF 추종값 50유로/MWh 상회",
        "ttf_above_60": "Trading Economics TTF 추종값 60유로/MWh 상회",
        "ttf_above_70": "Trading Economics TTF 추종값 70유로/MWh 상회",
        "ttf_above_80": "Trading Economics TTF 추종값 80유로/MWh 상회",
    }
    if signal in labels:
        return f"{labels[signal]} 종료" if cleared else labels[signal]
    return core.signal_label(signal, cleared)


def build_setup_test_v4(quotes: dict[str, core.Quote]):
    title, body, metadata = strict.build_setup_test_v3(quotes)
    title = "✅ LNG·천연가스 감시 정확도 규칙 v4 적용"
    body += (
        "\n• TTF는 지정 페이지 Trading Economics EU Gas 값을 최우선 사용"
        "\n• 한글·영문 페이지의 실제값·이전값과 내부 시세표가 허용오차 안에서 일치할 때만 반영"
        "\n• 페이지 내부 값이 어긋나면 숫자를 보내지 않고 '검증 실패'로 보류"
        "\n• 표기는 ICE 공식 실시간 TTF가 아니라 Trading Economics TTF 추종 공개값으로 명시"
    )
    metadata["version"] = 4
    metadata["ttf_primary_source"] = TE_TTF_URLS[0]
    return title, body, metadata


core.fetch_market_quotes = fetch_market_quotes_v4
core.format_quote = format_quote_v4
core.signal_label = signal_label_v4
core.build_setup_test = build_setup_test_v4


if __name__ == "__main__":
    raise SystemExit(core.main())

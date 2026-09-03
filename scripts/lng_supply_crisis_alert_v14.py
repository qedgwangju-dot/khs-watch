#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import math
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v13 as v13

UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")
YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)
FX_SYMBOLS = {
    "CAD": "CADKRW=X",
    "USD": "KRW=X",       # USD/KRW
    "EUR": "EURKRW=X",
    "JPY": "JPYKRW=X",
}
FX_NAMES_KO = {
    "CAD": "캐나다달러",
    "USD": "미국달러",
    "EUR": "유로",
    "JPY": "엔",
}


def _now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def _finite(value) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise RuntimeError("invalid FX value")
    return number


def _fetch_fx_endpoint(symbol: str, base: str) -> tuple[float, float]:
    encoded = urllib.parse.quote(symbol, safe="")
    params = urllib.parse.urlencode({"interval": "5m", "range": "1d", "includePrePost": "true"})
    req = urllib.request.Request(
        f"{base}/{encoded}?{params}",
        headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("chart", {}).get("result")
    if not result:
        raise RuntimeError(f"{symbol}: no result")
    meta = result[0].get("meta", {})
    price = _finite(meta.get("regularMarketPrice"))
    ts = _finite(meta.get("regularMarketTime"))
    return price, ts


def _fx_max_age() -> dt.timedelta:
    # 주말·월요일 아시아장 초반에는 직전 금요일 종가를 허용하되, 평일 장중은 오래된 값 사용 금지.
    now_kst = _now_utc().astimezone(KST)
    if now_kst.weekday() in (5, 6):
        return dt.timedelta(hours=84)
    if now_kst.weekday() == 0 and now_kst.hour < 9:
        return dt.timedelta(hours=84)
    return dt.timedelta(minutes=120)


def fetch_verified_fx(currency: str) -> dict[str, object]:
    symbol = FX_SYMBOLS[currency]
    first = _fetch_fx_endpoint(symbol, YAHOO_BASES[0])
    second = _fetch_fx_endpoint(symbol, YAHOO_BASES[1])
    price_gap = abs(first[0] - second[0]) / max(first[0], second[0])
    time_gap = abs(first[1] - second[1])
    if price_gap > 0.0005 or time_gap > 60:
        raise RuntimeError(f"{symbol}: endpoint mismatch price={price_gap:.4%} time={time_gap:.0f}s")
    observed = dt.datetime.fromtimestamp(first[1], UTC)
    age = _now_utc() - observed
    if age < dt.timedelta(0) or age > _fx_max_age():
        raise RuntimeError(f"{symbol}: stale FX age={age.total_seconds()/60:.0f}m")
    return {
        "currency": currency,
        "symbol": symbol,
        "rate": first[0],
        "timestamp_utc": observed.isoformat(timespec="seconds"),
        "timestamp_kst": observed.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
        "source": "Yahoo Finance 동일 제공사 2엔드포인트 검산",
    }


def format_krw(amount_krw: float) -> str:
    # 투자 알림 가독성을 위해 억원 단위 반올림, 1조원 이상은 조+억원 병기.
    eok = int(round(amount_krw / 100_000_000))
    if eok >= 10_000:
        jo, rem = divmod(eok, 10_000)
        return f"약 {jo}조{rem:,}억원" if rem else f"약 {jo}조원"
    return f"약 {eok:,}억원"


def convert_to_krw(amount: float, currency: str, fx: dict[str, object]) -> tuple[float, str]:
    rate = float(fx["rate"])
    krw = amount * rate
    return krw, format_krw(krw)


def build_regular_alert_v14(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v13.build_regular_alert_v13(groups, quotes, new_signals, cleared_signals)

    evidence_text = " ".join(
        f"{item.title} {item.source}"
        for group in groups
        for item in group.get("evidence", [])
    ).lower()
    manitoba_case = (
        "manitoba" in evidence_text
        or "매니토바" in evidence_text
        or "trade war complicates hydro plan to purchase gas turbines" in evidence_text
    )
    turbine_case = (
        "gas turbine" in evidence_text
        or "gas turbines" in evidence_text
        or "가스터빈" in evidence_text
        or "ge vernova" in evidence_text
    )

    fx_used: dict[str, object] = {}
    fx_errors: dict[str, str] = {}

    if manitoba_case and turbine_case:
        try:
            cad = fetch_verified_fx("CAD")
            fx_used["CADKRW"] = cad
            krw_value, krw_label = convert_to_krw(3_000_000_000.0, "CAD", cad)
            body = body.replace(
                "총 <b>30억 캐나다달러</b> 규모",
                f"총 <b>30억 캐나다달러 ({krw_label})</b> 규모",
            )
            rate = float(cad["rate"])
            fx_line = (
                f"• <b>원화 환산</b> 1캐나다달러 = <b>{rate:,.2f}원</b> · "
                f"30억 × {rate:,.2f}원 = <b>{krw_value:,.0f}원</b> · 기준 {cad['timestamp_kst']}"
            )
            marker = "• <b>장비</b> 가스터빈 <b>3기</b>"
            lines = body.splitlines()
            try:
                idx = lines.index(marker)
                lines.insert(idx, fx_line)
                body = "\n".join(lines)
            except ValueError:
                body += "\n" + fx_line
        except Exception as exc:
            fx_errors["CADKRW"] = f"{type(exc).__name__}: {exc}"
            body = body.replace(
                "총 <b>30억 캐나다달러</b> 규모",
                "총 <b>30억 캐나다달러</b> 규모 · <b>원화 환산 보류</b>(환율 검증 실패)",
            )

    metadata["version"] = 14
    metadata["krw_conversion_policy"] = {
        "rule": "foreign amount preserved + verified KRW amount appended",
        "required_fields": ["원통화 금액", "원화 환산", "적용 환율", "환율 기준시각", "계산식"],
        "on_failure": "원통화는 유지하고 원화 환산 보류; 임의 환산 금지",
        "fx_source": "Yahoo Finance same-provider two-endpoint validation",
        "max_endpoint_value_gap": "0.05%",
        "max_endpoint_time_gap": "60s",
    }
    metadata["fx_used"] = fx_used
    metadata["fx_errors"] = fx_errors
    return title, body, metadata


def build_setup_test_v14(quotes):
    title, body, metadata = v13.build_setup_test_v13(quotes)
    title = "✅ LNG·전력 인프라 감시 원화 환산 규칙 v14 적용"
    body += (
        "\n\n<b>통화 표기</b>"
        "\n• 외화 금액은 원통화를 삭제하지 않고 원화 환산액을 함께 표시"
        "\n• 적용 환율·환율 기준시각(KST)·계산식까지 표시"
        "\n• 동일 제공사 2엔드포인트 값/시각 검산을 통과한 환율만 사용"
        "\n• 환율 검증 실패 시 임의 환산하지 않고 '원화 환산 보류' 표시"
    )
    metadata["version"] = 14
    return title, body, metadata


core.fetch_news_item_set = v13.v12.v11.v10.fetch_news_item_set_v10
core.confirmed_news_groups = v13.v12.confirmed_news_groups_v12
core.category_label = v13.v12.category_label_v12
core.classify_polarity = v13.v12.classify_polarity_v12
core.classify_alert_context = v13.v12.classify_alert_context_v12
core.impact_text = v13.v12.impact_text_v12
core.fetch_market_quotes = v13.v12.v11.v9.v8.v7.fetch_market_quotes_v7
core.format_quote = v13.v12.v11.v9.v8.v7.v6.format_quote_v6
core.signal_label = v13.v12.v11.v9.signal_label_v9
core.build_regular_alert = build_regular_alert_v14
core.build_setup_test = build_setup_test_v14

if __name__ == "__main__":
    raise SystemExit(core.main())

#!/usr/bin/env python3
"""엔캐리 청산 위험을 확인하고 Telegram 전송용 파일을 생성한다.

외부 패키지 없이 GitHub Actions에서 실행하도록 작성했다.
기본 시장 데이터는 Yahoo Finance 차트 엔드포인트를 사용한다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
STATE_PATH = pathlib.Path("data/yen_carry_alert_state.json")
OUT_DIR = pathlib.Path("out")
ALERT_TITLE_PATH = OUT_DIR / "yen_carry_alert_title.txt"
ALERT_BODY_PATH = OUT_DIR / "yen_carry_alert.md"
ALERT_JSON_PATH = OUT_DIR / "yen_carry_alert.json"
SUMMARY_PATH = OUT_DIR / "yen_carry_watch.md"
PENDING_STATE_PATH = OUT_DIR / "yen_carry_pending_state.json"
TELEGRAM_CONFIRMED_PATH = OUT_DIR / "yen_carry_telegram_confirmed.json"

YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    label: str
    kind: str


@dataclass(frozen=True)
class Quote:
    symbol: str
    label: str
    kind: str
    price: float
    previous_close: float
    change_pct: float
    timestamp_utc: str
    timestamp_epoch: float


SYMBOLS = {
    "usd_jpy": SymbolSpec("JPY=X", "USD/JPY", "환율"),
    "nasdaq_cash": SymbolSpec("^IXIC", "Nasdaq Composite", "현물"),
    "nikkei_cash": SymbolSpec("^N225", "Nikkei 225", "현물"),
    "nasdaq_future": SymbolSpec("NQ=F", "Nasdaq 100 선물", "선물"),
    "nikkei_future_1": SymbolSpec("NIY=F", "Nikkei 225 엔화 선물", "선물"),
    "nikkei_future_2": SymbolSpec("NKD=F", "Nikkei 225 달러 선물", "선물"),
}


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_json(url: str, timeout: int = 20, attempts: int = 3) -> dict:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 yen-carry-alert/1.0",
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"시장 데이터 요청 실패: {last_error}")


def last_finite_point(timestamps: list, closes: list) -> tuple[float, float] | None:
    for timestamp, close in reversed(list(zip(timestamps, closes))):
        ts_value = finite_number(timestamp)
        close_value = finite_number(close)
        if ts_value is not None and close_value is not None:
            return ts_value, close_value
    return None


def parse_yahoo_payload(payload: dict, spec: SymbolSpec) -> Quote:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        error = chart.get("error") or {}
        raise RuntimeError(f"{spec.symbol} 데이터 없음: {error.get('description', 'unknown')}")

    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote_rows = indicators.get("quote") or []
    closes = quote_rows[0].get("close", []) if quote_rows else []
    last_point = last_finite_point(timestamps, closes)

    price = finite_number(meta.get("regularMarketPrice"))
    if price is None and last_point:
        price = last_point[1]

    previous_close = (
        finite_number(meta.get("chartPreviousClose"))
        or finite_number(meta.get("previousClose"))
        or finite_number(meta.get("regularMarketPreviousClose"))
    )

    timestamp = finite_number(meta.get("regularMarketTime"))
    if timestamp is None and last_point:
        timestamp = last_point[0]

    if price is None or previous_close is None or previous_close == 0 or timestamp is None:
        raise RuntimeError(f"{spec.symbol} 핵심 값 누락")

    observed = dt.datetime.fromtimestamp(timestamp, tz=UTC)
    return Quote(
        symbol=spec.symbol,
        label=spec.label,
        kind=spec.kind,
        price=price,
        previous_close=previous_close,
        change_pct=((price - previous_close) / previous_close) * 100,
        timestamp_utc=observed.isoformat().replace("+00:00", "Z"),
        timestamp_epoch=timestamp,
    )


def fetch_quote(spec: SymbolSpec) -> Quote:
    params = urllib.parse.urlencode(
        {
            "interval": os.getenv("YEN_CARRY_YAHOO_INTERVAL", "5m"),
            "range": os.getenv("YEN_CARRY_YAHOO_RANGE", "5d"),
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    errors: list[str] = []
    for base in YAHOO_BASES:
        url = f"{base}/{urllib.parse.quote(spec.symbol, safe='')}?{params}"
        try:
            return parse_yahoo_payload(fetch_json(url), spec)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(f"{spec.symbol} 조회 실패: {' | '.join(errors)}")


def age_minutes(quote: Quote, current: dt.datetime) -> float:
    return max(0.0, (current.timestamp() - quote.timestamp_epoch) / 60.0)


def is_fresh(quote: Quote | None, current: dt.datetime, max_age_minutes: int) -> bool:
    return quote is not None and age_minutes(quote, current) <= max_age_minutes


def choose_cash_or_future(
    cash: Quote | None,
    futures: Iterable[Quote | None],
    current: dt.datetime,
    cash_fresh_minutes: int,
    max_age_minutes: int,
) -> Quote | None:
    if is_fresh(cash, current, cash_fresh_minutes):
        return cash

    fresh_futures = [
        quote for quote in futures if quote is not None and is_fresh(quote, current, max_age_minutes)
    ]
    if fresh_futures:
        return max(fresh_futures, key=lambda quote: quote.timestamp_epoch)

    if is_fresh(cash, current, max_age_minutes):
        return cash
    return None


def determine_stage(usd_jpy: float, nasdaq_pct: float, nikkei_pct: float) -> int:
    if usd_jpy <= 152.0 and nasdaq_pct <= -3.0 and nikkei_pct <= -3.0:
        return 2
    if usd_jpy <= 154.0 and nasdaq_pct <= -2.0 and nikkei_pct <= -2.0:
        return 1
    return 0


def load_state(path: pathlib.Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"stage": 0, "last_alert_at_kst": None}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"stage": 0, "last_alert_at_kst": None}
    stage = value.get("stage")
    value["stage"] = stage if stage in (1, 2) else 0
    return value


def clean_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        ALERT_TITLE_PATH,
        ALERT_BODY_PATH,
        ALERT_JSON_PATH,
        PENDING_STATE_PATH,
        TELEGRAM_CONFIRMED_PATH,
    ):
        path.unlink(missing_ok=True)


def fmt_pct(value: float) -> str:
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.2f}%"


def fmt_kst(current: dt.datetime) -> str:
    return current.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def build_alert_body(stage: int, usd_jpy: Quote, nasdaq: Quote, nikkei: Quote, current: dt.datetime) -> str:
    if stage == 2:
        judgment = (
            "USD/JPY 152엔 이하와 양 지수 -3% 이상 하락이 겹쳤습니다. "
            "본격적인 엔캐리 언와인드와 강제 위험축소 가능성이 높아진 구간입니다."
        )
        effects = (
            "한국 증시: 외국인 선물·현물 동반 매도와 원화 약세가 겹칠 수 있음",
            "반도체: 고베타·레버리지 축소로 단기 낙폭 확대 위험",
            "가상자산: 증거금 축소와 달러 유동성 회수로 변동성 급등 가능",
        )
        threshold = "152엔·양 지수 -3%"
    else:
        judgment = (
            "USD/JPY 154엔 이하와 양 지수 -2% 이상 하락이 겹쳤습니다. "
            "엔 숏커버와 부분적인 엔캐리 청산 가능성이 커진 구간입니다."
        )
        effects = (
            "한국 증시: 장 초반 외국인 위험축소 여부 확인 필요",
            "반도체: 실적보다 수급 요인으로 변동성 확대 가능",
            "가상자산: 부분 청산이 번질 경우 동반 약세 가능",
        )
        threshold = "154엔·양 지수 -2%"

    lines = [
        f"조회 시각: {fmt_kst(current)}",
        f"USD/JPY: {usd_jpy.price:.3f} ({fmt_pct(usd_jpy.change_pct)})",
        f"{nasdaq.label}({nasdaq.kind}): {fmt_pct(nasdaq.change_pct)}",
        f"{nikkei.label}({nikkei.kind}): {fmt_pct(nikkei.change_pct)}",
        "",
        f"판정: {judgment}",
        "",
        "단기 영향",
        *(f"• {item}" for item in effects),
        "",
        f"기준 충족: {threshold}",
        "같은 단계가 유지되는 동안에는 중복 알림하지 않습니다.",
    ]
    return "\n".join(lines)


def build_test_body(quotes: dict[str, Quote | None], errors: dict[str, str], current: dt.datetime) -> str:
    lines = [
        f"조회 시각: {fmt_kst(current)}",
        "텔레그램 경보 연결 시험입니다. 실제 위험 조건 충족 알림이 아닙니다.",
        "",
    ]
    for key in ("usd_jpy", "nasdaq_cash", "nikkei_cash"):
        quote = quotes.get(key)
        if quote:
            lines.append(f"{quote.label}({quote.kind}): {quote.price:,.3f} / {fmt_pct(quote.change_pct)}")
        else:
            lines.append(f"{SYMBOLS[key].label}: 조회 실패 — {errors.get(key, 'unknown')}")
    lines.extend(
        [
            "",
            "정상 경보 기준",
            "• 1단계: USD/JPY 154 이하 + Nasdaq·Nikkei 각각 -2% 이하",
            "• 2단계: USD/JPY 152 이하 + Nasdaq·Nikkei 각각 -3% 이하",
        ]
    )
    return "\n".join(lines)


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_summary(
    current: dt.datetime,
    stage: int | None,
    previous_stage: int,
    usd_jpy: Quote | None,
    nasdaq: Quote | None,
    nikkei: Quote | None,
    errors: dict[str, str],
    status: str,
) -> None:
    def quote_line(label: str, quote: Quote | None) -> str:
        if quote is None:
            return f"- {label}: 확인 실패"
        return f"- {quote.label}({quote.kind}): {quote.price:,.3f}, {fmt_pct(quote.change_pct)}, 기준시각 {quote.timestamp_utc}"

    lines = [
        "# 엔캐리 청산 경보 점검",
        "",
        f"- 조회 시각: {fmt_kst(current)}",
        f"- 상태: {status}",
        f"- 직전 단계: {previous_stage}",
        f"- 현재 단계: {'판정 보류' if stage is None else stage}",
        quote_line("USD/JPY", usd_jpy),
        quote_line("Nasdaq", nasdaq),
        quote_line("Nikkei", nikkei),
    ]
    if errors:
        lines.extend(["", "## 조회 오류", *(f"- {key}: {value}" for key, value in sorted(errors.items()))])
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    current: dt.datetime | None = None,
    fetcher: Callable[[SymbolSpec], Quote] = fetch_quote,
    state_path: pathlib.Path = STATE_PATH,
    telegram_test: bool = False,
) -> dict:
    current = current or now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    clean_outputs()

    quotes: dict[str, Quote | None] = {}
    errors: dict[str, str] = {}
    for key, spec in SYMBOLS.items():
        try:
            quotes[key] = fetcher(spec)
        except Exception as exc:
            quotes[key] = None
            errors[key] = str(exc)

    state = load_state(state_path)
    previous_stage = int(state.get("stage", 0))

    if telegram_test:
        title = "✅ 엔캐리 청산 경보 연결 시험"
        body = build_test_body(quotes, errors, current)
        ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
        write_json(ALERT_JSON_PATH, {"test": True, "title": title, "body": body})
        write_summary(current, previous_stage, previous_stage, quotes.get("usd_jpy"), quotes.get("nasdaq_cash"), quotes.get("nikkei_cash"), errors, "연결 시험 메시지 생성")
        return {"stage": previous_stage, "previous_stage": previous_stage, "alerted": True, "test": True}

    max_age_minutes = int(os.getenv("YEN_CARRY_MAX_DATA_AGE_MINUTES", "240"))
    cash_fresh_minutes = int(os.getenv("YEN_CARRY_CASH_FRESH_MINUTES", "150"))

    usd_jpy = quotes.get("usd_jpy")
    nasdaq = choose_cash_or_future(
        quotes.get("nasdaq_cash"),
        [quotes.get("nasdaq_future")],
        current,
        cash_fresh_minutes,
        max_age_minutes,
    )
    nikkei = choose_cash_or_future(
        quotes.get("nikkei_cash"),
        [quotes.get("nikkei_future_1"), quotes.get("nikkei_future_2")],
        current,
        cash_fresh_minutes,
        max_age_minutes,
    )

    missing: list[str] = []
    if not is_fresh(usd_jpy, current, max_age_minutes):
        missing.append("USD/JPY")
        usd_jpy = None
    if nasdaq is None:
        missing.append("Nasdaq 현물·선물")
    if nikkei is None:
        missing.append("Nikkei 현물·선물")

    if missing:
        errors["신선도"] = ", ".join(missing)
        write_summary(current, None, previous_stage, usd_jpy, nasdaq, nikkei, errors, "데이터 누락·지연으로 판정 보류")
        return {"stage": None, "previous_stage": previous_stage, "alerted": False, "missing": missing}

    assert usd_jpy is not None and nasdaq is not None and nikkei is not None
    stage = determine_stage(usd_jpy.price, nasdaq.change_pct, nikkei.change_pct)
    should_alert = stage > 0 and (previous_stage == 0 or stage > previous_stage)

    if stage != previous_stage:
        pending_state = {
            "stage": stage,
            "updated_at_kst": fmt_kst(current),
            "last_alert_at_kst": fmt_kst(current) if should_alert else state.get("last_alert_at_kst"),
            "last_values": {
                "usd_jpy": round(usd_jpy.price, 4),
                "nasdaq_pct": round(nasdaq.change_pct, 3),
                "nikkei_pct": round(nikkei.change_pct, 3),
                "nasdaq_source": f"{nasdaq.label}({nasdaq.kind})",
                "nikkei_source": f"{nikkei.label}({nikkei.kind})",
            },
        }
        write_json(PENDING_STATE_PATH, pending_state)

    if should_alert:
        title = "🚨 엔캐리 청산 2단계 위험" if stage == 2 else "⚠️ 엔캐리 청산 1단계 경계"
        body = build_alert_body(stage, usd_jpy, nasdaq, nikkei, current)
        ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
        write_json(
            ALERT_JSON_PATH,
            {
                "test": False,
                "stage": stage,
                "previous_stage": previous_stage,
                "title": title,
                "body": body,
                "usd_jpy": asdict(usd_jpy),
                "nasdaq": asdict(nasdaq),
                "nikkei": asdict(nikkei),
            },
        )

    status = "경보 생성" if should_alert else ("단계 변경·무경보" if stage != previous_stage else "조건 미충족 또는 단계 유지")
    write_summary(current, stage, previous_stage, usd_jpy, nasdaq, nikkei, errors, status)
    return {"stage": stage, "previous_stage": previous_stage, "alerted": should_alert, "test": False}


def finalize_state(state_path: pathlib.Path = STATE_PATH) -> bool:
    if not PENDING_STATE_PATH.exists():
        return False
    alert_required = ALERT_BODY_PATH.exists()
    if alert_required and not TELEGRAM_CONFIRMED_PATH.exists():
        print("Telegram confirmation missing; pending state not finalized.")
        return False
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(PENDING_STATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Finalized state: {state_path}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true", help="Telegram 전송 확인 후 pending state를 확정")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.finalize:
        finalize_state()
        return 0
    telegram_test = os.getenv("TELEGRAM_TEST", "false").strip().lower() == "true"
    result = run(telegram_test=telegram_test)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

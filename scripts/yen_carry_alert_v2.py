#!/usr/bin/env python3
"""Accurate runner and formatter for the yen-carry Telegram alert."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yen_carry_alert as legacy
from yen_carry_market_data_v2 import fetch_quote

KST = ZoneInfo("Asia/Seoul")


def fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def fmt_price(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}"


def timestamp_kst(value: str) -> str:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def fetch_all() -> tuple[dict[str, legacy.Quote | None], dict[str, str]]:
    quotes: dict[str, legacy.Quote | None] = {}
    errors: dict[str, str] = {}
    for key, spec in legacy.SYMBOLS.items():
        try:
            quotes[key] = fetch_quote(spec)
        except Exception as exc:
            quotes[key] = None
            errors[key] = f"{type(exc).__name__}: {exc}"
    return quotes, errors


def quote_line(quote: legacy.Quote | None, fallback: str, *, fx: bool = False) -> str:
    if quote is None:
        return f"- {fallback}: 확인 실패"
    decimals = 3 if fx else 2
    if fx:
        return (
            f"- USD/JPY: {fmt_price(quote.price, decimals)}\n"
            f"  기준시각: {timestamp_kst(quote.timestamp_utc)}"
        )
    return (
        f"- {quote.label}({quote.kind}): {fmt_price(quote.price, decimals)} "
        f"(직전 거래일 대비 {fmt_pct(quote.change_pct)})\n"
        f"  기준시각: {timestamp_kst(quote.timestamp_utc)}"
    )


def write_test_message() -> dict:
    current = dt.datetime.now(dt.timezone.utc)
    quotes, errors = fetch_all()
    title = "✅ 엔캐리 청산 경보 연결 시험"
    lines = [
        "1. [엔캐리 연결 시험] 텔레그램 채널 경보 연결을 확인합니다.",
        f"조회 시각: {current.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "실제 위험 조건 충족 알림이 아니라 연결 시험입니다.",
        "",
        quote_line(quotes.get("usd_jpy"), "USD/JPY", fx=True),
        quote_line(quotes.get("nasdaq_cash"), "Nasdaq Composite"),
        quote_line(quotes.get("nikkei_cash"), "Nikkei 225"),
        "",
        "정상 경보 기준",
        "- 1단계: USD/JPY 154.00 이하 + Nasdaq·Nikkei 각각 -2.00% 이하",
        "- 2단계: USD/JPY 152.00 이하 + Nasdaq·Nikkei 각각 -3.00% 이하",
        "- 같은 단계 유지 중에는 중복 알림하지 않음",
        "- 조건 해제 뒤 재진입하거나 상위 단계로 악화되면 재알림",
        "",
        "검증 방식",
        "- 현물 지수: 최신 거래일 종가와 직전 거래일 종가를 직접 비교",
        "- USD/JPY: 정확히 24시간 전 시점과 비교",
        "- Yahoo query1·query2 값 불일치 시 송출 보류",
    ]
    if errors:
        lines.extend(["", "데이터 오류", *(f"- {key}: {value}" for key, value in sorted(errors.items()))])

    body = "\n".join(lines)
    legacy.OUT_DIR.mkdir(parents=True, exist_ok=True)
    legacy.ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    legacy.ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
    legacy.write_json(
        legacy.ALERT_JSON_PATH,
        {
            "test": True,
            "title": title,
            "body": body,
            "quotes": {
                key: (vars(value) if value is not None else None)
                for key, value in quotes.items()
            },
            "errors": errors,
        },
    )
    legacy.write_summary(
        current,
        0,
        0,
        quotes.get("usd_jpy"),
        quotes.get("nasdaq_cash"),
        quotes.get("nikkei_cash"),
        errors,
        "정확도 개선 연결 시험 메시지 생성",
    )
    return {"test": True, "alerted": True, "errors": errors}


def rewrite_real_alert() -> None:
    if not legacy.ALERT_JSON_PATH.exists() or not legacy.ALERT_BODY_PATH.exists():
        return
    data = json.loads(legacy.ALERT_JSON_PATH.read_text(encoding="utf-8"))
    if data.get("test"):
        return

    stage = int(data.get("stage", 0))
    usd = data.get("usd_jpy") or {}
    nasdaq = data.get("nasdaq") or {}
    nikkei = data.get("nikkei") or {}

    if stage == 2:
        judgment = (
            "USD/JPY 152.00 이하와 Nasdaq·Nikkei 각각 -3.00% 이하가 동시에 충족됐습니다. "
            "본격적인 엔캐리 언와인드와 강제 위험축소 가능성이 높아진 구간입니다."
        )
        effects = (
            "한국 증시: 외국인 선물·현물 동반 매도와 원화 약세가 겹칠 수 있음",
            "반도체: 고베타·레버리지 축소로 단기 낙폭 확대 위험",
            "가상자산: 증거금 축소와 달러 유동성 회수로 변동성 급등 가능",
        )
    else:
        judgment = (
            "USD/JPY 154.00 이하와 Nasdaq·Nikkei 각각 -2.00% 이하가 동시에 충족됐습니다. "
            "엔 숏커버와 부분적인 엔캐리 청산 가능성이 커진 구간입니다."
        )
        effects = (
            "한국 증시: 외국인 위험축소와 선물 수급 확인 필요",
            "반도체: 실적보다 수급 요인으로 단기 변동성 확대 가능",
            "가상자산: 위험축소가 번질 경우 동반 약세 가능",
        )

    now = dt.datetime.now(dt.timezone.utc).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    lines = [
        f"조회 시각: {now}",
        f"USD/JPY: {float(usd['price']):.3f}",
        f"  기준시각: {timestamp_kst(str(usd['timestamp_utc']))}",
        (
            f"{nasdaq['label']}({nasdaq['kind']}): {float(nasdaq['price']):,.2f} "
            f"(직전 거래일 대비 {fmt_pct(float(nasdaq['change_pct']))})"
        ),
        f"  기준시각: {timestamp_kst(str(nasdaq['timestamp_utc']))}",
        (
            f"{nikkei['label']}({nikkei['kind']}): {float(nikkei['price']):,.2f} "
            f"(직전 거래일 대비 {fmt_pct(float(nikkei['change_pct']))})"
        ),
        f"  기준시각: {timestamp_kst(str(nikkei['timestamp_utc']))}",
        "",
        f"판정: {judgment}",
        "",
        "단기 영향",
        *(f"• {item}" for item in effects),
        "",
        "같은 단계가 유지되는 동안에는 중복 알림하지 않습니다.",
    ]
    body = "\n".join(lines)
    legacy.ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
    data["body"] = body
    legacy.write_json(legacy.ALERT_JSON_PATH, data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()

    if args.finalize:
        legacy.finalize_state()
        return 0

    telegram_test = os.getenv("TELEGRAM_TEST", "false").strip().lower() == "true"
    if telegram_test:
        result = write_test_message()
    else:
        result = legacy.run(fetcher=fetch_quote, telegram_test=False)
        rewrite_real_alert()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

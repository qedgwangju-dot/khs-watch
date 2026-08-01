#!/usr/bin/env python3
"""Bridge yen-carry risk alerts into the confirmed KHS Telegram delivery lane.

The bridge writes its transition state into the existing Telegram delivery state
file. That file is committed only after the existing workflow confirms a
Telegram outcome, so a failed delivery is retried on the next scheduled run.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yen_carry_alert as market

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
OUT_DIR = Path("out")
DATA_DIR = Path("data")
DELIVERY_STATE_PATH = DATA_DIR / "khs_telegram_delivery_seen.json"
TITLE_PATH = OUT_DIR / "khs_policy_source_status_title.txt"
BODY_PATH = OUT_DIR / "khs_policy_source_status_alert.md"


def now_utc() -> dt.datetime:
    return dt.datetime.now(tz=UTC)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return value if isinstance(value, type(default)) else default


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fetch_quotes() -> tuple[dict[str, market.Quote | None], dict[str, str]]:
    quotes: dict[str, market.Quote | None] = {}
    errors: dict[str, str] = {}

    def fetch_one(item: tuple[str, market.SymbolSpec]):
        key, spec = item
        return key, market.fetch_quote(spec)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(market.SYMBOLS)) as executor:
        futures = {
            executor.submit(fetch_one, item): item[0]
            for item in market.SYMBOLS.items()
        }
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                _, quote = future.result()
                quotes[key] = quote
            except Exception as exc:
                quotes[key] = None
                errors[key] = f"{type(exc).__name__}: {exc}"
    return quotes, errors


def fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def fmt_price(value: float) -> str:
    return f"{value:,.2f}"


def fmt_kst(value: dt.datetime) -> str:
    return value.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def quote_line(quote: market.Quote | None, fallback: str) -> str:
    if quote is None:
        return f"- {fallback}: 확인 실패"
    return (
        f"- {quote.label}({quote.kind}): {fmt_price(quote.price)} "
        f"({fmt_pct(quote.change_pct)})"
    )


def choose_market_quotes(
    quotes: dict[str, market.Quote | None],
    current: dt.datetime,
) -> tuple[market.Quote | None, market.Quote | None, market.Quote | None, list[str]]:
    max_age_minutes = int(os.getenv("YEN_CARRY_MAX_DATA_AGE_MINUTES", "240"))
    cash_fresh_minutes = int(os.getenv("YEN_CARRY_CASH_FRESH_MINUTES", "150"))

    usd_jpy = quotes.get("usd_jpy")
    nasdaq = market.choose_cash_or_future(
        quotes.get("nasdaq_cash"),
        [quotes.get("nasdaq_future")],
        current,
        cash_fresh_minutes,
        max_age_minutes,
    )
    nikkei = market.choose_cash_or_future(
        quotes.get("nikkei_cash"),
        [quotes.get("nikkei_future_1"), quotes.get("nikkei_future_2")],
        current,
        cash_fresh_minutes,
        max_age_minutes,
    )

    missing: list[str] = []
    if not market.is_fresh(usd_jpy, current, max_age_minutes):
        usd_jpy = None
        missing.append("USD/JPY")
    if nasdaq is None:
        missing.append("Nasdaq 현물·선물")
    if nikkei is None:
        missing.append("Nikkei 현물·선물")
    return usd_jpy, nasdaq, nikkei, missing


def bootstrap_message(
    quotes: dict[str, market.Quote | None],
    errors: dict[str, str],
    current: dt.datetime,
) -> tuple[str, str]:
    title = "✅ 엔캐리 청산 경보 연결 시험"
    lines = [
        "1. [엔캐리 연결 시험] 텔레그램 채널 경보 연결을 확인합니다.",
        f"조회 시각: {fmt_kst(current)}",
        "실제 위험 조건 충족 알림이 아니라 최초 1회 연결 시험입니다.",
        "",
        quote_line(quotes.get("usd_jpy"), "USD/JPY"),
        quote_line(quotes.get("nasdaq_cash"), "Nasdaq Composite"),
        quote_line(quotes.get("nikkei_cash"), "Nikkei 225"),
        "",
        "정상 경보 기준",
        "- 1단계: 달러당 엔화 환율 154.00 이하 + Nasdaq·Nikkei 각각 -2.00% 이하",
        "- 2단계: 달러당 엔화 환율 152.00 이하 + Nasdaq·Nikkei 각각 -3.00% 이하",
        "- 같은 단계 유지 중에는 중복 알림하지 않음",
        "- 조건 해제 뒤 재진입하거나 상위 단계로 악화되면 재알림",
    ]
    if errors:
        lines.extend(
            [
                "",
                "참고: 시장이 닫혔거나 일부 데이터가 지연되면 최신 확인값만 표시합니다.",
            ]
        )
    return title, "\n".join(lines)


def transition_message(
    previous_stage: int,
    stage: int,
    usd_jpy: market.Quote,
    nasdaq: market.Quote,
    nikkei: market.Quote,
    current: dt.datetime,
) -> tuple[str, str]:
    if stage == 2:
        title = "🚨 엔캐리 청산 2단계 위험"
        heading = "1. [엔캐리 2단계] 본격적인 위험자산 동반 청산 가능성이 높아졌습니다."
        judgment = (
            "달러당 엔화 환율 152.00 이하와 Nasdaq·Nikkei 각각 -3.00% 이하가 동시에 충족됐습니다. "
            "엔 숏커버가 강제 위험축소로 번질 수 있는 구간입니다."
        )
        effects = [
            "한국 증시: 외국인 선물·현물 동반 매도와 원화 약세 가능",
            "반도체: 고베타·레버리지 축소로 단기 낙폭 확대 위험",
            "가상자산: 증거금 축소와 달러 유동성 회수로 변동성 급등 가능",
        ]
    elif stage == 1:
        if previous_stage == 2:
            title = "↘️ 엔캐리 청산 위험 1단계로 완화"
            heading = "1. [엔캐리 위험 완화] 2단계에서 1단계로 낮아졌습니다."
            judgment = (
                "2단계 조건은 해제됐지만 달러당 엔화 환율 154.00 이하와 양 지수 -2.00% 이하가 "
                "남아 있어 부분 청산 위험은 계속됩니다."
            )
        else:
            title = "⚠️ 엔캐리 청산 1단계 경계"
            heading = "1. [엔캐리 1단계] 부분 청산과 엔 숏커버 가능성이 커졌습니다."
            judgment = (
                "달러당 엔화 환율 154.00 이하와 Nasdaq·Nikkei 각각 -2.00% 이하가 동시에 충족됐습니다. "
                "엔 숏커버와 레버리지 축소가 확대되는지 확인해야 합니다."
            )
        effects = [
            "한국 증시: 외국인 위험축소와 선물 수급 확인 필요",
            "반도체: 실적보다 수급 요인으로 단기 변동성 확대 가능",
            "가상자산: 위험축소가 번질 경우 동반 약세 가능",
        ]
    else:
        title = "✅ 엔캐리 청산 경보 해제"
        heading = "1. [엔캐리 경보 해제] 동시 충족 조건이 해제됐습니다."
        judgment = (
            "달러당 엔화 환율과 Nasdaq·Nikkei의 동시 하락 조건이 더 이상 충족되지 않습니다. "
            "조건 해제 뒤 다시 진입하면 새 경보를 보냅니다."
        )
        effects = [
            "한국 증시: 강제 위험축소 압력 완화 여부 확인",
            "반도체: 수급성 매도 진정 여부 확인",
            "가상자산: 변동성 정상화 여부 확인",
        ]

    lines = [
        heading,
        f"조회 시각: {fmt_kst(current)}",
        f"- USD/JPY: {usd_jpy.price:.3f} ({fmt_pct(usd_jpy.change_pct)})",
        f"- {nasdaq.label}({nasdaq.kind}): {fmt_price(nasdaq.price)} ({fmt_pct(nasdaq.change_pct)})",
        f"- {nikkei.label}({nikkei.kind}): {fmt_price(nikkei.price)} ({fmt_pct(nikkei.change_pct)})",
        "",
        f"판정: {judgment}",
        "",
        "단기 영향",
        *(f"- {item}" for item in effects),
        "",
        "같은 단계 유지 중에는 중복 알림하지 않습니다.",
    ]
    return title, "\n".join(lines)


def append_lane(title: str, body: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing_body = BODY_PATH.read_text(encoding="utf-8").strip() if BODY_PATH.exists() else ""
    existing_title = TITLE_PATH.read_text(encoding="utf-8").strip() if TITLE_PATH.exists() else ""

    if existing_body:
        BODY_PATH.write_text(existing_body + "\n\n---\n\n" + body.strip() + "\n", encoding="utf-8")
    else:
        BODY_PATH.write_text(body.strip() + "\n", encoding="utf-8")
    if not existing_title:
        TITLE_PATH.write_text(title.strip() + "\n", encoding="utf-8")


def main() -> int:
    current = now_utc()
    quotes, errors = fetch_quotes()
    state = load_json(DELIVERY_STATE_PATH, {"sent": {}})
    yen_state = state.get("yen_carry") if isinstance(state.get("yen_carry"), dict) else {}
    previous_stage = int(yen_state.get("stage", 0) or 0)
    if previous_stage not in (0, 1, 2):
        previous_stage = 0

    if not bool(yen_state.get("bootstrap_done")):
        title, body = bootstrap_message(quotes, errors, current)
        append_lane(title, body)
        state["yen_carry"] = {
            **yen_state,
            "bootstrap_done": True,
            "stage": previous_stage,
            "updated_at_kst": fmt_kst(current),
            "last_event": "bootstrap_test",
        }
        write_json(DELIVERY_STATE_PATH, state)
        print("yen_carry_bridge=bootstrap_alert_created")
        return 0

    usd_jpy, nasdaq, nikkei, missing = choose_market_quotes(quotes, current)
    if missing:
        print(f"yen_carry_bridge=skipped_stale_or_missing missing={','.join(missing)}")
        return 0

    assert usd_jpy is not None and nasdaq is not None and nikkei is not None
    stage = market.determine_stage(usd_jpy.price, nasdaq.change_pct, nikkei.change_pct)
    if stage == previous_stage:
        print(f"yen_carry_bridge=no_transition stage={stage}")
        return 0

    title, body = transition_message(previous_stage, stage, usd_jpy, nasdaq, nikkei, current)
    append_lane(title, body)
    state["yen_carry"] = {
        **yen_state,
        "bootstrap_done": True,
        "stage": stage,
        "previous_stage": previous_stage,
        "updated_at_kst": fmt_kst(current),
        "last_event": "stage_transition",
        "last_values": {
            "usd_jpy": round(usd_jpy.price, 4),
            "nasdaq_pct": round(nasdaq.change_pct, 3),
            "nikkei_pct": round(nikkei.change_pct, 3),
            "nasdaq_source": f"{nasdaq.label}({nasdaq.kind})",
            "nikkei_source": f"{nikkei.label}({nikkei.kind})",
        },
    }
    write_json(DELIVERY_STATE_PATH, state)
    print(f"yen_carry_bridge=transition_alert_created previous={previous_stage} current={stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

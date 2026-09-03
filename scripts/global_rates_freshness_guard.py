#!/usr/bin/env python3
"""Freshness/date-alignment guard for the global-rates / yen-carry Telegram report.

Rules:
- Never calculate or trigger on the U.S.-Japan 2Y spread unless both official
  observations have the same market date.
- Reuse the existing query1/query2 cross-checked Yahoo 5-minute USD/JPY reader for
  the *current* FX signal. FRED H.10 remains an official daily reference only.
- Reject a live FX quote older than 12 minutes rather than silently falling back to
  a stale daily observation for current-signal logic.
- Keep lagged official values as labelled reference values, not as current signals.
- Remove stale/misaligned events before Telegram formatting so state is not consumed
  by a comparison that was never valid.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
PENDING = OUT / "global_rates_watch_pending_state.json"
ALERT = OUT / "global_rates_watch_alert.json"
FRESHNESS = OUT / "global_rates_freshness.json"
REPORT = OUT / "global_rates_watch_telegram.md"
MAX_LIVE_FX_AGE_SECONDS = 12 * 60


def load(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    match = re.match(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(value))
    if not match:
        return None
    try:
        year, month, day = map(int, match.groups())
        return dt.date(year, month, day)
    except Exception:
        return None


def fetch_live_usdjpy(now_utc: dt.datetime | None = None) -> dict[str, Any]:
    """Return current USD/JPY only after query1/query2 cross-check and freshness check."""
    from yen_carry_alert import SYMBOLS
    from yen_carry_market_data_v2 import fetch_quote

    now = now_utc or dt.datetime.now(dt.timezone.utc)
    quote = fetch_quote(SYMBOLS["usd_jpy"])
    observed = dt.datetime.fromtimestamp(float(quote.timestamp_epoch), tz=dt.timezone.utc)
    age = (now - observed).total_seconds()
    if age < -120:
        raise RuntimeError(f"USD/JPY quote timestamp is in the future by {-age:.0f}s")
    if age > MAX_LIVE_FX_AGE_SECONDS:
        raise RuntimeError(f"USD/JPY live quote stale: age={age:.0f}s > {MAX_LIVE_FX_AGE_SECONDS}s")
    return {
        "price": float(quote.price),
        "change_pct": float(quote.change_pct),
        "timestamp_epoch": float(quote.timestamp_epoch),
        "timestamp_utc": quote.timestamp_utc,
        "age_seconds": max(0.0, age),
        "source": "Yahoo query1/query2 5분 데이터 교차확인",
    }


def apply_guard(
    pending: dict[str, Any],
    alert: dict[str, Any],
    live_fx: dict[str, Any] | None = None,
    live_fx_error: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    values = dict(pending.get("last_values") or {})
    active = dict(pending.get("active") or {})
    dates = dict(pending.get("last_source_dates") or {})
    events = list(alert.get("events") or [])

    jgb_date = parse_date(dates.get("jgb2"))
    ust_date = parse_date(dates.get("ust2"))
    latest_rate_date = max([x for x in (jgb_date, ust_date) if x is not None], default=None)

    same_2y_date = bool(jgb_date and ust_date and jgb_date == ust_date)
    spread_reference = values.get("us_jp_2y_spread")
    if not same_2y_date:
        values["us_jp_2y_spread"] = None
        active["us_jp_2y_spread:below:2.0"] = False
        events = [e for e in events if e.get("metric") != "us_jp_2y_spread"]

    # Core watcher uses FRED H.10 for an official daily reference. Never let those
    # daily FX events masquerade as current FX events in a 15-minute alert.
    fred_fx_reference = values.get("usdjpy")
    fred_fx_change_reference = values.get("usdjpy_daily_change_pct")
    fred_fx_date = dates.get("usdjpy")
    events = [e for e in events if e.get("metric") not in {"usdjpy", "usdjpy_daily_change"}]

    live_ok = bool(live_fx and live_fx.get("price") is not None and live_fx.get("timestamp_epoch") is not None)
    if live_ok:
        observed_utc = dt.datetime.fromtimestamp(float(live_fx["timestamp_epoch"]), tz=dt.timezone.utc)
        values["usdjpy"] = float(live_fx["price"])
        values["usdjpy_daily_change_pct"] = float(live_fx.get("change_pct") or 0.0)
        dates["usdjpy"] = observed_utc.date().isoformat()
        active["usdjpy:below:155.0"] = values["usdjpy"] <= 155.0
        active["usdjpy:daily_change:below:-2.0"] = values["usdjpy_daily_change_pct"] <= -2.0
    else:
        values["usdjpy"] = None
        values["usdjpy_daily_change_pct"] = None
        active["usdjpy:below:155.0"] = False
        active["usdjpy:daily_change:below:-2.0"] = False

    pending["last_values"] = values
    pending["active"] = active
    pending["last_source_dates"] = dates
    pending["date_alignment"] = {
        "jgb2_date": dates.get("jgb2"),
        "ust2_date": dates.get("ust2"),
        "same_2y_date": same_2y_date,
        "latest_rate_date": latest_rate_date.isoformat() if latest_rate_date else None,
        "live_fx_signal_eligible": live_ok,
        "live_fx_timestamp_utc": (live_fx or {}).get("timestamp_utc"),
    }
    alert["events"] = events

    freshness = {
        "same_2y_date": same_2y_date,
        "jgb2_date": dates.get("jgb2"),
        "ust2_date": dates.get("ust2"),
        "spread_reference_pct_point": spread_reference,
        "latest_rate_date": latest_rate_date.isoformat() if latest_rate_date else None,
        "live_fx_signal_eligible": live_ok,
        "live_fx_price": (live_fx or {}).get("price"),
        "live_fx_change_pct": (live_fx or {}).get("change_pct"),
        "live_fx_timestamp_utc": (live_fx or {}).get("timestamp_utc"),
        "live_fx_age_seconds": (live_fx or {}).get("age_seconds"),
        "live_fx_source": (live_fx or {}).get("source"),
        "live_fx_error": live_fx_error,
        "fred_usdjpy_reference": fred_fx_reference,
        "fred_usdjpy_change_reference_pct": fred_fx_change_reference,
        "fred_usdjpy_date": fred_fx_date,
        "policy": "파생금리차는 동일 기준일만 계산. USD/JPY 현재 신호는 query1/query2 5분 교차확인값만 사용하고 FRED H.10은 공식 일일 참고값으로 분리.",
    }
    return pending, alert, freshness


def live_fx_kst_label(freshness: dict[str, Any]) -> str:
    raw = freshness.get("live_fx_timestamp_utc")
    if not raw:
        return "확인 불가"
    try:
        parsed = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return str(raw)


def annotate_report(report: str, freshness: dict[str, Any]) -> str:
    lines = report.splitlines()
    notes: list[str] = []

    if not freshness.get("same_2y_date"):
        replacement = (
            "⬜ 미·일 2Y 금리차 축소: 기준일 불일치 — 계산 보류 "
            f"(JGB {freshness.get('jgb2_date') or '확인 불가'} / UST {freshness.get('ust2_date') or '확인 불가'})"
        )
        for i, line in enumerate(lines):
            if "미·일 2Y 금리차 축소:" in line:
                lines[i] = replacement
        notes.append("미·일 2년 금리차는 동일 기준일일 때만 계산·판정")
    else:
        notes.append(f"미·일 2년물 동일 기준일 확인: {freshness.get('jgb2_date')}")

    if freshness.get("live_fx_signal_eligible"):
        price = float(freshness["live_fx_price"])
        change = float(freshness.get("live_fx_change_pct") or 0.0)
        replacement = (
            f"{'✅' if price <= 155.0 or change <= -2.0 else '⬜'} 엔화 급등: "
            f"USD/JPY {price:.3f} / 기준변화 {change:+.2f}% / {live_fx_kst_label(freshness)}"
        )
        for i, line in enumerate(lines):
            if "엔화 급등:" in line:
                lines[i] = replacement
        notes.append(
            f"USD/JPY 현재값: Yahoo query1/query2 5분 교차확인 / {live_fx_kst_label(freshness)} / "
            f"지연 {float(freshness.get('live_fx_age_seconds') or 0):.0f}초"
        )
    else:
        value = freshness.get("fred_usdjpy_reference")
        value_text = f"{float(value):.3f}" if value is not None else "확인 불가"
        replacement = (
            f"⬜ 엔화 급등: 현재값 확인 실패 — FRED H.10 공식 최신 일일 참고값 {value_text} "
            f"(기준일 {freshness.get('fred_usdjpy_date') or '확인 불가'}) / 현재 신호 판정 제외"
        )
        for i, line in enumerate(lines):
            if "엔화 급등:" in line:
                lines[i] = replacement
        notes.append(
            "USD/JPY 현재 5분 교차확인 실패 — 과거 일일값을 현재값으로 대체하지 않고 신호 판정 보류"
            + (f" ({freshness.get('live_fx_error')})" if freshness.get("live_fx_error") else "")
        )

    if notes:
        insert_at = 3 if len(lines) >= 3 else len(lines)
        block = ["데이터 최신성 검증", *[f"- {note}" for note in notes], ""]
        lines[insert_at:insert_at] = block

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotate", action="store_true")
    args = parser.parse_args()

    if args.annotate:
        if not REPORT.exists() or not FRESHNESS.exists():
            return 0
        freshness = load(FRESHNESS, {})
        REPORT.write_text(annotate_report(REPORT.read_text(encoding="utf-8"), freshness), encoding="utf-8")
        return 0

    pending = load(PENDING, {})
    if not pending:
        return 0
    alert = load(ALERT, {})
    live_fx = None
    live_fx_error = None
    try:
        live_fx = fetch_live_usdjpy()
    except Exception as exc:
        live_fx_error = f"{type(exc).__name__}: {exc}"

    pending, alert, freshness = apply_guard(pending, alert, live_fx=live_fx, live_fx_error=live_fx_error)
    save(PENDING, pending)
    if ALERT.exists() or alert.get("events"):
        save(ALERT, alert)
    save(FRESHNESS, freshness)
    print(json.dumps(freshness, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

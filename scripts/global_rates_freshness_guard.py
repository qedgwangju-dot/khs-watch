#!/usr/bin/env python3
"""Freshness/date-alignment guard for the global-rates / yen-carry Telegram report.

Rules:
- Never calculate or trigger on the U.S.-Japan 2Y spread unless both official observations have the same market date.
- Reuse the existing query1/query2 cross-checked Yahoo 5-minute USD/JPY reader for the current FX signal. FRED H.10 remains an official daily reference only.
- Reject a live FX quote older than 12 minutes rather than silently falling back to a stale daily observation for current-signal logic.
- Keep lagged official values as labelled reference values, not as current signals.
- Treat a low USD/JPY level and a fresh yen surge as separate concepts: price level alone never counts as a carry-unwind trigger.
- Reconcile the final Telegram risk label after all freshness checks so displayed signals, risk level and persisted state cannot disagree.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
PENDING = OUT / "global_rates_watch_pending_state.json"
ALERT = OUT / "global_rates_watch_alert.json"
FRESHNESS = OUT / "global_rates_freshness.json"
REPORT = OUT / "global_rates_watch_telegram.md"
TELEGRAM_PENDING = OUT / "global_rates_telegram_pending_state.json"
TELEGRAM_STATE = ROOT / "data" / "global_rates_telegram_state.json"
STRUCTURAL_EVENT = OUT / "global_rates_structural_event.json"
MAX_LIVE_FX_AGE_SECONDS = 12 * 60
YEN_STRONG_LEVEL = 155.0
YEN_SURGE_DAILY_PCT = -2.0


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


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_live_fx(price: Any, change_pct: Any) -> dict[str, Any]:
    """Separate yen price level from directional yen-surge confirmation.

    USD/JPY down means yen strength; USD/JPY up means yen weakness.  A level at or
    below 155 is retained as context only.  It does not count as a fresh yen surge.
    """
    p = _float_or_none(price)
    c = _float_or_none(change_pct)
    strong_level = bool(p is not None and p <= YEN_STRONG_LEVEL)
    surge = bool(c is not None and c <= YEN_SURGE_DAILY_PCT)
    if c is None:
        direction = "확인 불가"
    elif c < 0:
        direction = "엔화 강세"
    elif c > 0:
        direction = "엔화 약세"
    else:
        direction = "보합"
    return {
        "price": p,
        "change_pct": c,
        "strong_level": strong_level,
        "surge": surge,
        "direction": direction,
    }


def calculate_final_risk(signals: dict[str, Any]) -> tuple[int, str, str, int, int]:
    jgb10_3 = bool(signals.get("jgb10_3"))
    curve_up = bool(signals.get("jgb_curve_up"))
    spread_narrow = bool(signals.get("us_jp_2y_spread_narrow"))
    us_rates_down = bool(signals.get("us_2y_down"))
    yen_surge = bool(signals.get("yen_surge"))
    vix_spike = bool(signals.get("vix_spike"))
    equity_joint = bool(signals.get("nikkei_nasdaq_joint_weakness"))
    leading_count = sum([jgb10_3, curve_up, spread_narrow, us_rates_down, yen_surge])
    confirm_count = sum([vix_spike, equity_joint])

    if yen_surge and spread_narrow and (vix_spike or equity_joint):
        return 3, "실제 엔캐리 청산 위험 높음", "🔴", leading_count, confirm_count
    if (yen_surge and (spread_narrow or curve_up)) or (jgb10_3 and curve_up and spread_narrow):
        return 2, "엔캐리 청산 경계 강화", "🟠", leading_count, confirm_count
    if leading_count >= 2 or (jgb10_3 and (vix_spike or equity_joint)):
        return 1, "구조적 경계 상승", "🟡", leading_count, confirm_count
    return 0, "관찰", "🟢", leading_count, confirm_count


def fetch_live_usdjpy(now_utc: dt.datetime | None = None) -> dict[str, Any]:
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


def apply_guard(pending: dict[str, Any], alert: dict[str, Any], live_fx: dict[str, Any] | None = None, live_fx_error: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
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
        active["usdjpy:below:155.0"] = values["usdjpy"] <= YEN_STRONG_LEVEL
        active["usdjpy:daily_change:below:-2.0"] = values["usdjpy_daily_change_pct"] <= YEN_SURGE_DAILY_PCT
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

    fx_state = classify_live_fx((live_fx or {}).get("price"), (live_fx or {}).get("change_pct")) if live_ok else classify_live_fx(None, None)
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
        "yen_strong_level": fx_state["strong_level"],
        "yen_surge": fx_state["surge"],
        "yen_direction": fx_state["direction"],
        "fred_usdjpy_reference": fred_fx_reference,
        "fred_usdjpy_change_reference_pct": fred_fx_change_reference,
        "fred_usdjpy_date": fred_fx_date,
        "policy": "파생금리차는 동일 기준일만 계산. USD/JPY 155 이하는 가격 수준 참고값으로만 쓰고, 엔화 급등 신호는 현재 USD/JPY 변화율이 -2% 이하일 때만 판정. FRED H.10은 공식 일일 참고값으로 분리.",
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


def _replace_risk_line(lines: list[str], prefix: str, replacement: str) -> None:
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = replacement


def reconcile_final_report(report: str, freshness: dict[str, Any]) -> str | None:
    """Make the final displayed risk and persisted risk use the same post-freshness signals."""
    pending_state = load(TELEGRAM_PENDING, {})
    if not pending_state:
        return report

    signals = dict(pending_state.get("signals") or {})
    fx_state = classify_live_fx(freshness.get("live_fx_price"), freshness.get("live_fx_change_pct"))
    signals["yen_strong_level"] = bool(freshness.get("live_fx_signal_eligible") and fx_state["strong_level"])
    signals["yen_surge"] = bool(freshness.get("live_fx_signal_eligible") and fx_state["surge"])
    level, label, emoji, leading_count, confirm_count = calculate_final_risk(signals)
    pending_state["risk_level"] = level
    pending_state["risk_label"] = label
    pending_state["signals"] = signals
    save(TELEGRAM_PENDING, pending_state)

    previous = load(TELEGRAM_STATE, {"risk_level": 0, "risk_label": "관찰"})
    old_level = int(previous.get("risk_level") or 0)
    old_label = str(previous.get("risk_label") or "관찰")
    risk_changed = level != old_level
    primary_event = bool((load(ALERT, {}) or {}).get("events"))
    structural_changed = bool((load(STRUCTURAL_EVENT, {}) or {}).get("events"))
    manual_dispatch = os.getenv("GITHUB_EVENT_NAME", "") == "workflow_dispatch"

    # The earlier formatter may have created a report only because the old, incorrect
    # price-level rule promoted the risk. Suppress that false alert before Telegram.
    if not (manual_dispatch or primary_event or structural_changed or risk_changed):
        return None

    lines = report.splitlines()
    if lines and lines[0].startswith("[글로벌 금리·엔캐리 경보]"):
        lines[0] = f"[글로벌 금리·엔캐리 경보] {emoji}"
    _replace_risk_line(lines, "판정:", f"판정: {label}")

    event_indices = [i for i, line in enumerate(lines) if "위험단계 변화:" in line]
    if risk_changed:
        replacement = f"- 위험단계 변화: {old_label} → {label}"
        if event_indices:
            lines[event_indices[0]] = replacement
            for i in reversed(event_indices[1:]):
                lines.pop(i)
        else:
            for i, line in enumerate(lines):
                if line.strip() == "① 무엇이 바뀌었나":
                    lines.insert(i + 1, replacement)
                    break
    else:
        for i in reversed(event_indices):
            lines.pop(i)

    for i, line in enumerate(lines):
        if "선행 " in line and "후행확인 " in line and ("엔캐리" in line or "구조적" in line or "관찰" in line):
            lines[i] = f"{emoji} {label}: 선행 {leading_count}/5, 후행확인 {confirm_count}/2. 구조 신호는 실제 자금행동 확인용이며 단독으로 엔캐리 청산을 확정하지 않습니다."

    return "\n".join(lines).rstrip() + "\n"


def annotate_report(report: str, freshness: dict[str, Any]) -> str:
    lines = report.splitlines()

    if not freshness.get("same_2y_date"):
        replacement = "⬜ 미·일 2Y 금리차 축소: 기준일 불일치 — 계산 보류 " + f"(JGB {freshness.get('jgb2_date') or '확인 불가'} / UST {freshness.get('ust2_date') or '확인 불가'})"
        for i, line in enumerate(lines):
            if "미·일 2Y 금리차 축소:" in line:
                lines[i] = replacement
        rate_note = f"미·일2Y 불일치(JGB {freshness.get('jgb2_date') or '확인 불가'} / UST {freshness.get('ust2_date') or '확인 불가'})"
    else:
        rate_note = f"미·일2Y 동일 {freshness.get('jgb2_date')}"

    if freshness.get("live_fx_signal_eligible"):
        price = float(freshness["live_fx_price"])
        change = float(freshness.get("live_fx_change_pct") or 0.0)
        fx_state = classify_live_fx(price, change)
        replacement = f"{'✅' if fx_state['surge'] else '⬜'} 엔화 급등: USD/JPY {price:.3f} / {change:+.2f}% / {fx_state['direction']}"
        for i, line in enumerate(lines):
            if "엔화 급등:" in line:
                lines[i] = replacement
                break
        fx_note = f"USD/JPY {live_fx_kst_label(freshness)} · 지연 {float(freshness.get('live_fx_age_seconds') or 0):.0f}초"
    else:
        value = freshness.get("fred_usdjpy_reference")
        value_text = f"{float(value):.3f}" if value is not None else "확인 불가"
        replacement = f"⬜ 엔화 급등: 현재값 확인 실패 / FRED 일일 {value_text}({freshness.get('fred_usdjpy_date') or '확인 불가'}) / 판정 제외"
        for i, line in enumerate(lines):
            if "엔화 급등:" in line:
                lines[i] = replacement
        fx_note = "USD/JPY 실시간 확인 실패 · 판정 제외"

    # Keep freshness visible but to one scan line; detailed methodology remains
    # in the watcher logic and source artifacts instead of repeating in Telegram.
    insert_at = 3 if len(lines) >= 3 else len(lines)
    lines[insert_at:insert_at] = [f"최신성 │ {rate_note} · {fx_note}", ""]
    return "\n".join(lines).rstrip() + "\n"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotate", action="store_true")
    args = parser.parse_args()
    if args.annotate:
        if REPORT.exists() and FRESHNESS.exists():
            freshness = load(FRESHNESS, {})
            annotated = annotate_report(REPORT.read_text(encoding="utf-8"), freshness)
            reconciled = reconcile_final_report(annotated, freshness)
            if reconciled is None:
                REPORT.unlink(missing_ok=True)
                print("final_risk_consistency=ok false_price_level_alert_suppressed=true")
            else:
                REPORT.write_text(reconciled, encoding="utf-8")
                pending_state = load(TELEGRAM_PENDING, {})
                print(f"final_risk_consistency=ok risk_level={pending_state.get('risk_level')} risk_label={pending_state.get('risk_label')}")
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

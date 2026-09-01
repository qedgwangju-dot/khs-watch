#!/usr/bin/env python3
"""Freshness/date-alignment guard for the global-rates / yen-carry Telegram report.

Rules:
- Never calculate or trigger on the U.S.-Japan 2Y spread unless both official
  observations have the same market date.
- Never use a lagged FRED DEXJPUS daily observation as a current yen trigger when
  a newer official rates market date already exists.
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
    text = str(value).strip().replace("/", "-")
    try:
        return dt.date.fromisoformat(text[:10])
    except Exception:
        return None


def apply_guard(pending: dict[str, Any], alert: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    values = dict(pending.get("last_values") or {})
    active = dict(pending.get("active") or {})
    dates = dict(pending.get("last_source_dates") or {})
    events = list(alert.get("events") or [])

    jgb_date = parse_date(dates.get("jgb2"))
    ust_date = parse_date(dates.get("ust2"))
    fx_date = parse_date(dates.get("usdjpy"))
    latest_rate_date = max([x for x in (jgb_date, ust_date) if x is not None], default=None)

    same_2y_date = bool(jgb_date and ust_date and jgb_date == ust_date)
    spread_reference = values.get("us_jp_2y_spread")
    if not same_2y_date:
        values["us_jp_2y_spread"] = None
        active["us_jp_2y_spread:below:2.0"] = False
        events = [e for e in events if e.get("metric") != "us_jp_2y_spread"]

    fx_signal_eligible = bool(fx_date and latest_rate_date and fx_date >= latest_rate_date)
    fx_reference = values.get("usdjpy")
    fx_change_reference = values.get("usdjpy_daily_change_pct")
    if not fx_signal_eligible:
        values["usdjpy"] = None
        values["usdjpy_daily_change_pct"] = None
        active["usdjpy:below:155.0"] = False
        active["usdjpy:daily_change:below:-2.0"] = False
        events = [e for e in events if e.get("metric") not in {"usdjpy", "usdjpy_daily_change"}]

    pending["last_values"] = values
    pending["active"] = active
    pending["date_alignment"] = {
        "jgb2_date": dates.get("jgb2"),
        "ust2_date": dates.get("ust2"),
        "same_2y_date": same_2y_date,
        "usdjpy_date": dates.get("usdjpy"),
        "latest_rate_date": latest_rate_date.isoformat() if latest_rate_date else None,
        "fx_signal_eligible": fx_signal_eligible,
    }
    alert["events"] = events

    freshness = {
        "same_2y_date": same_2y_date,
        "jgb2_date": dates.get("jgb2"),
        "ust2_date": dates.get("ust2"),
        "spread_reference_pct_point": spread_reference,
        "fx_signal_eligible": fx_signal_eligible,
        "usdjpy_date": dates.get("usdjpy"),
        "latest_rate_date": latest_rate_date.isoformat() if latest_rate_date else None,
        "usdjpy_reference": fx_reference,
        "usdjpy_daily_change_reference_pct": fx_change_reference,
        "policy": "파생값은 동일 기준일만 계산. 지연된 공식 일일값은 참고값으로만 표시하고 현재 신호 판정에서 제외.",
    }
    return pending, alert, freshness


def annotate_report(report: str, freshness: dict[str, Any]) -> str:
    lines = report.splitlines()
    warnings: list[str] = []

    if not freshness.get("same_2y_date"):
        replacement = (
            "⬜ 미·일 2Y 금리차 축소: 기준일 불일치 — 계산 보류 "
            f"(JGB {freshness.get('jgb2_date') or '확인 불가'} / UST {freshness.get('ust2_date') or '확인 불가'})"
        )
        for i, line in enumerate(lines):
            if "미·일 2Y 금리차 축소:" in line:
                lines[i] = replacement
        warnings.append("미·일 2년 금리차는 동일 기준일이 아니어서 계산·신호 판정에서 제외")

    if not freshness.get("fx_signal_eligible"):
        value = freshness.get("usdjpy_reference")
        value_text = f"{float(value):.3f}" if value is not None else "확인 불가"
        replacement = (
            f"⬜ 엔화 급등: USD/JPY 공식 최신 일일값 {value_text} "
            f"(기준일 {freshness.get('usdjpy_date') or '확인 불가'}) — 최신성 부족으로 현재 신호 판정 제외"
        )
        for i, line in enumerate(lines):
            if "엔화 급등:" in line:
                lines[i] = replacement
        warnings.append("USD/JPY는 최신 금리 기준일보다 오래된 FRED 일일값이면 참고값으로만 표시")

    if warnings:
        insert_at = 3 if len(lines) >= 3 else len(lines)
        block = ["데이터 최신성 검증", *[f"- {w}" for w in warnings], ""]
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
    pending, alert, freshness = apply_guard(pending, alert)
    save(PENDING, pending)
    if ALERT.exists() or alert.get("events"):
        save(ALERT, alert)
    save(FRESHNESS, freshness)
    print(json.dumps(freshness, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify the live GAMEJOA report, JSON, and Telegram delivery agree."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
REPORT = OUT / "gamejoa_preopen_news_radar.md"
JSON_REPORT = OUT / "gamejoa_preopen_news_radar.json"
DELIVERY = OUT / "gamejoa_preopen_news_radar_delivery.json"


def parse_hhmm(value: str, fallback: tuple[int, int]) -> int:
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", value or "")
    if not match:
        return fallback[0] * 60 + fallback[1]
    hour, minute = int(match.group(1)), int(match.group(2))
    return max(0, min(23, hour)) * 60 + max(0, min(59, minute))


def send_window_open(query_time: dt.datetime) -> bool:
    if os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live":
        return True
    current = query_time.hour * 60 + query_time.minute
    start = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_START_KST", "05:30"), (5, 30))
    end = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_END_KST", "07:30"), (7, 30))
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def main() -> int:
    errors: list[str] = []
    for path in (REPORT, JSON_REPORT, DELIVERY):
        if not path.exists():
            errors.append(f"missing runtime artifact: {path.relative_to(ROOT)}")
    if errors:
        return fail(errors)

    report = REPORT.read_text(encoding="utf-8")
    data = json.loads(JSON_REPORT.read_text(encoding="utf-8"))
    delivery = json.loads(DELIVERY.read_text(encoding="utf-8"))

    visible_count = sum(1 for line in report.splitlines() if re.match(r"^\d+\)\s+\[", line))
    alerts = data.get("alerts")
    if not isinstance(alerts, list):
        errors.append("runtime JSON alerts is not a list")
        alerts = []
    if visible_count != len(alerts):
        errors.append(f"runtime report/JSON count mismatch: report={visible_count} json={len(alerts)}")

    diagnostics = data.get("selection_diagnostics")
    if not isinstance(diagnostics, dict):
        errors.append("runtime JSON missing selection_diagnostics")
    elif diagnostics.get("selected_alerts") != len(alerts):
        errors.append(
            "runtime diagnostics/JSON count mismatch: "
            f"diagnostics={diagnostics.get('selected_alerts')} json={len(alerts)}"
        )

    try:
        query_time = dt.datetime.fromisoformat(str(data.get("query_time_kst") or ""))
    except ValueError:
        errors.append("runtime JSON has invalid query_time_kst")
        query_time = dt.datetime.now().astimezone()

    status = str(delivery.get("status") or "").strip().lower()
    if not alerts:
        expected = "skipped_empty"
    elif send_window_open(query_time):
        expected = "sent"
    else:
        expected = "skipped_off_window"
    if status != expected:
        errors.append(f"runtime Telegram status mismatch: expected={expected} actual={status or 'missing'}")
    if status == "sent":
        if not isinstance(delivery.get("sent_chars"), int) or delivery.get("sent_chars", 0) <= 0:
            errors.append("runtime Telegram sent status missing sent_chars")
        if not isinstance(delivery.get("attempts"), int) or delivery.get("attempts", 0) <= 0:
            errors.append("runtime Telegram sent status missing attempts")

    if errors:
        return fail(errors)
    print(
        "GAMEJOA runtime delivery verified: "
        f"selected={len(alerts)} telegram_status={status} mode={os.getenv('RADAR_RUN_MODE', 'preopen')}"
    )
    return 0


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"GAMEJOA runtime delivery error: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

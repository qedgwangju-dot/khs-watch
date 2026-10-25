#!/usr/bin/env python3
"""Keep confirmed GDPNow/health state monotonic across overlapping GitHub runs.

Usage: python scripts/gdpnow_state_merge_guard.py gdp|health candidate.json repository_state.json
No API calls or Telegram sends occur. An older run is never allowed to
overwrite a newer confirmed observation or a newer health transition.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys


def read(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def timestamp(value: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def date_key(payload: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str((payload.get("latest") or {}).get("date") or ""))
    except ValueError:
        return None


def should_replace(kind: str, proposed: dict, current: dict) -> bool:
    if not proposed:
        return False
    if not current:
        return True
    if kind == "gdp":
        proposed_date, current_date = date_key(proposed), date_key(current)
        if proposed_date is None:
            raise ValueError("Proposed GDP state has no valid observation date")
        if current_date and proposed_date != current_date:
            return proposed_date > current_date
        proposed_time = timestamp(proposed.get("checked_at_kst"))
        current_time = timestamp(current.get("checked_at_kst"))
    elif kind == "health":
        proposed_time = timestamp(proposed.get("last_status_change_kst"))
        current_time = timestamp(current.get("last_status_change_kst"))
        if proposed_time is None:
            proposed_time = timestamp(proposed.get("last_check_kst"))
        if current_time is None:
            current_time = timestamp(current.get("last_check_kst"))
    else:
        raise ValueError(f"Unrecognized state kind: {kind}")

    if proposed_time and current_time:
        return proposed_time >= current_time and proposed != current
    if proposed_time:
        return True
    if current_time:
        return False
    # A legacy unversioned state cannot safely overwrite current state.
    return False


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in {"gdp", "health"}:
        raise SystemExit("Usage: gdpnow_state_merge_guard.py gdp|health candidate.json current.json")
    kind = sys.argv[1]
    candidate_path = pathlib.Path(sys.argv[2])
    current_path = pathlib.Path(sys.argv[3])
    candidate, current = read(candidate_path), read(current_path)
    if should_replace(kind, candidate, current):
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"state_merge={kind} accepted")
    else:
        print(f"state_merge={kind} skipped stale/equal candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

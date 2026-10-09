#!/usr/bin/env python3
"""Merge GitHub state without overwriting concurrently committed alert decisions."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "lg_auto_chiplet_watch_state.json"
PENDING = ROOT / "out" / "lg_auto_chiplet_pending_state.json"

def merge():
    if not PENDING.exists():
        raise RuntimeError("Pending chiplet state missing")
    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    remote = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    seen = dict(remote.get("seen") or {})
    for key, item in (pending.get("seen") or {}).items():
        old = seen.get(key) or {}
        # A previously delivered article must never be rolled back to undelivered.
        if old.get("alerted") and not item.get("alerted"):
            continue
        seen[key] = item
    events = dict(remote.get("events") or {})
    for key, item in (pending.get("events") or {}).items():
        old = events.get(key) or {}
        if old.get("alerted") and not item.get("alerted"):
            continue
        events[key] = item
    result = {**remote, **pending, "seen": dict(list(seen.items())[-2500:]), "events": events}
    result["initialized"] = True
    result["bootstrap_kst"] = remote.get("bootstrap_kst") or pending.get("bootstrap_kst")
    result["last_checked_kst"] = max(
        str(remote.get("last_checked_kst") or ""),
        str(pending.get("last_checked_kst") or ""),
    )
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"lg_chiplet_state_merge_ok=true articles={len(seen)} events={len(events)}")

if __name__ == "__main__":
    merge()

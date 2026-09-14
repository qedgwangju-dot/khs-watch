#!/usr/bin/env python3
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "clarity_ethics_breakthrough_state.json"
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"


def is_ethics_breakthrough(event):
    return "윤리 합의 진전" in str(event.get("event_type", ""))


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def filter_duplicates(events, state):
    # Once this specific AP/Tillis-Gallego negotiation breakthrough has been sent,
    # later rediscovery through a differently titled RSS item must not alert again.
    already_sent = bool(state.get("seen_signatures"))
    if not already_sent:
        return events
    return [event for event in events if not is_ethics_breakthrough(event)]


def main():
    if not ALERT_JSON.exists():
        print("clarity_ethics_duplicate_guard=false reason=no_alert_json")
        return
    events = load_json(ALERT_JSON, [])
    state = load_json(STATE_PATH, {})
    kept = filter_duplicates(events, state)
    dropped = len(events) - len(kept)
    if kept:
        ALERT_JSON.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        ALERT_JSON.unlink(missing_ok=True)
    print(f"clarity_ethics_duplicate_guard=true dropped={dropped} kept={len(kept)}")


if __name__ == "__main__":
    main()

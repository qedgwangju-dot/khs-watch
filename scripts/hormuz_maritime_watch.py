import hormuz_maritime_watch_v4 as watcher


KNOWN_BASELINE_EVENTS = {
    "news:2026-08-30:strike:hormuz:1": {
        "baseline": True,
        "note": "Known pre-monitor single-projectile tanker incident",
    },
    "news:2026-08-31:strike:hormuz:3": {
        "baseline": True,
        "note": "Known UKMTO 124-26 three-projectile tanker incident",
    },
}


def calibrated_source_confidence(items):
    sources = {item.get("source") for item in items if item.get("source")}
    strong = sources & watcher.STRONG_SOURCES
    specialists = sources & watcher.SPECIALIST_SOURCES
    authority_mention = any(item.get("mentions_authority") for item in items)
    if not authority_mention:
        return False
    if len(strong) >= 2:
        return True
    if len(sources) >= 2 and strong and specialists:
        return True
    return len(sources) >= 3 and bool(strong)


_original_load_state = watcher.load_state


def calibrated_load_state():
    state, migrating = _original_load_state()
    events = state.setdefault("confirmed_events", {})
    for key, value in KNOWN_BASELINE_EVENTS.items():
        events.setdefault(key, value)
    return state, migrating


watcher.source_confidence = calibrated_source_confidence
watcher.load_state = calibrated_load_state


if __name__ == "__main__":
    raise SystemExit(watcher.main())

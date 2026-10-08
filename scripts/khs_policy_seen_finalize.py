#!/usr/bin/env python3
"""Commit main policy-watch seen state only after a confirmed Telegram delivery."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
PENDING_PATH = OUT / "khs_policy_watch_pending_seen.json"
DELIVERY_PATH = OUT / "khs_telegram_delivery_confirmed.json"
SEEN_PATH = DATA / "khs_policy_watch_seen.json"
TRUSTED_ALERTS_PATH = OUT / "khs_trusted_policy_news_alerts.json"
TRUSTED_TITLE_PATH = OUT / "khs_trusted_policy_news_title.txt"
TRUSTED_STATE_PATH = DATA / "khs_trusted_policy_news_seen.json"
OISP_RULE_KEY = "us_treasury_outbound_ai_robotics_enforcement"
SURVIVING_ALERT_PATHS = (
    OUT / "khs_policy_watch_alerts.json",
    OUT / "khs_korea_presidential_personnel_alerts.json",
)


def load_object(path: Path, fallback: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else fallback
    except Exception:
        return fallback


def surviving_fingerprints() -> set[str]:
    fingerprints: set[str] = set()
    for path in SURVIVING_ALERT_PATHS:
        if not path.exists():
            continue
        try:
            alerts = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for alert in alerts if isinstance(alerts, list) else []:
            fingerprint = str(alert.get("fingerprint") or "").strip()
            if fingerprint:
                fingerprints.add(fingerprint)
    return fingerprints


def finalize_confirmed_outbound_alert(delivery: dict) -> None:
    # Do not acknowledge an event merely because some *other* policy lane sent.
    # The delivery receipt must match the trusted-policy bundle title exactly.
    if delivery.get("status") != "confirmed":
        return
    try:
        expected_title = TRUSTED_TITLE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return
    sent_titles = delivery.get("sent_titles") or []
    confirmed = any(
        isinstance(item, dict)
        and item.get("route") == "policy"
        and item.get("title") == expected_title
        for item in sent_titles
    )
    if not confirmed:
        print("trusted_oisp_seen_finalize=deferred no_matching_telegram_title")
        return
    try:
        events = json.loads(TRUSTED_ALERTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(events, list):
        return
    # The displayed policy bundle includes at most the first three general events.
    selected = [
        event for event in events[:3]
        if isinstance(event, dict) and event.get("key") == OISP_RULE_KEY
        and str(event.get("fingerprint") or "").strip()
    ]
    if not selected:
        return
    state = load_object(TRUSTED_STATE_PATH, {"seen": {}, "updated_at_kst": ""})
    seen = state.setdefault("seen", {})
    timestamp = str(delivery.get("confirmed_at_kst") or "")
    for event in selected:
        seen[str(event["fingerprint"])] = {
            "key": OISP_RULE_KEY,
            "title": str(event.get("title") or ""),
            "first_seen_kst": timestamp,
            "status": str(event.get("status") or "공식 확인 전"),
            "sources": [
                str(item.get("source") or "")
                for item in (event.get("items") or [])[:3]
                if isinstance(item, dict)
            ],
        }
    state["updated_at_kst"] = timestamp
    TRUSTED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRUSTED_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"trusted_oisp_seen_finalize=committed confirmed={len(selected)}")


def main() -> int:
    delivery = load_object(DELIVERY_PATH, {})
    finalize_confirmed_outbound_alert(delivery)
    if not PENDING_PATH.exists():
        print("policy_seen_finalize=no_pending")
        return 0
    if delivery.get("status") != "confirmed":
        print("policy_seen_finalize=deferred delivery_not_confirmed")
        return 0

    # Current delivery records always include an explicit sent count. Keep
    # legacy confirmed records (created before that field existed) compatible,
    # while still refusing current duplicate-only/no-send outcomes (sent=0).
    sent_raw = delivery.get("sent")
    if sent_raw is None:
        sent_count = 1
    else:
        try:
            sent_count = int(sent_raw or 0)
        except (TypeError, ValueError):
            sent_count = 0
    if sent_count <= 0:
        print("policy_seen_finalize=deferred no_telegram_send")
        return 0

    pending = load_object(PENDING_PATH, {"seen": {}})
    pending_seen = pending.get("seen") if isinstance(pending.get("seen"), dict) else {}
    surviving = surviving_fingerprints()
    confirmed = {key: value for key, value in pending_seen.items() if key in surviving}
    dropped = sorted(set(pending_seen) - set(confirmed))
    if not confirmed:
        print(
            f"policy_seen_finalize=no_surviving pending={len(pending_seen)} "
            f"dropped={len(dropped)}"
        )
        return 0

    state = load_object(SEEN_PATH, {"seen": {}, "updated_at_kst": ""})
    seen = state.setdefault("seen", {})
    seen.update(confirmed)
    state["updated_at_kst"] = str(delivery.get("confirmed_at_kst") or pending.get("created_at_kst") or "")
    DATA.mkdir(exist_ok=True)
    SEEN_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"policy_seen_finalize=committed confirmed={len(confirmed)} "
        f"dropped={len(dropped)} sent={sent_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

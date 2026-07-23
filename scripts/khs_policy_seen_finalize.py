#!/usr/bin/env python3
"""Commit main policy-watch seen state only after a confirmed Telegram outcome."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
PENDING_PATH = OUT / "khs_policy_watch_pending_seen.json"
DELIVERY_PATH = OUT / "khs_telegram_delivery_confirmed.json"
SEEN_PATH = DATA / "khs_policy_watch_seen.json"
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


def main() -> int:
    if not PENDING_PATH.exists():
        print("policy_seen_finalize=no_pending")
        return 0
    delivery = load_object(DELIVERY_PATH, {})
    if delivery.get("status") != "confirmed":
        print("policy_seen_finalize=deferred delivery_not_confirmed")
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
        f"dropped={len(dropped)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

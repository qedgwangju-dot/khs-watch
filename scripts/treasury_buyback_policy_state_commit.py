#!/usr/bin/env python3
"""Race-safe persistence of the EXISTING Treasury buyback policy alert state.

The Telegram sender confirms success before this script runs.  Preserve that
confirmed event when unrelated workflows advance the GitHub main branch.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

STATE = Path("data/treasury_buyback_policy_state.json")
VOLATILE = {"last_checked_kst"}
PENDING = {"pending_source_ids", "pending_schedule_change", "pending_special_sha", "pending_change"}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], text=True, capture_output=True, check=check)


def ordered_union(a, b, limit: int):
    combined = list(a or [])
    for item in b or []:
        if item not in combined:
            combined.append(item)
    return combined[-limit:]


def merge_state(remote: dict, local: dict) -> dict:
    """Pick the newest observation, but NEVER discard committed event fingerprints."""
    a = str(remote.get("last_checked_kst") or "")
    b = str(local.get("last_checked_kst") or "")
    latest = local if b >= a else remote
    merged = {**remote, **latest}
    merged["seen_source_ids"] = ordered_union(
        remote.get("seen_source_ids"), local.get("seen_source_ids"), 100
    )
    merged["seen_long_end_special_shas"] = ordered_union(
        remote.get("seen_long_end_special_shas"),
        local.get("seen_long_end_special_shas"), 50
    ) if remote.get("seen_long_end_special_shas") or local.get("seen_long_end_special_shas") else []
    merged["bessent_policy_boundary_revision"] = max(
        int(remote.get("bessent_policy_boundary_revision") or 0),
        int(local.get("bessent_policy_boundary_revision") or 0),
    )
    for key in PENDING:
        merged.pop(key, None)
    return merged


def material(state: dict) -> dict:
    return {key: value for key, value in state.items() if key not in VOLATILE}


def persist() -> None:
    local = json.loads(STATE.read_text(encoding="utf-8"))
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for attempt in range(1, 6):
        try:
            git("fetch", "origin", "main")
            remote = json.loads(
                git("show", f"origin/main:{STATE.as_posix()}").stdout
            )
            merged = merge_state(remote, local)
            if material(merged) == material(remote):
                print("Treasury policy state unchanged (timestamp-only): no commit")
                return
            git("reset", "--hard", "origin/main")
            STATE.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            git("add", STATE.as_posix())
            git("commit", "-m", "Update Treasury buyback policy state")
            push = git("push", "origin", "HEAD:main", check=False)
            if push.returncode == 0:
                print("Treasury policy state safely committed")
                return
            print(f"Treasury policy state write conflict: retry {attempt}/5")
        except Exception as exc:
            print(f"Treasury policy state persistence retry {attempt}/5: {type(exc).__name__}: {exc}")
        time.sleep(attempt)
    raise RuntimeError("Treasury policy state could not be persisted after five retries")


if __name__ == "__main__":
    persist()

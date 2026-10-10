#!/usr/bin/env python3
"""Race-safe state persistence for the existing QRA workflow's fiscal watch."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

STATE = Path("data/treasury_fiscal_plan_state.json")


def git(*args, check=True):
    return subprocess.run(["git", *args], text=True, capture_output=True, check=check)


def merge_state(remote: dict, local: dict) -> dict:
    seen = list(remote.get("seen_events") or [])
    for event in local.get("seen_events") or []:
        if event not in seen:
            seen.append(event)
    merged = {**remote, **local}
    merged["seen_events"] = seen[-500:]
    for flag in ("last_sent_at_kst",):
        merged[flag] = max(str(remote.get(flag) or ""), str(local.get(flag) or ""))
    return merged


def persist():
    local = json.loads(STATE.read_text(encoding="utf-8"))
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for attempt in range(1, 6):
        git("fetch", "origin", "main")
        remote_result = git("show", "origin/main:" + STATE.as_posix(), check=False)
        remote = json.loads(remote_result.stdout) if remote_result.returncode == 0 else {}
        combined = merge_state(remote, local)
        if combined == remote:
            print("No new fiscal policy event; no state commit")
            return
        git("reset", "--hard", "origin/main")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(
            json.dumps(combined, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        git("add", STATE.as_posix())
        git("commit", "-m", "Confirm US fiscal plan and debt milestone alert delivery")
        result = git("push", "origin", "HEAD:main", check=False)
        if result.returncode == 0:
            print("Treasury fiscal alert state confirmed")
            return
        print("Concurrent Git change: retrying confirmed fiscal event", attempt)
        time.sleep(attempt)
    raise RuntimeError("Unable to confirm Treasury fiscal alert state after 5 retries")


if __name__ == "__main__":
    persist()

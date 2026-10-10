#!/usr/bin/env python3
"""Race-safe commit of the existing Treasury QRA Telegram confirmation state."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

STATE = Path("data/qra_recurring_alert_state.json")


def git(*args, check=True):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def choose_newer(remote: dict, local: dict) -> dict:
    if str(remote.get("last_sent_at_kst") or "") >= str(local.get("last_sent_at_kst") or ""):
        return remote
    return local


def persist():
    local = json.loads(STATE.read_text(encoding="utf-8"))
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for attempt in range(1, 6):
        git("fetch", "origin", "main")
        remote_result = git("show", "origin/main:" + STATE.as_posix(), check=False)
        remote = json.loads(remote_result.stdout) if remote_result.returncode == 0 else {}
        combined = choose_newer(remote, local)
        if combined == remote:
            print("QRA confirmed state already up-to-date")
            return
        git("reset", "--hard", "origin/main")
        STATE.write_text(
            json.dumps(combined, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        git("add", STATE.as_posix())
        git("commit", "-m", "Record recurring interpreted QRA delivery")
        result = git("push", "origin", "HEAD:main", check=False)
        if result.returncode == 0:
            print("QRA state safely committed")
            return
        print("Concurrent Git push during QRA state commit, retry", attempt)
        time.sleep(attempt)
    raise RuntimeError("QRA state confirmation failed after five tries")


if __name__ == "__main__":
    persist()

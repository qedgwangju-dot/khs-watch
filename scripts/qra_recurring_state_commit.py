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
        selected = dict(remote)
    else:
        selected = dict(local)
    # Link-format repair edits the already confirmed message, not a new event.
    # Preserve this acknowledgment even if both records share the same send time.
    if (
        remote.get("last_heading") == local.get("last_heading")
        and remote.get("telegram_message_id") == local.get("telegram_message_id")
    ):
        message_id = selected.get("telegram_message_id")
        for candidate in (remote, local):
            if candidate.get("dealer_links_edited_message_id") == message_id:
                selected["dealer_links_edited_message_id"] = message_id
                selected["dealer_links_format"] = "html_v1"
                selected["dealer_links_edited_at_kst"] = max(
                    str(remote.get("dealer_links_edited_at_kst") or ""),
                    str(local.get("dealer_links_edited_at_kst") or ""),
                )
    # Preserve a verified one-time delivery to the requested separate bot.
    for candidate in (remote, local):
        if candidate.get("dealer_requested_bot_event") and candidate.get("dealer_requested_bot_message_id"):
            if (not selected.get("dealer_requested_bot_event")
                or str(candidate.get("dealer_requested_bot_sent_at_kst") or "")
                   > str(selected.get("dealer_requested_bot_sent_at_kst") or "")):
                for field in ("dealer_requested_bot_event", "dealer_requested_bot_username",
                              "dealer_requested_bot_message_id", "dealer_requested_bot_sent_at_kst"):
                    selected[field] = candidate[field]
    return selected


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

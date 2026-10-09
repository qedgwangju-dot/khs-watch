#!/usr/bin/env python3
"""Commit buyback alert state without dropping confirmed alerts on Git races."""
import json
import pathlib
import subprocess
import time

STATE = pathlib.Path("data/treasury_buyback_media_state.json")

def git(*args, check=True):
    return subprocess.run(["git", *args], text=True, capture_output=True, check=check)

def combine(remote, local):
    merged = {**remote, **local}
    seen = list(remote.get("seen", []))
    for key in local.get("seen", []):
        if key not in seen:
            seen.append(key)
    merged["seen"] = seen[-200:]
    if remote.get("latest_long_end_operation_date", "") > local.get("latest_long_end_operation_date", ""):
        merged["latest_long_end_operation_date"] = remote["latest_long_end_operation_date"]
        merged["latest_long_end_fingerprint"] = remote.get("latest_long_end_fingerprint")

    watches = {}
    for item in remote.get("yield_persistence_watches", []) + local.get("yield_persistence_watches", []):
        key = (str(item.get("operation_date")), str(item.get("fingerprint")))
        if key not in watches:
            watches[key] = {**item, "completed_offsets": []}
        offsets = set(watches[key]["completed_offsets"])
        offsets.update(item.get("completed_offsets") or [])
        watches[key]["completed_offsets"] = sorted(offsets)
    merged["yield_persistence_watches"] = [
        watches[key] for key in sorted(watches)[-10:]
    ]
    for field in ("last_checked_kst", "latest_yield_followup_operation_date"):
        merged[field] = max(str(remote.get(field) or ""), str(local.get(field) or ""))
    merged["format_revision"] = max(int(remote.get("format_revision") or 0),
                                    int(local.get("format_revision") or 0))
    pending = merged.get("pending_yield_followup") or {}
    if pending and str(pending.get("operation_date") or "") <= merged.get("latest_yield_followup_operation_date", ""):
        merged.pop("pending_yield_followup", None)
    return merged

def main():
    local = json.loads(STATE.read_text(encoding="utf-8"))
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for attempt in range(5):
        git("fetch", "origin", "main")
        remote = json.loads(git("show", "origin/main:" + STATE.as_posix()).stdout)
        merged = combine(remote, local)
        important = lambda data: {k: v for k, v in data.items() if k != "last_checked_kst"}
        if important(merged) == important(remote):
            print("No meaningful buyback state changes; skip timestamp-only commit")
            return
        git("reset", "--hard", "origin/main")
        STATE.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git("add", STATE.as_posix())
        git("commit", "-m", "Update Treasury buyback execution state")
        pushed = git("push", "origin", "HEAD:main", check=False)
        if pushed.returncode == 0:
            print("Buyback state committed with verified merge")
            return
        print("State push conflict or network issue; retry", attempt + 1)
        time.sleep(attempt + 1)
    raise RuntimeError("Buyback state persistence failed after five safe retries")

if __name__ == "__main__":
    main()

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
    return merged

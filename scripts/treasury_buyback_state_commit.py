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
    return merged

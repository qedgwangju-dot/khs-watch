#!/usr/bin/env python3
"""Merge a delivered radar run's seen keys with the latest remote state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"seen": {}, "updated_at_kst": ""}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("seen"), dict):
        raise ValueError(f"Invalid radar seen state: {path}")
    return state


def lanes_for(entry: dict) -> dict[str, str]:
    lanes = entry.get("lanes")
    if isinstance(lanes, dict):
        return {str(key): str(value) for key, value in lanes.items()}
    if isinstance(lanes, list):
        return {str(key): str(entry.get("first_seen_kst") or "") for key in lanes}
    return {"legacy": str(entry.get("first_seen_kst") or "")}


def merge_entry(remote: dict, pending: dict) -> dict:
    remote_last = str(remote.get("last_seen_kst") or remote.get("first_seen_kst") or "")
    pending_last = str(pending.get("last_seen_kst") or pending.get("first_seen_kst") or "")
    newer, older = (pending, remote) if pending_last >= remote_last else (remote, pending)
    merged = {**older, **newer}
    first_times = [str(value) for value in (remote.get("first_seen_kst"), pending.get("first_seen_kst")) if value]
    if first_times:
        merged["first_seen_kst"] = min(first_times)
    merged["last_seen_kst"] = max(remote_last, pending_last)
    lanes = lanes_for(remote)
    for lane, timestamp in lanes_for(pending).items():
        lanes[lane] = max(lanes.get(lane, ""), timestamp)
    merged["lanes"] = lanes
    return merged


def merge_states(remote: dict, pending: dict) -> dict:
    merged = {**pending, **remote}
    seen = dict(remote["seen"])
    for key, entry in pending["seen"].items():
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid pending seen entry: {key}")
        if key in seen:
            if not isinstance(seen[key], dict):
                raise ValueError(f"Invalid remote seen entry: {key}")
            seen[key] = merge_entry(seen[key], entry)
        else:
            seen[key] = entry
    merged["seen"] = seen
    merged["updated_at_kst"] = max(
        str(remote.get("updated_at_kst") or ""), str(pending.get("updated_at_kst") or "")
    )
    return merged


def delivery_receipt_allows_seen_persistence(receipt: dict) -> bool:
    return (receipt.get('status') == 'sent' and not receipt.get('error')
            and type(receipt.get('message_id')) is int and receipt['message_id'] > 0
            and type(receipt.get('sent_chars')) is int and receipt['sent_chars'] > 0
            and type(receipt.get('attempts')) is int and receipt['attempts'] > 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pending", type=Path)
    parser.add_argument("remote", type=Path)
    args = parser.parse_args()
    if not args.pending.exists():
        raise FileNotFoundError(args.pending)
    merged = merge_states(load_state(args.remote), load_state(args.pending))
    args.remote.parent.mkdir(parents=True, exist_ok=True)
    args.remote.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

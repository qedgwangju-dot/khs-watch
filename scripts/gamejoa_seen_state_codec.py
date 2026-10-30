#!/usr/bin/env python3
"""Compactly persist the radar's many lookup keys without duplicating entries."""

from __future__ import annotations

import copy
import hashlib
import json


FORMAT_KEY = "_storage_format"
FORMAT_VALUE = "gamejoa-seen-index-v2"


def decode_seen_state(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid GAMEJOA seen state: expected an object")
    if payload.get(FORMAT_KEY) != FORMAT_VALUE:
        state = copy.deepcopy(payload)
        if not isinstance(state.get("seen", {}), dict):
            raise ValueError("Invalid GAMEJOA seen state: seen must be an object")
        state.setdefault("seen", {})
        return state

    index = payload.get("seen")
    entries = payload.get("entries")
    if not isinstance(index, dict) or not isinstance(entries, dict):
        raise ValueError("Invalid compact GAMEJOA seen state")
    seen = {}
    for key, entry_id in index.items():
        if not isinstance(entry_id, str) or entry_id not in entries:
            raise ValueError(f"Invalid compact GAMEJOA seen entry reference: {key}")
        seen[key] = copy.deepcopy(entries[entry_id])
    state = {key: copy.deepcopy(value) for key, value in payload.items()
             if key not in {FORMAT_KEY, "entries", "seen"}}
    state["seen"] = seen
    return state


def encode_seen_state(state: dict) -> dict:
    if not isinstance(state, dict) or not isinstance(state.get("seen"), dict):
        raise ValueError("Invalid GAMEJOA seen state: seen must be an object")
    entries = {}
    index = {}
    for key, value in sorted(state["seen"].items()):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        entry_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        collision = 0
        while entry_id in entries and entries[entry_id] != value:
            collision += 1
            entry_id = f"{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}-{collision}"
        entries.setdefault(entry_id, value)
        index[str(key)] = entry_id

    compact = {key: value for key, value in state.items()
               if key not in {FORMAT_KEY, "entries", "seen"}}
    compact[FORMAT_KEY] = FORMAT_VALUE
    compact["entries"] = entries
    compact["seen"] = index
    return compact


def dumps_seen_state(state: dict) -> str:
    return json.dumps(encode_seen_state(state), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n"

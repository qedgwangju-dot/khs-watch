#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys


MAX_SEEN = 2500


def load_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def merge_states(current: dict, pending: dict) -> dict:
    """Merge pending watcher state into the latest main-branch state without losing seen IDs."""
    merged = dict(current)
    for key, value in pending.items():
        if key != "seen":
            merged[key] = value

    current_seen = current.get("seen") if isinstance(current.get("seen"), dict) else {}
    pending_seen = pending.get("seen") if isinstance(pending.get("seen"), dict) else {}
    seen = dict(current_seen)

    for key, value in pending_seen.items():
        old = seen.get(key)
        if old is None or str(value) > str(old):
            seen[key] = value

    if len(seen) > MAX_SEEN:
        ordered = sorted(seen.items(), key=lambda kv: str(kv[1]), reverse=True)[:MAX_SEEN]
        seen = dict(ordered)

    merged["seen"] = seen

    created = [x for x in (current.get("created_at"), pending.get("created_at")) if x]
    if created:
        merged["created_at"] = min(map(str, created))

    updated = [x for x in (current.get("updated_at"), pending.get("updated_at")) if x]
    if updated:
        merged["updated_at"] = max(map(str, updated))

    versions = []
    for value in (current.get("version"), pending.get("version")):
        try:
            versions.append(int(value))
        except (TypeError, ValueError):
            pass
    if versions:
        merged["version"] = max(versions)

    merged.pop("recovered", None)
    return merged


def write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def self_test() -> int:
    current = {
        "version": 1,
        "created_at": "2026-10-07T00:00:00+00:00",
        "updated_at": "2026-10-07T01:00:00+00:00",
        "seen": {"a": "2026-10-07T01:00:00+00:00", "shared": "2026-10-07T01:00:00+00:00"},
    }
    pending = {
        "version": 1,
        "created_at": "2026-10-07T00:30:00+00:00",
        "updated_at": "2026-10-07T02:00:00+00:00",
        "seen": {"b": "2026-10-07T02:00:00+00:00", "shared": "2026-10-07T02:00:00+00:00"},
    }
    merged = merge_states(current, pending)
    assert set(merged["seen"]) == {"a", "b", "shared"}
    assert merged["seen"]["shared"] == "2026-10-07T02:00:00+00:00"
    assert merged["created_at"] == "2026-10-07T00:00:00+00:00"
    assert merged["updated_at"] == "2026-10-07T02:00:00+00:00"
    print("space_launch_state_merge_self_test=ok")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()

    if len(sys.argv) != 4:
        print(
            "usage: merge_space_launch_state.py CURRENT_STATE PENDING_STATE OUTPUT_STATE | --self-test",
            file=sys.stderr,
        )
        return 2

    current_path = pathlib.Path(sys.argv[1])
    pending_path = pathlib.Path(sys.argv[2])
    output_path = pathlib.Path(sys.argv[3])

    pending = load_json(pending_path)
    if not pending:
        raise RuntimeError("pending state is missing or invalid")

    current = load_json(current_path)
    merged = merge_states(current, pending)
    write_json(output_path, merged)
    print(f"space_launch_state_merged=true seen={len(merged.get('seen', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

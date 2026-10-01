#!/usr/bin/env python3
"""Fair article retrieval with metadata-only history and same-run receipts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "gamejoa_article_detail_queue.json"
PENDING_PATH = ROOT / "out" / "gamejoa_article_detail_queue_pending.json"
CACHE_PATH = ROOT / "out" / "gamejoa_article_detail_run_cache.json"
RETENTION = dt.timedelta(days=3)


def parse_time(value) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        result = value
    else:
        try:
            result = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    return result if result.tzinfo else result.replace(tzinfo=dt.timezone.utc)


def article_key(row: dict) -> str:
    return hashlib.sha256(str(row.get("link") or "").strip().encode()).hexdigest()


def fingerprint(row: dict) -> str:
    title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip().lower()
    published = parse_time(row.get("published"))
    stamp = published.astimezone(dt.timezone.utc).isoformat() if published else ""
    return hashlib.sha256(f"{title}|{stamp}".encode()).hexdigest()


def load_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"version": 1, "entries": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("entries"), dict):
        raise ValueError(f"Invalid article-detail queue: {path}")
    return state


def prune_state(state: dict, now: dt.datetime) -> dict:
    return {"version": 1, "updated_kst": now.isoformat(timespec="seconds"), "entries": {
        key: dict(entry)
        for key, entry in state.get("entries", {}).items()
        if isinstance(entry, dict)
        and (parse_time(entry.get("last_discovered_kst")) or now) >= now - RETENTION
    }}


def plan_details(
    rows: list[dict], state: dict, now: dt.datetime, limit: int, *, respect_cooldown: bool = True,
) -> tuple[list[dict], dict, dict]:
    if limit < 1:
        raise ValueError("Article retrieval budget must be positive")
    pending = prune_state(state, now)
    eligible = []
    cooling = 0
    for row in rows:
        row.pop("_detail_deferred_reason", None)
        key = article_key(row)
        signature = fingerprint(row)
        old = pending["entries"].get(key, {})
        if old.get("fingerprint") != signature:
            old = {"first_discovered_kst": now.isoformat(timespec="seconds"), "attempts": 0}
        entry = {**old, "url": row.get("link"), "title": row.get("title"),
                 "fingerprint": signature, "last_discovered_kst": now.isoformat(timespec="seconds")}
        pending["entries"][key] = entry
        due = parse_time(entry.get("retry_after_kst"))
        if respect_cooldown and due and due > now:
            cooling += 1
            row["_detail_deferred_reason"] = "retry_cooldown"
            continue
        eligible.append(row)

    # Keep room for urgent candidates while guaranteeing progress for the
    # oldest waiting articles, independent of company-name keyword scores.
    priority_slots = max(1, limit // 2)
    selected = eligible[:priority_slots]
    chosen = {article_key(row) for row in selected}
    waiting = [row for row in eligible if article_key(row) not in chosen]
    waiting.sort(key=lambda row: (
        parse_time(pending["entries"][article_key(row)].get("last_attempt_kst"))
        or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        parse_time(pending["entries"][article_key(row)].get("first_discovered_kst")) or now,
        parse_time(row.get("published")) or now,
        article_key(row),
    ))
    selected.extend(waiting[:max(0, limit - len(selected))])
    chosen = {article_key(row) for row in selected}
    for row in eligible:
        if article_key(row) not in chosen:
            row["_detail_deferred_reason"] = "retrieval_budget"
    return selected, pending, {
        "eligible": len(eligible), "cooling": cooling,
        "fair_slots": max(0, len(selected) - min(priority_slots, len(selected))),
        "deferred": len(rows) - len(selected),
    }


def record_attempt(state: dict, row: dict, now: dt.datetime, *, verified: bool, error: str = "") -> None:
    entry = state["entries"][article_key(row)]
    attempts = int(entry.get("attempts") or 0) + 1
    failures = 0 if verified else int(entry.get("consecutive_failures") or 0) + 1
    minutes = 60 if verified else (5, 15, 60, 120)[min(failures - 1, 3)]
    entry.update({
        "attempts": attempts, "consecutive_failures": failures,
        "last_attempt_kst": now.isoformat(timespec="seconds"),
        "retry_after_kst": (now + dt.timedelta(minutes=minutes)).isoformat(timespec="seconds"),
        "verification_status": "verified" if verified else "failed",
        "last_error": error[:350],
    })


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_run_cache(now: dt.datetime, path: Path = CACHE_PATH) -> dict:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id or not path.exists():
        return {"run_id": run_id, "receipts": {}}
    cache = json.loads(path.read_text(encoding="utf-8"))
    if cache.get("run_id") != run_id:
        return {"run_id": run_id, "receipts": {}}
    if not isinstance(cache.get("receipts"), dict):
        raise ValueError("Invalid same-run article receipts")
    cache["receipts"] = {
        key: entry for key, entry in cache["receipts"].items()
        if isinstance(entry, dict) and parse_time(entry.get("query_time_kst"))
        and dt.timedelta() <= now - parse_time(entry["query_time_kst"]) <= dt.timedelta(minutes=15)
    }
    return cache


def cached_receipt(cache: dict, row: dict) -> dict | None:
    entry = cache.get("receipts", {}).get(article_key(row))
    if entry and entry.get("fingerprint") == fingerprint(row):
        return entry
    return None


def merge_state(pending: dict, current: dict, now: dt.datetime) -> dict:
    merged = prune_state(current, now)
    for key, incoming in prune_state(pending, now)["entries"].items():
        existing = merged["entries"].get(key)
        if not existing:
            merged["entries"][key] = incoming
            continue
        incoming_discovery = parse_time(incoming.get("last_discovered_kst"))
        existing_discovery = parse_time(existing.get("last_discovered_kst"))
        if incoming.get("fingerprint") != existing.get("fingerprint"):
            if incoming_discovery and (not existing_discovery or incoming_discovery >= existing_discovery):
                merged["entries"][key] = incoming
            continue
        incoming_attempt = parse_time(incoming.get("last_attempt_kst"))
        existing_attempt = parse_time(existing.get("last_attempt_kst"))
        entry = dict(incoming if incoming_attempt and (
            not existing_attempt or incoming_attempt >= existing_attempt
        ) else existing)
        if incoming_discovery and (not existing_discovery or incoming_discovery > existing_discovery):
            entry["last_discovered_kst"] = incoming["last_discovered_kst"]
        merged["entries"][key] = entry
    return merged


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: gamejoa_article_detail_queue.py pending.json current.json")
    source, destination = map(Path, sys.argv[1:])
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    merged = merge_state(load_state(source), load_state(destination), now)
    save_json(destination, merged)
    print(f"GAMEJOA article-detail queue persisted: entries={len(merged['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

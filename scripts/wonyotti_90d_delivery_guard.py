#!/usr/bin/env python3
"""Watcher-local durable Telegram attempt ledger. No shared alert code is modified."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
LEDGER = ROOT / "data" / "wonyotti_90d_thesis_delivery_ledger.json"
META = OUT / "wonyotti_90d_thesis_delivery_meta.json"
RECEIPT = OUT / "wonyotti_90d_thesis_delivery_receipt.json"
TEST = OUT / "wonyotti_90d_thesis_connection_test.html"


def load_ledger(path: pathlib.Path = LEDGER) -> dict:
    if not path.exists():
        return {"pending": {}, "delivered": {}}
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("pending"), dict) or not isinstance(obj.get("delivered"), dict):
        raise ValueError("Invalid Wonyotti delivery ledger; fail closed")
    return obj


def blocked_keys(path: pathlib.Path = LEDGER) -> set[str]:
    state = load_ledger(path)
    return set(state["pending"]) | set(state["delivered"])


def sh(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def sync_ledger(keys: list[str], operation: str, receipt: dict | None = None) -> None:
    run_id = str(os.environ.get("GITHUB_RUN_ID") or "")
    if not run_id:
        raise RuntimeError("No GitHub run id; refusing Telegram delivery")
    sh("git", "config", "user.name", "wonyotti-thesis-watch[bot]")
    sh("git", "config", "user.email", "wonyotti-thesis-watch[bot]@users.noreply.github.com")
    utc = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for attempt in range(4):
        sh("git", "fetch", "origin", "main")
        sh("git", "reset", "--hard", "origin/main")
        state = load_ledger()
        if operation == "prepare":
            if any(key in state["pending"] or key in state["delivered"] for key in keys):
                raise RuntimeError("Wonyotti delivery already pending/delivered; refusing duplicate")
            for key in keys:
                state["pending"][key] = {"run_id": run_id, "attempted_utc": utc, "status": "unconfirmed"}
        elif operation == "ack":
            ids = (receipt or {}).get("message_ids") or []
            if not ids or not all(isinstance(i, int) and i > 0 for i in ids):
                raise ValueError("Telegram receipt missing valid message_id; fail closed")
            for key in keys:
                existing = state["pending"].get(key) or {}
                if str(existing.get("run_id")) != run_id:
                    raise RuntimeError("Telegram intent mismatch; refusing to claim delivery")
            for key in keys:
                state["pending"].pop(key, None)
                state["delivered"][key] = {"run_id": run_id, "confirmed_utc": utc, "message_ids": ids}
            if len(state["delivered"]) > 2000:
                state["delivered"] = dict(list(state["delivered"].items())[-2000:])
        else:
            raise ValueError("Invalid operation")
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sh("git", "add", str(LEDGER.relative_to(ROOT)))
        try:
            sh("git", "commit", "-m", "Update Wonyotti delivery ledger")
            sh("git", "push", "origin", "HEAD:main")
            print(f"wonyotti_delivery_{operation}_persisted=true run_id={run_id} keys={len(keys)}")
            return
        except subprocess.CalledProcessError as exc:
            if attempt == 3:
                raise RuntimeError("Delivery ledger commit/push failed: do not send or mark delivered") from exc
    raise RuntimeError("Unreachable ledger retry exhaustion")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "ack"}:
        raise SystemExit("Usage: wonyotti_90d_delivery_guard.py prepare|ack")
    action = sys.argv[1]
    if META.exists():
        meta = json.loads(META.read_text(encoding="utf-8"))
        keys = meta.get("keys") or []
    elif TEST.exists():
        keys = [f"route-test:{os.environ.get('GITHUB_RUN_ID', '')}"]
    else:
        raise RuntimeError("No Wonyotti alert metadata; refusing to alter delivery ledger")
    if not keys or not all(isinstance(k, str) and k for k in keys):
        raise RuntimeError("Invalid alert event identities")
    keys = list(dict.fromkeys(keys))
    if action == "prepare":
        sync_ledger(keys, "prepare")
    else:
        if not RECEIPT.exists():
            raise RuntimeError("Missing Telegram receipt; delivery remains unconfirmed")
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        sync_ledger(keys, "ack", receipt)


if __name__ == "__main__":
    main()

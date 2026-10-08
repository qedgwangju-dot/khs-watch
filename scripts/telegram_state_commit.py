#!/usr/bin/env python3
"""Persist a single Telegram watcher state via GitHub Contents API.

Why: "git pull --rebase" does not solve JSON state-file merge conflicts
when many independent GitHub Actions workflows push to the same main branch.

This method retries an optimistic SHA-checked content update, always reading
the current remote version first. An older run cannot roll state backwards.
The caller must invoke it only after safe/no-alert or confirmed Telegram send.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request


ALLOWED = {
    "data/europe_sovereign_yield_state.json",
    "data/ecb_policy_watch_state.json",
}


def _api(url: str, token: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="PUT" if payload is not None else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "khs-watch-telegram-state-save/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as res:
        return json.loads(res.read().decode("utf-8"))


def _when(state: dict) -> dt.datetime | None:
    raw = state.get("last_checked_kst")
    if not raw or not isinstance(raw, str):
        return None
    try:
        ts = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return ts if ts.tzinfo is not None else None
    except ValueError:
        return None


def incoming_superseded(incoming: dict, remote: dict) -> bool:
    """Never roll backwards to a stale run after a newer run committed."""
    local_time, remote_time = _when(incoming), _when(remote)
    return bool(local_time and remote_time and remote_time >= local_time)


def persist(path: pathlib.Path, repo: str, token: str, *, branch: str = "main",
            max_attempts: int = 8, sleep=time.sleep) -> str:
    if path.as_posix() not in ALLOWED:
        raise ValueError("State path is not an approved Telegram watcher state file")
    if not token or not repo:
        raise RuntimeError("GitHub token or repository is missing; state not persisted")
    raw = path.read_text(encoding="utf-8")
    incoming = json.loads(raw)
    if not isinstance(incoming, dict) or not _when(incoming):
        raise ValueError("State must be a JSON object with an offset-aware last_checked_kst")

    api_url = "https://api.github.com/repos/" + repo + "/contents/" + urllib.parse.quote(path.as_posix(), safe="/")
    for attempt in range(1, max_attempts + 1):
        remote_payload = _api(api_url + "?ref=" + urllib.parse.quote(branch), token)
        remote_bytes = base64.b64decode(remote_payload["content"])
        remote = json.loads(remote_bytes.decode("utf-8"))
        if incoming_superseded(incoming, remote):
            print(f"state_save=skip_newer_remote file={path.as_posix()}")
            return "skip_newer_remote"
        if remote == incoming:
            print(f"state_save=no_change file={path.as_posix()}")
            return "no_change"
        data = {
            "message": "Update confirmed Telegram watcher state (SHA-safe)",
            "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
            "sha": remote_payload["sha"],
            "branch": branch,
        }
        try:
            result = _api(api_url, token, data)
            commit = (result.get("commit") or {}).get("sha", "")
            print(f"state_save=success file={path.as_posix()} commit={commit[:12]}")
            return "saved"
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422) or attempt == max_attempts:
                raise
            # Refetch the latest blob SHA. Do not retry a conflicted rebase.
            sleep(min(2 * attempt, 8))
    raise RuntimeError("Cannot persist Telegram watcher state after retries")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path", choices=sorted(ALLOWED))
    args = p.parse_args()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = (os.environ.get("GH_TOKEN") or "").strip()
    persist(pathlib.Path(args.path), repo, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

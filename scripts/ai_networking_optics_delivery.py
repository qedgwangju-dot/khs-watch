"""Receipt checkpoints for the existing optics Telegram route.

No automatic resend follows an unknown send outcome. A confirmed part is saved
before the next part; unfinished bundles keep their exact text and pending state.
Remote Git persistence remains the workflow's responsibility.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
STATE_PATH = Path("data/ai_networking_optics_watch_state.json")
LEDGER_PATH = Path("data/ai_networking_optics_delivery_receipts.json")
ALERT_PATH = Path("out/ai_networking_optics_watch_telegram.html")
PENDING_PATH = Path("out/ai_networking_optics_watch_pending_state.json")
CONFIRMED_PATH = Path("out/ai_networking_optics_watch_telegram_confirmed.json")
PARTIAL_PATH = Path("out/ai_networking_optics_watch_telegram_partial.json")
DELIVERED_PENDING_PATH = Path("out/ai_networking_optics_watch_delivered_pending_state.json")
GUARD_PATH = Path("out/ai_networking_optics_watch_delivery_guard.json")
STATUS_PATH = Path("out/ai_networking_optics_watch_status.md")
WORKFLOW_PATH = ".github/workflows/ai-networking-optics-telegram-watch.yml"
RUNTIME_EVENTS = {"schedule", "workflow_run", "workflow_dispatch"}
FRESHNESS_BACKUP = "AI Security Web Watch"


class DefinitiveRejection(RuntimeError):
    """Telegram explicitly rejected a request; retry is permitted on a later run."""


class AmbiguousDelivery(RuntimeError):
    """A send might have been accepted; automatic resend is prohibited."""


def stamp() -> str:
    return dt.datetime.now(KST).isoformat(timespec="seconds")


def digest(value) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        if default is None:
            raise RuntimeError(f"Required local delivery file missing: {path.name}")
        return copy.deepcopy(default)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid delivery object: {path.name}")
    return value


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def valid_id(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def split_html(text: str, limit: int = 3800) -> list[str]:
    """Split at text/entity boundaries and close/reopen supported HTML tags."""
    if not text.strip():
        raise ValueError("Telegram alert is empty")
    tokens = re.findall(r"<[^>]*>|&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);|[^<&]+|[<&]", text)
    stack: list[tuple[str, str]] = []
    chunks: list[str] = []
    current = ""
    has_text = False
    supported = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "span", "tg-spoiler", "blockquote"}

    def closing() -> str:
        return "".join(f"</{tag}>" for tag, _ in reversed(stack))

    def fits(value: str) -> bool:
        return max(len(value), len(value.encode("utf-16-le")) // 2) <= limit

    def flush() -> None:
        nonlocal current, has_text
        if not has_text:
            raise ValueError("HTML tag overhead exceeds safe Telegram chunk size")
        chunks.append(current + closing())
        current = "".join(raw for _, raw in stack)
        has_text = False

    for token in tokens:
        if token.startswith("<"):
            found = re.fullmatch(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^<>]*)?>", token)
            if not found or found.group(2).lower() not in supported:
                raise ValueError("Unsupported or malformed Telegram HTML tag")
            tag = found.group(2).lower()
            if found.group(1):
                if not stack or stack[-1][0] != tag:
                    raise ValueError("Unbalanced Telegram HTML tags")
                current += token
                stack.pop()
            else:
                suffix = token + f"</{tag}>" + closing()
                if not fits(current + suffix):
                    flush()
                if not fits(current + suffix):
                    raise ValueError("Telegram HTML tag is too long")
                current += token
                stack.append((tag, token))
            continue
        if token.startswith("&") and token != "&":
            if not fits(current + token + closing()):
                flush()
            if not fits(current + token + closing()):
                raise ValueError("Telegram HTML entity is too long")
            current += token
            has_text = True
            continue
        # Escaped ampersands/angles remain indivisible entities; plain text is
        # bounded in UTF-16 units as well as source characters for safe margins.
        for char in token:
            atom = html.escape(char, quote=False) if char in "<&" else char
            proposed = current + atom + closing()
            if not fits(proposed):
                flush()
            if not fits(current + atom + closing()):
                raise ValueError("Telegram HTML tag overhead is too long")
            current += atom
            has_text = True
    if stack:
        raise ValueError("Unclosed Telegram HTML tag")
    if has_text:
        chunks.append(current)
    return chunks


def merge_ledgers(base: dict, incoming: dict) -> dict:
    result = copy.deepcopy(base)
    result.setdefault("version", 1)
    holds = result.setdefault("recovery_holds", {})
    for key, hold in incoming.get("recovery_holds", {}).items():
        previous = holds.get(key, {})
        if str(hold.get("checked_at_kst", "")) >= str(previous.get("checked_at_kst", "")):
            holds[key] = copy.deepcopy(hold)
    cache = result.setdefault("history_cache", {})
    for key, record in incoming.get("history_cache", {}).items():
        old = cache.get(key, {})
        if str(record.get("checked_at_kst", "")) >= str(old.get("checked_at_kst", "")):
            cache[key] = copy.deepcopy(record)
    result["history_cache"] = dict(sorted(cache.items(), key=lambda pair: pair[1].get("checked_at_kst", ""), reverse=True)[:600])
    target = result.setdefault("bundles", {})
    if not isinstance(target, dict) or not isinstance(incoming.get("bundles", {}), dict):
        raise RuntimeError("Invalid optics receipt ledger; refusing to discard it")
    ranks = {"rejected": 0, "in_flight": 1, "ambiguous": 2, "confirmed": 3}
    for key, added in incoming.get("bundles", {}).items():
        if key not in target:
            target[key] = copy.deepcopy(added)
            continue
        old = target[key]
        if old.get("route_key") != added.get("route_key") or old.get("part_hashes") != added.get("part_hashes"):
            raise RuntimeError("Receipt bundle identity conflict")
        if (old.get("state_ancestor_sha256") and added.get("state_ancestor_sha256")
                and old["state_ancestor_sha256"] != added["state_ancestor_sha256"]):
            raise RuntimeError("Receipt bundle state ancestor conflict")
        merged = {**copy.deepcopy(old), **copy.deepcopy(added)}
        receipts = copy.deepcopy(old.get("receipts", {}))
        for index, receipt in added.get("receipts", {}).items():
            existing = receipts.get(index, {})
            if (existing.get("status") == receipt.get("status") == "confirmed"
                    and existing.get("message_id") != receipt.get("message_id")):
                raise RuntimeError("Conflicting confirmed message ids; refusing to hide a duplicate")
            if ranks.get(receipt.get("status"), -1) >= ranks.get(existing.get("status"), -1):
                receipts[index] = copy.deepcopy(receipt)
        merged["receipts"] = receipts
        complete = len(receipts) == len(merged["part_hashes"]) and all(
            row.get("status") == "confirmed" and valid_id(row.get("message_id")) for row in receipts.values())
        merged["status"] = "complete" if complete else (
            "ambiguous" if any(row.get("status") in {"ambiguous", "in_flight"} for row in receipts.values()) else "partial")
        if old.get("state_persisted") is True or added.get("state_persisted") is True:
            merged["state_persisted"] = True
            merged.pop("parts", None)
            merged.pop("pending_state", None)
            merged.pop("state_ancestor", None)
        target[key] = merged
    return result


def timestamp(value: str | None) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def runtime_preflight(*, event_name: str, event: dict, state: dict,
                      repository: str, now: dt.datetime) -> dict:
    """Apply the 25-minute freshness gate only to the new backup trigger."""
    upstream = event.get("workflow_run") or {}
    if event_name != "workflow_run" or upstream.get("name") != FRESHNESS_BACKUP:
        return {"run_watch": True, "reason": "existing_trigger_preserved"}
    trusted = (event.get("repository", {}).get("full_name") == repository
        and upstream.get("head_repository", {}).get("full_name") == repository
        and upstream.get("head_branch") == "main" and upstream.get("conclusion") == "success"
        and upstream.get("event") in {"schedule", "workflow_run"})
    if not trusted:
        return {"run_watch": False, "reason": "backup_event_not_allowed"}
    checked = timestamp(state.get("last_checked_kst"))
    age = (now - checked).total_seconds() if checked is not None else None
    if age is not None and 0 <= age < 25 * 60:
        return {"run_watch": False, "reason": "freshness_skip", "age_seconds": round(age)}
    return {"run_watch": True, "reason": "backup_check_due", "age_seconds": round(age) if age is not None else None}


def preflight_command() -> None:
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    event = read_json(Path(os.environ["GITHUB_EVENT_PATH"])) if event_name == "workflow_run" else {}
    result = runtime_preflight(event_name=event_name, event=event, state=read_json(STATE_PATH, {}),
        repository=os.getenv("GITHUB_REPOSITORY", ""), now=dt.datetime.now(dt.timezone.utc))
    output = os.getenv("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("Runtime preflight has no GitHub output channel")
    with Path(output).open("a", encoding="utf-8") as stream:
        stream.write("run_watch=" + str(result["run_watch"]).lower() + "\nreason=" + result["reason"] + "\n")
    if not result["run_watch"]:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text("# AI 네트워킹·광통신 감시 상태\n\n"
            + "- 실행 상태: " + result["reason"] + "\n"
            + "- 새 백업 실행 조건: 같은 저장소 main의 정상 완료 및 마지막 확인 후 25분 경과\n"
            + "- 수집·송신·상태 커밋: 실행하지 않음\n", encoding="utf-8")
    print("optics_runtime_preflight=" + json.dumps(result, sort_keys=True))


def audit_previous_runs(*, current: dict, runs: list[dict], load_jobs, ledger: dict,
                        state: dict, repository: str, expected_bot: str) -> dict:
    """Hold a prior attempted delivery whose state/receipt commit is unproven.

    A later *actual* confirmed delivery and successful persistence can reconcile
    an older failure. A successful source check or an empty sender step cannot.
    Unresolved holds remain in the ledger after the API's recent window moves on.
    """
    def trusted(run):
        return (run.get("repository", {}).get("full_name") == repository
                and run.get("head_repository", {}).get("full_name") == repository
                and run.get("workflow_id") == current.get("workflow_id")
                and str(run.get("path", "")).split("@")[0] == WORKFLOW_PATH
                and run.get("head_branch") == "main" and run.get("event") in RUNTIME_EVENTS)

    if not trusted(current) or not valid_id(current.get("id")) or not valid_id(current.get("workflow_id")):
        raise RuntimeError("Delivery history guard cannot verify this repository/workflow/main runtime")
    observations = []
    holds = ledger.setdefault("recovery_holds", {})
    cache = ledger.setdefault("history_cache", {})
    received = timestamp(state.get("last_successful_delivery_kst"))
    receipt_valid = (received is not None and state.get("telegram_chat_identity_verified") is True
        and str(state.get("bot_username", "")).lower() == expected_bot.lstrip("@").lower()
        and bool(state.get("telegram_message_ids")) and all(valid_id(n) for n in state.get("telegram_message_ids", [])))
    anchor = None
    queries = 0
    cache_hits = 0

    def inspect_attempt(run, attempt):
        nonlocal queries, cache_hits
        key = f"{run['id']}:{attempt}"
        fingerprint = digest({"repository": repository, "workflow_id": run["workflow_id"],
            "path": run["path"], "head_sha": run.get("head_sha"), "event": run["event"],
            "head_branch": run["head_branch"], "attempt_key": key})
        cached = cache.get(key, {})
        valid = cached.get("fingerprint") == fingerprint
        if valid and (cached.get("outcome") == "no_send" or (
                cached.get("outcome") == "attempted" and isinstance(cached.get("saved"), bool)
                and isinstance(cached.get("sent_success"), bool) and timestamp(cached.get("started"))
                and timestamp(cached.get("completed")))):
            cache_hits += 1
            return cached
        queries += 1
        if queries > 100:
            raise RuntimeError("Delivery history exceeds 100 uncached attempt checks; automatic send held")
        jobs = load_jobs(run["id"], attempt)
        monitor = [job for job in jobs if job.get("name") == "monitor"]
        if len(monitor) != 1 or monitor[0].get("run_id") != run["id"]:
            raise RuntimeError("Delivery history monitor identity could not be verified")
        job = monitor[0]
        if job.get("status") != "completed":
            raise RuntimeError("Prior delivery attempt still incomplete; automatic send held")
        steps = {step.get("name"): step for step in job.get("steps", [])}
        sent = steps.get("Send meaningful new signal to exact requested Telegram bot")
        record = {"fingerprint": fingerprint, "checked_at_kst": stamp(), "outcome": "no_send"}
        if sent is not None and sent.get("conclusion") != "skipped":
            started = timestamp(sent.get("started_at") or job.get("started_at"))
            completed = timestamp(sent.get("completed_at") or job.get("completed_at"))
            if started is None or completed is None or completed < started:
                raise RuntimeError("Prior sender timing unknown; automatic send held")
            persisted = steps.get("Persist baseline or delivered state", {})
            committed = steps.get("Commit watcher state and part receipts", steps.get("Commit watcher state", {}))
            saved = persisted.get("conclusion") == committed.get("conclusion") == "success"
            legacy_record = steps.get("Record confirmed Telegram delivery in watcher state")
            if sent.get("conclusion") == "success" and legacy_record is not None:
                saved = saved and legacy_record.get("conclusion") == "success"
            record.update(outcome="attempted", started=started.isoformat(), completed=completed.isoformat(),
                saved=saved, sent_success=sent.get("conclusion") == "success")
        cache[key] = record
        return record

    seen_attempts = set()
    candidates = [current] + [run for run in runs if run.get("id") != current["id"]]
    candidates.sort(key=lambda run: timestamp(run.get("run_started_at") or run.get("created_at"))
                    or dt.datetime.max.replace(tzinfo=dt.timezone.utc), reverse=True)
    for run in candidates:
        if run.get("event") not in RUNTIME_EVENTS or run.get("head_branch") != "main":
            continue
        if not trusted(run):
            raise RuntimeError("Delivery history contains an unverified workflow identity")
        latest_started = timestamp(run.get("run_started_at") or run.get("created_at"))
        if anchor is not None and latest_started is not None and latest_started < anchor:
            continue  # A newer confirmed receipt/commit already reconciles it.
        is_current = run["id"] == current["id"]
        if not is_current and run.get("status") != "completed":
            continue
        latest = run.get("run_attempt", 1)
        if not valid_id(latest) or latest > 10:
            raise RuntimeError("Delivery history attempts exceed verified bounds; manual review required")
        for attempt in range(latest - 1 if is_current else latest, 0, -1):
            identity = (run["id"], attempt)
            if identity in seen_attempts:
                continue
            seen_attempts.add(identity)
            record = inspect_attempt(run, attempt)
            if record["outcome"] == "no_send":
                continue  # Includes source 503 failures before any sender ran.
            started, completed = timestamp(record["started"]), timestamp(record["completed"])
            saved = record["saved"]
            observations.append({"key": f"{run['id']}:{attempt}", "run_id": run["id"],
                "run_attempt": attempt, "started": started, "completed": completed,
                "url": f"https://github.com/{repository}/actions/runs/{run['id']}/attempts/{attempt}",
                "saved": saved, "sent_success": record["sent_success"]})
            if (saved and record["sent_success"] and receipt_valid
                    and started - dt.timedelta(seconds=5) <= received <= completed + dt.timedelta(seconds=5)):
                anchor = max(anchor, completed) if anchor is not None else completed
            if not saved:
                row = observations[-1]
                holds[row["key"]] = {"run_id": row["run_id"], "run_attempt": row["run_attempt"],
                    "url": row["url"], "started_at": started.isoformat(), "status": "unresolved",
                    "reason": "sender_attempted_but_state_or_receipt_commit_unconfirmed", "checked_at_kst": stamp()}
    anchors = [row for row in observations if row["saved"] and row["sent_success"] and receipt_valid
               and row["started"] - dt.timedelta(seconds=5) <= received <= row["completed"] + dt.timedelta(seconds=5)]
    anchor = max((row["completed"] for row in anchors), default=None)
    for row in observations:
        if not row["saved"] and (anchor is None or row["started"] > anchor):
            holds[row["key"]] = {"run_id": row["run_id"], "run_attempt": row["run_attempt"],
                "url": row["url"], "started_at": row["started"].isoformat(), "status": "unresolved",
                "reason": "sender_attempted_but_state_or_receipt_commit_unconfirmed", "checked_at_kst": stamp()}
    for hold in holds.values():
        when = timestamp(hold.get("started_at"))
        if hold.get("status") == "unresolved" and anchor is not None and when is not None and when < anchor:
            hold.update(status="reconciled", resolution="later_verified_delivery_and_commit", checked_at_kst=stamp())
    unresolved = [row for row in holds.values() if row.get("status") == "unresolved"]
    if unresolved:
        first = min(unresolved, key=lambda row: row.get("started_at", ""))
        raise AmbiguousDelivery("Prior delivery persistence is unconfirmed; automatic send held for manual receipt review: " + first["url"])
    return {"checked_attempts": len(seen_attempts), "queried_attempts": queries, "cached_attempts": cache_hits, "recent_runs_listed": len(runs),
            "receipt_anchor_verified": bool(anchors), "unresolved_holds": 0}


def guard_command() -> None:
    if os.getenv("GITHUB_EVENT_NAME") not in RUNTIME_EVENTS:
        raise RuntimeError("This event is validation-only; delivery history guard refused")
    GUARD_PATH.unlink(missing_ok=True)
    repository, run_id = os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_RUN_ID", "")
    token = os.getenv("GITHUB_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not run_id.isdigit() or not token:
        raise RuntimeError("GitHub history identity/token unavailable; automatic send held")
    deadline = time.monotonic() + 55

    def fetch(path):
        if time.monotonic() >= deadline:
            raise RuntimeError("GitHub history verification time budget exceeded; automatic send held")
        request = urllib.request.Request("https://api.github.com/repos/" + repository + path,
            headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "optics-delivery-history-guard"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                value = json.loads(response.read().decode("utf-8"))
        except Exception:
            raise RuntimeError("GitHub Actions history lookup failed; automatic send held (actions:read required)") from None
        if not isinstance(value, dict):
            raise RuntimeError("Malformed GitHub history response; automatic send held")
        return value

    current = fetch("/actions/runs/" + run_id)
    if (current.get("id") != int(run_id) or str(current.get("run_attempt", 1)) != os.getenv("GITHUB_RUN_ATTEMPT", "1")
            or current.get("event") != os.getenv("GITHUB_EVENT_NAME")):
        raise RuntimeError("GitHub runtime attempt identity changed; automatic send held")
    history = fetch("/actions/workflows/ai-networking-optics-telegram-watch.yml/runs?branch=main&status=completed&per_page=100")
    if not isinstance(history.get("workflow_runs"), list):
        raise RuntimeError("GitHub recent workflow history missing; automatic send held")

    def jobs(identifier, attempt):
        value = fetch(f"/actions/runs/{identifier}/attempts/{attempt}/jobs?per_page=100")
        rows = value.get("jobs")
        if not isinstance(rows, list) or value.get("total_count") != len(rows):
            raise RuntimeError("GitHub attempt job history incomplete; automatic send held")
        return rows

    ledger = read_json(LEDGER_PATH, {"version": 1, "bundles": {}})
    try:
        result = audit_previous_runs(current=current, runs=history["workflow_runs"], load_jobs=jobs,
            ledger=ledger, state=read_json(STATE_PATH, {}), repository=repository,
            expected_bot=os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME", ""))
    finally:
        # Keep unresolved holds beyond the recent-100-run API window.
        atomic_json(LEDGER_PATH, ledger)
    source_sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
    atomic_json(GUARD_PATH, {"status": "verified", "run_id": run_id,
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "1"), "source_sha": source_sha,
        "checked_at_kst": stamp(), **result})
    print("optics_delivery_history=verified " + json.dumps(result, sort_keys=True))


def merge_watch_state(base: dict, incoming: dict, ancestor: dict | None = None) -> dict:
    """Apply the report snapshot; three-way merge only concurrent Git updates.

    Intentional dedupe cleanup must survive: blindly unioning an old baseline
    would restore records the watcher deliberately removed as false positives.
    """
    newer_incoming = str(incoming.get("last_checked_kst", "")) >= str(base.get("last_checked_kst", ""))
    result = {**copy.deepcopy(base), **copy.deepcopy(incoming)} if newer_incoming else {**copy.deepcopy(incoming), **copy.deepcopy(base)}
    for key, limit in (("seen_keys", 1500), ("seen_story_keys", 500), ("seen_story_records", 500)):
        if ancestor is None:
            if key in incoming:
                result[key] = copy.deepcopy(incoming[key])
            continue
        ancestor_ids = {digest(row) for row in ancestor.get(key, [])}
        incoming_ids = {digest(row) for row in incoming.get(key, [])}
        base_ids = {digest(row) for row in base.get(key, [])}
        removed = (ancestor_ids - incoming_ids) | (ancestor_ids - base_ids)
        values, identities = [], set()
        for row in list(incoming.get(key, [])) + list(base.get(key, [])):
            identity = digest(row)
            if identity not in identities and identity not in removed:
                values.append(row)
                identities.add(identity)
        if key in incoming or key in base:
            result[key] = values[:limit]
    for key in set(base) | set(incoming):
        if key.endswith("version") and isinstance(base.get(key), int) and isinstance(incoming.get(key), int):
            result[key] = max(base[key], incoming[key])
    for key in ("last_successful_delivery_kst", "telegram_message_ids", "bot_username", "telegram_chat_identity_verified"):
        source = incoming if str(incoming.get("last_successful_delivery_kst", "")) >= str(base.get("last_successful_delivery_kst", "")) else base
        if key in source:
            result[key] = copy.deepcopy(source[key])
    return result


def deliver_bundle(*, text: str | None, pending_state: dict | None, ledger: dict,
                   route_key: str, bot_username: str, source_sha: str,
                   send, checkpoint, state_ancestor: dict | None = None) -> tuple[dict | None, dict | None]:
    bundles = ledger.setdefault("bundles", {})
    if not isinstance(bundles, dict):
        raise RuntimeError("Invalid optics receipt ledger")
    active = [(key, entry) for key, entry in bundles.items()
              if entry.get("route_key") == route_key and entry.get("state_persisted") is not True]
    # Any unknown acceptance blocks automatic delivery on this route, even if
    # fresh source content changed the report text in the meantime.
    if any(any(r.get("status") in {"ambiguous", "in_flight"} for r in entry.get("receipts", {}).values()) for _, entry in active):
        raise AmbiguousDelivery("Prior Telegram outcome unknown; automatic resend held")
    if active:
        key, entry = min(active, key=lambda pair: pair[1].get("created_at_kst", ""))
        if "parts" not in entry or "pending_state" not in entry:
            raise RuntimeError("Unfinished delivery bundle lacks its pinned payload")
    elif text:
        if pending_state is None:
            raise RuntimeError("Alert has no matching pending state")
        parts = split_html(text)
        key = digest(route_key + "|" + text)
        if key in bundles:
            entry = bundles[key]
            # A complete persisted receipt can satisfy an exact-payload retry
            # without writing over any prior receipt or re-sending any part.
            if entry.get("status") != "complete":
                raise RuntimeError("Unexpected inactive optics bundle state")
        else:
            if not isinstance(state_ancestor, dict):
                raise RuntimeError("New delivery bundle lacks its original watch state; automatic send held")
            entry = {"route_key": route_key, "bot_username": bot_username,
                     "source_sha": source_sha, "created_at_kst": stamp(), "status": "pending",
                     "parts": parts, "part_hashes": [digest(part) for part in parts],
                     "pending_state": copy.deepcopy(pending_state), "receipts": {}, "state_persisted": False,
                     "state_ancestor": copy.deepcopy(state_ancestor), "state_ancestor_sha256": digest(state_ancestor)}
            bundles[key] = entry
            checkpoint({"status": "pending", "bundle_key": key})
    else:
        return None, None
    already_persisted = entry.get("state_persisted") is True
    if not already_persisted:
        pinned_ancestor = entry.get("state_ancestor")
        if (not isinstance(pinned_ancestor, dict)
                or entry.get("state_ancestor_sha256") != digest(pinned_ancestor)):
            raise RuntimeError("Unfinished delivery lacks a verified original watch state; automatic resend held for manual review")
    pinned_pending = copy.deepcopy(entry.get("pending_state", pending_state))
    if pinned_pending is None:
        raise RuntimeError("No pending snapshot available for confirmed bundle")
    parts = entry["parts"] if "parts" in entry else (split_html(text) if text else [])
    for index, part_hash in enumerate(entry["part_hashes"]):
        receipt = entry["receipts"].get(str(index), {})
        if receipt.get("status") == "confirmed":
            if not valid_id(receipt.get("message_id")):
                raise RuntimeError("Invalid saved part message id")
            continue
        if receipt.get("status") in {"ambiguous", "in_flight"}:
            raise AmbiguousDelivery("Telegram acceptance is unknown; automatic resend held")
        if index >= len(parts) or digest(parts[index]) != part_hash:
            raise RuntimeError("Pinned Telegram payload hash mismatch")
        entry["receipts"][str(index)] = {"status": "in_flight", "started_at_kst": stamp()}
        entry["status"] = "in_flight"
        checkpoint({"status": "in_flight", "bundle_key": key, "part_index": index})
        try:
            message_id = send(parts[index])
            if not valid_id(message_id):
                raise AmbiguousDelivery("Telegram returned no valid positive integer message id")
        except DefinitiveRejection:
            entry["receipts"][str(index)] = {"status": "rejected", "checked_at_kst": stamp()}
            entry["status"] = "partial"
            checkpoint({"status": "partial", "bundle_key": key, "part_index": index})
            raise
        except Exception:
            entry["receipts"][str(index)] = {"status": "ambiguous", "checked_at_kst": stamp()}
            entry["status"] = "ambiguous"
            checkpoint({"status": "ambiguous", "bundle_key": key, "part_index": index})
            raise AmbiguousDelivery("Telegram acceptance could not be confirmed; automatic resend held") from None
        entry["receipts"][str(index)] = {"status": "confirmed", "message_id": message_id,
            "confirmed_at_kst": stamp(), "chat_identity_verified": True, "source_sha": source_sha}
        entry["status"] = "partial"
        # If this disk write fails, stop before attempting any next part. The
        # previous durable in-flight marker then prevents an unsafe blind retry.
        checkpoint({"status": "partial", "bundle_key": key, "part_index": index})
    ids = [entry["receipts"][str(index)]["message_id"] for index in range(len(entry["part_hashes"]))]
    entry["status"] = "complete"
    entry.setdefault("confirmed_at_kst", stamp())
    checkpoint({"status": "complete", "bundle_key": key})
    return {"status": "confirmed", "bundle_key": key, "bot_username": bot_username,
            "chat_identity_verified": True, "route_key": route_key, "message_ids": ids,
            "confirmed_at_kst": entry["confirmed_at_kst"], "source_sha": entry.get("source_sha", source_sha),
            "sender_source_sha": source_sha,
            "state_already_persisted": already_persisted,
            "state_ancestor_sha256": entry.get("state_ancestor_sha256"),
            "pending_state_sha256": digest(pinned_pending)}, pinned_pending


def _telegram_read(token: str, method: str, values: dict | None = None) -> dict:
    encoded = urllib.parse.urlencode(values or {})
    url = f"https://api.telegram.org/bot{token}/{method}" + ("?" + encoded if encoded else "")
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise RuntimeError(f"Telegram {method} verification failed; no send attempted") from None
    if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("result"), dict):
        raise RuntimeError(f"Telegram {method} did not confirm route identity")
    return result["result"]


def verified_sender(token: str, configured_chat: str, expected: str):
    identity = _telegram_read(token, "getMe")
    username = str(identity.get("username", ""))
    if username.lower() != expected.lstrip("@").lower() or not valid_id(identity.get("id")):
        raise RuntimeError("Telegram bot identity differs from configured route")
    chat = _telegram_read(token, "getChat", {"chat_id": configured_chat})
    actual_chat = chat.get("id")
    if not isinstance(actual_chat, int) or isinstance(actual_chat, bool):
        raise RuntimeError("Telegram chat verification has no valid identifier")
    if configured_chat.lstrip("-").isdigit():
        matches = str(actual_chat) == configured_chat
    else:
        matches = configured_chat.startswith("@") and str(chat.get("username", "")).lower() == configured_chat[1:].lower()
    if not matches:
        raise RuntimeError("Telegram chat identity differs from configured route")
    route_key = digest(f"{identity['id']}|{username.lower()}|{actual_chat}")

    def send(part: str) -> int:
        payload = urllib.parse.urlencode({"chat_id": actual_chat, "text": part,
            "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode("utf-8")
        request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 401, 403, 404, 409, 429}:
                raise DefinitiveRejection(f"Telegram explicitly rejected send (HTTP {exc.code})") from None
            raise AmbiguousDelivery("Telegram server response unknown") from None
        except Exception:
            raise AmbiguousDelivery("Telegram send response unavailable") from None
        if not isinstance(result, dict):
            raise AmbiguousDelivery("Telegram returned a malformed receipt")
        if result.get("ok") is False:
            raise DefinitiveRejection("Telegram explicitly rejected send")
        delivered = result.get("result") or {}
        if (result.get("ok") is not True or not isinstance(delivered, dict)
                or not valid_id(delivered.get("message_id"))
                or isinstance((delivered.get("chat") or {}).get("id"), bool)
                or (delivered.get("chat") or {}).get("id") != actual_chat):
            raise AmbiguousDelivery("Telegram receipt did not confirm exact message and destination")
        return delivered["message_id"]
    return route_key, username, send


def verify_route_command() -> None:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    expected = os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME", "").strip()
    if not token or not chat or not expected:
        raise RuntimeError("Configured optics Telegram route is incomplete")
    _, username, _send = verified_sender(token, chat, expected)
    print(f"telegram_route_valid=true bot=@{username} chat_identity_verified=true read_only=true")


def send_command() -> None:
    if os.getenv("GITHUB_EVENT_NAME") not in RUNTIME_EVENTS:
        raise RuntimeError("This event is validation-only; delivery refused")
    for stale in (CONFIRMED_PATH, DELIVERED_PENDING_PATH):
        stale.unlink(missing_ok=True)
    ledger = read_json(LEDGER_PATH, {"version": 1, "bundles": {}})
    text = ALERT_PATH.read_text(encoding="utf-8").strip() if ALERT_PATH.exists() else None
    if not text and not any(entry.get("state_persisted") is not True for entry in ledger.get("bundles", {}).values()):
        print("optics_delivery=no_pending_message")
        return
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    expected = os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME", "").strip()
    if not token or not chat or not expected:
        raise RuntimeError("Configured optics Telegram route is incomplete")
    source_sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", source_sha):
        raise RuntimeError("Unable to verify checked-out code revision")
    guard = read_json(GUARD_PATH)
    if (guard.get("status") != "verified" or guard.get("source_sha") != source_sha
            or guard.get("run_id") != os.getenv("GITHUB_RUN_ID")
            or guard.get("run_attempt") != os.getenv("GITHUB_RUN_ATTEMPT", "1")):
        raise RuntimeError("No verified persistence-history guard for this runtime; automatic send held")
    route_key, username, send = verified_sender(token, chat, expected)
    pending = read_json(PENDING_PATH) if text else None

    def checkpoint(summary: dict) -> None:
        atomic_json(LEDGER_PATH, ledger)
        atomic_json(PARTIAL_PATH, {**summary, "checked_at_kst": stamp(), "source_sha": source_sha})
    confirmed, pinned = deliver_bundle(text=text, pending_state=pending, ledger=ledger,
        route_key=route_key, bot_username=username, source_sha=source_sha, send=send, checkpoint=checkpoint,
        state_ancestor=read_json(STATE_PATH, {}))
    if confirmed:
        atomic_json(DELIVERED_PENDING_PATH, pinned)
        atomic_json(CONFIRMED_PATH, confirmed)
        print(f"telegram_delivery_confirmed=true bot=@{username} message_ids={confirmed['message_ids']}")


def persist_state() -> None:
    if os.getenv("GITHUB_EVENT_NAME") == "push":
        raise RuntimeError("Push validation cannot advance optics state")
    old = read_json(STATE_PATH, {})
    ledger = read_json(LEDGER_PATH, {"version": 1, "bundles": {}})
    if CONFIRMED_PATH.exists():
        receipt = read_json(CONFIRMED_PATH)
        pending = read_json(DELIVERED_PENDING_PATH)
        key = receipt.get("bundle_key")
        entry = ledger.get("bundles", {}).get(key)
        ids = receipt.get("message_ids", [])
        if (receipt.get("status") != "confirmed" or receipt.get("chat_identity_verified") is not True
                or not ids or not all(valid_id(value) for value in ids)
                or receipt.get("pending_state_sha256") != digest(pending)
                or not entry or entry.get("status") != "complete"
                or entry.get("route_key") != receipt.get("route_key")
                or ids != [entry.get("receipts", {}).get(str(i), {}).get("message_id") for i in range(len(entry.get("part_hashes", [])))]):
            raise RuntimeError("Confirmed receipt is not bound to its pending state; state unchanged")
        if receipt.get("state_already_persisted") is True:
            if entry.get("state_persisted") is not True:
                raise RuntimeError("Already-applied receipt has no persisted bundle; state unchanged")
            print("optics_state=already_applied_bundle_preserved")
            return
        ancestor = entry.get("state_ancestor")
        if (not isinstance(ancestor, dict) or entry.get("state_ancestor_sha256") != digest(ancestor)
                or receipt.get("state_ancestor_sha256") != digest(ancestor)
                or not isinstance(entry.get("pending_state"), dict)
                or digest(entry["pending_state"]) != digest(pending)):
            raise RuntimeError("Confirmed delivery lacks a verified original watch state; state unchanged, receipts preserved")
        updated = merge_watch_state(old, pending, ancestor)
        updated.update({"last_successful_delivery_kst": receipt["confirmed_at_kst"],
                        "telegram_message_ids": ids, "bot_username": receipt["bot_username"],
                        "telegram_chat_identity_verified": True})
        atomic_json(STATE_PATH, updated)
        entry["state_persisted"] = True  # Local snapshot; Git commits both files together.
        entry.pop("parts", None)
        entry.pop("pending_state", None)
        entry.pop("state_ancestor", None)
        atomic_json(LEDGER_PATH, ledger)
        print("optics_state=confirmed_bundle_applied")
    elif (not ALERT_PATH.exists() and not PARTIAL_PATH.exists()
          and not any(row.get("state_persisted") is not True for row in ledger.get("bundles", {}).values())
          and not any(row.get("status") == "unresolved" for row in ledger.get("recovery_holds", {}).values())
          and PENDING_PATH.exists()):
        atomic_json(STATE_PATH, merge_watch_state(old, read_json(PENDING_PATH)))
        print("optics_state=silent_baseline_applied")
    else:
        print("optics_state=unchanged_unconfirmed_delivery receipts_preserved=true")


def merge_commit(snapshot_dir: Path) -> None:
    for path, merger in ((STATE_PATH, merge_watch_state), (LEDGER_PATH, merge_ledgers)):
        snapshot = snapshot_dir / path.name
        if snapshot.exists():
            base, incoming = read_json(path, {}), read_json(snapshot)
            if path == STATE_PATH:
                merged = merge_watch_state(base, incoming, read_json(snapshot_dir / "base-state.json", {}))
            else:
                merged = merger(base, incoming)
            atomic_json(path, merged)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "verify-route", "guard", "send", "persist-state", "merge-commit"))
    parser.add_argument("--snapshot-dir", type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        preflight_command()
    elif args.command == "verify-route":
        verify_route_command()
    elif args.command == "guard":
        guard_command()
    elif args.command == "send":
        send_command()
    elif args.command == "persist-state":
        persist_state()
    elif args.snapshot_dir is not None:
        merge_commit(args.snapshot_dir)
    else:
        parser.error("merge-commit requires --snapshot-dir")


if __name__ == "__main__":
    main()

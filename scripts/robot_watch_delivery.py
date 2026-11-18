#!/usr/bin/env python3
"""Receipt-bound Telegram delivery and bounded recovery for this watcher.

All message blocks are validated before the first POST. Confirmed receipts
retire only their complete article keys. A POST without a trustworthy reply
remains ambiguous: recovery stops automatic sending rather than guessing.
This is not an exactly-once protocol; expired/missing artifacts and a lost
runner after a POST require explicit investigation.
"""
from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

EXPECTED_BOT = "khs8879008879000088790000_bot"
WORKFLOW = "robotis-physical-ai-telegram-watch.yml"
SEND_STEP = "Send Telegram only on meaningful change"
ALERT_PATH = Path("out/robotis_physical_ai_watch_telegram.txt")
PENDING_PATH = Path("out/robotis_physical_ai_watch_pending_state.json")
RECEIPTS_PATH = Path("out/robotis_physical_ai_watch_delivery_receipts.json")
ATTEMPTS_PATH = Path("out/robotis_physical_ai_watch_delivery_attempts.json")
STATE_PATH = Path("data/robotis_physical_ai_watch_state.json")
MAX_CHARS = 3500
MAX_ARCHIVE = 4 * 1024 * 1024
MAX_MEMBER = 2 * 1024 * 1024
MAX_API_BODY = 4 * 1024 * 1024
MAX_FAILED_SEND_RUNS = 20
MAX_RUNS_INSPECTED = 10000
# Conservative composition, not a single documented GitHub limit: reruns are
# allowed within 30 days of the initial run, a workflow can last 35 days
# including waiting/approvals, and one extra day covers the date boundary.
# https://docs.github.com/en/actions/how-tos/manage-workflow-runs
# https://docs.github.com/en/actions/reference/limits
RECOVERY_CREATION_LOOKBACK_DAYS = 66
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ARTICLE = re.compile(r"(?m)^<b>(\d+)\.\s")


class DeliveryError(RuntimeError):
    pass


class RecoveryBlocked(DeliveryError):
    pass


class APIError(DeliveryError):
    def __init__(self, status: int):
        super().__init__(f"GitHub API failed with HTTP {status}")
        self.status = status


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _timestamp(value) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise DeliveryError("Missing or invalid timestamp") from None
    if parsed.tzinfo is None:
        raise DeliveryError("Timestamp has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pending_digest(pending: dict) -> str:
    return _digest(json.dumps(pending, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _require_first_run_attempt() -> None:
    # A rerun keeps its run_id but becomes in_progress again, hiding its prior
    # attempt from the completed-run query. Never silently skip that evidence.
    if os.environ.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        raise RecoveryBlocked("Workflow rerun requires prior-attempt delivery review; automatic resend is blocked")


def route_fingerprint(chat: str, bot_username: str = EXPECTED_BOT) -> str:
    chat = str(chat).strip()
    if not (re.fullmatch(r"-?\d+", chat) or re.fullmatch(r"@[A-Za-z0-9_]+", chat)):
        raise DeliveryError("Telegram target is missing or unsupported (redacted)")
    return _digest("robot-route-v1|" + bot_username.casefold() + "|" + chat.casefold())


class _HTMLCheck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag not in {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote", "tg-spoiler", "span"}:
            raise DeliveryError("Unsupported HTML in Telegram article")
        if tag == "a":
            hrefs = [value for name, value in attrs if name == "href"]
            if len(hrefs) != 1 or not hrefs[0]:
                raise DeliveryError("Article has a malformed source link")
            self.links.append(html.unescape(hrefs[0]))
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise DeliveryError("Article HTML tags cross a block boundary")

    def handle_startendtag(self, tag, attrs):
        raise DeliveryError("Self-closing Telegram HTML is unsupported")


def _html_links(text: str) -> list[str]:
    parser = _HTMLCheck()
    parser.feed(text)
    parser.close()
    if parser.stack:
        raise DeliveryError("Telegram article has an unclosed HTML tag")
    return parser.links


def build_chunks(text: str, pending: dict) -> list[dict]:
    """Validate the whole final HTML and return complete article chunks."""
    text = str(text).strip()
    selected = pending.get("last_selected") or []
    events = pending.get("last_selected_events") or []
    if not isinstance(selected, list) or not isinstance(events, list):
        raise DeliveryError("Pending event mapping must be a list")
    if not text:
        if selected or events:
            raise DeliveryError("Empty alert still contains selected event keys")
        return []
    if not selected or len(selected) != len(set(selected)):
        raise DeliveryError("Pending keys are missing or duplicated")
    if any(not isinstance(key, str) or not _HEX.fullmatch(key) for key in selected):
        raise DeliveryError("Pending event key is invalid")
    by_link = {}
    mapped_keys = []
    for event in events:
        if not isinstance(event, dict):
            raise DeliveryError("Invalid pending event mapping")
        key, link = event.get("key"), event.get("link")
        if not isinstance(link, str) or urllib.parse.urlparse(link).scheme not in {"https", "http"}:
            raise DeliveryError("Pending event source URL is invalid")
        if link in by_link:
            raise DeliveryError("Two pending events share one source URL")
        by_link[link] = key
        mapped_keys.append(key)
    if len(mapped_keys) != len(selected) or set(mapped_keys) != set(selected):
        raise DeliveryError("Selected keys and source URL mapping disagree")
    matches = list(_ARTICLE.finditer(text))
    if len(matches) != len(selected) or [int(m.group(1)) for m in matches] != list(range(1, len(matches) + 1)):
        raise DeliveryError("Final article blocks are missing, duplicated or misnumbered")
    header = text[:matches[0].start()].strip()
    if _html_links(header):
        raise DeliveryError("Unmapped source URL in report header")
    blocks = []
    all_keys = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        block = text[match.start():end].strip()
        links = _html_links(block)
        mapped = [by_link[link] for link in links if link in by_link]
        if len(mapped) != 1:
            raise DeliveryError("Article must contain exactly one mapped source URL")
        # Other evidence URLs may occur, but no second selected event may be
        # hidden inside an article. Repeated source links are also rejected.
        key = mapped[0]
        all_keys.append(key)
        if len(block) > MAX_CHARS:
            raise DeliveryError("A complete article exceeds the 3500-character limit")
        blocks.append((block, key))
    if len(set(all_keys)) != len(all_keys) or set(all_keys) != set(selected):
        raise DeliveryError("Final article keys do not exactly cover pending selection")
    chunks, current, current_keys = [], header, []
    for block, key in blocks:
        combined = (current + "\n\n" + block).strip() if current else block
        if len(combined) > MAX_CHARS:
            if not current_keys:
                raise DeliveryError("Report header and first article exceed the chunk limit")
            chunks.append({"text": current, "event_keys": current_keys})
            current, current_keys = block, [key]
        else:
            current, current_keys = combined, current_keys + [key]
    if current_keys:
        chunks.append({"text": current, "event_keys": current_keys})
    for index, chunk in enumerate(chunks):
        if len(chunk["text"]) > MAX_CHARS:
            raise DeliveryError("Telegram chunk exceeds its limit")
        _html_links(chunk["text"])
        chunk.update(chunk_index=index, sha256=_digest(chunk["text"]))
    return chunks


def check_receipts(text: str, pending: dict, receipts: list, expected_route_fingerprint: str) -> set[str]:
    """Validate a confirmed prefix, returning only completely delivered keys."""
    chunks = build_chunks(text, pending)
    if not isinstance(receipts, list) or not _HEX.fullmatch(expected_route_fingerprint):
        raise DeliveryError("Invalid delivery receipts or route fingerprint")
    confirmed, message_ids, attempt_ids = set(), set(), set()
    for expected_index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
            raise DeliveryError("Unsupported or malformed receipt schema")
        index = receipt.get("chunk_index")
        if type(index) is not int or index != expected_index or index >= len(chunks):
            raise DeliveryError("Receipts are not a unique confirmed chunk prefix")
        chunk = chunks[index]
        if receipt.get("sha256") != chunk["sha256"] or receipt.get("event_keys") != chunk["event_keys"]:
            raise DeliveryError("Receipt content hash or event keys disagree with final article")
        if receipt.get("route_fingerprint") != expected_route_fingerprint:
            raise DeliveryError("Receipt route mismatch (identifiers redacted)")
        message_id, attempt_id = receipt.get("message_id"), receipt.get("attempt_id")
        if type(message_id) is not int or message_id <= 0 or message_id in message_ids:
            raise DeliveryError("Invalid or repeated Telegram message ID")
        if not isinstance(attempt_id, str) or not attempt_id or attempt_id in attempt_ids:
            raise DeliveryError("Invalid or repeated delivery attempt ID")
        if receipt.get("chat_verification") not in {"numeric_id_equal", "username_equal"}:
            raise DeliveryError("Receipt has no verified recipient match")
        if type(receipt.get("run_id")) is not int or receipt["run_id"] <= 0:
            raise DeliveryError("Receipt has no workflow run identity")
        _timestamp(receipt.get("delivered_at_utc"))
        message_ids.add(message_id)
        attempt_ids.add(attempt_id)
        confirmed.update(chunk["event_keys"])
    return confirmed


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_bounded(response, limit: int) -> bytes:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise DeliveryError("Remote response exceeds the size limit")
    return raw


def _telegram(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    request = urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode() if payload else None)
    # A Telegram redirect must never forward the credential-bearing URL.
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=30) as response:
        return json.loads(_read_bounded(response, MAX_API_BODY))


def _recipient(reply: dict, chat: str) -> str:
    destination = reply.get("chat") or {}
    if re.fullmatch(r"-?\d+", chat):
        if str(destination.get("id")) != chat:
            raise DeliveryError("Telegram recipient mismatch (identifiers redacted)")
        return "numeric_id_equal"
    if chat.startswith("@") and str(destination.get("username") or "").casefold() == chat[1:].casefold():
        return "username_equal"
    raise DeliveryError("Telegram alias could not be verified (identifiers redacted)")


def send_alert(text: str, pending: dict, token: str, chat: str, *,
               receipt_path: Path = RECEIPTS_PATH, attempt_path: Path = ATTEMPTS_PATH,
               run_id: int, transport=None) -> set[str]:
    _require_first_run_attempt()
    if not str(text).strip():
        build_chunks(text, pending)
        return set()
    if type(run_id) is not int or run_id <= 0:
        raise DeliveryError("Missing workflow run identity")
    for path in (receipt_path, attempt_path):
        if path.exists() and json.loads(path.read_text(encoding="utf-8")):
            raise DeliveryError("Existing delivery evidence must not be overwritten")
    preflight = {
        "schema_version": 1, "kind": "preflight", "run_id": run_id,
        "status": "checking", "started_at_utc": _now(),
        "alert_sha256": _digest(str(text).strip()), "pending_sha256": _pending_digest(pending),
        "route_fingerprint": None,
    }
    receipts, attempts = [], [preflight]
    _atomic_json(receipt_path, receipts)
    _atomic_json(attempt_path, attempts)
    transport = transport or (lambda method, payload=None: _telegram(token, method, payload))
    try:
        # A failed preflight is durably distinguishable from an uncertain POST.
        # The whole report is checked before getMe or any sendMessage call.
        chunks = build_chunks(text, pending)
        fingerprint = route_fingerprint(chat)
        preflight["route_fingerprint"] = fingerprint
        if not token:
            raise DeliveryError("Missing Telegram credential")
        account = transport("getMe")
        username = (account.get("result") or {}).get("username", "")
        if not account.get("ok") or username.casefold() != EXPECTED_BOT.casefold():
            raise DeliveryError("Telegram bot identity mismatch")
    except Exception as exc:
        preflight.update(status="failed", finished_at_utc=_now(), error_type=type(exc).__name__)
        _atomic_json(attempt_path, attempts)
        message = str(exc) if isinstance(exc, DeliveryError) else "Telegram bot preflight failed (details redacted)"
        raise DeliveryError(message) from None
    preflight.update(status="passed", finished_at_utc=_now())
    _atomic_json(attempt_path, attempts)
    for chunk in chunks:
        attempt = {
            "schema_version": 1, "kind": "send", "run_id": run_id, "attempt_id": uuid.uuid4().hex,
            "chunk_index": chunk["chunk_index"], "sha256": chunk["sha256"],
            "event_keys": chunk["event_keys"], "route_fingerprint": fingerprint,
            "started_at_utc": _now(), "status": "in_flight",
        }
        attempts.append(attempt)
        _atomic_json(attempt_path, attempts)  # Before POST; uncertainty survives a lost reply.
        try:
            result = transport("sendMessage", {
                "chat_id": chat, "text": chunk["text"], "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            })
            if not result.get("ok"):
                attempt.update(status="rejected", finished_at_utc=_now())
                _atomic_json(attempt_path, attempts)
                raise DeliveryError("Telegram explicitly rejected a message")
            reply = result.get("result") or {}
            verification = _recipient(reply, chat)
            message_id = reply.get("message_id")
            if type(message_id) is not int or message_id <= 0:
                raise DeliveryError("Telegram reply has no valid message ID")
            receipt = {
                **{name: attempt[name] for name in ("schema_version", "run_id", "attempt_id", "chunk_index", "sha256", "event_keys", "route_fingerprint")},
                "delivered_at_utc": _now(), "chat_verification": verification,
                "message_id": message_id, "message_thread_id": reply.get("message_thread_id"),
            }
            receipts.append(receipt)
            _atomic_json(receipt_path, receipts)
            attempt.update(status="confirmed", finished_at_utc=_now(), message_id=message_id)
            _atomic_json(attempt_path, attempts)
            print(f"Telegram confirmed chunk {chunk['chunk_index'] + 1}; events={len(chunk['event_keys'])}", flush=True)
        except Exception as exc:
            if attempt["status"] != "rejected":
                # Even HTTP errors can arrive after a server-side action. A
                # parse/recipient error likewise cannot prove non-delivery.
                attempt.update(status="ambiguous", finished_at_utc=_now(), error_type=type(exc).__name__)
                _atomic_json(attempt_path, attempts)
            raise DeliveryError("Telegram send stopped; confirmed receipts retained; unresolved attempts require review") from None
    return check_receipts(text, pending, receipts, fingerprint)


class GitHubAPI:
    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
            raise DeliveryError("GitHub repository or recovery credential is missing")
        self.repository, self.token = repository, token
        self.opener = urllib.request.build_opener(_NoRedirect())

    def _request(self, path, method="GET", data=None):
        if not path.startswith(f"/repos/{self.repository}/"):
            raise DeliveryError("Recovery API path is outside this repository")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        raw = json.dumps(data).encode() if data is not None else None
        if raw is not None:
            headers["Content-Type"] = "application/json"
        return urllib.request.Request("https://api.github.com" + path, data=raw, headers=headers, method=method)

    def json(self, path, method="GET", data=None):
        try:
            with self.opener.open(self._request(path, method, data), timeout=30) as response:
                return json.loads(_read_bounded(response, MAX_API_BODY))
        except urllib.error.HTTPError as exc:
            raise APIError(exc.code) from None
        except (urllib.error.URLError, TimeoutError):
            raise DeliveryError("GitHub API connection failed (details redacted)") from None

    def download(self, artifact_id: int) -> bytes:
        path = f"/repos/{self.repository}/actions/artifacts/{artifact_id}/zip"
        try:
            with self.opener.open(self._request(path), timeout=30) as response:
                return _read_bounded(response, MAX_ARCHIVE)
        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise APIError(exc.code) from None
            location = exc.headers.get("Location", "")
        parts = urllib.parse.urlparse(location)
        host = (parts.hostname or "").casefold()
        allowed = (host.endswith(".blob.core.windows.net") or host.endswith(".githubusercontent.com")
                   or host.endswith(".s3.amazonaws.com") or bool(re.fullmatch(r".+\.s3[.-][a-z0-9-]+\.amazonaws\.com", host)))
        if parts.scheme != "https" or parts.username or parts.password or parts.port not in {None, 443} or not allowed:
            raise DeliveryError("Artifact redirect destination is not an approved storage host")
        # Deliberately create a new request: never copy Authorization to the
        # signed storage URL, and do not follow any additional redirects.
        try:
            with self.opener.open(urllib.request.Request(location), timeout=30) as response:
                return _read_bounded(response, MAX_ARCHIVE)
        except (urllib.error.URLError, TimeoutError):
            raise DeliveryError("Artifact storage download failed (details redacted)") from None


def _json_member(files: dict, name: str, default=None):
    if name not in files:
        if default is not None:
            return default
        raise RecoveryBlocked("Artifact is missing required delivery evidence")
    try:
        return json.loads(files[name])
    except (ValueError, UnicodeError):
        raise RecoveryBlocked("Artifact delivery JSON is malformed") from None


def read_artifact(raw: bytes, metadata: dict, run_id: int) -> dict[str, str]:
    if metadata.get("name") != f"robotis-physical-ai-{run_id}" or metadata.get("expired"):
        raise RecoveryBlocked("Artifact name or retention is invalid")
    if len(raw) > MAX_ARCHIVE or metadata.get("size_in_bytes", 0) > MAX_ARCHIVE:
        raise RecoveryBlocked("Artifact archive exceeds the size limit")
    digest = metadata.get("digest")
    if digest != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise RecoveryBlocked("Artifact archive digest is missing or mismatched")
    allowed = {ALERT_PATH.name, PENDING_PATH.name, RECEIPTS_PATH.name, ATTEMPTS_PATH.name,
               "robotis_physical_ai_watch_status.md", "robotis_physical_ai_watch_candidates.json"}
    files, total = {}, 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > len(allowed):
                raise RecoveryBlocked("Artifact contains unexpected members")
            for member in archive.infolist():
                name = PurePosixPath(member.filename)
                if member.filename != name.name or name.name not in allowed or name.name in files:
                    raise RecoveryBlocked("Artifact member path or name is not allowed")
                if member.flag_bits & 1 or stat.S_ISLNK(member.external_attr >> 16):
                    raise RecoveryBlocked("Encrypted or linked artifact members are not allowed")
                total += member.file_size
                if member.file_size > MAX_MEMBER or total > MAX_ARCHIVE:
                    raise RecoveryBlocked("Uncompressed artifact exceeds the size limit")
                files[name.name] = archive.read(member).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeError, RuntimeError) as exc:
        if isinstance(exc, RecoveryBlocked):
            raise
        raise RecoveryBlocked("Artifact ZIP could not be validated") from None
    return files


def artifact_delivery(files: dict, run_id: int, fingerprint: str) -> tuple[set[str], bool]:
    text = files.get(ALERT_PATH.name, "")
    pending = _json_member(files, PENDING_PATH.name)
    receipts = _json_member(files, RECEIPTS_PATH.name, [])
    attempts = _json_member(files, ATTEMPTS_PATH.name, [])
    if not isinstance(attempts, list):
        raise RecoveryBlocked("Artifact attempt log is not a list")
    if attempts and isinstance(attempts[0], dict) and attempts[0].get("kind") == "preflight":
        preflight, attempts = attempts[0], attempts[1:]
        if (preflight.get("schema_version") != 1 or preflight.get("run_id") != run_id
                or preflight.get("status") not in {"checking", "failed", "passed"}
                or preflight.get("alert_sha256") != _digest(text.strip())
                or preflight.get("pending_sha256") != _pending_digest(pending)):
            raise RecoveryBlocked("Artifact preflight identity or content hash disagrees")
        _timestamp(preflight.get("started_at_utc"))
        if not attempts and not receipts:
            return set(), False  # Protocol records each attempt before POST.
        if preflight.get("status") != "passed" or preflight.get("route_fingerprint") != fingerprint:
            raise RecoveryBlocked("Artifact send lacks a matching successful preflight")
    elif text.strip():
        raise RecoveryBlocked("Send was attempted without a complete preflight journal")
    keys = check_receipts(text, pending, receipts, fingerprint)
    chunks = build_chunks(text, pending)
    receipt_by_attempt = {r["attempt_id"]: r for r in receipts}
    if any(r["run_id"] != run_id for r in receipts):
        raise RecoveryBlocked("Artifact receipt belongs to another run")
    seen_attempts, ambiguous = set(), False
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict) or attempt.get("schema_version") != 1 or attempt.get("kind") != "send" or attempt.get("run_id") != run_id:
            raise RecoveryBlocked("Artifact attempt identity is invalid")
        attempt_id = attempt.get("attempt_id")
        chunk_index = attempt.get("chunk_index")
        if not isinstance(attempt_id, str) or not attempt_id or attempt_id in seen_attempts:
            raise RecoveryBlocked("Artifact attempt ID is missing or duplicated")
        if type(chunk_index) is not int or chunk_index != index or chunk_index >= len(chunks):
            raise RecoveryBlocked("Artifact attempts are not a valid chunk prefix")
        chunk = chunks[chunk_index]
        if attempt.get("sha256") != chunk["sha256"] or attempt.get("event_keys") != chunk["event_keys"] or attempt.get("route_fingerprint") != fingerprint:
            raise RecoveryBlocked("Artifact attempt content or route disagrees")
        _timestamp(attempt.get("started_at_utc"))
        receipt = receipt_by_attempt.get(attempt_id)
        if receipt:
            if receipt["chunk_index"] != chunk_index:
                raise RecoveryBlocked("Artifact receipt and attempt disagree")
        elif attempt.get("status") == "confirmed":
            raise RecoveryBlocked("Confirmed attempt has no matching receipt")
        elif attempt.get("status") in {"in_flight", "ambiguous"}:
            ambiguous = True
        elif attempt.get("status") != "rejected":
            raise RecoveryBlocked("Artifact attempt status is unknown")
        seen_attempts.add(attempt_id)
    if set(receipt_by_attempt) - seen_attempts:
        raise RecoveryBlocked("Artifact receipt has no preceding attempt record")
    if text.strip() and not attempts:
        # A send step ran, but there is no durable proof that it stopped before
        # POST. Old-format artifacts need manual examination, never replay.
        raise RecoveryBlocked("Send was attempted without a complete attempt journal")
    return keys, ambiguous


def _load_remote_state(api) -> tuple[dict, str]:
    value = api.json(f"/repos/{api.repository}/contents/{STATE_PATH.as_posix()}?ref=main")
    try:
        if value.get("encoding") != "base64" or not isinstance(value.get("sha"), str):
            raise ValueError
        raw = base64.b64decode(value["content"], validate=False)
        if len(raw) > MAX_MEMBER:
            raise ValueError
        state = json.loads(raw)
        if not isinstance(state, dict) or not isinstance(state.get("seen"), list) or not all(isinstance(k, str) for k in state["seen"]):
            raise ValueError
        _timestamp(state.get("updated_at"))
    except (KeyError, TypeError, ValueError):
        raise RecoveryBlocked("Remote dedup state is malformed") from None
    return state, value["sha"]


def _send_was_attempted(api, run_id: int) -> bool:
    response = api.json(f"/repos/{api.repository}/actions/runs/{run_id}/jobs?filter=all&per_page=100")
    jobs = response.get("jobs")
    if not isinstance(jobs, list) or not jobs or response.get("total_count", len(jobs)) > len(jobs):
        raise RecoveryBlocked(f"Run {run_id}: complete job evidence unavailable")
    found, attempted = False, False
    for job in jobs:
        if job.get("status") != "completed":
            raise RecoveryBlocked(f"Run {run_id}: job is not complete")
        steps = job.get("steps") or []
        sends = [step for step in steps if step.get("name") == SEND_STEP]
        if not sends:
            raise RecoveryBlocked(f"Run {run_id}: send-step history is absent")
        for step in sends:
            found = True
            if step.get("conclusion") != "skipped":
                attempted = True
    if not found:
        raise RecoveryBlocked(f"Run {run_id}: send step cannot be classified")
    return attempted


def _failed_runs(api, since: dt.datetime) -> list[dict]:
    failed, scanned, inspected = [], 0, set()
    first_day = (since - dt.timedelta(days=RECOVERY_CREATION_LOOKBACK_DAYS)).date()
    today = dt.datetime.now(dt.timezone.utc).date()
    if since > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise RecoveryBlocked("Dedup checkpoint is unexpectedly in the future")
    # A run created before the checkpoint may wait before sending afterward.
    # Include old-created runs whose later rerun completed after checkpoint.
    # Weekly windows avoid GitHub's 1000-results-per-filtered-search limit.
    while first_day <= today:
        final_day = min(first_day + dt.timedelta(days=6), today)
        window_seen = 0
        complete = False
        for page in range(1, 11):
            query = urllib.parse.urlencode({
                "status": "completed", "branch": "main",
                "created": f"{first_day.isoformat()}..{final_day.isoformat()}",
                "per_page": 100, "page": page,
            })
            result = api.json(f"/repos/{api.repository}/actions/workflows/{WORKFLOW}/runs?{query}")
            runs = result.get("workflow_runs")
            total = result.get("total_count")
            if not isinstance(runs, list) or type(total) is not int or total > 1000:
                raise RecoveryBlocked("Recovery search window exceeds complete API coverage")
            scanned += len(runs)
            window_seen += len(runs)
            if scanned > MAX_RUNS_INSPECTED:
                raise RecoveryBlocked("Recovery history exceeds its complete inspection limit")
            for run in runs:
                if run.get("status") != "completed" or _timestamp(run.get("updated_at")) <= since:
                    continue
                if run.get("conclusion") in {"success", "skipped", "neutral"}:
                    continue
                if run.get("head_branch") != "main" or run.get("path", "").split("@")[0] != ".github/workflows/" + WORKFLOW:
                    raise RecoveryBlocked("Recovery run workflow or branch does not match")
                run_id = run.get("id")
                if type(run_id) is not int or run_id <= 0:
                    raise RecoveryBlocked("Recovery run has invalid identity")
                if run_id in inspected:
                    continue
                inspected.add(run_id)
                if _send_was_attempted(api, run_id):
                    failed.append(run)
                    if len(failed) > MAX_FAILED_SEND_RUNS:
                        raise RecoveryBlocked("More than 20 failed send runs require review; recovery is not truncated")
            if window_seen >= total:
                complete = True
                break
            if len(runs) < 100:
                raise RecoveryBlocked("Recovery API returned an incomplete history page")
        if not complete:
            raise RecoveryBlocked("Recovery pagination did not reach the end of a search window")
        first_day = final_day + dt.timedelta(days=1)
    return sorted(failed, key=lambda r: _timestamp(r["updated_at"]))


def merge_recovered(api, records: list[dict]) -> dict:
    """CAS-retry a union, always re-reading the newest complete state."""
    keys = {key for record in records for key in record["event_keys"]}
    for _ in range(5):
        latest, sha = _load_remote_state(api)
        if keys <= set(latest["seen"]):
            return latest
        merged = copy.deepcopy(latest)
        merged["seen"] = list(dict.fromkeys(latest["seen"] + sorted(keys)))
        history = merged.get("delivery_recovery_history") or []
        if not isinstance(history, list):
            raise RecoveryBlocked("Existing recovery metadata has an invalid format")
        for record in records:
            if not any(isinstance(item, dict) and item.get("run_id") == record["run_id"] for item in history):
                history.append(copy.deepcopy(record))
        merged["delivery_recovery_history"] = history
        content = base64.b64encode((json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode()).decode()
        try:
            api.json(f"/repos/{api.repository}/contents/{STATE_PATH.as_posix()}", "PUT", {
                "message": "Recover verified ROBOTIS delivery keys [skip ci]", "content": content,
                "sha": sha, "branch": "main",
            })
            return merged
        except APIError as exc:
            if exc.status not in {409, 422}:
                raise
    raise RecoveryBlocked("Recovered delivery state could not be persisted after 5 CAS attempts")


def recover(api, chat: str, *, state_path: Path = STATE_PATH) -> dict:
    _require_first_run_attempt()
    initial, _ = _load_remote_state(api)
    runs = _failed_runs(api, _timestamp(initial["updated_at"]))
    fingerprint = route_fingerprint(chat)
    records, unresolved = [], []
    for run in runs:
        run_id = run["id"]
        result = api.json(f"/repos/{api.repository}/actions/runs/{run_id}/artifacts?per_page=100")
        artifacts = result.get("artifacts") or []
        if result.get("total_count", len(artifacts)) > len(artifacts):
            raise RecoveryBlocked(f"Run {run_id}: artifact listing is incomplete")
        matching = [a for a in artifacts if a.get("name") == f"robotis-physical-ai-{run_id}"]
        if len(matching) != 1 or matching[0].get("expired"):
            raise RecoveryBlocked(f"Run {run_id}: attempted send has missing, duplicated or expired evidence")
        artifact = matching[0]
        if type(artifact.get("id")) is not int or artifact["id"] <= 0:
            raise RecoveryBlocked("Artifact has invalid identity")
        files = read_artifact(api.download(artifact["id"]), artifact, run_id)
        keys, ambiguous = artifact_delivery(files, run_id, fingerprint)
        if keys:
            records.append({"run_id": run_id, "event_keys": sorted(keys), "recovered_at_utc": _now()})
        if ambiguous:
            unresolved.append(run_id)
    state = merge_recovered(api, records) if records else _load_remote_state(api)[0]
    _atomic_json(state_path, state)
    if unresolved:
        raise RecoveryBlocked("Ambiguous Telegram attempts block automatic resend; review runs " + ", ".join(map(str, unresolved)))
    return {"failed_send_runs_checked": len(runs), "confirmed_event_keys_recovered": len({k for r in records for k in r["event_keys"]})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("send", "recover"))
    args = parser.parse_args()
    try:
        chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if args.command == "recover":
            api = GitHubAPI(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", ""))
            print(json.dumps(recover(api, chat), ensure_ascii=False))
        else:
            text = ALERT_PATH.read_text(encoding="utf-8") if ALERT_PATH.exists() else ""
            if not text.strip():
                print("No meaningful change; Telegram silent.")
                return 0
            pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
            keys = send_alert(text, pending, os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), chat,
                              run_id=int(os.environ.get("GITHUB_RUN_ID", "0")))
            print(f"Telegram confirmed complete events: {len(keys)}")
        return 0
    except (DeliveryError, OSError, ValueError, KeyError, TypeError) as exc:
        # No urllib exception, token, chat ID or signed artifact URL is logged.
        message = str(exc) if isinstance(exc, DeliveryError) else type(exc).__name__
        print("ROBOTIS delivery stopped: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

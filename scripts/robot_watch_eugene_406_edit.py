#!/usr/bin/env python3
"""Scoped, verified one-message expansion of the ROBOTIS Eugene 2026-11-23 alert.

Only edits the already delivered Telegram message 406. Never sends/deletes a
message, changes a recipient, resets the dedup state, or touches another watch.
The original sent artifact and recipient receipt are verified before the first
remote state mutation. An uncertain edit is preserved as ambiguous and is NOT
automatically replayed. A confirmed reply is CAS-persisted before success.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile
from pathlib import PurePosixPath

import robot_watch_delivery as d
import robot_watch_message_corrections as c
from robot_watch_eugene_lifecycle_20261123 import EUGENE_ALERT_DETAILS, REPORT_KEY

SOURCE_RUN_ID = 45170833591
SOURCE_ARTIFACT_ID = 14817380683
SOURCE_ARTIFACT_DIGEST = "sha256:13288b0ecc0c52d8b30456d4c69cf8898fb0175d74b030884fc1a941b8fee739"
ORIGINAL_TEXT_SHA = "68edfab4fd82c3869f0a88af8b3679d49254fb655cfa739e52698fce93f9567f"
MESSAGE_ID = 406
CHECKPOINT = "eugene_report_20261123_406_detail_v1"
REPORT = Path("out/robot_watch_eugene_406_edit_receipt.json")
MAX_TEXT = d.MAX_CHARS
HEADER = "💡 <b>핵심</b>"
CHECK = "⚠️ <b>체크</b>"
TAIL = "\n\n──────────────────\n<b>판정 기준</b>"


def replacement(original: str, pending: dict) -> str:
    if d._digest(original.strip()) != ORIGINAL_TEXT_SHA:
        raise d.DeliveryError("Original Eugene 406 content SHA mismatch")
    if original.count(HEADER) != 1 or original.count(CHECK) != 1 or original.count(TAIL) != 1:
        raise d.DeliveryError("Original Eugene 406 template differs; correction blocked")
    start = original.index(HEADER)
    tail = original.index(TAIL, start)
    if not start < original.index(CHECK, start) < tail:
        raise d.DeliveryError("Original Eugene 406 article format differs")
    revised = (
        original[:start] +
        "✏️ <b>원문 대조 보강 · 핵심 수치·도표 6개 선·기업별 판단</b>\n" +
        EUGENE_ALERT_DETAILS + original[tail:]
    )
    if len(revised) > MAX_TEXT:
        raise d.DeliveryError("Eugene 406 full message exceeds 3500-character cap")
    chunks = d.build_chunks(revised, pending)
    if len(chunks) != 1 or chunks[0]["event_keys"] != [REPORT_KEY]:
        raise d.DeliveryError("Eugene correction changes the original event or chunk count")
    if len(c.plain_text(revised)) > 4096:
        raise d.DeliveryError("Telegram plain text exceeds message limit")
    return revised



# The archived Nov-23 source additionally contains a dedicated robot-message
# correction receipt. Its exact seven-member archive hash is pinned above;
# the shared legacy recovery reader only permits six names. Do not loosen it
# for any other alert or change the shared recovery implementation.
SOURCE_MEMBERS = {
    d.ALERT_PATH.name, d.PENDING_PATH.name,
    d.RECEIPTS_PATH.name, d.ATTEMPTS_PATH.name,
    "robotis_physical_ai_watch_status.md",
    "robotis_physical_ai_watch_candidates.json",
    "robot_watch_message_correction_receipts.json",
}


def _read_source_members(raw: bytes, metadata: dict) -> dict[str, str]:
    if (metadata.get("name") != f"robotis-physical-ai-{SOURCE_RUN_ID}"
            or metadata.get("digest") != SOURCE_ARTIFACT_DIGEST
            or metadata.get("expired") is True
            or len(raw) > d.MAX_ARCHIVE
            or metadata.get("size_in_bytes", 0) > d.MAX_ARCHIVE
            or "sha256:" + hashlib.sha256(raw).hexdigest() != SOURCE_ARTIFACT_DIGEST):
        raise d.DeliveryError("Pinned Eugene source artifact integrity check failed")
    result = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) != len(SOURCE_MEMBERS):
                raise d.DeliveryError("Pinned Eugene source artifact has unexpected member count")
            for item in members:
                name = PurePosixPath(item.filename)
                if (item.filename != name.name or name.name not in SOURCE_MEMBERS
                        or name.name in result or (item.flag_bits & 1)
                        or stat.S_ISLNK(item.external_attr >> 16)):
                    raise d.DeliveryError("Pinned Eugene archive contains unknown, unsafe, or duplicated entries")
                total += item.file_size
                if item.file_size > d.MAX_MEMBER or total > d.MAX_ARCHIVE:
                    raise d.DeliveryError("Pinned Eugene archive members exceed expected limits")
                result[name.name] = archive.read(item).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeError, OSError, RuntimeError):
        raise d.DeliveryError("Pinned Eugene source archive could not be safely inspected") from None
    if set(result) != SOURCE_MEMBERS:
        raise d.DeliveryError("Pinned Eugene source archive member names do not match")
    return result


def _check_original(api, state: dict, chat: str) -> tuple[str, dict, dict]:
    if REPORT_KEY not in set(state.get("seen") or []):
        raise d.DeliveryError("The Eugene report was not delivered in current dedup state")
    history = [row for row in state.get("delivery_history") or []
               if isinstance(row, dict) and row.get("run_id") == SOURCE_RUN_ID]
    if (len(history) != 1 or history[0].get("outcome") != "sent"
            or history[0].get("message_ids") != [MESSAGE_ID]
            or history[0].get("recipient_verified") is not True
            or history[0].get("confirmed_event_keys") != [REPORT_KEY]):
        raise d.DeliveryError("Eugene original delivery state does not match")
    run = api.json(f"/repos/{api.repository}/actions/runs/{SOURCE_RUN_ID}")
    if (run.get("id") != SOURCE_RUN_ID or run.get("conclusion") != "success"
            or run.get("status") != "completed" or run.get("head_branch") != "main"
            or str(run.get("path") or "").split("@")[0] !=
               ".github/workflows/" + d.WORKFLOW):
        raise d.DeliveryError("Eugene original GitHub run is not verified")
    metadata = api.json(f"/repos/{api.repository}/actions/artifacts/{SOURCE_ARTIFACT_ID}")
    if (metadata.get("digest") != SOURCE_ARTIFACT_DIGEST
            or metadata.get("id") != SOURCE_ARTIFACT_ID
            or (metadata.get("workflow_run") or {}).get("id") != SOURCE_RUN_ID
            or metadata.get("expired") is True):
        raise d.DeliveryError("Eugene original artifact digest or run is invalid")
    files = _read_source_members(api.download(SOURCE_ARTIFACT_ID), metadata)
    try:
        original = files[d.ALERT_PATH.name]
        pending = json.loads(files[d.PENDING_PATH.name])
        receipts = json.loads(files[d.RECEIPTS_PATH.name])
    except (KeyError, TypeError, ValueError):
        raise d.DeliveryError("Eugene original artifact lacks sent message proof") from None
    expected_route = d.route_fingerprint(chat)
    verified = d.check_receipts(original, pending, receipts, expected_route)
    if (verified != {REPORT_KEY} or pending.get("last_selected") != [REPORT_KEY]
            or len(receipts) != 1
            or receipts[0].get("message_id") != MESSAGE_ID
            or receipts[0].get("sha256") != ORIGINAL_TEXT_SHA
            or receipts[0].get("chat_verification") not in {"numeric_id_equal", "username_equal"}
            or receipts[0].get("message_thread_id") is not None):
        raise d.DeliveryError("Eugene original receipt, message or destination mismatch")
    return original, pending, receipts[0]


def _checkpoint(state: dict, replacement_sha: str, route: str) -> dict | None:
    all_records = state.get("eugene_message_edits") or {}
    if not isinstance(all_records, dict):
        raise d.DeliveryError("Existing Eugene message edit state is invalid")
    row = all_records.get(CHECKPOINT)
    if row is not None:
        if (not isinstance(row, dict)
                or row.get("source_run_id") != SOURCE_RUN_ID
                or row.get("source_artifact_id") != SOURCE_ARTIFACT_ID
                or row.get("message_id") != MESSAGE_ID
                or row.get("route_fingerprint") != route
                or row.get("source_sha256") != ORIGINAL_TEXT_SHA
                or row.get("replacement_sha256") != replacement_sha):
            raise d.DeliveryError("Prior Eugene edit checkpoint differs")
    return row


def _cas(api, proposed_sha: str, route: str, transform):
    for _ in range(5):
        state, state_sha = d._load_remote_state(api)
        previous = _checkpoint(state, proposed_sha, route)
        record = copy.deepcopy(previous) if previous else {
            "schema_version": 1, "source_run_id": SOURCE_RUN_ID,
            "source_artifact_id": SOURCE_ARTIFACT_ID, "message_id": MESSAGE_ID,
            "route_fingerprint": route,
            "source_sha256": ORIGINAL_TEXT_SHA, "replacement_sha256": proposed_sha,
            "status": "prepared", "attempts": 0
        }
        transform(record)
        if previous == record:
            return state
        merged = copy.deepcopy(state)
        merged.setdefault("eugene_message_edits", {})[CHECKPOINT] = record
        payload = base64.b64encode(
            (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode()
        ).decode()
        try:
            api.json(f"/repos/{api.repository}/contents/{d.STATE_PATH.as_posix()}",
                     "PUT", {"message": "Record scoped ROBOTIS Eugene 406 edit receipt [skip ci]",
                             "content": payload, "sha": state_sha, "branch": "main"})
            return merged
        except d.APIError as exc:
            if exc.status not in {409, 422}:
                raise
    raise d.DeliveryError("Eugene correction checkpoint CAS could not be persisted")


def edit_once(api, token: str, chat: str, *, transport=None, receipt_path=REPORT):
    route = d.route_fingerprint(chat)
    state, _ = d._load_remote_state(api)
    if not token:
        raise d.DeliveryError("Eugene edit has no bot credential")
    original, pending, source_receipt = _check_original(api, state, chat)
    text = replacement(original, pending)
    text_sha = d._digest(text)
    existing = _checkpoint(state, text_sha, route)
    if existing:
        if existing.get("status") == "confirmed":
            if (existing.get("verified_response_text_sha256") != d._digest(c.plain_text(text))
                    or existing.get("verified_method") != "reply_message_id_recipient_text_equal"):
                raise d.DeliveryError("Completed Eugene edit has no matching Telegram text proof")
            result = {"already_confirmed": True, "message_id": MESSAGE_ID,
                      "messages_edited": 0, "status": "confirmed", "route_verified": True}
            d._atomic_json(receipt_path, result)
            return result
        # Do not re-edit when a previous POST may have succeeded without a reply.
        raise d.DeliveryError("Eugene correction has an unresolved prior attempt; automatic replay stopped")
    transport = transport or (lambda method, payload=None: d._telegram(token, method, payload))
    try:
        account = transport("getMe")
        if not account.get("ok") or str((account.get("result") or {}).get("username") or "").casefold() != d.EXPECTED_BOT.casefold():
            raise d.DeliveryError("Eugene edit bot username differs from original sender")
    except Exception:
        raise d.DeliveryError("Eugene edit bot identity preflight failed") from None

    def begin(record):
        record.update(status="in_flight", attempts=1, requested_at_utc=d._now())
    _cas(api, text_sha, route, begin)
    try:
        response = transport("editMessageText", {
            "chat_id": chat, "message_id": MESSAGE_ID, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": "true",
        })
        reply = response.get("result") or {}
        if (response.get("ok") is not True or
                reply.get("message_id") != MESSAGE_ID or
                reply.get("message_thread_id") != source_receipt.get("message_thread_id") or
                reply.get("text") != c.plain_text(text)):
            raise d.DeliveryError("Eugene Telegram edit response not provably identical")
        check = d._recipient(reply, chat)
        if check not in {"numeric_id_equal", "username_equal"}:
            raise d.DeliveryError("Eugene edited message recipient mismatch")
    except Exception:
        def ambiguous(record):
            record.update(status="ambiguous", stopped_at_utc=d._now())
        try:
            _cas(api, text_sha, route, ambiguous)
        except Exception:
            pass
        raise d.DeliveryError("Eugene edit response unclear; no automatic retry") from None

    def confirmed(record):
        record.update(status="confirmed", verified_method="reply_message_id_recipient_text_equal",
                      verified_response_text_sha256=d._digest(c.plain_text(text)),
                      chat_verification=check, confirmed_at_utc=d._now())
    _cas(api, text_sha, route, confirmed)
    result = {"already_confirmed": False, "message_id": MESSAGE_ID,
              "messages_edited": 1, "status": "confirmed",
              "route_verified": True, "replacement_sha256": text_sha,
              "plain_text_chars": len(c.plain_text(text))}
    d._atomic_json(receipt_path, result)
    return result


def main() -> int:
    try:
        api = d.GitHubAPI(os.environ.get("GITHUB_REPOSITORY", ""),
                          os.environ.get("GH_TOKEN", ""))
        result = edit_once(api, os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
                           os.environ.get("TELEGRAM_CHAT_ID", "").strip())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print("ROBOTIS Eugene 406 scoped edit stopped: " +
              (str(exc) if isinstance(exc, d.DeliveryError) else type(exc).__name__),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

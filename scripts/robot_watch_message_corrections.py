#!/usr/bin/env python3
"""Apply pinned corrections to proven existing Telegram messages only.

No send/delete endpoint is used. Before any edit, all pending batches bind the
artifact digest, complete original receipts, current delivery history, route,
and immutable replacement payload. Each intent and confirmation is CAS-merged
into the newest state; unrelated state is preserved. Repeating the same setter
is safe after a lost reply, but 'not modified' is accepted only for a previously
persisted identical request and the exact Telegram error response.
"""
from __future__ import annotations

import argparse
import base64
import copy
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import urllib.error

import robot_watch_delivery as delivery

MANIFEST_PATH = Path("data/robot_watch_message_correction_20261118.json")
RECEIPT_PATH = Path("out/robot_watch_message_correction_receipts.json")
NOT_MODIFIED_DESCRIPTION = (
    "Bad Request: message is not modified: specified new message content and reply markup "
    "are exactly the same as a current content and reply markup of the message"
)


class CorrectionError(delivery.DeliveryError):
    pass


def object_sha(value) -> str:
    return delivery._digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(text: str) -> str:
    # Telegram returns Message.text without HTML tags, with entities decoded.
    delivery._html_links(text)
    parser = _PlainText()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def footer(text: str) -> str:
    match = re.search(r"(?m)^<b>판정 기준</b>", text)
    return text[match.start():].strip() if match else ""


def article_blocks(text: str, pending: dict) -> dict[str, str]:
    delivery.build_chunks(text, pending)
    by_link = {row["link"]: row["key"] for row in pending["last_selected_events"]}
    matches = list(delivery._ARTICLE.finditer(text))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start():end].strip()
        tail = footer(block)
        if tail:
            block = block[:-len(tail)].strip()
        keys = [by_link[url] for url in delivery._html_links(block) if url in by_link]
        result[keys[0]] = re.sub(r"^<b>\d+\.", "<b>#.", block)
    return result


def _request_definition(batch: dict, message: dict) -> dict:
    return {
        "method": "editMessageText", "route_fingerprint": batch["route_fingerprint"],
        "message_id": message["message_id"], "text": message["text"],
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }


def payload_sha(batch: dict, messages: list[dict]) -> str:
    return object_sha([_request_definition(batch, message) for message in messages])


def validate_manifest(manifest: dict) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise CorrectionError("Correction manifest schema is invalid")
    if manifest.get("expected_bot") != delivery.EXPECTED_BOT:
        raise CorrectionError("Correction manifest bot identity disagrees")
    batches = manifest.get("batches")
    if not isinstance(batches, list) or not batches:
        raise CorrectionError("Correction manifest has no batches")
    plans, ids, targets = [], set(), set()
    for batch in batches:
        if not isinstance(batch, dict) or not re.fullmatch(r"[a-z0-9_-]{8,120}", str(batch.get("batch_id") or "")):
            raise CorrectionError("Correction batch identity is invalid")
        if batch["batch_id"] in ids:
            raise CorrectionError("Correction batch identity is repeated")
        ids.add(batch["batch_id"])
        for field in ("original_alert_sha256", "original_pending_sha256", "original_receipts_sha256", "payload_sha256", "route_fingerprint"):
            if not delivery._HEX.fullmatch(str(batch.get(field) or "")):
                raise CorrectionError("Correction manifest hash is missing or invalid")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(batch.get("artifact_digest") or "")):
            raise CorrectionError("Correction artifact digest is not pinned")
        for field in ("source_run_id", "artifact_id"):
            if type(batch.get(field)) is not int or batch[field] <= 0:
                raise CorrectionError("Correction source identity is invalid")
        message_ids = batch.get("message_ids")
        if (not isinstance(message_ids, list) or len(message_ids) != 2
                or any(type(mid) is not int or mid <= 0 for mid in message_ids)
                or len(set(message_ids)) != len(message_ids)):
            raise CorrectionError("Correction requires exactly two unique original message IDs")
        for field in ("original_chunk_sha256", "corrected_chunk_sha256"):
            values = batch.get(field)
            if (not isinstance(values, list) or len(values) != len(message_ids)
                    or any(not isinstance(value, str) or not delivery._HEX.fullmatch(value) for value in values)):
                raise CorrectionError("Correction chunk hashes are missing or invalid")
        for mid in message_ids:
            target = (batch["route_fingerprint"], mid)
            if target in targets:
                raise CorrectionError("Two correction batches target the same message")
            targets.add(target)
        text, pending = batch.get("corrected_text"), batch.get("corrected_pending")
        if not isinstance(text, str) or not text.startswith("✏️ <b>정정</b>") or not isinstance(pending, dict):
            raise CorrectionError("Correction text or event mapping is invalid")
        chunks = delivery.build_chunks(text, pending)
        if len(chunks) != len(message_ids):
            raise CorrectionError("Correction chunk count differs from the original message count")
        messages = [dict(chunk, message_id=mid) for chunk, mid in zip(chunks, message_ids)]
        if [message["sha256"] for message in messages] != batch.get("corrected_chunk_sha256"):
            raise CorrectionError("Correction chunk payload changed after review")
        if payload_sha(batch, messages) != batch["payload_sha256"]:
            raise CorrectionError("Correction request payload hash differs from the pinned hash")
        plans.append({"batch": batch, "messages": messages})
    return plans


def _identity(plan: dict) -> dict:
    batch = plan["batch"]
    fields = ("source_run_id", "artifact_id", "artifact_digest", "route_fingerprint", "message_ids",
              "original_alert_sha256", "original_pending_sha256", "original_receipts_sha256",
              "original_chunk_sha256", "corrected_chunk_sha256", "payload_sha256")
    return {field: copy.deepcopy(batch[field]) for field in fields}


def _record(state: dict, plan: dict) -> dict | None:
    records = state.get("message_corrections", {})
    if not isinstance(records, dict):
        raise CorrectionError("Existing correction metadata has an unsupported format")
    record = records.get(plan["batch"]["batch_id"])
    if record is None:
        return None
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise CorrectionError("Existing correction record is malformed")
    if any(record.get(key) != value for key, value in _identity(plan).items()):
        raise CorrectionError("Existing correction batch has a different original or replacement payload")
    messages = record.get("messages")
    if not isinstance(messages, dict):
        raise CorrectionError("Existing correction message records are malformed")
    expected_ids = {str(message["message_id"]) for message in plan["messages"]}
    if set(messages) - expected_ids:
        raise CorrectionError("Existing correction targets an unapproved message")
    for message in plan["messages"]:
        receipt = messages.get(str(message["message_id"]))
        if receipt is not None and (not isinstance(receipt, dict)
                or receipt.get("request_sha256") != object_sha(_request_definition(plan["batch"], message))
                or receipt.get("replacement_sha256") != message["sha256"]):
            raise CorrectionError("Existing message correction payload does not match")
        if receipt is None:
            continue
        if (receipt.get("message_id") != message["message_id"]
                or receipt.get("status") not in {"in_flight", "ambiguous", "rejected", "confirmed"}
                or type(receipt.get("request_count")) is not int or receipt["request_count"] < 1):
            raise CorrectionError("Existing message correction attempt evidence is invalid")
        requested_at = delivery._timestamp(receipt.get("requested_at_utc"))
        if receipt.get("status") == "confirmed":
            verification = receipt.get("verification")
            expected_chat_checks = {
                "reply_message_id_recipient_text_equal": {"numeric_id_equal", "username_equal"},
                "prior_identical_request_exact_not_modified": {"original_receipt_and_identical_persisted_request"},
            }
            if (verification not in expected_chat_checks
                    or receipt.get("chat_verification") not in expected_chat_checks[verification]
                    or receipt.get("response_text_sha256") != delivery._digest(plain_text(message["text"]))
                    or (verification == "prior_identical_request_exact_not_modified" and receipt["request_count"] < 2)
                    or delivery._timestamp(receipt.get("confirmed_at_utc")) < requested_at):
                raise CorrectionError("Existing confirmed correction lacks verified message evidence")
    confirmed = [message["message_id"] for message in plan["messages"]
                 if (messages.get(str(message["message_id"])) or {}).get("status") == "confirmed"]
    if record.get("completed_message_ids") != confirmed:
        raise CorrectionError("Existing correction completion IDs disagree with verified evidence")
    return record


def _completed(state: dict, plan: dict) -> bool:
    record = _record(state, plan)
    if not record or record.get("status") != "completed":
        return False
    expected = plan["batch"]["message_ids"]
    if record.get("completed_message_ids") != expected:
        raise CorrectionError("Completed correction marker lacks all message IDs")
    for message in plan["messages"]:
        receipt = record["messages"].get(str(message["message_id"])) or {}
        if (receipt.get("status") != "confirmed" or receipt.get("verification") not in {
                "reply_message_id_recipient_text_equal", "prior_identical_request_exact_not_modified"}
                or receipt.get("response_text_sha256") != delivery._digest(plain_text(message["text"]))):
            raise CorrectionError("Completed correction marker lacks verified message evidence")
    return True


def _check_history(state: dict, plan: dict, original_keys: set[str]) -> None:
    batch = plan["batch"]
    history = state.get("delivery_history")
    if not isinstance(history, list):
        raise CorrectionError("Current state has no original delivery history")
    matches = [row for row in history if isinstance(row, dict) and row.get("run_id") == batch["source_run_id"]]
    if len(matches) != 1:
        raise CorrectionError("Original run is missing or duplicated in current delivery history")
    row = matches[0]
    if (row.get("outcome") != "sent" or row.get("message_ids") != batch["message_ids"]
            or row.get("recipient_verified") is not True
            or set(row.get("confirmed_event_keys") or []) != original_keys
            or not original_keys <= set(state.get("seen") or [])):
        raise CorrectionError("Original delivery history, recipient or confirmed keys disagree")


def validate_original(api, state: dict, plan: dict) -> None:
    batch = plan["batch"]
    run_id = batch["source_run_id"]
    run = api.json(f"/repos/{api.repository}/actions/runs/{run_id}")
    if (run.get("id") != run_id or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("head_branch") != "main"
            or str(run.get("path") or "").split("@")[0] != ".github/workflows/" + delivery.WORKFLOW):
        raise CorrectionError("Original run, workflow, branch or successful result disagrees")
    metadata = api.json(f"/repos/{api.repository}/actions/artifacts/{batch['artifact_id']}")
    if (metadata.get("id") != batch["artifact_id"] or metadata.get("digest") != batch["artifact_digest"]
            or (metadata.get("workflow_run") or {}).get("id") != run_id):
        raise CorrectionError("Original artifact identity or pinned digest disagrees")
    files = delivery.read_artifact(api.download(batch["artifact_id"]), metadata, run_id)
    try:
        original = files[delivery.ALERT_PATH.name]
        pending = json.loads(files[delivery.PENDING_PATH.name])
        receipts = json.loads(files[delivery.RECEIPTS_PATH.name])
    except (KeyError, TypeError, ValueError):
        raise CorrectionError("Original artifact is missing complete message evidence") from None
    if (delivery._digest(original.strip()) != batch["original_alert_sha256"]
            or delivery._pending_digest(pending) != batch["original_pending_sha256"]
            or object_sha(receipts) != batch["original_receipts_sha256"]):
        raise CorrectionError("Original alert, pending selection or receipts were modified")
    keys = delivery.check_receipts(original, pending, receipts, batch["route_fingerprint"])
    checked_keys, ambiguous = delivery.artifact_delivery(files, run_id, batch["route_fingerprint"])
    if (ambiguous or keys != checked_keys or keys != set(pending["last_selected"])
            or [row["message_id"] for row in receipts] != batch["message_ids"]
            or [row["sha256"] for row in receipts] != batch.get("original_chunk_sha256")
            or any(row["run_id"] != run_id for row in receipts)):
        raise CorrectionError("Original receipts do not prove the complete pinned messages")
    _check_history(state, plan, keys)
    corrected = batch["corrected_pending"]
    removed = set(batch.get("removed_event_keys") or [])
    if set(corrected["last_selected"]) != keys - removed or not removed <= keys:
        raise CorrectionError("Correction unexpectedly adds or drops event keys")
    original_blocks = article_blocks(original, pending)
    replacement_blocks = article_blocks(batch["corrected_text"], corrected)
    changes = batch.get("article_changes") or {}
    if not isinstance(changes, dict) or set(changes) - set(corrected["last_selected"]):
        raise CorrectionError("Correction change scope is invalid")
    for key, replacement in replacement_blocks.items():
        change = changes.get(key)
        if change is None and replacement != original_blocks[key]:
            raise CorrectionError("An unrelated article changed in the correction")
        if change == "title_only" and replacement.split("\n", 1)[1] != original_blocks[key].split("\n", 1)[1]:
            raise CorrectionError("A title-only correction also changed its article body")
        if change not in {None, "title_only", "replace_article"}:
            raise CorrectionError("Unsupported correction change kind")
    if footer(original) != footer(batch["corrected_text"]):
        raise CorrectionError("The original footer or exchange-rate disclosure changed")
    plan["original_keys"] = keys
    plan["original_receipts"] = receipts


def _cas_update(api, plan: dict, mutate) -> dict:
    batch = plan["batch"]
    for _ in range(5):
        latest, sha = delivery._load_remote_state(api)
        existing = _record(latest, plan)
        if not _completed(latest, plan):
            _check_history(latest, plan, plan["original_keys"])
        record = copy.deepcopy(existing) if existing else {
            "schema_version": 1, **_identity(plan), "status": "prepared",
            "messages": {}, "completed_message_ids": [], "prepared_at_utc": delivery._now(),
        }
        mutate(record)
        record["completed_message_ids"] = [mid for mid in batch["message_ids"]
                                           if (record["messages"].get(str(mid)) or {}).get("status") == "confirmed"]
        record["status"] = "completed" if record["completed_message_ids"] == batch["message_ids"] else "partial"
        if record["status"] == "completed":
            record.setdefault("completed_at_utc", delivery._now())
        if record == existing:
            return latest
        merged = copy.deepcopy(latest)
        merged.setdefault("message_corrections", {})[batch["batch_id"]] = record
        content = base64.b64encode((json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode()).decode()
        try:
            api.json(f"/repos/{api.repository}/contents/{delivery.STATE_PATH.as_posix()}", "PUT", {
                "message": "Record verified ROBOTIS message correction [skip ci]",
                "content": content, "sha": sha, "branch": "main",
            })
            return merged
        except delivery.APIError as exc:
            if exc.status not in {409, 422}:
                raise
    raise CorrectionError("Correction state could not be persisted after five CAS attempts")


def _edit_reply(transport, payload: dict) -> dict:
    try:
        return transport("editMessageText", payload)
    except urllib.error.HTTPError as exc:
        # Parse only a small JSON error body. Never expose its credential URL.
        if exc.code != 400:
            raise CorrectionError("Telegram edit HTTP request failed (details redacted)") from None
        try:
            response = json.loads(delivery._read_bounded(exc, 4096))
        except (ValueError, UnicodeError, OSError):
            raise CorrectionError("Telegram edit error could not be verified") from None
        return response


def _write_receipts(path: Path, plans: list[dict], state: dict, error: str | None = None) -> dict:
    rows = []
    for plan in plans:
        record = _record(state, plan)
        rows.append({"batch_id": plan["batch"]["batch_id"], "status": record.get("status") if record else "not_started",
                     "record": copy.deepcopy(record)})
    report = {"schema_version": 1, "checked_at_utc": delivery._now(), "batches": rows}
    if error:
        report["error_type"] = error
    delivery._atomic_json(path, report)
    return report


def apply_corrections(manifest: dict, api, token: str, chat: str, *,
                      receipt_path: Path = RECEIPT_PATH, transport=None) -> dict:
    plans = validate_manifest(manifest)
    if manifest.get("repository") != api.repository:
        raise CorrectionError("Correction repository differs from the pinned repository")
    fingerprint = delivery.route_fingerprint(chat)
    if any(plan["batch"]["route_fingerprint"] != fingerprint for plan in plans):
        raise CorrectionError("Correction route fingerprint mismatch (identifiers redacted)")
    state, _ = delivery._load_remote_state(api)
    remaining = [plan for plan in plans if not _completed(state, plan)]
    if not remaining:
        _write_receipts(receipt_path, plans, state)
        return {"batches_completed": len(plans), "messages_edited": 0, "already_completed": True}
    # Validate every pending batch before any Telegram or state mutation.
    for plan in remaining:
        validate_original(api, state, plan)
    if not token:
        raise CorrectionError("Missing Telegram correction credential")
    transport = transport or (lambda method, payload=None: delivery._telegram(token, method, payload))
    try:
        account = transport("getMe")
        if (not isinstance(account, dict) or account.get("ok") is not True
                or str((account.get("result") or {}).get("username") or "").casefold() != delivery.EXPECTED_BOT.casefold()):
            raise CorrectionError("Telegram correction bot identity mismatch")
    except Exception:
        raise CorrectionError("Telegram correction bot preflight failed (details redacted)") from None
    edits = 0
    for plan in remaining:
        batch = plan["batch"]
        for message in plan["messages"]:
            latest, _ = delivery._load_remote_state(api)
            record = _record(latest, plan)
            prior = (record or {}).get("messages", {}).get(str(message["message_id"]), {})
            if prior.get("status") == "confirmed":
                state = latest
                continue
            request_hash = object_sha(_request_definition(batch, message))
            replay = (prior.get("request_sha256") == request_hash
                      and prior.get("status") in {"in_flight", "ambiguous"}
                      and type(prior.get("request_count")) is int and prior["request_count"] >= 1)
            def intent(record):
                previous = record["messages"].get(str(message["message_id"]), {})
                if previous.get("status") == "confirmed":
                    return
                record["messages"][str(message["message_id"])] = {
                    **previous, "message_id": message["message_id"], "status": "in_flight",
                    "request_sha256": request_hash, "replacement_sha256": message["sha256"],
                    "request_count": previous.get("request_count", 0) + 1, "requested_at_utc": delivery._now(),
                }
            state = _cas_update(api, plan, intent)
            if state["message_corrections"][batch["batch_id"]]["messages"][str(message["message_id"])]["status"] == "confirmed":
                continue
            payload = {"chat_id": chat, "message_id": message["message_id"], "text": message["text"],
                       "parse_mode": "HTML", "disable_web_page_preview": "true"}
            rejected = False
            try:
                response = _edit_reply(transport, payload)
                if not isinstance(response, dict):
                    raise CorrectionError("Telegram edit reply is not a JSON object")
                expected_plain = plain_text(message["text"])
                if response.get("ok") is True:
                    reply = response.get("result")
                    if not isinstance(reply, dict) or reply.get("message_id") != message["message_id"]:
                        raise CorrectionError("Telegram edit reply changed the target message identity")
                    recipient = delivery._recipient(reply, chat)
                    if reply.get("text") != expected_plain:
                        raise CorrectionError("Telegram edit reply text differs from the pinned replacement")
                    original_receipt = plan["original_receipts"][message["chunk_index"]]
                    if reply.get("message_thread_id") != original_receipt.get("message_thread_id"):
                        raise CorrectionError("Telegram edit reply changed the original message topic")
                    verification = "reply_message_id_recipient_text_equal"
                elif (response.get("ok") is False and response.get("error_code") == 400
                      and response.get("description") == NOT_MODIFIED_DESCRIPTION and replay):
                    # The immutable original receipt proves the target route;
                    # an earlier CAS intent proves the identical replacement.
                    recipient = "original_receipt_and_identical_persisted_request"
                    verification = "prior_identical_request_exact_not_modified"
                else:
                    rejected = True
                    raise CorrectionError("Telegram explicitly rejected the pinned correction")
                receipt = {
                    "status": "confirmed", "confirmed_at_utc": delivery._now(),
                    "verification": verification, "chat_verification": recipient,
                    "response_text_sha256": delivery._digest(expected_plain),
                }
                def confirm(record):
                    record["messages"][str(message["message_id"])].update(receipt)
                state = _cas_update(api, plan, confirm)
                edits += 1
                _write_receipts(receipt_path, plans, state)
            except Exception as exc:
                def failed(record):
                    current = record["messages"].get(str(message["message_id"]), {})
                    if current.get("status") != "confirmed":
                        current.update(status="rejected" if rejected else "ambiguous",
                                       error_type=type(exc).__name__, stopped_at_utc=delivery._now())
                try:
                    state = _cas_update(api, plan, failed)
                except Exception:
                    pass  # The persisted pre-edit intent still supports safe retry.
                _write_receipts(receipt_path, plans, state, type(exc).__name__)
                raise CorrectionError("Correction stopped; existing message IDs and verified partial progress retained") from None
    state, _ = delivery._load_remote_state(api)
    if not all(_completed(state, plan) for plan in plans):
        raise CorrectionError("Correction finished without all verified completion markers")
    _write_receipts(receipt_path, plans, state)
    return {"batches_completed": len(plans), "messages_edited": edits, "already_completed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=RECEIPT_PATH)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        api = delivery.GitHubAPI(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", ""))
        result = apply_corrections(manifest, api, os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
                                   os.environ.get("TELEGRAM_CHAT_ID", "").strip(), receipt_path=args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, delivery.DeliveryError) else type(exc).__name__
        print("ROBOTIS message correction stopped: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

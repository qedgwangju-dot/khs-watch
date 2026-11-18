"""One authorized edit of optics message 504; never create a new message."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

try:
    from scripts import ai_networking_optics_delivery as delivery
except ModuleNotFoundError:
    import ai_networking_optics_delivery as delivery


BUNDLE_KEY = "9fc3aa5c7e228759a22505ecdffb6c0305238adb2a458c80f572f4394d1edacf"
ORIGINAL_PART_HASH = "4440df731dcacb74d52eb024f7870db059d38d78ea6bdcc5597edd02e41e5a9c"
ROUTE_KEY = "e06789d08ffbc610316e034294fc31cc16aee21380f9465db7a03610b61897c0"
MESSAGE_ID = 504
BOT_USERNAME = "khs88798879887988798879_bot"
ORIGINAL_SOURCE_SHA = "8cf89a3bd32f794cc8287d94927c7e89904a3ffc"
DEADLINE = dt.datetime(2026, 11, 19, 2, 4, 19, tzinfo=dt.timezone.utc)
LEDGER_PATH = Path("data/ai_networking_optics_delivery_receipts.json")
OUTPUT_PATH = Path("out/optics_duplicate_20261118_correction.json")
DEFAULT_ORIGINAL_PATH = Path("tests/fixtures/optics_duplicate_20261118_original.html")
CORRECTION_TEXT = """정정 — Lambda 광통신 알림

■ 2026년 11월 18일 11:04에 표시된 이 알림은 11월 16일 Lambda·NVIDIA의 기존 발표를 다룬 재보도여서 신규 알림으로 취급하지 않습니다.

■ 원제목은 “Lambda, Blackwell GPU 기반 첫 CPO 구축 사례 강조”이며, 앞선 본문은 자동번역 실패로 제목이 빠져 있었습니다.

■ 이번 기사에서 별도 신규 고객·계약·추가 가동은 확인되지 않았으며, 검색 분류 간 중복 판정과 번역 실패 처리를 수정했습니다.

공식 발표: https://blogs.nvidia.com/blog/lambda-photonics/
재보도: https://www.hpcwire.com/2026/11/17/lambda-touts-first-cpo-deployment-of-blackwell-gpus/"""


class RepairFailure(RuntimeError):
    """Only stable, non-sensitive error codes may reach logs or exceptions."""
    def __init__(self, code: str, status: str = "blocked", response=None):
        super().__init__(code)
        self.code, self.status, self.response = code, status, response


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def require_window(now: dt.datetime) -> None:
    if now.tzinfo is None or now > DEADLINE:
        raise RepairFailure("authorized_correction_window_closed")


def validate_ledger(ledger: dict, original: str) -> dict:
    if delivery.digest(original) != ORIGINAL_PART_HASH:
        raise RepairFailure("original_message_hash_mismatch")
    if delivery.digest(ROUTE_KEY + "|" + original) != BUNDLE_KEY:
        raise RepairFailure("original_bundle_hash_mismatch")
    entry = ledger.get("bundles", {}).get(BUNDLE_KEY)
    if not isinstance(entry, dict):
        raise RepairFailure("authorized_bundle_missing")
    if (entry.get("status") != "complete" or entry.get("state_persisted") is not True
            or entry.get("route_key") != ROUTE_KEY or entry.get("bot_username") != BOT_USERNAME
            or entry.get("source_sha") != ORIGINAL_SOURCE_SHA
            or entry.get("part_hashes") != [ORIGINAL_PART_HASH]):
        raise RepairFailure("authorized_bundle_metadata_mismatch")
    receipts = entry.get("receipts", {})
    if not isinstance(receipts, dict) or set(receipts) != {"0"}:
        raise RepairFailure("authorized_part_receipt_mismatch")
    receipt = receipts["0"]
    if (not isinstance(receipt, dict) or receipt.get("status") != "confirmed"
            or not delivery.valid_id(receipt.get("message_id")) or receipt["message_id"] != MESSAGE_ID
            or receipt.get("chat_identity_verified") is not True
            or receipt.get("source_sha") != ORIGINAL_SOURCE_SHA):
        raise RepairFailure("authorized_message_receipt_mismatch")
    return entry


def checked_out_sha() -> str:
    if os.getenv("GITHUB_EVENT_NAME") != "push" or os.getenv("GITHUB_REF") != "refs/heads/main":
        raise RepairFailure("correction_requires_authorized_main_push")
    expected = os.getenv("GITHUB_SHA", "")
    try:
        actual = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except Exception:
        raise RepairFailure("correction_code_revision_unavailable") from None
    if not re.fullmatch(r"[0-9a-f]{40}", expected) or actual != expected:
        raise RepairFailure("correction_code_revision_mismatch")
    return actual


def redact_response(value, secrets: tuple[str, ...]):
    """Store only evidence needed for this edit, without recipient profile data."""
    if not isinstance(value, dict):
        return {"response_type": type(value).__name__}
    clean = {"ok": value.get("ok") is True}
    if isinstance(value.get("error_code"), int):
        clean["error_code"] = value["error_code"]
    if "description" in value:
        clean["description"] = "message_not_modified" if is_not_modified(value) else "telegram_error_details_omitted"
    message = value.get("result")
    if isinstance(message, dict):
        result = {}
        for key in ("message_id", "date", "edit_date"):
            number = message.get(key)
            if isinstance(number, int) and not isinstance(number, bool):
                result[key] = "[redacted]" if str(number) in secrets else number
        if isinstance(message.get("text"), str):
            if message["text"] == CORRECTION_TEXT:
                result["text"] = CORRECTION_TEXT
            else:
                result["unexpected_text_sha256"] = delivery.digest(message["text"])
        chat = message.get("chat")
        if isinstance(chat, dict):
            result["chat"] = {"id": "[redacted]", "type": chat.get("type") if chat.get("type") in {"private", "group", "supergroup", "channel"} else "unknown"}
        sender = message.get("from")
        if isinstance(sender, dict):
            result["from"] = {"id": "[redacted]", "is_bot": sender.get("is_bot") is True,
                "username": BOT_USERNAME if sender.get("username") == BOT_USERNAME else "[redacted]"}
        clean["result"] = result
    elif "result" in value:
        clean["result_type"] = type(message).__name__
    return clean


def is_not_modified(value) -> bool:
    return (isinstance(value, dict) and value.get("ok") is False and value.get("error_code") == 400
        and str(value.get("description", "")).lower().startswith("bad request: message is not modified"))


def edit_existing(token: str, chat_id: int) -> dict:
    payload = {"chat_id": chat_id, "message_id": MESSAGE_ID, "text": CORRECTION_TEXT,
               "link_preview_options": {"is_disabled": True}}
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/editMessageText",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            value = json.loads(response.read(1_000_000).decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            value = json.loads(error.read(1_000_000).decode("utf-8"))
        except Exception:
            value = {"ok": False, "error_code": error.code}
        if error.code == 400 and is_not_modified(value):
            return value
        status = "edit_rejected" if 400 <= error.code < 500 else "edit_outcome_unknown"
        raise RepairFailure("telegram_edit_http_failure", status, value) from None
    except Exception:
        raise RepairFailure("telegram_edit_response_unavailable", "edit_outcome_unknown") from None
    if not isinstance(value, dict):
        raise RepairFailure("telegram_edit_malformed_response", "edit_outcome_unknown")
    if value.get("ok") is False and not is_not_modified(value):
        raise RepairFailure("telegram_edit_rejected", "edit_rejected", value)
    return value


def repair_once(original_path: Path, *, ledger_path: Path = LEDGER_PATH,
                output_path: Path = OUTPUT_PATH) -> dict:
    audit = {"status": "blocked", "verified_edit": False, "message_id": MESSAGE_ID,
        "bot_username": BOT_USERNAME, "route_key": ROUTE_KEY, "bundle_key": BUNDLE_KEY,
        "original_part_sha256": ORIGINAL_PART_HASH, "original_source_sha": ORIGINAL_SOURCE_SHA,
        "correction_text": CORRECTION_TEXT, "correction_sha256": delivery.digest(CORRECTION_TEXT),
        "deadline_utc": DEADLINE.isoformat(), "started_at_utc": utc_now().isoformat(),
        "new_message_created": False, "ledger_modified": False}
    sensitive = (os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""))
    failure = None
    requested = False
    try:
        require_window(utc_now())
        audit["repair_source_sha"] = checked_out_sha()
        try:
            original = original_path.read_text(encoding="utf-8").strip()
            ledger = delivery.read_json(ledger_path)
        except Exception:
            raise RepairFailure("original_or_ledger_unavailable") from None
        validate_ledger(ledger, original)
        audit["original_text"] = original
        audit["ledger_sha256_before"] = delivery.digest(ledger)
        token, configured_chat = sensitive
        if not token or not configured_chat:
            raise RepairFailure("configured_telegram_route_missing")
        try:
            route, username, _unused_sender = delivery.verified_sender(token, configured_chat, BOT_USERNAME)
            if route != ROUTE_KEY or username != BOT_USERNAME:
                raise RepairFailure("authorized_telegram_route_mismatch")
            # Resolve a numeric target and re-bind it to the verified bot. This
            # avoids editing through a mutable @channel alias.
            bot = delivery._telegram_read(token, "getMe")
            chat = delivery._telegram_read(token, "getChat", {"chat_id": configured_chat})
        except RepairFailure:
            raise
        except Exception:
            raise RepairFailure("telegram_route_verification_failed") from None
        chat_id = chat.get("id")
        if (not delivery.valid_id(bot.get("id")) or bot.get("is_bot") is not True
                or bot.get("username") != BOT_USERNAME or not isinstance(chat_id, int) or isinstance(chat_id, bool)
                or delivery.digest(f"{bot['id']}|{BOT_USERNAME.lower()}|{chat_id}") != ROUTE_KEY):
            raise RepairFailure("telegram_numeric_route_or_bot_mismatch")
        sensitive = (*sensitive, str(chat_id))
        audit["route_identity_verified"] = True
        audit["bot_identity_verified"] = True
        require_window(utc_now())  # The read-only checks may have crossed expiry.
        audit["status"] = "edit_pending"
        delivery.atomic_json(output_path, audit)  # Fail before editing if audit cannot be saved.
        requested = True
        response = edit_existing(token, chat_id)
        audit["api_response"] = redact_response(response, sensitive)
        if is_not_modified(response):
            audit.update(status="already_applied_not_modified", verified_edit=False,
                result_note="API reported unchanged content; no fresh edited-message receipt was returned")
        else:
            message = response.get("result")
            returned_chat = message.get("chat") if isinstance(message, dict) else None
            returned_bot = message.get("from") if isinstance(message, dict) else None
            checks = {
                "ok": response.get("ok") is True,
                "message_id": isinstance(message, dict) and delivery.valid_id(message.get("message_id")) and message.get("message_id") == MESSAGE_ID,
                "chat": isinstance(returned_chat, dict) and isinstance(returned_chat.get("id"), int) and not isinstance(returned_chat.get("id"), bool) and returned_chat.get("id") == chat_id,
                "text": isinstance(message, dict) and message.get("text") == CORRECTION_TEXT,
                "bot": isinstance(returned_bot, dict) and delivery.valid_id(returned_bot.get("id")) and returned_bot.get("id") == bot["id"] and returned_bot.get("username") == BOT_USERNAME and returned_bot.get("is_bot") is True,
            }
            audit["response_checks"] = checks
            if not all(checks.values()):
                raise RepairFailure("edited_message_receipt_not_verified", "edit_response_unverified", response)
            audit.update(status="verified_edit", verified_edit=True)
        # Only compare; never rewrite the ledger or watcher state.
        if delivery.digest(delivery.read_json(ledger_path)) != audit["ledger_sha256_before"]:
            raise RepairFailure("ledger_changed_during_correction", "edit_response_unverified")
        audit["ledger_unchanged_verified"] = True
    except RepairFailure as error:
        failure = error
        audit.update(status=error.status, verified_edit=False, error_code=error.code)
        if error.response is not None:
            audit["api_response"] = redact_response(error.response, sensitive)
    except Exception:
        failure = RepairFailure("correction_unexpected_failure", "edit_outcome_unknown" if requested else "blocked")
        audit.update(status=failure.status, verified_edit=False, error_code=failure.code)
    finally:
        audit["finished_at_utc"] = utc_now().isoformat()
        try:
            delivery.atomic_json(output_path, audit)
        except Exception:
            raise RepairFailure("correction_audit_write_failed", "edit_outcome_unknown" if requested else "blocked") from None
    if failure is not None:
        raise failure from None
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-path", type=Path, default=DEFAULT_ORIGINAL_PATH)
    args = parser.parse_args()
    try:
        result = repair_once(args.original_path)
    except RepairFailure as error:
        print(f"optics_correction_status={error.status} error_code={error.code} new_message_created=false")
        return 1
    print(f"optics_correction_status={result['status']} verified_edit={str(result['verified_edit']).lower()} message_id={MESSAGE_ID} new_message_created=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

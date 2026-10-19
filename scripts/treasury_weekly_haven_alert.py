#!/usr/bin/env python3
"""Send one verified weekly stock/Treasury regime alert via the EXISTING bond bot.

No independent scheduled workflow is created. Caller supplies the existing
GLOBAL_RATES Telegram secrets as TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import treasury_weekly_stock_bond_signal as signal

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "treasury_weekly_haven_state.json"
OUT_PATH = ROOT / "out" / "treasury_weekly_haven_alert.txt"
HTML_PATH = ROOT / "out" / "treasury_weekly_haven_telegram.html.txt"
RECEIPT_PATH = ROOT / "out" / "treasury_weekly_haven_confirmed.json"
FORMAT_REVISION = 2
EXPECTED_BOT = "khs8879887988798879_bot"


def load_state(path=STATE_PATH):
    if not path.exists():
        return {"last_alert": None}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or "last_alert" not in value:
        raise RuntimeError("weekly safe-haven state invalid; refusing to reset it")
    return value


def write_state(state, path=STATE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=".treasury_weekly_", suffix=".tmp", delete=False
    ) as temp:
        temp.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        tmpname = temp.name
    os.replace(tmpname, path)


def already_delivered(state, end):
    record = state.get("last_alert") or {}
    return bool(
        record.get("end") == end
        and record.get("message_id")
        and record.get("bot_username") == EXPECTED_BOT
    )


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.source_links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.source_links.append(href)


def _post_telegram_html(text_html: str, *, method: str, message_id: int | None = None):
    if method not in ("sendMessage", "editMessageText"):
        raise ValueError("unexpected Telegram API method")
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        raise RuntimeError("existing Global Rates Telegram secrets missing")
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or EXPECTED_BOT).strip().lstrip("@")
    if expected != EXPECTED_BOT:
        raise RuntimeError("unexpected existing Telegram bot identifier")
    if len(text_html) > 3900:
        raise RuntimeError("Telegram HTML exceeds safe length")
    parser = _LinkParser()
    parser.feed(text_html)
    if len(parser.source_links) != 3:
        raise RuntimeError("Telegram HTML must contain exactly three clickable source links")

    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/getMe", timeout=20
    ) as response:
        identity = json.load(response)
    actual = (identity.get("result") or {}).get("username")
    if not identity.get("ok") or actual != EXPECTED_BOT:
        raise RuntimeError("Telegram bot mismatch; refusing to send or edit")
    payload = {
        "chat_id": chat_id,
        "text": text_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if method == "editMessageText":
        if not isinstance(message_id, int) or message_id < 1:
            raise RuntimeError("editing requires existing Telegram message_id")
        payload["message_id"] = message_id
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=urllib.parse.urlencode(payload).encode("utf-8"), method="POST"
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.load(response)
    delivered = result.get("result") or {}
    returned_id = delivered.get("message_id") if isinstance(delivered, dict) else None
    if not result.get("ok") or not isinstance(returned_id, int) or returned_id < 1:
        raise RuntimeError("Telegram did not acknowledge a message_id")
    if message_id is not None and returned_id != message_id:
        raise RuntimeError("Telegram edited unexpected message_id")
    returned_entities = [
        entity.get("url")
        for entity in (delivered.get("entities") or [])
        if entity.get("type") == "text_link"
    ]
    if sorted(returned_entities) != sorted(parser.source_links):
        raise RuntimeError("Telegram response does not confirm all three clickable source links")
    visible_text = str(delivered.get("text") or "")
    for required in ("나스닥100:", "미 10년물 금리:", "CTA", "공식 출처"):
        if required not in visible_text:
            raise RuntimeError("Telegram response missing expected visible content: " + required)
    return actual, returned_id


def send_telegram(text_html: str):
    return _post_telegram_html(text_html, method="sendMessage")


def edit_telegram(text_html: str, message_id: int):
    return _post_telegram_html(text_html, method="editMessageText", message_id=message_id)


def run(validate_only=False, now=None, path=STATE_PATH, repair_format=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    if validate_only and repair_format:
        raise ValueError("validation and actual Telegram editing cannot run together")
    end = signal.completed_friday(now).isoformat()
    state = load_state(path)
    was_delivered = already_delivered(state, end)
    if was_delivered and not validate_only and not repair_format:
        return {"status": "duplicate_suppressed", "end": end, "telegram_sent": False}
    if repair_format:
        if not was_delivered:
            raise RuntimeError("cannot edit a weekly message without a confirmed same-week receipt")
        previous_receipt = state["last_alert"]
        if previous_receipt.get("format_revision", 1) >= FORMAT_REVISION:
            return {
                "status": "format_already_current", "end": end,
                "message_id": previous_receipt["message_id"],
                "telegram_sent": False,
            }

    try:
        data = signal.fetch_current_week(now)
    except (signal.SourceMissing, ValueError, OSError) as exc:
        return {
            "status": "source_unavailable",
            "end": end,
            "reason": f"{type(exc).__name__}: {str(exc)[:350]}",
            "telegram_sent": False,
        }
    except Exception as exc:
        return {
            "status": "source_unavailable",
            "end": end,
            "reason": f"{type(exc).__name__}: {str(exc)[:350]}",
            "telegram_sent": False,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = signal.report_text(data)
    telegram_html = signal.report_html(data)
    OUT_PATH.write_text(text + "\n", encoding="utf-8")
    HTML_PATH.write_text(telegram_html + "\n", encoding="utf-8")
    if not data["alert"]:
        if repair_format:
            raise RuntimeError("existing alert is confirmed but refreshed official signals no longer satisfy threshold")
        return {"status": "threshold_not_met", "end": end, "telegram_sent": False, "category": data["category"]}
    if validate_only:
        return {
            "status": "validated", "end": end, "telegram_sent": False,
            "format_revision": FORMAT_REVISION, "data": data,
            "clickable_sources": 3,
        }

    if repair_format:
        previous_receipt = state["last_alert"]
        if (
            data["category"] != previous_receipt.get("category")
            or abs(data["ndx_week_pct"] - previous_receipt.get("ndx_week_pct", float("inf"))) > 0.02
            or abs(data["y10_week_bp"] - previous_receipt.get("y10_week_bp", float("inf"))) > 0.1
        ):
            raise RuntimeError("live official weekly data diverge from previous confirmed Telegram message")
        username, confirmed_id = edit_telegram(telegram_html, int(previous_receipt["message_id"]))
        previous_receipt["format_revision"] = FORMAT_REVISION
        previous_receipt["edited_at_kst"] = dt.datetime.now(
            ZoneInfo("Asia/Seoul")
        ).isoformat(timespec="seconds")
        previous_receipt["clickable_source_links"] = 3
        write_state(state, path)
        receipt = {
            "operation": "editMessageText", "end": end, "message_id": confirmed_id,
            "bot_username": username, "format_revision": FORMAT_REVISION,
            "telegram_sent": False, "telegram_edited": True,
        }
        RECEIPT_PATH.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"status": "telegram_edited", **receipt}

    username, message_id = send_telegram(telegram_html)
    receipt = {
        "end": end,
        "category": data["category"],
        "ndx_week_pct": data["ndx_week_pct"],
        "y10_week_bp": data["y10_week_bp"],
        "bot_username": username,
        "message_id": message_id,
        "format_revision": FORMAT_REVISION,
        "clickable_source_links": 3,
        "confirmed_at_kst": dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state["last_alert"] = receipt
    write_state(state, path)
    return {"status": "telegram_confirmed", "telegram_sent": True, **receipt}


def main():
    validation = os.getenv("WEEKLY_HAVEN_VALIDATE_ONLY", "").lower() in ("1", "true", "yes")
    repair = os.getenv("WEEKLY_HAVEN_REPAIR_FORMAT", "").lower() in ("1", "true", "yes")
    result = run(validate_only=validation, repair_format=repair)
    print("treasury_weekly_haven_status=" + json.dumps(result, ensure_ascii=False))
    if result["status"] == "source_unavailable":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

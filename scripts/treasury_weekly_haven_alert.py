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
from zoneinfo import ZoneInfo

import treasury_weekly_stock_bond_signal as signal

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "treasury_weekly_haven_state.json"
OUT_PATH = ROOT / "out" / "treasury_weekly_haven_alert.txt"
RECEIPT_PATH = ROOT / "out" / "treasury_weekly_haven_confirmed.json"
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


def send_telegram(text):
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        raise RuntimeError("existing Global Rates Telegram secrets missing")
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or EXPECTED_BOT).strip().lstrip("@")
    if expected != EXPECTED_BOT:
        raise RuntimeError("unexpected existing Telegram bot identifier")
    if len(text) > 4000:
        raise RuntimeError("Telegram message too long")
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/getMe", timeout=20
    ) as response:
        identity = json.load(response)
    actual = (identity.get("result") or {}).get("username")
    if not identity.get("ok") or actual != EXPECTED_BOT:
        raise RuntimeError("Telegram bot mismatch; refusing to send")
    payload = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, method="POST"
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.load(response)
    message_id = (result.get("result") or {}).get("message_id")
    if not result.get("ok") or not isinstance(message_id, int) or message_id < 1:
        raise RuntimeError("Telegram did not acknowledge a message_id")
    return actual, message_id


def run(validate_only=False, now=None, path=STATE_PATH):
    now = now or dt.datetime.now(dt.timezone.utc)
    end = signal.completed_friday(now).isoformat()
    state = load_state(path)
    if already_delivered(state, end) and not validate_only:
        return {"status": "duplicate_suppressed", "end": end, "telegram_sent": False}
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
        # Source/provider failures are not successful 'no-news' checks.
        return {
            "status": "source_unavailable",
            "end": end,
            "reason": f"{type(exc).__name__}: {str(exc)[:350]}",
            "telegram_sent": False,
        }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = signal.report_text(data)
    OUT_PATH.write_text(text + "\n", encoding="utf-8")
    if not data["alert"]:
        return {"status": "threshold_not_met", "end": end, "telegram_sent": False, "category": data["category"]}
    if validate_only:
        return {"status": "validated", "end": end, "telegram_sent": False, "data": data}
    username, message_id = send_telegram(text)
    receipt = {
        "end": end,
        "category": data["category"],
        "ndx_week_pct": data["ndx_week_pct"],
        "y10_week_bp": data["y10_week_bp"],
        "bot_username": username,
        "message_id": message_id,
        "confirmed_at_kst": dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state["last_alert"] = receipt
    write_state(state, path)
    return {"status": "telegram_confirmed", "telegram_sent": True, **receipt}


def main():
    validation = os.getenv("WEEKLY_HAVEN_VALIDATE_ONLY", "").lower() in ("1", "true", "yes")
    result = run(validate_only=validation)
    print("treasury_weekly_haven_status=" + json.dumps(result, ensure_ascii=False))
    if result["status"] == "source_unavailable":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

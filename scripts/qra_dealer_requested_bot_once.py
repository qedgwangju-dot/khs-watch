#!/usr/bin/env python3
"""Deliver the already-confirmed October 16 QRA dealer event to the user-requested bot once.

Uses the existing QRA workflow and existing Treasury policy Telegram credentials;
does not alter the normal QRA bot or launch a separate event watcher.
"""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from scripts.qra_dealer_link_repair import build_original_message
except ImportError:
    from qra_dealer_link_repair import build_original_message

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "qra_recurring_alert_state.json"
CONFIRM = ROOT / "out" / "qra_requested_bot_dealer_confirmed.json"
EVENT = "dealer-agenda:2026-10-16:requested-bot:html-v1"
BOT = "hs88798879887988798879_bot"
KST = ZoneInfo("Asia/Seoul")


def main():
    CONFIRM.parent.mkdir(exist_ok=True, parents=True)
    CONFIRM.unlink(missing_ok=True)
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("dealer_requested_bot_event") == EVENT:
        print("dealer_requested_bot=already_confirmed_no_resend")
        return
    if state.get("dealer_links_edited_message_id") != 297:
        raise RuntimeError("Original QRA dealer event and source-links edit not confirmed")
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("Requested existing Telegram bot route credentials unavailable")
    with urllib.request.urlopen("https://api.telegram.org/bot" + token + "/getMe", timeout=25) as response:
        me = json.loads(response.read().decode("utf-8"))
    found = str((me.get("result") or {}).get("username") or "")
    if not me.get("ok") or found != BOT:
        raise RuntimeError("Wrong bot route: expected @" + BOT + ", got @" + found)
    message = build_original_message()
    if message.count('<a href="') != 2 or len(message) > 4096:
        raise RuntimeError("Original dealer links are not exactly two trusted HTML anchors")
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": message, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=data, method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.loads(response.read().decode("utf-8"))
    mid = (result.get("result") or {}).get("message_id")
    if not result.get("ok") or not mid:
        raise RuntimeError("Requested Telegram delivery not acknowledged")
    now = datetime.now(KST).isoformat(timespec="seconds")
    state["dealer_requested_bot_event"] = EVENT
    state["dealer_requested_bot_username"] = BOT
    state["dealer_requested_bot_message_id"] = mid
    state["dealer_requested_bot_sent_at_kst"] = now
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CONFIRM.write_text(json.dumps({
        "event": EVENT, "bot": BOT, "message_id": mid, "sent_at_kst": now,
        "link_format": "html", "original_qra_message_id": 297,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("dealer_requested_bot=sent_acknowledged message_id=" + str(mid))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

MAX_CHARS = 3900


def split_message(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in text.strip().split("\n\n"):
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) <= MAX_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > MAX_CHARS:
            chunks.append(paragraph[:MAX_CHARS])
            paragraph = paragraph[MAX_CHARS:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: space_launch_telegram_send.py REPORT_PATH", file=sys.stderr)
        return 2

    token = (os.getenv("SPACE_LAUNCH_TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("SPACE_LAUNCH_TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")

    if not token:
        raise RuntimeError("SPACE_LAUNCH_TELEGRAM_BOT_TOKEN is missing")
    if not chat_id:
        raise RuntimeError("SPACE_LAUNCH_TELEGRAM_CHAT_ID is missing")
    if not expected:
        raise RuntimeError("EXPECTED_TELEGRAM_BOT_USERNAME is missing")

    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
        identity = json.loads(response.read().decode("utf-8"))

    actual = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")

    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("Telegram report is empty")

    message_ids: list[int] = []
    for chunk in split_message(text):
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected message: {result}")
        message_ids.append(int(result["result"]["message_id"]))

    print(f"telegram_delivery_confirmed=true bot=@{actual} message_ids={message_ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

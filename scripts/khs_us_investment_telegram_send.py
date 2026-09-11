#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "khs_us_investment_alert.html"
DELIVERY = ROOT / "out" / "khs_us_investment_delivery.json"


def _api_json(url: str, *, data: bytes | None = None, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {exc.code}: {body}") from exc


def _resolve() -> tuple[str, dict]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token:
        raise RuntimeError("KHS887900_BOT_TOKEN secret is missing")

    identity = _api_json(f"https://api.telegram.org/bot{token}/getMe")
    username = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or username.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{username or 'unknown'}")

    def get_chat(chat_id: str) -> dict | None:
        if not chat_id:
            return None
        query = urllib.parse.urlencode({"chat_id": chat_id})
        try:
            result = _api_json(f"https://api.telegram.org/bot{token}/getChat?{query}")
            return result.get("result") if result.get("ok") else None
        except Exception:
            return None

    chat = None
    for chat_id in [
        (os.getenv("TELEGRAM_CHAT_ID_DIRECT") or "").strip(),
        (os.getenv("TELEGRAM_CHAT_ID_POLICY") or "").strip(),
        (os.getenv("TELEGRAM_CHAT_ID_GENERIC") or "").strip(),
    ]:
        chat = get_chat(chat_id)
        if chat:
            break

    if not chat:
        updates = _api_json(f"https://api.telegram.org/bot{token}/getUpdates?limit=100&timeout=0")
        for update in reversed(updates.get("result") or []):
            obj = update.get("message") or update.get("channel_post") or update.get("edited_message") or {}
            candidate = obj.get("chat") or {}
            if candidate.get("id") is not None:
                chat = candidate
                break

    if not chat or chat.get("id") is None:
        raise RuntimeError(f"@{expected} valid but no reachable chat resolved")
    return username, chat


def _visible_len(text: str) -> int:
    plain = re.sub(r"<[^>]+>", "", text)
    plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return len(plain)


def _split_html(text: str, limit: int = 3300) -> list[str]:
    # Every bold/link tag in the alert is line-local, so line-boundary splitting keeps HTML balanced.
    lines = text.splitlines()
    chunks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            chunks.append("\n".join(current).strip())
            current.clear()

    for line in lines:
        candidate = "\n".join(current + [line]).strip()
        if current and _visible_len(candidate) > limit:
            flush()
        if _visible_len(line) > limit:
            # Extremely long lines are not expected; fail rather than silently truncate.
            raise RuntimeError(f"single Telegram line exceeds safe limit: {_visible_len(line)}")
        current.append(line)
    flush()

    if not chunks:
        return []
    if len(chunks) == 1:
        return chunks

    rendered: list[str] = []
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        prefix = f"<b>대미투자 알림 {i}/{total}</b>\n" if i > 1 else ""
        rendered.append(prefix + chunk)
    return rendered


def resolve_mode() -> int:
    output = os.getenv("GITHUB_OUTPUT")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    try:
        username, chat = _resolve()
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("ready=true\n")
                f.write("reason=ok\n")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"Telegram 경로 확인: @{username}\n")
        print(f"telegram_route_valid=true bot=@{username} chat_type={chat.get('type', 'unknown')}")
        return 0
    except Exception as exc:
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("ready=false\n")
                f.write(f"reason={type(exc).__name__}\n")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"Telegram 경로 대기: {exc}\n")
        print(f"telegram_route_valid=false reason={exc}")
        return 0


def send_mode() -> int:
    if not ALERT.exists() or not ALERT.read_text(encoding="utf-8").strip():
        print("telegram_alert=none")
        return 0

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    username, chat = _resolve()
    text = ALERT.read_text(encoding="utf-8").strip()
    chunks = _split_html(text)
    message_ids: list[int] = []

    for chunk in chunks:
        payload = urllib.parse.urlencode({
            "chat_id": str(chat["id"]),
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        result = _api_json(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, timeout=30)
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected message: {result}")
        message_ids.append(int((result.get("result") or {}).get("message_id") or 0))

    DELIVERY.parent.mkdir(parents=True, exist_ok=True)
    DELIVERY.write_text(
        json.dumps({
            "bot": username,
            "message_ids": message_ids,
            "chat_type": chat.get("type"),
            "chunks": len(chunks),
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"telegram_delivery_confirmed=true bot=@{username} chunks={len(chunks)} message_ids={message_ids}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["resolve", "send"])
    args = parser.parse_args()
    return resolve_mode() if args.mode == "resolve" else send_mode()


if __name__ == "__main__":
    raise SystemExit(main())

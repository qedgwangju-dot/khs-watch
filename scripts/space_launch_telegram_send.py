#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_CHARS = 3400
MAX_BUTTONS_PER_MESSAGE = 8
SOURCE_PREFIX = "• 원문: "
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


class TelegramAPIError(RuntimeError):
    def __init__(self, message: str, *, error_code: int | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.retry_after = retry_after


def is_http_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def clean_paragraph(paragraph: str) -> tuple[str, list[str]]:
    """Remove long raw source URLs from message text and return them for buttons."""
    lines: list[str] = []
    urls: list[str] = []
    for line in paragraph.splitlines():
        if line.startswith(SOURCE_PREFIX):
            url = line[len(SOURCE_PREFIX):].strip()
            if is_http_url(url):
                urls.append(url)
                lines.append("• 원문: 아래 링크 버튼")
                continue
        lines.append(line)
    return "\n".join(lines), urls


def split_long_plain_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def build_messages(text: str) -> list[tuple[str, list[str]]]:
    """Pack plain-text paragraphs and their source buttons under Telegram limits."""
    messages: list[tuple[str, list[str]]] = []
    current_text = ""
    current_urls: list[str] = []

    def flush() -> None:
        nonlocal current_text, current_urls
        if current_text.strip():
            messages.append((current_text.strip(), current_urls[:]))
        current_text = ""
        current_urls = []

    for raw_paragraph in text.strip().split("\n\n"):
        paragraph, urls = clean_paragraph(raw_paragraph)
        parts = split_long_plain_text(paragraph)

        for index, part in enumerate(parts):
            part_urls = urls if index == 0 else []
            candidate = part if not current_text else current_text + "\n\n" + part
            too_long = len(candidate) > MAX_CHARS
            too_many_buttons = len(current_urls) + len(part_urls) > MAX_BUTTONS_PER_MESSAGE

            if (too_long or too_many_buttons) and current_text:
                flush()
                candidate = part

            if len(candidate) > MAX_CHARS:
                flush()
                for subpart in split_long_plain_text(part):
                    messages.append((subpart, part_urls if not messages or messages[-1][0] != subpart else []))
                continue

            current_text = candidate
            current_urls.extend(part_urls)

    flush()
    return messages


def inline_keyboard(urls: list[str]) -> dict | None:
    if not urls:
        return None
    rows = []
    for index, url in enumerate(urls[:MAX_BUTTONS_PER_MESSAGE], start=1):
        label = "🔗 원문 바로가기" if len(urls) == 1 else f"🔗 원문 {index}"
        rows.append([{"text": label, "url": url}])
    return {"inline_keyboard": rows}


def decode_api_error(raw: bytes, status: int | None = None) -> TelegramAPIError:
    error_code = status
    retry_after = None
    description = "Telegram API request failed"
    try:
        body = json.loads(raw.decode("utf-8", errors="replace"))
        error_code = int(body.get("error_code") or status or 0) or None
        description = str(body.get("description") or description)
        params = body.get("parameters") or {}
        if params.get("retry_after") is not None:
            retry_after = int(params["retry_after"])
    except Exception:
        pass
    return TelegramAPIError(description, error_code=error_code, retry_after=retry_after)


def telegram_call(
    token: str,
    method: str,
    payload: dict,
    *,
    attempts: int = 4,
) -> dict:
    """Call Bot API with bounded retry for rate limits and transient server/network failures."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read()
            result = json.loads(raw.decode("utf-8"))
            if result.get("ok"):
                return result
            exc = decode_api_error(raw)
            if exc.error_code in RETRYABLE_HTTP and attempt < attempts:
                delay = exc.retry_after or min(2 ** (attempt - 1), 8)
                time.sleep(max(1, min(delay, 15)))
                last_error = exc
                continue
            raise exc

        except urllib.error.HTTPError as exc:
            raw = exc.read()
            api_exc = decode_api_error(raw, exc.code)
            if api_exc.error_code in RETRYABLE_HTTP and attempt < attempts:
                delay = api_exc.retry_after or min(2 ** (attempt - 1), 8)
                time.sleep(max(1, min(delay, 15)))
                last_error = api_exc
                continue
            raise api_exc from exc

        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise TelegramAPIError(f"Telegram network failure after {attempts} attempts: {type(exc).__name__}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))

    raise TelegramAPIError(f"Telegram request failed: {last_error}")


def fallback_text_with_urls(text: str, urls: list[str]) -> str:
    if not urls:
        return text
    suffix = "\n".join(f"• 원문 {i}: {url}" for i, url in enumerate(urls, start=1))
    combined = f"{text}\n\n{suffix}"
    return combined[:4090]


def send_message(token: str, chat_id: str, text: str, urls: list[str]) -> int:
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    keyboard = inline_keyboard(urls)
    if keyboard:
        payload["reply_markup"] = keyboard

    try:
        result = telegram_call(token, "sendMessage", payload)
    except TelegramAPIError as exc:
        # Most formatting failures are eliminated by using plain text. If Telegram
        # still rejects the URL keyboard, preserve delivery by falling back to
        # plain auto-linked URLs with no reply_markup.
        if exc.error_code == 400 and urls:
            fallback_payload = {
                "chat_id": chat_id,
                "text": fallback_text_with_urls(text, urls),
                "disable_web_page_preview": True,
            }
            result = telegram_call(token, "sendMessage", fallback_payload)
        else:
            raise

    return int(result["result"]["message_id"])


def self_test() -> int:
    sample = (
        "🚀 테스트 <>&\n\n"
        "[계약] 예시\n"
        "• 핵심: plain text 특수문자 <tag> & 그대로 전송\n"
        "• 원문: https://example.com/a?x=1&y=2\n\n"
        "[개발] 예시2\n"
        "• 원문: https://example.org/b"
    )
    messages = build_messages(sample)
    assert messages
    body, urls = messages[0]
    assert "<tag> &" in body
    assert "https://example.com/a?x=1&y=2" not in body
    assert "https://example.com/a?x=1&y=2" in urls
    keyboard = inline_keyboard(urls)
    assert keyboard and keyboard["inline_keyboard"]
    payload = {"chat_id": "1", "text": body, "reply_markup": keyboard}
    assert "parse_mode" not in payload
    print("telegram_sender_self_test=ok mode=plain_text+inline_keyboard fallback=plain_url")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()

    if len(sys.argv) != 2:
        print("usage: space_launch_telegram_send.py REPORT_PATH | --self-test", file=sys.stderr)
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

    identity = telegram_call(token, "getMe", {})
    actual = str((identity.get("result") or {}).get("username") or "")
    if actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")

    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("Telegram report is empty")

    messages = build_messages(text)
    if not messages:
        raise RuntimeError("Telegram report produced no sendable messages")

    message_ids: list[int] = []
    for plain_text, urls in messages:
        message_ids.append(send_message(token, chat_id, plain_text, urls))

    print(
        "telegram_delivery_confirmed=true "
        f"bot=@{actual} mode=plain_text+inline_keyboard message_ids={message_ids}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

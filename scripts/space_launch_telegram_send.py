#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_CHARS = 3400  # Keep text below Telegram's 4096-unit limit
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



# Optional compact in-message source links. Default send path above is unchanged;
# only the Starlink Mobile workflow explicitly invokes --inline.
INLINE_SOURCE_RE = re.compile(r"^• 원문:\s*(https://\S+)\s*$")
INLINE_MAX_UNITS = 3450
INLINE_LABELS = "①②③④⑤⑥⑦⑧⑨⑩"


def utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def inline_combine(a: tuple[str, list[dict]], b: tuple[str, list[dict]], glue: str):
    prefix = utf16_units(a[0] + glue)
    return (
        a[0] + glue + b[0],
        a[1] + [dict(ent, offset=ent["offset"] + prefix) for ent in b[1]],
    )


def inline_url(value: str) -> str:
    from urllib.parse import urlsplit
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("Expected a valid HTTPS source link without credentials")
    if len(value) > 3000 or any(ord(ch) < 32 for ch in value):
        raise ValueError("Source link contains invalid characters or is too long")
    return value


def inline_link_row(urls: list[str]) -> tuple[str, list[dict]]:
    if not urls:
        return "", []
    if len(urls) > len(INLINE_LABELS):
        raise ValueError("Too many source links in one section")
    labels = [
        "원문" if len(urls) == 1 else f"원문{INLINE_LABELS[i]}"
        for i in range(len(urls))
    ]
    result = " · ".join(labels)
    entities = []
    pos = 0
    for i, (label, url) in enumerate(zip(labels, urls)):
        if i:
            pos += utf16_units(" · ")
        entities.append({
            "type": "text_link", "offset": pos, "length": utf16_units(label),
            "url": inline_url(url),
        })
        pos += utf16_units(label)
    return result, entities


def inline_paragraph(paragraph: str) -> tuple[str, list[dict]]:
    current = ("", [])
    pending_urls = []

    def flush(current):
        nonlocal pending_urls
        if not pending_urls:
            return current
        segment = inline_link_row(pending_urls)
        pending_urls = []
        return inline_combine(current, segment, "\n" if current[0] else "")

    for line in paragraph.splitlines():
        m = INLINE_SOURCE_RE.fullmatch(line.strip())
        if m:
            pending_urls.append(inline_url(m.group(1)))
            continue
        if line.strip() == "• 원문: 아래 링크 버튼":
            raise ValueError("Found old button placeholder instead of source")
        current = flush(current)
        current = inline_combine(current, (line, []), "\n" if current[0] else "")
    return flush(current)


def inline_cut_plain_line(value: str):
    chunks = []
    chunk = ""
    for ch in value:
        if utf16_units(chunk + ch) > INLINE_MAX_UNITS:
            chunks.append((chunk, []))
            chunk = ""
        chunk += ch
    if chunk:
        chunks.append((chunk, []))
    return chunks


def inline_split_big_block(block: tuple[str, list[dict]]):
    if utf16_units(block[0]) <= INLINE_MAX_UNITS:
        return [block]
    # Compute link offsets relative to each line before splitting. This preserves
    # all links and text in messages that exceed one Telegram message.
    result = []
    unit_offset = 0
    current = ("", [])
    for line in block[0].split("\n"):
        line_len = utf16_units(line)
        line_entities = [
            dict(ent, offset=ent["offset"] - unit_offset)
            for ent in block[1]
            if unit_offset <= ent["offset"] and
            ent["offset"] + ent["length"] <= unit_offset + line_len
        ]
        if line_len > INLINE_MAX_UNITS:
            if line_entities:
                raise ValueError("Oversize source-link line cannot be split")
            if current[0]:
                result.append(current)
                current = ("", [])
            result.extend(inline_cut_plain_line(line))
        else:
            seg = (line, line_entities)
            glue = "\n" if current[0] else ""
            candidate = inline_combine(current, seg, glue)
            if current[0] and utf16_units(candidate[0]) > INLINE_MAX_UNITS:
                result.append(current)
                current = seg
            else:
                current = candidate
        unit_offset += line_len + 1
    if current[0]:
        result.append(current)
    return result


def inline_messages(original: str):
    if not original.strip():
        raise ValueError("Empty alert")
    blocks = []
    for paragraph in original.strip().split("\n\n"):
        blocks.extend(inline_split_big_block(inline_paragraph(paragraph)))
    result = []
    current = ("", [])
    for block in blocks:
        glue = "\n\n" if current[0] else ""
        candidate = inline_combine(current, block, glue)
        if current[0] and utf16_units(candidate[0]) > INLINE_MAX_UNITS:
            result.append(current)
            current = block
        else:
            current = candidate
    if current[0]:
        result.append(current)

    original_urls = []
    for line in original.splitlines():
        m = INLINE_SOURCE_RE.fullmatch(line.strip())
        if m:
            original_urls.append(m.group(1))
    rendered_urls = [
        ent["url"] for txt, ents in result for ent in ents
    ]
    if rendered_urls != original_urls:
        raise AssertionError("Source link missing, duplicated or out of order")
    for text, ents in result:
        if utf16_units(text) > INLINE_MAX_UNITS:
            raise AssertionError("Telegram text length exceeds safe limit")
        encoded = text.encode("utf-16-le")
        for ent in ents:
            span = encoded[ent["offset"] * 2:
                           (ent["offset"] + ent["length"]) * 2].decode("utf-16-le")
            if not span.startswith("원문"):
                raise AssertionError("Bad Telegram UTF-16 hyperlink position")
        if "아래 링크 버튼" in text:
            raise AssertionError("Legacy button prompt survived")
    # The only removable lines are raw source URLs. The rest of the event must
    # remain present in the rendered Telegram output.
    all_text = "\n".join(item[0] for item in result)
    for line in original.splitlines():
        if line and not INLINE_SOURCE_RE.fullmatch(line.strip()):
            if line not in all_text and utf16_units(line) <= INLINE_MAX_UNITS:
                raise AssertionError("A source report line was dropped")
    return result


def inline_self_test() -> int:
    sample = (
        "📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시\n"
        "기준: 2026-10-09 17:55 KST\n\n"
        "[중요 정정] D2D 위성 1만5,000기\n"
        "• 위성 1만5,000기, 궤도 326~335km. 📡 문자 유지.\n"
        "• 원문: https://docs.fcc.gov/public/attachments/DA-26-1078A1.pdf\n"
        "• 원문: https://docs.fcc.gov/public/attachments/DA-26-36A1.pdf\n"
        "• 원문: https://graingp.com/announcements/spacex-800-mhz/"
    )
    texts = inline_messages(sample)
    assert len(texts) == 1
    assert "원문① · 원문② · 원문③" in texts[0][0]
    assert len(texts[0][1]) == 3
    assert all(e["type"] == "text_link" for e in texts[0][1])
    assert not any("reply_markup" in item[0] for item in texts)
    long_texts = inline_messages(
        "📡 장문 전송 검증\n\n" + ("• 실제 내용 손실 방지. " * 500)
        + "\n• 원문: https://example.com/confirmed"
    )
    assert len(long_texts) > 1
    assert sum(len(ents) for _, ents in long_texts) == 1
    assert inline_messages("이모지 📡\n• 원문: https://example.com/")[0][0].endswith("원문")
    print("starlink_d2d_inline_self_test=ok inline_links=3 utf16=ok long_text=ok no_buttons=ok")
    return 0


def send_inline_alert(token: str, chat_id: str, message: str):
    ids = []
    for plain_text, entities in inline_messages(message):
        response = telegram_call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": plain_text,
            "entities": entities,
            "disable_web_page_preview": True,
        })
        delivered = response.get("result") or {}
        returned_urls = [
            e.get("url") for e in delivered.get("entities", [])
            if e.get("type") == "text_link"
        ]
        if returned_urls != [e["url"] for e in entities]:
            raise RuntimeError("Telegram did not confirm clickable text links")
        if delivered.get("text") != plain_text:
            raise RuntimeError("Telegram returned modified alert text")
        ids.append(int(delivered["message_id"]))
    return ids

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

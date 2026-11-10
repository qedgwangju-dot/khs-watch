#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import unicodedata
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
INLINE_MAX_UNITS = 3500  # Existing inline sender remains unchanged.
READABLE_MAX_UNITS = 1000  # Short phone-friendly complete messages.
READABLE_BODY_UNITS = 740  # Leave room for report header, title, and [part/total].
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


def inline_source_name(url: str, number: int) -> str:
    """Clear and short source name, tied to the URL's issuer and purpose."""
    from urllib.parse import urlsplit
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    path = p.path.lower()
    if "investing.com" in host and "at-t-historical" in path:
        return "AT&T 주가"
    if "investing.com" in host and "verizon-communications" in path:
        return "VZ 주가"
    if "stockanalysis.com" in host and "/stocks/tmus/" in path:
        return "TMUS 주가"
    if "about.att.com" in host and "dividend" in path:
        return "AT&T 배당"
    if "verizon.com" in host and "dividend" in path:
        return "VZ 배당"
    if "nasa.gov" in host and "jsc-procurement" in path:
        return "NASA 조달"
    if "nasa.gov" in host and "news-release" in path:
        return "NASA 발표"
    if "nasa.gov" in host:
        return "NASA"
    if "fireflyspace.com" in host:
        return "파이어플라이"
    if "voyagertechnologies.com" in host:
        return "보이저"
    if "elonmuskarchive.org" in host:
        return "머스크 발언"
    if host in {"x.com", "twitter.com"}:
        return "X 원문"
    if "spacex.com" in host and "fairing" in path:
        return "Falcon 9"
    if "starlink.com" in host:
        return "Starlink"
    if "docs.fcc.gov" in host and "da-26-1078" in path:
        return "FCC 10월"
    if "docs.fcc.gov" in host and "da-26-36" in path:
        return "FCC 1월"
    if "fcc.gov" in host:
        return "FCC"
    if "graingp.com" in host:
        return "Grain"
    if "rocketlabcorp.com" in host:
        return "Rocket Lab 공식"
    if "news.google.com" in host:
        return "Google 뉴스 색인"
    if "reuters.com" in host:
        return "Reuters"
    return f"원문{INLINE_LABELS[number]}"


def inline_display_width(text: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in text
    )


def inline_link_row(urls: list[str]) -> tuple[str, list[dict]]:
    """Inline, named text links; Telegram itself decides where lines wrap.

    No invented 44-column phone width or per-source buttons. Entity offsets
    count UTF-16 units so Korean text and emoji cannot misalign the links.
    """
    if not urls:
        return "", []
    if len(urls) > len(INLINE_LABELS):
        raise ValueError("Too many source links in one section")
    result = "원문: "
    entities = []
    for index, url in enumerate(urls):
        validated = inline_url(url)
        label = inline_source_name(validated, index)
        separator = "" if index == 0 else " · "
        pos = utf16_units(result + separator)
        result += separator + label
        entities.append({
            "type": "text_link",
            "offset": pos,
            "length": utf16_units(label),
            "url": validated,
        })
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


def inline_cut_plain_line(value: str, limit: int = INLINE_MAX_UNITS):
    chunks = []
    chunk = ""
    for ch in value:
        if utf16_units(chunk + ch) > limit:
            chunks.append((chunk, []))
            chunk = ""
        chunk += ch
    if chunk:
        chunks.append((chunk, []))
    return chunks


def inline_split_big_block(block: tuple[str, list[dict]], limit: int = INLINE_MAX_UNITS):
    if utf16_units(block[0]) <= limit:
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
        if line_len > limit:
            if line_entities:
                raise ValueError("Oversize source-link line cannot be split")
            if current[0]:
                result.append(current)
                current = ("", [])
            result.extend(inline_cut_plain_line(line, limit))
        else:
            seg = (line, line_entities)
            glue = "\n" if current[0] else ""
            candidate = inline_combine(current, seg, glue)
            if current[0] and utf16_units(candidate[0]) > limit:
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
            expected_labels = {
                inline_source_name(ent["url"], index)
                for index in range(len(INLINE_LABELS))
            }
            if span not in expected_labels:
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


def readable_messages(original: str) -> list[tuple[str, list[dict]]]:
    """One event at a time in short, numbered Telegram chat messages.

    The raw report is never shortened. Source URLs become clickable labels,
    original numbers are preserved, and legacy --inline is not modified.
    """
    if not original.strip():
        raise ValueError("Empty readable Telegram report")
    paragraphs = [p.strip() for p in original.strip().split("\n\n") if p.strip()]
    header = paragraphs[0] if len(paragraphs) > 1 else ""
    sections = paragraphs[1:] if header else paragraphs
    all_parts: list[tuple[str, list[dict]]] = []
    original_urls: list[str] = []

    for section in sections:
        title = section.splitlines()[0].strip()
        # Both the alert header and section title are repeated on continuation
        # parts; reserve their full width before deciding where to split.
        reserved = utf16_units(header + "\n\n" + title + " (계속)\n") + 30
        budget = min(READABLE_BODY_UNITS, READABLE_MAX_UNITS - reserved)
        if budget < 160:
            raise ValueError("Event heading too long for readable Telegram budget")
        block = inline_paragraph(section)
        pieces = inline_split_big_block(block, limit=budget)
        if re.sub(r"\s+", "", "".join(part[0] for part in pieces)) != re.sub(
            r"\s+", "", block[0]
        ):
            raise AssertionError("Readable layout changed substantive event text")
        for part_index, part in enumerate(pieces):
            preface = header + "\n\n" if header else ""
            if part_index:
                # A reader can identify the event even when part 2 arrives
                # after messages from another, independent scheduled watcher.
                preface += title + " (계속)\n"
            all_parts.append(inline_combine((preface, []), part, ""))
        original_urls.extend(
            match.group(1) for line in section.splitlines()
            if (match := INLINE_SOURCE_RE.fullmatch(line.strip()))
        )

    if not all_parts:
        raise ValueError("Readable Telegram report generated no parts")
    total = len(all_parts)
    result: list[tuple[str, list[dict]]] = []
    for index, part in enumerate(all_parts, start=1):
        lead = f"[{index}/{total}] " if total > 1 else ""
        text, entities = inline_combine((lead, []), part, "")
        if utf16_units(text) > READABLE_MAX_UNITS:
            raise AssertionError("Readable Telegram part exceeded 1000 UTF-16 units")
        # Bold alert and event headings; source hyperlinks remain separate
        # text_link entities with correct UTF-16 offsets.
        offset_chars = 0
        for line in text.splitlines(keepends=True):
            label = line.rstrip("\r\n")
            if label and (label.startswith(("📡", "🚀", "["))):
                entities.append({
                    "type": "bold",
                    "offset": utf16_units(text[:offset_chars]),
                    "length": utf16_units(label),
                })
            offset_chars += len(line)
        result.append((text, sorted(entities, key=lambda ent: ent["offset"])))

    linked = [entity["url"] for _, entities in result
              for entity in entities if entity["type"] == "text_link"]
    if linked != original_urls:
        raise AssertionError("Source link lost, duplicated or reordered in readable layout")
    for text, entities in result:
        raw = text.encode("utf-16-le")
        for entity in entities:
            segment = raw[entity["offset"] * 2:
                          (entity["offset"] + entity["length"]) * 2].decode("utf-16-le")
            if not segment or entity["offset"] < 0:
                raise AssertionError("Invalid Telegram entity offset or length")
        if "아래 링크 버튼" in text:
            raise AssertionError("Legacy source placeholder in readable message")
    return result


def readable_self_test() -> int:
    sample = (
        "🚀 우주 발사 병목 웹감시\n기준: 2026-11-10 10:16 KST\n\n"
        "[NASA 공식] CLPS 2 신규 경쟁자격\n"
        "• 총 계약 한도 100억달러, 8개 기업, 2036년까지. "
        "확정 수주와 참여자격을 구분합니다.\n"
        "• 원문: https://www.nasa.gov/news-release/example\n"
        "• 원문: https://www.nasa.gov/johnson/jsc-procurement/clps2/\n\n"
        "[설계 구상] Starlink V4 광통신\n"
        "• 위성당 레이저 10개 또는 100개, 10Tbps, 위성 100,000기는 "
        "계획이며 실제 운영 용량은 아닙니다. 📡\n"
        "• 원문: https://elonmuskarchive.org/posts/example\n\n"
        "[장문 시험] 전수 보존 확인\n"
        + ("• 15,000기, 2028년 목표, 확정 매출 아님. 설명 계속.\n" * 60)
        + "• 원문: https://example.com/final"
    )
    chunks = readable_messages(sample)
    assert len(chunks) >= 5
    assert all(utf16_units(text) <= READABLE_MAX_UNITS for text, _ in chunks)
    assert all("🚀 우주 발사 병목 웹감시" in text for text, _ in chunks)
    assert all(("[{}/{}] ".format(i, len(chunks)) in text) for i, (text, _) in enumerate(chunks, 1))
    urls = [e["url"] for _, entities in chunks for e in entities if e["type"] == "text_link"]
    assert urls == [
        "https://www.nasa.gov/news-release/example",
        "https://www.nasa.gov/johnson/jsc-procurement/clps2/",
        "https://elonmuskarchive.org/posts/example",
        "https://example.com/final",
    ]
    rendered = "\n".join(text for text, _ in chunks)
    assert "100억달러" in rendered and "2036년" in rendered
    assert "10Tbps" in rendered and "100,000기" in rendered
    assert sum(text.count("15,000기") for text, _ in chunks) == 60
    assert sum(ent["type"] == "bold" for _, entities in chunks for ent in entities) >= 4
    assert sum(ent["type"] == "text_link" for _, entities in chunks for ent in entities) == 4
    short = readable_messages(
        "📡 Starlink Mobile 감시\n기준: 2026-11-10\n\n"
        "[공급계약] 퀄컴 공급계약\n"
        "• 실제 설치 수 미공개, 8만 곳 부지 협상과 구분.\n"
        "• 원문: https://example.org/release"
    )
    assert len(short) == 1
    assert "8만 곳" in short[0][0]
    # Simulate Telegram's actual response shape. Readability introduces
    # bold entities without URLs; only text_link entities have URL fields.
    real_call = telegram_call
    received_payloads = []
    def fake_telegram_call(token, method, payload, **kwargs):
        assert token == "local-only" and method == "sendMessage"
        received_payloads.append(payload)
        return {"ok": True, "result": {
            "message_id": 1000 + len(received_payloads),
            "text": payload["text"],
            "entities": payload["entities"],
            "chat": {"id": -12345},
        }}
    try:
        globals()["telegram_call"] = fake_telegram_call
        ids = send_inline_alert("local-only", "-12345", sample, readable=True)
        assert len(ids) == len(chunks)
        assert len(received_payloads) == len(chunks)
        for index, payload in enumerate(received_payloads, 1):
            assert payload["text"].startswith(f"[{index}/{len(chunks)}] ")
            assert payload["text"].count(f"[{index}/{len(chunks)}] ") == 1
            assert any(ent["type"] == "bold" for ent in payload["entities"])
            assert all(ent.get("type") != "text_link" or ent.get("url")
                       for ent in payload["entities"])
    finally:
        globals()["telegram_call"] = real_call
    print("telegram_readable_self_test=ok phone_budget=1000 source_links=4 "
          "all_numbers=1 per_event=1 ordered_parts=1 bold_headings=1")
    return 0


def inline_self_test() -> int:
    sample = (
        "📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시\n"
        "기준: 2026-10-11 17:39 KST\n\n"
        "[중요 정정] D2D 위성 1만5,000기\n"
        "• 위성 1만5,000기, 궤도 326~335km. 📡 문자 유지.\n"
        "• 원문: https://docs.fcc.gov/public/attachments/DA-26-1078A1.pdf\n"
        "• 원문: https://docs.fcc.gov/public/attachments/DA-26-36A1.pdf\n"
        "• 원문: https://graingp.com/announcements/spacex-800-mhz/"
    )
    messages = inline_messages(sample)
    assert len(messages) == 1, "Ordinary alerts must not split into tiny messages"
    text, ents = messages[0]
    assert "원문: FCC 10월 · FCC 1월 · Grain" in text
    assert len(ents) == 3 and all(e["type"] == "text_link" for e in ents)
    assert "\n      " not in text, "No hardcoded mobile-width indentation"
    assert inline_messages("이모지 📡\n• 원문: https://example.com/")[0][0].endswith("원문①")
    assert "AT&T 주가" == inline_source_name(
        "https://www.investing.com/equities/at-t-historical-data", 0)
    assert "VZ 배당" == inline_source_name(
        "https://www.verizon.com/about/investors/dividend-history", 0)

    # End-to-end 8-source real alert regression: all verified numbers and
    # hyperlinks must remain, yet it should fit a single Telegram message.
    from starlink_mobile_d2d_watch import price_dividend_display_correction
    from starlink_mobile_d2d_readability import format_mobile
    source = "📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시\n기준: 표시검증\n\n"
    full = format_mobile(source + price_dividend_display_correction())
    packed = inline_messages(full)
    assert len(packed) == 1, "Oct 11 factual alert should fit ONE message"
    urls = [entry["url"] for _, all_entries in packed for entry in all_entries]
    assert len(urls) == len(set(urls)) == 8
    combined = "\n".join(x for x, _ in packed)
    assert "22.18달러" in combined and "-10.82%" in combined
    assert "-9.81%" in combined and "41.65달러" in combined
    assert "-10.14%" in combined and "-8.75%" in combined
    assert "148.58달러" in combined and "-13.27%" in combined
    assert "0.2775달러" in combined and "0.7075달러" in combined
    assert "9억4,600만 달러" in combined and "1조2,685억원" in combined
    assert "2030년" in combined and "Falcon 9·Dragon" in combined
    assert "FCC 이전 승인" in combined and "Starship" in combined
    assert "Raptor" in combined and "원문: " in combined
    assert utf16_units(combined) < INLINE_MAX_UNITS

    # If a genuinely long report exceeds capacity, it is still losslessly split.
    overlong = "📡 장문 검증\n\n" + ("• 핵심 숫자 15,000기 · 설명 확인. " * 450)
    parts = inline_messages(overlong + "\n• 원문: https://example.com/confirmed")
    assert len(parts) > 1
    assert sum(len(es) for _, es in parts) == 1
    assert all(utf16_units(t) <= INLINE_MAX_UNITS for t, _ in parts)
    assert receipt_matches_destination({"chat":{"id":-10001234,"username":"example"}},"-10001234")
    assert receipt_matches_destination({"chat":{"id":-10001234,"username":"example"}},"@Example")
    assert not receipt_matches_destination({"chat":{"id":-10009999,"username":"wrong"}},"-10001234")
    assert not receipt_matches_destination({"chat":{"id":-10001234}},"@Example")
    print("starlink_d2d_inline_self_test=ok one_message_8_sources=1 natural_wrap=1 utf16=ok long_split=ok")
    return 0


def receipt_matches_destination(delivered: dict, expected: str) -> bool:
    """Validate Telegram's returned chat without exposing private identifiers."""
    chat=delivered.get("chat") or {}
    if expected.lstrip("-").isdigit():
        return str(chat.get("id") or "") == expected
    if expected.startswith("@"):
        return str(chat.get("username") or "").casefold() == expected[1:].casefold()
    return False


def send_inline_alert(token: str, chat_id: str, message: str, *, readable: bool = False):
    ids = []
    portions = readable_messages(message) if readable else inline_messages(message)
    for index, (plain_text, entities) in enumerate(portions, start=1):
        if len(portions) > 1 and not readable:
            # This makes the complete series identifiable on a small screen.
            prefix = f"[{index}/{len(portions)}] "
            plain_text, entities = inline_combine(
                (prefix, []), (plain_text, entities), ""
            )
        response = telegram_call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": plain_text,
            "entities": entities,
            "disable_web_page_preview": True,
        })
        delivered = response.get("result") or {}
        # Record accepted Telegram message IDs *before* subsequent receipt
        # checks, so partial deliveries can be reconstructed from job logs.
        if readable and delivered.get("message_id") is not None:
            print(f"telegram_api_accepted_part={index}/{len(portions)} "
                  f"message_id={delivered['message_id']}", flush=True)
        returned_urls = [
            e.get("url") for e in delivered.get("entities", [])
            if e.get("type") == "text_link"
        ]
        expected_urls = [e["url"] for e in entities if e.get("type") == "text_link"]
        if returned_urls != expected_urls:
            raise RuntimeError("Telegram did not confirm clickable text links")
        if delivered.get("text") != plain_text:
            raise RuntimeError("Telegram returned modified alert text")
        if os.getenv("SPACE_LAUNCH_VERIFY_RECEIPT") == "1":
            if not receipt_matches_destination(delivered, chat_id):
                raise RuntimeError("Telegram response did not confirm the configured recipient")
        ids.append(int(delivered["message_id"]))
        if readable:
            print(f"telegram_readable_part_receipt={index}/{len(portions)} message_id={ids[-1]}")
    return ids

def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()
    if len(sys.argv) == 2 and sys.argv[1] == "--inline-self-test":
        return inline_self_test()
    if len(sys.argv) == 2 and sys.argv[1] == "--readable-self-test":
        return readable_self_test()

    inline_mode = len(sys.argv) == 3 and sys.argv[1] == "--inline"
    readable_mode = len(sys.argv) == 3 and sys.argv[1] == "--readable"
    inline_live = len(sys.argv) == 2 and sys.argv[1] == "--inline-live-test"
    if len(sys.argv) != 2 and not (inline_mode or readable_mode):
        print("usage: space_launch_telegram_send.py REPORT_PATH | --inline REPORT_PATH | --readable REPORT_PATH | --self-test | --inline-self-test | --readable-self-test | --inline-live-test", file=sys.stderr)
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

    if inline_live:
        text = "\n".join((
            "📡 Starlink Mobile 원문 링크 표시 시험",
            "• 버튼 없이 원문 3개를 본문 한 줄의 클릭 가능한 글자로 표시합니다.",
            "• 원문: https://docs.fcc.gov/public/attachments/DA-26-1078A1.pdf",
            "• 원문: https://docs.fcc.gov/public/attachments/DA-26-36A1.pdf",
            "• 원문: https://graingp.com/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex/",
        ))
    else:
        path = pathlib.Path(sys.argv[2] if (inline_mode or readable_mode) else sys.argv[1])
        text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("Telegram report is empty")

    if inline_mode or inline_live or readable_mode:
        ids = send_inline_alert(token, chat_id, text, readable=readable_mode)
        if os.getenv("SPACE_LAUNCH_VERIFY_RECEIPT") == "1":
            print("telegram_recipient_receipt_verified=true")
        print(f"telegram_inline_links_delivered=true bot=@{actual} message_ids={ids} "
              f"inline=true readable={readable_mode} parts={len(ids)}")
        return 0

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

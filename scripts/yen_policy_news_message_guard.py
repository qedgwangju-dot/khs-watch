#!/usr/bin/env python3
"""Safe, non-truncating Telegram HTML message partition for yen-policy alerts."""
from __future__ import annotations

import re

MAX_MESSAGE_LEN = 3900  # reserve room for Telegram UTF-16 length/count differences


def split_html_message(title: str, body: str, *, max_length: int = MAX_MESSAGE_LEN) -> list[str]:
    if not title.strip() or not body.strip() or max_length < 200:
        raise ValueError("제목·본문 또는 허용 길이가 올바르지 않습니다.")
    prefix = title.strip() + "\n\n"
    continuation = title.strip() + " (계속)\n\n"
    if len(prefix) >= max_length or len(continuation) >= max_length:
        raise ValueError("텔레그램 경보 제목이 지나치게 깁니다.")
    lines = body.strip().splitlines(keepends=True)
    chunks: list[str] = []
    current = prefix

    for line in lines:
        # Inline links are generated on one line. Never cut inside <a> or <b> tags.
        for tag in ("a", "b", "i"):
            opens = len(re.findall(rf"<{tag}(?:\s|>)", line))
            closes = line.count(f"</{tag}>")
            if opens != closes:
                raise ValueError(f"안전하지 않은 텔레그램 HTML 줄 경계: {tag}")
        if len(line) + len(continuation) > max_length:
            raise ValueError("단일 줄이 텔레그램 안전 길이를 초과합니다. 원문 링크/본문을 점검해야 합니다.")
        if len(current) + len(line) > max_length:
            if current == prefix:
                raise ValueError("첫 메시지에 수용할 수 없는 긴 줄입니다.")
            chunks.append(current.rstrip())
            current = continuation
        current += line

    if current.strip() and current not in (prefix, continuation):
        chunks.append(current.rstrip())
    if not chunks:
        raise ValueError("텔레그램 메시지가 비어 있습니다.")
    if any(len(c) > max_length for c in chunks):
        raise ValueError("메시지 길이 검증 오류")
    return chunks

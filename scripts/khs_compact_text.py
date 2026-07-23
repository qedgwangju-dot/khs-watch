#!/usr/bin/env python3
"""Shared compact prose helpers for Telegram alerts."""

from __future__ import annotations

import re

MAX_PROSE_CHARS = 50
COMPACT_PROSE_PREFIXES = (
    "- 핵심:",
    "- 핵심 내용:",
    "- 핵심 근거:",
    "- 확인 근거:",
    "- 투자 관점:",
    "- 투자 영향:",
    "- 투자 포인트:",
    "- 한국장:",
    "- 한국장 영향:",
    "- 실패 신호:",
)
COMBINED_PROSE_PREFIX = "- 반영/반대:"


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _complete_sentence(text: str, limit: int) -> str:
    for match in re.finditer(r".+?[.!?](?:[\"'”’)]*)(?=\s|$)", text):
        sentence = normalize_text(match.group(0))
        if 8 <= len(sentence) <= limit:
            return sentence
    return ""


def _bounded_excerpt(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"[:limit]

    room = limit - 1
    head = text[:room].rstrip()
    minimum_boundary = max(8, int(room * 0.55))
    boundary = max(
        head.rfind(" "),
        head.rfind(","),
        head.rfind("·"),
        head.rfind("/"),
        head.rfind("|"),
        head.rfind(";"),
        head.rfind(":"),
    )
    if boundary >= minimum_boundary:
        head = head[:boundary].rstrip(" ,·/|;:")
    return head.rstrip() + "…"


def concise_text(
    value: object,
    *,
    fallback: object = "",
    limit: int = MAX_PROSE_CHARS,
    prefer_fallback_when_long: bool = False,
) -> str:
    """Return source-faithful prose that fits the visible Telegram limit."""

    text = normalize_text(value)
    fallback_text = normalize_text(fallback)
    if not text:
        text = fallback_text or "확인 불가"
    if len(text) <= limit:
        return text

    if prefer_fallback_when_long and fallback_text and fallback_text != text:
        if len(fallback_text) <= limit:
            return fallback_text
        sentence = _complete_sentence(fallback_text, limit)
        if sentence:
            return sentence
        return _bounded_excerpt(fallback_text, limit)

    sentence = _complete_sentence(text, limit)
    if sentence:
        return sentence

    if fallback_text and fallback_text != text:
        if len(fallback_text) <= limit:
            return fallback_text
        sentence = _complete_sentence(fallback_text, limit)
        if sentence:
            return sentence
        return _bounded_excerpt(fallback_text, limit)

    return _bounded_excerpt(text, limit)


def compact_prose_lines(
    body: str,
    *,
    limit: int = MAX_PROSE_CHARS,
) -> tuple[str, int]:
    """Rewrite long Telegram prose fields instead of rejecting the alert."""

    rewritten: list[str] = []
    changed_fields = 0
    for raw_line in str(body or "").splitlines():
        stripped = raw_line.strip()
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        compacted_line = raw_line

        for prefix in COMPACT_PROSE_PREFIXES:
            if not stripped.startswith(prefix):
                continue
            value = normalize_text(stripped.removeprefix(prefix))
            compacted = concise_text(value, limit=limit)
            compacted_line = f"{indent}{prefix} {compacted}"
            if compacted != value:
                changed_fields += 1
            break
        else:
            if stripped.startswith(COMBINED_PROSE_PREFIX):
                value = normalize_text(stripped.removeprefix(COMBINED_PROSE_PREFIX))
                parts = value.split(" / ", 1)
                compacted_parts = [
                    concise_text(part, limit=limit)
                    for part in parts
                ]
                compacted_line = (
                    f"{indent}{COMBINED_PROSE_PREFIX} "
                    + " / ".join(compacted_parts)
                )
                changed_fields += sum(
                    compacted != normalize_text(original)
                    for compacted, original in zip(compacted_parts, parts)
                )

        rewritten.append(compacted_line)

    suffix = "\n" if str(body or "").endswith("\n") else ""
    return "\n".join(rewritten) + suffix, changed_fields

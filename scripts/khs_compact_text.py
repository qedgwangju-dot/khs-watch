#!/usr/bin/env python3
"""Shared compact prose helpers for Telegram alerts."""

from __future__ import annotations

import re

MAX_PROSE_CHARS = 50


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

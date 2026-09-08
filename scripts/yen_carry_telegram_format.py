#!/usr/bin/env python3
"""Telegram HTML readability formatter for yen-carry alerts.

The alert calculation and source text remain unchanged. This module only applies
safe Telegram HTML at send time so important FX-shock values are visually easier
to scan without breaking sector enrichment or GitHub markdown artifacts.
Long alerts are split by line/paragraph instead of being silently truncated.
"""
from __future__ import annotations

import html
import re

# Telegram sendMessage allows 1-4096 characters after entity parsing. Keep margin
# for formatting and future changes while preserving every source line.
TELEGRAM_SAFE_TEXT_LIMIT = 3900

_SECTION_EXACT = {
    "빠른 급락 감지",
    "산업·업종 영향",
}
_SECTION_PREFIXES = (
    "지속 하락 감지",
    "60분 단순 비교",
)
_FULL_BOLD_PREFIXES = (
    "현재 상태:",
    "USD/JPY 현재가:",
    "최종 판정:",
    "빠른 급락 단계:",
    "종합 판정:",
)
_LABEL_PREFIXES = (
    "조회 시각:",
    "시장 데이터 시각:",
    "방향 읽는 법:",
    "알림 사유:",
    "감지 경로:",
    "같은 단계 재알림 최소 간격:",
    "확인 시각:",
    "원 경보:",
    "기준:",
)
_SECTOR_VERDICTS = (
    "예상 방향 확인",
    "예상과 반대",
    "유의한 상대변동 미확인",
    "환율 직접 영향 판단 보류",
)


def _bold(text: str) -> str:
    return f"<b>{html.escape(text)}</b>"


def _format_label_line(line: str) -> str:
    label, value = line.split(":", 1)
    return f"{_bold(label + ':')}{html.escape(value)}"


def _format_window_line(line: str) -> str:
    escaped = html.escape(line)
    escaped = re.sub(
        r"^(15분|30분|60분 참고)(\([^)]*\)):",
        r"<b>\1\2</b>:",
        escaped,
    )
    escaped = re.sub(r"([+-]\d+(?:\.\d+)?%)", r"<b>\1</b>", escaped)
    escaped = escaped.replace("충족 ← 경보 원인", "<b>충족 ← 경보 원인</b>")
    return escaped


def _format_sector_line(line: str) -> str:
    match = re.match(r"^• ([^:]+):(.*)$", line)
    if not match:
        return html.escape(line)
    name, rest = match.groups()
    rendered = f"• {_bold(name)}:{html.escape(rest)}"
    rendered = re.sub(
        r"(상대 [+-]\d+(?:\.\d+)?%p)",
        r"<b>\1</b>",
        rendered,
    )
    for verdict in _SECTOR_VERDICTS:
        rendered = rendered.replace(verdict, f"<b>{verdict}</b>")
    return rendered


def _format_fx_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    if stripped in _SECTION_EXACT or stripped.startswith(_SECTION_PREFIXES):
        return _bold(line)
    if line.startswith(_FULL_BOLD_PREFIXES) or line.startswith("가변 구간("):
        return _bold(line)
    if line.startswith(_LABEL_PREFIXES):
        return _format_label_line(line)
    if line.startswith(("15분(", "30분(", "60분 참고(")):
        return _format_window_line(line)
    if line.startswith("• "):
        return _format_sector_line(line)
    if line.startswith("주의:"):
        return f"{_bold('주의:')}{html.escape(line[len('주의:'):])}"
    return html.escape(line)


def _split_long_line(line: str, limit: int) -> list[str]:
    if len(line) <= limit:
        return [line]
    return [line[index : index + limit] for index in range(0, len(line), limit)]


def split_plain_message(title: str, body: str, limit: int = TELEGRAM_SAFE_TEXT_LIMIT) -> list[str]:
    """Split without dropping text; prefer existing line boundaries."""
    if limit < 100:
        raise ValueError("Telegram chunk limit is unreasonably small")

    plain = f"{title.strip()}\n\n{body.strip()}"
    source_lines: list[str] = []
    for line in plain.splitlines():
        source_lines.extend(_split_long_line(line, limit))

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in source_lines:
        added = len(line) + (1 if current else 0)
        if current and current_len + added > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += added
    if current:
        chunks.append("\n".join(current))
    return chunks or [""]


def _render_chunk(chunk: str, lane: str, *, first_chunk: bool) -> str:
    if lane != "fx_shock":
        return html.escape(chunk)

    lines = chunk.splitlines()
    if not lines:
        return ""
    rendered: list[str] = []
    for index, line in enumerate(lines):
        if first_chunk and index == 0:
            rendered.append(_bold(line))
        else:
            rendered.append(_format_fx_line(line))
    return "\n".join(rendered)


def render_telegram_html_chunks(title: str, body: str, lane: str) -> list[str]:
    """Render all Telegram-safe HTML chunks without truncating the alert."""
    plain_chunks = split_plain_message(title, body)
    return [
        _render_chunk(chunk, lane, first_chunk=(index == 0))
        for index, chunk in enumerate(plain_chunks)
    ]


def render_telegram_html(title: str, body: str, lane: str) -> str:
    """Compatibility helper for alerts that fit in one Telegram message."""
    chunks = render_telegram_html_chunks(title, body, lane)
    if len(chunks) != 1:
        raise ValueError("Alert exceeds one Telegram message; use render_telegram_html_chunks")
    return chunks[0]

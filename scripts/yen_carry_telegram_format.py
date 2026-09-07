#!/usr/bin/env python3
"""Telegram HTML readability formatter for yen-carry alerts.

The alert calculation and source text remain unchanged. This module only applies
safe Telegram HTML at send time so important FX-shock values are visually easier
to scan without breaking sector enrichment or GitHub markdown artifacts.
"""
from __future__ import annotations

import html
import re

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


def render_telegram_html(title: str, body: str, lane: str) -> str:
    """Render a Telegram-safe HTML message without changing alert logic/content."""
    plain = f"{title.strip()}\n\n{body.strip()}"[:4096]
    lines = plain.splitlines()
    if not lines:
        return ""
    if lane != "fx_shock":
        return html.escape(plain)

    rendered = [_bold(lines[0])]
    rendered.extend(_format_fx_line(line) for line in lines[1:])
    return "\n".join(rendered)

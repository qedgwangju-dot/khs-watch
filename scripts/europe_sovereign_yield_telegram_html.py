#!/usr/bin/env python3
"""Safe Telegram HTML formatter for European sovereign-yield alerts.

Always converts official AND secondary source links into clickable, short
descriptive labels. Builds message chunks BEFORE rendering individual lines
so Telegram HTML tags can never be split in the middle.
"""
from __future__ import annotations

import html
from urllib.parse import urlsplit

LINKS = (
    ("• Banque de France TEC10: ", "프랑스 중앙은행 TEC10 공식 원문", "www.banque-france.fr"),
    ("• Deutsche Bundesbank 10Y: ", "독일 Bundesbank 10년물 공식 원문", "www.bundesbank.de"),
    ("• Bank of England IUDMNPY: ", "영국 중앙은행 10년물 공식 자료", "www.bankofengland.co.uk"),
    ("• Italy 10Y Trading Economics 보조 시장자료: ", "이탈리아 10년물 시장자료", "tradingeconomics.com"),
    ("• France 10Y Trading Economics 보조 시장자료: ", "프랑스 10년물 시장자료", "tradingeconomics.com"),
    ("• Germany 10Y Trading Economics 보조 시장자료: ", "독일 10년물 시장자료", "tradingeconomics.com"),
    ("• UK 10Y Trading Economics 보조 시장자료: ", "영국 10년물 시장자료", "tradingeconomics.com"),
)


def render_line(line: str) -> str:
    for prefix, label, expected_host in LINKS:
        if not line.startswith(prefix):
            continue
        url = line[len(prefix):].strip()
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != expected_host or parsed.username or parsed.password:
            raise ValueError(f"Source link is not an expected HTTPS URL: {label}")
        if any(x in url for x in ("\n", "\r", "<", ">")):
            raise ValueError(f"Invalid characters in source URL: {label}")
        return f'• <a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
    # Untrusted text is never interpreted as HTML. Section headings are bold.
    if line.startswith("■ ") or line.startswith("🔴 [유럽") or line.startswith("🟠 [유럽") or line.startswith("🟡 [유럽"):
        return f"<b>{html.escape(line)}</b>"
    return html.escape(line)


def render_chunks(body: str, *, limit: int = 3900) -> list[str]:
    """Return HTML-parseable Telegram messages below the safe limit.

    Paragraphs are preferred; overly large paragraphs may split at whole lines,
    but never at HTML tags or URLs. Empty or overly long individual lines fail.
    """
    if not body.strip():
        raise ValueError("No alert body to send")
    chunks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            chunks.append("\n".join(current).strip())
            current.clear()

    for para in body.strip().split("\n\n"):
        lines = [render_line(line) for line in para.splitlines()]
        for index, line in enumerate(lines):
            if len(line) > limit:
                raise ValueError("Source line is too long for a safe Telegram message")
            sep = "\n\n" if current and index == 0 else ("\n" if current else "")
            projected = len("\n".join(current)) + len(sep) + len(line)
            if projected > limit:
                flush()
                sep = ""
            if sep == "\n\n":
                current.append("")
            current.append(line)
    flush()
    if not chunks or any(not x or len(x) > limit for x in chunks):
        raise ValueError("Telegram message chunk size validation failed")
    return chunks

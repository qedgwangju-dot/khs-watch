#!/usr/bin/env python3
"""Convert the global-rates Telegram report into safe HTML with compact source links."""
from __future__ import annotations

import html
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT = ROOT / "out" / "global_rates_watch_telegram.md"
SOURCE_RE = re.compile(r"^(?P<prefix>-\s+.+?):\s+(?P<url>https?://\S+)\s*$")


def htmlify(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_sources = False

    for line in lines:
        if line.strip() == "출처":
            in_sources = True
            out.append("<b>출처</b>")
            continue

        if in_sources:
            match = SOURCE_RE.match(line)
            if match:
                prefix = html.escape(match.group("prefix"), quote=False)
                url = html.escape(match.group("url"), quote=True)
                out.append(f'{prefix} · <a href="{url}">원문</a>')
                continue

        out.append(html.escape(line, quote=False))

    return "\n".join(out).strip() + "\n"


def main() -> int:
    if not REPORT.exists():
        return 0
    REPORT.write_text(htmlify(REPORT.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

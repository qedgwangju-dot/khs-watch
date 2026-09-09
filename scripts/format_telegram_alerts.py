#!/usr/bin/env python3
from __future__ import annotations

import html
import re
from pathlib import Path

OUT = Path("out")
URL_RE = re.compile(r"https?://\S+")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def bold_numbers(s: str) -> str:
    """Emphasize the values users scan first, without changing the wording."""
    s = esc(s)
    patterns = [
        r"(?<![\w])\$[0-9][0-9,]*(?:\.[0-9]+)?(?:B|M)?(?:/MW-day)?",
        r"(?<![\w])[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:MW|GW|GWh|MWh|kW)",
        r"(?<![\w])[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:조\s*)?[0-9,]*억원",
        r"(?<![\w])[0-9][0-9,]*(?:\.[0-9]+)?원(?:/MW-day)?",
        r"(?<![\w])[0-9][0-9,]*(?:\.[0-9]+)?%p?",
        r"(?<![\w])20\d{2}-\d{2}-\d{2}",
        r"(?<![\w])[0-9]{1,2}년",
    ]
    for pat in patterns:
        s = re.sub(pat, lambda m: f"<b>{m.group(0)}</b>", s)
    # Avoid accidental nested bold tags from overlapping patterns.
    s = s.replace("<b><b>", "<b>").replace("</b></b>", "</b>")
    return s


def clean_label(text: str) -> str:
    text = re.sub(r"\s+-\s+(RTO Insider|Utility Dive|Reuters|Energy-Storage\.News|Public Power)$", "", text).strip()
    text = re.sub(r"^(PJM 최신 공시·명령|PJM RBP 공식 페이지):\s*", "", text).strip()
    return text


def format_pjm(text: str) -> str:
    raw = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    seen_urls: set[str] = set()
    i = 0

    while i < len(raw):
        line = raw[i].strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            i += 1
            continue

        if i == 0:
            out.append(f"<b>{esc(line)}</b>")
            i += 1
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            icon = {
                "현재 공식 기준": "📌",
                "신규 확인": "🆕",
                "투자 해석": "🧭",
                "환율": "💱",
                "공식 원문": "🔗",
            }.get(section, "▪️")
            if out and out[-1] != "":
                out.append("")
            out.append(f"<b>{icon} {esc(section)}</b>")
            i += 1
            continue

        # Pair a descriptive bullet with a raw URL on the next line.
        if line.startswith("• ") and i + 1 < len(raw) and URL_RE.fullmatch(raw[i + 1].strip()):
            url = raw[i + 1].strip()
            label = clean_label(line[2:].strip())
            if url not in seen_urls:
                source_icon = "🏛️" if any(x in line for x in ("PJM", "FERC", "Federal Register")) else "📰"
                out.append(f"{source_icon} <a href=\"{esc(url)}\">{esc(label)}</a>")
                seen_urls.add(url)
            i += 2
            continue

        # Convert bullets containing an inline raw URL into a labeled text link.
        if line.startswith("• ") and URL_RE.search(line):
            m = URL_RE.search(line)
            assert m
            url = m.group(0)
            label = clean_label((line[2:m.start()] + line[m.end():]).strip(" :-")) or "원문"
            if url not in seen_urls:
                out.append(f"🔗 <a href=\"{esc(url)}\">{esc(label)}</a>")
                seen_urls.add(url)
            i += 1
            continue

        # Suppress standalone duplicate/raw URLs after they have been converted.
        if URL_RE.fullmatch(line):
            if line not in seen_urls:
                out.append(f"🔗 <a href=\"{esc(line)}\">원문</a>")
                seen_urls.add(line)
            i += 1
            continue

        if line.startswith("• "):
            body = line[2:].strip()
            if body.startswith("그 외 신규 자료"):
                out.append(f"• <i>{esc(body)}</i>")
            else:
                out.append("• " + bold_numbers(body))
            i += 1
            continue

        out.append(bold_numbers(line))
        i += 1

    # Collapse excessive blank lines.
    compact: list[str] = []
    for line in out:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)
    return "\n".join(compact).strip() + "\n"


def format_generic(text: str) -> str:
    lines = []
    for idx, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line:
            lines.append("")
        elif idx == 0:
            lines.append(f"<b>{esc(line)}</b>")
        elif line.startswith("[") and line.endswith("]"):
            lines.append(f"<b>▪️ {esc(line[1:-1])}</b>")
        elif line.startswith("• "):
            lines.append("• " + bold_numbers(line[2:]))
        elif URL_RE.fullmatch(line):
            lines.append(f"🔗 <a href=\"{esc(line)}\">공식 원문</a>")
        else:
            lines.append(bold_numbers(line))
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    files = [
        OUT / "data_center_growth_alert.txt",
        OUT / "pjm_data_center_policy_alert.txt",
    ]
    for p in files:
        if not p.exists() or not p.read_text(encoding="utf-8").strip():
            continue
        text = p.read_text(encoding="utf-8")
        formatted = format_pjm(text) if p.name.startswith("pjm_") else format_generic(text)
        p.write_text(formatted, encoding="utf-8")
        print(f"formatted={p}")


if __name__ == "__main__":
    main()

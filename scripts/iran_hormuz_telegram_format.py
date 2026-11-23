"""Render this watch's existing plain-text alerts as readable Telegram HTML.

Only the Bernstein block is regrouped; other event text and delivery state are
left intact. The returned HTML is intended for sendMessage(parse_mode='HTML').
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

BERNSTEIN_HEADING = "[Bernstein | 글로벌 석유 수급 전망 변화]"
LINK_LABELS = {
    "원문": "원문 보기",
    "기사 원문": "Bernstein 보도 원문",
    "IEA 참고": "IEA 공식 보고서",
    "환율 근거": "은행 환율 자료",
}


def _linked_source(line: str) -> str | None:
    """Turn a named trusted-web URL line into a short, safe clickable link."""
    for prefix, label in LINK_LABELS.items():
        start = prefix + ": "
        if not line.startswith(start):
            continue
        url = line[len(start):].strip()
        try:
            parts = urlsplit(url)
        except ValueError:
            return html.escape(line)
        if (parts.scheme.lower() not in {"https", "http"}
                or not parts.hostname or parts.username or parts.password
                or any(c in url for c in ('"', "<", ">", "\n", "\r"))):
            return html.escape(line)
        return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
    return None


def _ordinary_lines(body: str) -> str:
    lines = []
    for line in body.splitlines():
        linked = _linked_source(line)
        if linked is not None:
            lines.append(linked)
        elif re.fullmatch(r"\[[^\]\n]+\]", line):
            lines.append(f"<b>{html.escape(line)}</b>")
        else:
            lines.append(html.escape(line))
    return "\n".join(lines)


def _labeled_bullet(line: str) -> str:
    if ": " in line:
        field, value = line.split(": ", 1)
        return f"• <b>{html.escape(field)}</b>: {html.escape(value)}"
    return f"• {html.escape(line)}"


def _bernstein_block(body: str, add_heading: bool) -> str:
    sections: dict[str, list[str]] = {
        "meta": [], "balance": [], "price": [], "context": [],
        "risk": [], "fx": [], "source": [], "other": [],
    }
    for line in body.splitlines():
        line = line.strip()
        if not line or line == BERNSTEIN_HEADING:
            continue
        linked = _linked_source(line)
        if linked is not None:
            sections["source"].append(linked)
        elif line.startswith(("보도일:", "자료 단계:")):
            sections["meta"].append(line)
        elif line.startswith(("2026년:", "2027년:", "변화:", "2027년 연간 누적 공급 과잉:")):
            sections["balance"].append(line)
        elif line.startswith(("2027년 브렌트유", "2028년 브렌트유")):
            sections["price"].append(line)
        elif line.startswith(("흡수 요인:", "기간 정정:", "주의:", "독립 참고:", "그러나 IEA")):
            sections["context"].append(line)
        elif line.startswith(("역풍:", "다음 확인:")):
            sections["risk"].append(line)
        elif line.startswith("환산 기준:"):
            sections["fx"].append(line)
        else:
            sections["other"].append(line)

    output: list[str] = []
    if add_heading:
        output.append("<b>Bernstein | 글로벌 석유 수급 전망 변화</b>")
    for line in sections["meta"]:
        if line.startswith("자료 단계:"):
            output.append(f"<i>{html.escape(line)}</i>")
        else:
            output.append(html.escape(line))
    grouped = (
        ("수급 전망", "balance"),
        ("브렌트유 연평균 전망", "price"),
        ("전망의 의미와 검증", "context"),
        ("위험·후속 확인", "risk"),
        ("환율", "fx"),
        ("추가 확인사항", "other"),
    )
    for title, key in grouped:
        if sections[key]:
            output.append("")
            output.append(f"<b>{title}</b>")
            output.extend(_labeled_bullet(line) for line in sections[key])
    if sections["source"]:
        output.append("")
        output.append("<b>출처 링크</b>")
        output.append(" · ".join(sections["source"]))
    return "\n".join(output)


def render_telegram_html(title: str, body: str) -> str:
    """Preserve all source facts while providing clickable labeled links."""
    prefix = f"<b>{html.escape(title.strip())}</b>"
    if BERNSTEIN_HEADING not in body:
        return prefix + "\n\n" + _ordinary_lines(body.strip())
    ordinary, bernstein = body.split(BERNSTEIN_HEADING, 1)
    ordinary = ordinary.strip()
    block = _bernstein_block(BERNSTEIN_HEADING + bernstein, add_heading=bool(ordinary))
    return prefix + "\n\n" + (_ordinary_lines(ordinary) + "\n\n" if ordinary else "") + block


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.count = 0

    def handle_data(self, data: str) -> None:
        self.count += len(data)


def telegram_visible_length(rendered_html: str) -> int:
    """Telegram's 4096-character limit applies after HTML entity parsing."""
    parser = _VisibleText()
    parser.feed(rendered_html)
    parser.close()
    return parser.count

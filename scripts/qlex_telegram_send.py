from __future__ import annotations

import html
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

MAX_CHARS = 3900


def split_message(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in text.strip().split("\n\n"):
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) <= MAX_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(paragraph) > MAX_CHARS:
            cut = paragraph.rfind("\n", 0, MAX_CHARS)
            if cut < 1:
                cut = MAX_CHARS
            chunks.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def clean_source_url(url: str) -> str:
    """Hide search-engine redirect noise and use the embedded article URL when available."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.endswith("bing.com") and parsed.path.endswith("/news/apiclick.aspx"):
            target = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
            if target.startswith(("http://", "https://")):
                return target
    except Exception:
        pass
    return url


def render_html(text: str) -> str:
    """Escape normal text and render only source URLs as compact Telegram inline links."""
    rendered: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- 원문:"):
            url = stripped.split(":", 1)[1].strip()
            if url.startswith(("http://", "https://")):
                target = clean_source_url(url)
                rendered.append(
                    f'- <a href="{html.escape(target, quote=True)}">[원문 뉴스보기]</a>'
                )
                continue
        rendered.append(html.escape(line, quote=False))
    return "\n".join(rendered)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: qlex_telegram_send.py REPORT_PATH", file=sys.stderr)
        return 2

    token = (os.getenv("BIO_TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("BIO_TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token or not chat_id or not expected:
        raise RuntimeError("bio Telegram token/chat_id/expected username is missing")

    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
        identity = json.loads(response.read().decode("utf-8"))
    actual = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")

    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("Telegram report is empty")

    ids: list[int] = []
    for index, chunk in enumerate(split_message(text), 1):
        if index > 1:
            chunk = f"[QLEX 감시 계속 {index}]\n\n{chunk}"
        chunk_html = render_html(chunk)
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": chunk_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected message: {result}")
        ids.append(int(result["result"]["message_id"]))

    print(f"telegram_delivery_confirmed=true bot=@{actual} message_ids={ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

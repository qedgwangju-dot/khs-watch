from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

MAX_CHARS = 3900
KST = ZoneInfo("Asia/Seoul")
_TRANSLATION_CACHE: dict[str, str] = {}


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


def is_english_dominant(value: str) -> bool:
    latin = len(re.findall(r"[A-Za-z]", value))
    korean = len(re.findall(r"[가-힣]", value))
    return latin >= 8 and latin > korean * 2


def fallback_title_ko(title: str) -> str:
    """Deterministic Korean fallback for the recurring Intismeran/QLEX headline patterns."""
    low = title.lower()

    if "interpath-001" in low and "boosts rfs" in low:
        return "INTerpath-001: 흑색종 보조요법에서 Intismeran+Pembrolizumab이 재발 없는 생존기간(RFS) 개선"

    if "custom-made" in low and "mrna" in low and "cancer vaccine" in low and "melanoma" in low:
        return "Moderna·Merck의 개인맞춤형 mRNA 암 백신, 후기 흑색종 임상에서 긍정적 결과"

    if "meets primary endpoint" in low and ("phase iii" in low or "phase 3" in low):
        return "Moderna의 Intismeran+KEYTRUDA, 흑색종 3상 1차 평가변수 달성"

    if "meets" in low and "endpoint" in low and ("phase iii" in low or "phase 3" in low) and "melanoma" in low:
        return "Merck·Moderna의 Intismeran+KEYTRUDA, 흑색종 3상 평가변수 달성"

    if "stock soars" in low and "melanoma" in low:
        pct = re.search(r"\b(\d+(?:\.\d+)?)%", title)
        suffix = f" {pct.group(1)}%" if pct else ""
        return f"Merck 주가, 흑색종 임상 결과 발표 후{suffix} 급등"

    if "stock surging" in low and "cancer" in low and "vaccine" in low:
        return "Moderna 주가, 암 백신 임상 진전으로 급등…향후 변동성 주의"

    if "interpath-001" in low and "phase" in low and "melanoma" in low:
        return "INTerpath-001 흑색종 3상 관련 신규 보도"

    if "intismeran" in low and "keytruda" in low:
        return "Intismeran·KEYTRUDA 관련 신규 보도"

    # Last-resort glossary conversion: avoids sending a fully English headline even if translation API is unavailable.
    value = title
    replacements = [
        (r"\bPhase\s*III\b", "3상"),
        (r"\bPhase\s*3\b", "3상"),
        (r"\bprimary endpoint\b", "1차 평가변수"),
        (r"\bendpoints\b", "평가변수"),
        (r"\bendpoint\b", "평가변수"),
        (r"\badjuvant\b", "보조요법"),
        (r"\bmelanoma\b", "흑색종"),
        (r"\bcancer vaccine\b", "암 백신"),
        (r"\btrial results\b", "임상 결과"),
        (r"\btrial\b", "임상"),
        (r"\bshows promise\b", "긍정적 가능성 확인"),
        (r"\bmet\b", "달성"),
        (r"\bmeets\b", "달성"),
        (r"\bresults\b", "결과"),
    ]
    for pattern, repl in replacements:
        value = re.sub(pattern, repl, value, flags=re.I)
    if is_english_dominant(value):
        return "Intismeran·KEYTRUDA 관련 신규 보도 — 세부 내용은 아래 한국어 해석 참조"
    return value


def translate_title_to_ko(title: str) -> str:
    """Translate an English headline to Korean; never fail the alert if translation service is unavailable."""
    if not is_english_dominant(title):
        return title
    if title in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[title]

    translated = ""
    try:
        # MyMemory documents basic REST translation without an API key. Headline length stays well below its 500-byte segment limit.
        query = urllib.parse.urlencode({
            "q": title[:480],
            "langpair": "en|ko",
            "mt": "1",
        })
        req = urllib.request.Request(
            f"https://api.mymemory.translated.net/get?{query}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; BioAlertKorean/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        candidate = html.unescape(str((payload.get("responseData") or {}).get("translatedText") or "")).strip()
        if candidate and candidate.lower() != title.lower() and len(re.findall(r"[가-힣]", candidate)) >= 3:
            translated = candidate
    except Exception:
        translated = ""

    if not translated:
        translated = fallback_title_ko(title)

    # Normalize recurring technical wording while preserving identifiers.
    translated = re.sub(r"임상 시험", "임상", translated)
    translated = re.sub(r"3 단계", "3상", translated)
    translated = re.sub(r"3단계", "3상", translated)
    translated = re.sub(r"재발[- ]?없는 생존", "재발 없는 생존기간", translated)
    _TRANSLATION_CACHE[title] = translated
    return translated


def koreanize_timestamp(value: str) -> str:
    try:
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return stamp.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return value


def normalize_alert_language(text: str) -> str:
    """Korean-first Telegram output while preserving drug/trial identifiers."""
    out: list[str] = []
    title_pattern = re.compile(r"^(\d+[.)])\s+(.+)$")

    for line in text.splitlines():
        stripped = line.strip()
        match = title_pattern.match(stripped)
        if match:
            prefix, title = match.groups()
            line = f"{prefix} {translate_title_to_ko(title)}"
        elif stripped.startswith("- 발표/게시:"):
            value = stripped.split(":", 1)[1].strip()
            line = f"- 발표/게시: {koreanize_timestamp(value)}"
        elif not stripped.startswith("- 원문:"):
            # General explanatory English should be Korean; identifiers/acronyms stay unchanged.
            line = line.replace("heartbeat", "상태 확인")
            line = line.replace("watchdog", "자동 복구 감시")
            line = re.sub(r"\bPhase\s*III\b", "3상", line, flags=re.I)
            line = re.sub(r"\bPhase\s*3\b", "3상", line, flags=re.I)
        out.append(line)
    return "\n".join(out)


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
                    f'- <a href="{html.escape(target, quote=True)}">원문 뉴스보기</a>'
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

    text = normalize_alert_language(text)

    ids: list[int] = []
    for index, chunk in enumerate(split_message(text), 1):
        if index > 1:
            chunk = f"[바이오 감시 계속 {index}]\n\n{chunk}"
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
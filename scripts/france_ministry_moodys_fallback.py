#!/usr/bin/env python3
"""Read-only recovery of French Finance Ministry's first-party Moody's notice.

The AFT credit-rating page often returns HTTP 403 on GitHub runners. A ministry
press release is independently first-party French-government evidence of an
announced sovereign-rating event, NOT automatically an official Moody's issuer
rating action. Any rating or outcome not explicitly parsed remains unconfirmed.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import urllib.parse
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

SEARCH_URL = "https://presse.economie.gouv.fr/?s=Moody"
DIRECT_NOTICE_URL = "https://presse.economie.gouv.fr/notation-moodys-reaction-de-roland-lescure/"
HOST = "presse.economie.gouv.fr"
PARIS = ZoneInfo("Europe/Paris")
REVIEW_DATE = dt.date(2026, 10, 23)
MAX_PAGES = 5


def plain_text(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>",
                   " ", value, flags=re.I | re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def ministry_search_links(document: str) -> list[tuple[str, str]]:
    out = []
    for link, inner in re.findall(
        r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        document, re.I | re.S,
    ):
        label = plain_text(inner)
        if not re.search(r"moody['’]?s|moody", label, re.I):
            continue
        if not re.search(r"notation|note|rating|r[eé]action", label, re.I):
            continue
        url = urllib.parse.urljoin(SEARCH_URL, html.unescape(link))
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != HOST or parsed.username or parsed.password:
            continue
        if "/wp-" in parsed.path or parsed.path == "/":
            continue
        out.append((url, label))
    return list(dict.fromkeys(out))[:MAX_PAGES]


def ministry_publish_date(document: str) -> dt.date | None:
    for pattern in (
        r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})',
        r'property=["\']article:published_time["\'][^>]*content=["\'](\d{4}-\d{2}-\d{2})',
        r'<time[^>]*datetime=["\'](\d{4}-\d{2}-\d{2})',
    ):
        m = re.search(pattern, document, flags=re.I)
        if m:
            try:
                return dt.date.fromisoformat(m.group(1))
            except ValueError:
                pass
    # Only use visible article text, not scripts containing dynamic timestamps.
    s = plain_text(document)
    m = re.search(r"\b(\d{1,2})\s+(octobre|october)\s+(20\d{2})\b", s, re.I)
    if m:
        try:
            return dt.date(int(m.group(3)), 10, int(m.group(1)))
        except ValueError:
            return None
    return None


def validate_ministry_notice(document: str, url: str, now: dt.datetime) -> dict | None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST:
        return None
    published = ministry_publish_date(document)
    local_day = now.astimezone(PARIS).date()
    if not published or published < REVIEW_DATE or published > local_day:
        return None
    text = plain_text(document)
    if not (re.search(r"Moody", text, re.I) and
            re.search(r"notation|note souveraine|note de la france|rating", text, re.I) and
            re.search(r"\bFrance\b", text, re.I)):
        return None
    notice = {
        "kind": "government_rating_notice",
        "date": published.isoformat(),
        "url": url,
        "source_kind": "official_government_press",
        "source_scope": "French government press statement; not Moody's issuer rating action",
    }
    # A first-party government quote may report the result, but is not the
    # rating agency's own source. Do not promote it to official_document.
    if re.search(r"maintenir\s+la\s+note\s+de\s+la\s+France\s+à\s+Aa3\s+avec\s+perspective\s+n[eé]gative", text, re.I):
        notice["reported_rating_by_government"] = "Aa3"
        notice["reported_outlook_by_government"] = "Negative"
    return notice


def discover_ministry_notice(fetch, now: dt.datetime) -> tuple[dict | None, list[str]]:
    errors = []
    # The official 23 October press title says "Réaction" rather than
    # "notation": the general search page can miss it. Check its canonical
    # published URL first; never infer a rating result from HTTP success alone.
    try:
        document = fetch(DIRECT_NOTICE_URL)
        notice = validate_ministry_notice(document, DIRECT_NOTICE_URL, now)
        if notice:
            notice["title"] = "Moody's : réaction de Roland Lescure"
            return notice, errors
    except Exception as e:
        errors.append(f"French Finance Ministry direct notice: {type(e).__name__} {str(e)[:110]}")
    try:
        html_index = fetch(SEARCH_URL)
        candidates = ministry_search_links(html_index)
    except Exception as e:
        errors.append(f"French Finance Ministry search: {type(e).__name__} {str(e)[:110]}")
        return None, errors
    for url, title in candidates:
        try:
            candidate = validate_ministry_notice(fetch(url), url, now)
            if candidate:
                candidate["title"] = title
                return candidate, errors
        except Exception as e:
            errors.append(f"French Finance Ministry notice: {type(e).__name__} {str(e)[:110]}")
    return None, errors

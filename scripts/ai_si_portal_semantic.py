"""SI.gov official policy-link monitor for the existing AI policy workflow.

Do not hash page text: counters, navigation and design change independently of
policy. Use only canonical government document links and a durable baseline.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

SOURCE_URL = "https://www.si.gov/"
VERSION = 1
CONFIRM_OBSERVATIONS = 2
CONFIRM_MINUTES = 10
ALLOWED_HOSTS = {"si.gov", "www.si.gov", "www.whitehouse.gov", "whitehouse.gov", "www.federalregister.gov", "federalregister.gov"}
REGULATORY_KEYS = ("safety", "security", "procurement", "regulation", "audit", "standards")
INFRA_KEYS = ("data-center", "data-center-infrastructure", "power-grid", "permitting", "transmission")
EXPORT_KEYS = ("export", "american-si-stack", "technology-stack")
SCIENCE_KEYS = ("genesis", "science", "compute", "research", "funding")
EDUCATION_KEYS = ("challenge", "education", "student", "pledge", "school")


def canonical_url(href: str, base: str = SOURCE_URL) -> str | None:
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    url = urljoin(base, html.unescape(href).strip())
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    if parts.scheme != "https" or hostname not in ALLOWED_HOSTS:
        return None
    path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    if hostname in {"si.gov", "www.si.gov"}:
        if not (path.startswith("/initiatives/") or path.startswith("/news/")):
            return None
        hostname = "www.si.gov"
    elif hostname in {"whitehouse.gov", "www.whitehouse.gov"}:
        if not path.startswith(("/presidential-actions/", "/fact-sheets/", "/briefings-statements/", "/releases/", "/remarks/")):
            return None
        hostname = "www.whitehouse.gov"
    else:
        if not path.startswith(("/documents/", "/d/")):
            return None
        hostname = "www.federalregister.gov"
    return urlunsplit(("https", hostname, path, "", ""))


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inside_script = 0
        self.href: str | None = None
        self.anchor_parts: list[str] = []
        self.links: dict[str, str] = {}
        self.visible: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.inside_script += 1
            return
        if tag == "a" and not self.inside_script:
            self.href = dict(attrs).get("href")
            self.anchor_parts = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.inside_script:
            self.inside_script -= 1
        if tag == "a" and self.href is not None:
            url = canonical_url(self.href)
            title = " ".join(" ".join(self.anchor_parts).split())[:135]
            if url and title:
                self.links[url] = title
            self.href = None
            self.anchor_parts = []

    def handle_data(self, value):
        if self.inside_script:
            return
        cleaned = " ".join(value.split())
        if cleaned:
            self.visible.append(cleaned)
            if self.href is not None:
                self.anchor_parts.append(cleaned)


def extract_portal_links(page: str) -> dict[str, str]:
    parser = LinkParser()
    parser.feed(page)
    parser.close()
    text = " ".join(parser.visible).lower()
    if not ("super intelligence" in text and "genesis mission" in text and "american si stack" in text):
        raise ValueError("SI.gov page identity/content could not be verified")
    if len(parser.links) < 2:
        raise ValueError("SI.gov provided insufficient official policy links")
    return dict(sorted(parser.links.items()))


def category_for_link(url: str, title: str) -> str:
    text = (url + " " + title).lower()
    if any(k in text for k in REGULATORY_KEYS):
        return "SI 안전·규제·조달 변화"
    if any(k in text for k in INFRA_KEYS):
        return "SI 데이터센터·전력·인허가 변화"
    if any(k in text for k in EXPORT_KEYS):
        return "SI 기술 생태계·해외 수출 변화"
    if any(k in text for k in SCIENCE_KEYS):
        return "SI 연구개발·컴퓨팅 지원 변화"
    if any(k in text for k in EDUCATION_KEYS):
        return "SI 교육·인재 육성 변화"
    return "SI 공식 정책·사업 문서 변화"


def advance_portal_state(previous: dict | None, links: dict[str, str], now: dt.datetime):
    """Return (updated state, newly confirmed links). Missing links are not deletions."""
    prev = dict(previous or {})
    if prev.get("version") != VERSION or not prev.get("initialized"):
        return {
            "initialized": True,
            "version": VERSION,
            "last_success_at": now.isoformat(),
            "known_links": dict(links),
            "candidates": {},
        }, []

    known = dict(prev.get("known_links") or {})
    candidates = dict(prev.get("candidates") or {})
    confirmed = []
    for url, title in links.items():
        if url in known:
            candidates.pop(url, None)
            continue
        existing = candidates.get(url)
        if existing:
            first_seen = dt.datetime.fromisoformat(existing["first_seen_at"]).astimezone(dt.timezone.utc)
            count = int(existing.get("count") or 0) + 1
        else:
            first_seen = now.astimezone(dt.timezone.utc)
            count = 1
        delta = (now.astimezone(dt.timezone.utc) - first_seen).total_seconds()
        if count >= CONFIRM_OBSERVATIONS and delta >= CONFIRM_MINUTES * 60:
            known[url] = title
            candidates.pop(url, None)
            confirmed.append({"url": url, "title": title, "category": category_for_link(url, title)})
        else:
            candidates[url] = {"first_seen_at": first_seen.isoformat(), "count": count, "title": title}

    # Keep unobserved candidates for a short time, but never call removals new events.
    fresh_cutoff = now.astimezone(dt.timezone.utc) - dt.timedelta(days=3)
    for url in list(candidates):
        try:
            first = dt.datetime.fromisoformat(candidates[url]["first_seen_at"]).astimezone(dt.timezone.utc)
        except (ValueError, KeyError):
            first = fresh_cutoff - dt.timedelta(seconds=1)
        if first < fresh_cutoff:
            candidates.pop(url, None)

    return {
        "initialized": True, "version": VERSION,
        "last_success_at": now.isoformat(),
        "known_links": known, "candidates": candidates,
    }, confirmed

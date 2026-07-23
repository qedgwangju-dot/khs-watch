#!/usr/bin/env python3
"""Extract verified article identity and body text from trusted HTML pages."""

from __future__ import annotations

import datetime as dt
import html
import re
from html.parser import HTMLParser
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "blockquote"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP_TAGS = {"script", "style", "svg", "noscript", "template"}
TARGET_MARKERS = (
    "entry-content",
    "wp-block-post-content",
    "articlebody",
    "article-body",
    "article_body",
    "article-content",
    "article_content",
    "news-content",
    "news_content",
)
TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "fact",
    "sheet",
    "president",
    "donald",
    "j",
    "trump",
    "the",
    "to",
    "of",
    "on",
    "in",
    "from",
}


def clean(value: str | None) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


class ArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_text: list[str] = []
        self.in_title = False
        self.capture_depth = 0
        self.skip_depth = 0
        self.block_depth = 0
        self.block_parts: list[str] = []
        self.blocks: list[str] = []
        self.time_values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag == "meta":
            key = clean(attr.get("property") or attr.get("name")).lower()
            value = clean(attr.get("content"))
            if key and value:
                self.meta.setdefault(key, value)
            return
        if tag == "title":
            self.in_title = True
        if tag == "time" and attr.get("datetime"):
            self.time_values.append(clean(attr["datetime"]))

        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        identity = f"{attr.get('id', '')} {attr.get('class', '')} {attr.get('itemprop', '')}".lower().replace("_", "-")
        is_target = any(marker.replace("_", "-") in identity for marker in TARGET_MARKERS)
        if self.capture_depth:
            if tag not in VOID_TAGS:
                self.capture_depth += 1
        elif is_target:
            self.capture_depth = 1

        if self.capture_depth and tag in BLOCK_TAGS:
            if self.block_depth == 0:
                self.block_parts = []
            self.block_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return

        if self.capture_depth and tag in BLOCK_TAGS and self.block_depth:
            self.block_depth -= 1
            if self.block_depth == 0:
                value = clean(" ".join(self.block_parts))
                if value and (not self.blocks or value != self.blocks[-1]):
                    self.blocks.append(value)
                self.block_parts = []
        if self.capture_depth and tag not in VOID_TAGS:
            self.capture_depth = max(0, self.capture_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_text.append(data)
        if self.capture_depth and self.block_depth and not self.skip_depth:
            self.block_parts.append(data)


def parse_published(value: str | None) -> dt.datetime | None:
    value = clean(value)
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(value, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def normalized_title_tokens(value: str) -> list[str]:
    value = clean(value).lower().replace("’", "'")
    value = re.sub(r"\s+-\s+(?:이투데이|전자신문|the white house)\s*$", "", value, flags=re.I)
    tokens = re.findall(r"[a-z0-9가-힣]+", value)
    return [token for token in tokens if token not in TITLE_STOPWORDS and len(token) > 1]


def titles_align(listing_title: str, detail_title: str) -> bool:
    left = normalized_title_tokens(listing_title)
    right = normalized_title_tokens(detail_title)
    if not left or not right:
        return False
    left_text, right_text = " ".join(left), " ".join(right)
    if left_text in right_text or right_text in left_text:
        return True
    overlap = len(set(left) & set(right))
    return overlap / max(1, min(len(set(left)), len(set(right)))) >= 0.6


def extract_article_detail(html_text: str, listing_title: str = "") -> dict:
    parser = ArticleHTMLParser()
    try:
        parser.feed(html_text or "")
    except Exception:
        return {
            "title": "",
            "abstract": "",
            "body": "",
            "published_kst": "",
            "title_aligned": False,
            "body_verified": False,
        }

    title = clean(
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or " ".join(parser.title_text)
    )
    abstract = clean(parser.meta.get("og:description") or parser.meta.get("description"))
    body = "\n".join(parser.blocks)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    published = parse_published(
        parser.meta.get("article:published_time")
        or parser.meta.get("date")
        or parser.meta.get("dc.date.issued")
        or (parser.time_values[0] if parser.time_values else "")
    )
    aligned = titles_align(listing_title or title, title)
    return {
        "title": title,
        "abstract": abstract,
        "body": body[:50000],
        "published_kst": published.isoformat(timespec="seconds") if published else "",
        "title_aligned": aligned,
        "body_verified": bool(aligned and len(body) >= 180),
    }

#!/usr/bin/env python3
"""Extract verified article identity and body text from trusted HTML pages."""

from __future__ import annotations

import datetime as dt
import html
import json
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
    "news-body",
    "news-detail-wrap",
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
PUBLISHER_TITLE_SUFFIXES = (
    "이투데이",
    "전자신문",
    "이데일리",
    "머니투데이",
    "매일경제",
    "헤럴드경제",
    "연합뉴스",
    "한국경제",
    "서울경제",
    "edaily.co.kr",
    "mt.co.kr",
    "mk.co.kr",
    "biz.heraldcorp.com",
    "yna.co.kr",
    "hankyung.com",
)


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
        self.raw_parts: list[str] = []
        self.target_depth = 0
        self.target_parts: list[str] = []
        self.target_bodies: list[str] = []
        self.ignored_depth = 0
        self.ignored_tags: list[str] = []
        self.time_values: list[str] = []
        self.publication_region_depth = 0
        self.publication_region_parts: list[str] = []
        self.publication_region_values: list[str] = []
        self.json_ld_depth = 0
        self.json_ld_parts: list[str] = []
        self.json_ld_current: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {str(key).lower(): str(value or "") for key, value in attrs}
        if self.ignored_depth:
            if tag not in VOID_TAGS:
                self.ignored_tags.append(tag)
                self.ignored_depth = len(self.ignored_tags)
            return
        hidden = (
            "hidden" in attr or attr.get("aria-hidden", "").lower() == "true"
            or re.search(r"display\s*:\s*none", attr.get("style", ""), re.I)
        )
        if tag in {"aside", "nav", "footer", "form"} or hidden:
            if tag not in VOID_TAGS:
                self.ignored_tags = [tag]
                self.ignored_depth = 1
            return
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
        if tag == "script" and "ld+json" in attr.get("type", "").lower():
            self.json_ld_depth = 1
            self.json_ld_current = []
            return

        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        identity = f"{attr.get('id', '')} {attr.get('class', '')} {attr.get('itemprop', '')}".lower().replace("_", "-")
        if self.publication_region_depth:
            if tag not in VOID_TAGS:
                self.publication_region_depth += 1
        elif "time-info" in identity.split():
            self.publication_region_depth = 1
            self.publication_region_parts = []
        is_explicit_target = any(
            marker.replace("_", "-") in identity for marker in TARGET_MARKERS
        )
        if self.target_depth:
            if tag not in VOID_TAGS:
                self.target_depth += 1
        elif is_explicit_target:
            self.target_depth = 1
            self.target_parts = []
        if self.target_depth and tag in BLOCK_TAGS | {"br"}:
            self.target_parts.append("\n")
        if self.capture_depth:
            if tag not in VOID_TAGS:
                self.capture_depth += 1
        elif tag == "article" or is_explicit_target:
            self.capture_depth = 1

        if self.capture_depth and tag == "br":
            self.raw_parts.append("\n")
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
        if self.ignored_depth:
            if tag in self.ignored_tags:
                # Optional closing tags in a hidden menu must not hide the
                # subsequent article after its enclosing container closes.
                index = len(self.ignored_tags) - 1 - self.ignored_tags[::-1].index(tag)
                del self.ignored_tags[index:]
                self.ignored_depth = len(self.ignored_tags)
            return
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.json_ld_depth:
            self.json_ld_parts.append("".join(self.json_ld_current))
            self.json_ld_current = []
            self.json_ld_depth = 0
            return
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return

        if self.publication_region_depth and tag not in VOID_TAGS:
            self.publication_region_depth -= 1
            if self.publication_region_depth == 0:
                self.publication_region_values.append(clean(" ".join(self.publication_region_parts)))
                self.publication_region_parts = []

        if self.target_depth:
            if tag in BLOCK_TAGS:
                self.target_parts.append("\n")
            if tag not in VOID_TAGS:
                self.target_depth -= 1
            if self.target_depth == 0:
                self.target_bodies.append("".join(self.target_parts))
                self.target_parts = []

        if self.capture_depth and tag in BLOCK_TAGS and self.block_depth:
            self.block_depth -= 1
            if self.block_depth == 0:
                value = clean(" ".join(self.block_parts))
                if value and (not self.blocks or value != self.blocks[-1]):
                    self.blocks.append(value)
                self.block_parts = []
            self.raw_parts.append("\n")
        if self.capture_depth and tag not in VOID_TAGS:
            self.capture_depth = max(0, self.capture_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.json_ld_depth:
            self.json_ld_current.append(data)
            return
        if self.ignored_depth:
            return
        if self.in_title:
            self.title_text.append(data)
        if self.capture_depth and not self.skip_depth:
            self.raw_parts.append(data)
        if self.target_depth and not self.skip_depth:
            self.target_parts.append(data)
        if self.publication_region_depth and not self.skip_depth:
            self.publication_region_parts.append(data)
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
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(value, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def normalized_title_tokens(value: str) -> list[str]:
    value = clean(value).lower().replace("’", "'")
    suffixes = "|".join(re.escape(item) for item in PUBLISHER_TITLE_SUFFIXES)
    value = re.sub(rf"\s+-\s+(?:{suffixes}|the white house)\s*$", "", value, flags=re.I)
    tokens = re.findall(r"[a-z0-9가-힣]+", value)
    return [token for token in tokens if token not in TITLE_STOPWORDS and len(token) > 1]


def strip_publisher_title_suffix(value: str) -> str:
    suffixes = "|".join(re.escape(item) for item in PUBLISHER_TITLE_SUFFIXES)
    return clean(re.sub(rf"\s+-\s+(?:{suffixes}|the white house)\s*$", "", value, flags=re.I))


def news_article_json_ld(parts: list[str], preferred_title: str = "") -> dict:
    articles = []

    def walk(value):
        if isinstance(value, dict):
            article_type = value.get("@type")
            types = article_type if isinstance(article_type, list) else [article_type]
            if any(str(item).lower() in {"article", "newsarticle", "reportagenewsarticle"} for item in types):
                if value.get("headline") or value.get("articleBody"):
                    articles.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for part in parts:
        try:
            walk(json.loads(part))
        except (json.JSONDecodeError, TypeError):
            continue
    if preferred_title:
        articles = [item for item in articles if titles_align(preferred_title, str(item.get("headline") or ""))]
    return max(articles, key=lambda item: len(str(item.get("articleBody") or "")), default={})


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


def trim_article_footer(body: str) -> str:
    """A publisher's related-story area is not evidence for the linked article."""
    footer = re.search(
        r"(?im)^\s*(?:copyright\s*(?:©|\(c\))|"
        r"\[?저작권자\s*[©ⓒ]|많이\s*본\s*(?:뉴스|기사|사진)|"
        r"관련\s*기사\s*$|추천\s*기사\s*$)",
        body,
    )
    return body[:footer.start()].strip() if footer else body.strip()


def extract_article_detail(html_text: str, listing_title: str = "") -> dict:
    parser = ArticleHTMLParser()
    try:
        parser.feed(html_text or "")
        parser.close()
    except Exception:
        return {
            "title": "",
            "abstract": "",
            "body": "",
            "published_kst": "",
            "title_aligned": False,
            "body_verified": False,
        }

    identity_title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or listing_title
    structured = news_article_json_ld(parser.json_ld_parts, identity_title)
    title = strip_publisher_title_suffix(
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or structured.get("headline")
        or " ".join(parser.title_text)
    )
    abstract = clean(
        parser.meta.get("og:description")
        or parser.meta.get("description")
        or structured.get("description")
    )
    body = "\n".join(parser.blocks)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    raw_body = "\n".join(
        clean(part)
        for part in re.split(r"\n+", "".join(parser.raw_parts))
        if clean(part)
    )
    raw_body = re.sub(r"\n{3,}", "\n\n", raw_body).strip()
    if len(raw_body) > len(body) and len(body) < 180:
        body = raw_body
    target_bodies = [
        "\n".join(clean(line) for line in value.splitlines() if clean(line))
        for value in parser.target_bodies
    ]
    explicit_body = max(target_bodies, key=len, default="")
    structured_body = clean(structured.get("articleBody"))
    # Explicit article text wins over longer publisher navigation/recommendations.
    if len(explicit_body) >= 180:
        body = explicit_body
    elif len(structured_body) >= 180:
        body = structured_body
    body = trim_article_footer(body)
    visible_published = next((
        match.group(1)
        for value in parser.publication_region_values
        if (match := re.search(r"입력\s*:?\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", value))
    ), "")
    published = parse_published(
        parser.meta.get("article:published_time")
        or parser.meta.get("date")
        or parser.meta.get("dc.date.issued")
        or structured.get("datePublished")
        or (parser.time_values[0] if parser.time_values else "")
        or visible_published
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

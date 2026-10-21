"""텔레그램 알림의 공식 게시일·수정일·시행일과 검색 노출일을 분리한다.

발행사 원문에서 확인한 날짜만 '원문 게시일'로 표시한다.
RSS pubDate는 발견·재색인 시각일 수 있으므로 검증 없이 발표일로 승격하지 않는다.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
_DATE_TEXT = r"20\d{2}\s*(?:[-./]|년)\s*\d{1,2}\s*(?:[-./]|월)\s*\d{1,2}\s*(?:일)?"
_ARTICLE_TYPES = {"NewsArticle", "Article", "Report", "PressRelease", "BlogPosting"}

_PUBLISHED_META = (
    ('meta[property="article:published_time"]', "content"),
    ('meta[name="article:published_time"]', "content"),
    ('meta[property="og:article:published_time"]', "content"),
    ('meta[name="datePublished"]', "content"),
    ('meta[itemprop="datePublished"]', "content"),
    ('meta[property="datePublished"]', "content"),
)
_MODIFIED_META = (
    ('meta[property="article:modified_time"]', "content"),
    ('meta[name="article:modified_time"]', "content"),
    ('meta[name="dateModified"]', "content"),
    ('meta[itemprop="dateModified"]', "content"),
    ('meta[property="og:updated_time"]', "content"),
)


def parse_timestamp(value: str | None, *, default_tz: timezone = KST) -> datetime | None:
    """명시적 UTC 오프셋은 유지하고 한국 기관의 날짜만 표기는 KST로 해석."""
    value = str(value or "").strip()
    if not value:
        return None
    value = re.sub(r"\s+(KST|한국표준시)$", "+09:00", value, flags=re.I)
    value = re.sub(r"\s+UTC$", "+00:00", value, flags=re.I)
    candidate = None
    try:
        candidate = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    if candidate is None:
        try:
            candidate = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            pass
    if candidate is None:
        match = re.fullmatch(
            r"\s*(20\d{2})\s*(?:[-./]|년)\s*(\d{1,2})\s*(?:[-./]|월)\s*(\d{1,2})"
            r"(?:일)?\.?\s*(?:(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*",
            value,
        )
        if match:
            try:
                year, month, day = map(int, match.group(1, 2, 3))
                hour, minute, second = (int(part or 0) for part in match.group(4, 5, 6))
                candidate = datetime(year, month, day, hour, minute, second)
            except ValueError:
                return None
    if candidate is None:
        return None
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=default_tz)
    return candidate.astimezone(KST)


def korean_date(value: str | None) -> str:
    dt = parse_timestamp(value)
    return f"{dt.year}년 {dt.month}월 {dt.day}일" if dt else "날짜 확인 불가"


def _valid_published(raw: str, now: datetime) -> str:
    dt = parse_timestamp(raw)
    if not dt:
        return ""
    local_now = now.astimezone(KST)
    if dt.year < 2015 or dt > local_now + timedelta(days=1):
        return ""
    return dt.isoformat()


def _first_meta(soup: BeautifulSoup, selectors: tuple, now: datetime) -> str:
    for selector, attribute in selectors:
        for node in soup.select(selector):
            stamp = _valid_published(node.get(attribute, ""), now)
            if stamp:
                return stamp
    return ""


def _article_jsonld_dates(soup: BeautifulSoup, now: datetime) -> tuple[str, str]:
    found: list[tuple[str, str]] = []

    def walk(data: Any) -> None:
        if isinstance(data, list):
            for item in data:
                walk(item)
            return
        if not isinstance(data, dict):
            return
        kind = data.get("@type")
        kinds = [kind] if isinstance(kind, str) else kind if isinstance(kind, list) else []
        if any(str(t).split("/")[-1] in _ARTICLE_TYPES for t in kinds):
            published = _valid_published(str(data.get("datePublished") or ""), now)
            modified = _valid_published(str(data.get("dateModified") or ""), now)
            if published or modified:
                found.append((published, modified))
        if "@graph" in data:
            walk(data["@graph"])

    for node in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(node.string or node.get_text() or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return next((entry for entry in found if entry[0]), ("", ""))


def extract_original_dates(page_html: str, *, now: datetime | None = None) -> dict[str, str]:
    """본문·발행사 메타정보에서 입증되는 게시·수정·시행 날짜만 추출한다."""
    now = now or datetime.now(timezone.utc)
    soup = BeautifulSoup(page_html, "html.parser")
    published = _first_meta(soup, _PUBLISHED_META, now)
    modified = _first_meta(soup, _MODIFIED_META, now)
    source = "원문 메타정보" if published else ""

    json_published, json_modified = _article_jsonld_dates(soup, now)
    if not published and json_published:
        published = json_published
        source = "원문 구조화자료"
    if not modified:
        modified = json_modified

    if not published:
        for node in soup.select('time[datetime], time[pubdate]'):
            parent_name = str(node.parent.get("class", "")).lower() if node.parent else ""
            attrs = " ".join(f"{k}={v}" for k, v in node.attrs.items()).lower()
            if "publish" not in attrs + parent_name and "date" not in attrs + parent_name:
                continue
            stamp = _valid_published(node.get("datetime") or node.get_text(" ", strip=True), now)
            if stamp:
                published = stamp
                source = "원문 날짜 표시"
                break

    # 공공기관 게시판: 라벨과 바로 붙은 날짜만 허용. 본문에 등장하는 목표연도나
    # 법령 시행일을 무작위로 '발표일'로 가져오지 않는다.
    text = " ".join(soup.get_text(" ", strip=True).split())
    if not published:
        labelled = re.search(
            r"(?:등록일자|작성일자|등록일|작성일|게시일|게재일|공고일)\s*[:：]?\s*"
            r"(" + _DATE_TEXT + r")",
            text,
            flags=re.I,
        )
        if labelled:
            stamp = _valid_published(labelled.group(1), now)
            if stamp:
                published = stamp
                source = "원문 게시일 표기"

    effective = ""
    match = re.search(r"(?:\[시행\s*|시행일\s*[:：]?\s*)(" + _DATE_TEXT + r")", text)
    if match:
        parsed = parse_timestamp(match.group(1))
        if parsed:
            effective = parsed.isoformat()

    # 보도자료 수정일은 원문 게시일과 별도로 보존한다.
    return {
        "published": published,
        "modified": modified if modified and modified != published else "",
        "effective": effective,
        "published_source": source,
    }


def timeline_lines(
    record: dict[str, str],
    *,
    rss_published: str = "",
    include_rss_when_unverified: bool = True,
) -> list[str]:
    """원문 게시일과 RSS 노출일·시행일을 서로 다른 항목으로 표시."""
    lines: list[str] = []
    published = record.get("published", "")
    modified = record.get("modified", "")
    effective = record.get("effective", "")
    if published:
        lines.append(f"원문 게시일  {korean_date(published)}")
    else:
        lines.append("원문 게시일  확인 불가")
    if modified:
        lines.append(f"원문 수정일  {korean_date(modified)}")
    if effective:
        lines.append(f"법령 시행일  {korean_date(effective)}")
    if not published and include_rss_when_unverified and parse_timestamp(rss_published):
        lines.append(f"검색 노출일(발표일 아님)  {korean_date(rss_published)}")
    return lines


def verified_age_days(record: dict[str, str], now: datetime | None = None) -> float | None:
    published = parse_timestamp(record.get("published", ""))
    if not published:
        return None
    now = now or datetime.now(timezone.utc)
    return (now.astimezone(KST) - published).total_seconds() / 86400

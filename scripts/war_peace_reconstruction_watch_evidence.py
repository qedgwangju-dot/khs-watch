"""Publisher identity, publication metadata, and reproducible alert receipts."""
from __future__ import annotations

import datetime as dt
from email.utils import format_datetime
import hashlib
import html
from html.parser import HTMLParser
import json
import os
import re
import urllib.parse
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


def _host(url):
    return (urllib.parse.urlparse(url or '').hostname or '').lower().removeprefix('www.')


def publisher_matches(row, url):
    expected = _host(row.get('source_url'))
    if not expected:
        direct = _host(row.get('discovery_url') or row.get('link'))
        if direct and direct not in ('news.google.com', 'bing.com'):
            expected = direct
    if not expected:
        known = {'mbc': 'imbc.com', 'all israel news': 'allisraelnews.com',
                 '토큰포스트': 'tokenpost.kr', '파이낸셜뉴스': 'fnnews.com'}
        source = str(row.get('source') or '').lower()
        expected = next((host for label, host in known.items() if label in source), '')
    actual = _host(url)
    return bool(expected and (actual == expected or actual.endswith('.' + expected)))


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.scripts = []
        self._json = False
        self._script = []
        self.visible = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[(attrs.get('property') or attrs.get('name') or '').lower()] = attrs.get('content', '')
        if tag in ('script', 'style', 'noscript'):
            self._skip += 1
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self._json, self._script = True, []

    def handle_endtag(self, tag):
        if tag == 'script' and self._json:
            self.scripts.append(''.join(self._script))
            self._json = False
        if tag in ('script', 'style', 'noscript'):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._json:
            self._script.append(data)
        if not self._skip:
            self.visible.append(data)


def _iso(raw, *, korean=False):
    try:
        value = dt.datetime.fromisoformat(str(raw).strip().replace('Z', '+00:00'))
        if value.tzinfo is None:
            if not korean:
                return None
            value = value.replace(tzinfo=KST)
        return value.astimezone(KST)
    except (ValueError, TypeError):
        return None


def article_metadata(page, url):
    parser = Metadata()
    parser.feed(page or '')
    korean = _host(url).endswith(('.kr', '.imbc.com')) or _host(url) in ('fnnews.com', 'imbc.com')
    title = parser.meta.get('og:title', '')
    candidates = []
    for key in ('article:published_time', 'datepublished', 'pubdate', 'nextweb:createdate', 'dd:published_time'):
        value = _iso(parser.meta.get(key), korean=korean)
        if value:
            candidates.append((key, value))

    def visit(value):
        nonlocal title
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            kinds = value.get('@type') or []
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if any('Article' in str(kind) for kind in kinds):
                title = title or value.get('headline', '')
                stamp = _iso(value.get('datePublished'), korean=korean)
                if stamp:
                    candidates.append(('jsonld:datePublished', stamp))
            if '@graph' in value:
                visit(value['@graph'])

    for script in parser.scripts:
        try:
            visit(json.loads(script))
        except (ValueError, TypeError):
            continue
    visible = re.sub(r'\s+', ' ', ' '.join(parser.visible))
    if korean:
        match = re.search(r'입력\s*(20\d{2})[.\-/](\d{2})[.\-/](\d{2})\s*(\d{2}:\d{2})', visible)
        if match:
            stamp = _iso('-'.join(match.group(1, 2, 3)) + 'T' + match.group(4), korean=True)
            candidates.append(('visible:입력', stamp))
    stamps = [stamp for _, stamp in candidates]
    conflict = bool(stamps and (max(stamps) - min(stamps)).total_seconds() > 60)
    return {'title': html.unescape(str(title)),
            'publication_status': 'conflict' if conflict else 'verified' if stamps else 'unavailable',
            'published_at_kst': stamps[0].isoformat() if stamps and not conflict else None,
            'publication_candidates': [{'field': key, 'at_kst': stamp.isoformat()} for key, stamp in candidates]}


def title_matches(row, headline):
    def tokens(value):
        value = html.unescape(str(value or '')).lower()
        # Strip only a publisher suffix. A headline clause after a dash may
        # carry the very event/stage difference we need to verify.
        suffix = re.search(r'\s+[-|]\s+([^-|]+)$', value)
        source = str(row.get('source') or '').strip().lower()
        if suffix and suffix.group(1).strip() == source:
            value = value[:suffix.start()]
        return re.findall(r'[^\W_]+', value, re.UNICODE)
    a, b = tokens(row.get('title_original') or row.get('title')), tokens(headline)
    # A bag of words accepts "Russia attacks Ukraine" as the same headline as
    # "Ukraine attacks Russia", and can erase short negations. Verification
    # needs the same ordered words; shortened/edited headlines remain unverified.
    return bool(a and b and a == b)


def attach_article(row, url, page, body):
    metadata = article_metadata(page, url)
    if not publisher_matches(row, url) or not title_matches(row, metadata['title']):
        return False
    row['article_text'] = body
    row['body_verified'] = True
    row['resolved_url'] = url
    row['discovery_url'] = row.get('discovery_url') or row.get('link')
    row['link'] = url
    row['source_metadata'] = metadata
    if metadata['published_at_kst']:
        row['rss_published'] = row.get('rss_published') or row.get('published')
        row['published'] = format_datetime(dt.datetime.fromisoformat(metadata['published_at_kst']))
    return True


def alert_receipt(items, markets, now, text, market_status=None):
    urls = {html.unescape(url) for url in re.findall(r'<a href="([^"]+)"', text)}
    keys = ('id', 'title_original', 'title_ko', 'description', 'source', 'source_url', 'link', 'discovery_url',
            'resolved_url', 'published', 'rss_published', 'source_metadata', 'score', 'tags',
            'body_checked', 'body_verified', 'signals_ko', 'forced_tags', 'classification_color',
            'non_military_kind', 'render_withheld', 'duplicate_of', 'duplicate_basis')
    articles = []
    for row in items:
        item = {key: row.get(key) for key in keys if key in row}
        item['body_verified'] = bool(row.get('body_verified'))
        publication_status = (row.get('source_metadata') or {}).get('publication_status')
        item['publication_basis'] = ('publisher' if publication_status == 'verified' else
                                     'publisher_conflict' if publication_status == 'conflict' else 'discovery_feed')
        item['rendered'] = not row.get('render_withheld') and bool({row.get('link'), row.get('resolved_url')} & urls)
        item['article_text_sha256'] = hashlib.sha256(str(row.get('article_text') or '').encode()).hexdigest()
        articles.append(item)
    return {'schema_version': 1, 'queried_at_kst': now.isoformat(),
            'run_id': os.getenv('GITHUB_RUN_ID'), 'code_sha': os.getenv('WAR_WATCH_CODE_SHA') or os.getenv('GITHUB_SHA'),
            'alert_sha256': hashlib.sha256(text.strip().encode()).hexdigest(),
            'articles': articles, 'markets': markets, 'market_source_status': market_status or {}}

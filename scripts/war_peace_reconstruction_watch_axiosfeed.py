#!/usr/bin/env python3
import argparse
import html as html_lib
import re
import xml.etree.ElementTree as ET

import war_peace_reconstruction_watch_winter as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_google_news = watch.google_news

AXIOS_FEED = 'https://api.axios.com/feed/'
AXIOS_WORLD = 'https://www.axios.com/world'
AXIOS_SENTINEL = '__AXIOS_DIRECT_WAR_PEACE__'
watch.QUERIES = [AXIOS_SENTINEL] + list(watch.QUERIES)


def _node_text(node, name):
    if node is None:
        return ''
    child = node.find(name)
    if child is None:
        child = node.find(f'{{*}}{name}')
    return watch.clean(child.text if child is not None and child.text else '')


def axios_direct_feed():
    """Axios 공개 RSS를 직접 읽어 검색엔진 색인 지연을 우회한다."""
    try:
        root = ET.fromstring(watch.req(AXIOS_FEED, 10))
    except Exception:
        return []

    rows = []
    # RSS 2.0
    for item in root.findall('.//item')[:80]:
        title = _node_text(item, 'title')
        link = _node_text(item, 'link') or _node_text(item, 'guid')
        pub = _node_text(item, 'pubDate') or _node_text(item, 'date')
        desc = _node_text(item, 'description') or _node_text(item, 'summary')
        text = (title + ' ' + desc).lower()
        if not any(k in text for k in ('ukraine', 'russia', 'zelensky', 'zelenskiy', 'putin', 'witkoff', 'kushner', '우크라이나', '러시아', '젤렌스키', '푸틴')):
            continue
        rows.append({
            'title': title,
            'title_original': title,
            'link': link,
            'published': pub,
            'source': 'Axios',
            'description': desc,
            'feed': 'Axios 직접 RSS',
        })

    # Atom fallback
    if not rows:
        for entry in root.findall('.//{*}entry')[:80]:
            title = _node_text(entry, 'title')
            pub = _node_text(entry, 'published') or _node_text(entry, 'updated')
            desc = _node_text(entry, 'summary') or _node_text(entry, 'content')
            link = ''
            ln = entry.find('{*}link')
            if ln is not None:
                link = watch.clean(ln.attrib.get('href', ''))
            text = (title + ' ' + desc).lower()
            if not any(k in text for k in ('ukraine', 'russia', 'zelensky', 'zelenskiy', 'putin', 'witkoff', 'kushner', '우크라이나', '러시아', '젤렌스키', '푸틴')):
                continue
            rows.append({
                'title': title,
                'title_original': title,
                'link': link,
                'published': pub,
                'source': 'Axios',
                'description': desc,
                'feed': 'Axios 직접 RSS',
            })
    return rows


def axios_world_page():
    """Axios World 첫 화면에서 RSS 요약에 빠진 정상회담 날짜·장소 문구를 보완한다."""
    try:
        page = watch.req(AXIOS_WORLD, 12).decode('utf-8', errors='ignore')
    except Exception:
        return []

    raw = html_lib.unescape(page)
    low = raw.lower()
    rows = []
    needles = (
        'trump to meet with zelensky as russia-ukraine attacks intensify',
        'trump to meet with zelenskiy as russia-ukraine attacks intensify',
    )
    for needle in needles:
        start = 0
        while True:
            pos = low.find(needle, start)
            if pos == -1:
                break
            left = max(0, pos - 3500)
            right = min(len(raw), pos + 5000)
            chunk = raw[left:right]
            plain = watch.clean(re.sub(r'<[^>]+>', ' ', chunk))
            plow = plain.lower()
            if not ('trump' in plow and ('zelensky' in plow or 'zelenskiy' in plow)):
                start = pos + len(needle)
                continue
            if not any(k in plow for k in ('tuesday', '화요일', 'new york', 'un general assembly', 'united nations general assembly')):
                start = pos + len(needle)
                continue

            link = ''
            hrefs = re.findall(r'href=["\']([^"\']+)["\']', chunk, flags=re.I)
            for href in hrefs:
                if 'trump-zelensky' in href or 'trump-zelenskiy' in href:
                    link = href
                    break
            if link.startswith('/'):
                link = 'https://www.axios.com' + link
            elif not link.startswith('http'):
                link = 'https://www.axios.com/2026/09/20/trump-zelensky-meeting-russia-ukraine-war-talks'

            # 실제 일정 판정에 필요한 앞뒤 문장만 유지한다.
            m = re.search(
                r'([^.!?]{0,260}(?:tuesday|화요일)[^.!?]{0,420}(?:new york|un general assembly|united nations general assembly)[^.!?]{0,420})',
                plain,
                flags=re.I,
            )
            desc = m.group(1).strip() if m else plain[:1400]
            rows.append({
                'title': 'Trump to meet with Zelensky as Russia-Ukraine attacks intensify',
                'title_original': 'Trump to meet with Zelensky as Russia-Ukraine attacks intensify',
                'link': link,
                'published': '',
                'source': 'Axios',
                'description': desc,
                'article_text': desc,
                'feed': 'Axios World 직접',
                'deep_signal': True,
            })
            return rows
    return rows


def google_news_with_axios(query):
    # Axios 공개 RSS를 전용 센티널에서 직접 읽어 검색엔진 색인 지연·쿼리 순서 변경에 영향받지 않게 한다.
    if query == AXIOS_SENTINEL:
        return axios_direct_feed() + axios_world_page(), None
    rows, err = _prev_google_news(query)
    return rows, err


watch.google_news = google_news_with_axios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    ap.add_argument('--telegram-test', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == '__main__':
    main()

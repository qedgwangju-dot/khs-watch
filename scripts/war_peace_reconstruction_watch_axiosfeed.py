#!/usr/bin/env python3
import argparse
import xml.etree.ElementTree as ET

import war_peace_reconstruction_watch_winter as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_google_news = watch.google_news

AXIOS_FEED = 'https://api.axios.com/feed/'


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


def google_news_with_axios(query):
    rows, err = _prev_google_news(query)
    # 첫 Axios 검색축에서만 직접 RSS를 합쳐 중복 네트워크 호출을 막는다.
    if query == prev.WINTER_QUERIES[0]:
        rows = axios_direct_feed() + rows
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

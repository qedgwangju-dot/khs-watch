from __future__ import annotations

import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

import halozyme_legal_watch_v2 as base

# 미국 공식/영문 검색뿐 아니라 국내 보도가 먼저 뜨는 경우도 잡는다.
base.SEARCHES.extend([
    '할로자임 MSD 특허 무효 PGR',
    '할로자임 MDASE 특허 PTAB',
    '알테오젠 할로자임 특허 분쟁 MSD',
    'Halozyme MSD 특허심판원 무효',
])


def rss(query: str, engine: str) -> list[dict]:
    urls: list[tuple[str, str]] = []
    if engine == 'Google 뉴스':
        # 같은 검색어를 미국·한국 뉴스 색인에서 동시에 확인한다.
        urls.append(('Google 뉴스(미국)', 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
            'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'
        })))
        urls.append(('Google 뉴스(한국)', 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
            'q': query, 'hl': 'ko', 'gl': 'KR', 'ceid': 'KR:ko'
        })))
    else:
        urls.append(('Bing 웹', 'https://www.bing.com/search?' + urllib.parse.urlencode({'q': query, 'format': 'rss'})))

    out: list[dict] = []
    for label, url in urls:
        root = ET.fromstring(base.fetch(url))
        for n in root.findall('.//item')[:30]:
            title = html.unescape((n.findtext('title') or '').strip())
            link = base.clean_url((n.findtext('link') or '').strip())
            desc = re.sub(r'<[^>]+>', ' ', html.unescape(n.findtext('description') or ''))
            pub = (n.findtext('pubDate') or '').strip()
            if link:
                out.append({'engine': label, 'title': title, 'url': link, 'description': desc, 'published': pub})
    # 같은 URL은 여기서 한 번만 남긴다.
    unique: dict[str, dict] = {}
    for item in out:
        unique.setdefault(item['url'], item)
    return list(unique.values())


base.rss = rss


def main() -> int:
    # 새 검색축을 처음 도입하는 실행에서는 과거 기사/기존 절차를 기준선으로만 소비하고
    # Telegram 재탕 알림을 보내지 않는다. 그 다음 실행부터 새 사건만 발송한다.
    state = base.load_state()
    first_v3 = not bool(state.get('legal_v3_initialized'))
    original_send = base.send
    if first_v3:
        base.send = lambda token, chat, text: 0
    try:
        rc = base.main()
    finally:
        base.send = original_send

    try:
        state2 = json.loads(base.STATE.read_text(encoding='utf-8'))
    except Exception:
        state2 = {}
    state2['legal_v3_initialized'] = True
    state2['search_regions'] = ['미국 뉴스', '한국 뉴스', 'Bing 웹']
    base.STATE.write_text(json.dumps(state2, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'halozyme_legal_v3': 'ok', 'baseline_only': first_v3}, ensure_ascii=False))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())

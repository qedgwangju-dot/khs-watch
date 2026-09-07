#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "disaster_reconstruction_watch_state.json"
OUT = ROOT / "out"
ALERT = OUT / "disaster_reconstruction_alert.txt"
PENDING = OUT / "disaster_reconstruction_pending.json"
SUMMARY = OUT / "disaster_reconstruction_watch.md"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    'South Korea Nepal post-flood reconstruction support Cho Hyun when:48h',
    'site:mofa.go.kr 네팔 홍수 재건 복구 지원 조현 when:48h',
    'site:mofa.gov.np South Korea Nepal reconstruction rehabilitation flood when:48h',
    '(South Korea OR Republic of Korea OR 한국) (reconstruction OR rehabilitation OR rebuilding OR 재건 OR 복구) (flood OR earthquake OR typhoon OR cyclone OR landslide OR wildfire OR tsunami OR 홍수 OR 지진 OR 태풍 OR 산사태 OR 산불 OR 재난) when:24h',
    '(KOICA OR EDCF OR 한국수출입은행 OR 한국국제협력단) (재건 OR 복구 OR reconstruction OR rehabilitation) (홍수 OR 지진 OR 태풍 OR 재난 OR disaster) when:72h',
    '(World Bank OR ADB OR Asian Development Bank) (reconstruction OR rehabilitation) (South Korea OR Korean OR 한국) disaster when:72h',
    '(Korean company OR 한국 기업 OR 한국기업) (reconstruction OR rebuilding OR 재건 OR 복구) (flood OR earthquake OR typhoon OR disaster OR 홍수 OR 지진 OR 태풍 OR 재난) when:72h',
]

TRUSTED = (
    'Ministry of Foreign Affairs', '외교부', 'mofa.go.kr', 'mofa.gov.np', 'Reuters',
    'Associated Press', 'AP News', 'Yonhap', '연합뉴스', 'World Bank', 'Asian Development Bank',
    'ADB', 'KOICA', '한국국제협력단', 'EDCF', '한국수출입은행', 'NDTV Profit', 'Radio Nepal'
)

DISASTER = (
    'flood', 'floods', 'earthquake', 'typhoon', 'cyclone', 'landslide', 'wildfire', 'tsunami', 'disaster',
    '홍수', '지진', '태풍', '사이클론', '산사태', '산불', '쓰나미', '재난'
)
RECON = (
    'reconstruction', 'rehabilitation', 'rebuilding', 'recovery', 'restore', 'restoration',
    '재건', '복구', '복원', '재해복구', '피해복구'
)
KOREA = ('south korea', 'republic of korea', 'korea', '한국', '대한민국', 'koica', 'edcf', '조현')
MONEY = ('million', 'billion', 'trillion', 'usd', 'npr', '달러', '억원', '조원', '예산', '기금', 'fund')
TENDER = ('tender', 'bid', 'bidding', 'contract', 'award', 'epc', 'mou', '입찰', '수주', '본계약', '업무협약')
INFRA = ('road', 'bridge', 'hydropower', 'electricity', 'energy', 'telecom', 'housing', 'school', 'hospital',
         '도로', '교량', '수력발전', '전력', '에너지', '통신', '주택', '학교', '병원')


def req(url, timeout=20):
    headers = {'User-Agent': 'Mozilla/5.0 khs-disaster-reconstruction-watch/1.0'}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read()


def clean(s):
    s = html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))
    return re.sub(r'\s+', ' ', s).strip()


def has_korean(text):
    return bool(re.search(r'[가-힣]', text or ''))


def translate_ko(text):
    text = clean(text)
    if not text or has_korean(text):
        return text
    url = ('https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q=' + urllib.parse.quote(text))
    for _ in range(2):
        try:
            data = json.loads(req(url, 12).decode('utf-8'))
            out = clean(''.join(p[0] for p in data[0] if p and p[0]))
            if out and has_korean(out):
                return out
        except Exception:
            pass
    return '영문 기사 번역이 일시적으로 지연됨 — 원문 확인 필요'


def parse_pub(pub):
    try:
        d = parsedate_to_datetime(pub)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(KST)
    except Exception:
        return None


def age_minutes(row, now):
    p = parse_pub(row.get('published', ''))
    if not p:
        return None
    return max(0, int((now - p).total_seconds() // 60))


def google_news(query):
    q = urllib.parse.quote(query)
    url = f'https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko'
    try:
        root = ET.fromstring(req(url))
    except Exception:
        return []
    rows = []
    for item in root.findall('./channel/item')[:30]:
        source = item.find('source')
        rows.append({
            'title_original': clean(item.findtext('title')),
            'link': clean(item.findtext('link')),
            'published': clean(item.findtext('pubDate')),
            'source': clean(source.text if source is not None else ''),
            'description': clean(item.findtext('description')),
            'feed': 'Google News',
        })
    return rows


def bing_news(query):
    q = urllib.parse.quote(query.replace(' when:24h', '').replace(' when:48h', '').replace(' when:72h', ''))
    url = f'https://www.bing.com/news/search?q={q}&format=rss&setlang=ko-kr'
    try:
        root = ET.fromstring(req(url))
    except Exception:
        return []
    rows = []
    for item in root.findall('./channel/item')[:20]:
        rows.append({
            'title_original': clean(item.findtext('title')),
            'link': clean(item.findtext('link')),
            'published': clean(item.findtext('pubDate')),
            'source': clean(item.findtext('source') or 'Bing News'),
            'description': clean(item.findtext('description')),
            'feed': 'Bing News',
        })
    return rows


def text_of(row):
    return (row.get('title_original', '') + ' ' + row.get('description', '')).lower()


def classify(row):
    text = text_of(row)
    tags = []
    if any(k in text for k in DISASTER): tags.append('재난')
    if any(k in text for k in RECON): tags.append('재건·복구')
    if any(k in text for k in KOREA): tags.append('한국')
    if any(k in text for k in MONEY): tags.append('재원')
    if any(k in text for k in TENDER): tags.append('입찰·수주')
    if any(k in text for k in INFRA): tags.append('인프라')
    return sorted(set(tags))


def relevant(row):
    text = text_of(row)
    disaster = any(k in text for k in DISASTER)
    recon = any(k in text for k in RECON)
    korea = any(k in text for k in KOREA)
    # 전쟁 재건은 별도 감시로 보내고 이 알림에서는 제외
    war = any(k in text for k in ('ukraine', 'russia', 'iran', 'gaza', 'war', '우크라이나', '러시아', '이란', '전쟁'))
    return disaster and recon and korea and not war


def score(row, now):
    if not relevant(row):
        return -100
    text = text_of(row)
    src = (row.get('source') or '').lower()
    s = 20
    if any(t.lower() in src for t in TRUSTED): s += 10
    if any(k in text for k in ('pledges support', 'support reconstruction', 'support for reconstruction', '재건 지원', '복구 지원')): s += 10
    if any(k in text for k in MONEY): s += 5
    if any(k in text for k in TENDER): s += 8
    if any(k in text for k in INFRA): s += 4
    age = age_minutes(row, now)
    if age is not None:
        if age <= 30: s += 12
        elif age <= 120: s += 9
        elif age <= 360: s += 6
        elif age <= 720: s += 3
        elif age > 2880: s -= 10
    return s


def item_id(row):
    key = re.sub(r'\W+', ' ', row.get('title_original', '').lower()).strip()
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]


def country_label(row):
    text = text_of(row)
    mapping = [
        ('nepal', '네팔'), ('네팔', '네팔'), ('japan', '일본'), ('philippines', '필리핀'),
        ('indonesia', '인도네시아'), ('vietnam', '베트남'), ('myanmar', '미얀마'), ('turkey', '튀르키예'),
        ('pakistan', '파키스탄'), ('bangladesh', '방글라데시'), ('india', '인도'), ('sri lanka', '스리랑카')
    ]
    for k, v in mapping:
        if k in text:
            return v
    return '해외 재난'


def phase_lines(row):
    text = text_of(row)
    out = []
    if any(k in text for k in ('pledges support', 'support reconstruction', 'support for reconstruction', '재건 지원', '복구 지원')):
        out.append('<b>단계:</b> 한국의 재건·복구 지원 의향 확인')
    if any(k in text for k in ('1 million', '$1 million', 'usd 1 million', '100만달러', '100만 달러')):
        out.append('<b>확정:</b> 긴급 인도지원 100만달러 — 재건 사업비와 별도')
    if any(k in text for k in ('44-member', '44 member', '44명', 'kdrt', '해외긴급구호대')):
        out.append('<b>현장:</b> 대한민국 해외긴급구호대 44명은 수색·구조 단계')
    if any(k in text for k in INFRA):
        out.append('<b>대상:</b> 도로·교량·전력·수력발전 등 인프라 피해 복구 여부 확인')
    if any(k in text for k in TENDER):
        out.append('<b>사업화:</b> 입찰·본계약·한국기업 실명 단계로 진입 여부 확인')
    return out[:3]


def freshness(row, now):
    age = age_minutes(row, now)
    if age is None:
        return '신규', '공개시각 확인 필요'
    pub = parse_pub(row.get('published', ''))
    if age <= 30: level = '속보'
    elif age <= 180: level = '신규'
    else: level = '후속'
    return level, f'{pub:%H:%M} KST · 🟥 <b>{age}분 전</b>'


def source_label(row):
    src = clean(row.get('source') or row.get('feed') or '원문')
    return src[:32] or '원문'


def build_alert(items, now):
    lines = ['<b>재난·재건 웹감시</b>', f'조회 {now:%Y-%m-%d %H:%M} KST', '', '<b>핵심 변화</b>']
    for i, row in enumerate(items[:5], 1):
        level, time_str = freshness(row, now)
        title_ko = translate_ko(row.get('title_original', ''))
        country = country_label(row)
        link = html.escape(row.get('link', ''), quote=True)
        src = html.escape(source_label(row), quote=False)
        lines += [
            f'[{level}] <b>{i}. {country}</b>',
            html.escape(title_ko, quote=False),
        ]
        for p in phase_lines(row):
            lines.append('- ' + p)
        tags = ' · '.join(row.get('tags', []))
        meta = f'{time_str}' + (f' · {tags}' if tags else '') + f' · <a href="{link}">{src} 원문</a>'
        lines.append(meta)
        lines.append('')

    lines += [
        '<b>재건 단계</b>',
        '- <b>확정:</b> 정부 지원금·구호물자·재건 지원 의향',
        '- <b>미확정:</b> 별도 재건 사업비·발주처·입찰·한국기업 수주',
        '- <b>다음:</b> 피해평가 → 재원조달 → 사업목록 → 입찰 → 본계약',
    ]
    return '\n'.join(lines).strip()[:4000] + '\n'


def load_state():
    if not STATE.exists():
        return {'seen': [], 'updated_at': None}
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception:
        return {'seen': [], 'updated_at': None}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, PENDING):
        if p.exists(): p.unlink()

    now = dt.datetime.now(KST)
    rows = []
    for q in QUERIES:
        rows.extend(google_news(q))
        rows.extend(bing_news(q))

    dedup = {}
    for row in rows:
        iid = item_id(row)
        row['id'] = iid
        row['tags'] = classify(row)
        row['score'] = score(row, now)
        if row['score'] < 20:
            continue
        old = dedup.get(iid)
        if old is None or row['score'] > old['score']:
            dedup[iid] = row

    state = load_state()
    seen = set(state.get('seen', []))
    fresh = [x for x in dedup.values() if x['id'] not in seen]
    fresh.sort(key=lambda x: (x['score'], -(age_minutes(x, now) or 999999)), reverse=True)
    fresh = fresh[:5]

    SUMMARY.write_text(
        '# 재난·재건 웹감시\n\n' +
        f'- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n' +
        f'- 후보: {len(dedup)}건\n' +
        f'- 신규: {len(fresh)}건\n', encoding='utf-8'
    )

    if not fresh:
        return

    ALERT.write_text(build_alert(fresh, now), encoding='utf-8')
    PENDING.write_text(json.dumps({'ids': [x['id'] for x in fresh]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def finalize():
    if not PENDING.exists():
        return
    state = load_state()
    pending = json.loads(PENDING.read_text(encoding='utf-8'))
    seen = list(dict.fromkeys(state.get('seen', []) + pending.get('ids', [])))[-1000:]
    STATE.write_text(json.dumps({'seen': seen, 'updated_at': dt.datetime.now(KST).isoformat(timespec='seconds')}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    PENDING.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        finalize()
    else:
        run()


if __name__ == '__main__':
    main()

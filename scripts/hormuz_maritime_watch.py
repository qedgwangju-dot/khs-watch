from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

STATE_PATH = Path('data/hormuz_maritime_watch_state.json')
OUT_DIR = Path('out')
OUT_ALERT = OUT_DIR / 'hormuz_maritime_watch_telegram.txt'
OUT_STATUS = OUT_DIR / 'hormuz_maritime_watch_status.md'
OUT_PENDING = OUT_DIR / 'hormuz_maritime_watch_pending_state.json'
OUT_DEBUG = OUT_DIR / 'hormuz_maritime_watch_debug.json'
KST = ZoneInfo('Asia/Seoul')
UA = 'Mozilla/5.0 (compatible; KHS-Hormuz-Maritime-Watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'
TIMEOUT = 25
MAX_BODY = 6_000_000

UKMTO_QUERIES = [
    'site:ukmto.org "UKMTO WARNING" "Strait of Hormuz"',
    'site:ukmto.org "UKMTO WARNING" tanker Khasab',
    'site:ukmto.org "UKMTO WARNING" tanker Oman projectile',
    'site:ukmto.org "UKMTO WARNING" tanker Fujairah',
    'site:ukmto.org "UKMTO ADVISORY" "Strait of Hormuz"',
]
NEWS_QUERIES = [
    'Strait of Hormuz tanker UKMTO when:3d',
    'Hormuz tanker projectile UKMTO when:3d',
    'Hormuz vessel attack UKMTO when:3d',
    'Hormuz tanker mine missile drone when:3d',
    'Hormuz shipping closure blockade tanker when:3d',
]
ALLOWED_NEWS_SOURCES = {
    'Reuters', 'Associated Press', 'AP News', 'U.S. Central Command', 'CENTCOM',
    'Oman News Agency', 'The Maritime Executive', 'Lloyd’s List', "Lloyd's List", 'TradeWinds',
}
GEO_TERMS = (
    'hormuz', 'khasab', 'fujairah', 'muscat', 'oman', 'arabian gulf',
    'gulf of oman', 'larak', 'mina saqr', 'ras tanura',
)
VESSEL_TERMS = ('tanker', 'vessel', 'ship', 'vlcc', 'merchant', 'carrier')
SECURITY_TERMS = (
    'projectile', 'attack', 'struck', 'hit', 'explosion', 'fire', 'mine',
    'missile', 'drone', 'uav', 'usv', 'seized', 'seizure', 'boarding',
    'stopped', 'blocked', 'blockade', 'closure', 'closed', 'escort',
    'suspicious activity', 'security incident', 'casualty', 'casualties',
)


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def fetch(url: str, *, accept: str = '*/*') -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': accept,
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise RuntimeError(f'response too large: {url}')
        return body, str(r.headers.get('Content-Type') or '').lower()


def clean_text(value: str) -> str:
    value = html.unescape(value or '')
    value = re.sub(r'<script\b[^>]*>.*?</script>', ' ', value, flags=re.I | re.S)
    value = re.sub(r'<style\b[^>]*>.*?</style>', ' ', value, flags=re.I | re.S)
    value = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def normalize(value: str) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip()).lower()


def relevant(text: str) -> bool:
    t = normalize(text)
    return (
        any(x in t for x in GEO_TERMS)
        and any(x in t for x in VESSEL_TERMS)
        and any(x in t for x in SECURITY_TERMS)
    )


def warning_no(text: str) -> str | None:
    for pat in (
        r'\b(?:warning|ukmto)\s*[-:#]?\s*(\d{2,3})\s*[-_/]\s*(26)\b',
        r'\bukmto\s+#?(\d{2,3})\b',
    ):
        m = re.search(pat, text, flags=re.I)
        if m:
            return f'{int(m.group(1)):03d}-26'
    return None


def sha_text(text: str) -> str:
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()[:16]


def source_host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or '').lower().lstrip('www.')


def bing_rss(query: str) -> list[dict[str, str]]:
    url = 'https://www.bing.com/search?' + urllib.parse.urlencode({'q': query, 'format': 'rss', 'count': '20'})
    body, _ = fetch(url, accept='application/rss+xml,application/xml,text/xml,*/*')
    root = ET.fromstring(body)
    out = []
    for item in root.findall('.//item'):
        title = clean_text(item.findtext('title') or '')
        link = (item.findtext('link') or '').strip()
        desc = clean_text(item.findtext('description') or '')
        pub = clean_text(item.findtext('pubDate') or '')
        if link:
            out.append({'title': title, 'link': link, 'description': desc, 'pubDate': pub, 'source': 'Bing web search'})
    return out


def google_news_rss(query: str) -> list[dict[str, str]]:
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
        'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en',
    })
    body, _ = fetch(url, accept='application/rss+xml,application/xml,text/xml,*/*')
    root = ET.fromstring(body)
    out = []
    for item in root.findall('.//item'):
        source = ''
        for child in list(item):
            if child.tag.endswith('source'):
                source = clean_text(child.text or '')
                break
        out.append({
            'title': clean_text(item.findtext('title') or ''),
            'link': (item.findtext('link') or '').strip(),
            'description': clean_text(item.findtext('description') or ''),
            'pubDate': clean_text(item.findtext('pubDate') or ''),
            'source': source,
        })
    return out


def pdf_text(data: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return clean_text(' '.join((p.extract_text() or '') for p in reader.pages[:8]))
    except Exception:
        return ''


def fetch_official_text(url: str, fallback: str) -> str:
    try:
        body, ctype = fetch(url)
        if 'pdf' in ctype or url.lower().split('?')[0].endswith('.pdf') or body.startswith(b'%PDF'):
            text = pdf_text(body)
        else:
            text = clean_text(body.decode('utf-8', errors='replace'))
        return text if len(text) >= 60 else fallback
    except Exception:
        return fallback


def discover_official() -> tuple[list[dict[str, Any]], list[str]]:
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    direct_url = 'https://www.ukmto.org/recent-incidents'
    try:
        body, _ = fetch(direct_url)
        direct_text = clean_text(body.decode('utf-8', errors='replace'))
        for m in re.finditer(r'(UKMTO.{0,40}#?\s*\d{2,3}.{0,1800})', direct_text, flags=re.I):
            excerpt = m.group(1)[:1800]
            if relevant(excerpt):
                no = warning_no(excerpt)
                if no:
                    key = f'ukmto:{no}:{sha_text(excerpt)}'
                    found[key] = {
                        'key': key, 'warning': no, 'title': f'UKMTO {no}', 'url': direct_url,
                        'text': excerpt, 'discovery': 'UKMTO recent-incidents direct',
                    }
    except Exception as e:
        errors.append(f'UKMTO direct: {type(e).__name__}: {e}')

    for query in UKMTO_QUERIES:
        try:
            for item in bing_rss(query):
                host = source_host(item['link'])
                if host != 'ukmto.org' and not host.endswith('.ukmto.org'):
                    continue
                fallback = f"{item['title']} {item['description']}"
                text = fetch_official_text(item['link'], fallback)
                if not relevant(text + ' ' + fallback):
                    continue
                no = warning_no(text + ' ' + fallback)
                if not no:
                    continue
                key = f'ukmto:{no}:{sha_text(text[:6000])}'
                found[key] = {
                    'key': key, 'warning': no, 'title': item['title'] or f'UKMTO {no}',
                    'url': item['link'], 'text': text[:6000], 'pubDate': item.get('pubDate', ''),
                    'discovery': 'Bing -> official UKMTO',
                }
        except Exception as e:
            errors.append(f'UKMTO search {query!r}: {type(e).__name__}: {e}')
    return sorted(found.values(), key=lambda x: x.get('warning') or ''), errors


def discover_news() -> tuple[list[dict[str, Any]], list[str]]:
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for query in NEWS_QUERIES:
        try:
            for item in google_news_rss(query):
                src = item.get('source', '')
                text = f"{item.get('title','')} {item.get('description','')}"
                if src not in ALLOWED_NEWS_SOURCES or not relevant(text):
                    continue
                key = 'news:' + hashlib.sha256((src + '|' + item['title'] + '|' + item['link']).encode()).hexdigest()[:18]
                found[key] = {
                    'key': key, 'source': src, 'title': item['title'], 'url': item['link'],
                    'text': clean_text(item.get('description', '')), 'pubDate': item.get('pubDate', ''),
                    'warning': warning_no(text),
                }
        except Exception as e:
            errors.append(f'news search {query!r}: {type(e).__name__}: {e}')
    return list(found.values()), errors


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {'version': 1, 'initialized': False, 'official': {}, 'news': {}, 'last_checked_kst': None}
    try:
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        if not isinstance(state, dict):
            raise ValueError('state is not object')
        state.setdefault('version', 1)
        state.setdefault('initialized', False)
        state.setdefault('official', {})
        state.setdefault('news', {})
        return state
    except Exception:
        return {'version': 1, 'initialized': False, 'official': {}, 'news': {}, 'last_checked_kst': None}


def evidence_summary(text: str) -> list[str]:
    t = clean_text(text)
    parts: list[str] = []
    m = re.search(r'(\d+(?:\.\d+)?\s*NM\s+(?:north|south|east|west|northeast|northwest|southeast|southwest)?\s*(?:of|off)?\s*[^.]{2,80})', t, flags=re.I)
    if m:
        parts.append('위치: ' + m.group(1).strip())
    elif 'Strait of Hormuz' in t:
        parts.append('위치: Strait of Hormuz')
    m = re.search(r'((?:tanker|vessel|ship|VLCC)[^.]{0,180}(?:struck|hit|attack(?:ed)?|projectile|mine|fire|explosion)[^.]{0,180})', t, flags=re.I)
    if m:
        sentence = clean_text(m.group(1))[:330]
        sentence = re.sub(r'\bunknown projectiles?\b', '미상 발사체', sentence, flags=re.I)
        sentence = re.sub(r'\bunidentified projectiles?\b', '미상 발사체', sentence, flags=re.I)
        parts.append('사건: ' + sentence)
    lower = t.lower()
    if 'crew are reported safe' in lower or 'crew are safe' in lower or 'all crew are reported safe' in lower:
        parts.append('인명: UKMTO 원문상 crew safe')
    else:
        m = re.search(r'[^.]{0,90}(?:casualt(?:y|ies)|injur(?:y|ies|ed)|fatalit(?:y|ies)|missing)[^.]{0,120}', t, flags=re.I)
        if m:
            parts.append('인명: ' + clean_text(m.group(0))[:220])
    if 'no environmental impact' in lower or 'no reported environmental impact' in lower:
        parts.append('환경: 보고된 오염 없음')
    return parts[:4]


def related_news(official: dict[str, Any], news: list[dict[str, Any]]) -> list[dict[str, Any]]:
    no = official.get('warning')
    out = []
    official_text = normalize(official.get('text', ''))
    for item in news:
        if no and item.get('warning') == no:
            out.append(item)
            continue
        nt = normalize(item.get('title', '') + ' ' + item.get('text', ''))
        shared = sum(1 for token in ('hormuz', 'khasab', 'tanker', 'projectile', 'mine', 'struck', 'attack') if token in official_text and token in nt)
        if shared >= 4:
            out.append(item)
    rank = {'Reuters': 0, 'Associated Press': 1, 'AP News': 1, 'U.S. Central Command': 2, 'CENTCOM': 2}
    return sorted(out, key=lambda x: rank.get(x.get('source', ''), 9))[:3]


def build_alert(item: dict[str, Any], news: list[dict[str, Any]], *, update: bool) -> str:
    no = item.get('warning') or '번호 미확인'
    heading = '[호르무즈 해상보안 업데이트]' if update else '[호르무즈 해상보안 신규 경보]'
    lines = [heading, f'UKMTO: {no}', f'확인시각: {now_kst().strftime("%Y-%m-%d %H:%M KST")}']
    lines.extend(evidence_summary(item.get('text', '')))
    lines.append('무기/공격주체: UKMTO가 특정하지 않은 내용은 추정하지 않음')
    lines.append('원문: ' + item.get('url', ''))
    rel = related_news(item, news)
    exact = [n for n in rel if n.get('warning') == item.get('warning') and item.get('warning')]
    if exact:
        lines.append('교차검증: 경보번호까지 일치하는 보도 확인')
    elif rel:
        lines.append('교차검증: 관련 Reuters/AP/공식·해운 보도 확인(동일 사건 여부는 경보번호 불일치/미표기로 미확정)')
    else:
        lines.append('교차검증: UKMTO 공식 경보 우선 확인, Reuters/AP 후속 보도는 아직 검색되지 않음')
    for n in rel:
        lines.append(f"- {n.get('source')}: {n.get('title')} | {n.get('url')}")
    lines.append('표기 원칙: unknown/unidentified projectile = 미상 발사체. 포탄·미사일·드론으로 임의 단정하지 않음.')
    return '\n'.join(lines).strip() + '\n'


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    official, off_errors = discover_official()
    news, news_errors = discover_news()
    state = load_state()
    initialized = bool(state.get('initialized'))
    old_official = state.get('official') or {}
    old_news = state.get('news') or {}
    new_items = []
    for item in official:
        if item['key'] in old_official:
            continue
        same_warning_seen = any(v.get('warning') == item.get('warning') for v in old_official.values())
        if initialized:
            new_items.append((item, same_warning_seen))

    pending = {
        'version': 1, 'initialized': True,
        'official': dict(old_official), 'news': dict(old_news),
        'last_checked_kst': now_kst().isoformat(timespec='seconds'),
    }
    for item in official:
        pending['official'][item['key']] = {
            'warning': item.get('warning'), 'url': item.get('url'), 'title': item.get('title'),
            'first_seen_kst': old_official.get(item['key'], {}).get('first_seen_kst') or now_kst().isoformat(timespec='seconds'),
        }
    for item in news:
        pending['news'][item['key']] = {
            'source': item.get('source'), 'url': item.get('url'), 'title': item.get('title'),
            'first_seen_kst': old_news.get(item['key'], {}).get('first_seen_kst') or now_kst().isoformat(timespec='seconds'),
        }
    if len(pending['official']) > 250:
        pending['official'] = dict(list(pending['official'].items())[-250:])
    if len(pending['news']) > 500:
        pending['news'] = dict(list(pending['news'].items())[-500:])
    OUT_PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    alerts = [build_alert(item, news, update=update) for item, update in sorted(new_items, key=lambda x: x[0].get('warning') or '')]
    if alerts:
        OUT_ALERT.write_text('\n\n'.join(alerts).strip() + '\n', encoding='utf-8')
    elif OUT_ALERT.exists():
        OUT_ALERT.unlink()

    errors = off_errors + news_errors
    status = [
        '# Hormuz maritime watch',
        f'- checked: {now_kst().strftime("%Y-%m-%d %H:%M:%S KST")}',
        f'- initialized_before_run: {initialized}',
        f'- official_relevant_items: {len(official)}',
        f'- trusted_news_items: {len(news)}',
        f'- new_official_alerts: {len(new_items)}',
        '- policy: only ukmto.org evidence can trigger an official incident alert; unknown projectile is never upgraded to missile/shell/drone without source wording.',
    ]
    if errors:
        status.append('- partial errors:')
        status.extend('  - ' + e[:500] for e in errors[:12])
    OUT_STATUS.write_text('\n'.join(status) + '\n', encoding='utf-8')
    OUT_DEBUG.write_text(json.dumps({'official': official, 'news': news, 'errors': errors}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'hormuz_watch initialized={initialized} official={len(official)} news={len(news)} new={len(new_items)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

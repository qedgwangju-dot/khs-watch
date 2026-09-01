from __future__ import annotations

import datetime as dt
import hashlib
import html
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pypdf import PdfReader

STATE_PATH = Path('data/hormuz_maritime_watch_state.json')
OUT_DIR = Path('out')
OUT_ALERT = OUT_DIR / 'hormuz_maritime_watch_telegram.txt'
OUT_STATUS = OUT_DIR / 'hormuz_maritime_watch_status.md'
OUT_PENDING = OUT_DIR / 'hormuz_maritime_watch_pending_state.json'
OUT_DEBUG = OUT_DIR / 'hormuz_maritime_watch_debug.json'
KST = ZoneInfo('Asia/Seoul')
UA = 'Mozilla/5.0 (compatible; KHS-Hormuz-Maritime-Watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)'
TIMEOUT = 18
MAX_BODY = 7_000_000
STATE_VERSION = 2
BASELINE_WARNING = 124

# Known official baseline: this prevents the already-verified 31 Aug incident from being re-sent as new.
SEED_OFFICIAL_URLS = {
    '124-26': 'https://www.ukmto.org/-/media/ukmto/products/20260831-ukmto_warning_124-26.pdf',
}

# Discovery remains a fallback. Direct sequential PDF probing below is the fast official lane.
UKMTO_QUERIES = [
    'site:ukmto.org "UKMTO WARNING" "Strait of Hormuz"',
    'site:ukmto.org "UKMTO WARNING" tanker Khasab',
    'site:ukmto.org "UKMTO WARNING" tanker Oman projectile',
    'site:ukmto.org "UKMTO WARNING" tanker Fujairah',
]
NEWS_QUERIES = [
    'UKMTO Hormuz tanker when:7d',
    '"Strait of Hormuz" tanker when:7d',
    'Khasab tanker projectile when:7d',
    'Hormuz shipping Reuters when:7d',
    'Hormuz tanker mine missile drone when:7d',
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


def fetch(url: str, *, accept: str = '*/*') -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': accept,
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise RuntimeError(f'response too large: {url}')
        return body, str(r.headers.get('Content-Type') or '').lower(), r.geturl()


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
    return any(x in t for x in GEO_TERMS) and any(x in t for x in VESSEL_TERMS) and any(x in t for x in SECURITY_TERMS)


def warning_no(text: str) -> str | None:
    for pat in (
        r'\b(?:warning|ukmto)\s*[-:#]?\s*(\d{2,3})\s*[-_/]\s*(26)\b',
        r'\bukmto\s+#?(\d{2,3})\b',
    ):
        m = re.search(pat, text, flags=re.I)
        if m:
            return f'{int(m.group(1)):03d}-26'
    return None


def warning_int(value: str | None) -> int:
    m = re.match(r'^(\d{2,3})-26$', value or '')
    return int(m.group(1)) if m else 0


def sha_text(text: str) -> str:
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()[:16]


def source_host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or '').lower().lstrip('www.')


def pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return clean_text(' '.join((page.extract_text() or '') for page in reader.pages[:10]))
    except Exception:
        return ''


def fetch_official(url: str) -> tuple[str, str]:
    body, ctype, final_url = fetch(url)
    if 'pdf' in ctype or final_url.lower().split('?')[0].endswith('.pdf') or body.startswith(b'%PDF'):
        text = pdf_text(body)
    else:
        text = clean_text(body.decode('utf-8', errors='replace'))
    return text, final_url


def candidate_pdf_urls(number: int, days: int = 4) -> list[str]:
    year2 = str(now_kst().year)[-2:]
    urls = []
    for delta in range(days):
        date = (now_kst().date() - dt.timedelta(days=delta)).strftime('%Y%m%d')
        urls.extend([
            f'https://www.ukmto.org/-/media/ukmto/products/{date}-ukmto_warning_{number:03d}-{year2}.pdf',
            f'https://www.ukmto.org/-/media/ukmto/products/{date}-ukmto_warning_{number:03d}_{year2}.pdf',
            f'https://www.ukmto.org/-/media/ukmto/products/{date}-ukmto_warning_attack_{number:03d}_{year2}.pdf',
            f'https://www.ukmto.org/-/media/ukmto/products/{date}-ukmto_warning_suspicious_activity_{number:03d}_{year2}.pdf',
            f'https://www.ukmto.org/-/media/ukmto/products/{date}-ukmto_advisory_{number:03d}-{year2}.pdf',
        ])
    return urls


def direct_official_probes(highest: int) -> tuple[list[dict[str, Any]], int, list[str]]:
    found: list[dict[str, Any]] = []
    errors: list[str] = []
    max_seen = highest

    # Re-fetch the current verified baseline so same-warning official updates can be noticed.
    for known_no, url in SEED_OFFICIAL_URLS.items():
        try:
            text, final_url = fetch_official(url)
            if 'UKMTO' in text.upper() and warning_no(text) == known_no:
                found.append({
                    'warning': known_no, 'title': f'UKMTO {known_no}', 'url': final_url,
                    'text': text[:7000], 'discovery': 'direct official baseline URL',
                })
        except Exception as e:
            errors.append(f'baseline {known_no}: {type(e).__name__}: {e}')

    # Probe the next eight warning/advisory numbers. 404s are expected and are not logged as errors.
    start = max(BASELINE_WARNING + 1, highest + 1)
    for number in range(start, start + 8):
        hit = None
        for url in candidate_pdf_urls(number):
            try:
                text, final_url = fetch_official(url)
            except Exception as e:
                if getattr(e, 'code', None) in (403, 404):
                    continue
                continue
            no = warning_no(text)
            if no and warning_int(no) == number and 'UKMTO' in text.upper():
                hit = {
                    'warning': no, 'title': f'UKMTO {no}', 'url': final_url,
                    'text': text[:7000], 'discovery': 'direct sequential UKMTO PDF probe',
                }
                max_seen = max(max_seen, number)
                break
        if hit:
            found.append(hit)
    return found, max_seen, errors


def bing_rss(query: str) -> list[dict[str, str]]:
    url = 'https://www.bing.com/search?' + urllib.parse.urlencode({'q': query, 'format': 'rss', 'count': '20'})
    body, _, _ = fetch(url, accept='application/rss+xml,application/xml,text/xml,*/*')
    root = ET.fromstring(body)
    out = []
    for item in root.findall('.//item'):
        link = (item.findtext('link') or '').strip()
        if link:
            out.append({
                'title': clean_text(item.findtext('title') or ''),
                'link': link,
                'description': clean_text(item.findtext('description') or ''),
                'pubDate': clean_text(item.findtext('pubDate') or ''),
            })
    return out


def search_official() -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
    found = []
    errors = []
    samples = []
    for query in UKMTO_QUERIES:
        try:
            items = bing_rss(query)
            samples.extend(items[:2])
            for item in items:
                fallback = f"{item['title']} {item['description']}"
                try:
                    text, final_url = fetch_official(item['link'])
                except Exception:
                    continue
                host = source_host(final_url)
                if host != 'ukmto.org' and not host.endswith('.ukmto.org'):
                    continue
                merged = text + ' ' + fallback
                no = warning_no(merged)
                if no and relevant(merged):
                    found.append({
                        'warning': no, 'title': item['title'] or f'UKMTO {no}', 'url': final_url,
                        'text': text[:7000] if text else fallback[:7000], 'pubDate': item.get('pubDate', ''),
                        'discovery': 'Bing redirect -> official UKMTO',
                    })
        except Exception as e:
            errors.append(f'UKMTO search {query!r}: {type(e).__name__}: {e}')
    return found, errors, samples[:10]


def google_news_rss(query: str) -> list[dict[str, str]]:
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    body, _, _ = fetch(url, accept='application/rss+xml,application/xml,text/xml,*/*')
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


def discover_news() -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
    found: dict[str, dict[str, Any]] = {}
    errors = []
    samples = []
    for query in NEWS_QUERIES:
        try:
            items = google_news_rss(query)
            samples.extend(items[:3])
            for item in items:
                src = item.get('source', '')
                text = f"{item.get('title','')} {item.get('description','')}"
                if src not in ALLOWED_NEWS_SOURCES or not relevant(text):
                    continue
                key = hashlib.sha256((src + '|' + item['title'] + '|' + item['link']).encode()).hexdigest()[:18]
                found[key] = {
                    'key': key, 'source': src, 'title': item['title'], 'url': item['link'],
                    'text': item.get('description', ''), 'pubDate': item.get('pubDate', ''),
                    'warning': warning_no(text),
                }
        except Exception as e:
            errors.append(f'news {query!r}: {type(e).__name__}: {e}')
    return list(found.values()), errors, samples[:15]


def load_state() -> dict[str, Any]:
    default = {
        'version': STATE_VERSION, 'initialized': False, 'official': {}, 'news': {},
        'highest_warning_seen': BASELINE_WARNING, 'last_checked_kst': None,
    }
    if not STATE_PATH.exists():
        return default
    try:
        old = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        if int(old.get('version') or 0) < STATE_VERSION:
            return default
        old.setdefault('official', {})
        old.setdefault('news', {})
        old.setdefault('highest_warning_seen', BASELINE_WARNING)
        old.setdefault('initialized', False)
        return old
    except Exception:
        return default


def make_official_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    text = clean_text(raw.get('text', ''))
    no = raw.get('warning') or warning_no(text)
    if not no:
        return None
    digest = sha_text(text[:7000])
    return {
        **raw,
        'warning': no,
        'text': text,
        'key': f'ukmto:{no}:{digest}',
        'relevant': relevant(text),
    }


def evidence_summary(text: str) -> list[str]:
    t = clean_text(text)
    parts = []
    m = re.search(r'(\d+(?:\.\d+)?\s*NM\s+(?:north|south|east|west|northeast|northwest|southeast|southwest)?\s*(?:of|off)?\s*[^.]{2,90})', t, flags=re.I)
    if m:
        parts.append('위치: ' + m.group(1).strip())
    elif 'Strait of Hormuz' in t:
        parts.append('위치: Strait of Hormuz')
    m = re.search(r'((?:tanker|vessel|ship|VLCC)[^.]{0,200}(?:struck|hit|attack(?:ed)?|projectile|mine|fire|explosion)[^.]{0,200})', t, flags=re.I)
    if m:
        sentence = clean_text(m.group(1))[:360]
        sentence = re.sub(r'\bunknown projectiles?\b', '미상 발사체', sentence, flags=re.I)
        sentence = re.sub(r'\bunidentified projectiles?\b', '미상 발사체', sentence, flags=re.I)
        parts.append('사건: ' + sentence)
    lower = t.lower()
    if 'crew are reported safe' in lower or 'crew are safe' in lower or 'all crew are reported safe' in lower:
        parts.append('인명: UKMTO 원문상 crew safe')
    else:
        m = re.search(r'[^.]{0,90}(?:casualt(?:y|ies)|injur(?:y|ies|ed)|fatalit(?:y|ies)|missing)[^.]{0,130}', t, flags=re.I)
        if m:
            parts.append('인명: ' + clean_text(m.group(0))[:230])
    if 'no environmental impact' in lower or 'no reported environmental impact' in lower:
        parts.append('환경: 보고된 오염 없음')
    return parts[:4]


def related_news(official: dict[str, Any], news: list[dict[str, Any]]) -> list[dict[str, Any]]:
    no = official.get('warning')
    out = []
    ot = normalize(official.get('text', ''))
    for item in news:
        if no and item.get('warning') == no:
            out.append(item)
            continue
        nt = normalize(item.get('title', '') + ' ' + item.get('text', ''))
        shared = sum(1 for token in ('hormuz', 'khasab', 'tanker', 'projectile', 'mine', 'struck', 'attack') if token in ot and token in nt)
        if shared >= 4:
            out.append(item)
    rank = {'Reuters': 0, 'Associated Press': 1, 'AP News': 1, 'U.S. Central Command': 2, 'CENTCOM': 2}
    return sorted(out, key=lambda x: rank.get(x.get('source', ''), 9))[:3]


def build_alert(item: dict[str, Any], news: list[dict[str, Any]], update: bool) -> str:
    heading = '[호르무즈 해상보안 업데이트]' if update else '[호르무즈 해상보안 신규 경보]'
    lines = [heading, f"UKMTO: {item.get('warning')}", f"확인시각: {now_kst().strftime('%Y-%m-%d %H:%M KST')}"]
    lines.extend(evidence_summary(item.get('text', '')))
    lines.append('무기/공격주체: UKMTO가 특정하지 않은 내용은 추정하지 않음')
    lines.append('원문: ' + item.get('url', ''))
    rel = related_news(item, news)
    if any(n.get('warning') == item.get('warning') and item.get('warning') for n in rel):
        lines.append('교차검증: 경보번호까지 일치하는 신뢰 보도 확인')
    elif rel:
        lines.append('교차검증: 관련 Reuters/AP/공식·해운 보도 확인. 동일 사건 여부가 확정되지 않은 내용은 별도 표기')
    else:
        lines.append('교차검증: UKMTO 공식 원문 우선 확인. Reuters/AP 후속 보도는 아직 검색되지 않음')
    for n in rel:
        lines.append(f"- {n.get('source')}: {n.get('title')} | {n.get('url')}")
    lines.append('표기 원칙: unknown/unidentified projectile = 미상 발사체. 포탄·미사일·드론으로 임의 단정하지 않음.')
    return '\n'.join(lines).strip() + '\n'


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    initialized = bool(state.get('initialized'))
    highest = max(BASELINE_WARNING, int(state.get('highest_warning_seen') or BASELINE_WARNING))

    direct, direct_high, direct_errors = direct_official_probes(highest)
    searched, search_errors, search_samples = search_official()
    news, news_errors, news_samples = discover_news()

    raw_official = direct + searched
    official_map: dict[str, dict[str, Any]] = {}
    for raw in raw_official:
        item = make_official_item(raw)
        if item:
            official_map[item['key']] = item
    official = list(official_map.values())
    highest_discovered = max([direct_high, highest] + [warning_int(x.get('warning')) for x in official])

    old_official = state.get('official') or {}
    old_news = state.get('news') or {}
    new_items = []
    for item in official:
        if item['key'] in old_official:
            continue
        same_warning_seen = any(v.get('warning') == item.get('warning') for v in old_official.values())
        if initialized and item.get('relevant'):
            new_items.append((item, same_warning_seen))

    pending = {
        'version': STATE_VERSION,
        'initialized': True,
        'official': dict(old_official),
        'news': dict(old_news),
        'highest_warning_seen': highest_discovered,
        'last_checked_kst': now_kst().isoformat(timespec='seconds'),
    }
    for item in official:
        pending['official'][item['key']] = {
            'warning': item.get('warning'), 'url': item.get('url'), 'title': item.get('title'),
            'relevant': item.get('relevant'),
            'first_seen_kst': old_official.get(item['key'], {}).get('first_seen_kst') or now_kst().isoformat(timespec='seconds'),
        }
    for item in news:
        pending['news'][item['key']] = {
            'source': item.get('source'), 'url': item.get('url'), 'title': item.get('title'),
            'first_seen_kst': old_news.get(item['key'], {}).get('first_seen_kst') or now_kst().isoformat(timespec='seconds'),
        }
    if len(pending['official']) > 300:
        pending['official'] = dict(list(pending['official'].items())[-300:])
    if len(pending['news']) > 500:
        pending['news'] = dict(list(pending['news'].items())[-500:])
    OUT_PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    alerts = [build_alert(item, news, update) for item, update in sorted(new_items, key=lambda x: warning_int(x[0].get('warning')))]
    if alerts:
        OUT_ALERT.write_text('\n\n'.join(alerts).strip() + '\n', encoding='utf-8')
    elif OUT_ALERT.exists():
        OUT_ALERT.unlink()

    errors = direct_errors + search_errors + news_errors
    status = [
        '# Hormuz maritime watch',
        f'- checked: {now_kst().strftime("%Y-%m-%d %H:%M:%S KST")}',
        f'- state_version: {STATE_VERSION}',
        f'- initialized_before_run: {initialized}',
        f'- highest_warning_seen: {highest_discovered}',
        f'- official_items_detected: {len(official)}',
        f'- official_relevant_items: {sum(1 for x in official if x.get("relevant"))}',
        f'- trusted_news_items: {len(news)}',
        f'- new_official_alerts: {len(new_items)}',
        '- trigger: UKMTO official evidence only. Trusted news is cross-check/context, never a substitute for the official trigger.',
        '- fidelity: unknown/unidentified projectile remains 미상 발사체 unless an official source identifies the weapon.',
    ]
    if errors:
        status.append('- partial errors:')
        status.extend('  - ' + e[:500] for e in errors[:12])
    OUT_STATUS.write_text('\n'.join(status) + '\n', encoding='utf-8')
    OUT_DEBUG.write_text(json.dumps({
        'official': official, 'news': news, 'errors': errors,
        'ukmto_search_samples': search_samples, 'news_samples': news_samples,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'hormuz_watch_v2 initialized={initialized} highest={highest_discovered} official={len(official)} relevant={sum(1 for x in official if x.get("relevant"))} news={len(news)} new={len(new_items)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

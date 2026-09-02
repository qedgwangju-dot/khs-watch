from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
UTC = dt.timezone.utc
UA = 'Mozilla/5.0 (compatible; HalozymePTABWatch/1.0)'
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / 'data/halozyme_ptab_watch_state.json'
STATUS = ROOT / 'out/halozyme_ptab_status.md'
ROUTE = ROOT / 'data/bio_telegram_chat_id.enc'

CASES = {
    'PGR2025-00003': '11,952,600',
    'PGR2025-00004': '12,018,298',
    'PGR2025-00006': '12,152,262',
    'PGR2025-00009': '12,123,035',
    'PGR2025-00017': '12,110,520',
    'PGR2025-00024': '12,060,590',
    'PGR2025-00030': '12,054,758',
    'PGR2025-00033': '12,049,652',
    'PGR2025-00039': '12,104,185',
    'PGR2025-00042': '12,037,618',
    'PGR2025-00046': '12,091,692',
    'PGR2025-00050': '12,077,791',
    'PGR2025-00052': '12,264,345',
    'PGR2025-00053': '12,195,773',
    'PGR2025-00087': '12,371,685',
    'IPR2026-00312': '10,865,400',
    'IPR2026-00313': '11,041,149',
    'IPR2026-00314': '11,066,656',
}

# 이미 사용자가 확인한 5건의 최종 무효 결정은 기준선으로만 저장해 재송출하지 않는다.
BASELINE_FINALS = {
    'PGR2025-00003', 'PGR2025-00004', 'PGR2025-00006', 'PGR2025-00009', 'PGR2025-00017'
}

EVENT_WORDS = {
    'final_unpatentable': ('final written decision', 'all challenged claims unpatentable', 'determining all challenged claims unpatentable', '최종서면결정', '전부 무효', '청구항 전부가 무효'),
    'director_review': ('director review', 'director review denied', 'director review granted', '국장 재검토'),
    'rehearing': ('rehearing', 'request for rehearing', '재심'),
    'appeal': ('notice of appeal', 'federal circuit', 'court of appeals', '항소'),
    'institution': ('institution decision', 'granting institution', 'instituted', 'institution denied', '심판 개시'),
    'termination': ('motion to terminate', 'terminated', 'settlement', '종결', '합의'),
    'disclaimer': ('statutory disclaimer', 'disclaimed claims', '청구항 포기'),
}


def h(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]


def clean_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(html.unescape(url))
        if p.netloc.lower().endswith('bing.com') and p.path.endswith('/news/apiclick.aspx'):
            target = urllib.parse.parse_qs(p.query).get('url', [''])[0]
            if target.startswith(('http://', 'https://')):
                return clean_url(target)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in {'ocid','ref','source','cid'}]
        return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, '', urllib.parse.urlencode(q), ''))
    except Exception:
        return url


def fetch(url: str, timeout: int = 18) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1_000_000).decode(r.headers.get_content_charset() or 'utf-8', errors='replace')


def rss(query: str, news: bool) -> list[dict]:
    if news:
        url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    else:
        url = 'https://www.bing.com/search?' + urllib.parse.urlencode({'q': query, 'format': 'rss'})
    root = ET.fromstring(fetch(url))
    out = []
    for n in root.findall('.//item')[:20]:
        out.append({
            'title': html.unescape((n.findtext('title') or '').strip()),
            'url': clean_url((n.findtext('link') or '').strip()),
            'published': (n.findtext('pubDate') or '').strip(),
            'description': re.sub(r'<[^>]+>', ' ', html.unescape(n.findtext('description') or '')).strip(),
        })
    return out


def event_type(text: str) -> str:
    low = text.lower()
    for key, terms in EVENT_WORDS.items():
        if any(t.lower() in low for t in terms):
            return key
    return ''


def case_from(text: str) -> str:
    up = text.upper()
    for case in CASES:
        if case in up:
            return case
    digits = re.sub(r'[^0-9]', '', text)
    for case, patent in CASES.items():
        if re.sub(r'[^0-9]', '', patent) in digits:
            return case
    return ''


def is_official(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.endswith('uspto.gov') or host.endswith('ptacts.uspto.gov')


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            pass
    baseline = [h(f'{case}|final_unpatentable') for case in sorted(BASELINE_FINALS)]
    return {'initialized': False, 'seen_events': baseline, 'seen_urls': []}


def resolve_chat_id(token: str) -> str:
    direct = (os.getenv('BIO_TELEGRAM_CHAT_ID') or '').strip()
    if direct:
        return direct
    if not ROUTE.exists():
        return ''
    env = os.environ.copy(); env['BIO_TELEGRAM_BOT_TOKEN'] = token
    p = subprocess.run(['openssl','enc','-d','-aes-256-cbc','-a','-A','-pbkdf2','-pass','env:BIO_TELEGRAM_BOT_TOKEN','-in',str(ROUTE)], cwd=ROOT, text=True, capture_output=True, timeout=20, env=env)
    return p.stdout.strip() if p.returncode == 0 else ''


def send(token: str, chat_id: str, text: str) -> int:
    payload = urllib.parse.urlencode({'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=payload, method='POST')
    with urllib.request.urlopen(req, timeout=25) as r:
        result = json.loads(r.read().decode())
    if not result.get('ok'):
        raise RuntimeError(str(result))
    return int((result.get('result') or {}).get('message_id') or 0)


def format_alert(case: str, patent: str, kind: str, title: str, url: str, official: bool) -> str:
    labels = {
        'final_unpatentable': 'PTAB 최종서면결정', 'director_review': 'USPTO 국장 재검토', 'rehearing': 'PTAB 재심',
        'appeal': '연방순회항소법원 항소', 'institution': 'PGR·IPR 심판 개시 결정', 'termination': '분쟁 종결·합의', 'disclaimer': '청구항 포기'
    }
    event = labels.get(kind, '특허분쟁 새 결정')
    if kind == 'final_unpatentable':
        headline = f'MSD 승소 — {case}, Halozyme 미국 특허 {patent} 심판대상 청구항 무효'
        decision = 'PTAB가 심판 대상 청구항을 특허 받을 수 없음으로 최종 판단'
        alteogen = 'ALT-B4 자체 특허 판단은 아닙니다. 다만 Halozyme의 변형 PH20 특허 장벽이 약해지면 KEYTRUDA QLEX·ALT-B4의 미국 피하주사 전환 관련 특허분쟁 부담이 낮아지는 방향입니다.'
    else:
        headline = f'Halozyme 특허분쟁 — {case} 새 절차·결정'
        decision = title
        alteogen = 'MSD·알테오젠의 피하주사 전환 사업에 영향을 줄 수 있어 후속 결과를 직접 추적합니다.'
    source = 'USPTO/PTAB 공식자료' if official else '2차 자료 — USPTO/PTAB 공식 원문 교차확인 대상'
    safe_url = html.escape(url, quote=True)
    return (
        '<b>[바이오 감시] Halozyme 특허분쟁 새 결정</b>\n\n'
        f'<b>{html.escape(headline)}</b>\n\n'
        f'- <b>사건:</b> {case} · 미국 특허 {patent}\n'
        f'- <b>결정:</b> {html.escape(decision)}\n'
        f'- <b>알테오젠:</b> {html.escape(alteogen)}\n'
        '- <b>아직 남음:</b> 국장 재검토·재심·연방순회항소법원 항소 가능성 + 다른 관련 PGR·IPR + 뉴저지 연방법원 민사소송\n'
        '- <b>다음 확인:</b> Director Review/재심 → 항소 → 다른 관련 사건 최종서면결정\n'
        f'- <b>원문 확인:</b> {source}\n'
        f'- <a href="{safe_url}">원문 뉴스보기</a>'
    )


def main() -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True); STATUS.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(); seen_events = set(state.get('seen_events') or []); seen_urls = set(state.get('seen_urls') or [])
    found: list[tuple] = []; errors: list[str] = []
    # 개별 사건번호를 직접 조회해 기사 키워드보다 사건번호를 우선한다.
    for case, patent in CASES.items():
        queries = [f'"{case}" Halozyme Merck', f'"{case}" "Final Written Decision"', f'"{patent}" Halozyme Merck PTAB']
        for q in queries:
            for news in (False, True):
                try:
                    for item in rss(q, news):
                        blob = f"{item['title']} {item['description']} {item['url']}"
                        c = case_from(blob) or case
                        if c != case:
                            continue
                        kind = event_type(blob)
                        if not kind:
                            continue
                        ekey = h(f'{case}|{kind}')
                        if ekey in seen_events or item['url'] in seen_urls:
                            continue
                        found.append((0 if is_official(item['url']) else 1, case, patent, kind, item))
                except Exception as exc:
                    errors.append(f'{case} {q}: {type(exc).__name__}')
    # 같은 사건·같은 절차는 공식 원문을 우선해 한 번만 송출.
    best: dict[str, tuple] = {}
    for row in sorted(found, key=lambda x: x[0]):
        _, case, patent, kind, item = row
        best.setdefault(h(f'{case}|{kind}'), row)

    token = (os.getenv('BIO_TELEGRAM_BOT_TOKEN') or '').strip()
    chat_id = resolve_chat_id(token) if token else ''
    sent = []
    if not token or not chat_id:
        errors.append('Telegram route missing')
    else:
        for ekey, row in list(best.items())[:8]:
            _, case, patent, kind, item = row
            msg = format_alert(case, patent, kind, item['title'], item['url'], is_official(item['url']))
            mid = send(token, chat_id, msg)
            sent.append(mid); seen_events.add(ekey); seen_urls.add(item['url'])

    now = dt.datetime.now(KST).isoformat(timespec='seconds')
    state.update({'initialized': True, 'last_check_kst': now, 'seen_events': sorted(seen_events)[-4000:], 'seen_urls': sorted(seen_urls)[-4000:], 'tracked_cases': CASES, 'errors_last_run': errors[-20:]})
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    STATUS.write_text(f'Halozyme PTAB 감시 — {now}; 신규송출={len(sent)}; 추적사건={len(CASES)}; 오류={len(errors)}\n', encoding='utf-8')
    print(json.dumps({'status': 'ok' if not errors else 'partial', 'sent_message_ids': sent, 'tracked_cases': len(CASES), 'errors': errors[-5:]}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

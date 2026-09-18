#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

STATE = Path('data/warsh_post_fomc_ib_reaction_watch_state.json')
PATH_STATE = Path('data/warsh_policy_path_watch_state.json')
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'hshs8879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/3.1)'

FED_SEP = 'https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm'
REUTERS_VIEW = 'https://www.reuters.com/business/view-markets-steady-after-fed-raises-rates-points-another-hike-this-year-2026-09-16/'
REUTERS_MS = 'https://www.reuters.com/business/morgan-stanley-turns-more-hawkish-forecasts-two-fed-hikes-ecb-move-2026-09-15/'
UBS_OFFICIAL = 'https://www.ubs.com/us/en/wealth-management/insights/market-news/article.3754419.html'

# FOMC 직후 공개자료로 확인된 경로만 확정 기준선에 넣습니다.
CONFIRMED_BASE = {
    'Morgan Stanley': {'extra_hikes': 1, 'next': '12월', 'first_cut_2027': None, 'status': '공개 확인', 'source': REUTERS_MS},
    'Goldman Sachs': {'extra_hikes': 1, 'next': '12월', 'first_cut_2027': None, 'status': '공개 확인', 'source': REUTERS_VIEW},
    'UBS': {'extra_hikes': 1, 'next': '12월', 'first_cut_2027': None, 'status': '공개 확인', 'source': UBS_OFFICIAL},
}

# 사용자가 제공한 외사 요약 중 공개 원문을 아직 독립 확인하지 못한 항목은 후보로만 유지합니다.
TRACKING_BASE = {
    'Bank of America': {'extra_hikes': 2, 'next': '10월·12월', 'first_cut_2027': None, 'status': '리서치 요약 기준·공개 원문 추가 확인'},
    'Citi': {'extra_hikes': 0, 'next': '10월·12월 동결', 'first_cut_2027': '6월', 'status': '리서치 요약 기준·공개 원문 추가 확인'},
    'JPMorgan': {'extra_hikes': 1, 'next': '12월', 'first_cut_2027': None, 'status': '리서치 요약 기준·공개 원문 추가 확인'},
}

ALIASES = {
    'Morgan Stanley': ['Morgan Stanley'],
    'Goldman Sachs': ['Goldman Sachs', 'Goldman'],
    'UBS': ['UBS'],
    'Bank of America': ['Bank of America', 'BofA'],
    'Citi': ['Citigroup', 'Citi'],
    'JPMorgan': ['JPMorgan', 'JP Morgan', 'J.P. Morgan'],
}
TRUSTED = {'Reuters', 'Bloomberg', 'CNBC', 'The Wall Street Journal', 'WSJ', 'Financial Times', 'Barron’s', 'Barrons'}


def fetch(url, timeout=25):
    q = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(q, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def clean(s):
    s = re.sub(r'(?s)<[^>]+>', ' ', s or '')
    return html.unescape(re.sub(r'\s+', ' ', s)).strip()


def load(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else (default or {})
    except Exception:
        return default or {}


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def botname():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        return str((json.loads(r.read().decode()).get('result') or {}).get('username') or '')


def link(label, url):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def send(msg):
    if not TOKEN or not CHAT:
        raise RuntimeError('Telegram 비밀값 없음')
    actual = botname()
    if actual.lower() != BOT.lower():
        raise RuntimeError(f'Telegram 봇 불일치: expected @{BOT}, got @{actual}')
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4090], 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data=data, method='POST')
    with urllib.request.urlopen(req, timeout=25) as r:
        out = json.loads(r.read().decode())
    if not out.get('ok'):
        raise RuntimeError('Telegram 전송 실패')


def year_end_mid(extra):
    return 3.875 + 0.25 * int(extra)


def market_path():
    p = load(PATH_STATE, {})
    ms = [m for m in p.get('meetings', []) if str(m.get('date', '')).startswith('2026-')]
    year_end = None
    if ms:
        year_end = float(sorted(ms, key=lambda x: x['date'])[-1].get('post_rate'))
    extra_bp = ((p.get('classification') or {}).get('extra_bp'))
    return {'year_end': year_end, 'extra_bp': extra_bp, 'source': p.get('source')}


def rss_rows(inst):
    terms = ' '.join(ALIASES[inst][:2])
    query = urllib.parse.quote(f'{terms} Fed FOMC September 2026 additional hike October December 2027')
    url = f'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'
    try:
        raw = fetch(url)
        root = ET.fromstring(raw)
    except Exception:
        return []
    out = []
    for item in root.findall('.//item')[:50]:
        src = item.find('source')
        pub = clean(src.text if src is not None else '')
        if pub not in TRUSTED:
            continue
        title = clean(item.findtext('title'))
        desc = clean(item.findtext('description'))
        text = title + ' ' + desc
        if not any(a.lower() in text.lower() for a in ALIASES[inst]):
            continue
        out.append({'publisher': pub, 'title': title, 'description': desc, 'url': (item.findtext('link') or '').strip()})
    return out


def parse_path(text):
    low = text.lower().replace('basis points', 'bp').replace('basis point', 'bp')
    out = {}
    if re.search(r'(?:october|oct\.)[^.]{0,70}(?:december|dec\.)[^.]{0,70}(?:hike|raise)|(?:two|2)\s+(?:additional|more)?\s*(?:rate\s*)?hikes', low):
        out['extra_hikes'] = 2; out['next'] = '10월·12월'
    elif re.search(r'(?:one|1)\s+(?:additional|more)?\s*(?:rate\s*)?hike|another\s+(?:25\s*bp|quarter[- ]point)?\s*hike|(?:hike|raise)[^.]{0,60}december', low):
        out['extra_hikes'] = 1; out['next'] = '12월'
    elif re.search(r'no\s+(?:further|additional)\s+hikes|hold[^.]{0,50}(?:october|oct\.)[^.]{0,80}(?:december|dec\.)|(?:october|oct\.)[^.]{0,50}(?:and|,)[^.]{0,20}(?:december|dec\.)[^.]{0,50}hold', low):
        out['extra_hikes'] = 0; out['next'] = '10월·12월 동결'
    m = re.search(r'(?:cut|cuts|lower)[^.]{0,50}(?:june|jun\.)\s+2027|(?:june|jun\.)\s+2027[^.]{0,50}(?:cut|cuts|lower)', low)
    if m:
        out['first_cut_2027'] = '6월'
    return out


def evidence_updates(current):
    confirmed_changes = []
    candidates = []
    for inst in ALIASES:
        rows = rss_rows(inst)
        groups = {}
        for row in rows:
            p = parse_path(row['title'] + ' ' + row['description'])
            if 'extra_hikes' not in p:
                continue
            key = (p['extra_hikes'], p.get('next'), p.get('first_cut_2027'))
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            new = {'extra_hikes': key[0], 'next': key[1], 'first_cut_2027': key[2]}
            old = current.get(inst)
            if old and old.get('extra_hikes') == new['extra_hikes'] and old.get('next') == new['next'] and (not new.get('first_cut_2027') or old.get('first_cut_2027') == new.get('first_cut_2027')):
                continue
            pubs = {x['publisher'] for x in group}
            obj = {'institution': inst, 'old': old, 'new': new, 'evidence': group[:3]}
            if len(pubs) >= 2:
                confirmed_changes.append(obj)
            else:
                candidates.append(obj)
    return confirmed_changes, candidates


def counts(paths):
    out = {0: 0, 1: 0, 2: 0}
    for v in paths.values():
        x = v.get('extra_hikes')
        if x in out:
            out[x] += 1
    return out


def ib_center_mid(paths):
    mids = sorted(
        year_end_mid(v.get('extra_hikes'))
        for v in paths.values()
        if v.get('extra_hikes') in (0, 1, 2)
    )
    if not mids:
        return None
    n = len(mids)
    if n % 2:
        return mids[n // 2]
    return (mids[n // 2 - 1] + mids[n // 2]) / 2


def divergence_view(paths, market):
    center = ib_center_mid(paths)
    year_end = market.get('year_end')
    if center is None or year_end is None:
        return {'ib_center': center, 'market_year_end': year_end, 'gap_bp': None, 'zone': '확인 불가'}
    gap = (float(year_end) - float(center)) * 100
    if gap >= 25:
        zone = '선물시장 상방 괴리'
    elif gap <= -25:
        zone = '선물시장 하방 괴리'
    else:
        zone = '25bp 이내'
    return {'ib_center': center, 'market_year_end': float(year_end), 'gap_bp': gap, 'zone': zone}


def divergence_triggered(old_div, new_div):
    new_gap = new_div.get('gap_bp')
    if new_gap is None or abs(float(new_gap)) < 25:
        return False
    old_gap = old_div.get('gap_bp')
    if old_gap is None:
        return True
    old_gap = float(old_gap)
    new_gap = float(new_gap)
    if abs(old_gap) < 25:
        return True
    if old_gap * new_gap < 0:
        return True
    return abs(new_gap - old_gap) >= 25


def snapshot_message(confirmed, tracking, market, title='기준선'):
    cc = counts(confirmed)
    lines = ['<b>[FOMC 주요 IB 사후 정책경로]</b>', f'<b>{html.escape(title)}</b>', '',
             '<b>한눈에 보기</b>',
             f"• 공개 확인된 3곳: 추가 0회 {cc[0]}곳 · 1회 {cc[1]}곳 · 2회 {cc[2]}곳",
             '• 연준 공식 점도표: 추가 0회 2명 · 1회 12명 · 2회 4명',
             '• 정책금리 중간값 기준: 추가 0회 3.875% · 1회 4.125% · 2회 4.375%']
    if market.get('year_end') is not None:
        lines.append(f"• 선물시장 2026년 말 확률가중 경로: 약 {market['year_end']:.3f}%")
    if market.get('extra_bp') is not None:
        lines.append(f"• 9월 인상 뒤 연말까지 추가 기대: 약 +{float(market['extra_bp']):.1f}bp")
    div = divergence_view(confirmed, market)
    if div.get('gap_bp') is not None:
        lines.append(f"• 공개확인 IB 중심경로: 약 {div['ib_center']:.3f}% · 선물시장 괴리 {div['gap_bp']:+.1f}bp")
    lines += ['', '<b>공개 확인 경로</b>']
    for inst, v in confirmed.items():
        lines.append(f"• {html.escape(inst)}: 추가 {v['extra_hikes']}회 · 다음 {html.escape(v['next'])} · 연말 약 {year_end_mid(v['extra_hikes']):.3f}% · {link('근거', v['source'])}")
    lines += ['', '<b>추적 후보 — 공개 원문 추가 확인</b>']
    for inst, v in tracking.items():
        extra = f" · 첫 인하 {v['first_cut_2027']}" if v.get('first_cut_2027') else ''
        lines.append(f"• {html.escape(inst)}: 추가 {v['extra_hikes']}회 · {html.escape(v['next'])} · 연말 약 {year_end_mid(v['extra_hikes']):.3f}%{extra}")
    lines += ['', '<b>쉽게 말하면</b>',
              '• 지금 핵심은 “9월에 올렸느냐”가 아니라 그 뒤 0회·1회·2회 중 어디로 수렴하느냐입니다.',
              '• 선물시장의 +bp는 확률을 섞은 기대값입니다. 예를 들어 +34bp는 25bp 한 번이 확정되고 또 한 번이 확정됐다는 뜻이 아니라, 여러 경로의 확률가중 평균입니다.',
              '• 가장 큰 정책경로 차이는 추가 0회와 2회 사이 50bp입니다. 이 격차가 좁혀질 때 2년물·달러·성장주 할인율도 크게 재가격될 수 있습니다.', '',
              '<b>알림 조건</b>',
              '• 주요 IB의 추가 인상 횟수 또는 첫 다음 행동 시점 변경',
              '• 2027년 첫 인하 시점 변경',
              '• 3곳 이상이 같은 방향으로 전망 변경',
              '• IB 중심경로와 선물시장 경로의 괴리가 25bp 이상 확대', '',
              '<b>원천</b>', f"{link('연준 경제전망·점도표', FED_SEP)} · {link('Reuters FOMC 사후 반응', REUTERS_VIEW)} · {link('UBS 공식 전망', UBS_OFFICIAL)}"]
    return '\n'.join(lines)


def change_message(changes, current, market):
    lines = ['<b>[FOMC 주요 IB 사후 정책경로 · 변화]</b>', '', '<b>무엇이 달라졌나</b>']
    for c in changes:
        old = c.get('old') or {}
        new = c['new']
        lines.append(f"• {html.escape(c['institution'])}: 추가 {old.get('extra_hikes','?')}회/{html.escape(str(old.get('next','?')))} → 추가 {new['extra_hikes']}회/{html.escape(new['next'])}")
        for row in c['evidence'][:2]:
            lines.append(f"  · {link(row['publisher'], row['url'])}")
    if market.get('year_end') is not None:
        lines += ['', f"• 현재 선물시장 연말 확률가중 경로: 약 {market['year_end']:.3f}%"]
    lines += ['', '<b>쉽게 말하면</b>', '• 월가의 추가 인상 횟수 전망이 실제로 바뀌었는지, 그리고 선물시장도 같은 방향으로 따라가는지를 확인하는 신호입니다.']
    return '\n'.join(lines)


def divergence_message(current, market, div):
    direction = '선물시장이 IB 중심경로보다 더 높은 금리를 반영' if div['gap_bp'] > 0 else '선물시장이 IB 중심경로보다 더 낮은 금리를 반영'
    lines = ['<b>[FOMC 주요 IB 사후 정책경로 · 괴리]</b>', '',
             '<b>무엇이 달라졌나</b>',
             f"• 공개확인 IB 중심경로: 약 {div['ib_center']:.3f}%",
             f"• 선물시장 연말 확률가중 경로: 약 {div['market_year_end']:.3f}%",
             f"• 괴리: {div['gap_bp']:+.1f}bp — {html.escape(direction)}", '',
             '<b>쉽게 말하면</b>',
             '• IB 전망과 실제 금리선물 가격이 25bp 이상 벌어진 구간입니다. 말보다 시장 가격이 한 번의 25bp 움직임 이상 다르게 보고 있다는 뜻입니다.',
             '• 괴리가 다시 25bp 안으로 들어오면 별도 해소 알림은 보내지 않고 상태만 갱신합니다.', '',
             '<b>원천</b>',
             f"{link('연방기금금리 선물 기반 경로', market.get('source') or '')} · {link('연준 경제전망·점도표', FED_SEP)}"]
    return '\n'.join(lines)


def main():
    old = load(STATE, {})
    market = market_path()
    if not old:
        divergence = divergence_view(CONFIRMED_BASE, market)
        state = {'confirmed': CONFIRMED_BASE, 'tracking': TRACKING_BASE, 'candidate_seen': [], 'market': market, 'divergence': divergence}
        send(snapshot_message(CONFIRMED_BASE, TRACKING_BASE, market, 'FOMC 사후 기준선'))
        save(state)
        print(json.dumps({'first_run': True, 'sent': True, 'confirmed': counts(CONFIRMED_BASE), 'market': market, 'divergence': divergence}, ensure_ascii=False))
        return

    current = old.get('confirmed') or CONFIRMED_BASE
    changes, candidates = evidence_updates(current)
    sent = False
    if changes:
        for c in changes:
            new = dict(c['new']); new['status'] = '교차검증 확인'; new['source'] = c['evidence'][0]['url']
            current[c['institution']] = new

    divergence = divergence_view(current, market)
    divergence_alert = divergence_triggered(old.get('divergence') or {}, divergence)

    if changes:
        send(change_message(changes, current, market)); sent = True
    elif divergence_alert:
        send(divergence_message(current, market, divergence)); sent = True

    # 단일 출처 변화는 상태에만 기록해 두고 공개 원문/두 번째 출처가 붙기 전 전체 경로에 반영하지 않습니다.
    seen = set(old.get('candidate_seen') or [])
    for c in candidates:
        raw = c['institution'] + '|' + json.dumps(c['new'], sort_keys=True, ensure_ascii=False)
        seen.add(hashlib.sha256(raw.encode()).hexdigest()[:20])

    if FORCE and not sent:
        send(snapshot_message(current, old.get('tracking') or TRACKING_BASE, market, '수동 재확인'))
        sent = True
    save({'confirmed': current, 'tracking': old.get('tracking') or TRACKING_BASE, 'candidate_seen': sorted(seen), 'market': market, 'divergence': divergence})
    print(json.dumps({'first_run': False, 'sent': sent, 'confirmed_changes': len(changes), 'candidates': len(candidates), 'divergence_alert': divergence_alert, 'confirmed': counts(current), 'market': market, 'divergence': divergence}, ensure_ascii=False))


if __name__ == '__main__':
    main()

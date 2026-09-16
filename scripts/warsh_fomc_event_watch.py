#!/usr/bin/env python3
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE_PATH = Path('data/warsh_fomc_event_watch_state.json')
FED_CALENDAR = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
EVENT_DATE = '2026-09-16'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/3.0; +https://github.com/qedgwangju-dot/khs-watch)'

JPM_RANGES = {
    '동결': '-1.25%~-1.75%',
    '25bp 인상 + 가이던스 부재/제한': '+0.25%~+0.75%',
    '25bp 인상 + 추가 긴축 시사': '+0.50%~+1.00%',
    '25bp 인상 + 높은 중립금리 강조': '-0.25%~-1.00%',
    '25bp 인상 + 훨씬 더 높은 금리 필요': '-1.00%~-2.00%',
}

MARKET_SYMBOLS = {
    '2년물': '^UST2Y',
    '10년물': '^TNX',
    'S&P 500': '^GSPC',
    '나스닥': '^IXIC',
    '달러지수': 'DX-Y.NYB',
    '금': 'GC=F',
    '비트코인': 'BTC-USD',
}


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace'), r.geturl()


def clean_text(raw):
    raw = re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>', ' ', raw)
    raw = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>', '\n', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    text = html.unescape(raw).replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()


def find_latest_urls():
    raw, _ = fetch(FED_CALENDAR)
    statements = re.findall(r'href=["\']([^"\']*/newsevents/pressreleases/monetary(\d{8})a\.htm)["\']', raw, re.I)
    projections = re.findall(r'href=["\']([^"\']*/monetarypolicy/fomcprojtabl(\d{8})\.htm)["\']', raw, re.I)
    def choose(rows):
        vals = [(d, urllib.parse.urljoin(FED_CALENDAR, u)) for u, d in rows]
        return max(vals)[1] if vals else None
    return choose(statements), choose(projections)


def date_from_url(url):
    m = re.search(r'(?:monetary|fomcprojtabl)(\d{8})', url or '')
    if not m:
        return None
    d = m.group(1)
    return f'{d[:4]}-{d[4:6]}-{d[6:]}'


def parse_mixed_rate(token):
    token = token.strip().replace('–', '-').replace('—', '-').replace('−', '-')
    if re.fullmatch(r'\d+(?:\.\d+)?', token):
        return float(token)
    m = re.fullmatch(r'(\d+)-(\d+)/(\d+)', token)
    if m:
        return float(m.group(1)) + float(m.group(2)) / float(m.group(3))
    return None


def parse_statement(url):
    raw, final = fetch(url)
    text = clean_text(raw)
    low = high = None
    pats = [
        r'target range for the federal funds rate.*?to\s+([0-9]+(?:-[0-9]+/[0-9]+)?(?:\.[0-9]+)?)\s+to\s+([0-9]+(?:-[0-9]+/[0-9]+)?(?:\.[0-9]+)?)\s+percent',
        r'target range for the federal funds rate.*?at\s+([0-9]+(?:-[0-9]+/[0-9]+)?(?:\.[0-9]+)?)\s+to\s+([0-9]+(?:-[0-9]+/[0-9]+)?(?:\.[0-9]+)?)\s+percent',
    ]
    for pat in pats:
        m = re.search(pat, text, re.I | re.S)
        if m:
            low, high = parse_mixed_rate(m.group(1)), parse_mixed_rate(m.group(2))
            break
    against = None
    m = re.search(r'(Voting against this action were[^.]*\.)', text, re.I)
    if m:
        against = re.sub(r'\s+', ' ', m.group(1)).strip()
    return {
        'url': final,
        'date': date_from_url(final),
        'low': low,
        'high': high,
        'mid': (low + high) / 2 if low is not None and high is not None else None,
        'against': against,
    }


def first_numbers_after(label, text, count=4):
    m = re.search(re.escape(label) + r'\s+((?:[0-9]+(?:\.[0-9]+)?\s+){' + str(count) + r',})', text, re.I)
    if not m:
        return []
    return [float(x) for x in re.findall(r'[0-9]+(?:\.[0-9]+)?', m.group(1))[:count]]


def parse_sep(url):
    if not url:
        return None
    try:
        raw, final = fetch(url)
    except Exception:
        return None
    text = clean_text(raw)
    funds = first_numbers_after('Federal funds rate', text, 4)
    pce = first_numbers_after('PCE inflation', text, 4)
    core = first_numbers_after('Core PCE inflation', text, 3)
    unemp = first_numbers_after('Unemployment rate', text, 4)
    if len(funds) < 4:
        return None
    return {
        'url': final,
        'date': date_from_url(final),
        'funds_2026': funds[0], 'funds_2027': funds[1], 'funds_2028': funds[2], 'funds_longer': funds[3],
        'pce_2026': pce[0] if len(pce) > 0 else None,
        'core_pce_2026': core[0] if len(core) > 0 else None,
        'unemployment_2026': unemp[0] if len(unemp) > 0 else None,
    }


def yahoo_latest(symbol):
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(symbol, safe='') + '?range=1d&interval=5m&includePrePost=false'
    raw, _ = fetch(url, timeout=20)
    d = json.loads(raw)
    r = ((d.get('chart') or {}).get('result') or [None])[0]
    if not r:
        return None
    ts = r.get('timestamp') or []
    q = (((r.get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
    rows = [(t, float(v)) for t, v in zip(ts, q) if v is not None]
    if not rows:
        return None
    t, value = rows[-1]
    return {'value': value, 'timestamp': datetime.fromtimestamp(t, timezone.utc).isoformat()}


def market_snapshot():
    out = {}
    for name, sym in MARKET_SYMBOLS.items():
        try:
            q = yahoo_latest(sym)
            if q:
                out[name] = q
        except Exception:
            pass
    return out


def market_changes(pre, cur):
    out = {}
    for name in MARKET_SYMBOLS:
        if name not in pre or name not in cur:
            continue
        a, b = pre[name]['value'], cur[name]['value']
        if name in ('2년물', '10년물'):
            out[name] = {'start': a, 'end': b, 'change_bp': (b-a)*100.0}
        else:
            out[name] = {'start': a, 'end': b, 'change_pct': (b/a-1)*100.0 if a else None}
    return out


def market_read(ch):
    y2 = ch.get('2년물', {}).get('change_bp')
    y10 = ch.get('10년물', {}).get('change_bp')
    sp = ch.get('S&P 500', {}).get('change_pct')
    if y2 is not None and y10 is not None:
        if y2 >= 5 and y10 <= 0:
            return '2년물은 오르지만 10년물이 안정/하락 → 단기 정책금리 기대는 올라가도 장기 물가·할인율 불안은 완화되는 비교적 주식 우호적 조합입니다.'
        if y2 >= 5 and y10 >= 5:
            return '2년물과 10년물이 함께 상승 → 추가긴축 기대와 장기 할인율 부담이 동시에 커지는 주식 부담 조합입니다.'
        if y2 <= -5 and y10 <= -5:
            return '2년물·10년물이 함께 하락 → 추가긴축 기대와 장기 할인율 부담이 같이 완화되는 방향입니다.'
    if sp is not None:
        return f'S&P 500이 발표 전 대비 {sp:+.2f}% 움직였습니다. 금리 반응과 함께 봐야 방향을 확정할 수 있습니다.'
    return '시장 반응 데이터가 충분하지 않아 금리·주가 조합 판정을 보류합니다.'


def scenario(rate_change_bp, new_mid, sep_new, sep_old, news_class=None):
    if rate_change_bp is None:
        return '판정 보류'
    if rate_change_bp < 12.5:
        return '동결'
    if rate_change_bp <= 37.5:
        if news_class == '훨씬 더 높은 금리 필요':
            return '25bp 인상 + 훨씬 더 높은 금리 필요'
        if sep_new and sep_old and sep_new.get('funds_longer') is not None and sep_old.get('funds_longer') is not None:
            if sep_new['funds_longer'] - sep_old['funds_longer'] >= 0.125:
                return '25bp 인상 + 높은 중립금리 강조'
        if sep_new and new_mid is not None and sep_new.get('funds_2026') is not None:
            extra = (sep_new['funds_2026'] - new_mid) * 100.0
            if extra >= 18.75:
                return '25bp 인상 + 추가 긴축 시사'
        if news_class == '추가 긴축 시사':
            return '25bp 인상 + 추가 긴축 시사'
        return '25bp 인상 + 가이던스 부재/제한'
    return '50bp 이상 빅스텝'


def trusted_headlines():
    q = urllib.parse.quote('Kevin Warsh Fed September 16 2026 rates neutral rate further hikes')
    url = f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en'
    try:
        raw, _ = fetch(url)
        root = ET.fromstring(raw)
    except Exception:
        return [], None
    trusted = {'Reuters', 'The Wall Street Journal', 'WSJ', 'CNBC', 'Bloomberg', 'Financial Times'}
    rows = []
    for item in root.findall('.//item')[:30]:
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        src = item.find('source')
        publisher = (src.text or '').strip() if src is not None else ''
        if publisher not in trusted:
            continue
        rows.append({'title': title, 'url': link, 'publisher': publisher})
    joined = ' '.join(x['title'].lower() for x in rows)
    cls = None
    if re.search(r'much higher|substantially higher|far higher', joined):
        cls = '훨씬 더 높은 금리 필요'
    elif re.search(r'neutral rate.*higher|higher neutral rate|r-star.*higher', joined):
        cls = '높은 중립금리 강조'
    elif re.search(r'further hikes|additional hikes|more hikes|further tightening|additional tightening', joined):
        cls = '추가 긴축 시사'
    elif re.search(r'no guidance|no forward guidance|data dependent|not precommit', joined):
        cls = '가이던스 부재/제한'
    return rows[:5], cls


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {}
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def botname():
    if not TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN secret is missing')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        d = json.loads(r.read().decode())
    return str((d.get('result') or {}).get('username') or '')


def link(label, url):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def send(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError('Telegram token/chat id missing')
    actual = botname()
    if actual.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{actual}')
    data = urllib.parse.urlencode({'chat_id': CHAT_ID, 'text': text[:4090], 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data=data, method='POST')
    with urllib.request.urlopen(req, timeout=25) as r:
        out = json.loads(r.read().decode())
    if not out.get('ok'):
        raise RuntimeError(f'Telegram send failed: {out}')


def fmt_market(ch):
    lines = []
    for name in ('2년물','10년물'):
        if name in ch:
            x = ch[name]
            lines.append(f"• {name}: {x['start']:.3f}% → {x['end']:.3f}% ({x['change_bp']:+.1f}bp)")
    for name in ('S&P 500','나스닥','달러지수','금','비트코인'):
        if name in ch and ch[name].get('change_pct') is not None:
            lines.append(f"• {name}: 발표 전 대비 {ch[name]['change_pct']:+.2f}%")
    return lines


def decision_message(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls=None):
    rate_change = None
    if old_stmt and old_stmt.get('mid') is not None and new_stmt.get('mid') is not None:
        rate_change = (new_stmt['mid'] - old_stmt['mid']) * 100.0
    sc = scenario(rate_change, new_stmt.get('mid'), sep_new, sep_old, news_cls)
    ch = market_changes(pre or {}, cur or {})
    lines = [
        '<b>[FOMC 즉시 판정]</b>',
        f"기준: {new_stmt.get('date') or ''}", '',
        '<b>한눈에 보기</b>',
    ]
    if new_stmt.get('low') is not None:
        lines.append(f"• 정책금리 목표범위: {new_stmt['low']:.2f}%~{new_stmt['high']:.2f}%" + (f" · 직전 대비 {rate_change:+.0f}bp" if rate_change is not None else ''))
    lines.append(f"• <b>이벤트 판정: {html.escape(sc)}</b>")
    if sc in JPM_RANGES:
        lines.append(f"• JP모건 당일 S&P 500 시나리오 참고범위: {JPM_RANGES[sc]}")
    lines += ['', '<b>점도표(연준 위원들의 연말 정책금리 전망)</b>']
    if sep_new:
        lines.append(f"• 2026년 말 중앙값 {sep_new['funds_2026']:.3f}% · 2027년 {sep_new['funds_2027']:.3f}% · 장기 {sep_new['funds_longer']:.3f}%")
        if sep_old:
            lines.append(f"• 직전 점도표 대비: 2026년 {sep_new['funds_2026']-sep_old['funds_2026']:+.3f}%p · 장기 {sep_new['funds_longer']-sep_old['funds_longer']:+.3f}%p")
        if new_stmt.get('mid') is not None:
            extra = (sep_new['funds_2026'] - new_stmt['mid']) * 100.0
            lines.append(f"• 현재 회의 후 금리보다 연말 중앙값이 {extra:+.0f}bp 높음 → 연내 추가 인상 경로를 얼마나 남겼는지 보여줍니다.")
    else:
        lines.append('• 새 점도표 공식 페이지 확인 대기')
    if new_stmt.get('against'):
        lines += ['', '<b>투표</b>', f"• {html.escape(new_stmt['against'])}"]
    lines += ['', '<b>시장 반응</b>']
    lines += fmt_market(ch) or ['• 발표 직후 시장 데이터 확인 대기']
    lines += ['', '<b>쉽게 말하면</b>', f"• {market_read(ch)}"]
    if sc == '25bp 인상 + 가이던스 부재/제한':
        lines.append('• 0.25%포인트 인상은 이미 시장이 크게 예상한 조치라, 추가 인상을 강하게 약속하지 않으면 “예상했던 악재가 끝났다”는 안도 반응이 나올 수 있습니다.')
    elif sc == '25bp 인상 + 추가 긴축 시사':
        lines.append('• 추가 인상을 열어뒀더라도 시장이 이미 예상한 범위라면 불확실성 해소가 더 중요할 수 있습니다. 핵심은 10년물이 안정되는지입니다.')
    elif sc == '동결':
        lines.append('• 동결은 처음에는 안도감이 나올 수 있지만, 물가 대응 신뢰가 흔들려 10년물이 급등하면 오히려 주식에는 악재가 될 수 있습니다.')
    lines += ['', '<b>용어</b>',
              '• 25bp = 0.25%포인트',
              '• 중립금리(R-star) = 경기를 과열시키지도 침체시키지도 않는 금리 수준',
              '• 점도표 = 연준 위원들이 각 연말에 적절하다고 보는 정책금리 전망',
              '', '<b>원천</b>', link('연준 FOMC 성명', new_stmt['url'])]
    if sep_new:
        lines[-1] += ' · ' + link('연준 경제전망·점도표', sep_new['url'])
    lines[-1] += ' · ' + link('연준 FOMC 일정', FED_CALENDAR)
    return '\n'.join(lines)


def followup_message(state, label):
    pre = state.get('pre_event_market') or {}
    cur = market_snapshot()
    ch = market_changes(pre, cur)
    headlines, cls = trusted_headlines()
    old_stmt = state.get('previous_statement')
    new_stmt = state.get('current_statement') or {}
    sep_old = state.get('previous_sep')
    sep_new = state.get('current_sep')
    rate_change = None
    if old_stmt and old_stmt.get('mid') is not None and new_stmt.get('mid') is not None:
        rate_change = (new_stmt['mid'] - old_stmt['mid']) * 100.0
    sc = scenario(rate_change, new_stmt.get('mid'), sep_new, sep_old, cls)
    lines = [f'<b>[FOMC 시장 반응 재확인 · {label}]</b>', '', '<b>현재 판정</b>', f'• <b>{html.escape(sc)}</b>', '', '<b>발표 전 대비</b>']
    lines += fmt_market(ch) or ['• 시장 데이터 확인 불가']
    lines += ['', '<b>쉽게 말하면</b>', f'• {market_read(ch)}']
    if headlines:
        lines += ['', '<b>워시 기자회견·보도 확인</b>']
        if cls:
            lines.append(f'• 신뢰보도 헤드라인 기반 보조판정: {html.escape(cls)}')
        for row in headlines[:3]:
            lines.append(f"• {link(row['publisher'], row['url'])}: {html.escape(row['title'])}")
        lines.append('• 위 보조판정은 공식 기자회견 전문이 아니라 신뢰보도 헤드라인 기준이며, 공식 전문 확인 뒤 확정합니다.')
    lines += ['', '<b>다음 확인</b>', '• 2년물이 더 오르는지: 추가 인상 기대', '• 10년물이 5% 위에서 더 오르는지: 장기 할인율·물가 신뢰 부담', '• S&P 500이 금리 반응과 같은 방향으로 움직이는지', '', '<b>원천</b>', link('연준 FOMC 일정', FED_CALENDAR)]
    return '\n'.join(lines), cur, cls


def main():
    now = datetime.now(timezone.utc)
    state = load_state()
    stmt_url, sep_url = find_latest_urls()
    if not stmt_url:
        raise RuntimeError('최신 FOMC 성명 링크 확인 실패')
    stmt = parse_statement(stmt_url)
    sep = parse_sep(sep_url)

    if not state:
        save_state({'last_statement_url': stmt_url, 'current_statement': stmt, 'last_sep_url': sep_url, 'current_sep': sep, 'followups_sent': []})
        print(json.dumps({'first_run': True, 'statement': stmt.get('date'), 'sep': sep.get('date') if sep else None}, ensure_ascii=False))
        return

    # Event-day baseline: capture shortly before the scheduled 2:00 p.m. ET decision.
    if now.date().isoformat() == EVENT_DATE and now.hour == 17 and now.minute >= 40:
        try:
            state['pre_event_market'] = market_snapshot()
            state['pre_event_market_captured_at_utc'] = now.isoformat()
        except Exception:
            pass

    sent = []
    if stmt_url != state.get('last_statement_url'):
        previous_statement = state.get('current_statement')
        previous_sep = state.get('current_sep')
        cur_market = market_snapshot()
        msg = decision_message(previous_statement, stmt, previous_sep, sep, state.get('pre_event_market'), cur_market)
        send(msg)
        sent.append('decision')
        state['previous_statement'] = previous_statement
        state['previous_sep'] = previous_sep
        state['current_statement'] = stmt
        state['last_statement_url'] = stmt_url
        state['event_detected_at_utc'] = now.isoformat()
        state['event_statement_date'] = stmt.get('date')
        state['decision_market'] = cur_market
        state['followups_sent'] = []
        if sep:
            state['current_sep'] = sep
            state['last_sep_url'] = sep_url

    # SEP may appear a little after the statement. Send a compact addendum once.
    if sep and sep_url != state.get('last_sep_url') and state.get('event_statement_date') == EVENT_DATE:
        prev = state.get('previous_sep') or state.get('current_sep')
        lines = ['<b>[FOMC 점도표 추가 확인]</b>', f"• 2026년 말 정책금리 중앙값 {sep['funds_2026']:.3f}%", f"• 2027년 {sep['funds_2027']:.3f}% · 장기 {sep['funds_longer']:.3f}%"]
        if prev:
            lines.append(f"• 직전 대비 2026년 {sep['funds_2026']-prev['funds_2026']:+.3f}%p · 장기 {sep['funds_longer']-prev['funds_longer']:+.3f}%p")
        lines += ['• 장기 금리 중앙값이 올라가면 중립금리(경기를 과열·침체시키지 않는 금리) 자체가 높아졌다는 신호인지 확인합니다.', '', '<b>원천</b>', link('연준 경제전망·점도표', sep['url'])]
        send('\n'.join(lines))
        sent.append('sep')
        state['previous_sep'] = prev
        state['current_sep'] = sep
        state['last_sep_url'] = sep_url

    if state.get('event_statement_date') == EVENT_DATE and state.get('event_detected_at_utc'):
        try:
            detected = datetime.fromisoformat(state['event_detected_at_utc'])
        except Exception:
            detected = now
        elapsed = (now - detected).total_seconds() / 60.0
        fset = set(state.get('followups_sent') or [])
        for label, threshold in [('30분', 25), ('90분', 75)]:
            if elapsed >= threshold and label not in fset:
                msg, cur_market, cls = followup_message(state, label)
                send(msg)
                sent.append(label)
                fset.add(label)
                state['followups_sent'] = sorted(fset)
                state[f'followup_{label}_market'] = cur_market
                if cls:
                    state[f'followup_{label}_news_class'] = cls

    save_state(state)
    print(json.dumps({'first_run': False, 'statement': stmt.get('date'), 'sep': sep.get('date') if sep else None, 'sent': sent, 'event_date': EVENT_DATE}, ensure_ascii=False))


if __name__ == '__main__':
    main()

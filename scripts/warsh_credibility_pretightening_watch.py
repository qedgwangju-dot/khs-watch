#!/usr/bin/env python3
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path('data/warsh_credibility_pretightening_watch_state.json')
PCE_STATE_PATH = Path('data/warsh_pce_trend_watch_state.json')
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'

PRETIGHTEN_2Y_BP = float(os.getenv('WARSH_PRETIGHTEN_2Y_BP') or '15')
PRETIGHTEN_CURVE_BP = float(os.getenv('WARSH_PRETIGHTEN_CURVE_BP') or '8')
PRETIGHTEN_LOOKBACK = int(os.getenv('WARSH_PRETIGHTEN_LOOKBACK') or '5')
CREDIBILITY_STEEPEN_BP = float(os.getenv('WARSH_CREDIBILITY_STEEPEN_BP') or '8')
CREDIBILITY_LONG_END_BP = float(os.getenv('WARSH_CREDIBILITY_LONG_END_BP') or '5')

TREASURY_TEXT_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
FOMC_CALENDAR_URL = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
BLS_API_URL = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
BLS_EMP_URL = 'https://www.bls.gov/news.release/empsit.htm'
BLS_CPI_URL = 'https://www.bls.gov/news.release/cpi.nr0.htm'


def treasury_xml_url(year: int) -> str:
    return ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
            f'?data=daily_treasury_yield_curve&field_tdr_date_value={year}')


def fetch_text(url: str, accept: str = 'text/html,*/*') -> tuple[str, str]:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace'), r.geturl()


def fetch_bytes(url: str, accept: str = '*/*') -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'User-Agent': UA, 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def clean_text(raw: str) -> str:
    raw = re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>', ' ', raw)
    raw = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>', '\n', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    raw = html.unescape(raw).replace('\xa0', ' ')
    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'\n\s*\n+', '\n', raw)
    return raw.strip()


def treasury_rows():
    year = datetime.now(timezone.utc).year
    raw = fetch_bytes(treasury_xml_url(year), 'application/xml,text/xml,*/*')
    root = ET.fromstring(raw)
    rows = []
    for props in root.findall('.//{*}properties'):
        row = {'date': None, '2y': None, '10y': None, '30y': None}
        for child in list(props):
            name = child.tag.split('}')[-1]
            text = (child.text or '').strip()
            if name == 'NEW_DATE':
                row['date'] = text[:10]
            elif name == 'BC_2YEAR' and text:
                row['2y'] = float(text)
            elif name == 'BC_10YEAR' and text:
                row['10y'] = float(text)
            elif name == 'BC_30YEAR' and text:
                row['30y'] = float(text)
        if row['date'] and all(row[k] is not None for k in ('2y', '10y', '30y')):
            rows.append(row)
    rows.sort(key=lambda x: x['date'])
    if len(rows) < PRETIGHTEN_LOOKBACK + 1:
        raise RuntimeError('미 재무부 금리 데이터가 충분하지 않습니다.')
    return rows


def spread(row, long_key):
    return (row[long_key] - row['2y']) * 100.0


def bls_macro():
    now = datetime.now(timezone.utc)
    ids = ['CES0000000001', 'LNS14000000', 'CUSR0000SA0L1E']
    data = post_json(BLS_API_URL, {'seriesid': ids, 'startyear': str(now.year - 1), 'endyear': str(now.year)})
    if data.get('status') != 'REQUEST_SUCCEEDED':
        raise RuntimeError(f"BLS API 오류: {data.get('message')}")
    by_id = {}
    for series in data.get('Results', {}).get('series', []):
        vals = {}
        for r in series.get('data', []):
            p = r.get('period', '')
            if re.fullmatch(r'M(0[1-9]|1[0-2])', p):
                vals[(int(r['year']), int(p[1:]))] = float(str(r['value']).replace(',', ''))
        by_id[series['seriesID']] = vals

    payroll = by_id.get('CES0000000001', {})
    unemp = by_id.get('LNS14000000', {})
    core = by_id.get('CUSR0000SA0L1E', {})
    common_emp = sorted(set(payroll) & set(unemp))
    common_core = sorted(core)
    if len(common_emp) < 2 or len(common_core) < 2:
        raise RuntimeError('BLS 고용/CPI 시계열이 부족합니다.')
    ep, ep0 = common_emp[-1], common_emp[-2]
    cp, cp0 = common_core[-1], common_core[-2]
    payroll_change = payroll[ep] - payroll[ep0]
    unemp_change = unemp[ep] - unemp[ep0]
    core_mom = (core[cp] / core[cp0] - 1.0) * 100.0
    return {
        'employment_period': f'{ep[0]}-{ep[1]:02d}',
        'payroll_change_k': payroll_change,
        'unemployment_rate': unemp[ep],
        'unemployment_change_pp': unemp_change,
        'cpi_period': f'{cp[0]}-{cp[1]:02d}',
        'core_cpi_mom': core_mom,
        'employment_soft': payroll_change <= 50.0 or unemp_change >= 0.2,
        'inflation_cooling': core_mom <= 0.205,
    }


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def load_state():
    return load_json(STATE_PATH, {})


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def pce_context():
    p = load_json(PCE_STATE_PATH, {})
    core_yoy = p.get('core_yoy')
    core_6m = p.get('core_6m_ann')
    sticky = False
    if isinstance(core_yoy, (int, float)) and core_yoy >= 2.8:
        sticky = True
    if isinstance(core_6m, (int, float)) and core_6m >= 3.0:
        sticky = True
    return {
        'regime': p.get('regime', '확인 필요'),
        'core_yoy': core_yoy,
        'core_6m_ann': core_6m,
        'sticky': sticky,
    }


def parse_num_token(token: str) -> float:
    token = token.strip().replace('–', '-').replace('—', '-')
    if re.fullmatch(r'\d+(?:\.\d+)?', token):
        return float(token)
    m = re.fullmatch(r'(\d+)-(\d+)/(\d+)', token)
    if m:
        return float(m.group(1)) + float(m.group(2)) / float(m.group(3))
    m = re.fullmatch(r'(\d+)/(\d+)', token)
    if m:
        return float(m.group(1)) / float(m.group(2))
    raise ValueError(token)


def statement_range(text: str):
    patterns = [
        r'target range for the federal funds rate (?:at|to)\s+([0-9.]+|\d+-\d+/\d+)\s+to\s+([0-9.]+|\d+-\d+/\d+)\s+percent',
        r'target range[^\n.]{0,120}?([0-9.]+|\d+-\d+/\d+)\s+to\s+([0-9.]+|\d+-\d+/\d+)\s+percent',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return parse_num_token(m.group(1)), parse_num_token(m.group(2))
    return None


def fomc_statements():
    raw, _ = fetch_text(FOMC_CALENDAR_URL)
    hrefs = re.findall(r'href=["\']([^"\']*/newsevents/pressreleases/monetary(\d{8})a\.htm)["\']', raw, flags=re.I)
    found = {}
    for href, ds in hrefs:
        url = urllib.parse.urljoin(FOMC_CALENDAR_URL, href)
        found[ds] = url
    if len(found) < 2:
        raise RuntimeError('FOMC 성명 링크를 2개 이상 찾지 못했습니다.')
    ordered = sorted(found.items())
    out = []
    for ds, url in ordered[-3:]:
        body, final = fetch_text(url)
        text = clean_text(body)
        rng = statement_range(text)
        out.append({'date': f'{ds[:4]}-{ds[4:6]}-{ds[6:]}', 'url': final, 'range': rng, 'text': text})
    return out


def get_bot_username():
    if not TOKEN:
        raise RuntimeError('Telegram 토큰이 없습니다.')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError('Telegram getMe 실패')
    return str((data.get('result') or {}).get('username') or '')


def send_html(text: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError('Telegram 토큰/대화방 ID가 없습니다.')
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f'잘못된 Telegram 봇: expected @{EXPECTED_BOT}, got @{username}')
    payload = urllib.parse.urlencode({'chat_id': CHAT_ID, 'text': text[:4090], 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode('utf-8')
    req = urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data=payload, method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError(f'Telegram 전송 실패: {data}')


def pretightening_snapshot(rows, macro):
    latest = rows[-1]
    base = rows[-1 - PRETIGHTEN_LOOKBACK]
    d2 = (latest['2y'] - base['2y']) * 100.0
    d210 = spread(latest, '10y') - spread(base, '10y')
    d230 = spread(latest, '30y') - spread(base, '30y')
    avg_curve = (d210 + d230) / 2.0
    active = d2 >= PRETIGHTEN_2Y_BP and avg_curve <= -PRETIGHTEN_CURVE_BP

    if active and macro['employment_soft'] and macro['inflation_cooling']:
        verdict = '시장이 먼저 긴축했고 경제지표도 식는 중 — 실제 추가 인상 필요성이 일부 낮아질 수 있음'
    elif active and not macro['employment_soft'] and not macro['inflation_cooling']:
        verdict = '시장이 먼저 긴축했지만 고용·물가도 강함 — 실제 인상 논리는 아직 유지'
    elif active:
        verdict = '시장 선긴축 후보 — 고용·물가가 같은 방향인지 추가 확인 필요'
    else:
        verdict = '시장 선긴축 기준 미충족'

    return {
        'date': latest['date'], 'base_date': base['date'], 'active': active, 'd2_bp': d2,
        'd2s10s_bp': d210, 'd2s30s_bp': d230, 'avg_curve_bp': avg_curve, 'verdict': verdict,
    }


def pretightening_message(snap, macro):
    return '\n'.join([
        '<b>[워시 반응함수 · 시장이 먼저 긴축했는지 감지]</b>',
        f"기간: {html.escape(snap['base_date'])} → {html.escape(snap['date'])} ({PRETIGHTEN_LOOKBACK}거래일)",
        f"미 국채 2년물: {snap['d2_bp']:+.1f}bp",
        f"2년-10년 금리차: {snap['d2s10s_bp']:+.1f}bp | 2년-30년 금리차: {snap['d2s30s_bp']:+.1f}bp",
        '',
        f"고용: 비농업 고용 {macro['payroll_change_k']:+.0f}천명 / 실업률 {macro['unemployment_rate']:.1f}%",
        f"근원 소비자물가: 전월 대비 {macro['core_cpi_mom']:+.2f}%",
        '',
        f"판정: <b>{html.escape(snap['verdict'])}</b>",
        '쉽게 보면: 연준이 실제 금리를 올리기 전에 2년물 금리가 먼저 크게 오르면 시장금리 자체가 대출·투자를 억제합니다. 이후 고용과 물가까지 식으면 연준이 추가로 금리를 올릴 필요가 줄 수 있습니다.',
        '※ 1bp = 0.01%포인트',
        '',
        f'<a href="{html.escape(TREASURY_TEXT_URL, quote=True)}">미 재무부 공식 금리 원천</a> · <a href="{html.escape(BLS_EMP_URL, quote=True)}">미 노동부 고용 원천</a> · <a href="{html.escape(BLS_CPI_URL, quote=True)}">미 노동부 물가 원천</a>',
    ])


def find_event_row(rows, event_date):
    for i, r in enumerate(rows):
        if r['date'] >= event_date:
            if i == 0:
                return None, None
            return rows[i - 1], r
    return None, None


def credibility_verdict(delta_mid_bp, before, after, macro, pce):
    d2 = (after['2y'] - before['2y']) * 100.0
    d30 = (after['30y'] - before['30y']) * 100.0
    d230 = spread(after, '30y') - spread(before, '30y')
    sticky = pce['sticky']
    cooling = macro['employment_soft'] and macro['inflation_cooling']

    if delta_mid_bp >= 20:
        if d230 <= -5 or d2 >= d30 + 5:
            return '인상 실행 + 장기금리 상대 안정 — 워시의 물가대응 말과 행동이 일치하고 신뢰가 강화되는 패턴'
        if d30 >= CREDIBILITY_LONG_END_BP and d230 >= CREDIBILITY_STEEPEN_BP:
            return '금리를 올렸지만 장기금리도 더 크게 상승 — 시장이 물가·재정 위험을 아직 신뢰하지 않는 패턴'
        return '금리 인상 실행 — 장기채 반응은 혼합, 신뢰 강화 여부 추가 확인'

    if abs(delta_mid_bp) < 10:
        if sticky and d30 >= CREDIBILITY_LONG_END_BP and d230 >= CREDIBILITY_STEEPEN_BP:
            return '높은 물가 속 동결 + 장기금리 상승·금리차 확대 — 7월형 말-행동 괴리와 신뢰 우려 재발 가능성'
        if cooling:
            return '동결했지만 고용·물가 둔화가 확인 — 데이터에 따른 동결 근거가 있어 신뢰 훼손으로 단정하기 어려움'
        if sticky and d230 <= 0:
            return '높은 물가 속 동결이지만 장기채 반응 안정 — 시장이 설명을 일단 수용한 패턴'
        return '동결 — 물가·고용과 장기채 반응이 혼합돼 신뢰 판정 보류'

    if delta_mid_bp <= -20:
        if cooling:
            return '금리 인하 + 고용·물가 둔화 — 완화 근거가 데이터에서 확인되는 패턴'
        if sticky and d30 >= CREDIBILITY_LONG_END_BP:
            return '물가 고착 속 금리 인하 + 장기금리 상승 — 정책 신뢰 부담이 커지는 패턴'
        return '금리 인하 — 데이터와 장기채 반응을 추가 확인'

    return '정책금리 변화가 비정형적 — 추가 확인 필요'


def credibility_message(event, before, after, macro, pce):
    old_mid = sum(event['old_range']) / 2.0
    new_mid = sum(event['new_range']) / 2.0
    delta_mid_bp = (new_mid - old_mid) * 100.0
    d2 = (after['2y'] - before['2y']) * 100.0
    d10 = (after['10y'] - before['10y']) * 100.0
    d30 = (after['30y'] - before['30y']) * 100.0
    d210 = spread(after, '10y') - spread(before, '10y')
    d230 = spread(after, '30y') - spread(before, '30y')
    verdict = credibility_verdict(delta_mid_bp, before, after, macro, pce)
    action = '인상' if delta_mid_bp >= 20 else ('인하' if delta_mid_bp <= -20 else '동결')
    return '\n'.join([
        '<b>[워시 FOMC · 말과 행동 신뢰도 판정]</b>',
        f"FOMC: {html.escape(event['date'])} | 결정: <b>{action}</b>",
        f"정책금리 범위: {event['old_range'][0]:.2f}~{event['old_range'][1]:.2f}% → {event['new_range'][0]:.2f}~{event['new_range'][1]:.2f}%",
        '',
        f"FOMC 전후 미 국채: 2년 {d2:+.1f}bp | 10년 {d10:+.1f}bp | 30년 {d30:+.1f}bp",
        f"금리차 변화: 2년-10년 {d210:+.1f}bp | 2년-30년 {d230:+.1f}bp",
        f"물가 추세: {html.escape(str(pce['regime']))}",
        f"고용: 비농업 고용 {macro['payroll_change_k']:+.0f}천명 / 실업률 {macro['unemployment_rate']:.1f}% | 근원 소비자물가 전월 대비 {macro['core_cpi_mom']:+.2f}%",
        '',
        f"판정: <b>{html.escape(verdict)}</b>",
        '쉽게 보면: 인상·동결 자체보다 그 뒤 30년물과 장단기 금리차가 어떻게 움직이는지가 시장이 연준의 물가대응을 믿는지 보여줍니다.',
        '※ 1bp = 0.01%포인트',
        '',
        f'<a href="{html.escape(event['url'], quote=True)}">연준 FOMC 공식 성명</a> · <a href="{html.escape(TREASURY_TEXT_URL, quote=True)}">미 재무부 공식 금리 원천</a>',
    ])


def main():
    state = load_state()
    first_run = not bool(state)
    rows = treasury_rows()
    macro = bls_macro()
    pce = pce_context()
    statements = fomc_statements()
    latest_stmt = statements[-1]
    prev_stmt = statements[-2]

    if not latest_stmt['range'] or not prev_stmt['range']:
        raise RuntimeError('FOMC 정책금리 범위를 성명에서 읽지 못했습니다.')

    # 1) 시장이 연준 대신 먼저 긴축했는지: 5거래일 2Y +15bp 이상 + 금리차 평균 8bp 이상 축소.
    pre = pretightening_snapshot(rows, macro)
    prev_active = bool(state.get('pretightening_active', False))
    new_treasury_date = state.get('treasury_date') not in (None, pre['date'])
    if FORCE_NOTIFY or (new_treasury_date and pre['active'] and not prev_active):
        send_html(pretightening_message(pre, macro))
    elif new_treasury_date and prev_active and not pre['active']:
        msg = '\n'.join([
            '<b>[워시 반응함수 · 시장 선긴축 경보 해제]</b>',
            f"기준일 {html.escape(pre['date'])}",
            f"최근 {PRETIGHTEN_LOOKBACK}거래일 2년물 {pre['d2_bp']:+.1f}bp / 금리차 평균 {pre['avg_curve_bp']:+.1f}bp",
            '판정: 2년물 급등과 장단기 금리차 축소가 설정 기준 아래로 내려왔습니다. 시장이 연준 대신 긴축하는 압력은 이전보다 약해졌습니다.',
            '',
            f'<a href="{html.escape(TREASURY_TEXT_URL, quote=True)}">미 재무부 공식 금리 원천</a>',
        ])
        send_html(msg)

    # 2) 새 FOMC가 나오면, 같은 날(또는 이후 첫 공식일) Treasury 종가가 생길 때 말-행동 신뢰도를 1회 판정.
    last_seen_fomc = state.get('last_seen_fomc_url')
    pending = state.get('pending_fomc')
    if first_run:
        # 설치 시 과거 7월 FOMC를 새 이벤트로 재발송하지 않고 기준선만 저장.
        last_seen_fomc = latest_stmt['url']
    elif latest_stmt['url'] != last_seen_fomc:
        pending = {
            'date': latest_stmt['date'],
            'url': latest_stmt['url'],
            'old_range': list(prev_stmt['range']),
            'new_range': list(latest_stmt['range']),
        }
        last_seen_fomc = latest_stmt['url']

    credibility_done = False
    if pending:
        before, after = find_event_row(rows, pending['date'])
        if before and after:
            send_html(credibility_message(pending, before, after, macro, pce))
            pending = None
            credibility_done = True

    save_state({
        'treasury_date': pre['date'],
        'pretightening_active': pre['active'],
        'pretightening': pre,
        'macro': macro,
        'pce': pce,
        'last_seen_fomc_url': last_seen_fomc,
        'pending_fomc': pending,
        'last_credibility_completed': credibility_done,
    })
    print(json.dumps({
        'first_run': first_run,
        'treasury_date': pre['date'],
        'pretightening_active': pre['active'],
        'pretightening': pre,
        'macro': macro,
        'pce': pce,
        'latest_fomc': latest_stmt['date'],
        'pending_fomc': pending,
        'credibility_done': credibility_done,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

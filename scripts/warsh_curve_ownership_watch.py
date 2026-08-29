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

STATE_PATH = Path('data/warsh_curve_ownership_watch_state.json')
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
CURVE_ALERT_BP = float(os.getenv('TREASURY_CURVE_ALERT_BP') or '5')
BUYBACK_LONG_END_BP = float(os.getenv('TREASURY_BUYBACK_LONG_END_BP') or '5')
BUYBACK_CURVE_BP = float(os.getenv('TREASURY_BUYBACK_CURVE_BP') or '3')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'

BUYBACK_START = '2026-09-09'
BUYBACK_END = '2026-11-04'
BUYBACK_RELEASE_URL = 'https://home.treasury.gov/news/press-releases/sb0607'
BUYBACK_SCHEDULE_URL = 'https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml'
TREASURY_TEXT_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'


def treasury_xml_url(year: int) -> str:
    return ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
            f'?data=daily_treasury_yield_curve&field_tdr_date_value={year}')


def fetch_bytes(url: str, accept: str = '*/*') -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def yield_rows():
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
    if len(rows) < 2:
        raise RuntimeError('Treasury curve XML: not enough 2Y/10Y/30Y rows')
    rows.sort(key=lambda x: x['date'])
    return rows


def fp(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def get_bot_username() -> str:
    if not TOKEN:
        raise RuntimeError('Telegram token missing')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError('Telegram getMe failed')
    return str((data.get('result') or {}).get('username') or '')


def send_html(text: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError('Telegram token/chat id missing')
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}')
    payload = urllib.parse.urlencode({
        'chat_id': CHAT_ID,
        'text': text[:4090],
        'parse_mode': 'HTML',
        'disable_web_page_preview': 'true',
    }).encode('utf-8')
    req = urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data=payload, method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError(f'Telegram send failed: {data}')


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def spread(row, long_key):
    return (row[long_key] - row['2y']) * 100.0


def curve_label(d210, d230, current, prev):
    avg_spread = (d210 + d230) / 2.0
    d2 = (current['2y'] - prev['2y']) * 100.0
    dlong = (((current['10y'] - prev['10y']) + (current['30y'] - prev['30y'])) / 2.0) * 100.0
    if avg_spread < 0:
        if d2 > 0:
            return '단기금리가 더 많이 올라 장단기 금리차 축소'
        if dlong < 0:
            return '장기금리가 더 많이 내려 장단기 금리차 축소'
        return '장단기 금리차 축소'
    if avg_spread > 0:
        if dlong > 0:
            return '장기금리가 더 많이 올라 장단기 금리차 확대'
        if d2 < 0:
            return '단기금리가 더 많이 내려 장단기 금리차 확대'
        return '장단기 금리차 확대'
    return '장단기 금리차 변화 제한적'


def curve_message(current, prev):
    s210 = spread(current, '10y')
    s230 = spread(current, '30y')
    p210 = spread(prev, '10y')
    p230 = spread(prev, '30y')
    d210 = s210 - p210
    d230 = s230 - p230
    verdict = curve_label(d210, d230, current, prev)
    return '\n'.join([
        '<b>[Warsh·미 재무부 금리곡선 변화]</b>',
        f"기준일 {html.escape(current['date'])}",
        f"미 국채 2년 {current['2y']:.2f}% | 10년 {current['10y']:.2f}% | 30년 {current['30y']:.2f}%",
        '',
        f"2년-10년 금리차(2s10s) {s210:+.0f}bp (전일 대비 {d210:+.1f}bp)",
        f"2년-30년 금리차(2s30s) {s230:+.0f}bp (전일 대비 {d230:+.1f}bp)",
        f"판정: <b>{html.escape(verdict)}</b>",
        '',
        '쉽게 보면: 2년물이 상대적으로 더 오르면 연준(Fed)의 금리 전망 영향이 강한 것이고, 10~30년물이 상대적으로 더 오르면 재정·국채공급·인플레이션 위험 때문에 시장이 장기채에 더 높은 보상을 요구하는 것입니다.',
        '※ 1bp = 0.01%포인트',
        '',
        f'<a href="{html.escape(TREASURY_TEXT_URL, quote=True)}">미 재무부 공식 금리 원천</a>',
    ])


def buyback_market_message(current, prev, d210, d230):
    d2 = (current['2y'] - prev['2y']) * 100.0
    d10 = (current['10y'] - prev['10y']) * 100.0
    d30 = (current['30y'] - prev['30y']) * 100.0
    avg_long = (d10 + d30) / 2.0
    avg_curve = (d210 + d230) / 2.0

    if avg_long <= -BUYBACK_LONG_END_BP and avg_curve <= -BUYBACK_CURVE_BP:
        verdict = '미 재무부의 장기국채 재매입 효과와 같은 방향'
        detail = '10년·30년 금리가 함께 내리고 장단기 금리차도 축소 → 장기국채 유동성 지원 정책이 시장 방향과 맞아떨어진 패턴'
    elif avg_long >= BUYBACK_LONG_END_BP and avg_curve >= BUYBACK_CURVE_BP:
        verdict = '시장 장기금리 상승 압력이 재매입 효과보다 우세'
        detail = '10년·30년 금리가 함께 오르고 장단기 금리차도 확대 → 재무부가 국채를 재매입해도 시장이 장기채에 더 높은 금리를 요구하는 패턴'
    else:
        return None

    return '\n'.join([
        '<b>[미 재무부 장기국채 재매입 효과 감지]</b>',
        f"기준일 {html.escape(current['date'])} | 확대 적용기간 {BUYBACK_START}~{BUYBACK_END}",
        f"2년 금리 {d2:+.1f}bp | 10년 {d10:+.1f}bp | 30년 {d30:+.1f}bp",
        f"2년-10년 금리차 변화 {d210:+.1f}bp | 2년-30년 금리차 변화 {d230:+.1f}bp",
        '',
        f"판정: <b>{html.escape(verdict)}</b>",
        f"• {html.escape(detail)}",
        '• 주의: 이 알림은 수익률곡선의 시장 반응을 보는 것이며, 특정 날짜의 국채 재매입(Buyback) 한 번만으로 금리가 움직였다고 단정하지 않습니다.',
        '※ 1bp = 0.01%포인트',
        '',
        f'<a href="{html.escape(BUYBACK_RELEASE_URL, quote=True)}">미 재무부 공식 발표</a>',
    ])


def schedule_message():
    return '\n'.join([
        '<b>[미 재무부 장기국채 재매입 일정 변경]</b>',
        '미 재무부의 공식 국채 재매입 예정 일정이 변경됐습니다.',
        '10~20년물·20~30년물의 재매입 날짜와 최대 매입 한도가 달라졌는지 확인하세요.',
        '',
        f'<a href="{html.escape(BUYBACK_SCHEDULE_URL, quote=True)}">미 재무부 공식 재매입 일정</a>',
    ])


def main():
    state = load_state()
    first_run = not bool(state)
    rows = yield_rows()
    current, prev = rows[-1], rows[-2]
    is_new_date = state.get('curve_date') not in (None, current['date'])

    s210 = spread(current, '10y')
    s230 = spread(current, '30y')
    p210 = spread(prev, '10y')
    p230 = spread(prev, '30y')
    d210 = s210 - p210
    d230 = s230 - p230

    # Significant curve move: both spreads move at least threshold in same direction,
    # or either spread moves by 1.5x threshold.
    same_dir = (d210 > 0 and d230 > 0) or (d210 < 0 and d230 < 0)
    significant_curve = (same_dir and abs(d210) >= CURVE_ALERT_BP and abs(d230) >= CURVE_ALERT_BP) or max(abs(d210), abs(d230)) >= CURVE_ALERT_BP * 1.5

    if FORCE_NOTIFY or (is_new_date and significant_curve):
        send_html(curve_message(current, prev))

    # During the announced expanded long-end buyback regime, alert only on a material
    # market pattern consistent with Treasury flattening or a term-premium steepening override.
    buyback_active = BUYBACK_START <= current['date'] <= BUYBACK_END
    if is_new_date and buyback_active:
        msg = buyback_market_message(current, prev, d210, d230)
        if msg:
            send_html(msg)

    # Monitor the official tentative buyback schedule itself. First run establishes baseline.
    schedule_error = None
    schedule_hash = state.get('buyback_schedule_hash')
    try:
        schedule_raw = fetch_bytes(BUYBACK_SCHEDULE_URL, 'application/xml,text/xml,*/*')
        new_schedule_hash = fp(schedule_raw)
        if not first_run and schedule_hash and new_schedule_hash != schedule_hash:
            send_html(schedule_message())
        schedule_hash = new_schedule_hash
    except Exception as e:
        schedule_error = str(e)

    new_state = {
        'curve_date': current['date'],
        '2y': current['2y'],
        '10y': current['10y'],
        '30y': current['30y'],
        '2s10s_bp': s210,
        '2s30s_bp': s230,
        'last_curve_move_2s10s_bp': d210,
        'last_curve_move_2s30s_bp': d230,
        'buyback_active': buyback_active,
        'buyback_schedule_hash': schedule_hash,
        'last_error': schedule_error,
    }
    save_state(new_state)
    print(json.dumps({
        'first_run': first_run,
        'date': current['date'],
        '2s10s_bp': s210,
        '2s30s_bp': s230,
        'd2s10s_bp': d210,
        'd2s30s_bp': d230,
        'significant_curve': significant_curve,
        'buyback_active': buyback_active,
        'schedule_error': schedule_error,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

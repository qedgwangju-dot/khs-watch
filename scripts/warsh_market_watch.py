#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path('data/warsh_market_watch_state.json')
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
THRESHOLD_BP = float(os.getenv('TREASURY_2Y_ALERT_BP') or '10')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'


def treasury_url(year: int) -> str:
    return ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
            f'?data=daily_treasury_yield_curve&field_tdr_date_value={year}')


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def latest_2y():
    year = datetime.now(timezone.utc).year
    raw = fetch(treasury_url(year))
    root = ET.fromstring(raw)
    rows = []
    for props in root.findall('.//{*}properties'):
        date = None
        y2 = None
        for child in list(props):
            name = child.tag.split('}')[-1]
            text = (child.text or '').strip()
            if name == 'NEW_DATE':
                date = text[:10]
            elif name == 'BC_2YEAR' and text:
                try:
                    y2 = float(text)
                except ValueError:
                    pass
        if date and y2 is not None:
            rows.append((date, y2))
    if not rows:
        raise RuntimeError('Treasury XML feed: 2Y rows not found')
    rows.sort(key=lambda x: x[0])
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    return latest, prev, treasury_url(year)


def get_bot_username():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError('Telegram getMe failed')
    return str((data.get('result') or {}).get('username') or '')


def send(text: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError('Telegram token/chat id missing')
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}')
    payload = urllib.parse.urlencode({'chat_id': CHAT_ID, 'text': text, 'disable_web_page_preview': 'true'}).encode('utf-8')
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


def main():
    (date, value), prev, source = latest_2y()
    old = load_state()
    is_new_date = old.get('date') not in (None, date)
    day_bp = None
    if prev:
        day_bp = (value - prev[1]) * 100.0
    meaningful = is_new_date and day_bp is not None and abs(day_bp) >= THRESHOLD_BP
    if FORCE_NOTIFY or meaningful:
        direction = '상승' if (day_bp or 0) > 0 else '하락'
        msg = [
            '[Warsh 반응함수 시장 재가격 감지] 미국 2Y',
            f'미 재무부 공식 2Y: {value:.2f}%',
        ]
        if prev and day_bp is not None:
            msg.append(f'직전 {prev[0]} {prev[1]:.2f}% 대비 {day_bp:+.1f}bp ({direction})')
        msg += [
            '',
            f'판정: 하루 {THRESHOLD_BP:.0f}bp 이상 움직이면 Fed 정책경로 재가격 신호로 알림',
            'Warsh의 물가 우선·추가긴축 선택지가 시장금리에 반영되는지 고용/CPI/PCE/FOMC와 함께 확인',
            '',
            f'원천: {source}',
        ]
        send('\n'.join(msg))
    save_state({'date': date, 'value': value, 'prev_date': prev[0] if prev else None, 'prev_value': prev[1] if prev else None})
    print(json.dumps({'date': date, 'value': value, 'day_bp': day_bp, 'meaningful': meaningful}, ensure_ascii=False))


if __name__ == '__main__':
    main()

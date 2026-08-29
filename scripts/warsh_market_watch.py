#!/usr/bin/env python3
import html
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
RETENTION_THRESHOLD = float(os.getenv('TREASURY_2Y_RETENTION_RATIO') or '0.50')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.2; +https://github.com/qedgwangju-dot/khs-watch)'


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


def source_link(url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">원천</a>'


def send(text: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError('Telegram token/chat id missing')
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}')
    payload = urllib.parse.urlencode({
        'chat_id': CHAT_ID,
        'text': text,
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


def same_direction(a: float, b: float) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)


def send_initial_alert(date, value, prev, day_bp, source):
    direction = '상승' if day_bp > 0 else '하락'
    msg = [
        '[Warsh 반응함수 시장 재가격 감지] 미국 2Y',
        f'미 재무부 공식 2Y: {value:.2f}%',
        f'직전 {prev[0]} {prev[1]:.2f}% 대비 {day_bp:+.1f}bp ({direction})',
        '',
        f'1차 판정: 하루 {THRESHOLD_BP:.0f}bp 이상 이동 → Fed 정책경로 재가격 신호',
        f'다음 Treasury 공식 종가에서 최초 움직임의 {RETENTION_THRESHOLD*100:.0f}% 이상 유지되는지 재확인합니다.',
        'Warsh의 물가 우선·추가긴축 선택지가 시장금리에 실제로 남는지 고용/CPI/PCE/FOMC와 함께 판단',
        '',
        source_link(source),
    ]
    send('\n'.join(msg))


def send_followup_alert(current_date, current_value, event, source):
    base = float(event['base_value'])
    event_value = float(event['event_value'])
    original_bp = float(event['move_bp'])
    retained_bp = (current_value - base) * 100.0
    ratio = abs(retained_bp) / abs(original_bp) if original_bp else 0.0
    kept_direction = same_direction(retained_bp, original_bp)
    persistent = kept_direction and ratio >= RETENTION_THRESHOLD

    if persistent:
        verdict = '매파/정책경로 재가격 지속' if original_bp > 0 else '비둘기/완화 재가격 지속'
        detail = f'최초 이동의 {ratio*100:.0f}% 유지 → 일회성 이벤트 반응보다 지속적 재가격 가능성 우세'
    else:
        verdict = '이벤트 당일 과잉반응/포지션 정리 가능성 증가'
        if kept_direction:
            detail = f'최초 이동의 {ratio*100:.0f}%만 유지 → 50% 기준 미달, 상당 부분 반납'
        else:
            detail = '최초 이동 방향까지 되돌림 → 당일 반응의 지속성 약함'

    msg = [
        '[Warsh 반응함수 2Y 지속성 재확인]',
        f"이벤트일 {event['event_date']}: {event_value:.2f}% / 직전 기준 {base:.2f}% / {original_bp:+.1f}bp",
        f'다음 공식일 {current_date}: {current_value:.2f}%',
        f'기준점 대비 잔존 이동: {retained_bp:+.1f}bp',
        '',
        f'판정: {verdict}',
        f'• {detail}',
        '• 당일 반응보다 다음 공식 종가의 유지 여부를 우선해 정책 신호의 지속성을 판정',
        '',
        source_link(source),
    ]
    send('\n'.join(msg))
    return persistent, ratio, retained_bp


def main():
    (date, value), prev, source = latest_2y()
    old = load_state()
    is_new_date = old.get('date') not in (None, date)
    day_bp = (value - prev[1]) * 100.0 if prev else None

    # Follow up exactly once on the next official Treasury date after a large move.
    pending = old.get('pending_event')
    followup_done = False
    if pending and is_new_date and date > str(pending.get('event_date', '')):
        send_followup_alert(date, value, pending, source)
        pending = None
        followup_done = True

    # Bootstrap current large move if this logic was added after the event had already been stored.
    already_alerted = old.get('last_alert_date') == date
    large_move_now = day_bp is not None and abs(day_bp) >= THRESHOLD_BP
    bootstrap_large_move = (not is_new_date and not already_alerted and large_move_now and not old.get('pending_event'))
    meaningful = (is_new_date and large_move_now) or bootstrap_large_move

    if FORCE_NOTIFY or meaningful:
        if prev and day_bp is not None:
            send_initial_alert(date, value, prev, day_bp, source)
            pending = {
                'event_date': date,
                'base_date': prev[0],
                'base_value': prev[1],
                'event_value': value,
                'move_bp': day_bp,
            }
            old['last_alert_date'] = date

    new_state = {
        'date': date,
        'value': value,
        'prev_date': prev[0] if prev else None,
        'prev_value': prev[1] if prev else None,
        'last_alert_date': old.get('last_alert_date'),
        'pending_event': pending,
        'last_followup_completed': followup_done,
    }
    save_state(new_state)
    print(json.dumps({
        'date': date,
        'value': value,
        'day_bp': day_bp,
        'meaningful': meaningful,
        'pending_event': pending,
        'followup_done': followup_done,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

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
    return f'<a href="{html.escape(url, quote=True)}">미 재무부 공식 금리</a>'


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
    policy = '추가긴축 기대가 커지는 쪽' if day_bp > 0 else '추가긴축 기대가 약해지는 쪽'
    msg = [
        '<b>[Warsh 반응함수 · 미 국채 2년물 급변]</b>',
        f'기준일 {date}', '',
        '<b>한눈에 보기</b>',
        f'• <b>2년물</b> | {prev[1]:.2f}% → {value:.2f}% ({day_bp:+.1f}bp)',
        f'• <b>경보 기준</b> | 하루 ±{THRESHOLD_BP:.0f}bp 이상 → 기준 충족',
        f'• <b>1차 의미</b> | 시장이 연준 정책경로를 {policy}으로 크게 다시 가격하는 후보', '',
        '<b>왜 중요한가</b>',
        '• 2년물은 장기물보다 향후 연준 정책금리 기대에 더 민감합니다. 하루 급변만으로 확정하지 않고 다음 공식 종가까지 봅니다.',
        f'• 다음 공식 종가에서 최초 이동의 {RETENTION_THRESHOLD*100:.0f}% 이상 남으면 “하루짜리 튐”보다 지속적 재가격 가능성을 높게 봅니다.', '',
        '<b>다음 확인</b>',
        '• 다음 미 재무부 공식 종가에서 얼마나 유지·반납·추가 확대되는지 확인',
        '• 고용·CPI·PCE가 같은 방향이면 실제 정책경로 신호의 신뢰도가 더 높아집니다.', '',
        source_link(source),
        '※ 1bp = 0.01%포인트',
    ]
    send('\n'.join(msg))


def send_followup_alert(current_date, current_value, event, source):
    base = float(event['base_value'])
    event_value = float(event['event_value'])
    original_bp = float(event['move_bp'])
    retained_bp = (current_value - base) * 100.0
    next_bp = (current_value - event_value) * 100.0
    ratio = abs(retained_bp) / abs(original_bp) if original_bp else 0.0
    kept_direction = same_direction(retained_bp, original_bp)
    persistent = kept_direction and ratio >= RETENTION_THRESHOLD

    if persistent and ratio >= 1.0:
        verdict = '매파 재가격이 더 강해짐' if original_bp > 0 else '완화 재가격이 더 강해짐'
        detail = f'최초 이동을 전부 유지한 뒤 같은 방향으로 {abs(next_bp):.1f}bp 더 움직였습니다.'
    elif persistent:
        verdict = '매파/정책경로 재가격 지속' if original_bp > 0 else '비둘기/완화 재가격 지속'
        detail = f'최초 이동의 {ratio*100:.0f}%가 남아 {RETENTION_THRESHOLD*100:.0f}% 지속 기준을 충족했습니다.'
    else:
        verdict = '이벤트 당일 과잉반응/포지션 정리 가능성 증가'
        if kept_direction:
            detail = f'최초 이동의 {ratio*100:.0f}%만 남아 {RETENTION_THRESHOLD*100:.0f}% 지속 기준에 미달했습니다.'
        else:
            detail = '최초 이동 방향까지 되돌려 당일 반응의 지속성이 약합니다.'

    if ratio >= 1.0 and kept_direction:
        ratio_plain = f'{ratio*100:.0f}% = 최초 움직임 전부 유지 + 추가 확대'
    else:
        ratio_plain = f'{ratio*100:.0f}% = 최초 움직임 가운데 현재 남아 있는 비율'

    msg = [
        '<b>[Warsh 반응함수 · 미 국채 2년물 지속성 재확인]</b>',
        f"이벤트 {event['event_date']} → 재확인 {current_date}", '',
        '<b>한눈에 보기</b>',
        f'• <b>첫날</b> | {base:.2f}% → {event_value:.2f}% ({original_bp:+.1f}bp)',
        f'• <b>다음 공식일</b> | {event_value:.2f}% → {current_value:.2f}% ({next_bp:+.1f}bp)',
        f'• <b>기준점 대비 누적</b> | {base:.2f}% → {current_value:.2f}% ({retained_bp:+.1f}bp)',
        f'• <b>지속률</b> | {ratio_plain}', '',
        f'<b>판정: {html.escape(verdict)}</b>',
        f'• {html.escape(detail)}', '',
        '<b>쉽게 말하면</b>',
        f"• {'첫날 급등 뒤 되돌린 것이 아니라 다음 공식일에도 더 올라 매파 재가격이 이어진 것입니다.' if original_bp > 0 and persistent and ratio >= 1 else '첫날 움직임이 다음 공식일에도 남아 있어 일회성 반응으로 보기 어렵습니다.' if persistent else '첫날 움직임 상당 부분이 사라져 정책 신호로 보기에는 신뢰도가 낮아졌습니다.'}",
        '• 2년물은 연준 정책경로 기대에 민감하므로, 다음날까지 같은 방향이 유지될수록 단순 포지션 정리보다 정책 기대 변화일 가능성이 커집니다.', '',
        '<b>이 판정이 약해지는 조건</b>',
        f'• 기준점 대비 이동이 최초 움직임의 {RETENTION_THRESHOLD*100:.0f}% 아래로 줄거나 방향이 반대로 바뀌는 경우',
        '• 고용·PCE가 빠르게 식어 실제 추가긴축 근거가 약해지는 경우', '',
        source_link(source),
        '※ 1bp = 0.01%포인트',
    ]
    send('\n'.join(msg))
    return persistent, ratio, retained_bp


def main():
    (date, value), prev, source = latest_2y()
    old = load_state()
    is_new_date = old.get('date') not in (None, date)
    day_bp = (value - prev[1]) * 100.0 if prev else None

    pending = old.get('pending_event')
    followup_done = False
    if pending and is_new_date and date > str(pending.get('event_date', '')):
        send_followup_alert(date, value, pending, source)
        pending = None
        followup_done = True

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

#!/usr/bin/env python3
import html
import json
import os
import math
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path

STATE_PATH = Path('data/warsh_market_watch_state.json')
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
THRESHOLD_BP = float(os.getenv('TREASURY_2Y_ALERT_BP') or '10')
RETENTION_THRESHOLD = float(os.getenv('TREASURY_2Y_RETENTION_RATIO') or '0.50')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.2; +https://github.com/qedgwangju-dot/khs-watch)'
NY = ZoneInfo('America/New_York')


def treasury_url(year: int) -> str:
    return ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
            f'?data=daily_treasury_yield_curve&field_tdr_date_value={year}')


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req, timeout=30) as r:
        final = urllib.parse.urlsplit(r.geturl())
        if final.scheme != 'https' or final.hostname != 'home.treasury.gov':
            raise RuntimeError('Treasury source redirected outside official host')
        return r.read()


def bp(new, old):
    return float((Decimal(str(new)) - Decimal(str(old))) * 100)


def parse_rows(raw, year, today):
    root = ET.fromstring(raw)
    rows = {}
    for props in root.findall('.//{*}properties'):
        fields = {c.tag.split('}')[-1]: (c.text or '').strip() for c in props}
        date, value = fields.get('NEW_DATE','')[:10], fields.get('BC_2YEAR','')
        if not date:
            raise RuntimeError('Treasury 2Y observation date missing')
        if not value:
            raise RuntimeError('Treasury 2Y value missing in a published row')
        day = datetime.strptime(date, '%Y-%m-%d').date()
        if day.year != year or day > today or day.weekday() >= 5:
            raise RuntimeError('Treasury 2Y observation date invalid')
        y = float(value)
        if not math.isfinite(y) or abs(y) > 100:
            raise RuntimeError('Treasury 2Y observation value invalid')
        if date in rows and rows[date] != y:
            raise RuntimeError('Conflicting Treasury 2Y observations')
        rows[date] = y
    if not rows:
        raise RuntimeError('Treasury XML feed: 2Y rows not found')
    return sorted(rows.items())


def official_rows(old_date=None):
    today = datetime.now(NY).date()
    year = today.year
    rows = parse_rows(fetch(treasury_url(year)), year, today)
    if len(rows) < 2 or (old_date and old_date < rows[0][0]):
        previous_year = year - 1
        rows = parse_rows(fetch(treasury_url(previous_year)), previous_year, today) + rows
    if len(rows) < 2:
        raise RuntimeError('Treasury 2Y: insufficient official observations')
    return rows


def latest_2y():
    rows = official_rows()
    return rows[-1], rows[-2], treasury_url(int(rows[-1][0][:4]))


def get_bot_username():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError('Telegram getMe failed')
    return str((data.get('result') or {}).get('username') or '')


def source_link(url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">미 재무부 공식 금리</a>'


class DefinitelyNotSent(RuntimeError):
    pass


def verified_receipt(data, expected_chat):
    result = data.get('result') or {}
    chat = result.get('chat') or {}
    mid = result.get('message_id')
    matched = (str(chat.get('id')) == expected_chat if expected_chat.lstrip('-').isdigit()
               else expected_chat.startswith('@') and str(chat.get('username') or '').lower() == expected_chat[1:].lower())
    if data.get('ok') is not True or type(mid) is not int or mid <= 0 or not matched:
        raise RuntimeError('Telegram message_id or recipient not verified')
    return {'status': 'confirmed', 'message_id': mid, 'recipient_verified': True}


def send(text: str):
    # Errors before sendMessage are safe to retry. Ambiguous POST results are not.
    if not TOKEN or not CHAT_ID:
        raise DefinitelyNotSent('Telegram token/chat id missing')
    try:
        username = get_bot_username()
    except Exception:
        raise DefinitelyNotSent('Telegram preflight failed') from None
    if username.lower() != EXPECTED_BOT.lower():
        raise DefinitelyNotSent('Telegram bot identity mismatch')
    payload = urllib.parse.urlencode({
        'chat_id': CHAT_ID, 'text': text,
        'parse_mode': 'HTML', 'disable_web_page_preview': 'true',
    }).encode('utf-8')
    req = urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data=payload, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            response = json.loads(exc.read().decode('utf-8'))
        except Exception:
            raise RuntimeError('Telegram HTTP response unverified') from None
        if 400 <= exc.code < 500 and response.get('ok') is False:
            raise DefinitelyNotSent(f'Telegram rejected HTTP {exc.code}') from None
        raise RuntimeError('Telegram delivery uncertain') from None
    except Exception:
        raise RuntimeError('Telegram delivery uncertain') from None
    return verified_receipt(data, CHAT_ID)


def load_state():
    if not STATE_PATH.exists():
        return {}
    state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    if not isinstance(state, dict):
        raise RuntimeError('2Y delivery state is invalid — no resend')
    if 'delivery_records' in state and not isinstance(state['delivery_records'], dict):
        raise RuntimeError('2Y delivery records invalid — no resend')
    return state


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
    temp = STATE_PATH.with_suffix('.json.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, STATE_PATH)


def deliver_once(state, key, action):
    records = state.setdefault('delivery_records', {})
    previous = records.get(key) or {}
    status = previous.get('status')
    if status in ('confirmed', 'suppressed_integrated', 'legacy_sent_no_receipt'):
        return previous
    if status in ('sending', 'delivery_uncertain'):
        # Never replay a POST whose acceptance is unknown.
        if status == 'sending':
            previous['status'] = 'delivery_uncertain'
            save_state(state)
        return previous
    records[key] = {'status': 'sending'}
    save_state(state)
    try:
        receipt = action()
        if not isinstance(receipt, dict) or (
            receipt.get('status') != 'suppressed_integrated' and
            not (receipt.get('status') == 'confirmed' and
                 type(receipt.get('message_id')) is int and receipt['message_id'] > 0 and
                 receipt.get('recipient_verified') is True)
        ):
            raise RuntimeError('2Y delivery receipt invalid')
    except DefinitelyNotSent:
        records[key] = {'status': 'retryable_not_sent'}
        save_state(state)
        raise
    except Exception as exc:
        records[key] = {'status': 'delivery_uncertain', 'error_type': type(exc).__name__}
        save_state(state)
        return records[key]
    records[key] = {**receipt, 'recorded_at_utc': datetime.now(timezone.utc).isoformat()}
    save_state(state)
    return records[key]


def same_direction(a: float, b: float) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)


def send_initial_alert(date, value, prev, day_bp, source):
    policy = ('추가긴축 기대가 커지는 쪽' if day_bp > 0 else
              '추가긴축 기대가 약해지는 쪽' if day_bp < 0 else '변화 없는 수준')
    triggered = abs(day_bp) >= THRESHOLD_BP
    msg = [
        '<b>[Warsh 반응함수 · 미 국채 2년물 급변]</b>',
        f'기준일 {date}', '',
        '<b>한눈에 보기</b>',
        f'• <b>2년물</b> | {prev[1]:.2f}% → {value:.2f}% ({day_bp:+.1f}bp)',
        f'• <b>경보 기준</b> | 하루 ±{THRESHOLD_BP:.0f}bp 이상 → {"기준 충족" if triggered else "수동 조회 · 급변 기준 미달"}',
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
    return send('\n'.join(msg))


def followup_message(current_date, current_value, event, source):
    base = float(event['base_value'])
    event_value = float(event['event_value'])
    original_bp = bp(event_value, base)
    if not original_bp or abs(original_bp - float(event['move_bp'])) > 0.00001:
        raise RuntimeError('2Y event baseline does not match recorded move')
    retained_bp = bp(current_value, base)
    next_bp = bp(current_value, event_value)
    ratio = retained_bp / original_bp
    kept_direction = ratio > 0
    persistent = kept_direction and ratio >= RETENTION_THRESHOLD
    direction = '긴축' if original_bp > 0 else '완화'
    if persistent and ratio > 1:
        verdict = f'{direction} 방향 재가격 강화'
        detail = f'최초 이동을 전부 유지하고 같은 방향으로 {abs(next_bp):.1f}bp 추가 이동했습니다.'
    elif persistent and ratio == 1:
        verdict = f'{direction} 방향 재가격 유지 — 추가 강화 없음'
        detail = '첫날 이동을 100% 유지했지만 다음 공식일의 추가 이동은 0.0bp입니다.'
    elif persistent:
        verdict = f'{direction} 방향 재가격 지속 — 일부 반납'
        detail = f'최초 이동의 {ratio*100:.0f}%가 남아 {RETENTION_THRESHOLD*100:.0f}% 지속 기준을 충족했습니다.'
    elif kept_direction:
        verdict = '최초 방향 약화 — 지속 기준 미달'
        detail = f'최초 이동의 {ratio*100:.0f}%만 남았습니다.'
    else:
        verdict = '최초 이동 소멸' if ratio == 0 else '최초 이동 반전'
        detail = '기준점까지 되돌아왔습니다.' if ratio == 0 else f'기준점을 넘어 반대 방향으로 {abs(retained_bp):.1f}bp 이동했습니다.'
    if ratio > 1:
        ratio_plain = f'{ratio*100:.0f}% = 최초 이동 유지 + 같은 방향 {abs(next_bp):.1f}bp 추가'
    elif ratio == 1:
        ratio_plain = '100% = 최초 이동 전부 유지 · 추가 이동 0.0bp'
    elif ratio > 0:
        ratio_plain = f'{ratio*100:.0f}% = 최초 방향의 이동 중 남아 있는 비율'
    elif ratio == 0:
        ratio_plain = '0% = 최초 이동 전부 반납'
    else:
        ratio_plain = f'0% 유지 · 반대 방향 {abs(ratio)*100:.0f}% 이동(최초 이동폭 대비)'
    if original_bp > 0:
        weak = '고용·근원 PCE 물가가 둔화하고 추가 긴축 기대가 약해지는 경우'
        confirm = '고용·물가가 강해지거나 예상보다 높아지면 긴축 방향을 뒷받침할 수 있습니다.'
    else:
        weak = '고용·근원 PCE 물가가 예상보다 강해져 추가 긴축 기대가 다시 커지는 경우'
        confirm = '고용·물가가 둔화하면 완화 방향을 뒷받침할 수 있습니다.'
    msg = [
        '<b>[Warsh 반응함수 · 미 국채 2년물 지속성 재확인]</b>',
        f"이벤트 {event['event_date']} → 재확인 {current_date} (미국 현지 공식일)", '',
        '<b>한눈에 보기</b>',
        f'• <b>첫날</b> | {base:.2f}% → {event_value:.2f}% ({original_bp:+.1f}bp)',
        f'• <b>다음 공식일</b> | {event_value:.2f}% → {current_value:.2f}% ({next_bp:+.1f}bp)',
        f'• <b>기준점 대비 누적</b> | {base:.2f}% → {current_value:.2f}% ({retained_bp:+.1f}bp)',
        f'• <b>유지·확대율</b> | {ratio_plain}', '',
        f'<b>판정: {html.escape(verdict)}</b>',
        f'• {html.escape(detail)}', '',
        '<b>쉽게 말하면</b>',
        ('• 다음 공식일에도 최초 금리 이동이 남아 있습니다.' if persistent else '• 최초 금리 이동의 지속성이 약해졌습니다.'),
        '• 2년물은 정책금리 기대에 민감하지만 위험회피·자금수급 등도 반영합니다. 금리만으로 연준 정책 변경이나 금리 인하·인상을 확정할 수 없습니다.',
        f'• {confirm}', '',
        '<b>이 판정이 약해지는 조건</b>',
        f'• 기준점 대비 최초 방향 이동이 {RETENTION_THRESHOLD*100:.0f}% 미만으로 줄거나 반전되는 경우',
        f'• {weak}', '',
        source_link(source),
        '※ 1bp = 0.01%포인트 · 미 재무부 일별 공식 수익률',
    ]
    return '\n'.join(msg)


def send_followup_alert(current_date, current_value, event, source):
    return send(followup_message(current_date, current_value, event, source))


def process_rows(state, rows, force=False):
    """Process each official observation in order; no fabricated intermediate days."""
    state.setdefault('delivery_records', {})
    known = dict(rows)
    date = state.get('date')
    if date and date not in known:
        raise RuntimeError('2Y saved observation not present in official feed — no rollback')
    if date and float(state['value']) != known[date]:
        raise RuntimeError('2Y prior official observation revised — review before new alert')
    latest_date = rows[-1][0]
    if date and latest_date < date:
        raise RuntimeError('2Y official feed regressed — no rollback')
    pending = state.get('pending_event')
    if pending and pending.get('event_date') not in known:
        raise RuntimeError('2Y pending event missing from official feed')
    if pending and date and pending['event_date'] < date:
        # A prior missed followup is recovered at the actual next published row.
        first = next((i for i, row in enumerate(rows) if row[0] > pending['event_date']), len(rows))
    elif date:
        first = next((i for i, row in enumerate(rows) if row[0] > date), len(rows))
    else:
        first = len(rows) - 1
    indices = list(range(max(1, first), len(rows)))
    # Preserve existing bootstrap for an unalerted large latest-day move.
    if not indices and (force or (not pending and state.get('last_alert_date') != latest_date
                                  and abs(bp(rows[-1][1], rows[-2][1])) >= THRESHOLD_BP)):
        indices = [len(rows)-1]
    actions = []
    for i in indices:
        current_date, value = rows[i]
        prev = rows[i-1]
        source = treasury_url(int(current_date[:4]))
        day_bp = bp(value, prev[1])
        pending = state.get('pending_event')
        if pending and current_date > pending['event_date']:
            # If an observation was missed, verify the next *official* row, not latest.
            next_row = next((r for r in rows if r[0] > pending['event_date']), None)
            if not next_row or next_row[0] != current_date:
                raise RuntimeError('2Y followup is not the next official observation')
            if (known.get(pending['event_date']) != float(pending['event_value'])
                or known.get(pending['base_date']) != float(pending['base_value'])):
                raise RuntimeError('2Y pending baseline changed — no alert')
            key = 'followup:' + pending['event_date'] + ':' + current_date
            # Render and verify before starting the Telegram transaction.
            followup_message(current_date, value, pending, source)
            receipt = deliver_once(state, key, lambda: send_followup_alert(current_date, value, pending, source))
            actions.append({'key': key, **receipt})
            if receipt.get('status') == 'confirmed':
                state['last_followup_completed'] = True
                state['last_followup_event_date'] = pending['event_date']
                state['last_followup_date'] = current_date
                state['last_followup_message_id'] = receipt['message_id']
            # An ambiguous delivery is quarantined by key, not retried on later dates.
            state['pending_event'] = None
            save_state(state)
        if ((abs(day_bp) >= THRESHOLD_BP or (force and current_date == latest_date))
            and state.get('last_alert_date') != current_date and
            (not date or current_date >= date)):
            key = 'initial:' + current_date
            receipt = deliver_once(state, key, lambda: send_initial_alert(current_date, value, prev, day_bp, source))
            actions.append({'key': key, **receipt})
            if receipt.get('status') in ('confirmed', 'suppressed_integrated'):
                state['last_alert_date'] = current_date
                state['pending_event'] = ({
                    'event_date': current_date, 'base_date': prev[0], 'base_value': prev[1],
                    'event_value': value, 'move_bp': day_bp,
                } if abs(day_bp) >= THRESHOLD_BP else None)
                # A new pending event is distinct from the previous completed followup.
                save_state(state)
        if not date or current_date >= date:
            state.update({'date': current_date, 'value': value,
                          'prev_date': prev[0], 'prev_value': prev[1]})
            save_state(state)
    return actions


def self_test():
    """Network-free regression tests; run in this watcher only."""
    import tempfile
    from unittest.mock import patch
    event = {'event_date':'2026-11-20', 'base_date':'2026-11-19',
             'base_value':4.76, 'event_value':4.63, 'move_bp':-13}
    def render(value, e=event):
        return followup_message('2026-11-23',value,e,treasury_url(2026))
    assert '추가 강화 없음' in render(4.63) and '0.0bp 추가 확대' not in render(4.63)
    assert '재가격 강화' in render(4.60)
    assert '일부 반납' in render(4.69)
    assert '지속 기준 미달' in render(4.71)
    assert '최초 이동 소멸' in render(4.76)
    assert '최초 이동 반전' in render(4.80) and '0% 유지' in render(4.80)
    up = {**event, 'base_value':4.63, 'event_value':4.76, 'move_bp':13}
    assert '추가 강화 없음' in render(4.76,up)
    assert '고용·근원 PCE 물가가 둔화' in render(4.76,up)
    assert '고용·근원 PCE 물가가 예상보다 강해져' in render(4.63)
    assert bp(4.73,4.63)==10 and bp(4.63,4.73)==-10
    assert '지속 — 일부 반납' in render(4.68,{**event,'base_value':4.73,'event_value':4.63,'move_bp':-10})
    # Exactly 50% qualifies; contrary-direction movements never do.
    sample = b'<feed><properties><NEW_DATE>2026-11-23T00:00:00</NEW_DATE><BC_2YEAR>4.63</BC_2YEAR></properties></feed>'
    assert parse_rows(sample,2026,datetime(2026,11,24).date()) == [('2026-11-23',4.63)]
    try: parse_rows(sample.replace(b'4.63',b''),2026,datetime(2026,11,24).date())
    except RuntimeError: pass
    else: raise AssertionError('missing published yield accepted')
    assert verified_receipt({'ok':True,'result':{'message_id':44,'chat':{'id':-100}}},'-100')['message_id']==44
    for result in ({'ok':True,'result':{'message_id':44,'chat':{'id':-101}}},
                   {'ok':True,'result':{'chat':{'id':-100}}}):
        try: verified_receipt(result,'-100')
        except RuntimeError: pass
        else: raise AssertionError('unverified receipt accepted')
    receipt={'status':'confirmed','message_id':99,'recipient_verified':True}
    with tempfile.TemporaryDirectory() as p, patch(__name__+'.STATE_PATH',Path(p)/'state.json'):
        s={}
        assert deliver_once(s,'one',lambda:receipt)['message_id']==99
        assert deliver_once(s,'one',lambda:(_ for _ in ()).throw(AssertionError('duplicate send')))['message_id']==99
        def unknown(): raise TimeoutError('ambiguous')
        assert deliver_once(s,'two',unknown)['status']=='delivery_uncertain'
        assert deliver_once(s,'two',lambda:(_ for _ in ()).throw(AssertionError('duplicate uncertain send')))['status']=='delivery_uncertain'
        def reject(): raise DefinitelyNotSent('rejected')
        try: deliver_once(s,'three',reject)
        except DefinitelyNotSent: pass
        else: raise AssertionError('rejection not propagated')
        assert deliver_once(s,'three',lambda:receipt)['status']=='confirmed'
        # A stale/older input cannot advance state or emit alerts.
        rows=[('2026-11-19',4.76),('2026-11-20',4.63),('2026-11-23',4.63),('2026-11-24',4.62)]
        s={'date':'2026-11-20','value':4.63,'last_alert_date':'2026-11-20','pending_event':event}
        with patch(__name__+'.send_followup_alert',return_value=receipt) as follow:
            process_rows(s,rows)
            assert follow.call_count==1 and follow.call_args.args[:2]==('2026-11-23',4.63)
            assert s['last_followup_completed'] and s['last_followup_message_id']==99
            process_rows(s,rows)
            assert follow.call_count==1 and s['last_followup_completed']
            try: process_rows(s,rows[:-1])
            except RuntimeError: pass
            else: raise AssertionError('regressed source accepted')
        assert load_state()['last_followup_completed']
    print(json.dumps({'treasury_2y_regression':'passed',
                      'checks':'equal,extension,partial,weak,zero,reversal,direction,decimal,receipt,retry,uncertain,catchup,repeat,stale'},ensure_ascii=False))


def main():
    self_test()
    state = load_state()
    previous_date = state.get('date')
    try:
        rows = official_rows(previous_date)
    except Exception as exc:
        print(json.dumps({'source_status':'official_source_lookup_failed','error_type':type(exc).__name__,
                          'last_verified_date':previous_date},ensure_ascii=False))
        raise
    actions = process_rows(state, rows, force=FORCE_NOTIFY)
    records = state.get('delivery_records') or {}
    unresolved = [key for key, record in records.items()
                  if record.get('status') in ('sending','delivery_uncertain','retryable_not_sent')]
    latest, prev = rows[-1], rows[-2]
    print(json.dumps({
        'date': latest[0], 'value': latest[1], 'day_bp': bp(latest[1],prev[1]),
        'source_status': ('new_official_observation' if latest[0] != previous_date
                          else 'no_new_observation_in_verified_official_feed'),
        'source_verified': True,
        'published_observation_date': latest[0],
        'actions': actions, 'pending_event': state.get('pending_event'),
        'last_followup_completed': state.get('last_followup_completed'),
        'last_followup_date': state.get('last_followup_date'),
        'unresolved': unresolved,
    }, ensure_ascii=False))
    if unresolved:
        raise RuntimeError('2Y delivery unresolved — no automatic duplicate send')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import csv
import io
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path('data/warsh_pce_trend_watch_state.json')
FRED_CSV = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=PCEPI,PCEPILFE'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'


def fetch_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def annualized(latest, prior, months):
    return ((latest / prior) ** (12.0 / months) - 1.0) * 100.0


def yoy(latest, prior12):
    return (latest / prior12 - 1.0) * 100.0


def load_series():
    text = fetch_text(FRED_CSV)
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            pce = float(row['PCEPI'])
            core = float(row['PCEPILFE'])
        except Exception:
            continue
        rows.append((row['DATE'], pce, core))
    if len(rows) < 13:
        raise RuntimeError('PCE FRED series too short')
    return rows


def classify(core3, core6, headline3, headline6):
    # Warsh principle: trends matter most. Alert only when the trend regime changes.
    if core3 >= 3.0 and core6 >= 3.0:
        if core3 >= core6 + 0.25:
            return '재가속 — 추가긴축 논리 강화'
        return '3%대 고착 — 추가긴축 논리 유지'
    if core3 <= 2.5 and core6 <= 2.75 and core3 <= core6:
        return '2% 복귀 강화 — 추가긴축 논리 약화'
    if core3 <= 2.25 and headline3 <= 2.25:
        return '단기 2% 부근 — 완화 논의 여지 확대'
    return '혼합/추세 확인 필요'


def snapshot():
    rows = load_series()
    date, pce, core = rows[-1]
    pce3 = annualized(pce, rows[-4][1], 3)
    pce6 = annualized(pce, rows[-7][1], 6)
    core3 = annualized(core, rows[-4][2], 3)
    core6 = annualized(core, rows[-7][2], 6)
    pce_yoy = yoy(pce, rows[-13][1])
    core_yoy = yoy(core, rows[-13][2])
    regime = classify(core3, core6, pce3, pce6)
    return {
        'date': date,
        'headline_3m_ann': pce3,
        'headline_6m_ann': pce6,
        'headline_yoy': pce_yoy,
        'core_3m_ann': core3,
        'core_6m_ann': core6,
        'core_yoy': core_yoy,
        'regime': regime,
        'url': FRED_CSV,
    }


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


def get_bot_username():
    if not TOKEN:
        raise RuntimeError('Telegram token missing')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError('Telegram getMe failed')
    return str((data.get('result') or {}).get('username') or '')


def send(msg):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError('Telegram token/chat id missing')
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}')
    payload = urllib.parse.urlencode({'chat_id': CHAT_ID, 'text': msg[:4090], 'disable_web_page_preview': 'true'}).encode('utf-8')
    req = urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data=payload, method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode('utf-8'))
    if not out.get('ok'):
        raise RuntimeError(f'Telegram send failed: {out}')


def main():
    cur = snapshot()
    old = load_state()
    first_run = not bool(old)
    new_period = old.get('date') not in (None, cur['date'])
    regime_changed = old.get('regime') not in (None, cur['regime'])

    # Existing PCE watcher already reports every release. This watcher only sends a NEW INFORMATION alert
    # when the 3m/6m trend regime changes, avoiding duplicate monthly release alerts.
    if FORCE_NOTIFY or (not first_run and new_period and regime_changed):
        msg = [
            '[Warsh 새 정보축] PCE 3개월·6개월 추세',
            f"기준월: {cur['date']}",
            f"Headline PCE: 3개월 연율 {cur['headline_3m_ann']:+.2f}% | 6개월 연율 {cur['headline_6m_ann']:+.2f}% | YoY {cur['headline_yoy']:+.2f}%",
            f"Core PCE: 3개월 연율 {cur['core_3m_ann']:+.2f}% | 6개월 연율 {cur['core_6m_ann']:+.2f}% | YoY {cur['core_yoy']:+.2f}%",
            f"판정: {cur['regime']}",
            '',
            "의미: Warsh의 'Trends matter most' 원칙에 맞춰 한 달치 PCE가 아니라 3·6개월 기조가 2%로 충분히 빠르게 내려가는지 확인.",
            '원천: BEA PCE index via Federal Reserve Bank of St. Louis FRED',
            'PCEPI: https://fred.stlouisfed.org/series/PCEPI',
            'PCEPILFE: https://fred.stlouisfed.org/series/PCEPILFE',
        ]
        send('\n'.join(msg))

    save_state(cur)
    print(json.dumps({'first_run': first_run, 'new_period': new_period, 'regime_changed': regime_changed, **cur}, ensure_ascii=False))


if __name__ == '__main__':
    main()

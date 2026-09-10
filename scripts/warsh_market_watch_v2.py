#!/usr/bin/env python3
import json
from pathlib import Path
import warsh_market_watch as base

INTEGRATED_STATE = Path('data/warsh_inflation_market_watch_state.json')
_original_send_initial = base.send_initial_alert


def integrated_market_date():
    try:
        return json.loads(INTEGRATED_STATE.read_text(encoding='utf-8')).get('last_integrated_market_date')
    except Exception:
        return None


def send_initial_alert(date, value, prev, day_bp, source):
    if not base.FORCE_NOTIFY and integrated_market_date() == date:
        print(json.dumps({'standalone_2y_suppressed': True, 'date': date}, ensure_ascii=False))
        return
    return _original_send_initial(date, value, prev, day_bp, source)


base.send_initial_alert = send_initial_alert

if __name__ == '__main__':
    base.main()

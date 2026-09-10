#!/usr/bin/env python3
import json
import re
from pathlib import Path
import warsh_curve_ownership_watch as base

INTEGRATED_STATE = Path('data/warsh_inflation_market_watch_state.json')
_original_send_html = base.send_html


def integrated_market_date():
    try:
        return json.loads(INTEGRATED_STATE.read_text(encoding='utf-8')).get('last_integrated_market_date')
    except Exception:
        return None


def send_html(text: str):
    if not base.FORCE_NOTIFY and text.startswith('<b>[Warsh·미 재무부 금리곡선 변화]</b>'):
        m = re.search(r'기준일\s+(\d{4}-\d{2}-\d{2})', text)
        if m and integrated_market_date() == m.group(1):
            print(json.dumps({'standalone_curve_suppressed': True, 'date': m.group(1)}, ensure_ascii=False))
            return
    return _original_send_html(text)


base.send_html = send_html

if __name__ == '__main__':
    base.main()

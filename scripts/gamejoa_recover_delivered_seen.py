#!/usr/bin/env python3
"""Recover acknowledged report history without collecting or sending anything."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from merge_gamejoa_preopen_news_radar_seen import delivery_receipt_allows_seen_persistence


def recover_delivered_seen(report_path: Path, markdown_path: Path, receipt_path: Path) -> int:
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if not delivery_receipt_allows_seen_persistence(receipt):
        raise ValueError('No acknowledged nonempty Telegram delivery')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    alerts = report.get('alerts')
    mode = str(report.get('run_mode') or '')
    expected_mode = 'live' if os.getenv('RADAR_RUN_MODE', '').strip().lower() == 'live' else 'preopen'
    if mode != expected_mode or not isinstance(alerts, list) or not alerts:
        raise ValueError('Delivered report has missing alerts or mismatched lane')
    now = dt.datetime.fromisoformat(report['query_time_kst'])
    if now.tzinfo is None:
        raise ValueError('Delivered report query time has no timezone')

    import gamejoa_preopen_news_radar_fda_quality_runner as production
    renderer = production.runner
    guarded = renderer.guard_preopen_report(markdown_path.read_text(encoding='utf-8'))
    full_message, _entities = renderer.telegram_text_and_entities(guarded)
    visible = sum(bool(re.match(r'^\d+\)\s+\S', line)) for line in guarded.splitlines())
    if visible != len(alerts) or receipt.get('original_chars') != len(guarded):
        raise ValueError('Receipt does not match the saved complete report')
    if receipt['sent_chars'] != len(full_message):
        raise ValueError('Partial or truncated Telegram text cannot seed complete report history')
    for name, text in (('report_sha256', guarded), ('sent_text_sha256', full_message)):
        if receipt.get(name) and receipt[name] != hashlib.sha256(text.encode('utf-8')).hexdigest():
            raise ValueError('Acknowledged receipt hash disagrees with saved report text')
    if report.get('selection_diagnostics', {}).get('selected_alerts') != len(alerts):
        raise ValueError('Delivered report selection count disagrees with saved alerts')

    telegram = renderer.telegram
    path = telegram.SEEN_PATH
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'seen': {}}
    if not isinstance(state.get('seen'), dict):
        raise ValueError('Invalid current sent history')
    missing = [alert for alert in alerts if any(key not in state['seen'] for key in telegram.alert_seen_keys(alert))]
    if missing:
        telegram.record_seen_alerts(missing, now)
    print(f'GAMEJOA acknowledged seen recovery: message_id={receipt["message_id"]} recovered_articles={len(missing)}')
    return len(missing)


if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    recover_delivered_seen(root / 'out/gamejoa_preopen_news_radar.json',
                           root / 'out/gamejoa_preopen_news_radar.md',
                           root / 'out/gamejoa_preopen_news_radar_delivery.json')

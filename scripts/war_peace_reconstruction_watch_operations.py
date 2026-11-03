#!/usr/bin/env python3
"""Prepare a throttled, source-coverage-only operational warning.

This module never sends Telegram messages. The existing workflow sender owns
delivery; this file only prepares text and a pending deduplication state.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / 'out' / 'war_peace_reconstruction_coverage.json'
ALERT = ROOT / 'out' / 'war_peace_reconstruction_alert.txt'
STATE = ROOT / 'data' / 'war_peace_reconstruction_watch_ops_state.json'
WARNING = ROOT / 'out' / 'war_peace_reconstruction_ops_warning.txt'
PENDING = ROOT / 'out' / 'war_peace_reconstruction_ops_state_pending.json'
DELIVERY = ROOT / 'out' / 'war_peace_reconstruction_delivery.json'
KST = ZoneInfo('Asia/Seoul')
WARNING_INTERVAL = dt.timedelta(hours=6)


def _read_json(path: Path, default=None):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        if default is not None:
            return default
        raise
    if not isinstance(value, dict):
        raise ValueError(f'{path.name} must contain a JSON object')
    return value


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def _parse_time(value):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('operational state timestamps must include a timezone')
    return parsed.astimezone(dt.timezone.utc)


def _status_counts(news):
    counts = collections.Counter(str(row.get('status') or 'unknown') for row in news)
    total = len(news)
    complete = counts.get('ok', 0)
    return total, complete, counts


def _cause_counts(news):
    causes = collections.Counter()
    for row in news:
        if row.get('status') == 'ok':
            continue
        record_causes = set()
        if (row.get('coverage_issue') or {}).get('reason') == 'fallback_scope_not_verified':
            record_causes.add('대체 원천의 범위 미확인')
        status = str(row.get('status') or '')
        if 'deadline' in status:
            record_causes.add('수집 시간 초과')
        if status == 'worker_error':
            record_causes.add('수집 작업 오류')
        messages = [str(row.get('error') or '')]
        messages.extend(str(item.get('error') or '') for item in row.get('http', []))
        for message in messages:
            if not message:
                continue
            code_match = re.search(r'HTTP\s+Error\s+(401|403|429)|\b(401|403|429)\b', message, re.I)
            if code_match:
                code = next(group for group in code_match.groups() if group)
                label = {'401': 'HTTP 401 인증 거부', '403': 'HTTP 403 접근 거부',
                         '429': 'HTTP 429 요청 제한'}[code]
                record_causes.add(label)
            elif re.search(r'time.?out|timed out|deadline', message, re.I):
                record_causes.add('수집 시간 초과')
        if not record_causes:
            if any(row.get('error') or item.get('error') for item in row.get('http', [])):
                record_causes.add('원천 응답 오류')
            else:
                record_causes.add('원천 범위 미완료')
        causes.update(record_causes)
    return causes


def _failure_details(report):
    news = report.get('news')
    if not isinstance(news, list) or not news:
        if report.get('failure_phase') == 'collection' and report.get('error'):
            return {
                'query_total': report.get('query_count') if isinstance(report.get('query_count'), int) else None,
                'query_complete': None,
                'query_incomplete': None,
                'statuses': {},
                'causes': {'질의별 수집 결과 기록 없음': 1},
            }
        return None
    total, complete, statuses = _status_counts(news)
    if total == complete:
        return None
    causes = _cause_counts(news)
    stable_summary = {
        'query_total': total,
        'query_complete': complete,
        'query_incomplete': total - complete,
        'statuses': {key: statuses[key] for key in sorted(statuses)},
        'causes': {key: causes[key] for key in sorted(causes)},
    }
    return stable_summary


def _render_warning(details, first_seen_at, now):
    displayed = []
    for label, count in details['causes'].items():
        displayed.append(f'• {label}: {count}건')
    if not displayed:
        displayed = ['• 미완료 원천의 세부 유형은 확인되지 않았습니다.']
    first_seen = _parse_time(first_seen_at) or now
    first_seen_kst = first_seen.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')
    now_kst = now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')
    if details['query_total'] is None or details['query_complete'] is None:
        coverage_line = '원천 수집 완전 확인: 질의별 상태 증거 없음'
        incomplete_line = '미완료 질의 수: 확인 불가'
    else:
        coverage_line = f'원천 수집 완전 확인: {details["query_complete"]}/{details["query_total"]}개 질의'
        incomplete_line = f'미완료: {details["query_incomplete"]}개'
    lines = [
        '⚠️ <b>전쟁 알림 수집 지연·범위 미확인</b>',
        f'🕒 확인 {now_kst}',
        coverage_line,
        incomplete_line,
        *displayed[:6],
        f'장애 최초 확인: {first_seen_kst}',
        '전쟁 상황 알림은 원천 범위가 완전히 확인될 때까지 보류 중입니다.',
        '이 운영 경고는 상황 알림이 아니며, 계속될 경우 최소 6시간 간격으로 알립니다.',
    ]
    return '\n'.join(lines) + '\n'


def prepare(*, now=None, coverage_path=COVERAGE, state_path=STATE,
            warning_path=WARNING, pending_path=PENDING, alert_path=ALERT):
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    warning_path.unlink(missing_ok=True)
    pending_path.unlink(missing_ok=True)
    if not coverage_path.is_file():
        print('operational_warning=none; coverage evidence absent')
        return 'none'
    report = _read_json(coverage_path)
    state = _read_json(state_path, default={
        'active': False,
        'first_seen_at': None,
        'last_seen_at': None,
        'last_warning_sent_at': None,
        'last_failure': None,
    })

    partial_verified = (report.get('complete') is True and report.get('phase') == 'verified'
                        and report.get('source_coverage_complete') is False)
    if (report.get('complete') is True and report.get('phase') == 'verified'
            and not partial_verified):
        if state.get('active') is True:
            state.update(active=False, recovered_at=now.isoformat(timespec='seconds'))
            _write_json(pending_path, state)
            print('operational_source_incident=recovered')
            return 'recovered'
        print('operational_warning=none; source coverage complete')
        return 'healthy'

    if not partial_verified and (report.get('complete') is not False
                                 or report.get('failure_phase') != 'collection'):
        print('operational_warning=none; failure is outside source collection')
        return 'not_source_failure'

    details = _failure_details(report)
    if details is None:
        print('operational_warning=none; incomplete source counts unavailable')
        return 'no_failure_detail'

    first_seen = state.get('first_seen_at') if state.get('active') is True else now.isoformat(timespec='seconds')
    last_warning = _parse_time(state.get('last_warning_sent_at'))
    due = last_warning is None or now - last_warning >= WARNING_INTERVAL
    state.update(active=True, first_seen_at=first_seen, last_seen_at=now.isoformat(timespec='seconds'),
                 last_failure=details)
    # The partial situation alert already tells the recipient that collection
    # is incomplete. Do not prepare two Telegram payloads in the same run.
    if due and not (partial_verified and alert_path.is_file()):
        state['last_warning_sent_at'] = now.isoformat(timespec='seconds')
        message = _render_warning(details, first_seen, now)
        warning_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = warning_path.with_suffix(warning_path.suffix + '.tmp')
        temporary.write_text(message, encoding='utf-8')
        temporary.replace(warning_path)
    _write_json(pending_path, state)
    outcome = ('partial_alert' if partial_verified and alert_path.is_file()
               else 'send' if due else 'throttled')
    incomplete = details['query_incomplete']
    total = details['query_total']
    print(f'operational_warning={outcome} incomplete_queries={incomplete}/{total}' if total is not None
          else f'operational_warning={outcome} query_status=unavailable')
    return outcome


def finalize(*, state_path=STATE, warning_path=WARNING, pending_path=PENDING,
             delivery_path=DELIVERY):
    if not pending_path.is_file():
        print('operational_state_commit=none')
        return False
    pending = _read_json(pending_path)
    if warning_path.is_file():
        try:
            receipt = _read_json(delivery_path)
        except FileNotFoundError:
            print('operational_state_commit=held_without_delivery_receipt')
            return False
        delivered_text = warning_path.read_text(encoding='utf-8').strip()
        expected_hash = hashlib.sha256(delivered_text.encode('utf-8')).hexdigest()
        if (receipt.get('status') != 'confirmed'
                or receipt.get('kind') != 'operational_source_coverage_warning'
                or receipt.get('alert_sha256') != expected_hash):
            print('operational_state_commit=held_without_matching_delivery_receipt')
            return False
    _write_json(state_path, pending)
    pending_path.unlink(missing_ok=True)
    print('operational_state_commit=confirmed')
    return True


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--finalize', action='store_true')
    args = ap.parse_args()
    if args.prepare:
        prepare()
    else:
        finalize()


if __name__ == '__main__':
    main()

"""Independently recompute the snapshot from preserved official HTTP responses."""
import datetime as dt
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
from market_time_windows import subtract_calendar_months

ORIGIN = 'https://freesis.kofia.or.kr'
SIDS = {'deposit': 'STATSCU0100000060', 'mmf': 'STATFND0400000050',
        'cma': 'STATSCU0100000090', 'credit': 'STATSCU0100000070'}


def check(ok, reason):
    if not ok:
        raise RuntimeError('KOFIA source quality gate: ' + reason)


def day(value):
    check(isinstance(value, str) and bool(re.fullmatch(r'\d{8}', value)), 'invalid source date')
    dt.datetime.strptime(value, '%Y%m%d')
    return value


def number(value):
    check(type(value) in (str, int, float), 'invalid source numeric type')
    if isinstance(value, str):
        check(bool(value.strip()), 'missing source number')
        value = float(value.replace(',', '').strip())
    check(math.isfinite(value), 'non-finite source number')
    return int(value) if float(value).is_integer() else value


def total_row(rows, key):
    matches = [row for row in rows if row.get('TMPV1') == '합계'
               or (key == 'mmf' and row.get('TMPV98') == '99')
               or (key == 'cma' and row.get('ORD_SEQ') in (99, '99'))]
    check(len(matches) == 1, 'missing/ambiguous ' + key + ' total')
    return matches[0]


def matching_totals(rows, key):
    return [row for row in rows if row.get('TMPV1') == '합계'
            or (key == 'mmf' and row.get('TMPV98') == '99')
            or (key == 'cma' and row.get('ORD_SEQ') in (99, '99'))]


def month_horizons(end, series, point, current_values, request_failures, comparison_errors):
    deposit_rows = {day(row['TMPV1']): row for row in series[SIDS['deposit']]}
    credit_rows = {day(row['TMPV1']): row for row in series[SIDS['credit']]}
    horizons = {}
    for months in (1, 3):
        target = subtract_calendar_months(dt.date.fromisoformat(end), months).strftime('%Y%m%d')
        common = sorted((set(deposit_rows) & set(credit_rows)), reverse=True)
        eligible = [date for date in common if date <= target]
        anchor = eligible[0] if eligible else None
        gap_days = ((dt.datetime.strptime(target, '%Y%m%d').date()
                     - dt.datetime.strptime(anchor, '%Y%m%d').date()).days if anchor else None)
        common_reason = ('no_prior_official_deposit_date' if anchor is None else
                         'prior_official_date_more_than_7_days_before_target' if gap_days > 7 else None)
        window = {'months_back': months, 'target_date': target, 'anchor_date': anchor,
                  'end_date': end, 'max_anchor_gap_days': 7, 'changes': {}}
        for key in ('deposit', 'mmf', 'cma', 'credit'):
            if common_reason:
                window['changes'][key] = {'delta': None, 'reason': common_reason}
                continue
            prior = None
            if key == 'deposit':
                prior = number(deposit_rows[anchor]['TMPV2'])
            elif key == 'credit':
                prior = number(credit_rows[anchor]['TMPV2'])
            else:
                sid = SIDS[key]
                records = [rows for (source_sid, date), rows in point.items()
                           if source_sid == sid and date == anchor]
                if records:
                    matches = matching_totals(records[0], key)
                    if len(matches) == 1:
                        try:
                            prior = number(matches[0]['TMPV2' if key == 'mmf' else 'TMPV8'])
                        except (RuntimeError, ValueError, TypeError, KeyError):
                            prior = None
                    else:
                        prior = None
                if not records or prior is None:
                    details = [item for item in comparison_errors
                               if item.get('period') == f'm{months}' and item.get('metric') == key
                               and item.get('date') == anchor and item.get('error')]
                    check(len(details) == 1, f'{key} historical anchor unavailable without a dated comparison error')
                    if not records:
                        check((sid, anchor) in request_failures,
                              f'{key} unavailable comparison lacks a failed official request for its exact anchor')
                    window['changes'][key] = {'delta': None, 'reason': 'historical_source_unavailable'}
                    continue
            window['changes'][key] = {
                'delta': current_values[key]['value'] - prior,
                'start_date': anchor, 'end_date': end, 'reason': None,
            }
        horizons[f'm{months}'] = window
    return horizons


def decode(record):
    raw = record['response_text']
    check(hashlib.sha256(raw.encode()).hexdigest() == record['response_sha256'], 'source response hash mismatch')
    wire = base64.b64decode(record['response_body_base64'], validate=True)
    check(wire == raw.encode() and len(wire) == record['response_bytes'], 'source bytes/text mismatch')
    check(hashlib.sha256(wire).hexdigest() == record['response_sha256'], 'source wire hash mismatch')
    check(record['response_url'] == ORIGIN + record['endpoint'], 'source URL/redirect mismatch')
    value = raw
    for _ in range(3):
        if isinstance(value, str):
            value = json.loads(value)
    check(isinstance(value, dict), 'source response is not an object')
    return value


def validate(evidence, pending=None):
    check(evidence.get('source_origin') == ORIGIN and evidence.get('unit_won') == 1000000
          and evidence.get('unit') == '백만원', 'source identity/unit mismatch')
    requests = evidence['requests']
    latest, series, point = {}, {}, {}
    request_failures = set()
    for record in requests:
        if record.get('status') != 200 or record.get('error'):
            endpoint = record.get('endpoint')
            check(endpoint in ('/meta/getSrvData.do', '/meta/getMetaDataList.do'),
                  'failed request uses an unknown endpoint')
            if record.get('response_text') is not None:
                raw = record['response_text']
                check(hashlib.sha256(raw.encode()).hexdigest() == record.get('response_sha256'),
                      'failed response hash mismatch')
                wire = base64.b64decode(record['response_body_base64'], validate=True)
                check(wire == raw.encode() and len(wire) == record.get('response_bytes'),
                      'failed response bytes/text mismatch')
                check(record.get('response_url') == ORIGIN + endpoint,
                      'failed source URL/redirect mismatch')
            if endpoint == '/meta/getMetaDataList.do':
                search = (record.get('payload') or {}).get('dmSearch') or {}
                check(search.get('tmpV40') == '1000000', 'failed request unit is not million won')
                sid = str(search.get('OBJ_NM') or '').removesuffix('BO')
                check(sid in SIDS.values(), 'failed request has unknown source series')
                if sid == SIDS['mmf']:
                    check(search.get('tmpV39') == '1', 'failed MMF selector is not principal balance')
                    failed_date = day(search.get('tmpV34'))
                    request_failures.add((sid, failed_date))
                elif sid == SIDS['cma']:
                    check(search.get('tmpV1') == 'RD' and search.get('tmpV45') == search.get('tmpV46'),
                          'failed CMA request is not a single official date')
                    failed_date = day(search.get('tmpV45'))
                    request_failures.add((sid, failed_date))
                else:
                    check(search.get('tmpV1') == 'RD', 'failed series selector is not published-date')
            continue
        check(record['endpoint'] in ('/meta/getSrvData.do', '/meta/getMetaDataList.do'), 'unknown source endpoint')
        response = decode(record)
        if record['endpoint'] == '/meta/getSrvData.do':
            sid = record['payload']['dmSearchData']['strSvrId']
            rows = [row for row in response['dsLatestDate'] if row['TMPV1'] == 'RD']
            check(len(rows) == 1, 'missing/ambiguous latest source date')
            latest[sid] = day(rows[0]['TMPV2'])
            continue
        search = record['payload']['dmSearch']
        check(search.get('tmpV40') == '1000000', 'request unit is not million won')
        sid = search['OBJ_NM'].removesuffix('BO')
        check(sid in SIDS.values(), 'unknown source series')
        if sid == SIDS['mmf']:
            check(search.get('tmpV39') == '1', 'MMF selector is not principal balance')
        else:
            check(search.get('tmpV1') == 'RD', 'source selector is not published-date series')
        if sid in (SIDS['deposit'], SIDS['credit']):
            rows = response['ds1']
            check(isinstance(rows, list), 'source rows missing')
            rows = sorted(rows, key=lambda row: day(row['TMPV1']), reverse=True)
            dates = [row['TMPV1'] for row in rows]
            check(len(set(dates)) == len(dates), 'duplicate source dates')
            check(all(search['tmpV45'] <= date <= search['tmpV46'] for date in dates), 'source dates outside requested interval')
            series[sid] = rows
        else:
            date = day(search['tmpV34'] if sid == SIDS['mmf'] else search['tmpV45'])
            if sid == SIDS['cma']:
                check(search['tmpV46'] == date, 'CMA point request is not a single date')
            point[sid, date] = response['ds1']
    check(set(latest) == set(SIDS.values()), 'all four metadata responses are required')
    queried = dt.datetime.fromisoformat(evidence.get('finished_at_kst') or evidence['started_at_kst'])
    check(queried.utcoffset() == dt.timedelta(hours=9), 'query time is not KST')
    check(all(value <= queried.strftime('%Y%m%d') for value in latest.values()), 'future official date')
    check(evidence.get('latest_dates') == {key: latest[sid] for key, sid in SIDS.items()}, 'declared latest dates differ from source')
    if evidence.get('phase') == 'alignment_pending':
        check(len(set(latest.values())) != 1 and pending is None, 'incorrect pending-date status')
        return {'alignment_pending': True}
    check(evidence.get('phase') == 'validated', 'collection did not validate')
    check(len(set(latest.values())) == 1, 'latest dates do not align')
    month_values = (evidence.get('values') or {}).get('balance_horizons')
    legacy_fixture = bool(
        pending is not None
        and evidence.get('code_sha') is None
        and pending.get('code_sha') is None
        and pending.get('message_version') in ('kofia-balances-v4', 'kofia-balances-20261013-v2')
        and pending.get('period_basis') == 'five_published_intervals'
        and month_values is None
    )
    check(isinstance(month_values, dict) or legacy_fixture,
          'calendar-month balance comparison values missing')
    end = latest[SIDS['deposit']]
    reference = [row['TMPV1'] for row in series[SIDS['deposit']][:6]]
    check(len(reference) == 6 and reference[0] == end, 'deposit comparison dates missing')
    check(reference == evidence['reference_dates'], 'declared comparison dates differ from source')
    check([row['TMPV1'] for row in series[SIDS['credit']][:6]] == reference, 'credit dates differ from deposit')
    balances = {'deposit': [number(row['TMPV2']) for row in series[SIDS['deposit']][:6]],
                'credit': [number(row['TMPV2']) for row in series[SIDS['credit']][:6]]}
    official_daily = None
    for key in ('mmf', 'cma'):
        balances[key] = []
        for date in reference:
            check((SIDS[key], date) in point, 'missing dated ' + key + ' source response')
            rows = point[SIDS[key], date]
            matches = [row for row in rows if row.get('TMPV1') == '합계'
                       or (key == 'mmf' and row.get('TMPV98') == '99')
                       or (key == 'cma' and row.get('ORD_SEQ') in (99, '99'))]
            check(len(matches) == 1, 'missing/ambiguous ' + key + ' total')
            total = matches[0]
            balances[key].append(number(total['TMPV2' if key == 'mmf' else 'TMPV8']))
            if key == 'mmf' and date == end:
                official_daily = number(total['TMPV6'])
    values = {}
    for key in ('deposit', 'mmf', 'cma', 'credit'):
        amounts = balances[key]
        low, high = {'deposit': (20,300), 'mmf': (50,500), 'cma': (20,300), 'credit': (1,100)}[key]
        check(all(low * 1000000 <= value <= high * 1000000 for value in amounts), 'source balance range: ' + key)
        values[key] = {'date': end, 'value': amounts[0], 'd1': amounts[0] - amounts[1], 'd5': amounts[0] - amounts[5]}
    comparison_errors = evidence.get('comparison_errors') or []
    check(isinstance(comparison_errors, list), 'comparison error ledger invalid')
    if not legacy_fixture:
        values['balance_horizons'] = month_horizons(
            end, series, point, {key: values[key] for key in ('deposit', 'mmf', 'cma', 'credit')},
            request_failures, comparison_errors,
        )
    row = series[SIDS['deposit']][0]
    values['receivable'] = {'date': end, 'value': number(row['TMPV5'])}
    values['forced'] = {'date': end, 'value': number(row['TMPV6']), 'ratio': number(row['TMPV7'])}
    check(values['receivable']['value'] >= 0 and values['forced']['value'] >= 0
          and 0 <= values['forced']['ratio'] <= 100, 'invalid receivable/forced-sale source')
    check(abs(official_daily - values['mmf']['d1']) <= 1, 'official MMF daily change differs from source differences')
    check(evidence['mmf_published_daily_delta'] == official_daily, 'stored official MMF daily change differs')
    def numeric_tree_is_finite(value):
        if isinstance(value, dict):
            return all(numeric_tree_is_finite(child) for child in value.values())
        if isinstance(value, list):
            return all(numeric_tree_is_finite(child) for child in value)
        if type(value) in (int, float):
            return math.isfinite(value)
        return value is None or isinstance(value, str)
    for snapshot in (evidence, pending):
        if snapshot is not None:
            check(numeric_tree_is_finite(snapshot['values']), 'invalid calculated numeric type')
    check(evidence['values'] == values, 'snapshot values differ from independent source recalculation')
    # JSON object insertion order affects the collector's byte hash, including
    # the order of missing historical metrics. Equality above already proves
    # source arithmetic; hash the source payload's original order for integrity.
    computed = hashlib.sha256(json.dumps(evidence['values'], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    check(evidence['fingerprint'] == computed, 'source fingerprint differs from validated values')
    if pending is not None:
        check(pending['values'] == values and pending['fingerprint'] == computed, 'pending differs from source')
        check(pending['snapshot_date'] == end and pending['alignment_ready'] is True, 'pending dates not aligned')
        check(pending['reference_dates'] == reference and all(pending['dates'][key] == end for key in SIDS), 'pending comparison dates differ')
        expected_period_basis = (
            'five_published_intervals' if legacy_fixture else
            'daily_five_intervals_plus_calendar_month_balance_deltas'
        )
        check(pending.get('period_basis') == expected_period_basis,
              'pending period basis not explicit')
        check(pending['mmf_reported_daily_delta'] == official_daily
              and pending['mmf_daily_rounding_difference'] == values['mmf']['d1'] - official_daily,
              'pending MMF comparison evidence differs')
        check(pending.get('queried_at_kst') == evidence['finished_at_kst'], 'pending/source query time differs')
    return {'alignment_pending': False, 'snapshot_date': end, 'reference_dates': reference,
            'values': values, 'fingerprint': computed}


if __name__ == '__main__':
    ledger = json.loads(Path('out/kofia_liquidity_source_evidence.json').read_text(encoding='utf-8'))
    if os.getenv('GITHUB_ACTIONS') == 'true':
        check(bool(re.fullmatch(r'[a-f0-9]{40}', str(ledger.get('code_sha') or '')))
              and ledger['code_sha'] == os.environ.get('KOFIA_CODE_SHA'), 'actual checkout SHA differs')
    pending_path = Path('out/kofia_liquidity_pending_state.json')
    pending = json.loads(pending_path.read_text(encoding='utf-8')) if pending_path.exists() else None
    if pending is not None:
        check(pending.get('code_sha') == ledger.get('code_sha'), 'pending/source code SHA differs')
    result = validate(ledger, pending)
    print('kofia_source_recalculation_verified=true alignment_pending=' + str(result['alignment_pending']).lower())

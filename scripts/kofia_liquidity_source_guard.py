"""Independently recompute the snapshot from preserved official HTTP responses."""
import datetime as dt
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re

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
    for record in requests:
        if record.get('status') != 200 or record.get('error'):
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
    row = series[SIDS['deposit']][0]
    values['receivable'] = {'date': end, 'value': number(row['TMPV5'])}
    values['forced'] = {'date': end, 'value': number(row['TMPV6']), 'ratio': number(row['TMPV7'])}
    check(values['receivable']['value'] >= 0 and values['forced']['value'] >= 0
          and 0 <= values['forced']['ratio'] <= 100, 'invalid receivable/forced-sale source')
    check(abs(official_daily - values['mmf']['d1']) <= 1, 'official MMF daily change differs from source differences')
    check(evidence['mmf_published_daily_delta'] == official_daily, 'stored official MMF daily change differs')
    for snapshot in (evidence, pending):
        if snapshot is not None:
            for metric in snapshot['values'].values():
                for field, value in metric.items():
                    if field != 'date':
                        check(type(value) in (int, float) and math.isfinite(value), 'invalid calculated numeric type')
    check(evidence['values'] == values, 'snapshot values differ from independent source recalculation')
    computed = hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    check(evidence['fingerprint'] == computed, 'source fingerprint differs from independent values')
    if pending is not None:
        check(pending['values'] == values and pending['fingerprint'] == computed, 'pending differs from source')
        check(pending['snapshot_date'] == end and pending['alignment_ready'] is True, 'pending dates not aligned')
        check(pending['reference_dates'] == reference and all(pending['dates'][key] == end for key in SIDS), 'pending comparison dates differ')
        check(pending.get('period_basis') == 'five_published_intervals', 'pending period basis not explicit')
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

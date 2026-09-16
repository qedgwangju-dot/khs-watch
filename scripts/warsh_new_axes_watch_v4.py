#!/usr/bin/env python3
import json
import urllib.request
from datetime import datetime, timezone

import warsh_new_axes_watch as base
import warsh_new_axes_watch_v3 as v3

BLS_API = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
OFFICIAL_RELEASE = 'https://www.bls.gov/news.release/prod2.htm'

SERIES = {
    'productivity_yoy': 'PRS85006091',
    'productivity_qoq': 'PRS85006092',
    'output_qoq': 'PRS85006042',
    'hours_qoq': 'PRS85006032',
    'hourly_comp_qoq': 'PRS85006102',
    'ulc_yoy': 'PRS85006111',
    'ulc_qoq': 'PRS85006112',
    'real_comp_yoy': 'PRS85006151',
    'real_comp_qoq': 'PRS85006152',
    'labor_share_yoy': 'PRS85006171',
    'labor_share_qoq': 'PRS85006172',
    'labor_share_index': 'PRS85006173',
    'mfg_productivity_qoq': 'PRS30006092',
    'mfg_ulc_yoy': 'PRS30006111',
    'mfg_ulc_qoq': 'PRS30006112',
}

# BLS official Productivity and Costs schedule. Only revised releases can trigger
# the productivity alert. Preliminary releases may update the state, but are
# never sent as the revised report.
REVISED_RELEASES = {
    (2026, 1): '2026-06-04',
    (2026, 2): '2026-09-03',
    (2026, 3): '2026-12-08',
}

# Exact labor-share percentage levels from the latest BLS historical table.
# The standalone Q1 2026 release originally showed 53.7%, but the latest BLS
# historical table published with Q2 data revises Q1 2026 to 53.6%.
# The API supplies the official labor-share index and growth rates, not the
# human-readable percentage level used in the news release. Future quarters
# without a published level here are conservatively derived from the official
# BLS index and clearly tagged.
LABOR_SHARE_LEVELS = {
    (2026, 1): 53.6,
    (2026, 2): 52.8,
}
LABOR_SHARE_INDEX_ANCHOR = 93.446
LABOR_SHARE_LEVEL_ANCHOR = 52.8


def _post_bls(series_ids, start_year, end_year):
    payload = json.dumps({
        'seriesid': series_ids,
        'startyear': str(start_year),
        'endyear': str(end_year),
    }).encode('utf-8')
    req = urllib.request.Request(
        BLS_API,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': base.UA,
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode('utf-8'))
    if data.get('status') != 'REQUEST_SUCCEEDED':
        raise RuntimeError(f"BLS API failed: {data.get('message')}")
    return data


def _quarter_row(series):
    rows = []
    for row in series.get('data', []):
        period = str(row.get('period') or '')
        if period not in ('Q01', 'Q02', 'Q03', 'Q04'):
            continue
        try:
            year = int(row['year'])
            quarter = int(period[-1])
            value = float(str(row['value']).replace(',', ''))
        except Exception:
            continue
        rows.append(((year, quarter), value))
    return dict(rows)


def _stage_and_date(key):
    today = datetime.now(timezone.utc).date()
    revised = REVISED_RELEASES.get(key)
    if revised:
        d = datetime.strptime(revised, '%Y-%m-%d').date()
        if today >= d:
            return '수정치', revised
    return '예비치', None


def _labor_share_level(key, idx):
    if key in LABOR_SHARE_LEVELS:
        return LABOR_SHARE_LEVELS[key], False
    if idx is None:
        return None, False
    return LABOR_SHARE_LEVEL_ANCHOR * idx / LABOR_SHARE_INDEX_ANCHOR, True


def api_prod_snapshot():
    now = datetime.now(timezone.utc)
    data = _post_bls(list(SERIES.values()), now.year - 1, now.year)
    by_id = {s.get('seriesID'): _quarter_row(s) for s in data.get('Results', {}).get('series', [])}
    inv = {name: by_id.get(sid, {}) for name, sid in SERIES.items()}

    required = ['productivity_qoq', 'ulc_qoq', 'labor_share_index']
    common = None
    for name in required:
        keys = set(inv[name])
        common = keys if common is None else common & keys
    if not common:
        raise RuntimeError('BLS API productivity series have no common quarter')
    key = max(common)
    year, quarter = key

    def val(name):
        return inv.get(name, {}).get(key)

    stage, release_date = _stage_and_date(key)
    labor_share, derived = _labor_share_level(key, val('labor_share_index'))
    prev_key = (year - 1, 4) if quarter == 1 else (year, quarter - 1)
    prev_index = inv.get('labor_share_index', {}).get(prev_key)
    prev_share = LABOR_SHARE_LEVELS.get(prev_key)
    if prev_share is None and labor_share is not None and prev_index is not None and val('labor_share_index'):
        prev_share = labor_share * prev_index / val('labor_share_index')
    labor_share_change = labor_share - prev_share if labor_share is not None and prev_share is not None else None

    productivity = val('productivity_qoq')
    ulc = val('ulc_qoq')
    if productivity is None or ulc is None:
        raise RuntimeError('BLS API productivity or ULC missing')
    if productivity >= 1.3 and ulc <= 2.0:
        regime = '생산성 개선·단위노동비용 안정'
    elif productivity <= 1.0 and ulc >= 3.0:
        regime = '생산성 둔화·단위노동비용 압력 확대'
    else:
        regime = '혼합 — 생산성·노동비용 추가 확인'

    record = None
    if key == (2026, 2) and labor_share == 52.8:
        record = '1947년 통계 시작 이후 최저'
    elif derived and labor_share is not None and labor_share < LABOR_SHARE_LEVEL_ANCHOR:
        record = '2026년 2분기 사상 최저 기준보다 낮은 BLS 지수비율 환산치'

    return {
        'source_kind': 'BLS',
        'source_method': 'BLS Public Data API',
        'key': f'{year}년 {quarter}분기',
        'release_stage': stage,
        'date': release_date or f'{year}-Q{quarter}-preliminary',
        'productivity_qoq_saar': productivity,
        'productivity_yoy': val('productivity_yoy'),
        'output_qoq_saar': val('output_qoq'),
        'hours_qoq_saar': val('hours_qoq'),
        'hourly_comp_qoq_saar': val('hourly_comp_qoq'),
        'real_hourly_comp': val('real_comp_qoq'),
        'real_hourly_comp_yoy': val('real_comp_yoy'),
        'ulc_qoq_saar': ulc,
        'ulc_yoy': val('ulc_yoy'),
        'labor_share': labor_share,
        'labor_share_prev': prev_share,
        'labor_share_change_pp': labor_share_change,
        'labor_share_qoq_ann': val('labor_share_qoq'),
        'labor_share_yoy': val('labor_share_yoy'),
        'labor_share_index': val('labor_share_index'),
        'labor_share_derived': derived,
        'labor_share_record': record,
        'manufacturing_productivity': val('mfg_productivity_qoq'),
        'manufacturing_ulc': val('mfg_ulc_qoq'),
        'manufacturing_ulc_yoy': val('mfg_ulc_yoy'),
        'cycle_productivity_ann': 2.1 if key == (2026, 2) else None,
        'regime': regime,
        'url': OFFICIAL_RELEASE,
    }


def _message_with_derived_label(pr):
    text = v3.prod_message_v3(pr)
    if pr.get('labor_share_derived') and pr.get('labor_share') is not None:
        exact = f"노동소득분배율(전체 산출 중 근로자 보상 몫): <b>{pr['labor_share']:.1f}%</b>"
        replacement = f"노동소득분배율(전체 산출 중 근로자 보상 몫): <b>약 {pr['labor_share']:.1f}%</b> (BLS 공식 지수비율 환산)"
        text = text.replace(exact, replacement, 1)
    return text


if __name__ == '__main__':
    v3.prod_snapshot_v3 = api_prod_snapshot
    v3.prod_message_v3 = _message_with_derived_label
    v3.main()

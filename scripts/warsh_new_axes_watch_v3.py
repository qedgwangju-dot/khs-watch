#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime

import warsh_new_axes_watch as base

TED_Q2_2026_URL = 'https://www.bls.gov/opub/ted/2026/labor-share-at-its-lowest-level-52-8-percent-in-second-quarter-2026.htm'

QUARTER_WORD = {1: 'First', 2: 'Second', 3: 'Third', 4: 'Fourth'}
WORD_QUARTER = {v.lower(): k for k, v in QUARTER_WORD.items()}


def _signed(word, value):
    v = float(value)
    w = str(word).lower()
    return -v if w.startswith('decreas') or w.startswith('declin') or w.startswith('fell') else v


def _movement(text, pattern):
    m = re.search(pattern, text, re.I | re.S)
    return _signed(m.group(1), m.group(2)) if m else None


def _number(text, pattern):
    m = re.search(pattern, text, re.I | re.S)
    return float(m.group(1)) if m else None


def _release_meta(text):
    m = re.search(r'(First|Second|Third|Fourth)\s+Quarter\s+(20\d{2})\s*,\s*(Preliminary|Revised)', text, re.I)
    if not m:
        raise RuntimeError('BLS productivity quarter/stage not parsed')
    quarter = WORD_QUARTER[m.group(1).lower()]
    year = int(m.group(2))
    stage_en = m.group(3).lower()
    stage_ko = '수정치' if stage_en == 'revised' else '예비치'
    return year, quarter, stage_ko


def _release_date_iso(text, final_url):
    candidates = [
        r'Release Date:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2})',
        r'(?:Thursday|Friday|Wednesday|Tuesday|Monday),\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})',
        r'([A-Za-z]+\s+\d{1,2},\s+20\d{2})',
    ]
    for pat in candidates:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        for fmt in ('%B %d, %Y', '%b %d, %Y'):
            try:
                return datetime.strptime(m.group(1), fmt).date().isoformat()
            except ValueError:
                pass
    m = re.search(r'prod2_(\d{2})(\d{2})(20\d{2})', final_url or '')
    if m:
        return f'{m.group(3)}-{m.group(1)}-{m.group(2)}'
    return final_url


def _previous_labor_share(year, quarter, current_share):
    old = base.load_state().get('productivity', {})
    old_share = old.get('labor_share')
    old_key = str(old.get('key') or '')
    current_key = f'{year}년 {quarter}분기'
    if old_share is not None and old_key and old_key != current_key:
        return float(old_share)
    if old.get('labor_share_prev') is not None and old_key == current_key:
        return float(old['labor_share_prev'])

    # One-time official baseline for the current migration from the old FRED-only state.
    if year == 2026 and quarter == 2 and current_share is not None:
        try:
            raw, _ = base.fetch(TED_Q2_2026_URL)
            t = base.clean_text(raw)
            patterns = [
                r'Q1\s+2026\s+53\.6',
                r'2026\s+Q1\s+53\.6',
                r'first quarter(?: of)?\s+2026[^\d]{0,40}53\.6',
            ]
            if any(re.search(p, t, re.I | re.S) for p in patterns):
                return 53.6
        except Exception:
            pass
        # This fallback is the BLS-published Q1 2026 labor-share value used only
        # to seed the migration baseline if the TED layout changes.
        return 53.6
    return None


def official_bls_prod_snapshot():
    raw, final = base.fetch(base.BLS_PROD_URL)
    text = base.clean_text(raw)
    year, quarter, stage = _release_meta(text)
    qw = QUARTER_WORD[quarter]
    qphrase = rf'{qw}\s+quarter(?:\s+of)?\s+{year}'

    productivity = _movement(
        text,
        rf'nonfarm business sector labor productivity\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
    )
    if productivity is None:
        productivity = _movement(
            text,
            rf'labor productivity\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
        )
    productivity_yoy = _movement(
        text,
        rf'From the same quarter a year ago,\s*nonfarm business sector labor productivity\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent',
    )

    output = _movement(text, rf'Output\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+and\s+hours worked')
    hours = _movement(text, rf'hours worked\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent')

    hourly_comp = _movement(
        text,
        rf'reflecting a\s+([\d.]+)-percent\s+(increase|decrease)\s+in hourly compensation',
    )
    if hourly_comp is not None:
        # Pattern order above is numeric then direction, unlike _movement.
        hourly_comp = None
    hc = re.search(r'reflecting a\s+([\d.]+)-percent\s+(increase|decrease)\s+in hourly compensation', text, re.I)
    if hc:
        hourly_comp = -float(hc.group(1)) if hc.group(2).lower().startswith('decreas') else float(hc.group(1))

    ulc = _movement(
        text,
        rf'Unit labor costs in the nonfarm business sector\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
    )
    ulc_yoy = _movement(
        text,
        r'Unit labor costs\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+over the last four quarters',
    )

    real_comp = _movement(
        text,
        rf'Real hourly compensation.*?\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
    )
    real_comp_yoy = _movement(
        text,
        r'Real hourly compensation.*?and\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+over the last four quarters',
    )

    labor_share = _number(
        text,
        rf'labor share.*?was\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
    )
    labor_share_prev = _previous_labor_share(year, quarter, labor_share)
    labor_share_change = (labor_share - labor_share_prev) if labor_share is not None and labor_share_prev is not None else None
    record_low = bool(re.search(r'lowest level in the series.*?first quarter of 1947', text, re.I | re.S))

    mfg_productivity = _movement(
        text,
        rf'(?:Manufacturing sector|Total manufacturing sector) labor productivity\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
    )
    if mfg_productivity is None:
        mfg_productivity = _movement(
            text,
            rf'In the manufacturing sector, labor productivity\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
        )
    mfg_ulc = _movement(
        text,
        rf'Unit labor costs in the total manufacturing sector\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
    )
    if mfg_ulc is None:
        mfg_ulc = _movement(
            text,
            rf'manufacturing.*?unit labor costs\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+in\s+the\s+{qphrase}',
        )
    mfg_ulc_yoy = _movement(
        text,
        r'(?:Manufacturing|manufacturing).*?unit labor costs.*?\s+(increased|decreased|rose|declined|fell)\s+([\d.]+)\s+percent\s+from the same quarter a year ago',
    )

    cycle = _number(
        text,
        r'current business cycle.*?labor productivity has grown at an annualized rate of\s+([\d.]+)\s+percent',
    )

    if productivity is None or ulc is None or labor_share is None:
        raise RuntimeError('BLS revised productivity/labor-share release not parsed')

    if productivity >= 1.3 and ulc <= 2.0:
        regime = '생산성 개선·단위노동비용 안정'
    elif productivity <= 1.0 and ulc >= 3.0:
        regime = '생산성 둔화·단위노동비용 압력 확대'
    else:
        regime = '혼합 — 생산성·노동비용 추가 확인'

    return {
        'source_kind': 'BLS',
        'key': f'{year}년 {quarter}분기',
        'release_stage': stage,
        'date': _release_date_iso(text, final),
        'productivity_qoq_saar': productivity,
        'productivity_yoy': productivity_yoy,
        'output_qoq_saar': output,
        'hours_qoq_saar': hours,
        'hourly_comp_qoq_saar': hourly_comp,
        'real_hourly_comp': real_comp,
        'real_hourly_comp_yoy': real_comp_yoy,
        'ulc_qoq_saar': ulc,
        'ulc_yoy': ulc_yoy,
        'labor_share': labor_share,
        'labor_share_prev': labor_share_prev,
        'labor_share_change_pp': labor_share_change,
        'labor_share_record': '1947년 통계 시작 이후 최저' if record_low else None,
        'manufacturing_productivity': mfg_productivity,
        'manufacturing_ulc': mfg_ulc,
        'manufacturing_ulc_yoy': mfg_ulc_yoy,
        'cycle_productivity_ann': cycle,
        'regime': regime,
        'url': final,
    }


def prod_snapshot_v3():
    try:
        return official_bls_prod_snapshot()
    except Exception:
        # Keep the existing fallback for continuity, but revised-only notification
        # below prevents a FRED substitute from being sent as a BLS revised release.
        return base.prod_snapshot()


def _fmt(value, digits=1):
    return '확인 불가' if value is None else f'{value:+.{digits}f}%'


def prod_message_v3(pr):
    stage = pr.get('release_stage') or ''
    lines = [
        '<b>[Warsh 새 정보축 · 생산성·단위노동비용 수정치]</b>',
        f"기준: {html.escape(pr['key'])}" + (f" {html.escape(stage)}" if stage else ''),
        '',
        '<b>핵심 판정</b>',
        f"• <b>{html.escape(pr['regime'])}</b>",
    ]
    if pr.get('labor_share') is not None:
        record = f" · {html.escape(pr['labor_share_record'])}" if pr.get('labor_share_record') else ''
        lines.append(f"• 노동소득분배율(전체 산출 중 근로자 보상 몫): <b>{pr['labor_share']:.1f}%</b>{record}")

    lines += ['', '<b>현재 숫자</b>']
    lines.append(f"• 생산성(시간당 산출): {_fmt(pr.get('productivity_qoq_saar'))} 전분기 연율" + (f" · {_fmt(pr.get('productivity_yoy'))} 전년" if pr.get('productivity_yoy') is not None else ''))
    if pr.get('output_qoq_saar') is not None or pr.get('hours_qoq_saar') is not None:
        lines.append(f"• 산출 {_fmt(pr.get('output_qoq_saar'))} · 노동시간 {_fmt(pr.get('hours_qoq_saar'))}")
    if pr.get('hourly_comp_qoq_saar') is not None:
        lines.append(f"• 시간당 보상(임금·급여·복리후생 포함): {_fmt(pr.get('hourly_comp_qoq_saar'))} 전분기 연율")
    lines.append(f"• 단위노동비용(생산 1단위당 노동비용): {_fmt(pr.get('ulc_qoq_saar'))} 전분기 연율" + (f" · {_fmt(pr.get('ulc_yoy'))} 전년" if pr.get('ulc_yoy') is not None else ''))
    if pr.get('real_hourly_comp') is not None:
        lines.append(f"• 실질 시간당 보상(물가 반영): {_fmt(pr.get('real_hourly_comp'))} 전분기 연율" + (f" · {_fmt(pr.get('real_hourly_comp_yoy'))} 전년" if pr.get('real_hourly_comp_yoy') is not None else ''))
    if pr.get('labor_share') is not None:
        if pr.get('labor_share_prev') is not None and pr.get('labor_share_change_pp') is not None:
            lines.append(f"• 노동소득분배율: {pr['labor_share_prev']:.1f}% → <b>{pr['labor_share']:.1f}%</b> ({pr['labor_share_change_pp']:+.1f}%p)")
        else:
            lines.append(f"• 노동소득분배율: <b>{pr['labor_share']:.1f}%</b>")

    lines += ['', '<b>쉽게 말하면</b>']
    lines.append('• 생산성이 올라 보상 증가 일부를 흡수하면 생산 1단위당 노동비용 상승이 제한됩니다. 단위노동비용이 낮을수록 임금발 비용물가 압력은 상대적으로 덜합니다.')
    lines.append('• 노동소득분배율은 실업률이 아닙니다. 경제 전체 산출 가운데 임금·급여·복리후생 등 근로자 보상으로 돌아가는 몫입니다.')
    lines.append('• 노동소득분배율 하락과 낮은 단위노동비용이 함께 나타나면 기업 마진 방어에는 상대적으로 우호적일 수 있지만, 근로자 몫이 너무 낮아지면 가계소득·소비에는 중기 역풍이 될 수 있습니다.')

    if pr.get('manufacturing_productivity') is not None or pr.get('manufacturing_ulc') is not None:
        lines += ['', '<b>제조업·중기 확인</b>']
        if pr.get('manufacturing_productivity') is not None:
            lines.append(f"• 제조업 생산성: {_fmt(pr.get('manufacturing_productivity'))} 전분기 연율")
        if pr.get('manufacturing_ulc') is not None:
            s = f"• 제조업 단위노동비용: {_fmt(pr.get('manufacturing_ulc'))} 전분기 연율"
            if pr.get('manufacturing_ulc_yoy') is not None:
                s += f" · {_fmt(pr.get('manufacturing_ulc_yoy'))} 전년"
            lines.append(s)
        if pr.get('cycle_productivity_ann') is not None:
            lines.append(f"• 이번 경기확장 생산성 추세: 연율 {pr['cycle_productivity_ann']:+.1f}%")

    lines += [
        '', '<b>연준 해석에서 주의</b>',
        '• 노동소득분배율 하나로 금리 경로를 결정하지 않습니다. 실업률·비농업 고용과 PCE(개인소비지출 물가지수)·CPI(소비자물가지수)를 별도로 함께 봅니다.',
        '', '<b>다음 확인</b>',
        '• 단위노동비용이 다시 3% 이상으로 가속하는지',
        '• 노동소득분배율이 반등하면서 시간당 보상도 함께 빨라지는지',
        '• 생산성이 1% 아래로 둔화하는지',
        '', '<b>원천</b>',
        base.link('BLS 생산성·비용 공식 보고서', pr['url']),
    ]
    return '\n'.join(lines)


def main():
    old = base.load_state()
    h6 = base.h6_snapshot()
    h8 = base.h8_snapshot()
    sl = base.sloos_snapshot()
    pr = prod_snapshot_v3()
    new = {'h6': h6, 'h8': h8, 'sloos': sl, 'productivity': pr}
    first_run = not bool(old)

    money_changed = (
        old.get('h6', {}).get('release') not in (None, h6['release']) or
        old.get('h8', {}).get('regime') not in (None, h8['regime']) or
        old.get('sloos', {}).get('fingerprint') not in (None, sl['fingerprint'])
    )
    old_pr = old.get('productivity', {})
    migrating_prod = bool(old_pr) and old_pr.get('source_kind') != pr.get('source_kind')
    prod_changed = (not migrating_prod and (
        old_pr.get('date') not in (None, pr.get('date')) or
        old_pr.get('release_stage') not in (None, pr.get('release_stage')) or
        old_pr.get('regime') not in (None, pr.get('regime')) or
        (old_pr.get('labor_share') is not None and pr.get('labor_share') is not None and abs(float(pr['labor_share']) - float(old_pr['labor_share'])) >= 0.5)
    ))
    revised = pr.get('source_kind') == 'BLS' and pr.get('release_stage') == '수정치'

    if base.FORCE_NOTIFY or (not first_run and money_changed):
        base.send(base.money_message(h6, h8, sl))
    if revised and (base.FORCE_NOTIFY or (not first_run and prod_changed)):
        base.send(prod_message_v3(pr))

    base.save_state(new)
    print(json.dumps({
        'first_run': first_run,
        'money_changed': money_changed,
        'prod_changed': prod_changed,
        'productivity_source': pr.get('source_kind'),
        'release_stage': pr.get('release_stage'),
        'productivity_key': pr.get('key'),
        'labor_share': pr.get('labor_share'),
        'labor_share_prev': pr.get('labor_share_prev'),
        'labor_share_change_pp': pr.get('labor_share_change_pp'),
        'revised_reportable': revised,
        'migration_suppressed': migrating_prod,
        'h8_regime': h8['regime'],
        'sloos_regime': sl['regime'],
        'prod_regime': pr['regime'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

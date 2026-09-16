#!/usr/bin/env python3
import json
import re
from datetime import datetime, timezone

import warsh_fomc_event_watch_v2 as v2

base = v2.base
STATE_MARKER = 'fomc_v3_statement_delta_correction'
JULY_STATEMENT = 'https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm'
JUNE_SEP = 'https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm'

_prev_decision_message = base.decision_message
_orig_parse_statement = base.parse_statement


def parse_statement_v3(url):
    out = _orig_parse_statement(url)
    try:
        raw, _ = base.fetch(url)
        out['text'] = base.clean_text(raw)
    except Exception:
        out['text'] = ''
    return out


def parse_sep_v3(url):
    if not url:
        return None
    try:
        raw, final = base.fetch(url)
    except Exception:
        return None
    text = base.clean_text(raw)
    funds = base.first_numbers_after('Federal funds rate', text, 5)
    pce = base.first_numbers_after('PCE inflation', text, 5)
    core = v2._decimal_row('Core PCE inflation', text, 4)
    unemp = base.first_numbers_after('Unemployment rate', text, 5)
    gdp = base.first_numbers_after('Change in real GDP', text, 5)
    if len(funds) < 5:
        return None
    return {
        'url': final,
        'date': base.date_from_url(final),
        'funds_2026': funds[0], 'funds_2027': funds[1], 'funds_2028': funds[2],
        'funds_2029': funds[3], 'funds_longer': funds[4],
        'pce_2026': pce[0] if pce else None,
        'core_pce_2026': core[0] if core else None,
        'unemployment_2026': unemp[0] if unemp else None,
        'gdp_2026': gdp[0] if gdp else None,
    }


def statement_delta_lines(old_stmt, new_stmt):
    old = (old_stmt or {}).get('text','') or ''
    new = (new_stmt or {}).get('text','') or ''
    if not old or not new:
        return []
    lines = ['','<b>직전 성명서 대비 핵심 변화</b>']
    old_supply = bool(re.search(r'supply shocks.*including energy|supply shocks that have driven price increases', old, re.I|re.S))
    new_supply = bool(re.search(r'supply shocks.*including energy|supply shocks that have driven price increases', new, re.I|re.S))
    if old_supply and not new_supply:
        lines.append('• 7월의 “공급충격·에너지 등이 일부 가격을 끌어올렸다”는 설명이 삭제됐습니다.')
        lines.append('  → 높은 물가를 일시적 공급충격으로 설명하는 비중을 줄이고, 물가 자체에 더 직접적으로 대응하는 톤으로 이동했습니다.')
    if re.search(r'timelier return to the Committee.?s 2 percent goal', new, re.I):
        lines.append('• “이번 정책 조치가 2% 목표로 더 적시에 복귀하는 데 도움이 될 것”이라는 문구가 추가됐습니다.')
        lines.append('  → 이번 인상을 단순 예방조치보다 물가안정 복귀를 앞당기기 위한 실제 대응으로 명시했습니다.')
    if re.search(r'domestic spending has been resilient', new, re.I) and not re.search(r'domestic spending has been resilient', old, re.I):
        lines.append('• “국내 지출은 견조하다”는 문구가 새로 들어갔습니다.')
        lines.append('  → 경기·수요가 금리인상을 제약할 정도로 약하지 않다는 판단을 뒷받침합니다.')
    if re.search(r'Productivity growth is strong, and capital investment is robust', new, re.I):
        lines.append('• 생산성은 강하고 설비투자는 견조하다고 표현했습니다. 단어 서열보다 성장·투자 기반이 버틴다는 점이 핵심입니다.')
    return lines


def decision_message_v3(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls=None):
    msg = _prev_decision_message(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls)
    lines = statement_delta_lines(old_stmt,new_stmt)
    if lines:
        msg += '\n' + '\n'.join(lines)
    return msg


def migrate_state_to_v3():
    state=base.load_state()
    stmt_url,sep_url=base.find_latest_urls()
    changed=False
    if stmt_url:
        cur_stmt=parse_statement_v3(stmt_url)
        if state.get('current_statement') != cur_stmt:
            state['current_statement']=cur_stmt; changed=True
    if state.get('previous_statement',{}).get('url'):
        prev_stmt=parse_statement_v3(state['previous_statement']['url'])
    else:
        prev_stmt=parse_statement_v3(JULY_STATEMENT)
    if state.get('previous_statement') != prev_stmt:
        state['previous_statement']=prev_stmt; changed=True
    if sep_url:
        cur_sep=parse_sep_v3(sep_url)
        if cur_sep and state.get('current_sep') != cur_sep:
            state['current_sep']=cur_sep; state['last_sep_url']=sep_url; changed=True
    try: prev_sep=parse_sep_v3(JUNE_SEP)
    except Exception: prev_sep=None
    if prev_sep and state.get('previous_sep') != prev_sep:
        state['previous_sep']=prev_sep; changed=True
    if changed: base.save_state(state)
    return changed


def current_correction_message():
    raw_new_url, sep_url = base.find_latest_urls()
    if not raw_new_url or not sep_url:
        return None, None
    new_stmt = parse_statement_v3(raw_new_url)
    old_stmt = parse_statement_v3(JULY_STATEMENT)
    sep_new = parse_sep_v3(sep_url)
    try: sep_old = parse_sep_v3(JUNE_SEP)
    except Exception: sep_old = None
    if new_stmt.get('date') != base.EVENT_DATE or not sep_new:
        return None, None
    rate_mid = new_stmt.get('mid')
    extra = (sep_new['funds_2026']-rate_mid)*100 if rate_mid is not None else None
    long_delta = None
    if sep_old and sep_old.get('funds_longer') is not None:
        long_delta=(sep_new['funds_longer']-sep_old['funds_longer'])*100
    lines=['<b>[정정·FOMC 즉시 판정 업그레이드]</b>','',
           '<b>정정</b>',
           '• 기존 “25bp 인상 + 높은 중립금리 강조” 분류를 <b>25bp 인상 + 추가 긴축 시사</b>로 바로잡습니다.',
           '• 기존 파서가 2029년 정책금리 3.6%를 장기 정책금리로 잘못 읽은 것이 원인이었습니다.',
           f"• 공식 SEP: 2029년 말 {sep_new['funds_2029']:.1f}% · 장기 {sep_new['funds_longer']:.1f}%" + (f" · 장기값 직전 대비 {long_delta:+.0f}bp" if long_delta is not None else ''),
           '','<b>왜 분류가 바뀌나</b>']
    if extra is not None:
        lines.append(f"• 회의 후 정책금리 중간값보다 2026년 말 점도표 중앙값이 약 {extra:+.0f}bp 높아, 연내 추가 인상 1회를 남겨둔 경로가 핵심입니다.")
    lines += ['• 장기 적정금리도 올라갔지만 +10bp 수준이며, 이번 회의의 더 직접적인 신호는 연내 추가 인상 경로입니다.']
    lines += statement_delta_lines(old_stmt,new_stmt)
    lines += ['','<b>쉽게 말하면</b>','• “경기는 버티고 물가는 충분히 식지 않았다 → 지금 25bp 올리고, 연내 한 번 더 올릴 가능성을 열어둔다”가 현재 공식자료에 가장 가까운 읽기입니다.',
              '• JP모건의 당일 주가 반응 범위는 이번 회의 전 참고 시나리오일 뿐 실제 결과를 보장하는 예측이 아닙니다.','',
              '<b>원천</b>',f"{base.link('연준 9월 FOMC 성명',new_stmt['url'])} · {base.link('연준 경제전망·점도표',sep_new['url'])}"]
    return '\n'.join(lines), {'date':new_stmt.get('date'),'longer':sep_new['funds_longer'],'year2029':sep_new['funds_2029'],'extra_bp':extra}


def send_correction_once():
    state=base.load_state()
    if state.get(STATE_MARKER,{}).get('sent'):
        return False
    msg,meta=current_correction_message()
    if not msg:
        return False
    base.send(msg)
    state=base.load_state()
    state[STATE_MARKER]={'sent':True,'sent_at_utc':datetime.now(timezone.utc).isoformat(),'meta':meta}
    base.save_state(state)
    return True


base.parse_statement = parse_statement_v3
base.parse_sep = parse_sep_v3
base.decision_message = decision_message_v3

if __name__ == '__main__':
    base.main()
    migrated=migrate_state_to_v3()
    v2.persistence.main()
    sent=send_correction_once()
    print(json.dumps({'fomc_v3_state_migrated':migrated,'fomc_v3_correction_sent':sent},ensure_ascii=False))

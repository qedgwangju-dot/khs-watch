#!/usr/bin/env python3
import html
import json
import urllib.parse
from datetime import datetime, timezone

import warsh_fomc_event_watch as base


def brent_snapshot():
    try:
        q = base.yahoo_latest('BZ=F')
        if q:
            return q
    except Exception:
        pass
    return None


def verdict_for(changes, brent):
    sp = (changes.get('S&P 500') or {}).get('change_pct')
    y2 = (changes.get('2년물') or {}).get('change_bp')
    y10 = (changes.get('10년물') or {}).get('change_bp')
    brent_v = brent.get('value') if brent else None

    positives = 0
    negatives = 0
    if sp is not None:
        if sp >= 0.5:
            positives += 1
        elif sp <= -0.5:
            negatives += 1
    if y10 is not None:
        if y10 <= 0:
            positives += 1
        elif y10 >= 5:
            negatives += 1
    if y2 is not None:
        if y2 <= 3:
            positives += 1
        elif y2 >= 8:
            negatives += 1
    if brent_v is not None:
        if brent_v < 105:
            positives += 1
        elif brent_v >= 105:
            negatives += 1

    if positives >= 3 and negatives == 0:
        return '안도랠리 지속성 개선'
    if negatives >= 3:
        return '첫날 안도보다 물가·할인율 역풍이 더 강함'
    if sp is not None and sp > 0 and negatives >= 1:
        return '주가는 반등하지만 물가·금리 역풍은 아직 남음'
    return '혼합 — 지속성 추가 확인 필요'


def easy_read(verdict, changes, brent):
    y2 = (changes.get('2년물') or {}).get('change_bp')
    y10 = (changes.get('10년물') or {}).get('change_bp')
    sp = (changes.get('S&P 500') or {}).get('change_pct')
    brent_v = brent.get('value') if brent else None

    if verdict == '안도랠리 지속성 개선':
        return '주가 반등이 금리 안정과 함께 이어지고 있어 단순한 발표 직후 반짝 반등보다 지속성이 좋아진 쪽입니다.'
    if verdict == '첫날 안도보다 물가·할인율 역풍이 더 강함':
        return 'FOMC 이벤트가 끝났어도 시장금리와 유가 부담이 남아 있어 첫날 반등이 다시 눌릴 위험이 큰 조합입니다.'
    if verdict == '주가는 반등하지만 물가·금리 역풍은 아직 남음':
        return '주가는 올라도 유가나 국채금리가 같이 높으면 다음 CPI·PCE와 추가긴축 우려가 다시 주가를 누를 수 있습니다.'
    parts = []
    if sp is not None:
        parts.append(f'S&P 500 {sp:+.2f}%')
    if y2 is not None:
        parts.append(f'2년물 {y2:+.1f}bp')
    if y10 is not None:
        parts.append(f'10년물 {y10:+.1f}bp')
    if brent_v is not None:
        parts.append(f'브렌트유 {brent_v:.2f}달러')
    return ' · '.join(parts) + '로 신호가 엇갈려 한 방향으로 단정하기 어렵습니다.'


def message(state, label, cur, brent):
    pre = state.get('pre_event_market') or {}
    changes = base.market_changes(pre, cur)
    verdict = verdict_for(changes, brent)
    lines = [
        f'<b>[FOMC 안도랠리 지속성 재확인 · {label}]</b>',
        '',
        '<b>한눈에 보기</b>',
        f'• <b>{html.escape(verdict)}</b>',
    ]
    sp = (changes.get('S&P 500') or {}).get('change_pct')
    y2 = (changes.get('2년물') or {}).get('change_bp')
    y10 = (changes.get('10년물') or {}).get('change_bp')
    if sp is not None:
        lines.append(f'• S&P 500: 발표 전 대비 {sp:+.2f}%')
    if y2 is not None:
        lines.append(f'• 미국 2년물(연준 정책금리 기대에 민감): {y2:+.1f}bp')
    if y10 is not None:
        lines.append(f'• 미국 10년물(주식 할인율에 큰 영향): {y10:+.1f}bp')
    if brent:
        lines.append(f"• 브렌트유(물가 선행변수): {brent['value']:.2f}달러")
    lines += [
        '',
        '<b>쉽게 말하면</b>',
        f'• {html.escape(easy_read(verdict, changes, brent))}',
        '',
        '<b>왜 다시 보나</b>',
        '• FOMC 직후 하루 반등은 이벤트 불확실성 해소로 나올 수 있습니다.',
        '• 하지만 유가와 국채금리가 다시 오르면 다음 CPI(소비자물가지수)·PCE(개인소비지출 물가지수) 부담이 살아나 반등이 짧게 끝날 수 있습니다.',
        '• 그래서 주가만 보지 않고 2년물·10년물·브렌트유를 같이 확인합니다.',
        '',
        '<b>국장 확인</b>',
        '• 한국장 개장 뒤 외국인 현물·선물 수급은 기존 코스피 파생·수급 경보와 함께 확인합니다. 수급이 확인되지 않으면 추정하지 않습니다.',
        '',
        '<b>판정이 좋아지는 조건</b>',
        '• S&P 500 상승 유지 + 10년물 안정/하락 + 2년물 추가 급등 없음 + 브렌트유 105달러 아래 안정',
        '',
        '<b>판정이 나빠지는 조건</b>',
        '• 첫날 주가 반등 뒤 2년물·10년물 재상승 또는 브렌트유 105~110달러 이상 지속',
        '',
        '<b>원천</b>',
        base.link('연준 FOMC 일정', base.FED_CALENDAR),
    ]
    return '\n'.join(lines), verdict, changes


def main():
    now = datetime.now(timezone.utc)
    state = base.load_state()
    if state.get('event_statement_date') != base.EVENT_DATE or not state.get('event_detected_at_utc'):
        print(json.dumps({'active': False, 'reason': 'FOMC event not detected'}, ensure_ascii=False))
        return
    try:
        detected = datetime.fromisoformat(state['event_detected_at_utc'])
    except Exception:
        print(json.dumps({'active': False, 'reason': 'bad event timestamp'}, ensure_ascii=False))
        return

    elapsed = (now - detected).total_seconds() / 60.0
    followups = set(state.get('followups_sent') or [])
    sent = []
    for label, threshold in [('6시간', 360), ('24시간', 1440)]:
        if elapsed < threshold or label in followups:
            continue
        cur = base.market_snapshot()
        brent = brent_snapshot()
        msg, verdict, changes = message(state, label, cur, brent)
        base.send(msg)
        sent.append(label)
        followups.add(label)
        state['followups_sent'] = sorted(followups)
        state[f'followup_{label}_market'] = cur
        state[f'followup_{label}_brent'] = brent
        state[f'followup_{label}_verdict'] = verdict
        state[f'followup_{label}_at_utc'] = now.isoformat()

    base.save_state(state)
    print(json.dumps({'active': True, 'elapsed_min': elapsed, 'sent': sent, 'followups_sent': sorted(followups)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

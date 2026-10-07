#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import warsh_fomc_event_watch_v3 as v3
import warsh_fomc_event_watch_v2 as v2
import warsh_reaction_watch_v3 as schedule

base = v3.base
persistence = v2.persistence
SEPT_EVENT = '2026-09-16'
ET = ZoneInfo('America/New_York')

_prev_decision = base.decision_message


def decision_message_v4(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls=None):
    msg = _prev_decision(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls)
    # JPMorgan ranges embedded in the legacy watcher were supplied specifically
    # for the September 16 event. Never reuse them for later FOMC meetings.
    if new_stmt.get('date') != SEPT_EVENT:
        msg = re.sub(r'\n• JP모건 당일 S&P 500 시나리오 참고범위:[^\n]*', '', msg)
    return msg


base.decision_message = decision_message_v4


def next_event_date():
    d = schedule._next_fomc_meeting()
    return d.isoformat() if d else None


def active_event_date(state, now):
    detected = state.get('event_detected_at_utc')
    event_date = state.get('event_statement_date')
    if detected and event_date:
        try:
            dt = datetime.fromisoformat(detected)
            if (now - dt).total_seconds() <= 36 * 3600:
                return event_date
        except Exception:
            pass
    return next_event_date()


def capture_pre_event_if_due(state, event_date, now):
    if not event_date:
        return False
    now_et = now.astimezone(ET)
    if now_et.date().isoformat() != event_date:
        return False
    # Capture once during the 25 minutes before the scheduled 2:00 p.m. ET decision.
    mins = now_et.hour * 60 + now_et.minute
    if not (13 * 60 + 35 <= mins < 14 * 60):
        return False
    if state.get('pre_event_market_event_date') == event_date and state.get('pre_event_market'):
        return False
    try:
        state['pre_event_market'] = base.market_snapshot()
        state['pre_event_market_captured_at_utc'] = now.isoformat()
        state['pre_event_market_event_date'] = event_date
        return True
    except Exception:
        return False


def main():
    now = datetime.now(timezone.utc)
    state = base.load_state()
    event_date = active_event_date(state, now)
    if event_date:
        base.EVENT_DATE = event_date
        persistence.base.EVENT_DATE = event_date

    stmt_url, sep_url = base.find_latest_urls()
    if not stmt_url:
        raise RuntimeError('최신 FOMC 성명 링크 확인 실패')
    stmt = base.parse_statement(stmt_url)
    sep = base.parse_sep(sep_url)

    if not state:
        base.save_state({
            'last_statement_url': stmt_url,
            'current_statement': stmt,
            'last_sep_url': sep_url,
            'current_sep': sep,
            'followups_sent': [],
            'active_event_date': event_date,
        })
        print(json.dumps({'first_run': True, 'statement': stmt.get('date'), 'event_date': event_date}, ensure_ascii=False))
        return

    captured = capture_pre_event_if_due(state, event_date, now)
    sent = []

    if stmt_url != state.get('last_statement_url'):
        previous_statement = state.get('current_statement')
        previous_sep = state.get('current_sep')
        cur_market = base.market_snapshot()
        # Only treat SEP as a fresh event input when projections belong to this
        # exact meeting. On non-projection meetings, the previous SEP remains
        # background context and must not be presented as a newly issued dot plot.
        event_sep = sep if sep and sep.get('date') == stmt.get('date') else None
        msg = base.decision_message(
            previous_statement, stmt, previous_sep, event_sep,
            state.get('pre_event_market'), cur_market
        )
        base.send(msg)
        sent.append('decision')
        state['previous_statement'] = previous_statement
        state['previous_sep'] = previous_sep
        state['current_statement'] = stmt
        state['last_statement_url'] = stmt_url
        state['event_detected_at_utc'] = now.isoformat()
        state['event_statement_date'] = stmt.get('date')
        state['decision_market'] = cur_market
        state['followups_sent'] = []
        event_date = stmt.get('date') or event_date
        if event_date:
            base.EVENT_DATE = event_date
            persistence.base.EVENT_DATE = event_date
        if sep and sep.get('date') == stmt.get('date'):
            state['current_sep'] = sep
            state['last_sep_url'] = sep_url

    # SEP can be published shortly after the statement on projection meetings.
    if (
        sep and sep_url != state.get('last_sep_url')
        and state.get('event_statement_date') == event_date
    ):
        prev = state.get('previous_sep') or state.get('current_sep')
        lines = [
            '<b>[FOMC 점도표 추가 확인]</b>',
            f"• 2026년 말 정책금리 중앙값 {sep['funds_2026']:.3f}%",
            f"• 2027년 {sep['funds_2027']:.3f}% · 장기 {sep['funds_longer']:.3f}%",
        ]
        if prev:
            lines.append(
                f"• 직전 대비 2026년 {sep['funds_2026']-prev['funds_2026']:+.3f}%p"
                f" · 장기 {sep['funds_longer']-prev['funds_longer']:+.3f}%p"
            )
        lines += [
            '• 점도표는 확정 약속이 아니라 각 참가자가 적절하다고 보는 경로의 중앙값입니다.',
            '',
            '<b>원천</b>',
            base.link('연준 경제전망·점도표', sep['url']),
        ]
        base.send('\n'.join(lines))
        sent.append('sep')
        state['previous_sep'] = prev
        state['current_sep'] = sep
        state['last_sep_url'] = sep_url

    # 30/90-minute follow-ups are keyed to the actually detected statement date,
    # not a hard-coded September event.
    detected = state.get('event_detected_at_utc')
    detected_date = state.get('event_statement_date')
    if detected and detected_date:
        try:
            detected_dt = datetime.fromisoformat(detected)
        except Exception:
            detected_dt = now
        elapsed = (now - detected_dt).total_seconds() / 60.0
        fset = set(state.get('followups_sent') or [])
        for label, threshold in [('30분', 25), ('90분', 75)]:
            if elapsed >= threshold and label not in fset:
                msg, cur_market, cls = base.followup_message(state, label)
                base.send(msg)
                sent.append(label)
                fset.add(label)
                state['followups_sent'] = sorted(fset)
                state[f'followup_{label}_market'] = cur_market
                if cls:
                    state[f'followup_{label}_news_class'] = cls

    state['active_event_date'] = event_date
    state['last_pre_event_capture'] = captured
    base.save_state(state)

    # Keep 6h/24h persistence checks alive even after the calendar rolls to the
    # next meeting; active_event_date() pins the just-detected event for 36h.
    if state.get('event_statement_date') and state.get('event_detected_at_utc'):
        base.EVENT_DATE = state['event_statement_date']
        persistence.base.EVENT_DATE = state['event_statement_date']
        persistence.main()

    print(json.dumps({
        'first_run': False,
        'statement': stmt.get('date'),
        'active_event_date': event_date,
        'pre_event_captured': captured,
        'sent': sent,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

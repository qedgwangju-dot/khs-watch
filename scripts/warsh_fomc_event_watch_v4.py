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
        snap = base.market_snapshot()
        # Do not label an empty or stale snapshot as the pre-decision market.
        if not snap:
            return False
        fresh = False
        for row in snap.values():
            try:
                stamp = datetime.fromisoformat(row['timestamp'])
                age = (now - stamp).total_seconds()
                fresh = fresh or (0 <= age <= 20 * 60)
            except (KeyError, TypeError, ValueError):
                continue
        if not fresh:
            return False
        state['pre_event_market'] = snap
        state['pre_event_market_captured_at_utc'] = now.isoformat()
        state['pre_event_market_event_date'] = event_date
        return True
    except Exception:
        return False


FOLLOWUP_LABELS = ('30분', '90분', '6시간', '24시간')
FOLLOWUP_SUFFIXES = ('market', 'brent', 'verdict', 'at_utc', 'news_class', 'message_id', 'delivery_status', 'event_date')


def clear_event_scoped_snapshots(state, new_date):
    """Keep only a genuinely captured pre-event baseline for this meeting."""
    for label in FOLLOWUP_LABELS:
        for suffix in FOLLOWUP_SUFFIXES:
            state.pop(f'followup_{label}_{suffix}', None)
    state['followups_sent'] = []
    if state.get('pre_event_market_event_date') != new_date:
        for field in ('pre_event_market', 'pre_event_market_captured_at_utc', 'pre_event_market_event_date'):
            state.pop(field, None)


def prune_stale_snapshots(state, upcoming_date=None):
    """Older meeting snapshots must never masquerade as this event's follow-ups."""
    labels = set(state.get('followups_sent') or [])
    detected = state.get('event_detected_at_utc')
    for label in FOLLOWUP_LABELS:
        stamp = state.get(f'followup_{label}_at_utc')
        stale_stamp = False
        if stamp and detected:
            try:
                stale_stamp = datetime.fromisoformat(stamp) < datetime.fromisoformat(detected)
            except (TypeError, ValueError):
                stale_stamp = True
        if label not in labels or stale_stamp:
            for suffix in FOLLOWUP_SUFFIXES:
                state.pop(f'followup_{label}_{suffix}', None)
    if state.get('pre_event_market_event_date') not in (state.get('event_statement_date'), upcoming_date):
        for field in ('pre_event_market', 'pre_event_market_captured_at_utc', 'pre_event_market_event_date'):
            state.pop(field, None)


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
        event_key = f"{stmt.get('date')}|decision"
        if state.get('delivery_pending_key') == event_key:
            raise RuntimeError('FOMC 결정 알림 전송 결과 불명확 — 재전송 보류')
        state['delivery_pending_key'] = event_key
        state['delivery_status'] = 'sending'
        base.save_state(state)
        receipt = base.send(msg)
        if not isinstance(receipt, int):
            raise RuntimeError('FOMC 결정 Telegram message_id 미확인 — 중복 방지 보류')
        clear_event_scoped_snapshots(state, stmt.get('date'))
        state['decision_sent_key'] = event_key
        state['decision_message_id'] = receipt
        state['decision_delivery_status'] = 'confirmed'
        state['delivery_pending_key'] = None
        state['delivery_status'] = 'confirmed'
        sent.append('decision')
        state['previous_statement'] = previous_statement
        state['previous_sep'] = previous_sep
        state['current_statement'] = stmt
        state['last_statement_url'] = stmt_url
        state['event_detected_at_utc'] = now.isoformat()
        state['event_statement_date'] = stmt.get('date')
        state['decision_market'] = cur_market
        event_date = stmt.get('date') or event_date
        if event_date:
            base.EVENT_DATE = event_date
            persistence.base.EVENT_DATE = event_date
        if sep and sep.get('date') == stmt.get('date'):
            state['current_sep'] = sep
            state['last_sep_url'] = sep_url
    else:
        # Silent repair of an existing event's omitted vote, never a new alert.
        existing = state.get('current_statement') or {}
        if stmt.get('against') and not existing.get('against'):
            for field in ('against', 'vote_for', 'vote_against'):
                existing[field] = stmt.get(field)
            state['current_statement'] = existing
        prune_stale_snapshots(state, event_date)

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
                # Without a same-meeting pre-event quote, no valid market delta exists.
                if (not state.get('pre_event_market')
                        or state.get('pre_event_market_event_date') != detected_date):
                    continue
                msg, cur_market, cls = base.followup_message(state, label)
                followup_key = f'{detected_date}|{label}'
                if state.get('delivery_pending_key') == followup_key:
                    raise RuntimeError('FOMC 후속 알림 전송 불명확 — 재전송 보류')
                state['delivery_pending_key'] = followup_key
                state['delivery_status'] = 'sending'
                base.save_state(state)
                receipt = base.send(msg)
                if not isinstance(receipt, int):
                    raise RuntimeError('FOMC 후속 Telegram message_id 미확인')
                sent.append(label)
                fset.add(label)
                state['followups_sent'] = sorted(fset)
                state[f'followup_{label}_message_id'] = receipt
                state[f'followup_{label}_delivery_status'] = 'confirmed'
                state[f'followup_{label}_event_date'] = detected_date
                state['delivery_pending_key'] = None
                state['delivery_status'] = 'confirmed'
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

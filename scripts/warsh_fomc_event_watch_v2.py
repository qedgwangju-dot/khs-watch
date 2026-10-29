#!/usr/bin/env python3
import email.utils
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import warsh_fomc_event_watch as base
import warsh_fomc_persistence_watch as persistence

_original_decision_message = base.decision_message
_original_followup_message = base.followup_message
_original_persistence_main = persistence.main
AUDIT_KEY = '2026-10-28|headline-and-sep-audit-v1'


def _decimal_row(label, text, count):
    # Ignore a standalone footnote number before decimal SEP forecasts.
    m = re.search(
        re.escape(label) + r'\s+(?:\d+\s+)?((?:\d+\.\d+\s+){' + str(count) + r',})',
        text, re.I,
    )
    return [float(x) for x in re.findall(r'\d+\.\d+', m.group(1))[:count]] if m else []


def parse_sep_v2(url):
    if not url:
        return None
    try:
        raw, final = base.fetch(url)
    except Exception:
        return None
    text = base.clean_text(raw)
    funds = base.first_numbers_after('Federal funds rate', text, 4)
    pce = base.first_numbers_after('PCE inflation', text, 4)
    core = _decimal_row('Core PCE inflation', text, 3)
    unemp = base.first_numbers_after('Unemployment rate', text, 4)
    if len(funds) < 4:
        return None
    return {
        'url': final, 'date': base.date_from_url(final),
        'funds_2026': funds[0], 'funds_2027': funds[1],
        'funds_2028': funds[2], 'funds_longer': funds[3],
        'pce_2026': pce[0] if pce else None,
        'core_pce_2026': core[0] if core else None,
        'unemployment_2026': unemp[0] if unemp else None,
    }


def _meeting_release(event_date):
    # Regular FOMC decisions use 14:00 New York time, including DST.
    day = datetime.strptime(event_date, '%Y-%m-%d')
    return day.replace(hour=14, tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)


def _current_sep(sep, event_date):
    return sep if sep and sep.get('date') == event_date else None


def _dissent_korean(text):
    names = {'Lisa D. Cook': '리사 쿡', 'Lisa Cook': '리사 쿡',
             'Beth M. Hammack': '베스 해맥', 'Beth Hammack': '베스 해맥'}
    match = re.search(r'Voting against (?:this|the monetary policy) action (?:was|were)\s+(.+?),\s*who preferred to\s+(raise|lower)\s+the target range for the federal funds rate by\s+1/4\s+percentage point', text or '', re.I)
    if not match:
        return text
    people = match.group(1)
    for english, korean in names.items():
        people = people.replace(english, korean)
    people = people.replace(' and ', '·')
    move = '인상' if match.group(2).lower() == 'raise' else '인하'
    return f'{people}은 이번 회의에서 정책금리 0.25%포인트 {move}을 요구하며 반대했습니다.'


def decision_message_v2(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls=None):
    stmt = dict(new_stmt)
    if stmt.get('against'):
        stmt['against'] = _dissent_korean(stmt['against'])
    current = _current_sep(sep_new, stmt.get('date'))
    msg = _original_decision_message(old_stmt, stmt, sep_old, current, pre, cur, news_cls)
    if new_stmt.get('date') != '2026-09-16':
        msg = re.sub(r'\n• JP모건 당일 S&P 500 시나리오 참고범위:[^\n]*', '', msg)
    if not current:
        note = ('이번 10월 회의는 정기 경제전망·점도표 발표 회의가 아닙니다.'
                if stmt.get('date') == '2026-10-28' else
                '현재 회의에 해당하는 새 점도표는 확인되지 않았으며 직전 회의 전망과 구분합니다.')
        msg = msg.replace('새 점도표 공식 페이지 확인 대기', note)
    # Scheduled execution can be late; never promise an immediate delivery.
    return msg.replace('[FOMC 즉시 판정]', '[FOMC 공식 결정 확인]')


def _dated_news_rows(raw, event_date, now):
    release = _meeting_release(event_date)
    end = min(now, release + timedelta(hours=24))
    if end < release:
        return []
    trusted = {'Reuters', 'The Wall Street Journal', 'WSJ', 'CNBC', 'Bloomberg', 'Financial Times'}
    out, seen = [], set()
    for item in ET.fromstring(raw).findall('.//item')[:40]:
        publisher = (item.findtext('source') or '').strip()
        title = (item.findtext('title') or '').strip()
        url = (item.findtext('link') or '').strip()
        try:
            published = email.utils.parsedate_to_datetime(item.findtext('pubDate') or '')
            if published.tzinfo is None or not release <= published <= end:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        if publisher not in trusted or not url.startswith('https://') or url in seen:
            continue
        # Preview language and an explicit different meeting date cannot support
        # a post-decision claim, even when Google republishes an old title.
        if re.search(r'expected to|may point|preview|what to expect|ahead of|will decide', title, re.I):
            continue
        explicit_dates = re.findall(r'20\d{2}-\d{2}-\d{2}', title)
        if any(d != event_date for d in explicit_dates):
            continue
        if not re.search(r'\b(?:Fed|FOMC|Warsh)\b', title, re.I):
            continue
        seen.add(url)
        out.append({'publisher': publisher, 'url': url,
                    'title': '회의 후 보도 링크·본문 추가 확인 필요',
                    'published_at_utc': published.astimezone(timezone.utc).isoformat()})
    return out[:5]


def trusted_headlines_current():
    now = datetime.now(timezone.utc)
    event_date = str(base.EVENT_DATE)
    try:
        if now < _meeting_release(event_date) or now > _meeting_release(event_date) + timedelta(hours=36):
            return [], None
        query = urllib.parse.quote(f'Kevin Warsh Fed FOMC "{event_date}" decision press conference')
        raw, _ = base.fetch(f'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en')
        rows = _dated_news_rows(raw, event_date, now)
    except Exception:
        return [], None
    # A title mentioning 'more hikes' can be a denial or an unanswered question.
    # Headlines are references only, never a policy-direction classification.
    return rows, None


def followup_message_v2(state, label):
    current = dict(state)
    date = current.get('event_statement_date')
    current['current_sep'] = _current_sep(current.get('current_sep'), date)
    message, snapshot, classification = _original_followup_message(current, label)
    try:
        elapsed = int((datetime.now(timezone.utc) - _meeting_release(date)).total_seconds() / 60)
        message = message.replace(f'재확인 · {label}]', f'재확인 · 목표 {label} / 실제 발표 후 {elapsed}분]')
    except (ValueError, TypeError):
        message = message.replace(f'재확인 · {label}]', f'재확인 · 목표 {label} / 실제 경과시간 미확인]')
    message = message.replace(
        '위 보조판정은 공식 기자회견 전문이 아니라 신뢰보도 헤드라인 기준이며, 공식 전문 확인 뒤 확정합니다.',
        '보도 제목만으로 추가 긴축·완화를 판정하지 않습니다. 발언 본문과 현재 회의 공식자료 확인이 필요합니다.')
    return message, snapshot, classification


def _audit_needed(state, now):
    return (state.get('event_statement_date') == '2026-10-28'
            and state.get('followup_90분_news_class') == '추가 긴축 시사'
            and '90분' in (state.get('followups_sent') or [])
            and state.get('audit_sent_key') != AUDIT_KEY
            and _meeting_release('2026-10-28') <= now <= _meeting_release('2026-10-28') + timedelta(days=7))


def persistence_with_audit():
    _original_persistence_main()
    state = base.load_state()
    if not _audit_needed(state, datetime.now(timezone.utc)):
        return
    if state.get('audit_pending_key') == AUDIT_KEY:
        raise RuntimeError('FOMC 정정 전송 결과 불명확 — 중복 재발송 보류')
    text = '\n'.join([
        '<b>[FOMC 알림 정정 | 10월 28일 회의]</b>',
        '• 앞선 90분 알림의 “헤드라인 기반 추가 긴축 시사” 판정을 철회합니다.',
        '• 기사 검색이 9월 회의에 고정됐고, 회의 전 전망·부정 표현을 충분히 구분하지 못했습니다.',
        '• 이는 금리인상·인하가 확정됐다는 뜻이 아닙니다. 이후 정책 방향은 이번 회의의 발언 본문과 공식자료로 다시 확인해야 합니다.',
        '• 10월 회의는 정기 점도표 발표 회의가 아니므로 “새 점도표 확인 대기” 안내도 바로잡습니다.',
        '• 기존 30분·90분 표시는 감지 시점 기준이었습니다. 이후에는 목표 구간과 실제 발표 후 경과시간을 구분합니다.',
        '• 발표 전 시장값을 확보하지 못한 경우 변화를 추정하거나 “변화 없음”으로 처리하지 않습니다.',
        '', base.link('연준 공식 회의·경제전망 일정', base.FED_CALENDAR),
    ])
    state.update({'audit_pending_key': AUDIT_KEY, 'audit_delivery_status': 'sending'})
    base.save_state(state)
    receipt = base.send(text)
    if type(receipt) is not int or receipt <= 0:
        raise RuntimeError('FOMC 정정 Telegram message_id 미확인')
    state.update({'audit_pending_key': None, 'audit_delivery_status': 'confirmed',
                  'audit_sent_key': AUDIT_KEY, 'audit_message_id': receipt,
                  'audit_sent_at_utc': datetime.now(timezone.utc).isoformat(),
                  'legacy_headline_classification_valid': False})
    base.save_state(state)
    print(json.dumps({'fomc_audit_correction_sent': True, 'message_id': receipt}, ensure_ascii=False))


def _self_test():
    now = datetime(2026, 10, 28, 20, tzinfo=timezone.utc)
    def feed(title, stamp):
        return '<rss><channel><item><title>'+html.escape(title)+'</title><link>https://example.test/article</link><source>Reuters</source><pubDate>'+stamp+'</pubDate></item></channel></rss>'
    assert _meeting_release('2026-10-28').hour == 18
    assert _meeting_release('2026-12-09').hour == 19
    assert not _dated_news_rows(feed('Warsh further hikes', 'Wed, 16 Sep 2026 19:00:00 GMT'), '2026-10-28', now)
    assert not _dated_news_rows(feed('Fed expected to hold rates', 'Wed, 28 Oct 2026 19:00:00 GMT'), '2026-10-28', now)
    assert not _dated_news_rows(feed('Warsh 2026-09-16 decision', 'Wed, 28 Oct 2026 19:00:00 GMT'), '2026-10-28', now)
    assert not _dated_news_rows(feed('Fed decision', 'Wed, 28 Oct 2026 21:00:00 GMT'), '2026-10-28', now)
    assert not _dated_news_rows(feed('Fed decision', 'invalid'), '2026-10-28', now)
    assert len(_dated_news_rows(feed('Warsh punts on more hikes', 'Wed, 28 Oct 2026 19:00:00 GMT'), '2026-10-28', now)) == 1
    assert _current_sep({'date':'2026-09-16'}, '2026-10-28') is None
    assert _current_sep({'date':'2026-10-28'}, '2026-10-28') is not None
    vote = 'Voting against the monetary policy action were Lisa D. Cook and Beth M. Hammack, who preferred to raise the target range for the federal funds rate by 1/4 percentage point at this meeting.'
    assert '리사 쿡·베스 해맥' in _dissent_korean(vote)
    state = {'event_statement_date':'2026-10-28', 'followup_90분_news_class':'추가 긴축 시사', 'followups_sent':['90분']}
    assert _audit_needed(state, now)
    state['audit_sent_key'] = AUDIT_KEY
    assert not _audit_needed(state, now)


_self_test()
base.parse_sep = parse_sep_v2
base.decision_message = decision_message_v2
base.trusted_headlines = trusted_headlines_current
base.followup_message = followup_message_v2
persistence.main = persistence_with_audit

if __name__ == '__main__':
    base.main()
    persistence.main()

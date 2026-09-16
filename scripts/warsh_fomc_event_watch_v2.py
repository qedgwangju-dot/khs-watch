#!/usr/bin/env python3
import re

import warsh_fomc_event_watch as base

_original_decision_message = base.decision_message


def _decimal_row(label, text, count):
    # SEP table rows can contain a standalone footnote number immediately after
    # the label (for example, "Core PCE inflation 4 3.3 2.5 2.1").
    # Require decimals for the actual forecast values so the footnote is skipped.
    m = re.search(
        re.escape(label) + r'\s+(?:\d+\s+)?((?:\d+\.\d+\s+){' + str(count) + r',})',
        text,
        re.I,
    )
    if not m:
        return []
    return [float(x) for x in re.findall(r'\d+\.\d+', m.group(1))[:count]]


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
        'url': final,
        'date': base.date_from_url(final),
        'funds_2026': funds[0],
        'funds_2027': funds[1],
        'funds_2028': funds[2],
        'funds_longer': funds[3],
        'pce_2026': pce[0] if pce else None,
        'core_pce_2026': core[0] if core else None,
        'unemployment_2026': unemp[0] if unemp else None,
    }


def decision_message_v2(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls=None):
    msg = _original_decision_message(old_stmt, new_stmt, sep_old, sep_new, pre, cur, news_cls)
    # The JPMorgan S&P reaction ranges supplied for this setup are specific to
    # the 2026-09-16 FOMC event. Do not carry those percentages into later meetings.
    if new_stmt.get('date') != base.EVENT_DATE:
        msg = re.sub(r'\n• JP모건 당일 S&P 500 시나리오 참고범위:[^\n]*', '', msg)
    return msg


base.parse_sep = parse_sep_v2
base.decision_message = decision_message_v2

if __name__ == '__main__':
    base.main()

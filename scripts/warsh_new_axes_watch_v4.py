#!/usr/bin/env python3
import re
from datetime import datetime, timezone

import warsh_new_axes_watch as base
import warsh_new_axes_watch_v3 as v3

SCHEDULE_URL = 'https://www.bls.gov/schedule/news_release/prod2.htm'
ARCHIVE_TEMPLATE = 'https://www.bls.gov/news.release/archives/prod2_{:%m%d%Y}.htm'


def latest_revised_archive():
    raw, _ = base.fetch(SCHEDULE_URL)
    text = base.clean_text(raw)
    rows = []
    pattern = re.compile(
        r'(First|Second|Third|Fourth)\s+Quarter\s+(20\d{2})\s+\(R\)\s+'
        r'([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s+(20\d{2})',
        re.I,
    )
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }
    today = datetime.now(timezone.utc).date()
    for m in pattern.finditer(text):
        mon = month_map.get(m.group(3).lower()[:3])
        if not mon:
            continue
        d = datetime(int(m.group(5)), mon, int(m.group(4))).date()
        if d <= today:
            rows.append(d)
    if not rows:
        raise RuntimeError('BLS revised productivity schedule not parsed')
    latest = max(rows)
    return ARCHIVE_TEMPLATE.format(latest)


if __name__ == '__main__':
    # The BLS current-release alias can lag behind the revised archive. Resolve
    # the latest completed (R) release from BLS's own schedule, then read that
    # dated official archive so the alert never mistakes a preliminary release
    # for the revised release.
    base.BLS_PROD_URL = latest_revised_archive()
    v3.main()

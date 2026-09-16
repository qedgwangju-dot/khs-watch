#!/usr/bin/env python3
import re

import warsh_new_axes_watch as base
import warsh_new_axes_watch_v3 as v3

# Use the official BLS current-release endpoint. The alert is still gated inside
# v3 so only a release explicitly identified as 'Revised' can be sent.
OFFICIAL_CURRENT = 'https://www.bls.gov/news.release/prod2.nr0.htm'


# v3's generic movement helper expects '(direction, value)'. One BLS sentence
# is written as '2.6-percent increase', i.e. '(value, direction)'. Make the
# helper accept both forms so a valid official release cannot fall through to
# the FRED continuity fallback merely because of word order.
def _movement_flexible(text, pattern):
    m = re.search(pattern, text, re.I | re.S)
    if not m:
        return None
    a, b = m.group(1), m.group(2)
    try:
        return v3._signed(a, b)
    except (TypeError, ValueError):
        try:
            value = float(a)
        except (TypeError, ValueError):
            return None
        direction = str(b).lower()
        return -value if direction.startswith('decreas') or direction.startswith('declin') or direction.startswith('fell') else value


if __name__ == '__main__':
    base.BLS_PROD_URL = OFFICIAL_CURRENT
    v3._movement = _movement_flexible
    v3.main()

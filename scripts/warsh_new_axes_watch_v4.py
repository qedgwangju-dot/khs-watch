#!/usr/bin/env python3
import re
import sys

import warsh_new_axes_watch as base
import warsh_new_axes_watch_v3 as v3

OFFICIAL_CURRENT = 'https://www.bls.gov/news.release/prod2.nr0.htm'


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


def _snapshot_with_diagnostic():
    try:
        return v3.official_bls_prod_snapshot()
    except Exception as e:
        print(f'BLS_PRODUCTIVITY_PARSE_FALLBACK: {type(e).__name__}: {e}', file=sys.stderr)
        return base.prod_snapshot()


if __name__ == '__main__':
    base.BLS_PROD_URL = OFFICIAL_CURRENT
    v3._movement = _movement_flexible
    v3.prod_snapshot_v3 = _snapshot_with_diagnostic
    v3.main()

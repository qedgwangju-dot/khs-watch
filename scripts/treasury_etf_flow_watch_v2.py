#!/usr/bin/env python3
import re
import requests
from bs4 import BeautifulSoup

import treasury_etf_flow_watch as base
import treasury_etf_flow_watch_readable as report

_original_get_ishares = base.get_ishares


def robust_get_ishares(ticker, meta):
    row = _original_get_ishares(ticker, meta)
    if row.get("nav_change_pct") is not None:
        return row

    response = requests.get(meta["url"], headers=base.HEADERS, timeout=35)
    response.raise_for_status()
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    # iShares renders an image/token between the dollar move and the percentage,
    # so allow a wide non-greedy span before the parenthesized percentage.
    pattern = (
        r"1 Day NAV Change as of [A-Za-z]{3} \d{1,2}, \d{4}"
        r".*?\(([-+]?\d+(?:\.\d+)?)%\)"
    )
    match = re.search(pattern, text)
    if match:
        row["nav_change_pct"] = float(match.group(1))
    return row


base.get_ishares = robust_get_ishares

if __name__ == "__main__":
    report.main()

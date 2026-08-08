from __future__ import annotations

import csv
import io
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import jobs_wage_watch_full_report as base
import jobs_wage_watch_full_report_v2 as v2
import jobs_wage_watch_full_report_v4 as v4
import jobs_wage_watch_full_report_v5 as v5


def _fred_direct(series_id: str) -> dict:
    end = datetime.now(v4.ET).date()
    start = end - timedelta(days=21)
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urllib.parse.urlencode(
        {"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()}
    )
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; khs-jobs-wage-watch/1.0)",
                "Accept": "text/csv,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            text = response.read().decode("utf-8", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        values = []
        for row in rows[1:]:
            if len(row) < 2 or row[1] in ("", "."):
                continue
            try:
                values.append((row[0], float(row[1])))
            except Exception:
                continue
        if not values:
            raise RuntimeError("FRED CSV contained no numeric observations")
        latest = values[-1]
        prev = values[-2] if len(values) >= 2 else None
        return {
            "value": latest[1],
            "date": latest[0],
            "change_bp": (latest[1] - prev[1]) * 100.0 if prev else None,
            "status": "직접 조회",
            "source": "FRED",
        }
    except Exception as e:
        return {
            "value": None,
            "date": None,
            "change_bp": None,
            "status": "확인 불가",
            "source": "FRED",
            "error": f"{type(e).__name__}: {e}",
        }


def _market_snapshot_v6(trigger_dt):
    # Fetch FRED first. A standalone GitHub runner test confirmed these five
    # bounded official series respond normally; doing them before the broader
    # Yahoo fan-out avoids connection/rate-limit interference.
    fred = {name: _fred_direct(series_id) for name, series_id in base.FRED_SERIES.items()}

    yahoo_assets = dict(base.YAHOO_ASSETS)
    yahoo_assets.update(v4.RATE_MARKET_ASSETS)
    yahoo = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {name: pool.submit(v2._yahoo_reaction_v2, symbol, trigger_dt) for name, symbol in yahoo_assets.items()}
        for name, future in futures.items():
            try:
                yahoo[name] = future.result(timeout=18)
            except Exception as e:
                yahoo[name] = {
                    "value": None,
                    "change_pct": None,
                    "source": "Yahoo Finance",
                    "status": "확인 불가",
                    "error": f"{type(e).__name__}: {e}",
                }

    market = {"yahoo": yahoo, "fred": fred}
    v4._LAST_MARKET = market
    return market


base._market_snapshot = _market_snapshot_v6


def build_report(new_releases):
    return v5.build_report(new_releases)

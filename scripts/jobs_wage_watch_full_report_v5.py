from __future__ import annotations

import csv
import io
import urllib.parse
from datetime import datetime, timedelta

import jobs_wage_watch_full_report as base
import jobs_wage_watch_full_report_v4 as v4


def _fred_latest_fast(series_id: str) -> dict:
    end = datetime.now(v4.ET).date()
    start = end - timedelta(days=21)
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urllib.parse.urlencode(
        {"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()}
    )
    try:
        text = base._fetch(url, timeout=7).decode("utf-8", errors="replace")
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


# Keep report latency bounded. If an ancillary FRED request fails, v4's final
# status explicitly downgrades to 부분완료 instead of delaying for minutes.
v4._fred_latest_robust = _fred_latest_fast


def build_report(new_releases):
    return v4.build_report(new_releases)

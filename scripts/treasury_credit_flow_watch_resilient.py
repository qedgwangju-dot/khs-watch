#!/usr/bin/env python3
import datetime as dt
import requests

import treasury_credit_flow_watch as app


def recent_fred_pair(series_id):
    start = (dt.date.today() - dt.timedelta(days=45)).isoformat()
    urls = [
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}",
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?cosd={start}&id={series_id}",
    ]
    last_error = None
    for url in urls:
        try:
            r = requests.get(url, headers=app.base.HEADERS, timeout=(8, 15))
            r.raise_for_status()
            rows = []
            for line in r.text.strip().splitlines()[1:]:
                parts = line.split(",")
                if len(parts) < 2 or parts[1] in ("", "."):
                    continue
                try:
                    rows.append({"date": parts[0], "value": float(parts[1])})
                except ValueError:
                    continue
            if rows:
                return rows[-1], rows[-2] if len(rows) >= 2 else None
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Recent-window FRED {series_id} failed: {last_error}")


app.get_fred_pair = recent_fred_pair

if __name__ == "__main__":
    app.main()

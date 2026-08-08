from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import jobs_wage_watch as watch
import jobs_wage_watch_full_report_v3 as full_report

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"
ET = ZoneInfo("America/New_York")

BLS_RELEASE_DATES = {
    "2025-11": "2025-12-16",
    "2025-12": "2026-01-09",
    "2026-01": "2026-02-11",
    "2026-02": "2026-03-06",
    "2026-03": "2026-04-03",
    "2026-04": "2026-05-08",
    "2026-05": "2026-06-05",
    "2026-06": "2026-07-02",
    "2026-07": "2026-08-07",
    "2026-08": "2026-09-04",
    "2026-09": "2026-10-02",
    "2026-10": "2026-11-06",
    "2026-11": "2026-12-04",
}

SERIES = {
    "nfp_level": "CES0000000001",
    "unemployment_rate": "LNS14000000",
    "participation_rate": "LNS11300000",
    "epop": "LNS12300000",
    "ahe": "CES0500000003",
    "workweek": "CES0500000002",
    "manufacturing_workweek": "CES3000000002",
    "manufacturing_overtime": "CES3000000004",
}


def _release_dt(period: str) -> datetime:
    release_date = BLS_RELEASE_DATES.get(period)
    if not release_date:
        raise RuntimeError(
            f"Official BLS release date not mapped for {period}; fail closed. "
            f"Verify {BLS_SCHEDULE_URL} before enabling this period."
        )
    return datetime.fromisoformat(release_date + "T08:30:00").replace(tzinfo=ET)


def _latest_scheduled_period(now: datetime) -> str | None:
    eligible = []
    for period in BLS_RELEASE_DATES:
        dt = _release_dt(period)
        if dt <= now:
            eligible.append((dt, period))
    if not eligible:
        return None
    eligible.sort()
    latest_dt, latest_period = eligible[-1]
    max_dt = max(_release_dt(p) for p in BLS_RELEASE_DATES)
    if now > max_dt + timedelta(days=40):
        raise RuntimeError(
            "BLS official release-date map is stale; fail closed until the official Employment Situation calendar is extended."
        )
    return latest_period


def _reported_key_for(period: str) -> str:
    return watch.make_key("employment_situation", period, _release_dt(period))


def _already_reported_release(period: str) -> watch.Release:
    release_dt = _release_dt(period)
    return watch.Release(
        kind="employment_situation",
        key=_reported_key_for(period),
        title=f"Employment Situation {period}",
        period=period,
        release_dt_et=release_dt,
        source_url=BLS_SCHEDULE_URL,
        metrics={},
        raw_summary="Official BLS release already reported; API call suppressed to preserve public API quota.",
    )


def _bls_api() -> dict:
    now = datetime.now(ET)
    payload = json.dumps(
        {
            "seriesid": list(SERIES.values()),
            "startyear": str(now.year - 1),
            "endyear": str(now.year),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        BLS_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; khs-jobs-wage-watch/1.0)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        obj = json.loads(response.read().decode("utf-8"))
    if obj.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API request failed: {obj.get('status')} {obj.get('message')}")
    return obj


def _monthly(series: dict) -> list[dict]:
    values = []
    for row in series.get("data") or []:
        period = str(row.get("period") or "")
        if not period.startswith("M") or period == "M13":
            continue
        try:
            month = int(period[1:])
            year = int(row["year"])
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        values.append(
            {
                "year": year,
                "month": month,
                "period": f"{year:04d}-{month:02d}",
                "value": value,
                "latest": str(row.get("latest") or "").lower() == "true",
            }
        )
    values.sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return values


def _value_for(rows: list[dict], period: str):
    for row in rows:
        if row["period"] == period:
            return row["value"]
    return None


def _previous_period(period: str) -> str:
    y, m = [int(x) for x in period.split("-")]
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def _year_ago(period: str) -> str:
    y, m = [int(x) for x in period.split("-")]
    return f"{y - 1:04d}-{m:02d}"


def parse_bls_api() -> watch.Release | None:
    now = datetime.now(ET)
    scheduled_period = _latest_scheduled_period(now)
    if scheduled_period is None:
        return None

    if os.getenv("FORCE_BLS_API") != "1":
        reported = set(watch.load_state().get("reported_successfully") or [])
        if _reported_key_for(scheduled_period) in reported:
            return _already_reported_release(scheduled_period)

    obj = _bls_api()
    raw_series = (obj.get("Results") or {}).get("series") or []
    by_id = {str(s.get("seriesID")): _monthly(s) for s in raw_series}

    core_ids = [SERIES["nfp_level"], SERIES["unemployment_rate"], SERIES["participation_rate"], SERIES["epop"]]
    if any(not by_id.get(sid) for sid in core_ids):
        raise RuntimeError("BLS API core series incomplete")

    latest_periods = [by_id[sid][0]["period"] for sid in core_ids]
    if len(set(latest_periods)) != 1:
        raise RuntimeError(f"BLS API core series period mismatch: {latest_periods}")
    period = latest_periods[0]

    if period not in BLS_RELEASE_DATES:
        raise RuntimeError(
            f"Official BLS release date not mapped for API period {period}; fail closed. "
            f"Verify {BLS_SCHEDULE_URL} before enabling this period."
        )
    release_dt = _release_dt(period)
    if now < release_dt:
        return None

    nfp_rows = by_id[SERIES["nfp_level"]]
    latest_level = _value_for(nfp_rows, period)
    previous_level = _value_for(nfp_rows, _previous_period(period))
    if latest_level is None or previous_level is None:
        raise RuntimeError("BLS API NFP level/current-prior pair incomplete")
    nfp = int(round((latest_level - previous_level) * 1000))

    ahe_rows = by_id.get(SERIES["ahe"], [])
    ahe_now = _value_for(ahe_rows, period)
    ahe_year_ago = _value_for(ahe_rows, _year_ago(period))
    ahe_yoy = None
    if ahe_now is not None and ahe_year_ago not in (None, 0):
        ahe_yoy = round((ahe_now / ahe_year_ago - 1.0) * 100.0, 1)

    def value(name: str):
        return _value_for(by_id.get(SERIES[name], []), period)

    metrics = {
        "nfp": nfp,
        "unemployment_rate": value("unemployment_rate"),
        "participation_rate": value("participation_rate"),
        "epop": value("epop"),
        "ahe_yoy": ahe_yoy,
        "workweek": value("workweek"),
        "manufacturing_workweek": value("manufacturing_workweek"),
        "manufacturing_overtime": value("manufacturing_overtime"),
        "revisions_text": None,
        "retrieval_route": "official BLS Public Data API fallback",
        "schedule_source": BLS_SCHEDULE_URL,
    }

    required = [
        metrics["nfp"], metrics["unemployment_rate"], metrics["participation_rate"],
        metrics["epop"], metrics["ahe_yoy"], metrics["workweek"],
        metrics["manufacturing_workweek"], metrics["manufacturing_overtime"],
    ]
    if any(v is None for v in required):
        raise RuntimeError(f"BLS API required fields incomplete for {period}: {metrics}")

    key = watch.make_key("employment_situation", period, release_dt)
    return watch.Release(
        kind="employment_situation",
        key=key,
        title=f"Employment Situation {period}",
        period=period,
        release_dt_et=release_dt,
        source_url=BLS_API_URL,
        metrics=metrics,
        raw_summary="Official BLS Public Data API fallback; release date comes from the official Employment Situation calendar.",
    )


_original_claims = watch.parse_claims
_original_adp = watch.parse_adp
_cache: dict[str, watch.Release | None] = {}


def _cached(name: str, parser):
    def inner():
        if name not in _cache:
            _cache[name] = parser()
        return _cache[name]
    inner.__name__ = f"parse_{name}"
    return inner


watch.parse_bls = _cached("bls", parse_bls_api)
watch.parse_claims = _cached("claims", _original_claims)
watch.parse_adp = _cached("adp", _original_adp)
watch.build_report = full_report.build_report

if __name__ == "__main__":
    raise SystemExit(watch.main())

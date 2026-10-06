#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

KST = ZoneInfo("Asia/Seoul")


@lru_cache(maxsize=1)
def _calendar():
    return xcals.get_calendar("XKRX")


def session_bounds(day: dt.date | None = None) -> tuple[dt.datetime, dt.datetime] | None:
    day = day or dt.datetime.now(KST).date()
    ts = pd.Timestamp(day.isoformat())
    cal = _calendar()
    if not cal.is_session(ts):
        return None
    row = cal.schedule.loc[ts]
    open_dt = row["open"].tz_convert(KST).to_pydatetime()
    close_dt = row["close"].tz_convert(KST).to_pydatetime()
    return open_dt, close_dt


def is_session_day(day: dt.date | None = None) -> bool:
    return session_bounds(day) is not None


def session_state(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    else:
        now = now.astimezone(KST)
    bounds = session_bounds(now.date())
    if bounds is None:
        return {
            "is_session": False,
            "date": now.date().isoformat(),
            "open": None,
            "continuous_end": None,
            "close": None,
        }
    open_dt, close_dt = bounds
    continuous_end = close_dt - dt.timedelta(minutes=10)
    return {
        "is_session": True,
        "date": now.date().isoformat(),
        "open": open_dt,
        "continuous_end": continuous_end,
        "close": close_dt,
    }


if __name__ == "__main__":
    state = session_state()
    print({
        "is_session": state["is_session"],
        "date": state["date"],
        "open": state["open"].isoformat() if state["open"] else None,
        "continuous_end": state["continuous_end"].isoformat() if state["continuous_end"] else None,
        "close": state["close"].isoformat() if state["close"] else None,
    })

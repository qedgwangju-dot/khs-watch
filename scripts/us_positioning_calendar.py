"""Exchange-session helpers for the US positioning watcher."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")
POST_CLOSE_DELAY = timedelta(minutes=30)


def latest_completed_us_session(now: datetime | None = None) -> date:
    """Return the latest XNYS session with at least 30 minutes of post-close time.

    Weekday-only logic mistakes market holidays for trading sessions. XNYS is
    already an installed dependency in the watcher; use its published session
    calendar and fail closed if the requested date is outside its calendar.
    """
    now = now or datetime.now(NEW_YORK)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(NEW_YORK)
    calendar = xcals.get_calendar("XNYS")
    today = pd.Timestamp(now.date())

    if calendar.is_session(today):
        close = calendar.session_close(today).to_pydatetime().astimezone(NEW_YORK)
        if now >= close + POST_CLOSE_DELAY:
            return now.date()
        lookup_day = today - pd.Timedelta(days=1)
    else:
        lookup_day = today

    return calendar.date_to_session(lookup_day, direction="previous").date()


def completed_us_session_candidates(expected: date, limit: int = 7) -> list[date]:
    """Return descending actual XNYS sessions, skipping weekends and holidays."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if limit == 0:
        return []

    calendar = xcals.get_calendar("XNYS")
    session = calendar.date_to_session(pd.Timestamp(expected), direction="previous")
    candidates: list[date] = []
    while len(candidates) < limit:
        candidates.append(session.date())
        session = calendar.date_to_session(
            session - pd.Timedelta(days=1), direction="previous"
        )
    return candidates

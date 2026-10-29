"""Offline checks for pre-open and intraday index backfill."""
import datetime as dt
import unittest
from collections import deque
from unittest.mock import patch

import kospi_shock_episode_watch as watch


REAL_DATETIME = dt.datetime


class FixedDatetime(REAL_DATETIME):
    current = REAL_DATETIME(2026, 10, 29, 8, 58, 33, tzinfo=watch.KST)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


class BackfillClockTests(unittest.TestCase):
    def setUp(self):
        FixedDatetime.current = REAL_DATETIME(2026, 10, 29, 8, 58, 33, tzinfo=watch.KST)
        self.open = REAL_DATETIME(2026, 10, 29, 9, 0, tzinfo=watch.KST)

    def read_bars(self, upcode, data):
        with patch.object(watch.dt, "datetime", FixedDatetime), \
             patch.object(watch, "session_state", return_value={"open": self.open}), \
             patch.object(watch, "ls_post", return_value={"t8409OutBlock1": data}):
            return watch.backfill_index_bars("offline", upcode=upcode)

    def test_future_preopen_bar_cannot_create_opening_shock(self):
        # Time/value shape follows the observed 09:01 incident; the original t8409
        # response was not retained, so this is a synthetic fixture.
        row = {"date": "20261029", "time": "090100", "close": "771.28"}
        for upcode in ("001", "301"):
            with self.subTest(upcode=upcode):
                self.assertEqual([], self.read_bars(upcode, [row]))
        series = self.read_bars("301", [row])
        series.append((REAL_DATETIME(2026, 10, 29, 9, 1, 0, 500000, tzinfo=watch.KST).timestamp(), 767.13))
        watcher = watch.Watch.__new__(watch.Watch)
        watcher.kosdaq_idx = deque(series)
        watcher.kosdaq_last_episode_end_ts = None
        self.assertFalse(watcher._kosdaq_trigger()[0])

    def test_past_completed_bar_retained_and_future_bar_rejected(self):
        FixedDatetime.current = REAL_DATETIME(2026, 10, 29, 9, 2, 30, tzinfo=watch.KST)
        bars = [
            {"date": "20261029", "time": "090000", "close": "771.28"},
            {"date": "20261029", "time": "090100", "close": "767.78"},
            {"date": "20261029", "time": "090300", "close": "766.10"},
            {"date": "20261028", "time": "090100", "close": "770.00"},
        ]
        for upcode in ("001", "301"):
            with self.subTest(upcode=upcode):
                result = self.read_bars(upcode, bars)
                self.assertEqual([(REAL_DATETIME(2026, 10, 29, 9, 1, tzinfo=watch.KST).timestamp(), 767.78)], result)


if __name__ == "__main__":
    unittest.main()

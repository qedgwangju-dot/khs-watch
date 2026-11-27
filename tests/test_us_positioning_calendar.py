import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from us_positioning_calendar import (
    completed_us_session_candidates,
    latest_completed_us_session,
)

NY = ZoneInfo("America/New_York")


class CompletedUSSessionTests(unittest.TestCase):
    def test_thanksgiving_is_not_misclassified_as_a_weekday_session(self):
        now = datetime(2026, 11, 26, 21, 0, tzinfo=NY)
        self.assertEqual(latest_completed_us_session(now), date(2026, 11, 25))

    def test_regular_close_requires_post_close_grace(self):
        before = datetime(2026, 11, 25, 16, 29, tzinfo=NY)
        after = datetime(2026, 11, 25, 16, 30, tzinfo=NY)
        self.assertEqual(latest_completed_us_session(before), date(2026, 11, 24))
        self.assertEqual(latest_completed_us_session(after), date(2026, 11, 25))

    def test_early_close_uses_actual_exchange_close(self):
        before = datetime(2026, 11, 27, 13, 29, tzinfo=NY)
        after = datetime(2026, 11, 27, 13, 30, tzinfo=NY)
        self.assertEqual(latest_completed_us_session(before), date(2026, 11, 25))
        self.assertEqual(latest_completed_us_session(after), date(2026, 11, 27))

    def test_candidates_skip_weekends_and_holidays(self):
        self.assertEqual(
            completed_us_session_candidates(date(2026, 11, 25), limit=5),
            [
                date(2026, 11, 25),
                date(2026, 11, 24),
                date(2026, 11, 23),
                date(2026, 11, 20),
                date(2026, 11, 19),
            ],
        )

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            latest_completed_us_session(datetime(2026, 11, 26, 21, 0))


if __name__ == "__main__":
    unittest.main()

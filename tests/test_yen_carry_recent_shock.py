import datetime as dt
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from yen_carry_recent_shock import (
    calculate,
    detect_history_event,
    fetch_complete_snapshot,
    monitor_gap_minutes,
)

KST = ZoneInfo("Asia/Seoul")


class RecentShockTests(unittest.TestCase):
    def points(self, prices, step=300.0):
        start = 1_800_000_000.0 - (len(prices) - 1) * step
        return [(start + i * step, float(px)) for i, px in enumerate(prices)]

    def test_partial_five_minute_reference_retries_using_real_points(self):
        complete = self.points([100.0] * 30)
        target = complete[-1][0] - 30 * 60
        partial = [row for row in complete if abs(row[0] - target) > 600]
        from yen_carry_recent_shock import calculate
        with self.assertRaisesRegex(RuntimeError, "30-minute reference unavailable"):
            calculate(partial)
        with mock.patch("yen_carry_recent_shock.composite.fetch_fx_points", side_effect=[partial, complete]) as fetch:
            points, result = fetch_complete_snapshot(attempts=2, retry_pause_seconds=0)
        self.assertEqual(points, complete)
        self.assertEqual(result.change_30m_pct, 0)
        self.assertEqual(fetch.call_count, 2)

    def test_persistently_missing_reference_must_fail_not_fabricate_price(self):
        complete = self.points([100.0] * 30)
        target = complete[-1][0] - 30 * 60
        partial = [row for row in complete if abs(row[0] - target) > 600]
        with mock.patch("yen_carry_recent_shock.composite.fetch_fx_points", return_value=partial) as fetch:
            with self.assertRaisesRegex(RuntimeError, "30-minute reference unavailable"):
                fetch_complete_snapshot(attempts=2, retry_pause_seconds=0)
        self.assertEqual(fetch.call_count, 2)

    def test_current_shock_when_fast_drop_is_still_running(self):
        prices = [100.4] * 15 + [100.2, 100.0, 99.6, 99.2]
        snap = calculate(self.points(prices))
        self.assertTrue(snap.current_shock)
        self.assertFalse(snap.recent_shock)
        self.assertTrue(snap.history_shock)

    def test_recent_shock_survives_beyond_old_90_minute_window(self):
        # Shock 100 -> 98.8 (-1.2%), then residual 99.2 remains for >90 minutes.
        prices = [100.0, 98.8, 99.0] + [99.2] * 40
        snap = calculate(self.points(prices))
        self.assertFalse(snap.current_shock)
        self.assertTrue(snap.recent_shock)
        self.assertTrue(snap.history_shock)
        self.assertLessEqual(snap.history_max_drawdown_pct, -1.0)
        self.assertLessEqual(snap.history_current_vs_peak_pct, -0.5)

    def test_fully_recovered_shock_is_still_detectable_as_history_event(self):
        # The current price fully recovers, but the missed -1% shock must remain recoverable.
        prices = [100.0, 98.8, 99.0] + [100.0] * 40
        points = self.points(prices)
        snap = calculate(points)
        self.assertFalse(snap.current_shock)
        self.assertFalse(snap.recent_shock)
        self.assertTrue(snap.history_shock)
        event = detect_history_event({}, snap, points)
        self.assertIsNotNone(event)
        self.assertIn("-1%급 급락", event.reason)

    def test_old_shock_outside_six_hours_is_ignored(self):
        prices = [100.0, 98.7] + [100.0] * 80
        snap = calculate(self.points(prices))
        self.assertFalse(snap.current_shock)
        self.assertFalse(snap.recent_shock)
        self.assertFalse(snap.history_shock)

    def test_same_history_event_is_not_repeated(self):
        prices = [100.0, 98.8, 99.0] + [100.0] * 40
        points = self.points(prices)
        snap = calculate(points)
        previous = {
            "initialized": True,
            "last_history_alert_trough_epoch": snap.history_trough_epoch,
            "last_history_alert_trough_price": snap.history_trough_price,
        }
        self.assertIsNone(detect_history_event(previous, snap, points))

    def test_monitor_gap_over_twenty_minutes_is_measured(self):
        now = dt.datetime(2026, 9, 10, 10, 25, tzinfo=KST)
        previous = {
            "initialized": True,
            "updated_at_kst": "2026-09-10T10:00:00+09:00",
        }
        self.assertEqual(monitor_gap_minutes(previous, now), 25.0)


if __name__ == "__main__":
    unittest.main()

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

    def test_recent_shock_telegram_receipt_checks_actual_chat_and_message_id(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/yen-carry-recent-shock.yml").read_text(encoding="utf-8")
        self.assertIn("Recent-shock Telegram receipt missing message_id", workflow)
        self.assertIn("Recent-shock Telegram receipt chat mismatch", workflow)
        self.assertIn("'chat_id_verified': True", workflow)

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
        with mock.patch("yen_carry_recent_shock.composite.fetch_fx_points", return_value=partial) as fetch, \
             mock.patch("yen_carry_recent_shock.fetch_one_day_5m_snapshot", side_effect=RuntimeError("fallback unavailable")):
            with self.assertRaisesRegex(RuntimeError, "30-minute reference unavailable"):
                fetch_complete_snapshot(attempts=2, retry_pause_seconds=0)
        self.assertEqual(fetch.call_count, 2)

    def test_one_day_real_observation_fallback_restores_complete_window(self):
        full = self.points([100.0] * 35)
        target = full[-1][0] - 15 * 60
        incomplete = [row for row in full if abs(row[0] - target) > 600]
        from yen_carry_recent_shock import calculate
        with mock.patch("yen_carry_recent_shock.composite.fetch_fx_points", return_value=incomplete) as primary, \
             mock.patch("yen_carry_recent_shock.fetch_one_day_5m_snapshot", return_value=(full, calculate(full))) as alternate:
            points, snapshot = fetch_complete_snapshot(attempts=2, retry_pause_seconds=0)
        self.assertEqual(points, full)
        self.assertEqual(snapshot.change_15m_pct, 0)
        self.assertEqual(primary.call_count, 2)
        self.assertEqual(alternate.call_count, 1)

    def test_failed_market_source_records_attempt_without_advancing_shock_state(self):
        import json
        import pathlib
        import tempfile
        from yen_carry_recent_shock import main
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp)
            health = target / "yen_carry_recent_shock_market_check.json"
            status = target / "status.md"
            pending = target / "pending.json"
            with mock.patch("yen_carry_recent_shock.OUT", target), \
                 mock.patch("yen_carry_recent_shock.PENDING_PATH", pending), \
                 mock.patch("yen_carry_recent_shock.STATUS_PATH", status), \
                 mock.patch("yen_carry_recent_shock.fetch_complete_snapshot", side_effect=RuntimeError("15-minute reference unavailable")), \
                 mock.patch("sys.argv", ["yen_carry_recent_shock.py"]):
                self.assertEqual(main(), 1)
            self.assertTrue(health.exists())
            data = json.loads(health.read_text(encoding="utf-8"))
            self.assertFalse(data["fx_signal_eligible"])
            self.assertIsNone(data["fx_observed_at_kst"])
            self.assertEqual(data["issue_kind"], "market_data_unavailable")
            self.assertFalse(pending.exists())

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

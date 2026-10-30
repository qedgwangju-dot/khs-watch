from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import yen_carry_watchdog_quality as quality

KST = ZoneInfo("Asia/Seoul")


def status(now, *, last_minutes=1, observed_minutes=1, eligible=True, name="heartbeat"):
    return (
        name,
        {
            "updated_at_kst": (now - dt.timedelta(minutes=last_minutes)).isoformat(timespec="seconds"),
            "fx_observed_at_kst": (now - dt.timedelta(minutes=observed_minutes)).isoformat(timespec="seconds"),
            "fx_signal_eligible": eligible,
        },
    )


class YenCarryWatchdogQualityTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 30, 15, 9, tzinfo=KST)

    def test_fresh_eligible_quote_clears_prior_incident(self):
        row = quality.evaluate([status(self.now)], self.now)
        self.assertTrue(row["healthy"])
        self.assertTrue(row["fx_signal_eligible"])
        tr = quality.transition({"alert_active": True}, row)
        self.assertTrue(tr["recovered_incident"])
        self.assertFalse(tr["outage"])

    def test_181_minute_schedule_gap_triggers_single_outage(self):
        row = quality.evaluate([status(self.now, last_minutes=181, observed_minutes=181)], self.now)
        tr = quality.transition({"alert_active": False}, row)
        self.assertTrue(tr["new_outage"])
        self.assertFalse(tr["recovered_incident"])
        self.assertEqual(row["issue_kind"], "execution_stale")

    def test_new_bad_data_heartbeat_does_not_clear_incident(self):
        row = quality.evaluate([status(self.now, last_minutes=1, observed_minutes=181, eligible=False)], self.now)
        self.assertFalse(row["healthy"])
        self.assertEqual(row["issue_kind"], "market_data_unavailable")
        tr = quality.transition({"alert_active": True}, row)
        self.assertFalse(tr["recovered_incident"])
        self.assertTrue(tr["outage"])

    def test_recent_recovery_wins_over_stale_primary(self):
        rows = [
            status(self.now, last_minutes=181, observed_minutes=181, name="primary"),
            status(self.now, last_minutes=1, observed_minutes=1, name="recent"),
        ]
        result = quality.evaluate(rows, self.now)
        self.assertEqual(result["source_path"], "recent")
        self.assertTrue(result["healthy"])

    def test_weekend_price_is_not_falsely_required(self):
        saturday = dt.datetime(2026, 10, 31, 16, 0, tzinfo=KST)
        row = quality.evaluate([status(saturday, last_minutes=1, observed_minutes=180, eligible=False)], saturday)
        self.assertFalse(row["market_open"])
        self.assertTrue(row["healthy"])
        self.assertEqual(row["issue_kind"], "market_closed")

    def test_weekend_execution_gap_is_still_an_outage(self):
        saturday = dt.datetime(2026, 10, 31, 16, 0, tzinfo=KST)
        row = quality.evaluate([status(saturday, last_minutes=181, observed_minutes=180, eligible=False)], saturday)
        self.assertFalse(row["healthy"])
        self.assertEqual(row["issue_kind"], "execution_stale")
        self.assertTrue(quality.transition({"alert_active": False}, row)["new_outage"])

    def test_future_payload_is_not_a_valid_market_heartbeat(self):
        row = quality.evaluate([status(self.now, last_minutes=-10, observed_minutes=-10)], self.now)
        self.assertIsNone(row["stale_minutes"])
        self.assertFalse(row["healthy"])

    def test_invalid_json_payload_is_not_a_success(self):
        row = quality.evaluate([("heartbeat", {}), ("recent", {"updated_at_kst": "invalid"})], self.now)
        self.assertEqual(row["issue_kind"], "heartbeat_missing")
        self.assertFalse(row["healthy"])


if __name__ == "__main__":
    unittest.main()

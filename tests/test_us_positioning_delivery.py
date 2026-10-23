import unittest
from datetime import date
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from us_positioning_delivery import daily_digest_due, daily_event_label


class DailyDigestDeliveryTests(unittest.TestCase):
    def test_daily_digest_is_due_when_no_delivery_was_recorded(self):
        self.assertTrue(daily_digest_due({}, date(2026, 10, 24)))

    def test_retry_does_not_send_twice_on_the_same_korea_date(self):
        state = {"daily_digest_sent_date_kst": "2026-10-24"}
        self.assertFalse(daily_digest_due(state, date(2026, 10, 24)))
        self.assertTrue(daily_digest_due(state, date(2026, 10, 25)))

    def test_unchanged_daily_digest_is_not_mislabeled_as_new(self):
        self.assertEqual(daily_event_label([]), "일일 정기 현황")

    def test_daily_digest_labels_new_changes_and_corrections(self):
        self.assertEqual(
            daily_event_label([{"source": "SOX"}]),
            "일일 정기 현황 · 신규 변화",
        )
        self.assertEqual(
            daily_event_label([{"source": "SOX"}], correction=True),
            "일일 정기 현황 · 정정·보강",
        )


if __name__ == "__main__":
    unittest.main()

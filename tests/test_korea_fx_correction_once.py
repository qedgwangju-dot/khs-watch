"""2026-10-16 환율 경보 오탐 정정의 일회성·숫자 회귀 시험."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo

import korea_fx_20261016_correction as correction


class TestCorrectionOnce(unittest.TestCase):
    def test_wrong_and_correct_basis(self):
        self.assertEqual(correction.corrected_change(1336.4, 1350.0), (-13.6, -1.01))
        self.assertEqual(correction.corrected_change(1336.4, 1344.6), (-8.2, -0.61))
        self.assertEqual(correction.corrected_change(1331.4, 1344.6), (-13.2, -0.98))

    def test_one_time_event_not_replayed(self):
        now = dt.datetime(2026, 10, 16, 20, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        prior = {"seen_event_keys": [correction.BAD_EVENT]}
        self.assertTrue(correction.eligible({"seen_event_keys": []}, prior, now))
        self.assertFalse(correction.eligible(
            {"seen_event_keys": [correction.CORRECTION_EVENT]}, prior, now
        ))
        self.assertFalse(correction.eligible(
            {"seen_event_keys": []}, prior,
            dt.datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        ))

    def test_message_marks_old_alert_invalid(self):
        msg = correction.message()
        self.assertIn("이전 −1.01% 경보는 무효", msg)
        self.assertIn("1,344.6원", msg)
        self.assertIn("1,331.4원", msg)
        self.assertIn("−1.01%", msg)
        self.assertNotIn("통화스왑 체결", msg)


if __name__ == "__main__":
    unittest.main()

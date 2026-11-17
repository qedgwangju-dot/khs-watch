import datetime as dt
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import warsh_rba_minutes_context as rba


class RBAMinutesTests(unittest.TestCase):
    text = (
        "<h1>Minutes of the Monetary Policy Board Meeting</h1>"
        "<p>Sydney – 2 and 3 November 2026</p>"
        "<p>Data centre developers had raised debt equivalent to at least one-fifth "
        "of the increase in business debt this year.</p>"
        "<p>The &frac12;&nbsp;percentage point rise in the unemployment rate over the "
        "preceding six months suggested slowing demand.</p>"
        "<p>Most members determined that a higher neutral interest rate was possible. "
        "They discussed the risk of allowing inflation expectations to rise.</p>"
        "<p>A minority of members determined that the 100&nbsp;basis points of tightening "
        "could cause a sharper downturn and higher unemployment.</p>"
        "<p>The Board decided to raise the cash rate target to 4.85&nbsp;per&nbsp;cent. "
        "Six members voted in favour; three members voted to leave the cash rate "
        "target unchanged at 4.60 per cent.</p>"
    )

    def test_release_is_distinct_from_decision_and_labels_both_dates(self):
        fetch = Mock(return_value=self.text)
        message = rba.rba_minutes_message(fetch)
        fetch.assert_called_once_with(rba.RBA_MINUTES_URL)
        self.assertEqual(rba.RBA_KEY, "rba:minutes:20261117:20261103")
        self.assertEqual(rba.RBA_RELEASED_AT, dt.datetime.fromisoformat("2026-11-17T09:30:00+09:00"))
        for expected in ("11월 2~3일", "11월 17일 오전 9시 30분", "4.60%", "4.85%", "1.00%포인트",
                         "최근 6개월간 실업률이 0.5%포인트", "같은 기간 호주 기업부채 전체 증가분의 최소 5분의 1"):
            self.assertIn(expected, message)
        self.assertIn(rba.RBA_MINUTES_URL, message)

    def test_incomplete_or_changed_source_is_retryable(self):
        for original, replacement in (
            ("Minutes of the Monetary Policy Board Meeting", "Rate decision"),
            ("3 November 2026", "3 November 2025"),
            ("Six members", "Five members"),
            ("4.60 per cent", "4.50 per cent"),
            ("Most members determined", "No members determined"),
            ("neutral interest rate", "interest rate"),
            ("expectations to rise", "expectations to fall"),
            ("100&nbsp;basis points", "75&nbsp;basis points"),
            ("sharper downturn", "faster expansion"),
        ):
            with self.subTest(original=original), self.assertRaises(RuntimeError):
                rba.rba_minutes_message(Mock(return_value=self.text.replace(original, replacement)))

    def test_minority_position_cannot_be_inferred_from_a_majority_remark(self):
        text = self.text.replace("sharper downturn", "slower recovery").replace(
            "Most members determined", "Most members determined there might be a sharper downturn and"
        )
        with self.assertRaisesRegex(RuntimeError, "reasons"):
            rba.rba_minutes_message(Mock(return_value=text))

    def test_debt_denominator_and_unemployment_change_must_match(self):
        for original, replacement in (
            ("one-fifth", "one-tenth"),
            ("at least", "at most"),
            ("the increase in business debt", "total business debt"),
            ("this year", "last year"),
            ("Data centre developers", "Housing developers"),
            ("&frac12;", "0.25"),
            ("point rise", "point fall"),
            ("preceding six months", "preceding year"),
        ):
            with self.subTest(original=original), self.assertRaisesRegex(RuntimeError, "business debt growth"):
                rba.rba_minutes_message(Mock(return_value=self.text.replace(original, replacement)))

    def test_transport_failure_is_propagated(self):
        with self.assertRaises(TimeoutError):
            rba.rba_minutes_message(Mock(side_effect=TimeoutError("timeout")))


if __name__ == "__main__":
    unittest.main()

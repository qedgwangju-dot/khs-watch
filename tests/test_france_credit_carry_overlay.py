import datetime as dt
import unittest

from scripts import france_credit_carry_overlay as watch

EXAMPLE_EN = """
<table><thead><tr><th>Agency</th><th>Rating</th><th>Outlook</th><th>Last rating</th><th>Next date</th></tr></thead>
<tbody>
<tr><td><a href="#">Fitch</a></td><td>A+</td><td>Stable</td><td>28 August 2026</td><td>-</td></tr>
<tr><td><a href="#">Moody's</a></td><td>Aa3</td><td>Negative</td><td>10 April 2026</td><td>23 October 2026</td></tr>
<tr><td>Standard &amp; Poor's</td><td>A+</td><td>Stable</td><td>29 May 2026</td><td>27 November 2026</td></tr>
</tbody></table>
"""
EXAMPLE_FR = """
<table><tr><td>Moody's</td><td>Aa3</td><td>Négative</td><td>10 avril 2026</td><td>23 octobre 2026</td></tr></table>
"""


class FranceCreditCarryOverlayTests(unittest.TestCase):
    def test_english_rating_table_parsed(self):
        r = watch.parse_moodys(EXAMPLE_EN)
        self.assertEqual(r["rating"], "Aa3")
        self.assertEqual(r["outlook"], "Negative")
        self.assertEqual(r["decision_date"], "2026-04-10")
        self.assertEqual(r["next_review"], "2026-10-23")

    def test_french_rating_table_parsed(self):
        r = watch.parse_moodys(EXAMPLE_FR)
        self.assertEqual(r["outlook"], "Négative")
        self.assertEqual(r["next_review"], "2026-10-23")

    def test_bad_table_fails_closed(self):
        with self.assertRaises(ValueError):
            watch.parse_moodys("<div>Moody's Aa3 Negative 23 October 2026</div>")
        with self.assertRaises(ValueError):
            watch.parse_moodys("<table><tr><td>Moody's</td><td>unknown</td><td>Stable</td><td>1 April 2026</td><td>23 October 2026</td></tr></table>")

    def test_milestones_are_not_downgrade_forecasts(self):
        rating = watch.parse_moodys(EXAMPLE_EN)
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 14), {}, rating), [])
        milestone = watch.credit_events(dt.date(2026, 10, 16), {}, rating)
        self.assertEqual(milestone[0]["key"], "milestone:2026-10-23:D-7")
        self.assertEqual(milestone[0]["kind"], "milestone")
        old = {"sent_keys": [milestone[0]["key"]]}
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 16), old, rating), [])
        one_day = watch.credit_events(dt.date(2026, 10, 22), old, rating)
        self.assertEqual(one_day[0]["key"], "milestone:2026-10-23:D-1")

    def test_official_rating_downgrade_requires_changed_official_row(self):
        old = {"last_official": watch.parse_moodys(EXAMPLE_EN)}
        newest = {**old["last_official"], "rating": "A1", "decision_date": "2026-10-23", "next_review": None}
        events = watch.credit_events(dt.date(2026, 10, 24), old, newest)
        self.assertEqual(events, [{"kind": "decision", "key": "decision:2026-10-23:A1:Negative"}])
        old["sent_keys"] = [events[0]["key"]]
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 24), old, newest), [])

    def test_rating_unchanged_but_review_done_generates_one_verified_result(self):
        old = {"last_official": watch.parse_moodys(EXAMPLE_EN)}
        new = {**old["last_official"], "decision_date": "2026-10-23", "next_review": None}
        event = watch.credit_events(dt.date(2026, 10, 24), old, new)
        self.assertEqual(len(event), 1)
        self.assertEqual(event[0]["kind"], "decision")

    def test_rescheduled_review_does_not_send_false_october_milestones(self):
        rating = {**watch.parse_moodys(EXAMPLE_EN), "next_review": "2026-11-10"}
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 22), {}, rating), [])

    def test_spread_requires_matching_source_dates(self):
        pending = {"last_values": {"fr_mkt": 4.91, "de_mkt": 3.47},
                   "last_source_dates": {"fr_mkt": "2026-10-13", "de_mkt": "2026-10-13"}, "stale": []}
        self.assertEqual(watch.money_spread(pending), ("144.0bp", "2026-10-13"))
        pending["last_source_dates"]["de_mkt"] = "2026-10-12"
        self.assertEqual(watch.money_spread(pending)[0], "확인 불가(동일 기준일 자료 부족)")

    def test_message_says_not_a_forced_liquidation_deadline(self):
        rating = {**watch.parse_moodys(EXAMPLE_EN), "url": watch.AFT_EN}
        events = [{"kind": "milestone", "key": "milestone:2026-10-23:D-1", "days": 1}]
        _, msg = watch.format_event(rating, events, {}, dt.datetime(2026, 10, 22, 12, 0, tzinfo=watch.KST))
        self.assertIn("등급 강등 확정이 아닌", msg)
        self.assertIn("포지션 청산 마감일도 아닙니다", msg)
        self.assertIn("메모리주 영향은 조건부", msg)
        self.assertIn("AFT France Moody's rating calendar:", msg)

    def test_official_fetch_fallback(self):
        def fetch(url):
            if "/en/" in url:
                raise ConnectionError("en blocked")
            return EXAMPLE_FR
        rating, errors = watch.fetch_rating(fetch=fetch)
        self.assertEqual(rating["next_review"], "2026-10-23")
        self.assertEqual(rating["url"], watch.AFT_FR)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()

"""Offline regression for Figure's official article dates and query cutoff."""
import datetime as dt
import unittest
from unittest.mock import patch

import physical_ai_watch_figure_entry as figure


class FigureOfficialDatesTest(unittest.TestCase):
    def test_all_supported_months_and_one_or_two_digit_days(self):
        for month, number in figure.MONTHS.items():
            for day in (3, 17):
                with self.subTest(month=month, day=day):
                    actual = figure._figure_date_from_text(f"{month} {day:02d}, 2026")
                    self.assertEqual(actual, dt.datetime(2026, number, day, 12, tzinfo=dt.timezone.utc))
        self.assertEqual(figure._figure_date_from_text("September 3, 2026").day, 3)

    def test_real_official_article_dates_with_surrounding_text(self):
        # Dates directly visible on Figure's Helix 2.5 and Nscale articles.
        for text, day in (("Helix 2.5 September 17, 2026 Today we introduce", 17),
                          ("Figure and Nscale September 03, 2026 Partnership", 3)):
            self.assertEqual(figure._figure_date_from_text(text),
                             dt.datetime(2026, 9, day, 12, tzinfo=dt.timezone.utc))

    def test_whitespace_and_leap_day_are_preserved(self):
        for text in ("February 29, 2024", "February\n29,\t2024", "February\u00a029,\u00a02024"):
            self.assertEqual(figure._figure_date_from_text(text),
                             dt.datetime(2024, 2, 29, 12, tzinfo=dt.timezone.utc))

    def test_invalid_calendar_dates_return_none(self):
        for text in ("February 29, 2026", "February 30, 2024", "April 31, 2026",
                     "November 00, 2026", "December 32, 2026"):
            with self.subTest(text=text):
                self.assertIsNone(figure._figure_date_from_text(text))

    def test_unsupported_or_malformed_dates_remain_rejected(self):
        for text in ("", "2026-11-18", "Nov 18, 2026", "November 18 2026",
                     "November 18, 1999", "November 18, 20260", "November 118, 2026",
                     r"November\s18,\s2026", "NotNovember 18, 2026"):
            with self.subTest(text=text):
                self.assertIsNone(figure._figure_date_from_text(text))

    def test_official_query_recovers_valid_item_without_replaying_old_articles(self):
        dates = {"fresh": "November 18, 2026", "old": "September 17, 2026",
                 "future": "November 20, 2026", "invalid": "November 32, 2026"}
        index = "".join(f'<a href="/news/{slug}">{slug}</a>' for slug in dates)
        pages = {figure.FIGURE_NEWS_URL: index}
        for slug, date in dates.items():
            pages[f"https://www.figure.ai/news/{slug}"] = (
                f"<h1>Figure AI Helix humanoid model release</h1><p>{date}</p>"
                "<p>Figure 03 robot AI production deployment.</p>")
        before_queries = list(figure.base.QUERIES)
        with patch.object(figure.legacy, "_request_text", side_effect=pages.__getitem__) as request, \
             patch.object(figure.base, "NOW", dt.datetime(2026, 11, 18, 12, tzinfo=dt.timezone.utc)):
            rows = figure.query_news(figure.FIGURE_NEWS_SENTINEL)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["figure_official_slug"], "fresh")
        self.assertEqual(rows[0]["published"], "2026-11-18T12:00:00+00:00")
        self.assertEqual(rows[0]["published_precision"], "day")
        self.assertTrue(rows[0]["direct_primary"])
        self.assertEqual(request.call_count, 5)
        self.assertEqual(figure.base.QUERIES, before_queries)


if __name__ == "__main__":
    unittest.main()

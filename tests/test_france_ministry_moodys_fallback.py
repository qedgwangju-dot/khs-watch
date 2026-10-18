import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from scripts import france_ministry_moodys_fallback as m

PARIS = ZoneInfo("Europe/Paris")


class FranceMinistryMoodyTests(unittest.TestCase):
    def test_extracts_only_ministry_links(self):
        page = """
        <a href="https://presse.economie.gouv.fr/notation-moodys-france-2026/">
        Notation Moody's : réaction du ministre</a>
        <a href="https://evil.example/notation-moodys/">Notation Moody's outside</a>
        <a href="https://presse.economie.gouv.fr/autre/">Autre communiqué</a>
        """
        self.assertEqual(m.ministry_search_links(page), [
            ("https://presse.economie.gouv.fr/notation-moodys-france-2026/",
             "Notation Moody's : réaction du ministre")])

    def test_does_not_backfill_historical_2025_release(self):
        doc = """
        <meta property="article:published_time" content="2025-10-24T12:01:00+02:00">
        <article>Notation Moody's : la note souveraine de la France est Aa3</article>
        """
        notice = m.validate_ministry_notice(
            doc, "https://presse.economie.gouv.fr/notation-moodys/",
            dt.datetime(2026, 10, 24, 12, tzinfo=PARIS))
        self.assertIsNone(notice)

    def test_new_2026_official_press_announces_event_not_rating(self):
        doc = """
        <meta property="article:published_time" content="2026-10-24T08:01:00+02:00">
        <article>Notation Moody's : la note souveraine de la France</article>
        """
        notice = m.validate_ministry_notice(
            doc, "https://presse.economie.gouv.fr/notation-moodys-france/",
            dt.datetime(2026, 10, 24, 12, tzinfo=PARIS))
        self.assertEqual(notice["date"], "2026-10-24")
        self.assertEqual(notice["source_kind"], "official_government_press")
        self.assertNotIn("rating", notice)

    def test_future_press_date_rejected(self):
        doc = '<meta property="article:published_time" content="2026-10-24T10:00"><p>Moody note souveraine France</p>'
        self.assertIsNone(m.validate_ministry_notice(
            doc, "https://presse.economie.gouv.fr/notation-moodys-france/",
            dt.datetime(2026, 10, 23, 12, tzinfo=PARIS)))

    def test_discovery_distinguishes_press_release_from_rating_change(self):
        index = ('<a href="https://presse.economie.gouv.fr/notation-moodys-france/">'
                 "Notation Moody's : réaction de la France</a>")
        page = ('<meta property="article:published_time" content="2026-10-24T01:00:00+02:00">'
                "<p>Notation Moody's : note souveraine de la France</p>")
        def fetch(url):
            return index if "?s=" in url else page
        new, errors = m.discover_ministry_notice(fetch, dt.datetime(2026, 10, 24, 12, tzinfo=PARIS))
        self.assertFalse(errors)
        self.assertEqual(new["title"], "Notation Moody's : réaction de la France")


if __name__ == "__main__":
    unittest.main()

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
            if url == m.DIRECT_NOTICE_URL:
                return "<html><p>Archived index link missing publication date</p></html>"
            return index if "?s=" in url else page
        new, errors = m.discover_ministry_notice(fetch, dt.datetime(2026, 10, 24, 12, tzinfo=PARIS))
        self.assertFalse(errors)
        self.assertEqual(new["title"], "Notation Moody's : réaction de la France")

    def test_oct23_direct_ministry_release_is_recovered_with_source_grade_only(self):
        doc = (
            '<meta property="article:published_time" content="2026-10-23T20:00:00+02:00">'
            "<article>Paris, le 23 octobre 2026. Moody's : Réaction de Roland Lescure. "
            "Le ministre prend acte de la décision de Moody's de maintenir la note "
            "de la France à Aa3 avec perspective négative.</article>"
        )
        seen = []
        def fetch(url):
            seen.append(url)
            if url == m.DIRECT_NOTICE_URL:
                return doc
            raise AssertionError("Search fallback must not run after a verified direct release")
        notice, errors = m.discover_ministry_notice(
            fetch, dt.datetime(2026, 10, 24, 12, tzinfo=PARIS))
        self.assertFalse(errors)
        self.assertEqual(seen, [m.DIRECT_NOTICE_URL])
        self.assertEqual(notice["date"], "2026-10-23")
        self.assertEqual(notice["source_kind"], "official_government_press")
        self.assertEqual(notice["reported_rating_by_government"], "Aa3")
        self.assertEqual(notice["reported_outlook_by_government"], "Negative")
        self.assertNotIn("rating", notice)

    def test_direct_notice_403_still_uses_independent_ministry_search(self):
        index = ('<a href="/notation-moodys-france-2026/">'
                 "Notation Moody's : réaction du ministre</a>")
        page = ('<time datetime="2026-10-23T20:00:00+02:00"></time>'
                "<p>Moody's : note souveraine de la France.</p>")
        def fetch(url):
            if url == m.DIRECT_NOTICE_URL:
                raise RuntimeError("HTTP 403")
            return index if "?s=" in url else page
        notice, errors = m.discover_ministry_notice(
            fetch, dt.datetime(2026, 10, 24, 12, tzinfo=PARIS))
        self.assertEqual(notice["date"], "2026-10-23")
        self.assertEqual(len(errors), 1)
        self.assertIn("direct notice", errors[0])
        self.assertNotIn("reported_rating_by_government", notice)

    def test_stale_2025_direct_ministry_page_cannot_be_alerted(self):
        doc = ('<time datetime="2025-10-23T12:00:00+02:00"></time>'
               "<article>Moody's : note souveraine de la France.</article>")
        self.assertIsNone(m.validate_ministry_notice(
            doc, m.DIRECT_NOTICE_URL, dt.datetime(2026, 10, 24, tzinfo=PARIS)))

if __name__ == "__main__":
    unittest.main()

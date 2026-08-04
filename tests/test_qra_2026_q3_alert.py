import unittest

from scripts.qra_2026_q3_alert import QRASectionParser, preferred_links


class QRASectionParserTests(unittest.TestCase):
    def test_target_section_is_detected_and_scoped(self):
        source = """
        <h3>DOCUMENTS RELEASED at 3:00 PM Monday, August 3, 2026</h3>
        <a href="/old">Financing Estimates: 2026 - 3rd Quarter</a>
        <h3>DOCUMENTS RELEASED at 8:30 AM Wednesday, August 5, 2026</h3>
        <a href="/policy">Policy Statement: 2026 - 3rd Quarter</a>
        <a href="/table">TBAC Recommended Financing Table by Refunding Quarter</a>
        <h3>DOCUMENTS RELEASED at 8:30 AM Wednesday, May 6, 2026</h3>
        <a href="/older">Policy Statement: 2026 - 2nd Quarter</a>
        """
        parser = QRASectionParser("https://home.treasury.gov/base")
        parser.feed(source)
        self.assertTrue(parser.found_target)
        self.assertEqual([item.text for item in parser.links], [
            "Policy Statement: 2026 - 3rd Quarter",
            "TBAC Recommended Financing Table by Refunding Quarter",
        ])
        self.assertEqual(parser.links[0].url, "https://home.treasury.gov/policy")

    def test_next_release_notice_is_not_false_positive(self):
        source = """
        <h3>DOCUMENTS RELEASED at 8:30 AM Wednesday, May 6, 2026</h3>
        <a href="/q2">Policy Statement: 2026 - 2nd Quarter</a>
        <p>(The next release is scheduled for August 5, 2026)</p>
        """
        parser = QRASectionParser()
        parser.feed(source)
        self.assertFalse(parser.found_target)
        self.assertEqual(parser.links, [])

    def test_preferred_links_keep_official_order(self):
        source = """
        <h3>DOCUMENTS RELEASED at 8:30 a.m. Wednesday, August 5, 2026</h3>
        <a href="/table">TBAC Recommended Financing Table by Refunding Quarter</a>
        <a href="/policy">Policy Statement: 2026 - 3rd Quarter</a>
        <a href="/auction.pdf">Auction Schedule: PDF Format</a>
        """
        parser = QRASectionParser()
        parser.feed(source)
        items = preferred_links(parser.links)
        self.assertEqual([item.text for item in items], [
            "Policy Statement: 2026 - 3rd Quarter",
            "TBAC Recommended Financing Table by Refunding Quarter",
            "Auction Schedule: PDF Format",
        ])


if __name__ == "__main__":
    unittest.main()

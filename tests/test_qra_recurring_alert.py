import unittest

from scripts.qra_recurring_alert import (
    ReleaseParser,
    extract_refunding_amounts,
    extract_shortfall,
    guidance_word,
    maintain_guidance,
)


class QRARecurringAlertTests(unittest.TestCase):
    def test_release_parser_collects_830_sections(self):
        source = """
        <h3>DOCUMENTS RELEASED at 8:30 AM Wednesday, August 5, 2026</h3>
        <a href="/policy">Policy Statement: 2026 - 3rd Quarter</a>
        <a href="/minutes">TBAC Minutes: 2026 - 3rd Quarter</a>
        <h3>DOCUMENTS RELEASED at 3:00 PM Monday, August 3, 2026</h3>
        <a href="/estimate">Financing Estimates</a>
        <h3>DOCUMENTS RELEASED at 8:30 AM Wednesday, May 6, 2026</h3>
        <a href="/old-policy">Policy Statement: 2026 - 2nd Quarter</a>
        """
        parser = ReleaseParser("https://home.treasury.gov/base")
        parser.feed(source)
        self.assertEqual(len(parser.sections), 2)
        self.assertIn("August 5, 2026", parser.sections[0].heading)
        self.assertEqual(parser.sections[0].links[0].url, "https://home.treasury.gov/policy")

    def test_guidance_change_increases_to_changes(self):
        previous = "Treasury will continue to assess potential future increases to nominal coupon and FRN auction sizes."
        current = "Treasury will continue to assess potential future changes to nominal coupon and FRN auction sizes."
        self.assertEqual(guidance_word(previous), "increases")
        self.assertEqual(guidance_word(current), "changes")

    def test_maintain_guidance(self):
        text = "Treasury anticipates maintaining nominal coupon and FRN auction sizes for at least the next several quarters."
        self.assertTrue(maintain_guidance(text))

    def test_refunding_amounts_tenor_then_amount(self):
        text = (
            "The Treasury will auction a 3-year note in the amount of $58 billion, "
            "a 10-year note in the amount of $42 billion, and a 30-year bond in the amount of $25 billion."
        )
        self.assertEqual(extract_refunding_amounts(text), {"3년물": 58.0, "10년물": 42.0, "30년물": 25.0})

    def test_shortfall(self):
        text = "Dealers estimated a financing shortfall of approximately $1.45 trillion across FY2027-FY2028."
        value, years = extract_shortfall(text)
        self.assertEqual(value, "1.45")
        self.assertIsNotNone(years)


if __name__ == "__main__":
    unittest.main()

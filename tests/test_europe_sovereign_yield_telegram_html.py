import unittest
from scripts.europe_sovereign_yield_telegram_html import render_chunks, render_line, LINKS


class EuropeYieldTelegramHtmlTests(unittest.TestCase):
    def test_all_seven_source_links_are_clickable_with_short_labels(self):
        lines = [
            prefix + (
                f"https://{host}/archive/x?date=2026-10-08&series=10y"
                if host != "tradingeconomics.com" else
                f"https://{host}/italy/government-bond-yield"
            )
            for prefix, label, host in LINKS
        ]
        chunks = render_chunks("🔴 [유럽 국채금리 경보] 높은 수준\n\n■ 출처\n" + "\n".join(lines))
        combined = "\n".join(chunks)
        self.assertEqual(combined.count("<a href="), 7)
        self.assertEqual(combined.count("</a>"), 7)
        self.assertIn("&amp;series=10y", combined)
        self.assertIn("<b>■ 출처</b>", combined)
        self.assertIn("이탈리아 10년물 시장자료", combined)
        self.assertNotIn("https://tradingeconomics.com/italy/government-bond-yield</a>", combined)

    def test_invalid_source_url_rejected(self):
        for url in ["javascript:alert(1)", "http://tradingeconomics.com/foo",
                    "https://evil.example.com/foo"]:
            with self.assertRaises(ValueError):
                render_line("• Italy 10Y Trading Economics 보조 시장자료: " + url)

    def test_html_reserved_characters_are_escaped(self):
        self.assertEqual(render_line("가격 A & B < C"), "가격 A &amp; B &lt; C")

    def test_safe_chunking_never_cuts_link_tags(self):
        prefix = "반복 문장. " * 250
        lines = "\n\n".join([prefix] * 3)
        long_msg = lines + "\n\n" + "• Italy 10Y Trading Economics 보조 시장자료: https://tradingeconomics.com/italy/government-bond-yield"
        chunks = render_chunks(long_msg, limit=3900)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(s) <= 3900 for s in chunks))
        self.assertEqual(sum(x.count("<a href=") for x in chunks), 1)
        self.assertEqual(sum(x.count("</a>") for x in chunks), 1)

    def test_malformed_or_oversize_input_fails_closed(self):
        with self.assertRaises(ValueError):
            render_chunks("")
        with self.assertRaises(ValueError):
            render_chunks("Z" * 4000, limit=3900)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from yen_policy_news_message_guard import split_html_message


class YenPolicyTelegramSafetyTests(unittest.TestCase):
    def test_single_message_is_not_modified(self):
        chunks = split_html_message("제목", '내용\n확인 출처: 연준 · <a href="https://www.federalreserve.gov/">원문</a>')
        self.assertEqual(len(chunks), 1)
        self.assertIn('href="https://www.federalreserve.gov/"', chunks[0])

    def test_long_message_is_split_without_losing_source_links(self):
        line = "시장 해석: " + "실제 개입과 과거 공시를 구분합니다. " * 5 + "\n"
        source = '확인 출처: 연준 · <a href="https://www.federalreserve.gov/monetarypolicy/fomcminutes20260916.htm">원문</a>'
        body = line * 50 + source
        chunks = split_html_message("엔화 정책", body, max_length=420)
        self.assertGreater(len(chunks), 2)
        self.assertIn(source, "\n".join(chunks))
        self.assertTrue(all(len(x) <= 420 for x in chunks))
        self.assertEqual(sum(x.count("<a ") for x in chunks), 1)
        self.assertEqual(sum(x.count("</a>") for x in chunks), 1)

    def test_unbalanced_html_is_rejected_instead_of_sent(self):
        with self.assertRaises(ValueError):
            split_html_message("제목", '확인 출처: <a href="https://example.org">원문')

    def test_oversized_line_is_rejected_instead_of_truncated(self):
        with self.assertRaises(ValueError):
            split_html_message("제목", "매우 긴 원문" * 1000, max_length=400)

    def test_empty_body_is_rejected(self):
        with self.assertRaises(ValueError):
            split_html_message("제목", "  ")


if __name__ == "__main__":
    unittest.main()

import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import currency_krw_guard as g


class CurrencyKRWGuardTests(unittest.TestCase):
    def fake_rate(self, currency):
        return {
            "USD": (1350.0, "test"),
            "EUR": (1600.0, "test"),
            "JPY": (9.0, "test"),
            "MYR": (330.0, "test"),
        }[currency]

    def test_korean_usd_amount_gets_immediate_krw_parentheses(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("기업가치 1,500억달러")
        self.assertIn("1,500억달러(", out)
        self.assertIn("약 202조5,000억원", out)

    def test_usd_billion_symbol_gets_immediate_krw_parentheses(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("could raise $15 billion")
        self.assertIn("$15 billion(", out)
        self.assertIn("약 20조2,500억원", out)

    def test_existing_parenthetical_is_not_duplicated(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("150억달러(약 20조2,500억원)")
        self.assertEqual(out, "150억달러(약 20조2,500억원)")

    def test_exchange_rate_basis_is_not_rewritten(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("1달러=1,350원")
        self.assertEqual(out, "1달러=1,350원")

    def test_range_gets_one_immediate_krw_range(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("600억~640억달러")
        self.assertIn("600억~640억달러(", out)
        self.assertIn("약 81조원~약 86조4,000억원", out)

    def test_other_foreign_currency_words_are_supported(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("5억유로 / 100억엔 / 50억링깃")
        self.assertIn("5억유로(", out)
        self.assertIn("100억엔(", out)
        self.assertIn("50억링깃(", out)


if __name__ == "__main__":
    unittest.main()

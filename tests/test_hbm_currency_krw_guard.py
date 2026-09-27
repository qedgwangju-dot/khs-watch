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
            "CNY": (190.0, "test"),
            "HKD": (173.0, "test"),
            "GBP": (1810.0, "test"),
            "SGD": (1050.0, "test"),
            "TWD": (44.0, "test"),
            "AUD": (900.0, "test"),
            "CAD": (990.0, "test"),
            "CHF": (1700.0, "test"),
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


    def test_fx_failure_blocks_alert_instead_of_sending_unconverted_amount(self):
        with patch.object(g, "_rate", return_value=(None, "failed")):
            with self.assertRaises(RuntimeError):
                g.enforce_text("기업가치 1,500억달러")

    def test_validator_rejects_unpaired_foreign_amount(self):
        with self.assertRaises(RuntimeError):
            g.validate_text("조달액 150억달러")
        g.validate_text("조달액 150억달러(약 20조원)")

    def test_extended_currency_symbols_are_supported(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("HK$500 million / €2 billion / £1 billion")
        self.assertIn("HK$500 million(", out)
        self.assertIn("€2 billion(", out)
        self.assertIn("£1 billion(", out)

if __name__ == "__main__":
    unittest.main()

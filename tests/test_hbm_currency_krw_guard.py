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

    def test_us_investment_alert_all_dollar_amounts_get_immediate_krw_parentheses(self):
        sample = (
            "Project Star: 텍사스 엔시날 제1호 공식 추진 · 223억달러 · 6,472MW\n"
            "Project Power: 원전 8기 프레임워크 합의 · 최대 1,200억달러\n"
            "한국 대미 전략투자 2,000억달러 · 알래스카 LNG 540억달러"
        )
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text(sample)
        for token in ("223억달러", "1,200억달러", "2,000억달러", "540억달러"):
            self.assertIn(token + "(", out)
        g.validate_text(out)

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

    def test_extended_currency_words_are_supported(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("20억위안 / 10억홍콩달러 / 3억싱가포르달러")
        self.assertIn("20억위안(", out)
        self.assertIn("10억홍콩달러(", out)
        self.assertIn("3억싱가포르달러(", out)

    def test_iso_currency_amounts_get_immediate_krw_parentheses(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("리포트 가격 USD 30,000 / 비용 EUR 2 million")
        self.assertIn("USD 30,000(", out)
        self.assertIn("EUR 2 million(", out)
        g.validate_text(out)

    def test_validator_rejects_unpaired_iso_currency_amount(self):
        with self.assertRaises(RuntimeError):
            g.validate_text("가격 USD 30,000")
        g.validate_text("가격 USD 30,000(약 4,050만원)")


    def test_usd_per_mw_gets_immediate_krw_parentheses(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("MW당 연환산 매출 $40 million/MW")
        self.assertIn("$40 million/MW(", out)
        self.assertIn("원/MW)", out)
        g.validate_text(out)

    def test_korean_currency_per_mwh_gets_immediate_krw_parentheses(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("전력비 2백만달러/MWh")
        self.assertIn("2백만달러/MWh(", out)
        self.assertIn("원/MWh)", out)
        g.validate_text(out)

    def test_iso_currency_per_gpu_gets_immediate_krw_parentheses(self):
        with patch.object(g, "_rate", side_effect=self.fake_rate):
            out = g.enforce_text("가격 USD 30,000/GPU")
        self.assertIn("USD 30,000/GPU(", out)
        self.assertIn("원/GPU)", out)
        g.validate_text(out)

if __name__ == "__main__":
    unittest.main()

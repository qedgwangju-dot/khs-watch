import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "coin_alert_korean_terms",
    ROOT / "scripts" / "coin_alert_korean_terms.py",
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class CoinAlertKoreanTermsTest(unittest.TestCase):
    def test_gloss_is_added_only_once_per_alert(self):
        text = "USDC is used here. USDC balance rises. Stablecoin payments. stablecoin volume."
        rendered = MOD.koreanize_html_visible_text(text)
        self.assertEqual(rendered.count("USDC(서클 달러 스테이블코인)"), 1)
        self.assertIn("USDC balance rises", rendered)
        self.assertEqual(rendered.count("(스테이블코인)"), 1)

    def test_existing_parenthetical_gloss_counts_as_explained(self):
        text = "USDC(서클 달러 스테이블코인) 담보. USDC 잔액."
        rendered = MOD.koreanize_html_visible_text(text)
        self.assertEqual(rendered.count("USDC(서클 달러 스테이블코인)"), 1)
        self.assertIn("USDC 잔액", rendered)


    def test_actual_crypto_missing_etf_ticker_is_preserved(self):
        # Derived pre-translation excerpt from run 39523938653 and its saved state.
        text = "ETF(상장지수펀드) 2026-10-20 · 잠정 10/12 반영 · 미보고 IBIT, BTCO"
        self.assertEqual(MOD.koreanize_html_visible_text(text), text)

    def test_btc_substrings_do_not_change_other_fund_symbols(self):
        text = "FBTC BTCO BTCW GBTC"
        self.assertEqual(MOD.koreanize_html_visible_text(text), text)

    def test_embedded_tickers_do_not_consume_standalone_btc_gloss(self):
        text = "BTCO FBTC BTCW GBTC · BTC 가격과 BTC 잔액"
        rendered = MOD.koreanize_html_visible_text(text)
        self.assertEqual(rendered, "BTCO FBTC BTCW GBTC · BTC(비트코인) 가격과 BTC 잔액")

    def test_embedded_parenthetical_does_not_hide_first_btc(self):
        text = "BTCO BTCW(상품 코드) FBTC(펀드) · BTC와 BTC"
        rendered = MOD.koreanize_html_visible_text(text)
        self.assertEqual(rendered, "BTCO BTCW(상품 코드) FBTC(펀드) · BTC(비트코인)와 BTC")

    def test_btc_ascii_identifier_boundaries_and_html_attributes(self):
        text = '<a href="https://example.com/BTC?symbol=BTCO" title="BTC">BTCO</a> XBTC BTC2 BTC_value (BTC)는 BTC.'
        rendered = MOD.koreanize_html_visible_text(text)
        expected = '<a href="https://example.com/BTC?symbol=BTCO" title="BTC">BTCO</a> XBTC BTC2 BTC_value (BTC(비트코인))는 BTC.'
        self.assertEqual(rendered, expected)

if __name__ == "__main__":
    unittest.main()

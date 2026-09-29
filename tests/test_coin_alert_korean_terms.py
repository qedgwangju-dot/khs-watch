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


if __name__ == "__main__":
    unittest.main()

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_alert_formatter", ROOT / "scripts" / "clarity_alert_formatter.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityFormatterTest(unittest.TestCase):
    def test_sec_regulation_crypto_assets_is_korean_and_clickable(self):
        event = {
            "source": "SEC 보도자료",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "title": "SEC Proposes New Regulation Crypto Assets",
            "url": "https://www.sec.gov/newsroom/press-releases/2026-76-sec-proposes-new-regulation-crypto-assets",
            "date": "Tue, 18 Aug 2026 13:15:48 -0400",
            "detail": "The Securities and Exchange Commission today announced that it proposed new rules, titled Regulation Crypto Assets, that would create a clear and fit-for-purpose framework for certain investment contracts involving crypto assets.",
        }
        chunks = MOD.build_chunks([event])
        rendered = "\n".join(chunks)
        self.assertIn("SEC, 암호자산 관련 투자계약", rendered)
        self.assertIn("쉽게 말하면", rendered)
        self.assertIn('<a href="https://www.sec.gov/newsroom/press-releases/2026-76-sec-proposes-new-regulation-crypto-assets">원문</a>', rendered)
        self.assertNotIn("The Securities and Exchange Commission today announced", rendered)
        self.assertLessEqual(max(map(len, chunks)), 3900)


if __name__ == "__main__":
    unittest.main()

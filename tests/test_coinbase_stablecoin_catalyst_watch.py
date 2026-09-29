import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "coinbase_stablecoin_catalyst_watch",
    ROOT / "scripts" / "coinbase_stablecoin_catalyst_watch.py",
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class CoinbaseStablecoinCatalystWatchTest(unittest.TestCase):
    def test_extract_coinbase_dco_registered_row(self):
        sample = (
            "Gemini Olympus, LLC Registered 04/29/2026 Registered by Commission order. "
            "Coinbase Clearing LLC Registered 09/28/2026 Registered by Commission order; "
            "permitted to clear fully collateralized futures, options on futures, and swaps. "
            "CX Clearinghouse, L.P. Registered 04/20/2010 Registered by Commission order."
        )
        row = MOD.extract_coinbase_clearing_row(sample)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Registered")
        self.assertEqual(row["date"], "09/28/2026")
        self.assertIn("fully collateralized futures", row["remarks"])

    def test_citi_alert_explains_business_meaning_in_korean(self):
        event = MOD.Event(
            "citi_coinbase_stablecoin_payments",
            "Citi·Coinbase, 기업 결제망과 스테이블코인 결제 인프라 직접 연결",
            MOD.COINBASE_CITI_URL,
            "2026-09-28",
            "Coinbase 공식 발표",
            "법정화폐가 스테이블코인으로 자동 전환되고 Citi 기관고객은 스테이블코인 결제를 받을 수 있습니다.",
        )
        rendered = MOD.build_alert([event])
        self.assertIn("<b>🧩 핵심</b>", rendered)
        self.assertIn("기업 결제망", rendered)
        self.assertIn("반복수익 경로", rendered)
        self.assertIn("USDC 사용 비중", rendered)
        self.assertIn("<b>⚠️ 실패 경로</b>", rendered)
        self.assertNotIn("핵심 한 줄 요약", rendered)

    def test_dco_alert_explains_exchange_broker_clearing_stack(self):
        event = MOD.Event(
            "coinbase_clearing_dco_registered",
            "Coinbase Clearing LLC, CFTC DCO(파생상품청산기관) 등록 완료",
            MOD.CFTC_DCO_URL,
            "2026-09-28",
            "CFTC 공식 등록목록",
            "CFTC가 Coinbase Clearing LLC를 DCO(파생상품청산기관)로 등록했습니다.",
        )
        rendered = MOD.build_alert([event])
        self.assertIn("거래소(DCM)·중개(FCM)", rendered)
        self.assertIn("청산(DCO)", rendered)
        self.assertIn("실제 상품의 자체 DCO 이전·USDC 담보·24/7 청산 적용은 별도 확인 필요", rendered)
        self.assertIn("Coinbase 자체 DCO 청산 거래량", rendered)
        self.assertNotIn("핵심 한 줄 요약", rendered)


if __name__ == "__main__":
    unittest.main()

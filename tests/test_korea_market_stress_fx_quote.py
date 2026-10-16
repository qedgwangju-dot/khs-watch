"""환율 15:30 종가 식별·오류정보 비노출 회귀 시험."""
import pathlib
import unittest

import korea_market_stress_watch_v14 as fx
import korea_market_stress_watch_v11 as ecos


class SeoulFXQuoteTests(unittest.TestCase):
    def test_seoul_close_headline(self):
        text = "[외환] 원/달러 환율 6.3원 오른 1,344.6원(15:30 기준가)"
        self.assertEqual(fx._extract_krw_rate(text), 1344.6)

    def test_currency_table_usd_first_not_last_won_amount(self):
        text = (
            "외국환시세(10월15일·15:30 기준가) (15:30) 통 화 매매기준율 "
            "미국 달러* 일본 엔(100) 유럽통화단위 유로 "
            "1,344.60 851.34 1,507.16 1350원 호가 참고, "
            "다른 기사에서는 1,350원대라고 표현"
        )
        self.assertEqual(fx._extract_krw_rate(text), 1344.6)

    def test_ambiguous_intraday_quotation_is_not_a_close(self):
        self.assertIsNone(fx._extract_krw_rate("환율 장중 1,350원대에서 1,344원대로 하락"))
        self.assertIsNone(fx._extract_krw_rate("외국환시세 15:30 뉴스 다른 환율 1,350원"))
        self.assertIsNone(fx._extract_krw_rate("15:30 서울시세 1,350원 다른 가격"))

    def test_ambiguous_data_fails_closed_instead_of_crossing_alert(self):
        self.assertIsNone(fx._extract_krw_rate("외국환시세(10월15일·15:30 기준가) 달러 1,350원"))
        self.assertEqual(fx._extract_krw_rate("외국환시세(15:30 기준가) 미국 달러* | 1,344.60"), 1344.6)

    def test_ecos_exception_logging_cannot_embed_request_url(self):
        source = pathlib.Path(ecos.__file__).read_text(encoding="utf-8")
        self.assertIn("인증정보 비노출", source)
        self.assertNotIn('fx["ecos_error"] = f"{type(exc).__name__}: {exc}"', source)


if __name__ == "__main__":
    unittest.main()

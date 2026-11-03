"""환율 15:30 종가 식별·오류정보 비노출 회귀 시험."""
import pathlib
import unittest
from unittest.mock import patch
import datetime as dt
import requests

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

    def test_fx_list_uses_explicit_usd_close_before_unavailable_table(self):
        article_list = (
            '<a href="fxview?id=20261015153544777">'
            '외국환시세(10월15일·15:30 기준가)</a>'
            '<a href="fxview?id=20261015153115942">'
            '[외환] 원/달러 환율 6.3원 오른 1,344.6원(15:30 기준가)</a>'
        )

        class Response:
            text = article_list
            def raise_for_status(self):
                return None

        def mock_get(url, **kwargs):
            if "fxlist?page=1" in url:
                return Response()
            raise AssertionError("Correct headline should avoid fetching generic FX table")

        with patch.object(fx.requests, "get", side_effect=mock_get):
            result = fx.fetch_seoul_prev_close(dt.datetime(2026, 10, 16, 19, 35, tzinfo=fx.watch.KST))
        self.assertEqual(result["date"], "2026-10-15")
        self.assertEqual(result["value"], 1344.6)
        self.assertTrue(result["source"].endswith("20261015153115942"))

    def test_ksure_continues_after_unreadable_first_page(self):
        # Regression: page 1 includes a qualifying 15:30 table but its detail
        # times out. A valid explicit USD/KRW 15:30 headline on page 2
        # must still be considered before failing closed.
        article_lists = {
            "fxlist?page=1": (
                '<a href="fxview?id=20261102153900001">'
                '외국환시세(11월2일·15:30 기준가)</a>'
            ),
            "fxlist?page=2": (
                '<a href="fxview?id=20261102153400002">'
                '[외환] 원/달러 환율 2.4원 오른 1,344.6원(15:30 기준가)</a>'
            ),
        }

        class Response:
            def __init__(self, text):
                self.text = text
            def raise_for_status(self):
                return None

        def mock_get(url, **kwargs):
            for path, content in article_lists.items():
                if path in url:
                    return Response(content)
            if "fxview?id=20261102153900001" in url:
                raise requests.Timeout("unavailable FX table")
            raise AssertionError("Unexpected KSURE request: " + url)

        with patch.object(fx.requests, "get", side_effect=mock_get):
            result = fx.fetch_seoul_prev_close(
                dt.datetime(2026, 11, 3, 20, 0, tzinfo=fx.watch.KST)
            )
        self.assertEqual(result["date"], "2026-11-02")
        self.assertEqual(result["value"], 1344.6)
        self.assertTrue(result["source"].endswith("20261102153400002"))

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

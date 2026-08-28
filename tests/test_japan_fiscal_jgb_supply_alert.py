from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import japan_fiscal_jgb_supply_alert as alert  # noqa: E402
from krw_fx import JpyKrwQuote, format_krw, yen_to_krw  # noqa: E402


class JapanFiscalJgbSupplyAlertTests(unittest.TestCase):
    def item(self, title: str, source: str = "Reuters", description: str = "") -> alert.Item:
        return alert.Item(
            title=title,
            link="https://example.com/story",
            source=source,
            description=description,
            published=dt.datetime(2026, 8, 28, 10, 0, tzinfo=dt.timezone.utc),
        )

    def test_reuters_40_trillion_headline_is_high_materiality(self) -> None:
        result = alert.classify(
            self.item("Japan aims to cap FY27 new bond issuance at 40 trillion yen, PM says in Yomiuri interview")
        )
        self.assertEqual(result, ("일본 신규 국채 발행 목표·상한 변화", 5))

    def test_korean_40_trillion_headline_is_captured(self) -> None:
        result = alert.classify(self.item("일본, 신규 국채 발행 규모 40조엔으로 제한 계획", source="요미우리신문"))
        self.assertEqual(result, ("일본 신규 국채 발행 목표·상한 변화", 5))

    def test_chinese_40_trillion_headline_is_captured(self) -> None:
        result = alert.classify(self.item("日本首相计划将新国债发行规模限制在40万亿日元", source="读卖新闻"))
        self.assertEqual(result, ("일본 신규 국채 발행 목표·상한 변화", 5))

    def test_extract_trillion_yen_in_four_languages(self) -> None:
        self.assertEqual(alert.extract_trillion_yen("40 trillion yen"), 40.0)
        self.assertEqual(alert.extract_trillion_yen("40兆円"), 40.0)
        self.assertEqual(alert.extract_trillion_yen("40조엔"), 40.0)
        self.assertEqual(alert.extract_trillion_yen("40万亿日元"), 40.0)

    def test_generic_jgb_market_story_is_not_a_policy_alert(self) -> None:
        self.assertIsNone(alert.classify(self.item("Japan 10-year JGB yield rises to 2.9%")))
        self.assertIsNone(alert.classify(self.item("Japan offers 2.6 trillion yen of 10-year JGBs at auction")))

    def test_40_trillion_vs_fy26_revised_baseline(self) -> None:
        diff = 40.0 - alert.FY26_NEW_BONDS_TRILLION_YEN
        pct = diff / alert.FY26_NEW_BONDS_TRILLION_YEN * 100.0
        self.assertAlmostEqual(diff, 7.3025, places=4)
        self.assertAlmostEqual(pct, 22.333, places=2)

    def test_krw_formatter_uses_same_cross_quote(self) -> None:
        quote = JpyKrwQuote("2026-08-21", 1385.01, 158.91, 1385.01 / 158.91)
        won = yen_to_krw(40_000_000_000_000.0, quote)
        self.assertGreater(won, 348_000_000_000_000)
        self.assertLess(won, 349_000_000_000_000)
        rendered = format_krw(won)
        self.assertIn("조", rendered)
        self.assertTrue(rendered.endswith("원"))

    def test_context_contains_krw_for_every_yen_money_item(self) -> None:
        quote = JpyKrwQuote("2026-08-21", 1385.01, 158.91, 1385.01 / 158.91)
        text = "\n".join(alert.context_lines("일본 신규 국채 발행 목표·상한 변화", 40.0, quote))
        self.assertIn("40.00조엔 (약", text)
        self.assertIn("32.6975조엔 (약", text)
        self.assertIn("36.6386조엔 (약", text)
        self.assertIn("31.2758조엔 (약", text)
        self.assertIn("원화 환산 기준", text)

    def test_main_withholds_money_alert_if_krw_quote_fails(self) -> None:
        now = dt.datetime(2026, 8, 28, 10, 15, tzinfo=dt.timezone.utc)
        item = self.item(
            "Japan aims to cap FY27 new bond issuance at 40 trillion yen, PM says in Yomiuri interview"
        )
        rss = (
            "<rss><channel><item>"
            f"<title>{item.title}</title>"
            f"<link>{item.link}</link>"
            f"<source>{item.source}</source>"
            "<description>Japan plans to limit new government bond issuance to around 40 trillion yen.</description>"
            "<pubDate>Fri, 28 Aug 2026 10:00:00 GMT</pubDate>"
            "</item></channel></rss>"
        )
        with mock.patch.object(alert, "fetch", return_value=rss), \
             mock.patch.object(alert, "latest_jpy_krw", side_effect=RuntimeError("fx unavailable")), \
             mock.patch.object(alert, "load_state", return_value={}):
            result = alert.main(now)
        self.assertEqual(result, 2)
        self.assertFalse(alert.BODY.exists())


if __name__ == "__main__":
    unittest.main()

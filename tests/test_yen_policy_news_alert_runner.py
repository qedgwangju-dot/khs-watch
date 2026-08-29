from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_policy_news_alert_runner as runner  # noqa: E402


class YenPolicyNewsRunnerTests(unittest.TestCase):
    def item(self, title: str, source: str, description: str = "") -> runner.base.NewsItem:
        return runner.base.NewsItem(
            title=title,
            link="https://www.wsj.com/finance/currencies/test",
            source=source,
            description=description,
            published=dt.datetime(2026, 8, 19, 5, 0, tzinfo=dt.timezone.utc),
        )

    def test_wsj_is_major_source(self) -> None:
        item = self.item(
            "BOJ Has Chance to Support Yen With September Rate Hike",
            "The Wall Street Journal",
        )
        self.assertEqual(runner.base.source_level(item), 1)
        self.assertEqual(runner.base.source_group(item.source, item.text), "Wall Street Journal")

    def test_user_wsj_example_is_alerted_as_market_forecast(self) -> None:
        item = self.item(
            "BOJ Has Chance to Support Yen With September Rate Hike",
            "The Wall Street Journal",
            "HSBC strategist says a September hike could support the yen.",
        )
        classified = runner.base.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "BOJ 9월 인상 전망·시장 기대")
        self.assertEqual(classified.material_score, 3)
        rank, groups = runner.base.corroboration_rank(classified, [classified])
        self.assertEqual(rank, 1)
        self.assertEqual(groups, ["Wall Street Journal"])

    def test_official_or_reported_signal_keeps_signal_label(self) -> None:
        item = self.item(
            "BOJ September rate hike increasingly likely after hawkish debate",
            "Reuters",
        )
        classified = runner.base.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "BOJ 9월 인상 기대·신호")

    def test_explicit_wsj_queries_are_installed(self) -> None:
        queries = [query for _language, query in runner.base.RSS_QUERIES]
        self.assertTrue(any("Wall Street Journal" in query for query in queries))
        self.assertTrue(any("WSJ" in query for query in queries))

    def test_wsj_headline_uses_verified_literal_translation(self) -> None:
        current = dt.datetime(2026, 8, 19, 7, 0, tzinfo=dt.timezone.utc)
        translated, status = runner.base.translate_headline_to_korean(
            "BOJ Has Chance to Support Yen With September Rate Hike",
            "The Wall Street Journal",
            "BOJ 9월 인상 전망·시장 기대",
            current,
        )
        self.assertEqual(status, "verified_literal")
        self.assertEqual(
            translated,
            "BOJ는 9월 금리 인상으로 엔화를 지지할 기회가 있다",
        )
        self.assertNotIn("확정", translated)
        self.assertNotIn("결정", translated)

    def test_modal_translation_failure_never_upgrades_possibility_to_fact(self) -> None:
        current = dt.datetime(2026, 8, 19, 7, 0, tzinfo=dt.timezone.utc)
        with mock.patch.object(
            runner,
            "_original_translate_headline",
            return_value=("BOJ가 9월 금리를 인상해 엔화를 지지한다", "translated"),
        ):
            translated, status = runner.translate_headline_to_korean(
                "BOJ May Support Yen With September Rate Hike",
                "The Wall Street Journal",
                "BOJ 9월 인상 전망·시장 기대",
                current,
            )
        self.assertEqual(status, "fidelity_fallback")
        self.assertRegex(translated, r"가능성|전망")

    def test_message_separates_source_translation_from_market_interpretation(self) -> None:
        current = dt.datetime(2026, 8, 19, 7, 0, tzinfo=dt.timezone.utc)
        item = self.item(
            "BOJ Has Chance to Support Yen With September Rate Hike",
            "The Wall Street Journal",
            "HSBC strategist says a September hike could support the yen.",
        )
        classified = runner.base.classify(item)
        self.assertIsNotNone(classified)
        title, body, payload = runner.base.build_message(
            [(classified, 1, ["Wall Street Journal"])],
            current,
        )
        self.assertIn("엔화 정책 촉매 알림", title)
        self.assertIn(
            "원문 번역: BOJ는 9월 금리 인상으로 엔화를 지지할 기회가 있다",
            body,
        )
        self.assertIn("확인 범위: 원문 헤드라인·Google News RSS 요약 기준", body)
        self.assertIn("원문 성격: 시장 전망·분석 — BOJ 공식 결정이나 확정 신호 아님", body)
        self.assertIn("시장 해석(원문 외 연결):", body)
        self.assertNotIn("헤드라인:", body)
        self.assertTrue(
            payload["items"][0]["source_translation_separated_from_market_interpretation"]
        )
        self.assertEqual(
            payload["items"][0]["evidence_scope"],
            "headline_and_google_news_rss_summary",
        )
        self.assertIn("full_text_rule", payload["fidelity_policy"])

    def test_bloomberg_record_intervention_amount_is_material_alert(self) -> None:
        item = self.item(
            "Japan Yen Intervention Hits Record $96 Billion in Past Month",
            "Bloomberg",
        )
        classified = runner.base.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, runner.INTERVENTION_SCALE_TOPIC)
        self.assertEqual(classified.material_score, 5)
        self.assertEqual(classified.source_group, "Bloomberg")

    def test_reuters_record_spending_wording_is_material_alert(self) -> None:
        item = self.item(
            "Japan spent record $96.5 billion to support yen over past month, ministry data shows",
            "Reuters",
        )
        classified = runner.base.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, runner.INTERVENTION_SCALE_TOPIC)
        self.assertEqual(classified.material_score, 5)

    def test_old_market_recap_without_scale_stays_suppressed(self) -> None:
        item = self.item(
            "Yen gives up nearly half of gains from joint US-Japan market intervention",
            "Financial Times",
        )
        self.assertIsNone(runner.base.classify(item))

    def test_official_mof_monthly_disclosure_is_collected_and_ranked_official(self) -> None:
        current = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc)
        index_html = '<a href="20260828.html">令和8年7月30日～令和8年8月26日</a>'
        page_html = '''<html><title>外国為替平衡操作の実施状況</title><body>
        外国為替平衡操作の実施状況（令和8年7月30日～令和8年8月26日）
        外国為替平衡操作額 15兆3,993億円
        </body></html>'''
        with mock.patch.object(runner.base, "fetch_text", side_effect=[(index_html, None), (page_html, None)]):
            item = runner._latest_mof_monthly_item(current)
        self.assertIsNotNone(item)
        self.assertEqual(item.source, "Japan Ministry of Finance")
        classified = runner.base.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, runner.INTERVENTION_SCALE_TOPIC)
        rank, groups = runner.base.corroboration_rank(classified, [classified])
        self.assertEqual(rank, 3)
        self.assertEqual(groups, ["Japan MOF"])

    def test_intervention_money_context_always_pairs_foreign_amount_with_krw(self) -> None:
        item = self.item(
            "Japan Yen Intervention Hits Record $96 Billion in Past Month",
            "Bloomberg",
            "Japan intervened by 15.3993 trillion yen over the period.",
        )
        quote = runner.JpyKrwQuote("2026-08-28", 1377.18, 161.50, 1377.18 / 161.50)
        lines = runner._money_context(item, quote)
        text = "\n".join(lines)
        self.assertIn("15조3,993억엔 (약", text)
        self.assertIn("96.0십억달러 (약", text)
        self.assertIn("원화 환산 기준", text)

    def test_scale_message_labels_period_total_not_new_same_day_intervention(self) -> None:
        current = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc)
        item = self.item(
            "Japan Yen Intervention Hits Record $96 Billion in Past Month",
            "Bloomberg",
            "Japan intervened by 15.3993 trillion yen over the period.",
        )
        classified = runner.base.classify(item)
        self.assertIsNotNone(classified)
        quote = runner.JpyKrwQuote("2026-08-28", 1377.18, 161.50, 1377.18 / 161.50)
        with mock.patch.object(runner, "latest_jpy_krw", return_value=quote):
            title, body, payload = runner.base.build_message(
                [(classified, 1, ["Bloomberg"])],
                current,
            )
        self.assertIn("개입 실적 촉매", title)
        self.assertIn("누적 집행 실적", body)
        self.assertIn("15조3,993억엔 (약", body)
        self.assertIn("96.0십억달러 (약", body)
        self.assertTrue(payload["items"][0]["krw_conversion"]["required"])


if __name__ == "__main__":
    unittest.main()

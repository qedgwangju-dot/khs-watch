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


if __name__ == "__main__":
    unittest.main()

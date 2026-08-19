from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()

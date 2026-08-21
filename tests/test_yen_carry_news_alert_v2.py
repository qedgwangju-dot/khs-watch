from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_news_alert_v2 as extension  # noqa: E402

carry = extension.base


class YenCarryTurbochargedCoverageTests(unittest.TestCase):
    def item(self, title: str, source: str = "CNBC", description: str = "") -> carry.base.NewsItem:
        return carry.base.NewsItem(
            title=title,
            link="https://www.cnbc.com/example",
            source=source,
            description=description,
            published=dt.datetime(2026, 8, 20, 11, 0, tzinfo=dt.timezone.utc),
        )

    def test_user_cnbc_turbocharged_headline_is_material_alert(self) -> None:
        classified = carry.classify(
            self.item("Japan's historic yen intervention has 'turbo-charged' the carry trade")
        )
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "엔캐리 재구축·재확산")
        self.assertEqual(classified.material_score, 4)
        self.assertEqual(classified.source_group, "CNBC")

    def test_korean_turbocharged_rendering_is_captured(self) -> None:
        classified = carry.classify(
            self.item(
                "일본의 역사적인 엔화 개입이 엔 캐리 트레이드 가속화 초래",
                source="씨엔비씨",
            )
        )
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "엔캐리 재구축·재확산")
        self.assertEqual(classified.source_group, "CNBC")

    def test_plain_intervention_afterstory_remains_ignored(self) -> None:
        classified = carry.classify(
            self.item("Yen gives up nearly half its gains after historic intervention")
        )
        self.assertIsNone(classified)

    def test_exact_query_is_installed(self) -> None:
        queries = {query for language, query in carry.RSS_QUERIES if language == "en"}
        self.assertIn('"turbo-charged" "carry trade" yen intervention', queries)


if __name__ == "__main__":
    unittest.main()

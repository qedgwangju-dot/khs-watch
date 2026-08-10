from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_policy_news_alert as news  # noqa: E402


class YenPolicyNewsAlertTests(unittest.TestCase):
    def item(
        self,
        title: str,
        source: str = "Kyodo News",
        description: str = "",
        minutes_ago: int = 10,
    ) -> news.NewsItem:
        current = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
        return news.NewsItem(
            title=title,
            link=f"https://example.com/{abs(hash(title))}",
            source=source,
            description=description,
            published=current - dt.timedelta(minutes=minutes_ago),
        )

    def test_user_example_is_single_source_material_alert(self) -> None:
        item = self.item(
            "BOJ September rate hike signal led U.S. to join yen intervention, Kyodo says"
        )
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "미국의 엔화 개입 참여·지원")
        self.assertEqual(classified.material_score, 5)
        rank, groups = news.corroboration_rank(classified, [classified])
        self.assertEqual(rank, 1)
        self.assertEqual(groups, ["Kyodo"])
        self.assertTrue(
            news.should_alert(
                classified,
                rank,
                {"seen_item_ids": [], "clusters": {}},
                dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc),
            )
        )

    def test_official_source_is_rank_three(self) -> None:
        item = self.item(
            "Bank of Japan signals faster rate hikes after yen weakness",
            source="Bank of Japan",
        )
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        rank, groups = news.corroboration_rank(classified, [classified])
        self.assertEqual(rank, 3)
        self.assertEqual(groups, ["BOJ"])

    def test_two_major_sources_upgrade_to_corroborated(self) -> None:
        first = news.classify(
            self.item("Japan and U.S. discuss joint yen intervention", source="Reuters")
        )
        second = news.classify(
            self.item("U.S. joins Japan in yen market intervention", source="Kyodo News")
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first.topic, second.topic)
        rank, groups = news.corroboration_rank(first, [first, second])
        self.assertEqual(rank, 2)
        self.assertEqual(set(groups), {"Reuters", "Kyodo"})

    def test_low_relevance_story_is_ignored(self) -> None:
        item = self.item("Japan automakers report strong quarterly sales", source="Reuters")
        self.assertIsNone(news.classify(item))

    def test_generic_single_source_hike_without_timing_is_suppressed(self) -> None:
        item = self.item("BOJ could raise rates again this year", source="Reuters")
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        rank, _groups = news.corroboration_rank(classified, [classified])
        self.assertEqual(classified.material_score, 2)
        self.assertFalse(
            news.should_alert(
                classified,
                rank,
                {"seen_item_ids": [], "clusters": {}},
                dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc),
            )
        )

    def test_same_topic_same_rank_is_suppressed_but_upgrade_realerts(self) -> None:
        current = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)
        item = self.item("BOJ September rate hike signal strengthens", source="Kyodo News")
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        state = {
            "seen_item_ids": [],
            "clusters": {
                news.topic_key(classified.topic): {
                    "rank": 1,
                    "material_score": classified.material_score,
                    "sent_epoch": (current - dt.timedelta(hours=1)).timestamp(),
                }
            },
        }
        self.assertFalse(news.should_alert(classified, 1, state, current))
        self.assertTrue(news.should_alert(classified, 2, state, current))

    def test_parse_google_news_rss(self) -> None:
        xml = """<?xml version='1.0' encoding='UTF-8'?>
        <rss><channel><item>
          <title>BOJ September rate hike signal - Reuters</title>
          <link>https://news.google.com/rss/articles/test</link>
          <pubDate>Mon, 10 Aug 2026 11:50:00 GMT</pubDate>
          <description>Bank of Japan and yen intervention context</description>
          <source url='https://reuters.com'>Reuters</source>
        </item></channel></rss>"""
        items = news.parse_rss(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "Reuters")
        self.assertEqual(items[0].published.tzinfo, dt.timezone.utc)

    def test_finalize_requires_telegram_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            state = root / "state.json"
            pending = root / "pending.json"
            confirmation = root / "confirm.json"
            pending.write_text(
                json.dumps({"seen_item_ids": ["x"], "clusters": {}}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(news, "STATE_PATH", state),
                mock.patch.object(news, "PENDING_PATH", pending),
                mock.patch.object(news, "CONFIRM_PATH", confirmation),
            ):
                self.assertFalse(news.finalize())
                self.assertFalse(state.exists())
                confirmation.write_text(
                    json.dumps({"status": "confirmed", "lane": "yen_policy_news"}),
                    encoding="utf-8",
                )
                self.assertTrue(news.finalize())
                self.assertTrue(state.exists())


if __name__ == "__main__":
    unittest.main()

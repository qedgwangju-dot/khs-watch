from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_policy_news_alert as news  # noqa: E402
import yen_policy_carry_extension as carry  # noqa: E402


class YenPolicyCarryExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        carry.install()

    def item(
        self,
        title: str,
        source: str = "Financial Times",
        description: str = "",
    ) -> news.NewsItem:
        return news.NewsItem(
            title=title,
            link="https://example.com/article",
            source=source,
            description=description,
            published=dt.datetime(2026, 8, 15, 7, 0, tzinfo=dt.timezone.utc),
        )

    def test_resumed_carry_trade_is_material_alert(self) -> None:
        item = self.item(
            "Traders are spoiling for a fight over the yen",
            description=(
                "Two weeks after joint intervention, traders are resuming significant selling of the yen. "
                "A resurgence of the carry trade is being driven by the wide interest-rate gap."
            ),
        )
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "엔캐리 재구축·엔화 숏 재개")
        self.assertEqual(classified.material_score, 4)
        rank, _groups = news.corroboration_rank(classified, [classified])
        self.assertEqual(rank, 1)
        self.assertTrue(
            news.should_alert(
                classified,
                rank,
                {"seen_item_ids": [], "clusters": {}},
                dt.datetime(2026, 8, 15, 8, 0, tzinfo=dt.timezone.utc),
            )
        )

    def test_intervention_half_gain_retracement_is_alerted(self) -> None:
        item = self.item(
            "Yen gives up nearly half of gains from joint US-Japan market intervention"
        )
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "개입 효과 약화·엔화 재약세")
        self.assertEqual(classified.material_score, 4)

    def test_small_post_intervention_move_is_still_ignored(self) -> None:
        item = self.item(
            "Yen slips slightly after joint intervention as traders wait for BOJ"
        )
        self.assertIsNone(news.classify(item))

    def test_large_japanese_overseas_asset_buying_is_alerted(self) -> None:
        item = self.item(
            "Japanese investors return to overseas assets after yen intervention",
            source="Reuters",
            description="Japanese investors made their largest foreign securities purchases in two years.",
        )
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "일본 자금 해외유출·캐리 연료 확대")
        self.assertEqual(classified.material_score, 3)

    def test_generic_carry_commentary_without_rebuild_is_not_alerted(self) -> None:
        item = self.item(
            "Why the yen carry trade remains important for global markets",
            description="The carry trade has existed for many years.",
        )
        self.assertIsNone(news.classify(item))

    def test_structural_alert_uses_policy_and_flow_title(self) -> None:
        item = self.item(
            "Yen carry trade resumes after intervention",
            description="Investors are rebuilding yen-funded positions.",
        )
        classified = news.classify(item)
        self.assertIsNotNone(classified)
        with mock.patch.object(
            news,
            "translate_headline_to_korean",
            return_value=("개입 이후 엔 캐리 트레이드가 다시 확대", "translated"),
        ):
            title, body, _payload = news.build_message(
                [(classified, 1, ["Financial Times"])],
                dt.datetime(2026, 8, 15, 8, 0, tzinfo=dt.timezone.utc),
            )
        self.assertIn("엔화 정책·수급 촉매 알림", title)
        self.assertIn("정책·수급·개입 뉴스 경보", body)
        self.assertIn("향후 엔고 시 청산 압력 확대", body)

    def test_extra_queries_cover_carry_and_overseas_flows(self) -> None:
        query_text = " ".join(query for _lang, query in news.RSS_QUERIES).lower()
        self.assertIn("carry trade", query_text)
        self.assertIn("overseas assets", query_text)


if __name__ == "__main__":
    unittest.main()

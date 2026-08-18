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

import yen_carry_news_alert as carry  # noqa: E402


class YenCarryNewsAlertTests(unittest.TestCase):
    def item(
        self,
        title: str,
        source: str = "Reuters",
        description: str = "",
    ) -> carry.base.NewsItem:
        return carry.base.NewsItem(
            title=title,
            link=f"https://example.com/{abs(hash(title))}",
            source=source,
            description=description,
            published=dt.datetime(2026, 8, 18, 4, 0, tzinfo=dt.timezone.utc),
        )

    def test_rebuilt_carry_trade_is_material_alert(self) -> None:
        classified = carry.classify(
            self.item(
                "Yen carry trades rebuild after intervention as investors return to dollar assets"
            )
        )
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "엔캐리 재구축·재확산")
        self.assertEqual(classified.material_score, 4)

    def test_intervention_fades_and_carry_returns_is_alert(self) -> None:
        classified = carry.classify(
            self.item(
                "Yen gives up intervention gains near 160 as carry trade resumes",
                source="Bloomberg",
            )
        )
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "엔캐리 재구축·재확산")

    def test_structural_rate_gap_keeps_carry_alive(self) -> None:
        classified = carry.classify(
            self.item(
                "Yen carry trade remains attractive as interest rate gap persists near 160 per dollar"
            )
        )
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "엔캐리 지속·재확산 압력")
        self.assertEqual(classified.material_score, 3)

    def test_japanese_outbound_flow_surge_is_alert(self) -> None:
        classified = carry.classify(
            self.item(
                "Japanese investors make largest in two years purchases of foreign securities after yen intervention"
            )
        )
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "일본 자금 해외투자 재확대·엔화 매도 압력")
        self.assertEqual(classified.material_score, 4)

    def test_plain_intervention_afterstory_is_still_ignored(self) -> None:
        classified = carry.classify(
            self.item(
                "Yen gives up nearly half of gains from joint US-Japan market intervention",
                source="Financial Times",
            )
        )
        self.assertIsNone(classified)

    def test_generic_carry_trade_explainer_is_ignored(self) -> None:
        classified = carry.classify(
            self.item("What is the yen carry trade and how does it work?", source="Reuters")
        )
        self.assertIsNone(classified)

    def test_rate_gap_plus_intervention_weakness_without_carry_is_alert(self) -> None:
        classified = carry.classify(
            self.item(
                "Yen weakens near 160 after intervention as interest-rate differential remains wide"
            )
        )
        self.assertIsNotNone(classified)
        self.assertEqual(classified.topic, "개입 효과 약화·금리차 기반 엔화 약세")

    def test_two_sources_upgrade_corroboration(self) -> None:
        first = carry.classify(
            self.item("Yen carry trade resumes after intervention", source="Reuters")
        )
        second = carry.classify(
            self.item("Investors rebuild yen carry trade after intervention", source="Bloomberg")
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        rank, groups = carry.base.corroboration_rank(first, [first, second])
        self.assertEqual(rank, 2)
        self.assertEqual(set(groups), {"Reuters", "Bloomberg"})

    def test_message_has_specific_carry_interpretation(self) -> None:
        current = dt.datetime(2026, 8, 18, 5, 0, tzinfo=dt.timezone.utc)
        classified = carry.classify(
            self.item("Yen carry trade resumes after intervention", source="Reuters")
        )
        self.assertIsNotNone(classified)
        with mock.patch.object(
            carry.base,
            "translate_headline_to_korean",
            return_value=("개입 이후 엔캐리 거래가 재개", "translated"),
        ):
            title, body, payload = carry.build_message(
                [(classified, 1, ["Reuters"])], current
            )
        self.assertIn("엔화 수급 촉매 알림", title)
        self.assertIn("USD/JPY", body)
        self.assertIn("CFTC", body)
        self.assertEqual(payload["items"][0]["source_group"], "Reuters")

    def test_finalize_requires_own_lane_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            state = root / "state.json"
            pending = root / "pending.json"
            confirm = root / "confirm.json"
            pending.write_text(
                json.dumps({"seen_item_ids": ["x"], "clusters": {}}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(carry, "STATE_PATH", state),
                mock.patch.object(carry, "PENDING_PATH", pending),
                mock.patch.object(carry, "CONFIRM_PATH", confirm),
            ):
                self.assertFalse(carry.finalize())
                confirm.write_text(
                    json.dumps({"status": "confirmed", "lane": "yen_carry_news"}),
                    encoding="utf-8",
                )
                self.assertTrue(carry.finalize())
                self.assertTrue(state.exists())


if __name__ == "__main__":
    unittest.main()

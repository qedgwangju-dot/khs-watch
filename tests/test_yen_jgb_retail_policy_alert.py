from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_jgb_retail_policy_alert as alert  # noqa: E402


class JgbRetailTaxPolicyAlertTests(unittest.TestCase):
    def item(self, title: str, source: str = "Reuters", description: str = "") -> alert.Item:
        return alert.Item(
            title=title,
            link="https://example.com/a",
            source=source,
            description=description,
            published=dt.datetime(2026, 8, 25, 3, 30, tzinfo=dt.timezone.utc),
        )

    def test_user_reuters_example_is_alertable_review(self) -> None:
        item = self.item(
            "Japan will carefully consider tax incentives for retail JGB investors, minister says",
            description="Finance Minister Satsuki Katayama says making JGBs for retail investors more attractive is important and will discuss tax reform with relevant parties.",
        )
        result = alert.classify(item)
        self.assertEqual(result, ("일본 국채 수요 확충·개인투자자 세제지원 검토", 3))
        self.assertEqual(alert.source_level(item), 1)
        self.assertTrue(
            alert.should_send(
                item,
                result[0],
                result[1],
                1,
                {},
                dt.datetime(2026, 8, 25, 4, 0, tzinfo=dt.timezone.utc),
            )
        )

    def test_japanese_review_wording(self) -> None:
        item = self.item(
            "片山財務相、個人向け国債の税制優遇を慎重に検討",
            source="Reuters",
            description="個人投資家向け国債の魅力向上について与党と議論する",
        )
        self.assertEqual(alert.classify(item)[0], "일본 국채 수요 확충·개인투자자 세제지원 검토")

    def test_korean_review_wording(self) -> None:
        item = self.item(
            "日 정부, 개인 국채 투자자 대상 세제 혜택 신중히 검토할 것",
            description="가타야마 재무상은 개인 투자자용 일본 국채의 매력을 높이는 방안을 여당과 논의할 계획이라고 밝혔다",
        )
        self.assertEqual(alert.classify(item)[0], "일본 국채 수요 확충·개인투자자 세제지원 검토")

    def test_decision_realerts_as_higher_materiality(self) -> None:
        item = self.item(
            "Japan approves tax incentives for retail investors buying JGBs",
            description="Government decided to include retail JGB tax benefits in tax reform.",
        )
        topic, score = alert.classify(item)
        self.assertEqual(topic, "일본 국채 개인투자 세제지원 확정·구체화")
        self.assertEqual(score, 5)
        state = {"seen": [], "cluster": {"score": 3, "level": 1, "sent_epoch": dt.datetime(2026, 8, 25, 3, 0, tzinfo=dt.timezone.utc).timestamp()}}
        self.assertTrue(alert.should_send(item, topic, score, 1, state, dt.datetime(2026, 8, 25, 4, 0, tzinfo=dt.timezone.utc)))

    def test_generic_jgb_yield_story_is_not_alerted(self) -> None:
        item = self.item("Japan 10-year JGB yield rises toward 3%", description="Retail investors watch higher yields")
        self.assertIsNone(alert.classify(item))

    def test_tax_story_without_retail_jgb_is_not_alerted(self) -> None:
        item = self.item("Japan discusses corporate tax reform", description="Government considers investment incentives")
        self.assertIsNone(alert.classify(item))

    def test_impact_lines_do_not_force_yen_direction_or_company_earnings(self) -> None:
        lines = "\n".join(alert.impact_lines("일본 국채 수요 확충·개인투자자 세제지원 검토"))
        self.assertIn("방향 단정 금지", lines)
        self.assertIn("수급", lines)
        self.assertIn("할인율", lines)
        self.assertIn("시간표", lines)
        self.assertNotIn("수출주 부담", lines)
        self.assertNotIn("돈 버는 능력", lines)

    def test_korean_google_news_locale(self) -> None:
        url = alert.google_url("ko", "일본 국채 개인투자자 세제 개편")
        self.assertIn("ceid=KR%3Ako", url)
        self.assertIn("gl=KR", url)


if __name__ == "__main__":
    unittest.main()

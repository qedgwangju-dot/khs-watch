from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_policy_news_alert as base
import yen_policy_news_alert_runner as runner
import yen_policy_news_event_guard as guard

RELEASE = guard.FOMC_RELEASE_UTC
FULL_MINUTES = """
The joint U.S.–Japan intervention to support the yen in late July directly contributed.
The Desk, acting purely as fiscal agent for the U.S. Treasury, intervened
in the currency market using U.S. Treasury funds; the System Open Market
Account portfolio was not involved.
"""


def item(title: str, source: str = "Bloomberg.com", link: str = "https://example.org/story"):
    return base.NewsItem(
        title=title,
        link=link,
        source=source,
        description="",
        published=RELEASE + dt.timedelta(hours=1),
    )


class YenHistoricalFundingSafety(unittest.TestCase):
    def test_bloomberg_headline_is_past_funding_not_fresh_joint_action(self):
        x = item("Fed Used Treasury Funds to Support Yen in Joint Intervention - Bloomberg.com")
        out = base.classify(x)
        self.assertIsNotNone(out)
        self.assertEqual(out.topic, guard.FUNDING_TOPIC)
        self.assertEqual(out.material_score, 3)
        translated, status = base.translate_headline_to_korean(x.title, x.source, out.topic, RELEASE)
        self.assertIn("미 재무부 자금", translated)
        self.assertIn("연준 자체 자금", translated)
        self.assertNotIn("국채 자금", translated)
        self.assertEqual(status, "official_fidelity_translation")

    def test_retrospective_story_not_mislabeled_as_fresh_intervention(self):
        x = item("In July Japan and US joint intervention supported the yen")
        self.assertIsNone(base.classify(x))

    def test_new_joint_intervention_remains_a_live_signal(self):
        x = item("Japan and US join joint yen intervention again today")
        out = base.classify(x)
        self.assertIsNotNone(out)
        self.assertNotEqual(out.topic, guard.FUNDING_TOPIC)

    def test_official_minutes_generate_distinct_event_and_correct_message(self):
        now = RELEASE + dt.timedelta(hours=8)
        guard_body = base.collect_items
        # Avoid any outside network: mock each source used by the existing collector.
        with patch.object(runner, "_original_collect_items", return_value=([], [])), \
             patch.object(runner, "_latest_mof_monthly_item", return_value=None), \
             patch.object(base, "read_state", return_value={"seen_item_ids": [], "clusters": {}}), \
             patch.object(base, "fetch_text", return_value=(FULL_MINUTES, None)):
            items, errors = base.collect_items(now)
            self.assertEqual(errors, [])
            official = [x for x in items if x.link == guard.FOMC_MINUTES_URL]
            self.assertEqual(len(official), 1)
            classified = base.classify(official[0])
            self.assertEqual(classified.topic, guard.FUNDING_TOPIC)
            self.assertEqual(classified.source_level, 3)
            selected = [(classified, 3, [classified.source_group])]
            title, body, payload = base.build_message(selected, now)
            self.assertIn("공식 확인", title)
            self.assertIn("10월 신규 공동개입 발생을 의미하지 않음", body)
            self.assertIn("연준 자체 자금", body)
            self.assertIn("뉴욕연방준비은행", body)
            self.assertNotIn("실개입·공동개입 신호", body)
            self.assertNotIn("엔화 숏커버·엔캐리 청산 가능성을 가장 높게 경계", body)
            self.assertFalse(payload["fresh_intervention"])
            self.assertEqual(payload["items"][0]["link"], guard.FOMC_MINUTES_URL)
            pending = base.pending_state({"seen_item_ids": [], "clusters": {}}, selected, now)
            self.assertIn(guard.FUNDING_EVENT_KEY, pending["verified_event_keys"])
            self.assertFalse(base.should_alert(classified, 3, pending, now + dt.timedelta(hours=1)))

    def test_no_fake_official_confirmation_after_event_already_delivered(self):
        now = RELEASE + dt.timedelta(hours=8)
        with patch.object(runner, "_original_collect_items", return_value=([], [])), \
             patch.object(runner, "_latest_mof_monthly_item", return_value=None), \
             patch.object(base, "read_state", return_value={"verified_event_keys": [guard.FUNDING_EVENT_KEY]}):
            items, _ = base.collect_items(now)
        self.assertFalse(any(x.link == guard.FOMC_MINUTES_URL for x in items))

    def test_urgent_live_alert_source_remains_distinct(self):
        x = item("Fed Used Treasury Funds to Support Yen in Joint Intervention")
        classification = base.classify(x)
        self.assertEqual(classification.topic, guard.FUNDING_TOPIC)
        state = {"seen_item_ids": [x.item_id], "clusters": {}}
        self.assertFalse(base.should_alert(classification, 1, state, RELEASE + dt.timedelta(hours=2)))


if __name__ == "__main__":
    unittest.main()

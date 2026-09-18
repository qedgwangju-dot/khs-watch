import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from boj_policy_lead_alert import (
    Item,
    classify,
    extract_rate,
    extract_vote,
    signal_signature,
    should_alert,
)

KST = ZoneInfo("Asia/Seoul")


class BojPolicyPathAlertTests(unittest.TestCase):
    def mk(self, title, desc="", source="Reuters", hour=0):
        return Item(
            title=title,
            source=source,
            link="https://example.com",
            published=dt.datetime(2026, 9, 18, 12 + hour, tzinfo=KST),
            description=desc,
        )

    def test_expected_25bp_with_conditional_guidance_stays_yellow(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The BOJ said it would continue to raise interest rates if the outlook is realised, "
                "while the timing and pace will depend on economic and price risks. "
                "Financial conditions will remain accommodative.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.event_type, "decision")
        self.assertEqual(signal.level, 1)
        self.assertAlmostEqual(signal.policy_rate, 1.25)
        self.assertEqual(signal.hike_bp, 25)
        self.assertTrue(signal.further_hikes)
        self.assertTrue(signal.conditional_pace)
        self.assertTrue(signal.accommodative)

    def test_faster_next_meeting_signal_is_orange(self):
        signal = classify(
            self.mk(
                "BOJ Governor Ueda says next meeting could bring another rate hike - Reuters",
                "The central bank may raise rates faster if underlying inflation and upside risks persist.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.event_type, "press_conference")
        self.assertEqual(signal.level, 2)

    def test_surprise_half_point_is_red(self):
        signal = classify(
            self.mk(
                "BOJ raises policy rate to 1.50% in 50 basis-point move - Reuters",
                "The surprise half-point hike was approved at the policy meeting.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.level, 3)

    def test_pause_signal_is_green(self):
        signal = classify(
            self.mk(
                "BOJ Governor Ueda says no rush for further rate hike - Reuters",
                "The bank can wait and see before raising rates again.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.level, 0)

    def test_vote_parser(self):
        self.assertEqual(extract_vote("The decision passed by a 7-2 vote."), (7, 2))
        self.assertEqual(extract_vote("No vote count was provided."), (None, None))

    def test_rate_parser(self):
        self.assertEqual(extract_rate("The policy rate was raised to 1.25%."), 1.25)

    def test_event_type_change_realerts(self):
        decision = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The timing and pace will depend on the outlook.",
            )
        )
        conference = classify(
            self.mk(
                "BOJ Governor Ueda press conference focuses on rate path - Reuters",
                "The timing and pace will depend on the outlook.",
                hour=1,
            )
        )
        state = {
            "last_signal_key": decision.key,
            "last_alert_at_kst": "2026-09-18T12:10:00+09:00",
            "signature": signal_signature(decision),
        }
        ok, reason = should_alert(
            conference,
            state,
            dt.datetime(2026, 9, 18, 13, 5, tzinfo=KST),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "새 공식 정책 이벤트")

    def test_same_signature_is_suppressed_inside_cooldown(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The timing and pace will depend on the outlook.",
            )
        )
        state = {
            "last_signal_key": "different-key",
            "last_alert_at_kst": "2026-09-18T12:10:00+09:00",
            "signature": signal_signature(signal),
        }
        ok, reason = should_alert(
            signal,
            state,
            dt.datetime(2026, 9, 18, 13, 0, tzinfo=KST),
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "정책경로 실질 변화 없음")

    def test_official_statement_is_decision(self):
        signal = classify(
            self.mk(
                "Statement on Monetary Policy",
                source="Bank of Japan",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.event_type, "decision")


if __name__ == "__main__":
    unittest.main()

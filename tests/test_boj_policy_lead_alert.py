import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from boj_policy_lead_alert import Item, classify, prob, should

KST = ZoneInfo("Asia/Seoul")


class BojPolicyLeadAlertTests(unittest.TestCase):
    def mk(self, title, desc="", source="Reuters", hour=0):
        return Item(
            title=title,
            source=source,
            link="https://example.com",
            published=dt.datetime(2026, 9, 3, 12 + hour, tzinfo=KST),
            description=desc,
        )

    def test_reuters_poll_is_stage_1(self):
        signal = classify(self.mk("BOJ to speed up its tightening campaign, raise key rate to 1.25% in September - Reuters"))
        self.assertEqual(signal.stage, 1)
        self.assertEqual(signal.route, "reuters_poll")
        self.assertAlmostEqual(signal.target_rate, 1.25)

    def test_probability_70_or_more_is_stage_2(self):
        signal = classify(
            self.mk(
                "Yen jumps on BOJ hike bets, dollar slips - Reuters",
                "Markets now price a 75% probability of a 25-basis-point hike.",
            )
        )
        self.assertEqual(signal.stage, 2)
        self.assertEqual(signal.route, "market_probability")
        self.assertEqual(signal.hike_bp, 25)
        self.assertEqual(signal.probability, 75)

    def test_boj_official_commentary_report_is_stage_2(self):
        signal = classify(self.mk("BOJ chief signals chance of September rate hike, debate on price risks - Reuters"))
        self.assertEqual(signal.stage, 2)
        self.assertEqual(signal.route, "official_commentary")

    def test_untrusted_source_is_ignored(self):
        self.assertIsNone(classify(self.mk("BOJ rate hike likely", source="Random Blog")))

    def test_probability_needs_market_context(self):
        self.assertEqual(prob("markets price a 75% probability of a hike"), 75)
        self.assertIsNone(prob("inflation rose 75%"))

    def test_stage_escalation_realerts(self):
        signal = classify(
            self.mk(
                "Yen jumps on BOJ hike bets - Reuters",
                "Markets price a 75% probability of a 25 basis-point hike.",
            )
        )
        state = {
            "stage": 1,
            "route": "reuters_poll",
            "last_alert_at_kst": "2026-09-03T10:00:00+09:00",
            "last_signal_key": "old",
        }
        ok, reason = should(signal, state, dt.datetime(2026, 9, 3, 12, 5, tzinfo=KST))
        self.assertTrue(ok)
        self.assertEqual(reason, "정책 경보 단계 상승")


if __name__ == "__main__":
    unittest.main()

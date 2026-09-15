import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("clarity_negotiation_watch", ROOT / "scripts" / "clarity_negotiation_watch.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityNegotiationWatchTest(unittest.TestCase):
    def test_democratic_counteroffer_sent_is_state_change(self):
        text = "Senate Democrats sent a counteroffer to Republicans on the CLARITY Act late Monday"
        self.assertEqual(MOD.classify_signal(text), "dem_counteroffer_sent")

    def test_gop_rejection_is_stronger_than_counteroffer_sent(self):
        text = "Republicans rejected the Democratic counteroffer on the CLARITY Act after it was delivered"
        self.assertEqual(MOD.classify_signal(text), "gop_rejected_dem_counteroffer")
        self.assertGreater(MOD.event_rank("gop_rejected_dem_counteroffer"), MOD.event_rank("dem_counteroffer_sent"))

    def test_generic_rejection_without_counteroffer_is_not_mislabeled(self):
        text = "Republicans reject criticism and say the CLARITY Act is ready for a vote"
        self.assertIsNone(MOD.classify_signal(text))

    def test_article_is_evidence_not_monitoring_unit(self):
        event = MOD.build_event("dem_counteroffer_sent", {
            "url": "https://example.com/story",
            "pubDate": "Tue, 15 Sep 2026 04:09:00 GMT",
        }, "CoinDesk")
        self.assertEqual(event["monitoring_unit"], "event_state_change")
        self.assertIn("역제안", event["title"])


if __name__ == "__main__":
    unittest.main()

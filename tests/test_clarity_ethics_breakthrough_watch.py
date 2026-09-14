import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_ethics_breakthrough_watch", ROOT / "scripts" / "clarity_ethics_breakthrough_watch.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityEthicsBreakthroughWatchTest(unittest.TestCase):
    def test_ap_trump_ethics_agreement_is_detected(self):
        signal = (
            "Trump agrees to new bipartisan ethics provision in massive crypto bill. "
            "The CLARITY Act ethics compromise was negotiated by Tillis and Gallego."
        )
        self.assertTrue(MOD.is_ethics_breakthrough(signal))

    def test_generic_ethics_criticism_is_not_breakthrough(self):
        signal = "Senators criticize the CLARITY Act ethics language and Trump crypto conflicts."
        self.assertFalse(MOD.is_ethics_breakthrough(signal))

    def test_ap_event_is_cautious_specific_and_event_based(self):
        item = {
            "title": "Trump agrees to new bipartisan ethics provision in massive crypto bill, GOP aide says",
            "description": "CLARITY Act Tillis Gallego ethics compromise",
            "url": "https://news.google.com/example",
            "pubDate": "Mon, 14 Sep 2026 01:00:00 GMT",
            "source": "AP News",
        }
        event = MOD.event_from(item, "Associated Press", evidence_sources=["Associated Press", "Reuters"])
        self.assertIn("약 80%", event["detail"])
        self.assertIn("주 검찰총장", event["detail"])
        self.assertIn("블라인드 트러스트", event["detail"])
        self.assertIn("최종 조항 확정은 아닙니다", event["detail"])
        self.assertEqual(event["url"], MOD.AP_DIRECT_URL)
        self.assertEqual(event["monitoring_unit"], "event_state_change")
        self.assertEqual(event["evidence_sources"], ["Associated Press", "Reuters"])

    def test_ethics_signature_is_not_article_headline_dependent(self):
        first = MOD.semantic_signature()
        second = MOD.semantic_signature()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

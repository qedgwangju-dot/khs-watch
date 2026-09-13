import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_policy_pressure_watch", ROOT / "scripts" / "clarity_policy_pressure_watch.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityPolicyPressureWatchTest(unittest.TestCase):
    def test_bessent_alert_uses_correct_korean_particle(self):
        item = {
            "title": "Scott Bessent to Senate: Failure to Pass CLARITY Act Risks Sending Troubling Signal to Allies and Adversaries",
            "description": "Bessent urges senators to remain at the negotiating table and advance the CLARITY Act.",
            "url": "https://news.google.com/example",
            "pubDate": "Thu, 10 Sep 2026 04:18:00 GMT",
            "source": "Benzinga",
            "source_url": "https://www.benzinga.com",
            "matched_query": '"CLARITY Act" Bessent',
        }
        signal = f"{item['title']} {item['description']}"
        with mock.patch.object(MOD, "resolve_original_url", return_value="https://example.com/source"):
            event = MOD.korean_event(
                item,
                "Bessent 재무장관",
                "행정부·핵심 당사자 통과 촉구",
                "Benzinga",
                signal,
            )
        detail = event["detail"]
        self.assertIn("Bessent 재무장관이 CLARITY 법안", detail)
        self.assertNotIn("Bessent 재무장관가", detail)
        self.assertNotIn("이(가)", detail)

    def test_bloomberg_law_is_higher_tier_than_benzinga(self):
        self.assertEqual(MOD.source_tier("Bloomberg Law"), (1, "Bloomberg Law"))
        self.assertEqual(MOD.source_tier("Benzinga"), (2, "Benzinga"))


if __name__ == "__main__":
    unittest.main()

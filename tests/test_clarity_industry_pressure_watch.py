import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_industry_pressure_watch", ROOT / "scripts" / "clarity_industry_pressure_watch.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityIndustryPressureWatchTest(unittest.TestCase):
    def test_vangrack_is_recognized_as_coinbase_industry_actor(self):
        actor, company = MOD.extract_actor(
            "Coinbase Vice Chair Ryan VanGrack says it is time to stop talking and start voting on the CLARITY Act"
        )
        self.assertEqual(actor, "Coinbase 부회장 Ryan VanGrack")
        self.assertEqual(company, "Coinbase")

    def test_bloomberg_is_tier1_but_tokenpost_is_discovery_only(self):
        self.assertEqual(MOD.source_tier("Bloomberg")[0], 1)
        self.assertEqual(MOD.source_tier("TokenPost")[0], 3)

    def test_generated_event_is_separate_from_official_change(self):
        item = {
            "title": "Coinbase Vice Chair Ryan VanGrack Talks CLARITY Act",
            "description": "It is time to stop talking and start voting. Tokenization will continue whether Congress acts or not.",
            "url": "https://example.com",
            "pubDate": "Tue, 08 Sep 2026 16:00:00 GMT",
            "source": "Bloomberg",
        }
        event = MOD.make_event(
            item,
            "Coinbase 부회장 Ryan VanGrack",
            "Coinbase",
            "Bloomberg",
            item["title"] + " " + item["description"],
        )
        self.assertEqual(event["event_type"], "핵심 사업자·업계 표결 촉구")
        self.assertTrue(event["mobility_warning"])
        self.assertIn("정부의 공식 입법 조치와는 구분", event["detail"])


if __name__ == "__main__":
    unittest.main()

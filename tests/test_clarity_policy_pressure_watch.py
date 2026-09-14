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

    def test_reworded_articles_map_to_same_policy_event(self):
        signal_a = "Bessent urges Senate to pass CLARITY Act, warning of national security risks to allies and adversaries."
        signal_b = "Treasury Secretary Bessent says failure on the CLARITY Act sends a troubling signal to allies; national security is at stake."
        event_type = "행정부·핵심 당사자 통과 촉구"
        self.assertEqual(MOD.event_subtype(signal_a, event_type), "national_security_pressure")
        self.assertEqual(MOD.event_subtype(signal_b, event_type), "national_security_pressure")
        self.assertEqual(
            MOD.semantic_signature("Bessent 재무장관", event_type, signal_a),
            MOD.semantic_signature("Bessent 재무장관", event_type, signal_b),
        )

    def test_industry_copy_uses_actor_side_not_awkward_particle(self):
        item = {
            "title": "Coinbase Vice Chair Ryan VanGrack says it is time to start voting on the CLARITY Act",
            "description": "Ryan VanGrack urges the Senate to start voting on the CLARITY Act.",
            "url": "https://news.google.com/example",
            "pubDate": "Tue, 08 Sep 2026 14:00:00 GMT",
            "source": "Bloomberg",
            "matched_query": '"CLARITY Act" "Ryan VanGrack"',
        }
        signal = f"{item['title']} {item['description']}"
        with mock.patch.object(MOD, "resolve_original_url", return_value="https://example.com/source"):
            event = MOD.korean_event(item, "Coinbase 부회장 Ryan VanGrack", "핵심 사업자·업계 표결 촉구", "Bloomberg", signal)
        self.assertIn("Ryan VanGrack 측은 상원에", event["detail"])
        self.assertNotIn("이(가)", event["detail"])

    def test_final_draft_release_is_text_change_not_trump_ethics_risk(self):
        title = "Senate Republicans release 'final' Clarity Act draft as Trump accepts most ethics provisions"
        signal = title + " The revised draft incorporates most ethics provisions before the Senate vote."
        self.assertTrue(MOD.is_text_release_state(signal))
        event_type = "법안 문안 공개·핵심 수정 — 신뢰매체 확인"
        self.assertEqual(MOD.event_subtype(signal, event_type), "senate_revised_draft_release")
        item = {
            "title": title,
            "description": "The revised draft incorporates most ethics provisions before the Senate vote.",
            "url": "https://news.google.com/example",
            "pubDate": "Mon, 14 Sep 2026 04:24:37 GMT",
            "source": "The Block",
        }
        with mock.patch.object(MOD, "resolve_original_url", return_value="https://example.com/source"):
            event = MOD.korean_event(item, "상원 공화당 협상팀", event_type, "The Block", signal)
        self.assertIn("최신 초안 공개", event["title"])
        self.assertNotIn("Trump 대통령, CLARITY 법안 처리·통과를 의회에 촉구", event["title"])
        self.assertTrue(event["text_release"])
        self.assertIn("공식 원문", event["verification_status"])
        self.assertIn("법안 문안 자체가 바뀐 상태 변화", event["detail"])

    def test_reworded_draft_release_articles_share_semantic_signature(self):
        event_type = "법안 문안 공개·핵심 수정 — 신뢰매체 확인"
        a = "Senate Republicans release final CLARITY Act draft before vote"
        b = "Republican senators unveil revised CLARITY Act text ahead of cloture"
        self.assertTrue(MOD.is_text_release_state(a))
        self.assertTrue(MOD.is_text_release_state(b))
        self.assertEqual(
            MOD.semantic_signature("상원 공화당 협상팀", event_type, a),
            MOD.semantic_signature("상원 공화당 협상팀", event_type, b),
        )


if __name__ == "__main__":
    unittest.main()

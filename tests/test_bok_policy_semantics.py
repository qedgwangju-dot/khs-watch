#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bok_rate_signal_upgrade_v3 import policy_flags, event_score
from bok_mpc_watch_correct import parse_statement_correct, build_alert_correct
from bok_mpc_watch_final import _main_direction, parser_only_enrichment


class PolicySemanticsTests(unittest.TestCase):
    def test_k_shaped_household_inflation(self):
        text = "신현송 총재: 한국 경제 K자형 양극화 뚜렷, 저소득층에 인플레이션 피해 집중"
        self.assertTrue(policy_flags(text)["k_shaped_low_income"])

    def test_ai_middle_east_is_inflation_not_decided_hike(self):
        text = "신현송 총재: AI 호황과 중동 전쟁이 함께 물가 상승 압력"
        flags = policy_flags(text)
        self.assertTrue(flags["ai_war_inflation"])
        self.assertFalse(flags["next_meeting_hawk"])

    def test_fvi_leverage_and_investment_outlook(self):
        flags = policy_flags("금융취약성지수 FVI는 46, 레버리지 선제 관리는 중요하다")
        self.assertTrue(flags["fvi_leverage"])
        self.assertFalse(flags["next_meeting_hawk"])
        self.assertTrue(policy_flags("AI 투자 3~4년 1조달러 전망")["ai_investment_duration"])

    def test_no_hike_from_fvi_or_k_shape_alone(self):
        flags = policy_flags("K자형 경제, 저소득층 물가 부담. FVI 46 금융취약성 레버리지")
        self.assertFalse(flags["next_meeting_hawk"])
        self.assertLessEqual(event_score(flags), 1)

    def test_background_hike_mention_is_not_a_direct_request(self):
        flags = policy_flags("신현송 총재는 물가를 낮추겠다고 밝혔다. 이전의 추가 인상 기대가 언급됐다.")
        self.assertFalse(flags["hike_needed"])

    def test_reclassification_same_day_does_not_send_duplicate(self):
        from bok_rate_signal_upgrade_v3 import is_new_policy_event
        before = {"speaker": "신현송", "date": "2026-10-14", "flags": {"k_shaped_low_income": True}}
        after = {"speaker": "신현송", "date": "2026-10-14", "flags": {"k_shaped_low_income": True, "ai_war_inflation": True}}
        self.assertFalse(is_new_policy_event(after, before))
        self.assertTrue(is_new_policy_event(
            {"speaker": "신현송", "date": "2026-10-14", "flags": {"next_meeting_hawk": True}}, before
        ))
        self.assertTrue(is_new_policy_event(
            {"speaker": "신현송", "date": "2026-10-15", "flags": {"ai_war_inflation": True}}, before
        ))

    def test_october_hold_and_qualitative_forecasts(self):
        document = {
            "title": "통화정책방향(2026.10.22)",
            "url": "https://www.bok.or.kr/portal/bbs/P0000559/view.do?nttId=99999999",
            "hash": "fixture-only",
            "text": (
                "금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 "
                "현재의 3.00% 수준에서 유지하여 통화정책을 운용하기로 하였다. "
                "금년 및 내년 성장률은 지난 8월 전망치(각각 3.3%, 2.9%)를 상당폭 상회할 것이다. "
                "금년 소비자물가 및 근원물가 상승률은 8월 전망치에 대체로 부합하겠으나, "
                "내년에는 기존 전망치(2.3%, 2.5%)를 상회할 것이다. "
                "수도권 주택가격의 오름세는 다시 확대되었다. "
                "금번 기준금리 동결 결정에 대해서는 금융통화위원 7명 모두 찬성하였다. "
                "별도 시장금리 3.75%는 한국은행 기준금리가 아니다."
            ),
        }
        parsed = parse_statement_correct(document)
        self.assertEqual((parsed["rate_from"], parsed["rate_to"]), (3.0, 3.0))
        self.assertEqual(_main_direction(parsed), "동결")
        self.assertEqual(parsed["vote_for"], 7)
        self.assertNotIn("growth_this", parsed)
        self.assertNotIn("cpi_next", parsed)
        self.assertTrue(parsed["flags"]["growth_above_aug"])
        self.assertTrue(parsed["flags"]["inflation_next_up"])
        self.assertTrue(parsed["flags"]["housing_reaccelerating"])
        alert = build_alert_correct(parsed, None, False)
        self.assertIn("3%", alert)  # 텔레그램의 기존 금리 표기는 소수점 .00을 생략
        self.assertIn("상당폭 상회", alert)
        self.assertIn("7명", alert)
        self.assertIn("새 확정 수치 미제시", alert)

    def test_parser_upgrade_does_not_resend_same_policy_document(self):
        before = {
            "title": "통화정책방향(2026.10.22)",
            "url": "https://www.bok.or.kr/portal/bbs/P0000559/view.do?nttId=11065823",
            "parser_version": 3,
            "rate_from": 3.0, "rate_to": 3.0, "vote_for": 7,
            "flags": {"timing_speed": True, "housing": True},
        }
        after = dict(before)
        after.update(parser_version=4, hash="changed-dynamic-web-content")
        after["flags"] = {
            "timing_speed": True, "housing": True,
            "growth_above_aug": True,
        }
        self.assertTrue(parser_only_enrichment(before, after, None, None))
        self.assertFalse(parser_only_enrichment({**before, "vote_for": 6}, after, None, None))
        self.assertFalse(parser_only_enrichment(before, {**after, "rate_to": 3.25}, None, None))
        self.assertFalse(parser_only_enrichment(
            before, {**after, "flags": {**after["flags"], "unexpected_new_signal": True}},
            None, None,
        ))

    def test_growth_qualitative_wording_variants(self):
        document = {
            "title": "통화정책방향(2026.10.22)",
            "url": "https://www.bok.or.kr/portal/bbs/P0000559/view.do?nttId=99999999",
            "hash": "growth-variant",
            "text": (
                "금융통화위원회는 기준금리를 현재의 3.00% 수준에서 유지한다. "
                "올해와 내년의 경제성장률 전망에 관한 판단은 8월 경제전망보다 "
                "상당 폭 상회할 것으로 보이며 향후 여건 변화에 유의한다."
            ),
        }
        p = parse_statement_correct(document)
        self.assertEqual(p["growth_outlook"], "8월 전망 상당폭 상회")
        self.assertEqual(p["growth_reference_this"], 3.3)
        self.assertEqual(p["growth_reference_next"], 2.9)

    def test_august_baseline_does_not_gain_false_new_event_flags(self):
        document = {
            "title": "통화정책방향(2026.8.27)",
            "url": "https://www.bok.or.kr/portal/bbs/P0000559/view.do?nttId=11064191",
            "hash": "aug-fixture",
            "text": "금융통화위원회는 기준금리를 2.75%에서 3.00%로 상향 조정하였다.",
        }
        parsed = parse_statement_correct(document)
        self.assertEqual((parsed["rate_from"], parsed["rate_to"]), (2.75, 3.0))
        for key in ("growth_above_aug", "inflation_next_up", "housing_reaccelerating"):
            self.assertNotIn(key, parsed["flags"])


if __name__ == "__main__":
    unittest.main()

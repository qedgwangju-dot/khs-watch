#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bok_rate_signal_upgrade_v3 import policy_flags, event_score


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


if __name__ == "__main__":
    unittest.main()

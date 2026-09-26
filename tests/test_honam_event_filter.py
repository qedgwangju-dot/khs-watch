#!/usr/bin/env python3
import unittest

from scripts.honam_event_filter import _is_known_baseline_only, _is_proposal_only


class HonamEventFilterRegressionTest(unittest.TestCase):
    def test_250manpyeong_entry_agreement_plan_is_rehash(self):
        item = {
            "title": "전남광주, 반도체 국가산단 250만평 조성…삼성·SK하이닉스 입주 협약도 추진",
            "description": "기업과 10월 입주 협약을 맺고 투자를 구체화한다는 계획",
        }
        self.assertTrue(_is_known_baseline_only(item))

    def test_roadmap_numbers_are_rehash(self):
        item = {
            "title": "호남 반도체 2030년 6월 첫 양산",
            "description": "63만평 우선 개발, 2027년 상반기 착공, 전력 3.1GW에서 6.3GW로 단계 확대, 2028년 12월 1단계 공급",
        }
        self.assertTrue(_is_known_baseline_only(item))

    def test_signed_anchor_agreement_is_real_upgrade(self):
        item = {
            "title": "삼성전자·SK하이닉스, 호남 반도체 국가산단 입주 협약 체결",
            "description": "양사가 입주 협약을 체결했다",
        }
        self.assertFalse(_is_known_baseline_only(item))

    def test_actual_construction_start_is_real_upgrade(self):
        item = {
            "title": "호남 반도체 국가산단 첫 삽…63만평 우선구역 공사 시작",
            "description": "공사에 착수했다",
        }
        self.assertFalse(_is_known_baseline_only(item))

    def test_schedule_change_is_real_upgrade(self):
        item = {
            "title": "호남 반도체 1단계 전력 공급 일정 변경",
            "description": "2028년 12월 목표가 연기 확정됐다",
        }
        self.assertFalse(_is_known_baseline_only(item))

    def test_proposal_only_still_suppressed(self):
        item = {
            "title": "시의원, 호남 반도체 배후도시 확대 제안",
            "description": "5분 자유발언에서 정책 제안",
        }
        self.assertTrue(_is_proposal_only(item))


if __name__ == "__main__":
    unittest.main()

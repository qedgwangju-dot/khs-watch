#!/usr/bin/env python3
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.honam_event_filter import (
    _action_level,
    _event_family,
    _is_known_baseline_only,
    _is_proposal_only,
    _merge_group,
)
from scripts.honam_semiconductor_watch import canonical_headline_key, canonical_url_key


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

    def test_megaproject_followup_articles_share_one_family(self):
        item = {
            "title": "호남 반도체 클러스터 조성 가속도",
            "description": "전력 용수 정주 여건 마련 동시 진행",
            "body_excerpt": "메가프로젝트 점검회의에서 광주 군공항 임시이전 완료시기 2028년 중순은 늦다며 재검토를 지시했다. 호남권 계통관리변전소는 10월 1일 해제한다.",
        }
        self.assertEqual(_event_family(item), "honam_megaproject_20260929")

    def test_single_report_is_not_labeled_official(self):
        item = {
            "title": "호남 반도체 새 변화",
            "source": "테스트뉴스",
            "url": "https://example.com/news",
            "source_status": "보도 단계",
            "_kind": "news",
            "stages": ["6_산단투자_기업일정"],
            "stage_labels": ["⑥ 산단·기업투자·팹 일정"],
        }
        merged = _merge_group([item])
        self.assertEqual(merged["verification_level"], 1)
        self.assertEqual(merged["verification_status"], "단일 보도·공식 미확정")

    def test_official_evidence_promotes_verification(self):
        news = {
            "title": "호남 반도체 메가프로젝트",
            "source": "테스트뉴스",
            "url": "https://example.com/news",
            "source_status": "보도 단계",
            "_kind": "news",
            "stages": ["4_정주주거_배후도시", "6_산단투자_기업일정"],
            "stage_labels": ["④ 정주·주거·배후도시", "⑥ 산단·기업투자·팹 일정"],
        }
        official = {
            "title": "메가프로젝트 제3차 민관합동 점검회의",
            "source": "대한민국 청와대",
            "url": "https://www.president.go.kr/briefings/test",
            "source_status": "공식자료",
            "_kind": "official",
            "stages": ["4_정주주거_배후도시", "6_산단투자_기업일정"],
            "stage_labels": ["④ 정주·주거·배후도시", "⑥ 산단·기업투자·팹 일정"],
        }
        merged = _merge_group([news, official])
        self.assertEqual(merged["verification_level"], 3)
        self.assertEqual(merged["verification_status"], "공식자료 확인")
        self.assertEqual(merged["evidence_count"], 2)

    def test_news1_source_label_variants_share_headline_key(self):
        pub = "Mon, 05 Oct 2026 23:01:00 GMT"
        a = canonical_headline_key(
            "'반도체 도시' 준비 전남광주…10만명 '의료 정주여건' 밑그림 시급 - 뉴스1",
            pub,
        )
        b = canonical_headline_key(
            "'반도체 도시' 준비 전남광주…10만명 '의료 정주여건' 밑그림 시급 - news1.kr",
            pub,
        )
        self.assertEqual(a, b)

    def test_google_news_same_article_query_variants_share_url_key(self):
        base = "https://news.google.com/rss/articles/CBMiTESTARTICLE"
        self.assertEqual(
            canonical_url_key(base + "?oc=5"),
            canonical_url_key(base + "?oc=5&utm_source=test"),
        )

    def test_medical_settlement_article_maps_to_known_family(self):
        item = {
            "title": "'반도체 도시' 준비 전남광주…10만명 '의료 정주여건' 밑그림 시급 - 뉴스1",
            "description": "7일 반도체도시과 출범…연말 100일 전략 마련 검토",
        }
        self.assertEqual(_event_family(item), "honam_settlement_governance")
        self.assertEqual(_action_level(item), 1)

    def test_actual_department_launch_is_action_upgrade(self):
        item = {
            "title": "호남 반도체 정주 전담 반도체도시과 공식 출범",
            "description": "전남광주통합특별시는 7일 반도체도시과가 출범했다고 밝혔다.",
        }
        self.assertEqual(_event_family(item), "honam_settlement_governance")
        self.assertEqual(_action_level(item), 3)


if __name__ == "__main__":
    unittest.main()

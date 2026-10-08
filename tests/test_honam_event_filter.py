#!/usr/bin/env python3
import pathlib
import sys
import unittest
import hashlib
import json
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.honam_event_filter import (
    _action_level,
    _executive_visit_signal,
    _event_family,
    _is_known_baseline_only,
    _is_proposal_only,
    _merge_group,
)
from scripts.honam_semiconductor_watch import canonical_headline_key, canonical_url_key, verified_intake_events


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

    def test_chair_site_visit_scheduled_not_completed(self):
        item = {
            "title": "최태원 SK그룹 회장, 9일 광주 군공항 반도체 팹 예정지 방문한다",
            "description": "SK하이닉스 경영진이 현장 동행 예정. 기존 사장단은 7월에 방문했다.",
            "source_status": "보도 단계",
        }
        self.assertEqual(_executive_visit_signal(item), 1)
        self.assertEqual(_action_level(item), 1)
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261009")
        self.assertFalse(_is_known_baseline_only(item))

    def test_chair_site_visit_actual_completion_is_new_stage(self):
        item = {
            "title": "최태원 회장, 광주 군공항 반도체 부지 방문했다",
            "description": "SK하이닉스의 팹 건립 예정지 현장을 둘러봤다.",
            "source_status": "보도 단계",
        }
        self.assertEqual(_executive_visit_signal(item), 3)
        self.assertEqual(_action_level(item), 3)
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261009")

    def test_old_executive_visit_is_not_chair_visit(self):
        item = {
            "title": "SK하이닉스 염성진 사장단, 광주 군공항 부지 방문",
            "description": "최태원 회장은 향후 현장을 찾을 예정이라는 보도가 나왔다.",
        }
        self.assertEqual(_executive_visit_signal(item), 0)

    def test_chair_visit_not_investment_contract(self):
        item = {
            "title": "최태원, 호남 광주 군공항 반도체 부지 찾는다",
            "description": "SK하이닉스가 향후 설비투자 규모와 일정을 검토할 예정이다.",
        }
        self.assertEqual(_action_level(item), 1)

    def test_merge_completed_chair_visit_overrides_planned_article(self):
        planned = {
            "title": "최태원 회장, 광주 군공항 반도체 부지 방문 예정",
            "source": "이데일리", "url": "https://example.com/a",
            "source_status": "보도 단계",
            "stages": ["6_산단투자_기업일정"],
            "stage_labels": ["⑥ 산단·기업투자·팹 일정"],
        }
        actual = {
            "title": "최태원 회장, 광주 군공항 반도체 부지 방문했다",
            "source": "조선비즈", "url": "https://example.com/b",
            "source_status": "보도 단계",
            "stages": ["6_산단투자_기업일정"],
            "stage_labels": ["⑥ 산단·기업투자·팹 일정"],
        }
        merged = _merge_group([planned, actual])
        self.assertEqual(merged["verification_level"], 2)
        self.assertIn("완료", merged["title"])
        self.assertEqual(merged["evidence_count"], 2)

    def test_verified_incident_intake_is_once_by_family(self):
        payload = {"events": [{
            "event_family": "honam_sk_chair_site_visit_20261009",
            "event_phase": "scheduled",
            "title": "최태원 SK그룹 회장, 광주 군공항 반도체 부지 방문 예정",
            "description": "10월 9일 방문 예정",
            "evidence": [
                {"source": "이데일리", "url": "https://example.com/a"},
                {"source": "조선비즈", "url": "https://example.com/b"},
            ],
        }]}
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "intake.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with patch("scripts.honam_semiconductor_watch.VERIFIED_INTAKE_PATH", path):
                first = verified_intake_events({"seen_event_keys": []})
                self.assertEqual(len(first), 2)
                key = hashlib.sha256(
                    "family|honam_sk_chair_site_visit_20261009".encode("utf-8")
                ).hexdigest()[:28]
                self.assertEqual(verified_intake_events({"seen_event_keys": [key]}), [])


if __name__ == "__main__":
    unittest.main()

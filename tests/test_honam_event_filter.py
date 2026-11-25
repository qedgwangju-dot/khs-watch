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
    _power_event,
    main as event_filter_main,
)
from scripts.honam_semiconductor_watch import canonical_headline_key, canonical_url_key, verified_intake_events, source_collection_health
from scripts import honam_semiconductor_watch as honam_watch
from scripts.honam_telegram_formatter import build_message, split_message
from scripts.honam_event_filter import _action_level
from scripts.honam_delivery_journal import decision, verified_receipt


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
            "published": "Thu, 08 Oct 2026 11:09:00 GMT",
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
            "published": "Fri, 09 Oct 2026 06:00:00 GMT",
            "source_status": "보도 단계",
        }
        self.assertEqual(_executive_visit_signal(item), 3)
        self.assertEqual(_action_level(item), 3)
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261009")

    def test_another_visit_date_gets_new_event_key(self):
        future = {
            "title": "최태원 SK그룹 회장, 20일 광주 군공항 반도체 부지 방문 예정",
            "description": "새로운 현장 방문 일정",
            "published": "Mon, 19 Oct 2026 09:00:00 GMT",
        }
        self.assertEqual(_event_family(future), "honam_sk_chair_site_visit_20261020")

    def test_other_chipmaker_chair_has_separate_family(self):
        item = {
            "title": "이재용 삼성전자 회장, 9일 광주 군공항 반도체 부지 방문 예정",
            "description": "현장 확인을 위한 방문 예정",
            "published": "Thu, 08 Oct 2026 11:00:00 GMT",
        }
        self.assertEqual(_event_family(item), "honam_samsung_chair_site_visit_20261009")

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

    def test_chair_visit_infra_discussion_not_infra_state_change(self):
        planned = {
            "title": "최태원 회장, 광주 군공항 반도체 부지 방문 예정",
            "description": "광주 군공항 현장에서 전력·용수·인허가를 논의할 예정",
            "source": "이데일리", "url": "https://example.com/a",
            "source_status": "보도 단계",
            "stages": ["5_기반시설_생활SOC", "6_산단투자_기업일정"],
            "stage_labels": ["⑤ 전력·용수·교통·생활 인프라", "⑥ 산단·기업투자·팹 일정"],
        }
        merged = _merge_group([planned])
        self.assertEqual(merged["stages"], ["6_산단투자_기업일정"])
        self.assertIn("예정", merged["impact"])
        self.assertNotIn("전원 인가 시간표", merged["impact"])

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

    def _chair_oct8_reports(self):
        # Three publishers, same 9 October planned visit, different headline
        # wording, 8 October publication dates, and infrastructure keywords.
        return [
            {
                "title": "최태원, 광주 반도체팹 예정지 찾는다 … 용지·전력 등 점검",
                "description": "최 회장은 9일 오후 광주 군공항 내 팹 부지를 방문할 예정이다.",
                "published": "Thu, 08 Oct 2026 14:09:00 GMT",
                "source": "매일경제", "url": "https://example.com/mk",
                "source_status": "보도 단계",
                "stages": ["5_기반시설_생활SOC", "6_산단투자_기업일정"],
                "stage_labels": ["⑤ 전력·용수·교통·생활 인프라", "⑥ 산단·기업투자·팹 일정"],
            },
            {
                "title": "최태원 SK그룹 회장, 호남 반도체 부지 현장 방문 예정",
                "description": "SK하이닉스 경영진도 동행. 지난해 다른 임원 방문 이력이 있다.",
                "published": "Thu, 08 Oct 2026 13:04:00 GMT",
                "source": "세계일보", "url": "https://example.com/segye",
                "source_status": "보도 단계",
                "stages": ["6_산단투자_기업일정"],
                "stage_labels": ["⑥ 산단·기업투자·팹 일정"],
            },
            {
                "title": "최태원 SK 회장, 광주 첫 현장 방문…반도체 투자 우려 덜까",
                "description": "SK하이닉스 경영진 동행…민형배 시장과 팹 건설 추진 방안 논의.",
                "published": "Thu, 08 Oct 2026 10:44:00 GMT",
                "source": "노컷뉴스", "url": "https://example.com/nocut",
                "source_status": "보도 단계",
                "stages": ["5_기반시설_생활SOC", "6_산단투자_기업일정"],
                "stage_labels": ["⑤ 전력·용수·교통·생활 인프라", "⑥ 산단·기업투자·팹 일정"],
            },
        ]

    def test_three_oct8_chair_visit_reports_share_original_oct9_family(self):
        items = self._chair_oct8_reports()
        self.assertEqual([_executive_visit_signal(x) for x in items], [1, 1, 1])
        self.assertEqual([_action_level(x) for x in items], [1, 1, 1])
        self.assertEqual(
            {_event_family(x) for x in items},
            {"honam_sk_chair_site_visit_20261009"},
        )
        merged = _merge_group(items)
        self.assertEqual(merged["stages"], ["6_산단투자_기업일정"])
        self.assertEqual(merged["verification_level"], 2)
        self.assertEqual(merged["evidence_count"], 3)

    def test_previous_oct8_visit_alert_cannot_resend_as_three_oct9_events(self):
        family = "honam_sk_chair_site_visit_20261009"
        key = hashlib.sha256(("family|" + family).encode("utf-8")).hexdigest()[:28]
        items = self._chair_oct8_reports()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(
                json.dumps({"new_items": items, "official_changes": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            # Promotion from one newspaper to three is corroboration, not
            # a new action or a second notification.
            state.write_text(json.dumps({
                "seen_event_keys": [key],
                "event_status_levels": {key: 1},
                "event_action_levels": {key: 1},
            }), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            self.assertFalse(alert.exists(), "Already-notified scheduled visit was resent")
            data = json.loads(pending.read_text(encoding="utf-8"))
            self.assertEqual(data["event_action_levels"][key], 1)
            self.assertEqual(data["event_status_levels"][key], 2)

    def test_actual_oct9_chair_visit_advances_original_event_once(self):
        family = "honam_sk_chair_site_visit_20261009"
        key = hashlib.sha256(("family|" + family).encode("utf-8")).hexdigest()[:28]
        completed = {
            "title": "최태원 회장, 광주 군공항 반도체 부지 현장 방문을 마쳤다",
            "description": "최 회장이 9일 오후 반도체 팹 예정지를 방문한 뒤 향후 계획을 설명했다.",
            "published": "Fri, 09 Oct 2026 06:26:00 GMT",
            "source": "연합뉴스", "url": "https://example.com/yna",
            "source_status": "보도 단계",
            "stages": ["5_기반시설_생활SOC", "6_산단투자_기업일정"],
        }
        self.assertEqual(_event_family(completed), family)
        self.assertEqual(_action_level(completed), 3)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(
                json.dumps({"new_items": [completed], "official_changes": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            state.write_text(json.dumps({
                "seen_event_keys": [key],
                "event_status_levels": {key: 2},
                "event_action_levels": {key: 1},
            }), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            notification = json.loads(alert.read_text(encoding="utf-8"))
            self.assertEqual(notification["new_count"], 1)
            self.assertEqual(notification["new_items"][0]["event_key"], key)
            self.assertEqual(notification["new_items"][0]["stages"], ["6_산단투자_기업일정"])
            self.assertIn("완료", notification["new_items"][0]["title"])
            self.assertEqual(
                json.loads(pending.read_text(encoding="utf-8"))["event_action_levels"][key], 3,
            )

    def test_old_executive_visit_date_not_used_as_chair_visit_date(self):
        item = {
            "title": "최태원 SK 회장, 광주 첫 현장 방문…반도체 투자 점검",
            "description": "지난 7월 29일 SK하이닉스 경영진이 현장을 방문했다. 최 회장 방문을 앞두고 있다.",
            "published": "Thu, 08 Oct 2026 10:44:00 GMT",
        }
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261009")
        self.assertEqual(_executive_visit_signal(item), 1)


    def _chair_oct9_briefing_reports(self):
        return [
            {
                "title": '최태원 "호남 반도체 팹 규모, 용인 3분의 2 수준 검토"',
                "description": "향후 추가 부지와 공장 규모를 검토한다고 밝혔다.",
                "published": "Fri, 09 Oct 2026 06:26:00 GMT",
                "source": "연합뉴스", "url": "https://example.com/yna-briefing",
                "source_status": "보도 단계",
                "stages": ["6_산단투자_기업일정"],
            },
            {
                "title": '최태원 "용인만으론 부족…호남 반도체, 전력·용수 늦어도 먼저 착공"',
                "description": "현장 브리핑 중 전력과 용수보다 착공이 앞설 수 있다고 언급했다.",
                "published": "Fri, 09 Oct 2026 06:25:00 GMT",
                "source": "뉴시스", "url": "https://example.com/newsis-briefing",
                "source_status": "보도 단계",
                "stages": ["5_기반시설_생활SOC", "6_산단투자_기업일정"],
            },
        ]

    def test_oct9_briefing_headlines_are_one_completed_visit_not_infra_upgrade(self):
        items = self._chair_oct9_briefing_reports()
        self.assertEqual([_executive_visit_signal(x) for x in items], [3, 3])
        self.assertEqual({_event_family(x) for x in items}, {"honam_sk_chair_site_visit_20261009"})
        merged = _merge_group(items)
        self.assertEqual(merged["stages"], ["6_산단투자_기업일정"])
        self.assertEqual(merged["verification_level"], 2)
        self.assertIn("방문 완료", merged["title"])
        self.assertIn("규모", merged["title"])
        self.assertIn("선착공", merged["title"])

    def test_oct9_briefing_reprint_after_corrected_message_is_suppressed(self):
        family = "honam_sk_chair_site_visit_20261009"
        key = hashlib.sha256(("family|" + family).encode("utf-8")).hexdigest()[:28]
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(json.dumps({
                "new_items": self._chair_oct9_briefing_reports(), "official_changes": []
            }, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps({
                "seen_event_keys": [key],
                "event_status_levels": {key: 2},
                "event_action_levels": {key: 3},
            }), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            self.assertFalse(alert.exists(), "Completed visit recap was resent")
            data = json.loads(pending.read_text(encoding="utf-8"))
            self.assertEqual(data["event_action_levels"][key], 3)

    def test_verified_press_briefing_does_not_swallow_binding_contract(self):
        contract = {
            "title": "최태원, 호남 반도체 투자계약 체결 확정",
            "description": "새로운 확정 계약의 체결을 별도로 보도",
            "published": "Fri, 09 Oct 2026 07:30:00 GMT",
        }
        self.assertEqual(_executive_visit_signal(contract), 0)
        self.assertEqual(_event_family(contract), "")

    def test_previsit_quote_headline_cannot_be_reported_completed(self):
        before = {
            "title": '최태원 "호남 반도체, 전력·용수 늦어도 먼저 착공" 전망',
            "description": "9일 현장 방문을 앞둔 전망성 보도",
            "published": "Thu, 08 Oct 2026 12:00:00 GMT",
        }
        self.assertEqual(_executive_visit_signal(before), 1)


    def _late_cbc_20261012(self):
        return {
            "title": "최태원 SK그룹 회장, 호남 반도체 부지 현장 방문 예정",
            "description": "최태원 회장이 광주 반도체 클러스터 예정지를 찾아 기업투자와 부지를 점검한다는 내용을 재인용",
            "published": "Mon, 12 Oct 2026 00:48:00 GMT",
            "source": "CBC뉴스",
            "url": "https://news.google.com/rss/articles/CBMiaEFVX3lxTFBrN3NjMUZDRkxLTF93eTNjT2UzNjd2T2ppZzVVbnpFNTYwS1V4djhjY1VhbkF6b1VYd3NPaFFWQVFFNFBiSVdtMFpDZnB1REZLRnhzR0ZoVURUUkszekhLSTFSQ0ZTalFu?oc=5",
            "source_status": "보도 단계",
            "stages": ["6_산단투자_기업일정"],
            "stage_labels": ["⑥ 산단·기업투자·팹 일정"],
        }

    def test_oct12_cbc_reprint_is_oct9_visit_not_new_visit(self):
        item = self._late_cbc_20261012()
        self.assertEqual(_executive_visit_signal(item), 1)
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261009")
        self.assertEqual(_action_level(item), 1)

    def test_oct12_cbc_reprint_with_corrupt_20261012_state_is_suppressed(self):
        old_family = "honam_sk_chair_site_visit_20261009"
        fake_family = "honam_sk_chair_site_visit_20261012"
        old_key = hashlib.sha256(("family|" + old_family).encode()).hexdigest()[:28]
        fake_key = hashlib.sha256(("family|" + fake_family).encode()).hexdigest()[:28]
        self.assertNotEqual(old_key, fake_key)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(json.dumps({
                "new_items": [self._late_cbc_20261012()],
                "official_changes": [],
            }, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps({
                "seen_event_keys": [old_key, fake_key],
                "event_action_levels": {old_key: 3, fake_key: 1},
                "event_status_levels": {old_key: 2, fake_key: 1},
            }), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            self.assertFalse(alert.exists(), "Late duplicate generated another alert")
            after = json.loads(pending.read_text(encoding="utf-8"))
            self.assertEqual(after["event_action_levels"][old_key], 3)
            self.assertEqual(after["unresolved_visit_count_last_check"], 0)

    def test_oct9_visit_reprint_four_weeks_later_remains_same_incident(self):
        item = self._late_cbc_20261012()
        item["published"] = "Mon, 02 Nov 2026 00:48:00 GMT"
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261009")

    def test_undated_visit_outside_verified_window_is_quarantined(self):
        item = self._late_cbc_20261012()
        item["published"] = "Fri, 12 Feb 2027 00:48:00 GMT"
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_unknown")
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(json.dumps({
                "new_items": [item],
                "official_changes": [],
            }, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps({
                "seen_event_keys": [],
                "event_action_levels": {},
                "event_status_levels": {},
            }), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            self.assertFalse(alert.exists())
            after = json.loads(pending.read_text(encoding="utf-8"))
            self.assertEqual(after["unresolved_visit_count_last_check"], 1)

    def test_explicit_new_oct20_visit_remains_distinct_when_oct9_verified(self):
        item = self._late_cbc_20261012()
        item["title"] = "최태원 SK 회장, 20일 광주 군공항 반도체 부지 다시 방문 예정"
        item["published"] = "Mon, 19 Oct 2026 00:48:00 GMT"
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261020")
        self.assertEqual(_action_level(item), 1)

    def test_completed_oct9_visit_cannot_regress_to_oct12_scheduled(self):
        item = self._late_cbc_20261012()
        item["title"] = "최태원 SK 회장, 지난 9일 광주 군공항 부지 방문 완료"
        self.assertEqual(_event_family(item), "honam_sk_chair_site_visit_20261009")
        self.assertEqual(_action_level(item), 3)



    def _power_item(self, title, description="", source="연합뉴스", official=False):
        return {
            "title": title,
            "description": description,
            "source": source,
            "url": "https://example.com/" + hashlib.sha256((title + source).encode()).hexdigest()[:16],
            "source_status": "공식자료" if official else "보도 단계",
            "stages": ["5_기반시설_생활SOC", "6_산단투자_기업일정"],
            "stage_labels": ["⑤ 전력·용수·교통·생활 인프라", "⑥ 산단·기업투자·팹 일정"],
            "published": "Wed, 14 Oct 2026 04:00:00 GMT",
        }

    def test_power_government_mix_and_samsung_lng_request_are_existing_baselines(self):
        cases = (
            "정부, 호남 반도체 2029년 첫 팹 완공 목표…재생에너지·ESS·LNG 열병합 활용 방침",
            "삼성전자, 호남 반도체 LNG 열병합발전 추진 정부에 요청",
            "호남 반도체 ESS 보급 계획…원전·태양광·LNG 병행 예정",
            "호남 반도체 PPA 적극 추진 건의…전력구매계약 검토",
        )
        for title in cases:
            with self.subTest(title=title):
                item = self._power_item(title)
                meta = _power_event(item)
                self.assertIsNotNone(meta)
                self.assertEqual(meta["phase"], "baseline")
                self.assertEqual(_event_family(item), meta["family"])

    def test_power_yongin_plant_is_not_confirmed_honam_supply(self):
        item = self._power_item(
            "용인 LNG 열병합발전소 1050MW 착공 확정",
            "용인의 사례는 호남 반도체 클러스터에도 비슷한 과제를 제기한다."
        )
        self.assertIsNone(_power_event(item))

    def test_power_project_lng_approval_is_real_phase(self):
        item = self._power_item("호남 반도체 LNG 열병합발전 사업자 최종 선정")
        self.assertEqual(_power_event(item)["family"], "honam_power_lng_chp_contracted")
        self.assertEqual(_action_level(item), 2)
        plan = self._power_item("호남 반도체 LNG 열병합발전 사업자 선정 예정")
        self.assertEqual(_power_event(plan)["phase"], "baseline")

    def test_power_actual_ess_and_grid_are_distinct_milestones(self):
        self.assertEqual(
            _power_event(self._power_item("호남 반도체 ESS 발전사업 허가 승인"))["phase"],
            "authorized",
        )
        self.assertEqual(
            _power_event(self._power_item("호남 반도체 전력망 공사 착수"))["phase"],
            "construction",
        )
        self.assertEqual(
            _power_event(self._power_item("호남 반도체 전원 인가 완료"))["phase"],
            "commercial",
        )
        self.assertEqual(
            _power_event(self._power_item("호남 반도체 LNG 발전사업 허가 반려"))["phase"],
            "cancelled",
        )

    def test_power_one_press_report_waits_for_independent_corroboration(self):
        item = self._power_item("호남 반도체 LNG 열병합발전 사업자 최종 선정", source="뉴스1")
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(json.dumps({"new_items": [item], "official_changes": []}, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps({
                "seen_event_keys": [], "event_status_levels": {}, "event_action_levels": {},
            }), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            self.assertFalse(alert.exists())
            result = json.loads(pending.read_text(encoding="utf-8"))
            family = "honam_power_lng_chp_contracted"
            self.assertIn(family, result["power_pending_evidence"])
            key = hashlib.sha256(("family|" + family).encode()).hexdigest()[:28]
            self.assertNotIn(key, result["seen_event_keys"])
            self.assertNotIn(key, result["event_action_levels"])

            second = self._power_item(item["title"], source="연합뉴스")
            alert.write_text(json.dumps({"new_items": [second], "official_changes": []}, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            reported = json.loads(alert.read_text(encoding="utf-8"))
            self.assertEqual(reported["new_count"], 1)
            self.assertEqual(reported["new_items"][0]["stages"], ["5_기반시설_생활SOC"])
            self.assertEqual(reported["new_items"][0]["verification_level"], 2)
            self.assertEqual(len(reported["new_items"][0]["evidence_sources"]), 2)
            result = json.loads(pending.read_text(encoding="utf-8"))
            self.assertIn(key, result["seen_event_keys"])
            self.assertNotIn(family, result["power_pending_evidence"])

    def test_power_single_primary_document_can_confirm_contract(self):
        item = self._power_item("호남 반도체 전력구매계약 체결", source="삼성전자", official=True)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(json.dumps({"new_items": [item], "official_changes": []}, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps({"seen_event_keys": [], "event_status_levels": {}, "event_action_levels": {}}, ensure_ascii=False), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), \
                 patch("scripts.honam_event_filter.STATE_PATH", state), \
                 patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            self.assertEqual(json.loads(alert.read_text(encoding="utf-8"))["new_count"], 1)




    def test_rss_source_failure_is_not_no_new_announcement(self):
        self.assertIn("조회 성공", source_collection_health(3, 0, 3))
        self.assertIn("부분 조회 실패", source_collection_health(2, 1, 3))
        self.assertIn("전체 조회 실패", source_collection_health(0, 3, 3))
        with self.assertRaises(ValueError):
            source_collection_health(1, 1, 3)

    def test_total_rss_outage_refuses_state_advance_without_sending(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = pathlib.Path(tempdir)
            state, pending, alert, status = (root / name for name in ("state.json", "pending.json", "alert.json", "status.md"))
            original = '{"initialized":true,"seen_event_keys":["preserve"]}'
            state.write_text(original, encoding="utf-8")
            with patch.object(honam_watch, "STATE_PATH", state), \
                 patch.object(honam_watch, "PENDING_PATH", pending), \
                 patch.object(honam_watch, "ALERT_PATH", alert), \
                 patch.object(honam_watch, "STATUS_PATH", status), \
                 patch.object(honam_watch, "QUERIES", ["source A", "source B"]), \
                 patch.object(honam_watch, "google_news_items", side_effect=RuntimeError("HTTP 429")):
                with self.assertRaisesRegex(RuntimeError, "전체 RSS 수집 실패"):
                    honam_watch.main()
            self.assertEqual(state.read_text(encoding="utf-8"), original)
            self.assertFalse(pending.exists())
            self.assertFalse(alert.exists())
            self.assertFalse(status.exists())


    def test_honam_matching_article_body_and_fact_extraction(self):
        title = "전남광주 반도체 건설인력 주거대책 마련"
        raw = '<title>' + title + '</title><article><p>시 관계자는 건설인력 1만3천명과 공공임대 1만호 마련을 검토한다고 설명했다.</p><p>노바 미래도시 용역비는 2027년 본예산에 미반영됐다.</p></article>'
        body = honam_watch.article_body(raw, title)
        self.assertIn("1만3천명", body)
        self.assertIn("미반영", body)
        self.assertEqual(honam_watch.article_body(raw, "다른 반도체 국가산업단지 관련 기사"), "")
        self.assertEqual(len(honam_watch.article_fact_lines(body)), 2)

    def test_honam_unresolved_housing_source_is_preliminary(self):
        item = {"title":"전남광주 반도체 건설인력 주거대책 마련…모듈러 주택도 검토",
                "description":"2030년 6월 양산 목표, 63만평, 3.1GW 공급 목표",
                "source":"연합뉴스", "source_status":"보도 단계",
                "stages":["4_정주주거_배후도시"], "url":"https://news.google.com/rss/articles/example",
                "body_status":"본문 미확보(제목·검색 요약만 확인)"}
        self.assertFalse(_is_known_baseline_only(item))
        self.assertEqual(_action_level(item), 1)
        merged = _merge_group([item])
        self.assertEqual(merged["alert_type"], "선행경보")
        msg = build_message({"new_items":[merged],"official_changes":[],"rss_failed_queries":1})
        self.assertIn("선행경보 <b>1건", msg)
        self.assertIn("검색 경유 링크", msg)
        self.assertIn("일부 원천 조회 실패", msg)

    def test_honam_recovery_keeps_numbers_and_blocks_replay(self):
        items = [x for x in verified_intake_events({"seen_event_keys":[]}) if x.get("recovery")]
        groups = {}
        for x in items:
            groups.setdefault(_event_family(x), []).append(x)
            self.assertEqual(_action_level(x), 1)
            self.assertFalse(_is_known_baseline_only(x))
        self.assertEqual(len(groups), 2)
        msg = build_message({"new_items":[_merge_group(g) for g in groups.values()],"official_changes":[]})
        for fact in ("1만2천~1만3천명","1만호","1조5,790억원","노바","723억원","66억원","168억원","11.9억원","34.8억원","253필지","누락 보완"):
            self.assertIn(fact, msg)
        self.assertTrue(all(len(chunk) <= 3900 for chunk in split_message(msg)))
        self.assertIn("a0fd4038c2911f1e9d94b97a", honam_watch.registered_covered_headlines())
        keys = [hashlib.sha256(("family|"+name).encode()).hexdigest()[:28] for name in groups]
        self.assertFalse([x for x in verified_intake_events({"seen_event_keys":keys}) if x.get("recovery")])


    def test_nov25_recovery_aliases_group_all_five_reprints(self):
        housing = "honam_settlement_lead_20261125_housing_budget_recovery"
        water = "honam_water_lead_20261125_local_budget_recovery"
        titles = {
            '민형배 전남광주시장 "반도체 팹 건설인력 1만호 공공임대 필요" - 연합뉴스': housing,
            "호남 반도체 용수 공급 덕남정수장 생산량 2배로 늘린다": water,
            '민형배 "반도체 정주여건 핵심 도심융합특구 구체화 서둘러야"': housing,
            "전남광주, '반도체 16만 인구 유입' 대비 주거벨트 구축 속도전": housing,
            "민형배 시장 '반도체 공공임대 1만호 필요'": housing,
        }
        aliases = [{"title":title,"published":"Wed, 25 Nov 2026 05:00:00 GMT","source":"언론",
                    "source_status":"보도 단계","description":"기존 계획을 설명했다",
                    "stages":["2_수량수질_조사범위"],"stage_labels":["② 장록습지 수량·수질"]} for title in titles]
        for item in aliases:
            self.assertEqual(_event_family(item), titles[item["title"]])
            self.assertEqual(_action_level(item), 1)
        items = [i for i in verified_intake_events({"seen_event_keys":[]}) if i.get("recovery")] + aliases
        groups = {}
        for item in items:
            groups.setdefault(_event_family(item), []).append(item)
        self.assertEqual(set(groups), {housing, water})
        merged = {family:_merge_group(group) for family,group in groups.items()}
        self.assertIn("누락 보완", merged[housing]["title"])
        self.assertEqual(merged[housing]["stages"], ["4_정주주거_배후도시"])
        self.assertEqual(merged[water]["stages"], ["5_기반시설_생활SOC"])
        self.assertIn("723억원", build_message({"new_items":list(merged.values()),"official_changes":[]}))

    def test_nov25_reprint_after_confirmed_delivery_is_not_resent(self):
        family = "honam_settlement_lead_20261125_housing_budget_recovery"
        item = {"title":"민형배 시장 '반도체 공공임대 10,000호 필요'",
                "published":"Thu, 26 Nov 2026 01:00:00 GMT",
                "source":"보도 A", "description":"공공임대 마련 검토", "source_status":"보도 단계"}
        self.assertEqual(_event_family(item), family)
        key = hashlib.sha256(("family|"+family).encode()).hexdigest()[:28]
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            alert,state,pending = (root / name for name in ("alert.json","state.json","pending.json"))
            alert.write_text(json.dumps({"new_items":[item],"official_changes":[]},ensure_ascii=False),encoding="utf-8")
            state.write_text(json.dumps({"seen_event_keys":[key],"event_action_levels":{key:1},"event_status_levels":{key:2}}),encoding="utf-8")
            pending.write_text("{}",encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH",alert),patch("scripts.honam_event_filter.STATE_PATH",state),patch("scripts.honam_event_filter.PENDING_PATH",pending):
                event_filter_main()
            self.assertFalse(alert.exists())
            self.assertIn(key,json.loads(pending.read_text(encoding="utf-8"))["seen_event_keys"])

    def test_nov25_new_counts_and_actual_execution_not_folded_into_old_plan(self):
        old = "honam_settlement_lead_20261125_housing_budget_recovery"
        new = {"title":"광주 반도체 건설인력 공공임대 1만2천호 필요","description":"추가 공급 검토"}
        self.assertNotEqual(_event_family(new), old)
        self.assertEqual(_action_level(new), 1)
        contract = {"title":"광주 반도체 공공임대 1만호 공급 계약 체결","description":"계약을 체결했다"}
        self.assertNotEqual(_event_family(contract), old)
        self.assertGreaterEqual(_action_level(contract), 2)
        works = {"title":"호남 반도체 덕남정수장 생산량 2배 개량공사 착공","description":"공사에 착수했다"}
        self.assertNotEqual(_event_family(works), "honam_water_lead_20261125_local_budget_recovery")
        self.assertGreaterEqual(_action_level(works), 2)

    def test_honam_uncertain_delivery_is_held_and_confirmed_recovers(self):
        record = {"status":"sending","message_ids":[1],"total_parts":2,"pending_state":{"seen_event_keys":["x"]}}
        self.assertEqual(decision(None), "clear")
        self.assertEqual(decision(record), "hold_uncertain")
        self.assertEqual(decision(dict(record,status="uncertain")), "hold_uncertain")
        self.assertEqual(decision(dict(record,status="confirmed")), "hold_uncertain")
        self.assertEqual(decision(dict(record,status="confirmed",message_ids=[1,2])), "recover_confirmed")
        self.assertEqual(decision(dict(record,status="confirmed",message_ids=[1,1])), "hold_uncertain")

    def test_honam_receipt_requires_correct_destination_and_id(self):
        payload = {"ok":True,"result":{"message_id":5,"chat":{"id":-123,"username":"example"}}}
        self.assertEqual(verified_receipt(payload,"-123"), (5,-123))
        self.assertEqual(verified_receipt(payload,"@example"), (5,-123))
        with self.assertRaises(RuntimeError):
            verified_receipt(payload,"-124")
        with self.assertRaises(RuntimeError):
            verified_receipt({"ok":True,"result":{"chat":{"id":-123}}},"-123")


    def test_honam_readable_report_keeps_all_reviewed_facts_once(self):
        items = [i for i in verified_intake_events({"seen_event_keys": []}) if i.get("recovery")]
        groups = {}
        for item in items:
            groups.setdefault(_event_family(item), []).append(item)
        merged = [_merge_group(group) for group in groups.values()]
        msg = build_message({"new_items": merged, "official_changes": [], "new_count": 7,
                             "checked_at_kst": "2026-11-25T19:49:00+09:00"})
        self.assertIn("선행경보 <b>2건</b>", msg)
        self.assertEqual(msg.count("<b>■ "), 2)
        self.assertIn("<b>주거 수요·공급 구상</b>", msg)
        self.assertIn("<b>16:04 연합뉴스 · 시의회 예산심사</b>", msg)
        for value in ("1만2천~1만3천명", "1만호", "1만4천가구", "6,800", "3,200가구",
                      "85만2,693㎡", "1조5,790억원", "2027.12", "2031년", "2027년 본예산",
                      "723억원", "722억8,600만원", "5만t/일", "10만t/일",
                      "1,350㎜", "1,000㎜", "7천㎥", "2028.12", "66억원",
                      "168억원", "180억원", "11.9억원", "34.8억원", "253필지", "1.5조원"):
            self.assertIn(value, msg)
        self.assertNotIn("왜 중요:", msg)
        self.assertNotIn("② 장록습지 수량·수질(선행경보)", msg)
        self.assertIn("조회 범위 내 변화 미감지", msg)
        self.assertTrue(all(len(chunk) <= 3900 for chunk in split_message(msg)))

    def test_industrial_water_not_reported_as_wetland_or_fab_change(self):
        item = {"title":"호남 반도체 덕남정수장 개량 예산 검토", "description":"용수 공급을 위한 취수시설 계획",
                "source":"연합뉴스", "source_status":"보도 단계",
                "stages":["2_수량수질_조사범위","5_기반시설_생활SOC","6_산단투자_기업일정"],
                "reason":"장록습지 수량·수질 검증", "impact":"기반시설·전원 인가 시간표 영향"}
        merged = _merge_group([item])
        self.assertEqual(merged["stages"], ["5_기반시설_생활SOC"])
        self.assertNotIn("장록", merged["reason"])
        self.assertIn("용수", merged["impact"])
        actual = dict(item, title="호남 반도체 장록습지 수량·수질 현지조사 착수",
                      description="장록습지의 수위 및 수질 조사", stages=["2_수량수질_조사범위"])
        self.assertEqual(_merge_group([actual])["stages"], ["2_수량수질_조사범위"])

    def test_msn_reprint_not_independent_source(self):
        a = {"title":"호남 반도체 주거대책 검토", "source":"연합뉴스", "source_status":"보도 단계",
             "url":"https://www.yna.co.kr/view/test","stages":["4_정주주거_배후도시"]}
        b = dict(a, source="연합뉴스 on MSN", url="https://www.msn.com/ko-kr/news/test")
        merged = _merge_group([a,b])
        self.assertEqual(merged["verification_level"], 1)
        self.assertIn("재게시 링크", build_message({"new_items":[merged]}))

    def test_long_message_splits_by_event_and_keeps_continuation_context(self):
        items = [
            {"title":"사건 A", "summary_lines":["A 수치: "+str(n)+"억원 "+"가"*55 for n in range(42)],
             "alert_type":"선행경보","stages":["4_정주주거_배후도시"]},
            {"title":"사건 B", "summary_lines":["B 수치: "+str(n)+"억원 "+"나"*55 for n in range(22)],
             "alert_type":"선행경보","stages":["5_기반시설_생활SOC"]}
        ]
        chunks = split_message(build_message({"new_items":items}), limit=900)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 900 for chunk in chunks))
        self.assertTrue(any("계속" in chunk for chunk in chunks))
        combined = "\n".join(chunks)
        for n in range(42):
            self.assertIn(f"{n}억원 " + "가"*55, combined)
        for n in range(22):
            self.assertIn(f"{n}억원 " + "나"*55, combined)
        self.assertIn("사건 B", combined)


    def test_nov25_2152_reprint_is_same_incident(self):
        family = "honam_settlement_lead_20261125_housing_budget_recovery"
        article = {"title": "반도체 건설인력 몰려온다…전남광주, 임대주택 우선 활용",
                   "url": "https://news.jkn.co.kr/post/1122089",
                   "published": "Tue, 24 Nov 2026 19:32:00 GMT",
                   "source": "재경일보", "source_status": "보도 단계",
                   "description": "민간 임대주택 우선 활용, 모듈러 주택 검토",
                   "stages": ["4_정주주거_배후도시"]}
        self.assertEqual(_event_family(article), family)
        key = hashlib.sha256(("family|"+family).encode()).hexdigest()[:28]
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            alert,state,pending = (root / n for n in ("alert.json","state.json","pending.json"))
            alert.write_text(json.dumps({"new_items":[article],"official_changes":[]},ensure_ascii=False),encoding="utf-8")
            state.write_text(json.dumps({"seen_event_keys":[key],"event_action_levels":{key:1},"event_status_levels":{key:2}}),encoding="utf-8")
            pending.write_text("{}",encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH",alert),patch("scripts.honam_event_filter.STATE_PATH",state),patch("scripts.honam_event_filter.PENDING_PATH",pending):
                event_filter_main()
            self.assertFalse(alert.exists())
            self.assertIn(key,json.loads(pending.read_text(encoding="utf-8"))["seen_event_keys"])

    def test_same_hearing_body_alias_and_new_contract_distinguished(self):
        family = "honam_settlement_lead_20261125_housing_budget_recovery"
        item = {"title":"전남광주 반도체 주거 지원 대책",
                "published":"Wed, 25 Nov 2026 07:00:00 GMT",
                "description":"25일 2027년도 본예산안 심사에서 민간 임대주택 우선 활용, 부족하면 모듈러 주택 검토. 5개 자치구와 광주도시공사 협의체. 국제학교·도로·용수 요청. 올해 말 초안 마련."}
        self.assertEqual(_event_family(item), family)
        actual = dict(item, title="광주 반도체 공공임대 공급 계약 체결")
        self.assertNotEqual(_event_family(actual), family)
        new_day = dict(item, published="Tue, 01 Dec 2026 07:00:00 GMT")
        self.assertNotEqual(_event_family(new_day), family)

    def test_honam_compact_source_facts_keep_numbers_and_remove_paraphrase(self):
        from scripts.honam_telegram_formatter import build_message
        article = {"title":"반도체 건설인력 주거대책", "alert_type":"선행경보",
                   "verification_status":"단일 보도·공식 미확정",
                   "stages":["4_정주주거_배후도시"], "source":"재경일보",
                   "url":"https://news.jkn.co.kr/post/1122089",
                   "fact_lines":[
                       "민간 임대주택을 우선 활용하고, 공급이 부족하면 기업과 공공이 모듈러 주택을 공급하는 방안도 검토한다.",
                       "통합시는 우선 민간 임대주택을 활용하되, 주택 공급이 수요를 따라가지 못할 경우 기업과 공공기관이 협력해 조립식 주택인 모듈러 주택을 공급하는 방안까지 검토하고 있다.",
                       "통합시는 5개 자치구와 한국토지주택공사(LH), 광주도시공사 등이 참여하는 신속 행정 협의체도 연말까지 구성할 예정이다.",
                       "마스터플랜 수립을 위한 용역비가 2027년도 본예산에 반영되지 않았기 때문이다.",
                       "2027년 신규 공급 3,500가구는 아직 확정되지 않았다."
                   ],
                   "reason":"2030년 전후 인력 유입을 받을 주택·배후도시 공급 속도가 팹 가동의 정주 병목이 될 수 있음",
                   "impact":"정주·인력유입 준비도 변화"}
        msg = build_message({"new_items":[article],"rss_failed_queries":3})
        self.assertEqual(msg.count("모듈러(조립식)"), 1)
        for token in ("5개 자치구", "연말 구성 예정", "2027년 본예산 미반영", "3,500가구", "확정되지 않았다", "일부 원천 조회 실패(3건)"):
            self.assertIn(token,msg)
        self.assertNotIn("2030년 전후 인력 유입",msg)
        self.assertNotIn("본문 확인 사항(자동 발췌)",msg)

    def test_nov18_leads_remain_preliminary_and_separately_keyed(self):
        vetted = verified_intake_events({"seen_event_keys": []})
        allocation = [i for i in vetted if i.get("event_family") == "honam_fab_lead_site_allocation_20261118"]
        forecast = [i for i in vetted if i.get("event_family") == "honam_fab_lead_groundbreaking_forecast_20261118"]
        self.assertEqual(len(allocation), 3)
        self.assertEqual(len(forecast), 1)
        self.assertNotEqual(_event_family(allocation[0]), _event_family(forecast[0]))
        for item in allocation + forecast:
            self.assertEqual(item["alert_type"], "선행경보")
            self.assertFalse(_is_known_baseline_only(item))
            self.assertEqual(_action_level(item), 1)
            self.assertEqual(item["source_status"], "보도 단계")
        generic_rehash = dict(forecast[0], intake_verified=False)
        self.assertTrue(_is_known_baseline_only(generic_rehash))

    def test_nov18_verified_leads_render_full_numbers_and_source_levels(self):
        vetted = verified_intake_events({"seen_event_keys": []})
        items = [i for i in vetted if str(i.get("event_family") or "").startswith("honam_fab_lead_")]
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            alert, state, pending = (root / n for n in ("alert.json", "state.json", "pending.json"))
            alert.write_text(json.dumps({"new_items": items, "official_changes": [], "new_count": len(items)}, ensure_ascii=False), encoding="utf-8")
            state.write_text(json.dumps({"seen_event_keys": [], "event_action_levels": {}, "event_status_levels": {}}, ensure_ascii=False), encoding="utf-8")
            pending.write_text(state.read_text(encoding="utf-8"), encoding="utf-8")
            with patch("scripts.honam_event_filter.ALERT_PATH", alert), patch("scripts.honam_event_filter.STATE_PATH", state), patch("scripts.honam_event_filter.PENDING_PATH", pending):
                event_filter_main()
            report = json.loads(alert.read_text(encoding="utf-8"))
            self.assertEqual(report["new_count"], 2)
            by_family = {i["event_family"]: i for i in report["new_items"]}
            self.assertEqual(by_family["honam_fab_lead_site_allocation_20261118"]["verification_level"], 2)
            self.assertEqual(by_family["honam_fab_lead_groundbreaking_forecast_20261118"]["verification_level"], 1)
            rendered = build_message({"checked_at_kst": "2026-11-18T19:00:00+09:00", **report})
            for number in ("120만평", "100만평", "30만평", "63만평", "2027년 7월", "2028년", "2029년 중순", "2030년 6월", "3.1GW", "23㎞", "15만t", "310억원"):
                self.assertIn(number, rendered, number)
            self.assertIn("단일 보도", rendered)
            self.assertIn("선행경보", rendered)
            self.assertIn("원문", rendered)
            self.assertLessEqual(max(map(len, split_message(rendered))), 3900)
            # A successfully sent key must suppress repeated intake, not reset earlier records.
            delivered = json.loads(pending.read_text(encoding="utf-8"))["seen_event_keys"]
            self.assertFalse([i for i in verified_intake_events({"seen_event_keys": delivered}) if i.get("event_family", "").startswith("honam_fab_lead_")])

    def test_existing_2029_first_fab_completion_target_is_not_a_new_event(self):
        items = [
            {"title": "호남 반도체 2029년 첫 팹 완공 목표…속도전", "description": "정부는 인프라와 부지 조성을 추진할 방침"},
            {"title": "호남 반도체 팹 2029년 준공 전망", "description": "건설 가능한 부지부터 단계적으로 준비할 계획"},
        ]
        for item in items:
            with self.subTest(title=item["title"]):
                self.assertTrue(_is_known_baseline_only(item))

    def test_2029_reference_does_not_hide_actual_new_construction(self):
        item = {
            "title": "호남 반도체 팹 착공식 개최…2029년 첫 팹 완공 목표",
            "description": "당국이 2029년 목표를 재확인한 가운데 실제 공사 첫 삽을 떴다.",
        }
        self.assertFalse(_is_known_baseline_only(item))



if __name__ == "__main__":
    unittest.main()

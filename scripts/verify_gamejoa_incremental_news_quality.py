#!/usr/bin/env python3
"""Original-body replay plus negative/positive source-event regressions."""

import copy
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamejoa_preopen_news_radar_fda_quality_runner as production
import gamejoa_market_materiality as materiality
import verify_gamejoa_generated_report as generated_guard

radar = production.runner
telegram = radar.telegram
ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 10, 5, 18, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
FIXTURE = json.loads((ROOT / "data/gamejoa_incremental_news_fixtures_20261005.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in FIXTURE["cases"]}
CONTRACT_BODY = "AMD는 삼성전자와 2027년 데이터센터용 인공지능(AI) 반도체 공동개발을 위한 100억원 규모의 공급 계약을 체결했다고 밝혔다."
ADDITIONAL_FACT = " AMD는 해당 공급 계약을 위한 반도체 설비투자 예산 500억원을 확정했다고 공시했다."
PUBLISHERS = {"yna.co.kr": "연합뉴스", "hankyung.com": "한국경제", "etnews.com": "전자신문",
              "chosun.com": "조선비즈", "mk.co.kr": "매일경제", "newsis.com": "뉴시스"}


def alert(title="AMD·삼성전자, AI 반도체 공급 계약 체결", body=CONTRACT_BODY, url="https://www.etnews.com/20261005009901"):
    return {"news": title, "source_title": title, "original_news": title, "source_body": body,
            "source_abstract": body, "telegram_core_fact": body, "body_verified": True,
            "korean_business_news": True, "published": NOW.isoformat(), "publisher": "전자신문", "link": url}


def classify(case):
    return production.contract.strict.classify({
        "title": case["title"], "source_title": case["title"], "source_body": case["body"],
        "source_abstract": case["body"], "body_verified": True, "layer": "trusted",
        "published": radar.base.parse_date(case["published"]), "link": case["url"],
        "publisher": next((name for host, name in PUBLISHERS.items() if host in case["url"]), ""),
    }, NOW)


def eligible(title, body):
    assessment = materiality.assess(title, body)
    return assessment["disposition"] == "keep" and assessment["priority"] >= 2


def replay():
    rows = []
    for case in FIXTURE["cases"]:
        candidate = classify(case)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts([candidate], 30) if candidate else []
        rows.append({"id": case["id"], "url": case["url"], "expected_keep": case["expected_keep"],
                     "selected": bool(selected), "core": selected[0]["telegram_core_fact"] if selected else "",
                     "core_errors": radar.source_core_fact_errors(selected[0]) if selected else [],
                     "reason": candidate.get("_exclusion_reason") if candidate else "classifier_not_eligible"})
    return rows


class IncrementalNewsTests(unittest.TestCase):
    def test_all_ten_originals_are_bound_and_hashed(self):
        self.assertEqual(FIXTURE["original_count"], 10)
        self.assertEqual(len(CASES), 10)
        self.assertEqual(len({case["url"] for case in CASES.values()}), 10)
        groups = FIXTURE["event_groups"]
        self.assertEqual(len(groups), FIXTURE["unique_event_count"])
        self.assertEqual(sorted(name for group in groups.values() for name in group), sorted(CASES))
        self.assertEqual(set(groups["amd_visit"]), {"amd_hankyung", "amd_chosun", "amd_yonhap"})
        for case in CASES.values():
            with self.subTest(case=case["id"]):
                self.assertEqual(hashlib.sha256(case["body"].encode("utf-8")).hexdigest(), case["source_body_sha256"])
                self.assertRegex(case["response_sha256"], r"^[a-f0-9]{64}$")

    def test_production_replay_selects_only_two_incremental_actions(self):
        for row in replay():
            with self.subTest(case=row["id"]):
                self.assertEqual(row["selected"], row["expected_keep"])
                self.assertFalse(row["core_errors"])

    def test_radar_does_not_fill_a_large_limit_with_weak_news(self):
        candidates = [value for case in CASES.values() if (value := classify(case))]
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts(candidates, 30)
        self.assertEqual({item["link"] for item in selected}, {CASES[name]["url"] for name in ("housing", "cyber_regulator")})

    def test_actual_compact_render_has_complete_source_bound_cores_and_links(self):
        candidates = [value for case in CASES.values() if (value := classify(case))]
        with patch.object(radar.base, "kst_now", return_value=NOW), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}), patch.object(radar, "collect_fx_snapshot", return_value={"rates": {}}):
            selected = radar.compact_quality_final_alerts(candidates, 7)
            report = radar.compact_report(selected, {}, {}, NOW)
            radar.guard_preopen_report(report)
        self.assertEqual(len(selected), 2)
        self.assertFalse(generated_guard.duplicate_event_errors(selected, radar))
        for item in selected:
            self.assertTrue(radar.core_sentence_is_complete(item["telegram_core_fact"]))
            self.assertLessEqual(len(item["telegram_core_fact"]), 100)
            self.assertIn(item["link"], report)
        self.assertNotIn("투자 포인트:", report)
        self.assertNotIn("[상 |", report)

    def test_housing_core_is_instruction_not_house_price_background(self):
        row = next(row for row in replay() if row["id"] == "housing")
        self.assertIn("LH", row["core"])
        self.assertIn("미분양", row["core"])
        self.assertIn("매수확약", row["core"])
        self.assertIn("지시했다고", row["core"])
        self.assertNotIn("매입했다", row["core"])
        self.assertNotIn("원인", row["core"])

    def test_network_policy_core_retains_schedule_scope_and_maximum(self):
        row = next(row for row in replay() if row["id"] == "cyber_regulator")
        for fact in ("금융위", "7일", "보안 목적", "49개사에서 75개사", "10개사에서 최대 15개사", "예정"):
            self.assertIn(fact, row["core"])
        self.assertNotIn("유출", row["core"])

    def test_visit_speculation_is_not_a_contact_milestone(self):
        for name in ("amd_hankyung", "amd_chosun", "amd_yonhap"):
            case = CASES[name]
            self.assertFalse(eligible(case["title"], radar.article_summary_body(case["body"])))

    def test_other_ceo_visit_speculation_is_not_a_business_negotiation(self):
        self.assertFalse(eligible("브로드컴 CEO 방한…AI 협력 넓힐까", "업계에서는 브로드컴 CEO가 국내 반도체 기업과 공급 협력을 논의할 가능성이 있다고 보고 있다."))

    def test_unscoped_housing_rhetoric_is_not_a_supply_decision(self):
        self.assertFalse(eligible("대통령, 부동산 공급 확대 강조", "대통령은 주택 공급 부족이 가격 불안의 원인이라고 분석했다. 그는 공급을 늘려야 한다고 강조했다."))

    def test_network_policy_core_cannot_use_prior_breach_counts(self):
        candidate = classify(CASES["cyber_regulator"])
        normalized = radar.normalize_alert_for_output(candidate)
        normalized["telegram_core_fact"] = "신한은행 고객 2만5000명의 정보가 유출됐으며 하나은행에서도 89명의 정보가 빠져나갔다."
        self.assertTrue(radar.source_core_fact_errors(normalized))

    def test_incident_headline_is_not_replaced_by_background_network_policy(self):
        title = "신한은행 고객정보 유출…망분리 완화에도 해킹 피해"
        self.assertEqual(materiality.focus_kind(title), "cyber_incident")

    def test_other_concrete_housing_policy_is_not_forced_into_lh_supply(self):
        title = "대통령, 부동산 취득세율 인하 정책 발표"
        body = "정부는 부동산 취득세율을 3%에서 2%로 인하하는 개정안을 발표했다."
        self.assertNotEqual(materiality.focus_kind(title), "housing_supply_policy")
        self.assertTrue(eligible(title, body))

    def test_future_meeting_interest_is_not_actual_supply_execution(self):
        self.assertFalse(eligible("AMD CEO 방한…반도체 협력 회동 주목", "AMD CEO가 국내 반도체 기업과 공급 협력을 논의할지 주목된다."))

    def test_named_current_supply_negotiations_survive(self):
        self.assertTrue(eligible("AMD·삼성전자, 데이터센터 반도체 협상", "AMD와 삼성전자는 2027년 데이터센터용 반도체 공급과 공동개발 협상을 진행 중이라고 밝혔다."))

    def test_real_agreement_survives_visit_context(self):
        self.assertTrue(eligible("리사 수 방한…AMD·삼성전자 공급 계약 체결", CONTRACT_BODY))

    def test_new_ipo_application_survives(self):
        self.assertTrue(eligible("솔리다임, 나스닥 상장 신청", "솔리다임은 미국 나스닥 상장을 위한 등록 서류를 제출하고 기업공개를 추진한다고 발표했다."))

    def test_column_with_a_new_sourced_decision_survives(self):
        self.assertTrue(eligible("[기자24시] 솔리다임 상장…새 투자 결정", "솔리다임은 생산시설 설비투자 예산 500억원을 확정했다고 공시했다."))

    def test_consumer_article_with_new_earnings_guidance_survives(self):
        self.assertTrue(eligible("애플, 신제품 출시…분기 가이던스 상향", "애플은 분기 매출 가이던스를 10% 상향했다고 발표했다."))

    def test_training_article_with_committed_new_budget_survives(self):
        self.assertTrue(eligible("정부, 반도체 인력양성 예산 확정", "정부는 반도체 인력양성 보조금 예산 500억원을 확정하고 신규 지원금을 배정했다."))

    def test_robot_strategy_with_a_new_order_survives(self):
        self.assertTrue(eligible("中전기차 공장은 로봇 실험장…공급 계약 체결", "BYD는 자동차 공장용 휴머노이드 200대 공급 계약을 체결했다고 발표했다."))

    def test_source_fact_identity_ignores_publisher_typography(self):
        first = alert()
        second = alert("삼성·AMD, 데이터센터 반도체 공동개발 계약", CONTRACT_BODY.replace("인공지능(AI)", "AI").replace("공급 계약", "공급계약"), "https://www.mk.co.kr/news/business/9999001")
        self.assertTrue(materiality.verified_source_fact_identity(first))
        self.assertEqual(materiality.verified_source_fact_identity(first), materiality.verified_source_fact_identity(second))

    def test_unverified_body_never_gets_a_fact_identity(self):
        first = alert()
        first["body_verified"] = False
        self.assertEqual(materiality.verified_source_fact_identity(first), "")

    def test_changed_quantity_is_a_new_fact(self):
        self.assertNotEqual(materiality.verified_source_fact_identity(alert()), materiality.verified_source_fact_identity(alert(body=CONTRACT_BODY.replace("100억원", "200억원"))))

    def test_changed_counterparty_is_a_new_fact(self):
        self.assertNotEqual(materiality.verified_source_fact_identity(alert()), materiality.verified_source_fact_identity(alert(body=CONTRACT_BODY.replace("삼성전자", "SK하이닉스"))))

    def test_changed_period_is_a_new_fact(self):
        self.assertNotEqual(materiality.verified_source_fact_identity(alert()), materiality.verified_source_fact_identity(alert(body=CONTRACT_BODY.replace("2027년", "2028년"))))

    def test_negotiation_and_signed_contract_are_distinct(self):
        unsigned = CONTRACT_BODY.replace("체결했다고", "협상 중이라고")
        self.assertNotEqual(materiality.verified_source_fact_identity(alert()), materiality.verified_source_fact_identity(alert(body=unsigned)))

    def test_later_same_kind_quantity_changes_identity(self):
        case = CASES["cyber_regulator"]
        first = alert(case["title"], case["body"], case["url"])
        second = alert(case["title"], case["body"].replace("최대 15개사", "최대 20개사"), case["url"])
        self.assertNotEqual(materiality.verified_source_fact_identity(first), materiality.verified_source_fact_identity(second))

    def test_additional_material_fact_changes_identity(self):
        first = alert()
        second = alert(body=CONTRACT_BODY + ADDITIONAL_FACT)
        self.assertNotEqual(materiality.verified_source_fact_identity(first), materiality.verified_source_fact_identity(second))

    def test_shorter_wire_copy_does_not_repeat_previously_sent_facts(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([alert(body=CONTRACT_BODY + ADDITIONAL_FACT)], NOW)
            shorter = alert("AMD·삼성, AI 칩 공급계약 발표", CONTRACT_BODY, "https://www.mk.co.kr/news/business/9999001")
            fresh, skipped = telegram.filter_previously_seen_alerts([shorter], NOW, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_additional_fact_is_not_suppressed_by_shared_primary_fact(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([alert()], NOW)
            followup = alert(body=CONTRACT_BODY + ADDITIONAL_FACT)
            fresh, skipped = telegram.filter_previously_seen_alerts([followup], NOW, "live")
            self.assertEqual(len(fresh), 1)
            self.assertFalse(skipped)

    def test_legacy_exact_url_receipt_still_protects_existing_send(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"):
            old = alert()
            key = "link:" + telegram.digest_seen(old["link"])
            telegram.SEEN_PATH.write_text(json.dumps({"seen": {key: {"title": old["news"], "link": old["link"], "first_seen_kst": NOW.isoformat(), "lanes": {"live": NOW.isoformat()}}}}), encoding="utf-8")
            fresh, skipped = telegram.filter_previously_seen_alerts([old], NOW, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_fact_aliases_survive_seen_state_reload(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([alert()], NOW)
            state = telegram.load_seen_state()
            state["seen"] = {key: value for key, value in state["seen"].items() if key.startswith("link:")}
            telegram.SEEN_PATH.write_text(json.dumps(state), encoding="utf-8")
            repeat = alert("삼성·AMD, AI 반도체 공동개발 계약", CONTRACT_BODY, "https://www.mk.co.kr/news/business/9999001")
            fresh, skipped = telegram.filter_previously_seen_alerts([repeat], NOW, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_generated_report_guard_also_rejects_shorter_duplicate(self):
        errors = generated_guard.duplicate_event_errors([alert(body=CONTRACT_BODY + ADDITIONAL_FACT), alert()], radar)
        self.assertEqual(len(errors), 1)

    def test_duplicate_across_runs_preserves_followup_and_lanes(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            first = alert()
            telegram.record_seen_alerts([first], NOW)
            second = alert("삼성·AMD, 반도체 공동개발 공급계약", CONTRACT_BODY.replace("인공지능(AI)", "AI"), "https://www.mk.co.kr/news/business/9999001")
            fresh, skipped = telegram.filter_previously_seen_alerts([second], NOW, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            changed = alert(body=CONTRACT_BODY.replace("100억원", "200억원"))
            fresh, skipped = telegram.filter_previously_seen_alerts([changed], NOW, "live")
            self.assertEqual(len(fresh), 1)
            self.assertFalse(skipped)
            fresh, _ = telegram.filter_previously_seen_alerts([second], NOW, "preopen")
            self.assertEqual(len(fresh), 1)
            with patch.dict(os.environ, {"RADAR_RUN_MODE": "preopen"}):
                telegram.record_seen_alerts(fresh, NOW)
            fresh, skipped = telegram.filter_previously_seen_alerts([second], NOW, "preopen")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_same_run_copies_are_selected_once(self):
        first = classify({"title": "AMD·삼성전자, AI 반도체 공급 계약 체결", "body": CONTRACT_BODY, "published": NOW.isoformat(), "url": "https://www.etnews.com/20261005009901"})
        second = copy.deepcopy(first)
        second.update(news="삼성·AMD, 반도체 공동개발 계약", source_title="삼성·AMD, 반도체 공동개발 계약", original_news="삼성·AMD, 반도체 공동개발 계약", link="https://www.mk.co.kr/news/business/9999001", publisher="매일경제")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts([first, second], 30)
        self.assertEqual(len(selected), 1)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IncrementalNewsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    output = {"passed": result.wasSuccessful(), "tests": result.testsRun, "materiality_version": materiality.VERSION,
              "original_count": 10, "unique_article_count": 10, "unique_event_count": FIXTURE["unique_event_count"],
              "eligible_unique_events": 2, "excluded_unique_events": 6, "event_groups": FIXTURE["event_groups"], "external_delivery": False,
              "seen_state_modified": False, "cases": replay()}
    path = ROOT / "out/gamejoa_incremental_news_verification.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not result.wasSuccessful():
        raise SystemExit(1)
    print(f"gamejoa_incremental_news_quality=passed tests={result.testsRun} cases=10 external_delivery=false")

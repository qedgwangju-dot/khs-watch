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
LIVE_FIXTURE = json.loads((ROOT / "data/gamejoa_live_selection_fixtures_20261005.json").read_text(encoding="utf-8"))
LIVE_CASES = {case["id"]: case for case in LIVE_FIXTURE["cases"]}
FOREGROUND_FIXTURE = json.loads((ROOT / "data/gamejoa_foreground_selection_fixtures_20261005.json").read_text(encoding="utf-8"))
FOREGROUND_CASES = {case["id"]: case for case in FOREGROUND_FIXTURE["cases"]}
RUNTIME_FIXTURE = json.loads((ROOT / "data/gamejoa_runtime_selection_fixtures_20261005.json").read_text(encoding="utf-8"))
RUNTIME_CASES = {case["id"]: case for case in RUNTIME_FIXTURE["cases"]}
REPORTED_FIXTURE = json.loads((ROOT / "data/gamejoa_reported_event_fixtures_20261005.json").read_text(encoding="utf-8"))
REPORTED_CASES = {case["id"]: case for case in REPORTED_FIXTURE["cases"]}
EQUIVALENCE_FIXTURE = json.loads((ROOT / "data/gamejoa_event_equivalence_fixtures_20261005.json").read_text(encoding="utf-8"))
EQUIVALENCE_CASES = {case["id"]: case for case in EQUIVALENCE_FIXTURE["cases"]}
LIVE_NOW = NOW.replace(hour=19)
CONTRACT_BODY = "AMD는 삼성전자와 2027년 데이터센터용 인공지능(AI) 반도체 공동개발을 위한 100억원 규모의 공급 계약을 체결했다고 밝혔다."
ADDITIONAL_FACT = " AMD는 해당 공급 계약을 위한 반도체 설비투자 예산 500억원을 확정했다고 공시했다."
PUBLISHERS = {"yna.co.kr": "연합뉴스", "hankyung.com": "한국경제", "etnews.com": "전자신문",
              "chosun.com": "조선비즈", "mk.co.kr": "매일경제", "newsis.com": "뉴시스"}


def alert(title="AMD·삼성전자, AI 반도체 공급 계약 체결", body=CONTRACT_BODY, url="https://www.etnews.com/20261005009901"):
    return {"news": title, "source_title": title, "original_news": title, "source_body": body,
            "source_abstract": body, "telegram_core_fact": body, "body_verified": True,
            "korean_business_news": True, "published": NOW.isoformat(), "publisher": "전자신문", "link": url}


def classify(case, now=NOW):
    return production.contract.strict.classify({
        "title": case["title"], "source_title": case["title"], "source_body": case["body"],
        "source_abstract": case["body"], "body_verified": True, "layer": "trusted",
        "published": radar.base.parse_date(case["published"]), "link": case["url"],
        "publisher": next((name for host, name in PUBLISHERS.items() if host in case["url"]), ""),
    }, now)


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
    def event_alert(self, key):
        case = EQUIVALENCE_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_korean_money_units_have_exact_equivalence(self):
        for raw, expected in (("11억 7천만", "1170000000"), ("11억7000만", "1170000000"),
                              ("1조7000억", "1700000000000"), ("3천5백만", "35000000"),
                              ("1.5억", "150000000"), ("3,500", "3500")):
            with self.subTest(raw=raw):
                self.assertEqual(materiality.korean_amount_value(raw), expected)
        for raw in ("금액 미공개", "1억2조", "억", "1만만", ""):
            self.assertFalse(materiality.korean_amount_value(raw))

    def test_licensing_short_and_long_wire_have_one_event_identity(self):
        short = self.event_alert("exclusive_license_short_copy")
        long = self.event_alert("exclusive_license_long_copy")
        self.assertNotEqual(materiality.verified_source_fact_identity(short), materiality.verified_source_fact_identity(long))
        self.assertEqual(materiality.source_event_identity(short), materiality.source_event_identity(long))
        terms = materiality.licensing_event_terms(short["source_title"], short["source_body"])
        self.assertEqual(terms["upfront"], ["달러", "100000000"])
        self.assertEqual(terms["milestone"], ["달러", "1170000000", True])

    def test_changed_license_amount_asset_partner_scope_runway_remain_new(self):
        first = self.event_alert("exclusive_license_long_copy")
        identity = materiality.source_event_identity(first)
        for old, new in (("1억 달러", "2억 달러"), ("11억7000만", "12억7000만"),
                         ("AL050", "AL051"), ("제넨텍", "다른제약사"),
                         ("글로벌", "미국내"), ("2029년", "2030년")):
            revised = {**first, "source_title": first["source_title"].replace(old, new),
                       "source_body": first["source_body"].replace(old, new)}
            with self.subTest(term=old):
                self.assertNotEqual(materiality.source_event_identity(revised), identity)

    def test_new_numeric_royalty_terms_survive_duplicate_filter(self):
        first = self.event_alert("exclusive_license_short_copy")
        revised = {**first, "source_body": first["source_body"] + " 로열티율은 12%로 확정됐다."}
        self.assertNotEqual(materiality.source_event_identity(first), materiality.source_event_identity(revised))

    def test_unverified_or_negotiating_license_does_not_claim_signed_identity(self):
        first = self.event_alert("exclusive_license_long_copy")
        self.assertFalse(materiality.source_event_identity({**first, "body_verified": False}))
        self.assertFalse(materiality.source_event_identity({**first, "source_title": first["source_title"] + " 협상 중"}))

    def test_same_license_is_once_in_batch_and_report_guard(self):
        candidates = [classify(EQUIVALENCE_CASES[key], LIVE_NOW.replace(hour=21))
                      for key in ("exclusive_license_short_copy", "exclusive_license_long_copy")]
        self.assertTrue(all(candidates))
        with patch.object(radar.base, "kst_now", return_value=LIVE_NOW.replace(hour=21)):
            selected = radar.quality_display_alerts(candidates, 30)
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(generated_guard.duplicate_event_errors(candidates, radar)), 1)

    def test_same_license_is_once_across_runs_but_new_terms_are_sent(self):
        now = LIVE_NOW.replace(hour=21)
        short, long = self.event_alert("exclusive_license_short_copy"), self.event_alert("exclusive_license_long_copy")
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([long], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([short], now, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            changed = {**short, "source_body": short["source_body"].replace("1억 달러", "2억 달러")}
            fresh, skipped = telegram.filter_previously_seen_alerts([changed], now, "live")
            self.assertEqual(len(fresh), 1)
            self.assertFalse(skipped)

    def test_odd_lot_shares_and_units_are_one_review_event(self):
        case = RUNTIME_CASES["odd_lot_trading_rule"]
        shares = alert(case["title"], case["body"], case["url"])
        units = self.event_alert("odd_lot_units_copy")
        self.assertTrue(materiality.source_event_identity(shares))
        self.assertEqual(materiality.source_event_identity(shares), materiality.source_event_identity(units))

    def test_new_lot_size_or_actual_permission_is_new_event(self):
        first = self.event_alert("odd_lot_units_copy")
        identity = materiality.source_event_identity(first)
        changed = {**first, "source_body": first["source_body"].replace("20좌", "30좌")}
        self.assertNotEqual(materiality.source_event_identity(changed), identity)
        approved = {**first, "source_body": "금융위원회는 단일종목 레버리지 상품의 매매수량단위를 20좌로 확대했다. 단주 처분을 위한 시간외 종가매매를 허용한다고 확정 발표했다."}
        self.assertNotEqual(materiality.source_event_identity(approved), identity)
        self.assertTrue(materiality.source_event_identity(approved))

    def test_trading_rule_specific_disposal_date_remains_new(self):
        first = self.event_alert("odd_lot_units_copy")
        revised = {**first, "source_body": first["source_body"].replace("시간 외 종가 매매를 통해", "2026년 12월 1일부터 시간 외 종가 매매를 통해")}
        self.assertNotEqual(materiality.source_event_identity(first), materiality.source_event_identity(revised))

    def test_ordinary_twenty_share_trade_is_not_the_regulatory_event(self):
        body = "삼성전자 임원은 보통주 20주를 매수했다고 공시했다."
        self.assertFalse(materiality.odd_lot_rule_terms("삼성전자 임원 20주 매수", body))

    def test_audited_aliases_need_an_existing_sent_receipt(self):
        proofs = json.loads(telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))
        proof = next(row for row in proofs["entries"] if row["link"] == EQUIVALENCE_CASES["exclusive_license_long_copy"]["url"])
        state = {"seen": {}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertFalse(state["seen"])
        state["seen"]["link:test"] = {"title": proof["source_title"], "link": proof["link"], "first_seen_kst": "2026-10-05T20:57:26+09:00"}
        telegram.migrate_seen_verified_event_aliases(state)
        receipt = state["seen"]["event:" + telegram.digest_seen(proof["source_event_identity"])]
        self.assertEqual(receipt["event_alias_evidence_message_id"], 2231)

    def test_aliases_reject_unproved_identity_families(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "proof.json"
            path.write_text(json.dumps({"entries": [{"source_event_identity": "source_event:v2:company:unknown"}]}), encoding="utf-8")
            with patch.object(telegram, "VERIFIED_EVENT_ALIAS_PATH", path):
                with self.assertRaises(ValueError):
                    telegram.migrate_seen_verified_event_aliases({"seen": {}})

    def test_audited_event_aliases_match_the_replayed_source_terms(self):
        proofs = json.loads(telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))
        for key in ("exclusive_license_short_copy", "exclusive_license_long_copy", "odd_lot_units_copy"):
            case = EQUIVALENCE_CASES[key]
            proof = next(row for row in proofs["entries"] if row["link"] == case["url"])
            with self.subTest(case=key):
                self.assertEqual(proof["source_body_sha256"], case["full_body_sha256"])
                self.assertEqual(proof["source_event_identity"], materiality.source_event_identity(self.event_alert(key)))
                self.assertEqual(proof["run_id"], EQUIVALENCE_FIXTURE["run_id"])
                self.assertEqual(proof["message_id"], EQUIVALENCE_FIXTURE["message_id"])

    def test_maritime_core_retains_actual_reports_and_unknown_incident_time(self):
        case = EQUIVALENCE_CASES["maritime_attack_not_oil_counterfactual"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW.replace(hour=21)))
        fact = item["telegram_core_fact"]
        for term in ("UKMTO", "지난달 28일", "이달 3일", "7건", "보고", "4일", "발생 시점은 미공개"):
            self.assertIn(term, fact)
        self.assertFalse(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_maritime_report_count_is_source_bound_not_a_canned_core(self):
        case = EQUIVALENCE_CASES["maritime_attack_not_oil_counterfactual"]
        fact = radar.source_headline_event_fact(case["title"], case["body"].replace("7건", "9건").replace("지난달 28일", "지난달 27일"))
        self.assertIn("9건", fact)
        self.assertIn("지난달 27일", fact)
        self.assertNotIn("7건", fact)

    def test_maritime_hypothetical_oil_impact_is_not_the_reported_attack(self):
        case = EQUIVALENCE_CASES["maritime_attack_not_oil_counterfactual"]
        self.assertFalse(materiality.focus_matches(case["title"], case["old_core"]))

    def test_six_actual_sent_events_retain_reported_action_not_commentary(self):
        self.assertEqual(len(REPORTED_CASES), 6)
        for case in REPORTED_CASES.values():
            with self.subTest(case=case["id"]):
                candidate = classify(case, LIVE_NOW.replace(hour=21))
                self.assertIsNotNone(candidate)
                item = radar.normalize_alert_for_output(candidate)
                self.assertFalse(radar.source_core_fact_errors(item))
                self.assertTrue(radar.core_sentence_is_complete(item["telegram_core_fact"]))
                self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_labelled_ai_commentary_is_not_reported_article_evidence(self):
        for case in REPORTED_CASES.values():
            if case["body"].startswith("💡 AI 분석"):
                lines = case["body"].splitlines()
                with self.subTest(case=case["id"]):
                    self.assertNotIn(lines[1], radar.article_summary_body(case["body"]))
                    self.assertTrue(materiality.source_reported_body(case["body"]).startswith(lines[2]))
        ai_only = "AI 분석\n반도체 공급 계약 100억원 체결로 실적 기대가 커졌어요."
        self.assertFalse(eligible("반도체 공급 계약 체결", ai_only))

    def test_embedded_ai_reference_is_not_removed_as_a_leading_card(self):
        body = CONTRACT_BODY + "\n기업은 AI 분석 솔루션도 제공하고 있다."
        self.assertEqual(materiality.source_reported_body(body), body)

    def test_reported_cleanup_does_not_invalidate_previous_body_receipts(self):
        case = REPORTED_CASES["asset_sale_gross_and_buyback_authorization"]
        item = alert(case["title"], case["body"], case["url"])
        previous_digest = hashlib.sha256(materiality.canonical_source_fact(materiality.source_article_body(case["body"])).encode("utf-8")).hexdigest()
        self.assertEqual(materiality.verified_source_body_digest(item), previous_digest)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"):
            receipt = {"title": case["title"], "link": case["url"], "first_seen_kst": NOW.isoformat(),
                       "lanes": {"live": NOW.isoformat()}, "source_body_digest": previous_digest,
                       "source_fact_identity": "source_facts:v1:previous-rule", "source_fact_keys": []}
            telegram.SEEN_PATH.write_text(json.dumps({"seen": {"link:" + telegram.digest_seen(case["url"]): receipt}}), encoding="utf-8")
            before = telegram.SEEN_PATH.read_bytes()
            fresh, skipped = telegram.filter_previously_seen_alerts([item], LIVE_NOW.replace(hour=21), "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            self.assertEqual(telegram.SEEN_PATH.read_bytes(), before)

    def test_acquisition_retains_signed_agreement_and_conditional_future_close(self):
        case = REPORTED_CASES["signed_acquisition_with_future_closing"]
        fact = radar.source_headline_event_fact(case["title"], case["body"])
        for term in ("어드밴스드 드레니쥐 시스템즈", "스톰트랩", "5억3000만 달러", "최종 계약", "규제 승인", "2026년 4분기", "예정"):
            self.assertIn(term, fact)
        self.assertNotIn("인수 완료", fact)
        self.assertGreater(len(fact), 100)

    def test_acquisition_amount_and_closing_year_are_source_bound(self):
        case = REPORTED_CASES["signed_acquisition_with_future_closing"]
        fact = radar.source_headline_event_fact(case["title"].replace("5억3000만", "6억4000만"), case["body"].replace("5억3000만", "6억4000만").replace("2026년 역년", "2027년 역년"))
        self.assertIn("6억4000만 달러", fact)
        self.assertIn("2027년 4분기", fact)
        self.assertNotIn("5억3000만", fact)

    def test_manufacturing_contract_retains_subsidiary_partner_and_permission(self):
        case = REPORTED_CASES["manufacturing_contract_not_prior_license"]
        fact = radar.source_headline_event_fact(case["title"], case["body"])
        for term in ("사이언스 바이오메디컬", "TIRC", "베누비아", "이보가인", "제조 계약을 체결", "DEA", "규제 승인"):
            self.assertIn(term, fact)
        self.assertNotIn("사이언스랩스", fact)
        self.assertNotIn("승인 완료", fact)

    def test_cfo_change_retains_company_guidance_not_analyst_consensus(self):
        case = REPORTED_CASES["cfo_departure_company_guidance"]
        fact = radar.source_headline_event_fact(case["title"], case["body"])
        for term in ("인스메드", "CFO", "10월 30일", "2026년 연간", "유지", "후임"):
            self.assertIn(term, fact)
        self.assertNotIn("198.15%", fact)
        self.assertNotIn("18억800만", fact)

    def test_buyback_end_retains_horizon_and_upcoming_earnings_date(self):
        case = REPORTED_CASES["buyback_ending_not_prior_week_flow"]
        fact = radar.source_headline_event_fact(case["title"], case["body"])
        for term in ("삼성전자", "이달 중순", "종료 예정", "8일", "3분기 잠정실적"):
            self.assertIn(term, fact)
        self.assertNotIn("7조3845", fact)
        self.assertNotIn("100조원", fact)

    def test_asset_sale_retains_gross_proceeds_and_authorization_not_spending(self):
        case = REPORTED_CASES["asset_sale_gross_and_buyback_authorization"]
        fact = radar.source_headline_event_fact(case["title"], case["body"])
        for term in ("지오 그룹", "3곳", "9억5000만 달러", "매각 완료", "승인 한도", "12억5000만 달러"):
            self.assertIn(term, fact)
        self.assertNotIn("7억500만", fact)
        self.assertNotIn("매입 완료", fact)

    def test_us_fund_performance_retains_population_period_and_returns(self):
        case = REPORTED_CASES["us_fund_performance_not_domestic_decline"]
        fact = radar.source_headline_event_fact(case["title"], case["body"])
        for term in ("미국 상장", "ARKG", "지난 2일", "3개월", "24.8%", "연초 이후", "83.5%"):
            self.assertIn(term, fact)
        self.assertNotIn("국내", fact)

    def test_single_fund_historical_return_is_not_promoted_by_macro_background(self):
        case = REPORTED_CASES["us_fund_performance_not_domestic_decline"]
        self.assertFalse(eligible(case["title"], case["body"]))

    def test_reported_events_render_complete_with_inline_fx_inside_limit(self):
        now = LIVE_NOW.replace(hour=21)
        candidates = [classify(case, now) for case in REPORTED_CASES.values()]
        snapshot = {"rates": {"USD": {"value": 1420.0, "status": "최근거래", "reference_time_kst": now.isoformat(),
                    "query_time_kst": now.isoformat(), "source": "Test only", "url": "https://example.com/test-fx"}}}
        with patch.object(radar.base, "kst_now", return_value=now), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}), patch.object(radar, "collect_fx_snapshot", return_value=snapshot):
            selected = radar.compact_quality_final_alerts(candidates, 30)
            report = radar.compact_report(selected, {}, {}, now)
            radar.guard_preopen_report(report)
        self.assertEqual({item["link"] for item in selected}, {case["url"] for case in REPORTED_CASES.values() if case["expected_keep"]})
        for item in selected:
            self.assertFalse(radar.source_core_fact_errors(item))
            self.assertTrue(radar.core_sentence_is_complete(item["telegram_core_fact"]))
            self.assertLessEqual(len(item["telegram_core_fact"]), radar.GAMEJOA_CORE_MAX_CHARS)
            self.assertIn(item["link"], report)
        self.assertIn("(약", report)
        self.assertIn("9억5000만 달러(약 1조3,490억원)", report)
        self.assertIn("12억5000만 달러(약 1조7,750억원)", report)
        self.assertFalse(generated_guard.duplicate_event_errors(selected, radar))

    def test_small_trillion_conversion_does_not_round_away_material_amount(self):
        self.assertEqual(radar.format_krw_amount(1_349_000_000_000), "1조3,490억원")
        self.assertEqual(radar.format_krw_amount(1_775_000_000_000), "1조7,750억원")
        self.assertEqual(radar.format_krw_amount(99_999_990_000_000), "100조원")

    def test_very_large_conversion_retains_requested_whole_trillion_rounding(self):
        self.assertEqual(radar.format_krw_amount(1_388_850_000_000_000), "1,389조원")
        self.assertEqual(radar.format_krw_amount(2_485_600_000_000_000), "2,486조원")

    def test_real_runtime_report_is_replayed_with_its_three_original_bodies(self):
        self.assertEqual(len(RUNTIME_CASES), 3)
        for case in RUNTIME_CASES.values():
            candidate = classify(case, LIVE_NOW.replace(hour=20))
            with patch.object(radar.base, "kst_now", return_value=LIVE_NOW.replace(hour=20)):
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
            with self.subTest(case=case["id"]):
                self.assertEqual(len(selected), 1)
                self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_quarter_volume_retains_issuer_units_delivery_basis_and_growth(self):
        case = RUNTIME_CASES["quarter_delivery_volume"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW.replace(hour=20)))
        for term in ("니우 테크놀러지스", "2026년 3분기", "출고 기준", "53만7457대", "15.4%", "4만7051대", "226.3%"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_single_quarter_cannot_be_replaced_by_year_to_date(self):
        self.assertFalse(materiality.period_matches("3분기 판매 54만대", "1~3분기 누적 판매량은 123만대로 증가했다."))

    def test_volume_growth_percentage_without_absolute_units_is_preserved(self):
        self.assertTrue(eligible("아이폰 리뷰…분기 판매량 12% 증가", "아이폰의 분기 판매량이 12% 증가했다고 회사가 밝혔다."))

    def test_primary_quarter_with_explicit_cumulative_context_is_preserved(self):
        self.assertTrue(materiality.period_matches("3분기 판매 54만대", "3분기 판매량은 54만대다. 1~3분기 누적 판매량은 123만대다."))

    def test_odd_lot_core_retains_lot_exception_and_pending_stage(self):
        case = RUNTIME_CASES["odd_lot_trading_rule"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW.replace(hour=20)))
        for term in ("금융위", "단일종목 레버리지 ETF", "20주 미만 단주", "시간외 종가매매", "검토 중", "내달", "예정"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertNotIn("발행가격", item["telegram_core_fact"])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_odd_lot_quantity_is_source_bound_not_hardcoded(self):
        case = RUNTIME_CASES["odd_lot_trading_rule"]
        fact = radar.source_headline_event_fact(case["title"].replace("20주", "10주"), case["body"].replace("20주", "10주"))
        self.assertIn("10주 미만 단주", fact)
        self.assertNotIn("20주", fact)

    def test_final_remote_foreground_report_is_replayed_with_source_bodies(self):
        self.assertEqual(len(FOREGROUND_CASES), 4)
        for case in FOREGROUND_CASES.values():
            candidate = classify(case, LIVE_NOW)
            with patch.object(radar.base, "kst_now", return_value=LIVE_NOW):
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
            with self.subTest(case=case["id"]):
                self.assertEqual(bool(selected), case["expected_keep"])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))

    def test_standard_core_names_the_issuer_code_and_scope(self):
        case = FOREGROUND_CASES["photonics_standard"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW))
        for term in ("제덱", "JESD264", "실리콘 포토닉스", "발표했다", "구성요소 검증", "제조 공정"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_foreground_compact_render_retains_three_source_events_only(self):
        candidates = [value for case in FOREGROUND_CASES.values() if (value := classify(case, LIVE_NOW))]
        with patch.object(radar.base, "kst_now", return_value=LIVE_NOW), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}), patch.object(radar, "collect_fx_snapshot", return_value={"rates": {}}):
            selected = radar.compact_quality_final_alerts(candidates, 30)
            report = radar.compact_report(selected, {}, {}, LIVE_NOW)
            radar.guard_preopen_report(report)
        self.assertEqual(len(selected), 3)
        self.assertFalse(generated_guard.duplicate_event_errors(selected, radar))
        for item in selected:
            self.assertFalse(radar.source_core_fact_errors(item))
            self.assertIn(item["link"], report)
            self.assertTrue(radar.core_sentence_is_complete(item["telegram_core_fact"]))

    def test_capacity_is_not_employment_macro_data(self):
        audit = materiality.assess("고용량 데이터를 처리하는 AI 데이터센터", "고용량 데이터를 처리하는 AI 데이터센터 산업의 수요가 증가하고 있다.")
        self.assertNotIn("rates_fx_or_macro", {e["kind"] for e in audit["evidence"]})
        self.assertNotEqual(materiality.focus_kind("고용량 데이터 처리 기술"), "macro_release")

    def test_real_employment_data_is_preserved(self):
        audit = materiality.assess("미국 고용 증가 둔화", "미국 고용은 10만명 증가하며 예상치를 밑돌았다.")
        self.assertIn("rates_fx_or_macro", {e["kind"] for e in audit["evidence"]})

    def test_import_share_retains_cumulative_period_and_decimal_change(self):
        case = FOREGROUND_CASES["energy_import_mix"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW))
        for term in ("올해 1~8월", "국내 원유 도입 비중", "사우디산 29.90%", "전월 누적 30.91%", "1.01%p"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_foreign_flow_keeps_issuers_period_and_separate_amounts(self):
        case = FOREGROUND_CASES["foreign_issuer_weekly_flow"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW))
        for term in ("9월28일~10월2일", "외국인", "SK하이닉스 4조3691억원", "삼성전자 3조2174억원", "순매도"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertNotIn("기관", item["telegram_core_fact"])
        self.assertNotIn("9조", item["telegram_core_fact"])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_institutional_flow_never_uses_foreign_investor_amount(self):
        case = FOREGROUND_CASES["foreign_issuer_weekly_flow"]
        fact = radar.source_headline_event_fact("기관, 삼성전자·SK하이닉스 순매도", case["body"])
        self.assertIn("삼성전자 8445억원", fact)
        self.assertIn("SK하이닉스 4681억원", fact)
        self.assertNotIn("4조3691억원", fact)

    def test_actor_trade_reversal_is_not_rewritten_in_the_opposite_direction(self):
        body = "지난주(9월28일~10월2일) 수급을 집계했다.\n외국인은 삼성전자(-3조2174억원)를 순매도했다."
        self.assertFalse(radar.source_headline_event_fact("외국인, 삼성전자 순매수", body))

    def test_routine_foreign_stock_rank_is_not_a_market_catalyst(self):
        case = FOREGROUND_CASES["retail_foreign_rank"]
        audit = materiality.assess(case["title"], case["body"])
        self.assertFalse(audit["equity_publication"]["eligible"])
        self.assertEqual(audit["equity_publication"]["reason"], "routine_retail_foreign_stock_ranking_not_market_catalyst")

    def test_foreign_rank_article_with_a_new_source_contract_is_preserved(self):
        title = "테슬라 순매수 1위[서학픽]…신규 공급 계약 체결"
        audit = materiality.assess(title, "테슬라는 데이터센터용 반도체 공급 계약을 체결했다고 발표했다.")
        self.assertTrue(audit["equity_publication"]["eligible"])

    def test_remote_generated_report_is_replayed_with_source_bodies(self):
        self.assertEqual(len(LIVE_CASES), 6)
        for case in LIVE_CASES.values():
            candidate = classify(case, LIVE_NOW)
            with patch.object(radar.base, "kst_now", return_value=LIVE_NOW):
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
            with self.subTest(case=case["id"]):
                self.assertEqual(bool(selected), case["expected_keep"])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))

    def test_acquisition_talks_never_become_a_confirmed_purchase(self):
        case = LIVE_CASES["acquisition_talks"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW))
        for term in ("슈나이더 일렉트릭", "PTC", "200억달러", "논의 중", "보도됐다"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertIn("acquisition_negotiation_reported_as_confirmed", radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_acquisition_summary_is_bound_to_other_source_parties_and_amount(self):
        title = "브로드컴, 소프트웨어 기업 인수 협상"
        body = "브로드컴은 XYZ를 약 50억달러에 인수한다. 로이터는 브로드컴이 XYZ를 인수하는 방안을 논의 중이라고 보도했다."
        fact = radar.acquisition_negotiation_fact(title, body)
        for term in ("브로드컴", "XYZ", "50억달러", "논의 중"):
            self.assertIn(term, fact)
        self.assertNotIn("PTC", fact)

    def test_completed_transaction_is_not_downgraded_to_earlier_talks(self):
        self.assertFalse(radar.acquisition_negotiation_fact(
            "브로드컴, XYZ 인수 완료", "로이터는 브로드컴이 XYZ를 인수하는 방안을 논의 중이라고 보도했다. 브로드컴은 XYZ 인수를 완료했다고 발표했다.",
        ))

    def test_earnings_core_uses_the_headline_metric_and_retains_forecast(self):
        case = LIVE_CASES["earnings_consensus"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW))
        for term in ("에프앤가이드", "3분기", "영업이익 예상", "108조1312억원", "8일", "예정"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_etf_core_names_the_launch_and_date_not_a_general_trend(self):
        case = LIVE_CASES["named_etf_launch"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW))
        for term in ("KB자산운용", "20일", "RISE 반도체소부장액티브 ETF", "상장", "예정"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertFalse(eligible(case["title"], case["old_core"]))

    def test_asian_market_core_retains_probability_change_and_index_close(self):
        case = LIVE_CASES["asian_market_response"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW))
        for term in ("CME 페드워치", "64%", "20% 미만", "닛케이225", "2.40%", "상승 마감"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_partial_sovereign_issuance_article_cannot_use_fx_background(self):
        case = LIVE_CASES["partial_sovereign_issuance"]
        self.assertFalse(eligible(case["title"], radar.article_summary_body(case["body"])))
        self.assertFalse(materiality.core_focus_aligned(case["title"], case["old_core"]))

    def test_actual_new_bank_rate_action_remains_eligible(self):
        self.assertTrue(eligible("은행 주담대 금리 더 오르나[금리 쇼크]", "은행은 주담대 금리를 0.2%포인트 인상했다고 발표했다."))

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
            self.assertLessEqual(len(item["telegram_core_fact"]), radar.GAMEJOA_CORE_MAX_CHARS)
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

    def test_related_news_cannot_invent_a_new_event_identity(self):
        first = alert()
        footer = alert(body=CONTRACT_BODY + "\n관련 뉴스\n" + ADDITIONAL_FACT)
        self.assertEqual(materiality.verified_source_fact_identity(first), materiality.verified_source_fact_identity(footer))
        self.assertEqual(materiality.verified_source_fact_keys(first), materiality.verified_source_fact_keys(footer))

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

    def test_actual_legacy_fact_receipt_blocks_tracking_url_repeat(self):
        case = RUNTIME_CASES["foreign_issuer_weekly_flow"]
        receipt = RUNTIME_FIXTURE["previous_foreign_flow_receipt"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW.replace(hour=20)))
        self.assertNotEqual(materiality.verified_source_fact_identity(item), receipt["source_fact_identity"])
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"):
            key = "link:" + telegram.digest_seen(receipt["link"])
            telegram.SEEN_PATH.write_text(json.dumps({"seen": {key: receipt}}), encoding="utf-8")
            before = telegram.SEEN_PATH.read_bytes()
            fresh, skipped = telegram.filter_previously_seen_alerts([item], LIVE_NOW.replace(hour=20), "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            self.assertEqual(before, telegram.SEEN_PATH.read_bytes())

    def test_known_tracking_url_normalization_preserves_article_parameters(self):
        self.assertEqual(telegram.canonical_article_url("https://www.etoday.co.kr/news/view/2632237?trc=main_list_pick"),
                         "https://www.etoday.co.kr/news/view/2632237")
        self.assertNotEqual(telegram.canonical_article_url("https://www.edaily.co.kr/News/Read?newsId=100&mediaCodeNo=257"),
                            telegram.canonical_article_url("https://www.edaily.co.kr/News/Read?newsId=200&mediaCodeNo=257"))
        self.assertIn("trc=article_id", telegram.canonical_article_url("https://example.com/news?trc=article_id"))

    def test_legacy_unknown_revision_is_not_republished_as_proven_new(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"):
            old = alert()
            key = "link:" + telegram.digest_seen(old["link"])
            receipt = {"title": old["news"], "link": old["link"], "first_seen_kst": NOW.isoformat(),
                       "lanes": {"live": NOW.isoformat()}, "source_fact_identity": "source_facts:v1:old-rule"}
            telegram.SEEN_PATH.write_text(json.dumps({"seen": {key: receipt}}), encoding="utf-8")
            fresh, _ = telegram.filter_previously_seen_alerts([alert(body=CONTRACT_BODY + ADDITIONAL_FACT)], NOW, "live")
            self.assertFalse(fresh)

    def test_body_receipt_is_recorded_and_survives_fact_rule_upgrade(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            first = alert()
            telegram.record_seen_alerts([first], NOW)
            state = telegram.load_seen_state()
            state["seen"] = {key: {**value, "source_fact_identity": "source_facts:v1:old-rule", "source_fact_keys": []}
                             for key, value in state["seen"].items() if key.startswith("link:")}
            for value in state["seen"].values():
                self.assertEqual(value["source_body_digest"], materiality.verified_source_body_digest(first))
            telegram.SEEN_PATH.write_text(json.dumps(state), encoding="utf-8")
            repeat = {**first, "link": first["link"] + "?trc=main_list_pick"}
            fresh, skipped = telegram.filter_previously_seen_alerts([repeat], NOW, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_legacy_fact_receipt_does_not_hide_new_terms_on_a_new_source_url(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"):
            old = alert()
            key = "link:" + telegram.digest_seen(old["link"])
            receipt = {"title": old["news"], "link": old["link"], "first_seen_kst": NOW.isoformat(),
                       "lanes": {"live": NOW.isoformat()}, "source_fact_identity": "source_facts:v1:old-rule"}
            telegram.SEEN_PATH.write_text(json.dumps({"seen": {key: receipt}}), encoding="utf-8")
            followup = alert(body=CONTRACT_BODY.replace("100억원", "200억원"), url=old["link"] + "new")
            fresh, skipped = telegram.filter_previously_seen_alerts([followup], NOW, "live")
            self.assertEqual(len(fresh), 1)
            self.assertFalse(skipped)

    def test_body_receipt_does_not_hide_a_sourced_revision(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([alert()], NOW)
            for body in (CONTRACT_BODY.replace("100억원", "200억원"), CONTRACT_BODY.replace("2027년", "2028년"),
                         CONTRACT_BODY.replace("삼성전자", "SK하이닉스"), CONTRACT_BODY + ADDITIONAL_FACT):
                with self.subTest(body=body):
                    fresh, skipped = telegram.filter_previously_seen_alerts([alert(body=body)], NOW, "live")
                    self.assertEqual(len(fresh), 1)
                    self.assertFalse(skipped)

    def test_body_digest_ignores_rotating_related_news(self):
        first = alert()
        footer = alert(body=CONTRACT_BODY + "\n관련 뉴스\n" + ADDITIONAL_FACT)
        self.assertEqual(materiality.verified_source_body_digest(first), materiality.verified_source_body_digest(footer))

    def test_unverified_body_does_not_create_a_body_receipt(self):
        self.assertFalse(materiality.verified_source_body_digest({**alert(), "body_verified": False}))

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
              "seen_state_modified": False, "cases": replay(), "remote_replay_run_id": LIVE_FIXTURE["run_id"],
              "remote_replay_articles": len(LIVE_CASES), "foreground_replay_run_id": FOREGROUND_FIXTURE["run_id"],
              "foreground_replay_articles": len(FOREGROUND_CASES), "runtime_replay_run_id": RUNTIME_FIXTURE["run_id"],
              "runtime_replay_articles": len(RUNTIME_CASES), "reported_event_run_id": REPORTED_FIXTURE["run_id"],
              "reported_event_articles": len(REPORTED_CASES)}
    path = ROOT / "out/gamejoa_incremental_news_verification.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not result.wasSuccessful():
        raise SystemExit(1)
    print(f"gamejoa_incremental_news_quality=passed tests={result.testsRun} cases=10 external_delivery=false")

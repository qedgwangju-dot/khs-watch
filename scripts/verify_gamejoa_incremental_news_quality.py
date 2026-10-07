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
DECISION_FIXTURE = json.loads((ROOT / "data/gamejoa_decision_focus_fixtures_20261005.json").read_text(encoding="utf-8"))
DECISION_CASES = {case["id"]: case for case in DECISION_FIXTURE["cases"]}
NOISE_FIXTURE = json.loads((ROOT / "data/gamejoa_market_noise_fixtures_20261005.json").read_text(encoding="utf-8"))
NOISE_CASES = {case["id"]: case for case in NOISE_FIXTURE["cases"]}
BROKER_FIXTURE = json.loads((ROOT / "data/gamejoa_broker_report_fixtures_20261006.json").read_text(encoding="utf-8"))
BROKER_CASES = {case["id"]: case for case in BROKER_FIXTURE["cases"]}
FINAL_RUNTIME_FIXTURE = json.loads((ROOT / "data/gamejoa_final_runtime_fixtures_20261006.json").read_text(encoding="utf-8"))
FINAL_RUNTIME_CASES = {case["id"]: case for case in FINAL_RUNTIME_FIXTURE["cases"]}
FOLLOWON_FIXTURE = json.loads((ROOT / "data/gamejoa_followon_runtime_fixtures_20261006.json").read_text(encoding="utf-8"))
FOLLOWON_CASES = {case["id"]: case for case in FOLLOWON_FIXTURE["cases"]}
EQUITY_FOREGROUND_FIXTURE = json.loads((ROOT / "data/gamejoa_equity_foreground_fixtures_20261006.json").read_text(encoding="utf-8"))
EQUITY_FOREGROUND_CASES = {case["id"]: case for case in EQUITY_FOREGROUND_FIXTURE["cases"]}
SOURCE_PRECISION_FIXTURE = json.loads((ROOT / "data/gamejoa_source_precision_fixtures_20261006.json").read_text(encoding="utf-8"))
SOURCE_PRECISION_CASES = {case["id"]: case for case in SOURCE_PRECISION_FIXTURE["cases"]}
INTRADAY_SCOPE_FIXTURE = json.loads((ROOT / "data/gamejoa_intraday_scope_fixtures_20261006.json").read_text(encoding="utf-8"))
INTRADAY_SCOPE_CASES = {case["id"]: case for case in INTRADAY_SCOPE_FIXTURE["cases"]}
DELIVERY_SCOPE_FIXTURE = json.loads((ROOT / "data/gamejoa_delivery_scope_fixtures_20261006.json").read_text(encoding="utf-8"))
DELIVERY_SCOPE_CASES = {case["id"]: case for case in DELIVERY_SCOPE_FIXTURE["cases"]}
POSTDEPLOY_SCOPE_FIXTURE = json.loads((ROOT / "data/gamejoa_postdeploy_market_scope_fixtures_20261006.json").read_text(encoding="utf-8"))
POSTDEPLOY_SCOPE_CASES = {case["id"]: case for case in POSTDEPLOY_SCOPE_FIXTURE["cases"]}
FINAL_SCOPE_FIXTURE = json.loads((ROOT / "data/gamejoa_final_scope_fixtures_20261006.json").read_text(encoding="utf-8"))
FINAL_SCOPE_CASES = {case["id"]: case for case in FINAL_SCOPE_FIXTURE["cases"]}
PROGRAM_SCOPE_FIXTURE = json.loads((ROOT / "data/gamejoa_program_scope_fixtures_20261006.json").read_text(encoding="utf-8"))
PROGRAM_SCOPE_CASES = {case["id"]: case for case in PROGRAM_SCOPE_FIXTURE["cases"]}
POLICY_SCOPE_FIXTURE = json.loads((ROOT / "data/gamejoa_policy_scope_fixtures_20261006.json").read_text(encoding="utf-8"))
POLICY_SCOPE_CASES = {case["id"]: case for case in POLICY_SCOPE_FIXTURE["cases"]}
EXECUTION_SCOPE_FIXTURE = json.loads((ROOT / "data/gamejoa_execution_scope_fixtures_20261006.json").read_text(encoding="utf-8"))
EXECUTION_SCOPE_CASES = {case["id"]: case for case in EXECUTION_SCOPE_FIXTURE["cases"]}
FOREGROUND_TERMS_FIXTURE = json.loads((ROOT / 'data/gamejoa_foreground_terms_fixtures_20261006.json').read_text(encoding='utf-8'))
FOREGROUND_TERMS_CASES = {case['id']: case for case in FOREGROUND_TERMS_FIXTURE['cases']}
MATERIAL_EXECUTION_FIXTURE = json.loads((ROOT / 'data/gamejoa_material_execution_fixtures_20261006.json').read_text(encoding='utf-8'))
MATERIAL_EXECUTION_CASES = {case['id']: case for case in MATERIAL_EXECUTION_FIXTURE['cases']}
HEARING_SPECULATION_FIXTURE = json.loads((ROOT / 'data/gamejoa_hearing_speculation_fixtures_20261006.json').read_text(encoding='utf-8'))
HEARING_SPECULATION_CASES = {case['id']: case for case in HEARING_SPECULATION_FIXTURE['cases']}
HEADLINE_TERMS_FIXTURE = json.loads((ROOT / 'data/gamejoa_headline_terms_fixtures_20261006.json').read_text(encoding='utf-8'))
HEADLINE_TERMS_CASES = {case['id']: case for case in HEADLINE_TERMS_FIXTURE['cases']}
CONSUMER_SCOPE_FIXTURE = json.loads((ROOT / 'data/gamejoa_consumer_scope_fixtures_20261006.json').read_text(encoding='utf-8'))
CONSUMER_SCOPE_CASES = {case['id']: case for case in CONSUMER_SCOPE_FIXTURE['cases']}
PRIMARY_EVENT_FIXTURE = json.loads((ROOT / 'data/gamejoa_primary_event_scope_fixtures_20261006.json').read_text(encoding='utf-8'))
PRIMARY_EVENT_CASES = {case['id']: case for case in PRIMARY_EVENT_FIXTURE['cases']}
LOCAL_SCOPE_FIXTURE = json.loads((ROOT / 'data/gamejoa_local_scope_fixtures_20261006.json').read_text(encoding='utf-8'))
LOCAL_SCOPE_CASES = {case['id']: case for case in LOCAL_SCOPE_FIXTURE['cases']}
FOREIGN_SALES_FIXTURE = json.loads((ROOT / 'data/gamejoa_foreign_sales_scope_fixtures_20261006.json').read_text(encoding='utf-8'))
FOREIGN_SALES_CASES = {case['id']: case for case in FOREIGN_SALES_FIXTURE['cases']}
FOREGROUND_RECAP_FIXTURE = json.loads((ROOT / 'data/gamejoa_foreground_recap_fixtures_20261006.json').read_text(encoding='utf-8'))
FOREGROUND_RECAP_CASES = {case['id']: case for case in FOREGROUND_RECAP_FIXTURE['cases']}
ACTUAL_MARKET_FIXTURE = json.loads((ROOT / 'data/gamejoa_actual_market_scope_fixtures_20261006.json').read_text(encoding='utf-8'))
ACTUAL_MARKET_CASES = {case['id']: case for case in ACTUAL_MARKET_FIXTURE['cases']}
SOURCE_BINDING_FIXTURE = json.loads((ROOT / 'data/gamejoa_source_binding_fixtures_20261006.json').read_text(encoding='utf-8'))
SOURCE_BINDING_CASES = {case['id']: case for case in SOURCE_BINDING_FIXTURE['cases']}
PRIMARY_SUMMARY_FIXTURE = json.loads((ROOT / 'data/gamejoa_primary_summary_fixtures_20261006.json').read_text(encoding='utf-8'))
PRIMARY_SUMMARY_CASES = {case['id']: case for case in PRIMARY_SUMMARY_FIXTURE['cases']}
CONTRACT_BYLINE_CASE = json.loads((ROOT / 'data/gamejoa_contract_byline_fixture_20261006.json').read_text(encoding='utf-8'))
PACKET_QUALITY_CASES = {case['id']: case for case in json.loads(
    (ROOT / 'data/gamejoa_packet_quality_fixtures_20261006.json').read_text(encoding='utf-8'))['cases']}
HEADLINE_ANCHOR_FIXTURE = json.loads((ROOT / 'data/gamejoa_headline_anchor_fixtures_20261006.json').read_text(encoding='utf-8'))
HEADLINE_ANCHOR_CASES = {case['id']: case for case in HEADLINE_ANCHOR_FIXTURE['cases']}
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
        "published": dt.datetime.fromisoformat(case["published"]), "link": case["url"],
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
    def headline_anchor_alert(self, key):
        case = HEADLINE_ANCHOR_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_v98_all_seven_bodies_replay_without_new_delivery(self):
        now = dt.datetime.fromisoformat(HEADLINE_ANCHOR_FIXTURE['query_time_kst'])
        originals, selected = [], []
        for case in HEADLINE_ANCHOR_CASES.values():
            with self.subTest(case=case['id']):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = self.headline_anchor_alert(case['id'])
                originals.append(item)
                core = radar.verified_alert_core(item, case['title'])
                self.assertTrue(core)
                self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
                self.assertTrue(radar.core_sentence_is_complete(core))
                with patch.object(radar.base, 'kst_now', return_value=now):
                    selected.extend(radar.quality_display_alerts([classify(case, now)], 7))
        self.assertEqual(len(selected), 7)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'), patch.dict(os.environ, {'RADAR_RUN_MODE': 'live'}):
            telegram.record_seen_alerts(originals, now)
            fresh, skipped = telegram.filter_previously_seen_alerts(selected, now, 'live')
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 7)

    def test_won_dollar_headline_keeps_fixing_pair_time_level_and_change(self):
        item = self.headline_anchor_alert('won_dollar_fixing')
        core = radar.verified_alert_core(item, item['news'])
        for value in ('원/달러', '오후 3시 30분', '1,343.6원', '0.4원', '전일'):
            self.assertIn(value, core)
        self.assertNotIn('엔/달러', core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_nasdaq_core_keeps_its_close_not_dow_or_intraday_high(self):
        item = self.headline_anchor_alert('nasdaq_session_close')
        core = radar.verified_alert_core(item, item['news'])
        for value in ('5일(현지시간)', '나스닥', '1.05%', '2만7477.31', '마감'):
            self.assertIn(value, core)
        self.assertNotIn('2만7544.07', core)
        self.assertNotIn('5만1267.90', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        intraday = item['source_body'].replace('거래를 마쳤다', '장중 거래됐다')
        self.assertFalse(materiality.new_york_index_close_observation(item['news'], intraday))

    def test_annual_anonymous_mlcc_contract_matches_acknowledged_filing_terms(self):
        item = self.headline_anchor_alert('annual_mlcc_reprint')
        identity = materiality.source_event_identity(item)
        self.assertEqual(identity, 'source_event:v2:commercial_order:59030539ac8f67d85af931603a5f5d8ae4236604de93f005eabf8665698bb4d2')
        wire = {**item, 'link': 'https://www.yna.co.kr/view/annual-order-fixture',
                'source_title': '삼성전기, MLCC 2900억원 공급계약 공시'}
        self.assertEqual(identity, materiality.source_event_identity(wire))
        self.assertFalse(materiality.source_event_identity({**item, 'body_verified': False}))

    def test_changed_anonymous_filing_is_not_hidden_by_customer_label(self):
        item = self.headline_anchor_alert('annual_mlcc_reprint')
        identity = materiality.source_event_identity(item)
        variants = (item['source_body'].replace('2900', '3000'),
                    item['source_body'].replace('올해 6번째', '올해 7번째'),
                    item['source_body'].replace('2027년 12월 31일', '2028년 12월 31일'),
                    item['source_body'] + ' 삼성전기는 설비투자 예산 100억원을 확정했다고 공시했다.',
                    item['source_body'] + ' 계약 상대방은 엔비디아이다.')
        for body in variants:
            with self.subTest(body=body[-80:]):
                self.assertNotEqual(identity, materiality.source_event_identity({**item, 'source_body': body}))

    def packet_quality_alert(self, key):
        case = PACKET_QUALITY_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_v97_entire_packet_is_hashed_and_selects_four_unique_market_events(self):
        now = NOW.replace(day=6, hour=22)
        candidates = []
        for case in PACKET_QUALITY_CASES.values():
            with self.subTest(case=case['id']):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = classify(case, now)
                audit = radar.source_market_materiality(item) if item else {}
                keep = bool(item and audit.get('disposition') == 'keep' and audit.get('priority', 0) >= 2)
                self.assertEqual(keep, case['expected_keep'])
                if keep:
                    candidates.append(item)
        with patch.object(radar.base, 'kst_now', return_value=now), patch.object(radar, 'collect_fx_snapshot', return_value={'rates': {}}):
            selected = radar.compact_quality_final_alerts(candidates, 7)
            self.assertEqual(len(selected), 4)
            report = radar.compact_report(selected, {}, {}, now)
            radar.guard_preopen_report(report)
        for item in selected:
            self.assertFalse(radar.source_core_fact_errors(item))
            self.assertTrue(radar.core_sentence_is_complete(item['telegram_core_fact']))
            self.assertLessEqual(len(item['telegram_core_fact']), radar.GAMEJOA_CORE_MAX_CHARS)
        self.assertEqual(sum('신세계' in item['source_title'] for item in selected), 1)
        self.assertNotIn('골드만', report)
        self.assertNotIn('주식 모으기', report)

    def test_capital_participation_reprints_share_actor_amount_target_and_stage(self):
        first = self.packet_quality_alert('declared_capital_participation')
        second = self.packet_quality_alert('capital_participation_reprint')
        key = materiality.source_event_identity(first)
        self.assertTrue(key.startswith('source_event:v2:capital_participation:'))
        self.assertEqual(key, materiality.source_event_identity(second))
        for item in (first, second):
            core = radar.verified_alert_core(item, item['source_title'])
            for term in ('신세계그룹', '6일', '신세계프라퍼티', '파라마운트 스카이댄스', '워너브라더스', '10억달러', '참여한다고'):
                self.assertIn(term, core)
            self.assertNotIn('1084억달러', core)
            self.assertNotIn('완료', core)
            self.assertNotIn('합병했다', core)
            self.assertTrue(radar.source_core_fact_errors(item))

    def test_capital_participation_new_terms_and_paid_stage_remain_fresh(self):
        item = self.packet_quality_alert('capital_participation_reprint')
        key = materiality.source_event_identity(item)
        for old, new in (('10억달러', '12억달러'), ('신세계프라퍼티', '다른계열사'),
                         ('워너브라더스', '다른인수대상'), ('파라마운트 스카이댄스', '다른 스폰서')):
            changed = {**item, 'source_body': item['source_body'].replace(old, new)}
            self.assertTrue(materiality.source_event_identity(changed).startswith('source_event:v2:capital_participation:'))
            self.assertNotEqual(key, materiality.source_event_identity(changed))
        paid = {**item, 'source_body': '신세계프라퍼티는 투자금 10억달러를 납입했다.\n' + item['source_body']}
        self.assertNotEqual(key, materiality.source_event_identity(paid))
        core = radar.verified_alert_core(paid, paid['source_title'])
        self.assertIn('10억달러를 납입했다고', core)

    def test_partial_capital_payment_does_not_claim_the_entire_budget_was_paid(self):
        item = self.packet_quality_alert('capital_participation_reprint')
        paid = {**item, 'source_body': '신세계프라퍼티는 7일 투자금 2억달러를 납입했다.\n' + item['source_body']}
        core = radar.verified_alert_core(paid, paid['source_title'])
        self.assertIn('7일', core)
        self.assertIn('2억달러를 납입했다고', core)
        self.assertNotIn('10억달러를 납입', core)
        self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity(paid))

    def test_lfp_corporate_reprint_keeps_amount_without_inheriting_old_period(self):
        item = self.packet_quality_alert('lfp_press_release_reprint')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('포스코퓨처엠', '삼성SDI', '6조원', 'LFP 양극재', '체결했다'):
            self.assertIn(term, core)
        for historical in ('2027', '2032', '19만', '45%', 'LMO'):
            self.assertNotIn(historical, core)
        key = materiality.source_event_identity(item)
        self.assertEqual(key, materiality.source_event_identity(self.source_binding_alert('battery_contract_yonhap')))
        changed = {**item, 'source_body': item['source_body'].replace('6조원', '7조원')}
        self.assertNotEqual(key, materiality.source_event_identity(changed))

    def test_nuclear_procurement_keeps_equipment_lead_time_and_nonfixed_epc_interval(self):
        item = self.packet_quality_alert('nuclear_procurement_lead_time')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('미국', '최대 8기', '산업부', '안전제어반', '70개월', '체결 간격', '6개월', '노력', '확정 일정은 아니다'):
            self.assertIn(term, core)
        self.assertNotIn('6개월 안에 계약을 체결', core)
        self.assertNotIn('확정했다', core)
        wrong = core.replace('체결 간격', '체결 기한').replace('확정 일정은 아니다', '확정 일정이다')
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': wrong}))

    def test_oil_shipping_summary_keeps_measurement_period_and_daily_cost_basis(self):
        item = self.packet_quality_alert('iran_oil_shipping_constraints')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('CNN', '인용 보도', '9월', '원유 적재량', '0배럴', '하루 운항 비용', '160만달러', '지난해의 24배'):
            self.assertIn(term, core)
        self.assertNotIn('0만달러', core.replace('160만달러', ''))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('160만달러', '60만달러')}))

    def test_maintained_broker_view_without_quantified_revision_is_excluded(self):
        item = self.packet_quality_alert('unchanged_broker_opinion')
        self.assertFalse(eligible(item['source_title'], item['source_body']))

    def test_maintained_target_with_actual_eps_revision_is_kept(self):
        item = self.packet_quality_alert('unchanged_broker_opinion')
        body = item['source_body'] + '\n골드만삭스는 테슬라의 2026년 주당순이익(EPS) 전망을 3달러에서 4달러로 상향했다.'
        self.assertTrue(eligible(item['source_title'], body))

    def test_fractional_broker_app_definition_is_not_a_capital_commitment(self):
        case = PACKET_QUALITY_CASES['broker_fractional_service']
        self.assertFalse(eligible(case['title'], case['body']))
        definition = '국내 주식 모으기 서비스는 정기적으로 일정 금액을 주식에 투자할 수 있도록 하는 적립식 매수 서비스다.'
        self.assertFalse(materiality.evidence_is_new_event('capital_or_shareholder_action', definition))

    def test_broker_feature_with_new_market_rule_or_financial_result_is_kept(self):
        case = PACKET_QUALITY_CASES['broker_fractional_service']
        for title, change in (('금융위원회, 소수점 주식 매매수량단위 규칙 개정',
                               '금융위원회는 6일 소수점 주식 매매수량단위 규칙을 개정했다고 발표했다.'),
                              ('iM증권, 3분기 연결 매출 30% 증가…소수점 거래 서비스 개시',
                               'iM증권은 3분기 연결 매출이 500억원으로 30% 증가했다고 공시했다.')):
            self.assertTrue(eligible(title, change + '\n' + case['body']))

    def test_bracketed_publisher_byline_does_not_drop_a_verified_contract(self):
        case = CONTRACT_BYLINE_CASE
        self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
        now = NOW.replace(day=6, hour=22)
        candidate = classify(case, now)
        body_before = candidate['source_body']
        with patch.object(radar.base, 'kst_now', return_value=now), patch.object(radar, 'collect_fx_snapshot', return_value={'rates': {}}):
            selected = radar.compact_quality_final_alerts([candidate], 7)
            self.assertEqual(len(selected), 1)
            report = radar.compact_report(selected, {}, {}, now)
            radar.guard_preopen_report(report)
        self.assertEqual(candidate['source_body'], body_before)
        self.assertEqual(selected[0]['source_body'], case['body'])
        core = selected[0]['telegram_core_fact']
        for term in ('삼성전기', '글로벌 대형기업', '2900억원', '인공지능(AI)', 'MLCC', '체결했다'):
            self.assertIn(term, core)
        self.assertNotIn('기자', core)
        self.assertNotIn('아이뉴스24', core)
        self.assertIn(case['url'], report)
        self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_bracketed_byline_cleaning_does_not_need_a_publisher_allowlist(self):
        source = '[새경제뉴스 홍길동 기자] ' + CONTRACT_BODY
        self.assertEqual(radar.clean_article_summary_text(source), CONTRACT_BODY)

    def test_bracketed_byline_guard_still_rejects_raw_metadata_in_output(self):
        block = ('1) ' + CONTRACT_BYLINE_CASE['title'] + '\n- 핵심: ' + CONTRACT_BYLINE_CASE['body'].splitlines()[0])
        self.assertIn('article_ui_boilerplate', radar.compact_alert_block_errors(block))

    def test_non_byline_brackets_keep_the_source_actor_and_content(self):
        source = '[한국은행] 기준금리를 0.25%포인트 인상했다고 발표했다.'
        self.assertEqual(radar.clean_article_summary_text(source), source)

    def test_discovery_equivalence_requires_exact_acknowledged_source_reference(self):
        case = CONTRACT_BYLINE_CASE
        item = classify(case, NOW.replace(day=6, hour=22))
        identity = materiality.source_event_identity(item)
        reference = self.headline_terms_alert('mlcc_rounded_reprint')
        self.assertEqual(identity, materiality.source_event_identity(reference))
        proofs = materiality.verified_event_aliases()
        with patch.object(materiality, 'verified_event_aliases', return_value=tuple(
            proof for proof in proofs if proof['link'] != reference['link']
        )):
            self.assertNotEqual(identity, materiality.source_event_identity(item))
        for invalid in ({}, {'link': reference['link']}, {**next(proof['receipt_source'] for proof in proofs if proof.get('receipt_source')),
                                                         'source_body_sha256': '0' * 64}):
            altered = tuple({**proof, 'receipt_source': invalid} if proof.get('receipt_source') else proof for proof in proofs)
            with patch.object(materiality, 'verified_event_aliases', return_value=altered):
                self.assertNotEqual(identity, materiality.source_event_identity(item))
        changed = {**item, 'source_body': item['source_body'].replace('2900억원', '3900억원')}
        self.assertNotEqual(identity, materiality.source_event_identity(changed))

    def test_discovery_alias_never_creates_sent_history_for_unsent_article(self):
        case = CONTRACT_BYLINE_CASE
        now = NOW.replace(day=6, hour=22)
        item = classify(case, now)
        identity = materiality.source_event_identity(item)
        key = 'event:' + telegram.digest_seen(identity)
        state = {'seen': {'unsent_metadata': {'title': case['title'], 'link': case['url'],
                                              'first_seen_kst': now.isoformat()}}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertNotIn(key, state['seen'])
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'RADAR_RUN_MODE': 'live'}):
            path = Path(temp) / 'seen.json'
            path.write_text(json.dumps({'seen': {}}), encoding='utf-8')
            with patch.object(telegram, 'SEEN_PATH', path):
                fresh, _ = telegram.filter_previously_seen_alerts([item], now, 'live')
            self.assertEqual(len(fresh), 1)

    def primary_summary_alert(self, key):
        case = PRIMARY_SUMMARY_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_v96_complete_packet_is_source_hashed_and_replayed(self):
        now = NOW.replace(day=6, hour=21)
        items = []
        for case in PRIMARY_SUMMARY_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = classify(case, now)
                publication = radar.source_market_materiality(item) if item else {}
                self.assertEqual(bool(item and publication.get('disposition') == 'keep'
                                      and publication.get('priority', 0) >= 2), case['expected_keep'])
                if item and case['expected_keep']:
                    core = radar.verified_alert_core(item, case['title'])
                    self.assertTrue(radar.core_sentence_is_complete(core), core)
                    self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
                    items.append(item)
        with patch.object(radar.base, 'kst_now', return_value=now):
            self.assertEqual(len(radar.quality_display_alerts(items, 30)), 6)

    def test_truncated_project_safety_title_is_not_a_new_capacity_event(self):
        item = self.primary_summary_alert('truncated_project_safety')
        original = self.foreign_sales_alert('project_safety_denial')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('후티', '공격 주장', '현대차', '6일', '직원 피해', '파악했다고'):
            self.assertIn(term, core)
        self.assertNotIn('작년', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        key = materiality.source_event_identity(item)
        self.assertTrue(key.startswith('source_event:v2:project_safety_assessment:'))
        self.assertEqual(key, materiality.source_event_identity(original))
        changed = {**item, 'source_body': item['source_body'].replace('라빅의 아람코', '다른지역의 다른회사')}
        self.assertNotEqual(key, materiality.source_event_identity(changed))

    def test_conditional_project_payment_retains_amount_and_prerequisites(self):
        item = self.primary_summary_alert('conditional_nuclear_remittance')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('이형일', '한미 원전', '100억 달러', '선급금', '상업적 합리성', '국회 절차', '거쳐야', '지급할 수'):
            self.assertIn(term, core)
        self.assertNotIn('24억', core)
        self.assertNotIn('송금했다', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('100억', '24억')}))
        identity = materiality.source_event_identity(item)
        self.assertTrue(identity.startswith('source_event:v2:conditional_remittance:'))
        revised = {**item, 'source_body': item['source_body'].replace('100억 달러', '120억 달러')}
        self.assertNotEqual(identity, materiality.source_event_identity(revised))

    def test_court_injunction_retains_named_companies_and_interim_stage(self):
        item = self.primary_summary_alert('listing_suspension_ruling')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('서울남부지법', '2일', '주연테크', '케이엠제약', '효력정지 가처분', '각각 받아들였다'):
            self.assertIn(term, core)
        self.assertNotIn('300억', core)
        self.assertNotIn('기준을 폐지', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('효력정지 가처분', '최종 취소')}))
        self.assertTrue(materiality.source_event_identity(item).startswith('source_event:v2:listing_suspension_ruling:'))

    def test_market_outlook_keeps_actual_flow_and_forecast_attribution(self):
        item = self.primary_summary_alert('kospi_flow_outlook')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('9~10월', '21조6000억원', '순매도', '현대차증권', '김재승', '확인되면', '11월 이후', '전망했다'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_retrospective_public_careers_are_not_new_technical_validation(self):
        case = PRIMARY_SUMMARY_CASES['retrospective_career_survey']
        self.assertFalse(eligible(case['title'], case['body']))
        assessment = materiality.assess(case['title'], case['body'])
        self.assertEqual(assessment['equity_publication']['reason'], 'retrospective_career_inventory_not_current_technical_execution')
        self.assertTrue(eligible('반도체기업, HBM 대역폭 30% 향상 검증',
                                 '반도체기업은 6일 HBM 벤치마크 결과 대역폭이 기존 제품보다 30% 향상됐다고 발표했다.'))

    def test_market_close_is_complete_prose_not_a_source_grammar_error(self):
        item = self.primary_summary_alert('new_york_market_close')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('5일(현지시간)', '나스닥종합지수', '1.05%', '2만7477.31', '사상 최고치'):
            self.assertIn(term, core)
        self.assertNotIn('매도세를 이어지면서', core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))

    def test_new_primary_aliases_require_existing_matching_body_receipts(self):
        for key in ('truncated_project_safety', 'conditional_nuclear_remittance', 'listing_suspension_ruling'):
            item = self.primary_summary_alert(key)
            event_key = 'event:' + telegram.digest_seen(materiality.source_event_identity(item))
            entry = {'title': item['source_title'], 'link': item['link'],
                     'first_seen_kst': '2026-10-06T20:54:05+09:00',
                     'source_body_digest': materiality.verified_source_body_digest(item)}
            for digest in (None, '0' * 64):
                altered = {**entry}
                if digest is None:
                    altered.pop('source_body_digest')
                else:
                    altered['source_body_digest'] = digest
                state = {'seen': {'legacy_receipt': altered}}
                telegram.migrate_seen_verified_event_aliases(state)
                self.assertNotIn(event_key, state['seen'])
            state = {'seen': {'legacy_receipt': entry}}
            telegram.migrate_seen_verified_event_aliases(state)
            self.assertIn(event_key, state['seen'])
            self.assertEqual(state['seen'][event_key]['event_alias_evidence_message_id'], 2330)

    def source_binding_alert(self, key):
        case = SOURCE_BINDING_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_acknowledged_packet_all_seven_sources_are_replayed(self):
        now = NOW.replace(day=6, hour=21)
        items = []
        for case in SOURCE_BINDING_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))
                    items.extend(selected)
        with patch.object(radar.base, 'kst_now', return_value=now):
            self.assertEqual(len(radar.quality_display_alerts(items, 30)), 4)

    def test_stockpile_keeps_current_maximum_tender_and_exchange_not_old_release(self):
        item = self.source_binding_alert('stockpile_exchange')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('최대 4000만배럴', '입찰', '진행 중', '빌려간 뒤', '교환'):
            self.assertIn(term, core)
        self.assertNotIn('1억7200만', core)
        for wrong in (item['telegram_core_fact'], core.replace('4000만', '5000만'),
                      core.replace('추진한다', '완료했다'), core.replace('교환 방식', '매각 방식')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': wrong}))
        self.assertFalse(any(materiality.HISTORICAL_ACTION.search(e['source_excerpt'])
                             for e in materiality.assess(item['source_title'], item['source_body'])['evidence']))

    def test_contract_amount_stage_and_pair_are_used_for_core_and_identity(self):
        first = self.source_binding_alert('battery_contract_newsis')
        second = self.source_binding_alert('battery_contract_yonhap')
        key = materiality.source_event_identity(first)
        self.assertTrue(key.startswith('source_event:v2:commercial_order:'))
        self.assertEqual(key, materiality.source_event_identity(second))
        for item in (first, second):
            core = radar.verified_alert_core(item, item['source_title'])
            for term in ('포스코퓨처엠', '삼성SDI', '6조원', 'LFP 양극재', '체결했다'):
                self.assertIn(term, core)
            self.assertNotIn('2023년', core)
            self.assertNotIn('2032년', core)
            self.assertTrue(radar.source_core_fact_errors(item))
        for old, new in (('6조원', '7조원'), ('삼성SDI', '다른배터리사'), ('LFP', 'NCA'),
                         ('6일', '7일'), ('계약을 체결했다고', '계약을 추진한다고')):
            self.assertNotEqual(key, materiality.source_event_identity({**first, 'source_body': first['source_body'].replace(old, new)}))

    def test_mou_reprint_and_earlier_successful_source_are_one_planned_site_event(self):
        item = self.source_binding_alert('defense_site_mou_reprint')
        old = self.foreground_recap_alert('quantified_defense_mou')
        key = materiality.source_event_identity(item)
        self.assertTrue(key.startswith('source_event:v2:site_development_mou:'))
        self.assertEqual(key, materiality.source_event_identity(old))
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('MSDI', '구미시', '업무협약(MOU)', '2029년', '7000억원', '계획이다'):
            self.assertIn(term, core)
        self.assertNotIn('집행했다', core)
        self.assertNotIn('수주했다', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        for old_text, new_text in (('7000억원', '8000억원'), ('2029년', '2030년'), ('6일', '7일')):
            self.assertNotEqual(key, materiality.source_event_identity({**item, 'source_body': item['source_body'].replace(old_text, new_text)}))

    def test_commercial_property_repricing_keeps_attribution_and_observation_month(self):
        item = self.source_binding_alert('commercial_property_repricing')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('WSJ', '5일(현지시간)', '가격 재협상', '트렙', '8월', '11.42%', '특별관리'):
            self.assertIn(term, core)
        self.assertNotIn('상승다', core)
        self.assertFalse(radar.core_sentence_is_complete('자산가치가 상승다.'))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_source_guard_failure_cannot_fall_through_to_old_unverified_core(self):
        item = self.source_binding_alert('battery_contract_newsis')
        with patch.object(radar, 'source_core_fact_errors', return_value=['source_binding_failed']):
            self.assertEqual(radar.verified_alert_core(item, item['source_title']), '')

    def test_updated_committed_execution_cannot_be_hidden_by_old_contract_or_mou(self):
        for key, added in (
            ('battery_contract_newsis', '포스코퓨처엠은 해당 공급 계약의 설비투자 예산 500억원을 확정했다고 공시했다.'),
            ('defense_site_mou_reprint', 'MSDI는 공장 투자금 7000억원을 집행했다고 밝혔다.'),
        ):
            item = self.source_binding_alert(key)
            original = materiality.source_event_identity(item)
            revised = {**item, 'source_body': item['source_body'].replace('\n◎공감언론', '\n' + added + '\n◎공감언론')}
            self.assertNotEqual(original, materiality.source_event_identity(revised))

    def test_acknowledged_contract_and_site_aliases_upgrade_existing_receipts_only(self):
        for key in ('battery_contract_newsis', 'defense_site_mou_reprint'):
            item = self.source_binding_alert(key)
            identity = materiality.source_event_identity(item)
            event_key = 'event:' + telegram.digest_seen(identity)
            state = {'seen': {}}
            telegram.migrate_seen_verified_event_aliases(state)
            self.assertNotIn(event_key, state['seen'])
            old_key = 'link:' + telegram.digest_seen(telegram.canonical_article_url(item['link']))
            entry = {'title': item['source_title'], 'link': item['link'],
                     'first_seen_kst': NOW.replace(day=6, hour=20).isoformat(), 'lanes': {'live': NOW.replace(day=6, hour=20).isoformat()}}
            state = {'seen': {old_key: entry}}
            telegram.migrate_seen_verified_event_aliases(state)
            self.assertIn(event_key, state['seen'])
            self.assertEqual(state['seen'][event_key]['event_alias_evidence_message_id'], 2325)
            other = self.source_binding_alert('battery_contract_yonhap') if key == 'battery_contract_newsis' else self.foreground_recap_alert('quantified_defense_mou')
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'RADAR_RUN_MODE': 'live'}):
                path = Path(tmp) / 'seen.json'
                path.write_text(json.dumps(state), encoding='utf-8')
                with patch.object(telegram, 'SEEN_PATH', path):
                    fresh, skipped = telegram.filter_previously_seen_alerts([other], NOW.replace(day=6, hour=21), 'live')
                self.assertFalse(fresh)
                self.assertEqual(len(skipped), 1)

    def test_theme_etf_catalog_gates_keep_actual_current_flows_and_earnings(self):
        self.assertFalse(eligible(SOURCE_BINDING_CASES['etf_theme_recap']['title'], SOURCE_BINDING_CASES['etf_theme_recap']['body']))
        self.assertFalse(eligible(SOURCE_BINDING_CASES['consumer_device_catalog']['title'], SOURCE_BINDING_CASES['consumer_device_catalog']['body']))
        title = SOURCE_BINDING_CASES['etf_theme_recap']['title']
        body = SOURCE_BINDING_CASES['etf_theme_recap']['body'] + '\nxETFs는 NECK ETF의 이번 주 순유입이 3000억원으로 전주 대비 40% 증가했다고 6일 밝혔다.'
        self.assertTrue(eligible(title, body))
        self.assertTrue(eligible('삼성전자, 3분기 영업이익 10조원 발표', '삼성전자는 6일 3분기 매출 70조원, 영업이익 10조원을 기록했다고 발표했다.'))

    def actual_market_alert(self, key):
        case = ACTUAL_MARKET_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_all_seven_latest_received_bodies_keep_three_actual_business_changes(self):
        now = NOW.replace(day=6, hour=20)
        selected = []
        for case in ACTUAL_MARKET_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                result = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(result), case['expected_keep'])
                if result:
                    self.assertFalse(radar.source_core_fact_errors(result[0]))
                    selected.extend(result)
        self.assertEqual(len(selected), 3)

    def test_menu_distribution_is_not_company_sales_or_capital_investment(self):
        item = self.actual_market_alert('menu_distribution')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertFalse(eligible(item['source_title'].replace('버거킹', '다른외식기업'),
                                 item['source_body'].replace('버거킹', '다른외식기업')))
        self.assertTrue(eligible('외식기업, 분기 영업이익 500억원…메뉴 매장 확대',
                                 '외식기업은 6일 3분기 연결 영업이익 500억원을 공시했다.'))

    def test_consumer_dispute_statistics_need_a_current_financial_or_regulatory_action(self):
        item = self.actual_market_alert('dispute_statistics')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertTrue(eligible('네이버, 분기 영업이익 500억원…소비자 분쟁 통계 공개',
                                 '네이버는 6일 3분기 연결 영업이익 500억원을 공시했다. 분쟁 데이터를 전수 분석했다.'))

    def test_automated_quote_only_praise_is_not_a_new_quantified_broker_revision(self):
        item = self.actual_market_alert('automated_quote')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertTrue(eligible('장비기업, 신규 공급계약 공시에 강세',
                                 '장비기업은 6일 미국 고객사와 500억원 장비 공급 계약을 체결했다고 공시했다. '
                                 '이 기사는 기사 자동생성 알고리즘으로 작성했다.'))

    def test_local_demolition_reprint_does_not_turn_historical_selection_into_current_order(self):
        item = self.actual_market_alert('local_demolition_reprint')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertTrue(eligible('GS건설, 은평구 철거 공사 500억원 신규 수주',
                                 'GS건설은 6일 은평구 철거공사 500억원 공급 계약을 체결했다고 공시했다.'))

    def test_airline_rights_core_is_about_title_routes_not_unrelated_frequency_changes(self):
        item = self.actual_market_alert('airline_rights')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('제주항공', '9월', '인천~베이징', '주 7회', '인천~창사', '주 4회', '운수권'):
            self.assertIn(term, core)
        self.assertNotIn('웨이하이', core)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_airline_rights_values_and_award_month_are_source_bound(self):
        item = self.actual_market_alert('airline_rights')
        body = item['source_body'].replace('9월에는', '8월에는').replace('베이징 주 7회', '베이징 주 5회')
        changed = {**item, 'source_body': body, 'source_abstract': body}
        core = radar.verified_alert_core(changed, changed['source_title'])
        self.assertIn('8월', core)
        self.assertIn('주 5회', core)
        self.assertNotIn('9월', core)

    def test_customer_system_deployment_core_keeps_actual_use_and_implementation_not_praise(self):
        item = self.actual_market_alert('customer_system_deployment')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('싸이버로지텍', 'BNCT', '현장 운영', '디지털 트윈', '실시간 모니터링'):
            self.assertIn(term, core)
        self.assertNotIn('최우선 가치', core)
        self.assertNotIn('수주', core)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def foreground_recap_alert(self, key):
        case = FOREGROUND_RECAP_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_all_seven_followup_bodies_keep_four_foreground_catalysts(self):
        now = NOW.replace(day=6, hour=19)
        candidates = []
        for case in FOREGROUND_RECAP_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    candidates.extend(selected)
        self.assertEqual(len(candidates), 4)

    def test_anniversary_memorial_is_not_a_new_factory_or_supply_event(self):
        item = self.foreground_recap_alert('anniversary_memorial')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertFalse(eligible(item['source_title'].replace('고려아연', '다른금속'),
                                 item['source_body'].replace('고려아연', '다른금속')))
        self.assertTrue(eligible('금속기업, 창립 50주년 맞아 3000억원 제련공장 건설 계약 체결',
                                 '금속기업은 6일 3000억원 규모 제련공장 건설 계약을 체결했다고 공시했다.'))

    def test_retail_dessert_trend_sales_are_not_company_wide_earnings(self):
        item = self.foreground_recap_alert('consumer_dessert_trend')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertTrue(eligible('유통기업, 분기 영업이익 1000억원…디저트 판매 증가',
                                 '유통기업은 6일 3분기 연결 영업이익 1000억원을 발표했다. 디저트 판매도 늘었다.'))

    def test_ownership_exit_scenarios_need_a_current_owner_action(self):
        item = self.foreground_recap_alert('ownership_exit_scenario')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        body = '산업은행은 6일 한진칼 지분 매각을 검토 중이라고 밝혔다.\n' + item['source_body']
        self.assertTrue(eligible(item['source_title'], body))

    def test_premium_ap_share_core_keeps_forecast_population_and_period(self):
        item = self.foreground_recap_alert('premium_ap_share_forecast')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('카운터포인트리서치', '2026년', '프리미엄 안드로이드 AP', '미디어텍 12%', '삼성전자 엑시노스 11%', '전망'):
            self.assertIn(term, core)
        self.assertNotIn('2분기', core)
        self.assertNotIn('9%', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))

    def test_premium_ap_share_forecasts_are_source_derived_not_fixed(self):
        item = self.foreground_recap_alert('premium_ap_share_forecast')
        body = item['source_body'].replace('2026년', '2027년').replace('12%로', '13%로').replace('11%에', '10%에')
        core = radar.source_headline_event_fact(item['source_title'], body)
        for term in ('2027년', '미디어텍 13%', '엑시노스 10%'):
            self.assertIn(term, core)

    def test_new_listing_power_contract_report_and_quantified_mou_remain_early(self):
        for key in ('ai_listing_report', 'power_contract_early_report', 'quantified_defense_mou'):
            item = self.foreground_recap_alert(key)
            self.assertTrue(eligible(item['source_title'], item['source_body']))
            core = radar.verified_alert_core(item, item['source_title'])
            self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
            self.assertNotIn('확정됐다', core)

    def foreign_sales_alert(self, key):
        case = FOREIGN_SALES_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version94_seven_received_bodies_retain_primary_economic_facts(self):
        now = NOW.replace(day=6, hour=19)
        candidates = []
        for case in FOREIGN_SALES_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    candidates.extend(selected)
        with patch.object(radar.base, 'kst_now', return_value=now):
            self.assertEqual(len(radar.quality_display_alerts(candidates, 30)), 4)

    def test_foreign_sales_all_three_publishers_have_one_primary_milestone(self):
        identities = []
        for key in ('foreign_sales_newsis_roundup', 'foreign_sales_etoday_roundup', 'foreign_sales_newsis_release'):
            item = self.foreign_sales_alert(key)
            core = radar.verified_alert_core(item, item['source_title'])
            for term in ('롯데백화점', '6일', '올해', '누적', '외국인 고객 매출', '1조원', '돌파'):
                self.assertIn(term, core)
            self.assertNotIn('상징적', core)
            self.assertTrue(radar.source_core_fact_errors(item))
            identities.append(materiality.source_event_identity(item))
        self.assertTrue(all(identities))
        self.assertEqual(len(set(identities)), 1)

    def test_foreign_sales_milestone_values_and_issuer_are_source_derived(self):
        item = self.foreign_sales_alert('foreign_sales_etoday_roundup')
        title = item['source_title'].replace('롯데백화점', 'OTHER백화점')
        body = item['source_body'].replace('롯데백화점', 'OTHER백화점').replace('1조원', '1.2조원')
        core = radar.source_headline_event_fact(title, body)
        self.assertIn('OTHER백화점', core)
        self.assertIn('1.2조원', core)
        changed = {**item, 'source_title': title, 'news': title, 'source_body': body}
        self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity(changed))

    def test_foreign_sales_missing_period_or_missing_date_cannot_invent_terms(self):
        item = self.foreign_sales_alert('foreign_sales_etoday_roundup')
        self.assertFalse(materiality.cumulative_foreign_sales_observation(item['source_title'],
                         '롯데백화점이 외국인 매출 1조원을 돌파했다고 발표했다.'))

    def test_foreign_sales_other_retailer_cannot_supply_the_disclosure_date(self):
        item = self.foreign_sales_alert('foreign_sales_etoday_roundup')
        body = '신세계백화점은 5일 올해 외국인 매출 8500억원을 기록했다고 밝혔다.\n' + item['source_body']
        observation = materiality.cumulative_foreign_sales_observation(item['source_title'], body)
        self.assertEqual(observation['day'], '6')
        self.assertEqual(observation['amount'], '1조원')
        self.assertEqual(materiality.source_event_identity(item),
                         materiality.source_event_identity({**item, 'source_body': body}))

    def test_foreign_sales_same_title_cannot_hide_revised_amount_or_period(self):
        item = self.foreign_sales_alert('foreign_sales_etoday_roundup')
        identity = materiality.source_event_identity(item)
        for old, new in (('1조원', '1.2조원'), ('올해', '2027년'), ('6일', '7일')):
            changed = {**item, 'source_body': item['source_body'].replace(old, new)}
            self.assertTrue(materiality.source_event_identity(changed))
            self.assertNotEqual(identity, materiality.source_event_identity(changed))

    def test_segment_forecasts_do_not_become_total_company_profit_or_actual_losses(self):
        item = self.foreign_sales_alert('segment_loss_forecast')
        self.assertEqual(materiality.focus_kind(item['source_title']), 'earnings')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('IBK투자증권', 'MX·네트워크', '3분기', '1조1000억원', '유안타증권', '9000억원', '2000억원', '전망', '추정'):
            self.assertIn(term, core)
        self.assertNotIn('108조6800', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))

    def test_segment_forecast_values_are_not_fixed_template_amounts(self):
        item = self.foreign_sales_alert('segment_loss_forecast')
        body = item['source_body'].replace('1조1000억원', '1조3000억원').replace('9000억원', '8000억원')
        core = radar.source_headline_event_fact(item['source_title'], body)
        self.assertIn('1조3000억원', core)
        self.assertIn('8000억원', core)

    def test_quarterly_consensus_core_keeps_provider_values_period_and_release(self):
        item = self.foreign_sales_alert('quarterly_consensus')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('에프앤가이드', 'LG에너지솔루션', '3분기', '8조8257억원', '3217억원', '16.7%', '183.9%', '8일', '전망'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_quarterly_consensus_cannot_attach_a_different_lg_company(self):
        item = self.foreign_sales_alert('quarterly_consensus')
        self.assertFalse(materiality.quarterly_consensus_observation('LG전자, 3분기 매출 8조원 전망', item['source_body']))
        self.assertFalse(materiality.quarterly_consensus_observation('LG엔솔, 내년 매출 30조원 전망', item['source_body']))

    def test_project_safety_core_keeps_claim_and_current_company_response(self):
        item = self.foreign_sales_alert('project_safety_denial')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('후티', '공격 주장', '현대차', '6일', '건설현장', '직원 피해', '파악했다고'):
            self.assertIn(term, core)
        self.assertNotIn('작년', core)
        self.assertNotIn('5만대', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_local_demolition_cannot_reuse_a_historical_contractor_selection(self):
        item = self.foreign_sales_alert('local_demolition_notice')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertFalse(eligible(item['source_title'].replace('불광5', '다른7'), item['source_body'].replace('불광5', '다른7')))
        self.assertTrue(eligible('건설기업, 재개발 철거공사 500억원 수주',
                                '건설기업은 6일 재개발 철거공사 500억원 공급 계약을 체결했다고 공시했다.'))

    def test_non_etf_article_skips_etf_specific_execution_scan(self):
        from unittest.mock import Mock
        evidence = [{'kind': 'earnings_or_guidance', 'stage': 'reported_change',
                     'source_excerpt': '기업은 3분기 영업이익 1000억원을 발표했다.'}]
        counts = []
        for n in (5, 100):
            body = '기업은 3분기 영업이익 1000억원을 발표했다.\n' + '반도체 가격의 방향은 아직 불분명하다.\n' * n
            probe = Mock(wraps=materiality.NEW_EXECUTION)
            with patch.object(materiality, 'NEW_EXECUTION', probe):
                materiality.equity_publication_assessment('기업, 3분기 영업이익 1000억원', evidence, body=body)
            counts.append(probe.search.call_count)
        self.assertEqual(counts[0], counts[1])

    def test_acknowledged_receipt_survives_cancelled_job_but_failed_send_does_not(self):
        import merge_gamejoa_preopen_news_radar_seen as merge
        receipt = {'status': 'sent', 'message_id': 2318, 'sent_chars': 1079, 'attempts': 1, 'error': ''}
        self.assertTrue(merge.delivery_receipt_allows_seen_persistence(receipt))
        for change in ({'status': 'failed'}, {'status': 'dry_run'}, {'message_id': None},
                       {'message_id': True}, {'sent_chars': 0}, {'attempts': 0}, {'error': 'unconfirmed'}):
            self.assertFalse(merge.delivery_receipt_allows_seen_persistence({**receipt, **change}))

    def test_received_message_recovers_missing_seen_keys_without_resending(self):
        import gamejoa_recover_delivered_seen as recovery
        folder = ROOT / 'data/gamejoa_receipt_recovery_fixture_20261006'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'seen.json'
            path.write_text(json.dumps({'seen': {'sentinel': {'title': 'Existing receipt'}}}), encoding='utf-8')
            with patch.object(telegram, 'SEEN_PATH', path), patch.dict(os.environ, {'RADAR_RUN_MODE': 'live'}), \
                    patch.object(radar, 'send_telegram', side_effect=AssertionError('Recovery must not send')):
                self.assertEqual(recovery.recover_delivered_seen(folder / 'gamejoa_preopen_news_radar.json',
                                 folder / 'gamejoa_preopen_news_radar.md', folder / 'gamejoa_preopen_news_radar_delivery.json'), 7)
                self.assertEqual(recovery.recover_delivered_seen(folder / 'gamejoa_preopen_news_radar.json',
                                 folder / 'gamejoa_preopen_news_radar.md', folder / 'gamejoa_preopen_news_radar_delivery.json'), 0)
            self.assertIn('sentinel', json.loads(path.read_text(encoding='utf-8'))['seen'])

    def test_receipt_recovery_rejects_wrong_or_truncated_reports_without_seen_changes(self):
        import gamejoa_recover_delivered_seen as recovery
        folder = ROOT / 'data/gamejoa_receipt_recovery_fixture_20261006'
        receipt = json.loads((folder / 'gamejoa_preopen_news_radar_delivery.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'seen.json'
            state.write_text('{"seen": {}}', encoding='utf-8')
            before = state.read_bytes()
            for change in ({'status': 'failed'}, {'original_chars': receipt['original_chars'] + 1},
                           {'sent_chars': receipt['sent_chars'] - 1},
                           {'report_sha256': '0' * 64}, {'sent_text_sha256': '0' * 64}):
                proof = Path(tmp) / 'receipt.json'
                proof.write_text(json.dumps({**receipt, **change}), encoding='utf-8')
                with patch.object(telegram, 'SEEN_PATH', state), patch.dict(os.environ, {'RADAR_RUN_MODE': 'live'}):
                    with self.assertRaises(ValueError):
                        recovery.recover_delivered_seen(folder / 'gamejoa_preopen_news_radar.json',
                            folder / 'gamejoa_preopen_news_radar.md', proof)
                self.assertEqual(before, state.read_bytes())

    def test_workflow_retains_receipt_backed_state_after_timeout(self):
        workflow = (ROOT / '.github/workflows/gamejoa-preopen-news-radar.yml').read_text(encoding='utf-8')
        self.assertIn('timeout-minutes: 20', workflow)
        step = workflow.split('- name: Commit GAMEJOA radar seen state', 1)[1].split('- name: Commit GAMEJOA article retrieval queue', 1)[0]
        self.assertIn('if: always()', step)
        self.assertIn('delivery_receipt_allows_seen_persistence', step)
        self.assertIn('python scripts/gamejoa_recover_delivered_seen.py', step)
        self.assertIn('No acknowledged Telegram delivery', step)

    def local_scope_alert(self, key):
        case = LOCAL_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version93_all_seven_received_bodies_have_market_scope(self):
        now = NOW.replace(day=6, hour=18)
        for case in LOCAL_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_local_inspection_and_small_farm_subsidy_are_not_equity_catalysts(self):
        for key in ('local_fertiliser_inspection', 'local_farm_fuel_subsidy'):
            case = LOCAL_SCOPE_CASES[key]
            self.assertFalse(eligible(case['title'], case['body']))
            self.assertFalse(eligible(case['title'].replace('완주', '다른').replace('익산', '다른'),
                                     case['body'].replace('완주', '다른').replace('익산', '다른')))

    def test_local_industrial_contract_remains_a_real_market_execution(self):
        self.assertTrue(eligible('완주군, 데이터센터 1000억원 건설 계약 체결',
                                 '완주군은 6일 데이터센터 1000억원 건설 계약을 체결했다고 밝혔다.'))

    def test_national_farm_support_instrument_is_not_local_administration(self):
        self.assertTrue(eligible('정부, 전국 농업용 경유 세율 인하 시행',
                                 '정부는 6일 전국 농업용 경유의 세율을 5%에서 3%로 인하하는 고시를 개정했다.'))

    def test_weekly_etf_conditional_return_recap_needs_a_current_catalyst(self):
        case = LOCAL_SCOPE_CASES['weekly_etf_conditional_recap']
        self.assertFalse(eligible(case['title'], case['body']))
        current_flow = '6일 ETF 시장에 3000억원이 신규 순유입됐다고 거래소가 발표했다.\n' + case['body']
        self.assertTrue(eligible(case['title'], current_flow))

    def test_weekly_etf_recap_keeps_actual_power_supply_suspension(self):
        case = LOCAL_SCOPE_CASES['weekly_etf_conditional_recap']
        current = '전력회사는 6일 데이터센터 전력 공급을 중단했다고 발표했다.\n' + case['body']
        self.assertTrue(eligible(case['title'], current))

    def test_generic_build_cost_is_not_committed_capacity_investment(self):
        case = LOCAL_SCOPE_CASES['ai_factory_cost_explainer']
        self.assertFalse(eligible(case['title'], case['body']))
        self.assertFalse(materiality.evidence_is_new_event('physical_supply_or_capacity',
                         '메가와트급 AI 팩토리 하나를 구축하는 데 약 6000만달러가 투입된다.'))
        self.assertTrue(eligible('엔비디아, AI 팩토리 투자액 6000만달러 확정',
                                 '엔비디아는 6일 AI 팩토리 투자액 6000만달러를 확정했다고 공시했다.'))

    def test_new_external_gpu_result_is_separate_from_general_roi_explanation(self):
        self.assertTrue(eligible('엔비디아, GPU 반도체 외부 검증 결과 공개',
                                 '외부 기관은 6일 엔비디아 GPU 반도체의 성능 검증 결과를 공개했다. 처리량은 기존 대비 30배 증가했다.'))

    def test_foundry_core_keeps_reported_price_ranges_and_effective_periods(self):
        item = self.local_scope_alert('foundry_price_ranges')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('보도에 따르면', 'TSMC', '성숙공정', '내년 1월', '3~10%', '전망이다', '2나노', '내년 1분기', '6~8%', '전해졌다'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_foundry_price_values_and_issuer_are_not_fixed_template_values(self):
        case = LOCAL_SCOPE_CASES['foundry_price_ranges']
        title = case['title'].replace('TSMC', 'OTHER')
        body = case['body'].replace('TSMC', 'OTHER').replace('3~10%', '4~12%').replace('6~8%', '7~9%')
        core = radar.source_headline_event_fact(title, body)
        for term in ('OTHER', '4~12%', '7~9%'):
            self.assertIn(term, core)

    def test_airline_core_uses_current_schedule_not_april_rights(self):
        item = self.local_scope_alert('airline_current_schedule')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('제주항공', '부산~상하이', '25일부터 12월15일까지', '주 4회에서 주 7회', '인천~칭다오', '12월31일까지', '주 7회에서 주 11회'):
            self.assertIn(term, core)
        self.assertNotIn('4월', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_airline_schedule_changes_are_source_derived(self):
        case = LOCAL_SCOPE_CASES['airline_current_schedule']
        title = case['title'].replace('제주항공', 'OTHER항공')
        body = case['body'].replace('제주항공', 'OTHER항공').replace('주 4회에서 주 7회', '주 5회에서 주 9회')
        core = radar.source_headline_event_fact(title, body)
        for term in ('OTHER항공', '주 5회에서 주 9회'):
            self.assertIn(term, core)

    def test_publisher_ai_summary_card_is_not_reported_body(self):
        case = LOCAL_SCOPE_CASES['weekly_etf_conditional_recap']
        body = materiality.source_reported_body(case['body'])
        self.assertNotIn('AI 기사요약', body)
        self.assertNotIn('반사이익을 얻을 수 있다는 전망이 나옵니다', body)
        self.assertIn('11.09%', body)

    def test_foundry_reprint_keeps_one_event_across_titles_and_links(self):
        item = self.local_scope_alert('foundry_price_ranges')
        other = {**item, 'news': 'TSMC, 내년 파운드리 단가 인상 전망',
                 'source_title': 'TSMC, 내년 파운드리 단가 인상 전망', 'link': 'https://example.com/foundry-reprint'}
        self.assertTrue(materiality.source_event_identity(item))
        self.assertEqual(materiality.source_event_identity(item), materiality.source_event_identity(other))

    def test_foundry_changed_ranges_and_effective_periods_remain_distinct(self):
        item = self.local_scope_alert('foundry_price_ranges')
        for old, new in (('3~10%', '4~12%'), ('내년 1월', '내년 2월')):
            changed = {**item, 'source_body': item['source_body'].replace(old, new)}
            self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity(changed))

    def test_airline_reprint_keeps_one_event_across_titles_and_links(self):
        item = self.local_scope_alert('airline_current_schedule')
        other = {**item, 'news': '제주항공, 중국 동계 노선 증편 발표',
                 'source_title': '제주항공, 중국 동계 노선 증편 발표', 'link': 'https://example.com/airline-reprint'}
        self.assertTrue(materiality.source_event_identity(item))
        self.assertEqual(materiality.source_event_identity(item), materiality.source_event_identity(other))

    def test_airline_changed_frequencies_and_periods_remain_distinct(self):
        item = self.local_scope_alert('airline_current_schedule')
        for old, new in (('주 4회에서 주 7회', '주 4회에서 주 9회'), ('12월15일까지', '12월20일까지')):
            changed = {**item, 'source_body': item['source_body'].replace(old, new)}
            self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity(changed))

    def test_price_and_airline_terms_cannot_override_primary_earnings_or_contract(self):
        cases = (
            ('foundry_price_ranges', materiality.foundry_price_observation,
             'TSMC, 파운드리 단가 인상에 3분기 영업이익 10억달러', 'earnings'),
            ('foundry_price_ranges', materiality.foundry_price_observation,
             'TSMC, 파운드리 단가 인상 반영한 공급 계약 체결', 'commercial_order'),
            ('airline_current_schedule', materiality.airline_capacity_observation,
             '제주항공, 노선 증편에 3분기 영업이익 300억원', 'earnings'),
            ('airline_current_schedule', materiality.airline_capacity_observation,
             '제주항공, 노선 증편 위한 공급 계약 체결', 'commercial_order'),
        )
        for key, observe, title, focus in cases:
            item = self.local_scope_alert(key)
            changed = {**item, 'news': title, 'source_title': title, 'original_news': title}
            with self.subTest(title=title):
                self.assertEqual(materiality.focus_kind(title), focus)
                self.assertFalse(observe(title, item['source_body']))
                self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity(changed))
                self.assertNotEqual(radar.source_headline_event_fact(item['source_title'], item['source_body']),
                                    radar.source_headline_event_fact(title, item['source_body']))

    def primary_event_alert(self, key):
        case = PRIMARY_EVENT_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version92_all_seven_whole_bodies_replay_primary_events(self):
        now = NOW.replace(day=6, hour=17)
        for case in PRIMARY_EVENT_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_police_roundup_cannot_become_a_clinical_approval(self):
        item = self.primary_event_alert('police_roundup_incidental_clinical')
        self.assertFalse(eligible(item['news'], item['source_body']))
        for old, new in (('고범석', '다른경찰청장'), ('신약', '반도체')):
            self.assertFalse(eligible(item['news'].replace(old, new), item['source_body'].replace(old, new)))

    def test_clinical_bribery_is_not_an_approval_but_trial_suspension_is_an_event(self):
        self.assertFalse(materiality.evidence_is_new_event('technology_or_clinical_stage',
                          '경찰은 신약 임상시험 승인 청탁 의혹과 관련해 고발장 5건을 접수해 수사 중이라고 밝혔다.'))
        self.assertTrue(materiality.evidence_is_new_event('technology_or_clinical_stage',
                         '제약사는 수사 중인 신약의 임상시험을 중단했다고 공시했다.'))
        self.assertTrue(eligible('제약기업, 신약 임상 3상 승인', '식약처는 제약기업의 신약 임상 3상을 승인했다고 6일 발표했다.'))

    def test_unrecognised_headline_requires_its_market_topic_in_reported_lead(self):
        title = '기업대표 "이번 행사 정말 뜻깊다"'
        body = '기업대표는 지역 문화행사에 참여했다고 밝혔다.\n시민들은 축하 공연을 관람했다.\n기업대표는 신약 임상시험 승인 소식도 언급했다.'
        self.assertFalse(eligible(title, body))
        self.assertTrue(eligible('기업대표 "사업 전환 본격화"',
                                 '기업대표는 반도체 생산설비 1000억원 투자를 확정했다고 6일 공시했다.'))

    def test_governance_comment_is_not_a_new_insider_trade(self):
        item = self.primary_event_alert('governance_comment_on_old_trade')
        self.assertFalse(eligible(item['news'], item['source_body']))
        self.assertTrue(eligible('최태원 회장, SK 주식 9440억원 매각 공시',
                                 'SK는 6일 최태원 회장이 SK 주식 9440억원어치를 매각한다고 공시했다.'))

    def test_governance_comment_keeps_actual_changed_trade_terms(self):
        item = self.primary_event_alert('governance_comment_on_old_trade')
        changed = 'SK는 6일 매각 계약의 의결권 조건을 변경했다고 공시했다.\n' + item['source_body']
        self.assertTrue(eligible(item['news'], changed))

    def test_logistics_information_sharing_is_not_physical_throughput(self):
        item = self.primary_event_alert('historical_logistics_data_network')
        self.assertFalse(eligible(item['news'], item['source_body']))
        self.assertFalse(materiality.evidence_is_new_event('physical_supply_or_capacity',
                          '한중일 물류 정보 공유 협력도 2년 넘게 멈춘 것으로 나타났다.'))
        self.assertTrue(eligible('물류 항만 중단, 수출 선적 차질',
                                 '항만청은 6일 물류 항만의 하역 작업이 중단돼 수출 선적이 지연됐다고 밝혔다.'))

    def test_logistics_data_outage_with_real_shipping_disruption_remains_eligible(self):
        self.assertTrue(materiality.evidence_is_new_event('physical_supply_or_capacity',
                         '물류 데이터 플랫폼이 중단돼 통관과 선적에 차질이 발생했다고 항만청이 밝혔다.'))
        self.assertTrue(eligible('정부, 중국 물류 데이터 플랫폼 수입 금지',
                                 '정부는 6일 중국 물류 데이터 플랫폼의 수입을 금지하는 규제를 발표했다.'))

    def test_annual_consensus_summary_preserves_source_forecast_and_current_numbers(self):
        item = self.primary_event_alert('annual_earnings_consensus')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('에프앤가이드', '최근 1개월', 'SK이노베이션', '올해', '전망치 평균', '10조851억원', '3분기', '2조187억원', '252%'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        audit = materiality.assess(item['source_title'], item['source_body'])
        self.assertEqual(audit['evidence'][0]['stage'], 'early_signal')

    def test_annual_consensus_values_are_source_derived_not_fixed(self):
        item = self.primary_event_alert('annual_earnings_consensus')
        title = item['source_title'].replace('SK이노베이션', 'OTHER에너지')
        body = item['source_body'].replace('SK이노베이션', 'OTHER에너지').replace('10조851억원', '11조900억원').replace('2조187억원', '3조500억원')
        core = radar.source_headline_event_fact(title, body)
        for term in ('OTHER에너지', '11조900억원', '3조500억원'):
            self.assertIn(term, core)
        self.assertFalse(materiality.annual_earnings_consensus_observation(title, body.replace('컨센서스', '목표')))

    def test_global_ev_core_preserves_population_period_volume_and_issuer_share(self):
        item = self.primary_event_alert('global_ev_volume')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('SNE리서치', '1∼8월', '플러그인하이브리드 포함', '1천372만5천대', '5.9%', '현대차그룹', '49만9천대', '20.4%', '3.2%', '3.6%'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))

    def test_enacted_credit_decree_is_separate_from_conditional_operating_start(self):
        item = self.primary_event_alert('credit_union_decree')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('6일', '국무회의', '신용협동조합법 시행령', '의결됐다', '부실채권 매입', '22일부터', '출자·금융위 의결', '11월 이후', '예정이다'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertFalse(materiality.enacted_financial_decree_observation(item['news'], item['source_body'].replace('의결됐다고', '검토한다고')))

    def test_construction_order_summary_keeps_amount_and_current_cumulative_orders(self):
        item = self.primary_event_alert('construction_order')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('2812억원', '부산 연산13구역', '수주했다', '올해', '누적 수주액', '1조7666억원'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))

    def test_ui_cleaning_does_not_change_successful_body_receipts(self):
        item = self.primary_event_alert('police_roundup_incidental_clinical')
        old_digest = materiality.verified_source_body_digest(item)
        report = materiality.source_reported_body(item['source_body'])
        for term in ('AI 추천 뉴스', '기사 스크랩', '글자크기 조절', '자동차를 숫자와 현장에서'):
            self.assertNotIn(term, report)
        self.assertIn('고발장 5건', report)
        self.assertEqual(old_digest, materiality.verified_source_body_digest(item))

    def consumer_scope_alert(self, key):
        case = CONSUMER_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version91_whole_receipt_replays_consumer_and_report_scope(self):
        now = NOW.replace(day=6, hour=17)
        for case in CONSUMER_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_consumer_duty_free_app_is_not_a_tax_policy_event(self):
        item = self.consumer_scope_alert('airport_consumer_app')
        self.assertFalse(eligible(item['news'], item['source_body']))
        self.assertTrue(eligible('트럼프 면세 경유 도로 차량 사용 허용',
                                 HEADLINE_TERMS_CASES['diesel_tax_exemption_executive_order']['body']))

    def test_brand_profile_requires_actual_quantified_market_execution(self):
        item = self.consumer_scope_alert('food_brand_profile')
        self.assertFalse(eligible(item['news'], item['source_body']))
        self.assertTrue(eligible(item['news'], '제키스는 6일 신규 공장 설비투자 예산 500억원을 확정했다고 공시했다.\n' + item['source_body']))

    def test_hearing_robot_appeal_is_not_new_funding_or_technology_validation(self):
        item = self.consumer_scope_alert('hearing_robot_investment_appeal')
        self.assertFalse(eligible(item['news'], item['source_body']))
        self.assertTrue(eligible(item['news'], '정부는 6일 휴머노이드 설비투자 예산 1000억원을 확정했다.\n' + item['source_body']))

    def test_photo_credit_does_not_become_the_report_economic_change(self):
        body = CONSUMER_SCOPE_CASES['bok_eba_report_reprint']['body']
        reported = materiality.source_reported_body(body)
        self.assertNotIn('386억1000만', reported)
        self.assertIn('적정 경상수지는 기존 4.7%에서 3.3%', reported)
        self.assertEqual(materiality.strip_source_photo_caption('▲사업 수주 500억원을 공시했다.'), '▲사업 수주 500억원을 공시했다.')

    def test_macro_model_core_preserves_assessment_not_a_past_balance(self):
        item = self.consumer_scope_alert('bok_eba_report_reprint')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('한국은행이 발표한', 'IMF EBA 모형 개편', 'GDP 대비 적정 경상수지', '4.7%', '3.3%', '0.8%', '3.1%'):
            self.assertIn(term, core)
        self.assertNotIn('386억', core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_same_bok_report_across_publishers_dedupes_but_revision_survives(self):
        first = self.consumer_scope_alert('bok_eba_report')
        other = self.consumer_scope_alert('bok_eba_report_reprint')
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith('source_event:v2:macro_model_report:'))
        self.assertEqual(identity, materiality.source_event_identity(other))
        corrected = {**other, 'source_body': other['source_body'] + '\n한국은행은 이날 보고서를 정정했다.'}
        self.assertNotEqual(identity, materiality.source_event_identity(corrected))
        self.assertFalse(materiality.source_event_identity({**first, 'body_verified': False}))

    def test_cumulative_foreign_sales_reprint_dedupes_but_amount_and_period_survive(self):
        first = self.consumer_scope_alert('retailer_foreign_sales_first_receipt')
        other = self.consumer_scope_alert('retailer_foreign_sales_reprint')
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith('source_event:v2:cumulative_foreign_sales:'))
        self.assertEqual(identity, materiality.source_event_identity(other))
        for changed in ({**other, 'source_body': other['source_body'].replace('1조원', '2조원')},
                        {**other, 'published': other['published'].replace('2026-', '2027-')}):
            self.assertNotEqual(identity, materiality.source_event_identity(changed))
        self.assertFalse(materiality.source_event_identity({**first, 'body_verified': False}))

    def test_cumulative_foreign_sales_core_keeps_the_year_and_population(self):
        item = self.consumer_scope_alert('retailer_foreign_sales_reprint')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('롯데백화점', '6일', '올해 누적 외국인 고객 매출', '1조원'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_short_cancellation_disclosure_core_keeps_execution_date(self):
        item = self.consumer_scope_alert('share_cancellation_schedule')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('삼천리자전거', '44억원', '소각을 결정', '15일'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_successful_sales_and_report_receipts_block_cross_publisher_reprints(self):
        now = NOW.replace(day=6, hour=17)
        for first_key, other_key in (('retailer_foreign_sales_first_receipt', 'retailer_foreign_sales_reprint'),
                                     ('bok_eba_report', 'bok_eba_report_reprint')):
            first = self.consumer_scope_alert(first_key)
            other = self.consumer_scope_alert(other_key)
            state = {'seen': {'historical': {'title': first['source_title'], 'link': first['link'],
                                             'first_seen_kst': '2026-10-06T16:00:00+09:00'}}}
            with self.subTest(first=first_key), tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
                original = json.dumps(state).encode('utf-8')
                telegram.SEEN_PATH.write_bytes(original)
                fresh, skipped = telegram.filter_previously_seen_alerts([other], now, 'live')
                self.assertFalse(fresh)
                self.assertEqual(len(skipped), 1)
                self.assertEqual(telegram.SEEN_PATH.read_bytes(), original)

    def test_sales_and_report_aliases_never_seed_missing_or_changed_evidence(self):
        state = {'seen': {}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertFalse(state['seen'])
        first = self.consumer_scope_alert('retailer_foreign_sales_first_receipt')
        self.assertFalse(materiality.audited_source_event_identity({**first, 'source_body': first['source_body'] + '\n정정 공시.'}))

    def headline_terms_alert(self, key):
        case = HEADLINE_TERMS_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_second_version90_whole_receipt_replays_headline_terms(self):
        now = NOW.replace(day=6, hour=17)
        for case in HEADLINE_TERMS_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_two_reporter_names_do_not_become_the_policy_actor(self):
        core = radar.normalized_article_sentence('[세종=뉴시스]여동준 박광온 기자 = 정부가 24억 달러를 송금했다.')
        self.assertEqual(core, '정부가 24억 달러를 송금했다.')
        self.assertEqual(radar.normalized_article_sentence('김경택기자 = 삼성전기는 공급계약을 체결했다.'),
                         '삼성전기는 공급계약을 체결했다.')

    def test_paid_project_core_retains_not_yet_signed_power_purchase_contract(self):
        item = self.headline_terms_alert('paid_texas_project_pending_ppa')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('이형일', '텍사스 천연가스 발전소', '지난 1일', '24억 달러', '송금', '전력구매계약은 아직 체결되지 않았', '향후 체결'):
            self.assertIn(term, core)
        self.assertNotIn('여동준', core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_diesel_core_reports_signed_tax_scope_not_war_background(self):
        item = self.headline_terms_alert('diesel_tax_exemption_executive_order')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('트럼프', '면세 경유', '도로 차량', '행정명령에 서명', '갤런당 24센트', '사용 범위'):
            self.assertIn(term, core)
        self.assertNotIn('러시아', core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_regional_hearing_advocacy_is_not_a_new_capex_commitment(self):
        item = self.headline_terms_alert('regional_cluster_advocacy_not_new_capex')
        self.assertFalse(eligible(item['news'], item['source_body']))
        self.assertTrue(eligible(item['news'], '정부는 6일 반도체산단 기반시설 투자 예산 1000억원을 확정했다.\n' + item['source_body']))

    def test_semiconductor_sales_core_retains_cumulative_period_and_moving_average(self):
        item = self.headline_terms_alert('semiconductor_sales_period_and_ma_basis')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('미국 반도체산업협회(SIA)', '1~8월', '누적 매출', '1조달러', '1597억4000만달러', '6~8월', '3개월 이동평균', '144.3%'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('3개월 이동평균', '8월 단월 매출')}))

    def test_disclosed_contract_core_retains_counterparty_end_date_and_revenue_share(self):
        item = self.headline_terms_alert('refractory_contract_period_share')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('조선내화', '포스코', '351억원', '내화물', '내년 3월 31일까지', '6.60%'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_foreign_customer_sales_core_is_cumulative_not_regional_subset(self):
        item = self.headline_terms_alert('retailer_cumulative_foreign_sales')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('롯데백화점', '올해 누적', '외국인 고객 매출', '1조원', '돌파'):
            self.assertIn(term, core)
        self.assertNotIn('수도권을 제외', core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_rounded_mlcc_reprint_uses_individually_verified_alias_not_rounding_rule(self):
        item = self.headline_terms_alert('mlcc_rounded_reprint')
        first = self.hearing_speculation_alert('mlcc_first_exact_disclosure')
        self.assertEqual(materiality.source_event_identity(first), materiality.source_event_identity(item))
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('2027년', '1~12월', '약 2900억 원', '올해 5월', '약 3조9000억 원'):
            self.assertIn(term, core)
        changed = {**item, 'source_body': item['source_body'].replace('2027년 1월 1일', '2027년 1월 2일')}
        self.assertFalse(materiality.audited_source_event_identity(changed))

    def hearing_speculation_alert(self, key):
        case = HEARING_SPECULATION_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version90_eight_full_bodies_replay_hearing_speculation(self):
        now = NOW.replace(day=6, hour=16)
        for case in HEARING_SPECULATION_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_interrogative_cooperation_interest_is_not_execution(self):
        for ending in ('협력 범위를 넓힐지도 관심이다.', '협력이 구체화될지 주목된다.', '협력 접점을 늘릴지 관심이 쏠린다.'):
            body = 'AMD가 차세대 AI 서버 공급 확대를 앞둔 만큼 이번 방한에서 ' + ending
            for kind in ('physical_supply_or_capacity', 'technology_or_clinical_stage', 'customer_discussions'):
                self.assertFalse(materiality.evidence_is_new_event(kind, body), (kind, body))

    def test_signed_contract_survives_interrogative_extra_cooperation(self):
        body = 'AMD는 삼성전자와 2027년 AI 반도체 공급계약 100억원을 체결했으며, 협력 범위를 더 넓힐지 관심이다.'
        self.assertTrue(materiality.evidence_is_new_event('commercial_order', body))

    def test_hearing_responsibility_and_apology_are_not_market_changes(self):
        for key in ('capex_decision_blame', 'etf_past_decision_blame', 'etf_apology_reprint'):
            item = self.hearing_speculation_alert(key)
            self.assertEqual(materiality.assess(item['news'], item['source_body'])['reason'],
                             'retrospective_hearing_without_new_market_instrument')
        for row in ('투자계획의 결정 주체가 도마 위에 올랐다.', '레버리지 ETF 도입 취지는 규제의 비대칭성 완화였다고 설명했다.',
                    '정책 의도와 달리 시장 변동성을 확대한 데 무거운 마음을 가지고 있다고 밝혔다.'):
            for kind in ('capital_or_shareholder_action', 'policy_scope_or_stage', 'market_price_or_flow'):
                self.assertFalse(materiality.evidence_is_new_event(kind, row))

    def test_new_etf_instrument_survives_a_hearing_apology(self):
        item = self.hearing_speculation_alert('etf_past_decision_blame')
        body = '금융위는 단일종목 레버리지 ETF 규정을 개정했다. 기본예탁금은 7일부터 1000만원에서 3000만원으로 상향하며 시행일을 확정했다.\n' + item['source_body']
        self.assertTrue(eligible(item['news'], body))

    def test_conditional_project_payment_core_retains_condition_and_uncertainty(self):
        item = self.hearing_speculation_alert('conditional_nuclear_payment')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('최대 100억달러', '우선지급 방안', '이형일', '국내법 절차 완료 후', '연내 송금이 가능', '회수 시점·규모는 협의 중'):
            self.assertIn(term, core)
        self.assertNotIn('지급했다', core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_energy_report_core_keeps_targets_and_does_not_repeat_capacity(self):
        item = self.hearing_speculation_alert('energy_work_plan_targets')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('국회에 보고', '2030년', '100GW', '3GW', '2040년', '목표', 'ESS', '유연접속'):
            self.assertIn(term, core)
        self.assertEqual(core.count('100GW'), 1)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_mlcc_core_keeps_period_and_disclosed_revenue_share(self):
        for key in ('mlcc_reprint_exact_disclosure', 'mlcc_first_exact_disclosure'):
            item = self.hearing_speculation_alert(key)
            core = radar.verified_alert_core(item, item['source_title'])
            for term in ('삼성전기', '글로벌 대형기업', '2856억원', '내년 1월 1일', '12월 31일', '지난해 매출의 2.5%'):
                self.assertIn(term, core)
            self.assertTrue(radar.source_core_fact_errors(item))

    def test_mlcc_same_disclosure_terms_dedupe_but_changes_survive(self):
        first = self.hearing_speculation_alert('mlcc_first_exact_disclosure')
        reprint = self.hearing_speculation_alert('mlcc_reprint_exact_disclosure')
        key = materiality.source_event_identity(first)
        self.assertTrue(key.startswith('source_event:v2:commercial_order:'))
        self.assertEqual(key, materiality.source_event_identity(reprint))
        for old, new in (('2856억원', '2857억원'), ('1월 1일', '1월 2일'), ('2.5%', '2.6%'), ('글로벌 대형기업', '마이크로소프트')):
            self.assertNotEqual(key, materiality.source_event_identity({**first, 'source_body': first['source_body'].replace(old, new)}))
        changed = {**first, 'source_body': first['source_body'].replace(
            '\n◎공감언론', '\n삼성전기는 해당 공급계약을 위한 설비투자 예산 500억원을 확정했다고 공시했다.\n◎공감언론')}
        self.assertNotEqual(key, materiality.source_event_identity(changed))

    def test_mlcc_related_content_after_reporter_footer_is_not_new_execution(self):
        first = self.hearing_speculation_alert('mlcc_first_exact_disclosure')
        contaminated = {**first, 'source_body': first['source_body'] + '\n삼성전기는 해당 공급계약을 위한 설비투자 예산 500억원을 확정했다고 공시했다.'}
        self.assertEqual(materiality.source_event_identity(first), materiality.source_event_identity(contaminated))

    def test_mlcc_previous_successful_receipt_blocks_other_publisher_reprint(self):
        first = self.hearing_speculation_alert('mlcc_first_exact_disclosure')
        reprint = self.hearing_speculation_alert('mlcc_reprint_exact_disclosure')
        now = NOW.replace(day=6, hour=16)
        state = {'seen': {'historical': {'title': first['source_title'], 'link': first['link'],
                                         'first_seen_kst': '2026-10-06T11:52:00+09:00'}}}
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
            original = json.dumps(state).encode('utf-8')
            telegram.SEEN_PATH.write_bytes(original)
            fresh, skipped = telegram.filter_previously_seen_alerts([reprint], now, 'live')
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            self.assertEqual(telegram.SEEN_PATH.read_bytes(), original)
            changed = {**reprint, 'source_body': reprint['source_body'].replace('2.5%', '2.6%'),
                       'link': 'https://www.edaily.co.kr/News/Read?newsId=new-mlcc-terms'}
            fresh, _ = telegram.filter_previously_seen_alerts([changed], now, 'live')
            self.assertEqual(len(fresh), 1)

    def test_mlcc_verified_alias_cannot_seed_a_missing_receipt(self):
        first = self.hearing_speculation_alert('mlcc_first_exact_disclosure')
        identity = materiality.source_event_identity(first)
        state = {'seen': {}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertNotIn('event:' + telegram.digest_seen(identity), state['seen'])
        changed = {**first, 'source_body': first['source_body'].replace('2856억원', '2857억원')}
        self.assertFalse(materiality.audited_source_event_identity(changed))

    def material_execution_alert(self, key):
        case = MATERIAL_EXECUTION_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version89_all_seven_bodies_replay_material_execution(self):
        now = NOW.replace(day=6, hour=15)
        for case in MATERIAL_EXECUTION_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))

    def test_past_shared_political_statement_is_not_current_price_or_earnings(self):
        item = self.material_execution_alert('retail_survey_not_prior_speech')
        for kind in ('selling_price_or_cost', 'earnings_or_guidance'):
            self.assertFalse(materiality.evidence_is_new_event(kind, item['telegram_core_fact']))
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertTrue(eligible('교촌에프앤비, 3분기 영업이익 20% 증가',
                                 '교촌에프앤비는 3분기 매출 1500억원, 영업이익 120억원으로 전년 대비 20% 증가했다고 공시했다.'))

    def test_popup_target_attainment_is_not_company_earnings_but_new_capex_survives(self):
        case = MATERIAL_EXECUTION_CASES['popup_not_material_issuer_earnings']
        self.assertFalse(eligible(case['title'], case['body']))
        self.assertTrue(eligible('현대백화점, 신규 물류센터에 500억원 투자 확정',
                                 '현대백화점은 신규 물류센터 건설에 500억원을 투자하기로 확정했다고 6일 공시했다.'))

    def test_structured_filing_core_retains_client_exact_amount_and_period(self):
        item = self.material_execution_alert('structured_wafer_inspection_contract')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('넥스틴', 'SK하이닉스', '254.4억원', '웨이퍼 검사 시스템', '2026년 10월 03일', '2027년 11월 25일', '38.02%'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('254.4억원', '254억원')}))

    def test_structured_contract_terms_do_not_merge_nearby_amount_or_new_customer(self):
        item = self.material_execution_alert('structured_wafer_inspection_contract')
        identity = materiality.source_event_identity(item)
        self.assertTrue(identity.startswith('source_event:v2:commercial_order:'))
        for before, after in (('254.4억원', '254억원'), ('SK하이닉스', '삼성전자'), ('2027년 11월 25일', '2028년 11월 25일')):
            self.assertNotEqual(identity, materiality.source_event_identity({**item, 'source_body': item['source_body'].replace(before, after)}))

    def test_data_center_core_retains_actual_stop_authority_operator_and_reason(self):
        item = self.material_execution_alert('data_center_permit_stop')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('지난주', '인도네시아', '서부 자바 주', 'BDx', '공사 중단', '인허가 미발급'):
            self.assertIn(term, core)
        self.assertNotIn('전문가들은', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.is_actionable_local_dc_policy({**item, 'telegram_core_fact': core, 'local_dc_policy': True}))
        self.assertFalse(radar.is_actionable_local_dc_policy({**item, 'body_verified': False, 'local_dc_policy': True}))

    def test_lta_core_distinguishes_new_contract_from_cumulative_bookings(self):
        item = self.material_execution_alert('mlcc_contract_and_cumulative_lta')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('2027년 1~12월', '약 2900억 원', '올해 5월', '공시한 LTA 합계', '약 3조 9000억 원'):
            self.assertIn(term, core)
        self.assertNotIn('4조', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        changed = {**item, 'source_body': item['source_body'].replace('올해 5월', '지난해 8월')}
        changed_core = radar.verified_alert_core(changed, changed['source_title'])
        self.assertIn('지난해 8월부터', changed_core)
        self.assertNotIn('올해 5월', changed_core)

    def test_fund_core_separates_policy_support_private_matching_and_applicants(self):
        item = self.material_execution_alert('fund_matching_execution')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('최소 3000억원', '1926억원', '민간자금 1074억원', '추가 확보해야', '지원 운용사는 1곳'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_clinical_core_retains_comparator_duration_and_not_approval(self):
        item = self.material_execution_alert('clinical_result_not_only_conference')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('JW중외제약', '엠파가드', '24주', '0.81%', '0.24%', '55.7%', '25.5%', '대조군'):
            self.assertIn(term, core)
        self.assertNotIn('승인', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('0.81%', '0.24%')}))

    def foreground_terms_alert(self, key):
        case = FOREGROUND_TERMS_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version88_all_source_bodies_retain_concrete_foreground_terms(self):
        now = NOW.replace(day=6, hour=15)
        for case in FOREGROUND_TERMS_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))

    def test_caption_boundary_retains_following_article_sentence(self):
        item = self.foreground_terms_alert('regulatory_package_split_clauses_and_caption')
        cleaned = materiality.source_reported_body(item['source_body'])
        self.assertIn('정부가 자동차 내부 디스플레이', cleaned)
        self.assertNotIn('24.6형 OLED', cleaned)
        self.assertNotIn('(사진=', cleaned)
        self.assertEqual(materiality.strip_source_photo_caption('▲전기차 판매 20% 증가'), '▲전기차 판매 20% 증가')
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_split_regulation_clauses_use_same_package_not_caption_or_meeting_date(self):
        item = self.foreground_terms_alert('regulatory_package_split_clauses_and_caption')
        old = self.execution_scope_alert('regulatory_package_reprint')
        identity = materiality.source_event_identity(item)
        self.assertEqual(identity, materiality.source_event_identity(old))
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('수출입공고 개정', '연내', '2027년 1분기', '계획'):
            self.assertIn(term, core)
        self.assertNotIn('GV90', core)
        for old_value, new_value in (('2027년 1분기', '2027년 2분기'), ('연내 개정', '2028년 개정'),
                                     ('개정할 계획', '개정했다'), ('6일 규제', '7일 규제'),
                                     ('재생에너지 특구', '전국 모든 지역')):
            self.assertNotEqual(identity, materiality.source_event_identity({
                **item, 'source_body': item['source_body'].replace(old_value, new_value)}))

    def test_one_named_bill_across_publishers_preserves_new_stage_or_actor(self):
        item = self.foreground_terms_alert('bill_reprint_with_investment_vehicle')
        old = self.policy_scope_alert('legislative_action_not_prior_speech')
        identity = materiality.source_event_identity(item)
        self.assertTrue(identity.startswith('source_event:v2:legislative_action:'))
        self.assertEqual(identity, materiality.source_event_identity(old))
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('오세희', '발의했다', '투자전문회사 설립', '중소기업·중견기업'):
            self.assertIn(term, core)
        for old_value, new_value in (('오세희', '김미래'), ('신안보 혁신기업', '미래 에너지기업'),
                                     ('대표 발의했다', '통과했다')):
            self.assertNotEqual(identity, materiality.source_event_identity({
                **item, 'source_body': item['source_body'].replace(old_value, new_value)}))
        self.assertTrue(radar.source_core_fact_errors(item))

        no_ai_body = item['source_body'].replace('인공지능(AI)·', '')
        no_ai_core = radar.source_headline_event_fact(item['source_title'], no_ai_body)
        self.assertNotIn('AI·', no_ai_core)

    def test_capacity_contract_summary_keeps_customer_quantity_and_pending_expansion(self):
        item = self.foreground_terms_alert('cooling_contract_with_named_customer')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('LG전자', '에어 컨트롤 콘셉트', '5GW', '칠러', '장기 공급계약', 'CDU 공급 확대는 논의 중'):
            self.assertIn(term, core)
        self.assertNotIn('6000억원', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        identity = materiality.source_event_identity(item)
        for old_value, new_value in (('5GW', '6GW'), ('에어 컨트롤 콘셉트', '다른 고객'), ('논의 중', '체결했다')):
            self.assertNotEqual(identity, materiality.source_event_identity({
                **item, 'source_body': item['source_body'].replace(old_value, new_value)}))

    def test_named_bill_cross_run_reprint_is_quiet_but_new_actor_is_fresh(self):
        old = self.policy_scope_alert('legislative_action_not_prior_speech')
        item = self.foreground_terms_alert('bill_reprint_with_investment_vehicle')
        now = NOW.replace(day=6, hour=15)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
            telegram.record_seen_alerts([old], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([item], now, 'live')
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            changed = {**item, 'source_body': item['source_body'].replace('오세희', '김미래'),
                       'link': 'https://www.newsis.com/view/new-law-actor'}
            fresh, _ = telegram.filter_previously_seen_alerts([changed], now, 'live')
            self.assertEqual(len(fresh), 1)

    def test_regulatory_package_cross_run_reprint_is_quiet_but_new_deadline_is_fresh(self):
        old = self.execution_scope_alert('regulatory_package_reprint')
        item = self.foreground_terms_alert('regulatory_package_split_clauses_and_caption')
        now = NOW.replace(day=6, hour=15)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
            telegram.record_seen_alerts([old], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([item], now, 'live')
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            changed = {**item, 'source_body': item['source_body'].replace('2027년 1분기', '2027년 2분기'),
                       'link': 'https://www.etoday.co.kr/news/view/new-package-deadline'}
            fresh, _ = telegram.filter_previously_seen_alerts([changed], now, 'live')
            self.assertEqual(len(fresh), 1)

    def test_capacity_contract_receipt_migration_preserves_material_followups(self):
        item = self.foreground_terms_alert('cooling_contract_with_named_customer')
        proof = next(row for row in materiality.verified_event_aliases()
                     if row['message_id'] == 2285 and row['source_event_identity'].startswith('source_event:v2:capacity_supply_contract:'))
        now = NOW.replace(day=6, hour=15)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
            state = {'seen': {'old-receipt': {'title': proof['source_title'], 'link': proof['link'],
                                            'first_seen_kst': '2026-10-06T07:07:00+09:00'}}}
            telegram.SEEN_PATH.write_text(json.dumps(state), encoding='utf-8')
            fresh, skipped = telegram.filter_previously_seen_alerts([item], now, 'live')
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            for old_value, new_value in (('5GW', '6GW'), ('에어 컨트롤 콘셉트', '다른 고객'),
                                         ('논의 중', '체결했다'), ('6일 밝혔다', '7일 밝혔다')):
                with self.subTest(change=new_value):
                    changed = {**item, 'source_body': item['source_body'].replace(old_value, new_value),
                               'link': 'https://biz.heraldcorp.com/article/new-capacity-contract'}
                    fresh, _ = telegram.filter_previously_seen_alerts([changed], now, 'live')
                    self.assertEqual(len(fresh), 1)

    def test_vehicle_volume_retains_period_population_growth_and_regional_decline(self):
        item = self.foreground_terms_alert('vehicle_volume_period_and_regional_counterfact')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('현대차그룹', '1~8월', 'BEV·PHEV', '49만9500대', '20.4%', '5.9%', '북미', '23.4% 감소'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))
        for old_value, new_value in (('20.4%', '16.1%'), ('BEV·PHEV', 'BEV'), ('23.4% 감소', '23.4% 증가')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace(old_value, new_value)}))

    def test_marine_delivery_keeps_partial_application_and_attributed_capacity_claim(self):
        item = self.foreground_terms_alert('marine_delivery_partial_technology_and_claim')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('HD현대', '하이브리드 타입을 부분 적용', '프랑스 선사', '1만3000TEU', '인도했다', '10% 이상', '회사는', '설명했다'):
            self.assertIn(term, core)
        self.assertNotIn('부사장은', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('부분 적용', '전면 적용')}))

    def test_policy_advice_does_not_hide_actual_bill_or_current_tariff_execution(self):
        case = FOREGROUND_TERMS_CASES['scholarly_policy_advice_not_new_execution']
        self.assertFalse(eligible(case['title'], case['body']))
        self.assertTrue(eligible('농지법 개정 필요…의원, 특별법 발의',
                                 '오세희 의원은 6일 농지 공급 규제를 완화하는 특별법안을 발의했다. ' + case['body']))

    def test_property_stress_core_keeps_loan_scope_and_does_not_call_it_delinquency(self):
        item = self.foreground_terms_alert('commercial_property_refinancing_stress')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('미국', 'FTSE', '8월 말', '이달 2일', '8% 넘게', '트렙', '8월 CMBS', '11.42%', '특수관리', '2013년 2월'):
            self.assertIn(term, core)
        self.assertNotIn('연체율', core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('특수관리 대상', '연체 상태')}))
        self.assertFalse(materiality.commercial_property_stress_observation(
            item['source_title'], item['source_body'].replace('미국', '일본')))

    def execution_scope_alert(self, key):
        case = EXECUTION_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version87_entire_receipt_checks_quantified_current_execution(self):
        now = NOW.replace(day=6, hour=14)
        for case in EXECUTION_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))

    def test_construction_reprints_share_one_precisely_scoped_event(self):
        item = self.execution_scope_alert('construction_reprint_same_lot_share_duration')
        old = self.program_scope_alert('construction_total_not_company_share')
        identity = materiality.source_event_identity(item)
        self.assertTrue(identity.startswith('source_event:v2:construction_order:'))
        self.assertEqual(identity, materiality.source_event_identity(old))
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('제9공구', '8천65억원', '45%', '3천629억원', '60개월'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))
        for old_value, new_value in (('9공구', '10공구'), ('8천65억원', '8천66억원'),
                                     ('45.0%', '46.0%'), ('60개월', '61개월'),
                                     ('국가철도공단', '다른발주기관'), ('6일 밝혔다', '7일 밝혔다')):
            changed = {**item, 'source_title': item['source_title'].replace(old_value, new_value),
                       'source_body': item['source_body'].replace(old_value, new_value)}
            self.assertNotEqual(identity, materiality.source_event_identity(changed))

    def test_named_regulatory_package_dedupes_only_same_scope_stage_and_dates(self):
        item = self.execution_scope_alert('regulatory_package_reprint')
        old = self.policy_scope_alert('display_regulation_implementation')
        identity = materiality.source_event_identity(item)
        self.assertTrue(identity.startswith('source_event:v2:regulatory_package:'))
        self.assertEqual(identity, materiality.source_event_identity(old))
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('수입 승인 대상에서 제외', '연내', '수출입공고 개정', '내년 1분기', '계획'):
            self.assertIn(term, core)
        self.assertTrue(radar.source_core_fact_errors(item))
        for old_value, new_value in (('연내', '2028년'), ('내년 1분기', '내년 2분기'),
                                     ('개정을 추진한다', '개정을 시행했다'), ('6일 밝혔다', '7일 밝혔다'),
                                     ('현장규제 개선방안', '현장규제 추가개선방안')):
            self.assertNotEqual(identity, materiality.source_event_identity({
                **item, 'source_body': item['source_body'].replace(old_value, new_value)}))

    def test_cooling_summary_binds_new_model_claim_and_each_certification_stage(self):
        item = self.execution_scope_alert('industrial_cooling_model_and_certification')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('65LC', '최대 85%', '설명이다', "1.3MW '65LL'", '엔비디아 인증', '2.6MW 제품 인증은 추진 중'):
            self.assertIn(term, core)
        self.assertNotIn('48MW', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('인증은 추진 중', '인증을 받았')}))
        self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity({
            **item, 'source_body': item['source_body'].replace('85%', '90%')}))

    def test_thermal_policy_core_keeps_instrument_cost_payers_and_deadline(self):
        item = self.execution_scope_alert('thermal_lifespan_cost_sharing_review')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('일본 경제산업성', '휴·폐지', '1~3년', '전력 소매 공급자', '비용을 분담', '검토한다', '올해 안'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_clinical_recommendation_does_not_erase_failed_endpoints(self):
        item = self.execution_scope_alert('pre_submission_recommendation_with_failed_endpoints')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('한독', '레졸루트', '에르소데투그(RZ358)', '허가신청 전 미팅', '권고받았다', '3상', '1차·주요 2차', '충족하지 못했다'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        for old_value, new_value in (('권고받았다', '승인받았다'), ('충족하지 못했다', '충족했다')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace(old_value, new_value)}))

    def test_poll_gate_preserves_current_policy_execution_and_real_macro_releases(self):
        case = EXECUTION_SCOPE_CASES['political_poll_with_economic_background']
        self.assertFalse(eligible(case['title'], case['body']))
        self.assertTrue(eligible('트럼프, 지지율 하락 속 반도체 관세 행정명령 서명',
                                 '트럼프 대통령은 6일 반도체 관세를 15%로 부과하는 행정명령에 서명했다고 발표했다. ' + case['body']))
        self.assertTrue(eligible('美 소비자심리지수 하락…미시간대 10월 예비치 발표',
                                 '미시간대는 10월 소비자심리지수가 58.0으로 전월 60.0에서 하락했다고 6일 발표했다.'))

    def test_construction_and_regulation_reprints_are_suppressed_across_publishers_and_runs(self):
        now = NOW.replace(day=6, hour=14)
        pairs = ((self.program_scope_alert('construction_total_not_company_share'),
                  self.execution_scope_alert('construction_reprint_same_lot_share_duration')),
                 (self.policy_scope_alert('display_regulation_implementation'),
                  self.execution_scope_alert('regulatory_package_reprint')))
        for old, current in pairs:
            with self.subTest(title=current['source_title']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(len(radar.quality_display_alerts([old, current], 30)), 1)
                with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
                    telegram.record_seen_alerts([old], now)
                    before = telegram.SEEN_PATH.read_bytes()
                    fresh, skipped = telegram.filter_previously_seen_alerts([current], now, 'live')
                    self.assertFalse(fresh)
                    self.assertEqual(len(skipped), 1)
                    self.assertEqual(before, telegram.SEEN_PATH.read_bytes())

    def test_changed_regulatory_zone_or_issued_stage_cannot_use_old_package_alias(self):
        item = self.execution_scope_alert('regulatory_package_reprint')
        identity = materiality.source_event_identity(item)
        for body in (item['source_body'].replace('재생에너지 특구 내', '전국 모든 지역 내'),
                     item['source_body'].replace('내년 1분기', '2028년 1분기'),
                     item['source_body'].replace('총칭명', '실제 물질명'),
                     item['source_body'].replace('공표할 계획이다', '공표했다')):
            self.assertNotEqual(identity, materiality.source_event_identity({**item, 'source_body': body}))

    def policy_scope_alert(self, key):
        case = POLICY_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version86_entire_receipt_replays_current_events_not_prior_speeches(self):
        now = NOW.replace(day=6, hour=13)
        for case in POLICY_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))

    def test_named_delivery_ignores_english_model_alias_and_caption_award(self):
        item = self.policy_scope_alert('model_delivery_with_english_alias')
        original = self.delivery_scope_alert('cockpit_delivery_newsis')
        self.assertEqual(materiality.commercial_delivery_terms(item['source_title'], item['source_body'], item['published'])['customer'], '르노그룹')
        self.assertEqual(materiality.source_event_identity(item), materiality.source_event_identity(original))
        for body in (item['source_body'].replace('뉴 트래픽 이테크 일렉트릭', '다른 차종'),
                     item['source_body'].replace('르노그룹', '다른고객'),
                     item['source_body'].replace('공급한다.', '추가 공급한다.')):
            self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity({**item, 'source_body': body}))

    def test_scoped_anonymous_order_dedupes_only_exact_date_equipment_markets_and_target(self):
        item = self.policy_scope_alert('anonymous_battery_order_reprint')
        old = self.postdeploy_scope_alert('battery_order_with_expansion_target')
        identity = materiality.source_event_identity(item)
        self.assertTrue(identity.startswith('source_event:v2:scoped_anonymous_order:'))
        self.assertEqual(identity, materiality.source_event_identity(old))
        for body in (item['source_body'].replace('250억원', '350억원'),
                     item['source_body'].replace('A사', 'B사'),
                     item['source_body'].replace('스태킹', '검사'),
                     item['source_body'].replace('유럽', '미국'),
                     item['source_body'].replace('6일 밝혔다', '7일 밝혔다'),
                     item['source_body'] + ' 이번 계약 금액은 100억원이다.'):
            self.assertNotEqual(identity, materiality.source_event_identity({**item, 'source_body': body}))
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('엠플러스', 'A사', '노칭', '스태킹', '250억원', '목표다'):
            self.assertIn(term, core)
        self.assertNotIn('250억원을 수주', core)
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_legislation_core_preserves_draft_stage_and_current_actor(self):
        item = self.policy_scope_alert('legislative_action_not_prior_speech')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('오세희', '신안보 혁신기업 육성에 관한 특별법', '대표발의했다', '중소기업·중견기업'):
            self.assertIn(term, core)
        self.assertNotIn('지난 6월', core)
        self.assertNotIn('통과했다', core)
        self.assertNotIn('이 대통령은 당시', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        changed = {**item, 'source_title': item['source_title'].replace('오세희', '김미래'),
                   'source_body': item['source_body'].replace('오세희', '김미래').replace('신안보 혁신기업 육성', '첨단산업 경쟁력 강화')}
        changed_core = radar.verified_alert_core(changed, changed['source_title'])
        self.assertIn('김미래', changed_core)
        self.assertIn('첨단산업 경쟁력 강화', changed_core)

    def test_regulatory_core_keeps_implementation_timing_not_generic_announcement(self):
        item = self.policy_scope_alert('display_regulation_implementation')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('수입 승인 대상에서 제외', '연내', '수출입공고 개정', '보안 가이드라인', '내년 1분기', '계획'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))

    def test_hearing_goals_and_precommercial_pilots_do_not_block_committed_execution(self):
        for key in ('national_hearing_energy_aspiration', 'precommercial_cxl_validation_mou'):
            case = POLICY_SCOPE_CASES[key]
            self.assertFalse(eligible(case['title'], case['body']))
        self.assertTrue(eligible('기후장관, 재생에너지 예산 1000억원 증액 확정',
                                 '기후장관은 6일 국정감사에서 재생에너지 지원 예산을 1000억원 증액했다고 발표했다.'))
        telecom = NOISE_CASES['telecom_operating_requirement_is_policy_change']
        self.assertTrue(eligible(telecom['title'], '정부는 국정감사에서 정책 방안을 설명했다. ' + telecom['body']))
        pilot = POLICY_SCOPE_CASES['precommercial_cxl_validation_mou']
        self.assertTrue(eligible('반도체기업, CXL 공급 계약 체결',
                                 '반도체기업은 신규 고객과 100억원의 CXL 공급 계약을 체결했다고 6일 밝혔다. ' + pilot['body']))

    def program_scope_alert(self, key):
        case = PROGRAM_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version85_whole_receipt_keeps_five_distinct_source_events(self):
        now = NOW.replace(day=6, hour=13)
        selected_all = []
        for case in PROGRAM_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))
                selected_all.extend(selected)
        with patch.object(radar.base, 'kst_now', return_value=now):
            self.assertEqual(len(radar.quality_display_alerts(selected_all, 30)), 5)

    def test_signed_materials_development_mou_is_one_event_not_future_customer_order(self):
        first = self.program_scope_alert('battery_development_mou_edaily')
        second = self.program_scope_alert('battery_development_mou_zdnet')
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith('source_event:v2:industrial_development_mou:'))
        self.assertEqual(identity, materiality.source_event_identity(second))
        for body in (second['source_body'].replace('삼성SDI', '다른고객'),
                     second['source_body'].replace('전고체 배터리용 소재개발', '전력 반도체개발'),
                     second['source_body'].replace('6일 밝혔다', '7일 밝혔다'),
                     second['source_body'].replace('체결했다고', '체결할 예정이라고')):
            self.assertNotEqual(identity, materiality.source_event_identity({**second, 'source_body': body}))
        for item in (first, second):
            core = radar.verified_alert_core(item, item['source_title'])
            for value in ('에코프로비엠', '삼성SDI', '전고체', '업무협약(MOU)', '체결했다고 6일 밝혔다'):
                self.assertIn(value, core)
            self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
            self.assertTrue(radar.source_core_fact_errors(item))
            self.assertNotIn('양산 완료', core)

    def test_research_award_title_variants_keep_budget_and_receipt_identity(self):
        item = self.program_scope_alert('research_award_reprint_different_headline')
        old = self.postdeploy_scope_alert('national_research_award_two_budgets')
        self.assertEqual(materiality.source_event_identity(item), materiality.source_event_identity(old))
        self.assertTrue(materiality.source_event_identity(item).startswith('source_event:v2:research_award:'))
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('차세대 협동로봇', '지능형 용접 솔루션', '2건', '989억원', '681억원'):
            self.assertIn(value, core)
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertNotEqual(materiality.source_event_identity(item), materiality.source_event_identity({
            **item, 'source_body': item['source_body'].replace('989억원', '1089억원')}))

    def test_v100_actual_research_award_cross_publisher_and_changed_terms(self):
        newsis = alert("두산로보틱스, '한국형 피지컬 AI' 시동…989억 국책과제 수주",
                       "두산로보틱스는 산업통상부와 한국산업기술기획평가원이 공동 주관한 'K온디바이스 AI 반도체 기술개발사업'과 '로봇산업 기술개발사업'에서 제안한 과제 2건이 국책과제로 선정됐다고 6일 밝혔다.\n"
                       "두 과제의 총 연구개발비는 약 989억원으로, 이 가운데 정부 지원금은 약 681억원이다.",
                       "https://www.newsis.com/view/NISX20261006_0003814993")
        etoday = alert("두산로보틱스, 989억 규모 피지컬 AI 국책과제 수주",
                       "두산로보틱스는 산업통상부와 한국산업기술기획평가원이 주관하는 ‘K-온디바이스 AI 반도체 기술개발사업’과 ‘로봇산업 기술개발사업’에서 제안한 2개 과제가 국책과제로 선정됐다고 6일 밝혔다.\n"
                       "두 과제의 총 연구개발비는 약 989억원이며 이 가운데 정부 지원금은 약 681억원이다.",
                       "https://www.etoday.co.kr/news/view/2632636")
        for item in (newsis, etoday):
            item['published'] = '2026-10-06T10:05+09:00'
        identity = materiality.source_event_identity(newsis)
        self.assertEqual(identity, materiality.source_event_identity(etoday))
        self.assertTrue(identity.startswith('source_event:v2:research_award:'))
        core = radar.verified_alert_core(etoday, etoday['source_title'])
        for value in ('K온디바이스', '로봇산업 기술개발사업', '2건에 선정됐다고', '전체 과제', '989억원', '681억원'):
            self.assertIn(value, core)
        self.assertNotIn('두산로보틱스 매출', core)
        self.assertFalse(radar.source_core_fact_errors({**etoday, 'telegram_core_fact': core}))
        for old, new in (('989억원', '1089억원'), ('681억원', '700억원'), ('로봇산업 기술개발사업', '드론산업 기술개발사업'),
                         ('6일 밝혔다', '7일 밝혔다')):
            changed = {**etoday, 'source_body': etoday['source_body'].replace(old, new)}
            self.assertNotEqual(identity, materiality.source_event_identity(changed))

    def test_v100_nasdaq_close_same_session_but_intraday_and_new_session_survive(self):
        hankyung = alert("고금리 공포에도…나스닥·엔비디아 '사상 최고가'",
                         "엔비디아와 나스닥이 5일(현지시간) 사상 최고가를 기록했다.\n"
                         "이날 나스닥은 전 거래일 대비 286.45포인트(1.05%) 오른 2만7477.31에 거래를 마쳤다.")
        etoday = alert("뉴욕증시, 국채금리 상승에도 강세⋯나스닥, 사상 최고치",
                       "5일(현지시간) 뉴욕증권거래소에서 다우지수는 상승했다. S&P500지수는 51.23포인트(0.66%) 상승한 7773.95에, 기술주 중심의 나스닥지수는 286.45포인트(1.05%) 오른 2만7477.31에 마감했다.")
        for item in (hankyung, etoday):
            item['published'] = '2026-10-06T15:57+09:00'
        identity = materiality.source_event_identity(hankyung)
        self.assertEqual(identity, materiality.source_event_identity(etoday))
        self.assertEqual(identity, 'source_event:v1:us:equity_close:2026-10-05:nasdaq=27477.31:change=1.05')
        self.assertNotEqual(identity, materiality.source_event_identity({**etoday, 'source_body': etoday['source_body'].replace('5일(현지시간)', '6일(현지시간)')}))
        self.assertNotEqual(identity, materiality.source_event_identity({**etoday, 'source_body': etoday['source_body'].replace('2만7477.31', '2만7500.00')}))
        intraday = alert('유가·美 국채 내리자…S&P500·나스닥 사상 최고치 돌파',
                         '미 동부 시간으로 6일 오전 10시에 S&P500은 0.75% 오른 7832.17을 기록했다. 나스닥은 이 날도 0.73% 올랐다.')
        self.assertFalse(materiality.us_equity_close_identity(intraday))
        self.assertNotEqual(materiality.assess(intraday['source_title'], intraday['source_body'])['reason'],
                            'us_equity_close_session_unverified')

    def test_v100_undated_close_and_conflicting_metric_wait_for_source_check(self):
        roundup = ('[뉴스프레소] 나스닥 사상 최고가…고금리도 못막은 AI 랠리',
                   '미국 10년물 금리가 5.31%로 마감했음에도 나스닥과 S&P500은 상승 마감했습니다. 나스닥은 1%, S&P500은 0.66% 상승했습니다.')
        german = ('8월 독일 산업생산 10.6% 급감…"대형수주 기저효과"',
                  '독일 연방통계청은 6일 8월 산업생산 지수가 10.6% 급락했다고 발표했다. 산업생산은 예상보다 낮았다. '
                  '8월 산업수주 급감은 대형수주 기저효과다. 산업수주 통계가 축소됐다. 산업수주 증가율은 둔화했다. '
                  '산업수주가 감소했다. 산업수주가 변동성을 보였다. 산업수주 관련 제조업 매출은 보합이다.')
        self.assertEqual(materiality.assess(*roundup)['reason'], 'us_equity_close_session_unverified')
        self.assertEqual(materiality.assess(*german)['reason'], 'source_primary_metric_conflict_production_vs_orders')
        self.assertNotEqual(materiality.assess('독일 산업생산 10.6% 급감',
                            '독일 연방통계청은 6일 8월 산업생산이 전월 대비 10.6% 감소했다고 발표했다.')['reason'],
                            'source_primary_metric_conflict_production_vs_orders')

    def test_v100_aliases_upgrade_only_existing_acknowledged_articles(self):
        payload = json.loads((ROOT / 'data/gamejoa_verified_event_aliases.json').read_text(encoding='utf-8'))
        proofs = [entry for entry in payload['entries'] if entry.get('run_id') in {37472158800, 37480540629}
                  and entry.get('link') in {
                      'https://www.newsis.com/view/NISX20261006_0003814993',
                      'https://www.hankyung.com/article/202610065899i',
                      'https://www.etoday.co.kr/news/view/2632636',
                      'https://www.etoday.co.kr/news/view/2632544'}]
        self.assertEqual(len(proofs), 4)
        absent = {'seen': {}}
        telegram.migrate_seen_verified_event_aliases(absent)
        self.assertFalse(absent['seen'])
        original = [proof for proof in proofs if proof['run_id'] == 37472158800]
        state = {'seen': {str(index): {
            'title': proof['source_title'], 'link': proof['link'],
            'first_seen_kst': '2026-10-06T22:51:44+09:00', 'source_event_identity': '',
        } for index, proof in enumerate(original)}}
        telegram.migrate_seen_verified_event_aliases(state)
        for proof in original:
            key = 'event:' + telegram.digest_seen(proof['source_event_identity'])
            self.assertEqual(state['seen'][key]['event_alias_evidence_message_id'], 2339)
        self.assertEqual(sum(key.startswith('event:') for key in state['seen']), 2)

    def test_v100_attributed_oil_report_core_uses_shipment_not_unrelated_dispute(self):
        title = "우크라, '한국의 러 석유공급' 기사 인용해 韓 비판(종합)"
        body = ("블라디슬라우 블라시우크 우크라이나 대통령실 제재 담당 보좌관은 6일(현지시간) "
                "한국이 러시아에 경유 등을 공급했다는 기사 내용을 인용하며 한국의 대러시아 제재 정책과 극명하게 대비된다고 밝혔다.\n"
                "영국 일간 가디언은 이날 항만 기록과 선박 추적 데이터 분석을 토대로 지난 7∼8월 유조선 7척이 "
                "14차례에 나눠 한국 항구에서 실은 총 17만6천t 이상의 석유제품을 러시아 극동 지역에 실어 날랐다고 보도했다.")
        core = radar.source_headline_event_fact(title, body)
        for value in ('가디언', '7∼8월', '17만6천t', '우크라이나 대통령실', '보도했다'):
            self.assertIn(value, core)
        self.assertNotIn('포로', core)
        self.assertIn('article_without_headline_market_change_evidence',
                      radar.source_core_fact_errors({**alert(title, body), 'telegram_core_fact': core}))

    def test_quoted_diplomatic_criticism_needs_a_new_trade_action(self):
        title = "우크라, '한국의 러 석유공급' 기사 인용해 韓 비판"
        body = ("우크라이나 대통령실 보좌관은 한국의 대러 제재 정책을 비판했다. "
                "가디언은 항만 자료를 토대로 지난 7∼8월 한국에서 러시아로 석유제품 17만6천t이 운송됐다고 보도했다.")
        result = materiality.assess(title, body)
        self.assertEqual(result['disposition'], 'exclude')
        self.assertEqual(result['reason'], 'quoted_diplomatic_criticism_without_new_trade_action')
        new_action = ("우크라이나 정부는 한국 정유사에 신규 제재를 부과했다고 발표했다. " + body)
        self.assertNotEqual(materiality.assess(title, new_action)['reason'],
                            'quoted_diplomatic_criticism_without_new_trade_action')

    def test_v100_new_york_close_renderer_accepts_source_date_before_exchange(self):
        title = '뉴욕증시, 국채금리 상승에도 강세⋯나스닥, 사상 최고치 [글로벌마켓 모닝 브리핑]'
        body = ('5일(현지시간) 뉴욕증권거래소에서 다우지수는 전 거래일 대비 90.94포인트(0.18%) 오른 5만1267.90에 거래를 마쳤다. '
                'S&P500지수는 51.23포인트(0.66%) 상승한 7773.95에, 기술주 중심의 나스닥지수는 286.45포인트(1.05%) 오른 2만7477.31에 마감했다. '
                '나스닥지수는 사상 최고치를 경신했다.')
        observation = materiality.new_york_index_close_observation(title, body)
        self.assertEqual((observation['day'], observation['level'], observation['percent']), ('5', '2만7477.31', '1.05'))
        core = radar.source_headline_event_fact(title, body)
        for value in ('5일(현지시간)', '나스닥종합지수', '1.05%', '2만7477.31', '사상 최고치'):
            self.assertIn(value, core)
        self.assertFalse(radar.source_core_fact_errors({**alert(title, body), 'telegram_core_fact': core}))

    def test_v100_personal_ai_product_spec_alone_is_not_market_scale(self):
        title = '엔비디아, DGX 스파크 64GB 공개…로컬 AI 확장 지원'
        body = ('엔비디아가 개인용 AI 슈퍼컴퓨터 DGX 스파크의 64GB 구성을 공개했다. '
                '두 대를 연결하면 통합 메모리 128GB로 최대 2000억 파라미터 모델을 로컬에서 실행할 수 있다. '
                '오는 23일 출시하며 가격은 4999달러부터다.')
        result = materiality.equity_publication_assessment(title, [{
            'kind': 'model_operating_specification', 'source_excerpt': body,
        }], body=body)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['reason'], 'personal_ai_product_spec_without_verified_market_scale')
        scaled = materiality.equity_publication_assessment(title, [{
            'kind': 'model_operating_specification', 'source_excerpt': body,
        }, {'kind': 'commercial_order', 'source_excerpt': '엔비디아는 고객사와 공급 계약을 체결했다.'}],
            body=body + ' 엔비디아는 고객사와 공급 계약을 체결했다.')
        self.assertTrue(scaled['eligible'])

    def test_construction_core_separates_project_total_issuer_share_and_duration(self):
        item = self.program_scope_alert('construction_total_not_company_share')
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('국가철도공단', '제9공구', '총 공사비', '8065억원', '회사 지분', '45%', '60개월'):
            self.assertIn(value, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('45%', '100%')}))

    def test_national_program_core_preserves_parent_grant_and_subproject_boundaries(self):
        item = self.program_scope_alert('national_program_and_subproject_budgets')
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('원프레딕트', '공동연구기관', '6종 개발', '2030년', '전체 예산', '7368억원', '국비 5150억원', '세부과제 예산', '720억원'):
            self.assertIn(value, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('국비 5150억원', '회사 수주 5150억원')}))

    def test_prior_clinical_conference_interview_does_not_block_new_results(self):
        case = PROGRAM_SCOPE_CASES['old_clinical_results_interview']
        self.assertFalse(eligible(case['title'], case['body']))
        self.assertTrue(eligible('바이오기업, APB-R3 임상 2상 결과 발표',
                                 '바이오기업은 6일 환자 70명이 참여한 APB-R3 임상 2상 결과를 발표했다. 12주차 증상 점수는 55% 감소해 위약군 22%를 웃돌았다.'))

    def final_scope_alert(self, key):
        case = FINAL_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_last_prefixed_version83_receipt_replays_all_seven_sources(self):
        now = NOW.replace(day=6, hour=12)
        selected_all = []
        for case in FINAL_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))
                selected_all.extend(selected)
        with patch.object(radar.base, 'kst_now', return_value=now):
            self.assertEqual(len(radar.quality_display_alerts(selected_all, 30)), 2)

    def test_deliberative_opinion_survey_is_not_current_employment_statistics(self):
        case = FINAL_SCOPE_CASES['public_deliberation_not_employment_data']
        self.assertFalse(eligible(case['title'], case['body']))
        self.assertTrue(eligible('美 비농업 고용 증가 10만명…예상치 하회',
                                 '미 노동부는 9월 비농업 일자리가 10만명 증가해 예상치 15만명을 하회했다고 6일 발표했다.'))

    def test_historical_grid_survey_does_not_block_current_power_outage(self):
        case = FINAL_SCOPE_CASES['historical_grid_audit_not_current_outage']
        self.assertFalse(eligible(case['title'], case['body']))
        self.assertTrue(eligible('서울 폭염에 대규모 정전…3만가구 피해',
                                 '서울시는 6일 폭염으로 변압기 과부하 정전이 발생해 3만가구가 피해를 봤다고 밝혔다.'))

    def test_model_qualifiers_preserve_named_delivery_identity_and_receipt(self):
        original = self.delivery_scope_alert('cockpit_delivery_newsis')
        identity = materiality.source_event_identity(original)
        for key in ('named_model_delivery_zdnet', 'named_model_delivery_fnnews'):
            item = self.final_scope_alert(key)
            self.assertEqual(materiality.source_event_identity(item), identity)
            changed = {**item, 'source_body': item['source_body'].replace('뉴 트래픽 이테크 일렉트릭', '다른 차종')}
            self.assertNotEqual(materiality.source_event_identity(changed), identity)

    def test_broker_backlog_core_uses_issuer_period_amount_and_region_not_peer_margin(self):
        item = self.final_scope_alert('broker_backlog_not_peer_margin')
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('NH투자증권', '6일', '일진전기', '올해 상반기', '중전기 부문', '13억달러', '북미 비중', '80%에 육박', '분석했다'):
            self.assertIn(value, core)
        self.assertNotIn('30%', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('상반기', '하반기')}))
        changed = {**item, 'source_title': item['source_title'].replace('일진전기', 'OTHER전기'),
                   'source_body': item['source_body'].replace('일진전기', 'OTHER전기').replace('13억달러', '17억달러').replace('80%', '60%')}
        changed_core = radar.verified_alert_core(changed, changed['source_title'])
        for value in ('OTHER전기', '17억달러', '60%'):
            self.assertIn(value, changed_core)

    def postdeploy_scope_alert(self, key):
        case = POSTDEPLOY_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_version83_delivery_all_seven_full_bodies_and_three_unique_events(self):
        self.assertEqual(len(POSTDEPLOY_SCOPE_CASES), 7)
        now = NOW.replace(day=6, hour=12)
        selected_all = []
        for case in POSTDEPLOY_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))
                selected_all.extend(selected)
        with patch.object(radar.base, 'kst_now', return_value=now):
            self.assertEqual(len(radar.quality_display_alerts(selected_all, 30)), 3)

    def test_research_award_keeps_whole_project_budget_not_company_sales(self):
        item = self.postdeploy_scope_alert('national_research_award_two_budgets')
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('차세대 협동로봇', '지능형 용접', '2건', '6일', '전체 과제', '연구개발비는 약 989억원', '정부 지원금은 약 681억원'):
            self.assertIn(value, core)
        self.assertNotIn('매출', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        for old, new in (('989억원', '1660억원'), ('정부 지원금', '두산로보틱스 매출'), ('수주했다고', '상용화를 완료했다고')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace(old, new)}))

    def test_research_award_core_uses_mutated_source_actor_tasks_and_budgets(self):
        item = self.postdeploy_scope_alert('national_research_award_two_budgets')
        title, body = item['source_title'], item['source_body']
        for old, new in (('두산로보틱스', 'OTHER로봇'), ('차세대 협동로봇', '차세대 물류로봇'),
                         ('989억원', '1200억원'), ('681억원', '800억원'), ('6일 밝혔다', '7일 밝혔다')):
            title, body = title.replace(old, new), body.replace(old, new)
        core = radar.source_headline_event_fact(title, body)
        for value in ('OTHER로봇', '차세대 물류로봇', '1200억원', '800억원', '7일'):
            self.assertIn(value, core)
        self.assertNotIn('989억원', core)

    def test_signed_battery_order_amount_is_separate_from_expansion_target(self):
        item = self.postdeploy_scope_alert('battery_order_with_expansion_target')
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('엠플러스', '유럽 글로벌 배터리 기업 A사', '노칭 장비와 스태킹 장비', '수주했다고 6일', '250억원', '목표다'):
            self.assertIn(value, core)
        self.assertNotIn('154억원', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        for old, new in (('목표다', '확정됐다'), ('250억원', '400억원'), ('A사', '실명고객사')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace(old, new)}))

    def test_order_expansion_target_is_derived_not_hardcoded(self):
        item = self.postdeploy_scope_alert('battery_order_with_expansion_target')
        body = item['source_body'].replace('엠플러스', 'OTHER장비').replace('250억원', '310억원').replace('A사', 'B사')
        title = item['source_title'].replace('엠플러스', 'OTHER장비')
        core = radar.source_headline_event_fact(title, body)
        for value in ('OTHER장비', 'B사', '310억원', '목표다'):
            self.assertIn(value, core)

    def test_equipment_adoption_keeps_each_sources_stage_and_current_site(self):
        for key in ('mlcc_adoption_etoday', 'mlcc_adoption_newsis'):
            item = self.postdeploy_scope_alert(key)
            core = radar.verified_alert_core(item, item['source_title'])
            with self.subTest(case=key):
                for value in ('씨피시스템', 'MLCC', '자동광학검사(AOI)', '로보킷', '6일', '베트남 생산거점'):
                    self.assertIn(value, core)
                self.assertEqual('초도 물량 납품을 완료' in core, key == 'mlcc_adoption_etoday')
                self.assertNotIn('3배', core)
                self.assertNotIn('중국·대만', core)
                self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
                self.assertTrue(radar.source_core_fact_errors(item))
                self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('베트남', '인도')}))

    def test_equipment_adoption_observation_uses_changed_product_actor_and_site(self):
        item = self.postdeploy_scope_alert('mlcc_adoption_newsis')
        title, body = item['source_title'], item['source_body']
        for old, new in (('씨피시스템', 'OTHER시스템'), ('로보킷', '뉴로보킷'), ('베트남', '인도')):
            title, body = title.replace(old, new), body.replace(old, new)
        core = radar.source_headline_event_fact(title, body)
        for value in ('OTHER시스템', '뉴로보킷', '인도 생산거점'):
            self.assertIn(value, core)

    def test_audited_anonymous_customer_adoption_is_one_event_not_a_sector_block(self):
        first = self.postdeploy_scope_alert('mlcc_adoption_etoday')
        second = self.postdeploy_scope_alert('mlcc_adoption_newsis')
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith('source_event:v2:industrial_adoption:'))
        self.assertEqual(identity, materiality.source_event_identity(second))
        for old, new in (('베트남', '인도'), ('로보킷', '다른제품'), ('6일 밝혔다', '7일 밝혔다'), ('제조사', '다른고객사')):
            changed = {**first, 'source_body': first['source_body'].replace(old, new)}
            self.assertFalse(materiality.audited_source_event_identity(changed))
            self.assertNotEqual(identity, materiality.source_event_identity(changed))
        self.assertFalse(materiality.audited_source_event_identity({**first, 'body_verified': False}))

    def test_anonymous_adoption_alias_only_upgrades_existing_sent_receipt(self):
        case = POSTDEPLOY_SCOPE_CASES['mlcc_adoption_newsis']
        identity = materiality.source_event_identity(self.postdeploy_scope_alert(case['id']))
        absent = {'seen': {}}
        telegram.migrate_seen_verified_event_aliases(absent)
        self.assertFalse(absent['seen'])
        state = {'seen': {'old': {'title': case['title'], 'link': case['url'], 'first_seen_kst': '2026-10-06T11:24:00+09:00'}}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertEqual(state['seen']['event:' + telegram.digest_seen(identity)]['event_alias_evidence_message_id'], 2292)

    def test_nonincremental_scope_gates_preserve_crypto_etf_and_actual_policy_changes(self):
        self.assertTrue(eligible('비트코인 ETF에 기관자금 3000억원 순유입',
                                 '비트코인 ETF 기관자금 순유입은 3000억원으로 전주 대비 40% 증가했다고 발표했다.'))
        self.assertTrue(eligible('금융당국, 가상자산 규제 시행',
                                 '금융당국은 가상자산 발행사 규제를 강화해 준비자산 규정을 11월부터 시행한다고 발표했다.'))
        case = POSTDEPLOY_SCOPE_CASES['policy_reiteration_national_hearing']
        body = case['body'] + '\n정부는 수출기업 지원금 3000억원을 신규 배정하기로 결정했다.'
        self.assertTrue(materiality.equity_publication_assessment(case['title'], [
            {'kind': 'policy_scope_or_stage', 'source_excerpt': '정부는 지원금을 신규 배정하기로 결정했다.'}], body=body)['eligible'])

    def test_local_farming_gate_preserves_equipment_contract_and_climate_damage(self):
        self.assertTrue(eligible('충주시 영농사업, 장비기업과 100억원 공급 계약 체결',
                                 '충주시는 장비기업과 농업 장비 100억원 규모의 공급 계약을 체결했다고 밝혔다.'))
        self.assertTrue(eligible('충주시 폭염에 쌀 생산 차질…농작물 피해',
                                 '충주시는 폭염으로 농작물 피해 300억원과 쌀 생산 중단이 발생했다고 밝혔다.'))

    def intraday_scope_alert(self, key):
        case = INTRADAY_SCOPE_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_two_followup_receipts_all_fourteen_full_bodies_are_replayed(self):
        self.assertEqual(len(INTRADAY_SCOPE_CASES), 14)
        now = NOW.replace(day=6, hour=11)
        for case in INTRADAY_SCOPE_CASES.values():
            with self.subTest(case=case['id']), patch.object(radar.base, 'kst_now', return_value=now):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))

    def test_intraday_time_before_subject_retains_quote_not_yesterdays_contract(self):
        item = self.intraday_scope_alert('intraday_lg_time_before_issuer')
        self.assertEqual(materiality.focus_kind(item['source_title']), 'intraday_equity')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('LG전자', '6일', '9시40분', '5.56%', '22만8000원', '전 거래일 대비'):
            self.assertIn(term, core)
        self.assertNotIn('공급 계약', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_intraday_omitted_subject_is_bound_to_stock_code_not_session_high(self):
        item = self.intraday_scope_alert('intraday_lg_separate_subject')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('유가증권시장', 'LG전자', '9시13분', '5.32%', '22만7천500원', '전 거래일 대비'):
            self.assertIn(term, core)
        self.assertNotIn('8.80%', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_intraday_variants_do_not_guess_issuer_basis_or_day(self):
        for key in ('intraday_lg_time_before_issuer', 'intraday_lg_separate_subject'):
            item = self.intraday_scope_alert(key)
            source = item['source_body']
            with self.subTest(case=key):
                self.assertTrue(materiality.intraday_equity_event_terms(item))
                basis = '전 거래일 대비' if key.endswith('issuer') else '전장보다'
                self.assertFalse(materiality.intraday_equity_observations(item['source_title'], source.replace(basis, '연초 대비')))
                self.assertFalse(materiality.intraday_equity_event_terms({**item, 'body_verified': False}))
                self.assertFalse(materiality.intraday_equity_event_terms({**item, 'published': '2026-10-07T10:00+09:00'}))
                self.assertFalse(materiality.intraday_equity_observations(item['source_title'], source.replace('LG전자', '다른회사')))

    def test_same_session_issuer_price_ticks_are_one_cross_publisher_event(self):
        first = self.intraday_scope_alert('intraday_lg_time_before_issuer')
        second = self.intraday_scope_alert('intraday_lg_separate_subject')
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith('source_event:v2:intraday_equity:'))
        self.assertEqual(identity, materiality.source_event_identity(second))
        now = NOW.replace(day=6, hour=11)
        with patch.object(radar.base, 'kst_now', return_value=now):
            candidates = [classify(INTRADAY_SCOPE_CASES[key], now) for key in ('intraday_lg_time_before_issuer', 'intraday_lg_separate_subject')]
            self.assertEqual(len(radar.quality_display_alerts(candidates, 30)), 1)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
            telegram.record_seen_alerts([first], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([second], now, 'live')
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_larger_intraday_move_reversal_or_new_session_is_not_hidden(self):
        item = self.intraday_scope_alert('intraday_lg_time_before_issuer')
        identity = materiality.source_event_identity(item)
        for changed in (
            {**item, 'source_body': item['source_body'].replace('5.56%', '10.56%')},
            {**item, 'source_body': item['source_body'].replace('5.56% 오른', '5.56% 내린')},
            {**item, 'source_body': item['source_body'].replace('6일', '7일'), 'published': '2026-10-07T09:44+09:00'},
        ):
            self.assertNotEqual(identity, materiality.source_event_identity(changed))

    def test_quote_summary_rejects_another_time_price_or_comparison(self):
        item = self.intraday_scope_alert('intraday_lg_time_before_issuer')
        core = radar.verified_alert_core(item, item['source_title'])
        for old, new in (('9시40분', '9시13분'), ('5.56%', '8.80%'), ('22만8000원', '23만5천원'), ('전 거래일 대비', '연초 대비')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace(old, new)}))

    def test_stock_price_focus_does_not_replace_primary_contract_or_analyst_revision(self):
        self.assertEqual(materiality.focus_kind('LG전자, 5GW 데이터센터 냉각 공급 계약 체결'), 'commercial_order')
        self.assertEqual(materiality.focus_kind('LG전자 목표주가 상향, 장초반 강세'), 'analyst_revision')

    def test_single_sku_sale_is_not_consolidated_earnings(self):
        item = self.intraday_scope_alert('single_food_sku_sales')
        self.assertFalse(eligible(item['source_title'], item['source_body']))
        title = '식품기업, 3분기 영업이익 30% 증가'
        body = '식품기업은 3분기 연결 영업이익이 전년 동기 대비 30% 증가한 300억원을 기록했다고 6일 공시했다.'
        self.assertTrue(eligible(title, body))

    def test_historical_inventory_is_not_new_project_cancellation(self):
        for key in ('historical_franchise_survey', 'prior_year_lh_inventory'):
            item = self.intraday_scope_alert(key)
            self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertTrue(eligible('건설기업, 공공주택 건설 계약 해지 공시',
                                 '건설기업은 오늘 1000억원 규모의 공공주택 건설 계약을 해지했다고 공시했다.'))

    def test_current_national_housing_demand_retains_provider_window_and_population(self):
        item = self.intraday_scope_alert('national_housing_demand')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('직방', '6일', '1월 1일~9월 18일', '입주자모집공고', '전국 1순위', '5.6대 1', '지난해 같은 기간', '10.2대 1'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        for old, new in (('전국', '서울'), ('9월 18일', '12월 31일'), ('5.6대 1', '100대 1')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace(old, new)}))

    def test_military_core_reports_support_plan_not_interpretation_or_completed_deployment(self):
        item = self.intraday_scope_alert('military_deployment_agreement')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('튀르키예·파키스탄', '군사력 지원 계획', '발표했다', '설명하지 않았다'):
            self.assertIn(term, core)
        self.assertNotIn('배치를 완료했다', core)
        self.assertNotIn('입장으로 보인다', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_contract_power_is_not_operating_power_or_unconditional_2029_supply(self):
        item = self.intraday_scope_alert('contract_power_expansion_conditional')
        core = radar.verified_alert_core(item, item['source_title'])
        for term in ('계약 전력 용량', '500MW', '1GW', '승인', '전제다', '2029년'):
            self.assertIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('계약 전력 용량', '가동 전력 용량')}))

    def test_historical_rankings_product_launch_and_auto_streak_are_not_capital_actions(self):
        for key in ('retrospective_deal_ranking', 'retail_fund_launch', 'automated_stock_streak'):
            item = self.intraday_scope_alert(key)
            self.assertFalse(eligible(item['source_title'], item['source_body']))
        self.assertTrue(eligible('기관, 펀드에 1조원 신규 출자 확정', '기관은 6일 펀드에 1조원 신규 출자를 확정했다고 발표했다.'))

    def test_intraday_aliases_upgrade_only_actual_existing_receipts(self):
        item = self.intraday_scope_alert('intraday_lg_time_before_issuer')
        identity = materiality.source_event_identity(item)
        empty = {'seen': {}}
        telegram.migrate_seen_verified_event_aliases(empty)
        self.assertFalse(empty['seen'])
        state = {'seen': {'historical': {'title': item['source_title'], 'link': item['link'],
                                          'first_seen_kst': '2026-10-06T10:18:00+09:00'}}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertEqual(state['seen']['historical']['source_event_identity'], identity)
        event = state['seen']['event:' + telegram.digest_seen(identity)]
        self.assertEqual(event['event_alias_evidence_run_id'], 37396976374)
        self.assertEqual(event['event_alias_evidence_message_id'], 2289)
        wrong = {'seen': {'historical': {'title': item['source_title'], 'link': item['link'],
                                          'first_seen_kst': '2026-10-05T10:18:00+09:00'}}}
        telegram.migrate_seen_verified_event_aliases(wrong)
        self.assertNotIn('source_event_identity', wrong['seen']['historical'])

    def test_amount_in_separate_sentence_does_not_repeat_audited_same_order(self):
        item = self.intraday_scope_alert('equipment_order_amount_separate_sentence')
        old = self.runtime_alert('equipment_order_precise_reprint')
        self.assertEqual(materiality.source_event_identity(item), materiality.source_event_identity(old))
        changed = {**item, 'source_body': item['source_body'].replace('244억8000만원', '300억원')}
        self.assertNotEqual(materiality.source_event_identity(changed), materiality.source_event_identity(old))
        self.assertFalse(materiality.audited_source_event_identity({**item, 'body_verified': False}))

    def test_military_summary_does_not_borrow_economic_scope_from_another_article(self):
        item = self.intraday_scope_alert('military_deployment_agreement')
        core = radar.verified_alert_core(item, item['source_title'])
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('지원 계획을 발표했다', '배치를 완료했다')}))
        self.assertFalse(eligible('두 나라, 군사력 배치 훈련 실시', '두 나라는 군사력 배치 계획을 발표했다. 정례적인 교육 훈련이다.'))

    def test_contract_power_summary_is_built_from_sourced_names_and_units(self):
        item = self.intraday_scope_alert('contract_power_expansion_conditional')
        changed = {**item, 'source_title': item['source_title'].replace('테라울프', '새기업'),
                   'source_body': item['source_body'].replace('테라울프', '새기업').replace('500메가와트', '300메가와트')
                                                    .replace('1기가와트', '2기가와트').replace('2029년', '2030년')}
        core = radar.verified_alert_core(changed, changed['source_title'])
        for term in ('새기업', '300MW에서 2GW', '2030년', '승인'):
            self.assertIn(term, core)
        self.assertNotIn('테라울프', core)
        self.assertFalse(radar.source_core_fact_errors({**changed, 'telegram_core_fact': core}))

    def source_precision_alert(self, key):
        case = SOURCE_PRECISION_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_next_receipt_all_seven_sources_are_replayed_not_just_order_example(self):
        self.assertEqual(len(SOURCE_PRECISION_CASES), 7)
        now = NOW.replace(day=6, hour=10)
        for case in SOURCE_PRECISION_CASES.values():
            with self.subTest(case=case["id"]), patch.object(radar.base, "kst_now", return_value=now):
                self.assertEqual(hashlib.sha256(case["body"].encode()).hexdigest(), case["full_body_sha256"])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case["expected_keep"])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))

    def test_stock_code_does_not_make_exact_same_equipment_contract_new(self):
        coded = self.source_precision_alert("exact_order_with_stock_code")
        prior = self.runtime_alert("equipment_order_precise_reprint")
        self.assertEqual(materiality.source_event_identity(coded), materiality.source_event_identity(prior))
        changed = {**coded, "source_body": coded["source_body"].replace("244억8000만원", "300억원")}
        self.assertNotEqual(materiality.source_event_identity(changed), materiality.source_event_identity(prior))
        now = NOW.replace(day=6, hour=10)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([prior], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([coded], now, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_menu_pr_with_old_item_sales_is_not_company_earnings(self):
        case = SOURCE_PRECISION_CASES["coffee_menu_publicity"]
        self.assertFalse(eligible(case["title"], case["body"]))
        self.assertTrue(eligible("외식기업, 신메뉴 확대와 분기 영업이익 40% 증가 발표",
                                 "외식기업은 분기 영업이익이 40% 증가한 300억원이라고 공시했다. 회사는 신메뉴 확대를 발표했다."))

    def test_existing_trade_rule_analysis_does_not_hide_a_new_signed_agreement(self):
        case = SOURCE_PRECISION_CASES["existing_trade_rules_and_old_estimate"]
        self.assertFalse(eligible(case["title"], case["body"]))
        new = case["body"] + "\n정부는 6일 CPTPP 가입 협정에 서명했다. 정부는 농산물 관세율을 10%에서 5%로 인하했다고 발표했다."
        self.assertTrue(eligible(case["title"], new))

    def test_freight_cost_retains_maximum_voyage_and_daily_charter_bases(self):
        item = self.source_precision_alert("freight_cost_not_crew_bonus")
        core = radar.verified_alert_core(item, item["source_title"])
        for term in ("WSJ", "5일 현지", "호르무즈", "VLCC", "왕복 1회", "최대 4000만달러", "지난달 말", "페르시아만에서 중국", "하루 약 23만달러", "하루 120만달러"):
            self.assertIn(term, core)
        self.assertNotIn("보상금", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for old, new in (("왕복 1회", "하루"), ("최대 4000만달러", "4000만달러"), ("지난달 말", "오늘")):
            self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": core.replace(old, new)}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_freight_cost_foreign_conversions_remain_inline_not_per_share(self):
        item = self.source_precision_alert("freight_cost_not_crew_bonus")
        core = radar.verified_alert_core(item, item["source_title"])
        converted = core.replace("4000만달러", "4000만달러(약 536억원)").replace("23만달러", "23만달러(약 3억원)").replace("120만달러", "120만달러(약 16억원)")
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": converted}))
        self.assertTrue(radar.core_sentence_is_complete(converted))

    def test_gpu_core_keeps_original_application_period_and_denominator(self):
        item = self.source_precision_alert("public_gpu_allocation_not_new_capex")
        core = radar.verified_alert_core(item, item["source_title"])
        for term in ("NIPA", "2025년 12월부터 올해 1월", "공모", "1만3712장", "4224장", "30.8%", "배정"):
            self.assertIn(term, core)
        for term in ("과감하게", "추가 예산 확정", "3096장", "72.1%"):
            self.assertNotIn(term, core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": core.replace("2025년 12월부터 올해 1월", "오늘")}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_public_compute_metrics_need_named_provider_round_and_allocation(self):
        case = SOURCE_PRECISION_CASES["public_gpu_allocation_not_new_capex"]
        self.assertFalse(materiality.public_compute_allocation(case["title"], case["body"].replace("정보통신산업진흥원(NIPA)", "일부 관계자")))
        self.assertFalse(materiality.public_compute_allocation(case["title"], case["body"].replace("2025년 12월부터 올해 1월", "예전에")))

    def test_index_outlook_keeps_broker_conditions_and_target_not_profit_scenarios(self):
        item = self.source_precision_alert("conditional_index_forecast")
        core = radar.verified_alert_core(item, item["source_title"])
        for term in ("대신증권", "6일 보고서", "유가·금리의 추가 급등이 없고", "코스피", "7100선", "돌파·안착", "7500~7700선", "전망했다"):
            self.assertIn(term, core)
        self.assertNotIn("영업이익", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertTrue(radar.source_core_fact_errors(item))
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": core.replace("전망했다", "확정했다")}))

    def test_conditional_index_target_is_one_report_but_changed_threshold_is_new(self):
        item = self.source_precision_alert("conditional_index_forecast")
        identity = materiality.source_event_identity(item)
        self.assertTrue(identity.startswith("source_event:v2:conditional_index_outlook:"))
        self.assertEqual(identity, materiality.source_event_identity({**item, "link": "https://www.newsis.com/view/other", "source_title": "코스피 7500~7700 전망, 대신증권 조건부 분석"}))
        self.assertNotEqual(identity, materiality.source_event_identity({**item, "source_body": item["source_body"].replace("7100", "7200")}))

    def test_index_outlook_alias_requires_actual_existing_sent_receipt(self):
        item = self.source_precision_alert("conditional_index_forecast")
        identity = materiality.source_event_identity(item)
        proof = next(p for p in materiality.verified_event_aliases() if p['source_event_identity'] == identity)
        self.assertEqual((proof['run_id'], proof['message_id']), (37395127123, 2287))
        self.assertEqual(proof['source_body_sha256'], hashlib.sha256(item['source_body'].encode()).hexdigest())
        empty = {'seen': {}}
        telegram.migrate_seen_verified_event_aliases(empty)
        self.assertFalse(empty['seen'])
        state = {'seen': {'actual_article': {'title': item['source_title'], 'link': item['link'],
                                           'first_seen_kst': '2026-10-06T09:58:38+09:00', 'lanes': ['live']}}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertEqual(state['seen']['actual_article']['source_event_identity'], identity)

    def test_named_customer_api_delivery_is_preserved_without_inventing_revenue(self):
        item = self.source_precision_alert("named_customer_api_supply")
        core = radar.verified_alert_core(item, item["source_title"])
        for term in ("쿠콘", "현대해상", "API", "공급했다"):
            self.assertIn(term, core)
        self.assertNotIn("억원", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))

    def equity_foreground_alert(self, key):
        case = EQUITY_FOREGROUND_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_equity_foreground_all_seven_full_bodies_not_only_one_example(self):
        self.assertEqual(len(EQUITY_FOREGROUND_CASES), 7)
        now = NOW.replace(day=6, hour=10)
        for case in EQUITY_FOREGROUND_CASES.values():
            with self.subTest(case=case["id"]), patch.object(radar.base, "kst_now", return_value=now):
                self.assertEqual(hashlib.sha256(case["body"].encode()).hexdigest(), case["full_body_sha256"])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case["expected_keep"])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))

    def test_intraday_core_retains_both_issuers_prices_time_and_comparison(self):
        item = self.equity_foreground_alert("sector_intraday_price_observation")
        core = radar.verified_alert_core(item, item["source_title"])
        for term in ("한국거래소", "6일", "오전 9시4분", "센서뷰", "15.08%", "2175원", "스피어", "10.98%", "2만7300원", "전 거래일 대비"):
            self.assertIn(term, core)
        self.assertNotIn("신규 계약", core)
        self.assertNotIn("궤도", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_intraday_observation_does_not_accept_minor_move_or_another_basis(self):
        case = EQUITY_FOREGROUND_CASES["sector_intraday_price_observation"]
        self.assertTrue(materiality.intraday_equity_observations(case["title"], case["body"]))
        self.assertFalse(materiality.intraday_equity_observations(case["title"], case["body"].replace("15.08%", "0.08%")))
        self.assertFalse(materiality.intraday_equity_observations(case["title"], case["body"].replace("전 거래일 대비", "연초 대비")))

    def test_equity_index_in_crypto_column_keeps_actual_index_and_intraday_yield(self):
        item = self.equity_foreground_alert("equity_index_record_in_crypto_column")
        self.assertEqual(materiality.focus_kind(item["source_title"]), "equity_index")
        core = radar.verified_alert_core(item, item["source_title"])
        for term in ("나스닥지수", "1.05%", "사상 최고치", "10년물", "장중 5.347%"):
            self.assertIn(term, core)
        self.assertNotIn("ETF", core)
        self.assertNotIn("훈풍", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_index_record_forecast_is_not_an_observed_return(self):
        self.assertFalse(materiality.focus_matches("나스닥 사상 최고", "나스닥이 1.05% 올라 사상 최고치를 경신할 것으로 전망했다."))

    def test_equipment_investment_core_retains_population_period_and_observed_growth(self):
        item = self.equity_foreground_alert("computer_equipment_investment_observation")
        self.assertEqual(materiality.focus_kind(item["source_title"]), "capital_spending")
        core = radar.verified_alert_core(item, item["source_title"])
        for term in ("미국 기업", "컴퓨터 및 관련 장비", "올해 2분기", "1000억달러", "넘었고", "전년 동기 대비 60%"):
            self.assertIn(term, core)
        self.assertNotIn("10조달러", core)
        self.assertNotIn("5.5%", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_equipment_investment_conversion_remains_inline_and_source_aligned(self):
        item = self.equity_foreground_alert("computer_equipment_investment_observation")
        core = radar.verified_alert_core(item, item["source_title"])
        converted = core.replace("1000억달러", "1000억달러(약 134조원)")
        self.assertTrue(materiality.core_focus_aligned(item["source_title"], converted))
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": converted}))
        wrong = converted.replace("컴퓨터 및 관련 장비", "전체 AI 인프라")
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": wrong}))

    def test_hypothetical_rate_quote_is_not_a_released_investment_or_rate_change(self):
        case = EQUITY_FOREGROUND_CASES["computer_equipment_investment_observation"]
        hypothetical = next(s for s in materiality.source_sentences(case["body"]) if "5.5%" in s)
        self.assertFalse(materiality.business_investment_observation(hypothetical))
        self.assertFalse(materiality.evidence_is_new_event("rates_fx_or_macro", hypothetical))
        self.assertFalse(materiality.business_investment_observation("연구팀은 2032년까지 전체 AI 인프라 투자가 10조달러를 넘을 것으로 추산했다."))

    def test_crypto_price_recap_does_not_promote_old_jobs_or_background_policy(self):
        case = EQUITY_FOREGROUND_CASES["crypto_flat_recap"]
        assessment = materiality.assess(case["title"], case["body"])
        self.assertFalse(assessment["equity_publication"]["eligible"])
        self.assertEqual(assessment["scope_note"], "crypto_spot_recap_without_foreground_equity_catalyst")

    def test_crypto_foreground_regulatory_action_or_measured_etf_flow_is_preserved(self):
        self.assertTrue(eligible("CFTC, 가상자산 마진거래 규칙 제안", "CFTC는 가상자산 마진거래 규제에 관한 두 가지 규칙을 제안했다고 밝혔다."))
        self.assertTrue(eligible("비트코인 ETF, 하루 1조원 순유입", "미국 비트코인 ETF에는 5일 하루 1조원의 자금이 순유입됐다."))

    def test_local_robot_service_upgrade_is_not_industrial_deployment(self):
        case = EQUITY_FOREGROUND_CASES["local_cooking_robot_publicity"]
        self.assertFalse(eligible(case["title"], case["body"]))
        self.assertTrue(eligible("강남구, 로봇 업체와 100억원 공급 계약 체결", "강남구는 로봇 업체와 100억원 규모의 신규 로봇 공급 계약을 체결했다고 밝혔다."))

    def test_vendor_self_test_and_old_commercialization_do_not_substitute_for_new_event(self):
        case = EQUITY_FOREGROUND_CASES["unquantified_vendor_self_test"]
        self.assertFalse(eligible(case["title"], case["body"]))
        self.assertFalse(materiality.evidence_is_new_event("technology_or_clinical_stage", case["old_core"]))

    def test_self_test_does_not_block_new_paid_contract(self):
        title = "AI 보안 업체, 100억원 신규 공급계약 체결"
        body = "AI 보안 업체는 자체 테스트를 마쳤다. 업체는 금융 고객사와 100억원 규모 보안 기술 공급 계약을 체결했다고 밝혔다."
        self.assertTrue(eligible(title, body))

    def test_external_measured_technology_validation_is_not_routine_self_test(self):
        title = "반도체 검사 기술, 외부 고객 검증서 성능 30% 향상"
        body = "회사는 자체 시험 이후 외부 고객 검증에서 반도체 검사 기술의 성능이 30% 향상됐다고 밝혔다."
        self.assertTrue(eligible(title, body))

    def test_rounded_industry_order_uses_only_exact_audited_body_not_amount_tolerance(self):
        item = self.equity_foreground_alert("equipment_industry_rounded_reprint")
        identity = materiality.source_event_identity(item)
        precise = self.runtime_alert("equipment_order_precise_reprint")
        self.assertEqual(identity, materiality.source_event_identity(precise))
        for old, new in (("245억원", "246억원"), ("삼성전기", "LG이노텍"), ("6일 관련", "7일 관련"), ("MSVP", "TC본더")):
            with self.subTest(term=old):
                self.assertNotEqual(materiality.source_event_identity({**item, "source_body": item["source_body"].replace(old, new)}), identity)
        self.assertFalse(materiality.audited_source_event_identity({**item, "body_verified": False}))

    def test_audited_rounded_order_receipt_suppresses_other_publisher_reprint(self):
        old = self.equity_foreground_alert("equipment_industry_rounded_reprint")
        other = self.runtime_alert("equipment_order_precise_reprint")
        now = NOW.replace(day=6, hour=10)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([old], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([other], now, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_independent_new_equipment_volume_is_not_merged_with_an_old_order(self):
        order = self.equity_foreground_alert("equipment_industry_rounded_reprint")
        volume = alert("한미반도체, MSVP 판매량 200대 돌파", "한미반도체는 올해 MSVP 장비 판매량이 200대를 돌파해 전년 대비 2배 이상 늘었다고 밝혔다.", "https://www.fnnews.com/news/20261006099999")
        self.assertNotEqual(materiality.source_event_identity(volume), materiality.source_event_identity(order))

    def test_price_movement_verb_is_not_semiconductor_shipments(self):
        case = EQUITY_FOREGROUND_CASES["sector_intraday_price_observation"]
        self.assertNotIn("earnings_or_guidance", {row["kind"] for row in materiality.assess(case["title"], case["body"])["evidence"]})

    def followon_alert(self, key):
        case = FOLLOWON_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_followon_seven_full_bodies_keep_five_equity_events_not_two_services(self):
        self.assertEqual(len(FOLLOWON_CASES), 7)
        now = NOW.replace(day=6, hour=10)
        for case in FOLLOWON_CASES.values():
            with self.subTest(case=case["id"]), patch.object(radar.base, "kst_now", return_value=now):
                self.assertEqual(hashlib.sha256(case["body"].encode()).hexdigest(), case["full_body_sha256"])
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30) if item else []
                self.assertEqual(bool(selected), case["expected_keep"])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))

    def test_data_center_contract_core_keeps_counterparty_capacity_and_discussion_stage(self):
        case = FOLLOWON_CASES["cooling_contract_not_half_year_order_total"]
        item = self.followon_alert(case["id"])
        core = radar.verified_alert_core(item, case["title"])
        for term in ("LG전자", "에어 컨트롤 콘셉트", "5GW", "장기 공급계약", "CDU", "논의 중"):
            self.assertIn(term, core)
        self.assertNotIn("6000억원", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_equipment_acronym_description_and_press_release_share_exact_order_identity(self):
        first = self.runtime_alert("equipment_order_precise_reprint")
        other = self.followon_alert("equipment_acronym_description_reprint")
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith("source_event:v2:commercial_order:"))
        self.assertEqual(materiality.source_event_identity(other), identity)
        self.assertNotEqual(materiality.source_event_identity({**other, "source_body": other["source_body"].replace("삼성전기", "LG이노텍")}), identity)

    def test_route_study_reprint_core_keeps_signed_mou_not_only_country_responsibilities(self):
        case = FOLLOWON_CASES["industrial_route_study_reprint"]
        item = self.followon_alert(case["id"])
        core = radar.verified_alert_core(item, case["title"])
        for term in ("현대글로비스", "LGL", "SMR", "한미 항로", "공동 검토", "업무협약", "체결"):
            self.assertIn(term, core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_route_study_same_mou_dedupes_across_publisher_and_headline_scope(self):
        first = self.runtime_alert("industrial_mou_not_sector_aspiration")
        other = self.followon_alert("industrial_route_study_reprint")
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith("source_event:v2:industrial_route_study:"))
        self.assertEqual(materiality.source_event_identity(other), identity)
        now = NOW.replace(day=6, hour=10)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([first], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([other], now, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)

    def test_route_study_changed_partner_date_terms_or_stage_remain_new(self):
        first = self.followon_alert("industrial_route_study_reprint")
        identity = materiality.source_event_identity(first)
        for old, new in (("LGL", "OTHER"), ("6일", "7일"), ("체결했다고", "10억원 규모로 체결했다고"), ("업무협약(MOU)", "추가 협약 업무협약(MOU)")):
            changed = {**first, "source_body": first["source_body"].replace(old, new)}
            with self.subTest(term=old):
                self.assertNotEqual(materiality.source_event_identity(changed), identity)
        uncertain = first["source_body"].replace("체결했다고", "체결할 가능성이 있다고")
        self.assertFalse(materiality.industrial_route_study_terms(first["source_title"], uncertain, first["published"]))
        self.assertFalse(materiality.source_event_identity({**first, "body_verified": False}))

    def test_audited_route_study_alias_uses_existing_receipt_without_seeding_missing_state(self):
        case = FOLLOWON_CASES["industrial_route_study_reprint"]
        identity = materiality.source_event_identity(self.followon_alert(case["id"]))
        proofs = json.loads(telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))["entries"]
        proof = next(row for row in proofs if row["link"] == case["url"])
        self.assertEqual(proof["source_body_sha256"], case["full_body_sha256"])
        self.assertEqual(proof["source_event_identity"], identity)
        self.assertEqual(proof["message_id"], FOLLOWON_FIXTURE["message_id"])
        absent = {"seen": {}}
        telegram.migrate_seen_verified_event_aliases(absent)
        self.assertFalse(absent["seen"])
        state = {"seen": {"old": {"title": case["title"], "link": case["url"], "first_seen_kst": "2026-10-06T09:25:00+09:00"}}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertIn("event:" + telegram.digest_seen(identity), state["seen"])

    def test_service_promotion_does_not_hide_a_separate_verified_industrial_contract(self):
        title = "정품인증 스티커 업체, 반도체 신규 공급계약 체결"
        body = "정품인증 스티커 업체는 반도체 고객사와 100억원 규모의 신규 장비 공급 계약을 체결했다고 밝혔다."
        self.assertTrue(eligible(title, body))

    def test_student_rental_notice_nationwide_label_is_not_national_housing_underwriting(self):
        case = FOLLOWON_CASES["student_rental_supply_notice"]
        self.assertFalse(eligible(case["title"], case["body"]))
        policy = CASES["housing"]
        self.assertTrue(eligible(policy["title"], policy["body"]))

    def runtime_alert(self, key):
        case = FINAL_RUNTIME_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_all_seven_actual_runtime_sources_keep_only_their_headline_change(self):
        now = NOW.replace(day=6, hour=9)
        for case in FINAL_RUNTIME_CASES.values():
            with self.subTest(case=case["id"]), patch.object(radar.base, "kst_now", return_value=now):
                item = classify(case, now)
                selected = radar.quality_display_alerts([item], 30)
                self.assertEqual(len(selected), 1)
                self.assertFalse(radar.source_core_fact_errors(selected[0]))
                self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))

    def test_actual_background_and_segment_forecast_cores_are_rejected(self):
        now = NOW.replace(day=6, hour=9)
        for case in FINAL_RUNTIME_CASES.values():
            if case.get("old_core"):
                item = radar.normalize_alert_for_output(classify(case, now))
                with self.subTest(case=case["id"]):
                    self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_signed_smr_mou_keeps_parties_route_and_research_not_vessel_order(self):
        item = radar.normalize_alert_for_output(classify(FINAL_RUNTIME_CASES["industrial_mou_not_sector_aspiration"], NOW.replace(day=6, hour=9)))
        for term in ("현대글로비스", "LGL", "SMR", "한국과 미국", "공동 검토", "업무협약", "공동 연구할 예정"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertNotIn("수주", item["telegram_core_fact"])
        self.assertEqual({row["kind"] for row in radar.source_market_materiality(item)["evidence"]}, {"industrial_partnership_execution"})

    def test_smr_sector_aspiration_without_signed_mou_is_not_execution(self):
        case = FINAL_RUNTIME_CASES["industrial_mou_not_sector_aspiration"]
        self.assertFalse(eligible(case["title"], case["old_core"]))
        self.assertFalse(eligible(case["title"], case["body"].replace("체결했다고", "체결할 가능성이 있다고")))

    def test_three_target_cuts_keep_broker_issuer_and_previous_current_prices(self):
        for key, terms in (("department_store_target_cut_not_segment_forecast", ("유안타증권", "현대백화점", "26만3000원", "12만원")),
                           ("biopharma_broker_target_revision", ("다올투자증권", "삼성바이오로직스", "210만원", "200만원")),
                           ("portal_target_cut_not_quarter_forecast", ("대신증권", "NAVER", "32만원", "29만원"))):
            core = radar.normalize_alert_for_output(classify(FINAL_RUNTIME_CASES[key], NOW.replace(day=6, hour=9)))["telegram_core_fact"]
            with self.subTest(case=key):
                for term in terms:
                    self.assertIn(term, core)
                self.assertIn("하향 조정했다", core)

    def test_primary_reported_earnings_are_not_overridden_by_secondary_target_revision(self):
        title = "HL디앤아이한라, 상반기 영업익 34%↑…증권가도 목표주가 상향"
        body = "HL D&I한라의 상반기 연결 기준 매출은 8302억원, 영업이익은 455억원으로 전년비 각각 13.5%, 34.1% 증가했다."
        item = alert(title, body)
        self.assertEqual(materiality.focus_kind(title), "earnings")
        self.assertEqual(materiality.analyst_target_revision_terms(title, body), {})
        core = radar.verified_alert_core(item, title)
        self.assertIn("455억원", core)
        self.assertIn("34.1%", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])

    def test_foreign_target_revision_keeps_broker_issuer_and_original_currency(self):
        title = "[美특징주]팔로알토, 수요 증가 전망·플랫폼 전략 ‘긍정적’ 평가…개장전 1%↑"
        body = ("TD코웬은 2일(현지 시간) 인공지능(AI) 확산에 따른 사이버보안 수요 증가와 플랫폼 전략의 성과를 반영해 팔로 알토 네트웍스(PANW)의 목표주가를 기존 400달러에서 440달러로 상향하고, 투자의견은 그대로 ‘매수’를 유지했다.\n"
                "플랫폼화 고객의 순매출유지율(NRR)은 120%를 기록했다.")
        item = {**alert(title, body), "telegram_core_fact": "플랫폼화 고객의 순매출유지율(NRR)은 120%를 기록했다."}
        core = radar.verified_alert_core(item, title)
        for term in ("TD코웬", "PANW", "400달러", "440달러", "상향"):
            self.assertIn(term, core)
        self.assertNotIn("120%", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])

    def test_target_revision_same_source_terms_dedupe_but_new_target_or_broker_survives(self):
        first = self.runtime_alert("portal_target_cut_not_quarter_forecast")
        same = {**first, "source_title": "대신證 NAVER 목표가 하향", "news": "대신證 NAVER 목표가 하향", "link": "https://www.etnews.com/20261006009998"}
        self.assertEqual(materiality.source_event_identity(first), materiality.source_event_identity(same))
        for old, new in (("29만원", "28만원"), ("대신", "한화"), ("NAVER", "KAKAO")):
            changed = {**first, "source_title": first["source_title"].replace(old, new), "source_body": first["source_body"].replace(old, new)}
            with self.subTest(term=old):
                self.assertNotEqual(materiality.source_event_identity(first), materiality.source_event_identity(changed))

    def test_equipment_order_same_exact_terms_dedupe_without_rounding_different_values(self):
        first = self.runtime_alert("equipment_order_precise_reprint")
        same = {**first, "source_body": first["source_body"].replace("244억8000만원", "244.8억원"), "source_title": "한미반도체, 삼성전기 MSVP 장비 공급계약"}
        self.assertEqual(materiality.source_event_identity(first), materiality.source_event_identity(same))
        for old, new in (("244억8000만원", "244억9000만원"), ("삼성전기", "LG이노텍"), ("MSVP", "OTHER"), ("6일", "7일"), ("수주했다고", "추가 수주했다고")):
            changed = {**first, "source_title": first["source_title"].replace(old, new), "source_body": first["source_body"].replace(old, new)}
            with self.subTest(term=old):
                self.assertNotEqual(materiality.source_event_identity(first), materiality.source_event_identity(changed))
        prior = FINAL_RUNTIME_FIXTURE["previous_order"]
        rounded = {**alert(prior["title"], prior["body"], prior["url"]), "published": prior["published"]}
        self.assertNotEqual(materiality.source_event_identity(first), materiality.source_event_identity(rounded))

    def test_audited_equipment_alias_migrates_only_the_existing_successful_receipt(self):
        previous = FINAL_RUNTIME_FIXTURE["previous_order"]
        first = self.runtime_alert("equipment_order_precise_reprint")
        identity = materiality.source_event_identity(first)
        proofs = json.loads(telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))["entries"]
        proof = next(row for row in proofs if row["link"] == previous["url"])
        self.assertEqual(proof["source_body_sha256"], previous["full_body_sha256"])
        self.assertEqual(proof["message_id"], previous["message_id"])
        self.assertEqual(proof["source_event_identity"], identity)
        absent = {"seen": {}}
        telegram.migrate_seen_verified_event_aliases(absent)
        self.assertFalse(absent["seen"])
        state = {"seen": {"historical": {"title": previous["title"], "link": previous["url"], "first_seen_kst": "2026-10-06T08:36:00+09:00"}}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertIn("event:" + telegram.digest_seen(identity), state["seen"])

    def test_current_holdings_core_names_owner_issuer_new_shares_and_stake(self):
        case = FINAL_RUNTIME_CASES["holder_company_and_current_share_change"]
        core = radar.normalize_alert_for_output(classify(case, NOW.replace(day=6, hour=9)))["telegram_core_fact"]
        for term in ("제이엘케이", "KB자산운용", "130만9845주", "168만6664주", "5.09%", "6.56%", "단순투자"):
            self.assertIn(term, core)
        self.assertNotIn("지난 6월", core)

    def test_missing_source_verification_cannot_create_order_or_target_identity(self):
        for key in ("equipment_order_precise_reprint", "portal_target_cut_not_quarter_forecast"):
            item = self.runtime_alert(key)
            self.assertFalse(materiality.source_event_identity({**item, "body_verified": False}))
            self.assertFalse(materiality.source_event_identity({**item, "published": ""}))

    def broker_alert(self, key):
        case = BROKER_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_one_broker_report_is_one_event_despite_company_abbreviation_and_publisher(self):
        first, second = (self.broker_alert(key) for key in BROKER_CASES)
        self.assertEqual(materiality.source_event_identity(first), materiality.source_event_identity(second))
        self.assertTrue(materiality.source_event_identity(first).startswith("source_event:v2:broker_earnings:"))
        now = NOW.replace(day=6, hour=9)
        with patch.object(radar.base, "kst_now", return_value=now):
            candidates = [classify(case, now) for case in BROKER_CASES.values()]
            self.assertTrue(all(candidates))
            self.assertEqual(len(radar.quality_display_alerts(candidates, 30)), 1)

    def test_broker_duplicate_across_runs_is_quiet_but_new_profit_forecast_survives(self):
        now = NOW.replace(day=6, hour=9)
        first, second = (self.broker_alert(key) for key in BROKER_CASES)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([first], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([second], now, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            changed = {**second, "source_body": second["source_body"].replace("5890억", "6890억")}
            fresh, skipped = telegram.filter_previously_seen_alerts([changed], now, "live")
            self.assertEqual(len(fresh), 1)
            self.assertFalse(skipped)

    def test_broker_report_new_terms_and_correction_are_not_hidden(self):
        first = self.broker_alert("broker_report_newsis")
        identity = materiality.source_event_identity(first)
        for old, new in (("5890억", "6890억"), ("1조3380억", "1조4380억"), ("3분기", "2분기"),
                         ("대신", "한화"), ("삼성바이오", "OTHER바이오"), ("200만원", "210만원"),
                         ("2조4780억", "2조5780억"), ("성장폭 확대", "성장폭 확대 정정")):
            changed = {**first, "source_title": first["source_title"].replace(old, new), "source_body": first["source_body"].replace(old, new)}
            with self.subTest(term=old):
                self.assertNotEqual(materiality.source_event_identity(changed), identity)

    def test_broker_core_names_source_issuer_quarter_and_forecast_not_past_strike(self):
        now = NOW.replace(day=6, hour=9)
        for case in BROKER_CASES.values():
            with self.subTest(case=case["id"]):
                item = radar.normalize_alert_for_output(classify(case, now))
                self.assertEqual(item["telegram_core_fact"], "대신증권은 삼성바이오로직스의 3분기 매출을 1조3380억원, 영업이익을 5890억원으로 예상했다.")
                self.assertFalse(radar.source_core_fact_errors(item))
                self.assertTrue(radar.core_sentence_is_complete(item["telegram_core_fact"]))
                self.assertNotIn("지난 5월", item["telegram_core_fact"])
                self.assertNotIn("공시", item["telegram_core_fact"])

    def test_broker_core_amounts_are_source_bound_not_company_specific_template(self):
        case = BROKER_CASES["broker_report_newsis"]
        core = radar.source_headline_event_fact(case["title"].replace("삼성바이오", "OTHER바이오"),
                                              case["body"].replace("삼성바이오", "OTHER바이오").replace("5890억", "6890억"))
        self.assertIn("OTHER바이오로직스", core)
        self.assertIn("6890억원", core)
        self.assertNotIn("삼성바이오", core)

    def test_company_release_unverified_body_and_missing_date_do_not_claim_broker_identity(self):
        first = self.broker_alert("broker_report_newsis")
        self.assertFalse(materiality.source_event_identity({**first, "body_verified": False}))
        self.assertFalse(materiality.source_event_identity({**first, "published": ""}))
        self.assertFalse(materiality.broker_earnings_report_terms("삼성바이오로직스, 3분기 실적 공시", first["source_body"]))
        self.assertFalse(materiality.broker_earnings_report_terms(first["source_title"], first["source_body"].replace("대신증권", "한화증권")))

    def test_broker_copy_forecasts_keep_exact_annual_amounts_and_target(self):
        for case in BROKER_CASES.values():
            terms = materiality.broker_earnings_report_terms(case["title"], case["body"], case["published"])
            self.assertEqual(terms["annual_forecast_won"], ["5531000000000", "2478000000000"])
            self.assertEqual(terms["current_target_won"], ["2000000"])
            self.assertEqual(terms["year"], "2026")

    def test_broker_fiscal_year_is_not_replaced_by_publication_year(self):
        case = BROKER_CASES["broker_report_etoday"]
        terms = materiality.broker_earnings_report_terms(case["title"], case["body"].replace("2026년", "2027회계연도"), case["published"])
        self.assertEqual(terms["year"], "2027")
        unknown = case["body"].replace("2026년", "").replace("올해", "")
        self.assertEqual(materiality.broker_earnings_report_terms(case["title"], unknown, case["published"])["year"], "")
        self.assertFalse(materiality.source_event_identity({**self.broker_alert(case["id"]), "source_body": unknown}))

    def test_broker_aliases_are_bound_to_actual_full_source_and_delivery_receipts(self):
        proofs = json.loads(telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))["entries"]
        for case in BROKER_CASES.values():
            proof = next(row for row in proofs if row["link"] == case["url"])
            self.assertEqual(proof["source_body_sha256"], case["full_body_sha256"])
            self.assertEqual(proof["run_id"], case["run_id"])
            self.assertEqual(proof["message_id"], case["message_id"])
            self.assertEqual(proof["source_event_identity"], materiality.source_event_identity(self.broker_alert(case["id"])))

    def noise_alert(self, key):
        case = NOISE_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_actual_noise_batch_keeps_three_equity_events_not_four_publicity_notices(self):
        self.assertEqual(len(NOISE_CASES), 7)
        now = LIVE_NOW.replace(hour=22)
        candidates = []
        with patch.object(radar.base, "kst_now", return_value=now):
            for case in NOISE_CASES.values():
                candidate = classify(case, now)
                selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                with self.subTest(case=case["id"]):
                    self.assertEqual(bool(selected), case["expected_keep"])
                    if selected:
                        self.assertFalse(radar.source_core_fact_errors(selected[0]))
                        self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))
                        candidates.extend(selected)
            self.assertEqual(len(radar.quality_display_alerts(candidates, 30)), 3)

    def test_same_merger_buyer_target_and_short_copies_select_once(self):
        now = LIVE_NOW.replace(hour=22)
        cases = [DECISION_CASES["merger_agreement_short_copy"], DECISION_CASES["merger_agreement_long_copy"],
                 NOISE_CASES["same_merger_from_target_perspective"]]
        candidates = [classify(case, now) for case in cases]
        self.assertTrue(all(candidates))
        identities = {materiality.source_event_identity(item) for item in candidates}
        self.assertEqual(len(identities), 1)
        with patch.object(radar.base, "kst_now", return_value=now):
            self.assertEqual(len(radar.quality_display_alerts(candidates, 30)), 1)

    def test_target_perspective_merger_core_uses_total_not_first_per_share_price(self):
        case = NOISE_CASES["same_merger_from_target_perspective"]
        core = radar.source_headline_event_fact(case["title"], case["body"])
        self.assertEqual(core, "C.H.로빈슨은 58억달러 규모의 RXO 인수에 합의했다.")
        self.assertNotIn("30.25", core)
        changed = radar.source_headline_event_fact(case["title"].replace("58억", "60억"), case["body"].replace("58억", "60억"))
        self.assertIn("60억달러", changed)
        self.assertNotIn("58억", changed)

    def test_target_perspective_merger_does_not_resend_after_buyer_report(self):
        now = LIVE_NOW.replace(hour=22)
        buyer = self.decision_alert("merger_agreement_long_copy")
        target = self.noise_alert("same_merger_from_target_perspective")
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([buyer], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([target], now, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            revised = {**target, "source_title": target["source_title"].replace("58억", "60억"),
                       "source_body": target["source_body"].replace("58억", "60억")}
            fresh, skipped = telegram.filter_previously_seen_alerts([revised], now, "live")
            self.assertEqual(len(fresh), 1)
            self.assertFalse(skipped)

    def test_target_merger_alias_has_source_hash_delivery_proof_and_existing_receipt(self):
        case = NOISE_CASES["same_merger_from_target_perspective"]
        proofs = json.loads(telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))["entries"]
        proof = next(row for row in proofs if row["link"] == case["url"])
        self.assertEqual(proof["source_body_sha256"], case["full_body_sha256"])
        self.assertEqual(proof["source_event_identity"], materiality.source_event_identity(self.noise_alert(case["id"])))
        self.assertEqual(proof["run_id"], NOISE_FIXTURE["run_id"])
        self.assertEqual(proof["message_id"], NOISE_FIXTURE["message_id"])
        state = {"seen": {"link:actual": {"title": proof["source_title"], "link": proof["link"], "first_seen_kst": case["published"]}}}
        telegram.migrate_seen_verified_event_aliases(state)
        receipt = state["seen"]["event:" + telegram.digest_seen(proof["source_event_identity"])]
        self.assertEqual(receipt["event_alias_evidence_message_id"], NOISE_FIXTURE["message_id"])

    def test_productivity_service_expansion_is_not_industrial_production(self):
        case = NOISE_CASES["subscription_productivity_not_factory_capacity"]
        assessment = materiality.assess(case["title"], case["body"])
        self.assertFalse(any(item["kind"] == "physical_supply_or_capacity" for item in assessment["evidence"]))
        self.assertFalse(eligible(case["title"], case["body"]))
        self.assertTrue(eligible("LG유플러스, 데이터센터 전력설비 증설 예산 확정", "LG유플러스는 AI 데이터센터 전력설비 증설에 1000억원을 집행하기로 확정했다고 공시했다."))

    def test_fashion_launch_noise_does_not_block_real_issuer_earnings_or_contract(self):
        case = NOISE_CASES["fashion_collection_not_industrial_capacity"]
        self.assertEqual(materiality.assess(case["title"], case["body"])["reason"], "consumer_fashion_publicity_without_new_financial_change")
        self.assertTrue(eligible("LF, 패션사업 영업이익 30% 증가 공시", "LF는 3분기 패션사업 영업이익이 전년 대비 30% 증가한 500억원이라고 공시했다."))
        self.assertTrue(eligible("패션기업, 미국 유통사와 1000억원 공급 계약 체결", "패션기업은 미국 유통사와 1000억원 규모의 상품 공급 계약을 체결했다고 밝혔다."))

    def test_local_student_welfare_is_not_equity_policy_but_factory_permit_is(self):
        case = NOISE_CASES["municipal_student_welfare_not_equity_policy"]
        self.assertEqual(materiality.assess(case["title"], case["body"])["reason"], "local_education_welfare_notice_not_equity_event")
        self.assertTrue(eligible("순창군, 반도체 신규 공장 인허가 승인", "순창군은 상장 반도체 기업의 신규 공장 인허가를 승인했다고 발표했다."))

    def test_startup_profile_old_commercialization_does_not_block_new_execution(self):
        case = NOISE_CASES["startup_profile_not_new_cooling_execution"]
        self.assertEqual(materiality.assess(case["title"], case["body"])["reason"], "startup_profile_without_new_verified_execution")
        body = "[판교 창업존 입주기업 인터뷰] 씨이앤에스는 이번에 AI 데이터센터 운영사와 100억원의 냉각장비 공급 계약을 체결했다고 밝혔다."
        self.assertTrue(eligible("씨이앤에스, AI 데이터센터 냉각장비 공급 계약 체결", body))
        body = "[판교 창업존 입주기업 인터뷰] 씨이앤에스는 AI 데이터센터 고객 검증을 완료하고 냉각장비의 전력효율 30% 개선 실증 결과를 발표했다."
        self.assertTrue(eligible("씨이앤에스, AI 데이터센터 냉각장비 고객 검증 완료", body))

    def test_telecom_proposed_staffing_cost_core_retains_scope_numbers_and_stage(self):
        item = radar.normalize_alert_for_output(classify(NOISE_CASES["telecom_operating_requirement_is_policy_change"], LIVE_NOW.replace(hour=22)))
        for term in ("SK텔레콤", "1만명당", "1명", "KT·LG유플러스", "최소 3명", "추진"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertNotIn("확정", item["telegram_core_fact"])

    def decision_alert(self, key):
        case = DECISION_CASES[key]
        return {**alert(case["title"], case["body"], case["url"]), "published": case["published"]}

    def test_actual_decision_articles_select_six_then_five_unique_events(self):
        self.assertEqual(len(DECISION_CASES), 7)
        candidates = [classify(case, LIVE_NOW.replace(hour=22)) for case in DECISION_CASES.values()]
        with patch.object(radar.base, "kst_now", return_value=LIVE_NOW.replace(hour=22)):
            for case, candidate in zip(DECISION_CASES.values(), candidates):
                with self.subTest(case=case["id"]):
                    selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                    self.assertEqual(bool(selected), case["expected_keep"])
                    if selected:
                        self.assertFalse(radar.source_core_fact_errors(selected[0]))
                        self.assertTrue(radar.core_sentence_is_complete(selected[0]["telegram_core_fact"]))
            selected = radar.quality_display_alerts([item for item in candidates if item], 30)
        self.assertEqual(len(selected), 5)
        self.assertFalse(generated_guard.duplicate_event_errors(selected, radar))

    def test_actual_decision_old_cores_cannot_replace_reported_event(self):
        for case in DECISION_CASES.values():
            if not case["expected_keep"]:
                continue
            with self.subTest(case=case["id"]):
                item = radar.normalize_alert_for_output(classify(case, LIVE_NOW.replace(hour=22)))
                self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": case["old_core"]}))

    def test_opec_core_retains_current_group_period_and_decision(self):
        item = radar.normalize_alert_for_output(classify(DECISION_CASES["opec_production_target_not_old_oil_background"], LIVE_NOW.replace(hour=22)))
        for term in ("OPEC+", "7개국", "내달", "생산 목표", "유지", "합의"):
            self.assertIn(term, item["telegram_core_fact"])
        for term in ("G7", "비축유", "100달러"):
            self.assertNotIn(term, item["telegram_core_fact"])

    def test_opec_population_and_month_are_source_bound(self):
        case = DECISION_CASES["opec_production_target_not_old_oil_background"]
        core = radar.source_headline_event_fact(case["title"], case["body"].replace("내 7개국", "내 8개국").replace("내달 생산", "12월 생산"))
        self.assertIn("8개국", core)
        self.assertIn("12월", core)
        self.assertNotIn("7개국", core)

    def test_fda_core_retains_approval_product_facility_and_capacity(self):
        item = radar.normalize_alert_for_output(classify(DECISION_CASES["fda_facility_approval_not_analyst_revenue"], LIVE_NOW.replace(hour=22)))
        for term in ("알보테크", "FDA", "심랜디", "DSM2", "미국용 원료의약품", "2배", "회사는"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertNotIn("컨센서스", item["telegram_core_fact"])

    def test_fda_facility_and_capacity_are_not_canned(self):
        case = DECISION_CASES["fda_facility_approval_not_analyst_revenue"]
        body = case["body"].replace("DSM2", "DSM3").replace("2배", "3배")
        core = radar.source_headline_event_fact(case["title"], body)
        self.assertIn("DSM3", core)
        self.assertIn("3배", core)
        self.assertNotIn("DSM2", core)
        self.assertNotIn("2배", core)

    def test_nav_core_retains_comparison_basis_and_unaudited_forecast(self):
        item = radar.normalize_alert_for_output(classify(DECISION_CASES["issuer_nav_forecast_not_metric_list"], LIVE_NOW.replace(hour=22)))
        for term in ("디파이 디벨롭먼트", "9월 30일", "8월 12일", "100%", "예상했다", "감사 전", "달라질 수 있다"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertFalse(radar.source_core_fact_errors(item))

    def test_nav_forecast_growth_and_baseline_come_from_source(self):
        case = DECISION_CASES["issuer_nav_forecast_not_metric_list"]
        core = radar.source_headline_event_fact(case["title"], case["body"].replace("8월 12일", "8월 15일").replace("100%", "120%"))
        self.assertIn("8월 15일", core)
        self.assertIn("120%", core)
        self.assertNotIn("100%", core)

    def test_old_unlisted_survey_and_advice_are_not_current_market_change(self):
        case = DECISION_CASES["historical_survey_not_new_execution"]
        assessment = materiality.assess(case["title"], case["body"])
        self.assertEqual(assessment["disposition"], "exclude")
        self.assertEqual(assessment["reason"], "historical_survey_and_policy_advice_without_new_execution")
        self.assertTrue(eligible("상장 반도체 기업, 신규 설비투자 예산 1000억원 확정", "상장 반도체 기업은 신규 공장 설비투자 예산 1000억원을 확정했다고 공시했다. 이전 보고서는 2019년부터 2023년까지 누적 매출을 조사하고 지원 제도를 마련해야 한다고 제언했다."))

    def test_dotted_company_name_is_not_a_sentence_boundary(self):
        case = DECISION_CASES["merger_agreement_long_copy"]
        lead = materiality.source_sentences(case["body"])[0]
        self.assertTrue(lead.startswith("C.H. 로빈슨(CHRW)이"))
        self.assertIn("인수하는 합병계약", lead)
        for sentence in materiality.source_sentences(case["body"]):
            self.assertNotEqual(sentence, "C.H.")

    def test_same_merger_synopsis_and_full_report_have_one_identity(self):
        short = self.decision_alert("merger_agreement_short_copy")
        long = self.decision_alert("merger_agreement_long_copy")
        self.assertEqual(materiality.source_event_identity(short), materiality.source_event_identity(long))
        self.assertTrue(materiality.source_event_identity(short).startswith("source_event:v2:merger_agreement:"))

    def test_merger_changes_amount_target_or_explicit_revised_terms_are_new(self):
        first = self.decision_alert("merger_agreement_long_copy")
        for old, new in (("58억", "60억"), ("RXO", "OTHER"), ("인수 합의", "인수 합의 조건 변경")):
            changed = {**first, "source_title": first["source_title"].replace(old, new), "source_body": first["source_body"].replace(old, new)}
            with self.subTest(change=old):
                self.assertNotEqual(materiality.source_event_identity(first), materiality.source_event_identity(changed))

    def test_merger_duplicates_are_quiet_across_runs_not_changed_contracts(self):
        now = LIVE_NOW.replace(hour=22)
        short = self.decision_alert("merger_agreement_short_copy")
        long = self.decision_alert("merger_agreement_long_copy")
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, "SEEN_PATH", Path(folder) / "seen.json"), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            telegram.record_seen_alerts([long], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([short], now, "live")
            self.assertFalse(fresh)
            self.assertEqual(len(skipped), 1)
            changed = {**short, "source_title": short["source_title"].replace("58억", "60억"), "source_body": short["source_body"].replace("58억", "60억")}
            fresh, skipped = telegram.filter_previously_seen_alerts([changed], now, "live")
            self.assertEqual(len(fresh), 1)
            self.assertFalse(skipped)

    def test_merger_audited_receipts_match_source_hash_and_announcement(self):
        proofs = json.loads(telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))["entries"]
        for key in ("merger_agreement_short_copy", "merger_agreement_long_copy"):
            case = DECISION_CASES[key]
            proof = next(row for row in proofs if row["link"] == case["url"])
            self.assertEqual(proof["source_body_sha256"], case["full_body_sha256"])
            self.assertEqual(proof["source_event_identity"], materiality.source_event_identity(self.decision_alert(key)))
            self.assertEqual(proof["run_id"], DECISION_FIXTURE["run_id"])
            self.assertEqual(proof["message_id"], DECISION_FIXTURE["message_id"])
        state = {"seen": {}}
        telegram.migrate_seen_verified_event_aliases(state)
        self.assertFalse(state["seen"])

    def test_merger_uncertain_title_has_no_signed_event_identity(self):
        first = self.decision_alert("merger_agreement_long_copy")
        for suffix in (" 협상 중", " 논의 중", " 검토", " 가능성"):
            self.assertFalse(materiality.merger_agreement_terms(first["source_title"] + suffix, first["source_body"]))

    def test_weekly_preview_keeps_quantified_broker_revision_not_company_guidance(self):
        item = radar.normalize_alert_for_output(classify(DECISION_CASES["broker_consensus_revision_not_optimism"], LIVE_NOW.replace(hour=22)))
        for term in ("NH투자증권에 따르면", "삼성전자", "3분기", "컨센서스", "9월초", "113조1000억원", "109조5000억원", "하향"):
            self.assertIn(term, item["telegram_core_fact"])
        self.assertNotIn("가이던스", item["telegram_core_fact"])

    def test_consensus_revision_amount_and_period_are_source_bound(self):
        case = DECISION_CASES["broker_consensus_revision_not_optimism"]
        core = radar.source_headline_event_fact(case["title"], case["body"].replace("3분기", "4분기").replace("109조5000억원", "99조5000억원"))
        self.assertIn("4분기", core)
        self.assertIn("99조5000억원", core)
        self.assertNotIn("109조5000억원", core)

    def test_weekly_preview_cannot_use_other_company_or_old_earnings(self):
        case = DECISION_CASES["broker_consensus_revision_not_optimism"]
        item = radar.normalize_alert_for_output(classify(case, LIVE_NOW.replace(hour=22)))
        wrong = {**item, "telegram_core_fact": "삼성전자는 지난해 연간 영업이익 50조원을 기록했다."}
        self.assertFalse(radar.source_output_aligned(wrong))
        other = {**item, "telegram_core_fact": item["telegram_core_fact"].replace("삼성전자", "SK하이닉스")}
        self.assertFalse(radar.source_output_aligned(other))

    def test_fixture_publication_times_are_retained_without_inferred_dates(self):
        case = DECISION_CASES["broker_consensus_revision_not_optimism"]
        item = classify(case, LIVE_NOW.replace(hour=22))
        self.assertEqual(item["published"], case["published"])

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

    def test_foreign_amount_extractor_keeps_adjacent_korean_units(self):
        for text in ("최대 11억 7천만 달러", "최대 11억7000만 달러"):
            amounts = radar.extract_foreign_amounts(text)
            self.assertEqual(len(amounts), 1)
            self.assertEqual(amounts[0]["amount"], 1170000000)
            self.assertEqual(amounts[0]["raw"], text.removeprefix("최대 "))

    def test_short_license_copy_also_has_every_inline_currency_conversion(self):
        now = LIVE_NOW.replace(hour=21)
        candidate = classify(EQUIVALENCE_CASES["exclusive_license_short_copy"], now)
        snapshot = {"rates": {"USD": {"value": 1420.0, "status": "최근거래", "reference_time_kst": now.isoformat(),
                    "query_time_kst": now.isoformat(), "source": "Test only", "url": "https://example.com/test-fx"}}}
        with patch.object(radar.base, "kst_now", return_value=now), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}), patch.object(radar, "collect_fx_snapshot", return_value=snapshot):
            selected = radar.compact_quality_final_alerts([candidate], 30)
            report = radar.compact_report(selected, {}, {}, now)
            radar.guard_preopen_report(report)
        self.assertEqual(len(selected), 1)
        self.assertIn("11억 7천만 달러(약 1조6,614억원)", report)
        self.assertIn("1억 달러(약 1,420억원)", report)

    def test_adjacent_units_do_not_change_foreign_decimal_or_english_scale(self):
        for text, expected in (("1.5억 달러", 150000000), ("$42 billion", 42000000000), ("3천5백만 유로", 35000000)):
            self.assertEqual(radar.extract_foreign_amounts(text)[0]["amount"], expected)

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

    def delivery_scope_alert(self, key):
        case = DELIVERY_SCOPE_CASES[key]
        return {**alert(case['title'], case['body'], case['url']), 'published': case['published'],
                'telegram_core_fact': case['old_core']}

    def test_last_version82_receipt_all_seven_original_bodies(self):
        now = dt.datetime(2026, 10, 6, 11, tzinfo=NOW.tzinfo)
        for case in DELIVERY_SCOPE_CASES.values():
            with self.subTest(case=case['id']):
                self.assertEqual(hashlib.sha256(case['body'].encode()).hexdigest(), case['full_body_sha256'])
                candidate = classify(case, now)
                with patch.object(radar.base, 'kst_now', return_value=now):
                    selected = radar.quality_display_alerts([candidate], 30) if candidate else []
                self.assertEqual(bool(selected), case['expected_keep'])
                if selected:
                    self.assertFalse(radar.source_core_fact_errors(selected[0]))
                    self.assertTrue(radar.core_sentence_is_complete(selected[0]['telegram_core_fact']))

    def test_model_delivery_is_one_event_across_publishers_and_runs(self):
        first = self.delivery_scope_alert('cockpit_delivery_newsis')
        second = self.delivery_scope_alert('cockpit_delivery_etoday')
        identity = materiality.source_event_identity(first)
        self.assertTrue(identity.startswith('source_event:v2:commercial_delivery:'))
        self.assertEqual(identity, materiality.source_event_identity(second))
        now = dt.datetime(2026, 10, 6, 11, tzinfo=NOW.tzinfo)
        with patch.object(radar.base, 'kst_now', return_value=now):
            selected = radar.quality_display_alerts([first, second], 30)
        self.assertEqual(len(selected), 1)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
            telegram.record_seen_alerts([first], now)
            fresh, skipped = telegram.filter_previously_seen_alerts([second], now, 'live')
        self.assertFalse(fresh)
        self.assertEqual(len(skipped), 1)

    def test_changed_model_customer_product_or_date_is_new_delivery(self):
        first = self.delivery_scope_alert('cockpit_delivery_newsis')
        identity = materiality.source_event_identity(first)
        for old, new in (('르노그룹', 'OTHER그룹'), ('뉴 트래픽 이테크 일렉트릭', '다른 신차 모델'),
                         ('통합 콕핏 솔루션', '차량 통신 솔루션')):
            changed = {**first, 'source_title': first['source_title'].replace(old, new),
                       'source_body': first['source_body'].replace(old, new)}
            self.assertNotEqual(identity, materiality.source_event_identity(changed))
        changed = {**first, 'source_body': first['source_body'].replace('6일 밝혔다', '7일 밝혔다'),
                   'published': '2026-10-07T10:00+09:00'}
        self.assertNotEqual(identity, materiality.source_event_identity(changed))

    def test_marketing_contract_retains_new_period_maximum_and_forecast(self):
        item = self.delivery_scope_alert('marketing_contract_new_maximum_volume')
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('이녹스리튬', '트라피구라', '2029년', '마케팅 계약', '최대 3만톤', '전망된다'):
            self.assertIn(value, core)
        self.assertNotIn('700톤', core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        for old, new in (('2029년', '2030년'), ('3만톤', '5만톤'), ('전망된다', '확정됐다')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace(old, new)}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_marketing_contract_is_derived_from_changed_source_not_template(self):
        item = self.delivery_scope_alert('marketing_contract_new_maximum_volume')
        body = item['source_body'].replace('이녹스리튬', 'OTHER리튬').replace('트라피구라', 'OTHER무역').replace('2029년', '2031년').replace('3만톤', '4만톤')
        title = item['source_title'].replace('이녹스리튬', 'OTHER리튬').replace('2029년', '2031년')
        core = radar.source_headline_event_fact(title, body)
        for value in ('OTHER리튬', 'OTHER무역', '2031년', '4만톤'):
            self.assertIn(value, core)
        self.assertNotIn('트라피구라', core)

    def test_airline_summary_preserves_effective_day_routes_and_frequencies(self):
        item = self.delivery_scope_alert('airline_winter_frequency')
        core = radar.verified_alert_core(item, item['source_title'])
        for value in ('제주항공', '25일부터', '부산∼상하이', '주 4회에서 매일', '인천∼칭다오', '주 7회에서 11회', '인천∼웨이하이', '주 7회에서 10회'):
            self.assertIn(value, core)
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': core.replace('25일부터', '26일부터')}))
        self.assertTrue(radar.source_core_fact_errors(item))

    def test_local_delivery_gates_preserve_quantified_orders_and_new_flows(self):
        self.assertTrue(eligible('보안기업, 대학에 100억원 보안 솔루션 공급 계약 체결',
                                 '보안기업은 대학에 100억원 규모의 보안 솔루션을 공급하는 계약을 체결했다고 6일 공시했다.'))
        self.assertTrue(eligible('기계기업, 중고 건설장비 100대 수출 계약 체결',
                                 '기계기업은 베트남 기업과 중고 건설장비 100대 공급 계약을 200억원에 체결했다고 6일 밝혔다.'))
        self.assertTrue(eligible('주간 ETF 자금 순유입 3000억원',
                                 'ETF체크는 지난주 국내 ETF 자금 순유입이 3000억원으로 전주 대비 40% 증가했다고 6일 발표했다.'))

    def test_airline_network_focus_does_not_override_primary_earnings_or_contract(self):
        self.assertEqual(materiality.focus_kind('제주항공, 노선 확대에 3분기 영업이익 300억원'), 'earnings')
        self.assertEqual(materiality.focus_kind('항공기업, 노선 확대 위한 공급 계약 체결'), 'commercial_order')
        self.assertNotEqual(materiality.focus_kind('항공기업, 국제 노선 운항 중단'), 'aviation_network')

    def test_current_quantified_etf_turnover_declines_remain_eligible(self):
        self.assertTrue(eligible('삼성전자·SK하이닉스 레버리지 ETF 거래대금 91% 급감',
                                 '삼성전자와 SK하이닉스 레버리지 ETF 거래대금이 한 달 만에 91% 급감했다고 거래소가 6일 발표했다.'))
        self.assertTrue(eligible('단일종목 레버리지 ETF 거래대금 19조원에서 5000억원',
                                 '단일종목 레버리지 ETF 규제 후 거래대금이 19조원에서 5000억원으로 줄었습니다.'))

    def test_hardware_purchase_requires_quantified_commitment_not_wishlist(self):
        self.assertTrue(eligible('아마존, 엔비디아 GPU 200만개 추가 확보 결정',
                                 'AWS는 AI 수요 대응을 위해 엔비디아 GPU 200만개를 추가 확보하기로 했습니다.'))
        self.assertFalse(eligible('아마존, GPU 확보 필요성 제기',
                                  'AWS는 AI 수요 대응을 위해 GPU 200만개를 확보해야 한다는 의견이 나왔습니다.'))
        self.assertFalse(eligible('기업, GPU 구매 검토',
                                  '기업은 GPU를 추가 구매하기로 했습니다.'))

    def test_foundry_share_and_memory_customer_adoption_are_not_device_catalogs(self):
        self.assertTrue(eligible('TSMC 파운드리 점유율 73%·삼성전자 7%',
                                 '2분기 파운드리 점유율은 TSMC 73%, 삼성전자 7%로 격차가 확대됐습니다.'))
        self.assertTrue(eligible('CXMT LPDDR6 양산·샤오미 스마트폰 첫 탑재',
                                 'CXMT가 LPDDR6을 양산해 샤오미 스마트폰에 처음 탑재했습니다.'))

    def test_thin_discovery_templates_cannot_bypass_verified_source_guard(self):
        import verify_gamejoa_cross_market_coverage_contract as coverage
        groups = (coverage.ATTACHMENT_20260827_ALERT_CASES,
                  coverage.ATTACHMENT_20260827_EVENING_ALERT_CASES,
                  coverage.ATTACHMENT_20260827_30_ALERT_CASES)
        tested = set()
        for cases in groups:
            for title, body, kind, _required, *_publisher in cases:
                if kind not in coverage.SOURCE_EVIDENCE_REQUIRED_CASES:
                    continue
                row = coverage.source_row(title, body, publisher=_publisher[0] if _publisher else 'contract fixture')
                item = radar.build_attachment_verified_event_alert(row, NOW, f'{title} {body}'.lower())
                self.assertIsNotNone(item, kind)
                self.assertEqual(radar.verified_alert_core(item, title), '', kind)
                self.assertTrue(radar.source_core_fact_errors(item), kind)
                tested.add(kind)
        self.assertEqual(tested, coverage.SOURCE_EVIDENCE_REQUIRED_CASES)

    def test_same_run_copies_are_selected_once(self):
        first = classify({"title": "AMD·삼성전자, AI 반도체 공급 계약 체결", "body": CONTRACT_BODY, "published": NOW.isoformat(), "url": "https://www.etnews.com/20261005009901"})
        second = copy.deepcopy(first)
        second.update(news="삼성·AMD, 반도체 공동개발 계약", source_title="삼성·AMD, 반도체 공동개발 계약", original_news="삼성·AMD, 반도체 공동개발 계약", link="https://www.mk.co.kr/news/business/9999001", publisher="매일경제")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts([first, second], 30)
        self.assertEqual(len(selected), 1)

    def test_identical_verified_core_blocks_distinct_body_fingerprints(self):
        first = alert()
        second = {**first, "source_body": CONTRACT_BODY + ADDITIONAL_FACT,
                  "source_abstract": CONTRACT_BODY + ADDITIONAL_FACT,
                  "link": "https://www.mk.co.kr/news/business/9999002", "publisher": "매일경제"}
        self.assertNotEqual(materiality.verified_source_body_digest(first),
                            materiality.verified_source_body_digest(second))
        self.assertIn("core:", " ".join(telegram.alert_seen_keys(first)))
        self.assertEqual(len(generated_guard.duplicate_event_errors([first, second], radar)), 1)
        with tempfile.TemporaryDirectory() as folder, patch.object(telegram, 'SEEN_PATH', Path(folder) / 'seen.json'):
            telegram.record_seen_alerts([first], NOW)
            fresh, skipped = telegram.filter_previously_seen_alerts([second], NOW + dt.timedelta(minutes=5), 'live')
        self.assertFalse(fresh)
        self.assertEqual(len(skipped), 1)

    def test_core_receipt_migration_needs_original_seen_body_digest(self):
        proof = json.loads(telegram.VERIFIED_CORE_RECEIPTS_PATH.read_text(encoding='utf-8'))['entries'][0]
        seen = {
            'link': proof['link'], 'title': proof['source_title'],
            'first_seen_kst': '2026-10-07T07:39:19+09:00',
            'source_body_digest': proof['source_body_digest'],
            'lanes': {'live': '2026-10-07T07:39:19+09:00'},
        }
        key = 'core:' + telegram.digest_seen(telegram.base.norm(proof['telegram_core_fact']))
        for original, expected in ((seen, True), ({**seen, 'source_body_digest': '0' * 64}, False),
                                   ({**seen, 'first_seen_kst': '2026-10-06T07:39:19+09:00'}, False)):
            with self.subTest(expected=expected, original=original):
                state = {'seen': {'link:original': dict(original)}}
                telegram.migrate_seen_verified_core_receipts(state)
                self.assertEqual(key in state['seen'], expected)
                if expected:
                    self.assertEqual(state['seen'][key]['core_alias_evidence_message_id'], proof['message_id'])

    def test_opinion_is_not_a_new_market_action(self):
        title = '경영권 인수 넘어 성장자본으로…PEF 순기능 살려야 [김앤장 금융·핀테크·가상자산 인사이트]'
        body = 'PEF는 기업 성장에 기여할 수 있다. 2021년 제도 변화로 성장자본의 역할이 확대됐다.'
        self.assertEqual(materiality.assess(title, body)['reason'], 'professional_opinion_without_new_market_action')
        current_action = '삼성전자는 7일 반도체 장비업체와 100억원 규모의 공급 계약을 체결했다고 공시했다.'
        self.assertNotEqual(materiality.assess('반도체 투자 필요 [칼럼]', current_action)['reason'],
                            'professional_opinion_without_new_market_action')

    def test_ceo_appointment_does_not_become_generic_strategy_summary(self):
        title = "'알렉사 주역' 보스턴다이나믹스 지휘한다 …현대차 피지컬 AI 속도"
        body = ('현대차그룹 산하 보스턴다이나믹스가 아마존의 인공지능(AI) 사업을 이끌어온 '
                '로히트 프라사드를 신임 최고경영자(CEO)로 영입했다. '
                '현대차그룹 제조 현장에 로봇을 적용할 것으로 기대된다.')
        fact = radar.source_headline_event_fact(title, body)
        self.assertIn('로히트 프라사드', fact)
        self.assertIn('신임 CEO로 영입했다', fact)
        candidate = alert(title=title, body=body)
        candidate['telegram_core_fact'] = '현대차그룹 제조 현장에 AI를 도입하는 전략이 중요하다.'
        self.assertIn('headline_actor_population_period_or_standard_mismatch',
                      radar.source_core_fact_errors(candidate))

    def test_foreign_local_indicator_and_household_aid_need_korean_equity_channel(self):
        india = '인도 9월 서비스업 PMI 55.2·1.1P↑'
        pmi_body = '인도 서비스업 구매관리자지수는 9월 55.2를 기록해 전월 54.1에서 상승했다.'
        pakistan = '파키스탄, 저소득층 900만여명에 연료보조금 지급'
        aid_body = '파키스탄 정부는 지난달 저소득층 900만명에게 연료보조금 지급을 승인했다.'
        for title, body in ((india, pmi_body), (pakistan, aid_body)):
            with self.subTest(title=title):
                self.assertEqual(materiality.assess(title, body)['reason'],
                                 'foreign_local_measure_without_korean_equity_channel')
        linked = pmi_body + ' 한국 자동차 부품 수출 주문이 이 지표에 맞춰 증가했다고 발표했다.'
        self.assertNotEqual(materiality.assess(india, linked)['reason'],
                            'foreign_local_measure_without_korean_equity_channel')

    def test_regional_pilot_without_funding_or_orders_is_not_equity_news(self):
        title = '인천시, 글로벌캠퍼스에 피지컬 AI 실증센터 구축'
        bare = '인천시는 AI 실증센터를 구축한다고 밝혔다. 내년 4월까지 시설을 조성할 계획이다.'
        funded = bare + ' 인천시는 관련 인프라 구축을 위해 120억원 규모 사업을 발주했다고 밝혔다.'
        self.assertEqual(materiality.assess(title, bare)['reason'],
                         'regional_pilot_facility_without_material_commitment')
        self.assertNotEqual(materiality.assess(title, funded)['reason'],
                            'regional_pilot_facility_without_material_commitment')

    def test_repaired_market_cores_keep_current_supply_capacity_and_broker_basis(self):
        housing = '국토장관, 연내 신규택지 7.3만 가구 발표'
        housing_body = ('홍지선 국토교통부 장관이 수도권 주택 공급 확대를 위해 공공택지 착공 물량을 '
                        '16만 가구 이상 확충하고 연내 7만3000가구+α 규모의 신규택지 입지를 추가 발표하겠다고 밝혔다.')
        housing_core = radar.source_headline_event_fact(housing, housing_body)
        self.assertIn('7만3000가구+α', housing_core)
        self.assertIn('16만 가구', housing_core)
        self.assertIn('8만2000가구', radar.source_headline_event_fact(
            housing, housing_body.replace('7만3000가구', '8만2000가구')))
        lithium = '포스코홀딩스, 아르헨티나 리튬 2공장 준공'
        lithium_body = ('포스코홀딩스가 아르헨티나 염수리튬 2공장 상공정을 준공했다. '
                        '2공장 상공정은 연간 2만3000톤의 탄산리튬 생산능력을 갖췄다. '
                        '기존 1공장을 포함해 총 4만8000톤까지 상업생산 능력을 확대했다.')
        lithium_core = radar.source_headline_event_fact(lithium, lithium_body)
        for token in ('준공했다', '2만3000톤', '4만8000톤'):
            self.assertIn(token, lithium_core)
        self.assertIn('3만1000톤', radar.source_headline_event_fact(
            lithium, lithium_body.replace('2만3000톤', '3만1000톤')))
        broker = '하나證 “효성중공업, 고마진 매출 이연으로 3분기 실적 하회”'
        broker_body = ('하나증권이 7일 효성중공업(298040)에 대해 고마진 물량의 매출 인식 이연으로 '
                       '단기 실적이 기대치를 하회할 것으로 전망했다. '
                       '유 연구원은 효성중공업의 3분기 매출액이 전년 대비 11.6% 증가한 1조3000억원으로 전망했다. '
                       '영업이익은 전년 대비 34.7% 증가한 2961억원으로 전망했다.')
        broker_core = radar.source_headline_event_fact(broker, broker_body)
        for token in ('하나증권', '매출 인식 이연', '1조3000억원', '2961억원'):
            self.assertIn(token, broker_core)
        self.assertIn('3100억원', radar.source_headline_event_fact(
            broker, broker_body.replace('2961억원', '3100억원')))

    def test_media_award_and_multi_issuer_roundup_are_not_new_orders(self):
        award_title = '한화, AI 에너지 관리 기술 미국 차세대 신기술 선정'
        award_body = ('한화 자회사의 AI 에너지 관리 기술이 미국 경제·경영 혁신 전문 매체 '
                      '패스트 컴퍼니의 차세대 신기술에 선정됐다고 7일 밝혔다.')
        self.assertEqual(materiality.assess(award_title, award_body)['reason'],
                         'media_recognition_without_new_commercial_action')
        funded_award = award_body + ' 한화는 프라임그룹과 150억원 규모 공급 계약을 체결했다고 7일 밝혔다.'
        self.assertNotEqual(materiality.assess(award_title, funded_award)['reason'],
                            'media_recognition_without_new_commercial_action')
        roundup_title = '반도체·전력기기 3종목 목표가 모음 [株토피아]'
        roundup_body = ('오늘 오전 주요 증권사 리포트를 정리해드립니다. '
                        'A증권은 SK하이닉스 목표주가를 유지했다. B증권은 효성중공업 목표주가를 유지했다.')
        self.assertEqual(materiality.assess(roundup_title, roundup_body)['reason'],
                         'multi_issuer_analyst_roundup_without_single_event')
        standalone = '하나증권은 효성중공업 영업이익 전망치를 3000억원으로 상향했다고 밝혔다.'
        self.assertNotEqual(materiality.assess('효성중공업, 이익 전망 상향', standalone)['reason'],
                            'multi_issuer_analyst_roundup_without_single_event')

    def test_delivery_contract_and_foreign_allocation_cores_track_source_values(self):
        delivery_title = '삼미금속, 가스터빈 블레이드 납품 개시'
        delivery_body = ('삼미금속(012210)이 지난해 한화파워(구 PSM)로부터 수주한 '
                         '가스터빈용 블레이드 제품의 본격적인 공급을 시작했다고 7일 밝혔다.')
        delivery_core = radar.source_headline_event_fact(delivery_title, delivery_body)
        self.assertIn('한화파워', delivery_core)
        self.assertIn('본격 공급을 시작', delivery_core)
        self.assertIn('다른파워', radar.source_headline_event_fact(
            delivery_title, delivery_body.replace('한화파워', '다른파워')))
        contract_title = '한성크린텍, 삼성전기 베트남 공장 230억원 초순수 E&P 계약 체결'
        contract_body = ('한성크린텍은 삼성이앤에이와 230억원 규모의 삼성전기 베트남 공장 '
                         '초순수 처리 시스템 설계·조달(E&P) 계약을 체결했다고 밝혔다. '
                         '계약기간은 2027년 6월 30일까지다.')
        contract_core = radar.source_headline_event_fact(contract_title, contract_body)
        for value in ('삼성이앤에이', '삼성전기', '230억원', '2027년 6월 30일'):
            self.assertIn(value, contract_core)
        self.assertIn('250억원', radar.source_headline_event_fact(
            contract_title, contract_body.replace('230억원', '250억원')))
        allocation_title = '블룸버그 AI 투자처는 대만...코스피 위험'
        allocation_body = ('블룸버그에 따르면 대만 자취엔지수는 지난 분기 코스피 수익률을 약 23%포인트 웃돌았다. '
                           '지난달 펀드매니저 87명을 대상으로 실시된 BofA 조사에서 이들 중 40%가 '
                           '대만 주식 비중을 확대하고 있다고 답한 반면, 한국 주식의 경우 25%에 불과했다.')
        allocation_core = radar.source_headline_event_fact(allocation_title, allocation_body)
        for value in ('23%포인트', '40%', '25%'):
            self.assertIn(value, allocation_core)
        self.assertIn('30%포인트', radar.source_headline_event_fact(
            allocation_title, allocation_body.replace('23%포인트', '30%포인트')))

    def test_reported_oil_shipments_are_not_replaced_by_diplomatic_quote(self):
        title = '우크라 "한국이 러시아에 석유 공급" 저격'
        body = ('우크라이나 대통령실 제재정 담당 보좌관은 한국의 제재 정책과 극명한 대조를 이룬다고 비판했다. '
                '가디언은 항만 기록과 선박 추적 데이터를 분석한 결과 지난 7~8월 한국 항구에서 '
                '총 17만 6000t이 넘는 석유제품을 싣고 러시아로 운송했다고 보도했다.')
        core = radar.source_headline_event_fact(title, body)
        self.assertIn('17만 6000t', core)
        self.assertIn('7~8월', core)
        self.assertIn('가디언', core)
        self.assertIn('20만 1000t', radar.source_headline_event_fact(
            title, body.replace('17만 6000t', '20만 1000t')))

    def test_regional_output_enforcement_and_small_foreign_brand_sales_are_not_equity_alerts(self):
        regional = '8월 대구 제조업 생산 4.8% 증가·경북 3.2% 감소…수출 동반 증가'
        regional_body = '한국은행 대구경북본부는 8월 대구 제조업 생산이 증가했고 경북은 감소했다고 밝혔다.'
        self.assertEqual(materiality.assess(regional, regional_body)['reason'],
                         'regional_production_without_listed_issuer_change')
        enforcement = '건설현장 불법하도급 연말까지 집중단속…공공현장 275곳 점검'
        enforcement_body = '국토교통부는 기존 불법하도급 의심 공공현장 275곳을 점검한다고 밝혔다.'
        self.assertEqual(materiality.assess(enforcement, enforcement_body)['reason'],
                         'routine_enforcement_without_named_issuer_or_new_penalty')
        brand = '폴스타, 9월 역대 최대 판매…연간 목표 달성 성큼'
        brand_body = '폴스타코리아는 한국수입자동차협회 기준 국내 9월 신규 등록대수가 769대라고 밝혔다.'
        self.assertEqual(materiality.assess(brand, brand_body)['reason'],
                         'foreign_brand_local_sales_without_market_wide_effect')
        global_sales = brand_body + ' 글로벌 분기 판매량과 매출도 전년 대비 늘었다.'
        self.assertNotEqual(materiality.assess(brand, global_sales)['reason'],
                            'foreign_brand_local_sales_without_market_wide_effect')

    def test_earnings_fdi_and_unconfirmed_partnership_follow_source_not_sector_templates(self):
        lg_title = 'LG전자, 3분기 누적 매출 70조·영업익 4조 첫 돌파'
        lg_body = ('LG전자는 2026년 3분기 연결기준 매출액 23조8270억원, 영업이익 7818억원의 잠정실적을 '
                   '기록했다고 7일 밝혔다. 올해 1~3분기 누적 매출액은 71조3807억원으로 증가했다. '
                   '누적 영업이익은 4조346억원으로 늘었다. 시장 전망치인 매출 24조2150억원, '
                   '영업이익 1조301억원을 밑돌았다.')
        lg_core = radar.source_headline_event_fact(lg_title, lg_body)
        self.assertIn('7818억원', lg_core)
        self.assertIn('시장 전망치', lg_core)
        self.assertIn('4조346억원', lg_core)
        self.assertIn('8000억원', radar.source_headline_event_fact(
            lg_title, lg_body.replace('7818억원', '8000억원')))
        fdi_title = '3분기 外人투자 도착 148.7억弗 전년比 30.6% 증가'
        fdi_body = ('산업통상부는 3분기 누계 외국인 직접투자(신고기준)이 전년동기대비 10.8% 증가한 '
                    '229억 달러를 기록했다고 밝혔다. 자금 도착은 30.6% 증가한 148억7000만 달러를 기록했다. '
                    '정보통신 분야 신고액은 24억3000만 달러다.')
        fdi_core = radar.source_headline_event_fact(fdi_title, fdi_body)
        for token in ('자금 도착액', '148억7000만 달러', '신고액', '229억 달러'):
            self.assertIn(token, fdi_core)
        self.assertNotIn('24억3000만', fdi_core)
        self.assertIn('160억7000만', radar.source_headline_event_fact(
            fdi_title, fdi_body.replace('148억7000만', '160억7000만')))
        partnership_title = '애플·LG전자, AI 스마트홈 기기 공동 개발…도어락 출시 추진'
        partnership_body = ('블룸버그통신에 따르면 애플과 LG전자는 스마트 도어락 등 스마트홈 기기를 '
                            '공동 개발 중이다. LG전자는 FCC에 제품 인증을 신청했다. '
                            '다만 인증 문서에는 애플과의 협력 사실이 명시되지 않았다.')
        partnership_core = radar.source_headline_event_fact(partnership_title, partnership_body)
        self.assertIn('소식통', partnership_core)
        self.assertIn('명시되지 않았다', partnership_core)
        self.assertFalse(radar.source_headline_event_fact(
            partnership_title, partnership_body.replace('명시되지 않았다', '명시됐다')))


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
              "reported_event_articles": len(REPORTED_CASES), "decision_focus_run_id": DECISION_FIXTURE["run_id"],
              "decision_focus_articles": len(DECISION_CASES), "event_equivalence_run_id": EQUIVALENCE_FIXTURE["run_id"],
              "event_equivalence_articles": len(EQUIVALENCE_CASES), "market_noise_run_id": NOISE_FIXTURE["run_id"],
              "market_noise_articles": len(NOISE_CASES)}
    output["broker_report_articles"] = len(BROKER_CASES)
    output["final_runtime_run_id"] = FINAL_RUNTIME_FIXTURE["run_id"]
    output["final_runtime_articles"] = len(FINAL_RUNTIME_CASES)
    path = ROOT / "out/gamejoa_incremental_news_verification.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not result.wasSuccessful():
        raise SystemExit(1)
    print(f"gamejoa_incremental_news_quality=passed tests={result.testsRun} cases=10 external_delivery=false")

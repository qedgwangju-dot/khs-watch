#!/usr/bin/env python3
"""Regression checks for fair retrieval, source isolation and same-run reuse."""

from __future__ import annotations

import copy
import datetime as dt
import html
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

import gamejoa_article_detail_queue as queue
import khs_source_fetch as source_fetch
import gamejoa_preopen_news_radar_full_compact_runner as radar
from khs_article_detail import ArticleHTMLParser, extract_article_detail


NOW = dt.datetime(2026, 10, 1, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))


def article(index: int, published=NOW) -> dict:
    return {
        "title": f"기업{index} 신규 공급계약 체결", "link": f"https://www.etnews.com/20261001{index:05d}",
        "source": "전자신문", "publisher": "전자신문", "published": published, "layer": "trusted",
    }


def fixture(title: str, body: str) -> str:
    return f'<meta property="og:title" content="{html.escape(title, quote=True)}"><article itemprop="articleBody">{body}</article>'


class DetailQueueChecks(unittest.TestCase):
    def test_scoped_market_changes_outrank_isolated_corporate_actions(self):
        assess = radar.market_materiality.assess
        policy = assess('FCC, 중국산 데이터센터 장비 수입 제한 검토',
                        'FCC는 중국산 데이터센터 장비의 수입 제한안을 검토 중이라고 소식통이 전했다.')
        capex = assess('메모리기업, 반도체 설비투자 2배 확대',
                       '메모리기업은 반도체 생산능력 확대를 위해 설비투자를 2배 늘려 250억 달러를 투입할 계획이라고 발표했다.')
        company = assess('통신기업, 현금·주식 피인수 계약',
                         '통신기업은 인수 계약을 체결하고 거래 종결 시 주당 현금 4.925달러를 받는다고 발표했다.')
        for result in (policy, capex, company):
            self.assertEqual(result['disposition'], 'keep', result)
        self.assertGreater(policy['transmission_scope_rank'], capex['transmission_scope_rank'])
        self.assertGreater(capex['transmission_scope_rank'], company['transmission_scope_rank'])
        praise = assess('반도체기업, 미래 혁신 비전', '반도체기업은 미래 혁신 비전을 공유하며 협력을 강화하기로 했다.')
        self.assertNotEqual(praise['disposition'], 'keep', praise)

    def test_photo_caption_cannot_supply_an_unrelated_corporate_event(self):
        title = '스타벅스, 中신장 첫 진출…美의원·인권단체 "즉각 매장 닫아라"'
        caption = ('[보스턴=AP/뉴시스] 스타벅스가 일본 법인 지분 매각을 두고 예비 협의를 진행했다. '
                   '사진은 보스턴의 한 매장 외부에 스타벅스 로고가 걸려 있는 모습. 2026.06.11.')
        current = ('미국 커피 체인 스타벅스가 중국 신장위구르자치구에 처음으로 매장을 열자 미국 정치권과 '
                   '위구르 인권단체에서 매장을 폐쇄하라는 요구가 나왔다. '
                   '스타벅스는 지난달 29일 우루무치에 매장 2곳을 열고 신장 시장에 처음 진출했다. '
                   '미 하원 의원은 성명을 내고 매장 폐쇄를 요구했다. 회사는 요구에 대해 별도의 입장을 내놓지 않았다.')
        source = fixture(title, '<div class="article_photo"><p id="caption_NISI20260611">' + caption + '</p></div><p>' + current + '</p>')
        detail = extract_article_detail(source, title)
        self.assertTrue(detail['body_verified'], detail)
        self.assertIn('우루무치', detail['body'])
        self.assertNotIn('일본 법인', detail['body'])
        self.assertNotIn('일본 법인', radar.article_summary_body(caption + current))
        core = radar.detailed_article_core(title, detail['body'])
        self.assertNotIn('일본', core)
        self.assertNotIn('지분 매각', core)

    def test_actual_share_consolidation_core_keeps_ratio_proposal_and_vote_date(self):
        title = '가드포스 AI, 40대1 액면병합 추진…복수의결권 도입도'
        body = ('가드포스 AI(GFAI)가 기존 보통주 40주를 1주로 합치는 액면병합과 복수의결권 구조 도입 '
                '등 3개 안건을 임시주주총회에 상정한다고 10월 2일 발표했다.\n'
                '임시주총은 홍콩 시간 기준 10월 27일 오전 11시에 열린다.\n'
                '일부 투자자와 애널리스트가 액면병합을 부정적으로 인식하고, 병합 후 주가가 병합 전 수준으로 '
                '되돌아간 사례가 있으며, 발행주식 수 감소로 유동성이 떨어질 수 있다는 점이다.')
        wrong = radar.market_materiality.source_sentences(body)[-1]
        self.assertFalse(radar.market_materiality.core_focus_aligned(title, wrong))
        core = radar.detailed_article_core(title, body)
        for term in ('가드포스 AI', '40대1', '복수의결권', '10월 27일', '상정한다'):
            self.assertIn(term, core)
        self.assertNotIn('시행했다', core)
        self.assertNotIn('일부 투자자', core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_actual_preliminary_revenue_core_is_total_not_a_segment(self):
        title = '루안윈 에다이 테크놀로지, 상반기 잠정매출 930만~950만달러..전년비 25배'
        body = ('루안윈 에다이 테크놀로지(RYET)가 9월 30일 종료된 2027 회계연도 상반기(6개월) 잠정 미감사 '
                '매출액이 약 930만~950만 달러(약 6300만~6450만 위안)로 전년 동기 약 37만 달러(260만 위안) '
                '대비 약 25배에 이를 것으로 예상된다고 2일 발표했다.\n'
                '이 부문 매출은 약 500만~520만 달러(3400만~3550만 위안)로 전체의 약 53~56%를 차지할 전망이다.\n'
                '매출 인식, 기간 귀속, 환율 환산 등 기말 조정에 따라 최종 수치는 크게 달라질 수 있다.')
        core = radar.detailed_article_core(title, body)
        for term in ('루안윈', '2027회계연도 상반기', '잠정 미감사', '930만~950만 달러', '예상했다', '약 25배'):
            self.assertIn(term, core)
        self.assertNotIn('500만', core)
        self.assertFalse(radar.core_sentence_is_complete('이 부문 매출은 500만 달러로 예상된다.'))
        audit = radar.market_materiality.assess(title, body)
        self.assertNotIn('rates_fx_or_macro', [item['kind'] for item in audit['evidence']])
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_service_comparison_and_unchanged_dividend_are_not_new_high_impact_events(self):
        title = '국내 3사 자율주행 서비스 비교해보니'
        body = '지난 3월에는 AI 서비스 기업 NCS와 자율주행 물류 사업 공동 수주를 위한 업무협약을 체결했다.'
        audit = radar.market_materiality.assess(title, body)
        self.assertLess(audit['priority'], 2, audit)
        self.assertFalse(radar.market_materiality.evidence_is_new_event('commercial_order', body))
        current = 'A2Z는 UAE 기업과 100억원 규모 자율주행 차량 공급 계약을 체결했다고 발표했다.'
        self.assertEqual(radar.market_materiality.assess('A2Z, 100억원 공급 계약 체결', current)['disposition'], 'keep')
        unchanged = radar.market_materiality.assess('펜넷파크, 10월 배당 주당 0.08달러 유지',
                                                  '펜넷파크는 월간 배당금을 0.08달러로 확정하고 11월 2일 지급한다고 발표했다.')
        self.assertLess(unchanged['priority'], 2, unchanged)
        cut = radar.market_materiality.assess('금융기업, 배당 50% 삭감', '금융기업은 분기 배당금을 50% 삭감한다고 발표했다.')
        self.assertEqual(cut['disposition'], 'keep', cut)

    def test_office_photo_in_lead_cannot_exclude_actual_shareholder_change(self):
        title = '두둑해진 곳간에 주주환원 관심…반도체기업 자사주 소각'
        body = '반도체기업 본사 전경.\n반도체기업은 40조원 규모 자기주식을 취득하고 전량 소각한다고 발표했다.'
        audit = radar.market_materiality.assess(title, body)
        self.assertEqual(audit['disposition'], 'keep', audit)
        self.assertNotEqual(audit['reason'], 'office_publicity_without_business_economics')

    def test_connective_debt_core_is_rebuilt_as_the_actual_debt_repayment(self):
        title = '하이페리온 디파이, 부채 전액 상환·자사주 매입 시작에 주목'
        body = ('아브뉴 캐피털 대출 약 860만 달러를 전액 상환해 잔여 장기 부채가 없어지면서 이자 부담이 줄었습니다. '
                '여기에 가중평균 3.21달러로 자사주 24만 주를 매입하며 주주환원 의지도 보였습니다.')
        self.assertEqual(radar.market_materiality.focus_kind(title), 'debt_repayment')
        self.assertFalse(radar.core_sentence_is_complete('여기에 자사주 24만 주를 매입했습니다.'))
        core = radar.detailed_article_core(title, body)
        self.assertIn('860만', core)
        self.assertIn('전액 상환', core)
        self.assertNotIn('여기에', core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_actual_convertible_article_summarizes_issue_not_unrelated_consensus(self):
        title = "스노우플레이크, 35억달러 전환사채 발행 추진..2027년물 환매"
        event = (
            "스노우플레이크(SNOW)가 2029년 만기 13억 달러, 2031년 만기 22억 달러 등 총 35억 달러 규모의 "
            "이표율 0.00% 전환 선순위 채권(Convertible Senior Notes)을 사모 방식으로 발행하고, 조달 자금 일부로 "
            "기존 2027년 만기 전환사채를 환매할 계획이라고 2일(현지시간) 발표했다."
        )
        wrong = "증권가 컨센서스에 따르면 스노우플레이크의 2027 회계연도 매출액은 약 63억1700만 달러로 전년 대비 34.86% 증가할 것으로 예상된다."
        body = "무이자 전환사채라 이자 부담은 없고 캡드콜로 희석도 일부 막아요.\n" + event + "\n" + wrong
        item = {"news": title, "source_title": title, "source_body": body, "source_abstract": body,
                "body_verified": True, "korean_business_news": True, "telegram_core_fact": wrong,
                "link": "https://stock.mk.co.kr/news/view/1169333"}
        self.assertEqual(radar.market_materiality.focus_kind(title), "financing")
        self.assertIn("headline_event_or_period_mismatch", radar.source_core_fact_errors(item))
        self.assertFalse(radar.source_output_aligned(item))
        core = radar.verified_alert_core(item, title)
        for term in ("스노우플레이크", "35억 달러", "무이자", "추진", "2027년물", "환매할 계획"):
            self.assertIn(term, core)
        self.assertNotIn("63억", core)
        self.assertNotIn("34.86%", core)
        self.assertNotIn("발행했다", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertTrue(radar.source_output_aligned({**item, "telegram_core_fact": core}), core)
        conversion = radar.build_alert_fx_conversion(
            {**item, "telegram_core_fact": core},
            {"rates": {"USD": {"value": 1348.28, "status": "fixture", "source": "unit test"}}}, NOW,
        )
        converted = radar.compact_converted_core(core, conversion)
        self.assertIn("35억 달러(약 5조원)", converted)
        self.assertIn("2027년물", converted)
        self.assertTrue(radar.core_sentence_is_complete(converted), converted)

    def test_actual_cash_and_stock_acquisition_keeps_terms_and_closing_condition(self):
        title = "상고마 테크놀러지스, BRC그룹 피인수 계약..주당 현금 4.925달러+주식"
        body = (
            "현금과 주식을 함께 받는 인수 계약이라 거래가 마무리되면 주주가 일정 수준의 현금 가치를 확보할 수 있어요.\n"
            "상고마 테크놀러지스(SANG)가 미국 델라웨어주 법인 BRC 그룹 홀딩스에 인수되는 "
            "계획합병(Arrangement Agreement) 계약을 체결했으며, 주주는 보통주 1주당 현금 4.925달러와 "
            "BRC 그룹 홀딩스 보통주 0.04767주를 받게 된다고 10월 2일 발표했다.\n"
            "증권가 컨센서스에 따르면 상고마의 2027년 매출액은 2억652만 달러로 전년 대비 46.64% 증가할 전망이다."
        )
        core = radar.detailed_article_core(title, body)
        for term in ("상고마", "BRC 그룹 홀딩스", "인수 계약", "거래 종결 시", "4.925달러", "0.04767주"):
            self.assertIn(term, core)
        self.assertNotIn("46.64%", core)
        self.assertNotIn("확보할 수 있어요", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        item = {"news": title, "source_title": title, "source_body": body, "body_verified": True,
                "korean_business_news": True, "telegram_core_fact": core,
                "link": "https://www.mk.co.kr/news/stock/12167629"}
        self.assertTrue(radar.source_output_aligned(item), radar.source_core_fact_errors(item))

    def test_equity_compensation_beats_company_profile_and_uses_actual_estimate(self):
        title = "아이큐엠 퀀텀 컴퓨터스, 전직원 주식보상 도입..최대 2600만 유로"
        event = (
            "아이큐엠 퀀텀 컴퓨터스(IQMX)는 이사회가 전 직원을 대상으로 한 성과연동주식보상제(PSP 2026~2032)와 "
            "양도제한조건부주식(RSU) 풀(2026~2030)을 신규 도입하기로 결의했으며, 두 제도의 추정 총가치는 "
            "약 2570만 유로(PSP 약 1820만 유로, RSU 약 750만 유로)라고 9월 30일(현지시간) 발표했다."
        )
        profile = "아이큐엠 퀀텀 컴퓨터스는 초전도 방식 양자컴퓨팅 분야의 글로벌 기업으로, 기업·연구기관 등에 양자 시스템을 공급한다."
        body = event + "\n" + profile
        self.assertEqual(radar.market_materiality.focus_kind(title), "equity_compensation")
        audit = radar.market_materiality.assess(title, body)
        self.assertEqual(audit["priority"], 2, audit)
        self.assertEqual([row["kind"] for row in audit["evidence"]], ["equity_compensation_change"])
        core = radar.detailed_article_core(title, body)
        for term in ("전 직원", "도입을 결의", "추정 총가치", "약 2570만 유로"):
            self.assertIn(term, core)
        self.assertNotIn("2600만", core)
        self.assertNotIn("시스템을 공급", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        item = {"news": title, "source_title": title, "source_body": body, "body_verified": True,
                "korean_business_news": True, "telegram_core_fact": profile,
                "link": "https://stock.mk.co.kr/news/view/1169291"}
        self.assertIn("company_profile_not_news_core", radar.source_core_fact_errors(item))
        self.assertFalse(radar.source_output_aligned(item))
        self.assertTrue(radar.source_output_aligned({**item, "telegram_core_fact": core}), core)

    def test_generic_company_service_profile_is_not_a_new_supply_or_technology_event(self):
        title = "양자기업, 초전도 컴퓨팅 사업 소개"
        body = "양자기업은 초전도 방식 양자컴퓨팅 분야의 글로벌 기업으로, 연구기관과 국립연구소 등에 양자 시스템을 공급한다."
        audit = radar.market_materiality.assess(title, body)
        self.assertEqual(audit["evidence"], [], audit)
        self.assertNotEqual(audit["disposition"], "keep", audit)
        self.assertFalse(radar.market_materiality.evidence_is_new_event("customer_supply_start", body))

    def test_actual_mosquito_laser_curiosity_does_not_borrow_production_delay(self):
        title = "모기 보이면 '레이저 발사'...中서 나온 134만원짜리 기계"
        body = ("모기를 감지해 레이저로 제거하는 기기가 중국에서 개발돼 이달 출시를 앞두고 있다. "
                "대량 생산이 지연된 데다 레이저 제품의 안전성을 둘러싼 우려도 제기됐기 때문이다.")
        audit = radar.market_materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "exclude", audit)
        self.assertEqual(audit["reason"], "consumer_curiosity_without_market_business_link")
        real = radar.market_materiality.assess("상장사, 모기 퇴치 센서 공급계약 체결",
                                              "상장사는 병원 고객과 500억원 모기 퇴치 센서 공급계약을 체결했다.")
        self.assertEqual(real["disposition"], "keep", real)

    def test_headings_reference_notes_and_conditional_analysis_are_not_new_deals(self):
        for sentence in (
            "■ 경쟁 인수 제한과 자금 조달",
            "해당 수치는 이번 인수 계약에 따른 변동이 반영되지 않았을 수 있다.",
            "현금과 주식을 함께 받는 인수 계약이라 거래가 마무리되면 주주가 현금 가치를 확보할 수 있어요.",
        ):
            with self.subTest(sentence=sentence):
                audit = radar.market_materiality.assess("기업, 인수 계약 발표", sentence)
                self.assertEqual(audit["evidence"], [], audit)
        self.assertFalse(radar.market_materiality.evidence_is_new_event(
            "capital_or_shareholder_action", "일반 운영자금에는 향후 자사주 매입과 기술 인수가 포함될 수 있다.",
        ))

    def test_inference_acquisition_keeps_named_issuer_and_source_expected_cost_effect(self):
        title = "네비우스, 인퍼라이즈 인수로 AI 추론 스택 확장 나서"
        body = ("추론 최적화 기업 인퍼라이즈를 인수한다고 발표했습니다. "
                "인퍼라이즈의 콜드 스타트 단축 기술로 유휴 GPU 비용을 줄이고 가동률을 높일 수 있을 것으로 기대됩니다.")
        core = radar.detailed_article_core(title, body)
        self.assertIn("네비우스는", core)
        self.assertIn("인퍼라이즈 인수를 발표", core)
        self.assertIn("GPU 비용", core)
        self.assertIn("기대", core)
        self.assertNotIn("인수했다", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_convertible_term_definition_is_not_an_approved_conversion(self):
        sentence = "무이자 전환사채라 이자 부담은 없고 캡드콜로 희석도 일부 막아요."
        self.assertFalse(radar.market_materiality.evidence_is_new_event("convertible_ownership_rights", sentence))
        self.assertTrue(radar.market_materiality.evidence_is_new_event("convertible_ownership_rights",
                                                                     "이사회는 전환사채 전환을 승인했다."))

    def test_foreign_flow_core_uses_observed_amount_not_generic_outlook_or_other_actor(self):
        title = "9월에 20조 팔아치운 외국인, 10월엔 돌아올까"
        body = (
            "10월에는 실적 발표와 미국 장기금리, 환율 등이 외국인 귀환 여부를 가를 변수로 거론된다. "
            "개인은 9월 국내 증시에서 10조원을 순매수했다. "
            "2일 한국거래소에 따르면 지난 9월 외국인은 유가증권시장에서 20조3722억원어치를 순매도했다. "
            "외국인은 10월에 5조원을 순매수할 것으로 예상된다."
        )
        core = radar.detailed_article_core(title, body)
        self.assertIn("20조3722억원", core)
        self.assertIn("9월 외국인", core)
        self.assertIn("순매도했다", core)
        self.assertNotIn("10조원", core)
        self.assertNotIn("5조원", core)
        self.assertNotIn("변수", core)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_verified_nonmaterial_recheck_is_metadata_only_and_rearmed_by_changes(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1, selection_version=40)
        queue.record_attempt(state, row, NOW, verified=True, selection_version=40,
                             source_disposition="exclude", source_reason="consumer_review_not_industry_change")
        entry = state["entries"][queue.article_key(row)]
        self.assertEqual(queue.parse_time(entry["retry_after_kst"]), NOW + dt.timedelta(hours=6))
        selected, _, stats = queue.plan_details([row], state, NOW + dt.timedelta(hours=1), 1, selection_version=40)
        self.assertFalse(selected)
        self.assertEqual(stats["nonmaterial_recheck"], 1)
        self.assertTrue(queue.plan_details([row], state, NOW + dt.timedelta(hours=6), 1, selection_version=40)[0])
        self.assertTrue(queue.plan_details([row], state, NOW + dt.timedelta(seconds=1), 1, selection_version=41)[0])
        changed = {**row, "title": "기업1, 신규 공급계약 금액 1000억원", "published": NOW + dt.timedelta(minutes=1)}
        self.assertTrue(queue.plan_details([changed], state, NOW + dt.timedelta(minutes=1), 1, selection_version=40)[0])
        encoded = json.dumps(state)
        self.assertNotIn("source_body", encoded)
        self.assertNotIn('"seen"', encoded)
        queue.record_attempt(state, row, NOW + dt.timedelta(hours=6), verified=False, error="HTTP 502", selection_version=40)
        self.assertEqual(entry["source_selection_disposition"], "")
        self.assertEqual(queue.parse_time(entry["retry_after_kst"]), NOW + dt.timedelta(hours=6, minutes=5))

    def test_collector_records_nonmaterial_recheck_only_after_verified_source_body(self):
        row = {**article(1), "title": "휴대폰 카메라 써보니, 찍는 맛 [리뷰]"}
        body = "새 휴대폰 카메라를 직접 사용해 촬영 사진과 사용감을 살펴봤다. 구도와 화질에 대한 개인 평가다. " * 5
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live", "GITHUB_RUN_ID": "source-exclusion-test"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "kst_now", return_value=NOW), \
                patch.object(radar.base, "fetch", return_value=(fixture(row["title"], body), None)):
            radar.hydrate_korean_business_details([row], NOW)
            entry = queue.load_state(queue.PENDING_PATH)["entries"][queue.article_key(row)]
            self.assertEqual(entry["verification_status"], "verified")
            self.assertEqual(entry["source_selection_disposition"], "exclude")
            self.assertEqual(entry["source_selection_reason"], "consumer_review_not_industry_change")
            self.assertEqual(queue.parse_time(entry["retry_after_kst"]), NOW + dt.timedelta(hours=6))
            self.assertNotIn("source_body", entry)

    def test_hidden_menu_optional_end_tags_do_not_swallow_following_article(self):
        title = "외국인, 9월 코스피 주식 20조원 순매도"
        body = "외국인은 9월 코스피 시장에서 20조3722억원을 순매도했다. 삼성전자와 SK하이닉스 매도가 집중됐다. " * 5
        source = (
            f'<meta property="og:title" content="{title}">'
            '<aside style="display:none"><ul><li>숨긴 추천기사<li><svg><path></path></svg>다른 추천기사</ul></aside>'
            f'<div class="news_cnt_detail_wrap" itemprop="articleBody"><p>{body}</p></div>'
            '<div class="recommendation">다른 기사 자사주 매수</div>'
        )
        detail = extract_article_detail(source, title)
        self.assertTrue(detail["body_verified"])
        self.assertIn("20조3722억원", detail["body"])
        for noise in ("추천기사", "자사주 매수"):
            self.assertNotIn(noise, detail["body"])
        self.assertFalse(extract_article_detail(source, "기업, 신제품 출시와 신규 생산라인 가동")["body_verified"])

    def test_mk_stock_article_region_recovers_body_and_original_kst_publication(self):
        title = "미국 9월 고용, 예상치 크게 밑돌아"
        body = "미국 9월 비농업 고용은 2만9000명 증가하며 예상치에 못 미쳤다. 실업률은 4.2%로 상승했다. " * 5
        source = (
            f'<meta property="og:title" content="{title}">'
            '<div class="time_info mt-500"><span>입력&nbsp;:&nbsp;2026.10.02 22:50:34</span></div>'
            f'<section id="news_body"><div class="news_detail_wrap"><p>{body}</p></div></section>'
            '<section><p>다른 기사 제목과 주가 정보</p></section>'
        )
        detail = extract_article_detail(source, title)
        self.assertTrue(detail["body_verified"])
        self.assertEqual(detail["published_kst"], "2026-10-02T22:50:34+09:00")
        self.assertNotIn("다른 기사", detail["body"])
        self.assertNotIn("입력", detail["body"])

    def test_listing_search_photo_and_spoofed_publisher_urls_do_not_take_fetch_budget(self):
        bad_links = (
            "https://www.etoday.co.kr/search/?keyword=삼성전자",
            "https://www.fnnews.com/section/002001000",
            "https://www.kmib.co.kr/article/listing.asp?sid1=chr&page=11",
            "https://www.newsis.com/view/NISI20261002_0002100000",
            "https://www.newsis.com/view.html?id=NISI20261002_0002100000",
            "https://attacker.invalid/path/mk.co.kr/news/stock/12167168",
            "https://mk.co.kr.attacker.invalid/news/stock/12167168",
        )
        for link in bad_links:
            self.assertTrue(radar.korean_business_article_url_rejection(link), link)
        for link in (
            "https://www.etoday.co.kr/news/view/2631400",
            "https://www.fnnews.com/news/202610011945430660",
            "https://www.kmib.co.kr/article/view.asp?arcid=9000001517&cp=nv",
            "https://www.newsis.com/view/NISX20261002_0003787706",
            "https://stock.mk.co.kr/news/view/1169273",
        ):
            self.assertFalse(radar.korean_business_article_url_rejection(link), link)
        rows = [{**article(index), "link": link} for index, link in enumerate(bad_links)]
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "fetch") as fetch:
            notes = radar.hydrate_korean_business_details(rows, NOW)
            fetch.assert_not_called()
            self.assertIn("invalid_url_skipped=7", notes[-1])

    def test_invalid_edaily_mobile_host_maps_same_id_but_still_requires_body_alignment(self):
        original = "https://m.coinlab.edaily.co.kr/News/Read?newsId=06573126645608984&mediaCodeNo=257"
        canonical = "https://www.edaily.co.kr/News/Read?newsId=06573126645608984&mediaCodeNo=257"
        self.assertEqual(radar.canonical_korean_business_article_url(original), canonical)
        for link in (
            "https://marketin.edaily.co.kr/News/Read?newsId=04372246645608984",
            "https://m.coinlab.edaily.co.kr/News/Read?newsId=invalid",
            "https://m.coinlab.edaily.co.kr.attacker.invalid/News/Read?newsId=06573126645608984",
        ):
            self.assertEqual(radar.canonical_korean_business_article_url(link), link)
        row = {**article(1), "link": original, "publisher": "이데일리"}
        body = "미국의 9월 신규 고용이 예상치를 크게 밑돌았고 실업률은 상승했다. 미국 국채금리가 하락했다. " * 5
        page = fixture("미국 9월 고용 쇼크", body)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live", "GITHUB_RUN_ID": "canonical-test"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "fetch", return_value=(page, None)) as fetch:
            radar.hydrate_korean_business_details([row], NOW)
            self.assertEqual(fetch.call_args.args[0], canonical)
            self.assertEqual(row["link"], canonical)
            self.assertEqual(row["source_discovery_url"], original)
            self.assertFalse(row.get("body_verified"))
            self.assertIn("title/body mismatch", row["_article_verification_failed"])
            self.assertIn("mismatch", fetch.call_args.kwargs["response_validator"](page))

    def test_backlog_carries_metadata_not_body_and_preserves_failure_cooldown(self):
        row = article(0)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1, selection_version=37)
        queue.record_attempt(state, row, NOW, verified=False, error="timeout", selection_version=37)
        resumed = queue.backlog_rows(state, NOW + dt.timedelta(seconds=1), set(), 24)
        self.assertEqual(len(resumed), 1)
        self.assertEqual(queue.fingerprint(resumed[0]), queue.fingerprint(row))
        self.assertNotIn("source_body", resumed[0])
        self.assertNotIn("body_verified", resumed[0])
        selected, _, stats = queue.plan_details(resumed, state, NOW + dt.timedelta(seconds=1), 1, selection_version=38)
        self.assertFalse(selected)
        self.assertEqual(stats["cooling"], 1)
        self.assertFalse(queue.backlog_rows(state, NOW, {row['link']}, 24))
        self.assertFalse(queue.backlog_rows(state, NOW + dt.timedelta(hours=25), set(), 24))

    def test_feed_evicted_article_is_freshly_verified_without_forcing_or_reusing_prior_body(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1)
        queue.record_attempt(state, row, NOW, verified=True)
        body = "<p>기업은 신규 공급계약을 체결하고 생산시설을 확대한다고 발표했다. 계약금액은 1000억원이다.</p>" * 5
        page = '<meta property="article:published_time" content="' + NOW.isoformat() + '">' + fixture(row['title'], body)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live", "GITHUB_RUN_ID": "backlog-test"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "kst_now", return_value=NOW + dt.timedelta(seconds=1)), \
                patch.object(radar.base, "fetch", return_value=(page, None)) as fetch:
            queue.save_json(queue.STATE_PATH, state)
            rows = []
            notes = radar.hydrate_korean_business_details(rows, NOW + dt.timedelta(seconds=1))
            fetch.assert_called_once()
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]['body_verified'])
            self.assertEqual(rows[0]['published'], NOW)
            self.assertIn('backlog_resumed=1', notes[-1])
            with patch.object(radar.telegram, 'load_seen_state', return_value={"seen": {"a": {"link": row['link'], "last_seen_kst": NOW.isoformat()}}}):
                sent_rows = []
                radar.hydrate_korean_business_details(sent_rows, NOW + dt.timedelta(seconds=2))
            self.assertFalse(sent_rows)
            self.assertEqual(fetch.call_count, 1)

    def test_legacy_backlog_without_publication_time_cannot_send_or_reset_transport_backoff(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1)
        queue.record_attempt(state, row, NOW, verified=False, error='timeout')
        state['entries'][queue.article_key(row)].pop('published_kst')
        resumed = queue.backlog_rows(state, NOW + dt.timedelta(seconds=1), set(), 24)
        self.assertIsNone(resumed[0]['published'])
        self.assertEqual(queue.fingerprint(resumed[0]), queue.fingerprint(row))
        self.assertFalse(queue.plan_details(resumed, state, NOW + dt.timedelta(seconds=1), 1)[0])
        body = "<p>기업은 신규 공급계약을 체결했다고 밝혔다. 공급 품목은 전력기기이며 계약금액은 1000억원이다.</p>" * 5
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live", "GITHUB_RUN_ID": "undated-backlog-test"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "kst_now", return_value=NOW + dt.timedelta(minutes=6)), \
                patch.object(radar.base, "fetch", return_value=(fixture(row['title'], body), None)):
            queue.save_json(queue.STATE_PATH, state)
            rows = []
            radar.hydrate_korean_business_details(rows, NOW + dt.timedelta(minutes=6))
            self.assertFalse(rows[0].get('body_verified'))
            self.assertIsNone(rows[0]['published'])
            self.assertIn('publication time unavailable', rows[0]['_article_verification_failed'])
            candidate = radar.contract.strict.classify(rows[0], NOW + dt.timedelta(minutes=6))
            self.assertFalse(radar.quality_display_alerts([candidate] if candidate else [], 1))

    def test_changed_selection_rules_refresh_verified_metadata_once_without_reusing_body(self):
        row = article(0)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1, selection_version=36)
        queue.record_attempt(state, row, NOW, verified=True, selection_version=36)
        selected, state, stats = queue.plan_details(
            [row], state, NOW + dt.timedelta(seconds=1), 1, selection_version=37,
        )
        self.assertEqual(selected, [row])
        self.assertEqual(stats["selection_refresh"], 1)
        self.assertNotIn("source_body", json.dumps(state))
        self.assertNotIn('"seen"', json.dumps(state))
        queue.record_attempt(state, row, NOW + dt.timedelta(seconds=1), verified=True, selection_version=37)
        selected, _, stats = queue.plan_details(
            [row], state, NOW + dt.timedelta(seconds=2), 1, selection_version=37,
        )
        self.assertFalse(selected)
        self.assertEqual(stats["selection_refresh"], 0)
        self.assertEqual(stats["cooling"], 1)

    def test_changed_selection_rules_do_not_bypass_transport_failure_backoff(self):
        row = article(0)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1, selection_version=36)
        queue.record_attempt(state, row, NOW, verified=False, error="HTTP 502", selection_version=36)
        selected, _, stats = queue.plan_details(
            [row], state, NOW + dt.timedelta(seconds=1), 1, selection_version=37,
        )
        self.assertFalse(selected)
        self.assertEqual(stats["selection_refresh"], 0)
        self.assertEqual(stats["cooling"], 1)

    def test_new_rules_fetch_fresh_body_in_real_collector_instead_of_using_verified_history(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1)
        queue.record_attempt(
            state, row, NOW, verified=True, selection_version=radar.market_materiality.VERSION - 1,
        )
        body = "<p>기업은 신규 공급계약을 체결하고 생산시설을 확대한다고 발표했다. 계약금액은 1000억원이다.</p>" * 5
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live", "GITHUB_RUN_ID": "new-selection-test"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "kst_now", return_value=NOW + dt.timedelta(seconds=1)), \
                patch.object(radar.base, "fetch", return_value=(fixture(row["title"], body), None)) as fetch:
            queue.save_json(queue.STATE_PATH, state)
            notes = radar.hydrate_korean_business_details([row], NOW + dt.timedelta(seconds=1))
            fetch.assert_called_once()
            self.assertTrue(row["body_verified"])
            self.assertIn("1000억원", row["source_body"])
            refreshed = queue.load_state(queue.PENDING_PATH)["entries"][queue.article_key(row)]
            self.assertEqual(refreshed["selection_validation_version"], radar.market_materiality.VERSION)
            self.assertNotIn("source_body", refreshed)
            diagnostic = radar.telegram.selection_diagnostics([], notes, [], [], [], [], True)
            self.assertEqual(diagnostic["detail_queue"]["selection_refresh"], 1)

    def test_old_http_only_validation_failure_is_rechecked_once(self):
        row = article(0)
        selected, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 1)
        queue.record_attempt(state, row, NOW, verified=False, error="title/body mismatch aligned=None body_chars=0")
        entry = state["entries"][queue.article_key(row)]
        entry.pop("response_validation_version")
        selected, state, _ = queue.plan_details([row], state, NOW + dt.timedelta(seconds=1), 1)
        self.assertEqual(selected, [row])
        queue.record_attempt(state, row, NOW + dt.timedelta(seconds=1), verified=False, error="title/body mismatch aligned=None body_chars=0")
        selected, _, stats = queue.plan_details([row], state, NOW + dt.timedelta(seconds=2), 1)
        self.assertFalse(selected)
        self.assertEqual(stats["cooling"], 1)

    def test_fair_progress_despite_continuous_urgent_candidates_and_failures(self):
        original = [article(index) for index in range(200)]
        state = {"entries": {}}
        attempted = set()
        for run in range(20):
            now = NOW + dt.timedelta(minutes=6 * run)
            urgent = [article(1000 + run * 10 + index, now) for index in range(10)]
            selected, state, stats = queue.plan_details(urgent + copy.deepcopy(original), state, now, 20)
            self.assertEqual(stats["fair_slots"], 10)
            for row in selected:
                attempted.add(row["link"])
                queue.record_attempt(state, row, now, verified=False, error="timeout")
        self.assertTrue({row["link"] for row in original} <= attempted)
        self.assertNotIn("source_body", json.dumps(state))
        self.assertNotIn('"seen"', json.dumps(state))

    def test_cooldown_backoff_changed_headline_and_preopen_bypass(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 12)
        for attempt, minutes in enumerate((5, 15, 60, 120)):
            now = NOW + dt.timedelta(hours=attempt * 3)
            queue.record_attempt(state, row, now, verified=False, error="HTTP 502")
            self.assertEqual(queue.parse_time(state["entries"][queue.article_key(row)]["retry_after_kst"]), now + dt.timedelta(minutes=minutes))
        during = now + dt.timedelta(minutes=1)
        selected, _, stats = queue.plan_details([row], state, during, 12)
        self.assertFalse(selected)
        self.assertEqual(stats["cooling"], 1)
        selected, _, _ = queue.plan_details([row], state, during, 12, respect_cooldown=False)
        self.assertEqual(selected, [row])
        updated = {**row, "title": "기업1 공급계약 금액 확대", "published": during}
        selected, changed, _ = queue.plan_details([updated], state, during, 12)
        self.assertEqual(selected, [updated])
        self.assertEqual(changed["entries"][queue.article_key(updated)]["attempts"], 0)

    def test_merge_keeps_attempt_when_only_discovery_is_newer(self):
        row = article(1)
        _, state, _ = queue.plan_details([row], {"entries": {}}, NOW, 12)
        discovered = copy.deepcopy(state)
        queue.record_attempt(state, row, NOW, verified=True)
        discovered["entries"][queue.article_key(row)]["last_discovered_kst"] = (NOW + dt.timedelta(minutes=2)).isoformat()
        merged = queue.merge_state(discovered, state, NOW + dt.timedelta(minutes=2))
        self.assertEqual(merged["entries"][queue.article_key(row)]["attempts"], 1)
        self.assertEqual(merged["entries"][queue.article_key(row)]["verification_status"], "verified")
        self.assertEqual(merged["entries"][queue.article_key(row)]["last_discovered_kst"], discovered["entries"][queue.article_key(row)]["last_discovered_kst"])
        later = copy.deepcopy(merged)
        queue.record_attempt(later, row, NOW + dt.timedelta(minutes=3), verified=False, error="later failure")
        self.assertEqual(queue.merge_state(state, later, NOW)["entries"][queue.article_key(row)]["last_error"], "later failure")

    def test_cache_never_crosses_run_date_fingerprint_or_age(self):
        row = article(1)
        receipt = {"fingerprint": queue.fingerprint(row), "query_time_kst": NOW.isoformat(), "detail": {"body": "current primary text"}, "error": ""}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_RUN_ID": "run-a"}):
            path = Path(folder) / "cache.json"
            queue.save_json(path, {"run_id": "run-a", "receipts": {queue.article_key(row): receipt}})
            cache = queue.load_run_cache(NOW + dt.timedelta(minutes=3), path)
            self.assertIsNotNone(queue.cached_receipt(cache, row))
            self.assertIsNone(queue.cached_receipt(cache, {**row, "title": "changed"}))
            self.assertIsNone(queue.cached_receipt(cache, {**row, "published": NOW + dt.timedelta(seconds=1)}))
            self.assertFalse(queue.load_run_cache(NOW + dt.timedelta(minutes=16), path)["receipts"])
            self.assertFalse(queue.load_run_cache(NOW - dt.timedelta(minutes=1), path)["receipts"])
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "run-b"}):
                self.assertFalse(queue.load_run_cache(NOW, path)["receipts"])
            with patch.dict(os.environ, {"GITHUB_RUN_ID": ""}):
                self.assertFalse(queue.load_run_cache(NOW, path)["receipts"])

    def test_preflight_reuse_and_new_run_rotation_in_real_collector(self):
        rows = [article(index) for index in range(12)]
        body = "<p>회사는 생산시설 확충을 위한 신규 공급계약을 체결했다고 공시했다. 계약 기간은 2027년까지이며 공급 품목은 전력기기다.</p>" * 4
        pages = {row["link"]: '<meta property="og:description" content="unrelated recommendation preview">' + fixture(row["title"], body) for row in rows}
        calls = []

        def fetch(url, timeout, *, response_validator=None):
            calls.append(url)
            self.assertIsNotNone(response_validator)
            self.assertIsNone(response_validator(pages[url]))
            return pages[url], None

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run", "RADAR_RUN_MODE": "live"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar, "KOREAN_BUSINESS_DETAIL_LIMIT", 4), \
                patch.object(radar.telegram, "load_seen_state", return_value={"seen": {}}), \
                patch.object(radar.base, "kst_now", return_value=NOW), patch.object(radar.base, "fetch", side_effect=fetch):
            preflight = copy.deepcopy(rows)
            radar.hydrate_korean_business_details(preflight, NOW)
            first_urls = set(calls)
            self.assertEqual(len(calls), 4)
            send_rows = copy.deepcopy(rows)
            notes = radar.hydrate_korean_business_details(send_rows, NOW + dt.timedelta(minutes=1))
            self.assertEqual(len(calls), 4)
            self.assertIn("cache_hits=4", notes[-1])
            verified = [row for row in send_rows if row.get("body_verified")]
            self.assertTrue(all(row["article_query_time_kst"] == NOW.isoformat(timespec="seconds") for row in verified))
            self.assertTrue(all("unrelated recommendation" not in row["source_abstract"] for row in verified))
            state = queue.load_state(queue.PENDING_PATH)
            self.assertTrue(all(entry["attempts"] == 1 for entry in state["entries"].values() if entry.get("last_attempt_kst")))
            queue.save_json(queue.STATE_PATH, state)
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "next-run"}), patch.object(radar.base, "kst_now", return_value=NOW + dt.timedelta(minutes=6)):
                notes = radar.hydrate_korean_business_details(copy.deepcopy(rows), NOW + dt.timedelta(minutes=6))
            self.assertEqual(len(calls), 8)
            self.assertFalse(first_urls & set(calls[4:]))
            self.assertIn("cache_hits=0", notes[-1])
            diagnostic = radar.telegram.selection_diagnostics([], notes, [], [], [], [], True)
            self.assertEqual(diagnostic["detail_queue"]["source_fetches"], 4)
            self.assertTrue(diagnostic["coverage_incomplete"])

    def test_recently_sent_does_not_hide_updated_article_or_preopen_digest(self):
        original = article(1, NOW - dt.timedelta(minutes=30))
        seen = {"seen": {"a": {"link": original["link"], "title": original["title"], "last_seen_kst": (NOW - dt.timedelta(minutes=5)).isoformat()}}}
        body = "<p>공급계약은 장비 생산 확대와 관련되어 있다. 해당 회사는 신규 공장의 가동을 준비하며 자금 조달을 마쳤다고 설명했다.</p>" * 5
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"RADAR_RUN_MODE": "live", "GITHUB_RUN_ID": "recent-test"}), \
                patch.object(queue, "STATE_PATH", Path(folder) / "state.json"), \
                patch.object(queue, "PENDING_PATH", Path(folder) / "pending.json"), \
                patch.object(queue, "CACHE_PATH", Path(folder) / "cache.json"), \
                patch.object(radar.telegram, "load_seen_state", return_value=seen), \
                patch.object(radar.base, "kst_now", return_value=NOW), \
                patch.object(radar.base, "fetch", return_value=(fixture(original["title"], body), None)) as fetch:
            same = copy.deepcopy(original)
            radar.hydrate_korean_business_details([same], NOW)
            fetch.assert_not_called()
            self.assertEqual(same["_detail_skipped_reason"], "recently_delivered_unchanged_title")
            with patch.dict(os.environ, {"RADAR_RUN_MODE": "preopen"}):
                digest = copy.deepcopy(original)
                radar.hydrate_korean_business_details([digest], NOW)
                self.assertTrue(digest["body_verified"])
            updated = {**original, "published": NOW}
            radar.hydrate_korean_business_details([updated], NOW)
            self.assertTrue(updated["body_verified"])
            self.assertEqual(fetch.call_count, 2)


class SourceIsolationChecks(unittest.TestCase):
    def test_article_validation_requests_html_not_feed_content(self):
        validator = lambda text: None
        with patch.object(radar.base, "fetch_text", return_value=("body", None)) as fetch:
            radar.base.fetch("https://www.hankyung.com/article/fixture", response_validator=validator)
            self.assertEqual(fetch.call_args.kwargs["accept"], "text/html,application/xhtml+xml,*/*")
            self.assertIs(fetch.call_args.kwargs["response_validator"], validator)
            radar.base.fetch("https://source.example/rss")
            self.assertIn("application/rss+xml", fetch.call_args.kwargs["accept"])
            self.assertIsNone(fetch.call_args.kwargs["response_validator"])

    def test_fast_invalid_proxy_does_not_hide_valid_direct_article(self):
        import time
        title = "한국 수출 증가 발표"
        body = "한국 수출이 전년 대비 증가했다. 정부는 수출액과 주요 산업별 실적을 발표했으며 반도체와 자동차 수출이 늘었다. " * 6
        good = fixture(title, body)
        bad = '<meta property="og:title" content="한국 수출 증가 발표"><div>본문 없는 동의 화면</div>'

        def direct(*args):
            time.sleep(0.03)
            return good, None

        def validate(text):
            return None if extract_article_detail(text, title)["body_verified"] else "unverified article"

        with patch.object(source_fetch, "_fetch_proxy", return_value=(bad, None)), \
                patch.object(source_fetch, "_fetch_direct", side_effect=direct), \
                patch.dict(os.environ, {"KHS_SOURCE_PROXY_URL": "https://proxy.example/fetch", "KHS_SOURCE_PROXY_FIRST": "true"}):
            text, error = radar.base.fetch("https://www.hankyung.com/article/fixture", 1, response_validator=validate)
            self.assertIsNone(error)
            self.assertEqual(text, good)
            legacy, legacy_error = radar.base.fetch("https://www.hankyung.com/article/fixture", 1)
            self.assertIsNone(legacy_error)
            self.assertEqual(legacy, bad)

    def test_both_invalid_routes_stay_failed_with_both_reasons(self):
        with patch.object(source_fetch, "_fetch_proxy", return_value=("wrong title", None)), \
                patch.object(source_fetch, "_fetch_direct", return_value=("empty body", None)), \
                patch.dict(os.environ, {"KHS_SOURCE_PROXY_URL": "https://proxy.example/fetch", "KHS_SOURCE_PROXY_FIRST": "true"}):
            text, error = source_fetch.fetch_text(
                "https://www.hankyung.com/article/fixture", "test", timeout=1, attempts=1,
                response_validator=lambda text: text,
            )
            self.assertIsNone(text)
            self.assertIn("proxy race", error)
            self.assertIn("wrong title", error)
            self.assertIn("direct race", error)
            self.assertIn("empty body", error)

    def test_sequential_validation_uses_fallback_without_changing_defaults(self):
        with patch.object(source_fetch, "_fetch_direct", return_value=("empty body", None)), \
                patch.object(source_fetch, "_fetch_proxy", return_value=("verified body", None)), \
                patch.dict(os.environ, {"KHS_SOURCE_PROXY_URL": "https://proxy.example/fetch", "KHS_SOURCE_PROXY_FIRST": "false"}):
            text, error = source_fetch.fetch_text(
                "https://source.example/article", "test", timeout=1, attempts=1,
                response_validator=lambda text: None if text == "verified body" else "missing body",
            )
            self.assertIsNone(error)
            self.assertEqual(text, "verified body")
            text, error = source_fetch.fetch_text("https://source.example/article", "test", timeout=1, attempts=1)
            self.assertEqual(text, "empty body")
            self.assertIsNone(error)

    def test_explicit_body_beats_all_other_article_nodes(self):
        title = "기업 신규 공장 투자계획 발표"
        body = "<p>기업이 신규 공장 투자계획을 발표했다. 생산시설 확충을 통해 공급 능력을 늘리기로 했으며 공장 가동 일정은 내년이다.</p>" * 5
        page = '<article class="editor">편집자 소개</article>' + fixture(title, body)
        page += '<article class="thistime_news">엉뚱한 추천 뉴스와 스포츠 선거 소식</article>' * 30
        detail = extract_article_detail(page, title)
        self.assertTrue(detail["body_verified"])
        self.assertIn("공장 가동 일정", detail["body"])
        self.assertNotIn("추천 뉴스", detail["body"])
        self.assertNotIn("편집자 소개", detail["body"])

    def test_hidden_stock_popup_and_sidebar_are_not_source_facts(self):
        title = "코스피 장중 상승 전환"
        paragraph = '<p>코스피는 오후 12시 현재 상승했다. <a>삼성전자<span class="lay_feature" style="display:none;"><span>주가 팝업 관련뉴스: 중국 기업 인수</span></span></a>와 다른 종목도 올랐다.</p>'
        page = fixture(title, paragraph * 6 + '<aside><p>사이드바에서 추천하는 반도체 매각 소식</p></aside>')
        detail = extract_article_detail(page, title)
        self.assertTrue(detail["body_verified"])
        self.assertIn("삼성전자", detail["body"])
        for contaminant in ("중국 기업 인수", "매각 소식", "주가 팝업"):
            self.assertNotIn(contaminant, detail["body"])

    def test_json_ld_is_joined_per_script_and_selected_by_identity(self):
        title = "기업 신규 공급계약 체결"
        wrong = {"@type": "NewsArticle", "headline": "스포츠 선거 당선", "articleBody": "다른 기사 내용 " * 100}
        right = {"@type": "NewsArticle", "headline": title, "articleBody": "실제 공급계약과 생산계획이 공시됐다. " * 20}
        source = f'<meta property="og:title" content="{title}"><script type="application/ld+json">{json.dumps(wrong)}</script><script type="application/ld+json">{json.dumps(right)}</script>'
        parser = ArticleHTMLParser()
        for start in range(0, len(source), 7):
            parser.feed(source[start:start + 7])
        parser.close()
        self.assertEqual(len(parser.json_ld_parts), 2)
        detail = extract_article_detail(source, title)
        self.assertTrue(detail["body_verified"])
        self.assertIn("실제 공급계약", detail["body"])
        self.assertNotIn("다른 기사", detail["body"])

    def test_sports_election_and_ceremonial_photo_not_corporate_events(self):
        for title in ("제4대 대한당구연맹 회장 선거, 강진모 후보 당선", "이더커넥트2026, 폐회사 하는 이종재 이투데이 대표 [포토]"):
            self.assertTrue(radar.is_nonmarket_business_event({"title": title}))
        for title in (
            "최태원 회장, SK하이닉스 주식 3620주 매수", "회장, 자사주 매수 발표 [포토]",
            "기업 투자협약 기념촬영 [포토]", "기업 CEO 신규 공급계약 체결",
            "폭염에 변압기 과부하로 서울 아파트 정전", "美 관세 정책 발표",
        ):
            self.assertFalse(radar.is_nonmarket_business_event({"title": title}))

    def test_intraday_snapshot_is_not_presented_as_after_close_update(self):
        snapshot = {"source_title": "코스피, 모든 주체 매도세에도 소폭 상승세 전환", "published": (NOW.replace(hour=12)).isoformat(), "source_abstract": "오후 12시 현재 코스피는 상승했다."}
        with patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            self.assertTrue(radar.is_stale_intraday_market_report(snapshot, NOW))
            self.assertFalse(radar.is_stale_intraday_market_report(snapshot, NOW.replace(hour=13)))
            self.assertFalse(radar.is_stale_intraday_market_report({**snapshot, "source_title": "코스피 상승 마감"}, NOW))
            self.assertFalse(radar.is_stale_intraday_market_report({**snapshot, "source_title": "코스피, 정책 수혜에 내일 반등 기대"}, NOW))
        with patch.dict(os.environ, {"RADAR_RUN_MODE": "preopen"}):
            self.assertFalse(radar.is_stale_intraday_market_report(snapshot, NOW))

    def test_generated_sector_is_not_a_source_market_event(self):
        cases = (
            ("오아시스, 90년대 미공개 녹음본 28억 경매에 법적 대응…출품 취소",
             "영국 밴드 오아시스는 미공개 녹음 테이프 경매에 법적 대응했다. 음원 지식재산권(IP)은 밴드가 보유하고 있다."),
            ('프락시스 CEO "서울 모처에 디지털국가 대사관 짓겠다"',
             "프락시스 CEO는 서울에 공동체 공간을 만들겠다고 말했다. 과거 펀드로부터 투자를 받았으며 정부와의 협약은 없는 단계다."),
        )
        for title, body in cases:
            alert = {
                "source_title": title, "source_abstract": body, "source_body": body,
                "korean_business_news": True, "body_verified": True,
                "sectors": ["AI/데이터센터"], "policy_plain_summary": "반도체 실적과 수급을 바꿉니다.",
            }
            self.assertFalse(radar.stock_market_channels(alert))
            self.assertFalse(radar.has_stock_market_link(alert), title)
            self.assertFalse(radar.quality_display_alerts([alert], 1), title)

    def test_source_market_event_keeps_broad_industries_and_private_investment(self):
        cases = (
            ("스타트업, 800억원 투자 유치", "국내 바이오 스타트업이 연구개발을 위해 800억원 투자를 유치했다고 밝혔다."),
            ("지자체, 앵커기업 투자보조금 조례 제정", "시는 기업의 생산시설 투자를 유치하기 위한 조례를 제정했다."),
            ("자동차 부품사, 해외 공장 법인 설립", "자동차 부품사는 현지 생산과 고객 지원을 위한 신규 법인을 설립했다."),
            ("양식장 폭염에 물고기 집단 폐사", "고수온으로 양식장의 생산 피해가 늘며 수산물 공급 차질이 우려된다."),
            ("제약사, 신약 임상 3상 승인", "제약사는 임상 3상 시험을 승인받았으며 의약품 상용화를 추진한다."),
            ("최태원 회장, SK하이닉스 주식 3620주 매수", "최태원 회장은 SK하이닉스 주식을 장내 매수했다고 공시했다."),
            ("해운사 파업에 항만 공급 차질", "해운사 노동자 파업으로 항만 운송과 공급 차질이 확대됐다."),
            ("전력장비 업체, AI 냉각 신제품 출시", "전력장비 업체는 데이터센터 고객에게 공급할 냉각 제품을 출시했다."),
        )
        for title, body in cases:
            alert = {"source_title": title, "source_body": body, "korean_business_news": True, "body_verified": True}
            self.assertTrue(radar.has_stock_market_link(alert), title)

    def test_photo_credit_and_obfuscated_email_are_not_core_facts(self):
        title = "기업, 신규 공장 투자계획 발표"
        body = (
            "[서울=뉴시스] 기업 공장. (사진 = 기업 제공) [email protected] *재판매 및 DB 금지 "
            "[촬영 박수현] (서울=연합뉴스) 박수현 기자 = "
            "2026.10.1 willow@yna.co.kr 기업은 신규 공장에 1000억원을 투자한다고 발표했다."
        )
        core = radar.detailed_article_core(title, body)
        self.assertIn("1000억원", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        for garbage in ("email protected", "촬영", "DB 금지", "@", "2026.10.1"):
            self.assertNotIn(garbage, core)
        self.assertTrue(radar.core_has_ui_garbage("[email protected] 기업이 투자한다고 밝혔다."))
        self.assertTrue(radar.core_has_ui_garbage("[촬영 박수현] 기업이 투자한다고 밝혔다."))
        self.assertTrue(radar.core_has_ui_garbage("willow@yna.co.kr 기업이 투자한다고 밝혔다."))

    def test_workflow_persists_attempts_separately_from_delivery(self):
        workflow = (queue.ROOT / ".github/workflows/gamejoa-preopen-news-radar.yml").read_text(encoding="utf-8")
        self.assertIn('GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT: "160"', workflow)
        self.assertIn('GAMEJOA_KOREAN_BUSINESS_DETAIL_WORKERS: "12"', workflow)
        self.assertIn("python scripts/verify_gamejoa_article_detail_queue.py", workflow)
        self.assertIn("Commit GAMEJOA article retrieval queue", workflow)
        self.assertIn("always() && github.event.inputs.telegram_dry_run != 'true'", workflow)
        self.assertIn("out/gamejoa_article_detail_queue_pending.json", workflow)
        self.assertIn("data/gamejoa_article_detail_queue.json", workflow)

    def test_probability_core_preserves_actual_market_action(self):
        title = "美 10월 금리동결 확률 상승, 예상 밑돈 물가"
        body = (
            "8월 PCE 물가가 전년 동월 대비 3.4% 올랐다. 다우존스의 전문가 예상치 3.7%를 밑돈 수치다. "
            "CME 페드워치에 따르면 시장은 연준이 오는 10월 기준금리를 동결할 가능성을 전날 49.1%에서 이날 65.1%로 올려 반영했다."
        )
        core = radar.detailed_article_core(title, body)
        for fact in ("10월 금리동결", "49.1%", "65.1%", "CME 페드워치"):
            self.assertIn(fact, core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertFalse(radar.policy_probability_article_fact(title, body.replace("페드워치", "일반 전망")))

    def test_company_statement_wins_over_context_only_background(self):
        title = "SK하이닉스, 솔리다임 자금조달 방식 미정"
        body = (
            "SK하이닉스가 솔리다임의 경쟁력을 강화할 여러 전략을 검토 중이라고 공식화했다. "
            "이 과정에서 솔리다임이 별도 상장될 경우 SK하이닉스 주주가치가 훼손될 수 있다는 우려가 나왔다. "
            "솔리다임의 자금조달 방식은 아직 결정되지 않았다."
        )
        core = radar.detailed_article_core(title, body)
        self.assertFalse(core.startswith("이 과정"))
        self.assertIn("솔리다임", core)
        self.assertTrue("검토" in core or "결정되지" in core)

    def test_image_credit_not_part_of_financial_fact(self):
        core = radar.detailed_article_core(
            "3분기 스타트업 누적 투자액 10조원 돌파",
            "(AI 이미지 생성)\n3분기 국내 스타트업의 누적 투자액이 10조원을 돌파했다. 투자 회복세는 4년 만이다.",
        )
        self.assertIn("10조원", core)
        self.assertNotIn("이미지 생성", core)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_corporate_denial_not_replaced_with_market_speculation(self):
        title = "SK하이닉스, 솔리다임 자금조달 방식 미정"
        statement = "SK하이닉스는 솔리다임 관련 보도에 대해 확정된 사항은 없다고 설명했다."
        rumour = "시장은 SK하이닉스가 솔리다임 투자 재원 마련을 위해 외부자본을 유치할 수 있다는 관측을 제기했다."
        core = radar.detailed_article_core(title, statement + " " + rumour)
        self.assertIn("확정된 사항은 없", core)
        self.assertIn("자금조달 방식", core)
        self.assertNotIn("관측", core)
        self.assertFalse(radar.unconfirmed_company_action_fact(title, rumour))

    def test_decimal_values_are_not_treated_as_sentence_boundaries(self):
        source = "출처 안내문이 길게 붙었다 " * 30 + ". 미국 8월 PCE 물가는 전년 동월 대비 3.4% 상승했다."
        core = radar.complete_prose_text(source, limit=100)
        self.assertEqual(core, "미국 8월 PCE 물가는 전년 동월 대비 3.4% 상승했다.")

    def test_forecast_comparison_and_anaphora_need_the_actual_fact(self):
        for orphan in (
            "다우존스가 집계한 전문가 예상치 3.7%를 밑돈 수치다.",
            "이 과정에서 솔리다임이 상장되면 주주가치가 훼손될 수 있다는 우려가 나왔다.",
        ):
            self.assertFalse(radar.core_sentence_is_complete(orphan))
        self.assertTrue(radar.core_sentence_is_complete("KB증권은 내년 기업 매출이 23% 늘어날 것으로 예상했다."))


def verify_live_source_boundaries() -> None:
    cases = (
        ("https://biz.heraldcorp.com/article/10891069", "sports", ("강진모",)),
        ("https://core.asiae.co.kr/article/2026100112163454437", "intraday", ("코스피", "코스닥")),
        ("https://www.etoday.co.kr/news/view/2631400", "company", ("솔리다임", "확정된")),
    )
    results = []
    for url, kind, anchors in cases:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=25) as response:
            source = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        parser = ArticleHTMLParser()
        parser.feed(source)
        parser.close()
        detail = extract_article_detail(source)
        assert detail["body_verified"] and parser.target_bodies, f"Unverified explicit source body: {url}"
        assert all(anchor in detail["body"] for anchor in anchors), f"Missing article facts: {url}"
        if kind == "sports":
            assert radar.is_nonmarket_business_event({"title": detail["title"]}), "Sports election must not become a market alert"
            assert not any(marker in detail["body"] for marker in ("'속보' 확인", "프리미엄콘텐츠", "기사를 더 봅니다"))
        elif kind == "intraday":
            assert "주요종목시세" not in detail["body"] and "출처: 한국거래소" not in detail["body"], "Hidden quote-popup data leaked into body"
        else:
            core = radar.detailed_article_core(detail["title"], detail["body"])
            assert radar.core_sentence_is_complete(core) and "확정된 사항은 없" in core and "자금조달 방식" in core, f"Primary company statement was replaced: {core!r}"
        results.append({
            "url": url, "source_title": detail["title"], "body_chars": len(detail["body"]),
            "explicit_regions": len(parser.target_bodies), "body_verified": detail["body_verified"],
            "nonmarket_event": radar.is_nonmarket_business_event({"title": detail["title"]}),
            "query_time_kst": dt.datetime.now(NOW.tzinfo).isoformat(timespec="seconds"),
        })
    queue.save_json(queue.ROOT / "out/gamejoa_live_source_boundary_audit.json", {"status": "passed", "sources": results})
    print(json.dumps(results, ensure_ascii=False))


def audit_saved_report(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist() if name.endswith("gamejoa_preopen_news_radar.json"))
        report = json.loads(archive.read(name))
    audited = []
    for alert in report["alerts"]:
        if not alert.get("korean_business_news"):
            continue
        title = alert.get("source_title") or alert["news"]
        draft = radar.detailed_article_core(title, alert.get("source_body") or alert.get("source_abstract") or "")
        revised = radar.verified_alert_core({**alert, "telegram_core_fact": draft}, title)
        assert radar.core_sentence_is_complete(revised), f"No complete recovered fact: {title}"
        assert radar.compact_title_summary_aligned(title, revised), f"Recovered title/core mismatch: {title}"
        assert not radar.core_has_ui_garbage(revised) and "이미지 생성" not in revised, f"Publisher credit leaked into core: {title}"
        audited.append({
            "title": title, "previous_core": alert.get("telegram_core_fact"), "recovered_core": revised,
            "source_market_event": radar.has_stock_market_link(alert),
        })
    queue.save_json(queue.ROOT / "out/gamejoa_saved_report_core_audit.json", {"status": "passed", "artifact_zip": str(path), "audited": audited})
    print(json.dumps(audited, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    if "--live-sources" in sys.argv:
        verify_live_source_boundaries()
    elif "--audit-report" in sys.argv:
        audit_saved_report(Path(sys.argv[sys.argv.index("--audit-report") + 1]))
    else:
        unittest.main()

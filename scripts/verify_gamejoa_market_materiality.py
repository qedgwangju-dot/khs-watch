#!/usr/bin/env python3
"""Selection regressions and read-only saved-run materiality audits."""

import argparse
import copy
import datetime as dt
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import gamejoa_market_materiality as materiality
import gamejoa_preopen_news_radar_fda_quality_runner as production

radar = production.runner
NOW = dt.datetime(2026, 10, 1, 22, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
KEEP = (
    ("식품기업, 미국 김밥 매출 59% 증가", "식품기업은 미국 김밥의 1∼7월 매출이 전년비 59% 증가했다고 밝혔다."),
    ("전자기업, 신제품 공개…분기 가이던스 상향", "전자기업은 분기 매출 가이던스를 12% 상향했다고 발표했다."),
    ("반도체, 2027년 계약가 인상 협상", "공급 부족을 반영해 2027년 HBM4 계약가 인상 협상을 진행 중이라는 전망이다."),
    ("FCC, 중국산 장비 수입 제한 검토", "소식통에 따르면 FCC는 중국산 데이터센터 광 송수신기의 수입 제한안을 검토 중이다."),
    ("EU, 한국산 철강 관세 완화 제안", "EU는 한국산 철강 관세를 46%에서 19.7%로 완화하는 방안을 제안했다."),
    ("재무부, 차입 추정 발표", "미 재무부는 분기 시장성 차입 추정을 발표하고 국채 조달 규모를 증액했다."),
    ("ECB, 기준금리 인하", "유럽중앙은행은 기준금리를 0.25%포인트 인하했다."),
    ("이란 협상 재개 발언", "트럼프는 이란에서 연락을 받았으며 이란이 협상을 원한다고 말했다."),
    ("우크라이나, 에너지 시설 공격", "우크라이나는 러시아 에너지 시설 공격을 확대했다."),
    ("레버리지 규제 첫날 거래대금 급감", "레버리지 ETF 거래대금은 기본예탁금 상향 첫날 12조원에서 3조원으로 감소했다."),
    ("외국인, 반도체주 순매수", "외국인은 삼성전자와 SK하이닉스 주식을 4조5000억원 순매수했다."),
    ("그룹 회장, 자사주 매수", "그룹 회장은 회사 주식 3620주를 매수했다고 공시했다."),
    ("바이오 스타트업, 투자유치", "바이오 스타트업은 임상 연구를 위해 800억원 투자를 유치했다."),
    ("조선기업, AI 용접 고객 도입", "조선기업은 미국 군함 조선소 고객의 생산라인에 AI 용접 기술을 도입했다."),
    ("약물 임상 결과 공개", "제약기업은 신약의 임상 3상 결과를 공개하고 허가 신청을 추진한다고 밝혔다."),
    ("글로벌 고객사와 HBM 협력 논의", "양측은 HBM 공급과 파운드리 공동 개발 협력 방안을 논의한 것으로 관측됐다."),
    ("공장 가동 검토", "기업은 반도체 생산 확대를 위해 해외 공장 가동을 검토한다."),
    ("전력장비, 냉각 기술 공개", "업체는 데이터센터 고객 공급을 위해 검증한 냉각 기술을 공개했다."),
    ("폭염에 양식장 집단 폐사", "폭염으로 양식장 어류 3만 마리가 폐사해 생산과 공급에 피해가 발생했다."),
    ("아파트 정전 잇따라", "폭염 속 변압기 과부하로 아파트 정전이 잇따랐다."),
    ("항만 노조 파업", "항만 노조 파업으로 화물 운송과 공급 일정에 차질이 발생했다."),
    ("기업 주주환원 확대 전망", "증권사는 기업의 주주환원 규모가 확대될 것으로 전망하며 배당 상향을 예상했다."),
    ("엔비디아 NVHBM 공개", "엔비디아는 메모리 공급 업체와 검증한 NVHBM의 대역폭이 30% 높아졌다고 공개했다."),
    ("Robotmaker unveils production plan", "The robotmaker plans to expand production capacity at its new factory."),
    ("ECB cuts interest rates", "The ECB cut interest rates after inflation fell."),
    ("US drafting import ban", "Sources say the US is drafting an import ban on Chinese data center devices."),
)
DROP = (
    ("전자기업, AI 미래 협력 강화", "전자기업은 AI 혁신 비전을 공유하고 협력을 강화하기로 했다."),
    ("자동차기업, 대표 방문…협력 강화", "대표는 혁신 비전을 공유하며 동반성장을 약속했다."),
    ("회장, 한국 경제 극찬", "회장은 한국 경제의 저력을 극찬하고 미래를 응원했다."),
    ("반도체기업, 임직원 봉사", "반도체기업 직원 100명은 이웃을 돕는 봉사 활동에 참가했다."),
    ("투자 기업, 브랜드상 수상", "투자 기업은 고객 만족도를 인정받아 브랜드상을 수상했다고 발표했다."),
    ("AI기업, 신제품 공개", "AI기업은 세련된 디자인과 편리한 사용성을 갖춘 신제품을 공개했다."),
    ("전자기업, 체험행사…신제품 할인", "전자기업은 신제품 체험행사에서 경품과 할인 쿠폰을 제공한다고 발표했다."),
    ("기업, 협력 강화", "기업은 협력 비전을 공유했다. 지난해 기업 매출은 20% 증가했다."),
    ("전자기업, 대표 회동", "대표들은 미래 혁신을 이야기했다. 다른 자동차업체는 매출 전망을 20% 상향했다."),
    ("전자기업, AI 협력 강화", "전자기업은 AI 혁신 비전을 공유했다. 전자기업의 매출은 20% 증가했다."),
    ("Bank unveils brand award", "The bank announced its charity brand award."),
)


def alert(title, body):
    return {"news": title, "source_title": title, "original_news": title,
            "source_body": body, "source_abstract": body, "body_verified": True,
            "korean_business_news": True, "published": NOW.isoformat(),
            "impacts": ["돈 버는 능력", "시간표"], "sectors": ["한국 기업/산업 뉴스"],
            "link": "https://www.yna.co.kr/view/materiality-fixture"}


class MaterialityChecks(unittest.TestCase):
    def test_preopen_specific_fact_baseline_is_preserved_in_live_selection(self):
        cases = (
            ("AI 인프라 기업, 최대 420억달러 금융지원 협상", "AI 인프라 기업은 고객의 데이터센터 투자를 지원하기 위해 최대 420억달러 대출 자금조달 계약을 검토한다."),
            ("브렌트유, 중동 공급 위험에 4.37% 상승", "12월물 브렌트유는 4.37% 상승한 배럴당 102.31달러로 집계됐다."),
            ("뉴욕증시, 소폭 상승…나스닥 0.04% 상승", "나스닥지수는 0.04% 상승하며 거래를 마쳤다."),
        )
        items = [production.contract.strict.classify({
            "title": title, "summary": body, "source_body": body, "source_abstract": body,
            "body_verified": True, "layer": "trusted", "publisher": "연합뉴스", "published": NOW,
            "link": f"https://www.yna.co.kr/view/preopen-quality-baseline-{index}",
        }, NOW) for index, (title, body) in enumerate(cases)]
        self.assertTrue(all(item is not None for item in items[:2]), [(case[0], item is not None) for case, item in zip(cases, items)])
        # Simulate a weak recap supplied by legacy preselection as well.
        items[-1] = items[-1] or alert(*cases[-1])
        items[-1]["score"] = 9999
        outputs = []
        for mode in ("preopen", "live"):
            with patch.dict(radar.os.environ, {"RADAR_RUN_MODE": mode}), patch.object(radar.base, "kst_now", return_value=NOW):
                selected = radar.quality_display_alerts(copy.deepcopy(items), 2)
            self.assertEqual({item["source_title"] for item in selected}, {case[0] for case in cases[:2]})
            cores = {item["source_title"]: radar.verified_alert_core(item, item["news"]) for item in selected}
            self.assertIn("420억달러", cores[cases[0][0]])
            self.assertIn("검토", cores[cases[0][0]])
            self.assertIn("4.37%", cores[cases[1][0]])
            self.assertIn("102.31달러", cores[cases[1][0]])
            self.assertTrue(all(radar.core_sentence_is_complete(core) for core in cores.values()))
            outputs.append(cores)
        self.assertEqual(outputs[0], outputs[1])

    def test_ipo_timing_precedes_historical_revenue_and_retains_early_stage(self):
        title = "앤스로픽, 11월 중순 상장 추진…오픈AI 제치고 IPO 선점하나"
        body = "AI 모델 클로드를 개발한 앤스로픽이 이르면 11월 중순 미국 증시 상장을 추진한다. 앤스로픽의 매출은 지난해 46억달러로 직전해보다 급증했다."
        item = {**alert(title, body), "telegram_core_fact": "앤스로픽 매출은 46억달러입니다."}
        core = radar.verified_alert_core(item, title)
        self.assertIn("11월 중순", core)
        self.assertIn("추진", core)
        self.assertNotIn("46억", core)
        assessment = materiality.assess(title, body)
        self.assertEqual(assessment["priority"], 3)
        self.assertIn("timeline", assessment["axes"])
        self.assertEqual(assessment["evidence"][0]["stage"], "early_signal")
        self.assertNotEqual(materiality.focus_kind("상장지수펀드 시장 성장"), "capital_listing")

    def test_first_headline_event_precedes_secondary_bond_context(self):
        title = "원·달러 NDF 0.2원 하락, 미국채 금리 하락 vs 달러인덱스 연 최고"
        body = "원·달러 역외 NDF 환율은 전장 대비 0.2원 하락했다. 특히 미국채 2년물 금리는 10bp 넘게 급락했다."
        item = {**alert(title, body), "telegram_core_fact": "특히 미국채 2년물 금리는 10bp 넘게 급락했다."}
        core = radar.verified_alert_core(item, title)
        self.assertEqual(materiality.focus_kind(title), "fx")
        self.assertIn("NDF", core)
        self.assertIn("0.2원", core)
        self.assertNotIn("2년물", core)
        body = "미국채 금리가 하락한 반면 달러화는 연중 최고치를 경신했다. 1일(현지시간) 차액결제선물환(NDF)시장에서 원·달러 1개월물은 1357.3/1357.7원에 최종 호가되며 거래를 마쳤다."
        core = radar.verified_alert_core(alert(title, body), title)
        self.assertIn("NDF", core)
        self.assertIn("1357.3/1357.7원", core)

    def test_mortgage_source_rate_change_precedes_broad_home_cost_commentary(self):
        title = "美 주담대 금리 7.28%…주택 구매 여력 약화"
        body = "미국 주택담보대출(모기지) 금리가 7%를 훌쩍 넘어서며 3년 만에 최고 수준으로 치솟았다. 1일(현지시간) 월스트리트저널 등에 따르면 국책 모기지업체 프레디맥이 집계한 미국의 30년 만기 고정금리 모기지 평균 금리는 이번 주 7.28%로 전주 7.03%보다 0.25%포인트 올랐다. 미국 주택 가격과 계약금이 상승한 상황에서 대출 금리마저 7%를 넘어서면서다."
        item = {**alert(title, body), "telegram_core_fact": "미국 주택 가격과 계약금이 상승한 상황에서 대출 금리마저 7%를 넘어서면서다."}
        core = radar.verified_alert_core(item, title)
        for fact in ("미국", "30년", "7.28%", "0.25%포인트"):
            self.assertIn(fact, core)
        self.assertLessEqual(len(core), 100)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_denial_headline_cannot_reuse_the_previous_announcement_as_core(self):
        title = '한정애 "알래스카 LNG 투자 확정 아냐"'
        body = '더불어민주당 한정애 사무총장은 1일 도널드 트럼프 미국 대통령이 한국의 알래스카 액화천연가스(LNG) 개발 사업 투자를 기정사실로 발표한 데 대해 "확정된 것이 아니다"라고 밝혔다. 앞서 트럼프 대통령은 알래스카 LNG 개발 사업에 한국이 500억 달러 이상을 투자할 것이라고 발표했다.'
        item = {**alert(title, body), "telegram_core_fact": "트럼프 대통령은 한국이 알래스카 LNG에 500억 달러를 투자할 것이라고 발표했다."}
        core = radar.verified_alert_core(item, title)
        self.assertIn("한정애", core)
        self.assertIn("LNG", core)
        self.assertIn("확정된 것이 아니다", core)
        self.assertNotIn("500억", core)
        self.assertLessEqual(len(core), 100)
        self.assertTrue(radar.core_sentence_is_complete(core))
        bad = "1) " + title + "\n- 핵심: 한국은 알래스카 LNG에 500억 달러를 투자한다고 발표했다.\n"
        self.assertIn("headline_event_or_period_mismatch", radar.compact_alert_block_errors(bad))

    def test_loan_advertorial_cannot_be_rescued_by_an_ipo_or_supply_paragraph(self):
        title = "신규 상장주 움직임에 관심…최대 4배까지 활용 가능한 기회 잡으려면"
        body = "항법 기술 기업이 코스닥에 상장했다. 회사는 방산 제품을 공급하고 양산 확대를 계획한다. 방산 분야의 추가매수를 고려하고 있었다면 필요한 투자금을 준비하는 방법도 검토할 수 있다. 하이스탁론은 최대 4배 주식자금 상품과 신용·미수 대환을 제공한다. 고객상담센터로 연락하면 대출 상담이 가능하다."
        item = alert(title, body)
        self.assertEqual(radar.source_market_materiality(item)["disposition"], "exclude")
        self.assertEqual(radar.quality_display_alerts([item], 1), [])
        self.assertIn("investment_loan_solicitation", item["_exclusion_reason"])
        regulatory = materiality.assess("스탁론 담보 규제 강화", "금융당국은 스탁론의 담보 규제를 강화해 시행했다.")
        self.assertEqual(regulatory["disposition"], "keep")

    def test_previous_session_today_preview_is_stale_even_inside_24_hour_window(self):
        now = NOW.replace(day=2, hour=7, minute=40)
        item = alert("[오늘의 증시] 장기금리 부담 속 반등 기대", "미국 국채금리는 5.30%까지 상승했다.")
        item["published"] = NOW.replace(hour=8, minute=3).isoformat()
        self.assertTrue(radar.is_stale_session_preview(item, now))
        with patch.object(radar.base, "kst_now", return_value=now):
            self.assertEqual(radar.quality_display_alerts([item], 1), [])
        self.assertEqual(item["_exclusion_reason"], "stale_session_preview")
        item["published"] = now.isoformat()
        self.assertFalse(radar.is_stale_session_preview(item, now))
        item["source_title"] = "뉴욕증시 마감…금리 상승"
        item["published"] = NOW.replace(hour=23).isoformat()
        self.assertFalse(radar.is_stale_session_preview(item, now))

    def test_buyback_ending_core_keeps_source_deadlines_and_uncertainty(self):
        title = "삼전닉스 자사주 방파제 곧 사라진다"
        body = "증권가는 자사주 매입 종료 후 수급을 주목한다. 지난 8월 5329만주 취득을 공시하고 거래일마다 200만주씩 주문을 낸 삼성전자는 이날 매수를 마무리할 예정이다. 2407만주 취득을 예고하고 하루 60만주씩 사들인 SK하이닉스는 오는 15~17일쯤 마지막 주문을 낼 것으로 점쳐진다."
        item = {**alert(title, body), "telegram_core_fact": "증권가는 자사주 매입 종료 후 수급을 주목한다."}
        core = radar.verified_alert_core(item, title)
        for fact in ("삼성전자", "예정", "SK하이닉스", "15~17일", "점쳐진다"):
            self.assertIn(fact, core)
        self.assertLessEqual(len(core), 100)
        self.assertTrue(materiality.core_focus_aligned(title, core))
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_orders_and_selling_prices_have_direct_earnings_evidence_in_any_industry(self):
        for title, body in (
            ("신산업 기업, 공급계약 체결", "신산업 기업은 해외 고객과 제품 공급계약을 체결했다고 밝혔다."),
            ("부품업체, 판가 인상", "부품업체는 제품 판가를 12% 인상했다고 밝혔다."),
        ):
            audit = materiality.assess(title, body)
            self.assertEqual(audit["disposition"], "keep")
            self.assertEqual(audit["priority"], 3)
            self.assertIn("earnings", audit["axes"])
            self.assertNotIn("flows", audit["axes"])
        audit = materiality.assess("신산업 기업, 공급계약 협상", "신산업 기업은 해외 고객과 공급계약을 협상 중이다.")
        self.assertEqual(audit["disposition"], "keep")
        self.assertEqual(audit["evidence"][0]["stage"], "early_signal")

    def test_tactical_weapon_news_needs_economic_transmission_not_range_or_stock(self):
        title = "우크라, 자체 개발 탄도미사일 첫 실전 투입…러시아 목표물 타격"
        body = "우크라이나가 자체 개발한 탄도미사일을 처음으로 실전에 투입했다. 생산 능력 부족으로 미사일 공급이 지연되고 있다. 러시아 진지를 공격했다."
        self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
        item = alert(title, body)
        self.assertEqual(radar.quality_display_alerts([item], 1), [])
        commercial = "조선기업은 미국 군함 조선소 고객의 생산라인에 AI 용접 기술을 도입했다."
        self.assertEqual(materiality.assess("조선기업, 군함 조선소 AI 기술 도입", commercial)["disposition"], "keep")
        for headline, source in (
            ("우크라이나, 러시아 에너지 시설 공격", "우크라이나는 러시아 에너지 시설 공격을 확대했다."),
            ("트럼프, 이란 협상 재개", "트럼프는 이란이 협상을 원한다고 말했다."),
            ("미국, 중동 병력 증강", "미국은 이란 위협에 대응해 중동 항공모함 배치와 병력 증강을 발표했다."),
        ):
            self.assertNotEqual(materiality.assess(headline, source)["disposition"], "exclude")

    def test_hormuz_hit_keeps_reported_uncertainty_and_direct_supply_evidence(self):
        title = "호르무즈해협서 또 유조선 미확인 발사체에 피격…화재 발생"
        body = "UKMTO는 호르무즈 해협의 유조선이 미확인 발사체에 맞아 화재가 발생했다는 제3자 보고를 접수했다고 밝혔다. 미국과 이란의 협상은 교착 상태다."
        audit = materiality.assess(title, body)
        self.assertEqual(audit["priority"], 3)
        self.assertIn("제3자 보고", audit["evidence"][0]["source_excerpt"])
        core = radar.verified_alert_core(alert(title, body), title)
        self.assertIn("제3자 보고", core)
        self.assertNotIn("유가 상승", core)

    def test_major_war_escalation_survives_without_already_observed_oil_reaction(self):
        for title, body in (
            ("트럼프, 이란 추가 공격 임박 경고", "트럼프는 이란에 대한 추가 공격이 임박했다고 경고했다."),
            ("미국, 중동 항공모함 추가 배치", "미국은 이란 위협에 대응해 중동 항공모함 추가 배치와 병력 증강을 발표했다."),
            ("러시아, 핵무기 사용 위협", "러시아는 전쟁 확대에 대해 핵무기 사용으로 대응할 수 있다고 경고했다."),
        ):
            audit = materiality.assess(title, body)
            self.assertEqual(audit["disposition"], "keep", audit)
            self.assertGreaterEqual(audit["priority"], 2)
            self.assertIn("discount_rate", audit["axes"])

    def test_new_financing_precedes_routine_price_recap_without_keyword_score(self):
        financing = materiality.assess("브로드컴, 앤트로픽 대출 협상", "브로드컴은 앤트로픽에 420억달러 대출을 제공하는 자금조달 계약을 검토한다.")
        recap = materiality.assess("뉴욕증시 강보합 마감…나스닥 0.04% 상승", "나스닥 주가는 0.04% 상승했다. 다른 기업의 매출은 50% 증가했다.")
        self.assertGreater(financing["priority"], recap["priority"])
        self.assertEqual(financing["headline_stage"], "early_signal")
        self.assertNotIn("flows", materiality.assess("나스닥 상승", "나스닥 주가는 0.04% 상승했다.")["axes"])

    def test_energy_headline_core_does_not_select_unrelated_stock_returns(self):
        title = "뉴욕증시 강보합…브렌트유 중동 항모 추가에 4% 상승"
        body = "나이키 주가는 0.71% 하락했고 알파벳은 제미니 공개 후 1.70% 밀렸다. 브렌트유 12월 인도분 종가는 전장 대비 4.4% 급등한 배럴당 102.31달러를 기록했다."
        item = alert(title, body)
        item["telegram_core_fact"] = body.split(". 브렌트유")[0] + "."
        core = radar.verified_alert_core(item, title)
        self.assertIn("브렌트유", core)
        self.assertIn("4.4%", core)
        self.assertNotIn("나이키", core)
        self.assertNotIn("알파벳", core)
        bad = "1) " + title + "\n- 핵심: 나이키 주가는 0.71% 하락했다.\n"
        self.assertIn("headline_event_or_period_mismatch", radar.compact_alert_block_errors(bad))

    def test_bond_yield_core_does_not_substitute_treasury_buyback(self):
        title = "미·영·프 장기금리 수십년래 최고…글로벌 국채 투매 심화"
        body = "미국 10년물 국채금리는 장중 5.34%까지 치솟아 24년 최고치를 갱신했다. 영국 30년물 국채금리는 6.029%로 상승했다. 재무부는 463억9000만달러 판매 제안을 받아 60억달러를 매입했다."
        item = alert(title, body)
        item["telegram_core_fact"] = "재무부는 60억달러를 매입했다."
        core = radar.verified_alert_core(item, title)
        self.assertIn("10년물", core)
        self.assertIn("5.34%", core)
        self.assertNotIn("60억달러", core)

    def test_headline_month_and_ownership_fact_beat_background_or_aspiration(self):
        title = "상승 종목 743곳→265곳 급감…9월 코스피 순환매 꺾였다"
        body = "5월 코스피 지수는 28.45% 급등했지만 상승 종목 비중은 11.7%였다. 9월 코스피 시장에서 주가가 오른 종목은 265곳으로 전체의 28.1%에 그쳤다."
        core = radar.verified_alert_core({**alert(title, body), "telegram_core_fact": body.split(". 9월")[0] + "."}, title)
        self.assertIn("9월", core)
        self.assertIn("265곳", core)
        self.assertNotIn("5월", core)
        self.assertTrue(all("5월" not in e["source_excerpt"] for e in materiality.assess(title, body)["evidence"]))
        title = "이에이트, 다컴시스템 지분 35% 인수…AIDC 사업 진출"
        body = "이에이트는 IT장비 공급기업 다컴시스템의 지분 35%를 인수했다고 밝혔다. 이에이트 관계자는 데이터센터를 새로운 성장축으로 키우고 기업가치를 높이겠다고 말했다."
        item = {**alert(title, body), "telegram_core_fact": "이에이트 관계자는 데이터센터를 새로운 성장축으로 키우고 기업가치를 높이겠다고 말했다."}
        core = radar.verified_alert_core(item, title)
        self.assertIn("35%", core)
        self.assertIn("다컴시스템", core)
        self.assertNotIn("성장축", core)

    def test_research_spending_core_keeps_issuer_not_subjectless_connector(self):
        title = "대기업 SI, 상반기 R&D 투자 가장 많이 한 기업은?"
        body = "포스코DX의 상반기 R&D 비용은 79억6800만원으로 전년 대비 62.1% 증가했다. 또 매출 대비 R&D 비중도 0.86%에서 1.68%로 높아졌다."
        core = radar.verified_alert_core({**alert(title, body), "telegram_core_fact": "또 매출 대비 R&D 비중은 1.68%로 높아졌다."}, title)
        self.assertIn("포스코DX", core)
        self.assertIn("62.1%", core)
        self.assertLessEqual(materiality.assess(title, body)["priority"], 2)
        self.assertLessEqual(len(core), 100)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_source_chrome_and_related_story_are_not_article_evidence(self):
        title = "[속보] 국제유가 급등…브렌트유 4.37% 상승"
        body = "이투데이\n국제경제\n입력 2026-10-02 06:07\n북마크 되었습니다.\nURL공유\n가장작게\n크게\n국제유가는 급등했다.\n런던 ICE선물거래소에서 12월물 브렌트유는 4.37% 상승한 배럴당 102.31달러로 집계됐다.\n관련 뉴스\n다른 기업은 매출이 500% 증가했다고 발표했다."
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        self.assertIn("102.31달러", core)
        self.assertNotIn("되었습니다", core)
        self.assertEqual(radar.source_market_materiality(item)["priority"], 3)
        self.assertNotIn("500%", str(radar.source_market_materiality(item)["evidence"]))
        title = "이에이트, 다컴시스템 지분 35% 인수"
        body = "읽기모드\n다크모드\n폰트크기\n가\n기사반응\n이에이트(E8)는 공공조달 IT장비 공급기업 다컴시스템의 지분 35%를 인수했다고 1일 밝혔다."
        core = radar.verified_alert_core(alert(title, body), title)
        self.assertIn("35%", core)
        self.assertNotIn("기사반응", core)

    def test_following_rd_amount_binds_only_to_adjacent_source_issuer(self):
        title = "대기업 SI, 상반기 R&D 투자 확대"
        body = "포스코DX는 R&D 투자를 늘렸다.\n올해 상반기 R&D 비용으로 전년 동기 대비 62.1% 늘어난 79억6800만원을 집행한 것이다.\n롯데이노베이트도 R&D 투자를 늘렸다.\n올해 상반기 연구개발비는 86억3800만원으로 전년 동기보다 29.7% 증가했다."
        sentences = radar.ranked_article_sentences(body, [], title=title)
        self.assertTrue(any("포스코DX" in s and "79억6800만원" in s for s in sentences))
        self.assertTrue(any("롯데이노베이트" in s and "86억3800만원" in s for s in sentences))
        self.assertFalse(any("포스코DX" in s and "86억3800만원" in s for s in sentences))

    def test_royalty_contract_is_cashflow_but_price_recap_is_not_a_flow(self):
        audit = materiality.assess("바이오기업, 로열티 계약", "바이오기업은 계약 체결 후 시판 7년간 매출의 7%를 로열티로 수령한다.")
        self.assertEqual(audit["priority"], 3)
        self.assertIn("earnings", audit["axes"])
        self.assertNotIn("flows", audit["axes"])
        recap = materiality.assess("뉴욕증시 소폭 상승…나스닥 0.04%↑", "나스닥 주가는 0.04% 상승했다. 다른 회사 매출은 40% 증가했다.")
        self.assertLess(recap["priority"], audit["priority"])

    def test_other_fund_or_old_loss_buffer_cannot_replace_current_fund_results(self):
        title = "뉴딜펀드 만기청산 절반 손실…재정 부담 139억"
        body = "2일 국회 정무위원회 소속 의원실이 관계 기관으로부터 상세히 제출받은 조사 자료에 따르면 만기청산된 뉴딜 국민참여형펀드 자펀드 17개의 평균 내부수익률은 0.68%로 집계됐다.\n2021년 출시된 뉴딜펀드는 손실이 발생해도 21.5%까지 재정이 우선 부담한다.\n다른 성장펀드의 자펀드는 재정이 손실의 18.8%를 우선 부담한다."
        core = radar.verified_alert_core(alert(title, body), title)
        self.assertIn("뉴딜", core)
        self.assertIn("17개", core)
        self.assertIn("0.68%", core)
        self.assertNotIn("21.5%", core)
        self.assertNotIn("18.8%", core)
        self.assertLessEqual(len(core), 100)

    def test_material_and_early_news_survive_without_signed_contract_or_ticker_list(self):
        for title, body in KEEP:
            with self.subTest(title=title):
                audit = materiality.assess(title, body)
                self.assertEqual(audit["disposition"], "keep", audit)
                for item in audit["evidence"]:
                    self.assertIn(item["source_excerpt"], body)

    def test_routine_and_vague_news_are_not_market_changes(self):
        for title, body in DROP:
            with self.subTest(title=title):
                self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")

    def test_preliminary_stage_is_not_upgraded_to_confirmed(self):
        for title, body in KEEP[2:5]:
            audit = materiality.assess(title, body)
            self.assertTrue(any(item["stage"] == "early_signal" for item in audit["evidence"]), audit)

    def test_price_increase_is_not_evidence_of_foreign_investor_buying(self):
        audit = materiality.assess("주가 상승", "회사 주가는 전일보다 5% 상승했다.")
        self.assertEqual(audit["disposition"], "keep")
        self.assertNotIn("flows", audit["axes"])
        self.assertIn("flows", materiality.assess(*KEEP[10])["axes"])

    def test_templates_and_flags_cannot_rescue_vague_news(self):
        item = alert(*DROP[0])
        item.update(policy_plain_summary="매출 100% 증가, 관세 인하와 순매수가 발생했다.", sectors=["AI/반도체"], policy_drive=True)
        self.assertEqual(radar.source_market_materiality(item)["disposition"], "exclude")
        self.assertEqual(radar.quality_display_alerts([item], 1), [])
        self.assertTrue(item["_exclusion_reason"].startswith("market_materiality:"))

    def test_floating_solar_is_not_misread_as_an_award(self):
        audit = materiality.assess("수상 태양광 신기술 공개", "수상 태양광 기업은 고객 공급을 위해 검증한 신기술을 공개했다.")
        self.assertEqual(audit["disposition"], "keep")

    def test_proposal_not_upgraded_by_background_statistics(self):
        audit = materiality.assess("증시 경보 체계 바꿔야", "연구위원은 증시 규제를 완화해야 한다고 제언했다. 경보 지정 중 주가 상승률 요건의 비중은 72%로 증가했다.")
        self.assertEqual(audit["priority"], 2)
        self.assertEqual(audit["headline_stage"], "early_signal")
        released = materiality.assess("PCE 물가 3.4% 상승", "PCE 물가는 전년비 3.4% 상승해 예상치 3.7%를 하회했다.")
        self.assertEqual(released["priority"], 3)
        self.assertTrue(all(item["stage"] == "reported_change" for item in released["evidence"]))

    def test_real_operating_spec_and_share_transfer_are_not_routine_promotions(self):
        cases = (
            ("업스테이지, 솔라 미니 4 공개", "업스테이지는 GPU 한 장으로 구동할 수 있는 AI 모델 솔라 미니 4를 공개했다."),
            ("회장, 재단에 460억원 규모 주식 기부", "회장은 재단에 460억원 규모의 회사 주식을 기부할 계획이라고 밝혔다."),
        )
        for title, body in cases:
            self.assertEqual(materiality.assess(title, body)["disposition"], "keep")

    def test_memory_article_core_keeps_source_forecast_not_subjectless_revenue(self):
        title = '"내년·내후년 HBM 수급 더 빠듯"…삼전닉스 200조 분기 영업익 시대'
        body = (
            "마이크론은 4분기 매출액이 73조5000억원을 기록했다고 밝혔다. "
            "트렌드포스는 내년 HBM 평균판매가격(Blended ASP)이 올해보다 121% 급등할 것으로 전망했다."
        )
        core = radar.detailed_article_core(title, body)
        self.assertIn("트렌드포스", core)
        self.assertIn("121%", core)
        self.assertIn("전망", core)
        self.assertNotIn("73조", core)
        recovered = radar.verified_alert_core({**alert(title, body), "telegram_core_fact": "4분기 매출은 73조5000억원입니다."}, title)
        self.assertEqual(recovered, core)
        self.assertIn("financial_subject_missing", radar.compact_alert_block_errors("1) 기업 실적 발표\n- 핵심: 4분기 매출은 73조5000억원입니다.\n"))

    def test_financial_compaction_retains_actual_issuer(self):
        core = radar.financial_result_fact("메모리 업황", ["마이크론은 4분기 매출이 73조5000억원을 기록했다고 밝혔다."])
        self.assertIn("마이크론", core)
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_listing_rule_announcement_outweighs_old_earnings_in_core(self):
        title = "매출 2100억 제조기업도 상폐 걱정…우진플라임, 시총 기준 강화 대응"
        body = (
            "1985년 설립돼 2001년 코스닥시장에 상장한 뒤 2006년 유가증권시장으로 이전했다. "
            "우진플라임은 2분기 매출 558억원, 영업이익 8억원을 기록했다. "
            "내년 7월 유가증권시장 상장유지 시가총액 기준이 500억원으로 높아지면서 기업가치 제고가 당면 과제로 떠올랐다. "
            "우진플라임은 이날 기업가치 제고 계획을 공시하고 2028년까지 ROE를 높이겠다고 밝혔다. "
            "향후 3년간 주당 50원 이상을 배당하고 발행주식의 2% 이상인 자사주 40만주 이상을 매입·소각한다."
        )
        item = alert(title, body)
        item["telegram_core_fact"] = "우진플라임 2분기 영업이익은 8억원입니다."
        core = radar.verified_alert_core(item, title)
        self.assertIn("우진플라임", core)
        self.assertIn("내년 7월", core)
        self.assertIn("500억원", core)
        self.assertIn("40만주", core)
        self.assertIn("계획", core)
        self.assertNotIn("영업이익은 8억원", core)
        self.assertEqual(core, radar.detailed_article_core(title, body))
        self.assertTrue(radar.core_sentence_is_complete(core))
        audit = materiality.assess(title, body)
        self.assertNotIn("1985년 설립돼", str(audit["evidence"]))

    def test_unverified_body_cannot_establish_materiality(self):
        item = alert(*KEEP[0])
        item["body_verified"] = False
        audit = radar.source_market_materiality(item)
        self.assertEqual(audit["evidence"], [])
        self.assertEqual(audit["reason"], "source_evidence_unavailable")

    def test_materiality_precedes_legacy_score_and_display_limit(self):
        meeting_case = ("이재용, 오픈AI 본사서 샘 올트먼 만났다", "삼성전자와 오픈AI는 HBM 공급과 파운드리 공동 개발 협력 방안을 논의한 것으로 관측됐다.")
        meeting, result = [production.contract.strict.classify({
            "title": title, "summary": body, "source_body": body, "source_abstract": body, "body_verified": True, "layer": "trusted",
            "publisher": "연합뉴스", "published": NOW, "link": f"https://www.yna.co.kr/view/materiality-rank-{index}",
        }, NOW) for index, (title, body) in enumerate((meeting_case, KEEP[0]))]
        self.assertIsNotNone(meeting)
        self.assertIsNotNone(result)
        meeting["score"], result["score"] = 9999, 10
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts([meeting, result], 1)
        self.assertEqual(len(selected), 1, (meeting.get("_exclusion_reason"), result.get("_exclusion_reason")))
        self.assertEqual(selected[0]["source_title"], result["source_title"])
        self.assertEqual(selected[0]["market_materiality"], radar.source_market_materiality(selected[0]))

    def test_title_core_and_compact_format_stay_intact(self):
        row = {"title": KEEP[0][0], "summary": KEEP[0][1], "source_abstract": KEEP[0][1],
               "source_body": KEEP[0][1], "layer": "trusted", "body_verified": True, "publisher": "연합뉴스", "published": NOW,
               "link": "https://www.yna.co.kr/view/materiality-fixture"}
        classified = production.contract.strict.classify(row, NOW)
        self.assertIsNotNone(classified)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts([classified], 1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["news"], row["title"])
        block = radar.compact_alert(selected[0], 1, NOW, {}, {})
        self.assertEqual(radar.compact_alert_block_errors(block), [])
        self.assertIn("59%", block)
        self.assertNotIn("market_materiality", block)
        self.assertNotIn("의사결정 영향", block)

    def test_assessment_does_not_modify_alert_or_delivery_state(self):
        item = alert(*KEEP[0])
        before = copy.deepcopy(item)
        radar.source_market_materiality(item)
        self.assertEqual(item, before)
        for name in ("seen", "first_seen_kst", "message_id", "sent", "send_telegram"):
            self.assertNotIn(name, materiality.assess(*KEEP[0]))

    def test_guards_are_in_both_execution_workflows(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("gamejoa-preopen-news-radar.yml", "gamejoa-preopen-news-radar-test.yml"):
            self.assertIn("python scripts/verify_gamejoa_market_materiality.py", (root / ".github/workflows" / name).read_text(encoding="utf-8"))
        self.assertIn('alert.get("market_materiality") != materiality', (root / "scripts/verify_gamejoa_generated_report.py").read_text(encoding="utf-8"))


def audit_saved_runs(paths):
    results = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            name = next(name for name in archive.namelist() if name.endswith("gamejoa_preopen_news_radar.json"))
            report = json.loads(archive.read(name))
        for item in report["alerts"]:
            title = item.get("source_title") or item.get("news") or ""
            run_time = radar.detail_queue.parse_time(report.get("query_time_kst"))
            results.append({
                "artifact": str(path), "title": title,
                "materiality": radar.source_market_materiality(item),
                "stored_core": item.get("telegram_core_fact"),
                "revalidated_core": radar.verified_alert_core(item, title),
                "stale_session_preview": bool(run_time and radar.is_stale_session_preview(item, run_time)),
            })
    print(json.dumps({"read_only_shadow_audit": True, "articles": len(results),
                      "changed_cores": sum(r["stored_core"] != r["revalidated_core"] for r in results),
                      "excluded": sum(r["materiality"]["disposition"] == "exclude" for r in results),
                      "stale_previews": sum(r["stale_session_preview"] for r in results),
                      "focus_mismatches": sum(not materiality.core_focus_aligned(r["title"], r["revalidated_core"]) for r in results),
                      "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-zip", action="append", type=Path)
    args, remaining = parser.parse_known_args()
    if args.audit_zip:
        audit_saved_runs(args.audit_zip)
    else:
        unittest.main(argv=[__file__, *remaining])

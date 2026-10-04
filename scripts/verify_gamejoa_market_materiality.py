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

# Synthetic source sentences exercise every event class in the user's industry
# digest. They are selection fixtures, not verification of that digest's claims.
INDUSTRY_DRIVER_CASES = (
    ("robot_foundation_platform", "로봇 모델기업, 외부 하드웨어와 파운데이션 모델 통합", "로봇 모델기업은 외부 휴머노이드 하드웨어에 파운데이션 모델을 통합하는 공동개발 파트너십을 발표했다."),
    ("satellite_environmental_review", "위성 인허가 환경심사 면제", "통신당국은 위성 인허가의 환경심사를 면제하는 규제 개편을 의결했다."),
    ("data_center_power_architecture", "AI 데이터센터, 800V HVDC 규격 채택", "데이터센터 사업자는 전력 분배를 800V HVDC 아키텍처로 전환하는 규격을 채택했다고 발표했다."),
    ("frontier_model_efficiency", "AI 모델기업, 추론비용 절감 모델 공개", "AI 모델기업은 추론비용을 30% 줄인 새 모델의 성능 검증 결과를 공개했다."),
    ("orbital_compute_test", "궤도 AI 가속기 시험 위성 발사 추진", "우주기업은 궤도 AI 가속기의 방사선 내성과 열관리를 검증하기 위한 시험 위성 발사를 추진한다."),
    ("ai_customer_financing", "AI 고객사 장비 리스 자금조달 협상", "인프라기업은 고객의 AI 가속기 리스를 지원하는 100억원 대출 자금조달 계약을 협상 중이다."),
    ("ipo_timing", "AI 기업, 11월 기업공개 추진", "AI 기업은 이르면 11월 미국 증시 기업공개를 추진한다."),
    ("consumer_earnings_restructuring", "소비재기업 매출 감소·비용 구조조정", "소비재기업은 분기 매출이 4% 감소했다고 발표하고 공급망 비용을 줄이는 조직 감원을 추진한다."),
    ("memory_customer_commitments", "메모리기업, 장기계약 잔여수주 확대", "메모리기업은 장기 공급계약의 잔여수주가 증가했다고 발표하고 내년 설비투자 확대를 결정했다."),
    ("power_compute_joint_development", "발전기업·서버기업, AI 데이터센터 공동개발 협약", "발전기업과 서버기업은 400MW AI 데이터센터 공동개발 협약을 맺고 2028년 단계 가동을 계획한다."),
    ("inference_optimization_acquisition", "클라우드기업, 추론 최적화 회사 인수", "클라우드기업은 GPU 유휴시간과 추론비용을 줄이는 기술을 보유한 회사를 인수했다고 발표했다."),
    ("cryogenic_quantum_validation", "양자기업, 극저온 인터커넥트 검증", "양자기업은 20mK 환경에서 극저온 인터커넥트의 채널 격리도 100dB 이상과 열 순환 안정성을 검증했다고 발표했다."),
    ("compound_substrate_cycle", "SiC 기판 공급 부족 전망", "산업 리서치는 AI 전력변환용 SiC 기판 공급 부족과 리드타임 연장을 전망했다."),
    ("optical_architecture_adoption", "AI 클러스터, 800G·1.6T 광트랜시버·CPO 도입", "통신장비기업은 AI 클러스터에 800G·1.6T 광트랜시버와 CPO를 도입하는 규격을 채택했다고 발표했다."),
    ("space_compute_execution", "우주기업, 궤도컴퓨팅 시험 위성 발사 성공", "우주기업은 궤도컴퓨팅 시험 탑재체를 실은 위성 발사 임무를 완료했다고 발표했다."),
    ("commercial_launch_order", "우주기업, 고객과 위성 20회 발사계약 체결", "우주기업은 고객과 위성 20회 발사계약을 체결했다고 발표했다."),
    ("launch_license_review", "연간 발사한도 확대 환경영향평가 착수", "항공당국은 연간 발사한도를 12회에서 50회로 확대하는 허가를 검토하기 위해 환경영향평가에 착수했다."),
    ("space_external_financing", "우주기업, 외부 자금조달 검토", "우주기업은 위성통신 사업을 위한 외부 자금조달 계약을 검토한다고 발표했다."),
    ("defense_cost_scope", "방위사업 예산 추산 비교", "의회는 방위사업 예산의 20년 총비용 추산을 공개하고 국방부의 10년 추산과 산정 범위를 비교했다."),
    ("ai_biology_discovery", "AI 연구진, 신규 효소 시스템 실험 검증", "AI 연구진은 DNA 데이터에서 신규 효소 시스템을 발견하고 실험실 검증 결과를 공개했다. 기능 규명은 진행 중이다."),
    ("reusable_launch_bottleneck", "로켓 열차폐 타일 손상에 재발사 일정 지연", "로켓 운영사는 재진입 열차폐 타일 손상으로 검사와 교체가 늘어 재발사 일정이 5일 지연됐다고 발표했다."),
    ("thermal_protection_validation", "우주선 열차폐 부착 구조 시험 검증", "우주선 개발사는 열차폐 타일 부착 구조가 1400도 열 순환 시험 10회를 견뎠다고 검증 결과를 발표했다."),
    ("propellant_storage_validation", "궤도 극저온 추진제 ZBO 저장 실증", "우주 연구진은 궤도에서 액체 메탄 추진제의 ZBO 저장을 4개월 실증했다고 발표했다."),
    ("launch_material_supply_contract", "발사체 소재기업, 초내열합금 납품계약 체결", "소재기업은 재사용 로켓용 초내열합금 100톤 납품계약을 고객과 체결했다고 발표했다."),
)


def alert(title, body):
    return {"news": title, "source_title": title, "original_news": title,
            "source_body": body, "source_abstract": body, "body_verified": True,
            "korean_business_news": True, "published": NOW.isoformat(),
            "impacts": ["돈 버는 능력", "시간표"], "sectors": ["한국 기업/산업 뉴스"],
            "link": "https://www.yna.co.kr/view/materiality-fixture"}


# Source excerpts from actual deliveries on 2026-10-02, not sector-label fixtures.
DELIVERED_LOCAL_ADMINISTRATION = (
    ("강원도, 지역 생산 전력 활용법 찾는다…현안 6건 돌파구 모색 | 연합뉴스",
     "강원특별자치도가 송전망 제약으로 지역에서 생산한 전력을 제대로 활용하지 못하는 문제를 개선하기 위해 직접 전력거래와 분산에너지 대상 확대 등을 모색하고 나섰다.\n강릉시는 송전제약지역에서 발전사업자가 생산한 전력을 수요처에 직접 공급할 수 있도록 정부 고시 마련과 개정을 건의했다.",
     "https://www.yna.co.kr/view/AKR20261002150900062"),
    ("강원 고성군, 평화경제특구 도전…화진포·대진 관광 거점 조성 | 연합뉴스",
     "호반그룹과 6천800억 투자협약 체결\n군은 군사 규제로 인한 개발 제약과 금강산 육로 관광 중단에 따른 지역경제 피해를 극복하기 위한 대안으로 평화경제특구 조성을 추진한다.",
     "https://www.yna.co.kr/view/AKR20261002155100062"),
    ("최태림 경북도의원 \"대구경북통합신공항 6년 표류, 의성 편입지역 실질 지원하라\"",
     "최태림 경북도의원은 편입지역 주민 지원을 촉구했다.\n기약 없는 이주와 재산권 침해로 고통받는 편입지역 주민들을 위해 경북도 차원의 특별생계지원금 지급이 필요하다며 공식적인 지원 방안을 제안했다.",
     "https://www.etoday.co.kr/news/view/2632202"),
    ("추미애 \"일자리와 주거 연결해야\"…경기도형 특화전략 제시 | 연합뉴스",
     "정부가 수도권 주택공급 확대를 추진하는 가운데 추미애 경기도지사가 지역의 산업·일자리와 주거를 함께 설계하는 경기도형 주택공급 전략을 제시하고 나섰다.\n서울 집값 상승에 따른 공급 대책이 세워지면 이에 대한 신규택지 공급을 경기도가 떠안게 되고 그러다보니 경기도 나름의 도시계획 비전을 전개할 여유가 없다고 덧붙였다.",
     "https://www.yna.co.kr/view/AKR20261002161400061"),
)


class EntertainmentBoundaryChecks(unittest.TestCase):
    SOURCE_URL = "https://biz.chosun.com/entertainment/enter_general/2026/10/03/ME4GKNBTG44DGZTDMU4TAMJTMI/"

    def test_actual_social_reunion_is_rejected_even_with_forged_ai_metadata(self):
        title = '공효진, 케빈오 두고 전남편 만났다.."우리 한잔했어"'
        body = ("배우 공효진이 전남편과 음주 회동을 인증했다.\n"
                "공효진은 3일 자신의 SNS에 별다른 설명 없이 짧은 영상을 게재했다.\n"
                "공개된 영상에는 밤거리를 걷고 있는 공효진과 정준원의 모습이 담겨 있었다.")
        item = {**alert(title, body), "link": self.SOURCE_URL,
                "source": "오픈AI·브로드컴 자체 AI칩·HBM", "sectors": ["반도체/AI"],
                "market_materiality": {"disposition": "keep", "priority": 3, "axes": ["earnings"]}}
        audit = radar.source_market_materiality(item)
        self.assertEqual(audit["reason"], "private_life_without_business_change")
        self.assertFalse(audit["evidence"])
        self.assertTrue(radar.is_nonmarket_business_event(item))
        self.assertIsNone(radar.build_verified_korean_business_alert({**item, "title": title}, NOW))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([item], 7), [])

    def test_entertainment_section_needs_a_headline_market_event_not_meeting_words(self):
        title = "다시 만난 두 배우, 영상 공개"
        body = "두 배우는 고객 초청 행사에서 회동했다. 두 사람의 영상이 공개됐다."
        audit = materiality.assess(title, body, source_url=self.SOURCE_URL)
        self.assertEqual(audit["reason"], "entertainment_without_headline_market_event")
        self.assertFalse(audit["evidence"])

    def test_incidental_quarter_and_connection_words_are_not_business_exceptions(self):
        title = "새 분기에도 연결된 배우들의 만남"
        body = "두 배우는 SNS에 인증 사진을 공개했다. 소속사의 지난해 영업이익은 증가했다."
        audit = materiality.assess(title, body, source_url=self.SOURCE_URL)
        self.assertEqual(audit["disposition"], "exclude", audit)
        self.assertEqual(audit["priority"], 0)

    def test_social_proof_is_not_a_customer_discussion_in_any_source(self):
        for sentence in (
            "대표는 고객과 술자리 회동을 인증했다.",
            "공급사 대표가 친분을 드러내는 회동 인증 사진을 공개했다.",
            "The customer posted photos of a drinking reunion after the meeting.",
        ):
            self.assertFalse(materiality.evidence_is_new_event("customer_discussions", sentence), sentence)
        audit = materiality.assess("대표, 고객과 회동 인증", "대표는 고객과 회동을 인증했다.")
        self.assertFalse(audit["evidence"], audit)

    def test_customer_certification_alone_is_not_a_business_meeting_topic(self):
        audit = materiality.assess("대표, 만남 인증", "대표는 회동을 인증했다.")
        self.assertNotEqual(audit["disposition"], "keep", audit)
        self.assertTrue(materiality.evidence_is_new_event(
            "customer_discussions", "고객사는 HBM 공급과 공동 개발 방안을 논의했다.",
        ))

    def test_technical_customer_certification_is_not_a_private_life_photo(self):
        title = "반도체기업, HBM 고객 인증 완료"
        body = ("반도체기업은 데이터센터 공급용 HBM 고객 인증을 완료했다. "
                "검증팀은 제품 인증 사진을 공개했다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep", audit)
        self.assertTrue(any(item["kind"] == "technology_or_clinical_stage" for item in audit["evidence"]))

    def test_entertainment_company_earnings_and_insider_trades_remain_eligible(self):
        for title, body in (
            ("하이브, 3분기 영업이익 30% 증가", "하이브는 3분기 영업이익이 전년비 30% 증가했다고 발표했다."),
            ("JYP 박진영, 회사 주식 50억원 매수", "JYP 박진영 대표는 회사 주식 50억원을 매수했다고 공시했다."),
            ("YG, 자사주 200억원 매입 결정", "YG는 200억원 규모 자사주 매입을 결정했다고 공시했다."),
        ):
            item = {**alert(title, body), "link": self.SOURCE_URL}
            audit = radar.source_market_materiality(item)
            self.assertEqual(audit["disposition"], "keep", audit)
            self.assertGreaterEqual(audit["priority"], 2)
            self.assertFalse(radar.is_nonmarket_business_event(item))
            row = {**item, "title": title, "publisher": "조선비즈", "published": NOW}
            built = radar.build_verified_korean_business_alert(row, NOW)
            self.assertIsNotNone(built, title)
            with patch.object(radar.base, "kst_now", return_value=NOW):
                self.assertEqual(len(radar.quality_display_alerts([built], 7)), 1, built)

    def test_scoped_customer_supply_talks_are_not_blocked_by_meeting_photos(self):
        title = "반도체기업, 고객과 HBM 공급 논의"
        body = "반도체기업 대표는 고객과 HBM 공급 협상을 논의하고 회동 사진을 공개했다."
        self.assertTrue(materiality.evidence_is_new_event("customer_discussions", body))
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep", audit)
        self.assertTrue(any(item["kind"] == "customer_discussions" for item in audit["evidence"]))

    def test_entertainment_url_guard_uses_path_not_query_text(self):
        title = "기업 대표, 고객사와 회동"
        for url in (
            "https://www.yna.co.kr/view/article?redirect=/entertainment/",
            "https://www.etnews.com/news/article#entertainment/",
            "https://www.yna.co.kr/view/entertainment-fixture",
        ):
            self.assertEqual(materiality.nonmarket_entertainment_reason(title, source_url=url), "")
        self.assertEqual(materiality.nonmarket_entertainment_reason(title, source_url=self.SOURCE_URL),
                         "entertainment_without_headline_market_event")


class MaterialityChecks(unittest.TestCase):
    def test_combined_vehicle_sales_mix_does_not_become_one_issuer_decline(self):
        title = "'내연기관 시대 저문다'…현대차·기아, 국내 판매 2대 중 1대 '친환경'"
        body = ("올해 현대자동차와 기아가 국내에서 판매한 차량 2대 중 1대는 친환경차인 것으로 나타났다.\n"
                "3일 뉴시스가 현대차와 기아의 차종별 판매 실적을 분석한 결과 양사의 1~9월 국내 판매량 "
                "88만4482대 중 하이브리드·전기차·수소차는 43만9587대로 49.7%를 차지했다. "
                "전년 동기 39.4%보다 10.3%포인트 높아졌다.\n"
                "현대차는 노조 파업에 따른 생산 차질과 신차 대기 수요 등으로 내수 판매가 16.3% 줄면서 "
                "하이브리드도 11만9522대로 12.2% 감소했다.")
        core = radar.detailed_article_core(title, body)
        for fact in ("현대차·기아", "1~9월", "국내 친환경차", "43만9587대", "전체 판매의 49.7%", "10.3%포인트"):
            self.assertIn(fact, core)
        self.assertNotIn("16.3%", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertLessEqual(len(core), 100)
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])
        wrong_core = "현대차는 노조 파업에 따른 생산 차질과 신차 대기 수요 등으로 내수 판매가 16.3% 줄면서 하이브리드도 11만9522대로 12.2% 감소했다."
        self.assertFalse(materiality.core_focus_aligned(title, wrong_core))
        self.assertIn("combined_sales_population_or_mix_mismatch", radar.source_core_fact_errors(
            {**alert(title, body), "telegram_core_fact": wrong_core},
        ))
        for mismatched in (core.replace("현대차·기아", "현대차"), core.replace("49.7%", "45.7%"), core.replace("1~9월", "9월")):
            self.assertIn("combined_sales_population_or_mix_mismatch", radar.source_core_fact_errors(
                {**alert(title, body), "telegram_core_fact": mismatched},
            ))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([alert(title, body)], 7)), 1)
        variant = title.replace("현대차·기아", "제조사A·제조사B")
        source = body.replace("현대자동차", "제조사A").replace("현대차", "제조사A").replace("기아", "제조사B")
        self.assertIn("제조사A·제조사B", radar.detailed_article_core(variant, source))

    def test_observed_same_period_loss_keeps_attribution_and_revenue_change(self):
        title = "돼지는 적자 닭은 방어…원스식품 실적 바닥 통과하나"
        body = ("원스식품은 올 상반기 매출 467억4700만위안(약 9조3600억원)으로 전년 동기 대비 6.23% 감소했다. "
                "모회사 귀속 순손실은 43억6600만위안으로 지난해 같은 기간 34억7500만위안 흑자에서 적자로 전환했다. "
                "특히 올 2분기에만 32억9600만위안의 순손실을 냈다.")
        core = radar.detailed_article_core(title, body)
        for fact in ("원스식품", "상반기", "6.23% 감소", "모회사 귀속 순손실", "43억6600만위안", "적자 전환"):
            self.assertIn(fact, core)
        self.assertNotIn("2분기", core)
        self.assertNotIn("32억", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])
        for incomplete in ("원스식품은 상반기 매출이 전년비 6.23% 감소했다.", core.replace("모회사 귀속 ", "")):
            self.assertIn("observed_loss_or_accounting_basis_omitted", radar.source_core_fact_errors(
                {**alert(title, body), "telegram_core_fact": incomplete},
            ))
        self.assertIn("observed_loss_amount_mismatch", radar.source_core_fact_errors(
            {**alert(title, body), "telegram_core_fact": core.replace("43억6600만위안", "32억9600만위안")},
        ))
        item = {**alert(title, body), "telegram_core_fact": core}
        item["fx_conversion"] = radar.build_alert_fx_conversion(
            item, {"rates": {"CNY": {"value": 201.1, "status": "fixture", "source": "unit test"}}}, NOW,
        )
        rendered = radar.compact_converted_core(core, item["fx_conversion"], 100)
        self.assertIn("모회사 귀속 순손실", rendered)
        self.assertIn("적자 전환", rendered)
        self.assertIn("약 8,780억원", rendered)
        self.assertTrue(radar.core_sentence_is_complete(rendered))
        self.assertLessEqual(len(rendered), 100)
        block = radar.compact_alert(item, 1, NOW, {}, {})
        self.assertIn(rendered, block)
        self.assertEqual(radar.compact_alert_block_errors(block), [])
        uncertain = body.replace("적자로 전환했다", "적자로 전환할 전망이다")
        self.assertEqual(radar.profit_loss_result_fact(title, materiality.source_sentences(uncertain)), "")

    def test_actual_food_price_release_keeps_published_index_not_general_cause(self):
        title = "세계식량가격 석 달째 상승…설탕 6.1%·곡물 5.1%↑"
        body = ("세계식량가격이 3개월 연속 상승했다. 흑해 지역의 물류 차질과 주요 생산국의 작황 우려로 "
                "곡물·설탕 가격이 오르면서 전체 지수를 끌어올렸다.\n"
                "농림축산식품부는 3일 유엔 식량농업기구(FAO)의 9월 세계식량가격지수가 136.0으로 "
                "전월보다 1.5% 상승했다고 밝혔다. 지난해 같은 달과 비교하면 5.8% 높다.\n"
                "지수는 지난 6월 130.1에서 7월 131.7, 8월 134.0, 9월 136.0으로 석 달째 상승했다.")
        core = radar.detailed_article_core(title, body)
        for fact in ("FAO", "9월", "136.0", "전월보다 1.5%", "상승"):
            self.assertIn(fact, core)
        self.assertNotIn("흑해", core)
        self.assertNotIn("6.1%", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertLessEqual(len(core), 100)
        self.assertEqual(materiality.assess(title, body)["disposition"], "keep")
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])

    def test_actual_retail_fuel_core_keeps_product_period_price_and_comparison(self):
        title = "전국 주유소 기름값 20주 연속 하락…휘발유 L당 1857원"
        body = ("휘발유 전주보다 0.4원↓…서울 1904원·대구 1829.8원\n"
                "전국 주유소 기름값이 소폭 내리며 20주 연속 하락세를 이어갔다.\n"
                "3일 한국석유공사 유가정보시스템 오피넷에 따르면 9월 다섯째 주(9월 27일~10월 1일) "
                "전국 주유소 휘발유 평균 판매가격은 리터(L)당 1857.6원으로 전주보다 0.4원 내렸다.\n"
                "전국 주유소의 경유 평균 판매가격도 하락세를 이어갔다.\n"
                "경유는 전주보다 L당 0.1원 내린 1843.3원을 기록했다.\n"
                "정부는 석유 최고가격제를 유지하고 있다.")
        core = radar.detailed_article_core(title, body)
        self.assertEqual(core, "9월 다섯째 주 전국 휘발유 평균 판매가격은 L당 1857.6원으로 전주보다 0.4원 하락했다.")
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertTrue(materiality.core_focus_aligned(title, core))
        self.assertFalse(materiality.core_focus_aligned(title, "전국 주유소의 경유 평균 판매가격도 하락세를 이어갔다."))
        self.assertLessEqual(len(core), 100)
        assessed = materiality.assess(title, body)
        self.assertEqual(assessed["reason"], "routine_weekly_retail_fuel_move_below_one_percent", assessed)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])

    def test_material_retail_fuel_price_change_is_not_silenced(self):
        for product, price in (("휘발유", "1957.6"), ("경유", "1943.3")):
            title = f"전국 주유소 {product} 급등…L당 {price}원"
            body = f"9월 다섯째 주 전국 주유소 {product} 평균 판매가격은 L당 {price}원으로 전주보다 100원 올랐다."
            self.assertEqual(materiality.assess(title, body)["disposition"], "keep")
            core = radar.detailed_article_core(title, body)
            for fact in (product, price, "100원 상승했다"):
                self.assertIn(fact, core)
            self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])

    def test_actual_breadth_article_is_not_a_hyperscaler_capex_event(self):
        title = "고금리·고유가에도 AI주는 웃었다…S&P500 종목 80%는 하락"
        body = (title + "\n등록 2026.10.03 22:00:00 수정 2026.10.03 23:34:24\n"
                "지난 9월 기술주 중심의 나스닥100지수는 3% 올랐지만, S&P500 구성 종목의 약 80%는 하락했다.\n"
                "종목별 평균 하락률은 5%에 달했다.\n"
                "AI 투자에 자금이 몰렸다. 메타와 알파벳이 상승했다. 미국 국채금리는 4.7%에서 5.3%로 뛰었다.")
        item = {**alert(title, body), "link": "https://www.newsis.com/view/NISX20261003_0003813673",
                "published": "2026-10-03T23:34:24+09:00", "supply_chain_theme": "hyperscaler_ai_capex:2026-10-03"}
        identity = materiality.source_event_identity(item)
        self.assertEqual(identity, "source_event:v1:market_breadth:s&p500:2026-09:down_share=80")
        canonical = radar.normalize_alert_for_output(item)
        self.assertEqual(canonical["supply_chain_theme"], identity)
        self.assertEqual(radar.alert_dedup_key(item), (identity, "event"))
        row = {**item, "title": title, "published": NOW, "source": "뉴시스"}
        self.assertIsNone(radar.build_hyperscaler_ai_capex_alert(row, NOW, body.lower()))
        built = radar.build_verified_korean_business_alert(row, NOW)
        self.assertIsNotNone(built)
        self.assertEqual(materiality.focus_kind(built["source_title"]), "breadth")
        self.assertNotEqual(built.get("korean_business_kind"), "hyperscaler_ai_capex")
        self.assertTrue(materiality.core_focus_aligned(title, radar.verified_alert_core(built, title)))

    def test_breadth_duplicate_identity_preserves_population_period_and_changed_measure(self):
        title = "S&P500 종목 80%는 하락…AI주 쏠림"
        body = "2026년 9월 S&P500 구성 종목의 약 80%는 하락했다."
        first = alert(title, body)
        repeated = {**first, "news": "상승 종목 쏠림…S&P500 대부분은 하락", "source_title": "상승 종목 쏠림…S&P500 대부분은 하락",
                    "link": "https://www.etoday.co.kr/news/view/other-breadth", "published": "2026-10-04T01:30:00+09:00"}
        identity = materiality.source_event_identity(first)
        self.assertEqual(identity, materiality.source_event_identity(repeated))
        for changed in (
            {**first, "source_body": body.replace("80%", "75%")},
            {**first, "source_body": body.replace("9월", "8월")},
            {**first, "source_body": body.replace("2026년", "2025년")},
            {**first, "source_body": body.replace("S&P500", "코스피")},
            {**first, "source_body": body.replace("하락", "상승")},
        ):
            self.assertNotEqual(identity, materiality.source_event_identity(changed), changed)
        self.assertEqual(materiality.source_event_identity({**first, "body_verified": False}), "")
        self.assertEqual(materiality.source_event_identity({**first, "source_body": body.replace("2026년 9월 ", "")}), "")
        subset = {**first, "source_body": "2026년 9월 S&P500 상위 100개 종목 중 80%는 하락했다."}
        self.assertEqual(materiality.source_event_identity(subset), "")
        state = {"seen": {}}
        with patch.object(radar.telegram, "load_seen_state", return_value=state), \
                patch.object(radar.telegram, "save_seen_state", side_effect=lambda *_args: None):
            radar.telegram.record_seen_alerts([first], NOW)
            fresh, skipped = radar.telegram.filter_previously_seen_alerts([repeated], NOW, "live")
            revised = {**repeated, "source_body": body.replace("80%", "75%")}
            changed, _ = radar.telegram.filter_previously_seen_alerts([revised], NOW, "live")
        self.assertEqual(fresh, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(len(changed), 1)

    def test_unrelated_legacy_sector_key_cannot_hide_source_verified_breadth(self):
        title = "고금리·고유가에도 AI주는 웃었다…S&P500 종목 80%는 하락"
        body = "지난 9월 나스닥100지수는 3% 올랐지만, S&P500 구성 종목의 약 80%는 하락했다."
        item = {**alert(title, body), "link": "https://www.newsis.com/view/NISX20261003_0003813673",
                "supply_chain_theme": "hyperscaler_ai_capex:2026-10-03"}
        entry = {"title": "부산대 작년 지역 생산유발 1.5조원, 일자리 창출 1.2만명",
                 "link": "https://www.newsis.com/view/NISX20261002_0003812256",
                 "first_seen_kst": NOW.isoformat(), "lanes": {"live": NOW.isoformat()}}
        coarse = "event:" + radar.telegram.digest_seen(item["supply_chain_theme"])
        state = {"seen": {coarse: entry}}
        radar.telegram.migrate_seen_title_aliases(state)
        with patch.object(radar.telegram, "load_seen_state", return_value=state):
            fresh, skipped = radar.telegram.filter_previously_seen_alerts([item], NOW, "live")
        self.assertEqual(len(fresh), 1)
        self.assertEqual(skipped, [])
        self.assertIn(coarse, state["seen"])
        # Historical exact-article receipts remain effective without wiping state.
        state["seen"]["link:" + radar.telegram.digest_seen(item["link"])] = {**entry, "title": title, "link": item["link"]}
        with patch.object(radar.telegram, "load_seen_state", return_value=state):
            exact, repeated = radar.telegram.filter_previously_seen_alerts([item], NOW, "live")
        self.assertEqual(exact, [])
        self.assertEqual(len(repeated), 1)

    def test_article_series_introduction_and_license_noun_are_not_policy_changes(self):
        title = "한국 바람에 20년 투자, 외국 투자자는 무엇을 보나 [지평 기후에너지리포트]"
        introduction = "[지평 기후에너지리포트]에서는 기후에너지환경 분야 정책 변화부터 사업개발, 투자, 인허가, 분쟁까지 주요 법률 이슈를 짚고, 기업이 알아야 할 핵심 정보를 전달하고자 합니다."
        body = "해상풍력 크로스보더 투자의 법률 이슈. 해상풍력특별법이 지난 3월 시행됐다. 외국 투자자는 제도의 안정성을 살핀다.\n" + introduction
        self.assertFalse(materiality.evidence_is_new_event("policy_scope_or_stage", introduction))
        self.assertLess(materiality.assess(title, body)["priority"], 2)
        self.assertNotIn("policy_scope_or_stage", [row["kind"] for row in materiality.assess("기업, 사업 절차 소개", "회사는 인허가 절차와 관련 규제 정보를 제공한다.")["evidence"]])
        for action in ("허가했다", "승인했다", "허가를 내줬다"):
            changed = materiality.assess("정부, 신규 공장 인허가", f"정부는 신규 반도체 공장 건설을 {action}.")
            self.assertEqual(changed["disposition"], "keep", changed)

    def test_boycott_article_cannot_borrow_late_company_revenue_forecast(self):
        title = "JYP, 중대 결정...파격 '보이콧' 선언"
        body = ("방탄소년단에 이어 스트레이 키즈도 그래미 시상식 보이콧에 나섰다.\n"
                "JYP엔터테인먼트는 내년 그래미 시상식에 음악을 출품하지 않았다고 밝혔다.\n"
                "그래미는 아시안 팝 부문 시상을 강행하겠다고 발표했다.\n"
                "스트레이 키즈는 빌보드 200에서 9차례 1위를 기록했다.\n"
                "스트레이 키즈는 JYP의 실적 효자이기도 하다.\n"
                "최근 SK증권은 스트레이 키즈의 활약에 힘입어 JYP엔터테인먼트의 2026년 매출액을 8665억원으로 전망했다.")
        self.assertLess(materiality.assess(title, body)["priority"], 2)
        item = {**alert(title, body), "link": "https://magazine.hankyung.com/business/article/202610031631b"}
        wrong_core = "최근 SK증권은 스트레이 키즈의 활약에 힘입어 JYP엔터테인먼트의 2026년 매출액을 8665억원으로 전망했다."
        self.assertIn("article_without_headline_market_change_evidence", radar.source_core_fact_errors({**item, "telegram_core_fact": wrong_core}))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([item], 7), [])
        actual = materiality.assess("JYP, 공연 취소로 매출 가이던스 하향", "JYP엔터테인먼트는 공연 취소로 매출 가이던스를 10% 하향했다.")
        self.assertEqual(actual["disposition"], "keep")

    def test_actual_asset_purchase_core_keeps_object_price_and_unclosed_stage(self):
        title = "나노 뉴클리어 에너지, NRC 인허가 핵연료 자산 1350만 달러 인수"
        body = ("나노 뉴클리어 에너지(NNE)가 자회사 HALEU 에너지 퓨얼과 함께 라드노스틱스 및 자회사로부터 "
                "미국 원자력규제위원회(NRC) 인허가와 관련 지식재산권·기술 자료 등 핵연료 처리 자산을 "
                "현금 950만 달러와 자사 보통주 400만 달러어치 등 총 1350만 달러에 인수하는 확정 자산매입계약을 체결했다고 2일 발표했다.\n"
                "다만 해당 인허가에 따른 시설은 실제로 건설되지 않았다.\n"
                "이번 거래는 우라늄 전환, 농축, 탈전환, 운송에서 원자로 배치까지 아우르는 수직계열화된 첨단 원자력 에너지·연료 플랫폼 구축이라는 회사의 장기 전략의 일환이다.\n"
                "종결은 NRC의 인허가 이전 동의, 뉴멕시코주 당국을 포함한 기타 필수 승인·동의, 부지 관련 조건 충족을 전제로 한다.")
        item = {**alert(title, body), "link": "https://www.mk.co.kr/news/stock/12167665"}
        self.assertEqual(materiality.focus_kind(title), "ownership")
        core = radar.verified_alert_core(item, title)
        for fact in ("나노 뉴클리어 에너지", "NRC 인허가", "핵연료 처리 자산", "1350만달러", "계약을 체결", "미건설", "종결에는 규제 승인"):
            self.assertIn(fact, core)
        self.assertNotRegex(core, "인수했다|인수 완료|시설을 가동|장기 전략")
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertFalse(materiality.core_focus_aligned(title, "이번 거래는 장기적인 수직계열화 전략의 일환이다."))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            built = radar.build_verified_korean_business_alert({**item, "published": NOW, "source": "매일경제"}, NOW)
            self.assertIsNotNone(built)
            self.assertEqual(len(radar.quality_display_alerts([built], 7)), 1)
        item["telegram_core_fact"] = core
        item["fx_conversion"] = radar.build_alert_fx_conversion(
            item, {"rates": {"USD": {"value": 1348.28, "status": "fixture", "source": "unit test"}}}, NOW,
        )
        block = radar.compact_alert(item, 1, NOW, {}, {})
        self.assertIn("1350만달러(약 182억원)", block)
        self.assertIn("규제 승인이 필요하다", block)
        self.assertEqual(radar.compact_alert_block_errors(block), [])
        renamed = body.replace("나노 뉴클리어 에너지", "새로운 원자력 기업").replace("1350만 달러", "1400만 달러")
        renamed_title = title.replace("나노 뉴클리어 에너지", "새로운 원자력 기업").replace("1350만 달러", "1400만 달러")
        renamed_core = radar.verified_alert_core(alert(renamed_title, renamed), renamed_title)
        self.assertIn("새로운 원자력 기업", renamed_core)
        self.assertIn("1400만달러", renamed_core)

    def test_actual_cloud_competency_definition_is_not_new_customer_negotiation(self):
        title = "SK쉴더스, AWS '위협탐지 및 대응' 컴피턴시 국내 첫 획득"
        body = ("SK쉴더스가 AWS의 위협 탐지 및 대응 컴피턴시를 획득했다.\n"
                "2일 SK쉴더스에 따르면, AWS 보안 컴피턴시는 AWS 환경에서 보안 솔루션과 서비스를 제공하는 "
                "AWS 파트너의 전문성과 고객 사례 등을 검토하는 프로그램이다.\n"
                "SK쉴더스는 심사 과정에서 AWS 보안 서비스를 활용해 고객 환경의 위협 탐지 및 대응 체계를 구축한 사례를 제출했다.\n"
                "앞으로 다양한 산업군으로 서비스 저변을 확대해 나갈 예정이다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "exclude", audit)
        self.assertFalse(materiality.evidence_is_new_event("customer_discussions", materiality.source_sentences(body)[1]))
        item = {**alert(title, body), "link": "https://zdnet.co.kr/view/?no=20261003212658"}
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([item], 7), [])
        actual_contract = body + "\nSK쉴더스는 신규 고객 공급계약을 체결했다."
        self.assertEqual(materiality.assess(title, actual_contract)["disposition"], "keep")
        self.assertEqual(materiality.assess(title, body + "\nSK쉴더스는 지난해 신규 고객 공급계약을 체결했다.")["disposition"], "exclude")
        self.assertTrue(materiality.evidence_is_new_event("customer_discussions", "회사는 고객과 신규 보안 장비 공급을 협상 중이다."))
        self.assertEqual(materiality.assess("제약기업, 신약 FDA 승인 획득", "제약기업은 신약 FDA 승인을 획득했다.")["disposition"], "keep")

    def test_hypothetical_household_interest_bill_is_not_a_new_mortgage_rate(self):
        title = '주담대 8% 되면…"5억 빌렸다면 이자만 매달 330만원"'
        body = ("주택담보대출 금리가 8%까지 오르면 5억원을 빌린 차주는 매달 330만원의 이자를 부담할 수 있다는 분석이 나왔다. "
                "현재 5대 은행의 금리 상단은 7%대이며 금리가 8% 수준까지 오를 경우 차주의 부담이 늘어날 수 있다고 말했다.")
        result = materiality.assess(title, body)
        self.assertEqual(result["disposition"], "exclude", result)
        self.assertEqual(result["reason"], "hypothetical_household_interest_calculation_not_new_rate", result)
        actual = materiality.assess("은행, 주담대 금리 상향", "은행은 주택담보대출 금리 상단을 7%에서 8%로 상향했다고 발표했다.")
        self.assertEqual(actual["disposition"], "keep", actual)

    def test_intern_reporter_byline_is_removed_before_core_ranking(self):
        source = "[서울=뉴시스]장인혜 인턴 기자 = 은행은 주택담보대출 금리 상단을 8%로 상향했다."
        core = radar.normalized_article_sentence(source)
        self.assertNotIn("장인혜", core)
        self.assertNotIn("기자", core)
        self.assertTrue(core.startswith("은행"), core)

    def test_us_market_close_dedup_uses_session_and_observed_level_across_publishers(self):
        first = {**alert("취업문 얼었는데 환호한 월가[뉴욕마감]",
                          "뉴욕증시 3대 지수가 2일(현지시간) 일제히 상승했다. 나스닥종합지수는 319.27포인트(1.19%) 오른 2만7190.86에 마감했다."),
                 "published": "2026-10-03T06:27+09:00"}
        second = {**alert("뉴욕증시, 美 고용 지표 소화하며 상승…나스닥 1.19%↑[상보]",
                           "25일(현지시간) 트레이더 사진. 뉴욕증시가 2일(현지시간) 상승했다. 나스닥지수는 319.27포인트(1.19%) 뛴 27190.86에 거래를 끝냈다."),
                  "published": "2026-10-03T06:47+09:00", "link": "https://www.etoday.co.kr/news/view/market-fixture"}
        identity = materiality.source_event_identity(first)
        self.assertEqual(identity, "source_event:v1:us:equity_close:2026-10-02:nasdaq=27190.86:change=1.19")
        self.assertEqual(identity, materiality.source_event_identity(second))
        changed_level = {**second, "source_body": second["source_body"].replace("27190.86", "27191.86")}
        self.assertNotEqual(identity, materiality.source_event_identity(changed_level))
        next_day = {**second, "source_body": second["source_body"].replace("2일(현지시간)", "3일(현지시간)"),
                    "published": "2026-10-04T06:47+09:00"}
        self.assertNotEqual(identity, materiality.source_event_identity(next_day))
        intraday = {**second, "source_body": second["source_body"].replace("거래를 끝냈다", "장중 거래되고 있다")}
        self.assertEqual(materiality.source_event_identity(intraday), "")
        state = {"seen": {}}
        seen_time = dt.datetime.fromisoformat("2026-10-04T07:00+09:00")
        with patch.dict("os.environ", {"RADAR_RUN_MODE": "live"}), \
                patch.object(radar.telegram, "load_seen_state", return_value=state), \
                patch.object(radar.telegram, "save_seen_state", side_effect=lambda *_: None):
            radar.telegram.record_seen_alerts([first], seen_time)
            fresh, skipped = radar.telegram.filter_previously_seen_alerts([second, changed_level, next_day], seen_time, "live")
        self.assertEqual(len(skipped), 1)
        self.assertEqual(len(fresh), 2)

    def test_known_legacy_delivery_gets_verified_close_alias_without_new_sent_records(self):
        evidence = json.loads(radar.telegram.VERIFIED_EVENT_ALIAS_PATH.read_text(encoding="utf-8"))["entries"][0]
        receipt = {"title": evidence["source_title"], "link": evidence["link"],
                   "first_seen_kst": "2026-10-04T00:22:15+09:00", "lanes": {"live": "2026-10-04T00:22:15+09:00"}}
        state = {"seen": {"old-link": dict(receipt)}}
        radar.telegram.migrate_seen_verified_event_aliases(state)
        key = f"event:{radar.telegram.digest_seen(evidence['source_event_identity'])}"
        self.assertEqual(state["seen"][key]["first_seen_kst"], receipt["first_seen_kst"])
        self.assertEqual(state["seen"][key]["event_alias_evidence_message_id"], 2111)
        for name, value in receipt.items():
            self.assertEqual(state["seen"]["old-link"][name], value)
        self.assertEqual(state["seen"]["old-link"]["source_event_identity"], evidence["source_event_identity"])
        revised = {**alert(evidence["source_title"], "뉴욕증시가 2일(현지시간) 상승했다. 나스닥지수는 319.27포인트(1.19%) 뛴 27191.86에 거래를 끝냈다."),
                   "published": evidence["source_published_kst"], "link": evidence["link"]}
        with patch.object(radar.telegram, "load_seen_state", return_value=state):
            fresh, skipped = radar.telegram.filter_previously_seen_alerts([revised], dt.datetime.fromisoformat(receipt["first_seen_kst"]), "live")
        self.assertEqual(len(fresh), 1)
        self.assertEqual(len(skipped), 0)
        unrelated = {"seen": {"old-link": {**receipt, "link": "https://www.etoday.co.kr/news/view/other"}}}
        radar.telegram.migrate_seen_verified_event_aliases(unrelated)
        self.assertEqual(len(unrelated["seen"]), 1)

    def test_employment_market_core_supports_verified_close_sentence_variants(self):
        title = "뉴욕증시, 美 고용 지표 소화하며 상승…나스닥 1.19%↑[상보]"
        body = ("뉴욕증시가 2일(현지시간) 상승했다. "
                "나스닥지수는 319.27포인트(1.19%) 뛴 2만7190.86에 거래를 끝냈다. "
                "9월 비농업 부문 고용은 전월 대비 2만9000명 증가하는 데 그쳐 시장 예상치인 8만4000명 증가를 밑돌았다.")
        core = radar.detailed_article_core(title, body)
        for value in ("9월", "2만9000명", "8만4000명", "나스닥", "1.19%"):
            self.assertIn(value, core)
        self.assertTrue(radar.source_output_aligned({**alert(title, body), "telegram_core_fact": core}))

    def test_marine_industry_is_not_a_production_milestone(self):
        sentence = "해양산업에서 인공지능과 디지털 기술의 활용이 늘어나는 만큼 연구소도 다양한 연구를 추진하고 있다."
        self.assertFalse(materiality.evidence_is_new_event("technology_or_clinical_stage", sentence))
        self.assertNotEqual(materiality.assess("바다 안전 기술", sentence)["disposition"], "keep")
        self.assertEqual(materiality.assess("반도체 기술, 양산 시작", "기업은 검증한 반도체 기술의 양산을 시작했다.")["disposition"], "keep")

    def test_actual_agency_role_series_is_not_industry_breaking_news(self):
        title = "[해수분해] 가라앉는 배 탈출 '골든타임' 늘린다…바다 안전 기술"
        body = ("연합뉴스는 해양수산부와 소속 기관의 업무를 하나씩 '분해'해 살펴보는 기획 기사를 매주 송고합니다. "
                "해양산업에서 AI와 디지털 기술의 활용이 늘어 연구소도 다양한 연구를 추진하고 있다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "exclude", audit)
        self.assertEqual(audit["reason"], "agency_role_overview_not_new_industry_event", audit)

    def test_employment_driven_market_close_keeps_release_actual_forecast_and_index(self):
        title = "취업문 얼었는데 환호한 월가…엔비디아·AMD 줄줄이 최고치[뉴욕마감]"
        body = ("나스닥종합지수는 319.27포인트(1.19%) 오른 2만7190.86에 마감했다. "
                "미 노동부는 9월 미국의 비농업 일자리가 전달보다 2만9000명 증가했다고 발표했다. "
                "다우존스가 집계한 전문가 예상치 8만4000명의 3분의 1에도 못 미친다. 실업률도 4.2%로 전달보다 올랐다. "
                "엔비디아, 크라우드스트라이크, 팔로알토네트웍스, AMD가 줄줄이 장중 역대 최고가를 경신했다.")
        core = radar.detailed_article_core(title, body)
        for term in ("9월", "비농업", "2만9000명", "8만4000명", "1.19%", "나스닥"):
            self.assertIn(term, core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])
        audit = materiality.assess(title, body)
        self.assertEqual(audit["transmission_scope_rank"], 3, audit)
        row = {"title": title, "source_title": title, "source_body": body, "source_abstract": body,
               "body_verified": True, "link": "https://www.mt.co.kr/world/2026/10/01/macro-fixture",
               "publisher": "머니투데이", "source": "머니투데이", "published": NOW}
        with patch.object(radar.base, "kst_now", return_value=NOW):
            fresh = radar.build_verified_korean_business_alert(row, NOW)
            self.assertIsNotNone(fresh)
            selected = radar.quality_display_alerts([fresh], 1)
            self.assertEqual(len(selected), 1, fresh.get("_exclusion_reason"))
            self.assertIn("엔비디아·AMD", selected[0]["telegram_core_fact"])
            self.assertIn("장중 최고가", selected[0]["telegram_core_fact"])

    def test_macro_market_core_cannot_turn_a_falling_index_into_a_rising_close(self):
        title = "고용 부진에 뉴욕증시 하락[뉴욕마감]"
        body = ("나스닥종합지수는 319.27포인트(1.19%) 내린 2만7190.86에 마감했다. "
                "미 노동부는 9월 미국의 비농업 일자리가 전달보다 2만9000명 증가했다고 발표했다. "
                "다우존스가 집계한 전문가 예상치 8만4000명의 3분의 1에도 못 미친다.")
        core = radar.detailed_article_core(title, body)
        self.assertNotIn("상승 마감", core)
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])

    def test_macro_market_core_does_not_invent_a_company_record_from_a_forecast(self):
        title = "취업문 얼었는데 환호한 월가…엔비디아·AMD 줄줄이 최고치[뉴욕마감]"
        sentences = ["나스닥종합지수는 319.27포인트(1.19%) 오른 2만7190.86에 마감했다.",
                     "미 노동부는 9월 미국의 비농업 일자리가 전달보다 2만9000명 증가했다고 발표했다.",
                     "다우존스가 집계한 전문가 예상치 8만4000명의 3분의 1에도 못 미친다.",
                     "엔비디아와 AMD는 장중 최고가를 경신할 것으로 예상된다."]
        core = radar.source_focused_article_core(title, sentences)
        self.assertNotIn("장중 최고가를 경신했다", core)

    def test_past_fundraising_after_company_name_is_not_current_capital_event(self):
        past = "에이프릴바이오는 지난 6월 TKG휴켐스·IMM 측으로부터 3468억원 규모의 투자를 유치하면서 경영권을 TKG휴켐스에 넘겼다."
        self.assertFalse(materiality.evidence_is_new_event("capital_or_shareholder_action", past))
        self.assertFalse(materiality.evidence_is_new_event("insider_disclosed_trade", "대표는 지난 6월 주식 177만주를 매각했다."))
        self.assertFalse(materiality.evidence_is_new_event("commercial_order", "회사는 지난 6월 공급계약을 체결했다."))
        current = "바이오기업은 임상 연구를 위해 3468억원 규모의 신규 투자를 유치했다고 발표했다."
        self.assertTrue(materiality.evidence_is_new_event("capital_or_shareholder_action", current))
        self.assertEqual(materiality.assess("바이오기업, 신규 투자유치", current)["disposition"], "keep")

    def test_actual_person_profile_does_not_promote_old_control_transfer(self):
        title = "경영권 내려놓은 차상훈 대표 'APB-R3'로 'SAFA' 가치 증명할까[화제의 바이오人]"
        body = ("에이프릴바이오는 지난 6월 3468억원 규모의 투자를 유치하면서 경영권을 넘겼다. "
                "차 대표도 보유주식 177만주를 약 582억원에 매각했다. "
                "차 대표는 2013년 에이프릴바이오를 설립한 창업자다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "exclude", audit)
        self.assertEqual(audit["reason"], "person_profile_without_direct_new_business_event", audit)
        positive = materiality.assess("바이오기업, 임상 2상 결과 공개[화제의 바이오人]", "바이오기업은 신약의 임상 2상 결과를 공개했다.")
        self.assertEqual(positive["disposition"], "keep", positive)

    def test_copied_headline_is_not_independent_source_evidence(self):
        title = "기업, 신규 반도체 공급계약 100억원 체결"
        body = title + "\n회사는 반도체 분야의 전문 기업으로 알려져 있다."
        audit = materiality.assess(title, body)
        self.assertNotEqual(audit["disposition"], "keep", audit)
        self.assertEqual(audit["evidence"], [], audit)
        confirmed = body + "\n기업은 고객과 100억원 규모의 반도체 공급계약을 체결했다고 공시했다."
        audit = materiality.assess(title, confirmed)
        self.assertEqual(audit["disposition"], "keep", audit)
        self.assertTrue(all(row["source_excerpt"] != title for row in audit["evidence"]), audit)

    def test_new_source_environmental_approval_core_is_the_decision_not_recycling_plan(self):
        title = "고려아연 '프로젝트 크루서블' 美 환경평가 통과…친환경 제련소 구축 탄력"
        body = ("2일 업계에 따르면 미국 전쟁부는 지난달 11일(현지시간) 미국 국가환경정책법(NEPA)에 따라 프로젝트 크루서블의 최종 환경평가(Final EA)를 완료하고 '중대한 환경영향 없음(FONSI)' 결정을 내렸다.\n"
                "평가서에 따르면 고려아연은 연간 약 35만t의 주요 공정 잔재·부산물 가운데 약 96%인 33만5000t을 재활용할 계획이다.")
        item = {**alert(title, body), "telegram_core_fact": "고려아연은 공정 잔재 96%를 재활용할 계획이다."}
        core = radar.verified_alert_core(item, title)
        for term in ("미국 전쟁부", "지난달 11일", "크루서블", "최종 환경평가", "FONSI", "결정"):
            self.assertIn(term, core)
        self.assertNotIn("96%", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])

    def test_new_source_biology_research_core_keeps_benchmark_result_not_generic_clinical_background(self):
        title = "GC녹십자, 국내외 학회 참가해 독자 mRNA-LNP 플랫폼 연구 성과 공개"
        body = ("GC녹십자는 자체 플랫폼 연구 성과를 발표했다.\n"
                "회사는 자체 개발한 비번역영역(UTR) 서열과 폴리A 구조에 AI 기반 코돈 최적화 기술을 적용해 벤치마크 대비 단백질 번역 효율을 50% 이상 향상시켰다.\n"
                "GC녹십자의 독자 mRNA-LNP 플랫폼은 현재 임상 단계에서도 검증이 진행되고 있다.")
        item = {**alert(title, body), "telegram_core_fact": "GC녹십자의 독자 mRNA-LNP 플랫폼은 현재 임상 단계에서도 검증이 진행되고 있다."}
        core = radar.verified_alert_core(item, title)
        for term in ("GC녹십자", "코돈 최적화", "벤치마크", "단백질 번역 효율", "50% 이상"):
            self.assertIn(term, core)
        self.assertNotIn("임상", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])

    def test_actual_construction_spending_delivery_keeps_period_basis_and_change(self):
        title = "미국 8월 건설지출 0.9% 증가…비주거용이 견인"
        body = ("미국 부동산 시황을 파악할 수 있는 2026년 8월 건설지출은 연율 환산으로 전월 대비 0.9% 증가했다고 마켓워치와 RTT 뉴스, MSN이 2일 보도했다.\n"
                "공장 건설도 비주거용 건설 증가에 기여했다.")
        item = {**alert(title, body), "telegram_core_fact": "공장 건설도 비주거용 건설 증가에 기여했다."}
        core = radar.verified_alert_core(item, title)
        for term in ("미국", "8월", "건설지출", "연율", "전월 대비", "0.9%"):
            self.assertIn(term, core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertFalse(materiality.core_focus_aligned(title, item["telegram_core_fact"]))

    def test_actual_model_efficiency_delivery_uses_fourfold_token_change_not_background(self):
        title = "LGU+, AI 토큰 처리량 4배 높였다...GPU·전력 효율화"
        body = ("LG유플러스가 같은 GPU에서 AI가 처리할 수 있는 토큰량을 최대 4배까지 높이는 기술을 개발했다.\n"
                "AI 서비스 확대로 GPU와 전력 비용이 늘어나는 가운데 모델 성능을 유지하면서 인프라 운영비를 줄이는 기술 확보에 나선다.\n"
                "앞서 NPU에서 전력 소모를 78%, 모델 크기를 82% 줄였다.")
        item = {**alert(title, body), "telegram_core_fact": "AI 서비스 확대로 GPU와 전력 비용이 늘어나는 가운데 모델 성능을 유지하면서 인프라 운영비를 줄이는 기술 확보에 나선다."}
        core = radar.verified_alert_core(item, title)
        for term in ("LG유플러스", "GPU", "토큰량", "최대 4배"):
            self.assertIn(term, core)
        self.assertNotIn("78%", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])

    def test_actual_analyst_revision_delivery_does_not_use_old_customer_metric(self):
        title = "[美특징주]팔로알토, 수요 증가 전망·플랫폼 전략 ‘긍정적’ 평가…개장전 1%↑"
        body = ("TD코웬은 2일(현지 시간) 인공지능(AI) 확산에 따른 사이버보안 수요 증가와 플랫폼 전략의 성과를 반영해 팔로 알토 네트웍스(PANW)의 목표주가를 기존 400달러에서 440달러로 상향하고, 투자의견은 그대로 ‘매수’를 유지했다.\n"
                "플랫폼화 고객의 순매출유지율(NRR)은 120%를 기록했다.")
        item = {**alert(title, body), "telegram_core_fact": "플랫폼화 고객의 순매출유지율(NRR)은 120%를 기록했다."}
        core = radar.verified_alert_core(item, title)
        for term in ("TD코웬", "PANW", "목표주가", "400달러", "440달러", "상향"):
            self.assertIn(term, core)
        self.assertNotIn("120%", core)
        self.assertIn("440달러로", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertTrue(radar.source_output_aligned({**item, "telegram_core_fact": core}))

    def test_actual_labor_rejection_core_keeps_rejection_not_proposed_payments(self):
        title = "기본급 12만원 인상에도…HD현대重 임단협 합의안 부결"
        payment = "기본급 외에 산업전환 특별협약 체결 축하금 500만원, 생산성 향상 격려금 300만원을 지급하는 내용도 포함됐다."
        body = ("HD현대중공업 노사의 올해 임금·단체협약 잠정합의안이 조합원 찬반투표에서 부결됐다.\n"
                + payment + "\n이번 부결로 노사는 임금·복지 등 쟁점을 놓고 추가 교섭에 나설 것으로 보인다.")
        item = {**alert(title, body), "telegram_core_fact": payment}
        core = radar.verified_alert_core(item, title)
        self.assertIn("HD현대중공업", core)
        self.assertIn("부결", core)
        self.assertNotIn("500만원", core)
        self.assertFalse(materiality.core_focus_aligned(title, payment))
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertEqual({row["kind"] for row in materiality.assess(title, body)["evidence"]}, {"labor_cost_or_execution"})

    def test_actual_insider_trade_keeps_planned_share_count_not_photo_caption(self):
        title = '"최태원, 노소영에 9440억 현금으로 줘야"…결국 SK주식 판다'
        body = ("최태원 SK그룹 회장(왼쪽)과 노소영 아트센터 나비 관장_[연합뉴스 자료사진][이데일리 박민웅 기자] "
                "최태원 SK그룹 회장이 재산분할 소송 관련 개인 자금 마련을 위해 SK㈜ 지분 일부를 매각한다.\n"
                "SK㈜는 최대주주인 최 회장이 보유한 회사 주식 가운데 165만3924주를 매도하는 내용의 임원·주요주주 특정증권 등 거래계획보고서를 2일 공시했다.\n"
                "실제 거래는 공시 한 달 뒤 진행될 예정이다.")
        item = {**alert(title, body), "telegram_core_fact": body.split("\n")[0]}
        core = radar.verified_alert_core(item, title)
        for term in ("SK㈜", "165만3924주", "거래계획", "공시"):
            self.assertIn(term, core)
        self.assertNotIn("자료사진", core)
        self.assertNotIn("왼쪽", core)
        self.assertIn("최태원", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertTrue(radar.source_output_aligned({**item, "telegram_core_fact": core}))

    def test_concatenated_photo_prefix_is_removed_before_sentence_ranking(self):
        value = "회장(왼쪽)과 대표_[연합뉴스 자료사진][이데일리 기자] 기업이 지분 매각 계획을 공시했다."
        self.assertTrue(radar.core_has_ui_garbage(value))
        cleaned = radar.strip_core_ui_garbage(value)
        self.assertNotIn("왼쪽", cleaned)
        self.assertNotIn("자료사진", cleaned)
        self.assertIn("기업이 지분 매각 계획을 공시했다.", cleaned)

    def test_ai_exploration_catalog_is_not_customer_adoption(self):
        title = "해양산업 AI 전환 지원…해진공 AX 사이트 개통"
        body = ("한국해양진흥공사가 해운·항만·물류 기업의 AI 전환을 지원하기 위해 AI 체험 및 솔루션 카탈로그 서비스를 개시했다.\n"
                "이 서비스는 해양산업 실무자들이 현장 업무에서 적용할 수 있는 AI 기술을 체험해보고 자사에 필요한 솔루션과 공급 기업을 탐색할 수 있도록 지원한다.\n"
                "솔루션 카탈로그는 19개 사의 36개 솔루션을 분류했다.\n"
                "이용자들은 용선계약서 조항 검토와 터미널 추가 비용 산출을 미리 체험해 볼 수 있다.")
        self.assertNotEqual(materiality.assess(title, body)["disposition"], "keep")
        self.assertEqual(materiality.assess(title, body)["evidence"], [])
        real_contract = body + "\nAI 기업은 해운사와 AI 솔루션 공급 계약을 체결했다."
        self.assertEqual(materiality.assess(title, real_contract)["disposition"], "keep")

    def test_new_semiconductor_etf_launch_is_a_listing_stage_not_realized_inflow(self):
        title = "신한운용, 오는 7일 'SOL 글로벌DRAM반도체플러스' ETF 출시"
        body = "신한자산운용은 오는 7일 SOL 글로벌DRAM반도체플러스 ETF를 출시한다고 밝혔다."
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep")
        self.assertEqual(audit["evidence"][0]["kind"], "capital_listing_stage")
        self.assertEqual(audit["evidence"][0]["stage"], "early_signal")
        self.assertNotIn("market_price_or_flow", {row["kind"] for row in audit["evidence"]})
        self.assertFalse(materiality.evidence_is_new_event("capital_listing_stage", "반도체 ETF 시장이 성장하면서 지난해 자금 유입이 확대됐다."))
        self.assertFalse(materiality.evidence_is_new_event("market_price_or_flow", "연금 계좌에서도 글로벌 메모리 밸류체인에 투자할 수 있다."))

    def test_source_etf_listing_core_preserves_name_and_schedule_not_portfolio_description(self):
        title = "신한운용 'SOL 글로벌DRAM반도체플러스' ETF 7일 상장"
        body = ("신한자산운용은 2일 글로벌 메모리 반도체 핵심 기업과 장비 업체에 집중 투자하는 'SOL 글로벌DRAM반도체 플러스' 상장지수펀드(ETF)를 오는 7일 유가증권시장에 상장한다고 밝혔다.\n"
                "포트폴리오의 약 90%는 '메모리7' 기업으로 채운다.")
        item = {**alert(title, body), "telegram_core_fact": "포트폴리오의 약 90%는 '메모리7' 기업으로 채운다."}
        core = radar.verified_alert_core(item, title)
        for term in ("신한자산운용", "SOL", "7일", "유가증권시장", "상장한다고"):
            self.assertIn(term, core)
        self.assertNotIn("90%", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertTrue(radar.source_output_aligned({**item, "telegram_core_fact": core}))
        audit = materiality.assess(title, body)
        self.assertEqual(audit["evidence"][0]["kind"], "capital_listing_stage")
        self.assertNotIn("market_price_or_flow", {row["kind"] for row in audit["evidence"]})

    def test_orbital_test_core_keeps_actual_communication_result_not_purpose(self):
        title = "구글 AI칩 우주로 쐈다…‘우주 데이터센터’ 첫 실험"
        purpose = "이번 시험의 핵심은 고성능 AI 칩이 우주의 방사선과 온도 변화 속에서도 정상 작동하는지 확인하는 것이다."
        body = ("내년 TPU 위성 2대 연결, 레이저 통신으로 실험 사진 확대 플래닛랩스 시설에서 공개된 구글 시험 위성.\n"
                "구글은 발사 후 위성과 교신하는 데 성공했으며 위성이 정상 작동하고 있다고 밝혔다.\n" + purpose)
        item = {**alert(title, body), "telegram_core_fact": purpose}
        core = radar.verified_alert_core(item, title)
        for term in ("구글", "교신", "성공", "정상 작동"):
            self.assertIn(term, core)
        self.assertNotIn("확인하는 것이다", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertTrue(radar.source_output_aligned({**item, "telegram_core_fact": core}))
        self.assertNotIn("사진 확대", str(materiality.assess(title, body)["evidence"]))

    def test_photo_expansion_caption_alone_does_not_establish_space_milestone(self):
        title = "구글 우주 데이터센터 첫 실험"
        body = "내년 TPU 위성 2대 연결, 레이저 통신으로 실험 사진 확대 플래닛랩스 시설에서 공개된 구글 시험 위성."
        self.assertNotEqual(materiality.assess(title, body)["disposition"], "keep")
        self.assertEqual(materiality.assess(title, body)["evidence"], [])

    def test_country_representative_appointment_does_not_promote_supply_history(self):
        title = "스웨덴 방산기업 사브, 스테판 엥스트룀 한국 대표 선임"
        history = "사브는 한국에서 20여년간 첨단 센서, 레이더, 전자전 등 부체계와 기술을 공급하며 국내 방산업체와 협력해왔다."
        body = "사브가 신임 대표이사를 선임했다.\n" + history
        self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
        self.assertEqual(materiality.assess(title, body)["reason"], "staff_appointment_without_market_change")
        self.assertEqual(materiality.assess("사브, 한국 방산기업과 협력", history)["evidence"], [])
        real_change = "사브가 신임 대표이사를 선임했다. 새 대표는 분기 매출 가이던스를 15% 상향한다고 밝혔다."
        self.assertEqual(materiality.assess(title, real_change)["disposition"], "keep")

    def test_etf_product_name_is_not_new_listing_evidence(self):
        title = 'ETF 27종 토큰화…"진짜 경쟁은 유통시장"'
        body = "토큰화 시장은 국채와 머니마켓펀드(MMF)를 넘어 주식·상장지수펀드(ETF), 사모대출 등으로 빠르게 확장되고 있다."
        audit = materiality.assess(title, body)
        self.assertLess(audit["priority"], 2)
        self.assertNotIn("timeline", audit["axes"])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])
        real_listing = materiality.assess("신규 ETN 상장 예정", "새 ETN은 오는 7일 상장한다고 밝혔다.")
        self.assertEqual(real_listing["disposition"], "keep")
        self.assertGreaterEqual(real_listing["priority"], 2)

    def test_memory_price_research_preserves_ranges_and_forecast_status(self):
        title = 'KB증권 "4분기 메모리 가격 두자릿수 상승…가속구간 진입"'
        body = (
            "KB증권은 4분기 메모리 가격 상승을 분석했다. "
            '김동원 본부장은 트렌드포스를 인용해 "4분기 범용 D램 가격은 전 분기 대비 10∼15%, '
            '낸드(NAND) 가격은 15∼20% 추가 상승하며 두 자릿수 상승세를 이어갈 전망"이라고 짚었다.'
        )
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for term in ("KB증권", "트렌드포스", "4분기", "전분기 대비", "10∼15%", "15∼20%", "전망"):
            self.assertIn(term, core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 7)), 1)

    def test_lng_cost_comparison_is_research_not_new_capital_commitment(self):
        title = '로이터 "알래스카 LNG 사업비, 멕시코만 연안의 두배"'
        body = (
            "알래스카 액화천연가스(LNG) 사업의 비용이 미국 멕시코만 연안 LNG 사업의 두 배를 넘는다고 로이터 통신이 보도했다. "
            "글렌판은 이 사업 비용을 445억∼545억달러로 추산했다."
        )
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        self.assertIn("알래스카 LNG 사업비", core)
        self.assertIn("멕시코만 연안", core)
        self.assertIn("두 배", core)
        self.assertIn("로이터", core)
        self.assertNotRegex(core, "투자했다|집행했다|계약했다")
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 7)), 1)
        opinion = materiality.assess("LNG 사업비 부담", "LNG 사업비 부담이 크다고 지적했다.")
        self.assertEqual(opinion["evidence"], [])

    def test_middle_east_military_reinforcement_is_not_excluded_by_oil_token_gate(self):
        title = "미국 항모·1만병력 중동 추가 파견"
        body = "미국은 중동에 항공모함과 병력 1만명을 추가 파견했다. 병력은 11월 말 도착할 예정이다."
        item = alert(title, body)
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep")
        self.assertGreaterEqual(audit["priority"], 2)
        self.assertIn("discount_rate", audit["axes"])
        core = radar.verified_alert_core(item, title)
        self.assertIn("추가 파견", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 7)), 1)

    def test_earnings_abbreviation_remains_primary_ahead_of_secondary_analyst_revision(self):
        title = "HL디앤아이한라, 상반기 영업익 34%↑…증권가도 목표주가 상향"
        self.assertEqual(materiality.focus_kind(title), "earnings")
        body = "HL D&I한라의 상반기 연결 기준 매출은 8302억원, 영업이익은 455억원으로 전년비 각각 13.5%, 34.1% 증가했다."
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        self.assertIn("455억원", core)
        self.assertIn("34.1%", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])

    def test_actual_investment_explainer_and_routine_security_certificate_are_not_core_news(self):
        rows = (
            ("행동주의 따라 투자하면 돈 벌까", "행동주의 펀드의 지분 취득이 알려지면 주가가 뛰기도 한다. 2014년부터 2026년까지 국내 사례를 분석했다."),
            ("문서 AI 플랫폼, KISA 클라우드 보안인증 획득", "업체는 그동안 공공기관에 구축형으로 AI를 공급했지만 이제 클라우드 형태로도 제공할 수 있게 됐다."),
        )
        for title, body in rows:
            self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
        positive = materiality.assess("보안인증 획득 후 신규 공급계약 체결", "회사는 보안인증 획득 후 신규 고객 공급계약을 체결했다.")
        self.assertEqual(positive["disposition"], "keep")

    def test_actual_export_delivery_uses_statistics_not_regulator_aspiration(self):
        title = "K-뷰티 수출 1위, 중국 아닌 ‘이 나라’였다"
        body = ("올해 1~3분기 수출액 111억 달러\n"
                "2일 식품의약품안전처에 따르면 1~3분기 화장품 수출액은 전년 동기 대비 31.1% 증가한 111억달러(15조원)를 기록했다.\n"
                "국가별로는 23억5000만달러로 미국이 1위를 기록했다.\n"
                "식약처 관계자는 ‘K-뷰티의 위상이 더 높아질 수 있도록 규제기관 간 협력을 강화할 것’이라며 ‘국가별 규제정보 제공, 할랄 인증 컨설팅 지원 등을 추진하겠다’고 말했다.")
        item = {**alert(title, body), "link": "https://biz.heraldcorp.com/article/10892265",
                "telegram_core_fact": "식약처 관계자는 국가별 규제정보 제공, 할랄 인증 컨설팅 지원 등을 추진하겠다고 말했다."}
        core = radar.verified_alert_core(item, title)
        for term in ("1~3분기", "화장품 수출액", "31.1%", "111억달러", "미국", "1위"):
            self.assertIn(term, core)
        self.assertNotIn("컨설팅", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertFalse(materiality.core_focus_aligned(title, item["telegram_core_fact"]))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 7)), 1, item.get("_exclusion_reason"))

    def test_export_results_need_source_quantity_and_do_not_reclassify_export_bans(self):
        for title, body in (
            ("화장품 수출액 증가 기대", "관계자는 화장품 수출액 증가를 기대하며 협력을 강화하겠다고 말했다."),
            ("수출 컨설팅 지원 확대", "기관은 수출 컨설팅 지원을 확대하겠다고 말했다."),
        ):
            audit = materiality.assess(title, body)
            self.assertNotIn("export_results", [item["kind"] for item in audit["evidence"]])
        self.assertNotEqual(materiality.focus_kind("트럼프, 디젤 수출 금지 경고"), "export_results")

    def test_new_source_ai_financing_core_keeps_agreement_amount_and_reporting_attribution(self):
        title = "AI 속도조절론에도 대규모 자금 투입 '가속'"
        body = ("AI 모델 개발회사를 향한 대규모 자금 투입이 이어지고 있다.\n"
                "로이터통신은 앤트로픽의 비공개 기업공개(IPO) 서류를 인용해 앤트로픽이 브로드컴으로부터 최대 420억달러(약 57조원) 규모의 대출을 받기로 합의했다고 1일(현지시간) 보도했다.\n"
                "오픈AI는 이와 별개로 신규 자금조달을 추진하고 있다.")
        item = {**alert(title, body), "link": "https://www.hankyung.com/article/2026100208801"}
        core = radar.verified_alert_core(item, title)
        for term in ("로이터통신", "앤트로픽", "브로드컴", "최대 420억달러", "합의했다고", "보도했다"):
            self.assertIn(term, core)
        self.assertNotIn("오픈AI", core)
        self.assertNotIn("대출을 받았다", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 7)), 1, item.get("_exclusion_reason"))
        for wrong in (core.replace("앤트로픽", "다른기업"), core.replace("420억달러", "500억달러")):
            self.assertFalse(radar.source_output_aligned({**item, "telegram_core_fact": wrong}))
        item["telegram_core_fact"] = core
        item["fx_conversion"] = radar.build_alert_fx_conversion(
            item, {"rates": {"USD": {"value": 1421, "status": "fixture", "source": "unit test"}}}, NOW,
        )
        block = radar.compact_alert(item, 1, NOW, {}, {})
        self.assertIn("420억달러(약 60조원)", block)
        self.assertEqual(radar.compact_alert_block_errors(block), [])

    def test_new_source_ai_infrastructure_core_recovers_change_not_old_revenue_level(self):
        title = "앤트로픽, 초고속 성장 속 인프라 지출 계획"
        body = ("앤트로픽의 비공개 IPO 투자설명서 내용 기반 언론 보도가 이어지고 있다.\n"
                "앤트로픽의 2025년 매출은 45.9억달러로 전년 대비 1088% 초고성장하고 있다.\n"
                "앤트로픽은 기존의 클라우드 중심 모델에서 벗어나 전용 데이터센터 구축과 자체 칩을 활용하는 방식의 인프라 전략을 확대하고 있다.")
        item = {**alert(title, body), "link": "https://magazine.hankyung.com/business/article/202610017669b",
                "telegram_core_fact": "앤트로픽 매출은 45.9억달러입니다."}
        core = radar.verified_alert_core(item, title)
        for term in ("앤트로픽", "전용 데이터센터", "자체 칩", "확대"):
            self.assertIn(term, core)
        self.assertNotIn("45.9억달러", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 7)), 1)

    def test_change_core_recovery_cannot_rescue_consumer_or_local_administrative_promotions(self):
        for title, body, _link in DELIVERED_LOCAL_ADMINISTRATION:
            item = {**alert(title, body), "telegram_core_fact": "새로운 발전 전략을 소개했다."}
            with patch.object(radar.base, "kst_now", return_value=NOW):
                self.assertEqual(radar.quality_display_alerts([item], 7), [])
        audit = materiality.assess("은행, 비대면 개인사업자 대출 출시", "은행은 간편한 개인사업자 대출 상품을 출시했다고 밝혔다.")
        self.assertNotIn("customer_financing_commitment", [item["kind"] for item in audit["evidence"]])

    def test_actual_local_administration_deliveries_do_not_fill_core_news_slots(self):
        for title, body, link in DELIVERED_LOCAL_ADMINISTRATION:
            with self.subTest(link=link):
                audit = materiality.assess(title, body)
                self.assertLess(audit["priority"], 2, audit)
                item = {**alert(title, body), "link": link}
                with patch.object(radar.base, "kst_now", return_value=NOW):
                    self.assertEqual(radar.quality_display_alerts([item], 7), [])

    def test_oil_price_evidence_requires_the_actual_word_not_korean_substrings(self):
        for word in ("여유가", "보유가", "공유가", "유가증권"):
            with self.subTest(word=word):
                audit = materiality.assess("지역 주택 공급 전략", f"경기도는 주택 공급 확대를 발표했지만 계획을 전개할 {word} 없다고 설명했다.")
                self.assertNotIn("energy_geopolitics_or_supply_risk", [item["kind"] for item in audit["evidence"]])
                self.assertNotEqual(materiality.focus_kind(word + " 상승"), "energy_supply")
        for word in ("유가", "국제유가", "고유가"):
            audit = materiality.assess(word + " 상승", word + " 상승으로 원유 공급 비용이 늘었다.")
            self.assertIn("energy_geopolitics_or_supply_risk", [item["kind"] for item in audit["evidence"]])

    def test_request_for_rule_change_is_not_an_executed_rule_change(self):
        for verb in ("건의했다", "요청했다", "촉구했다"):
            body = f"강릉시는 발전 전력 직접 공급을 위한 정부 고시 개정을 {verb}."
            self.assertFalse(materiality.evidence_is_new_event("policy_scope_or_stage", body))
        enacted = "강릉시의회는 데이터센터 인허가 조례를 개정했다."
        self.assertTrue(materiality.evidence_is_new_event("policy_scope_or_stage", enacted))

    def test_early_cross_border_industry_signals_survive_local_scope_filter(self):
        for title, body in (
            KEEP[2], KEEP[3], KEEP[4], KEEP[7],
            ("트럼프, 유럽에 디젤 수출금지 경고", "트럼프 대통령은 비축유 방출에 응하지 않으면 미국산 디젤 수출을 금지할 수 있다고 경고했다."),
            ("트럼프, 유럽에 디젤 수출금지 경고", "트럼프 대통령은 비축유 방출을 요구하며 불응 시 미국산 디젤 수출을 금지할 수 있다고 경고했다."),
            INDUSTRY_DRIVER_CASES[5][1:],
        ):
            with self.subTest(title=title):
                audit = materiality.assess(title, body)
                self.assertEqual(audit["disposition"], "keep", audit)
                self.assertGreaterEqual(audit["priority"], 2, audit)

    def test_local_industrial_execution_survives_without_issuer_allowlist(self):
        for title, body in (
            ("지역 데이터센터 조례 개편", "시의회는 데이터센터 인허가 조례를 개편하고 전력 공급 규제를 완화했다."),
            ("강릉시, 전력 제약 해소…데이터센터 건설 허가", "강릉시는 지역 전력 제약 해소를 위해 200MW 데이터센터 건설을 허가했다."),
            ("강원도, 산업단지 현안 해소…반도체 공장 착공", "강원도는 지역 산업단지의 반도체 공장 착공식을 열고 생산 설비 증설을 시작했다."),
            ("고성군, 관광 거점 조성…시공사 공급계약 체결", "고성군 관광 거점 조성을 위해 시공사는 3000억원 공급계약을 체결했다."),
            ("경기도, 지역 전력 문제 해소…발전소 금융 종결", "경기도 발전소 신설 사업은 금융 종결을 마치고 투자 자금 조달을 완료했다."),
            ("경기도, 폭염에 양식장 공급 피해", "경기도는 폭염으로 양식장 어류 3만마리가 폐사해 생산과 공급에 피해가 발생했다고 밝혔다."),
        ):
            with self.subTest(title=title):
                audit = materiality.assess(title, body)
                self.assertEqual(audit["disposition"], "keep", audit)
                self.assertGreaterEqual(audit["priority"], 2, audit)

    def test_nominal_local_project_budget_cannot_rescue_administrative_proposal(self):
        title, body, _link = DELIVERED_LOCAL_ADMINISTRATION[1]
        body += "\n관광특구 예상 사업비는 1조6000억원이며 지정되면 세제 혜택과 금융 지원을 받을 수 있다."
        self.assertLess(materiality.assess(title, body)["priority"], 2)

    def test_actual_orders_and_capital_contract_precede_local_mou(self):
        items = [alert(title, body) for title, body, _link in DELIVERED_LOCAL_ADMINISTRATION]
        strong = (
            ("삼성중공업 LNGC 6722억 수주", "삼성중공업이 액화천연가스 운반선 2척을 6722억원에 수주했다."),
            ("CJ제일제당, ADM과 출자계약 체결", "CJ제일제당은 미국 ADM과 합작법인 설립을 위한 출자계약을 체결했다."),
        )
        items.extend(alert(title, body) for title, body in strong)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts(items, 7)
        self.assertEqual({item["source_title"] for item in selected}, {title for title, _body in strong})

    def test_saved_report_guard_rechecks_local_scope_instead_of_trusting_old_priority(self):
        import verify_gamejoa_generated_report as guard
        for title, body, link in DELIVERED_LOCAL_ADMINISTRATION:
            item = {**alert(title, body), "link": link,
                    "market_materiality": {"version": 25, "disposition": "keep", "priority": 3}}
            errors = guard.source_materiality_errors(item, radar)
            self.assertTrue(any("without source market-change evidence" in error for error in errors), errors)
            self.assertTrue(any("audit missing or stale" in error for error in errors), errors)
        item = alert("조선기업, LNG선 2척 수주", "조선기업은 LNG선 2척을 6722억원에 수주했다.")
        item["market_materiality"] = radar.source_market_materiality(item)
        self.assertEqual(guard.source_materiality_errors(item, radar), [])

    def test_price_component_commentary_cannot_outrank_primary_cpi_or_supply_shock(self):
        title = "전체 물가 2.9% 오를 때 농축산물 1.0%↓…축산물은 상승폭 확대"
        body = "지난달 전체 소비자물가가 2.9% 오른 가운데 농축산물 물가는 1.0% 하락했다.\n농식품부는 추석 성수품을 평시 대비 1.6배 확대 공급하고 유통기업이 할인행사를 진행한 점이 물가 부담을 낮추는 데 도움이 됐다고 설명했다."
        audit = materiality.assess(title, body)
        self.assertLess(audit["priority"], 2)
        self.assertNotIn("physical_supply_or_capacity", [item["kind"] for item in audit["evidence"]])
        self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])
        cpi = materiality.assess("9월 소비자물가 2.9% 상승…예상 상회", "9월 소비자물가는 2.9% 상승해 예상치 2.6%를 상회했다.")
        self.assertEqual(cpi["priority"], 3)
        shock = materiality.assess("폭염에 농축산물 공급 피해", "폭염으로 양식장 어류 3만마리가 폐사해 생산과 공급에 피해가 발생했다.")
        self.assertEqual(shock["priority"], 3)
        policy = materiality.assess("농축산물 물가 안정…정부, 수입 관세 0% 시행", "정부는 농축산물 물가 안정과 공급 부족에 대응해 수입 관세를 0%로 인하하는 규제 개편을 시행한다.")
        self.assertEqual(policy["priority"], 3)

    def test_planned_share_disposal_keeps_source_quantity_and_stage(self):
        title = "최태원 SK 회장, 9440억원 규모 그룹 지분 매각 추진"
        body = "최태원 SK그룹 회장이 그룹 지주사 SK㈜ 지분 9440억원 규모를 매각한다.\nSK㈜는 최대주주인 최태원 회장이 주식 165만3924주(2.3%)를 매각할 예정이라고 2일 공시했다.\n거래는 1개월 뒤인 11월 2일부터 진행될 예정이다."
        item = alert(title, body)
        item["telegram_core_fact"] = body.split("\n")[0]
        self.assertIn("planned_disposal_reported_as_completed", radar.source_core_fact_errors(item))
        core = radar.verified_alert_core(item, title)
        self.assertIn("165만3924주", core)
        self.assertIn("2.3%", core)
        self.assertIn("예정", core)
        self.assertIn("최태원", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertTrue(radar.core_sentence_is_complete(core))

    def test_investment_nonagreement_keeps_denial_and_reporting_source(self):
        title = "미국 내부서도 '알래스카 LNG' 의문…한국과 투자 합의 안 됐다"
        body = ('미국 언론들은 알래스카 액화천연가스(LNG) 파이프라인 사업성에 의문을 표했다.\n'
                '월스트리트저널(WSJ)은 1일(현지시간) 한국이 알래스카 LNG 사업에 약 500억달러를 투자할 것이라고 발표했다며 '
                '"문제는 한국이 구체적인 투자액은 물론 투자 자체에도 합의하지 않았다는 것"이라고 보도했다.')
        self.assertFalse(materiality.core_focus_aligned(title, body.split("\n")[0]))
        core = radar.verified_alert_core(alert(title, body), title)
        self.assertIn("WSJ", core)
        self.assertIn("알래스카 LNG", core)
        self.assertIn("합의하지 않았", core)
        self.assertIn("보도했다", core)
        self.assertNotIn("500억달러", core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertTrue(materiality.core_focus_aligned(title, core))
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])

    def test_annual_target_reiteration_cannot_borrow_earlier_actuals(self):
        title = "국토부 차관, 연말 공공주택 6만2000가구 착공 총력"
        body = "국토부는 연말까지 기존 공공주택 착공 목표를 달성하도록 당부했다. 1~8월 서울 주택 인허가는 3만9940가구로 전년비 40.4% 증가했고 착공은 2만679가구로 41.1% 늘었다."
        audit = materiality.assess(title, body)
        self.assertLess(audit["priority"], 2)
        self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])
        actual = materiality.assess("정부, 공공주택 공급 총력…신규 발주 확정", "정부는 공공주택 공급을 위해 3000억원 공급 계약을 체결하고 발주를 확정했다.")
        self.assertEqual(actual["priority"], 3)

    def test_primary_sales_issuer_not_competitor_forecast_owns_core_numbers(self):
        title = "현대차·기아, 3분기 美 역대 최다 기록…포드 제치고 빅3 눈앞"
        body = "현대차·기아는 3분기 합산 판매량이 50만6200대로 집계됐다고 2일 밝혔다. 전년 동기 대비 5.4% 증가한 것이다.\n포드는 아직 9월 판매 실적을 발표하지 않았는데 콕스는 포드의 3분기 판매량이 7.1% 감소한 50만4172대로 전망된다고 밝혔다."
        item = alert(title, body)
        item["telegram_core_fact"] = body.split("\n")[-1]
        self.assertIn("financial_subject_mismatch", radar.source_core_fact_errors(item))
        core = radar.verified_alert_core(item, title)
        self.assertIn("현대차·기아", core)
        self.assertIn("50만6200대", core)
        self.assertIn("5.4% 증가", core)
        self.assertNotIn("50만4172대", core)
        self.assertNotIn("전망", core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])
        self.assertEqual(radar.quality_display_alerts([item], 1)[0]["telegram_core_fact"], core)

    def test_multiple_reporter_byline_does_not_enter_reader_core(self):
        sentence = "신창용 기자 김계연 특파원 = 영국 정부가 한국의 러시아산 LNG 장기 계약 물량에 대해 제재를 면제하기로 했다."
        core = radar.normalized_article_sentence(sentence)
        self.assertTrue(core.startswith("영국 정부"))
        self.assertNotIn("기자", core)
        self.assertNotIn("특파원", core)
        body = "영국, 한국 러시아산 LNG 수입 제재 면제\n" + sentence + "\n이에 따라 한국은 기존 장기 계약 물량에 대해 2028년 3월 31일까지 제재를 면제받는다."
        core = radar.verified_alert_core(alert("EU 이어 영국도 한국의 러시아산 LNG 수입 제재 면제", body), "EU 이어 영국도 한국의 러시아산 LNG 수입 제재 면제")
        self.assertIn("2028년 3월 31일", core)
        self.assertNotIn("특파원", core)
        self.assertIn("영국 정부", core)

    def test_local_public_milestones_need_business_execution(self):
        for title, body in (
            ("제2용인-서울고속도로 민자적격성조사 통과", "국토부는 민자적격성조사를 통과해 후속 환경영향평가에 착수한다고 밝혔다. 2031년 착공이 목표다."),
            ("경기도, 기후위성 2호기 발사 성공", "경기도는 온실가스 관측용 위성 발사에 성공했다. 기존 예산 외 추가 비용은 들지 않는다."),
        ):
            self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
        actual = materiality.assess("제2용인-서울고속도로 민자적격성조사 통과·시공사 선정", "시공사는 3000억원 공급 계약을 체결했다.")
        self.assertEqual(actual["disposition"], "keep")

    def test_consumer_visa_consultation_cannot_borrow_cpi_and_capital_words(self):
        item = alert("이민업체, 미국투자이민 상담…EB-5 수수료 조정", "EB-5 수수료는 물가상승률에 따라 조정된다. 업체는 투자금 상환과 가족 영주권 신청을 위한 개별상담을 운영한다.")
        self.assertEqual(radar.source_market_materiality(item)["disposition"], "exclude")
        self.assertEqual(radar.quality_display_alerts([item], 1), [])
        policy = materiality.assess("미국, H-1B 비자 비용 인상", "미국 정부는 H-1B 취업 비자 비용을 올리는 규제안을 발표했다.")
        self.assertEqual(policy["disposition"], "keep")

    def test_exemption_action_beats_monitoring_quote_and_deduplicates_publishers(self):
        title = "英, 한국 러시아산 LNG 제재 면제…연 150만t 도입 차질 우려 해소"
        action = "사진=뉴시스2일 산업통상부에 따르면 영국 정부는 1일(현지시간) 러시아산 LNG 관련 제재 예외조치를 발표하고 한국이 기존 장기계약에 따라 수입하는 사할린Ⅱ LNG에 대해 2028년 3월 31일까지 제재를 면제하기로 했다."
        quote = '산업부는 “제재 면제조치가 실제 운송·보험 과정에서 적용되는지 점검하고 사할린Ⅱ LNG의 안정적인 도입을 관리할 계획”이라고 밝혔다.'
        first = alert(title, action + "\n" + quote)
        first["telegram_core_fact"] = quote
        core = radar.verified_alert_core(first, title)
        self.assertIn("영국 정부", core)
        self.assertIn("기존 장기계약", core)
        self.assertIn("2028년 3월 31일", core)
        self.assertIn("면제하기로", core)
        self.assertNotIn("점검", core)
        self.assertNotIn("사진", core)
        second = alert('영국, 러시아 제재 발표…"한국 사할린-2 LNG 수입 제재 면제"', "영국은 러시아 사할린-2 LNG의 한국 수입에 제재 예외를 적용하기로 했다. 허가는 2027년 1월1일부터 2028년 3월31일 사이 적용된다.")
        second["link"] = "https://www.yna.co.kr/view/another-exemption"
        second["published"] = "2026-10-01T23:50:00+09:00"
        self.assertEqual(radar.semantic_event_theme(first), radar.semantic_event_theme(second))
        self.assertEqual(radar.semantic_event_theme(first), radar.semantic_event_theme({**second, "source_title": "EU 이어 영국도 한국의 러시아산 LNG 수입 제재 면제"}))
        self.assertEqual(len(radar.quality_display_alerts([first, second], 7)), 1)
        stale = {**second, "source_title": "EU 이어 영국도 한국의 러시아산 LNG 수입 제재 면제", "news": "EU 이어 영국도 한국의 러시아산 LNG 수입 제재 면제", "supply_chain_theme": "sanctions_exemption:eu:russia:sakhalin-2:korea:2028-03-31"}
        self.assertEqual(len(radar.quality_display_alerts([first, stale], 7)), 1)
        self.assertNotEqual(radar.semantic_event_theme(first), radar.semantic_event_theme({**second, "source_body": second["source_body"].replace("2028년 3월31일", "2029년 3월31일")}))
        self.assertNotEqual(radar.semantic_event_theme(first), radar.semantic_event_theme({**second, "source_title": second["source_title"].replace("영국", "미국")}))
        self.assertEqual(radar.semantic_event_theme({**first, "body_verified": False}), "")

    def test_municipal_targets_do_not_outrank_committed_energy_projects(self):
        vague = materiality.assess("과천시, 2030년 재생에너지 보급률 10%로 확대", "과천시는 지역에너지계획 보고회를 열고 2030년 보급률 10%를 목표로 논의했다.")
        self.assertEqual(vague["disposition"], "exclude")
        actual = materiality.assess("과천시, 태양광 설비 500억원 공급 계약 체결", "과천시는 태양광 설비 500억원 공급 계약을 체결했다.")
        self.assertEqual(actual["disposition"], "keep")

    def test_policy_core_prioritizes_the_instrument_over_promises_and_forum_tasks(self):
        title = "국조실, 신산업 규제혁신 간담회 개최"
        action = "정부는 무인 자율주행차의 동일 사양 추가 허가 절차를 완화하도록 관련 고시를 개정한다."
        body = action + '\n실장은 "규제합리화위원회가 강화된 만큼 자율주행, 로봇의 애로사항이 해소될 수 있도록 논의해 나가겠다"고 말했다.'
        item = alert(title, body)
        item["telegram_core_fact"] = body.split("\n")[-1]
        self.assertIn("core_without_market_change_evidence", radar.source_core_fact_errors(item))
        self.assertEqual(radar.verified_alert_core(item, title), action)
        normalized = radar.normalize_alert_for_output(item)
        self.assertTrue(radar.source_output_aligned(normalized))
        self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)
        self.assertFalse(radar.korean_title_core_aligned(title, "정부는 AI 미래 혁신 비전을 공유했다."))
        self.assertFalse(radar.korean_title_core_aligned("자동차기업, 분기 실적 발표", action))
        forum = materiality.assess("코인 규율 도마…제도 정비 과제 부상", "기본법 제정과 결제수단별 규제 정비가 주요 과제로 제시됐다.")
        self.assertNotEqual(forum["disposition"], "keep")
        speculative = materiality.assess("코인 규율 도마…제도 정비 과제 부상", "포럼에서 교수는 국세청의 가상자산 과세 관련 고시가 이번 달에 나오지 않을까 본다고 말했다.")
        self.assertLess(speculative["priority"], 2)
        official = materiality.assess("정책 포럼, 자율주행 규제 고시 개정 발표", "정부는 포럼에서 자율주행 허가 절차를 완화하도록 관련 고시를 개정한다고 발표했다.")
        self.assertGreaterEqual(official["priority"], 2)

    def test_sanctions_exemption_core_keeps_the_actor_scope_and_deadline(self):
        title = '영국, 러시아 제재 발표…"한국 사할린 LNG 수입 제재 면제"'
        body = "영국이 1일(현지 시간) 러시아 제재를 새로 발표한 가운데 한국에 공급되는 사할린 LNG에 대해서는 2028년 3월까지 예외를 적용하기로 했다.\n대상은 2025년 6월17일 이전 체결된 LNG 공급 계약에 한해 적용된다."
        item = alert(title, body)
        item["telegram_core_fact"] = body.split("\n")[-1]
        core = radar.verified_alert_core(item, title)
        self.assertIn("영국", core)
        self.assertIn("한국", core)
        self.assertIn("2028년 3월", core)
        self.assertIn("예외", core)
        self.assertFalse(core.startswith("대상은"))
        self.assertTrue(radar.source_output_aligned({**item, "telegram_core_fact": core}))

    def test_principal_personnel_and_reward_events_cannot_borrow_contracts_or_policy(self):
        for title, body in (
            ("방산기업, 조기 선제 인사로 수출 확대", "지난 8월 공급 계약을 체결했다. 이번 정기 인사는 해외 수출 확대에 초점을 맞췄다."),
            ("금융위, 규제 개선한 공무원 1800만원 포상", "금융위는 망분리 규제 완화를 추진한 직원에게 1800만원의 포상금을 지급했다."),
        ):
            with self.subTest(title=title):
                self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
        actual = materiality.assess("기업, 인사와 함께 영업이익 전망 20% 상향", "기업은 영업이익 전망을 20% 상향했다고 밝혔다.")
        self.assertEqual(actual["disposition"], "keep")

    def test_photo_cannot_be_order_evidence_or_the_core(self):
        title = "전력기업, 영국 해상풍력 추가 수주"
        caption = "전력기업 관계자가 수주 계약 서명식에서 기념촬영을 하고 있다."
        body = caption + " (사진=전력기업) 전력기업은 영국 해상풍력 공사를 추가 수주했다고 공시했다. 계약금액은 1871억원이다."
        item = alert(title, body)
        item["telegram_core_fact"] = caption
        self.assertIn("photo_description_not_news_core", radar.source_core_fact_errors(item))
        core = radar.verified_alert_core(item, title)
        self.assertNotIn("기념촬영", core)
        self.assertNotIn("사진=", core)
        self.assertIn("추가 수주", core)
        self.assertIn("1871억원", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertFalse(any("기념촬영" in entry["source_excerpt"] for entry in materiality.assess(title, body)["evidence"]))

    def test_data_leak_is_not_investor_fund_outflow(self):
        title = "서비스기업, 개인정보 유출 후 보안체계 고도화"
        body = "서비스기업은 보안체계를 개선한다. 앞서 약 3954만개의 계정 정보가 유출된 사실이 확인됐다."
        audit = materiality.assess(title, body)
        self.assertFalse(any(entry["kind"] == "market_price_or_flow" for entry in audit["evidence"]))
        flows = materiality.assess("주식펀드 자금 유출", "주식펀드에서 1000억원의 자금이 유출됐다.")
        self.assertEqual(flows["disposition"], "keep")

    def test_named_joint_validation_merges_publishers_but_keeps_new_results(self):
        body = "전력사·반도체사·검증기관 기술협력\n세 기관은 'K-Perf' 기반 AI 반도체 성능검증 업무협약(MOU)을 체결했다."
        first = alert("전력사, 국산 AI 반도체 현장 성능검증 착수", body)
        second = alert("국산 AI반도체 지표 'K-Perf', 전력사서 첫 실증", body)
        result = alert("전력사, 국산 AI 반도체 성능검증 결과 20% 개선", body)
        other = alert("다른기관, 국산 AI 반도체 현장 성능검증 착수", body.replace("전력사", "다른기관"))
        first_key = radar.joint_validation_event_theme(first)
        self.assertTrue(first_key)
        self.assertEqual(first_key, radar.joint_validation_event_theme(second))
        self.assertNotEqual(first_key, radar.joint_validation_event_theme(result))
        self.assertNotEqual(first_key, radar.joint_validation_event_theme(other))
        first["body_verified"] = False
        self.assertEqual(radar.joint_validation_event_theme(first), "")

    def test_rendered_core_must_explain_a_market_change_not_background_words(self):
        cases = (
            ("항공사 회장 경영자상 수상", "회장이 경영자상을 수상했다. 과거 여객 수요가 급감하자 화물 사업을 확대했다.", "회장이 경영자상을 수상했다."),
            ("내년 머니 트렌드 서적 인기", "서점가에서 내년 트렌드 서적이 인기다. 책은 금리와 반도체 수요의 장기 전망을 쉽게 풀어낸다.", "서점가에서 내년 트렌드 서적이 인기다."),
        )
        for title, body, core in cases:
            with self.subTest(title=title):
                item = alert(title, body)
                item["telegram_core_fact"] = core
                self.assertIn("core_without_market_change_evidence", radar.source_core_fact_errors(item))
                self.assertFalse(radar.source_output_aligned(item))
                with patch.object(radar.base, "kst_now", return_value=NOW):
                    self.assertEqual(radar.quality_display_alerts([item], 7), [])
        for title, body in (
            ("기업, 수주잔고 확보", "기업은 2조원을 웃도는 수주잔고를 확보했다고 밝혔다."),
            ("유로존 9월 제조업 PMI 52.9", "유로존 9월 제조업 구매관리자 지수(PMI)는 52.9를 기록했다."),
            ("발전사, 육상풍력 업무협약 체결", "발전사는 개발공사와 육상풍력사업 업무협약을 체결했다."),
            ("현대차 9월 판매 역대 최대", "현대차의 9월 하이브리드 판매는 전년 동월 대비 39% 증가했다."),
            ("컬리, 넥스트키친 100% 자회사로", "컬리는 넥스트키친을 100% 자회사로 편입한다."),
            ("하이즈복합재산업, 무인기 생태계 MOU", "하이즈복합재산업은 한화에어로스페이스와 무인기 업무협약(MOU)을 체결했다."),
            ("미국, 경유 수출 금지 경고", "트럼프 행정부는 미국의 경유 수출을 금지하겠다고 유럽에 최후통첩을 보냈다."),
            ("유가 상승", "브렌트유는 이날 4.4% 오른 배럴당 102.31달러를 기록했다."),
            ("SBVA, 데이터브릭스 투자 라운드 참여", "SBVA는 데이터브릭스의 50억달러 규모 전략적 투자 라운드에 참여했다."),
            ("미국, 중국 과잉생산 대응 조치 예고", "미국이 중국 등을 겨냥한 과잉생산 대응 조치를 수주일 내 발표한다."),
            ("알래스카 LNG 투자 구상", "트럼프는 한국의 2000억달러 전략투자 가운데 540억달러를 알래스카 LNG 개발에 투입하는 구상을 발표했다."),
            ("미국 고용지표 예상 하회", "미국 비농업 고용이 예상치를 밑돌았습니다."),
            ("기업, 인수 자금조달 미정", "기업은 인수 자금조달 방식에 대해 확정된 사항은 없다고 설명했다."),
        ):
            with self.subTest(title=title):
                item = alert(title, body)
                item["telegram_core_fact"] = body
                self.assertEqual(radar.source_core_fact_errors(item), [])

    def test_photo_description_concatenated_with_business_fact_is_repaired(self):
        title = 'SG "온양캠퍼스 에코스틸아스콘 1차 시공 완료"'
        body = "SG가 온양캠퍼스에 아스콘을 시공하고 있다 (사진=SG) [서울=뉴시스] 기자 = SG는 온양캠퍼스에 에코스틸아스콘 1차 시공을 완료했다고 밝혔다."
        item = alert(title, body)
        item["telegram_core_fact"] = "SG가 아스콘을 시공하고 있다 아스콘 기업 SG는 온양캠퍼스에 1차 시공을 완료했다."
        self.assertIn("concatenated_photo_caption", radar.source_core_fact_errors(item))
        core = radar.verified_alert_core(item, title)
        self.assertNotIn("시공하고 있다", core)
        self.assertIn("1차 시공을 완료", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_viral_and_personnel_foreground_cannot_borrow_background_economics(self):
        cases = (
            ("현실판 터미네이터?…용광로에 뛰어든 로봇", "휴머노이드 로봇이 용광로에 뛰어드는 이색적인 장면이 공개됐습니다. 차세대 로봇 생산이 확대되면서 기존 모델을 퇴역시키기로 한 겁니다. 영화 패러디 영상입니다."),
            ("신보·경제진흥원 수장 후보 적격", "시의회가 이사장과 원장 후보자에게 적격 판단을 내렸다. 소상공인 생존기간과 매출 증가 등 실질 성과를 관리하겠다는 방향을 긍정적으로 봤다."),
        )
        for title, body in cases:
            with self.subTest(title=title):
                assessed = materiality.assess(title, body)
                self.assertNotEqual(assessed["disposition"], "keep", assessed)
                with patch.object(radar.base, "kst_now", return_value=NOW):
                    self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])
        actual = materiality.assess("로봇 검증 결과 공개", "로봇기업은 전력효율을 30% 높인 검증 결과를 공개했다. 영상에는 영화 패러디도 포함됐다.")
        self.assertEqual(actual["disposition"], "keep", actual)

    def test_scoped_tax_event_beats_oil_import_background(self):
        title = '관세청장 "중동산 원유 우회운송 비용 증가분 비과세 특례 검토"'
        body = '관세청은 원유 수입 중 중동산 비중이 70.9%에서 55.6%로 감소했다고 밝혔다. 관세청장은 "중동산 원유 대체운반 운임·보험료 증가분을 과세에서 제외하는 특례 방안을 검토하겠다"고 밝혔다.'
        item = alert(title, body)
        item["telegram_core_fact"] = "원유 수입 중 중동산 비중이 70.9%에서 55.6%로 감소했다."
        self.assertFalse(radar.source_output_aligned(item))
        core = radar.verified_alert_core(item, title)
        self.assertIn("과세에서 제외", core)
        self.assertIn("검토", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_punctuation_inside_quotes_keeps_speaker_and_whole_statement(self):
        title = "미 무역대표부, 과잉생산 대응 조치 수주일 내 발표"
        body = '미국이 중국 등을 겨냥한 과잉생산 대응 조치를 수주일 내 발표한다. 그리어 대표는 “조용히 받아들일 생각이 없다. 미국은 행동할 것”이라며 “향후 수주일 안에 조사 내용을 공개할 것”이라고 밝혔다.'
        sentences = materiality.source_sentences(body)
        self.assertEqual(len(sentences), 2)
        self.assertTrue(sentences[1].startswith("그리어 대표는"))
        ranked = radar.ranked_article_sentences(body, [], title=title)
        self.assertFalse(any(sentence.startswith("미국은 행동할 것") for sentence in ranked))
        for sentence in ranked:
            self.assertEqual(sentence.count("“"), sentence.count("”"), sentence)
        core = radar.detailed_article_core(title, body)
        self.assertEqual(core.count("“"), core.count("”"), core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        item = alert(title, body)
        item["source_body"] = '그리어 대표 "수주일 내 조사 내용 공개"\n▲그리어 대표가 기자회견에서 발언하고 있다. 밀워키(미국)/AP연합뉴스\n' + body
        item["telegram_core_fact"] = '미국은 행동할 것”이라며 “수주일 안에 조사 내용을 공개할 것”이라고 밝혔다.'
        self.assertIn("orphaned_source_quote", radar.source_core_fact_errors(item))
        repaired = radar.verified_alert_core(item, title)
        self.assertEqual(repaired.count("“"), repaired.count("”"), repaired)
        self.assertTrue(radar.core_sentence_is_complete(repaired), repaired)
        self.assertNotIn("AP연합뉴스", repaired)
        self.assertNotIn("발언하고 있다", repaired)

    def test_fresh_run_administrative_and_exhibition_fillers_do_not_pass(self):
        cases = (
            ("리알로, 파트너와 함께 메인넷 연다", "리알로는 은행이 온체인에서 대출을 제공하려면 대출자의 온체인 자산과 신용정보를 확인할 필요가 있다고 말했다. 리알로가 뉴욕증권거래소와 연결돼 있다고 설명했다. 한국 기관들이 규제 명확성이 생기기를 기다리며 기회를 검토하고 있다고 말했다."),
            ("농산물무역정책심의회 법정위 격상…생산자 참여 확대", "농산물무역정책심의회 법정위 격상…생산자 참여 확대. 이날 회의에서는 사료와 가공식품 원료 등 국내 생산이 부족한 품목을 대상으로 일정 물량에 저율 수입 관세를 부과하는 내년도 운영계획안을 논의했다."),
            ("삼천당제약, CPHI 첫 단독부스…글로벌 협력 확대", "삼천당제약은 전시회에 처음으로 단독부스를 마련한다. 유럽과 북미에 공급 중인 점안제와 바이오시밀러를 전시하고 기술이전과 공동개발 논의를 통해 글로벌 사업 확대에 나선다는 계획이다."),
            ('구청장 "공원 개발 반대"[인터뷰]', "장관은 공원의 일부 부지에 주택을 공급하도록 검토하자는 입장인 것으로 알려져 있다. 구청장은 개발 반대 입장을 밝혔다."),
            ("[르포] 강북 집값 숨고르기…대출 부담", "서울 주택 공급 부족으로 집값이 올랐지만 이제 높아진 가격이 매수자에게 부담으로 작용한다. 최근 기준금리 인상으로 주택담보대출 이자 부담이 커졌다."),
        )
        for title, body in cases:
            with self.subTest(title=title):
                assessed = materiality.assess(title, body)
                self.assertTrue(assessed["disposition"] != "keep" or assessed["priority"] < 2, assessed)
                with patch.object(radar.base, "kst_now", return_value=NOW):
                    self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])

    def test_new_business_event_survives_exhibition_and_committee_context(self):
        for title, body in (
            ("바이오기업, 전시회서 기술이전 계약", "바이오기업은 글로벌 고객과 신약 기술이전 계약을 체결했다."),
            ("바이오기업, 전시회서 임상 3상 결과 발표", "바이오기업은 임상 3상 결과 반응률이 30% 개선됐다고 발표했다."),
            ("정책위원회, 수입 관세율 인하 의결", "정책위원회는 수입 관세율을 20%에서 5%로 인하하는 개정안을 의결했다."),
            ("공장 투자위원회, 생산설비 투자 승인", "기업 투자위원회는 300억원을 투자해 생산설비를 증설하기로 승인했다."),
        ):
            with self.subTest(title=title):
                assessed = materiality.assess(title, body)
                self.assertEqual(assessed["disposition"], "keep", assessed)
                self.assertGreaterEqual(assessed["priority"], 2, assessed)

    def test_current_customer_implementation_displaces_other_sites_background(self):
        title = "SG, 삼성전자 온양캠퍼스에 에코스틸아스콘 1차 시공"
        body = "▲SG는 삼성전자 온양캠퍼스에 에코스틸아스콘 1차 시공을 완료했다고 밝혔다. 공공 인프라에서는 서울시 도로에서 성능을 검증한 데 이어 고속도로 현장에도 납품했다."
        core = radar.detailed_article_core(title, body)
        self.assertIn("온양캠퍼스", core)
        self.assertIn("1차 시공을 완료", core)
        self.assertNotIn("고속도로", core)
        self.assertNotIn("▲", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertFalse(materiality.core_focus_aligned(title, "고속도로 현장에도 납품했다."))

    def test_actual_delivery_publicity_is_not_promoted_by_service_keywords(self):
        cases = (
            ("지평, 방사청 출신 변호사 영입…방산 법률자문 강화", "법무법인 지평은 방사청 출신 변호사를 영입했다고 밝혔다. 국방 조달 및 수출 통제, 해외 투자 및 인수합병(M&A), 기술 이전을 아우르는 법률 솔루션을 제공하고 있다."),
            ("바이오협, 바이오기업 31곳 투자유치 지원…미팅 20건 연계", "협회는 바이오기업 31곳을 대상으로 투자유치 지원 프로그램을 운영했다. 상장과 인수합병(M&A), 기술이전 등 투자금 회수 전략을 검토할 때 참고할 내용도 수록했다."),
            ("관악연구소, 3억원 투자유치", "금융 AI 기업 관악연구소는 서울대학교 기술지주로부터 3억원 투자를 유치했다. 금융권 기술 적용 가능성을 확인하고 있다. 투자자는 독보적인 기술 역량으로 혁신을 이끌 것으로 기대한다고 말했다."),
            ("휴온스, 글로벌 학회 신약 연구 초록 채택", "휴온스는 비임상 연구결과 2건이 학회 초록으로 선정됐다고 밝혔다. 관계자는 후보물질의 개발 가능성을 검증하면서 임상 단계까지 확대하겠다고 말했다."),
            ("광통신주, AI 투자 기대감에 상한가", "차세대 통신망 수요 확대 기대감에 광통신주가 29.8% 상승했다. 단기 테마성 수급 유입에 유의할 필요가 있다는 지적이다."),
            ("[특징주] AI 데이터 센터 투자 확대에 광통신주 강세…머큐리, 상한가", "차세대 통신망 수요 확대 기대감에 머큐리가 29.8% 상승했다. 이날 주가 상승은 인공지능(AI) 데이터센터 확산과 대용량 트래픽 증가에 따라 초고속 유무선 전송망과 광통신 네트워크 인프라를 고도화해야 한다는 시장의 요구가 부각된 영향으로 풀이된다. 오이솔루션은 광트랜시버를 생산하고 있으며, 우리넷은 광전송 네트워크 장비 경쟁력을 보유하고 있어 통신 인프라 확충에 따른 공급 확대 가능성이 주가를 뒷받침했다."),
            ("계란 생산량 늘어 한 판 가격 하락", "계란 생산량 증가로 특란 가격은 6882원으로 하락했다."),
        )
        for title, body in cases:
            with self.subTest(title=title):
                assessed = materiality.assess(title, body)
                self.assertTrue(assessed["disposition"] != "keep" or assessed["priority"] < 2, assessed)
                with patch.object(radar.base, "kst_now", return_value=NOW):
                    self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])

    def test_new_transactions_and_tests_survive_publicity_scope_checks(self):
        cases = (
            ("바이오 지원펀드, 신규 출자 계약", "바이오 지원펀드는 신약 임상 3상 지원을 위해 800억원 출자 계약을 체결했다."),
            ("바이오기업, 학회서 임상 3상 결과 공개", "바이오기업은 학회에서 신약 임상 3상 결과를 공개했으며 반응률이 30% 개선됐다고 밝혔다."),
            ("자동차 부품기업, 자율주행 고객 첫 공급", "자동차 부품기업은 자율주행 고객에 전자 브레이크를 첫 공급했다."),
            ("메모리 장비업체, 신규 계약 체결", "메모리 장비업체는 고객과 공급계약을 체결했다."),
            ("냉각장비기업, 데이터센터 설비투자", "냉각장비기업은 AI 데이터센터 수요 대응을 위해 1500억원 증설투자를 실시한다."),
            ("식품 공급망, 폭염에 집단 폐사", "폭염으로 양식장 어류 3만 마리가 폐사해 생산과 공급에 피해가 발생했다."),
        )
        for title, body in cases:
            with self.subTest(title=title):
                result = materiality.assess(title, body)
                self.assertEqual(result["disposition"], "keep", result)
                self.assertGreaterEqual(result["priority"], 2, result)

    def test_new_change_rank_precedes_focus_and_certainty(self):
        early = alert("양자기업, 극저온 검증 결과 공개", "양자기업은 20mK 극저온 환경에서 격리도 100dB를 검증하고 상용화 협력을 추진한다고 발표했다.")
        routine = alert("국고채 금리 하락", "국고채 3년물 금리는 5bp 하락한 연 3.960%를 기록했다.")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts([routine, early], 1)
        self.assertEqual(selected[0]["source_title"], early["source_title"])

    def test_stock_quote_does_not_create_energy_policy_evidence(self):
        result = materiality.assess("우주 프로젝트 관련주 상승", "국내 기업은 위성 고객과 발사계약을 체결했다. S-Oil(163200원 ▲14400 +9.68%)이 9%대 급등했다.")
        self.assertNotIn("energy_geopolitics_or_supply_risk", {row["kind"] for row in result["evidence"]})

    def test_bid_execution_replaces_generic_order_history(self):
        title = "IPARK현대산업개발, 수도권 정비사업 확장"
        body = "IPARK현대산업개발은 최근 수도권 정비사업 수주를 이어가고 있다. IPARK현대산업개발은 능곡3구역 시공사 입찰제안서를 단독 제출했다. 시공사 선정은 오는 11월 예정이다."
        audit = materiality.assess(title, body)
        self.assertIn("procurement_execution_stage", {row["kind"] for row in audit["evidence"]})
        self.assertNotIn("수주를 이어가고", str(audit["evidence"]))
        core = radar.detailed_article_core(title, body)
        self.assertIn("단독 제출", core)
        self.assertNotIn("수주를 이어가고", core)

    def test_analyst_revision_retains_issuer_and_new_estimate(self):
        title = '메리츠증권 "넷마블, 신작보다 기존작 수명 연장 집중"'
        body = "메리츠증권은 넷마블에 대해 시장 기대치를 밑돌 것으로 전망했다. 메리츠증권은 3분기 환율이 13% 하락한 점을 반영해 매출 추정치를 350억원 낮췄고, 영업이익 전망치도 기존 1069억원에서 786억원으로 26.5% 하향했다."
        item = alert(title, body)
        item["telegram_core_fact"] = "메리츠증권 3분기 영업이익은 1069억원 전망입니다."
        self.assertEqual(set(radar.source_core_fact_errors(item)), {"financial_subject_mismatch", "superseded_financial_estimate"},
                         {"revision": radar.financial_revision_fact(title, radar.ranked_article_sentences(body, [], title=title)),
                          "target": radar.analyst_research_target(title, body),
                          "sentences": radar.ranked_article_sentences(body, [], title=title)})
        core = radar.verified_alert_core(item, title)
        self.assertIn("넷마블", core)
        self.assertIn("1069억원→786억원", core)
        self.assertIn("26.5% 하향", core)
        self.assertNotIn("메리츠증권 3분기", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertEqual(radar.source_core_fact_errors({**item, "telegram_core_fact": core}), [])

    def test_group_insider_purchase_is_not_one_persons_total(self):
        title = "더네이쳐홀딩스, 박영준 대표 등 임원 주식 매입"
        body = "더네이쳐홀딩스는 박영준 대표이사를 비롯한 주요 임원 4명 등 특수관계인이 시간외 대량매매(블록딜) 방식으로 자사주 4만9480주(약 3억2000만원 규모)를 매입했다고 2일 밝혔다. 회사 측에 따르면 박 대표는 이번에 1만3894주를 매입했다."
        core = radar.insider_purchase_fact(title, radar.ranked_article_sentences(body, [], title=title))
        self.assertIn("임원 4명", core)
        self.assertIn("4만9480주", core)
        self.assertIn("3억2000만원", core)
        self.assertNotIn("개인 명의", core)
        self.assertNotIn("1만3894주", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_vision_headline_cannot_hide_office_publicity_or_historical_fundraising(self):
        title = "금융그룹 회장 새로운 금융의 길 열겠다"
        body = '금융그룹 회장은 헤드쿼터 개관식에서 새로운 100년을 열겠다고 말했다. 시장은 축사에서 "15년간 이어온 투자유치 노력이 타운의 완성으로 결실을 맺었다"고 말했다.'
        self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])
        historical = materiality.assess("금융그룹 새로운 100년", '시장은 "15년간 이어온 투자유치 노력이 결실을 맺었다"고 말했다.')
        self.assertNotEqual(historical["disposition"], "keep")
        actual = materiality.assess("기업 본사 이전, 자금조달 계약", "기업은 본사 이전과 함께 신규 투자자에게 300억원 투자를 유치했다고 발표했다.")
        self.assertEqual(actual["disposition"], "keep")

    def test_weather_shelter_publicity_requires_actual_operational_damage(self):
        title = "항만공사, 비즈니스 라운지 무더위·한파 쉼터 지정"
        body = "비즈니스 라운지는 폭염과 한파 시기 시민과 항만 근로자의 쉼터 역할을 한다. 항만공사 사장은 공공서비스를 확대해 나갈 것이라고 말했다."
        self.assertNotEqual(materiality.assess(title, body)["disposition"], "keep")
        for headline, source in (
            ("폭염에 항만 정전", "폭염으로 변압기 과부하와 항만 정전이 발생해 화물 처리에 차질이 발생했다."),
            ("폭염 속 사망자 증가", "폭염으로 온열질환 사망자가 증가했다."),
        ):
            self.assertEqual(materiality.assess(headline, source)["disposition"], "keep")

    def test_photo_caption_is_removed_without_removing_following_warning(self):
        title = "푸틴, 칼리닌그라드 피격시 핵 대응 시사"
        body = '[모스크바=AP/뉴시스] 블라디미르 푸틴 러시아 대통령(왼쪽)이 모스크바에서 열린 발다이 국제토론클럽에서 발언하고 있다. [서울=뉴시스] 기자 = 블라디미르 푸틴 러시아 대통령은 1일(현지 시간) 발트해 연안 역외 영토 칼리닌그라드가 공격받을 경우 "특별한 수단"을를 포함한 모든 무기를 사용할 준비가 돼 있다고 경고했다.'
        self.assertTrue(radar.core_has_ui_garbage("푸틴이 토론클럽에서 발언하고 있다."))
        sentences = radar.ranked_article_sentences(body, [], title=title)
        self.assertFalse(any("발언하고 있다" in sentence for sentence in sentences))
        core = radar.source_focused_article_core(title, sentences)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertIn("공격받을 경우", core)
        self.assertIn("준비", core)
        self.assertNotIn("왼쪽", core)
        self.assertNotIn("을를", core)
        self.assertFalse(materiality.core_focus_aligned(title, "러시아는 우크라이나의 정유시설을 공격했다고 밝혔다."))

    def test_central_bank_guidance_core_keeps_statement_over_numeric_background(self):
        title = '"더 시간이 필요할 수도"…연준 부의장, 추가 금리인상 신중론'
        body = '미국 국채 수익률은 지난달 5%에서 5.25%로 상승했다. 필립 제퍼슨 연방준비제도 부의장은 "금리를 다시 인상할지 결정하기 전에 더 많은 시간이 필요할 수 있다"고 밝혔다.'
        core = radar.source_focused_article_core(title, radar.ranked_article_sentences(body, [], title=title))
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertIn("제퍼슨", core)
        self.assertIn("시간", core)
        self.assertNotIn("5.25%", core)
        self.assertEqual(materiality.assess(title, body)["disposition"], "keep")

    def test_campaign_rhetoric_and_personnel_disputes_are_not_macro_or_labor_events(self):
        cases = (
            ("트럼프-밴스, 공화당 지지지역 유세 지원", '밴스는 일자리 100만 개가 미국인에게 돌아갔다고 주장했다. 야당은 트럼프와 밴스가 이란전 비용으로 물가를 치솟게 만든 장본인이라고 비판했다.'),
            ("광역시, 불통 인사 반박", '광역시는 공무원노조의 원칙 없는 인사 중단 요구에 대해 업무성과를 고려해 단행했다고 반박했다.'),
        )
        for title, body in cases:
            item = alert(title, body)
            self.assertNotEqual(materiality.assess(title, body)["disposition"], "keep")
            with patch.object(radar.base, "kst_now", return_value=NOW):
                self.assertEqual(radar.quality_display_alerts([item], 7), [])
        for title, body in (
            ("트럼프 유세서 중국산 장비 관세 인상 제안", "트럼프는 중국산 장비에 대한 관세를 30%로 인상하는 방안을 제안했다."),
            ("트럼프 유세서 이란 추가 공격 경고", "트럼프는 이란에 대한 추가 공격이 임박했다고 경고했다."),
            ("항만 노조 파업", "항만 노조는 임금 교섭 결렬로 파업을 결정했다."),
        ):
            self.assertEqual(materiality.assess(title, body)["disposition"], "keep")

    def test_industry_program_core_explains_implementation_not_panel_discussion(self):
        title = "SMR·양자 상용화 속도낸다…정부 7대 시드 시동"
        body = "과기정통부는 양자 기업 대상 지원책의 방향성을 설명했고, 종합토론에서는 학계 관계자들이 지원 방안 등을 논의했다. 소형모듈원자로(SMR)는 수요·공급 기업이 참여하는 민관협의체를 이달 출범시켜 상용화 기반 마련에 나서고, 양자 분야는 연구 성과를 창업과 사업화로 연결하기 위한 지원을 본격화한다."
        core = radar.source_focused_article_core(title, radar.ranked_article_sentences(body, [], title=title))
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertIn("이달", core)
        self.assertIn("민관협의체", core)
        self.assertIn("사업화", core)
        self.assertNotIn("종합토론", core)

    def test_trade_editions_deduplicate_without_collapsing_changed_quantities(self):
        import verify_gamejoa_generated_report as guard
        core = "HLB그룹은 진 의장이 지분 99%를 보유한 금융투자회사 에포케가 최근 장내에서 HLB이노베이션과 HLB테라퓨틱스 주식을 추가 매수했다고 밝혔다."
        titles = ("진양곤 HLB 의장, 개인법인 통해 계열사 지분 확대", "진양곤 HLB 의장, 후속 파이프라인 자신감")
        items = [alert(title, core + " 에포케는 주식 21만8718주를 장내 매수했다. 주식 13만584주를 매수했다.") for title in titles]
        for index, item in enumerate(items):
            item.update(telegram_core_fact=core.replace("에포케", "'에포케'") if index else core,
                        link=f"https://www.yna.co.kr/view/trade-edition-{index}")
        items[0]["source_body"] = items[0]["source_body"].replace("13만584주를 매수했다", "13만584주를 장내에서 사들였다")
        telegram = production.contract.telegram
        self.assertTrue(telegram.verified_trade_theme(items[0]))
        self.assertEqual(telegram.verified_trade_theme(items[0]), telegram.verified_trade_theme(items[1]))
        self.assertEqual(len(guard.duplicate_event_errors(items, radar)), 1)
        self.assertTrue(set(telegram.alert_seen_keys(items[0])) & set(telegram.alert_seen_keys(items[1])))
        changed = {**items[1], "source_body": items[1]["source_body"].replace("21만8718주", "25만8718주")}
        self.assertNotEqual(telegram.verified_trade_theme(items[0]), telegram.verified_trade_theme(changed))
        revised = {**items[0], "telegram_core_fact": core.replace("99%", "9.9%")}
        self.assertNotEqual(telegram.verified_trade_theme(items[0]), telegram.verified_trade_theme(revised))
        self.assertEqual(telegram.verified_trade_theme({**items[0], "body_verified": False}), "")

    def test_trading_resumption_core_does_not_replace_event_with_old_contract(self):
        title = "5대 1 액면병합 끝낸 아이비젼웍스, 거래 재개일에 상한가"
        body = "거래정지 기간 중 아이비젼웍스는 38억원 규모의 검사 시스템 공급계약을 체결했다. 아이비젼웍스는 거래 재개 기준가 대비 29.97% 오른 상한가 6440원에 거래되고 있다."
        core = radar.source_focused_article_core(title, radar.ranked_article_sentences(body, [], title=title))
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertIn("재개", core)
        self.assertNotIn("38억원", core)
        self.assertEqual(materiality.assess(title, body)["disposition"], "keep")

    def test_certification_emissions_and_hospital_are_not_financial_actions(self):
        cases = (
            ("한유원 인증 3개 취득", "한유원은 안전보건 경영 인증을 받았다. 무재해사업장 달성, 온실가스 감축 실적 및 에너지 절약 캠페인 성과를 인정받았다."),
            ("김해시의원 의료거점 설립 협의 촉구", "경남 김해지역 종합병원의 잇따른 운영 중단과 의료기관 개원 지연에 따른 의료공백 해소를 위해 협의에 나서야 한다는 의견이 나왔다."),
            ("부산 북항 크레인 내구연한 초과", "부산 북항 크레인 155기 중 151기가 내구연한을 초과했다. 다만 이들 사고는 대부분 항만 건설공사 현장과 여객터미널 등에서 발생했다."),
        )
        for title, body in cases:
            audit = materiality.assess(title, body)
            self.assertFalse(audit["disposition"] == "keep" and audit["priority"] >= 2, (title, audit))
        for title, body in (
            ("제조업체 인력 감축 발표", "제조업체는 공장 비용 축소를 위해 인력 300명을 감축한다고 발표했다."),
            ("반도체 업체 합병 승인", "경쟁당국은 반도체 업체 합병을 승인했다."),
            ("항만 크레인 교체 발주", "항만공사는 노후 크레인 교체 공사를 신규 발주했다고 발표했다."),
        ):
            self.assertEqual(materiality.assess(title, body)["disposition"], "keep", title)

    def test_contact_footer_related_titles_cannot_supply_article_evidence(self):
        title = "산업부 CPTPP 간담회"
        body = "산업부는 제조업계의 의견을 듣는 간담회를 열었다.\nreporter@example.com\nCPTPP 가입 시 보조금 제한 가능성\n국가 AI 투자 2조원 승인"
        cleaned = radar.article_summary_body(body)
        self.assertNotIn("보조금", cleaned)
        self.assertNotIn("투자", cleaned)
        item = alert(title, body)
        audit = radar.source_market_materiality(item)
        self.assertNotEqual(audit["disposition"], "keep", audit)

    def test_data_center_target_core_keeps_capacity_and_stage_not_per_gw_cost(self):
        title = "日 JERA·델·라엘름, 5년내 3~4GW 데이터센터 구축 목표"
        body = "파이낸셜타임스(FT)는 JERA의 글로벌 최고경영자(CEO) 유키오 카니가 자사와 인터뷰에서 5년 안에 3~4기가와트(GW) 규모의 데이터센터와 가스발전 인프라 구축을 목표로 한다고 말했다고 전했다. 그는 GW당 구축 비용을 350억~450억달러로 추산했다. 국제데이터센터협회(IDCA)의 보고서에 따르면 미국 데이터센터의 전력소비량은 29.2GW로 전 세계 데이터센터 전력소비량의 43%를 차지한다. 다른 회사는 400MW 데이터센터 건설을 추진한다."
        sentences = radar.ranked_article_sentences(body, [], title=title)
        core = radar.source_focused_article_core(title, sentences)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertIn("JERA", core)
        self.assertIn("3~4", core)
        self.assertIn("목표", core)
        self.assertNotIn("달러", core)
        self.assertNotIn("29.2", core)
        self.assertNotIn("400MW", core)
        self.assertFalse(materiality.core_focus_aligned(title, "그는 GW당 구축 비용을 350억~450억달러로 추산했다."))
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep", audit)
        self.assertEqual(audit["evidence"][0]["stage"], "early_signal", audit)
        item = alert(title, body)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts([item], 7)
        self.assertEqual(len(selected), 1, item.get("_exclusion_reason"))

    def test_capacity_headline_core_cannot_substitute_previous_quarter_revenue(self):
        title = "엠케이전자, 중국 법인 성장 지속…도금와이어 캐파 증설 착수"
        body = "실제로 엠케이전자 중국법인의 2분기 매출은 전 분기 대비 약 15% 증가했다. 엠케이전자는 내년 상반기까지 올해 대비 도금와이어 생산능력을 50% 확대하는 증설에 착수했다."
        sentences = radar.ranked_article_sentences(body, [], title=title)
        core = radar.source_focused_article_core(title, sentences)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertIn("증설", core)
        self.assertIn("50%", core)
        self.assertIn("올해 대비", core)
        self.assertNotIn("15%", core)
        self.assertFalse(materiality.core_focus_aligned(title, "2분기 매출은 15% 증가했다."))

    def test_foreign_wire_dateline_and_invisible_characters_do_not_reach_core(self):
        raw = "[마나마=AP/뉴시스] \ufeff마코 루비오\ufeff 미국 국무장관이 이란 대표단에 출국을 요구한 것으로 전해졌다."
        self.assertTrue(radar.core_has_ui_garbage(raw))
        cleaned = radar.normalized_article_sentence(raw)
        self.assertNotIn("[마나마", cleaned)
        self.assertNotIn("\ufeff", cleaned)
        self.assertTrue(radar.core_sentence_is_complete(cleaned), cleaned)
        self.assertIn("요구한 것으로 전해졌다", cleaned)

    def test_foreign_topic_overlays_preserve_only_verified_collector_evidence(self):
        title = "US attacks Iran over ship being hit in Strait of Hormuz"
        body = "The US military completed airstrikes targeting Iran after a civilian vessel was attacked in the Strait of Hormuz, threatening the ceasefire."
        row = {"source": "AP News", "publisher": "AP News", "layer": "trusted", "title": title,
               "source_title": title, "source_body": body, "source_abstract": body, "summary": body,
               "body_verified": True, "published": NOW, "link": "https://apnews.com/article/verified-foreign-fixture"}
        item = production.contract.strict.classify(row, NOW)
        self.assertIsNotNone(item)
        self.assertTrue(item["body_verified"])
        self.assertEqual(item["source_body"], body)
        self.assertEqual(item["source_title"], title)
        self.assertEqual(radar.source_market_materiality(item)["disposition"], "keep")
        unverified = production.contract.strict.classify({**row, "body_verified": False}, NOW)
        self.assertIsNotNone(unverified)
        self.assertNotEqual(radar.source_market_materiality(unverified)["disposition"], "keep")

    def test_legacy_sector_labels_cannot_replace_source_market_change_evidence(self):
        cases = (
            ("영월 2027년 주요업무 보고회 개최", "영월은 주요업무 보고회를 개최했다. 출향군민 교류 조례 제정으로 행정 수요에 대응한다."),
            ("기업 AI 데이터센터 운영 혁신 전략 발표", "기업은 기술 강연을 진행했다. 발표자는 AIDC의 설비 가동 중단을 방지하는 운영 품질이 중요하다고 말했다."),
            ("우크라 외무 北포로 공개 논란 진화", "우크라이나와 한국은 포로 송환 사실을 비공개하기로 합의했지만, 비공개 합의 여부를 두고 논란이 발생했다."),
            ("재경부 세수추계 개선", "재경부는 세수추계 정확도를 개선한다. 세수 부족 규모를 파악해 다음 해 예산안 심사에 활용한다. 국유재산 실태조사에는 인공지능 변화탐지 기술을 도입했다."),
            ("식품기업 반려동물 정원 개장", "식품기업은 서울시와 반려동물 정원을 개장했다. 한편 식품기업은 해외 회사 인수를 계기로 사업 통합을 추진한다."),
        )
        for title, body in cases:
            item = alert(title, body)
            item["sectors"] = ["반도체/AI", "금융/자본시장"]
            with patch.object(radar.base, "kst_now", return_value=NOW):
                self.assertEqual(radar.quality_display_alerts([item], 7), [], title)

    def test_conference_or_local_policy_with_new_economic_change_survives(self):
        cases = (
            ("기업 AI 데이터센터 운영 혁신 전략 발표", "기업은 데이터센터에 800V HVDC 전력 변환 규격을 채택한다고 발표했다."),
            ("지역 데이터센터 조례 개편", "시의회는 데이터센터 인허가 조례를 개편하고 전력 공급 규제를 완화했다."),
            ("재경부 세율 인하 발표", "재경부는 기업의 세율을 2%포인트 인하하는 방안을 발표했다."),
            ("우크라 에너지 시설 공격", "우크라이나는 러시아 에너지 시설 공격을 확대했다."),
        )
        for title, body in cases:
            audit = materiality.assess(title, body)
            self.assertEqual(audit["disposition"], "keep", (title, audit))
            self.assertGreaterEqual(audit["priority"], 2)

    def test_actual_run_nonmarket_ownership_ceremony_and_product_pr_are_excluded(self):
        cases = (
            ("메시, 스페인 2부 엘덴세 지분 전량 인수…두 번째 구단주 행보", "메시는 투자그룹이 보유한 엘덴세 지분 전량을 인수했다. 축구 구단주가 됐다."),
            ("마포구 '다시 500만그루 나무심기' 본격화", "서울 마포구는 나무 심기 선포식을 연다고 밝혔다. 식재 공간이 부족하면 이동형 화분을 사용한다."),
            ("생활용품 기업, 출시 2년 만에 누적 매출 600억원 돌파", "기업은 세탁 제품의 누적 매출이 600억원을 돌파했다고 밝혔다. 올해 8월 매출은 8.6% 증가했다."),
        )
        for title, body in cases:
            item = alert(title, body)
            self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
            with patch.object(radar.base, "kst_now", return_value=NOW):
                self.assertEqual(radar.quality_display_alerts([item], 7), [])

    def test_scoped_exclusions_preserve_actual_earnings_and_listed_club_transactions(self):
        cases = (
            ("상장 축구 구단 지분 인수 결정", "상장 구단의 최대주주는 지분 25% 인수를 결정했다."),
            ("생활용품 기업 누적 매출 증가…영업이익 가이던스 상향", "세탁 제품 기업은 영업이익 가이던스를 20% 상향했다고 발표했다."),
            ("부산시 전력장비 공급계약 체결", "부산시는 전력장비 100억원 공급계약을 기업과 체결했다."),
        )
        for title, body in cases:
            self.assertEqual(materiality.assess(title, body)["disposition"], "keep")

    def test_domestic_cpi_editions_use_verified_actual_not_counterfactual_rate(self):
        core = "국가데이터처가 발표한 2026년 9월 소비자물가지수는 전년 동월보다 2.9% 상승했다."
        titles = (
            "9월 물가 2.9%↑…정부 최고가격제 없었다면 3.5%(종합)",
            "9월 물가 2.9%↑…통신료 기저효과 종료(2보)",
        )
        items = [alert(title, core) for title in titles]
        for index, item in enumerate(items):
            item.update(telegram_core_fact=core, published="2026-10-02T09:33:00+09:00", link=f"https://www.newsis.com/view/cpi-edition-{index}")
        themes = [production.contract.telegram.macro_release_theme(item) for item in items]
        self.assertTrue(themes[0])
        self.assertEqual(themes[0], themes[1])
        self.assertTrue(set(production.contract.telegram.alert_seen_keys(items[0])) & set(production.contract.telegram.alert_seen_keys(items[1])))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts(items, 7)
        self.assertEqual(len(selected), 1)

    def test_macro_core_fallback_keeps_forecasts_revisions_and_periods_distinct(self):
        telegram = production.contract.telegram
        base_item = {**alert("9월 물가 2.9%↑(종합)", "국가데이터처가 발표한 9월 소비자물가는 2.9% 상승했다."),
                     "published": "2026-10-02T09:33:00+09:00", "telegram_core_fact": "국가데이터처가 발표한 9월 소비자물가는 2.9% 상승했다."}
        base_key = telegram.macro_release_theme(base_item)
        self.assertTrue(base_key)
        for core in ("국가데이터처가 발표한 9월 소비자물가는 3.0% 상승했다.",
                     "국가데이터처가 발표한 8월 소비자물가는 2.9% 상승했다."):
            self.assertNotEqual(telegram.macro_release_theme({**base_item, "telegram_core_fact": core}), base_key)
        self.assertEqual(telegram.macro_release_theme({**base_item, "source_title": "10월 물가 3% 상승 예상", "telegram_core_fact": "한국은행은 10월 소비자물가가 3% 내외로 상승할 것으로 예상했다."}), "")
        self.assertEqual(telegram.macro_release_theme({**base_item, "body_verified": False}), "")

    def test_generated_report_guard_rejects_duplicate_source_events(self):
        import verify_gamejoa_generated_report as guard

        core = "국가데이터처가 발표한 9월 소비자물가는 2.9% 상승했다."
        items = [alert(title, core) for title in ("9월 물가 2.9%↑(종합)", "9월 물가 2.9%↑(2보)")]
        for item in items:
            item.update(telegram_core_fact=core, published="2026-10-02T09:33:00+09:00")
        self.assertEqual(len(guard.duplicate_event_errors(items, radar)), 1)
        revised = {**items[1], "source_title": "9월 물가 3.0%↑(수정)",
                   "telegram_core_fact": core.replace("2.9%", "3.0%")}
        self.assertEqual(guard.duplicate_event_errors([items[0], revised], radar), [])

    def test_cross_source_macro_caption_uses_verified_release_context(self):
        full_core = "국가데이터처가 발표한 2026년 9월 소비자물가는 전년비 2.9% 상승했다."
        first = {**alert("9월 물가 2.9%↑(종합)", full_core), "telegram_core_fact": full_core, "published": "2026-10-02T09:33:00+09:00"}
        caption = {**alert("소비자 물가상승률 2.9%", "국가데이터처 심의관이 2026년 9월 소비자물가 동향을 브리핑했다. 지난달 소비자물가 상승률은 작년 동월보다 2.9% 상승했다."),
                   "telegram_core_fact": "지난달 소비자물가 상승률은 작년 동월보다 2.9% 상승했다.", "published": "2026-10-02T09:19:00+09:00",
                   "link": "https://www.yna.co.kr/view/PYH-caption-fixture"}
        telegram = production.contract.telegram
        self.assertEqual(telegram.macro_release_theme(first), telegram.macro_release_theme(caption))
        normalized = [radar.normalize_alert_for_output(item) for item in (first, caption)]
        import verify_gamejoa_generated_report as guard
        self.assertEqual(len(guard.duplicate_event_errors(normalized, radar)), 1)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([first, caption], 7)), 1)
        self.assertEqual(telegram.macro_release_theme({**caption, "body_verified": False}), "")
        different = {**caption, "source_body": caption["source_body"].replace("9월", "8월")}
        self.assertNotEqual(telegram.macro_release_theme(different), telegram.macro_release_theme(first))

    def test_office_opening_profile_does_not_become_new_financing(self):
        title = "금융그룹 '4000명 새 둥지' 시대 열었다…새로운 100년 시작"
        body = "금융그룹은 헤드쿼터 오프닝 행사를 열었다. 회장은 혁신 비전을 강조했다. 시장은 축사에서 15년간 이어온 투자유치 노력의 결실이라고 말했다."
        self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 7), [])
        for headline, source in (
            ("금융기업 사옥 매각, 현금흐름 개선", "금융기업은 사옥 매각을 결정했다."),
            ("사옥 이전으로 임대료 절감…영업이익 가이던스 상향", "기업은 사옥 이전으로 임대료를 줄여 영업이익 가이던스를 10% 상향했다."),
            ("반도체기업, 미국 법인 출범", "반도체기업은 현지 고객 지원을 위해 미국 법인에 20억원을 출자한다고 발표했다."),
        ):
            self.assertEqual(materiality.assess(headline, source)["disposition"], "keep")

    def test_retail_fx_benefits_are_not_macro_rate_changes(self):
        title = "백화점, 中 국경절 관광객 공략…K패션 행사"
        body = "백화점이 중국 국경절 연휴 관광객 공략에 나선다. 300만원 이상 결제하면 10만원을 즉시 할인하고 환율 우대 혜택을 적용한다."
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "exclude", audit)
        self.assertNotIn("discount_rate", audit["axes"])
        item = alert(title, body)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([item], 1), [])
        self.assertIn("discount_rate", materiality.assess("연준, 기준금리 인하", "연준은 기준금리를 0.25%포인트 인하하고 달러화가 하락했다.")["axes"])

    def test_regulator_abbreviation_and_partner_nouns_are_not_actions(self):
        audit = materiality.assess("파생결합증권 잔액 증가", "금감원은 원금지급형 상품 수요가 늘며 잔액이 증가했다고 밝혔다.")
        self.assertNotIn("labor_cost_or_execution", [item["kind"] for item in audit["evidence"]])
        anniversary = materiality.assess("보험사 일본지사 50주년…함께 성장", "회장은 고객사와 협력사에 감사하며 함께 성장하겠다고 말했다.")
        self.assertEqual(anniversary["disposition"], "exclude", anniversary)
        self.assertEqual(materiality.assess("기업, 인력 감원", "기업은 비용 구조조정을 위해 인력 감원을 발표했다.")["disposition"], "keep")

    def test_industry_changes_precede_local_cpi_and_product_sales_pr(self):
        weak = (
            ("부산 9월 소비자물가 2.7% 상승", "부산의 9월 소비자물가지수는 전년 동월 대비 2.7% 상승했다."),
            ("커피기업, 매장당 매출 3년 새 18% 증가", "공정위 정보공개서 기준 지난해 매장당 매출은 3년 전보다 18% 증가했다."),
            ("키즈 신발 매출 2.5배 증가", "패션기업은 걸음마 신발의 1~9월 매출이 전년 동기 대비 150% 증가했다고 밝혔다."),
            ("명동 패션 매장 고객 10명 중 7명 외국인…쇼핑 뜬다", "패션기업은 명동 플래그십 스토어의 외국인 매출이 열흘간 전년 대비 40% 증가했다고 밝혔다."),
            ("그룹, 사장단 인사…건설사 이사회 의장 내정", "그룹은 사장단 인사를 발표했다. 계열사의 기존 자산 매각 계약이 체결됐고 해외 공장 가동이 늘었다."),
        )
        for (title, body), priority in zip(weak, (1, 1, 1, 1, 0)):
            self.assertEqual(materiality.assess(title, body)["priority"], priority)
        strong = [INDUSTRY_DRIVER_CASES[index][1:] for index in (0, 2, 10)]
        items = [alert(title, body) for title, body in (*weak, *strong)]
        for item in items[:len(weak)]:
            item["score"] = 9999
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts(items, len(strong))
        self.assertEqual({item["source_title"] for item in selected}, {title for title, _body in strong})
        self.assertEqual(materiality.assess("신발기업, 영업이익 가이던스 상향", "신발기업은 영업이익 가이던스를 20% 상향했다.")["priority"], 3)
        self.assertEqual(materiality.assess("임원 인사·이사회 의장 내정, 지분 인수 결정", "기업은 지분 30% 인수를 결정하고 이사회 의장을 내정했다.")["priority"], 3)

    def test_limited_scope_publicity_does_not_fill_unused_core_slots(self):
        cases = (
            ("부산 9월 소비자물가 2.7% 상승", "부산의 9월 소비자물가는 2.7% 상승했다."),
            ("키즈 신발 매출 2.5배 증가", "패션기업은 걸음마 신발 매출이 150% 증가했다고 밝혔다."),
            ("그룹 사장단 인사·이사회 의장 내정", "그룹은 사장단 인사를 발표했다. 계열사는 해외 공장 가동을 확대했다."),
        )
        for title, body in cases:
            item = alert(title, body)
            with patch.object(radar.base, "kst_now", return_value=NOW):
                self.assertEqual(radar.quality_display_alerts([item], 7), [])

    def test_bond_threshold_revisions_share_an_event_but_new_levels_do_not(self):
        titles = (
            "영국 30년물 국채 금리 장중 6％ 돌파…G7서 14년만(종합)",
            "영국 30년물 국채 금리 장중 6% 돌파…G7서 14년만에 처음",
            "영국 30년물 국채 금리 장중 6.1% 돌파",
        )
        items = [alert(title, f"영국 30년물 국채 금리는 장중 {'6.1' if index == 2 else '6.029'}%까지 상승했다.") for index, title in enumerate(titles)]
        for index, item in enumerate(items):
            item["link"] = f"https://www.yna.co.kr/view/bond-threshold-{index}"
        themes = [radar.bond_yield_threshold_theme(item) for item in items]
        self.assertEqual(themes[0], themes[1])
        self.assertNotEqual(themes[1], themes[2])
        seen_keys = [set(production.contract.telegram.alert_seen_keys(item)) for item in items]
        self.assertTrue(any(key.startswith("event:") for key in seen_keys[0] & seen_keys[1]))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            selected = radar.quality_display_alerts(items, 7)
        self.assertEqual(len(selected), 2)
        changed_country = {**items[0], "source_title": titles[0].replace("영국", "미국")}
        changed_tenor = {**items[0], "source_title": titles[0].replace("30년물", "10년물")}
        self.assertNotEqual(themes[0], radar.bond_yield_threshold_theme(changed_country))
        self.assertNotEqual(themes[0], radar.bond_yield_threshold_theme(changed_tenor))

    def test_industry_driver_event_classes_have_source_evidence(self):
        self.assertEqual(len(INDUSTRY_DRIVER_CASES), 24)
        for name, title, body in INDUSTRY_DRIVER_CASES:
            with self.subTest(name=name):
                audit = materiality.assess(title, body)
                self.assertEqual(audit["disposition"], "keep", audit)
                self.assertGreaterEqual(audit["priority"], 2)
                self.assertTrue(audit["evidence"])
                self.assertNotIn("flows", audit["axes"] if name != "ipo_timing" else [])
                with patch.object(radar.base, "kst_now", return_value=NOW):
                    item = alert(title, body)
                    selected = radar.quality_display_alerts([item], 1)
                self.assertEqual(len(selected), 1, item.get("_exclusion_reason"))

    def test_industry_topics_without_a_changed_source_fact_are_not_evidence(self):
        for title, body in (
            ("기업, 우주·양자 미래 비전 공개", "기업은 우주와 양자 산업의 미래를 응원하며 비전을 공유했다."),
            ("기업, CPO·HVDC 혁신 협력 강화", "기업은 CPO와 HVDC 생태계의 혁신 비전을 공유하며 협력을 강화했다."),
            ("AI 기업, 효소 기술 협력 강화", "AI 기업은 효소와 단백질 기술의 미래 혁신 비전을 공유했다."),
        ):
            self.assertEqual(materiality.assess(title, body)["disposition"], "exclude")

    def test_industry_driver_classes_survive_production_candidate_classification(self):
        for name, title, body in INDUSTRY_DRIVER_CASES:
            with self.subTest(name=name):
                item = production.contract.strict.classify({
                    "title": title, "summary": body, "source_body": body, "source_abstract": body,
                    "body_verified": True, "layer": "trusted", "publisher": "연합뉴스", "published": NOW,
                    "link": f"https://www.yna.co.kr/view/industry-driver-{name}",
                }, NOW)
                self.assertIsNotNone(item)
                with patch.object(radar.base, "kst_now", return_value=NOW):
                    selected = radar.quality_display_alerts([item], 1)
                self.assertEqual(len(selected), 1, item.get("_exclusion_reason"))
                core = radar.verified_alert_core(selected[0], selected[0]["news"])
                self.assertTrue(radar.core_sentence_is_complete(core), core)
                self.assertLessEqual(len(core), 100)

    def test_industry_discovery_queries_reach_the_active_collector(self):
        queries = dict(radar.KOREAN_BUSINESS_SEARCH_SOURCES)
        for name, terms in (
            ("AI 전력·광통신 아키텍처 채택", ("HVDC", "CPO", "광트랜시버", "SiC")),
            ("로봇·AI 모델 통합·운용비용 변화", ("휴머노이드", "통합", "추론비용", "인수")),
            ("위성·궤도컴퓨팅 인허가·상업 발사계약", ("발사계약", "환경영향평가", "주파수")),
            ("양자·바이오 AI 실험 검증 이정표", ("극저온", "효소", "검증", "발견")),
            ("재사용 발사체 열차폐·정비·재발사 병목", ("열차폐", "재진입", "지연", "계약")),
            ("궤도 극저온 추진제 저장·ZBO 실증", ("추진제", "ZBO", "저장", "실증")),
        ):
            self.assertIn(name, queries)
            self.assertTrue(all(term in queries[name] for term in terms))

    def test_industry_early_stages_are_not_upgraded_to_commercial_execution(self):
        cases = {name: (title, body) for name, title, body in INDUSTRY_DRIVER_CASES}
        for name, expected in (
            ("orbital_compute_test", ("시험", "추진")),
            ("launch_license_review", ("검토", "환경영향평가")),
            ("ai_customer_financing", ("협상",)),
            ("ai_biology_discovery", ("발견", "검증")),
        ):
            title, body = cases[name]
            item = production.contract.strict.classify({
                "title": title, "summary": body, "source_body": body, "source_abstract": body,
                "body_verified": True, "layer": "trusted", "publisher": "연합뉴스", "published": NOW,
                "link": f"https://www.yna.co.kr/view/industry-stage-{name}",
            }, NOW)
            core = radar.verified_alert_core(item, title)
            self.assertTrue(all(term in core for term in expected), core)
            for invented in ("상업 가동", "확정 수주", "품목허가"):
                self.assertNotIn(invented, core)
        self.assertEqual(materiality.assess(*cases["ai_biology_discovery"])["axes"], ["timeline"])
        self.assertEqual(materiality.assess(*cases["defense_cost_scope"])["axes"], ["timeline"])

    def test_space_bottlenecks_and_research_have_distinct_source_axes(self):
        cases = {name: (title, body) for name, title, body in INDUSTRY_DRIVER_CASES}
        self.assertEqual(materiality.assess(*cases["reusable_launch_bottleneck"])["axes"], ["earnings", "timeline"])
        for name in ("thermal_protection_validation", "propellant_storage_validation"):
            self.assertEqual(materiality.assess(*cases[name])["axes"], ["timeline"])
        for title, body in (
            ("Reusable rocket turnaround delayed", "The rocket's turnaround was delayed by five days after heat shield tile damage."),
            ("Spacecraft heat shield test validated", "The spacecraft heat shield was validated through ten thermal cycling tests."),
            ("Orbital propellant zero-boil-off test", "The orbital propellant zero-boil-off storage system was demonstrated for four months."),
        ):
            self.assertEqual(materiality.assess(title, body)["disposition"], "keep")

    def test_space_supplier_theme_alone_is_not_exposure_evidence(self):
        title = "로켓 초내열합금 기업, 독점 공급 수혜 기대"
        body = "소재기업은 초내열합금과 탄소복합재를 제조한다. 향후 우주 시장 성장의 수혜를 기대한다."
        self.assertLess(materiality.assess(title, body)["priority"], 2)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_space_storage_plans_remain_plans_and_not_heat_shield_adoption(self):
        title = "우주선 추진제 ZBO 저장 도입 검토"
        body = "우주선 개발사는 액체 메탄 추진제의 ZBO 저장 도입을 검토 중이다."
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        self.assertIn("검토", core)
        self.assertNotIn("열차폐", core)
        self.assertTrue(all(evidence["stage"] == "early_signal" for evidence in materiality.assess(title, body)["evidence"]))

    def test_industry_coverage_does_not_bypass_source_body_verification(self):
        for name, title, body in INDUSTRY_DRIVER_CASES:
            item = {**alert(title, body), "body_verified": False}
            self.assertEqual(radar.verified_materiality_axes(item), [], name)
            with patch.object(radar.base, "kst_now", return_value=NOW):
                self.assertEqual(radar.quality_display_alerts([item], 1), [], name)

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

    def test_funding_headline_owns_hbm_background_and_keeps_review_stage(self):
        title = "HBM 투자 바쁜 메모리기업…미국 자회사 자금조달 고심"
        body = ("메모리기업의 HBM 생산량은 전년보다 30% 증가했다. "
                "이에 따라 메모리기업은 자회사의 외부자본 활용을 위해 내주는 지분 가치와 "
                "메모리기업 자체 자금의 활용 가치를 면밀히 비교 검토 중인 것으로 알려졌다. "
                "연구원은 지분을 매각할 경우 150억달러가 확보될 것으로 예상했다.")
        item = {**alert(title, body), "telegram_core_fact": "메모리기업의 HBM 생산량은 전년보다 30% 증가했다."}
        self.assertEqual(materiality.focus_kind(title), "financing")
        core = radar.verified_alert_core(item, title)
        for value in ("외부자본", "자체 자금", "검토 중", "알려졌다"):
            self.assertIn(value, core)
        self.assertNotIn("30%", core)
        self.assertNotIn("150억", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertTrue(all(e["stage"] == "early_signal" for e in materiality.assess(title, body)["evidence"]))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_earnings_consensus_cannot_become_actual_or_old_quarter_results(self):
        title = "메모리기업, 이번 주 3Q 실적 발표…영업이익 증가 전망"
        body = ("증권사가 집계한 메모리기업의 3분기 실적 컨센서스는 매출 20조원, 영업이익 10조원이다. "
                "전년 동기 대비 매출은 30%, 영업이익은 50% 증가한 규모다. "
                "메모리기업은 지난 2분기 영업이익 8조원을 기록했다. "
                "메모리기업은 오는 8일 잠정실적을 발표한다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep")
        self.assertTrue(all(e["stage"] == "early_signal" for e in audit["evidence"]), audit)
        self.assertNotIn("8조", str(audit["evidence"]))
        item = {**alert(title, body), "telegram_core_fact": "메모리기업은 지난 2분기 영업이익 8조원을 기록했다."}
        core = radar.verified_alert_core(item, title)
        self.assertIn("컨센서스", core)
        self.assertIn("10조", core)
        self.assertNotIn("8조", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))

    def test_current_earnings_beat_is_not_downgraded_by_previous_forecast(self):
        title = "기업, 3분기 영업이익 발표…컨센서스 상회"
        body = "증권사 컨센서스는 영업이익 1조원이었다. 기업은 3분기 영업이익 2조원을 공시했다."
        self.assertTrue(any(e["stage"] == "reported_change" for e in materiality.assess(title, body)["evidence"]))

    def test_sanctions_response_needs_source_economic_measures_not_political_rhetoric(self):
        title = '이란 대통령 "경제전쟁 대응 새 조치 도입"'
        body = ("이란 대통령은 경제전쟁 대응을 위한 새로운 조치를 도입하고 있다고 밝혔다. "
                "이란 정부는 환율과 필수 물자 공급을 점검했다고 보도됐다.")
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        self.assertIn("도입하고 있다고 밝혔다", core)
        self.assertIn("환율·필수물자", core)
        self.assertNotIn("이란 이란", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertEqual(materiality.assess(title, body)["transmission_scope_rank"], 2)
        vague = materiality.assess(title, "이란 대통령은 경제전쟁에서 반드시 승리해야 한다고 강조했다.")
        self.assertNotEqual(vague["disposition"], "keep")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_complete_low_materiality_core_is_not_telegram_eligible(self):
        title = "원·달러 NDF 최종 호가"
        body = "원·달러 NDF 1개월물은 1357.3/1357.7원에 최종 호가되며 거래를 마쳤다."
        item = alert(title, body)
        self.assertIn("NDF", radar.verified_alert_core(item, title))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([item], 1), [])

    def test_manufacturing_layoffs_are_not_discarded_as_campaign_rhetoric(self):
        title = "트럼프 유세 앞두고 트럭 공장 1400명 해고"
        body = "트럭 제조기업은 공장에서 직원 1400명을 해고했다. 트럼프의 선거 유세가 예정돼 있다."
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep")
        self.assertIn("labor_cost_or_execution", {e["kind"] for e in audit["evidence"]})
        self.assertNotEqual(materiality.assess("트럼프 유세, 고용 확대 약속", "트럼프는 유세에서 공장 일자리를 늘려야 한다고 강조했다.")["disposition"], "keep")

    def test_similar_source_searches_are_configured_without_forcing_publication(self):
        searches = dict(radar.KOREAN_BUSINESS_SEARCH_SOURCES)
        for name in ("반도체 자회사·설비투자 자금조달", "AI 인프라 자산매각·담보금융·재임차", "국내외 제조업 공장 감원·생산축소"):
            self.assertIn(name, searches)
        self.assertIn("site:news1.kr", searches["중동 경제전·원유·해운 리스크"])
        unverified = {**alert("AI 기업, GPU 매각 자금조달", "AI 기업은 GPU를 매각해 자금을 조달하는 거래를 검토한다."), "body_verified": False}
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([unverified], 1), [])

    def test_bare_issuer_metadata_cannot_be_a_market_news_headline(self):
        title = "신한은행"
        body = "신한은행은 자본재 산업 금융지원 업무협약을 체결했다. 양측은 생산자금 지원 플랫폼을 연계한다."
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "exclude")
        self.assertEqual(audit["reason"], "source_headline_without_event")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_agency_program_overview_is_not_new_procurement_or_rule_change(self):
        title = '"필수의약품 수급불안 없다"…정부주도 공급[식약처가 바꾼다]'
        body = ("식약처, 의료현장 필수의약품 공적 공급 확대. "
                "정부는 올해 6월부터 공적 공급체계를 가동했다. "
                "지난 9월에는 기존 의약품 10개 품목을 긴급도입 대상으로 전환했다. "
                "공적 공급제도를 활용하는 것은 민간 공급만으로 확보가 어려운 의약품에 정부가 개입하기 위해서다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "exclude", audit)
        self.assertEqual(audit["reason"], "agency_role_overview_not_new_industry_event")
        current = materiality.assess(title, "식약처는 오늘 제조기업과 신규 의약품 공급 계약 500억원을 체결했다. " + body)
        self.assertEqual(current["disposition"], "keep", current)
        self.assertGreaterEqual(current["priority"], 2, current)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_generic_technology_trend_cannot_own_the_core(self):
        title = "[AI위클리] AI 경쟁 기준 달라졌다…성능 넘어 실행으로"
        sentence = "국산 AI 반도체의 성능을 실제 산업 현장에서 검증하는 움직임도 이어지고 있다."
        body = ("최근 AI 경쟁이 실제 업무와 산업 현장에서 성과를 내는 단계로 옮겨가고 있다. "
                "AI 반도체와 보안 기술이 고도화되면서 실행하는 AI 경쟁이 본격화하고 있다. " + sentence)
        self.assertFalse(materiality.evidence_is_new_event("technology_or_clinical_stage", sentence))
        audit = materiality.assess(title, body)
        self.assertNotEqual(audit["disposition"], "keep", audit)
        self.assertLess(audit["priority"], 2, audit)
        self.assertEqual(audit["evidence"], [])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_weekly_label_retains_specific_new_commercial_fact(self):
        title = "[AI위클리] AI 반도체 경쟁, 성능 넘어 공급 계약으로"
        body = ("AI 반도체 회사는 오늘 고객과 1조원 규모의 공급 계약을 체결했다. "
                "AI 반도체 검증 움직임도 이어지고 있다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep", audit)
        self.assertGreaterEqual(audit["priority"], 2, audit)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([alert(title, body)], 1)), 1)

    def test_submission_word_is_not_shipments(self):
        title = "중학교 신입생 배정 계획 확정"
        body = "졸업예정자들은 중학교에 대해 지망순위를 기록한 배정원서를 제출하면 된다."
        audit = materiality.assess(title, body)
        self.assertNotEqual(audit["disposition"], "keep", audit)
        self.assertEqual(audit["evidence"], [])
        actual = materiality.assess("반도체 기업, 3분기 출하량 30% 증가", "회사의 3분기 반도체 출하량은 전년비 30% 증가했다.")
        self.assertEqual(actual["disposition"], "keep", actual)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_exhibition_cannot_republish_existing_investment_plan(self):
        title = "삼성전자, 용인 과학축제 참가…국가산단 청사진 제시"
        body = ("삼성전자는 과학축제에 참가해 전시를 운영했다. "
                "삼성전자는 용인 국가산단에 약 360조원을 투자할 계획이다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["reason"], "exhibition_foreground_not_new_investment")
        actual = materiality.assess("삼성전자, 용인 새 공장 착공…축제서 진행 현황 공개",
                                    "삼성전자는 오늘 용인 반도체 공장을 착공했다. " + body)
        self.assertEqual(actual["disposition"], "keep", actual)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_investment_headline_cannot_hide_exhibition_foreground_in_body(self):
        title = '삼성전자, "360조 투자" 용인 반도체 산단 "이렇게 건설됩니다"'
        body = ('삼성전자는 국가산업단지의 미래 모습과 에너지 관리 방안을 주민에게 소개했다.\n'
                '삼성전자는 용인 사이버 과학축제에 참가했다.\n'
                '청사진과 에너지 인프라를 주제로 전시를 구성했다.\n'
                '삼성전자는 용인 국가산단에 약 360조원을 투자할 계획이다.')
        self.assertEqual(materiality.assess(title, body)['reason'], 'exhibition_foreground_not_new_investment')
        with patch.object(radar.base, 'kst_now', return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])
        actual = '삼성전자는 용인 반도체 공장을 오늘 착공했다.\n' + body
        self.assertEqual(materiality.assess(title, actual)['disposition'], 'keep')

    def test_personal_finance_advice_is_not_new_market_flow(self):
        title = "배당주 말고 S&P500…전문가가 말한 자산 키우는 법"
        body = ("작가는 매달 배당금이 들어오는 대신 주가 상승에 따른 수익은 크지 않다고 설명했다. "
                "배당 상품의 수익률은 일반적으로 10% 정도이며 장기 투자자는 지수를 사라고 조언했다.")
        audit = materiality.assess(title, body)
        self.assertEqual(audit["reason"], "investment_method_explainer_not_new_market_event")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_fx_outlook_core_keeps_analyst_target_and_horizon(self):
        title = "원·달러 환율 다시 오르나…1400원대 넘어설 전망"
        body = ("원·달러 환율이 1330원대까지 급락한 뒤 다시 상승할 것이라는 전망이 나왔다. "
                "4일 IBK투자증권에 따르면 향후 원·달러 환율이 다시 상승하는 흐름으로 전개될 것으로 전망했다. "
                "올해 연말 환율은 1400원 전후로 예상했으며 대외 요인 악화 가능성도 열어둘 필요가 있다고 판단했다.")
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for expected in ("IBK투자증권", "올해 연말", "1400원 전후", "전망했다"):
            self.assertIn(expected, core)
        self.assertNotIn("1330", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong in (
            core.replace("IBK투자증권", "다른증권"),
            core.replace("1400", "1500"),
            core.replace("올해 연말", "내년 연말"),
            core.replace("전망했다", "기록했다"),
        ):
            with self.subTest(wrong=wrong):
                self.assertIn("fx_forecast_attribution_target_or_horizon_mismatch",
                              radar.source_core_fact_errors({**item, "telegram_core_fact": wrong}))
                self.assertFalse(radar.source_output_aligned({**item, "telegram_core_fact": wrong}))
        vague = materiality.assess(title, "전문가는 앞으로 환율 상승을 전망했다.")
        self.assertNotIn("attributed_fx_forecast", {e["kind"] for e in vague["evidence"]})
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_gpu_asset_financing_core_preserves_discussion_not_sale_completion(self):
        title = "11조 규모 엔비디아 칩 파는 아마존"
        body = ("파이낸셜타임스에 따르면 아마존은 최근 투자자들과 접촉해 미국 데이터센터에 배치된 "
                "약 80억달러(약 11조원) 규모의 엔비디아 그레이스 블랙웰 칩을 특수목적기구(SPV)로 이전하는 방안을 논의하고 있다. "
                "엔비디아 역시 금융회사들과 AI 인프라 전용 금융 플랫폼을 구축하고 있다.")
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        self.assertEqual(materiality.focus_kind(title), "asset_financing")
        for expected in ("아마존", "80억달러", "그레이스 블랙웰", "특수목적기구(SPV)", "논의 중"):
            self.assertIn(expected, core)
        self.assertLessEqual(len(core), radar.GAMEJOA_CORE_MAX_CHARS)
        self.assertNotIn("완료", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong in (
            core.replace("아마존", "엔비디아"),
            core.replace("80억", "90억"),
            core.replace("그레이스 블랙웰", "호퍼"),
            core.replace("논의 중이다", "완료했다"),
            "엔비디아는 금융회사들과 AI 인프라 전용 금융 플랫폼을 구축하고 있다.",
        ):
            with self.subTest(wrong=wrong):
                self.assertIn("asset_financing_actor_amount_or_stage_mismatch",
                              radar.source_core_fact_errors({**item, "telegram_core_fact": wrong}))
                self.assertFalse(radar.source_output_aligned({**item, "telegram_core_fact": wrong}))
        self.assertIn("asset_financing_actor_amount_or_stage_mismatch", radar.source_core_fact_errors({
            **item, "source_body": "아마존은 80억달러 규모의 그레이스 블랙웰 칩 매각을 검토 중이다.",
            "telegram_core_fact": core,
        }))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_factory_tariff_statement_keeps_rate_condition_and_grace_period(self):
        title = '격전지 간 트럼프 "美에 공장 안 지으면 관세 300%까지 부과"'
        old = ('트럼프 대통령은 전날에도 한국이 알래스카 액화천연가스 사업에 투자하지 않을 경우 '
               '관세 인상 가능성을 시사한 바 있다.')
        body = ('트럼프 대통령은 지원유세에서 "우리는 그들이 여기에 공장을 지을 수 있도록 약 1년 반 정도의 기회를 준다"며 '
                '"그들이 그렇게 하지 않으면 우리는 150, 200, 250, 300%의 관세를 부과한다"고 말했다. ' + old)
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for expected in ("트럼프", "약 1년 반", "미국 공장", "미건설 시", "300%", "말했다"):
            self.assertIn(expected, core)
        self.assertNotIn("알래스카", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong in (old, core.replace("300%", "600%"), core.replace("약 1년 반", "약 2년"),
                      core.replace("미건설 시", "모든 기업에"), core.replace("부과한다고 말했다", "시행을 확정했다")):
            with self.subTest(wrong=wrong):
                self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": wrong}))
                self.assertFalse(radar.source_output_aligned({**item, "telegram_core_fact": wrong}))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_old_lng_statement_cannot_support_new_factory_tariff_headline(self):
        title = '트럼프 "美에 공장 안 지으면 관세 300%까지 부과"'
        body = '트럼프 대통령은 전날 한국이 알래스카 LNG 사업에 투자하지 않을 경우 관세를 인상할 수 있다고 말했다.'
        audit = materiality.assess(title, body)
        self.assertEqual(audit["evidence"], [])
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_factory_tariff_identity_is_terms_bound_not_publisher_or_day_bound(self):
        title = '트럼프 "美에 공장 안 지으면 관세 300%까지 부과"'
        body = ('트럼프 대통령은 "우리는 그들이 여기에 공장을 지을 수 있도록 약 1년 반 정도의 작은 기회를 준다"며 '
                '"그들이 그렇게 하지 않으면 우리는 150, 200, 250, 300%의 관세를 부과한다"고 말했다.')
        first = {**alert(title, body), "supply_chain_theme": "us_canada_tariff_trade:2026-10-04"}
        repeated = {**first, "news": '"미국에 공장 안 지으면 관세 300%"…트럼프 또 압박',
                    "source_title": '"미국에 공장 안 지으면 관세 300%"…트럼프 또 압박',
                    "link": "https://www.etoday.co.kr/news/view/repeated-tariff",
                    "published": "2026-10-05T08:00:00+09:00"}
        identity = materiality.source_event_identity(first)
        self.assertIn("max_rate=300:grace_approx_months=18", identity)
        self.assertEqual(identity, materiality.source_event_identity(repeated))
        self.assertEqual(radar.alert_dedup_key(first), (identity, "event"))
        self.assertEqual(radar.normalize_alert_for_output(first)["supply_chain_theme"], identity)
        for changed in (
            {**first, "source_title": title.replace("300%", "600%"), "source_body": body.replace("300%", "600%")},
            {**first, "source_body": body.replace("약 1년 반", "약 2년")},
            {**first, "source_body": body.replace("그렇게 하지 않으면", "그렇게 하면")},
            {**first, "source_body": body.replace("말했다", "시행을 확정했다")},
            {**first, "body_verified": False},
        ):
            self.assertNotEqual(identity, materiality.source_event_identity(changed))
        state = {"seen": {}}
        with patch.object(radar.telegram, "load_seen_state", return_value=state), \
                patch.object(radar.telegram, "save_seen_state", side_effect=lambda *_args: None):
            radar.telegram.record_seen_alerts([first], NOW)
            fresh, skipped = radar.telegram.filter_previously_seen_alerts([repeated], NOW, "live")
            self.assertEqual(fresh, [])
            self.assertEqual(len(skipped), 1)

    def test_generic_campaign_headline_deduplicates_the_same_factory_tariff_quote(self):
        quote = ('트럼프 대통령은 지원유세에서 "우리는 그들이 여기에 공장을 지을 수 있도록 약 1년 반 정도의 기회를 준다"며 '
                 '"그들이 그렇게 하지 않으면 우리는 150, 200, 250, 300%의 관세를 부과한다"고 말했다.')
        body = '트럼프 미국 대통령은 오하이오주에서 관세 정책을 통해 외국 기업들의 미국 내 투자를 유치한다고 밝혔다.\n' + quote
        first = alert('트럼프 "美에 공장 안 지으면 관세 300%까지 부과"', body)
        repeated = {**alert('격전지 간 트럼프', body), "link": "https://stock.mk.co.kr/news/view/1169503"}
        identity = materiality.source_event_identity(first)
        self.assertEqual(identity, materiality.source_event_identity(repeated))
        self.assertEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(repeated))
        core = radar.verified_alert_core(repeated, repeated["source_title"])
        for expected in ("약 1년 반", "미건설 시", "300%", "말했다"):
            self.assertIn(expected, core)
        self.assertFalse(radar.source_core_fact_errors({**repeated, "telegram_core_fact": core}))
        self.assertTrue(radar.source_core_fact_errors({**repeated, "telegram_core_fact": body.split("\n")[0]}))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([first, repeated], 7)), 1)
        state = {"seen": {}}
        with patch.object(radar.telegram, "load_seen_state", return_value=state), \
                patch.object(radar.telegram, "save_seen_state", side_effect=lambda *_args: None):
            radar.telegram.record_seen_alerts([first], NOW)
            fresh, skipped = radar.telegram.filter_previously_seen_alerts([repeated], NOW, "live")
        self.assertEqual(fresh, [])
        self.assertEqual(len(skipped), 1)

    def test_generic_factory_tariff_identity_cannot_use_an_old_or_unbound_quote(self):
        quote = ('트럼프 대통령은 "공장을 지을 수 있도록 약 1년 반 기회를 준다"며 '
                 '"그렇게 하지 않으면 300%의 관세를 부과한다"고 말했다.')
        lead = '트럼프 대통령은 관세를 통해 외국 기업의 미국 내 투자를 유치한다고 밝혔다.\n'
        for body in (quote, lead + '트럼프 대통령은 전날 ' + quote, lead + '행사를 찾았다.\n' * 3 + quote):
            self.assertEqual(materiality.source_event_identity(alert('격전지 간 트럼프', body)), "")
        for title in ('트럼프, 이란 협상 재개', '트럼프, 격전지서 이란 협상 발언'):
            self.assertEqual(materiality.source_event_identity(alert(title, lead + quote)), "")

    def test_financial_cyber_incident_core_keeps_bank_count_and_scheduled_response(self):
        title = 'AI 해킹 금융권 전방위 확산…당국, 금융사 CEO 긴급소집'
        body = ('예가람저축은행은 해킹 공격으로 약 4만명의 고객 정보가 유출됐다고 밝혔다.\n'
                '이억원 금융위원장과 이찬진 금융감독원장은 이날 오후 정부서울청사에서 '
                '침해 사고가 발생한 금융회사 CEO를 불러 긴급 점검회의를 연다.\n'
                '신한은행이 국회에 제출한 자료에 따르면 공격은 지난달 30일까지 이어졌다.\n'
                '이 과정에서 개인정보 2만5727건이 유출됐다.\n'
                '당국은 금융사가 AI를 활용하도록 망분리 규제를 단계적으로 완화하는 방안을 추진 중이다.')
        item = alert(title, body)
        self.assertEqual(materiality.focus_kind(title), 'cyber_incident')
        core = radar.verified_alert_core(item, title)
        for expected in ('신한은행', '2만5727건', '등이 유출됐다', '금융위원장·금감원장', '이날 오후', '열 예정이다'):
            self.assertIn(expected, core)
        self.assertNotIn('망분리', core)
        self.assertLessEqual(len(core), radar.GAMEJOA_CORE_MAX_CHARS)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        for wrong in (core.replace('신한은행', '농협은행'), core.replace('2만5727건', '4만건'),
                      core.replace('열 예정이다', '열었다'), core.replace('등이', '모든 정보가'), body.split('\n')[-1]):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': wrong}))
        with patch.object(radar.base, 'kst_now', return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_cyber_prevention_blocked_attempts_and_unbound_counts_are_not_breaches(self):
        title = '금융권 AI 해킹 피해 점검'
        for body in (
            '은행은 AI 해킹을 예방하기 위한 모의 해킹 훈련을 했다. 개인정보 4만건 유출 상황을 시연했다.',
            '농협은행은 해킹 공격을 차단했다. 개인정보 유출로 이어지지 않았으며 피해가 없다고 밝혔다.',
        ):
            self.assertNotEqual(materiality.assess(title, body)['disposition'], 'keep')
            self.assertEqual(radar.financial_cyber_incident_fact(title, body), '')
        meeting = ('금융위원장과 금융감독원장은 이날 오후 금융회사 CEO를 불러 긴급 점검회의를 연다.')
        for body in (
            '개인정보 2만5727건이 유출됐다.\n' + meeting,
            '신한은행과 국민은행이 피해를 점검했다.\n이 과정에서 개인정보 2만5727건이 유출됐다.\n' + meeting,
            '지난해 신한은행이 국회에 자료를 제출했다.\n이 과정에서 개인정보 2만5727건이 유출됐다.\n' + meeting,
        ):
            self.assertEqual(radar.financial_cyber_incident_fact(title, body), '')

    def test_multiple_cyber_victims_retain_headcount_basis_and_uncertainty(self):
        title = 'AI 해킹에 비상 걸린 금융…현대캐피탈·예가람저축은행도 뚫렸다'
        body = ('예가람저축은행은 고객 개인정보가 유출된 정황을 확인했다고 밝혔다.\n'
                '유출된 정보는 성명과 연락처다. 유출 규모는 약 4만명에 달하는 것으로 사측은 추정하고 있다.\n'
                '현재까지 AI 침투 흔적은 발견되지 않았다. AI 이용 가능성도 배제할 수 없어 확인할 예정이다.\n'
                '현대캐피탈도 해외 IP를 통한 주택대출 모집인 페이지 공격을 확인했다고 밝혔다.\n'
                '공격받은 페이지는 공개 정보를 확인하는 페이지다.\n'
                '회사는 주택대출 모집인 146명의 일부 개인정보가 유출된 것을 확인했다.')
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for expected in ('현대캐피탈', '대출모집인 146명', '확인했다', '예가람저축은행', '약4만명', '추정했다', '예가람저축은행 공격의 AI 이용은 미확인'):
            self.assertIn(expected, core)
        self.assertLessEqual(len(core), radar.GAMEJOA_CORE_MAX_CHARS)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertFalse(radar.source_core_fact_errors({**item, 'telegram_core_fact': core}))
        for wrong in (core.replace('대출모집인 146명', '고객 146명'), core.replace('약4만명', '4만건'),
                      core.replace('추정했다', '확정했다'), core.replace('AI 이용은 미확인', 'AI 이용을 확인한 것')):
            self.assertTrue(radar.source_core_fact_errors({**item, 'telegram_core_fact': wrong}))
        with patch.object(radar.base, 'kst_now', return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_product_profile_contract_summary_retains_the_contextual_supplier(self):
        title = '신생아 선별검사, 유전체 시대 열린다'
        body = ('쓰리빌리언은 해외에서는 자체 신생아 선별검사 3B-NEO를 앞세워 사업화에 나섰다.\n'
                '올해 출시한 3B-NEO는 704개 핵심 유전자를 분석하는 서비스다.\n'
                '출시 이후 필리핀 정부가 추진하는 신생아 유전체 진단 사업 수행기관으로 선정됐으며 '
                '최근에는 도미니카공화국 모체태아의학 전문 의료센터와 공급 계약을 체결했다.')
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for expected in ("쓰리빌리언은", "필리핀", "도미니카공화국", "공급 계약을 체결했다"):
            self.assertIn(expected, core)
        self.assertLessEqual(len(core), radar.GAMEJOA_CORE_MAX_CHARS)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong in (core.replace('쓰리빌리언은 ', ''), core.replace('쓰리빌리언', '삼성전자'),
                      core.replace('도미니카공화국', '미국'), core.replace('체결했다', '검토 중이다')):
            self.assertTrue(radar.source_core_fact_errors({**item, "telegram_core_fact": wrong}))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_subjectless_contract_cannot_invent_a_supplier(self):
        title = '신생아 선별검사, 유전체 시대 열린다'
        contract = '출시 이후 필리핀 정부의 사업 수행기관으로 선정됐으며 의료센터와 공급 계약을 체결했다.'
        for body in (contract, '회사는 자체 신생아 검사를 출시했다.\n' + contract):
            self.assertEqual(radar.contextual_commercial_fact(title, body), '')
            self.assertIn('commercial_contract_actor_missing', radar.source_core_fact_errors({**alert(title, body), 'telegram_core_fact': contract}))

    def test_capex_supply_effect_core_keeps_fiscal_period_and_analyst_horizon(self):
        title = '반도체 설비투자 확대로 공급 확대? "내후년 하반기는 돼야"'
        body = ('마이크론은 2027 회계연도 상반기에 설비투자에 250억 달러를 투입하고 하반기는 더 늘어날 것이라는 청사진을 제시했다. '
                '류형근 대신증권 연구원은 "설비투자 상향이 즉각적인 생산 증가를 일으키는 것은 아니다"라며 '
                '"유의미한 생산 증가 효과는 2028년 하반기부터 나타날 것"이라고 분석했다.')
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for expected in ("마이크론", "2027회계연도 상반기", "250억달러", "계획했다", "대신증권", "2028년 하반기", "전망했다"):
            self.assertIn(expected, core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertLessEqual(len(core), radar.GAMEJOA_CORE_MAX_CHARS)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong in (core.replace("2027회계연도", "2026회계연도"), core.replace("2028년", "2027년"),
                      core.replace("전망했다", "확정했다")):
            with self.subTest(wrong=wrong):
                self.assertFalse(radar.source_output_aligned({**item, "telegram_core_fact": wrong}))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_market_breadth_core_retains_population_and_comparison_basis(self):
        title = "美 증시 사상 최고치의 착시…AI 빼면 이미 구멍 숭숭"
        body = ('미국 10년물 국채금리가 지난 1일 5.34%까지 치솟았다. '
                '블룸버그통신은 S&P500지수가 사상 최고치에서 2%도 떨어지지 않은 수준에 머물고 있음에도 '
                '시장 내부에서는 상당수 업종과 종목이 고점 대비 5% 이상 하락한 상태라고 전했다.')
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for expected in ("블룸버그", "S&P500", "사상 최고치 대비 2%", "상당수 업종·종목", "고점 대비 5%"):
            self.assertIn(expected, core)
        self.assertNotIn("국채금리", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        self.assertEqual(radar.verified_materiality_axes(item), [])
        self.assertTrue(radar.verified_market_breadth_change(item))
        self.assertFalse(radar.verified_market_breadth_change({**item, "body_verified": False}))
        self.assertFalse(radar.verified_market_breadth_change(alert(title, "시장 내부에서는 종목별 격차가 커지고 있다고 전했다.")))
        for wrong in (core.replace("상당수 업종·종목", "모든 종목"), core.replace("고점 대비", "연초 대비"),
                      core.replace("5%", "15%"), "미국 국채금리는 5.34%까지 치솟았다."):
            with self.subTest(wrong=wrong):
                self.assertFalse(radar.source_output_aligned({**item, "telegram_core_fact": wrong}))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1)

    def test_support_mou_needs_size_terms_or_committed_execution(self):
        title = "신한은행, 공제조합과 금융지원 업무협약"
        body = ("신한은행은 자본재공제조합과 플랫폼 기반 금융지원 업무협약을 체결했다. "
                "양측은 자본재공제조합의 매출채권신용공제와 신한은행 지급결제 플랫폼을 연계해 기업의 제조·생산자금을 지원한다.")
        audit = materiality.assess(title, body)
        self.assertLess(audit["priority"], 2, audit)
        self.assertEqual(audit.get("scope_note"), "support_mou_without_size_terms_or_committed_execution", audit)
        scoped = materiality.assess("은행, 제조기업과 1000억원 투자 자금조달 약정 체결",
                                    body + " 은행은 제조기업과 투자 자금조달 대출 약정 1000억원을 체결했다.")
        self.assertGreaterEqual(scoped["priority"], 2, scoped)
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])

    def test_forum_agenda_is_not_policy_execution_or_new_housing_supply(self):
        title = "서울 전월세시장 불안 해법은…민간임대·장기전세 머리 맞댄다"
        body = ("7일 서울주거포럼 개최. 임대주택 공급체계·세입자 주거안정 논의. "
                "서울시가 민간임대주택 공급 확대와 장기전세주택의 역할 등 세입자 주거 안정을 위한 해법을 모색한다. "
                "이창무 서울특별시 총괄건축가는 '매매시장 규제 강화와 전·월세 시장 불안'을 주제로 기조 발제에 나선다.")
        audit = materiality.assess(title, body)
        self.assertLess(audit["priority"], 2, audit)
        self.assertEqual(audit.get("scope_note"), "forum_policy_opinion_without_announced_instrument_change")
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(radar.quality_display_alerts([alert(title, body)], 1), [])
        for change in (
            "정부는 포럼에서 임대주택 신규 규제를 입법예고했다.",
            "서울시는 포럼에서 임대주택 공급 확대 예산 1000억원을 확정했다.",
        ):
            with self.subTest(change=change):
                self.assertGreaterEqual(materiality.assess("포럼서 임대주택 지원 새 대책 발표", change)["priority"], 2)

    def test_export_milestone_keeps_observed_total_not_conditional_calculation(self):
        title = "'1조 달러 수출국' 초읽기…11월 말~12월 초 한국 수출사 새로 쓴다"
        body = ("올해 1~9월 누적 수출액이 8145억 달러에 달하면서 연간 목표 달성이 가까워졌다. "
                "올해 1~9월 누적 수출액은 8145억 달러로 늘었다. "
                "지난해 연간 수출액 7093억 달러를 이미 넘어섰다. "
                "10~12월 월평균 약 618억 달러를 수출하면 1조 달러를 달성할 수 있다.")
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        self.assertIn("1~9월", core)
        self.assertIn("8145억달러", core)
        self.assertNotIn("618억", core)
        self.assertIn("지난해 연간", core)
        audit = materiality.assess(title, "우리나라의 연간 수출액 1조 달러 달성이 가시권에 들어왔다. " + body)
        self.assertEqual(audit["transmission_scope_rank"], 3)
        self.assertIn("8145", audit["evidence"][0]["source_excerpt"])
        self.assertEqual(audit["evidence"][0]["stage"], "reported_change")
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        with patch.object(radar.base, "kst_now", return_value=NOW):
            self.assertEqual(len(radar.quality_display_alerts([item], 1)), 1, item.get("_exclusion_reason"))

    def test_export_history_cannot_replace_declared_current_release(self):
        title = "건어물 팔던 나라서 반도체 수출국으로…韓수출 1조弗 눈앞 [세쓸통]"
        history = ("1981년에는 수출액 200억 달러를 돌파했고 1986년에는 국제유가 하락과 "
                   "원화 약세, 국제금리 하락 등에 힘입어 첫 무역흑자라는 기념비적인 기록을 세웠습니다.")
        observed = ("산업통상부가 발표한 2026년 9월 수출입동향에 따르면 올해 1~9월 누적 수출액은 "
                    "8145억 달러입니다.")
        body = "우리나라 연간 수출이 1조 달러 시대를 앞두고 있습니다. " + observed + " " + history
        audit = materiality.assess(title, body)
        self.assertEqual(audit["disposition"], "keep", audit)
        self.assertIn(observed, [row["source_excerpt"] for row in audit["evidence"]])
        self.assertNotIn(history, [row["source_excerpt"] for row in audit["evidence"]])
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for value in ("올해", "1~9월", "8145억달러", "집계됐다"):
            self.assertIn(value, core)
        self.assertNotIn("1986", core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong_core in (core.replace("1~9월", "9월"), core.replace("8145", "1855"), history):
            self.assertIn("national_export_observed_period_total_mismatch",
                          radar.source_core_fact_errors({**item, "telegram_core_fact": wrong_core}))
        for annotation in ("(약 1,098조원)", "(원화 환산 확인 불가)"):
            converted = core.replace("8145억달러", "8145억달러" + annotation)
            self.assertTrue(materiality.core_focus_aligned(title, converted), converted)
            self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": converted}))
            self.assertEqual(radar.compact_alert_block_errors(
                f"1) {title}\n- 핵심: {converted}\n- 출처: https://www.newsis.com/view/export-current"
            ), [])

    def test_compensation_core_uses_issuer_cost_horizon_and_margin_forecast(self):
        title = "반도체 호황에 성과급↑…메모리 3사 실적에 '보상비용' 변수"
        heading = title + ' 마이크론 실적발표서 "성과급, 매출총이익률 전망에 큰 영향" 삼성·SK하이닉스 3분기 충당금 확대 전망'
        cost = ('머피 CFO는 다음 분기 매출총이익률 전망과 관련한 질문에 "성과급은 매출총이익률 전망에 큰 영향을 미치는 요인"이라며 '
                '성과급과 신규 생산시설 초기 가동 비용 등으로 2027회계연도 1분기(9∼11월)에 약 10억달러(1조3천500억원)의 추가 비용이 발생할 것으로 예상했다.')
        body = (heading + '\n마크 머피 마이크론 최고재무책임자(CFO)는 최근 콘퍼런스콜에서 수익성 영향을 설명했다.\n'
                + cost + '\n마이크론은 매출총이익률이 4분기 87%에서 성과급을 비롯한 비용 증가 영향에 따라 다음 분기에는 약 86.3%로 낮아질 것으로 관측했다.')
        audit = materiality.assess(title, body)
        self.assertNotIn(heading, [row["source_excerpt"] for row in audit["evidence"]])
        self.assertEqual(materiality.focus_kind(title), "earnings")
        item = alert(title, body)
        core = radar.verified_alert_core(item, title)
        for value in ("마이크론", "성과급·신규시설 초기 가동", "2027회계연도 1분기", "10억달러", "예상했다", "86.3%", "전망했다"):
            self.assertIn(value, core)
        self.assertTrue(radar.core_sentence_is_complete(core))
        self.assertLessEqual(len(core), 100)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong_core in (core.replace("마이크론", "삼성전자"), core.replace("1분기", "4분기"), core.replace("10억", "26억"), core.replace("예상했다", "집행했다")):
            self.assertIn("compensation_cost_forecast_actor_period_or_amount_mismatch",
                          radar.source_core_fact_errors({**item, "telegram_core_fact": wrong_core}))

    def test_conditional_crypto_market_entry_keeps_issuer_date_and_precondition(self):
        title = "'최대 XRP DAT' 에버노스 “XRP 굴려 운용수익 낸다, 규제 열리면 韓 진출”[인터뷰]"
        body = ('조만간 미국 나스닥시장에서 첫 거래를 시작하는 에버노스 홀딩스(Evernoth Holdings·주식 티커명 ‘XRPN’)라는 기업이 XRP를 보유한 상장기업으로 등극하게 된다. '
                'XRP 투자수단이 되겠다는 비전을 달성하기 위해 SPAC 합병을 통한 패스트트랙을 택했다. '
                '에버노스 CEO는 “XRP를 체인 위에서 운용해 수익을 얻는 일을 할 것이고, 그 재원으로 더 많은 XRP를 축적할 것”이라고 밝혔다. '
                '한국 내 규제가 명확해진다는 전제 하에서 한국 사업 확대와 법인 설립 가능성을 열어 두겠다고 강조했다. '
                '오는 8일 나스닥에 상장돼 그 날부터 XRPN 티커로 첫 거래를 시작한다. '
                '규제당국의 동의를 받은 뒤 진행하고 싶다. 그 이후에 검토할 것이다.')
        item = alert(title, body)
        audit = materiality.assess(title, body)
        kinds = {row["kind"] for row in audit["evidence"]}
        self.assertIn("capital_listing_stage", kinds)
        self.assertNotIn("rates_fx_or_macro", kinds)
        self.assertNotIn("market_price_or_flow", kinds)
        core = radar.verified_alert_core(item, title)
        for value in ("에버노스 CEO", "XRP 운용수익", "규제 명확화 후", "한국 진출 검토", "나스닥 상장·첫 거래", "8일 예정"):
            self.assertIn(value, core)
        self.assertFalse(radar.source_core_fact_errors({**item, "telegram_core_fact": core}))
        for wrong_core in (core.replace("8일", "4일"), core.replace("규제 명확화 후 ", ""), core.replace("검토", "시행")):
            self.assertIn("market_entry_conditions_issuer_or_first_trade_date_mismatch",
                          radar.source_core_fact_errors({**item, "telegram_core_fact": wrong_core}))

    def test_digital_treasury_and_spac_route_profile_are_not_macro_or_new_funding(self):
        title = "에버노스 CEO, 기업 소개 인터뷰"
        body = ('에버노스 CEO는 “우리는 액티브 트레저리(active treasury)이며 운용수익을 축적할 것”이라고 밝혔다. '
                '투자수단이 되겠다는 비전을 달성하기 위해 SPAC 합병을 통한 패스트트랙을 택했다. '
                '반면 XRPN(나스닥 상장사인 에버노스 홀딩스)은 다르다.')
        audit = materiality.assess(title, body)
        self.assertFalse(audit["evidence"], audit)

    def test_export_history_or_future_target_alone_is_not_current_data(self):
        title = "한국 연간 수출 1조 달러 목표 눈앞"
        for sentence in (
            "1981년에는 수출액 200억 달러를 돌파했고 1986년에는 첫 무역흑자를 기록했습니다.",
            "올해 10~12월 월평균 618억 달러를 수출하면 연간 수출액 1조 달러를 달성할 수 있다.",
            "올해 1~9월 누적 수출액은 8145억 달러로 전망된다.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(materiality.national_export_observation(sentence))
                audit = materiality.assess(title, sentence)
                self.assertLess(audit["priority"], 2, audit)
                self.assertFalse(audit["evidence"], audit)

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


class ForegroundAndEventIdentityTests(unittest.TestCase):
    def test_remaining_publicity_cannot_borrow_background_market_facts(self):
        cases = (
            ('이스라엘 대통령 "트럼프, 최고의 친구" 우호 과시', '대통령은 트럼프와 좋은 관계라고 말했다. 영국은 앞서 정착촌 생산품 수입을 금지했다.'),
            ('찍는 맛 살린 아이폰 프로 맥스', '[리뷰] 아이폰 써보니 카메라가 개선됐다. 칩 패키징 변화로 지속 성능이 40% 향상됐다.'),
            ('모기 잡는데 레이저? 모기 저격수 등장', '스타트업은 라이다 제품의 월 생산량을 5000대로 늘려 소비자에게 판매할 계획이다.'),
            ('국책은행, 영화 투자 외부 요청 없었다', '은행은 기존 절차에 따라 투자했다고 밝혔다. 앞서 제작사에 300억원을 출자했다.'),
            ('트럼프, 공화당 승리하면 모두 5000달러', '트럼프는 선거 유세에서 공화당 지지를 호소했다. G7의 비축유 방출 성과를 강조했다.'),
        )
        for title, body in cases:
            with self.subTest(title=title):
                audit = materiality.assess(title, body)
                self.assertEqual(audit['disposition'], 'exclude', audit)

    def test_actual_policy_and_business_changes_survive_publicity_guards(self):
        cases = (
            ('아이폰 리뷰…분기 판매량 12% 증가', '아이폰의 분기 판매량이 12% 증가했다고 회사가 밝혔다.'),
            ('모기 퇴치 센서 공급계약 체결', '상장사는 병원 고객과 500억원 센서 공급계약을 체결했다.'),
            ('대통령, 관세 인하 합의…우호 과시', '대통령은 한국산 자동차 관세를 25%에서 15%로 낮추기로 합의했다.'),
            ('국책은행, 외부 요청 없었다…신규 투자 철회', '은행은 제작사에 대한 신규 투자를 철회하고 출자액을 감액하기로 결정했다.'),
        )
        for title, body in cases:
            with self.subTest(title=title):
                audit = materiality.assess(title, body)
                self.assertEqual(audit['disposition'], 'keep', audit)
                self.assertGreaterEqual(audit['priority'], 2, audit)

    def test_g7_separate_foreground_sentences_retain_quantity_duration_and_identity(self):
        title = 'G7, 비축유 1억배럴 푼다…긴급 처방'
        body = (
            '주요 7개국(G7)이 총 1억배럴 규모의 석유 비축분을 공동 방출하기로 했다. '
            '국제에너지기구와 협력해 4개월 동안 1억 배럴을 방출할 예정이다. '
            'G7은 에너지 수출 금지는 하지 않겠다고 밝혔다.'
        )
        item = radar.normalize_alert_for_output(alert(title, body))
        self.assertIn('4개월', item['telegram_core_fact'])
        self.assertIn('1억배럴', item['telegram_core_fact'])
        self.assertNotIn('수출', item['telegram_core_fact'])
        self.assertEqual(radar.source_core_fact_errors(item), [])
        self.assertTrue(radar.source_output_aligned(item), item)
        other = alert('G7, 4개월간 비축유 방출', 'G7은 비축유 1억 배럴을 4개월 동안 방출하기로 합의했다.')
        self.assertEqual(materiality.source_event_identity(item), materiality.source_event_identity(other))

    def test_oil_project_identity_uses_verified_country_context_not_only_headline(self):
        first = alert('대미투자 이견 와중에 트럼프, 11조원 석유 프로젝트 추진',
                      '트럼프 대통령은 한국과의 협상에 따라 84억달러 규모의 원유 회수 증진 프로젝트가 추진된다고 발표했다. 프로젝트 위치와 기업은 밝히지 않았다.')
        second = alert('트럼프, 한국 석유 프로젝트 84억달러 발표', first['source_body'])
        self.assertEqual(materiality.source_event_identity(first), materiality.source_event_identity(second))
        item = radar.normalize_alert_for_output(first)
        self.assertIn('원유 회수 증진', item['telegram_core_fact'])
        self.assertIn('84억달러', item['telegram_core_fact'])
        self.assertNotIn('미국', item['telegram_core_fact'])
        self.assertEqual(radar.source_core_fact_errors(item), [])
        self.assertTrue(radar.source_output_aligned(item), item)

    def test_quoted_alaska_bill_is_summarized_as_a_bill_not_a_tariff(self):
        title = '트럼프 "韓 알래스카 투자 합의않으면 두배로 청구" 노골적 압박'
        body = (
            '트럼프는 한국의 알래스카 LNG 투자를 확정 발표했다. '
            '이어 해당 질문을 한 취재진에 "그들이 합의를 하지 않았다고 하느냐"고 되물으며 '
            '"곧 합의하지 않는다면 (청구금을) 두 배로 올릴 것이라고 전하라"고 말했다. '
            '앞서 트럼프는 한국 정부가 500억달러를 투자한다고 발표했다.'
        )
        item = radar.normalize_alert_for_output(alert(title, body))
        self.assertIn("곧 합의하지 않으면", item["telegram_core_fact"])
        self.assertIn("청구액을 두 배", item["telegram_core_fact"])
        self.assertNotIn("관세", item["telegram_core_fact"])
        self.assertNotIn("500억", item["telegram_core_fact"])
        self.assertEqual(radar.source_core_fact_errors(item), [])
        self.assertTrue(radar.source_output_aligned(item), item)

    def test_g7_summary_and_cross_source_identity_keep_release_not_export_background(self):
        title = 'G7 "4달 동안 비축유 1억배럴 방출"…트럼프 압박'
        body = (
            '주요 7개국(G7)이 향후 4개월에 걸쳐 비축 경유와 원유 1억 배럴을 방출하기로 합의했다. '
            'G7은 경유 수출을 금지하지 않기로 의견을 모았다.'
        )
        core = radar.detailed_article_core(title, body)
        self.assertIn("4개월", core)
        self.assertIn("1억 배럴", core)
        self.assertNotIn("수출", core)
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])
        self.assertTrue(radar.source_output_aligned(radar.normalize_alert_for_output(alert(title, body))))
        other = alert('G7 "4개월간 경유·원유 1억배럴 방출"', body)
        self.assertEqual(radar.alert_dedup_key(alert(title, body)), radar.alert_dedup_key(other))

    def test_continued_dialogue_does_not_promote_old_tariff_changes(self):
        title = 'Key Trump ally urges continued US-China engagement on rare earths'
        body = 'The senator called for continued dialogue. Under the earlier deal, the US cut tariffs and Chinese export controls were paused.'
        audit = materiality.assess(title, body)
        self.assertEqual(audit["priority"], 1)
        self.assertEqual(audit["reason"], "continued_dialogue_without_new_policy_or_supply_terms")

    def test_incidental_economic_words_do_not_rescue_nonmarket_foreground(self):
        cases = (
            ("한화투자증권, 업비트와 인스타툰 론칭 이벤트", "고객들이 디지털자산을 친근하게 접하도록 협력 기회를 발굴한다. 경품을 지급한다."),
            ("광주시의사회, 네팔 대홍수 피해 지역에 구호대 파견", "의사회는 홍수 피해 주민에게 구호품 2500만원을 지원했다."),
            ("총리, 연대와 통합 강조…홍익인간 정신", "총리는 홍수 피해 구조대의 노고에 감사했다."),
            ("시장, 성매매 의혹 마타도어 비판", "시장은 의혹을 확대 재생산한 데 대해 사과를 요구했다."),
            ("부산대, 지역 생산유발 1.5조원", "연구 결과 지난해 고용 1만2000명과 생산유발 1.5조원 증가 효과를 기록했다."),
            ("식당 테이블 간장 금지? 식약처 사실 아님", "앞서 지난 7월 고시를 개정했다. 이번 간장 금지 주장은 사실이 아니다."),
            ("복잡한 전력망 운영 노하우…한국전력 제2의 삼전닉스", "한국전력은 정전 시간이 세계 2위로 짧다고 밝혔다."),
        )
        for title, body in cases:
            with self.subTest(title=title):
                audit = materiality.assess(title, body)
                self.assertFalse(audit["disposition"] == "keep" and audit["priority"] >= 2, audit)

    def test_new_operating_damage_and_hard_changes_remain_eligible(self):
        cases = (
            ("폭염 속 서울 아파트 정전 잇따라", "폭염으로 변압기 과부하 정전이 발생해 1000세대 전력 공급이 중단됐다."),
            ("태풍에 반도체 공장 생산 중단", "태풍 침수 피해로 반도체 공장의 생산을 중단했다."),
            ("반도체 설비투자 확대", "기업은 내년 반도체 설비투자를 2배 늘릴 계획이라고 밝혔다."),
            ("대학교 기술기업, 반도체 공급계약 체결", "대학교 기술기업은 반도체 고객과 500억원 공급계약을 체결했다."),
        )
        for title, body in cases:
            with self.subTest(title=title):
                audit = materiality.assess(title, body)
                self.assertEqual(audit["disposition"], "keep", audit)
                self.assertGreaterEqual(audit["priority"], 2, audit)

    def test_dram_share_core_preserves_period_basis_values_and_gap(self):
        title = "마이크론, D램 2위 SK하이닉스 턱밑 추격…점유율 격차 1%포인트"
        body = (
            "마이크론은 AI 수요로 매출이 빠르게 늘었다. "
            "카운터포인트에 따르면 D램 시장에서 마이크론은 매출 점유율 24%로 3위를 기록했다. "
            "2위 SK하이닉스 점유율은 25%였다. 두 업체 점유율 격차는 1%포인트였다. "
            "2026년 2분기 D램 매출 시장 점유율. "
            "마이크론은 4분기 매출 542억달러를 발표했다."
        )
        core = radar.detailed_article_core(title, body)
        for required in ("카운터포인트", "2026년 2분기", "매출 점유율", "24%", "25%", "1%포인트"):
            self.assertIn(required, core)
        self.assertNotIn("542억", core)
        item = radar.normalize_alert_for_output(alert(title, body))
        self.assertEqual(radar.source_core_fact_errors(item), [])
        self.assertTrue(radar.source_output_aligned(item), item)

    def test_capex_core_is_forward_plan_not_prior_spend_or_reporter_estimate(self):
        title = "연간 설비투자 2배 늘리는 마이크론…삼성·SK 압박"
        body = (
            '마이크론은 "2027회계연도 상반기(9월~2027년 2월) 설비투자는 250억 달러에 이를 것"이라며 '
            '"하반기(2027년 3~8월)에는 자본지출이 더 증가할 것으로 예상한다"고 밝혔다. '
            "보수적인 계산으로 연간 500억 달러를 넘어선다. "
            "마이크론의 투자계획은 정부 지원금을 차감한 순액을 기준으로 한다. "
            "마이크론의 2026회계연도 설비투자 규모는 274억 달러였다."
        )
        core = radar.detailed_article_core(title, body)
        for required in ("마이크론", "2027회계연도", "상반기", "순설비투자", "250억 달러", "하반기", "예상"):
            self.assertIn(required, core)
        self.assertNotIn("274억", core)
        self.assertNotIn("500억", core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertEqual(radar.source_core_fact_errors({**alert(title, body), "telegram_core_fact": core}), [])

    def test_background_investment_is_not_trade_threat_core(self):
        title = '트럼프, 한국에 알래스카 투자 안 하면 관세 두 배 위협'
        body = '앞서 트럼프는 한국이 500억달러를 투자한다고 발표했다. 트럼프는 한국이 알래스카 투자에 참여하지 않으면 관세를 두 배 올리겠다고 경고했다.'
        core = radar.detailed_article_core(title, body)
        self.assertIn("참여하지 않으면", core)
        self.assertIn("관세", core)
        self.assertNotIn("500억", core)

    def test_cross_publisher_event_identity_keeps_changed_terms_and_stage(self):
        first = alert("트럼프, 한국 알래스카 투자 없으면 관세 두 배 위협", "트럼프는 한국이 알래스카에 투자하지 않으면 관세를 두 배 인상하겠다고 경고했다.")
        second = alert("한국에 알래스카 투자 촉구한 트럼프, 관세 2배 경고", first["source_body"])
        self.assertEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(second))
        self.assertTrue(set(radar.telegram.alert_seen_keys(first)) & set(radar.telegram.alert_seen_keys(second)))
        for title in (
            "트럼프, 한국 알래스카 투자 없으면 관세 세 배 위협",
            "트럼프, 한국 알래스카 투자 없으면 관세 3배 위협",
            "트럼프, 한국 알래스카 투자 조건 관세 두 배 부과 결정",
            "트럼프, 한국 알래스카 투자 없으면 비용 두 배 청구",
        ):
            changed = alert(title, title + "이라고 밝혔다.")
            self.assertNotEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(changed))

    def test_g7_release_has_quantity_and_duration_not_publication_date(self):
        first = alert("G7, 비축유 1억 배럴 방출", "G7은 비축유 1억 배럴을 향후 4개월 동안 방출하기로 합의했다.")
        second = alert("주요 7개국, 비축유 방출 합의", first["source_body"])
        second["published"] = "2026-10-03T12:00:00+09:00"
        self.assertEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(second))
        changed = alert("G7, 비축유 추가 방출", "G7은 비축유 2억 배럴을 향후 4개월 동안 방출하기로 합의했다.")
        self.assertNotEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(changed))
        duration = alert("G7, 비축유 방출 기간 변경", "G7은 비축유 1억 배럴을 향후 6개월 동안 방출하기로 합의했다.")
        self.assertNotEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(duration))

    def test_event_identity_does_not_merge_investment_statement_with_signed_or_denied_deal(self):
        first = alert("트럼프, 한국의 미국 석유 투자 발표", "트럼프는 한국이 미국 석유 사업에 84억 달러를 투자한다고 밝혔다.")
        second = alert("한국의 석유 투자 84억달러 언급한 트럼프", first["source_body"])
        self.assertEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(second))
        for title, body in (
            ("트럼프, 한국 미국 석유 투자 계약 서명", first["source_body"]),
            ("한국, 트럼프 미국 석유 투자 발표 부인", first["source_body"]),
            (first["news"], first["source_body"].replace("84억", "85억")),
        ):
            self.assertNotEqual(radar.alert_dedup_key(first), radar.alert_dedup_key(alert(title, body)))

    def test_stockpile_refill_cannot_reuse_background_release_core(self):
        title = "트럼프, 미국 비축유 다시 채운다"
        body = "G7은 비축유 1억 배럴을 4개월간 방출하기로 합의했다. 트럼프는 미국의 비축유를 다시 채우겠다고 발표했다."
        core = radar.detailed_article_core(title, body)
        self.assertIn("채우", core)
        self.assertNotIn("G7", core)
        self.assertNotIn("방출", core)

    def test_hypothetical_psychological_logistics_effect_is_not_actual_supply_disruption(self):
        title = '러 드론, 키이우 교량 타격…차량 통행 중단'
        body = '전문가 “교통·물류 차질과 주민 심리 압박 가능성”\n러시아군의 교량 공격으로 시내 교통 혼잡이 발생했다. 전문가는 러시아군이 물류에 차질을 주면서 주민들에게 심리적 압박을 가하려는 것일 수 있다고 분석했다.'
        audit = materiality.assess(title, body)
        self.assertEqual(audit['disposition'], 'review', audit)
        self.assertEqual(audit['priority'], 1, audit)
        self.assertFalse(audit['evidence'], audit)

    def test_public_opinion_percentages_do_not_become_policy_execution(self):
        title = '英 총리 다시 꺼낸 EU 재가입론…찬성 49%·반대 28.5%'
        body = '영국 총리가 EU 재가입론을 다시 언급했다. EU와의 현재 관계를 유지하면서 무역장벽을 최대한 낮추는 방안에는 48.2%가 찬성했고, 관세동맹 가입은 47.1%, 단일시장 가입은 45.1%의 지지를 받았다.'
        audit = materiality.assess(title, body)
        self.assertEqual(audit['disposition'], 'review', audit)
        self.assertFalse(audit['evidence'], audit)

    def test_actual_policy_execution_is_not_rejected_by_adjacent_poll(self):
        title = '정부, 수입 관세 인하 규정 시행'
        body = '여론조사에서 관세 인하 찬성은 48.2%였다. 정부는 수입 관세를 15%에서 10%로 낮추는 규정을 개정했다.'
        audit = materiality.assess(title, body)
        self.assertEqual(audit['disposition'], 'keep', audit)
        self.assertTrue(any('규정을 개정했다' in item['source_excerpt'] for item in audit['evidence']), audit)

    def test_bond_summary_prefers_observed_yield_change_to_causal_commentary(self):
        title = '[김남현의 채권썰] 금리 단기고점 본 듯, 단 은행채 경계 지속'
        body = '최근 금리 상승에 따른 머니무브와 함께 은행채 발행 증가가 이어질 것으로 보여서다. 이에 따라 주초 4.119%까지 올라 3년10개월만에 최고치를 기록했던 국고3년물 금리는 한달여만에 4%를 밑돌았다.'
        core = radar.detailed_article_core(title, body)
        self.assertIn('국고3년물 금리는 한달여만에 4%를 밑돌았다', core)
        self.assertNotIn('보여서다', core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)

    def test_actual_supply_disruption_survives_following_speculation(self):
        title = '러시아 드론 공격에 원유 운송 중단'
        body = '러시아 드론 공격으로 원유 운송이 중단됐다고 당국이 밝혔다. 전문가는 이번 공격이 심리적 압박을 가하려는 것일 수 있다고 분석했다.'
        audit = materiality.assess(title, body)
        self.assertEqual(audit['disposition'], 'keep', audit)
        self.assertGreaterEqual(audit['priority'], 2, audit)
        self.assertIn('원유 운송이 중단', audit['evidence'][0]['source_excerpt'])

    def test_dated_wire_photo_does_not_become_current_market_evidence(self):
        title = '기업, 신규 공급계약 체결'
        caption = '[현장=AP/뉴시스] 소방관들이 공장 화재를 진압하고 있다. 2026.09.09.'
        fact = '기업은 생산 확대를 위한 신규 공급계약을 체결했다고 밝혔다.'
        body = caption + fact
        cleaned = radar.article_summary_body(body)
        self.assertEqual(cleaned, fact)
        core = radar.detailed_article_core(title, body)
        self.assertIn('신규 공급계약', core)
        self.assertNotIn('2026.09.09', core)
        self.assertNotIn('화재', core)
        self.assertTrue(radar.core_sentence_is_complete(core), core)
        self.assertFalse(radar.core_sentence_is_complete('2026.09.09.' + fact))

    def test_scoped_stockpile_refill_is_not_excluded_only_because_speech_was_at_rally(self):
        title = '트럼프, 미국 비축유 다시 채운다'
        body = '트럼프는 선거 유세에서 발언했다. 트럼프는 미국의 전략비축유를 다시 채우겠다고 발표했다. 앞서 G7은 비축유 1억 배럴을 4개월 동안 방출하기로 합의했다.'
        audit = materiality.assess(title, body)
        self.assertEqual(audit['disposition'], 'keep', audit)
        self.assertGreaterEqual(audit['priority'], 2, audit)
        self.assertTrue(any(item['kind'] == 'energy_stockpile_action' for item in audit['evidence']), audit)
        core = radar.detailed_article_core(title, body)
        self.assertIn('채우', core)
        self.assertNotIn('G7', core)

    def test_unverified_body_cannot_invent_dedup_terms(self):
        item = alert("G7, 비축유 방출", "G7은 비축유 1억 배럴을 4개월 동안 방출한다.")
        item["body_verified"] = False
        self.assertEqual(materiality.source_event_identity(item), "")

    def test_article_tracking_aliases_keep_identifying_query_parameters(self):
        first = alert("기업, 고객 계약 체결", "기업은 고객과 공급계약을 체결했다.")
        first["link"] = "https://www.edaily.co.kr/News/Read?newsId=123&mediaCodeNo=257&utm_source=naver"
        second = {**first, "link": "https://www.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=123&utm_medium=referral"}
        self.assertTrue(set(radar.telegram.alert_seen_keys(first)) & set(radar.telegram.alert_seen_keys(second)))
        one = radar.telegram.canonical_article_url(first["link"])
        two = radar.telegram.canonical_article_url(first["link"].replace("newsId=123", "newsId=124"))
        self.assertNotEqual(one, two)
        self.assertIn("newsId=123", one)

    def test_persistent_dedup_allows_new_amount_even_with_same_title_and_link(self):
        first = alert("트럼프, 한국의 미국 석유 투자 발표", "트럼프는 한국이 미국 석유 사업에 84억 달러를 투자한다고 밝혔다.")
        state = {"seen": {}}
        with patch.object(radar.telegram, "load_seen_state", return_value=state), \
                patch.object(radar.telegram, "save_seen_state", side_effect=lambda *_args: None):
            radar.telegram.record_seen_alerts([first], NOW)
            changed = {**first, "source_body": first["source_body"].replace("84억", "85억")}
            fresh, skipped = radar.telegram.filter_previously_seen_alerts([changed], NOW, "live")
            repeated, duplicates = radar.telegram.filter_previously_seen_alerts([first], NOW, "live")
        self.assertEqual(len(fresh), 1)
        self.assertEqual(skipped, [])
        self.assertEqual(repeated, [])
        self.assertEqual(len(duplicates), 1)

    def test_legacy_migration_uses_only_self_contained_receipts(self):
        entry = {"title": "트럼프, 한국 알래스카 투자 없으면 관세 두 배 위협", "first_seen_kst": NOW.isoformat(), "lanes": {"live": NOW.isoformat()}}
        state = {"seen": {"old": entry}}
        radar.telegram.migrate_seen_title_aliases(state)
        item = alert("한국에 알래스카 투자 촉구한 트럼프, 관세 2배 경고", "트럼프는 한국이 알래스카에 투자하지 않으면 관세를 두 배 인상하겠다고 경고했다.")
        with patch.object(radar.telegram, "load_seen_state", return_value=state):
            fresh, repeated = radar.telegram.filter_previously_seen_alerts([item], NOW, "live")
            digest, _ = radar.telegram.filter_previously_seen_alerts([item], NOW, "preopen")
        self.assertEqual(fresh, [])
        self.assertEqual(len(repeated), 1)
        self.assertEqual(len(digest), 1)

    def test_legacy_coarse_receipt_cannot_be_bypassed_by_new_structured_identity(self):
        item = alert('G7, 비축유 방출', 'G7은 비축유 1억 배럴을 4개월간 방출하기로 합의했다.')
        entry = {'title': item['news'], 'link': item['link'], 'first_seen_kst': NOW.isoformat(), 'lanes': {'live': NOW.isoformat()}}
        state = {'seen': {'old': entry}}
        radar.telegram.migrate_seen_title_aliases(state)
        with patch.object(radar.telegram, 'load_seen_state', return_value=state):
            fresh, repeated = radar.telegram.filter_previously_seen_alerts([item], NOW, 'live')
        self.assertEqual(fresh, [])
        self.assertEqual(len(repeated), 1)


def audit_saved_runs(paths):
    results = []
    selections = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            name = next(name for name in archive.namelist() if name.endswith("gamejoa_preopen_news_radar.json"))
            report = json.loads(archive.read(name))
        run_time = radar.detail_queue.parse_time(report.get("query_time_kst"))
        candidates = copy.deepcopy(report["alerts"])
        with patch.object(radar.base, "kst_now", return_value=run_time or NOW):
            selected = radar.quality_display_alerts(candidates, 7)
        selected_links = {item.get("link") for item in selected}
        selections.append({"artifact": str(path), "original_count": len(candidates), "revalidated_count": len(selected),
                           "selected_titles": [item.get("source_title") for item in selected],
                           "removed": [{"title": item.get("source_title"), "reason": item.get("_exclusion_reason")}
                                       for item in candidates if item.get("link") not in selected_links]})
        for item in report["alerts"]:
            title = item.get("source_title") or item.get("news") or ""
            core = radar.verified_alert_core(item, title)
            core_item = {**item, "telegram_core_fact": core}
            results.append({
                "artifact": str(path), "title": title,
                "materiality": radar.source_market_materiality(item),
                "stored_core": item.get("telegram_core_fact"),
                "revalidated_core": core,
                "core_errors": radar.source_core_fact_errors(core_item),
                "core_materiality": materiality.assess(title, core),
                "stale_session_preview": bool(run_time and radar.is_stale_session_preview(item, run_time)),
            })
    print(json.dumps({"read_only_shadow_audit": True, "articles": len(results),
                      "changed_cores": sum(r["stored_core"] != r["revalidated_core"] for r in results),
                      "excluded": sum(r["materiality"]["disposition"] == "exclude" for r in results),
                      "stale_previews": sum(r["stale_session_preview"] for r in results),
                      "focus_mismatches": sum(not materiality.core_focus_aligned(r["title"], r["revalidated_core"]) for r in results),
                      "selection_audits": selections,
                      "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-zip", action="append", type=Path)
    args, remaining = parser.parse_known_args()
    if args.audit_zip:
        audit_saved_runs(args.audit_zip)
    else:
        unittest.main(argv=[__file__, *remaining])

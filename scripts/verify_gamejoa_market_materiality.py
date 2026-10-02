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


class MaterialityChecks(unittest.TestCase):
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
        self.assertEqual(len(radar.quality_display_alerts([first, second], 7)), 1)
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

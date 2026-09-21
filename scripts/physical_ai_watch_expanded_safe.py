#!/usr/bin/env python3
"""Runtime safety shim for expanded physical-AI watcher."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_expanded as expanded

base = expanded.base
ext = expanded.ext
_orig_score = base.score
_orig_same_event = ext._same_event

NEW_MEANING = {
    '고객 파이프라인·양산 프로토타입': '삼현이 단순 샘플 협의를 넘어 양산 프로토타입 계약과 다수 글로벌 고객 파이프라인을 확보하는지 봅니다. 4건의 Award가 실제 양산 수주·납품 물량으로 전환되는지가 핵심입니다.',
    '생산능력·양산 준비': '고객 요청에 앞서 액추에이터·모터 생산능력을 선제 확대하는 단계입니다. 가동률과 수율이 동반되면 외부 휴머노이드 OEM 주문을 빠르게 매출로 전환할 수 있습니다.',
    '글로벌 휴머노이드 초도 양산 수주': '삼현이 프로토타입·고객 검증 단계를 넘어 실제 글로벌 휴머노이드 고객사의 초도 양산 물량을 확보한 단계 변화입니다. 고객 실명·수량·단가는 NDA로 비공개이므로 12월 첫 출하와 후속 발주가 실제 매출 규모를 가르는 다음 확인점입니다.',
    '첫 양산 출하·공급 개시': '양산 수주가 실제 출하와 매출 인식으로 넘어가는 단계입니다. 출하 수량·인식 매출·초기 수율·불량률·고객 재주문을 함께 확인합니다.',
    '후속 양산 발주·물량 확대': '초도 공급이 반복 주문으로 전환돼 고객 검증이 상업적 확대로 이어지는 가장 강한 신호입니다. 후속 발주 규모와 납기, 생산라인 가동률을 확인합니다.',
    'IRON 생산라인·양산 전환': '샤오펑 IRON이 연구 시제품에서 실제 생산라인 제조로 넘어간 신호입니다. 2026년 말 양산과 2027년 외부 고객 인도가 물량·부품 발주로 연결되는지 봅니다.',
    'AXIUM 고객·수주 전환': 'LG전자가 AXIUM을 기술 공개 단계에서 글로벌 고객 수주 단계로 옮기는 신호입니다. 10월 빅테크 기술·생산 미팅 이후 고객 실명·계약 물량이 나오는지가 핵심입니다.',
    '베어로보틱스 가치·상장 상태': '베어로보틱스의 외부 가치평가·자금조달·상장 상태가 LG전자 로봇 자산의 시장가치 기준점으로 작용할 수 있습니다.',
    '프런티어AI→로봇 지능': '프런티어 모델 자체 성능이 아니라 실제 로봇의 계획·추론·행동모델·현장 배치에 연결되는지를 봅니다. 로봇 성공률·시도비용·지연시간이 개선될 때만 구조 변화로 판단합니다.',
}

NEW_RISK = {
    '고객 파이프라인·양산 프로토타입': '프로토타입 계약은 대량 양산 계약과 다릅니다. 고객 실명·단가·납기·반복 발주와 실제 양산 수주 전환을 확인해야 합니다.',
    '생산능력·양산 준비': '증설이 주문보다 앞서면 가동률·감가상각 부담이 먼저 커질 수 있습니다. 생산능력보다 실제 양산 수주가 더 중요합니다.',
    '글로벌 휴머노이드 초도 양산 수주': '수주금액·공급수량·고객명이 NDA로 비공개라 실적 민감도를 아직 계산할 수 없습니다. 가장 현실적인 실패 경로는 12월 초도 공급 이후 수율·품질 또는 고객 일정 문제로 후속 발주가 늦어지는 경우입니다.',
    '첫 양산 출하·공급 개시': '첫 출하는 안정 양산과 다릅니다. 초기 수율·재작업·반품·교환 접수와 보증비용이 높으면 매출 증가보다 원가 부담이 먼저 나타날 수 있습니다.',
    '후속 양산 발주·물량 확대': '반복 발주가 한 고객에 집중되면 고객 의존도가 커질 수 있습니다. 복수 고객사 양산 전환과 평균판매단가·마진 유지 여부를 같이 봅니다.',
    'IRON 생산라인·양산 전환': '생산라인 가동과 대량 판매는 다릅니다. 수율·주간 생산량·실제 인도 대수·안전성 검증이 늦어지면 상용화 일정이 밀릴 수 있습니다.',
    'AXIUM 고객·수주 전환': '현재는 수주 협의 단계이며 특정 빅테크 계약은 아직 확정되지 않았습니다. 10월 미팅 이후 고객 인증·납품 단가·수량을 확인해야 합니다.',
    '베어로보틱스 가치·상장 상태': '상장 보도와 확정 일정은 구분해야 합니다. LG전자는 해외 상장에 대해 결정된 바 없다고 공시한 만큼 실제 이사회·공시·투자조건을 우선합니다.',
    '프런티어AI→로봇 지능': 'GPT-6 Astra 같은 모델의 일반 추론 성능만으로 로봇 상용화를 확정할 수 없습니다. 실제 로봇 통합·행동 성공률·지연·안전 검증이 없으면 알림하지 않습니다.',
}


def meaning(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw in NEW_MEANING:
        return NEW_MEANING[raw]
    return expanded._orig_meaning(cat)


def risk(cat: str) -> str:
    raw = cat.split(' · ', 1)[-1]
    if raw in NEW_RISK:
        return NEW_RISK[raw]
    return expanded._orig_risk(cat)


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    group = base.topic_group(text)
    source = item.get('source') or ''
    if group == 'lg_robotics' and source in base.LOW_QUALITY_SOURCES:
        return -30
    return _orig_score(item)


def same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != b.get('group'):
        return False
    if a.get('group') == 'xpeng':
        ta = f"{a.get('title','')} {a.get('description','')}"
        tb = f"{b.get('title','')} {b.get('description','')}"
        robot_a = re.search(r'IRON|아이언|휴머노이드|humanoid', ta, re.I)
        robot_b = re.search(r'IRON|아이언|휴머노이드|humanoid', tb, re.I)
        prod_a = re.search(r'생산\s*라인|production\s*line|양산|mass\s*production|80%|2026년\s*말|2027년', ta, re.I)
        prod_b = re.search(r'생산\s*라인|production\s*line|양산|mass\s*production|80%|2026년\s*말|2027년', tb, re.I)
        if robot_a and robot_b and prod_a and prod_b:
            return True
    return False

base.meaning = meaning
base.risk = risk
base.score = score
ext._same_event = same_event

if __name__ == '__main__':
    base.main()

#!/usr/bin/env python3
"""Shared Korean market-impact explanation helpers for KHS policy alerts."""

from __future__ import annotations

import re
from typing import Any


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,|/]", value) if part.strip()]
        return parts or [value.strip()]
    return [str(value)]


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def matched_terms(item: dict) -> str:
    matched = item.get("matched") or {}
    if isinstance(matched, dict):
        return " ".join(term for terms in matched.values() for term in as_list(terms))
    return " ".join(as_list(matched))


def text_for(item: dict) -> str:
    return " ".join(
        str(part or "")
        for part in (
            item.get("source"),
            item.get("title"),
            item.get("original_title"),
            item.get("summary"),
            item.get("core"),
            item.get("point"),
            item.get("impact"),
            item.get("policy_plain_summary"),
            matched_terms(item),
            " ".join(as_list(item.get("sectors"))),
        )
    ).lower()


def has_any(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)


def put(item: dict, **values: Any) -> None:
    for key, value in values.items():
        if value is not None:
            item[key] = value


def default_context(item: dict) -> None:
    impacts = unique(as_list(item.get("impacts")) or ["의사결정 영향 제한적"])
    sectors = unique(as_list(item.get("sectors")) or ["정책/규제 일반"])
    paths = unique(as_list(item.get("paths")) or ["정책 타임라인"])
    item["impacts"] = impacts
    item["sectors"] = sectors
    item["paths"] = paths
    item.setdefault(
        "policy_plain_summary",
        f"공식 정책·규제 문서에서 {', '.join(impacts)} 관련 상태 변화 후보가 확인됐습니다.",
    )
    item.setdefault(
        "investment_view",
        "매출·마진·할인율·수급·정책 시간표 중 무엇이 실제로 바뀌는지 후속 원문과 시장 반응으로 확인해야 합니다.",
    )
    item.setdefault(
        "korea_market_impact",
        f"한국장 체크 대상은 {', '.join(sectors)}입니다. 원문에 직접 근거가 없는 업종 확장은 제외합니다.",
    )
    item.setdefault("priced_in", "낮음~중간. 공식 원문 확인 후 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.")
    item.setdefault("counter", "세부 시행일, 예산, 예외 조항, 대상 기업, 실제 계약 조건 확인 전까지 직접 실적 연결은 제한적입니다.")
    item.setdefault("failure_signal", "후속 시행일·예산·계약·수급 반응이 없으면 단발성 정책 뉴스로 끝납니다.")


def is_transformer(text: str, item: dict) -> bool:
    return bool(item.get("transformer_tariff_policy_watch")) or "transformer_tariff_policy" in (item.get("matched") or {}) or (
        has_any(text, ["transformer", "distribution transformer", "grain-oriented electrical steel", "amorphous core"])
        and has_any(text, ["tariff", "section 232", "232", "25%", "15%", "관세", "변압기"])
    )


def is_domestic_nuclear_siting(text: str, item: dict) -> bool:
    return bool(item.get("korea_nuclear_siting_policy_watch")) or "korea_nuclear_siting_policy" in (item.get("matched") or {}) or has_any(
        text,
        ["smr", "표준설계", "원전 입지", "입지 선정", "대형 원전", "방폐장", "송전망", "인허가", "2037", "2038"],
    )


def is_domestic_telecom(text: str, item: dict) -> bool:
    return bool(item.get("telecom_policy_risk")) or "korea_telecom_policy" in (item.get("matched") or {}) or has_any(
        text,
        ["가계통신비", "통신비", "선택약정", "5g 요금제", "중간요금제", "arpu", "sk텔레콤", "lg유플러스"],
    )


def is_stablecoin(text: str, item: dict) -> bool:
    return bool(item.get("domestic_stablecoin_policy_watch")) or "korea_stablecoin_policy" in (item.get("matched") or {}) or has_any(
        text,
        ["스테이블코인", "원화 스테이블코인", "디지털자산", "가상자산 2단계", "예금 대체", "한국은행", "발행 주체"],
    )


def is_personnel(text: str, item: dict) -> bool:
    return "korea_presidential_personnel" in (item.get("matched") or {}) or bool(item.get("appointees"))


def is_fcc_resilient(text: str) -> bool:
    return has_any(
        text,
        [
            "resilient networks",
            "disruptions to communications",
            "disaster information reporting system",
            "dirs",
            "outage reporting",
            "network outage reporting",
            "communications disruption",
            "disaster reporting",
        ],
    )


def ensure_explained(item: dict) -> dict:
    default_context(item)
    text = text_for(item)

    if is_personnel(text, item):
        appointees = item.get("appointees") or "고위급 인사"
        color = item.get("policy_color") or "발표자 직함·기존 이력 기준 정책 색깔 확인 필요"
        sectors = unique(as_list(item.get("sectors")) or ["한국 대통령실/고위급 인사"])
        put(
            item,
            impacts=["시간표"],
            paths=["정책 인선", "정책 타임라인"],
            sectors=sectors,
            policy_plain_summary=f"대통령실/청와대 공식 인사에서 {appointees}가 확인됐습니다. {color}.",
            investment_view="인선 자체는 매출을 만들지 않지만, 어느 부처·정책 라인이 힘을 받는지와 후속 규제·예산 시간표를 앞당길 수 있습니다.",
            korea_market_impact=f"한국장에서는 {', '.join(sectors)}에 한해 정책 기대가 붙을 수 있습니다. 원문에 없는 섹터 연결은 제외합니다.",
            priced_in="중간. 공식 인사 발표는 바로 공개되지만, 개별 업종 영향은 후속 업무지시·부처 발표 전까지 제한적입니다.",
            counter="인사 발표만으로 예산·법안·규제 시행이 확정된 것은 아닙니다.",
            failure_signal="취임 후 업무지시, 부처별 정책 발표, 예산·입법·규제 일정이 나오지 않으면 인사 뉴스에서 끝납니다.",
        )
    elif is_transformer(text, item):
        put(
            item,
            importance="상",
            impacts=["돈 버는 능력", "할인율", "수급", "시간표"],
            paths=["이익", "정책 타임라인", "밸류체인", "수급", "계약 가시성"],
            sectors=["전력기기/변압기", "관세/수출주", "전력망/데이터센터"],
            policy_plain_summary="미국 대형 변압기 관세·효율규제 변화가 한국 전력기기 수출 채산성과 미국 전력망 투자 수혜 기대를 바꿀 수 있는 사안입니다.",
            investment_view="관세율 인하나 규제 재검토가 공식화되면 한국 변압기·전력기기 업체의 가격경쟁력, 마진, 신규 수주 기대가 동시에 바뀝니다.",
            korea_market_impact="한국장에서는 효성중공업·HD현대일렉트릭·LS ELECTRIC 등 전력기기/변압기 밸류체인과 데이터센터 전력망 테마 수급을 우선 확인합니다.",
            priced_in="중간. 전력기기 테마는 선반영이 강하지만, 관세율·시행일·품목코드가 공식 확인되면 실적 추정치 조정 여지가 남습니다.",
            counter="공식 관보·상무부·USTR 문서에서 품목, 세율, 시행일, 예외 조항이 확인되기 전에는 보도 기반 예비 재료입니다.",
            failure_signal="관세율·품목코드·시행일 공식 문서가 없거나 개별 기업 수주·마진 가이던스가 따라오지 않으면 재료가 약해집니다.",
        )
    elif is_domestic_nuclear_siting(text, item):
        put(
            item,
            impacts=["시간표", "수급"],
            paths=["정책 타임라인", "인허가", "밸류체인", "수급"],
            sectors=["국내 원전/SMR", "원전 기자재/전력기기", "송전망/전선", "두산에너빌리티/KHNP"],
            policy_plain_summary="국내 원전·SMR 입지, 표준설계, 인허가, 송전망·방폐장 과제가 정책 시간표로 다시 부각된 사안입니다.",
            investment_view="당장 수주 확정보다 장기 CAPEX와 밸류체인 기대를 되살리는 재료입니다. 실제 돈 버는 능력은 인허가, 주민수용성, 계약 규모가 확정돼야 바뀝니다.",
            korea_market_impact="한국장에서는 원전 기자재, 전력기기, 송전망, 두산에너빌리티/KHNP 연계 종목의 수급 반응을 보되 테마 과열을 경계해야 합니다.",
            priced_in="중간~높음. 원전 테마는 정책 기대가 빠르게 선반영되므로 계약·인허가 일정이 확인되지 않으면 되돌림 위험이 큽니다.",
            counter="SMR 표준설계, 대형원전 인허가, 방폐장·송전망·안전성 검증과 주민수용성이 남아 있어 당장 매출 확정으로 볼 수 없습니다.",
            failure_signal="입지 확정 후 인허가·송전망·방폐장·주민수용성 일정이 지연되거나 실제 계약 규모가 나오지 않으면 모멘텀이 꺾입니다.",
        )
    elif is_domestic_telecom(text, item):
        put(
            item,
            impacts=["돈 버는 능력", "시간표"],
            paths=["이익", "정책 타임라인", "요금규제", "수익구조"],
            sectors=["국내 통신정책/통신3사", "AI 데이터센터/IDC", "통신장비"],
            policy_plain_summary="국내 통신비 인하 압박, 요금제 개편, 선택약정 할인 확대 가능성이 통신사 ARPU와 이익률을 흔들 수 있는 정책 리스크입니다.",
            investment_view="통신요금 규제는 단기 이익에는 부담입니다. 다만 AI 인프라·IDC·B2B 매출 비중이 커질수록 통신요금 의존도 하락 여부가 더 중요해집니다.",
            korea_market_impact="한국장에서는 SK텔레콤·KT·LG유플러스의 ARPU, 배당 매력, AI/IDC 매출 비중, 전기료 부담을 같이 확인합니다.",
            priced_in="중간. 통신비 인하 압박은 오래된 리스크지만 구체 제도 변경이 나오면 이익 추정 조정이 가능합니다.",
            counter="요금 인하가 실제 시행되지 않거나 AI 인프라 매출 증가가 ARPU 둔화를 상쇄하면 주가 영향은 제한됩니다.",
            failure_signal="요금제·선택약정·단통법 후속 조치가 없거나 통신사 B2B/AI 인프라 매출이 방어하면 규제 악재가 약해집니다.",
        )
    elif is_stablecoin(text, item):
        put(
            item,
            impacts=["시간표", "수급", "할인율"],
            paths=["정책 타임라인", "금융 인프라", "규제 강도", "수급"],
            sectors=["금융/자본시장/스테이블코인", "은행/핀테크/결제", "가상자산거래소/디지털자산"],
            policy_plain_summary="원화 스테이블코인·디지털자산 입법은 발행 주체, 준비자산, 지급결제 표준을 둘러싼 금융 인프라 재편 이슈입니다.",
            investment_view="지금 붙는 자금은 실적보다 누가 미래 결제·유통 표준을 잡을지에 대한 베팅 성격이 큽니다. 예금 대체 논란이 커지면 규제 강도도 세질 수 있습니다.",
            korea_market_impact="한국장에서는 은행, 핀테크, 결제, 가상자산거래소, 보안·인증 인프라를 보되 코인 가격보다 금융 인프라 재편 관점으로 봐야 합니다.",
            priced_in="중간. 법안 기대는 테마 수급에 빨리 반영되지만, 발행 주체와 감독 강도가 확정되지 않아 변동성이 큽니다.",
            counter="은행 중심인지 핀테크·거래소까지 허용할지, 한국은행·금융당국 규제 강도가 어느 수준일지 아직 확정되지 않았습니다.",
            failure_signal="발행 주체가 좁게 제한되거나 준비자산·상환·건전성 규제가 강해지면 테마 확산이 약해집니다.",
        )
    elif is_fcc_resilient(text):
        put(
            item,
            importance="중",
            impacts=["시간표", "의사결정 영향 제한적"],
            paths=["정책 타임라인", "규제 준수"],
            sectors=["미국 통신망 복구/장애보고"],
            policy_plain_summary="FCC가 재난·정전·허리케인 등 통신장애 때 사업자가 DIRS에 보고하는 절차를 현대화한 최종규칙입니다. 통신망 투자 확대나 주파수 경매가 아니라 재난 대응 보고·행정 부담 조정 성격입니다.",
            investment_view="매출을 직접 늘리는 정책은 아닙니다. 미국 통신사·장비사의 단기 CAPEX, 한국 통신3사 실적, 국내 네트워크 장비 수주로 바로 연결되는 근거는 제한적입니다.",
            korea_market_impact="한국장에서는 통신장비·위성·통신주 테마 반응이 붙어도 직접 가격 변수는 약합니다. 재난통신 장비 조달, 911·공공안전망 투자, 보안장비 의무화가 뒤따를 때만 재평가 후보입니다.",
            priced_in="낮음. 선반영 여부보다 영향 자체가 제한적입니다.",
            counter="최종규칙이라도 핵심은 보고 절차 정비입니다. 신규 예산·장비 발주·주파수 정책·보조금이 확인되지 않으면 실적 연결은 약합니다.",
            failure_signal="미국 통신사 CAPEX 가이던스, 장비 발주, 공공안전망 예산, 국내 장비사 수주 공시가 없으면 테마성 반응에서 끝납니다.",
        )
    elif has_any(text, ["export control", "entity list", "bis", "semiconductor", "chips", "ai chip", "수출통제"]):
        put(
            item,
            impacts=["돈 버는 능력", "할인율", "시간표"],
            paths=["공급망", "정책 타임라인", "밸류체인", "규제 리스크"],
            sectors=["반도체/AI", "장비·소재", "중국 노출 밸류체인"],
            policy_plain_summary="미국 수출통제·엔티티리스트·첨단기술 규제는 AI 반도체와 장비·소재 공급망의 판매 가능 시장을 바꿀 수 있는 정책 변수입니다.",
            investment_view="대상 품목과 국가가 확인되면 매출처 제한, 재고 조정, 우회 수요, 장비 발주 시간표가 바뀝니다.",
            korea_market_impact="한국장에서는 삼성전자·SK하이닉스, 반도체 장비·소재, 중국 매출 노출 업체와 HBM/AI 체인 수급을 우선 확인합니다.",
            priced_in="중간. 미중 기술규제는 반복 재료지만 새 품목·새 기업·새 시행일이면 실적 추정에 반영될 수 있습니다.",
            counter="초안·검토·보도 단계이면 실제 적용 범위가 축소될 수 있고, 예외 라이선스가 열리면 충격은 줄어듭니다.",
            failure_signal="최종 규정, 시행일, 대상 기업·품목, 라이선스 제한이 확인되지 않으면 테마성 반응으로 끝납니다.",
        )
    elif has_any(text, ["tariff", "section 301", "customs", "duty", "관세", "통관"]):
        put(
            item,
            impacts=["돈 버는 능력", "할인율", "수급", "시간표"],
            paths=["이익", "공급망", "정책 타임라인", "수급"],
            sectors=["관세/수출주", "소비재·산업재", "물류/공급망"],
            policy_plain_summary="관세·통관 집행 변화는 수입 원가, 가격전가, 공급망 재배치, 수출주 마진을 바꿀 수 있는 정책 변수입니다.",
            investment_view="품목·국가·세율·시행일이 확인되면 해당 밸류체인의 매출총이익률과 주문 이전 기대가 바로 바뀝니다.",
            korea_market_impact="한국장에서는 미국향 수출주, 중국 대체 공급망, 관세 민감 소비재·산업재, 물류비 민감 업종을 선별 확인합니다.",
            priced_in="낮음~중간. 단순 발언은 빨리 소멸하지만 관보·행정명령·USTR 문서로 확정되면 재평가 여지가 있습니다.",
            counter="품목코드, 예외 조항, 유예 기간이 확인되지 않으면 개별 종목 영향 추정은 과대해석일 수 있습니다.",
            failure_signal="공식 세율·품목·시행일이 나오지 않거나 기업 가격전가/수주 변화가 확인되지 않으면 실패입니다.",
        )
    elif has_any(text, ["nuclear", "reactor", "uranium", "ap1000", "westinghouse", "data center", "nrc", "원전"]):
        put(
            item,
            impacts=["시간표", "돈 버는 능력", "수급"],
            paths=["원전 정책 타임라인", "AI 데이터센터 전력수요", "원전 밸류체인", "수급"],
            sectors=["원전/전력기기", "전력망/데이터센터", "우라늄", "SMR/대형원전 기자재"],
            policy_plain_summary="원전 인허가, 핵연료, 신규 원전, AI 데이터센터 전력수요가 정책 시간표로 공식화되는지 보는 사안입니다.",
            investment_view="확정 매출은 아니지만 대형 CAPEX와 인허가 시간이 앞당겨지면 원전기기·전력기기·우라늄 체인의 수주 기대가 커집니다.",
            korea_market_impact="한국장에서는 원전 기자재, 전력기기, 송전망, 두산에너빌리티·한전기술·한전KPS 등 밸류체인 수급을 확인합니다.",
            priced_in="중간. 원전 테마는 선반영이 강하지만 정책·대출·NRC 일정이 동시에 확인되면 추가 재평가 여지가 있습니다.",
            counter="부지, 최종 계약, 예산·대출 조건, NRC 인허가, 착공 일정이 확정되지 않으면 실제 매출 인식까지 시차가 큽니다.",
            failure_signal="대출 조건, 부지, NRC 일정, 원전기기 발주가 확인되지 않으면 정책 기대에서 끝납니다.",
        )
    elif has_any(text, ["ferc", "power grid", "transmission", "interconnection", "electric grid", "전력망"]):
        put(
            item,
            impacts=["시간표", "돈 버는 능력", "수급"],
            paths=["전력망 투자", "정책 타임라인", "밸류체인", "수급"],
            sectors=["전력망/전력기기", "전선/변압기", "데이터센터 전력 인프라"],
            policy_plain_summary="전력망·송전·계통연계 정책은 데이터센터와 전력 인프라 CAPEX 시간표를 바꿀 수 있는 사안입니다.",
            investment_view="계통연계 병목 완화나 투자 인센티브가 확인되면 변압기·전선·전력기기 수주 기대가 커집니다.",
            korea_market_impact="한국장에서는 전선, 변압기, 전력기기, 데이터센터 전력 인프라 관련 종목의 수급과 수주 공시를 확인합니다.",
            priced_in="중간. 전력망 테마가 이미 강하면 시행일·예산·발주 없이는 추가 반응이 제한됩니다.",
            counter="규칙 제안이나 의견수렴 단계는 실제 발주와 거리가 있을 수 있습니다.",
            failure_signal="FERC/DOE 후속 일정, 유틸리티 CAPEX, 장비 발주가 없으면 테마성 반응에 그칩니다.",
        )
    elif has_any(text, ["fda", "clinical", "drug", "complete response letter", "approval", "crl", "임상", "허가"]):
        put(
            item,
            impacts=["돈 버는 능력", "시간표", "수급"],
            paths=["임상/허가 시간표", "이익", "수급"],
            sectors=["바이오/FDA", "제약", "헬스케어"],
            policy_plain_summary="FDA 승인·거절·임상 관련 결정은 개발 시간표와 상업화 가능성을 직접 바꾸는 바이오 이벤트입니다.",
            investment_view="승인·CRL·임상 결과는 매출 개시 시점, 추가 비용, 기술이전 협상력을 바꿀 수 있습니다.",
            korea_market_impact="한국장에서는 해당 파이프라인 보유사, CDMO, 바이오텍 섹터 수급을 확인하되 원문 적응증·대상 기업 근거가 필요합니다.",
            priced_in="중간~높음. 바이오 이벤트는 기대가 선반영되기 쉬워 결과와 시장 기대의 차이가 중요합니다.",
            counter="부분 승인, 라벨 제한, 추가 임상 요구, 안전성 이슈가 있으면 headline보다 영향이 약할 수 있습니다.",
            failure_signal="라벨·시장규모·상업화 파트너·후속 비용이 확인되지 않으면 주가 재료가 약해집니다.",
        )
    elif has_any(text, ["robot", "robotics", "commerce", "china", "chinese", "robotics tariffs"]):
        put(
            item,
            impacts=["시간표", "수급", "돈 버는 능력"],
            paths=["정책 타임라인", "중국 대체 공급망", "관세/수입제한", "수급"],
            sectors=["로봇/스마트팩토리", "감속기/FA", "산업자동화", "관세/수출주"],
            policy_plain_summary="미국이 중국산 로봇 수입·보조금·국가안보 리스크를 검토한다는 신호는 로봇 산업을 미중 기술패권의 다음 전선으로 보는 재료입니다.",
            investment_view="관세·수입제한·미국 내 제조지원으로 이어지면 중국 대체 밸류체인과 자동화 장비 수요 기대가 커질 수 있습니다.",
            korea_market_impact="한국장에서는 로봇, 감속기, 스마트팩토리, FA 장비, 중국 대체 공급망 테마 수급을 보되 공식 상무부 발표 전이면 예비로 봐야 합니다.",
            priced_in="낮음~중간. 보도 직후 테마 수급은 빠르지만 공식 조치 전에는 되돌림 위험이 큽니다.",
            counter="익명 소식통 보도 단계라 품목, 관세율, 시행일, 대출 조건, 대상 기업은 미확정입니다.",
            failure_signal="상무부 공식 조사·관세·OSC 대출 조건이 나오지 않으면 단기 테마성 반응으로 끝납니다.",
        )
    elif has_any(text, ["spectrum", "satellite", "space bureau", "wireless", "broadband", "fcc"]):
        put(
            item,
            impacts=["시간표", "수급"],
            paths=["정책 타임라인", "주파수/통신 규제", "수급"],
            sectors=["통신/FCC/위성", "통신장비", "위성통신"],
            policy_plain_summary="FCC 통신·주파수·위성 규제 문서는 통신 인프라 정책 시간표를 바꿀 수 있지만, 문서 성격에 따라 시장 영향 차이가 큽니다.",
            investment_view="주파수 경매, 위성 인허가, 장비 인증, 보안 의무처럼 CAPEX나 조달로 이어질 때만 실적 재료가 됩니다.",
            korea_market_impact="한국장에서는 통신장비·위성통신·네트워크 장비 테마를 확인하되, 행정 공지·회의 공고 수준이면 직접 영향은 제한적입니다.",
            priced_in="낮음~중간. 구체 인허가·경매·보안 의무가 없으면 가격 반응은 약합니다.",
            counter="FCC 문서라도 회의 공지, 데이터 수집, 보고 양식 정비는 고충격 재료가 아닐 수 있습니다.",
            failure_signal="주파수 경매, 장비 의무화, 인허가, 통신사 CAPEX 변화가 없으면 제외해야 합니다.",
        )

    item["impacts"] = unique(as_list(item.get("impacts")) or ["의사결정 영향 제한적"])
    item["paths"] = unique(as_list(item.get("paths")) or ["정책 타임라인"])
    item["sectors"] = unique(as_list(item.get("sectors")) or ["정책/규제 일반"])
    return item


def explanation_lines(item: dict) -> list[str]:
    ensure_explained(item)
    return [
        f"- 핵심 내용: {item.get('policy_plain_summary') or '정책 세부 내용 확인 필요'}",
        f"- 투자 관점: {item.get('investment_view') or '실적·할인율·수급·시간표 변화 여부 확인 필요'}",
        f"- 한국장 영향: {item.get('korea_market_impact') or '한국장 직접 영향 확인 필요'}",
        f"- 의사결정 영향: {', '.join(as_list(item.get('impacts')) or ['의사결정 영향 제한적'])}",
        f"- 영향 경로: {', '.join(as_list(item.get('paths')) or ['정책 타임라인'])}",
        f"- 영향 섹터: {', '.join(as_list(item.get('sectors')) or ['정책/규제 일반'])}",
        f"- 반영 가능성: {item.get('priced_in') or '낮음~중간'}",
        f"- 반대 근거: {item.get('counter') or '세부 조건 확인 전까지 직접 실적 연결은 제한적입니다.'}",
        f"- 실패 신호: {item.get('failure_signal') or '후속 시행일·예산·계약·수급 반응이 없으면 단발성 정책 뉴스로 끝납니다.'}",
    ]

#!/usr/bin/env python3
"""LNG 공급·가격 감시 v26: 기사 자체가 아닌 사건·상태 변화 중심 감시 + 전 알림 가독성 상단 요약."""
from __future__ import annotations

import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v25 as v25

# v25를 import하면 카타르→미국 LNG 오버레이까지 현행 core에 연결된 뒤다.
_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

# 특정 기사 제목/URL을 추적하는 방식이 아니라, 같은 사건을 여러 표현·매체에서 발견하기 위한
# 넓은 사건축 검색어를 추가한다. 기사/검색결과는 '센서·증거'이고 알림 대상은 아래 사건축의 변화다.
EVENT_DISCOVERY_QUERIES = (
    ("qatar_supply", 'QatarEnergy LNG supply disruption repair duration replacement procurement long-term portfolio when:7d'),
    ("qatar_supply", 'Qatar LNG customer replacement cargo force majeure duration supply portfolio when:7d'),
    ("hormuz_shipping", 'Hormuz LNG transit insurance vessel traffic STS transfer reroute normalization when:3d'),
    ("europe_storage", 'Europe gas storage refill pace Germany Netherlands LNG cargo competition winter when:3d'),
    ("asia_procurement", 'Asia LNG JKM spot tender cargo competition Korea Japan long-term procurement when:3d'),
    ("korea_supply", '한국 LNG 장기조달 현물입찰 국적선 화물창 국산화 실증 발주 when:7d'),
    ("power_equipment_supply", 'gas turbine transformer HVDC procurement backlog delivery slot tariff utility when:7d'),
)
for item in EVENT_DISCOVERY_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

# 사용자가 빠르게 읽을 수 있도록 subtype을 기사 제목이 아니라 '현재 단계' 언어로 표시한다.
STAGE_LABELS = {
    "force_majeure": "불가항력 선언·연장/해제",
    "production_outage": "생산·수출 중단",
    "production_restart": "생산 재가동",
    "export_resume": "수출 재개",
    "facility_damage": "생산시설 피해",
    "hormuz_closure": "호르무즈 통항 차질",
    "hormuz_reopen": "호르무즈 통항 정상화",
    "insurance": "전쟁위험 보험 변화",
    "reroute": "우회·환적 경로 변화",
    "storage": "유럽 저장량 변화",
    "storage_refill_gap": "유럽 저장 목표 부족분",
    "storage_lng_competition": "유럽↔아시아 LNG 카고 경쟁",
    "jkm_price": "아시아 JKM 가격 변화",
    "cargo_tender": "현물 LNG 입찰·조달 경쟁",
    "ttf_intraday_80": "TTF 장중 80유로 돌파",
    "ttf_intraday_90": "TTF 장중 90유로 돌파",
    "ttf_intraday_100": "TTF 장중 100유로 돌파",
    "qatar_us_lng_talks": "카타르의 미국 LNG 장기조달 협상 시작",
    "qatar_us_lng_scope": "카타르 미국 LNG 협상 물량·기간·후보 구체화",
    "qatar_us_lng_spa": "카타르 미국 LNG 장기계약 체결",
    "qatar_us_lng_delivery": "카타르 대체 미국 LNG 실제 인도",
    "lng_cargo_tank_localization": "한국 LNG 화물창 국산화 추진",
    "lng_cargo_tank_large_demo": "한국 LNG 화물창 대형선 실증",
    "lng_cargo_tank_certification": "한국 LNG 화물창 선급·기술 인증",
    "lng_cargo_tank_commercial_order": "한국 LNG 화물창 실제 발주",
    "power_trade_barrier": "무역장벽에 따른 발전설비 조달 변화",
    "gas_turbine_procurement": "가스터빈 조달·납기 변화",
    "transformer_procurement": "변압기·HVDC 조달 변화",
    "power_delivery_slot": "발전·전력기기 제조 슬롯 변화",
    "europe_rates_energy_ecb": "에너지 충격의 ECB 재가격 전이",
    "europe_rates_bund_selloff": "유럽 장기채 매도·금리 상승",
}

CATEGORY_MEANING = {
    "qatar_supply": "카타르 공급 지속성·불가항력·대체조달 구조",
    "hormuz_shipping": "호르무즈 통항·보험·우회/환적 경로",
    "europe_storage": "유럽 재고·TTF·겨울 조달 경쟁",
    "asia_procurement": "JKM·아시아 현물 LNG 조달 경쟁",
    "korea_supply": "한국 LNG 조달·국산화·국적선/가스공사 변화",
    "alaska_lng": "알래스카 LNG 정책→계약→FID→EPC/발주 단계",
    "power_equipment_supply": "가스터빈·변압기·HVDC 공급망 병목",
    "europe_rates": "가스·에너지 충격의 ECB·장기금리 전이",
}


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in out:
            out.append(value)
    return out


def _verdict(groups, new_signals, cleared_signals) -> str:
    polarities = {str(g.get("polarity") or "") for g in groups}
    if polarities == {"worsening"}:
        base = "수급·가격·정책 스트레스 악화"
    elif polarities == {"easing"}:
        base = "공급·조달 스트레스 완화"
    elif "worsening" in polarities and "easing" in polarities:
        base = "악화·완화 신호 혼재 · 방향 확인 필요"
    elif new_signals:
        base = "시장 임계값 신규 진입"
    elif cleared_signals:
        base = "시장 임계값 이탈 · 공급 정상화와는 별도 판정"
    else:
        base = "검증된 상태 변화 확인"
    return base


def _stage_text(groups, new_signals, cleared_signals) -> str:
    labels = _unique([
        STAGE_LABELS.get(str(g.get("subtype") or ""), str(g.get("subtype") or "상태 변화"))
        for g in groups
    ])
    signal_labels: list[str] = []
    for signal in new_signals:
        try:
            signal_labels.append(core.signal_label(str(signal), False))
        except Exception:
            signal_labels.append(str(signal))
    for signal in cleared_signals:
        try:
            signal_labels.append(core.signal_label(str(signal), True))
        except Exception:
            signal_labels.append(f"{signal} 이탈")
    combined = _unique(labels + signal_labels)
    if not combined:
        return "새 확정 변화 없음"
    if len(combined) <= 3:
        return " · ".join(combined)
    return " · ".join(combined[:3]) + f" · 외 {len(combined)-3}건"


def _watch_axes(groups) -> str:
    values = _unique([
        CATEGORY_MEANING.get(str(g.get("category") or ""), core.category_label(str(g.get("category") or "unknown")))
        for g in groups
    ])
    return " / ".join(values[:4]) if values else "LNG 수급·가격·공급망"


def _global_summary(groups, new_signals, cleared_signals) -> list[str]:
    return [
        "<b>한눈에</b>",
        f"• <b>판정</b> {_verdict(groups, new_signals, cleared_signals)}",
        f"• <b>감시 축</b> {_watch_axes(groups)}",
        f"• <b>이번 변화</b> {_stage_text(groups, new_signals, cleared_signals)}",
    ]


def _dedupe_exact_lines(body: str) -> str:
    """같은 문장/헤더가 오버레이 중첩으로 반복된 경우만 제거한다. 정보 자체는 삭제하지 않는다."""
    seen: set[str] = set()
    out: list[str] = []
    previous_blank = False
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if previous_blank:
                continue
            out.append("")
            previous_blank = True
            continue
        previous_blank = False
        key = line.strip()
        # 기사 근거 줄은 같은 링크/문장일 때만 중복 제거한다.
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out).strip()


def _make_event_first(body: str, groups, new_signals, cleared_signals) -> str:
    clean = _dedupe_exact_lines(body)
    summary = _global_summary(groups, new_signals, cleared_signals)
    if clean.startswith("<b>한눈에</b>"):
        # 이미 v25 전용 포맷이 있는 경우 기존 한눈에를 유지하고, 중복 요약은 추가하지 않는다.
        return clean
    return "\n".join(summary) + "\n\n" + clean


def build_regular_alert_v26(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    body = _make_event_first(body, groups, new_signals, cleared_signals)
    metadata["version"] = 26
    metadata["monitoring_model"] = {
        "target": "event_state_and_threshold_changes",
        "article_role": "discovery_and_evidence_only",
        "not_target": "specific_article_url_or_headline",
        "material_changes": [
            "worsening_or_easing_state",
            "stage_upgrade_or_downgrade",
            "volume_duration_counterparty_or_timetable_change",
            "official_confirmation_or_contract_step",
            "market_threshold_entry_reentry_or_exit",
        ],
        "readability_order": [
            "판정", "감시 축", "이번 변화", "핵심 숫자/현재 단계", "근거", "한국 영향", "투자 포인트", "다음 확인", "핵심 한 줄",
        ],
    }
    return title, body, metadata


def build_setup_test_v26(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    title = "✅ LNG 사건·상태 중심 감시 + 전 알림 가독성 v26 적용"
    body += (
        "\n\n<b>감시 원칙</b>"
        "\n• 특정 기사 제목·URL 자체를 추적하지 않고 LNG 수급·정책·가격·프로젝트·공급망의 실제 상태 변화를 추적"
        "\n• 기사는 새 상태를 발견하고 교차검증하는 근거로만 사용"
        "\n• 같은 핵심 정보는 삭제하지 않고 판정 → 감시 축 → 이번 변화 → 숫자/단계 → 근거 → 영향 → 다음 확인 순으로 재배치"
        "\n• 같은 문장·헤더가 오버레이에서 반복될 때만 중복 제거"
    )
    metadata["version"] = 26
    metadata["monitoring_model"] = "event/state first; articles are evidence only"
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v26
core.build_setup_test = build_setup_test_v26

if __name__ == "__main__":
    raise SystemExit(core.main())

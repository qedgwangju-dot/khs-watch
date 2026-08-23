#!/usr/bin/env python3
"""Regression gate for cross-market and next-generation semiconductor coverage."""

from datetime import datetime, timezone
from pathlib import Path
import sys

# Prefer the runner checked into this scripts directory over any same-named
# module in the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gamejoa_preopen_news_radar_full_compact_runner as radar


SEARCH_NAMES = {
    "미국장 빅테크 실적·한국 ADR·반도체 수급",
    "HBM5·zHBM·HBF 차세대 메모리 기술·상용화",
    "메모리 장기공급·수요전망·고객 사양 변경",
    "삼성 파운드리 가동률·풀캐파·공정 주문",
    "핵심 원자재 사상최고·공급차질",
    "레버리지 규제 후 거래대금·자금이동",
    "SK하이닉스 해외 HBM 생산거점",
    "엔비디아 AI 서버 가격·메모리 공급부족",
    "YMTC 낸드 IPO·중국 메모리 공급",
    "앤트로픽 IPO·AI 인프라 자금",
    "삼성·SK HBM 핫칩스·기술공개",
    "빅테크 AI 회사채·미국 국채금리",
    "미국·캐나다 무역협정·관세",
    "이란·중국 원유·브렌트",
    "삼성 TV 출하·메모리 원가",
    "반도체 노조·성과급·가동 리스크",
    "트럼프 자산공시·대형 주식거래",
    "미국 쇠고기 관세·통상",
    "중동 경제전·원유·해운 리스크",
    "러시아·우크라이나 경제목표·에너지·물류",
    "AGI·HBM 첨단패키징 병목",
    "삼성 엑시노스·2나노·퀄컴 성능",
    "엔비디아 실적·잭슨홀 일정",
    "미 재정적자·장기국채 금리",
    "고배당·커버드콜 ETF 순매수",
}

CASES = (
    (
        "뉴욕증시, 아마존 실적 훈풍…SK하이닉스 ADR 3.5% 하락",
        "adr",
        {"돈 버는 능력", "수급"},
    ),
    (
        "삼성전자, HBM5보다 8배 빠른 zHBM 공개",
        "zhbm",
        {"돈 버는 능력", "시간표"},
    ),
    (
        "삼성 파운드리 4나노 풀캐파·5나노 주문 증가",
        "풀캐파",
        {"돈 버는 능력", "시간표"},
    ),
    (
        "구리값 사상 최고…광산 사고로 공급난 가중",
        "공급난",
        {"돈 버는 능력", "시간표"},
    ),
    (
        "삼전닉스 레버리지 규제 후 코스피200으로 자금 이동",
        "자금 이동",
        {"수급", "시간표"},
    ),
)

# The 2026-08-22 attachment had 35 source articles. Duplicated wire stories are
# retained in the source count, while operational coverage is decided per theme.
ATTACHMENT_20260822_GROUPS = {
    "iran_china_trade_policy": {"source_items": 1, "route": "policy"},
    "iran_china_oil_trade": {"source_items": 1, "route": "send"},
    "us_equity_market_recap": {"source_items": 1, "route": "conditional"},
    "samsung_labor_compensation": {"source_items": 1, "route": "conditional"},
    "skhynix_overseas_hbm_production": {"source_items": 1, "route": "send"},
    "samsung_tv_memory_cost_share": {"source_items": 1, "route": "send"},
    "trump_asset_trade_disclosure": {"source_items": 8, "route": "policy"},
    "skhynix_stock_split_commentary": {"source_items": 1, "route": "exclude"},
    "ymtc_nand_ipo": {"source_items": 1, "route": "send"},
    "us_canada_tariff_trade": {"source_items": 4, "route": "send"},
    "anthropic_ipo_ai_infrastructure": {"source_items": 2, "route": "send"},
    "samsung_skhynix_hbm_hotchips": {"source_items": 1, "route": "send"},
    "us_beef_tariff_policy": {"source_items": 3, "route": "policy"},
    "samsung_social_support": {"source_items": 1, "route": "exclude"},
    "nvidia_ai_server_memory_price": {"source_items": 1, "route": "send"},
    "high_yield_stock_recommendation": {"source_items": 1, "route": "exclude"},
    "samsung_skhynix_fcf_returns": {"source_items": 1, "route": "send"},
    "skhynix_return_leverage_etf": {"source_items": 1, "route": "send"},
    "korea_etf_asset_valuation": {"source_items": 1, "route": "send"},
    "bigtech_ai_credit_yield": {"source_items": 1, "route": "send"},
    "us_apec_china_policy": {"source_items": 1, "route": "policy"},
    "us_midterm_seasonality": {"source_items": 1, "route": "exclude"},
}

ATTACHMENT_ALERT_CASES = (
    (
        "트럼프, 이란의 최대 무역 상대국 중국에 경제적 D-Day 경고",
        "이란의 최대 무역 상대국 중국을 겨냥해 트럼프가 경제적 D-Day를 예고했습니다.",
        "iran_china_trade_policy",
        "이란",
    ),
    (
        "이란 휴전 기대 후퇴에 중국 원유 수입 차질·브렌트 상승",
        "이란 휴전 기대가 후퇴하며 중국 원유 수입 차질 우려와 브렌트 상승이 나왔습니다.",
        "iran_china_oil_trade",
        "이란",
    ),
    (
        "SK하이닉스, 일본 반도체 공장 건설 검토",
        "SK하이닉스가 HBM 생산 확대를 위해 일본 반도체 공장 건설을 검토합니다.",
        "skhynix_overseas_hbm_production",
        "SK하이닉스",
    ),
    (
        "삼성전자 TV 출하 1위…미니 LED 확대와 메모리 원가 부담",
        "삼성전자가 TV 출하량 1위를 지켰지만 미니 LED 확대와 메모리 가격 상승이 원가를 압박합니다.",
        "samsung_tv_memory_cost_share",
        "삼성전자",
    ),
    (
        "삼성전자 노조, 성과급·임단협 재협상 요구",
        "삼성전자 노조가 성과급과 임단협 재협상을 요구해 반도체 가동 리스크가 커졌습니다.",
        "samsung_labor_compensation_risk",
        "삼성전자",
    ),
    (
        "YMTC, 낸드 생산 확대 위한 IPO 추진",
        "YMTC가 낸드와 SSD 생산 확대 자금을 조달하기 위해 IPO를 추진합니다.",
        "ymtc_nand_ipo",
        "YMTC",
    ),
    (
        "미국·캐나다 무역협정 결렬, 관세 50% 보복 우려",
        "미국과 캐나다의 무역협정이 결렬돼 관세 50%와 북미 공급망 불확실성이 커졌습니다.",
        "us_canada_tariff_trade",
        "캐나다",
    ),
    (
        "앤트로픽, AI 데이터센터 투자 확대 앞두고 IPO 검토",
        "앤트로픽이 AI 데이터센터 투자 확대를 위해 기업가치 산정과 IPO를 검토합니다.",
        "anthropic_ipo_ai_infrastructure",
        "앤트로픽",
    ),
    (
        "삼성전자·SK하이닉스, 핫칩스에서 HBM 기술 공개",
        "삼성전자와 SK하이닉스가 핫칩스에서 HBM 기술을 공개하고 고객 인증 일정을 제시합니다.",
        "samsung_skhynix_hbm_hotchips",
        "HBM",
    ),
    (
        "엔비디아, 메모리 부족에 AI 서버 가격 15% 인상",
        "엔비디아가 메모리 부족으로 AI 서버 가격을 15% 인상하겠다고 고객사에 통보했습니다.",
        "nvidia_ai_server_memory_price",
        "엔비디아",
    ),
    (
        "빅테크 AI 투자 확대에 회사채 발행·미국 국채 금리 상승",
        "빅테크의 AI 데이터센터 투자 확대가 회사채 발행과 미국 국채 금리 상승으로 이어졌습니다.",
        "bigtech_ai_credit_yield",
        "빅테크",
    ),
    (
        "APEC 앞두고 미국 우선주의 의제와 중국 정상회담 주목",
        "APEC에서 미국 우선주의 의제와 중국 정상회담이 수출통제 위험을 바꿀 수 있습니다.",
        "us_apec_china_policy",
        "APEC",
    ),
    (
        "트럼프, 미국산 쇠고기 관세 철폐 검토",
        "트럼프 행정부가 미국산 쇠고기 수입 관세 철폐와 통상 협상을 검토합니다.",
        "us_beef_tariff_policy",
        "쇠고기",
    ),
    (
        "트럼프 자산공시, 대형 주식 거래 내역 공개",
        "트럼프 자산공시에 투자계좌와 대형 주식 거래 내역이 공개됐습니다.",
        "trump_asset_trade_disclosure",
        "트럼프",
    ),
    (
        "국내 ETF 순자산 두 달 새 60조원 감소",
        "국내 주식형 ETF 순자산이 기초자산 가격 하락과 레버리지 규제 영향으로 두 달 새 60조원 감소했습니다.",
        "korea_etf_asset_flow",
        "60조원 감소",
    ),
)


ATTACHMENT_20260823_GROUPS = {
    "iran_economic_war_trade_risk": {"source_items": 1, "route": "policy"},
    "russia_ukraine_economic_targets": {"source_items": 1, "route": "conditional"},
    "agi_advanced_packaging_hbm_bottleneck": {"source_items": 1, "route": "send"},
    "active_covered_call_etf_net_buy": {"source_items": 1, "route": "send"},
    "samsung_exynos_2nm_performance": {"source_items": 1, "route": "send"},
    "nvidia_earnings_jackson_hole_calendar": {"source_items": 1, "route": "send"},
    "nvidia_ai_server_memory_price": {"source_items": 1, "route": "send"},
    "us_fiscal_deficit_treasury_yield": {"source_items": 1, "route": "send"},
}

ATTACHMENT_20260823_ALERT_CASES = (
    (
        "테헤란, 미국 경제 전쟁 무력화 다짐",
        "테헤란은 미국의 경제 전쟁을 무력화하겠다고 다짐하며 제재와 원유 수출 불확실성이 이어졌습니다.",
        "iran_economic_war_trade_risk",
        "테헤란",
    ),
    (
        "푸틴, 우크라이나 경제적 목표물 공격은 판도라의 상자",
        "푸틴은 우크라이나 경제적 목표물 공격이 판도라의 상자를 열었다고 말해 에너지·물류 위험을 경고했습니다.",
        "russia_ukraine_economic_targets",
        "푸틴",
    ),
    (
        "반도체 패키징이 AGI 성패 좌우…HBM 병목 심화",
        "AGI 연산 확대에 반도체 패키징과 HBM 병목이 심해지면 한국 공급망에 기회가 커질 수 있습니다.",
        "agi_advanced_packaging_hbm_bottleneck",
        "AGI",
    ),
    (
        "ACE 고배당주PLUS커버드콜액티브 순매수 1천억 돌파",
        "ACE 고배당주PLUS커버드콜액티브 ETF 순매수가 1천억원을 돌파했습니다.",
        "active_covered_call_etf_net_buy",
        "ACE",
    ),
    (
        "삼성 엑시노스 사내 테스트서 퀄컴칩 압도",
        "엑시노스가 사내 테스트에서 퀄컴칩을 앞섰고 삼성 2나노 공정 적용 가능성이 거론됐습니다.",
        "samsung_exynos_2nm_performance",
        "엑시노스",
    ),
    (
        "엔비디아 실적 발표와 잭슨홀 미팅에 주목",
        "엔비디아 실적 발표와 잭슨홀 회의가 AI 투자심리와 금리 경로를 가를 일정으로 주목됩니다.",
        "nvidia_earnings_jackson_hole_calendar",
        "엔비디아",
    ),
    (
        "엔비디아도 메모리 부족에 AI 서버 가격 15% 인상",
        "엔비디아가 메모리 부족으로 AI 서버 가격을 15% 인상하겠다고 고객사에 통보했습니다.",
        "nvidia_ai_server_memory_price",
        "엔비디아",
    ),
    (
        "미국 재정적자 40조달러, 장기 국채 금리 상승 경고",
        "미국 재정적자가 40조달러로 늘면서 30년물 국채 금리 상승과 달러 경로가 경고 요인으로 지목됐습니다.",
        "us_fiscal_deficit_treasury_yield",
        "미국",
    ),
)


def source_row(title: str, body: str) -> dict:
    return {
        "source_title": title,
        "title": title,
        "source_body": body,
        "source_abstract": body,
        "source": "contract fixture",
        "publisher": "contract fixture",
        "link": "https://example.com/article",
        "published": datetime(2026, 8, 22, tzinfo=timezone.utc),
        "body_verified": True,
    }


def main() -> int:
    failures = []
    configured = {item[0] for item in radar.KOREAN_BUSINESS_SEARCH_SOURCES}
    missing = SEARCH_NAMES - configured
    if missing:
        failures.append(f"missing_searches={sorted(missing)}")

    for title, required_term, required_impacts in CASES:
        lowered = title.lower()
        material = {
            term
            for term in radar.KOREAN_BUSINESS_MATERIAL_TERMS
            if radar.korean_business_title_has_material_term(lowered, term)
        }
        impacts = set(radar.korean_business_impacts(lowered, []))
        if required_term not in material:
            failures.append(f"missing_material={required_term}:{title}")
        if not required_impacts.issubset(impacts):
            failures.append(
                f"missing_impacts={sorted(required_impacts - impacts)}:{title}"
            )

    route_counts = {}
    for group, item in ATTACHMENT_20260822_GROUPS.items():
        route = item["route"]
        route_counts[route] = route_counts.get(route, 0) + int(item["source_items"])
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment_route={group}:{route}")
    source_item_count = sum(
        int(item["source_items"]) for item in ATTACHMENT_20260822_GROUPS.values()
    )
    if source_item_count != 35:
        failures.append(f"attachment_source_count={source_item_count}:expected=35")
    if route_counts.get("send", 0) < 14:
        failures.append(f"attachment_send_coverage={route_counts.get('send', 0)}")

    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    for title, body, expected_kind, required_fact in ATTACHMENT_ALERT_CASES:
        row = source_row(title, body)
        alert = radar.build_attachment_verified_event_alert(
            row, now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                f"attachment_alert_kind={alert.get('korean_business_kind')}:"
                f"expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment_alert_incomplete_core={expected_kind}:{core!r}"
            )

    attachment23_route_counts = {}
    for group, item in ATTACHMENT_20260823_GROUPS.items():
        route = item["route"]
        attachment23_route_counts[route] = (
            attachment23_route_counts.get(route, 0) + int(item["source_items"])
        )
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment23_route={group}:{route}")
    attachment23_source_item_count = sum(
        int(item["source_items"]) for item in ATTACHMENT_20260823_GROUPS.values()
    )
    if attachment23_source_item_count != 8:
        failures.append(
            f"attachment23_source_count={attachment23_source_item_count}:expected=8"
        )
    if attachment23_route_counts.get("send", 0) < 6:
        failures.append(
            f"attachment23_send_coverage={attachment23_route_counts.get('send', 0)}"
        )

    for title, body, expected_kind, required_fact in ATTACHMENT_20260823_ALERT_CASES:
        row = source_row(title, body)
        alert = radar.build_attachment_verified_event_alert(
            row, now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment23_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                f"attachment23_alert_kind={alert.get('korean_business_kind')}:"
                f"expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment23_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment23_alert_incomplete_core={expected_kind}:{core!r}"
            )

    ymtc_row = source_row(
        "YMTC, 낸드 생산 확대 위한 IPO 추진",
        "YMTC가 낸드와 SSD 생산 확대 자금을 조달하기 위해 IPO를 추진합니다.",
    )
    ymtc_alert = radar.build_china_memory_ipo_alert(
        ymtc_row, now, "ymtc 낸드 ssd ipo 상장 추진"
    )
    if not ymtc_alert or "YMTC" not in str(ymtc_alert.get("telegram_core_fact")):
        failures.append("ymtc_memory_ipo_builder_missing")

    etf_row = source_row(
        "국내 ETF 순자산 두 달 새 60조원 감소",
        "국내 주식형 ETF 순자산이 기초자산 가격 하락과 레버리지 규제 영향으로 두 달 새 60조원 감소했습니다.",
    )
    etf_alert = radar.build_attachment_verified_event_alert(
        etf_row, now, "국내 주식형 etf 순자산 기초자산 가격 하락 레버리지 규제 60조원 감소"
    )
    etf_core = str((etf_alert or {}).get("telegram_core_fact") or "")
    if "60조원 감소" not in etf_core or "유입" in etf_core or "유출" in etf_core:
        failures.append(f"etf_valuation_not_flow={etf_core!r}")

    # A clipped source fragment must be rejected, never completed by invention.
    prose_cases = (
        ("MSCI 반영 시 1조원대 자금 유입을 기대할…", ""),
        ("및 수주잔고 20억달러를 기록했습니다.", "수주잔고 20억달러를 기록했습니다."),
    )
    for raw, expected in prose_cases:
        actual = radar.complete_prose_text(raw, limit=100)
        if actual != expected:
            failures.append(f"damaged_core_prose={actual!r}:expected={expected!r}")
        if actual and not radar.core_sentence_is_complete(actual, limit=100):
            failures.append(f"incomplete_core_prose={actual!r}")

    if failures:
        print("GAMEJOA cross-market coverage contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        "cross_market_coverage_contract=passed "
        f"cases={len(CASES)} attachment_cases={len(ATTACHMENT_ALERT_CASES)} "
        f"attachment_groups={len(ATTACHMENT_20260822_GROUPS)} "
        f"source_items={source_item_count} "
        f"attachment23_cases={len(ATTACHMENT_20260823_ALERT_CASES)} "
        f"attachment23_groups={len(ATTACHMENT_20260823_GROUPS)} "
        f"attachment23_source_items={attachment23_source_item_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regression gate for cross-market and next-generation semiconductor coverage."""

import gamejoa_preopen_news_radar_full_compact_runner as radar


SEARCH_NAMES = {
    "미국장 빅테크 실적·한국 ADR·반도체 수급",
    "HBM5·zHBM·HBF 차세대 메모리 기술·상용화",
    "메모리 장기공급·수요전망·고객 사양 변경",
    "삼성 파운드리 가동률·풀캐파·공정 주문",
    "핵심 원자재 사상최고·공급차질",
    "레버리지 규제 후 거래대금·자금이동",
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

    if failures:
        print("GAMEJOA cross-market coverage contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"cross_market_coverage_contract=passed cases={len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


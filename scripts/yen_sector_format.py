#!/usr/bin/env python3
"""Formatting and confidence rules for sector-reaction output."""
from __future__ import annotations

import datetime as dt

from yen_sector_config import *
from yen_sector_data import all_symbols


def spec_map() -> dict[str, SectorSpec]:
    return {spec.key: spec for spec in SECTORS}


def confidence_label(results: list[SectorResult]) -> str:
    aligned = sum(item.aligned is True for item in results)
    contrary = sum(item.contrary is True for item in results)
    if contrary >= 2 or (aligned > 0 and contrary > 0):
        return "혼재"
    if aligned >= 3 and contrary == 0:
        return "높음"
    if aligned >= 2:
        return "중간"
    return "미확인"


def result_signal(item: SectorResult) -> str:
    if item.expected_sign == 0:
        return "환율 직접 영향 판단 보류"
    if item.aligned:
        return "예상 방향 확인"
    if item.contrary:
        return "예상과 반대"
    return "유의한 상대변동 미확인"


def benchmark_label(item: SectorResult) -> str:
    spec = spec_map().get(item.key)
    return spec.benchmark_label if spec is not None else "시장"


def result_line(item: SectorResult) -> str:
    breadth = ""
    if item.breadth_pct is not None:
        breadth = f" · 확산 {item.breadth_pct:.0f}%"
    return (
        f"• {item.name}: {item.sector_change_pct:+.2f}% / "
        f"{benchmark_label(item)} {item.benchmark_change_pct:+.2f}% "
        f"→ 상대 {item.relative_pct:+.2f}%p"
        f"({item.timeframe}, {item.market_status})"
        f"{breadth} · {result_signal(item)}"
    )


def select_display_results(
    results: list[SectorResult],
    limit: int = 7,
) -> list[SectorResult]:
    priority_keys = {"kr_semis", "kr_semicap"}
    priority = [item for item in results if item.key in priority_keys]
    priority.sort(key=lambda item: item.key)
    others = [item for item in results if item.key not in priority_keys]
    others.sort(
        key=lambda item: (item.significant, abs(item.relative_pct)),
        reverse=True,
    )
    selected = others[: max(0, limit - len(priority))] + priority
    return selected[:limit]


def observed_sector_block(
    results: list[SectorResult],
    errors: dict[str, str],
) -> str:
    if not results:
        return "\n".join(
            [
                SECTOR_HEADING,
                "실측 실패: 업종·시장 데이터가 충분하지 않아 예상 영향만 유지합니다.",
                "주의: 업종 실측 실패가 환율 경보 자체를 무효화하지는 않습니다.",
            ]
        )
    confidence = confidence_label(results)
    lines = [
        SECTOR_HEADING,
        (
            "실제 업종 반응: 각 업종에 맞는 기준지수"
            "(TOPIX·KOSPI 200·KOSDAQ 150) 대비 상대수익률"
        ),
        *(result_line(item) for item in select_display_results(results)),
        f"종합 판정: 엔화 강세 연동 가능성 {confidence}",
    ]
    if errors:
        lines.append(
            f"데이터 참고: 전체 {len(all_symbols())}개 중 "
            f"{len(errors)}개 조회 실패·제외"
        )
    lines.append(
        "주의: 상대수익률은 연동 가능성을 보여줄 뿐, "
        "환율이 유일한 원인임을 뜻하지 않습니다."
    )
    return "\n".join(lines)


def replace_sector_block(body: str, block: str) -> str:
    lines = body.splitlines()
    try:
        start = lines.index(SECTOR_HEADING)
    except ValueError:
        start = -1
    if start >= 0:
        while start > 0 and not lines[start - 1].strip():
            start -= 1
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if lines[index].strip() == FINAL_MARKER
            ),
            len(lines),
        )
        del lines[start:end]
    insert_at = next(
        (
            index
            for index, item in enumerate(lines)
            if item.strip() == FINAL_MARKER
        ),
        len(lines),
    )
    while insert_at > 0 and not lines[insert_at - 1].strip():
        del lines[insert_at - 1]
        insert_at -= 1
    lines[insert_at:insert_at] = ["", *block.splitlines(), ""]
    return "\n".join(lines).strip() + "\n"


def parse_datetime(value: object) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(UTC)


def result_baseline(results: list[SectorResult]) -> dict[str, dict]:
    specs = spec_map()
    baseline: dict[str, dict] = {}
    for item in results:
        spec = specs.get(item.key)
        baseline[item.key] = {
            "name": item.name,
            "country": item.country,
            "expected_sign": item.expected_sign,
            "component_prices": item.component_prices,
            "benchmark_price": item.benchmark_price,
            "benchmark_symbol": spec.benchmark if spec is not None else None,
            "benchmark_label": (
                spec.benchmark_label if spec is not None else "시장"
            ),
            "data_epoch": item.data_epoch,
        }
    return baseline

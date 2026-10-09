#!/usr/bin/env python3
"""Add Bessent policy-coordination and cross-asset interpretation to yen-carry alerts.

This is a presentation layer only. It does not create a new alert trigger and does not
change the underlying USD/JPY or carry-unwind thresholds. It enriches an alert only
when an existing yen-carry lane has already produced an alert file.
"""
from __future__ import annotations

import pathlib

PRIMARY_BODY = pathlib.Path("out/yen_carry_alert.md")
FX_BODY = pathlib.Path("out/yen_carry_fx_shock_alert.md")
COMPOSITE_BODY = pathlib.Path("out/yen_carry_composite_alert.md")

HEADING = "정책·주식 해석"
COMPOSITE_HEADING = "미·일 정책공조·시장 영향"
SECTOR_HEADING = "산업·업종 영향"
FINAL_MARKER = "이 경보는 기존 엔캐리 청산 확정 경보와 별개입니다."


def interpretation_block() -> str:
    return "\n".join(
        [
            HEADING,
            "• 정책 단계: ‘I am the house now’는 <b>구두개입·정책정보 우위 경고</b>로 분류합니다. 특정 USD/JPY 숫자를 공식 방어선으로 선언한 것으로 보지 않습니다.",
            "• 확인 순서: <b>구두개입 → 미·일 정책공조 → 실제 외환시장 개입 → USD/JPY → 엔 숏·캐리 축소</b>. 발언만으로 정책 성공이나 엔캐리 청산을 확정하지 않습니다.",
            "• 지속성 검증: 정책 발언 직후 하루 반응과 5영업일·20영업일 지속효과를 분리합니다. 엔화가 다시 발언 이전 약세권으로 복귀하면 구두개입 효과 약화로 낮춰 판정합니다.",
            "• 주식시장 영향: 질서 있는 엔 강세·점진적 숏 축소만이면 미국 성장주 영향은 대체로 중립이고, 일본 수출주는 부담·일본 은행주는 금리정상화가 동반될 때 상대 우호입니다.",
            "• 위험 전환: <b>USD/JPY 급락 + 변동성 급등 + Nasdaq·KOSPI·BTC 동반 하락</b>이면 엔캐리 강제청산으로 판정해 🔴 글로벌 위험자산 수급 악재로 격상합니다.",
            "• 한국 영향: 원화가 안정적인데 엔화만 강해지면 일본 경쟁 수출주의 가격 우위가 약해져 한국 자동차·기계에는 상대적으로 우호적일 수 있으나, 글로벌 강제 디레버리징이 붙으면 이 효과보다 외국인 수급 악화가 우선합니다.",
            "• 역할 분리: BOJ 결정·미일 공조·실제 개입의 확정 사실은 별도 정책 감시가 담당하고, 이 알림은 USD/JPY와 엔캐리의 <b>실제 시장반응</b>만 판정합니다.",
            "• 경계선: 정책당국이 특정 환율 숫자를 반복적으로 사실상 방어선처럼 제시하면 🟠 시장의 방어선 테스트·정책 신뢰 위험으로 별도 경보합니다.",
        ]
    )



COMPOSITE_STOP_HEADINGS = {
    "판정",
    "이번 변화",
    "시장·금리",
    "포지션·자금",
    "정책",
    "정확한 의미",
    "구조적 경계·자금환류",
    "JGB 입찰 수요",
    "실질금리·정책 정상화",
    "긴축 경로·레버리지",
    "주식시장 영향",
    "자료 확인 상태",
    "출처",
}


def composite_interpretation_block() -> str:
    return "\n".join(
        [
            COMPOSITE_HEADING,
            "• 정책 단계: Bessent의 ‘I am the house now’는 <b>구두개입·정책정보 우위 경고</b>입니다. 특정 USD/JPY 숫자를 공식 방어선으로 선언한 것으로 보지 않습니다.",
            "• 확인 순서: <b>구두개입 → 미·일 정책공조 → 실제 외환시장 개입 → BOJ 정책 → USD/JPY → 엔 숏·캐리 축소</b>. 발언만으로 정책 성공이나 청산을 확정하지 않습니다.",
            "• 지속성 검증: 하루 반응과 5영업일·20영업일 지속효과를 분리합니다. 엔화가 다시 발언 이전 약세권으로 복귀하면 구두개입 효과 약화로 낮춰 판정합니다.",
            "• 주식시장: <b>질서 있는 엔 강세·점진적 숏 축소는 중립~약한 우호</b>지만, USD/JPY 급락·변동성 급등과 Nasdaq·KOSPI·BTC 동반 하락이 겹치면 엔캐리 강제청산으로 보고 🔴 위험자산 수급 악재로 격상합니다.",
            "• 한국시장: 원화가 안정적인데 엔화만 강해지면 일본 경쟁 수출주의 가격 우위가 약해져 한국 자동차·기계에는 상대 우호적일 수 있습니다. 다만 글로벌 디레버리징이 붙으면 외국인 수급 악화가 우선합니다.",
            "• 정책 경계선: 특정 환율 숫자를 반복적으로 사실상 방어선처럼 제시하면 <b>시장 방어선 테스트·정책 신뢰 위험</b>으로 별도 경보합니다.",
        ]
    )


def insert_composite_block(body: str) -> str:
    lines = body.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == COMPOSITE_HEADING)
    except StopIteration:
        start = -1
    if start >= 0:
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].strip() in COMPOSITE_STOP_HEADINGS:
                end = i
                break
        del lines[start:end]
        while start < len(lines) and not lines[start].strip():
            del lines[start]

    insert_at = len(lines)
    for marker in ("주식시장 영향", "자료 확인 상태", "출처"):
        for i, line in enumerate(lines):
            if line.strip() == marker:
                insert_at = min(insert_at, i)
                break
    while insert_at > 0 and not lines[insert_at - 1].strip():
        del lines[insert_at - 1]
        insert_at -= 1
    lines[insert_at:insert_at] = ["", *composite_interpretation_block().splitlines(), ""]
    return "\n".join(lines).strip() + "\n"


def enrich_composite(path: pathlib.Path) -> str:
    if not path.exists():
        return "skipped_no_alert"
    body = path.read_text(encoding="utf-8")
    path.write_text(insert_composite_block(body), encoding="utf-8")
    return "added"

def _remove_existing(lines: list[str]) -> list[str]:
    try:
        start = lines.index(HEADING)
    except ValueError:
        return lines

    end = len(lines)
    for index in range(start + 1, len(lines)):
        item = lines[index].strip()
        if item in (SECTOR_HEADING, FINAL_MARKER):
            end = index
            break
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    return lines


def insert_block(body: str) -> str:
    lines = _remove_existing(body.splitlines())
    insert_at = len(lines)
    for marker in (SECTOR_HEADING, FINAL_MARKER):
        try:
            insert_at = min(insert_at, lines.index(marker))
        except ValueError:
            pass
    while insert_at > 0 and not lines[insert_at - 1].strip():
        del lines[insert_at - 1]
        insert_at -= 1
    lines[insert_at:insert_at] = ["", *interpretation_block().splitlines(), ""]
    return "\n".join(lines).strip() + "\n"


def enrich(path: pathlib.Path) -> str:
    if not path.exists():
        return "skipped_no_alert"
    body = path.read_text(encoding="utf-8")
    path.write_text(insert_block(body), encoding="utf-8")
    return "added"


def main() -> int:
    print(f"yen_carry_policy_equity={enrich(PRIMARY_BODY)}")
    print(f"yen_fx_policy_equity={enrich(FX_BODY)}")
    print(f"yen_composite_policy_equity={enrich_composite(COMPOSITE_BODY)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

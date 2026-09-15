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

HEADING = "정책·주식 해석"
SECTOR_HEADING = "산업·업종 영향"
FINAL_MARKER = "이 경보는 기존 엔캐리 청산 확정 경보와 별개입니다."


def interpretation_block() -> str:
    return "\n".join(
        [
            HEADING,
            "• 정책 신호: Bessent의 ‘I am the house now’는 특정 USD/JPY 방어선이 아니라 정책정보 우위·구두개입 경고로 분류합니다.",
            "• 확인 순서: 발언 → BOJ·미일 정책행동 → 실제 외환시장 개입 → USD/JPY → 엔 숏·캐리 축소. 발언만으로 성공 판정하지 않습니다.",
            "• 주식: 질서 있는 엔 강세·포지션 축소만이면 중립. USD/JPY 급락 + 변동성 급등 + Nasdaq·KOSPI 동반 하락이면 🔴 강제 캐리청산 수급 악재로 격상합니다.",
            "• 일본: 수출주는 엔 강세가 부담이고, BOJ 인상과 장단기금리 정상화가 동반되면 은행주는 상대적으로 우호적일 수 있습니다.",
            "• 역할 분리: BOJ 정책·실제 개입 상세는 별도 정책 감시가 담당하고, 이 알림은 USD/JPY·엔캐리의 실제 시장반응만 판정합니다.",
            "• 경계선: 특정 환율 숫자를 방어선처럼 반복 제시하면 🟠 시장의 방어선 테스트 위험으로 별도 경보합니다.",
        ]
    )


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

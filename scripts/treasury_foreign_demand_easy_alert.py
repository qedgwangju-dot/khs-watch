#!/usr/bin/env python3
"""Prepend a plain-language interpretation block to Treasury foreign-demand alerts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
ALERT = OUT / "treasury_foreign_demand_alert.md"
DETAIL = OUT / "treasury_foreign_demand_detail.json"


def fmt_bn(v: float | None, *, signed: bool = False) -> str:
    if v is None:
        return "확인 불가"
    sign = "+" if signed and v > 0 else ""
    if abs(v) >= 1000:
        return f"{sign}{v / 1000:,.3f}조달러"
    return f"{sign}{v * 10:,.0f}억달러"


def tic_easy(detail: dict) -> list[str]:
    holding = detail.get("core3_change_bn")
    net = detail.get("core3_net_bn")
    val = detail.get("core3_lt_val_bn")
    total = detail.get("total_change_bn")

    if net is None:
        badge = "🟡"
        one = "보유액은 움직였지만 실제 순매매 자료가 완전히 확인되지 않아 매도·매수로 단정하면 안 됩니다."
        rate = "장기금리 영향은 중립 판단 — 거래자료 확인이 먼저입니다."
    elif holding is not None and holding < 0 and net >= 0:
        badge = "🟢"
        one = "일본·영국·중국의 보유액은 줄었지만 실제 거래는 순매도가 아닙니다. ‘외국이 미국채를 던졌다’고 볼 상황은 아닙니다."
        rate = "보유액 감소만으로 10년·30년 금리 상승 재료로 보면 과장입니다. 평가손실·기타 조정 영향이 더 큽니다."
    elif holding is not None and holding < 0 and net <= -20:
        badge = "🔴"
        one = "일본·영국·중국의 보유액 감소와 실제 순매도가 함께 확인됐습니다. 해외 미국채 수요 약화 신호가 뚜렷합니다."
        rate = "민간이 더 많은 국채를 받아야 해 기간 프리미엄과 10년·30년 금리에 상승 압력이 될 수 있습니다."
    elif holding is not None and holding < 0 and net < 0:
        badge = "🟡"
        one = "보유액 감소와 실제 순매도가 함께 나왔지만, 아직 대규모 수요 이탈로 단정할 단계인지는 규모와 다음 달 흐름을 봐야 합니다."
        rate = "장기금리에는 부담 방향이지만 Fed 보관잔액과 10·30년 입찰로 확인이 필요합니다."
    elif holding is not None and holding > 0 and net > 0:
        badge = "🟢"
        one = "보유액 증가와 실제 순매수가 같이 확인돼 해외 미국채 수요는 양호한 방향입니다."
        rate = "국채 수급에는 우호적이며 장기금리의 공급·수요 압력을 일부 낮추는 신호입니다."
    else:
        badge = "🟡"
        one = "보유액과 실제 거래 방향이 엇갈려 한 가지 원인으로 설명하기 어렵습니다."
        rate = "장기금리 영향은 혼합 — 다음 TIC와 Fed 주간 보관잔액을 같이 봐야 합니다."

    return [
        "쉽게 말하면",
        f"{badge} {one}",
        f"• 일본+영국+중국 보유액 변화: {fmt_bn(holding, signed=True)}",
        f"• 일본+영국+중국 실제 순거래: {fmt_bn(net, signed=True)}",
        f"• 장기채 평가효과: {fmt_bn(val, signed=True)}",
        f"• 전체 외국인 보유액 변화: {fmt_bn(total, signed=True)}",
        f"• 금리 해석: {rate}",
        "• 주식 해석: 실제 해외 순매도와 장기 실질금리 상승이 함께 확인될 때 AI·성장주 할인율 부담이 커집니다.",
        "• 핵심 주의: ‘보유액 감소’ ≠ ‘그만큼 실제 매도’. 영국·벨기에·룩셈부르크·케이맨은 보관기관 위치 효과도 큽니다.",
    ]


def h41_easy(detail: dict) -> list[str]:
    weekly = detail.get("weekly_bn")
    four = detail.get("four_week_bn")
    yoy = detail.get("yoy_bn")

    if weekly is not None and weekly <= -20 and four is not None and four <= -50:
        badge = "🔴"
        one = "해외 공식계정의 미국채 보관잔액이 1주와 4주 기준 모두 크게 줄었습니다. 해외 공식수요 약화 경보가 강해졌습니다."
        rate = "지속되면 민간 흡수 부담 증가 → 기간 프리미엄·10년/30년 금리 상승 압력으로 연결될 수 있습니다."
    elif weekly is not None and weekly < 0:
        badge = "🟡"
        one = "해외 공식계정 보관잔액이 의미 있게 줄었습니다. 다만 한 주 수치만으로 실제 매도를 확정하면 안 됩니다."
        rate = "장기금리에는 부담 방향이지만 월간 TIC와 국채 입찰 확인 전에는 경계 신호로 봅니다."
    else:
        badge = "🟢"
        one = "해외 공식계정 보관잔액이 증가해 주간 수급은 우호적입니다."
        rate = "국채 수요 측면에서 장기금리 상승 압력을 완화하는 방향입니다."

    return [
        "쉽게 말하면",
        f"{badge} {one}",
        f"• 주간 변화: {fmt_bn(weekly, signed=True)}",
        f"• 4주 변화: {fmt_bn(four, signed=True)}",
        f"• 전년 대비: {fmt_bn(yoy, signed=True)}",
        f"• 금리 해석: {rate}",
        "• 핵심 주의: Fed H.4.1은 해외 공식·국제계정 보관잔액이라 전체 외국인 보유액과 범위가 다릅니다.",
    ]


def main() -> int:
    if not ALERT.exists() or not DETAIL.exists():
        return 0

    detail = json.loads(DETAIL.read_text(encoding="utf-8"))
    original = ALERT.read_text(encoding="utf-8").strip()
    kind = detail.get("type")
    easy = tic_easy(detail) if kind == "tic" else h41_easy(detail) if kind == "h41" else []
    if not easy:
        return 0

    # Keep the easy interpretation first so Telegram's 4096-character cap preserves the conclusion.
    merged = "\n".join(easy) + "\n\n세부 숫자·근거\n" + original
    ALERT.write_text(merged[:4096].rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

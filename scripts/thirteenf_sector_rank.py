#!/usr/bin/env python3
"""Ranking of *position changes* reported in SEC 13F, not executed trades.

Values are proportional quarter-end marks on changed common-share quantities.
Option rows are excluded because 13F underlying values are not paid premiums.
Do not calculate a bogus buy-minus-sell cash flow across quarterly marks.
"""
from collections import defaultdict


def changed_share_reference_value(x):
    """Return (side, reference USD) for an ordinary share change, or (None, 0)."""
    if (x.get("putcall") or "").upper() in {"CALL", "PUT"}:
        return None, 0.0
    action = x.get("action")
    delta = float(x.get("delta_shares") or 0)
    shares = float(x.get("shares") or 0)
    if action in {"신규 매수", "보유 확대"} and delta > 0 and shares > 0:
        current = float(x.get("cur_value") or 0)
        if current > 0:
            return "buy", current * delta / shares
    if action in {"보유 축소", "전량 청산"} and delta < 0:
        previous = float(x.get("prev_value") or 0)
        previous_shares = shares if action == "전량 청산" else shares - delta
        if previous > 0 and previous_shares > 0:
            return "sell", previous * (-delta) / previous_shares
    return None, 0.0


def rank_changes(changes):
    sectors = defaultdict(lambda: {
        "buy_value": 0.0, "sell_value": 0.0,
        "buy_rows": 0, "sell_rows": 0,
    })
    unknown = 0
    options = 0
    for item in changes:
        if (item.get("putcall") or "").upper() in {"CALL", "PUT"}:
            options += 1
            continue
        direction, value = changed_share_reference_value(item)
        if direction is None:
            unknown += 1
            continue
        sec=item.get("sector") or "기타"
        group=sectors[sec]
        group[direction+"_value"] += value
        group[direction+"_rows"] += 1
    buys=sorted(
        [(sec,v) for sec,v in sectors.items() if v["buy_rows"] and sec != "기타"],
        key=lambda x:(-x[1]["buy_value"],x[0]),
    )
    sells=sorted(
        [(sec,v) for sec,v in sectors.items() if v["sell_rows"] and sec != "기타"],
        key=lambda x:(-x[1]["sell_value"],x[0]),
    )
    return buys,sells,sectors.get("기타"),options,unknown


def build_ranking(changes, money):
    buys,sells,unknown,options,unpriced=rank_changes(changes)
    lines=["▶ 업종별 신규 편입·보유 확대 순위"]
    lines.append("기준: 추가로 보유하게 된 보통주 수량의 당해 분기말 평가액 환산 · 실제 매수대금 아님")
    if not buys:
        lines.append("• 분류·가치 검증된 보통주 매수·확대가 없습니다.")
    for i,(sec,values) in enumerate(buys[:7],1):
        total=values["buy_value"]
        avg=total/values["buy_rows"]
        lines.append(
            f"• {i}위 {sec}: {money(total)} · {values['buy_rows']}개 종목행 · "
            f"행당 평균 {money(avg)}"
        )

    lines += ["", "▶ 업종별 보유 축소·청산 순위"]
    lines.append("기준: 줄어든 보통주 수량의 직전 분기말 평가액 환산 · 매도대금 아님")
    if not sells:
        lines.append("• 분류·가치 검증된 보통주 축소·청산이 없습니다.")
    for i,(sec,values) in enumerate(sells[:5],1):
        lines.append(
            f"• {i}위 {sec}: {money(values['sell_value'])} · "
            f"{values['sell_rows']}개 종목행"
        )
    if unknown and (unknown["buy_rows"] or unknown["sell_rows"]):
        lines.append(
            f"• 업종 미분류: 신규·확대 {unknown['buy_rows']}건 / "
            f"축소·청산 {unknown['sell_rows']}건 · 순위에서 제외"
        )
    if options:
        lines.append(f"• 콜·풋옵션 {options}개 변동행은 주식과 합산하지 않고 별도로 처리합니다.")
    if unpriced:
        lines.append(f"• 참조 평가액이 없는 변동행 {unpriced}건은 금액 합계에서 제외합니다.")
    lines.append(
        "※ 매수·매도 양쪽에 서로 다른 분기말 가격이 적용되므로 "
        "두 값을 빼 실제 현금 순매수라고 표시하지 않습니다."
    )
    return "\n".join(lines)

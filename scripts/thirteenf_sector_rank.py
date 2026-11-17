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


def _security_delta_label(item, display):
    """Use share-count deltas, not valuation-weight movement, for changes."""
    import math
    action=item.get("action")
    name=str(display(item))
    if action=="신규 매수":
        return f"{name} 신규"
    if action=="전량 청산":
        return f"{name} 전량"
    shares=float(item.get("shares") or 0)
    delta=float(item.get("delta_shares") or 0)
    old=shares-delta
    if old<=0 or not math.isfinite(old):
        return f"{name} 수량 변동"
    pct=abs(100*delta/old)
    if not math.isfinite(pct):
        return f"{name} 수량 변동"
    sign="+" if delta>0 else "-"
    return f"{name} {sign}{pct:,.1f}%"


def _group_sector_changes(changes):
    """Reference values of changed ordinary shares, never actual trade cash.

    Compare buy/sell within each separately, because quarters use different
    marking dates. Preserve misc sectors and unpriced rows as visibility gaps.
    """
    groups=defaultdict(lambda: {
        "buy":0.0, "sell":0.0, "buys":[], "sells":[],
    })
    options={"CALL":0,"PUT":0}
    missing=0
    for row in changes:
        pc=str(row.get("putcall") or "").upper()
        if pc in options:
            options[pc]+=1
            continue
        side,value=changed_share_reference_value(row)
        if not side:
            missing+=1
            continue
        group=groups[row.get("sector") or "기타"]
        group[side]+=value
        group["buys" if side=="buy" else "sells"].append((value,row))
    return groups,options,missing


def build_sector_brief(changes, money, display, *, top_n=4):
    """Telegram top-line: industry rotation, leading names and caveats.

    This is a quarterly 13F *position* change, not executed buy/sell flows.
    Existing old-format builder stays available for diagnostics.
    """
    groups,options,missing=_group_sector_changes(changes)
    excluded=groups.get("기타",{})
    recognized={k:v for k,v in groups.items() if k!="기타"}
    buying=sorted(((k,v) for k,v in recognized.items() if v["buys"]),
                  key=lambda kv:(-kv[1]["buy"],kv[0]))
    selling=sorted(((k,v) for k,v in recognized.items() if v["sells"]),
                   key=lambda kv:(-kv[1]["sell"],kv[0]))
    lines=["[업종별 신규편입·보유확대]"]
    if not buying:
        lines.append("• 분류된 보통주 확대 없음")
    for i,(sector,v) in enumerate(buying[:top_n],1):
        important=sorted(v["buys"],key=lambda p:-p[0])[:2]
        names=" · ".join(_security_delta_label(x,display) for _,x in important)
        lines.append(f"• {i}. {sector}: {money(v['buy'])} / {len(v['buys'])}건")
        lines.append(f"  {names}")

    lines += ["", "[업종별 축소·전량청산]"]
    if not selling:
        lines.append("• 분류된 보통주 축소 없음")
    for i,(sector,v) in enumerate(selling[:top_n],1):
        important=sorted(v["sells"],key=lambda p:-p[0])[:2]
        names=" · ".join(_security_delta_label(x,display) for _,x in important)
        lines.append(f"• {i}. {sector}: {money(v['sell'])} / {len(v['sells'])}건")
        lines.append(f"  {names}")

    both=sorted(((k,v) for k,v in recognized.items()
                 if v["buys"] and v["sells"]),
                key=lambda kv:-(kv[1]["buy"]+kv[1]["sell"]))
    if both:
        lines += ["", "[같은 업종 양방향]"]
        for sec,v in both[:2]:
            buy=sorted(v["buys"],key=lambda p:-p[0])[0][1]
            sell=sorted(v["sells"],key=lambda p:-p[0])[0][1]
            lines.append(f"• {sec}: 확대 {_security_delta_label(buy,display)}"
                         f" / 축소 {_security_delta_label(sell,display)}")

    if excluded and (excluded["buys"] or excluded["sells"]):
        lines += ["",f"• 업종 미분류: 확대 {len(excluded['buys'])}건 ({money(excluded['buy'])})"
                 f" / 축소 {len(excluded['sells'])}건 ({money(excluded['sell'])}) · 순위 제외"]
    if options["CALL"] or options["PUT"]:
        lines.append(f"• 옵션 변동 별도: 콜 {options['CALL']}건 / 풋 {options['PUT']}건 (보통주 합산 제외)")
    if missing:
        lines.append(f"• 평가·수량 미확인 변동 {missing}건 제외")
    lines += [
        "※ 확대액=추가 보통주 수량×당분기말 평가단가, 축소액=감소 수량×직전분기말 평가단가의 참고값.",
        "※ 두 금액은 기준시점이 달라 순매수 금액으로 차감하지 않으며 실제 체결대금이 아닙니다.",
        "※ 실제 매매시점·공매도·비상장자산·현금은 13F로 확인되지 않습니다.",
    ]
    return "\n".join(lines)


def _short_share_move(item, display):
    """One position change, shares and % of prior holdings. No cash-flow claim."""
    action=item.get("action")
    name=str(display(item))
    delta=abs(int(round(float(item.get("delta_shares") or 0))))
    qty=f"{delta:,}주"
    if action=="신규 매수":
        return f"{name} 신규 +{qty}"
    if action=="전량 청산":
        return f"{name} 전량 -{qty}"
    prior=float(item.get("shares") or 0)-float(item.get("delta_shares") or 0)
    pct=100*delta/prior if prior>0 else None
    rate=f" ({pct:,.1f}%)" if pct is not None and pct<1_000_000 else ""
    sign="+" if action=="보유 확대" else "-"
    return f"{name} {sign}{qty}{rate}"


def build_sector_direction(changes, display, *, top_n=4):
    """Compact, reliable industry direction from 13F holdings.

    Securities' filed value units are NOT used as currency. Some SEC filing
    numbers disagree with share count times quarter-end market price by 1000x.
    Ranking is by count of changed, classified *non-option reporting rows*,
    NOT cash flow or purchased dollars. Option positions are separate.
    """
    groups=defaultdict(lambda: {"buy":[],"sell":[]})
    opts={"CALL":0,"PUT":0}
    other=0
    for row in changes:
        putcall=str(row.get("putcall") or "").upper()
        if putcall in opts:
            opts[putcall]+=1
            continue
        action=row.get("action")
        delta=float(row.get("delta_shares") or 0)
        if action in {"신규 매수","보유 확대"} and delta>0:
            side="buy"
        elif action in {"보유 축소","전량 청산"} and delta<0:
            side="sell"
        else:
            other+=1
            continue
        group=groups[row.get("sector") or "기타"]
        # Reference is used to pick representative examples within the same
        # filing ONLY; it is not shown or compared as a verified dollar amount.
        _,reference=changed_share_reference_value(row)
        group[side].append((reference,row))

    misc=groups.get("기타",{"buy":[],"sell":[]})
    classified={k:v for k,v in groups.items() if k!="기타"}
    buy=sorted(((k,v) for k,v in classified.items() if v["buy"]),
               key=lambda item:(-len(item[1]["buy"]),-sum(r[0] for r in item[1]["buy"]),item[0]))
    sell=sorted(((k,v) for k,v in classified.items() if v["sell"]),
                key=lambda item:(-len(item[1]["sell"]),-sum(r[0] for r in item[1]["sell"]),item[0]))
    total_buy=sum(len(x["buy"]) for x in groups.values())
    total_sell=sum(len(x["sell"]) for x in groups.values())
    known_buy=total_buy-len(misc["buy"])
    known_sell=total_sell-len(misc["sell"])
    denominator=total_buy+total_sell
    coverage=(100*(known_buy+known_sell)/denominator) if denominator else 0

    def headline(changes, side):
        return ", ".join(f"{sector}({len(v[side])}행)" for sector,v in changes[:2]) or "없음"

    lines=[
        "13F 비옵션 증권 업종 방향 — 분기말 보유수량 변화",
        f"■ 집중 확대: {headline(buy,'buy')}",
        f"■ 집중 축소: {headline(sell,'sell')}",
        "",
        "▶ 신규 편입·보유 확대",
    ]
    if not buy:
        lines.append("• 분류된 업종의 확대 기록 없음")
    for i,(sector,data) in enumerate(buy[:top_n],1):
        rows=data["buy"]
        newly=sum(r["action"]=="신규 매수" for _,r in rows)
        ordered=sorted(rows,key=lambda v:(-v[0],-abs(v[1].get("delta_shares") or 0)))[:2]
        lines.append(f"{i}. {sector} — {len(rows)}행 (신규 {newly}·확대 {len(rows)-newly})")
        lines.append("   "+ " · ".join(_short_share_move(r,display) for _,r in ordered))
    if len(buy)>top_n:
        lines.append(f"• 그 외 확대 업종 {len(buy)-top_n}개")

    lines.extend(["", "▶ 보유 축소·전량 청산"])
    if not sell:
        lines.append("• 분류된 업종의 축소 기록 없음")
    for i,(sector,data) in enumerate(sell[:top_n],1):
        rows=data["sell"]
        exits=sum(r["action"]=="전량 청산" for _,r in rows)
        ordered=sorted(rows,key=lambda v:(-v[0],-abs(v[1].get("delta_shares") or 0)))[:2]
        lines.append(f"{i}. {sector} — {len(rows)}행 (청산 {exits}·축소 {len(rows)-exits})")
        lines.append("   "+ " · ".join(_short_share_move(r,display) for _,r in ordered))
    if len(sell)>top_n:
        lines.append(f"• 그 외 축소 업종 {len(sell)-top_n}개")

    mixed=sorted(((k,v) for k,v in classified.items() if v["buy"] and v["sell"]),
                 key=lambda kv:-(len(kv[1]["buy"])+len(kv[1]["sell"])))
    if mixed:
        lines.extend(["","▶ 동일 업종 내 양방향 변화"])
        for sector,v in mixed[:2]:
            lines.append(f"• {sector}: 확대 {len(v['buy'])}행 / 축소 {len(v['sell'])}행 — 금액 순매수 판정 안 함")

    lines.extend([
        "",
        f"• 업종 분류 {known_buy+known_sell}/{denominator}행 ({coverage:.0f}%)"
        f" · 미분류 확대 {len(misc['buy'])}행 / 축소 {len(misc['sell'])}행",
    ])
    if coverage<60 and denominator>0:
        lines.append("• 주의: 미분류가 많아 위 순위는 전체 포트폴리오 방향을 대표하지 못할 수 있습니다.")
    if opts["CALL"] or opts["PUT"]:
        lines.append(f"• 옵션 별도: 콜 {opts['CALL']}행 / 풋 {opts['PUT']}행 (보통주 제외)")
    if other:
        lines.append(f"• 수량·유형 불명 {other}행: 방향 산정 제외")
    lines.extend([
        "※ 순위는 분류된 비옵션 증권(보통주·ETF 등)의 변동행 수 기준이며, 실제 주문·자금이동 규모의 순위가 아닙니다.",
        "※ 일부 공시에서 신고 평가액과 주수×주가의 단위 불일치가 확인되어, 검증 전 달러·원화 금액은 표시하지 않습니다.",
        "※ 13F는 분기말 보유 현황이며 매매시점·매매단가·공매도·현금은 확인되지 않습니다.",
    ])
    return "\n".join(lines)

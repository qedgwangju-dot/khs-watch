#!/usr/bin/env python3
"""Ranking of *position changes* reported in SEC 13F, not executed trades.

Values are proportional quarter-end marks on changed common-share quantities.
Option rows are excluded because 13F underlying values are not paid premiums.
Do not calculate a bogus buy-minus-sell cash flow across quarterly marks.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _display_number(value):
    """Finite decimal for display only. All financial calculations stay raw."""
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("13F currency display requires a numeric value") from exc
    if not out.is_finite():
        raise ValueError("13F currency display requires a finite value")
    return out


def _human_round(value, base, digits=0):
    return (value / Decimal(base)).quantize(
        Decimal("1").scaleb(-digits), rounding=ROUND_HALF_UP)


def compact_usd(usd):
    """Readable Korean dollars: >=100m two-decimal 억; >=1m 10만 precision."""
    value = _display_number(usd)
    magnitude = abs(value)
    if magnitude >= 100_000_000:
        return f"{_human_round(value, 100_000_000, 2):,.2f}억달러"
    if magnitude >= 1_000_000:
        man_dollars = _human_round(value, 100_000) * 10
        if abs(man_dollars) >= 10_000:
            return f"{_human_round(value, 100_000_000, 2):,.2f}억달러"
        return f"{man_dollars:,.0f}만달러"
    if magnitude >= 100_000:
        return f"{_human_round(value, 10_000):,.0f}만달러"
    if magnitude >= 10_000:
        man = _human_round(value, 10_000, 1)
        return (f"{man:,.0f}만달러" if man == man.to_integral_value()
                else f"{man:,.1f}만달러")
    return f"{_human_round(value, 1):,.0f}달러"


def compact_krw(won):
    """Readable Korean won: >=1tn two-decimal 조; >=10억 integer 억."""
    value = _display_number(won)
    magnitude = abs(value)
    if magnitude >= 1_000_000_000_000:
        return f"약 {_human_round(value, 1_000_000_000_000, 2):,.2f}조원"
    if magnitude >= 1_000_000_000:
        eok = _human_round(value, 100_000_000)
        if abs(eok) >= 10_000:
            return f"약 {_human_round(value, 1_000_000_000_000, 2):,.2f}조원"
        return f"약 {eok:,.0f}억원"
    if magnitude >= 100_000_000:
        eok = _human_round(value, 100_000_000, 1)
        return (f"약 {eok:,.0f}억원" if eok == eok.to_integral_value()
                else f"약 {eok:,.1f}억원")
    if magnitude >= 10_000:
        return f"약 {_human_round(value, 10_000):,.0f}만원"
    return f"약 {_human_round(value, 1):,.0f}원"


# SEC has required whole-dollar 13F values since 2023-01-03. These exact
# Duquesne filings are independently reconciled at 1000x the submitted
# numbers: 2026-Q3 raw cover total 4,470,866 vs independently reconstructed
# 4,470,866,000 USD; 2026-Q2 raw about 5.21M vs 5.21B USD.
# Sources: SEC 13F primary_doc.xml; SEC 13F FAQ Q36; PortfolioSavvy,
# FilingExplorer and TradingJournl 2026-Q2/Q3 13F holdings.
# This is an explicitly identified reported-unit anomaly, NOT a claim
# that 13F generally uses thousand-dollar values.
VERIFIED_ANOMALOUS_SCALE = {
    ("Duquesne Family Office","0001536411-26-000011"): 1000,
    ("Duquesne Family Office","0001536411-26-000006"): 1000,
}


def verified_scale(label, filing):
    """Returns 1/1000 for audited filings, None if unit is unknown."""
    if filing is None:
        return None
    accession = (filing or {}).get("accession")
    if not accession:
        return None
    if (label, accession) in VERIFIED_ANOMALOUS_SCALE:
        return VERIFIED_ANOMALOUS_SCALE[(label, accession)]
    if label == "Duquesne Family Office":
        # This manager has submitted recurring nonstandard value units.
        # A future accession must be re-audited before USD amounts appear.
        return None
    return 1  # SEC's post-2023 actual-dollar unit (no arbitrary ×1000)


def verified_change_values(changes, label, filing, previous):
    """Scale 13F valuation columns ONLY for audited report accessions.

    Keeps the precise share changes and category classification untouched.
    Flags an unknown previous/current filing, so the renderer can suppress
    currency amounts while preserving share-count direction.
    """
    current_scale=verified_scale(label,filing)
    previous_scale=verified_scale(label,previous)
    out=[]
    for change in changes:
        x=dict(change)
        action=x.get("action")
        use_current=action in ("신규 매수","보유 확대")
        factor=current_scale if use_current else previous_scale
        x["valuation_verified"]=(factor is not None)
        x["valuation_scale"]=factor
        x["cur_value"]=float(x.get("cur_value") or 0) * (current_scale or 1)
        x["prev_value"]=float(x.get("prev_value") or 0) * (previous_scale or 1)
        out.append(x)
    return out



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


def build_sector_direction(changes, display, *, top_n=4, money=None):
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

    def _formatted_value(rows):
        if money is None:
            return None
        if not rows or not all(record.get("valuation_verified",True)
                               for _,record in rows):
            return "평가액 단위 확인 전"
        return money(sum(ref for ref,_ in rows))

    def _representative(rows):
        if not rows:
            return ""
        items=[]
        for reference,row in sorted(rows,key=lambda r:-r[0])[:2]:
            label=_short_share_move(row,display)
            if money is not None:
                if row.get("valuation_verified",True):
                    label+=f" · 변경분 {money(reference)}"
                else:
                    label+=" · 변경분 평가액 미검증"
            items.append(label)
        return " · ".join(items)

    def headline(changes, side):
        lines=[]
        for sector,values in changes[:2]:
            val=_formatted_value(values[side])
            lines.append(f"{sector}({len(values[side])}행"+(f", {val}" if val else "")+")")
        return ", ".join(lines) or "없음"

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
        val=_formatted_value(rows)
        lines.append(f"{i}. {sector} — {len(rows)}행 (신규 {newly}·확대 {len(rows)-newly})"+
                     (f" · 변경분 {val}" if val else ""))
        lines.append("   "+_representative(rows))
    if len(buy)>top_n:
        lines.append(f"• 그 외 확대 업종 {len(buy)-top_n}개")

    lines.extend(["", "▶ 보유 축소·전량 청산"])
    if not sell:
        lines.append("• 분류된 업종의 축소 기록 없음")
    for i,(sector,data) in enumerate(sell[:top_n],1):
        rows=data["sell"]
        exits=sum(r["action"]=="전량 청산" for _,r in rows)
        val=_formatted_value(rows)
        lines.append(f"{i}. {sector} — {len(rows)}행 (청산 {exits}·축소 {len(rows)-exits})"+
                     (f" · 변경분 {val}" if val else ""))
        lines.append("   "+_representative(rows))
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
        ("※ 검증된 13F 변경분 평가액을 반올림해 표시합니다. 원화는 반올림 전 달러×검증 환율로 계산. "
         "일부 듀케인 2026년 공시값은 독립 검증한 접수번호에 한해 ×1,000 보정하며 "
         "미검증 공시는 금액을 보류합니다." if money is not None else
         "※ 일부 공시에서 신고 평가액과 주수×주가의 단위 불일치가 확인되어, 검증 전 달러·원화 금액은 표시하지 않습니다."),
        "※ 13F는 분기말 보유 현황이며 매매시점·매매단가·공매도·현금은 확인되지 않습니다.",
    ])
    return "\n".join(lines)


# The source SEC information table is the discovery source for every newly
# filed manager. Never require a media headline or hand-entered ticker.
# The old sector-only report remains available for past reports/tests.
def build_automatic_13f_digest(changes, current_holdings, display, money,
                                *, report_scale=None, max_chars=3050):
    """Autonomously surfaces *all* noteworthy holdings changes from Q2 vs Q3.

    The algorithm scans every current/prior filing change, including unknown
    sectors; ranks by verified changed-share reference value when possible,
    and independently surfaces AI/space/chip additions or exits. It cannot
    identify actual fills, short selling, or confidentially omitted positions.
    Options are counted but never mixed into common-share changes.
    """
    if not isinstance(changes,list) or not isinstance(current_holdings,dict):
        raise ValueError("13F automatic digest needs complete position changes and current holdings")
    nonoptions=[x for x in changes if str(x.get("putcall") or "").upper() not in ("PUT","CALL")]
    options=[x for x in changes if str(x.get("putcall") or "").upper() in ("PUT","CALL")]
    new=[x for x in nonoptions if x.get("action")=="신규 매수"]
    ended=[x for x in nonoptions if x.get("action")=="전량 청산"]
    up=[x for x in nonoptions if x.get("action")=="보유 확대"]
    down=[x for x in nonoptions if x.get("action")=="보유 축소"]
    unknown_sector=sum(x.get("sector") in ("기타","업종 미확인",None,"") for x in nonoptions)
    category=("AI","우주","반도체","메모리","데이터센터","기업·응용",
              "디지털 광고","자동화","게임·3D","디지털자산")
    def tech(row):
        return any(term in str(row.get("sector") or "") for term in category)
    def reference(row):
        side,value=changed_share_reference_value(row)
        return float(value) if side and row.get("valuation_verified",False) else None
    def rank(rows):
        return sorted(rows,key=lambda row:(reference(row) is not None,
                      reference(row) or 0,abs(float(row.get("delta_shares") or 0))),
                      reverse=True)
    def label(row):
        text=str(display(row))
        if len(text)>47:
            text=text[:45]+"…"
        return text
    def currency(row):
        value=reference(row)
        if value is None or money is None:
            return " · 금액 미검증"
        return " · "+money(value)
    def describe(row):
        action=row.get("action")
        n=abs(int(round(float(row.get("delta_shares") or 0))))
        if action=="신규 매수":
            change=f"신규 {n:,}주"
        elif action=="전량 청산":
            change=f"신고상 종료 {n:,}주"
        else:
            old=float(row.get("shares") or 0)-float(row.get("delta_shares") or 0)
            pct=(100*float(row["delta_shares"])/old) if old>0 else None
            change=(f"{float(row['delta_shares'])/abs(float(row['delta_shares'])):+.0f}{n:,}주"
                    if pct is None else f"{pct:+.1f}% ({n:,}주)")
        return f"{label(row)} {change}{currency(row)}"
    def distinct(a,b,limit):
        used={id(x) for x in a}
        return [x for x in rank(b) if id(x) not in used][:limit]

    total_value=None
    top_holding=None
    if current_holdings and report_scale is not None:
        rows=list(current_holdings.values())
        total_value=sum(float(r.get("value") or 0) for r in rows)*report_scale
        shares=[r for r in rows if str(r.get("putcall") or "").upper() not in ("PUT","CALL")]
        if total_value>0 and shares:
            top_holding=max(shares,key=lambda x:float(x.get("value") or 0))
    def report(limits):
        n_large,n_themes,n_changed,n_sectors=limits
        primary_new=rank(new)[:n_large]
        extra_new=distinct(primary_new,(x for x in new if tech(x)),n_themes)
        primary_exit=rank(ended)[:n_large]
        extra_exit=distinct(primary_exit,(x for x in ended if tech(x)),n_themes)
        def big(rows):
            filt=[]
            for x in rows:
                old=float(x.get("shares") or 0)-float(x.get("delta_shares") or 0)
                if old<=0:
                    continue
                pct=abs(float(x["delta_shares"])/old*100)
                if pct>=40:
                    filt.append(x)
            return rank(filt)[:n_changed]
        big_up=big(up)
        big_down=big(down)
        lines=[
            f"■ 신규 편입 {len(new)}행 · 신고상 보유 종료 {len(ended)}행"
            f" · 확대 {len(up)}행 · 축소 {len(down)}행",
            "▶ 주요 신규 편입(평가액 기준)" if any(reference(x) is not None for x in new)
                else "▶ 주요 신규 편입(보유수량 기준)",
        ]
        lines += ["• "+describe(x) for x in primary_new] or ["• 없음"]
        if extra_new:
            lines.append("▶ 추가 확인: AI·반도체·우주 등 기술 분야 신규 편입")
            lines += ["• "+describe(x) for x in extra_new]
        lines.append("▶ 신고에서 사라진 주요 보유증권")
        lines += ["• "+describe(x) for x in primary_exit] or ["• 없음"]
        if extra_exit:
            lines.append("▶ 추가 확인: AI·반도체·우주 등 기술 분야 신고 종료")
            lines += ["• "+describe(x) for x in extra_exit]
        if big_up:
            lines.append("▶ 큰 폭으로 보유 확대(직전 보유수량 대비 40% 이상)")
            lines += ["• "+describe(x) for x in big_up]
        if big_down:
            lines.append("▶ 큰 폭으로 보유 축소(직전 보유수량 대비 40% 이상)")
            lines += ["• "+describe(x) for x in big_down]
        if top_holding is not None:
            amount=float(top_holding["value"])*report_scale
            percent=100*amount/total_value
            toprow=dict(top_holding)
            lines.append(f"■ 현재 최대 공개 비옵션 보유: {label(toprow)}"
                         f" {int(toprow.get('shares') or 0):,}주"
                         f" · 전체 13F 신고 평가액의 {percent:.1f}%"
                         f" · {money(amount) if money else '평가액 표시 안 함'}")
        if n_sectors:
            groups=defaultdict(lambda: {"new":0,"exit":0,"up":0,"down":0})
            for x in nonoptions:
                sector=x.get("sector") or "기타"
                action=x.get("action")
                field={"신규 매수":"new","전량 청산":"exit",
                       "보유 확대":"up","보유 축소":"down"}.get(action)
                if field:
                    groups[sector][field]+=1
            non_misc=[(k,v) for k,v in groups.items() if k not in ("기타","업종 미확인")]
            buy_group=sorted(non_misc,key=lambda a:-(a[1]["new"]+a[1]["up"]))[:n_sectors]
            sell_group=sorted(non_misc,key=lambda a:-(a[1]["exit"]+a[1]["down"]))[:n_sectors]
            fmt=lambda v,side:f"{v['new']+v['up']}행" if side=="buy" else f"{v['exit']+v['down']}행"
            lines.append("■ 업종별 보유변동 행 수: 확대 "+
                         (", ".join(f"{k} {fmt(v,'buy')}" for k,v in buy_group) or "없음")
                         +" / 축소 "+
                         (", ".join(f"{k} {fmt(v,'sell')}" for k,v in sell_group) or "없음"))
        lines.append(f"• 업종 미분류 {unknown_sector}/{len(nonoptions)}행 · 옵션 {len(options)}행 별도")
        lines.append("※ 13F는 분기말 공개 보유현황입니다. '신고상 종료'는 매도일·현금거래·비공개 보유의 확정 증거가 아닙니다.")
        lines.append("※ 변경분 금액은 확대 주수×이번 분기말 단가, 축소 주수×직전 분기말 단가의 참고 평가액입니다.")
        return "\n".join(lines)
    for limits in ((4,4,5,2),(3,3,4,2),(3,2,3,1),(2,2,2,1),(2,1,2,0)):
        summary=report(limits)
        if len(summary)<=max_chars:
            return summary
    raise ValueError("13F automatic report too long even in compact mode")

"""Read-only Telegram presentation for the verified US positioning snapshot.

Price direction, the level/change of weekly futures positions, and option volume
are separate observations. This module performs no collection, sending or I/O.
"""

from datetime import datetime
from html import escape
from math import isfinite

from us_positioning_horizons import verified_price_return, verified_position_change
from us_positioning_context import checked_path, checked_composition, checked_options, breadth_comparison, checked_returns
from us_positioning_amounts import checked_turnover, checked_reference, money_pair, notional
from us_positioning_fx import checked_fx

PRESENTATION_VERSION = "us-positioning-at-a-glance-20261015-v1"
BRIEF_MAX_CHARS = 2400


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
        return value
    return None


def date_value(period):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%A, %B %d, %Y"):
        try:
            return datetime.strptime(str(period), fmt).date()
        except ValueError:
            pass
    return None


def date_label(source):
    value = date_value((source or {}).get("period"))
    return value.isoformat() if value else "기준일 미확인"


def integer(value, signed=False):
    value = number(value)
    if value is None:
        return "미확인"
    return format(int(value), "+," if signed else ",")


def percent(value, digits=1, signed=False):
    value = number(value)
    if value is None:
        return "미확인"
    return format(value, ("+" if signed else "") + f".{digits}f") + "%"


def percentile(value):
    value = number(value)
    return f"{value:.0f}" if value is not None else "미확인"


def price_direction(sox):
    """Describe completed SOX returns only; never infer the whole US market."""
    metrics = (sox or {}).get("metrics", {})
    values = [number(metrics.get(f"d{days}_pct")) for days in (1, 3, 5)]
    d1, d3, d5 = values
    if metrics.get("final_close_confirmed") is not True or d1 is None:
        return "⚪", "가격 방향 확인 대기", "확인된 반도체 종가가 부족합니다."
    if d3 is None or d5 is None:
        word = "상승" if d1 > 0 else "하락" if d1 < 0 else "보합"
        return "⚪", f"당일 {word} · 추세 확인 대기", "3·5거래일 중 미확인 값이 있어 기간 전체 방향은 보류합니다."
    if all(value < 0 for value in values):
        return "🔴", "반도체 하락 우세", "SOX 1·3·5거래일 수익률이 모두 음수입니다."
    if all(value > 0 for value in values):
        return "🟢", "반도체 상승 우세", "SOX 1·3·5거래일 수익률이 모두 양수입니다."
    if d1 > 0 and d3 < 0 and d5 < 0:
        return "🟡", "반도체 당일 반등 · 추세 혼재", "당일은 올랐지만 3·5거래일 수익률은 아직 음수입니다."
    if d1 < 0 and d3 > 0 and d5 > 0:
        return "🟡", "반도체 당일 하락 · 추세 혼재", "당일은 내렸지만 3·5거래일 수익률은 아직 양수입니다."
    if all(value == 0 for value in values):
        return "⚪", "반도체 보합", "SOX 1·3·5거래일 수익률이 모두 0입니다."
    return "🟡", "반도체 기간별 방향 혼재", "SOX 1·3·5거래일 방향이 일치하지 않습니다."


def horizon_overview(sox):
    short_icon, short_title, _ = price_direction(sox)
    metrics = (sox or {}).get("metrics", {})
    windows = metrics.get("month_windows", {})
    end = date_value((sox or {}).get("period"))
    if end is None or metrics.get("final_close_confirmed") is not True or number(metrics.get("d1_pct")) is None or number(metrics.get("value")) is None:
        return "⚪", "반도체 가격 방향 확인 대기", "확인된 최신 종가·기준일이 부족해 기간 종합을 보류합니다."
    one, three = [verified_price_return(windows.get(key), end, metrics.get("value")) for key in ("1m", "3m")]
    if one is None or three is None:
        return "⚪", "반도체 중기 방향 확인 대기", f"단기는 {short_title.removeprefix('반도체 ')}. 1·3개월 중 미확인 값이 있어 기간 종합은 보류합니다."
    if short_icon == "🔴" and one < 0 and three < 0:
        return "🔴", "반도체 단기·1개월·3개월 모두 하락", "여러 기간의 가격 수익률이 같은 하락 방향입니다."
    if short_icon == "🟢" and one > 0 and three > 0:
        return "🟢", "반도체 단기·1개월·3개월 모두 상승", "여러 기간의 가격 수익률이 같은 상승 방향입니다."
    if short_icon == "🔴" and one > 0 and three < 0:
        return "🟡", "반도체 혼재 · 1개월 전 대비 상승, 단기·3개월 하락", "최근 며칠의 약세와 최근 몇 달의 흐름을 구분합니다."
    if short_icon == "🔴" and one < 0 and three > 0:
        return "🟡", "반도체 혼재 · 3개월 전 대비 상승, 단기·1개월 하락", "3개월 수익률은 양수지만 최근 1개월과 단기는 하락입니다."
    if short_icon == "🔴" and one > 0 and three > 0:
        return "🟡", "반도체 1·3개월 전 대비 상승 속 단기 하락", "최근 하락만으로 1·3개월 방향까지 하락으로 표시하지 않습니다."
    if short_icon in ("🟢", "🟡") and one < 0 and three < 0 and number(metrics.get("d1_pct")) is not None and metrics["d1_pct"] > 0:
        return "🟡", "반도체 1·3개월 전 대비 하락 속 단기 반등", "당일 상승만으로 1·3개월의 하락 방향이 바뀌었다고 보지 않습니다."
    if short_title == "반도체 보합" and one == three == 0:
        return "⚪", "반도체 단기·1개월·3개월 보합", "세 비교 기간에서 방향성 변화가 없습니다."
    return "🟡", "반도체 기간별 방향 혼재", "단기·1개월·3개월 수익률의 방향이 일치하지 않습니다."


def position_level(net):
    net = number(net)
    if net is None:
        return "순포지션 미확인"
    if net == 0:
        return "롱·숏 균형(순포지션 0)"
    return f"{'순롱' if net > 0 else '순숏'} {abs(int(net)):,}계약"


def position_change(net, change):
    """Keep current level separate from weekly change, including sign changes."""
    net, change = number(net), number(change)
    if net is None or change is None:
        return "주간 변화 미확인"
    previous = net - change
    if change == 0:
        return "주간 변화 없음"
    if previous < 0 < net:
        return "순숏 → 순롱 전환"
    if previous > 0 > net:
        return "순롱 → 순숏 전환"
    if net == 0:
        return "순숏 해소·롱숏 균형" if previous < 0 else "순롱 해소·롱숏 균형"
    if previous == 0:
        return "순롱 형성" if net > 0 else "순숏 형성"
    if net > 0:
        return "순롱 확대" if change > 0 else "순롱 축소"
    return "순숏 축소" if change > 0 else "순숏 확대"


def position_movement(net, change):
    """Express the change in the net holding's size, including zero crossings."""
    net, change = number(net), number(change)
    if net is None or change is None or int(net) != net or int(change) != change:
        return "순포지션 변화 확인 대기"
    previous = net - change
    if change == 0:
        return "롱·숏 균형 유지" if net == 0 else f"{'순롱' if net > 0 else '순숏'} 규모 변화 없음"
    if previous * net < 0:
        return f"{position_level(previous)} → {position_level(net)} 전환"
    if net == 0:
        return f"{position_level(previous)} 해소 · 롱·숏 균형"
    if previous == 0:
        return f"{position_level(net)} 형성"
    side = "순롱" if net > 0 else "순숏"
    direction = "확대" if abs(net) > abs(previous) else "축소"
    return f"{side} {integer(abs(change))}계약 {direction}"


def holding_change(label, change):
    change = number(change)
    if change is None or int(change) != change:
        return f"{label} 보유 변화 미확인"
    if change == 0:
        return f"{label} 보유 변화 없음"
    return f"{label} {integer(abs(change))} {'증가' if change > 0 else '감소'}"


def position_line(label, net, change):
    value = number(change)
    weekly = (f"주간 순포지션 변화 {integer(value, signed=True)}계약 ({position_movement(net, value)})"
              if value is not None and int(value) == value else "주간 순포지션 변화 확인 대기")
    return (
        f"• {escape(label)}: <b>{position_level(net)}</b>"
        f" | {weekly}"
    )


def volume_description(calls, puts, pc_ratio):
    calls, puts, pc_ratio = number(calls), number(puts), number(pc_ratio)
    if calls is not None and puts is not None and calls >= 0 and puts >= 0:
        if calls == puts == 0:
            return "콜·풋 거래량 모두 0 · 비율 계산 불가"
        if calls == 0:
            return "콜 0 · 풋만 거래됨"
        if puts == 0:
            return "풋 0 · 콜만 거래됨"
        ratio = puts / calls
        if 0.90 <= ratio <= 1.10:
            return "콜·풋 거래량 비슷"
        if calls > puts:
            return f"콜 거래량이 풋의 {calls / puts:.2f}배"
        return f"풋 거래량이 콜의 {puts / calls:.2f}배"
    if pc_ratio is None or pc_ratio < 0:
        return "거래량·비율 미확인"
    if 0.90 <= pc_ratio <= 1.10:
        return "콜·풋 거래량 비슷(공표 비율 기준)"
    return "콜 거래량 우위(공표 비율 기준)" if pc_ratio < 0.90 else "풋 거래량 우위(공표 비율 기준)"


def _lag_line(cftc, sox):
    report, price = date_value((cftc or {}).get("period")), date_value((sox or {}).get("period"))
    if report is None or price is None:
        return "• CFTC와 가격의 기준일 차이 미확인 · 당일 포지션으로 해석하지 않음"
    lag = (price - report).days
    if lag > 0:
        return f"• 선물은 가격보다 <b>{lag}일 이전</b> 자료 · 현재 가격과 같은 시점의 포지션은 미확인"
    if lag < 0:
        return f"• 선물과 가격의 기준일이 {-lag}일 다름 · 같은 시점의 포지션으로 해석하지 않음"
    return "• CFTC는 같은 기준일의 주간 관측 · 당일 매매 흐름을 직접 나타내지는 않음"



def path_lines(path, end, label, returns=True):
    path = path or {}
    expected = {"SOX":"SOX", "나스닥100":"NDX", "S&P500":"SPX"}.get(label)
    actual = checked_path(path, end, expected) if end else None
    summary = checked_returns(path.get("returns"), end, expected) if end else None
    lines = []
    if returns:
        if summary is None:
            lines.append(f"• {label} 기간 수익률: <b>확인 대기</b> · 현재·기준 종가 누락 또는 불일치")
        else:
            lines.append(f"<b>{label}</b> · {summary['end_date']} 종가 {summary['close']:,.2f}")
            for keys,names in ((("1d","3d","5d"),("1거래일","3거래일","5거래일")),(("1m","3m"),("1개월 전 대비","3개월 전 대비"))):
                bits=[]
                for key,name in zip(keys,names):
                    w=summary["windows"][key]
                    bits.append(f"{name} {percent(w['return_pct'],2,True)} ({w['base_date']} → {w['end_date']})" if w["status"] == "verified" else f"{name} 확인 대기")
                lines.append("• " + " | ".join(bits))
    if actual is None:
        reason = path.get("reason", "거래일·제공처·이력 검산 미완료")
        if len(reason) > 75:
            reason = "거래일·제공처·이력 검산 미완료"
        lines.append(f"• {label} 20·60일 추세·63일 고점 대비: <b>확인 대기</b> · {escape(reason)}")
        return lines
    v = actual["values"]
    position = lambda n: "위" if v["close"] > v[f"ma{n}"] else "아래" if v["close"] < v[f"ma{n}"] else "같음"
    lines.append(f"• {label} 현재 추세(규칙): <b>{v['trend']}</b> | 종가가 20일선 {position(20)}·60일선 {position(60)}")
    lines.append("• " + " / ".join(f"{n}일 평균 {v[f'ma{n}']:,.2f} (5거래일 전 평균 대비 {percent(v[f'ma{n}_change5_pct'],2,True)})" for n in (20,60)))
    lines.append(f"• 최근 63거래일 종가고점 {v['peak63_close']:,.2f}({v['peak63_date']}) 대비 {percent(v['drawdown63_pct'],2,True)}")
    return lines


def composition_description(parts):
    l, s = parts["long_change"], parts["short_change"]
    if l == s == 0:
        return "롱·숏 보유 변화 없음"
    influence = ", 롱 보유 변화의 영향이 더 큼" if abs(l) > abs(s) else ", 숏 보유 변화의 영향이 더 큼" if abs(s) > abs(l) else ", 기여 크기는 같음"
    if l > 0 and s < 0:
        return "롱 증가·숏 감소가 함께 순포지션을 높임" + influence
    if l < 0 and s > 0:
        return "롱 감소·숏 증가가 함께 순포지션을 낮춤" + influence
    label = lambda value: "증가" if value > 0 else "감소" if value < 0 else "변화 없음"
    result = f"롱 {label(l)}·숏 {label(s)}"
    if abs(l) == abs(s):
        return result + ", 두 변화의 순효과가 상쇄"
    return result + (", 롱 보유 변화의 영향이 더 큼" if abs(l) > abs(s) else ", 숏 보유 변화의 영향이 더 큼")


def price_level_line(label, close, previous=None, change_pct=None):
    current, prior = number(close), number(previous)
    if current is None or current <= 0:
        return f"• {label} 종가: 확인 대기"
    line = f"• {label} <b>{current:,.2f}pt</b>"
    if prior is not None and prior > 0 and number(change_pct) is not None:
        if abs((current/prior-1)*100-change_pct) < 0.00001:
            line += f" · 전일 {current-prior:+,.2f}pt ({percent(change_pct,2,True)})"
    return line


def turnover_lines(amounts, end, detail=False):
    amounts = amounts or {}
    value = checked_turnover(amounts.get("turnover"),end) if end else None
    lines = [f"<b>{'⑤' if detail else '②'} 실제 거래대금 | 미국 주식시장 전체</b>"]
    if value is None:
        return lines+["• 실제 거래대금: 확인 대기 · 공식 날짜·거래소·체결합계 미확인"]
    fx = amounts.get("fx",{})
    money = lambda amount,signed=False: money_pair(amount,fx,end,signed)
    lines.append(f"• {value['end_date']} 당일 <b>{money(value['daily_usd'])}</b>")
    lines.append(f"• 전일 대비 {money(value['change_usd'],True)} ({float(value['change_pct']):+.2f}%)")
    averages=[]
    for key,label in (("5d","5거래일"),("1m","1개월"),("3m","3개월")):
        w=value["windows"][key]
        averages.append(f"{label} {money(w['average_daily_usd'])}")
        if detail:
            lines.append(f"• {label} ({w['start_date']}~{w['end_date']}, {w['sessions']}거래일): 합계 {money(w['total_usd'])} / 일평균 {money(w['average_daily_usd'])}")
    if not detail:
        lines.append("• 일평균: " + " / ".join(averages))
    rate=checked_fx(fx,end)
    lines.append((f"※ 원화 환산: 1달러={float(rate['krw_per_usd']):,.2f}원 · 한국은행 ECOS {rate['date']}. 과거 금액도 이 환율로 환산."
                  if rate else "※ 해당일 ECOS 매매기준율 미확인 · 원화 환산 보류"))
    lines.append("※ Cboe 전체 거래소·TRF의 체결가×주식 수 합계. ETF 등 포함. 지수별 거래대금·순유입액 아님.")
    if detail:
        lines += [f"• 직전 거래일 {value['previous_date']}: {money(value['previous_daily_usd'])}",
                  f'<a href="{value["source_url"]}">Cboe 거래대금 정의·공식 CSV</a> · <a href="https://ecos.bok.or.kr/">한국은행 ECOS</a>']
    return lines


def reference_amount_line(contracts, amounts, report):
    if number(contracts) is None:
        return None
    value=notional(abs(contracts),amounts.get("nq_reference"),report) if report else None
    return money_pair(value,amounts.get("nq_fx"),report) if value is not None else None


def reference_amount_detail(cftc, amounts, report):
    ref=checked_reference(amounts.get("nq_reference"),report) if report else None
    if ref is None:
        date=report.isoformat() if report else "기준일 미확인"
        return [f"• NQ 참고 명목금액: 환산 보류 · {date} NDX 종가 누락·제공처 불일치"]
    nq=(cftc or {}).get("nq_mini",{})
    lines=[f"<b>NQ 기준일 지수 종가 환산 참고 명목규모 | {ref['date']}</b>"]
    for key,label in (("leveraged_long","롱"),("leveraged_short","숏"),("leveraged_net","순포지션")):
        if number(nq.get(key)) is not None:
            amount=reference_amount_line(nq[key],amounts,report)
            lines.append(f"• {label} {integer(nq[key])}계약 · 참고규모 {amount or '확인 대기'}")
    multiplier=money_pair(20,amounts.get("nq_fx"),report)
    lines.append(f"• {ref['date']} 현물 NDX 종가 {ref['primary_close']:,.2f}pt × 계약당 {multiplier}/pt × 계약 수")
    rate=checked_fx(amounts.get("nq_fx"),report)
    lines.append(f"• 환산: 한국은행 ECOS {rate['date']}, 1달러={float(rate['krw_per_usd']):,.2f}원" if rate else "• 해당일 ECOS 미확인 · 원화 환산 보류")
    lines.append("※ 만기별 실제 선물 정산가 평가액·거래대금·증거금·자금 유입액이 아님. 계약 수 변화 환산도 같은 보고일 가격·환율을 사용.")
    return lines


def composition_line(window, actor, label, end):
    parts = checked_composition(window, actor, end) if end else None
    if parts is None:
        return f"  {label}: 롱·숏 변화 구성 확인 대기"
    return (f"  {label}: 롱 {integer(parts['long_change'],True)} / 숏 {integer(parts['short_change'],True)}"
            f" / 순포지션 변화 {integer(parts['net_change'],True)}계약 · {position_movement(parts['end_net'],parts['net_change'])} · {composition_description(parts)}")


def breadth_lines(value, end):
    comparison = breadth_comparison(value.get("series",{}), end) if end else {}
    if comparison.get("status") != "verified" or comparison != value.get("comparison"):
        return ["<b>시장 확산 참고</b>", "• 동일가중·시가총액가중 비교: 확인 대기 · 같은 날짜의 두 ETF 조정종가·원종가 대조 필요"]
    lines = ["<b>시장 확산 참고 | 동일가중 RSP 대 시가총액가중 SPY</b>"]
    for key,name in (("5d","5거래일"),("1m","1개월"),("3m","3개월")):
        w = comparison["windows"][key]
        lines.append(f"• {name}: RSP {percent(w['rsp_return_pct'],2,True)} / SPY {percent(w['spy_return_pct'],2,True)} → 차이 {w['difference_pp']:+.2f}%p ({w['base_date']} → {w['end_date']})")
    lines.append("• Yahoo 배당·분할 조정종가 기준 ETF 상대수익률, 원종가는 Nasdaq 대조. 조정값은 단일 제공처 기준이며 비용·추적오차 포함")
    lines.append("• 동일가중 상대우위도 두 ETF가 함께 하락할 수 있음. 상승 종목 비율·시장 전체 상승 확인값은 아님")
    return lines


def option_history_lines(values, current, end):
    lines = ["<b>옵션의 평소 대비 위치</b>"]
    for key,label in (("1m","1개월"),("3m","3개월")):
        value = checked_options(values.get(key),current,end) if end else None
        if value is None:
            w = values.get(key,{})
            missing = w.get("missing_dates",[])
            lines.append(f"• 과거 {label}: 확인 대기 · 공식 일별 자료 누락 {len(missing)}일" if missing else f"• 과거 {label}: 확인 대기 · 기준일·거래량·표본 검산 미완료")
            continue
        bits = []
        for kind,name in (("equity","주식"),("index","지수"),("total","전체")):
            m = value["values"][kind]
            bits.append(f"{name} 중앙값 {m['median_pc']:.3f}·현재값 이하 {m['current_le_percent']:.1f}%")
        lines.append(f"• {label} ({value['start_date']}~현재일 직전, {value['expected_sessions']}거래일): " + " / ".join(bits))
    return lines


def render_detail_alert(cftc, cboe, sox, updates, results, errors=(), event_label="신규 변화", context=None):
    """Preserve all verified values and caveats in the downloadable detail file."""
    icon, title, reason = horizon_overview(sox)
    context = context or {}
    end = date_value((sox or {}).get("period"))
    broad = [checked_returns(context.get("indices", {}).get(k, {}).get("returns"), end, k) for k in ("NDX", "SPX")] if end else []
    if broad and all(broad) and all(x["windows"]["5d"]["status"] == "verified" for x in broad):
        five = [x["windows"]["5d"]["return_pct"] for x in broad]
        icon = "🔴" if all(v < 0 for v in five) else "🟢" if all(v > 0 for v in five) else "🟡"
        title = "미국 주요지수 최근 5거래일 " + ("하락" if all(v < 0 for v in five) else "상승" if all(v > 0 for v in five) else "방향 혼재")
        reason = "나스닥100·S&P500의 기간 수익률 비교입니다. 현재 추세는 아래 20·60거래일 기준으로 따로 표시합니다."
    else:
        reason += " 미국 주요지수 종합은 자료 확인 대기입니다."
    body = [
        f"🇺🇸 <b>[미국 포지셔닝 | {escape(event_label)}]</b>",
        "",
        f"{icon} <b>기간 종합: {title}</b>",
        reason,
    ]
    cm = (cftc or {}).get("metrics", {})
    if cm and number(cm.get("lev_net")) is not None and cm["lev_net"] < 0 and number(cm.get("lev_net_wow")) is not None and cm["lev_net_wow"] > 0:
        body.append("선물의 순숏은 줄었지만 여전히 순숏입니다. 이 주간 변화만으로 가격 반등을 판단하지 않습니다.")
    body += ["", f"<b>① 기간 수익률과 현재 추세 | {date_label(sox)} 마감</b>"]
    sm = (sox or {}).get("metrics", {})
    if number(sm.get("value")) is not None:
        body.append(f"• SOX {sm['value']:,.2f} | 전일 {sm.get('previous_close', 0):,.2f}" if number(sm.get("previous_close")) is not None else f"• SOX {sm['value']:,.2f} | 전일 종가 미확인")
    else:
        body.append("• SOX 종가 미확인")
    body.append("• " + " | ".join(f"{days}거래일 {percent(sm.get(f'd{days}_pct'), 2, signed=True)}" for days in (1, 3, 5)))
    body.append(f"• 단기 판정: {price_direction(sox)[1].removeprefix('반도체 ')}")
    verified_months = 0
    for key, label in (("1m", "1개월"), ("3m", "3개월")):
        window = sm.get("month_windows", {}).get(key, {})
        change = verified_price_return(window, date_value((sox or {}).get("period")), sm.get("value")) if date_value((sox or {}).get("period")) else None
        if change is None:
            body.append(f"• {label}: <b>확인 대기</b> · 같은 날짜의 Nasdaq·Yahoo 기준 종가 미확인 또는 불일치")
        else:
            verified_months += 1
            direction = "상승" if change > 0 else "하락" if change < 0 else "보합"
            body.append(f"• {label} 전 대비: <b>{percent(change, 2, signed=True)} · {direction}</b> ({window['base_date']} → {window['end_date']})")
    body.append("• 월간은 달력 1·3개월 전 기준일 이하 최근 종가와 비교한 수익률이며 현재 추세와 별개")
    body.append("• 1·3개월의 현재·기준 종가를 Nasdaq·Yahoo로 대조" if verified_months == 2 else "• 두 제공처에서 확인된 월간만 표시. 미확인·불일치 기간의 계산과 종합 판정은 보류")

    body.extend(path_lines(sm.get("price_path"), end, "SOX", returns=False))
    for symbol, label in (("NDX", "나스닥100"), ("SPX", "S&P500")):
        body.extend(path_lines(context.get("indices", {}).get(symbol), end, label))
    body.append("• 추세 규칙: 종가·20일·60일선의 순서와 두 이동평균의 최근 5거래일 방향이 일치할 때만 상승/하락, 그 밖에는 혼재")
    body.extend(breadth_lines(context.get("breadth", {}), end))

    body += ["", f"<b>② 선물 보유 방향 | {date_label(cftc)} 주간</b>", "나스닥100 통합 · 선물만"]
    body.append(position_line("기관", cm.get("asset_net"), cm.get("asset_net_wow")))
    body.append(position_line("헤지펀드성", cm.get("lev_net"), cm.get("lev_net_wow")))
    body.append(_lag_line(cftc, sox))
    body.append("• 순롱=롱이 더 많음 / 순숏=숏이 더 많음 · 투자자 전체 자산이나 현물 매수·매도액은 아님")
    position_windows = (cftc or {}).get("history_3y", {}).get("month_windows", {})
    body.append("<b>NQ E-mini · 롱·숏 보유 변화 구성 | 단위: 계약</b>")
    weekly = (cftc or {}).get("history_3y", {}).get("week_window", {})
    if weekly.get("base_date"):
        body.append(f"• 직전 주간 관측 ({weekly['base_date']} → {weekly['end_date']}):")
    else:
        body.append("• 직전 주간 관측: 확인 대기")
    for actor, label in (("asset_manager", "기관"), ("leveraged_funds", "헤지펀드성")):
        body.append(composition_line(weekly, actor, label, date_value((cftc or {}).get("period"))))
    for key, label in (("1m", "1개월"), ("3m", "3개월")):
        window = position_windows.get(key, {})
        bits = []
        for actor, actor_label in (("asset_manager", "기관"), ("leveraged_funds", "헤지펀드성")):
            change = verified_position_change(window, actor, date_value((cftc or {}).get("period"))) if date_value((cftc or {}).get("period")) else None
            if change is None:
                bits.append(f"{actor_label} 확인 대기")
            else:
                parts = checked_composition(window, actor, date_value((cftc or {}).get("period")))
                if parts is None:
                    bits.append(f"{actor_label} 변화 구성 확인 대기")
                else:
                    net = parts["end_net"]
                    bits.append(f"{actor_label} 롱 {integer(parts['long_change'], signed=True)} / 숏 {integer(parts['short_change'], signed=True)} / 순포지션 변화 {integer(change, signed=True)}계약({position_movement(net, change)})")
        interval = f" ({window['base_date']} → {window['end_date']})" if window.get("base_date") else ""
        body.append(f"• {label}{interval}: " + " / ".join(bits))
        parts = checked_composition(window, "leveraged_funds", date_value((cftc or {}).get("period")))
        if parts is not None:
            body.append("  헤지펀드성 구성: " + composition_description(parts))
    body.append("• 순포지션 변화=롱 보유 변화−숏 보유 변화. 달력 기준일 이하 최근 주간 관측 사용. 통합 수치와 범위가 다름")

    body.append("• 집계된 보유 수량의 변화이며 개별 거래자의 신규 주문·청산·헤지 목적은 미확인")
    body.extend(reference_amount_detail(cftc,context.get("amounts",{}),date_value((cftc or {}).get("period"))))

    body += ["", f"<b>③ 옵션 거래량 | {date_label(cboe)} 일별 참고</b>"]
    om = (cboe or {}).get("metrics", {})
    for key, label in (("equity", "주식"), ("index", "지수"), ("total", "전체")):
        calls, puts, ratio = [om.get(key + suffix) for suffix in ("_calls", "_puts", "_pc_ratio")]
        ratio_text = f"{ratio:.2f}" if number(ratio) is not None else "미확인"
        body.append(f"• {label}: <b>{volume_description(calls, puts, ratio)}</b> | P/C {ratio_text}")
    body.extend(option_history_lines(context.get("options", {}), om, date_value((cboe or {}).get("period"))))
    body.append("• 과거 비교는 현재일을 제외한 달력 1·3개월의 Cboe 일별 마감 통계. 이하 비중은 동률 포함이며 높을수록 현재 풋/콜 비율이 과거보다 높은 편")
    body.append("• P/C=풋÷콜 거래량. 매수·매도는 구분되지 않아 옵션만으로 상승·하락 방향을 판정하지 않음")
    body.append("• 옵션 프리미엄 거래대금: 현재 Cboe 무료 집계 원자료 미제공 · 계약 수로 금액을 추정하지 않음")

    nq = (cftc or {}).get("nq_mini") or {}
    hist = (cftc or {}).get("history_3y") or {}
    if nq:
        body += ["", "<b>④ 숏 규모 상세 | NQ E-mini 선물만</b>"]
        body.append(position_line("헤지펀드성", nq.get("leveraged_net"), nq.get("leveraged_net_wow")))
        body.append(f"• 숏/OI {percent(nq.get('short_share_oi_pct'))} | OI 주간 {integer(nq.get('open_interest_wow'), signed=True)}계약")
        if number(hist.get("net_short_percentile_3y")) is not None:
            body.append(f"• 3년 백분위: 순숏 {percentile(hist.get('net_short_percentile_3y'))} / 총숏 {percentile(hist.get('gross_short_percentile_3y'))} / 숏÷OI {percentile(hist.get('short_share_oi_percentile_3y'))}")
            body.append(f"• 3년 최대치 대비 축소: 순숏 {percent(hist.get('net_short_unwind_from_peak_pct'))} / 총숏 {percent(hist.get('gross_short_unwind_from_peak_pct'))}")
            body.append(f"• 총숏 계약 변화: 1주 {integer(hist.get('leveraged_short_1w_change'), signed=True)} / 4주 {integer(hist.get('leveraged_short_4w_change'), signed=True)}")
        else:
            body.append("• 3년 백분위: 공식 자료 확인 대기")
        if hist.get("ten_year_complete") and number(hist.get("net_short_percentile_10y")) is not None:
            body.append(f"• 10년 백분위: 순숏 {percentile(hist.get('net_short_percentile_10y'))} / 총숏 {percentile(hist.get('gross_short_percentile_10y'))} / 숏÷OI {percentile(hist.get('short_share_oi_percentile_10y'))}")
            body.append(f"• 이번 주 총숏 변화 {integer(hist.get('gross_short_weekly_change_10y'), signed=True)}계약(10년 {percentile(hist.get('gross_short_weekly_build_percentile_10y'))}백분위)")
            body.append(f"• 이번 주 순숏 변화 {integer(hist.get('net_short_weekly_build_10y'), signed=True)}계약(10년 {percentile(hist.get('net_short_weekly_build_percentile_10y'))}백분위)")
            body.append(f"• 10년 최대 주간 총숏 증가 {integer(hist.get('max_gross_short_weekly_build_10y'), signed=True)}계약({escape(str(hist.get('max_gross_short_weekly_build_date_10y') or '날짜 미확인'))})")
        else:
            body.append("• 10년 백분위·최대 기록: 공식 자료 확인 대기")
        body += [
            "• 백분위가 높을수록 해당 숏 지표가 과거보다 큼. 낮은 백분위가 상승을 뜻하지는 않음",
            "• 통합과 E-mini는 집계 범위가 달라 합산하지 않음. 순숏·총숏·숏/OI는 서로 다른 지표이며 Goldman/BofA PB 모델과도 모집단이 다름",
        ]

    body += [""] + turnover_lines(context.get("amounts",{}),end,detail=True)
    body += ["", "<b>원수치 · 단위: 계약</b>"]
    for prefix, label in (("asset", "통합 기관"), ("lev", "통합 헤지펀드성")):
        body.append(f"• {label}: 롱 {integer(cm.get(prefix + '_long'))} / 숏 {integer(cm.get(prefix + '_short'))}")
    if nq:
        body.append(f"• E-mini 헤지펀드성: 롱 {integer(nq.get('leveraged_long'))} / 숏 {integer(nq.get('leveraged_short'))}")
    for key, label in (("equity", "주식옵션"), ("index", "지수옵션"), ("total", "전체옵션")):
        calls, puts = om.get(key + "_calls"), om.get(key + "_puts")
        share = calls / (calls + puts) * 100 if number(calls) is not None and number(puts) is not None and calls + puts > 0 else None
        body.append(f"• {label}: 콜 {integer(calls)} / 풋 {integer(puts)} | 콜 비중 {percent(share)}")

    body += ["", "<b>이번에 바뀐 자료</b>"]
    for source in (updates if updates else results):
        body.append(f"• {escape(source['source'])} | {date_label(source)} | <a href=\"{escape(source['url'], quote=True)}\">원천</a>")
    body.append("• SOX는 반도체, NDX는 나스닥100, S&P500은 미국 대형주 범위. 선물·옵션과 모집단이 다름\n• 가격: Nasdaq 또는 Cboe 종가·Yahoo 대조. 옵션: Cboe 일별 마감 거래량")
    if errors:
        body += ["", "<b>확인 대기</b>"]
        body.extend("• " + escape(error.split(":", 1)[0]) + " 최신값 자동 재확인 중" for error in errors)
    return "\n".join(body) + "\n"


def _brief_path(path, end, symbol, label):
    actual = checked_path(path or {}, end, symbol) if end else None
    if actual is None:
        reason = (path or {}).get("reason", "이력·제공처 검산 미완료")
        if len(reason) > 60:
            reason = "이력·제공처 검산 미완료"
        return f"• {label} 추세 확인 대기 · {escape(reason)}"
    v = actual["values"]
    location = lambda n: "위" if v["close"] > v[f"ma{n}"] else "아래" if v["close"] < v[f"ma{n}"] else "같음"
    return (f"• {label} 추세 <b>{v['trend']}</b>: 20일선 {location(20)}·60일선 {location(60)}"
            f" | 63거래일 종가고점 대비 {percent(v['drawdown63_pct'],2,True)}")


def render_detail_document(*args, **kwargs):
    analysis = render_detail_alert(*args, **kwargs)
    return ('<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>미국 포지셔닝 상세 수치와 출처</title></head>'
            '<body style="font-family:system-ui,sans-serif;line-height:1.65;'
            'max-width:900px;margin:24px auto;padding:0 20px">'
            '<main style="white-space:pre-wrap">' + analysis + '</main></body></html>\n')


def _at_a_glance(cftc, cboe, sox, context):
    """Summarize the same verified observations used by the sections below."""
    end = date_value((sox or {}).get("period"))
    sm = (sox or {}).get("metrics", {})
    daily = [percent(sm.get("d1_pct"), 2, True) if sm.get("final_close_confirmed") is True else "확인 대기"]
    for symbol in ("NDX", "SPX"):
        value = checked_returns(context.get("indices", {}).get(symbol, {}).get("returns"), end, symbol) if end else None
        window = value["windows"].get("1d", {}) if value else {}
        daily.append(percent(window.get("return_pct"), 2, True) if window.get("status") == "verified" else "확인 대기")
    lines = [f"• 가격({date_label(sox)}·전일): " + " / ".join(f"{name} {value}" for name, value in zip(("SOX", "나스닥100", "S&P500"), daily))]

    amounts = context.get("amounts", {})
    turnover = checked_turnover(amounts.get("turnover"), end) if end else None
    lines.append(f"• 실제 거래대금: {money_pair(turnover['daily_usd'], amounts.get('fx', {}), end)} · 전일 {float(turnover['change_pct']):+.2f}%"
                 if turnover else "• 실제 거래대금: 확인 대기")

    report = date_value((cftc or {}).get("period"))
    cm = (cftc or {}).get("metrics", {})
    lines.append(f"• 통합 선물({date_label(cftc)}): 기관 {position_level(cm.get('asset_net'))} / 헤지펀드성 {position_level(cm.get('lev_net'))}")
    window = (cftc or {}).get("history_3y", {}).get("week_window")
    parts = checked_composition(window, "leveraged_funds", report) if report else None
    if parts:
        base = date_value(window.get("base_date"))
        comparison = "1주 전 대비" if base and (report - base).days == 7 else f"직전 관측({window['base_date']}) 대비"
        lines.append(f"• NQ E-mini: {position_level(parts['end_net'])} · {comparison} {position_movement(parts['end_net'], parts['net_change'])}")
    else:
        lines.append("• NQ E-mini: 현재·주간 변화 확인 대기")

    om = (cboe or {}).get("metrics", {})
    lines.append(f"• 옵션({date_label(cboe)}): " + " / ".join(f"{label} {om[key+'_pc_ratio']:.2f}" if number(om.get(key+'_pc_ratio')) is not None else f"{label} 미확인" for key, label in (("equity", "주식 P/C"), ("index", "지수"), ("total", "전체"))))
    if report and end and report < end:
        lines.append(f"※ 선물은 가격보다 {(end-report).days}일 이전 자료 · 옵션의 매수·매도 방향 미확인.")
    else:
        lines.append("※ 선물은 주간 보유량이며 당일 매매 흐름이 아님 · 옵션의 매수·매도 방향 미확인.")
    return lines


def render_alert(cftc, cboe, sox, updates, results, errors=(), event_label="신규 변화", context=None, detail_url=None):
    """A bounded, single-message brief; detail generation never sends a message."""
    context = context or {}
    end = date_value((sox or {}).get("period"))
    sm = (sox or {}).get("metrics", {})
    indices = context.get("indices", {})
    broad = [checked_returns(indices.get(k, {}).get("returns"), end, k) for k in ("NDX", "SPX")] if end else []
    if broad and all(broad) and all(x["windows"]["5d"]["status"] == "verified" for x in broad):
        five = [x["windows"]["5d"]["return_pct"] for x in broad]
        icon = "🔴" if all(v < 0 for v in five) else "🟢" if all(v > 0 for v in five) else "🟡"
        title = "나스닥100·S&P500 최근 5거래일 " + ("하락" if all(v < 0 for v in five) else "상승" if all(v > 0 for v in five) else "방향 혼재")
    else:
        icon, title, _ = horizon_overview(sox)
        title += " · 주요지수 종합 확인 대기"
    body = [f"🇺🇸 <b>미국 포지셔닝 | {escape(event_label)}</b>", "", "<b>한눈에 보기</b>", f"{icon} <b>{title}</b>"]
    body += _at_a_glance(cftc, cboe, sox, context)
    body += ["", f"<b>① 가격 | {date_label(sox)} 마감</b>",
             "수익률 순서: 5거래일 / 1개월 전 대비 / 3개월 전 대비"]
    sox_returns = [sm.get("d5_pct") if sm.get("final_close_confirmed") is True else None]
    sox_returns += [verified_price_return(sm.get("month_windows", {}).get(k), end, sm.get("value")) if end and sm.get("final_close_confirmed") is True else None for k in ("1m", "3m")]
    body.append(price_level_line("SOX",sm.get("value") if sm.get("final_close_confirmed") is True else None,sm.get("previous_close"),sm.get("d1_pct")))
    body.append("• SOX: " + " / ".join(percent(v,2,True) if number(v) is not None else "확인 대기" for v in sox_returns))
    for symbol, label in (("NDX", "나스닥100"), ("SPX", "S&P500")):
        checked = checked_returns(indices.get(symbol, {}).get("returns"), end, symbol) if end else None
        daily=checked["windows"].get("1d",{}) if checked else {}
        body.append(price_level_line(label,checked.get("close") if checked else None,
                                     daily.get("base_primary") if daily.get("status")=="verified" else None,daily.get("return_pct")))
        bits = []
        for key in ("5d", "1m", "3m"):
            window = checked["windows"][key] if checked else {}
            bits.append(percent(window["return_pct"],2,True) if window.get("status") == "verified" else "확인 대기")
        body.append(f"• {label}: " + " / ".join(bits))
    for symbol, label, path in (("SOX", "SOX", sm.get("price_path")), ("NDX", "나스닥100", indices.get("NDX")), ("SPX", "S&P500", indices.get("SPX"))):
        body.append(_brief_path(path, end, symbol, label))
    body.append("※ 기간 수익률과 현재 추세는 별개. 추세는 종가·20·60일선 순서와 평균선 방향 기준.")
    body += [""] + turnover_lines(context.get("amounts",{}),end)

    report = date_value((cftc or {}).get("period"))
    cm = (cftc or {}).get("metrics", {})
    history = (cftc or {}).get("history_3y", {})
    amounts=context.get("amounts",{})
    reference=checked_reference(amounts.get("nq_reference"),report) if report else None
    body += ["", f"<b>③ 선물 | {date_label(cftc)} 주간 · 계약</b>",
             f"• 나스닥100 통합: 기관 {position_level(cm.get('asset_net'))} / 헤지펀드성 {position_level(cm.get('lev_net'))}",
             "<b>NQ E-mini 헤지펀드성 · 통합과 별도 집계</b>"]
    for label, window in (("1주", history.get("week_window")), ("1개월", history.get("month_windows", {}).get("1m")), ("3개월", history.get("month_windows", {}).get("3m"))):
        parts = checked_composition(window, "leveraged_funds", report) if report else None
        if parts is None:
            body.append(f"• {label} 롱·숏 변화: 확인 대기")
            continue
        if label == "1주":
            estimated=reference_amount_line(parts['end_net'],amounts,report)
            body.append(f"• 현재 <b>{position_level(parts['end_net'])}</b>" + (f" · 참고 {estimated}" if estimated else ""))
            base = date_value(window.get("base_date"))
            comparison = "1주 전 대비" if base and (report - base).days == 7 else f"직전 관측 대비({window['base_date']})"
        else:
            comparison = f"{label} 비교"
        body.append(f"• {comparison}: <b>{position_movement(parts['end_net'],parts['net_change'])}</b>")
        body.append("  " + holding_change("롱",parts["long_change"]) + " / " + holding_change("숏",parts["short_change"]))
        estimated=reference_amount_line(parts['net_change'],amounts,report)
        if estimated:
            body.append("  계약 수 변화의 동일가격 환산: " + estimated)
    if reference is None:
        label=report.isoformat() if report else "주간 기준일"
        body.append(f"• 참고 명목금액: 환산 보류 · {label} NDX 종가 누락·불일치")
    else:
        rate=checked_fx(amounts.get("nq_fx"),report)
        multiplier=money_pair(20,amounts.get("nq_fx"),report)
        body.append(f"※ 참고금액: {reference['date']} NDX 종가×{multiplier}/pt, ECOS {rate['date'] if rate else '환율 미확인'}. 거래대금·증거금 아님.")
    if report and end:
        lag = (end - report).days
        body.append(f"※ 가격보다 {lag}일 이전 자료. 보유량 변화이며 주문·청산 목적 미확인." if lag > 0 else "※ 주간 보유량 변화이며 현재 매매·주문·청산 목적 미확인.")
    else:
        body.append("※ 가격과 선물 기준일 차이 미확인. 주문·청산 목적 미확인.")

    body += ["", "<b>④ 시장 확산·옵션 참고</b>"]
    breadth = context.get("breadth", {})
    comparison = breadth_comparison(breadth.get("series", {}), end) if end else {}
    if comparison.get("status") == "verified" and comparison == breadth.get("comparison"):
        bits = [f"{label} {comparison['windows'][key]['difference_pp']:+.2f}%p" for key,label in (("5d","5일"),("1m","1개월"),("3m","3개월"))]
        body.append("• 동일가중 RSP − 시총가중 SPY: " + " / ".join(bits))
        body.append("  Yahoo 조정종가의 ETF 상대수익률. 상승 종목 비율·시장 전체 방향은 미확인.")
    else:
        body.append("• RSP−SPY 상대수익률: 확인 대기")
    om = (cboe or {}).get("metrics", {})
    body.append(f"• 옵션 P/C({date_label(cboe)}): " + " / ".join(f"{label} {om[key+'_pc_ratio']:.2f}" if number(om.get(key+'_pc_ratio')) is not None else f"{label} 미확인" for key,label in (("equity","주식"),("index","지수"),("total","전체"))))
    body.append(f"• 옵션 전체 거래량: 콜 {integer(om.get('total_calls'))} / 풋 {integer(om.get('total_puts'))}계약 · 프리미엄 거래대금 미제공")
    options_end = date_value((cboe or {}).get("period"))
    for key, label in (("1m", "1개월"), ("3m", "3개월")):
        stats = checked_options(context.get("options", {}).get(key), om, options_end) if options_end else None
        if stats is None:
            body.append(f"• 주식 P/C 과거 {label}: 확인 대기")
        else:
            v = stats["values"]["equity"]
            body.append(f"• 주식 P/C 과거 {label}: 중앙값 {v['median_pc']:.3f} / 현재값 이하 {v['current_le_percent']:.1f}% (현재일 제외·동률 포함)")
    body.append("※ P/C=풋÷콜 거래량. 매수·매도 방향과 가격 반등을 확인한 값은 아님.")
    if errors:
        body.append("⚠ 일부 자료 확인 대기 · 세부 사유는 상세 기록")
    body += ["", f'<a href="{escape(detail_url,quote=True)}">상세 수치·계산·출처</a>' if detail_url else "상세 원값·계산·출처는 별도 상세 기록에 보존"]
    message = "\n".join(body) + "\n"
    if len(message.strip()) > BRIEF_MAX_CHARS:
        raise ValueError("US positioning brief exceeds the single-message length budget")
    return message

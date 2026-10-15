"""Read-only Telegram presentation for the verified US positioning snapshot.

Price direction, the level/change of weekly futures positions, and option volume
are separate observations. This module performs no collection, sending or I/O.
"""

from datetime import datetime
from html import escape
from math import isfinite

from us_positioning_horizons import verified_price_return, verified_position_change


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
        return "🟡", "반도체 혼재 · 1개월 상승, 단기·3개월 하락", "최근 며칠의 약세와 최근 몇 달의 흐름을 구분합니다."
    if short_icon == "🔴" and one < 0 and three > 0:
        return "🟡", "반도체 혼재 · 3개월 상승, 단기·1개월 하락", "3개월 수익률은 양수지만 최근 1개월과 단기는 하락입니다."
    if short_icon == "🔴" and one > 0 and three > 0:
        return "🟡", "반도체 1·3개월 상승 속 단기 하락", "최근 하락만으로 1·3개월 방향까지 하락으로 표시하지 않습니다."
    if short_icon in ("🟢", "🟡") and one < 0 and three < 0 and number(metrics.get("d1_pct")) is not None and metrics["d1_pct"] > 0:
        return "🟡", "반도체 1·3개월 하락 속 단기 반등", "당일 상승만으로 1·3개월의 하락 방향이 바뀌었다고 보지 않습니다."
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


def position_line(label, net, change):
    return (
        f"• {escape(label)}: <b>{position_level(net)}</b>"
        f" | 주간 {integer(change, signed=True)} → {position_change(net, change)}"
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


def render_alert(cftc, cboe, sox, updates, results, errors=(), event_label="신규 변화"):
    """Render the operating message from inputs already passed by source gates."""
    icon, title, reason = horizon_overview(sox)
    body = [
        f"🇺🇸 <b>[미국 포지셔닝 | {escape(event_label)}]</b>",
        "",
        f"{icon} <b>기간 종합: {title}</b>",
        reason,
    ]
    cm = (cftc or {}).get("metrics", {})
    if cm and number(cm.get("lev_net")) is not None and cm["lev_net"] < 0 and number(cm.get("lev_net_wow")) is not None and cm["lev_net_wow"] > 0:
        body.append("선물의 순숏은 줄었지만 여전히 순숏입니다. 이 주간 변화만으로 가격 반등을 판단하지 않습니다.")
    body += ["", f"<b>① 기간별 가격 방향 | {date_label(sox)} 마감</b>"]
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
            body.append(f"• {label}: <b>{percent(change, 2, signed=True)} · {direction}</b> ({window['base_date']} → {window['end_date']})")
    body.append("• 월간은 달력 1·3개월 전 기준일 이하 최근 관측 종가와 비교")
    body.append("• 1·3개월의 현재·기준 종가를 Nasdaq·Yahoo로 대조" if verified_months == 2 else "• 두 제공처에서 확인된 월간만 표시. 미확인·불일치 기간의 계산과 종합 판정은 보류")

    body += ["", f"<b>② 선물 보유 방향 | {date_label(cftc)} 주간</b>", "나스닥100 통합 · 선물만"]
    body.append(position_line("기관", cm.get("asset_net"), cm.get("asset_net_wow")))
    body.append(position_line("헤지펀드성", cm.get("lev_net"), cm.get("lev_net_wow")))
    body.append(_lag_line(cftc, sox))
    body.append("• 순롱=롱이 더 많음 / 순숏=숏이 더 많음 · 투자자 전체 자산이나 현물 매수·매도액은 아님")
    position_windows = (cftc or {}).get("history_3y", {}).get("month_windows", {})
    body.append("<b>NQ E-mini · 1개월/3개월 순포지션 변화</b>")
    for key, label in (("1m", "1개월"), ("3m", "3개월")):
        window = position_windows.get(key, {})
        bits = []
        for actor, actor_label in (("asset_manager", "기관"), ("leveraged_funds", "헤지펀드성")):
            change = verified_position_change(window, actor, date_value((cftc or {}).get("period"))) if date_value((cftc or {}).get("period")) else None
            if change is None:
                bits.append(f"{actor_label} 확인 대기")
            else:
                net = window["actors"][actor]["end_net"]
                bits.append(f"{actor_label} {integer(change, signed=True)}계약({position_change(net, change)})")
        interval = f" ({window['base_date']} → {window['end_date']})" if window.get("base_date") else ""
        body.append(f"• {label}{interval}: " + " / ".join(bits))
    body.append("• 월간 선물 비교는 각 달력 기준일 이하 최근 주간 관측 사용. 위 통합 수치와 집계 범위가 다름")

    body += ["", f"<b>③ 옵션 거래량 | {date_label(cboe)} 일별 참고</b>"]
    om = (cboe or {}).get("metrics", {})
    for key, label in (("equity", "주식"), ("index", "지수"), ("total", "전체")):
        calls, puts, ratio = [om.get(key + suffix) for suffix in ("_calls", "_puts", "_pc_ratio")]
        ratio_text = f"{ratio:.2f}" if number(ratio) is not None else "미확인"
        body.append(f"• {label}: <b>{volume_description(calls, puts, ratio)}</b> | P/C {ratio_text}")
    body.append("• P/C=풋÷콜 거래량. 매수·매도는 구분되지 않아 옵션만으로 상승·하락 방향을 판정하지 않음")

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
    body.append("• 가격은 SOX 반도체 지수 범위. Nasdaq·Yahoo 동일 거래일 종가 교차검증 및 Cboe 일별 마감 통계 기준")
    if errors:
        body += ["", "<b>확인 대기</b>"]
        body.extend("• " + escape(error.split(":", 1)[0]) + " 최신값 자동 재확인 중" for error in errors)
    return "\n".join(body) + "\n"

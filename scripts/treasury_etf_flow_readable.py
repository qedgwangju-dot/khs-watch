#!/usr/bin/env python3
import datetime as dt

import treasury_etf_flow_watch as base


def flow_arrow(value):
    if value is None:
        return "·"
    return "↑" if value > 0 else "↓" if value < 0 else "→"


def price_arrow(value):
    if value is None:
        return "·"
    return "↑" if value > 0 else "↓" if value < 0 else "→"


def plain_interpretation(ticker, r):
    flow = r.get("flow_usd")
    price = r.get("nav_change_pct")
    sf = base.sign_value(flow)
    sp = base.sign_value(price)

    if ticker == "SHY":
        if sf > 0:
            return "아직 방어적: 짧은 국채에서 높은 이자를 받으며 장기금리 방향 확신을 미루는 돈이 들어오는 중"
        if sf < 0:
            return "방어자금 일부 이탈: 단기채에 주차했던 돈이 다른 만기로 이동할 가능성을 확인할 구간"
        return "단기채 자금 방향은 중립"

    if ticker == "IEF":
        if sf > 0:
            return "금리 하락 기대가 조금씩 강해짐: 7~10년 국채로 실제 자금이 들어오기 시작"
        if sf < 0:
            return "10년물 금리 하락 확신이 아직 약함: 중기 국채에서 돈이 빠지는 중"
        return "중기채 금리 하락 베팅은 아직 뚜렷하지 않음"

    if ticker == "TLT":
        if sp > 0 and sf > 0:
            return "장기금리 하락에 실제 돈까지 베팅하기 시작: 가격 상승과 신규 자금 유입이 동시에 확인됨"
        if sp > 0 and sf < 0:
            return "가격은 반등했지만 돈은 빠짐: 장기채 강세 확신보다 반등 때 빠져나오는 자금이 아직 우세"
        if sp < 0 and sf > 0:
            return "장기채 저가매수: 가격은 약하지만 금리 하락을 기대하는 선행 자금이 들어오는 중"
        if sp < 0 and sf < 0:
            return "장기채 회피: 가격도 약하고 자금도 빠져 장기금리 상승 부담을 경계하는 흐름"
        if sf > 0:
            return "장기채로 자금은 들어오지만 가격 확인이 더 필요"
        if sf < 0:
            return "장기채에서 자금 이탈 중"
        return "장기채 방향은 중립"

    return ""


def market_direction(results, curve):
    shy = base.sign_value(results["SHY"].get("flow_usd"))
    ief = base.sign_value(results["IEF"].get("flow_usd"))
    tlt = base.sign_value(results["TLT"].get("flow_usd"))
    tlt_price = base.sign_value(results["TLT"].get("nav_change_pct"))
    thirty = curve.get("30Y")

    if thirty is not None and thirty >= 5.30:
        return "장기금리 위험 확대", "30년물이 5.30% 이상이라 장기채와 고밸류 위험자산의 할인율 부담이 다시 커진 상태"
    if shy > 0 and ief <= 0 and tlt <= 0:
        return "단기채 피신·방어적", "돈이 SHY에 머물고 IEF·TLT로 넘어가지 않아 아직 장기금리 하락을 신뢰하지 않는 흐름"
    if ief > 0 and tlt_price > 0 and tlt > 0:
        return "장기채 로테이션 확인", "IEF 유입과 TLT 가격·자금 동반 상승이 확인돼 단기채에서 중·장기채로 실제 로테이션이 시작된 흐름"
    if ief > 0 and tlt <= 0:
        return "중기채 전환 초기", "IEF로는 돈이 들어오지만 TLT까지 확산되지 않아 금리 하락 기대가 중기물에서 먼저 나타나는 단계"
    if tlt_price > 0 and tlt < 0:
        return "장기채 반등은 있으나 확신 부족", "TLT 가격은 올랐지만 자금은 빠져 신규 장기채 매수보다 반등 매도가 섞인 흐름"
    if tlt_price < 0 and tlt > 0:
        return "장기채 저가매수 진행", "TLT 가격 하락에도 자금이 들어와 장기금리 고점에 베팅하는 선행 매수가 들어오는 흐름"
    return "방향성 확인 대기", "SHY·IEF·TLT 사이의 자금 이동이 아직 한 방향으로 정렬되지 않은 상태"


def main():
    state = base.load_state()
    state.setdefault("history", {})
    now = dt.datetime.now(base.KST)
    fx = base.get_usdkrw()
    curve = base.get_treasury_curve()
    results = {}

    for ticker, meta in base.FUNDS.items():
        cur = base.get_ishares(ticker, meta)
        hist = state["history"].get(ticker, [])
        flow = base.compute_flow(cur, hist)
        cur["flow_usd"] = flow
        hist = base.upsert_history(hist, cur, flow)
        state["history"][ticker] = hist
        cur["flow_5d_usd"] = base.last_n_flows(hist, 5)
        results[ticker] = cur

    headline, headline_text = market_direction(results, curve)

    lines = [
        "[미 국채 ETF Fund Flow — 방향성 한눈에 보기]",
        f"조회시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        "",
        f"오늘의 방향: {headline}",
        f"→ {headline_text}",
        "",
        "[돈이 어디로 가는가]",
    ]

    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        flow = r.get("flow_usd")
        flow5 = r.get("flow_5d_usd")
        lines.append(
            f"{ticker} {flow_arrow(flow)}  일간 {base.fmt_usd_flow(flow)} ({base.fmt_krw(flow, fx['rate'])})"
            f" | 최근 5회 {base.fmt_usd_flow(flow5)} ({base.fmt_krw(flow5, fx['rate'])})"
        )
        lines.append(f"→ {plain_interpretation(ticker, r)}")

    lines.extend([
        "",
        "[이 흐름을 이렇게 읽으면 됨]",
        "SHY 유입↑ = 아직 방어적 → 짧은 만기에서 이자를 받으며 기다리는 돈이 많음",
        "IEF 유입 전환 = 금리 하락 기대가 조금씩 강해짐 → 중기 국채로 돈이 이동하기 시작",
        "TLT 가격↑ + 자금↑ = 장기금리 하락에 실제 돈까지 베팅하기 시작 → 가장 강한 장기채 강세 확인",
        "TLT 가격↑ + 자금↓ = 반등은 나왔지만 확신 부족 → 기존 보유자의 반등 매도 가능성",
        "TLT 가격↓ + 자금↑ = 장기채 저가매수 → 가격보다 먼저 금리 고점에 베팅하는 자금",
        "",
        "[ETF별 상세 숫자]",
    ])

    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        price = "확인불가" if r["nav_change_pct"] is None else f"{r['nav_change_pct']:+.2f}%"
        sec = "확인불가" if r["sec_yield"] is None else f"{r['sec_yield']:.2f}%"
        lines.append(f"{ticker} ({r['label']}) — 기준 {r['date']}")
        lines.append(f"• NAV ${r['nav']:.2f} ({price_arrow(r.get('nav_change_pct'))} {price}) | 30일 SEC 수익률 {sec}")
        lines.append(f"• 일간 자금흐름: {base.fmt_usd_flow(r['flow_usd'])} ({base.fmt_krw(r['flow_usd'], fx['rate'])})")
        lines.append(f"• 최근 5회 누적: {base.fmt_usd_flow(r['flow_5d_usd'])} ({base.fmt_krw(r['flow_5d_usd'], fx['rate'])})")
        lines.append(f"• 발행좌수: {r['shares']:,.0f}")

    lines.extend([
        "",
        f"[미 재무부 공식 금리 — {curve['date']}]",
        f"2년 {curve['2Y']:.2f}% | 10년 {curve['10Y']:.2f}% | 30년 {curve['30Y']:.2f}%",
        f"30년물 5.30% 경계: {'위험구간 재진입' if curve['30Y'] >= 5.30 else f'현재 {5.30-curve[\"30Y\"]:.2f}%p 아래'}",
        "",
        "[최종 해석]",
        f"{headline} — {headline_text}",
        "",
        f"USD/KRW {fx['rate']:,.2f}원 | 기준 {fx.get('date') or '최신'} | {fx['source']}",
        "자금흐름 산식: iShares 공식 발행좌수 변화 × 해당일 NAV. 유료 벤더 Fund Flow와 집계시점 차이가 있을 수 있음.",
        "출처: iShares 공식 SHY·IEF·TLT, U.S. Treasury, 환율 교차자료",
    ])

    text = "\n".join(lines)
    (base.OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")

    username, ids = base.send_telegram(text)
    state["last_delivery"] = {
        "at_kst": now.isoformat(timespec="seconds"),
        "bot_username": username,
        "message_ids": ids,
        "classification": headline,
        "treasury_date": curve["date"],
    }
    base.save_state(state)
    print(f"telegram_delivery_confirmed=true bot=@{username} message_ids={ids} classification={headline}")


if __name__ == "__main__":
    main()

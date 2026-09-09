#!/usr/bin/env python3
import datetime as dt
import html
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests

import treasury_etf_flow_watch as base

KST = ZoneInfo("Asia/Seoul")

FUNDS = {
    "SHY": {
        "label": "미 국채 1~3년",
        "url": "https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf",
        "group": "treasury",
    },
    "IEF": {
        "label": "미 국채 7~10년",
        "url": "https://www.ishares.com/us/products/239456/ishares-7-10-year-treasury-bond-etf",
        "group": "treasury",
    },
    "TLT": {
        "label": "미 국채 20년 이상",
        "url": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
        "group": "treasury",
    },
    "LQD": {
        "label": "미 투자등급 회사채",
        "url": "https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf",
        "group": "credit",
    },
    "HYG": {
        "label": "미 고수익 회사채",
        "url": "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf",
        "group": "credit",
    },
}

FRED_SERIES = {
    "IG_OAS": "BAMLC0A0CM",
    "HY_OAS": "BAMLH0A0HYM2",
}


def arrow(v):
    if v is None:
        return "·"
    return "↑" if v > 0 else "↓" if v < 0 else "→"


def flow_word(v):
    if v is None:
        return "기준점 수집 중"
    return "순유입" if v > 0 else "순유출" if v < 0 else "중립"


def get_curve_pair():
    year = dt.datetime.now(KST).year
    url = (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
        f"?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    )
    r = requests.get(url, headers=base.HEADERS, timeout=35)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns_d = "http://schemas.microsoft.com/ado/2007/08/dataservices"
    rows = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        def val(name):
            node = entry.find(f".//{{{ns_d}}}{name}")
            return None if node is None or node.text in (None, "") else node.text
        d = val("NEW_DATE")
        if not d:
            continue
        rows.append({
            "date": d[:10],
            "2Y": float(val("BC_2YEAR")) if val("BC_2YEAR") else None,
            "10Y": float(val("BC_10YEAR")) if val("BC_10YEAR") else None,
            "30Y": float(val("BC_30YEAR")) if val("BC_30YEAR") else None,
        })
    rows.sort(key=lambda x: x["date"])
    if not rows:
        raise RuntimeError("Treasury yield curve returned no rows")
    return rows[-1], rows[-2] if len(rows) >= 2 else None


def get_fred_pair(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, headers=base.HEADERS, timeout=35)
    r.raise_for_status()
    rows = []
    for line in r.text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2 or parts[1] in ("", "."):
            continue
        try:
            rows.append({"date": parts[0], "value": float(parts[1])})
        except ValueError:
            continue
    if not rows:
        raise RuntimeError(f"FRED {series_id} returned no observations")
    return rows[-1], rows[-2] if len(rows) >= 2 else None


def bp(cur, prev, key):
    if not prev or cur.get(key) is None or prev.get(key) is None:
        return None
    return (cur[key] - prev[key]) * 100.0


def fmt_bp(v):
    if v is None:
        return "비교불가"
    return f"{arrow(v)} {v:+.0f}bp"


def curve_regime(cur, prev):
    if not prev:
        return "판정 대기", "직전 거래일 자료가 없어 수익률곡선 변화 판정 대기", None, None
    d2, d10, d30 = bp(cur, prev, "2Y"), bp(cur, prev, "10Y"), bp(cur, prev, "30Y")
    s210_now = (cur["10Y"] - cur["2Y"]) * 100
    s210_prev = (prev["10Y"] - prev["2Y"]) * 100
    ds210 = s210_now - s210_prev
    s1030_now = (cur["30Y"] - cur["10Y"]) * 100
    s1030_prev = (prev["30Y"] - prev["10Y"]) * 100
    ds1030 = s1030_now - s1030_prev

    if d2 is not None and d10 is not None and d2 > 0 and d10 > 0 and ds210 < 0:
        name = "베어 플래트닝"
        easy = "금리↑ + 단기금리가 더 크게↑ → Fed 재인상·고금리 장기화 우려"
    elif d2 is not None and d10 is not None and d2 > 0 and d10 > 0 and ds210 > 0:
        name = "베어 스티프닝"
        easy = "금리↑ + 장기금리가 더 크게↑ → 재정·국채 공급·인플레이션·기간프리미엄 부담"
    elif d2 is not None and d10 is not None and d2 < 0 and d10 < 0 and ds210 > 0:
        name = "불 스티프닝"
        easy = "금리↓ + 단기금리가 더 크게↓ → Fed 인하·경기둔화 기대"
    elif d2 is not None and d10 is not None and d2 < 0 and d10 < 0 and ds210 < 0:
        name = "불 플래트닝"
        easy = "금리↓ + 장기금리가 더 크게↓ → 장기 성장·물가 기대 약화"
    else:
        name = "커브 트위스트·혼조"
        easy = "2년·10년 금리가 한 방향으로 정렬되지 않음 → Fed 경로와 장기 재정·성장 요인을 분리 확인"

    if ds1030 > 0.5:
        back = "10년-30년 금리차 확대 → 30년물이 상대적으로 더 약함 → 재정·장기채 공급·기간프리미엄 부담 강화"
    elif ds1030 < -0.5:
        back = "10년-30년 금리차 축소 → 30년물이 상대적으로 덜 약함/더 강함 → 뒷단 재정·장기채 공급 압력 상대 완화"
    else:
        back = "10년-30년 금리차 변화 제한 → 뒷단 재정·장기채 공급 압력의 추가 변화는 제한적"

    front_fed = d2 is not None and d10 is not None and d2 > 0 and d10 > 0 and d2 > d10
    back_fiscal = d30 is not None and d10 is not None and d30 > d10 and d30 > 0
    if front_fed and not back_fiscal:
        driver = "오늘의 주도축: 앞단 Fed 문제 우세 → 재인상·고금리 장기화 우려가 핵심"
    elif back_fiscal and not front_fed:
        driver = "오늘의 주도축: 뒷단 재정·장기채 공급 문제 우세 → 기간프리미엄·국채 공급 부담이 핵심"
    elif front_fed and back_fiscal:
        driver = "오늘의 주도축: 앞단 Fed와 뒷단 재정·장기채 공급이 동시에 압박"
    else:
        driver = "오늘의 주도축: Fed와 재정 중 한쪽으로 단정하기 어려움"

    return name, easy, (s210_now, s210_prev, ds210), (s1030_now, s1030_prev, ds1030, back, driver)


def etf_interpretation(ticker, price, flow):
    if ticker == "SHY":
        if flow is None:
            return "단기채 피신 여부 판정 대기"
        return "짧은 미 국채에서 이자를 받으며 기다리는 방어자금 유입" if flow > 0 else "단기 안전자산에 주차했던 자금 일부 이탈"
    if ticker == "IEF":
        if flow is None:
            return "중기채 방향 판정 대기"
        return "7~10년 국채로 실제 자금 유입 → 금리하락 베팅이 중기물로 이동" if flow > 0 else "10년물 금리하락 확신 약화 → 중기채 자금 이탈"
    if ticker == "TLT":
        if flow is None:
            return "장기채 방향 판정 대기"
        if price is not None and price > 0 and flow > 0:
            return "가격↑ + 자금↑ → 장기금리 하락에 실제 돈까지 베팅, 장기채 강세 확인"
        if price is not None and price > 0 and flow < 0:
            return "가격↑ + 자금↓ → 반등 매도·신규 장기매수 확신 부족"
        if price is not None and price < 0 and flow > 0:
            return "가격↓ + 자금↑ → 장기금리 고점에 선행 베팅하는 저가매수"
        if price is not None and price < 0 and flow < 0:
            return "가격↓ + 자금↓ → 장기금리 상승 부담을 피하는 장기채 회피"
        return "장기채 방향 혼조"
    if ticker == "LQD":
        if flow is None:
            return "투자등급 회사채 자금 방향 판정 대기"
        if price is not None and price < 0 and flow < 0:
            return "가격↓ + 자금↓ → 우량 회사채에서도 위험 축소, 품질 선호 강화 신호"
        if price is not None and price > 0 and flow > 0:
            return "가격↑ + 자금↑ → 투자등급 회사채 수요 회복"
        if flow < 0:
            return "자금↓ → 우량 회사채 노출 축소, 신용위험 경계"
        return "자금↑ → 투자등급 신용자산 선호 회복"
    if ticker == "HYG":
        if flow is None:
            return "고수익 회사채 자금 방향 판정 대기"
        if price is not None and price < 0 and flow < 0:
            return "가격↓ + 자금↓ → 위험선호 약화가 가격과 자금에서 동시에 확인"
        if price is not None and price > 0 and flow < 0:
            return "가격↑ + 자금↓ → 가격은 버티지만 위험자금은 먼저 이탈하는 초기 경계"
        if price is not None and price > 0 and flow > 0:
            return "가격↑ + 자금↑ → 위험선호 회복"
        if flow < 0:
            return "자금↓ → 고위험 회사채 회피, 위험선호 약화"
        return "자금↑ → 고위험 신용자산 선호 회복"
    return ""


def treasury_flow_classification(results, curve):
    vals = [results[x].get("flow_usd") for x in ("SHY", "IEF", "TLT")]
    if any(v is None for v in vals):
        return "국채 Fund Flow 판정 대기", "기준점 부족으로 순유입·순유출 판정 대기"
    shy, ief, tlt = vals
    tlt_price = results["TLT"].get("nav_change_pct")
    if curve.get("30Y") is not None and curve["30Y"] >= 5.30:
        return "장기채 위험 확대", "30년물 5.30% 이상 → 장기채·고밸류 위험자산 할인율 부담 확대"
    if shy > 0 and ief <= 0 and tlt <= 0:
        return "단기채 피신·방어적", "SHY 유입 + IEF/TLT 이탈 → 장기금리 하락보다 짧은 만기 이자 선호"
    if ief > 0 and tlt > 0 and (tlt_price or 0) > 0:
        return "장기채 로테이션 확인", "IEF 순유입 + TLT 가격·자금 동반 상승 → 실제 자금이 중·장기 만기로 이동"
    if ief > 0 and tlt > 0:
        return "중·장기채 저가매수", "IEF·TLT에 동시 자금 유입 → 장기금리 고점 베팅이 일부 시작"
    if ief > 0 and tlt <= 0:
        return "중기채 전환 초기", "IEF에서 금리하락 기대가 먼저 나타나지만 TLT까지 확산되지 않음"
    return "국채 내부 혼조", "SHY·IEF·TLT 자금이 한 방향으로 정렬되지 않음"


def credit_classification(results, ig_oas, hy_oas):
    lqd = results["LQD"].get("flow_usd")
    hyg = results["HYG"].get("flow_usd")
    lp = results["LQD"].get("nav_change_pct")
    hp = results["HYG"].get("nav_change_pct")
    if lqd is None or hyg is None:
        return "신용 Fund Flow 판정 대기", "LQD·HYG 기준점이 충분히 쌓일 때까지 신용자금 방향 판정 대기"

    ig_delta = None if not ig_oas[1] else (ig_oas[0]["value"] - ig_oas[1]["value"]) * 100
    hy_delta = None if not hy_oas[1] else (hy_oas[0]["value"] - hy_oas[1]["value"]) * 100

    if hyg < 0 and (hp or 0) < 0 and hy_delta is not None and hy_delta >= 5:
        return "신용위험 확대 확인", "HYG 가격↓ + 자금↓ + 고수익채 스프레드↑ → 위험회피가 가격·수급·신용에서 동시에 확인"
    if lqd < 0 and hyg < 0:
        if (ig_delta is None or abs(ig_delta) < 5) and (hy_delta is None or abs(hy_delta) < 5):
            return "품질 선호·선제적 위험축소", "LQD·HYG 자금은 빠지지만 스프레드 급등은 아직 없음 → 신용위기보다 자금이 먼저 방어적으로 이동"
        return "회사채 위험축소", "LQD·HYG 동반 유출 → 정부채 대비 기업 신용위험 노출 축소"
    if lqd > 0 and hyg < 0:
        return "우량 신용만 선호", "LQD 유입·HYG 유출 → 회사채 안에서도 투자등급으로 품질 이동"
    if lqd > 0 and hyg > 0:
        return "신용 위험선호 회복", "LQD·HYG 동반 유입 → 기업 신용자산으로 위험선호 회복"
    return "신용시장 혼조", "LQD·HYG가 서로 다른 방향 → 위험선호 확정 전 추가 확인"


def overall_classification(treasury_head, credit_head, results):
    shy = results["SHY"].get("flow_usd")
    lqd = results["LQD"].get("flow_usd")
    hyg = results["HYG"].get("flow_usd")
    if shy is not None and lqd is not None and hyg is not None and shy > 0 and lqd < 0 and hyg < 0:
        return "방어적·품질 선호 강화", "회사채에서 빠진 자금이 안전한 미 국채, 특히 짧은 만기로 이동하는 품질 이동"
    if "신용위험 확대" in credit_head:
        return "위험회피 강화", "신용위험이 자금흐름을 넘어 가격·스프레드까지 번지는 단계"
    if "신용 위험선호 회복" in credit_head and "장기채 로테이션" in treasury_head:
        return "위험선호·금리하락 베팅 동시 회복", "중·장기 국채와 회사채로 자금이 함께 복귀"
    return "혼조·추가 확인", "국채 만기 이동과 회사채 위험선호가 아직 완전히 같은 방향으로 정렬되지 않음"


def _format_telegram_html(chunk):
    formatted = []
    for line in chunk.splitlines():
        escaped = html.escape(line, quote=False)
        bold = (
            line == "[오늘의 결론]"
            or line.startswith("ETF 자금 방향:")
            or line.startswith("신용자금 방향:")
            or line.startswith("전체 자금 방향:")
            or line.startswith("• 현재 형태:")
            or line.startswith("• 오늘의 주도축:")
            or line.startswith("• 신용 위험:")
        )
        formatted.append(f"<b>{escaped}</b>" if bold else escaped)
    return "\n".join(formatted)


def send_exact(text):
    token = (base.os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (base.os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (base.os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as r:
        identity = json.loads(r.read().decode("utf-8"))
    actual = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")

    chunks, current = [], ""
    for para in text.split("\n\n"):
        candidate = para if not current else current + "\n\n" + para
        if len(candidate) <= 3800:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)

    ids = []
    for chunk in chunks:
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": _format_telegram_html(chunk),
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=25) as r:
            result = json.loads(r.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected: {result}")
        ids.append((result.get("result") or {}).get("message_id"))
    return actual, ids


def main():
    state = base.load_state()
    state.setdefault("history", {})
    now = dt.datetime.now(KST)
    fx = base.get_usdkrw()
    curve, curve_prev = get_curve_pair()
    ig_oas = get_fred_pair(FRED_SERIES["IG_OAS"])
    hy_oas = get_fred_pair(FRED_SERIES["HY_OAS"])
    results = {}

    for ticker, meta in FUNDS.items():
        cur = base.get_ishares(ticker, meta)
        hist = list(state["history"].get(ticker, []))
        flow = base.compute_flow(cur, hist)
        cur["flow_usd"] = flow
        hist = base.upsert_history(hist, cur, flow)
        state["history"][ticker] = hist
        cur["flow_5d_usd"] = base.last_n_flows(hist, 5)
        results[ticker] = cur

    t_head, t_reason = treasury_flow_classification(results, curve)
    c_head, c_reason = credit_classification(results, ig_oas, hy_oas)
    o_head, o_reason = overall_classification(t_head, c_head, results)
    regime, regime_easy, s210, s1030 = curve_regime(curve, curve_prev)
    d2, d10, d30 = bp(curve, curve_prev, "2Y"), bp(curve, curve_prev, "10Y"), bp(curve, curve_prev, "30Y")
    gap30 = (5.30 - curve["30Y"]) * 100 if curve.get("30Y") is not None else None
    ig_delta = None if not ig_oas[1] else (ig_oas[0]["value"] - ig_oas[1]["value"]) * 100
    hy_delta = None if not hy_oas[1] else (hy_oas[0]["value"] - hy_oas[1]["value"]) * 100

    lines = [
        "[미 국채·회사채 ETF Fund Flow — 방향성·신용·수익률곡선 일일 보고]",
        f"조회시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"환율: 1달러={fx['rate']:,.2f}원 | 기준 {fx.get('date') or '최신'}",
        "",
        "[한눈에 보기]",
        f"전체 자금 방향: {o_head}",
        f"→ {o_reason}",
        f"ETF 자금 방향: {t_head}",
        f"→ {t_reason}",
        f"신용자금 방향: {c_head}",
        f"→ {c_reason}",
        f"금리 구조: {regime}",
        f"→ {regime_easy}",
        "",
    ]

    lines.append("[미 국채 ETF]")
    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        p, flow, flow5 = r.get("nav_change_pct"), r.get("flow_usd"), r.get("flow_5d_usd")
        price = "확인불가" if p is None else f"{arrow(p)} {p:+.2f}%"
        sec = "확인불가" if r.get("sec_yield") is None else f"{r['sec_yield']:.2f}%"
        lines.extend([
            f"{ticker} ({r['label']}) — {r['date']}",
            f"• 가격: NAV ${r['nav']:.2f} | 1일 {price} | 30일 SEC {sec}",
            f"• 일간 자금: {arrow(flow)} {flow_word(flow)} {base.fmt_usd_flow(flow)} ({base.fmt_krw(flow, fx['rate'])})",
            f"• 최근 5회: {arrow(flow5)} {base.fmt_usd_flow(flow5)} ({base.fmt_krw(flow5, fx['rate'])})",
            f"• 해석: {etf_interpretation(ticker, p, flow)}",
            "",
        ])

    lines.append("[회사채 ETF — 위험선호 확인]")
    for ticker in ("LQD", "HYG"):
        r = results[ticker]
        p, flow, flow5 = r.get("nav_change_pct"), r.get("flow_usd"), r.get("flow_5d_usd")
        price = "확인불가" if p is None else f"{arrow(p)} {p:+.2f}%"
        sec = "확인불가" if r.get("sec_yield") is None else f"{r['sec_yield']:.2f}%"
        lines.extend([
            f"{ticker} ({r['label']}) — {r['date']}",
            f"• 가격: NAV ${r['nav']:.2f} | 1일 {price} | 30일 SEC {sec}",
            f"• 일간 자금: {arrow(flow)} {flow_word(flow)} {base.fmt_usd_flow(flow)} ({base.fmt_krw(flow, fx['rate'])})",
            f"• 최근 5회: {arrow(flow5)} {base.fmt_usd_flow(flow5)} ({base.fmt_krw(flow5, fx['rate'])})",
            f"• 해석: {etf_interpretation(ticker, p, flow)}",
            "",
        ])

    lines.extend([
        "[신용스프레드 — FRED/ICE BofA]",
        f"• 투자등급 OAS: {ig_oas[0]['value']:.2f}% | {('비교불가' if ig_delta is None else f'{arrow(ig_delta)} {ig_delta:+.0f}bp')} | 기준 {ig_oas[0]['date']}",
        f"• 고수익채 OAS: {hy_oas[0]['value']:.2f}% | {('비교불가' if hy_delta is None else f'{arrow(hy_delta)} {hy_delta:+.0f}bp')} | 기준 {hy_oas[0]['date']}",
        f"• 신용 위험: {c_head}",
        f"→ {c_reason}",
        "• 핵심 조합: HYG 가격↓ + Fund Flow↓ + 고수익채 OAS↑ = 위험회피가 가격·수급·신용에서 동시에 확인",
        "• 반대 조합: LQD/HYG 자금↑ + OAS↓ = 회사채 위험선호 회복",
        "",
        "[미 국채 금리 방향]",
        f"기준: {curve['date']} | 직전: {curve_prev['date'] if curve_prev else '없음'}",
        f"• 2년: {curve['2Y']:.2f}% | {fmt_bp(d2)}",
        f"• 10년: {curve['10Y']:.2f}% | {fmt_bp(d10)}",
        f"• 30년: {curve['30Y']:.2f}% | {fmt_bp(d30)}",
    ])
    if s210:
        lines.append(f"• 2년-10년 금리차: {s210[1]:.0f}bp → {s210[0]:.0f}bp ({s210[2]:+.0f}bp)")
    if s1030:
        lines.append(f"• 10년-30년 금리차: {s1030[1]:.0f}bp → {s1030[0]:.0f}bp ({s1030[2]:+.0f}bp)")
        lines.append(f"• 뒷단 해석: {s1030[3]}")
        lines.append(f"• {s1030[4]}")
    lines.extend([
        f"• 30년 5.30% 경계: {'위험구간 진입' if curve['30Y'] >= 5.30 else f'아직 {gap30:.0f}bp 아래'}",
        "",
        "[수익률곡선 고정 해석]",
        f"• 현재 형태: {regime}",
        f"• 쉬운 해석: {regime_easy}",
        "• 베어 플래트닝 = 금리↑ + 단기금리가 더 크게↑ → Fed 재인상·고금리 장기화 우려",
        "• 베어 스티프닝 = 금리↑ + 장기금리가 더 크게↑ → 재정·국채 공급·인플레이션·기간프리미엄 부담",
        "• 불 스티프닝 = 금리↓ + 단기금리가 더 크게↓ → Fed 인하·경기둔화 기대",
        "• 불 플래트닝 = 금리↓ + 장기금리가 더 크게↓ → 장기 성장·물가 기대 약화",
        "",
        "[투자 언어로 번역]",
        f"• 국채: {t_reason}",
        f"• 회사채: {c_reason}",
        f"• 전체: {o_reason}",
        "• 해석 순서: SHY·IEF·TLT로 만기 이동 확인 → LQD·HYG로 기업 신용위험 확인 → OAS로 실제 신용악화인지 검증",
        "",
        "[오늘의 결론]",
        f"전체 자금 방향: {o_head}",
        f"ETF 자금 방향: {t_head}",
        f"신용자금 방향: {c_head}",
        f"금리 구조: {regime}",
        f"→ {o_reason}",
        "",
        "자금흐름 산식: iShares 공식 발행좌수 변화 × 해당일 NAV. LQD·HYG 첫 기준점만 있을 때는 자금방향을 억지 판정하지 않음.",
        "신용스프레드: FRED의 ICE BofA US Corporate OAS 및 US High Yield OAS 일별 종가.",
        "출처: iShares 공식 SHY·IEF·TLT·LQD·HYG, U.S. Treasury, FRED/ICE BofA, 환율 교차자료",
    ])

    text = "\n".join(lines)
    (base.OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")
    username, ids = send_exact(text)
    state["last_delivery"] = {
        "at_kst": now.isoformat(timespec="seconds"),
        "bot_username": username,
        "message_ids": ids,
        "treasury_flow": t_head,
        "credit_flow": c_head,
        "overall": o_head,
        "curve_regime": regime,
        "treasury_date": curve["date"],
        "ig_oas_date": ig_oas[0]["date"],
        "hy_oas_date": hy_oas[0]["date"],
        "format": "treasury-credit-directional-v1",
    }
    base.save_state(state)
    print(f"telegram_delivery_confirmed=true bot=@{username} message_ids={ids} overall={o_head} treasury={t_head} credit={c_head} curve={regime}")


if __name__ == "__main__":
    main()

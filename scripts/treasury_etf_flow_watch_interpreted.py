#!/usr/bin/env python3
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

import treasury_etf_flow_watch as base

KST = ZoneInfo("Asia/Seoul")


def arrow(v):
    if v is None:
        return "·"
    return "↑" if v > 0 else "↓" if v < 0 else "→"


def flow_word(v):
    if v is None:
        return "기준점 수집 중"
    return "순유입" if v > 0 else "순유출" if v < 0 else "중립"


def parse_1d_nav_change(meta):
    try:
        r = requests.get(meta["url"], headers=base.HEADERS, timeout=35)
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        m = re.search(
            r"1 Day NAV Change as of [A-Za-z]{3} \d{1,2}, \d{4}.{0,120}?(-?\d+(?:\.\d+)?)%\)",
            text,
        )
        if m:
            return float(m.group(1))
    except Exception:
        return None
    return None


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


def bp(cur, prev, key):
    if not prev or cur.get(key) is None or prev.get(key) is None:
        return None
    return (cur[key] - prev[key]) * 100


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

    both_up = d2 > 0 and d10 > 0
    both_down = d2 < 0 and d10 < 0
    if both_up and ds210 < 0:
        name = "베어 플래트닝"
        easy = "금리는 전반적으로 올랐지만 2년물이 10년물보다 더 크게 상승 → Fed 재인상·고금리 장기화 우려가 앞단을 더 세게 때린 흐름"
    elif both_up and ds210 > 0:
        name = "베어 스티프닝"
        easy = "금리는 전반적으로 올랐고 10년물이 2년물보다 더 크게 상승 → 인플레이션·국채공급·기간프리미엄 같은 장기 부담이 커진 흐름"
    elif both_down and ds210 > 0:
        name = "불 스티프닝"
        easy = "금리는 전반적으로 내렸고 2년물이 더 크게 하락 → Fed 인하 기대·경기둔화 우려가 앞단 금리를 빠르게 끌어내린 흐름"
    elif both_down and ds210 < 0:
        name = "불 플래트닝"
        easy = "금리는 전반적으로 내렸지만 10년물이 더 크게 하락 → 장기 성장·물가 기대가 더 약해진 흐름"
    else:
        name = "커브 트위스트·혼조"
        easy = "2년과 10년 금리가 같은 방향으로 움직이지 않아 Fed 경로와 장기 재정·성장 요인이 서로 다른 방향으로 작용하는 흐름"

    if d2 is not None and d30 is not None:
        if d2 - d30 >= 5:
            easy += ". 특히 앞단 상승이 장기물보다 훨씬 커 정책금리 재평가 성격이 강함"
        elif d30 - d2 >= 5:
            easy += ". 특히 장기물 상승이 앞단보다 훨씬 커 재정·기간프리미엄 압력이 강함"

    return name, easy, (s210_now, s210_prev, ds210), (s1030_now, s1030_prev, ds1030)


def etf_interpretation(ticker, price, flow):
    if ticker == "SHY":
        if flow is None:
            return "아직 전일 발행좌수 기준점이 없어 단기채 피신 여부는 판정 대기"
        return "짧은 국채에서 이자를 받으며 기다리는 방어자금 유입" if flow > 0 else "단기채에 주차했던 방어자금 일부 이탈"
    if ticker == "IEF":
        if flow is None:
            return "아직 전일 기준점이 없어 7~10년 금리하락 베팅 여부는 판정 대기"
        return "7~10년 국채로 실제 자금이 들어와 금리하락 기대가 중기물로 이동" if flow > 0 else "10년물 금리하락 확신이 약해 중기채에서 자금 이탈"
    if ticker == "TLT":
        if flow is None:
            return "아직 전일 기준점이 없어 장기채 신규자금 방향은 판정 대기"
        if price is not None and price > 0 and flow > 0:
            return "가격 상승 + 자금 유입 → 장기금리 하락에 실제 돈까지 베팅, 장기채 강세 확인"
        if price is not None and price > 0 and flow < 0:
            return "가격 반등 + 자금 유출 → 신규 장기매수보다 반등 매도, 강세 확신 부족"
        if price is not None and price < 0 and flow > 0:
            return "가격 하락 + 자금 유입 → 장기금리 고점에 선행 베팅하는 저가매수"
        if price is not None and price < 0 and flow < 0:
            return "가격 하락 + 자금 유출 → 장기금리 상승 부담을 피하는 장기채 회피"
        return "장기채 자금 방향 확인 중"
    return ""


def flow_classification(results, curve):
    vals = [results[x].get("flow_usd") for x in ("SHY", "IEF", "TLT")]
    if any(v is None for v in vals):
        return "Fund Flow 판정 대기", "첫 기준점만 확보돼 실제 순유입·순유출 방향은 다음 미국 영업일 데이터부터 판정 가능"
    shy, ief, tlt = vals
    tlt_price = results["TLT"].get("nav_change_pct")
    if curve.get("30Y") is not None and curve["30Y"] >= 5.30:
        return "장기채 위험 확대", "30년물 5.30% 이상으로 장기채와 고밸류 위험자산의 할인율 부담 확대"
    if shy > 0 and ief <= 0 and tlt <= 0:
        return "단기채 피신·방어적", "SHY로 돈이 들어가고 IEF·TLT는 이탈 → 장기금리 하락보다 짧은 만기 이자 선호"
    if ief > 0 and tlt > 0 and (tlt_price or 0) > 0:
        return "장기채 로테이션 확인", "IEF 순유입 + TLT 가격·자금 동반 상승 → 실제 자금이 중·장기 만기로 이동"
    if ief > 0 and tlt <= 0:
        return "중기채 전환 초기", "금리하락 기대가 IEF에서 먼저 나타나지만 TLT까지 확산되지는 않음"
    if (tlt_price or 0) > 0 and tlt < 0:
        return "TLT 반등은 있으나 확신 부족", "가격은 올랐지만 자금은 빠져 반등 매도가 섞인 흐름"
    return "혼조·방향 확인 대기", "SHY·IEF·TLT 자금이 아직 한 방향으로 정렬되지 않음"


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
        if len(candidate) <= 3900:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    ids = []
    for chunk in chunks:
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"}).encode()
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
    results = {}

    for ticker, meta in base.FUNDS.items():
        cur = base.get_ishares(ticker, meta)
        one_day = parse_1d_nav_change(meta)
        if one_day is not None:
            cur["nav_change_pct"] = one_day
        hist = list(state["history"].get(ticker, []))
        flow = base.compute_flow(cur, hist)
        cur["flow_usd"] = flow
        hist = base.upsert_history(hist, cur, flow)
        state["history"][ticker] = hist
        cur["flow_5d_usd"] = base.last_n_flows(hist, 5)
        results[ticker] = cur

    flow_head, flow_reason = flow_classification(results, curve)
    regime, regime_easy, s210, s1030 = curve_regime(curve, curve_prev)
    d2, d10, d30 = bp(curve, curve_prev, "2Y"), bp(curve, curve_prev, "10Y"), bp(curve, curve_prev, "30Y")
    gap30 = (5.30 - curve["30Y"]) * 100 if curve.get("30Y") is not None else None

    lines = [
        "[미 국채 ETF Fund Flow — 방향성·수익률곡선 일일 보고]",
        f"조회시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"환율: 1달러={fx['rate']:,.2f}원 | 기준 {fx.get('date') or '최신'}",
        "",
        "[한눈에 보기]",
        f"ETF 자금 방향: {flow_head}",
        f"→ {flow_reason}",
        f"금리 구조: {regime}",
        f"→ {regime_easy}",
        "",
    ]

    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        flow = r.get("flow_usd")
        flow5 = r.get("flow_5d_usd")
        p = r.get("nav_change_pct")
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
    lines.extend([
        f"• 30년 5.30% 경계: {'위험구간 진입' if curve['30Y'] >= 5.30 else f'아직 {gap30:.0f}bp 아래'}",
        "",
        "[수익률곡선 해석]",
        f"• 현재 형태: {regime}",
        f"• 쉬운 해석: {regime_easy}",
        "• 베어 플래트닝 = 금리는 오르는데 단기금리가 더 많이 상승 → Fed 재인상·고금리 장기화 우려",
        "• 베어 스티프닝 = 금리는 오르는데 장기금리가 더 많이 상승 → 재정·국채공급·인플레 장기 부담",
        "• 불 스티프닝 = 금리는 내리는데 단기금리가 더 많이 하락 → Fed 인하·경기둔화 기대",
        "• 불 플래트닝 = 금리는 내리는데 장기금리가 더 많이 하락 → 장기 성장·물가 기대 약화",
        "",
        "[투자 언어로 번역]",
        f"{regime_easy}.",
        "ETF Fund Flow가 쌓이면 이 금리 움직임과 SHY·IEF·TLT 실제 자금 이동이 같은 방향인지 함께 확인.",
        "",
        "[오늘의 결론]",
        f"금리: {regime} | ETF 자금: {flow_head}",
        f"→ {flow_reason}",
        "",
        "자금흐름 산식: iShares 공식 발행좌수 변화 × 해당일 NAV. 첫 기준점만 있을 때는 방향을 억지로 판정하지 않음.",
        "출처: iShares 공식 SHY·IEF·TLT, U.S. Treasury, 환율 교차자료",
    ])

    text = "\n".join(lines)
    (base.OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")
    username, ids = send_exact(text)
    state["last_delivery"] = {
        "at_kst": now.isoformat(timespec="seconds"),
        "bot_username": username,
        "message_ids": ids,
        "classification": flow_head,
        "curve_regime": regime,
        "treasury_date": curve["date"],
        "format": "directional-curve-readable-v2",
    }
    base.save_state(state)
    print(f"telegram_delivery_confirmed=true bot=@{username} message_ids={ids} flow={flow_head} curve={regime}")


if __name__ == "__main__":
    main()

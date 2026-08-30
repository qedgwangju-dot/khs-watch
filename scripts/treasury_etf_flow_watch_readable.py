#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests

import treasury_etf_flow_watch as base

KST = ZoneInfo("Asia/Seoul")
OUT = base.OUT
DATA = base.DATA


def arrow(value, positive="↑", negative="↓", flat="→"):
    if value is None:
        return "·"
    if value > 0:
        return positive
    if value < 0:
        return negative
    return flat


def flow_word(value):
    if value is None:
        return "기준점 수집 중"
    if value > 0:
        return "순유입"
    if value < 0:
        return "순유출"
    return "중립"


def price_word(value):
    if value is None:
        return "가격 확인불가"
    if value > 0:
        return "가격 상승"
    if value < 0:
        return "가격 하락"
    return "가격 보합"


def flow_momentum(history, current_date, current_flow):
    if current_flow is None:
        return "비교 대기"
    prevs = [x for x in history if x.get("date") and x["date"] < current_date and x.get("flow_usd") is not None]
    if not prevs:
        return "직전 흐름 비교 대기"
    prev = sorted(prevs, key=lambda x: x["date"])[-1]["flow_usd"]
    if current_flow > 0 and prev > 0:
        return "유입 확대" if current_flow > prev else "유입 둔화"
    if current_flow < 0 and prev < 0:
        return "유출 확대" if abs(current_flow) > abs(prev) else "유출 둔화"
    if current_flow > 0 >= prev:
        return "유출→유입 전환"
    if current_flow < 0 <= prev:
        return "유입→유출 전환"
    return "방향 변화 제한"


def etf_interpretation(ticker, price, flow):
    if ticker == "SHY":
        if flow is None:
            return "단기채 선호 판단 대기"
        return "단기채·현금성 선호 강화" if flow > 0 else "단기 피신 수요 약화"
    if ticker == "IEF":
        if flow is None:
            return "중기 듀레이션 판단 대기"
        return "7~10년 듀레이션 수요 회복" if flow > 0 else "10년물 금리하락 베팅 약화"
    if ticker == "TLT":
        if price is None or flow is None:
            return "장기채 확신 판단 대기"
        if price > 0 and flow > 0:
            return "가격·자금 동반 상승 → 장기채 강세 확인"
        if price > 0 and flow < 0:
            return "가격 반등·자금 유출 → 반등 매도/확신 부족"
        if price < 0 and flow > 0:
            return "가격 하락·자금 유입 → 장기채 저가매수"
        if price < 0 and flow < 0:
            return "가격·자금 동반 하락 → 장기채 약세"
        return "장기채 방향 중립"
    return ""


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
    rows = sorted(rows, key=lambda x: x["date"])
    if not rows:
        raise RuntimeError("Treasury yield curve returned no rows")
    return rows[-1], rows[-2] if len(rows) >= 2 else None


def bp_change(cur, prev, key):
    if not prev or cur.get(key) is None or prev.get(key) is None:
        return None
    return (cur[key] - prev[key]) * 100.0


def fmt_bp(value):
    if value is None:
        return "비교불가"
    return f"{arrow(value)} {value:+.0f}bp"


def classify_direction(results, curve):
    shy = results["SHY"].get("flow_usd")
    ief = results["IEF"].get("flow_usd")
    tlt = results["TLT"].get("flow_usd")
    tlt_price = results["TLT"].get("nav_change_pct")
    thirty = curve.get("30Y")

    if thirty is not None and thirty >= 5.30:
        return "장기채 위험 확대", "30년물 5.30% 이상 — 장기 듀레이션 부담이 다시 커지는 구간"
    if ief is not None and tlt is not None and ief > 0 and tlt > 0 and (tlt_price or 0) > 0:
        return "장기채 로테이션 시작", "IEF 순유입 + TLT 가격·자금 동반 상승 — 실제 돈이 장기 듀레이션으로 이동"
    if shy is not None and ief is not None and tlt is not None and shy > 0 and ief <= 0 and tlt <= 0:
        return "단기채 선호·듀레이션 축소", "SHY로 유입되는 반면 IEF·TLT는 이탈 — 금리하락 확신보다 단기 이자 선호"
    if tlt is not None and (tlt_price or 0) > 0 and tlt < 0:
        return "TLT 반등은 아직 미확인", "가격은 올랐지만 자금은 빠짐 — 장기채 신규매수보다 반등 매도 가능성"
    return "중립·방향 확인 대기", "SHY→IEF→TLT 중 뚜렷한 자금 이동이 아직 확인되지 않음"


def send_exact_telegram(text):
    token = (base.os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (base.os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (base.os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("Dedicated Telegram token/chat secrets missing")

    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
        identity = json.loads(response.read().decode("utf-8"))
    actual = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot configured: expected @{expected}, got @{actual or 'unknown'}")

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
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"}).encode("utf-8")
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected message: {result}")
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
        hist_before = list(state["history"].get(ticker, []))
        flow = base.compute_flow(cur, hist_before)
        cur["flow_usd"] = flow
        cur["flow_momentum"] = flow_momentum(hist_before, cur["date"], flow)
        hist_after = base.upsert_history(hist_before, cur, flow)
        state["history"][ticker] = hist_after
        cur["flow_5d_usd"] = base.last_n_flows(hist_after, 5)
        results[ticker] = cur

    headline, headline_reason = classify_direction(results, curve)

    lines = [
        "[미 국채 ETF Fund Flow — 방향성 중심 일일 보고]",
        f"조회시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"환율: 1달러={fx['rate']:,.2f}원 | 기준 {fx.get('date') or '최신'}",
        "",
        "[한눈에 보기]",
        f"오늘의 방향: {headline}",
        f"→ {headline_reason}",
    ]

    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        flow = r["flow_usd"]
        flow5 = r["flow_5d_usd"]
        p = r["nav_change_pct"]
        lines.append(
            f"{ticker} {arrow(flow)} {flow_word(flow)} {base.fmt_usd_flow(flow)} "
            f"({base.fmt_krw(flow, fx['rate'])}) | 5회 {arrow(flow5)} {base.fmt_usd_flow(flow5)}"
        )
    lines.append("")

    lines.append("[ETF별 상세 해석]")
    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        flow = r["flow_usd"]
        flow5 = r["flow_5d_usd"]
        p = r["nav_change_pct"]
        price = "확인불가" if p is None else f"{arrow(p)} {p:+.2f}%"
        sec = "확인불가" if r["sec_yield"] is None else f"{r['sec_yield']:.2f}%"
        lines.extend([
            f"{ticker} ({r['label']}) — {r['date']}",
            f"• 가격: NAV ${r['nav']:.2f} | 1일 {price} | 30일 SEC {sec}",
            f"• 오늘 자금: {arrow(flow)} {flow_word(flow)} {base.fmt_usd_flow(flow)} ({base.fmt_krw(flow, fx['rate'])})",
            f"• 최근 5회: {arrow(flow5)} {base.fmt_usd_flow(flow5)} ({base.fmt_krw(flow5, fx['rate'])})",
            f"• 직전 대비: {r['flow_momentum']}",
            f"• 해석: {etf_interpretation(ticker, p, flow)}",
            f"• 발행좌수: {r['shares']:,.0f}",
            "",
        ])

    d2 = bp_change(curve, curve_prev, "2Y")
    d10 = bp_change(curve, curve_prev, "10Y")
    d30 = bp_change(curve, curve_prev, "30Y")
    gap30 = (5.30 - curve["30Y"]) * 100.0 if curve.get("30Y") is not None else None

    lines.extend([
        "[미 국채 금리 방향]",
        f"기준: {curve['date']} | 직전: {curve_prev['date'] if curve_prev else '없음'}",
        f"• 2년: {curve['2Y']:.2f}% | {fmt_bp(d2)}",
        f"• 10년: {curve['10Y']:.2f}% | {fmt_bp(d10)}",
        f"• 30년: {curve['30Y']:.2f}% | {fmt_bp(d30)}",
        f"• 30년 5.30% 경계: {'위험구간 진입' if curve['30Y'] >= 5.30 else f'아직 {gap30:.0f}bp 아래'}",
        "",
        "[방향성 판독]",
        "• SHY 유입↑ + IEF/TLT 유출↓ → 단기채 피신·듀레이션 축소",
        "• SHY 유입 둔화 + IEF 유입 전환 → 금리하락 베팅이 중기물로 이동",
        "• IEF 유입 + TLT 가격↑·자금↑ → 장기채 로테이션 확인",
        "• TLT 가격↑·자금↓ → 반등은 나왔지만 신규 장기자금 확신 부족",
        "• 30년물 5.30% 재돌파 → 장기채·고밸류 성장주 할인율 부담 확대",
        "",
        "[오늘의 결론]",
        f"{headline}: {headline_reason}",
        "",
        "자금흐름 산식: iShares 공식 발행좌수 변화 × 해당일 NAV. 유료 벤더 Fund Flow와 집계시점 차이가 있을 수 있음.",
        "출처: iShares 공식 SHY·IEF·TLT, U.S. Treasury, 환율 교차자료",
    ])

    text = "\n".join(lines)
    (OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")

    username, ids = send_exact_telegram(text)
    state["last_delivery"] = {
        "at_kst": now.isoformat(timespec="seconds"),
        "bot_username": username,
        "message_ids": ids,
        "classification": headline,
        "treasury_date": curve["date"],
        "format": "directional-readable-v1",
    }
    base.save_state(state)
    print(f"telegram_delivery_confirmed=true bot=@{username} message_ids={ids} classification={headline}")


if __name__ == "__main__":
    main()

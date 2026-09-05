#!/usr/bin/env python3
import datetime as dt
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "treasury_etf_flow_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
DATA.parent.mkdir(exist_ok=True)

FUNDS = {
    "SHY": {
        "label": "1~3년",
        "url": "https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf",
    },
    "IEF": {
        "label": "7~10년",
        "url": "https://www.ishares.com/us/products/239456/ishares-7-10-year-treasury-bond-etf",
    },
    "TLT": {
        "label": "20년 이상",
        "url": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def load_state():
    if not DATA.exists():
        return {"history": {}}
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except Exception:
        return {"history": {}}


def save_state(state):
    DATA.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_date(value):
    return dt.datetime.strptime(value, "%b %d, %Y").date().isoformat()


def money_number(value):
    return float(value.replace(",", ""))


def get_ishares(ticker, meta):
    response = requests.get(meta["url"], headers=HEADERS, timeout=35)
    response.raise_for_status()
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    nav_m = re.search(r"NAV as of ([A-Za-z]{3} \d{1,2}, \d{4}).{0,35}?\$+\s*([0-9,.]+)", text)
    shares_m = re.search(r"Shares Outstanding\s+([0-9,]+(?:\.\d+)?)\s+as of\s+([A-Za-z]{3} \d{1,2}, \d{4})", text)
    sec_m = re.search(r"30 Day SEC Yield as of [A-Za-z]{3} \d{1,2}, \d{4}\s+([0-9.]+)%", text)
    change_m = re.search(r"1 Day NAV Change as of [A-Za-z]{3} \d{1,2}, \d{4}.{0,110}?\(([-+]?\d+(?:\.\d+)?)%\)", text)
    assets_m = re.search(r"Net Assets of Fund\s+\$([0-9,]+(?:\.\d+)?)\s+as of\s+([A-Za-z]{3} \d{1,2}, \d{4})", text)

    if not nav_m or not shares_m:
        snippet = text[:1200]
        raise RuntimeError(f"{ticker}: iShares NAV/shares parse failed. snippet={snippet}")

    nav_date = parse_date(nav_m.group(1))
    shares_date = parse_date(shares_m.group(2))
    if nav_date != shares_date:
        # Preserve both dates, but use the older date to avoid pretending the flow is same-day exact.
        data_date = min(nav_date, shares_date)
    else:
        data_date = nav_date

    return {
        "ticker": ticker,
        "label": meta["label"],
        "date": data_date,
        "nav_date": nav_date,
        "shares_date": shares_date,
        "nav": money_number(nav_m.group(2)),
        "shares": money_number(shares_m.group(1)),
        "sec_yield": float(sec_m.group(1)) if sec_m else None,
        "nav_change_pct": float(change_m.group(1)) if change_m else None,
        "net_assets": money_number(assets_m.group(1)) if assets_m else None,
        "source": meta["url"],
    }


def get_treasury_curve():
    year = dt.datetime.now(KST).year
    url = (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
        f"?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    )
    r = requests.get(url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns_d = "http://schemas.microsoft.com/ado/2007/08/dataservices"
    rows = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        def val(name):
            node = entry.find(f".//{{{ns_d}}}{name}")
            return None if node is None or node.text in (None, "") else node.text
        date_text = val("NEW_DATE")
        if not date_text:
            continue
        rows.append({
            "date": date_text[:10],
            "2Y": float(val("BC_2YEAR")) if val("BC_2YEAR") else None,
            "10Y": float(val("BC_10YEAR")) if val("BC_10YEAR") else None,
            "30Y": float(val("BC_30YEAR")) if val("BC_30YEAR") else None,
        })
    if not rows:
        raise RuntimeError("Treasury yield curve returned no rows")
    return sorted(rows, key=lambda x: x["date"])[-1]


def get_usdkrw():
    from fx_api import daily_krw
    q = daily_krw()
    return {"rate": q.rate, "date": q.basis, "source": q.source}


def previous_snapshot(history, date):
    candidates = [x for x in history if x.get("date") and x["date"] < date]
    return sorted(candidates, key=lambda x: x["date"])[-1] if candidates else None


def compute_flow(current, history):
    prev = previous_snapshot(history, current["date"])
    if not prev:
        return None
    delta_shares = current["shares"] - float(prev["shares"])
    return delta_shares * current["nav"]


def upsert_history(history, current, flow_usd):
    row = dict(current)
    row["flow_usd"] = flow_usd
    history = [x for x in history if x.get("date") != current["date"]]
    history.append(row)
    history = sorted(history, key=lambda x: x["date"])
    return history[-45:]


def last_n_flows(history, n=5):
    vals = [x.get("flow_usd") for x in sorted(history, key=lambda x: x.get("date", "")) if x.get("flow_usd") is not None]
    return sum(vals[-n:]) if vals else None


def fmt_usd_flow(value):
    if value is None:
        return "기준점 수집 중"
    sign = "+" if value > 0 else "" if value < 0 else "±"
    av = abs(value)
    if av >= 1_000_000_000:
        return f"{sign}${value/1_000_000_000:,.2f}B"
    if av >= 1_000_000:
        return f"{sign}${value/1_000_000:,.1f}M"
    return f"{sign}${value:,.0f}"


def fmt_krw(value, fx):
    if value is None:
        return "-"
    krw = value * fx
    sign = "+" if krw > 0 else "-" if krw < 0 else "±"
    av = abs(krw)
    if av >= 1e12:
        return f"{sign}{av/1e12:,.2f}조원"
    if av >= 1e8:
        return f"{sign}{av/1e8:,.0f}억원"
    return f"{sign}{av:,.0f}원"


def sign_value(v):
    if v is None:
        return 0
    return 1 if v > 0 else -1 if v < 0 else 0


def classify(results, curve):
    flows = {k: v.get("flow_usd") for k, v in results.items()}
    tlt_price = results["TLT"].get("nav_change_pct")
    thirty = curve.get("30Y")

    if thirty is not None and thirty >= 5.30:
        headline = "장기채 위험 확대"
    elif sign_value(flows["IEF"]) > 0 and sign_value(flows["TLT"]) > 0 and (tlt_price or 0) > 0:
        headline = "장기채 로테이션 시작"
    elif sign_value(flows["SHY"]) > 0 and sign_value(flows["IEF"]) <= 0 and sign_value(flows["TLT"]) <= 0:
        headline = "단기채 선호·듀레이션 축소"
    elif (tlt_price or 0) > 0 and sign_value(flows["TLT"]) < 0:
        headline = "TLT 반등 중 자금유출—확신 부족"
    else:
        headline = "중립·로테이션 확인 대기"

    notes = []
    if sign_value(flows["SHY"]) > 0:
        notes.append("SHY 순유입: 짧은 만기 선호")
    if sign_value(flows["IEF"]) > 0:
        notes.append("IEF 순유입: 7~10년 듀레이션 수요 회복")
    elif sign_value(flows["IEF"]) < 0:
        notes.append("IEF 순유출: 10년물 금리하락 확신 약함")
    if (tlt_price or 0) > 0 and sign_value(flows["TLT"]) > 0:
        notes.append("TLT 가격·자금 동반 상승: 장기채 강세 확인")
    elif (tlt_price or 0) > 0 and sign_value(flows["TLT"]) < 0:
        notes.append("TLT 가격은 반등했지만 자금은 유출: 반등 매도 가능성")
    if thirty is not None:
        notes.append(f"30년물 {thirty:.2f}%: {'5.30% 이상 위험구간' if thirty >= 5.30 else '5.30% 아래'}")
    return headline, notes


def send_telegram(text):
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("YEN_CARRY_TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("YEN_CARRY_TELEGRAM_CHAT_ID") or os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        raise RuntimeError("Telegram secret missing: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID (or existing fallback secrets)")

    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
        identity = json.loads(response.read().decode("utf-8"))
    if not identity.get("ok"):
        raise RuntimeError(f"Telegram getMe failed: {identity}")
    username = str((identity.get("result") or {}).get("username") or "")

    chunks = []
    current = ""
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
    return username, ids


def main():
    state = load_state()
    state.setdefault("history", {})
    now = dt.datetime.now(KST)
    fx = get_usdkrw()
    curve = get_treasury_curve()
    results = {}
    same_dates = True

    for ticker, meta in FUNDS.items():
        cur = get_ishares(ticker, meta)
        hist = state["history"].get(ticker, [])
        flow = compute_flow(cur, hist)
        prev = previous_snapshot(hist, cur["date"])
        if prev is None or prev.get("date") != cur.get("date"):
            same_dates = False
        cur["flow_usd"] = flow
        hist = upsert_history(hist, cur, flow)
        state["history"][ticker] = hist
        cur["flow_5d_usd"] = last_n_flows(hist, 5)
        results[ticker] = cur

    headline, notes = classify(results, curve)
    lines = [
        "[미 국채 ETF Fund Flow 일일 감시]",
        f"조회시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"USD/KRW: {fx['rate']:,.2f}원 ({fx['source']}, 기준 {fx.get('date') or '최신'})",
        "",
    ]

    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        price = "확인불가" if r["nav_change_pct"] is None else f"{r['nav_change_pct']:+.2f}%"
        sec = "확인불가" if r["sec_yield"] is None else f"{r['sec_yield']:.2f}%"
        flow = r["flow_usd"]
        flow5 = r["flow_5d_usd"]
        lines.append(f"{ticker} ({r['label']}) — 기준 {r['date']}")
        lines.append(f"• NAV ${r['nav']:.2f} | 1일 {price} | 30일 SEC {sec}")
        lines.append(f"• 일간 생성/환매 추정: {fmt_usd_flow(flow)} ({fmt_krw(flow, fx['rate'])})")
        lines.append(f"• 최근 5회 누적: {fmt_usd_flow(flow5)} ({fmt_krw(flow5, fx['rate'])})")
        lines.append(f"• 발행좌수: {r['shares']:,.0f}")
        lines.append("")

    lines.extend([
        f"미 재무부 공식 수익률곡선 — {curve['date']}",
        f"• 2년 {curve['2Y']:.2f}% | 10년 {curve['10Y']:.2f}% | 30년 {curve['30Y']:.2f}%",
        f"• 30년물 5.30%: {'재돌파/이상' if curve['30Y'] >= 5.30 else '아래'}",
        "",
        f"오늘의 판정: {headline}",
    ])
    for note in notes:
        lines.append(f"• {note}")
    lines.extend([
        "",
        "판정 기준",
        "• SHY 유입↑ + IEF/TLT 유출 = 듀레이션 축소·단기채 선호",
        "• IEF 유입 전환 + TLT 가격·자금 동반 상승 = 장기채 로테이션 확인",
        "• TLT 가격↑인데 자금↓ = 반등 매도/확신 부족 가능성",
        "",
        "자금흐름 산식: iShares 공식 발행좌수 변화 × 해당일 NAV. Bloomberg 등 유료 벤더의 Fund Flow와 집계시점 차이로 숫자가 완전히 같지 않을 수 있음.",
        "출처: iShares 공식 SHY·IEF·TLT, U.S. Treasury, 환율 교차자료",
    ])

    text = "\n".join(lines)
    (OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")

    username, ids = send_telegram(text)
    state["last_delivery"] = {
        "at_kst": now.isoformat(timespec="seconds"),
        "bot_username": username,
        "message_ids": ids,
        "classification": headline,
        "treasury_date": curve["date"],
    }
    save_state(state)
    print(f"telegram_delivery_confirmed=true bot=@{username} message_ids={ids} classification={headline}")


if __name__ == "__main__":
    main()

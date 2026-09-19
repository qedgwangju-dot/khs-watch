#!/usr/bin/env python3
import os, re, json, hashlib, html
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

STATE = DATA / "us_positioning_options_sox_state.json"
ALERT = OUT / "us_positioning_options_sox_alert.html"
STATUS = OUT / "us_positioning_options_sox_status.md"
PENDING = OUT / "us_positioning_options_sox_pending_state.json"

for p in (ALERT, STATUS, PENDING):
    try:
        p.unlink()
    except FileNotFoundError:
        pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

CFTC_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CBOE_DAILY = "https://www.cboe.com/us/options/market_statistics/daily/"
SOX_URL = "https://indexes.nasdaq.com/Index/History/SOX"

CONTRACTS = {
    "nasdaq100": {"code": "209742", "label": "Nasdaq-100 E-mini"},
    "sp500": {"code": "13874A", "label": "S&P 500 E-mini"},
}


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "history": {"sox": []}, "values": {}}


def n(v):
    if v is None or v == "":
        return None
    return float(str(v).replace(",", ""))


def pct_rank(values, current):
    vals = [float(x) for x in values if x is not None]
    if not vals:
        return None
    return 100.0 * sum(x <= current for x in vals) / len(vals)


def fmt_int(x):
    return f"{int(round(x)):,}"


def fmt_signed_int(x):
    return f"{int(round(x)):+,}"


def fmt_pct(x, digits=0):
    if x is None:
        return "확인 불가"
    return f"{x:.{digits}f}%"


def browser_html(url):
    exe = next(
        (p for p in [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ] if os.path.exists(p)),
        None,
    )
    if not exe:
        raise RuntimeError("Chrome/Chromium not found")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=exe,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(user_agent=UA, locale="en-US")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(800)
        out = page.content()
        browser.close()
        return out


def fetch_cftc_contract(code):
    params = {
        "$limit": "70",
        "$where": f"cftc_contract_market_code='{code}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
    }
    r = S.get(CFTC_URL, params=params, timeout=40)
    r.raise_for_status()
    rows = r.json()
    if len(rows) < 2:
        raise RuntimeError(f"CFTC {code}: insufficient rows")

    parsed = []
    for row in rows:
        try:
            dt = str(row["report_date_as_yyyy_mm_dd"])[:10]
            oi = n(row.get("open_interest_all"))
            am_l = n(row.get("asset_mgr_positions_long"))
            am_s = n(row.get("asset_mgr_positions_short"))
            lev_l = n(row.get("lev_money_positions_long"))
            lev_s = n(row.get("lev_money_positions_short"))
            if None in (oi, am_l, am_s, lev_l, lev_s):
                continue
            am_net = am_l - am_s
            lev_net = lev_l - lev_s
            parsed.append({
                "date": dt,
                "oi": oi,
                "asset_long": am_l,
                "asset_short": am_s,
                "asset_net": am_net,
                "asset_net_oi": am_net / oi * 100.0,
                "lev_long": lev_l,
                "lev_short": lev_s,
                "lev_net": lev_net,
                "lev_net_oi": lev_net / oi * 100.0,
            })
        except Exception:
            continue
    if len(parsed) < 2:
        raise RuntimeError(f"CFTC {code}: malformed rows")

    cur, prev = parsed[0], parsed[1]
    last52 = parsed[:52]
    cur["asset_net_change"] = cur["asset_net"] - prev["asset_net"]
    cur["lev_net_change"] = cur["lev_net"] - prev["lev_net"]
    cur["asset_pctile_52w"] = pct_rank([x["asset_net_oi"] for x in last52], cur["asset_net_oi"])
    cur["lev_pctile_52w"] = pct_rank([x["lev_net_oi"] for x in last52], cur["lev_net_oi"])
    return cur


def parse_cboe_text(text, d):
    ratios = {}
    pats = {
        "total": r"TOTAL PUT/CALL RATIO\\s+([0-9]+(?:\\.[0-9]+)?)",
        "index": r"INDEX PUT/CALL RATIO\\s+([0-9]+(?:\\.[0-9]+)?)",
        "equity": r"EQUITY PUT/CALL RATIO\\s+([0-9]+(?:\\.[0-9]+)?)",
    }
    for key, pat in pats.items():
        m = re.search(pat, text, re.I)
        if m:
            ratios[key] = float(m.group(1))
    if len(ratios) != 3:
        return None
    return {
        "date": d.isoformat(),
        **ratios,
        "url": "https://www.cboe.com/markets/us/options/market-statistics/daily?dt=" + d.isoformat(),
    }


def fetch_cboe_history():
    exe = next(
        (p for p in [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ] if os.path.exists(p)),
        None,
    )
    if not exe:
        raise RuntimeError("Chrome/Chromium not found for Cboe")

    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    dates = []
    for back in range(0, 42):
        d = today_et - timedelta(days=back)
        if d.weekday() < 5:
            dates.append(d)
        if len(dates) >= 26:
            break

    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=exe,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(user_agent=UA, locale="en-US")
        for d in dates:
            url = "https://www.cboe.com/markets/us/options/market-statistics/daily?dt=" + d.isoformat()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(350)
                text = re.sub(r"\\s+", " ", page.locator("body").inner_text(timeout=10000))
                row = parse_cboe_text(text, d)
                if row:
                    rows.append(row)
            except Exception:
                continue
            if len(rows) >= 20:
                break
        browser.close()

    if len(rows) < 5:
        raise RuntimeError(f"Cboe daily ratio rows unavailable: {len(rows)}")

    rows.sort(key=lambda x: x["date"], reverse=True)
    cur = dict(rows[0])
    hist = rows[:20]
    for key in ("total", "index", "equity"):
        vals5 = [x[key] for x in hist[:5]]
        vals20 = [x[key] for x in hist[:20]]
        cur[key + "_avg5"] = sum(vals5) / len(vals5)
        cur[key + "_avg20"] = sum(vals20) / len(vals20)
        cur[key + "_pctile20"] = pct_rank(vals20, cur[key])
    cur["history_count"] = len(hist)
    return cur


def fetch_sox():
    raw = browser_html(SOX_URL)
    text = re.sub(r"\s+", " ", BeautifulSoup(raw, "html.parser").get_text(" ", strip=True))
    m = re.search(
        r"DATA AS OF\s+(\d{1,2}/\d{1,2}/20\d{2})\s+([\d,]+\.\d+)\s+([-+\d,]+\.\d+)\s+([-+\d.]+)%",
        text,
        re.I,
    )
    if not m:
        raise RuntimeError("Nasdaq SOX current value not found")
    dt = datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
    value = float(m.group(2).replace(",", ""))
    change = float(m.group(3).replace(",", ""))
    pct = float(m.group(4))
    # History page occasionally has a stale percent field; recompute from absolute change.
    prev = value - change
    calc_pct = (change / prev * 100.0) if prev else pct
    return {
        "date": dt,
        "value": value,
        "change": change,
        "pct": calc_pct,
        "high": None,
        "low": None,
        "url": SOX_URL,
    }


def update_sox_history(state, sox):
    hist = list((state.get("history") or {}).get("sox") or [])
    hist = [x for x in hist if x.get("date") != sox["date"]]
    hist.append({"date": sox["date"], "value": sox["value"], "pct": sox["pct"]})
    hist.sort(key=lambda x: x["date"], reverse=True)
    return hist[:20]


def signal_text(sox, cboe, cftc_ndx, sox_hist):
    pieces = []
    sox_up = sox["pct"] > 0
    prev_sox = next((x for x in sox_hist if x["date"] < sox["date"]), None)
    follow = sox_up and prev_sox is not None and prev_sox.get("pct", 0) > 0

    eq_call_heavy = cboe["equity_pctile20"] <= 30 if cboe.get("equity_pctile20") is not None else False
    idx_hedged = cboe["index_pctile20"] >= 70 if cboe.get("index_pctile20") is not None else False
    lev_buy = cftc_ndx["lev_net_change"] > 0
    asset_buy = cftc_ndx["asset_net_change"] > 0

    if follow:
        pieces.append("SOX가 이틀 연속 상승해 만기 하루짜리 반등보다 후속 강세 쪽")
    elif sox_up:
        pieces.append("SOX는 상승했지만 연속 상승 확인은 아직 부족")
    else:
        pieces.append("SOX가 하락해 가격 확인은 약화")

    if eq_call_heavy and not idx_hedged:
        pieces.append("주식옵션은 콜 우위가 강하고 지수 헤지도 과도하지 않아 상방 수요 강화")
    elif eq_call_heavy and idx_hedged:
        pieces.append("개별주 콜 수요는 강하지만 지수 옵션에서는 헤지도 높아 낙관 일변도는 아님")
    elif idx_hedged:
        pieces.append("지수 옵션 헤지 수요가 높아 기관 경계감이 남아 있음")
    else:
        pieces.append("옵션 수급은 극단적 상방·하방 어느 쪽도 아님")

    if lev_buy and asset_buy:
        pieces.append("CFTC에서 헤지펀드와 자산운용사가 모두 Nasdaq-100 방향을 매수 쪽으로 이동")
    elif lev_buy:
        pieces.append("CFTC 레버리지드펀드는 Nasdaq-100 매수 쪽으로 이동했지만 자산운용사는 동행하지 않음")
    elif asset_buy:
        pieces.append("자산운용사는 Nasdaq-100 매수 쪽이지만 레버리지드펀드는 아직 동행하지 않음")
    else:
        pieces.append("CFTC에서 헤지펀드·자산운용사 모두 추가 매수 확인이 약함")

    score = sum([follow, eq_call_heavy, lev_buy, asset_buy]) - (1 if idx_hedged else 0)
    if score >= 3:
        headline = "상방 추격 신호 강화"
    elif score >= 1:
        headline = "상방 신호 일부 확인"
    else:
        headline = "상방 추격 확인 부족"
    return headline, pieces


def cftc_block(label, x):
    lev_bias = "순롱" if x["lev_net"] >= 0 else "순숏"
    asset_bias = "순롱" if x["asset_net"] >= 0 else "순숏"
    return [
        f"• {label} 레버리지드펀드: {lev_bias} {fmt_int(abs(x['lev_net']))}계약 / 주간 {fmt_signed_int(x['lev_net_change'])}계약 / OI 대비 {x['lev_net_oi']:+.1f}% / 1년 {fmt_pct(x['lev_pctile_52w'])} 백분위",
        f"• {label} 자산운용사·기관: {asset_bias} {fmt_int(abs(x['asset_net']))}계약 / 주간 {fmt_signed_int(x['asset_net_change'])}계약 / OI 대비 {x['asset_net_oi']:+.1f}% / 1년 {fmt_pct(x['asset_pctile_52w'])} 백분위",
    ]


state = load_state()
errors = []
values = {}

for key, fn in [
    ("cftc_nasdaq100", lambda: fetch_cftc_contract(CONTRACTS["nasdaq100"]["code"])),
    ("cftc_sp500", lambda: fetch_cftc_contract(CONTRACTS["sp500"]["code"])),
    ("cboe", fetch_cboe_history),
    ("sox", fetch_sox),
]:
    try:
        values[key] = fn()
    except Exception as e:
        errors.append(f"{key}: {type(e).__name__}: {e}")

required = ("cftc_nasdaq100", "cftc_sp500", "cboe", "sox")
if not all(k in values for k in required):
    STATUS.write_text(
        "# US Positioning Options SOX Watch\n\n- status: PARTIAL\n" +
        "\n".join(f"- {e}" for e in errors) + "\n",
        encoding="utf-8",
    )
    print("us_positioning_options_sox_alert_ready=false partial=true")
    raise SystemExit(0)

sox_hist = update_sox_history(state, values["sox"])
headline, details = signal_text(values["sox"], values["cboe"], values["cftc_nasdaq100"], sox_hist)

semantic = {
    "cftc_nasdaq100": {k: values["cftc_nasdaq100"][k] for k in ("date","asset_net","asset_net_change","lev_net","lev_net_change")},
    "cftc_sp500": {k: values["cftc_sp500"][k] for k in ("date","asset_net","asset_net_change","lev_net","lev_net_change")},
    "cboe": {k: values["cboe"][k] for k in ("date","total","index","equity")},
    "sox": {k: values["sox"][k] for k in ("date","value","pct")},
}
fp = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
old_fp = (state.get("seen") or {}).get("fingerprint")
changed = fp != old_fp
force = (os.getenv("FORCE_SEND") or "").lower() in ("1","true","yes")

cboe = values["cboe"]
sox = values["sox"]
ndx = values["cftc_nasdaq100"]
spx = values["cftc_sp500"]

body = [
    f"📡 <b>[미국 상방 추격 신호 | {html.escape(headline)}]</b>",
    "",
    "<b>한눈에 보기</b>",
    f"• SOX 반도체: {sox['value']:,.2f} / {sox['pct']:+.2f}% → {'가격 강세' if sox['pct'] > 0 else '가격 약세'}",
    f"• Cboe 주식옵션 P/C: {cboe['equity']:.2f} / 20일 {cboe['equity_avg20']:.2f} / 20일 {fmt_pct(cboe['equity_pctile20'])} 백분위",
    f"• Cboe 지수옵션 P/C: {cboe['index']:.2f} / 20일 {cboe['index_avg20']:.2f} / 20일 {fmt_pct(cboe['index_pctile20'])} 백분위",
    f"• Nasdaq-100 헤지펀드 주간 포지션 변화: {fmt_signed_int(ndx['lev_net_change'])}계약",
    f"• Nasdaq-100 자산운용사·기관 주간 포지션 변화: {fmt_signed_int(ndx['asset_net_change'])}계약",
    "",
    "<b>현재 판정</b>",
]
for d in details:
    body.append("• " + html.escape(d))

body += [
    "",
    "<b>CFTC 기관·헤지펀드 포지션</b>",
]
body += cftc_block("Nasdaq-100", ndx)
body += cftc_block("S&P 500", spx)

body += [
    "",
    "<b>옵션 수급</b>",
    f"• 주식옵션 P/C {cboe['equity']:.2f} → {'콜 우위가 강한 편' if cboe['equity_pctile20'] <= 30 else '중립권' if cboe['equity_pctile20'] < 70 else '풋 우위가 강한 편'}",
    f"• 지수옵션 P/C {cboe['index']:.2f} → {'기관 헤지 수요 높은 편' if cboe['index_pctile20'] >= 70 else '중립권' if cboe['index_pctile20'] > 30 else '지수 헤지 수요 낮은 편'}",
    f"• 총 P/C {cboe['total']:.2f} / 5일 평균 {cboe['total_avg5']:.2f} / 20일 평균 {cboe['total_avg20']:.2f}",
    "",
    "<b>SOX 확인</b>",
    f"• 기준일 {sox['date']} / {sox['value']:,.2f} / 일간 {sox['pct']:+.2f}%",
]
prev_sox = next((x for x in sox_hist if x["date"] < sox["date"]), None)
if prev_sox:
    body.append(f"• 직전 거래일 {prev_sox['date']} {prev_sox['pct']:+.2f}% → {'2거래일 연속 상승' if sox['pct'] > 0 and prev_sox['pct'] > 0 else '연속 상승 아님'}")
else:
    body.append("• 직전 거래일 비교: 첫 기준값 적립 중")

body += [
    "",
    "<b>해석 원칙</b>",
    "• SOX 가격 + Cboe 옵션 수급 + CFTC 실제 포지션이 같은 방향일 때만 상방 추격 신호를 강하게 판정",
    "• 낮은 주식옵션 P/C는 콜 거래 우위 신호지만 단독으로 매수 확정 신호로 보지 않음",
    "• 높은 지수옵션 P/C는 기관 헤지 수요로 해석하되 주식옵션과 분리",
    "• CFTC는 매주 금요일 공개되는 직전 화요일 기준 포지션이라 일간 시장보다 느린 지표",
    "• 계약 수·비율·지수 포인트는 달러 금액이 아니므로 원화 환산 대상이 아님",
    "",
    f'• 원천: <a href="https://publicreporting.cftc.gov/stories/s/TFF-Futures-Only/98ig-3k9y/">CFTC TFF</a> · <a href="{html.escape(cboe["url"], quote=True)}">Cboe</a> · <a href="{SOX_URL}">Nasdaq SOX</a>',
]

STATUS.write_text(
    "# US Positioning Options SOX Watch\n\n" +
    f"- fingerprint: {fp}\n- prior: {old_fp}\n- changed: {changed}\n- headline: {headline}\n" +
    f"- cftc_ndx: {ndx['date']}\n- cftc_spx: {spx['date']}\n- cboe: {cboe['date']}\n- sox: {sox['date']}\n" +
    ("\n".join(f"- error: {e}" for e in errors) + "\n" if errors else ""),
    encoding="utf-8",
)

if changed or force:
    ALERT.write_text("\n".join(body) + "\n", encoding="utf-8")
    next_state = {
        "seen": {"fingerprint": fp},
        "values": values,
        "history": {"sox": sox_hist},
        "last_headline": headline,
        "updated_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
    }
    PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"us_positioning_options_sox_alert_ready=true headline={headline}")
else:
    print("us_positioning_options_sox_alert_ready=false unchanged=true")

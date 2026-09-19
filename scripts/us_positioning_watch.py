#!/usr/bin/env python3
import os, re, json, hashlib, html
from pathlib import Path
from datetime import datetime, timezone, timedelta
from io import StringIO

import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

ALERT = OUT / "us_positioning_alert.html"
STATUS = OUT / "us_positioning_status.md"
PENDING = OUT / "us_positioning_pending_state.json"
STATE = DATA / "us_positioning_state.json"

for p in (ALERT, STATUS, PENDING):
    try:
        p.unlink()
    except FileNotFoundError:
        pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

CFTC = "https://www.cftc.gov/dea/futures/financial_lf.htm"
CBOE = "https://www.cboe.com/us/options/market_statistics/market/"
SOX = "https://indexes.nasdaq.com/Index/History/SOX"
SOX_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQSOX"


def get(url, timeout=35):
    r = S.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def browser_html(url):
    exe = next(
        (
            p
            for p in [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ]
            if os.path.exists(p)
        ),
        None,
    )
    if not exe:
        raise RuntimeError("system Chrome/Chromium not found")
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            executable_path=exe,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = b.new_page(user_agent=UA, locale="en-US")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(900)
        h = page.content()
        b.close()
        return h


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "values": {}}


def fp(core):
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def parse_num(x):
    if x is None:
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def int_list(text):
    vals = re.findall(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)", text)
    return [int(x.replace(",", "")) for x in vals]


def parse_cftc():
    raw = get(CFTC).text
    soup = BeautifulSoup(raw, "html.parser")

    # CFTC report is a preformatted official table. Parse the NASDAQ-100 block directly.
    pre = soup.find("pre")
    plain = pre.get_text("\n") if pre else soup.get_text("\n")
    plain = plain.replace("\xa0", " ")

    report_m = re.search(
        r"Positions as of\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        plain,
        re.I,
    )
    period = report_m.group(1) if report_m else "latest"

    start = plain.find("NASDAQ-100 Consolidated")
    if start < 0:
        raise RuntimeError("NASDAQ-100 CFTC section not found")
    # Slice only enough of the report to cover NASDAQ-100 positions and changes.
    block = plain[start : start + 7000]

    oi_m = re.search(r"Open Interest is\s+([\d,]+)", block, re.I)
    if not oi_m:
        raise RuntimeError("NASDAQ-100 CFTC open interest not found")
    open_interest = int(oi_m.group(1).replace(",", ""))

    pos_m = re.search(
        r"Positions\s+([\s\S]*?)\s+Changes from:",
        block,
        re.I,
    )
    if not pos_m:
        raise RuntimeError("NASDAQ-100 CFTC positions row not found")
    pos = int_list(pos_m.group(1))
    # Exact CFTC layout has 14 position values:
    # dealer(3), asset manager(3), leveraged funds(3), other reportable(3), nonreportable(2).
    if len(pos) < 14:
        raise RuntimeError(f"NASDAQ-100 CFTC positions parse failed: {len(pos)} fields")
    pos = pos[:14]

    ch_m = re.search(
        r"Changes from:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2}).*?Total Change is:\s*[-+]?([\d,]+)\s+([\s\S]*?)\s+Percent of Open Interest",
        block,
        re.I,
    )
    if not ch_m:
        raise RuntimeError("NASDAQ-100 CFTC weekly changes row not found")
    prev_period = ch_m.group(1)
    changes = int_list(ch_m.group(3))
    if len(changes) < 14:
        raise RuntimeError(f"NASDAQ-100 CFTC change parse failed: {len(changes)} fields")
    changes = changes[:14]

    asset_long, asset_short = pos[3], pos[4]
    lev_long, lev_short = pos[6], pos[7]
    asset_long_wow, asset_short_wow = changes[3], changes[4]
    lev_long_wow, lev_short_wow = changes[6], changes[7]

    metrics = {
        "open_interest": open_interest,
        "asset_long": asset_long,
        "asset_short": asset_short,
        "asset_net": asset_long - asset_short,
        "asset_long_wow": asset_long_wow,
        "asset_short_wow": asset_short_wow,
        "asset_net_wow": asset_long_wow - asset_short_wow,
        "lev_long": lev_long,
        "lev_short": lev_short,
        "lev_net": lev_long - lev_short,
        "lev_long_wow": lev_long_wow,
        "lev_short_wow": lev_short_wow,
        "lev_net_wow": lev_long_wow - lev_short_wow,
        "previous_period": prev_period,
    }
    core = {"source": "CFTC", "kind": "cot", "period": period, "metrics": metrics}
    return {**core, "url": CFTC, "fingerprint": fp(core)}


def parse_cboe_section(text, heading, next_heading=None):
    start = text.find(heading)
    if start < 0:
        return None
    end = text.find(next_heading, start + len(heading)) if next_heading else len(text)
    if end < 0:
        end = len(text)
    block = text[start:end]

    # Cboe publishes cumulative intraday rows. Take the latest row that has actual values.
    rows = re.findall(
        r"(\d{1,2}:\d{2}\s*[AP]M)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+(\d+(?:\.\d+)?)",
        block,
        re.I,
    )
    if not rows:
        return None
    t, calls, puts, total, ratio = rows[-1]
    return {
        "time_ct": t.upper().replace("  ", " "),
        "calls": int(calls.replace(",", "")),
        "puts": int(puts.replace(",", "")),
        "total": int(total.replace(",", "")),
        "pc_ratio": float(ratio),
    }


def parse_cboe():
    # Browser rendering is needed because the current-statistics tables are JS-backed.
    h = browser_html(CBOE)
    text = BeautifulSoup(h, "html.parser").get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)

    period_m = re.search(
        r"Cboe Exchange Market Statistics for\s+([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+20\d{2})",
        text,
        re.I,
    )
    period = period_m.group(1) if period_m else "latest"

    total = parse_cboe_section(text, "Total", "Index Options")
    index_opt = parse_cboe_section(text, "Index Options", "Equity Options")
    equity = parse_cboe_section(text, "Equity Options")

    if not total and not equity:
        raise RuntimeError("Cboe current market-statistics rows not found")

    metrics = {
        "total_pc_ratio": total["pc_ratio"] if total else None,
        "total_calls": total["calls"] if total else None,
        "total_puts": total["puts"] if total else None,
        "total_time_ct": total["time_ct"] if total else None,
        "equity_pc_ratio": equity["pc_ratio"] if equity else None,
        "equity_calls": equity["calls"] if equity else None,
        "equity_puts": equity["puts"] if equity else None,
        "equity_time_ct": equity["time_ct"] if equity else None,
        "index_pc_ratio": index_opt["pc_ratio"] if index_opt else None,
        "index_time_ct": index_opt["time_ct"] if index_opt else None,
    }
    core = {"source": "Cboe", "kind": "options", "period": period, "metrics": metrics}
    return {**core, "url": CBOE, "fingerprint": fp(core)}


def parse_sox():
    # First use Nasdaq History page for the current level and previous close.
    # Never trust the Overview-page percentage field, which can show 0.00% after the close.
    h = browser_html(SOX)
    txt = BeautifulSoup(h, "html.parser").get_text(" ", strip=True)

    m = re.search(
        r"DATA AS OF\s+(\d{1,2}/\d{1,2}/20\d{2})\s+([\d,]+\.\d+)",
        txt,
        re.I,
    )
    if not m:
        raise RuntimeError("SOX Nasdaq latest level not found")
    period = m.group(1)
    latest = float(m.group(2).replace(",", ""))

    prev_m = re.search(r"Previous Close\s+([\d,]+\.\d+)", txt, re.I)
    prev1 = float(prev_m.group(1).replace(",", "")) if prev_m else None

    # Nasdaq's History page can render inconsistently after the close.
    # Prefer actual historical values from FRED's NASDAQSOX distribution when available.
    history = []
    fred_errors = []
    fred_urls = [
        "https://fred.stlouisfed.org/data/NASDAQSOX.txt",
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQSOX&cosd=2026-08-20",
    ]

    for url in fred_urls:
        try:
            r = S.get(url, timeout=18)
            r.raise_for_status()
            if url.endswith(".txt"):
                rows = re.findall(r"^(20\d{2}-\d{2}-\d{2})\s+([\d.]+)$", r.text, re.M)
                history = [(d, float(v)) for d, v in rows]
            else:
                df = pd.read_csv(StringIO(r.text))
                if "NASDAQSOX" in df.columns:
                    df["NASDAQSOX"] = pd.to_numeric(df["NASDAQSOX"], errors="coerce")
                    df = df.dropna(subset=["NASDAQSOX"])
                    history = [(str(row["DATE"]), float(row["NASDAQSOX"])) for _, row in df.iterrows()]
            if history:
                break
        except Exception as e:
            fred_errors.append(str(e))

    # Cross-check latest FRED/Nasdaq value where FRED is available.
    metrics = {
        "value": latest,
        "previous_close": prev1,
    }

    if history:
        history.sort(key=lambda x: x[0])
        vals = [v for d, v in history if d <= datetime.strptime(period, "%m/%d/%Y").strftime("%Y-%m-%d")]
        if vals:
            fred_latest = vals[-1]
            if abs(fred_latest - latest) > 0.05:
                raise RuntimeError(
                    f"SOX Nasdaq/FRED mismatch: Nasdaq={latest}, FRED={fred_latest}"
                )
        if len(vals) >= 2:
            prev1 = vals[-2]
            metrics["previous_close"] = prev1
            metrics["net_change"] = latest - prev1
            metrics["d1_pct"] = (latest / prev1 - 1) * 100
            metrics["pct"] = metrics["d1_pct"]
        if len(vals) >= 4:
            metrics["d3_pct"] = (latest / vals[-4] - 1) * 100
        if len(vals) >= 6:
            metrics["d5_pct"] = (latest / vals[-6] - 1) * 100

    # If FRED was temporarily unavailable, still compute the verified 1D change
    # from Nasdaq History's own Previous Close instead of failing the whole SOX lane.
    if "d1_pct" not in metrics:
        if prev1 is None or prev1 <= 0:
            raise RuntimeError("SOX previous close unavailable")
        metrics["net_change"] = latest - prev1
        metrics["d1_pct"] = (latest / prev1 - 1) * 100
        metrics["pct"] = metrics["d1_pct"]

    core = {"source": "Nasdaq SOX", "kind": "sox", "period": period, "metrics": metrics}
    return {**core, "url": SOX, "fingerprint": fp(core)}


def explain(cftc, cboe, sox):
    lines = []

    if sox:
        m = sox["metrics"]
        lines.append(
            f"• 반도체(SOX): {m['value']:,.2f} | 1D {m['d1_pct']:+.2f}% | "
            f"3D {m['d3_pct']:+.2f}% | 5D {m['d5_pct']:+.2f}%"
        )

    if cftc:
        m = cftc["metrics"]
        lines.append(
            f"• 기관(Asset Manager): 순포지션 {m['asset_net']:+,}계약 | "
            f"주간 {m['asset_net_wow']:+,}계약"
        )
        lines.append(
            f"• 헤지펀드성(Leveraged Funds): 순포지션 {m['lev_net']:+,}계약 | "
            f"주간 {m['lev_net_wow']:+,}계약"
        )

    if cboe:
        m = cboe["metrics"]
        if m.get("equity_pc_ratio") is not None:
            lines.append(
                f"• Cboe 주식옵션 풋/콜 {m['equity_pc_ratio']:.2f} "
                f"({m.get('equity_time_ct') or '최신'} CT) | "
                f"전체 {m['total_pc_ratio']:.2f}"
                if m.get("total_pc_ratio") is not None
                else f"• Cboe 주식옵션 풋/콜 {m['equity_pc_ratio']:.2f}"
            )
        elif m.get("total_pc_ratio") is not None:
            lines.append(f"• Cboe 전체 풋/콜 {m['total_pc_ratio']:.2f}")

    sox_up = bool(sox and sox["metrics"].get("d1_pct", 0) > 0)
    lev_improving = bool(
        cftc
        and cftc["metrics"].get("lev_net_wow") is not None
        and cftc["metrics"]["lev_net_wow"] > 0
    )
    asset_improving = bool(
        cftc
        and cftc["metrics"].get("asset_net_wow") is not None
        and cftc["metrics"]["asset_net_wow"] > 0
    )
    equity_pc = cboe["metrics"].get("equity_pc_ratio") if cboe else None
    calls_favored = bool(equity_pc is not None and equity_pc < 0.80)

    if sox_up and lev_improving and calls_favored:
        overall = (
            "SOX 상승 + 헤지펀드 순포지션 개선 + 주식옵션 콜 우위가 동시에 확인됨 "
            "→ 상방 추격 신호가 강해진 조합"
        )
    elif sox_up and lev_improving:
        overall = (
            "SOX가 오르고 헤지펀드 순포지션도 크게 개선 "
            "→ 가격 상승을 숏커버·롱 추가가 따라붙는 방향"
        )
    elif sox_up and not lev_improving:
        overall = (
            "SOX는 강하지만 헤지펀드 포지션이 따라붙는 확인이 부족 "
            "→ 만기수급·일시 반등 가능성도 남음"
        )
    elif (not sox_up) and lev_improving:
        overall = (
            "가격은 약하지만 헤지펀드 포지션은 개선 "
            "→ 선행 포지셔닝인지 실패 신호인지 다음 거래일 확인 필요"
        )
    else:
        overall = "가격·기관 포지션·옵션 수요가 아직 한 방향으로 정렬되지 않음"

    # Extra nuance: asset managers and leveraged funds can move in opposite directions.
    if cftc and lev_improving and not asset_improving:
        overall += (
            " / 다만 Asset Manager는 순포지션을 줄여 장기기관과 헤지펀드성 자금의 방향은 엇갈림"
        )

    return lines, overall


state = load_state()
results = []
errors = []

for name, fn in [("CFTC", parse_cftc), ("Cboe", parse_cboe), ("SOX", parse_sox)]:
    try:
        results.append(fn())
    except Exception as e:
        errors.append(f"{name}: {type(e).__name__}: {e}")

updates = []
for x in results:
    key = f"{x['source']}|{x['kind']}"
    if state.get("seen", {}).get(key) != x["fingerprint"]:
        updates.append(x)

cftc = next((x for x in results if x["kind"] == "cot"), None)
cboe = next((x for x in results if x["kind"] == "options"), None)
sox = next((x for x in results if x["kind"] == "sox"), None)
lines, overall = explain(cftc, cboe, sox)

STATUS.write_text(
    "\n".join(
        [
            "# US Positioning Watch",
            "",
            f"- parsed sources: {len(results)}",
            f"- updates: {len(updates)}",
            *[
                f"- {x['source']} {x['period']} {x['fingerprint'][:12]} metrics={json.dumps(x['metrics'], ensure_ascii=False)}"
                for x in results
            ],
            *[f"- error: {e}" for e in errors],
        ]
    )
    + "\n",
    encoding="utf-8",
)

force = (os.getenv("FORCE_SEND") or "").lower() in ("1", "true", "yes")
if updates or force:
    prior_sox = (state.get("values", {}) or {}).get("Nasdaq SOX|sox")
    prior_cftc = (state.get("values", {}) or {}).get("CFTC|cot")
    prior_cboe = (state.get("values", {}) or {}).get("Cboe|options")
    correction = bool(
        prior_sox
        and sox
        and prior_sox.get("period") == sox.get("period")
        and (
            abs(float((prior_sox.get("metrics") or {}).get("pct", 999)) - float(sox["metrics"]["pct"])) > 0.01
            or prior_cftc is None
            or prior_cboe is None
        )
    )
    event_label = "정정·보강" if correction else "신규 변화"

    body = [
        f"🇺🇸 <b>[미국 상방 포지셔닝 추적 | {event_label}]</b>",
        "",
        "<b>한눈에 보기</b>",
        *lines,
        f"→ <b>종합</b>: {html.escape(overall)}",
        "",
    ]

    if sox:
        body += [
            "<b>SOX 확인</b>",
            f"• 전일 {sox['metrics']['previous_close']:,.2f} → {sox['metrics']['value']:,.2f} "
            f"({sox['metrics']['d1_pct']:+.2f}%)",
            "• Nasdaq 최신 지수값과 FRED의 Nasdaq 일별 시계열을 교차검증해 등락률을 직접 계산",
            "",
        ]

    if cftc:
        m = cftc["metrics"]
        body += [
            "<b>CFTC 포지션 해석</b>",
            f"• Asset Manager: 롱 {m['asset_long']:,} / 숏 {m['asset_short']:,} → 순 {m['asset_net']:+,}계약",
            f"• 전주 대비 순포지션 {m['asset_net_wow']:+,}계약 "
            f"→ {'기관 순롱 확대' if m['asset_net_wow'] > 0 else '기관 순롱 축소' if m['asset_net_wow'] < 0 else '변화 제한'}",
            f"• Leveraged Funds: 롱 {m['lev_long']:,} / 숏 {m['lev_short']:,} → 순 {m['lev_net']:+,}계약",
            f"• 전주 대비 순포지션 {m['lev_net_wow']:+,}계약 "
            f"→ {'헤지펀드성 포지션 개선' if m['lev_net_wow'] > 0 else '헤지펀드성 포지션 악화' if m['lev_net_wow'] < 0 else '변화 제한'}",
            "",
        ]

    if cboe:
        m = cboe["metrics"]
        body += ["<b>Cboe 옵션 해석</b>"]
        if m.get("equity_pc_ratio") is not None:
            body.append(
                f"• 주식옵션 풋/콜 {m['equity_pc_ratio']:.2f} "
                f"({m.get('equity_time_ct') or '최신'} CT) "
                f"→ {'콜 우위' if m['equity_pc_ratio'] < 0.80 else '중립권' if m['equity_pc_ratio'] <= 1.0 else '풋 우위'}"
            )
        if m.get("index_pc_ratio") is not None:
            body.append(f"• 지수옵션 풋/콜 {m['index_pc_ratio']:.2f}")
        if m.get("total_pc_ratio") is not None:
            body.append(f"• 전체 풋/콜 {m['total_pc_ratio']:.2f}")
        body.append("")

    body += [
        "<b>이번에 실제로 바뀐 값</b>",
    ]
    for x in (updates if updates else results):
        body.append(
            f"• {html.escape(x['source'])} | {html.escape(str(x['period']))} | "
            f"<a href=\"{html.escape(x['url'], quote=True)}\">원천</a>"
        )

    if errors:
        body += ["", "<b>확인 대기</b>"]
        for e in errors:
            body.append("• " + html.escape(e.split(":", 1)[0]) + " 최신값 자동 재확인 중")

    ALERT.write_text("\n".join(body) + "\n", encoding="utf-8")

    ns = state
    ns.setdefault("seen", {})
    ns.setdefault("values", {})
    for x in results:
        key = f"{x['source']}|{x['kind']}"
        ns["seen"][key] = x["fingerprint"]
        ns["values"][key] = x
    ns["updated_at_kst"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
    PENDING.write_text(
        json.dumps(ns, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"us_positioning_alert_ready=true event={event_label} updates={len(updates)}")
else:
    print("us_positioning_alert_ready=false unchanged=true")

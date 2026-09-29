#!/usr/bin/env python3
import os, re, json, hashlib, html
from pathlib import Path
from datetime import datetime, timezone, timedelta
from io import StringIO, BytesIO

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
CFTC_HISTORY_TEMPLATE = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
NQ_CFTC_CODE = "209742"
CBOE = "https://www.cboe.com/us/options/market_statistics/market/"
SOX = "https://indexes.nasdaq.com/Index/History/SOX"
SOX_OVERVIEW = "https://beta.indexes.nasdaq.com/Index/Overview/SOX"
SOX_OVERVIEW_FALLBACK = "https://indexes.nasdaq.com/Index/Overview/SOX"
SOX_AUX = "https://indexes.nasdaq.com/Index/Weighting/SOX"


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


def parse_cftc_nq_mini(plain):
    """Parse the official NASDAQ MINI (NQ) TFF block separately from Consolidated."""
    start = plain.find("NASDAQ MINI -")
    if start < 0:
        return None
    block = plain[start : start + 7000]

    oi_m = re.search(r"Open Interest is\s+([\d,]+)", block, re.I)
    pos_m = re.search(r"Positions\s+([\s\S]*?)\s+Changes from:", block, re.I)
    ch_m = re.search(
        r"Changes from:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2}).*?"
        r"Total Change is:\s*([-+]?\s*[\d,]+)\s+([\s\S]*?)\s+Percent of Open Interest",
        block,
        re.I,
    )
    if not oi_m or not pos_m or not ch_m:
        return None

    pos = int_list(pos_m.group(1))[:14]
    changes = int_list(ch_m.group(3))[:14]
    if len(pos) < 14 or len(changes) < 14:
        return None

    oi = int(oi_m.group(1).replace(",", ""))
    oi_wow = int(ch_m.group(2).replace(" ", "").replace(",", ""))
    lev_long, lev_short = pos[6], pos[7]
    lev_long_wow, lev_short_wow = changes[6], changes[7]
    return {
        "contract": "NASDAQ MINI",
        "cftc_code": NQ_CFTC_CODE,
        "open_interest": oi,
        "open_interest_wow": oi_wow,
        "leveraged_long": lev_long,
        "leveraged_short": lev_short,
        "leveraged_net": lev_long - lev_short,
        "leveraged_long_wow": lev_long_wow,
        "leveraged_short_wow": lev_short_wow,
        "leveraged_net_wow": lev_long_wow - lev_short_wow,
        "short_share_oi_pct": (lev_short / oi * 100.0) if oi else None,
        "previous_period": ch_m.group(1),
        "scope": "CFTC TFF NASDAQ MINI 전체시장 주간",
    }


def cftc_nq_history_3y(current_nq=None, current_period=None):
    """Build a three-year NQ leveraged-fund distribution from official CFTC history."""
    year = datetime.now(timezone.utc).year
    frames = []
    errors = []
    for y in range(year - 3, year + 1):
        url = CFTC_HISTORY_TEMPLATE.format(year=y)
        try:
            raw = get(url, timeout=50).content
            df = pd.read_csv(BytesIO(raw), compression="zip", low_memory=False)
            df.columns = [str(x).strip() for x in df.columns]
            frames.append(df)
        except Exception as exc:
            errors.append(f"{y}:{type(exc).__name__}")

    if not frames:
        raise RuntimeError("CFTC TFF 3년 압축자료 조회 실패: " + ", ".join(errors))

    df = pd.concat(frames, ignore_index=True)
    code_col = "CFTC_Contract_Market_Code"
    if code_col not in df.columns:
        raise RuntimeError("CFTC history code column missing")

    codes = (
        df[code_col].astype(str)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    df = df[codes == NQ_CFTC_CODE].copy()
    if df.empty:
        raise RuntimeError("CFTC history NASDAQ MINI rows missing")

    date_col = next(
        (x for x in ("Report_Date_as_YYYY-MM-DD", "Report_Date_as_MM_DD_YYYY") if x in df.columns),
        None,
    )
    needed = [
        "Open_Interest_All",
        "Lev_Money_Positions_Long_All",
        "Lev_Money_Positions_Short_All",
    ]
    if not date_col or any(x not in df.columns for x in needed):
        raise RuntimeError("CFTC history required columns missing")

    df["_date"] = pd.to_datetime(df[date_col], errors="coerce")
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["_date", *needed]).sort_values("_date")
    df = df.drop_duplicates(subset=["_date"], keep="last")

    if current_nq and current_period:
        try:
            d = pd.to_datetime(current_period)
            if df.empty or d > df["_date"].max():
                df = pd.concat(
                    [
                        df,
                        pd.DataFrame(
                            [{
                                "_date": d,
                                "Open_Interest_All": current_nq["open_interest"],
                                "Lev_Money_Positions_Long_All": current_nq["leveraged_long"],
                                "Lev_Money_Positions_Short_All": current_nq["leveraged_short"],
                            }]
                        ),
                    ],
                    ignore_index=True,
                )
        except Exception:
            pass

    df = df.sort_values("_date").drop_duplicates(subset=["_date"], keep="last")
    latest = df["_date"].max()
    cutoff = latest - pd.Timedelta(days=1096)
    df = df[df["_date"] >= cutoff].tail(160).copy()
    if len(df) < 52:
        raise RuntimeError(f"CFTC history sample too short: {len(df)}")

    df["_net"] = df["Lev_Money_Positions_Long_All"] - df["Lev_Money_Positions_Short_All"]
    df["_short_severity"] = (-df["_net"]).clip(lower=0)
    df["_short_share"] = (
        df["Lev_Money_Positions_Short_All"] / df["Open_Interest_All"] * 100.0
    )

    cur = df.iloc[-1]
    severity = float(cur["_short_severity"])
    short_share = float(cur["_short_share"])
    severity_pct = float((df["_short_severity"] <= severity).mean() * 100.0)
    short_share_pct = float((df["_short_share"] <= short_share).mean() * 100.0)
    peak = float(df["_short_severity"].max())
    unwind = ((peak - severity) / peak * 100.0) if peak > 0 else None

    def diff(col, weeks):
        if len(df) <= weeks:
            return None
        return float(df.iloc[-1][col] - df.iloc[-1 - weeks][col])

    return {
        "basis": "CFTC TFF NASDAQ MINI futures-only",
        "sample_n": int(len(df)),
        "start_date": df.iloc[0]["_date"].strftime("%Y-%m-%d"),
        "end_date": df.iloc[-1]["_date"].strftime("%Y-%m-%d"),
        "short_extreme_percentile_3y": severity_pct,
        "short_share_oi_percentile_3y": short_share_pct,
        "peak_net_short_contracts_3y": int(round(peak)),
        "unwind_from_peak_pct": unwind,
        "leveraged_short_1w_change": int(round(diff("Lev_Money_Positions_Short_All", 1))) if diff("Lev_Money_Positions_Short_All", 1) is not None else None,
        "leveraged_short_4w_change": int(round(diff("Lev_Money_Positions_Short_All", 4))) if diff("Lev_Money_Positions_Short_All", 4) is not None else None,
        "leveraged_net_1w_change": int(round(diff("_net", 1))) if diff("_net", 1) is not None else None,
        "leveraged_net_4w_change": int(round(diff("_net", 4))) if diff("_net", 4) is not None else None,
        "history_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm",
        "download_errors": errors,
    }


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
    nq_mini = parse_cftc_nq_mini(plain)
    try:
        history_3y = cftc_nq_history_3y(nq_mini, period) if nq_mini else None
    except Exception as exc:
        history_3y = {"error": f"{type(exc).__name__}: {exc}"}

    # Keep the existing fingerprint limited to the original current-report core.
    # The NQ/3Y enrichment must not create a fake "new positioning" alert by itself.
    core = {"source": "CFTC", "kind": "cot", "period": period, "metrics": metrics}
    return {
        **core,
        "url": CFTC,
        "fingerprint": fp(core),
        "nq_mini": nq_mini,
        "history_3y": history_3y,
    }


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

    report_start = text.find("Cboe Exchange Market Statistics for")
    report_text = text[report_start:] if report_start >= 0 else text
    total = parse_cboe_section(report_text, "Total", "Index Options")
    index_opt = parse_cboe_section(report_text, "Index Options", "Equity Options")
    equity = parse_cboe_section(report_text, "Equity Options")

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
    """Parse the official Nasdaq SOX close and fail closed on inconsistent fields."""
    errors = []
    parsed = None
    source_url = None

    for url in (SOX_OVERVIEW, SOX_OVERVIEW_FALLBACK):
        try:
            raw = get(url).text
            txt = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
            cur = re.search(
                r"DATA AS OF\s+(\d{1,2}/\d{1,2}/20\d{2})\s+"
                r"([\d,]+\.\d+)\s+([+-]?[\d,]+\.\d+)\s+([+-]?\d+(?:\.\d+)?)%",
                txt,
                re.I,
            )
            prev_m = re.search(r"Previous Close\s+([\d,]+\.\d+)", txt, re.I)
            if not cur or not prev_m:
                raise RuntimeError("Overview headline/previous close missing")

            period = cur.group(1)
            latest = float(cur.group(2).replace(",", ""))
            net_change = float(cur.group(3).replace(",", ""))
            pct = float(cur.group(4))
            previous_close = float(prev_m.group(1).replace(",", ""))

            calc_net = latest - previous_close
            calc_pct = (latest / previous_close - 1.0) * 100.0 if previous_close else None
            if calc_pct is None or abs(calc_pct - pct) > 0.08:
                raise RuntimeError(
                    f"SOX pct mismatch: page={pct}, calc={calc_pct:.2f}"
                )
            if abs(pct) > 25:
                raise RuntimeError(f"SOX daily pct sanity failed: {pct}")

            # Nasdaq's SOX page can publish a stale Net Change field while Last,
            # Previous Close and Net Change(%) are internally consistent. In that
            # exact case, derive the net change arithmetically and record that fact
            # instead of silently accepting the inconsistent field.
            net_change_source = "Nasdaq official Overview"
            if abs(calc_net - net_change) > 1.0:
                net_change = calc_net
                net_change_source = "Nasdaq Last minus Previous Close derived; displayed Net Change stale"

            parsed = (period, latest, net_change, pct, previous_close, net_change_source)
            source_url = url
            break
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    if parsed is None:
        raise RuntimeError("SOX official Overview validation failed: " + " | ".join(errors))

    period, latest, displayed_net_change, displayed_pct, previous_close, net_change_source = parsed
    metrics = {
        "value": latest,
        "previous_close": previous_close,
        "previous_close_source": "Nasdaq official Overview",
        "net_change": displayed_net_change,
        "net_change_source": net_change_source,
        "pct": displayed_pct,
        "d1_pct": displayed_pct,
        "official_overview_url": source_url,
    }

    # Optional 3D/5D context only. It never overrides the official Nasdaq 1D close.
    try:
        inv = get("https://www.investing.com/indices/phlx-semiconductor-historical-data").text
        tables = pd.read_html(StringIO(inv))
        hist = None
        for t in tables:
            flat = " ".join(map(str, t.astype(str).values.flatten()))
            if "Date" in flat and ("Price" in flat or "Change %" in flat):
                hist = t
                break
        if hist is not None:
            hist.columns = [str(x[-1] if isinstance(x, tuple) else x).strip() for x in hist.columns]
            date_col = next((x for x in hist.columns if x.lower() == "date"), None)
            pcol = next((x for x in hist.columns if x.lower() in ("price", "last", "close")), None)
            if date_col and pcol:
                rows = []
                for _, row in hist.head(10).iterrows():
                    ds = str(row.get(date_col, "")).strip()
                    val = parse_num(row.get(pcol))
                    if ds and val is not None:
                        rows.append((ds, val))
                if rows:
                    def _norm_date(s):
                        for fmt in ("%b %d, %Y", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
                            try:
                                return datetime.strptime(s, fmt).strftime("%m/%d/%Y")
                            except Exception:
                                pass
                        return s
                    if _norm_date(rows[0][0]) == period and abs(rows[0][1] - latest) <= 1.0:
                        vals = [v for _, v in rows]
                        if len(vals) >= 4:
                            metrics["d3_pct"] = (vals[0] / vals[3] - 1) * 100
                        if len(vals) >= 6:
                            metrics["d5_pct"] = (vals[0] / vals[5] - 1) * 100
    except Exception:
        pass

    core = {"source": "Nasdaq SOX", "kind": "sox", "period": period, "metrics": metrics}
    return {**core, "url": source_url, "fingerprint": fp(core)}


def explain(cftc, cboe, sox):
    lines = []

    if sox:
        m = sox["metrics"]
        parts = [
            f"• 반도체(SOX): {m['value']:,.2f}",
            f"1D {m['d1_pct']:+.2f}%",
        ]
        if m.get("d3_pct") is not None:
            parts.append(f"3D {m['d3_pct']:+.2f}%")
        if m.get("d5_pct") is not None:
            parts.append(f"5D {m['d5_pct']:+.2f}%")
        lines.append(" | ".join(parts))

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
        nq = cftc.get("nq_mini") or {}
        hist = cftc.get("history_3y") or {}
        if nq:
            pct = hist.get("short_extreme_percentile_3y")
            pct_txt = f" · 3년 순숏 {pct:.0f}백분위" if isinstance(pct, (int, float)) else ""
            lines.append(
                f"• NQ E-mini Leveraged Funds: 순포지션 {int(nq.get('leveraged_net') or 0):+,}계약"
                f" | 주간 {int(nq.get('leveraged_net_wow') or 0):+,}계약{pct_txt}"
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

# Fail closed: this alert is only useful when all three critical lanes are valid.
# Never send a partial "new change" alert with missing CFTC/Cboe/SOX values.
required_kinds = {"cot", "options", "sox"}
present_kinds = {x.get("kind") for x in results}

def validate_critical_sources(cftc_obj, cboe_obj, sox_obj):
    problems = []

    if cftc_obj:
        m = cftc_obj["metrics"]
        if m["asset_net"] != m["asset_long"] - m["asset_short"]:
            problems.append("CFTC Asset Manager 순포지션 산술 불일치")
        if m["lev_net"] != m["lev_long"] - m["lev_short"]:
            problems.append("CFTC Leveraged Funds 순포지션 산술 불일치")
        if m["asset_net_wow"] != m["asset_long_wow"] - m["asset_short_wow"]:
            problems.append("CFTC Asset Manager 주간변화 산술 불일치")
        if m["lev_net_wow"] != m["lev_long_wow"] - m["lev_short_wow"]:
            problems.append("CFTC Leveraged Funds 주간변화 산술 불일치")

        nq = cftc_obj.get("nq_mini") or {}
        hist = cftc_obj.get("history_3y") or {}
        if not nq or nq.get("cftc_code") != NQ_CFTC_CODE:
            problems.append("CFTC NASDAQ MINI 공식 코드/포지션 확인 불가")
        else:
            if nq.get("leveraged_net") != nq.get("leveraged_long", 0) - nq.get("leveraged_short", 0):
                problems.append("CFTC NQ Leveraged Funds 순포지션 산술 불일치")
            if nq.get("open_interest_wow") is None:
                problems.append("CFTC NQ 동일범위 OI 주간변화 확인 불가")
        if not isinstance(hist.get("short_extreme_percentile_3y"), (int, float)):
            problems.append("CFTC NQ 3년 순숏 백분위 확인 불가")
        if int(hist.get("sample_n") or 0) < 150:
            problems.append("CFTC NQ 3년 표본 부족")

    if cboe_obj:
        m = cboe_obj["metrics"]
        if m.get("total_calls") and m.get("total_puts") and m.get("total_pc_ratio") is not None:
            calc = m["total_puts"] / m["total_calls"]
            if abs(calc - m["total_pc_ratio"]) > 0.03:
                problems.append(
                    f"Cboe 전체 풋/콜 검산 불일치: 계산 {calc:.3f} vs 표 {m['total_pc_ratio']:.3f}"
                )
        if m.get("equity_calls") and m.get("equity_puts") and m.get("equity_pc_ratio") is not None:
            calc = m["equity_puts"] / m["equity_calls"]
            if abs(calc - m["equity_pc_ratio"]) > 0.03:
                problems.append(
                    f"Cboe 주식옵션 풋/콜 검산 불일치: 계산 {calc:.3f} vs 표 {m['equity_pc_ratio']:.3f}"
                )

    if sox_obj:
        m = sox_obj["metrics"]
        if abs(m.get("net_change", 0)) > 1 and abs(m.get("d1_pct", 0)) < 0.01:
            problems.append("SOX 순변동은 큰데 등락률이 0.00%로 모순")
        prev = m.get("previous_close")
        if prev and prev > 0:
            calc_pct = (m["value"] / prev - 1) * 100
            if abs(calc_pct - m["d1_pct"]) > 0.08:
                problems.append(
                    f"SOX 등락률 검산 불일치: 계산 {calc_pct:.2f}% vs 표 {m['d1_pct']:.2f}%"
                )

    return problems


cftc_for_gate = next((x for x in results if x.get("kind") == "cot"), None)
cboe_for_gate = next((x for x in results if x.get("kind") == "options"), None)
sox_for_gate = next((x for x in results if x.get("kind") == "sox"), None)

validation_problems = validate_critical_sources(
    cftc_for_gate, cboe_for_gate, sox_for_gate
)
if validation_problems:
    errors.extend("검산: " + p for p in validation_problems)

quality_gate_ok = required_kinds.issubset(present_kinds) and not validation_problems

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
            f"- quality_gate_ok: {quality_gate_ok}",
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
if quality_gate_ok and (updates or force):
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
            "• Nasdaq History의 공식 종가·등락률을 사용하고, 3D·5D는 별도 과거 시계열로 보조 확인",
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
        ]
        nq = cftc.get("nq_mini") or {}
        hist = cftc.get("history_3y") or {}
        if nq:
            body += [
                "",
                "<b>Nasdaq NQ E-mini 3년 포지션 추적</b>",
                f"• Leveraged Funds: 롱 {int(nq.get('leveraged_long') or 0):,} / 숏 {int(nq.get('leveraged_short') or 0):,} → 순 {int(nq.get('leveraged_net') or 0):+,}계약",
                f"• 주간 순포지션 변화 {int(nq.get('leveraged_net_wow') or 0):+,}계약 · OI 변화 {int(nq.get('open_interest_wow') or 0):+,}계약",
                f"• 숏/OI {float(nq.get('short_share_oi_pct') or 0):.1f}%",
            ]
            if isinstance(hist.get("short_extreme_percentile_3y"), (int, float)):
                body += [
                    f"• 최근 3년 순숏 백분위: <b>{hist['short_extreme_percentile_3y']:.0f}백분위</b> · 숏/OI {hist.get('short_share_oi_percentile_3y', 0):.0f}백분위",
                    f"• 3년 최대 순숏 대비 청산률: {hist.get('unwind_from_peak_pct', 0):.1f}%",
                    f"• 숏 계약 변화: 1주 {int(hist.get('leveraged_short_1w_change') or 0):+,} · 4주 {int(hist.get('leveraged_short_4w_change') or 0):+,}",
                    "※ 3년 백분위는 CFTC TFF NASDAQ MINI futures-only 공식 연간 압축자료로 계산. Goldman/BofA PB 독자 모델과 동일하지 않습니다.",
                ]
            elif hist.get("error"):
                body.append("• 3년 백분위: 공식 압축자료 재조회 대기")
        body.append("")

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
    if not quality_gate_ok:
        print("us_positioning_alert_ready=false quality_gate_failed=true")
    else:
        print("us_positioning_alert_ready=false unchanged=true")

# Persist the official CFTC NQ/3Y enrichment even when another lane (for example
# SOX rendering) fails the composite Telegram quality gate. Do not advance the
# CFTC 'seen' fingerprint here: if the full quality gate later recovers, the
# missed CFTC change must still be eligible for a user-facing alert.
current_cftc = next((x for x in results if x.get("kind") == "cot"), None)
prior_cftc = (state.get("values", {}) or {}).get("CFTC|cot")
enrichment_changed = bool(
    current_cftc
    and (
        not prior_cftc
        or prior_cftc.get("nq_mini") != current_cftc.get("nq_mini")
        or prior_cftc.get("history_3y") != current_cftc.get("history_3y")
    )
)
if enrichment_changed and not PENDING.exists():
    ns = json.loads(json.dumps(state))
    ns.setdefault("values", {})
    ns["values"]["CFTC|cot"] = current_cftc
    ns["updated_at_kst"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
    PENDING.write_text(
        json.dumps(ns, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("us_positioning_enrichment_state_ready=true")

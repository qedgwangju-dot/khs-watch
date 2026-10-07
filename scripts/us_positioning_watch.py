#!/usr/bin/env python3
import os, re, json, hashlib, html, time
from pathlib import Path
from datetime import datetime, timezone, timedelta, time as dt_time
from zoneinfo import ZoneInfo
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
CFTC_HISTORY_INDEX = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm"
CFTC_SOCRATA = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CBOE = "https://www.cboe.com/us/options/market_statistics/market/"
CBOE_DAILY_TEMPLATE = "https://www.cboe.com/markets/us/options/market-statistics/daily?dt={date}"
SOX = "https://indexes.nasdaq.com/Index/History/SOX"
SOX_OVERVIEW = "https://beta.indexes.nasdaq.com/Index/Overview/SOX"
SOX_OVERVIEW_FALLBACK = "https://indexes.nasdaq.com/Index/Overview/SOX"
SOX_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/%5ESOX?range=10d&interval=1d"
SOX_NASDAQ_HIST_API = "https://api.nasdaq.com/api/quote/SOX/historical"
NY = ZoneInfo("America/New_York")
SOX_AUX = "https://indexes.nasdaq.com/Index/Weighting/SOX"


def get(url, timeout=35):
    """Bounded retries for transient 429/5xx/network failures; no stale cache reuse."""
    errors = []
    for attempt in range(3):
        try:
            r = S.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
            )
            r.raise_for_status()
            return r
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"HTTP 조회 3회 실패: {url} / {' | '.join(errors)}")


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


def option_regimes(eq_pc, idx_pc):
    eq = "call" if eq_pc < 0.80 else "neutral" if eq_pc <= 1.00 else "put"
    idx = "call" if idx_pc < 0.90 else "neutral" if idx_pc <= 1.10 else "put"
    return eq, idx


# Deterministic guard for the alert's option-direction taxonomy.
if option_regimes(0.58, 0.86) != ("call", "call"):
    raise RuntimeError("option regime self-test failed for aligned call case")
if option_regimes(0.58, 1.05) != ("call", "neutral"):
    raise RuntimeError("option regime self-test failed for call/neutral case")
if option_regimes(1.05, 1.20) != ("put", "put"):
    raise RuntimeError("option regime self-test failed for aligned put case")


def int_list(text):
    vals = re.findall(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)", text)
    return [int(x.replace(",", "")) for x in vals]


def cftc_fixed_fields(text, expected=14):
    """Preserve CFTC '.' confidentiality placeholders so columns never shift."""
    tokens = re.findall(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)|\.", text or "")
    if len(tokens) < expected:
        raise RuntimeError(f"CFTC TFF row too short: {len(tokens)} < {expected}")
    return [None if t == "." else int(t.replace(",", "")) for t in tokens[:expected]]


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

    pos = cftc_fixed_fields(pos_m.group(1))
    changes = cftc_fixed_fields(ch_m.group(3))
    if any(pos[i] is None for i in (6, 7)) or any(changes[i] is None for i in (6, 7)):
        raise RuntimeError("NASDAQ MINI Leveraged Funds fields confidential/missing")

    oi = int(oi_m.group(1).replace(",", ""))
    oi_wow = int(ch_m.group(2).replace(" ", "").replace(",", ""))
    lev_long, lev_short = int(pos[6]), int(pos[7])
    lev_long_wow, lev_short_wow = int(changes[6]), int(changes[7])
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


def _self_test_cftc_parser():
    # Official CFTC TFF NASDAQ MINI sample, 2026-09-29. This guards both
    # category indexes and signed weekly changes from silent regex drift.
    sample = """
NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE (NASDAQ 100 STOCK INDEX X $20)
CFTC Code #209742 Open Interest is 270,554
Positions
49,079 107,321 3,041 108,558 38,814 4,654 48,150 72,873 6,073 11,001 8,124 0 39,998 29,654
Changes from: September 22, 2026 Total Change is: -15,767
-8,433 -8,595 1,145 2,318 4,794 -628 -5,883 -11,843 919 -4,589 -212 -4 -612 -1,343
Percent of Open Interest
"""
    row = parse_cftc_nq_mini(sample)
    expected = {
        "open_interest": 270554,
        "open_interest_wow": -15767,
        "leveraged_long": 48150,
        "leveraged_short": 72873,
        "leveraged_net": -24723,
        "leveraged_net_wow": 5960,
    }
    if row is None:
        raise RuntimeError("CFTC NQ parser self-test returned None")
    for key, value in expected.items():
        if row.get(key) != value:
            raise RuntimeError(
                f"CFTC NQ parser self-test failed: {key}={row.get(key)} expected={value}"
            )


_self_test_cftc_parser()

def _socrata_rows(params, timeout=50):
    """Official CFTC Public Reporting API fallback (dataset gpe5-46if)."""
    errors = []
    for attempt in range(3):
        try:
            r = S.get(
                CFTC_SOCRATA,
                params=params,
                timeout=timeout,
                headers={
                    "Accept": "application/json",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )
            r.raise_for_status()
            rows = r.json()
            if not isinstance(rows, list):
                raise RuntimeError("CFTC Socrata response is not a list")
            return rows
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("CFTC Socrata 3회 실패: " + " | ".join(errors))


def _socrata_nq_history_frame():
    rows = _socrata_rows({
        "$where": f"cftc_contract_market_code='{NQ_CFTC_CODE}'",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": "2000",
    }, timeout=60)
    if not rows:
        raise RuntimeError("CFTC Socrata NQ history empty")
    df = pd.DataFrame(rows)
    needed = [
        "report_date_as_yyyy_mm_dd",
        "open_interest_all",
        "lev_money_positions_long",
        "lev_money_positions_short",
    ]
    missing = [x for x in needed if x not in df.columns]
    if missing:
        raise RuntimeError("CFTC Socrata NQ history missing fields: " + ",".join(missing))
    out = pd.DataFrame({
        "_date": pd.to_datetime(df["report_date_as_yyyy_mm_dd"].astype(str).str[:10], errors="coerce"),
        "Open_Interest_All": pd.to_numeric(df["open_interest_all"], errors="coerce"),
        "Lev_Money_Positions_Long_All": pd.to_numeric(df["lev_money_positions_long"], errors="coerce"),
        "Lev_Money_Positions_Short_All": pd.to_numeric(df["lev_money_positions_short"], errors="coerce"),
    })
    return out.dropna().sort_values("_date").drop_duplicates("_date", keep="last")


def cftc_nq_history_3y(current_nq=None, current_period=None):
    """Build 3Y and 10Y NQ leveraged-fund distributions from official CFTC TFF history.

    Three-year statistics remain the mandatory operational gate. Ten-year values are
    published only when every required annual file is available, so an incomplete
    long-history download can never be mislabeled as a full 10-year comparison.
    """
    year = datetime.now(timezone.utc).year
    requested_years = list(range(year - 10, year + 1))
    frames = []
    errors = []
    loaded_years = []
    history_source = "CFTC annual compressed TFF"

    for y in requested_years:
        url = CFTC_HISTORY_TEMPLATE.format(year=y)
        last_exc = None
        for _attempt in range(2):
            try:
                raw = get(url, timeout=50).content
                df_year = pd.read_csv(BytesIO(raw), compression="zip", low_memory=False)
                df_year.columns = [str(x).strip() for x in df_year.columns]
                frames.append(df_year)
                loaded_years.append(y)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            errors.append(f"{y}:{type(last_exc).__name__}")

    if frames:
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
    else:
        # www.cftc.gov can block cloud runners. Public Reporting is an independent
        # official CFTC path to the same TFF futures-only dataset.
        df = _socrata_nq_history_frame()
        loaded_years = sorted(set(int(x.year) for x in df["_date"]))
        history_source = "CFTC Public Reporting Socrata gpe5-46if"

    if current_nq and current_period:
        try:
            d = pd.to_datetime(current_period)
            same = df[df["_date"] == d]
            if not same.empty:
                row = same.iloc[-1]
                checks = {
                    "Open_Interest_All": int(current_nq["open_interest"]),
                    "Lev_Money_Positions_Long_All": int(current_nq["leveraged_long"]),
                    "Lev_Money_Positions_Short_All": int(current_nq["leveraged_short"]),
                }
                mismatches = []
                for col, expected in checks.items():
                    actual = int(row[col])
                    if actual != expected:
                        mismatches.append(f"{col} history={actual} live={expected}")
                if mismatches:
                    raise RuntimeError(
                        "CFTC live/history same-date mismatch: " + " | ".join(mismatches)
                    )
            elif df.empty or d > df["_date"].max():
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
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"CFTC current-period alignment failed: {exc}") from exc

    df = df.sort_values("_date").drop_duplicates(subset=["_date"], keep="last")
    latest = df["_date"].max()
    df["_net"] = df["Lev_Money_Positions_Long_All"] - df["Lev_Money_Positions_Short_All"]
    df["_short_severity"] = (-df["_net"]).clip(lower=0)
    df["_gross_short"] = df["Lev_Money_Positions_Short_All"]
    df["_short_share"] = (
        df["Lev_Money_Positions_Short_All"] / df["Open_Interest_All"] * 100.0
    )

    def _window(years: int):
        cutoff = latest - pd.DateOffset(years=years)
        return df[df["_date"] >= cutoff].copy()

    def _stats(frame):
        frame = frame.sort_values("_date").copy()
        if frame.empty:
            return None
        cur = frame.iloc[-1]
        severity = float(cur["_short_severity"])
        gross_short = float(cur["_gross_short"])
        short_share = float(cur["_short_share"])
        peak_net_idx = frame["_short_severity"].idxmax()
        peak_gross_idx = frame["_gross_short"].idxmax()
        peak_net = float(frame.loc[peak_net_idx, "_short_severity"])
        peak_gross = float(frame.loc[peak_gross_idx, "_gross_short"])

        gross_weekly_add = frame["_gross_short"].diff()
        net_weekly_build = -frame["_net"].diff()
        cur_gross_add = float(gross_weekly_add.iloc[-1]) if pd.notna(gross_weekly_add.iloc[-1]) else None
        cur_net_build = float(net_weekly_build.iloc[-1]) if pd.notna(net_weekly_build.iloc[-1]) else None
        gross_build_clean = gross_weekly_add.dropna()
        net_build_clean = net_weekly_build.dropna()

        def _pctile(series, value):
            if value is None or series.empty:
                return None
            return float((series <= value).mean() * 100.0)

        def _max_with_date(series):
            if series.empty:
                return None, None
            idx = series.idxmax()
            return float(series.loc[idx]), frame.loc[idx, "_date"].strftime("%Y-%m-%d")

        max_gross_build, max_gross_build_date = _max_with_date(gross_build_clean)
        max_net_build, max_net_build_date = _max_with_date(net_build_clean)

        return {
            "sample_n": int(len(frame)),
            "start_date": frame.iloc[0]["_date"].strftime("%Y-%m-%d"),
            "end_date": frame.iloc[-1]["_date"].strftime("%Y-%m-%d"),
            "net_short_percentile": float((frame["_short_severity"] <= severity).mean() * 100.0),
            "gross_short_percentile": float((frame["_gross_short"] <= gross_short).mean() * 100.0),
            "short_share_oi_percentile": float((frame["_short_share"] <= short_share).mean() * 100.0),
            "peak_net_short_contracts": int(round(peak_net)),
            "peak_net_short_date": frame.loc[peak_net_idx, "_date"].strftime("%Y-%m-%d"),
            "peak_gross_short_contracts": int(round(peak_gross)),
            "peak_gross_short_date": frame.loc[peak_gross_idx, "_date"].strftime("%Y-%m-%d"),
            "net_short_unwind_from_peak_pct": ((peak_net - severity) / peak_net * 100.0) if peak_net > 0 else None,
            "gross_short_unwind_from_peak_pct": ((peak_gross - gross_short) / peak_gross * 100.0) if peak_gross > 0 else None,
            "gross_short_weekly_change": int(round(cur_gross_add)) if cur_gross_add is not None else None,
            "net_short_weekly_build": int(round(cur_net_build)) if cur_net_build is not None else None,
            "gross_short_weekly_build_percentile": _pctile(gross_build_clean, cur_gross_add),
            "net_short_weekly_build_percentile": _pctile(net_build_clean, cur_net_build),
            "max_gross_short_weekly_build": int(round(max_gross_build)) if max_gross_build is not None else None,
            "max_gross_short_weekly_build_date": max_gross_build_date,
            "max_net_short_weekly_build": int(round(max_net_build)) if max_net_build is not None else None,
            "max_net_short_weekly_build_date": max_net_build_date,
            "gross_short_weekly_record": bool(
                cur_gross_add is not None and max_gross_build is not None and cur_gross_add >= max_gross_build
            ),
            "net_short_weekly_record": bool(
                cur_net_build is not None and max_net_build is not None and cur_net_build >= max_net_build
            ),
        }

    df3 = _window(3)
    if len(df3) < 150:
        raise RuntimeError(f"CFTC 3년 history sample too short: {len(df3)}")
    s3 = _stats(df3)

    # A full 10-year statement is allowed only when every annual file covering the
    # requested interval was loaded. Missing older files do not block the 3Y gate,
    # but they suppress every 10Y percentile/record claim.
    ten_year_complete = set(requested_years).issubset(set(loaded_years))
    df10 = _window(10)
    s10 = _stats(df10) if ten_year_complete and len(df10) >= 500 else None

    def diff(frame, col, weeks):
        frame = frame.sort_values("_date")
        if len(frame) <= weeks:
            return None
        return float(frame.iloc[-1][col] - frame.iloc[-1 - weeks][col])

    result = {
        "basis": "CFTC TFF NASDAQ MINI futures-only",
        "sample_n": s3["sample_n"],
        "start_date": s3["start_date"],
        "end_date": s3["end_date"],
        "net_short_percentile_3y": s3["net_short_percentile"],
        "gross_short_percentile_3y": s3["gross_short_percentile"],
        "short_extreme_percentile_3y": s3["net_short_percentile"],
        "short_share_oi_percentile_3y": s3["short_share_oi_percentile"],
        "peak_net_short_contracts_3y": s3["peak_net_short_contracts"],
        "peak_net_short_date_3y": s3["peak_net_short_date"],
        "peak_gross_short_contracts_3y": s3["peak_gross_short_contracts"],
        "peak_gross_short_date_3y": s3["peak_gross_short_date"],
        "net_short_unwind_from_peak_pct": s3["net_short_unwind_from_peak_pct"],
        "gross_short_unwind_from_peak_pct": s3["gross_short_unwind_from_peak_pct"],
        "unwind_from_peak_pct": s3["net_short_unwind_from_peak_pct"],
        "leveraged_short_1w_change": int(round(diff(df3, "_gross_short", 1))) if diff(df3, "_gross_short", 1) is not None else None,
        "leveraged_short_4w_change": int(round(diff(df3, "_gross_short", 4))) if diff(df3, "_gross_short", 4) is not None else None,
        "leveraged_net_1w_change": int(round(diff(df3, "_net", 1))) if diff(df3, "_net", 1) is not None else None,
        "leveraged_net_4w_change": int(round(diff(df3, "_net", 4))) if diff(df3, "_net", 4) is not None else None,
        "history_url": CFTC_HISTORY_INDEX,
        "history_source": history_source,
        "download_errors": errors,
        "loaded_years": loaded_years,
        "ten_year_complete": ten_year_complete,
    }

    if s10 is not None:
        result.update({
            "sample_n_10y": s10["sample_n"],
            "start_date_10y": s10["start_date"],
            "end_date_10y": s10["end_date"],
            "net_short_percentile_10y": s10["net_short_percentile"],
            "gross_short_percentile_10y": s10["gross_short_percentile"],
            "short_share_oi_percentile_10y": s10["short_share_oi_percentile"],
            "peak_net_short_contracts_10y": s10["peak_net_short_contracts"],
            "peak_net_short_date_10y": s10["peak_net_short_date"],
            "peak_gross_short_contracts_10y": s10["peak_gross_short_contracts"],
            "peak_gross_short_date_10y": s10["peak_gross_short_date"],
            "net_short_unwind_from_peak_pct_10y": s10["net_short_unwind_from_peak_pct"],
            "gross_short_unwind_from_peak_pct_10y": s10["gross_short_unwind_from_peak_pct"],
            "gross_short_weekly_change_10y": s10["gross_short_weekly_change"],
            "net_short_weekly_build_10y": s10["net_short_weekly_build"],
            "gross_short_weekly_build_percentile_10y": s10["gross_short_weekly_build_percentile"],
            "net_short_weekly_build_percentile_10y": s10["net_short_weekly_build_percentile"],
            "max_gross_short_weekly_build_10y": s10["max_gross_short_weekly_build"],
            "max_gross_short_weekly_build_date_10y": s10["max_gross_short_weekly_build_date"],
            "max_net_short_weekly_build_10y": s10["max_net_short_weekly_build"],
            "max_net_short_weekly_build_date_10y": s10["max_net_short_weekly_build_date"],
            "gross_short_weekly_record_10y": s10["gross_short_weekly_record"],
            "net_short_weekly_record_10y": s10["net_short_weekly_record"],
        })
    return result



def _parse_cftc_live():
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
    pos = cftc_fixed_fields(pos_m.group(1))
    # Exact CFTC layout has 14 position values:
    # dealer(3), asset manager(3), leveraged funds(3), other reportable(3), nonreportable(2).
    if any(pos[i] is None for i in (3, 4, 6, 7)):
        raise RuntimeError("NASDAQ-100 CFTC critical position fields confidential/missing")

    ch_m = re.search(
        r"Changes from:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2}).*?Total Change is:\s*[-+]?([\d,]+)\s+([\s\S]*?)\s+Percent of Open Interest",
        block,
        re.I,
    )
    if not ch_m:
        raise RuntimeError("NASDAQ-100 CFTC weekly changes row not found")
    prev_period = ch_m.group(1)
    changes = cftc_fixed_fields(ch_m.group(3))
    if any(changes[i] is None for i in (3, 4, 6, 7)):
        raise RuntimeError("NASDAQ-100 CFTC critical weekly-change fields confidential/missing")

    asset_long, asset_short = int(pos[3]), int(pos[4])
    lev_long, lev_short = int(pos[6]), int(pos[7])
    asset_long_wow, asset_short_wow = int(changes[3]), int(changes[4])
    lev_long_wow, lev_short_wow = int(changes[6]), int(changes[7])

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


def _tff_latest_rows_from_compressed():
    """Official current-year TFF compressed fallback when the live CFTC HTML is blocked."""
    year = datetime.now(timezone.utc).year
    url = CFTC_HISTORY_TEMPLATE.format(year=year)
    raw = get(url, timeout=50).content
    df = pd.read_csv(BytesIO(raw), compression="zip", low_memory=False)
    df.columns = [str(x).strip() for x in df.columns]

    date_col = next(
        (x for x in ("Report_Date_as_YYYY-MM-DD", "Report_Date_as_MM_DD_YYYY") if x in df.columns),
        None,
    )
    if not date_col:
        raise RuntimeError("CFTC compressed fallback date column missing")
    df["_date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["_date"])
    if df.empty:
        raise RuntimeError("CFTC compressed fallback has no dated rows")
    return df, url


def _num_int(row, key, fallback=None):
    val = pd.to_numeric(row.get(key), errors="coerce")
    if pd.notna(val):
        return int(val)
    return fallback


def _period_label(ts) -> str:
    return pd.Timestamp(ts).strftime("%B %d, %Y").replace(" 0", " ")


def _parse_cftc_socrata_fallback(live_error: Exception | None = None):
    """Official Public Reporting current-row fallback for Consolidated + NQ."""
    rows = _socrata_rows({
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "1000",
    }, timeout=60)
    if not rows:
        raise RuntimeError("CFTC Socrata current rows empty")

    def dkey(row):
        return str(row.get("report_date_as_yyyy_mm_dd") or "")[:10]

    latest = max((dkey(r) for r in rows if dkey(r)), default="")
    if not latest:
        raise RuntimeError("CFTC Socrata current date missing")
    same = [r for r in rows if dkey(r) == latest]

    def code(row):
        return str(row.get("cftc_contract_market_code") or "").replace('"', "").strip()

    nq = next((r for r in same if code(r) == NQ_CFTC_CODE), None)
    cons = next(
        (
            r for r in same
            if "NASDAQ-100 Consolidated" in str(r.get("market_and_exchange_names") or "")
        ),
        None,
    )
    if cons is None:
        cons = next((r for r in same if code(r).startswith("20974") and code(r) != NQ_CFTC_CODE), None)
    if nq is None or cons is None:
        raise RuntimeError(
            f"CFTC Socrata latest markets missing: date={latest} consolidated={bool(cons)} nq={bool(nq)}"
        )

    def iv(row, key):
        v = parse_num(row.get(key))
        if v is None:
            raise RuntimeError(f"CFTC Socrata missing {key}")
        return int(v)

    period = datetime.strptime(latest, "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    prev_iso = ""
    prior_dates = sorted({dkey(r) for r in rows if dkey(r) and dkey(r) < latest}, reverse=True)
    if prior_dates:
        prev_iso = prior_dates[0]
    prev_period = (
        datetime.strptime(prev_iso, "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
        if prev_iso else "확인 불가"
    )

    asset_long = iv(cons, "asset_mgr_positions_long")
    asset_short = iv(cons, "asset_mgr_positions_short")
    lev_long = iv(cons, "lev_money_positions_long")
    lev_short = iv(cons, "lev_money_positions_short")
    open_interest = iv(cons, "open_interest_all")

    def change(row, key, current_key, market_code):
        val = parse_num(row.get(key))
        if val is not None:
            return int(val)
        if not prev_iso:
            raise RuntimeError(f"CFTC Socrata no prior date for {key}")
        prev = next((r for r in rows if dkey(r) == prev_iso and code(r) == market_code), None)
        if prev is None:
            raise RuntimeError(f"CFTC Socrata prior row missing for {market_code}")
        return iv(row, current_key) - iv(prev, current_key)

    ccode = code(cons)
    asset_long_wow = change(cons, "change_in_asset_mgr_long", "asset_mgr_positions_long", ccode)
    asset_short_wow = change(cons, "change_in_asset_mgr_short", "asset_mgr_positions_short", ccode)
    lev_long_wow = change(cons, "change_in_lev_money_long", "lev_money_positions_long", ccode)
    lev_short_wow = change(cons, "change_in_lev_money_short", "lev_money_positions_short", ccode)

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

    nq_oi = iv(nq, "open_interest_all")
    nq_long = iv(nq, "lev_money_positions_long")
    nq_short = iv(nq, "lev_money_positions_short")
    nq_long_wow = change(nq, "change_in_lev_money_long", "lev_money_positions_long", NQ_CFTC_CODE)
    nq_short_wow = change(nq, "change_in_lev_money_short", "lev_money_positions_short", NQ_CFTC_CODE)
    nq_oi_wow = change(nq, "change_in_open_interest_all", "open_interest_all", NQ_CFTC_CODE)
    nqi = {
        "contract": "NASDAQ MINI",
        "cftc_code": NQ_CFTC_CODE,
        "open_interest": nq_oi,
        "open_interest_wow": nq_oi_wow,
        "leveraged_long": nq_long,
        "leveraged_short": nq_short,
        "leveraged_net": nq_long - nq_short,
        "leveraged_long_wow": nq_long_wow,
        "leveraged_short_wow": nq_short_wow,
        "leveraged_net_wow": nq_long_wow - nq_short_wow,
        "short_share_oi_pct": nq_short / nq_oi * 100.0 if nq_oi else None,
        "previous_period": prev_period,
        "scope": "CFTC TFF NASDAQ MINI 전체시장 주간",
    }

    history_3y = cftc_nq_history_3y(nqi, period)
    core = {"source": "CFTC", "kind": "cot", "period": period, "metrics": metrics}
    return {
        **core,
        "url": CFTC_SOCRATA,
        "fingerprint": fp(core),
        "nq_mini": nqi,
        "history_3y": history_3y,
        "source_mode": "CFTC Public Reporting Socrata gpe5-46if",
        "live_source_error": (
            f"{type(live_error).__name__}: {live_error}" if live_error is not None else None
        ),
    }


def _parse_cftc_compressed_fallback(live_error: Exception | None = None):
    df, source_url = _tff_latest_rows_from_compressed()

    names = df["Market_and_Exchange_Names"].astype(str) if "Market_and_Exchange_Names" in df.columns else pd.Series("", index=df.index)
    codes = (
        df["CFTC_Contract_Market_Code"].astype(str)
        .str.replace('"', "", regex=False).str.strip().str.replace(r"\.0$", "", regex=True)
        if "CFTC_Contract_Market_Code" in df.columns
        else pd.Series("", index=df.index)
    )

    consolidated = df[names.str.contains("NASDAQ-100 Consolidated", case=False, na=False)].copy()
    if consolidated.empty:
        consolidated = df[codes.str.startswith("20974+")].copy()
    nqdf = df[codes == NQ_CFTC_CODE].copy()

    if consolidated.empty or nqdf.empty:
        raise RuntimeError(
            f"CFTC compressed fallback missing markets: consolidated={len(consolidated)} nq={len(nqdf)}"
        )

    consolidated = consolidated.sort_values("_date").drop_duplicates("_date", keep="last")
    nqdf = nqdf.sort_values("_date").drop_duplicates("_date", keep="last")
    crow = consolidated.iloc[-1]
    nrow = nqdf.iloc[-1]
    if pd.Timestamp(crow["_date"]) != pd.Timestamp(nrow["_date"]):
        raise RuntimeError(
            f"CFTC compressed fallback date mismatch: consolidated={crow['_date']} nq={nrow['_date']}"
        )

    period = _period_label(crow["_date"])
    previous_period = _period_label(consolidated.iloc[-2]["_date"]) if len(consolidated) >= 2 else "확인 불가"

    asset_long = _num_int(crow, "Asset_Mgr_Positions_Long_All")
    asset_short = _num_int(crow, "Asset_Mgr_Positions_Short_All")
    lev_long = _num_int(crow, "Lev_Money_Positions_Long_All")
    lev_short = _num_int(crow, "Lev_Money_Positions_Short_All")
    open_interest = _num_int(crow, "Open_Interest_All")
    critical = [asset_long, asset_short, lev_long, lev_short, open_interest]
    if any(x is None for x in critical):
        raise RuntimeError("CFTC compressed fallback critical consolidated fields missing")

    prev_crow = consolidated.iloc[-2] if len(consolidated) >= 2 else None
    def wow(change_key, value_key, current_value):
        v = _num_int(crow, change_key)
        if v is not None:
            return v
        if prev_crow is not None:
            prevv = _num_int(prev_crow, value_key)
            if prevv is not None:
                return int(current_value - prevv)
        raise RuntimeError(f"CFTC compressed fallback missing weekly change: {change_key}")

    asset_long_wow = wow("Change_in_Asset_Mgr_Long_All", "Asset_Mgr_Positions_Long_All", asset_long)
    asset_short_wow = wow("Change_in_Asset_Mgr_Short_All", "Asset_Mgr_Positions_Short_All", asset_short)
    lev_long_wow = wow("Change_in_Lev_Money_Long_All", "Lev_Money_Positions_Long_All", lev_long)
    lev_short_wow = wow("Change_in_Lev_Money_Short_All", "Lev_Money_Positions_Short_All", lev_short)

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
        "previous_period": previous_period,
    }

    nqi = {
        "contract": "NASDAQ MINI",
        "cftc_code": NQ_CFTC_CODE,
        "open_interest": _num_int(nrow, "Open_Interest_All"),
        "open_interest_wow": _num_int(nrow, "Change_in_Open_Interest_All"),
        "leveraged_long": _num_int(nrow, "Lev_Money_Positions_Long_All"),
        "leveraged_short": _num_int(nrow, "Lev_Money_Positions_Short_All"),
        "leveraged_long_wow": _num_int(nrow, "Change_in_Lev_Money_Long_All"),
        "leveraged_short_wow": _num_int(nrow, "Change_in_Lev_Money_Short_All"),
        "previous_period": _period_label(nqdf.iloc[-2]["_date"]) if len(nqdf) >= 2 else "확인 불가",
        "scope": "CFTC TFF NASDAQ MINI 전체시장 주간",
    }
    if any(nqi.get(k) is None for k in ("open_interest","open_interest_wow","leveraged_long","leveraged_short","leveraged_long_wow","leveraged_short_wow")):
        raise RuntimeError("CFTC compressed fallback critical NQ fields missing")
    nqi["leveraged_net"] = nqi["leveraged_long"] - nqi["leveraged_short"]
    nqi["leveraged_net_wow"] = nqi["leveraged_long_wow"] - nqi["leveraged_short_wow"]
    nqi["short_share_oi_pct"] = nqi["leveraged_short"] / nqi["open_interest"] * 100.0 if nqi["open_interest"] else None

    try:
        history_3y = cftc_nq_history_3y(nqi, period)
    except Exception as exc:
        history_3y = {"error": f"{type(exc).__name__}: {exc}"}

    core = {"source": "CFTC", "kind": "cot", "period": period, "metrics": metrics}
    return {
        **core,
        "url": source_url,
        "fingerprint": fp(core),
        "nq_mini": nqi,
        "history_3y": history_3y,
        "source_mode": "CFTC TFF official historical compressed fallback",
        "live_source_error": (
            f"{type(live_error).__name__}: {live_error}" if live_error is not None else None
        ),
    }


def parse_cftc():
    live_exc = None
    try:
        out = _parse_cftc_live()
        out["source_mode"] = "CFTC TFF live HTML"
        return out
    except Exception as exc:
        live_exc = exc
    try:
        return _parse_cftc_socrata_fallback(live_exc)
    except Exception as socrata_exc:
        out = _parse_cftc_compressed_fallback(live_exc)
        out["socrata_error"] = f"{type(socrata_exc).__name__}: {socrata_exc}"
        return out


def parse_cboe_section(text, heading, next_heading=None, required_time="03:15 PM"):
    start = text.find(heading)
    if start < 0:
        return None
    end = text.find(next_heading, start + len(heading)) if next_heading else len(text)
    if end < 0:
        end = len(text)
    block = text[start:end]

    rows = re.findall(
        r"(\d{1,2}:\d{2}\s*[AP]M)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+(\d+(?:\.\d+)?)",
        block,
        re.I,
    )
    if not rows:
        return None

    normalized_required = required_time.upper().replace("  ", " ")
    for row in rows:
        t, calls, puts, total, ratio = row
        normalized_time = t.upper().replace("  ", " ")
        if normalized_time == normalized_required:
            return {
                "time_ct": normalized_time,
                "calls": int(calls.replace(",", "")),
                "puts": int(puts.replace(",", "")),
                "total": int(total.replace(",", "")),
                "pc_ratio": float(ratio),
            }
    return None


def _parse_cboe_daily_volume_section(text, heading, next_heading=None):
    start = text.find(heading)
    if start < 0:
        return None
    end = text.find(next_heading, start + len(heading)) if next_heading else len(text)
    if end < 0:
        end = len(text)
    section = text[start:end]
    m = re.search(
        r"\bVOLUME\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        section,
        re.I,
    )
    if not m:
        return None
    calls = int(m.group(1).replace(",", ""))
    puts = int(m.group(2).replace(",", ""))
    total = int(m.group(3).replace(",", ""))
    if calls + puts != total:
        raise RuntimeError(
            f"Cboe daily {heading} volume arithmetic mismatch: "
            f"calls={calls} puts={puts} total={total}"
        )
    return {"calls": calls, "puts": puts, "total": total}


def _previous_weekday(day):
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _expected_completed_us_session():
    """Latest session that should have a final close, not the live intraday date."""
    now = datetime.now(NY)
    if now.weekday() < 5 and now.time() >= dt_time(16, 30):
        return now.date()
    d = now.date()
    if now.weekday() < 5:
        d = _previous_weekday(d)
    else:
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def _completed_session_candidates(limit=7):
    d = _expected_completed_us_session()
    out = []
    while len(out) < limit:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def fetch_cboe_daily_snapshot(period):
    """Use Cboe's date-specific Daily Market Statistics as the canonical EOD source.

    The live Market Statistics page is cumulative intraday and can surface inconsistent
    cached snapshots. The date-specific Daily page is treated as the end-of-day source
    for total/index/equity put-call ratios and call/put volumes.
    """
    d = datetime.strptime(period, "%A, %B %d, %Y").date()
    url = CBOE_DAILY_TEMPLATE.format(date=d.isoformat())
    h = browser_html(url)
    text = re.sub(r"\s+", " ", BeautifulSoup(h, "html.parser").get_text(" ", strip=True))

    ratio_patterns = {
        "total": r"TOTAL PUT/CALL RATIO\s+([0-9]+(?:\.[0-9]+)?)",
        "index": r"INDEX PUT/CALL RATIO\s+([0-9]+(?:\.[0-9]+)?)",
        "equity": r"EQUITY PUT/CALL RATIO\s+([0-9]+(?:\.[0-9]+)?)",
    }
    ratios = {}
    for key, pat in ratio_patterns.items():
        m = re.search(pat, text, re.I)
        if not m:
            raise RuntimeError(f"Cboe Daily Market Statistics ratio missing: {key} {d.isoformat()}")
        ratios[key] = float(m.group(1))

    total = _parse_cboe_daily_volume_section(
        text, "SUM OF ALL PRODUCTS", "INDEX OPTIONS"
    )
    index_opt = _parse_cboe_daily_volume_section(
        text, "INDEX OPTIONS", "EXCHANGE TRADED PRODUCTS"
    )
    equity = _parse_cboe_daily_volume_section(
        text, "EQUITY OPTIONS"
    )
    if not (total and index_opt and equity):
        raise RuntimeError(
            f"Cboe Daily Market Statistics EOD volume rows unavailable for {d.isoformat()}"
        )

    sections = {"total": total, "index": index_opt, "equity": equity}
    mismatches = []
    for key, sec in sections.items():
        calc = sec["puts"] / sec["calls"] if sec["calls"] else None
        if calc is None or abs(calc - ratios[key]) > 0.015:
            mismatches.append(
                f"{key}: volume-calc={calc if calc is not None else 'none'} "
                f"published={ratios[key]:.2f}"
            )
    if mismatches:
        raise RuntimeError(
            "Cboe Daily Market Statistics ratio/volume cross-check failed | "
            + " | ".join(mismatches)
        )

    metrics = {
        "total_pc_ratio": ratios["total"],
        "total_calls": total["calls"],
        "total_puts": total["puts"],
        "total_time_ct": "일별 마감",
        "equity_pc_ratio": ratios["equity"],
        "equity_calls": equity["calls"],
        "equity_puts": equity["puts"],
        "equity_time_ct": "일별 마감",
        "index_pc_ratio": ratios["index"],
        "index_calls": index_opt["calls"],
        "index_puts": index_opt["puts"],
        "index_time_ct": "일별 마감",
        "snapshot_type": "cboe_daily_eod",
        "final_snapshot": True,
        "daily_ratio_crosscheck": {
            "date": d.isoformat(),
            "total": ratios["total"],
            "index": ratios["index"],
            "equity": ratios["equity"],
            "url": url,
        },
    }
    core = {"source": "Cboe", "kind": "options", "period": period, "metrics": metrics}
    return {**core, "url": url, "fingerprint": fp(core)}


def parse_cboe():
    # Never treat the current intraday page as an end-of-day snapshot.
    # Try the latest completed U.S. session first and walk backward across holidays.
    errors = []
    for d in _completed_session_candidates(7):
        period = d.strftime("%A, %B %d, %Y").replace(" 0", " ")
        try:
            return fetch_cboe_daily_snapshot(period)
        except Exception as exc:
            errors.append(f"{d.isoformat()}:{type(exc).__name__}:{exc}")
    raise RuntimeError("Cboe completed-session EOD unavailable: " + " | ".join(errors))

def _nasdaq_sox_historical(expected_date):
    """Official Nasdaq historical API, restricted to completed sessions."""
    start = expected_date - timedelta(days=14)
    params = urllib.parse.urlencode({
        "assetclass": "index",
        "fromdate": start.isoformat(),
        "todate": expected_date.isoformat(),
        "limit": "20",
    })
    url = SOX_NASDAQ_HIST_API + "?" + params
    payload = get(url, timeout=40).json()
    data = (payload or {}).get("data") or {}
    table = data.get("tradesTable") or data.get("trades_table") or {}
    rows = table.get("rows") if isinstance(table, dict) else None
    if not isinstance(rows, list):
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_date = str(row.get("date") or row.get("tradeDate") or row.get("trade_date") or "").strip()
        d = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                d = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                pass
        if d is None or d > expected_date:
            continue
        close = parse_num(
            row.get("close")
            or row.get("last")
            or row.get("indexValue")
            or row.get("index_value")
            or row.get("value")
        )
        if close is not None:
            parsed.append((d, float(close)))
    if not parsed:
        raise RuntimeError("Nasdaq SOX historical API returned no completed closes")
    parsed.sort(key=lambda x: x[0])
    return parsed, url


def parse_sox():
    """Use completed-session closes only and cross-check Nasdaq vs Yahoo."""
    expected = _expected_completed_us_session()

    # Independent daily series: discard any current intraday bar after expected session.
    try:
        payload = get(SOX_YAHOO).json()
        result = (((payload or {}).get("chart") or {}).get("result") or [None])[0]
        if not result:
            raise RuntimeError("Yahoo SOX chart result missing")
        timestamps = result.get("timestamp") or []
        quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
        closes = quote.get("close") or []
        rows = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            day = datetime.fromtimestamp(int(ts), timezone.utc).astimezone(NY).date()
            if day <= expected:
                rows.append((day, float(close)))
        rows = sorted(dict(rows).items())
        if len(rows) < 2:
            raise RuntimeError("Yahoo SOX completed daily closes insufficient")
        yahoo_date, yahoo_latest = rows[-1]
        _, yahoo_prev = rows[-2]
    except Exception as exc:
        raise RuntimeError(f"SOX Yahoo completed-close cross-check unavailable: {type(exc).__name__}: {exc}")

    # Primary official route: Nasdaq historical API for the same completed date.
    nasdaq_errors = []
    nasdaq_latest = None
    official_url = None
    try:
        nrows, official_url = _nasdaq_sox_historical(expected)
        same = [x for x in nrows if x[0] == yahoo_date]
        if not same:
            raise RuntimeError(f"Nasdaq historical API missing {yahoo_date}")
        nasdaq_latest = same[-1][1]
    except Exception as exc:
        nasdaq_errors.append(f"historical API: {type(exc).__name__}: {exc}")

    # Secondary official route: GIW overview/history headline, accepted only when
    # it is already on the same completed date. Intraday/current-date values are rejected.
    if nasdaq_latest is None:
        for url in (SOX, SOX_OVERVIEW, SOX_OVERVIEW_FALLBACK):
            try:
                txt = BeautifulSoup(get(url).text, "html.parser").get_text(" ", strip=True)
                cur = re.search(
                    r"DATA AS OF\s+(\d{1,2}/\d{1,2}/20\d{2})\s+([\d,]+\.\d+)",
                    txt,
                    re.I,
                )
                if not cur:
                    raise RuntimeError("Nasdaq SOX headline date/level missing")
                day = datetime.strptime(cur.group(1), "%m/%d/%Y").date()
                if day != yahoo_date:
                    raise RuntimeError(
                        f"official headline is not completed target: {day} vs {yahoo_date}"
                    )
                nasdaq_latest = float(cur.group(2).replace(",", ""))
                official_url = url
                break
            except Exception as exc:
                nasdaq_errors.append(f"{url}: {type(exc).__name__}: {exc}")

    if nasdaq_latest is None:
        raise RuntimeError("SOX Nasdaq completed close unavailable: " + " | ".join(nasdaq_errors))

    if abs(yahoo_latest - nasdaq_latest) > 0.10:
        raise RuntimeError(
            f"SOX final-close mismatch: Nasdaq={nasdaq_latest:.2f}, Yahoo={yahoo_latest:.2f}"
        )

    latest = nasdaq_latest
    previous_close = yahoo_prev
    net_change = latest - previous_close
    pct = (latest / previous_close - 1.0) * 100.0 if previous_close else None
    if pct is None or abs(pct) > 25:
        raise RuntimeError(f"SOX cross-checked pct sanity failed: {pct}")

    metrics = {
        "value": latest,
        "previous_close": previous_close,
        "previous_close_source": "Yahoo daily close cross-check",
        "net_change": net_change,
        "net_change_source": "Nasdaq official completed close minus Yahoo prior daily close",
        "pct": pct,
        "d1_pct": pct,
        "official_overview_url": official_url,
        "crosscheck_url": SOX_YAHOO,
        "crosscheck_same_date": True,
        "crosscheck_close_diff": latest - yahoo_latest,
        "final_close_confirmed": True,
        "expected_completed_session": expected.isoformat(),
    }

    vals = [x[1] for x in rows]
    if len(vals) >= 4:
        metrics["d3_pct"] = (vals[-1] / vals[-4] - 1.0) * 100.0
    if len(vals) >= 6:
        metrics["d5_pct"] = (vals[-1] / vals[-6] - 1.0) * 100.0

    period = yahoo_date.strftime("%m/%d/%Y")
    core = {"source": "Nasdaq SOX", "kind": "sox", "period": period, "metrics": metrics}
    return {**core, "url": official_url, "fingerprint": fp(core)}


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
            net_pct3 = hist.get("net_short_percentile_3y")
            gross_pct3 = hist.get("gross_short_percentile_3y")
            net_pct10 = hist.get("net_short_percentile_10y")
            gross_pct10 = hist.get("gross_short_percentile_10y")
            bits = []
            if isinstance(net_pct3, (int, float)):
                bits.append(f"3년 순숏 {net_pct3:.0f}백분위")
            if isinstance(gross_pct3, (int, float)):
                bits.append(f"3년 총숏 {gross_pct3:.0f}백분위")
            if isinstance(net_pct10, (int, float)):
                bits.append(f"10년 순숏 {net_pct10:.0f}백분위")
            if isinstance(gross_pct10, (int, float)):
                bits.append(f"10년 총숏 {gross_pct10:.0f}백분위")
            pct_txt = (" · " + " / ".join(bits)) if bits else ""
            lines.append(
                f"• NQ E-mini Leveraged Funds: 순포지션 {int(nq.get('leveraged_net') or 0):+,}계약"
                f" | 주간 {int(nq.get('leveraged_net_wow') or 0):+,}계약{pct_txt}"
            )

    if cboe:
        m = cboe["metrics"]
        eq_pc = m.get("equity_pc_ratio")
        idx_pc = m.get("index_pc_ratio")
        total_pc = m.get("total_pc_ratio")
        if eq_pc is not None:
            eq_calls = m.get("equity_calls")
            eq_puts = m.get("equity_puts")
            eq_call_put = (
                eq_calls / eq_puts
                if eq_calls and eq_puts
                else (1.0 / eq_pc if eq_pc > 0 else None)
            )
            if idx_pc is not None:
                idx_desc = (
                    "거의 1:1"
                    if 0.90 <= idx_pc <= 1.10
                    else "풋 거래 우위"
                    if idx_pc > 1.10
                    else "콜 거래 우위"
                )
                lines.append(
                    f"• Cboe 옵션: 주식 P/C {eq_pc:.2f}"
                    f"({'콜이 풋의 ' + format(eq_call_put, '.2f') + '배' if eq_call_put else '비율 확인'})"
                    f" / 지수 P/C {idx_pc:.2f}({idx_desc})"
                    + (f" / 전체 {total_pc:.2f}" if total_pc is not None else "")
                )
            else:
                lines.append(
                    f"• Cboe 주식옵션 P/C {eq_pc:.2f} "
                    f"({m.get('equity_time_ct') or '일별 마감'})"
                    + (f" / 전체 {total_pc:.2f}" if total_pc is not None else "")
                )
        elif total_pc is not None:
            lines.append(f"• Cboe 전체 풋/콜 {total_pc:.2f}")

    sox_up = bool(sox and sox["metrics"].get("d1_pct", 0) > 0)
    cftc_lag_days = None
    if cftc and sox:
        try:
            cftc_date = datetime.strptime(cftc["period"], "%B %d, %Y").date()
            sox_date = datetime.strptime(sox["period"], "%m/%d/%Y").date()
            cftc_lag_days = (sox_date - cftc_date).days
        except Exception:
            cftc_lag_days = None

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

    lag_note = (
        f"CFTC는 {cftc['period']} 기준으로 SOX보다 {cftc_lag_days}일 느린 주간 자료"
        if cftc and isinstance(cftc_lag_days, int) and cftc_lag_days > 0
        else "CFTC는 주간 자료"
    )

    if sox_up and lev_improving and calls_favored:
        overall = (
            "SOX 마감 강세 + Cboe 주식옵션 콜 거래 우위가 확인됨. "
            f"{lag_note}이며, 당시 헤지펀드성 순포지션은 개선 방향 "
            "→ 상방 신호는 우호적이지만 당일 선물 포지션 동행으로 단정하지 않음"
        )
    elif sox_up and lev_improving:
        overall = (
            "SOX는 마감 기준 상승. "
            f"{lag_note}에서 헤지펀드성 순포지션은 개선됐지만 "
            "당일 가격 상승과 같은 시점의 포지션 변화로 볼 수는 없음"
        )
    elif sox_up and not lev_improving:
        overall = (
            "SOX는 마감 기준 강세지만 "
            f"{lag_note}에서 헤지펀드성 순포지션은 순숏 확대 방향 "
            "→ 현재 상승에 헤지펀드가 동행했는지는 다음 CFTC 갱신 전까지 미확인"
        )
    elif (not sox_up) and lev_improving:
        overall = (
            "SOX는 마감 기준 약세. "
            f"{lag_note}에서는 헤지펀드성 순포지션이 개선됐으나 "
            "시점이 달라 선행 신호로 단정하지 않음"
        )
    else:
        overall = (
            "SOX·Cboe 옵션과 CFTC 주간 포지션의 시점·방향이 완전히 정렬되지 않아 "
            "상방 추격 신호를 확정하지 않음"
        )

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

def validate_source_freshness(cftc_obj, cboe_obj, sox_obj):
    """Reject stale cached/report pages before they can advance Telegram state."""
    today = datetime.now(timezone(timedelta(hours=9))).date()
    problems = []

    def check(label, raw, max_days, formats):
        if not raw:
            problems.append(f"{label} 날짜 없음")
            return
        parsed = None
        text = str(raw).strip()
        for fmt in formats:
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            problems.append(f"{label} 날짜 파싱 실패: {text}")
            return
        age = (today - parsed).days
        if age < 0 or age > max_days:
            problems.append(f"{label} 자료 지연: {text} ({age}일)")

    if cftc_obj:
        check(
            "CFTC",
            cftc_obj.get("period"),
            10,
            ("%B %d, %Y", "%Y-%m-%d"),
        )
    if cboe_obj:
        check(
            "Cboe",
            cboe_obj.get("period"),
            4,
            ("%A, %B %d, %Y", "%B %d, %Y", "%m/%d/%Y"),
        )
    if sox_obj:
        check(
            "SOX",
            sox_obj.get("period"),
            4,
            ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y"),
        )
    return problems


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
        if not isinstance(hist.get("net_short_percentile_3y"), (int, float)):
            problems.append("CFTC NQ 3년 순숏 백분위 확인 불가")
        if not isinstance(hist.get("gross_short_percentile_3y"), (int, float)):
            problems.append("CFTC NQ 3년 총숏 백분위 확인 불가")
        if int(hist.get("sample_n") or 0) < 150:
            problems.append("CFTC NQ 3년 표본 부족")
        if hist.get("ten_year_complete"):
            for key in (
                "net_short_percentile_10y",
                "gross_short_percentile_10y",
                "short_share_oi_percentile_10y",
                "gross_short_weekly_build_percentile_10y",
                "net_short_weekly_build_percentile_10y",
            ):
                if not isinstance(hist.get(key), (int, float)):
                    problems.append(f"CFTC NQ 10년 검산값 누락: {key}")

    if cboe_obj:
        m = cboe_obj["metrics"]
        if m.get("final_snapshot") is not True or m.get("snapshot_type") != "cboe_daily_eod":
            problems.append("Cboe 일별 마감 공식 스냅샷 미확인")
        daily = m.get("daily_ratio_crosscheck") or {}
        for key, metric_key in (("total","total_pc_ratio"),("index","index_pc_ratio"),("equity","equity_pc_ratio")):
            if not isinstance(daily.get(key), (int, float)):
                problems.append(f"Cboe 일별 공식비율 검산 누락: {key}")
            elif abs(float(m.get(metric_key)) - float(daily.get(key))) > 0.01:
                problems.append(
                    f"Cboe 일별 공식비율 내부 불일치 {key}: {m.get(metric_key)} vs {daily.get(key)}"
                )
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
        if m.get("index_calls") and m.get("index_puts") and m.get("index_pc_ratio") is not None:
            calc = m["index_puts"] / m["index_calls"]
            if abs(calc - m["index_pc_ratio"]) > 0.03:
                problems.append(
                    f"Cboe 지수옵션 풋/콜 검산 불일치: 계산 {calc:.3f} vs 표 {m['index_pc_ratio']:.3f}"
                )

    if sox_obj:
        m = sox_obj["metrics"]
        if m.get("final_close_confirmed") is not True:
            problems.append("SOX 최종 종가 교차검증 미확인")
        if abs(float(m.get("crosscheck_close_diff", 999))) > 0.10:
            problems.append(
                f"SOX Nasdaq/Yahoo 최종 종가 차이 과대: {m.get('crosscheck_close_diff')}"
            )
        if abs(m.get("net_change", 0)) > 1 and abs(m.get("d1_pct", 0)) < 0.01:
            problems.append("SOX 순변동은 큰데 등락률이 0.00%로 모순")
        prev = m.get("previous_close")
        if prev and prev > 0:
            calc_pct = (m["value"] / prev - 1) * 100
            if abs(calc_pct - m["d1_pct"]) > 0.08:
                problems.append(
                    f"SOX 등락률 검산 불일치: 계산 {calc_pct:.2f}% vs 표 {m['d1_pct']:.2f}%"
                )

    if cboe_obj and sox_obj:
        try:
            cboe_date = datetime.strptime(cboe_obj["period"], "%A, %B %d, %Y").date()
            sox_date = datetime.strptime(sox_obj["period"], "%m/%d/%Y").date()
            if cboe_date != sox_date:
                problems.append(
                    f"Cboe/SOX 기준 거래일 불일치: Cboe={cboe_date} SOX={sox_date}"
                )
        except Exception as exc:
            problems.append(f"Cboe/SOX 거래일 검증 실패: {exc}")

    return problems


cftc_for_gate = next((x for x in results if x.get("kind") == "cot"), None)
cboe_for_gate = next((x for x in results if x.get("kind") == "options"), None)
sox_for_gate = next((x for x in results if x.get("kind") == "sox"), None)

validation_problems = validate_critical_sources(
    cftc_for_gate, cboe_for_gate, sox_for_gate
)
freshness_problems = validate_source_freshness(
    cftc_for_gate, cboe_for_gate, sox_for_gate
)
if validation_problems:
    errors.extend("검산: " + p for p in validation_problems)
if freshness_problems:
    errors.extend("신선도: " + p for p in freshness_problems)

quality_gate_ok = (
    required_kinds.issubset(present_kinds)
    and not validation_problems
    and not freshness_problems
)

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
            f"- freshness_gate_ok: {not freshness_problems}",
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
    def same_period_changed(prior, current):
        return bool(
            prior
            and current
            and prior.get("period") == current.get("period")
            and prior.get("fingerprint") != current.get("fingerprint")
        )

    correction = any([
        same_period_changed(prior_sox, sox),
        same_period_changed(prior_cboe, cboe),
        same_period_changed(prior_cftc, cftc),
    ])
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
            "• 미국 장 마감 후 Nasdaq 공식 종가와 Yahoo 일별 종가를 같은 날짜·0.10포인트 이내로 교차검증한 뒤 1D·3D·5D를 계산",
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
            f"→ {'헤지펀드성 순숏 축소·순포지션 개선' if m['lev_net_wow'] > 0 else '헤지펀드성 순숏 확대·순포지션 약화' if m['lev_net_wow'] < 0 else '변화 제한'}",
            f"• 기준일: {html.escape(cftc['period'])} — CFTC TFF는 주간 자료이므로 현재 SOX/Cboe 거래일과 시차가 있을 수 있음",
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
            if isinstance(hist.get("net_short_percentile_3y"), (int, float)):
                body += [
                    f"• 최근 3년 순숏: <b>{hist['net_short_percentile_3y']:.0f}백분위</b> · 총 숏 계약수 {hist.get('gross_short_percentile_3y', 0):.0f}백분위 · 숏/OI {hist.get('short_share_oi_percentile_3y', 0):.0f}백분위",
                    f"• 3년 극단 대비 축소율: 순숏 {hist.get('net_short_unwind_from_peak_pct', 0):.1f}% · 총숏 {hist.get('gross_short_unwind_from_peak_pct', 0):.1f}%",
                    f"• 숏 계약 변화: 1주 {int(hist.get('leveraged_short_1w_change') or 0):+,} · 4주 {int(hist.get('leveraged_short_4w_change') or 0):+,}",
                ]
                if hist.get("ten_year_complete") and isinstance(hist.get("net_short_percentile_10y"), (int, float)):
                    gross_record = "예" if hist.get("gross_short_weekly_record_10y") else "아니오"
                    net_record = "예" if hist.get("net_short_weekly_record_10y") else "아니오"
                    gross_week = int(hist.get('gross_short_weekly_change_10y') or 0)
                    net_build_week = int(hist.get('net_short_weekly_build_10y') or 0)
                    gross_word = "증가" if gross_week > 0 else "감소" if gross_week < 0 else "변화 없음"
                    net_word = "확대" if net_build_week > 0 else "축소" if net_build_week < 0 else "변화 없음"
                    gross_abs = abs(gross_week)
                    net_abs = abs(net_build_week)
                    body += [
                        f"• 최근 10년 순숏 {hist['net_short_percentile_10y']:.0f}백분위 · 총숏 {hist.get('gross_short_percentile_10y', 0):.0f}백분위 · 숏/OI {hist.get('short_share_oi_percentile_10y', 0):.0f}백분위",
                        f"• 이번 주 총숏 {gross_word} {gross_abs:,}계약 · 주간 총숏 변화 10년 {hist.get('gross_short_weekly_build_percentile_10y', 0):.0f}백분위"
                        + (f" · 10년 최대 증가 기록 여부 {gross_record}" if gross_week > 0 else ""),
                        f"• 이번 주 순숏 {net_word} {net_abs:,}계약 · 주간 순숏 변화 10년 {hist.get('net_short_weekly_build_percentile_10y', 0):.0f}백분위"
                        + (f" · 10년 최대 확대 기록 여부 {net_record}" if net_build_week > 0 else ""),
                        f"• 10년 최대 주간 총숏 증가 {int(hist.get('max_gross_short_weekly_build_10y') or 0):+,}계약 ({hist.get('max_gross_short_weekly_build_date_10y') or '날짜 확인 불가'})",
                    ]
                else:
                    body.append("• 10년 기록 판정: 공식 연도별 압축자료 일부 재조회 대기 — 10년 최고/백분위 단정 보류")
                body.append("※ 순숏·총숏·숏/OI·주간 숏 증가는 서로 다른 지표입니다. CFTC futures-only와 Goldman/BofA PB 독자 모델도 같은 모집단이 아닙니다.")
            elif hist.get("error"):
                body.append("• 백분위: 공식 압축자료 재조회 대기")
        body.append("")

    if cboe:
        m = cboe["metrics"]
        body += ["<b>Cboe 옵션 해석</b>"]

        eq_pc = m.get("equity_pc_ratio")
        eq_calls = m.get("equity_calls")
        eq_puts = m.get("equity_puts")
        idx_pc = m.get("index_pc_ratio")
        idx_calls = m.get("index_calls")
        idx_puts = m.get("index_puts")
        total_pc = m.get("total_pc_ratio")
        total_calls = m.get("total_calls")
        total_puts = m.get("total_puts")

        if eq_pc is not None and eq_calls and eq_puts:
            eq_call_share = eq_calls / (eq_calls + eq_puts) * 100.0
            eq_call_put = eq_calls / eq_puts if eq_puts else None
            eq_desc = "콜 거래 우위" if eq_pc < 0.80 else "혼재·중립권" if eq_pc <= 1.0 else "풋 거래 우위"
            body.append(
                f"• 주식옵션: 콜 {eq_calls:,} / 풋 {eq_puts:,} → P/C {eq_pc:.2f} "
                f"({m.get('equity_time_ct') or '일별 마감'})"
            )
            body.append(
                f"  → 콜이 풋의 {eq_call_put:.2f}배 · 콜+풋 거래량 중 콜 {eq_call_share:.1f}% "
                f"→ <b>{eq_desc}</b>"
            )
        elif eq_pc is not None:
            body.append(
                f"• 주식옵션 P/C {eq_pc:.2f} "
                f"→ {'콜 거래 우위' if eq_pc < 0.80 else '혼재·중립권' if eq_pc <= 1.0 else '풋 거래 우위'}"
            )

        if idx_pc is not None and idx_calls and idx_puts:
            idx_call_share = idx_calls / (idx_calls + idx_puts) * 100.0
            if 0.90 <= idx_pc <= 1.10:
                idx_desc = "콜·풋이 거의 1:1 → 지수 전체 방향성·헤지는 중립권"
            elif idx_pc > 1.10:
                idx_desc = "풋 우위 → 지수 하락 방어·헤지 수요가 상대적으로 강함"
            else:
                idx_desc = "콜 우위 → 지수 상방 수요가 상대적으로 강함"
            body.append(
                f"• 지수옵션: 콜 {idx_calls:,} / 풋 {idx_puts:,} → P/C {idx_pc:.2f} "
                f"({m.get('index_time_ct') or '일별 마감'})"
            )
            body.append(f"  → 콜 비중 {idx_call_share:.1f}% · {idx_desc}")
        elif idx_pc is not None:
            body.append(
                f"• 지수옵션 P/C {idx_pc:.2f} "
                f"→ {'거의 1:1·중립권' if 0.90 <= idx_pc <= 1.10 else '풋 우위·헤지 강화' if idx_pc > 1.10 else '콜 우위'}"
            )

        if total_pc is not None and total_calls and total_puts:
            total_call_share = total_calls / (total_calls + total_puts) * 100.0
            total_call_put = total_calls / total_puts if total_puts else None
            body.append(
                f"• Cboe 전체 옵션: 콜 {total_calls:,} / 풋 {total_puts:,} → P/C {total_pc:.2f} "
                f"({m.get('total_time_ct') or '일별 마감'})"
            )
            body.append(
                f"  → 콜이 풋의 {total_call_put:.2f}배 · 콜 비중 {total_call_share:.1f}%"
            )
        elif total_pc is not None:
            body.append(f"• 전체 풋/콜 {total_pc:.2f}")

        if eq_pc is not None and idx_pc is not None:
            eq_regime, idx_regime = option_regimes(eq_pc, idx_pc)

            if eq_regime == "call" and idx_regime == "call":
                option_combo = (
                    "개별주와 지수 모두 콜 거래 우위 "
                    "→ 옵션 거래량 기준으로 상방 성향이 같은 방향으로 정렬"
                )
            elif eq_regime == "call" and idx_regime == "neutral":
                option_combo = (
                    "개별주에서는 콜 거래 우위지만 지수는 거의 중립 "
                    "→ 종목별 상방 성향은 있으나 시장 전체 위험선호는 중립에 가까움"
                )
            elif eq_regime == "call" and idx_regime == "put":
                option_combo = (
                    "개별주 콜 거래 우위와 지수 풋 거래 우위가 동시에 나타남 "
                    "→ 종목 상방 성향과 시장 전체 하락 방어가 공존하는 혼합 신호"
                )
            elif eq_regime == "neutral" and idx_regime == "call":
                option_combo = (
                    "개별주는 중립권이고 지수는 콜 거래 우위 "
                    "→ 시장 전체 상방 성향이 상대적으로 더 강한 조합"
                )
            elif eq_regime == "neutral" and idx_regime == "neutral":
                option_combo = "개별주와 지수 모두 중립권 → 옵션 거래량만으로 방향성 우위가 뚜렷하지 않음"
            elif eq_regime == "neutral" and idx_regime == "put":
                option_combo = "개별주는 중립권이고 지수는 풋 거래 우위 → 지수 방어·헤지 성향이 상대적으로 강함"
            elif eq_regime == "put" and idx_regime == "call":
                option_combo = (
                    "개별주는 풋 거래 우위, 지수는 콜 거래 우위 "
                    "→ 개별주 경계와 지수 상방 성향이 엇갈리는 혼합 신호"
                )
            elif eq_regime == "put" and idx_regime == "neutral":
                option_combo = "개별주는 풋 거래 우위지만 지수는 중립 → 개별주 하방 경계가 상대적으로 더 강함"
            else:
                option_combo = "개별주와 지수 모두 풋 거래 우위 → 옵션 거래량 기준으로 하방·방어 성향이 같은 방향으로 정렬"
            body.append(f"• <b>옵션 조합</b>: {option_combo}")

        if cftc:
            cm = cftc["metrics"]
            asset_dir = "기관 순롱 확대" if cm["asset_net_wow"] > 0 else "기관 순롱 축소" if cm["asset_net_wow"] < 0 else "기관 변화 제한"
            lev_dir = (
                "헤지펀드성 순숏 축소·순포지션 개선"
                if cm["lev_net_wow"] > 0
                else "헤지펀드성 순숏 확대·순포지션 약화"
                if cm["lev_net_wow"] < 0
                else "헤지펀드성 변화 제한"
            )
            lag_text = ""
            if sox:
                try:
                    cftc_d = datetime.strptime(cftc["period"], "%B %d, %Y").date()
                    sox_d = datetime.strptime(sox["period"], "%m/%d/%Y").date()
                    lag_days = (sox_d - cftc_d).days
                    if lag_days > 0:
                        lag_text = f" · CFTC 기준일이 SOX/Cboe보다 {lag_days}일 느림"
                except Exception:
                    pass
            body.append(
                f"• <b>CFTC와 연결</b>: {asset_dir} + {lev_dir}{lag_text} "
                "→ 같은 날의 옵션·선물 동행으로 단정하지 않고 다음 CFTC 갱신에서 확인"
            )

        body.append(
            "• 기준: Cboe의 날짜별 Daily Market Statistics 마감 통계만 사용. 장중 누적값은 알림에 사용하지 않음"
        )
        body.append(
            "• 주의: 풋/콜은 거래량 비율이라 콜·풋의 실제 매수/매도 방향을 구분하지 않음. "
            "콜 거래가 많아도 콜 매도가 섞일 수 있어 단독 강세·약세 확정 신호로 쓰지 않음"
        )
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

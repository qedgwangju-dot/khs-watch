#!/usr/bin/env python3
import os, re, json, hashlib, html
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote, urljoin
from email.utils import parsedate_to_datetime

import requests
import pandas as pd
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)
ALERT = OUT / "us_fund_flow_alert.html"
STATUS = OUT / "us_fund_flow_status.md"
PENDING = OUT / "us_fund_flow_pending_state.json"
STATE = DATA / "us_fund_flow_state.json"

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

ICI_COMBINED = "https://www.ici.org/research/stats/combined_flows"
ICI_MMF = "https://www.ici.org/research/stats/mmf"
FINRA_MARGIN = "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"
BING_Bofa = 'BofA EPFR US stocks money market Reuters'
BING_LIPPER = 'LSEG Lipper U.S. equity funds money market Reuters'
JPM_ALL_TOPICS = "https://www.jpmorganchase.com/institute/all-topics"
JPM_HOUSEHOLD = "https://www.jpmorganchase.com/institute/all-topics/household-financial-health/drawing-on-investment-wealth-full-report"
FED_Z1 = "https://www.federalreserve.gov/releases/z1/default.htm"
FED_Z1_EQUITY_TABLE = "https://www.federalreserve.gov/releases/z1/dataviz/z1/balance_sheet/table/"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
FRED_SP500 = "https://fred.stlouisfed.org/series/SP500"
FRED_YIELDS = "https://fred.stlouisfed.org/series/DGS10"
FRED_FED_POLICY = "https://fred.stlouisfed.org/series/DFEDTARU"
TREASURY_OFFICIAL_CURVE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value=2026"
FED_MONETARY_RSS = "https://www.federalreserve.gov/feeds/press_monetary.xml"
FED_CURRENT_VERIFIED_FALLBACK = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
HARTNETT_REPORT_DATE = "October 9, 2026"
HARTNETT_REPORT_WEEK = "October 7, 2026"
HARTNETT_REPORT_URL = "https://ca.finance.yahoo.com/news/investors-pour-cash-set-stay-084543679.html"
HARTNETT_MMF_REPORTED_BN = 166.4  # Bloomberg citing Hartnett/BofA; not an ICI observation.
HARTNETT_TRACK_VERSION = "2026-10-09-v1"
US_MIDTERM_DATE = datetime(2026, 11, 3).date()
YAHOO_SP500_API = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5y&interval=1d&includePrePost=false&events=div%2Csplits"
YAHOO_SP500 = "https://finance.yahoo.com/quote/%5EGSPC/"
FRED_SERIES = {
    "household_equities": "BOGZ1LM153064475Q",
    "household_financial_assets": "TFAABSHNO",
    "household_total_assets": "TABSHNO",
    "household_net_worth": "TNWBSHNO",
}


def get(url, timeout=35):
    r = S.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


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
        raise RuntimeError("system Chrome/Chromium not found")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=exe,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(user_agent=UA, locale="en-US")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        out = page.content()
        browser.close()
        return out


def load_state():
    # A damaged or unreadable state must never be mistaken for a first run:
    # resetting all fingerprints would replay previously delivered alerts.
    if not STATE.exists():
        raise RuntimeError("US fund-flow state missing; fail closed to avoid replaying historical alerts")
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("US fund-flow state unreadable; fail closed to avoid duplicate Telegram delivery") from exc
    if not isinstance(value, dict) or not isinstance(value.get("seen"), dict) or not isinstance(value.get("values"), dict):
        raise RuntimeError("US fund-flow state schema invalid; fail closed to avoid duplicate Telegram delivery")
    return value


def parse_num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)) and pd.notna(x):
        return float(x)
    s = str(x).replace(",", "").replace("$", "").replace("%", "").strip()
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def clean_text(x):
    return re.sub(r"\s+", " ", BeautifulSoup(str(x), "html.parser").get_text(" ", strip=True)).strip()


def _canonicalize_semantic(v):
    # Numeric JSON spelling must not create false changes: 34 and 34.0 are the same metric.
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _canonicalize_semantic(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_canonicalize_semantic(val) for val in v]
    if isinstance(v, (int, float)):
        return float(v)
    return v


def semantic_core(x):
    """Only economically meaningful fields participate in duplicate detection."""
    return {
        "source": x.get("source"),
        "kind": x.get("kind"),
        "period": x.get("period"),
        "metrics": _canonicalize_semantic(x.get("metrics") or {}),
    }


def semantic_fingerprint(x):
    return hashlib.sha256(
        json.dumps(semantic_core(x), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def fetch_fx():
    key = (os.getenv("ECOS_API_KEY") or "").strip()
    if not key:
        return None
    today = datetime.now(timezone(timedelta(hours=9))).date()
    start = (today - timedelta(days=12)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/731Y001/D/{start}/{end}/0000001"
    try:
        j = get(url).json()
        rows = (j.get("StatisticSearch") or {}).get("row") or []
        vals = []
        for row in rows:
            v = parse_num(row.get("DATA_VALUE"))
            d = str(row.get("TIME") or "")
            if v is not None and d:
                vals.append((d, v))
        vals.sort()
        if vals:
            date_text, rate = vals[-1]
            observed = datetime.strptime(date_text, "%Y%m%d").date()
            # Never treat a wildly invalid rate or a stale cached observation as current.
            if not (500.0 <= rate <= 3000.0) or not (0 <= (today-observed).days <= 5):
                return None
            return {"date": date_text, "usdkrw": rate}
    except Exception:
        return None
    return None


def krw_trillion(bn_usd, fx):
    if bn_usd is None or not fx:
        return None
    return bn_usd * fx["usdkrw"] / 1000.0


def fmt_krw_trillion(v, signed=False):
    if v is None:
        return "원화 환산 확인 불가"
    # An '0.01 trillion won' display can erase up to 50억 of useful precision.
    total_eok = round(abs(v) * 10000.0)
    jo, eok = divmod(total_eok, 10000)
    if jo and eok:
        amount = f"{jo:,}조{eok:,}억원"
    elif jo:
        amount = f"{jo:,}조원"
    else:
        amount = f"{eok:,}억원"
    sign = "-" if v < 0 else "+" if signed and v > 0 else ""
    return f"약 {sign}{amount}"


def fmt_usd_bn_kr(x, fx):
    if x is None:
        return "확인 불가"
    sign = "-" if x < 0 else "+" if x > 0 else ""
    usd_eok = f"{abs(x)*10:,.2f}".rstrip("0").rstrip(".")
    base = f"{sign}{usd_eok}억달러"
    kr = krw_trillion(x, fx) if fx else None
    return f"{base}({fmt_krw_trillion(kr, signed=True)})"


def fmt_usd_trillion_kr(x, fx):
    if x is None:
        return "확인 불가"
    base = f"{x:,.3f}조달러"
    kr = x * fx["usdkrw"] if fx else None
    return f"{base}({fmt_krw_trillion(kr, signed=False)})"


def first_date(text):
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}",
        text,
    )
    return m.group(0) if m else None


def normalize_columns(t):
    out = t.copy()
    cols = []
    for c in out.columns:
        if isinstance(c, tuple):
            vals = [str(v).strip() for v in c if str(v).strip().lower() not in ("nan", "")]
            cols.append(" | ".join(vals))
        else:
            cols.append(str(c).strip())
    out.columns = cols
    return out


def fred_series_rows(series_id):
    url = FRED_CSV.format(series=quote(series_id))
    r = get(url, timeout=35)
    t = pd.read_csv(StringIO(r.text))
    if t.empty or len(t.columns) < 2:
        raise RuntimeError(f"FRED {series_id} data empty")
    date_col = t.columns[0]
    value_col = series_id if series_id in t.columns else t.columns[-1]
    t = t[[date_col, value_col]].copy()
    t.columns = ["date", "value"]
    t["date"] = pd.to_datetime(t["date"], errors="coerce")
    t["value"] = pd.to_numeric(t["value"], errors="coerce")
    t = t.dropna().sort_values("date")
    if t.empty:
        raise RuntimeError(f"FRED {series_id} numeric rows not found")
    return t


def latest_fred(series_id):
    t = fred_series_rows(series_id)
    latest = t.iloc[-1]
    prev = t.iloc[-2] if len(t) >= 2 else None
    return {
        "date": latest["date"].date(),
        "value": float(latest["value"]),
        "prev_date": prev["date"].date() if prev is not None else None,
        "prev_value": float(prev["value"]) if prev is not None else None,
        "rows": t,
    }


def quarter_label(d):
    return f"{d.year}:Q{((d.month - 1) // 3) + 1}"


def _jpm_candidate_urls():
    urls = [JPM_HOUSEHOLD]
    try:
        page_html = browser_html(JPM_ALL_TOPICS)
        soup = BeautifulSoup(page_html, "html.parser")
        candidates = []
        for a in soup.find_all("a", href=True):
            label = clean_text(a.get_text(" ", strip=True))
            href = urljoin(JPM_ALL_TOPICS, a.get("href"))
            if "/institute/all-topics/household-financial-health/" not in href:
                continue
            if not re.search(r"invest|wealth|spend|financial market", label + " " + href, re.I):
                continue
            candidates.append(href)
        expanded = []
        for u in candidates[:8]:
            expanded.append(u)
            try:
                raw = get(u, timeout=25).text
                ss = BeautifulSoup(raw, "html.parser")
                for a in ss.find_all("a", href=True):
                    href = urljoin(u, a.get("href"))
                    label = clean_text(a.get_text(" ", strip=True))
                    if "full-report" in href or re.search(r"full report", label, re.I):
                        expanded.append(href)
            except Exception:
                pass
        urls = expanded + urls
    except Exception:
        pass
    out = []
    seen = set()
    for u in urls:
        u = u.split("#", 1)[0]
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def parse_jpm_household():
    last_error = None
    for url in _jpm_candidate_urls():
        try:
            try:
                raw = get(url, timeout=35).text
                text = clean_text(raw)
            except Exception:
                text = clean_text(browser_html(url))

            # Require the same concepts used in the Institute's withdrawal/spending study.
            if not re.search(r"net withdrawals|withdrew money from investments|investment accounts", text, re.I):
                continue
            if not re.search(r"spending", text, re.I):
                continue

            m_all = re.search(
                r"By this measure,\s*([\d.]+)\s*percent of people withdrew money from investments.*?"
                r"over\s+([A-Za-z]+[–—-][A-Za-z]+\s+20\d{2})",
                text, re.I | re.S,
            )
            if not m_all:
                m_all = re.search(
                    r"([\d.]+)\s*percent of people withdrew money from investments.*?"
                    r"over\s+([A-Za-z]+[–—-][A-Za-z]+\s+20\d{2})",
                    text, re.I | re.S,
                )
            m_top = re.search(
                r"top income segment rose from\s*[\d.]+\s*percent.*?to\s*([\d.]+)\s*percent",
                text, re.I | re.S,
            )
            m_low = re.search(
                r"compared with a rise from\s*[\d.]+\s*percent to\s*([\d.]+)\s*percent among those below the median",
                text, re.I | re.S,
            )
            m_spend = re.search(
                r"reaching\s*([\d.]+)\s*percent in\s+([A-Za-z]+\s+20\d{2})",
                text, re.I,
            )
            if not (m_all and m_top and m_low and m_spend):
                continue

            period = m_all.group(2).replace("–", "-").replace("—", "-")
            payload = {
                "source": "JPMorganChase Institute",
                "kind": "household_withdrawals",
                "period": period,
                "published": first_date(text),
                "url": url,
                "metrics": {
                    "withdrawers_all_pct": float(m_all.group(1)),
                    "withdrawers_top10_pct": float(m_top.group(1)),
                    "withdrawers_below_median_pct": float(m_low.group(1)),
                    "spending_funded_pct": float(m_spend.group(1)),
                },
            }
            payload["fingerprint"] = semantic_fingerprint(payload)
            return payload
        except Exception as e:
            last_error = e
    raise RuntimeError(f"JPMorgan household withdrawal metrics not found: {last_error or 'no matching official report'}")


def parse_fed_household_balance_sheet():
    # Use the Board of Governors' official household-balance-sheet visualization table.
    # It is a stable current-release endpoint and exposes the exact quarterly levels needed
    # without depending on FRED availability.
    r = get(FED_Z1_EQUITY_TABLE, timeout=45)
    tables = pd.read_html(StringIO(r.text))
    target = None
    for raw in tables:
        t = normalize_columns(raw)
        cols = [str(x) for x in t.columns]
        joined = " ".join(cols)
        if (
            re.search(r"Quarter", joined, re.I)
            and re.search(r"Total assets", joined, re.I)
            and re.search(r"Total liabilities", joined, re.I)
            and re.search(r"Financial assets: Directly held stock", joined, re.I)
            and re.search(r"Financial assets: Indirectly held stock", joined, re.I)
        ):
            target = t
            break
    if target is None:
        raise RuntimeError("Federal Reserve household balance-sheet visualization table not found")

    def col_match(pattern, reject=None):
        for col in target.columns:
            s = str(col)
            if re.search(pattern, s, re.I) and (not reject or not re.search(reject, s, re.I)):
                return col
        return None

    q_col = col_match(r"\bQuarter\b")
    assets_col = col_match(r"^Total assets\b", r"/\s*DPI|percent|%")
    liabilities_col = col_match(r"^Total liabilities\b", r"/\s*DPI|percent|%")
    fin_col = col_match(r"^Financial assets\b", r":|/\s*DPI|percent|%")
    direct_stock_col = col_match(r"Financial assets:\s*Directly held stock\b", r"/\s*DPI|percent|%")
    indirect_stock_col = col_match(r"Financial assets:\s*Indirectly held stock\b", r"/\s*DPI|percent|%")

    needed = {
        "quarter": q_col,
        "assets": assets_col,
        "liabilities": liabilities_col,
        "financial_assets": fin_col,
        "direct_stock": direct_stock_col,
        "indirect_stock": indirect_stock_col,
    }
    missing = [k for k, v in needed.items() if v is None]
    if missing:
        raise RuntimeError(
            "Federal Reserve balance-sheet columns missing: "
            + ", ".join(missing)
            + " | "
            + " || ".join(map(str, target.columns))
        )

    rows = []
    for _, row in target.iterrows():
        period = clean_text(row[q_col])
        if not re.fullmatch(r"20\d{2}:Q[1-4]", period):
            continue
        vals = {
            "period": period,
            "assets": parse_num(row[assets_col]),
            "liabilities": parse_num(row[liabilities_col]),
            "financial_assets": parse_num(row[fin_col]),
            "direct_stock": parse_num(row[direct_stock_col]),
            "indirect_stock": parse_num(row[indirect_stock_col]),
        }
        if all(vals[k] is not None for k in ("assets","liabilities","financial_assets","direct_stock","indirect_stock")):
            rows.append(vals)
    if not rows:
        raise RuntimeError("Federal Reserve household balance-sheet quarterly rows not found")

    def qkey(p):
        m = re.fullmatch(r"(20\d{2}):Q([1-4])", p)
        return (int(m.group(1)), int(m.group(2)))
    latest = max(rows, key=lambda x: qkey(x["period"]))

    equities_bn = latest["direct_stock"] + latest["indirect_stock"]
    net_worth_bn = latest["assets"] - latest["liabilities"]
    metrics = {
        "equities_trillion": round(equities_bn / 1000.0, 4),
        "financial_assets_trillion": round(latest["financial_assets"] / 1000.0, 4),
        "total_assets_trillion": round(latest["assets"] / 1000.0, 4),
        "net_worth_trillion": round(net_worth_bn / 1000.0, 4),
        "equities_share_total_assets_pct": round(equities_bn / latest["assets"] * 100.0, 1),
        "equities_share_financial_assets_pct": round(equities_bn / latest["financial_assets"] * 100.0, 1),
    }
    payload = {
        "source": "Federal Reserve Z.1",
        "kind": "household_balance_sheet",
        "period": latest["period"],
        "published": None,
        "url": FED_Z1_EQUITY_TABLE,
        "metrics": metrics,
    }
    payload["fingerprint"] = semantic_fingerprint(payload)
    return payload

def _sp500_from_yahoo():
    j = get(YAHOO_SP500_API, timeout=25).json()
    result = ((j.get("chart") or {}).get("result") or [])
    if not result:
        raise RuntimeError("Yahoo S&P 500 chart result empty")
    r = result[0]
    timestamps = r.get("timestamp") or []
    quotes = (((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    rows = []
    for ts, close in zip(timestamps, quotes):
        if close is None:
            continue
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        rows.append((pd.Timestamp(d.date()), float(close)))
    if not rows:
        raise RuntimeError("Yahoo S&P 500 close rows empty")
    t = pd.DataFrame(rows, columns=["date", "value"]).drop_duplicates("date").sort_values("date")
    return t, "Yahoo Finance", YAHOO_SP500


def fetch_sp500_context():
    errors = []
    try:
        # FRED remains the preferred public series, but do not let an outage disable the risk gate.
        t = fred_series_rows("SP500")
        source, source_url = "FRED", FRED_SP500
    except Exception as e:
        errors.append(f"FRED={type(e).__name__}:{e}")
        try:
            t, source, source_url = _sp500_from_yahoo()
        except Exception as e2:
            errors.append(f"Yahoo={type(e2).__name__}:{e2}")
            raise RuntimeError("S&P 500 sources unavailable | " + " | ".join(errors))

    latest = t.iloc[-1]
    cutoff = latest["date"] - pd.Timedelta(days=365 * 5)
    recent = t[t["date"] >= cutoff].copy()
    peak_i = recent["value"].idxmax()
    peak = recent.loc[peak_i]
    last_value = float(latest["value"])
    peak_value = float(peak["value"])
    drawdown_pct = (last_value / peak_value - 1.0) * 100.0
    return {
        "last_date": latest["date"].date().isoformat(),
        "last_value": last_value,
        "peak_date": peak["date"].date().isoformat(),
        "peak_value": peak_value,
        "drawdown_pct": round(drawdown_pct, 2),
        "band": "stress" if drawdown_pct <= -15.0 else "normal",
        "source": source,
        "url": source_url,
    }


def _treasury_official_history():
    """Daily par yields; compare 2-year and 10-year on one official date."""
    treasury_year = datetime.now(ZoneInfo("America/New_York")).year
    yearly_url = TREASURY_OFFICIAL_CURVE.replace("field_tdr_date_value=2026", f"field_tdr_date_value={treasury_year}")
    r = get(yearly_url, timeout=20)
    tables = pd.read_html(StringIO(r.text))
    candidates = []
    for tab in tables:
        t = normalize_columns(tab)
        date_col = next((x for x in t.columns if re.fullmatch(r"Date", str(x), re.I)), None)
        two_col = next((x for x in t.columns if re.fullmatch(r"2\s*YR", str(x), re.I)), None)
        ten_col = next((x for x in t.columns if re.fullmatch(r"10\s*YR", str(x), re.I)), None)
        if not (date_col and two_col and ten_col):
            continue
        for _, row in t.iterrows():
            try:
                d = datetime.strptime(str(row[date_col]).strip(), "%m/%d/%Y").date()
            except Exception:
                continue
            y2, y10 = parse_num(row[two_col]), parse_num(row[ten_col])
            if y2 is not None and y10 is not None and 0.1 < y2 < 20 and 0.1 < y10 < 20:
                candidates.append((d, y2, y10))
    by_date = {x[0]: x for x in candidates}
    dates = sorted(by_date)
    if len(dates) < 6:
        raise RuntimeError(f"US Treasury official 2Y/10Y rows insufficient: {len(dates)}")
    latest = by_date[dates[-1]]
    prior_5 = by_date[dates[-6]]
    return {
        "date": latest[0], "y2": latest[1], "y10": latest[2],
        "five_day_bp": round((latest[2] - prior_5[2]) * 100.0, 1),
        "source_url": yearly_url,
    }


def _fractional_rate(x):
    s = str(x).strip()
    if "-" in s:
        whole, frac = s.split("-", 1)
        num, den = frac.split("/", 1)
        return float(whole) + float(num)/float(den)
    return float(s)


def _fed_target_from_official():
    """Require dated Fed FOMC statement; never infer policy from Treasury yields."""
    today = datetime.now(ZoneInfo("America/New_York")).date()
    candidates = []
    try:
        for item in rss_items(FED_MONETARY_RSS):
            url = str(item.get("link") or "")
            m = re.search(r"monetary(20\d{6})a\.htm", url)
            if m:
                d = datetime.strptime(m.group(1), "%Y%m%d").date()
                if d <= today:
                    candidates.append((d,url))
    except Exception:
        pass
    candidates.append((datetime(2026,9,16).date(), FED_CURRENT_VERIFIED_FALLBACK))
    candidates = sorted(set(candidates), reverse=True)
    last_error = "none"
    for d,url in candidates:
        if (today-d).days > 40:
            continue
        try:
            page = clean_text(get(url, timeout=16).text)
            if not re.search(r"federal funds rate", page, re.I):
                continue
            m = re.search(
                r"target range for the federal funds rate.{0,100}?\b(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s+to\s+(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s+percent",
                page, re.I
            )
            if not m:
                last_error = f"FOMC target range not found in {url}"
                continue
            low,upper = _fractional_rate(m.group(1)), _fractional_rate(m.group(2))
            if not (0 <= low <= upper <= 20 and 0.1 <= upper-low <= 1.0):
                raise RuntimeError(f"FOMC target range outside sanity checks: {low}–{upper}")
            return {"rate_upper":upper,"date":d,"url":url}
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
    raise RuntimeError("No verified current FOMC statement: "+last_error)


def bond_yield_band(y10):
    """In-house risk zones, NOT BofA targets or forecasts."""
    if y10 >= 6.00:
        return "at_or_above_6_00"
    if y10 >= 5.50:
        return "5_50_to_6_00"
    if y10 >= 5.30:
        return "5_30_to_5_50"
    return "below_5_30"

assert bond_yield_band(5.24) == "below_5_30"
assert bond_yield_band(5.30) == "5_30_to_5_50"
assert bond_yield_band(5.50) == "5_50_to_6_00"
assert bond_yield_band(6.00) == "at_or_above_6_00"


def fetch_hartnett_macro_context():
    """Official Treasury and FOMC only; withhold joint interpretation on failure."""
    curve = _treasury_official_history()
    fed = _fed_target_from_official()
    dt = curve["date"]
    today = datetime.now(ZoneInfo("America/New_York")).date()
    if not (0 <= (today-dt).days <= 7):
        raise RuntimeError(f"US Treasury yields stale or future-dated: {dt}")
    y10,y2,upper = float(curve["y10"]),float(curve["y2"]),float(fed["rate_upper"])
    five_bp = curve["five_day_bp"]
    return {
        "treasury_date":dt.isoformat(),
        "yield_10y_pct":round(y10,3), "yield_2y_pct":round(y2,3),
        "yield_10y_5d_bp":five_bp,
        "curve_10y_minus_2y_bp":round((y10-y2)*100.0,1),
        "fed_target_upper_pct":round(upper,3),
        "fed_effective_date":fed["date"].isoformat(),
        "bond_level":bond_yield_band(y10),
        "bond_momentum":"rise_20bp" if five_bp>=20 else "fall_20bp" if five_bp<=-20 else "neutral",
        "url_yields":curve["source_url"],
        "url_fed":fed["url"],
    }

def election_window_label(reference_date):
    """A calendar reminder is not a forecast of an election outcome."""
    days = (US_MIDTERM_DATE - reference_date).days
    if days > 7:
        return "outside"
    if 1 <= days <= 7:
        return "within_7_days"
    if days == 0:
        return "election_day"
    if -3 <= days < 0:
        return "post_election_window"
    return "past"


def new_bond_momentum_episode(previous, current):
    """Neutral resets must re-arm the next genuinely new +/-20bp episode."""
    return current in ("rise_20bp","fall_20bp") and previous != current


# Regression guards: repeat alerts require a silent neutral reset between episodes.
assert new_bond_momentum_episode("neutral","rise_20bp")
assert new_bond_momentum_episode("neutral","fall_20bp")
assert not new_bond_momentum_episode("rise_20bp","rise_20bp")
assert not new_bond_momentum_episode("rise_20bp","neutral")


def hartnett_regime_signal(mmf_weekly_bn, bond):
    if bond is None:
        return "금리 공식 수치 확인 대기 — 현금성 자금만으로 위험선호 방향 단정 금지"
    if mmf_weekly_bn is None:
        return "ICI 주간 MMF 갱신 대기 — 채권금리만으로 MMF 이동을 추정하지 않음"
    if mmf_weekly_bn > 0 and bond["bond_level"] != "below_5_30":
        return "ICI MMF 총자산 증가·미 10년물 감시기준 5.30% 이상: 현금 대기와 금리 부담 동반. 주식 강제매도로 단정하지 않음"
    if mmf_weekly_bn < 0 and bond["yield_10y_5d_bp"] < -15:
        return "MMF 감소·10년물 금리 하락: 현금 대기 완화 가능성. 실제 주식형 순유입 확인 전 재진입 단정 금지"
    return "현금·채권금리 신호 혼재 — 명확한 시장 재진입 판단 보류"


assert election_window_label(datetime(2026, 11, 3).date()) == "election_day"
assert election_window_label(datetime(2026, 10, 27).date()) == "within_7_days"
assert "강제매도" in hartnett_regime_signal(72.27, {
    "bond_level":"5_30_to_5_50", "yield_10y_5d_bp":20.0
})
assert "재진입 단정 금지" in hartnett_regime_signal(-1.0, {
    "bond_level":"below_5_30","yield_10y_5d_bp":-20.0
})


def _ici_table_rows(page_html, required_labels):
    """Read the latest official ICI table column, never free-form prose amounts.

    ICI text repeats last week, last month, and prose in each report. Searching
    arbitrary phrases can silently attach the wrong row or week to a metric.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True))
                     for cell in tr.find_all(["th", "td"], recursive=False)]
            if cells:
                rows.append(cells)
        header_date = None
        for cells in rows:
            for cell in cells:
                m = re.fullmatch(r"(\d{1,2}/\d{1,2}/20\d{2})", cell.strip())
                if m:
                    header_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                    break
            if header_date:
                break
        if not header_date:
            continue
        mapped = {}
        for cells in rows:
            if len(cells) < 2:
                continue
            label = cells[0].strip().lower().replace("*", "")
            if label in required_labels:
                n = parse_num(cells[1])
                if n is not None:
                    mapped[label] = {"value": n, "cells": cells}
        if set(required_labels).issubset(mapped):
            return header_date, mapped
    raise RuntimeError("ICI latest-week official numeric table incomplete; alert withheld")


def _ici_period_from_prose(text):
    m = re.search(
        r"week ended(?: Wednesday,?)?\s+([A-Za-z]+\s+\d{1,2})(?:,\s+(20\d{2}))?",
        text, re.I
    )
    if not m:
        raise RuntimeError("ICI report reference-week prose date missing")
    pub = _ici_published_date(text)
    year = int(m.group(2)) if m.group(2) else (
        datetime.strptime(pub, "%B %d, %Y").year if pub else None
    )
    if year is None:
        raise RuntimeError("ICI cannot determine reference-week year")
    return datetime.strptime(f"{m.group(1)}, {year}", "%B %d, %Y").date()

def _ici_published_date(text):
    m = re.search(
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2})\s*\|\s*Print",
        text, re.I
    )
    return m.group(1) if m else first_date(text)


def parse_ici_combined():
    page_html = browser_html(ICI_COMBINED)
    text = clean_text(page_html)
    labels = ("equity", "domestic", "world", "hybrid", "bond", "commodity", "total")
    ref_date, table = _ici_table_rows(page_html, labels)
    prose_date = _ici_period_from_prose(text)
    if ref_date != prose_date:
        raise RuntimeError(f"ICI combined header/prose date mismatch {ref_date} vs {prose_date}")

    values = {k: round(table[k]["value"] / 1000.0, 3) for k in labels}
    if abs(values["equity"] - values["domestic"] - values["world"]) > 0.015:
        raise RuntimeError("ICI combined domestic+world does not equal equity")
    if abs(values["total"] - sum(values[k] for k in ("equity","hybrid","bond","commodity"))) > 0.025:
        raise RuntimeError("ICI combined category total identity failed")

    m = re.search(r"Total estimated (inflows|outflows).*?(?:were|was) \$([\d,.]+) billion", text, re.I)
    if not m:
        raise RuntimeError("ICI combined official text direction/total missing")
    prose_total = float(m.group(2).replace(",", "")) * (-1 if "outflow" in m.group(1).lower() else 1)
    if abs(values["total"] - prose_total) > 0.025:
        raise RuntimeError(f"ICI combined table/prose amount mismatch {values['total']} vs {prose_total}")

    payload = {
        "source": "ICI", "kind": "combined",
        "period": ref_date.strftime("%B %d, %Y"),
        "published": _ici_published_date(text),
        "url": ICI_COMBINED, "metrics": values, "domestic_4w": None,
        "quality_checks": ["date_header_matches_prose", "equity_identity", "categories_total", "prose_total"],
    }
    payload["fingerprint"] = semantic_fingerprint(payload)
    return payload


def parse_ici_mmf():
    page_html = browser_html(ICI_MMF)
    text = clean_text(page_html)
    ref_date, table = _ici_table_rows(page_html, ("total",))
    prose_date = _ici_period_from_prose(text)
    if ref_date != prose_date:
        raise RuntimeError(f"ICI MMF header/prose date mismatch {ref_date} vs {prose_date}")

    m = re.search(
        r"Total money market fund assets.*?(increased|decreased) by \$([\d,.]+) billion to \$([\d,.]+) trillion",
        text, re.I
    )
    if not m:
        raise RuntimeError("ICI MMF official text total/direction missing")
    reported_delta = float(m.group(2).replace(",", "")) * (1 if m.group(1).lower() == "increased" else -1)
    reported_assets_tr = float(m.group(3).replace(",", ""))
    row = table["total"]["cells"]
    if len(row) < 4:
        raise RuntimeError("ICI MMF official Total row missing 2 weeks and change columns")
    total_bn = parse_num(row[1])
    previous_bn = parse_num(row[2])
    tab_delta_bn = parse_num(row[3])
    if None in (total_bn, previous_bn, tab_delta_bn):
        raise RuntimeError("ICI MMF numeric totals incomplete")
    if abs(total_bn - previous_bn - reported_delta) > 0.06:
        raise RuntimeError("ICI MMF weekly arithmetic mismatch")
    if abs(tab_delta_bn - reported_delta) > 0.06:
        raise RuntimeError("ICI MMF reported change differs from official table")
    if abs(total_bn / 1000.0 - reported_assets_tr) > 0.006:
        raise RuntimeError("ICI MMF headline/trillion level mismatch")

    payload = {
        "source": "ICI", "kind": "mmf",
        "period": ref_date.strftime("%B %d, %Y"),
        "published": _ici_published_date(text),
        "url": ICI_MMF,
        "metrics": {
            "assets_trillion": round(total_bn / 1000.0, 5),
            "weekly_change_bn": round(reported_delta, 2),
        },
        "quality_checks": ["same_week", "weekly_arithmetic", "table_change", "prose_level"],
    }
    payload["fingerprint"] = semantic_fingerprint(payload)
    return payload

def parse_finra():
    r = get(FINRA_MARGIN)
    tables = pd.read_html(StringIO(r.text))
    target = None
    for raw in tables:
        t = normalize_columns(raw)
        flat = " ".join(t.columns) + " " + " ".join(map(str, t.astype(str).values.flatten()[:40]))
        if re.search(r"Debit Balances", flat, re.I) and re.search(r"Free Credit", flat, re.I):
            target = t
            break
    if target is None:
        raise RuntimeError("FINRA margin table not found")

    # Locate date/month column and three numeric columns by header labels.
    month_col = target.columns[0]
    debit_col = next((c for c in target.columns if re.search(r"Debit Balances", c, re.I)), target.columns[1])
    free_cols = [c for c in target.columns if re.search(r"Free Credit", c, re.I)]
    if len(free_cols) < 2:
        # Some FINRA pages have headers collapsed; fall back by column position only if there are 4+ cols.
        if len(target.columns) < 4:
            raise RuntimeError(f"FINRA margin columns unexpected: {list(target.columns)}")
        free_cols = [target.columns[2], target.columns[3]]

    rows = []
    for _, row in target.iterrows():
        period = str(row[month_col]).strip()
        if not re.search(r"\d{2}|20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", period, re.I):
            continue
        debit = parse_num(row[debit_col])
        cash = parse_num(row[free_cols[0]])
        margin_cash = parse_num(row[free_cols[1]])
        if debit is not None:
            rows.append((period, debit, cash, margin_cash))
    if len(rows) < 2:
        raise RuntimeError("FINRA margin data rows not found")

    def month_key(period):
        p = period.strip()
        for fmt in ("%b-%y", "%b %Y", "%B %Y", "%m/%Y", "%Y-%m"):
            try:
                return datetime.strptime(p, fmt)
            except Exception:
                pass
        # Fallback to order on page; mark as minimal.
        return datetime.min

    if any(month_key(r[0]) != datetime.min for r in rows):
        rows.sort(key=lambda r: month_key(r[0]), reverse=True)
    latest, prev = rows[0], rows[1]

    # FINRA values are $ millions.
    metrics = {
        "margin_debt_bn": latest[1] / 1000.0,
        "cash_free_bn": latest[2] / 1000.0 if latest[2] is not None else None,
        "margin_free_bn": latest[3] / 1000.0 if latest[3] is not None else None,
        "margin_debt_mom_bn": (latest[1] - prev[1]) / 1000.0,
    }
    payload = {
        "source": "FINRA",
        "kind": "margin",
        "period": latest[0],
        "published": None,
        "url": FINRA_MARGIN,
        "metrics": metrics,
    }
    payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def rss_items(url):
    try:
        root = ET.fromstring(get(url).content)
    except Exception:
        return []
    out = []
    for item in root.findall(".//item")[:40]:
        out.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "pub": (item.findtext("pubDate") or "").strip(),
            "desc": clean_text(item.findtext("description") or ""),
        })
    return out


def news_items(query):
    bing = "https://www.bing.com/news/search?q=" + quote(query) + "&format=rss"
    google = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=en-US&gl=US&ceid=US:en"
    seen = set()
    out = []
    for it in rss_items(bing) + rss_items(google):
        k = it["title"] + "|" + it["link"]
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def extract_article_body(url):
    try:
        try:
            r = get(url, timeout=25)
            raw_html = r.text
            final_url = r.url
        except Exception:
            raw_html = browser_html(url)
            final_url = url
        soup = BeautifulSoup(raw_html, "html.parser")
        bodies = []
        for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                j = json.loads(s.string or "")
                stack = j if isinstance(j, list) else [j]
                for o in stack:
                    if isinstance(o, dict) and o.get("articleBody"):
                        bodies.append(str(o["articleBody"]))
                    if isinstance(o, dict) and isinstance(o.get("@graph"), list):
                        for q in o["@graph"]:
                            if isinstance(q, dict) and q.get("articleBody"):
                                bodies.append(str(q["articleBody"]))
            except Exception:
                pass
        body = max(bodies, key=len) if bodies else clean_text(raw_html)
        return final_url, body
    except Exception:
        return url, ""


def signed_flow_sentence(text, concept_regex):
    # Do not split "U.S. equity funds" after the abbreviation; that previously
    # discarded otherwise valid U.S. equity flow observations.
    normalized = re.sub(r"\bU\.S\.(?=\s)", "US", text, flags=re.I)
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for sent in sentences:
        if not re.search(concept_regex, sent, re.I):
            continue
        amounts = re.findall(r"\$([\d,.]+)\s*(billion|million)\b", sent, re.I)
        # Fail closed on multi-amount sentences; the amount might refer to another asset class.
        if len(amounts) != 1:
            continue
        low = sent.lower()
        has_outflow = bool(re.search(r"outflows?|withdraw(?:n|als?)?|withdrew|pulled|redemptions?|net sales|lost|sold", low))
        has_inflow = bool(re.search(r"inflows?|received|attracted|bought|poured|added|net purchases?|net investments?", low))
        # A sentence mentioning both inflows and outflows is directionally ambiguous.
        if has_inflow == has_outflow:
            continue
        sign = 1 if has_inflow else -1
        amount, unit = amounts[0]
        amount_bn = float(amount.replace(",", "")) / (1000.0 if unit.lower() == "million" else 1.0)
        return sign * amount_bn, sent[:700]
    return None, None


# Regression guard: a sentence with opposing directions or multiple amounts cannot be signed.
assert signed_flow_sentence("US equity had $5.11 billion in net outflows", r"US equity")[0] == -5.11
assert signed_flow_sentence("U.S. equity funds had $5.11 billion in net outflows", r"US.*equity") [0] == -5.11
assert signed_flow_sentence("Global equity funds attracted $560 million", r"global.*equity")[0] == 0.56
assert signed_flow_sentence("US equity had $5 billion in inflows and $4 billion in outflows", r"US equity")[0] is None
assert signed_flow_sentence("US equity saw both inflows and $5 billion in outflows", r"US equity")[0] is None


def report_reference_week(text, pub_day):
    """Only an explicitly stated 'week ended/ending' can identify media fund-flow dates."""
    hits=[]
    pattern=(
        r"\bweek\s+(?:ended|ending|through|to)\s+(?:on\s+)?"
        r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday),?\s+)?"
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\s+(\d{1,2})(?:,?\s+(20\d{2}))?"
    )
    for m in re.finditer(pattern, text, re.I):
        mon=m.group(1).title()
        mon="Sep" if mon.lower()=="sept" else mon
        year=int(m.group(3)) if m.group(3) else pub_day.year
        try:
            d=datetime.strptime(f"{mon} {int(m.group(2))} {year}", "%B %d %Y").date()
        except ValueError:
            try: d=datetime.strptime(f"{mon} {int(m.group(2))} {year}", "%b %d %Y").date()
            except ValueError: continue
        if 0 <= (pub_day-d).days <= 14:
            hits.append(d)
    # Multiple competing recent weeks in one story are ambiguous; fail closed.
    return hits[0] if hits and len(set(hits))==1 else None

assert report_reference_week("In the week ended October 7, money funds...", datetime(2026,10,9).date()) == datetime(2026,10,7).date()
assert report_reference_week("Funds rose on October 7.", datetime(2026,10,9).date()) is None
assert report_reference_week("in the week ended October 7 and week ended September 30", datetime(2026,10,9).date()) is None


# A geographic prefix must occur NEXT TO the reported fund class.
# The old 'US.*equity' pattern matched navigation widgets far away from a
# 'global equity funds' sentence, falsely labeling global +$560m as US +$560m.
US_EQUITY_FUND_RE = (
    r"\b(?:US|United States)\s+(?:equity|stock)\s+funds?\b"
    r"|\b(?:equity|stock)\s+funds?\s+(?:of|from|in)\s+(?:the\s+)?(?:US|United States)\b"
)
GLOBAL_EQUITY_FUND_RE = r"\b(?:global|worldwide)\s+(?:equity|stock)\s+funds?\b"
LSEG_US_REUTERS_CONFIRM = (
    "https://www.investing.com/news/stock-market-news/"
    "us-equity-funds-witness-first-weekly-outflow-in-three-weeks-4940766"
)

assert signed_flow_sentence(
    "CNA Games Find US puzzles Investors made net purchases of $560 million in global equity funds.",
    US_EQUITY_FUND_RE
)[0] is None
assert signed_flow_sentence(
    "Investors withdrew a net $5.11 billion from U.S. equity funds during the week.",
    US_EQUITY_FUND_RE
)[0] == -5.11
assert signed_flow_sentence(
    "Investors made net purchases of $560 million in global equity funds.",
    GLOBAL_EQUITY_FUND_RE
)[0] == 0.56


def elliptical_us_equity_outflow_in_global_dispatch(body):
    """Read US regional net sales whose context is global EQUITY funds.

    Reuters can write: 'Asian equity funds gained $6.16bn, but withdrew
    $5.11bn from U.S. funds.' The two amounts share a sentence; never
    assign the Asian amount to the US or mistake US bond/MMF funds.
    """
    normalized = re.sub(r"\bU\.S\.(?=\s)", "US", body, flags=re.I)
    if not re.search(GLOBAL_EQUITY_FUND_RE, normalized, re.I):
        return None, None
    pattern = (
        r"\b(?:withdrew|withdrawn|pulled)\s+\$([\d,.]+)\s*"
        r"(billion|million)\s+from\s+(?:the\s+)?US\s+funds?\b"
    )
    candidates = []
    for m in re.finditer(pattern, normalized, re.I):
        preceding = normalized[max(0, m.start() - 350): m.start()]
        # The explicitly named neighboring regional EQUITY funds make the
        # elided 'US funds' phrase unambiguously equity, not MMF or bonds.
        if not re.search(r"\b(?:Asian|European|global)\s+equity\s+funds?\b", preceding, re.I):
            continue
        amount = float(m.group(1).replace(",", ""))
        if m.group(2).lower() == "million":
            amount /= 1000.0
        candidates.append((-amount, normalized[max(0,m.start()-120):m.end()+40]))
    if not candidates or len({round(v, 4) for v, _ in candidates}) != 1:
        return None, None
    return candidates[0]


assert elliptical_us_equity_outflow_in_global_dispatch(
    "Investors bought $560 million in global equity funds. "
    "European equity funds attracted $6.19 billion. "
    "Investors added a net $6.16 billion to Asian equity funds, "
    "but withdrew $5.11 billion from U.S. funds."
)[0] == -5.11
assert elliptical_us_equity_outflow_in_global_dispatch(
    "US money market funds bought $5.11 billion of government bonds."
)[0] is None
assert elliptical_us_equity_outflow_in_global_dispatch(
    "Global equity funds gained $560 million while US money market funds saw net sales of $5.11 billion."
)[0] is None


def parse_reuters(kind):
    query = BING_Bofa if kind == "bofa" else BING_LIPPER
    seeds = {
        "bofa": [{
            "title": "Investors buy US stocks at fastest pace in three months, BofA says - Reuters",
            "link": "https://www.reuters.com/world/china/investors-buy-us-stocks-fastest-pace-three-months-bofa-says-2026-09-18/",
            "pub": "Fri, 18 Sep 2026 00:00:00 GMT",
            "desc": "BofA EPFR fund flows Reuters",
        }],
        "lipper": [{
            # Official Reuters reporting republished by Channel NewsAsia; use only while fresh.
            "title": "Money market funds attract massive inflows as bond selloff bit - Reuters",
            "link": "https://www.channelnewsasia.com/business/money-market-funds-attract-massive-inflows-bond-selloff-bit-6445901",
            "pub": "Fri, 09 Oct 2026 10:00:00 GMT",
            "desc": "LSEG Lipper Reuters syndicated report",
        }],
    }
    items = seeds.get(kind, []) + news_items(query)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    for it in items:
        # A publisher's old article is not a fresh fund-flow observation.
        # RSS publication time is used ONLY as an article freshness guard, never
        # as the underlying fund-flow reference week.
        try:
            pub_day = parsedate_to_datetime(str(it.get("pub") or "")).date()
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
        if not 0 <= (today - pub_day).days <= 14:
            continue
        blob = (it["title"] + " " + it["desc"])
        if "Reuters" not in blob and "reuters" not in blob.lower():
            continue
        if kind == "bofa" and not re.search(r"BofA|Bank of America|EPFR", blob, re.I):
            continue
        if kind == "lipper" and not re.search(r"LSEG|Lipper|global equity fund", blob, re.I):
            continue

        final, body = extract_article_body(it["link"])
        combined = blob + " " + body
        if kind == "bofa" and not re.search(r"BofA|Bank of America|EPFR", combined, re.I):
            continue
        if kind == "lipper" and not re.search(r"LSEG|Lipper", combined, re.I):
            continue

        us, us_sent = signed_flow_sentence(body, US_EQUITY_FUND_RE)
        glob, glob_sent = signed_flow_sentence(body, GLOBAL_EQUITY_FUND_RE)
        mmf, mmf_sent = signed_flow_sentence(body, r"\bmoney[- ]market\s+funds?\b")

        # Media publication date alone is never a weekly fund-flow observation.
        observed = report_reference_week(body, pub_day)
        if observed is None:
            continue
        us_equity_url = None
        if kind == "lipper":
            if us is None:
                regional_us, regional_sentence = elliptical_us_equity_outflow_in_global_dispatch(body)
                if regional_us is not None:
                    us, us_sent = regional_us, regional_sentence
                    us_equity_url = final or it["link"]
            # Global and US fund figures are not interchangeable. Verify the
            # dedicated Reuters US-equity dispatch only if it states the SAME week.
            try:
                dedicated_url, dedicated_body = extract_article_body(LSEG_US_REUTERS_CONFIRM)
                dedicated_week = report_reference_week(dedicated_body, pub_day)
                dedicated_us, dedicated_sentence = signed_flow_sentence(
                    dedicated_body, US_EQUITY_FUND_RE
                )
                if dedicated_week == observed and dedicated_us is not None:
                    # A global-dispatch parser disagreement is unsafe: withhold
                    # US value unless the dedicated dispatch resolves it.
                    if us is None or abs(us - dedicated_us) < 0.011:
                        us, us_sent = dedicated_us, dedicated_sentence
                        us_equity_url = dedicated_url
                    else:
                        us, us_sent = None, None
            except Exception:
                pass
        if us_sent is not None and glob_sent is not None and us_sent == glob_sent:
            # Defensive independent evidence requirement for differing markets.
            us, us_sent = None, None
        if us is None and glob is None and mmf is None:
            continue
        # Underlying scope differs across providers. Do not infer direct asset transfers.
        payload = {
            "source": "BofA/EPFR via Reuters" if kind == "bofa" else "LSEG Lipper via Reuters",
            "kind": kind,
            "period": observed.strftime("%B %d, %Y"),
            "published": it["pub"],
            "url": final or it["link"],
            "title": it["title"],
            "reference_week_verified": True,
            "reference_week": observed.isoformat(),
            "comparison_note": "기사에 명시된 기준주간 확인; 통계 모집단별 순유입·순유출은 직접 자금 이전이 아님",
            "metrics": {"us_equity_bn": us, "global_equity_bn": glob, "mmf_bn": mmf},
            "evidence": {"us": us_sent, "global": glob_sent, "mmf": mmf_sent},
            "us_equity_url": us_equity_url,
        }
        payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return payload
    # Include a compact diagnostic in status logs only when no matching Reuters item can be parsed.
    sample = [it.get("title","") for it in news_items(query)[:5]]
    if sample:
        raise RuntimeError("Reuters discovery sample: " + " || ".join(sample))
    return None


def period_date(x):
    if not x:
        return None
    p = str(x.get("period") or "").strip()
    pub = str(x.get("published") or "").strip()
    year = None
    ym = re.search(r"(20\d{2})", p) or re.search(r"(20\d{2})", pub)
    if ym:
        year = int(ym.group(1))
    else:
        year = datetime.now(timezone(timedelta(hours=9))).year

    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(p, fmt).date()
        except Exception:
            pass
    for fmt in ("%B %d", "%b %d"):
        try:
            d = datetime.strptime(p, fmt)
            return d.replace(year=year).date()
        except Exception:
            pass
    # Low-frequency sources have month, quarter, or range labels rather than daily dates.
    for fmt in ("%b-%y", "%b %Y", "%B %Y", "%m/%Y", "%Y-%m"):
        try:
            return datetime.strptime(p, fmt).date().replace(day=1)
        except ValueError:
            pass
    q = re.fullmatch(r"(20\d{2}):Q([1-4])", p)
    if q:
        return datetime(int(q.group(1)), int(q.group(2)) * 3, 1).date()
    interval = re.fullmatch(r"([A-Za-z]+)[-–—]([A-Za-z]+)\s+(20\d{2})", p)
    if interval:
        try:
            return datetime.strptime(f"{interval.group(2)} {interval.group(3)}", "%B %Y").date()
        except ValueError:
            pass
    return None


def same_reference_week(a, b):
    da, db = period_date(a), period_date(b)
    return bool(da and db and da == db)


def eligible_reference_week(x):
    """Article publication date is NOT a fund-flow observation week.

    ICI official releases identify the actual reference week; Reuters/Bloomberg
    articles qualify only if an independently parsed, verified week exists.
    """
    if not isinstance(x, dict):
        return None
    if x.get("source") == "ICI" and x.get("kind") in ("combined", "mmf"):
        return period_date(x)
    if x.get("reference_week_verified") is True:
        try:
            return datetime.strptime(str(x["reference_week"]), "%Y-%m-%d").date()
        except (KeyError, ValueError):
            return None
    return None


def recent_official_week(x, on_date, max_age_days=14):
    observed = eligible_reference_week(x)
    return bool(observed and 0 <= (on_date-observed).days <= max_age_days)


def source_is_stale(x, previous, on_date):
    """Old pages must never roll back a delivered observation or replace newer state."""
    current_period = eligible_reference_week(x) or period_date(x)
    old_period = eligible_reference_week(previous) or period_date(previous)
    if current_period is not None and current_period > on_date:
        return True
    if current_period is not None and old_period is not None and current_period < old_period:
        return True
    if x.get("source") == "ICI" and x.get("kind") in ("combined", "mmf"):
        return not recent_official_week(x, on_date, max_age_days=21)
    return False


assert source_is_stale(
    {"source":"ICI","kind":"mmf","period":"September 30, 2026"},
    {"source":"ICI","kind":"mmf","period":"October 07, 2026"},
    datetime(2026,10,10).date()
)
assert not source_is_stale(
    {"source":"ICI","kind":"mmf","period":"October 07, 2026"},
    {"source":"ICI","kind":"mmf","period":"October 07, 2026"},
    datetime(2026,10,10).date()
)
assert source_is_stale(
    {"source":"FINRA","kind":"margin","period":"Jul-26"},
    {"source":"FINRA","kind":"margin","period":"Aug-26"},
    datetime(2026,10,10).date()
)
assert source_is_stale(
    {"source":"Federal Reserve Z.1","kind":"household_balance_sheet","period":"2026:Q1"},
    {"source":"Federal Reserve Z.1","kind":"household_balance_sheet","period":"2026:Q2"},
    datetime(2026,10,10).date()
)


# Regression guards: media report date is not equivalent to fund observation date.
assert eligible_reference_week({"source":"BofA/EPFR via Reuters","kind":"bofa","period":"Fri, 09 Oct 2026"}) is None
assert eligible_reference_week({"source":"ICI","kind":"mmf","period":"October 07, 2026"}) == datetime(2026,10,7).date()
assert not recent_official_week({"source":"ICI","kind":"mmf","period":"October 07, 2026"}, datetime(2026,11,8).date())
assert same_reference_week({"period":"October 07, 2026"}, {"period":"October 07, 2026"})


def flow_direction(us, mmf):
    """ICI equity net flows and ICI MMF asset-balance changes are NOT matching flows."""
    if us is None or mmf is None:
        return "주식형 순유입·순유출과 MMF 총자산 증감을 동시에 검증하지 못해 방향 판정 보류"
    equity = "순유입" if us > 0 else "순유출" if us < 0 else "보합"
    assets = "증가" if mmf > 0 else "감소" if mmf < 0 else "보합"
    return (
        f"ICI 동일 기준주간: 미국 국내주식형 {equity} / MMF 총자산 {assets}. "
        "주식형 순유입·순유출과 MMF 총자산 증감은 다른 지표이므로 "
        "동일 자금의 직접 이동 확인 불가"
    )


assert "직접 이동 확인 불가" in flow_direction(10.0, -5.0)
assert "직접 이동 확인 불가" in flow_direction(-10.0, 5.0)


def source_block(x, fx):
    m = x["metrics"]
    lines = []
    if x["kind"] == "combined":
        lines.append(f"• 미국 국내주식형(뮤추얼펀드+ETF) {fmt_usd_bn_kr(m.get('domestic'), fx)}")
        lines.append(f"• 세계주식형 {fmt_usd_bn_kr(m.get('world'), fx)} / 채권형 {fmt_usd_bn_kr(m.get('bond'), fx)}")
        if x.get("domestic_4w") is not None:
            lines.append(f"• 미국 국내주식형 최근 4주 합계 {fmt_usd_bn_kr(x['domestic_4w'], fx)}")
    elif x["kind"] == "mmf":
        ch = m["weekly_change_bn"]
        lines.append(
            f"• MMF(단기 현금 주차성 펀드) 총자산 {fmt_usd_trillion_kr(m['assets_trillion'], fx)} "
            f"/ 주간 {fmt_usd_bn_kr(ch, fx)}"
        )
    elif x["kind"] == "margin":
        lines.append(
            f"• 마진부채(주식담보 신용거래 차입) {fmt_usd_bn_kr(m['margin_debt_bn'], fx)} "
            f"/ 전월 {fmt_usd_bn_kr(m['margin_debt_mom_bn'], fx)}"
        )
        if m.get("cash_free_bn") is not None and m.get("margin_free_bn") is not None:
            lines.append(
                f"• 현금계좌 가용현금 {fmt_usd_bn_kr(m['cash_free_bn'], fx)} "
                f"/ 마진계좌 가용현금 {fmt_usd_bn_kr(m['margin_free_bn'], fx)}"
            )
    elif x["kind"] == "household_withdrawals":
        lines.append(
            f"• 투자계좌→예금계좌 순인출 개인 비중 {m['withdrawers_all_pct']:.1f}% "
            f"/ 상위 10% {m['withdrawers_top10_pct']:.1f}% "
            f"/ 중위소득 미만 {m['withdrawers_below_median_pct']:.1f}%"
        )
        lines.append(
            f"• 투자자산 인출로 충당되는 소비 비중 {m['spending_funded_pct']:.1f}%"
        )
    elif x["kind"] == "household_balance_sheet":
        lines.append(
            f"• 가계·비영리 직접+간접 기업주식 {fmt_usd_trillion_kr(m['equities_trillion'], fx)} "
            f"/ 총자산 대비 {m['equities_share_total_assets_pct']:.2f}%"
        )
        lines.append(
            f"• 총 금융자산 {fmt_usd_trillion_kr(m['financial_assets_trillion'], fx)} "
            f"/ 순자산 {fmt_usd_trillion_kr(m['net_worth_trillion'], fx)}"
        )
    else:
        lines.append(f"• 미국 주식형 {fmt_usd_bn_kr(m.get('us_equity_bn'), fx)}")
        if m.get("us_equity_bn") is not None and x.get("us_equity_url"):
            lines.append(f'• 미국 주식형 별도 원문: <a href="{html.escape(x["us_equity_url"], quote=True)}">Reuters 기사 열기</a>')
        if m.get("global_equity_bn") is not None:
            lines.append(f"• 글로벌 주식형 {fmt_usd_bn_kr(m.get('global_equity_bn'), fx)}")
        if m.get("mmf_bn") is not None:
            mmf_label="글로벌 MMF" if x["kind"]=="lipper" else "MMF(해당 보고서 집계)"
            direction="순유입" if m["mmf_bn"]>0 else "순유출" if m["mmf_bn"]<0 else "보합"
            lines.append(f"• {mmf_label} {direction} {fmt_usd_bn_kr(m.get('mmf_bn'), fx)}")
        if x.get("reference_week_verified") is True:
            lines.append(
                f"• 기준주간 {x.get('reference_week')}: 기사 본문에서 주간을 확인했으나 "
                "주식형·MMF의 모집단이 달라 직접 자금 이동으로 결론 내리지 않음"
            )
        else:
            lines.append("• 기사 게시일만으로 집계주간을 추정하지 않음 — 방향 판정 보류")
    return "\n".join(lines)


state = load_state()
fx = fetch_fx()
results = []
errors = []

for name, fn in [
    ("ICI 장기펀드+ETF", parse_ici_combined),
    ("ICI MMF", parse_ici_mmf),
    ("FINRA 마진", parse_finra),
    ("JPMorganChase 가계 투자자산 인출", parse_jpm_household),
    ("Federal Reserve Z.1 가계 대차대조표", parse_fed_household_balance_sheet),
    ("BofA/EPFR Reuters", lambda: parse_reuters("bofa")),
    ("LSEG Lipper Reuters", lambda: parse_reuters("lipper")),
]:
    try:
        x = fn()
        if x:
            results.append(x)
        else:
            errors.append(f"{name}: 최신 데이터 항목 미발견")
    except Exception as e:
        errors.append(f"{name}: {type(e).__name__}: {e}")

# Exclude genuinely stale source pages before comparing fingerprints AND before
# writing any state. Otherwise an unrelated new update could roll back ICI data.
fresh_results = []
reference_today = datetime.now(ZoneInfo("America/New_York")).date()
for x in results:
    key = f"{x['source']}|{x['kind']}"
    previous = (state.get("values") or {}).get(key)
    if source_is_stale(x, previous, reference_today):
        errors.append(f"{key}: 과거 기준기간 또는 오래된 원자료 감지 — 상태와 알림에서 제외")
        continue
    fresh_results.append(x)
results = fresh_results

updates = []
for x in results:
    key = f"{x['source']}|{x['kind']}"
    current_fp = semantic_fingerprint(x)
    x["fingerprint"] = current_fp

    # Backward-compatible migration: old state may have fingerprints that included URL/title metadata.
    old_value = state.get("values", {}).get(key)
    old_semantic = semantic_fingerprint(old_value) if isinstance(old_value, dict) else None
    old_seen = state.get("seen", {}).get(key)

    # A source URL/domain change, article title edit, published timestamp change, or parser metadata
    # must NOT create a Telegram alert when period + metrics are identical.
    if old_semantic == current_fp or old_seen == current_fp:
        continue
    updates.append(x)

ici = next((x for x in results if x["kind"] == "combined"), None)
ici_mmf = next((x for x in results if x["kind"] == "mmf"), None)
finra = next((x for x in results if x["kind"] == "margin"), None)
bofa = next((x for x in results if x["kind"] == "bofa"), None)
lipper = next((x for x in results if x["kind"] == "lipper"), None)
jpm_household = next((x for x in results if x["kind"] == "household_withdrawals"), None)
fed_household = next((x for x in results if x["kind"] == "household_balance_sheet"), None)

hartnett_macro = None
try:
    hartnett_macro = fetch_hartnett_macro_context()
except Exception as e:
    errors.append(f"Hartnett 금리 검증: {type(e).__name__}: {e}")

old_hartnett = (state.get("derived") or {})
new_york_date = datetime.now(ZoneInfo("America/New_York")).date()
mmf_recent = recent_official_week(ici_mmf, new_york_date)
hartnett_init = bool(
    hartnett_macro and ici_mmf and mmf_recent
    and old_hartnett.get("hartnett_tracking_version") != HARTNETT_TRACK_VERSION
)
old_bond_band = old_hartnett.get("hartnett_bond_level")
if old_bond_band == "elevated" and hartnett_macro:
    # Migration from one generic elevated zone to finer 5.30 / 5.50 / 6.00 zones.
    old_bond_band = bond_yield_band(float(old_hartnett.get("hartnett_10y_pct",5.30)))
bond_level_transition = bool(
    hartnett_macro
    and old_bond_band
    and old_bond_band != hartnett_macro["bond_level"]
)
bond_momentum_transition = bool(
    hartnett_macro and new_bond_momentum_episode(
        old_hartnett.get("hartnett_bond_momentum"),
        hartnett_macro["bond_momentum"],
    )
)
target_rate_change = bool(
    hartnett_macro
    and isinstance(old_hartnett.get("hartnett_fed_target_upper_pct"), (int,float))
    and abs(old_hartnett["hartnett_fed_target_upper_pct"] - hartnett_macro["fed_target_upper_pct"]) >= 0.245
)
election_window = election_window_label(datetime.now(ZoneInfo("America/New_York")).date())
election_transition = bool(
    old_hartnett.get("hartnett_election_stage")
    and old_hartnett.get("hartnett_election_stage") != election_window
    and election_window in ("within_7_days","election_day","post_election_window")
)

sp500 = None
try:
    sp500 = fetch_sp500_context()
except Exception as e:
    errors.append(f"S&P 500 FRED: {type(e).__name__}: {e}")

old_jpm = (state.get("values") or {}).get("JPMorganChase Institute|household_withdrawals")
jpm_updated = any(x.get("kind") == "household_withdrawals" for x in updates)

def metric_delta(current, previous, key):
    try:
        return float(current["metrics"][key]) - float(previous["metrics"][key])
    except Exception:
        return None

jpm_withdrawal_delta = metric_delta(jpm_household, old_jpm, "withdrawers_all_pct") if jpm_household else None
jpm_spending_delta = metric_delta(jpm_household, old_jpm, "spending_funded_pct") if jpm_household else None

old_band = (state.get("derived") or {}).get("sp500_drawdown_band")
current_band = sp500.get("band") if sp500 else None
drawdown_transition = bool(old_band and current_band and old_band != current_band)

# Do not flag cross-vendor flow disagreement when the observation weeks differ,
# or when the only "date" is a journalist's publication timestamp.
cross = []
pairs = [
    ("BofA/EPFR", bofa["metrics"].get("us_equity_bn") if bofa else None, eligible_reference_week(bofa)),
    ("LSEG Lipper", lipper["metrics"].get("us_equity_bn") if lipper else None, eligible_reference_week(lipper)),
    ("ICI", ici["metrics"].get("domestic") if ici else None, eligible_reference_week(ici)),
]
known = [(name, value, observed) for name,value,observed in pairs if value is not None and observed]
for i in range(len(known)):
    for j in range(i + 1, len(known)):
        n1, v1, d1 = known[i]
        n2, v2, d2 = known[j]
        if d1 == d2 and v1*v2 < 0:
            cross.append(
                f"{n1}와 {n2}의 동일 주간({d1}) 미국 주식 흐름 방향 반대 "
                "→ 모집단이 달라 합산하지 않고 각 출처 원문을 별도로 확인"
            )

interpret = []
if bofa:
    interpret.append(
        f"BofA/EPFR: 집계주간 {bofa.get('reference_week') or '확인 불가'}, "
        "기사에 명시된 주간만 인정. 주식형·MMF 자금을 직접 이동으로 단정하지 않음"
    )
if lipper:
    interpret.append(
        f"LSEG Lipper: 집계주간 {lipper.get('reference_week') or '확인 불가'}, "
        "글로벌 MMF와 미국 주식형은 모집단이 달라 직접 이동으로 단정하지 않음"
    )
if ici:
    d = ici["metrics"].get("domestic")
    if d is not None:
        interpret.append(f"ICI 공식 미국 국내주식형: {'순유입' if d > 0 else '순유출'} {fmt_usd_bn_kr(d, fx)}")
if ici_mmf:
    ch = ici_mmf["metrics"].get("weekly_change_bn")
    if ch is not None:
        interpret.append(f"ICI 공식 MMF: {'증가' if ch > 0 else '감소'} {fmt_usd_bn_kr(ch, fx)}")
        if mmf_recent:
            interpret.append("Hartnett 감시 기준: " + hartnett_regime_signal(ch, hartnett_macro))
        else:
            interpret.append("ICI MMF 집계 기준일이 14일보다 오래되어 금리와의 현재 동시 신호 판정 보류")
if finra:
    md = finra["metrics"].get("margin_debt_mom_bn")
    if md is not None:
        interpret.append(
            f"FINRA 월간 마진부채: {'증가 → 레버리지 확대' if md > 0 else '감소 → 레버리지 축소'} "
            f"({fmt_usd_bn_kr(md, fx)} 전월비)"
        )
if jpm_household:
    jm = jpm_household["metrics"]
    interpret.append(
        f"JPMorganChase 가계 구조: 순인출자 {jm['withdrawers_all_pct']:.1f}% / "
        f"상위 10% {jm['withdrawers_top10_pct']:.1f}% / "
        f"투자자산으로 충당되는 소비 {jm['spending_funded_pct']:.1f}%"
    )
if fed_household:
    fm = fed_household["metrics"]
    interpret.append(
        f"연준 Z.1 가계 주식 노출: 직접+간접 기업주식 {fm['equities_trillion']:.2f}조달러 / "
        f"총자산 대비 {fm['equities_share_total_assets_pct']:.2f}%"
    )
if sp500:
    interpret.append(
        f"S&P 500: {sp500['last_value']:,.2f} ({sp500['last_date']}) / "
        f"5년 내 고점 {sp500['peak_value']:,.2f} ({sp500['peak_date']}) 대비 "
        f"{sp500['drawdown_pct']:.2f}%"
    )
    if sp500["drawdown_pct"] <= -15.0:
        if jpm_updated and jpm_withdrawal_delta is not None and jpm_withdrawal_delta > 0:
            interpret.append(
                f"🚨 가계 자산현금화 경보: S&P 500이 고점 대비 15% 이상 하락한 상태에서 "
                f"JPMorgan 순인출자 비중이 직전 공식값보다 {jpm_withdrawal_delta:+.1f}%p 상승 "
                "→ 2020·2022·2025 하락기의 인출 둔화 패턴과 다른 방향"
            )
        elif jpm_updated and jpm_withdrawal_delta is not None and jpm_withdrawal_delta <= 0:
            interpret.append(
                "S&P 500이 고점 대비 15% 이상 하락했지만 JPMorgan 순인출자 비중은 상승하지 않음 "
                "→ 과거 급락기와 유사한 방향"
            )
        elif ici_mmf and ici_mmf["metrics"].get("weekly_change_bn", 0) > 0:
            interpret.append(
                "S&P 500 15% 이상 하락 + ICI MMF 증가 → 위험회피 신호 강화. "
                "다만 JPMorgan의 새 가계 인출 자료가 나오기 전에는 강제매도 악순환으로 단정하지 않음"
            )
    elif ici_mmf and ici_mmf["metrics"].get("weekly_change_bn", 0) > 0:
        interpret.append(
            "MMF가 증가해도 S&P 500의 고점 대비 낙폭이 15% 미만이면 "
            "차익실현·현금대기와 위험회피를 구분해 해석"
        )

if jpm_updated and jpm_withdrawal_delta is not None and jpm_spending_delta is not None:
    if jpm_withdrawal_delta > 0 and jpm_spending_delta > 0:
        interpret.append(
            f"JPMorgan 구조 변화: 순인출자 {jpm_withdrawal_delta:+.1f}%p, "
            f"투자자산 충당 소비 {jpm_spending_delta:+.1f}%p → 소비의 금융자산 의존도 상승"
        )
    elif jpm_withdrawal_delta < 0 and jpm_spending_delta < 0:
        interpret.append(
            f"JPMorgan 구조 변화: 순인출자 {jpm_withdrawal_delta:+.1f}%p, "
            f"투자자산 충당 소비 {jpm_spending_delta:+.1f}%p → 금융자산 의존도 완화"
        )

# ICI equity and MMF must refer to the same week before treating them as a rotation pair.
if ici and ici_mmf:
    d = ici["metrics"].get("domestic")
    ch = ici_mmf["metrics"].get("weekly_change_bn")
    if d is not None and ch is not None:
        if same_reference_week(ici, ici_mmf):
            interpret.append("ICI 조합: " + flow_direction(d, ch))
        else:
            interpret.append(
                f"ICI 기간 차이: 미국 국내주식형 {ici.get('period')} / MMF {ici_mmf.get('period')} "
                "→ 서로 다른 주간이라 직접 자금 회전 판정 보류"
            )

def direction_word(v, up="증가", down="감소"):
    if v is None:
        return "확인 대기"
    if v > 0:
        return up
    if v < 0:
        return down
    return "변화 없음"


stock_signals = []
if ici and ici["metrics"].get("domestic") is not None:
    stock_signals.append(("ICI", ici["metrics"]["domestic"], ici["period"]))
# A press publication date alone cannot qualify as a current investor-flow week.
# The underlying reference week must be verified and recent before use in the headline.
if bofa and recent_official_week(bofa, new_york_date) and bofa["metrics"].get("us_equity_bn") is not None:
    stock_signals.append(("BofA/EPFR", bofa["metrics"]["us_equity_bn"], bofa["period"]))
if lipper and recent_official_week(lipper, new_york_date) and lipper["metrics"].get("us_equity_bn") is not None:
    stock_signals.append(("LSEG Lipper", lipper["metrics"]["us_equity_bn"], lipper["period"]))

mmf_change = ici_mmf["metrics"].get("weekly_change_bn") if ici_mmf else None
margin_change = finra["metrics"].get("margin_debt_mom_bn") if finra else None

if cross:
    overall_easy = (
        "주식형 펀드 방향이 출처마다 엇갈립니다. "
        "모집단과 기준기간이 다를 수 있어 합산·평균하지 않고 각 출처를 따로 봅니다."
    )
elif bofa and bofa.get("reference_week_verified") and bofa["metrics"].get("us_equity_bn") is not None and bofa["metrics"].get("mmf_bn") is not None:
    overall_easy = (
        "BofA/EPFR 자료에서 주식형과 MMF 방향이 함께 관찰됐습니다. "
        "집계 대상이 다를 수 있어 같은 돈의 직접 이동·주식 매수 전환으로 단정하지 않습니다."
    )
elif lipper and lipper.get("reference_week_verified") and lipper["metrics"].get("us_equity_bn") is not None and lipper["metrics"].get("mmf_bn") is not None:
    overall_easy = (
        "LSEG Lipper 동일 기준주간에 미국 주식형 자금과 글로벌 MMF 자금이 반대 방향을 보였습니다. "
        "집계 지역이 달라 직접 이동이나 전체 미국증시 순매도로 단정하지 않습니다."
    )
elif ici and ici_mmf and same_reference_week(ici, ici_mmf):
    overall_easy = "ICI 같은 주간 판정: " + flow_direction(
        ici["metrics"].get("domestic"), ici_mmf["metrics"].get("weekly_change_bn")
    )
elif ici and ici_mmf and not same_reference_week(ici, ici_mmf):
    overall_easy = (
        "주식형과 MMF 최신값의 기준주간이 달라 직접 자금 회전 판정을 보류합니다. "
        "각 수치는 별도 신호로만 봅니다."
    )
elif not stock_signals and mmf_change is not None and margin_change is not None:
    overall_easy = (
        f"MMF는 {direction_word(mmf_change)}, 마진부채는 "
        f"{'확대' if margin_change > 0 else '축소' if margin_change < 0 else '보합'}입니다. "
        "주간 현금성 자금과 월간 레버리지는 기간이 달라 각각 별도 신호로 봅니다."
    )
else:
    overall_easy = "비교 가능한 최신값이 부족하거나 기준기간이 달라 한 방향으로 단정하지 않습니다."



source_corrections = []
previous_lseg = (state.get("values") or {}).get("LSEG Lipper via Reuters|lipper") or {}
lseg_data = next((item for item in updates if item.get("kind") == "lipper"), None)
old_lseg_metrics = previous_lseg.get("metrics") or {}
old_lseg_evidence = previous_lseg.get("evidence") or {}
media_correction = bool(
    lseg_data and same_reference_week(previous_lseg, lseg_data)
    and lseg_data["metrics"].get("us_equity_bn") != old_lseg_metrics.get("us_equity_bn")
)
for x in updates:
    old = (state.get("values") or {}).get(f"{x['source']}|{x['kind']}")
    if isinstance(old, dict) and x["kind"] in ("combined", "mmf"):
        if period_date(old) == period_date(x):
            source_corrections.append(x["kind"])

status_lines = [
    "# US Fund Flow Watch",
    "",
    f"- parsed sources: {len(results)}",
    f"- updates: {len(updates)}",
    f"- corrected ICI categories: {','.join(source_corrections) or 'none'}",
]
for x in results:
    status_lines.append(f"- {x['source']} {x['kind']} | {x['period']} | {x['fingerprint'][:12]}")
for e in errors:
    status_lines.append(f"- error: {e}")
if sp500:
    status_lines.append(
        f"- S&P500 context: {sp500['last_date']} {sp500['last_value']:.2f} | "
        f"peak {sp500['peak_date']} {sp500['peak_value']:.2f} | "
        f"drawdown {sp500['drawdown_pct']:.2f}% | band={sp500['band']} | source={sp500.get('source','unknown')}"
    )
    status_lines.append(f"- S&P500 band transition: {old_band or 'none'} -> {current_band or 'none'} | changed={str(drawdown_transition).lower()}")
if jpm_updated:
    status_lines.append(
        f"- JPM household delta: withdrawers={jpm_withdrawal_delta}pp | spending-funded={jpm_spending_delta}pp"
    )
if hartnett_macro:
    status_lines.append(
        f"- Hartnett 10Y={hartnett_macro['yield_10y_pct']}% "
        f"2Y={hartnett_macro['yield_2y_pct']}% 5D={hartnett_macro['yield_10y_5d_bp']}bp "
        f"FedUpper={hartnett_macro['fed_target_upper_pct']}% "
        f"obs={hartnett_macro['treasury_date']} "
        f"init={hartnett_init} level_transition={bond_level_transition} "
        f"momentum_transition={bond_momentum_transition} target_change={target_rate_change}"
    )
status_lines.append(f"- Hartnett election stage: {election_window} transition={election_transition}")
status_lines.append(
    f"- Hartnett ICI reference check: reference={ici_mmf.get('period') if ici_mmf else 'missing'} "
    f"date={new_york_date} recent={str(mmf_recent).lower()}"
)
status_lines.append(
    "- Hartnett news rule: BofA/Bloomberg 2026-10-09 figures are dated analyst reports, "
    "not a live repeatable official weekly flow series"
)
if fx:
    status_lines.append(f"- USD/KRW: {fx['usdkrw']} ({fx['date']})")
STATUS.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

force = (os.getenv("FORCE_SEND") or "").lower() in ("1", "true", "yes")
should_alert = bool(updates or force or drawdown_transition or hartnett_init
                    or bond_level_transition or bond_momentum_transition
                    or target_rate_change or election_transition)
# Never send a dollar-denominated report lacking a fresh, verified KRW conversion.
# Do not advance fingerprints on this failure; a later healthy run may deliver it.
if should_alert and fx is None:
    raise RuntimeError("ECOS USD/KRW unavailable or stale; alert withheld and fingerprints preserved")
if should_alert:
    body = [
        f"🇺🇸 <b>[미국 증시 자금흐름 추적 | {'수치 정정' if (source_corrections or media_correction) else 'Hartnett 감시 추가' if hartnett_init and not updates else '신규 변화'}]</b>",
        "",
        "<b>한눈에 보기</b>",
    ]

    if ici_mmf:
        ch = ici_mmf["metrics"].get("weekly_change_bn")
        body.append(
            f"• 현금성 대기자금(MMF): {fmt_usd_bn_kr(ch, fx)} → "
            f"{'감소' if ch is not None and ch < 0 else '증가' if ch is not None and ch > 0 else '변화 없음'}"
        )
    if finra:
        md = finra["metrics"].get("margin_debt_mom_bn")
        body.append(
            f"• 레버리지(마진부채): {fmt_usd_bn_kr(md, fx)} 전월비 → "
            f"{'빚투 확대' if md is not None and md > 0 else '빚투 축소' if md is not None and md < 0 else '변화 제한'}"
        )
    if stock_signals:
        stock_text = " / ".join(
            f"{name}({reference}) {fmt_usd_bn_kr(value, fx)}"
            f"({'유입' if value > 0 else '유출' if value < 0 else '보합'})"
            for name, value, reference in stock_signals
        )
        body.append("• 미국 주식형: " + stock_text)
    else:
        body.append("• 미국 주식형: 최신 비교값 자동 확인 대기")
    if sp500:
        body.append(
            f"• S&P 500: {sp500['last_value']:,.2f} / 5년 내 고점 대비 {sp500['drawdown_pct']:.2f}% "
            f"→ {'15% 급락 구간' if sp500['band']=='stress' else '15% 급락 기준 미충족'}"
        )
    if jpm_household and fed_household:
        jm = jpm_household["metrics"]
        fm = fed_household["metrics"]
        body.append(
            f"• 가계 구조: 투자계좌 순인출자 {jm['withdrawers_all_pct']:.1f}% "
            f"(상위 10% {jm['withdrawers_top10_pct']:.1f}%) / "
            f"투자자산 충당 소비 {jm['spending_funded_pct']:.1f}% / "
            f"가계 기업주식·펀드 총자산 비중 {fm['equities_share_total_assets_pct']:.2f}%"
        )

    if media_correction:
        corrected_us = lseg_data["metrics"].get("us_equity_bn")
        detail = (
            f"Reuters 원문에서 재검증한 미국 주식형 순유출 {fmt_usd_bn_kr(corrected_us, fx)}."
            if corrected_us is not None and corrected_us < 0 else
            f"Reuters 원문에서 재검증한 미국 주식형 순유입 {fmt_usd_bn_kr(corrected_us, fx)}."
            if corrected_us is not None else
            "미국 주식형 수치는 기사 본문에서 재검증되지 않아 확인 대기."
        )
        body.append(
            "• <b>전송 오류 정정</b>: 직전 LSEG 미국 주식형 순유입 +5.6억달러 표기는 "
            "글로벌 주식형 순유입 +5.6억달러를 잘못 복사한 값이었습니다. "
            + detail + " 글로벌 주식형과 미국 주식형은 다른 모집단입니다."
        )
    if source_corrections:
        body.append(
            "• ICI 동일 기준기간에 기존 저장값과 다른 새 원자료 수치가 감지됨: "
            + ", ".join("MMF 총자산" if k=="mmf" else "주식·채권 자금흐름" for k in source_corrections)
            + " — 공식 수정치인지 수집 오류인지 원자료로 검산 필요"
        )
    # Hartnett/BofA is an analyst's publicly reported opinion, not an ICI official series.
    # Keep the Bloomberg-quoted $166.4B separate from ICI's U.S. fund-asset change.
    body += ["", "<b>Hartnett 현금·금리·중간선거 감시</b>"]
    body.append(
        f"• BofA/Hartnett 발언 기준선({HARTNETT_REPORT_DATE} Bloomberg 인용): "
        f"10/7 주간 MMF 유입 {fmt_usd_bn_kr(HARTNETT_MMF_REPORTED_BN, fx)} "
        "— ICI 공식 미국 MMF 자산 변화와 모집단·산식 미확인으로 별도 표시"
    )
    body.append(
        f"• 동일 보도에 나온 BofA 집계: 주식형 {fmt_usd_bn_kr(12.4, fx)}, "
        f"채권형 {fmt_usd_bn_kr(33.8, fx)}. ICI 자산 증가와 다른 시리즈로만 표시"
    )
    if ici_mmf:
        body.append(
            f"• ICI 미국 MMF: {html.escape(str(ici_mmf['period']))} 기준 "
            f"{fmt_usd_bn_kr(ici_mmf['metrics']['weekly_change_bn'], fx)} "
            "→ BofA 수치와 비교·합산 금지"
        )
    if hartnett_macro:
        zone_txt = {
            "below_5_30":"5.30% 미만",
            "5_30_to_5_50":"5.30~5.50% 미만",
            "5_50_to_6_00":"5.50~6.00% 미만",
            "at_or_above_6_00":"6.00% 이상",
        }.get(hartnett_macro["bond_level"],"검증 대기")
        body.append(
            f"• 미 국채 10년물 {hartnett_macro['yield_10y_pct']:.3f}% "
            f"/ 2년물 {hartnett_macro['yield_2y_pct']:.3f}% "
            f"/ 10년물 5거래일 {hartnett_macro['yield_10y_5d_bp']:+.1f}bp "
            f"(기준 {hartnett_macro['treasury_date']})"
        )
        body.append(f"• 장기금리 내부 위험구간: {zone_txt} (자체 기준이며 BofA 제시 임계치 아님)")
        prior_rate=old_hartnett.get("hartnett_fed_target_upper_pct")
        rate_move=(hartnett_macro["fed_target_upper_pct"]-prior_rate) if isinstance(prior_rate,(int,float)) else None
        rate_note=(
            f" · 직전 저장값 대비 {'인상' if rate_move > 0 else '인하'} {abs(rate_move)*100:.0f}bp"
            if rate_move is not None and abs(rate_move)>=0.245 else ""
        )
        body.append(
            f"• 연준 목표금리 상단 {hartnett_macro['fed_target_upper_pct']:.2f}% "
            f"(효력일 {hartnett_macro['fed_effective_date']}){rate_note}"
        )
        body.append(
            f"• 검증 판정: {html.escape(hartnett_regime_signal(mmf_change if mmf_recent else None, hartnett_macro))}"
        )
    else:
        body.append("• 미국 국채·연준 공식 수치 수집 실패: 금리와 현금 이동의 결합 판정 보류")
    body.append(
        f"• 미국 중간선거 2026-11-03 / 감시 단계 {election_window} "
        "— 민주당 양원 승리 시 미국 증시 -10% 초과 가능성은 Hartnett의 조건부 시나리오이며 "
        "실제 선거 결과 또는 시장하락 확정 예측이 아님"
    )
    body.append(
        f'• 근거: <a href="{html.escape(HARTNETT_REPORT_URL, quote=True)}">Bloomberg 인용 보도</a> / '
        f'<a href="{html.escape(ICI_MMF, quote=True)}">ICI 미국 MMF 공식</a> / '
        f'<a href="{html.escape(hartnett_macro["url_yields"] if hartnett_macro else TREASURY_OFFICIAL_CURVE, quote=True)}">미 재무부 국채금리</a> / '
        f'<a href="{html.escape(hartnett_macro["url_fed"] if hartnett_macro else FED_CURRENT_VERIFIED_FALLBACK, quote=True)}">연준 FOMC 기준금리</a> / '
        f'<a href="https://www.fec.gov/documents/5910/2026pdates.pdf">미국 선거일 공식자료</a>'
    )

    body += [
        f"→ <b>종합</b>: {html.escape(overall_easy)}",
        "",
        "<b>이번에 실제로 바뀐 값</b>",
    ]

    selected = results if force else updates
    if drawdown_transition:
        body += [
            f"<b>S&P 500 15% 낙폭 체계 변화</b>",
            f"• {html.escape(str(old_band))} → {html.escape(str(current_band))} "
            f"/ 현재 낙폭 {sp500['drawdown_pct']:.2f}%" if sp500 else "• S&P 500 상태 확인 불가",
            "",
        ]
    for x in selected:
        body += [
            f"<b>{html.escape(x['source'])} | {html.escape(str(x.get('period') or ''))}</b>",
            source_block(x, fx),
            f'• 원천: <a href="{html.escape(x["url"], quote=True)}">열기</a>',
            "",
        ]

    body.append("<b>현재 판정</b>")
    for s in interpret:
        body.append("• " + html.escape(s))
    for s in cross:
        body.append("• ⚠️ " + html.escape(s))
    if not interpret:
        body.append("• 비교 가능한 최신 공식 수치가 부족해 방향 판정을 보류합니다.")
    if not cross:
        body.append("• 출처 간 미국 주식 방향 충돌은 확인되지 않았거나 동시 비교 가능한 값이 부족합니다.")

    # Keep technical parser errors in the workflow status only. Telegram gets simple availability labels.
    if errors:
        body += ["", "<b>확인 대기</b>"]
        seen_labels = set()
        for e in errors:
            label = e.split(":", 1)[0].strip()
            if label and label not in seen_labels:
                seen_labels.add(label)
                body.append(f"• {html.escape(label)}: 최신값 자동 수집 재확인 중")

    body += [
        "",
        "<b>해석 원칙</b>",
        "• 같은 출처 안에서만 미국주식↔MMF 방향을 조합해 자금 회전을 해석",
        "• BofA/Hartnett Bloomberg 인용 2026-10-07 주간 MMF 1,664억달러는 당시 보도값이며 이후 주간 최신값으로 재사용 금지",
        "• BofA/Hartnett 주간 순유입과 ICI 공식 MMF 총자산 주간 증감은 모집단·산식이 달라 합산·직접 비교 금지",
        "• ICI·BofA/EPFR·LSEG Lipper는 모집단이 달라 합산·평균하지 않음",
        "• 보도일은 집계주간이 아님. 출처별 실제 집계기간이 확인되지 않으면 주식형 자금흐름 충돌 판정도 보류",
        "• 미 국채 10년물 5.30%·5.50%·6.00%와 5거래일 20bp는 내부 경보 기준이며 BofA가 공식 제시한 임계치가 아님",
        "• FINRA 마진부채는 월간 레버리지 확인용으로 주간 펀드 흐름과 기간을 섞지 않음",
        "• JPMorganChase Institute 가계 인출은 저빈도 구조지표로 사용하며 새 공식 수치가 있을 때만 변화로 처리",
        "• Federal Reserve Z.1 가계 자산은 분기 구조지표로 사용하며 새 분기 값이 있을 때만 변화로 처리",
        "• S&P 500은 FRED를 우선 조회하고 장애 시 Yahoo Finance 종가로 대체해 5년 내 고점 대비 낙폭을 계산, 15% 선 진입·이탈 때만 별도 경보",
        "• S&P 500 15% 이상 하락 중 JPMorgan 순인출자 비중까지 상승할 때만 과거 패턴 이탈 경보로 격상",
        "• MMF 유출액이 그대로 주식으로 이동했다고 단정하지 않음",
        "• 같은 기준기간·같은 수치면 원천 URL이나 문구가 바뀌어도 중복 알림하지 않음",
        "• 모든 달러 금액은 같은 문장 바로 뒤 괄호에 한국은행 ECOS 환율 기준 원화 환산액을 함께 표시",
    ]
    if fx:
        body.append(f"• 원화 환산: 한국은행 ECOS USD/KRW {fx['usdkrw']:,.2f} ({fx['date']})")

    ALERT.write_text("\n".join(body) + "\n", encoding="utf-8")

    newstate = state
    newstate.setdefault("seen", {})
    newstate.setdefault("values", {})
    for x in results:
        key = f"{x['source']}|{x['kind']}"
        newstate["seen"][key] = x["fingerprint"]
        newstate["values"][key] = x
    if hartnett_macro:
        newstate.setdefault("derived", {})
        newstate["derived"].update({
            "hartnett_tracking_version": HARTNETT_TRACK_VERSION,
            "hartnett_treasury_date": hartnett_macro["treasury_date"],
            "hartnett_10y_pct": hartnett_macro["yield_10y_pct"],
            "hartnett_10y_5d_bp": hartnett_macro["yield_10y_5d_bp"],
            "hartnett_bond_level": hartnett_macro["bond_level"],
            "hartnett_bond_momentum": hartnett_macro["bond_momentum"],
            "hartnett_fed_target_upper_pct": hartnett_macro["fed_target_upper_pct"],
            "hartnett_fed_effective_date": hartnett_macro["fed_effective_date"],
            "hartnett_election_stage": election_window,
        })
    if sp500:
        newstate.setdefault("derived", {})
        newstate["derived"].update({
            "sp500_drawdown_band": sp500["band"],
            "sp500_last_date": sp500["last_date"],
            "sp500_last_value": sp500["last_value"],
            "sp500_peak_date": sp500["peak_date"],
            "sp500_peak_value": sp500["peak_value"],
            "sp500_drawdown_pct": sp500["drawdown_pct"],
        })
    newstate["updated_at_kst"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
    PENDING.write_text(json.dumps(newstate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"us_fund_flow_alert_ready=true updates={len(updates)} "
        f"drawdown_transition={str(drawdown_transition).lower()} "
        f"hartnett_init={str(hartnett_init).lower()} "
        f"bond_level_transition={str(bond_level_transition).lower()}"
    )
else:
    # A neutral weekly yield-momentum regime must be recorded without sending Telegram.
    # Otherwise, after an earlier +20bp alert a neutral reset is never saved and a
    # later fresh +20bp episode is incorrectly suppressed as "already seen".
    silent_state = json.loads(json.dumps(state))
    changed_silent = False
    if hartnett_macro:
        derived = silent_state.setdefault("derived", {})
        latest_hartnett = {
            "hartnett_treasury_date": hartnett_macro["treasury_date"],
            "hartnett_10y_pct": hartnett_macro["yield_10y_pct"],
            "hartnett_10y_5d_bp": hartnett_macro["yield_10y_5d_bp"],
            "hartnett_bond_level": hartnett_macro["bond_level"],
            "hartnett_bond_momentum": hartnett_macro["bond_momentum"],
            "hartnett_fed_target_upper_pct": hartnett_macro["fed_target_upper_pct"],
            "hartnett_fed_effective_date": hartnett_macro["fed_effective_date"],
            "hartnett_election_stage": election_window,
        }
        for key, value in latest_hartnett.items():
            if derived.get(key) != value:
                derived[key] = value
                changed_silent = True
    if changed_silent:
        # This contains only previously delivered source fingerprints plus checked
        # derived context. No unseen ICI/Reuters source observation is acknowledged.
        PENDING.write_text(
            json.dumps(silent_state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("us_fund_flow_alert_ready=false silent_derived_state_refresh=true")
    else:
        print("us_fund_flow_alert_ready=false unchanged=true")

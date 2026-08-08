from __future__ import annotations

import csv
import io
import json
import math
import pathlib
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

import jobs_wage_watch as watch

ROOT = pathlib.Path(__file__).resolve().parents[1]
FULL_STATE_PATH = ROOT / "data" / "jobs_wage_full_state.json"
FULL_PENDING_PATH = ROOT / "out" / "jobs_wage_full_state_pending.json"
ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_SCHEDULE = "https://www.bls.gov/schedule/news_release/empsit.htm"
ADP_CALENDAR = "https://adpemploymentreport.com/"
FRED_GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"

BLS_RELEASES = {
    "2026-07": datetime(2026, 8, 7, 8, 30, tzinfo=ET),
    "2026-08": datetime(2026, 9, 4, 8, 30, tzinfo=ET),
    "2026-09": datetime(2026, 10, 2, 8, 30, tzinfo=ET),
    "2026-10": datetime(2026, 11, 6, 8, 30, tzinfo=ET),
    "2026-11": datetime(2026, 12, 4, 8, 30, tzinfo=ET),
}

ADP_RELEASES = [
    datetime(2026, 8, 5, 8, 15, tzinfo=ET),
    datetime(2026, 9, 2, 8, 15, tzinfo=ET),
    datetime(2026, 9, 30, 8, 15, tzinfo=ET),
    datetime(2026, 11, 4, 8, 15, tzinfo=ET),
    datetime(2026, 12, 2, 8, 15, tzinfo=ET),
]

# Official BLS public API series. CES employment levels are thousands of jobs;
# CPS labor-force levels are thousands of persons.
BLS_SERIES = {
    "nfp_level": "CES0000000001",
    "private_level": "CES0500000001",
    "government_level": "CES9000000001",
    "manufacturing_level": "CES3000000001",
    "construction_level": "CES2000000001",
    "private_education_health_level": "CES6500000001",
    "leisure_hospitality_level": "CES7000000001",
    "professional_business_level": "CES6000000001",
    "temp_help_level": "CES6056132001",
    "ahe": "CES0500000003",
    "workweek": "CES0500000002",
    "manufacturing_workweek": "CES3000000002",
    "manufacturing_overtime": "CES3000000004",
    "unemployment_rate": "LNS14000000",
    "participation_rate": "LNS11300000",
    "epop": "LNS12300000",
    "labor_force": "LNS11000000",
    "household_employment": "LNS12000000",
    "unemployment_level": "LNS13000000",
    "not_in_labor_force": "LNS15000000",
    "civilian_population": "LNS10000000",
}

YAHOO_ASSETS = {
    "DXY": "DX-Y.NYB",
    "USD/JPY": "JPY=X",
    "EUR/USD": "EURUSD=X",
    "USD/KRW": "KRW=X",
    "TLT": "TLT",
    "VIX": "^VIX",
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "SOXX": "SOXX",
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "Gold": "GC=F",
    "Bitcoin": "BTC-USD",
    "HYG": "HYG",
    "JNK": "JNK",
}

FRED_SERIES = {
    "UST 2Y": "DGS2",
    "UST 5Y": "DGS5",
    "UST 10Y": "DGS10",
    "10Y real yield": "DFII10",
    "10Y BEI": "T10YIE",
}


def _fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-jobs-wage-full-report/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _fmt_int(v) -> str:
    if v is None:
        return "확인 불가"
    return f"{int(round(v)):+,}" if v != 0 else "0"


def _fmt_level(v) -> str:
    if v is None:
        return "확인 불가"
    return f"{int(round(v)):,}"


def _fmt_pct(v, digits: int = 1) -> str:
    return "확인 불가" if v is None else f"{v:.{digits}f}%"


def _fmt_bp(v) -> str:
    return "확인 불가" if v is None else f"{v:+.1f}bp"


def _period_shift(period: str, months: int) -> str:
    y, m = map(int, period.split("-"))
    idx = y * 12 + (m - 1) + months
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _load_full_state() -> dict:
    if not FULL_STATE_PATH.exists():
        return {}
    try:
        obj = json.loads(FULL_STATE_PATH.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _monthly_rows(series: dict) -> list[dict]:
    rows = []
    for item in series.get("data") or []:
        p = str(item.get("period") or "")
        if not p.startswith("M") or p == "M13":
            continue
        try:
            y = int(item["year"])
            m = int(p[1:])
            value = float(item["value"])
        except Exception:
            continue
        rows.append({"period": f"{y:04d}-{m:02d}", "value": value})
    rows.sort(key=lambda x: x["period"], reverse=True)
    return rows


def _query_bls_snapshot() -> dict:
    now = datetime.now(ET)
    payload = json.dumps(
        {
            "seriesid": list(BLS_SERIES.values()),
            "startyear": str(now.year - 2),
            "endyear": str(now.year),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        BLS_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; khs-jobs-wage-full-report/1.0)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        obj = json.loads(r.read().decode("utf-8"))
    if obj.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS supplemental API failed: {obj.get('status')} {obj.get('message')}")
    series_map = {str(s.get("seriesID")): _monthly_rows(s) for s in (obj.get("Results") or {}).get("series") or []}
    by_name = {name: series_map.get(sid, []) for name, sid in BLS_SERIES.items()}
    required = ["nfp_level", "private_level", "government_level", "manufacturing_level", "construction_level", "ahe", "workweek", "unemployment_rate", "participation_rate", "epop", "labor_force", "household_employment", "not_in_labor_force"]
    missing = [name for name in required if not by_name.get(name)]
    if missing:
        raise RuntimeError(f"BLS supplemental core series missing: {missing}")
    return by_name


def _value(rows: list[dict], period: str):
    for row in rows:
        if row["period"] == period:
            return row["value"]
    return None


def _latest_period(bls: dict) -> str:
    periods = []
    for name in ("nfp_level", "unemployment_rate", "participation_rate", "epop"):
        rows = bls.get(name) or []
        if not rows:
            raise RuntimeError(f"BLS latest period unavailable for {name}")
        periods.append(rows[0]["period"])
    if len(set(periods)) != 1:
        raise RuntimeError(f"BLS supplemental latest-period mismatch: {periods}")
    return periods[0]


def _change_jobs(bls: dict, name: str, period: str):
    cur = _value(bls.get(name, []), period)
    prev = _value(bls.get(name, []), _period_shift(period, -1))
    if cur is None or prev is None:
        return None
    return int(round((cur - prev) * 1000))


def _pct_change(bls: dict, name: str, period: str):
    cur = _value(bls.get(name, []), period)
    prev = _value(bls.get(name, []), _period_shift(period, -1))
    if cur is None or prev in (None, 0):
        return None
    return (cur / prev - 1.0) * 100.0


def _yoy_change(bls: dict, name: str, period: str):
    cur = _value(bls.get(name, []), period)
    prev = _value(bls.get(name, []), _period_shift(period, -12))
    if cur is None or prev in (None, 0):
        return None
    return (cur / prev - 1.0) * 100.0


def _breakeven_proxy(bls: dict, period: str) -> dict:
    lf = bls["labor_force"]
    u = _value(bls["unemployment_rate"], period)
    if u is None:
        return {"low": None, "high": None, "three": None, "six": None}
    diffs = []
    for i in range(0, 6):
        p = _period_shift(period, -i)
        p1 = _period_shift(period, -i - 1)
        a = _value(lf, p)
        b = _value(lf, p1)
        if a is not None and b is not None:
            diffs.append((a - b) * 1000)
    if len(diffs) < 3:
        return {"low": None, "high": None, "three": None, "six": None}
    three = mean(diffs[:3]) * (1 - u / 100.0)
    six = mean(diffs[:6]) * (1 - u / 100.0) if len(diffs) >= 6 else None
    vals = [x for x in (three, six) if x is not None]
    return {
        "low": min(vals) if vals else None,
        "high": max(vals) if vals else None,
        "three": three,
        "six": six,
    }


def _revision_block(bls: dict, period: str, previous_state: dict) -> dict:
    levels_now = {row["period"]: row["value"] for row in bls.get("nfp_level", [])[:18]}
    old_levels = previous_state.get("bls_nfp_levels") or {}
    rows = []
    total_revision = 0
    has_revision = False
    for offset in (-1, -2):
        p = _period_shift(period, offset)
        pp = _period_shift(p, -1)
        current = None
        original = None
        if p in levels_now and pp in levels_now:
            current = int(round((levels_now[p] - levels_now[pp]) * 1000))
        if p in old_levels and pp in old_levels:
            original = int(round((float(old_levels[p]) - float(old_levels[pp])) * 1000))
        revision = None if current is None or original is None else current - original
        if revision is not None:
            total_revision += revision
            has_revision = True
        rows.append({"period": p, "original": original, "revised": current, "revision": revision})
    return {
        "rows": rows,
        "net_revision": total_revision if has_revision else None,
        "levels_now": levels_now,
    }


def _parse_num(text: str | None):
    if text is None:
        return None
    try:
        return int(text.replace(",", "").replace("+", "").strip())
    except Exception:
        return None


def _enrich_adp(r: watch.Release | None) -> dict:
    if not r:
        return {}
    try:
        text = watch.html_text(watch.fetch_text(r.source_url))
    except Exception:
        text = r.raw_summary or ""

    def num(label: str):
        m = re.search(label + r"\s*[:]?\s*([+\-]?\d[\d,]*)", text, re.I)
        return _parse_num(m.group(1)) if m else None

    def pay(pattern: str):
        m = re.search(pattern, text, re.I)
        return float(m.group(1)) if m else None

    industries = {
        "natural_resources_mining": num(r"Natural resources/mining"),
        "construction": num(r"Construction"),
        "manufacturing": num(r"Manufacturing"),
        "trade_transport_utilities": num(r"Trade/transportation/utilities"),
        "information": num(r"Information"),
        "financial_activities": num(r"Financial activities"),
        "professional_business": num(r"Professional/business services"),
        "education_health": num(r"Education/health services"),
        "leisure_hospitality": num(r"Leisure/hospitality"),
        "other_services": num(r"Other services"),
    }
    sizes = {
        "small": num(r"Small establishments"),
        "1_19": num(r"1-19 employees"),
        "20_49": num(r"20-49 employees"),
        "medium": num(r"Medium establishments"),
        "50_249": num(r"50-249 employees"),
        "250_499": num(r"250-499 employees"),
        "large": num(r"Large establishments"),
        "500_plus": num(r"500\+ employees"),
    }
    overall_pay = pay(r"pay was up\s*([0-9.]+)\s*percent year-over-year")
    if overall_pay is None:
        overall_pay = r.metrics.get("job_stayer_pay")
    return {"industries": industries, "sizes": sizes, "overall_pay": overall_pay, "text": text}


def _enrich_claims(r: watch.Release | None) -> dict:
    if not r:
        return {}
    text = r.raw_summary or ""
    m = re.search(r"previous week's revised level.*?from\s*([\d,]+)\s*to\s*([\d,]+)", text, re.I)
    original = _parse_num(m.group(1)) if m else None
    revised = _parse_num(m.group(2)) if m else r.metrics.get("previous_revised")
    revision = None if original is None or revised is None else revised - original
    c = re.search(r"insured unemployment.*?previous week's revised level.*?from\s*([\d,]+)\s*to\s*([\d,]+)", text, re.I)
    c_original = _parse_num(c.group(1)) if c else None
    c_revised = _parse_num(c.group(2)) if c else r.metrics.get("continuing_previous_revised")
    c_revision = None if c_original is None or c_revised is None else c_revised - c_original
    cw = re.search(r"week ending\s+([A-Za-z]+\s+\d{1,2}).{0,80}?insured unemployment", text, re.I)
    return {
        "previous_original": original,
        "previous_revised": revised,
        "previous_revision": revision,
        "continuing_previous_original": c_original,
        "continuing_previous_revised": c_revised,
        "continuing_previous_revision": c_revision,
        "continuing_reference_week": cw.group(1) if cw else None,
        "seasonal_adjustment": "seasonally adjusted" if "seasonally adjusted" in text.lower() else "확인 불가",
    }


def _fred_latest(series_id: str) -> dict:
    try:
        text = _fetch(FRED_GRAPH + urllib.parse.quote(series_id)).decode("utf-8", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        vals = []
        for row in rows[1:]:
            if len(row) < 2 or row[1] in ("", "."):
                continue
            try:
                vals.append((row[0], float(row[1])))
            except Exception:
                continue
        if not vals:
            return {"value": None, "date": None, "change_bp": None}
        latest = vals[-1]
        prev = vals[-2] if len(vals) >= 2 else None
        change_bp = (latest[1] - prev[1]) * 100 if prev else None
        return {"value": latest[1], "date": latest[0], "change_bp": change_bp}
    except Exception as e:
        return {"value": None, "date": None, "change_bp": None, "error": f"{type(e).__name__}: {e}"}


def _yahoo_reaction(symbol: str, release_dt: datetime) -> dict:
    try:
        now = datetime.now(ET)
        p1 = int((release_dt - timedelta(hours=6)).timestamp())
        p2 = int((now + timedelta(minutes=10)).timestamp())
        qs = urllib.parse.urlencode({
            "period1": p1,
            "period2": p2,
            "interval": "5m",
            "includePrePost": "true",
            "events": "div,splits",
        })
        url = YAHOO_CHART + urllib.parse.quote(symbol, safe="") + "?" + qs
        obj = json.loads(_fetch(url).decode("utf-8"))
        result = ((obj.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return {"value": None, "change_pct": None, "source": "Yahoo Finance"}
        meta = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
        pairs = [(int(ts), float(c)) for ts, c in zip(timestamps, closes) if c is not None]
        baseline_pair = [p for p in pairs if p[0] <= int(release_dt.timestamp())]
        after_pair = [p for p in pairs if p[0] > int(release_dt.timestamp())]
        baseline = baseline_pair[-1][1] if baseline_pair else meta.get("chartPreviousClose") or meta.get("previousClose")
        latest = after_pair[-1][1] if after_pair else None
        latest_ts = after_pair[-1][0] if after_pair else None
        if baseline in (None, 0) or latest is None:
            return {"value": latest, "change_pct": None, "source": "Yahoo Finance", "timestamp": latest_ts}
        return {
            "value": latest,
            "change_pct": (latest / float(baseline) - 1.0) * 100.0,
            "source": "Yahoo Finance",
            "timestamp": latest_ts,
        }
    except Exception as e:
        return {"value": None, "change_pct": None, "source": "Yahoo Finance", "error": f"{type(e).__name__}: {e}"}


def _market_snapshot(trigger_dt: datetime) -> dict:
    yahoo = {name: _yahoo_reaction(symbol, trigger_dt) for name, symbol in YAHOO_ASSETS.items()}
    fred = {name: _fred_latest(series_id) for name, series_id in FRED_SERIES.items()}
    return {"yahoo": yahoo, "fred": fred}


def _latest_release_set(new_releases: list[watch.Release]) -> dict:
    result = {r.kind: r for r in new_releases}
    for kind, parser in (("employment_situation", watch.parse_bls), ("weekly_claims", watch.parse_claims), ("adp", watch.parse_adp)):
        if kind in result:
            continue
        try:
            r = parser()
            if r:
                result[kind] = r
        except Exception:
            pass
    return result


def _next_bls(now: datetime) -> datetime | None:
    future = sorted(dt for dt in BLS_RELEASES.values() if dt > now)
    return future[0] if future else None


def _next_adp(now: datetime) -> datetime | None:
    future = sorted(dt for dt in ADP_RELEASES if dt > now)
    return future[0] if future else None


def _next_claims(now: datetime) -> datetime:
    days = (3 - now.weekday()) % 7  # Thursday=3
    if days == 0 and now.time() >= datetime(2000, 1, 1, 8, 30).time():
        days = 7
    d = now + timedelta(days=days)
    return d.replace(hour=8, minute=30, second=0, microsecond=0)


def _regime(latest: dict, bls: dict, period: str) -> tuple[str, dict]:
    b = latest.get("employment_situation")
    c = latest.get("weekly_claims")
    a = latest.get("adp")
    nfp = b.metrics.get("nfp") if b else _change_jobs(bls, "nfp_level", period)
    adp = a.metrics.get("private_payroll_change") if a else None
    initial = c.metrics.get("initial_claims") if c else None
    continuing = c.metrics.get("continuing_claims") if c else None
    unemployment = _value(bls["unemployment_rate"], period)
    participation = _value(bls["participation_rate"], period)
    weak_hiring = (nfp is not None and nfp < 100000) or (adp is not None and adp < 100000)
    low_layoffs = initial is not None and initial < 240000
    hard_reemployment = continuing is not None and continuing >= 1850000
    wage_sticky = _yoy_change(bls, "ahe", period) is not None and _yoy_change(bls, "ahe", period) >= 3.5
    if weak_hiring and low_layoffs:
        label = "저해고·저채용(고용 동결)"
    elif weak_hiring and hard_reemployment:
        label = "침체 초기 위험"
    elif not weak_hiring and unemployment is not None and unemployment <= 4.5:
        label = "연착륙"
    else:
        label = "혼합 국면"
    if wage_sticky and weak_hiring:
        label += " + 임금 경직"
    return label, {
        "nfp": nfp,
        "adp": adp,
        "initial": initial,
        "continuing": continuing,
        "unemployment": unemployment,
        "participation": participation,
        "weak_hiring": weak_hiring,
        "low_layoffs": low_layoffs,
        "hard_reemployment": hard_reemployment,
        "wage_sticky": wage_sticky,
    }


def _release_heading(r: watch.Release) -> str:
    if r.kind == "employment_situation":
        return "① Employment Situation"
    if r.kind == "weekly_claims":
        return "② Weekly Claims"
    return "③ ADP National Employment Report·Pay Insights"


def _new_release_summary(new_releases: list[watch.Release], adp_extra: dict, claims_extra: dict) -> str:
    lines = []
    for r in new_releases:
        m = r.metrics
        lines.append(_release_heading(r))
        lines.append(f"- 기준기간: {r.period} | 발표: {r.release_dt_et.strftime('%Y-%m-%d %H:%M ET')} / {r.release_dt_et.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')}")
        if r.kind == "employment_situation":
            lines += [
                f"- NFP {_fmt_int(m.get('nfp'))}명 | 실업률 {_fmt_pct(m.get('unemployment_rate'))} | 참가율 {_fmt_pct(m.get('participation_rate'))} | EPOP {_fmt_pct(m.get('epop'))}",
                f"- AHE YoY {_fmt_pct(m.get('ahe_yoy'))} | 주당근로 {m.get('workweek') if m.get('workweek') is not None else '확인 불가'}시간 | 제조업 초과근로 {m.get('manufacturing_overtime') if m.get('manufacturing_overtime') is not None else '확인 불가'}시간",
            ]
        elif r.kind == "weekly_claims":
            lines += [
                f"- Initial {_fmt_level(m.get('initial_claims'))}건 | 4주 평균 {_fmt_level(m.get('four_week_average'))}건 | Continuing {_fmt_level(m.get('continuing_claims'))}건",
                f"- 직전주 Initial: 원래 {_fmt_level(claims_extra.get('previous_original'))} → 수정 {_fmt_level(claims_extra.get('previous_revised'))} ({_fmt_int(claims_extra.get('previous_revision'))})",
                f"- Insured unemployment rate {_fmt_pct(m.get('insured_unemployment_rate'))} | 계절조정: {claims_extra.get('seasonal_adjustment') or '확인 불가'}",
            ]
        else:
            lines += [
                f"- ADP 민간고용 {_fmt_int(m.get('private_payroll_change'))}명 | Goods {_fmt_int(m.get('goods'))} | Services {_fmt_int(m.get('services'))}",
                f"- 연간 임금(헤드라인) {_fmt_pct(adp_extra.get('overall_pay'))} | Stayer {_fmt_pct(m.get('job_stayer_pay'))} | Changer {_fmt_pct(m.get('job_changer_pay'))} | 프리미엄 {_fmt_pct(m.get('job_changer_premium'))}",
                "- ADP는 민간부문 추정치이고 BLS NFP는 정부 공식통계입니다.",
            ]
        lines.append(f"- 공식 원문: {r.source_url}")
    return "\n".join(lines)


def _current_number_tracking(latest: dict, bls: dict, period: str, revisions: dict, adp_extra: dict) -> str:
    cur = lambda name: _value(bls.get(name, []), period)
    hh_change = _change_jobs(bls, "household_employment", period)
    lf_change = _change_jobs(bls, "labor_force", period)
    nilf_change = _change_jobs(bls, "not_in_labor_force", period)
    ahe_mom = _pct_change(bls, "ahe", period)
    ahe_yoy = _yoy_change(bls, "ahe", period)
    sector_names = [
        ("민간", "private_level"), ("정부", "government_level"), ("제조업", "manufacturing_level"),
        ("건설", "construction_level"), ("민간 교육·헬스", "private_education_health_level"),
        ("레저·호스피탈리티", "leisure_hospitality_level"), ("전문·비즈니스", "professional_business_level"),
        ("Temp Help", "temp_help_level"),
    ]
    sectors = " | ".join(f"{label} {_fmt_int(_change_jobs(bls, name, period))}" for label, name in sector_names)
    rev_lines = []
    for row in revisions["rows"]:
        rev_lines.append(
            f"{row['period']}: 원래 {_fmt_int(row['original'])} → 현재 {_fmt_int(row['revised'])} (수정 {_fmt_int(row['revision'])})"
        )
    claims = latest.get("weekly_claims")
    adp = latest.get("adp")
    claims_line = "확인 불가"
    if claims:
        claims_line = f"Initial {_fmt_level(claims.metrics.get('initial_claims'))} / Continuing {_fmt_level(claims.metrics.get('continuing_claims'))}"
    adp_line = "확인 불가"
    if adp:
        adp_line = f"고용 {_fmt_int(adp.metrics.get('private_payroll_change'))}, Stayer {_fmt_pct(adp.metrics.get('job_stayer_pay'))}, Changer {_fmt_pct(adp.metrics.get('job_changer_pay'))}"
    return (
        f"- BLS 기준월 {period}: NFP {_fmt_int(_change_jobs(bls, 'nfp_level', period))} | 민간 {_fmt_int(_change_jobs(bls, 'private_level', period))} | 정부 {_fmt_int(_change_jobs(bls, 'government_level', period))}\n"
        f"- 업종: {sectors}\n"
        f"- AHE MoM {_fmt_pct(ahe_mom, 2)} / YoY {_fmt_pct(ahe_yoy)} | 주당근로 {cur('workweek') if cur('workweek') is not None else '확인 불가'}시간 | 제조업 근로 {cur('manufacturing_workweek') if cur('manufacturing_workweek') is not None else '확인 불가'}시간 | 초과근로 {cur('manufacturing_overtime') if cur('manufacturing_overtime') is not None else '확인 불가'}시간\n"
        f"- CPS: 실업률 {_fmt_pct(cur('unemployment_rate'))} | 참가율 {_fmt_pct(cur('participation_rate'))} | EPOP {_fmt_pct(cur('epop'))} | 가계취업 {_fmt_int(hh_change)} | 노동력 {_fmt_int(lf_change)} | 비경제활동 {_fmt_int(nilf_change)}\n"
        f"- 이전 2개월 NFP 수정: {' / '.join(rev_lines)} | 합계 수정 {_fmt_int(revisions.get('net_revision'))}\n"
        f"- 최신 공식 비교값 — Weekly Claims: {claims_line} | ADP: {adp_line}\n"
        f"- ADP 세부(공식 공개 시): 헤드라인 임금 {_fmt_pct(adp_extra.get('overall_pay'))}"
    )


def _future_revaluation(regime: str, signals: dict, bls: dict, period: str, adp_extra: dict) -> str:
    temp = _change_jobs(bls, "temp_help_level", period)
    overtime = _value(bls["manufacturing_overtime"], period)
    hours = _value(bls["workweek"], period)
    adp_ind = adp_extra.get("industries") or {}
    size = adp_extra.get("sizes") or {}
    weak_small = sum(x for x in (size.get("1_19"), size.get("20_49")) if isinstance(x, int)) if size else None
    points = [
        f"- 국면: **{regime}**. 신규채용 약화가 반복되면 노동소득 증가율 둔화 → 소비량/기업 매출 증가율 둔화 → 경기민감 EPS 하향의 순서로 재평가될 수 있습니다.",
        f"- Temp Help {_fmt_int(temp)}명, 제조업 초과근로 {overtime if overtime is not None else '확인 불가'}시간, 전체 주당근로 {hours if hours is not None else '확인 불가'}시간은 헤드라인 NFP보다 선행적으로 고용의 질을 보여주는 보조 신호입니다.",
        "- 임금은 BLS AHE와 ADP Stayer·Changer를 함께 봅니다. Changer만 강하면 숙련인력 희소성/구성효과일 수 있어 광범위한 임금 인플레로 단정하지 않습니다.",
    ]
    if weak_small is not None:
        points.append(f"- ADP 소형사업장(1~49명) 합계 {_fmt_int(weak_small)}명: 중소기업 채용이 약하면 금융여건·내수 민감 업종의 후행 부담을 더 크게 봅니다.")
    if adp_ind:
        strongest = sorted(((k, v) for k, v in adp_ind.items() if isinstance(v, int)), key=lambda kv: kv[1], reverse=True)[:2]
        weakest = sorted(((k, v) for k, v in adp_ind.items() if isinstance(v, int)), key=lambda kv: kv[1])[:2]
        points.append(f"- ADP 업종 확산: 강한 쪽 {strongest or '확인 불가'}, 약한 쪽 {weakest or '확인 불가'} — 총고용이 한두 업종에 집중되면 민간 자생적 채용 폭은 약한 것으로 해석합니다.")
    return "\n".join(points)


def _breakeven_section(breakeven: dict, bls: dict, period: str) -> str:
    p = _value(bls["participation_rate"], period)
    hh = _change_jobs(bls, "household_employment", period)
    lf = _change_jobs(bls, "labor_force", period)
    nilf = _change_jobs(bls, "not_in_labor_force", period)
    low, high = breakeven.get("low"), breakeven.get("high")
    range_text = "확인 불가" if low is None or high is None else f"약 {_fmt_int(low)} ~ {_fmt_int(high)}명/월"
    interp = []
    if lf is not None and lf < 0 and nilf is not None and nilf > 0:
        interp.append("노동력 감소+비경제활동 증가이므로 낮은 실업률이 노동시장 강세가 아니라 노동공급 이탈의 착시일 수 있습니다.")
    if hh is not None and hh < 0:
        interp.append("가계취업 감소가 동반되어 냉각 신호를 강화합니다.")
    if lf is not None and lf > 0:
        interp.append("노동력 유입이 늘면 실업률 상승 일부는 신규 진입자 증가일 수 있어 자동으로 침체 신호로 보지 않습니다.")
    return (
        f"- 정의: 실업률을 대체로 안정적으로 유지하는 데 필요한 월간 고용 증가의 단순 추정치입니다. **공식 BLS 지표가 아닙니다.**\n"
        f"- 현재 추정 범위: {range_text} (최근 3개월·6개월 노동력 증가율 × 취업비중 기반). 참가율 {_fmt_pct(p)}.\n"
        f"- 해석: {' '.join(interp) if interp else '낮은 breakeven에서는 낮은 NFP도 실업률을 크게 올리지 않을 수 있으므로 절대 NFP 숫자만으로 강·약을 판정하지 않습니다.'}"
    )


def _market_section(market: dict, signals: dict) -> str:
    y = market["yahoo"]
    f = market["fred"]
    order = ["DXY", "USD/JPY", "EUR/USD", "USD/KRW", "TLT", "VIX", "S&P 500", "NASDAQ", "SOXX", "KOSPI", "KOSDAQ", "Gold", "Bitcoin", "HYG", "JNK"]
    vals = []
    for name in order:
        item = y.get(name) or {}
        vals.append(f"{name} {_fmt_pct(item.get('change_pct'), 2)}")
    rates = []
    for name in ("UST 2Y", "UST 5Y", "UST 10Y", "10Y real yield", "10Y BEI"):
        item = f.get(name) or {}
        level = "확인 불가" if item.get("value") is None else f"{item['value']:.2f}%"
        rates.append(f"{name} {level} ({_fmt_bp(item.get('change_bp'))}, {item.get('date') or '날짜 확인 불가'})")
    dxy = (y.get("DXY") or {}).get("change_pct")
    spx = (y.get("S&P 500") or {}).get("change_pct")
    vix = (y.get("VIX") or {}).get("change_pct")
    tlt = (y.get("TLT") or {}).get("change_pct")
    if signals.get("weak_hiring") and dxy is not None and dxy < 0 and tlt is not None and tlt > 0:
        judgment = "고용 냉각 + 채권강세 + 달러약세 조합이면 연준 완화 기대형 반응에 가깝습니다."
    elif signals.get("weak_hiring") and dxy is not None and dxy > 0 and ((spx is not None and spx < 0) or (vix is not None and vix > 0)):
        judgment = "고용 냉각에도 달러가 강하고 주식/VIX가 위험회피를 보이면 경기침체·안전자산 달러형 반응으로 봅니다."
    else:
        judgment = "시장 반응이 혼합되거나 일부 자산이 아직 거래 전이면 단일 방향으로 단정하지 않습니다."
    return (
        "- 발표 직후/이후 이용 가능한 Yahoo Finance 5분봉 변화: " + " | ".join(vals) + "\n"
        "- FRED 최신 공식 비교값(일별, 발표 직후값과 시차 가능): " + " | ".join(rates) + "\n"
        f"- 판정: {judgment}\n"
        "- 주의: 한국 지수는 미국 08:30 ET 발표 시점에 장이 닫혀 있을 수 있어 KOSPI/KOSDAQ 반응은 다음 한국장으로 이연될 수 있습니다."
    )


def _fed_section(signals: dict, bls: dict, period: str, latest: dict) -> str:
    ahe = _yoy_change(bls, "ahe", period)
    unemployment = _value(bls["unemployment_rate"], period)
    claims = latest.get("weekly_claims")
    continuing = claims.metrics.get("continuing_claims") if claims else None
    if signals.get("weak_hiring") and (ahe is None or ahe < 3.5):
        base = "고용과 임금이 함께 식으면 최대고용 하방 위험의 비중이 커져 완화 논리가 강화됩니다."
    elif signals.get("weak_hiring") and ahe is not None and ahe >= 3.5:
        base = "고용은 약하지만 임금이 끈적하면 연준은 고용 하방과 서비스 물가 상방을 동시에 봐야 해 빠른 완화 확신이 약해집니다."
    else:
        base = "고용이 버티고 임금도 견조하면 2% 물가 복귀 확인 전까지 완화 속도를 서두를 유인이 작습니다."
    return (
        f"- 1차 기준은 이중책무입니다: **최대고용 + 물가안정(2%)**. {base}\n"
        f"- 데이터/고용: 실업률 {_fmt_pct(unemployment)}, Continuing {_fmt_level(continuing)}건. 고용 폭·참가율·생산성까지 확인해야 합니다.\n"
        "- 커뮤니케이션: 한 달 좋은 숫자만으로 임무완수로 보지 않고 다음 고용·물가의 반복 확인이 중요합니다.\n"
        "- 대차대조표: QT/유동성은 고용지표 자체와 별개 축이므로 위험자산 반응을 보조합니다.\n"
        "- 위험자산·AI·레버리지 집중은 금융여건 보조 신호이지 고용·물가 이중책무를 대체하지 않습니다."
    )


def _hidden_headwinds(latest: dict, bls: dict, period: str, revisions: dict, breakeven: dict, adp_extra: dict) -> str:
    nfp = _change_jobs(bls, "nfp_level", period)
    private = _change_jobs(bls, "private_level", period)
    govt = _change_jobs(bls, "government_level", period)
    edu_health = _change_jobs(bls, "private_education_health_level", period)
    temp = _change_jobs(bls, "temp_help_level", period)
    hh = _change_jobs(bls, "household_employment", period)
    lf = _change_jobs(bls, "labor_force", period)
    nilf = _change_jobs(bls, "not_in_labor_force", period)
    claims = latest.get("weekly_claims")
    initial = claims.metrics.get("initial_claims") if claims else None
    continuing = claims.metrics.get("continuing_claims") if claims else None
    items = [
        f"1. **수정치 역풍**: 직전 2개월 순수정 {_fmt_int(revisions.get('net_revision'))}. 헤드라인이 좋아도 과거치가 크게 내려가면 현재 모멘텀을 과대평가할 수 있습니다.",
        f"2. **업종 집중**: NFP {_fmt_int(nfp)} 중 민간 교육·헬스 {_fmt_int(edu_health)}, 정부 {_fmt_int(govt)}. 이 둘 의존도가 높으면 민간 자생적 채용 폭은 헤드라인보다 약할 수 있습니다.",
        f"3. **근로시간/임금 상쇄**: AHE가 둔화해도 주당근로가 늘면 총 노동소득이 버틸 수 있고, 반대면 소비 둔화가 더 빨라질 수 있습니다.",
        f"4. **참가율 착시**: 노동력 {_fmt_int(lf)}, 비경제활동 {_fmt_int(nilf)}, 가계취업 {_fmt_int(hh)}. 실업률 하락이 참가율 하락과 함께면 강세로 단정하지 않습니다.",
        f"5. **낮은 breakeven 착시**: 현재 추정 하단 {_fmt_int(breakeven.get('low'))}, 상단 {_fmt_int(breakeven.get('high'))}. 노동공급 증가가 둔하면 낮은 NFP도 실업률을 안정시킬 수 있습니다.",
        f"6. **CES/CPS 괴리**: 사업체 NFP {_fmt_int(nfp)} vs 가계취업 {_fmt_int(hh)}. 방향이 다르면 표본·자영업·인구추계 차이를 확인해야 합니다.",
        f"7. **선행 고용 질**: Temp Help {_fmt_int(temp)}. 약세가 지속되면 정규 채용보다 앞선 냉각 신호일 수 있습니다.",
        f"8. **저해고·재취업 지연**: Initial {_fmt_level(initial)} vs Continuing {_fmt_level(continuing)}. Initial이 낮아도 Continuing이 높으면 문제는 해고보다 재취업 속도입니다.",
        "9. **연준 충돌 위험**: 고용 둔화가 완화 기대를 높여도 서비스 물가가 끈적하면 금리 하락이 제한될 수 있습니다.",
        "10. **안전자산 달러 실패모드**: 고용 악화가 심하면 금리는 내려도 달러가 강해지고 주식·크레딧이 약해지는 경기침체형 반응이 가능합니다.",
        "11. **ADP/BLS 차이**: ADP는 민간 급여 데이터 기반 추정, BLS는 정부 공식 표본조사라 표본·계절조정·산업구성이 달라 방향이 엇갈릴 수 있습니다.",
    ]
    size = adp_extra.get("sizes") or {}
    if size:
        small = sum(v for k, v in size.items() if k in ("1_19", "20_49") and isinstance(v, int))
        large = size.get("500_plus")
        items.append(f"12. **기업규모 양극화**: ADP 1~49명 {_fmt_int(small)} vs 500+ {_fmt_int(large)}. 총고용이 강해도 중소기업이 약하면 폭은 취약할 수 있습니다.")
    return "\n".join(items)


def _scenario_section() -> str:
    return (
        "**시나리오 A — 고용·임금 동반 둔화**\n"
        "- 연준: 완화 논리 강화 → 2Y/실질금리 하락 가능. 달러는 완화형이면 약세.\n"
        "- 자산: 장기듀레이션 성장·바이오·현금흐름이 확인된 AI/반도체에 우호적. 다만 경기민감 소비·산업은 EPS 둔화와 충돌.\n"
        "- 강화: NFP/ADP/임금/Continuing이 같은 방향으로 2회 이상 둔화. 무효화: 서비스 물가 재가속 또는 고용 급반등.\n\n"
        "**시나리오 B — 고용 약화 + 임금 강세**\n"
        "- 연준: 고용 하방과 물가 상방이 충돌해 금리인하 기대의 속도 제한. 2Y는 잘 안 내려가고 달러는 버틸 수 있음.\n"
        "- 자산: S&P/NASDAQ은 혼조, 고밸류 장기듀레이션 부담. 질 좋은 현금흐름 성장주가 상대우위. KOSDAQ/바이오는 할인율 부담에 더 민감.\n"
        "- 강화: AHE/Stayer/Changer가 끈적한데 고용 폭·Temp Help가 악화. 무효화: 임금까지 뚜렷하게 둔화.\n\n"
        "**시나리오 C — 고용 반등**\n"
        "- 연준: 인하 기대 후퇴 → 명목·실질금리 상승, 달러 강세 가능.\n"
        "- 자산: 경기민감 매출 기대는 좋아지지만 할인율 상승이 NASDAQ·바이오·고PER 성장에 부담. 한국 반도체는 수요 개선과 원화 약세가 완충 가능.\n"
        "- 강화: 민간·제조·건설·전문서비스까지 고르게 반등하고 참가율도 유지. 무효화: 정부/헬스 집중 또는 큰 하향수정.\n\n"
        "**시나리오 D — 약한 NFP + 참가율 하락**\n"
        "- 연준: 실업률 하락만 보면 안 됩니다. 노동공급 이탈이면 실질 고용 냉각으로 해석.\n"
        "- 자산: 초기에는 금리하락이 성장주를 돕더라도 소비·EPS 우려가 커지면 경기침체형 주가 약세로 전환 가능.\n"
        "- 강화: 노동력 감소+비경제활동 증가+가계취업 감소. 무효화: 참가율 반등과 가계취업 회복."
    )


def _four_axis(regime: str, signals: dict, market: dict, next_dates: dict) -> str:
    y = market["yahoo"]
    spx = (y.get("S&P 500") or {}).get("change_pct")
    nasdaq = (y.get("NASDAQ") or {}).get("change_pct")
    usdkrw = (y.get("USD/KRW") or {}).get("change_pct")
    earning_class = "부담" if signals.get("weak_hiring") else "중립~우호적"
    discount_class = "우호적 가능" if signals.get("weak_hiring") and not signals.get("wage_sticky") else "중립~부담"
    supply_class = "중립"
    if spx is not None and nasdaq is not None and spx > 0 and nasdaq > 0:
        supply_class = "우호적"
    elif spx is not None and nasdaq is not None and spx < 0 and nasdaq < 0:
        supply_class = "부담"
    timing = " / ".join(f"{k} {v}" for k, v in next_dates.items())
    return (
        "### 더 강한 종합 해석\n"
        f"현재 노동시장 국면은 **{regime}**로 판단합니다. 발표 직후에는 할인율 채널과 EPS 채널이 반대로 움직일 수 있으므로 둘을 분리해서 봅니다.\n\n"
        "투자 관점의 4축으로 보면:\n"
        f"- 돈 버는 능력: **{earning_class}** — 채용 둔화 → 노동소득/소비 증가율 둔화 → 경기민감 소비·산업의 매출·마진·EPS 부담. 반면 방어주와 수주/현금흐름이 이미 확인된 AI·반도체는 상대적으로 방어적일 수 있습니다. 즉시 영향보다 1~3개월 누적 고용·소비 데이터가 중요합니다.\n"
        f"- 할인율: **{discount_class}** — 고용 냉각이 임금·물가 둔화와 결합하면 연준 완화 기대 → 2Y·실질금리 하락 → NASDAQ·바이오·KOSDAQ 같은 장기듀레이션에 우호적입니다. 임금이 끈적하면 이 경로는 약해집니다.\n"
        f"- 수급: **{supply_class}** — 발표 직후 S&P { _fmt_pct(spx, 2) }, NASDAQ { _fmt_pct(nasdaq, 2) }, USD/KRW { _fmt_pct(usdkrw, 2) }. 금리하락+달러약세+성장주 상승이면 완화형, 달러강세+VIX상승+주식하락이면 침체형 수급으로 구분합니다.\n"
        f"- 시간표: **중립** — {timing}. 다음 공식 데이터에서 같은 방향이 반복되면 판단을 강화하고, 고용 폭·참가율·임금이 반대로 돌아서면 현재 결론을 무효화합니다."
    )


def _one_line(latest: dict, bls: dict, period: str, breakeven: dict, market: dict, regime: str) -> str:
    adp = latest.get("adp")
    claims = latest.get("weekly_claims")
    y = market["yahoo"]
    return (
        f"{regime} | NFP {_fmt_int(_change_jobs(bls, 'nfp_level', period))} | ADP {_fmt_int(adp.metrics.get('private_payroll_change') if adp else None)} | "
        f"실업률 {_fmt_pct(_value(bls['unemployment_rate'], period))} | 참가율 {_fmt_pct(_value(bls['participation_rate'], period))} | breakeven {_fmt_int(breakeven.get('low'))}~{_fmt_int(breakeven.get('high'))} | "
        f"EPOP {_fmt_pct(_value(bls['epop'], period))} | AHE {_fmt_pct(_yoy_change(bls, 'ahe', period))} | ADP Stayer/Changer {_fmt_pct(adp.metrics.get('job_stayer_pay') if adp else None)}/{_fmt_pct(adp.metrics.get('job_changer_pay') if adp else None)} | "
        f"Initial/Continuing {_fmt_level(claims.metrics.get('initial_claims') if claims else None)}/{_fmt_level(claims.metrics.get('continuing_claims') if claims else None)} | "
        f"DXY {_fmt_pct((y.get('DXY') or {}).get('change_pct'), 2)} | S&P {_fmt_pct((y.get('S&P 500') or {}).get('change_pct'), 2)} | NASDAQ {_fmt_pct((y.get('NASDAQ') or {}).get('change_pct'), 2)} | SOXX {_fmt_pct((y.get('SOXX') or {}).get('change_pct'), 2)} | USD/KRW {_fmt_pct((y.get('USD/KRW') or {}).get('change_pct'), 2)}"
    )


def _validate_trigger_core(new_releases: list[watch.Release], bls: dict, adp_extra: dict, claims_extra: dict):
    for r in new_releases:
        if r.kind == "employment_situation":
            required = [
                r.metrics.get("nfp"), r.metrics.get("unemployment_rate"), r.metrics.get("participation_rate"), r.metrics.get("epop"),
                _change_jobs(bls, "private_level", r.period), _change_jobs(bls, "government_level", r.period),
                _change_jobs(bls, "manufacturing_level", r.period), _change_jobs(bls, "construction_level", r.period),
                _change_jobs(bls, "professional_business_level", r.period), _change_jobs(bls, "temp_help_level", r.period),
                _pct_change(bls, "ahe", r.period), _yoy_change(bls, "ahe", r.period),
                _value(bls["workweek"], r.period), _value(bls["manufacturing_overtime"], r.period),
            ]
            if any(v is None for v in required):
                raise RuntimeError("Employment Situation core/official-table fields incomplete; suppress Telegram report")
        elif r.kind == "weekly_claims":
            required = [r.metrics.get("initial_claims"), r.metrics.get("previous_revised"), r.metrics.get("four_week_average"), r.metrics.get("continuing_claims"), r.metrics.get("insured_unemployment_rate")]
            if any(v is None for v in required):
                raise RuntimeError("Weekly Claims core fields incomplete; suppress Telegram report")
        elif r.kind == "adp":
            required = [r.metrics.get("private_payroll_change"), r.metrics.get("goods"), r.metrics.get("services"), r.metrics.get("job_stayer_pay"), r.metrics.get("job_changer_pay")]
            if any(v is None for v in required):
                raise RuntimeError("ADP monthly core fields incomplete; suppress Telegram report")
            sizes = adp_extra.get("sizes") or {}
            industries = adp_extra.get("industries") or {}
            if not any(v is not None for v in sizes.values()) or not any(v is not None for v in industries.values()):
                raise RuntimeError("ADP official industry/establishment-size table incomplete; suppress Telegram report")


def build_report(new_releases: list[watch.Release]) -> str:
    now_kst = datetime.now(KST)
    now_et = datetime.now(ET)
    latest = _latest_release_set(new_releases)
    bls = _query_bls_snapshot()
    period = _latest_period(bls)
    previous_state = _load_full_state()
    revisions = _revision_block(bls, period, previous_state)
    breakeven = _breakeven_proxy(bls, period)
    adp_extra = _enrich_adp(latest.get("adp"))
    claims_extra = _enrich_claims(latest.get("weekly_claims"))
    _validate_trigger_core(new_releases, bls, adp_extra, claims_extra)

    trigger_dt = min(r.release_dt_et for r in new_releases)
    market = _market_snapshot(trigger_dt)
    regime, signals = _regime(latest, bls, period)

    nb = _next_bls(now_et)
    na = _next_adp(now_et)
    nc = _next_claims(now_et)
    next_dates = {
        "BLS": nb.strftime("%Y-%m-%d 08:30 ET") if nb else "공식 일정 추가 확인 필요",
        "Claims": nc.strftime("%Y-%m-%d 08:30 ET") + "(정기 목요일, 공휴일 변동 가능)",
        "ADP": na.strftime("%Y-%m-%d 08:15 ET") if na else "공식 ADP 캘린더 추가 확인 필요",
    }

    pending_state = dict(previous_state)
    pending_state["bls_nfp_levels"] = revisions["levels_now"]
    pending_state["last_report_generated_kst"] = now_kst.isoformat(timespec="seconds")
    pending_state["last_bls_period"] = period
    FULL_PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    FULL_PENDING_PATH.write_text(json.dumps(pending_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    adp_only = len(new_releases) == 1 and new_releases[0].kind == "adp"
    parts = [
        "# Jobs Wage Watch",
        f"조회 시각: {now_kst.strftime('%Y-%m-%d %H:%M:%S KST')}",
        "자료 원칙: 새 공식 발표만 트리거. 비교값은 '최신 공식 비교값'일 뿐 별도 트리거가 아닙니다.",
        "",
        "## 1) 조회 시각·자료 처리 상태",
        f"- 새 공식 발표 {len(new_releases)}건 | 중복키 재발송 금지 | BLS Public Data API·DOL 공식 PDF·ADP 공식 원문 기반",
        "",
        f"## 2) {'오늘 ADP 고용·임금 결과 요약' if adp_only else '오늘 발표 결과 요약'}",
        f"- 노동시장 국면: **{regime}**",
        _new_release_summary(new_releases, adp_extra, claims_extra),
        "",
        "## 3) 1단계 현재 숫자 추적",
        _current_number_tracking(latest, bls, period, revisions, adp_extra),
        "",
        "## 4) 2단계 미래 재평가 요인 발굴",
        _future_revaluation(regime, signals, bls, period, adp_extra),
        "",
        "## 5) breakeven 고용·경제활동참가율 해석",
        _breakeven_section(breakeven, bls, period),
        "",
        "## 6) 달러 안전자산·경기침체 공포 점검",
        _market_section(market, signals),
        "",
        "## 7) 연준 반응함수 보조 프레임",
        _fed_section(signals, bls, period, latest),
        "",
        "## 8) 숨은 역풍·실패모드",
        _hidden_headwinds(latest, bls, period, revisions, breakeven, adp_extra),
        "",
        "## 다음 공식 발표별 시나리오",
        _scenario_section(),
        "",
        "## 9) 결론",
        _four_axis(regime, signals, market, next_dates),
        "",
        "## 10) 핵심 한 줄 요약",
        _one_line(latest, bls, period, breakeven, market, regime),
        "",
        "상태: 원천 재조회·중복 확인·수치 재검증 완료.",
    ]
    return "\n".join(parts).strip() + "\n"

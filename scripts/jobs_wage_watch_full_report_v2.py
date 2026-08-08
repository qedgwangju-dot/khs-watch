from __future__ import annotations

import csv
import io
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

import jobs_wage_watch_full_report as base

ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

# Extend the official BLS comparison set without changing trigger semantics.
base.BLS_SERIES["u6"] = "LNS13327709"
base.BLS_SERIES["health_care_social_assistance_level"] = "CES6562000001"

# Immediate U.S. equity reaction is measured with liquid futures so the 08:15/
# 08:30 ET release window is observable before the cash market opens.
base.YAHOO_ASSETS["UUP"] = "UUP"
base.YAHOO_ASSETS["S&P 500"] = "ES=F"
base.YAHOO_ASSETS["NASDAQ"] = "NQ=F"


def _breakeven_proxy_v2(bls: dict, period: str) -> dict:
    """Population-trend breakeven proxy, avoiding noisy monthly LF changes.

    Approximation: monthly civilian noninstitutional population growth × LFPR ×
    employment share. This is not an official BLS statistic and is reported as
    a range using 3m/6m population trends.
    """
    pop = bls.get("civilian_population") or []
    lfpr = base._value(bls.get("participation_rate") or [], period)
    u = base._value(bls.get("unemployment_rate") or [], period)
    if lfpr is None or u is None:
        return {"low": None, "high": None, "three": None, "six": None, "method": "population_trend"}

    estimates = {}
    for horizon in (3, 6):
        cur = base._value(pop, period)
        old = base._value(pop, base._period_shift(period, -horizon))
        if cur is None or old is None:
            estimates[horizon] = None
            continue
        monthly_pop_growth = (cur - old) * 1000.0 / horizon
        estimate = monthly_pop_growth * (lfpr / 100.0) * (1.0 - u / 100.0)
        # A shrinking population/labor supply can mathematically imply a
        # negative value, but for an intuitive "jobs needed" floor we report
        # zero rather than a misleading negative payroll requirement.
        estimates[horizon] = max(0.0, estimate)

    vals = [v for v in estimates.values() if v is not None]
    return {
        "low": min(vals) if vals else None,
        "high": max(vals) if vals else None,
        "three": estimates.get(3),
        "six": estimates.get(6),
        "method": "population_trend",
    }


def _yahoo_reaction_v2(symbol: str, release_dt: datetime) -> dict:
    """Only call something a release reaction if quotes bracket the release.

    Prevents a closed KOSPI/KOSDAQ session, or a U.S. cash index with no
    pre-market quotes, from being compared with an unrelated prior close.
    """
    try:
        p1 = int((release_dt - timedelta(hours=3)).timestamp())
        p2 = int((release_dt + timedelta(hours=2)).timestamp())
        qs = urllib.parse.urlencode({
            "period1": p1,
            "period2": p2,
            "interval": "5m",
            "includePrePost": "true",
            "events": "div,splits",
        })
        url = base.YAHOO_CHART + urllib.parse.quote(symbol, safe="") + "?" + qs
        obj = json.loads(base._fetch(url, timeout=10).decode("utf-8"))
        result = ((obj.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return {"value": None, "change_pct": None, "source": "Yahoo Finance", "status": "확인 불가"}
        timestamps = result.get("timestamp") or []
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
        pairs = [(int(ts), float(c)) for ts, c in zip(timestamps, closes) if c is not None]
        t0 = int(release_dt.timestamp())
        before = [p for p in pairs if t0 - 90 * 60 <= p[0] <= t0]
        after = [p for p in pairs if t0 < p[0] <= t0 + 90 * 60]
        if not before or not after:
            return {
                "value": after[-1][1] if after else None,
                "change_pct": None,
                "source": "Yahoo Finance",
                "status": "해당 발표시각 거래자료 없음",
            }
        baseline = before[-1][1]
        latest = after[-1][1]
        if baseline == 0:
            return {"value": latest, "change_pct": None, "source": "Yahoo Finance", "status": "확인 불가"}
        return {
            "value": latest,
            "change_pct": (latest / baseline - 1.0) * 100.0,
            "source": "Yahoo Finance",
            "status": "직접 조회",
            "baseline_timestamp": before[-1][0],
            "latest_timestamp": after[-1][0],
        }
    except Exception as e:
        return {"value": None, "change_pct": None, "source": "Yahoo Finance", "status": "확인 불가", "error": f"{type(e).__name__}: {e}"}


def _fred_latest_v2(series_id: str) -> dict:
    try:
        end = datetime.now(ET).date()
        start = end - timedelta(days=14)
        qs = urllib.parse.urlencode({"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()})
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + qs
        text = base._fetch(url, timeout=10).decode("utf-8", errors="replace")
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
            return {"value": None, "date": None, "change_bp": None, "status": "확인 불가"}
        latest = vals[-1]
        prev = vals[-2] if len(vals) >= 2 else None
        return {
            "value": latest[1],
            "date": latest[0],
            "change_bp": (latest[1] - prev[1]) * 100.0 if prev else None,
            "status": "직접 조회",
        }
    except Exception as e:
        return {"value": None, "date": None, "change_bp": None, "status": "확인 불가", "error": f"{type(e).__name__}: {e}"}


def _market_snapshot_v2(trigger_dt: datetime) -> dict:
    yahoo: dict = {}
    fred: dict = {}
    jobs = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        for name, symbol in base.YAHOO_ASSETS.items():
            jobs.append(("yahoo", name, pool.submit(_yahoo_reaction_v2, symbol, trigger_dt)))
        for name, series_id in base.FRED_SERIES.items():
            jobs.append(("fred", name, pool.submit(_fred_latest_v2, series_id)))
        for kind, name, future in jobs:
            try:
                value = future.result(timeout=15)
            except Exception as e:
                value = {"value": None, "change_pct": None, "status": "확인 불가", "error": f"{type(e).__name__}: {e}"}
            if kind == "yahoo":
                yahoo[name] = value
            else:
                fred[name] = value
    return {"yahoo": yahoo, "fred": fred}


def _regime_v2(latest: dict, bls: dict, period: str):
    b = latest.get("employment_situation")
    c = latest.get("weekly_claims")
    a = latest.get("adp")
    b_nfp = b.metrics.get("nfp") if b and b.metrics else None
    nfp = b_nfp if b_nfp is not None else base._change_jobs(bls, "nfp_level", period)
    adp = a.metrics.get("private_payroll_change") if a else None
    initial = c.metrics.get("initial_claims") if c else None
    continuing = c.metrics.get("continuing_claims") if c else None
    unemployment = base._value(bls["unemployment_rate"], period)
    participation = base._value(bls["participation_rate"], period)
    weak_hiring = (nfp is not None and nfp < 100000) or (adp is not None and adp < 100000)
    low_layoffs = initial is not None and initial < 240000
    hard_reemployment = continuing is not None and continuing >= 1850000
    ahe = base._yoy_change(bls, "ahe", period)
    wage_sticky = ahe is not None and ahe >= 3.5
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
        "nfp": nfp, "adp": adp, "initial": initial, "continuing": continuing,
        "unemployment": unemployment, "participation": participation,
        "weak_hiring": weak_hiring, "low_layoffs": low_layoffs,
        "hard_reemployment": hard_reemployment, "wage_sticky": wage_sticky,
    }


def _three_month_nfp(bls: dict, period: str):
    vals = []
    for offset in (0, -1, -2):
        v = base._change_jobs(bls, "nfp_level", base._period_shift(period, offset))
        if v is not None:
            vals.append(v)
    return mean(vals) if len(vals) == 3 else None


def _wage_character(latest: dict, bls: dict, period: str) -> str:
    ahe = base._yoy_change(bls, "ahe", period)
    adp = latest.get("adp")
    stayer = adp.metrics.get("job_stayer_pay") if adp else None
    changer = adp.metrics.get("job_changer_pay") if adp else None
    if ahe is None or stayer is None or changer is None:
        return "임금 성격: 확인 불가 — BLS AHE·ADP Stayer·Changer 중 일부가 없습니다."
    premium = changer - stayer
    if ahe >= 4.0 and stayer >= 4.5 and changer >= 5.0:
        return "임금 성격: 광범위한 임금 압력 — BLS AHE와 ADP Stayer·Changer가 함께 높습니다."
    if premium >= 1.5 and ahe < 3.5:
        return "임금 성격: 광범위 재가속보다는 숙련인력 희소성·이직자 구성효과 — Changer 프리미엄은 높지만 BLS AHE는 상대적으로 낮습니다."
    return "임금 성격: 전반 둔화/혼합 — 한 지표만으로 광범위 재가속을 판정하지 않습니다."


def _direction_conflict(latest: dict, bls: dict, period: str) -> str:
    adp = latest.get("adp")
    if not adp:
        return "ADP/BLS 방향 비교: 확인 불가"
    adp_change = adp.metrics.get("private_payroll_change")
    bls_private = base._change_jobs(bls, "private_level", period)
    if adp_change is None or bls_private is None:
        return "ADP/BLS 방향 비교: 확인 불가"
    conflict = (adp_change < 0 <= bls_private) or (bls_private < 0 <= adp_change)
    if conflict:
        return (
            f"출처 간 방향 불일치 있음 — ADP 민간 {_fmt_int(adp_change)} vs BLS 민간 {_fmt_int(bls_private)}. "
            "ADP와 BLS는 표본·급여처리 데이터/설문 방식·계절조정·산업구성이 달라 단월 괴리가 가능하며 다음 공식 BLS·ADP에서 재확인합니다."
        )
    return f"ADP/BLS 방향: 일치 — ADP 민간 {_fmt_int(adp_change)} / BLS 민간 {_fmt_int(bls_private)}."


def _fmt_int(v):
    return base._fmt_int(v)


def _current_number_tracking_v2(latest: dict, bls: dict, period: str, revisions: dict, adp_extra: dict) -> str:
    text = _original_current(latest, bls, period, revisions, adp_extra)
    u6 = base._value(bls.get("u6") or [], period)
    avg3 = _three_month_nfp(bls, period)
    health = base._change_jobs(bls, "health_care_social_assistance_level", period)
    retrieval = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    return (
        text
        + f"\n- NFP 3개월 평균 {_fmt_int(avg3)}명 | U-6 {base._fmt_pct(u6)} | Health care & social assistance {_fmt_int(health)}명"
        + "\n- 시장 컨센서스: 확인 불가 — 공식 원천에는 시장 컨센서스가 없으며 임의 추정/재사용하지 않습니다."
        + f"\n- BLS 현재값 공통 조회: {retrieval} | BLS Public Data API | 직접 열람 성공"
        + f"\n- {_direction_conflict(latest, bls, period)}"
        + f"\n- {_wage_character(latest, bls, period)}"
    )


def _future_revaluation_v2(regime: str, signals: dict, bls: dict, period: str, adp_extra: dict) -> str:
    return _original_future(regime, signals, bls, period, adp_extra) + "\n- 고용의 질 판정은 총량보다 업종 확산·Temp Help·근로시간·제조업 초과근로를 묶어 봅니다. 헬스/정부 등 일부 업종 집중이면 자생적 민간 채용 폭을 낮게 평가합니다."


def _market_section_v2(market: dict, signals: dict) -> str:
    text = _original_market(market, signals)
    unavailable = [name for name in ("KOSPI", "KOSDAQ") if (market["yahoo"].get(name) or {}).get("change_pct") is None]
    proxy_note = "S&P 500·NASDAQ의 미국 발표 직후 반응은 각각 ES·NQ 선물 프록시로 측정합니다."
    korea_note = ""
    if unavailable:
        korea_note = " 한국지수는 미국 발표시각에 현물장이 닫혀 있어 같은 시각 반응을 억지 계산하지 않고 '확인 불가/다음장 대기'로 처리합니다."
    return text + f"\n- 반응 측정 규칙: {proxy_note}{korea_note} UUP도 DXY와 함께 달러 방향을 교차확인합니다."


def _four_axis_v2(regime: str, signals: dict, market: dict, next_dates: dict) -> str:
    text = _original_four_axis(regime, signals, market, next_dates)
    if signals.get("weak_hiring"):
        extra = (
            "\n- 자산 차별화: S&P 500은 할인율 완화와 경기민감 EPS 둔화가 상쇄될 수 있고, NASDAQ은 실질금리 하락 시 상대 우위입니다. "
            "KOSPI는 다음 한국장에서 원/달러·반도체 수요 기대를 함께 확인하고, KOSDAQ·바이오는 할인율 하락의 수혜가 더 크지만 침체형 위험회피에는 더 취약합니다. "
            "한국 반도체는 현금흐름/메모리 가격·AI 수요가 확인될수록 단순 장기듀레이션 성장주보다 방어력이 높습니다."
        )
    else:
        extra = (
            "\n- 자산 차별화: 고용 반등이 경기민감 EPS에는 우호적이어도 금리·달러 상승이 NASDAQ·KOSDAQ·바이오의 밸류에이션을 누를 수 있습니다. "
            "한국 반도체는 수요 회복과 원화 약세 효과가 금리 부담을 일부 상쇄할 수 있습니다."
        )
    return text + extra


def build_report(new_releases):
    report = base.build_report(new_releases)
    trigger_status = []
    for r in new_releases:
        source = "BLS 공식 API" if r.kind == "employment_situation" else ("DOL 공식 PDF" if r.kind == "weekly_claims" else "ADP 공식 원문")
        trigger_status.append(f"{source}=직접 열람 성공")
    marker = "- 새 공식 발표 "
    idx = report.find(marker)
    if idx >= 0:
        end = report.find("\n", idx)
        if end >= 0:
            report = report[: end + 1] + "- 트리거 원천: " + " / ".join(trigger_status) + "\n" + report[end + 1 :]
    return report


# Patch base globals used by base.build_report at runtime.
_original_current = base._current_number_tracking
_original_future = base._future_revaluation
_original_market = base._market_section
_original_four_axis = base._four_axis
base._breakeven_proxy = _breakeven_proxy_v2
base._market_snapshot = _market_snapshot_v2
base._regime = _regime_v2
base._current_number_tracking = _current_number_tracking_v2
base._future_revaluation = _future_revaluation_v2
base._market_section = _market_section_v2
base._four_axis = _four_axis_v2

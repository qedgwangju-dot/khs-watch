from __future__ import annotations

import csv
import io
import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import jobs_wage_watch_full_report as base
import jobs_wage_watch_full_report_v2 as v2
import jobs_wage_watch_full_report_v3 as v3

ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

# Immediate rate-market proxies that actually trade around 08:15/08:30 ET.
# ^FVX/^TNX are yield indices; ZT=F is a 2Y note futures PRICE proxy, so its
# sign is inverse to the direction of the underlying short Treasury yield.
RATE_MARKET_ASSETS = {
    "2Y Treasury futures": "ZT=F",
    "5Y yield": "^FVX",
    "10Y yield": "^TNX",
}

_LAST_MARKET: dict | None = None


def _fred_latest_robust(series_id: str) -> dict:
    """Bounded FRED CSV query with retries.

    The unbounded graph endpoint intermittently returned an empty result in the
    full parallel report even though the bounded endpoint is reachable from the
    same GitHub runner. Keep FRED sequential and bound the requested dates.
    """
    end = datetime.now(ET).date()
    start = end - timedelta(days=21)
    qs = urllib.parse.urlencode({"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()})
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + qs
    last_error = None
    for _ in range(3):
        try:
            text = base._fetch(url, timeout=15).decode("utf-8", errors="replace")
            rows = list(csv.reader(io.StringIO(text)))
            values = []
            for row in rows[1:]:
                if len(row) < 2 or row[1] in ("", "."):
                    continue
                try:
                    values.append((row[0], float(row[1])))
                except Exception:
                    continue
            if not values:
                raise RuntimeError("FRED CSV contained no numeric observations")
            latest = values[-1]
            prev = values[-2] if len(values) >= 2 else None
            return {
                "value": latest[1],
                "date": latest[0],
                "change_bp": (latest[1] - prev[1]) * 100.0 if prev else None,
                "status": "직접 조회",
                "source": "FRED",
            }
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
    return {
        "value": None,
        "date": None,
        "change_bp": None,
        "status": "확인 불가",
        "source": "FRED",
        "error": last_error,
    }


def _market_snapshot_v4(trigger_dt: datetime) -> dict:
    global _LAST_MARKET

    yahoo_assets = dict(base.YAHOO_ASSETS)
    yahoo_assets.update(RATE_MARKET_ASSETS)
    yahoo = {}

    # Yahoo endpoints can be parallelized. FRED is intentionally sequential to
    # avoid the intermittent empty result seen in the earlier all-parallel run.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {name: pool.submit(v2._yahoo_reaction_v2, symbol, trigger_dt) for name, symbol in yahoo_assets.items()}
        for name, future in futures.items():
            try:
                yahoo[name] = future.result(timeout=18)
            except Exception as e:
                yahoo[name] = {
                    "value": None,
                    "change_pct": None,
                    "source": "Yahoo Finance",
                    "status": "확인 불가",
                    "error": f"{type(e).__name__}: {e}",
                }

    fred = {name: _fred_latest_robust(series_id) for name, series_id in base.FRED_SERIES.items()}
    _LAST_MARKET = {"yahoo": yahoo, "fred": fred}
    return _LAST_MARKET


def _fmt_market_pct(item: dict | None) -> str:
    item = item or {}
    if item.get("change_pct") is None:
        status = item.get("status") or "확인 불가"
        return status
    return base._fmt_pct(item.get("change_pct"), 2)


def _market_classification(market: dict, signals: dict) -> str:
    y = market["yahoo"]
    dxy = (y.get("DXY") or {}).get("change_pct")
    uup = (y.get("UUP") or {}).get("change_pct")
    spx = (y.get("S&P 500") or {}).get("change_pct")
    nasdaq = (y.get("NASDAQ") or {}).get("change_pct")
    vix = (y.get("VIX") or {}).get("change_pct")
    hyg = (y.get("HYG") or {}).get("change_pct")
    zt = (y.get("2Y Treasury futures") or {}).get("change_pct")
    fvx = (y.get("5Y yield") or {}).get("change_pct")
    tnx = (y.get("10Y yield") or {}).get("change_pct")

    dollar_down = dxy is not None and dxy < 0 and (uup is None or uup <= 0)
    equities_up = spx is not None and nasdaq is not None and spx > 0 and nasdaq > 0
    rates_easing = (
        (zt is not None and zt > 0) or
        (fvx is not None and fvx < 0) or
        (tnx is not None and tnx < 0)
    )
    if signals.get("weak_hiring") and dollar_down and equities_up and rates_easing:
        return "연준 완화 기대형 — 고용 냉각과 함께 달러가 약해지고, 금리/채권 프록시가 완화 방향이며, 주가지수 선물이 상승합니다."

    dollar_up = dxy is not None and dxy > 0 and (uup is None or uup >= 0)
    equities_down = spx is not None and nasdaq is not None and spx < 0 and nasdaq < 0
    risk_off = vix is not None and vix > 0 and (hyg is None or hyg < 0)
    if signals.get("weak_hiring") and dollar_up and equities_down and risk_off:
        return "경기침체·안전자산 달러형 — 고용 냉각에도 달러가 강하고 주식이 동반 하락하며 VIX/크레딧이 위험회피를 확인합니다."

    return "혼합 반응 — 달러·금리·주식·VIX가 한 방향으로 정렬되지 않아 완화형/침체형 중 하나로 단정하지 않습니다."


def _market_section_v4(market: dict, signals: dict) -> str:
    y = market["yahoo"]
    f = market["fred"]

    regular_order = [
        "DXY", "UUP", "USD/JPY", "EUR/USD", "USD/KRW", "TLT", "VIX",
        "S&P 500", "NASDAQ", "SOXX", "KOSPI", "KOSDAQ", "Gold", "Bitcoin", "HYG", "JNK",
    ]
    regular = " | ".join(f"{name} {_fmt_market_pct(y.get(name))}" for name in regular_order)

    immediate_rates = (
        f"2Y Treasury futures(가격·금리와 반대) {_fmt_market_pct(y.get('2Y Treasury futures'))} | "
        f"5Y yield {_fmt_market_pct(y.get('5Y yield'))} | "
        f"10Y yield {_fmt_market_pct(y.get('10Y yield'))}"
    )

    rates = []
    for name in ("UST 2Y", "UST 5Y", "UST 10Y", "10Y real yield", "10Y BEI"):
        item = f.get(name) or {}
        level = "확인 불가" if item.get("value") is None else f"{item['value']:.2f}%"
        rates.append(
            f"{name} {level} ({base._fmt_bp(item.get('change_bp'))}, {item.get('date') or '날짜 확인 불가'}, {item.get('status') or '확인 불가'})"
        )

    return (
        "- 발표 직후 Yahoo Finance 5분봉: " + regular + "\n"
        "- 금리 즉시 프록시: " + immediate_rates + "\n"
        "- FRED 최신 일별 공식 비교값(발표 직후값 아님·시차 가능): " + " | ".join(rates) + "\n"
        f"- 판정: {_market_classification(market, signals)}\n"
        "- 측정 규칙: S&P 500·NASDAQ은 미국 08:15/08:30 ET 발표 직후 ES·NQ 선물로 측정합니다. 2Y는 현물 수익률 5분봉이 없어 ZT 선물가격을 보조 프록시로 쓰며, 가격 상승은 대체로 2Y 금리 하락 방향입니다.\n"
        "- 한국 지수는 미국 발표시각에 현물장이 닫혀 있으면 과거 장 변동률을 끌어오지 않고 '해당 발표시각 거래자료 없음'으로 처리해 다음 한국장으로 이연합니다."
    )


def _breakeven_section_v4(breakeven: dict, bls: dict, period: str) -> str:
    p = base._value(bls["participation_rate"], period)
    hh = base._change_jobs(bls, "household_employment", period)
    lf = base._change_jobs(bls, "labor_force", period)
    nilf = base._change_jobs(bls, "not_in_labor_force", period)
    low, high = breakeven.get("low"), breakeven.get("high")
    range_text = "확인 불가" if low is None or high is None else f"약 {base._fmt_int(low)} ~ {base._fmt_int(high)}명/월"
    interp = []
    if lf is not None and lf < 0 and nilf is not None and nilf > 0:
        interp.append("노동력 감소+비경제활동 증가이므로 낮은 실업률이 노동시장 강세가 아니라 노동공급 이탈의 착시일 수 있습니다.")
    if hh is not None and hh < 0:
        interp.append("가계취업 감소가 동반되어 냉각 신호를 강화합니다.")
    if lf is not None and lf > 0:
        interp.append("노동력 유입이 늘면 실업률 상승 일부는 신규 진입자 증가일 수 있어 자동으로 침체 신호로 보지 않습니다.")
    return (
        "- 정의: 실업률을 대체로 안정적으로 유지하는 데 필요한 월간 고용 증가의 단순 추정치입니다. **공식 BLS 지표가 아닙니다.**\n"
        f"- 현재 추정 범위: {range_text} (CPS 노동력+비경제활동으로 재구성한 민간 비제도권 인구의 3·6개월 추세 × 참가율 × 취업비중 기반). 참가율 {base._fmt_pct(p)}.\n"
        f"- 해석: {' '.join(interp) if interp else '낮은 breakeven에서는 낮은 NFP도 실업률을 크게 올리지 않을 수 있으므로 절대 NFP 숫자만으로 강·약을 판정하지 않습니다.'}"
    )


def _report_status() -> str:
    market = _LAST_MARKET or {}
    fred = market.get("fred") or {}
    missing_rates = [name for name in ("UST 2Y", "UST 5Y", "UST 10Y", "10Y real yield", "10Y BEI") if (fred.get(name) or {}).get("value") is None]
    if missing_rates:
        return "상태: 부분완료 — FRED 금리 비교값 확인 불가: " + ", ".join(missing_rates) + "."
    return "상태: 원천 재조회·중복 확인·수치 재검증 완료."


# Patch the base module used by v3/v2 report builders.
base._market_snapshot = _market_snapshot_v4
base._market_section = _market_section_v4
base._breakeven_section = _breakeven_section_v4


def build_report(new_releases):
    report = v3.build_report(new_releases)
    old = "상태: 원천 재조회·중복 확인·수치 재검증 완료."
    status = _report_status()
    if old in report:
        report = report.replace(old, status)
    elif "상태:" not in report:
        report = report.rstrip() + "\n\n" + status + "\n"
    return report

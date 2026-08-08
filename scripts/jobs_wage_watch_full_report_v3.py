from __future__ import annotations

from statistics import mean

import jobs_wage_watch_full_report as base
import jobs_wage_watch_full_report_v2 as v2

# Verified against the official BLS Public Data API on 2026-08-08.
base.BLS_SERIES["health_care_social_assistance_level"] = "CES6562000101"  # Health care
base.BLS_SERIES["diffusion_private_1m"] = "CES0500000021"
base.BLS_SERIES["diffusion_manufacturing_1m"] = "CES3000000021"


def _breakeven_proxy_v3(bls: dict, period: str) -> dict:
    """Breakeven payroll proxy from CPS population trend.

    BLS API does not expose LNS10000000 here. Civilian noninstitutional
    population is reconstructed exactly from civilian labor force + not in
    labor force for each month, then a 3m/6m population-growth trend is
    multiplied by current LFPR and employment share. This avoids using a
    volatile one-month labor-force change as the required payroll pace.
    """
    lfpr = base._value(bls.get("participation_rate") or [], period)
    u = base._value(bls.get("unemployment_rate") or [], period)
    if lfpr is None or u is None:
        return {"low": None, "high": None, "three": None, "six": None, "method": "cps_population_trend"}

    def population(p: str):
        lf = base._value(bls.get("labor_force") or [], p)
        nilf = base._value(bls.get("not_in_labor_force") or [], p)
        if lf is None or nilf is None:
            return None
        return lf + nilf  # both are thousands of persons

    estimates = {}
    for horizon in (3, 6):
        cur = population(period)
        old = population(base._period_shift(period, -horizon))
        if cur is None or old is None:
            estimates[horizon] = None
            continue
        monthly_population_growth = (cur - old) * 1000.0 / horizon
        needed = monthly_population_growth * (lfpr / 100.0) * (1.0 - u / 100.0)
        estimates[horizon] = max(0.0, needed)

    vals = [v for v in estimates.values() if v is not None]
    return {
        "low": min(vals) if vals else None,
        "high": max(vals) if vals else None,
        "three": estimates.get(3),
        "six": estimates.get(6),
        "method": "cps_population_trend",
    }


_prev_current = base._current_number_tracking


def _current_number_tracking_v3(latest: dict, bls: dict, period: str, revisions: dict, adp_extra: dict) -> str:
    text = _prev_current(latest, bls, period, revisions, adp_extra)
    text = text.replace("Health care & social assistance", "Health care")
    private_diff = base._value(bls.get("diffusion_private_1m") or [], period)
    mfg_diff = base._value(bls.get("diffusion_manufacturing_1m") or [], period)
    return (
        text
        + f"\n- BLS 1개월 고용 확산지수: Total private {base._fmt_pct(private_diff)} / Manufacturing {base._fmt_pct(mfg_diff)}"
        + " — 50 초과는 증가 업종이 더 넓다는 뜻이며 고용 증가율 자체가 아닙니다."
    )


base._breakeven_proxy = _breakeven_proxy_v3
base._current_number_tracking = _current_number_tracking_v3


def build_report(new_releases):
    return v2.build_report(new_releases)

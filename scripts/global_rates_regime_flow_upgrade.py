#!/usr/bin/env python3
"""JGB regime/flow watcher entrypoint using the official current weekly PDF.

The classifier is deliberately non-exclusive: when more than one independently
supported driver is active, report a mixed regime instead of forcing one causal story.
"""
from __future__ import annotations

import global_rates_regime_flow_core as core
from global_rates_regime_flow_core import *  # re-export core helpers for tests
from global_rates_weekly_flow_pdf import fetch_weekly_outward_flows as _fetch_pdf_flows


def fetch_weekly_outward_flows():
    return _fetch_pdf_flows(core.get_bytes)


def classify_regime(prev_jgb, cur_jgb, prev_ust, cur_ust, live_fx):
    d2 = core.bp(cur_jgb["jgb2"], prev_jgb["jgb2"])
    d5 = core.bp(cur_jgb["jgb5"], prev_jgb["jgb5"])
    d10 = core.bp(cur_jgb["jgb10"], prev_jgb["jgb10"])
    d30 = core.bp(cur_jgb["jgb30"], prev_jgb["jgb30"])
    u10 = core.bp(cur_ust["ust10"], prev_ust["ust10"])
    fx_change = core.fnum(live_fx.get("live_fx_change_pct")) if live_fx else None

    policy = sum([
        bool(d2 is not None and d2 >= 5),
        bool(d5 is not None and d5 >= 5),
        bool(fx_change is not None and fx_change <= -0.50),
    ])
    fiscal = sum([
        bool(d30 is not None and d10 is not None and d30 - d10 >= 5),
        bool(d30 is not None and d30 >= 8),
        bool(fx_change is not None and fx_change >= 0.30),
    ])
    global_sync = sum([
        bool(d10 is not None and d10 >= 5),
        bool(u10 is not None and u10 >= 5),
    ])

    scores = {
        "BOJ 정상화 신호": policy,
        "재정 위험 프리미엄 신호": fiscal,
        "글로벌 금리 동조 신호": global_sync,
    }
    active = [name for name, score in scores.items() if score >= 2]
    if len(active) == 1:
        label = active[0] + " 우세"
    elif len(active) > 1:
        label = "혼재형(" + " + ".join(active) + ")"
    else:
        label = "원인 미확정·혼재"

    return {
        "label": label,
        "scores": scores,
        "jgb_date": cur_jgb["date"],
        "ust_date": cur_ust["date"],
        "jgb2": cur_jgb["jgb2"],
        "jgb5": cur_jgb["jgb5"],
        "jgb10": cur_jgb["jgb10"],
        "jgb30": cur_jgb["jgb30"],
        "d2_bp": d2,
        "d5_bp": d5,
        "d10_bp": d10,
        "d30_bp": d30,
        "ust10": cur_ust["ust10"],
        "ust10_change_bp": u10,
        "live_usdjpy": core.fnum(live_fx.get("live_fx_price")) if live_fx else None,
        "live_usdjpy_change_pct": fx_change,
        "causality_note": "일일 JGB·UST와 현재 USD/JPY의 관측시각이 다를 수 있으므로 단일 원인으로 확정하지 않고 동시 신호로 분류",
    }


def main() -> int:
    core.fetch_weekly_outward_flows = fetch_weekly_outward_flows
    core.classify_regime = classify_regime
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())

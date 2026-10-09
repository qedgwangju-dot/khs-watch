from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import treasury_cta_squeeze_equity_watch as equity  # noqa: E402
import treasury_cta_squeeze_watch as base_watch  # noqa: E402


def _snapshot(*, z20=-0.5, zn_pct=0.0):
    return {
        "cftc": {
            "markets": {
                "10Y": {
                    "leveraged_net": -1_900_000,
                    "short_share_oi_pct": 44.0,
                }
            }
        },
        "cme": {"ZN": {"pct_change": zn_pct}},
        "yield10": {"z20": z20},
        "repo": {},
    }


def _raw(
    *,
    price_pct=0.6,
    trade_date="2026-09-30",
    official=True,
    oi_change=-1_000,
    net_wow=-1_000,
    net_pct=95.0,
    gross_pct=95.0,
    report_date="September 22, 2026",
    history_end="2026-09-22",
):
    return {
        "nq_cftc": {
            "report_date": report_date,
            "open_interest": 300_000,
            "open_interest_wow": -20_000,
            "leveraged_long": 50_000,
            "leveraged_short": 90_000,
            "leveraged_net": -40_000,
            "leveraged_net_wow": net_wow,
            "leveraged_short_wow": 10_000,
            "short_share_oi_pct": 30.0,
        },
        "nq_price": {
            "price": 30_000.0,
            "pct_change": price_pct,
            "official": official,
            "trade_date": trade_date,
            "oi_change": oi_change,
            "source": "test",
        },
        "history_3y": {
            "verified_current": True,
            "sample_n": 157,
            "end_date": history_end,
            "net_short_percentile_3y": net_pct,
            "gross_short_percentile_3y": gross_pct,
        },
        "errors": [],
    }


def _patch_common(monkeypatch, raw, *, data_fresh=True, repo_ok=True, evidence=None):
    monkeypatch.setattr(equity, "_cross_raw", lambda: raw)
    monkeypatch.setattr(equity, "_latest_completed_us_session_date", lambda: date(2026, 9, 30))
    monkeypatch.setattr(
        equity.audited,
        "_repo_not_worse",
        lambda current, previous: (repo_ok, [] if repo_ok else ["SOFR"]),
    )
    monkeypatch.setattr(
        equity.audited,
        "_data_freshness",
        lambda snapshot: (data_fresh, [] if data_fresh else ["stale"]),
    )
    monkeypatch.setattr(
        equity.watcher,
        "squeeze_evidence",
        lambda current, previous: list(evidence or []),
    )


def test_low_3y_percentile_overrides_large_absolute_short(monkeypatch):
    raw = _raw(net_pct=39.5, gross_pct=57.3)
    _patch_common(monkeypatch, raw)

    result = equity._cross_asset_snapshot(_snapshot(zn_pct=0.2), {})

    assert result["nq_extreme"] is False
    assert result["nq_fuel"] is False
    assert result["stage"] == 0


def test_stale_nq_price_cannot_trigger_preparation(monkeypatch):
    raw = _raw(trade_date="2026-09-29", price_pct=1.0)
    _patch_common(monkeypatch, raw)

    result = equity._cross_asset_snapshot(_snapshot(zn_pct=0.0), {})

    assert result["nq_price_fresh"] is False
    assert result["stage"] == 0


def test_fresh_official_nq_price_can_only_prepare_without_short_cover(monkeypatch):
    raw = _raw(net_wow=-5_000)
    _patch_common(monkeypatch, raw)

    result = equity._cross_asset_snapshot(_snapshot(zn_pct=0.0), {})

    assert result["nq_price_fresh"] is True
    assert result["nq_confirmed"] is False
    assert result["stage"] == 1


def test_stage2_requires_zn_evidence_not_other_treasury_contract(monkeypatch):
    raw = _raw(net_wow=5_000)

    _patch_common(monkeypatch, raw, evidence=["ZB 공식 CME 같은 거래일 가격↑ + OI↓"])
    without_zn = equity._cross_asset_snapshot(_snapshot(z20=-1.2, zn_pct=0.3), {})
    assert without_zn["nq_confirmed"] is True
    assert without_zn["treasury_10y_evidence"] is False
    assert without_zn["stage"] == 1

    _patch_common(monkeypatch, raw, evidence=["ZN 공식 CME 같은 거래일 가격↑ + OI↓"])
    with_zn = equity._cross_asset_snapshot(_snapshot(z20=-1.2, zn_pct=0.3), {})
    assert with_zn["treasury_10y_evidence"] is True
    assert with_zn["treasury_confirmed"] is True
    assert with_zn["stage"] == 2


def test_stale_global_inputs_fail_closed(monkeypatch):
    raw = _raw(net_wow=5_000)
    _patch_common(
        monkeypatch,
        raw,
        data_fresh=False,
        evidence=["ZN 공식 CME 같은 거래일 가격↑ + OI↓"],
    )

    result = equity._cross_asset_snapshot(_snapshot(z20=-1.2, zn_pct=0.3), {})

    assert result["data_fresh"] is False
    assert result["treasury_confirmed"] is False
    assert result["stage"] == 0


def test_equity_impact_is_neutral_when_inputs_are_stale(monkeypatch):
    monkeypatch.setattr(equity.watcher, "squeeze_evidence", lambda current, previous: ["ZN evidence"])
    monkeypatch.setattr(equity.audited, "_repo_not_worse", lambda current, previous: (True, []))
    monkeypatch.setattr(equity.audited, "_data_freshness", lambda snapshot: (False, ["stale"]))
    monkeypatch.setattr(equity.audited, "_price_up_count", lambda snapshot: 3)

    impact, reason = equity._equity_impact(
        _snapshot(z20=-1.5, zn_pct=0.5),
        {},
        ["CFTC 숏 축소"],
    )

    assert impact == "⚪ 중립·금리 위험 점검"
    assert "지속적인 할인율 완화 모두 미확인" in reason


def test_cross_alert_latch_does_not_reset_on_stale_gap():
    current_state = {
        "nasdaq_cross_asset_stage": 1,
        "nasdaq_cross_asset_alerted_stage": 1,
        "nasdaq_cross_asset_format_revision": equity.CROSS_FORMAT_REVISION,
    }
    stale_gap = {
        "stage": 0,
        "treasury_fuel": True,
        "nq_fuel": True,
        "data_fresh": False,
        "nq_history_ready": True,
        "nq_history_fresh": True,
    }
    due, base, next_alerted, reset = equity._cross_alert_gate(current_state, stale_gap)
    assert due is False
    assert base == 1
    assert next_alerted == 1
    assert reset is False

    recovered_same_stage = {
        **stale_gap,
        "stage": 1,
        "data_fresh": True,
    }
    due, base, next_alerted, reset = equity._cross_alert_gate(
        {**current_state, "nasdaq_cross_asset_stage": 0},
        recovered_same_stage,
    )
    assert due is False
    assert base == 1
    assert next_alerted == 1
    assert reset is False


def test_old_format_revision_can_force_one_corrected_delivery():
    current_state = {
        "nasdaq_cross_asset_stage": 1,
        "nasdaq_cross_asset_alerted_stage": 1,
        "nasdaq_cross_asset_format_revision": equity.CROSS_FORMAT_REVISION - 1,
    }
    same_stage = {
        "stage": 1,
        "treasury_fuel": True,
        "nq_fuel": True,
        "data_fresh": True,
        "nq_history_ready": True,
        "nq_history_fresh": True,
    }

    due, base, next_alerted, reset = equity._cross_alert_gate(current_state, same_stage)

    assert due is True
    assert base == 1
    assert next_alerted == 1
    assert reset is False


def test_cross_alert_latch_resets_only_after_fresh_fuel_disappears():
    current_state = {
        "nasdaq_cross_asset_stage": 2,
        "nasdaq_cross_asset_alerted_stage": 2,
    }
    ended = {
        "stage": 0,
        "treasury_fuel": True,
        "nq_fuel": False,
        "data_fresh": True,
        "nq_history_ready": True,
        "nq_history_fresh": True,
        "nq_crosscheck_match": True,
    }
    due, base, next_alerted, reset = equity._cross_alert_gate(current_state, ended)
    assert due is False
    assert base == 0
    assert next_alerted == 0
    assert reset is True

    new_episode = {
        **ended,
        "stage": 1,
        "nq_fuel": True,
    }
    due, base, next_alerted, reset = equity._cross_alert_gate(
        {"nasdaq_cross_asset_alerted_stage": next_alerted},
        new_episode,
    )
    assert due is True
    assert base == 0
    assert next_alerted == 1
    assert reset is False


def test_tff_fixed_parser_preserves_confidential_placeholder_columns():
    fields = base_watch._tff_fields(
        "1 2 3 4 5 6 7 . 9 10 11 12 13 14"
    )
    assert len(fields) == 14
    assert fields[6] == 7
    assert fields[7] is None
    assert fields[8] == 9


def test_active_treasury_squeeze_evidence_requires_fresh_official_same_day_oi():
    current = {
        "cme": {
            "ZN": {
                "display_symbol": "TY/ZN",
                "fresh_for_confirmation": True,
                "trade_date_iso": "2026-10-06",
                "change": 0.5,
                "oi_change": -100,
            }
        }
    }
    previous = {
        "cme": {
            "ZN": {
                "trade_date_iso": "2026-10-05",
            }
        }
    }
    signals = equity.watcher.squeeze_evidence(current, previous)
    assert any("ZN" in s and "같은 거래일" in s for s in signals)

    stale = {
        "cme": {
            "ZN": {
                "display_symbol": "TY/ZN",
                "fresh_for_confirmation": False,
                "trade_date_iso": "2026-10-06",
                "change": 0.5,
                "oi_change": -100,
            }
        }
    }
    assert equity.watcher.squeeze_evidence(stale, previous) == []

    same_bulletin = {
        "cme": {
            "ZN": {
                "display_symbol": "TY/ZN",
                "fresh_for_confirmation": True,
                "trade_date_iso": "2026-10-06",
                "change": 0.5,
                "oi_change": -100,
            }
        }
    }
    assert equity.watcher.squeeze_evidence(
        same_bulletin,
        {"cme": {"ZN": {"trade_date_iso": "2026-10-06"}}},
    ) == []


def test_compact_event_body_stays_under_telegram_limit(monkeypatch):
    raw = _raw(
        net_wow=5_000,
        net_pct=95.0,
        gross_pct=95.0,
        trade_date="2026-09-30",
    )
    _patch_common(monkeypatch, raw, evidence=["TY/ZN 공식 CME 같은 거래일 가격↑ + OI↓"])
    snapshot = _snapshot(z20=-1.2, zn_pct=0.3)
    snapshot["checked_kst"] = "2026-10-01T07:00:00+09:00"
    snapshot["repo"] = {
        "SOFR": {"rate": 3.64, "date": "2026-09-30"},
        "BGCR": {"rate": 3.62, "date": "2026-09-30"},
        "TGCR": {"rate": 3.62, "date": "2026-09-30"},
    }
    snapshot["cftc"]["report_date"] = "September 29, 2026"
    snapshot["cme"]["ZB"] = {"pct_change": 0.1, "open_interest": 100}
    snapshot["cme"]["UB"] = {"pct_change": 0.1, "open_interest": 100}
    snapshot["yield10"].update({"yield": 4.8, "mean20": 4.7, "distance_to_4_3_bp": 50.0})

    body = equity._compact_event_body(
        snapshot,
        {},
        1400.0,
        "2026-09-30",
        ["테스트 사유 " * 30],
    )
    assert len("테스트 제목") + 2 + len(body) < 4096


def test_mixed_week_history_suppresses_all_stale_nq_percentiles(monkeypatch):
    raw = _raw(
        report_date="October 6, 2026",
        history_end="2026-09-29",
        price_pct=-1.38,
        trade_date="2026-10-08",
    )
    raw["history_3y"].update({
        "verified_current": False,
        "ten_year_complete": True,
        "gross_short_weekly_change_10y": -11843,
        "gross_short_weekly_build_percentile_10y": 10.0,
        "gross_short_percentile_3y": 25.0,
    })
    raw["history_status"] = "2026-10-06 실시간, 이력 2026-09-29"
    _patch_common(monkeypatch, raw)
    monkeypatch.setattr(equity, "_latest_completed_us_session_date", lambda: date(2026, 10, 9))
    snap = _snapshot(z20=0.71, zn_pct=-0.10)
    snap["cftc"]["markets"]["10Y"]["leveraged_net"] = -2139785
    cross = equity._cross_asset_snapshot(snap, {})
    assert cross["nq_crosscheck_match"] is False
    assert cross["nq_history_fresh"] is False
    assert cross["nq_price_fresh"] is False
    assert cross["stage"] == 0
    shown = equity._cross_asset_block(snap, {}, compact=True)
    assert "백분위 표시 보류" in shown
    assert "-11,843" not in shown
    assert "총숏 -11,843" not in shown
    assert "2026-10-08" in shown
    assert "예상 2026-10-09" in shown
    assert "가격·일일 OI 판정 제외" in shown


def test_cftc_latest_week_short_change_is_live_and_labelled(monkeypatch):
    raw = _raw(report_date="October 6, 2026", history_end="2026-10-06",
               price_pct=-1.38, trade_date="2026-10-08",
               net_pct=30.0, gross_pct=25.0)
    raw["nq_cftc"].update({
        "leveraged_net": -19212,
        "leveraged_net_wow": 5511,
        "leveraged_short_wow": -2312,
    })
    raw["history_3y"]["ten_year_complete"] = False
    _patch_common(monkeypatch, raw)
    monkeypatch.setattr(equity, "_latest_completed_us_session_date", lambda: date(2026, 10, 9))
    displayed = equity._cross_asset_block(_snapshot(z20=0.71), {}, compact=True)
    assert "총숏 -2,312계약" in displayed
    assert "순포지션 +5,511계약" in displayed
    assert "순숏 30 · 총숏 25" in displayed
    assert "2026-10-08" in displayed


def test_independent_cftc_history_calculation_checks_live_and_weekly_changes():
    latest = date(2026, 10, 6)
    rows = []
    for i in range(550, -1, -1):
        d = latest - timedelta(weeks=i)
        level = 80000 + (550 - i) * 2
        rows.append({
            "report_date_as_yyyy_mm_dd": d.isoformat(),
            "open_interest_all": 300000,
            "lev_money_positions_long": 50000,
            "lev_money_positions_short": level,
        })
    current = {
        "report_date": "October 6, 2026",
        "previous_period": "September 29, 2026",
        "open_interest": 300000,
        "leveraged_long": 50000,
        "leveraged_short": 81100,
        "leveraged_net": -31100,
        "leveraged_net_wow": -2,
        "leveraged_short_wow": 2,
    }
    hist = equity._nq_history_statistics(rows, current)
    assert hist["verified_current"] is True
    assert hist["end_date"] == "2026-10-06"
    assert hist["leveraged_short_1w_change"] == 2
    assert hist["gross_short_weekly_change_10y"] == 2
    assert hist["ten_year_complete"] is True


def test_independent_history_refuses_inconsistent_same_week_data():
    rows = [
        {"report_date_as_yyyy_mm_dd": "2026-09-29", "open_interest_all": 300000,
         "lev_money_positions_long": 50000, "lev_money_positions_short": 85000},
        {"report_date_as_yyyy_mm_dd": "2026-10-06", "open_interest_all": 300000,
         "lev_money_positions_long": 50000, "lev_money_positions_short": 90000},
    ]
    current = {
        "report_date": "October 6, 2026",
        "previous_period": "September 29, 2026",
        "open_interest": 300000,
        "leveraged_long": 50000,
        "leveraged_short": 90001,
        "leveraged_net": -40001,
        "leveraged_net_wow": -5001,
        "leveraged_short_wow": 5001,
    }
    with pytest.raises(RuntimeError, match="historical/live mismatch"):
        equity._nq_history_statistics(rows, current)


def test_yahoo_price_count_does_not_claim_bond_squeeze(monkeypatch):
    monkeypatch.setattr(equity.watcher, "squeeze_evidence", lambda *_: [])
    monkeypatch.setattr(equity.audited, "_repo_not_worse", lambda *_: (True, []))
    monkeypatch.setattr(equity.audited, "_data_freshness", lambda *_: (True, []))
    monkeypatch.setattr(equity.audited, "_price_up_count", lambda *_: 2)
    snap = _snapshot(z20=0.71, zn_pct=-0.10)
    snap["yield10"]["yield"] = 5.24
    verdict, _ = equity.audited._direction_label(snap, {}, ["정정"])
    assert verdict == "⚪ 숏 스퀴즈 미확인"
    impact, _ = equity._equity_impact(snap, {}, ["정정"])
    assert impact.startswith("⚪ 중립")

def test_latch_preserved_on_same_date_cftc_crosscheck_mismatch():
    current_state = {
        "nasdaq_cross_asset_stage": 1,
        "nasdaq_cross_asset_alerted_stage": 1,
        "nasdaq_cross_asset_format_revision": equity.CROSS_FORMAT_REVISION,
    }
    invalid_gap = {
        "stage": 0,
        "treasury_fuel": True,
        "nq_fuel": False,
        "data_fresh": True,
        "nq_history_ready": True,
        "nq_history_fresh": True,
        "nq_crosscheck_match": False,
    }
    due, base, alerted, reset = equity._cross_alert_gate(current_state, invalid_gap)
    assert due is False
    assert reset is False
    assert base == 1
    assert alerted == 1



from __future__ import annotations

import sys
from datetime import date
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

    assert impact == "⚪ 중립"
    assert "할인율 완화 신호 미확인" in reason


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

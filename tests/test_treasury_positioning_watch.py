from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import treasury_positioning_watch as watch  # noqa: E402


def test_select_week_reference_uses_calendar_week_not_observation_count():
    points = [
        ("2026-09-22", 100.0),
        ("2026-09-24", 110.0),
        ("2026-09-25", 120.0),
        ("2026-09-28", 130.0),
        ("2026-09-29", 140.0),
        ("2026-10-01", 150.0),
    ]
    assert watch.select_week_reference(points) == (
        "2026-10-01",
        150.0,
        "2026-09-24",
        110.0,
    )


def test_select_week_reference_fails_without_calendar_week_anchor():
    with pytest.raises(RuntimeError):
        watch.select_week_reference([
            ("2026-09-29", 140.0),
            ("2026-10-01", 150.0),
        ])


def _cftc_rows():
    return {
        label: {
            "oi": 1_000_000 + i,
            "long": 100_000 + i,
            "short": 200_000 + i,
            "net": -100_000,
            "net_change": -10_000,
        }
        for i, label in enumerate(watch.CONTRACTS, start=1)
    }


def test_cftc_crosscheck_accepts_exact_official_match():
    rows = _cftc_rows()
    html_rows = {
        label: {key: int(rows[label][key]) for key in ("oi", "long", "short")}
        for label in rows
    }
    assert watch.validate_cftc_crosscheck(
        "2026-09-29",
        rows,
        "2026-09-29",
        html_rows,
    ) is True


def test_cftc_crosscheck_fails_closed_on_mismatch():
    rows = _cftc_rows()
    html_rows = {
        label: {key: int(rows[label][key]) for key in ("oi", "long", "short")}
        for label in rows
    }
    html_rows["10년"]["short"] += 1
    with pytest.raises(RuntimeError, match="CFTC source mismatch"):
        watch.validate_cftc_crosscheck(
            "2026-09-29",
            rows,
            "2026-09-29",
            html_rows,
        )


def test_classify_three_short_expansions_and_repo_growth():
    rows = {
        "2년": {"net": -10, "net_change": +2},
        "5년": {"net": -10, "net_change": -2},
        "10년": {"net": -10, "net_change": -3},
        "30년": {"net": -10, "net_change": -4},
    }
    repo = {"state": "안정", "dvp_week_pct": 7.6}
    label, reason = watch.classify(rows, repo)
    assert label == "숏·레버리지 확대 가능성"
    assert "3개" in reason
    assert "+7.6%" in reason


def test_zb_and_ultra_bond_contracts_are_separated():
    assert watch.CONTRACTS["30년"]["code"] == "020601"
    assert watch.CONTRACTS["초장기(UB)"]["code"] == "020604"
    assert watch.CONTRACTS["30년"]["name"] == "UST BOND"
    assert watch.CONTRACTS["초장기(UB)"]["name"] == "ULTRA UST BOND"
    assert watch.CORE_CONTRACTS == ("2년", "5년", "10년", "30년")


def test_ultra_position_does_not_change_existing_core_regime_thresholds():
    rows = {
        "2년": {"net": -10, "net_change": 2},
        "5년": {"net": -10, "net_change": 2},
        "10년": {"net": -10, "net_change": -2},
        "30년": {"net": -10, "net_change": -2},
        "초장기(UB)": {"net": -10, "net_change": 400},
    }
    repo = {"state": "스트레스", "dvp_week_pct": 1.0}
    head, _ = watch.classify(rows, repo)
    assert head == "혼조·추가 확인"


def test_cftc_contract_name_anchor_blocks_ultra_substring_match():
    import re
    sample = "\nULTRA UST BOND - CHICAGO BOARD OF TRADE\nOpen Interest is 999\nUST BOND - CHICAGO BOARD OF TRADE\nOpen Interest is 123\n"
    pattern = r"(?m)^\s*" + re.escape(watch.CONTRACTS["30년"]["name"]) + r"\s*-\s*CHICAGO BOARD OF TRADE\b"
    match = re.search(pattern, sample, re.I)
    assert match is not None
    assert match.group(0).strip() == "UST BOND - CHICAGO BOARD OF TRADE"


def test_ctd_switch_requires_delivery_basket_not_cash_bond_yield():
    assert "cmegroup.com" in watch.CME_CTD_EDUCATION_URL
    assert watch.CONTRACTS["초장기(UB)"]["name"] == "ULTRA UST BOND"
    assert "6.00%" in watch.jpm_30y_signal(6.0)

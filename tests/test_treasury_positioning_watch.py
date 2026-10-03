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

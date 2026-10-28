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


def test_us_rate_holiday_skips_columbus_day_2026():
    import datetime as dt
    from zoneinfo import ZoneInfo

    assert watch.nyfed_closed(dt.date(2026, 10, 12))
    assert not watch.nyfed_closed(dt.date(2026, 10, 9))
    before = dt.datetime(2026, 10, 13, 5, 22, tzinfo=ZoneInfo("America/New_York"))
    assert watch.completed_publication_days("2026-10-08", 8, before) == 1
    assert watch.ensure_recent_funding_date(
        "SOFR/TGCR", "2026-10-08", publish_hour=8, max_lag=1, now_ny=before
    ) == 1


def test_sofr_lag_becomes_stale_after_expected_publication():
    import datetime as dt
    from zoneinfo import ZoneInfo

    after = dt.datetime(2026, 10, 13, 8, 20, tzinfo=ZoneInfo("America/New_York"))
    assert watch.completed_publication_days("2026-10-08", 8, after) == 2
    with pytest.raises(RuntimeError, match="publication lag"):
        watch.ensure_recent_funding_date(
            "SOFR/TGCR", "2026-10-08", publish_hour=8, max_lag=1, now_ny=after
        )


def test_ofr_cutoff_is_3pm_ny_and_holidays_not_calendar_days():
    import datetime as dt
    from zoneinfo import ZoneInfo

    before = dt.datetime(2026, 10, 13, 14, 40, tzinfo=ZoneInfo("America/New_York"))
    after = dt.datetime(2026, 10, 13, 15, 20, tzinfo=ZoneInfo("America/New_York"))
    assert watch.completed_publication_days("2026-10-08", 15, before) == 1
    assert watch.completed_publication_days("2026-10-08", 15, after) == 2
    assert watch.ensure_recent_funding_date(
        "OFR DVP Repo", "2026-10-08", publish_hour=15, max_lag=2, now_ny=after
    ) == 2


def test_funding_freshness_fails_for_future_date_and_real_staleness():
    import datetime as dt
    from zoneinfo import ZoneInfo

    now = dt.datetime(2026, 10, 14, 16, 0, tzinfo=ZoneInfo("America/New_York"))
    with pytest.raises(RuntimeError, match="future-dated"):
        watch.completed_publication_days("2026-10-15", 8, now)
    with pytest.raises(RuntimeError, match="publication lag"):
        watch.ensure_recent_funding_date(
            "OFR DVP Repo", "2026-10-08", publish_hour=15, max_lag=2, now_ny=now
        )

def test_covering_candidate_requires_falling_gross_shorts_not_just_net_change():
    row={"net":-500000,"long_change":-10,"short_change":-110,"net_change":100}
    assert "숏 축소 우세" in watch.gross_position_driver(row)
    assert "신규 롱 증가 아님" in watch.position_note(row)


def test_new_long_addition_with_more_shorts_is_not_short_covering():
    row={"net":-1000,"long_change":150,"short_change":100,"net_change":50}
    assert watch.position_note(row)=="롱 증가 중심(숏 축소 아님)"


def test_simultaneous_long_addition_short_reduction_identified():
    row={"net":-1000,"long_change":20,"short_change":-100,"net_change":120}
    assert watch.position_note(row)=="숏 축소 우세·롱 증가 동반"


def test_oct20_ultra_public_cftc_does_not_imply_jpm_client_neutrality():
    row={"net":-804808,"long_change":6234,"short_change":95313,"net_change":-89079}
    assert watch.gross_position_driver(row)=="숏 증가가 롱 증가 앞섬"
    assert "중립" not in watch.gross_position_driver(row)


def test_bad_gross_net_arithmetic_fails_closed():
    row={"long_change":30,"short_change":-20,"net_change":100}
    with pytest.raises(ValueError,match="gross long/short"):
        watch.gross_position_driver(row)


def test_telegram_ack_requires_correct_chat_and_positive_message_id(monkeypatch):
    import json

    class FakeResponse:
        def __init__(self,payload): self.raw=json.dumps(payload).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return self.raw

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN","test-fixture-only")
    monkeypatch.setenv("TELEGRAM_CHAT_ID","-10012345")
    correct={"ok":True,"result":{"message_id":488,"chat":{"id":-10012345}}}
    monkeypatch.setattr(
        watch.urllib.request,"urlopen",
        lambda *args,**kwargs: FakeResponse(correct)
    )
    assert watch.send_telegram("CFTC fixture") == 488
    invalid=[
        {"ok":False,"result":correct["result"]},
        {"ok":True,"result":{"chat":{"id":-10012345}}},
        {"ok":True,"result":{"message_id":True,"chat":{"id":-10012345}}},
        {"ok":True,"result":{"message_id":488,"chat":{"id":-10098765}}},
        {"ok":True,"result":{"message_id":488,"chat":{}}},
    ]
    for bad in invalid:
        monkeypatch.setattr(
            watch.urllib.request,"urlopen",
            lambda *args,_bad=bad,**kwargs: FakeResponse(_bad)
        )
        with pytest.raises(RuntimeError):
            watch.send_telegram("CFTC fixture")


def test_contracts_and_observation_scope_stay_separate():
    assert watch.CONTRACTS["30년"]["code"] == "020601"
    assert watch.CONTRACTS["초장기(UB)"]["code"] == "020604"
    row={"net":-100000,"long_change":0,"short_change":-200,"net_change":200}
    assert watch.position_note(row)=="숏 축소 우세(신규 롱 증가 아님)"


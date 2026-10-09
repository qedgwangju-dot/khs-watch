"""Offline regression checks for the official Treasury 30Y conditional-alert watcher.

No network access or Telegram messages are used in these tests.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import treasury_30y_jpm_level_alert as watch


def state(date="2026-10-07", rate=5.54):
    return {
        "version": 1,
        "last_date": date,
        "last_rate": rate,
        "armed": {**{watch.k("up", v): True for v in watch.UP},
                  **{watch.k("down", v): True for v in watch.DOWN}},
        "last_alert": None,
    }


def test_initialization_sends_nothing_when_already_above_559():
    s, events = watch.transition({}, [("2026-10-07", 5.67), ("2026-10-08", 5.60)])
    assert not events
    assert not s["armed"]["up:5.59"]
    assert s["armed"]["up:5.78"]


def test_one_true_up_crossing_and_same_observation_deduped():
    s, events = watch.transition(state(), [("2026-10-07", 5.54), ("2026-10-08", 5.59)])
    assert [(e["direction"], e["level"], e["date"]) for e in events] == [("up", 5.59, "2026-10-08")]
    assert not s["armed"]["up:5.59"]
    same, repeated = watch.transition(s, [("2026-10-07", 5.54), ("2026-10-08", 5.59)])
    assert not repeated
    assert same == s


def test_five_bp_hysteresis_rearms_only_after_full_retreat():
    s, e = watch.transition(state(), [("2026-10-07", 5.54), ("2026-10-08", 5.60)])
    assert len(e) == 1
    s, e = watch.transition(s, [("2026-10-08", 5.60), ("2026-10-09", 5.57)])
    assert not e and not s["armed"]["up:5.59"]
    s, e = watch.transition(s, [("2026-10-09", 5.57), ("2026-10-12", 5.54)])
    assert not e and s["armed"]["up:5.59"]
    s, e = watch.transition(s, [("2026-10-12", 5.54), ("2026-10-13", 5.59)])
    assert [(x["direction"], x["level"]) for x in e] == [("up", 5.59)]


def test_downward_thresholds_and_rearm():
    initial = state(rate=5.31)
    s, events = watch.transition(initial, [("2026-10-07", 5.31), ("2026-10-08", 5.12)])
    assert {(e["direction"], e["level"]) for e in events} == {("down", 5.25), ("down", 5.15)}
    assert not s["armed"]["down:5.25"]
    s, events = watch.transition(s, [("2026-10-08", 5.12), ("2026-10-09", 5.26)])
    assert not events and not s["armed"]["down:5.25"]
    s, events = watch.transition(s, [("2026-10-09", 5.26), ("2026-10-12", 5.30)])
    assert not events and s["armed"]["down:5.25"]
    s, events = watch.transition(s, [("2026-10-12", 5.30), ("2026-10-13", 5.25)])
    assert [(e["direction"], e["level"]) for e in events] == [("down", 5.25)]


def test_gapped_trading_days_are_scanned():
    s, events = watch.transition(state(), [
        ("2026-10-07", 5.54),
        ("2026-10-08", 5.60),
        ("2026-10-09", 5.52),
        ("2026-10-12", 5.59),
    ])
    assert [e["date"] for e in events] == ["2026-10-08", "2026-10-12"]


def test_jump_across_multiple_levels_in_one_day_single_batch():
    s, events = watch.transition(state(), [("2026-10-07", 5.54), ("2026-10-08", 6.01)])
    assert [e["level"] for e in events] == [5.59, 5.78, 6.00]
    msg = watch.format_alert(events, "2026-10-08", 6.01)
    assert msg.count("상향 돌파") == 3
    assert "장중 실시간 돌파 알림은 아닙니다" in msg
    assert len(msg) < 3800


def test_below_upper_level_not_mislabeled_as_breakout():
    s, events = watch.transition(state(rate=5.60), [("2026-10-07", 5.60), ("2026-10-08", 5.56)])
    assert not events


def test_mismatched_or_missing_historical_state_fails_closed():
    with pytest.raises(RuntimeError, match="unavailable"):
        watch.transition(state(), [("2026-10-08", 5.60), ("2026-10-09", 5.63)])
    with pytest.raises(RuntimeError, match="Revised"):
        watch.transition(state(), [("2026-10-07", 5.55), ("2026-10-08", 5.60)])


def test_expected_market_date_uses_new_york_session_not_korean_calendar():
    import datetime as dt
    from zoneinfo import ZoneInfo
    now = dt.datetime(2026, 10, 9, 8, 40, tzinfo=ZoneInfo("Asia/Seoul"))
    assert watch.latest_expected_date(now) == "2026-10-08"
    sun = dt.datetime(2026, 10, 11, 8, 40, tzinfo=ZoneInfo("Asia/Seoul"))
    assert watch.latest_expected_date(sun) == "2026-10-09"


def test_updater_disallows_unverified_source_differences(monkeypatch):
    monkeypatch.setattr(watch, "get_curve_pair", lambda: (
        {"date": "2026-10-08", "30Y": 5.61},
        {"date": "2026-10-07", "30Y": 5.55},
    ))
    with pytest.raises(RuntimeError, match="parser mismatch"):
        watch.crosscheck_latest([("2026-10-07", 5.55), ("2026-10-08", 5.60)])


def test_telegram_route_and_endpoint_are_hardcoded_to_expected_bot():
    from inspect import getsource
    code = getsource(watch.send_telegram)
    assert "khs8879887988798879_bot" in code
    assert "getChat" in code and "getMe" in code
    assert "/sendMessage" in code

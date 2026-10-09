"""Regression suite: U.S. Treasury official end-of-day 30Y threshold alerts."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import treasury_30y_jpm_threshold_watch as watch  # noqa: E402
import treasury_positioning_watch as weekly  # noqa: E402


def test_bp_exact_and_float_precision():
    assert watch.bp_from_percent("5.59") == 559
    assert watch.bp_from_percent(5.78) == 578
    assert watch.pct(515) == "5.15%"
    with pytest.raises(RuntimeError, match="precision"):
        watch.bp_from_percent("5.591")


def test_bootstrap_above_level_does_not_report_historical_breakout():
    start = watch.initial_state("2026-10-08", 560)
    assert start["armed_up"]["559"] is False
    again, events = watch.evaluate(start, "2026-10-08", 560, "2026-10-07", 567)
    assert not events
    assert again == start


def test_upward_5_59_breakout_once_and_same_day_dedupe():
    state = watch.initial_state("2026-10-06", 553)
    updated, events = watch.evaluate(state, "2026-10-07", 559, "2026-10-06", 553)
    assert events == [("상향", 559)]
    assert updated["armed_up"]["559"] is False
    same, duplicate = watch.evaluate(updated, "2026-10-07", 559, "2026-10-06", 553)
    assert same == updated
    assert not duplicate


def test_large_gap_crosses_multiple_upward_levels_in_one_message():
    state = watch.initial_state("2026-10-06", 553)
    _, events = watch.evaluate(state, "2026-10-07", 605, "2026-10-06", 553)
    assert events == [("상향", 559), ("상향", 578), ("상향", 600)]
    msg = watch.crossing_message(
        "2026-10-07", 605, "2026-10-06", 553, events, "https://home.treasury.gov/"
    )
    for level in ("5.59%", "5.78%", "6.00%"):
        assert level in msg
    assert "장중 실시간 돌파가 아닌 공식 일별 관측치" in msg


def test_downward_levels_and_missing_middle_threshold():
    state = watch.initial_state("2026-10-06", 528)
    _, events = watch.evaluate(state, "2026-10-07", 514, "2026-10-06", 528)
    assert events == [("하향", 525), ("하향", 515)]


def test_5_bp_rearm_blocks_noise():
    state = watch.initial_state("2026-10-01", 553)
    state, ev = watch.evaluate(state, "2026-10-02", 561, "2026-10-01", 553)
    assert ev == [("상향", 559)]
    state, _ = watch.evaluate(state, "2026-10-05", 556, "2026-10-02", 561)
    state, ev = watch.evaluate(state, "2026-10-06", 561, "2026-10-05", 556)
    assert not ev
    state, _ = watch.evaluate(state, "2026-10-07", 554, "2026-10-06", 561)
    assert state["armed_up"]["559"] is True
    state, ev = watch.evaluate(state, "2026-10-08", 560, "2026-10-07", 554)
    assert ev == [("상향", 559)]


def test_down_rearm_blocks_noisy_reentry():
    state = watch.initial_state("2026-10-01", 530)
    state, ev = watch.evaluate(state, "2026-10-02", 525, "2026-10-01", 530)
    assert ev == [("하향", 525)]
    state, _ = watch.evaluate(state, "2026-10-05", 528, "2026-10-02", 525)
    state, ev = watch.evaluate(state, "2026-10-06", 524, "2026-10-05", 528)
    assert ev == []
    state, _ = watch.evaluate(state, "2026-10-07", 530, "2026-10-06", 524)
    state, ev = watch.evaluate(state, "2026-10-08", 524, "2026-10-07", 530)
    assert ev == [("하향", 525)]


def test_official_date_regression_and_revision_fail_closed():
    state = watch.initial_state("2026-10-08", 560)
    with pytest.raises(RuntimeError, match="regressed"):
        watch.evaluate(state, "2026-10-07", 540, "2026-10-06", 550)
    with pytest.raises(RuntimeError, match="revised"):
        watch.evaluate(state, "2026-10-08", 561, "2026-10-07", 550)
    with pytest.raises(RuntimeError, match="gap/revision"):
        watch.evaluate(state, "2026-10-09", 540, "2026-10-07", 550)


def test_freshness_weekend_and_future_observation():
    import datetime as dt
    assert watch.days_since_business_date("2026-10-09", dt.date(2026, 10, 12)) == 1
    with pytest.raises(RuntimeError, match="future"):
        watch.days_since_business_date("2026-10-13", dt.date(2026, 10, 12))


def test_weekly_report_distinguishes_holding_above_from_fresh_crossing():
    assert "유지" in weekly.jpm_30y_signal(5.60)
    assert "신규 돌파 여부는" in weekly.jpm_30y_signal(5.60)


def test_bootstrap_does_not_send_or_replay_earlier_spike(tmp_path):
    data = [
        ("2026-10-06", 553),
        ("2026-10-07", 560),
        ("2026-10-08", 561),
    ]
    state_path = tmp_path / "state.json"
    with patch.object(watch, "STATE", state_path), \
         patch.object(watch, "fetch_official_observations", return_value=(data, "https://home.treasury.gov/")), \
         patch.object(watch, "send_telegram", side_effect=AssertionError("Unexpected send")):
        watch.main()
    payload = json.loads(state_path.read_text())
    assert payload["last_processed_date"] == "2026-10-08"
    assert payload["last_message_id"] is None


def test_missed_official_dates_replay_without_false_stale_alert(tmp_path):
    data = [
        ("2026-10-06", 553),
        ("2026-10-07", 560),
        ("2026-10-08", 561),
    ]
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(watch.initial_state("2026-10-06", 553)))
    with patch.object(watch, "STATE", state_path), \
         patch.object(watch, "fetch_official_observations", return_value=(data, "https://home.treasury.gov/")), \
         patch.object(watch, "send_telegram", side_effect=AssertionError("Should not replay old signal")):
        watch.main()
    st = json.loads(state_path.read_text())
    assert st["last_processed_date"] == "2026-10-08"
    assert st["armed_up"]["559"] is False
    assert st["last_message_id"] is None


def test_validation_never_sends_or_advances_delivery_state(tmp_path, monkeypatch):
    data = [("2026-10-07", 553), ("2026-10-08", 560)]
    state_path = tmp_path / "state.json"
    initial = watch.initial_state("2026-10-07", 553)
    state_path.write_text(json.dumps(initial))
    monkeypatch.setenv("TREASURY_30Y_VALIDATE_ONLY", "1")
    with patch.object(watch, "STATE", state_path), \
         patch.object(watch, "OUT", tmp_path), \
         patch.object(watch, "fetch_official_observations", return_value=(data, "https://home.treasury.gov/")), \
         patch.object(watch, "send_telegram", side_effect=AssertionError("Audit must not send")):
        watch.main()
    assert json.loads(state_path.read_text()) == initial
    assert (tmp_path / "treasury_30y_jpm_crossing_preview.txt").exists()


def test_send_failure_does_not_consume_event_and_retry_sends_once(tmp_path, monkeypatch):
    data = [("2026-10-07", 553), ("2026-10-08", 560)]
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(watch.initial_state("2026-10-07", 553)))
    monkeypatch.delenv("TREASURY_30Y_VALIDATE_ONLY", raising=False)
    with patch.object(watch, "STATE", state_path), \
         patch.object(watch, "OUT", tmp_path), \
         patch.object(watch, "fetch_official_observations", return_value=(data, "https://home.treasury.gov/")):
        with patch.object(watch, "send_telegram", side_effect=RuntimeError("telegram unavailable")):
            with pytest.raises(RuntimeError, match="telegram unavailable"):
                watch.main()
        assert json.loads(state_path.read_text())["last_processed_date"] == "2026-10-07"
        with patch.object(watch, "send_telegram", return_value=988) as sender:
            watch.main()
            watch.main()
            sender.assert_called_once()
    st = json.loads(state_path.read_text())
    assert st["last_processed_date"] == "2026-10-08"
    assert st["last_message_id"] == 988

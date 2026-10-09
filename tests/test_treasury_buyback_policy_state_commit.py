"""Regression tests for the EXISTING Treasury buyback policy state writer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from treasury_buyback_policy_state_commit import merge_state, material


def test_policy_state_merges_confirmed_alerts_during_concurrent_commits():
    remote = {
        "last_checked_kst": "2026-10-10T07:00:00+09:00",
        "seen_source_ids": ["released-a"],
        "seen_long_end_special_shas": ["special-a"],
        "bessent_policy_boundary_revision": 11,
        "bessent_causal_verdict_key": "mixed",
    }
    local = {
        "last_checked_kst": "2026-10-10T07:10:00+09:00",
        "seen_source_ids": ["released-b"],
        "seen_long_end_special_shas": ["special-b"],
        "bessent_policy_boundary_revision": 12,
        "bessent_causal_verdict_key": "energy_disinflation_support",
        "pending_source_ids": ["should-not-commit"],
    }
    merged = merge_state(remote, local)
    assert merged["seen_source_ids"] == ["released-a", "released-b"]
    assert merged["seen_long_end_special_shas"] == ["special-a", "special-b"]
    assert merged["bessent_policy_boundary_revision"] == 12
    assert merged["bessent_causal_verdict_key"] == "energy_disinflation_support"
    assert "pending_source_ids" not in merged


def test_stale_policy_writer_never_overwrites_newer_remote_observation():
    remote = {
        "last_checked_kst": "2026-10-10T07:20:00+09:00",
        "long_end_max_bn": {"10Y to 20Y": 6.0},
        "bessent_causal_verdict_key": "mixed",
        "bessent_policy_boundary_revision": 12,
    }
    stale = {
        "last_checked_kst": "2026-10-10T07:00:00+09:00",
        "long_end_max_bn": {"10Y to 20Y": 4.0},
        "bessent_causal_verdict_key": "old",
        "bessent_policy_boundary_revision": 11,
    }
    merged = merge_state(remote, stale)
    assert merged["long_end_max_bn"]["10Y to 20Y"] == 6.0
    assert merged["bessent_causal_verdict_key"] == "mixed"
    assert merged["bessent_policy_boundary_revision"] == 12


def test_timestamp_only_change_does_not_need_commit():
    a = {"last_checked_kst": "2026-10-10T07:00:00+09:00", "last_state": "mixed"}
    b = {"last_checked_kst": "2026-10-10T07:15:00+09:00", "last_state": "mixed"}
    assert material(a) == material(b)

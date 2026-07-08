#!/usr/bin/env python3
"""Verify source-status Telegram alerts do not fire on one transient timeout."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "khs_policy_source_status_alert.py"


def run_status_script(cwd: pathlib.Path) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return (result.stdout or "").strip()


def write_failures(cwd: pathlib.Path, failures: list[dict]) -> None:
    out_dir = cwd / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "khs_source_failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sample_failure(source: str, lane: str = "domestic_stablecoin", url: str | None = None) -> dict:
    url = url or f"https://example.com/{source}"
    return {
        "key": f"{lane}|{source}|{url}",
        "lane": lane,
        "source": source,
        "url": url,
        "error": "timeout",
        "checked_at_kst": "2026-07-03T23:12:33+09:00",
        "proxy_configured": True,
    }


def assert_exists(path: pathlib.Path, expected: bool) -> None:
    actual = path.exists()
    if actual != expected:
        raise AssertionError(f"{path} exists={actual}, expected={expected}")


def verify_single_source_streak() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cwd = pathlib.Path(temp_dir)
        write_failures(cwd, [sample_failure("Korea FIU virtual asset notices")])

        first = run_status_script(cwd)
        if "skipped_single_transient_source" not in first:
            raise AssertionError(first)
        assert_exists(cwd / "out" / "khs_policy_source_status_alert.md", False)

        second = run_status_script(cwd)
        if "source_status_alert=created" not in second:
            raise AssertionError(second)
        assert_exists(cwd / "out" / "khs_policy_source_status_alert.md", True)

        (cwd / "out" / "khs_source_failures.json").unlink()
        cleared = run_status_script(cwd)
        if "cleared_failure_streaks" not in cleared:
            raise AssertionError(cleared)
        state = json.loads((cwd / "data" / "khs_source_failure_seen.json").read_text(encoding="utf-8"))
        if state.get("failure_streaks") != {}:
            raise AssertionError(state)


def verify_multiple_sources_alert_immediately() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cwd = pathlib.Path(temp_dir)
        write_failures(
            cwd,
            [
                sample_failure("Korea FIU virtual asset notices"),
                sample_failure("Korea telecom policy", lane="domestic_telecom"),
            ],
        )

        first = run_status_script(cwd)
        if "source_status_alert=created" not in first:
            raise AssertionError(first)
        assert_exists(cwd / "out" / "khs_policy_source_status_alert.md", True)


def verify_same_source_family_is_single_logical_failure() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cwd = pathlib.Path(temp_dir)
        write_failures(
            cwd,
            [
                sample_failure(
                    "Korea Policy Briefing stablecoin search",
                    url="https://www.korea.kr/news/policyNewsList.do?srchKeyword=stablecoin",
                ),
                sample_failure(
                    "Korea Policy Briefing digital asset search",
                    url="https://www.korea.kr/news/policyNewsList.do?srchKeyword=digitalasset",
                ),
            ],
        )

        first = run_status_script(cwd)
        if "skipped_single_transient_source" not in first:
            raise AssertionError(first)
        if "logical_failures=1" not in first:
            raise AssertionError(first)
        assert_exists(cwd / "out" / "khs_policy_source_status_alert.md", False)


def main() -> int:
    verify_single_source_streak()
    verify_multiple_sources_alert_immediately()
    verify_same_source_family_is_single_logical_failure()
    print("khs_source_status_contract=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

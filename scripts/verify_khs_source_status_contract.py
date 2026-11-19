#!/usr/bin/env python3
"""Verify source-status Telegram alerts do not fire on one transient timeout."""

from __future__ import annotations

import json
import datetime as dt
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import khs_policy_source_status_alert as status
from khs_policy_telegram_formatter import format_policy_message, prepare_telegram_html

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


def verify_two_sources_require_repeat() -> None:
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
        if "skipped_multiple_transient_sources" not in first:
            raise AssertionError(first)
        assert_exists(cwd / "out" / "khs_policy_source_status_alert.md", False)

        second = run_status_script(cwd)
        if "source_status_alert=created" not in second:
            raise AssertionError(second)
        assert_exists(cwd / "out" / "khs_policy_source_status_alert.md", True)


def verify_broad_outage_alerts_immediately() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cwd = pathlib.Path(temp_dir)
        write_failures(
            cwd,
            [
                sample_failure("Korea telecom policy", lane="domestic_telecom", url="https://www.korea.kr/news"),
                sample_failure("FSC stablecoin", url="https://www.fsc.go.kr/no010101"),
                sample_failure("Korea FIU", url="https://www.kofiu.go.kr/kor/notification"),
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


def mixed_failures() -> list[dict]:
    review = sample_failure(
        "BIS remote rule material conditions",
        lane="trusted_policy",
        url="https://www.federalregister.gov/documents/full_text/text/2026/11/19/2026-23529.txt",
    )
    review["error"] = "Material conditions differ from validated snapshot; detailed facts withheld."
    fsc = [
        sample_failure(name, url=f"https://www.fsc.go.kr/{board}?srchText={term}")
        for name, board, term in (
            ("FSC stablecoin releases", "no010101", "stablecoin"),
            ("FSC stablecoin explanations", "no010102", "stablecoin"),
            ("FSC digital asset releases", "no010101", "digitalasset"),
        )
    ]
    return [review, *fsc]


def verify_mixed_outcomes_are_not_domestic_outage() -> None:
    rows = mixed_failures()
    now = dt.datetime(2026, 11, 19, 21, 56, tzinfo=status.KST)
    title, body = status.render(rows, now)
    assert "국내 공식 소스 확인 불가" not in title
    assert "원문 수집 완료·세부 조건 재검증 필요" in body
    assert body.count("이번 실행에서 접속 실패") == 1
    assert "국내 통신정책" not in body
    assert "검색·게시판 3개" in body
    assert "Material conditions differ" not in body
    title, body = format_policy_message(title, body, rates={}, now=now)
    html = prepare_telegram_html(title, body)
    assert html.count('<a href="') == 2
    assert "&lt;a href" not in html
    review = {**rows[0], "failure_kind": "content_review"}
    outage = {**rows[0], "source": "BIS original", "error": "timeout", "failure_kind": "source_unavailable"}
    assert status.logical_failure_key(review) != status.logical_failure_key(outage)
    title, body = status.render([review], now)
    assert title == "정책 워치: 공식 원문 재검증 필요"
    assert "이번 실행에서 접속 실패" not in body
    assert "직접 조회" not in body and "프록시" not in body
    publication = {**review, "failure_kind": "publication_unverified"}
    assert "정식 관보 게재 확인 보류" in status.render([publication], now)[1]


def verify_review_does_not_promote_transient_network_or_repeat_as_groups_change() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cwd = pathlib.Path(temp_dir)
        rows = mixed_failures()
        write_failures(cwd, rows)
        assert "source_status_alert=created" in run_status_script(cwd)
        body_path = cwd / "out" / "khs_policy_source_status_alert.md"
        first = body_path.read_text(encoding="utf-8")
        assert "재검증 필요" in first and "금융위원회" not in first
        assert "source_status_alert=created" in run_status_script(cwd)
        second = body_path.read_text(encoding="utf-8")
        assert "금융위원회" in second and "미 BIS" not in second
        write_failures(cwd, rows[1:3])
        assert "skipped_duplicate" in run_status_script(cwd)
        assert_exists(body_path, False)
        (cwd / "out" / "khs_source_failures.json").unlink()
        run_status_script(cwd)
        assert_exists(body_path, False)


def verify_legacy_notification_is_not_resent() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cwd = pathlib.Path(temp_dir)
        rows = mixed_failures()
        write_failures(cwd, rows)
        (cwd / "data").mkdir()
        (cwd / "data" / "khs_source_failure_seen.json").write_text(json.dumps({
            "seen": {"old-bundle": {
                "first_seen_kst": status.now_kst().isoformat(),
                "sources": [row["source"] for row in rows],
            }},
        }), encoding="utf-8")
        assert "skipped_duplicate" in run_status_script(cwd)
        assert_exists(cwd / "out" / "khs_policy_source_status_alert.md", False)


def main() -> int:
    verify_single_source_streak()
    verify_two_sources_require_repeat()
    verify_broad_outage_alerts_immediately()
    verify_same_source_family_is_single_logical_failure()
    verify_mixed_outcomes_are_not_domestic_outage()
    verify_review_does_not_promote_transient_network_or_repeat_as_groups_change()
    verify_legacy_notification_is_not_resent()
    print("khs_source_status_contract=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

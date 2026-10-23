from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ACTIVE_SOURCE_JOBS = {
    "KOSPI Derivatives Flow CI": {"test"},
    "KOSPI LS Realtime Derivatives Flow Watch": {"morning", "afternoon"},
    "Korea Market Stress and Global Wave Telegram Watch": {"watch"},
    "KOSPI Derivatives Flow Telegram Watch": {"watch"},
    "KOSDAQ Surge Industry Context CI": {
        "live_source", "native_source", "market_flow_source",
    },
}


def _default_fetch_json(repository: str, token: str, path: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/{path.lstrip('/')}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def find_active_source_consumers(
    repository: str,
    token: str,
    current_run_id: int,
    fetch_json: Callable[[str, str, str], dict[str, Any]] = _default_fetch_json,
) -> tuple[list[str], list[str], int]:
    active: list[str] = []
    unknown: list[str] = []
    scanned = 0
    for status in ("in_progress", "queued"):
        try:
            payload = fetch_json(
                repository, token,
                f"actions/runs?status={status}&per_page=100",
            )
            runs = payload.get("workflow_runs")
            if not isinstance(runs, list):
                unknown.append(f"invalid_run_list:{status}")
                continue
            if len(runs) >= 100:
                unknown.append(f"run_list_truncated:{status}")
            for run in runs:
                if not isinstance(run, dict):
                    unknown.append(f"invalid_run_row:{status}")
                    continue
                name = str(run.get("name") or "")
                relevant_jobs = ACTIVE_SOURCE_JOBS.get(name)
                if not relevant_jobs:
                    continue
                run_id = int(run.get("id") or 0)
                if run_id == current_run_id:
                    continue
                scanned += 1
                if status == "queued" or run.get("status") == "queued":
                    active.append(f"{name}#{run_id}:queued")
                    continue
                try:
                    job_payload = fetch_json(
                        repository, token,
                        f"actions/runs/{run_id}/jobs?per_page=100",
                    )
                    jobs = job_payload.get("jobs")
                    if not isinstance(jobs, list):
                        unknown.append(f"invalid_job_list:{run_id}")
                        continue
                except Exception as exc:
                    unknown.append(f"job_lookup_failed:{run_id}:{type(exc).__name__}")
                    continue
                matching = [
                    job for job in jobs
                    if isinstance(job, dict)
                    and str(job.get("name") or "") in relevant_jobs
                ]
                if not matching:
                    unknown.append(f"consumer_job_not_visible:{run_id}")
                    continue
                for job in matching:
                    if job.get("status") in {"queued", "in_progress"}:
                        active.append(
                            f"{name}#{run_id}:{job.get('name')}:{job.get('status')}"
                        )
        except Exception as exc:
            unknown.append(f"run_lookup_failed:{status}:{type(exc).__name__}")
    return active, unknown, scanned


def _in_market_session(now: datetime, session: dict[str, Any]) -> bool:
    if not session.get("is_session"):
        return False
    market_open = session.get("open")
    market_close = session.get("close")
    return bool(
        market_open is not None
        and market_close is not None
        and market_open <= now < market_close
    )


def decide_live_probe(
    event_name: str,
    opted_in: bool,
    in_session: bool,
    active_consumers: list[str],
    unknown_checks: list[str],
) -> tuple[bool, str]:
    if event_name not in {"schedule", "workflow_dispatch"}:
        return False, "scheduled_or_manual_event_required"
    if event_name == "workflow_dispatch" and not opted_in:
        return False, "manual_opt_in_required"
    if not in_session:
        return False, "outside_market_session"
    if unknown_checks:
        return False, "active_consumer_scan_incomplete"
    if active_consumers:
        return False, "active_source_consumer_present"
    return True, "clear"


def decide_history_probe(
    event_name: str,
    opted_in: bool,
    in_session: bool,
    active_consumers: list[str],
    unknown_checks: list[str],
) -> tuple[bool, str]:
    if event_name not in {"schedule", "workflow_dispatch"}:
        return False, "scheduled_or_manual_event_required"
    if event_name == "workflow_dispatch" and not opted_in:
        return False, "manual_opt_in_required"
    if in_session:
        return False, "market_session_active"
    if unknown_checks:
        return False, "active_consumer_scan_incomplete"
    if active_consumers:
        return False, "active_source_consumer_present"
    return True, "clear_after_hours"


def write_github_outputs(
    live_allowed: bool,
    history_allowed: bool,
    reason: str,
    env: dict[str, str] | None = None,
) -> None:
    env = os.environ if env is None else env
    env_path = env.get("GITHUB_ENV")
    if env_path:
        with open(env_path, "a", encoding="utf-8") as out:
            out.write(f"KOSPI_SKIP_LIVE_TESTS={'0' if live_allowed else '1'}\n")
            out.write(f"KOSPI_HISTORY_PROBE_ALLOWED={'1' if history_allowed else '0'}\n")
    output_path = env.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as out:
            out.write(f"allow={'true' if live_allowed else 'false'}\n")
            out.write(f"history_allow={'true' if history_allowed else 'false'}\n")
            out.write(f"reason={reason}\n")


def main() -> int:
    from krx_session_calendar import session_state

    event_name = (os.environ.get("EVENT_NAME") or "").strip()
    opted_in = (os.environ.get("RUN_LIVE_SOURCE_PROBES") or "").strip().lower() == "true"
    now = datetime.now(KST)
    session = session_state(now)
    in_session = _in_market_session(now, session)
    active: list[str] = []
    unknown: list[str] = []
    scanned = 0

    if event_name == "schedule" or (event_name == "workflow_dispatch" and opted_in):
        repository = (os.environ.get("REPOSITORY") or "").strip()
        token = (os.environ.get("GH_TOKEN") or "").strip()
        try:
            current_run_id = int(os.environ.get("CURRENT_RUN_ID") or "0")
        except ValueError:
            current_run_id = 0
        if not repository or not token or current_run_id <= 0:
            unknown.append("missing_github_api_context")
        else:
            active, unknown, scanned = find_active_source_consumers(
                repository, token, current_run_id,
            )

    live_allowed, live_reason = decide_live_probe(
        event_name, opted_in, in_session, active, unknown,
    )
    history_allowed, history_reason = decide_history_probe(
        event_name, opted_in, in_session, active, unknown,
    )
    reason = live_reason if in_session else history_reason
    if unknown:
        reason = "active_consumer_scan_incomplete"
    write_github_outputs(live_allowed, history_allowed, reason)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("### LS source-probe gate\n")
            summary.write(f"- Live probe: {'allowed' if live_allowed else 'skipped'}\n")
            summary.write(f"- After-hours history probe: {'allowed' if history_allowed else 'skipped'}\n")
            summary.write(f"- Decision: {reason}\n")
            summary.write(f"- Active source consumers: {len(active)}; incomplete checks: {len(unknown)}\n")

    print(
        "ls_live_source_gate="
        f"live_allowed={str(live_allowed).lower()} "
        f"history_allowed={str(history_allowed).lower()} "
        f"event={event_name or 'unknown'} opted_in={str(opted_in).lower()} "
        f"in_session={str(in_session).lower()} active_consumers={len(active)} "
        f"unknown_checks={len(unknown)} scanned={scanned} reason={reason}"
    )
    for item in active[:20]:
        print(f"active_source_consumer={item}")
    for item in unknown[:20]:
        print(f"active_source_consumer_unknown={item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

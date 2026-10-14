#!/usr/bin/env python3
"""Warsh 워크플로 예약 누락 보완용 실행 간격 가드.

정규 cron은 그대로 보존한다. GitHub Actions 예약 실행이 지연/누락될 때
AI Security Web Watch의 workflow_run 이벤트를 보조 트리거로 사용하되,
직전 Warsh monitor 작업이 정상 완료된 지 55분이 지나지 않았으면
중복 실행을 건너뛴다.

중요:
- schedule/push/workflow_dispatch는 절대 막지 않는다.
- 보조 트리거 판정에 GitHub Actions API 조회가 실패하면 coverage를 우선해 실행한다.
- workflow 전체 success가 아니라 실제 'monitor' job success만 최근 정상 실행으로 인정한다.
"""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request

WORKFLOW_FILE = "warsh-reaction-telegram-watch.yml"
DEFAULT_FALLBACK_GAP_MINUTES = 55.0


def parse_utc(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def due_decision(event_name, last_monitor_success_at, now=None, threshold_minutes=DEFAULT_FALLBACK_GAP_MINUTES):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if event_name != "workflow_run":
        return True, None, "정규 트리거 보존"
    if last_monitor_success_at is None:
        return True, None, "직전 monitor 성공 실행을 찾지 못해 보조 실행"
    last = last_monitor_success_at.astimezone(dt.timezone.utc)
    lag = (now.astimezone(dt.timezone.utc) - last).total_seconds() / 60.0
    if lag < 0:
        # GitHub 시각 불일치가 있으면 누락보다 중복을 감수한다.
        return True, lag, "실행시각 역전 감지 — 보조 실행"
    return lag >= threshold_minutes, lag, (
        "정규 실행 공백 보완" if lag >= threshold_minutes else "최근 정상 실행 존재 — 보조 실행 생략"
    )


def api_json(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "khs-watch-warsh-cadence/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_monitor_success(repo, token, current_run_id):
    workflow = urllib.parse.quote(WORKFLOW_FILE, safe="")
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs"
        "?branch=main&status=completed&per_page=20"
    )
    data = api_json(url, token)
    runs = data.get("workflow_runs") or []
    for run in runs:
        try:
            run_id = int(run.get("id"))
        except (TypeError, ValueError):
            continue
        if run_id == int(current_run_id):
            continue
        if run.get("conclusion") != "success":
            continue
        jobs_url = str(run.get("jobs_url") or "")
        if not jobs_url:
            jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
        jobs = api_json(jobs_url, token).get("jobs") or []
        monitor = next((j for j in jobs if j.get("name") == "monitor"), None)
        if not monitor or monitor.get("conclusion") != "success":
            continue
        stamp = (
            monitor.get("completed_at")
            or run.get("updated_at")
            or run.get("run_started_at")
            or run.get("created_at")
        )
        parsed = parse_utc(stamp)
        if parsed is not None:
            return {
                "run_id": run_id,
                "completed_at": parsed,
                "event": run.get("event"),
                "html_url": run.get("html_url"),
            }
    return None


def write_output(name, value):
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{name}={value}\n")


def main():
    event = (os.getenv("GITHUB_EVENT_NAME") or "").strip()
    threshold = float(os.getenv("WARSH_FALLBACK_GAP_MINUTES") or DEFAULT_FALLBACK_GAP_MINUTES)
    current_run = int(os.getenv("GITHUB_RUN_ID") or "0")
    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = (os.getenv("GH_TOKEN") or "").strip()

    previous = None
    error = None
    if event == "workflow_run":
        if not repo or not token or not current_run:
            error = "GitHub Actions 조회 환경변수 누락"
        else:
            try:
                previous = latest_monitor_success(repo, token, current_run)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"

    if error:
        should_run, lag, reason = True, None, "보조 트리거 상태조회 실패 — 누락 방지로 실행"
    else:
        should_run, lag, reason = due_decision(
            event,
            previous.get("completed_at") if previous else None,
            threshold_minutes=threshold,
        )

    write_output("run", "true" if should_run else "false")
    write_output("lag_minutes", "" if lag is None else f"{lag:.1f}")
    write_output("reason", reason.replace("\n", " "))
    write_output("last_success_run_id", previous.get("run_id") if previous else "")

    print(json.dumps({
        "trigger": event,
        "execute": should_run,
        "threshold_minutes": threshold,
        "last_monitor_success_run_id": previous.get("run_id") if previous else None,
        "last_monitor_success_at_utc": (
            previous["completed_at"].isoformat() if previous else None
        ),
        "lag_minutes": None if lag is None else round(lag, 1),
        "reason": reason,
        "api_error": error,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

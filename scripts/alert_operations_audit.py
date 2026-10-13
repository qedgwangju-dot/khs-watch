#!/usr/bin/env python3
"""Read-only operational checks for the existing GitHub -> Python -> Telegram watches.

Never enables/disables workflows, sends messages, rewrites seen state, or accesses
repository secrets. GitHub job success is not proof of Telegram delivery.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import re
from typing import Any


def parse_jsonl(path: pathlib.Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    records = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{n}: invalid JSONL: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{n}: expected object")
            records.append(item)
    return records


def conservative_schedule_gap_hours(cron: str) -> int | None:
    """Flag only predictable hourly or daily schedules, never guess on weekly/custom cron."""
    parts = cron.strip().split()
    if len(parts) != 5:
        return None
    minute, hour, day_of_month, month, day_of_week = parts
    if (day_of_month, month, day_of_week) != ("*", "*", "*"):
        return None
    if hour == "*":
        return 3  # Hourly cadence plus GitHub scheduling delay tolerance.
    if re.fullmatch(r"(?:[01]?\\d|2[0-3])", hour):
        return 48  # Daily cadence plus generous delay tolerance.
    return None


def inspect_workflow(path: pathlib.Path) -> dict[str, Any]:
    body = path.read_text(encoding="utf-8")
    is_schedule = bool(re.search(r"(?m)^  schedule:\s*$", body))
    is_dispatch = bool(re.search(r"(?m)^  workflow_dispatch:\s*", body))
    direct_send = "/sendMessage" in body or "sendMessage" in body
    is_active_alert = bool(re.search(r"(?i)(telegram|alert|watch)", path.name))
    is_one_shot = bool(re.search(r"(?i)(-once|-smoketest|-smoke-test|-test|-ci|route-inventory)", path.name))
    risks = []
    crons: list[str] = []
    if r"\${{" in body:
        risks.append("escaped_github_expression")
    if direct_send and not is_one_shot and not re.search(r"\bmessage_id\b", body):
        risks.append("direct_send_without_message_id_check")
    if is_schedule and not is_dispatch and is_active_alert and not is_one_shot:
        risks.append("no_manual_dispatch_for_scheduled_watch")
    if (is_schedule and "workflow_run:" in body and
            re.search(r"(?m)^\s+cancel-in-progress:\s*true\s*$", body)):
        risks.append("schedule_workflow_run_cancellation_risk")
    if is_schedule:
        crons = re.findall(r"(?m)^\s*-\s*cron:\s*['\"]?([^'\"\n#]+)", body)
        if not crons:
            risks.append("missing_cron_for_scheduled_watch")
        for cron in crons:
            if len(cron.strip().split()) != 5:
                risks.append("invalid_cron_field_count")
                break
    return {
        "path": path.as_posix(),
        "schedule": is_schedule,
        "dispatch": is_dispatch,
        "inline_telegram_send": direct_send,
        "receipt_marker": bool(re.search(r"\bmessage_id\b", body)),
        "one_shot_or_test": is_one_shot,
        "schedule_max_gap_hours": (
            min(limits) if (limits := [gap for cron in crons if (gap := conservative_schedule_gap_hours(cron)) is not None])
            else None
        ),
        "risks": sorted(set(risks)),
    }


def audit_static(root: pathlib.Path) -> dict[str, Any]:
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        raise FileNotFoundError(f"workflow directory not found: {directory}")
    paths = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    rows = []
    for p in paths:
        row = inspect_workflow(p)
        row["path"] = str(p.relative_to(root))
        rows.append(row)
    counts = collections.Counter(risk for row in rows for risk in row["risks"])
    return {
        "workflow_files": len(rows),
        "workflow_paths": [row["path"] for row in rows],
        "scheduled_files": sum(row["schedule"] for row in rows),
        "inline_send_files": sum(row["inline_telegram_send"] for row in rows),
        "schedule_max_gap_hours": {
            row["path"]: row["schedule_max_gap_hours"]
            for row in rows if row["schedule_max_gap_hours"] is not None
        },
        "risk_counts": dict(sorted(counts.items())),
        "findings": [{"path": row["path"], "risks": row["risks"]} for row in rows if row["risks"]],
        "scope": "static read-only; does not prove a workflow is enabled or has sent Telegram",
    }


def audit_runtime(
    runs: list[dict[str, Any]],
    workflows: list[dict[str, Any]],
    known_paths: set[str] | None = None,
    schedule_max_gap_hours: dict[str, int] | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    # Adjacent API time windows may overlap at their exact boundary. Count
    # a workflow run ID once, not once per API page or window.
    unique: dict[str, dict[str, Any]] = {}
    for run in runs:
        key = str(run.get("id") or "").strip()
        if not key:
            key = "|".join(str(run.get(k) or "") for k in ("path", "created_at", "event", "conclusion"))
        unique[key] = run
    runs = list(unique.values())
    by_path: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for run in runs:
        path = str(run.get("path") or "").strip()
        if path:
            by_path[path].append(run)
    for group in by_path.values():
        group.sort(key=lambda run: str(run.get("created_at") or ""), reverse=True)
    failures = []
    totals = collections.Counter()
    for path, group in by_path.items():
        counts = collections.Counter(str(x.get("conclusion") or x.get("status") or "unknown") for x in group)
        totals.update(counts)
        if counts.get("failure") or counts.get("cancelled") or counts.get("timed_out"):
            latest = group[0]
            latest_schedule = next((run for run in group if run.get("event") == "schedule"), None)
            failures.append({
                "path": path,
                "failures": counts.get("failure", 0),
                "cancelled": counts.get("cancelled", 0),
                "timed_out": counts.get("timed_out", 0),
                "latest_conclusion": latest.get("conclusion") or latest.get("status") or "unknown",
                "latest_event": latest.get("event") or "unknown",
                "latest_at": latest.get("created_at") or "",
                "latest_url": latest.get("html_url") or "",
                "latest_schedule_conclusion": (
                    (latest_schedule.get("conclusion") or latest_schedule.get("status") or "unknown")
                    if latest_schedule else "not_observed"
                ),
                "latest_schedule_at": latest_schedule.get("created_at", "") if latest_schedule else "",
                "latest_schedule_url": latest_schedule.get("html_url", "") if latest_schedule else "",
            })
    failures.sort(key=lambda x: (-x["failures"], -x["cancelled"], x["path"]))
    disabled = [
        {"path": w.get("path", ""), "state": w.get("state", ""), "name": w.get("name", "")}
        for w in workflows if str(w.get("state") or "") not in ("active", "")
    ]
    registry_only = [
        {"path": w.get("path", ""), "state": w.get("state", ""), "name": w.get("name", "")}
        for w in workflows
        if known_paths is not None and str(w.get("path") or "") not in known_paths
    ]
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Audit clock must be timezone-aware")
    schedule_gaps = []
    for workflow in workflows:
        # Never diagnose or reactivate a disabled workflow; only the registry
        # can establish whether a workflow is currently active.
        if str(workflow.get("state") or "") != "active":
            continue
        path = str(workflow.get("path") or "")
        max_gap = (schedule_max_gap_hours or {}).get(path)
        if max_gap is None:
            continue
        schedules = [run for run in by_path.get(path, []) if run.get("event") == "schedule"]
        latest = schedules[0] if schedules else None
        if not latest:
            schedule_gaps.append({
                "path": path, "max_gap_hours": max_gap,
                "reason": "no_scheduled_run_in_observed_window",
                "latest_run_url": "", "hours_since_run": None,
            })
            continue
        raw_time = str(latest.get("created_at") or "")
        try:
            created = dt.datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            if created.tzinfo is None:
                continue
        except ValueError:
            continue
        age = (now - created).total_seconds() / 3600
        if age > max_gap:
            schedule_gaps.append({
                "path": path, "max_gap_hours": max_gap,
                "reason": "scheduled_run_overdue",
                "latest_run_url": str(latest.get("html_url") or ""),
                "hours_since_run": round(age, 2),
            })
    return {
        "runs_reviewed": len(runs),
        "workflow_groups_in_runs": len(by_path),
        "registry_only_workflows": registry_only,
        "conclusions": dict(sorted(totals.items())),
        "failure_clusters": failures,
        "schedule_silence_candidates": schedule_gaps,
        "inactive_workflows": disabled,
        "registry_size": len(workflows),
        "limitations": [
            "A successful GitHub run does not prove Telegram sendMessage or message_id",
            "Cancelled runs cannot be called lost alerts without their job logs and dedupe state",
            "A source coverage fail-closed result must not be reclassified as no news",
            "Never auto-enable inactive or manually disabled workflows",
            "Schedule silence is a candidate requiring activation metadata, run-log and sampling-window checks, not proof of missing Telegram delivery",
        ],
    }


def make_markdown(static: dict[str, Any], runtime: dict[str, Any] | None) -> str:
    lines = [
        "## 알림 운영 공통 진단 — 읽기 전용",
        f"- 워크플로 파일: {static['workflow_files']}개 · 예약 설정: {static['scheduled_files']}개",
        f"- 직접 Telegram API 송출 코드: {static['inline_send_files']}개",
        "- 공통 위험 후보(확정 장애 아님):",
    ]
    for name, n in static["risk_counts"].items():
        lines.append(f"  - {name}: {n}개")
    if not static["risk_counts"]:
        lines.append("  - 없음")
    if runtime is None:
        lines.append("- 최근 실행 기록: 이 실행에서는 조회하지 않음")
    else:
        counts = runtime["conclusions"]
        lines.extend([
            f"- 실행 {runtime['runs_reviewed']}건: 성공 {counts.get('success',0)} · 실패 {counts.get('failure',0)} · 취소 {counts.get('cancelled',0)}",
            f"- 등록 워크플로 {runtime['registry_size']}개 · 비활성 {len(runtime['inactive_workflows'])}개 (임의 재활성화 금지)",
            f"- 현재 파일 목록과 불일치하는 등록 항목: {len(runtime['registry_only_workflows'])}개 (확인 전 삭제 금지)",
            f"- 활성 작업 예약 실행 공백 후보: {len(runtime.get('schedule_silence_candidates', []))}개 (등록일·조회 기간 확인 전 장애 단정 금지)",
        ])
        for gap in runtime.get("schedule_silence_candidates", [])[:12]:
            lines.append(
                f"  - {gap['path']}: {gap['reason']}"
                f" · 확인 허용간격 {gap['max_gap_hours']}시간"
                f" · 마지막 관측 {gap.get('hours_since_run') if gap.get('hours_since_run') is not None else '자료 없음'}"
            )
        for row in runtime["failure_clusters"][:12]:
            lines.append(
                f"  - {row['path']}: 실패 {row['failures']} · 취소 {row['cancelled']}"
                f" · 최신 전체 {row['latest_event']}/{row['latest_conclusion']}"
                f" · 마지막 예약 {row['latest_schedule_conclusion']}"
                f" · {row['latest_url']}"
            )
    lines += [
        "- 주의: 이 진단은 실제 전송 성공·상태 파일 갱신까지 입증하지 않음. 개별 message_id/로그는 별도 대조 필요.",
        "- 대상 워크플로의 설정·예약·전송·상태 파일을 수정하지 않음.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    ap.add_argument("--runs", type=pathlib.Path)
    ap.add_argument("--workflows", type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path, default=pathlib.Path("out/alert_operations_audit.json"))
    ap.add_argument("--markdown", type=pathlib.Path, default=pathlib.Path("out/alert_operations_audit.md"))
    args = ap.parse_args()
    static = audit_static(args.root)
    runtime = audit_runtime(
        parse_jsonl(args.runs), parse_jsonl(args.workflows),
        known_paths=set(static["workflow_paths"]),
        schedule_max_gap_hours=static["schedule_max_gap_hours"],
    ) if args.runs and args.workflows else None
    result = {"static": static, "runtime": runtime, "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(make_markdown(static, runtime), encoding="utf-8")
    print(f"alert_operations_audit workflows={static['workflow_files']} scheduled={static['scheduled_files']} runtime_runs={len(parse_jsonl(args.runs)) if args.runs else 'not_checked'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Distinguish unavailable sources from verified documents awaiting review."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
DATA_DIR = Path("data")
FAILURES_PATH = OUT_DIR / "khs_source_failures.json"
SEEN_PATH = DATA_DIR / "khs_source_failure_seen.json"
TITLE_PATH = OUT_DIR / "khs_policy_source_status_title.txt"
BODY_PATH = OUT_DIR / "khs_policy_source_status_alert.md"
SINGLE_SOURCE_MIN_STREAK = int(os.getenv("KHS_SOURCE_STATUS_SINGLE_SOURCE_MIN_STREAK", "2"))
MULTI_SOURCE_MIN_FAILURES = int(os.getenv("KHS_SOURCE_STATUS_MULTI_SOURCE_MIN_FAILURES", "3"))
MULTI_SOURCE_MIN_STREAK = int(os.getenv("KHS_SOURCE_STATUS_MULTI_SOURCE_MIN_STREAK", "2"))
STREAK_WINDOW_HOURS = int(os.getenv("KHS_SOURCE_STATUS_STREAK_WINDOW_HOURS", "8"))


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_seen(seen: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fingerprint(failures: list[dict], day: str) -> str:
    material = "\n".join(
        sorted(item.get("logical_key") or logical_failure_key(item) for item in failures)
    )
    return hashlib.sha256(f"{day}\n{material}".encode("utf-8")).hexdigest()[:16]


def failure_key(item: dict) -> str:
    return f"{item.get('lane')}|{item.get('source')}|{item.get('url')}"


def failure_kind(item: dict) -> str:
    kind = str(item.get("failure_kind") or "")
    if kind in {"content_review", "publication_unverified"}:
        return kind
    # Older checkpoints did not carry a typed outcome.
    source = str(item.get("source") or "").lower()
    error = str(item.get("error") or "").lower()
    if "material conditions" in source or "material conditions differ" in error:
        return "content_review"
    if "public-inspection fallback is not publication" in error:
        return "publication_unverified"
    return "source_unavailable"


def source_domain(url: object) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except Exception:
        return ""
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def logical_failure_key(item: dict) -> str:
    lane = str(item.get("lane") or "unknown_lane").strip().lower()
    domain = source_domain(item.get("url"))
    if domain:
        key = f"{lane}|{domain}"
        # Review of a fetched document is not an outage of the same host.
        kind = failure_kind(item)
        if kind != "source_unavailable":
            key += f"|{kind}|{urllib.parse.urlparse(str(item.get('url') or '')).path}"
        return key
    source = " ".join(str(item.get("source") or "").lower().split())
    return f"{lane}|{source or 'unknown_source'}"


def collapse_logical_failures(failures: list[dict]) -> list[dict]:
    collapsed: dict[str, dict] = {}
    for item in failures:
        key = logical_failure_key(item)
        current = collapsed.get(key)
        if current is None:
            current = dict(item)
            current["logical_key"] = key
            current["related_sources"] = [item.get("source")]
            current["related_urls"] = [item.get("url")]
            collapsed[key] = current
            continue
        source = item.get("source")
        url = item.get("url")
        if source and source not in current.setdefault("related_sources", []):
            current["related_sources"].append(source)
        if url and url not in current.setdefault("related_urls", []):
            current["related_urls"].append(url)
    return list(collapsed.values())


def parse_kst(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def update_streaks(seen: dict, failures: list[dict], now: dt.datetime) -> int:
    streaks = seen.setdefault("failure_streaks", {})
    max_streak = 0
    window = dt.timedelta(hours=max(1, STREAK_WINDOW_HOURS))

    for item in failures:
        key = item.get("logical_key") or logical_failure_key(item)
        previous = streaks.get(key, {}) if isinstance(streaks.get(key), dict) else {}
        previous_seen = parse_kst(previous.get("last_seen_kst"))
        previous_streak = int(previous.get("streak", 0) or 0)
        if previous_seen and previous_seen.date() == now.date() and now - previous_seen <= window:
            streak = previous_streak + 1
        else:
            streak = 1
        streaks[key] = {
            "streak": streak,
            "last_seen_kst": now.isoformat(timespec="seconds"),
            "source": item.get("source"),
            "lane": item.get("lane"),
        }
        max_streak = max(max_streak, streak)

    for key, value in list(streaks.items()):
        last_seen = parse_kst(value.get("last_seen_kst") if isinstance(value, dict) else None)
        if not last_seen or now - last_seen > window:
            streaks.pop(key, None)

    return max_streak


def current_min_streak(seen: dict, failures: list[dict]) -> int:
    streaks = seen.get("failure_streaks", {})
    values = []
    for item in failures:
        key = item.get("logical_key") or logical_failure_key(item)
        value = streaks.get(key, {}) if isinstance(streaks.get(key), dict) else {}
        values.append(int(value.get("streak", 0) or 0))
    return min(values) if values else 0


def should_alert(failures: list[dict], max_streak: int, min_streak: int) -> tuple[bool, str]:
    if len(failures) >= max(1, MULTI_SOURCE_MIN_FAILURES):
        return True, "broad_source_outage"
    if len(failures) >= 2:
        if min_streak >= max(1, MULTI_SOURCE_MIN_STREAK):
            return True, "repeated_multiple_sources"
        if max_streak >= max(1, SINGLE_SOURCE_MIN_STREAK):
            return True, "repeated_single_source"
        return False, "multiple_transient_sources"
    if max_streak >= max(1, SINGLE_SOURCE_MIN_STREAK):
        return True, "repeated_single_source"
    return False, "single_transient_source"


def clear_streaks_if_needed() -> None:
    seen = load_json(SEEN_PATH, {"seen": {}})
    if seen.get("failure_streaks"):
        seen["failure_streaks"] = {}
        save_seen(seen)
        print("source_status_alert=cleared_failure_streaks")


def render(failures: list[dict], now: dt.datetime) -> tuple[str, str]:
    time_label = now.strftime("%Y년 %m월 %d일 %H:%M KST")
    groups = collapse_logical_failures(failures)
    has_outage = any(failure_kind(item) == "source_unavailable" for item in groups)
    has_review = any(failure_kind(item) != "source_unavailable" for item in groups)
    title = "정책 워치: " + (
        "원문 검증·소스 접속 상태 점검" if has_outage and has_review
        else "일부 공식 소스 접속 지연" if has_outage
        else "공식 원문 재검증 필요"
    )
    scope_names = {
        "domestic_telecom": "국내 통신정책",
        "domestic_stablecoin": "국내 스테이블코인·디지털자산 정책",
        "trusted_policy": "국외 정책 원문·신뢰외신",
    }
    lanes = {str(item.get("lane") or "") for item in groups}
    scope = " / ".join(scope_names.get(lane, lane or "해당 감시 항목") for lane in sorted(lanes))
    lines = [
        f"정책 워치 점검 · {time_label}",
        "",
        "접속 실패와 원문 검증 보류를 구분한 감시 상태 알림입니다.",
        "정책 뉴스 전체가 없거나 감시 전체가 중단됐다는 뜻은 아닙니다.",
        "",
        f"- 점검 범위: {scope}",
        "- 송출 기준: 같은 점검 항목은 하루 1회만 알림",
        "",
    ]
    for idx, item in enumerate(groups[:8], start=1):
        source = item.get("source") or "해당 소스"
        if source_domain(item.get("url")) == "fsc.go.kr":
            source = "금융위원회 공식 게시판"
        elif str(source).startswith("BIS remote rule"):
            source = "미 BIS 반도체 원격접근 규칙"
        url = item.get("url") or ""
        error = str(item.get("error") or "").lower()
        checked = item.get("checked_at_kst") or "조회시각 확인 필요"
        kind = failure_kind(item)
        if kind == "content_review":
            status = "원문 수집 완료·세부 조건 재검증 필요"
            reason = "검증한 기준본과 문안이 일치하지 않습니다. 정책 변경 확정이나 접속 실패로 단정하지 않습니다."
            action = "원문 조항을 대조할 때까지 기존 숫자·대상·예외를 재사용하지 않습니다."
        elif kind == "publication_unverified":
            status = "공개열람본 확인·정식 관보 게재 확인 보류"
            reason = "공개열람본만 확인된 상태입니다. 예정일 경과만으로 정식 게재·발효 처리하지 않습니다."
            action = "정식 관보와 발효일을 별도 재조회합니다."
        else:
            status = "이번 실행에서 접속 실패"
            reason = (
                "응답시간 초과 또는 중계 서버 오류로 원문을 읽지 못했습니다."
                if any(term in error for term in ("timeout", "timed out", "502", "503", "504"))
                else "이번 실행에서 해당 원문을 확인하지 못했습니다."
            )
            action = "다음 정기 실행에서 재조회합니다. 새 정책이 없다고 판단하지 않습니다."
            tried = []
            if "direct " in error:
                tried.append("직접 조회")
            if "proxy " in error:
                tried.append("설정된 프록시")
            if tried:
                action = " / ".join(tried) + " 확인 실패. " + action
        lines.extend(
            [
                f"{idx}. {source}",
                f"- 상태: {status}",
                f"- 조회시각: {checked}",
                f"- 사유: {reason}",
                f"- 처리: {action}",
                f"- 출처: [원문]({url})",
                "",
            ]
        )
        count = len(item.get("related_sources") or [])
        if count > 1:
            lines.insert(len(lines) - 1, f"- 묶인 조회: 같은 기관의 검색·게시판 {count}개")
    if len(groups) > 8:
        lines.append(f"- 추가 점검 항목: {len(groups) - 8}건")
    lines.append("세부 오류와 요청 주소는 실행 로그에 보존합니다. 이 알림은 정책 시행·변경 발표가 아닙니다.")
    return title, "\n".join(lines)


def main() -> int:
    for path in (TITLE_PATH, BODY_PATH):
        path.unlink(missing_ok=True)
    failures = load_json(FAILURES_PATH, [])
    if not failures:
        clear_streaks_if_needed()
        return 0
    failures = [item for item in failures if isinstance(item, dict)]
    if not failures:
        clear_streaks_if_needed()
        return 0

    now = now_kst()
    day = now.strftime("%Y-%m-%d")
    seen = load_json(SEEN_PATH, {"seen": {}})
    decision_failures = collapse_logical_failures(failures)
    max_streak = update_streaks(seen, decision_failures, now)
    min_streak = current_min_streak(seen, decision_failures)
    outages = [item for item in decision_failures if failure_kind(item) == "source_unavailable"]
    reviews = [item for item in decision_failures if failure_kind(item) != "source_unavailable"]

    def streak(item: dict) -> int:
        return int(seen.get("failure_streaks", {}).get(item["logical_key"], {}).get("streak", 0))

    alert_ok, alert_reason = should_alert(
        outages, max((streak(item) for item in outages), default=0), current_min_streak(seen, outages)
    )
    if reviews:
        alert_ok, alert_reason = True, "verified_document_review"
        decision_failures = reviews + [
            item for item in outages
            if len(outages) >= max(1, MULTI_SOURCE_MIN_FAILURES)
            or streak(item) >= max(1, SINGLE_SOURCE_MIN_STREAK)
        ]
    if not alert_ok:
        save_seen(seen)
        print(
            f"source_status_alert=skipped_{alert_reason} "
            f"failures={len(failures)} logical_failures={len(decision_failures)} "
            f"max_streak={max_streak} min_streak={min_streak}"
        )
        return 0

    seen_map = seen.setdefault("seen", {})
    notified_keys = set()
    legacy_sources = set()
    for previous in seen_map.values():
        if str(previous.get("first_seen_kst") or "")[:10] == day:
            notified_keys.update(previous.get("logical_keys") or [])
            if not previous.get("logical_keys"):
                legacy_sources.update(previous.get("sources") or [])
    decision_failures = [
        item for item in decision_failures
        if item["logical_key"] not in notified_keys
        and not set(item.get("related_sources") or []).intersection(legacy_sources)
    ]
    if not decision_failures:
        save_seen(seen)
        print(f"source_status_alert=skipped_duplicate failures={len(failures)}")
        return 0
    fp = fingerprint(decision_failures, day)
    if fp in seen_map:
        save_seen(seen)
        print(f"source_status_alert=skipped_duplicate failures={len(failures)}")
        return 0

    selected_keys = {item["logical_key"] for item in decision_failures}
    selected = [item for item in failures if logical_failure_key(item) in selected_keys]
    title, body = render(selected, now)
    OUT_DIR.mkdir(exist_ok=True)
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    BODY_PATH.write_text(body + "\n", encoding="utf-8")

    seen_map[fp] = {
        "first_seen_kst": now.isoformat(timespec="seconds"),
        "failure_count": len(failures),
        "logical_failure_count": len(decision_failures),
        "sources": [item.get("source") for item in selected],
        "logical_keys": sorted(selected_keys),
    }
    if len(seen_map) > 60:
        for key in list(seen_map.keys())[:-60]:
            seen_map.pop(key, None)
    save_seen(seen)
    print(f"source_status_alert=created failures={len(failures)}")
    return 0


def run_yen_carry_bridge() -> int:
    try:
        from yen_carry_khs_bridge import main as bridge_main

        return bridge_main()
    except Exception as exc:
        print(f"yen_carry_bridge_error={type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    source_status_result = main()
    bridge_result = run_yen_carry_bridge()
    raise SystemExit(source_status_result or bridge_result)

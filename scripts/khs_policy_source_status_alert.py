#!/usr/bin/env python3
"""Render a throttled Telegram notice when KHS official sources are unreachable."""

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
MULTI_SOURCE_MIN_FAILURES = int(os.getenv("KHS_SOURCE_STATUS_MULTI_SOURCE_MIN_FAILURES", "2"))
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
        return f"{lane}|{domain}"
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

    # Keep stale streak state from making a future one-off timeout look consecutive.
    for key, value in list(streaks.items()):
        last_seen = parse_kst(value.get("last_seen_kst") if isinstance(value, dict) else None)
        if not last_seen or now - last_seen > window:
            streaks.pop(key, None)

    return max_streak


def should_alert(failures: list[dict], max_streak: int) -> tuple[bool, str]:
    if len(failures) >= max(1, MULTI_SOURCE_MIN_FAILURES):
        return True, "multiple_sources"
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
    day = now.strftime("%Y-%m-%d")
    time_label = now.strftime("%Y년 %m월 %d일 %H:%M KST")
    title = "KHS 정책 워치: 국내 공식 소스 확인 불가"
    lines = [
        f"⚠️ KHS 정책 워치 소스 점검 알림 · {time_label}",
        "",
        "국내 정책 공식 소스 일부가 GitHub Actions 실행환경에서 확인되지 않았습니다.",
        "이번 실행의 `0건`은 순수한 뉴스 부재가 아니라 `확인 불가`가 섞인 상태입니다.",
        "",
        "- 상태: 확인 불가",
        "- 영향: 국내 통신비, 스테이블코인/디지털자산 등 국내 정책 라인 감시 공백 가능",
        "- 처리: 직접 조회 실패 후 Cloudflare 공식소스 프록시 fallback까지 시도",
        "- 송출 기준: 같은 실패 묶음은 하루 1회만 알림",
        "",
        "실패 소스:",
    ]
    for idx, item in enumerate(failures[:8], start=1):
        source = item.get("source") or "unknown source"
        lane = item.get("lane") or "unknown lane"
        url = item.get("url") or ""
        error = item.get("error") or "unknown error"
        checked = item.get("checked_at_kst") or day
        lines.extend(
            [
                f"{idx}. {source}",
                f"- 라인: {lane}",
                f"- 상태: 확인 불가",
                f"- 조회시각: {checked}",
                f"- 오류: {error[:260]}",
                f"- 원문: {url}",
            ]
        )
    if len(failures) > 8:
        lines.append(f"- 추가 실패 소스: {len(failures) - 8}건")

    lines.extend(
        [
            "",
            "판단: 이 알림은 투자 뉴스가 아니라 감시 품질 알림입니다. 국내 정책 뉴스가 없다고 단정하지 말고 다음 정상 조회 때 재확인해야 합니다.",
        ]
    )
    return title, "\n".join(lines)


def main() -> int:
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
    alert_ok, alert_reason = should_alert(decision_failures, max_streak)
    if not alert_ok:
        save_seen(seen)
        print(
            f"source_status_alert=skipped_{alert_reason} "
            f"failures={len(failures)} logical_failures={len(decision_failures)} max_streak={max_streak}"
        )
        return 0

    fp = fingerprint(decision_failures, day)
    seen_map = seen.setdefault("seen", {})
    if fp in seen_map:
        save_seen(seen)
        print(f"source_status_alert=skipped_duplicate failures={len(failures)}")
        return 0

    title, body = render(failures, now)
    OUT_DIR.mkdir(exist_ok=True)
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    BODY_PATH.write_text(body + "\n", encoding="utf-8")

    seen_map[fp] = {
        "first_seen_kst": now.isoformat(timespec="seconds"),
        "failure_count": len(failures),
        "logical_failure_count": len(decision_failures),
        "sources": [item.get("source") for item in failures],
    }
    # Keep the state small while preserving recent dedupe history.
    if len(seen_map) > 60:
        for key in list(seen_map.keys())[:-60]:
            seen_map.pop(key, None)
    save_seen(seen)
    print(f"source_status_alert=created failures={len(failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

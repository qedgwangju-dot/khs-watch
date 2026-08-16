#!/usr/bin/env python3
"""Track Silver Bulletin Trump issue net-approval averages and emit Telegram-ready alerts.

The watcher reads the issue charts embedded in Silver Bulletin's Trump approval page,
tries the published Datawrapper dataset.csv endpoints, and compares the latest issue
values with the last successfully delivered snapshot.
"""
from __future__ import annotations

import csv
import datetime as dt
import html as html_lib
import io
import json
import os
import pathlib
import re
import urllib.error
import urllib.request
from typing import Dict, Iterable, List, Optional, Tuple

SILVER_URL = "https://www.natesilver.net/p/trump-approval-ratings-nate-silver-bulletin"
STATE_PATH = pathlib.Path("data/silver_bulletin_issue_state.json")
OUT_DIR = pathlib.Path("out")
ALERT_PATH = OUT_DIR / "silver_bulletin_issue_alert.md"
STATUS_PATH = OUT_DIR / "silver_bulletin_issue_status.md"
PENDING_PATH = OUT_DIR / "silver_bulletin_issue_state_pending.json"
ERROR_PATH = OUT_DIR / "silver_bulletin_issue_errors.log"

# Current published issue-area chart URLs as a fallback only. The primary path is
# to rediscover the live iframes from SILVER_URL on every run.
FALLBACK_CHARTS = [
    "https://datawrapper.dwcdn.net/AdipN/76/",
    "https://datawrapper.dwcdn.net/RFXsV/73/",
    "https://datawrapper.dwcdn.net/wWI2Y/70/",
]

ISSUES = {
    "economy": {
        "ko": "경제",
        "aliases": ["economy", "economic"],
    },
    "immigration": {
        "ko": "이민",
        "aliases": ["immigration", "immigrant", "border"],
    },
    "trade": {
        "ko": "무역·관세",
        "aliases": ["trade and tariffs", "trade & tariffs", "trade/tariffs", "trade", "tariff", "tariffs"],
    },
    "cost_of_living": {
        "ko": "물가·생활비",
        "aliases": ["cost of living", "inflation/prices", "inflation", "prices", "price", "living costs"],
    },
}

DATE_HINTS = ("date", "day", "time", "fieldwork", "end")
VALUE_HINTS = ("net", "net approval", "net_approval", "value", "average", "avg", "rating", "margin")
APPROVE_HINTS = ("approve", "approval", "positive")
DISAPPROVE_HINTS = ("disapprove", "disapproval", "negative")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def fetch_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": os.getenv(
                "SILVER_BULLETIN_USER_AGENT",
                "Mozilla/5.0 (compatible; KHS-Silver-Bulletin-Watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)",
            ),
            "Accept": "text/html,application/xhtml+xml,text/csv,text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def normalize(text: object) -> str:
    value = html_lib.unescape(str(text or ""))
    value = value.replace("\u2212", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def parse_number(value: object) -> Optional[float]:
    text = normalize(value).replace(",", "")
    if not text or text in {"na", "n/a", "null", "none", "-"}:
        return None
    # Avoid treating dates like 2026-08-07 as a metric.
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
        return None
    m = re.search(r"(?<!\d)([-+]?\d+(?:\.\d+)?)(?:\s*%)?", text)
    if not m:
        return None
    try:
        value_f = float(m.group(1))
    except ValueError:
        return None
    # Net issue approval should be a percentage-point value, not a year/index.
    if abs(value_f) > 100:
        return None
    return value_f


def parse_date(value: object) -> Optional[dt.datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text, text.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            pass
    for fmt in (
        "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d %H:%M:%S"
    ):
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
    return None


def match_issue(text: object) -> Optional[str]:
    norm = normalize(text)
    if not norm:
        return None
    # More specific labels first to keep "prices" from matching unrelated prose.
    for key in ("cost_of_living", "immigration", "trade", "economy"):
        for alias in ISSUES[key]["aliases"]:
            a = normalize(alias)
            if norm == a or re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", norm):
                return key
    return None


def discover_datawrapper_charts(page_html: str) -> List[str]:
    unescaped = html_lib.unescape(page_html)
    # Restrict to the issue section when headings are present.
    lower = unescaped.lower()
    start = lower.find("the issues")
    end = lower.find("the deep dive", start + 1) if start >= 0 else -1
    section = unescaped[start:end if end > start else None] if start >= 0 else unescaped

    urls = []
    patterns = [
        r"https?://datawrapper\.dwcdn\.net/[A-Za-z0-9]+/\d+/?",
        r"//datawrapper\.dwcdn\.net/[A-Za-z0-9]+/\d+/?",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, section):
            url = match
            if url.startswith("//"):
                url = "https:" + url
            if not url.endswith("/"):
                url += "/"
            if url not in urls:
                urls.append(url)
    return urls


def read_csv_rows(text: str) -> Tuple[List[str], List[Dict[str, str]]]:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    rows = []
    for row in reader:
        clean = {str(k): ("" if v is None else str(v)) for k, v in row.items() if k is not None}
        if any(v.strip() for v in clean.values()):
            rows.append(clean)
    return headers, rows


def row_timestamp(row: Dict[str, str], headers: List[str], fallback_index: int) -> Tuple[float, str]:
    for h in headers:
        if any(token in normalize(h) for token in DATE_HINTS):
            parsed = parse_date(row.get(h))
            if parsed:
                return parsed.timestamp(), parsed.date().isoformat()
    # Look for date-like values even if the column is generically named.
    for h in headers:
        parsed = parse_date(row.get(h))
        if parsed:
            return parsed.timestamp(), parsed.date().isoformat()
    return float(fallback_index), ""


def pick_net_value(row: Dict[str, str], headers: List[str], label_header: Optional[str] = None) -> Optional[float]:
    # Prefer an explicit net/average/value field.
    scored = []
    for h in headers:
        if h == label_header:
            continue
        hn = normalize(h)
        score = 0
        if "net" in hn:
            score += 20
        if any(hint == hn or hint in hn for hint in VALUE_HINTS):
            score += 8
        if any(token in hn for token in DATE_HINTS):
            score -= 20
        value = parse_number(row.get(h))
        if value is not None:
            scored.append((score, h, value))
    if scored:
        scored.sort(reverse=True, key=lambda item: item[0])
        if scored[0][0] > 0:
            return scored[0][2]

    # If approval and disapproval are available, calculate the net directly.
    approve = disapprove = None
    for h in headers:
        hn = normalize(h)
        if approve is None and any(token in hn for token in APPROVE_HINTS) and "dis" not in hn:
            approve = parse_number(row.get(h))
        if disapprove is None and any(token in hn for token in DISAPPROVE_HINTS):
            disapprove = parse_number(row.get(h))
    if approve is not None and disapprove is not None:
        return round(approve - disapprove, 3)
    return None


def extract_issue_values(headers: List[str], rows: List[Dict[str, str]]) -> Dict[str, Dict[str, object]]:
    found: Dict[str, Dict[str, object]] = {}

    # Wide form: issue names are columns, dates are rows.
    for h in headers:
        issue = match_issue(h)
        if not issue:
            continue
        for idx, row in enumerate(rows):
            value = parse_number(row.get(h))
            if value is None:
                continue
            ts, date_label = row_timestamp(row, headers, idx)
            candidate = {"value": value, "timestamp": ts, "date": date_label, "mode": "wide", "field": h}
            if issue not in found or ts >= float(found[issue].get("timestamp", -1)):
                found[issue] = candidate

    # Long form: one column carries the issue label, another carries net/value.
    for label_h in headers:
        matched_rows = [(idx, row, match_issue(row.get(label_h))) for idx, row in enumerate(rows)]
        matched_rows = [(idx, row, issue) for idx, row, issue in matched_rows if issue]
        if not matched_rows:
            continue
        for idx, row, issue in matched_rows:
            assert issue is not None
            value = pick_net_value(row, headers, label_header=label_h)
            if value is None:
                continue
            ts, date_label = row_timestamp(row, headers, idx)
            candidate = {"value": value, "timestamp": ts, "date": date_label, "mode": "long", "field": label_h}
            if issue not in found or ts >= float(found[issue].get("timestamp", -1)):
                found[issue] = candidate

    return found


def load_state() -> Dict[str, object]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def fmt_value(value: float) -> str:
    return f"{value:+.1f}%p"


def build_message(previous: Dict[str, object], current: Dict[str, Dict[str, object]], charts: List[str]) -> str:
    prev_values = previous.get("values") if isinstance(previous, dict) else {}
    if not isinstance(prev_values, dict):
        prev_values = {}

    first_run = not prev_values
    lines = [
        "[Silver Bulletin 트럼프 이슈 지지율 감시] " + ("Telegram 연결 완료" if first_run else "변화 감지"),
        "",
    ]
    deltas: List[Tuple[float, str, float]] = []
    for key in ("cost_of_living", "economy", "immigration", "trade"):
        if key not in current:
            continue
        label = ISSUES[key]["ko"]
        value = float(current[key]["value"])
        prev_raw = prev_values.get(key)
        if isinstance(prev_raw, dict):
            prev_raw = prev_raw.get("value")
        try:
            prev = float(prev_raw) if prev_raw is not None else None
        except (TypeError, ValueError):
            prev = None
        if prev is None:
            lines.append(f"- {label}: {fmt_value(value)}")
        else:
            delta = value - prev
            deltas.append((abs(delta), label, delta))
            lines.append(f"- {label}: {fmt_value(prev)} → {fmt_value(value)} ({delta:+.1f}%p)")

    if deltas:
        _, label, delta = max(deltas, key=lambda item: item[0])
        direction = "개선" if delta > 0 else "악화" if delta < 0 else "변화 없음"
        lines.extend(["", f"→ 가장 큰 변화: {label} {abs(delta):.1f}%p {direction}"])
    elif first_run:
        lines.extend(["", "→ 현재 수치를 기준값으로 저장했습니다. 이후 값이 바뀔 때만 알립니다."])

    lines.extend(["", f"- 원문: {SILVER_URL}"])
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (ALERT_PATH, PENDING_PATH, ERROR_PATH):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    errors: List[str] = []
    page_html = ""
    charts: List[str] = []
    try:
        page_html = fetch_text(SILVER_URL)
        charts = discover_datawrapper_charts(page_html)
    except Exception as exc:  # network failures are reported, not guessed through
        errors.append(f"Silver page fetch failed: {type(exc).__name__}: {exc}")

    if not charts:
        charts = list(FALLBACK_CHARTS)

    all_values: Dict[str, Dict[str, object]] = {}
    chart_results = []
    for base in charts:
        dataset_url = base.rstrip("/") + "/dataset.csv"
        try:
            csv_text = fetch_text(dataset_url)
            headers, rows = read_csv_rows(csv_text)
            values = extract_issue_values(headers, rows)
            chart_results.append(
                {
                    "chart": base,
                    "dataset": dataset_url,
                    "headers": headers[:30],
                    "rows": len(rows),
                    "issues": sorted(values),
                }
            )
            for issue, candidate in values.items():
                current = all_values.get(issue)
                if current is None or float(candidate.get("timestamp", -1)) >= float(current.get("timestamp", -1)):
                    candidate = dict(candidate)
                    candidate["chart"] = base
                    all_values[issue] = candidate
        except Exception as exc:
            errors.append(f"{dataset_url}: {type(exc).__name__}: {exc}")

    # We require at least 3 of the four advertised topics so a random poll table can
    # never be mistaken for the issue-average chart. Normally all 4 are present.
    if len(all_values) < 3:
        status = {
            "status": "parse_failed",
            "checked_at_utc": now_utc().isoformat(),
            "source": SILVER_URL,
            "charts": charts,
            "chart_results": chart_results,
            "issues_found": sorted(all_values),
        }
        STATUS_PATH.write_text(
            "Silver Bulletin 이슈 지지율 감시: 확인 불가\n\n"
            f"- 확인된 이슈 수: {len(all_values)}/4\n"
            "- 기존 기준값은 변경하지 않았고 Telegram 알림도 보내지 않습니다.\n",
            encoding="utf-8",
        )
        ERROR_PATH.write_text("\n".join(errors + [json.dumps(status, ensure_ascii=False, indent=2)]) + "\n", encoding="utf-8")
        return 2

    previous = load_state()
    prev_values = previous.get("values") if isinstance(previous, dict) else {}
    if not isinstance(prev_values, dict):
        prev_values = {}

    changed = not prev_values
    if prev_values:
        for key, payload in all_values.items():
            prev_raw = prev_values.get(key)
            if isinstance(prev_raw, dict):
                prev_raw = prev_raw.get("value")
            try:
                prev_num = float(prev_raw)
            except (TypeError, ValueError):
                changed = True
                break
            if abs(float(payload["value"]) - prev_num) >= 0.05:
                changed = True
                break

    checked_at = now_utc().isoformat()
    compact_values = {
        key: {
            "value": round(float(payload["value"]), 3),
            "date": str(payload.get("date") or ""),
            "chart": str(payload.get("chart") or ""),
        }
        for key, payload in all_values.items()
    }

    if changed:
        pending = {
            "source": SILVER_URL,
            "checked_at_utc": checked_at,
            "values": compact_values,
            "charts": charts,
        }
        PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ALERT_PATH.write_text(build_message(previous, all_values, charts), encoding="utf-8")

    STATUS_PATH.write_text(
        "Silver Bulletin 이슈 지지율 감시\n\n"
        f"- 확인 시각(UTC): {checked_at}\n"
        f"- 확인된 이슈: {', '.join(ISSUES[k]['ko'] for k in all_values if k in ISSUES)}\n"
        f"- 상태: {'초기 기준값/변화 감지' if changed else '변화 없음'}\n"
        f"- Telegram 발송 필요: {'예' if changed else '아니오'}\n",
        encoding="utf-8",
    )
    if errors:
        ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

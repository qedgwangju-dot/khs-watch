#!/usr/bin/env python3
"""Official-source global rates / yen-carry threshold watcher.

Sources
- Japan MOF daily constant-maturity JGB yields (official, published next business day)
- U.S. Treasury daily par yield curve XML (official)
- Federal Reserve Bank of St. Louis FRED DEXJPUS daily USD/JPY (Federal Reserve data)

The script writes:
- out/global_rates_watch_status.md
- out/global_rates_watch_pending_state.json
- out/global_rates_watch_alert.md (only when a threshold newly triggers or clears)
- out/global_rates_watch_alert.json

It does NOT send Telegram itself. Delivery and state persistence are handled by the
GitHub Actions workflow so a failed/missing Telegram delivery cannot consume an alert.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Iterable
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "global_rates_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)

JGB_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
UST_XML_BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
JAPAN_BUDGET_RATE_URL = "https://www.mof.go.jp/policy/budget/topics/outlook/sy2026a.htm"

USER_AGENT = "khs-watch-global-rates/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"


@dataclass
class Point:
    name: str
    date: str
    value: float
    source: str


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text or text.upper() in {"N/A", "NA", "ND", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"last_values": {}, "active": {}, "last_source_dates": {}}
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("state must be object")
        raw.setdefault("last_values", {})
        raw.setdefault("active", {})
        raw.setdefault("last_source_dates", {})
        return raw
    except Exception:
        return {"last_values": {}, "active": {}, "last_source_dates": {}}


def fetch_jgb() -> tuple[Point, Point]:
    raw = http_get(JGB_URL)
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    header_idx = None
    for i, row in enumerate(rows[:10]):
        if row and any(normalize_header(c) == "date" for c in row):
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError("Japan MOF CSV header not found")
    header = [c.strip() for c in rows[header_idx]]
    norm = [normalize_header(c) for c in header]

    def find_col(candidates: Iterable[str]) -> int:
        wanted = {normalize_header(c) for c in candidates}
        for idx, key in enumerate(norm):
            if key in wanted:
                return idx
        raise RuntimeError(f"Japan MOF CSV column not found: {sorted(wanted)}; header={header}")

    date_i = find_col(["Date"])
    y2_i = find_col(["2Y", "2 year", "2-year", "2"])
    y10_i = find_col(["10Y", "10 year", "10-year", "10"])

    latest = None
    for row in rows[header_idx + 1 :]:
        if not row or len(row) <= max(date_i, y2_i, y10_i):
            continue
        y2, y10 = to_float(row[y2_i]), to_float(row[y10_i])
        date_text = row[date_i].strip()
        if date_text and y2 is not None and y10 is not None:
            latest = (date_text, y2, y10)
    if latest is None:
        raise RuntimeError("Japan MOF CSV had no complete 2Y/10Y row")
    d, y2, y10 = latest
    return (
        Point("jgb2", d, y2, JGB_URL),
        Point("jgb10", d, y10, JGB_URL),
    )


def fetch_ust_curve(data_key: str = "daily_treasury_yield_curve") -> dict[str, Point]:
    year = dt.datetime.now(KST).year
    params = urllib.parse.urlencode({"data": data_key, "field_tdr_date_value": str(year)})
    url = f"{UST_XML_BASE}?{params}"
    root = ET.fromstring(http_get(url))
    records: list[dict[str, str]] = []
    for entry in root.iter():
        if localname(entry.tag) != "entry":
            continue
        props = None
        for node in entry.iter():
            if localname(node.tag) == "properties":
                props = node
                break
        if props is None:
            continue
        rec: dict[str, str] = {}
        for child in list(props):
            rec[localname(child.tag)] = (child.text or "").strip()
        if rec:
            records.append(rec)
    if not records:
        raise RuntimeError(f"U.S. Treasury XML had no entries for {data_key}")

    def parse_date(rec: dict[str, str]) -> dt.datetime:
        raw = rec.get("NEW_DATE") or rec.get("QUOTE_DATE") or ""
        raw = raw.replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(raw)
        except Exception:
            return dt.datetime.min

    records.sort(key=parse_date)
    rec = records[-1]
    raw_date = rec.get("NEW_DATE") or rec.get("QUOTE_DATE") or ""
    date_text = raw_date[:10] if len(raw_date) >= 10 else raw_date

    out: dict[str, Point] = {}
    for key, name in [("BC_2YEAR", "ust2"), ("BC_10YEAR", "ust10"), ("BC_30YEAR", "ust30")]:
        val = to_float(rec.get(key))
        if val is not None:
            out[name] = Point(name, date_text, val, url)
    if not {"ust2", "ust10", "ust30"}.issubset(out):
        raise RuntimeError(f"U.S. Treasury XML missing required tenors: keys={sorted(rec)}")
    return out


def fetch_fred_series(series_id: str, max_rows: int = 10) -> list[tuple[str, float]]:
    params = urllib.parse.urlencode({"id": series_id})
    url = f"{FRED_CSV}?{params}"
    text = http_get(url).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[tuple[str, float]] = []
    for row in reader:
        val = to_float(row.get(series_id))
        date_text = (row.get("DATE") or row.get("observation_date") or "").strip()
        if date_text and val is not None:
            rows.append((date_text, val))
    if not rows:
        raise RuntimeError(f"FRED series {series_id} returned no observations")
    return rows[-max_rows:]


def pct_change(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def render_level(level: float) -> str:
    text = f"{level:.2f}"
    return text.rstrip("0").rstrip(".")


def main() -> int:
    now = dt.datetime.now(KST)
    errors: list[str] = []
    points: dict[str, Point] = {}

    try:
        jgb2, jgb10 = fetch_jgb()
        points[jgb2.name] = jgb2
        points[jgb10.name] = jgb10
    except Exception as e:
        errors.append(f"Japan MOF: {type(e).__name__}: {e}")

    try:
        points.update(fetch_ust_curve())
    except Exception as e:
        errors.append(f"U.S. Treasury: {type(e).__name__}: {e}")

    usdjpy_rows: list[tuple[str, float]] = []
    try:
        usdjpy_rows = fetch_fred_series("DEXJPUS", max_rows=5)
        d, v = usdjpy_rows[-1]
        points["usdjpy"] = Point("usdjpy", d, v, f"{FRED_CSV}?id=DEXJPUS")
    except Exception as e:
        errors.append(f"FRED DEXJPUS: {type(e).__name__}: {e}")

    required = {"jgb2", "jgb10", "ust2", "ust10", "ust30", "usdjpy"}
    missing = sorted(required - points.keys())
    if missing:
        status = [
            "# 글로벌 금리·엔캐리 감시 상태",
            "",
            f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
            f"- 상태: 확인 불가 — 필수 공식 데이터 누락: {', '.join(missing)}",
        ]
        if errors:
            status += ["", "## 오류"] + [f"- {e}" for e in errors]
        (OUT / "global_rates_watch_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")
        return 2

    state = load_state()
    last_values = dict(state.get("last_values") or {})
    active = dict(state.get("active") or {})
    events: list[dict[str, Any]] = []

    def eval_above(metric: str, levels: list[float], label: str) -> None:
        value = points[metric].value
        prev = to_float(last_values.get(metric))
        for level in levels:
            key = f"{metric}:above:{level}"
            was = bool(active.get(key, (prev is not None and prev >= level)))
            is_now = value >= level
            if is_now and not was:
                events.append({"type": "trigger", "metric": metric, "label": label, "level": level, "value": value})
            elif was and not is_now:
                events.append({"type": "clear", "metric": metric, "label": label, "level": level, "value": value})
            active[key] = is_now

    def eval_below(metric: str, level: float, label: str) -> None:
        value = points[metric].value
        prev = to_float(last_values.get(metric))
        key = f"{metric}:below:{level}"
        was = bool(active.get(key, (prev is not None and prev <= level)))
        is_now = value <= level
        if is_now and not was:
            events.append({"type": "trigger", "metric": metric, "label": label, "level": level, "value": value})
        elif was and not is_now:
            events.append({"type": "clear", "metric": metric, "label": label, "level": level, "value": value})
        active[key] = is_now

    eval_above("jgb10", [3.00], "일본 10년 JGB")
    eval_above("ust10", [4.50, 4.70, 4.75], "미국 10년 국채")
    eval_above("ust30", [5.00, 5.30], "미국 30년 국채")
    eval_below("usdjpy", 155.0, "USD/JPY")

    usd_day_change = None
    if len(usdjpy_rows) >= 2:
        usd_day_change = pct_change(usdjpy_rows[-1][1], usdjpy_rows[-2][1])
        key = "usdjpy:daily_change:below:-2.0"
        was = bool(active.get(key, False))
        is_now = usd_day_change <= -2.0
        if is_now and not was:
            events.append({
                "type": "trigger", "metric": "usdjpy_daily_change", "label": "USD/JPY 1일 변화율",
                "level": -2.0, "value": usd_day_change,
            })
        elif was and not is_now:
            events.append({
                "type": "clear", "metric": "usdjpy_daily_change", "label": "USD/JPY 1일 변화율",
                "level": -2.0, "value": usd_day_change,
            })
        active[key] = is_now

    spread_2y = points["ust2"].value - points["jgb2"].value
    prev_spread = to_float(last_values.get("us_jp_2y_spread"))
    spread_change = None if prev_spread is None else spread_2y - prev_spread
    key = "us_jp_2y_spread:below:2.0"
    was = bool(active.get(key, (prev_spread is not None and prev_spread <= 2.0)))
    is_now = spread_2y <= 2.0
    if is_now and not was:
        events.append({"type": "trigger", "metric": "us_jp_2y_spread", "label": "미·일 2년 금리차", "level": 2.0, "value": spread_2y})
    elif was and not is_now:
        events.append({"type": "clear", "metric": "us_jp_2y_spread", "label": "미·일 2년 금리차", "level": 2.0, "value": spread_2y})
    active[key] = is_now

    jgb_stress = points["jgb10"].value >= 3.0
    us_long_stress = points["ust10"].value >= 4.75 or points["ust30"].value >= 5.30
    yen_jump = points["usdjpy"].value <= 155.0 or (usd_day_change is not None and usd_day_change <= -2.0)
    carry_confirm = jgb_stress and yen_jump and spread_2y <= 2.0

    if carry_confirm:
        classification = "엔캐리 청산 위험 강화"
    elif jgb_stress and yen_jump:
        classification = "엔캐리 청산 경계 — 환율 확인, 금리차는 아직 미충족"
    elif us_long_stress and jgb_stress:
        classification = "미·일 장기채 동시 스트레스"
    elif us_long_stress:
        classification = "미국 장기채 스트레스"
    elif jgb_stress:
        classification = "JGB 재정 경계 — 엔캐리 청산 미확인"
    else:
        classification = "단순 경계"

    pending = {
        "last_values": {
            **{k: p.value for k, p in points.items()},
            "us_jp_2y_spread": spread_2y,
            "usdjpy_daily_change_pct": usd_day_change,
        },
        "active": active,
        "last_source_dates": {k: p.date for k, p in points.items()},
        "classification": classification,
        "updated_at_kst": now.isoformat(timespec="seconds"),
    }
    (OUT / "global_rates_watch_pending_state.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    status_lines = [
        "# 글로벌 금리·엔캐리 감시 상태",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 판정: **{classification}**",
        f"- 일본 10년 JGB: **{points['jgb10'].value:.3f}%** ({points['jgb10'].date})",
        f"- 일본 2년 JGB: **{points['jgb2'].value:.3f}%** ({points['jgb2'].date})",
        f"- 미국 10년 국채: **{points['ust10'].value:.3f}%** ({points['ust10'].date})",
        f"- 미국 30년 국채: **{points['ust30'].value:.3f}%** ({points['ust30'].date})",
        f"- 미국 2년 국채: **{points['ust2'].value:.3f}%** ({points['ust2'].date})",
        f"- 미·일 2년 금리차: **{spread_2y:.3f}%p**" + (f" ({spread_change:+.3f}%p vs 저장값)" if spread_change is not None else ""),
        f"- USD/JPY: **{points['usdjpy'].value:.3f}** ({points['usdjpy'].date})" + (f", 1일 {usd_day_change:+.2f}%" if usd_day_change is not None else ""),
        f"- 신규/해제 이벤트: **{len(events)}건**",
    ]
    if errors:
        status_lines += ["", "## 비필수 오류"] + [f"- {e}" for e in errors]
    (OUT / "global_rates_watch_status.md").write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if not events:
        for p in [OUT / "global_rates_watch_alert.md", OUT / "global_rates_watch_alert.json"]:
            if p.exists():
                p.unlink()
        return 0

    event_lines = []
    for e in events:
        state_ko = "돌파/진입" if e["type"] == "trigger" else "해제/이탈"
        metric = e["metric"]
        if metric == "usdjpy_daily_change":
            event_lines.append(f"- {e['label']} {state_ko}: {e['value']:+.2f}% (경계 {e['level']:+.2f}%)")
        elif metric in {"usdjpy"}:
            event_lines.append(f"- {e['label']} {state_ko}: {e['value']:.3f} (경계 {render_level(e['level'])})")
        elif metric == "us_jp_2y_spread":
            event_lines.append(f"- {e['label']} {state_ko}: {e['value']:.3f}%p (경계 {render_level(e['level'])}%p)")
        else:
            event_lines.append(f"- {e['label']} {state_ko}: {e['value']:.3f}% (경계 {render_level(e['level'])}%)")

    alert_lines = [
        "[글로벌 금리·엔캐리 경보]",
        f"조회시각: {now.strftime('%Y-%m-%d %H:%M:%S')} KST",
        f"판정: {classification}",
        "",
        "변화",
        *event_lines,
        "",
        "현재값",
        f"- 일본 10년 JGB {points['jgb10'].value:.3f}% / 2년 {points['jgb2'].value:.3f}% (MOF {points['jgb10'].date})",
        f"- 미국 10년 {points['ust10'].value:.3f}% / 30년 {points['ust30'].value:.3f}% / 2년 {points['ust2'].value:.3f}% (U.S. Treasury {points['ust10'].date})",
        f"- 미·일 2년 금리차 {spread_2y:.3f}%p",
        f"- USD/JPY {points['usdjpy'].value:.3f}" + (f" / 1일 {usd_day_change:+.2f}%" if usd_day_change is not None else ""),
        "",
        "정확한 의미",
        "- 일본 10년 3.0%: 엔캐리 자동 청산선이나 BOJ 공식 방어선이 아니라 FY2026 일본 정부 예산의 국채 이자비용 계산 가정금리와 겹치는 재정 경계선.",
        "- 미국 10년 4.7%: 공식 'TACO선'이 아님. 4.5%·30년 5.0% 부근은 과거 정책 후퇴 때 시장이 주목했던 경험적 고통구간으로만 취급.",
        "- 엔캐리 청산: JGB 3% 하나로 단정하지 않고 USD/JPY 급락 + 미·일 단기금리차 축소가 같이 확인될 때 위험 강화를 판정.",
        "",
        "시장 연결",
        "- 할인율: 미국 장기금리 상승은 Nasdaq·SOX·XBI·고PER 성장주에 부담.",
        "- 수급: 일본 금리 상승과 엔화 강세가 겹치면 일본 자금의 해외채권 환류 가능성을 점검.",
        "- 시간표: 일본 MOF JGB 금리는 15시 시장 마감값을 다음 영업일 09:30에 공식 공표하므로 실시간 시세가 아닌 공식 일일 확인치.",
        "",
        "공식 출처",
        f"- Japan MOF JGB: {JGB_URL}",
        f"- Japan FY2026 예산금리 참고: {JAPAN_BUDGET_RATE_URL}",
        f"- U.S. Treasury: {points['ust10'].source}",
        f"- Federal Reserve/FRED USDJPY: {points['usdjpy'].source}",
    ]
    text = "\n".join(alert_lines).strip() + "\n"
    (OUT / "global_rates_watch_alert.md").write_text(text, encoding="utf-8")
    (OUT / "global_rates_watch_alert.json").write_text(
        json.dumps({
            "events": events,
            "classification": classification,
            "values": pending["last_values"],
            "source_dates": pending["last_source_dates"],
            "generated_at_kst": now.isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

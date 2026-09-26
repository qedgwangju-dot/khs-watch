#!/usr/bin/env python3
"""BOJ exit-strategy quality overlay for the yen-carry composite monitor.

This layer answers a slow-moving question that the fast USD/JPY lane cannot:
Is the BOJ reducing its JGB footprint in an orderly way while private demand
absorbs the transition, or is the Bank being forced to step back in?

Official sources only:
- BOJ Accounts (every ten days): current JGS holdings and 1m/3m change.
- BOJ Time-Series API / MD09: monthly outright JGB purchases.
- BOJ Time-Series API / FF: selected domestic-private holdings of central
  government securities (banks/depository institutions, insurers/pensions,
  households) when unambiguous official series are available.
- BOJ JGB-purchase plan / official release indexes: plan changes and emergency
  fixed-rate/additional purchase language.

The private-absorption ratio is a heuristic:
selected private-sector increase / absolute BOJ JGS decrease over the same
quarter. It is not a matched-flow identity and can exceed 100% because net
issuance and other holders also move.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import pathlib
import re
import urllib.parse
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text, record_source_failure

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "yen_carry_boj_exit_state.json"
PENDING_PATH = OUT / "yen_carry_boj_exit_pending_state.json"
CONTEXT_JSON = OUT / "yen_carry_boj_exit_context.json"
CONTEXT_MD = OUT / "yen_carry_boj_exit_context.md"
ALERT_TITLE = OUT / "yen_carry_boj_exit_alert_title.txt"
ALERT_BODY = OUT / "yen_carry_boj_exit_alert.md"
ALERT_JSON = OUT / "yen_carry_boj_exit_alert.json"
CONFIRMED = OUT / "yen_carry_boj_exit_telegram_confirmed.json"

COMPOSITE_ALERT_BODY = OUT / "yen_carry_composite_alert.md"
COMPOSITE_ALERT_JSON = OUT / "yen_carry_composite_alert.json"
STRUCTURAL_PENDING = OUT / "yen_carry_structural_pending_state.json"

BOJ_ACCOUNTS_INDEX = "https://www.boj.or.jp/en/statistics/boj/other/acmai/release/{year}/index.htm"
BOJ_POLICY_INDEX = "https://www.boj.or.jp/en/mopo/mpmdeci/state_{year}/index.htm"
BOJ_OPERATION_INDEX = "https://www.boj.or.jp/en/mopo/mpmdeci/ope_col_{year}/index.htm"
BOJ_JGB_PURCHASE_PAGE = "https://www.boj.or.jp/en/mopo/measures/mkt_ope/ope_f/"
BOJ_PLAN_SOURCE = "https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/k260616d.pdf"
BOJ_FOF_SOURCE = "https://www.boj.or.jp/en/statistics/sj/"
BOJ_TS_API = "https://www.stat-search.boj.or.jp/api/v1"

USER_AGENT = "Mozilla/5.0 khs-boj-exit-quality/1.0"
BASE_PLAN_DATE = dt.date(2026, 6, 16)

ACTUAL_OVER_PLAN_RATIO = 1.20
ACTUAL_OVER_PLAN_TRILLION = 0.30
ABSORPTION_WEAK_RATIO = 0.50
JGB_STRESS_LEVEL = 3.0
JGB_STRESS_DAYS = 2


@dataclass(frozen=True)
class AccountPoint:
    date: str
    jgs_trillion_yen: float
    total_assets_trillion_yen: float | None
    url: str


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href: str | None = None
        self.parts: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            self.anchors.append((" ".join(" ".join(self.parts).split()), self.href))
            self.href = None
            self.parts = []


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def number(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("−", "-")
    try:
        out = float(text)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def fetch(url: str, *, accept="text/html,application/json,*/*") -> str:
    text, error = fetch_text(url, USER_AGENT, timeout=20, attempts=2, accept=accept)
    if error or not text:
        raise RuntimeError(error or f"empty response: {url}")
    return text


def record_failure(name: str, url: str, error: Exception | str, now: dt.datetime) -> None:
    record_source_failure(
        lane="yen_carry_boj_exit",
        source_name=name,
        source_url=url,
        error=str(error),
        checked_at=now.astimezone(KST),
    )


def plain(text: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", text or "", flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return " ".join(value.replace("\xa0", " ").split())


def account_release_links(year: int) -> list[tuple[dt.date, str]]:
    url = BOJ_ACCOUNTS_INDEX.format(year=year)
    parser = AnchorParser()
    parser.feed(fetch(url))
    result: list[tuple[dt.date, str]] = []
    for _text, href in parser.anchors:
        full = urllib.parse.urljoin(url, href)
        match = re.search(r"/ac(\d{2})(\d{2})(\d{2})\.htm", full)
        if not match:
            continue
        yy, mm, dd = map(int, match.groups())
        try:
            date = dt.date(2000 + yy, mm, dd)
        except ValueError:
            continue
        result.append((date, full))
    return sorted(set(result), key=lambda item: item[0])


def parse_account_release(date: dt.date, url: str) -> AccountPoint:
    parser = TableParser()
    parser.feed(fetch(url))
    jgs = total = None
    seen_assets_total = False
    for row in parser.rows:
        if len(row) < 2:
            continue
        label = row[0].lower()
        value = number(row[1])
        if value is None:
            continue
        if "japanese government securities" in label and jgs is None:
            jgs = value / 1_000_000_000.0  # thousand yen -> trillion yen
        if label.strip() == "total" and not seen_assets_total:
            total = value / 1_000_000_000.0
            seen_assets_total = True
    if jgs is None:
        raise RuntimeError(f"JGS row missing in BOJ Accounts: {url}")
    return AccountPoint(date=date.isoformat(), jgs_trillion_yen=jgs, total_assets_trillion_yen=total, url=url)


def nearest_on_or_before(points: list[AccountPoint], target: dt.date) -> AccountPoint | None:
    eligible = [p for p in points if dt.date.fromisoformat(p.date) <= target]
    return max(eligible, key=lambda p: p.date) if eligible else None


def fetch_account_history(now: dt.datetime) -> dict:
    year = now.astimezone(KST).year
    links: list[tuple[dt.date, str]] = []
    for y in (year - 1, year):
        try:
            links.extend(account_release_links(y))
        except Exception:
            if y == year:
                raise
    links = sorted(set(links), key=lambda item: item[0])
    if not links:
        raise RuntimeError("BOJ Accounts release links unavailable")

    latest_date, latest_url = links[-1]
    target_dates = [latest_date, latest_date - dt.timedelta(days=30), latest_date - dt.timedelta(days=90)]
    selected: dict[dt.date, str] = {latest_date: latest_url}
    for target in target_dates[1:]:
        eligible = [item for item in links if item[0] <= target]
        if eligible:
            d, u = max(eligible, key=lambda item: item[0])
            selected[d] = u

    points = sorted([parse_account_release(d, u) for d, u in selected.items()], key=lambda p: p.date)
    latest = max(points, key=lambda p: p.date)
    one = nearest_on_or_before(points, latest_date - dt.timedelta(days=30))
    three = nearest_on_or_before(points, latest_date - dt.timedelta(days=90))
    return {
        "latest": asdict(latest),
        "one_month": asdict(one) if one else None,
        "three_month": asdict(three) if three else None,
        "change_1m_trillion_yen": None if one is None else latest.jgs_trillion_yen - one.jgs_trillion_yen,
        "change_3m_trillion_yen": None if three is None else latest.jgs_trillion_yen - three.jgs_trillion_yen,
    }


def walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_dicts(value)


def keymap(row: dict) -> dict:
    return {str(k).upper(): v for k, v in row.items()}


def api_json(path: str, params: dict) -> dict:
    url = BOJ_TS_API + path + "?" + urllib.parse.urlencode(params)
    return json.loads(fetch(url, accept="application/json,*/*"))


def metadata_rows(db: str) -> list[dict]:
    payload = api_json("/getMetadata", {"format": "json", "lang": "en", "db": db})
    rows: list[dict] = []
    seen: set[str] = set()
    for raw in walk_dicts(payload):
        row = keymap(raw)
        code = str(row.get("SERIES_CODE") or "").strip()
        name = str(row.get("NAME_OF_TIME_SERIES") or row.get("NAME_OF_TIMESERIES") or "").strip()
        if code and name and code not in seen:
            seen.add(code)
            rows.append(row)
    if not rows:
        raise RuntimeError(f"BOJ API metadata empty for {db}")
    return rows


def choose_md09_purchase_series(rows: list[dict]) -> dict:
    candidates = []
    for row in rows:
        name = str(row.get("NAME_OF_TIME_SERIES") or "").lower()
        category = str(row.get("CATEGORY") or "").lower()
        freq = str(row.get("FREQUENCY") or "").lower()
        if "japanese government bonds" not in name or "outright purchases" not in name:
            continue
        if freq and "month" not in freq:
            continue
        score = 0
        for token in ("flow", "during month", "changes during", "purchase"):
            if token in name or token in category:
                score += 2
        if "amount outstanding" in name:
            score -= 4
        candidates.append((score, row))
    if not candidates:
        raise RuntimeError("MD09 JGB outright-purchase series not found")
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        names = [str(item[1].get("NAME_OF_TIME_SERIES")) for item in candidates[:5]]
        raise RuntimeError(f"MD09 JGB purchase series ambiguous: {names}")
    return candidates[0][1]


def series_observations(db: str, row: dict, start: str) -> list[tuple[str, float]]:
    code = str(row["SERIES_CODE"])
    payload = api_json(
        "/getDataCode",
        {"format": "json", "lang": "en", "db": db, "startDate": start, "code": code},
    )
    target = None
    for raw in walk_dicts(payload):
        item = keymap(raw)
        if str(item.get("SERIES_CODE") or "") == code and "VALUES" in item:
            target = item
            break
    if target is None:
        raise RuntimeError(f"BOJ API data not found: {db} {code}")
    dates = target.get("SURVEY_DATES")
    values = target.get("VALUES")
    if not isinstance(dates, list) or not isinstance(values, list):
        raise RuntimeError(f"BOJ API data shape unexpected: {db} {code}")
    out: list[tuple[str, float]] = []
    for d, v in zip(dates, values):
        n = number(v)
        if n is not None:
            out.append((str(d), n))
    if not out:
        raise RuntimeError(f"BOJ API series has no numeric observations: {db} {code}")
    return out


def to_trillion(value: float, unit: str) -> float:
    low = unit.lower()
    if "100 million" in low or "100million" in low:
        return value / 10000.0
    if "billion" in low:
        return value / 1000.0
    if "trillion" in low:
        return value
    if "million" in low:
        return value / 1_000_000.0
    raise RuntimeError(f"Unsupported BOJ API unit: {unit}")


def planned_monthly_purchase(period: str) -> float | None:
    try:
        year = int(period[:4])
        month = int(period[-2:])
    except Exception:
        return None
    yyyymm = year * 100 + month
    if 202604 <= yyyymm <= 202606:
        return 2.7
    if 202607 <= yyyymm <= 202609:
        return 2.5
    if 202610 <= yyyymm <= 202612:
        return 2.3
    if 202701 <= yyyymm <= 202703:
        return 2.1
    if yyyymm >= 202704:
        return 2.0
    return None


def fetch_actual_purchases(now: dt.datetime) -> dict:
    rows = metadata_rows("MD09")
    series = choose_md09_purchase_series(rows)
    obs = series_observations("MD09", series, f"{now.astimezone(KST).year - 1}01")
    period, raw = obs[-1]
    actual = to_trillion(raw, str(series.get("UNIT") or ""))
    plan = planned_monthly_purchase(period)
    deviation = None if not plan else actual - plan
    ratio = None if not plan else actual / plan
    return {
        "series_code": series.get("SERIES_CODE"),
        "series_name": series.get("NAME_OF_TIME_SERIES"),
        "unit": series.get("UNIT"),
        "period": period,
        "actual_trillion_yen": actual,
        "planned_trillion_yen": plan,
        "deviation_trillion_yen": deviation,
        "actual_plan_ratio": ratio,
    }


def normalize_period(value: str) -> tuple[int, int] | None:
    nums = re.findall(r"\d+", str(value))
    if len(nums) >= 2:
        y, m = int(nums[0]), int(nums[1])
        if y >= 1900 and 1 <= m <= 12:
            quarter = (m - 1) // 3 + 1
            return y, quarter
    if len(nums) == 1 and len(nums[0]) >= 6:
        text = nums[0]
        y = int(text[:4])
        q = int(text[-2:])
        if 1 <= q <= 4:
            return y, q
    return None


def fof_candidate(rows: list[dict], aliases: tuple[str, ...]) -> dict | None:
    candidates: list[tuple[int, dict]] = []
    for row in rows:
        name = str(row.get("NAME_OF_TIME_SERIES") or "")
        low = name.lower()
        freq = str(row.get("FREQUENCY") or "").lower()
        if freq and "quarter" not in freq:
            continue
        if "central government securities" not in low:
            continue
        if "stock" not in low:
            continue
        if not any(alias.lower() in low for alias in aliases):
            continue
        score = 0
        if "assets" in low:
            score += 4
        if "financial assets" in low:
            score += 2
        if low.endswith("/stock") or "/stock" in low:
            score += 1
        candidates.append((score, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    return candidates[0][1]


def quarter_end_account(account_links: list[tuple[dt.date, str]], year: int, quarter: int) -> AccountPoint | None:
    month = quarter * 3
    target = dt.date(year, month, 31 if month in {3, 12} else 30)
    eligible = [item for item in account_links if item[0] <= target]
    if not eligible:
        return None
    d, u = max(eligible, key=lambda item: item[0])
    if (target - d).days > 15:
        return None
    return parse_account_release(d, u)


def fetch_private_absorption(now: dt.datetime) -> dict:
    rows = metadata_rows("FF")
    groups = {
        "banks": ("banks", "depository corporations"),
        "insurance_pensions": ("insurance and pension funds", "insurance corporations", "pension funds"),
        "households": ("households",),
    }
    chosen: dict[str, dict] = {}
    for key, aliases in groups.items():
        row = fof_candidate(rows, aliases)
        if row:
            chosen[key] = row
    if len(chosen) < 2:
        raise RuntimeError(f"FOF private JGB series insufficient: found={list(chosen)}")

    series_data: dict[str, list[tuple[str, float]]] = {}
    for key, row in chosen.items():
        obs = series_observations("FF", row, f"{now.astimezone(KST).year - 2}01")
        series_data[key] = obs

    latest_period = min((values[-1][0] for values in series_data.values()), key=str)
    common_periods = set(series_data[next(iter(series_data))][i][0] for i in range(len(series_data[next(iter(series_data))])))
    for obs in series_data.values():
        common_periods &= {p for p, _ in obs}
    common = sorted(common_periods)
    if len(common) < 2:
        raise RuntimeError("FOF private JGB series have no two common quarters")
    current_period, prior_period = common[-1], common[-2]

    def value_at(obs, period):
        return next(v for p, v in obs if p == period)

    current_total = 0.0
    prior_total = 0.0
    detail: dict[str, dict] = {}
    for key, row in chosen.items():
        unit = str(row.get("UNIT") or "")
        current = to_trillion(value_at(series_data[key], current_period), unit)
        prior = to_trillion(value_at(series_data[key], prior_period), unit)
        current_total += current
        prior_total += prior
        detail[key] = {
            "series_code": row.get("SERIES_CODE"),
            "series_name": row.get("NAME_OF_TIME_SERIES"),
            "current_trillion_yen": current,
            "prior_trillion_yen": prior,
            "change_trillion_yen": current - prior,
        }

    parsed = normalize_period(current_period)
    prior_parsed = normalize_period(prior_period)
    if not parsed or not prior_parsed:
        raise RuntimeError(f"FOF period parse failed: {current_period}/{prior_period}")

    links: list[tuple[dt.date, str]] = []
    for y in {parsed[0], prior_parsed[0]}:
        links.extend(account_release_links(y))
    current_boj = quarter_end_account(links, *parsed)
    prior_boj = quarter_end_account(links, *prior_parsed)
    boj_change = None
    ratio = None
    if current_boj and prior_boj:
        boj_change = current_boj.jgs_trillion_yen - prior_boj.jgs_trillion_yen
        if boj_change < -0.01:
            ratio = (current_total - prior_total) / abs(boj_change)

    return {
        "current_period": current_period,
        "prior_period": prior_period,
        "selected_groups": detail,
        "private_current_trillion_yen": current_total,
        "private_prior_trillion_yen": prior_total,
        "private_change_trillion_yen": current_total - prior_total,
        "boj_change_same_quarter_trillion_yen": boj_change,
        "private_absorption_ratio": ratio,
        "note": "선택된 민간부문 JGB 보유증가 ÷ 같은 분기 BOJ JGS 보유감소. 신규발행·기타 보유주체가 있어 100% 초과 가능.",
    }


def parse_release_date_from_href(href: str) -> dt.date | None:
    match = re.search(r"[kmg](\d{2})(\d{2})(\d{2})", href)
    if not match:
        return None
    yy, mm, dd = map(int, match.groups())
    try:
        return dt.date(2000 + yy, mm, dd)
    except ValueError:
        return None


def scan_policy_plan(now: dt.datetime) -> dict:
    year = now.astimezone(KST).year
    url = BOJ_POLICY_INDEX.format(year=year)
    parser = AnchorParser()
    parser.feed(fetch(url))
    plan_items = []
    for title, href in parser.anchors:
        if "plan for the outright purchases" not in title.lower():
            continue
        full = urllib.parse.urljoin(url, href)
        date = parse_release_date_from_href(full)
        plan_items.append({"title": title, "url": full, "date": date.isoformat() if date else None})
    newer = [item for item in plan_items if item.get("date") and dt.date.fromisoformat(item["date"]) > BASE_PLAN_DATE]
    return {"items": plan_items[:10], "newer_than_baseline": newer}


def scan_emergency_operations(now: dt.datetime) -> dict:
    year = now.astimezone(KST).year
    urls = [BOJ_OPERATION_INDEX.format(year=year), BOJ_JGB_PURCHASE_PAGE]
    hits = []
    for url in urls:
        try:
            parser = AnchorParser()
            parser.feed(fetch(url))
        except Exception:
            continue
        for title, href in parser.anchors:
            low = title.lower()
            if not (
                ("fixed-rate" in low and ("purchase" in low or "jgb" in low))
                or ("additional" in low and ("purchase" in low or "jgb" in low))
                or ("increase" in low and "jgb" in low)
            ):
                continue
            full = urllib.parse.urljoin(url, href)
            date = parse_release_date_from_href(full)
            hits.append({"title": title, "url": full, "date": date.isoformat() if date else None})
    recent_cutoff = now.astimezone(KST).date() - dt.timedelta(days=30)
    recent = [h for h in hits if h.get("date") and dt.date.fromisoformat(h["date"]) >= recent_cutoff]
    return {"hits": hits[:20], "recent_30d": recent}


def stress_from_structural() -> dict:
    state = load_json(STRUCTURAL_PENDING, {})
    values = state.get("values") or {}
    jgb = number(values.get("jgb10"))
    days = int(values.get("jgb10_consecutive_days_ge_3") or 0)
    a10_btc = number(values.get("auction10_bid_to_cover"))
    a10_tail = number(values.get("auction10_tail_bp"))
    a30_btc = number(values.get("auction30_bid_to_cover"))
    a30_tail = number(values.get("auction30_tail_bp"))
    weak10 = bool(a10_btc is not None and a10_tail is not None and a10_btc < 2.5 and a10_tail >= 5.0)
    weak30 = bool(a30_btc is not None and a30_tail is not None and a30_btc < 2.5 and a30_tail >= 5.0)
    return {
        "jgb10": jgb,
        "jgb10_days_ge_3": days,
        "weak_auction_10y": weak10,
        "weak_auction_30y": weak30,
        "joint_market_stress": bool(jgb is not None and jgb >= JGB_STRESS_LEVEL and days >= JGB_STRESS_DAYS and (weak10 or weak30)),
    }


def classify(previous: dict, account: dict | None, purchase: dict | None, absorption: dict | None,
             plan: dict | None, emergency: dict | None, stress: dict | None) -> tuple[dict, list[str]]:
    reasons: list[str] = []
    plan_revision = bool(plan and plan.get("newer_than_baseline"))
    emergency_recent = bool(emergency and emergency.get("recent_30d"))

    actual_over_plan = False
    if purchase and purchase.get("planned_trillion_yen"):
        actual = float(purchase["actual_trillion_yen"])
        planned = float(purchase["planned_trillion_yen"])
        actual_over_plan = (
            actual >= planned * ACTUAL_OVER_PLAN_RATIO
            and actual - planned >= ACTUAL_OVER_PLAN_TRILLION
        )

    weak_absorption = bool(
        absorption
        and absorption.get("private_absorption_ratio") is not None
        and float(absorption["private_absorption_ratio"]) < ABSORPTION_WEAK_RATIO
        and float(absorption.get("boj_change_same_quarter_trillion_yen") or 0) < 0
    )
    market_stress = bool(stress and stress.get("joint_market_stress"))

    current = {
        "plan_revision": plan_revision,
        "emergency_purchase_signal": emergency_recent,
        "actual_over_plan": actual_over_plan,
        "weak_private_absorption": weak_absorption,
        "joint_market_stress": market_stress,
    }
    old = previous.get("signals") or {}
    labels = {
        "plan_revision": "BOJ JGB 매입축소 계획 공식 변경 감지",
        "emergency_purchase_signal": "BOJ 고정금리·추가 JGB 매입 신호 감지",
        "actual_over_plan": "월간 JGB 실제 매입이 공식 계획을 크게 상회",
        "weak_private_absorption": "BOJ 보유감소 대비 민간 JGB 흡수 약화",
        "joint_market_stress": "10년 JGB 3% 이상 지속과 입찰 약화 동시 확인",
    }
    if previous.get("initialized"):
        for key, label in labels.items():
            if current[key] and not bool(old.get(key)):
                reasons.append(label)

    anomaly_count = sum(bool(v) for v in current.values())
    if current["emergency_purchase_signal"] or current["plan_revision"]:
        level = 3
        label = "질서 있는 출구 흔들림 — 정책 경로 변경"
    elif current["actual_over_plan"] or current["joint_market_stress"]:
        level = 2
        label = "질서 있는 출구 경계 — 시장안정 개입 위험"
    elif current["weak_private_absorption"]:
        level = 1
        label = "민간 흡수력 점검 필요"
    else:
        level = 0
        label = "질서 있는 출구 진행 여부 정상 감시"

    return {"level": level, "label": label, "signals": current, "active_count": anomaly_count}, reasons


def fmt(value, suffix="", digits=2):
    if value is None:
        return "확인 불가"
    return f"{float(value):+.{digits}f}{suffix}"


def build_context(classification: dict, account, purchase, absorption, stress, errors: list[str]) -> str:
    lines = [
        "BOJ 출구전략 품질",
        f"- 판정: {classification['label']}",
    ]
    if account:
        latest = account["latest"]
        lines += [
            f"- BOJ JGS 보유: {latest['jgs_trillion_yen']:.2f}조엔 ({latest['date']})",
            f"- 보유 변화: 1개월 {fmt(account.get('change_1m_trillion_yen'), '조엔')} / 3개월 {fmt(account.get('change_3m_trillion_yen'), '조엔')}",
        ]
    else:
        lines.append("- BOJ JGS 보유·1/3개월 변화: 확인 지연")

    if purchase:
        plan_text = "확인 불가" if purchase.get("planned_trillion_yen") is None else f"{purchase['planned_trillion_yen']:.2f}조엔"
        ratio = purchase.get("actual_plan_ratio")
        ratio_text = "확인 불가" if ratio is None else f"{ratio * 100:.0f}%"
        lines.append(
            f"- 월간 JGB 매입: 실제 {purchase['actual_trillion_yen']:.2f}조엔 / 계획 {plan_text} / 계획 대비 {ratio_text} ({purchase['period']})"
        )
    else:
        lines.append("- 월간 실제 매입 vs 계획: 확인 지연")

    if absorption:
        ratio = absorption.get("private_absorption_ratio")
        ratio_text = "계산 대상 아님" if ratio is None else f"{ratio * 100:.0f}%"
        lines += [
            f"- 선택 민간부문 JGB 보유 변화: {fmt(absorption.get('private_change_trillion_yen'), '조엔')} ({absorption['prior_period']}→{absorption['current_period']})",
            f"- 같은 분기 BOJ JGS 변화: {fmt(absorption.get('boj_change_same_quarter_trillion_yen'), '조엔')} / 민간 흡수비율 {ratio_text}",
            "※ 민간 흡수비율은 은행·보험/연금·가계 중 공식 시계열이 명확히 확인된 부문의 합계이며, 신규발행 때문에 100%를 넘을 수 있습니다.",
        ]
    else:
        lines.append("- 분기 민간 JGB 흡수비율: 공식 시계열 자동 식별 지연")

    if stress:
        lines.append(
            f"- 시장 확인: 10년 JGB {fmt(stress.get('jgb10'), '%', digits=3)} / 3% 이상 {stress.get('jgb10_days_ge_3')}영업일 / "
            f"10년 입찰약화 {'예' if stress.get('weak_auction_10y') else '아니오'} / 30년 {'예' if stress.get('weak_auction_30y') else '아니오'}"
        )

    lines += [
        "※ 잔액 감소 한 점만으로 QT 가속·후퇴를 판정하지 않고 1·3개월 변화, 실제 매입, 민간 수요, 입찰을 함께 봅니다.",
    ]
    if errors:
        lines += ["", "자료 확인 상태"] + [f"- {item}" for item in errors]
    return "\n".join(lines)


def append_to_composite(context: str, payload: dict) -> None:
    if not COMPOSITE_ALERT_BODY.exists():
        return
    body = COMPOSITE_ALERT_BODY.read_text(encoding="utf-8")
    if "BOJ 출구전략 품질" not in body:
        marker = "\n\n출처\n"
        if marker in body:
            body = body.replace(marker, "\n\n" + context + marker, 1)
        else:
            body = body.rstrip() + "\n\n" + context + "\n"
        COMPOSITE_ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")
    alert_json = load_json(COMPOSITE_ALERT_JSON, {})
    if alert_json:
        alert_json["boj_exit_quality"] = payload
        write_json(COMPOSITE_ALERT_JSON, alert_json)


def build_alert(classification: dict, reasons: list[str], context: str, sources: dict, now: dt.datetime) -> tuple[str, str]:
    emoji = {1: "🟡", 2: "🟠", 3: "🔴"}.get(int(classification["level"]), "🟡")
    title = f"{emoji} BOJ 질서 있는 출구 경보 — {classification['label']}"
    body = [
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "",
        "판정",
        f"- {classification['label']}",
        "",
        "이번 변화",
        *[f"- {r}" for r in reasons],
        "",
        context,
        "",
        "다음 확인",
        "- BOJ 계획 매입액 수정·추가매입·고정금리 매입 여부",
        "- 10년·30년 JGB 입찰배율과 꼬리, 10년 금리 3% 이상 지속 여부",
        "- BOJ 보유 JGS 1·3개월 변화와 분기별 민간 JGB 흡수",
        "",
        "출처",
        f"- BOJ Accounts: {sources['accounts']}",
        f"- BOJ Time-Series API: {sources['api']}",
        f"- BOJ Flow of Funds: {BOJ_FOF_SOURCE}",
        f"- BOJ JGB purchase plan: {BOJ_PLAN_SOURCE}",
        f"- BOJ JGB purchase operations: {BOJ_JGB_PURCHASE_PAGE}",
    ]
    return title, "\n".join(body)


def finalize() -> int:
    if not PENDING_PATH.exists():
        return 0
    if ALERT_BODY.exists() and not CONFIRMED.exists():
        print("boj_exit_state_not_advanced=telegram_unconfirmed")
        return 0
    STATE_PATH.write_text(PENDING_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print("boj_exit_state_finalized=true")
    return 0


def clean_outputs() -> None:
    for path in (ALERT_TITLE, ALERT_BODY, ALERT_JSON, CONFIRMED):
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize()

    clean_outputs()
    now = dt.datetime.now(UTC)
    previous = load_json(STATE_PATH, {})
    errors: list[str] = []

    account = purchase = absorption = plan = emergency = None

    try:
        account = fetch_account_history(now)
    except Exception as exc:
        errors.append(f"BOJ Accounts: {type(exc).__name__}: {exc}")
        record_failure("BOJ Accounts", BOJ_ACCOUNTS_INDEX.format(year=now.astimezone(KST).year), exc, now)

    try:
        purchase = fetch_actual_purchases(now)
    except Exception as exc:
        errors.append(f"월간 JGB 매입: {type(exc).__name__}: {exc}")
        record_failure("BOJ MD09 JGB purchases", BOJ_TS_API, exc, now)

    try:
        absorption = fetch_private_absorption(now)
    except Exception as exc:
        errors.append(f"민간 JGB 흡수: {type(exc).__name__}: {exc}")
        record_failure("BOJ FOF private absorption", BOJ_TS_API, exc, now)

    try:
        plan = scan_policy_plan(now)
    except Exception as exc:
        errors.append(f"BOJ 매입계획: {type(exc).__name__}: {exc}")

    try:
        emergency = scan_emergency_operations(now)
    except Exception as exc:
        errors.append(f"BOJ 긴급매입 탐지: {type(exc).__name__}: {exc}")

    stress = stress_from_structural()
    classification, reasons = classify(previous, account, purchase, absorption, plan, emergency, stress)

    current = {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "classification": classification,
        "signals": classification["signals"],
        "account": account,
        "purchase": purchase,
        "private_absorption": absorption,
        "policy_plan": plan,
        "emergency_operations": emergency,
        "market_stress": stress,
        "errors": errors,
    }
    write_json(PENDING_PATH, current)
    write_json(CONTEXT_JSON, current)
    context = build_context(classification, account, purchase, absorption, stress, errors)
    CONTEXT_MD.write_text("# BOJ 출구전략 품질\n\n" + context + "\n", encoding="utf-8")
    append_to_composite(context, current)

    if reasons:
        title, body = build_alert(
            classification,
            reasons,
            context,
            {
                "accounts": BOJ_ACCOUNTS_INDEX.format(year=now.astimezone(KST).year),
                "api": BOJ_TS_API,
            },
            now,
        )
        ALERT_TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")
        write_json(ALERT_JSON, {"classification": classification, "reasons": reasons, "context": current})
        print(f"boj_exit_alert=true reasons={reasons}")
    else:
        print(f"boj_exit_alert=false level={classification['level']} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

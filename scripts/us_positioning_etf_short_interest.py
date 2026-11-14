#!/usr/bin/env python3
"""QQQ/SPY twice-monthly short-interest divergence within existing US positioning route.

Independent secondary publishers reproduce exchange-reported position counts;
FINRA supplies the official publication calendar. Daily FINRA short-sale
volume and CFTC NQ futures positions are deliberately NOT interchangeable
with twice-monthly ETF short interest.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
from html import escape
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "us_positioning_etf_short_interest_state.json"
OUT = ROOT / "out"
STATUS = OUT / "us_positioning_etf_short_interest_status.json"
RECEIPT = OUT / "us_positioning_etf_short_interest_confirmed.json"
KST = ZoneInfo("Asia/Seoul")
FINRA_CALENDAR = "https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest"
EXPECTED_BOT = "khs887900887900008879_bot"
PROVIDERS = {
    "chartexchange": "https://chartexchange.com/symbol/{venue}-{ticker}/short-interest/",
    "benzinga": "https://www.benzinga.com/quote/{ticker}/short-interest",
    "finshort": "https://finshort.com/{ticker}/short-interest",
}
VENUES = {"QQQ": "nasdaq", "SPY": "nyse"}
MAX_PUBLICATION_AGE_DAYS = 21

# Exact dates verified against FINRA's 2026 publication schedule.
# If the official calendar page cannot be reached, no unknown 2027 date is guessed.
FINRA_VERIFIED_FALLBACK = {
    "2026-10-15": "2026-10-26",
    "2026-10-30": "2026-11-10",
    "2026-11-13": "2026-11-24",
    "2026-11-30": "2026-12-09",
    "2026-12-15": "2026-12-24",
    "2026-12-31": "2027-01-12",
}
MONTHS = "January February March April May June July August September October November December".split()
MONTH_RE = r"(?:%s)" % "|".join(MONTHS)


def get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(4_000_000)
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
    return data.decode("utf-8", "replace")


def day(raw: str) -> dt.date:
    raw = str(raw or "").strip().replace("\xa0", " ")
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError("unrecognized short-interest date")


def whole(raw: str) -> int:
    token = str(raw).replace(",", "").replace("\xa0", "").strip()
    if not re.fullmatch(r"\d+", token):
        raise ValueError("short-interest share count must be a whole number")
    n = int(token)
    if not 1_000_000 <= n <= 2_000_000_000:
        raise ValueError("short-interest shares outside ETF sanity bounds")
    return n


def parse_provider(source: str, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for tr in soup.select("tr"):
        cells = [c.get_text(" ", strip=True).replace("\xa0", " ") for c in tr.find_all(["th", "td"], recursive=False)]
        if len(cells) < 3:
            continue
        try:
            if source == "chartexchange":
                if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", cells[0]) or len(cells) < 6:
                    continue
                period, count = day(cells[0]), whole(cells[2])
            elif source == "benzinga":
                if not re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}, 20\d{2}", cells[0]) or len(cells) < 7:
                    continue
                period, count = day(cells[0]), whole(cells[4])
            elif source == "finshort":
                if not re.fullmatch(r"[A-Z][a-z]{2} \d{1,2}, 20\d{2}", cells[0]) or len(cells) < 3:
                    continue
                period, count = day(cells[0]), whole(cells[1])
            else:
                raise ValueError("unknown provider")
            found.append({"settlement": period.isoformat(), "shares": count})
        except (ValueError, IndexError):
            continue
    # Never accept a single stray count from a quote widget as a true time series.
    unique = {}
    for row in found:
        when = row["settlement"]
        if when in unique and unique[when] != row["shares"]:
            raise ValueError(f"{source}: contradictory values for same settlement")
        unique[when] = row["shares"]
    rows = sorted(({"settlement": k, "shares": v} for k, v in unique.items()), key=lambda x: x["settlement"], reverse=True)
    if len(rows) < 2 or rows[0]["settlement"] <= rows[1]["settlement"]:
        raise ValueError(f"{source}: two consecutive published short-interest observations missing")
    if not (5_000_000 <= rows[0]["shares"] <= 400_000_000):
        raise ValueError(f"{source}: latest QQQ/SPY figure implausible")
    return rows


def read_calendar(html: str, reporting_year: int) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for table in soup.select("table"):
        # FINRA presents several calendar years on the same page. Never
        # reinterpret a prior-year table as belonging to the current year.
        year_heading = table.find_previous(["h2", "h3"])
        if year_heading is not None:
            marker = re.search(r"(20\d{2})\s+Short Interest Reporting Dates",
                               year_heading.get_text(" ", strip=True), re.I)
            if marker and int(marker.group(1)) != reporting_year:
                continue
        rows = table.select("tr")
        if not rows:
            continue
        heading = rows[0].get_text(" ", strip=True).lower()
        if not all(word in heading for word in ("settlement", "publication")):
            continue
        for tr in rows[1:]:
            cells = [x.get_text(" ", strip=True) for x in tr.find_all(["th", "td"], recursive=False)]
            if len(cells) < 3:
                continue
            first = re.search(r"\b(" + MONTH_RE + r")\s+(\d{1,2})\b", cells[0], re.I)
            last = re.search(r"\b(" + MONTH_RE + r")\s+(\d{1,2})\b", cells[-1], re.I)
            if not first or not last:
                continue
            observed = day(f"{first.group(1)} {first.group(2)}, {reporting_year}")
            pub_year = reporting_year + (observed.month == 12 and last.group(1).lower() == "january")
            published = day(f"{last.group(1)} {last.group(2)}, {pub_year}")
            out[observed.isoformat()] = published.isoformat()
    return out


def verified_calendar(today: dt.date, getter=get) -> dict[str, str]:
    official = {}
    try:
        raw = getter(FINRA_CALENDAR)
        for year in (today.year - 1, today.year):
            official.update(read_calendar(raw, year))
    except Exception as exc:
        print(f"etf_si_finra_calendar_access={type(exc).__name__}")
    # Previous-year December settlements can publish in the new year.
    # Keep only previously verified literal dates; never guess a future year.
    fallback = {
        settlement: published
        for settlement, published in FINRA_VERIFIED_FALLBACK.items()
        if int(settlement[:4]) in (today.year - 1, today.year)
    }
    return {**fallback, **official}


def collect(*, now: dt.date | None = None, getter=get) -> dict:
    # FINRA publication dates are New York local, not Korea calendar dates.
    today = now or dt.datetime.now(ZoneInfo("America/New_York")).date()
    official_schedule = verified_calendar(today, getter=getter)
    sources = {}
    by_ticker = {}
    validated_histories = {}
    for ticker in ("QQQ", "SPY"):
        reports = []
        for provider, template in PROVIDERS.items():
            url = template.format(ticker=ticker, venue=VENUES[ticker])
            try:
                parsed = parse_provider(provider, getter(url))
                reports.append((provider, parsed, url))
            except Exception as exc:
                print(f"etf_si_source_unavailable ticker={ticker} provider={provider} error={type(exc).__name__}")
        if len(reports) < 2:
            raise RuntimeError(f"{ticker}: fewer than two independent publishers of reported ETF short interest")
        # Require two different providers to agree on the same two latest records.
        groups = {}
        for provider, rows, url in reports:
            identity = tuple((x["settlement"], x["shares"]) for x in rows[:2])
            groups.setdefault(identity, []).append((provider, url))
        winner, matched_sources = max(groups.items(), key=lambda x: len(x[1]))
        if len(matched_sources) < 2:
            raise RuntimeError(f"{ticker}: providers disagree on settlement dates or share counts")
        latest, prior = winner
        validated_histories[ticker] = _validated_history(reports, matched_sources)
        by_ticker[ticker] = {
            "settlement": latest[0], "shares": latest[1],
            "previous_settlement": prior[0], "previous_shares": prior[1],
            "change_shares": latest[1] - prior[1],
            "change_pct": (latest[1] / prior[1] - 1.0) * 100.0,
            "publisher_count": len(matched_sources),
            "sources": [p for p, url in matched_sources],
        }
        sources[ticker] = [u for p, u in matched_sources]
    q, s = by_ticker["QQQ"], by_ticker["SPY"]
    if q["settlement"] != s["settlement"] or q["previous_settlement"] != s["previous_settlement"]:
        raise RuntimeError("QQQ/SPY settlement dates do not align")
    settlement = q["settlement"]
    published = official_schedule.get(settlement)
    if not published:
        raise RuntimeError("Official FINRA publication date not verified for this settlement")
    pub_date = day(published)
    age = (today - pub_date).days
    if age < 0:
        raise RuntimeError(f"ETF short interest publication not current: age={age} calendar days")
    # The most recently *officially published* settlement remains valid
    # until the next FINRA publication; a fixed 12-day age silently misses
    # valid twice-monthly data near longer reporting gaps.
    released = [
        dt.date.fromisoformat(key)
        for key, value in official_schedule.items()
        if dt.date.fromisoformat(value) <= today
    ]
    if not released or dt.date.fromisoformat(settlement) != max(released):
        raise RuntimeError("ETF short interest publication lag: newer FINRA settlement available")
    # If the official calendar ends/temporarily disappears, never carry a
    # published value forward indefinitely.
    if age > MAX_PUBLICATION_AGE_DAYS:
        raise RuntimeError(f"ETF short interest publication expired: age={age} calendar days")
    # Only compare percent changes on identical settlement intervals.
    divergence = q["change_pct"] - s["change_pct"]
    opp = (q["change_pct"] > 0 and s["change_pct"] < 0) or (q["change_pct"] < 0 and s["change_pct"] > 0)
    legacy_divergence = bool(opp and abs(divergence) >= 15.0)
    legacy_surge = bool(q["change_pct"] >= 20.0 and q["change_shares"] >= 10_000_000)
    # A new, source-confirmed multi-month high can matter even when QQQ's
    # two-week percentage change is small or SPY shorts also rise.
    qqq_peak = _verified_qqq_high(settlement, validated_histories["QQQ"])
    reasons = []
    if legacy_divergence:
        reasons.append("qqq_spy_divergence")
    if legacy_surge:
        reasons.append("qqq_rapid_short_growth")
    if qqq_peak is not None:
        reasons.append("qqq_verified_short_peak")
    signal = bool(reasons)
    key = f"{settlement}:{q['shares']}:{s['shares']}"
    return {
        "settlement": settlement, "previous_settlement": q["previous_settlement"],
        "published": published, "publication_age_days": age,
        "QQQ": q, "SPY": s, "divergence_pp": divergence,
        "signal": signal, "signal_key": key,
        "signal_reasons": reasons, "qqq_verified_peak": qqq_peak,
        "period_comparisons": _aligned_period_comparisons(settlement, validated_histories),
        "sources": sources, "official_schedule": FINRA_CALENDAR,
        "source_type": "FINRA calendar + two independent secondary per-ticker republishes",
    }


def _calendar_months_before(d: dt.date, months: int) -> dt.date:
    """Use calendar months rather than fixed 30-day approximations."""
    year, zero_month = divmod(d.year * 12 + d.month - 1 - months, 12)
    month = zero_month + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _validated_history(reports: list, matched_sources: list) -> dict[str, int]:
    """Require two agreeing source publishers for EACH historical share count."""
    accepted = {provider for provider, _url in matched_sources}
    votes: dict[tuple[str, int], set[str]] = {}
    for provider, rows, _url in reports:
        if provider not in accepted:
            continue
        for row in rows:
            key = (row["settlement"], row["shares"])
            votes.setdefault(key, set()).add(provider)
    counts = {}
    for (settlement, shares), sources in votes.items():
        if len(sources) >= 2:
            if settlement in counts and counts[settlement] != shares:
                # Two contradictory majorities: suppress the ambiguous date.
                counts[settlement] = None
            elif settlement not in counts:
                counts[settlement] = shares
    return {date_str: amount for date_str, amount in counts.items()
            if isinstance(amount, int)}


def _verified_qqq_high(latest: str, history: dict[str, int]) -> dict | None:
    """High watermark only from agreed, dated share counts (not an image).

    Do not claim "since 2023" without source-matched coverage since 2023.
    Need >=8 prior settlement observations spanning >=145 days for six months,
    or >=18 spanning >=300 days for 12 months; otherwise withhold this signal.
    """
    when = dt.date.fromisoformat(latest)
    current = history.get(latest)
    if not isinstance(current, int) or current <= 0:
        return None
    for months, required_span, required_points in ((12, 300, 18), (6, 145, 8)):
        start = _calendar_months_before(when, months)
        prior = sorted(
            (dt.date.fromisoformat(d), amount)
            for d, amount in history.items()
            if isinstance(amount, int) and start <= dt.date.fromisoformat(d) < when
        )
        if len(prior) < required_points or (when - prior[0][0]).days < required_span:
            continue
        prior_max = max(amount for _d, amount in prior)
        if current > prior_max:
            return {
                "months": months, "prior_max_shares": prior_max,
                "observations": len(prior) + 1,
                "oldest_verified_settlement": prior[0][0].isoformat(),
            }
    return None


def _aligned_period_comparisons(latest: str, histories: dict) -> dict:
    """Compare QQQ and SPY on the exact same past settlement for each horizon."""
    current_date = dt.date.fromisoformat(latest)
    qqq, spy = histories["QQQ"], histories["SPY"]
    if latest not in qqq or latest not in spy:
        return {}
    joint_dates = sorted(
        dt.date.fromisoformat(d) for d in (set(qqq) & set(spy))
        if d != latest
    )
    targets = [("1개월", _calendar_months_before(current_date, 1)),
               ("2개월", _calendar_months_before(current_date, 2)),
               ("3개월", _calendar_months_before(current_date, 3)),
               ("6개월", _calendar_months_before(current_date, 6)),
               ("연초", dt.date(current_date.year - 1, 12, 31))]
    result = {}
    for label, target in targets:
        eligible = [d for d in joint_dates if d <= target and (target - d).days <= 20]
        if not eligible:
            continue
        prior_date = max(eligible).isoformat()
        row = {"previous_settlement": prior_date}
        for ticker, history in (("QQQ", qqq), ("SPY", spy)):
            old, new = history[prior_date], history[latest]
            if old <= 0:
                break
            row[ticker] = {
                "previous_shares": old,
                "shares": new,
                "change_shares": new - old,
                "change_pct": (new / old - 1.0) * 100.0,
            }
        if "QQQ" in row and "SPY" in row:
            row["divergence_pp"] = row["QQQ"]["change_pct"] - row["SPY"]["change_pct"]
            result[label] = row
    return result


def load_state(path: pathlib.Path = STATE) -> dict:
    if not path.exists():
        return {"sent_keys": [], "last_alert": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RuntimeError("ETF SI delivery state unreadable; do not reset") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sent_keys"), list):
        raise RuntimeError("ETF SI state invalid; refuse to reset")
    return data


def render(d: dict) -> tuple[str, str]:
    q, s = d["QQQ"], d["SPY"]
    peak = d.get("qqq_verified_peak")
    title = ("QQQ 공매도 잔량 장기 최고 · 기술주 헤지 경계"
             if peak else "미국 QQQ·SPY 공매도 잔량 괴리 확대")
    periods = d.get("period_comparisons") or {}
    historical = ["<b>동일 기준일 1·2·3·6개월 및 연초 비교</b>"]
    for label in ("1개월", "2개월", "3개월", "6개월", "연초"):
        period = periods.get(label)
        if not period:
            historical.append(f"• {label}: 과거 잔량 교차검증 미완료")
            continue
        previous = period["previous_settlement"]
        old_q, old_s = period["QQQ"], period["SPY"]
        historical.append(
            f"• {label}({previous}): "
            f"QQQ {old_q['previous_shares']:,}→{old_q['shares']:,}주 "
            f"({old_q['change_shares']:+,}주, {old_q['change_pct']:+.2f}%) · "
            f"SPY {old_s['previous_shares']:,}→{old_s['shares']:,}주 "
            f"({old_s['change_shares']:+,}주, {old_s['change_pct']:+.2f}%)"
        )
    body = "\n".join([
        "<b>방향: QQQ 공매도 잔량 증가 → 기술주 수급 위험, 향후 숏커버 반등 가능성 병행 점검</b>",
        "<b>QQQ·SPY 공매도 미청산 잔량 — 공식 공표 자료</b>",
        f"• 결제 기준일: {d['settlement']} · 공표일: {d['published']}",
        f"• 비교기간: 직전 결제일 {d['previous_settlement']} → {d['settlement']} (약 2주)",
        f"• QQQ: {q['previous_shares']:,}→{q['shares']:,}주"
        f" ({q['change_shares']:+,}주, {q['change_pct']:+.2f}%)",
        f"• SPY: {s['previous_shares']:,}→{s['shares']:,}주"
        f" ({s['change_shares']:+,}주, {s['change_pct']:+.2f}%)",
        f"• 직전 발표 대비 증감률 격차: {d['divergence_pp']:+.2f}%p"
        " (같은 기간 비교, 선행경보 기준 15%p)",
        *((
            f"• 신규 경보: QQQ 공매도 잔량 {peak['months']}개월 확인 이력 최고치 "
            f"({peak['observations']}개 결제일·2개 이상 제공처 교차확인, "
            f"기존 최고 {peak['prior_max_shares']:,}주 → 현재 {q['shares']:,}주). "
            "2023년 이후 최고라는 의미는 아닙니다.",
        ) if peak else ()),
        "",
        *historical,
        "• 과거 비교는 두 종목의 결제 기준일을 일치시켰으며, "
        "기간별 잔량을 두 자료 제공처 이상에서 대조했습니다.",
        "• 서로 다른 비교기간의 변화율·주식수 감소를 하나의 괴리율로 합치지 않습니다.",
        "",
        "• 공매도 미청산 잔량은 일별 공매도 거래량이 아닙니다.",
        "• 기술주 위험 회피·ETF 헤지·상대가치 거래 등 원인을 구분해야 합니다.",
        "• SPY 잔량 감소가 미국 주식시장 전체의 순매수 확정은 아닙니다.",
        "• 잔량 증가 자체는 약세 헤지 또는 상대가치 거래일 수 있습니다.",
        "• 가격 반등과 공매도 청산이 동시에 확인될 때만 숏커버 주도 반등으로 판단합니다.",
        "• 잔량 변화만으로 나스닥 폭락·숏 스퀴즈를 확정할 수 없습니다.",
        "• 다음 확인: 다음 FINRA 공표, 두 ETF 잔량·유통주식 대비 비중, "
        "NQ 선물 포지션·옵션·시장 확산 지표.",
        f'<a href="{d["sources"]["QQQ"][0]}">QQQ 데이터</a>'
        f' · <a href="{d["sources"]["SPY"][0]}">SPY 데이터</a>'
        f' · <a href="{FINRA_CALENDAR}">FINRA 공식 발표 일정</a>',
    ])
    if len(title) + 2 + len(body) > 3900:
        raise RuntimeError("ETF SI Telegram message exceeds safe size")
    return title, body


def send_message(title: str, body: str, *, sender=None) -> dict:
    """Single attempt only: a timeout AFTER delivery may otherwise duplicate."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    expected = os.environ.get("EXPECTED_TELEGRAM_BOT_USERNAME", EXPECTED_BOT).strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("Existing US positioning Telegram route missing")
    sender = sender or get
    identity = json.loads(sender(f"https://api.telegram.org/bot{token}/getMe"))
    username = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or username.lower() != expected.lower():
        raise RuntimeError("Telegram bot identity mismatch")
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": title + "\n\n" + body,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    msg = payload.get("result") or {}
    receipt_chat = msg.get("chat") or {}
    message_id = msg.get("message_id")
    if not payload.get("ok") or not isinstance(message_id, int) or message_id <= 0:
        raise RuntimeError("Telegram send result not confirmed")
    if not receipt_chat.get("id"):
        raise RuntimeError("Telegram send chat.id not returned")
    if chat_id.lstrip("-").isdigit():
        valid = str(receipt_chat["id"]) == chat_id
    elif chat_id.startswith("@"):
        valid = str(receipt_chat.get("username") or "").lower() == chat_id.lstrip("@").lower()
    else:
        valid = False
    if not valid:
        raise RuntimeError("Telegram response chat mismatched configured recipient")
    return {
        "bot_username": username,
        "chat_id_returned": True,
        "chat_id_match": True,
        "message_id": message_id,
    }


def run(*, validate_only: bool, now: dt.date | None = None, getter=get,
        state_path: pathlib.Path = STATE) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    RECEIPT.unlink(missing_ok=True)
    state = load_state(state_path)
    try:
        current = collect(now=now, getter=getter)
    except Exception as exc:
        result = {"status": "source_withheld", "reason": f"{type(exc).__name__}: {str(exc)[:200]}",
                  "telegram_sent": False}
        STATUS.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    already_sent = current["signal_key"] in state.get("sent_keys", [])
    due = current["signal"] and not already_sent
    result = {
        "status": "alert_due" if due else "duplicate_suppressed" if already_sent else "threshold_not_met",
        "settlement": current["settlement"], "published": current["published"],
        "QQQ": {"shares": current["QQQ"]["shares"], "change_pct": round(current["QQQ"]["change_pct"], 3)},
        "SPY": {"shares": current["SPY"]["shares"], "change_pct": round(current["SPY"]["change_pct"], 3)},
        "divergence_pp": round(current["divergence_pp"], 3),
        "signal_reasons": current.get("signal_reasons", []),
        "qqq_verified_peak": current.get("qqq_verified_peak"),
        "period_comparisons": current.get("period_comparisons", {}),
        "sources": {k: current[k]["sources"] for k in ("QQQ", "SPY")},
        "telegram_sent": False,
        "validate_only": validate_only,
    }
    if due:
        title, body = render(current)
        if not validate_only:
            receipt = send_message(title, body)
            result["telegram_sent"] = True
            result["message_id"] = receipt["message_id"]
            state.setdefault("sent_keys", []).append(current["signal_key"])
            state["sent_keys"] = state["sent_keys"][-80:]
            state["last_alert"] = {
                **receipt,
                "key": current["signal_key"],
                "settlement": current["settlement"],
                "published": current["published"],
                "sent_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            }
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            RECEIPT.write_text(json.dumps(state["last_alert"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--validate-only", action="store_true")
    args = cli.parse_args()
    result = run(validate_only=args.validate_only)
    print("us_etf_short_interest_status=" + json.dumps(result, ensure_ascii=False))
    if result["status"] == "source_withheld":
        # A blocked or conflicting source is an operational failure, not a clean no-alert run.
        # An out-of-date publication window remains a normal scheduled no-alert state.
        reason = result.get("reason", "")
        if args.validate_only or "ETF short interest publication not current:" not in reason:
            raise SystemExit(1)

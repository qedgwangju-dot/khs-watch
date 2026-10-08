#!/usr/bin/env python3
"""European sovereign-yield alert.

Monitors secondary-market government borrowing costs separately from ECB policy rates.
Primary trigger sources:
- France: Banque de France TEC10 (official, daily)
- Germany: Deutsche Bundesbank current 10Y Bund yield (official, daily)
- UK: Bank of England IUDMNPY 10Y nominal par yield (official, daily)

Italy is deliberately not used as an automated hard trigger until a timely official
daily endpoint is validated. This prevents a fragile or inferred series from causing
false alerts.

The watcher is fail-closed:
- partial source failures do not make the scheduled job fail,
- missing/stale data cannot create a trigger,
- state advances only after confirmed Telegram delivery when an alert exists.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html as htmllib
import io
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
PARIS = ZoneInfo("Europe/Paris")
LONDON = ZoneInfo("Europe/London")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
STATE = DATA / "europe_sovereign_yield_state.json"
PENDING = OUT / "europe_sovereign_yield_pending_state.json"
ALERT = OUT / "europe_sovereign_yield_alert.md"
TITLE = OUT / "europe_sovereign_yield_alert_title.txt"
DETAIL = OUT / "europe_sovereign_yield_alert.json"
STATUS = OUT / "europe_sovereign_yield_status.md"
CONFIRMED = OUT / "europe_sovereign_yield_telegram_confirmed.json"

FR_BASE_EN = "https://www.banque-france.fr/en/statistics/rates-and-prices/bond-indexes-{date}"
FR_BASE_FR = "https://www.banque-france.fr/fr/statistiques/taux-et-cours/indices-obligataires-{date}"
DE_CSV = "https://api.statistiken.bundesbank.de/rest/data/BBSSY/D.REN.EUR.A630.000000WT1010.A?format=csv&lang=en"
DE_PAGE = "https://www.bundesbank.de/en/statistics/money-and-capital-markets/interest-rates-and-yields/daily-yields-of-current-federal-securities-772220"
UK_SERIES = "IUDMNPY"
UK_VIEW = "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"
UK_CSV = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
UA = "khs-watch-europe-sovereign-yield/1.0"

FR_LEVELS = [4.50, 4.75, 5.00]
UK_LEVELS = [5.00, 5.25, 5.50]
DE_LEVELS = [3.25, 3.50, 3.75]
FR_DE_SPREAD_LEVELS_BP = [100.0, 125.0, 150.0]
IT_LEVELS = [4.50, 4.75, 5.00]
DAILY_MOVE_BP = 10.0
FIVE_OBS_MOVE_BP = 25.0
MAX_BUSINESS_LAG = 1

MARKET_URLS = {
    "fr_mkt": "https://tradingeconomics.com/france/government-bond-yield",
    "de_mkt": "https://tradingeconomics.com/germany/government-bond-yield",
    "it10": "https://tradingeconomics.com/italy/government-bond-yield",
    "uk_mkt": "https://tradingeconomics.com/united-kingdom/government-bond-yield",
}


@dataclass
class Obs:
    key: str
    label: str
    date: str
    value: float
    source: str
    daily_bp: float | None = None


def fetch(url: str, tries: int = 3, timeout: int = 30) -> str:
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,text/csv,*/*",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                charset = r.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except Exception as exc:
            last = exc
            if attempt + 1 < tries:
                time.sleep(1 + attempt)
    raise last or RuntimeError("fetch failed")


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", htmllib.unescape(value)).strip()


def load_json(path: pathlib.Path, default: dict) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else dict(default)
    except Exception:
        return dict(default)


def parse_iso(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        return None


def latest_two(rows: list[Obs]) -> tuple[Obs | None, Obs | None]:
    rows = sorted(rows, key=lambda x: x.date)
    if not rows:
        return None, None
    return rows[-1], rows[-2] if len(rows) >= 2 else None


def fetch_france(now: dt.datetime) -> list[Obs]:
    errors = []
    for lag in range(0, 10):
        day = (now.astimezone(PARIS).date() - dt.timedelta(days=lag)).isoformat()
        for tmpl in (FR_BASE_EN, FR_BASE_FR):
            url = tmpl.format(date=day)
            try:
                plain = strip_html(fetch(url))
                daily = re.split(r"Indices Hebdomadaires|Weekly", plain, maxsplit=1, flags=re.I)[0]
                dates = []
                for x in re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", daily):
                    if x not in dates:
                        dates.append(x)
                m = re.search(r"\bTEC10\b\s+((?:[0-9]+[,.][0-9]+\s+){1,10})", daily)
                if not m:
                    continue
                vals = [float(x.replace(",", ".")) for x in re.findall(r"[0-9]+[,.][0-9]+", m.group(1))]
                if not vals or not dates:
                    continue
                n = min(len(dates), len(vals))
                rows = []
                for ds, v in zip(dates[-n:], vals[-n:]):
                    d = dt.datetime.strptime(ds, "%d/%m/%Y").date().isoformat()
                    rows.append(Obs("fr10", "프랑스 10년", d, v, url))
                if rows:
                    return rows
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}")
    raise RuntimeError("Banque de France TEC10 parse failed; " + " | ".join(errors[-3:]))


def uk_url(now: dt.datetime) -> str:
    end = now.astimezone(LONDON).date()
    start = end - dt.timedelta(days=45)
    params = {
        "CSVF": "TT",
        "DAT": "RNG",
        "FD": start.day,
        "FM": start.strftime("%b"),
        "FNY": "Y",
        "FY": start.year,
        "Filter": "N",
        "FromSeries": 1,
        "SeriesCodes": UK_SERIES,
        "TD": end.day,
        "TM": end.strftime("%b"),
        "TY": end.year,
        "ToSeries": 50,
        "Travel": "NIxAZxSUx",
        "UsingCodes": "Y",
        "VPD": "Y",
        "title": UK_SERIES,
    }
    return UK_VIEW + "?" + urllib.parse.urlencode(params)


def parse_uk(text: str, source: str) -> list[Obs]:
    plain = strip_html(text)
    rows = []
    for ds, value in re.findall(r"\b(\d{2}\s+[A-Z][a-z]{2}\s+\d{2})\s+([0-9]+(?:\.[0-9]+)?)\b", plain):
        try:
            d = dt.datetime.strptime(ds, "%d %b %y").date().isoformat()
            rows.append(Obs("uk10", "영국 10년", d, float(value), source))
        except Exception:
            pass
    dedup = {x.date: x for x in rows}
    return sorted(dedup.values(), key=lambda x: x.date)


def uk_csv_url(now: dt.datetime) -> str:
    end = now.astimezone(LONDON).date()
    start = end - dt.timedelta(days=45)
    params = {
        "csv.x": "yes",
        "Datefrom": start.strftime("%d/%b/%Y"),
        "Dateto": end.strftime("%d/%b/%Y"),
        "SeriesCodes": UK_SERIES,
        "UsingCodes": "Y",
        "CSVF": "TN",
    }
    return UK_CSV + "?" + urllib.parse.urlencode(params)


def parse_uk_csv(text: str, source: str) -> list[Obs]:
    rows = []
    # Accept both CSV and tab-delimited exports and several official date styles.
    for line in text.replace("\ufeff", "").splitlines():
        m = re.search(r"(\d{1,2}[ /-][A-Za-z]{3}[ /-]\d{2,4}|\d{4}-\d{2}-\d{2})[^0-9+-]+([+-]?\d+(?:[.,]\d+)?)\s*$", line.strip())
        if not m:
            continue
        ds, raw = m.groups()
        parsed = None
        for form in ("%d/%b/%Y", "%d %b %Y", "%d %b %y", "%d-%b-%Y", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(ds, form).date()
                break
            except Exception:
                pass
        if parsed is None:
            continue
        try:
            rows.append(Obs("uk10", "영국 10년", parsed.isoformat(), float(raw.replace(",", ".")), source))
        except Exception:
            pass
    dedup = {x.date: x for x in rows}
    return sorted(dedup.values(), key=lambda x: x.date)


def fetch_uk(now: dt.datetime) -> list[Obs]:
    errors = []
    csv_url = uk_csv_url(now)
    try:
        raw = fetch(csv_url)
        rows = parse_uk_csv(raw, csv_url)
        if rows:
            return rows[-30:]
        (OUT / "europe_sovereign_debug_uk.txt").write_text(raw[:20000], encoding="utf-8")
        errors.append("CSV parse empty")
    except Exception as exc:
        errors.append(f"CSV {type(exc).__name__}: {exc}")

    url = uk_url(now)
    try:
        raw = fetch(url)
        rows = parse_uk(raw, url)
        if rows:
            return rows[-30:]
        (OUT / "europe_sovereign_debug_uk_html.txt").write_text(raw[:20000], encoding="utf-8")
        errors.append("HTML parse empty")
    except Exception as exc:
        errors.append(f"HTML {type(exc).__name__}: {exc}")
    raise RuntimeError("Bank of England IUDMNPY parse failed; " + " | ".join(errors))


def parse_delimited(text: str) -> list[dict[str, str]]:
    lines = text.replace("\ufeff", "").splitlines()
    for delimiter in (";", ",", "\t"):
        for start in range(min(120, len(lines))):
            header = [x.strip().strip('"') for x in lines[start].split(delimiter)]
            normalized = {re.sub(r"[^A-Z0-9_]", "", x.upper()) for x in header}
            if not ({"TIME_PERIOD", "OBS_VALUE"} <= normalized or {"DATE", "IUDMNPY"} <= normalized):
                continue
            try:
                reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter)
                rows = list(reader)
                if reader.fieldnames and rows:
                    return [{str(k or "").strip().strip('"'): str(v or "").strip().strip('"') for k, v in row.items()} for row in rows]
            except Exception:
                continue
    raise RuntimeError("CSV header not recognized")


def parse_germany(text: str, source: str) -> list[Obs]:
    out = []

    # Official Bundesbank CSV: metadata first, then YYYY-MM-DD,value,flags.
    for line in text.replace("\ufeff", "").splitlines():
        m = re.match(
            r'^"?([0-9]{4}-[0-9]{2}-[0-9]{2})"?[,;\t]+"?([+-]?[0-9]+(?:[.,][0-9]+)?)"?(?:[,;\t]|$)',
            line.strip(),
        )
        if not m:
            continue
        ds, raw = m.groups()
        try:
            out.append(Obs("de10", "독일 10년", ds, float(raw.replace(",", ".")), source))
        except Exception:
            pass

    if out:
        dedup = {x.date: x for x in out}
        return sorted(dedup.values(), key=lambda x: x.date)

    # Fallback for SDMX-like exports with explicit observation headers.
    rows = parse_delimited(text)
    for row in rows:
        keys = {re.sub(r"[^A-Z0-9_]", "", k.upper()): k for k in row}
        date_key = next((keys[x] for x in ("TIME_PERIOD", "DATE", "TIMEPERIOD") if x in keys), None)
        value_key = next((keys[x] for x in ("OBS_VALUE", "VALUE", "OBSVALUE") if x in keys), None)
        if date_key is None or value_key is None:
            continue
        ds = row.get(date_key, "")
        raw = row.get(value_key, "").replace(",", ".")
        try:
            d = dt.date.fromisoformat(ds[:10]).isoformat()
            out.append(Obs("de10", "독일 10년", d, float(raw), source))
        except Exception:
            continue
    dedup = {x.date: x for x in out}
    return sorted(dedup.values(), key=lambda x: x.date)


def fetch_germany() -> list[Obs]:
    raw = fetch(DE_CSV)
    try:
        rows = parse_germany(raw, DE_CSV)
    except Exception:
        (OUT / "europe_sovereign_debug_de.txt").write_text(raw[:30000], encoding="utf-8")
        raise
    if not rows:
        (OUT / "europe_sovereign_debug_de.txt").write_text(raw[:30000], encoding="utf-8")
        raise RuntimeError("Bundesbank 10Y CSV parse failed")
    return rows[-30:]


def business_lag_days(obs: Obs, now: dt.datetime, tz=PARIS) -> int:
    """Business-day lag in the source's own market timezone.

    Future-dated records are invalid and cannot trigger alerts.
    """
    d = parse_iso(obs.date)
    if d is None:
        return 999
    today = now.astimezone(tz).date()
    if d > today:
        return 999
    lag = 0
    cur = d
    while cur < today:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            lag += 1
    return lag


def parse_market_page(text: str, key: str, label: str, source: str) -> list[Obs]:
    plain = strip_html(text)
    # Trading Economics summary, e.g.
    # "The yield on Italy 10Y Bond Yield rose to 4.69% on October 7, 2026..."
    m = re.search(
        r"The yield on\s+.+?(?:10Y|10 Year|10-Year).+?(?:rose|fell|declined|increased|decreased|was|held steady)\s+(?:to|at)?\s*"
        r"([0-9]+(?:\.[0-9]+)?)%\s+on\s+([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})",
        plain,
        re.I,
    )
    if not m:
        # More tolerant fallback: any first current-yield/date sentence.
        m = re.search(
            r"(?:yield|Bond Yield)[^\.]{0,160}?([0-9]+(?:\.[0-9]+)?)%\s+on\s+"
            r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})",
            plain,
            re.I,
        )
    if not m:
        raise ValueError(f"Trading Economics current quote parse failed: {key}")
    value = float(m.group(1))
    d = dt.datetime.strptime(m.group(2), "%B %d, %Y").date().isoformat()
    if not 0.0 < value < 25.0:
        raise ValueError(f"Unreasonable market bond-yield value: {key}={value}")
    # A whole-page search could attach an unrelated news-item price change.
    # Match daily change only immediately after the SAME current quote.
    quote_tail = plain[m.end():m.end() + 185]
    move = re.match(
        r",?\s*marking a\s+([0-9]+(?:\.[0-9]+)?)\s+percentage points\s+"
        r"(increase|decrease)\s+from the previous session",
        quote_tail,
        re.I,
    )
    daily_bp = None
    if move:
        daily_bp = float(move.group(1)) * 100.0
        if move.group(2).lower() == "decrease":
            daily_bp = -daily_bp
    return [Obs(key, label, d, value, source, daily_bp=daily_bp)]


def fetch_market_history(key: str, label: str) -> list[Obs]:
    url = MARKET_URLS[key]
    return parse_market_page(fetch(url), key, label, url)


def bp(new: float, old: float) -> float:
    return (new - old) * 100.0


def history_from_state(state: dict, key: str) -> list[dict]:
    rows = state.get("history", {}).get(key, [])
    return rows if isinstance(rows, list) else []


def previous_trading_observation(cur: Obs, today_rows: list[Obs], state: dict) -> Obs | None:
    """Find an earlier SOURCE DATE: same-day snapshots are never previous close."""
    candidates = [x for x in today_rows if x.date < cur.date]
    for x in history_from_state(state, cur.key):
        day = str(x.get("date") or "")
        if not day or day >= cur.date:
            continue
        try:
            value = float(x["value"])
        except (TypeError, ValueError, KeyError):
            continue
        candidates.append(Obs(cur.key, cur.label, day, value, cur.source))
    candidates.sort(key=lambda x: x.date)
    return candidates[-1] if candidates else None


def merge_daily_history(state: dict, key: str, cur: Obs) -> list[dict]:
    """Replace revised same-date quotes, preserving one observation per date."""
    by_date = {}
    for row in history_from_state(state, key):
        day = str(row.get("date") or "")
        try:
            value = float(row["value"])
        except (TypeError, ValueError, KeyError):
            continue
        if parse_iso(day):
            by_date[day] = value
    by_date[cur.date] = cur.value
    return [{"date": day, "value": value}
            for day, value in sorted(by_date.items())][-40:]


def comparable_market_spread(latest: dict[str, Obs], stale: list[str]) -> float | None:
    """Same vendor, identical source date and fresh observations."""
    fr, de = latest.get("fr_mkt"), latest.get("de_mkt")
    if fr is None or de is None or "fr_mkt" in stale or "de_mkt" in stale:
        return None
    if fr.date != de.date:
        return None
    return (fr.value - de.value) * 100.0


def coverage_by_country(latest: dict[str, Obs], stale: list[str]) -> dict[str, bool]:
    def ok(key: str) -> bool:
        return key in latest and key not in stale
    return {
        "프랑스": ok("fr10") or ok("fr_mkt"),
        "독일": ok("de10") or ok("de_mkt"),
        "이탈리아": ok("it10"),
        "영국": ok("uk10") or ok("uk_mkt"),
    }


def active_prev(state: dict, key: str) -> bool:
    return bool((state.get("active") or {}).get(key, False))


def mark_event(events: list[dict], active: dict, state: dict, key: str, condition: bool, summary: str, *, clear_summary: str | None = None) -> None:
    before = active_prev(state, key)
    if condition and not before:
        events.append({"type": "trigger", "key": key, "summary": summary})
    elif before and not condition:
        events.append({"type": "clear", "key": key, "summary": clear_summary or summary.replace("진입", "해제")})
    active[key] = condition


def fmt(v: float | None, digits: int = 3) -> str:
    return "확인 불가" if v is None else f"{v:.{digits}f}%"


def signed_bp(v: float | None) -> str:
    return "확인 불가" if v is None else f"{v:+.1f}bp"


def build_alert(latest: dict[str, Obs], changes: dict, spread_bp: float | None, events: list[dict], stale: list[str], errors: list[str], now: dt.datetime) -> tuple[str, str, dict]:
    fr = latest.get("fr10")
    de = latest.get("de10")
    uk = latest.get("uk10")
    it = latest.get("it10")
    fr_mkt = latest.get("fr_mkt")
    de_mkt = latest.get("de_mkt")
    uk_mkt = latest.get("uk_mkt")

    uk_live = uk if uk and "uk10" not in stale else uk_mkt if uk_mkt and "uk_mkt" not in stale else None
    stress_count = sum([
        bool(fr and fr.value >= 4.75 and "fr10" not in stale),
        bool(uk_live and uk_live.value >= 5.25),
        bool(it and it.value >= 4.75 and "it10" not in stale),
        bool(spread_bp is not None and spread_bp >= 125),
    ])
    if stress_count >= 2 or (fr and "fr10" not in stale and fr.value >= 5.0):
        level, emoji = "유럽 장기금리 고수준 경계", "🔴"
    elif any(e.get("type") == "trigger" for e in events):
        level, emoji = "유럽 장기금리 상승 경계", "🟠"
    else:
        level, emoji = "금리 상승 속도 둔화·수준 별도 확인", "🟡"

    lines = [
        f"{emoji} [유럽 국채금리 경보] {level}",
        "",
        f"■ 조회: {now.strftime('%Y-%m-%d %H:%M')} 한국시간",
        "※ 시장 보조자료는 당일 확정 종가가 아닌 조회 시점의 제공값입니다.",
        "",
        "■ 지금 숫자",
    ]
    if fr and "fr10" not in stale:
        lines.append(f"🇫🇷 Banque de France TEC10 {fr.value:.3f}% / 직전 공식 관측일 대비 {signed_bp(changes.get('fr10_day_bp'))} / 기준일 {fr.date}")
    if fr_mkt and "fr_mkt" not in stale:
        lines.append(f"   ↳ 프랑스 10년 시장수익률 {fr_mkt.value:.3f}% / 기준일 {fr_mkt.date} (Trading Economics 보조 시장자료)")
    if it and "it10" not in stale:
        lines.append(f"🇮🇹 이탈리아 10년 시장수익률 {it.value:.3f}% / 출처 표기 전 거래일 대비 {signed_bp(changes.get('it10_day_bp'))} / 기준일 {it.date}")
    if uk and "uk10" not in stale:
        lines.append(f"🇬🇧 BoE 10년 명목 파수익률 {uk.value:.3f}% / 직전 공식 관측일 대비 {signed_bp(changes.get('uk10_day_bp'))} / 기준일 {uk.date}")
    elif uk_mkt and "uk_mkt" not in stale:
        lines.append(f"🇬🇧 영국 10년 시장수익률 {uk_mkt.value:.3f}% / 출처 표기 전 거래일 대비 {signed_bp(changes.get('uk_mkt_day_bp'))} / 기준일 {uk_mkt.date} (BoE 공식값 후행으로 Trading Economics 보조 시장자료 사용)")
    if de and "de10" not in stale:
        suffix = ""
        lines.append(f"🇩🇪 Bundesbank 10년 {de.value:.3f}% / 직전 공식 관측일 대비 {signed_bp(changes.get('de10_day_bp'))} / 기준일 {de.date}{suffix}")
    if de_mkt and "de_mkt" not in stale:
        lines.append(f"   ↳ 독일 10년 시장수익률 {de_mkt.value:.3f}% / 기준일 {de_mkt.date} (Trading Economics 보조 시장자료)")
    if spread_bp is not None:
        lines.append(f"🇫🇷-🇩🇪 동일 시장자료 기준 금리차 {spread_bp:.1f}bp")

    lines += ["", "■ 무엇이 바뀌었나"]
    for e in events[:8]:
        prefix = "• 경계 진입:" if e["type"] == "trigger" else "• 경계 해제:"
        lines.append(f"{prefix} {e['summary']}")

    lines += [
        "",
        "■ 왜 중요한가",
        "• ECB 정책금리와 별개입니다. 시장의 10년 국채금리가 오르면 정부·기업·주택의 실제 장기 차입비용과 주식 할인율이 올라갑니다.",
        "• 프랑스-독일 금리차는 동일 제공사·동일 기준일의 시장금리로 계산합니다. 산출방식 또는 날짜가 다르면 계산하지 않습니다.",
        "",
        "■ 시장 영향",
        "• 성장주·리츠·고부채 기업: 할인율·자금조달비용 상승 부담.",
        "• 은행: 순이자마진 개선 가능성과 국채 평가손실·신용비용 상승을 함께 봐야 합니다.",
        "• 유로: 프랑스-독일 금리차가 더 벌어지면 유로존 분절 위험이 커질 수 있습니다.",
        "",
        "■ 다음 경계",
        "• 감시 기준: 프랑스 TEC10 5.00% / 영국 10년 5.50% / 프랑스-독일 동일 시장자료 금리차 150bp.",
        "• 하루 +10bp 또는 최근 5개 관측치 +25bp면 속도 경보를 별도로 냅니다.",
        "• 속도 경계 해제는 금리 수준의 위험 해소를 뜻하지 않습니다.",
        "• 위 숫자는 ECB·BoE의 공식 위기선이 아니라 변동성 확대를 빨리 잡기 위한 내부 감시 기준입니다.",
        "",
        "■ 출처",
    ]
    if fr:
        lines.append(f"• Banque de France TEC10: {fr.source}")
    if de:
        lines.append(f"• Deutsche Bundesbank 10Y: {DE_PAGE}")
    if uk:
        lines.append(f"• Bank of England IUDMNPY: {uk.source}")
    if it:
        lines.append(f"• Italy 10Y Trading Economics 보조 시장자료: {it.source}")
    if fr_mkt:
        lines.append(f"• France 10Y Trading Economics 보조 시장자료: {fr_mkt.source}")
    if de_mkt:
        lines.append(f"• Germany 10Y Trading Economics 보조 시장자료: {de_mkt.source}")
    if uk_mkt:
        lines.append(f"• UK 10Y Trading Economics 보조 시장자료: {uk_mkt.source}")
    if stale:
        stale_names = {"uk10": "영국 중앙은행 공식 10년물",
                       "fr10": "프랑스 중앙은행 TEC10",
                       "de10": "독일 중앙은행 10년물"}
        dated = [f"{stale_names.get(k, k)} ({latest[k].date})" for k in stale if k in latest]
        lines += ["", "※ 기준일이 늦은 자료는 신규 경보에서 제외: " + ", ".join(dated)]
    if errors:
        lines += ["※ 일부 보조 소스는 확인 불가였지만, 해당 값은 경보 계산에서 제외했습니다. 상세 오류는 실행 상태에만 기록합니다."]

    detail = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "level": level,
        "events": events,
        "latest": {k: {"date": v.date, "value": v.value, "source": v.source} for k, v in latest.items()},
        "changes": changes,
        "change_basis": {k: ("출처 명시 변화" if k in MARKET_URLS else "공식 직전 관측치 차이") for k in latest},
        "fr_de_spread_bp": spread_bp,
        "stale": stale,
        "errors": errors,
    }
    detail["signature"] = hashlib.sha256(json.dumps(detail["events"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
    return f"유럽 국채금리 경보 — {level}", "\n".join(lines), detail


def finalize() -> int:
    if not PENDING.exists():
        return 0
    if ALERT.exists() and not CONFIRMED.exists():
        raise RuntimeError("유럽 국채금리 알림이 생성됐지만 Telegram 전송 확인이 없어 상태를 확정하지 않습니다.")
    DATA.mkdir(parents=True, exist_ok=True)
    STATE.write_text(PENDING.read_text(encoding="utf-8"), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        return finalize()

    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    for p in (PENDING, ALERT, TITLE, DETAIL, CONFIRMED):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    now = dt.datetime.now(KST)
    state = load_json(STATE, {})
    errors = []
    all_rows: dict[str, list[Obs]] = {}

    source_jobs = (
        ("fr10", lambda: fetch_france(now)),
        ("de10", fetch_germany),
        ("uk10", lambda: fetch_uk(now)),
        ("fr_mkt", lambda: fetch_market_history("fr_mkt", "프랑스 10년 시장수익률")),
        ("de_mkt", lambda: fetch_market_history("de_mkt", "독일 10년 시장수익률")),
        ("it10", lambda: fetch_market_history("it10", "이탈리아 10년 시장수익률")),
        ("uk_mkt", lambda: fetch_market_history("uk_mkt", "영국 10년 시장수익률")),
    )
    for key, fn in source_jobs:
        try:
            all_rows[key] = fn()
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

    latest = {}
    prev = {}
    stale = []
    changes = {}
    history = dict(state.get("history") or {})

    change_basis: dict[str, str] = {}
    for key, rows in all_rows.items():
        cur, _ = latest_two(rows)
        if cur:
            latest[key] = cur
            tz = LONDON if key in {"uk10", "uk_mkt"} else PARIS
            if business_lag_days(cur, now, tz) > MAX_BUSINESS_LAG:
                stale.append(key)
            old = previous_trading_observation(cur, rows, state)
            if key in MARKET_URLS:
                # Cached intraday quotes are not prior-day closes. Never call
                # such same-day movements a "previous-day change".
                if cur.daily_bp is not None:
                    changes[f"{key}_day_bp"] = cur.daily_bp
                    change_basis[key] = "자료제공사가 명시한 전 거래일 대비"
            elif old is not None:
                prev[key] = old
                changes[f"{key}_day_bp"] = bp(cur.value, old.value)
                change_basis[key] = f"공식자료 이전 관측일 {old.date} 대비"
            if len(rows) >= 5:
                changes[f"{key}_5obs_bp"] = bp(rows[-1].value, rows[-5].value)
            history[key] = merge_daily_history(state, key, cur)

    active = dict(state.get("active") or {})
    events = []

    def fresh(key: str) -> bool:
        return key in latest and key not in stale

    # Official hard levels for France/Germany; UK uses the official series when fresh.
    # Italy is monitored from the current benchmark market series because Banca d'Italia
    # does not publish a timely daily benchmark 10Y series.
    for key, levels, label in (
        ("fr10", FR_LEVELS, "프랑스 TEC10"),
        ("de10", DE_LEVELS, "독일 10년(Bundesbank)"),
        ("it10", IT_LEVELS, "이탈리아 10년 시장수익률"),
    ):
        if not fresh(key):
            continue
        value = latest[key].value
        for level in levels:
            k = f"{key}:above:{level}"
            mark_event(events, active, state, k, value >= level, f"{label} {level:.2f}% 이상 ({value:.3f}%)", clear_summary=f"{label} {level:.2f}% 아래로 하락 ({value:.3f}%)")
        d1 = changes.get(f"{key}_day_bp")
        if d1 is not None:
            mark_event(events, active, state, f"{key}:daymove:{DAILY_MOVE_BP}", d1 >= DAILY_MOVE_BP, f"{label} 하루 +{DAILY_MOVE_BP:.0f}bp 이상 급등 ({d1:+.1f}bp)", clear_summary=f"{label} 하루 급등 속도 정상화 ({d1:+.1f}bp)")
        d5 = changes.get(f"{key}_5obs_bp")
        if d5 is not None:
            mark_event(events, active, state, f"{key}:5obs:{FIVE_OBS_MOVE_BP}", d5 >= FIVE_OBS_MOVE_BP, f"{label} 최근 5개 관측치 +{FIVE_OBS_MOVE_BP:.0f}bp 이상 ({d5:+.1f}bp)", clear_summary=f"{label} 5개 관측치 급등 속도 정상화 ({d5:+.1f}bp)")

    # UK official curve is sometimes published with a lag. Use the official BoE
    # series when fresh, otherwise the same-day market fallback, but keep one
    # logical alert key so source switching cannot create duplicate threshold alerts.
    uk_source_key = "uk10" if fresh("uk10") else "uk_mkt" if fresh("uk_mkt") else None
    if uk_source_key:
        uk_value = latest[uk_source_key].value
        uk_label = "영국 10년(BoE)" if uk_source_key == "uk10" else "영국 10년 시장수익률"
        for level in UK_LEVELS:
            k = f"uk10:above:{level}"
            mark_event(
                events, active, state, k, uk_value >= level,
                f"{uk_label} {level:.2f}% 이상 ({uk_value:.3f}%)",
                clear_summary=f"{uk_label} {level:.2f}% 아래로 하락 ({uk_value:.3f}%)",
            )
        uk_day = changes.get(f"{uk_source_key}_day_bp")
        if uk_day is not None:
            mark_event(
                events, active, state, f"uk10:daymove:{DAILY_MOVE_BP}",
                uk_day >= DAILY_MOVE_BP,
                f"{uk_label} 하루 +{DAILY_MOVE_BP:.0f}bp 이상 급등 ({uk_day:+.1f}bp)",
                clear_summary=f"{uk_label} 하루 급등 속도 정상화 ({uk_day:+.1f}bp)",
            )

    # Comparable spread must use the same market-data methodology/provider.
    # Do NOT mix Banque de France TEC10 with a Bundesbank benchmark and call the
    # arithmetic difference a market risk premium.
    spread_bp = comparable_market_spread(latest, stale)
    if spread_bp is not None:
        for level in FR_DE_SPREAD_LEVELS_BP:
            mark_event(
                events, active, state, f"fr_de_market_spread:above:{level}", spread_bp >= level,
                f"프랑스-독일 10년 시장금리차 {level:.0f}bp 이상 ({spread_bp:.1f}bp)",
                clear_summary=f"프랑스-독일 10년 시장금리차 {level:.0f}bp 아래 ({spread_bp:.1f}bp)",
            )

    coverage = coverage_by_country(latest, stale)
    enough_coverage = sum(coverage.values()) >= 2
    bad_streak = 0 if enough_coverage else int(state.get("source_fail_streak") or 0) + 1
    health_alert = (
        bad_streak >= 4
        and not state.get("coverage_outage_alerted", False)
        and not events
    )

    next_state = {
        "last_checked_kst": now.isoformat(timespec="seconds"),
        "active": active,
        "history": history,
        "source_fail_streak": bad_streak,
        "coverage_outage_alerted": bool(
            health_alert or (not enough_coverage and state.get("coverage_outage_alerted", False))
        ),
        "country_coverage": coverage,
        "last_source_dates": {k: v.date for k, v in latest.items()},
        "last_values": {k: v.value for k, v in latest.items()},
        "last_change_basis": change_basis,
        "stale": stale,
    }
    PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = [
        "# 유럽 국채금리 감시",
        "",
        f"- 조회: {now.isoformat(timespec='seconds')}",
        f"- 정상 소스: {', '.join(sorted(latest)) if latest else '없음'}",
        f"- 후행 소스: {', '.join(stale) if stale else '없음'}",
        f"- 신규/해제 경보: {len(events)}건",
        f"- 유효 국가별 자료: {sum(coverage.values())}/4개국",
        f"- 데이터 부족 연속: {bad_streak}회",
        f"- 수집 장애 경보: {'예' if health_alert else '아니오'}",
    ]
    for k, v in latest.items():
        status.append(f"- {v.label}: {v.value:.3f}% ({v.date})")
    if spread_bp is not None:
        status.append(f"- 프랑스-독일 10년 동일 시장자료 금리차: {spread_bp:.1f}bp")
    if errors:
        status += ["", "## 일부 소스 오류"] + [f"- {x}" for x in errors]
    STATUS.write_text("\n".join(status) + "\n", encoding="utf-8")

    if events:
        title, body, detail = build_alert(latest, changes, spread_bp, events, stale, errors, now)
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body.strip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif health_alert:
        # Distinguish a monitoring failure from a genuine market stress event.
        title = "유럽 국채금리 감시 — 자료 수집 장애"
        body = "\n".join([
            "🟠 [유럽 국채금리 감시 장애] 자료 부족 — 금리 급등 경보가 아닙니다.",
            "",
            f"■ 조회: {now.strftime('%Y-%m-%d %H:%M')} 한국시간",
            f"• 정상 확인 국가 {sum(coverage.values())}/4개국, 연속 부족 {bad_streak}회",
            "• 확인되지 않은 수치로 금리차·급등을 계산하지 않았습니다.",
            "• 시장 경보가 지연될 수 있으므로 공식 자료를 직접 확인해 주십시오.",
            "",
            "■ 자료",
            "• Banque de France TEC10: https://www.banque-france.fr",
            f"• Deutsche Bundesbank 10Y: {DE_PAGE}",
            f"• Bank of England IUDMNPY: {UK_VIEW}",
            f"• Italy 10Y Trading Economics 보조 시장자료: {MARKET_URLS['it10']}",
        ])
        detail = {"kind": "source_health", "country_coverage": coverage,
                  "fail_streak": bad_streak, "checked_at_kst": now.isoformat(timespec="seconds")}
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

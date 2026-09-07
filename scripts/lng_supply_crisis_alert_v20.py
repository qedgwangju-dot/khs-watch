#!/usr/bin/env python3
"""LNG 공급·가격 감시 v20: 독일/미국 10년물을 공식 일일 원천으로 전환."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import urllib.request
import xml.etree.ElementTree as ET

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v19 as v19

UTC = dt.timezone.utc
BUNDESBANK_10Y_CSV = (
    "https://api.statistiken.bundesbank.de/rest/data/BBSSY/"
    "D.REN.EUR.A630.000000WT1010.A?format=csv&lang=en"
)
UST_XML_2026 = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value=2026"
)
MAX_OFFICIAL_AGE_DAYS = 5
AUG4 = dt.date(2026, 8, 4)


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 khs-lng-europe-rates-alert/20.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def parse_bundesbank_csv(raw: bytes) -> list[tuple[dt.date, float]]:
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        up = line.upper()
        if "TIME_PERIOD" in up and "OBS_VALUE" in up:
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError("Bundesbank CSV TIME_PERIOD/OBS_VALUE header not found")
    sample = "\n".join(lines[header_idx:header_idx + 5])
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except Exception:
        delimiter = ";"
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])), delimiter=delimiter)
    out: list[tuple[dt.date, float]] = []
    for row in reader:
        if not row:
            continue
        normalized = {str(k).strip().upper(): (v or "").strip() for k, v in row.items() if k is not None}
        period = normalized.get("TIME_PERIOD", "")
        value = normalized.get("OBS_VALUE", "")
        if not period or not value:
            continue
        try:
            date = dt.date.fromisoformat(period[:10])
            val = float(value.replace(",", "."))
        except Exception:
            continue
        out.append((date, val))
    out = sorted(set(out))
    if len(out) < 3:
        raise RuntimeError("Bundesbank CSV too few observations")
    return out


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_treasury_xml(raw: bytes) -> list[tuple[dt.date, float]]:
    root = ET.fromstring(raw)
    out: list[tuple[dt.date, float]] = []
    for entry in root.iter():
        if _local_name(entry.tag) != "entry":
            continue
        date_text = None
        y10_text = None
        for node in entry.iter():
            name = _local_name(node.tag).upper()
            if name == "NEW_DATE" and node.text:
                date_text = node.text.strip()
            elif name == "BC_10YEAR" and node.text:
                y10_text = node.text.strip()
        if date_text and y10_text:
            try:
                out.append((dt.date.fromisoformat(date_text[:10]), float(y10_text)))
            except Exception:
                pass
    out = sorted(set(out))
    if len(out) < 3:
        raise RuntimeError("US Treasury XML too few 10Y observations")
    return out


def _series_snapshot(series: list[tuple[dt.date, float]], source: str) -> dict[str, object]:
    latest_date, latest = series[-1]
    previous_date, previous = series[-2]
    today = core.now_utc().astimezone(core.KST).date()
    age_days = (today - latest_date).days
    if age_days < 0 or age_days > MAX_OFFICIAL_AGE_DAYS:
        raise RuntimeError(f"official bond source stale source={source} date={latest_date} age={age_days}d")
    lookup = dict(series)
    if AUG4 not in lookup:
        raise RuntimeError(f"official bond source missing Aug 4 source={source}")
    return {
        "latest_date": latest_date,
        "latest": latest,
        "previous_date": previous_date,
        "previous": previous,
        "aug4": float(lookup[AUG4]),
        "lookup": lookup,
        "source": source,
    }


def fetch_official_bond_snapshots() -> tuple[dict[str, object], dict[str, object]]:
    bund = _series_snapshot(
        parse_bundesbank_csv(_fetch_bytes(BUNDESBANK_10Y_CSV)),
        "Deutsche Bundesbank BBSSY.D.REN.EUR.A630.000000WT1010.A",
    )
    us = _series_snapshot(
        parse_treasury_xml(_fetch_bytes(UST_XML_2026)),
        "U.S. Treasury Daily Treasury Par Yield Curve 10Y",
    )
    common_date = min(bund["latest_date"], us["latest_date"])
    bund_lookup = bund["lookup"]
    us_lookup = us["lookup"]
    common_candidates = sorted(set(bund_lookup).intersection(us_lookup))
    common_candidates = [d for d in common_candidates if AUG4 <= d <= common_date]
    if not common_candidates:
        raise RuntimeError("no common official Germany/US 10Y comparison date")
    common_date = common_candidates[-1]
    bund["common_date"] = common_date
    us["common_date"] = common_date
    bund["common_value"] = float(bund_lookup[common_date])
    us["common_value"] = float(us_lookup[common_date])
    bund["common_since_aug4_bp"] = (float(bund["common_value"]) - float(bund["aug4"])) * 100.0
    us["common_since_aug4_bp"] = (float(us["common_value"]) - float(us["aug4"])) * 100.0
    return bund, us


def _make_quote(key: str, snap: dict[str, object]) -> core.Quote:
    latest = float(snap["latest"])
    previous = float(snap["previous"])
    observed = core.now_utc()
    since_aug4 = (latest - float(snap["aug4"])) * 100.0
    return core.Quote(
        key=key,
        symbol=str(core.PRICE_SPECS[key]["symbol"]),
        label=("독일 10년 현행 연방채(분데스방크 공식)" if key == "bund10" else "미국 10년 Treasury(미 재무부 공식)"),
        unit="bp",
        price=latest * 100.0,
        previous_close=previous * 100.0,
        change_pct=(latest / previous - 1.0) * 100.0 if previous else 0.0,
        timestamp_epoch=observed.timestamp(),
        timestamp_utc=observed.isoformat(timespec="seconds"),
        age_minutes=0,
        source_note=(
            f"official daily series; basis_date={snap['latest_date']}; previous_date={snap['previous_date']}; "
            f"aug4={float(snap['aug4']):.4f}; since_aug4_bp={since_aug4:+.1f}; "
            f"common_date={snap['common_date']}; common_value={float(snap['common_value']):.4f}; "
            f"common_since_aug4_bp={float(snap['common_since_aug4_bp']):+.1f}; source={snap['source']}"
        ),
    )


_base_fetch_market_quotes = v19.fetch_market_quotes_v19
_base_apply_hysteresis = v19.apply_hysteresis_v19
_base_format_quote = v19.format_quote_v19


def fetch_market_quotes_v20():
    # v19의 비공식 bond quote는 버리고 기존 LNG/에너지 quote만 유지한 뒤 공식 bond를 덮어쓴다.
    quotes, errors = _base_fetch_market_quotes()
    quotes.pop("bund10", None)
    quotes.pop("us10", None)
    errors = [e for e in errors if not (e.startswith("bund10:") or e.startswith("us10:"))]
    try:
        bund, us = fetch_official_bond_snapshots()
        quotes["bund10"] = _make_quote("bund10", bund)
        quotes["us10"] = _make_quote("us10", us)
    except Exception as exc:
        errors.append(f"official_bonds: {type(exc).__name__}: {exc}")
    return quotes, errors


def _common_delta(quote: core.Quote) -> float | None:
    m = re.search(r"common_since_aug4_bp=([+-]?[0-9.]+)", quote.source_note)
    return float(m.group(1)) if m else None


def _common_date(quote: core.Quote) -> str | None:
    m = re.search(r"common_date=(\d{4}-\d{2}-\d{2})", quote.source_note)
    return m.group(1) if m else None


def apply_hysteresis_v20(quotes, previous_signals):
    current = _base_apply_hysteresis(quotes, previous_signals)
    # v19의 비동일 날짜 상대비교 신호를 제거하고 공통 영업일 기준으로 다시 판정한다.
    current.discard("bund10_rise_leads_us10_5bp")
    bund = quotes.get("bund10")
    us = quotes.get("us10")
    if bund and us:
        de = _common_delta(bund)
        usa = _common_delta(us)
        if de is not None and usa is not None:
            lead = de - usa
            if lead >= 5.0:
                current.add("bund10_rise_leads_us10_5bp")
            elif lead < 3.0:
                current.discard("bund10_rise_leads_us10_5bp")
    return current


def format_quote_v20(quote: core.Quote) -> str:
    if quote.key not in ("bund10", "us10"):
        return _base_format_quote(quote)
    basis = re.search(r"basis_date=(\d{4}-\d{2}-\d{2})", quote.source_note)
    previous_date = re.search(r"previous_date=(\d{4}-\d{2}-\d{2})", quote.source_note)
    delta = v19._aug4_delta_bp(quote)
    aug = re.search(r"aug4=([0-9.]+)", quote.source_note)
    current_pct = quote.price / 100.0
    previous_pct = quote.previous_close / 100.0
    day_bp = (current_pct - previous_pct) * 100.0
    return (
        f"{quote.label} <b>{current_pct:.3f}%</b> · {previous_date.group(1) if previous_date else '직전'} "
        f"{previous_pct:.3f}% 대비 {day_bp:+.1f}bp · 8/4 {float(aug.group(1)):.3f}% 대비 "
        f"{delta:+.1f}bp · 기준 {basis.group(1) if basis else '미확인'}"
    )


def build_regular_alert_v20(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v19.build_regular_alert_v19(groups, quotes, new_signals, cleared_signals)
    bund = quotes.get("bund10")
    us = quotes.get("us10")
    if bund and us and ("유럽 가스·채권금리 스트레스 경보" in title or any(s.startswith("bund10_") for s in set(new_signals) | set(cleared_signals))):
        de = _common_delta(bund)
        usa = _common_delta(us)
        date = _common_date(bund)
        if de is not None and usa is not None and date:
            line = (
                f"• <b>8/4 이후 동일 종가 기준 상대 매도강도</b> 공통 기준일 {date} · "
                f"독일 {de:+.1f}bp vs 미국 {usa:+.1f}bp · 독일이 <b>{de-usa:+.1f}bp</b> 더 상승"
            )
            body = re.sub(r"• <b>8/4 이후 상대 매도강도</b>[^\n]*", line, body)
            if line not in body:
                body += "\n" + line
        body += (
            "\n• <b>채권 수치 원천</b> 독일=Deutsche Bundesbank 현행 10년 연방채 공식 일일 시계열 · "
            "미국=U.S. Treasury 공식 Daily Treasury Par Yield Curve 10Y · 서로 다른 장중 호가를 억지로 비교하지 않고 공통 영업일 종가로 상대상승폭 계산"
        )
    metadata["version"] = 20
    metadata["official_bond_sources"] = {
        "germany_10y": "Bundesbank BBSSY.D.REN.EUR.A630.000000WT1010.A",
        "us_10y": "U.S. Treasury Daily Treasury Par Yield Curve 10Y",
        "relative_method": "Aug 4 to latest common observation date",
        "max_age_days": MAX_OFFICIAL_AGE_DAYS,
    }
    return title, body, metadata


def build_setup_test_v20(quotes):
    title, body, metadata = v19.build_setup_test_v19(quotes)
    title = "✅ LNG·유럽 채권금리 전이 감시 v20 적용"
    body += (
        "\n\n<b>공식 채권 수치 원천</b>"
        "\n• 독일 10년: Deutsche Bundesbank 현행 10년 연방채 공식 일일 시계열"
        "\n• 미국 10년: U.S. Treasury 공식 Daily Treasury Par Yield Curve"
        "\n• 8/4 이후 독일↔미국 상대상승폭은 양쪽에 모두 존재하는 최신 공통 영업일 종가로 계산"
        "\n• 공식값이 5일보다 오래되거나 8/4 기준값이 없으면 숫자 경보 보류"
    )
    metadata["version"] = 20
    return title, body, metadata


core.fetch_market_quotes = fetch_market_quotes_v20
core.apply_hysteresis = apply_hysteresis_v20
core.format_quote = format_quote_v20
core.build_regular_alert = build_regular_alert_v20
core.build_setup_test = build_setup_test_v20

if __name__ == "__main__":
    raise SystemExit(core.main())

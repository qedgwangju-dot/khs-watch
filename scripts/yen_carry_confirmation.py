#!/usr/bin/env python3
"""Daily confirmation layer for the global-rates / yen-carry watchers.

Current USD/JPY direction is handled by the dedicated live FX layer. This module is
for *daily market-contagion confirmation* and therefore prefers each index publisher:
- VIX: Cboe daily closing file, with Cboe current summary as a freshness supplement
- Nasdaq Composite: Nasdaq Global Index Watch
- Nikkei 225: Nikkei Indexes historical data
FRED remains a same-series fallback where useful; missing confirmation data never
creates a positive carry-unwind signal.
"""
from __future__ import annotations

import csv
import html
import io
import json
import pathlib
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import yen_carry_target_currency_confirmation as target_currency

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
UA = "khs-watch-yen-carry-confirmation/1.5"

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
CBOE_VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
CBOE_VIX_PAGE = "https://www.cboe.com/tradable-products/vix"
NASDAQ_COMP = "https://indexes.nasdaq.com/Index/Overview/COMP"
NIKKEI_225 = "https://indexes.nikkei.co.jp/en/nkave/archives/data"


def _request_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/csv,text/html,application/xhtml+xml,*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def _number(value: str) -> float:
    return float(str(value).replace(",", "").replace("$", "").strip())


def _iso_from_us(value: str) -> str:
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return value.strip()


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def _parse_cboe_vix(text: str) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        keys = {str(k).strip().upper(): v for k, v in row.items() if k is not None}
        date = str(keys.get("DATE") or "").strip()
        close = str(keys.get("CLOSE") or "").strip()
        if not date or not close:
            continue
        try:
            rows.append((_iso_from_us(date), _number(close)))
        except ValueError:
            continue
    if len(rows) < 2:
        raise RuntimeError(f"Cboe VIX daily file insufficient: {len(rows)}")
    return rows


def _parse_cboe_vix_page(text: str) -> tuple[str, float, float] | None:
    plain = _plain(text)
    date_match = re.search(
        r"as of\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})",
        plain,
        flags=re.IGNORECASE,
    )
    price_match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s+VIX\s+Spot\s+Price", plain, flags=re.IGNORECASE)
    change_match = re.search(
        r"Change\s*([+-]?\d+(?:\.\d+)?)%\s*\(([+-]?\d+(?:\.\d+)?)\)",
        plain,
        flags=re.IGNORECASE,
    )
    if not change_match:
        # Cboe's current page renders the percentage/point change before the
        # literal "Change" label (e.g. "3.23% (0.49) Change").
        change_match = re.search(
            r"([+-]?\d+(?:\.\d+)?)%\s*\(([+-]?\d+(?:\.\d+)?)\)\s*Change",
            plain,
            flags=re.IGNORECASE,
        )
    if not date_match or not price_match or not change_match:
        return None
    month_names = {name.lower(): idx for idx, name in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], start=1
    )}
    month = month_names[date_match.group(1).lower()]
    date = f"{int(date_match.group(3)):04d}-{month:02d}-{int(date_match.group(2)):02d}"
    current = _number(price_match.group(1))
    delta = _number(change_match.group(2))
    previous = current - delta
    if previous <= 0:
        return None
    return date, current, previous


def _get_cboe_vix() -> list[tuple[str, float]]:
    rows = _parse_cboe_vix(_request_text(CBOE_VIX_CSV, timeout=15))
    try:
        current = _parse_cboe_vix_page(_request_text(CBOE_VIX_PAGE, timeout=8))
        if current:
            date, value, previous = current
            if date > rows[-1][0]:
                rows.append((date, value))
            elif date == rows[-1][0]:
                rows[-1] = (date, value)
            elif len(rows) < 2:
                rows = [("이전 거래일", previous), (date, value)]
    except Exception:
        pass
    return rows


def _parse_nasdaq_comp(text: str) -> list[tuple[str, float]]:
    plain = _plain(text)
    # Read date, index value and net change from the same official headline block.
    # This avoids hidden/stale Previous Close elements elsewhere in the page DOM.
    match = re.search(
        r"DATA\s+AS\s+OF\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+(?:\.\d+)?)\s+([+-]?[\d,]+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)%",
        plain,
        flags=re.IGNORECASE,
    )
    if not match:
        raise RuntimeError("Nasdaq COMP official headline not found")
    date = _iso_from_us(match.group(1))
    current = _number(match.group(2))
    net_change = _number(match.group(3))
    previous = current - net_change
    if previous <= 0:
        raise RuntimeError("Nasdaq COMP derived previous close invalid")
    return [("이전 거래일", previous), (date, current)]


def _parse_nikkei_225(text: str) -> list[tuple[str, float]]:
    plain = _plain(text)
    months = {name: idx for idx, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1
    )}
    found: list[tuple[str, float]] = []
    pattern = re.compile(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/(\d{1,2})/(\d{4})\s+"
        r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)"
    )
    for month, day, year, _open, _high, _low, close in pattern.findall(plain):
        try:
            iso = f"{int(year):04d}-{months[month]:02d}-{int(day):02d}"
            found.append((iso, _number(close)))
        except (ValueError, KeyError):
            continue
    found = sorted(dict(found).items())
    if len(found) < 2:
        raise RuntimeError(f"Nikkei 225 official history insufficient: {len(found)}")
    return found


def _parse_fred(series: str, text: str) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        date = (row.get("DATE") or row.get("observation_date") or "").strip()
        raw = (row.get(series) or "").strip()
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if date:
            rows.append((date, value))
    return rows


def _fred_fallback(series: str) -> tuple[list[tuple[str, float]], str]:
    url = FRED_CSV + "?" + urllib.parse.urlencode({"id": series})
    rows = _parse_fred(series, _request_text(url, timeout=7))
    if len(rows) < 2:
        raise RuntimeError(f"FRED {series} insufficient: {len(rows)}")
    return rows, "FRED 일간"


def get(series: str, n: int = 5) -> tuple[list[tuple[str, float]], str]:
    errors: list[str] = []
    try:
        if series == "VIXCLS":
            rows = _get_cboe_vix()
            return rows[-n:], "Cboe 공식 일간 종가"
        if series == "NASDAQCOM":
            rows = _parse_nasdaq_comp(_request_text(NASDAQ_COMP, timeout=15))
            return rows[-n:], "Nasdaq 공식 지수"
        if series == "NIKKEI225":
            rows = _parse_nikkei_225(_request_text(NIKKEI_225, timeout=15))
            return rows[-n:], "Nikkei 공식 지수"
    except Exception as exc:
        errors.append(f"공식 제공처 {type(exc).__name__}: {exc}")

    try:
        rows, label = _fred_fallback(series)
        return rows[-n:], label
    except Exception as exc:
        errors.append(f"FRED {type(exc).__name__}: {exc}")

    raise RuntimeError(f"{series}: official routes failed: {' | '.join(errors)}")


def pct(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def main() -> None:
    now = datetime.now(KST)
    data: dict[str, dict] = {}
    errors: list[str] = []

    # USD/JPY current direction is already decided by the live query1/query2 layer.
    # This module only needs the three downstream daily contagion indicators.
    series_list = ["VIXCLS", "NASDAQCOM", "NIKKEI225"]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(get, series): series for series in series_list}
        for future in as_completed(futures):
            series = futures[future]
            try:
                rows, source = future.result()
                d0, v0 = rows[-1]
                d1, v1 = rows[-2]
                data[series] = {
                    "date": d0,
                    "value": v0,
                    "prev_date": d1,
                    "prev": v1,
                    "change_pct": pct(v0, v1),
                    "source": source,
                }
            except Exception as exc:
                errors.append(f"{series}: {type(exc).__name__}: {exc}")

    signals = {
        "yen_strength_daily_2pct": False,
        "vix_spike_20pct": data.get("VIXCLS", {}).get("change_pct", 0) >= 20.0,
        "nasdaq_down_2pct": data.get("NASDAQCOM", {}).get("change_pct", 0) <= -2.0,
        "nikkei_down_2pct": data.get("NIKKEI225", {}).get("change_pct", 0) <= -2.0,
    }
    equity_joint = signals["nasdaq_down_2pct"] and signals["nikkei_down_2pct"]
    confirm_count = sum(bool(signals[key]) for key in ("vix_spike_20pct", "nasdaq_down_2pct", "nikkei_down_2pct"))

    result = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "data": data,
        "signals": signals,
        "equity_joint_weakness": equity_joint,
        "confirmation_count": confirm_count,
        "errors": errors,
        "note": "USD/JPY 방향은 실시간 FX 층에서 판정. VIX·Nasdaq·Nikkei는 각 공식 지수 제공처 우선, 동일 지표 FRED 일간값을 대체 경로로 사용.",
    }
    (OUT / "yen_carry_confirmation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = ["# 엔캐리 후행 확인", "", f"- 조회시각(KST): {result['checked_at_kst']}"]
    names = {"VIXCLS": "VIX", "NASDAQCOM": "Nasdaq Composite", "NIKKEI225": "Nikkei 225"}
    for series, name in names.items():
        item = data.get(series)
        if item:
            lines.append(
                f"- {name}: {item['value']:.4f} ({item['change_pct']:+.2f}%, 기준일 {item['date']}, {item['source']})"
            )
    lines += [
        "",
        "- USD/JPY 급등락: 별도 실시간 FX 층에서 판정",
        f"- VIX 일간 +20% 이상: {'예' if signals['vix_spike_20pct'] else '아니오'}",
        f"- Nasdaq -2% 이하: {'예' if signals['nasdaq_down_2pct'] else '아니오'}",
        f"- Nikkei -2% 이하: {'예' if signals['nikkei_down_2pct'] else '아니오'}",
        f"- Nikkei/Nasdaq 동반 약세 확인: {'예' if equity_joint else '아니오'}",
        "",
        "※ VIX·Nasdaq·Nikkei는 선행조건이 아니라 실제 디레버리징이 위험자산으로 번졌는지 보는 일간 후행 확인 신호입니다.",
        "※ 공식 지수 제공처가 우선이며, 해당 경로가 실패할 때만 동일 지표의 FRED 일간값을 사용합니다.",
        "※ BOJ 시장 내재 인상확률은 신뢰 가능한 자동 시계열이 확보되기 전까지 임의 계산하지 않습니다.",
    ]
    if errors:
        lines += ["", "## 확인 불가"] + [f"- {error}" for error in errors]
    (OUT / "yen_carry_confirmation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))

    try:
        target_currency.process()
    except Exception as exc:
        print(f"target_currency_confirmation_failed={type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()

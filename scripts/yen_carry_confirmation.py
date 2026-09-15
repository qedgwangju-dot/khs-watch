#!/usr/bin/env python3
"""Secondary confirmation layer for the global-rates watcher.

Uses daily public FRED series to confirm whether a JGB/rate warning is spreading into
FX volatility and equities. This is deliberately a *confirmation* layer, not a real-time
market feed.

Series:
- DEXJPUS   : Japanese yen to U.S. dollar exchange rate (yen per USD)
- VIXCLS    : CBOE VIX
- NASDAQCOM : Nasdaq Composite
- NIKKEI225 : Nikkei 225

Also invokes the intraday MXN/JPY, BRL/JPY and ZAR/JPY carry-target confirmation layer.
Outputs out/yen_carry_confirmation.json and .md.
"""
from __future__ import annotations

import csv
import html
import io
import json
import pathlib
import re
import urllib.error
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
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_TABLE = "https://fred.stlouisfed.org/data/{series}"
UA = "khs-watch-yen-carry-confirmation/1.3"


def _request_text(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig", errors="replace")


def _parse_csv(series: str, text: str) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        date = (row.get("DATE") or row.get("observation_date") or "").strip()
        raw = (row.get(series) or "").strip()
        try:
            val = float(raw)
        except Exception:
            continue
        if date:
            rows.append((date, val))
    return rows


def _parse_fred_table(text: str) -> list[tuple[str, float]]:
    # FRED's /data/<SERIES> page exposes the same official DATE/VALUE table.
    # Strip markup and recover only strict ISO-date/value pairs so navigation text
    # cannot be misread as an observation.
    plain = html.unescape(re.sub(r"<[^>]+>", " ", text))
    rows: list[tuple[str, float]] = []
    for date, raw in re.findall(r"(\d{4}-\d{2}-\d{2})\s+(-?\d+(?:\.\d+)?)", plain):
        try:
            rows.append((date, float(raw)))
        except ValueError:
            continue
    # Preserve order while dropping duplicate date/value renderings.
    dedup: dict[str, float] = {}
    for date, value in rows:
        dedup[date] = value
    return sorted(dedup.items())


def get(series: str, n: int = 5):
    errors: list[str] = []
    csv_url = FRED_CSV + "?" + urllib.parse.urlencode({"id": series})
    try:
        rows = _parse_csv(series, _request_text(csv_url, timeout=8))
        if len(rows) >= 2:
            return rows[-n:], "FRED CSV"
        errors.append(f"CSV insufficient data: {len(rows)}")
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        errors.append(f"CSV {type(exc).__name__}: {exc}")

    table_url = FRED_TABLE.format(series=urllib.parse.quote(series, safe=""))
    try:
        rows = _parse_fred_table(_request_text(table_url, timeout=12))
        if len(rows) >= 2:
            return rows[-n:], "FRED 표 데이터"
        errors.append(f"table insufficient data: {len(rows)}")
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        errors.append(f"table {type(exc).__name__}: {exc}")

    raise RuntimeError(f"{series}: official FRED routes failed: {' | '.join(errors)}")


def pct(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def main():
    now = datetime.now(KST)
    data = {}
    errors = []
    series_list = ["DEXJPUS", "VIXCLS", "NASDAQCOM", "NIKKEI225"]

    # Two workers avoid hammering FRED while preventing four slow routes from
    # serially blocking the watcher. Each series has an independent official
    # CSV -> FRED table fallback and never substitutes an unrelated provider.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(get, series): series for series in series_list}
        for future in as_completed(futures):
            s = futures[future]
            try:
                rows, source = future.result()
                d0, v0 = rows[-1]
                d1, v1 = rows[-2]
                data[s] = {
                    "date": d0,
                    "value": v0,
                    "prev_date": d1,
                    "prev": v1,
                    "change_pct": pct(v0, v1),
                    "source": source,
                }
            except Exception as e:
                errors.append(f"{s}: {type(e).__name__}: {e}")

    signals = {
        "yen_strength_daily_2pct": data.get("DEXJPUS", {}).get("change_pct", 0) <= -2.0,
        "vix_spike_20pct": data.get("VIXCLS", {}).get("change_pct", 0) >= 20.0,
        "nasdaq_down_2pct": data.get("NASDAQCOM", {}).get("change_pct", 0) <= -2.0,
        "nikkei_down_2pct": data.get("NIKKEI225", {}).get("change_pct", 0) <= -2.0,
    }
    equity_joint = signals["nasdaq_down_2pct"] and signals["nikkei_down_2pct"]
    confirm_count = sum(bool(v) for v in signals.values())

    result = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "data": data,
        "signals": signals,
        "equity_joint_weakness": equity_joint,
        "confirmation_count": confirm_count,
        "errors": errors,
        "note": "FRED daily-close confirmation only. BOJ OIS is not estimated without a reliable market source.",
    }
    (OUT / "yen_carry_confirmation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# 엔캐리 후행 확인", "", f"- 조회시각(KST): {result['checked_at_kst']}"]
    names = {"DEXJPUS":"USD/JPY", "VIXCLS":"VIX", "NASDAQCOM":"Nasdaq Composite", "NIKKEI225":"Nikkei 225"}
    for s, name in names.items():
        x = data.get(s)
        if x:
            lines.append(f"- {name}: {x['value']:.4f} ({x['change_pct']:+.2f}%, 기준일 {x['date']}, {x.get('source','FRED')})")
    lines += [
        "",
        f"- USD/JPY 일간 -2% 이하: {'예' if signals['yen_strength_daily_2pct'] else '아니오'}",
        f"- VIX 일간 +20% 이상: {'예' if signals['vix_spike_20pct'] else '아니오'}",
        f"- Nasdaq -2% 이하: {'예' if signals['nasdaq_down_2pct'] else '아니오'}",
        f"- Nikkei -2% 이하: {'예' if signals['nikkei_down_2pct'] else '아니오'}",
        f"- Nikkei/Nasdaq 동반 약세 확인: {'예' if equity_joint else '아니오'}",
        "",
        "※ Nikkei·Nasdaq·VIX는 엔캐리 청산의 선행조건이 아니라 실제 디레버리징이 위험자산으로 번졌는지 보는 FRED 일간 후행 확인 신호입니다.",
        "※ BOJ OIS 인상확률은 신뢰 가능한 자동 시계열이 확보되기 전까지 임의 계산하지 않습니다.",
    ]
    if errors:
        lines += ["", "## 확인 불가"] + [f"- {e}" for e in errors]
    (OUT / "yen_carry_confirmation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))

    # Intraday carry-target confirmation is supplemental. A retrieval failure here must not
    # suppress the established rates/FX lane; missing target data are excluded from risk scoring.
    try:
        target_currency.process()
    except Exception as exc:
        print(f"target_currency_confirmation_failed={type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()

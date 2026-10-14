"""Product-specific LS investor channels shared by the two index monitors.

Amounts from t8463 and t1640 retain their provider scale. The public guide
does not establish a currency scale. No spot/futures/program amounts are added.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import threading
import time
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
MARKET_SPECS = {
    "KOSPI": {"spot_market": "1", "upcode": "001", "asset": "K2I",
              "futures_label": "KOSPI200 선물", "program": ("11", "12", "13")},
    "KOSDAQ": {"spot_market": "3", "upcode": "301", "asset": "KQI",
               "futures_label": "KOSDAQ150 선물", "program": ("21", "22", "23")},
}

# Both market collectors run in threads. Rate limits apply to the TR, rather
# than independently to each market. Waiting here never blocks price polling.
_PACE_LOCKS = {tr: threading.Lock() for tr in ("t1602", "t1640", "t8463")}
_NEXT_CALL = {tr: 0.0 for tr in _PACE_LOCKS}


def pace(tr: str) -> None:
    lock = _PACE_LOCKS.get(tr)
    if lock is None:
        return
    with lock:
        delay = _NEXT_CALL[tr] - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _NEXT_CALL[tr] = time.monotonic() + 1.1


def number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        result = float(str(value).replace(",", ""))
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None


def decoded_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def futures_request(market: str) -> dict:
    spec = MARKET_SPECS[market]
    return {"t8463InBlock": {"tm_rng": "D", "fot_clsf_cd": "F",
                            "bsc_asts_id": spec["asset"], "cnt": 100, "bgubun": "0"}}


def parse_futures(body: dict, market: str, received_ts: float) -> dict:
    """Require the echoed product/session plus the provider's dated clock."""
    spec = MARKET_SPECS[market]
    summary = body.get("t8463OutBlock") or {}
    expected = {"tm_rng": "D", "fot_clsf_cd": "F", "bsc_asts_id": spec["asset"]}
    if any(str(summary.get(k) or "").strip() != v for k, v in expected.items()):
        raise ValueError("t8463 product/session echo mismatch or missing")
    rows = body.get("t8463OutBlock1") or []
    if isinstance(rows, dict):
        rows = [rows]
    today = dt.datetime.fromtimestamp(received_ts, KST).strftime("%Y%m%d")
    valid = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_asset = str(row.get("bsc_asts_id") or "").strip()
        if row_asset and row_asset != spec["asset"]:
            raise ValueError("t8463 row product conflicts with summary")
        day, clock = str(row.get("date") or "").strip(), str(row.get("time") or "").strip()
        if day != today or len(clock) != 6 or not clock.isdigit():
            continue
        stamp = str(row.get("datetime") or "").strip()
        # LS's own example has date-only datetime. It is not a full clock.
        if stamp and stamp not in (day, day + clock):
            raise ValueError("t8463 dated clock fields conflict")
        try:
            ts = dt.datetime.strptime(day + clock, "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp()
        except ValueError:
            continue
        if ts > received_ts + 5:
            continue
        values = {actor: number(row.get(field)) for actor, field in
                  (("개인", "indmsamt"), ("외국인", "formsamt"), ("기관", "sysmsamt"))}
        if any(v is None for v in values.values()):
            continue
        valid.append((ts, row, values))
    if not valid:
        raise ValueError("t8463 no complete current-day investor row")
    ts, row, values = max(valid, key=lambda item: item[0])
    return {"market": market, "asset": spec["asset"], "source_tr": "t8463",
            "source_scope_verified": True, "sample_ts": ts, "received_ts": received_ts,
            "timestamp_basis": "provider_date_time", "time": row["time"], "date": row["date"],
            "unit": "LS_raw_amount", "unit_verified": False,
            "request": futures_request(market), "summary": summary, "source_row": row,
            "decoded_response_json_sha256": decoded_hash(body), **values}


def futures_current(token: str, market: str, post) -> dict:
    body = post(token, "/futureoption/investor", "t8463", futures_request(market),
                max_attempts=2, request_timeout=8.0)
    return parse_futures(body, market, time.time())


def program_current(token: str, market: str, post) -> dict:
    """Keep all three query intervals; receipt time is not a source timestamp."""
    items = []
    for gubun in MARKET_SPECS[market]["program"]:
        started = time.time()
        request = {"t1640InBlock": {"gubun": gubun, "exchgubun": "U"}}
        body = post(token, "/stock/program", "t1640", request,
                    max_attempts=2, request_timeout=8.0)
        ended = time.time()
        row = body.get("t1640OutBlock")
        if not isinstance(row, dict) or number(row.get("value")) is None:
            raise ValueError("t1640 missing cumulative amount")
        if row.get("gubun") is not None and str(row["gubun"]).strip() != gubun:
            raise ValueError("t1640 market/component echo conflicts")
        items.append({"request": request, "row": row, "query_started_ts": started,
                      "received_ts": ended, "decoded_response_json_sha256": decoded_hash(body)})
    total, arb, nonarb = [number(item["row"]["value"]) for item in items]
    started, ended = items[0]["query_started_ts"], items[-1]["received_ts"]
    return {"market": market, "source_tr": "t1640", "source_scope_verified": True,
            "unit": "LS_raw_amount", "unit_verified": False,
            "timestamp_basis": "query_interval", "source_time_verified": False,
            "query_started_ts": started, "received_ts": ended,
            # Use the interval's end, never its midpoint before data was known.
            "sample_ts": ended, "time": dt.datetime.fromtimestamp(ended, KST).strftime("%H%M%S"),
            "전체": total, "차익": arb, "비차익": nonarb,
            "베이시스": number(items[0]["row"].get("basis")),
            "차익비차익합": arb + nonarb, "전체대비차이": total - arb - nonarb,
            "표본시차초": ended - started, "source_queries": items}


def block_scope_matches(block: dict, market: str, channel: str) -> bool:
    """Legacy spot history stays useful; it never acquires missing channels."""
    if block.get("market") is not None and block["market"] != market:
        return False
    if channel == "지수선물":
        return (block.get("source_tr") == "t8463"
                and block.get("asset") == MARKET_SPECS[market]["asset"]
                and block.get("source_scope_verified") is True)
    if channel == "프로그램" and market == "KOSDAQ":
        return block.get("source_tr") == "t1640" and block.get("market") == market
    return True

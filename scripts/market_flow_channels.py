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

from market_investors import PRIMARY_ACTORS

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

# 기관계의 세부 업종은 중복 합산하지 않는다. LS가 따로 반환하는
# 개인/외국인/기관계/기타/국가만 같은 행 안에서 검산한다.
FUTURES_INVESTORS = {
    "개인": ("ind", "0008"), "외국인": ("for", "0009"),
    "기관": ("sys", "0018"), "기타": ("etc", "0007"),
    "국가": ("nat", "0011"),
}


class FuturesInvestorQualityError(ValueError):
    def __init__(self, evidence: dict):
        self.evidence = evidence
        super().__init__("t8463 investor reconciliation failed: "
                         + "; ".join(evidence["investor_quality"]["issues"]))


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
                            "bsc_asts_id": spec["asset"], "cnt": 10, "bgubun": "0"}}


def futures_investor_quality(summary: dict, row: dict) -> dict:
    """A dated row can still be partially updated. Zero is not sufficient proof."""
    summary = summary if isinstance(summary, dict) else {}
    row = row if isinstance(row, dict) else {}
    issues, amounts, volumes = [], {}, {}
    for actor, (prefix, code) in FUTURES_INVESTORS.items():
        if str(summary.get(prefix + "code") or "").strip() != code:
            issues.append(actor + " 투자자코드 미확인/불일치")
        amounts[actor] = number(row.get(prefix + "msamt"))
        volumes[actor] = number(row.get(prefix + "msvol"))
        if amounts[actor] is None or volumes[actor] is None:
            issues.append(actor + " 순매수 금액/수량 누락")
        elif not volumes[actor].is_integer():
            issues.append(actor + " 순매수 수량이 정수가 아님")
    amount_sum = sum(amounts.values()) if all(x is not None for x in amounts.values()) else None
    volume_sum = sum(volumes.values()) if all(x is not None for x in volumes.values()) else None
    # 계약 수량에는 반올림을 허용하지 않는다. 정수로 공표된 금액은
    # 다섯 집단 각각 원값 1 이내의 표시 차이만 허용하며 통화 단위를 추정하지 않는다.
    if volume_sum is not None and volume_sum != 0:
        issues.append(f"전체 투자자 순매수 수량 합계 {volume_sum:+g} (필요 0)")
    if amount_sum is not None and abs(amount_sum) > len(FUTURES_INVESTORS):
        issues.append(f"전체 투자자 순매수 금액 합계 {amount_sum:+g} (허용 원값 ±5)")
    return {"verified": not issues, "issues": issues, "amounts": amounts, "volumes": volumes,
            "amount_sum": amount_sum, "volume_sum": volume_sum,
            "amount_rounding_tolerance_raw": len(FUTURES_INVESTORS)}


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
        valid.append((ts, row, values))
    if not valid:
        raise ValueError("t8463 no complete current-day investor row")
    ts, row, values = max(valid, key=lambda item: item[0])
    if any(v is None for v in values.values()):
        raise ValueError("t8463 latest row missing investor amount")
    # inv is the institutional subgroup, not an additional reconciliation
    # bucket. An absent/mismatched subgroup must not invalidate its parent.
    trust_amount = number(row.get("invmsamt"))
    trust_volume = number(row.get("invmsvol"))
    trust_valid = (str(summary.get("invcode") or "").strip() == "0003"
                   and trust_amount is not None and trust_volume is not None
                   and trust_volume.is_integer())
    values["투신"] = trust_amount if trust_valid else None
    financial_amount = number(row.get("stomsamt"))
    financial_volume = number(row.get("stomsvol"))
    financial_valid = (str(summary.get("stocode") or "").strip() == "0001"
                       and financial_amount is not None and financial_volume is not None
                       and financial_volume.is_integer())
    values["금융투자"] = financial_amount if financial_valid else None
    result = {"market": market, "asset": spec["asset"], "source_tr": "t8463",
            "source_scope_verified": True, "sample_ts": ts, "received_ts": received_ts,
            "timestamp_basis": "provider_date_time", "time": row["time"], "date": row["date"],
            "unit": "LS_raw_amount", "unit_verified": False,
            "request": futures_request(market), "summary": summary, "source_row": row,
            "actor_quality": {"투신": {"verified": trust_valid, "parent": "기관",
                "code": summary.get("invcode"), "amount_field": "invmsamt",
                "volume_field": "invmsvol", "included_in_reconciliation": False,
                "reason": None if trust_valid else "투신 코드0003·금액·수량 확인 부족"},
                "금융투자": {"verified": financial_valid, "parent": "기관", "provider_label": "증권",
                    "code": summary.get("stocode"), "amount_field": "stomsamt", "volume_field": "stomsvol",
                    "included_in_reconciliation": False,
                    "reason": None if financial_valid else "증권 코드0001·금액·수량 확인 부족"}},
            "decoded_response_json_sha256": decoded_hash(body), **values}
    if market == "KOSDAQ":
        result["investor_quality"] = futures_investor_quality(summary, row)
        if not result["investor_quality"]["verified"]:
            # Reject the latest row; never substitute an older complete row.
            raise FuturesInvestorQualityError(result)
    return result


def futures_current(token: str, market: str, post) -> dict:
    body = post(token, "/futureoption/investor", "t8463", futures_request(market),
                max_attempts=1, request_timeout=25.0)
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
    if block.get("source_tr") == "ka90005":
        return (channel == "프로그램" and block.get("market") == market
                and block.get("source_scope_verified") is True
                and block.get("unit_verified") is True and block.get("unit") == "억원"
                and block.get("independent_population_unit_and_clock_verified") is True)
    if channel == "지수선물":
        quality = futures_investor_quality(block.get("summary"), block.get("source_row")) if market == "KOSDAQ" else None
        return (block.get("source_tr") == "t8463"
                and block.get("asset") == MARKET_SPECS[market]["asset"]
                and block.get("source_scope_verified") is True
                and (market != "KOSDAQ" or (
                    quality["verified"] and all(number(block.get(actor)) == quality["amounts"][actor]
                                                for actor in PRIMARY_ACTORS))))
    if channel == "프로그램" and market == "KOSDAQ":
        return block.get("source_tr") == "t1640" and block.get("market") == market
    return True

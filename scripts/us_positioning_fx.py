"""Dated ECOS USD/KRW observations for US positioning amount conversions.

The parser and verifier perform no I/O.  Collection delegates preservation of
the actual HTTP response to the supplied reader, with an explicitly redacted
evidence URL when the ECOS credential is part of the request path.  A missing
observation stays unavailable; this module never substitutes another date or
another provider's rate.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import os
import re
from urllib.parse import quote


ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
ECOS_HOME = "https://ecos.bok.or.kr/"
STAT_CODE = "731Y001"
ITEM_CODE = "0000001"
ITEM_NAME = "원/미국달러(매매기준율)"
SOURCE = "한국은행 ECOS 원/미국달러(매매기준율)"
BASIS = "정확히 요청일의 공식 일별 매매기준율 · 1미국달러당 원"

_REASONS = {
    "requested_date": "ECOS 요청 기준일을 확인할 수 없음",
    "response_format": "ECOS 원응답 형식을 확인할 수 없음",
    "duplicate_fields": "ECOS 원응답에 중복된 필드가 있음",
    "response_error": "ECOS가 오류 또는 자료 없음 응답을 반환함",
    "row_count": "ECOS 요청일의 유일한 관측 행을 확인할 수 없음",
    "series": "ECOS 통계 코드 또는 통화 항목이 일치하지 않음",
    "unit": "ECOS 원/미국달러 매매기준율 단위가 원으로 확인되지 않음",
    "observation_date": "ECOS 관측일이 정확한 요청 기준일과 일치하지 않음",
    "rate": "ECOS 환율이 양수의 유한한 십진수로 확인되지 않음",
    "collection": "ECOS 원자료 조회에 실패함",
}


class _InvalidFx(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(_REASONS[code])


def _date(value):
    if type(value) is dt.date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise _InvalidFx("requested_date")
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise _InvalidFx("requested_date") from None


def _unavailable(requested_date, code):
    return {
        "status": "unavailable",
        "requested_date": requested_date,
        "date": None,
        "reason_code": code,
        "reason": _REASONS[code] + " · 원화 환산 보류",
    }


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise _InvalidFx("duplicate_fields")
        out[key] = value
    return out


def _payload(value):
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value, object_pairs_hook=_unique_pairs)
        except _InvalidFx:
            raise
        except (UnicodeError, ValueError, TypeError):
            raise _InvalidFx("response_format") from None
    if not isinstance(value, dict):
        raise _InvalidFx("response_format")
    return value


def _rate(value):
    # DATA_VALUE is a decimal string in the ECOS response.  Reject booleans,
    # floats and exponent/underscore syntax rather than coercing their values.
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+)?", value):
        raise _InvalidFx("rate")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        raise _InvalidFx("rate") from None
    if not parsed.is_finite() or parsed <= 0:
        raise _InvalidFx("rate")
    return format(parsed, "f")


def parse_ecos_usdkrw(payload, requested_date):
    """Return a verified semantic snapshot or an explicit unavailable result.

    Only the exact requested calendar date is accepted.  Both a duplicate row
    and a response reporting more observations than it supplied are rejected.
    Required source operands remain available for independent recomputation.
    Errors use fixed reason codes and never quote an upstream error message.
    """
    try:
        target = _date(requested_date)
    except _InvalidFx as exc:
        return _unavailable(None, exc.code)
    requested = target.isoformat()
    try:
        document = _payload(payload)
        if "RESULT" in document:
            raise _InvalidFx("response_error")
        block = document.get("StatisticSearch")
        if not isinstance(block, dict):
            raise _InvalidFx("response_format")
        if "RESULT" in block:
            raise _InvalidFx("response_error")
        rows = block.get("row")
        count = block.get("list_total_count")
        if type(count) is not int or count != 1 or not isinstance(rows, list) or len(rows) != 1:
            raise _InvalidFx("row_count")
        row = rows[0]
        if not isinstance(row, dict):
            raise _InvalidFx("response_format")
        if (row.get("STAT_CODE") != STAT_CODE or row.get("ITEM_CODE1") != ITEM_CODE
                or row.get("ITEM_NAME1") != ITEM_NAME
                or any(row.get(f"ITEM_CODE{n}") not in (None, "") for n in (2, 3, 4))):
            raise _InvalidFx("series")
        if row.get("UNIT_NAME") != "원":
            raise _InvalidFx("unit")
        if row.get("TIME") != target.strftime("%Y%m%d"):
            raise _InvalidFx("observation_date")
        rate = _rate(row.get("DATA_VALUE"))
        # Whitelist the source operands.  Unrelated API metadata and timestamps
        # cannot introduce volatility or credentials into the semantic snapshot.
        source_row = {key: row[key] for key in (
            "STAT_CODE", "ITEM_CODE1", "ITEM_NAME1", "UNIT_NAME", "TIME", "DATA_VALUE",
        )}
        return {
            "status": "verified",
            "requested_date": requested,
            "date": requested,
            "krw_per_usd": rate,
            "base_currency": "USD",
            "quote_currency": "KRW",
            "unit": "원/미국달러",
            "basis": BASIS,
            "source": SOURCE,
            "source_url": ECOS_HOME,
            "operands": {"StatisticSearch": {"list_total_count": 1, "row": [source_row]}},
        }
    except _InvalidFx as exc:
        return _unavailable(requested, exc.code)


def collect_fx(reader, requested_date):
    """Collect an exact-date ECOS observation, preserving response via reader.

    ``reader.get`` must support ``evidence_url`` and redact its diagnostics as
    well as its ledger URL.  ECOS_API_KEY takes precedence over the compatible
    BOK_ECOS_API_KEY name.  Without either key, the official sample endpoint is
    used with its limit of ten rows.  No key or exception text is returned.
    """
    try:
        target = _date(requested_date)
    except _InvalidFx as exc:
        return _unavailable(None, exc.code)
    key = (os.getenv("ECOS_API_KEY") or "").strip() or (os.getenv("BOK_ECOS_API_KEY") or "").strip()
    segment = quote(key, safe="") if key else "sample"
    redacted_segment = "[REDACTED]" if key else "sample"
    tail = f"/json/kr/1/10/{STAT_CODE}/D/{target:%Y%m%d}/{target:%Y%m%d}/{ITEM_CODE}"
    try:
        raw = reader.get(f"{ECOS_BASE}/{segment}{tail}",
                         evidence_url=f"{ECOS_BASE}/{redacted_segment}{tail}")
    except Exception:
        return _unavailable(target.isoformat(), "collection")
    return parse_ecos_usdkrw(raw, target)


def checked_fx(value, requested_date=None):
    """Return a snapshot only if every semantic field matches its operands.

    This rejects forged conversion amounts, changed source/unit/date labels,
    and unexpected volatile metadata.  Renderers must use the returned snapshot
    and its Decimal string rather than an unverified stored FX value.
    """
    if not isinstance(value, dict) or value.get("status") != "verified":
        return None
    try:
        target = _date(requested_date if requested_date is not None else value.get("requested_date"))
        computed = parse_ecos_usdkrw(value.get("operands"), target)
        return value if computed.get("status") == "verified" and computed == value else None
    except (TypeError, ValueError, KeyError):
        return None

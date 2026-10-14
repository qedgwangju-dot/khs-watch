"""Read-only industry context for an existing KOSDAQ five-minute buy alert.

UBM msval is a cumulative net-buy amount. LS's public UBM field guide does not
specify its currency multiplier, so it is used for ranking only, never KRW
conversion. Both payload receipt time and the preserved LS clock must be at or
before each market boundary and within 30 seconds of it. No interpolation,
future observations, investor mixing, or standalone industry alerts are used.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from kospi_shock_enrichment import _display_name, _is_real_industry

KST = ZoneInfo("Asia/Seoul")
INVESTORS = {"개인": "0008", "외국인": "0017", "기관": "0018"}
MAX_GAP_SEC = 30.0
SOURCE = "LS UBM 통합 업종별투자자별매매현황"
GUIDE_URL = "https://openapi.ls-sec.co.kr/apiservice?api_id=9a2800c3-9bf2-4d67-8d83-905074f06646"


def _number(value: Any) -> float | None:
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            return None
        result = float(str(value).replace(",", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _industry(code: str, name: str) -> bool:
    return bool(re.fullmatch(r"3\d{2}", code) and code != "301" and 0 < len(name) <= 60
                and name != code and "코스닥" not in name and "KOSDAQ" not in name.upper()
                and _is_real_industry(name, code))


def _clock(value: Any, received_ts: float) -> float | None:
    """Never substitute receipt time for a missing/invalid upstream clock."""
    digits = str(value or "").strip()
    if not re.fullmatch(r"\d{6}(?:\d{2})?", digits):
        return None
    try:
        day = dt.datetime.fromtimestamp(received_ts, KST)
        return day.replace(hour=int(digits[:2]), minute=int(digits[2:4]),
                           second=int(digits[4:6]), microsecond=0).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _time(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, KST).strftime("%H:%M:%S")


def industry_buy_context(start_ts: float, end_ts: float, investor: str,
                         *, path: Path | None = None,
                         session_open_ts: float | None = None) -> dict[str, Any]:
    """Rank positive cumulative changes among independently aligned industries.

    The current journal can be appended while we read it. An unfinished final
    JSON line is excluded; malformed complete records are reported in coverage.
    Same-clock UBM updates are valid, but only payloads actually received before
    the selected boundary can contribute to that boundary.
    """
    block: dict[str, Any] = {
        "version": "kosdaq-surge-industries-v1", "market": "KOSDAQ",
        "investor": investor, "requested_window": [start_ts, end_ts],
        "available": False, "rows": [], "top": [], "source": SOURCE,
        "source_guide": GUIDE_URL, "source_unit": "UNVERIFIED",
        "display_unit": None, "unit_verified": False,
        "unit_reason": "공식 UBM msval 필드 설명에 금액 단위 없음",
        "ranking_basis": "positive end_msval - start_msval",
        "max_gap_sec": MAX_GAP_SEC, "covered_industries": 0,
        "observed_industries": 0, "expected_industries": None,
        "coverage_complete": False, "excluded": {},
    }

    def hold(reason: str) -> dict[str, Any]:
        block["reason"] = reason
        return block

    start, end = _number(start_ts), _number(end_ts)
    if investor not in INVESTORS or start is None or end is None or not 300 <= end - start <= 330:
        return hold("같은 투자자의 유효한 5분 구간 없음")
    try:
        start_day = dt.datetime.fromtimestamp(start, KST).date()
        end_day = dt.datetime.fromtimestamp(end, KST).date()
    except (ValueError, OverflowError, OSError):
        return hold("업종 기준점의 시각 확인 불가")
    if start_day != end_day:
        return hold("업종 기준점의 거래일 불일치")
    if session_open_ts is None or start < session_open_ts:
        return hold("정규장 시작 이후의 기준점 확인 불가")
    p = path or Path(os.getenv("KOSPI_INDUSTRY_FLOW_PATH", "out/kospi_industry_flow.jsonl"))
    try:
        payload = p.read_bytes()
    except OSError:
        return hold("업종 수급 자료 없음 또는 읽기 실패")
    block["journal_sha256"] = hashlib.sha256(payload).hexdigest()
    block["journal_bytes"] = len(payload)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tainted: dict[str, list[float]] = defaultdict(list)
    expected: set[str] | None = None
    invalid: dict[str, int] = defaultdict(int)

    def taint(code: str, row: dict[str, Any]) -> None:
        received = _number(row.get("received_ts"))
        if received is not None and start - MAX_GAP_SEC <= received <= end:
            tainted[code].append(received)

    lines = payload.splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError):
            # A concurrently written trailing fragment is not a source record.
            key = "incomplete_tail" if index == len(lines) - 1 and not line.endswith(b"\n") else "malformed_json"
            invalid[key] += 1
            continue
        if not isinstance(row, dict):
            invalid["invalid_record"] += 1
            continue
        if row.get("record_type") == "subscription_coverage":
            stamp = _number(row.get("ts"))
            if (row.get("market") == "KOSDAQ" and row.get("source_tr") == "UBM"
                    and stamp is not None and session_open_ts - 3600 <= stamp <= end
                    and dt.datetime.fromtimestamp(stamp, KST).date() == start_day):
                items = row.get("expected")
                if isinstance(items, list):
                    expected = {str(x.get("code")) for x in items if isinstance(x, dict)
                                and _industry(str(x.get("code")), _display_name(x.get("name")))}
            continue
        if row.get("investor") != investor:
            continue
        code = str(row.get("upcode") or "").strip()
        name = _display_name(row.get("industry"))
        if not _industry(code, name):
            if re.fullmatch(r"3\d{2}", code) and (not name or len(name) > 60 or name == code):
                taint(code, row)
                invalid["invalid_industry_name"] += 1
            continue
        # The preserved exchange code proves an integrated subscription; K/N
        # observations and actor-name/code contradictions cannot be accepted.
        if (row.get("ex_upcode") != "U" + code
                or row.get("source_tr", "UBM") != "UBM"):
            invalid["exchange_or_source_mismatch"] += 1
            continue
        if row.get("investor_code") != INVESTORS[investor]:
            taint(code, row)
            invalid["actor_mismatch"] += 1
            continue
        if row.get("source_unit") not in (None, "UNVERIFIED"):
            taint(code, row)
            invalid["incompatible_unit"] += 1
            continue
        received = _number(row.get("received_ts"))
        source = _clock(row.get("source_time"), received) if received is not None else None
        stored_source = _number(row.get("source_ts"))
        value = _number(row.get("msval"))
        if (received is None or source is None or stored_source is None or value is None
                or abs(source - stored_source) > 0.01 or source > received
                or dt.datetime.fromtimestamp(source, KST).date() != start_day):
            invalid["invalid_value_or_clock"] += 1
            taint(code, row)
            continue
        if source < session_open_ts or received > end or received < start - MAX_GAP_SEC:
            continue
        grouped[code].append({
            "code": code, "name": name, "msval": value,
            "received_ts": received, "source_ts": source,
            "source_time": row["source_time"], "ex_upcode": row["ex_upcode"],
            "investor_code": row["investor_code"],
        })
    block["observed_industries"] = len(grouped)
    block["expected_industries"] = len(expected) if expected is not None else None
    for code, rows in grouped.items():
        if expected is not None and code not in expected:
            invalid["outside_master"] += 1
            continue
        points = []
        for target in (start, end):
            prior = [x for x in rows if x["received_ts"] <= target and x["source_ts"] <= target]
            if not prior:
                break
            latest = max(x["received_ts"] for x in prior)
            if any(latest <= ts <= target for ts in tainted[code]):
                invalid["invalid_latest_boundary"] += 1
                break
            choices = [x for x in prior if x["received_ts"] == latest]
            if len({(x["msval"], x["source_ts"], x["name"]) for x in choices}) != 1:
                invalid["conflicting_boundary"] += 1
                break
            point = choices[-1]
            if max(target - point["received_ts"], target - point["source_ts"]) > MAX_GAP_SEC:
                break
            points.append(point)
        if len(points) != 2:
            invalid["unaligned_industry"] += 1
            continue
        a, b = points
        if a["source_ts"] >= b["source_ts"] or a["name"] != b["name"]:
            invalid["incompatible_boundaries"] += 1
            continue
        delta = b["msval"] - a["msval"]
        if not math.isfinite(delta):
            invalid["nonfinite_delta"] += 1
            continue
        block["rows"].append({
            "code": code, "name": b["name"], "investor": investor,
            "delta_raw": delta, "start_value_raw": a["msval"], "end_value_raw": b["msval"],
            "start": a, "end": b,
            "start_gap_sec": start - a["source_ts"], "end_gap_sec": end - b["source_ts"],
            "start_received_gap_sec": start - a["received_ts"],
            "end_received_gap_sec": end - b["received_ts"],
        })
    block["rows"].sort(key=lambda x: (-x["delta_raw"], x["code"]))
    block["covered_industries"] = len(block["rows"])
    block["coverage_complete"] = bool(expected and {x["code"] for x in block["rows"]} == expected
                                      and not invalid.get("malformed_json") and not invalid.get("invalid_record"))
    block["excluded"] = dict(invalid)
    block["top"] = [x for x in block["rows"] if x["delta_raw"] > 0][:3]
    block["available"] = bool(block["top"])
    block["reason"] = None if block["top"] else (
        "확인된 업종에 순매수 증가 없음" if block["rows"] else "같은 구간의 업종 기준점·원자료 시각 확인 부족")
    return block


def industry_context_lines(block: dict[str, Any] | None, investor: str,
                           start_ts: float, end_ts: float) -> list[str]:
    if (not block or block.get("market") != "KOSDAQ" or block.get("investor") != investor
            or block.get("requested_window") != [start_ts, end_ts]):
        return ["• 업종 순매수 증가 확인 보류 — 같은 투자자·구간의 자료 없음"]
    top = block.get("top") or []
    coverage = f"확인 {block['covered_industries']}개"
    expected = block.get("expected_industries")
    if expected is not None:
        coverage += f" / 수집 대상 {expected}개"
    coverage += " · 전체 업종 순위 확정 보류" if not block.get("coverage_complete") else " · 수집 대상 모두 정렬 확인"
    if not top:
        return [f"• 업종 순매수 증가 확인 보류 — {html.escape(str(block.get('reason') or '자료 부족'))}",
                "• 업종 확인 범위: " + coverage]
    lines = [f"• <b>{html.escape(investor)} 업종 순매수 증가 상위 {len(top)}개</b> (확인된 업종 기준)"]
    for rank, row in enumerate(top, 1):
        lines.append(f"  {rank}. <b>{html.escape(row['name'])}</b> · 표본 {_time(row['start']['source_ts'])}~{_time(row['end']['source_ts'])}")
    lines += ["• 업종 확인 범위: " + coverage,
              "• 전체 수급과 같은 구간 조회 · 업종 기준점 시차 최대 30초",
              "• 업종 금액: 원자료 단위 미확인으로 표시 보류"]
    return lines

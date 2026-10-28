#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import base64
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from kospi_shock_enrichment import build_enrichment, build_kosdaq_enrichment
from kosdaq_surge_industries import industry_buy_context, industry_context_lines
from krx_session_calendar import session_state
from market_flow_channels import (
    MARKET_SPECS, pace, block_scope_matches, futures_current,
    FuturesInvestorQualityError,
    program_current as market_program_current,
)
from market_program_close import collect as collect_program_close, render as render_program_close
from market_alert_delivery import DeliveryUncertain, delivery_context, receipt_for, send_message
from market_investors import (ALERT_ACTORS, DISPLAY_ACTORS, PRIMARY_ACTORS, LEADER_NOTE,
                              TRUST_NOTE, SUBGROUP_NOTE, FINANCIAL_NOTE, actor_label,
                              trust_direction_lines, trust_value, subgroup_value, subgroup_direction_lines)
from market_supplementary_flow import enrich_snapshot, cash_lines

KST = ZoneInfo("Asia/Seoul")
BASE = "https://openapi.ls-sec.co.kr:8080"
STATUS = Path("out/kospi_shock_episode_status.md")
RAW = Path("out/kospi_shock_episode_raw.json")
DELIVERY_LOG = Path("out/kospi_shock_delivery_log.jsonl")
KOSPI_URL = "https://m.stock.naver.com/domestic/index/KOSPI/total"
LS_URL = "https://openapi.ls-sec.co.kr/apiservice"
NEWS_URL = "https://search.naver.com/search.naver?where=news&query=" + urllib.parse.quote("코스피 급락")

PRICE_LOOKBACK_SEC = 3 * 60 * 60
FLOW_LOOKBACK_SEC = 4 * 60 * 60
FLOW_INTERVAL_SEC = 15
NEW_LOW_CONFIRM_SEC = 240
MAX_EPISODE_SEC = 3 * 60 * 60
MAX_FLOW_ALIGNMENT_SEC = 30
MAX_FLOW_HEALTH_AGE_SEC = 90.0  # API 응답 시각과 원자료 시각을 따로 확인한다.
MAX_PROGRAM_SNAPSHOT_SKEW_SEC = 8.0
MAX_PROGRAM_CROSSCHECK_RATIO_PCT = 1.0  # 1% 초과면 방향이 같아도 높은 확신도 부여 금지
OPEN_GAP_ALERT_PCT = -1.0
# 장중 가격 급락과 독립된 5분 수급 급유입 감시 (최초 보수적 기준값).
# t1602 현물/선물은 억원 표기, t1640 프로그램은 원값을 유지한다.
SURGE_WINDOW_SEC = 5 * 60
SURGE_MAX_SAMPLE_SKEW_SEC = 30.0
SURGE_MAX_END_AGE_SEC = 45.0
SURGE_CONFIRM_SEC = 10.0
SURGE_COOLDOWN_SEC = 20 * 60
SURGE_COMBINED_SPOT_EOK = 300.0
SURGE_COMBINED_FUT_EOK = 450.0
SURGE_SINGLE_SPOT_EOK = 900.0
SURGE_SINGLE_FUT_EOK = 1300.0
# 코스닥은 KOSPI200 선물과 섞지 않고 현물 독립 신호로 감시한다.
KOSDAQ_SURGE_PREALERT_SPOT_EOK = 100.0
KOSDAQ_SURGE_SINGLE_SPOT_EOK = 150.0
KOSDAQ_SURGE_ACTORS = DISPLAY_ACTORS
KOSDAQ_URL = "https://m.stock.naver.com/domestic/index/KOSDAQ/total"
KOSDAQ_NEWS_URL = "https://search.naver.com/search.naver?where=news&query=" + urllib.parse.quote("코스닥 급락")
# 코스닥 가격/수급은 같은 기존 프로세스의 독립 상태로 관리하며 코스피 수급·파생과 합산하지 않는다.
KOSDAQ_PRICE_POLL_INTERVAL_SEC = 5.0
KOSDAQ_PRICE_MAX_AGE_SEC = 30.0
FLOW_SURGE_ALERT_CONTRACT = "market-flow-surge-v1"



def fnum(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        result = float(str(v).replace(",", "").strip())
        return result if math.isfinite(result) else None
    except Exception:
        return None


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b / a - 1.0) * 100.0


def fmt_clock(ts: float | None) -> str:
    if ts is None:
        return "확인 불가"
    return dt.datetime.fromtimestamp(ts, KST).strftime("%H:%M:%S")


def ko_subject(name: str | None) -> str:
    text = str(name or "").strip()
    if not text:
        return text
    last = ord(text[-1])
    if 0xAC00 <= last <= 0xD7A3:
        return text + ("이" if (last - 0xAC00) % 28 else "가")
    return text + "가"


def market_clock_epoch(value: Any, fallback_ts: float | None = None) -> float | None:
    """원자료 HHMMSS가 유효할 때만 사건구간 기준시각으로 사용한다.

    조회 완료 시각(fallback_ts)은 비교 기준일 뿐 원자료 시각을 대신하지 않는다.
    """
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    # 실전 t1602는 HHMMSScc(8자리), 일부 API는 HHMMSS/HHMM를 반환한다.
    # 8자리의 마지막 두 자리는 1/100초이므로 초 필드 검증 전 제거한다.
    if len(digits) not in {4, 6, 8}:
        return None
    if len(digits) == 4:
        digits += "00"
    elif len(digits) == 8:
        digits = digits[:6]
    try:
        # HHMMSS has no date. Infer the date from the associated receive/reference
        # timestamp so replayed inputs do not depend on the machine's wall clock.
        ref = fallback_ts if fallback_ts is not None else time.time()
        reference = dt.datetime.fromtimestamp(ref, KST)
        point = dt.datetime(reference.year, reference.month, reference.day,
                            int(digits[:2]), int(digits[2:4]), int(digits[4:6]),
                            tzinfo=KST)
        ts = point.timestamp()
        # 오래되거나 유효하지 않은 자료는 새 HTTP 조회 시각으로 위장하지 않는다.
        if abs(ts - ref) > 6 * 60 * 60:
            return None
        return ts
    except (ValueError, OverflowError):
        return None


def should_finalize_market_close(
    now: dt.datetime,
    actual_close: dt.datetime | None,
    test_seconds: int | None = None,
) -> bool:
    """오전·오후 작업 인계는 장마감이 아니다. 장 종료 시에만 사건을 최종 확정한다."""
    return test_seconds is None and actual_close is not None and now >= actual_close


def price_event_window_open(
    observed_ts: float,
    actual_close_ts: float | None,
    evaluation_ts: float | None = None,
) -> bool:
    """장마감 후 지연된 시세 조회를 신규 장중 급락으로 오인하지 않는다."""
    if actual_close_ts is None:
        return True
    effective_ts = observed_ts if evaluation_ts is None else max(observed_ts, evaluation_ts)
    return effective_ts < actual_close_ts


def continuous_flow_guard_active(now: dt.datetime, session: dict[str, Any]) -> bool:
    """동시호가 구간에는 현물·선물 수급 원자료가 일시 정지할 수 있다.
    원자료는 오래됐다고 표시하되 장마감 감시 프로세스까지 재기동하지 않는다.
    """
    open_dt = session.get("open")
    continuous_end = session.get("continuous_end")
    return bool(session.get("is_session") and open_dt and continuous_end
                and open_dt <= now < continuous_end)


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}시간 {m}분 {s}초"
    return f"{m}분 {s}초"


def link(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def telegram_send(text: str) -> int:
    return send_message(text)


def get_token() -> str:
    key = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    secret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not key or not secret:
        raise RuntimeError("LS secrets missing")
    last_error = ""
    for attempt in range(6):
        try:
            r = requests.post(
                BASE + "/oauth2/token",
                headers={"content-type": "application/x-www-form-urlencoded"},
                params={
                    "grant_type": "client_credentials",
                    "appkey": key,
                    "appsecretkey": secret,
                    "scope": "oob",
                },
                timeout=30,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            last_error = f"LS token transport error: {type(exc).__name__}: {exc}"
            if attempt < 5:
                time.sleep(min(12.0, 1.0 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc

        if 300 <= r.status_code < 400 or r.status_code in {429, 500, 502, 503, 504}:
            last_error = f"LS token transient HTTP {r.status_code}: {(r.text or '')[:200]}"
            if attempt < 5:
                time.sleep(min(12.0, 1.0 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error)
        if not r.ok:
            raise RuntimeError(f"LS token HTTP {r.status_code}: {(r.text or '')[:200]}")

        try:
            data = r.json()
        except Exception as exc:
            last_error = f"LS token invalid JSON: {(r.text or '')[:200]}"
            if attempt < 5:
                time.sleep(min(12.0, 1.0 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        token = str(data.get("access_token") or "").strip()
        if token:
            return token
        last_error = f"LS access token issue failed: {data.get('rsp_cd')} {data.get('rsp_msg')}"
        if attempt < 5:
            time.sleep(min(12.0, 1.0 * (2 ** attempt)))
            continue
        raise RuntimeError(last_error)
    raise RuntimeError(last_error or "LS access token issue failed")


def ls_post(token: str, path: str, tr: str, body: dict[str, Any], *,
            max_attempts: int = 5, request_timeout: float = 20.0,
            capture: dict[str, Any] | None = None) -> dict[str, Any]:
    last_error = ""
    for attempt in range(max_attempts):
        pace(tr)
        request_started = time.time()
        try:
            r = requests.post(
                BASE + path,
                headers={"content-type": "application/json; charset=utf-8",
                         "authorization": "Bearer " + token, "tr_cd": tr,
                         "tr_cont": "N", "tr_cont_key": ""},
                data=json.dumps(body), timeout=request_timeout)
        except requests.RequestException as exc:
            last_error = f"{tr} transport error: {type(exc).__name__}: {exc}"
            if attempt < max_attempts - 1:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        text = r.text or ""
        if capture is not None:
            # Preserve only this public market-data response and non-secret request.
            # Authorization headers and the bearer token are never retained.
            capture.update({"endpoint": path, "tr_cd": tr, "request": body,
                            "http_status": r.status_code, "query_started_ts": request_started,
                            "received_ts": time.time(),
                            "raw_base64": base64.b64encode(r.content).decode("ascii"),
                            "raw_sha256": hashlib.sha256(r.content).hexdigest()})
        # LS 게이트웨이가 임시 장애의 /503.html 경로를 HTTP 404로 반환하는
        # 실전 사례가 있다. 진짜 404와 구분해 해당 경로만 재시도한다.
        gateway_503_as_404 = r.status_code == 404 and "/503.html" in text
        retryable_http = r.status_code in {429, 500, 502, 503, 504} or gateway_503_as_404
        if not r.ok:
            last_error = f"{tr} HTTP {r.status_code}: {text[:250]}"
            if attempt < max_attempts - 1 and retryable_http:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error)
        try:
            d = r.json()
            if not isinstance(d, dict):
                raise ValueError("LS response is not a JSON object")
        except (ValueError, TypeError) as exc:
            last_error = f"{tr} invalid JSON: {type(exc).__name__}: {text[:200]}"
            if attempt < max_attempts - 1:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        code = str(d.get("rsp_cd") or "")
        if code and code not in {"00000", "0000"}:
            last_error = f"{tr} rejected {code}: {d.get('rsp_msg')}"
            if attempt < max_attempts - 1 and code in {"IGW00201"}:
                time.sleep(min(8.0, 1.0 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error)
        return d
    raise RuntimeError(last_error or f"{tr} request failed after retries")


def _latest_time_row(rows: Any) -> dict[str, Any] | None:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return None
    valid = []
    observed = time.time()
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_ts = market_clock_epoch(row.get("time"), observed)
        if source_ts is not None:
            valid.append((source_ts, row))
    return max(valid, key=lambda x: x[0])[1] if valid else None


def investor_current(token: str, market: str, upcode: str, exchgubun: str = "K", *,
                     max_attempts: int = 5, request_timeout: float = 20.0) -> dict[str, Any] | None:
    body = {"t1602InBlock": {"market": market, "upcode": upcode,
            "gubun1": "2", "gubun2": "0", "cts_time": "", "cts_idx": 0,
            "cnt": 100, "gubun3": "", "exchgubun": exchgubun}}
    if max_attempts == 5 and request_timeout == 20.0:
        d = ls_post(token, "/stock/investor", "t1602", body)
    else:
        d = ls_post(token, "/stock/investor", "t1602", body,
                    max_attempts=max_attempts, request_timeout=request_timeout)
    row = _latest_time_row(d.get("t1602OutBlock1"))
    if not row:
        return None
    fetched_ts = time.time()
    ex_upcode = str((d.get("t1602OutBlock") or {}).get("ex_upcode") or "").strip()
    if ex_upcode and not ex_upcode.endswith(upcode):
        raise ValueError("t1602 returned industry code conflicts with request")
    return {"time": row.get("time"), "sample_ts": market_clock_epoch(row.get("time"), fetched_ts),
            "market": {"001": "KOSPI", "301": "KOSDAQ"}.get(upcode),
            "source_tr": "t1602", "request_market": market, "upcode": upcode,
            "exchgubun": exchgubun, "returned_ex_upcode": ex_upcode,
            "timestamp_basis": "provider_time", "received_ts": fetched_ts,
            "source_row": row,
            "개인": fnum(row.get("sv_08")),
            "외국인": fnum(row.get("sv_17")), "기관": fnum(row.get("sv_18")),
            "투신": fnum(row.get("sv_03")),
            "금융투자": fnum(row.get("sv_01")),
            "actor_quality": {"투신": {"parent": "기관", "amount_field": "sv_03",
                "verified": fnum(row.get("sv_03")) is not None,
                "reason": None if fnum(row.get("sv_03")) is not None else "투신 원값sv_03 미제공"},
                "금융투자": {"parent": "기관", "provider_label": "증권", "amount_field": "sv_01",
                    "verified": fnum(row.get("sv_01")) is not None,
                    "reason": None if fnum(row.get("sv_01")) is not None else "증권 원값sv_01 미제공"}}}


def program_current(token: str, market: str = "KOSPI") -> dict[str, Any]:
    return market_program_current(token, market, ls_post)


def fetch_flow_snapshot(token: str, market_name: str = "KOSPI", on_channel=None) -> dict[str, Any]:
    started_ts = time.time()
    spec = MARKET_SPECS[market_name]
    snap: dict[str, Any] = {"ts": started_ts, "ts_start": started_ts, "errors": {},
                            "market": market_name, "flow_schema": "market-three-channel-v1"}
    queries = {"현물": lambda: investor_current(token, spec["spot_market"], spec["upcode"], "U",
                                                max_attempts=2, request_timeout=8.0),
               "지수선물": lambda: futures_current(token, market_name, ls_post),
               "프로그램": lambda: market_program_current(token, market_name, ls_post)}
    if market_name == "KOSPI":
        # Retain the existing, separately scaled five-minute surge series.
        # Crash attribution uses the explicit K2I product below, not this TR.
        queries["선물"] = lambda: investor_current(token, "4", "900", "K", max_attempts=2, request_timeout=8.0)
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        pending = {pool.submit(query): key for key, query in queries.items()}
        for result in as_completed(pending):
            key = pending[result]
            try:
                snap[key] = result.result()
            except Exception as exc:
                snap[key] = None
                snap["errors"][key] = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, FuturesInvestorQualityError):
                    snap.setdefault("rejected_source_evidence", {})[key] = exc.evidence
            if on_channel is not None:
                on_channel({**snap, "ts": time.time(), "errors": dict(snap["errors"])})
    snap = enrich_snapshot(snap, market_name)
    if on_channel is not None and ("cash_supplement" in snap or "program_supplement" in snap):
        on_channel({**snap, "ts": time.time(), "errors": dict(snap["errors"])})
    ended_ts = time.time()
    snap["ts_end"] = ended_ts
    snap["ts"] = (started_ts + ended_ts) / 2.0
    snap["sample_span_sec"] = ended_ts - started_ts
    return snap


def flow_snapshot_health(
    snap: dict[str, Any], now_ts: float | None = None,
    max_age_sec: float = MAX_FLOW_HEALTH_AGE_SEC,
) -> tuple[bool, dict[str, str]]:
    """HTTP 수신 성공과 수급 원자료의 시간·필드 유효성을 구분한다."""
    now_ts = time.time() if now_ts is None else now_ts
    issues: dict[str, str] = {}
    future_key = "지수선물" if "지수선물" in snap else "선물"
    for key in ("현물", future_key, "프로그램"):
        block = snap.get(key)
        if not isinstance(block, dict):
            issues[key] = "수급 채널 누락"
            continue
        source_ts = fnum(block.get("sample_ts"))
        if source_ts is None:
            issues[key] = "원자료 기준시각 누락"
            continue
        age = now_ts - source_ts
        if not (-5.0 <= age <= max_age_sec):
            issues[key] = f"원자료 시차 {age:.1f}초(허용 {max_age_sec:.0f}초)"
            continue
        fields = ("개인", "외국인", "기관") if key != "프로그램" else ("전체", "차익", "비차익")
        missing = [field for field in fields if fnum(block.get(field)) is None]
        if missing:
            issues[key] = "필수 수급값 누락: " + ",".join(missing)
    return not issues, issues


def fetch_kpi200() -> float | None:
    try:
        r = requests.get("https://m.stock.naver.com/api/index/KPI200/basic",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        return fnum(r.json().get("closePrice"))
    except Exception:
        return None


def get_weekly_puts(token: str, current: float | None, limit: int = 5) -> list[dict[str, Any]]:
    try:
        d = ls_post(token, "/futureoption/market-data", "t8435", {"t8435InBlock": {"gubun": "WK"}})
        rows = d.get("t8435OutBlock") or []
    except Exception:
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("hname") or "").strip()
        code = str(row.get("shcode") or "").strip()
        if not code or not re.match(r"^P(?:\s|$)", name, re.I):
            continue
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*$", name)
        strike = fnum(m.group(1)) if m else fnum(row.get("recprice"))
        if strike is None:
            continue
        out.append({"code": code, "name": name, "strike": strike})
    if current is not None:
        out.sort(key=lambda x: abs(float(x["strike"]) - current))
    return out[:limit]



def get_front_future(token: str) -> str:
    d = ls_post(token, "/futureoption/market-data", "t9943",
                {"t9943InBlock": {"gubun": "1"}})
    rows = d.get("t9943OutBlock") or []
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        code = str((row or {}).get("shcode") or "").strip()
        if code:
            return code
    raise RuntimeError("No KOSPI200 front future code from t9943")


def fetch_index_quote(token: str) -> dict[str, Any]:
    d = ls_post(token, "/indtp/market-data", "t1511",
                {"t1511InBlock": {"upcode": "001"}})
    row = d.get("t1511OutBlock") or {}
    price = fnum(row.get("pricejisu"))
    if price is None or price <= 0:
        raise RuntimeError(f"t1511 KOSPI price missing: {row}")
    return {
        "price": price,
        "prev_close": fnum(row.get("jniljisu")),
        "day_pct": fnum(row.get("diffjisu")),
        "open_pct": fnum(row.get("opendiff")),
        "open_time": str(row.get("opentime") or ""),
        "high": fnum(row.get("highjisu")),
        "low": fnum(row.get("lowjisu")),
        "open": fnum(row.get("openjisu")),
        "high_time": str(row.get("hightime") or ""),
        "low_time": str(row.get("lowtime") or ""),
        "raw": row,
    }


def fetch_kosdaq_index_quote(token: str) -> dict[str, Any]:
    """LS t1511 코스닥 종합지수 301. 가격·시가가 부재하면 이전 값으로 대체하지 않는다."""
    d = ls_post(token, "/indtp/market-data", "t1511",
                {"t1511InBlock": {"upcode": "301"}},
                max_attempts=2, request_timeout=8.0)
    row = d.get("t1511OutBlock") or {}
    price = fnum(row.get("pricejisu"))
    if price is None or price <= 0:
        raise RuntimeError(f"t1511 KOSDAQ 301 price missing: {row}")
    return {
        "price": price, "prev_close": fnum(row.get("jniljisu")),
        "open": fnum(row.get("openjisu")), "high": fnum(row.get("highjisu")),
        "low": fnum(row.get("lowjisu")), "open_time": str(row.get("opentime") or ""),
        "source": "LS t1511 upcode=301",
    }


def fetch_derivative_quote(token: str, code: str) -> dict[str, Any]:
    d = ls_post(token, "/futureoption/market-data", "t2111",
                {"t2111InBlock": {"focode": code}})
    row = d.get("t2111OutBlock") or {}
    price = fnum(row.get("price"))
    if price is None:
        raise RuntimeError(f"t2111 price missing for {code}: {row}")
    return {
        "price": price,
        "kpi200": fnum(row.get("kospijisu")),
        "basis": fnum(row.get("basis")),
        "market_basis": fnum(row.get("sbasis")),
        "time": str(row.get("chetime") or row.get("time") or ""),
        "raw": row,
    }


def backfill_index_bars(token: str, max_rows: int = 500, upcode: str = "001") -> list[tuple[float, float]]:
    # 재기동 시 당일 KOSPI 1분봉을 복구해 오전/직전 급락 시작점을 잃지 않는다.
    body = {"t8409InBlock": {
        "shcode": upcode, "ncnt": 1, "qrycnt": max_rows, "nday": "1",
        "sdate": " ", "stime": "", "edate": "99999999", "etime": "",
        "cts_date": " ", "cts_time": "", "comp_yn": "N"
    }}
    d = ls_post(token, "/indtp/chart", "t8409", body)
    rows = d.get("t8409OutBlock1") or []
    if isinstance(rows, dict):
        rows = [rows]
    out: list[tuple[float, float]] = []
    local_now = dt.datetime.now(KST)
    today = local_now.date()
    session = session_state(local_now)
    # 시초 첫 1분봉에 개장 전 전일 종가가 혼재할 수 있으므로 보수적으로 제외.
    first_reliable_bar = (
        session["open"] + dt.timedelta(minutes=1)
        if session.get("open") is not None else None
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        ds = "".join(ch for ch in str(row.get("date") or "") if ch.isdigit())
        ts = "".join(ch for ch in str(row.get("time") or "") if ch.isdigit())
        close = fnum(row.get("close"))
        if len(ds) != 8 or len(ts) < 4 or close is None or close <= 0:
            continue
        try:
            day = dt.datetime.strptime(ds, "%Y%m%d").date()
            if day != today:
                continue
            ts = (ts + "000000")[:6]
            when = dt.datetime(day.year, day.month, day.day,
                               int(ts[:2]), int(ts[2:4]), int(ts[4:6]), tzinfo=KST)
            if first_reliable_bar is not None and when < first_reliable_bar:
                continue
            out.append((when.timestamp(), close))
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    return out



def _actor_delta(start: dict[str, Any] | None, end: dict[str, Any] | None) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for actor in DISPLAY_ACTORS:
        a = subgroup_value(start, actor) if actor in {'투신', '금융투자'} else fnum((start or {}).get(actor))
        b = subgroup_value(end, actor) if actor in {'투신', '금융투자'} else fnum((end or {}).get(actor))
        out[actor] = (b - a) if a is not None and b is not None else None
    return out


def _program_delta(start: dict[str, Any] | None, end: dict[str, Any] | None) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for k in ("차익", "비차익", "베이시스"):
        a = fnum((start or {}).get(k)); b = fnum((end or {}).get(k))
        out[k] = (b - a) if a is not None and b is not None else None
    a_total = fnum((start or {}).get("전체")); b_total = fnum((end or {}).get("전체"))
    direct_total = (b_total - a_total) if a_total is not None and b_total is not None else None
    calc_total = None
    if out.get("차익") is not None and out.get("비차익") is not None:
        calc_total = float(out["차익"]) + float(out["비차익"])
    out["전체"] = calc_total
    out["전체직접"] = direct_total
    out["검산차이"] = (direct_total - calc_total) if direct_total is not None and calc_total is not None else None
    return out


def fmt_eok(v: float | None) -> str:
    if v is None:
        return "확인 불가"
    return f"{v:+,.0f}억원"


def fmt_raw(v: float | None) -> str:
    if v is None:
        return "확인 불가"
    return f"{v:+,.0f}"


def program_quality_label(att: dict[str, Any]) -> str:
    numeric = _program_numeric_quality_label(att)
    if att.get("program_source_time_verified") is False:
        return numeric + " · 원천 공표시각 미제공·조회시각 기준 — 확신도 상향 보류"
    return numeric


def _program_numeric_quality_label(att: dict[str, Any]) -> str:
    """직접값과 차익+비차익의 엄밀한 수치 차이를 '일치'로 오표기하지 않는다."""
    ratio = fnum(att.get("program_crosscheck_ratio_pct"))
    span = fnum(att.get("program_sample_span_sec"))
    if ratio is None or span is None:
        return "검산·조회시차 자료 부족 — 확신도 상향 보류"
    if span > MAX_PROGRAM_SNAPSHOT_SKEW_SEC:
        return f"3종 조회시차 {span:.1f}초 초과 — 확신도 상향 보류"
    if att.get("program_direction_consistent") is False:
        return f"매매 방향 불일치(합계 차이 {ratio:.2f}%) — 재확인 필요"
    if ratio > MAX_PROGRAM_CROSSCHECK_RATIO_PCT:
        return f"방향 일치·합계 차이 {ratio:.2f}%(높은 확신도 보류)"
    if ratio < 0.005:
        return "수치 일치(합계 차이 0.01% 미만)"
    return f"1% 이내 근사 일치(합계 차이 {ratio:.2f}%)"


def market_attribution_footer(market: str, final: bool = False) -> str:
    end = "저점" if final else "현재"
    return (f"• 판정: 사건 시작 직전→{end} 수급 변화. 현물·프로그램은 KRX+NXT 통합, "
            f"{MARKET_SPECS[market]['futures_label']}은 해당 파생상품만 관측합니다. "
            "채널 간 금액을 합산하거나 프로그램 수급을 특정 투자자에게 귀속하지 않습니다.")


def market_attribution_lines(att: dict[str, Any], market: str, final: bool = False) -> list[str]:
    """Identical channel order and quality disclosure for both markets."""
    ko = "코스피" if market == "KOSPI" else "코스닥"
    statuses = att.get("channel_status") or {}
    future_fmt = fmt_raw if att.get("futures_unit") == "LS_raw_amount" else fmt_eok
    program_fmt = fmt_eok if att.get("program_unit") == "억원" else fmt_raw
    program_note = "키움·독립 원화 원표 대조" if att.get("program_unit") == "억원" else "LS 원값"
    lines = []
    for name, label, formatter in (("spot", f"{ko} 현물(통합)", fmt_eok),
                                   ("futures", MARKET_SPECS[market]["futures_label"], future_fmt)):
        values = att.get(name)
        if values is not None:
            shown = " · ".join(f"{actor_label(actor)} <b>{formatter(values.get(actor))}</b>"
                               for actor in DISPLAY_ACTORS)
            suffix = " <i>(LS 순매수금액 원값·환산 단위 미확인)</i>" if formatter is fmt_raw else ""
            lines.append(f"• {label}: {shown}{suffix}")
            sellers = [(a, values.get(a)) for a in PRIMARY_ACTORS
                       if values.get(a) is not None and values[a] < 0]
            leader, value = min(sellers, key=lambda item: item[1]) if sellers else ("없음", None)
            if name == "futures" and market == "KOSDAQ" and not sellers:
                leader = "외국인·기관·개인 중 없음"
            lines.append(f"• {'현물' if name == 'spot' else '선물'} 최다매도: <b>{leader}</b>"
                         + (" " + formatter(value) if value is not None else ""))
        else:
            reason = str((statuses.get(name) or {}).get("reason") or "기준점 없음")
            lines.append(f"• {label}: 확인 보류 — {html.escape(reason)}")
    if att.get("available"):
        cross = ", ".join(att.get("cross_sellers") or []) or "없음"
        lines.append(f"• 현물·선물 동시매도: <b>{html.escape(cross)}</b>")
    else:
        lines.append("• 현물·선물 동시매도: 판정 보류")
    lines.extend(subgroup_direction_lines(att.get("spot"), att.get("futures") or {}))
    lines.append("• " + LEADER_NOTE)
    p = att.get("program") or {}
    pgm_ok = (statuses.get("program") or {}).get("available", att.get("available"))
    if pgm_ok and p.get("전체") is not None:
        ratio = fnum(att.get("program_crosscheck_ratio_pct"))
        check_suffix = f" ({ratio:.2f}%)" if ratio is not None else " (비율 검증 보류)"
        lines += [f"• {ko} 프로그램 전체(차익+비차익) <b>{program_fmt(p.get('전체'))}</b> · "
                  f"차익 <b>{program_fmt(p.get('차익'))}</b> · 비차익 <b>{program_fmt(p.get('비차익'))}</b> <i>({program_note})</i>",
                  f"• {'키움' if att.get('program_unit') == '억원' else 'LS'} 전체 직접값 변화 <b>{program_fmt(p.get('전체직접'))}</b> · "
                  f"계산합계와 차이 <b>{program_fmt(p.get('검산차이'))}</b>{check_suffix}"]
    else:
        reason = str((statuses.get("program") or {}).get("reason") or "기준점 없음")
        lines.append(f"• {ko} 프로그램 전체·차익·비차익: 확인 보류 — {html.escape(reason)}")
    for name, label in (("spot", "현물"), ("futures", "선물"), ("program", "프로그램 조회")):
        status = statuses.get(name) or {}
        if status.get("start_gap") is not None and status.get("end_gap") is not None:
            lines.append(f"• {label} 기준점 시차: 시작 {status['start_gap']:.1f}초 / "
                         f"{'저점' if final else '종료'} {status['end_gap']:.1f}초 (허용 30초)")
    span = fnum(att.get("program_sample_span_sec"))
    if span is not None:
        lines.append(f"• 프로그램 3종 조회시차 최대 {span:.1f}초 (허용 8초)")
    lines.append("• 프로그램 교차검증 품질: <b>" + html.escape(program_quality_label(att)) + "</b>")
    if att.get("available"):
        lines += ["", "<b>판정</b>",
                  f"• <b>{html.escape(str(att.get('verdict')))}</b> · 확신도 {html.escape(str(att.get('confidence')))}"]
    else:
        lines.append("• 주체 판정 보류 — " + html.escape(str(att.get("reason") or "수급 기준점 부족")))
    lines.append("• 동일 검증 기준: 수급 시차 30초·프로그램 3종 조회시차 8초·합계 차이 1%. "
                 "원천 공표시각이 없는 프로그램은 조회시각을 표시하며 확신도 상향을 보류합니다.")
    lines += cash_lines(att.get("cash_supplement"), market, att.get("end_ts"))
    return lines


def _flow_surge_channel_pair(
    rows: list[dict[str, Any]], channel: str, now_ts: float,
    session_open_ts: float | None = None,
) -> dict[str, Any] | None:
    """원자료 시각 기준으로 5분 누적값의 시작/종료를 30초 이내 정렬한다."""
    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        block = row.get(channel)
        if not isinstance(block, dict):
            continue
        source_ts = fnum(block.get("sample_ts"))
        if (source_ts is None or source_ts > now_ts
                or (session_open_ts is not None and source_ts < session_open_ts)):
            continue
        if all(fnum(block.get(who)) is not None for who in ("외국인", "기관", "개인")):
            candidates.append((source_ts, block))
    if not candidates:
        return None
    end_ts, end = max(candidates, key=lambda x: x[0])
    if session_open_ts is not None and end_ts < session_open_ts + SURGE_WINDOW_SEC:
        return None
    if not (0 <= now_ts - end_ts <= SURGE_MAX_END_AGE_SEC):
        return None
    target = end_ts - SURGE_WINDOW_SEC
    before = [(ts, b) for ts, b in candidates if ts <= target]
    if not before:
        return None
    start_ts, start = max(before, key=lambda x: x[0])
    skew = target - start_ts
    if skew > SURGE_MAX_SAMPLE_SKEW_SEC:
        return None
    if (start.get("source_tr"), start.get("unit")) != (end.get("source_tr"), end.get("unit")):
        return None
    return {
        "start_ts": start_ts, "end_ts": end_ts,
        "start": start, "end": end, "start_skew_sec": skew,
        "end_age_sec": now_ts - end_ts,
        "deltas": _actor_delta(start, end),
    }


def _flow_surge_program(
    rows: list[dict[str, Any]], now_ts: float,
    session_open_ts: float | None = None,
) -> dict[str, Any] | None:
    """프로그램 원값은 독립적으로 검산한다. 억원·투자자별 수급과 합산 금지."""
    candidates = []
    for row in rows:
        block = row.get("프로그램")
        if not isinstance(block, dict):
            continue
        ts = fnum(block.get("sample_ts"))
        if (ts is None or ts > now_ts
                or (session_open_ts is not None and ts < session_open_ts)):
            continue
        if all(fnum(block.get(k)) is not None for k in ("전체", "차익", "비차익")):
            candidates.append((ts, block))
    if not candidates:
        return None
    end_ts, end = max(candidates, key=lambda x: x[0])
    if session_open_ts is not None and end_ts < session_open_ts + SURGE_WINDOW_SEC:
        return None
    if not (0 <= now_ts - end_ts <= SURGE_MAX_END_AGE_SEC):
        return None
    target = end_ts - SURGE_WINDOW_SEC
    prev = [(ts, b) for ts, b in candidates if ts <= target]
    if not prev:
        return None
    start_ts, start = max(prev, key=lambda x: x[0])
    if target - start_ts > SURGE_MAX_SAMPLE_SKEW_SEC:
        return None
    if (start.get("source_tr"), start.get("unit")) != (end.get("source_tr"), end.get("unit")):
        return None
    values = _program_delta(start, end)
    calc, direct, gap = (
        fnum(values.get("전체")),
        fnum(values.get("전체직접")),
        fnum(values.get("검산차이")),
    )
    if calc is None or direct is None or gap is None:
        return None
    ratio = abs(gap) / max(abs(calc), abs(direct), 1.0) * 100
    span_values = [
        fnum(start.get("표본시차초")),
        fnum(end.get("표본시차초")),
    ]
    span = max(v if v is not None else float("inf") for v in span_values)
    aligned = (
        span <= MAX_PROGRAM_SNAPSHOT_SKEW_SEC
        and ratio <= MAX_PROGRAM_CROSSCHECK_RATIO_PCT
        and ((calc == 0 and direct == 0) or (calc != 0 and direct != 0 and (calc < 0) == (direct < 0)))
    )
    return {
        "delta": calc,
        "direct": direct,
        "gap": gap,
        "ratio_pct": ratio,
        "sample_span_sec": span,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "valid": aligned,
        "unit": end.get("unit"),
        "source_tr": end.get("source_tr"),
    }


def flow_surge_candidates(
    rows: list[dict[str, Any]], now_ts: float,
    session_open_ts: float | None = None,
) -> list[dict[str, Any]]:
    """급락과 관계없이 최근 5분의 '순매수 누적 변화'를 판정한다.

    잔고와 신규 순매수 혼동, 시차가 큰 표본의 소급 재구성, 단위 혼합을 막는다.
    """
    # 08:59 등 장전 순매수와 정규장 5분 순매수를 합치지 않는다.
    if session_open_ts is not None and now_ts < session_open_ts + SURGE_WINDOW_SEC:
        return []
    spot = _flow_surge_channel_pair(rows, "현물", now_ts, session_open_ts)
    fut = _flow_surge_channel_pair(rows, "선물", now_ts, session_open_ts)
    if not spot and not fut:
        return []
    program = _flow_surge_program(rows, now_ts, session_open_ts)
    result = []
    for actor in ALERT_ACTORS:
        ds = fnum((spot or {}).get("deltas", {}).get(actor))
        df = fnum((fut or {}).get("deltas", {}).get(actor))
        # 현물과 선물 표본 종료시점이 서로 멀면 하나의 동시 유입으로 합치지 않는다.
        # 각 채널은 독립적으로는 신선해도 서로 최대 90초 어긋날 수 있다.
        both = (
            ds is not None and df is not None
            and ds >= SURGE_COMBINED_SPOT_EOK
            and df >= SURGE_COMBINED_FUT_EOK
            and abs(float(spot["end_ts"]) - float(fut["end_ts"])) <= SURGE_MAX_SAMPLE_SKEW_SEC
        )
        spot_only = ds is not None and ds >= SURGE_SINGLE_SPOT_EOK
        fut_only = df is not None and df >= SURGE_SINGLE_FUT_EOK
        if not (both or spot_only or fut_only):
            continue
        if both:
            mode = "현물·선물 동시"
            key_ts = min(float(spot["end_ts"]), float(fut["end_ts"]))
        elif spot_only and (not fut_only or ds / SURGE_SINGLE_SPOT_EOK >= df / SURGE_SINGLE_FUT_EOK):
            mode = "현물 중심"
            key_ts = float(spot["end_ts"])
        else:
            mode = "선물 중심"
            key_ts = float(fut["end_ts"])
        # 프로그램 자체의 차익·비차익 검산이 일치해도 사건 기준시점과
        # 30초 이상 어긋난 프로그램 데이터를 동시 매수 근거로 사용하지 않는다.
        program_aligned = bool(
            program and program["valid"] and program["delta"] > 0
            and abs(float(program["end_ts"]) - key_ts) <= SURGE_MAX_SAMPLE_SKEW_SEC
        )
        result.append({
            "actor": actor, "mode": mode,
            "spot": ds, "futures": df, "sample_ts": key_ts,
            "spot_window": (float(spot["start_ts"]), float(spot["end_ts"])) if spot else None,
            "futures_window": (float(fut["start_ts"]), float(fut["end_ts"])) if fut else None,
            "spot_start_skew_sec": (spot or {}).get("start_skew_sec"),
            "futures_start_skew_sec": (fut or {}).get("start_skew_sec"),
            "spot_end_cumulative": fnum((spot or {}).get("end", {}).get(actor)),
            "spot_start_cumulative": fnum((spot or {}).get("start", {}).get(actor)),
            "futures_end_cumulative": fnum((fut or {}).get("end", {}).get(actor)),
            "program": program,
            "cash_supplement": (spot or {}).get("end", {}).get("cash_supplement"),
            # 프로그램 매수는 투자자별 매수주체 확증이 아니라 별도의 시장 보조정보.
            "confidence": ("높음" if both and program_aligned else "중간" if both else "단독 신호"),
        })
    return result


def confirm_flow_surge(pending: dict[str, Any], actor: str, sample_ts: float,
                       now_ts: float, end_values: dict[str, float | None]) -> bool:
    """Both markets require new source time AND increased cumulative buying.

    The triggering channel set must stay the same. A reversal or a legacy
    handoff without cumulative endpoints starts a fresh confirmation; receipt
    time alone can never turn an unchanged upstream value into a second one.
    """
    if not end_values or any(fnum(v) is None for v in end_values.values()):
        pending.pop(actor, None)
        return False
    values = {key: float(value) for key, value in end_values.items()}
    previous = pending.get(actor) or {}
    old_values = previous.get("end_values") or {}
    # The existing KOSDAQ handoff stored a single spot endpoint.
    if not old_values and set(values) == {"spot"} and fnum(previous.get("end_value")) is not None:
        old_values = {"spot": float(previous["end_value"])}
    previous_ts, seen_at = fnum(previous.get("sample_ts")), fnum(previous.get("seen_at"))
    reset = (previous_ts is None or seen_at is None or sample_ts < previous_ts
             or not 0 <= now_ts - seen_at <= 120
             or set(old_values) != set(values)
             or any(fnum(old_values.get(key)) is None or value < float(old_values[key])
                    for key, value in values.items()))
    if reset:
        pending[actor] = {"sample_ts": sample_ts, "seen_at": now_ts, "end_values": values}
        if set(values) == {"spot"}:
            pending[actor]["end_value"] = values["spot"]
        return False
    return (sample_ts - previous_ts >= SURGE_CONFIRM_SEC
            and any(value > float(old_values[key]) for key, value in values.items()))


class Watch:
    def __init__(self, token: str, puts: list[dict[str, Any]], front_future: str, test: bool):
        self.token = token; self.put_defs = puts; self.test = test
        self.idx: deque[tuple[float, float]] = deque(maxlen=30000)
        self.fut: deque[tuple[float, float]] = deque(maxlen=30000)
        self.puts: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=30000))
        self.flows: deque[dict[str, Any]] = deque(maxlen=10000)
        self.front_future = front_future; self.episode: dict[str, Any] | None = None
        # 종료된 사건의 과거 고점으로 새로운 시작 경보를 재발송하지 않는다.
        self.last_episode_end_ts: float | None = None
        self.last_flow_poll = 0.0; self.flow_task: asyncio.Task | None = None
        self.msg_ids: list[int] = []; self.enrichment_msg_ids: list[int] = []; self.raw: dict[str, Any] = {}
        self.enrichment_tasks: set[asyncio.Task] = set()
        self.enrichment_sem = asyncio.Semaphore(1)
        self.monitor_started_ts = time.time()
        self.last_idx_tick_ts: float | None = None
        self.last_fut_tick_ts: float | None = None
        self.last_flow_success_ts: float | None = None
        self.last_option_poll = 0.0
        self.session_open_ts: float | None = None
        self.session_close_ts: float | None = None
        self.session_continuous_end_ts: float | None = None
        # 장전 전일 종가 유지값은 정규장 최초 가격으로 확정하지 않는다.
        self.regular_price_ready = False
        self.opening_gap_sent = False
        self.handoff_path: str | None = None
        self.last_handoff_save_ts = 0.0
        self.surge_last_processed_ts = 0.0
        self.surge_pending: dict[str, dict[str, Any]] = {}
        self.surge_sent_at: dict[str, float] = {}
        # 같은 프로세스에서 별도로 조회하되 코스피 급락·수급 작업을 막지 않는다.
        self.kosdaq_flows: deque[dict[str, Any]] = deque(maxlen=10000)
        self.kosdaq_flow_task: asyncio.Task | None = None
        self.kosdaq_last_poll = 0.0
        self.kosdaq_last_success_ts: float | None = None
        self.kosdaq_surge_last_processed_ts = 0.0
        self.kosdaq_surge_pending: dict[str, dict[str, Any]] = {}
        self.kosdaq_surge_sent_at: dict[str, float] = {}
        self.kosdaq_prealert_last_processed_ts = 0.0
        self.kosdaq_prealert_pending: dict[str, dict[str, Any]] = {}
        self.kosdaq_prealert_sent_at: dict[str, float] = {}
        # 코스닥 급락 가격 사건은 별도 지수·최저점·중복키·시가갭을 보관한다.
        self.kosdaq_idx: deque[tuple[float, float]] = deque(maxlen=30000)
        self.kosdaq_episode: dict[str, Any] | None = None
        self.kosdaq_last_episode_end_ts: float | None = None
        self.kosdaq_regular_price_ready = False
        self.kosdaq_opening_gap_sent = False
        self.kosdaq_last_price_poll = 0.0
        self.kosdaq_last_idx_tick_ts: float | None = None
        self.kosdaq_last_price_processed_ts = 0.0
        self.kosdaq_price_task: asyncio.Task | None = None
        self.kosdaq_backfill_task: asyncio.Task | None = None
        self.kosdaq_last_price_snapshot: dict[str, Any] = {}
        self.daily_close: dict[str, Any] = {}


    @staticmethod
    def _nearest(buf: deque[tuple[float, float]], ts: float) -> tuple[float, float] | None:
        return min(buf, key=lambda x: abs(x[0] - ts)) if buf else None

    def _ret(self, minutes: int) -> float | None:
        if not self.idx:
            return None
        cur_t, cur = self.idx[-1]
        p = self._nearest(self.idx, cur_t - minutes * 60)
        if not p or cur_t - p[0] < minutes * 60 * 0.65:
            return None
        return pct(p[1], cur)

    def _recent_peak(self, seconds: int = PRICE_LOOKBACK_SEC) -> tuple[float, float] | None:
        if not self.idx:
            return None
        cutoff = self.idx[-1][0] - seconds
        rows = [x for x in self.idx if x[0] >= cutoff]
        if not rows:
            return None
        high = max(v for _, v in rows)
        candidates = [x for x in rows if x[1] == high]
        return candidates[-1]

    def _window_peak(self, minutes: int, pad_minutes: int) -> tuple[float, float] | None:
        if not self.idx:
            return None
        now_t = self.idx[-1][0]
        cutoff = now_t - (minutes + pad_minutes) * 60
        last_end = fnum(getattr(self, "last_episode_end_ts", None))
        # 이미 끝난 사건의 시작 고점이 새로운 사건의 시작점으로 재사용되면
        # 다른 시각의 가격변동을 한 사건으로 잘못 묶게 된다.
        rows = [x for x in self.idx
                if x[0] >= cutoff and (last_end is None or x[0] > last_end)]
        if not rows:
            return None
        high = max(v for _, v in rows)
        # 같은 고점이 여러 번이면 급락 직전의 마지막 고점을 사용한다.
        return [x for x in rows if x[1] == high][-1]

    def _trigger(self) -> tuple[bool, dict[str, Any]]:
        if len(self.idx) < 2:
            return False, {}
        now_t, cur = self.idx[-1]
        returns = {m: self._ret(m) for m in (5, 10, 15, 30, 60)}
        # 가장 짧은 시간창부터 검사한다. 따라서 오전 세션고점이 아니라
        # 실제 급락 직전 국소고점이 사건 시작점으로 우선 선택된다.
        rules = [
            (5, -0.35, 2),
            (10, -0.55, 3),
            (15, -0.70, 5),
            (20, -0.90, 5),
            (30, -1.00, 7),
            (45, -1.10, 10),
            (60, -1.20, 10),
            (90, -1.30, 15),
            (120, -1.40, 20),
            (180, -1.50, 20),
        ]
        for window, threshold, pad in rules:
            peak = self._window_peak(window, pad)
            if not peak:
                continue
            duration = now_t - peak[0]
            if duration <= 0:
                continue
            drop = pct(peak[1], cur)
            if drop is None or drop > threshold:
                continue

            # 30분 이상 구간은 최근에도 하락 압력이 살아 있어야 사건으로 인정한다.
            active = True
            if window > 20 and window <= 60:
                active = any(
                    returns.get(m) is not None and returns[m] <= lim
                    for m, lim in ((10, -0.20), (15, -0.30), (30, -0.45))
                )
            elif window > 60:
                # 몇 시간짜리 완만한 하락은 급락 사건으로 보지 않는다.
                # 장시간 누적 낙폭에 더해 최근 15~60분 하락 가속이 확인돼야 한다.
                active = any(
                    returns.get(m) is not None and returns[m] <= lim
                    for m, lim in ((15, -0.55), (30, -0.70), (60, -0.90))
                )
            if not active:
                continue

            return True, {
                "peak_ts": peak[0], "peak": peak[1],
                "cur_ts": now_t, "cur": cur,
                "drop": drop, "duration": duration,
                "threshold": threshold, "window_minutes": window,
                "r5": returns.get(5), "r10": returns.get(10),
                "r15": returns.get(15), "r30": returns.get(30),
                "r60": returns.get(60),
            }
        return False, {}

    def _kosdaq_trigger(self) -> tuple[bool, dict[str, Any]]:
        """코스피와 동일한 국소 급락 문턱값, 코스닥 가격·종료 시각만 사용."""
        if len(self.kosdaq_idx) < 2:
            return False, {}
        now_t, cur = self.kosdaq_idx[-1]
        rows = list(self.kosdaq_idx)
        last_end = self.kosdaq_last_episode_end_ts
        returns: dict[int, float | None] = {}
        for minutes in (5, 10, 15, 30, 60):
            target = now_t - minutes * 60
            p = min(rows, key=lambda x: abs(x[0]-target))
            returns[minutes] = (
                pct(p[1], cur) if now_t-p[0] >= minutes*60*0.65 else None
            )
        rules = [
            (5, -0.35, 2), (10, -0.55, 3), (15, -0.70, 5),
            (20, -0.90, 5), (30, -1.00, 7), (45, -1.10, 10),
            (60, -1.20, 10), (90, -1.30, 15), (120, -1.40, 20),
            (180, -1.50, 20),
        ]
        for window, threshold, pad in rules:
            eligible = [x for x in rows
                        if x[0] >= now_t-(window+pad)*60
                        and (last_end is None or x[0] > last_end)]
            if not eligible:
                continue
            high = max(v for _,v in eligible)
            peak = [x for x in eligible if x[1]==high][-1]
            duration = now_t-peak[0]
            drop = pct(peak[1], cur)
            if duration <= 0 or drop is None or drop > threshold:
                continue
            if window > 20 and window <= 60:
                active = any(returns.get(m) is not None and returns[m] <= lim
                             for m,lim in ((10,-0.20),(15,-0.30),(30,-0.45)))
            elif window > 60:
                active = any(returns.get(m) is not None and returns[m] <= lim
                             for m,lim in ((15,-0.55),(30,-0.70),(60,-0.90)))
            else:
                active = True
            if not active:
                continue
            return True, {
                "peak_ts": peak[0], "peak": peak[1], "cur_ts": now_t,
                "cur": cur, "drop": drop, "duration": duration,
                "threshold": threshold, "window_minutes": window,
            }
        return False, {}

    def _kosdaq_attribution(self, start_ts: float, end_ts: float) -> dict[str, Any]:
        return self._market_attribution(start_ts, end_ts, "KOSDAQ")

    def _flow_near(self, ts: float, prefer_before: bool = True) -> dict[str, Any] | None:
        rows = list(self.flows)
        if not rows:
            return None
        if prefer_before:
            prior = [x for x in rows if float(x.get("ts", 0)) <= ts]
            # 사건 시작 이전 스냅샷이 없으면 이후 값을 시작값으로 대체하지 않는다.
            return max(prior, key=lambda x: float(x.get("ts", 0))) if prior else None
        return min(rows, key=lambda x: abs(float(x.get("ts", 0)) - ts))

    def _flow_channel_near(self, ts: float, channel: str, *,
                           rows=None, market: str = "KOSPI") -> tuple[dict[str, Any], float] | None:
        candidates: list[tuple[dict[str, Any], float]] = []
        for snap in (self.flows if rows is None else rows):
            block = snap.get(channel)
            if not isinstance(block, dict) or not block_scope_matches(block, market, channel):
                continue
            sample_ts = fnum(block.get("sample_ts"))
            if sample_ts is None and market == "KOSPI" and not block.get("source_tr"):
                sample_ts = fnum(snap.get("ts"))
            if sample_ts is None or sample_ts > ts:
                continue
            # 시가 갭과 당일 수급은 개장 전 스냅샷을 사건 시작점으로 섞지 않는다.
            # 시차가 30초 이내라도 정규장 09:00 이전 표본이면 사용할 수 없다.
            regular_open_ts = fnum(getattr(self, "session_open_ts", None))
            if regular_open_ts is not None and sample_ts < regular_open_ts:
                continue
            fields = ("외국인", "기관", "개인") if channel != "프로그램" else ("전체", "차익", "비차익")
            if any(fnum(block.get(field)) is None for field in fields):
                continue
            candidates.append((block, sample_ts))
        return max(candidates, key=lambda x: x[1]) if candidates else None

    def attribution(self, start_ts: float, end_ts: float) -> dict[str, Any]:
        return self._market_attribution(start_ts, end_ts, "KOSPI")

    def _market_attribution(self, start_ts: float, end_ts: float, market: str) -> dict[str, Any]:
        rows = list(self.flows if market == "KOSPI" else self.kosdaq_flows)
        supplements = [x.get("cash_supplement") for x in rows if isinstance(x.get("cash_supplement"), dict)
                       and float(x["cash_supplement"].get("received_ts") or 0) <= end_ts]
        cash_supplement = max(supplements, key=lambda x: float(x.get("received_ts") or 0)) if supplements else None
        # Legacy KOSPI handoffs keep their old series; after a new collection,
        # both markets require the exact-product channel. Never mix its scale
        # with the t1602 five-minute surge series.
        future_key = "지수선물" if market == "KOSDAQ" or any(x.get("flow_schema") or "지수선물" in x for x in rows) else "선물"
        pairs, statuses = {}, {}
        for name, key in (("spot", "현물"), ("futures", future_key), ("program", "프로그램")):
            first = self._flow_channel_near(start_ts, key, rows=rows, market=market)
            last = self._flow_channel_near(end_ts, key, rows=rows, market=market)
            status = {"available": False, "reason": "사건 시작 또는 종료 이전 기준점 없음"}
            if first and last:
                gaps = (start_ts-first[1], end_ts-last[1])
                status.update(start_gap=gaps[0], end_gap=gaps[1],
                              start_ts=first[1], end_ts=last[1])
                legacy_tr = "t1602" if name == "spot" else None
                same_series = ((first[0].get("source_tr", legacy_tr), first[0].get("unit")) ==
                               (last[0].get("source_tr", legacy_tr), last[0].get("unit")))
                if max(gaps) > MAX_FLOW_ALIGNMENT_SEC:
                    status["reason"] = f"기준점 시간 정렬 초과: 시작 {gaps[0]:.1f}초 / 종료 {gaps[1]:.1f}초(허용 30초)"
                elif not same_series:
                    status["reason"] = "원천·단위가 다른 시작/종료 표본"
                elif first[1] == last[1]:
                    status["reason"] = "시작/종료 원자료 표본 동일 — 구간 변화 확인 불가"
                else:
                    status.update(available=True, reason=None)
            if name == "futures" and market == "KOSDAQ" and not status["available"]:
                for snap in reversed(rows):
                    rejected = (snap.get("rejected_source_evidence") or {}).get(future_key)
                    if isinstance(rejected, dict) and start_ts <= float(rejected.get("sample_ts") or 0) <= end_ts:
                        status["reason"] = "LS 선물 원자료 투자자 검산 미통과 — " + "; ".join(
                            (rejected.get("investor_quality") or {}).get("issues") or ["미확인 행"])
                        break
            statuses[name] = status
            pairs[name] = (first, last) if status["available"] else (None, None)
        spot_a, spot_b = pairs["spot"]
        fut_a, fut_b = pairs["futures"]
        pgm_a, pgm_b = pairs["program"]
        observed = {name: _actor_delta(*[p[0] for p in pairs[name]]) if statuses[name]["available"] else None
                    for name in ("spot", "futures")}
        meta = {"market": market, "channel_status": statuses,
                "spot": observed["spot"], "futures": observed["futures"],
                "futures_label": MARKET_SPECS[market]["futures_label"],
                "futures_unit": (fut_b[0].get("unit") if fut_b else None),
                "program_unit": (pgm_b[0].get("unit") if pgm_b else None),
                "cash_supplement": cash_supplement,
                "start_ts": start_ts, "end_ts": end_ts}
        if market in ("KOSPI", "KOSDAQ"):
            # Delivery evidence must survive the one-hour handoff lookback.
            # These are decoded provider fields, not preserved HTTP bytes.
            meta["source_evidence"] = {
                name: {"start": pair[0][0] if pair[0] else None,
                       "end": pair[1][0] if pair[1] else None}
                for name, pair in pairs.items()
            }
            for snap in reversed(rows):
                rejected = (snap.get("rejected_source_evidence") or {}).get(future_key)
                if isinstance(rejected, dict) and start_ts <= float(rejected.get("sample_ts") or 0) <= end_ts:
                    meta["source_evidence"]["rejected_futures"] = rejected
                    break
        if not spot_a or not spot_b or not fut_a or not fut_b:
            failed = [("현물" if n == "spot" else "선물") + ": " + str(statuses[n]["reason"])
                      for n in ("spot", "futures") if not statuses[n]["available"]]
            return {**meta, "available": False, "reason": " · ".join(failed),
                    "program": _program_delta(pgm_a[0], pgm_b[0]) if pgm_a and pgm_b else {},
                    "program_quality": False, "confidence": "보류"}

        spot_start_gap = max(0.0, start_ts - spot_a[1])
        spot_end_gap = max(0.0, end_ts - spot_b[1])
        fut_start_gap = max(0.0, start_ts - fut_a[1])
        fut_end_gap = max(0.0, end_ts - fut_b[1])
        start_gap = max(spot_start_gap, fut_start_gap)
        end_gap = max(spot_end_gap, fut_end_gap)
        if start_gap > MAX_FLOW_ALIGNMENT_SEC or end_gap > MAX_FLOW_ALIGNMENT_SEC:
            return {
                "available": False,
                "reason": f"현물·선물 기준점 시간 정렬 초과(시작 최대 {start_gap:.1f}초, 종료 최대 {end_gap:.1f}초; 허용 {MAX_FLOW_ALIGNMENT_SEC}초)",
                "start_alignment_sec": start_gap,
                "end_alignment_sec": end_gap,
            }

        spot = _actor_delta(spot_a[0], spot_b[0])
        fut = _actor_delta(fut_a[0], fut_b[0])
        pgm_start_gap = max(0.0, start_ts - pgm_a[1]) if pgm_a else None
        pgm_end_gap = max(0.0, end_ts - pgm_b[1]) if pgm_b else None
        pgm_aligned = bool(
            pgm_a and pgm_b
            and pgm_start_gap is not None and pgm_end_gap is not None
            and pgm_start_gap <= MAX_FLOW_ALIGNMENT_SEC
            and pgm_end_gap <= MAX_FLOW_ALIGNMENT_SEC
        )
        pgm = _program_delta(pgm_a[0], pgm_b[0]) if pgm_aligned else {"전체": None, "차익": None, "비차익": None, "베이시스": None}
        def dominant_seller(block: dict[str, float | None]) -> tuple[str | None, float | None]:
            sellers = [(actor, block.get(actor)) for actor in PRIMARY_ACTORS
                       if block.get(actor) is not None and float(block[actor]) < 0]
            return min(sellers, key=lambda x: float(x[1])) if sellers else (None, None)

        spot_leader, spot_leader_val = dominant_seller(spot)
        fut_leader, fut_leader_val = dominant_seller(fut)
        cross_sellers = [actor for actor in ("외국인", "기관", "개인")
                         if spot.get(actor) is not None and fut.get(actor) is not None
                         and float(spot[actor]) < 0 and float(fut[actor]) < 0]
        pgm_neg = pgm.get("전체") is not None and float(pgm["전체"]) < 0
        pgm_spans = [
            fnum(block.get("표본시차초"))
            for block in ((pgm_a[0] if pgm_a else {}), (pgm_b[0] if pgm_b else {}))
        ]
        pgm_spans = [x for x in pgm_spans if x is not None]
        max_pgm_span = max(pgm_spans) if pgm_spans else None
        calc_total = fnum(pgm.get("전체"))
        direct_total = fnum(pgm.get("전체직접"))
        crosscheck_gap = fnum(pgm.get("검산차이"))
        direction_consistent = bool(
            calc_total is not None and direct_total is not None
            and ((calc_total == 0 and direct_total == 0)
                 or (calc_total != 0 and direct_total != 0 and (calc_total < 0) == (direct_total < 0)))
        )
        crosscheck_ratio_pct = None
        if crosscheck_gap is not None and calc_total is not None and direct_total is not None:
            denom = max(abs(calc_total), abs(direct_total), 1.0)
            crosscheck_ratio_pct = abs(crosscheck_gap) / denom * 100.0
        crosscheck_consistent = bool(
            crosscheck_ratio_pct is not None and crosscheck_ratio_pct <= MAX_PROGRAM_CROSSCHECK_RATIO_PCT
        )
        program_quality = bool(
            pgm_aligned
            and max_pgm_span is not None
            and max_pgm_span <= MAX_PROGRAM_SNAPSHOT_SKEW_SEC
            and direction_consistent
            and crosscheck_consistent
            and pgm_a[0].get("source_time_verified") is not False
            and pgm_b[0].get("source_time_verified") is not False
        )

        # '두 시장 모두 음수'와 '두 시장을 주도'를 구분한다.
        # 현물/선물의 최다 매도자가 같을 때만 단일 주체 주도로 올린다.
        if spot_leader and spot_leader == fut_leader:
            if pgm_neg and program_quality:
                verdict = f"{spot_leader}: 현물·선물 모두 최다 매도 + 프로그램 매도 동반 — 주도 가능성 높음"
                confidence = "높음"
            elif pgm_neg:
                verdict = f"{spot_leader}: 현물·선물 모두 최다 매도, 프로그램 매도 방향도 확인 — 프로그램 시차·검산 품질 때문에 확신도 상향 보류"
                confidence = "중간"
            else:
                verdict = f"{spot_leader}: 현물·선물 모두 최다 매도 — 주도 후보지만 프로그램 동조는 약함"
                confidence = "중간"
        elif spot_leader and fut_leader and spot_leader != fut_leader:
            verdict = f"현물은 {spot_leader}, 선물은 {ko_subject(fut_leader)} 최다 매도 — 주체 분산, 단일 주도자 확정 보류"
            confidence = "낮음" if not pgm_neg else "중간"
        elif fut_leader and pgm_neg:
            verdict = f"{fut_leader} 선물 최다 매도와 프로그램 매도가 동반 — 파생발 하락 전이 가능성 확인"
            confidence = "중간"
        else:
            verdict = "현물·선물·프로그램이 한 주체로 정렬되지 않아 단일 매도주체 확정 보류"
            confidence = "낮음"
        pgm_kind = "확인 불가"
        if pgm.get("전체") is not None:
            if float(pgm["전체"]) < 0:
                av, nv = pgm.get("차익"), pgm.get("비차익")
                if av is not None and nv is not None:
                    pgm_kind = "비차익 매도 우세" if nv < av else "차익 매도 우세"
                else:
                    pgm_kind = "프로그램 매도"
            elif float(pgm["전체"]) > 0:
                pgm_kind = "프로그램 매수"
            else:
                pgm_kind = "중립"
        return {**meta, "available": True, "start_ts": start_ts, "end_ts": end_ts,
                "leader": spot_leader, "start_gap": spot_start_gap, "end_gap": spot_end_gap,
                "program_source_time_verified": bool(pgm_aligned and
                    pgm_a[0].get("source_time_verified") is not False and
                    pgm_b[0].get("source_time_verified") is not False),
                "spot": spot, "futures": fut, "program": pgm,
                "spot_leader": spot_leader, "spot_leader_value": spot_leader_val,
                "futures_leader": fut_leader, "futures_leader_value": fut_leader_val,
                "cross_sellers": cross_sellers,
                "verdict": verdict, "confidence": confidence, "program_kind": pgm_kind,
                "start_alignment_sec": start_gap, "end_alignment_sec": end_gap,
                "spot_start_alignment_sec": spot_start_gap, "spot_end_alignment_sec": spot_end_gap,
                "futures_start_alignment_sec": fut_start_gap, "futures_end_alignment_sec": fut_end_gap,
                "program_start_alignment_sec": pgm_start_gap, "program_end_alignment_sec": pgm_end_gap,
                "program_sample_span_sec": max_pgm_span,
                "program_crosscheck_gap": crosscheck_gap,
                "program_crosscheck_ratio_pct": crosscheck_ratio_pct,
                "program_direction_consistent": direction_consistent,
                "program_direct_total": direct_total,
                "program_quality": program_quality}

    def option_move(self, start_ts: float, end_ts: float) -> tuple[str, float] | None:
        best = None
        for opt in self.put_defs:
            b = self.puts.get(opt["code"])
            if not b:
                continue
            a = self._nearest(b, start_ts); z = self._nearest(b, end_ts)
            if not a or not z or a[1] <= 0:
                continue
            mult = z[1] / a[1]
            if best is None or mult > best[1]:
                best = (opt["name"], mult)
        return best

    def build_open_gap_alert(self, snap: dict[str, Any]) -> str:
        idx = snap.get("KOSPI") or {}
        prev = fnum(idx.get("prev_close"))
        opn = fnum(idx.get("open"))
        opct = fnum(idx.get("open_pct"))
        if opct is None:
            opct = pct(prev, opn)
        lines = [
            "⚠️ <b>코스피 개장 갭다운</b>",
            f"<code>{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} KST</code>",
            "",
            f"• 전일 종가 <b>{prev:,.2f}</b>" if prev is not None else "• 전일 종가 확인 불가",
            f"• 시가 <b>{opn:,.2f}</b>" if opn is not None else "• 시가 확인 불가",
            f"• 개장 갭 <b>{opct:+.2f}%</b>" if opct is not None else "• 개장 갭 확인 불가",
            "",
            "• 전일 종가→시가 구간에는 동일한 장중 수급 기준점이 없으므로 특정 매도주체를 단정하지 않습니다.",
            "• 개장 이후의 현물·선물·프로그램 급락 사건은 별도 사건구간으로 계속 추적합니다.",
            "",
            "• " + " · ".join([link(KOSPI_URL,"KOSPI"), link(LS_URL,"LS OpenAPI")]),
        ]
        lines += cash_lines(self._cash_supplement("KOSPI", time.time()), "KOSPI")
        return "\n".join(lines)

    def build_alert(self, stage: str, ep: dict[str, Any], end_ts: float, end_price: float) -> str:
        att = self.attribution(float(ep["start_ts"]), end_ts)
        drop = pct(float(ep["start_price"]), end_price) or 0.0
        if ep.get("price_only"):
            title = (
                "⚠️ <b>코스피 급락 가격구간 포착 · 수급 원인 보류</b>"
                if stage == "start" else
                "🔴 <b>코스피 급락 가격구간 확대 · 수급 원인 보류</b>"
            )
        else:
            title = "🚨 <b>코스피 급락 사건구간 포착</b>" if stage == "start" else "🔴 <b>코스피 급락 사건구간 확대</b>"
        lines = [title, f"<code>{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} KST</code>", "",
                 "<b>급락 구간</b>",
                 f"• 시작 <b>{fmt_clock(ep['start_ts'])}</b> → 현재 <b>{fmt_clock(end_ts)}</b> · {fmt_duration(int(end_ts)-int(float(ep['start_ts'])))}",
                 f"• KOSPI <b>{float(ep['start_price']):,.2f}</b> → <b>{end_price:,.2f}</b> · <b>{drop:+.2f}%</b>",
                 f"• 현재 구간 저점 <b>{float(ep['low_price']):,.2f}</b> ({fmt_clock(ep['low_ts'])})", ""]
        if ep.get("price_only"):
            if "alignment exceeds" in str(ep.get("price_only_reason") or ""):
                lines += [
                    "⚠️ <b>수급 기준점 시간 정렬 미충족</b> — 가격 급락은 확인됐지만",
                    "• 사건 시작 직전 수급 시차가 30초를 넘어 주체 판정을 보류합니다. 감시 중단으로 단정하지 않습니다.",
                    "",
                ]
            else:
                lines += [
                    "⚠️ <b>수급 기준점 미확보</b> — 가격 급락은 확인됐지만",
                    "• 사건 시작 이전의 정확한 현물·선물·프로그램 기준점이 없어 매도주체는 소급 추정하지 않습니다.",
                    "",
                ]
        lines += ["<b>그 구간에서 누가 팔았나</b>"]
        lines += market_attribution_lines(att, "KOSPI")
        opt = self.option_move(float(ep["start_ts"]), end_ts)
        if opt:
            lines += ["", "<b>파생 증폭 확인</b>", f"• 근접 위클리 풋 <b>{html.escape(opt[0])}</b> · 사건 시작 대비 <b>{opt[1]:.1f}배</b>"]
        lines += [
            "",
            market_attribution_footer("KOSPI"),
            "• 검증: 수급 시차 30초·프로그램 합계 차이 1% 초과 시 확신도 보류. 프로그램 수급은 특정 투자자에게 귀속하지 않으며 LS 원값을 임의 환산하지 않습니다.",
            "• " + " · ".join([link(KOSPI_URL,"KOSPI"), link(NEWS_URL,"급락 뉴스"), link(LS_URL,"LS OpenAPI")]),
        ]
        return "\n".join(lines)

    async def _prepare_program_close(self, close_dt: dt.datetime | None,
                                     test_seconds: int | None, now: dt.datetime | None = None) -> None:
        if not should_finalize_market_close(now or dt.datetime.now(KST), close_dt, test_seconds):
            return
        state = self._daily_close_state(close_dt.date().isoformat())
        for market in ("KOSPI", "KOSDAQ"):
            if market in state["plans"] or market in state["message_ids"]:
                continue
            try:
                result = await asyncio.to_thread(
                    collect_program_close, self.token, market, close_dt.timestamp(), ls_post
                )
            except Exception as exc:
                result = {"market": market, "status": "held",
                          "reason": f"{type(exc).__name__}: {exc}"}
            self.raw.setdefault("program_close", {})[market] = result

    def _daily_close_state(self, day: str) -> dict[str, Any]:
        state = getattr(self, "daily_close", {})
        if not isinstance(state, dict) or state.get("date") != day:
            state = {"date": day, "last_completed": {}, "plans": {}, "message_ids": {}}
            self.daily_close = state
        return state

    def _cash_supplement(self, market: str, at_ts: float) -> dict | None:
        rows = getattr(self, "flows" if market == "KOSPI" else "kosdaq_flows", ())
        values = [x.get("cash_supplement") for x in rows if isinstance(x.get("cash_supplement"), dict)
                  and 0 < float(x["cash_supplement"].get("received_ts") or 0) <= at_ts]
        return max(values, key=lambda x: x["received_ts"]) if values else None

    def _remember_completed_episode(self, market: str, ep: dict[str, Any],
                                    attribution: dict[str, Any], ended_ts: float) -> None:
        day = dt.datetime.fromtimestamp(float(ep["start_ts"]), KST).date().isoformat()
        state = self._daily_close_state(day)
        state["last_completed"][market] = json.loads(json.dumps({
            "episode": ep, "attribution": attribution, "ended_ts": ended_ts,
        }))

    def _close_quote(self, market: str, close_dt: dt.datetime, now: dt.datetime) -> dict[str, Any]:
        series = self.idx if market == "KOSPI" else self.kosdaq_idx
        if not series:
            return {"available": False, "reason": "마감 시세 조회 기록 없음"}
        ts, price = series[-1]
        valid = (fnum(price) is not None and float(price) > 0
                 and close_dt.timestamp() <= ts <= now.timestamp() + 5
                 and 0 <= now.timestamp() - ts <= 90
                 and dt.datetime.fromtimestamp(ts, KST).date() == close_dt.date())
        return {"available": valid, "observed_ts": ts, "observed_price": price,
                "reason": "" if valid else "마감 이후의 신선한 시세 미확보",
                "independent_official_close_verified": False}

    def _build_daily_close_plan(self, market: str, close_dt: dt.datetime,
                               now: dt.datetime) -> dict[str, Any]:
        state = self._daily_close_state(close_dt.date().isoformat())
        active = self.episode if market == "KOSPI" else self.kosdaq_episode
        completed = state["last_completed"].get(market)
        candidate = None
        if active:
            att = (self.attribution if market == "KOSPI" else self._kosdaq_attribution)(
                float(active["start_ts"]), float(active["low_ts"]))
            candidate = {"episode": active, "attribution": att, "origin": "active"}
        elif completed:
            candidate = {**completed, "origin": "completed_intraday"}
        quote = self._close_quote(market, close_dt, now)
        price = quote.get("observed_price") if quote["available"] else None
        observed_ts = quote.get("observed_ts", close_dt.timestamp())
        label = "코스피" if market == "KOSPI" else "코스닥"
        program = (self.raw.get("program_close") or {}).get(market)
        if candidate:
            ep = json.loads(json.dumps(candidate["episode"]))
            ep["market"] = market
            att = json.loads(json.dumps(candidate["attribution"]))
            if market == "KOSPI":
                text = self.build_end(ep, observed_ts, price, session_close=True, attribution=att)
            else:
                text = self.build_kosdaq_drop_alert("close", ep, observed_ts, price,
                                                   session_close=True, attribution=att)
            if candidate["origin"] == "completed_intraday":
                text += f"\n• 대상: 장중 {fmt_clock(candidate['ended_ts'])}에 종료된 마지막 급락 사건."
        else:
            # The close timestamp is a daily summary identity, not a fabricated incident.
            ep = {"market": market, "start_ts": close_dt.timestamp(),
                  "low_ts": close_dt.timestamp(), "daily_summary_only": True}
            att = {}
            lines = [f"🟣 <b>{label} 장마감 요약</b>",
                     f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>", "",
                     "• 기록된 급락 경보 사건 없음 (감시에서 수집된 범위)." if price is not None
                     else "• 급락 사건·마감 시세 확인 보류: 마감 이후 시세 미확보."]
            if price is not None:
                lines.append(f"• 마감 조회 시세 <b>{price:,.2f}</b> (조회 {fmt_clock(observed_ts)})")
            lines += ["• 사건 시작·저점 수급이 없어 매도주체 판정은 하지 않습니다."]
            lines += cash_lines(self._cash_supplement(market, now.timestamp()), market, now.timestamp())
            lines += render_program_close(program, market)
            lines += ["• 마감 조회 시세의 공식 종가 독립 대조는 미완료입니다.",
                      "• " + link(KOSPI_URL if market == "KOSPI" else KOSDAQ_URL, market)]
            text = "\n".join(lines)
        return json.loads(json.dumps({
            "session_date": close_dt.date().isoformat(), "market": market,
            "stage": "close" if market == "KOSPI" else "kosdaq_shock_close",
            "episode": ep, "origin": candidate["origin"] if candidate else "summary_only",
            "quote": quote, "observed_ts": observed_ts, "attribution": att,
            "program_close": program, "text": text,
            "request_body_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }))

    async def _finalize_daily_close(self, close_dt: dt.datetime | None,
                                    test_seconds: int | None = None,
                                    now: dt.datetime | None = None) -> None:
        now = now or dt.datetime.now(KST)
        if (not should_finalize_market_close(now, close_dt, test_seconds)
                or now.date() != close_dt.date()):
            return
        state = self._daily_close_state(close_dt.date().isoformat())
        await self._prepare_program_close(close_dt, test_seconds, now)
        for market in ("KOSPI", "KOSDAQ"):
            if market not in state["plans"] and market not in state["message_ids"]:
                state["plans"][market] = self._build_daily_close_plan(market, close_dt, now)
        # Freeze both bodies and incident identities before either send. A restart
        # reuses the existing delivery journal's approval for the same plan.
        self._checkpoint_handoff(force=True)
        errors, enrichment = {}, []
        for market in ("KOSPI", "KOSDAQ"):
            if market in state["message_ids"]:
                continue
            plan = state["plans"][market]
            ep = plan["episode"]
            try:
                msg_id = await self._send_event(plan["stage"], ep, plan["observed_ts"], plan["text"])
                state["message_ids"][market] = msg_id
                self.msg_ids.append(msg_id)
                if market == "KOSPI":
                    self.episode = None
                    self.last_episode_end_ts = plan["observed_ts"]
                else:
                    self.kosdaq_episode = None
                    self.kosdaq_last_episode_end_ts = plan["observed_ts"]
                self._record_delivery(plan["stage"], msg_id, ep, plan["observed_ts"], evidence={
                    "market_attribution": plan["attribution"], "program_close": plan["program_close"],
                    "episode_origin": plan["origin"], "close_quote": plan["quote"],
                    "request_body_sha256": plan["request_body_sha256"],
                })
                if plan["origin"] == "active":
                    enrichment.append((market, ep, plan["attribution"]))
            except Exception as exc:
                errors[market] = f"{type(exc).__name__}: {exc}"
        self.raw["daily_close"] = {
            "date": state["date"], "message_ids": dict(state["message_ids"]),
            "complete": set(state["message_ids"]) == {"KOSPI", "KOSDAQ"}, "errors": errors,
        }
        self._checkpoint_handoff(force=True)
        if errors:
            raise RuntimeError("Daily close delivery incomplete: " + "; ".join(
                market + " " + error for market, error in errors.items()))
        for market, ep, att in enrichment:
            run = self._run_enrichment if market == "KOSPI" else self._run_kosdaq_enrichment
            task = asyncio.create_task(run(json.loads(json.dumps(ep)), att))
            self.enrichment_tasks.add(task)
            task.add_done_callback(self.enrichment_tasks.discard)

    def build_end(
        self,
        ep: dict[str, Any],
        end_ts: float,
        end_price: float | None,
        session_close: bool = False,
        attribution: dict[str, Any] | None = None,
    ) -> str:
        att = attribution if attribution is not None else self.attribution(float(ep["start_ts"]), float(ep["low_ts"]))
        drop = pct(float(ep["start_price"]), float(ep["low_price"])) or 0.0
        rebound = pct(float(ep["low_price"]), end_price) or 0.0
        if ep.get("price_only"):
            title = (
                "🟣 <b>코스피 급락 가격구간 장마감 확정 · 수급 원인 보류</b>"
                if session_close else
                "🟢 <b>코스피 급락 가격구간 종료·반등 확인 · 수급 원인 보류</b>"
            )
        else:
            title = (
                "🟣 <b>코스피 급락 사건구간 장마감 확정</b>"
                if session_close else
                "🟢 <b>코스피 급락 사건구간 종료·반등 확인</b>"
            )
        lines = [title, f"<code>{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} KST</code>", "",
                 "<b>확정된 급락 구간</b>",
                 f"• <b>{fmt_clock(ep['start_ts'])} → {fmt_clock(ep['low_ts'])}</b> · {fmt_duration(int(float(ep['low_ts']))-int(float(ep['start_ts'])))}",
                 f"• KOSPI <b>{float(ep['start_price']):,.2f}</b> → <b>{float(ep['low_price']):,.2f}</b> · <b>{drop:+.2f}%</b>",
                 (
                     (f"• 저점 이후 마감 조회 시세 <b>{end_price:,.2f}</b> (조회 {fmt_clock(end_ts)}) · 반등 <b>{rebound:+.2f}%</b>"
                      if end_price is not None else "• 마감 조회 시세 확인 보류: 마감 이후의 신선한 시세 미확보.")
                     if session_close else
                     f"• 저점 이후 현재 <b>{end_price:,.2f}</b> · 반등 <b>{rebound:+.2f}%</b>"
                 ), "",
                 "<b>저점까지 실제 매도주체</b>"]
        lines += market_attribution_lines(att, "KOSPI", final=True)
        if session_close:
            lines += render_program_close((getattr(self, "raw", {}).get("program_close") or {}).get("KOSPI"), "KOSPI")
            lines += ["", "• <b>장 마감으로 사건 추적을 종료합니다. 복원 여부는 확정하지 않습니다.</b>"]
            lines += ["• 마감 조회 시세의 공식 종가 독립 대조는 미완료입니다."]
        lines += ["", market_attribution_footer("KOSPI", final=True),
                  "• " + " · ".join([link(KOSPI_URL,"KOSPI"), link(NEWS_URL,"관련 뉴스")])]
        return "\n".join(lines)

    async def _run_enrichment(self, ep: dict[str, Any], att: dict[str, Any]) -> None:
        async with self.enrichment_sem:
            source_ready = False
            try:
                text, detail = await asyncio.to_thread(
                    build_enrichment, self.token, ep, att
                )
                text += "\n" + "\n".join(cash_lines(att.get("cash_supplement"), "KOSPI", att.get("end_ts")))
                source_ready = True
                msg_id = await self._send_event("enrichment", ep, float(ep.get("low_ts") or time.time()), text)
                self.enrichment_msg_ids.append(msg_id)
                self._record_delivery("enrichment", msg_id, ep, float(ep.get("low_ts") or time.time()))
                self.raw["last_enrichment"] = {
                    "generated_at_kst": detail.get("generated_at_kst"),
                    "market_basis": detail.get("market_basis"),
                    "stock_count": len(detail.get("stocks") or []),
                    "industry_count": len(detail.get("industries") or []),
                    "theme_count": len(detail.get("themes") or []),
                    "etf_count": len(detail.get("etfs") or []),
                    "errors": detail.get("errors") or [],
                    "message_id": msg_id,
                }
            except Exception as exc:
                self.raw["last_enrichment_error"] = f"{type(exc).__name__}: {exc}"
                self.raw["last_enrichment_error_phase"] = "delivery" if source_ready else "source"
                print(f"kospi_enrichment_error={type(exc).__name__}: {exc}", flush=True)

    async def _run_kosdaq_enrichment(self, ep: dict[str,Any], att: dict[str,Any]) -> None:
        """기존 코스피 정밀분해의 송출·인계 경로를 재사용하되 시장은 코스닥으로 한정."""
        async with self.enrichment_sem:
            source_ready = False
            try:
                text, detail = await asyncio.to_thread(build_kosdaq_enrichment,self.token,ep,att)
                text += "\n" + "\n".join(cash_lines(att.get("cash_supplement"), "KOSDAQ", att.get("end_ts")))
                source_ready = True
                msg_id = await self._send_event("kosdaq_enrichment", ep, float(ep.get("low_ts") or time.time()), text)
                self.enrichment_msg_ids.append(msg_id)
                self._record_delivery("kosdaq_enrichment",msg_id,ep,float(ep.get("low_ts") or time.time()))
                self.raw["last_kosdaq_enrichment"]={
                    "generated_at_kst":detail.get("generated_at_kst"),
                    "market_basis":detail.get("market_basis"),
                    "stock_count":len(detail.get("stocks") or []),
                    "industry_count":len(detail.get("industries") or []),
                    "theme_count":len(detail.get("themes") or []),
                    "etf_count":len(detail.get("etfs") or []),
                    "errors":detail.get("errors") or [],
                    "message_id":msg_id,
                }
            except Exception as exc:
                self.raw["last_kosdaq_enrichment_error"]=f"{type(exc).__name__}: {exc}"
                self.raw["last_kosdaq_enrichment_error_phase"] = "delivery" if source_ready else "source"
                print(f"kosdaq_enrichment_error={type(exc).__name__}: {exc}",flush=True)
                if source_ready:
                    # A send/checkpoint failure is not a missing market-data source.
                    # Preserve its receipt/uncertainty instead of sending a false source hold.
                    return
                # 원자료가 부족할 때 코스피 종목·선물 수급을 대신 쓰지 않는다.
                # Telegram을 통한 오류 상태 고지는 별도 후보 숫자를 꾸며내지 않는다.
                try:
                    lines=[
                        "🔎 <b>코스닥 급락 정밀분해 · 원자료 확인 보류</b>",
                        f"• 사건구간 {fmt_clock(ep.get('start_ts'))} → {fmt_clock(ep.get('low_ts'))}",
                        "• 코스닥 업종·종목·ETF에 필요한 LS 자료 확보 실패 — 매도종목을 추정하지 않습니다.",
                        "• 코스피200 선물과 코스피 종목 자료를 코스닥 근거로 대체하지 않습니다.",
                    ]
                    msg_id=await self._send_event("kosdaq_enrichment_hold", ep, float(ep.get("low_ts") or time.time()), "\n".join(lines))
                    self.enrichment_msg_ids.append(msg_id)
                    self._record_delivery("kosdaq_enrichment_hold",msg_id,ep,float(ep.get("low_ts") or time.time()))
                except Exception as notify_exc:
                    self.raw["last_kosdaq_enrichment_hold_notify_error"]=f"{type(notify_exc).__name__}: {notify_exc}"

    async def maybe_flow(self) -> None:
        now = time.time()
        if self.flow_task and not self.flow_task.done():
            return
        if now - self.last_flow_poll < FLOW_INTERVAL_SEC:
            return
        self.last_flow_poll = now
        async def run_one():
            try:
                loop = asyncio.get_running_loop()
                publish = lambda point: loop.call_soon_threadsafe(self.flows.append, point)
                snap = await asyncio.to_thread(fetch_flow_snapshot, self.token, "KOSPI", publish)
                self.raw["last_flow_snapshot"] = snap
                snapshot_ok, issues = flow_snapshot_health(snap)
                if snapshot_ok:
                    self.last_flow_success_ts = time.time()
                    self.raw.pop("last_flow_health_issue", None)
                    prior_error = self.raw.pop("last_flow_error", None)
                    if prior_error:
                        self.raw["last_flow_recovered_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
                else:
                    self.raw["last_flow_health_issue"] = issues
                cutoff = time.time() - FLOW_LOOKBACK_SEC
                while self.flows and float(self.flows[0].get("ts", 0)) < cutoff:
                    self.flows.popleft()
            except Exception as exc:
                self.raw["last_flow_error"] = f"{type(exc).__name__}: {exc}"
        self.flow_task = asyncio.create_task(run_one())


    async def maybe_kosdaq_flow(self) -> None:
        """코스닥 자체의 3개 채널을 독립 조회. 가격 감시는 기다리지 않는다."""
        # 기존 가격·급락 회귀시험의 __new__ 부분 객체에는 신규 필드가 없다.
        if not hasattr(self, "kosdaq_flows") or not getattr(self, "token", None):
            return
        now = time.time()
        if self.kosdaq_flow_task and not self.kosdaq_flow_task.done():
            return
        if now - self.kosdaq_last_poll < FLOW_INTERVAL_SEC:
            return
        self.kosdaq_last_poll = now

        async def run_one():
            try:
                loop = asyncio.get_running_loop()
                publish = lambda point: loop.call_soon_threadsafe(self.kosdaq_flows.append, point)
                snap = await asyncio.to_thread(fetch_flow_snapshot, self.token, "KOSDAQ", publish)
                ok, issues = flow_snapshot_health(snap)
                self.raw["last_kosdaq_flow_snapshot"] = snap
                spot = snap.get("현물") or {}
                # Spot surge continuity remains independent of unavailable derivatives.
                sample_ts = fnum(spot.get("sample_ts"))
                if sample_ts and -5 <= time.time()-sample_ts <= MAX_FLOW_HEALTH_AGE_SEC:
                    self.kosdaq_last_success_ts = sample_ts
                self.raw["last_kosdaq_flow"] = {
                    "sample_at_kst": fmt_clock(sample_ts),
                    "last_received_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
                    "market": "KOSDAQ", "sources": {key: (snap.get(key) or {}).get("source_tr")
                                                     for key in ("현물", "지수선물", "프로그램")},
                }
                if ok:
                    self.raw.pop("last_kosdaq_flow_error", None)
                    self.raw.pop("last_kosdaq_flow_health_issue", None)
                else:
                    self.raw["last_kosdaq_flow_health_issue"] = issues
                cutoff = time.time() - FLOW_LOOKBACK_SEC
                while self.kosdaq_flows and float(self.kosdaq_flows[0].get("ts", 0)) < cutoff:
                    self.kosdaq_flows.popleft()
            except Exception as exc:
                self.raw["last_kosdaq_flow_error"] = f"{type(exc).__name__}: {exc}"

        self.kosdaq_flow_task = asyncio.create_task(run_one())

    async def seed_kosdaq_backfill(self) -> None:
        """코스닥도 오늘의 1분봉으로 최근 고점을 복원한다. KOSPI 수집은 독립 실행."""
        try:
            rows=await asyncio.to_thread(backfill_index_bars, self.token, 300, "301")
            cutoff=time.time()-PRICE_LOOKBACK_SEC
            merged={float(ts):float(price) for ts,price in rows
                    if ts>=cutoff and price>0}
            merged.update({float(ts):float(price) for ts,price in self.kosdaq_idx
                           if ts>=cutoff and price>0})
            self.kosdaq_idx=deque(sorted(merged.items()),maxlen=30000)
            self.raw["kosdaq_backfill_rows"]=len(rows)
        except Exception as exc:
            self.raw["kosdaq_backfill_error"]=f"{type(exc).__name__}: {exc}"

    async def maybe_kosdaq_price(self) -> None:
        """t1511 코스닥 현재가를 별도로 조회한다. 가격 지연이 코스피 루프를 막지 않는다."""
        if not hasattr(self,"kosdaq_idx") or not getattr(self,"token",None):
            return
        now=time.time()
        if self.kosdaq_price_task and not self.kosdaq_price_task.done():
            return
        if now-self.kosdaq_last_price_poll<KOSDAQ_PRICE_POLL_INTERVAL_SEC:
            return
        self.kosdaq_last_price_poll=now

        async def run_one():
            try:
                idx=await asyncio.to_thread(fetch_kosdaq_index_quote,self.token)
                received_ts=time.time()
                price=float(idx["price"])
                opening=fnum(idx.get("open"))
                prev_close=fnum(idx.get("prev_close"))
                open_ts=getattr(self,"session_open_ts",None)
                usable=True
                reason=None
                if open_ts is not None and received_ts<open_ts:
                    usable=False
                    reason="정규장 개장 전 전일종가 유지값"
                elif open_ts is not None and not self.kosdaq_regular_price_ready:
                    if opening is None or opening<=0:
                        usable=False
                        reason="코스닥 개장 시가 미확인"
                    elif (prev_close is not None and prev_close>0
                          and abs((opening/prev_close-1.0)*100)>=0.5
                          and abs((price/prev_close-1.0)*100)<=0.01):
                        usable=False
                        reason="코스닥 시가 갭과 다른 전일종가 유지값"
                if usable:
                    self.kosdaq_idx.append((received_ts,price))
                    self.kosdaq_regular_price_ready=True
                    self.kosdaq_last_idx_tick_ts=received_ts
                    cutoff=received_ts-PRICE_LOOKBACK_SEC
                    while self.kosdaq_idx and self.kosdaq_idx[0][0]<cutoff:
                        self.kosdaq_idx.popleft()
                    if self.raw.pop("last_kosdaq_price_error",None):
                        self.raw["kosdaq_price_recovered_at_kst"]=fmt_clock(received_ts)
                else:
                    self.raw["last_kosdaq_unconfirmed_price"]={
                        "observed_at":fmt_clock(received_ts),"reason":reason,
                        "price":price,"open":opening,"prev_close":prev_close,
                    }
                self.kosdaq_last_price_snapshot=dict(idx)
                self.raw["last_kosdaq_price_snapshot"]={
                    "market":"KOSDAQ","source":"LS t1511 upcode=301",
                    "received_at_kst":fmt_clock(received_ts),
                    "price":price,"open":opening,"prev_close":prev_close,
                    "regular_price_usable":usable,
                }
            except Exception as exc:
                self.raw["last_kosdaq_price_error"]=f"{type(exc).__name__}: {exc}"
                self.raw["kosdaq_price_poll_failures_total"]=int(
                    self.raw.get("kosdaq_price_poll_failures_total",0)
                )+1

        self.kosdaq_price_task=asyncio.create_task(run_one())

    def build_kosdaq_drop_alert(self, stage: str, ep: dict[str, Any],
                                now_ts: float, price: float | None,
                                session_close: bool=False,
                                attribution: dict[str, Any] | None = None) -> str:
        label={"start":"🚨 코스닥 급락 포착", "expand":"🔴 코스닥 급락 확대",
               "end":"🟢 코스닥 급락 종료·반등 확인",
               "close":"🟣 코스닥 급락 장마감 확정"}.get(stage,"코스닥 급락")
        start_ts=float(ep["start_ts"])
        low_ts=float(ep["low_ts"])
        low=float(ep["low_price"])
        is_final=stage in {"end","close"}
        end_point=low if is_final else price
        change=pct(float(ep["start_price"]),end_point)
        att=attribution if attribution is not None else self._kosdaq_attribution(start_ts, low_ts if is_final else now_ts)
        lines=[
            f"<b>{label}</b>",
            f"<code>{dt.datetime.fromtimestamp(time.time(),KST):%Y-%m-%d %H:%M:%S} KST</code>",
            f"• 구간 <b>{fmt_clock(start_ts)} → {fmt_clock(low_ts if is_final else now_ts)}</b> · {fmt_duration(int(low_ts if is_final else now_ts)-int(start_ts))}",
            f"• 코스닥 <b>{float(ep['start_price']):,.2f} → {end_point:,.2f}</b> ({change:+.2f}%)",
        ]
        if is_final:
            rebound=pct(low,price) or 0.0
            if session_close or stage == "close":
                lines.append(f"• 저점 이후 마감 조회 시세 {price:,.2f} (조회 {fmt_clock(now_ts)}) · 반등 {rebound:+.2f}%"
                             if price is not None else "• 마감 조회 시세 확인 보류: 마감 이후의 신선한 시세 미확보.")
            else:
                lines.append(f"• 저점 이후 현재 {price:,.2f} · 반등 {rebound:+.2f}%")
        lines += ["", "<b>그 구간에서 누가 팔았나</b>"]
        lines += market_attribution_lines(att, "KOSDAQ", final=is_final)
        if session_close or stage == "close":
            lines += render_program_close((getattr(self, "raw", {}).get("program_close") or {}).get("KOSDAQ"), "KOSDAQ")
            lines += ["• 마감 조회 시세의 공식 종가 독립 대조는 미완료입니다."]
        lines.extend([
            market_attribution_footer("KOSDAQ", final=is_final),
            "• 코스피200 선물·코스피 프로그램 수급은 코스닥 매도주체로 사용하지 않습니다.",
            "• "+ " · ".join([link(KOSDAQ_URL,"KOSDAQ"),link(KOSDAQ_NEWS_URL,"관련 뉴스")]),
        ])
        text = "\n".join(lines)
        self._kosdaq_render_evidence = json.loads(json.dumps({
            "stage": "kosdaq_shock_" + stage, "event_start_ts": start_ts,
            "event_low_ts": low_ts, "request_body_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "market_attribution": att, "original_http_bytes_preserved": False,
        }))
        return text

    async def maybe_alert_kosdaq_drop(self) -> None:
        if getattr(self,"test",False) or not getattr(self,"kosdaq_idx",None):
            return
        if not getattr(self,"kosdaq_regular_price_ready",False):
            return
        now_t,price=self.kosdaq_idx[-1]
        if now_t<=self.kosdaq_last_price_processed_ts:
            return
        age=time.time()-now_t
        if not (-5.0<=age<=KOSDAQ_PRICE_MAX_AGE_SEC):
            self.raw["kosdaq_stale_price_alert_suppressed"]={
                "source_time":fmt_clock(now_t),"age_sec":round(age,1),
            }
            return
        if not price_event_window_open(now_t,getattr(self,"session_close_ts",None),time.time()):
            return
        self.kosdaq_last_price_processed_ts=now_t

        if (not self.kosdaq_opening_gap_sent
                and self.session_open_ts is not None
                and self.session_open_ts<=now_t<=self.session_open_ts+15*60):
            idx=self.kosdaq_last_price_snapshot
            prev=fnum(idx.get("prev_close"))
            opn=fnum(idx.get("open"))
            gap=pct(prev,opn)
            if gap is not None and gap<=OPEN_GAP_ALERT_PCT:
                text="\n".join([
                    "⚠️ <b>코스닥 개장 갭다운</b>",
                    f"<code>{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} KST</code>",
                    f"• 전일 종가 {prev:,.2f} → 시가 {opn:,.2f} · <b>{gap:+.2f}%</b>",
                    "• 전일 종가→시가 갭과 개장 이후 현물 순매도를 별도로 판정합니다.",
                    "• "+link(KOSDAQ_URL,"코스닥 지수"),
                ])
                text += "\n" + "\n".join(cash_lines(self._cash_supplement("KOSDAQ", now_t), "KOSDAQ", now_t))
                msg_id=await self._try_send_event("kosdaq_open_gap", {"market":"KOSDAQ","start_ts":self.session_open_ts}, now_t, text)
                if msg_id is not None:
                    self.msg_ids.append(msg_id)
                    self.kosdaq_opening_gap_sent=True
                    self._record_delivery("kosdaq_open_gap",msg_id,
                                          {"market":"KOSDAQ","start_ts":now_t,"low_ts":now_t},now_t)
        if self.kosdaq_episode is None:
            hit,info=self._kosdaq_trigger()
            if not hit:
                return
            ep={
                "market":"KOSDAQ","start_ts":info["peak_ts"],
                "start_price":info["peak"],"low_ts":now_t,"low_price":price,
                "sent_drop":abs(float(info["drop"])),"trigger":info,
            }
            msg_id=await self._try_send_event("kosdaq_shock_start", ep, now_t, self.build_kosdaq_drop_alert("start",ep,now_t,price))
            self.kosdaq_episode=ep
            if msg_id is None:
                ep["start_delivery_status"]="unconfirmed"
                self._checkpoint_handoff(force=True)
                return
            ep["sent_drop"]=self._approved_drop(msg_id, ep["sent_drop"])
            self.msg_ids.append(msg_id)
            self._record_delivery("kosdaq_shock_start",msg_id,ep,now_t)
            return
        ep=self.kosdaq_episode
        if price<float(ep["low_price"]):
            ep["low_price"]=price
            ep["low_ts"]=now_t
        total_drop=abs(pct(float(ep["start_price"]),price) or 0.0)
        if total_drop>=float(ep.get("sent_drop",0.0))+0.50:
            msg_id=await self._try_send_event("kosdaq_shock_expand", ep, now_t, self.build_kosdaq_drop_alert("expand",ep,now_t,price))
            if msg_id is not None:
                ep["sent_drop"]=self._approved_drop(msg_id, total_drop)
                self.msg_ids.append(msg_id)
                self._record_delivery("kosdaq_shock_expand",msg_id,ep,now_t)
        low_age=now_t-float(ep["low_ts"])
        full_drop=abs(pct(float(ep["start_price"]),float(ep["low_price"])) or 0.0)
        rebound=pct(float(ep["low_price"]),price) or 0.0
        need_rebound=max(0.30,min(0.70,full_drop*0.30))
        recovery_ratio=(
            (price-float(ep["low_price"]))/
            (float(ep["start_price"])-float(ep["low_price"]))
            if float(ep["start_price"])>float(ep["low_price"]) else 0.0
        )
        ended=((low_age>=NEW_LOW_CONFIRM_SEC and rebound>=need_rebound)
               or (low_age>=120 and recovery_ratio>=0.45)
               or (now_t-float(ep["start_ts"])>=MAX_EPISODE_SEC and low_age>=600))
        if ended:
            final_att=self._kosdaq_attribution(float(ep["start_ts"]),float(ep["low_ts"]))
            msg_id=await self._try_send_event("kosdaq_shock_end", ep, now_t, self.build_kosdaq_drop_alert("end",ep,now_t,price))
            if msg_id is None:
                ep["end_delivery_status"]="unconfirmed"
            self._remember_completed_episode("KOSDAQ", ep, final_att, now_t)
            self.kosdaq_episode=None
            self.kosdaq_last_episode_end_ts=now_t
            if msg_id is None:
                self._checkpoint_handoff(force=True)
                return
            self.msg_ids.append(msg_id)
            self._record_delivery("kosdaq_shock_end",msg_id,ep,now_t)
            ep_copy=json.loads(json.dumps(ep))
            task=asyncio.create_task(self._run_kosdaq_enrichment(ep_copy,final_att))
            self.enrichment_tasks.add(task)
            task.add_done_callback(self.enrichment_tasks.discard)

    @staticmethod
    def _build_market_flow_surge_alert(market: str, actor: str, spot: float | None,
                                       spot_window: tuple | list | None, now_ts: float,
                                       industries: dict[str, Any] | None, *,
                                       mode: str, confidence: str, threshold: str,
                                       extra_windows: list[str] | None = None,
                                       extra_lines: list[str] | None = None,
                                       alert_title: str | None = None) -> str:
        """One reader contract for every actor in either market's buy alerts."""
        name = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}[market]
        windows = ([f"현물 {fmt_clock(spot_window[0])}~{fmt_clock(spot_window[1])}"]
                   if spot_window else []) + (extra_windows or [])
        lines = [
            alert_title or f"⚡ <b>{name} 단기 순매수 급증</b>",
            f"<code>{dt.datetime.fromtimestamp(now_ts, KST):%Y-%m-%d %H:%M:%S} KST</code>",
            f"• <b>{html.escape(actor_label(actor))}</b> · {html.escape(mode)} · 최근 5분",
            f"• 실제 수급 표본: {' / '.join(windows) if windows else '확인 불가'}",
            f"• {name} 현물(통합) <b>{fmt_eok(spot)}</b>",
        ]
        if fnum(spot) is not None and spot > 0 and spot_window:
            lines.extend(industry_context_lines(industries, actor, *spot_window, market=market))
        else:
            lines.append("• 현물 업종 순매수 증가 확인 보류 — 같은 구간의 현물 순매수 증가 없음 또는 표본 부족")
        lines += [
            "• 업종 순위는 현물 기준이며 선물·프로그램의 업종별 자금 배분을 뜻하지 않습니다.",
            f"• 확인 수준: {html.escape(confidence)}",
        ]
        lines.extend(extra_lines or [])
        if market == "KOSDAQ":
            lines.extend(["• " + SUBGROUP_NOTE, "• " + FINANCIAL_NOTE])
        else:
            lines.append("• " + TRUST_NOTE)
        lines += [
            f"• 감지 기준: {html.escape(threshold)} · 두 차례 연속 확인",
            "• 당일 누적 순매수의 5분 변화량입니다. 총거래대금·외부 신규자금 유입·주가 상승 확정값이 아닙니다.",
            "• " + " · ".join([link(KOSPI_URL if market == "KOSPI" else KOSDAQ_URL, market),
                                   link(LS_URL, "LS OpenAPI")]),
        ]
        return "\n".join(lines)

    async def _surge_industry_context(self, market: str, actor: str,
                                      spot: float | None, spot_window: tuple | list | None,
                                      session_open_ts: float) -> dict[str, Any] | None:
        if fnum(spot) is None or spot <= 0 or not spot_window:
            return None
        if market == "KOSDAQ" and actor == "금융투자":
            return {
                "market": market, "investor": actor, "requested_window": list(spot_window),
                "available": False, "rows": [], "top": [], "covered_industries": 0,
                "expected_industries": None, "coverage_complete": False,
                "reason": "금융투자 업종 원자료 확인 불가",
            }
        try:
            return await asyncio.to_thread(
                industry_buy_context, *spot_window, actor,
                session_open_ts=session_open_ts, market=market,
            )
        except Exception as exc:
            # Failure of industry detail cannot discard a confirmed market alert.
            return {
                "market": market, "investor": actor, "requested_window": list(spot_window),
                "available": False, "rows": [], "top": [], "covered_industries": 0,
                "expected_industries": None, "coverage_complete": False,
                "reason": "업종 수급 자료 처리 실패", "error_type": type(exc).__name__,
            }

    @staticmethod
    def build_kosdaq_flow_surge_alert(actor: str, delta: float, pair: dict[str, Any],
                                     now_ts: float, industries: dict[str, Any] | None = None,
                                     *, preliminary: bool = False) -> str:
        return Watch._build_market_flow_surge_alert(
            "KOSDAQ", actor, delta, (pair["start_ts"], pair["end_ts"]), now_ts, industries,
            mode="현물 중심",
            confidence=("예비 단계·현물 단독 신호" if preliminary else "현물 단독 신호"),
            threshold=f"현물 {KOSDAQ_SURGE_PREALERT_SPOT_EOK if preliminary else KOSDAQ_SURGE_SINGLE_SPOT_EOK:,.0f}억원 이상",
            extra_lines=["• 지수선물·프로그램: 이 알림의 감지 기준에 사용하지 않음 (KOSPI200 선물·프로그램 수급과 합산하지 않음)"]
                        + cash_lines(pair.get("end", {}).get("cash_supplement"), "KOSDAQ", now_ts),
            alert_title=("🔎 <b>코스닥 단기 순매수 예비 경보</b>" if preliminary else None),
        )

    async def maybe_alert_kosdaq_prealert(self, now_ts: float | None = None) -> None:
        """Send a distinct, lower-threshold KOSDAQ cash-flow early warning."""
        if getattr(self, "test", False) or not getattr(self, "kosdaq_flows", None):
            return
        now_ts = time.time() if now_ts is None else now_ts
        start = getattr(self, "session_open_ts", None)
        end = getattr(self, "session_close_ts", None)
        continuous_end = getattr(self, "session_continuous_end_ts", None)
        if (start is None or end is None or not (start <= now_ts < end)
                or (continuous_end is not None and now_ts >= continuous_end)):
            return
        latest = fnum((self.kosdaq_flows[-1].get("현물") or {}).get("sample_ts"))
        if latest is None or latest <= self.kosdaq_prealert_last_processed_ts:
            return
        self.kosdaq_prealert_last_processed_ts = latest
        pair = _flow_surge_channel_pair(list(self.kosdaq_flows), "현물", now_ts, start)
        candidates = {}
        if pair is not None:
            for actor in KOSDAQ_SURGE_ACTORS:
                delta = fnum((pair.get("deltas") or {}).get(actor))
                if (delta is not None
                        and KOSDAQ_SURGE_PREALERT_SPOT_EOK <= delta < KOSDAQ_SURGE_SINGLE_SPOT_EOK):
                    candidates[actor] = delta
        for actor in list(self.kosdaq_prealert_pending):
            if actor not in candidates:
                self.kosdaq_prealert_pending.pop(actor, None)
        for actor, delta in candidates.items():
            sample_ts = float(pair["end_ts"])
            end_value = (subgroup_value(pair["end"], actor) if actor in {"투신", "금융투자"}
                         else fnum(pair["end"].get(actor)))
            if not confirm_flow_surge(self.kosdaq_prealert_pending, actor, sample_ts, now_ts,
                                      {"spot": end_value}):
                continue
            last_attempt = max(
                self.kosdaq_prealert_sent_at.get(actor, 0.0),
                self._surge_delivery_hold_at("KOSDAQ", actor, "kosdaq_flow_prealert"),
                self.kosdaq_surge_sent_at.get(actor, 0.0),
                self._surge_delivery_hold_at("KOSDAQ", actor),
            )
            if now_ts - last_attempt < SURGE_COOLDOWN_SEC:
                continue
            industries = await self._surge_industry_context(
                "KOSDAQ", actor, delta, (pair["start_ts"], pair["end_ts"]), start)
            text = self.build_kosdaq_flow_surge_alert(
                actor, delta, pair, now_ts, industries, preliminary=True)
            confirmation_first = dict(self.kosdaq_prealert_pending[actor])
            msg_id = await self._try_send_event(
                "kosdaq_flow_prealert", {"market": "KOSDAQ", "actor": actor,
                                         "start_ts": pair["start_ts"], "low_ts": pair["end_ts"]},
                pair["end_ts"], text,
            )
            if msg_id is None:
                self.kosdaq_prealert_pending.pop(actor, None)
                self._checkpoint_handoff(force=True)
                continue
            self.msg_ids.append(msg_id)
            self.kosdaq_prealert_sent_at[actor] = now_ts
            self.kosdaq_prealert_pending.pop(actor, None)
            self.raw["last_kosdaq_prealert_alert"] = {
                "alert_contract": FLOW_SURGE_ALERT_CONTRACT,
                "actor": actor, "market": "KOSDAQ", "spot_5m_eok": delta,
                "threshold_eok": KOSDAQ_SURGE_PREALERT_SPOT_EOK,
                "sample_ts": sample_ts, "message_id": msg_id,
                "spot_window": [pair["start_ts"], pair["end_ts"]],
                "spot_cumulative_start": fnum(pair["start"].get(actor)),
                "spot_cumulative_end": end_value,
                "industry_context": industries,
            }
            self._record_delivery(
                "kosdaq_flow_prealert", msg_id,
                {"start_ts": pair["start_ts"], "low_ts": pair["end_ts"],
                 "market": "KOSDAQ", "actor": actor},
                pair["end_ts"],
                evidence={
                    "alert_contract": FLOW_SURGE_ALERT_CONTRACT,
                    "market": "KOSDAQ", "actor": actor,
                    "stage": "prealert",
                    "source": "LS t1602 market=3 upcode=301 exchgubun=U gubun1=2",
                    "spot_window": [pair["start_ts"], pair["end_ts"]],
                    "spot_start_cumulative": fnum(pair["start"].get(actor)),
                    "spot_end_cumulative": end_value,
                    "spot_delta": delta,
                    "spot_delta_eok": delta,
                    "threshold_eok": KOSDAQ_SURGE_PREALERT_SPOT_EOK,
                    "display_unit": "억원",
                    "confirmation_first": confirmation_first,
                    "confirmation_second": {"sample_ts": sample_ts, "end_values": {"spot": end_value}},
                    "industry_context": industries,
                    "message_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                },
            )
            self._checkpoint_handoff(force=True)

    async def maybe_alert_kosdaq_surge(self, now_ts: float | None = None) -> None:
        if getattr(self, "test", False) or not getattr(self, "kosdaq_flows", None):
            return
        now_ts = time.time() if now_ts is None else now_ts
        start = getattr(self, "session_open_ts", None)
        end = getattr(self, "session_close_ts", None)
        continuous_end = getattr(self, "session_continuous_end_ts", None)
        if (start is None or end is None or not (start <= now_ts < end)
                or (continuous_end is not None and now_ts >= continuous_end)):
            return
        latest = fnum((self.kosdaq_flows[-1].get("현물") or {}).get("sample_ts"))
        if latest is None or latest <= self.kosdaq_surge_last_processed_ts:
            return
        self.kosdaq_surge_last_processed_ts = latest
        pair = _flow_surge_channel_pair(list(self.kosdaq_flows), "현물", now_ts, start)
        candidates = {}
        if pair is not None:
            for actor in KOSDAQ_SURGE_ACTORS:
                delta = fnum((pair.get("deltas") or {}).get(actor))
                if delta is not None and delta >= KOSDAQ_SURGE_SINGLE_SPOT_EOK:
                    candidates[actor] = delta
        for actor in list(self.kosdaq_surge_pending):
            if actor not in candidates:
                self.kosdaq_surge_pending.pop(actor, None)
        for actor, delta in candidates.items():
            sample_ts = float(pair["end_ts"])
            end_value = (subgroup_value(pair["end"], actor) if actor in {"투신", "금융투자"}
                         else fnum(pair["end"].get(actor)))
            if not confirm_flow_surge(self.kosdaq_surge_pending, actor, sample_ts, now_ts,
                                      {"spot": end_value}):
                continue
            last_attempt = max(self.kosdaq_surge_sent_at.get(actor, 0.0),
                               self._surge_delivery_hold_at("KOSDAQ", actor))
            if now_ts - last_attempt < SURGE_COOLDOWN_SEC:
                continue
            industries = await self._surge_industry_context(
                "KOSDAQ", actor, delta, (pair["start_ts"], pair["end_ts"]), start)
            text = self.build_kosdaq_flow_surge_alert(actor, delta, pair, now_ts, industries)
            confirmation_first = dict(self.kosdaq_surge_pending[actor])
            msg_id = await self._try_send_event(
                "kosdaq_flow_surge", {"market": "KOSDAQ", "actor": actor,
                                      "start_ts": pair["start_ts"], "low_ts": pair["end_ts"]},
                pair["end_ts"], text,
            )
            if msg_id is None:
                self.kosdaq_surge_pending.pop(actor, None)
                self._checkpoint_handoff(force=True)
                continue
            self.msg_ids.append(msg_id)
            self.kosdaq_surge_sent_at[actor] = now_ts
            self.kosdaq_surge_pending.pop(actor, None)
            self.raw["last_kosdaq_surge_alert"] = {
                "alert_contract": FLOW_SURGE_ALERT_CONTRACT,
                "actor": actor, "market": "KOSDAQ", "spot_5m_eok": delta,
                "sample_ts": sample_ts, "message_id": msg_id,
                "spot_window": [pair["start_ts"], pair["end_ts"]],
                "spot_cumulative_start": fnum(pair["start"].get(actor)),
                "spot_cumulative_end": end_value,
                "industry_context": industries,
            }
            self._record_delivery(
                "kosdaq_flow_surge", msg_id,
                {"start_ts": pair["start_ts"], "low_ts": pair["end_ts"],
                 "market": "KOSDAQ", "actor": actor},
                pair["end_ts"],
                evidence={
                    "alert_contract": FLOW_SURGE_ALERT_CONTRACT,
                    "market": "KOSDAQ", "actor": actor,
                    "source": "LS t1602 market=3 upcode=301 exchgubun=U gubun1=2",
                    "spot_window": [pair["start_ts"], pair["end_ts"]],
                    "spot_start_cumulative": fnum(pair["start"].get(actor)),
                    "spot_end_cumulative": end_value,
                    "spot_delta": delta,
                    "spot_delta_eok": delta,
                    "display_unit": "억원",
                    "confirmation_first": confirmation_first,
                    "confirmation_second": {"sample_ts": sample_ts, "end_values": {"spot": end_value}},
                    "industry_context": industries,
                    "message_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                },
            )

    def build_flow_surge_alert(self, cand: dict[str, Any], now_ts: float,
                               industries: dict[str, Any] | None = None) -> str:
        spot, fut = cand.get("spot"), cand.get("futures")
        windows = []
        if cand.get("futures_window"):
            window = cand["futures_window"]
            windows.append(f"선물 {fmt_clock(window[0])}~{fmt_clock(window[1])}")
        lines = [f"• KOSPI200 선물 {fmt_eok(fut)} (현물 업종 순위와 분리)"]
        p = cand.get("program") or {}
        if p.get("valid"):
            trend = "순매수 증가" if p["delta"] > 0 else "순매도 증가" if p["delta"] < 0 else "변화 없음"
            amount = fmt_eok(p.get("delta")) if p.get("unit") == "억원" else fmt_raw(p.get("delta"))
            provider = "키움·독립 원화 원표 대조" if p.get("source_tr") == "ka90005" else "LS 원값"
            lines.append(f"• 프로그램 {trend} {amount} ({provider}, 투자자 미구분)")
        else:
            lines.append("• 프로그램 교차검증: 미충족·보류 (매수주체 판정에 사용하지 않음)")
        if self.idx:
            now_price_ts, now_price = self.idx[-1]
            if 0 <= now_ts - now_price_ts <= SURGE_MAX_END_AGE_SEC:
                prior = min(self.idx, key=lambda x: abs(x[0] - (now_price_ts - SURGE_WINDOW_SEC)))
                if abs(prior[0] - (now_price_ts - SURGE_WINDOW_SEC)) <= SURGE_MAX_SAMPLE_SKEW_SEC:
                    change = pct(prior[1], now_price)
                    if change is not None:
                        lines.append(f"• 같은 구간 KOSPI {change:+.2f}% (가격 보조지표)")
        threshold = (f"현물 {SURGE_SINGLE_SPOT_EOK:,.0f}억원 또는 선물 {SURGE_SINGLE_FUT_EOK:,.0f}억원 이상, "
                     f"또는 현물 {SURGE_COMBINED_SPOT_EOK:,.0f}억원·선물 {SURGE_COMBINED_FUT_EOK:,.0f}억원 동시 증가")
        return self._build_market_flow_surge_alert(
            "KOSPI", str(cand["actor"]), spot, cand.get("spot_window"), now_ts, industries,
            mode=str(cand["mode"]),
            confidence=("현물 단독 신호" if cand["mode"] == "현물 중심" else
                        "선물 단독 신호" if cand["mode"] == "선물 중심" else str(cand["confidence"])),
            threshold=threshold,
            extra_windows=windows, extra_lines=lines + cash_lines(cand.get("cash_supplement"), "KOSPI", now_ts),
        )

    async def maybe_alert_flow_surge(self, now_ts: float | None = None) -> None:
        """가격 급락과 독립적으로 동작하며 다른 경보의 상태를 수정하지 않는다."""
        if getattr(self, "test", False) or not getattr(self, "flows", None):
            return
        now_ts = time.time() if now_ts is None else now_ts
        start = getattr(self, "session_open_ts", None)
        end = getattr(self, "session_close_ts", None)
        continuous_end = getattr(self, "session_continuous_end_ts", None)
        if (
            start is None or end is None or not (start <= now_ts < end)
            or (continuous_end is not None and now_ts >= continuous_end)
        ):
            return
        latest_ts = fnum(self.flows[-1].get("ts"))
        if latest_ts is None or latest_ts <= self.surge_last_processed_ts:
            return
        # 같은 원자료로 초당 여러 번 '새 유입'을 판정하지 않는다.
        self.surge_last_processed_ts = latest_ts
        candidates = flow_surge_candidates(list(self.flows), now_ts, start)
        current = {str(x["actor"]): x for x in candidates}
        for actor in list(self.surge_pending):
            if actor not in current:
                self.surge_pending.pop(actor, None)
        for actor, cand in current.items():
            sample_ts = float(cand["sample_ts"])
            channels = ({"spot", "futures"} if cand["mode"] == "현물·선물 동시"
                        else {"futures"} if cand["mode"] == "선물 중심" else {"spot"})
            end_values = {key: fnum(cand.get(key + "_end_cumulative")) for key in channels}
            if not confirm_flow_surge(self.surge_pending, actor, sample_ts, now_ts, end_values):
                continue
            last_attempt = max(self.surge_sent_at.get(actor, 0.0),
                               self._surge_delivery_hold_at("KOSPI", actor))
            if now_ts - last_attempt < SURGE_COOLDOWN_SEC:
                continue
            spot_window = cand.get("spot_window")
            industries = await self._surge_industry_context("KOSPI", actor, cand.get("spot"), spot_window, start)
            text = self.build_flow_surge_alert(cand, now_ts, industries)
            confirmation_first = dict(self.surge_pending[actor])
            msg_id = await self._try_send_event(
                "flow_surge", {"market": "KOSPI", "actor": actor,
                               "start_ts": sample_ts - SURGE_WINDOW_SEC, "low_ts": sample_ts},
                sample_ts, text,
            )
            if msg_id is None:
                self.surge_pending.pop(actor, None)
                self._checkpoint_handoff(force=True)
                continue
            self.msg_ids.append(msg_id)
            self.surge_sent_at[actor] = now_ts
            self.surge_pending.pop(actor, None)
            self.raw["last_flow_surge_alert"] = {
                "alert_contract": FLOW_SURGE_ALERT_CONTRACT,
                "market": "KOSPI", "actor": actor, "mode": cand["mode"],
                "sample_ts": sample_ts, "message_id": msg_id,
                "spot_5m_eok": cand["spot"], "futures_5m_eok": cand["futures"],
                "confidence": cand["confidence"],
                "spot_window": spot_window, "futures_window": cand.get("futures_window"),
                "industry_context": industries,
            }
            # 기존 급락과 동일한 실전 송출 기록/상태 인계 경로를 재사용한다.
            self._record_delivery(
                "flow_surge", msg_id,
                {"start_ts": sample_ts - SURGE_WINDOW_SEC, "low_ts": sample_ts,
                 "market": "KOSPI", "actor": actor},
                sample_ts,
                evidence={
                    "alert_contract": FLOW_SURGE_ALERT_CONTRACT,
                    "market": "KOSPI", "actor": actor,
                    "spot_window": spot_window, "futures_window": cand.get("futures_window"),
                    "spot_delta_eok": cand.get("spot"), "futures_delta_eok": cand.get("futures"),
                    "display_unit": "억원",
                    "spot_start_cumulative": cand.get("spot_start_cumulative"),
                    "spot_end_cumulative": cand.get("spot_end_cumulative"),
                    "confirmation_first": confirmation_first,
                    "confirmation_second": {"sample_ts": sample_ts, "end_values": end_values},
                    "confirmed_cumulative_endpoints": end_values,
                    "industry_context": industries,
                    "message_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                },
            )

    async def evaluate(self) -> None:
        await self.maybe_flow()
        await self.maybe_kosdaq_flow()
        await self.maybe_kosdaq_price()
        await self.maybe_alert_flow_surge()
        await self.maybe_alert_kosdaq_prealert()
        await self.maybe_alert_kosdaq_surge()
        await self.maybe_alert_kosdaq_drop()
        # CI 실데이터 조회(--test)는 소스와 API 품질만 검사한다.
        # 장중 급락 조건이 충족돼도 시험 실행이 실전 Telegram 알림을 보내서는 안 된다.
        if getattr(self, "test", False):
            self.raw["test_mode_notification_suppressed"] = True
            return
        if not self.idx or not getattr(self, "regular_price_ready", True):
            return
        now_t, cur = self.idx[-1]

        if not price_event_window_open(
            now_t, getattr(self, "session_close_ts", None), time.time()
        ):
            self.raw["post_close_alert_suppressed"] = {
                "observed_at_kst": fmt_clock(now_t),
                "reason": "XKRX 정규장 종료 후 신규 급락·확대·반등 판정 중단",
            }
            return

        if (
            not self.opening_gap_sent
            and self.session_open_ts is not None
            and self.session_open_ts <= now_t <= self.session_open_ts + 15 * 60
        ):
            snap = self.raw.get("last_price_snapshot") or {}
            opct = fnum((snap.get("KOSPI") or {}).get("open_pct"))
            if opct is not None and opct <= OPEN_GAP_ALERT_PCT:
                msg_id = await self._try_send_event("open_gap", {"start_ts":self.session_open_ts}, now_t, self.build_open_gap_alert(snap))
                if msg_id is not None:
                    self.msg_ids.append(msg_id)
                    self.opening_gap_sent = True
                    self.raw["opening_gap_alert"] = {
                        "message_id": msg_id, "open_pct": opct,
                        "sent_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
                    }
                    self._record_delivery("open_gap", msg_id,
                                          {"start_ts": self.session_open_ts, "low_ts": now_t}, now_t)
        if self.episode is None:
            hit, info = self._trigger()
            if not hit:
                return

            start_ts = float(info["peak_ts"])
            start_channels = {
                key: self._flow_channel_near(start_ts, key)
                for key in ("현물", "선물", "프로그램")
            }
            if any(start_channels[key] is None for key in ("현물", "선물", "프로그램")):
                # 재기동 전에 시작된 사건도 가격 급락 자체는 숨기지 않는다.
                # 정확한 시작 수급이 없으므로 매도주체는 소급 추정하지 않고 가격구간만 알린다.
                self.raw["historical_price_only_trigger"] = {
                    "peak_ts": info["peak_ts"], "peak": info["peak"],
                    "cur_ts": info["cur_ts"], "cur": info["cur"],
                    "drop": info["drop"], "reason": "missing channel snapshot at/before event start",
                }
                ep = {
                    "start_ts": info["peak_ts"], "start_price": info["peak"],
                    "low_ts": now_t, "low_price": cur, "sent_drop": abs(float(info["drop"])),
                    "alerted": True, "trigger": info, "price_only": True,
                    "price_only_reason": "missing channel snapshot at/before event start",
                }
                msg_id = await self._try_send_event("price_only_start", ep, now_t, self.build_alert("start", ep, now_t, cur))
                self.episode = ep
                if msg_id is None:
                    ep.update(alerted=False, start_delivery_status="unconfirmed")
                    self._checkpoint_handoff(force=True)
                    return
                ep["sent_drop"] = self._approved_drop(msg_id, ep["sent_drop"])
                self.msg_ids.append(msg_id)
                self._record_delivery("price_only_start", msg_id, self.episode, now_t)
                return
            channel_gaps = {
                key: start_ts - float(start_channels[key][1])
                for key in ("현물", "선물", "프로그램")
            }
            if any(gap > MAX_FLOW_ALIGNMENT_SEC for gap in channel_gaps.values()):
                self.raw["stale_flow_price_only_trigger"] = {
                    "peak_ts": info["peak_ts"], "channel_alignment_sec": channel_gaps,
                    "reason": f"start channel alignment exceeds {MAX_FLOW_ALIGNMENT_SEC}s",
                }
                ep = {
                    "start_ts": info["peak_ts"], "start_price": info["peak"],
                    "low_ts": now_t, "low_price": cur, "sent_drop": abs(float(info["drop"])),
                    "alerted": True, "trigger": info, "price_only": True,
                    "price_only_reason": f"start channel alignment exceeds {MAX_FLOW_ALIGNMENT_SEC}s",
                }
                msg_id = await self._try_send_event("price_only_start", ep, now_t, self.build_alert("start", ep, now_t, cur))
                self.episode = ep
                if msg_id is None:
                    ep.update(alerted=False, start_delivery_status="unconfirmed")
                    self._checkpoint_handoff(force=True)
                    return
                ep["sent_drop"] = self._approved_drop(msg_id, ep["sent_drop"])
                self.msg_ids.append(msg_id)
                self._record_delivery("price_only_start", msg_id, self.episode, now_t)
                return

            ep = {"start_ts": info["peak_ts"], "start_price": info["peak"],
                            "low_ts": now_t, "low_price": cur, "sent_drop": abs(float(info["drop"])),
                            "alerted": True, "trigger": info}
            msg_id = await self._try_send_event("start", ep, now_t, self.build_alert("start", ep, now_t, cur))
            self.episode = ep
            if msg_id is None:
                ep.update(alerted=False, start_delivery_status="unconfirmed")
                self._checkpoint_handoff(force=True)
                return
            ep["sent_drop"] = self._approved_drop(msg_id, ep["sent_drop"])
            self.msg_ids.append(msg_id)
            self._record_delivery("start", msg_id, self.episode, now_t)
            return
        ep = self.episode
        if cur < float(ep["low_price"]):
            ep["low_price"] = cur; ep["low_ts"] = now_t
        total_drop = abs(pct(float(ep["start_price"]), cur) or 0.0)
        if total_drop >= float(ep.get("sent_drop", 0.0)) + 0.50:
            msg_id = await self._try_send_event("expand", ep, now_t, self.build_alert("expand", ep, now_t, cur))
            if msg_id is not None:
                ep["sent_drop"] = self._approved_drop(msg_id, total_drop)
                self.msg_ids.append(msg_id)
                self._record_delivery("expand", msg_id, ep, now_t)
        low_age = now_t - float(ep["low_ts"])
        full_drop = abs(pct(float(ep["start_price"]), float(ep["low_price"])) or 0.0)
        rebound = pct(float(ep["low_price"]), cur) or 0.0
        need_rebound = max(0.30, min(0.70, full_drop * 0.30))
        recovery_ratio = 0.0
        if float(ep["start_price"]) > float(ep["low_price"]):
            recovery_ratio = (cur - float(ep["low_price"])) / (float(ep["start_price"]) - float(ep["low_price"]))
        ended = ((low_age >= NEW_LOW_CONFIRM_SEC and rebound >= need_rebound) or
                 (low_age >= 120 and recovery_ratio >= 0.45) or
                 (now_t - float(ep["start_ts"]) >= MAX_EPISODE_SEC and low_age >= 600))
        if ended:
            final_att = self.attribution(float(ep["start_ts"]), float(ep["low_ts"]))
            msg_id = await self._try_send_event("end", ep, now_t, self.build_end(ep, now_t, cur))
            if msg_id is None:
                ep["end_delivery_status"] = "unconfirmed"
            self._remember_completed_episode("KOSPI", ep, final_att, now_t)
            # Incident tracking may finish even when its Telegram receipt is
            # held. Preserve the uncertainty without blocking the next incident.
            self.episode = None
            self.last_episode_end_ts = now_t
            if msg_id is None:
                self._checkpoint_handoff(force=True)
                return
            self.msg_ids.append(msg_id)
            self._record_delivery("end", msg_id, ep, now_t)
            ep_copy = json.loads(json.dumps(ep))
            task = asyncio.create_task(self._run_enrichment(ep_copy, final_att))
            self.enrichment_tasks.add(task)
            task.add_done_callback(self.enrichment_tasks.discard)

    def _checkpoint_handoff(self, force: bool = False) -> None:
        if not self.handoff_path:
            return
        now = time.time()
        if not force and now - self.last_handoff_save_ts < 30:
            return
        self.save_handoff(self.handoff_path)
        self.last_handoff_save_ts = now

    def _event_context(self, stage: str, ep: dict[str, Any], observed_ts: float) -> dict[str, Any]:
        market = str(ep.get("market") or ("KOSDAQ" if stage.startswith("kosdaq") else "KOSPI"))
        series = getattr(self, "kosdaq_idx" if market == "KOSDAQ" else "idx", [])
        current_price = series[-1][1] if series else None
        context = {
            "market": market, "stage": stage, "actor": str(ep.get("actor") or ""),
            "event_start_ts": ep.get("start_ts"), "event_low_ts": ep.get("low_ts"),
            "observed_ts": observed_ts,
            "observed_drop": abs(pct(ep.get("start_price"), current_price) or 0.0),
        }
        if stage in {"expand", "kosdaq_shock_expand"}:
            context["expansion_from"] = ep.get("sent_drop", 0.0)
        return context

    async def _send_event(self, stage: str, ep: dict[str, Any], observed_ts: float,
                          text: str) -> int:
        with delivery_context(**self._event_context(stage, ep, observed_ts)):
            return await asyncio.to_thread(telegram_send, text)

    async def _try_send_event(self, stage: str, ep: dict[str, Any], observed_ts: float,
                              text: str) -> int | None:
        """Hold an ambiguous incident without terminating the market observer.

        The sender's durable journal remains authoritative. A held incident is
        never retried here and never receives a synthetic approval/message ID.
        """
        context = self._event_context(stage, ep, observed_ts)
        identity = {k: context.get(k) for k in
                    ("market", "stage", "actor", "event_start_ts", "expansion_from")}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        holds = self.raw.setdefault("delivery_holds", {})
        if key in holds:
            return None
        try:
            return await self._send_event(stage, ep, observed_ts, text)
        except DeliveryUncertain as exc:
            holds[key] = {"status": "unconfirmed", "context": identity,
                          "held_at_ts": time.time(), "observed_ts": observed_ts,
                          "error": str(exc), "message_id": None}
            print("market_alert_delivery_held=" + json.dumps(holds[key], ensure_ascii=False), flush=True)
            self._checkpoint_handoff(force=True)
            return None

    def _surge_delivery_hold_at(self, market: str, actor: str, stage: str | None = None) -> float:
        stages = {stage} if stage else {"flow_surge", "kosdaq_flow_surge"}
        return max((float(row.get("held_at_ts") or 0) for row in
                    self.raw.get("delivery_holds", {}).values()
                    if row.get("context", {}).get("market") == market
                    and row.get("context", {}).get("actor") == actor
                    and row.get("context", {}).get("stage") in stages),
                   default=0.0)

    @staticmethod
    def _approved_drop(message_id: int, fallback: float) -> float:
        # A persisted approval may be reused after a checkpoint failure. Advance
        # only to the drawdown in that actual message, not a later unseen tick.
        receipt = receipt_for(message_id) or {}
        value = (receipt.get("context") or {}).get("observed_drop")
        return float(value) if value is not None else fallback

    def _record_delivery(self, stage: str, message_id: int, ep: dict[str, Any],
                         observed_ts: float, evidence: dict[str, Any] | None = None) -> None:
        DELIVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "logged_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "stage": stage,
            "message_id": message_id,
            "market": str(ep.get("market") or "KOSPI"),
            "actor": str(ep.get("actor") or ""),
            "event_start_ts": ep.get("start_ts"),
            "event_start_kst": fmt_clock(ep.get("start_ts")),
            "event_low_ts": ep.get("low_ts"),
            "event_low_kst": fmt_clock(ep.get("low_ts")),
            "observed_ts": observed_ts,
            "observed_kst": fmt_clock(observed_ts),
        }
        rendered = getattr(self, "_kosdaq_render_evidence", None)
        if (evidence is None and record["market"] == "KOSDAQ" and isinstance(rendered, dict)
                and rendered.get("stage") == stage
                and rendered.get("event_start_ts") == ep.get("start_ts")
                and rendered.get("event_low_ts") == ep.get("low_ts")):
            evidence = rendered
        if evidence is not None:
            record["evidence"] = evidence
        receipt = receipt_for(message_id)
        if receipt and (receipt.get("context") or {}).get("stage") == stage:
            record["delivery_receipt"] = {k: v for k, v in receipt.items() if k != "request_html"}
            record["request_body_sha256"] = receipt["request_body_sha256"]
            record["recipient_sha256"] = receipt["returned_recipient_sha256"]
            actual = receipt.get("context") or {}
            for name in ("event_start_ts", "event_low_ts", "observed_ts"):
                record[name] = actual.get(name)
            record["event_start_kst"] = fmt_clock(record["event_start_ts"])
            record["event_low_kst"] = fmt_clock(record["event_low_ts"])
            record["observed_kst"] = fmt_clock(record["observed_ts"])
            if DELIVERY_LOG.exists():
                for line in DELIVERY_LOG.read_text(encoding="utf-8").splitlines():
                    previous = json.loads(line)
                    if previous.get("message_id") == message_id:
                        prior_key = (previous.get("delivery_receipt") or {}).get("delivery_key")
                        if prior_key != receipt.get("delivery_key"):
                            raise RuntimeError("Conflicting market delivery receipt for the same message_id")
                        self._checkpoint_handoff(force=True)
                        return
        with DELIVERY_LOG.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._checkpoint_handoff(force=True)

    def _log_market_health(self) -> None:
        now = time.time()
        if getattr(self, "test", False) or now - getattr(self, "_last_health_log", 0.0) < 60:
            return
        self._last_health_log = now
        def age(value):
            return round(now - value, 1) if value is not None else None
        state = {
            "observed_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "kospi_price_age_sec": age(getattr(self, "last_idx_tick_ts", None)),
            "kospi_futures_price_age_sec": age(getattr(self, "last_fut_tick_ts", None)),
            "kospi_flow_success_age_sec": age(getattr(self, "last_flow_success_ts", None)),
            "kosdaq_price_age_sec": age(self.kosdaq_idx[-1][0] if self.kosdaq_idx else None),
            "kospi_episode_active": self.episode is not None,
            "kosdaq_episode_active": self.kosdaq_episode is not None,
            "delivery_holds": len(self.raw.get("delivery_holds", {})),
        }
        print("market_watch_health=" + json.dumps(state, ensure_ascii=False), flush=True)

    def save_handoff(self, path: str | Path | None) -> None:
        if not path:
            return
        p = Path(path)
        cutoff = time.time() - 60 * 60
        payload = {
            "date": dt.datetime.now(KST).strftime("%Y-%m-%d"),
            "saved_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "flows": [x for x in self.flows if float(x.get("ts", 0)) >= cutoff],
            "episode": self.episode,
            "last_episode_end_ts": self.last_episode_end_ts,
            "opening_gap_sent": self.opening_gap_sent,
            "msg_ids": self.msg_ids[-20:],
            "enrichment_msg_ids": self.enrichment_msg_ids[-20:],
            "surge_last_processed_ts": self.surge_last_processed_ts,
            "surge_pending": self.surge_pending,
            "surge_sent_at": self.surge_sent_at,
            "kosdaq_flows": [x for x in self.kosdaq_flows if float(x.get("ts",0)) >= cutoff],
            "kosdaq_surge_last_processed_ts": self.kosdaq_surge_last_processed_ts,
            "kosdaq_surge_pending": self.kosdaq_surge_pending,
            "kosdaq_surge_sent_at": self.kosdaq_surge_sent_at,
            "kosdaq_prealert_last_processed_ts": self.kosdaq_prealert_last_processed_ts,
            "kosdaq_prealert_pending": self.kosdaq_prealert_pending,
            "kosdaq_prealert_sent_at": self.kosdaq_prealert_sent_at,
            "kosdaq_idx": [[ts,v] for ts,v in self.kosdaq_idx
                           if ts >= time.time()-PRICE_LOOKBACK_SEC][-4000:],
            "kosdaq_episode": self.kosdaq_episode,
            "kosdaq_last_episode_end_ts": self.kosdaq_last_episode_end_ts,
            "kosdaq_regular_price_ready": self.kosdaq_regular_price_ready,
            "kosdaq_opening_gap_sent": self.kosdaq_opening_gap_sent,
            "kosdaq_last_price_processed_ts": self.kosdaq_last_price_processed_ts,
            "kosdaq_last_price_snapshot": self.kosdaq_last_price_snapshot,
            "daily_close": getattr(self, "daily_close", {}),
            "delivery_holds": self.raw.get("delivery_holds", {}),
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        # 인계 파일을 직접 덮어쓰다 중단되면 손상된 JSON이 다음 작업에 넘어갈 수 있다.
        temp = p.with_name(p.name + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(p)
        self.raw["handoff_saved"] = {
            "path": str(p), "flow_count": len(payload["flows"]),
            "episode_active": bool(self.episode),
        }

    def load_handoff(self, path: str | Path | None) -> None:
        if not path:
            return
        p = Path(path)
        if not p.exists():
            self.raw["handoff_loaded"] = {"path": str(p), "status": "missing"}
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            today = dt.datetime.now(KST).strftime("%Y-%m-%d")
            if str(data.get("date") or "") != today:
                self.raw["handoff_loaded"] = {"path": str(p), "status": "stale_date"}
                return
            holds = data.get("delivery_holds")
            if isinstance(holds, dict):
                self.raw["delivery_holds"] = {
                    key: row for key, row in holds.items()
                    if isinstance(row, dict) and row.get("status") == "unconfirmed"
                    and isinstance(row.get("context"), dict)
                    and fnum(row.get("held_at_ts")) is not None
                }
            daily_close = data.get("daily_close")
            if isinstance(daily_close, dict) and daily_close.get("date") == today:
                self.daily_close = daily_close
            loaded = 0
            cutoff = time.time() - FLOW_LOOKBACK_SEC
            for snap in data.get("flows") or []:
                if not isinstance(snap, dict):
                    continue
                if float(snap.get("ts", 0)) < cutoff:
                    continue
                self.flows.append(snap)
                loaded += 1
            ep = data.get("episode")
            if isinstance(ep, dict) and ep.get("start_ts") and ep.get("start_price"):
                self.episode = ep
            self.last_episode_end_ts = fnum(data.get("last_episode_end_ts"))
            self.opening_gap_sent = bool(data.get("opening_gap_sent", False))
            self.msg_ids.extend(int(x) for x in (data.get("msg_ids") or []) if str(x).isdigit())
            self.enrichment_msg_ids.extend(int(x) for x in (data.get("enrichment_msg_ids") or []) if str(x).isdigit())
            self.surge_last_processed_ts = fnum(data.get("surge_last_processed_ts")) or 0.0
            self.surge_sent_at = {
                str(k): float(v) for k, v in (data.get("surge_sent_at") or {}).items()
                if str(k) in ALERT_ACTORS and fnum(v) is not None
            }
            self.surge_pending = {
                str(k): {"sample_ts": float(v["sample_ts"]), "seen_at": float(v["seen_at"]),
                         **({"end_value": float(v["end_value"])} if fnum(v.get("end_value")) is not None else {}),
                         "end_values": {str(channel): float(value) for channel, value in
                                        (v.get("end_values") if isinstance(v.get("end_values"), dict) else {}).items()
                                        if channel in {"spot", "futures"} and fnum(value) is not None}}
                for k, v in (data.get("surge_pending") or {}).items()
                if str(k) in ALERT_ACTORS and isinstance(v, dict)
                and fnum(v.get("sample_ts")) is not None and fnum(v.get("seen_at")) is not None
            }
            # 기존 KOSPI handoff 형식도 정상 복원하고 코스닥은 독립 보관한다.
            for snap in data.get("kosdaq_flows") or []:
                if isinstance(snap, dict) and isinstance(snap.get("현물"), dict) and float(snap.get("ts",0)) >= cutoff:
                    self.kosdaq_flows.append(snap)
            self.kosdaq_surge_last_processed_ts = fnum(data.get("kosdaq_surge_last_processed_ts")) or 0.0
            self.kosdaq_surge_sent_at = {
                str(k): float(v) for k,v in (data.get("kosdaq_surge_sent_at") or {}).items()
                if str(k) in KOSDAQ_SURGE_ACTORS and fnum(v) is not None
            }
            self.kosdaq_surge_pending = {
                str(k): {"sample_ts": float(v["sample_ts"]), "seen_at": float(v["seen_at"]),
                         "end_value": float(v["end_value"]),
                         "end_values": {"spot": float(v["end_value"])}}
                for k,v in (data.get("kosdaq_surge_pending") or {}).items()
                if str(k) in KOSDAQ_SURGE_ACTORS and isinstance(v,dict)
                and fnum(v.get("sample_ts")) is not None and fnum(v.get("seen_at")) is not None
                and fnum(v.get("end_value")) is not None
            }
            self.kosdaq_prealert_last_processed_ts = fnum(data.get("kosdaq_prealert_last_processed_ts")) or 0.0
            self.kosdaq_prealert_sent_at = {
                str(k): float(v) for k,v in (data.get("kosdaq_prealert_sent_at") or {}).items()
                if str(k) in KOSDAQ_SURGE_ACTORS and fnum(v) is not None
            }
            self.kosdaq_prealert_pending = {
                str(k): {"sample_ts": float(v["sample_ts"]), "seen_at": float(v["seen_at"]),
                         "end_value": float(v["end_value"]),
                         "end_values": {"spot": float(v["end_value"])} }
                for k,v in (data.get("kosdaq_prealert_pending") or {}).items()
                if str(k) in KOSDAQ_SURGE_ACTORS and isinstance(v,dict)
                and fnum(v.get("sample_ts")) is not None and fnum(v.get("seen_at")) is not None
                and fnum(v.get("end_value")) is not None
            }
            if self.kosdaq_flows:
                self.kosdaq_last_success_ts = fnum((self.kosdaq_flows[-1].get("현물") or {}).get("sample_ts"))
            # 코스닥 가격 사건과 현물 수급 인계는 기존 KOSPI 사건과 완전히 분리한다.
            price_cutoff=time.time()-PRICE_LOOKBACK_SEC
            for row in data.get("kosdaq_idx") or []:
                if not isinstance(row,(list,tuple)) or len(row)!=2:
                    continue
                ts,v=fnum(row[0]),fnum(row[1])
                if ts is not None and v is not None and v>0 and ts>=price_cutoff:
                    self.kosdaq_idx.append((ts,v))
            if self.kosdaq_idx:
                self.kosdaq_idx=deque(sorted(self.kosdaq_idx),maxlen=30000)
                self.kosdaq_last_idx_tick_ts=self.kosdaq_idx[-1][0]
            raw_ep=data.get("kosdaq_episode")
            if isinstance(raw_ep,dict) and fnum(raw_ep.get("start_ts")) is not None and fnum(raw_ep.get("start_price")):
                self.kosdaq_episode=raw_ep
            self.kosdaq_last_episode_end_ts=fnum(data.get("kosdaq_last_episode_end_ts"))
            self.kosdaq_regular_price_ready=bool(data.get("kosdaq_regular_price_ready",False))
            self.kosdaq_opening_gap_sent=bool(data.get("kosdaq_opening_gap_sent",False))
            self.kosdaq_last_price_processed_ts=fnum(data.get("kosdaq_last_price_processed_ts")) or 0.0
            cached_quote=data.get("kosdaq_last_price_snapshot")
            if isinstance(cached_quote,dict):
                self.kosdaq_last_price_snapshot=cached_quote
            if self.flows:
                latest_snap = max(self.flows, key=lambda x: float(x.get("ts", 0)))
                latest = float(latest_snap.get("ts", 0))
                healthy, issues = flow_snapshot_health(latest_snap)
                if healthy and time.time() - latest <= 180:
                    self.last_flow_success_ts = latest
                elif issues:
                    self.raw["handoff_flow_health_issue"] = issues
            self.raw["handoff_loaded"] = {
                "path": str(p), "status": "ok", "flow_count": loaded,
                "episode_active": bool(self.episode),
            }
        except Exception as exc:
            self.raw["handoff_loaded"] = {
                "path": str(p), "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

    def seed_backfill(self) -> None:
        try:
            rows = backfill_index_bars(self.token)
            cutoff = time.time() - PRICE_LOOKBACK_SEC
            for ts, price in rows:
                if ts >= cutoff:
                    self.idx.append((ts, price))
            self.raw["backfill_rows"] = len(rows)
        except Exception as exc:
            self.raw["backfill_error"] = f"{type(exc).__name__}: {exc}"

    def poll_market_once(self) -> None:
        idx = fetch_index_quote(self.token)
        # 실제 수신 시각을 지수 가격 시각으로 사용한다. 호출 시작시각을 소급 사용하지 않는다.
        idx_received_ts = time.time()
        fut = fetch_derivative_quote(self.token, self.front_future)
        fut_received_ts = time.time()

        current_price = float(idx["price"])
        opening = fnum(idx.get("open"))
        previous_close = fnum(idx.get("prev_close"))
        open_ts = getattr(self, "session_open_ts", None)
        price_usable = True
        price_block_reason = None
        if open_ts is not None and idx_received_ts < open_ts:
            price_usable = False
            price_block_reason = "정규장 개장 전 전일종가 유지값"
        elif open_ts is not None and not getattr(self, "regular_price_ready", False):
            if opening is None or opening <= 0:
                price_usable = False
                price_block_reason = "개장 시가 미확인"
            elif (
                previous_close is not None and previous_close > 0
                and abs((opening / previous_close - 1.0) * 100.0) >= 0.5
                and abs((current_price / previous_close - 1.0) * 100.0) <= 0.01
            ):
                price_usable = False
                price_block_reason = "시가 갭과 다른 전일종가 유지값 — 가짜 장중 급락 차단"

        if price_usable:
            self.idx.append((idx_received_ts, current_price))
            self.regular_price_ready = True
            self.last_idx_tick_ts = idx_received_ts
        else:
            self.raw["last_unconfirmed_price"] = {
                "received_at_kst": fmt_clock(idx_received_ts),
                "reason": price_block_reason,
                "price": current_price, "open": opening,
                "prev_close": previous_close,
            }

        self.fut.append((fut_received_ts, float(fut["price"])))
        self.last_fut_tick_ts = fut_received_ts
        cutoff = fut_received_ts - PRICE_LOOKBACK_SEC
        while self.idx and self.idx[0][0] < cutoff:
            self.idx.popleft()
        while self.fut and self.fut[0][0] < cutoff:
            self.fut.popleft()

        snap = {
            "ts": idx_received_ts,
            "KOSPI": {k: idx.get(k) for k in ("price","prev_close","day_pct","open_pct","open_time","high","low","open","high_time","low_time")},
            "선물": {k: fut.get(k) for k in ("price","kpi200","basis","market_basis","time")},
            "regular_price_usable": price_usable,
            "index_received_ts": idx_received_ts,
            "futures_received_ts": fut_received_ts,
        }
        self.raw["last_price_snapshot"] = snap

        # 옵션 조회는 별도 경로에서 처리한다.


    async def run(self, until: dt.time, test_seconds: int | None = None) -> None:
        self.seed_backfill()
        self.kosdaq_backfill_task=asyncio.create_task(self.seed_kosdaq_backfill())
        started = time.time()
        last_poll_error: str | None = None

        initial_now = dt.datetime.now(KST)
        session = session_state(initial_now)
        self.raw["krx_session"] = {
            "is_session": session["is_session"],
            "date": session["date"],
            "open": session["open"].isoformat() if session["open"] else None,
            "continuous_end": session["continuous_end"].isoformat() if session["continuous_end"] else None,
            "close": session["close"].isoformat() if session["close"] else None,
        }
        if test_seconds is None and not session["is_session"]:
            self.raw["market_closed_reason"] = "XKRX non-session day"
            return

        open_dt = session["open"]
        close_dt = session["close"]
        self.session_open_ts = open_dt.timestamp() if open_dt is not None else None
        self.session_close_ts = close_dt.timestamp() if close_dt is not None else None
        self.session_continuous_end_ts = (
            session["continuous_end"].timestamp()
            if session.get("continuous_end") is not None else self.session_close_ts
        )
        poll_start_dt = (
            open_dt - dt.timedelta(seconds=90)
            if open_dt is not None else initial_now
        )
        effective_end_dt = (
            min(
                dt.datetime.combine(initial_now.date(), until, tzinfo=KST),
                close_dt + dt.timedelta(minutes=2),
            )
            if test_seconds is None and close_dt is not None
            else None
        )

        while True:
            now = dt.datetime.now(KST)
            if test_seconds is not None and time.time() - started >= test_seconds:
                break
            if test_seconds is None and effective_end_dt is not None and now >= effective_end_dt:
                break
            if test_seconds is None and now < poll_start_dt:
                await asyncio.sleep(min(5.0, max(0.5, (poll_start_dt - now).total_seconds())))
                continue

            price_poll_ok = False
            try:
                await asyncio.to_thread(self.poll_market_once)
                price_poll_ok = True
                last_poll_error = None
                if self.raw.pop("last_price_poll_error", None):
                    self.raw["last_price_poll_recovered_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
            except Exception as exc:
                last_poll_error = f"{type(exc).__name__}: {exc}"
                self.raw["last_price_poll_error"] = last_poll_error
                self.raw["price_poll_failures_total"] = int(self.raw.get("price_poll_failures_total", 0)) + 1

            # 현재가 조회 실패 시 이전 가격으로 신규 급락 사건을 판정하지 않는다.
            # 기존 마지막 틱은 상태 표시용으로만 유지하고, 새 가격이 들어왔을 때 평가를 재개한다.
            if price_poll_ok:
                await self.evaluate()
            else:
                # 가격 API 일시 장애 중에도 독립 수급 감지는 계속 수행한다.
                await self.maybe_flow()
                await self.maybe_kosdaq_flow()
                await self.maybe_kosdaq_price()
                await self.maybe_alert_flow_surge()
                await self.maybe_alert_kosdaq_prealert()
                await self.maybe_alert_kosdaq_surge()
                await self.maybe_alert_kosdaq_drop()
                self.raw["price_event_skipped_on_poll_failure"] = True
            self._checkpoint_handoff()

            # XKRX 실제 세션 기준으로만 stale 검사를 적용한다.
            if (
                test_seconds is None
                and open_dt is not None and close_dt is not None
                and open_dt + dt.timedelta(minutes=2) <= now < close_dt + dt.timedelta(minutes=1)
                and time.time() - started >= 60
            ):
                now_ts = time.time()
                if self.last_idx_tick_ts is None or now_ts - self.last_idx_tick_ts > 90:
                    raise RuntimeError(f"KOSPI REST price stale >90s; last_error={last_poll_error}")
                if self.last_fut_tick_ts is None or now_ts - self.last_fut_tick_ts > 90:
                    raise RuntimeError(f"KOSPI200 futures REST price stale >90s; last_error={last_poll_error}")
                # 거래소 연속매매가 끝난 뒤의 동시호가에서는 투자자 수급 원자료가
                # 정지할 수 있다. 가격은 계속 감시하되 수급 stale로 전체 작업을
                # 불필요하게 재기동하지 않는다.
                if continuous_flow_guard_active(now, session):
                    if self.last_flow_success_ts is None or now_ts - self.last_flow_success_ts > 180:
                        raise RuntimeError("LS spot/futures/program flow snapshot stale >180s")

            self._log_market_health()
            await asyncio.sleep(0.6)

        await self._finalize_daily_close(close_dt, test_seconds)

        if self.kosdaq_price_task:
            try:
                await asyncio.wait_for(self.kosdaq_price_task, timeout=10)
            except Exception:
                pass
        if self.kosdaq_backfill_task:
            try:
                await asyncio.wait_for(self.kosdaq_backfill_task, timeout=10)
            except Exception:
                pass

        if self.flow_task:
            try:
                await asyncio.wait_for(self.flow_task, timeout=8)
            except Exception:
                pass
        if self.kosdaq_flow_task:
            try:
                await asyncio.wait_for(self.kosdaq_flow_task, timeout=8)
            except Exception:
                pass
        if self.enrichment_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*list(self.enrichment_tasks), return_exceptions=True),
                    timeout=180,
                )
            except Exception as exc:
                self.raw["enrichment_shutdown_error"] = f"{type(exc).__name__}: {exc}"


def write_status(w: Watch, started: dt.datetime, status: str) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text("\n".join([
        "# 코스피 급락 사건구간 감시", "",
        f"- 시작: {started:%Y-%m-%d %H:%M:%S} KST", f"- 상태: {status}",
        f"- KOSPI 틱: {len(w.idx)}", f"- 선물 틱: {len(w.fut)}", f"- 수급 스냅샷: {len(w.flows)}",
        f"- 코스닥 현물 수급 스냅샷: {len(w.kosdaq_flows)}",
        f"- 코스닥 가격 틱: {len(w.kosdaq_idx)}",
        f"- 코스닥 급락 진행 중: {'있음' if w.kosdaq_episode else '없음'}",
        f"- 코스닥 가격 최근 오류: {w.raw.get('last_kosdaq_price_error') or '없음'}",
        f"- 최근월물 선물: {w.front_future or '미확인'}", f"- 구독 풋옵션: {len(w.put_defs)}",
        f"- 진행 중 사건: {'있음' if w.episode else '없음'}", f"- 텔레그램 ID: {w.msg_ids}",
        f"- 정밀분해 텔레그램 ID: {w.enrichment_msg_ids}",
    ]) + "\n", encoding="utf-8")
    RAW.write_text(json.dumps(w.raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def synthetic_test() -> int:
    base = time.time() - 60 * 70
    prices = []
    for i in range(15): prices.append((base+i*60, 7170 + i*0.1))
    for i in range(1, 48): prices.append((base+(15+i)*60, 7171.4 - i*2.7))
    for i in range(1, 9): prices.append((base+(62+i)*60, 7044.5 + i*5.0))
    class Dummy: pass
    d = Dummy(); d.idx = deque(prices, maxlen=30000)
    d._nearest = Watch._nearest; d._ret = Watch._ret.__get__(d, Dummy); d._recent_peak = Watch._recent_peak.__get__(d, Dummy); d._window_peak = Watch._window_peak.__get__(d, Dummy)
    hit, info = Watch._trigger(d)
    print(json.dumps({"hit": hit, "start": fmt_clock(info.get("peak_ts")), "drop": info.get("drop"), "duration_min": (info.get("duration") or 0)/60}, ensure_ascii=False))
    return 0 if hit else 1


async def amain(
    test: bool,
    seconds: int,
    until: dt.time,
    handoff_in: str | None = None,
    handoff_out: str | None = None,
) -> int:
    key=(os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    secret=(os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not key or not secret:
        raise RuntimeError("LS secrets missing")

    token = await asyncio.to_thread(get_token)
    front = await asyncio.to_thread(get_front_future, token)
    fq = await asyncio.to_thread(fetch_derivative_quote, token, front)
    current200 = fnum(fq.get("kpi200"))
    puts = await asyncio.to_thread(get_weekly_puts, token, current200)

    w = Watch(token, puts, front, test)
    w.handoff_path = handoff_out
    w.load_handoff(handoff_in)
    started = dt.datetime.now(KST)
    try:
        await w.run(until, seconds if test else None)
        w.save_handoff(handoff_out)
        write_status(w, started, "정상 종료")
        return 0
    except Exception as exc:
        # 장애 복구 작업이 사건 시작점·최근 수급을 이어받을 수 있도록
        # 오류 종료에서도 반드시 handoff를 남긴다.
        try:
            w.save_handoff(handoff_out)
        except Exception as handoff_exc:
            w.raw["handoff_save_error"] = f"{type(handoff_exc).__name__}: {handoff_exc}"
        write_status(w, started, f"오류: {type(exc).__name__}: {exc}")
        raise

def parse_hhmm(s: str) -> dt.time:
    h, m = map(int, s.split(":")); return dt.time(h, m)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--test", action="store_true"); ap.add_argument("--test-seconds", type=int, default=12)
    ap.add_argument("--synthetic-test", action="store_true"); ap.add_argument("--until", default="15:32")
    ap.add_argument("--handoff-in"); ap.add_argument("--handoff-out")
    args = ap.parse_args()
    if args.synthetic_test: return synthetic_test()
    return asyncio.run(
        amain(args.test, args.test_seconds, parse_hhmm(args.until), args.handoff_in, args.handoff_out)
    )

if __name__ == "__main__": raise SystemExit(main())

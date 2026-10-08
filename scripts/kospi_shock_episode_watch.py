#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from kospi_shock_enrichment import build_enrichment
from krx_session_calendar import session_state

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


def fnum(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(str(v).replace(",", "").strip())
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
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 4:
        return fallback_ts
    digits = (digits + "000000")[:6]
    try:
        now = dt.datetime.now(KST)
        point = dt.datetime(now.year, now.month, now.day,
                            int(digits[:2]), int(digits[2:4]), int(digits[4:6]),
                            tzinfo=KST)
        ts = point.timestamp()
        # 장중 API 시각이 비정상적으로 미래/과거면 조회시각을 사용한다.
        ref = fallback_ts if fallback_ts is not None else time.time()
        if abs(ts - ref) > 6 * 60 * 60:
            return fallback_ts
        return ts
    except Exception:
        return fallback_ts


def should_finalize_market_close(
    now: dt.datetime,
    actual_close: dt.datetime | None,
    test_seconds: int | None = None,
) -> bool:
    """오전·오후 작업 인계는 장마감이 아니다. 장 종료 시에만 사건을 최종 확정한다."""
    return test_seconds is None and actual_close is not None and now >= actual_close


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
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = ((os.getenv("TELEGRAM_CHAT_ID_PRIMARY") or "").strip()
               or (os.getenv("TELEGRAM_CHAT_ID_FALLBACK") or "").strip())
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("Telegram token/chat id missing")

    actual = ""
    last_error = ""
    for attempt in range(5):
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=20) as r:
                ident = json.loads(r.read().decode("utf-8"))
            actual = str((ident.get("result") or {}).get("username") or "")
            if not ident.get("ok") or (expected and actual.lower() != expected.lower()):
                raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")
            break
        except RuntimeError:
            raise
        except Exception as exc:
            last_error = f"Telegram getMe transport error: {type(exc).__name__}: {exc}"
            if attempt >= 4:
                raise RuntimeError(last_error) from exc
            time.sleep(min(8.0, 1.0 * (2 ** attempt)))

    payload = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    for attempt in range(6):
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read().decode("utf-8"))
            if out.get("ok"):
                message_id = int(out["result"]["message_id"])
                print(
                    f"telegram_delivery_confirmed=true bot=@{actual} message_id={message_id}",
                    flush=True,
                )
                return message_id
            code = int(out.get("error_code") or 0)
            last_error = f"Telegram rejected message: {out}"
            if code == 429 or code >= 500:
                retry_after = fnum(((out.get("parameters") or {}).get("retry_after")))
                time.sleep(min(30.0, retry_after if retry_after is not None else 1.5 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error)
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            last_error = f"Telegram HTTP {exc.code}: {body[:300]}"
            if attempt < 5 and (exc.code == 429 or 500 <= exc.code < 600):
                time.sleep(min(30.0, 1.5 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        except RuntimeError:
            raise
        except Exception as exc:
            last_error = f"Telegram send transport error: {type(exc).__name__}: {exc}"
            if attempt >= 5:
                raise RuntimeError(last_error) from exc
            time.sleep(min(30.0, 1.5 * (2 ** attempt)))
    raise RuntimeError(last_error or "Telegram send failed after retries")


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


def ls_post(token: str, path: str, tr: str, body: dict[str, Any]) -> dict[str, Any]:
    last_error = ""
    for attempt in range(5):
        try:
            r = requests.post(
                BASE + path,
                headers={"content-type": "application/json; charset=utf-8",
                         "authorization": "Bearer " + token, "tr_cd": tr,
                         "tr_cont": "N", "tr_cont_key": ""},
                data=json.dumps(body), timeout=20)
        except requests.RequestException as exc:
            last_error = f"{tr} transport error: {type(exc).__name__}: {exc}"
            if attempt < 4:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        text = r.text or ""
        # LS 게이트웨이가 임시 장애의 /503.html 경로를 HTTP 404로 반환하는
        # 실전 사례가 있다. 진짜 404와 구분해 해당 경로만 재시도한다.
        gateway_503_as_404 = r.status_code == 404 and "/503.html" in text
        retryable_http = r.status_code in {429, 500, 502, 503, 504} or gateway_503_as_404
        if not r.ok:
            last_error = f"{tr} HTTP {r.status_code}: {text[:250]}"
            if attempt < 4 and retryable_http:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error)
        try:
            d = r.json()
            if not isinstance(d, dict):
                raise ValueError("LS response is not a JSON object")
        except (ValueError, TypeError) as exc:
            last_error = f"{tr} invalid JSON: {type(exc).__name__}: {text[:200]}"
            if attempt < 4:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        code = str(d.get("rsp_cd") or "")
        if code and code not in {"00000", "0000"}:
            last_error = f"{tr} rejected {code}: {d.get('rsp_msg')}"
            if attempt < 4 and code in {"IGW00201"}:
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
    for row in rows:
        if not isinstance(row, dict):
            continue
        s = "".join(c for c in str(row.get("time") or "") if c.isdigit())
        if len(s) >= 6:
            valid.append((s[:6], row))
    return max(valid, key=lambda x: x[0])[1] if valid else None


def investor_current(token: str, market: str, upcode: str, exchgubun: str = "K") -> dict[str, Any] | None:
    body = {"t1602InBlock": {"market": market, "upcode": upcode,
            "gubun1": "2", "gubun2": "0", "cts_time": "", "cts_idx": 0,
            "cnt": 100, "gubun3": "", "exchgubun": exchgubun}}
    d = ls_post(token, "/stock/investor", "t1602", body)
    row = _latest_time_row(d.get("t1602OutBlock1"))
    if not row:
        return None
    fetched_ts = time.time()
    return {"time": row.get("time"), "sample_ts": market_clock_epoch(row.get("time"), fetched_ts),
            "개인": fnum(row.get("sv_08")),
            "외국인": fnum(row.get("sv_17")), "기관": fnum(row.get("sv_18"))}


def _program_mini(token: str, gubun: str) -> dict[str, Any] | None:
    # t1640: 11=거래소 전체, 12=거래소 차익, 13=거래소 비차익.
    d = ls_post(token, "/stock/program", "t1640", {"t1640InBlock": {"gubun": gubun, "exchgubun": "U"}})
    row = d.get("t1640OutBlock")
    if not isinstance(row, dict) or not row:
        return None
    out = dict(row)
    out["_fetched_ts"] = time.time()
    return out


def program_current(token: str) -> dict[str, Any] | None:
    # t1632의 '최신 행'을 누적값처럼 차감하지 않는다.
    # t1640 누적 스냅샷 3종을 동일 시점에 조회해 사건 시작→저점 차이를 계산한다.
    total = _program_mini(token, "11")
    time.sleep(1.05)
    arb = _program_mini(token, "12")
    time.sleep(1.05)
    nonarb = _program_mini(token, "13")
    if not total and not arb and not nonarb:
        return None
    total_val = fnum((total or {}).get("value"))
    arb_val = fnum((arb or {}).get("value"))
    nonarb_val = fnum((nonarb or {}).get("value"))
    fetch_times = [fnum((x or {}).get("_fetched_ts")) for x in (total, arb, nonarb)]
    fetch_times = [x for x in fetch_times if x is not None]
    component_sum = (arb_val + nonarb_val) if arb_val is not None and nonarb_val is not None else None
    identity_gap = (total_val - component_sum) if total_val is not None and component_sum is not None else None
    return {
        "time": dt.datetime.now(KST).strftime("%H%M%S"),
        "전체": total_val,
        "차익": arb_val,
        "비차익": nonarb_val,
        "베이시스": fnum((total or {}).get("basis")),
        "전체_순매수증감": fnum((total or {}).get("sunvaldiff") or (total or {}).get("sundiff")),
        "표본시차초": (max(fetch_times) - min(fetch_times)) if len(fetch_times) >= 2 else None,
        "차익비차익합": component_sum,
        "전체대비차이": identity_gap,
        "sample_ts": ((min(fetch_times) + max(fetch_times)) / 2.0) if fetch_times else time.time(),
    }


def fetch_flow_snapshot(token: str) -> dict[str, Any]:
    started_ts = time.time()
    snap: dict[str, Any] = {"ts": started_ts, "ts_start": started_ts, "errors": {}}
    for key, market, upcode, exchgubun in (
        ("현물", "1", "001", "U"),
        ("선물", "4", "900", "K"),
    ):
        try:
            snap[key] = investor_current(token, market, upcode, exchgubun)
        except Exception as exc:
            snap[key] = None
            snap["errors"][key] = f"{type(exc).__name__}: {exc}"
        time.sleep(1.05)
    try:
        snap["프로그램"] = program_current(token)
    except Exception as exc:
        snap["프로그램"] = None
        snap["errors"]["프로그램"] = f"{type(exc).__name__}: {exc}"
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
    for key in ("현물", "선물", "프로그램"):
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


def backfill_index_bars(token: str, max_rows: int = 500) -> list[tuple[float, float]]:
    # 재기동 시 당일 KOSPI 1분봉을 복구해 오전/직전 급락 시작점을 잃지 않는다.
    body = {"t8409InBlock": {
        "shcode": "001", "ncnt": 1, "qrycnt": max_rows, "nday": "1",
        "sdate": " ", "stime": "", "edate": "99999999", "etime": "",
        "cts_date": " ", "cts_time": "", "comp_yn": "N"
    }}
    d = ls_post(token, "/indtp/chart", "t8409", body)
    rows = d.get("t8409OutBlock1") or []
    if isinstance(rows, dict):
        rows = [rows]
    out: list[tuple[float, float]] = []
    today = dt.datetime.now(KST).date()
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
            out.append((when.timestamp(), close))
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    return out



def _actor_delta(start: dict[str, Any] | None, end: dict[str, Any] | None) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for actor in ("외국인", "기관", "개인"):
        a = fnum((start or {}).get(actor)); b = fnum((end or {}).get(actor))
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


class Watch:
    def __init__(self, token: str, puts: list[dict[str, Any]], front_future: str, test: bool):
        self.token = token; self.put_defs = puts; self.test = test
        self.idx: deque[tuple[float, float]] = deque(maxlen=30000)
        self.fut: deque[tuple[float, float]] = deque(maxlen=30000)
        self.puts: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=30000))
        self.flows: deque[dict[str, Any]] = deque(maxlen=2500)
        self.front_future = front_future; self.episode: dict[str, Any] | None = None
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
        self.opening_gap_sent = False
        self.handoff_path: str | None = None
        self.last_handoff_save_ts = 0.0

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
        rows = [x for x in self.idx if x[0] >= cutoff]
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

    def _flow_near(self, ts: float, prefer_before: bool = True) -> dict[str, Any] | None:
        rows = list(self.flows)
        if not rows:
            return None
        if prefer_before:
            prior = [x for x in rows if float(x.get("ts", 0)) <= ts]
            # 사건 시작 이전 스냅샷이 없으면 이후 값을 시작값으로 대체하지 않는다.
            return max(prior, key=lambda x: float(x.get("ts", 0))) if prior else None
        return min(rows, key=lambda x: abs(float(x.get("ts", 0)) - ts))

    def _flow_channel_near(self, ts: float, channel: str) -> tuple[dict[str, Any], float] | None:
        candidates: list[tuple[dict[str, Any], float]] = []
        for snap in self.flows:
            block = snap.get(channel)
            if not isinstance(block, dict):
                continue
            sample_ts = fnum(block.get("sample_ts"))
            if sample_ts is None:
                sample_ts = fnum(snap.get("ts"))
            if sample_ts is None or sample_ts > ts:
                continue
            candidates.append((block, sample_ts))
        return max(candidates, key=lambda x: x[1]) if candidates else None

    def attribution(self, start_ts: float, end_ts: float) -> dict[str, Any]:
        spot_a = self._flow_channel_near(start_ts, "현물")
        spot_b = self._flow_channel_near(end_ts, "현물")
        fut_a = self._flow_channel_near(start_ts, "선물")
        fut_b = self._flow_channel_near(end_ts, "선물")
        pgm_a = self._flow_channel_near(start_ts, "프로그램")
        pgm_b = self._flow_channel_near(end_ts, "프로그램")
        if not spot_a or not spot_b or not fut_a or not fut_b:
            return {"available": False, "reason": "사건 시작 또는 종료 이전 현물·선물 수급 스냅샷 없음"}

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
            sellers = [(actor, val) for actor, val in block.items() if val is not None and float(val) < 0]
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
        return {"available": True, "start_ts": start_ts, "end_ts": end_ts,
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
            lines += [
                "⚠️ <b>감시 공백 또는 수급 기준점 부족</b> — 가격 급락은 확인됐지만",
                "• 사건 시작 이전의 정확한 현물·선물·프로그램 기준점이 없어 매도주체는 소급 추정하지 않습니다.",
                "",
            ]
        lines += ["<b>그 구간에서 누가 팔았나</b>"]
        if att.get("available"):
            s, f, p = att["spot"], att["futures"], att["program"]
            cross = ", ".join(att.get("cross_sellers") or []) or "없음"
            lines += [f"• 현물(통합): 외국인 <b>{fmt_eok(s.get('외국인'))}</b> · 기관 <b>{fmt_eok(s.get('기관'))}</b> · 개인 <b>{fmt_eok(s.get('개인'))}</b>",
                      f"• KOSPI200 선물: 외국인 <b>{fmt_eok(f.get('외국인'))}</b> · 기관 <b>{fmt_eok(f.get('기관'))}</b> · 개인 <b>{fmt_eok(f.get('개인'))}</b>",
                      f"• 현물 최다매도: <b>{html.escape(str(att.get('spot_leader') or '없음'))}</b> {fmt_eok(att.get('spot_leader_value'))}",
                      f"• 선물 최다매도: <b>{html.escape(str(att.get('futures_leader') or '없음'))}</b> {fmt_eok(att.get('futures_leader_value'))}",
                      f"• 양시장 동시매도: <b>{html.escape(cross)}</b>",
                      f"• 프로그램 전체(차익+비차익) <b>{fmt_raw(p.get('전체'))}</b> · 차익 <b>{fmt_raw(p.get('차익'))}</b> · 비차익 <b>{fmt_raw(p.get('비차익'))}</b> <i>(LS t1640 사건구간 변화)</i>",
                      f"• LS 전체 직접값 변화 <b>{fmt_raw(p.get('전체직접'))}</b> · 계산합계와 차이 <b>{fmt_raw(p.get('검산차이'))}</b> ({float(att.get('program_crosscheck_ratio_pct') or 0):.2f}%)",
                      f"• 프로그램 방향: <b>{html.escape(str(att.get('program_kind')))}</b>",
                      f"• 수급 기준점 시차: 시작 <b>{float(att.get('start_alignment_sec') or 0):.1f}초</b> · 종료 <b>{float(att.get('end_alignment_sec') or 0):.1f}초</b> · 프로그램 3종 조회시차 최대 <b>{float(att.get('program_sample_span_sec') or 0):.1f}초</b>",
                      f"• 프로그램 교차검증 품질: <b>{html.escape(program_quality_label(att))}</b>", "",
                      "<b>판정</b>", f"• <b>{html.escape(str(att.get('verdict')))}</b> · 확신도 {html.escape(str(att.get('confidence')))}"]
        else:
            lines += [f"• 주체 판정 보류 — {html.escape(str(att.get('reason') or '수급 스냅샷 부족'))}"]
        opt = self.option_move(float(ep["start_ts"]), end_ts)
        if opt:
            lines += ["", "<b>파생 증폭 확인</b>", f"• 근접 위클리 풋 <b>{html.escape(opt[0])}</b> · 사건 시작 대비 <b>{opt[1]:.1f}배</b>"]
        lines += ["", "<b>읽는 법</b>",
                  "• 하루 누적 수급이 아니라 <b>급락 시작 직전 → 현재</b> 변화량만 비교합니다.",
                  "• 현물·프로그램은 <b>통합 기준</b>, KOSPI200 선물은 파생시장 기준입니다.",
                  "• 현물·선물·프로그램이 같은 방향으로 겹칠 때만 특정 주체를 급락 주도 후보로 올립니다.",
                  "• 프로그램 전체는 차익 변화+비차익 변화로 계산하며, LS 전체 직접값과 방향·수치 차이를 별도 검증합니다. t1640 3종은 순차 조회이고 차이가 1%를 넘으면 높은 확신도로 판정하지 않습니다.", "",
                  "• " + " · ".join([link(KOSPI_URL,"KOSPI"), link(NEWS_URL,"급락 뉴스"), link(LS_URL,"LS OpenAPI")])]
        return "\n".join(lines)

    def build_end(
        self,
        ep: dict[str, Any],
        end_ts: float,
        end_price: float,
        session_close: bool = False,
    ) -> str:
        att = self.attribution(float(ep["start_ts"]), float(ep["low_ts"]))
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
                     f"• 저점 이후 장마감 <b>{end_price:,.2f}</b> · 반등 <b>{rebound:+.2f}%</b>"
                     if session_close else
                     f"• 저점 이후 현재 <b>{end_price:,.2f}</b> · 반등 <b>{rebound:+.2f}%</b>"
                 ), "",
                 "<b>저점까지 실제 매도주체</b>"]
        if att.get("available"):
            s, f, p = att["spot"], att["futures"], att["program"]
            cross = ", ".join(att.get("cross_sellers") or []) or "없음"
            lines += [f"• 현물(통합): 외국인 <b>{fmt_eok(s.get('외국인'))}</b> · 기관 <b>{fmt_eok(s.get('기관'))}</b> · 개인 <b>{fmt_eok(s.get('개인'))}</b>",
                      f"• KOSPI200 선물: 외국인 <b>{fmt_eok(f.get('외국인'))}</b> · 기관 <b>{fmt_eok(f.get('기관'))}</b> · 개인 <b>{fmt_eok(f.get('개인'))}</b>",
                      f"• 현물 최다매도: <b>{html.escape(str(att.get('spot_leader') or '없음'))}</b> {fmt_eok(att.get('spot_leader_value'))}",
                      f"• 선물 최다매도: <b>{html.escape(str(att.get('futures_leader') or '없음'))}</b> {fmt_eok(att.get('futures_leader_value'))}",
                      f"• 양시장 동시매도: <b>{html.escape(cross)}</b>",
                      f"• 프로그램 전체(차익+비차익) <b>{fmt_raw(p.get('전체'))}</b> · 차익 <b>{fmt_raw(p.get('차익'))}</b> · 비차익 <b>{fmt_raw(p.get('비차익'))}</b> <i>(LS t1640 사건구간 변화)</i>",
                      f"• LS 전체 직접값 변화 <b>{fmt_raw(p.get('전체직접'))}</b> · 계산합계와 차이 <b>{fmt_raw(p.get('검산차이'))}</b> ({float(att.get('program_crosscheck_ratio_pct') or 0):.2f}%)",
                      f"• 수급 기준점 시차: 시작 <b>{float(att.get('start_alignment_sec') or 0):.1f}초</b> · 저점 <b>{float(att.get('end_alignment_sec') or 0):.1f}초</b> · 프로그램 3종 조회시차 최대 <b>{float(att.get('program_sample_span_sec') or 0):.1f}초</b>",
                      f"• 프로그램 교차검증 품질: <b>{html.escape(program_quality_label(att))}</b>",
                      f"• 최종 판정: <b>{html.escape(str(att.get('verdict')))}</b> · 확신도 {html.escape(str(att.get('confidence')))}"]
        else:
            lines += [f"• 가격 구간만 확정 — {html.escape(str(att.get('reason') or '수급 스냅샷 부족'))}"]
        if session_close:
            lines += ["", "• <b>장 마감으로 사건 추적을 종료합니다. 복원 여부는 확정하지 않습니다.</b>"]
        lines += ["", "• 현물·프로그램은 <b>통합 기준</b>, KOSPI200 선물은 파생시장 기준",
                  "• " + " · ".join([link(KOSPI_URL,"KOSPI"), link(NEWS_URL,"관련 뉴스")])]
        return "\n".join(lines)

    async def _run_enrichment(self, ep: dict[str, Any], att: dict[str, Any]) -> None:
        async with self.enrichment_sem:
            try:
                text, detail = await asyncio.to_thread(
                    build_enrichment, self.token, ep, att
                )
                msg_id = await asyncio.to_thread(telegram_send, text)
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
                print(f"kospi_enrichment_error={type(exc).__name__}: {exc}", flush=True)

    async def maybe_flow(self) -> None:
        now = time.time()
        if self.flow_task and not self.flow_task.done():
            return
        if now - self.last_flow_poll < FLOW_INTERVAL_SEC:
            return
        self.last_flow_poll = now
        async def run_one():
            try:
                snap = await asyncio.to_thread(fetch_flow_snapshot, self.token)
                self.flows.append(snap)
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

    async def evaluate(self) -> None:
        await self.maybe_flow()
        if not self.idx:
            return
        now_t, cur = self.idx[-1]

        if (
            not self.opening_gap_sent
            and self.session_open_ts is not None
            and self.session_open_ts <= now_t <= self.session_open_ts + 15 * 60
        ):
            snap = self.raw.get("last_price_snapshot") or {}
            opct = fnum((snap.get("KOSPI") or {}).get("open_pct"))
            if opct is not None and opct <= OPEN_GAP_ALERT_PCT:
                msg_id = await asyncio.to_thread(telegram_send, self.build_open_gap_alert(snap))
                self.msg_ids.append(msg_id)
                self.opening_gap_sent = True
                self.raw["opening_gap_alert"] = {
                    "message_id": msg_id, "open_pct": opct,
                    "sent_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
                }
                # 개장 경보는 일반 사건 _record_delivery 경로를 거치지 않으므로 즉시 인계한다.
                self._checkpoint_handoff(force=True)
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
                self.episode = {
                    "start_ts": info["peak_ts"], "start_price": info["peak"],
                    "low_ts": now_t, "low_price": cur, "sent_drop": abs(float(info["drop"])),
                    "alerted": True, "trigger": info, "price_only": True,
                    "price_only_reason": "missing channel snapshot at/before event start",
                }
                msg_id = await asyncio.to_thread(
                    telegram_send, self.build_alert("start", self.episode, now_t, cur)
                )
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
                self.episode = {
                    "start_ts": info["peak_ts"], "start_price": info["peak"],
                    "low_ts": now_t, "low_price": cur, "sent_drop": abs(float(info["drop"])),
                    "alerted": True, "trigger": info, "price_only": True,
                    "price_only_reason": f"start channel alignment exceeds {MAX_FLOW_ALIGNMENT_SEC}s",
                }
                msg_id = await asyncio.to_thread(
                    telegram_send, self.build_alert("start", self.episode, now_t, cur)
                )
                self.msg_ids.append(msg_id)
                self._record_delivery("price_only_start", msg_id, self.episode, now_t)
                return

            self.episode = {"start_ts": info["peak_ts"], "start_price": info["peak"],
                            "low_ts": now_t, "low_price": cur, "sent_drop": abs(float(info["drop"])),
                            "alerted": True, "trigger": info}
            msg_id = await asyncio.to_thread(telegram_send, self.build_alert("start", self.episode, now_t, cur))
            self.msg_ids.append(msg_id)
            self._record_delivery("start", msg_id, self.episode, now_t)
            return
        ep = self.episode
        if cur < float(ep["low_price"]):
            ep["low_price"] = cur; ep["low_ts"] = now_t
        total_drop = abs(pct(float(ep["start_price"]), cur) or 0.0)
        if total_drop >= float(ep.get("sent_drop", 0.0)) + 0.50:
            ep["sent_drop"] = total_drop
            msg_id = await asyncio.to_thread(telegram_send, self.build_alert("expand", ep, now_t, cur))
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
            msg_id = await asyncio.to_thread(telegram_send, self.build_end(ep, now_t, cur))
            self.msg_ids.append(msg_id)
            self._record_delivery("end", msg_id, ep, now_t)
            ep_copy = json.loads(json.dumps(ep))
            task = asyncio.create_task(self._run_enrichment(ep_copy, final_att))
            self.enrichment_tasks.add(task)
            task.add_done_callback(self.enrichment_tasks.discard)
            self.episode = None

    def _checkpoint_handoff(self, force: bool = False) -> None:
        if not self.handoff_path:
            return
        now = time.time()
        if not force and now - self.last_handoff_save_ts < 30:
            return
        self.save_handoff(self.handoff_path)
        self.last_handoff_save_ts = now

    def _record_delivery(self, stage: str, message_id: int, ep: dict[str, Any], observed_ts: float) -> None:
        DELIVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "logged_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "stage": stage,
            "message_id": message_id,
            "event_start_ts": ep.get("start_ts"),
            "event_start_kst": fmt_clock(ep.get("start_ts")),
            "event_low_ts": ep.get("low_ts"),
            "event_low_kst": fmt_clock(ep.get("low_ts")),
            "observed_ts": observed_ts,
            "observed_kst": fmt_clock(observed_ts),
        }
        with DELIVERY_LOG.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._checkpoint_handoff(force=True)

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
            "opening_gap_sent": self.opening_gap_sent,
            "msg_ids": self.msg_ids[-20:],
            "enrichment_msg_ids": self.enrichment_msg_ids[-20:],
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            self.opening_gap_sent = bool(data.get("opening_gap_sent", False))
            self.msg_ids.extend(int(x) for x in (data.get("msg_ids") or []) if str(x).isdigit())
            self.enrichment_msg_ids.extend(int(x) for x in (data.get("enrichment_msg_ids") or []) if str(x).isdigit())
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
        now_ts = time.time()
        idx = fetch_index_quote(self.token)
        fut = fetch_derivative_quote(self.token, self.front_future)

        self.idx.append((now_ts, float(idx["price"])))
        self.fut.append((now_ts, float(fut["price"])))
        self.last_idx_tick_ts = now_ts
        self.last_fut_tick_ts = now_ts
        cutoff = now_ts - PRICE_LOOKBACK_SEC
        while self.idx and self.idx[0][0] < cutoff:
            self.idx.popleft()
        while self.fut and self.fut[0][0] < cutoff:
            self.fut.popleft()

        snap = {
            "ts": now_ts,
            "KOSPI": {k: idx.get(k) for k in ("price","prev_close","day_pct","open_pct","open_time","high","low","open","high_time","low_time")},
            "선물": {k: fut.get(k) for k in ("price","kpi200","basis","market_basis","time")},
        }
        self.raw["last_price_snapshot"] = snap

        # 옵션은 핵심 가격/수급 감시와 분리한다.
        # 느린 옵션 조회가 KOSPI·선물 폴링을 지연시키지 않도록 주 루프에서는 조회하지 않는다.


    async def run(self, until: dt.time, test_seconds: int | None = None) -> None:
        self.seed_backfill()
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

            try:
                await asyncio.to_thread(self.poll_market_once)
                last_poll_error = None
                if self.raw.pop("last_price_poll_error", None):
                    self.raw["last_price_poll_recovered_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
            except Exception as exc:
                last_poll_error = f"{type(exc).__name__}: {exc}"
                self.raw["last_price_poll_error"] = last_poll_error
                self.raw["price_poll_failures_total"] = int(self.raw.get("price_poll_failures_total", 0)) + 1

            await self.evaluate()
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
                if self.last_flow_success_ts is None or now_ts - self.last_flow_success_ts > 180:
                    raise RuntimeError("LS spot/futures/program flow snapshot stale >180s")

            await asyncio.sleep(0.6)

        if self.episode is not None and self.idx and should_finalize_market_close(
            dt.datetime.now(KST), close_dt, test_seconds
        ):
            ep = self.episode
            end_ts, end_price = self.idx[-1]
            final_att = self.attribution(float(ep["start_ts"]), float(ep["low_ts"]))
            msg_id = await asyncio.to_thread(
                telegram_send,
                self.build_end(ep, end_ts, end_price, session_close=True),
            )
            self.msg_ids.append(msg_id)
            self._record_delivery("close", msg_id, ep, end_ts)
            ep_copy = json.loads(json.dumps(ep))
            task = asyncio.create_task(self._run_enrichment(ep_copy, final_att))
            self.enrichment_tasks.add(task)
            task.add_done_callback(self.enrichment_tasks.discard)
            self.episode = None

        if self.flow_task:
            try:
                await asyncio.wait_for(self.flow_task, timeout=8)
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

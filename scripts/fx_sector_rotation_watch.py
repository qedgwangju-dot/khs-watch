#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

import korea_market_stress_watch_v11 as v11
import korea_market_stress_watch_v14 as fx_basis
from krx_session_calendar import session_bounds

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "fx_sector_rotation_state.json"
MARKET_STATE_PATH = ROOT / "data" / "korea_market_stress_watch_state.json"
MARKET_PENDING_PATH = ROOT / "out" / "korea_market_stress_pending_state.json"
PENDING_PATH = ROOT / "out" / "fx_sector_rotation_pending_state.json"
ALERT_PATH = ROOT / "out" / "fx_sector_rotation_alert.html"
STATUS_PATH = ROOT / "out" / "fx_sector_rotation_status.md"

FX_URL = "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=5"
KOSPI_URL = "https://m.stock.naver.com/api/index/KOSPI/basic"
KOSPI_DAILY_URL = "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=5&page=1"
KIWOOM_CLOSE_DOC = "https://openapi.kiwoom.com/m/guide/apiguide/07/ka11081"
LS_CLOSE_DOC = "https://openapi.ls-sec.co.kr/"
LS_CLOSE_BASIS = "LS증권 KRX 15:30 정규장 봉·종가 교차검증"
_CLOSE_SOURCES = {KIWOOM_CLOSE_DOC: "키움 KRX 정규장 일봉", LS_CLOSE_DOC: LS_CLOSE_BASIS}
_LS_CLOSE_TOKEN = None
_LS_CLOSE_DISABLED = False
_LS_CLOSE_NEXT = 0.0
_LS_CLOSE_FAILURES = 0
CLOSE_SETTLE_MINUTES = 5
_CLOSE_TOKEN = None
_CLOSE_DISABLED = False
_CLOSE_NEXT = 0.0


class SourceFailure(RuntimeError):
    """Safe diagnostic: never include provider response bodies or credentials."""


def _failure_detail(exc: Exception) -> str:
    if isinstance(exc, SourceFailure):
        return str(exc)
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        return f"HTTP {response.status_code}" if response is not None else "HTTP error"
    if type(exc) is RuntimeError and str(exc) in {
        "원/달러 시세 없음", "원/달러 현재값 범위 오류", "원/달러 기준일 불일치",
        "환율 원천 관측시각 지연", "KOSPI 정규장 날짜·시각·수치 검증 실패",
        "종목 정규장 날짜·시각·수치 검증 실패",
        "정규장 종료 경계 또는 수집 시차 초과",
    }:
        return str(exc)
    return type(exc).__name__


def _checked(stage: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        raise SourceFailure(f"{stage}: {_failure_detail(exc)}") from None
VALIDATION_FOOTER = "• 검증 원칙: 값의 시장·시점·산출방식을 확인한 뒤 사용하며, 서로 다른 기준값은 혼용하지 않음"

START = dt.time(9, 0)
MARKET_CLOSE = dt.time(15, 35)
END = dt.time(23, 59, 59)

FX_REBOUND_KRW = 10.0
FX_REBOUND_PCT = 0.5
FX_STRONG_KRW = 20.0
FX_STRONG_PCT = 1.0
SECTOR_RELATIVE_PPT = 1.0
COUNTER_RELATIVE_PPT = -0.5

SHIPBUILDING = [
    ("HD현대중공업", "329180"),
    ("삼성중공업", "010140"),
    ("HD한국조선해양", "009540"),
    ("한화오션", "042660"),
]
DEFENSE = [
    ("한화에어로스페이스", "012450"),
    ("현대로템", "064350"),
    ("LIG넥스원", "079550"),
    ("한국항공우주", "047810"),
]
AUTOMOTIVE = [
    ("현대차", "005380"),
    ("기아", "000270"),
    ("현대모비스", "012330"),
    ("HL만도", "204320"),
]
COUNTER = [
    ("대한항공", "003490"),
    ("제주항공", "089590"),
    ("한국전력", "015760"),
    ("한국가스공사", "036460"),
]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-fx-sector-rotation-watch/1.0)",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}


def fnum(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        value = float(str(v).replace(",", "").replace("%", "").strip())
        return value if math.isfinite(value) and not isinstance(v, bool) else None
    except Exception:
        return None


def load_state(today: str) -> dict[str, Any]:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    if not isinstance(state, dict):
        raise ValueError("로테이션 상태 형식 오류 — 발송 보류")
    if state.get("date") == today and (
            state.get("sent_level") not in (0, 1, 2)
            or not isinstance(state.get("fx_samples"), list)):
        raise ValueError("로테이션 상태 필수값 오류 — 중복 방지 기록 보존")
    if state.get("date") != today:
        state = {
            "date": today,
            "fx_samples": [],
            "sent_level": 0,
            "sent_weakening": False,
            "last_signal": None,
        }
    return state


def save_pending(state: dict[str, Any]) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_time(raw: Any) -> dt.datetime | None:
    """Parse provider observation clock; date-only values are not clocks."""
    try:
        value = str(raw or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
            return None
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        # localTradedAt denotes the local exchange/provider time.
        return stamp.replace(tzinfo=KST) if stamp.tzinfo is None else stamp.astimezone(KST)
    except (ValueError, TypeError):
        return None


def _regular_quote_time(row: dict[str, Any], now: dt.datetime,
                        bounds: tuple[dt.datetime, dt.datetime]) -> dt.datetime | None:
    stamp = _source_time(row.get("localTradedAt"))
    opened, closed = bounds
    if stamp is None or stamp.date() != now.date() or stamp < opened:
        return None
    if stamp > now + dt.timedelta(seconds=5):
        return None
    if now >= closed:
        # Index remains at regular close: no after-market stock prices allowed.
        if str(row.get("marketStatus") or "").upper() not in ("CLOSE", "CLOSED"):
            return None
        if not closed - dt.timedelta(minutes=1) <= stamp <= closed + dt.timedelta(minutes=5):
            return None
    elif stamp > closed or now - stamp > dt.timedelta(minutes=5):
        return None
    return stamp


def _previous_session_day(day: dt.date) -> str:
    for offset in range(1, 15):
        candidate = day - dt.timedelta(days=offset)
        if session_bounds(candidate) is not None:
            return candidate.isoformat()
    raise RuntimeError("직전 거래일 확인 실패")


def _validated_prev_close_from_market_watch(today: str, expected: str) -> dict[str, Any] | None:
    # Prefer the current run. A committed prior state is usable ONLY when the
    # same current date and exact previous closing date are independently valid.
    for path in (MARKET_PENDING_PATH, MARKET_STATE_PATH):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            fx = (state.get("snapshot") or {}).get("usdkrw") or {}
            if str(fx.get("date") or "") != today or str(fx.get("prev_date") or "") != expected:
                continue
            if fx.get("comparison_valid") is not True:
                continue
            basis = str(fx.get("comparison_basis") or "")
            source = str(fx.get("seoul_close_source") or "")
            prev = fnum(fx.get("prev_value"))
            if ("서울외환시장 15:30" in basis and prev is not None
                    and 900 <= prev <= 2500
                    and source.startswith("https://ksureapi.einfomax.co.kr/")):
                return {"date": expected, "value": prev, "source": source, "basis": basis}
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return None


def fetch_fx(now: dt.datetime) -> dict[str, Any]:
    r = requests.get(FX_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("result") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise RuntimeError("원/달러 시세 없음")
    row = rows[0]
    value = fnum(row.get("closePrice"))
    raw_stamp = row.get("localTradedAt") or row.get("localDate")
    today = str(raw_stamp or "")[:10]
    if value is None or not 900 <= value <= 2500:
        raise RuntimeError("원/달러 현재값 범위 오류")
    if today != now.date().isoformat():
        raise RuntimeError("원/달러 기준일 불일치")
    stamp = _source_time(raw_stamp)
    received = dt.datetime.now(KST)
    if stamp is not None and (stamp.date() != now.date() or not
            -5 <= (received - stamp).total_seconds() <= 20 * 60):
        raise RuntimeError("환율 원천 관측시각 지연")
    naver_prev = fnum(rows[1].get("closePrice")) if len(rows) > 1 and isinstance(rows[1], dict) else None
    prev, prev_source, prev_date = None, None, None
    basis = "서울외환시장 15:30 USD/KRW 종가"
    basis_error, basis_reused = None, False
    try:
        expected = _previous_session_day(now.date())
        ref = _validated_prev_close_from_market_watch(today, expected)
        if ref is not None:
            basis_reused = True
            basis += " · 시장 스트레스 감시 동일 기준일 검증값 재사용"
        else:
            ref = fx_basis.fetch_seoul_prev_close(now)
        prev = fnum(ref.get("value"))
        prev_date = str(ref.get("date") or "")
        prev_source = str(ref.get("source") or "")
        if (prev_date != expected or prev is None or not 900 <= prev <= 2500
                or not prev_source.startswith("https://ksureapi.einfomax.co.kr/")):
            raise ValueError("직전 서울 종가 기준일·수치·출처 검증 실패")
    except Exception as exc:
        prev, prev_source, prev_date = None, None, None
        basis_error = type(exc).__name__
        basis_reused = False
    return {
        "value": value, "prev_close": prev, "prev_date": prev_date,
        "naver_prev_close": naver_prev, "date": today, "source": FX_URL,
        "comparison_basis": basis, "prev_close_source": prev_source,
        "basis_error": basis_error, "basis_reused": basis_reused,
        "queried_at": received.isoformat(timespec="seconds"),
        "source_observed_at": stamp.isoformat(timespec="seconds") if stamp else None,
        "source_time_verified": stamp is not None,
    }


def _dated_pair(rows: Any, date_key: str, today: str, previous: str) -> tuple[dict, dict]:
    if not isinstance(rows, list):
        raise SourceFailure("일별 자료 형식 오류")
    a = [r for r in rows if isinstance(r, dict) and str(r.get(date_key) or "") == today]
    b = [r for r in rows if isinstance(r, dict) and str(r.get(date_key) or "") == previous]
    if len(a) != 1 or len(b) != 1:
        raise SourceFailure("당일·직전 거래일 일별 자료 누락 또는 중복")
    return a[0], b[0]


def _parse_kospi_close(rows: Any, bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    closed = bounds[1]
    day = closed.date().isoformat()
    previous = _previous_session_day(closed.date())
    row, prior = _dated_pair(rows, "localTradedAt", day, previous)
    price, prev, pct = (fnum(row.get("closePrice")), fnum(prior.get("closePrice")),
                        fnum(row.get("fluctuationsRatio")))
    if price is None or prev is None or pct is None or price <= 0 or prev <= 0 or abs(pct) > 30:
        raise SourceFailure("KOSPI 일별 종가 수치 누락")
    if abs((price / prev - 1) * 100 - pct) > 0.02:
        raise SourceFailure("KOSPI 일별 종가·등락률 검산 불일치")
    return {"price": price, "change_pct": pct, "source": KOSPI_DAILY_URL,
            "source_date": day, "source_observed_at": None,
            "session_close_at": closed.isoformat(timespec="seconds"),
            "quote_basis": "정규장 일별 지수 종가"}


def _fetch_kospi_close(bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    r = requests.get(KOSPI_DAILY_URL, headers=HEADERS, timeout=(5, 10))
    r.raise_for_status()
    return _parse_kospi_close(r.json(), bounds)


def _kiwoom_close_response(code: str, day: str) -> dict:
    # Read-only regular-session TR; reuse the existing Kiwoom authentication
    # helper, not its cash-flow TR dispatch or any order/account interface.
    global _CLOSE_TOKEN, _CLOSE_DISABLED, _CLOSE_NEXT
    if not re.fullmatch(r"[0-9]{6}", code) or not re.fullmatch(r"[0-9]{8}", day):
        raise SourceFailure("키움 정규장 종목·날짜 형식 오류")
    if _CLOSE_DISABLED:
        raise SourceFailure("키움 인증 또는 통신 일시 중단")
    if _CLOSE_TOKEN is None:
        try:
            import market_kiwoom_flow as kiwoom_auth
            if not kiwoom_auth.configured():
                raise SourceFailure("키움 기존 인증 설정 없음")
            _CLOSE_TOKEN = kiwoom_auth._token()
        except Exception as exc:
            _CLOSE_DISABLED = True
            raise SourceFailure("키움 인증: " + type(exc).__name__) from None
    try:
        time.sleep(max(0.0, _CLOSE_NEXT - time.monotonic()))
        _CLOSE_NEXT = time.monotonic() + 0.30
        r = requests.post("https://api.kiwoom.com/api/dostk/chart",
                          headers={"authorization": "Bearer " + _CLOSE_TOKEN,
                                   "api-id": "ka11081", "content-type": "application/json;charset=UTF-8",
                                   "cont-yn": "N", "next-key": ""},
                          json={"stk_cd": code, "base_dt": day, "upd_stkpc_tp": "1"},
                          timeout=(5, 8), allow_redirects=False)
        if r.status_code != 200:
            if r.status_code in (401, 403, 429) or r.status_code >= 500:
                _CLOSE_DISABLED = True
            raise SourceFailure(f"키움 정규장 일봉 HTTP {r.status_code}")
        data = r.json()
        if not isinstance(data, dict) or data.get("return_code") not in (0, "0"):
            _CLOSE_DISABLED = True
            raise SourceFailure("키움 정규장 일봉 응답 미승인")
        return data
    except requests.RequestException as exc:
        _CLOSE_DISABLED = True
        raise SourceFailure("키움 정규장 일봉 통신: " + type(exc).__name__) from None


def _parse_kiwoom_close(data: dict, name: str, code: str,
                        bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    closed = bounds[1]
    day = closed.date().strftime("%Y%m%d")
    previous = _previous_session_day(closed.date()).replace("-", "")
    if str(data.get("stk_cd") or "") != code:
        raise SourceFailure("키움 정규장 종목코드 응답 불일치")
    row, prior = _dated_pair(data.get("result_list"), "dt", day, previous)
    price, prev, delta = (fnum(row.get("cur_prc")), fnum(prior.get("cur_prc")),
                          fnum(row.get("pred_pre")))
    sign = str(row.get("pred_pre_sig") or "")
    if price is None or prev is None or delta is None or not price or not prev or sign not in ("1", "2", "3", "4", "5"):
        raise SourceFailure("키움 정규장 종가·전일 대비 원값 누락")
    price, prev = abs(price), abs(prev)
    signed_delta = abs(delta) * (1 if sign in ("1", "2") else -1 if sign in ("4", "5") else 0)
    if (sign == "3" and delta != 0) or abs((price - prev) - signed_delta) > 0.5:
        raise SourceFailure("키움 정규장 전일 대비·직전 종가 검산 불일치")
    pct = (price / prev - 1) * 100
    if not math.isfinite(pct) or abs(pct) > 100:
        raise SourceFailure("키움 정규장 등락률 범위 오류")
    return {"name": name, "code": code, "price": price, "change_pct": pct,
            "source": KIWOOM_CLOSE_DOC, "source_date": closed.date().isoformat(),
            "source_observed_at": None, "session_close_at": closed.isoformat(timespec="seconds"),
            "quote_basis": "키움 KRX 정규장 일봉"}


def _fetch_kiwoom_close(name: str, code: str, bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    return _parse_kiwoom_close(_kiwoom_close_response(code, bounds[1].date().strftime("%Y%m%d")),
                               name, code, bounds)


def _parse_ls_close(data: dict, name: str, code: str,
                    bounds: tuple[dt.datetime, dt.datetime],
                    previous_bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    """Accept only exact KRX session-end bars independently matching both
    official header closes. Never use the last extended-session candle."""
    header = data.get("t8452OutBlock") or {}
    if not isinstance(header, dict) or str(header.get("shcode") or "") != code:
        raise SourceFailure("LS 정규장 종목코드 응답 불일치")
    closed, previous_close = bounds[1], previous_bounds[1]
    if (str(header.get("s_time") or "") != bounds[0].strftime("%H%M%S")
            or str(header.get("e_time") or "") != closed.strftime("%H%M%S")):
        raise SourceFailure("LS 정규장 시작·종료시각 불일치")
    rows = data.get("t8452OutBlock1")
    if not isinstance(rows, list):
        raise SourceFailure("LS 분봉 형식 오류")
    def at_close(when):
        day, clock = when.strftime("%Y%m%d"), when.strftime("%H%M%S")
        dated = [r for r in rows if isinstance(r, dict) and str(r.get("date") or "").strip() == day]
        # LS time fields can include a zero fractional-second suffix (up to
        # ten digits). Do not truncate a nonzero fraction or accept nearby bars.
        exact = [r for r in dated if re.fullmatch(clock+r"0{0,4}", str(r.get("time") or "").strip())]
        if len(exact) != 1:
            clocks = sorted({str(r.get("time") or "").strip() for r in dated
                             if re.fullmatch(r"[0-9]{6,10}", str(r.get("time") or "").strip())})
            near = [t for t in clocks if t[:4] in ("1525", "1529", "1530", "1531", "1535")]
            raise SourceFailure(f"LS 정규장 종료 봉 누락·중복 날짜={day} 당일행={len(dated)} 일치={len(exact)} 종료부근시각={','.join(near[:6]) or '없음'}")
        value = fnum(exact[0].get("close"))
        if value is None or value <= 0:
            raise SourceFailure("LS 정규장 종료 봉 종가 누락")
        return value
    price, prev = at_close(closed), at_close(previous_close)
    official, official_prev = fnum(header.get("diclose")), fnum(header.get("jiclosev"))
    if official != price or official_prev != prev:
        raise SourceFailure("LS 정규장 종료 봉·공식 종가 교차검증 불일치")
    limit_low, limit_high = fnum(header.get("lowend")), fnum(header.get("highend"))
    if (limit_low is not None and limit_high is not None and limit_low > 0
            and not limit_low <= prev <= limit_high):
        raise SourceFailure("LS 직전 종가·당일 가격제한 기준 불일치")
    pct = (price / prev - 1) * 100
    if not math.isfinite(pct) or abs(pct) > 30.1:
        raise SourceFailure("LS 정규장 등락률 범위 오류")
    return {"name": name, "code": code, "price": price, "change_pct": pct,
            "source": LS_CLOSE_DOC, "source_date": closed.date().isoformat(),
            "source_observed_at": None, "session_close_at": closed.isoformat(timespec="seconds"),
            "quote_basis": LS_CLOSE_BASIS}


def _fetch_ls_close(name: str, code: str, bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    global _LS_CLOSE_TOKEN, _LS_CLOSE_DISABLED, _LS_CLOSE_NEXT, _LS_CLOSE_FAILURES
    if _LS_CLOSE_DISABLED:
        raise SourceFailure("LS 인증 또는 통신 일시 중단")
    if not re.fullmatch(r"[0-9]{6}", code):
        raise SourceFailure("LS 종목코드 형식 오류")
    previous = dt.date.fromisoformat(_previous_session_day(bounds[1].date()))
    prev_bounds = session_bounds(previous)
    if prev_bounds is None:
        raise SourceFailure("LS 직전 거래일 달력 확인 실패")
    if _LS_CLOSE_TOKEN is None:
        try:
            key = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
            secret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
            if not key or not secret:
                raise SourceFailure("LS 기존 인증 설정 없음")
            auth = requests.post("https://openapi.ls-sec.co.kr:8080/oauth2/token",
                                 headers={"content-type": "application/x-www-form-urlencoded"},
                                 params={"grant_type": "client_credentials", "appkey": key,
                                         "appsecretkey": secret, "scope": "oob"},
                                 timeout=(5, 10), allow_redirects=False)
            if auth.status_code != 200:
                raise SourceFailure(f"LS 인증 HTTP {auth.status_code}")
            token = auth.json().get("access_token")
            if not isinstance(token, str) or not token:
                raise SourceFailure("LS 인증 응답 토큰 없음")
            _LS_CLOSE_TOKEN = token
        except Exception as exc:
            _LS_CLOSE_DISABLED = True
            raise SourceFailure("LS 인증: " + _failure_detail(exc)) from None
    def fetch_day(day: str) -> dict:
        global _LS_CLOSE_NEXT, _LS_CLOSE_DISABLED, _LS_CLOSE_FAILURES
        for attempt in range(2):
            time.sleep(max(0.0, _LS_CLOSE_NEXT - time.monotonic()))
            _LS_CLOSE_NEXT = time.monotonic() + 1.10
            try:
                r = requests.post("https://openapi.ls-sec.co.kr:8080/stock/chart",
                                  headers={"authorization": "Bearer " + _LS_CLOSE_TOKEN,
                                           "content-type": "application/json; charset=utf-8",
                                           "tr_cd": "t8452", "tr_cont": "N", "tr_cont_key": ""},
                                  json={"t8452InBlock": {"shcode": code, "ncnt": 5, "qrycnt": 350,
                                        "nday": "0", "sdate": day, "stime": "",
                                        "edate": day, "etime": "",
                                        "cts_date": " ", "cts_time": "", "comp_yn": "N", "exchgubun": "K"}},
                                  timeout=(5, 10), allow_redirects=False)
            except requests.RequestException as exc:
                if attempt == 0:
                    time.sleep(2.0)
                    continue
                _LS_CLOSE_FAILURES += 1
                if _LS_CLOSE_FAILURES >= 2:
                    _LS_CLOSE_DISABLED = True
                raise SourceFailure("LS 정규장 분봉 통신: " + type(exc).__name__) from None
            if r.status_code != 200:
                retryable = r.status_code in (429, 500, 502, 503, 504) or (
                    r.status_code == 404 and "/503.html" in (r.text or ""))
                if retryable and attempt == 0:
                    time.sleep(2.5)
                    continue
                if retryable:
                    _LS_CLOSE_FAILURES += 1
                if r.status_code in (401, 403, 429) or _LS_CLOSE_FAILURES >= 2:
                    _LS_CLOSE_DISABLED = True
                raise SourceFailure(f"LS 정규장 분봉 HTTP {r.status_code}")
            data = r.json()
            if not isinstance(data, dict) or str(data.get("rsp_cd") or "") not in ("00000", "00001"):
                raise SourceFailure("LS 정규장 분봉 응답 미승인")
            header = data.get("t8452OutBlock") or {}
            if not isinstance(header, dict) or str(header.get("shcode") or "") != code:
                raise SourceFailure("LS 거래일별 종목코드 불일치")
            rows = data.get("t8452OutBlock1")
            if not isinstance(rows, list):
                raise SourceFailure("LS 거래일별 분봉 형식 오류")
            rows = [r for r in rows if isinstance(r, dict) and str(r.get("date") or "").strip() == day]
            if not rows:
                raise SourceFailure(f"LS 거래일별 분봉 없음 날짜={day}")
            _LS_CLOSE_FAILURES = 0
            return {"t8452OutBlock": header, "t8452OutBlock1": rows}
        raise SourceFailure("LS 정규장 분봉 재시도 소진")

    # Real 2026-11-27 probe: the combined request returned only 33 prior-day
    # rows without the prior session end. Query each trading date separately.
    day = bounds[1].date().strftime("%Y%m%d")
    prior_day = previous.strftime("%Y%m%d")
    current = fetch_day(day)
    prior = fetch_day(prior_day)
    combined = {"t8452OutBlock": current["t8452OutBlock"],
                "t8452OutBlock1": current["t8452OutBlock1"] + prior["t8452OutBlock1"]}
    return _parse_ls_close(combined, name, code, bounds, prev_bounds)


def _fetch_regular_stock_close(name: str, code: str, bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    # LS authenticated in the real probe; Kiwoom authentication failed.
    try:
        return _fetch_ls_close(name, code, bounds)
    except Exception as exc:
        ls_reason = _failure_detail(exc)
    try:
        return _fetch_kiwoom_close(name, code, bounds)
    except Exception as exc:
        raise SourceFailure("LS: " + ls_reason + " / 키움: " + _failure_detail(exc)) from None


def fetch_kospi(bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    now = dt.datetime.now(KST)
    close_error = None
    if now >= bounds[1] + dt.timedelta(minutes=CLOSE_SETTLE_MINUTES):
        try:
            return _fetch_kospi_close(bounds)
        except Exception as exc:
            close_error = _failure_detail(exc)
            print("fx_sector_rotation_kospi_daily_unavailable=" + close_error)
    try:
        return _fetch_kospi_basic(bounds)
    except Exception as exc:
        if close_error is not None:
            raise SourceFailure("일별 종가: " + close_error + " / 기본 시세: " + _failure_detail(exc)) from None
        raise


def _fetch_kospi_basic(bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    r = requests.get(KOSPI_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    d = r.json()
    pct = fnum(d.get("fluctuationsRatio"))
    price = fnum(d.get("closePrice") or d.get("currentPrice"))
    stamp = _regular_quote_time(d, dt.datetime.now(KST), bounds)
    if pct is None or abs(pct) > 30 or price is None or price <= 0 or stamp is None:
        raise RuntimeError("KOSPI 정규장 날짜·시각·수치 검증 실패")
    return {"change_pct": pct, "price": price, "source": KOSPI_URL,
            "source_observed_at": stamp.isoformat(timespec="seconds")}


def fetch_quote(name: str, code: str,
                bounds: tuple[dt.datetime, dt.datetime]) -> dict[str, Any]:
    # Same existing basic endpoint, no new provider or undated HTML fallback.
    url = v11.NAVER_STOCK_BASIC.format(code=code)
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    row = r.json()
    pct_raw = row.get("fluctuationsRatio")
    if pct_raw in (None, ""):
        pct_raw = row.get("changeRate")
    price = fnum(row.get("closePrice") or row.get("currentPrice"))
    pct = fnum(pct_raw)
    stamp = _regular_quote_time(row, dt.datetime.now(KST), bounds)
    returned_code = row.get("itemCode") or row.get("stockCode")
    if (returned_code not in (None, "", code) or stamp is None or price is None
            or price <= 0 or pct is None or abs(pct) > 100):
        raise RuntimeError("종목 정규장 날짜·시각·수치 검증 실패")
    return {"name": str(row.get("stockName") or row.get("itemName") or name),
            "code": code, "price": price, "change_pct": pct,
            "source_observed_at": stamp.isoformat(timespec="seconds")}


def fetch_group(items: list[tuple[str, str]], bounds: tuple[dt.datetime, dt.datetime],
                state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    settled = dt.datetime.now(KST) >= bounds[1] + dt.timedelta(minutes=CLOSE_SETTLE_MINUTES)
    cache = state.setdefault("regular_closes", {}) if state is not None and settled else {}
    if not isinstance(cache, dict):
        cache = {}
        if state is not None:
            state["regular_closes"] = cache
    for name, code in items:
        reasons = []
        if settled:
            cached = cache.get(code) or {}
            if (isinstance(cached, dict) and cached.get("code") == code
                    and cached.get("source_date") == bounds[1].date().isoformat()
                    and cached.get("session_close_at") == bounds[1].isoformat(timespec="seconds")
                    and cached.get("source") in _CLOSE_SOURCES
                    and cached.get("quote_basis") == _CLOSE_SOURCES[cached["source"]]
                    and (fnum(cached.get("price")) or 0) > 0
                    and fnum(cached.get("change_pct")) is not None
                    and abs(float(cached["change_pct"])) <= 100):
                out.append(dict(cached))
                continue
            try:
                row = _fetch_regular_stock_close(name, code, bounds)
                cache[code] = row
                out.append(row)
                continue
            except Exception as exc:
                reasons.append("증권사 정규장: " + _failure_detail(exc))
        try:
            out.append(fetch_quote(name, code, bounds))
            continue
        except Exception as exc:
            reasons.append("기본 시세: " + _failure_detail(exc))
        reason = " / ".join(reasons)
        print(f"fx_sector_rotation_quote_unavailable={code}: {reason}")
        out.append({"name": name, "code": code, "price": None, "change_pct": None, "error": reason})
    return out


def group_stats(rows: list[dict[str, Any]], benchmark: float) -> dict[str, Any]:
    vals = [v for r in rows if (v := fnum(r.get("change_pct"))) is not None]
    if not vals:
        return {"avg": None, "positive": 0, "relative": None, "valid": 0, "confirmed": False}
    avg = sum(vals) / len(vals)
    pos = sum(1 for v in vals if v > 0)
    rel = avg - benchmark
    confirmed = len(vals) >= 3 and pos >= 3 and rel >= SECTOR_RELATIVE_PPT
    return {"avg": avg, "positive": pos, "relative": rel, "valid": len(vals), "confirmed": confirmed}


def quote_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for r in rows:
        if r.get("change_pct") is None:
            lines.append(f"• {html.escape(str(r['name']))}: 시세 확인 실패")
        else:
            lines.append(
                f"• {html.escape(str(r['name']))}: <b>{float(r['price']):,.0f}원 ({float(r['change_pct']):+.2f}%)</b>"
            )
    return lines


def fmt_stats(label: str, s: dict[str, Any], benchmark: float) -> list[str]:
    if s.get("avg") is None:
        return [f"• {label}: 확인 실패"]
    verdict = "확인" if s.get("confirmed") else ("자료 부족" if int(s.get("valid") or 0) < 3 else "조건 미충족")
    return [
        f"• {label}: {int(s['positive'])}/{int(s['valid'])} 상승 · 평균 <b>{float(s['avg']):+.2f}%</b>",
        f"  ↳ KOSPI {benchmark:+.2f}% 대비 상대강도 <b>{float(s['relative']):+.2f}%p</b> · 로테이션 {verdict}",
    ]


def build_alert(
    now: dt.datetime,
    fx: dict[str, Any],
    session_low: float | None,
    rebound_krw: float | None,
    rebound_pct: float | None,
    daily_krw: float | None,
    daily_pct: float | None,
    kospi: dict[str, Any],
    ship_rows: list[dict[str, Any]],
    defense_rows: list[dict[str, Any]],
    auto_rows: list[dict[str, Any]],
    counter_rows: list[dict[str, Any]],
    ship: dict[str, Any],
    defense: dict[str, Any],
    auto: dict[str, Any],
    counter: dict[str, Any],
    level: int,
) -> str:
    after_close = bool(fx.get("after_close"))
    confirmed_labels = [
        label for label, stats in (("조선", ship), ("방산", defense), ("자동차", auto))
        if stats.get("confirmed")
    ]
    if level >= 2:
        verdict = "🔴 <b>강한 환율 민감 업종 로테이션</b> — 환율 강한 반등과 수출형 업종 2개 이상 상대강세 확인"
    elif len(confirmed_labels) >= 2:
        verdict = "🟠 <b>환율 민감 업종 로테이션 확인</b> — " + "·".join(confirmed_labels) + " 동반 상대강세"
    else:
        confirmed = confirmed_labels[0] if confirmed_labels else "수출형 업종"
        verdict = f"🟡 <b>부분 로테이션</b> — {confirmed} 상대강세 우선 확인"

    counter_note = ""
    if counter.get("relative") is not None and int(counter.get("valid") or 0) >= 3:
        if float(counter["relative"]) <= COUNTER_RELATIVE_PPT:
            counter_note = "  ↳ 달러비용 민감 업종의 상대약세까지 동반 → 환율 설명력 보강"
        else:
            counter_note = "  ↳ 반대편 업종 상대약세는 뚜렷하지 않음 → 환율 단독 설명은 제한"

    reaction_label = "당일 종가 반응" if after_close else "현재 반응"
    lines = [
        "🔄 <b>환율 민감 업종 로테이션 감지</b>",
        f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>",
        "",
        verdict,
    ]
    if after_close:
        lines += [
            "• 시점 구분: <b>주식은 정규장 종가 반응</b>, <b>환율은 장마감 후 현재값</b>",
            "  ↳ 장마감 후 환율 추가 상승이 확인된 것이므로 당일 주가 상승을 그 이후 환율 움직임의 결과라고 역으로 단정하지 않음",
        ]
    lines += [
        "",
        "<b>원/달러 반등</b>",
        f"• 환율 조회값 <b>{float(fx['value']):,.1f}원</b> · 기준일 {fx['date']}",
        "• 원천 관측시각: " + (html.escape(str(fx.get("source_observed_at"))) if fx.get("source_time_verified") else "미제공 — 날짜가 확인된 조회 표본이며 주식과의 동시성 미검증"),
    ]
    if session_low is not None and rebound_krw is not None and rebound_pct is not None:
        lines.append(f"• 정규장 조회 표본 저점 {session_low:,.1f}원 대비 <b>{rebound_krw:+,.1f}원 ({rebound_pct:+.2f}%)</b> — 실제 장중 최저가 아님")
    else:
        lines.append("• 정규장 저점 표본 없음 — 저점 반등 조건 판정 보류")
    if fx.get("sample_gap_minutes", 0) > 30:
        lines.append(f"• 정규장 표본 최대 공백 {fx['sample_gap_minutes']:.0f}분 — 사이에 발생한 움직임은 미확인")
    if kospi.get("quote_basis"):
        lines.append("• KOSPI: " + html.escape(str(kospi["quote_basis"])) + " · " + html.escape(str(kospi.get("session_close_at") or "")))
    else:
        lines.append(f"• KOSPI 관측시각: {html.escape(str(kospi.get('source_observed_at') or '미확인'))}")
    close_rows = ship_rows + defense_rows + auto_rows + counter_rows
    if any(row.get("source") == KIWOOM_CLOSE_DOC for row in close_rows):
        lines.append(f'• 종목 정규장 종가: <a href="{KIWOOM_CLOSE_DOC}">키움증권 공식 일봉</a> (원천 제공 종가 기준)')
    if any(row.get("source") == LS_CLOSE_DOC for row in close_rows):
        lines.append(f'• 종목 정규장 종가: <a href="{LS_CLOSE_DOC}">LS증권</a> KRX 정규장 종료 봉과 당일·직전 종가 일치 검증')
    if daily_krw is not None and daily_pct is not None:
        lines.append(f"• 직전 서울 15:30 종가({fx.get('prev_date')}) 대비 <b>{daily_krw:+,.1f}원 ({daily_pct:+.2f}%)</b>")
        if fx.get("basis_reused"):
            lines.append("  ↳ 서울 종가 원천 일시 조회 실패 → 시장 스트레스 감시에서 이미 검증한 동일 공식 기준값 재사용")
    elif fx.get("basis_error"):
        lines.append("• 전일 서울 15:30 종가 조회 실패 → 일간 강한 신호 판정 보류")

    lines += [
        "",
        "<b>업종 상대강도</b>",
        *fmt_stats("조선", ship, float(kospi["change_pct"])),
        *fmt_stats("방산", defense, float(kospi["change_pct"])),
        *fmt_stats("자동차", auto, float(kospi["change_pct"])),
        *fmt_stats("달러비용 민감 업종", counter, float(kospi["change_pct"])),
    ]
    if counter_note:
        lines.append(counter_note)

    lines += [
        "",
        f"<b>조선 {reaction_label}</b>",
        *quote_lines(ship_rows),
        "",
        f"<b>방산 {reaction_label}</b>",
        *quote_lines(defense_rows),
        "",
        f"<b>자동차 {reaction_label}</b>",
        *quote_lines(auto_rows),
        "",
        "<b>반대편 확인</b>",
        *quote_lines(counter_rows),
        "",
        "<b>해석</b>",
        "• 원/달러 반등은 원화 강세로 약화됐던 수출형 산업재의 환산실적 우려를 완화하는 방향입니다.",
        "• 다만 조선·방산·자동차 주가를 환율 하나로 설명하지 않습니다. 수주잔고·신규수주·실적 개선·낙폭 과대·정책/지정학 재료를 별도로 확인합니다.",
        "• 조선은 외화 수주와 환헤지 구조, 방산은 계약통화·환헤지·매출 인식 시점·현지조달 비중, 자동차는 해외판매·현지생산·환헤지 비중에 따라 실제 이익 민감도가 달라집니다.",
        "",
        "<b>무효화 조건</b>",
        "• 원/달러 반등폭이 이번 신호의 50% 이상 반납하거나",
        "• 조선·방산·자동차가 모두 KOSPI 대비 상대강도 +1%p를 잃으면 환율 로테이션 신호 약화로 봅니다.",
        "",
        "<b>원문</b>",
        f'• <a href="{html.escape(str(fx["source"]), quote=True)}">원/달러 시세</a>',
        f'• <a href="{html.escape(str(kospi.get("source") or KOSPI_URL), quote=True)}">KOSPI 시세</a>',
    ]
    if fx.get("prev_close_source"):
        lines.append(f'• <a href="{html.escape(str(fx["prev_close_source"]), quote=True)}">전일 서울 15:30 종가 근거</a>')
    lines += ["", VALIDATION_FOOTER]
    return "\n".join(lines)


def _relative_lost(*groups: dict[str, Any]) -> bool:
    # Missing is unknown, not zero or -999. Preserve the original 3-of-4 rule.
    return all(int(g.get("valid") or 0) >= 3 and
               (v := fnum(g.get("relative"))) is not None and
               v < SECTOR_RELATIVE_PPT for g in groups)


def _regular_samples(state: dict[str, Any], bounds: tuple[dt.datetime, dt.datetime]) -> list[dict[str, Any]]:
    opened, closed = bounds
    rows = []
    for row in state.get("fx_samples") or []:
        stamp = _source_time(row.get("ts"))
        value = fnum(row.get("value"))
        if stamp is not None and opened <= stamp <= closed and value is not None and 900 <= value <= 2500:
            rows.append({"ts": stamp.isoformat(timespec="seconds"), "value": value})
    return rows


def _sample_low_and_gap(state: dict[str, Any], bounds: tuple[dt.datetime, dt.datetime],
                        now: dt.datetime) -> tuple[float | None, float]:
    opened, closed = bounds
    rows = _regular_samples(state, bounds)
    prior_low = state.get("regular_sample_low") or {}
    stamp = _source_time(prior_low.get("ts"))
    value = fnum(prior_low.get("value"))
    if stamp is not None and opened <= stamp <= closed and value is not None and 900 <= value <= 2500:
        rows.append({"ts": stamp.isoformat(timespec="seconds"), "value": value})
    if rows:
        best = min(rows, key=lambda x: x["value"])
        state["regular_sample_low"] = best
        low = best["value"]
    else:
        low = None
    times = sorted(set(_source_time(r["ts"]) for r in rows))
    end = min(now, closed)
    timestamps = [opened] + [t for t in times if t is not None and opened <= t <= end] + [end]
    gap = max((b-a).total_seconds()/60 for a,b in zip(timestamps, timestamps[1:]))
    # Preserve measured gap even if early samples have since been compacted.
    gap = max(gap, fnum(state.get("regular_max_gap_minutes")) or 0.0)
    state["regular_max_gap_minutes"] = round(gap, 2)
    return low, gap


def _weakening_reason(fx: dict[str, Any], sig: dict[str, Any], ship: dict[str, Any],
                     defense: dict[str, Any], auto: dict[str, Any]) -> list[str]:
    peak, low, current = (fnum(sig.get("rebound_krw")),
                          fnum(sig.get("session_low")), fnum(fx.get("value")))
    reasons = []
    if peak is not None and peak > 0 and low is not None and current is not None and current-low <= peak*0.5:
        reasons.append("환율 반등폭 50% 이상 반납")
    if _relative_lost(ship, defense, auto):
        reasons.append("세 업종 모두 상대강도 +1%p 미달")
    return reasons


def build_weakening_alert(now: dt.datetime, fx: dict[str, Any], state: dict[str, Any], kospi_pct: float,
                          ship: dict[str, Any], defense: dict[str, Any], auto: dict[str, Any],
                          reasons: list[str]) -> str:
    sig = state.get("last_signal") or {}
    peak, low = fnum(sig.get("rebound_krw")), fnum(sig.get("session_low"))
    cur = fnum(fx.get("value"))
    movement = "• 직전 신호 반등폭 또는 저점 자료 부족"
    if peak is not None and low is not None and cur is not None:
        movement = f"• 직전 반등폭 <b>{peak:+,.1f}원</b> → 같은 저점 대비 <b>{cur-low:+,.1f}원</b>"
    lines = [
        "⚠️ <b>환율 민감 업종 로테이션 약화</b>",
        f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>", "", movement,
    ]
    for label, group in (("조선", ship), ("방산", defense), ("자동차", auto)):
        relative = fnum(group.get("relative"))
        if relative is None or int(group.get("valid") or 0) < 3:
            lines.append(f"• {label} 상대강도: 확인 불가")
        else:
            lines.append(f"• {label} 상대강도: <b>{relative:+.2f}%p</b>")
    lines += [f"• KOSPI: <b>{kospi_pct:+.2f}%</b>",
              "• 판정: " + " / ".join(reasons),
              "• 환율은 조회 표본 기준이며 원천 시각 미제공 시 주식과의 동시성 미검증",
              "", VALIDATION_FOOTER]
    return "\n".join(lines)


def write_status(now: dt.datetime, text: str) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(f"# 환율 민감 업종 로테이션\n\n- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n- 상태: {text}\n", encoding="utf-8")


def _regression_checks() -> None:
    """Small deterministic target-only checks, no external calls or state writes."""
    day = dt.date(2026, 11, 26)
    op = dt.datetime.combine(day, dt.time(9), KST)
    cl = dt.datetime.combine(day, dt.time(15, 30), KST)
    bounds = (op, cl)
    def check(condition, label):
        if not condition:
            raise AssertionError(label)
    good = {"localTradedAt": "2026-11-26T15:30:00+09:00", "marketStatus": "CLOSE"}
    check(_regular_quote_time(good, cl+dt.timedelta(hours=2), bounds) is not None, "regular close")
    check(_regular_quote_time(dict(good, localTradedAt="2026-11-26T17:00:00+09:00"),
                              cl+dt.timedelta(hours=2), bounds) is None, "aftermarket exclusion")
    check(_regular_quote_time(dict(good, localTradedAt="2026-11-25T15:30:00+09:00"),
                              cl+dt.timedelta(hours=2), bounds) is None, "previous date exclusion")
    check(_regular_quote_time({"localTradedAt": "2026-11-26"}, cl, bounds) is None, "date-only exclusion")
    check(_regular_quote_time({"localTradedAt": "2026-11-26T10:00:00+09:00"},
                              op+dt.timedelta(hours=2), bounds) is None, "stale quote")
    known = {"valid": 4, "relative": 0.0}
    missing = {"valid": 0, "relative": None}
    check(_relative_lost(known, known, known), "real zero relative strength")
    check(not _relative_lost(known, known, missing), "missing is not weakening")
    check(not _weakening_reason({"value": 1345}, {"rebound_krw": 10, "session_low": 1335},
                                known, known, missing), "no false weakening")
    check(group_stats([{"change_pct": float("nan")}, {"change_pct": 0.0}], 0)["valid"] == 1, "finite and zero")
    state = {"fx_samples": [{"ts": "2026-11-26T11:00:00+09:00", "value": 1340.0},
                            {"ts": "2026-11-26T19:00:00+09:00", "value": 1320.0}]}
    low, gap = _sample_low_and_gap(state, bounds, cl+dt.timedelta(hours=4))
    check(low == 1340 and gap == 270, "regular low and gap")
    state["fx_samples"] = []
    check(_sample_low_and_gap(state, bounds, cl)[0] == 1340, "persisted regular low")
    previous = _previous_session_day(day)
    pair = [{"localTradedAt": day.isoformat(), "closePrice": 1020, "fluctuationsRatio": 2.0},
            {"localTradedAt": previous, "closePrice": 1000}]
    check(_parse_kospi_close(pair, bounds)["change_pct"] == 2.0, "daily close")
    def rejects(fn, label):
        try:
            fn()
        except SourceFailure:
            return
        raise AssertionError(label)
    rejects(lambda: _parse_kospi_close(pair[:1], bounds), "previous day missing")
    rejects(lambda: _parse_kospi_close([dict(pair[0], fluctuationsRatio=3), pair[1]], bounds), "index arithmetic")
    code = "005930"
    data = {"stk_cd": code, "result_list": [
        {"dt": day.strftime("%Y%m%d"), "cur_prc": "10200", "pred_pre": "200", "pred_pre_sig": "2"},
        {"dt": previous.replace("-", ""), "cur_prc": "10000"}]}
    check(abs(_parse_kiwoom_close(data, "검사", code, bounds)["change_pct"] - 2) < 1e-8, "regular stock close")
    rejects(lambda: _parse_kiwoom_close(dict(data, stk_cd=code+"_NX"), "검사", code, bounds), "NXT rejection")
    rejects(lambda: _parse_kiwoom_close(dict(data, result_list=data["result_list"][:1]), "검사", code, bounds), "stock prior date missing")
    bad = dict(data, result_list=[dict(data["result_list"][0], pred_pre="300"), data["result_list"][1]])
    rejects(lambda: _parse_kiwoom_close(bad, "검사", code, bounds), "stock arithmetic")
    down = dict(data, result_list=[dict(data["result_list"][0], cur_prc="-9800", pred_pre="-200", pred_pre_sig="5"), data["result_list"][1]])
    check(abs(_parse_kiwoom_close(down, "검사", code, bounds)["change_pct"] + 2) < 1e-8, "signed decline")
    prev_bounds = session_bounds(dt.date.fromisoformat(previous))
    def ls_bar(when, price):
        return {"date": when.strftime("%Y%m%d"), "time": when.strftime("%H%M%S"), "close": price}
    ls_data = {"t8452OutBlock": {"shcode": code, "s_time": "090000", "e_time": "153000",
                                "diclose": 10200, "jiclosev": 10000},
               "t8452OutBlock1": [ls_bar(cl, 10200), ls_bar(prev_bounds[1], 10000),
                                  ls_bar(cl+dt.timedelta(hours=1), 11000)]}
    check(abs(_parse_ls_close(ls_data, "검사", code, bounds, prev_bounds)["change_pct"] - 2) < 1e-8,
          "LS exact close not aftermarket")
    rejects(lambda: _parse_ls_close(dict(ls_data, t8452OutBlock1=ls_data["t8452OutBlock1"][1:]),
                                   "검사", code, bounds, prev_bounds), "LS exact close missing")
    rejects(lambda: _parse_ls_close(dict(ls_data, t8452OutBlock=dict(ls_data["t8452OutBlock"], diclose=11000)),
                                   "검사", code, bounds, prev_bounds), "LS header mismatch")
    rejects(lambda: _parse_ls_close(dict(ls_data, t8452OutBlock=dict(ls_data["t8452OutBlock"], shcode="000660")),
                                   "검사", code, bounds, prev_bounds), "LS code mismatch")
    rejects(lambda: _parse_ls_close(dict(ls_data, t8452OutBlock=dict(ls_data["t8452OutBlock"], e_time="200000")),
                                   "검사", code, bounds, prev_bounds), "LS session mismatch")
    extended_clock = dict(ls_data, t8452OutBlock1=[
        dict(ls_data["t8452OutBlock1"][0], time=cl.strftime("%H%M%S")+"0000"),
        ls_data["t8452OutBlock1"][1], ls_data["t8452OutBlock1"][2]])
    check(abs(_parse_ls_close(extended_clock, "검사", code, bounds, prev_bounds)["change_pct"] - 2) < 1e-8,
          "LS ten-digit exact clock")
    rejects(lambda: _parse_ls_close(dict(extended_clock, t8452OutBlock1=[
        dict(extended_clock["t8452OutBlock1"][0], time=cl.strftime("%H%M%S")+"0001"),
        *extended_clock["t8452OutBlock1"][1:]]), "검사", code, bounds, prev_bounds),
        "LS nonzero post-close fractional clock")
    print("fx_sector_rotation_regressions=26 passed; no Telegram or state writes")


def _run() -> int:
    now = dt.datetime.now(KST)
    today = now.date().isoformat()
    bounds = session_bounds(now.date())
    if bounds is None or now < bounds[0] or not (START <= now.time() <= END):
        # No midnight/pre-open rewrite of a previously delivered day's keys.
        write_status(now, "정규 거래일 감시시간 외 — 기존 상태 보존, 신규 발송 없음")
        print("fx_sector_rotation=outside_session_window")
        return 0

    state = _checked("상태 읽기", load_state, today)
    fx = _checked("원/달러 조회", fetch_fx, now)
    after_close = now >= bounds[1]

    samples = list(state.get("fx_samples") or [])
    samples.append({"ts": fx.get("source_observed_at") or fx["queried_at"], "value": float(fx["value"])})
    state["fx_samples"] = samples[-256:]
    session_low, gap = _sample_low_and_gap(state, bounds, now)
    try:
        kospi = _checked("KOSPI 조회", fetch_kospi, bounds)
    except SourceFailure as exc:
        state["last_attempt"] = {"checked_at": now.isoformat(timespec="seconds"),
                                 "quality": "unavailable", "reason": str(exc)}
        save_pending(state)
        write_status(now, "판정 보류 / " + str(exc) + " / 유효 환율 표본만 저장")
        print("fx_sector_rotation=unavailable reason=" + str(exc))
        return 2
    fx["after_close"] = after_close
    fx["sample_gap_minutes"] = round(gap, 2)
    rebound_krw = float(fx["value"])-session_low if session_low is not None else None
    rebound_pct = (float(fx["value"])/session_low-1)*100 if session_low is not None else None
    daily_krw = daily_pct = None
    if fx.get("prev_close") is not None:
        daily_krw = float(fx["value"])-float(fx["prev_close"])
        daily_pct = (float(fx["value"])/float(fx["prev_close"])-1)*100

    ship_rows = fetch_group(SHIPBUILDING, bounds, state)
    defense_rows = fetch_group(DEFENSE, bounds, state)
    auto_rows = fetch_group(AUTOMOTIVE, bounds, state)
    counter_rows = fetch_group(COUNTER, bounds, state)
    benchmark = float(kospi["change_pct"])
    ship, defense, auto, counter = (group_stats(rows, benchmark)
        for rows in (ship_rows, defense_rows, auto_rows, counter_rows))

    # A long quote collection may cross the close; never mix live and closed
    # returns from different phases, nor large observation-time differences.
    finished = dt.datetime.now(KST)
    if (now < bounds[1] <= finished) or (not after_close and
            (finished-now).total_seconds() > 5*60):
        raise RuntimeError("정규장 종료 경계 또는 수집 시차 초과")

    fx_hit = bool((rebound_krw is not None and rebound_krw >= FX_REBOUND_KRW)
                  or (rebound_pct is not None and rebound_pct >= FX_REBOUND_PCT))
    strong_fx = bool((daily_krw is not None and daily_krw >= FX_STRONG_KRW)
                     or (daily_pct is not None and daily_pct >= FX_STRONG_PCT))
    sectors_confirmed = sum(int(bool(g.get("confirmed"))) for g in (ship, defense, auto))
    level = 1 if fx_hit and sectors_confirmed >= 1 else 0
    if strong_fx and sectors_confirmed >= 2:
        level = 2

    sent_level = int(state.get("sent_level") or 0)
    coverage = f"유효 종목 조선 {ship['valid']}/4·방산 {defense['valid']}/4·자동차 {auto['valid']}/4·반대편 {counter['valid']}/4"
    if after_close:
        close_rows = ship_rows + defense_rows + auto_rows + counter_rows
        official = sum(r.get("source") == KIWOOM_CLOSE_DOC for r in close_rows)
        ls_official = sum(r.get("source") == LS_CLOSE_DOC for r in close_rows)
        coverage += f" / 증권사 정규장 종가 키움 {official}·LS {ls_official}/16"
    if not fx["source_time_verified"]:
        coverage += " / 환율 원천시각 미제공(동일일 조회 표본)"
    if gap > 30:
        coverage += f" / 정규장 표본 공백 최대 {gap:.0f}분"
    if fx.get("basis_error"):
        coverage += " / 직전 종가 미확인 — 강한 일간 신호 판정 보류"

    ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if level > sent_level:
        ALERT_PATH.write_text(
            build_alert(now, fx, session_low, rebound_krw, rebound_pct, daily_krw, daily_pct,
                        kospi, ship_rows, defense_rows, auto_rows, counter_rows,
                        ship, defense, auto, counter, level)+"\n", encoding="utf-8")
        # Pending only: the existing shared workflow commits after Telegram ack.
        state["sent_level"] = level
        state["sent_weakening"] = False
        state["last_signal"] = {
            "time": now.isoformat(timespec="seconds"), "level": level,
            "session_low": session_low, "fx_value": float(fx["value"]),
            "rebound_krw": rebound_krw, "ship_relative": ship.get("relative"),
            "defense_relative": defense.get("relative"), "auto_relative": auto.get("relative"),
            "after_close": after_close,
        }
        decision = f"신규 로테이션 레벨 {level} 감지 — 전송 응답 대기"
    else:
        sig = state.get("last_signal") or {}
        reasons = _weakening_reason(fx, sig, ship, defense, auto) if sig and not state.get("sent_weakening") else []
        if reasons:
            ALERT_PATH.write_text(build_weakening_alert(now, fx, state, benchmark, ship, defense, auto, reasons)+"\n",
                                  encoding="utf-8")
            state["sent_weakening"] = True
            decision = "직전 로테이션 신호 약화 — 전송 응답 대기"
        elif any(g["valid"] < 3 for g in (ship, defense, auto)) or fx.get("basis_error"):
            decision = "신규 확정 신호 없음 — 일부 자료 검증 부족, 해당 조건 판정 보류"
        else:
            decision = "신규 상향 신호 없음"

    state["latest"] = {
        "checked_at": now.isoformat(timespec="seconds"),
        "market_phase": "장마감 후" if after_close else "정규장",
        "fx": fx, "session_low": session_low, "rebound_krw": rebound_krw,
        "rebound_pct": rebound_pct, "daily_krw": daily_krw, "daily_pct": daily_pct,
        "kospi_pct": benchmark, "ship": ship, "defense": defense,
        "auto": auto, "counter": counter,
        "kospi_source_observed_at": kospi.get("source_observed_at"),
        "kospi_source": kospi.get("source"),
        "kospi_quote_basis": kospi.get("quote_basis"),
        "kospi_session_close_at": kospi.get("session_close_at"),
        "quote_sources": {r["code"]: {k: r.get(k) for k in ("source", "source_date", "session_close_at", "source_observed_at", "error")}
                          for r in ship_rows + defense_rows + auto_rows + counter_rows},
    }
    partial = any(g["valid"] < 3 for g in (ship, defense, auto)) or bool(fx.get("basis_error")) or session_low is None
    state["last_attempt"] = {"checked_at": now.isoformat(timespec="seconds"),
                             "quality": "partial" if partial else "validated", "decision": decision}
    save_pending(state)
    write_status(now, decision+" / "+coverage)
    print("fx_sector_rotation="+decision+" / "+coverage)
    return 2 if partial else 0


def _requested_close_probe(now: dt.datetime) -> bool:
    # One explicitly marked push on a non-trading day only; no alerts or state
    # writes. Scheduled executions never invoke this historical read-only probe.
    if os.getenv("GITHUB_EVENT_NAME") != "push" or session_bounds(now.date()) is not None:
        return False
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        return "[fx-rotation-close-probe]" in str((event.get("head_commit") or {}).get("message") or "")
    except (OSError, ValueError, KeyError, AttributeError):
        return False


def _close_probe(now: dt.datetime) -> bool:
    day = dt.date.fromisoformat(_previous_session_day(now.date()))
    bounds = session_bounds(day)
    if bounds is None:
        raise SourceFailure("과거 정규장 달력 확인 실패")
    try:
        index = _fetch_kospi_close(bounds)
        print(f"fx_sector_rotation_close_probe_index=ok date={day} pct={index['change_pct']:+.2f}")
    except Exception as exc:
        print("fx_sector_rotation_close_probe_index=unavailable reason=" + _failure_detail(exc))
        index = None
    rows = []
    for name, code in SHIPBUILDING + DEFENSE + AUTOMOTIVE + COUNTER:
        try:
            row = _fetch_regular_stock_close(name, code, bounds)
            rows.append(row)
            print(f"fx_sector_rotation_close_probe_stock={code} ok price={row['price']:.0f} pct={row['change_pct']:+.4f} source={row['quote_basis']}")
        except Exception as exc:
            print(f"fx_sector_rotation_close_probe_stock={code} unavailable reason={_failure_detail(exc)}")
    kiwoom_count = sum(r.get("source") == KIWOOM_CLOSE_DOC for r in rows)
    ls_count = sum(r.get("source") == LS_CLOSE_DOC for r in rows)
    print(f"fx_sector_rotation_close_probe=history_only date={day} index={int(index is not None)} stocks={len(rows)}/16 kiwoom={kiwoom_count} ls={ls_count}; no Telegram or state writes")
    if index is not None and len(rows) == 16:
        for label, items in (("조선", SHIPBUILDING), ("방산", DEFENSE), ("자동차", AUTOMOTIVE), ("반대편", COUNTER)):
            codes = {code for _, code in items}
            stats = group_stats([r for r in rows if r["code"] in codes], index["change_pct"])
            print(f"fx_sector_rotation_close_probe_group={label} avg={stats['avg']:+.4f} relative={stats['relative']:+.4f} valid={stats['valid']}")
        return True
    return False


def main() -> int:
    ALERT_PATH.unlink(missing_ok=True)
    PENDING_PATH.unlink(missing_ok=True)
    now = dt.datetime.now(KST)
    try:
        _regression_checks()
        if _requested_close_probe(now):
            return 0 if _close_probe(now) else 2
        return _run()
    except Exception as exc:
        # No fresh/confirmed state or alert on source failure or invalid
        # state; avoid suppressing other alerts in the shared workflow.
        ALERT_PATH.unlink(missing_ok=True)
        PENDING_PATH.unlink(missing_ok=True)
        label = "자체 회귀검사 실패" if isinstance(exc, AssertionError) else "자료 조회·검증 또는 상태 처리 실패"
        detail = _failure_detail(exc)
        write_status(now, f"{label} ({detail}) — 로테이션 판정 보류, 기존 상태 보존")
        print(f"fx_sector_rotation=unavailable reason={detail}; no delivery or state update")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

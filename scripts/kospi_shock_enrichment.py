#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
BASE = "https://openapi.ls-sec.co.kr:8080"
OUT = Path("out/kospi_shock_enrichment_latest.json")
KOSDAQ_OUT = Path("out/kosdaq_shock_enrichment_latest.json")
PROBE = Path("out/kospi_shock_enrichment_probe.json")
INDUSTRY_FLOW = Path(os.getenv("KOSPI_INDUSTRY_FLOW_PATH", "out/kospi_industry_flow.jsonl"))

_LAST_CALL: dict[str, float] = {}
_ONE_SEC_TR = {
    "t8424", "t1516", "t8409", "t1532", "t1537",
    "t1636", "t1637", "t8452", "t1904",
}


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


def _display_name(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if re.fullmatch(r"[가-힣 ]+", text):
        text = text.replace(" ", "")
    return text


def _is_actionable_theme(name: str) -> bool:
    compact = name.replace(" ", "").lower()
    blocked = ("지수", "index", "value-up", "valueup", "밸류업")
    return bool(compact) and not any(x in compact for x in blocked)


def _pace(tr: str) -> None:
    if tr not in _ONE_SEC_TR:
        return
    prev = _LAST_CALL.get(tr, 0.0)
    wait = 1.08 - (time.time() - prev)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[tr] = time.time()


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
        _pace(tr)
        try:
            r = requests.post(
                BASE + path,
                headers={
                    "content-type": "application/json; charset=utf-8",
                    "authorization": "Bearer " + token,
                    "tr_cd": tr,
                    "tr_cont": "N",
                    "tr_cont_key": "",
                },
                data=json.dumps(body),
                timeout=25,
            )
        except requests.RequestException as exc:
            last_error = f"{tr} transport error: {type(exc).__name__}: {exc}"
            if attempt < 4:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        text = r.text or ""
        # LS 임시 게이트웨이 장애는 /503.html로 라우팅한 뒤 HTTP 404로 반환될 수 있다.
        # 존재하지 않는 정상 API 경로의 진짜 404와 구분하여 임시 장애만 재시도한다.
        gateway_503_as_404 = r.status_code == 404 and "/503.html" in text
        retryable_http = r.status_code in {429, 500, 502, 503, 504} or gateway_503_as_404
        if not r.ok:
            last_error = f"{tr} HTTP {r.status_code}: {text[:300]}"
            if attempt < 4 and retryable_http:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error)
        try:
            data = r.json()
        except Exception as exc:
            last_error = f"{tr} invalid JSON: {text[:200]}"
            if attempt < 4:
                time.sleep(min(8.0, 0.8 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error) from exc
        code = str(data.get("rsp_cd") or "")
        if code and code not in {"00000", "0000"}:
            last_error = f"{tr} rejected {code}: {data.get('rsp_msg')}"
            if attempt < 4 and code == "IGW00201":
                time.sleep(min(8.0, 1.0 * (2 ** attempt)))
                continue
            raise RuntimeError(last_error)
        return data
    raise RuntimeError(last_error or f"{tr} failed")


def _rows(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = data.get(key) or []
    if isinstance(rows, dict):
        rows = [rows]
    return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []


def _epoch(date_value: Any, time_value: Any) -> float | None:
    ds = "".join(ch for ch in str(date_value or "") if ch.isdigit())
    ts = "".join(ch for ch in str(time_value or "") if ch.isdigit())
    if len(ts) < 4:
        return None
    ts = (ts + "000000")[:6]
    if len(ds) != 8:
        ds = dt.datetime.now(KST).strftime("%Y%m%d")
    try:
        when = dt.datetime.strptime(ds + ts, "%Y%m%d%H%M%S").replace(tzinfo=KST)
        return when.timestamp()
    except Exception:
        return None


def _nearest_row(
    rows: list[dict[str, Any]],
    target_ts: float,
    date_key: str = "date",
    time_key: str = "time",
) -> tuple[dict[str, Any], float, float] | None:
    vals: list[tuple[dict[str, Any], float, float]] = []
    for row in rows:
        ts = _epoch(row.get(date_key), row.get(time_key))
        if ts is None:
            continue
        vals.append((row, ts, abs(ts - target_ts)))
    return min(vals, key=lambda x: x[2]) if vals else None


def _aligned_prior_row(
    rows: list[dict[str, Any]],
    target_ts: float,
    max_age_sec: float = 90.0,
    date_key: str = "date",
    time_key: str = "time",
) -> tuple[dict[str, Any], float, float] | None:
    """구간 판정에는 미래 표본을 사용하지 않고, 오래된 분봉도 배제한다."""
    candidates: list[tuple[dict[str, Any], float, float]] = []
    for row in rows:
        ts = _epoch(row.get(date_key), row.get(time_key))
        if ts is None or ts > target_ts:
            continue
        age = target_ts - ts
        if age <= max_age_sec:
            candidates.append((row, ts, age))
    return min(candidates, key=lambda x: x[2]) if candidates else None


def direct_industry_interval(
    start_ts: float,
    end_ts: float,
    investor: str | None,
    path: Path | None = None,
    max_gap_sec: float = 30.0,
    market: str = "KOSPI",
) -> dict[str, Any]:
    p = path or INDUSTRY_FLOW
    if not investor:
        return {"available": False, "reason": "현물 최다매도 주체 없음", "rows": []}
    if not p.exists():
        return {"available": False, "reason": "통합 UBM 수급 파일 없음", "rows": []}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("investor") or "") != investor:
                continue
            code = str(row.get("upcode") or "").strip()
            # 코스닥 직접 업종은 3xx 업종만 인정한다. KOSPI 0xx는 혼합 금지.
            if market == "KOSDAQ" and not (len(code) == 3 and code.startswith("3")):
                continue
            if market == "KOSPI" and len(code) == 3 and code.startswith("3"):
                continue
            ts = fnum(row.get("ts"))
            msval = fnum(row.get("msval"))
            if not code or ts is None or msval is None:
                continue
            grouped[code].append(row)
    except Exception as exc:
        return {
            "available": False,
            "reason": f"통합 UBM 파일 읽기 실패: {type(exc).__name__}: {exc}",
            "rows": [],
        }

    out = []
    for code, rows in grouped.items():
        rows.sort(key=lambda x: float(x.get("ts") or 0))
        before_start = [x for x in rows if float(x.get("ts") or 0) <= start_ts]
        before_end = [x for x in rows if float(x.get("ts") or 0) <= end_ts]
        if not before_start or not before_end:
            continue
        a = before_start[-1]
        b = before_end[-1]
        a_ts = float(a.get("ts") or 0)
        b_ts = float(b.get("ts") or 0)
        start_gap = start_ts - a_ts
        end_gap = end_ts - b_ts
        if start_gap < 0 or end_gap < 0 or start_gap > max_gap_sec or end_gap > max_gap_sec:
            continue
        av = fnum(a.get("msval"))
        bv = fnum(b.get("msval"))
        if av is None or bv is None:
            continue
        out.append({
            "code": code,
            "name": _display_name(b.get("industry") or a.get("industry") or code),
            "investor": investor,
            "delta": bv - av,
            "start_value": av,
            "end_value": bv,
            "start_gap_sec": start_gap,
            "end_gap_sec": end_gap,
            "start_time": fmt_clock(a_ts),
            "end_time": fmt_clock(b_ts),
        })

    out.sort(key=lambda x: float(x.get("delta") or 0))
    return {
        "available": bool(out),
        "reason": None if out else f"통합 UBM 기준점 {max_gap_sec:.0f}초 정렬 충족 업종 없음",
        "investor": investor,
        "rows": out,
        "covered_industries": len(out),
        "observed_industries": len(grouped),
        "source": "LS UBM 통합 업종별투자자별매매현황",
        "unit_note": "msval 누적 원값의 사건 시작→저점 변화. 임의 원화 환산 없음.",
    }


def stock_master(token: str) -> list[dict[str, Any]]:
    data = ls_post(
        token, "/stock/etc", "t8436",
        {"t8436InBlock": {"gubun": "1"}},
    )
    return _rows(data, "t8436OutBlock")


def industry_master(token: str, market: str = "KOSPI") -> list[dict[str, Any]]:
    best: list[dict[str, Any]] = []
    errors = []
    groups = ("2", "0", "1") if market == "KOSDAQ" else ("1", "0")
    for gubun in groups:
        try:
            data = ls_post(
                token, "/indtp/market-data", "t8424",
                {"t8424InBlock": {"gubun1": gubun}},
            )
            rows = _rows(data, "t8424OutBlock")
            if market == "KOSDAQ":
                rows = [row for row in rows if str(row.get("upcode") or "").startswith("3")]
            else:
                rows = [row for row in rows if not str(row.get("upcode") or "").startswith("3")]
            if len(rows) > len(best):
                best = rows
            if rows:
                break
        except Exception as exc:
            errors.append(str(exc))
    if not best:
        raise RuntimeError(f"t8424 {market} industry master unavailable: " + " | ".join(errors))
    return best


def _is_real_industry(name: str, code: str) -> bool:
    n = name.replace(" ", "")
    if not code or code == "001":
        return False
    blocked = (
        "코스피", "KOSPI", "대형주", "중형주", "소형주", "배당", "우선주",
        "200", "100", "50", "시가총액", "스타일", "저변동", "고배당",
        "제조업", "종합",
    )
    return not any(x in n for x in blocked)


def industry_members(token: str, upcode: str) -> list[dict[str, Any]]:
    last_error = ""
    for gubun in ("0", "1"):
        try:
            data = ls_post(
                token, "/indtp/market-data", "t1516",
                {"t1516InBlock": {"upcode": upcode, "gubun": gubun, "shcode": ""}},
            )
            rows = _rows(data, "t1516OutBlock1")
            if rows:
                return rows
        except Exception as exc:
            last_error = str(exc)
    if last_error:
        raise RuntimeError(last_error)
    return []


def map_industries(
    token: str,
    target_codes: set[str],
    max_industries: int = 40,
    market: str = "KOSPI",
) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    mapping: dict[str, list[dict[str, str]]] = defaultdict(list)
    errors: list[str] = []
    industries = industry_master(token, market=market)
    filtered = []
    for row in industries:
        name = _display_name(row.get("hname"))
        code = str(row.get("upcode") or "").strip()
        if _is_real_industry(name, code) and (
            (market == "KOSDAQ" and len(code) == 3 and code.startswith("3"))
            or (market == "KOSPI" and len(code) == 3 and not code.startswith("3"))
        ):
            filtered.append((name, code))
    for name, code in filtered[:max_industries]:
        try:
            members = industry_members(token, code)
        except Exception as exc:
            errors.append(f"{name}({code}): {type(exc).__name__}: {exc}")
            continue
        member_codes = {str(x.get("shcode") or "").strip() for x in members}
        hit = target_codes & member_codes
        for shcode in hit:
            mapping[shcode].append({"name": name, "code": code})
        if target_codes and all(mapping.get(code0) for code0 in target_codes):
            break
    return dict(mapping), errors


def fetch_stock_bars(token: str, shcode: str, exchgubun: str = "U") -> list[dict[str, Any]]:
    body = {
        "t8452InBlock": {
            "shcode": shcode,
            "ncnt": 1,
            "qrycnt": 240,
            "nday": "1",
            "sdate": " ",
            "stime": "",
            "edate": "99999999",
            "etime": "",
            "cts_date": " ",
            "cts_time": "",
            "comp_yn": "N",
            "exchgubun": exchgubun,
        }
    }
    data = ls_post(token, "/stock/chart", "t8452", body)
    return _rows(data, "t8452OutBlock1")


def stock_interval_price(
    token: str,
    shcode: str,
    start_ts: float,
    end_ts: float,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # 검증 경로에서는 같은 요청의 원자료를 재사용해 조회 시차·서로 다른 봉 집합을 방지한다.
    if rows is None:
        rows = fetch_stock_bars(token, shcode, "U")
    a = _aligned_prior_row(rows, start_ts)
    b = _aligned_prior_row(rows, end_ts)
    if not a or not b or a[1] >= b[1]:
        return {"available": False, "error": "1분봉 기준점 누락·시차 초과·시각 역전"}
    ap = fnum(a[0].get("close"))
    bp = fnum(b[0].get("close"))
    return {
        "available": ap is not None and bp is not None,
        "start_price": ap,
        "end_price": bp,
        "return_pct": pct(ap, bp),
        "start_time": fmt_clock(a[1]),
        "end_time": fmt_clock(b[1]),
        "start_gap_sec": a[2],
        "end_gap_sec": b[2],
    }


def program_rank_candidates(token: str, limit: int = 18) -> tuple[list[dict[str, Any]], list[str]]:
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    trials = [
        ("0", "1", "0"),
        ("0", "1", "1"),
        ("1", "1", "0"),
        ("1", "1", "1"),
        ("0", "1", "2"),
    ]
    for gubun, gubun1, gubun2 in trials:
        body = {
            "t1636InBlock": {
                "gubun": gubun,
                "gubun1": gubun1,
                "gubun2": gubun2,
                "shcode": "",
                "cts_idx": 0,
                "exchgubun": "U",
            }
        }
        try:
            data = ls_post(token, "/stock/program", "t1636", body)
            rows = _rows(data, "t1636OutBlock1")
        except Exception as exc:
            errors.append(f"{gubun}/{gubun1}/{gubun2}: {type(exc).__name__}: {exc}")
            continue
        for row in rows:
            code = str(row.get("shcode") or "").strip()
            if not re.fullmatch(r"\d{6}", code):
                continue
            old = found.get(code)
            cur = fnum(row.get("svalue"))
            if old is None:
                found[code] = dict(row)
            else:
                oldv = fnum(old.get("svalue"))
                if cur is not None and (oldv is None or cur < oldv):
                    found[code] = dict(row)
        negatives = [r for r in found.values() if (fnum(r.get("svalue")) or 0) < 0]
        if len(negatives) >= limit:
            break
    rows = list(found.values())
    rows.sort(key=lambda r: fnum(r.get("svalue")) if fnum(r.get("svalue")) is not None else 10**30)
    return rows[: max(limit * 2, limit)], errors


def program_interval(
    token: str,
    shcode: str,
    start_ts: float,
    end_ts: float,
) -> dict[str, Any]:
    today = dt.datetime.fromtimestamp(end_ts, KST).strftime("%Y%m%d")
    bodies = [
        {
            "t1637InBlock": {
                "gubun1": "1",
                "gubun2": "0",
                "shcode": shcode,
                "date": today,
                "time": "",
                "cts_idx": 9999,
                "exchgubun": "U",
            }
        },
        {
            "t1637InBlock": {
                "gubun1": "1",
                "gubun2": "0",
                "shcode": shcode,
                "date": "",
                "time": "",
                "cts_idx": 9999,
                "exchgubun": "U",
            }
        },
    ]
    rows: list[dict[str, Any]] = []
    error = ""
    for body in bodies:
        try:
            data = ls_post(token, "/stock/program", "t1637", body)
            rows = _rows(data, "t1637OutBlock1")
            if rows:
                break
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    if not rows:
        return {"available": False, "error": error or "no rows"}
    a = _aligned_prior_row(rows, start_ts)
    b = _aligned_prior_row(rows, end_ts)
    if not a or not b or a[1] >= b[1]:
        return {"available": False, "error": "프로그램 구간 표본 90초 정렬 미충족·시각 역전"}
    av = fnum(a[0].get("svalue"))
    bv = fnum(b[0].get("svalue"))
    if av is None or bv is None:
        return {"available": False, "error": "svalue missing"}
    return {
        "available": True,
        "program_delta": bv - av,
        "start_value": av,
        "end_value": bv,
        "start_time": fmt_clock(a[1]),
        "end_time": fmt_clock(b[1]),
        "start_gap_sec": a[2],
        "end_gap_sec": b[2],
    }


def stock_themes(token: str, shcode: str) -> list[dict[str, str]]:
    data = ls_post(
        token, "/stock/sector", "t1532",
        {"t1532InBlock": {"shcode": shcode}},
    )
    out = []
    for row in _rows(data, "t1532OutBlock"):
        name = _display_name(row.get("tmname"))
        code = str(row.get("tmcode") or "").strip()
        if name:
            out.append({"name": name, "code": code})
    return out


def industry_index_interval(
    token: str,
    upcode: str,
    start_ts: float,
    end_ts: float,
) -> dict[str, Any]:
    body = {
        "t8409InBlock": {
            "shcode": upcode,
            "ncnt": 1,
            "qrycnt": 240,
            "nday": "1",
            "sdate": " ",
            "stime": "",
            "edate": "99999999",
            "etime": "",
            "cts_date": " ",
            "cts_time": "",
            "comp_yn": "N",
        }
    }
    data = ls_post(token, "/indtp/chart", "t8409", body)
    rows = _rows(data, "t8409OutBlock1")
    a = _aligned_prior_row(rows, start_ts)
    b = _aligned_prior_row(rows, end_ts)
    if not a or not b or a[1] >= b[1]:
        return {"available": False, "error": "업종지수 1분봉 기준점 누락·시차 초과·시각 역전"}
    av = fnum(a[0].get("close"))
    bv = fnum(b[0].get("close"))
    return {
        "available": av is not None and bv is not None,
        "start": av,
        "end": bv,
        "return_pct": pct(av, bv),
        "start_gap_sec": a[2],
        "end_gap_sec": b[2],
    }


def etf_master(token: str) -> list[dict[str, Any]]:
    return [
        x for x in stock_master(token)
        if str(x.get("etfgubun") or "") == "1"
        and re.fullmatch(r"\d{6}", str(x.get("shcode") or "").strip())
    ]


_STOPWORDS = {
    "테마", "관련", "지수", "업종", "코스피", "KOSPI", "그룹", "대표", "주요",
    "KODEX", "TIGER", "RISE", "ACE", "SOL", "PLUS", "HANARO", "KOSEF",
    "TIMEFOLIO", "WON", "KIWOOM", "FOCUS", "UNICORN", "1Q",
}
_ETF_EXCLUDE = ("인버스", "레버리지", "2X", "선물", "채권", "머니", "단기", "커버드콜", "TRF")


def _theme_keywords(names: list[str]) -> list[str]:
    out: set[str] = set()
    synonyms = {
        "전기전자": ["반도체", "IT", "정보기술"],
        "운수장비": ["자동차", "조선", "방산"],
        "화학": ["2차전지", "배터리", "화학"],
        "금융": ["금융", "은행", "증권", "보험"],
        "기계": ["기계", "로봇", "방산"],
        "전기가스": ["전력", "전기", "원전", "에너지"],
        "의약품": ["바이오", "헬스케어", "의약"],
        "서비스": ["인터넷", "소프트웨어", "AI"],
        "통신": ["통신", "5G"],
    }
    for name in names:
        n = re.sub(r"[^\w가-힣]+", " ", name).strip()
        for tok in n.split():
            if len(tok) >= 2 and tok not in _STOPWORDS:
                out.add(tok)
        compact = name.replace(" ", "")
        for key, vals in synonyms.items():
            if key in compact:
                out.update(vals)
    return sorted(out, key=lambda x: (-len(x), x))


def select_etfs(
    master: list[dict[str, Any]],
    keywords: list[str],
    limit: int = 8,
) -> list[dict[str, Any]]:
    scored = []
    for row in master:
        name = str(row.get("hname") or "").strip()
        if any(x in name for x in _ETF_EXCLUDE):
            continue
        score = sum(3 if kw in name else 0 for kw in keywords)
        if score <= 0:
            continue
        scored.append((score, name, row))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [dict(x[2]) for x in scored[:limit]]


def etf_pdf_overlap(
    token: str,
    etf_code: str,
    stock_codes: set[str],
) -> dict[str, Any]:
    today = dt.datetime.now(KST).strftime("%Y%m%d")
    body = {
        "t1904InBlock": {
            "shcode": etf_code,
            "date": today,
            "sgb": "1",
            "exchgubun": "U",
        }
    }
    try:
        data = ls_post(token, "/stock/etf", "t1904", body)
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    rows = _rows(data, "t1904OutBlock1")
    overlap = []
    weight_sum = 0.0
    for row in rows:
        code = str(row.get("shcode") or "")[:6]
        if code not in stock_codes:
            continue
        w = fnum(row.get("weight")) or 0.0
        weight_sum += w
        overlap.append({
            "code": code,
            "name": str(row.get("hname") or "").strip(),
            "weight": w,
        })
    overlap.sort(key=lambda x: -float(x.get("weight") or 0))
    return {"available": True, "overlap_weight": weight_sum, "overlap": overlap[:5]}


def _fmt_program(v: Any) -> str:
    n = fnum(v)
    return "확인 불가" if n is None else f"{n:+,.0f}"


def confirmed_interval_sellers(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """장중 후보가 아니라 사건구간에 유효하게 검증된 프로그램 순매도 종목만 선택."""
    matches = [
        row for row in stocks
        if (row.get("program") or {}).get("available")
        and (fnum((row.get("program") or {}).get("program_delta")) or 0.0) < 0
    ]
    return sorted(matches, key=lambda row: float(row["program"]["program_delta"]))


def _fmt_pct(v: Any) -> str:
    n = fnum(v)
    return "확인 불가" if n is None else f"{n:+.2f}%"


def _enrichment_visible_length(value: str) -> int:
    """Telegram HTML 해석 후 가시문자 수: HTML 중간 절단 방지."""
    return len(html.unescape(re.sub(r"<[^>]*>", "", value)))


def render_enrichment_summary(raw: dict[str, Any]) -> str:
    """정밀 원자료는 그대로 보존하고 알림은 중복 없이 핵심순으로 출력한다."""
    event = raw.get("event") or {}
    market = event.get("market_attribution") or {}
    stocks = raw.get("stocks") or []
    industries = raw.get("industries") or []
    themes = raw.get("themes") or []
    etfs = raw.get("etfs") or []
    by_actor = raw.get("direct_industry_by_actor") or {}
    proxy = raw.get("cap_drop_proxy") or []
    errors = raw.get("errors") or []
    esc = lambda x: html.escape(str(x), quote=False)
    event_time = str(raw.get("generated_at_kst") or "").replace("T", " ")[:19]
    start = esc(event.get("start_kst") or "확인 불가")
    low = esc(event.get("low_kst") or "확인 불가")

    # 사건구간에 정렬된 업종·종목·ETF 자료가 하나도 없으면 다섯 개의 빈 목록을
    # 보낸 것처럼 보이게 하지 않는다. 실패 자료와 원인은 기존 raw에 그대로 보존.
    has_direct = any(
        (fnum((raw.get("market_spot_deltas") or {}).get(actor)) or 0) < 0
        and any((fnum(item.get("delta")) or 0) < 0
                for item in (by_actor.get(actor) or {}).get("rows", []))
        for actor in ("외국인", "기관", "개인")
    )
    has_etf = any((item.get("price") or {}).get("available") for item in etfs)
    if not (has_direct or industries or stocks or themes or has_etf or proxy):
        if market.get("available") and market.get("spot_leader"):
            market_line = (
                "• 현물·선물 시장 매도주체: "
                + esc(market.get("spot_leader")) + " / "
                + esc(market.get("futures_leader") or "확인 불가")
                + " · 해당 사건 시장 수급 판정만 유지"
            )
        else:
            market_line = "• 시장 매도주체: 수급 시각 정렬 미충족 · 판정 보류"
        return "\n".join([
            "🔎 <b>코스피 급락 · 정밀분해 자료 보류</b>",
            f"<code>{esc(event_time)} KST</code>",
            f"• 구간 <b>{start} → {low}</b>",
            market_line,
            "• 사건구간 업종·종목·테마·ETF 유효 자료 없음 — 순위·순매도액을 추정하지 않습니다.",
            ("• 원자료 조회 오류 있음 · GitHub Actions 아티팩트에 기록"
             if errors else "• 자료 시각 정렬·후보 검증 미충족 · GitHub Actions 아티팩트에 기록"),
            "• LS 프로그램·UBM 원값은 억원으로 임의 환산하지 않습니다.",
        ])

    def _render(stock_limit: int, theme_limit: int, etf_limit: int, direct_limit: int) -> str:
        lines = [
            "🔎 <b>코스피 급락 · 수급·업종 정밀분해</b>",
            f"<code>{esc(event_time)} KST</code>",
            f"• 구간 <b>{start} → {low}</b> · 현물·프로그램 통합 / 선물 별도",
        ]
        spot = esc(market.get("spot_leader") or "확인 불가")
        fut = esc(market.get("futures_leader") or "확인 불가")
        confidence = esc(market.get("confidence") or "판정 보류")
        verdict = str(market.get("verdict") or "")
        if not market.get("available"):
            lines.append("• <b>매도주체 판정 보류</b> · 사건구간 수급 정렬 부족")
        elif market.get("single_leader") and "보류" not in verdict:
            lines.append(f"• <b>매도 주도 후보: {spot}</b> · 확신도 {confidence}")
        else:
            lines.append(f"• 매도주체: 현물 {spot} / 선물 {fut} · 단일 주도자 보류")

        lines.extend(["", "<b>① 현물 직접 업종</b> <i>(UBM 원값·30초 정렬)</i>"])
        any_direct = False
        spot_block = (raw.get("market_spot_deltas") or {})
        for actor in ("외국인", "기관", "개인"):
            val = fnum(spot_block.get(actor))
            if val is None or val >= 0:
                continue
            block = by_actor.get(actor) or {}
            valid = [r for r in block.get("rows", []) if (fnum(r.get("delta")) or 0) < 0]
            if not valid:
                continue
            any_direct = True
            prefix = f"• {esc(actor)} {val:+,.0f}억원 → "
            entries = []
            for item in valid[:direct_limit]:
                age1, age2 = fnum(item.get("start_gap_sec")), fnum(item.get("end_gap_sec"))
                align = f" ({age1:.0f}/{age2:.0f}초)" if age1 is not None and age2 is not None else ""
                entries.append(f"{esc(item.get('name') or item.get('code') or '?')} {_fmt_program(item.get('delta'))}{align}")
            covered = block.get("covered_industries")
            observed = block.get("observed_industries")
            coverage = (
                f" [정렬 {covered}/{observed}업종]"
                if isinstance(covered, int) and isinstance(observed, int) and observed > 0
                else ""
            )
            lines.append(prefix + "; ".join(entries) + coverage)
        if not any_direct:
            lines.append("• 업종 직접 수급: <b>정렬 충족 표본 없음 · 판정 보류</b>")

        lines.extend(["", "<b>② 하락 업종</b> <i>(업종 등락 / 후보 프로그램 합계·원값)</i>"])
        if industries:
            for ind in industries[:3]:
                ret = _fmt_pct((ind.get("price") or {}).get("return_pct"))
                members = "·".join(esc(v) for v in (ind.get("stocks") or [])[:3])
                lines.append(
                    f"• {esc(ind.get('name') or '?')} {ret} / {_fmt_program(ind.get('program_delta'))}"
                    + (f" · {members}" if members else "")
                )
        else:
            lines.append("• 구간 정렬을 충족한 업종 후보 없음")

        lines.extend(["", "<b>③ 프로그램 순매도 종목</b> <i>(LS 원값 / 구간 등락)</i>"])
        if stocks:
            for row in stocks[:stock_limit]:
                delta = (row.get("program") or {}).get("program_delta")
                ret = (row.get("price") or {}).get("return_pct")
                lines.append(f"• {esc(row.get('name') or row.get('code') or '?')} {_fmt_program(delta)} / {_fmt_pct(ret)}")
        else:
            lines.append("• 사건구간 순매도 검증 종목 없음")

        lines.extend(["", "<b>④ 겹치는 테마</b> <i>(후보 연결·중복 허용)</i>"])
        # 같은 구성·같은 원값의 테마는 한 행으로 묶는다.
        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        for th in themes[:theme_limit]:
            delta = fnum(th.get("program_delta"))
            member_key = tuple(str(v) for v in (th.get("stocks") or []))
            key = (delta, member_key)
            if key not in merged:
                merged[key] = {"names": [], "delta": delta, "stocks": member_key}
            merged[key]["names"].append(str(th.get("name") or "?"))
        for bucket in merged.values():
            names = "·".join(esc(x) for x in bucket["names"])
            members = "·".join(esc(x) for x in bucket["stocks"][:3])
            lines.append(f"• {names} {_fmt_program(bucket['delta'])}" + (f" · {members}" if members else ""))
        if not merged:
            lines.append("• 확인된 연결 테마 없음")

        lines.extend(["", "<b>⑤ ETF 구간 반응</b> <i>(가격 / 구성 겹침)</i>"])
        display_etfs = [x for x in etfs if (x.get("price") or {}).get("available")]
        if display_etfs:
            for item in display_etfs[:etf_limit]:
                overlap = fnum((item.get("overlap") or {}).get("overlap_weight"))
                suffix = f" · 구성 겹침 {overlap:.1f}%" if overlap is not None and overlap > 0 else ""
                lines.append(
                    f"• {esc(item.get('name') or item.get('code') or '?')} "
                    f"{_fmt_pct((item.get('price') or {}).get('return_pct'))}{suffix}"
                )
        else:
            lines.append("• 사건구간 ETF 가격 확인 불가")

        if proxy:
            ranks = " → ".join(esc(x.get("name") or x.get("code") or "?") for x in proxy[:3])
            lines.append(f"• 시총×낙폭 근사: {ranks}")

        lines.extend([
            "",
            "※ 프로그램·UBM 수치는 <b>LS 원값</b>으로 억원 환산·합산 금지. "
            "업종·종목은 상위 후보군, 테마는 중복, ETF 등락·구성 겹침은 자금 유출이 아닙니다.",
            "※ 시총×낙폭은 지수 기여도가 아닌 근사치. "
            + ("일부 자료 조회 실패 — 부분 검증." if errors else "표시 순위는 시간 정렬된 관측치 기준."),
        ])
        return "\n".join(lines)

    # 항목을 임의의 문자 위치에서 자르지 않는다. 우선순위를 유지한 단계별 구성.
    for limits in ((6, 4, 5, 3), (6, 3, 4, 2), (5, 2, 3, 2), (3, 1, 2, 1)):
        text = _render(*limits)
        if _enrichment_visible_length(text) <= 3800:
            return text
    # 극단적인 종목명 길이에서도 감시 자체가 조용히 실패하지 않도록 핵심만 보낸다.
    # 세부 숫자는 기존 아티팩트에 전량 남으며 문장·HTML을 중간에서 자르지 않는다.
    market = event.get("market_attribution") or {}
    brief = [
        "🔎 <b>코스피 급락 · 정밀분해 요약</b>",
        f"<code>{esc(event_time)} KST</code>",
        f"• 구간 <b>{start} → {low}</b>",
        "• 시장 판정: " + esc(market.get("verdict") or "수급 정렬 부족·판정 보류"),
        "• 상세 표시는 Telegram 글자 수를 초과하여 생략했습니다. 검증 원자료는 기존 GitHub Actions 아티팩트에 저장합니다.",
    ]
    result = "\n".join(brief)
    if _enrichment_visible_length(result) > 3800:
        raise ValueError("필수 시장 판정 텍스트가 Telegram 제한을 초과")
    return result


def build_enrichment(
    token: str,
    episode: dict[str, Any],
    attribution: dict[str, Any] | str | None = None,
) -> tuple[str, dict[str, Any]]:
    start_ts = float(episode["start_ts"])
    low_ts = float(episode["low_ts"])
    errors: list[str] = []
    att = attribution if isinstance(attribution, dict) else {}
    legacy_leader = str(attribution).strip() if isinstance(attribution, str) else ""
    spot_leader = str(att.get("spot_leader") or "").strip()
    futures_leader = str(att.get("futures_leader") or "").strip()
    confidence = str(att.get("confidence") or "").strip()
    verdict = str(att.get("verdict") or "").strip()
    single_leader = bool(
        att.get("available") and spot_leader and spot_leader == futures_leader
        and "보류" not in verdict
    )
    spot_block = att.get("spot") or {}
    negative_spot_actors = []
    for actor in ("외국인", "기관", "개인"):
        value = fnum(spot_block.get(actor))
        if value is not None and value < 0:
            negative_spot_actors.append((actor, value))
    negative_spot_actors.sort(key=lambda x: x[1])
    direct_industry_by_actor = {
        actor: direct_industry_interval(start_ts, low_ts, actor)
        for actor, _ in negative_spot_actors
    }
    direct_industry = (
        direct_industry_by_actor.get(spot_leader)
        if spot_leader else {"available": False, "reason": "현물 최다매도 주체 없음", "rows": []}
    )

    master_rows = stock_master(token)
    master = {str(x.get("shcode") or "").strip(): x for x in master_rows}
    rank_rows, rank_errors = program_rank_candidates(token, limit=14)
    errors.extend(rank_errors)

    candidates = []
    for row in rank_rows:
        code = str(row.get("shcode") or "").strip()
        if code not in master or str(master[code].get("etfgubun") or "") == "1":
            continue
        daily_program = fnum(row.get("svalue"))
        if daily_program is None or daily_program >= 0:
            continue
        candidates.append({
            "code": code,
            "name": str(row.get("hname") or master[code].get("hname") or code).strip(),
            "marketcap": fnum(row.get("sgta")),
            "daily_program": daily_program,
        })
        if len(candidates) >= 10:
            break

    stocks = []
    for c in candidates:
        code = c["code"]
        try:
            pgm = program_interval(token, code, start_ts, low_ts)
        except Exception as exc:
            pgm = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            price = stock_interval_price(token, code, start_ts, low_ts)
        except Exception as exc:
            price = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
        row = {**c, "program": pgm, "price": price}
        pd = fnum(pgm.get("program_delta")) if pgm.get("available") else None
        ret = fnum(price.get("return_pct")) if price.get("available") else None
        cap = fnum(c.get("marketcap"))
        row["pressure_score"] = (
            abs(pd) * max(0.0, -(ret or 0.0))
            if pd is not None and pd < 0 and ret is not None else 0.0
        )
        row["cap_drop_proxy"] = (
            cap * max(0.0, -(ret or 0.0)) / 100.0
            if cap is not None and ret is not None else None
        )
        stocks.append(row)

    # 장중 누적 매도 상위 후보라도 사건구간에서 실제 순매도·표본 정렬이
    # 확인되지 않으면 이번 사건의 '프로그램 매도 종목'으로 표시하지 않는다.
    usable = confirmed_interval_sellers(stocks)
    top_stocks = usable[:7]

    theme_sums: dict[str, dict[str, Any]] = {}
    for stock in top_stocks[:6]:
        try:
            themes = stock_themes(token, stock["code"])
        except Exception as exc:
            errors.append(f"theme {stock['code']}: {type(exc).__name__}: {exc}")
            themes = []
        stock["themes"] = themes
        delta = fnum(stock.get("program", {}).get("program_delta")) or 0.0
        for th in themes:
            name = th["name"]
            if not _is_actionable_theme(name):
                continue
            bucket = theme_sums.setdefault(name, {"program_delta": 0.0, "stocks": []})
            bucket["program_delta"] += delta
            bucket["stocks"].append(stock["name"])

    theme_rows = [
        {"name": name, **vals}
        for name, vals in theme_sums.items()
        if vals["program_delta"] < 0
    ]
    theme_rows.sort(key=lambda x: x["program_delta"])
    theme_rows = theme_rows[:5]

    target_codes = {x["code"] for x in top_stocks[:7]}
    industry_map, industry_errors = map_industries(token, target_codes)
    errors.extend(industry_errors)

    industry_buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for stock in top_stocks:
        delta = fnum(stock.get("program", {}).get("program_delta")) or 0.0
        for ind in industry_map.get(stock["code"], []):
            key = (ind["name"], ind["code"])
            bucket = industry_buckets.setdefault(
                key, {"name": ind["name"], "code": ind["code"], "program_delta": 0.0, "stocks": []}
            )
            bucket["program_delta"] += delta
            bucket["stocks"].append(stock["name"])

    industries = list(industry_buckets.values())
    industries.sort(key=lambda x: x["program_delta"])
    industries = industries[:4]
    for ind in industries:
        try:
            ind["price"] = industry_index_interval(token, ind["code"], start_ts, low_ts)
        except Exception as exc:
            ind["price"] = {"available": False}
            errors.append(f"industry price {ind['name']}: {type(exc).__name__}: {exc}")

    names_for_keywords = [x["name"] for x in theme_rows] + [x["name"] for x in industries]
    keywords = _theme_keywords(names_for_keywords)
    etfs = []
    try:
        etf_rows = etf_master(token)
        picks = select_etfs(etf_rows, keywords, limit=8)
        for row in picks:
            code = str(row.get("shcode") or "").strip()
            name = str(row.get("hname") or code).strip()
            try:
                price = stock_interval_price(token, code, start_ts, low_ts)
            except Exception as exc:
                price = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
            etfs.append({"code": code, "name": name, "price": price, "overlap": None})
        sold_codes = {x["code"] for x in top_stocks}
        for row in etfs[:4]:
            row["overlap"] = etf_pdf_overlap(token, row["code"], sold_codes)
        etfs.sort(
            key=lambda x: (
                -(fnum((x.get("overlap") or {}).get("overlap_weight")) or 0.0),
                fnum(x.get("price", {}).get("return_pct")) or 999.0,
            )
        )
    except Exception as exc:
        errors.append(f"ETF: {type(exc).__name__}: {exc}")

    cap_proxy = [x for x in top_stocks if fnum(x.get("cap_drop_proxy")) is not None]
    cap_proxy.sort(key=lambda x: -(fnum(x.get("cap_drop_proxy")) or 0.0))

    raw = {
        "generated_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "market_basis": "통합(U) 종목 체결·프로그램, 선물은 파생시장",
        "event": {
            "start_ts": start_ts,
            "start_kst": fmt_clock(start_ts),
            "low_ts": low_ts,
            "low_kst": fmt_clock(low_ts),
            "start_price": episode.get("start_price"),
            "low_price": episode.get("low_price"),
            "leader": spot_leader if single_leader else None,
            "market_attribution": {
                "available": bool(att.get("available")),
                "spot_leader": spot_leader or None,
                "futures_leader": futures_leader or None,
                "confidence": confidence or None,
                "verdict": verdict or None,
                "single_leader": single_leader,
            },
        },
        "stocks": top_stocks,
        "direct_industry": direct_industry,
        "direct_industry_by_actor": direct_industry_by_actor,
        "market_spot_deltas": spot_block,
        "industries": industries,
        "themes": theme_rows,
        "etfs": etfs[:6],
        "cap_drop_proxy": [
            {"code": x["code"], "name": x["name"], "value": x.get("cap_drop_proxy")}
            for x in cap_proxy[:5]
        ],
        "keywords": keywords,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return render_enrichment_summary(raw), raw




def kosdaq_stock_master(token: str) -> dict[str, dict[str, Any]]:
    """LS t8436 gubun=2에서 확인되는 코스닥 종목만 결과에 포함."""
    data=ls_post(token,"/stock/etc","t8436",{"t8436InBlock":{"gubun":"2"}})
    rows=_rows(data,"t8436OutBlock")
    out={
        str(row.get("shcode") or "").strip():row
        for row in rows
        if re.fullmatch(r"\d{6}",str(row.get("shcode") or "").strip())
        and str(row.get("etfgubun") or "") != "1"
    }
    if not out:
        raise RuntimeError("코스닥 t8436 gubun=2 종목 마스터 누락 — 타 시장 종목 대입 금지")
    return out


def kosdaq_program_candidates(token: str, max_rows: int = 28) -> tuple[list[dict[str, Any]], list[str]]:
    """t1636 구분 1=코스닥, 금액=1, 순매도상위=2. 다른 시장 순위와 합치지 않는다."""
    errors=[]
    found:dict[str,dict[str,Any]]={}
    for order in ("2","0","3"):
        body={"t1636InBlock":{
            "gubun":"1","gubun1":"1","gubun2":order,
            "shcode":"","cts_idx":0,"exchgubun":"U",
        }}
        try:
            data=ls_post(token,"/stock/program","t1636",body)
            rows=_rows(data,"t1636OutBlock1")
        except Exception as exc:
            errors.append(f"코스닥 t1636 순위 {order}: {type(exc).__name__}: {exc}")
            continue
        for row in rows:
            code=str(row.get("shcode") or "").strip()
            val=fnum(row.get("svalue"))
            if not re.fullmatch(r"\d{6}",code) or val is None or val>=0:
                continue
            previous=found.get(code)
            if previous is None or val < (fnum(previous.get("svalue")) or 0):
                found[code]=row
        if len(found)>=max_rows:
            break
    result=sorted(found.values(),key=lambda row:fnum(row.get("svalue")) or 0)
    return result[:max_rows],errors


def render_kosdaq_enrichment(raw: dict[str,Any]) -> str:
    """코스닥만의 5축 정밀분해. 유효하지 않은 항목은 보류하며 빈 나열을 피한다."""
    event=raw.get("event") or {}
    stocks=raw.get("stocks") or []
    industries=raw.get("industries") or []
    themes=raw.get("themes") or []
    etfs=raw.get("etfs") or []
    direct=raw.get("direct_industry_by_actor") or {}
    delta=(raw.get("market_spot_deltas") or {})
    esc=lambda x:html.escape(str(x),quote=False)
    kst=str(raw.get("generated_at_kst") or "").replace("T"," ")[:19]
    line=[
        "🔎 <b>코스닥 급락 · 수급·업종 정밀분해</b>",
        f"<code>{esc(kst)} KST</code>",
        f"• 구간 {esc(event.get('start_kst') or '?')} → {esc(event.get('low_kst') or '?')}",
    ]
    actor=event.get("spot_leader")
    if event.get("attribution_available") and actor:
        line.append(f"• 현물 최다매도: <b>{esc(actor)}</b> · 현물 단독 관측(선물 주도 판정 아님)")
    elif event.get("attribution_available"):
        line.append("• 코스닥 현물: 순매도 우위 주체 없음")
    else:
        line.append("• 현물 매도주체: 기준점 시간정렬 미충족 · 보류")

    matched=[]
    for k in ("외국인","기관","개인"):
        amt=fnum(delta.get(k))
        block=direct.get(k) or {}
        cand=[x for x in block.get("rows",[]) if (fnum(x.get("delta")) or 0)<0]
        if amt is not None and amt < 0 and cand:
            for x in cand[:1]:
                matched.append(f"{esc(k)} {amt:+,.0f}억원 → {esc(x.get('name') or '?')} {_fmt_program(x.get('delta'))}")
    line.extend(["","<b>① 현물 직접 업종</b> <i>(코스닥 3xx UBM 원값)</i>"])
    line.extend(f"• {x}" for x in matched[:3])
    if not matched:
        line.append("• 정렬된 코스닥 업종별 수급 없음 · 직접 판정 보류")
    line.extend(["","<b>② 하락 업종</b> <i>(등락 / 후보 프로그램 원값)</i>"])
    for ind in industries[:3]:
        members="·".join(esc(x) for x in (ind.get("stocks") or [])[:2])
        line.append(f"• {esc(ind.get('name') or '?')} {_fmt_pct((ind.get('price') or {}).get('return_pct'))} / {_fmt_program(ind.get('program_delta'))}"+(f" · {members}" if members else ""))
    if not industries:line.append("• 검증된 코스닥 업종 후보 없음")
    line.extend(["","<b>③ 프로그램 매도 후보 종목</b> <i>(LS 원값·사건구간)</i>"])
    for row in stocks[:5]:
        line.append(f"• {esc(row.get('name') or row.get('code') or '?')} {_fmt_program((row.get('program') or {}).get('program_delta'))} / {_fmt_pct((row.get('price') or {}).get('return_pct'))}")
    if not stocks:line.append("• 코스닥 종목별 프로그램 구간 검증 없음")
    line.extend(["","<b>④ 연결 테마</b> <i>(중복 허용)</i>"])
    for th in themes[:2]:
        line.append(f"• {esc(th.get('name') or '?')} {_fmt_program(th.get('program_delta'))} · {'·'.join(esc(x) for x in (th.get('stocks') or [])[:2])}")
    if not themes:line.append("• 검증된 연결 테마 없음")
    line.extend(["","<b>⑤ 관련 ETF 구간 반응</b> <i>(가격 / 구성 겹침)</i>"])
    valid_etfs=[e for e in etfs if (e.get("price") or {}).get("available")]
    for item in valid_etfs[:3]:
        overlap=fnum((item.get("overlap") or {}).get("overlap_weight"))
        tail=f" · 구성 겹침 {overlap:.1f}%" if overlap is not None and overlap>0 else ""
        line.append(f"• {esc(item.get('name') or '?')} {_fmt_pct((item.get('price') or {}).get('return_pct'))}{tail}")
    if not valid_etfs:line.append("• 사건구간 ETF 가격·구성 확인 불가")
    line.extend([
        "",
        "※ 코스닥 현물·코스닥 종목만으로 판정. 코스피200 선물 및 코스피 프로그램과 합산하지 않습니다.",
        "※ 업종·프로그램은 표본 후보이며 LS 원값은 원화로 임의 환산하지 않습니다. 테마는 중복, ETF 가격은 자금 유출이 아닙니다.",
    ])
    errors=raw.get("errors") or []
    if errors:line.append("※ 일부 원자료 조회 실패 · 미확인 항목은 제외했습니다.")
    text="\n".join(line)
    if _enrichment_visible_length(text)<=3800:
        return text
    # 토큰 수 문제가 생기면 검증된 핵심 외의 연결테마·ETF 항목만 순차 압축.
    for key in ("④ 연결 테마","⑤ 관련 ETF 구간 반응"):
        if _enrichment_visible_length(text)<=3800: break
        line=[x for x in line if key not in x]
        text="\n".join(line)
    if _enrichment_visible_length(text)>3800:
        text="\n".join(line[:15]+["※ 상세 검증값은 GitHub Actions 산출물에 보관됩니다."])
    if _enrichment_visible_length(text)>3800:
        raise ValueError("코스닥 정밀분해 메시지가 Telegram 최대 길이를 초과")
    return text


def build_kosdaq_enrichment(
    token: str, episode: dict[str,Any], attribution: dict[str,Any] | None=None,
) -> tuple[str,dict[str,Any]]:
    """기존 정밀분해 코드·아티팩트 경로를 재사용하되 시장 경계는 독립 검증."""
    if str(episode.get("market") or "")!="KOSDAQ":
        raise ValueError("코스닥 정밀분해에는 market=KOSDAQ 사건만 허용")
    start_ts=float(episode["start_ts"])
    low_ts=float(episode["low_ts"])
    if low_ts<=start_ts:
        raise ValueError("코스닥 사건 구간 시각 역전")
    att=attribution if isinstance(attribution,dict) else {}
    errors=[]
    spot_available = bool((att.get("channel_status") or {}).get("spot", {}).get("available", att.get("available")))
    spot=dict(att.get("spot") or {}) if spot_available else {}
    neg=[(k,fnum(spot.get(k))) for k in ("외국인","기관","개인")]
    neg=[(k,v) for k,v in neg if v is not None and v<0]
    neg.sort(key=lambda x:x[1])
    direct={
        k:direct_industry_interval(start_ts,low_ts,k,market="KOSDAQ")
        for k,_ in neg
    }
    candidates=[]
    try:
        master=kosdaq_stock_master(token)
        ranks,problems=kosdaq_program_candidates(token, max_rows=28)
        errors.extend(problems)
        for row in ranks:
            code=str(row.get("shcode") or "").strip()
            if code not in master:
                continue
            daily=fnum(row.get("svalue"))
            if daily is None or daily>=0:
                continue
            candidates.append({
                "code":code,"name":str(master[code].get("hname") or row.get("hname") or code).strip(),
                "market":"KOSDAQ","daily_program":daily,
                "marketcap":fnum(row.get("sgta")),
            })
            if len(candidates)>=7:break
    except Exception as exc:
        errors.append(f"KOSDAQ master/rank: {type(exc).__name__}: {exc}")
    stocks=[]
    for item in candidates:
        code=item["code"]
        try: pgm=program_interval(token,code,start_ts,low_ts)
        except Exception as exc: pgm={"available":False,"error":str(exc)}
        try: price=stock_interval_price(token,code,start_ts,low_ts)
        except Exception as exc: price={"available":False,"error":str(exc)}
        data={**item,"program":pgm,"price":price}
        if pgm.get("available") and (fnum(pgm.get("program_delta")) or 0)<0:
            stocks.append(data)
    stocks=confirmed_interval_sellers(stocks)[:6]
    themes_map={}
    for stock in stocks[:5]:
        try: ths=stock_themes(token,stock["code"])
        except Exception as exc:
            errors.append(f"theme {stock['code']}: {type(exc).__name__}: {exc}")
            ths=[]
        for th in ths:
            name=str(th.get("name") or "")
            if not _is_actionable_theme(name):continue
            row=themes_map.setdefault(name,{"name":name,"program_delta":0.0,"stocks":[]})
            row["program_delta"]+=float(stock["program"]["program_delta"])
            row["stocks"].append(stock["name"])
    themes=sorted(themes_map.values(),key=lambda x:x["program_delta"])[:3]
    target={x["code"] for x in stocks}
    industry_map={}
    if target:
        try:
            industry_map,mapping_errors=map_industries(token,target,max_industries=80,market="KOSDAQ")
            errors.extend(mapping_errors)
        except Exception as exc:
            errors.append(f"industry mapping: {type(exc).__name__}: {exc}")
    buckets={}
    for stock in stocks:
        for ind in industry_map.get(stock["code"],[]):
            key=(ind["name"],ind["code"])
            b=buckets.setdefault(key,{"name":ind["name"],"code":ind["code"],"program_delta":0.0,"stocks":[]})
            b["program_delta"]+=float(stock["program"]["program_delta"])
            b["stocks"].append(stock["name"])
    industries=sorted(buckets.values(),key=lambda x:x["program_delta"])[:3]
    for ind in industries:
        try: ind["price"]=industry_index_interval(token,ind["code"],start_ts,low_ts)
        except Exception as exc:
            errors.append(f"industry price {ind['code']}: {type(exc).__name__}: {exc}")
            ind["price"]={"available":False}
    etfs=[]
    if target:
        try:
            keywords=_theme_keywords([x["name"] for x in themes+industries])
            picks=select_etfs(etf_master(token),keywords,limit=5)
            for row in picks:
                code=str(row.get("shcode") or "").strip()
                try: price=stock_interval_price(token,code,start_ts,low_ts)
                except Exception as exc:
                    price={"available":False,"error":str(exc)}
                etfs.append({"name":str(row.get("hname") or code).strip(),
                             "code":code,"price":price,"overlap":None})
            for e in etfs[:3]:
                e["overlap"]=etf_pdf_overlap(token,e["code"],target)
            etfs.sort(key=lambda x:-(fnum((x.get("overlap") or {}).get("overlap_weight")) or 0))
        except Exception as exc:
            errors.append(f"KOSDAQ ETF: {type(exc).__name__}: {exc}")
    raw={
        "generated_at_kst":dt.datetime.now(KST).isoformat(timespec="seconds"),
        "market_basis":"KOSDAQ t8436 gubun=2 / t1636 gubun=1 / t1602 현물 / UBM 3xx",
        "event":{
            "market":"KOSDAQ","start_ts":start_ts,"low_ts":low_ts,
            "start_kst":fmt_clock(start_ts),"low_kst":fmt_clock(low_ts),
            "spot_leader":att.get("leader") or (min(neg,key=lambda x:x[1])[0] if neg else None),
            "attribution_available":spot_available,
            "market_attribution":att,
        },
        "market_spot_deltas":spot,
        "direct_industry_by_actor":direct,
        "stocks":stocks,"industries":industries,"themes":themes,"etfs":etfs,
        "candidate_count":len(candidates),"validated_stock_count":len(stocks),
        "errors":errors,
    }
    KOSDAQ_OUT.parent.mkdir(parents=True,exist_ok=True)
    KOSDAQ_OUT.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return render_kosdaq_enrichment(raw),raw


def latest_kospi_episode(token: str, minutes: int = 10) -> dict[str, Any]:
    body = {
        "t8409InBlock": {
            "shcode": "001", "ncnt": 1, "qrycnt": 400, "nday": "1",
            "sdate": " ", "stime": "", "edate": "99999999", "etime": "",
            "cts_date": " ", "cts_time": "", "comp_yn": "N",
        }
    }
    data = ls_post(token, "/indtp/chart", "t8409", body)
    rows = _rows(data, "t8409OutBlock1")
    timed = []
    for row in rows:
        ts = _epoch(row.get("date"), row.get("time"))
        close = fnum(row.get("close"))
        if ts is not None and close is not None:
            timed.append((ts, close))
    if len(timed) < 2:
        raise RuntimeError("KOSPI intraday rows unavailable for smoke window")
    timed.sort()
    end_ts, end_price = timed[-1]
    target = end_ts - minutes * 60
    start_ts, start_price = min(timed, key=lambda x: abs(x[0] - target))
    if start_ts >= end_ts:
        raise RuntimeError("invalid KOSPI smoke window")
    low_ts, low_price = min(
        ((ts, price) for ts, price in timed if start_ts <= ts <= end_ts),
        key=lambda x: x[1],
    )
    # 정밀분해 API 경로 검증이 목적이므로 종료시각을 저점으로 사용하되,
    # 저점이 시작과 같으면 마지막 시각으로 넓힌다.
    if low_ts <= start_ts:
        low_ts, low_price = end_ts, end_price
    return {
        "start_ts": start_ts,
        "start_price": start_price,
        "low_ts": low_ts,
        "low_price": low_price,
    }


def run_smoke(token: str) -> dict[str, Any]:
    episode = latest_kospi_episode(token, 10)
    text, detail = build_enrichment(
        token, episode,
        {"available": True, "spot_leader": "외국인", "futures_leader": "외국인",
         "confidence": "높음", "verdict": "외국인: 현물·선물 모두 최다 매도",}
    )
    summary = {
        "episode": detail.get("event"),
        "stock_count": len(detail.get("stocks") or []),
        "industry_count": len(detail.get("industries") or []),
        "theme_count": len(detail.get("themes") or []),
        "etf_count": len(detail.get("etfs") or []),
        "stock_program_available": sum(
            1 for x in (detail.get("stocks") or [])
            if (x.get("program") or {}).get("available")
        ),
        "stock_price_available": sum(
            1 for x in (detail.get("stocks") or [])
            if (x.get("price") or {}).get("available")
        ),
        "industry_price_available": sum(
            1 for x in (detail.get("industries") or [])
            if (x.get("price") or {}).get("available")
        ),
        "etf_price_available": sum(
            1 for x in (detail.get("etfs") or [])
            if (x.get("price") or {}).get("available")
        ),
        "errors": detail.get("errors") or [],
        "text_preview": text[:800],
    }
    if summary["stock_program_available"] < 1:
        raise RuntimeError(f"full enrichment has no event stock program interval: {summary}")
    if summary["stock_price_available"] < 1:
        raise RuntimeError(f"full enrichment has no integrated stock interval price: {summary}")
    if summary["theme_count"] < 1:
        raise RuntimeError(f"full enrichment has no theme mapping: {summary}")
    if summary["industry_count"] < 1:
        raise RuntimeError(f"full enrichment has no industry mapping: {summary}")
    if summary["etf_price_available"] < 1:
        raise RuntimeError(f"full enrichment has no ETF interval price: {summary}")
    return summary


def select_stock_chart_probe_window(
    rows: list[dict[str, Any]],
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """검증만 장중 실시간 창과 장마감 당일 원자료 창을 구분한다.

    실전 사건구간 stock_interval_price의 과거 표본 금지·90초 정렬 규칙은 그대로 둔다.
    장외에 '현재-10분'을 사용하면 정상인 당일 장중 봉도 무조건 실패하는 문제를 막는다.
    """
    from krx_session_calendar import session_state

    now = now or dt.datetime.now(KST)
    now = now.replace(tzinfo=KST) if now.tzinfo is None else now.astimezone(KST)
    session = session_state(now)
    if not session["is_session"] or not session["open"] or not session["close"]:
        return {"available": False, "mode": "휴장", "reason": "XKRX 휴장일: 장중 API 검증 대상 아님"}

    open_ts = session["open"].timestamp()
    close_ts = session["close"].timestamp()
    now_ts = now.timestamp()
    date_key = now.strftime("%Y%m%d")
    timed = []
    for row in rows:
        # 빈 날짜를 _epoch에서 오늘로 대체하는 관용 동작을 CI 검증에는 허용하지 않는다.
        bar_date = "".join(ch for ch in str(row.get("date") or "") if ch.isdigit())
        if bar_date != date_key:
            continue
        ts = _epoch(row.get("date"), row.get("time"))
        price = fnum(row.get("close"))
        if (
            ts is not None and price is not None and price > 0
            and open_ts <= ts <= min(now_ts, close_ts + 120)
        ):
            timed.append((ts, row))
    if len(timed) < 2:
        return {"available": False, "mode": "자료부족",
                "reason": "당일 정규장 1분봉 표본 2개 미만(과거 날짜·미래 봉 제외)",
                "session_date":date_key,"valid_bars":len(timed)}

    end_ts, _ = max(timed, key=lambda x:x[0])
    is_live = bool(now < session["continuous_end"])
    age = now_ts - end_ts
    if is_live and age > 180:
        return {"available": False, "mode": "장중",
                "reason": f"장중 1분봉 {age:.0f}초 지연(허용 180초)",
                "session_date":date_key,"bar_age_sec":round(age,1)}
    # 종가단일가 구간 및 장마감 후에는 당일 마지막 유효 체결봉을 검증한다.
    # 정규장 종료 20분보다 오래된 표본만 남았다면 장마감 봉조차 불완전한 것.
    if not is_live and close_ts - end_ts > 20 * 60:
        return {"available": False, "mode": "장마감 자료",
                "reason": "정규장 종료 전 20분 내 유효 1분봉 없음",
                "session_date":date_key,"last_bar_kst":fmt_clock(end_ts)}

    target_ts = max(open_ts, end_ts - 10 * 60)
    start_row = _aligned_prior_row([row for _, row in timed], target_ts)
    if not start_row or start_row[1] >= end_ts:
        return {"available": False, "mode": "장중" if is_live else "장마감 자료",
                "reason": "당일 10분 이전 기준봉 부재·90초 시간 정렬 실패",
                "session_date":date_key, "last_bar_kst":fmt_clock(end_ts)}
    return {
        "available": True,
        "mode": "장중" if is_live else "장마감 자료",
        "session_date": date_key,
        "start_ts": target_ts, "end_ts": end_ts,
        "start_bar_kst":fmt_clock(start_row[1]),
        "end_bar_kst":fmt_clock(end_ts),
        "bar_age_sec": round(age,1),
        "valid_bars": len(timed),
    }


def run_probe(token: str) -> dict[str, Any]:
    # 시각과 검증 데이터의 거래일을 잠근 뒤 장중·장외 창을 분리한다.
    master = stock_master(token)
    etfs = etf_master(token)
    industries = industry_master(token)
    real_inds = [
        x for x in industries
        if _is_real_industry(str(x.get("hname") or ""), str(x.get("upcode") or ""))
    ]
    first_members = []
    if real_inds:
        first_members = industry_members(token, str(real_inds[0].get("upcode") or ""))
    rank, rank_errors = program_rank_candidates(token, limit=5)
    samsung_bars = fetch_stock_bars(token, "005930", "U")
    chart_window = select_stock_chart_probe_window(samsung_bars)
    if chart_window.get("available"):
        samsung_price = stock_interval_price(
            token, "005930",
            float(chart_window["start_ts"]), float(chart_window["end_ts"]),
            rows=samsung_bars,
        )
    else:
        samsung_price = {"available":False,"error":chart_window.get("reason")}
    try:
        themes = stock_themes(token, "000660")
    except Exception as exc:
        themes = [{"error": f"{type(exc).__name__}: {exc}"}]
    etf_pdf_probe = None
    if etfs:
        etf_code = str(etfs[0].get("shcode") or "").strip()
        if etf_code:
            etf_pdf_probe = {"code": etf_code, **etf_pdf_overlap(token, etf_code, {"005930", "000660"})}
    probe = {
        "master_count": len(master),
        "etf_count": len(etfs),
        "industry_count": len(industries),
        "real_industry_count": len(real_inds),
        "first_industry": real_inds[0] if real_inds else None,
        "first_industry_members": len(first_members),
        "program_rank_count": len(rank),
        "program_rank_sample": rank[:3],
        "program_rank_errors": rank_errors,
        "stock_chart_probe_window": chart_window,
        "samsung_integrated_price": samsung_price,
        "skhynix_themes": themes[:8],
        "etf_pdf_probe": etf_pdf_probe,
    }
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    PROBE.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not master or not industries:
        raise RuntimeError(f"enrichment probe failed: {probe}")
    if not samsung_price.get("available"):
        raise RuntimeError(
            "integrated stock chart probe failed "
            f"(mode={chart_window.get('mode')}, "
            f"reason={chart_window.get('reason') or samsung_price.get('error')}, "
            f"date={chart_window.get('session_date')})"
        )
    if not rank:
        raise RuntimeError(f"integrated program rank probe failed: {probe}")
    if etf_pdf_probe is None or not etf_pdf_probe.get("available"):
        raise RuntimeError(f"integrated ETF PDF probe failed: {probe}")
    return probe


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    token = get_token()
    if args.probe:
        print(json.dumps(run_probe(token), ensure_ascii=False, indent=2))
        return 0
    if args.smoke:
        print(json.dumps(run_smoke(token), ensure_ascii=False, indent=2))
        return 0
    raise SystemExit("Use as module or run with --probe/--smoke")


if __name__ == "__main__":
    raise SystemExit(main())

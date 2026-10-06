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
    for attempt in range(4):
        _pace(tr)
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
        text = r.text or ""
        if not r.ok:
            last_error = f"{tr} HTTP {r.status_code}: {text[:300]}"
            if attempt < 3 and (r.status_code == 429 or "IGW00201" in text):
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise RuntimeError(last_error)
        data = r.json()
        code = str(data.get("rsp_cd") or "")
        if code and code not in {"00000", "0000"}:
            last_error = f"{tr} rejected {code}: {data.get('rsp_msg')}"
            if attempt < 3 and code == "IGW00201":
                time.sleep(1.5 * (2 ** attempt))
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


def direct_industry_interval(
    start_ts: float,
    end_ts: float,
    investor: str | None,
    path: Path | None = None,
    max_gap_sec: float = 30.0,
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
        "source": "LS UBM 통합 업종별투자자별매매현황",
        "unit_note": "msval 누적 원값의 사건 시작→저점 변화. 임의 원화 환산 없음.",
    }


def stock_master(token: str) -> list[dict[str, Any]]:
    data = ls_post(
        token, "/stock/etc", "t8436",
        {"t8436InBlock": {"gubun": "1"}},
    )
    return _rows(data, "t8436OutBlock")


def industry_master(token: str) -> list[dict[str, Any]]:
    best: list[dict[str, Any]] = []
    errors = []
    for gubun in ("1", "0"):
        try:
            data = ls_post(
                token, "/indtp/market-data", "t8424",
                {"t8424InBlock": {"gubun1": gubun}},
            )
            rows = _rows(data, "t8424OutBlock")
            if len(rows) > len(best):
                best = rows
            if rows:
                break
        except Exception as exc:
            errors.append(str(exc))
    if not best:
        raise RuntimeError("t8424 industry master unavailable: " + " | ".join(errors))
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
) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    mapping: dict[str, list[dict[str, str]]] = defaultdict(list)
    errors: list[str] = []
    industries = industry_master(token)
    filtered = []
    for row in industries:
        name = _display_name(row.get("hname"))
        code = str(row.get("upcode") or "").strip()
        if _is_real_industry(name, code):
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
) -> dict[str, Any]:
    rows = fetch_stock_bars(token, shcode, "U")
    a = _nearest_row(rows, start_ts)
    b = _nearest_row(rows, end_ts)
    if not a or not b:
        return {"available": False}
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
    a = _nearest_row(rows, start_ts)
    b = _nearest_row(rows, end_ts)
    if not a or not b:
        return {"available": False, "error": "time rows unavailable"}
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
    a = _nearest_row(rows, start_ts)
    b = _nearest_row(rows, end_ts)
    if not a or not b:
        return {"available": False}
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


def _fmt_pct(v: Any) -> str:
    n = fnum(v)
    return "확인 불가" if n is None else f"{n:+.2f}%"


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
    direct_industry = direct_industry_interval(start_ts, low_ts, spot_leader or None)

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

    usable = [
        x for x in stocks
        if x.get("program", {}).get("available")
        and fnum(x["program"].get("program_delta")) is not None
    ]
    usable.sort(key=lambda x: fnum(x["program"].get("program_delta")) or 0.0)
    top_stocks = usable[:7] if usable else stocks[:7]

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

    lines = [
        "🔎 <b>코스피 급락 정밀 분해 · 통합</b>",
        f"<code>{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} KST</code>",
        "",
        f"• 분석 구간 <b>{fmt_clock(start_ts)} → {fmt_clock(low_ts)}</b>",
        "• 종목 체결·프로그램·ETF는 <b>통합 기준</b> · 선물은 파생시장 기준",
    ]
    if att.get("available"):
        if single_leader:
            lines.append(
                f"• 시장 매도 주도 후보: <b>{html.escape(spot_leader)}</b>"
                + (f" · 확신도 {html.escape(confidence)}" if confidence else "")
            )
        elif spot_leader or futures_leader:
            lines.append(
                f"• 시장 매도주체: 현물 <b>{html.escape(spot_leader or '확인 불가')}</b>"
                f" / 선물 <b>{html.escape(futures_leader or '확인 불가')}</b> · "
                "<b>단일 주도자 보류</b>"
            )
        else:
            lines.append("• 시장 매도주체: <b>확정 보류</b>")
    elif legacy_leader:
        lines.append(f"• 시장 매도 주도 후보: <b>{html.escape(legacy_leader)}</b>")

    lines += ["", "<b>현물 주체가 직접 판 업종</b>"]
    direct_rows = [
        x for x in (direct_industry.get("rows") or [])
        if (fnum(x.get("delta")) or 0.0) < 0
    ]
    if direct_industry.get("available") and direct_rows:
        lines.append(
            f"• 기준: 현물 최다매도 <b>{html.escape(str(direct_industry.get('investor') or '확인 불가'))}</b> · "
            "통합 UBM 사건구간 순매수 원값 변화"
        )
        for i, row in enumerate(direct_rows[:4], 1):
            lines.append(
                f"• {i}. <b>{html.escape(str(row.get('name') or row.get('code')))}</b> · "
                f"{html.escape(str(row.get('investor') or ''))} {_fmt_program(row.get('delta'))} "
                f"<i>(LS UBM 원값)</i> · 기준점 시차 "
                f"{float(row.get('start_gap_sec') or 0):.1f}초/{float(row.get('end_gap_sec') or 0):.1f}초"
            )
    else:
        lines.append(
            "• 직접 업종 수급 판정 보류 — "
            + html.escape(str(direct_industry.get("reason") or "통합 UBM 기준점 부족"))
        )

    lines += ["", "<b>프로그램·가격으로 본 하락 업종</b>"]
    if industries:
        for i, ind in enumerate(industries[:3], 1):
            ret = (ind.get("price") or {}).get("return_pct")
            stocks_txt = ", ".join(ind.get("stocks", [])[:3])
            lines.append(
                f"• {i}. <b>{html.escape(ind['name'])}</b> · 업종지수 {_fmt_pct(ret)} · "
                f"상위 프로그램 매도종목 합계 {_fmt_program(ind.get('program_delta'))} <i>(LS 원값)</i> · {html.escape(stocks_txt)}"
            )
    else:
        lines.append("• 업종 분류 확인 불가")

    lines += ["", "<b>상위 프로그램 매도 후보 연결 테마</b>"]
    if theme_rows:
        for i, th in enumerate(theme_rows[:4], 1):
            names = ", ".join(th.get("stocks", [])[:3])
            lines.append(
                f"• {i}. <b>{html.escape(th['name'])}</b> · 상위 구성종목 프로그램 "
                f"{_fmt_program(th['program_delta'])} <i>(LS 원값)</i> · {html.escape(names)}"
            )
    else:
        lines.append("• 상위 매도종목의 LS 테마 연결 확인 불가")

    lines += ["", "<b>프로그램 매도 상위 후보 종목</b>"]
    if top_stocks:
        for i, stock in enumerate(top_stocks[:6], 1):
            pd = stock.get("program", {}).get("program_delta")
            ret = stock.get("price", {}).get("return_pct")
            lines.append(
                f"• {i}. <b>{html.escape(stock['name'])}</b> · 프로그램 {_fmt_program(pd)} <i>(LS 원값)</i> · 구간 {_fmt_pct(ret)}"
            )
    else:
        lines.append("• 종목별 프로그램 매도 구간 확인 불가")

    lines += ["", "<b>같이 움직인 ETF</b>"]
    usable_etfs = [x for x in etfs if x.get("price", {}).get("available")]
    if usable_etfs:
        for i, etf in enumerate(usable_etfs[:5], 1):
            ret = etf.get("price", {}).get("return_pct")
            overlap = etf.get("overlap") or {}
            weight = fnum(overlap.get("overlap_weight"))
            suffix = f" · 핵심 매도종목 PDF 비중 {weight:.1f}%" if weight is not None and weight > 0 else ""
            lines.append(
                f"• {i}. <b>{html.escape(etf['name'])}</b> · 구간 {_fmt_pct(ret)}{suffix}"
            )
    else:
        lines.append("• 연결 ETF의 구간 가격 확인 불가")

    lines += ["", "<b>지수 하락기여 후보</b>"]
    if cap_proxy:
        proxy_names = " → ".join(html.escape(x["name"]) for x in cap_proxy[:3])
        lines.append(f"• 시가총액×구간수익률 근사: <b>{proxy_names}</b>")
    else:
        lines.append("• 근사 기여도 계산 불가")

    lines += [
        "",
        "<b>정확성</b>",
        "• '현물 주체가 직접 판 업종'만 통합 UBM 투자자 수급으로 직접 판정합니다. 기준점이 30초를 넘으면 판정을 보류합니다.",
        "• 프로그램·가격 업종·테마·종목 순위는 장중 프로그램 매도 상위 후보군을 사건구간으로 재검산한 결과이며 전체 상장종목의 완전 전수순위로 표현하지 않습니다.",
        "• LS 프로그램 원값은 단위를 임의로 억원 환산하지 않습니다.",
        "• 특정 업종·테마의 외국인 직접 순매도액으로 바꿔 쓰지 않습니다.",
        "• ETF는 2차시장 가격과 PDF 겹침을 보여주며, ETF 자금 유출로 단정하지 않습니다.",
    ]
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3850].rsplit("\n", 1)[0] + "\n• 상세 원자료는 검증 아티팩트에 저장"
    return text, raw


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


def run_probe(token: str) -> dict[str, Any]:
    now = time.time()
    start = now - 10 * 60
    master = stock_master(token)
    etfs = [x for x in master if str(x.get("etfgubun") or "") == "1"]
    industries = industry_master(token)
    real_inds = [
        x for x in industries
        if _is_real_industry(str(x.get("hname") or ""), str(x.get("upcode") or ""))
    ]
    first_members = []
    if real_inds:
        first_members = industry_members(token, str(real_inds[0].get("upcode") or ""))
    rank, rank_errors = program_rank_candidates(token, limit=5)
    samsung_price = stock_interval_price(token, "005930", start, now)
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
        "samsung_integrated_price": samsung_price,
        "skhynix_themes": themes[:8],
        "etf_pdf_probe": etf_pdf_probe,
    }
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    PROBE.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not master or not industries:
        raise RuntimeError(f"enrichment probe failed: {probe}")
    if not samsung_price.get("available"):
        raise RuntimeError(f"integrated stock chart probe failed: {probe}")
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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
DIAG_PATH = Path("out/kospi_flow_attribution_ls_diagnostic.json")

INVESTORS = {
    "개인": "08",
    "외국인": "17",
    "기관계": "18",
    "증권": "01",
    "투신": "03",
    "은행": "04",
    "보험": "02",
    "종금": "05",
    "기금": "06",
    "기타": "07",
    "국가": "11",
    "사모펀드": "00",
}


def fnum(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def get_ls_token() -> str:
    app_key = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    app_secret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not app_key or not app_secret:
        raise RuntimeError("LS_OPENAPI_APP_KEY / LS_OPENAPI_APP_SECRET missing")
    r = requests.post(
        f"{BASE_URL}/oauth2/token",
        headers={"content-type": "application/x-www-form-urlencoded"},
        params={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecretkey": app_secret,
            "scope": "oob",
        },
        timeout=30,
    )
    r.raise_for_status()
    token = str(r.json().get("access_token") or "").strip()
    if not token:
        raise RuntimeError("LS access token issue failed")
    return token


def ls_rest(token: str, path: str, tr_cd: str, body: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        f"{BASE_URL}/{path}",
        headers={
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "tr_cd": tr_cd,
            "tr_cont": "N",
            "tr_cont_key": "",
        },
        data=json.dumps(body),
        timeout=20,
    )
    if not r.ok:
        raise RuntimeError(f"{tr_cd} HTTP {r.status_code}: {(r.text or '')[:400]}")
    data = r.json()
    rsp_cd = str(data.get("rsp_cd") or "")
    if rsp_cd and rsp_cd not in {"00000", "0000"}:
        raise RuntimeError(f"{tr_cd} rejected: {rsp_cd} {data.get('rsp_msg')}")
    return data


def _time_seconds(v: Any) -> int | None:
    s = "".join(ch for ch in str(v or "") if ch.isdigit())
    if len(s) >= 6:
        s = s[:6]
    elif len(s) == 4:
        s += "00"
    else:
        return None
    try:
        hh, mm, ss = int(s[:2]), int(s[2:4]), int(s[4:6])
        if hh > 23 or mm > 59 or ss > 59:
            return None
        return hh * 3600 + mm * 60 + ss
    except Exception:
        return None


def _sorted_rows(rows: Any) -> list[dict[str, Any]]:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    out = [r for r in rows if isinstance(r, dict) and _time_seconds(r.get("time")) is not None]
    out.sort(key=lambda r: _time_seconds(r.get("time")) or -1)
    return out


def _window_values(rows: list[dict[str, Any]], fields: dict[str, str], minutes: int) -> dict[str, Any]:
    if not rows:
        return {"latest_time": None, "base_time": None, "current": {}, "delta": {}}
    latest = rows[-1]
    latest_s = _time_seconds(latest.get("time")) or 0
    target = latest_s - minutes * 60
    eligible = [r for r in rows[:-1] if (_time_seconds(r.get("time")) or 10**9) <= target]
    if eligible:
        base = max(eligible, key=lambda r: _time_seconds(r.get("time")) or -1)
    elif len(rows) >= 2:
        base = rows[0]
    else:
        base = None
    current: dict[str, float | None] = {}
    delta: dict[str, float | None] = {}
    for label, field in fields.items():
        cur = fnum(latest.get(field))
        old = fnum(base.get(field)) if base else None
        current[label] = cur
        delta[label] = (cur - old) if cur is not None and old is not None else None
    return {
        "latest_time": str(latest.get("time") or ""),
        "base_time": str(base.get("time") or "") if base else None,
        "current": current,
        "delta": delta,
    }


def fetch_investor_series(
    token: str,
    market: str,
    upcode: str,
    *,
    amount: bool = True,
    count: int = 100,
) -> dict[str, Any]:
    body = {
        "t1602InBlock": {
            "market": market,
            "upcode": upcode,
            "gubun1": "2" if amount else "1",
            "gubun2": "0",
            "cts_time": "",
            "cts_idx": 0,
            "cnt": count,
            "gubun3": "",
            "exchgubun": "K",
        }
    }
    d = ls_rest(token, "stock/investor", "t1602", body)
    rows = _sorted_rows(d.get("t1602OutBlock1"))
    summary = d.get("t1602OutBlock") if isinstance(d.get("t1602OutBlock"), dict) else {}
    return {
        "request": body["t1602InBlock"],
        "summary": summary,
        "rows": rows,
        "row_count": len(rows),
    }


def fetch_program_series(token: str, count_hint: int = 100) -> dict[str, Any]:
    # LS current sample: gubun=0 거래소/KOSPI, gubun1=0 금액, gubun2=1 직전대비,
    # gubun3=1 당일, date/time blank first request, exchgubun=K.
    body = {
        "t1632InBlock": {
            "gubun": "0",
            "gubun1": "0",
            "gubun2": "1",
            "gubun3": "1",
            "date": "",
            "time": "",
            "exchgubun": "K",
        }
    }
    d = ls_rest(token, "stock/program", "t1632", body)
    rows = _sorted_rows(d.get("t1632OutBlock1"))
    return {
        "request": body["t1632InBlock"],
        "summary": d.get("t1632OutBlock") if isinstance(d.get("t1632OutBlock"), dict) else {},
        "rows": rows[-count_hint:],
        "row_count": len(rows),
    }


def _top_seller(delta: dict[str, Any], labels: tuple[str, ...]) -> tuple[str | None, float | None]:
    vals = [(label, fnum(delta.get(label))) for label in labels]
    vals = [(label, val) for label, val in vals if val is not None]
    if not vals:
        return None, None
    return min(vals, key=lambda x: x[1])


def _flow_block(series: dict[str, Any], minutes: int) -> dict[str, Any]:
    fields = {label: f"sv_{code}" for label, code in INVESTORS.items()}
    return _window_values(series.get("rows") or [], fields, minutes)


def _program_block(series: dict[str, Any], minutes: int) -> dict[str, Any]:
    return _window_values(
        series.get("rows") or [],
        {"전체": "tot3", "차익": "cha3", "비차익": "bcha3"},
        minutes,
    )


def classify_attribution(data: dict[str, Any]) -> dict[str, Any]:
    spot = data.get("kospi", {})
    kp200 = data.get("kp200", {})
    fut = data.get("futures", {})
    pgm = data.get("program", {})

    spot_seller, spot_delta = _top_seller(spot.get("delta") or {}, ("외국인", "기관계", "개인"))
    kp_seller, kp_delta = _top_seller(kp200.get("delta") or {}, ("외국인", "기관계", "개인"))
    fut_seller, fut_delta = _top_seller(fut.get("delta") or {}, ("외국인", "기관계", "개인"))
    pgm_seller, pgm_delta = _top_seller(pgm.get("delta") or {}, ("차익", "비차익"))

    signals: list[str] = []
    if spot_seller and spot_delta is not None and spot_delta < 0:
        signals.append(f"KOSPI 현물 {spot_seller} 순매수 악화")
    if kp_seller and kp_delta is not None and kp_delta < 0:
        signals.append(f"KOSPI200 {kp_seller} 순매수 악화")
    if fut_seller and fut_delta is not None and fut_delta < 0:
        signals.append(f"국내선물 {fut_seller} 순매수 악화")
    if pgm_seller and pgm_delta is not None and pgm_delta < 0:
        signals.append(f"프로그램 {pgm_seller} 순매수 악화")

    cross = []
    foreign_neg = sum(
        1 for block in (spot, kp200, fut)
        if fnum((block.get("delta") or {}).get("외국인")) is not None
        and float((block.get("delta") or {}).get("외국인")) < 0
    )
    inst_neg = sum(
        1 for block in (spot, kp200, fut)
        if fnum((block.get("delta") or {}).get("기관계")) is not None
        and float((block.get("delta") or {}).get("기관계")) < 0
    )
    program_total = fnum((pgm.get("delta") or {}).get("전체"))
    nonarb = fnum((pgm.get("delta") or {}).get("비차익"))
    arb = fnum((pgm.get("delta") or {}).get("차익"))
    if foreign_neg >= 2:
        cross.append("외국인 매도가 현물·KOSPI200·선물 중 2개 이상에서 동시 확인")
    if inst_neg >= 2:
        cross.append("기관 매도가 현물·KOSPI200·선물 중 2개 이상에서 동시 확인")
    if program_total is not None and program_total < 0:
        if nonarb is not None and arb is not None:
            cross.append("프로그램 매도 동반 — 비차익 우세" if nonarb < arb else "프로그램 매도 동반 — 차익 우세")
        else:
            cross.append("프로그램 매도 동반")

    if foreign_neg >= 2 and program_total is not None and program_total < 0:
        verdict = "외국인 매도와 프로그램 매도가 동시에 확대 — 외국인·프로그램 수급 주도 가능성 높음"
        confidence = "높음"
    elif inst_neg >= 2 and program_total is not None and program_total < 0:
        verdict = "기관 매도와 프로그램 매도가 동시에 확대 — 기관·프로그램 수급 주도 가능성 높음"
        confidence = "높음"
    elif spot_seller and spot_delta is not None and spot_delta < 0:
        verdict = f"{spot_seller} 현물 매도가 가장 뚜렷 — 파생·프로그램 동조 여부를 함께 확인"
        confidence = "중간"
    elif signals:
        verdict = "매도 우위 주체는 확인되지만 시장 간 동조가 약함 — 단일 주체 원인으로 단정하지 않음"
        confidence = "낮음"
    else:
        verdict = "가격 급락과 동시에 뚜렷하게 악화된 주체별 수급을 확인하지 못함"
        confidence = "낮음"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "spot_leader": {"actor": spot_seller, "delta": spot_delta},
        "kp200_leader": {"actor": kp_seller, "delta": kp_delta},
        "futures_leader": {"actor": fut_seller, "delta": fut_delta},
        "program_leader": {"actor": pgm_seller, "delta": pgm_delta},
        "signals": signals,
        "cross_checks": cross,
    }


def fetch_attribution(token: str | None = None, window_minutes: int = 15) -> dict[str, Any]:
    token = token or get_ls_token()
    errors: dict[str, str] = {}
    raw: dict[str, Any] = {}

    def grab(name: str, fn):
        try:
            raw[name] = fn()
        except Exception as exc:
            raw[name] = {"rows": [], "summary": {}, "row_count": 0}
            errors[name] = f"{type(exc).__name__}: {exc}"

    grab("kospi_raw", lambda: fetch_investor_series(token, "1", "001", amount=True))
    grab("kp200_raw", lambda: fetch_investor_series(token, "2", "101", amount=True))
    grab("futures_raw", lambda: fetch_investor_series(token, "4", "900", amount=True))
    grab("program_raw", lambda: fetch_program_series(token))

    data = {
        "asof": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "window_minutes": window_minutes,
        "kospi": _flow_block(raw["kospi_raw"], window_minutes),
        "kp200": _flow_block(raw["kp200_raw"], window_minutes),
        "futures": _flow_block(raw["futures_raw"], window_minutes),
        "program": _program_block(raw["program_raw"], window_minutes),
        "errors": errors,
        "raw_meta": {
            name: {
                "request": value.get("request"),
                "row_count": value.get("row_count"),
                "summary_keys": sorted((value.get("summary") or {}).keys()),
                "latest_row": (value.get("rows") or [])[-1] if value.get("rows") else None,
                "earliest_row": (value.get("rows") or [None])[0] if value.get("rows") else None,
            }
            for name, value in raw.items()
        },
    }
    data["classification"] = classify_attribution(data)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--window", type=int, default=15)
    args = ap.parse_args()
    data = fetch_attribution(window_minutes=max(1, args.window))
    if args.diagnose:
        DIAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DIAG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

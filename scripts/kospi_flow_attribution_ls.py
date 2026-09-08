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
REGULAR_START = 8 * 3600 + 30 * 60
REGULAR_END = 15 * 3600 + 45 * 60

INVESTORS = {
    "개인": "08", "외국인": "17", "기관계": "18", "증권": "01",
    "투신": "03", "은행": "04", "보험": "02", "종금": "05",
    "기금": "06", "기타": "07", "국가": "11", "사모펀드": "00",
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
        params={"grant_type": "client_credentials", "appkey": app_key,
                "appsecretkey": app_secret, "scope": "oob"},
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
        headers={"content-type": "application/json; charset=utf-8",
                 "authorization": f"Bearer {token}", "tr_cd": tr_cd,
                 "tr_cont": "N", "tr_cont_key": ""},
        data=json.dumps(body), timeout=20,
    )
    if not r.ok:
        raise RuntimeError(f"{tr_cd} HTTP {r.status_code}: {(r.text or '')[:400]}")
    d = r.json()
    rsp_cd = str(d.get("rsp_cd") or "")
    if rsp_cd and rsp_cd not in {"00000", "0000"}:
        raise RuntimeError(f"{tr_cd} rejected: {rsp_cd} {d.get('rsp_msg')}")
    return d


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


def _regular_rows(rows: Any) -> list[dict[str, Any]]:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sec = _time_seconds(row.get("time"))
        if sec is not None and REGULAR_START <= sec <= REGULAR_END:
            out.append(row)
    out.sort(key=lambda r: _time_seconds(r.get("time")) or -1)
    return out


def _window_values(rows: list[dict[str, Any]], fields: dict[str, str], minutes: int,
                   now: dt.datetime) -> dict[str, Any]:
    if not rows:
        return {"latest_time": None, "base_time": None, "current": {}, "delta": {},
                "stale": True, "covered_minutes": 0.0}
    latest = rows[-1]
    latest_s = _time_seconds(latest.get("time")) or 0
    target = latest_s - minutes * 60
    eligible = [r for r in rows[:-1] if (_time_seconds(r.get("time")) or 10**9) <= target]
    base = max(eligible, key=lambda r: _time_seconds(r.get("time")) or -1) if eligible else None
    current: dict[str, float | None] = {}
    delta: dict[str, float | None] = {}
    for label, field in fields.items():
        cur = fnum(latest.get(field))
        old = fnum(base.get(field)) if base else None
        current[label] = cur
        delta[label] = (cur - old) if cur is not None and old is not None else None
    base_s = _time_seconds(base.get("time")) if base else None
    covered = (latest_s - base_s) / 60 if base_s is not None else 0.0
    now_s = now.hour * 3600 + now.minute * 60 + now.second
    # 정규장 중에는 최신 수급시각이 3분 이상 뒤처지면 원인 판정에 쓰지 않는다.
    stale = bool(REGULAR_START <= now_s <= REGULAR_END and now_s - latest_s > 180)
    return {"latest_time": str(latest.get("time") or ""),
            "base_time": str(base.get("time") or "") if base else None,
            "current": current, "delta": delta, "stale": stale,
            "covered_minutes": covered}


def fetch_investor_series(token: str, market: str, upcode: str, count: int = 100) -> dict[str, Any]:
    body = {"t1602InBlock": {"market": market, "upcode": upcode,
             "gubun1": "2", "gubun2": "0", "cts_time": "", "cts_idx": 0,
             "cnt": count, "gubun3": "", "exchgubun": "K"}}
    d = ls_rest(token, "stock/investor", "t1602", body)
    rows = _regular_rows(d.get("t1602OutBlock1"))
    return {"request": body["t1602InBlock"],
            "summary": d.get("t1602OutBlock") if isinstance(d.get("t1602OutBlock"), dict) else {},
            "rows": rows, "row_count": len(rows)}


def fetch_program_series(token: str) -> dict[str, Any]:
    body = {"t1632InBlock": {"gubun": "0", "gubun1": "0", "gubun2": "1",
             "gubun3": "1", "date": "", "time": "", "exchgubun": "K"}}
    d = ls_rest(token, "stock/program", "t1632", body)
    rows = _regular_rows(d.get("t1632OutBlock1"))
    return {"request": body["t1632InBlock"],
            "summary": d.get("t1632OutBlock") if isinstance(d.get("t1632OutBlock"), dict) else {},
            "rows": rows, "row_count": len(rows)}


def _flow_block(series: dict[str, Any], minutes: int, now: dt.datetime) -> dict[str, Any]:
    return _window_values(series.get("rows") or [],
                          {label: f"sv_{code}" for label, code in INVESTORS.items()},
                          minutes, now)


def _program_block(series: dict[str, Any], minutes: int, now: dt.datetime) -> dict[str, Any]:
    return _window_values(series.get("rows") or [],
                          {"전체": "tot3", "차익": "cha3", "비차익": "bcha3"},
                          minutes, now)


def _top_negative(delta: dict[str, Any], labels: tuple[str, ...]) -> tuple[str | None, float | None, float]:
    vals = [(label, fnum(delta.get(label))) for label in labels]
    neg = [(label, val) for label, val in vals if val is not None and val < 0]
    if not neg:
        return None, None, 0.0
    actor, value = min(neg, key=lambda x: x[1])
    total_abs = sum(abs(v) for _, v in neg)
    share = abs(value) / total_abs if total_abs else 0.0
    return actor, value, share


def classify_attribution(data: dict[str, Any]) -> dict[str, Any]:
    spot, kp200, fut, pgm = (data.get("kospi", {}), data.get("kp200", {}),
                             data.get("futures", {}), data.get("program", {}))
    usable = [b for b in (spot, kp200, fut) if not b.get("stale") and b.get("base_time")]
    spot_actor, spot_delta, spot_share = _top_negative(spot.get("delta") or {}, ("외국인", "기관계", "개인"))
    kp_actor, kp_delta, kp_share = _top_negative(kp200.get("delta") or {}, ("외국인", "기관계", "개인"))
    fut_actor, fut_delta, fut_share = _top_negative(fut.get("delta") or {}, ("외국인", "기관계", "개인"))

    actor_hits = {"외국인": 0, "기관계": 0, "개인": 0}
    for block in usable:
        for actor in actor_hits:
            v = fnum((block.get("delta") or {}).get(actor))
            if v is not None and v < 0:
                actor_hits[actor] += 1
    cross_actor = max(actor_hits, key=actor_hits.get) if usable else None
    cross_hits = actor_hits.get(cross_actor, 0) if cross_actor else 0

    program_total = None if pgm.get("stale") or not pgm.get("base_time") else fnum((pgm.get("delta") or {}).get("전체"))
    arb = fnum((pgm.get("delta") or {}).get("차익"))
    nonarb = fnum((pgm.get("delta") or {}).get("비차익"))
    program_direction = "확인 불가"
    if program_total is not None:
        if program_total < 0:
            if arb is not None and nonarb is not None:
                program_direction = "비차익 매도 우세" if nonarb < arb else "차익 매도 우세"
            else:
                program_direction = "프로그램 매도 우세"
        elif program_total > 0:
            program_direction = "프로그램 매수 우세"
        else:
            program_direction = "프로그램 중립"

    # 가장 중요한 판정은 급락구간 변화량이다. 하루 누적 순매수는 보조표시만 한다.
    if len(usable) < 2:
        verdict = "급락구간 주체별 수급 표본이 부족해 원인 주체 확정 보류"
        confidence = "낮음"
    elif cross_hits >= 2 and program_total is not None and program_total < 0:
        verdict = f"{cross_actor} 매도가 2개 이상 시장에서 동시 확대되고 프로그램 매도도 동반"
        confidence = "높음"
    elif cross_hits >= 2:
        verdict = f"{cross_actor} 매도가 2개 이상 시장에서 동시 확대 — 주도 매도 가능성 높음"
        confidence = "중간"
    elif spot_actor and spot_delta is not None and spot_share >= 0.55:
        verdict = f"KOSPI 현물 급락구간은 {spot_actor} 매도 비중이 가장 큼 — 파생 동조는 제한적"
        confidence = "중간"
    elif spot_actor:
        verdict = "현물 매도 주체가 분산돼 단일 주체가 급락을 만들었다고 보기 어려움"
        confidence = "낮음"
    else:
        verdict = "급락구간에서 외국인·기관·개인 중 뚜렷한 순매도 확대 주체가 없음"
        confidence = "낮음"

    return {"verdict": verdict, "confidence": confidence,
            "spot_leader": {"actor": spot_actor, "delta": spot_delta, "negative_share": spot_share},
            "kp200_leader": {"actor": kp_actor, "delta": kp_delta, "negative_share": kp_share},
            "futures_leader": {"actor": fut_actor, "delta": fut_delta, "negative_share": fut_share},
            "cross_actor": cross_actor, "cross_hits": cross_hits,
            "program_direction": program_direction,
            "usable_market_blocks": len(usable)}


def fetch_attribution(token: str | None = None, window_minutes: int = 15) -> dict[str, Any]:
    token = token or get_ls_token()
    now = dt.datetime.now(KST)
    raw: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def grab(name: str, fn) -> None:
        try:
            raw[name] = fn()
        except Exception as exc:
            raw[name] = {"rows": [], "summary": {}, "row_count": 0}
            errors[name] = f"{type(exc).__name__}: {exc}"

    grab("kospi_raw", lambda: fetch_investor_series(token, "1", "001"))
    grab("kp200_raw", lambda: fetch_investor_series(token, "2", "101"))
    grab("futures_raw", lambda: fetch_investor_series(token, "4", "900"))
    grab("program_raw", lambda: fetch_program_series(token))
    data = {"asof": now.isoformat(timespec="seconds"), "window_minutes": window_minutes,
            "kospi": _flow_block(raw["kospi_raw"], window_minutes, now),
            "kp200": _flow_block(raw["kp200_raw"], window_minutes, now),
            "futures": _flow_block(raw["futures_raw"], window_minutes, now),
            "program": _program_block(raw["program_raw"], window_minutes, now),
            "errors": errors,
            "unit_note": "t1602 gubun1=2 금액값은 억원 기준으로 검증. t1632는 방향 판정 위주로 사용.",
            "raw_meta": {name: {"request": value.get("request"), "row_count": value.get("row_count"),
                                      "latest_row": (value.get("rows") or [])[-1] if value.get("rows") else None}
                         for name, value in raw.items()}}
    data["classification"] = classify_attribution(data)
    return data


def fmt_eok(v: Any) -> str:
    n = fnum(v)
    if n is None:
        return "확인 불가"
    sign = "+" if n > 0 else ""
    return f"{sign}{n:,.0f}억원"


def attribution_html_lines(data: dict[str, Any]) -> list[str]:
    window = int(data.get("window_minutes") or 15)
    cls = data.get("classification") or {}
    lines = ["<b>누가 밀었나 · 급락구간 수급</b>"]
    for key, label in (("kospi", "KOSPI 현물"), ("kp200", "KOSPI200"), ("futures", "국내선물")):
        block = data.get(key) or {}
        delta = block.get("delta") or {}
        if block.get("stale") or not block.get("base_time"):
            lines.append(f"• {label}: {window}분 변화량 확인 불가")
            continue
        lines.append(f"• {label} {window}분: 외국인 <b>{fmt_eok(delta.get('외국인'))}</b> · 기관 <b>{fmt_eok(delta.get('기관계'))}</b> · 개인 <b>{fmt_eok(delta.get('개인'))}</b>")
    lines += ["", "<b>하루 누적 수급 · 원인 판정과 분리</b>"]
    spot_cur = (data.get("kospi") or {}).get("current") or {}
    lines.append(f"• KOSPI 누적: 외국인 {fmt_eok(spot_cur.get('외국인'))} · 기관 {fmt_eok(spot_cur.get('기관계'))} · 개인 {fmt_eok(spot_cur.get('개인'))}")
    lines += ["", "<b>수급 원인 판정</b>",
              f"• <b>{str(cls.get('verdict') or '판정 불가')}</b> · 확신도 {str(cls.get('confidence') or '낮음')}",
              f"• 프로그램: {str(cls.get('program_direction') or '확인 불가')}"]
    if data.get("errors"):
        lines.append("• 일부 LS 수급 조회 실패 — 확인된 항목만으로 단정하지 않음")
    return lines


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

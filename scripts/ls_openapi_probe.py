#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import ssl
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import websocket

KST = ZoneInfo("Asia/Seoul")
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
STOCK_WS_URL = "wss://openapi.ls-sec.co.kr:9443/websocket"
DERIV_WS_URL = "wss://openapi.ls-sec.co.kr:9443/websocket/futureoption"
OUT = Path("out/ls_openapi_probe.json")
STATUS = Path("out/ls_openapi_probe_status.md")


def get_token() -> str:
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
    d = r.json()
    token = str(d.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"LS token missing: rsp_cd={d.get('rsp_cd')} msg={d.get('rsp_msg')}")
    return token


def rest(token: str, tr_cd: str, body: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/futureoption/market-data",
        headers={
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "tr_cd": tr_cd,
            "tr_cont": "N",
            "tr_cont_key": "",
        },
        data=json.dumps(body),
        timeout=30,
    )
    if not r.ok:
        text = (r.text or "").replace("\n", " ")[:800]
        raise RuntimeError(f"{tr_cd} HTTP {r.status_code}: {text}")
    d = r.json()
    if str(d.get("rsp_cd") or "00000") not in ("00000", ""):
        raise RuntimeError(f"{tr_cd} failed: {d.get('rsp_cd')} {d.get('rsp_msg')}")
    return d


def _register_and_collect(url: str, token: str, regs: list[tuple[str, str]], seconds: float = 5.0) -> dict:
    ws = websocket.create_connection(url, timeout=5, sslopt={"cert_reqs": ssl.CERT_REQUIRED})
    for tr_cd, tr_key in regs:
        ws.send(json.dumps({
            "header": {"token": token, "tr_type": "3"},
            "body": {"tr_cd": tr_cd, "tr_key": tr_key},
        }))
    received = []
    deadline = time.time() + seconds
    while time.time() < deadline and len(received) < 12:
        try:
            raw = ws.recv()
        except Exception:
            break
        if not raw:
            continue
        try:
            d = json.loads(raw)
            header = d.get("header") or {}
            received.append({
                "tr_cd": header.get("tr_cd"),
                "tr_key": header.get("tr_key"),
                "rsp_cd": header.get("rsp_cd"),
                "rsp_msg": header.get("rsp_msg"),
                "has_body": bool(d.get("body")),
            })
        except Exception:
            received.append({"raw_type": type(raw).__name__})
    ws.close()
    return {
        "url_path": url.split(":9443", 1)[-1],
        "connected": True,
        "registrations": [x[0] for x in regs],
        "received": received,
    }


def _acks_ok(result: dict, required: set[str]) -> bool:
    ok = {
        str(x.get("tr_cd"))
        for x in result.get("received") or []
        if str(x.get("rsp_cd") or "") == "00000"
    }
    return required.issubset(ok)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    token = get_token()

    futures = rest(token, "t8467", {"t8467InBlock": {"gubun": "1"}}).get("t8467OutBlock") or []
    futcode = str((futures[0] if futures else {}).get("shcode") or "").strip() or None

    options = []
    option_error = None
    try:
        options = rest(token, "t8433", {"t8433InBlock": {"dummy": ""}}).get("t8433OutBlock") or []
    except Exception as exc:
        option_error = f"{type(exc).__name__}: {exc}"
    optcode = str((options[0] if options else {}).get("shcode") or "").strip() or None

    weekly = []
    weekly_error = None
    try:
        weekly = rest(token, "t8435", {"t8435InBlock": {"gubun": "WK"}}).get("t8435OutBlock") or []
    except Exception as exc:
        weekly_error = f"{type(exc).__name__}: {exc}"

    stock_ws = _register_and_collect(STOCK_WS_URL, token, [("IJ_", "001"), ("PM_", "001")], 4.0)
    deriv_regs: list[tuple[str, str]] = []
    if futcode:
        deriv_regs.append(("FC0", futcode))
    if optcode:
        deriv_regs.append(("OC0", optcode))
    deriv_ws = _register_and_collect(DERIV_WS_URL, token, deriv_regs, 4.0) if deriv_regs else {
        "connected": False, "registrations": [], "received": []
    }

    stock_ok = _acks_ok(stock_ws, {"IJ_", "PM_"})
    deriv_required = {x[0] for x in deriv_regs}
    deriv_ok = bool(deriv_regs) and _acks_ok(deriv_ws, deriv_required)

    safe = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "token_issued": True,
        "futures_count": len(futures),
        "front_future": {
            "hname": (futures[0] if futures else {}).get("hname"),
            "shcode": futcode,
            "expcode": (futures[0] if futures else {}).get("expcode"),
        },
        "index_option_count": len(options),
        "option_probe": {
            "hname": (options[0] if options else {}).get("hname"),
            "shcode": optcode,
            "expcode": (options[0] if options else {}).get("expcode"),
        },
        "index_option_error": option_error,
        "weekly_option_count": len(weekly),
        "weekly_sample": [
            {k: x.get(k) for k in ("hname", "shcode", "expcode", "recprice")}
            for x in weekly[:5]
        ],
        "weekly_error": weekly_error,
        "stock_websocket": stock_ws,
        "derivatives_websocket": deriv_ws,
        "stock_registration_ok": stock_ok,
        "derivatives_registration_ok": deriv_ok,
    }
    OUT.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# LS증권 OpenAPI 연결 검증\n\n"
        f"- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n"
        "- Access Token: 발급 성공\n"
        f"- KOSPI200 지수선물 마스터(t8467): {len(futures)}개 / 최근월물 {futcode or '미확인'}\n"
        f"- 지수옵션 마스터(t8433): {len(options)}개" + (f" / 오류 {option_error}" if option_error else "") + "\n"
        f"- 위클리옵션 마스터 탐색: {len(weekly)}개" + (f" / 오류 {weekly_error}" if weekly_error else "") + "\n"
        f"- 주식 WebSocket IJ_/PM_ 등록: {'성공' if stock_ok else '부분/실패'}\n"
        f"- 파생 WebSocket FC0/OC0 등록: {'성공' if deriv_ok else '부분/실패'}\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "ls_probe_ok": stock_ok and deriv_ok,
        "front_future": futcode,
        "futures_count": len(futures),
        "option_count": len(options),
        "weekly_count": len(weekly),
        "stock_ws_ok": stock_ok,
        "deriv_ws_ok": deriv_ok,
        "stock_messages": len(stock_ws.get("received") or []),
        "deriv_messages": len(deriv_ws.get("received") or []),
    }, ensure_ascii=False))
    if not stock_ok or not deriv_ok:
        raise RuntimeError("LS WebSocket registration verification failed; inspect out/ls_openapi_probe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

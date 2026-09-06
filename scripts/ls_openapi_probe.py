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
WS_URL = "wss://openapi.ls-sec.co.kr:9443/websocket"
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


def probe_ws(token: str, futcode: str | None) -> dict:
    ws = websocket.create_connection(WS_URL, timeout=5, sslopt={"cert_reqs": ssl.CERT_REQUIRED})
    regs = [("IJ_", "001"), ("PM_", "001")]
    if futcode:
        regs.append(("FC0", futcode))
    for tr_cd, tr_key in regs:
        ws.send(json.dumps({
            "header": {"token": token, "tr_type": "3"},
            "body": {"tr_cd": tr_cd, "tr_key": tr_key},
        }))
    received = []
    deadline = time.time() + 5.0
    while time.time() < deadline and len(received) < 10:
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
    return {"connected": True, "registrations": [x[0] for x in regs], "received": received}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    token = get_token()

    # 2026 current LS OpenAPI guide: t8467 is the current index-futures master TR.
    futures = rest(token, "t8467", {"t8467InBlock": {"gubun": "1"}}).get("t8467OutBlock") or []
    futcode = str((futures[0] if futures else {}).get("shcode") or "").strip() or None

    # Current regular index-option master. Sunday probe only validates master availability;
    # ATM/near-OTM selection for the realtime watcher is done on a market day.
    options = []
    option_error = None
    try:
        options = rest(token, "t8433", {"t8433InBlock": {"dummy": ""}}).get("t8433OutBlock") or []
    except Exception as exc:
        option_error = f"{type(exc).__name__}: {exc}"

    # Weekly discovery conventions have changed across LS/Xing revisions. Probe it only as
    # an optional capability and never fail the credential test if unsupported.
    weekly = []
    weekly_error = None
    try:
        weekly = rest(token, "t8435", {"t8435InBlock": {"gubun": "WK"}}).get("t8435OutBlock") or []
    except Exception as exc:
        weekly_error = f"{type(exc).__name__}: {exc}"

    ws_result = probe_ws(token, futcode)

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
        "index_option_sample": [
            {k: x.get(k) for k in ("hname", "shcode", "expcode", "recprice")}
            for x in options[:5]
        ],
        "index_option_error": option_error,
        "weekly_option_count": len(weekly),
        "weekly_sample": [
            {k: x.get(k) for k in ("hname", "shcode", "expcode", "recprice")}
            for x in weekly[:5]
        ],
        "weekly_error": weekly_error,
        "websocket": ws_result,
    }
    OUT.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# LS증권 OpenAPI 연결 검증\n\n"
        f"- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n"
        "- Access Token: 발급 성공\n"
        f"- KOSPI200 지수선물 마스터(t8467): {len(futures)}개 / 최근월물 {futcode or '미확인'}\n"
        f"- 지수옵션 마스터(t8433): {len(options)}개" + (f" / 오류 {option_error}" if option_error else "") + "\n"
        f"- 위클리옵션 추가 탐색: {len(weekly)}개" + (f" / 미지원 가능 {weekly_error}" if weekly_error else "") + "\n"
        f"- WebSocket 접속: {'성공' if ws_result.get('connected') else '실패'}\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "ls_probe_ok": True,
        "front_future": futcode,
        "futures_count": len(futures),
        "option_count": len(options),
        "weekly_count": len(weekly),
        "ws_connected": True,
        "ws_messages": len(ws_result.get("received") or []),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

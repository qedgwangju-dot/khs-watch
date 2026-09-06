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
    r.raise_for_status()
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
    deadline = time.time() + 4.0
    while time.time() < deadline and len(received) < 8:
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

    futures = rest(token, "t8432", {"t8432InBlock": {"gubun": "1"}}).get("t8432OutBlock") or []
    futcode = str((futures[0] if futures else {}).get("shcode") or "").strip() or None

    weekly = []
    weekly_error = None
    try:
        weekly = rest(token, "t8435", {"t8435InBlock": {"gubun": "WK"}}).get("t8435OutBlock") or []
    except Exception as exc:
        weekly_error = f"{type(exc).__name__}: {exc}"

    regular_options = []
    regular_error = None
    try:
        yyyymm = now.strftime("%Y%m")
        board = rest(token, "t2301", {"t2301InBlock": {"yyyymm": yyyymm, "gubun": "G"}})
        calls = board.get("t2301OutBlock1") or []
        puts = board.get("t2301OutBlock2") or []
        regular_options = [{"side": "call", **x} for x in calls[:3]] + [{"side": "put", **x} for x in puts[:3]]
    except Exception as exc:
        regular_error = f"{type(exc).__name__}: {exc}"

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
        "weekly_option_count": len(weekly),
        "weekly_sample": [
            {k: x.get(k) for k in ("hname", "shcode", "expcode", "recprice")}
            for x in weekly[:5]
        ],
        "weekly_error": weekly_error,
        "regular_option_sample": [
            {k: x.get(k) for k in ("side", "actprice", "optcode", "price", "atmgubun")}
            for x in regular_options
        ],
        "regular_error": regular_error,
        "websocket": ws_result,
    }
    OUT.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# LS증권 OpenAPI 연결 검증\n\n"
        f"- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n"
        "- Access Token: 발급 성공\n"
        f"- KOSPI200 지수선물 마스터: {len(futures)}개 / 최근월물 {futcode or '미확인'}\n"
        f"- 위클리옵션 마스터: {len(weekly)}개" + (f" / 오류 {weekly_error}" if weekly_error else "") + "\n"
        f"- 정규 옵션 표본: {len(regular_options)}개" + (f" / 오류 {regular_error}" if regular_error else "") + "\n"
        f"- WebSocket 접속: {'성공' if ws_result.get('connected') else '실패'}\n",
        encoding="utf-8",
    )
    print(json.dumps({"ls_probe_ok": True, "front_future": futcode, "weekly_count": len(weekly), "ws_connected": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

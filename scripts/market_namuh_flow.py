"""Read-only NAMUH PLUG transport and source evidence.

Only two documented market-data interfaces are allowed. No accounts, orders,
Telegram, or alert state are accessed. Tokens use a 24h encrypted shared cache;
the credential-bearing OAuth URL and response are deliberately never retained.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
BASE = "https://api.nhplug.com:8443"
INVESTORS = "/krfuture/quote/v1/tradingStatus"
PROGRAM = "/krfuture/quote/v1/timeProgramTrading"
SPEC_URL = "https://www.nhplug.com/openapi-docs/krfuture/openapi.json"
SPEC_SHA256 = "502e4813cae12ce46283a4c989435398bff90d2d8618c1dd49f8b3a1aaf970a7"
GUIDE_URL = "https://www.nhplug.com/llms.txt"
GUIDE_SHA256 = "e0b18001394142f66ccdf3e624dad2633aee9e6cefba014914d21ce4cceb123d"
_LOCK = threading.RLock()
_TOKEN = ""
_TOKEN_UNTIL = 0.0
_NEXT = 0.0
_CODE_SHA = None


def configured() -> bool:
    return (os.getenv("MARKET_SOURCE_OFFLINE") != "1" and bool(
        os.getenv("NHPLUG_APP_KEY", "").strip() and os.getenv("NHPLUG_APP_SECRET", "").strip()))


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def code_sha() -> str | None:
    global _CODE_SHA
    if _CODE_SHA is None:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True, timeout=5)
        _CODE_SHA = result.stdout.strip() if result.returncode == 0 else ""
    return _CODE_SHA or None


def _redact(message, token="") -> str:
    text = str(message or "")
    for secret in (token, os.getenv("NHPLUG_APP_KEY"), os.getenv("NHPLUG_APP_SECRET")):
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:300]


def _cache():
    from cryptography.fernet import Fernet
    key = os.environ["NHPLUG_APP_KEY"]
    secret = os.environ["NHPLUG_APP_SECRET"]
    material = ("khs-watch-namuh-v1\0" + BASE + "\0" + key + "\0" + secret).encode()
    cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))
    scope = digest((BASE + "|" + key).encode())[:16]
    folder = Path(os.getenv("NHPLUG_TOKEN_CACHE_DIR", str(Path.home() / ".cache/khs-watch-namuh")))
    return folder / (scope + ".enc"), cipher, scope


def _token() -> str:
    global _TOKEN, _TOKEN_UNTIL
    with _LOCK:
        if _TOKEN and time.time() < _TOKEN_UNTIL:
            return _TOKEN
        if not configured():
            raise ValueError("나무 인증 설정 없음")
        path, cipher, scope = _cache()
        if path.exists():
            try:
                cached = json.loads(cipher.decrypt(path.read_bytes()))
                if cached["scope"] != scope:
                    raise ValueError("scope")
                if cached["expires_at"] > time.time() + 120:
                    _TOKEN, _TOKEN_UNTIL = cached["access_token"], cached["expires_at"] - 120
                    return _TOKEN
            except Exception:
                # Do not silently generate more tokens when an existing cache is corrupt.
                raise ValueError("나무 암호화 토큰 캐시 검증 실패") from None
        try:
            response = requests.post(BASE + "/oauth2/token", params={
                "appkey": os.environ["NHPLUG_APP_KEY"], "appsecretkey": os.environ["NHPLUG_APP_SECRET"],
                "grant_type": "client_credentials", "scope": "oob"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=(5, 15), allow_redirects=False)
            body = response.json()
        except requests.RequestException as exc:
            raise ValueError("나무 인증 통신 실패: " + type(exc).__name__) from None
        except ValueError:
            raise ValueError("나무 인증 응답 형식 미확인") from None
        token = body.get("access_token")
        if response.status_code != 200 or not isinstance(token, str) or not token:
            message = body.get("error_description") or body.get("rsp_msg") or body.get("message")
            raise ValueError("나무 인증 미승인 (HTTP " + str(response.status_code) + "): " + _redact(message))
        try:
            ttl = float(body.get("expires_in", 0))
        except (TypeError, ValueError):
            ttl = 0
        if not 120 < ttl <= 172800:
            raise ValueError("나무 인증 만료시각 미확인")
        expires = time.time() + ttl
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fp:
            fp.write(cipher.encrypt(json.dumps({"scope": scope, "access_token": token, "expires_at": expires}).encode()))
        os.replace(tmp, path)
        _TOKEN, _TOKEN_UNTIL = token, expires - 120
        return token


def _validate_request(path: str, inputs: dict) -> None:
    if path not in (INVESTORS, PROGRAM) or not isinstance(inputs, dict):
        raise ValueError("나무 시세 전용 허용 경로 아님")
    if inputs.get("market_cd") not in {"KRX", "NXT", "UNT"}:
        raise ValueError("나무 거래소 범위 미확인")
    if path == INVESTORS:
        allowed = {"market_cd", "mrkt_cls_code", "cycle_cls_code", "opt_cls_code", "cnt"}
        if (inputs.get("mrkt_cls_code") not in {"1", "2", "3", "6"}
                or inputs.get("cycle_cls_code") not in {"2", "7"}
                or inputs.get("opt_cls_code") not in {"1", "2"}):
            raise ValueError("나무 투자자 시장·일별/당일분·금액/수량 조건 미확인")
    else:
        allowed = {"market_cd", "mrkt_cls_code", "cycle_cls_code", "opt_cls_code", "data_cls_code", "array_cnt"}
        if (inputs.get("mrkt_cls_code") not in {"1", "0"}
                or inputs.get("cycle_cls_code") not in {"1", "2"}
                or inputs.get("opt_cls_code") != "2" or inputs.get("data_cls_code") != "1"):
            raise ValueError("나무 프로그램 시장·주기·금액 조건 미확인")
    if set(inputs) - allowed:
        raise ValueError("나무 문서 외 조회 인자 거절")


def checked(entry: dict) -> dict:
    _validate_request(entry.get("endpoint"), entry.get("request"))
    raw = base64.b64decode(entry["raw_base64"], validate=True)
    if entry.get("http_status") != 200 or digest(raw) != entry.get("raw_sha256"):
        raise ValueError("나무 원응답 HTTP·바이트·해시 불일치")
    body = json.loads(raw)
    if body != entry.get("response"):
        raise ValueError("나무 응답 저장값과 원문 불일치")
    message = body.get("rsp_msg") or (body.get("message") or {}).get("msg")
    # The documented completion message is accepted independently of rsp_cd.
    # Unknown messages remain held, including HTTP 200 business errors.
    if message not in {"조회가 완료되었습니다.", "조회가 계속됩니다.", "조회가 계속됩니다. 다음을 누르십시오."}:
        raise ValueError("나무 조회 완료 미확인: " + _redact(message))
    if not isinstance(body.get("Output_0"), list) or not body["Output_0"]:
        raise ValueError("나무 시세 원행 없음")
    return body


def retain(entry: dict) -> dict:
    folder = Path(os.getenv("MARKET_SOURCE_EVIDENCE_DIR", "out/market_source_evidence"))
    folder.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()
    path = folder / (digest(raw) + ".json")
    path.write_bytes(raw)
    return {"path": str(path), "sha256": digest(raw), "response_sha256": entry["raw_sha256"]}


def request(path: str, inputs: dict) -> dict:
    global _NEXT
    _validate_request(path, inputs)
    token = _token()
    with _LOCK:
        delay = _NEXT - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _NEXT = time.monotonic() + 0.55
    started = time.time()
    try:
        response = requests.post(BASE + path, json={"Input_0": inputs},
            headers={"Content-Type": "application/json;charset=utf-8", "Authorization": "Bearer " + token},
            timeout=(5, 15), allow_redirects=False)
    except requests.RequestException as exc:
        raise ValueError("나무 시세 통신 실패: " + type(exc).__name__) from None
    raw = response.content
    if any(secret and secret.encode() in raw for secret in
           (token, os.getenv("NHPLUG_APP_KEY"), os.getenv("NHPLUG_APP_SECRET"))):
        raise ValueError("인증정보 포함 응답 보존 거절")
    try:
        body = response.json()
    except ValueError:
        body = None
    entry = {"provider": "Namuh", "endpoint": path, "request": inputs, "query_started_ts": started,
             "received_ts": time.time(), "http_status": response.status_code,
             "raw_base64": base64.b64encode(raw).decode(), "raw_sha256": digest(raw), "response": body,
             "response_headers": {k.lower(): v for k, v in response.headers.items()
                                  if k.lower() in {"date", "cts", "cts_flag", "content-type"}},
             "official_spec_url": SPEC_URL, "official_spec_sha256": SPEC_SHA256,
             "code_sha": code_sha(), "run_id": os.getenv("GITHUB_RUN_ID")}
    entry["retained_evidence"] = retain(entry)
    checked(entry)
    return entry


def investor_request(market: str, *, futures=False, quantity=False, minute=False, venue=None) -> dict:
    if market not in {"KOSPI", "KOSDAQ"}:
        raise ValueError("나무 지수 시장 미확인")
    code = ({"KOSPI": "3", "KOSDAQ": "6"} if futures else {"KOSPI": "1", "KOSDAQ": "2"})[market]
    return {"market_cd": venue or ("KRX" if futures else "UNT"), "mrkt_cls_code": code,
            "cycle_cls_code": "7" if minute else "2", "opt_cls_code": "2" if quantity else "1", "cnt": "003"}


def program_request(market: str, *, minute=False, venue="UNT") -> dict:
    return {"market_cd": venue, "mrkt_cls_code": {"KOSPI": "1", "KOSDAQ": "0"}[market],
            "cycle_cls_code": "1" if minute else "2", "data_cls_code": "1", "opt_cls_code": "2", "array_cnt": "003"}

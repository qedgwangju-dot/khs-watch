"""Read-only NAMUH PLUG transport and source evidence.

Only two documented market-data interfaces are allowed. No accounts, orders,
Telegram, or alert state are accessed. Tokens use a 24h encrypted shared cache;
the credential-bearing OAuth URL and response are deliberately never retained.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import re
import threading
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote, quote_plus
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
_OBSERVATIONS = {}
ACTORS = {"외국인계": "frgn_val", "기관": "orgn_val", "개인": "prsn_val", "투신": "ivtr_val", "금융투자": "scrt_val"}
SUBGROUPS = ("scrt_val", "insu_val", "ivtr_val", "bank_val", "mrbn_val", "fund_val", "pe_fund_val")
PROGRAM_FIELDS = {"cha2": "arbt_seln_qty", "cha1": "arbt_shnu_qty", "cha3": "arbt_ntby_qty",
                  "bcha2": "nabt_seln_qty", "bcha1": "nabt_shnu_qty", "bcha3": "nabt_ntby_qty",
                  "tot2": "tot_seln_qty", "tot1": "tot_shnu_qty", "tot3": "tot_ntby_qty"}
NPAY_CASH_UNIT = {"page_url": "https://stock.naver.com/market/stock/kr/trend/trader",
    "bundle_url": "https://ssl.pstatic.net/imgstock/fn/real/pc/_next/static/chunks/app/market/stock/kr/trend/trader/page-e0f16d7ee4fb6a62.js",
    "bundle_sha256": "1fc0aa73bb31e9411961b6dd611dc065afae5405eb70fb10ad1287d29488b274",
    "formatter": "cash diffValue/1e8 -> 억; FUT diffValue -> 계약; 9001 is combined with 9000"}


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
            for representation in {secret, quote(secret, safe=""), quote_plus(secret)}:
                text = text.replace(representation, "[redacted]")
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
        if not isinstance(body, dict):
            raise ValueError("나무 인증 응답 형식 미확인")
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
    if not isinstance(body, dict):
        raise ValueError("나무 응답 블록 형식 미확인")
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


def integer(value) -> int:
    if value is None or isinstance(value, bool):
        raise ValueError("나무 원값 누락")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("나무 원값 형식 오류") from None
    if not parsed.is_finite() or parsed != parsed.to_integral_value():
        raise ValueError("나무 정수 원값 미확인")
    return int(parsed)


def _capture_valid(entry: dict) -> dict:
    raw = base64.b64decode(entry["raw_base64"], validate=True)
    if entry.get("http_status") != 200 or digest(raw) != entry.get("raw_sha256"):
        raise ValueError("독립 원표 HTTP·바이트·해시 불일치")
    body = json.loads(raw)
    if body != entry.get("response"):
        raise ValueError("독립 원표 저장값과 원문 불일치")
    start, end = float(entry["query_started_ts"]), float(entry["received_ts"])
    if not 0 <= end - start <= 120:
        raise ValueError("독립 원표 조회구간 미확인")
    return body


def _daily(entry: dict, path: str, expected: dict) -> tuple[dict, str]:
    body = checked(entry)
    if entry["endpoint"] != path or entry["request"] != expected:
        raise ValueError("나무 시장·거래소·당일 조건 불일치")
    start, end = float(entry["query_started_ts"]), float(entry["received_ts"])
    if not 0 <= end - start <= 120:
        raise ValueError("나무 조회구간 미확인")
    day = dt.datetime.fromtimestamp(end, KST).strftime("%Y%m%d")
    date_field = "bsop_date" if path == PROGRAM else "bsop_hour"
    dates = []
    for row in body["Output_0"]:
        text = row.get(date_field)
        if not isinstance(text, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{2}", text):
            raise ValueError("나무 일별 공표일 형식 미확인")
        parsed = dt.datetime.strptime(text, "%y/%m/%d").strftime("%Y%m%d")
        if path == INVESTORS and row.get("timez12") != parsed[2:] + "000000":
            raise ValueError("나무 일별 날짜와 시계열 충돌")
        dates.append(parsed)
    if dates != sorted(set(dates), reverse=True) or dates[0] != day:
        # Never select an older complete row after rejecting the newest row.
        raise ValueError("나무 최신 일별 원행의 거래일·정렬·중복 불일치")
    if entry.get("response_headers", {}).get("cts_flag") not in {"Y", "N"}:
        raise ValueError("나무 이력 연속조회 상태 미확인")
    return body["Output_0"][0], day


def _investor_values(row: dict, *, quantity=False) -> dict:
    fields = set(SUBGROUPS) | {"prsn_val", "frgn_val", "orgn_val", "etc_orgt_val", "etc_corp_val", "whol_val"}
    values = {key: integer(row.get(key)) for key in fields}
    tolerance = 0 if quantity else 7
    if abs(sum(values[key] for key in SUBGROUPS) - values["orgn_val"]) > tolerance:
        raise ValueError("나무 기관·세부집단 검산 실패")
    if abs(sum(values[key] for key in ("prsn_val", "frgn_val", "orgn_val", "etc_orgt_val", "etc_corp_val"))) > (0 if quantity else 5):
        raise ValueError("나무 투자자 순매수 검산 실패")
    if values["whol_val"] != 0:
        raise ValueError("나무 전체 순매수 검산 실패")
    return values


def _reference_investors(entry: dict, market: str, day: str) -> dict:
    expected = {"tradeType": "KRX", "marketType": market, "bizdate": day, "startIdx": 0, "pageSize": 30}
    if entry.get("request") != expected or entry.get("endpoint") != "/api/domestic/market/trend/time":
        raise ValueError("독립 현물 원표 시장·거래소·날짜 요청 불일치")
    body = _capture_valid(entry)
    rows = body.get("content")
    if not isinstance(rows, list) or not rows:
        raise ValueError("독립 현물 시각 원표 없음")
    result = {}
    for row in rows:
        clock = row.get("time", "")
        if row.get("bizdate") != day or not re.fullmatch(r"\d{6}", str(clock)) or clock in result:
            raise ValueError("독립 현물 원표 날짜·시각 중복 오류")
        dt.datetime.strptime(day + clock, "%Y%m%d%H%M%S")
        raw_values = row.get("netAmounts")
        if not isinstance(raw_values, list):
            raise ValueError("독립 투자자 원표 없음")
        by_actor = {}
        for value in raw_values:
            actor = value.get("investorGubun")
            if actor in by_actor:
                raise ValueError("독립 투자자 코드 중복")
            by_actor[actor] = integer(value.get("diffValue"))
        required = {"1000", "2000", "3000", "3100", "4000", "5000", "6000", "7100", "8000", "9000", "9001"}
        if not required <= set(by_actor):
            raise ValueError("독립 투자자 비교집단 누락")
        mapped = {field: by_actor[code] for field, code in (("scrt_val", "1000"), ("insu_val", "2000"),
            ("ivtr_val", "3000"), ("pe_fund_val", "3100"), ("bank_val", "4000"), ("mrbn_val", "5000"),
            ("fund_val", "6000"), ("etc_corp_val", "7100"), ("prsn_val", "8000"))}
        mapped["frgn_val"] = by_actor["9000"] + by_actor["9001"]
        result[clock] = mapped
    return result


def cash_unit_calibration(entry: dict, reference: dict, market: str, day: str) -> dict:
    if entry.get("request") != investor_request(market, minute=True, venue="KRX"):
        raise ValueError("나무 단위 대조 현물 KRX 요청 불일치")
    body = checked(entry)
    references = _reference_investors(reference, market, day)
    rows = {}
    for row in body["Output_0"]:
        text = str(row.get("bsop_hour") or "")
        if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", text) or row.get("timez12") != "000000" + text.replace(":", ""):
            raise ValueError("나무 현물 단위 대조 시각 충돌")
        clock = text.replace(":", "")
        if clock in rows:
            raise ValueError("나무 현물 단위 대조 시각 중복")
        rows[clock] = _investor_values(row)
    matches = []
    for clock in sorted(set(rows) & set(references), reverse=True):
        source, other = rows[clock], references[clock]
        if sum(bool(v) for v in other.values()) < 3:
            continue  # All-zero rows cannot identify a currency scale.
        factors = [factor for factor in (1, 1000, 1_000_000, 100_000_000)
                   if all(abs(source[field] * factor - value) <= 2 * factor for field, value in other.items())]
        if factors == [1_000_000]:
            matches.append(clock)
    if not matches:
        raise ValueError("나무 현물 단위·외국인계 범위의 같은 시각 독립 대조 미확인")
    return {"raw_to_won": 1_000_000, "unit": "백만원", "calibration_clock": matches[0],
            "date": day, "calibration_scope": "KRX", "same_clock_actor_count": len(references[matches[0]]),
            "unit_contract": NPAY_CASH_UNIT,
            "current_value_independently_verified": False,
            "note": "KRX 동일 시각 원표의 단위·외국인계 분류 대조. 최신 통합 금액 전체의 독립 확인과 구분."}


def parse_cash(entry: dict, calibration: dict, reference: dict, market: str) -> dict:
    row, day = _daily(entry, INVESTORS, investor_request(market))
    raw_values = _investor_values(row)
    unit = cash_unit_calibration(calibration, reference, market, day)
    return {"market": market, "provider": "Namuh", "kind": "cash", "date": day, "scope": "KRX+NXT",
            "source_tr": "IVOUUJTUD04", "unit": "억원", "unit_verified": True,
            "values": {actor: raw_values[field] / 100 for actor, field in ACTORS.items()},
            "source_row": row, "received_ts": entry["received_ts"], "query_started_ts": entry["query_started_ts"],
            "interval_eligible": False, "source_time_verified": False,
            "source_date_verified": True, "source_date_basis": "나무 일별 최신행 날짜·시계열 echo",
            "timestamp_basis": "query_interval", "calibration": unit,
            "raw_sha256": entry["raw_sha256"], "revision_possible": True}


def parse_futures(entry: dict, market: str) -> dict:
    row, day = _daily(entry, INVESTORS, investor_request(market, futures=True, quantity=True))
    values = _investor_values(row, quantity=True)
    return {"market": market, "provider": "Namuh", "kind": "futures_quantity", "date": day, "scope": "KRX",
            "source_tr": "IVOUUJTUD04", "unit": "계약", "unit_verified": True,
            "market_selector": "3" if market == "KOSPI" else "6",
            "product_label": "선물(나무구분3)" if market == "KOSPI" else "KOSDAQ150선물",
            "values": {actor: values[field] for actor, field in ACTORS.items()}, "source_row": row,
            "interval_eligible": False, "source_time_verified": False, "source_date_verified": True,
            "timestamp_basis": "query_interval", "received_ts": entry["received_ts"],
            "raw_sha256": entry["raw_sha256"], "amount_in_won_verified": False,
            "unit_basis": "선물 시장 수량 opt_cls_code=2; 금액으로 환산하지 않음"}


def parse_program(entry: dict, references: dict, market: str) -> dict:
    from market_program_close import _arithmetic, _rows, reference_request
    row, day = _daily(entry, PROGRAM, program_request(market))
    amounts = {field: integer(row.get(name)) for field, name in PROGRAM_FIELDS.items()}
    _arithmetic(amounts, 2)
    latest = {}
    for venue in ("KRX", "NXT"):
        reference = references[venue]
        expected = {**reference_request(market, day, venue), "pageSize": 1}
        if reference.get("request") != expected or reference.get("endpoint") != "/api/domestic/market/trendProgram":
            raise ValueError("독립 프로그램 원표 시장·거래소·날짜 불일치")
        rows = _rows(_capture_valid(reference), day, reference=True)
        clock = max(rows)
        ts = dt.datetime.strptime(day + clock, "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp()
        if ts > float(reference["received_ts"]) + 5:
            raise ValueError("독립 프로그램 원표 미래 시각")
        latest[venue] = (clock, rows[clock])
    factors = [factor for factor in (1, 1000, 1_000_000, 100_000_000)
               if all(abs(value * factor - sum(latest[v][1][field] for v in latest)) <= 2 * factor
                      for field, value in amounts.items())]
    if factors != [1_000_000] or not any(amounts.values()):
        raise ValueError("나무 당일 프로그램 누적액·단위의 독립 원화 대조 미확인")
    return {"market": market, "provider": "Namuh", "kind": "program", "date": day, "scope": "KRX+NXT",
            "source_tr": "IVOUGMMAL01", "unit": "억원", "unit_verified": True,
            "values": {label: amounts[field] / 100 for label, field in (("전체", "tot3"), ("차익", "cha3"), ("비차익", "bcha3"))},
            "source_row": row, "raw_to_won": 1_000_000,
            "independent_latest_cumulative_amounts_verified": True,
            "independent_asof_clocks": {v: latest[v][0] for v in latest},
            "same_clock_verified": len({latest[v][0] for v in latest}) == 1,
            "source_time_verified": False, "interval_eligible": False,
            "source_date_verified": True, "timestamp_basis": "query_interval",
            "received_ts": entry["received_ts"], "raw_sha256": entry["raw_sha256"],
            "investor_breakdown_available": False}


def reference_get(endpoint: str, params: dict) -> dict:
    if endpoint not in {"/api/domestic/market/trend/time", "/api/domestic/market/trendProgram"}:
        raise ValueError("허용하지 않은 공개 대조 표")
    started = time.time()
    try:
        response = requests.get("https://stock.naver.com" + endpoint, params=params, timeout=(5, 10), allow_redirects=False)
    except requests.RequestException as exc:
        raise ValueError("공개 대조 표 통신 실패: " + type(exc).__name__) from None
    try:
        body = response.json()
    except ValueError:
        body = None
    entry = {"provider": "Npay", "endpoint": endpoint, "request": params,
             "query_started_ts": started, "received_ts": time.time(), "http_status": response.status_code,
             "raw_base64": base64.b64encode(response.content).decode(), "raw_sha256": digest(response.content),
             "response": body, "code_sha": code_sha(), "run_id": os.getenv("GITHUB_RUN_ID")}
    entry["retained_evidence"] = retain(entry)
    _capture_valid(entry)
    return entry


def derive_capture(capture: dict) -> dict:
    market = capture["market"]
    source_times = [float(entry["received_ts"]) for entry in capture["sources"].values()]
    if source_times and float(capture["received_ts"]) != max(source_times):
        raise ValueError("나무 묶음 시각은 실제 마지막 원응답 시각이어야 함")
    result = {"provider": "Namuh", "market": market, "received_ts": capture["received_ts"],
              "date": dt.datetime.fromtimestamp(capture["received_ts"], KST).strftime("%Y%m%d"),
              "interval_eligible": False, "components": {}}
    sources = capture["sources"]
    for kind in ("cash", "futures", "program"):
        try:
            if kind == "cash":
                value = parse_cash(sources["cash"], sources["cash_calibration"], sources["cash_reference"], market)
            elif kind == "futures":
                value = parse_futures(sources["futures"], market)
            else:
                value = parse_program(sources["program"], {v: sources["program_" + v] for v in ("KRX", "NXT")}, market)
            result["components"][kind] = value
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            result["components"][kind] = {"status": "held", "reason": _redact(str(exc)), "kind": kind}
    result["complete"] = all(value.get("unit_verified") is True for value in result["components"].values())
    return result


def current(market: str) -> dict:
    from market_program_close import reference_request
    now = time.time()
    with _LOCK:
        old = _OBSERVATIONS.get(market)
        if old and 0 <= now - old["checked_ts"] < 60:
            return old["result"]  # Preserve actual source times on a cache hit.
    day = dt.datetime.fromtimestamp(now, KST).strftime("%Y%m%d")
    sources, errors = {}, {}
    queries = {
        "cash": lambda: request(INVESTORS, investor_request(market)),
        "cash_calibration": lambda: request(INVESTORS, investor_request(market, minute=True, venue="KRX")),
        "cash_reference": lambda: reference_get("/api/domestic/market/trend/time", {
            "tradeType": "KRX", "marketType": market, "bizdate": day, "startIdx": 0, "pageSize": 30}),
        "futures": lambda: request(INVESTORS, investor_request(market, futures=True, quantity=True)),
        "program": lambda: request(PROGRAM, program_request(market)),
        "program_KRX": lambda: reference_get("/api/domestic/market/trendProgram", {**reference_request(market, day, "KRX"), "pageSize": 1}),
        "program_NXT": lambda: reference_get("/api/domestic/market/trendProgram", {**reference_request(market, day, "NXT"), "pageSize": 1}),
    }
    for name, collect in queries.items():
        try:
            sources[name] = collect()
        except Exception as exc:
            errors[name] = {"type": type(exc).__name__, "reason": _redact(str(exc))}
            if name == "cash" and "인증" in str(exc):
                break  # No repeated authentication attempts for the remaining quote blocks.
    capture = {"schema": "namuh_supplement_v1", "market": market, "sources": sources,
               "errors": errors, "received_ts": max((x["received_ts"] for x in sources.values()), default=now),
               "code_sha": code_sha(), "run_id": os.getenv("GITHUB_RUN_ID")}
    result = derive_capture(capture)
    result["evidence"] = retain_capture(capture)
    with _LOCK:
        _OBSERVATIONS[market] = {"checked_ts": time.time(), "result": result}
    return result


def retain_capture(capture: dict) -> dict:
    folder = Path(os.getenv("MARKET_SOURCE_EVIDENCE_DIR", "out/market_source_evidence"))
    folder.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(capture, ensure_ascii=False, sort_keys=True).encode()
    path = folder / (digest(raw) + ".json")
    path.write_bytes(raw)
    return {"path": str(path), "sha256": digest(raw)}


def _proof(bundle: dict) -> dict:
    root = Path(os.getenv("MARKET_SOURCE_EVIDENCE_DIR", "out/market_source_evidence")).resolve()
    evidence = bundle.get("evidence") or {}
    path = Path(evidence.get("path", "")).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("나무 원자료 증거 파일 미확보")
    raw = path.read_bytes()
    if digest(raw) != evidence.get("sha256"):
        raise ValueError("나무 원자료 증거 해시 불일치")
    verified = derive_capture(json.loads(raw))
    for key in ("provider", "market", "date", "received_ts", "interval_eligible", "components", "complete"):
        if verified.get(key) != bundle.get(key):
            raise ValueError("나무 렌더 원값·시장·단위·기준일 불일치")
    return verified


def lines(bundle: dict | None, market: str, now_ts=None) -> list[str]:
    if not bundle:
        return []
    now_ts = time.time() if now_ts is None else now_ts
    try:
        day = dt.datetime.fromtimestamp(now_ts, KST).strftime("%Y%m%d")
        if bundle.get("market") != market or bundle.get("date") != day or not 0 <= now_ts - bundle["received_ts"] <= 120:
            raise ValueError("나무 보완 시장·거래일·조회시각 불일치")
        verified = _proof(bundle)
        stamp = dt.datetime.fromtimestamp(bundle["received_ts"], KST)
        result = ["", f"<b>나무 당일누적 · {stamp:%m/%d %H:%M} 조회</b>"]
        def number(value):
            rounded = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return "0" if rounded == 0 else format(rounded, "+,f")
        for kind, label in (("cash", "현물/억원(KRX+NXT)"), ("program", "프로그램/억원(KRX+NXT)"),
                            ("futures", "선물3/계약(KRX)" if market == "KOSPI" else "KQ150선물/계약(KRX)")):
            block = verified["components"][kind]
            if block.get("status") == "held":
                result.append("• " + label + " 확인 보류")
                continue
            labels = ("전체", "차익", "비차익") if kind == "program" else tuple(ACTORS)
            result.append("• " + label + " " + " / ".join(("외인계" if actor == "외국인계" else actor) + " " + number(block["values"][actor]) for actor in labels))
        result.append("공표시각 미제공 · 투신·금융투자⊂기관 · 구간수급 아님 · 프로그램 주체·선물금액 미확인")
        plain = html.unescape(re.sub(r"<[^>]+>", "", "\n".join(result)))
        if len(plain) > 290:
            raise ValueError("나무 보완 표시 예산 초과")
        return result
    except (KeyError, ValueError, TypeError, OSError):
        return ["• 나무 당일누적 보완: 시장·날짜·단위·원자료 확인 보류"]


def enrich_snapshot(snapshot: dict, market: str) -> dict:
    if not configured():
        return snapshot
    try:
        supplement = current(market)
    except Exception:
        # A source/evidence failure must not stop the existing price monitor.
        snapshot["cash_supplement"] = {"provider": "Namuh", "market": market, "status": "held"}
        return snapshot
    snapshot["cash_supplement"] = supplement
    if isinstance(snapshot.get("현물"), dict):
        snapshot["현물"]["cash_supplement"] = supplement
    snapshot["namuh_supplement_coverage"] = {"cumulative": supplement["complete"], "incident_interval": False,
        "program_by_investor": False, "futures_amount_in_won": False}
    return snapshot

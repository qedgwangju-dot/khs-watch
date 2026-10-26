"""Read-only Kiwoom supplementary cash and independently checked program data.

ka10051 has no source date/time echo. Its amounts are a requested-day cumulative
observation, never an incident-window endpoint. ka90005 clocks are accepted only
after exact-date/clock KRX+NXT won originals reconcile all nine amount fields.
"""
from __future__ import annotations

import base64
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
BASE = "https://api.kiwoom.com"
SPEC_COMMIT = "953e5dbff123f437ab4d11a78a95191a685eb51f"
SPEC_SHA256 = "42a7b3912c9d9588c83bdc2db7779c8d2e038703a2b5562e54ef46ae905cba79"
PATHS = {"ka10051": "/api/dostk/sect", "ka90005": "/api/dostk/mrkcond"}
CODES = {"KOSPI": ("0", "001_AL", "P001_AL01"),
         "KOSDAQ": ("1", "101_AL", "P101_AL02")}
ACTORS = {"외국인": "frgnr_netprps", "기관": "orgn_netprps", "개인": "ind_netprps",
          "투신": "invtrt_netprps", "금융투자": "sc_netprps", "보험": "insrnc_netprps",
          "은행": "bank_netprps", "종금": "jnsinkm_netprps", "기금": "endw_netprps",
          "사모펀드": "samo_fund_netprps", "기타법인": "etc_corp_netprps",
          "기타외국인": "native_trmt_frgnr_netprps", "국가": "natn_netprps"}
PROGRAM_FIELDS = {"tot1": "all_buy", "tot2": "all_sel", "tot3": "all_netprps",
                  "cha1": "dfrt_trde_buy", "cha2": "dfrt_trde_sel", "cha3": "dfrt_trde_netprps",
                  "bcha1": "ndiffpro_trde_buy", "bcha2": "ndiffpro_trde_sel", "bcha3": "ndiffpro_trde_netprps"}
_LOCK = threading.RLock()
_TOKEN = ""
_TOKEN_UNTIL = 0.0
_NEXT = 0.0
_CACHE = {}
_CODE_SHA = None


def code_sha() -> str | None:
    global _CODE_SHA
    if _CODE_SHA is None:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True, timeout=5)
        _CODE_SHA = result.stdout.strip() if result.returncode == 0 else ""
    return _CODE_SHA or None


def configured() -> bool:
    return (os.getenv("MARKET_SOURCE_OFFLINE") != "1"
            and bool(os.getenv("KIWOOM_APPKEY", "").strip() and os.getenv("KIWOOM_SECRETKEY", "").strip()))


def integer(value, *, repeated_negative=False) -> int:
    if value is None or isinstance(value, bool):
        raise ValueError("금액 원값 누락")
    text = str(value).strip().replace(",", "")
    # Actual ka90005 can prepend its direction sign to an already negative
    # amount. It is a negative representation, not a mathematical double minus.
    if repeated_negative and re.fullmatch(r"--\d+", text):
        text = text[1:]
    if not re.fullmatch(r"[+-]?\d+", text):
        raise ValueError("정수 금액 형식 미확인")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("금액 형식 오류") from exc
    return int(value)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checked(entry: dict) -> dict:
    raw = base64.b64decode(entry["raw_base64"], validate=True)
    if entry.get("http_status") != 200 or digest(raw) != entry.get("raw_sha256"):
        raise ValueError("키움 원응답 바이트·해시 불일치")
    body = json.loads(raw)
    if not isinstance(body, dict) or body.get("return_code") != 0:
        raise ValueError("키움 조회 미승인")
    if body != entry.get("response"):
        raise ValueError("키움 저장 응답과 원문 불일치")
    return body


def _retain(entry: dict) -> dict:
    directory = Path(os.getenv("MARKET_SOURCE_EVIDENCE_DIR", "out/market_source_evidence"))
    directory.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()
    path = directory / (digest(raw) + ".json")
    path.write_bytes(raw)
    return {"path": str(path), "sha256": digest(raw), "response_sha256": entry["raw_sha256"]}


def _token() -> str:
    global _TOKEN, _TOKEN_UNTIL
    with _LOCK:
        if _TOKEN and time.time() < _TOKEN_UNTIL:
            return _TOKEN
        if not configured():
            raise ValueError("키움 인증 설정 없음")
        try:
            r = requests.post(BASE + "/oauth2/token", json={"grant_type": "client_credentials",
                "appkey": os.environ["KIWOOM_APPKEY"], "secretkey": os.environ["KIWOOM_SECRETKEY"]},
                timeout=(5, 10), allow_redirects=False)
            body = r.json()
            if r.status_code != 200 or body.get("return_code") != 0 or not body.get("token"):
                message = str(body.get("return_msg") or "")
                for secret in (os.environ["KIWOOM_APPKEY"], os.environ["KIWOOM_SECRETKEY"], body.get("token")):
                    if secret:
                        message = message.replace(str(secret), "[redacted]")
                raise ValueError("키움 인증 미승인 (HTTP " + str(r.status_code) + ", code "
                                 + str(body.get("return_code")) + "): " + message[:240])
            _TOKEN = str(body["token"])
            _TOKEN_UNTIL = time.time() + 20 * 60
            return _TOKEN
        except requests.RequestException as exc:
            raise ValueError("키움 인증 통신 실패: " + type(exc).__name__) from None


def request(api_id: str, body: dict, *, next_key="") -> dict:
    """Only the two public market-data TRs; no account/order interface."""
    global _NEXT
    if api_id not in PATHS:
        raise ValueError("허용하지 않은 키움 TR")
    token = _token()
    with _LOCK:
        delay = _NEXT - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _NEXT = time.monotonic() + 0.55
    started = time.time()
    try:
        r = requests.post(BASE + PATHS[api_id], json=body,
            headers={"Content-Type": "application/json;charset=UTF-8", "api-id": api_id,
                     "authorization": "Bearer " + token, "cont-yn": "Y" if next_key else "N", "next-key": next_key},
            timeout=(5, 10), allow_redirects=False)
    except requests.RequestException as exc:
        raise ValueError("키움 수급 통신 실패: " + type(exc).__name__) from None
    raw = r.content
    if any(secret and secret.encode() in raw for secret in
           (token, os.getenv("KIWOOM_APPKEY"), os.getenv("KIWOOM_SECRETKEY"))):
        raise ValueError("인증정보 포함 응답 보존 거절")
    entry = {"provider": "Kiwoom", "api_id": api_id, "endpoint": PATHS[api_id], "request": body,
             "query_started_ts": started, "received_ts": time.time(), "http_status": r.status_code,
             "raw_base64": base64.b64encode(raw).decode(), "raw_sha256": digest(raw),
             "response": r.json(), "cont_yn": r.headers.get("cont-yn"),
             "next_key": r.headers.get("next-key", ""), "request_next_key": next_key,
             "official_spec_commit": SPEC_COMMIT, "official_spec_sha256": SPEC_SHA256,
             "code_sha": code_sha(), "run_id": os.getenv("GITHUB_RUN_ID")}
    _checked(entry)
    entry["retained_evidence"] = _retain(entry)
    return entry


def cash_request(market: str, day: str) -> dict:
    return {"mrkt_tp": CODES[market][0], "amt_qty_tp": "0", "base_dt": day, "stex_tp": "3"}


def parse_cash(entry: dict, market: str) -> dict:
    body = _checked(entry)
    day = str(entry.get("request", {}).get("base_dt", ""))
    received = float(entry["received_ts"])
    if not 0 <= received - float(entry["query_started_ts"]) <= 120:
        raise ValueError("키움 현물 조회 구간 미확인")
    if entry.get("api_id") != "ka10051" or entry.get("request") != cash_request(market, day):
        raise ValueError("키움 현물 요청 시장·단위·거래소 불일치")
    if day != dt.datetime.fromtimestamp(received, KST).strftime("%Y%m%d"):
        raise ValueError("키움 현물 요청 거래일 불일치")
    if entry.get("cont_yn") != "N":
        raise ValueError("키움 업종 전체 페이지 미확보")
    rows = body.get("inds_netprps")
    if not isinstance(rows, list) or not rows:
        raise ValueError("키움 현물·업종 원표 없음")
    aggregate = [r for r in rows if r.get("inds_cd") == CODES[market][1]]
    if len(aggregate) != 1:
        raise ValueError("키움 정확 시장 통합 집계행 미확인")
    row = aggregate[0]
    expected_name = "종합(" + market + ")"
    if row.get("inds_nm") != expected_name:
        raise ValueError("키움 시장 집계 이름 불일치")
    values = {}
    for actor, field in ACTORS.items():
        values[actor] = integer(row[field]) if row.get(field) not in (None, "") else None
    if any(values[a] is None for a in ("외국인", "기관", "개인", "기타법인", "기타외국인", "국가")):
        raise ValueError("키움 투자자 검산 집단 누락")
    disjoint = ("외국인", "기관", "개인", "기타법인", "기타외국인", "국가")
    residual = sum(values[a] for a in disjoint)
    if abs(residual) > len(disjoint):
        raise ValueError("키움 투자자 순매수 합계 검산 실패")
    subgroups = ("금융투자", "보험", "투신", "은행", "종금", "기금", "사모펀드")
    subgroup_residual = None
    if all(values[a] is not None for a in subgroups):
        subgroup_residual = sum(values[a] for a in subgroups) - values["기관"]
        if abs(subgroup_residual) > len(subgroups):
            raise ValueError("키움 기관 세부 합계 검산 실패")
    if body.get("date") not in (None, day) or body.get("base_dt") not in (None, day):
        raise ValueError("키움 반환 거래일 충돌")
    return {"market": market, "source_tr": "ka10051", "provider": "Kiwoom", "date": day,
            "scope": "KRX+NXT", "unit": "억원", "unit_verified": True, "values": values,
            "source_row": row, "industry_row_count": len(rows),
            "query_started_ts": float(entry["query_started_ts"]), "received_ts": received,
            "timestamp_basis": "query_interval", "source_time_verified": False,
            "source_date_basis": "base_dt 요청 범위; 응답 날짜·시각 echo 없음",
            "interval_eligible": False, "investor_residual_eok": residual,
            "institution_subgroup_residual_eok": subgroup_residual,
            "request": entry["request"], "raw_sha256": entry["raw_sha256"],
            "evidence": entry.get("retained_evidence")}


def cash_current(market: str, *, call=None) -> dict:
    call = call or request
    now = time.time()
    day = dt.datetime.fromtimestamp(now, KST).strftime("%Y%m%d")
    with _LOCK:
        old = _CACHE.get(("cash", market))
        if old and old.get("date") == day and 0 <= now - old["received_ts"] < 60:
            return old  # Keep original observation time; cache access is not a query.
    result = parse_cash(call("ka10051", cash_request(market, day)), market)
    with _LOCK:
        _CACHE[("cash", market)] = result
    return result


def optional_cash(market: str) -> dict | None:
    if not configured():
        return None
    try:
        return cash_current(market)
    except Exception as exc:
        return {"status": "held", "market": market,
                "reason": "키움 원자료 검증 보류: " + type(exc).__name__}


def program_request(market: str, day: str) -> dict:
    return {"date": day, "amt_qty_tp": "1", "mrkt_tp": CODES[market][2],
            "min_tic_tp": "1", "stex_tp": "3"}


def parse_program(entry: dict, market: str, references: dict, *, target_clock=None) -> dict:
    from market_program_close import _arithmetic, _rows, reference_request
    body = _checked(entry)
    day = str(entry.get("request", {}).get("date", ""))
    received = float(entry["received_ts"])
    if (entry.get("api_id") != "ka90005" or entry.get("request") != program_request(market, day)
            or day != dt.datetime.fromtimestamp(received, KST).strftime("%Y%m%d")):
        raise ValueError("키움 프로그램 시장·날짜·단위 요청 불일치")
    rows = body.get("prm_trde_trnsn")
    if not isinstance(rows, list) or not rows:
        raise ValueError("키움 프로그램 원표 없음")
    stamps = [str(row.get("cntr_tm", "")) for row in rows]
    if any(not re.fullmatch(r"\d{6}", x) for x in stamps) or len(stamps) != len(set(stamps)):
        raise ValueError("키움 프로그램 시각 누락·중복")
    clock = target_clock or max(stamps)
    chosen = [row for row in rows if row["cntr_tm"] == clock]
    if len(chosen) != 1:
        raise ValueError("요청한 정확 프로그램 시각 원표 없음")
    row = chosen[0]
    ts = dt.datetime.strptime(day + clock, "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp()
    if ts > received + 5:
        raise ValueError("미래 프로그램 표본")
    amounts = {k: integer(row.get(v), repeated_negative=k.endswith('3')) for k, v in PROGRAM_FIELDS.items()}
    _arithmetic(amounts, 2)
    reference_rows = {}
    for venue in ("KRX", "NXT"):
        ref = references.get(venue) or {}
        if ref.get("request") != reference_request(market, day, venue):
            raise ValueError("프로그램 독립 원표 모집단·날짜 요청 불일치")
        raw = base64.b64decode(ref.get("raw_base64", ""), validate=True)
        if (ref.get("http_status") != 200 or digest(raw) != ref.get("raw_sha256")
                or json.loads(raw) != ref.get("response")):
            raise ValueError("프로그램 독립 원표 바이트·해시 불일치")
        reference_rows[venue] = _rows(ref["response"], day, reference=True)
        if clock not in reference_rows[venue]:
            raise ValueError("프로그램 동일 시각 KRX·NXT 원표 미확보")
    for field, value in amounts.items():
        expected = sum(reference_rows[v][clock][field] for v in ("KRX", "NXT"))
        if abs(value * 1_000_000 - expected) > 2_000_000:
            raise ValueError("프로그램 독립 원화 원표와 불일치: " + field)
    return {"market": market, "source_tr": "ka90005", "provider": "Kiwoom", "date": day,
            "scope": "KRX+NXT", "source_scope_verified": True, "unit": "억원", "unit_verified": True,
            "sample_ts": ts, "received_ts": received, "query_started_ts": entry["query_started_ts"],
            "timestamp_basis": "provider_time_and_independent_dated_won_rows", "source_time_verified": True,
            "time": clock, "source_date_basis": "같은 날짜·시각 KRX+NXT 원화 원표 독립 대조",
            "전체": amounts['tot3'] / 100, "차익": amounts['cha3'] / 100, "비차익": amounts['bcha3'] / 100,
            "차익비차익합": (amounts['cha3'] + amounts['bcha3']) / 100,
            "전체대비차이": (amounts['tot3'] - amounts['cha3'] - amounts['bcha3']) / 100,
            "표본시차초": 0, "source_row": row, "raw_sha256": entry["raw_sha256"],
            "evidence": entry.get("retained_evidence"), "independent_population_unit_and_clock_verified": True,
            "references": {v: {"raw_sha256": references[v]["raw_sha256"],
                               "evidence": references[v].get("retained_evidence")} for v in references}}


def program_current(market: str, *, call=None, get=None) -> dict:
    from market_program_close import reference_request
    now = time.time()
    day = dt.datetime.fromtimestamp(now, KST).strftime("%Y%m%d")
    call, get = call or request, get or requests.get
    entry = call("ka90005", program_request(market, day))
    references = {}
    for venue in ("KRX", "NXT"):
        params = reference_request(market, day, venue)
        start = time.time()
        r = get("https://stock.naver.com/api/domestic/market/trendProgram?" + urlencode(params), timeout=6)
        ref = {"provider": "Npay public program table", "request": params, "http_status": r.status_code,
               "query_started_ts": start, "received_ts": time.time(), "raw_base64": base64.b64encode(r.content).decode(),
               "raw_sha256": digest(r.content), "response": r.json()}
        ref["retained_evidence"] = _retain(ref)
        references[venue] = ref
    return parse_program(entry, market, references)


def enrich_snapshot(snapshot: dict, market: str) -> dict:
    """Optional supplements never stop price monitoring or weaken an LS gate."""
    if not configured():
        return snapshot
    now = time.time()
    for kind, collect in (("cash", cash_current), ("program", program_current)):
        key = ("supplement", kind, market)
        with _LOCK:
            previous = _CACHE.get(key)
        if previous and 0 <= now - previous["checked_ts"] < 60:
            value = previous["result"]
        else:
            try:
                value = collect(market)
            except Exception as exc:
                # Credential-bearing transport details must not enter an alert.
                value = {"status": "held", "market": market,
                         "reason": "키움 원자료 검증 보류: " + type(exc).__name__}
            with _LOCK:
                _CACHE[key] = {"checked_ts": now, "result": value}
        if kind == "cash":
            snapshot["cash_supplement"] = value
            if isinstance(snapshot.get("현물"), dict):
                snapshot["현물"]["cash_supplement"] = value
        else:
            snapshot["program_supplement"] = value
            stamp = value.get("sample_ts")
            # Preserve the original rejected/older source separately. A cached
            # response keeps its original source time and never becomes fresh.
            if (value.get("unit_verified") is True and stamp is not None
                    and -5 <= time.time() - float(stamp) <= 90):
                snapshot.setdefault("alternate_sources", {})["프로그램_LS"] = snapshot.get("프로그램")
                snapshot["프로그램"] = value
                old_error = snapshot.get("errors", {}).pop("프로그램", None)
                if old_error:
                    snapshot.setdefault("recovered_source_errors", {})["프로그램_LS"] = old_error
    snapshot["source_coverage"] = {
        "cash_cumulative": (snapshot.get("cash_supplement") or {}).get("unit_verified") is True,
        "cash_interval_from_kiwoom": False,
        "program_independently_verified": (snapshot.get("프로그램") or {}).get("independent_population_unit_and_clock_verified") is True,
        "kiwoom_index_futures_available": False,
    }
    return snapshot


def _cash_proof(block: dict) -> None:
    evidence = block.get("evidence") or {}
    root = Path(os.getenv("MARKET_SOURCE_EVIDENCE_DIR", "out/market_source_evidence")).resolve()
    path = Path(evidence.get("path", "")).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("키움 원응답 증거 미확보")
    raw = path.read_bytes()
    if digest(raw) != evidence.get("sha256"):
        raise ValueError("키움 증거 파일 해시 불일치")
    original = parse_cash(json.loads(raw), block["market"])
    for field in ("market", "date", "scope", "unit", "values", "source_row", "received_ts",
                  "query_started_ts", "raw_sha256", "interval_eligible", "source_time_verified"):
        if block.get(field) != original.get(field):
            raise ValueError("키움 당일 누적값·범위·시각 변조")


def cash_lines(block: dict | None, market: str, now_ts=None) -> list[str]:
    if not block:
        return []
    now_ts = time.time() if now_ts is None else now_ts
    if block.get("status") == "held":
        return ["• 키움 보완 조회 보류: " + html.escape(str(block.get("reason", "원자료 미확인"))[:80])]
    try:
        if block['market'] != market or block['date'] != dt.datetime.fromtimestamp(now_ts, KST).strftime('%Y%m%d'):
            raise ValueError("시장·거래일 불일치")
        if not 0 <= now_ts - float(block['received_ts']) <= 120:
            raise ValueError("조회 표본 120초 초과")
        if block.get('unit_verified') is not True or block.get('interval_eligible') is not False:
            raise ValueError("단위·사용 범위 불일치")
        _cash_proof(block)
        values = block['values']
        stamp = dt.datetime.fromtimestamp(block['received_ts'], KST)
        lines = ["", "<b>키움 당일 누적 현물 수급 · KRX+NXT</b>",
                 f"• 요청일 {block['date']} · 조회 {stamp:%H:%M:%S} KST · 억원"]
        for actor in ("외국인", "기관", "개인", "투신", "금융투자"):
            value = values.get(actor)
            label = actor + "(기관 내)" if actor in {"투신", "금융투자"} else actor
            lines.append(f"• {label} " + (f"<b>{value:+,}억원</b>" if value is not None else "확인 보류(원값 없음)"))
        lines.append("• 원자료 날짜·시각 미제공. 사건 구간·5분 수급을 대신하지 않습니다.")
        # Existing structured enrichment compacts to 3800 visible characters.
        # Keep this separate tail within the remaining Telegram budget.
        visible = html.unescape(re.sub(r"<[^>]+>", "", "\n".join(lines)))
        if len(visible) > 280:
            raise ValueError("키움 누적 표시 길이 확인 보류")
        return lines
    except (KeyError, TypeError, ValueError, OSError):
        return ["• 키움 당일 누적 현물 보완: 시장·거래일·단위·조회시각 확인 보류"]

"""Same-day, exact KRX-close-clock program cumulative amounts for close messages.

The incident monitor's t1640 deltas keep their original unverified scale. This
reader uses the direct U t1662 cumulative row, never sums intraday rows. Its
currency scale must uniquely reconcile with same-date, same-clock KRX + NXT
won originals across all nine amounts at the latest common clock in that response. The close
row is checked separately when both independent venues publish that clock.

Npay's public program table renders these raw amount fields through module
53890 Lg: Math.round(amount / 1e8), with unit '억'; its chart uses y4 amount /
1e8 and '억원'. The source URLs/hashes are pinned below as the unit contract,
not as a substitute for the fresh dated amount responses collected each run.
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
import subprocess
import threading
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
TR = "t1662"
RAW_TO_WON = 1_000_000
ROUNDING_RAW = 2
UNIT_CONTRACT = {
    "reference_unit": "KRW",
    "amount_divisor_to_eokwon": 100_000_000,
    "table_url": "https://stock.naver.com/market/stock/kr/trend/program",
    "table_bundle_url": "https://ssl.pstatic.net/imgstock/fn/real/pc/_next/static/chunks/app/market/stock/kr/trend/program/page-203ed8bfa92a68bc.js",
    "formatter_bundle_url": "https://ssl.pstatic.net/imgstock/fn/real/pc/_next/static/chunks/12945-3945748613dfbec4.js",
    "formatter_sha256": "0611045e197a81e7a14d377908524cbded3af99c84507679f4f1bebaa49cfb62",
    "formatter": "53890.Lg=Math.round(amount/1e8); table unit=억; chart y4=amount/1e8, tooltip unit=억원",
}
FIELDS = {
    "tot3": "totalDiffPureBuyAmt", "tot1": "totalDiffBuyAmt", "tot2": "totalDiffSellAmt",
    "cha3": "diffPureBuyAmt", "cha1": "diffBuyAmt", "cha2": "diffSellAmt",
    "bcha3": "biDiffPureBuyAmt", "bcha1": "biDiffBuyAmt", "bcha2": "biDiffSellAmt",
}
_LOCK = threading.Lock()
_NEXT = 0.0


def _pace() -> None:
    global _NEXT
    with _LOCK:
        wait = _NEXT - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _NEXT = time.monotonic() + 1.1


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _integer(value) -> int:
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        raise ValueError("누적 금액 누락")
    try:
        result = Decimal(str(value).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("누적 금액 형식 오류") from exc
    if not result.is_finite() or result != result.to_integral_value():
        raise ValueError("누적 금액의 정수 원표 확인 불가")
    return int(result)


def _amounts(row: dict, reference: bool = False) -> dict:
    return {key: _integer(row.get(field if reference else key)) for key, field in FIELDS.items()}


def _arithmetic(amounts: dict, tolerance: int) -> None:
    for net, buy, sell in (("tot3", "tot1", "tot2"), ("cha3", "cha1", "cha2"),
                           ("bcha3", "bcha1", "bcha2")):
        if amounts[buy] < 0 or amounts[sell] < 0:
            raise ValueError("누적 매수·매도 금액 음수")
        if abs(amounts[buy] - amounts[sell] - amounts[net]) > tolerance:
            raise ValueError("매수−매도와 순매수 원표 불일치")
    for tail in ("1", "2", "3"):
        if abs(amounts["cha" + tail] + amounts["bcha" + tail] - amounts["tot" + tail]) > tolerance:
            raise ValueError("전체와 차익·비차익 원표 불일치")


def _clock(clock, day: str) -> str:
    text = str(clock or "").strip()
    if len(text) != 6 or not text.isdigit():
        raise ValueError("프로그램 원표 시각 확인 불가")
    dt.datetime.strptime(day + text, "%Y%m%d%H%M%S")
    return text


def _rows(payload: dict, day: str, reference: bool = False) -> dict:
    source = payload.get("content" if reference else "t1662OutBlock")
    if not isinstance(source, list) or not source:
        raise ValueError("프로그램 시간별 원표 없음")
    result = {}
    for row in source:
        if not isinstance(row, dict):
            raise ValueError("프로그램 시간별 원표 형식 오류")
        if reference and str(row.get("bizdate") or "") != day:
            raise ValueError("원화 대조 원표의 거래일 불일치")
        if not reference and row.get("date") is not None and str(row["date"]) != day:
            raise ValueError("LS 원표의 거래일 불일치")
        clock = _clock(row.get("time"), day)
        if clock in result:
            raise ValueError("프로그램 같은 시각 원표 중복")
        values = _amounts(row, reference)
        _arithmetic(values, 0 if reference else ROUNDING_RAW)
        result[clock] = values
    return result


def derive(market: str, close_ts: float, ls: dict, references: dict) -> dict:
    """Pure source replay, also used again immediately before rendering."""
    if market not in ("KOSPI", "KOSDAQ"):
        raise ValueError("프로그램 시장 확인 불가")
    close = dt.datetime.fromtimestamp(close_ts, KST)
    day, cutoff = close.strftime("%Y%m%d"), close.strftime("%H%M%S")
    expected = {"t1662InBlock": {"gubun": "0" if market == "KOSPI" else "1",
                               "gubun1": "0", "gubun3": "0", "exchgubun": "U"}}
    if ls.get("request") != expected:
        raise ValueError("LS 시장·당일·금액·통합 요청 불일치")
    body = ls.get("response") or {}
    if str(body.get("rsp_cd") or "") not in ("0000", "00000"):
        raise ValueError("LS 프로그램 원표 조회 실패")
    chart = _rows(body, day)
    if cutoff not in chart:
        raise ValueError("실제 장마감 시각 원표 없음 — 직전 값으로 대체하지 않음")
    by_venue = {}
    for venue in ("KRX", "NXT"):
        ref = references.get(venue) or {}
        if ref.get("request") != reference_request(market, day, venue):
            raise ValueError("원화 대조 원표의 시장·거래소·날짜 요청 불일치")
        by_venue[venue] = _rows(ref.get("response") or {}, day, reference=True)
    clocks = sorted(set(chart) & set(by_venue["KRX"]) & set(by_venue["NXT"]))
    clocks = [key for key in clocks if key <= cutoff][-1:]
    if not clocks:
        raise ValueError("동일 날짜·동일 시각의 단위 대조 원표 미확보")
    independent = {key: {field: by_venue["KRX"][key][field] + by_venue["NXT"][key][field]
                         for field in FIELDS} for key in clocks}
    factors = [factor for factor in (1, 1_000, RAW_TO_WON, 100_000_000)
               if all(abs(chart[key][field] * factor - independent[key][field]) <= ROUNDING_RAW * factor
                      for key in clocks for field in FIELDS)]
    if factors != [RAW_TO_WON]:
        raise ValueError("원화 환산 단위가 유일하게 대조되지 않음")
    independent_close = cutoff in by_venue["KRX"] and cutoff in by_venue["NXT"]
    if independent_close:
        for field in FIELDS:
            other = by_venue["KRX"][cutoff][field] + by_venue["NXT"][cutoff][field]
            if abs(chart[cutoff][field] * RAW_TO_WON - other) > ROUNDING_RAW * RAW_TO_WON:
                raise ValueError("장마감 시각 누적액의 원화 대조 불일치")
    values = {label: chart[cutoff][field] * RAW_TO_WON
              for label, field in (("전체", "tot3"), ("차익", "cha3"), ("비차익", "bcha3"))}
    return {"market": market, "date": day, "source_time": cutoff, "source_tr": TR,
            "exchange": "U", "scope": "KRX+NXT", "metric": "당일 누적 순매수",
            "unit_verified": True, "raw_unit": "백만원", "raw_to_won": RAW_TO_WON,
            "amounts_won": values, "raw_close_row": chart[cutoff],
            "unit_calibration_clocks": clocks, "close_amount_independently_checked": independent_close,
            "net_component_residual_won": values["전체"] - values["차익"] - values["비차익"],
            "source_date_basis": "당일 요청 및 같은 거래일의 시각별 원화 원표 대조; LS 날짜 echo 없음",
            "precision_note": "백만원 원표 환산액; 원 단위 실측값 아님", "revisable": True,
            "nxt_daily_close": False}


def reference_request(market: str, day: str, venue: str) -> dict:
    return {"tradeType": venue, "krxMarketType": market, "bizdate": day,
            "startIdx": 0, "pageSize": 100, "periodType": "TIME"}


def _runtime() -> dict:
    root = Path(__file__).resolve().parents[1]
    commit = None
    try:
        probe = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                               capture_output=True, text=True, timeout=3, check=False)
        if probe.returncode == 0:
            commit = probe.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return {"actual_checkout_sha": commit, "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "collector_code_sha256": _hash(Path(__file__).read_bytes()),
            "watch_code_sha256": _hash((root / "scripts/kospi_shock_episode_watch.py").read_bytes())}


def _check_captures(result: dict) -> None:
    ls = result["ls"]
    entries = [(ls.get("transport") or {}, ls.get("response"))]
    transport = entries[0][0]
    if (transport.get("endpoint") != "/stock/program" or transport.get("tr_cd") != TR
            or transport.get("request") != ls.get("request")):
        raise ValueError("LS 원응답의 요청·TR 대조 불일치")
    entries += [(entry, entry.get("response")) for entry in result["references"].values()]
    for receipt, response in entries:
        original = base64.b64decode(receipt.get("raw_base64", ""), validate=True)
        if receipt.get("http_status") != 200 or not original or _hash(original) != receipt.get("raw_sha256"):
            raise ValueError("마감 누적액 원응답 HTTP·바이트·해시 대조 실패")
        if json.loads(original) != response:
            raise ValueError("마감 누적액 원응답과 저장 원표 불일치")
        start, end = float(receipt["query_started_ts"]), float(receipt["received_ts"])
        if not result["close_ts"] <= start <= end <= result["received_ts"]:
            raise ValueError("마감 누적액 원응답 조회시각 불일치")
        day = dt.datetime.fromtimestamp(result["close_ts"], KST).date()
        if dt.datetime.fromtimestamp(end, KST).date() != day:
            raise ValueError("마감 누적액 원응답 조회날짜 불일치")


def collect(token: str, market: str, close_ts: float, post, get=None) -> dict:
    """Only read sources; each market can fail closed without losing its close alert."""
    started = time.time()
    close = dt.datetime.fromtimestamp(close_ts, KST)
    day = close.strftime("%Y%m%d")
    result = {"schema": "program_close_cumulative_v1", "market": market, "close_ts": close_ts,
              "query_started_ts": started, "status": "held", "ls": {}, "references": {},
              "unit_contract": UNIT_CONTRACT, "runtime": _runtime()}
    try:
        if dt.datetime.fromtimestamp(started, KST).strftime("%Y%m%d") != day or started < close_ts:
            raise ValueError("실제 마감 전 또는 조회 날짜 불일치")
        if market not in ("KOSPI", "KOSDAQ"):
            raise ValueError("프로그램 시장 확인 불가")
        request = {"t1662InBlock": {"gubun": "0" if market == "KOSPI" else "1",
                                   "gubun1": "0", "gubun3": "0", "exchgubun": "U"}}
        result["ls"] = {"request": request, "transport": {}}
        _pace()
        result["ls"]["response"] = post(token, "/stock/program", TR, request, max_attempts=1,
                                        request_timeout=8.0, capture=result["ls"]["transport"])
        get = get or requests.get
        for venue in ("KRX", "NXT"):
            params = reference_request(market, day, venue)
            url = "https://stock.naver.com/api/domestic/market/trendProgram?" + urlencode(params)
            stamp = time.time()
            response = get(url, timeout=6.0)
            entry = {"request": params, "url": url, "query_started_ts": stamp,
                     "received_ts": time.time(), "http_status": response.status_code,
                     "raw_base64": base64.b64encode(response.content).decode("ascii"),
                     "raw_sha256": _hash(response.content)}
            result["references"][venue] = entry
            response.raise_for_status()
            entry["response"] = response.json()
        result["received_ts"] = time.time()
        _check_captures(result)
        result["derived"] = derive(market, close_ts, result["ls"], result["references"])
        result["status"] = "verified"
    except Exception as exc:
        # Requests errors can contain URLs. These read-only market URLs contain no credentials.
        result["reason"] = f"{type(exc).__name__}: {exc}"
    result["received_ts"] = time.time()
    return result


def render(result: dict | None, market: str, now_ts: float | None = None) -> list[str]:
    lines = ["", "<b>장마감 시점 당일 누적 프로그램 수급</b>"]
    reason = "마감 원표·원화 환산 단위 미확인"
    if isinstance(result, dict):
        reason = str(result.get("reason") or reason)
        try:
            if result.get("status") != "verified" or result.get("market") != market:
                raise ValueError(reason)
            now = time.time() if now_ts is None else now_ts
            received = float(result["received_ts"])
            close_ts = float(result["close_ts"])
            if not close_ts <= received <= now + 5 or now - received > 180:
                raise ValueError("마감 누적액 조회시각 불일치·오래된 조회")
            if dt.datetime.fromtimestamp(now, KST).date() != dt.datetime.fromtimestamp(close_ts, KST).date():
                raise ValueError("마감 누적액 날짜 불일치")
            if result.get("unit_contract") != UNIT_CONTRACT:
                raise ValueError("원화 대조 단위 계약 불일치")
            _check_captures(result)
            derived = derive(market, close_ts, result["ls"], result["references"])
            if result.get("derived") != derived:
                raise ValueError("저장 누적액·환산·원표 대조 불일치")
            close = dt.datetime.fromtimestamp(close_ts, KST)
            lines += [f"• <b>{close:%Y-%m-%d %H:%M:%S} KST</b> 원표 · KRX+NXT 통합 · 당일 매수−매도 누적"]
            for label, value in derived["amounts_won"].items():
                eok = Decimal(value) / Decimal(100_000_000)
                lines.append(f"• {label} <b>{eok:+,.2f}억원</b> ({value:+,}원)")
            lines += ["• 단위: 원·억원 (백만원 단위 원표의 환산액; 환산 단위 검증).",
                      "• KRX 마감 시각 누적이며 NXT 하루 최종값은 아닙니다. 이후 원자료 수정 가능."]
            if not derived["close_amount_independently_checked"]:
                lines.append("• 마감 금액의 독립 대조: 일부 원화 원표 미공표로 미완료.")
            residual = derived["net_component_residual_won"]
            if residual:
                lines.append(f"• 전체 직접값−차익·비차익 합계 차이 {residual:+,}원 (원표 표시 정밀도 내; 직접값 보존)")
            return lines
        except Exception as exc:
            reason = str(exc)
    lines.append("• <b>확인 보류</b>: " + html.escape(reason[:240]))
    return lines

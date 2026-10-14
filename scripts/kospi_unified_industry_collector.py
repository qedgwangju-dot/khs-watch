#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import time
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

import ebest

from kospi_shock_enrichment import _display_name, _is_real_industry
from krx_session_calendar import session_state
from kosdaq_surge_industries import _industry

KST = ZoneInfo("Asia/Seoul")
INVESTORS = {"0008": "개인", "0017": "외국인", "0018": "기관"}


def fnum(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def market_ts(value: str | None, fallback: float) -> float:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 6:
        return fallback
    digits = digits[:6]
    now = dt.datetime.now(KST)
    try:
        point = dt.datetime(
            now.year, now.month, now.day,
            int(digits[:2]), int(digits[2:4]), int(digits[4:6]),
            tzinfo=KST,
        )
        ts = point.timestamp()
        return ts if abs(ts - fallback) < 6 * 60 * 60 else fallback
    except Exception:
        return fallback


def parse_until(value: str) -> dt.time:
    hh, mm = map(int, value.split(":"))
    return dt.time(hh, mm)


async def industry_master(api: ebest.OpenApi) -> list[dict]:
    """기존 코스피 업종을 보존하고 코스닥 3xx 업종을 추가 수집한다."""
    found: dict[str,dict] = {}
    # LS 업종 마스터의 시장구분별 목록은 겹칠 수 있어 코드로 병합한다.
    for index, gubun in enumerate(("1", "2", "0")):
        # LS t8424는 초당 1회 조회 제한. 시장별 마스터 요청은 최소 1.1초 간격으로 수행.
        if index:
            await asyncio.sleep(1.1)
        try:
            rsp = await api.request("t8424", {"t8424InBlock": {"gubun1": gubun}})
        except Exception:
            continue
        rows = (rsp.body.get("t8424OutBlock") or []) if rsp else []
        if isinstance(rows,dict):
            rows=[rows]
        for row in rows if isinstance(rows,list) else []:
            if not isinstance(row,dict):continue
            code=str(row.get("upcode") or "").strip()
            name=_display_name(row.get("hname"))
            if len(code)==3 and _is_real_industry(name,code):
                found[code]={"code":code,"name":name}
    return list(found.values())


async def main(out_path: Path, until: dt.time, test_seconds: int | None = None) -> int:
    appkey = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    appsecret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not appkey or not appsecret:
        raise RuntimeError("LS OpenAPI secrets missing")

    session = session_state(dt.datetime.now(KST))
    if test_seconds is None and not session["is_session"]:
        flag = out_path.parent / "krx_market_closed.flag"
        flag.write_text(session["date"] + "\n", encoding="utf-8")
        print("ubm_collector_market_closed=true reason=XKRX_non_session", flush=True)
        return 0

    api = ebest.OpenApi()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    registrations: list[tuple[str, str]] = []
    history_task: asyncio.Task | None = None
    industry_names: dict[str, str] = {}
    last_signature: dict[tuple[str, str], tuple[str, float, float | None, float]] = {}
    signature_lock = threading.Lock()
    last_payload_ts: float | None = None

    try:
        if not await api.login(appkey, appsecret):
            raise RuntimeError(f"LS login failed: {api.last_message}")

        industries = await industry_master(api)
        if not industries:
            raise RuntimeError("No industry master rows for UBM collector")
        industry_names = {x["code"]: x["name"] for x in industries}

        fp = out_path.open("a", encoding="utf-8", buffering=1)

        def on_realtime(api_obj, trcode, key, data):
            nonlocal written, last_payload_ts
            if str(trcode) != "UBM" or not isinstance(data, dict):
                return
            last_payload_ts = time.time()
            investor_code = str(data.get("tjjcode") or "").strip()
            investor = INVESTORS.get(investor_code)
            if not investor:
                return
            upcode = str(data.get("upcode") or "").strip()
            msval = fnum(data.get("msval"))
            if not upcode or msval is None:
                return
            tjjtime = str(data.get("tjjtime") or "")
            msvol = fnum(data.get("msvol"))
            signature_key = (upcode, investor)
            received_ts = time.time()
            # UBM의 tjjtime은 같은 값이 여러 초~수십 초 유지될 수 있다.
            # 사건구간 정렬은 실제 payload 수신시각을 사용하고, LS 원시시각은 별도 보존한다.
            with signature_lock:
                prev = last_signature.get(signature_key)
                if prev is not None:
                    prev_time, prev_val, prev_vol, prev_received = prev
                    same_payload = (
                        prev_time == tjjtime and prev_val == msval and prev_vol == msvol
                    )
                    # 같은 payload가 짧은 간격으로 중복 전송되면 억제하되,
                    # 값이 그대로여도 5초마다 기준점용 heartbeat는 남긴다.
                    if same_payload and received_ts - prev_received < 5.0:
                        return
                last_signature[signature_key] = (tjjtime, msval, msvol, received_ts)
            source_ts = market_ts(tjjtime, received_ts)
            row = {
                "ts": received_ts,
                "received_ts": received_ts,
                "source_ts": source_ts,
                "source_time": tjjtime,
                "source_lag_sec": (received_ts - source_ts) if source_ts is not None else None,
                "time": tjjtime,
                "upcode": upcode,
                "industry": industry_names.get(upcode) or upcode,
                "investor_code": investor_code,
                "investor": investor,
                "msval": msval,
                "msvol": msvol,
                "ex_upcode": str(data.get("ex_upcode") or ""),
                "source_tr": "UBM",
                "subscription_key": str(key),
                "source_unit": "UNVERIFIED",
            }
            with signature_lock:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

        api.on_realtime.connect(on_realtime)

        failed = []
        kosdaq_failed = []
        for item in industries:
            key = "U" + item["code"]
            ok = await api.add_realtime("UBM", key)
            if ok:
                registrations.append(("UBM", key))
            elif str(item["code"]).startswith("3"):
                # 코스닥 업종 구독이 거절돼도 기존 코스피 감시를 중단하지 않는다.
                kosdaq_failed.append({"key": key, "message": str(api.last_message)})
            else:
                failed.append({"key": key, "message": str(api.last_message)})
            await asyncio.sleep(0.03)

        if kosdaq_failed:
            print(f"kosdaq_ubm_degraded=true failed={kosdaq_failed}", flush=True)
        if failed:
            raise RuntimeError(f"UBM registration failures: {failed}")
        # A separate metadata record makes missing/unregistered KOSDAQ sectors
        # visible to the buy-alert reader. Existing crash parsers ignore it.
        fp.write(json.dumps({
            "record_type": "subscription_coverage", "ts": time.time(),
            "market": "KOSDAQ", "source_tr": "UBM",
            "expected": [x for x in industries if str(x["code"]).startswith("3")],
            "registered": [key[1:] for _, key in registrations if key[1:].startswith("3")],
            "failed": kosdaq_failed,
        }, ensure_ascii=False) + "\n")

        async def collect_kosdaq_history():
            # t1621 is limited to 1 request/second. Spread one pass across the
            # industries, repeat no sooner than 60s, and leave UBM/KOSPI intact.
            sectors = [x for x in industries if _industry(x["code"], x["name"])]
            while True:
                cycle_started = time.monotonic()
                for item in sectors:
                    call_started = time.monotonic()
                    request = {"t1621InBlock": {"upcode": item["code"], "nmin": 1,
                                               "cnt": 10, "bgubun": "0", "exchgubun": "U"}}
                    record = {"record_type": "industry_history_snapshot", "source_tr": "t1621",
                              "market": "KOSDAQ", "upcode": item["code"], "industry": item["name"],
                              "request": request, "source_unit": "UNVERIFIED"}
                    try:
                        response = await asyncio.wait_for(api.request("t1621", request), timeout=8)
                        record["response"] = getattr(response, "body", {})
                        record["status"] = "success" if response else "request_failed"
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        record.update(status="request_failed", error_type=type(exc).__name__)
                    record["received_ts"] = time.time()
                    with signature_lock:
                        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
                    await asyncio.sleep(max(0, 1.1 - (time.monotonic() - call_started)))
                await asyncio.sleep(max(0, 60 - (time.monotonic() - cycle_started)))

        history_task = asyncio.create_task(collect_kosdaq_history())
        print(
            f"ubm_market_coverage kospi={sum(not x[1][1:].startswith('3') for x in registrations)} "
            f"kosdaq={sum(x[1][1:].startswith('3') for x in registrations)}",
            flush=True,
        )

        print(
            f"ubm_collector_started=true industries={len(industries)} "
            f"keys={[x[1] for x in registrations[:5]]}...",
            flush=True,
        )

        started = time.time()
        while True:
            now = dt.datetime.now(KST)
            elapsed = time.time() - started
            if test_seconds is not None and elapsed >= test_seconds:
                break
            if test_seconds is None and now.time() >= until:
                break
            # XKRX 실제 연속매매 구간에서만 stale 재접속을 적용한다.
            live_window = bool(
                session["is_session"]
                and session["open"] is not None
                and session["continuous_end"] is not None
                and session["open"] <= now < session["continuous_end"]
            )
            if live_window and elapsed >= 90:
                stale_for = None if last_payload_ts is None else time.time() - last_payload_ts
                if last_payload_ts is None or (stale_for is not None and stale_for > 120):
                    raise RuntimeError(
                        "UBM feed stale >120s during market hours; "
                        f"last_payload_age={stale_for}"
                    )
            await asyncio.sleep(1)

        history_task.cancel()
        await asyncio.gather(history_task, return_exceptions=True)
        fp.flush()
        fp.close()
        now_done = dt.datetime.now(KST)
        continuous_market_hours = bool(
            session["is_session"]
            and session["open"] is not None
            and session["continuous_end"] is not None
            and session["open"] <= now_done < session["continuous_end"]
        )
        print(
            f"ubm_collector_finished=true records={written} "
            f"continuous_market_hours={str(continuous_market_hours).lower()}",
            flush=True,
        )
        if test_seconds is not None and continuous_market_hours and written <= 0:
            raise RuntimeError("UBM collector received no investor-industry payload during continuous market hours")
        return 0
    finally:
        if history_task is not None:
            history_task.cancel()
            await asyncio.gather(history_task, return_exceptions=True)
        for tr, key in registrations:
            try:
                await api.remove_realtime(tr, key)
            except Exception:
                pass
        try:
            await api.close()
        except Exception:
            pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/kospi_industry_flow.jsonl")
    ap.add_argument("--until", default="15:32")
    ap.add_argument("--test-seconds", type=int)
    args = ap.parse_args()
    raise SystemExit(
        asyncio.run(main(Path(args.out), parse_until(args.until), args.test_seconds))
    )

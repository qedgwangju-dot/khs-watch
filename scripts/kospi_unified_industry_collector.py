#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import ebest

from kospi_shock_enrichment import _display_name, _is_real_industry

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
    best: list[dict] = []
    for gubun in ("1", "0"):
        try:
            rsp = await api.request("t8424", {"t8424InBlock": {"gubun1": gubun}})
        except Exception:
            continue
        rows = (rsp.body.get("t8424OutBlock") or []) if rsp else []
        if isinstance(rows, dict):
            rows = [rows]
        clean = [x for x in rows if isinstance(x, dict)]
        if len(clean) > len(best):
            best = clean
        if clean:
            break
    out = []
    for row in best:
        code = str(row.get("upcode") or "").strip()
        name = _display_name(row.get("hname"))
        if len(code) == 3 and _is_real_industry(name, code):
            out.append({"code": code, "name": name})
    return out


async def main(out_path: Path, until: dt.time, test_seconds: int | None = None) -> int:
    appkey = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    appsecret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not appkey or not appsecret:
        raise RuntimeError("LS OpenAPI secrets missing")

    api = ebest.OpenApi()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    registrations: list[tuple[str, str]] = []
    industry_names: dict[str, str] = {}
    last_signature: dict[tuple[str, str], tuple[str, float]] = {}
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
            signature_key = (upcode, investor)
            signature = (tjjtime, msval)
            if last_signature.get(signature_key) == signature:
                return
            last_signature[signature_key] = signature
            received_ts = time.time()
            row = {
                "ts": market_ts(str(data.get("tjjtime") or ""), received_ts),
                "received_ts": received_ts,
                "time": tjjtime,
                "upcode": upcode,
                "industry": industry_names.get(upcode) or upcode,
                "investor_code": investor_code,
                "investor": investor,
                "msval": msval,
                "msvol": fnum(data.get("msvol")),
                "ex_upcode": str(data.get("ex_upcode") or ""),
            }
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

        api.on_realtime.connect(on_realtime)

        failed = []
        for item in industries:
            key = "U" + item["code"]
            ok = await api.add_realtime("UBM", key)
            if ok:
                registrations.append(("UBM", key))
            else:
                failed.append({"key": key, "message": str(api.last_message)})
            await asyncio.sleep(0.03)

        if failed:
            raise RuntimeError(f"UBM registration failures: {failed}")

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
            live_window = now.weekday() < 5 and dt.time(9, 0) <= now.time() < until
            if live_window and elapsed >= 90:
                stale_for = None if last_payload_ts is None else time.time() - last_payload_ts
                if last_payload_ts is None or (stale_for is not None and stale_for > 120):
                    raise RuntimeError(
                        "UBM feed stale >120s during market hours; "
                        f"last_payload_age={stale_for}"
                    )
            await asyncio.sleep(1)

        fp.flush()
        fp.close()
        market_hours = dt.datetime.now(KST).weekday() < 5 and dt.time(9, 0) <= dt.datetime.now(KST).time() <= dt.time(15, 20)
        print(f"ubm_collector_finished=true records={written} market_hours={str(market_hours).lower()}", flush=True)
        if test_seconds is not None and market_hours and written <= 0:
            raise RuntimeError("UBM collector received no investor-industry payload during market hours")
        return 0
    finally:
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
    ap.add_argument("--until", default="15:20")
    ap.add_argument("--test-seconds", type=int)
    args = ap.parse_args()
    raise SystemExit(
        asyncio.run(main(Path(args.out), parse_until(args.until), args.test_seconds))
    )

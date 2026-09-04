#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import io
import json

from zoneinfo import ZoneInfo

import war_peace_reconstruction_watch_live as live

watch = live.watch
runner = live.runner
clean = live.clean

KST = ZoneInfo("Asia/Seoul")
WARSAW = ZoneInfo("Europe/Warsaw")

YAHOO_SYMBOLS = {
    "NQ=F": "나스닥100 선물",
    "CL=F": "WTI",
    "BZ=F": "Brent",
    "DX-Y.NYB": "달러지수",
}

STOOQ_SYMBOLS = {
    "NQ=F": "nq.f",
    "CL=F": "cl.f",
    "BZ=F": "cb.f",
    "DX-Y.NYB": "dx.f",
}


def _yahoo_quote(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{watch.urllib.parse.quote(sym)}?range=1d&interval=1m"
    data = json.loads(watch.req(url, 15).decode())
    result = data["chart"]["result"][0]
    meta = result["meta"]
    timestamps = result.get("timestamp", [])
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    valid = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
    if not valid:
        return None
    ts, px = valid[-1]
    prev = float(meta.get("previousClose") or 0)
    if not prev:
        return None
    asof = dt.datetime.fromtimestamp(ts, KST)
    pct = (float(px) / prev - 1.0) * 100.0
    return {
        "price": float(px),
        "prev": prev,
        "pct": pct,
        "asof": asof,
        "source": "Yahoo Finance 1분봉",
    }


def _stooq_quote(sym):
    url = f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"
    raw = watch.req(url, 15).decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        return None
    row = rows[0]
    close = row.get("Close") or row.get("close")
    date_s = row.get("Date") or row.get("date")
    time_s = row.get("Time") or row.get("time")
    if not close or close in ("N/D", "-") or not date_s or not time_s:
        return None
    px = float(close)
    local = dt.datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=WARSAW)
    return {
        "price": px,
        "asof": local.astimezone(KST),
        "source": "Stooq",
    }


def _fresh_minutes(asof, now):
    return max(0.0, (now - asof).total_seconds() / 60.0)


def precise_market_snapshot():
    now = dt.datetime.now(KST)
    rows = []
    for sym, name in YAHOO_SYMBOLS.items():
        try:
            y = _yahoo_quote(sym)
        except Exception:
            y = None
        if not y:
            continue

        try:
            s = _stooq_quote(STOOQ_SYMBOLS[sym])
        except Exception:
            s = None

        # Yahoo 최신 1분봉이 20분보다 오래됐으면 값 자체를 발송하지 않는다.
        if _fresh_minutes(y["asof"], now) > 20:
            continue

        selected = y
        verified = False
        verify_note = ""
        if s and _fresh_minutes(s["asof"], now) <= 20:
            gap_pct = abs(s["price"] / y["price"] - 1.0) * 100.0
            if gap_pct <= 0.20:
                verified = True
                # 더 최신 시각의 가격을 사용하되 일간 등락률은 동일 계약의 전일 종가 기준으로 재계산한다.
                if s["asof"] > y["asof"]:
                    selected = dict(y)
                    selected["price"] = s["price"]
                    selected["asof"] = s["asof"]
                    selected["source"] = "Stooq + Yahoo Finance 교차검증"
                    selected["pct"] = (selected["price"] / y["prev"] - 1.0) * 100.0
                verify_note = f"교차검증 일치(차이 {gap_pct:.2f}%)"
            else:
                # 두 실시간 원천이 0.20% 넘게 어긋나면 잘못된 값을 보내느니 해당 항목을 생략한다.
                continue

        rows.append({
            "name": name,
            "price": selected["price"],
            "pct": selected["pct"],
            "arrow": "▲" if selected["pct"] > 0 else "▼" if selected["pct"] < 0 else "－",
            "basis": "전일 종가 대비",
            "source": selected["source"],
            "asof": selected["asof"].strftime("%H:%M KST"),
            "verified": verified,
            "verify_note": verify_note,
        })
    return rows


watch.market_snapshot = precise_market_snapshot

_old_build_alert = watch.build_alert


def precise_build_alert(items, markets, now):
    text = _old_build_alert(items, markets, now)
    for m in markets:
        old = f"{m['name']}  <b>{m['price']:,.2f}</b>  {m['pct']:+.2f}%"
        note = f"{m['name']}  <b>{m['price']:,.2f}</b>  {m['pct']:+.2f}% · 전일 종가 대비 · 기준 {m['asof']}"
        if m.get("verified"):
            note += " · 교차검증"
        text = text.replace(old, note)
    return text


watch.build_alert = precise_build_alert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        clean.write_clean_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()

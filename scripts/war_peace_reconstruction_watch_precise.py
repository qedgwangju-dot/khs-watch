#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import io
import json
import math

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
QUOTE_DIAGNOSTICS = {}


def _yahoo_quote(sym):
    diagnostic = QUOTE_DIAGNOSTICS[sym] = {'status': 'unavailable', 'reason': '제공처 조회 실패'}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{watch.urllib.parse.quote(sym)}?range=1d&interval=1m"
    data = json.loads(watch.req(url, 15).decode())
    result = data["chart"]["result"][0]
    meta = result["meta"]
    baseline_metadata = {key: meta[key] for key in (
        'symbol', 'instrumentType', 'previousClose', 'chartPreviousClose', 'exchangeTimezoneName',
        'regularMarketTime', 'currentTradingPeriod') if key in meta}
    diagnostic['quote_metadata'] = baseline_metadata
    if meta.get('symbol') != sym:
        diagnostic.update(status='withheld', reason='제공처 종목 코드 불일치')
        return None
    timestamps = result.get("timestamp", [])
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    valid = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
    if not valid:
        diagnostic.update(status='withheld', reason='유효 가격 표본 없음')
        return None
    ts, px = valid[-1]
    closes = {key: float(meta[key]) for key in ('previousClose', 'chartPreviousClose')
              if meta.get(key) is not None}
    if len(closes) == 2 and not math.isclose(closes['previousClose'], closes['chartPreviousClose'], rel_tol=1e-6, abs_tol=1e-6):
        diagnostic.update(status='withheld', reason='제공처 비교종가 필드 불일치')
        return None
    close_field = 'chartPreviousClose' if 'chartPreviousClose' in closes else 'previousClose'
    prev = closes.get(close_field, 0)
    px = float(px)
    if not all(math.isfinite(value) and value > 0 for value in (px, prev)):
        diagnostic.update(status='withheld', reason='가격·비교종가 비정상')
        return None
    asof = dt.datetime.fromtimestamp(ts, KST)
    pct = (float(px) / prev - 1.0) * 100.0
    diagnostic.update(status='available', reason=None)
    return {
        "price": float(px),
        "prev": prev,
        "pct": pct,
        "asof": asof,
        "source": "Yahoo Finance 1분봉",
        "previous_close_field": close_field,
        "previous_close_date_verified": False,
        "quote_metadata": baseline_metadata,
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
    if not math.isfinite(px) or px <= 0:
        return None
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
    QUOTE_DIAGNOSTICS.clear()
    statuses = watch.market_source_status = {}
    for sym, name in YAHOO_SYMBOLS.items():
        try:
            y = _yahoo_quote(sym)
        except Exception as exc:
            QUOTE_DIAGNOSTICS.setdefault(sym, {}).update(status='unavailable', reason='제공처 조회 실패', error_kind=type(exc).__name__)
            y = None
        if not y:
            statuses[sym] = {'name': name, **QUOTE_DIAGNOSTICS.get(sym, {'status': 'unavailable', 'reason': '제공처 조회 실패'})}
            continue

        try:
            s = _stooq_quote(STOOQ_SYMBOLS[sym])
        except Exception:
            s = None

        # Yahoo 최신 1분봉이 20분보다 오래됐으면 값 자체를 발송하지 않는다.
        if _fresh_minutes(y["asof"], now) > 20 or y["asof"] > now + dt.timedelta(minutes=5):
            statuses[sym] = {'name': name, 'status': 'withheld', 'reason': '가격 시각 오래됨·미래 시각',
                             'observed_at_kst': y['asof'].isoformat()}
            continue

        selected = y
        verified = False
        verify_note = ""
        comparison = None
        if s and _fresh_minutes(s["asof"], now) <= 20 and s["asof"] <= now + dt.timedelta(minutes=5):
            gap_pct = abs(s["price"] / y["price"] - 1.0) * 100.0
            comparison = {'source': s['source'], 'symbol': STOOQ_SYMBOLS[sym],
                          'price': s['price'], 'asof': s['asof'].isoformat(), 'gap_pct': gap_pct,
                          'contract_identity_verified': False}
            if gap_pct <= 0.20:
                # Both generic futures symbols may roll differently. A nearby
                # price is auxiliary evidence, not proof of the same contract.
                verify_note = f"보조가격 차이 {gap_pct:.2f}% · 계약 동일성 미확인"
            else:
                # 두 실시간 원천이 0.20% 넘게 어긋나면 잘못된 값을 보내느니 해당 항목을 생략한다.
                statuses[sym] = {'name': name, 'status': 'withheld', 'reason': '보조 가격 차이 한도 초과', 'comparison': comparison}
                continue

        rows.append({
            "name": name,
            "price": selected["price"],
            "pct": selected["pct"],
            "arrow": "▲" if selected["pct"] > 0 else "▼" if selected["pct"] < 0 else "－",
            "basis": "제공처 비교종가 대비",
            "source": selected["source"],
            "asof": selected["asof"].strftime("%H:%M KST"),
            "observed_at_kst": selected["asof"].isoformat(),
            "symbol": sym,
            "previous_close": y['prev'],
            "previous_close_field": y.get('previous_close_field'),
            "previous_close_date_verified": y.get('previous_close_date_verified', False),
            "quote_metadata": y.get('quote_metadata', {}),
            "source_url": f"https://query1.finance.yahoo.com/v8/finance/chart/{watch.urllib.parse.quote(sym)}?range=1d&interval=1m",
            "comparison": comparison,
            "verified": verified,
            "verify_note": verify_note,
        })
        statuses[sym] = {'name': name, 'status': 'available', 'reason': None}
    return rows


watch.market_snapshot = precise_market_snapshot

_old_build_alert = watch.build_alert


def precise_build_alert(items, markets, now):
    text = _old_build_alert(items, markets, now)
    for m in markets:
        old = f"{m['name']}  <b>{m['price']:,.2f}</b>  {m['pct']:+.2f}%"
        note = f"{m['name']}  <b>{m['price']:,.2f}</b>  {m['pct']:+.2f}% · {m.get('basis', '제공처 비교종가 대비')} · 기준 {m['asof']}"
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

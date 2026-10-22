#!/usr/bin/env python3
"""Trade-date closing-price notional estimates for ARK ETF trades.

ARK's trade notification has exact shares but not execution prices. Never
call this the actual buy cost. Suppress any estimate if its date is wrong.
"""
import csv
import datetime as dt
import io
import json
import math
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ET=ZoneInfo("America/New_York")


def _request(url, timeout=8):
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0 (KHS ARK Daily Trade Notional Check)",
        "Accept":"text/csv,application/json,*/*",
    })
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return response.read(150_000)


def stooq_close(ticker, day):
    if ticker=="HO":
        return None  # Thales HO is Paris-traded EUR, not a U.S. USD security.
    yyyymmdd=day.replace("-","")
    params=urllib.parse.urlencode({"s":ticker.lower().replace(".","-")+".us",
        "i":"d","d1":yyyymmdd,"d2":yyyymmdd})
    body=_request("https://stooq.com/q/d/l/?"+params).decode("utf-8-sig","replace")
    for record in csv.DictReader(io.StringIO(body)):
        if (record.get("Date") or "").strip()!=day:
            continue
        try: close=float(record["Close"])
        except (ValueError,TypeError,KeyError): continue
        if math.isfinite(close) and 0.01<close<100_000:
            return close
    return None


def yahoo_close(ticker,day):
    if ticker=="HO": return None
    d=dt.date.fromisoformat(day)
    start=int(dt.datetime.combine(d-dt.timedelta(days=2),dt.time(),tzinfo=dt.timezone.utc).timestamp())
    end=int(dt.datetime.combine(d+dt.timedelta(days=3),dt.time(),tzinfo=dt.timezone.utc).timestamp())
    params=urllib.parse.urlencode({"period1":start,"period2":end,
        "interval":"1d","events":"history"})
    url="https://query1.finance.yahoo.com/v8/finance/chart/"+urllib.parse.quote(ticker,safe="")+"?"+params
    payload=json.loads(_request(url))
    result=(payload.get("chart",{}).get("result") or [None])[0]
    if not result: return None
    times=result.get("timestamp") or []
    quotes=(result.get("indicators",{}).get("quote") or [{}])[0]
    for timestamp,close in zip(times,quotes.get("close") or []):
        if dt.datetime.fromtimestamp(timestamp,ET).date().isoformat()!=day: continue
        if close is None: continue
        try: value=float(close)
        except (TypeError,ValueError): continue
        if math.isfinite(value) and 0.01<value<100_000:
            return value
    return None


def close_prices(rows,day):
    """Best effort with independent provider comparison and strict date validation."""
    result={}
    for ticker in sorted({r["ticker"] for r in rows}):
        quotes={}
        for provider,fn in [("Stooq",stooq_close),("Yahoo Finance",yahoo_close)]:
            try:
                value=fn(ticker,day)
                if value is not None: quotes[provider]=float(value)
            except Exception as error:
                print("ARK_PRICE_PROVIDER_UNAVAILABLE",ticker,provider,repr(error)[:160])
        if len(quotes)==2:
            values=list(quotes.values())
            delta=abs(values[0]-values[1])/max(values)
            if delta>0.04:
                print("ARK_PRICE_MISMATCH_SUPPRESSED",ticker,day,quotes)
                continue
            result[ticker]={"close":quotes["Yahoo Finance"],"source":"2곳 교차확인"}
        elif len(quotes)==1:
            provider,price=next(iter(quotes.items()))
            result[ticker]={"close":price,"source":provider+" 1곳"}
        else:
            print("ARK_PRICE_UNAVAILABLE",ticker,day)
    return result


def usd_krw(usd,rate):
    if usd>=100_000_000: usd_text=f"{usd/100_000_000:,.2f}억달러"
    elif usd>=10_000: usd_text=f"{usd/10_000:,.1f}만달러"
    else: usd_text=f"{usd:,.0f}달러"
    krw=usd*rate
    if krw>=1_000_000_000_000: krw_text=f"{krw/1_000_000_000_000:,.2f}조원"
    elif krw>=100_000_000: krw_text=f"{krw/100_000_000:,.1f}억원"
    else: krw_text=f"{krw/10_000:,.0f}만원"
    return f"{usd_text}(약 {krw_text})"


def estimated_amount(ticker,shares,prices,rate):
    quote=(prices or {}).get(ticker)
    if not quote or rate is None or not math.isfinite(rate) or rate<=0:
        return "거래대금: 체결단가 미공개·종가 추정 불가"
    amount=shares*quote["close"]
    return f"당일 종가 기준 추정 {usd_krw(amount,rate)}"


if __name__=="__main__":
    # No live requests occur when imported or in synthetic tests.
    print(usd_krw(10_000_000,1350))

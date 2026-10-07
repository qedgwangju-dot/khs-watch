#!/usr/bin/env python3
"""Warsh 금리경로 v4: CME 공식 결제값 + 뉴욕연은 EFFR 우선.

공식 시장원천이 실패하면 직전 정상 상태를 보존하고 신규 금리경로 판정을
중지한다. 보조 웹 화면의 오래된 확률을 자동 알림에 사용하지 않는다.
"""
import calendar
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import warsh_policy_path_watch_v3 as v3

CME_PRODUCT_ID = 305
CME_SETTLEMENTS_PAGE = (
    "https://www.cmegroup.com/markets/interest-rates/stirs/"
    "30-day-federal-fund.settlements.html"
)
CME_API = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/"
    + str(CME_PRODUCT_ID) + "/FUT?tradeDate={trade_date}"
)
NYFED_EFFR = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json"
UA = "Mozilla/5.0 (compatible; khs-watch/4.1; +https://github.com/qedgwangju-dot/khs-watch)"
MONTHS = {
    "JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
    "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12,
}


def ny_today():
    return datetime.now(ZoneInfo("America/New_York")).date()


def get_json(url, referer=None, retries=3):
    last = None
    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    for n in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            last = exc
            if n + 1 < retries:
                time.sleep(2 * (n + 1))
    raise last


def parse_price(value):
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(value or "").replace(",", ""))
    return float(m.group(1)) if m else None


def parse_month(value):
    s = re.sub(r"\s+", " ", str(value or "").upper()).strip()
    m = re.search(r"\b([A-Z]{3})\s*(\d{2}|20\d{2})\b", s)
    if not m or m.group(1) not in MONTHS:
        return None
    y = int(m.group(2))
    if y < 100:
        y += 2000
    return y, MONTHS[m.group(1)]


def cme_monthly_rates():
    errors = []
    today = ny_today()
    for offset in range(10):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        td = urllib.parse.quote(d.strftime("%m/%d/%Y"), safe="")
        url = CME_API.format(trade_date=td)
        try:
            data = get_json(url, CME_SETTLEMENTS_PAGE, retries=2)
        except Exception as exc:
            errors.append(f"{d}: {exc}")
            continue

        rows = data.get("settlements") or data.get("payload") or []
        months = {}
        for row in rows:
            ym = parse_month(
                row.get("month") or row.get("contractMonth") or row.get("symbol")
            )
            px = parse_price(
                row.get("settle") or row.get("settlement")
                or row.get("decimalSettlePx") or row.get("formatSettlePx")
            )
            if ym and px is not None and 90.0 <= px <= 100.5:
                months[ym] = 100.0 - px
        if len(months) >= 3:
            return d.isoformat(), months
        errors.append(f"{d}: 유효 ZQ 결제행 부족")
    raise RuntimeError("CME 공식 결제값 실패: " + " | ".join(errors[-4:]))


def official_effr():
    data = get_json(
        NYFED_EFFR,
        "https://www.newyorkfed.org/markets/reference-rates/effr",
    )
    rows = data.get("refRates") or data.get("ref_rates") or []
    rows = [r for r in rows if str(r.get("type") or "").upper() == "EFFR"] or rows
    if not rows:
        raise RuntimeError("뉴욕연은 EFFR 행 없음")
    rows.sort(key=lambda r: str(r.get("effectiveDate") or r.get("effective_date") or ""))
    row = rows[-1]
    rate = row.get("percentRate")
    if rate is None:
        rate = row.get("rate")
    if rate is None:
        raise RuntimeError("뉴욕연은 EFFR 값 없음")
    return float(rate), str(row.get("effectiveDate") or row.get("effective_date") or "")


def adjacent_distribution(change_bp):
    """확률가중 기대변화를 인접한 25bp 결과 두 개로 분해."""
    u = float(change_bp) / 25.0
    if u >= 0:
        lo = math.floor(u); frac = u - lo
        dist = {int(lo*25):(1-frac)*100, int((lo+1)*25):frac*100}
    else:
        hi = math.ceil(u); frac = hi - u
        dist = {int(hi*25):(1-frac)*100, int((hi-1)*25):frac*100}
    return {k:max(0.0,min(100.0,v)) for k,v in dist.items() if v > 0.0001}


def official_snapshot():
    trade_date, monthly = cme_monthly_rates()
    effr, effr_date = official_effr()
    meetings = v3.base.parse_snapshot().get("meetings") or []
    # 회의 날짜 자체는 공개 FOMC 일정과 기존 파서가 이미 검증한 미래 회의만 사용.
    today = ny_today()
    future = []
    for m in meetings:
        try:
            d = datetime.strptime(str(m.get("date")), "%Y-%m-%d").date()
        except Exception:
            continue
        if d >= today:
            future.append(d)
    if not future:
        raise RuntimeError("향후 FOMC 회의 날짜 없음")

    meet_months = {(d.year,d.month) for d in future}
    result = []
    prev_post = None
    for d in future:
        ym = (d.year,d.month)
        if ym not in monthly:
            continue
        pym = (d.year-1,12) if d.month == 1 else (d.year,d.month-1)
        if ym == (today.year,today.month):
            pre = effr
        elif pym in monthly and pym not in meet_months:
            pre = monthly[pym]
        elif prev_post is not None:
            pre = prev_post
        else:
            pre = effr

        days = calendar.monthrange(d.year,d.month)[1]
        post_days = days - d.day
        if post_days <= 0:
            continue
        avg = monthly[ym]
        post = (avg*days - pre*d.day) / post_days
        change = (post-pre)*100.0
        dist = adjacent_distribution(change)
        result.append({
            "date":d.isoformat(),
            "label":f"{calendar.month_abbr[d.month]} {d.day}, {d.year}",
            "prob_cell":" / ".join(f"{k:+d}bp {p:.0f}%" for k,p in sorted(dist.items())),
            "implied_avg":avg,
            "pre_rate":pre,
            "post_rate":post,
            "change_bp":change,
            "hike25_prob":dist.get(25,0.0),
            "hike25_or_more_prob":sum(p for k,p in dist.items() if k >= 25),
            "hold_prob":dist.get(0,0.0),
            "cut_prob":sum(p for k,p in dist.items() if k < 0),
            "outcomes":{str(k):p for k,p in dist.items()},
            "contract":f"ZQ-{d.year:04d}-{d.month:02d}",
        })
        prev_post = post

    if not result:
        raise RuntimeError("CME 월물과 향후 FOMC 회의 연결 실패")
    lag = (today - datetime.strptime(trade_date,"%Y-%m-%d").date()).days
    if lag > 4:
        raise RuntimeError(f"CME 결제값 오래됨: {trade_date}, {lag}일 전")

    snap = {
        "effr":effr,
        "effr_date":effr_date,
        "meetings":result[:6],
        "url":CME_SETTLEMENTS_PAGE,
        "market_data_basis":"CME 공식 지연 결제값",
        "official_settlement_date":trade_date,
    }
    # v3 메시지/분류가 요구하는 필드와 정확도 라벨.
    snap["source_kind"] = snap["market_data_basis"]
    return snap


# 공식 CME를 못 읽으면 v3의 오류보존 로직으로 들어가며,
# 오래된 보조확률을 새로운 시장판정으로 발송하지 않는다.
v3.validated_snapshot = official_snapshot

if __name__ == "__main__":
    v3.main()

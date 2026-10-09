#!/usr/bin/env python3
"""Warsh 금리경로 v4: CME 공식 결제값 + 뉴욕연은 EFFR 우선.

공식 시장원천이 실패하면 직전 정상 상태를 보존하고 신규 금리경로 판정을
중지한다. 보조 웹 화면의 오래된 확률을 자동 알림에 사용하지 않는다.
"""
import calendar
import csv
import io
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
CME_FTP_ROOT = "https://www.cmegroup.com/ftp/pub/pub/grs/ctr/rt/rates"
ZQ_MONTH_CODES = {"F":1,"G":2,"H":3,"J":4,"K":5,"M":6,"N":7,"Q":8,"U":9,"V":10,"X":11,"Z":12}
NYFED_EFFR = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json"
UA = "Mozilla/5.0 (compatible; khs-watch/4.1; +https://github.com/qedgwangju-dot/khs-watch)"
MONTHS = {
    "JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
    "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12,
}


def ny_today():
    return datetime.now(ZoneInfo("America/New_York")).date()


def get_json(url, referer=None, retries=1, timeout=8):
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
            with urllib.request.urlopen(req, timeout=timeout) as r:
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


def _zq_symbol_month(symbol, ref_year):
    s = str(symbol or "").upper().strip()
    m = re.search(r"\bZQ([FGHJKMNQUVXZ])(\d{1,2})\b", s)
    if not m:
        return None
    month = ZQ_MONTH_CODES[m.group(1)]
    ytxt = m.group(2)
    if len(ytxt) == 2:
        year = 2000 + int(ytxt)
    else:
        digit = int(ytxt)
        candidates = [y for y in range(ref_year - 5, ref_year + 6) if y % 10 == digit]
        if not candidates:
            return None
        year = min(candidates, key=lambda y: abs(y - ref_year))
    return year, month


def parse_cme_ftp_csv(raw_text, ref_date):
    """Parse CME's official daily interest-rate CSV without guessing a price column.

    The fallback is accepted only when a ZQ contract symbol and an explicitly
    labelled settlement column are both present.  If CME changes the schema we
    fail closed instead of picking an OHLC value that merely looks like 95.xx.
    """
    rows = list(csv.reader(io.StringIO(raw_text)))
    header_i = None
    symbol_i = None
    settle_i = None
    for i, row in enumerate(rows[:12]):
        normalized = [re.sub(r"[^a-z0-9]+", "", str(x).lower()) for x in row]
        sidx = next((j for j,x in enumerate(normalized) if x in {"symbol","globexsymbol","contract","contractsymbol","instrument"}), None)
        pidx = next((j for j,x in enumerate(normalized) if "settle" in x), None)
        if sidx is not None and pidx is not None:
            header_i, symbol_i, settle_i = i, sidx, pidx
            break
    if header_i is None:
        raise RuntimeError("CME FTP CSV에 symbol/settlement 헤더 없음")

    months = {}
    for row in rows[header_i + 1:]:
        if max(symbol_i, settle_i) >= len(row):
            continue
        ym = _zq_symbol_month(row[symbol_i], ref_date.year)
        px = parse_price(row[settle_i])
        if ym and px is not None and 90.0 <= px <= 100.5:
            months[ym] = 100.0 - px
    if len(months) < 3:
        raise RuntimeError(f"CME FTP CSV 유효 ZQ 결제행 부족: {len(months)}")
    return months


def cme_monthly_rates_ftp():
    errors = []
    today = ny_today()
    tried = 0
    # CME's current-day archive can appear later than the daily settlement.
    # Try at most the latest three business dates with short timeouts so an
    # unpublished/temporarily slow file does not hide a still-fresh prior
    # official settlement or stall the whole hourly workflow.
    for offset in range(8):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        tried += 1
        if tried > 3:
            break
        folder = f"{d.month:02d}-{calendar.month_abbr[d.month]}"
        url = f"{CME_FTP_ROOT}/{d.year}/{folder}/IR.{d.strftime('%Y%m%d')}.csv"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/csv,text/plain,*/*",
                "Referer": CME_SETTLEMENTS_PAGE,
            })
            with urllib.request.urlopen(req, timeout=6) as r:
                raw = r.read().decode("utf-8", "replace")
            months = parse_cme_ftp_csv(raw, d)
            return d.isoformat(), months
        except Exception as exc:
            errors.append(f"{d}: {type(exc).__name__}: {exc}")
            from urllib.error import HTTPError, URLError
            # A missing or temporarily unreachable newest file may coexist with
            # a valid prior official settlement.  Continue, but only within the
            # bounded three-business-day window above.
            if isinstance(exc, RuntimeError) and ('헤더' in str(exc) or '유효 ZQ' in str(exc)):
                # A file was returned but its schema/product is not the expected
                # ZQ settlement dataset.  Fail closed rather than silently use
                # an older schema that may no longer represent the same data.
                break
            if isinstance(exc, HTTPError) and exc.code not in (404, 408, 429, 500, 502, 503, 504):
                break
            if not isinstance(exc, (HTTPError, URLError, TimeoutError, ConnectionError)):
                break
            continue
    raise RuntimeError("CME 공식 공개 CSV 조회/검증 실패: " + " | ".join(errors[-6:]))


def cme_monthly_rates():
    api_errors = []
    today = ny_today()
    transport_failure = False
    for offset in range(6):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        td = urllib.parse.quote(d.strftime("%m/%d/%Y"), safe="")
        url = CME_API.format(trade_date=td)
        try:
            data = get_json(url, CME_SETTLEMENTS_PAGE, retries=1, timeout=8)
        except Exception as exc:
            api_errors.append(f"{d}: {type(exc).__name__}: {exc}")
            from urllib.error import HTTPError, URLError
            gated = isinstance(exc, HTTPError) and exc.code in (401, 403, 429, 500, 502, 503, 504)
            transport = isinstance(exc, (TimeoutError, ConnectionError)) or (isinstance(exc, URLError) and not isinstance(exc, HTTPError))
            if gated or transport:
                transport_failure = True
                break
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
        api_errors.append(f"{d}: 유효 ZQ 결제행 부족")

    # Root-cause resilience: CME's JSON endpoint can be intermittently blocked
    # or time out on GitHub runners.  Use CME's own daily CSV archive as a
    # second official source before declaring the market path unavailable.
    try:
        return cme_monthly_rates_ftp()
    except Exception as ftp_exc:
        prefix = "CME 공식 JSON 접속 장애" if transport_failure else "CME 공식 JSON 결제값 실패"
        raise RuntimeError(
            prefix + ": " + " | ".join(api_errors[-3:])
            + " ; " + str(ftp_exc)
            + " — 최신 시장경로 판정 보류"
        ) from ftp_exc


def official_effr():
    data = get_json(
        NYFED_EFFR,
        "https://www.newyorkfed.org/markets/reference-rates/effr",
        retries=1, timeout=8,
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


def official_fomc_dates():
    raw, _ = v3.base.fetch(v3.base.FED_CALENDAR)
    text = v3.base.clean_text(raw)
    today = ny_today()
    month_re = "|".join(calendar.month_name[1:])
    out = []
    for year in (today.year, today.year + 1):
        start = text.find(f"{year} FOMC Meetings")
        if start < 0:
            continue
        end = text.find(f"{year + 1} FOMC Meetings", start + 1)
        section = text[start:end if end >= 0 else None]
        # 공식 달력의 정규 FOMC는 2일 범위로 표시된다.
        # 의사록 공개일(예: October 7)을 정책회의로 오인하지 않도록
        # 반드시 '월 일-일' 범위만 회의일로 인정한다.
        for m in re.finditer(
            rf"\b({month_re})\s+(\d{{1,2}})-(\d{{1,2}})\*?",
            section,
            re.I,
        ):
            month = list(calendar.month_name).index(m.group(1).capitalize())
            day = int(m.group(3))
            try:
                d = datetime(year, month, day).date()
            except ValueError:
                continue
            if d >= today:
                out.append(d)
    out = sorted(dict.fromkeys(out))
    if not out:
        raise RuntimeError("연준 공식 FOMC 회의일 파싱 실패")
    return out


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
    try:
        effr_age = (ny_today() - datetime.strptime(effr_date[:10], '%Y-%m-%d').date()).days
    except (ValueError, TypeError):
        raise RuntimeError('뉴욕연은 EFFR 기준일 검증 실패')
    if not 0 <= effr_age <= 7:
        raise RuntimeError(f'뉴욕연은 EFFR 오래됨: {effr_date}, {effr_age}일')
    policy = v3.base.official_policy_baseline()
    if not policy or policy.get('low') is None or policy.get('high') is None:
        raise RuntimeError('연준 공식 목표금리 확인 불가 — CME 경로 판정 유보')
    if not float(policy['low']) - 0.03 <= effr <= float(policy['high']) + 0.03:
        raise RuntimeError('뉴욕연은 EFFR와 연준 공식 목표금리 불일치 — 경로 판정 유보')
    # 회의 날짜도 제3자 시장화면이 아니라 연준 공식 FOMC 달력에서 직접 읽는다.
    today = ny_today()
    future = official_fomc_dates()

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
        # 회의 직후의 월내 일수가 적을 때 결제값 오차가 크게 증폭될 수 있다.
        # 100bp를 넘는 단일 회의 추론·비정상 금리 수준은 발송하지 않는다.
        if not (math.isfinite(post) and math.isfinite(change) and 0.0 <= post <= 15.0 and abs(change) <= 100.0):
            raise RuntimeError(f'CME 월물 정책경로 비정상값: {d.isoformat()} {change:.1f}bp')
        dist = adjacent_distribution(change)
        result.append({
            "date":d.isoformat(),
            "label":f"{calendar.month_abbr[d.month]} {d.day}, {d.year}",
            "prob_cell":"CME 결제값 기반 확률 역산 보류", 

            "implied_avg":avg,
            "pre_rate":pre,
            "post_rate":post,
            "change_bp":change,
            "hike25_prob":None,  # 공식 CME FedWatch 확률이 아닌 2구간 추정치를 확정 확률로 내지 않는다.
            "hike25_or_more_prob":None,
            "hold_prob":None,
            "cut_prob":None,
            "outcomes":{},  # 월평균 선물 결제값과 실제 FedWatch 확률 분포를 혼동하지 않음.
            "contract":f"ZQ-{d.year:04d}-{d.month:02d}",
        })
        prev_post = post

    if not result:
        raise RuntimeError("CME 월물과 향후 FOMC 회의 연결 실패")
    current_year_meetings = [d for d in future if d.year == today.year]
    if current_year_meetings:
        terminal = max(current_year_meetings).isoformat()
        if not any(m['date'] == terminal for m in result):
            raise RuntimeError(f'CME 연말 FOMC 금리선물 누락: {terminal}')
    lag = (today - datetime.strptime(trade_date,"%Y-%m-%d").date()).days
    if lag > 4:
        raise RuntimeError(f"CME 결제값 오래됨: {trade_date}, {lag}일 전")

    snap = {
        "effr":effr,
        "effr_date":effr_date,
        "meetings":result[:6],
        "url":CME_SETTLEMENTS_PAGE,
        "market_data_basis":"CME 공식 지연 결제값 기반 금리 기대(확률 별도 확인 전 판정 유보)",
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

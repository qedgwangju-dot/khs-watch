"""Actual consolidated equity turnover and explicitly labelled NQ reference size.

Turnover is Cboe's sum of execution price times shares, never close times volume.
NQ reference size is a dated cash-index valuation, never trading cash flow.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import csv
import io
import re

from us_positioning_context import close_map, day, sessions
from us_positioning_horizons import months_before
from us_positioning_fx import collect_fx, checked_fx

MARKET_URL = "https://cdn.cboe.com/resources/us/equities/market-statistics/historical-market-volume/market_history_{year}.csv"
MARKET_DEFINITION = "https://www.cboe.com/markets/us/equities/market-statistics/historical-market-volume/"
NQ_CONTRACT = "https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.contractSpecs.html"
# Reviewed against the official 2026-07 through 2026-10 consolidated files.
# A venue roster change must be reviewed instead of producing a partial total.
VENUES = frozenset("A B C DB DN DQ F G H J K L M N P Q U V X Y Z".split())
FIELDS = ["Day", "Market Participant", *[f"Tape {t} Shares" for t in "ABC"],
          "Total Shares", *[f"Tape {t} Notional" for t in "ABC"], "Total Notional",
          *[f"Tape {t} Trade Count" for t in "ABC"], "Total Trade Count"]


def decimal(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("금액 원값 누락")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("금액 원값 비정상") from None
    if not result.is_finite():
        raise ValueError("금액 원값 비정상")
    return result


def _amount(value):
    result = decimal(value)
    if result < 0:
        raise ValueError("거래대금 음수")
    return result


def turnover_from_operands(operands, end_date):
    end = day(end_date)
    out = dict(status="unavailable", end_date=end.isoformat(), currency="USD",
               scope="US consolidated equities; all exchanges and TRFs; Tapes A/B/C",
               basis="sum of each execution price times shares; Cboe published notional",
               source_url=MARKET_DEFINITION)
    try:
        required = sessions(months_before(end, 3) + timedelta(days=1), end)
        if not required or required[-1] != end.isoformat() or len(required) < 5:
            raise ValueError("거래대금 기준일·미국 거래일 미확인")
        if [row[0] for row in operands] != required:
            raise ValueError("거래대금 기간 내 거래일 누락·중복")
        totals = {}
        for observed, venues in operands:
            codes = [v[0] for v in venues]
            if len(codes) != len(VENUES) or set(codes) != VENUES:
                raise ValueError("거래소·TRF 목록 누락·중복·변경: " + observed)
            values = []
            for venue in venues:
                if len(venue) != 5:
                    raise ValueError("거래대금 열 미확인")
                a, b, c, total = [_amount(v) for v in venue[1:]]
                if abs(a+b+c-total) > Decimal("0.000010"):
                    raise ValueError("Tape별·전체 거래대금 합계 불일치: " + observed)
                values.append(total)
            totals[observed] = sum(values, Decimal(0))
            if totals[observed] <= 0:
                raise ValueError("거래대금이 0이거나 미보고: " + observed)
        latest, previous = totals[required[-1]], totals[required[-2]]
        windows = {}
        for key, dates in [("5d", required[-5:]), *[(f"{m}m", sessions(months_before(end, m)+timedelta(days=1), end)) for m in (1,3)]]:
            total = sum((totals[d] for d in dates), Decimal(0))
            windows[key] = dict(start_date=dates[0], end_date=dates[-1], sessions=len(dates),
                                session_dates=dates, total_usd=str(total), average_daily_usd=str(total/len(dates)))
        out.update(status="verified", daily_usd=str(latest), previous_date=required[-2],
                   previous_daily_usd=str(previous), change_usd=str(latest-previous),
                   change_pct=str((latest/previous-1)*100), windows=windows,
                   daily_operands=operands, required_venue_codes=sorted(VENUES))
    except (KeyError, TypeError, ValueError, IndexError):
        out["reason"] = "공식 거래대금의 날짜·거래소·Tape 합계 검산 미완료"
    return out


def parse_turnover_csv(raw_pages, end_date):
    end = day(end_date)
    start = months_before(end, 3)+timedelta(days=1)
    grouped = {}
    try:
        for raw in raw_pages:
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            if reader.fieldnames != FIELDS:
                raise ValueError("거래대금 CSV 열 변경")
            for row in reader:
                observed = day(row["Day"])
                if not start <= observed <= end:
                    continue
                code = re.search(r"\(([A-Z]{1,2})\)$", row["Market Participant"])
                if not code or None in row:
                    raise ValueError("거래소 식별자 또는 열 누락")
                # Independently validate all three published row totals.
                for kind in ("Shares", "Notional", "Trade Count"):
                    numbers = [_amount(row[f"Tape {t} {kind}"]) for t in "ABC"]
                    total = _amount(row[f"Total {kind}"])
                    if abs(sum(numbers, Decimal(0))-total) > (Decimal(0) if kind == "Trade Count" else Decimal("0.000010")):
                        raise ValueError("CSV Tape 합계 불일치")
                    if kind == "Trade Count" and any(n != n.to_integral_value() for n in numbers+[total]):
                        raise ValueError("체결 건수 단위 비정상")
                grouped.setdefault(observed.isoformat(), []).append([code[1], *[row[f"Tape {t} Notional"] for t in "ABC"], row["Total Notional"]])
        operands = [[d, sorted(v)] for d,v in sorted(grouped.items())]
        return turnover_from_operands(operands, end)
    except (UnicodeError, KeyError, TypeError, ValueError, csv.Error):
        result = turnover_from_operands([], end)
        result["reason"] = "공식 거래대금 CSV 열·단위·합계 확인 대기"
        return result


def checked_turnover(value, end_date):
    if not isinstance(value, dict) or value.get("status") != "verified":
        return None
    try:
        computed = turnover_from_operands(value["daily_operands"], end_date)
        return value if computed == value and computed["status"] == "verified" else None
    except (KeyError, TypeError, ValueError):
        return None


def reference_price(primary, secondary, report_date):
    target = day(report_date)
    value = dict(status="unavailable", date=target.isoformat(), symbol="NDX",
                 basis="same-date cash NDX close reference; not expiry-specific futures settlement",
                 multiplier_usd_per_point="20", contract_source=NQ_CONTRACT)
    try:
        if sessions(target, target) != [target.isoformat()]:
            raise ValueError("주간 기준일 미확인")
        p, s = close_map(primary).get(target.isoformat()), close_map(secondary).get(target.isoformat())
        a, b = decimal(p), decimal(s)
        value.update(primary_close=p, secondary_close=s)
        if min(a,b) <= 0 or abs(a-b) > Decimal("0.10"):
            raise ValueError("NDX 기준일 종가 불일치")
        value["status"] = "verified"
    except (KeyError, TypeError, ValueError):
        value["reason"] = "NDX 기준일 종가 누락·제공처 불일치"
    return value


def checked_reference(value, report_date):
    if not isinstance(value, dict) or value.get("status") != "verified":
        return None
    try:
        computed = reference_price([(value["date"],value["primary_close"])], [(value["date"],value["secondary_close"])], report_date)
        return value if value == computed else None
    except (KeyError, TypeError, ValueError):
        return None


def notional(contracts, reference, report_date):
    reference = checked_reference(reference, report_date)
    try:
        count = decimal(contracts)
        if reference is None or count != count.to_integral_value():
            return None
        return count*decimal(reference["primary_close"])*Decimal(20)
    except ValueError:
        return None


def _money(value, currency, signed=False):
    value = decimal(value)
    if currency == "USD":
        units = [(Decimal("1e12"), "조달러",4), (Decimal("1e8"),"억달러",2), (Decimal("1e4"),"만달러",2)]
    else:
        units = [(Decimal("1e12"), "조원",2), (Decimal("1e8"),"억원",2), (Decimal("1e4"),"만원",2)]
    divisor, unit, places = next(((d,u,p) for d,u,p in units if abs(value)>=d), (Decimal(1),"달러" if currency=="USD" else "원",2))
    shown = (value/divisor).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if shown == 0:
        shown = abs(shown)
    return format(shown, ("+" if signed else "")+f",.{places}f")+unit


def money_pair(value, fx, target, signed=False):
    rate = checked_fx(fx, target)
    try:
        original = _money(value,"USD",signed)
    except ValueError:
        return "금액 확인 대기"
    if rate is None:
        return original+" (원화 환산 보류: 해당일 ECOS 미확인)"
    return original+" ("+_money(decimal(value)*decimal(rate["krw_per_usd"]),"KRW",signed)+")"


def report_day(cftc):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(str((cftc or {}).get("period")),fmt).date()
        except ValueError:
            pass
    return None


def collect_amounts(reader, end_date, cftc, reference):
    end, report = day(end_date), report_day(cftc)
    def market():
        try:
            years = range((months_before(end,3)+timedelta(days=1)).year,end.year+1)
            return parse_turnover_csv([reader.get(MARKET_URL.format(year=y)) for y in years],end)
        except Exception:
            value=turnover_from_operands([],end)
            value["reason"]="Cboe 실제 거래대금 원자료 확인 대기"
            return value
    with ThreadPoolExecutor(max_workers=3) as pool:
        turnover=pool.submit(market)
        fx=pool.submit(collect_fx,reader,end)
        report_fx=pool.submit(collect_fx,reader,report) if report and report!=end else fx
        return dict(turnover=turnover.result(),fx=fx.result(),nq_reference=reference or {},
                    nq_fx=report_fx.result() if report else {})

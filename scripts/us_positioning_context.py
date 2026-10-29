"""Dated price paths, NQ position composition and Cboe historical volume context.

All calculations retain their operands. Missing sessions, conflicting providers
and partial historical windows remain unavailable; no forward fill is used.
"""
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from math import isfinite
from statistics import median
from pathlib import Path
from urllib.parse import urlencode, quote
import gzip
import hashlib
import json
import os
import re
import threading
import time
from zoneinfo import ZoneInfo

from us_positioning_horizons import months_before

NY = ZoneInfo("America/New_York")
CBOE_DAILY = "https://www.cboe.com/markets/us/options/market-statistics/daily?dt={date}"
SPX_HISTORY = "https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_SPX.json"


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value)


def day(value):
    return value if type(value) is date else date.fromisoformat(str(value)[:10])


def sessions(start, end):
    # XNYS includes observed holidays and historical exceptional closures.
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    return [d.date().isoformat() for d in cal.sessions_in_range(str(start), str(end))]


def close_map(rows):
    out = {}
    for d, value in rows:
        d = day(d).isoformat()
        if d in out and out[d] != value:
            raise ValueError("동일 날짜 종가 충돌: " + d)
        out[d] = value
    return out


def price_path(end_date, primary_rows, secondary_rows, symbol, tolerance=0.10):
    end = day(end_date)
    result = dict(status="unavailable", end_date=end.isoformat(), symbol=symbol,
                  tolerance_points=tolerance, price_basis="unadjusted completed-session close")
    try:
        primary = close_map((d,v) for d,v in primary_rows if day(d) <= end)
        secondary = close_map((d,v) for d,v in secondary_rows if day(d) <= end)
        calendar = sessions(end - timedelta(days=200), end)
        if not calendar or calendar[-1] != end.isoformat():
            raise ValueError("목표일이 확인된 미국 거래일이 아님")
        required = calendar[-65:]
        if len(required) < 65:
            raise ValueError("20·60일 비교에 필요한 65거래일 부족")
        for d in required:
            a, b = primary.get(d), secondary.get(d)
            if not all(finite(v) and v > 0 for v in (a, b)):
                raise ValueError("거래일 종가 누락·비정상: " + d)
            if abs(a - b) > tolerance:
                raise ValueError("제공처 종가 불일치: " + d)
        values = [primary[d] for d in required]
        latest = values[-1]
        calc = {f"d{n}_pct": (latest / values[-n-1] - 1) * 100 for n in (1, 3, 5)}
        for n in (20, 60):
            current = sum(values[-n:]) / n
            previous = sum(values[-n-5:-5]) / n
            calc.update({f"ma{n}": current, f"ma{n}_prior5": previous,
                         f"ma{n}_change5_pct": (current / previous - 1) * 100,
                         f"price_vs_ma{n}_pct": (latest / current - 1) * 100})
        peak = max(values[-63:])
        peak_day = max(d for d in required[-63:] if primary[d] == peak)
        calc.update(close=latest, peak63_close=peak, peak63_date=peak_day,
                    drawdown63_pct=(latest / peak - 1) * 100)
        up = latest > calc["ma20"] > calc["ma60"] and all(calc[f"ma{n}"] > calc[f"ma{n}_prior5"] for n in (20, 60))
        down = latest < calc["ma20"] < calc["ma60"] and all(calc[f"ma{n}"] < calc[f"ma{n}_prior5"] for n in (20, 60))
        calc["trend"] = "상승" if up else "하락" if down else "혼재"
        windows = {}
        for m in (1, 3):
            cutoff = months_before(end, m)
            bases = sessions(cutoff - timedelta(days=10), cutoff)
            if not bases:
                raise ValueError("달력 기준 거래일 미확인")
            baseline = bases[-1]
            a, b = primary.get(baseline), secondary.get(baseline)
            if not all(finite(v) and v > 0 for v in (a, b)) or abs(a - b) > tolerance:
                windows[f"{m}m"] = dict(status="unavailable", reason="동일 기준일 종가 누락·불일치", base_date=baseline)
            else:
                windows[f"{m}m"] = dict(status="verified", base_date=baseline, end_date=end.isoformat(),
                    base_primary_close=a, base_secondary_close=b, end_close=latest,
                    return_pct=(latest / a - 1) * 100)
        # Only dated operands used by this calculation are persisted.
        selected = sorted(set(required) | {w["base_date"] for w in windows.values()})
        result.update(status="verified", values=calc, month_windows=windows,
                      operands=[[d, primary.get(d), secondary.get(d)] for d in selected],
                      session_dates=required)
    except Exception as exc:
        result["reason"] = str(exc)
    return result


def checked_path(value, end_date=None, expected_symbol=None):
    if not value or value.get("status") != "verified":
        return None
    if value.get("tolerance_points") != 0.10:
        return None
    if expected_symbol is not None and value.get("symbol") != expected_symbol:
        return None
    if end_date is not None and value.get("end_date") != day(end_date).isoformat():
        return None
    rows = value.get("operands") or []
    try:
        actual = price_path(value["end_date"], [(r[0], r[1]) for r in rows],
                            [(r[0], r[2]) for r in rows], value["symbol"],
                            value["tolerance_points"])
        if actual.get("status") != "verified":
            return None
        for field in ("values", "month_windows", "session_dates", "operands"):
            if actual.get(field) != value.get(field):
                return None
        return actual
    except (KeyError, TypeError, ValueError):
        return None


def position_week_window(rows, end_date, current_nq):
    end = day(end_date)
    dated = {}
    for row in rows:
        d = day(row["date"])
        if d > end:
            continue
        if d in dated and dated[d] != row:
            raise ValueError("동일 주간 포지션 충돌")
        dated[d] = row
    result = dict(status="unavailable", end_date=end.isoformat(), cftc_code="209742",
                  market="NASDAQ MINI", actors={})
    earlier = sorted(d for d in dated if d < end)
    current = dated.get(end)
    if not current or not earlier:
        return {**result, "reason": "직전·현재 공식 주간 관측 누락"}
    base = earlier[-1]
    if (end - base).days > 14:
        return {**result, "reason": "직전 주간 관측 공백이 14일 초과"}
    for field, key in (("lev_long", "leveraged_long"), ("lev_short", "leveraged_short"), ("oi", "open_interest")):
        if current.get(field) != (current_nq or {}).get(key):
            raise ValueError("현재 NQ 원값과 주간 이력 불일치: " + field)
    result["base_date"] = base.isoformat()
    for prefix, actor in (("lev", "leveraged_funds"), ("asset", "asset_manager")):
        vals = [dated[base].get(prefix+"_long"), dated[base].get(prefix+"_short"),
                current.get(prefix+"_long"), current.get(prefix+"_short")]
        if not all(finite(v) and v >= 0 for v in vals):
            result["actors"][actor] = dict(status="unavailable", reason="롱·숏 원값 누락")
            continue
        bl, bs, el, es = vals
        result["actors"][actor] = dict(status="verified", base_long=bl, base_short=bs,
            end_long=el, end_short=es, base_net=bl-bs, end_net=el-es,
            long_change=el-bl, short_change=es-bs, net_change=(el-es)-(bl-bs))
    result["status"] = "verified" if result["actors"].get("leveraged_funds", {}).get("status") == "verified" else "unavailable"
    return result


def checked_composition(window, actor, end_date):
    """Validate all three deltas; do not infer orders, covering or hedge intent."""
    if not window or window.get("status") != "verified" or window.get("cftc_code") != "209742":
        return None
    try:
        end, base = day(window["end_date"]), day(window["base_date"])
        if end != day(end_date) or base >= end:
            return None
        if "calendar_months" in window:
            cutoff = months_before(end, window["calendar_months"])
            if window["calendar_months"] not in (1, 3) or window.get("cutoff_date") != cutoff.isoformat() or not 0 <= (cutoff-base).days <= 14:
                return None
        elif (end-base).days > 14:
            return None
        v = window["actors"][actor]
        bl, bs, el, es = [v[k] for k in ("base_long", "base_short", "end_long", "end_short")]
        if v.get("status") != "verified" or not all(finite(x) and x >= 0 for x in (bl, bs, el, es)):
            return None
        computed = dict(base_net=bl-bs, end_net=el-es, long_change=el-bl,
                        short_change=es-bs, net_change=(el-es)-(bl-bs))
        return computed if all(v.get(k) == x for k, x in computed.items()) else None
    except (KeyError, TypeError, ValueError):
        return None


def parse_cboe_day(raw, expected_date):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw, "html.parser")
    # This visible date is rendered alongside the returned statistics. A request
    # query string or a selectedDate echo alone is not a publication-date check.
    visible_dates = []
    for node in soup.select("input[value]"):
        try:
            visible_dates.append(datetime.strptime(node["value"], "%d %B %Y").date())
        except ValueError:
            pass
    if visible_dates != [day(expected_date)]:
        raise ValueError("Cboe 통계의 표시 기준일 누락·불일치")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    headers = [("total", "SUM OF ALL PRODUCTS", "INDEX OPTIONS"),
               ("index", "INDEX OPTIONS", "EXCHANGE TRADED PRODUCTS"),
               ("equity", "EQUITY OPTIONS", "CBOE VOLATILITY INDEX")]
    result = dict(date=day(expected_date).isoformat(), metrics={})
    for key, heading, following in headers:
        start = text.find(heading)
        stop = text.find(following, start+len(heading))
        section = text[start:stop if stop >= 0 else None] if start >= 0 else ""
        volume = re.search(r"\bVOLUME\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", section)
        ratio = re.search(r"\b"+key.upper()+r" PUT/CALL RATIO\s+([0-9]+(?:\.[0-9]+)?)", text)
        if not volume or not ratio:
            raise ValueError("Cboe 일별 마감 행 누락: "+key)
        calls, puts, total = [int(s.replace(",", "")) for s in volume.groups()]
        pc = float(ratio.group(1))
        if calls <= 0 or calls+puts != total or abs(puts/calls-pc) > .015:
            raise ValueError("Cboe 거래량·P/C 산술 불일치: "+key)
        result["metrics"].update({key+"_calls": calls, key+"_puts": puts, key+"_pc_ratio": pc})
    return result


def option_distributions(rows, end_date, current_metrics):
    end = day(end_date)
    dated = {}
    duplicate_error = None
    for row in rows:
        d = day(row["date"]).isoformat()
        if not months_before(end,3).isoformat() <= d < end.isoformat():
            continue
        if d in dated and dated[d] != row:
            duplicate_error = "동일 날짜 Cboe 과거 원값 충돌"
        dated[d] = row
    result = {}
    for m in (1, 3):
        cutoff = months_before(end, m)
        expected = sessions(cutoff, end-timedelta(days=1))
        item = dict(status="unavailable", start_date=cutoff.isoformat(),
                    end_exclusive=end.isoformat(), expected_sessions=len(expected),
                    basis="published daily P/C; current day excluded; <= tie convention")
        missing = [d for d in expected if d not in dated]
        if missing or duplicate_error:
            item.update(reason=duplicate_error or "기간 내 공식 일별 자료 누락", missing_dates=missing)
        else:
            try:
                values = {}
                for key in ("equity", "index", "total"):
                    pc = current_metrics.get(key+"_pc_ratio")
                    if not finite(pc) or pc < 0:
                        raise ValueError("현재 P/C 미확인")
                    operands = []
                    for d in expected:
                        mt = dated[d]["metrics"]
                        calls, puts, ratio = [mt.get(key+suffix) for suffix in ("_calls", "_puts", "_pc_ratio")]
                        if not all(finite(v) and v >= 0 for v in (calls, puts, ratio)) or calls <= 0 or abs(puts/calls-ratio) > .015:
                            raise ValueError("과거 P/C와 거래량 불일치: "+d)
                        operands.append(dict(date=d, calls=calls, puts=puts, pc_ratio=ratio))
                    sample = [x["pc_ratio"] for x in operands]
                    if len(sample) < (15 if m == 1 else 45):
                        raise ValueError("해당 기간 표본 부족")
                    values[key] = dict(current_pc=pc, sample_n=len(sample), median_pc=median(sample),
                        current_le_percent=sum(x <= pc for x in sample)/len(sample)*100,
                        min_pc=min(sample), max_pc=max(sample), operands=operands)
                item.update(status="verified", values=values, missing_dates=[])
            except Exception as exc:
                item["reason"] = str(exc)
        result[f"{m}m"] = item
    return result


def checked_options(value, current_metrics, end_date):
    if not value or value.get("status") != "verified" or value.get("end_exclusive") != day(end_date).isoformat():
        return None
    rows = {}
    try:
        for key in ("equity", "index", "total"):
            for r in value["values"][key]["operands"]:
                mt = rows.setdefault(r["date"], dict(date=r["date"], metrics={}))["metrics"]
                mt.update({key+"_calls": r["calls"], key+"_puts": r["puts"], key+"_pc_ratio": r["pc_ratio"]})
        calculated = option_distributions(list(rows.values()), end_date, current_metrics)
        return value if any(value == w for w in calculated.values()) else None
    except (KeyError, TypeError, ValueError):
        return None


def parse_yahoo(payload, symbol, expected_date):
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result or result.get("meta", {}).get("symbol") != symbol:
        raise ValueError("Yahoo 반환 종목 코드 불일치: "+symbol)
    if result.get("meta", {}).get("currency") != "USD":
        raise ValueError("Yahoo 통화 단위 미확인")
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    closes = (indicators.get("quote") or [{}])[0].get("close") or []
    adj = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
    if len(timestamps) != len(closes) or (adj and len(adj) != len(timestamps)):
        raise ValueError("Yahoo 날짜·종가 배열 길이 불일치")
    raw, adjusted = [], []
    for i, ts in enumerate(timestamps):
        d = datetime.fromtimestamp(ts, timezone.utc).astimezone(NY).date()
        if d <= day(expected_date):
            raw.append((d.isoformat(), closes[i]))
            if adj:
                adjusted.append((d.isoformat(), adj[i]))
    return raw, adjusted


def parse_nasdaq(payload, symbol, expected_date):
    data = payload.get("data") or {}
    if data.get("symbol") != symbol:
        raise ValueError("Nasdaq 반환 종목 코드 불일치: "+symbol)
    out = []
    for row in (data.get("tradesTable") or {}).get("rows") or []:
        d = datetime.strptime(row["date"], "%m/%d/%Y").date()
        if d <= day(expected_date):
            close = float(str(row["close"]).replace("$", "").replace(",", ""))
            out.append((d.isoformat(), close))
    if not out:
        raise ValueError("Nasdaq 날짜별 종가 누락")
    return out


class SourceReader:
    def __init__(self, output):
        self.output = Path(output)
        self.directory = self.output/"us_positioning_sources"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.records = []
        self.lock = threading.Lock()
        self.deadline = time.monotonic()+150

    def get(self, url, *, evidence_url=None):
        import requests
        if time.monotonic() >= self.deadline:
            raise TimeoutError("맥락 원자료 수집 제한시간")
        started = datetime.now(timezone.utc).isoformat()
        rec = dict(url=evidence_url or url,started_at_utc=started)
        if evidence_url is not None:
            rec["request_credentials_redacted"] = True
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/html,*/*"}, timeout=(5,12))
            raw = response.content
            digest = hashlib.sha256(raw).hexdigest()
            filename = digest+".gz"
            with self.lock:
                with gzip.open(self.directory/filename, "wb") as f:
                    f.write(raw)
            rec.update(status=response.status_code, final_url=evidence_url or response.url,
                       bytes=len(raw), sha256=digest, gzip_file="us_positioning_sources/"+filename)
            response.raise_for_status()
            return raw
        except Exception as exc:
            rec["error"] = (type(exc).__name__+": protected source request failed"
                            if evidence_url is not None else type(exc).__name__+": "+str(exc))
            raise
        finally:
            rec["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            with self.lock:
                self.records.append(rec)

    def save(self):
        ledger = dict(requests=sorted(self.records,key=lambda x:x["url"]),
            raw_HTTP_bytes_gzip_preserved=True, price_basis="completed sessions only",
            github_run_id=os.getenv("GITHUB_RUN_ID"),
            github_code_sha=os.getenv("US_POSITIONING_CHECKOUT_SHA") or os.getenv("GITHUB_SHA"),
            github_event_sha=os.getenv("GITHUB_SHA"))
        (self.output/"us_positioning_source_evidence.json").write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def collect_context(sox, cboe, output, cftc=None):
    """Supplementary lanes fail individually; never turn missingness into a signal."""
    expected = day(datetime.strptime(sox["period"], "%m/%d/%Y").date())
    reader = SourceReader(output)
    current_options = cboe["metrics"]
    indices, proxies = {}, {}
    references = {}
    from us_positioning_amounts import reference_price, collect_amounts, report_day
    report = report_day(cftc)

    def asset(symbol, yahoo_symbol, assetclass):
        yurl = "https://query1.finance.yahoo.com/v8/finance/chart/"+quote(yahoo_symbol,safe="")+"?range=6mo&interval=1d"
        yrows, adj = parse_yahoo(json.loads(reader.get(yurl)), yahoo_symbol, expected)
        if symbol == "SPX":
            purl = SPX_HISTORY
            data = json.loads(reader.get(purl))
            if data.get("symbol") != "_SPX":
                raise ValueError("Cboe 반환 종목 코드가 _SPX가 아님")
            prows = [(r["date"],float(r["close"])) for r in data.get("data",[]) if day(r["date"]) <= expected]
        else:
            params = urlencode(dict(assetclass=assetclass, fromdate=(expected-timedelta(days=190)).isoformat(),
                                   todate=expected.isoformat(),limit=200))
            purl = "https://api.nasdaq.com/api/quote/"+symbol+"/historical?"+params
            prows = parse_nasdaq(json.loads(reader.get(purl)),symbol,expected)
        if symbol == "NDX" and report is not None:
            references["nq"] = reference_price(prows, yrows, report)
        path = price_path(expected, prows, yrows, symbol)
        path.update(primary_url=purl, secondary_url=yurl)
        path["returns"] = price_returns(expected,prows,yrows,symbol)
        if assetclass == "etf" and path["status"] == "verified":
            path["adjusted_operands"] = [[d,v] for d,v in adj]
        return path

    def fetch_asset(args):
        symbol, yahoo_symbol, assetclass = args
        try:
            return symbol, asset(symbol,yahoo_symbol,assetclass)
        except Exception as exc:
            return symbol, dict(status="unavailable", end_date=expected.isoformat(),symbol=symbol,reason=str(exc))

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for symbol,result in pool.map(fetch_asset,[("NDX","^NDX","index"),("SPX","^GSPC","index"),("RSP","RSP","etf"),("SPY","SPY","etf")]):
                (proxies if symbol in ("RSP","SPY") else indices)[symbol] = result
        amounts = collect_amounts(reader, expected, cftc, references.get("nq"))
        dates = sessions(months_before(expected,3),expected-timedelta(days=1))
        def option_row(d):
            try:
                return parse_cboe_day(reader.get(CBOE_DAILY.format(date=d)),d)
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            option_rows = [r for r in pool.map(option_row,dates) if r is not None]
        options = option_distributions(option_rows,expected,current_options)
        context = dict(indices=indices, breadth=dict(series=proxies,
            comparison=breadth_comparison(proxies,expected)), options=options, amounts=amounts)
        return context
    finally:
        reader.save()


def breadth_comparison(series, end_date):
    result = dict(status="unavailable", end_date=day(end_date).isoformat(),
        basis="RSP vs SPY; Yahoo dividend/split-adjusted closes; Nasdaq raw-close cross-check",
        population="ETF relative performance; not advancing-stock percentage")
    left, right = [checked_path(series.get(k),end_date,k) for k in ("RSP","SPY")]
    if left is None or right is None:
        return {**result,"reason":"동일 날짜 ETF 원종가·교차검증 미확인"}
    try:
        maps = {k:close_map(series[k].get("adjusted_operands",[])) for k in ("RSP","SPY")}
        required = left["session_dates"]
        if required != right["session_dates"]:
            raise ValueError("ETF 거래일 범위 불일치")
        windows = {}
        for key in ("5d","1m","3m"):
            if key == "5d":
                base = required[-6]
            else:
                a, b = left["month_windows"][key], right["month_windows"][key]
                if a["status"] != "verified" or b["status"] != "verified" or a["base_date"] != b["base_date"]:
                    raise ValueError("ETF 기간 기준일 불일치·미확인")
                base = a["base_date"]
            end = day(end_date).isoformat()
            vals = [maps[k].get(d) for k in ("RSP","SPY") for d in (base,end)]
            if not all(finite(v) and v > 0 for v in vals):
                raise ValueError("ETF 배당조정 기준·종료값 누락")
            rl, rr = [(vals[i+1]/vals[i]-1)*100 for i in (0,2)]
            windows[key] = dict(base_date=base,end_date=end,rsp_base=vals[0],rsp_end=vals[1],
                spy_base=vals[2],spy_end=vals[3],rsp_return_pct=rl,spy_return_pct=rr,
                difference_pp=rl-rr)
        return {**result,"status":"verified","windows":windows}
    except Exception as exc:
        return {**result,"reason":str(exc)}


def context_change_key(context, end_date):
    """Ignore only unused adjusted ETF rows after rechecking the dated comparison.

    Full inputs remain in the state/evidence. Used endpoints, all raw-close
    paths, dates, validation states and every other context field stay exact.
    No rounding, numerical tolerance or old-value substitution is applied.
    """
    value = deepcopy(context)
    if not isinstance(value, dict):
        return value
    breadth = value.get("breadth") or {}
    try:
        computed = breadth_comparison(breadth.get("series", {}), end_date)
        if computed.get("status") != "verified" or computed != breadth.get("comparison"):
            return value
        dates = {w[k] for w in computed["windows"].values() for k in ("base_date", "end_date")}
        for symbol in ("RSP", "SPY"):
            series = breadth["series"][symbol]
            series["adjusted_operands"] = [row for row in series["adjusted_operands"] if row[0] in dates]
    except (KeyError, TypeError, ValueError, AttributeError):
        return deepcopy(context)
    return value


def remember_verified_context_fx(existing, *contexts):
    """Keep verified FX operands for comparison, never for report rendering."""
    from us_positioning_fx import checked_fx

    saved = {}
    if isinstance(existing, dict):
        for name in ("fx", "nq_fx"):
            value = existing.get(name)
            if isinstance(value, dict) and checked_fx(value, value.get("requested_date")):
                saved[name] = deepcopy(value)
    for context in contexts:
        amounts = context.get("amounts", {}) if isinstance(context, dict) else {}
        if not isinstance(amounts, dict):
            continue
        for name in ("fx", "nq_fx"):
            value = amounts.get(name)
            if isinstance(value, dict) and checked_fx(value, value.get("requested_date")):
                saved[name] = deepcopy(value)
    return saved


def context_equal_except_transient_fx(previous, current, end_date, verified_fx=None):
    """Ignore a same-date ECOS collection failure for change detection only.

    On recovery, suppress it only when the verified rate equals a retained,
    independently checked observation. No old value enters the report itself.
    """
    from us_positioning_fx import checked_fx

    before = context_change_key(previous, end_date)
    after = context_change_key(current, end_date)
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    old_amounts, new_amounts = before.get("amounts"), after.get("amounts")
    if not isinstance(old_amounts, dict) or not isinstance(new_amounts, dict):
        return False
    baselines = verified_fx if isinstance(verified_fx, dict) else {}
    replaced = False
    for name in ("fx", "nq_fx"):
        old, new = old_amounts.get(name), new_amounts.get(name)
        if not isinstance(old, dict) or not isinstance(new, dict):
            continue
        date = old.get("requested_date")
        if not date or date != new.get("requested_date"):
            continue
        old_failed = old.get("status") == "unavailable" and old.get("reason_code") == "collection"
        new_failed = new.get("status") == "unavailable" and new.get("reason_code") == "collection"
        if new_failed and checked_fx(old, date):
            new_amounts[name] = deepcopy(old)
            replaced = True
        elif old_failed and checked_fx(new, date):
            baseline = baselines.get(name)
            if checked_fx(baseline, date):
                old_amounts[name] = deepcopy(baseline)
                replaced = True
    return replaced and before == after


def price_returns(end_date, primary_rows, secondary_rows, symbol):
    """Verify each return independently of an intermediate trend-history conflict."""
    end = day(end_date)
    out = dict(status="unavailable",symbol=symbol,end_date=end.isoformat(),windows={})
    try:
        primary = close_map((d,v) for d,v in primary_rows if day(d) <= end)
        secondary = close_map((d,v) for d,v in secondary_rows if day(d) <= end)
        dates = sessions(end-timedelta(days=200),end)
        if not dates or dates[-1] != end.isoformat():
            raise ValueError("목표일이 미국 거래일이 아님")
        latest, peer = primary.get(end.isoformat()),secondary.get(end.isoformat())
        if not all(finite(v) and v > 0 for v in (latest,peer)) or abs(latest-peer) > .10:
            raise ValueError("현재 종가 누락·제공처 불일치")
        required={end.isoformat()}
        for key in ("1d","3d","5d","1m","3m"):
            baseline=dates[-int(key[:-1])-1] if key.endswith("d") else sessions(months_before(end,int(key[:-1]))-timedelta(days=10),months_before(end,int(key[:-1])))[-1]
            required.add(baseline)
            a,b=primary.get(baseline),secondary.get(baseline)
            if all(finite(v) and v > 0 for v in (a,b)) and abs(a-b) <= .10:
                out["windows"][key]=dict(status="verified",base_date=baseline,end_date=end.isoformat(),base_primary=a,base_secondary=b,end_primary=latest,end_secondary=peer,return_pct=(latest/a-1)*100)
            else:
                out["windows"][key]=dict(status="unavailable",base_date=baseline,reason="기준 종가 누락·제공처 불일치")
        out.update(status="verified",close=latest,peer_close=peer,
                   operands=[[d,primary.get(d),secondary.get(d)] for d in sorted(required)])
    except Exception as exc:
        out["reason"]=str(exc)
    return out


def checked_returns(value,end_date,expected_symbol=None):
    if not value or value.get("status") != "verified" or value.get("end_date") != day(end_date).isoformat():
        return None
    if expected_symbol is not None and value.get("symbol") != expected_symbol:
        return None
    try:
        rows=value["operands"]
        computed=price_returns(end_date,[(r[0],r[1]) for r in rows],[(r[0],r[2]) for r in rows],value["symbol"])
        return value if value == computed else None
    except (KeyError,TypeError,ValueError):
        return None


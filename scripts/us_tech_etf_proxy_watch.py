#!/usr/bin/env python3
"""Public tech ETF creations/redemptions proxy in the EXISTING U.S. fund-flow route.

This is NOT JPMorgan's licensed retail order-imbalance series. Do not label
ETF share creations as retail purchases, secondary-market trades, or sector-
wide aggregate flows. Never transmit on a one-day initial baseline.
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
import math
import os
import pathlib
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import uuid

import requests
from zoneinfo import ZoneInfo

import treasury_etf_flow_watch as ishares

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "us_tech_etf_proxy_state.json"
OUT = ROOT / "out"
RECEIPT = OUT / "us_tech_etf_proxy_receipt.json"
CANDIDATE = OUT / "us_tech_etf_proxy_candidate.html"
IMAGE_CANDIDATE = OUT / "us_tech_etf_proxy_candidate.png"
FUNDS = {
    "IYW": {
        "label": "미국 기술주 ETF",
        "url": "https://www.ishares.com/us/products/239522/ishares-us-technology-etf",
    },
    "SOXX": {
        "label": "미국 반도체 ETF",
        "url": "https://www.ishares.com/us/products/239705/ishares-phlx-semiconductor-etf",
    },
}
# EWY extends the existing U.S. ETF watcher; no new sender or schedule.
# Failure to retrieve EWY must not stop legacy IYW/SOXX alerts.
OPTIONAL_KOREA_FUND = {
    "EWY": {
        "label": "미국 상장 한국 주식 ETF",
        "url": "https://www.ishares.com/us/products/239681/ishares-msci-south-korea-etf",
    }
}
PORTFOLIO_IDS = {"IYW":239522, "SOXX":239705, "EWY":239681}
HIST_URL = ("https://www.ishares.com/varnish-api/blk-one01-product-data/"
            "product-data/api/v2/get-product-data")
WINDOWS = ((21, "1개월"), (63, "3개월"))
HISTORY_LIMIT = 110
EXPECTED_BOT = "khs887900887900008879_bot"
class DeliveryUnconfirmed(RuntimeError):
    """A send was attempted but its exact outcome cannot safely be retried."""


class DeliveryRejected(RuntimeError):
    """Telegram explicitly rejected the request; no success key is recorded."""


class OfficialPublicationPending(RuntimeError):
    """A newly closed U.S. market session has not yet appeared in iShares data."""


ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")


def load_state(path=STATE):
    if not path.exists():
        return {"history": {}, "last_alert": None}
    try:
        x = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as e:
        raise RuntimeError("tech ETF saved state unreadable; refuse to reset") from e
    if not isinstance(x, dict) or not isinstance(x.get("history"), dict):
        raise RuntimeError("tech ETF saved state malformed; refuse to reset")
    return x


def save_state(state, path=STATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        f.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        tmp = f.name
    os.replace(tmp, path)


def exchange_sessions(start, end):
    import exchange_calendars
    cal = exchange_calendars.get_calendar("XNYS")
    return [x.date().isoformat() for x in cal.sessions_in_range(start, end)]


def latest_us_close(now):
    n = now.astimezone(ET)
    d = n.date()
    if n.time() < dt.time(18, 0):
        d -= dt.timedelta(days=1)
    sessions = exchange_sessions(d - dt.timedelta(days=14), d)
    if not sessions:
        raise ValueError("US exchange calendar has no completed session")
    return dt.date.fromisoformat(sessions[-1])


def collect(now=None, fetcher=ishares.get_ishares):
    now = now or dt.datetime.now(dt.timezone.utc)
    fund_rows = {}
    budget = ishares.IsharesRetryBudget()
    for ticker, meta in FUNDS.items():
        row = fetcher(ticker, meta, retry_budget=budget)
        if row.get("nav_date") != row.get("shares_date"):
            raise ValueError(f"{ticker}: NAV and shares outstanding have different source dates")
        if row.get("nav_date") != row.get("date"):
            raise ValueError(f"{ticker}: computed report date differs from fund observation")
        for col in ("nav", "shares"):
            v = row.get(col)
            if not isinstance(v, (float, int)) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"{ticker}: invalid official {col}")
        # The issuer also publishes total fund net assets. When available,
        # shares × NAV must reconcile to the same issuer's asset figure.
        assets = row.get("net_assets")
        if assets is not None:
            if not isinstance(assets, (int, float)) or not math.isfinite(assets) or assets <= 0:
                raise ValueError(f"{ticker}: invalid official fund net assets")
            discrepancy = abs(row["shares"] * row["nav"] / assets - 1.0) * 100
            if discrepancy > 1.0:
                raise ValueError(f"{ticker}: official fund net assets differ from NAV × outstanding shares by {discrepancy:.2f}%")
            row["asset_check_pct"] = discrepancy
        fund_rows[ticker] = row
    observed = {v["date"] for v in fund_rows.values()}
    if len(observed) != 1:
        raise ValueError("IYW/SOXX official observation dates not aligned")
    date = dt.date.fromisoformat(next(iter(observed)))
    latest = latest_us_close(now)
    if date > latest or (latest - date).days > 4:
        raise ValueError(f"ETF official data unavailable/stale: {date} vs US last close {latest}")
    if date < latest:
        prev_sessions = exchange_sessions(latest - dt.timedelta(days=14), latest)
        prev_day = dt.date.fromisoformat(prev_sessions[-2])
        if date == prev_day:
            raise OfficialPublicationPending(
                f"iShares official observation {date} awaits latest completed US session {latest}")
        raise ValueError(f"ETF official data unavailable/stale: {date} vs US last close {latest}")
    try:
        meta = OPTIONAL_KOREA_FUND["EWY"]
        ewy = fetcher("EWY", meta, retry_budget=budget)
        if not (ewy.get("date") == ewy.get("nav_date") == ewy.get("shares_date") == date.isoformat()):
            raise ValueError("EWY and technology ETF official NAV/share dates differ")
        for col in ("nav", "shares"):
            v = ewy.get(col)
            if not isinstance(v, (float, int)) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"EWY: invalid {col}")
        fund_rows["EWY"] = ewy
    except Exception as exc:
        # Preserve both mandatory technology ETF lanes; never impute stale EWY.
        print(f"ewy_optional_source_withheld=true type={type(exc).__name__} reason={str(exc)[:150]}")
    return fund_rows


def _consecutive_weekday_dates(rows):
    """Conservative 5D guard: require every intervening Monday-Friday date.

    Exchange holidays will withhold the cumulative signal rather than invent
    a closing observation. The daily comparison is unaffected.
    """
    if len(rows) < 2:
        return False
    day0 = dt.date.fromisoformat(rows[0]["date"])
    dayn = dt.date.fromisoformat(rows[-1]["date"])
    dates = []
    cursor = day0
    while cursor <= dayn:
        if cursor.weekday() < 5:
            dates.append(cursor.isoformat())
        cursor += dt.timedelta(days=1)
    return dates == [x["date"] for x in rows]



def issuer_nav_history(ticker, current):
    """Read the issuer's daily NAV/shares history, not ETF trading volume."""
    params = {"appSubType":"ISHARES", "appType":"PRODUCT_PAGE",
              "component":"fundDownload", "locale":"en_US",
              "portfolioId":str(PORTFOLIO_IDS[ticker]),
              "targetSite":"us-ishares", "userType":"individual",
              "excludeContent":"true"}
    resp = requests.get(HIST_URL, params=params,
                        headers=ishares.HEADERS, timeout=(7, 24))
    resp.raise_for_status()
    data = resp.json()
    cols = (data.get("componentsByNameMap", {}).get("fundDownload", {})
            .get("containersByNameMap", {}).get("historical", {})
            .get("dataPointsByNameMap", {}))
    try:
        days = cols["asof"]["value"]
        navs = cols["nav"]["value"]
        shares = cols["sharesOutstanding"]["value"]
    except (KeyError, TypeError) as exc:
        raise ValueError("iShares historical NAV and shares fields missing") from exc
    if not (isinstance(days,list) and len(days)==len(navs)==len(shares) and len(days)>63):
        raise ValueError("iShares historical observations missing or misaligned")
    def raw(x):
        return x.get("r") if isinstance(x,dict) else x
    out = {}
    for date,nav,share in zip(days,navs,shares):
        try:
            key = str(int(float(raw(date))))
            day = dt.datetime.strptime(key,"%Y%m%d").date().isoformat()
            if day > current["date"]:
                continue
            price = float(str(raw(nav)).replace(",",""))
            count = float(str(raw(share)).replace(",",""))
            if not all(map(math.isfinite,(price,count))) or price<=0 or count<=0:
                continue
        except (ValueError,TypeError,OverflowError):
            continue
        if day in out and (out[day]["shares"]!=count or out[day]["nav"]!=price):
            raise ValueError("Conflicting issuer historical share observations")
        out[day]={"date":day,"nav":price,"shares":count}
    if not out:
        raise ValueError("No valid historical records in issuer NAV feed")
    # Prevent stale/revised/split-adjusted history from silently replacing the
    # exact current issuer page or any already verified observation.
    today=out.get(current["date"])
    if today and (abs(today["shares"]-current["shares"])>1 or
                  abs(today["nav"]-current["nav"])>0.025):
        raise ValueError("Issuer historical and current fund page mismatch")
    return sorted(out.values(),key=lambda x:x["date"])[-HISTORY_LIMIT:]


def verified_backfill(state, current, *, fetcher=issuer_nav_history):
    """Optional, read-only issuer backfill. Never replace validated existing rows."""
    copied={**state,"history":{k:list(v) for k,v in state.get("history",{}).items()}}
    count=0
    for ticker,row in current.items():
        existing=copied["history"].get(ticker,[])
        if len(existing)>=70:
            continue
        try:
            fetched=fetcher(ticker,row)
            hist={z["date"]:z for z in fetched}
            if not any(z["date"] in hist for z in existing) and row["date"] not in hist:
                raise ValueError("Issuer history has no verifiable overlap")
            for saved in existing:
                candidate=hist.get(saved["date"])
                if candidate and (abs(candidate["shares"]-saved["shares"])>1 or
                                  abs(candidate["nav"]-saved["nav"])>0.025):
                    raise ValueError("Issuer historical revision conflicts with saved state")
                hist[saved["date"]]=saved
            hist[row["date"]]={"date":row["date"],"nav":row["nav"],"shares":row["shares"]}
            combined=sorted(hist.values(),key=lambda z:z["date"])[-HISTORY_LIMIT:]
            copied["history"][ticker]=combined
            count+=max(0,len(combined)-len(existing))
            print(f"tech_etf_issuer_backfill={ticker} verified_rows={len(combined)}")
        except Exception as exc:
            print(f"tech_etf_issuer_backfill_withheld={ticker} reason={type(exc).__name__} "
                  f"detail={str(exc)[:90]}")
    return copied,count


def rolling_estimated_flows(rows, count, ticker):
    """Sum each daily share change times that day's NAV over exact US sessions."""
    if len(rows)<count+1:
        return None
    window=rows[-(count+1):]
    if ticker=="SOXX" and window[0]["date"]<"2026-11-05"<=window[-1]["date"]:
        return None
    try:
        import exchange_calendars
        calendar=exchange_calendars.get_calendar("XNYS")
        valid=[x.date().isoformat() for x in calendar.sessions_in_range(
            window[0]["date"],window[-1]["date"])]
    except Exception:
        return None
    if valid != [z["date"] for z in window]:
        return None
    total=0.0
    for previous,today in zip(window,window[1:]):
        a,b=float(previous["shares"]),float(today["shares"])
        nav=float(today["nav"])
        if not all(math.isfinite(x) and x>0 for x in (a,b,nav)):
            return None
        if not 0.60<=b/a<=1.65:
            return None
        total+=(b-a)*nav
    change=(float(window[-1]["shares"])/float(window[0]["shares"])-1)*100
    return {"start":window[0]["date"],"end":window[-1]["date"],
            "sessions":count,"net_usd":total,"share_pct":change}

def calculate(observations, state):
    if not set(FUNDS).issubset(set(observations)):
        raise ValueError("both official technology sector funds required")
    if set(observations).difference(set(FUNDS), set(OPTIONAL_KOREA_FUND)):
        raise ValueError("unexpected fund ticker in tech ETF proxy")
    today = next(iter(observations.values()))["date"]
    current_date = dt.date.fromisoformat(today)
    # Keep verified EWY history when its optional source is temporarily absent.
    new_history = {
        t: list(v) for t, v in state.get("history", {}).items()
        if t == "EWY" and t not in observations
    }
    movements = {}
    for ticker in ("IYW", "SOXX", "EWY"):
        if ticker not in observations:
            continue
        row = observations[ticker]
        history = list(state.get("history", {}).get(ticker, []))
        if history and dt.date.fromisoformat(history[-1]["date"]) > current_date:
            raise ValueError("new observation older than confirmed history")
        old = next((x for x in reversed(history) if x["date"] < today), None)
        delta = None
        period_days = None
        if old:
            period_days = (current_date - dt.date.fromisoformat(old["date"])).days
            if 0 < period_days <= 4 and exchange_sessions(old["date"], today) == [old["date"], today]:
                delta = row["shares"] - old["shares"]
        # SOXX officially announced a forward split effective November 5, 2026.
        # Freeze the comparison across this event until adjusted history exists.
        split_guard = ticker == "SOXX" and (
            "2026-11-03" <= today <= "2026-11-09" or
            (old is not None and old["date"] < "2026-11-05" <= today)
        )
        if split_guard:
            delta = None
        if old and delta is not None and (
            row["shares"] / old["shares"] > 1.65 or row["shares"] / old["shares"] < 0.60
        ):
            delta = None
        value_usd = None if delta is None else delta * row["nav"]
        pct = None if delta is None else (delta / old["shares"] * 100)
        obs = {
            "date": today, "nav": row["nav"], "shares": row["shares"],
            "previous_shares": old["shares"] if old else None,
            "asset_check_pct": row.get("asset_check_pct"),
            "prev_date": old["date"] if old else None,
            "elapsed_calendar_days": period_days,
            "shares_delta": delta, "estimated_creation_value_usd": value_usd,
            "outstanding_shares_change_pct": pct,
            "split_guard": split_guard,
        }
        rows = [x for x in history if x.get("date") != today] + [
            {"date": today, "nav": row["nav"], "shares": row["shares"]}
        ]
        rows = sorted(rows, key=lambda x: x["date"])[-HISTORY_LIMIT:]
        obs.update({
            "five_observations_from": None,
            "five_observations_share_change_pct": None,
            "five_observations_creation_usd": None,
        })
        if len(rows) >= 6:
            anchor = rows[-6]
            anchor_date = dt.date.fromisoformat(anchor["date"])
            gap = (current_date - anchor_date).days
            cross_split = ticker == "SOXX" and anchor["date"] < "2026-11-05" <= today
            if 0 < gap <= 10 and _consecutive_weekday_dates(rows[-6:]) and not cross_split and not split_guard:
                # Five-day money is the sum of five DAILY share changes at
                # their own NAVs. End-day NAV times net shares is only a
                # different proxy and must not be mislabeled as cumulative.
                five = rolling_estimated_flows(rows, 5, ticker)
                if five is not None and -50 <= five["share_pct"] <= 65:
                    obs.update({
                        "five_observations_from": five["start"],
                        "five_observations_share_change_pct": five["share_pct"],
                        "five_observations_creation_usd": five["net_usd"],
                    })
        obs["rolling"]={n:rolling_estimated_flows(rows,n,ticker) for n,_ in WINDOWS}
        obs["history_points"]=len(rows)
        new_history[ticker] = rows
        movements[ticker] = obs

    signals = []
    # Economic meaning: + means estimated creation, - means redemption.
    for ticker, m in movements.items():
        v = m["estimated_creation_value_usd"]
        pct = m["outstanding_shares_change_pct"]
        if v is None or pct is None:
            continue
        if pct >= 1.0 and v >= 100_000_000:
            signals.append(f"{ticker} 발행좌수 당일 +1% 이상")
        if pct <= -1.0 and v <= -100_000_000:
            signals.append(f"{ticker} 발행좌수 당일 -1% 이하")
    for ticker, m in movements.items():
        v5 = m["five_observations_creation_usd"]
        p5 = m["five_observations_share_change_pct"]
        if v5 is None or p5 is None:
            continue
        if p5 >= 2.5 and v5 >= 250_000_000:
            signals.append(f"{ticker} 최근 5회 발행좌수 +2.5% 이상")
        if p5 <= -2.5 and v5 <= -250_000_000:
            signals.append(f"{ticker} 최근 5회 발행좌수 -2.5% 이하")
    # Additional EWY 3-session continuous creations checkpoint (four
    # official shares-outstanding observations). Never label these as
    # Korean foreign-investor trades or licensed retail order imbalance.
    if "EWY" in movements:
        ewy_rows = new_history["EWY"]
        if len(ewy_rows) >= 4 and _consecutive_weekday_dates(ewy_rows[-4:]):
            recent = ewy_rows[-4:]
            increments = [
                recent[i]["shares"] - recent[i-1]["shares"]
                for i in range(1, 4)
            ]
            if all(x > 0 for x in increments):
                ewy_three = rolling_estimated_flows(recent, 3, "EWY")
                if ewy_three is not None and ewy_three["net_usd"] >= 150_000_000:
                    signals.append("EWY 발행좌수 3거래일 연속 증가·누적 1억5천만달러 이상")

    a = movements["IYW"]["estimated_creation_value_usd"]
    b = movements["SOXX"]["estimated_creation_value_usd"]
    if a is not None and b is not None and a >= 100_000_000 and b <= -100_000_000:
        signals.append("기술주 ETF 설정·반도체 ETF 환매 차별화")
    if a is not None and b is not None and b >= 100_000_000 and a <= -100_000_000:
        signals.append("반도체 ETF 설정·기술주 ETF 환매 차별화")
    return {
        "date": today, "movements": movements, "signals": signals,
        "new_history": new_history,
        "alert_key": today + "|" + "|".join(sorted(signals)),
    }


def money_usd(v):
    if v is None:
        return "비교 기준 부족"
    return f"{v/1e6:+,.1f}백만달러"


def money_krw(v, fx):
    if v is None or fx is None:
        return "원화 환산 확인 불가"
    return f"{v*fx/1e8:+,.0f}억원"


def render(result, fx, fx_date):
    lines = [
        "<b>미국 기술주·반도체 ETF 설정·환매 감시</b>",
        f"공식 자료일: <b>{html.escape(result['date'])}</b>",
        "<b>변화:</b> " + (" / ".join(html.escape(x) for x in result["signals"]) if result["signals"] else "조건 미충족"),
    ]
    all_funds = {**FUNDS, **OPTIONAL_KOREA_FUND}
    for ticker in ("IYW", "SOXX", "EWY"):
        if ticker not in result["movements"]:
            continue
        x = result["movements"][ticker]
        if x["estimated_creation_value_usd"] is None:
            v = "비교 보류" + ("(분할 조정 기간)" if x["split_guard"] else "(연속 자료 부족)")
        else:
            n = x["estimated_creation_value_usd"]
            title = "추정 설정" if n > 0 else "추정 환매" if n < 0 else "설정·환매 중립"
            v = (
                f"{title} {money_usd(n)} ({money_krw(n, fx)}) "
                f"/ 발행좌수 {x['outstanding_shares_change_pct']:+.2f}% "
                f"/ 비교 {x['prev_date']}→{x['date']}"
            )
        lines.append(f"• <b>{ticker}</b> ({all_funds[ticker]['label']}): {html.escape(v)}")
        if x["shares_delta"] is not None and x["previous_shares"] is not None:
            lines.append(
                f"  검산: 발행좌수 {x['previous_shares']:,.0f}→{x['shares']:,.0f}주"
                f" (증감 {x['shares_delta']:+,.0f}주) × 당일 기준가격 ${x['nav']:,.2f}"
            )
        if x.get("asset_check_pct") is not None:
            lines.append(f"  발행사 순자산과 발행좌수×기준가격 차이 {x['asset_check_pct']:.3f}%")
        v5 = x["five_observations_creation_usd"]
        if v5 is not None:
            lines.append(
                f"  최근 5개 관측 간격 ({x['five_observations_from']}→{x['date']}): "
                f"{x['five_observations_share_change_pct']:+.2f}% "
                f"· 일별 기준가격 적용 합계 {html.escape(money_usd(v5))} "
                f"({html.escape(money_krw(v5, fx))})"
            )
        elif any(signal.startswith(ticker + " 발행좌수 당일 ") for signal in result["signals"]):
            lines.append(
                "  최근 5거래일 합계: 확인 보류(6개 연속 관측점 부족·휴장·분할 등)"
            )
    for ticker in ("IYW","SOXX","EWY"):
        if ticker not in result["movements"]:
            continue
        x=result["movements"][ticker]
        for sessions,period in WINDOWS:
            stat=x["rolling"].get(sessions)
            if stat is None:
                why=("분할 전후 비교 보류" if ticker=="SOXX"
                     and "2026-11-05"<=result["date"] and
                     x["history_points"]>=sessions+1
                     else "발행사 연속 거래일 자료 부족·누락")
                lines.append(f"  {ticker} {period}({sessions}거래일) 누적: 확인 대기({why})")
                continue
            label=("설정 우위" if stat["net_usd"]>0 else
                   "환매 우위" if stat["net_usd"]<0 else "중립")
            lines.append(
                f"  {ticker} {period}({sessions}거래일): {label} "
                f"{html.escape(money_usd(stat['net_usd']))} "
                f"({html.escape(money_krw(stat['net_usd'],fx))}) / "
                f"발행좌수 {stat['share_pct']:+.2f}% / "
                f"{stat['start']}→{stat['end']}")
        short,long=(x["rolling"].get(21),x["rolling"].get(63))
        if short and long:
            s1=0 if abs(short["net_usd"])<1 else (1 if short["net_usd"]>0 else -1)
            s3=0 if abs(long["net_usd"])<1 else (1 if long["net_usd"]>0 else -1)
            trend=("장·단기 설정 우위 지속" if s1==s3==1 else
                   "장·단기 환매 우위 지속" if s1==s3==-1 else
                   "단기 설정 전환" if s1==1 and s3==-1 else
                   "단기 환매 전환" if s1==-1 and s3==1 else
                   "혼조·방향 추가 확인")
            lines.append(f"  {ticker} 중기 방향: {trend}")
    if "EWY" not in result["movements"]:
        lines.append("• <b>EWY</b>: 공식값·기준일 동기화 확인 불가 → 한국 ETF 설정·환매 판정 보류")
    lines += [
        "해석: ETF 발행좌수 증감×당일 기준가격을 이용한 <b>설정·환매 대용 추정</b>입니다.",
        "주의: JP모건 개인 순매수 불균형과 이 ETF 발행좌수 추정치는 다릅니다. 개인·기관별 순매수나 전체 기술주 펀드 순유입액이 아닙니다.",
        "EWY는 미국 상장 한국 주식 ETF이며, EWY 설정·환매를 한국거래소 외국인 현물 매수·매도로 치환하지 않습니다.",
        "최근 5회 누적은 해당 ETF 공식 발행좌수 6개 연속 평일 관측점만 사용합니다. 휴장·결측이 포함되면 누적 경보를 보류합니다.",
        "1개월·3개월은 각각 21·63개 연속 미국 증시 거래 간격의 일별 발행좌수 증감×각일 기준가격 합계(추정)입니다. 과거치·휴장·결측은 검증 없이 채우지 않습니다.",
        "해당 ETF의 2차시장 거래량과 실제 발행·환매는 다르며, 설정·환매 주체를 개인·기관으로 식별할 수 없습니다.",
        "SOXX는 2026-11-05 시행된 3대 1 주식분할 전후 발행좌수 비교 경보를 보류합니다.",
        f"환율: {fx:,.2f}원/달러 (공식 기준 {html.escape(fx_date)})" if fx else "환율: 확인 불가",
        f'원천: <a href="{FUNDS["IYW"]["url"]}">IYW 공식</a> · '
        f'<a href="{FUNDS["SOXX"]["url"]}">SOXX 공식</a> · '
        f'<a href="{OPTIONAL_KOREA_FUND["EWY"]["url"]}">EWY 공식</a>',
    ]
    out = "\n".join(lines)
    if len(out) >= 3900:
        raise ValueError("Telegram summary length exceeded safe limit")
    return out



def _flow_stats(result, ticker):
    x = result["movements"].get(ticker)
    if x is None:
        return None, [None] * 4
    daily = None if x["estimated_creation_value_usd"] is None else (
        x["estimated_creation_value_usd"], x["outstanding_shares_change_pct"])
    five = None if x["five_observations_creation_usd"] is None else (
        x["five_observations_creation_usd"], x["five_observations_share_change_pct"])
    periods = [daily, five]
    for n, _ in WINDOWS:
        q = x["rolling"].get(n)
        periods.append(None if q is None else (q["net_usd"], q["share_pct"]))
    return x, periods


def _flow_direction(stat):
    if stat is None:
        return "확인 보류"
    return "설정(유입)" if stat[0] > 0 else "환매(유출)" if stat[0] < 0 else "중립"


def render_photo_caption(result, fx, fx_date):
    lines = [f"<b>미국 ETF 자금 흐름 | {html.escape(result['date'])}</b>"]
    for ticker in ("IYW", "SOXX", "EWY"):
        _, periods = _flow_stats(result, ticker)
        d, f = periods[:2]
        def brief(stat):
            return "보류" if stat is None else f"{_flow_direction(stat)} {money_krw(stat[0],fx)}"
        lines.append(f"{ticker}: 오늘 {brief(d)} / 5일 {brief(f)}")
    lines += ["설정=ETF 좌수 증가, 환매=좌수 감소에 따른 금액 추정.",
              "투자자별 순매수 또는 한국거래소 외국인 매매와 다릅니다.",
              f"환율 {fx:,.2f}원/달러 | {html.escape(str(fx_date))}",
              '원천: <a href="'+FUNDS["IYW"]["url"]+'">IYW</a> · '
              '<a href="'+FUNDS["SOXX"]["url"]+'">SOXX</a> · '
              '<a href="'+OPTIONAL_KOREA_FUND["EWY"]["url"]+'">EWY</a>']
    caption = "\n".join(lines)
    if len(caption) > 1000:
        raise ValueError("Photo caption exceeds safe length")
    return caption


def render_image(result, fx, fx_date):
    """Deterministic, Korean-readable PNG from the exact validated alert values."""
    from PIL import Image, ImageDraw, ImageFont
    regular = pathlib.Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    bold = pathlib.Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
    if not regular.is_file() or not bold.is_file():
        raise RuntimeError("Korean report fonts unavailable")
    fonts = {}
    def font(size, strong=False):
        key = (size, strong)
        if key not in fonts:
            fonts[key] = ImageFont.truetype(str(bold if strong else regular), size, index=1)
        return fonts[key]
    im = Image.new("RGB", (1200, 1760), "#F3F6FA")
    draw = ImageDraw.Draw(im)
    ink, muted, navy = "#14263C", "#566579", "#142E4A"
    red, blue = "#B42333", "#2455A6"
    def line(x, y, value, size=32, color=ink, strong=False, width=1100):
        value = str(value)
        while size > 19 and draw.textlength(value, font=font(size,strong)) > width:
            size -= 1
        if draw.textlength(value, font=font(size,strong)) > width:
            raise ValueError("Image text exceeds allocated space")
        draw.text((x,y), value, fill=color, font=font(size,strong), anchor="lt")
    def box(x,y,w,h,fill,outline=None,r=18):
        draw.rounded_rectangle((x,y,x+w,y+h),radius=r,fill=fill,outline=outline,width=2 if outline else 1)
    box(0,0,1199,218,navy,r=0)
    line(42,29,"미국 ETF 자금 흐름",51,"#FFFFFF",True)
    line(44,94,f"공식 자료일 {result['date']}  |  추정 설정·환매",29,"#D8E4F1")
    hit = [f"{k} {'일간' if '당일' in s else '5일' if '최근 5회' in s else '연속'}" for k in ("SOXX","IYW","EWY") for s in result["signals"] if s.startswith(k)]
    summary = " · ".join(dict.fromkeys(hit)) or "설정·환매 방향 차이 감지"
    line(44,146,"경보: "+summary,32,"#FFFFFF",True)
    labels = {"IYW":"미국 기술주", "SOXX":"미국 반도체", "EWY":"한국 주식(미국 상장)"}
    for i,ticker in enumerate(("IYW","SOXX","EWY")):
        y = 238+i*435
        x, periods = _flow_stats(result,ticker)
        box(30,y,1140,416,"#FFFFFF","#DFE5ED")
        line(53,y+18,ticker,38,navy,True)
        line(200,y+24,labels[ticker],31,muted,True)
        for j,(period,stat) in enumerate(zip(("오늘","최근 5거래일","1개월 · 21일","3개월 · 63일"),periods)):
            a = 53+j*279
            color = muted if stat is None or stat[0]==0 else red if stat[0]>0 else blue
            bg = "#F4F6F8" if stat is None or stat[0]==0 else "#FFF1F2" if stat[0]>0 else "#EEF4FF"
            box(a,y+73,263,187,bg,r=14)
            line(a+12,y+86,period,26,muted,True,239)
            line(a+12,y+126,_flow_direction(stat),26,color,True,239)
            if stat is None:
                reason = "분할·자료 확인" if ticker=="SOXX" else "연속 자료 부족"
                line(a+12,y+171,reason,23,muted,False,239)
            else:
                amount,pct = stat
                line(a+12,y+166,money_krw(amount,fx),33,color,True,239)
                line(a+12,y+208,f"{amount/1e6:+,.1f}백만달러",22,muted,False,239)
                line(a+12,y+235,f"좌수 {pct:+.2f}%",22,muted,False,239)
        if x is None:
            line(55,y+283,"공식값 또는 기준일 동기화 미확인 — 추정하지 않음",29,muted)
        elif x["shares_delta"] is not None:
            line(55,y+279,f"좌수 {x['previous_shares']:,.0f} → {x['shares']:,.0f}주  |  기준가 ${x['nav']:,.2f}",27,ink,False,1090)
            asset = "" if x.get("asset_check_pct") is None else f"  |  순자산 검산 차이 {x['asset_check_pct']:.3f}%"
            line(55,y+320,f"일간 {x['prev_date']} → {x['date']}"+asset,24,muted,False,1090)
        else:
            line(55,y+283,"일간 비교 보류 — 연속 자료 또는 분할 확인 필요",28,muted)
        if x is not None:
            ranges = []
            if x.get("five_observations_from"):
                ranges.append(f"5일 {x['five_observations_from'][5:]}~{result['date'][5:]}")
            for n,label in WINDOWS:
                r=x["rolling"].get(n)
                if r:
                    ranges.append(f"{label} {r['start'][5:]}~{r['end'][5:]}")
            if ranges:
                line(55,y+365,"  |  ".join(ranges),25,muted,False,1090)
    box(30,1542,1140,192,"#E8EEF5")
    line(52,1558,"읽는 법: 빨강 = 설정(유입)  /  파랑 = 환매(유출)",29,navy,True)
    line(52,1599,"일별 좌수 증감 × 해당일 기준가격을 합산한 추정치입니다.",25,ink)
    line(52,1633,"개인·기관 순매수 또는 한국거래소 외국인 매매가 아닙니다.",25,ink)
    line(52,1667,"SOXX 11/05 3:1 분할 전후 비교 보류 · 출처 iShares",24,muted)
    line(52,1701,f"환율 {fx:,.2f}원/달러  |  {fx_date}",23,muted)
    buffer = io.BytesIO()
    im.save(buffer,format="PNG",optimize=True)
    png = buffer.getvalue()
    if len(png)>9_500_000:
        raise ValueError("Image too large for Telegram")
    return png


def _photo_request(token, chat_id, photo, caption):
    boundary = "tech_etf_" + uuid.uuid4().hex
    chunks = []
    for name,value in (("chat_id",chat_id),("caption",caption),("parse_mode","HTML")):
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="etf-flow.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+photo+b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto",
        data=b"".join(chunks),headers={"Content-Type":"multipart/form-data; boundary="+boundary},method="POST")


def _send_response(request):
    # Never retry a timeout, malformed acknowledgement or HTTP 5xx: the
    # server might already have delivered the message.
    try:
        with urllib.request.urlopen(request,timeout=25) as response:
            returned=json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            failure=json.load(exc)
        except Exception:
            failure={}
        if 400<=exc.code<500 and failure.get("ok") is False:
            description=str(failure.get("description","")).lower()
            # Only a definitive photo/caption-format rejection permits text fallback.
            if exc.code==400 and any(s in description for s in
                    ("photo","image","caption","file too","media")):
                raise DeliveryRejected("photo_format_rejected") from None
            raise DeliveryRejected(f"Telegram explicitly rejected HTTP {exc.code}") from None
        raise DeliveryUnconfirmed(f"Telegram HTTP {exc.code}; receipt unverified") from None
    except Exception as exc:
        raise DeliveryUnconfirmed(f"Telegram response unverified: {type(exc).__name__}") from None
    if not isinstance(returned,dict):
        raise DeliveryUnconfirmed("Telegram response is not an object")
    return returned


def send_exact(text, photo=None, caption=None):
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or EXPECTED_BOT).strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("U.S. fund-flow bot credentials missing")
    if expected != EXPECTED_BOT:
        raise RuntimeError("unexpected bot for U.S. fund-flow route")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe",timeout=20) as response:
        auth = json.load(response)
    who = (auth.get("result") or {}).get("username")
    if not auth.get("ok") or who != EXPECTED_BOT:
        raise RuntimeError("Telegram bot identity mismatch")
    body = urllib.parse.urlencode({
        "chat_id":chat_id, "text":text, "parse_mode":"HTML", "disable_web_page_preview":"true"
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",data=body,method="POST"
    )
    if photo is not None:
        try:
            returned=_send_response(_photo_request(token,chat_id,photo,caption))
        except DeliveryRejected as exc:
            if str(exc)!="photo_format_rejected":
                raise
            print("tech_etf_photo_rejected_safe_text_fallback=true")
            returned=_send_response(request)
    else:
        returned=_send_response(request)
    result = returned.get("result") or {}
    msg_id = result.get("message_id")
    actual_chat = result.get("chat") or {}
    if not returned.get("ok") or type(msg_id) is not int or msg_id < 1:
        raise DeliveryUnconfirmed("Telegram send acknowledgement missing message_id")
    if type(actual_chat.get("id")) is not int:
        raise DeliveryUnconfirmed("Telegram response missing actual chat.id")
    if chat_id.lstrip("-").isdigit():
        matching_chat = actual_chat["id"] == int(chat_id)
    elif chat_id.startswith("@"):
        matching_chat = str(actual_chat.get("username") or "").casefold() == chat_id[1:].casefold()
    else:
        raise RuntimeError("Unrecognized Telegram chat destination")
    if not matching_chat:
        raise DeliveryUnconfirmed("Telegram acknowledged unexpected chat; do not advance state")
    print("tech_etf_delivery_format="+("photo" if isinstance(result.get("photo"),list) and result["photo"] else "text"))
    return msg_id


def previously_sent_signal_keys(state):
    """Track date+signal rather than only the most recently sent composite alert."""
    recorded = state.get("sent_signal_keys", [])
    if not isinstance(recorded, list) or any(not isinstance(x, str) for x in recorded):
        raise RuntimeError("Invalid ETF alert deduplication state")
    keys = set(recorded)
    prev = state.get("last_alert") or {}
    if prev.get("message_id") and prev.get("alert_key"):
        parts = str(prev["alert_key"]).split("|")
        if len(parts) > 1:
            keys.update(parts[0] + "|" + name for name in parts[1:])
    return keys


def run(validate_only=False, now=None, state_path=STATE, getter=collect):
    state=load_state(state_path)
    try:
        current=getter(now)
        added=0
        if getter is collect and any(len(state.get("history",{}).get(t,[]))<70
                                     for t in current):
            state,added=verified_backfill(state,current)
        outcome=calculate(current,state)
    except OfficialPublicationPending as e:
        return {"status":"publication_pending","reason":str(e)[:220],"telegram_sent":False}
    except (ValueError, RuntimeError, OSError, TimeoutError, ConnectionError) as e:
        return {"status":"source_withheld","reason":f"{type(e).__name__}: {str(e)[:220]}","telegram_sent":False}
    except Exception as e:
        return {"status":"source_withheld","reason":f"{type(e).__name__}: {str(e)[:220]}","telegram_sent":False}
    sent_keys = previously_sent_signal_keys(state)
    pending=state.get("unconfirmed_deliveries",[])
    if not isinstance(pending,list) or any(not isinstance(item,dict) or
            not isinstance(item.get("keys"),list) for item in pending):
        raise RuntimeError("Invalid unconfirmed ETF delivery state")
    pending_keys={k for item in pending for k in item["keys"]}
    blocked=[name for name in outcome["signals"] if outcome["date"]+"|"+name in pending_keys]
    fresh_signals = [name for name in outcome["signals"]
                     if outcome["date"] + "|" + name not in sent_keys | pending_keys]
    if blocked and not fresh_signals and not validate_only:
        return {"status":"delivery_unconfirmed","date":outcome["date"],
                "telegram_sent":False,"reason":"Prior send outcome requires reconciliation; no automatic resend"}
    if outcome["signals"] and not fresh_signals and not validate_only:
        if added:
            state["history"]=outcome["new_history"]
            state["last_update_date"]=outcome["date"]
            save_state(state,state_path)
        return {"status":"duplicate_suppressed","date":outcome["date"],
                "history_backfilled":added,"telegram_sent":False}
    fx,fx_date=None,None
    preview_signals = outcome["signals"] if validate_only else fresh_signals
    if preview_signals:
        try:
            q=ishares.get_usdkrw()
            fx=float(q["rate"])
            fx_date=q["date"]
            if not math.isfinite(fx) or not 400<fx<3000:
                raise ValueError("invalid USDKRW quote")
        except Exception as e:
            return {"status":"fx_withheld","reason":type(e).__name__,"telegram_sent":False}
    new_outcome = {**outcome, "signals":preview_signals,
                   "alert_key":outcome["date"] + "|" + "|".join(sorted(preview_signals))}
    photo,caption=None,None
    if preview_signals:
        body=render(new_outcome,fx,fx_date)
        OUT.mkdir(parents=True,exist_ok=True)
        CANDIDATE.write_text(body+"\n",encoding="utf-8")
        try:
            png=render_image(new_outcome,fx,fx_date)
            short=render_photo_caption(new_outcome,fx,fx_date)
            IMAGE_CANDIDATE.write_bytes(png)
            photo,caption=png,short
        except Exception as exc:
            print(f"tech_etf_image_unavailable={type(exc).__name__}; safe_text_fallback=true")
    if validate_only:
        return {"status":"validated","date":outcome["date"],"signals":outcome["signals"],
                "historical_rows_added":added,
                "movements":outcome["movements"],"telegram_sent":False,
                "image_preview":photo is not None}
    if fresh_signals:
        try:
            message_id=send_exact(body,photo=photo,caption=caption)
        except DeliveryUnconfirmed as exc:
            keys=[outcome["date"]+"|"+name for name in fresh_signals]
            state["unconfirmed_deliveries"]=pending+[{
                "date":outcome["date"],"keys":keys,"reason":str(exc)[:160],
                "recorded_at_kst":dt.datetime.now(KST).isoformat(timespec="seconds")}]
            state["history"]=outcome["new_history"]
            state["last_update_date"]=outcome["date"]
            save_state(state,state_path)
            return {"status":"delivery_unconfirmed","date":outcome["date"],
                    "telegram_sent":False,"reason":"Receipt unverified; held for reconciliation"}
        sent_keys.update(outcome["date"] + "|" + name for name in fresh_signals)
        state["sent_signal_keys"]=sorted(sent_keys)[-300:]
        state["last_alert"]={
            "alert_key":new_outcome["alert_key"],"date":outcome["date"],
            "message_id":message_id,"bot_username":EXPECTED_BOT,
            "chat_id_verified":True,
            "sent_at_kst":dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        OUT.mkdir(parents=True,exist_ok=True)
        RECEIPT.write_text(json.dumps(state["last_alert"],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    state["history"]=outcome["new_history"]
    state["last_update_date"]=outcome["date"]
    save_state(state,state_path)
    return {"status":"sent" if fresh_signals else "baseline_or_no_signal",
            "historical_rows_added":added,
            "date":outcome["date"],"signals":fresh_signals,
            "telegram_sent":bool(fresh_signals),
            "message_id":(state.get("last_alert") or {}).get("message_id") if fresh_signals else None}


def main():
    validate=os.getenv("TECH_ETF_PROXY_VALIDATE_ONLY","0").lower() in ("1","true","yes")
    result=run(validate_only=validate)
    print("us_tech_etf_proxy_status="+json.dumps(result,ensure_ascii=False))
    if result["status"] in ("source_withheld","fx_withheld"):
        raise SystemExit(2)


if __name__=="__main__":
    main()

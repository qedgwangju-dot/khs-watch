#!/usr/bin/env python3
"""Public tech ETF creations/redemptions proxy in the EXISTING U.S. fund-flow route.

This is NOT JPMorgan's licensed retail order-imbalance series. Do not label
ETF share creations as retail purchases, secondary-market trades, or sector-
wide aggregate flows. Never transmit on a one-day initial baseline.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import pathlib
import tempfile
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import treasury_etf_flow_watch as ishares

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "us_tech_etf_proxy_state.json"
OUT = ROOT / "out"
RECEIPT = OUT / "us_tech_etf_proxy_receipt.json"
CANDIDATE = OUT / "us_tech_etf_proxy_candidate.html"
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
EXPECTED_BOT = "khs887900887900008879_bot"
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


def latest_us_close(now):
    n = now.astimezone(ET)
    d = n.date()
    if n.time() < dt.time(18, 0):
        d -= dt.timedelta(days=1)
    while d.weekday() > 4:
        d -= dt.timedelta(days=1)
    return d


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
        fund_rows[ticker] = row
    observed = {v["date"] for v in fund_rows.values()}
    if len(observed) != 1:
        raise ValueError("IYW/SOXX official observation dates not aligned")
    date = dt.date.fromisoformat(next(iter(observed)))
    latest = latest_us_close(now)
    if date > latest or (latest - date).days > 4:
        raise ValueError(f"ETF official data unavailable/stale: {date} vs US last close {latest}")
    return fund_rows


def calculate(observations, state):
    if {x for x in FUNDS} != set(observations):
        raise ValueError("both official technology sector funds required")
    today = next(iter(observations.values()))["date"]
    current_date = dt.date.fromisoformat(today)
    new_history = {}
    movements = {}
    for ticker in FUNDS:
        row = observations[ticker]
        history = list(state.get("history", {}).get(ticker, []))
        if history and dt.date.fromisoformat(history[-1]["date"]) > current_date:
            raise ValueError("new observation older than confirmed history")
        old = next((x for x in reversed(history) if x["date"] < today), None)
        delta = None
        period_days = None
        if old:
            period_days = (current_date - dt.date.fromisoformat(old["date"])).days
            if 0 < period_days <= 4:
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
            "prev_date": old["date"] if old else None,
            "elapsed_calendar_days": period_days,
            "shares_delta": delta, "estimated_creation_value_usd": value_usd,
            "outstanding_shares_change_pct": pct,
            "split_guard": split_guard,
        }
        rows = [x for x in history if x.get("date") != today] + [
            {"date": today, "nav": row["nav"], "shares": row["shares"]}
        ]
        rows = sorted(rows, key=lambda x: x["date"])[-20:]
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
            if 0 < gap <= 10 and not cross_split and not split_guard:
                share_base = float(anchor["shares"])
                if share_base > 0:
                    share_delta_5 = row["shares"] - share_base
                    pct5 = share_delta_5 / share_base * 100
                    if -50 <= pct5 <= 65:
                        obs.update({
                            "five_observations_from": anchor["date"],
                            "five_observations_share_change_pct": pct5,
                            "five_observations_creation_usd": share_delta_5 * row["nav"],
                        })
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
    for ticker in ("IYW", "SOXX"):
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
        lines.append(f"• <b>{ticker}</b> ({FUNDS[ticker]['label']}): {html.escape(v)}")
        v5 = x["five_observations_creation_usd"]
        if v5 is not None:
            lines.append(
                f"  최근 5개 관측 간격 ({x['five_observations_from']}→{x['date']}): "
                f"{x['five_observations_share_change_pct']:+.2f}% "
                f"· {html.escape(money_usd(v5))} ({html.escape(money_krw(v5, fx))})"
            )
    lines += [
        "해석: ETF 발행좌수 증감×당일 기준가격을 이용한 <b>설정·환매 대용 추정</b>입니다.",
        "주의: 개인투자자만의 매매·JP모건 5거래일 개인 순매수 불균형·전체 기술주 펀드 순유입액이 아닙니다.",
        "5회 누적은 최근 6개 동일 ETF의 공식 관측일 간 발행좌수 변화이며, 중간 거래일 자료가 빠지면 산출하지 않습니다.",
        "해당 ETF의 2차시장 거래량과 실제 발행·환매는 다르며, 설정·환매 주체를 개인·기관으로 식별할 수 없습니다.",
        "SOXX는 2026-11-05 예정 주식분할 전후 발행좌수 비교 경보를 보류합니다.",
        f"환율: {fx:,.2f}원/달러 (공식 기준 {html.escape(fx_date)})" if fx else "환율: 확인 불가",
        f'원천: <a href="{FUNDS["IYW"]["url"]}">IYW 공식</a> · '
        f'<a href="{FUNDS["SOXX"]["url"]}">SOXX 공식</a>',
    ]
    out = "\n".join(lines)
    if len(out) >= 3500:
        raise ValueError("Telegram summary length exceeded safe limit")
    return out


def send_exact(text):
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
    with urllib.request.urlopen(request,timeout=25) as response:
        returned=json.load(response)
    msg_id=(returned.get("result") or {}).get("message_id")
    if not returned.get("ok") or not isinstance(msg_id,int) or msg_id<1:
        raise RuntimeError("Telegram send acknowledgement missing message_id")
    return msg_id


def run(validate_only=False, now=None, state_path=STATE, getter=collect):
    state=load_state(state_path)
    try:
        current=getter(now)
        outcome=calculate(current,state)
    except (ValueError, RuntimeError, OSError, TimeoutError, ConnectionError) as e:
        return {"status":"source_withheld","reason":f"{type(e).__name__}: {str(e)[:220]}","telegram_sent":False}
    except Exception as e:
        return {"status":"source_withheld","reason":f"{type(e).__name__}: {str(e)[:220]}","telegram_sent":False}
    fx,fx_date=None,None
    if outcome["signals"]:
        try:
            q=ishares.get_usdkrw()
            fx=float(q["rate"])
            fx_date=q["date"]
            if not math.isfinite(fx) or not 400<fx<3000:
                raise ValueError("invalid USDKRW quote")
        except Exception as e:
            return {"status":"fx_withheld","reason":type(e).__name__,"telegram_sent":False}
    last=state.get("last_alert") or {}
    if outcome["signals"] and last.get("alert_key")==outcome["alert_key"] and last.get("message_id"):
        return {"status":"duplicate_suppressed","date":outcome["date"],"telegram_sent":False}
    if outcome["signals"]:
        body=render(outcome,fx,fx_date)
        OUT.mkdir(parents=True,exist_ok=True)
        CANDIDATE.write_text(body+"\n",encoding="utf-8")
    if validate_only:
        return {"status":"validated","date":outcome["date"],"signals":outcome["signals"],
                "movements":outcome["movements"],"telegram_sent":False}
    if outcome["signals"]:
        message_id=send_exact(body)
        state["last_alert"]={
            "alert_key":outcome["alert_key"],"date":outcome["date"],
            "message_id":message_id,"bot_username":EXPECTED_BOT,
            "sent_at_kst":dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        OUT.mkdir(parents=True,exist_ok=True)
        RECEIPT.write_text(json.dumps(state["last_alert"],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    state["history"]=outcome["new_history"]
    state["last_update_date"]=outcome["date"]
    save_state(state,state_path)
    return {"status":"sent" if outcome["signals"] else "baseline_or_no_signal",
            "date":outcome["date"],"signals":outcome["signals"],
            "telegram_sent":bool(outcome["signals"]),
            "message_id":(state.get("last_alert") or {}).get("message_id") if outcome["signals"] else None}


def main():
    validate=os.getenv("TECH_ETF_PROXY_VALIDATE_ONLY","0").lower() in ("1","true","yes")
    result=run(validate_only=validate)
    print("us_tech_etf_proxy_status="+json.dumps(result,ensure_ascii=False))
    if result["status"] in ("source_withheld","fx_withheld"):
        raise SystemExit(2)


if __name__=="__main__":
    main()

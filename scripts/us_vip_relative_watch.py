#!/usr/bin/env python3
"""Public ETF proxy: 75 completed U.S. sessions of GVIP vs SPY relative performance.

GVIP price is NOT Goldman's licensed GSTHHVIP basket series, nor actual
hedge-fund prime-book trading. Only independently verified market-price closes
from Nasdaq historical API are used. Separate state from every existing alert.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
from pathlib import Path
import tempfile
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "us_vip_relative_state.json"
OUT = ROOT / "out"
CANDIDATE = OUT / "us_vip_relative_candidate.html"
RECEIPT = OUT / "us_vip_relative_receipt.json"
ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")
BOT = "khs887900887900008879_bot"
BASE = "https://api.nasdaq.com/api/quote/"
SOURCE = "https://indexes.nasdaq.com/Index/History/NDX"


class SourceError(RuntimeError):
    pass


class OfficialPublicationPending(SourceError):
    """The two Nasdaq ETF closing series have not synchronized after U.S. close."""
    pass


def recent_publication_gap(expected: str, g_last: str, s_last: str) -> bool:
    """Only an at-most-one-business-session lag is an expected release delay."""
    day = dt.date.fromisoformat(expected)
    prior = day - dt.timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= dt.timedelta(days=1)
    dates = {g_last, s_last}
    return (all(value in (expected, prior.isoformat()) for value in (g_last, s_last))
            and (g_last != expected or s_last != expected))


def last_completed_us_weekday(now: dt.datetime) -> dt.date:
    local = now.astimezone(ET)
    d = local.date()
    if local.time() < dt.time(18, 0):
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def parse_nasdaq(ticker: str, data: dict) -> dict:
    if ticker not in ("GVIP", "SPY"):
        raise ValueError("unknown ETF")
    if not isinstance(data, dict) or (data.get("status") or {}).get("rCode") not in (200, "200"):
        raise SourceError(ticker + ": Nasdaq response not successful")
    block = data.get("data") or {}
    if str(block.get("symbol") or "").upper() != ticker:
        raise SourceError(ticker + ": Nasdaq returned wrong security")
    rows = ((block.get("tradesTable") or {}).get("rows") or [])
    if not rows:
        raise SourceError(ticker + ": empty historical prices")
    parsed = {}
    for row in rows:
        try:
            date = dt.datetime.strptime(str(row["date"]).strip(), "%m/%d/%Y").date().isoformat()
            close = float(str(row["close"]).replace(",", "").replace("$", "").strip())
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(
                f"{ticker}: malformed Nasdaq quote row date={str(row.get('date'))[:16]} "
                f"close={str(row.get('close'))[:24]}"
            ) from exc
        # Historical trading volume is sometimes a non-numeric placeholder;
        # it is not a price and is never imputed as an actual trade count.
        try:
            volume_raw = str(row.get("volume") or "0").replace(",", "").strip()
            volume = int(float(volume_raw)) if volume_raw not in ("--", "", "N/A") else 0
        except (TypeError, ValueError):
            volume = 0
        if not math.isfinite(close) or close <= 0:
            raise SourceError(ticker + ": invalid close")
        if date in parsed and abs(parsed[date]["close"] - close) > 0.001:
            raise SourceError(ticker + ": conflicting same-session prices")
        parsed[date] = {"close": close, "volume": volume}
    return parsed


def collect(now: dt.datetime | None = None, client=requests):
    now = now or dt.datetime.now(dt.timezone.utc)
    expected = last_completed_us_weekday(now).isoformat()
    from_date = (dt.date.fromisoformat(expected) - dt.timedelta(days=195)).isoformat()
    rows = {}
    for ticker in ("GVIP", "SPY"):
        url = BASE + ticker + "/historical"
        try:
            response = client.get(
                url,
                params={"assetclass": "etf", "limit": 200,
                        "fromdate": from_date, "todate": expected},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                         "Origin": "https://www.nasdaq.com"},
                timeout=(6, 16),
            )
            response.raise_for_status()
            rows[ticker] = parse_nasdaq(ticker, response.json())
        except (requests.RequestException, ValueError) as exc:
            raise SourceError(ticker + ": official source unavailable: " + type(exc).__name__) from exc
    g_last = max(rows["GVIP"]) if rows["GVIP"] else ""
    s_last = max(rows["SPY"]) if rows["SPY"] else ""
    if recent_publication_gap(expected, g_last, s_last):
        raise OfficialPublicationPending(
            f"Nasdaq GVIP/SPY published {g_last}/{s_last}; awaiting completed US session {expected}")
    return evaluate(rows["GVIP"], rows["SPY"], expected)


def evaluate(gvip: dict, spy: dict, expected: str):
    dates_g = sorted(gvip)
    dates_s = sorted(spy)
    if not dates_g or not dates_s or dates_g[-1] != expected or dates_s[-1] != expected:
        raise SourceError("GVIP/SPY latest completed U.S. trading dates are missing or mismatched")
    if len(dates_g) < 76 or len(dates_s) < 76:
        raise SourceError("GVIP/SPY require 76 full paired daily closing observations")
    # No silent forward-fill when either ETF has a missing session.
    if dates_g[-76:] != dates_s[-76:]:
        raise SourceError("GVIP/SPY 76-session history has missing or unmatched dates")
    dates = dates_g[-76:]
    start, end = dates[0], dates[-1]
    for ticker, history in (("GVIP", gvip), ("SPY", spy)):
        for i in range(1, len(dates)):
            p0, p1 = history[dates[i-1]]["close"], history[dates[i]]["close"]
            if not 0.75 <= p1 / p0 <= 1.25:
                raise SourceError(ticker + ": suspicious unadjusted jump/split within relative window")
        if history[end]["volume"] <= 0 or history[start]["volume"] <= 0:
            raise SourceError(ticker + ": price without confirmed official trading volume")
    g_start, g_end = gvip[start]["close"], gvip[end]["close"]
    s_start, s_end = spy[start]["close"], spy[end]["close"]
    g_return = (g_end / g_start - 1.0) * 100.0
    s_return = (s_end / s_start - 1.0) * 100.0
    relative_pp = g_return - s_return
    ratio_return = ((g_end / s_end) / (g_start / s_start) - 1.0) * 100.0
    if relative_pp <= -20:
        band = "상대성과 -20%p 이하"
    elif relative_pp <= -15:
        band = "상대성과 -15%p 이하"
    elif relative_pp <= -10:
        band = "상대성과 -10%p 이하"
    elif relative_pp >= -5:
        band = "상대성과 -5%p 초과"
    else:
        band = "추가 관찰"
    return {
        "end": end, "start": start, "sessions": 75,
        "gvip_start": g_start, "gvip_end": g_end,
        "spy_start": s_start, "spy_end": s_end,
        "gvip_return": round(g_return, 4), "spy_return": round(s_return, 4),
        "relative_pp": round(relative_pp, 4),
        "ratio_return_pct": round(ratio_return, 4),
        "gvip_end_volume": gvip[end]["volume"],
        "band": band,
    }


def load_state(path=STATE):
    if not path.exists():
        return {"last_observation": None, "last_alert": None}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("GVIP state invalid; refusing to erase existing alert state") from exc
    if not isinstance(value, dict) or "last_alert" not in value or "last_observation" not in value:
        raise RuntimeError("GVIP state invalid; refusing to erase existing alert state")
    return value


def save_state(state, path=STATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
        dir=path.parent, prefix=".gvip-", suffix=".tmp", delete=False) as file:
        file.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        temp = file.name
    os.replace(temp, path)


def decide(snapshot, state):
    alert = state.get("last_alert") or {}
    band = snapshot["band"]
    old_band = alert.get("band")
    if alert.get("end") == snapshot["end"]:
        return None
    if band in ("상대성과 -10%p 이하", "상대성과 -15%p 이하", "상대성과 -20%p 이하"):
        bands = {"상대성과 -10%p 이하": 1, "상대성과 -15%p 이하": 2,
                 "상대성과 -20%p 이하": 3}
        if bands[band] > bands.get(old_band, 0):
            return (
                "인기 보유종목 ETF 상대 약세 확인"
                if not old_band else "인기 보유종목 ETF 상대 약세 확대"
            )
    if band == "상대성과 -5%p 초과" and old_band in (
        "상대성과 -10%p 이하", "상대성과 -15%p 이하", "상대성과 -20%p 이하"):
        return "인기 보유종목 ETF 상대 약세 완화"
    return None


def render(snapshot, verdict):
    q = snapshot
    urls = {
        t: BASE + t + "/historical?assetclass=etf"
        for t in ("GVIP", "SPY")
    }
    def link(url, text):
        return f'<a href="{html.escape(url,quote=True)}">{text}</a>'
    lines = [
        "<b>헤지펀드 인기 보유종목 ETF 상대성과 감시</b>",
        f"<b>판정: {html.escape(verdict)}</b>",
        f"미국 정규장 기준: {q['start']} → {q['end']} (75거래일)",
        f"• GVIP 75거래일 가격수익률: {q['gvip_return']:+.2f}%",
        f"• SPY 75거래일 가격수익률: {q['spy_return']:+.2f}%",
        f"<b>75거래일 가격수익률 차이: {q['relative_pp']:+.2f}%p</b>",
        f"상대가격비율 변화(별도 계산): {q['ratio_return_pct']:+.2f}%",
        "해석: GVIP의 인기 롱 보유종목 가격성과가 미국 대형주 시장과 얼마나 벌어졌는지 보는 공개시장 대용 지표.",
        "주의: Goldman의 고객 전용 GSTHHVIP 지수·프라임북 실시간 포지션과 동일하지 않음. ",
        "13F는 분기 공시 후 반영되며, GVIP 가격은 배당을 제외하고 유동성에 영향받을 수 있음.",
        "이 결과만으로 헤지펀드 강제청산·개인 매수·실제 숏커버링을 확정하지 않음.",
        "출처: " + " · ".join(link(urls[t], t + " Nasdaq 종가") for t in ("GVIP", "SPY")),
        "지수 추종 근거: " + link(
            "https://www.sec.gov/Archives/edgar/data/1479026/000119312525334820/d43716d497k.htm",
            "Goldman GVIP 공식 투자설명서"),
    ]
    body = "\n".join(lines)
    if len(body) > 3900:
        raise RuntimeError("GVIP Telegram body too long")
    return body


def send_telegram(body):
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or BOT).strip().lstrip("@")
    if not token or not chat_id or expected != BOT:
        raise RuntimeError("GVIP alert existing bot credentials/identity not set")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=20) as response:
        auth = json.load(response)
    if not auth.get("ok") or (auth.get("result") or {}).get("username") != BOT:
        raise RuntimeError("GVIP Telegram bot does not match existing US fund-flow route")
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": body, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", method="POST", data=data
    ), timeout=25) as response:
        result = json.load(response)
    reply = result.get("result") or {}
    message_id = reply.get("message_id")
    if not result.get("ok") or not isinstance(message_id, int) or message_id <= 0:
        raise RuntimeError("GVIP Telegram API acknowledgement missing")
    return message_id


def run(validate_only=False, now=None, state_path=STATE, source=collect):
    state = load_state(state_path)
    try:
        snapshot = source(now)
    except OfficialPublicationPending as exc:
        return {"status": "publication_pending", "reason": str(exc)[:150],
                "telegram_sent": False}
    except (SourceError, requests.RequestException, ValueError, TimeoutError) as exc:
        return {"status": "source_withheld", "reason": f"{type(exc).__name__}: {str(exc)[:150]}",
                "telegram_sent": False}
    current = state.get("last_observation") or {}
    if current.get("end") and snapshot["end"] < current["end"]:
        return {"status": "source_withheld", "reason": "official data went backwards",
                "telegram_sent": False}
    verdict = decide(snapshot, state)
    if validate_only:
        return {"status": "validated", "telegram_sent": False, "verdict": verdict, "data": snapshot}
    if verdict:
        OUT.mkdir(parents=True, exist_ok=True)
        body = render(snapshot, verdict)
        CANDIDATE.write_text(body + "\n", encoding="utf-8")
        message_id = send_telegram(body)
        receipt = {
            "end": snapshot["end"], "band": snapshot["band"],
            "message_id": message_id, "bot_username": BOT,
            "relative_pp": snapshot["relative_pp"],
            "sent_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False) + "\n", encoding="utf-8")
        state["last_alert"] = receipt
    state["last_observation"] = snapshot
    save_state(state, state_path)
    return {"status": "sent" if verdict else "baseline_or_no_change",
            "telegram_sent": bool(verdict), "verdict": verdict,
            "end": snapshot["end"], "band": snapshot["band"],
            "message_id": (state.get("last_alert") or {}).get("message_id") if verdict else None}


def main():
    validate = os.getenv("GVIP_RELATIVE_VALIDATE_ONLY", "").lower() in ("1", "true", "yes")
    result = run(validate_only=validate)
    print("gvip_relative_status=" + json.dumps(result, ensure_ascii=False))
    if result["status"] == "source_withheld":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

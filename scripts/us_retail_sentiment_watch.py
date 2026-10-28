#!/usr/bin/env python3
"""Official monthly US retail stock-allocation and expectation monitor.

Runs in the existing US Fund Flow Actions workflow and Telegram bot.
First valid observation per source is a silent baseline, not a backfilled alert.
No proprietary Conference Board stock-optimism percentage is inferred.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

AAII_URL = "https://www.aaii.com/assetallocationsurvey"
CB_URL = "https://www.conference-board.org/topics/consumer-confidence/"
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data/us_retail_sentiment_state.json"
OUT = ROOT / "out"
STATUS = OUT / "us_retail_sentiment_status.md"
MESSAGE = OUT / "us_retail_sentiment_alert.html"
RECEIPT = OUT / "us_retail_sentiment_receipt.json"
EXPECTED_BOT = "khs887900887900008879_bot"
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
MONTH_NAMES = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}


def text_of(document: str) -> str:
    soup = BeautifulSoup(document, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def month_number(name: str) -> int:
    number = MONTH_NAMES.get(name.lower())
    if number is None:
        raise ValueError("Unknown source survey month")
    return number


def canonical_month(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def parse_aaii(document: str, now: dt.date) -> dict:
    text = text_of(document)
    anchor = re.search(r"Asset Allocation Results for\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if not anchor:
        raise ValueError("AAII latest official asset allocation month missing")
    month = month_number(anchor.group(1))
    year = int(anchor.group(2))
    observed_month = canonical_month(year, month)
    observed_day = dt.date(year, month, calendar.monthrange(year, month)[1])
    if observed_day > now or (now - observed_day).days > 70:
        raise ValueError("AAII survey month future or stale")
    section = text[anchor.end():anchor.end() + 950]

    def metric(label: str) -> float:
        expression = re.search(label + r"\s+(\d{1,2}(?:\.\d+)?)\s*%", section, re.I)
        if not expression:
            raise ValueError("AAII official source missing category: " + label)
        value = float(expression.group(1))
        if not 0 <= value <= 100:
            raise ValueError("AAII percentage invalid")
        return value

    stocks = metric(r"Stocks Total")
    bonds = metric(r"Bonds Total")
    cash = metric(r"Cash(?:\s+Image)?")
    if abs(stocks + bonds + cash - 100) > 0.3:
        raise ValueError("AAII asset allocation shares do not sum to 100%")
    return {
        "source": "AAII", "period": observed_month, "published": None,
        "stock_pct": stocks, "bond_pct": bonds, "cash_pct": cash,
        "url": AAII_URL, "basis": "actual surveyed portfolio weights",
    }


def parse_conference_board(document: str, now: dt.date) -> dict:
    text = text_of(document)
    stamp = re.search(r"Updated:\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
                      r"([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})", text, re.I)
    if not stamp:
        raise ValueError("Conference Board official release date not found")
    published = dt.date(int(stamp.group(3)), month_number(stamp.group(1)),
                        int(stamp.group(2)))
    if published > now or (now - published).days > 65:
        raise ValueError("Conference Board release future or stale")
    block = text[stamp.end():stamp.end() + 7500]
    index = re.search(r"Consumer Confidence Index.{0,220}?\bto\s+(\d{2,3}(?:\.\d+)?)"
                      r"\s*\(1985=100\)\s+in\s+([A-Za-z]+),?\s+"
                      r"(up|down)\s+from\s+(\d{2,3}(?:\.\d+)?)", block, re.I)
    if not index:
        raise ValueError("Conference Board official current and prior index absent")
    level = float(index.group(1))
    prior = float(index.group(4))
    reference_month = canonical_month(published.year, month_number(index.group(2)))
    if reference_month != canonical_month(published.year, published.month):
        raise ValueError("Conference Board headline and release month disagree")
    if not (30 <= level <= 200 and 30 <= prior <= 200):
        raise ValueError("Conference Board index outside valid bounds")
    change = round(level - prior, 2)
    if (index.group(3).lower() == "up" and change < 0) or (
            index.group(3).lower() == "down" and change > 0):
        raise ValueError("Conference Board direction inconsistent with index values")
    optimism = "미확인"
    stock_sentence = re.search(
        r"(?:Overall,\s+)?more consumers in\s+[A-Za-z]+\s+expected stock prices to "
        r"(increase|decrease)\s+rather than\s+(increase|decrease)\s+in the next 12 months",
        block, re.I)
    if stock_sentence:
        first, second = stock_sentence.group(1).lower(), stock_sentence.group(2).lower()
        if first == second:
            raise ValueError("Conference Board stock-outlook sentence malformed")
        optimism = "상승 기대 우세" if first == "increase" else "하락 기대 우세"
    return {
        "source": "Conference Board", "period": reference_month,
        "published": published.isoformat(), "cci": level,
        "cci_previous_revised": prior, "cci_delta": change,
        "stock_outlook_12m": optimism,
        "stock_outlook_12m_percent": None,  # Public prose does not establish this number.
        "url": CB_URL, "basis": "survey of consumers; not AAII investor allocation",
    }


def get_official(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (KHS retail survey monitor; public sources)",
                      "Accept": "text/html,application/xhtml+xml", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError("Official survey source returned non-200")
        return response.read().decode("utf-8", "replace")


def load_state(path=STATE) -> dict:
    if not path.exists():
        return {"version": 1, "sources": {}, "sent_keys": [], "last_delivery": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("sources"), dict)
            or not isinstance(data.get("sent_keys"), list)
            or any(not isinstance(x, str) for x in data["sent_keys"])):
        raise RuntimeError("Retail sentiment saved state malformed; cannot reset")
    return data


def fingerprint(observation: dict) -> str:
    core = {k: v for k, v in observation.items() if k not in {"url", "basis", "published"}}
    raw = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def classify_changes(old: dict, current: dict) -> tuple[dict, list[dict]]:
    updated = json.loads(json.dumps(old))
    updated.setdefault("sources", {})
    updated.setdefault("sent_keys", [])
    delivered = set(updated["sent_keys"])
    events = []
    for name, observation in current.items():
        prior = updated["sources"].get(name)
        if prior and observation["period"] < prior["period"]:
            continue  # Source cache rollback must not overwrite newer confirmed state.
        if prior is None:
            updated["sources"][name] = observation  # Silent source-by-source baseline.
            continue
        key = f"{name}:{observation['period']}:{fingerprint(observation)}"
        if fingerprint(prior) != fingerprint(observation) and key not in delivered:
            events.append({"key": key, "source": name, "previous": prior, "current": observation})
            updated["sources"][name] = observation
    return updated, events


def render(events: list[dict], observed: dict) -> str:
    lines = ["<b>미국 개인투자자 주식 편입·상승 기대 공식 감시</b>",
             "<b>새로 확인된 월간 변화</b>"]
    for event in events:
        cur, prior = event["current"], event["previous"]
        if event["source"] == "AAII":
            delta = cur["stock_pct"] - prior["stock_pct"]
            cash_delta = cur["cash_pct"] - prior["cash_pct"]
            lines.append(
                f"• AAII 주식·주식형 펀드 {cur['stock_pct']:.2f}% "
                f"(직전 {prior['stock_pct']:.2f}% → {delta:+.2f}%p), "
                f"현금 {cur['cash_pct']:.2f}% ({cash_delta:+.2f}%p) "
                f"/ 기준 {cur['period']}")
        else:
            lines.append(
                f"• Conference Board 소비자신뢰 {cur['cci']:.1f} "
                f"(수정된 직전 {cur['cci_previous_revised']:.1f}, "
                f"{cur['cci_delta']:+.1f}p) / 기준 {cur['period']} "
                f"/ 향후 12개월 주가 기대: {html.escape(cur['stock_outlook_12m'])}")
    aaii = observed.get("AAII") or {}
    cb = observed.get("Conference Board") or {}
    if aaii and cb:
        stretched = aaii["stock_pct"] >= 70 and aaii["cash_pct"] <= 15
        lines.append(
            f"• 결합 점검: AAII 주식 비중 {aaii['stock_pct']:.2f}%·현금 {aaii['cash_pct']:.2f}% "
            f"→ {'고편입 경계(자체 기준)' if stretched else '고편입 복합조건 미충족'}; "
            f"Conference Board 주가 기대 {html.escape(cb['stock_outlook_12m'])}")
    lines += [
        "• AAII는 회원의 월간 실제 투자 비중, Conference Board는 소비자들의 12개월 주가 기대입니다. "
        "서로 다른 표본이며 ETF 순유입액·헤지펀드 매매액과 합산하지 않습니다.",
        "• '사상 최고' 여부와 Conference Board 주가 상승 기대자의 정확한 백분율은 "
        "전체 공식 시계열 또는 공개 원표가 없어 단정하지 않습니다.",
        "• 향후 검증: AAII 현금 비중, 공개된 AAII 6개월 상승·하락 전망, "
        "Goldman Prime 공개 보도와 지수·옵션의 동일 기간 확인. 지표만으로 매도 신호 판정 금지.",
        f'• 원천: <a href="{AAII_URL}">AAII 공식 월간 자산배분</a> · '
        f'<a href="{CB_URL}">Conference Board 공식 소비자심리</a>',
    ]
    out = "\n".join(lines)
    if len(out) > 3600:
        raise ValueError("Retail sentiment Telegram HTML message exceeds safe length")
    return out


def send_verified(message: str) -> tuple[str, int]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or EXPECTED_BOT).strip().lstrip("@")
    if not token or not chat_id or expected != EXPECTED_BOT:
        raise RuntimeError("Existing US market Telegram route missing or changed")
    def call(method: str, payload: dict | None = None) -> dict:
        data = (urllib.parse.urlencode(payload).encode() if payload else None)
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/{method}",
            data=data, method="POST" if data is not None else "GET")
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    ident = call("getMe")
    username = str((ident.get("result") or {}).get("username") or "")
    if ident.get("ok") is not True or username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError("Retail sentiment Telegram bot identifier mismatch")
    result = call("sendMessage", {
        "chat_id": chat_id, "text": message, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })
    if result.get("ok") is not True:
        raise RuntimeError("Retail sentiment Telegram API did not acknowledge send")
    sent = result.get("result") or {}
    mid = sent.get("message_id")
    rec = sent.get("chat") or {}
    if type(mid) is not int or mid <= 0 or type(rec.get("id")) is not int:
        raise RuntimeError("Telegram missing valid message_id or returned chat.id")
    if chat_id.lstrip("-").isdigit():
        valid = rec["id"] == int(chat_id)
    elif chat_id.startswith("@"):
        valid = str(rec.get("username") or "").lower() == chat_id[1:].lower()
    else:
        raise RuntimeError("Telegram destination unsupported")
    if not valid:
        raise RuntimeError("Telegram acknowledged unexpected chat; state not updated")
    return username, mid


def write_state(state: dict, path=STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(*, validate_only=False, getter=get_official, state_path=STATE, now=None,
        sender=send_verified) -> dict:
    now = now or dt.datetime.now(NY).date()
    if type(now) is not dt.date:
        raise ValueError("Expected US market local calendar date")
    old = load_state(state_path)
    observations, errors = {}, []
    for name, source_url, parser in (
        ("AAII", AAII_URL, parse_aaii),
        ("Conference Board", CB_URL, parse_conference_board),
    ):
        try:
            observations[name] = parser(getter(source_url), now)
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:130]}")
    updated, events = classify_changes(old, observations)
    changed = updated != old
    result = {"status": "validated" if validate_only else "unchanged",
              "observations": {k: v["period"] for k, v in observations.items()},
              "errors": errors, "events": [x["key"] for x in events],
              "telegram_sent": False}
    if validate_only:
        result["status"] = "validated" if len(observations) == 2 else "source_withheld"
        return result
    if not observations:
        result["status"] = "source_withheld"
        return result
    if events:
        message = render(events, updated["sources"])
        OUT.mkdir(parents=True, exist_ok=True)
        MESSAGE.write_text(message + "\n", encoding="utf-8")
        username, message_id = sender(message)
        updated["sent_keys"] = list(dict.fromkeys(
            updated["sent_keys"] + [event["key"] for event in events]))[-300:]
        updated["last_delivery"] = {
            "message_id": message_id, "bot_username": username,
            "chat_id_verified": True, "events": [e["key"] for e in events],
            "sent_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        result.update(status="sent", telegram_sent=True, message_id=message_id)
    elif changed:
        result["status"] = "baseline_saved"  # No historical replay.
    if changed or events:
        updated["updated_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
        write_state(updated, state_path)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (MESSAGE, RECEIPT):
        path.unlink(missing_ok=True)
    dry = os.getenv("RETAIL_SENTIMENT_VALIDATE_ONLY", "0") == "1"
    result = run(validate_only=dry)
    STATUS.write_text(
        "미국 개인투자자 자산배분·주가 기대 공식 감시\n"
        + json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    if result.get("status") == "sent":
        RECEIPT.write_text(
            json.dumps({"message_id": result["message_id"],
                        "chat_id_verified": True,
                        "event_keys": result["events"]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    print("us_retail_sentiment_status=" + json.dumps(result, ensure_ascii=False))
    if result["status"] == "source_withheld":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

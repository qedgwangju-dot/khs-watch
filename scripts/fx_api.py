"""Validated daily conversion rates. Never use these for intraday signals."""
from __future__ import annotations
import datetime as dt
import json
import math
import urllib.request
from dataclasses import dataclass

UTC = dt.timezone.utc
KST = dt.timezone(dt.timedelta(hours=9))
_CACHE = {}

@dataclass(frozen=True)
class Quote:
    rate: float
    date: str
    source: str
    fetched_at: str
    check: str

    @property
    def basis(self):
        return f"{self.date} 일일 기준 · {self.source} · 조회 {self.fetched_at} · {self.check}"


def _json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "khs-watch-fx/2", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.load(response)


def _validate(rate, date, now):
    if isinstance(rate, bool):
        raise ValueError("환율에 불리언 사용 금지")
    rate = float(rate)
    day = dt.date.fromisoformat(date)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("환율은 양수 유한값이어야 함")
    age = (now.date() - day).days
    if age < 0 or age > 7:
        raise ValueError("환율 기준일이 미래이거나 7일 초과 지연")
    return rate, day.isoformat()


def historical_krw(currency, target, *, now=None):
    """Use an actual observation on/before target; never today's rate for history."""
    now = now or dt.datetime.now(UTC)
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha() or currency != currency.upper():
        raise ValueError("ISO 통화코드 필요")
    if target > now.astimezone(KST).date():
        raise ValueError("미래 기준일 환율 조회 금지")
    start = target - dt.timedelta(days=7)
    url = (f"https://api.frankfurter.dev/v2/rates?base={currency}&quotes=KRW&providers=ECB"
           f"&from={start.isoformat()}&to={target.isoformat()}")
    rows = _json(url)
    valid = []
    for row in rows:
        if row.get("base") != currency or row.get("quote") != "KRW":
            continue
        try:
            rate, day = _validate(row["rate"], row["date"], dt.datetime.combine(target, dt.time(), UTC))
            valid.append((day, rate))
        except (ValueError, TypeError, KeyError):
            continue
    if not valid:
        raise RuntimeError("해당 기준일 이전 환율 API 관측값 없음—환산 보류")
    day, rate = max(valid)
    return Quote(rate, day, "ECB/Frankfurter", now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"), "단일 공식 API · 독립 교차검증 미완료")


def daily_krw(currency="USD", *, now=None):
    now = now or dt.datetime.now(UTC)
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha() or currency != currency.upper():
        raise ValueError("ISO 통화코드 필요")
    cached = _CACHE.get(currency)
    if cached and 0 <= (now - cached[0]).total_seconds() < 300:
        return cached[1]
    candidates, errors = [], []
    try:
        data = _json(f"https://api.frankfurter.dev/v2/rates?base={currency}&quotes=KRW&providers=ECB")
        row = next(x for x in data if x.get("base") == currency and x.get("quote") == "KRW")
        rate, date = _validate(row["rate"], row["date"], now)
        candidates.append((rate, date, "ECB/Frankfurter"))
    except Exception as exc:
        errors.append(f"ECB API {type(exc).__name__}")
    try:
        data = _json(f"https://open.er-api.com/v6/latest/{currency}")
        if data.get("result") != "success" or data.get("base_code") != currency:
            raise ValueError("API 상태·통화 불일치")
        observed = dt.datetime.fromtimestamp(int(data["time_last_update_unix"]), UTC)
        if observed > now:
            raise ValueError("미래 환율 시각")
        rate, date = _validate(data["rates"]["KRW"], observed.date().isoformat(), now)
        candidates.append((rate, date, "ExchangeRate-API https://www.exchangerate-api.com"))
    except Exception as exc:
        errors.append(f"ExchangeRate API {type(exc).__name__}")
    if not candidates:
        raise RuntimeError("환율 API 확인 불가—고정값 대체 금지: " + "; ".join(errors))
    rate, date, source = candidates[0]
    check = "단일 API 확인 · 독립 교차검증 미완료"
    if len(candidates) > 1:
        other, other_date, _ = candidates[1]
        gap = abs(other / rate - 1) * 100
        check = f"보조 API {other_date} · 차이 {gap:.2f}% · 일중 기준시각 차이 가능"
        if date == other_date and gap > 1:
            raise RuntimeError("동일 날짜 API 환율 1% 초과 불일치—환산 보류")
        if date != other_date and gap > 3:
            raise RuntimeError("서로 다른 날짜 API 환율 3% 초과 괴리—환산 보류")
    quote = Quote(rate, date, source, now.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"), check)
    _CACHE[currency] = (now, quote)
    return quote

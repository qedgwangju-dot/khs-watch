from __future__ import annotations

import pathlib
import re

from fx_api import daily_krw

CURRENCY_WORDS = {
    "달러": "USD",
    "유로": "EUR",
    "엔": "JPY",
    "링깃": "MYR",
    "위안": "CNY",
    "홍콩달러": "HKD",
    "파운드": "GBP",
    "싱가포르달러": "SGD",
    "대만달러": "TWD",
    "호주달러": "AUD",
    "캐나다달러": "CAD",
    "스위스프랑": "CHF",
}
SYMBOL_CURRENCIES = {
    "US$": "USD",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "HK$": "HKD",
    "S$": "SGD",
    "NT$": "TWD",
    "A$": "AUD",
    "C$": "CAD",
}
ISO_CURRENCIES = {
    "USD": "USD",
    "EUR": "EUR",
    "JPY": "JPY",
    "MYR": "MYR",
    "CNY": "CNY",
    "HKD": "HKD",
    "GBP": "GBP",
    "SGD": "SGD",
    "TWD": "TWD",
    "AUD": "AUD",
    "CAD": "CAD",
    "CHF": "CHF",
}
SCALE = {
    "조": 1_000_000_000_000,
    "억": 100_000_000,
    "십억": 1_000_000_000,
    "백만": 1_000_000,
    "천만": 10_000_000,
}
PER_UNIT_PATTERN = r"(?:MWh|GWh|kWh|GPU|CPU|module|wafer|month|year|TiB|TB|GB|Gb|kW|MW|GW|Wh|kg|chip|서버|랙|주|개|대|g|t|W)"
_RATE_CACHE: dict[str, tuple[float | None, str]] = {}


def _rate(currency: str) -> tuple[float | None, str]:
    if currency in _RATE_CACHE:
        return _RATE_CACHE[currency]
    try:
        q = daily_krw(currency)
        result = (q.rate, q.basis)
    except Exception:
        result = (None, "환율 확인 불가")
    _RATE_CACHE[currency] = result
    return result


def _krw_text(value: float, currency: str, per_unit: str = "") -> str:
    rate, basis = _rate(currency)
    if rate is None:
        raise RuntimeError(f"{currency} 원화 환율 확인 실패—외화 금액 알림 발송 보류")
    won = value * rate
    if per_unit:
        return f"약 {won:,.0f}원{per_unit}"
    eok = int(round(won / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    if eok >= 1:
        return f"약 {eok:,}억원"
    return f"약 {won:,.0f}원"


def _number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _already_parenthesized(tail: str) -> bool:
    return bool(re.match(r"\s*\([^)]*원(?:/[^)]*)?\)", tail))


def _normalize_existing_separate_krw(text: str) -> str:
    # 과거 고정환율로 본문에 박혀 있던 "223억달러 ≈ 29조..." 같은 값을 제거한 뒤
    # 아래 enforce 단계에서 실행 시점의 검증된 API 환율로 다시 계산한다.
    # 사용자가 요구한 표기는 항상 "외화금액(약 원화금액)"으로 통일한다.
    pat = re.compile(
        r"(?P<fx>\d[\d,.]*(?:\.\d+)?\s*(?:조|십억|억|백만|천만)(?:싱가포르달러|홍콩달러|캐나다달러|대만달러|호주달러|스위스프랑|달러|유로|엔|링깃|위안|파운드))"
        r"\s*(?:·|=|≈|≒)\s*(?:약\s*)?[\d,]+(?:조[\d,]*억|조|억)?원"
    )
    return pat.sub(lambda m: m.group("fx"), text)


def enforce_text(text: str) -> str:
    text = _normalize_existing_separate_krw(text)

    # Ranges that share a currency unit, e.g. 600억~640억달러.
    range_pat = re.compile(
        r"(?P<a>\d[\d,.]*(?:\.\d+)?)\s*(?P<ua>조|십억|억|백만|천만)"
        r"\s*(?P<sep>[~～–—-])\s*"
        r"(?P<b>\d[\d,.]*(?:\.\d+)?)\s*(?P<ub>조|십억|억|백만|천만)?"
        r"(?P<word>싱가포르달러|홍콩달러|캐나다달러|대만달러|호주달러|스위스프랑|달러|유로|엔|링깃|위안|파운드)"
    )
    def repl_range(m):
        tail = text[m.end():]
        if _already_parenthesized(tail):
            return m.group(0)
        ua = m.group("ua")
        ub = m.group("ub") or ua
        currency = CURRENCY_WORDS[m.group("word")]
        a = _number(m.group("a")) * SCALE[ua]
        b = _number(m.group("b")) * SCALE[ub]
        return f"{m.group(0)}({_krw_text(a, currency)}~{_krw_text(b, currency)})"
    text = range_pat.sub(repl_range, text)

    # Korean large-unit currency amounts.
    large_pat = re.compile(
        r"(?P<num>\d[\d,.]*(?:\.\d+)?)\s*(?P<unit>조|십억|억|백만|천만)"
        r"(?P<word>싱가포르달러|홍콩달러|캐나다달러|대만달러|호주달러|스위스프랑|달러|유로|엔|링깃|위안|파운드)(?P<per>/" + PER_UNIT_PATTERN + r")?",
        re.I,
    )
    def repl_large(m):
        tail = text[m.end():]
        if _already_parenthesized(tail):
            return m.group(0)
        currency = CURRENCY_WORDS[m.group("word")]
        value = _number(m.group("num")) * SCALE[m.group("unit")]
        per = m.group("per") or ""
        return f"{m.group(0)}({_krw_text(value, currency, per)})"
    text = large_pat.sub(repl_large, text)

    # Symbol amounts such as $11.4B, €2 billion, HK$500 million.
    symbol_pat = re.compile(
        r"(?P<prefix>US\$|HK\$|NT\$|S\$|A\$|C\$|\$|€|£)\s*"
        r"(?P<num>\d[\d,.]*(?:\.\d+)?)\s*"
        r"(?P<unit>billion|million|B|M)\b(?P<per>/" + PER_UNIT_PATTERN + r")?",
        re.I,
    )
    def repl_symbol(m):
        tail = text[m.end():]
        if _already_parenthesized(tail):
            return m.group(0)
        unit = m.group("unit").lower()
        value = _number(m.group("num")) * (1_000_000_000 if unit in ("billion", "b") else 1_000_000)
        per = m.group("per") or ""
        prefix = m.group("prefix")
        currency = SYMBOL_CURRENCIES.get(prefix.upper() if prefix.upper() in SYMBOL_CURRENCIES else prefix, SYMBOL_CURRENCIES.get(prefix))
        if not currency:
            currency = "USD" if "$" in prefix else ("EUR" if prefix == "€" else "GBP")
        return f"{m.group(0)}({_krw_text(value, currency, per)})"
    text = symbol_pat.sub(repl_symbol, text)

    # ISO-code amounts such as USD 30,000, EUR 2 billion, JPY 500 million.
    iso_pat = re.compile(
        r"(?P<code>USD|EUR|JPY|MYR|CNY|HKD|GBP|SGD|TWD|AUD|CAD|CHF)\s*"
        r"(?P<num>\d[\d,.]*(?:\.\d+)?)\s*"
        r"(?P<unit>billion|million|B|M)?\b(?P<per>/" + PER_UNIT_PATTERN + r")?",
        re.I,
    )
    def repl_iso(m):
        tail = text[m.end():]
        if _already_parenthesized(tail):
            return m.group(0)
        code = m.group("code").upper()
        currency = ISO_CURRENCIES[code]
        unit = (m.group("unit") or "").lower()
        value = _number(m.group("num"))
        if unit in ("billion", "b"):
            value *= 1_000_000_000
        elif unit in ("million", "m"):
            value *= 1_000_000
        per = m.group("per") or ""
        return f"{m.group(0)}({_krw_text(value, currency, per)})"
    text = iso_pat.sub(repl_iso, text)

    # Plain symbol amounts such as $73.39/kg, €12, HK$500.
    symbol_plain = re.compile(
        r"(?P<prefix>US\$|HK\$|NT\$|S\$|A\$|C\$|\$|€|£)\s*"
        r"(?P<num>\d[\d,.]*(?:\.\d+)?)"
        r"(?P<per>/" + PER_UNIT_PATTERN + r")?",
        re.I,
    )
    def repl_symbol_plain(m):
        tail = text[m.end():]
        if _already_parenthesized(tail):
            return m.group(0)
        if re.match(r"\s*(?:billion|million|B|M)\b", tail, re.I):
            return m.group(0)
        prefix = m.group("prefix")
        currency = SYMBOL_CURRENCIES.get(prefix.upper() if prefix.upper() in SYMBOL_CURRENCIES else prefix, SYMBOL_CURRENCIES.get(prefix))
        if not currency:
            currency = "USD" if "$" in prefix else ("EUR" if prefix == "€" else "GBP")
        per = m.group("per") or ""
        return f"{m.group(0)}({_krw_text(_number(m.group('num')), currency, per)})"
    text = symbol_plain.sub(repl_symbol_plain, text)

    word_plain = re.compile(
        r"(?P<num>\d[\d,.]*(?:\.\d+)?)\s*(?P<word>싱가포르달러|홍콩달러|캐나다달러|대만달러|호주달러|스위스프랑|달러|유로|엔|링깃|위안|파운드)"
        r"(?P<per>/" + PER_UNIT_PATTERN + r")?"
    )
    def repl_word_plain(m):
        tail = text[m.end():]
        if tail.lstrip().startswith("=") or _already_parenthesized(tail):
            return m.group(0)
        # Large-unit amounts were already handled.
        before = text[max(0, m.start()-4):m.start()]
        if any(before.endswith(x) for x in ("조", "십억", "억", "백만", "천만")):
            return m.group(0)
        currency = CURRENCY_WORDS[m.group("word")]
        per = m.group("per") or ""
        return f"{m.group(0)}({_krw_text(_number(m.group('num')), currency, per)})"
    text = word_plain.sub(repl_word_plain, text)
    validate_text(text)
    return text


def _money_candidates(text: str):
    word = (
        r"\d[\d,.]*(?:\.\d+)?\s*(?:조|십억|억|백만|천만)?"
        r"(?:싱가포르달러|홍콩달러|캐나다달러|대만달러|호주달러|스위스프랑|달러|유로|엔|링깃|위안|파운드)"
        r"(?:/" + PER_UNIT_PATTERN + r")?"
    )
    symbol = (
        r"(?:US\$|HK\$|NT\$|S\$|A\$|C\$|\$|€|£)\s*"
        r"\d[\d,.]*(?:\.\d+)?(?:\s*(?:billion|million|B|M))?"
        r"(?:/" + PER_UNIT_PATTERN + r")?"
    )
    iso = (
        r"(?:USD|EUR|JPY|MYR|CNY|HKD|GBP|SGD|TWD|AUD|CAD|CHF)\s*"
        r"\d[\d,.]*(?:\.\d+)?(?:\s*(?:billion|million|B|M))?"
        r"(?:/" + PER_UNIT_PATTERN + r")?"
    )
    for m in re.finditer(word + "|" + symbol + "|" + iso, text, re.I):
        yield m


def validate_text(text: str) -> None:
    unpaired = []
    for m in _money_candidates(text):
        token = m.group(0)
        tail = text[m.end():]
        # Exchange-rate basis lines such as 1달러=1,350원 are not monetary
        # values requiring a second KRW conversion.
        if re.match(r"\s*=", tail):
            continue
        if not _already_parenthesized(tail):
            unpaired.append(token)
    if unpaired:
        sample = ", ".join(unpaired[:3])
        raise RuntimeError("외화 금액 뒤 원화 괄호 누락—알림 발송 보류: " + sample)


def enforce_file(path: str | pathlib.Path) -> bool:
    p = pathlib.Path(path)
    if not p.exists():
        return False
    original = p.read_text(encoding="utf-8")
    updated = enforce_text(original)
    if updated != original:
        p.write_text(updated, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        print(f"{arg}: changed={enforce_file(arg)}")

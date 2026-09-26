from __future__ import annotations

import pathlib
import re

from fx_api import daily_krw

CURRENCY_WORDS = {
    "달러": "USD",
    "유로": "EUR",
    "엔": "JPY",
    "링깃": "MYR",
}
SCALE = {
    "조": 1_000_000_000_000,
    "억": 100_000_000,
    "십억": 1_000_000_000,
    "백만": 1_000_000,
    "천만": 10_000_000,
}
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
    rate, _ = _rate(currency)
    if rate is None:
        return "원화 환산 확인 불가" + per_unit
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
    # "150십억달러 · 약 203조원" -> "150십억달러(약 203조원)"
    pat = re.compile(
        r"(?P<fx>\d[\d,.]*(?:\.\d+)?\s*(?:조|십억|억|백만|천만)?(?:달러|유로|엔|링깃))"
        r"\s*(?:·|=)\s*(?P<krw>약\s*[\d,]+(?:조[\d,]*억|조|억)?원)"
    )
    return pat.sub(lambda m: f"{m.group('fx')}({m.group('krw')})", text)


def enforce_text(text: str) -> str:
    text = _normalize_existing_separate_krw(text)

    # Ranges that share a currency unit, e.g. 600억~640억달러.
    range_pat = re.compile(
        r"(?P<a>\d[\d,.]*(?:\.\d+)?)\s*(?P<ua>조|십억|억|백만|천만)"
        r"\s*(?P<sep>[~～–—-])\s*"
        r"(?P<b>\d[\d,.]*(?:\.\d+)?)\s*(?P<ub>조|십억|억|백만|천만)?"
        r"(?P<word>달러|유로|엔|링깃)"
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
        r"(?P<word>달러|유로|엔|링깃)(?P<per>/(?:kg|GB|Gb|TB|주|개|module|chip))?",
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

    # $11.4B / US$15 billion.
    symbol_pat = re.compile(
        r"(?P<prefix>US\$|\$)\s*(?P<num>\d[\d,.]*(?:\.\d+)?)\s*"
        r"(?P<unit>billion|million|B|M)\b(?P<per>/(?:kg|GB|Gb|TB|주|개|module|chip))?",
        re.I,
    )
    def repl_symbol(m):
        tail = text[m.end():]
        if _already_parenthesized(tail):
            return m.group(0)
        unit = m.group("unit").lower()
        value = _number(m.group("num")) * (1_000_000_000 if unit in ("billion", "b") else 1_000_000)
        per = m.group("per") or ""
        return f"{m.group(0)}({_krw_text(value, 'USD', per)})"
    text = symbol_pat.sub(repl_symbol, text)

    # Plain amounts such as $73.39/kg or 73.39달러/kg.
    usd_plain = re.compile(
        r"(?P<prefix>US\$|\$)\s*(?P<num>\d[\d,.]*(?:\.\d+)?)"
        r"(?P<per>/(?:kg|GB|Gb|TB|주|개|module|chip))?",
        re.I,
    )
    def repl_usd_plain(m):
        # Do not re-process a symbol amount that was already expanded above.
        tail = text[m.end():]
        if _already_parenthesized(tail):
            return m.group(0)
        if re.match(r"\s*(?:billion|million|B|M)\b", tail, re.I):
            return m.group(0)
        per = m.group("per") or ""
        return f"{m.group(0)}({_krw_text(_number(m.group('num')), 'USD', per)})"
    text = usd_plain.sub(repl_usd_plain, text)

    word_plain = re.compile(
        r"(?P<num>\d[\d,.]*(?:\.\d+)?)\s*(?P<word>달러|유로|엔|링깃)"
        r"(?P<per>/(?:kg|GB|Gb|TB|주|개|module|chip))?"
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
    return text


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

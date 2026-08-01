#!/usr/bin/env python3
"""Normalize policy-watch Telegram messages immediately before delivery."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
FX_TIMEOUT_SECONDS = max(3, int(os.getenv("KHS_POLICY_FX_TIMEOUT_SECONDS", "8")))
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"

REMOVED_FIELD_PREFIXES = (
    "- 투자 관점:",
    "- 투자 영향:",
    "- 투자 포인트:",
    "- 한국장 영향:",
    "- 한국장:",
    "- 의사결정 영향:",
    "- 영향 섹터:",
    "- 한국 밸류체인:",
    "- 반영/반대:",
    "- 실패 신호:",
    "- 원화 환산 기준:",
)

REMOVED_EXACT_LINES = {
    "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
}

CURRENCY_SPECS = {
    "USD": {"labels": ("미국 달러", "미달러", "달러", "USD", "US$", "$"), "symbol": "KRW=X"},
    "EUR": {"labels": ("유로", "EUR", "€"), "symbol": "EURKRW=X"},
    "JPY": {"labels": ("일본 엔", "엔화", "엔", "JPY"), "symbol": "JPYKRW=X"},
    "CNY": {"labels": ("중국 위안", "위안화", "위안", "CNY", "RMB"), "symbol": "CNYKRW=X"},
    "GBP": {"labels": ("영국 파운드", "파운드", "GBP", "£"), "symbol": "GBPKRW=X"},
    "CHF": {"labels": ("스위스 프랑", "스위스프랑", "CHF"), "symbol": "CHFKRW=X"},
    "CAD": {"labels": ("캐나다 달러", "캐나다달러", "CAD"), "symbol": "CADKRW=X"},
    "AUD": {"labels": ("호주 달러", "호주달러", "AUD"), "symbol": "AUDKRW=X"},
    "HKD": {"labels": ("홍콩 달러", "홍콩달러", "HKD"), "symbol": "HKDKRW=X"},
    "SGD": {"labels": ("싱가포르 달러", "싱가포르달러", "SGD"), "symbol": "SGDKRW=X"},
    "TWD": {"labels": ("대만 달러", "대만달러", "TWD"), "symbol": "TWDKRW=X"},
    "INR": {"labels": ("인도 루피", "루피", "INR"), "symbol": "INRKRW=X"},
    "BRL": {"labels": ("브라질 헤알", "헤알", "BRL"), "symbol": "BRLKRW=X"},
    "MXN": {"labels": ("멕시코 페소", "멕시코페소", "MXN"), "symbol": "MXNKRW=X"},
    "NZD": {"labels": ("뉴질랜드 달러", "뉴질랜드달러", "NZD"), "symbol": "NZDKRW=X"},
    "SEK": {"labels": ("스웨덴 크로나", "SEK"), "symbol": "SEKKRW=X"},
    "NOK": {"labels": ("노르웨이 크로네", "NOK"), "symbol": "NOKKRW=X"},
    "DKK": {"labels": ("덴마크 크로네", "DKK"), "symbol": "DKKKRW=X"},
    "PLN": {"labels": ("폴란드 즈워티", "즈워티", "PLN"), "symbol": "PLNKRW=X"},
    "TRY": {"labels": ("튀르키예 리라", "터키 리라", "리라", "TRY"), "symbol": "TRYKRW=X"},
    "SAR": {"labels": ("사우디 리얄", "리얄", "SAR"), "symbol": "SARKRW=X"},
    "AED": {"labels": ("UAE 디르함", "아랍에미리트 디르함", "디르함", "AED"), "symbol": "AEDKRW=X"},
    "IDR": {"labels": ("인도네시아 루피아", "루피아", "IDR"), "symbol": "IDRKRW=X"},
    "MYR": {"labels": ("말레이시아 링깃", "링깃", "MYR"), "symbol": "MYRKRW=X"},
    "THB": {"labels": ("태국 바트", "바트", "THB"), "symbol": "THBKRW=X"},
    "PHP": {"labels": ("필리핀 페소", "필리핀페소", "PHP"), "symbol": "PHPKRW=X"},
    "ZAR": {"labels": ("남아공 랜드", "랜드", "ZAR"), "symbol": "ZARKRW=X"},
}

ENGLISH_SCALE_MULTIPLIERS = {
    "trillion": 1_000_000_000_000,
    "tn": 1_000_000_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "million": 1_000_000,
    "mn": 1_000_000,
}

FOREIGN_NUMBER_PATTERN = r"\d[\d,.]*(?:\s*[천백십조억만]\s*\d[\d,.]*)*(?:\s*[천백십조억만])?"


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_small_korean_number(value: str) -> float:
    text = re.sub(r"[,\s]", "", value or "")
    if not text:
        return 0.0
    total = 0.0
    remaining = text
    for unit, multiplier in (("천", 1_000), ("백", 100), ("십", 10)):
        if unit not in remaining:
            continue
        left, remaining = remaining.split(unit, 1)
        total += (float(left) if left else 1.0) * multiplier
    if remaining:
        total += float(remaining)
    return total


def _parse_foreign_number(value: str, scale: str = "") -> float | None:
    text = re.sub(r"[,\s]", "", value or "")
    if not text:
        return None
    try:
        total = 0.0
        remaining = text
        for unit, multiplier in (("조", 1_000_000_000_000), ("억", 100_000_000), ("만", 10_000)):
            if unit not in remaining:
                continue
            left, remaining = remaining.split(unit, 1)
            total += _parse_small_korean_number(left or "1") * multiplier
        total += _parse_small_korean_number(remaining)
        total *= ENGLISH_SCALE_MULTIPLIERS.get((scale or "").lower(), 1)
        return total if total > 0 else None
    except (TypeError, ValueError):
        return None


def _label_to_code(label: str) -> str:
    normalized = _clean(label).lower()
    for code, spec in CURRENCY_SPECS.items():
        if any(normalized == candidate.lower() for candidate in spec["labels"]):
            return code
    return ""


def _amount_patterns() -> tuple[re.Pattern[str], re.Pattern[str]]:
    suffix_labels = sorted(
        {
            label
            for spec in CURRENCY_SPECS.values()
            for label in spec["labels"]
            if label not in {"$", "€", "£"}
        },
        key=len,
        reverse=True,
    )
    prefix_labels = sorted(
        {"$", "€", "£", "US$", *CURRENCY_SPECS.keys()},
        key=len,
        reverse=True,
    )
    suffix = re.compile(
        rf"(?P<number>{FOREIGN_NUMBER_PATTERN})\s*"
        rf"(?P<scale>trillion|billion|million|tn|bn|mn)?\s*"
        rf"(?P<label>{'|'.join(re.escape(value) for value in suffix_labels)})",
        re.IGNORECASE,
    )
    prefix = re.compile(
        rf"(?<![A-Za-z])(?P<label>{'|'.join(re.escape(value) for value in prefix_labels)})\s*"
        rf"(?P<number>{FOREIGN_NUMBER_PATTERN})\s*"
        rf"(?P<scale>trillion|billion|million|tn|bn|mn)?",
        re.IGNORECASE,
    )
    return suffix, prefix


AMOUNT_PATTERNS = _amount_patterns()


def extract_foreign_amounts(text: str) -> list[dict]:
    output: list[dict] = []
    occupied: list[tuple[int, int]] = []
    for pattern in AMOUNT_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            tail = str(text or "")[match.end(): match.end() + 28]
            if re.match(r"\s*\((?:약\s*)?[\d,.조억만원]+\)", tail):
                continue
            code = _label_to_code(match.group("label"))
            amount = _parse_foreign_number(match.group("number"), match.group("scale") or "")
            if not code or amount is None:
                continue
            occupied.append(match.span())
            output.append(
                {
                    "code": code,
                    "amount": amount,
                    "raw": re.sub(r"\s+", " ", match.group(0)).strip(),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return sorted(output, key=lambda item: item["start"])


def _yahoo_rate(code: str, now: dt.datetime) -> dict:
    symbol = str(CURRENCY_SPECS.get(code, {}).get("symbol") or f"{code}KRW=X")
    url = (
        YAHOO_CHART_URL
        + urllib.parse.quote(symbol, safe="")
        + "?interval=1d&range=5d"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GAMEJOA-policy-watch/1.0)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=FX_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
        meta = result.get("meta") or {}
        value = float(meta["regularMarketPrice"])
        reference = dt.datetime.fromtimestamp(
            int(meta["regularMarketTime"]),
            tz=dt.timezone.utc,
        ).astimezone(KST)
        return {
            "value": value,
            "source": "Yahoo Finance",
            "reference_time_kst": reference.isoformat(timespec="minutes"),
            "query_time_kst": now.isoformat(timespec="minutes"),
        }
    except Exception as exc:
        return {
            "value": None,
            "source": "Yahoo Finance",
            "reference_time_kst": "",
            "query_time_kst": now.isoformat(timespec="minutes"),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _frankfurter_rates(codes: list[str], now: dt.datetime) -> dict[str, dict]:
    if not codes:
        return {}
    request = urllib.request.Request(
        "https://api.frankfurter.app/latest",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GAMEJOA-policy-watch/1.0)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=FX_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rates = payload.get("rates") or {}
        krw_per_eur = float(rates["KRW"])
        reference = f"{payload.get('date')}T00:00+09:00"
        output: dict[str, dict] = {}
        for code in codes:
            if code == "EUR":
                value = krw_per_eur
            elif code in rates:
                value = krw_per_eur / float(rates[code])
            else:
                continue
            output[code] = {
                "value": value,
                "source": "ECB/Frankfurter",
                "reference_time_kst": reference,
                "query_time_kst": now.isoformat(timespec="minutes"),
            }
        return output
    except Exception:
        return {}


def collect_rates(codes: list[str], now: dt.datetime) -> dict[str, dict]:
    rates = {code: _yahoo_rate(code, now) for code in codes}
    missing = [code for code, item in rates.items() if item.get("value") is None]
    for code, item in _frankfurter_rates(missing, now).items():
        rates[code] = item
    return rates


def _normalized_rates(rates: dict | None, codes: list[str], now: dt.datetime) -> dict[str, dict]:
    if rates is None:
        return collect_rates(codes, now)
    output: dict[str, dict] = {}
    for code in codes:
        raw = rates.get(code)
        if isinstance(raw, (int, float)):
            output[code] = {
                "value": float(raw),
                "source": "검증 고정값",
                "reference_time_kst": now.isoformat(timespec="minutes"),
                "query_time_kst": now.isoformat(timespec="minutes"),
            }
        elif isinstance(raw, dict):
            output[code] = {
                "value": raw.get("value"),
                "source": raw.get("source") or "확인 불가",
                "reference_time_kst": raw.get("reference_time_kst") or "",
                "query_time_kst": raw.get("query_time_kst") or now.isoformat(timespec="minutes"),
            }
        else:
            output[code] = {
                "value": None,
                "source": "확인 불가",
                "reference_time_kst": "",
                "query_time_kst": now.isoformat(timespec="minutes"),
            }
    return output


def format_krw_amount(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"{int(value / 1_000_000_000_000 + 0.5):,}조원"
    if value >= 100_000_000:
        number = f"{value / 100_000_000:,.1f}".rstrip("0").rstrip(".")
        return f"{number}억원"
    if value >= 10_000:
        number = f"{value / 10_000:,.1f}".rstrip("0").rstrip(".")
        return f"{number}만원"
    return f"{value:,.0f}원"


def _convert_text(text: str, rates: dict[str, dict]) -> tuple[str, set[str]]:
    matches = extract_foreign_amounts(text)
    if not matches:
        return text, set()
    output = text
    used: set[str] = set()
    for item in reversed(matches):
        rate = rates.get(item["code"]) or {}
        if rate.get("value") is None:
            converted = "원화 환산 확인 불가"
        else:
            converted = f"약 {format_krw_amount(item['amount'] * float(rate['value']))}"
        replacement = f"{item['raw']}({converted})"
        output = output[: item["start"]] + replacement + output[item["end"]:]
        used.add(item["code"])
    return output, used


def _format_fx_provenance(codes: set[str], rates: dict[str, dict]) -> str:
    parts: list[str] = []
    for code in sorted(codes):
        item = rates.get(code) or {}
        value = item.get("value")
        source = str(item.get("source") or "확인 불가")
        reference = str(item.get("reference_time_kst") or "")
        reference_label = reference[5:16].replace("T", " ") if len(reference) >= 16 else "기준일 확인 불가"
        if value is None:
            parts.append(f"{code}/KRW 확인 불가 · {source}")
        else:
            parts.append(f"{code}/KRW {float(value):,.2f}원 · {source} · {reference_label} KST")
    return "- 원화 환산 기준: " + " / ".join(parts)


def _compact_converted_core(core: str, limit: int = 50) -> str:
    text = re.sub(r"\s+", " ", str(core or "")).strip()
    if len(text) <= limit:
        return text
    chunks: list[str] = []
    first_position: int | None = None
    occupied: list[tuple[int, int]] = []
    for pattern in AMOUNT_PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            krw_match = re.match(
                r"\((?:약\s*)?[^)]{1,40}원\)",
                text[match.end():],
            )
            if not krw_match:
                continue
            occupied.append(match.span())
            chunk = text[match.start(): match.end() + krw_match.end()]
            if chunk in chunks:
                continue
            if first_position is None:
                first_position = match.start()
            chunks.append(chunk)
    if chunks:
        prefix = text[: first_position or 0].strip(" ,·;:")
        prefix_tokens = re.findall(r"[A-Za-z0-9가-힣·]+", prefix)
        short_prefix = " ".join(prefix_tokens[-2:])
        joined = ", ".join(chunks)
        for candidate in (
            f"{short_prefix} {joined}입니다.".strip(),
            f"{joined}입니다.",
        ):
            if len(candidate) <= limit:
                return candidate
    return text


def _compact_converted_core_lines(body: str) -> str:
    output: list[str] = []
    for raw_line in str(body or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- 핵심:"):
            core = stripped.removeprefix("- 핵심:").strip()
            indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            raw_line = f"{indent}- 핵심: {_compact_converted_core(core)}"
        output.append(raw_line)
    return "\n".join(output)


def normalize_policy_structure(title: str, body: str) -> tuple[str, str]:
    title = re.sub(r"^\s*KHS\s+", "", str(title or "").strip(), flags=re.IGNORECASE)
    lines: list[str] = []
    for raw_line in str(body or "").splitlines():
        line = re.sub(r"^(\s*(?:🚨|⚠️)?\s*)KHS\s+", r"\1", raw_line, flags=re.IGNORECASE)
        line = re.sub(r"^\s*##\s+", "", line)
        stripped = line.strip()
        if stripped in REMOVED_EXACT_LINES:
            continue
        if stripped.startswith(REMOVED_FIELD_PREFIXES):
            continue
        if re.match(r"^(?:Actions|Issues):\s*https?://", stripped, flags=re.IGNORECASE):
            continue
        lines.append(line.rstrip())
    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return title, body


def format_policy_message(
    title: str,
    body: str,
    *,
    rates: dict | None = None,
    now: dt.datetime | None = None,
) -> tuple[str, str]:
    """Return the final compact policy-watch title and body."""
    now = now or dt.datetime.now(tz=KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    else:
        now = now.astimezone(KST)

    title, body = normalize_policy_structure(title, body)
    amounts = extract_foreign_amounts(f"{title}\n{body}")
    codes = sorted({str(item["code"]) for item in amounts})
    rate_snapshot = _normalized_rates(rates, codes, now)
    title, _title_codes = _convert_text(title, rate_snapshot)
    body, _body_codes = _convert_text(body, rate_snapshot)
    body = _compact_converted_core_lines(body)
    return title.strip(), body.strip() + "\n"


def validate_final_policy_message(title: str, body: str) -> list[str]:
    errors: list[str] = []
    combined = f"{title}\n{body}"
    if re.search(r"(?mi)^(?:🚨\s*|⚠️\s*)?KHS\s+", combined):
        errors.append("khs_branding_present")
    if re.search(r"(?m)^\s*##\s+", body):
        errors.append("markdown_heading_present")
    for prefix in REMOVED_FIELD_PREFIXES:
        if prefix in body:
            errors.append(f"removed_field_present:{prefix}")
    if re.search(r"(?mi)^(?:Actions|Issues):\s*https?://", body):
        errors.append("github_meta_link_present")
    if any(line in body for line in REMOVED_EXACT_LINES):
        errors.append("policy_disclaimer_present")
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- 핵심:"):
            continue
        core = stripped.removeprefix("- 핵심:").strip()
        if len(core) > 50:
            errors.append(f"policy_core_too_long:{len(core)}")
        if "…" in core or re.search(r"\.{3,}", core):
            errors.append("policy_core_truncated")
    if extract_foreign_amounts(combined):
        errors.append("foreign_currency_not_converted")
    return errors

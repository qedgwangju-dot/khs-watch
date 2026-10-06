#!/usr/bin/env python3
"""Normalize policy-watch Telegram messages immediately before delivery."""

from __future__ import annotations

import datetime as dt
import html
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



SOURCE_LINE_RE = re.compile(r"^(?P<indent>\s*-\s*출처:\s*)(?P<value>.*)$")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
HTML_SOURCE_LINK_RE = re.compile(
    r'<a\s+href=(?P<quote>["\'])(?P<url>https?://[^"\'<>\s]+)(?P=quote)>'
    r'(?P<label>[^<]*)</a>',
    re.IGNORECASE,
)
SOURCE_LINK_GENERIC_LABELS = {
    "원문",
    "원문 보기",
    "원문보기",
    "원문 뉴스보기",
    "원문뉴스보기",
    "source",
    "출처",
}


def _clean_source_url(url: str) -> str:
    return str(url or "").strip().rstrip(".,;:)")


def _html_source_link(url: str, label: str = "원문") -> str:
    url = _clean_source_url(url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    safe_label = html.escape(_clean(label) or "원문", quote=False)
    return '<a href="' + html.escape(url, quote=True) + '">' + safe_label + '</a>'


def _source_suffix(parts: list[str]) -> str:
    cleaned: list[str] = []
    for value in parts:
        value = re.sub(r"^\s*[·|]\s*", "", str(value or "")).strip()
        value = re.sub(r"\s+", " ", value)
        if value and value not in cleaned:
            cleaned.append(value)
    return " · ".join(cleaned)


def normalize_source_line(line: str) -> str:
    """Render every source row as one Telegram-safe, clickable 원문 link."""
    match = SOURCE_LINE_RE.match(str(line or ""))
    if not match:
        return line

    prefix = match.group("indent")
    value = match.group("value").strip()
    link_match = HTML_SOURCE_LINK_RE.search(value)
    if link_match:
        label = link_match.group("label").strip()
        url = html.unescape(link_match.group("url"))
        before = value[: link_match.start()]
        after = value[link_match.end() :]
    else:
        link_match = MARKDOWN_LINK_RE.search(value)
        if link_match:
            label = link_match.group(1).strip()
            url = link_match.group(2)
            before = value[: link_match.start()]
            after = value[link_match.end() :]
        else:
            raw_url = re.search(r"https?://[^\s)>]+", value)
            if not raw_url:
                return line
            label = ""
            url = raw_url.group(0)
            before = value[: raw_url.start()]
            after = value[raw_url.end() :]

    source_link = _html_source_link(url)
    if not source_link:
        return line

    parts: list[str] = []
    normalized_label = re.sub(r"\s+", " ", label).strip().lower()
    cleaned_before = re.sub(
        r"(?i)원문(?:\s*뉴스)?\s*보기?\s*[:(]?$",
        "",
        before,
    ).strip(" ·:()")
    if cleaned_before:
        parts.append(cleaned_before)
    if label and normalized_label not in SOURCE_LINK_GENERIC_LABELS:
        parts.append(label)
    if after:
        parts.append(after)

    suffix = _source_suffix(parts)
    return prefix + source_link + (f" · {suffix}" if suffix else "")


def normalize_source_links(body: str) -> str:
    return "\n".join(normalize_source_line(line) for line in str(body or "").splitlines())


def _bold_timeline_dates_html(value: str) -> str:
    """Bold Korean-formatted dates only inside the timeline section."""
    date_re = re.compile(r"\b(\d{4}년\s+\d{1,2}월\s+\d{1,2}일)\b")
    output: list[str] = []
    in_timeline = False
    for raw_line in str(value or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- 타임라인:") or stripped == "타임라인":
            in_timeline = True
            raw_line = date_re.sub(r"<b>\1</b>", raw_line)
        elif in_timeline:
            if not stripped:
                in_timeline = False
            elif stripped.startswith(("•", "·")):
                raw_line = date_re.sub(r"<b>\1</b>", raw_line)
            else:
                in_timeline = False
        output.append(raw_line)
    return "\n".join(output)


def prepare_telegram_html(title: str, body: str) -> str:
    """Escape message text while preserving safe source links and timeline-date bold."""
    message = f"{title}\n\n{body}".strip()
    anchors: list[str] = []

    def protect(match: re.Match[str]) -> str:
        url = _clean_source_url(html.unescape(match.group("url")))
        label = match.group("label").strip() or "원문"
        anchor = _html_source_link(url, label)
        if not anchor:
            return ""
        token = f"@@KHS_SOURCE_LINK_{len(anchors)}@@"
        anchors.append(anchor)
        return token

    escaped = html.escape(HTML_SOURCE_LINK_RE.sub(protect, message), quote=False)
    for index, anchor in enumerate(anchors):
        escaped = escaped.replace(f"@@KHS_SOURCE_LINK_{index}@@", anchor)
    escaped = _bold_timeline_dates_html(escaped)
    escaped = re.sub(r"(?m)^(\d+\.\s+\[[^\]\n]+\][^\n]+)$", r"<b>\1</b>", escaped)
    escaped = re.sub(
        r"(?m)^(- (?:핵심|실제 내용|현재 단계|발표일|채택일|공개일|타임라인|범위 주의|다음 확인):)",
        r"<b>\1</b>",
        escaped,
    )
    return escaped


def prepare_telegram_messages(title: str, body: str, limit: int = 4096) -> list[str]:
    """Split on article/field boundaries; preserve every fact and complete source anchor."""
    articles = re.split(r"(?m)(?=^\d+\.\s+\[[^\]\n]+\])", str(body or "").strip())
    blocks: list[str] = []
    for article in articles:
        if not article.strip():
            continue
        if len(prepare_telegram_html(title, article)) <= limit:
            blocks.append(article.strip())
        else:
            for paragraph in re.split(r"\n\s*\n", article.strip()):
                if len(prepare_telegram_html(title, paragraph)) <= limit:
                    blocks.append(paragraph)
                else:
                    blocks.extend(paragraph.splitlines())
    output: list[str] = []
    current = ""
    for block in blocks:
        candidate = (current + "\n\n" + block).strip() if current else block
        if len(prepare_telegram_html(title, candidate)) <= limit:
            current = candidate
            continue
        if current:
            output.append(prepare_telegram_html(title, current))
        if len(prepare_telegram_html(title, block)) > limit:
            raise ValueError("policy_field_exceeds_telegram_limit: preserve source text for review")
        current = block
    if current:
        output.append(prepare_telegram_html(title, current))
    return output



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
    body = normalize_source_links(body)
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
    try:
        from khs_policy_readability_patch import improve_policy_readability
    except ImportError:
        from scripts.khs_policy_readability_patch import improve_policy_readability
    body = improve_policy_readability(body)
    amounts = extract_foreign_amounts(f"{title}\n{body}")
    codes = sorted({str(item["code"]) for item in amounts})
    rate_snapshot = _normalized_rates(rates, codes, now)
    title, _title_codes = _convert_text(title, rate_snapshot)
    body, _body_codes = _convert_text(body, rate_snapshot)
    return title.strip(), body.strip() + "\n"



_TIMELINE_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _timeline_parse_day(value: object) -> dt.date | None:
    raw = _clean(value)
    if not raw:
        return None
    iso = re.match(r"^(20\d{2})-(\d{1,2})-(\d{1,2})", raw)
    if iso:
        try:
            return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    korean = re.search(r"\b(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\b", raw)
    if korean:
        try:
            return dt.date(int(korean.group(1)), int(korean.group(2)), int(korean.group(3)))
        except ValueError:
            return None
    english = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(\d{1,2}),\s+(20\d{2})\b",
        raw,
        re.I,
    )
    if english:
        month = _TIMELINE_MONTHS.get(english.group(1).lower())
        try:
            return dt.date(int(english.group(3)), int(month or 0), int(english.group(2)))
        except ValueError:
            return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.date()
    except ValueError:
        return None


def _timeline_ko_date(day: dt.date) -> str:
    return f"{day.year}년 {day.month}월 {day.day}일"


def _presidential_action_surface(value: object) -> str:
    if isinstance(value, dict):
        keys = (
            "document_type", "presidential_document_type", "title", "source_title",
            "original_title", "news", "original_news", "summary", "source_abstract",
            "source_body", "policy_plain_summary", "link", "source",
        )
        parts = [str(value.get(key) or "") for key in keys]
        for row in value.get("source_links") or []:
            if isinstance(row, dict):
                parts.extend(
                    str(row.get(key) or "")
                    for key in (
                        "document_type", "presidential_document_type", "original_title",
                        "link", "source", "executive_order_number",
                    )
                )
        return re.sub(r"\s+", " ", " ".join(parts)).strip()
    return re.sub(r"\s+", " ", str(value or "")).strip()


def presidential_action_timeline_required(value: object) -> bool:
    text = _presidential_action_surface(value).lower()
    if not text:
        return False
    if any(term in text for term in (
        "executive order", "행정명령",
        "presidential determination", "대통령 결정",
        "presidential memorandum", "대통령각서",
    )):
        return True
    dpa = "defense production act" in text or re.search(r"\bdpa\b", text) is not None
    return bool(
        dpa
        and any(term in text for term in (
            "white house", "whitehouse.gov", "department of energy", "energy.gov",
            "section 303", "50 u.s.c. 4533", "전력망", "송전", "변압기", "national defense",
        ))
    )


def presidential_action_timeline_lines(alert: dict) -> list[str]:
    """Return a source-faithful timeline for executive/presidential-action alerts.

    The timeline never invents an earlier event. It prefers explicit structured
    dates, then dates cited in the verified source body. If only a news date is
    known, it is labelled as a report/current-event date rather than a signing date.
    """
    if not presidential_action_timeline_required(alert):
        return []

    events: list[tuple[dt.date, str]] = []

    def add(day_value: object, detail: str) -> None:
        day = _timeline_parse_day(day_value)
        detail = _clean(detail)
        if not day or not detail:
            return
        key = (day, detail)
        if key not in events:
            events.append(key)

    existing = alert.get("policy_timeline") or []
    for row in existing:
        if isinstance(row, dict):
            detail = " · ".join(
                part for part in (
                    _clean(row.get("stage")),
                    _clean(row.get("detail")),
                ) if part
            )
            add(row.get("date"), detail)
        elif isinstance(row, str):
            m = re.match(
                r"\s*(20\d{2}-\d{1,2}-\d{1,2}|20\d{2}년\s*\d{1,2}월\s*\d{1,2}일)\s*[:·-]\s*(.+)",
                row,
            )
            if m:
                add(m.group(1), m.group(2))

    text = _presidential_action_surface(alert)
    low = text.lower()
    dpa = "defense production act" in low or re.search(r"\bdpa\b", low) is not None
    beluga = any(term in low for term in ("beluga-healy", "beluga healy", "alaska railbelt"))
    grid_dpa = dpa and any(term in low for term in (
        "grid infrastructure", "전력망", "transformer", "변압기", "transmission", "송전",
        "substation", "변전소", "section 303", "제303조",
    ))

    # Official lineage verified from White House and DOE primary sources.
    if grid_dpa:
        add("2025-01-20", "기반 · Executive Order 14156 국가 에너지 비상사태 선언")
        add("2026-04-20", "법적 근거 · DPA 제303조 전력망·전력기기·공급망 대통령 결정")
    if beluga and dpa:
        add(
            "2026-10-05",
            "이번 집행 · DOE, Beluga-Healy 송전사업에 DPA 최대 1.5억달러 투입 의향 발표",
        )

    # Explicit earlier Executive Orders cited by the current official body.
    for match in re.finditer(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),\s+(20\d{2})[^.]{0,140}?\bExecutive Order\s+(\d{4,6})\b",
        text,
        re.I,
    ):
        add(
            f"{match.group(3)}-{_TIMELINE_MONTHS[match.group(1).lower()]:02d}-{int(match.group(2)):02d}",
            f"선행 근거 · Executive Order {match.group(4)}",
        )
    for match in re.finditer(
        r"\bExecutive Order\s+(\d{4,6})\s+of\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),\s+(20\d{2})\b",
        text,
        re.I,
    ):
        add(
            f"{match.group(4)}-{_TIMELINE_MONTHS[match.group(2).lower()]:02d}-{int(match.group(3)):02d}",
            f"선행 근거 · Executive Order {match.group(1)}",
        )

    doc_type = _clean(
        alert.get("presidential_document_type") or alert.get("document_type")
    ).lower()
    source = _clean(alert.get("source")).lower()
    link = _clean(alert.get("link")).lower()
    number = _clean(alert.get("executive_order_number"))
    signing_day = _timeline_parse_day(alert.get("signing_date"))
    published_day = _timeline_parse_day(
        alert.get("published_kst") or alert.get("published")
    )
    publication_day = _timeline_parse_day(alert.get("publication_date"))

    current_day = signing_day or published_day
    if current_day:
        if "executive order" in doc_type or "/executive-orders/" in link:
            label = "이번 조치 · 행정명령"
            if number:
                label += f" {number}"
            label += " 서명·공개"
        elif "presidential memorandum" in doc_type or "presidential determination" in low:
            label = "이번 조치 · 대통령각서·결정 공개"
        elif "energy.gov" in link or "department of energy" in source or source.startswith("doe"):
            label = "이번 조치 · DOE 후속 집행 발표"
        else:
            label = "이번 조치 · 현재 정책 발표"
        if not any(day == current_day for day, _ in events):
            add(current_day.isoformat(), label)

    if publication_day and (
        not current_day or publication_day != current_day
    ):
        add(publication_day.isoformat(), "공식 절차 · 연방관보 게재")

    # Only compute relative deadlines for the actual order/memorandum itself.
    direct_presidential = (
        "executive order" in doc_type
        or "presidential memorandum" in doc_type
        or "/presidential-actions/" in link and ("whitehouse.gov" in link)
    )
    if direct_presidential and current_day:
        for match in re.finditer(
            r"\b(?:within|not later than)\s+(\d{1,3})\s+days(?:\s+of|\s+after)?\s+"
            r"(?:the\s+date\s+of\s+)?(?:this|the)\s+(?:order|memorandum)\b",
            text,
            re.I,
        ):
            days = int(match.group(1))
            if 0 < days <= 730:
                deadline = current_day + dt.timedelta(days=days)
                add(deadline.isoformat(), f"원문 기한 · 서명일 기준 {days}일 이내 후속조치")
        for match in re.finditer(
            r"\b(?:not later than|no later than|by)\s+"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2}),\s+(20\d{2})\b",
            text,
            re.I,
        ):
            add(
                f"{match.group(3)}-{_TIMELINE_MONTHS[match.group(1).lower()]:02d}-{int(match.group(2)):02d}",
                "원문 명시 후속조치 기한",
            )

    # For non-official coverage, do not promote the article date to a signing date.
    if not events and published_day:
        add(
            published_day.isoformat(),
            "보도 기준 현재 사건 · 행정명령 서명일·연방관보 일자는 공식 원문 확인 필요",
        )

    if not events:
        return []

    events.sort(key=lambda item: item[0])
    lines = ["- 타임라인:"]
    for day, detail in events[:8]:
        lines.append(f"  • {_timeline_ko_date(day)}: {detail}")
    return lines


def validate_final_policy_message(title: str, body: str) -> list[str]:
    errors: list[str] = []
    combined = f"{title}\n{body}"
    plain_combined = re.sub(r"<[^>]+>", "", combined)
    if (
        "대미투자 | 내용 변화" in plain_combined
        and "자동 용량 계산" in plain_combined
        and "AP1000" in plain_combined
        and "APR1400" in plain_combined
    ):
        errors.append("legacy_us_investment_article_led_format")
    if re.search(r"미분류\s*-\d+\s*기", plain_combined):
        errors.append("negative_unclassified_reactor_count")
    total8 = bool(re.search(r"(?:전체|총)\s*8\s*기|원전\s*(?:최대\s*)?8\s*기", plain_combined))
    ap8 = bool(re.search(r"AP1000[^\\n]{0,80}\\b8\s*기", plain_combined, re.I))
    apr8 = bool(re.search(r"APR1400[^\\n]{0,80}\\b8\s*기", plain_combined, re.I))
    if total8 and ap8 and apr8:
        errors.append("reactor_composition_double_count")
    if re.search(r"APR1400[^\\n]{0,80}2\s*기\s*(?:→|->|에서)\s*8\s*기", plain_combined, re.I):
        errors.append("unsupported_apr1400_2_to_8_transition")
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
        if "…" in core or re.search(r"\.{3,}", core):
            errors.append("policy_core_truncated")
        if re.search(r"(?:\s(?:상|하향)|Elon Musk|Autonomous Systems|\d+(?:MHz|GHz)와)입니다\.$", core):
            errors.append("policy_core_nominal_fragment")
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- 출처:"):
            continue
        anchors = list(HTML_SOURCE_LINK_RE.finditer(stripped))
        if len(anchors) != 1 or anchors[0].group("label").strip() != "원문":
            errors.append("source_link_not_single_html_anchor")
            continue
        visible = HTML_SOURCE_LINK_RE.sub("", stripped)
        if re.search(r"\[[^\]]+\]\(https?://", stripped) or re.search(r"https?://", visible):
            errors.append("source_link_raw_or_markdown_url_present")
        if "원문 보기" in stripped or "원문뉴스보기" in stripped:
            errors.append("source_link_verbose_label_present")
    if presidential_action_timeline_required(plain_combined):
        if "- 타임라인:" not in plain_combined:
            errors.append("presidential_action_timeline_missing")
        elif not re.search(
            r"(?m)^\s*[•·]\s*20\d{2}년\s*\d{1,2}월\s*\d{1,2}일\s*:",
            plain_combined,
        ):
            errors.append("presidential_action_timeline_has_no_dated_event")
    if extract_foreign_amounts(combined):
        errors.append("foreign_currency_not_converted")
    return errors

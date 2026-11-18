"""Alias narrowly verified reprints to keys already delivered by this watch.

Evidence: run 43862615845 (2026-11-16), report entries 1/5/6/7/8,
Telegram receipts 374/375. Recreating the sender's 3500-character chunks
matched both receipt SHA256 values. All five keys below already exist in
the pending state's seen set; the first is the canonical key, not a new key.

Only the key function is wrapped. No queries, recovery rows, state migration,
selection, scoring, scheduling, recipient or delivery changes are made.
Unknown descriptions and other dates deliberately retain the upstream key.
Explicit material follow-ups get a distinct key only if the upstream key
collides with one of the five verified deliveries (the upstream fallback
currently ignores descriptions). This does not promote their source grade.

The Nov-16 first delivery's original article already disclosed Jupiter Power,
16 GWh, three years from 2029, and cumulative 27 GWh. These are the same
contract, not newly revealed customer/quantity or primary-source upgrades:
https://www.fnnews.com/news/202611161821561260
https://www.samsungsdi.co.kr/sdi-now/sdi-news/5101.html
https://news.samsungsdi.com/global/articleView?seq=477
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import re
import unicodedata
from urllib.parse import urlparse
from urllib.parse import parse_qs

DELIVERED_KEYS = (
    "74b8af0633e381675eceda39d2b49eecea704846622d7dc2021c7de98fb923bb",
    "97a6e31a218129c4139622a50124c18e671de9f929737d63b888a7beeb68b757",
    "6cfce30fa10d0f1ea8475144bfdc3a2d4fe27f50d3b5563a8b81c2b218a5c766",
    "1f3a67b1011a4495ebcca54a1a7dd2793e2ceb5630fa7e8c8eb6009a022f6b1c",
    "61e7d1fb7fd206fe7af9b3d91809f38afb77356c94ee8e0c286fc872c2a031a7",
)
CANONICAL_KEY = DELIVERED_KEYS[0]
DAILYMAKER_DELIVERED_KEY = "ac27b7e72d387fde3f20c9a4332f7999192808dc66a245ac736abb38090bcb7c"
SEOUL_DELIVERED_KEY = "54b3e2e0871a6c64b7169fdbfcbcb6a0e247901555c99f76aecc651d72832be7"
HISTORICAL_EVENT_KEYS = DELIVERED_KEYS + (DAILYMAKER_DELIVERED_KEY, SEOUL_DELIVERED_KEY)
EVENT_DAY = dt.date(2026, 11, 16)
REPRINT_END_DAY = dt.date(2026, 11, 18)
KST = dt.timezone(dt.timedelta(hours=9))

# Full-headline matching intentionally excludes extra customer names, exact
# amounts, quantities and verbs. A broad keyword conjunction would hide news.
_BASE_HEADLINE = re.compile(
    r"(?:탈중국앞세운)?삼성sdi"
    r"(?:미국(?:에서|서)?수조원대|수조원대미국(?:에서|서)?)"
    r"ess(?:배터리)?(?:수주|공급계약)(?:lfp로영역확장)?"
)
_KNOWN_STOCK_HEADLINE = "삼성sdi수조원대ess배터리수주에상승세"
_KNOWN_DAILYMAKER_HEADLINE = "북미ess시장뭉칫돈삼성sdi16gwh공급계약"
_KNOWN_SEOUL_HEADLINE = "삼성sdi미국lfp양산하자마자4조대형수주ess공급망넓힌다"
_JUPITER = re.compile(r"주피터\s*파워|Jupiter\s*Power", re.I)
_VOLUME = re.compile(r"(?<![\d.])([\d,]+(?:\.\d+)?)\s*(GWh|MWh|기가와트시|메가와트시)", re.I)
_SIMPLE_16_HEADLINE = re.compile(
    r"삼성sdi(?:미국|북미)(?:서|에서)?(?:ess)?(?:용)?16(?:gwh|기가와트시)"
    r"(?:규모)?(?:lfp)?(?:배터리)?(?:수주|공급계약)(?:체결)?"
)
_PRIMARY_HOSTS = (
    "samsungsdi.com", "samsungsdi.co.kr", "dart.fss.or.kr", "kind.krx.co.kr",
)
_PRIMARY_SOURCE = re.compile(
    r"^(?:삼성\s*SDI|Samsung\s*SDI)(?:\s*(?:공식|뉴스룸|Newsroom))?$|"
    r"\bDART\b|\bKIND\b|전자공시|공식\s*공시", re.I,
)
_FOLLOWUP = (
    ("named_customer", re.compile(
        r"(?:신규|새로운|실명)\s*(?:고객|고객사|계약\s*상대방).{0,70}"
        r"(?:공개|확인|밝혔|확정)|"
        r"(?:고객사?\s*(?:명|이름)|계약\s*상대방).{0,60}"
        r"(?:공개|확인|밝혔|확정)|"
        r"(?:customer|counterparty).{0,60}(?:named|revealed|disclosed)", re.I)),
    ("quantified_contract", re.compile(
        r"(?:계약\s*금액|계약\s*물량|공급\s*물량).{0,35}"
        r"\d[\d,.]*\s*(?:조\s*원|억\s*원|만\s*달러|억\s*달러|GWh|MWh)"
        r".{0,35}(?:공개|확정|체결)|"
        r"\d[\d,.]*\s*(?:조\s*원|억\s*원|GWh|MWh).{0,35}"
        r"(?:새로\s*공개|첫\s*공개|공개|확정)|"
        r"(?:contract\s*(?:value|volume)|supply\s*volume).{0,50}"
        r"\d[\d,.]*\s*(?:billion|million|GWh|MWh)", re.I)),
    ("additional_order", re.compile(
        r"추가\s*(?:수주|공급\s*계약|계약).{0,25}(?:체결|확보|따냈|성사)|"
        r"(?:additional|follow[- ]on)\s+(?:order|supply\s*contract)"
        r".{0,25}(?:signed|secured|confirmed)", re.I)),
    ("delivery", re.compile(
        r"(?:첫\s*|초도\s*|실제\s*)?(?:납품|출하|검수).{0,12}"
        r"(?:완료|개시|시작)|매출\s*인식.{0,10}(?:개시|시작)|"
        r"(?:first\s+)?(?:deliveries|shipments).{0,15}(?:began|started|completed)", re.I)),
    ("official_confirmation", re.compile(
        r"공식\s*(?:발표|공시).{0,40}(?:확정|체결|확인|공개)|"
        r"(?:확정|체결).{0,30}공식\s*(?:발표|공시)|"
        r"official\s*(?:filing|confirmation|announcement)", re.I)),
)
_NOT_ACHIEVED = re.compile(
    r"미공개|미확정|미확인|미체결|공개되지|공개하지|확인되지|확정되지|"
    r"확정하지|체결되지|없다|없음|않았|못했|예정|계획|목표|검토|협의|기대|"
    r"가능성|전망|의향|잠정|부인|\b(?:not|no|will|planned|planning|may|could)\b",
    re.I,
)


def _plain(value: object) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text)).strip()


def _compact(value: object) -> str:
    text = unicodedata.normalize("NFKC", _plain(value)).casefold()
    text = re.sub(r"^\[(?:et)?특징주\]\s*", "", text)
    text = text.replace("脫", "탈").replace("美", "미국")
    text = re.sub(r"[^a-z0-9가-힣]", "", text)
    return text.replace("samsungsdi", "삼성sdi").replace("에너지저장장치", "ess")


def _headline(item: dict) -> str:
    title, source = _plain(item.get("title")), _plain(item.get("source"))
    if source:
        title = re.sub(r"\s+-\s+" + re.escape(source) + r"\s*$", "", title, flags=re.I)
    return _compact(title)


def _day(item: dict) -> dt.date | None:
    value = item.get("published")
    if not value:
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            return None
    try:
        stamp = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if stamp.tzinfo is None:
        return None  # An unknown time zone is not proof of the event date.
    return stamp.astimezone(KST).date()


def _primary(item: dict) -> bool:
    if _PRIMARY_SOURCE.search(_plain(item.get("source"))):
        return True
    if any(item.get(field) for field in ("primary_feed", "official_source", "primary_source")):
        return True
    for field in ("link", "source_url", "original_url", "canonical_url"):
        try:
            host = (urlparse(str(item.get(field) or "")).hostname or "").casefold()
        except ValueError:
            continue
        if any(host == name or host.endswith("." + name) for name in _PRIMARY_HOSTS):
            return True
    return False


def _redundant_description(item: dict, title: str) -> bool:
    source = _compact(item.get("source"))
    # Normal Google News RSS descriptions repeat the title and publisher.
    # Anything else may contain a newly named customer or contractual detail.
    allowed = {"", title, title + source, title + source + source, source + title}
    return all(_compact(item.get(field)) in allowed for field in
               ("description", "summary", "body", "content", "article_text"))


def _followup_stages(text: str) -> list[str]:
    stages = []
    for name, pattern in _FOLLOWUP:
        for match in pattern.finditer(text):
            near = text[max(0, match.start() - 14):match.end() + 16]
            if not _NOT_ACHIEVED.search(near):
                stages.append(name)
                break
    return stages


def _baseline_url(item: dict) -> bool:
    for field in ("link", "source_url", "original_url", "canonical_url"):
        try:
            parsed = urlparse(str(item.get(field) or ""))
        except ValueError:
            continue
        if parsed.hostname in {"www.fnnews.com", "fnnews.com"} and parsed.path == "/news/202611161821561260":
            return True
        if parsed.hostname in {"www.samsungsdi.co.kr", "samsungsdi.co.kr"} and parsed.path == "/sdi-now/sdi-news/5101.html":
            return True
        if parsed.hostname == "news.samsungsdi.com" and parsed.path == "/global/articleView" and parse_qs(parsed.query).get("seq") == ["477"]:
            return True
        if parsed.hostname in {"www.seouleconews.com", "seouleconews.com"} and parsed.path == "/news/articleView.html" and parse_qs(parsed.query).get("idxno") == ["95029"]:
            return True
        if parsed.hostname in {"www.hankyung.com", "hankyung.com"} and parsed.path == "/article/2026111601571":
            return True
    return False


def _jupiter_baseline(item: dict, previous_key: str, title: str, text: str) -> str | None:
    """Return same/changed only for the independently verified Nov-16 deal."""
    combined = _plain(item.get("title")) + " " + text
    compact = _compact(combined)
    if "삼성sdi" not in compact or not re.search(r"ess|bess|lfp|리튬인산철", compact):
        return None
    known_daily = (title == _KNOWN_DAILYMAKER_HEADLINE and
                   previous_key == DAILYMAKER_DELIVERED_KEY)
    known_seoul = title == _KNOWN_SEOUL_HEADLINE and previous_key == SEOUL_DELIVERED_KEY
    named_in_title = bool(_JUPITER.search(_plain(item.get("title"))))
    known_headline = bool(_BASE_HEADLINE.fullmatch(title) or _SIMPLE_16_HEADLINE.fullmatch(title))
    named = bool(_JUPITER.search(combined))
    volumes = []
    for match in _VOLUME.finditer(combined):
        value = float(match.group(1).replace(",", ""))
        if match.group(2).casefold() in {"mwh", "메가와트시"}:
            value /= 1000
        volumes.append((value, match))
    has_16 = any(value == 16 for value, _ in volumes)
    period = bool(re.search(r"2029\s*년?\s*(?:부터.{0,35}3\s*년|[~–—-]\s*2031)|"
                            r"three\s+years\s+(?:starting|from)\s+(?:in\s+)?2029", combined, re.I))
    cumulative = bool(re.search(r"(?:누적|합계|총|total).{0,45}27\s*(?:GWh|기가와트시)", combined, re.I))
    historical_facts = (previous_key in DELIVERED_KEYS and known_headline and
                        (named or bool(volumes) or "named_customer" in _followup_stages(combined) or
                         re.search(r"(20\d{2})\s*년?\s*부터|(?:공급\s*대상|계약\s*상대방|고객사)\s*(?:은|는|:)", combined)))
    verified = known_daily or known_seoul or historical_facts or _baseline_url(item) or (
        named and (named_in_title or known_headline) and (has_16 or (period and cumulative)))
    if not verified:
        return None

    # Do not let historical Jupiter context consume a different new customer.
    for match in re.finditer(r"(?:고객사|계약\s*상대방|공급\s*대상)\s*(?:은|는|:)\s*([^,.;。]{1,80})|"
                             r"(?:customer\s+is|agreement\s+with|contract\s+with)\s+([^,.;]{1,80})", combined, re.I):
        if not _JUPITER.search(match.group(1) or match.group(2)):
            return "changed"
    for _, pattern in _FOLLOWUP[:1]:
        for match in pattern.finditer(combined):
            near = combined[max(0, match.start() - 14):match.end() + 16]
            if not _JUPITER.search(match.group(0)) and not _NOT_ACHIEVED.search(near):
                return "changed"
    if re.search(r"별도\s*(?:계약|수주)|다른\s*고객|계약\s*(?:변경|해지|취소|철회)|"
                 r"공급\s*(?:기간|일정).{0,25}(?:변경|연장|단축|지연)|"
                 r"(?:amended|terminated|cancelled|separate)\s+(?:supply\s+)?contract", combined, re.I):
        return "changed"
    if any(stage in {"additional_order", "delivery"} for stage in _followup_stages(combined)):
        return "changed"
    for value, match in volumes:
        if value in {16, 27}:
            continue
        # The same official release also reports Jupiter's development pipeline;
        # these are not Samsung's contract quantities.
        near = combined[max(0, match.start() - 70):match.end() + 90]
        if value == 11 and re.search(r"앞서|기존|이전|previous|earlier", near, re.I):
            continue
        if value == 1 and re.match(r"\s*당", combined[match.end():]):
            continue  # A press estimate's unit-price denominator is not an order.
        if value in {19.7, 110} and re.search(r"project|operating|construction|development|개발|프로젝트", near, re.I):
            continue
        return "changed"
    monetary_text = combined
    # Nov-16 reports already estimated 3~4 trillion KRW; Seoul's 4-trillion
    # headline is not a disclosed contract price. Only remove that quoted band
    # when it is explicitly an estimate, not an official price confirmation.
    for match in list(re.finditer(r"3\s*조\s*[~∼–—-]\s*4\s*조\s*원?", monetary_text)):
        near = monetary_text[max(0, match.start() - 35):match.end() + 45]
        if re.search(r"추산|추정|알려|업계", near) and not re.search(r"(?:공식|회사).{0,20}(?:확정|공개)|공시", near):
            monetary_text = monetary_text[:match.start()] + " " * (match.end() - match.start()) + monetary_text[match.end():]
    if re.search(r"\d[\d,.]*\s*(?:조\s*원|억\s*원|billion\s*(?:USD|dollars)|million\s*(?:USD|dollars))", monetary_text, re.I):
        return "changed"  # The baseline disclosed only an estimated trillions band.
    for match in re.finditer(r"(20\d{2})\s*년?\s*부터|(?:starting\s+(?:in\s+)?|from\s+)(20\d{2})", combined, re.I):
        if int(match.group(1) or match.group(2)) != 2029:
            return "changed"
    for match in re.finditer(r"(20\d{2})\s*년?\s*[~–—-]\s*(20\d{2})", combined):
        if (int(match.group(1)), int(match.group(2))) != (2029, 2031):
            return "changed"
    for match in re.finditer(r"(?<!\d)(20\d{2})(?!\d)", combined):
        year = int(match.group(1))
        near = combined[max(0, match.start() - 30):match.end() + 35]
        if year not in {2026, 2029, 2030, 2031} and re.search(r"공급|납품|계약|부터|starting|from|through|until", near, re.I):
            return "changed"
    for match in re.finditer(r"(?<!\d)(\d{1,2})\s*년\s*(?:간|공급|계약)|\b(\d+)\s+years?\b", combined, re.I):
        if int(match.group(1) or match.group(2)) != 3:
            return "changed"
    if re.search(r"\b(?:one|two|four|five|six|seven|eight|nine|ten)\s+years?\b", combined, re.I):
        return "changed"
    return "same"


def _followup_key(item: dict, title: str, text: str, stages: list[str]) -> str:
    identity = "|".join(("verified-delivery-followup", CANONICAL_KEY,
                         ",".join(stages), title, text.casefold()))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def verified_key(item: dict, previous_key: str) -> str:
    """Return a verified alias or preserve the complete upstream key."""
    day = _day(item)
    if day is None or not EVENT_DAY <= day <= REPRINT_END_DAY:
        return previous_key
    title = _headline(item)
    text = " ".join(_plain(item.get(field)) for field in
                    ("description", "summary", "body", "content", "article_text"))
    baseline = _jupiter_baseline(item, previous_key, title, text)
    if baseline == "same":
        return CANONICAL_KEY
    if baseline == "changed":
        return (_followup_key(item, title, text, ["jupiter_contract_changed"])
                if previous_key in HISTORICAL_EVENT_KEYS else previous_key)
    known_stock = title == _KNOWN_STOCK_HEADLINE and previous_key in DELIVERED_KEYS
    if not (_BASE_HEADLINE.fullmatch(title) or known_stock):
        return previous_key
    if not _plain(item.get("source")):
        return previous_key

    # Nov-16 was already company-confirmed. Source grade or another generic
    # confirmation is not a new event without changed contractual facts.
    stages = [stage for stage in _followup_stages(text) if stage != "official_confirmation"]
    if stages:
        if previous_key not in HISTORICAL_EVENT_KEYS:
            return previous_key
        # Existing title-only keys can otherwise hide a real description-only
        # upgrade. Derive the key from the new evidence, not from feed order.
        return _followup_key(item, title, text, stages)
    if not _redundant_description(item, title):
        return previous_key
    return CANONICAL_KEY


def install(base) -> None:
    previous = base.key
    if getattr(previous, "_verified_delivery_aliases", False):
        return

    def key(item: dict) -> str:
        return verified_key(item, previous(item))

    key._verified_delivery_aliases = True
    base.key = key

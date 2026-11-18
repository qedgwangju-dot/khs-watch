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
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import re
import unicodedata
from urllib.parse import urlparse

DELIVERED_KEYS = (
    "74b8af0633e381675eceda39d2b49eecea704846622d7dc2021c7de98fb923bb",
    "97a6e31a218129c4139622a50124c18e671de9f929737d63b888a7beeb68b757",
    "6cfce30fa10d0f1ea8475144bfdc3a2d4fe27f50d3b5563a8b81c2b218a5c766",
    "1f3a67b1011a4495ebcca54a1a7dd2793e2ceb5630fa7e8c8eb6009a022f6b1c",
    "61e7d1fb7fd206fe7af9b3d91809f38afb77356c94ee8e0c286fc872c2a031a7",
)
CANONICAL_KEY = DELIVERED_KEYS[0]
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


def verified_key(item: dict, previous_key: str) -> str:
    """Return a verified alias or preserve the complete upstream key."""
    day = _day(item)
    if day is None or not EVENT_DAY <= day <= REPRINT_END_DAY:
        return previous_key
    title = _headline(item)
    known_stock = title == _KNOWN_STOCK_HEADLINE and previous_key in DELIVERED_KEYS
    if not (_BASE_HEADLINE.fullmatch(title) or known_stock):
        return previous_key
    if not _plain(item.get("source")):
        return previous_key

    text = " ".join(_plain(item.get(field)) for field in
                    ("description", "summary", "body", "content", "article_text"))
    stages = _followup_stages(text)
    primary = _primary(item)
    if stages or primary:
        if previous_key not in DELIVERED_KEYS:
            return previous_key
        # Existing title-only keys can otherwise hide a real description-only
        # upgrade. Derive the key from the new evidence, not from feed order.
        identity = "|".join((
            "verified-delivery-followup", CANONICAL_KEY,
            ",".join(stages) or "primary_source", title, text.casefold(),
            _plain(item.get("source")).casefold() if primary else "",
        ))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()
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

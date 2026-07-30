from __future__ import annotations

import re
from models import Document, Finding

FUND_RE = re.compile(r"SVIC\s*(?:제|No\.?\s*)?(82|83)\s*호?", re.I)
AMOUNT_RE = re.compile(r"((?:USD|KRW|EUR|JPY|\$|₩)?\s?[\d,.]+\s?(?:억\s?원|만\s?원|원|million|billion)?)", re.I)
EVENTS = {
    "confirmed_investment": ("투자", "출자", "investment", "invested"),
    "investment_terms": ("지분", "investment amount", "stake", "funding round"),
    "samsung_validation": ("공동개발", "PoC", "고객 인증", "sample evaluation"),
    "mass_production": ("양산", "공정 적용", "제품 탑재", "mass production"),
    "failure": ("투자 철회", "손상차손", "검증 실패", "impairment", "withdrawal"),
    "follow_on_or_mna": ("후속 투자", "인수", "합병", "acquisition", "merger"),
}


def parse_document(doc: Document) -> list[Finding]:
    text = f"{doc.title}\n{doc.body}"
    fund = FUND_RE.search(text)
    event_type = next((event for event, terms in EVENTS.items() if any(term.casefold() in text.casefold() for term in terms)), None)
    if not event_type:
        return []
    # A candidate may be stored, but an 82/83 confirmation requires a named official source.
    confirmed = bool(fund and doc.official)
    company = _company_hint(doc.title)
    amount = AMOUNT_RE.search(text)
    return [Finding(
        company_name_original=company,
        event_type=event_type,
        announcement_date=doc.published_at[:10],
        source_urls=[doc.url],
        summary=doc.title,
        related_fund=f"SVIC {fund.group(1)}호" if fund else "",
        fund_confirmation_status="confirmed" if confirmed else "candidate",
        investment_amount_original=amount.group(1).strip() if amount else "",
        official_source_exists=doc.official,
        confidence_level="confirmed" if confirmed else ("expected" if doc.official else "review"),
        details={"source": doc.source, "reliability": doc.reliability},
    )]


def _company_hint(title: str) -> str:
    for separator in (" - ", " | ", "…", ":"):
        if separator in title:
            return title.split(separator, 1)[0].strip()[:120]
    return title.strip()[:120] or "기업명 확인 필요"


from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Document:
    source: str
    url: str
    title: str
    published_at: str
    body: str
    official: bool
    reliability: float
    fetched_at: str = field(default_factory=utc_now)

    @property
    def content_hash(self) -> str:
        normalized = "\n".join((self.url.strip(), self.title.strip(), self.published_at.strip(), self.body.strip()))
        return sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class Finding:
    company_name_original: str
    event_type: str
    announcement_date: str
    source_urls: list[str]
    summary: str
    related_fund: str = ""
    fund_confirmation_status: str = "candidate"
    investment_amount_original: str = ""
    official_source_exists: bool = False
    confidence_level: str = "review"
    details: dict = field(default_factory=dict)

    @property
    def alert_hash(self) -> str:
        stable = {
            "company": self.company_name_original.casefold().strip(),
            "event": self.event_type,
            "date": self.announcement_date,
            "amount": self.investment_amount_original.strip(),
            "summary": " ".join(self.summary.casefold().split()),
            "urls": sorted(url.strip() for url in self.source_urls),
        }
        return sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

"""Conservative verification of claimed federal AI incident-reporting instruments.

News headlines and RSS source names are not legal instruments.
Fetch official Federal Register metadata before calling a candidate enacted.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request
from urllib.parse import urlparse


FORMAL_STAGES = {"rule_proposal", "rule_final", "executive_instrument"}
GOV_SOURCES = {
    "Federal Register",
    "GovInfo",
    "U.S. Government Publishing Office",
    "The White House",
    "White House",
}


def _actual_regulatory_subject(text: str) -> bool:
    lower = " ".join(text.lower().split())
    return (
        any(x in lower for x in (
            "artificial intelligence", "ai model", "frontier model",
            "super intelligence", "superintelligence",
        ))
        and any(x in lower for x in (
            "model incident", "ai incident", "security incident",
            "incident reporting", "incident notification",
            "reporting of incidents",
        ))
    )


def _fetch_fr_document(document_number: str) -> dict:
    url = (
        "https://www.federalregister.gov/api/v1/documents/"
        + document_number + ".json"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "khs-si-regulation-validator/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def verify_formal_instrument(stage: str, row: dict, *, fetch_document=None) -> tuple[bool, str, str]:
    """Validate a proposal/final rule/EO and return (ok, official URL, reason).

    A false result MUST NOT be translated into a regulatory alert. A confirmed
    Axios statement is a separate non-regulatory stage.
    """
    if stage not in FORMAL_STAGES:
        return True, row.get("link", ""), "Non-regulatory stage"

    source = row.get("source", "")
    text = " ".join([
        str(row.get("title") or ""),
        str(row.get("description") or ""),
        str(row.get("text") or ""),
    ])
    if source not in GOV_SOURCES or not _actual_regulatory_subject(text):
        return False, "", "Official source and incident subject not verified"

    match = re.search(r"(?<!\d)(20\d{2}-\d{4,7})(?!\d)", text)
    if not match:
        return False, "", "Missing Federal Register document number"
    number = match.group(1)

    try:
        fetch = fetch_document or _fetch_fr_document
        document = fetch(number)
    except Exception as exc:
        return False, "", "Official Federal Register lookup failed: " + type(exc).__name__

    if not isinstance(document, dict) or str(document.get("document_number")) != number:
        return False, "", "Official document identifier mismatch"
    doc_type = str(document.get("type") or "")
    if stage == "rule_final" and doc_type != "Rule":
        return False, "", "Not an official final rule"
    if stage == "rule_proposal" and doc_type != "Proposed Rule":
        return False, "", "Not an official proposed rule"
    if stage == "executive_instrument" and doc_type != "Presidential Document":
        return False, "", "Not an official presidential instrument"

    official_text = " ".join(str(document.get(k) or "") for k in ("title", "abstract", "action"))
    if not _actual_regulatory_subject(official_text):
        return False, "", "Official document does not confirm AI incident reporting"
    date = str(document.get("publication_date") or "")
    try:
        published = dt.date.fromisoformat(date)
    except ValueError:
        return False, "", "Official publication date missing"
    if published > dt.datetime.now(dt.timezone.utc).date():
        return False, "", "Official document has future publication date"

    url = str(document.get("html_url") or "")
    host = (urlparse(url).hostname or "").lower()
    if host not in {"www.federalregister.gov", "federalregister.gov"}:
        return False, "", "Official publication URL not independently verified"
    return True, url, "Federal Register original record verified"

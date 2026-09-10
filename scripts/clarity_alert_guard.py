#!/usr/bin/env python3
import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"

STRICT_CRYPTO_RE = re.compile(
    r"(?:\bCLARITY\b|H\.?\s*R\.?\s*3633|digital\s+asset(?:s)?|digital\s+commodit(?:y|ies)|"
    r"crypto(?:-|\s*)asset(?:s)?|cryptocurrency|stablecoin(?:s)?|blockchain|"
    r"tokeni[sz](?:ed|ation)|tokenized\s+securit(?:y|ies)|decentralized\s+finance|\bDeFi\b|"
    r"virtual\s+currenc(?:y|ies)|non-security\s+crypto)",
    re.I,
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-CLARITY-Watch/3.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def url_works(url):
    if not url:
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= getattr(r, "status", 200) < 400
    except Exception:
        return False


def document_number(event):
    for value in (event.get("url", ""), event.get("title", ""), event.get("detail", "")):
        m = re.search(r"\b(20\d{2}-\d{4,6})\b", clean(value))
        if m:
            return m.group(1)
    return ""


def flatten_topics(meta):
    values = []
    for key in ("topics", "agency_names", "docket_ids", "regulation_id_numbers"):
        item = meta.get(key)
        if isinstance(item, list):
            for x in item:
                if isinstance(x, dict):
                    values.extend(clean(v) for v in x.values())
                else:
                    values.append(clean(x))
        elif item:
            values.append(clean(item))
    return " ".join(values)


def classify_rule_type(meta, source):
    raw = clean(meta.get("type") or source).lower()
    if "proposed" in raw or "prorule" in raw or "제안규칙" in source:
        return "SEC·CFTC 제안규칙"
    if raw == "rule" or "final rule" in raw or "최종규칙" in source:
        return "SEC·CFTC 최종규칙"
    return "SEC·CFTC 공식 규칙·해석·집행지침"


def best_authoritative_url(meta, docno):
    # Prefer the readable FederalRegister.gov document page when it resolves.
    # If it does not, fall back exactly in the user's requested order: JSON -> XML -> MODS.
    candidates = [
        meta.get("html_url"),
        meta.get("json_url") or f"https://www.federalregister.gov/api/v1/documents/{docno}.json",
        meta.get("full_text_xml_url"),
        meta.get("mods_url"),
    ]
    for url in candidates:
        if url and url_works(url):
            return url
    return candidates[1] or candidates[2] or candidates[3] or candidates[0] or ""


def validate_federal_register_event(event):
    source = clean(event.get("source", ""))
    if "Federal Register" not in source:
        return event, "not_federal_register"

    docno = document_number(event)
    if not docno:
        return None, "missing_document_number"

    api_url = f"https://www.federalregister.gov/api/v1/documents/{docno}.json"
    try:
        meta = fetch_json(api_url)
    except Exception as exc:
        return None, f"metadata_fetch_failed:{exc}"

    title = clean(meta.get("title") or event.get("title"))
    abstract = clean(meta.get("abstract"))
    action = clean(meta.get("action"))
    context = " ".join([title, abstract, action, flatten_topics(meta)])

    # Critical rule: agency=SEC/CFTC is not enough. The document itself must contain
    # a strong crypto/CLARITY term in its official metadata/content description.
    if not STRICT_CRYPTO_RE.search(context):
        return None, f"irrelevant_federal_register_document:{docno}:{title}"

    checked = dict(event)
    checked["title"] = title
    checked["detail"] = abstract or action or clean(event.get("detail"))
    checked["date"] = clean(meta.get("publication_date") or event.get("date"))
    checked["event_type"] = classify_rule_type(meta, source)
    checked["url"] = best_authoritative_url(meta, docno)
    checked["document_number"] = docno
    checked["source_json_url"] = clean(meta.get("json_url") or api_url)
    checked["source_xml_url"] = clean(meta.get("full_text_xml_url"))
    checked["source_mods_url"] = clean(meta.get("mods_url"))
    checked["federal_register_type"] = clean(meta.get("type"))
    return checked, "validated"


def main():
    if not ALERT_JSON.exists():
        print("clarity_guard=no_alert_json")
        return

    events = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
    kept = []
    removed = []
    for event in events:
        checked, reason = validate_federal_register_event(event)
        if checked is None:
            removed.append({"title": event.get("title", ""), "url": event.get("url", ""), "reason": reason})
        else:
            kept.append(checked)

    ALERT_JSON.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = ROOT / "out" / "clarity_alert_guard_report.json"
    report.write_text(json.dumps({"kept": len(kept), "removed": removed}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clarity_guard_kept={len(kept)} removed={len(removed)}")
    for item in removed:
        print("removed=" + item["reason"])


if __name__ == "__main__":
    main()

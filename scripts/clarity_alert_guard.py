#!/usr/bin/env python3
import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"

STRICT_CRYPTO_RE = re.compile(
    r"(?:\bCLARITY\s+(?:Act|Bill|law)\b|Digital\s+Asset\s+Market\s+Clarity\s+Act|H\.?\s*R\.?\s*3633|"
    r"digital\s+asset(?:s)?|digital\s+commodit(?:y|ies)|crypto(?:-|\s*)asset(?:s)?|cryptocurrency|"
    r"stablecoin(?:s)?|blockchain|tokeni[sz](?:ed|ation)|tokenized\s+securit(?:y|ies)|"
    r"decentralized\s+finance|\bDeFi\b|virtual\s+currenc(?:y|ies)|non-security\s+crypto)",
    re.I,
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-CLARITY-Watch/3.3"})
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
    raw_type = clean(meta.get("type")).lower()
    if raw_type:
        if "proposed" in raw_type or "prorule" in raw_type:
            return "SEC·CFTC 제안규칙"
        if raw_type == "rule" or "final rule" in raw_type:
            return "SEC·CFTC 최종규칙"
        return "SEC·CFTC 공식 규칙·해석·집행지침"
    if "제안규칙" in source:
        return "SEC·CFTC 제안규칙"
    if "최종규칙" in source:
        return "SEC·CFTC 최종규칙"
    return "SEC·CFTC 공식 규칙·해석·집행지침"


def source_urls(docno, publication_date, meta=None):
    meta = meta or {}
    date = clean(publication_date)
    json_url = ""
    xml_url = ""
    mods_url = ""
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", date):
        yyyy, mm, dd = date.split("-")
        json_url = f"https://www.federalregister.gov/api/v1/documents/{docno}?publication_date={date}"
        xml_url = f"https://www.federalregister.gov/documents/full_text/xml/{yyyy}/{mm}/{dd}/{docno}.xml"
        mods_url = f"https://www.govinfo.gov/metadata/granule/FR-{date}/{docno}/mods.xml"
    return {
        "html": clean(meta.get("html_url")),
        "json": json_url or clean(meta.get("json_url")) or f"https://www.federalregister.gov/api/v1/documents/{docno}.json",
        "xml": xml_url or clean(meta.get("full_text_xml_url")),
        "mods": mods_url or clean(meta.get("mods_url")),
    }


def best_authoritative_url(meta, docno, publication_date):
    urls = source_urls(docno, publication_date, meta)
    for key in ("html", "json", "xml", "mods"):
        url = urls[key]
        if url and url_works(url):
            return url, key, urls
    return urls["json"] or urls["xml"] or urls["mods"] or urls["html"] or "", "unverified", urls


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
    primary_context = " ".join([title, abstract, action])

    # HARD GATE: only direct crypto/digital-asset/CLARITY-Act language in the document's
    # own title, abstract, or action can qualify. Generic English words such as
    # "clarity" never count as the CLARITY Act.
    if not STRICT_CRYPTO_RE.search(primary_context):
        return None, f"irrelevant_federal_register_document:{docno}:{title}"

    publication_date = clean(meta.get("publication_date") or event.get("date"))
    best_url, best_kind, urls = best_authoritative_url(meta, docno, publication_date)
    source_checks = {name: bool(url and url_works(url)) for name, url in urls.items() if name != "html"}

    checked = dict(event)
    checked["title"] = title
    checked["detail"] = abstract or action or clean(event.get("detail"))
    checked["date"] = publication_date
    checked["event_type"] = classify_rule_type(meta, source)
    checked["url"] = best_url
    checked["document_number"] = docno
    checked["source_json_url"] = urls["json"]
    checked["source_xml_url"] = urls["xml"]
    checked["source_mods_url"] = urls["mods"]
    checked["source_link_kind"] = best_kind
    checked["source_checks"] = source_checks
    checked["federal_register_type"] = clean(meta.get("type"))
    checked["aux_metadata"] = flatten_topics(meta)
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

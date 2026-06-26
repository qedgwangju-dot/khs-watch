#!/usr/bin/env python3
"""Runtime compatibility patch for KHS policy watch.

The base watcher is intentionally broad. Until the Korean presidential
personnel parser is folded into the source watcher, this script injects that
parser in one visible, testable place instead of keeping a long inline patch in
the GitHub Actions YAML.
"""

from __future__ import annotations

from pathlib import Path

WATCH_PATH = Path("scripts/khs_policy_watch.py")


FEDERAL_REGISTER_CLEAN_TEXT = r'''
FEDERAL_REGISTER_BOILERPLATE_PATTERNS = [
    r"This document is also available in the following formats:",
    r"\bJSON\s+\[?Normalized attributes and metadata",
    r"\bXML\s+\[?Original full text XML",
    r"\bMODS\s+\[?Government Publishing Office metadata",
    r"\[?Normalized attributes and metadata",
    r"\[?Original full text XML",
    r"\[?Government Publishing Office metadata",
    r"More information and documentation can be found in our developer tools pages",
]


def strip_federal_register_boilerplate(value: str) -> str:
    first_index: int | None = None
    for pattern in FEDERAL_REGISTER_BOILERPLATE_PATTERNS:
        match = re.search(pattern, value, re.I)
        if match and (first_index is None or match.start() < first_index):
            first_index = match.start()
    if first_index is not None:
        value = value[:first_index]
    return value


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = strip_federal_register_boilerplate(value)
    return re.sub(r"\s+", " ", value).strip()
'''


KOREA_CONSTANTS = '''
KOREA_PRESIDENTIAL_PERSONNEL_KEYWORDS = [
    "인사 발표",
    "인사 관련",
    "인사 브리핑",
    "인사발표",
    "임명",
    "임명했습니다",
    "임명하셨습니다",
    "지명",
    "지명했습니다",
    "내정",
    "후보자",
    "대통령비서실",
    "대통령실",
    "청와대",
    "국가안보실",
]

KOREA_PRESIDENTIAL_SENIOR_ROLE_KEYWORDS = [
    "비서실장",
    "정책실장",
    "안보실장",
    "수석비서관",
    "수석",
    "대변인",
    "차장",
    "장관 후보자",
    "장관",
    "차관",
    "위원장",
    "금융위원장",
    "공정거래위원장",
    "방송통신위원장",
    "검찰총장",
    "국세청장",
    "관세청장",
    "금융감독원장",
]
'''


KOREA_PARSER = r'''
def is_korea_presidential_personnel(text: str) -> bool:
    has_personnel_action = any(keyword in text for keyword in KOREA_PRESIDENTIAL_PERSONNEL_KEYWORDS)
    has_senior_role = any(keyword in text for keyword in KOREA_PRESIDENTIAL_SENIOR_ROLE_KEYWORDS)
    return has_personnel_action and has_senior_role


def parse_korea_president_html(text: str, source: Source) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    date_pattern = re.compile(r"\b20\d{2}[.-]\d{1,2}[.-]\d{1,2}\b")
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        if len(title) < 4 or "인사" not in title:
            continue
        link = urllib.parse.urljoin(source.url, html.unescape(match.group("href")))
        link_lower = link.lower()
        if "president.go.kr" not in link_lower and "korea.kr" not in link_lower:
            continue
        context = clean_text(text[max(0, match.start() - 350): match.end() + 1000])
        detail_text, detail_error = fetch_text(link)
        detail_clean = clean_text(detail_text or "") if not detail_error else ""
        haystack = f"{title} {context} {detail_clean[:6000]}"
        if not is_korea_presidential_personnel(haystack):
            continue
        date_match = date_pattern.search(haystack)
        published = parse_date(date_match.group(0)) if date_match else None
        if not published:
            continue
        published = published.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        summary = clean_text(detail_clean[:700] or context[:700])
        deduped[link] = {
            "source": source.name,
            "title": title,
            "link": link,
            "summary": summary or f"{source.name} official personnel briefing: {title}",
            "published_kst": published.isoformat(),
        }
    return list(deduped.values())[:20]
'''


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"Patch anchor not found: {old[:80]!r}")
    return text.replace(old, new, 1)


def patch_federal_register_boilerplate(text: str) -> str:
    if "FEDERAL_REGISTER_BOILERPLATE_PATTERNS" in text:
        return text
    return replace_once(
        text,
        r'''

def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()
''',
        "\n\n" + FEDERAL_REGISTER_CLEAN_TEXT,
    )


def patch_watch_source(text: str) -> str:
    text = patch_federal_register_boilerplate(text)
    if "korea_presidential_personnel" in text:
        return text

    text = replace_once(text, "\nSTAGE_KEYWORDS = {", KOREA_CONSTANTS + "\nSTAGE_KEYWORDS = {")
    text = replace_once(
        text,
        '    "company_filing": [\n',
        '    "korea_presidential_personnel": [\n'
        '        *KOREA_PRESIDENTIAL_PERSONNEL_KEYWORDS,\n'
        '        *KOREA_PRESIDENTIAL_SENIOR_ROLE_KEYWORDS,\n'
        '    ],\n'
        '    "company_filing": [\n',
    )
    text = replace_once(
        text,
        '\nBSEE_STATIC_EXCLUDE = ["approval process", "forms", "about", "faq", "data center", "statistics"]',
        '\nSECTOR_KEYWORDS["한국 대통령실/고위급 인사"] = [\n'
        '    "대통령비서실", "대통령실", "청와대", "국가안보실", "비서실장", "정책실장", "안보실장",\n'
        '    "수석비서관", "수석", "대변인", "차장", "장관", "차관", "위원장",\n'
        ']\n\n'
        'BSEE_STATIC_EXCLUDE = ["approval process", "forms", "about", "faq", "data center", "statistics"]',
    )
    text = replace_once(
        text,
        '    Source("White House proclamations", "https://www.whitehouse.gov/presidential-actions/proclamations/", "whitehouse_html"),\n',
        '    Source("White House proclamations", "https://www.whitehouse.gov/presidential-actions/proclamations/", "whitehouse_html"),\n'
        '    Source("Korea President briefings", "https://www.president.go.kr/briefings", "korea_president_html"),\n'
        '    Source("Korea Policy Briefing presidential briefings", "https://www.korea.kr/briefing/briefingHomeList.do", "korea_president_html"),\n',
    )
    text = replace_once(
        text,
        'for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):',
        'for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%Y.%m.%d"):',
    )
    text = replace_once(text, "\n\ndef parse_fcc_html", KOREA_PARSER + "\n\ndef parse_fcc_html")
    text = replace_once(
        text,
        '("court_order", "final_rule", "sanctions_tariffs_export", "presidential_action", "fda_decision")',
        '("court_order", "final_rule", "sanctions_tariffs_export", "presidential_action", "korea_presidential_personnel", "fda_decision")',
    )
    text = replace_once(
        text,
        '("court_order", "final_rule", "permit_restart", "agency_order", "presidential_action", "fcc_decision_notice")',
        '("court_order", "final_rule", "permit_restart", "agency_order", "presidential_action", "korea_presidential_personnel", "fcc_decision_notice")',
    )
    text = replace_once(
        text,
        '        elif source.kind == "whitehouse_html":\n'
        '            items = parse_whitehouse_html(text or "", source)\n'
        '        elif source.kind == "fcc_html":\n',
        '        elif source.kind == "whitehouse_html":\n'
        '            items = parse_whitehouse_html(text or "", source)\n'
        '        elif source.kind == "korea_president_html":\n'
        '            items = parse_korea_president_html(text or "", source)\n'
        '        elif source.kind == "fcc_html":\n',
    )
    text = replace_once(
        text,
        '{"rss", "courtlistener", "kind_html", "federal_register_json", "whitehouse_html", "fcc_html"}',
        '{"rss", "courtlistener", "kind_html", "federal_register_json", "whitehouse_html", "korea_president_html", "fcc_html"}',
    )
    return text


def main() -> int:
    text = WATCH_PATH.read_text(encoding="utf-8")
    patched = patch_watch_source(text)
    if patched == text:
        print("KHS policy runtime patch already present.")
        return 0
    WATCH_PATH.write_text(patched, encoding="utf-8")
    print("KHS policy runtime patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

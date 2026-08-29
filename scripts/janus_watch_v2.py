#!/usr/bin/env python3
from pathlib import Path
from urllib.parse import urlparse
import html
import re
import sys

import requests
from bs4 import BeautifulSoup
import janus_watch as base

ROOT = Path(__file__).resolve().parents[1]

base.SOURCES = [
    source for source in base.SOURCES
    if source.get("name") != "미 전쟁부 Janus 발표"
]
base.SOURCES.insert(
    2,
    {
        "name": "미 에너지부 원자로 실증 프로그램",
        "url": "https://www.energy.gov/ne/us-department-energy-reactor-pilot-program",
        "kind": "official",
    },
)

base.STATE_PATH = ROOT / "data" / "janus_watch_v2_state.json"
base.PENDING_STATE_PATH = ROOT / "out" / "janus_watch_v2_state_pending.json"
base.ALERT_PATH = ROOT / "out" / "janus_alert_v2.html"
base.STATUS_PATH = ROOT / "out" / "janus_status_v2.md"
base.ERROR_PATH = ROOT / "out" / "janus_errors_v2.log"
base.CONNECTION_TEST_PATH = ROOT / "out" / "janus_connection_test_v2.html"

_PROTECTED_TERMS = [
    "Antares Nuclear", "Antares", "BWXT Advanced Technologies", "BWXT",
    "General Atomics Electromagnetic Systems", "General Atomics",
    "Radiant Industries", "Radiant", "Westinghouse Government Services", "Westinghouse",
    "Kaleidos", "eVinci", "GA-TES", "Janus", "TRISO", "HALEU", "DOE", "NRC",
    "INL", "DOME", "R-50", "Standard Nuclear", "Centrus Energy", "Equinix", "DIU",
]

_BAD_TITLE_RE = re.compile(
    r"(?:error\s*\d+|server\s+error|that['’]?s\s+an\s+error|"
    r"please\s+try\s+again\s+later|something\s+went\s+wrong|"
    r"service\s+unavailable|access\s+denied|forbidden|captcha|"
    r"temporarily\s+unavailable|internal\s+server\s+error)",
    re.I,
)

_RADIANT_SLUG_TITLES = {
    "radiant-locks-triso-fuel-supply-through-early-2030s": "Radiant Locks TRISO Fuel Supply Through Early 2030s",
    "triso-fuel-supply": "Radiant Locks TRISO Fuel Supply Through Early 2030s",
    "buckley-space-force": "Air Force Selects Radiant to Deliver Microreactors to Buckley Space Force Base",
    "triso-fuel-inl": "Radiant Receives First TRISO Fuel Shipment at INL DOME, Clearing Path to Full-Power Testing",
    "radiant-wins-750m-janus-army-contract": "Radiant Wins $750M Contract from U.S. Army for Janus Microreactor Deployment",
    "second-haleu-allocation": "DOE Selects Radiant for Second HALEU Allocation for Buckley Space Force Base",
    "factory-site-license": "NRC Accepts Radiant R-50 Production Facility License Application for Accelerated Review",
    "kaleidos-has-left-the-building": "Kaleidos Has Left the Building and Is En Route to INL DOME",
    "kaleidos-shipped": "Kaleidos Has Left the Building and Is En Route to INL DOME",
}


def _append_error(message: str) -> None:
    base.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with base.ERROR_PATH.open("a", encoding="utf-8") as f:
        f.write(base.norm(message) + "\n")


def _is_bad_title(text: str) -> bool:
    text = base.norm(text)
    if not text or _BAD_TITLE_RE.search(text):
        return True
    if len(text) < 5 or not re.search(r"[A-Za-z가-힣]", text):
        return True
    return False


def _clean_page_title(text: str) -> str:
    text = base.norm(text)
    text = re.sub(r"\s*[|\-–—]\s*Radiant(?: Nuclear)?\s*$", "", text, flags=re.I)
    return base.norm(text)


def _title_from_detail_page(url: str) -> str:
    try:
        page = base.fetch(url)
        soup = BeautifulSoup(page, "html.parser")
        candidates = []
        for attr, value in [("property", "og:title"), ("name", "twitter:title")]:
            tag = soup.find("meta", attrs={attr: value})
            if tag and tag.get("content"):
                candidates.append(tag.get("content"))
        h1 = soup.find("h1")
        if h1:
            candidates.append(h1.get_text(" ", strip=True))
        if soup.title:
            candidates.append(soup.title.get_text(" ", strip=True))
        for candidate in candidates:
            candidate = _clean_page_title(candidate)
            if not _is_bad_title(candidate):
                return candidate
    except Exception as exc:
        _append_error(f"상세 제목 조회 실패 | {url} | {type(exc).__name__}: {exc}")
    return ""


def _title_from_slug(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1].lower()
    if slug in _RADIANT_SLUG_TITLES:
        return _RADIANT_SLUG_TITLES[slug]
    words = re.sub(r"[-_]+", " ", slug).strip()
    return words.title() if words else ""


def _resolve_event_title(event) -> str:
    title = _clean_page_title(event.get("title", ""))
    if not _is_bad_title(title):
        return title
    resolved = _title_from_detail_page(event.get("url", "")) or _title_from_slug(event.get("url", ""))
    resolved = _clean_page_title(resolved)
    if _is_bad_title(resolved):
        _append_error(
            f"오류 제목 차단 | {event.get('source','')} | {event.get('url','')} | 원문={event.get('title','')}"
        )
        return ""
    return resolved


_ORIGINAL_EXTRACT_ITEMS = base.extract_items


def _extract_items_clean(source, page_html):
    items = _ORIGINAL_EXTRACT_ITEMS(source, page_html)
    cleaned = []
    for item in items:
        title = _resolve_event_title(item)
        if not title:
            continue
        item = dict(item)
        item["title"] = title
        cleaned.append(item)
    return cleaned


base.extract_items = _extract_items_clean


def _needs_translation(text: str) -> bool:
    text = text or ""
    if not re.search(r"[A-Za-z]{2,}", text):
        return False
    stripped = text
    for term in sorted(_PROTECTED_TERMS, key=len, reverse=True):
        stripped = re.sub(re.escape(term), " ", stripped, flags=re.I)
    return bool(re.search(r"\b[A-Za-z]{3,}\b", stripped))


def _restore_known_korean(text: str) -> str:
    replacements = [
        (r"\bU\.?S\.?\s+Army\b", "미 육군"),
        (r"\bUS\s+Army\b", "미 육군"),
        (r"\bU\.?S\.?\s+Air\s+Force\b", "미 공군"),
        (r"\bAir\s+Force\b", "미 공군"),
        (r"\bDepartment\s+of\s+Energy\b", "미 에너지부"),
        (r"\bDepartment\s+of\s+the\s+Air\s+Force\b", "미 공군부"),
        (r"\bSpace\s+Force\s+Base\b", "우주군기지"),
        (r"\bMicroreactors?\b", "마이크로원자로"),
        (r"\bFuel\s+Supply\s+Agreement\b", "연료 공급계약"),
        (r"\bContract\b", "계약"),
        (r"\bFactory\b", "공장"),
        (r"\bLicense\s+Application\b", "허가 신청"),
        (r"\bProgram\b", "프로그램"),
        (r"\bDeployment\b", "배치"),
        (r"\bDeployments\b", "배치"),
        (r"\bSelects\b", "선정"),
        (r"\bSelected\b", "선정"),
        (r"미세\s*반응기", "마이크로원자로"),
        (r"소형\s*반응기", "마이크로원자로"),
        (r"마이크로\s*리액터", "마이크로원자로"),
        (r"배포", "배치"),
        (r"포트\s+드럼", "포트 드럼"),
    ]
    out = text
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.I)
    return base.norm(out)


def _translate_google_web(text: str, source: str = "en") -> str:
    params = {
        "client": "gtx",
        "sl": source,
        "tl": "ko",
        "dt": "t",
        "q": text,
    }
    r = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params=params,
        headers={"User-Agent": base.UA},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    parts = []
    for row in (data[0] if isinstance(data, list) and data else []):
        if isinstance(row, list) and row and row[0]:
            parts.append(str(row[0]))
    result = base.norm("".join(parts))
    if not result:
        raise RuntimeError("Google 웹 번역 결과가 비어 있음")
    return result


def _translate_mymemory(text: str) -> str:
    r = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": "en|ko"},
        headers={"User-Agent": base.UA},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    result = base.norm(((data.get("responseData") or {}).get("translatedText") or ""))
    if not result:
        raise RuntimeError("MyMemory 번역 결과가 비어 있음")
    return html.unescape(result)


def _translate_ko(text: str) -> str:
    raw = base.norm(text)
    if not raw:
        return raw
    if _BAD_TITLE_RE.search(raw):
        raise RuntimeError("오류 페이지 문구가 포함되어 송출 차단")
    if not _needs_translation(raw):
        return _restore_known_korean(raw)

    translated = ""
    errors = []
    try:
        translated = _translate_google_web(raw, "auto" if re.search(r"[가-힣]", raw) else "en")
    except Exception as exc:
        errors.append(f"Google={exc}")

    if not translated or _needs_translation(_restore_known_korean(translated)):
        try:
            fallback = _translate_mymemory(raw)
            if fallback:
                translated = fallback
        except Exception as exc:
            errors.append(f"MyMemory={exc}")

    translated = _restore_known_korean(base.norm(translated))
    if _BAD_TITLE_RE.search(translated):
        raise RuntimeError("오류 페이지 문구가 포함되어 송출 차단")
    if _needs_translation(translated):
        raise RuntimeError(f"설명형 영어 미번역 잔존: {translated} | {'; '.join(errors)}")
    if not re.search(r"[가-힣]", translated):
        raise RuntimeError(f"한국어 번역 결과 없음: {translated} | {'; '.join(errors)}")
    return translated


def _render_alert_korean(events, fact_changes):
    lines = ["<b>[Janus 웹감시] 신규 변화</b>", ""]
    translation_errors = []
    shown_events = 0

    for event in events[:12]:
        resolved_title = _resolve_event_title(event)
        if not resolved_title:
            continue
        try:
            title_ko = _translate_ko(resolved_title)
        except Exception as exc:
            translation_errors.append(f"{event['source']} | {event['url']} | {exc}")
            continue
        cat = base.classify(resolved_title)
        lines.extend(
            [
                f"• <b>분류:</b> {html.escape(cat)}",
                f"• <b>출처:</b> {html.escape(event['source'])}",
                f"• <b>새 사실:</b> {html.escape(title_ko)}",
                f"• <b>의미:</b> {html.escape(base.meaning(cat))}",
                f"• <a href=\"{html.escape(event['url'], quote=True)}\">원문</a>",
                "",
            ]
        )
        shown_events += 1

    shown_facts = 0
    for fc in fact_changes[:6]:
        try:
            summary_ko = _translate_ko(fc["summary"])
        except Exception as exc:
            translation_errors.append(f"{fc['source']} | {fc['url']} | {exc}")
            continue
        lines.extend(
            [
                "• <b>분류:</b> 공식 핵심 수치·당사자 변경",
                f"• <b>출처:</b> {html.escape(fc['source'])}",
                f"• <b>변경:</b> {html.escape(summary_ko)}",
                f"• <a href=\"{html.escape(fc['url'], quote=True)}\">원문</a>",
                "",
            ]
        )
        shown_facts += 1

    for err in translation_errors:
        _append_error(err)

    if shown_events + shown_facts == 0:
        return ""

    total = len(events) + len(fact_changes)
    shown = shown_events + shown_facts
    if total > shown:
        lines.append(f"• 오류·번역 미완료로 송출 보류된 항목 {total-shown}건은 다음 실행에서 재검증")
    result = "\n".join(lines).strip()
    if _BAD_TITLE_RE.search(result):
        raise RuntimeError("최종 알림에 서버 오류 문구가 남아 송출 차단")
    return result


base.render_alert = _render_alert_korean

if __name__ == "__main__":
    sys.exit(base.main())

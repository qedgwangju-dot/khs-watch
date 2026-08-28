#!/usr/bin/env python3
from pathlib import Path
import html
import re
import sys

import janus_watch as base
from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]

# war.gov is protected against GitHub-hosted runners (HTTP 403). Replace it with
# DOE's official Reactor Pilot Program page, which tracks Antares/Radiant and
# related reactor criticality/deployment milestones that can affect Janus supply.
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

# Keep v2 state/output isolated so the first successful run establishes a clean
# baseline and does not replay old Janus headlines as new alerts.
base.STATE_PATH = ROOT / "data" / "janus_watch_v2_state.json"
base.PENDING_STATE_PATH = ROOT / "out" / "janus_watch_v2_state_pending.json"
base.ALERT_PATH = ROOT / "out" / "janus_alert_v2.html"
base.STATUS_PATH = ROOT / "out" / "janus_status_v2.md"
base.ERROR_PATH = ROOT / "out" / "janus_errors_v2.log"
base.CONNECTION_TEST_PATH = ROOT / "out" / "janus_connection_test_v2.html"

_TRANSLATOR = GoogleTranslator(source="auto", target="ko")
_PROTECTED_TERMS = [
    "Janus Program",
    "Janus",
    "Antares Nuclear",
    "Antares",
    "BWXT Advanced Technologies",
    "BWXT",
    "General Atomics Electromagnetic Systems",
    "General Atomics",
    "Radiant Industries",
    "Radiant",
    "Westinghouse Government Services",
    "Westinghouse",
    "Fort Bragg",
    "Fort Campbell",
    "Fort Hood",
    "Fort Benning",
    "Fort Drum",
    "Kaleidos",
    "eVinci",
    "GA-TES",
    "TRISO",
    "HALEU",
    "DOE",
    "U.S. Army",
    "Army",
]


def _has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def _needs_translation(text: str) -> bool:
    text = text or ""
    # 번역 대상은 설명형 영문이 남아 있는 경우다. 회사명·모델명만 남는 것은 식별을 위해 허용한다.
    letters = re.findall(r"[A-Za-z]{2,}", text)
    if not letters:
        return False
    stripped = text
    for term in sorted(_PROTECTED_TERMS, key=len, reverse=True):
        stripped = re.sub(re.escape(term), " ", stripped, flags=re.I)
    return bool(re.search(r"[A-Za-z]{3,}", stripped))


def _translate_ko(text: str) -> str:
    text = base.norm(text)
    if not text or not _needs_translation(text):
        return text

    protected = {}
    work = text
    # 고유명·노형·약어는 원문 식별성을 유지하고 일반 설명어만 한국어로 바꾼다.
    for idx, term in enumerate(sorted(_PROTECTED_TERMS, key=len, reverse=True)):
        pattern = re.compile(re.escape(term), re.I)
        if pattern.search(work):
            token = f"ZXQ{idx}QXZ"
            matched = pattern.search(work).group(0)
            protected[token] = matched
            work = pattern.sub(token, work)

    try:
        translated = _TRANSLATOR.translate(work)
    except Exception as exc:
        # 영어를 그대로 송출하지 않는다. 실패 시 해당 사실은 보류하고 오류 파일에 남긴다.
        raise RuntimeError(f"한국어 번역 실패: {exc}") from exc

    for token, original in protected.items():
        translated = translated.replace(token, original)
        translated = translated.replace(token.lower(), original)

    translated = base.norm(translated)
    if _needs_translation(translated):
        # 번역기가 설명형 영어를 남긴 경우 한 번 더 번역한다.
        try:
            translated2 = _TRANSLATOR.translate(translated)
            if translated2:
                translated = base.norm(translated2)
        except Exception:
            pass

    return translated


def _render_alert_korean(events, fact_changes):
    lines = ["<b>[Janus 웹감시] 신규 변화</b>", ""]
    translation_errors = []
    shown_events = 0

    for event in events[:12]:
        try:
            title_ko = _translate_ko(event["title"])
        except Exception as exc:
            translation_errors.append(f"{event['source']} | {event['url']} | {exc}")
            continue
        cat = base.classify(event["title"])
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

    if translation_errors:
        base.OUT_DIR.mkdir(parents=True, exist_ok=True)
        with base.ERROR_PATH.open("a", encoding="utf-8") as f:
            for err in translation_errors:
                f.write(err + "\n")

    if shown_events + shown_facts == 0:
        # 번역되지 않은 영어를 보내느니 알림을 보류한다.
        return ""

    total = len(events) + len(fact_changes)
    shown = shown_events + shown_facts
    if total > shown:
        lines.append(f"• 번역 또는 표시 제한으로 보류된 항목 {total-shown}건은 다음 실행에서 재검증")
    return "\n".join(lines).strip()


# 기존 영문 제목 기반 알림 생성기를 한국어 번역 강제 버전으로 교체한다.
base.render_alert = _render_alert_korean

if __name__ == "__main__":
    sys.exit(base.main())

#!/usr/bin/env python3
"""에너지 공급감시 v32: 모든 알림의 근거 기사 제목을 한국어로 강제.

v31까지의 사건 감시·중복방지·전용 본문을 유지한다.
특정 전용 포맷이 v12의 번역 렌더러를 우회하더라도 groups의 원문 evidence 제목을
최종 본문에서 다시 한국어로 치환해 영문 기사 제목이 Telegram으로 새지 않게 한다.
"""
from __future__ import annotations

import html
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v31 as v31

v30 = v31.v30
v29 = v31.v29
v12 = v31.v12
v8 = v31.v8

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

v8.SOURCE_KO.update({
    "wsj": "월스트리트저널",
    "wall street journal": "월스트리트저널",
    "the wall street journal": "월스트리트저널",
    "reuters": "로이터",
    "bloomberg": "블룸버그",
    "yahoo finance uk": "야후 파이낸스 영국",
    "yahoo finance": "야후 파이낸스",
    "the guardian": "가디언",
})


def _strict_title(item: core.NewsItem) -> str:
    try:
        translated = v12.translate_title_ko_strict(item).strip()
        if translated and not v12._contains_untranslated_prose(translated):
            return translated
    except Exception:
        pass
    try:
        return v12.fallback_korean_title_v12(item)
    except Exception:
        return "관련 사건의 확정 변화 확인"


def _source_ko(source: str) -> str:
    try:
        return v8.source_name_ko(source)
    except Exception:
        return "주요 매체"


def _replace_evidence_text(body: str, groups) -> str:
    rendered = body
    for group in groups:
        for item in list(group.get("evidence") or []):
            raw_title = str(getattr(item, "title", "") or "").strip()
            raw_source = str(getattr(item, "source", "") or "").strip()
            if raw_title:
                translated = _strict_title(item)
                rendered = rendered.replace(html.escape(raw_title), html.escape(translated))
                rendered = rendered.replace(raw_title, translated)
            if raw_source:
                source_ko = _source_ko(raw_source)
                raw_escaped = html.escape(raw_source)
                source_escaped = html.escape(source_ko)
                patterns = (
                    (f"<b>{raw_escaped}</b>", f"<b>{source_escaped}</b>"),
                    (f"- {raw_escaped} ·", f"- {source_escaped} ·"),
                    (f"• {raw_escaped} ·", f"• {source_escaped} ·"),
                    (f"- {raw_escaped}:", f"- {source_escaped}:"),
                )
                for before, after in patterns:
                    rendered = rendered.replace(before, after)
    return rendered


def _raw_english_evidence_remaining(body: str, groups) -> list[str]:
    remaining: list[str] = []
    for group in groups:
        for item in list(group.get("evidence") or []):
            raw = str(getattr(item, "title", "") or "").strip()
            if raw and re.search(r"[A-Za-z]{2,}", raw):
                if raw in body or html.escape(raw) in body:
                    remaining.append(raw)
    return remaining


def build_regular_alert_v32(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    body = _replace_evidence_text(body, groups)
    leaks = _raw_english_evidence_remaining(body, groups)
    if leaks:
        raise RuntimeError("영문 기사 제목 송출 차단: " + " | ".join(leaks[:3]))
    metadata["version"] = 32
    metadata["global_evidence_language"] = "ko-strict-final-pass"
    metadata["english_headline_guard"] = "raw evidence title remaining => block alert generation"
    return title, body, metadata


def build_setup_test_v32(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 모든 전용 알림 포맷의 근거 기사 제목을 최종 송출 직전에 다시 한국어로 치환"
        "\n• 원문 영문 제목이 한 줄이라도 남아 있으면 알림 생성을 차단해 Telegram 영문 누출 방지"
    )
    metadata["version"] = 32
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v32
core.build_setup_test = build_setup_test_v32

if __name__ == "__main__":
    raise SystemExit(core.main())

#!/usr/bin/env python3
"""Prevent a historical U.S.-Japan yen intervention funding disclosure becoming a fresh-intervention alert.

Evidence rule: only the Fed's original 2026-09 FOMC minutes can upgrade this
specific 2026-07 intervention funding disclosure to 'officially confirmed'.
A media headline alone can never prove the funding source or a new intervention.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from functools import lru_cache

FUNDING_TOPIC = "7월 말 미·일 공동개입 재원 공개"
FUNDING_EVENT_KEY = "US_JP_2026_07_TREASURY_FUNDS_FOMC_2026_10_07"
FOMC_MINUTES_URL = "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260916.htm"
FOMC_PRESS_URL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261007a.htm"
FOMC_RELEASE_UTC = dt.datetime(2026, 10, 7, 18, 0, tzinfo=dt.timezone.utc)
FOMC_DISCLOSURE_WINDOW = dt.timedelta(hours=24)
OFFICIAL_TITLE = "미 연준 공식 확인: 7월 말 미·일 공동 엔화 개입은 미 재무부 자금으로 집행"
OFFICIAL_DESCRIPTION = (
    "연준 9월 회의록을 10월 7일 공개. 뉴욕연은은 재무부의 재정 대리인으로 집행했고 "
    "연준의 자체 자금과 시스템 공개시장계정(SOMA)은 사용하지 않았음. "
    "과거 7월 말 개입 관련 신규 공개로서 10월 신규 개입은 확인되지 않음."
)
FUNDING_HEADLINE = re.compile(
    r"fed used treasury funds to support yen in joint intervention", re.I
)
REQUIRED_MINUTES_EVIDENCE = (
    "joint u s japan intervention to support the yen in late july",
    "acting purely as fiscal agent for the u s treasury",
    "using u s treasury funds",
    "system open market account portfolio was not involved",
)


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", html.unescape(value or "").lower()))


def _is_funding_article(item) -> bool:
    title = html.unescape(item.title or "")
    if FUNDING_HEADLINE.search(title):
        return True
    lowered = (title + " " + (item.description or "")).lower()
    return (
        ("joint intervention" in lowered or "協調介入" in lowered)
        and ("yen" in lowered or "円" in lowered)
        and ("treasury funds" in lowered or ("米財務省" in lowered and "資金" in lowered))
        and ("fed" in lowered or "frb" in lowered or "連邦準備" in lowered)
        and ("used" in lowered or "not" in lowered or "投入" in lowered)
    )


def _retrospective_only(item) -> bool:
    """Discard stale commentary only when the title explicitly dates a past action.

    Fresh official disclosures and newly announced actions must not be suppressed.
    """
    title = html.unescape(item.title or "").lower()
    if not (("intervention" in title or "為替介入" in title) and
            ("yen" in title or "円" in title)):
        return False
    past = ("late july", "in july", "july intervention", "last year's intervention",
            "previous intervention", "過去の", "昨年の")
    new_action = ("today", "again", "new intervention", "fresh intervention",
                  "intervened again", "再び介入", "追加介入")
    return any(p in title for p in past) and not any(n in title for n in new_action)


def install(base) -> None:
    old_collect = base.collect_items
    old_classify = base.classify
    old_translate = base.translate_headline_to_korean
    old_build = base.build_message
    old_should_alert = base.should_alert
    old_pending_state = base.pending_state

    @lru_cache(maxsize=1)
    def minutes_verified() -> bool:
        text, error = base.fetch_text(
            FOMC_MINUTES_URL, base.USER_AGENT, timeout=13, attempts=2,
            accept="text/html,application/xhtml+xml,*/*",
        )
        if error or not text:
            base.record_source_failure(
                lane="yen_policy_fomc_evidence",
                source_name="Federal Reserve September FOMC minutes",
                source_url=FOMC_MINUTES_URL,
                error=error or "empty official source",
                checked_at=dt.datetime.now(base.KST),
            )
            return False
        plain = _normalized(re.sub(r"<[^>]+>", " ", text))
        missing = [phrase for phrase in REQUIRED_MINUTES_EVIDENCE if phrase not in plain]
        if missing:
            base.record_source_failure(
                lane="yen_policy_fomc_evidence",
                source_name="Federal Reserve September FOMC minutes content check",
                source_url=FOMC_MINUTES_URL,
                error="Required July intervention funding evidence not present",
                checked_at=dt.datetime.now(base.KST),
            )
            return False
        return True

    def classify(item):
        if item.source == "Federal Reserve" and item.link == FOMC_MINUTES_URL and item.title == OFFICIAL_TITLE:
            if minutes_verified():
                return base.ClassifiedItem(item, FUNDING_TOPIC, 4, 3, "미 연준 공식 회의록")
            return None
        if _is_funding_article(item):
            level = base.source_level(item)
            if not level:
                return None
            return base.ClassifiedItem(
                item, FUNDING_TOPIC, 3, level, base.source_group(item.source, item.text)
            )
        if _retrospective_only(item):
            return None
        return old_classify(item)

    def collect_items(current):
        items, errors = old_collect(current)
        state = base.read_state()
        previous = set(state.get("verified_event_keys") or [])
        within_window = FOMC_RELEASE_UTC <= current <= FOMC_RELEASE_UTC + FOMC_DISCLOSURE_WINDOW
        if within_window and FUNDING_EVENT_KEY not in previous and minutes_verified():
            official = base.NewsItem(
                title=OFFICIAL_TITLE,
                link=FOMC_MINUTES_URL,
                source="Federal Reserve",
                description=OFFICIAL_DESCRIPTION,
                published=FOMC_RELEASE_UTC,
            )
            if official.item_id not in {x.item_id for x in items}:
                items.append(official)
                items.sort(key=lambda x: x.published, reverse=True)
        return items, errors

    def should_alert(item, rank, state, current):
        if item.topic == FUNDING_TOPIC and FUNDING_EVENT_KEY in set(state.get("verified_event_keys") or []):
            return False
        return old_should_alert(item, rank, state, current)

    def pending_state(state, selected, current):
        out = old_pending_state(state, selected, current)
        if any(x.topic == FUNDING_TOPIC and x.source_level >= 3 for x, _rank, _groups in selected):
            existing = list(out.get("verified_event_keys") or [])
            if FUNDING_EVENT_KEY not in existing:
                existing.append(FUNDING_EVENT_KEY)
            out["verified_event_keys"] = existing[-100:]
        return out

    def translate(title, source, topic, current):
        if FUNDING_HEADLINE.search(html.unescape(title or "")):
            return ("7월 말 미·일 공동 엔화 개입에 미 재무부 자금 사용…연준 자체 자금은 미투입",
                    "official_fidelity_translation")
        return old_translate(title, source, topic, current)

    def build_message(selected, current):
        special = [(x, rank, groups) for x, rank, groups in selected if x.topic == FUNDING_TOPIC]
        if not special:
            return old_build(selected, current)
        others = [x for x in selected if x[0].topic != FUNDING_TOPIC]
        item, rank, groups = special[0]
        is_official = rank >= 3 and item.source_level == 3 and minutes_verified()
        stamp = current.astimezone(base.KST).strftime("%Y-%m-%d %H:%M:%S KST")
        published = item.item.published.astimezone(base.KST).strftime("%Y-%m-%d %H:%M KST")
        evidence_label = "공식 회의록 원문 확인" if is_official else "주요매체 원문 제목·요약 확인, 공식 회의록 검증 대기"
        title = ("🔎 엔화 정책 공식 확인 · 7월 공동개입 재원"
                 if is_official else "⚠️ 엔화 정책 사실확인 대기 · 과거 개입 재원")
        body = [
            f"조회 시각: {stamp}",
            "판정: 7월 말 기존 개입의 자금조달 방식 공개 — 10월 신규 공동개입 발생을 의미하지 않음",
            "",
            f"1) {FUNDING_TOPIC} · {'공식 확인' if is_official else '보도 단계'}",
            f"출처: {'미 연준 공식 회의록' if is_official else item.item.source} · {published}",
            "원문 번역: 7월 말 미·일 공동 엔화 개입에는 미 재무부 자금이 사용됐으며, 연준 자체 자금은 사용되지 않음",
            f"확인 범위: {evidence_label}",
            "사건 시점: 2026년 7월 말의 과거 시장개입",
            "새 정보 공개: 2026년 10월 7일 연준 9월 회의록 발표",
            "",
            "공식자료로 확인된 집행 구조" if is_official else "주요매체 보도 내용 — 공식 대조 전",
            ("• 실행: 뉴욕연방준비은행이 미 재무부의 재정 대리인으로 수행"
             if is_official else "• 보도 주장: 뉴욕연방준비은행이 미 재무부의 재정 대리인으로 수행"),
            ("• 재원: 미국 재무부 자금 (미국 국채 매각대금이라는 뜻 아님)"
             if is_official else "• 보도 주장: 미국 재무부 자금 (미국 국채 매각대금이라는 뜻 아님)"),
            ("• 미사용: 미 연준 자체 자금 및 시스템 공개시장계정(SOMA) 보유증권"
             if is_official else "• 보도 주장: 연준 자체 자금과 시스템 공개시장계정(SOMA) 보유증권 미사용"),
            "• 미국 측 투입 규모: 해당 회의록에 금액 미공개 — 추정·원화 환산 금지",
            "• 신규 개입 여부: 이번 회의록만으로는 10월 신규 개입을 확인할 수 없음",
            "",
            "시장 해석(원문 외 연결)",
            "• 자금 출처가 확인된 것이며, 오늘 엔화 숏커버나 엔캐리 청산이 새로 시작됐다는 근거는 아님",
            "• 달러/엔 실제 하락과 위험자산 동반 반응은 기존 가격·엔캐리 경보에서 별도 확인",
            "• 새로운 개입은 미·일 당국의 신규 공식 발표나 거래·실행 시점이 확인될 때만 별도 경보",
            "",
            f"교차확인: {'미 연준 공식 회의록' if is_official else item.source_group}",
        ]
        entry = {
            "item_id": item.item.item_id,
            "topic": FUNDING_TOPIC,
            "material_score": item.material_score,
            "rank": rank,
            "rank_label": "공식 확인" if is_official else "미확인 주요보도",
            "source": item.item.source,
            "source_group": "미 연준 공식 회의록" if is_official else item.source_group,
            "corroborating_groups": ["미 연준 공식 회의록" if is_official else item.source_group],
            "headline": item.item.title,
            "headline_original": item.item.title,
            "headline_ko": "7월 말 미·일 공동 엔화 개입의 자금은 미국 재무부가 제공; 연준 자체 자금 미사용",
            "headline_translation_status": "official_minutes_verified" if is_official else "context_guarded",
            "link": FOMC_MINUTES_URL if is_official else item.item.link,
            "published_at_kst": item.item.published.astimezone(base.KST).isoformat(timespec="seconds"),
            "original_intervention_period": "2026-07 말",
            "funding_disclosure_date": "2026-10-07",
            "fresh_intervention": False,
            "evidence_scope": "federal_reserve_official_minutes_verified" if is_official else "news_headline_only",
            "source_translation_separated_from_market_interpretation": True,
        }
        payload = {"items": [entry], "fresh_intervention": False,
                   "verification_method": "FOMC minutes full-text multi-phrase check; no historical/new event conflation",
                   "original_event_key": FUNDING_EVENT_KEY}
        if others:
            other_title, other_body, other_payload = old_build(others, current)
            lines = other_body.splitlines()
            if len(lines) > 2 and lines[0].startswith("조회 시각:"):
                lines = lines[2:]
            body += ["", "별도 신규 정책 촉매", *lines]
            payload["items"].extend(other_payload.get("items") or [])
            payload["also_live_catalysts"] = True
        return title, "\n".join(body), payload

    base.collect_items = collect_items
    base.classify = classify
    base.should_alert = should_alert
    base.pending_state = pending_state
    base.translate_headline_to_korean = translate
    base.build_message = build_message
    return None

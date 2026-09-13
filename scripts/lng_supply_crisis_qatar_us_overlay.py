#!/usr/bin/env python3
"""QatarEnergy의 미국 LNG 장기조달·포트폴리오 다변화 조기경보 오버레이."""
from __future__ import annotations

import hashlib

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v12 as v12

# 카타르의 '공급차질' 자체뿐 아니라, 공급부족을 메우기 위해 미국 장기물량을 사들이는
# 구조적 포트폴리오 재편을 별도 사건으로 포착한다.
QATAR_US_LNG_QUERIES = (
    ("qatar_supply", '"Qatar" talks buy US LNG long-term agreements when:7d'),
    ("qatar_supply", '"QatarEnergy" seeks US LNG deals through 2031 when:7d'),
    ("qatar_supply", '"QatarEnergy Trading" 2-3 million tonnes US LNG through 2031 when:7d'),
    ("qatar_supply", 'QatarEnergy Venture Global Cheniere Woodside long-term LNG when:7d'),
    ("qatar_supply", '카타르 미국 LNG 장기계약 매입 호르무즈 대체물량 when:7d'),
    ("qatar_supply", '카타르에너지 미국 LNG 2031 200만 300만톤 장기조달 when:7d'),
)
for item in QATAR_US_LNG_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "bloomberg", "reuters", "yahoo finance", "the edge singapore",
)

# 계약 단계가 높은 문구부터 먼저 잡는다.
core.SUBTYPE_TERMS = (
    ("qatar_us_lng_delivery", (
        "delivery begins", "first delivery", "cargo delivered", "첫 인도", "첫 카고", "공급 개시",
    )),
    ("qatar_us_lng_spa", (
        "signs us lng", "signed us lng", "long-term spa", "supply agreement signed",
        "purchase agreement signed", "장기공급계약 체결", "spa 체결", "구매계약 체결",
    )),
    ("qatar_us_lng_scope", (
        "through to 2031", "through 2031", "2-3 million", "2-3 mtpa", "2 million to 3 million",
        "venture global", "cheniere", "woodside", "2031년", "200만", "300만톤",
    )),
    ("qatar_us_lng_talks", (
        "talks to buy us lng", "in discussions to buy", "buy us lng", "seeks us lng deals",
        "long-term agreements", "long term agreements", "미국 lng 매입", "미국산 lng", "장기조달",
    )),
) + tuple(core.SUBTYPE_TERMS)

_BASE_CLASSIFY_POLARITY = core.classify_polarity
_BASE_CONFIRMED = core.confirmed_news_groups
_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

QATAR_US_SUBTYPES = {
    "qatar_us_lng_talks",
    "qatar_us_lng_scope",
    "qatar_us_lng_spa",
    "qatar_us_lng_delivery",
}

MAJOR_SOURCES = (
    "bloomberg", "reuters", "financial times", "wall street journal", "cnbc",
    "yahoo finance", "the edge singapore",
)


def classify_polarity_qatar_us(category: str, title: str) -> str | None:
    normalized = core.normalize_text(title)
    if category == "qatar_supply" and any(
        marker in normalized
        for marker in (
            "us lng", "u.s. lng", "미국 lng", "미국산 lng", "venture global", "cheniere", "woodside",
        )
    ):
        if any(term in normalized for term in (
            "signed", "signs", "agreement signed", "spa", "first delivery", "cargo delivered",
            "계약 체결", "spa 체결", "첫 인도", "공급 개시",
        )):
            return "easing"
        # 협상 자체는 완화조치이지만, '자국 수출국이 외부 장기물량을 찾는다'는 사실은
        # 공급차질 장기화 위험을 확인하는 구조적 스트레스 신호로 본다.
        return "worsening"
    return _BASE_CLASSIFY_POLARITY(category, title)


def _event_id(subtype: str, published_epoch: float) -> str:
    bucket = int(published_epoch // (7 * 24 * 3600))
    basis = f"qatar_us_lng|{subtype}|{bucket}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def confirmed_news_groups_qatar_us(items: list[core.NewsItem]):
    confirmed = list(_BASE_CONFIRMED(items))
    existing = {str(group.get("event_id")) for group in confirmed}

    for item in sorted(items, key=lambda value: value.published_epoch, reverse=True):
        if item.category != "qatar_supply" or item.subtype not in QATAR_US_SUBTYPES:
            continue
        if not (item.official or core.source_matches(item.source, MAJOR_SOURCES)):
            continue
        event_id = _event_id(item.subtype, item.published_epoch)
        if event_id in existing:
            continue
        confirmed.append({
            "category": "qatar_supply",
            "polarity": item.polarity,
            "subtype": item.subtype,
            "event_id": event_id,
            "latest_epoch": item.published_epoch,
            "evidence": [item],
            "verification": "카타르 미국 LNG 장기조달 구조변화 · 주요 통신/금융매체 조기신호",
        })
        existing.add(event_id)

    confirmed.sort(key=lambda group: float(group.get("latest_epoch") or 0), reverse=True)
    return confirmed


def _stage(subtype: str) -> tuple[int, str]:
    if subtype == "qatar_us_lng_delivery":
        return 4, "미국산 LNG 실제 인도·공급 개시"
    if subtype == "qatar_us_lng_spa":
        return 3, "장기 SPA·구매계약 체결"
    if subtype == "qatar_us_lng_scope":
        return 2, "기간·물량·후보 공급사까지 협상 범위 구체화"
    return 1, "장기조달 협상 시작·계약 미확정"


def _qatar_us_section(groups: list[dict[str, object]]) -> list[str]:
    selected = [g for g in groups if str(g.get("subtype") or "") in QATAR_US_SUBTYPES]
    if not selected:
        return []

    best = max(selected, key=lambda g: _stage(str(g.get("subtype") or ""))[0])
    stage_no, stage_name = _stage(str(best.get("subtype") or ""))
    has_scope = any(str(g.get("subtype")) == "qatar_us_lng_scope" for g in selected)
    has_signed = any(str(g.get("subtype")) in {"qatar_us_lng_spa", "qatar_us_lng_delivery"} for g in selected)

    if has_signed:
        verdict = "대체조달이 실제 계약/인도로 진전 · 공급공백 완화와 포트폴리오 재편을 함께 확인"
    else:
        verdict = "카타르 공급차질이 현물 대응을 넘어 장기 포트폴리오 재편 단계로 확대"

    lines = [
        "<b>카타르 → 미국 LNG 대체조달</b>",
        f"• <b>판정</b> {verdict}",
        f"• <b>현재 단계</b> {stage_name} · <b>{stage_no}/4</b>",
        "• <b>왜 이례적인가</b> 세계 최대 LNG 수출국 중 하나인 카타르가 자국 수요가 아니라 기존 해외 고객 계약을 지키기 위해 미국산 LNG 장기물량을 찾는 구조",
        "• <b>Bloomberg 9/10 기준</b> 기존·건설 중인 미국 수출 프로젝트의 장기물량 매입 협상 · 전쟁 이후 중동 밖 공급 포트폴리오 확대의 첫 신호",
    ]
    if has_scope:
        lines.extend([
            "• <b>Reuters 9/11 후속</b> 2031년까지 연 <b>200만~300만t</b> 조달 협상 · Venture Global·Cheniere·Woodside가 후보로 거론",
            "• <b>공급공백 기준선</b> 라스라판 14개 트레인 중 2개 피해 · <b>연 1,280만t</b> 생산능력 3~5년 차질 가능성",
            "• <b>미국 가용 후보물량</b> Reuters가 인용한 Rapidan Energy 기준 건설 중 프로젝트의 미계약 물량 약 <b>2,500만t/년</b>",
            "• <b>아시아 노출</b> 카타르 LNG 출하의 약 <b>80%</b>가 아시아 구매자향으로 보도돼 한국·일본·중국의 대체조달 경쟁과 직접 연결",
        ])
    lines.extend([
        "• <b>Golden Pass 기준선</b> QatarEnergy 70%·ExxonMobil 30% 합작 · 2026년 3월 첫 생산, 4월 첫 수출 카고 출항",
        "• <b>해석</b> 이미 미국 생산자산을 보유한 카타르가 제3자 미국 물량까지 찾는다면 자체 미국 포트폴리오만으로는 장기 공급공백을 모두 메우기 어렵다고 보는 신호일 수 있음",
        "• <b>확정/미확정</b> 협상 보도 ≠ SPA 체결 ≠ 실제 인도. 공급사·물량·기간·가격식이 서명될 때마다 단계 상향",
        "• <b>한국 영향</b> 카타르가 미국 장기물량을 선점하면 아시아 구매자가 접근할 수 있는 유연 미국 LNG 물량이 줄어 JKM·현물 프리미엄 압력이 커질 수 있음",
        "• <b>투자 연결</b> 미국 LNG 생산·액화 프로젝트에는 수요 가시성 강화 요인 · 반대로 아시아 구매자는 조달비와 장기계약 경쟁 부담 확대",
        "• <b>다음 확인</b> 상대방 실명·연간 물량·계약기간·가격식 → SPA 서명 → 첫 인도 → 카타르 고객 재판매/대체공급 구조 → 불가항력 종료·호르무즈 정상화",
    ])
    return lines


def build_regular_alert_qatar_us(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    lines = _qatar_us_section(groups)
    if lines:
        title = "⚠️ 카타르 LNG 공급망 재편 · 미국 장기조달 협상"
        body += "\n\n" + "\n".join(lines)
    metadata["qatar_us_lng_watch"] = {
        "stages": [
            "장기조달 협상",
            "기간·물량·후보 구체화",
            "SPA·구매계약 체결",
            "실제 인도·공급 개시",
        ],
        "rule": "talks are a structural stress/hedging signal, not a signed supply contract",
        "dedupe": "weekly bucket per stage; stage upgrades alert separately",
    }
    return title, body, metadata


def build_setup_test_qatar_us(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n\n<b>카타르 미국 LNG 장기조달</b>"
        "\n• 협상 → 기간·물량·후보 구체화 → SPA 체결 → 실제 인도를 별도 단계로 감시"
        "\n• 미국산 매입은 단순 호재가 아니라 카타르 공급차질의 장기화 신호와 완화조치를 동시에 표시"
        "\n• Golden Pass 기존 70% 지분/수출과 제3자 미국 장기구매를 구분"
    )
    metadata["qatar_us_lng_watch_enabled"] = True
    return title, body, metadata

# 영문 제목이 그대로 Telegram에 나가지 않도록 주요 헤드라인은 한국어로 잠근다.
v12.v8.KNOWN_TRANSLATIONS.update({
    "Qatar in Talks to Buy US LNG With Specter of Lengthy War Looming": "장기전 우려 속 카타르, 미국산 LNG 장기매입 협상",
    "Qatar in talks to buy US LNG with spectre of lengthy war looming - Bloomberg": "장기전 우려 속 카타르, 미국산 LNG 장기매입 협상",
    "QatarEnergy seeks US LNG deals through to 2031, sources say": "카타르에너지, 2031년까지 미국산 LNG 장기조달 협상",
})

core.classify_polarity = classify_polarity_qatar_us
core.confirmed_news_groups = confirmed_news_groups_qatar_us
core.build_regular_alert = build_regular_alert_qatar_us
core.build_setup_test = build_setup_test_qatar_us

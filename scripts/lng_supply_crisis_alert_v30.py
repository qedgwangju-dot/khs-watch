#!/usr/bin/env python3
"""에너지 공급감시 v30: 장기 LNG SPA·미중 LNG 계약 재개/확대 감시.

v29의 호르무즈·가격·한국어 출력 규칙을 유지하면서, 특정 기사 자체가 아니라
장기 LNG 구매계약(SPA)의 체결/확대/취소와 실물 인도 단계 변화를 별도 사건축으로 감시한다.

핵심 원칙
- MOU/협상과 구속력 있는 SPA를 구분한다.
- 계약 체결과 실제 중국향 물리적 수입 재개를 구분한다.
- 물량·기간·개시연도·기존 누적 오프테이크가 확인되면 상단에 배치한다.
- 계약가격/가격식이 비공개면 원화 계약가를 임의 추정하지 않는다.
- 기사 제목/매체명은 한국어로만 송출하며 식별 필수 약어(SPA, LNG, MTPA 등)만 유지한다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v29 as v29

v28 = v29.v28
v27 = v28.v27
v26 = v27.v26
v12 = v27.v12
v8 = v12.v8

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test
_BASE_POLARITY = core.classify_polarity
_BASE_CATEGORY_LABEL = core.category_label
_BASE_CONFIRMED = core.confirmed_news_groups

CATEGORY = "long_term_lng_contract"

LONG_TERM_CONTRACT_QUERIES = (
    (CATEGORY, '"long-term LNG" SPA China US Venture Global Cheniere NextDecade Sempra when:3d'),
    (CATEGORY, '"LNG sales and purchase agreement" China Korea Japan US when:3d'),
    (CATEGORY, 'China US LNG 20-year agreement tariff imports Venture Global when:7d'),
    (CATEGORY, 'China Gas Venture Global LNG SPA 0.5 MTPA 2030 when:7d'),
    (CATEGORY, 'Asia buyer US LNG long-term SPA offtake when:3d'),
    (CATEGORY, '중국 미국 LNG 장기계약 SPA 벤처글로벌 관세 수입 재개 when:7d'),
    (CATEGORY, '한국 일본 중국 미국산 LNG 장기 구매계약 체결 해지 물량 when:7d'),
)
for item in LONG_TERM_CONTRACT_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "business wire", "venture global", "china gas holdings", "china gas",
    "cheniere", "nextdecade", "sempra", "woodside", "exxonmobil", "chevron",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + (
    "venture global", "china gas holdings", "china gas", "cheniere", "nextdecade", "sempra",
)

core.WORSENING_TERMS[CATEGORY] = (
    "cancel", "cancelled", "canceled", "terminate", "terminated", "termination",
    "withdraw", "withdraws", "suspend agreement", "scrap deal", "deal collapses",
    "계약 취소", "계약 해지", "계약 종료", "철회", "무산",
)
core.EASING_TERMS[CATEGORY] = (
    "long-term lng agreement", "long term lng agreement", "sales and purchase agreement",
    "spa", "20-year", "20 year", "long-term offtake", "long term offtake",
    "signs", "signed", "announce new", "new long-term", "purchase agreement",
    "장기 구매계약", "장기계약", "판매구매계약", "계약 체결", "오프테이크",
)

core.SUBTYPE_TERMS = (
    ("lng_long_term_spa_cancelled", (
        "lng agreement cancelled", "lng agreement canceled", "spa terminated", "spa cancellation",
        "계약 취소", "계약 해지", "계약 종료",
    )),
    ("lng_long_term_delivery_start", (
        "first delivery under", "first cargo under", "deliveries begin", "deliveries start",
        "첫 인도", "첫 카고", "공급 개시", "인도 개시",
    )),
    ("lng_long_term_spa_signed", (
        "long-term lng agreement", "long term lng agreement", "sales and purchase agreement",
        "20-year", "20 year", "long-term offtake", "long term offtake",
        "장기 구매계약", "장기계약", "판매구매계약", "오프테이크",
    )),
) + tuple(core.SUBTYPE_TERMS)

v26.STAGE_LABELS.update({
    "lng_long_term_spa_signed": "장기 LNG 구매계약(SPA) 체결·확대",
    "lng_long_term_spa_cancelled": "장기 LNG 구매계약 취소·해지",
    "lng_long_term_delivery_start": "장기계약 물량 실제 인도 개시",
})
v26.CATEGORY_MEANING[CATEGORY] = "장기 LNG 계약·미국산 LNG 오프테이크·실물 인도"

v8.SOURCE_KO.update({
    "business wire": "비즈니스와이어",
    "venture global": "벤처 글로벌",
    "china gas holdings": "차이나가스",
    "china gas": "차이나가스",
})
v8.KNOWN_TRANSLATIONS.update({
    "Venture Global and China Gas Announce New Long-Term LNG Agreement":
        "벤처 글로벌·차이나가스, 미국산 LNG 20년 장기 구매계약 추가 체결",
    "Venture Global and China Gas Announce New Long-Term LNG Agreement - Business Wire":
        "벤처 글로벌·차이나가스, 미국산 LNG 20년 장기 구매계약 추가 체결",
    "China Gas signs 20-year LNG import deal with US-based Venture Global":
        "차이나가스, 벤처 글로벌과 미국산 LNG 20년 장기 구매계약 체결",
    "China Gas signs 20-year LNG import deal with US-based Venture Global - Reuters":
        "차이나가스, 벤처 글로벌과 미국산 LNG 20년 장기 구매계약 체결",
})

ENTITY_PATTERNS = (
    ("venture global", "venture-global"),
    ("china gas", "china-gas"),
    ("cheniere", "cheniere"),
    ("sinopec", "sinopec"),
    ("cnooc", "cnooc"),
    ("petrochina", "petrochina"),
    ("cnpc", "cnpc"),
    ("kogas", "kogas"),
    ("hanwha", "hanwha"),
    ("jera", "jera"),
    ("tokyo gas", "tokyo-gas"),
    ("osaka gas", "osaka-gas"),
    ("nextdecade", "nextdecade"),
    ("sempra", "sempra"),
    ("woodside", "woodside"),
)

MAJOR_CONTRACT_SOURCES = (
    "reuters", "bloomberg", "financial times", "wall street journal",
    "business wire", "venture global", "china gas", "cheniere", "nextdecade", "sempra",
)


def category_label_v30(category: str) -> str:
    if category == CATEGORY:
        return "장기 LNG 구매계약·오프테이크"
    return _BASE_CATEGORY_LABEL(category)


def classify_polarity_v30(category: str, title: str) -> str | None:
    if category != CATEGORY:
        return _BASE_POLARITY(category, title)
    normalized = core.normalize_text(title)
    if any(term in normalized for term in core.WORSENING_TERMS[CATEGORY]):
        return "worsening"
    if any(term in normalized for term in core.EASING_TERMS[CATEGORY]):
        return "easing"
    return None


def _contract_event_id(items: list[core.NewsItem]) -> str:
    latest = max(items, key=lambda x: x.published_epoch)
    text = " ".join(core.normalize_text(item.title) for item in items)
    entities = sorted({canon for pattern, canon in ENTITY_PATTERNS if pattern in text})
    if not entities:
        tokens = [
            token for token in re.findall(r"[a-z0-9가-힣]+", core.normalize_text(latest.title))
            if len(token) >= 4 and token not in core.STOPWORDS
        ]
        entities = tokens[:5]
    day = dt.datetime.fromtimestamp(latest.published_epoch, dt.timezone.utc).strftime("%Y-%m-%d")
    raw = f"{latest.subtype}|{'|'.join(entities)}|{day}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def confirmed_news_groups_v30(items: list[core.NewsItem]):
    base = [g for g in _BASE_CONFIRMED(items) if str(g.get("category") or "") != CATEGORY]
    contract_items = [item for item in items if item.category == CATEGORY]
    buckets: dict[tuple[str, str], list[core.NewsItem]] = {}
    for item in contract_items:
        normalized = core.normalize_text(item.title)
        entities = tuple(sorted(canon for pattern, canon in ENTITY_PATTERNS if pattern in normalized))
        key = (item.subtype, "|".join(entities) or normalized[:80])
        buckets.setdefault(key, []).append(item)

    for (_, _), group in buckets.items():
        group.sort(key=lambda x: x.published_epoch, reverse=True)
        latest = group[0]
        recent = [x for x in group if latest.published_epoch - x.published_epoch <= 48 * 3600]
        official = [x for x in recent if x.official]
        major = [x for x in recent if core.source_matches(x.source, MAJOR_CONTRACT_SOURCES)]
        distinct_sources = {core.normalize_text(x.source) for x in recent}
        if not official and not major and len(distinct_sources) < 2:
            continue
        evidence: list[core.NewsItem] = []
        used: set[str] = set()
        for item in (official + major + recent):
            skey = core.normalize_text(item.source)
            if skey in used:
                continue
            evidence.append(item)
            used.add(skey)
            if len(evidence) >= 2:
                break
        if official:
            verification = "구속력 있는 SPA · 회사 공식 발표 확인"
        elif major:
            verification = "구속력 있는 SPA · 주요 통신/공시성 배포 확인"
        else:
            verification = "장기 LNG 계약 · 신뢰 매체 2곳 교차"
        base.append({
            "category": CATEGORY,
            "polarity": latest.polarity,
            "subtype": latest.subtype,
            "event_id": _contract_event_id(recent),
            "latest_epoch": latest.published_epoch,
            "evidence": evidence,
            "verification": verification,
        })

    base.sort(key=lambda g: float(g.get("latest_epoch") or 0), reverse=True)
    return base


def _contract_groups(groups):
    return [g for g in groups if str(g.get("category") or "") == CATEGORY]


def _is_china_gas_venture_global(groups) -> bool:
    text = " ".join(
        core.normalize_text(str(getattr(item, "title", "") or ""))
        for group in groups for item in list(group.get("evidence") or [])
    )
    return "venture global" in text and "china gas" in text


def _title_ko(item: core.NewsItem) -> str:
    raw = str(getattr(item, "title", "") or "").strip()
    if raw in v8.KNOWN_TRANSLATIONS:
        return v8.KNOWN_TRANSLATIONS[raw]
    translated = v12.translate_title_ko_strict(item).strip()
    if not translated or v12._contains_untranslated_prose(translated):
        if item.subtype == "lng_long_term_spa_cancelled":
            return "장기 LNG 구매계약 취소·해지 확인"
        if item.subtype == "lng_long_term_delivery_start":
            return "장기 LNG 계약 물량의 실제 인도 개시"
        return "장기 LNG 구매계약(SPA) 체결·확대 확인"
    return translated


def _evidence_lines(groups) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for group in sorted(groups, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True):
        for item in list(group.get("evidence") or []):
            raw_title = str(getattr(item, "title", "") or "").strip()
            link = str(getattr(item, "link", "") or "").strip()
            key = (raw_title, link)
            if key in seen:
                continue
            seen.add(key)
            source = v8.source_name_ko(str(getattr(item, "source", "주요 매체") or "주요 매체"))
            title = _title_ko(item)
            if link:
                lines.append(
                    f'• <b>{html.escape(source)}</b> · {html.escape(title)} · '
                    f'<a href="{html.escape(link, quote=True)}">원문</a>'
                )
            else:
                lines.append(f"• <b>{html.escape(source)}</b> · {html.escape(title)}")
            if len(lines) >= 3:
                return lines
    return lines


def _build_contract_body(groups) -> str:
    selected = _contract_groups(groups)
    latest = max(selected, key=lambda g: float(g.get("latest_epoch") or 0))
    subtype = str(latest.get("subtype") or "")
    is_china_gas = _is_china_gas_venture_global(selected)

    if subtype == "lng_long_term_spa_cancelled":
        verdict = "장기 LNG 계약 후퇴 · 확보물량·프로젝트 상업성 재점검"
        stage = "구매계약 취소·해지"
    elif subtype == "lng_long_term_delivery_start":
        verdict = "장기 LNG 계약이 실제 물리적 공급 단계로 진입"
        stage = "계약물량 실제 인도 개시"
    else:
        verdict = "장기 LNG 계약 확대 · 미래 오프테이크 선점"
        stage = "구속력 있는 구매계약(SPA) 체결"

    lines = [
        "<b>한눈에</b>",
        f"• <b>판정</b> {verdict}",
        f"• <b>현재 단계</b> {stage}",
    ]

    if is_china_gas and subtype == "lng_long_term_spa_signed":
        lines.extend([
            "• <b>신규 물량</b> 연 <b>50만톤(0.5 MTPA)</b> · <b>20년</b> · <b>2030년</b> 공급 시작",
            "• <b>신규 계약 총량</b> 20년 기준 <b>1,000만톤</b>",
            "• <b>누적 관계</b> 차이나가스의 벤처 글로벌 장기 오프테이크가 연 <b>250만톤(2.5 MTPA)</b>으로 확대",
            "• <b>주의</b> 장기계약 체결 ≠ 중국향 실물 LNG 수입 즉시 재개",
        ])

    lines.extend(["", "<b>확정 당사자</b>"])
    if is_china_gas:
        lines.extend([
            "• <b>구매자</b> 차이나가스(0384.HK) · 중국 도시가스·에너지 유통",
            "• <b>판매자</b> 벤처 글로벌(NYSE: VG) · 미국 루이지애나 LNG 포트폴리오",
            "• <b>기존 계약</b> 2023년 플라크마인즈 LNG 100만톤/년 + CP2 LNG 100만톤/년 · 각각 20년",
        ])
    else:
        lines.append("• 구매자·판매자·물량·기간·개시연도는 공식 발표/주요 통신 확인값만 표시")

    lines.extend(["", "<b>확인 근거</b>"])
    lines.extend(_evidence_lines(selected) or ["• 공식 발표 또는 주요 통신에서 장기 LNG 계약 단계 변화 확인"])

    if is_china_gas:
        lines.extend([
            "",
            "<b>왜 중요한가</b>",
            "• <b>무역 연결</b> 중국은 2025년 관세 충돌 뒤 미국산 LNG 직접 수입이 사실상 멈췄지만 장기 계약 관계는 유지돼 왔음",
            "• <b>이번 의미</b> 현행 관세가 남아 있는 상황에서도 2030년 이후 미국산 LNG를 추가로 장기 확보했다는 점에서 미중 에너지 연결고리가 끊기지 않았다는 신호",
            "• <b>실물과 계약 분리</b> 기존 미국산 계약 카고가 중국 대신 유럽 등 제3국으로 재판매될 수 있어, SPA 체결만으로 중국의 즉시 수입 회복을 뜻하지 않음",
            "• <b>계약액</b> 가격식·계약단가 비공개 → 실제 원화 총계약액은 추정하지 않음",
        ])

    lines.extend([
        "",
        "<b>한국 영향</b>",
        "• <b>장기 수급</b> 중국이 미국 LNG를 2030년 이후 장기로 선점하면 한국·일본 구매자와의 장기 오프테이크 경쟁이 강해질 수 있음",
        "• <b>반대 요인</b> 미국 LNG 생산능력도 빠르게 증설 중이므로 50만톤/년 계약 하나만으로 한국 공급 부족을 단정하지 않음",
        "",
        "<b>투자 4축</b>",
        "• <b>돈버는능력</b> 벤처 글로벌은 장기 판매물량·현금흐름 가시성 강화 / 차이나가스는 장기 조달 포트폴리오 확대",
        "• <b>할인율</b> 장기 SPA는 프로젝트 금융·증설의 현금흐름 가시성을 높이지만 실제 가격식과 신용조건이 중요",
        "• <b>수급</b> 미국 신규 LNG 물량 중 장기계약으로 잠기는 비중과 아시아 구매자별 계약량을 추적",
        "• <b>시간표</b> SPA 체결 → 관세·정책 변화 → 공급 프로젝트 진행 → 2030년 인도 개시 → 중국향 실제 통관/도착 순으로 확인",
        "",
        "<b>숨은 역풍·실패모드</b>",
        "• 중국 LNG 수요 둔화·관세 유지·목적지 변경권으로 실제 중국 내 소비와 계약물량이 분리될 수 있음",
        "• 먼저 볼 지표는 미국산 LNG의 중국 직접 통관 재개 여부와 계약 카고의 실제 목적지",
        "",
        "<b>다음 확인</b>",
        "• ① 계약 가격식·목적지 유연성 → ② 중국의 미국 LNG 관세 → ③ 벤처 글로벌 공급 프로젝트 → ④ 첫 인도 → ⑤ 중국 직접 통관량 → ⑥ 한국·일본 신규 장기 SPA",
        "",
        "<b>핵심 한 줄</b>",
        "• 중국이 미국산 LNG 장기계약을 다시 늘렸다는 점이 핵심이며, 진짜 다음 단계는 계약 체결이 아니라 관세 변화와 중국향 실제 카고 인도 재개임",
    ])
    return "\n".join(lines)


def build_regular_alert_v30(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    contracts = _contract_groups(groups)
    if contracts and not v29._bypass_groups(groups):
        title = "📌 장기 LNG 구매계약·오프테이크 변화"
        body = _build_contract_body(groups)
    elif contracts:
        body += "\n\n" + _build_contract_body(contracts)
    metadata["version"] = 30
    metadata["long_term_lng_contract_watch"] = {
        "target": "binding SPA/offtake/delivery state changes, not specific articles",
        "stages": ["SPA signed/expanded", "SPA cancelled/terminated", "physical delivery start"],
        "trade_separation": "contract signing != physical import resumption",
        "price_rule": "do not estimate KRW contract value when price formula is undisclosed",
        "headline_language": "ko-strict",
    }
    return title, body, metadata


def build_setup_test_v30(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 장기 LNG SPA 체결·확대·취소·실제 인도 개시를 별도 사건축으로 감시"
        "\n• 미중 LNG는 계약 체결과 중국향 실물 수입 재개를 분리 판정"
        "\n• 물량·기간·개시연도·누적 오프테이크를 상단 표시하고 가격식 비공개 시 원화 계약액 추정 금지"
    )
    metadata["version"] = 30
    return title, body, metadata


core.category_label = category_label_v30
core.classify_polarity = classify_polarity_v30
core.confirmed_news_groups = confirmed_news_groups_v30
core.build_regular_alert = build_regular_alert_v30
core.build_setup_test = build_setup_test_v30

if __name__ == "__main__":
    raise SystemExit(core.main())

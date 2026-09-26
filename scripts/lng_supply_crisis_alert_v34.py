#!/usr/bin/env python3
"""에너지 공급감시 v34: 정제제품 경보 한국어·가독성·시점 안전성 보강.

v33의 정제제품 사건축을 유지하면서 다음만 수정한다.
- 월스트리트저널 연료위기 제목이 LNG 일반 대체문으로 떨어지지 않도록 전용 한국어 제목 사용
- Yahoo/Vitol 같은 영문 표시를 한국어로 정리
- 2026-09-04 EIA 주간값은 9월 16일 다음 발표 이후 자동으로 고정값 노출 차단
- Alaska LNG·Polar LNG·AGDC·Glenfarne 및 545억달러·800억달러 규모 변화 감시
- 사우디 동서 송유관·Yanbu 원유 전용 기사는 LNG 공급경보에서 제외
- TTF 기준일은 Trading Economics 동일값 상품표 행으로 재검증
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v33 as v33

v32 = v33.v32
v12 = v33.v12
v8 = v33.v8

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test
_BASE_POLARITY_V34 = core.classify_polarity
_BASE_CATEGORY_LABEL_V34 = core.category_label
_BASE_CONFIRMED_V34 = core.confirmed_news_groups
_BASE_V32_STRICT_TITLE_V34 = v32._strict_title
_BASE_V32_SOURCE_KO_V34 = v32._source_ko

ALASKA_CATEGORY = "alaska_lng_supply"
ASIA_DEMAND_CATEGORY = "asia_lng_demand_rethink"
ASIA_DEMAND_QUERIES = (
    (ASIA_DEMAND_CATEGORY, '"sour on LNG" Asia when:14d'),
    (ASIA_DEMAND_CATEGORY, '"wean themselves off LNG" Asia when:14d'),
    (ASIA_DEMAND_CATEGORY, '"LNG demand" Asia solar coal nuclear when:14d'),
    (ASIA_DEMAND_CATEGORY, '"$7 billion" LNG Asia Pakistan Bangladesh Thailand Vietnam when:14d'),
    (ASIA_DEMAND_CATEGORY, '"$7.4 billion" LNG Asia when:14d'),
    (ASIA_DEMAND_CATEGORY, '아시아 LNG 탈 LNG 비용 폭탄 현물 조달 태양광 석탄 when:14d'),
)
for item in ASIA_DEMAND_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

ALASKA_LNG_QUERIES = (
    (ALASKA_CATEGORY, '"Alaska LNG" Glenfarne AGDC when:7d'),
    (ALASKA_CATEGORY, '"Polar LNG" Alaska when:7d'),
    (ALASKA_CATEGORY, '"Alaska LNG" "54.5 billion" OR "80 billion" when:14d'),
    (ALASKA_CATEGORY, 'Alaska LNG "$54.5bn" OR "$80bn" when:14d'),
    (ALASKA_CATEGORY, 'Alaska LNG superpower 80bn when:7d'),
    (ALASKA_CATEGORY, '"Alaska as LNG superpower" when:7d'),
    (ALASKA_CATEGORY, '"Trump vision" Alaska LNG superpower when:7d'),
    (ALASKA_CATEGORY, '"Alaska LNG" sanctions financing when:14d'),
    (ALASKA_CATEGORY, '"Alaska LNG" "3mn tonnes" offtake FID when:14d'),
    (ALASKA_CATEGORY, '"Alaska LNG" tax breaks delay when:14d'),
    (ALASKA_CATEGORY, '"Polar LNG" Novatek sanctions when:14d'),
    (ALASKA_CATEGORY, '알래스카 LNG 글렌파른 AGDC 545억달러 800억달러 제재 자금조달 when:14d'),
)
for item in ALASKA_LNG_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "alaska gasline development corporation", "agdc", "glenfarne", "polar lng",
    "federal energy regulatory commission", "ferc",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + (
    "alaska gasline development corporation", "agdc", "glenfarne", "polar lng",
    "federal energy regulatory commission", "ferc",
)

core.WORSENING_TERMS[ASIA_DEMAND_CATEGORY] = (
    "sour on lng", "wean themselves off lng", "wean off lng", "demand destruction",
    "shift away from lng", "move away from lng", "lng demand slows", "lng demand weakens",
    "cancelled", "canceled", "withdrawn", "no progress", "coal", "solar", "hydropower",
    "renewables", "nuclear", "local gas", "piped gas",
    "탈 lng", "lng 이탈", "수요 파괴", "수요 둔화", "태양광", "석탄", "원전", "국산가스",
)
core.EASING_TERMS[ASIA_DEMAND_CATEGORY] = (
    "lng demand growth", "lng demand rises", "lng demand rebounds", "new lng demand",
    "gas-fired expansion", "lng adoption", "수요 증가", "lng 확대", "가스발전 확대",
)

core.WORSENING_TERMS[ALASKA_CATEGORY] = (
    "delay", "delayed", "postpone", "postponed", "hold", "stalled", "stall",
    "cost overrun", "cost increase", "financing gap", "funding gap", "tax incentive failed",
    "failed to pass", "sanction", "sanctions", "permit challenge", "lawsuit", "cancelled", "canceled",
    "confronts", "hurdle", "obstacle", "risk",
    "지연", "연기", "중단", "보류", "비용 증가", "자금조달 난항", "제재", "허가 지연", "취소",
)
core.EASING_TERMS[ALASKA_CATEGORY] = (
    "final investment decision", "fid", "signed", "agreement", "offtake", "gas sales",
    "secured", "committed", "funding", "financing", "final engineering", "feed", "construction",
    "groundbreaking", "supply agreement", "strategic partner", "investment", "export terminal",
    "최종투자결정", "계약", "협약", "구매", "공급", "자금조달", "투자", "착공", "최종 설계",
)
core.SUBTYPE_TERMS = (
    ("asia_lng_demand_rethink", ("sour on lng", "wean themselves off lng", "wean off lng", "탈 lng", "수요 파괴")),
    ("asia_lng_cost_shock", ("7.4 billion", "$7.4 billion", "7 billion", "$7 billion", "비용 폭탄")),
    ("alaska_lng_cost_scale", ("54.5 billion", "80 billion", "54.5bn", "80bn", "545억달러", "800억달러")),
    ("polar_lng_project", ("polar lng",)),
    ("alaska_lng_project", ("alaska lng", "glenfarne", "agdc", "alaska gasline development corporation")),
) + tuple(core.SUBTYPE_TERMS)

ALASKA_MAJOR_SOURCES = (
    "reuters", "bloomberg", "financial times", "wall street journal", "wsj",
    "associated press", "ap news", "cnbc", "s&p global commodity insights", "argus media",
)
ASIA_DEMAND_MAJOR_SOURCES = (
    "bloomberg", "reuters", "financial times", "wall street journal", "wsj",
    "s&p global commodity insights", "argus media", "nikkei asia",
)

v8.SOURCE_KO.update({
    "the white house": "미국 백악관",
    "white house": "미국 백악관",
    "u.s. department of energy": "미국 에너지부",
    "department of energy": "미국 에너지부",
    "state of alaska": "알래스카주 정부",
    "alaska gasline development corporation": "알래스카가스라인개발공사(AGDC)",
    "alaska gasline development corp": "알래스카가스라인개발공사(AGDC)",
    "alaska gasline development": "알래스카가스라인개발공사(AGDC)",
    "agdc": "알래스카가스라인개발공사(AGDC)",
    "glenfarne alaska lng": "Glenfarne Alaska LNG",
    "glenfarne": "Glenfarne",
})

ALASKA_POLICY_MARKERS = (
    ("going_to_alaska", ("going to alaska", "go to alaska", "알래스카로 간다", "load up", "build pipelines")),
    ("strategic_progress", ("significant progress", "전략투자", "strategic investment", "progress in discussions")),
    ("participation_review", ("possible investment", "considering", "participation", "참여 검토", "투자 검토")),
    ("funding_claim", ("secured funds", "unprecedented funds", "funds from korea", "funds from japan")),
)
ALASKA_POLICY_COUNTERPARTIES = (
    ("korea", ("south korea", "korea", "한국")),
    ("japan", ("japan", "일본")),
    ("trump", ("trump", "트럼프", "president")),
    ("us", ("united states", "u.s.", "us investment", "미국")),
)

LNG_RELEVANCE_TERMS = (
    "lng", "liquefied natural gas", "natural gas", "gas tanker", "lng tanker",
    "qatar lng", "qatarenergy", "jkm", "ttf",
)
SAUDI_OIL_ONLY_TERMS = (
    "east-west pipeline", "east west pipeline", "yanbu", "saudi pipeline",
    "crude cargo", "crude cargoes", "oil cargo", "oil cargoes",
    "crude shipment", "crude shipments", "oil shipment", "oil shipments",
)
OIL_ONLY_TERMS = (
    "crude", "crude oil", "oil supply", "oil sales", "oil buyer", "oil buyers",
    "oil cargo", "oil cargoes", "oil shipment", "oil shipments", "oil exports",
    "refinery", "refineries", "refining", "diesel", "gasoline", "jet fuel",
    "brent", "wti", "barrel", "barrels", "aramco",
)
HORMUZ_ROUTE_TERMS = (
    "strait of hormuz", "hormuz", "red sea", "bab el-mandeb", "bab el mandeb", "suez",
)
HORMUZ_GENERIC_STATUS_TERMS = (
    "closed", "closure", "blocked", "blockade", "attack", "attacked", "seized",
    "shipping halted", "traffic halted", "traffic below", "shipping disruption",
    "traffic disruption", "war risk", "insurance withdrawn", "safe passage",
    "reopens", "reopened", "shipping resumes", "traffic resumes", "transit",
    "vessel", "vessels", "shipping traffic",
)


def _canonical_alaska_policy_event_id_v34(group) -> str | None:
    if str(group.get("category") or "") != "alaska_lng":
        return None
    if str(group.get("subtype") or "") != "alaska_policy_signal":
        return None
    text = _group_evidence_text(group)
    markers = [name for name, terms in ALASKA_POLICY_MARKERS if any(term in text for term in terms)]
    counterparties = [name for name, terms in ALASKA_POLICY_COUNTERPARTIES if any(term in text for term in terms)]
    if not markers:
        tokens = [token for token in text.split() if len(token) >= 4][:8]
        markers = ["fallback:" + "_".join(tokens)]
    basis = "alaska_lng|policy|" + ",".join(sorted(markers)) + "|" + ",".join(sorted(counterparties))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def _is_lng_relevant_item_v34(item: core.NewsItem) -> bool:
    if str(getattr(item, "category", "") or "") != "hormuz_shipping":
        return True
    text = core.normalize_text(str(getattr(item, "title", "") or ""))
    if any(term in text for term in LNG_RELEVANCE_TERMS):
        return True
    if any(term in text for term in OIL_ONLY_TERMS):
        return False
    route_relevant = any(term in text for term in HORMUZ_ROUTE_TERMS)
    status_relevant = any(term in text for term in HORMUZ_GENERIC_STATUS_TERMS)
    return route_relevant and status_relevant


def _group_evidence_text(group) -> str:
    parts: list[str] = []
    for item in list(group.get("evidence") or []):
        parts.append(str(getattr(item, "title", "") or ""))
    return core.normalize_text(" ".join(parts))


def _is_saudi_oil_only_group(group) -> bool:
    if str(group.get("category") or "") != "hormuz_shipping":
        return False
    text = _group_evidence_text(group)
    if "saudi" not in text:
        return False
    oil_route = any(term in text for term in SAUDI_OIL_ONLY_TERMS)
    lng_relevant = any(term in text for term in LNG_RELEVANCE_TERMS)
    return oil_route and not lng_relevant


def classify_polarity_v34(category: str, title: str) -> str | None:
    if category != ALASKA_CATEGORY:
        return _BASE_POLARITY_V34(category, title)
    normalized = core.normalize_text(title)
    if any(term in normalized for term in core.WORSENING_TERMS[ALASKA_CATEGORY]):
        return "worsening"
    if any(term in normalized for term in core.EASING_TERMS[ALASKA_CATEGORY]):
        return "easing"
    if (
        ("alaska" in normalized and "lng" in normalized)
        or any(term in normalized for term in (
            "alaska lng", "polar lng", "glenfarne", "agdc",
            "54.5 billion", "80 billion", "54.5bn", "80bn", "545억달러", "800억달러",
        ))
    ):
        return "easing"
    return None


def category_label_v34(category: str) -> str:
    if category == ALASKA_CATEGORY:
        return "알래스카 LNG·대체공급 프로젝트"
    if category == ASIA_DEMAND_CATEGORY:
        return "아시아 LNG 구조적 수요 재평가"
    return _BASE_CATEGORY_LABEL_V34(category)


def confirmed_news_groups_v34(items: list[core.NewsItem]):
    relevant_items = [item for item in items if _is_lng_relevant_item_v34(item)]
    raw_base = [
        group for group in _BASE_CONFIRMED_V34(relevant_items)
        if str(group.get("category") or "") != ALASKA_CATEGORY
    ]
    base = [group for group in raw_base if not _is_saudi_oil_only_group(group)]
    for group in base:
        canonical_policy_id = _canonical_alaska_policy_event_id_v34(group)
        if canonical_policy_id:
            group["event_id"] = canonical_policy_id
            group["verification"] = str(group.get("verification") or "정책 발언 확인")

    alaska_items = [item for item in items if item.category == ALASKA_CATEGORY]
    buckets: dict[tuple[str, str], list[core.NewsItem]] = {}
    for item in alaska_items:
        buckets.setdefault((item.subtype, item.polarity), []).append(item)

    for (_, _), group in buckets.items():
        group.sort(key=lambda x: x.published_epoch, reverse=True)
        latest = group[0]
        recent = [x for x in group if latest.published_epoch - x.published_epoch <= 96 * 3600]
        official = [x for x in recent if x.official]
        major = [x for x in recent if core.source_matches(x.source, ALASKA_MAJOR_SOURCES)]
        distinct = {core.normalize_text(x.source) for x in recent}
        if not official and not major and len(distinct) < 2:
            continue

        evidence: list[core.NewsItem] = []
        used: set[str] = set()
        for item in (official + major + recent):
            source_key = core.normalize_text(item.source)
            if source_key in used:
                continue
            evidence.append(item)
            used.add(source_key)
            if len(evidence) >= 2:
                break

        if official:
            verification = "공식 원문"
        elif major:
            verification = "주요 신뢰매체 보도 단계"
        else:
            verification = "신뢰 매체 2곳 교차"

        base.append({
            "category": ALASKA_CATEGORY,
            "polarity": latest.polarity,
            "subtype": latest.subtype,
            "event_id": latest.event_id,
            "latest_epoch": latest.published_epoch,
            "evidence": evidence,
            "verification": verification,
        })

    asia_items = [item for item in items if item.category == ASIA_DEMAND_CATEGORY]
    asia_buckets: dict[tuple[str, str], list[core.NewsItem]] = {}
    for item in asia_items:
        asia_buckets.setdefault((item.subtype, item.polarity), []).append(item)

    for (_, _), group in asia_buckets.items():
        group.sort(key=lambda x: x.published_epoch, reverse=True)
        latest = group[0]
        recent = [x for x in group if latest.published_epoch - x.published_epoch <= 120 * 3600]
        major = [x for x in recent if core.source_matches(x.source, ASIA_DEMAND_MAJOR_SOURCES)]
        distinct = {core.normalize_text(x.source) for x in recent}
        if not major and len(distinct) < 2:
            continue

        evidence: list[core.NewsItem] = []
        used: set[str] = set()
        for item in (major + recent):
            source_key = core.normalize_text(item.source)
            if source_key in used:
                continue
            evidence.append(item)
            used.add(source_key)
            if len(evidence) >= 2:
                break

        verification = "주요 신뢰매체 분석 단계" if major else "신뢰 매체 2곳 교차"
        base.append({
            "category": ASIA_DEMAND_CATEGORY,
            "polarity": latest.polarity,
            "subtype": latest.subtype,
            "event_id": latest.event_id,
            "latest_epoch": latest.published_epoch,
            "evidence": evidence,
            "verification": verification,
        })

    base.sort(key=lambda group: float(group.get("latest_epoch") or 0), reverse=True)
    return base


core.classify_polarity = classify_polarity_v34
core.category_label = category_label_v34
core.confirmed_news_groups = confirmed_news_groups_v34


def _title_ko_v34(item: core.NewsItem) -> str:
    raw = str(getattr(item, "title", "") or "").strip()
    normalized = core.normalize_text(raw)
    if item.category == ASIA_DEMAND_CATEGORY:
        if "7.4 billion" in normalized or "$7.4 billion" in normalized or "7 billion" in normalized or "$7 billion" in normalized:
            return "아시아 신흥국 LNG 조달비 급증·장기 수요 재평가"
        return "아시아 LNG 수요 파괴·연료 전환 재평가 신호"
    if item.category == "alaska_lng":
        subtype = str(item.subtype or "")
        if subtype == "alaska_policy_signal":
            return "Alaska LNG 관련 한국·일본 참여·정책 발언의 실질 변화 확인"
        if subtype == "alaska_offtake":
            return "Alaska LNG 오프테이크·장기구매계약 단계 변화"
        if subtype == "alaska_fid":
            return "Alaska LNG 최종투자결정(FID) 단계 변화"
        if subtype == "alaska_epc":
            return "Alaska LNG EPC·발주 단계 변화"
        if subtype == "alaska_setback":
            return "Alaska LNG 일정·사업성 후퇴 신호"
    if item.category == ALASKA_CATEGORY:
        if any(term in normalized for term in core.WORSENING_TERMS[ALASKA_CATEGORY]):
            return "알래스카 LNG 프로젝트 지연·사업성 위험 신규 변화"
        if "polar lng" in normalized:
            return "Polar LNG 알래스카 노스슬로프 프로젝트 신규 변화"
        if any(term in normalized for term in ("54.5 billion", "80 billion", "54.5bn", "80bn", "545억달러", "800억달러")):
            return "알래스카 LNG 대형 프로젝트 투자비·사업성 관련 신규 변화"
        return "Alaska LNG·Glenfarne·AGDC 대체공급 프로젝트 신규 변화"
    if "great fuel crisis is here" in normalized:
        return "미국 석유업계 경영진, 글로벌 연료 위기가 이미 시작됐다고 경고"
    if "global diesel supply to stay tight through winter" in normalized:
        return "글로벌 디젤 공급, 겨울까지 빠듯할 전망…업계 경영진 경고"
    if item.category == v33.CATEGORY:
        subtype = str(item.subtype or "")
        return {
            "fuel_crisis_systemic": "글로벌 연료 공급 위기 단계 상승",
            "refined_inventory_draw": "상업용 연료·중간유분 재고 감소 심화",
            "diesel_shortage": "디젤·중간유분 공급 부족 심화",
            "refinery_capacity_tight": "정유설비 여유능력 부족·가동 차질 확대",
            "fuel_buffer_rebuild": "연료재고·정제능력 회복 진전",
        }.get(subtype, "정제제품·연료 공급망의 확정 변화")
    return _BASE_V32_STRICT_TITLE_V34(item)


def _source_ko_v34(source: str) -> str:
    mapped = _BASE_V32_SOURCE_KO_V34(source)
    if mapped != "해외 매체":
        return mapped
    # 공식 기관인데 사전 매핑이 아직 없는 경우 '해외 매체'로 뭉개지 말고 식별명을 보존한다.
    if core.source_matches(source, core.OFFICIAL_SOURCE_ALIASES):
        return str(source or "공식 기관").strip()
    return mapped


def _evidence_lines_v34(groups) -> list[str]:
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
            source = _source_ko_v34(str(getattr(item, "source", "주요 매체") or "주요 매체"))
            title = _title_ko_v34(item)
            line = f"• <b>{html.escape(source)}</b> · {html.escape(title)}"
            if link:
                line += f' · <a href="{html.escape(link, quote=True)}">원문</a>'
            lines.append(line)
            if len(lines) >= 3:
                return lines
    return lines


# v33/v32 본문 빌더가 호출하는 근거 렌더러도 동일 규칙으로 교체한다.
v33._title_ko = _title_ko_v34
v33._evidence_lines = _evidence_lines_v34
v32._strict_title = _title_ko_v34
v32._source_ko = _source_ko_v34


def _build_fuel_body_v34(groups, quotes) -> str:
    body = v33._build_fuel_body(groups, quotes)
    body = body.replace("Yahoo Brent 선물 ", "")
    body = body.replace("Yahoo 이전 종가", "이전 종가")
    body = body.replace("Yahoo", "야후 파이낸스")
    body = body.replace("Vitol", "비톨")

    # 9/16 다음 주간 EIA 발표 이후에는 9/4 수치를 현재값처럼 계속 노출하지 않는다.
    today_kst = dt.datetime.now(core.KST).date()
    if today_kst > dt.date(2026, 9, 16):
        kept: list[str] = []
        inserted = False
        for line in body.splitlines():
            if "<b>미국 중간유분 재고</b>" in line or "<b>미국 전략비축유</b>" in line:
                if not inserted:
                    kept.append("• <b>EIA 주간 재고</b> 9/4 고정값 재사용 차단 · 최신 공식 주간값 확인 전 숫자 송출 보류")
                    inserted = True
                continue
            kept.append(line)
        body = "\n".join(kept)
    return body


def _alaska_groups(groups) -> list[dict]:
    return [group for group in groups if str(group.get("category") or "") == ALASKA_CATEGORY]


def _build_alaska_body_v34(groups) -> str:
    alaska = _alaska_groups(groups)
    primary = sorted(alaska, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True)[0]
    worsening = str(primary.get("polarity") or "") == "worsening"
    verification = html.escape(str(primary.get("verification") or "확인 단계"))
    status = "사업성·일정 위험 확대" if worsening else "사업 추진 진전"
    meaning = (
        "현재 LNG 물량이 중단됐다는 뜻이 아니라, 알래스카가 중장기 비호르무즈 대체공급원이 되는 시간표가 늦어질 수 있다는 신호입니다."
        if worsening
        else "현재 LNG 물량이 바로 늘었다는 뜻이 아니라, 알래스카가 중장기 비호르무즈 대체공급원이 되는 시간표가 한 단계 전진했다는 신호입니다."
    )
    timetable = (
        "FID·자금조달·구속력 있는 장기구매계약·세제/허가·착공 일정이 실제로 뒤로 밀리는지 확인합니다."
        if worsening
        else "FID·자금조달·구속력 있는 장기구매계약·세제/허가·착공으로 실제 전환되는지 확인합니다."
    )
    evidence = _evidence_lines_v34(alaska)
    evidence_text = "\n".join(evidence) if evidence else "• 공개 근거 링크 확인 필요"
    return (
        "<b>한눈에</b>\n"
        f"• <b>판정</b> 알래스카 LNG·대체공급 프로젝트 {status}\n"
        f"• <b>확인 수준</b> {verification} · 현재 공급중단/공급개시 확정과는 구분\n\n"
        "<b>무엇이 바뀌었나</b>\n"
        f"{evidence_text}\n\n"
        "<b>정확한 의미</b>\n"
        f"• {meaning}\n"
        f"• {timetable}\n\n"
        "<b>한국 영향</b>\n"
        "• 한국의 당장 LNG 재고가 줄었다는 신호가 아닙니다. 중동 공급 차질을 대체할 장기 조달원의 가동 시점과 계약 가능성이 바뀌는지 보는 감시축입니다.\n\n"
        "<b>투자 포인트</b>\n"
        "• 돈 버는 능력: 실제 장기구매계약·FID·착공이 생겨야 공급사·건설·파이프라인 매출로 연결됩니다.\n"
        "• 시간표: Glenfarne·AGDC·Polar LNG의 공식 발표, 자금조달, 장기구매계약, FID, 착공 순으로 확인합니다.\n\n"
        "<b>다음 확인</b>\n"
        "• 공식 자금조달·구속력 있는 구매계약·FID·세제/허가·착공 일정 변화\n\n"
        "<b>핵심 한 줄</b> 알래스카 LNG 뉴스는 현재 공급량 변화가 아니라 중장기 대체공급원의 사업성·가동 시간표 변화로 해석합니다."
    )


def _self_validate_alaska_body_v34() -> None:
    fixture = core.NewsItem(
        category=ALASKA_CATEGORY,
        polarity="worsening",
        subtype="alaska_lng_cost_scale",
        title="Trump's vision of Alaska as LNG superpower confronts an $80bn test",
        source="Financial Times",
        link="https://example.com/alaska-lng",
        published_utc="2026-09-15T00:00:00+00:00",
        published_epoch=1.0,
        official=False,
        event_id="fixture-alaska-lng",
    )
    body = _build_alaska_body_v34([{
        "category": ALASKA_CATEGORY,
        "polarity": "worsening",
        "subtype": "alaska_lng_cost_scale",
        "event_id": "fixture-alaska-lng",
        "latest_epoch": 1.0,
        "evidence": [fixture],
        "verification": "주요 신뢰매체 보도 단계",
    }])
    assert "알래스카 LNG·대체공급 프로젝트 사업성·일정 위험 확대" in body
    assert "현재 LNG 물량이 중단됐다는 뜻이 아니라" in body
    assert "파이낸셜타임스" in body
    assert "카타르 생산" not in body
    assert "호르무즈 우회" not in body


def _self_validate_lng_relevance_v34() -> None:
    oil_item = core.NewsItem(
        category="hormuz_shipping",
        polarity="worsening",
        subtype="pipeline_outage",
        title="Saudi Arabia cancels some oil cargoes after East-West pipeline shutdown at Yanbu",
        source="Reuters",
        link="https://example.com/saudi-oil",
        published_utc="2026-09-15T00:00:00+00:00",
        published_epoch=1.0,
        official=False,
        event_id="fixture-saudi-oil",
    )
    oil_group = {
        "category": "hormuz_shipping",
        "polarity": "worsening",
        "subtype": "pipeline_outage",
        "event_id": "fixture-saudi-oil",
        "latest_epoch": 1.0,
        "evidence": [oil_item],
        "verification": "신뢰 매체 2곳 교차",
    }
    assert _is_saudi_oil_only_group(oil_group)

    lng_item = core.NewsItem(
        category="hormuz_shipping",
        polarity="worsening",
        subtype="reroute",
        title="Qatar LNG tanker reroutes as Strait of Hormuz shipping disruption worsens",
        source="Reuters",
        link="https://example.com/hormuz-lng",
        published_utc="2026-09-15T00:00:00+00:00",
        published_epoch=1.0,
        official=False,
        event_id="fixture-hormuz-lng",
    )
    lng_group = {
        "category": "hormuz_shipping",
        "polarity": "worsening",
        "subtype": "reroute",
        "event_id": "fixture-hormuz-lng",
        "latest_epoch": 1.0,
        "evidence": [lng_item],
        "verification": "신뢰 매체 2곳 교차",
    }
    assert not _is_saudi_oil_only_group(lng_group)


def _self_validate_cross_source_relevance_v34() -> None:
    lng_item = core.NewsItem(
        category="hormuz_shipping",
        polarity="worsening",
        subtype="reroute",
        title="LNG shipping disruption at Strait of Hormuz keeps Qatar LNG vessels outside the strait",
        source="Reuters",
        link="https://example.com/reuters-lng",
        published_utc="2026-09-20T00:00:00+00:00",
        published_epoch=10.0,
        official=False,
        event_id="fixture-reuters-lng",
    )
    oil_item = core.NewsItem(
        category="hormuz_shipping",
        polarity="worsening",
        subtype="reroute",
        title="European oil supply pressure rises after attacks cut Saudi sales",
        source="Bloomberg",
        link="https://example.com/bloomberg-oil",
        published_utc="2026-09-20T00:00:00+00:00",
        published_epoch=9.0,
        official=False,
        event_id="fixture-bloomberg-oil",
    )
    mixed = confirmed_news_groups_v34([lng_item, oil_item])
    assert not any(str(group.get("category") or "") == "hormuz_shipping" for group in mixed)

    lng_item_2 = core.NewsItem(
        category="hormuz_shipping",
        polarity="worsening",
        subtype="reroute",
        title="Qatar LNG tanker traffic remains disrupted through Strait of Hormuz",
        source="S&P Global Commodity Insights",
        link="https://example.com/spglobal-lng",
        published_utc="2026-09-20T00:00:00+00:00",
        published_epoch=8.0,
        official=False,
        event_id="fixture-spglobal-lng",
    )
    direct = confirmed_news_groups_v34([lng_item, lng_item_2])
    assert any(str(group.get("category") or "") == "hormuz_shipping" for group in direct)


_self_validate_alaska_body_v34()
_self_validate_lng_relevance_v34()
_self_validate_cross_source_relevance_v34()


def _self_validate_alaska_policy_render_v34() -> None:
    item = core.NewsItem(
        category="alaska_lng",
        polarity="easing",
        subtype="alaska_policy_signal",
        title="South Korea's Lee, Trump welcome progress in US strategic investment projects",
        source="Alaska Gasline Development Corporation",
        link="https://example.com/alaska-policy",
        published_utc="2026-09-23T00:00:00+00:00",
        published_epoch=1.0,
        official=True,
        event_id="fixture-alaska-policy",
    )
    rendered = v32._replace_evidence_text(
        '<b>Alaska Gasline Development Corporation</b> · South Korea\'s Lee, Trump welcome progress in US strategic investment projects',
        [{
            "category": "alaska_lng",
            "polarity": "easing",
            "subtype": "alaska_policy_signal",
            "event_id": "fixture-alaska-policy",
            "latest_epoch": 1.0,
            "evidence": [item],
            "verification": "공식 원문",
        }],
    )
    assert "알래스카가스라인개발공사(AGDC)" in rendered
    assert "정책 발언의 실질 변화" in rendered
    assert "해외 매체" not in rendered
    assert "LNG 수급 완화 관련 확정 변화" not in rendered


_self_validate_alaska_policy_render_v34()


def _asia_demand_groups(groups) -> list[dict]:
    return [group for group in groups if str(group.get("category") or "") == ASIA_DEMAND_CATEGORY]


def _build_asia_demand_body_v34(groups) -> str:
    asia = _asia_demand_groups(groups)
    primary = sorted(asia, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True)[0]
    verification = html.escape(str(primary.get("verification") or "분석 단계"))
    evidence = _evidence_lines_v34(asia)
    evidence_text = "\n".join(evidence) if evidence else "• 공개 근거 링크 확인 필요"
    return (
        "<b>한눈에</b>\n"
        "• <b>판정</b> 아시아 LNG 구조적 수요 재평가 신호\n"
        f"• <b>확인 수준</b> {verification} · 실제 LNG 소비 감소 확정과는 구분\n\n"
        "<b>무엇이 바뀌었나</b>\n"
        f"{evidence_text}\n\n"
        "<b>정확한 의미</b>\n"
        "• 공급 차질과 현물가격 급등이 반복되면서 아시아 신흥국이 LNG를 안정적 전환연료로 보는 전제가 흔들리는지 확인하는 신호입니다.\n"
        "• 재생에너지·수력·석탄·원전·국산가스·배관가스 전환이 실제 정책·발전계획·설비투자로 이어져야 구조적 수요 감소로 확정합니다.\n\n"
        "<b>투자 포인트</b>\n"
        "• LNG 생산자: 단기 가격 상승은 유리하지만 장기 아시아 수요 가정 하향 위험이 커질 수 있습니다.\n"
        "• 발전·전력: 국가별로 태양광·수력·석탄·원전 대체 경로가 달라 설비투자 방향을 따로 확인합니다.\n\n"
        "<b>다음 확인</b>\n"
        "• 장기구매계약 축소·취소, LNG 발전소 취소·연기, 국가 전력계획 변경, 실제 LNG 수입량 감소\n\n"
        "<b>핵심 한 줄</b> 단기 LNG 가격 강세와 장기 LNG 수요 파괴가 동시에 나타날 수 있는 구간입니다."
    )


def _self_validate_asia_demand_v34() -> None:
    item = core.NewsItem(
        category=ASIA_DEMAND_CATEGORY,
        polarity="worsening",
        subtype="asia_lng_cost_shock",
        title="A $7 Billion Gas Bill Sees Developing Asian Nations Sour on LNG",
        source="Bloomberg",
        link="https://example.com/asia-lng",
        published_utc="2026-09-14T00:00:00+00:00",
        published_epoch=1.0,
        official=False,
        event_id="fixture-asia-lng",
    )
    groups = confirmed_news_groups_v34([item])
    assert any(str(group.get("category") or "") == ASIA_DEMAND_CATEGORY for group in groups)
    body = _build_asia_demand_body_v34(groups)
    assert "구조적 수요 재평가" in body
    assert "실제 LNG 소비 감소 확정과는 구분" in body


_self_validate_asia_demand_v34()


def build_regular_alert_v34(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    alaska = _alaska_groups(groups)
    asia_demand = _asia_demand_groups(groups)
    if alaska:
        title = "🚨 알래스카 LNG·대체공급 프로젝트 변화"
        body = _build_alaska_body_v34(groups)
    elif asia_demand:
        title = "⚠️ 아시아 LNG 구조적 수요 재평가"
        body = _build_asia_demand_body_v34(groups)
    elif v33._fuel_groups(groups):
        title = "🚨 글로벌 연료·정제제품 공급경보"
        body = _build_fuel_body_v34(groups, quotes)
        body = v32._replace_evidence_text(body, groups)
    else:
        body = v32._replace_evidence_text(body, groups)
    leaks = v32._raw_english_evidence_remaining(body, groups)
    if leaks:
        raise RuntimeError("영문 기사 제목 송출 차단: " + " | ".join(leaks[:3]))
    metadata["version"] = 34
    metadata.setdefault("refined_fuel_watch", {})["output_guard"] = (
        "fuel-specific Korean evidence + Yahoo/Vitol Korean display + stale EIA fixed-value block"
    )
    metadata["alaska_lng_watch"] = {
        "category": ALASKA_CATEGORY,
        "keywords": ["Alaska LNG", "Polar LNG", "AGDC", "Glenfarne", "545억달러", "800억달러"],
        "headline_variants": ["Alaska + LNG", "$54.5bn", "$80bn", "LNG superpower"],
        "single_major_source_mode": "보도 단계만 허용",
        "interpretation_guard": "project timetable != current LNG supply outage",
        "self_validation": "Alaska LNG body must not reuse Qatar/Hormuz outage wording",
        "state_file_preserved": str(core.STATE_PATH),
    }
    metadata["alaska_policy_dedupe"] = {
        "rule": "policy reprints use a stable material-claim fingerprint instead of a 72-hour publication bucket",
        "stage": "alaska_policy_signal",
        "source_display": "official sources are named explicitly; no generic overseas-media label",
    }
    metadata["asia_lng_demand_watch"] = {
        "category": ASIA_DEMAND_CATEGORY,
        "signals": ["현물 조달비 급증", "LNG 장기수요 재평가", "발전원 전환", "장기계약 축소", "발전소 취소·연기"],
        "interpretation_guard": "analysis signal != confirmed demand destruction",
    }
    metadata["lng_relevance_guard"] = {
        "exclude": "oil/crude/refinery-only evidence cannot cross-confirm LNG/Hormuz groups",
        "keep": "direct LNG/natural-gas evidence or commodity-neutral chokepoint status; independent market threshold signals remain separate",
        "cross_source_rule": "two-source confirmation counts only LNG-relevant evidence items",
    }
    return title, body, metadata


def build_setup_test_v34(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 정제제품 경보의 근거기사 제목을 연료 사건 전용 한국어로 표시"
        "\n• 야후 파이낸스·비톨 등 사용자 노출 문구도 한국어 표기로 정리"
        "\n• EIA 9/4 숫자는 다음 공식 발표 뒤 자동으로 현재값 재사용을 차단"
        "\n• Alaska LNG·Polar LNG·AGDC·Glenfarne·545억달러·800억달러 신규 변화 감시"
        "\n• Alaska+LNG 및 $54.5bn·$80bn·LNG superpower 제목 표기도 동일 사건으로 감지"
        "\n• Alaska LNG 프로젝트는 주요 신뢰매체 1곳 보도도 '보도 단계'로 감지하고 공급 정상화 확정과 구분"
        "\n• Alaska LNG 프로젝트 뉴스는 현재 공급중단과 분리해 FID·자금조달·장기구매계약·착공 시간표로 해석"
        "\n• 사우디 동서 송유관·Yanbu 원유 전용 보도는 LNG 직접 근거가 없으면 LNG 경보에서 제외"
        "\n• 아시아 LNG 현물비용 급증·탈 LNG·발전원 전환은 구조적 수요 재평가 신호로 별도 감시"
        "\n• Alaska LNG는 자금조달·제재·추가 300만톤 장기구매계약·세제혜택·FID 변화를 별도 감시"
        "\n• Alaska LNG 정책 발언은 72시간 기사 버킷이 아니라 실질 발언 지문으로 중복방지"
        "\n• 백악관·미 에너지부·알래스카주·AGDC 등 공식 출처는 실제 기관명으로 표시"
    )
    metadata["version"] = 34
    metadata["alaska_lng_watch"] = True
    metadata["lng_relevance_guard"] = True
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v34
core.build_setup_test = build_setup_test_v34

if __name__ == "__main__":
    raise SystemExit(core.main())

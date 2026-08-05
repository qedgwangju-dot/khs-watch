
#!/usr/bin/env python3
"""FDA quality gate overlay for the GAMEJOA preopen radar.

This runner keeps the existing production chain intact, then applies a final
guardrail so generic Federal Register/FDA administrative documents do not get
promoted as high-impact biotech news.
"""

from __future__ import annotations

import gamejoa_preopen_news_radar_semisupply_runner as current


runner = current.runner
base = current.base
contract = current.contract
telegram = current.telegram

BIOTECH_SECTOR = "바이오/FDA"
FDA_MATERIAL_TIMELINE_TERMS = [
    "pdufa", "fda approves", "fda approval", "complete response letter", "crl",
    "clinical hold", "priority review", "accelerated approval", "advisory committee",
    "adcom", "biologics license application", "new drug application", "bla", "nda",
    "phase 3", "pivotal trial", "approval letter", "승인", "허가", "임상 3상",
]
FDA_LOW_IMPACT_ADMIN_TERMS = [
    "tobacco", "establishment registration", "product listing", "medical devices",
    "orthopedic devices", "classification of", "patent extension",
    "regulatory review period", "device classification", "food additive",
    "color additive", "medial knee implanted shock absorber", "vyalev",
]


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def is_federal_register_fda(text: str) -> bool:
    return "federal register" in text and ("fda" in text or "food and drug administration" in text)


def biotech_korean_title(text: str) -> str:
    if has_any(text, ["complete response letter", "crl"]):
        return "FDA CRL/거절: 바이오 승인 지연 리스크"
    if has_any(text, ["clinical hold"]):
        return "FDA 임상보류: 개발 시간표 지연 리스크"
    if has_any(text, ["advisory committee", "adcom", "biologics license application", "bla"]):
        return "FDA 자문위/BLA 일정: 바이오 심사 시간표 체크"
    if has_any(text, ["fda approves", "fda approval", "approval letter", "accelerated approval", "승인", "허가"]):
        return "FDA 승인/허가: 바이오 매출 전환 가능성 체크"
    if has_any(text, ["pdufa", "priority review", "nda", "new drug application"]):
        return "FDA 심사 일정: PDUFA/NDA 승인 시간표 체크"
    return "FDA/바이오 일정: 실제 매출·이익 전환 조건 체크"


def heat_grid_outage_alert(row: dict, now, text: str) -> dict | None:
    """Promote verified heat-driven distribution failures, not weather alone."""
    heat_terms = ("폭염", "극한 폭염", "극한폭염", "열대야", "전력 피크", "전력피크")
    outage_terms = ("아파트 정전", "아파트정전", "정전 사고", "정전사고", "대규모 정전")
    equipment_terms = (
        "변압기", "과부하", "노후 설비", "노후설비", "배전 설비", "배전설비",
        "수배전반", "전력 사용량", "전력사용량",
    )
    if not (
        any(term in text for term in heat_terms)
        and any(term in text for term in outage_terms)
        and any(term in text for term in equipment_terms)
    ):
        return None

    title = str(row.get("source_title") or row.get("title") or "").strip()
    body = str(row.get("source_body") or row.get("source_abstract") or "").strip()
    core = runner.article_sentences(
        body,
        ["폭염", "열대야", "정전", "변압기", "과부하", "전력 사용", "복구", "가구"],
        2,
        title=title,
    ) or title
    alert = runner.base_korean_business_alert(
        row, now, score=110, impacts=["돈 버는 능력", "시간표"]
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "investment_view": (
                "폭염이 냉방 전력피크와 배전 변압기 과부하로 이어진 실제 장애입니다. "
                "반복·광역화되면 노후 변압기 교체와 배전망 보강 투자 시점이 앞당겨집니다."
            ),
            "korea_market_impact": (
                "배전용 변압기·차단기·전선·전력기기와 ESS·수요관리 중 "
                "교체 발주나 전력망 투자에 직접 노출된 종목만 확인합니다."
            ),
            "sectors": ["배전용 변압기/차단기", "전선/전력기기", "ESS/전력수요관리"],
            "paths": ["전력 수요", "배전설비 과부하", "교체·보강 투자"],
            "korean_business_kind": "korea_heat_grid_outage",
            "supply_chain_theme": (
                "korea_heat_grid_outage:"
                f"{runner.korean_business_event_date(row)}:{base.norm(title)[:24]}"
            ),
        }
    )
    return alert


def enforce_fda_quality_gate() -> None:
    original_classify = contract.strict.classify

    def classify(row: dict, now):
        if runner.is_korean_business_row(row):
            # The Korean-news layer already fails closed: verified bodies use
            # source-faithful summaries and self-contained hard headlines are
            # marked 예비. Do not erase that fallback when a publisher blocks
            # article-body fetching in GitHub Actions.
            if row.get("body_verified"):
                title = str(row.get("source_title") or row.get("title") or "")
                body = str(row.get("source_body") or row.get("source_abstract") or "")
                heat_alert = heat_grid_outage_alert(row, now, f"{title} {body}".lower())
                if heat_alert:
                    return heat_alert
            return original_classify(row, now)
        text = base.source_content_text(row)
        alert = original_classify(row, now)
        if not alert:
            return None

        sectors = alert.get("sectors") or []
        is_biotech = BIOTECH_SECTOR in sectors or has_any(text, ["fda", "pdufa", "crl", "bla", "nda", "clinical trial"])
        if not is_biotech:
            return alert

        material_fda = has_any(text, FDA_MATERIAL_TIMELINE_TERMS)
        low_impact_admin = has_any(text, FDA_LOW_IMPACT_ADMIN_TERMS)
        fr_fda = is_federal_register_fda(text)

        if fr_fda and (low_impact_admin or not material_fda):
            return None
        if has_any(text, ["fda"]) and not material_fda and not has_any(text, ["commercial sales", "drug launch", "revenue", "profit", "earnings", "guidance", "pipeline priority", "big pharma"]):
            return None

        if material_fda:
            alert["news"] = biotech_korean_title(text)
            alert["biotech_material_fda_timeline"] = True
            if fr_fda:
                alert["sectors"] = [BIOTECH_SECTOR]
                alert["score"] = min(max(int(alert.get("score", 0)), 92), 96)
                alert["importance"] = "중"
        return alert

    contract.strict.classify = classify


enforce_fda_quality_gate()


if __name__ == "__main__":
    raise SystemExit(telegram.main())


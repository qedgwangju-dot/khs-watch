#!/usr/bin/env python3
"""FDA quality gate overlay for the GAMEJOA preopen radar.

This runner keeps the existing production chain intact, then applies a final
guardrail so generic Federal Register/FDA administrative documents do not get
promoted as high-impact biotech news.
"""

from __future__ import annotations

import gamejoa_preopen_news_radar_memory_antitrust_runner as current


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


def enforce_fda_quality_gate() -> None:
    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
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

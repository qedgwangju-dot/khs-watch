#!/usr/bin/env python3
"""Domestic nuclear siting overlay for the GAMEJOA preopen radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_transformer_tariff_runner as transformer

runner = transformer.runner
base = transformer.base
contract = transformer.contract
telegram = transformer.telegram
SECTOR = "국내 원전/SMR/입지·인허가"
CHECK = "SMR 2028년 표준설계인가, 대형 원전 2029년 인허가, 2037~2038년 완공 목표, 입지 선정 후속 일정, 방폐장·송전망·안전성 검증·주민 수용성 확인"
RISK_TABLE = "당장 수주 확정 아님: 입지 선정으로 밸류체인 기대가 살아나는 단계 / 방폐장·송전망: 인허가와 주민 수용성 병목 / 안전성 검증: 표준설계인가·건설허가 지연 시 모멘텀 약화 / 테마 과열: 실제 계약·공시·착공 전까지 매출 인식 시차 큼"
STRUCTURE_NOTE = "이번 이슈는 확정 수주보다 입지 선정으로 원전 밸류체인이 다시 살아났는지를 보는 단계입니다. 짧게는 테마 과열, 길게는 실제 인허가와 주민 수용성이 따라오는지 끝까지 확인해야 합니다."
NUCLEAR_TERMS = ["원전", "원자력", "신규 원전", "대형 원전", "smr", "small modular reactor", "소형모듈원전", "혁신형 smr", "i-smr", "i-SMR"]
TIMELINE_TERMS = ["입지", "후보지", "부지", "표준설계인가", "표준설계", "설계인가", "2028", "인허가", "건설허가", "운영허가", "2029", "2037", "2038", "완공", "상업운전"]
RISK_TERMS = ["방폐장", "방사성폐기물", "고준위", "사용후핵연료", "송전망", "계통", "안전성 검증", "안전성", "주민 수용성", "주민수용성", "주민", "환경영향평가"]
TRUSTED = ["연합뉴스", "yna", "정책브리핑", "korea.kr", "산업통상자원부", "motie", "motir", "원자력안전위원회", "nssc", "한국수력원자력", "khnp"]
QUERIES = [
    ("국내 원전 입지 선정", "신규 원전 입지 SMR 표준설계인가 2028 2029 2037 2038 방폐장 송전망 연합뉴스"),
    ("국내 SMR 인허가 일정", "SMR 표준설계인가 2028 대형 원전 인허가 2029 완공 2037 2038 주민 수용성"),
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def is_domestic_nuclear_siting(text: str) -> bool:
    trusted = has_any(text, TRUSTED) or has_any(text, ["yonhap", "korea.kr", "motie", "motir", "nssc"])
    return trusted and has_any(text, NUCLEAR_TERMS) and has_any(text, TIMELINE_TERMS) and has_any(text, RISK_TERMS)


def title_for(_: str) -> str:
    return "국내 원전 정책: 입지 선정·SMR 표준설계·대형원전 인허가 체크"


def interpretation(_: str) -> str:
    return "국내 원전 입지 선정은 당장 수주 확정이 아니라 원전 기자재·전력기기 밸류체인 기대가 다시 살아나는지 보는 단계입니다. 핵심은 2028년 SMR 표준설계인가, 2029년 대형 원전 인허가, 2037~2038년 완공 목표까지 실제 일정이 밀리지 않는지입니다."


def counter(_: str) -> str:
    return "SMR 표준설계인가와 대형 원전 인허가까지 시간이 남아 있고 방폐장·송전망·안전성 검증·주민 수용성이 병목입니다. 후보지나 입지 선정 뉴스만으로 확정 수주나 단기 실적을 바로 계산하면 과대해석입니다."


def enforce_domestic_nuclear_siting_watch() -> None:
    append_unique(base.QUERIES, QUERIES)
    append_unique(base.TERMS, NUCLEAR_TERMS + TIMELINE_TERMS + RISK_TERMS)
    append_unique(base.TRUSTED, TRUSTED + ["yonhap"])
    if not any(label == SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((SECTOR, NUCLEAR_TERMS + TIMELINE_TERMS + RISK_TERMS))
    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        alert = original_classify(row, now)
        if not is_domestic_nuclear_siting(text):
            return alert
        age = base.age_hours(row, now)
        score = 106 + (6 if age is not None and age <= 12 else 0)
        status = "확정" if row.get("layer") == "official" or has_any(text, ["정책브리핑", "korea.kr", "산업통상자원부", "motie", "motir", "원자력안전위원회", "nssc"]) else "예비"
        news = title_for(text)
        if not alert:
            alert = {
                "score": score,
                "importance": "상",
                "status": status,
                "news": news,
                "original_news": row.get("title") or news,
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "matched": [],
                "reflection": "중간",
                "korea_basis": "새 뉴스" if status == "확정" else "국내 언론 확산",
            }
        alert["score"] = max(int(alert.get("score", 0)), score)
        alert["importance"] = "상"
        alert["status"] = status
        alert["news"] = news
        alert["impacts"] = ["시간표", "수급", "할인율"]
        alert["paths"] = ["정책 타임라인", "밸류체인", "수급", "인허가 리스크"]
        alert["sectors"] = [SECTOR, "원전 기자재/전력기기", "송전망/전선", "두산에너빌리티/KHNP"]
        alert["counter"] = counter(text)
        alert["interpretation"] = interpretation(text)
        alert["failed_signal"] = "표준설계인가·인허가·방폐장·송전망·주민수용성 일정이 지연되거나 실제 계약·공시로 이어지지 않으면 테마 약화"
        alert["korea_nuclear_siting_policy_watch"] = True
        alert["domestic_nuclear_siting_check"] = CHECK
        alert["domestic_nuclear_siting_risk_table"] = RISK_TABLE
        alert["domestic_nuclear_siting_structure_note"] = STRUCTURE_NOTE
        return alert

    contract.strict.classify = classify


ORIGINAL_KOREAN_TITLE = telegram.korean_title
ORIGINAL_RELATED_TEXT = runner.related_text
ORIGINAL_DISPLAY_NEWS = runner.display_news
ORIGINAL_COMPACT_ALERT = runner.compact_alert


def korean_title(alert: dict) -> str:
    if alert.get("korea_nuclear_siting_policy_watch") or SECTOR in (alert.get("sectors") or []):
        return alert.get("news") or "국내 원전 정책: 입지 선정·SMR 표준설계·대형원전 인허가 체크"
    return ORIGINAL_KOREAN_TITLE(alert)


def related_text(alert: dict, fred: dict, te: dict) -> str:
    base_text = ORIGINAL_RELATED_TEXT(alert, fred, te)
    extra = []
    if alert.get("korea_nuclear_siting_policy_watch"):
        extra = ["SMR 표준설계인가 2028", "대형원전 인허가 2029", "2037~2038 완공 목표", "방폐장", "송전망", "주민수용성", "034020.KS", "KHNP"]
    parts = [] if base_text == "확인 가능한 직접 지표 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
    return ", ".join(dict.fromkeys(parts + extra)) or "확인 가능한 직접 지표 없음"


def display_news(alert: dict) -> str:
    if alert.get("korea_nuclear_siting_policy_watch"):
        return alert.get("news") or "국내 원전 정책: 입지 선정·SMR 표준설계·대형원전 인허가 체크"
    return ORIGINAL_DISPLAY_NEWS(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("korea_nuclear_siting_policy_watch") and "국내 원전 입지·인허가 체크:" not in text:
        marker = "\n- 실패 신호:"
        check = f"\n- 국내 원전 입지·인허가 체크: {alert.get('domestic_nuclear_siting_check') or CHECK}"
        if alert.get("domestic_nuclear_siting_risk_table"):
            check += f"\n- 체크할 리스크: {alert.get('domestic_nuclear_siting_risk_table')}"
        if alert.get("domestic_nuclear_siting_structure_note"):
            check += f"\n- 구조 변화: {alert.get('domestic_nuclear_siting_structure_note')}"
        return text.replace(marker, check + marker, 1)
    return text


enforce_domestic_nuclear_siting_watch()
telegram.korean_title = korean_title
runner.related_text = related_text
runner.display_news = display_news
runner.compact_alert = compact_alert

if __name__ == "__main__":
    raise SystemExit(telegram.main())

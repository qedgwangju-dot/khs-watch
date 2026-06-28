#!/usr/bin/env python3
"""Domestic telecom-fee policy overlay for the preopen radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_nuclear_turbine_runner as power


runner = power.runner
base = power.base
contract = power.contract
telegram = power.telegram

TELECOM_SECTOR = "국내 통신정책/통신3사/IDC"
TELECOM_CHECK = (
    "통신비 인하 압박, 5G 중간요금제·저가요금제, 선택약정 할인율, 단통법/지원금, "
    "ARPU·마진·배당 매력, AI 데이터센터 수요·전기료·임대단가 확인"
)
TELECOM_RISK_TABLE = (
    "통신비 인하 정책 강화: ARPU 하락→이익 감소 가능성 중간 / "
    "AI 데이터센터 수요 둔화: GPU 투자 회수 지연 가능성 낮음 / "
    "금리 인하 지연: 배당주 매력도 감소 가능성 중간 / "
    "데이터센터 과잉 공급: 임대 단가 하락 가능성 낮음~중간 / "
    "전기료 인상: 데이터센터 운영비 증가 가능성 중간"
)
TELECOM_STRUCTURE_NOTE = (
    "통신비 인하 압박은 오래된 리스크지만 AI 인프라·IDC·클라우드 매출 비중이 커질수록 "
    "통신사 실적에서 통신요금 의존도는 낮아집니다. 핵심은 요금 규제보다 수익 구조 전환 속도입니다."
)
TELECOM_ACTOR_TERMS = [
    "과학기술정보통신부", "과기정통부", "방송통신위원회", "방통위", "정부",
    "국회", "통신3사", "SK텔레콤", "KT", "LG유플러스", "msit", "kcc",
]
TELECOM_POLICY_TERMS = [
    "가계통신비", "통신비", "통신요금", "요금제", "5g 요금제", "5G 요금제",
    "중간요금제", "2만 원대 5G", "2만원대 5G", "선택약정", "선택약정 할인",
    "할인율", "단말기유통법", "단통법", "공시지원금", "전환지원금",
    "추가지원금", "알뜰폰", "도매대가", "최적요금제", "번호이동",
]
TELECOM_RISK_TERMS = [
    "arpu", "가입자당 평균매출", "가입자당평균매출", "ai 데이터센터",
    "데이터센터", "idc", "gpu 투자", "전기료", "전기요금", "전력요금",
    "금리 인하 지연", "배당", "배당주", "임대 단가", "과잉 공급",
]
TELECOM_EVENT_TERMS = [
    "인하", "부담 완화", "확대", "개편", "시행", "의무", "검토", "추진",
    "발표", "정책", "규제", "압박", "완화", "지원금", "할인율",
]
TELECOM_QUERIES = [
    (
        "국내 통신비 인하 정책",
        "과기정통부 방송통신위원회 통신비 인하 선택약정 할인율 5G 요금제 SK텔레콤 KT LG유플러스 정책브리핑 연합뉴스",
    ),
    (
        "통신3사 ARPU 요금제 리스크",
        "SK텔레콤 KT LG유플러스 ARPU 요금제 통신비 인하 선택약정 할인율 실적 마진 연합뉴스 블룸버그",
    ),
    (
        "통신 IDC 데이터센터 전기료 리스크",
        "통신사 IDC 데이터센터 전기료 전기요금 AI 데이터센터 임대 단가 과잉 공급 SK텔레콤 KT LG유플러스",
    ),
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def is_domestic_telecom_policy(text: str) -> bool:
    has_actor = has_any(text, TELECOM_ACTOR_TERMS) or has_any(text, ["정책브리핑", "korea.kr", "kcc.go.kr"])
    has_policy = has_any(text, TELECOM_POLICY_TERMS)
    has_event = has_any(text, TELECOM_EVENT_TERMS)
    return has_actor and has_policy and has_event


def has_telecom_idc_risk(text: str) -> bool:
    has_actor = has_any(text, ["SK텔레콤", "KT", "LG유플러스", "통신3사", "telecom", "telco"])
    has_risk = has_any(text, TELECOM_RISK_TERMS)
    return has_actor and has_risk


def telecom_title(text: str) -> str:
    if has_any(text, ["선택약정", "할인율"]):
        return "국내 통신정책: 선택약정 할인율·통신비 인하 압박 체크"
    if has_any(text, ["5g 요금제", "5G 요금제", "중간요금제", "2만 원대 5G", "2만원대 5G"]):
        return "국내 통신정책: 5G 요금제 개편·ARPU 압박 체크"
    if has_any(text, ["전기료", "전기요금", "전력요금"]):
        return "통신 IDC 리스크: 전기료 상승·데이터센터 마진 체크"
    if has_any(text, ["과잉 공급", "임대 단가"]):
        return "통신 IDC 리스크: 데이터센터 과잉공급·임대단가 체크"
    return "국내 통신정책: 통신비 인하 압박·ARPU 리스크 체크"


def telecom_interpretation(text: str) -> str:
    if is_domestic_telecom_policy(text):
        return (
            "정부의 통신비 인하 압박은 통신3사의 ARPU와 무선서비스 마진을 직접 건드리는 국내 정책 변수입니다. "
            "다만 AI 인프라·IDC·클라우드 매출 비중이 커질수록 통신요금 의존도는 낮아지므로, 더 중요한 포인트는 수익 구조 전환 속도입니다."
        )
    return (
        "통신사의 AI 데이터센터·IDC 성장 옵션은 전기료, 임대단가, GPU 투자 회수 속도에 민감합니다. "
        "AI 인프라 매출 비중이 커질수록 통신비 인하 리스크를 일부 흡수할 수 있어 배당 매력과 성장 옵션을 분리해서 봐야 합니다."
    )


def telecom_counter(text: str) -> str:
    if is_domestic_telecom_policy(text):
        return "정책 발표가 권고·검토 단계에 그치거나 AI 인프라·IDC·클라우드 매출 비중 확대가 요금 규제 부담을 상쇄하면 ARPU 리스크는 과대해석일 수 있습니다."
    return "IDC 수요 둔화·전기료 상승이 실제 실적 가이던스나 CAPEX 조정으로 확인되지 않으면 단기 리스크 프리미엄에 그칠 수 있습니다."


def enforce_telecom_policy_watch() -> None:
    append_unique(base.QUERIES, TELECOM_QUERIES)
    append_unique(base.TERMS, TELECOM_ACTOR_TERMS + TELECOM_POLICY_TERMS + TELECOM_RISK_TERMS + TELECOM_EVENT_TERMS)
    append_unique(base.TRUSTED, [
        "정책브리핑", "korea.kr", "과학기술정보통신부", "방송통신위원회",
        "연합뉴스", "yna", "yonhap", "korea herald",
    ])
    if not any(label == TELECOM_SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((TELECOM_SECTOR, TELECOM_ACTOR_TERMS + TELECOM_POLICY_TERMS + TELECOM_RISK_TERMS))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        telecom_policy = is_domestic_telecom_policy(text)
        idc_risk = has_telecom_idc_risk(text)
        alert = original_classify(row, now)
        if not telecom_policy and not idc_risk:
            return alert

        age = base.age_hours(row, now)
        status = "확정" if row.get("layer") == "official" or has_any(text, ["정책브리핑", "korea.kr", "kcc.go.kr"]) else "공식 확인 전"
        impacts = ["돈 버는 능력", "할인율", "시간표"] if telecom_policy else ["돈 버는 능력", "할인율"]
        paths = ["이익", "할인율", "정책 타임라인", "수익구조 전환"] if telecom_policy else ["이익", "할인율", "공급·수요", "수익구조 전환"]
        score = 102 if telecom_policy else 84
        if age is not None and age <= 12:
            score += 6

        if not alert:
            alert = {
                "score": score,
                "importance": "상" if score >= 100 else "중",
                "status": status,
                "news": telecom_title(text),
                "original_news": row.get("title") or telecom_title(text),
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": impacts[:],
                "paths": paths[:],
                "sectors": [TELECOM_SECTOR],
                "matched": [],
                "reflection": "중간",
                "counter": telecom_counter(text),
                "interpretation": telecom_interpretation(text),
                "failed_signal": "요금 인하가 권고에 그치거나 AI 인프라·IDC 매출 비중 확대가 ARPU·마진 압박을 상쇄하면 규제 악재 약화",
                "korea_basis": "새 뉴스" if status == "확정" else "외신/국내 언론 확산",
            }
        else:
            alert["score"] = max(int(alert.get("score", 0)), score)
            alert["importance"] = "상" if int(alert["score"]) >= 100 else "중"
            alert["status"] = alert.get("status") or status
            alert["news"] = telecom_title(text)
            alert["original_news"] = alert.get("original_news") or row.get("title") or telecom_title(text)
            alert["impacts"] = impacts[:]
            alert["paths"] = paths[:]
            alert["sectors"] = [TELECOM_SECTOR]
            alert["counter"] = telecom_counter(text)
            alert["interpretation"] = telecom_interpretation(text)
            alert["failed_signal"] = "요금 인하가 권고에 그치거나 AI 인프라·IDC 매출 비중 확대가 ARPU·마진 압박을 상쇄하면 규제 악재 약화"

        alert["domestic_telecom_policy_watch"] = True
        alert["telecom_policy_check"] = TELECOM_CHECK
        alert["telecom_risk_table"] = TELECOM_RISK_TABLE
        alert["telecom_structure_note"] = TELECOM_STRUCTURE_NOTE
        return alert

    contract.strict.classify = classify


ORIGINAL_RELATED_TEXT = runner.related_text
ORIGINAL_DISPLAY_NEWS = runner.display_news
ORIGINAL_COMPACT_ALERT = runner.compact_alert
ORIGINAL_KOREAN_TITLE = telegram.korean_title


def korean_title(alert: dict) -> str:
    sectors = alert.get("sectors") or []
    if alert.get("domestic_telecom_policy_watch") or TELECOM_SECTOR in sectors:
        return alert.get("news") or "국내 통신정책: 통신비 인하 압박·ARPU 리스크 체크"
    return ORIGINAL_KOREAN_TITLE(alert)


def related_text(alert: dict, fred: dict, te: dict) -> str:
    base_text = ORIGINAL_RELATED_TEXT(alert, fred, te)
    extra = []
    if alert.get("domestic_telecom_policy_watch"):
        extra = ["SK텔레콤", "KT", "LG유플러스", "ARPU", "선택약정", "5G 요금제", "IDC", "전기요금", "배당수익률"]
    parts = [] if base_text == "확인 가능한 직접 지표 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
    return ", ".join(dict.fromkeys(parts + extra)) or "확인 가능한 직접 지표 없음"


def display_news(alert: dict) -> str:
    if alert.get("domestic_telecom_policy_watch"):
        return alert.get("news") or "국내 통신정책: 통신비 인하 압박·ARPU 리스크 체크"
    return ORIGINAL_DISPLAY_NEWS(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("domestic_telecom_policy_watch") and "국내 통신정책 체크:" not in text:
        marker = "\n- 실패 신호:"
        check = f"\n- 국내 통신정책 체크: {alert.get('telecom_policy_check') or TELECOM_CHECK}"
        risk_table = alert.get("telecom_risk_table")
        if risk_table:
            check += f"\n- 체크할 리스크: {risk_table}"
        structure_note = alert.get("telecom_structure_note")
        if structure_note:
            check += f"\n- 구조 변화: {structure_note}"
        return text.replace(marker, check + marker, 1)
    return text


enforce_telecom_policy_watch()
telegram.korean_title = korean_title
runner.related_text = related_text
runner.display_news = display_news
runner.compact_alert = compact_alert


if __name__ == "__main__":
    raise SystemExit(telegram.main())

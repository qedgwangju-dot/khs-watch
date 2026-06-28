#!/usr/bin/env python3
"""Transformer tariff overlay for the GAMEJOA preopen radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_domestic_telecom_runner as domestic


runner = domestic.runner
base = domestic.base
contract = domestic.contract
telegram = domestic.telegram

SECTORS = ["전력기기/변압기", "관세/수출주", "전력망/데이터센터"]
CHECK = (
    "미국 Section 232/철강·알루미늄 파생상품 적용에서 대형 변압기·전력망 장비 관세율 "
    "25%→15% 적용 여부, 품목코드, 시행일, 예외·원산지 요건, 기존 계약 가격 조정 가능성 확인"
)
RISK_TABLE = (
    "관세율 인하: 한국 변압기 가격경쟁력·수주마진 개선 가능 / "
    "품목코드·원산지·예외 미확정: 직접 수혜 제한 / "
    "공급능력·납기 병목: 수주 기대 과열 가능 / "
    "4월 공식 문서 재해석이면 6월 보도 신규성은 낮을 수 있음"
)
STRUCTURE_NOTE = (
    "핵심은 관세율 숫자 자체보다 미국 전력망·AI 데이터센터 투자에서 한국 전력기기 업체의 "
    "가격경쟁력, 수주 가능성, 매출 인식 시간이 바뀌는지입니다."
)
EQUIPMENT_TERMS = [
    "transformer", "transformers", "large power transformer", "power transformer",
    "distribution transformer", "electrical grid equipment", "electrical equipment",
    "electrical steel", "grain-oriented electrical steel", "GOES", "대형 변압기", "변압기",
    "전력기기", "전력 기자재", "전력망 장비", "전기강판",
]
POLICY_TERMS = [
    "tariff", "tariffs", "duty", "duties", "section 232", "232조", "관세", "상호관세",
    "철강", "알루미늄", "파생상품", "25%", "25 percent", "15%", "15 percent",
    "인하", "lower", "lowered", "reduce", "reduced", "cut", "조정",
]
VALUE_TERMS = [
    "한국", "korea", "효성", "hyosung", "포스코", "posco", "hd현대일렉트릭",
    "hyundai electric", "ls electric", "일진전기", "대한전선", "white house",
    "federal register", "백악관",
]
QUERIES = [
    ("미국 대형 변압기 관세", "미국 대형 변압기 관세 25% 15% Section 232 효성 포스코 HD현대일렉트릭 전력기기"),
    ("미국 전력기기 관세 정책", "United States transformer tariff 25% 15% Section 232 electrical grid equipment Korea Hyosung POSCO"),
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def is_transformer_tariff(text: str) -> bool:
    return has_any(text, EQUIPMENT_TERMS) and has_any(text, POLICY_TERMS) and has_any(text, VALUE_TERMS)


def title_for(text: str) -> str:
    if has_any(text, ["25%", "25 percent"]) and has_any(text, ["15%", "15 percent", "인하", "lower", "reduced"]):
        return "미국 변압기 관세 정책: 대형 변압기 25%→15% 적용 체크"
    return "미국 변압기 관세 정책: Section 232 전력기기 수혜 체크"


def interpretation(_: str) -> str:
    return (
        "변압기 관세율 인하는 한국 전력기기 업체의 미국향 가격경쟁력과 수주 마진 기대를 직접 건드리는 정책 변수입니다. "
        "다만 공식 시행일, 품목코드, 원산지 요건이 확인돼야 실제 매출·마진 변화로 연결됩니다."
    )


def counter(_: str) -> str:
    return (
        "품목코드, 실제 적용세율, 시행일, 원산지 요건, 기존 계약 가격 조정 여부가 확인되지 않으면 수혜가 제한될 수 있습니다. "
        "4월 공식 문서의 재해석이면 새 정책 발표가 아니라 국내 재확산 재료입니다."
    )


def enforce_transformer_tariff_watch() -> None:
    append_unique(base.QUERIES, QUERIES)
    append_unique(base.TERMS, EQUIPMENT_TERMS + POLICY_TERMS + VALUE_TERMS)
    append_unique(base.TRUSTED, ["whitehouse.gov", "federalregister.gov", "Federal Register", "백악관", "더구루", "the guru"])
    for sector in SECTORS:
        if not any(label == sector for label, _ in base.SECTORS):
            base.SECTORS.append((sector, EQUIPMENT_TERMS + POLICY_TERMS + VALUE_TERMS))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        alert = original_classify(row, now)
        if not is_transformer_tariff(text):
            return alert

        age = base.age_hours(row, now)
        score = 108 + (6 if age is not None and age <= 12 else 0)
        status = "확정" if row.get("layer") == "official" or has_any(text, ["whitehouse.gov", "federalregister.gov", "Federal Register", "백악관"]) else "예비"
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
                "korea_basis": "새 뉴스" if status == "확정" else "외신/국내 언론 확산",
            }
        alert["score"] = max(int(alert.get("score", 0)), score)
        alert["importance"] = "상"
        alert["status"] = status
        alert["news"] = news
        alert["impacts"] = ["돈 버는 능력", "할인율", "수급", "시간표"]
        alert["paths"] = ["이익", "정책 타임라인", "밸류체인", "수급", "계약 가시성"]
        alert["sectors"] = SECTORS[:]
        alert["counter"] = counter(text)
        alert["interpretation"] = interpretation(text)
        alert["failed_signal"] = "품목코드·시행일·원산지 요건이 맞지 않거나 4월 공식 문서 재해석에 그치면 수주·마진 재평가 약화"
        alert["transformer_tariff_policy_watch"] = True
        alert["transformer_tariff_check"] = CHECK
        alert["transformer_tariff_risk_table"] = RISK_TABLE
        alert["transformer_tariff_structure_note"] = STRUCTURE_NOTE
        return alert

    contract.strict.classify = classify


ORIGINAL_KOREAN_TITLE = telegram.korean_title
ORIGINAL_RELATED_TEXT = runner.related_text
ORIGINAL_DISPLAY_NEWS = runner.display_news
ORIGINAL_COMPACT_ALERT = runner.compact_alert


def korean_title(alert: dict) -> str:
    if alert.get("transformer_tariff_policy_watch") or any(sector in (alert.get("sectors") or []) for sector in SECTORS):
        return alert.get("news") or "미국 변압기 관세 정책: 대형 변압기 25%→15% 적용 체크"
    return ORIGINAL_KOREAN_TITLE(alert)


def related_text(alert: dict, fred: dict, te: dict) -> str:
    base_text = ORIGINAL_RELATED_TEXT(alert, fred, te)
    extra = []
    if alert.get("transformer_tariff_policy_watch"):
        extra = ["대형 변압기", "전력기기", "Section 232", "관세 25%→15%", "효성중공업", "HD현대일렉트릭", "LS ELECTRIC", "포스코 전기강판"]
    parts = [] if base_text == "확인 가능한 직접 지표 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
    return ", ".join(dict.fromkeys(parts + extra)) or "확인 가능한 직접 지표 없음"


def display_news(alert: dict) -> str:
    if alert.get("transformer_tariff_policy_watch"):
        return alert.get("news") or "미국 변압기 관세 정책: 대형 변압기 25%→15% 적용 체크"
    return ORIGINAL_DISPLAY_NEWS(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("transformer_tariff_policy_watch") and "변압기 관세 체크:" not in text:
        marker = "\n- 실패 신호:"
        check = f"\n- 변압기 관세 체크: {alert.get('transformer_tariff_check') or CHECK}"
        if alert.get("transformer_tariff_risk_table"):
            check += f"\n- 체크할 리스크: {alert.get('transformer_tariff_risk_table')}"
        if alert.get("transformer_tariff_structure_note"):
            check += f"\n- 구조 변화: {alert.get('transformer_tariff_structure_note')}"
        return text.replace(marker, check + marker, 1)
    return text


enforce_transformer_tariff_watch()
telegram.korean_title = korean_title
runner.related_text = related_text
runner.display_news = display_news
runner.compact_alert = compact_alert


if __name__ == "__main__":
    raise SystemExit(telegram.main())

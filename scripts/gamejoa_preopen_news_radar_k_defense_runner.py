#!/usr/bin/env python3
"""K-defense overlay for the GAMEJOA preopen news radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_full_compact_runner as runner


base = runner.base
contract = runner.contract
telegram = runner.telegram

K_DEFENSE_DART_CODES = {"012450", "079550", "047810", "064350", "272210"}
K_DEFENSE_SECTOR = "K-방산/항공우주"
K_DEFENSE_CHECK = "계약금액·기간·상대국/상대방·공시 여부·양산/인도 일정·수출허가 확인"
K_DEFENSE_COMPANY_TERMS = [
    "hanwha aerospace", "한화에어로스페이스",
    "lig nex1", "lig넥스원", "lig 넥스원",
    "korea aerospace industries", "한국항공우주", "kai",
    "hyundai rotem", "현대로템",
    "hanwha systems", "한화시스템",
]
K_DEFENSE_SYSTEM_TERMS = [
    "k9", "k9 thunder", "k9 자주포", "chunmoo", "천무", "redback", "레드백",
    "cheongung", "cheongung ii", "km-sam", "천궁", "천궁Ⅱ", "천궁ii", "천궁2",
    "hyungung", "현궁", "guided missile", "유도무기", "fa-50", "kf-21",
    "surion", "수리온", "k2 tank", "k2 전차", "wheeled armored vehicle",
    "차륜형장갑차", "radar", "레이더", "satellite", "위성", "electronic warfare", "전자전",
]
K_DEFENSE_EVENT_TERMS = [
    "arms export", "contract", "defense contract", "defense order", "delivery",
    "export", "loi", "mass production", "mou", "order", "procurement",
    "selected", "supply agreement", "tender", "wins",
    "계약", "공급계약", "도입", "무기체계", "방산", "수주", "수출", "양산",
    "유도무기", "입찰", "전력화", "조달", "체결",
]
K_DEFENSE_QUERIES = [
    (
        "K-방산 수출/수주",
        "Hanwha Aerospace K9 Thunder Chunmoo Redback LIG Nex1 Cheongung II KM-SAM Hyungung KAI FA-50 KF-21 Surion Hyundai Rotem K2 tank Hanwha Systems radar satellite electronic warfare defense contract order export Reuters Bloomberg Yonhap DART",
    ),
    (
        "K-방산 무기체계",
        "한화에어로스페이스 K9 자주포 천무 레드백 LIG넥스원 천궁Ⅱ 현궁 유도무기 한국항공우주 FA-50 KF-21 수리온 현대로템 K2 전차 차륜형장갑차 한화시스템 레이더 위성 전자전 수주 계약 수출 공시",
    ),
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def k_defense_title(text: str) -> str:
    if has_any(text, ["hanwha aerospace", "한화에어로스페이스", "k9", "k9 thunder", "k9 자주포", "chunmoo", "천무", "redback", "레드백"]):
        return "한화에어로스페이스 K9·천무·레드백 수출/수주 체크"
    if has_any(text, ["lig nex1", "lig넥스원", "lig 넥스원", "cheongung", "cheongung ii", "km-sam", "천궁", "천궁Ⅱ", "천궁2", "hyungung", "현궁", "guided missile", "유도무기"]):
        return "LIG넥스원 천궁Ⅱ·현궁·유도무기 수출/수주 체크"
    if has_any(text, ["korea aerospace industries", "한국항공우주", "kai", "fa-50", "kf-21", "surion", "수리온"]):
        return "한국항공우주 FA-50·KF-21·수리온 수출/수주 체크"
    if has_any(text, ["hyundai rotem", "현대로템", "k2 tank", "k2 전차", "wheeled armored vehicle", "차륜형장갑차"]):
        return "현대로템 K2 전차·차륜형장갑차 수출/수주 체크"
    if has_any(text, ["hanwha systems", "한화시스템", "radar", "레이더", "satellite", "위성", "electronic warfare", "전자전"]):
        return "한화시스템 레이더·위성·전자전 수주/정책 체크"
    return "K-방산 무기체계 수출/수주 체크"


def enforce_k_defense_watch() -> None:
    append_unique(base.QUERIES, K_DEFENSE_QUERIES)
    append_unique(base.TERMS, K_DEFENSE_COMPANY_TERMS + K_DEFENSE_SYSTEM_TERMS + K_DEFENSE_EVENT_TERMS)
    append_unique(base.TRUSTED, ["yonhap", "yna", "korea herald", "korea joongang daily", "opendart", "dart"])
    if hasattr(base, "DART_WATCH_STOCK_CODES"):
        base.DART_WATCH_STOCK_CODES.update(K_DEFENSE_DART_CODES)
    if not any(label == K_DEFENSE_SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((K_DEFENSE_SECTOR, K_DEFENSE_COMPANY_TERMS + K_DEFENSE_SYSTEM_TERMS))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        has_k_defense = has_any(text, K_DEFENSE_COMPANY_TERMS + K_DEFENSE_SYSTEM_TERMS)
        has_event = has_any(text, K_DEFENSE_EVENT_TERMS)
        alert = original_classify(row, now)
        if not has_k_defense or (not has_event and not alert):
            return alert

        is_soft_deal = has_any(text, ["mou", "loi", "양해각서"])
        hard_contract = has_any(text, ["contract", "defense contract", "order", "procurement", "supply agreement", "계약", "공급계약", "수주", "수출", "조달", "체결"]) and not is_soft_deal
        age = base.age_hours(row, now)
        status = "확정" if row.get("layer") == "official" else "공식 확인 전"
        impacts = ["시간표", "수급"] if is_soft_deal else ["돈 버는 능력", "수급", "시간표"]
        paths = ["계약 가시성", "공급·수요", "정책 타임라인"] if not is_soft_deal else ["정책 타임라인", "테마 수급"]
        title = k_defense_title(text)

        if not alert:
            score = 106 if hard_contract else 88
            if age is not None and age <= 12:
                score += 8
            alert = {
                "score": score,
                "importance": "상" if score >= 100 else "중",
                "status": status,
                "news": title,
                "original_news": row.get("title") or title,
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": impacts[:],
                "paths": paths[:],
                "sectors": [K_DEFENSE_SECTOR],
                "matched": [],
                "reflection": "낮음" if age is not None and age <= 6 else "중간",
                "counter": "MOU/LOI는 확정 매출이 아니며 본계약·금액·인도 일정·수출허가 확인 전 과대해석 가능" if is_soft_deal else "계약금액, 기간, 상대국 예산, 수출허가, 양산·인도 일정 확인 전까지 실제 매출 인식에는 시차가 있습니다.",
                "interpretation": "K-방산 무기체계 수주·수출은 국내 방산주의 수주잔고와 밸류체인 수급을 바로 흔들 수 있는 재료입니다.",
                "failed_signal": "공시·공식 발표·상대국 예산·수출허가·납기 확인이 뒤따르지 않으면 테마성 반응으로 약화",
                "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
            }
        else:
            alert["score"] = max(int(alert.get("score", 0)), 106 if hard_contract else 88)
            alert["importance"] = "상" if int(alert["score"]) >= 100 else "중"
            alert["status"] = alert.get("status") or status
            alert["news"] = title
            alert["original_news"] = alert.get("original_news") or row.get("title") or title
            append_unique(alert.setdefault("impacts", []), impacts)
            append_unique(alert.setdefault("paths", []), paths)
            append_unique(alert.setdefault("sectors", []), [K_DEFENSE_SECTOR])
            alert["counter"] = "MOU/LOI는 확정 매출이 아니며 본계약·금액·인도 일정·수출허가 확인 전 과대해석 가능" if is_soft_deal else "계약금액, 기간, 상대국 예산, 수출허가, 양산·인도 일정 확인 전까지 실제 매출 인식에는 시차가 있습니다."
            alert["interpretation"] = "K-방산 무기체계 수주·수출은 국내 방산주의 수주잔고와 밸류체인 수급을 바로 흔들 수 있는 재료입니다."
            alert["failed_signal"] = "공시·공식 발표·상대국 예산·수출허가·납기 확인이 뒤따르지 않으면 테마성 반응으로 약화"

        alert["k_defense_watch"] = True
        alert["k_defense_check"] = K_DEFENSE_CHECK
        return alert

    contract.strict.classify = classify


ORIGINAL_KOREAN_TITLE = telegram.korean_title
ORIGINAL_COMPACT_ALERT = runner.compact_alert


def korean_title(alert: dict) -> str:
    sectors = alert.get("sectors") or []
    if alert.get("k_defense_watch") or K_DEFENSE_SECTOR in sectors:
        return alert.get("news") or k_defense_title(base.norm(alert.get("original_news") or ""))
    return ORIGINAL_KOREAN_TITLE(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("k_defense_watch") and "K-방산 체크:" not in text:
        marker = "\n- 실패 신호:"
        check = f"\n- K-방산 체크: {alert.get('k_defense_check') or K_DEFENSE_CHECK}"
        return text.replace(marker, check + marker, 1)
    return text


enforce_k_defense_watch()
telegram.korean_title = korean_title
runner.compact_alert = compact_alert


if __name__ == "__main__":
    raise SystemExit(telegram.main())

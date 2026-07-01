#!/usr/bin/env python3
"""K-nuclear, SMR, and gas-turbine overlay for the preopen radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_grid_policy_runner as grid


runner = grid.runner
base = grid.base
contract = grid.contract
telegram = grid.telegram

K_POWER_SECTOR = "원전/SMR/가스터빈/두산에너빌리티"
K_POWER_CHECK = (
    "체코 원전 최종계약·계약규모, i-SMR 상용화 일정, 금리 인하, "
    "중동 원전 추가수주, SpaceX 가스터빈 발주·두산 수주 공시 확인"
)
K_POWER_CHECKPOINTS = (
    "체코 원전 최종 계약: 2027년 이후 예상·계약 규모 확정 시 모멘텀 / "
    "SMR 기술 상용화: 2030년 전후·한국형 i-SMR 개발 진행 / "
    "금리 인하: 인프라 프로젝트 밸류에이션 호재 / "
    "중동 추가 수주: 사우디 등 원전 도입 검토 / "
    "SpaceX 가스터빈 발주: 두산에너빌리티 직접 수주 확인 시 모멘텀"
)
K_POWER_TERMS = [
    "doosan enerbility", "doosan heavy", "두산에너빌리티", "두산중공업",
    "khnp", "korea hydro", "한국수력원자력", "한수원",
    "nuclear power", "nuclear reactor", "원전", "원자력",
    "smr", "small modular reactor", "i-smr", "혁신형 smr", "소형모듈원전",
    "gas turbine", "gas turbines", "가스터빈",
    "spacex", "space x", "스페이스x", "스페이스X",
    "czech", "czech republic", "dukovany", "체코", "두코바니",
    "saudi", "saudi arabia", "middle east", "uae", "사우디", "중동", "아랍에미리트",
]
K_POWER_EVENT_TERMS = [
    "award", "awarded", "contract", "contract signed", "contract value", "final contract",
    "order", "procurement", "selected", "supply agreement", "tender", "wins",
    "commercialization", "commercial operation", "design approval", "license", "licensing",
    "rate cut", "interest rate cut", "fed cuts", "lower rates",
    "계약", "계약규모", "계약금액", "공급계약", "발주", "본계약", "선정", "수주", "입찰", "체결",
    "기술 상용화", "상용화", "설계인가", "인허가", "금리 인하", "금리인하",
]
K_POWER_QUERIES = [
    (
        "두산에너빌리티 SpaceX 가스터빈",
        "SpaceX gas turbine order contract procurement Doosan Enerbility power generation turbine Reuters Bloomberg CNBC Yonhap",
    ),
    (
        "체코 원전 최종계약",
        "Czech nuclear final contract Dukovany KHNP Korea Hydro Nuclear Power Doosan Enerbility contract value Reuters Bloomberg Yonhap",
    ),
    (
        "SMR i-SMR 상용화",
        "SMR commercialization i-SMR Korea small modular reactor design approval licensing 2030 Doosan Enerbility Reuters Bloomberg Yonhap",
    ),
    (
        "중동 원전 추가수주",
        "Saudi Arabia Middle East nuclear power plant tender reactor procurement KHNP Doosan Enerbility UAE Reuters Bloomberg Yonhap",
    ),
    (
        "원전 인프라 금리인하",
        "rate cut infrastructure project finance nuclear power valuation utilities capex Doosan Enerbility Reuters Bloomberg CNBC",
    ),
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def power_flags(text: str) -> dict[str, bool]:
    return {
        "spacex": has_any(text, ["spacex", "space x", "스페이스x", "스페이스X"])
        and has_any(text, ["gas turbine", "gas turbines", "가스터빈"])
        and has_any(text, ["doosan enerbility", "두산에너빌리티", "doosan heavy", "두산중공업"]),
        "czech": has_any(text, ["czech", "czech republic", "dukovany", "체코", "두코바니"])
        and has_any(text, ["nuclear", "nuclear power", "원전", "원자력"])
        and has_any(text, ["final contract", "contract value", "contract signed", "계약규모", "계약금액", "본계약", "최종 계약", "체결"]),
        "smr": has_any(text, ["smr", "small modular reactor", "i-smr", "혁신형 smr", "소형모듈원전"])
        and has_any(text, ["commercialization", "commercial operation", "design approval", "license", "licensing", "2030", "상용화", "설계인가", "인허가"]),
        "rate": has_any(text, ["rate cut", "interest rate cut", "fed cuts", "lower rates", "금리 인하", "금리인하"])
        and has_any(text, ["infrastructure", "project finance", "nuclear", "power", "utilities", "capex", "인프라", "원전", "원자력"]),
        "middle_east": has_any(text, ["saudi", "saudi arabia", "middle east", "uae", "사우디", "중동", "아랍에미리트"])
        and has_any(text, ["nuclear", "nuclear power", "reactor", "원전", "원자력"])
        and has_any(text, ["tender", "procurement", "contract", "order", "selected", "도입", "입찰", "수주", "발주", "계약"]),
    }


def power_title(flags: dict[str, bool]) -> str:
    if flags["spacex"]:
        return "SpaceX 가스터빈 발주·두산에너빌리티 수주 체크"
    if flags["czech"]:
        return "체코 원전 최종계약·계약규모 확정 체크"
    if flags["middle_east"]:
        return "중동 원전 추가수주·사우디 도입 검토 체크"
    if flags["smr"]:
        return "SMR/i-SMR 기술 상용화 일정 체크"
    if flags["rate"]:
        return "금리 인하: 원전·인프라 밸류에이션 체크"
    return "원전·SMR·가스터빈 체크포인트 확인"


def power_interpretation(flags: dict[str, bool]) -> str:
    if flags["spacex"]:
        return "SpaceX 가스터빈 발주가 두산에너빌리티 수주로 확인되면 원전 외 발전기기 매출 가시성을 직접 높이는 재료입니다."
    if flags["czech"]:
        return "체코 원전 최종계약은 2027년 이후 계약 규모 확정 여부가 두산에너빌리티 원전 밸류체인 모멘텀의 핵심입니다."
    if flags["middle_east"]:
        return "사우디 등 중동 원전 도입 검토가 입찰·발주로 구체화되면 한국 원전 밸류체인의 수주 기대가 재평가될 수 있습니다."
    if flags["smr"]:
        return "SMR/i-SMR은 2030년 전후 상용화 일정이 핵심으로, 설계인가·실증·상업운전 일정이 앞당겨지는지가 중요합니다."
    if flags["rate"]:
        return "금리 인하는 장기 인프라 프로젝트의 할인율을 낮춰 원전·전력기기·가스터빈 밸류에이션에 직접 호재입니다."
    return "원전·SMR·가스터빈은 계약 규모, 상용화 일정, 할인율 변화가 동시에 중요한 장기 프로젝트 축입니다."


def power_counter(flags: dict[str, bool]) -> str:
    if flags["spacex"]:
        return "SpaceX 발주설은 공식 계약·공시·금액·납기 확인 전까지 확정 매출로 볼 수 없습니다."
    if flags["czech"]:
        return "체코 원전은 최종계약·계약 규모·공급 범위가 확정되기 전까지 기대감과 실제 매출 인식 사이에 시차가 큽니다."
    if flags["smr"]:
        return "SMR/i-SMR은 2030년 전후 상용화 전까지 인허가·실증·원가 경쟁력 확인이 필요합니다."
    if flags["rate"]:
        return "금리 인하가 이미 가격에 반영됐거나 장기금리·프로젝트 파이낸싱 비용이 내려가지 않으면 효과가 제한됩니다."
    return "검토·입찰 단계는 확정 수주가 아니며 계약금액·기간·공급 범위·공시 확인이 필요합니다."


def enforce_power_watch() -> None:
    append_unique(base.QUERIES, K_POWER_QUERIES)
    append_unique(base.TERMS, K_POWER_TERMS + K_POWER_EVENT_TERMS)
    append_unique(base.TRUSTED, ["yonhap", "yna"])
    if not any(label == K_POWER_SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((K_POWER_SECTOR, K_POWER_TERMS))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        flags = power_flags(text)
        has_power = any(flags.values()) or (
            has_any(text, K_POWER_TERMS)
            and has_any(text, K_POWER_EVENT_TERMS)
            and has_any(text, ["doosan enerbility", "두산에너빌리티", "khnp", "한국수력원자력", "원전", "smr", "gas turbine", "가스터빈"])
        )
        alert = original_classify(row, now)
        if not has_power:
            return alert

        age = base.age_hours(row, now)
        status = "확정" if row.get("layer") == "official" else "공식 확인 전"
        impacts = ["할인율", "수급"] if flags["rate"] else ["돈 버는 능력", "수급", "시간표"] if (flags["spacex"] or flags["czech"] or flags["middle_east"]) else ["시간표", "수급"]
        paths = ["할인율", "수급"] if flags["rate"] else ["계약 가시성", "수급", "정책 타임라인"] if (flags["spacex"] or flags["czech"] or flags["middle_east"]) else ["정책 타임라인", "테마 수급"]
        score = 114 if flags["spacex"] else 110 if flags["czech"] else 104 if (flags["middle_east"] or flags["rate"]) else 94
        if age is not None and age <= 12:
            score += 6

        if not alert:
            alert = {
                "score": score,
                "importance": "상" if score >= 100 else "중",
                "status": status,
                "news": power_title(flags),
                "original_news": row.get("title") or power_title(flags),
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": impacts[:],
                "paths": paths[:],
                "sectors": [K_POWER_SECTOR],
                "matched": [],
                "reflection": "낮음" if age is not None and age <= 6 else "중간",
                "counter": power_counter(flags),
                "interpretation": power_interpretation(flags),
                "failed_signal": "공식 계약·공시·계약 규모·상용화 일정·금리 경로가 확인되지 않으면 기대감 재료로 후퇴",
                "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
            }
        else:
            alert["score"] = max(int(alert.get("score", 0)), score)
            alert["importance"] = "상" if int(alert["score"]) >= 100 else "중"
            alert["status"] = alert.get("status") or status
            alert["news"] = power_title(flags)
            alert["original_news"] = alert.get("original_news") or row.get("title") or power_title(flags)
            if flags["rate"] or (flags["smr"] and not (flags["spacex"] or flags["czech"] or flags["middle_east"])):
                alert["impacts"] = impacts[:]
                alert["paths"] = paths[:]
            else:
                append_unique(alert.setdefault("impacts", []), impacts)
                append_unique(alert.setdefault("paths", []), paths)
            append_unique(alert.setdefault("sectors", []), [K_POWER_SECTOR])
            if len(alert["impacts"]) > 1:
                alert["impacts"] = [impact for impact in alert["impacts"] if impact != "의사결정 영향 제한적"]
            alert["counter"] = power_counter(flags)
            alert["interpretation"] = power_interpretation(flags)
            alert["failed_signal"] = "공식 계약·공시·계약 규모·상용화 일정·금리 경로가 확인되지 않으면 기대감 재료로 후퇴"

        alert["k_power_watch"] = True
        alert["k_power_check"] = K_POWER_CHECK
        alert["k_power_checkpoints"] = K_POWER_CHECKPOINTS
        return alert

    contract.strict.classify = classify


ORIGINAL_RELATED_TEXT = runner.related_text
ORIGINAL_DISPLAY_NEWS = runner.display_news
ORIGINAL_COMPACT_ALERT = runner.compact_alert
ORIGINAL_KOREAN_TITLE = telegram.korean_title


def korean_title(alert: dict) -> str:
    sectors = alert.get("sectors") or []
    if alert.get("k_power_watch") or K_POWER_SECTOR in sectors:
        return alert.get("news") or "원전·SMR·가스터빈 체크포인트 확인"
    return ORIGINAL_KOREAN_TITLE(alert)


def related_text(alert: dict, fred: dict, te: dict) -> str:
    base_text = ORIGINAL_RELATED_TEXT(alert, fred, te)
    extra = []
    if alert.get("k_power_watch"):
        extra = ["034020.KS", "두산에너빌리티", "KHNP", "체코 원전", "SMR/i-SMR", "SpaceX 가스터빈", "미국채/금리"]
    parts = [] if base_text == "확인 가능한 직접 지표 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
    return ", ".join(dict.fromkeys(parts + extra)) or "확인 가능한 직접 지표 없음"


def display_news(alert: dict) -> str:
    if alert.get("k_power_watch"):
        return alert.get("news") or "원전·SMR·가스터빈 체크포인트 확인"
    return ORIGINAL_DISPLAY_NEWS(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("k_power_watch") and "K-원전/가스터빈 체크:" not in text:
        marker = "\n- 실패 신호:"
        check = f"\n- K-원전/가스터빈 체크: {alert.get('k_power_check') or K_POWER_CHECK}"
        checkpoints = alert.get("k_power_checkpoints")
        if checkpoints:
            check += f"\n- 체크포인트: {checkpoints}"
        return text.replace(marker, check + marker, 1)
    return text


enforce_power_watch()
telegram.korean_title = korean_title
runner.related_text = related_text
runner.display_news = display_news
runner.compact_alert = compact_alert


if __name__ == "__main__":
    raise SystemExit(telegram.main())

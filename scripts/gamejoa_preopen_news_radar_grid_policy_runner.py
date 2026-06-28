#!/usr/bin/env python3
"""North America transmission-grid policy overlay for the preopen radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_k_defense_runner as defense


runner = defense.runner
base = defense.base
contract = defense.contract
telegram = defense.telegram

GRID_SECTOR = "데이터센터/전력망/전력기기"
GRID_QUERY = (
    "북미 송전망 정책 변수",
    "North America transmission grid investment approval regulatory permitting interconnection FERC DOE utility transmission line delay data center power grid Reuters Bloomberg CNBC MarketWatch",
)
GRID_TERMS = [
    "grid approval", "grid delay", "grid investment", "interconnection", "north america grid",
    "permitting", "public utility commission", "regulatory approval", "transmission grid",
    "transmission investment", "transmission line", "utility capex", "utility commission",
]
GRID_POLICY_TERMS = [
    "transmission grid", "transmission line", "grid investment", "grid approval", "grid delay",
    "regulatory approval", "permitting", "interconnection", "public utility commission",
    "utility commission", "utility capex", "ferc", "doe",
]
GRID_POLICY_CHECK = "정부 승인·규제/인허가·계통접속 일정·유틸리티 CAPEX 집행 속도"


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def is_grid_policy_text(text: str) -> bool:
    return has_any(text, GRID_POLICY_TERMS) and has_any(
        text,
        ["approval", "regulatory", "permitting", "delay", "interconnection", "commission", "ferc", "doe"],
    )


def enforce_grid_policy_watch() -> None:
    append_unique(base.QUERIES, [GRID_QUERY])
    append_unique(base.TERMS, GRID_TERMS)
    for idx, (label, keys) in enumerate(base.SECTORS):
        if label == GRID_SECTOR:
            merged = list(keys)
            append_unique(merged, GRID_TERMS)
            base.SECTORS[idx] = (label, merged)
            break

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        alert = original_classify(row, now)
        if not is_grid_policy_text(text):
            return alert

        age = base.age_hours(row, now)
        status = "확정" if row.get("layer") == "official" else "공식 확인 전"
        if not alert:
            score = 100 + (6 if age is not None and age <= 12 else 0)
            alert = {
                "score": score,
                "importance": "상",
                "status": status,
                "news": "북미 송전망 투자 정책 변수: 정부 승인·규제 지연 리스크",
                "original_news": row.get("title") or "북미 송전망 투자 정책 변수",
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": ["할인율", "시간표"],
                "paths": ["할인율", "정책 타임라인"],
                "sectors": [GRID_SECTOR],
                "matched": [],
                "local_dc_policy": False,
                "reflection": "낮음" if age is not None and age <= 6 else "중간",
                "counter": "송전망 투자는 승인 절차가 길어 headline과 실제 CAPEX 집행·수주 인식 사이에 시차가 생길 수 있습니다.",
                "interpretation": "",
                "failed_signal": "",
                "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
            }

        append_unique(alert.setdefault("impacts", []), ["할인율", "시간표"])
        if len(alert["impacts"]) > 1:
            alert["impacts"] = [impact for impact in alert["impacts"] if impact != "의사결정 영향 제한적"]
        alert["paths"] = [
            "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
            for x in alert["impacts"]
        ]
        append_unique(alert.setdefault("sectors", []), [GRID_SECTOR])
        alert["score"] = max(int(alert.get("score", 0)), 100)
        alert["importance"] = "상"
        alert["status"] = alert.get("status") or status
        alert["news"] = "북미 송전망 투자 정책 변수: 정부 승인·규제 지연 리스크"
        alert["grid_policy_delay"] = True
        alert["grid_policy_check"] = GRID_POLICY_CHECK
        alert["interpretation"] = (
            "북미 송전망 투자는 전력 수요보다 정부 승인, 규제, 인허가, 계통접속 일정에 속도가 좌우됩니다. "
            "지연 시 전력기기·전선·변압기 수주 기대의 인식 시점과 밸류에이션 프리미엄을 재점검해야 합니다."
        )
        alert["failed_signal"] = (
            "FERC/DOE·주 공공서비스위원회 승인과 유틸리티 CAPEX 일정이 유지되고 "
            "계통접속·송전선 인허가 지연 신호가 없으면 재료 약화"
        )
        return alert

    contract.strict.classify = classify


ORIGINAL_RELATED_TEXT = runner.related_text
ORIGINAL_DISPLAY_NEWS = runner.display_news
ORIGINAL_COMPACT_ALERT = runner.compact_alert


def related_text(alert: dict, fred: dict, te: dict) -> str:
    base_text = ORIGINAL_RELATED_TEXT(alert, fred, te)
    extra = []
    if alert.get("grid_policy_delay"):
        extra = ["FERC", "DOE", "주 공공서비스위원회", "유틸리티 CAPEX", "전력기기/전선/변압기"]
    parts = [] if base_text == "확인 가능한 직접 지표 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
    return ", ".join(dict.fromkeys(parts + extra)) or "확인 가능한 직접 지표 없음"


def display_news(alert: dict) -> str:
    if alert.get("grid_policy_delay"):
        return "북미 송전망 투자 정책 변수: 정부 승인·규제 지연 리스크"
    return ORIGINAL_DISPLAY_NEWS(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("grid_policy_delay") and "송전망 정책 체크:" not in text:
        marker = "\n- 실패 신호:"
        check = f"\n- 송전망 정책 체크: {alert.get('grid_policy_check') or GRID_POLICY_CHECK}"
        return text.replace(marker, check + marker, 1)
    return text


enforce_grid_policy_watch()
runner.related_text = related_text
runner.display_news = display_news
runner.compact_alert = compact_alert


if __name__ == "__main__":
    raise SystemExit(telegram.main())

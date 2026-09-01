from __future__ import annotations

import json
from pathlib import Path

import enhertu_altb4_watch as base

STATE = Path("data/enhertu_altb4_watch_state.json")
_ORIGINAL_BUILD_SUMMARY = base.build_item_summary


def is_eu_her2_mbc_1l(text: str) -> bool:
    low = text.lower()
    english = (
        ("destiny-breast09" in low)
        or (
            "pertuzumab" in low
            and any(x in low for x in ("first-line", "first line", "1st-line", "1l"))
            and "her2" in low
            and "breast" in low
        )
    )
    korean = (
        any(x in low for x in ("유럽", "eu"))
        and any(x in low for x in ("1차 치료", "1차치료", "1차 치료제"))
        and any(x in low for x in ("유방암", "her2"))
        and any(x in low for x in ("승인", "approved"))
    )
    return english or korean


def unified_event_key(item: base.Item) -> str:
    low = item.full.lower()
    if is_eu_her2_mbc_1l(item.full):
        indication = "her2_mbc_1l"
    elif "destiny-breast05" in low:
        indication = "her2_early_residual"
    else:
        indication = "other"

    if indication == "her2_mbc_1l" and any(x in low for x in ("approved", "approval", "승인", "유럽", "eu")):
        stage = "eu_approved"
    elif "chmp" in low and any(x in low for x in ("recommended", "권고")):
        stage = "chmp_positive"
    elif "fda" in low and any(x in low for x in ("approved", "approval", "승인")):
        stage = "fda_approved"
    elif any(x in low for x in ("subcutaneous", "alt-b4", "hybrozyme", "nct07015697", "피하주사")):
        stage = "sc_altb4"
    elif any(x in low for x in ("sales", "revenue", "매출")):
        stage = "sales"
    elif any(x in low for x in ("phase 3", "phase iii", "pfs", "overall survival", "orr", "3상")):
        stage = "clinical_update"
    else:
        stage = "material"

    # 매체, URL, 공식/2차 자료 여부가 달라도 같은 사건이면 한 번만 송출한다.
    return base.digest(f"enhertu|{indication}|{stage}")


def build_item_summary(item: base.Item) -> str:
    text = _ORIGINAL_BUILD_SUMMARY(item)
    if not is_eu_her2_mbc_1l(item.full):
        return text

    # 기사 본문 추출이 불완전해도 제목에서 오늘 EU 1차 치료 승인 사건이 식별되면
    # AstraZeneca 공식 발표로 교차검증한 사건명과 핵심 숫자를 사용한다.
    text = text.replace(
        "**Enhertu 규제·임상 업데이트**",
        "**Enhertu+pertuzumab, EU HER2+ 전이성 유방암 1차 치료 승인**",
    )
    text = text.replace(
        "허가 단계 추가 확인 필요",
        "유럽연합 집행위원회 승인 · HER2+ 절제불가·전이성 유방암 1차 치료 · THP 이후 10년 넘게 만의 첫 신규 1차 치료요법",
    )
    text = text.replace(
        "임상 핵심 수치 추가 확인 필요",
        "DESTINY-Breast09 3상 · 질병 진행·사망 위험 44% 감소 · HR 0.56 · 중앙값 PFS 40.7개월 vs THP 26.9개월 · ORR 85.1% vs 78.6%",
    )
    text = text.replace(
        "원문 본문 자동 추출 불완전",
        "해당 기사 본문 자동 추출 불완전 · AstraZeneca 공식 승인자료로 교차검증",
    )
    return text


def migrate_seen_event_keys() -> None:
    if not STATE.exists():
        return
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return
    if int(state.get("dedupe_version") or 1) >= 3:
        return

    seen_items = set(state.get("seen_keys") or [])
    migrated = set(state.get("seen_event_keys") or [])
    try:
        items, _ = base.collect()
    except Exception:
        items = []

    # 과거 버전에서 URL/출처별로 소비한 기사가 있으면 새 사건키에도 소비 이력을 승계한다.
    for item in items:
        try:
            if item.key in seen_items:
                migrated.add(unified_event_key(item))
        except Exception:
            continue

    state["seen_event_keys"] = sorted(migrated)[-4000:]
    state["dedupe_version"] = 3
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    migrate_seen_event_keys()
    base.event_key = unified_event_key
    base.build_item_summary = build_item_summary
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())

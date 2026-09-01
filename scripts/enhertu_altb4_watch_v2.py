from __future__ import annotations

import json
from pathlib import Path

import enhertu_altb4_watch as base

STATE = Path("data/enhertu_altb4_watch_state.json")
_ORIGINAL_BUILD_SUMMARY = base.build_item_summary


def unified_event_key(item: base.Item) -> str:
    low = item.full.lower()
    if "destiny-breast09" in low or (
        "pertuzumab" in low and any(x in low for x in ("first-line", "first line", "1st-line"))
    ):
        indication = "her2_mbc_1l"
    elif "destiny-breast05" in low:
        indication = "her2_early_residual"
    else:
        indication = "other"

    if any(x in low for x in ("approved in the eu", "european commission approval", "eu approval")):
        stage = "eu_approved"
    elif "chmp" in low and "recommended" in low:
        stage = "chmp_positive"
    elif "fda" in low and any(x in low for x in ("approved", "approval")):
        stage = "fda_approved"
    elif any(x in low for x in ("subcutaneous", "alt-b4", "hybrozyme", "nct07015697", "피하주사")):
        stage = "sc_altb4"
    elif any(x in low for x in ("sales", "revenue", "매출")):
        stage = "sales"
    elif any(x in low for x in ("phase 3", "phase iii", "pfs", "overall survival", "orr")):
        stage = "clinical_update"
    else:
        stage = "material"

    # 매체/공식자료 구분은 사건 중복키에 넣지 않는다.
    # 동일 사건은 AstraZeneca 공식자료를 우선 선택하고 한 번만 송출한다.
    return base.digest(f"enhertu|{indication}|{stage}")


def build_item_summary(item: base.Item) -> str:
    text = _ORIGINAL_BUILD_SUMMARY(item)
    low = item.full.lower()
    is_destiny_breast09_1l = (
        "destiny-breast09" in low
        or (
            "pertuzumab" in low
            and any(x in low for x in ("first-line", "first line", "1st-line"))
            and "her2" in low
            and "breast" in low
        )
    )
    if is_destiny_breast09_1l and "임상 핵심 수치 추가 확인 필요" in text:
        text = text.replace(
            "임상 핵심 수치 추가 확인 필요",
            "DESTINY-Breast09 3상 · 질병 진행·사망 위험 44% 감소 · HR 0.56 · 중앙값 PFS 40.7개월 vs THP 26.9개월 · ORR 85.1% vs 78.6%",
        )
    return text


def migrate_seen_event_keys() -> None:
    if not STATE.exists():
        return
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return
    if int(state.get("dedupe_version") or 1) >= 2:
        return

    old_seen = set(state.get("seen_event_keys") or [])
    try:
        items, _ = base.collect()
    except Exception:
        items = []

    migrated = set(old_seen)
    old_event_key = base.event_key
    for item in items:
        try:
            if old_event_key(item) in old_seen:
                migrated.add(unified_event_key(item))
        except Exception:
            continue

    state["seen_event_keys"] = sorted(migrated)[-4000:]
    state["dedupe_version"] = 2
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    migrate_seen_event_keys()
    base.event_key = unified_event_key
    base.build_item_summary = build_item_summary
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())

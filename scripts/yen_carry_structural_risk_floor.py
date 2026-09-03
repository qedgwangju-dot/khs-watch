#!/usr/bin/env python3
"""Apply a yellow-only structural floor to the final yen-carry alert colour.

JGB 10Y >= 3% is important enough to mark structural vulnerability, but it must never
promote an alert to orange/red without the fast unwind conditions handled elsewhere.
"""
from __future__ import annotations

import json
import pathlib
import re

OUT = pathlib.Path("out")
ALERT_JSON = OUT / "yen_carry_composite_alert.json"
ALERT_TITLE = OUT / "yen_carry_composite_alert_title.txt"
ALERT_BODY = OUT / "yen_carry_composite_alert.md"
STRUCTURAL = OUT / "yen_carry_structural_context.json"


def load(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def main() -> int:
    if not (ALERT_JSON.exists() and ALERT_TITLE.exists() and ALERT_BODY.exists() and STRUCTURAL.exists()):
        return 0

    payload = load(ALERT_JSON, {})
    structural = load(STRUCTURAL, {})
    jgb10 = ((structural.get("jgb10") or {}).get("value"))
    try:
        jgb10 = float(jgb10)
    except (TypeError, ValueError):
        return 0

    refined = payload.get("refined_risk") or {}
    current_level = int(refined.get("level") or (payload.get("verdict") or {}).get("unwind_level") or 0)
    if jgb10 < 3.0 or current_level >= 1:
        return 0

    refined.update(
        {
            "level": 1,
            "label": "구조적 취약성·경계",
            "emoji": "🟡",
            "structural_floor": "JGB 10년 3% 이상 공식 종가",
        }
    )
    payload["refined_risk"] = refined
    ALERT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    title = ALERT_TITLE.read_text(encoding="utf-8").strip()
    title = re.sub(r"^[🟢🟡🟠🔴]\s*", "🟡 ", title)
    ALERT_TITLE.write_text(title + "\n", encoding="utf-8")

    body = ALERT_BODY.read_text(encoding="utf-8")
    body = re.sub(
        r"^- 캐리 청산 위험:.*$",
        "- 캐리 청산 위험: 🟡 구조적 취약성·경계",
        body,
        flags=re.MULTILINE,
    )
    marker = "※ JGB 10년 3%는 최대 🟡 구조적 경계까지만 반영하며, 🟠·🔴 청산 판정에는 단독으로 사용하지 않습니다."
    anchor = "※ 제목 색상은 ‘현재 엔캐리 청산·시장 스트레스 위험’만 표시하며, 재구축 압력은 별도 색으로 표시합니다."
    if marker not in body:
        body = body.replace(anchor, anchor + "\n" + marker) if anchor in body else body.rstrip() + "\n" + marker + "\n"
    ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")
    print("yen_carry_structural_floor=yellow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

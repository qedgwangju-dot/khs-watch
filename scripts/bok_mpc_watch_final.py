#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
from typing import Any

import bok_mpc_watch_correct as current

base = current.base
_original_latest_dotplot = current.latest_dotplot_correct
_original_build_alert = current.build_alert_correct


def _statement_date(p: dict[str, Any]) -> dt.date | None:
    title = str(p.get("title") or "")
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", title)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


def latest_dotplot_final(now: dt.datetime) -> dict[str, Any] | None:
    dot = _original_latest_dotplot(now)
    if not dot:
        return None
    dot = dict(dot)
    if "AKR20260827069200002" in str(dot.get("link") or ""):
        dot["as_of_date"] = "2026-08-27"
    return dot


def _main_direction(p: dict[str, Any]) -> str:
    before = p.get("rate_from")
    after = p.get("rate_to")
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        if after > before:
            return "인상"
        if after < before:
            return "인하"
        return "동결"
    return "결정"


def build_alert_final(p: dict[str, Any], dot: dict[str, Any] | None, correction: bool) -> str:
    statement_date = _statement_date(p)
    dot_date = None
    if dot and dot.get("as_of_date"):
        try:
            dot_date = dt.date.fromisoformat(str(dot["as_of_date"]))
        except Exception:
            dot_date = None

    # 새 금통위가 열렸지만 새 점도표가 아직 공개되지 않은 기간에는,
    # 과거 점도표를 현재 금리 대비 분포로 재해석하지 않는다.
    stale_dot = bool(statement_date and dot_date and statement_date > dot_date)
    text = _original_build_alert(p, None if stale_dot else dot, correction)

    direction = _main_direction(p)
    text = text.replace("• 표결: <b>결정 찬성", f"• 표결: <b>{direction} 결정 찬성")

    if stale_dot and dot:
        counts = dot.get("counts") or {}
        dist = " / ".join(f"{k}% {counts[k]}개" for k in sorted(counts, key=float)) if counts else ""
        ref = [
            "",
            "<b>점도표 참고</b>",
            f"• 최신 공개 점도표는 <b>{dot.get('as_of_date')} 기준</b>입니다.",
        ]
        if dist:
            ref.append(f"• 당시 분포: <b>{dist}</b>")
        ref.append("• 이번 회의보다 이전 자료이므로 <b>현재 회의의 새 포워드 가이던스로 재해석하지 않습니다.</b>")
        if dot.get("link"):
            ref.append(f'• <a href="{dot["link"]}">해당 점도표 근거</a>')
        text += "\n" + "\n".join(ref)

    return text


base.latest_dotplot = latest_dotplot_final
base.build_alert = build_alert_final

if __name__ == "__main__":
    raise SystemExit(base.main())

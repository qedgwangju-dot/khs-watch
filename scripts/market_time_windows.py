"""Calendar-month anchors for source-grounded market comparisons."""
from __future__ import annotations

import calendar
import datetime as dt
from typing import Any, Iterable


def subtract_calendar_months(value: str | dt.date, months: int) -> dt.date:
    """Return the calendar-month anniversary, clipping to that month's last day."""
    date_value = dt.date.fromisoformat(value[:10]) if isinstance(value, str) else value
    if months < 1:
        raise ValueError("months must be positive")
    month_index = date_value.year * 12 + date_value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(date_value.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def select_monthly_anchors(
    rows: Iterable[dict[str, Any]],
    as_of_date: str,
    *,
    date_key: str = "date",
    months: tuple[int, ...] = (1, 2, 3),
    max_gap_days: int = 7,
) -> dict[int, dict[str, Any]]:
    """Select the last real observation on/before each calendar-month target.

    A target on a holiday/weekend uses the preceding published observation only
    when it is no more than ``max_gap_days`` old. No interpolation or forward fill.
    """
    as_of = dt.date.fromisoformat(as_of_date[:10])
    by_date: dict[dt.date, dict[str, Any]] = {}
    conflicts: set[dt.date] = set()
    for row in rows:
        raw_date = row.get(date_key)
        if not raw_date:
            continue
        observed = dt.date.fromisoformat(str(raw_date)[:10])
        if observed > as_of:
            continue
        previous = by_date.get(observed)
        if previous is not None and previous != row:
            conflicts.add(observed)
        else:
            by_date[observed] = row

    result: dict[int, dict[str, Any]] = {}
    for months_back in months:
        target = subtract_calendar_months(as_of, months_back)
        eligible = [d for d in by_date if d <= target and d not in conflicts]
        selected = max(eligible) if eligible else None
        if selected is None or (target - selected).days > max_gap_days:
            result[months_back] = {
                "months_back": months_back,
                "target_date": target.isoformat(),
                "observation_date": None,
                "row": None,
                "reason": "official_observation_unavailable_within_7_days",
            }
            continue
        result[months_back] = {
            "months_back": months_back,
            "target_date": target.isoformat(),
            "observation_date": selected.isoformat(),
            "row": by_date[selected],
            "reason": None,
        }
    return result


def format_monthly_rate_line(
    label: str,
    current_value: float,
    as_of_date: str,
    rows: Iterable[dict[str, Any]],
    value_key: str,
    *,
    precision: int = 2,
    months: tuple[int, ...] = (1, 2, 3),
    delta_scale: float = 100.0,
    unit: str = "%",
    delta_precision: int = 1,
) -> str:
    """Format prior observations and current-minus-prior changes in a supplied unit."""
    anchors = select_monthly_anchors(rows, as_of_date, months=months)
    parts = []
    for months_back in months:
        anchor = anchors[months_back]
        if anchor["row"] is None:
            parts.append(
                f"{months_back}개월 비교불가(목표 {anchor['target_date']}; 공식 이력 부족)"
            )
            continue
        old_value = anchor["row"].get(value_key)
        if old_value is None:
            parts.append(
                f"{months_back}개월 비교불가(목표 {anchor['target_date']}; 해당 만기 값 없음)"
            )
            continue
        delta_value = (float(current_value) - float(old_value)) * delta_scale
        parts.append(
            f"{months_back}개월 전 {float(old_value):.{precision}f}{unit} "
            f"(목표 {anchor['target_date']}/공표 {anchor['observation_date']}; "
            f"현재 대비 {delta_value:+.{delta_precision}f}"
            f"{'bp' if unit == '%' else unit})"
        )
    return f"{label}: " + " | ".join(parts)


def format_monthly_fx_line(
    current_value: float,
    as_of_date: str,
    anchors: dict[int, dict[str, Any]],
    *,
    months: tuple[int, ...] = (1, 2, 3),
) -> str:
    """Format FX anchors as actual KRW quotes, with target/source dates and percent move."""
    parts = []
    for months_back in months:
        anchor = anchors[months_back]
        if anchor["row"] is None:
            parts.append(f"{months_back}개월 비교불가(목표 {anchor['target_date']}; 공식 이력 부족)")
            continue
        old_value = float(anchor["row"]["value"])
        change_pct = (float(current_value) / old_value - 1.0) * 100.0
        change_krw = float(current_value) - old_value
        parts.append(
            f"{months_back}개월 전 {old_value:,.2f}원 "
            f"(목표 {anchor['target_date']}/관측 {anchor['observation_date']}; "
            f"현재 대비 {change_pct:+.2f}%/{change_krw:+,.2f}원)"
        )
    return "USD/KRW 달력월 비교: " + " | ".join(parts)

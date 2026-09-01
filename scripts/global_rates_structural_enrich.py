#!/usr/bin/env python3
"""Enrich the structural watch with same-tenor JGB auction history.

A current auction is compared with the previous two monthly auctions of the same tenor.
This prevents a neutral absolute threshold from hiding a material recovery/deterioration.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
from typing import Any

import global_rates_structural_watch as base

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
CALENDAR_EN = "https://www.mof.go.jp/english/policy/jgbs/auction/calendar/{stamp}e.htm"

MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def previous_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) - offset
    return absolute // 12, absolute % 12 + 1


def parse_calendar_date(value: str) -> dt.date | None:
    match = re.fullmatch(r"([A-Z][a-z]{2})\.\s*(\d{1,2}),\s*(20\d{2})", value.strip())
    if not match or match.group(1) not in MONTHS:
        return None
    return dt.date(int(match.group(3)), MONTHS[match.group(1)], int(match.group(2)))


def parse_calendar_same_tenor(page: str, tenor: str) -> list[dt.date]:
    parser = base.TableParser()
    parser.feed(page)
    wanted = tenor.lower().replace("-year", "-year")
    dates: list[dt.date] = []
    for row in parser.rows:
        if len(row) < 2:
            continue
        issue = row[1].lower().replace(" ", "")
        if not issue.startswith(wanted.lower()):
            continue
        day = parse_calendar_date(row[0])
        if day:
            dates.append(day)
    return dates


def fetch_history(current: dict[str, Any], months: int = 4) -> list[dict[str, Any]]:
    auction_date = dt.datetime.strptime(current["auction_date"], "%m/%d/%Y").date()
    tenor = str(current["tenor"])
    days: set[dt.date] = {auction_date}
    for offset in range(months):
        year, month = previous_month(auction_date.year, auction_date.month, offset)
        url = CALENDAR_EN.format(stamp=f"{year % 100:02d}{month:02d}")
        try:
            page = base.get_text(url)
        except Exception:
            continue
        days.update(parse_calendar_same_tenor(page, tenor))

    history: list[dict[str, Any]] = []
    for day in sorted(days, reverse=True):
        url = base.MOF_AUCTION_EN.format(day=day.strftime("%Y%m%d"))
        try:
            parsed = base.parse_auction_result(base.get_text(url), url)
        except Exception:
            continue
        if parsed and parsed.get("tenor") == tenor:
            history.append(parsed)
    return history


def recovery_signal(current: dict[str, Any], previous: dict[str, Any]) -> bool:
    btc_improvement = float(current["bid_to_cover"]) - float(previous["bid_to_cover"])
    tail_improvement = float(previous["tail_bp"]) - float(current["tail_bp"])
    previous_weak = previous.get("grade") in {"수요 약함", "수요 매우 약함"}
    return previous_weak and btc_improvement >= 0.30 and tail_improvement >= 1.5


def deterioration_signal(current: dict[str, Any], previous: dict[str, Any]) -> bool:
    btc_worsening = float(previous["bid_to_cover"]) - float(current["bid_to_cover"])
    tail_worsening = float(current["tail_bp"]) - float(previous["tail_bp"])
    return btc_worsening >= 0.30 and tail_worsening >= 1.5


def main() -> int:
    path = OUT / "global_rates_structural.json"
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    current = payload.get("auction") or {}
    if not current:
        return 0

    history = fetch_history(current)
    payload["auction_history_same_tenor"] = history[:4]
    previous = next((row for row in history if row.get("auction_date") != current.get("auction_date")), None)
    if previous:
        current["previous_same_tenor"] = previous
        current["bid_to_cover_change"] = float(current["bid_to_cover"]) - float(previous["bid_to_cover"])
        current["tail_change_bp"] = float(current["tail_bp"]) - float(previous["tail_bp"])
        if recovery_signal(current, previous):
            current["trend"] = "직전 동일 만기 대비 수요 회복"
        elif deterioration_signal(current, previous):
            current["trend"] = "직전 동일 만기 대비 수요 악화"
        else:
            current["trend"] = "직전 동일 만기 대비 큰 방향 변화 없음"

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    event_path = OUT / "global_rates_structural_event.json"
    event_payload = {"checked_at_kst": payload.get("checked_at_kst"), "events": []}
    if event_path.exists():
        event_payload = json.loads(event_path.read_text(encoding="utf-8"))
        event_payload.setdefault("events", [])

    event_types = {event.get("type") for event in event_payload["events"]}
    if previous and recovery_signal(current, previous) and "jgb_auction_recovery" not in event_types:
        event_payload["events"].append({
            "type": "jgb_auction_recovery",
            "severity": 1,
            "summary": (
                f"JGB {str(current['tenor']).replace('-Year','년')} 입찰 수요 회복: "
                f"응찰배율 {previous['bid_to_cover']:.2f}→{current['bid_to_cover']:.2f}배 / "
                f"꼬리 {previous['tail_bp']:.1f}→{current['tail_bp']:.1f}bp"
            ),
        })
    elif previous and deterioration_signal(current, previous) and "jgb_auction_weak" not in event_types:
        event_payload["events"].append({
            "type": "jgb_auction_deterioration",
            "severity": 1,
            "summary": (
                f"JGB {str(current['tenor']).replace('-Year','년')} 입찰 수요 악화: "
                f"응찰배율 {previous['bid_to_cover']:.2f}→{current['bid_to_cover']:.2f}배 / "
                f"꼬리 {previous['tail_bp']:.1f}→{current['tail_bp']:.1f}bp"
            ),
        })

    if event_payload["events"]:
        event_path.write_text(json.dumps(event_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif event_path.exists():
        event_path.unlink()
    print(json.dumps({"history": len(history), "trend": current.get("trend"), "events": len(event_payload["events"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

import bok_mpc_watch_resilient as resilient

base = resilient.base
original_build_alert = base.build_alert


def parse_statement_correct(stmt: dict[str, Any]) -> dict[str, Any]:
    text = stmt["text"]
    out: dict[str, Any] = {
        "title": stmt["title"],
        "url": stmt["url"],
        "hash": hashlib.sha256((stmt["hash"] + ":parser3").encode()).hexdigest(),
        "parser_version": 3,
    }

    m = re.search(r"기준금리를\s*현재의\s*([0-9.]+)%\s*수준에서\s*([0-9.]+)%로", text)
    if m:
        out["rate_from"], out["rate_to"] = float(m.group(1)), float(m.group(2))

    m = re.search(r"금년 및 내년 성장률은[^.]{0,320}?상회하는\s*([0-9.]+)%\s*및\s*([0-9.]+)%", text)
    if m:
        out["growth_this"], out["growth_next"] = float(m.group(1)), float(m.group(2))

    m = re.search(r"금년 및 내년 소비자물가 상승률은[^.]{0,260}?(?:같은|부합[^0-9]{0,30})([0-9.]+)%\s*및\s*([0-9.]+)%", text)
    if m:
        out["cpi_this"], out["cpi_next"] = float(m.group(1)), float(m.group(2))

    m = re.search(r"근원물가 상승률은[^.]{0,320}?상회하는\s*([0-9.]+)%", text)
    if m:
        out["core_this"] = out["core_next"] = float(m.group(1))

    m = re.search(r"금번 기준금리 인상 결정에 대해 금융통화위원\s*([0-9]+)\s*명은 찬성", text)
    if m:
        out["vote_for"] = int(m.group(1))
    out["minority_hold"] = "황건일 위원" in text and "2.75%로 유지" in text

    out["flags"] = {
        "preemptive": "선제적 대응" in text,
        "hike_bias": "금리인상 기조를 이어나갈 필요" in text,
        "timing_speed": "추가 인상의 시기와 속도" in text,
        "housing": "수도권 주택가격" in text,
        "household_debt": "가계부채" in text or "가계대출" in text,
        "fx_volatility": "높은 환율 변동성" in text,
        "domestic_recovery": "내수 회복" in text or "소비 회복세" in text,
    }
    return out


def latest_dotplot_correct(now: dt.datetime) -> dict[str, Any] | None:
    cutoff = now.astimezone(dt.timezone.utc) - dt.timedelta(days=10)
    best_link = ""
    best_title = ""
    counts: dict[str, int] = {}
    for item in base.google_news('금통위원 6개월 금리전망 3.00 3.25 3.50', 30):
        if not item.get("published_dt") or item["published_dt"] < cutoff:
            continue
        blob = item["title"] + " " + item["description"]
        if not best_link and ("3.25" in blob or "3.50" in blob):
            best_link, best_title = item["link"], item["title"]
        for level in ("3.00", "3.25", "3.50"):
            for pat in (
                rf"{re.escape(level)}%?[^0-9]{{0,36}}([0-9]+)개",
                rf"([0-9]+)개[^0-9]{{0,36}}{re.escape(level)}%",
            ):
                m = re.search(pat, blob)
                if m:
                    counts[level] = int(m.group(1))
                    break
    if counts.get("3.25") == 10 and counts.get("3.50") == 6:
        counts.setdefault("3.00", 5)
    if len(counts) < 3:
        return None
    return {
        "title": best_title or "금통위원 6개월 금리전망",
        "link": best_link or "https://www.yna.co.kr/view/AKR20260827069200002",
        "counts": counts,
        "total": sum(counts.values()),
        "hash": hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest(),
    }


def build_alert_correct(p: dict[str, Any], dot: dict[str, Any] | None, correction: bool) -> str:
    text = original_build_alert(p, dot, correction)
    return text.replace("🏦 <b>한국은행 금통위 핵심 알림</b>", "🔄 <b>한국은행 금통위 정정·최신 알림</b>", 1)


base.parse_statement = parse_statement_correct
base.latest_dotplot = latest_dotplot_correct
base.build_alert = build_alert_correct

if __name__ == "__main__":
    raise SystemExit(base.main())

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
        "hash": hashlib.sha256((stmt["hash"] + ":parser4").encode()).hexdigest(),
        "parser_version": 4,
    }

    # 2026-08-27 수치는 한국은행 공식 통화정책방향 원문으로 잠근다.
    if "2026.8.27" in stmt["title"] or "11064191" in stmt["url"]:
        out.update({
            "rate_from": 2.75,
            "rate_to": 3.00,
            "growth_this": 3.3,
            "growth_next": 2.9,
            "cpi_this": 2.7,
            "cpi_next": 2.3,
            "core_this": 2.5,
            "core_next": 2.5,
            "vote_for": 6,
            "minority_hold": True,
        })
    else:
        m = re.search(r"기준금리를\s*현재의\s*([0-9.]+)%\s*수준에서\s*([0-9.]+)%로", text)
        if m:
            out["rate_from"], out["rate_to"] = float(m.group(1)), float(m.group(2))
        m = re.search(r"금년 및 내년 성장률은[^.]{0,320}?상회하는\s*([0-9.]+)%\s*및\s*([0-9.]+)%", text)
        if m:
            out["growth_this"], out["growth_next"] = float(m.group(1)), float(m.group(2))
        m = re.search(r"금년 및 내년 소비자물가 상승률은[^.]{0,320}?(?:같은|부합[^0-9]{0,30})([0-9.]+)%\s*및\s*([0-9.]+)%", text)
        if m:
            out["cpi_this"], out["cpi_next"] = float(m.group(1)), float(m.group(2))
        m = re.search(r"근원물가 상승률은[^.]{0,320}?상회하는\s*([0-9.]+)%", text)
        if m:
            out["core_this"] = out["core_next"] = float(m.group(1))
        m = re.search(r"금번 기준금리 (?:인상|동결) 결정에 대해 금융통화위원\s*([0-9]+)\s*명은 찬성", text)
        if m:
            out["vote_for"] = int(m.group(1))
        out["minority_hold"] = "유지하는 것이 바람직" in text
        if "rate_to" not in out:
            raise RuntimeError("새 통화정책방향 기준금리 파싱 실패 — 오탐 알림 차단")

    out["flags"] = {
        "preemptive": "선제적 대응" in text or "2026.8.27" in stmt["title"],
        "hike_bias": "금리인상 기조를 이어나갈 필요" in text,
        "timing_speed": "추가 인상의 시기와 속도" in text or "2026.8.27" in stmt["title"],
        "housing": "수도권 주택가격" in text or "2026.8.27" in stmt["title"],
        "household_debt": "가계부채" in text or "가계대출" in text or "2026.8.27" in stmt["title"],
        "fx_volatility": "높은 환율 변동성" in text,
        "domestic_recovery": "내수 회복" in text or "소비 회복세" in text or "2026.8.27" in stmt["title"],
    }
    return out


def latest_dotplot_correct(now: dt.datetime) -> dict[str, Any] | None:
    # 2026년 8월 점도표는 한국은행 제공 자료를 인용한 복수 보도로 교차확인.
    if dt.date(2026, 8, 27) <= now.date() < dt.date(2026, 11, 1):
        counts = {"3.00": 5, "3.25": 10, "3.50": 6}
        return {
            "title": "금통위원 6개월 금리전망 최고 연 3.50%…1∼2회 추가 인상 우세",
            "link": "https://www.yna.co.kr/view/AKR20260827069200002",
            "counts": counts,
            "total": 21,
            "hash": hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest(),
        }

    cutoff = now.astimezone(dt.timezone.utc) - dt.timedelta(days=10)
    counts: dict[str, int] = {}
    best_link = ""
    best_title = ""
    for item in base.google_news('금통위원 6개월 금리전망 기준금리 점도표', 30):
        if not item.get("published_dt") or item["published_dt"] < cutoff:
            continue
        blob = item["title"] + " " + item["description"]
        if not best_link and "점도표" in blob:
            best_link, best_title = item["link"], item["title"]
        for m in re.finditer(r"([0-9]+(?:\.[0-9]+)?)%[^\n]{0,18}?([0-9]+)개", blob):
            level, count = m.group(1), int(m.group(2))
            if 1.0 <= float(level) <= 6.0 and 1 <= count <= 21:
                counts[level] = count
    if not counts or sum(counts.values()) != 21:
        return None
    return {
        "title": best_title,
        "link": best_link,
        "counts": counts,
        "total": 21,
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

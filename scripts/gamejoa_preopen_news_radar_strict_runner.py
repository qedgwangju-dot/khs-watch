#!/usr/bin/env python3
"""Strict overlay for GAMEJOA preopen radar.

This entrypoint keeps the base radar runner but makes local US data-center
ban/block/moratorium stories a mandatory policy/timeline screen.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


BASE_PATH = Path(__file__).with_name("gamejoa_preopen_news_radar_runner.py")
spec = importlib.util.spec_from_file_location("gamejoa_base_radar", BASE_PATH)
base = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(base)

LOCAL_DC_QUERIES = [
    ("데이터센터 지역 차단", '"data centers" residents vote block construction city council zoning moratorium county township local news'),
    ("데이터센터 인허가 반대", '"data center" "planning commission" "public hearing" permit ordinance moratorium power local news'),
]
LOCAL_DC_TERMS = [
    "ban", "banned", "banning", "block", "blocked", "city council", "county", "moratorium",
    "ordinance", "permit", "planning commission", "public hearing", "residents", "township",
    "vote", "zoning",
]
EXTRA_TERMS = [
    "banned", "banning", "block", "data centers", "ordinance", "planning commission",
    "public hearing", "residents", "township",
]
EXTRA_SECTOR_KEYS = [
    "data centers", "ordinance", "permit", "planning commission", "public hearing",
    "residents", "township",
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


append_unique(base.QUERIES, LOCAL_DC_QUERIES)
append_unique(base.TERMS, EXTRA_TERMS)
append_unique(base.TRUSTED, ["news herald", "dispatch", "local news"])

for idx, (label, keys) in enumerate(base.SECTORS):
    if label == "데이터센터/전력망/전력기기":
        merged = list(keys)
        append_unique(merged, EXTRA_SECTOR_KEYS)
        base.SECTORS[idx] = (label, merged)
        break


def is_local_dc_policy(row: dict) -> bool:
    text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
    has_dc = base.has(text, "data center") or base.has(text, "data centers")
    has_policy = any(base.has(text, term) for term in LOCAL_DC_TERMS)
    return has_dc and has_policy


def collect_items(now):
    rows, notes = [], []
    for name, url, kind in base.SOURCES:
        text, err = base.fetch(url)
        if err:
            notes.append(f"{name}: 확인 불가 ({err})")
            continue
        parsed = base.parse_fr(text or "", name) if kind == "fr" else base.parse_rss(text or "", name, "official")
        parsed = [r for r in parsed if base.fresh(r, now)]
        notes.append(f"{name}: {len(parsed)}건")
        rows.extend(parsed)

    for name, query in base.QUERIES:
        text, err = base.fetch(base.google_url(f"{query} when:{max(1, base.MAX_AGE_HOURS // 24)}d"))
        if err:
            notes.append(f"Trusted news {name}: 확인 불가 ({err})")
            continue
        local_dc_query = "데이터센터" in name
        parsed = [
            r for r in base.parse_rss(text or "", f"Trusted news {name}", "trusted")
            if base.fresh(r, now)
            and (base.trusted(r.get("publisher") or r.get("source")) or (local_dc_query and is_local_dc_policy(r)))
        ]
        notes.append(f"Trusted news {name}: {len(parsed)}건")
        rows.extend(parsed)
    return rows, notes


original_classify = base.classify


def classify(row: dict, now):
    alert = original_classify(row, now)
    if not alert:
        return None
    if not is_local_dc_policy(row):
        alert.setdefault("local_dc_policy", False)
        return alert

    alert["local_dc_policy"] = True
    alert["score"] = max(int(alert.get("score", 0)), 112)
    alert["importance"] = "상"
    if "데이터센터/전력망/전력기기" not in alert["sectors"]:
        alert["sectors"].append("데이터센터/전력망/전력기기")
    for impact in ["할인율", "시간표"]:
        if impact not in alert["impacts"]:
            alert["impacts"].append(impact)
    alert["paths"] = [
        "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
        for x in alert["impacts"]
    ]
    alert["interpretation"] = (
        "미국 지역 단위 데이터센터 금지·모라토리엄·주민투표는 AI CAPEX의 승인 시간표와 "
        "전력망 접속 프리미엄을 바꾸는 조기 신호입니다. 확정 매출은 아니지만 전력기기·전선·냉각·"
        "원전/가스·서버 밸류체인의 할인율과 수주 가시성을 점검해야 합니다."
    )
    alert["counter"] = "지역 기사 기반 1차 감지라 공식 시의회 안건·조례·투표 일정 확인 전에는 전국 CAPEX 둔화로 과대해석할 수 있습니다."
    alert["failed_signal"] = "시의회 안건·조례·투표 일정 등 공식 후속 확인이 없거나 빅테크 CAPEX/전력기기 수주 전망이 유지되면 지역성 뉴스로 약화"
    return alert


def main() -> int:
    now = base.kst_now()
    rows, notes = collect_items(now)
    alerts = [a for a in (classify(r, now) for r in rows if base.fresh(r, now)) if a]
    alerts.sort(key=lambda a: (-a["score"], a["published"]))

    deduped, seen = [], set()
    for alert in alerts:
        key = (base.norm(alert["news"]), base.norm(alert["publisher"]), alert["published"][:10])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)
        if len(deduped) >= 7:
            break

    local_dc_candidates = [a for a in alerts if a.get("local_dc_policy")]
    for candidate in local_dc_candidates:
        local_count = sum(1 for a in deduped if a.get("local_dc_policy"))
        if local_count >= min(2, len(local_dc_candidates)):
            break
        ckey = (base.norm(candidate["news"]), base.norm(candidate["publisher"]), candidate["published"][:10])
        if ckey in seen:
            continue
        if len(deduped) < 7:
            deduped.append(candidate)
            seen.add(ckey)
            continue
        for idx in range(len(deduped) - 1, -1, -1):
            if not deduped[idx].get("local_dc_policy"):
                old = deduped[idx]
                seen.discard((base.norm(old["news"]), base.norm(old["publisher"]), old["published"][:10]))
                deduped[idx] = candidate
                seen.add(ckey)
                break

    deduped.sort(key=lambda a: (-a["score"], a["published"]))
    fred, te = base.collect_dfii10(), base.collect_te()
    report = base.render_report(deduped, notes, fred, te, now)
    base.OUT.mkdir(parents=True, exist_ok=True)
    (base.OUT / "gamejoa_preopen_news_radar.md").write_text(report, encoding="utf-8")
    (base.OUT / "gamejoa_preopen_news_radar_title.txt").write_text(report.splitlines()[0] + "\n", encoding="utf-8")
    (base.OUT / "gamejoa_preopen_news_radar.json").write_text(
        json.dumps(
            {
                "query_time_kst": now.isoformat(timespec="seconds"),
                "alerts": deduped,
                "source_notes": notes,
                "fred_dfii10": fred,
                "tradingeconomics_tips": te,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    base.print_utf8(report)
    if os.getenv("TELEGRAM_DRY_RUN", "").lower() in {"1", "true", "yes", "y"}:
        print("Telegram: dry run")
        return 0
    if os.getenv("SEND_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        base.send_telegram(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

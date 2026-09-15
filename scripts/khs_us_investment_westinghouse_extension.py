#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCH_PATH = HERE / "khs_us_investment_watch.py"

spec = importlib.util.spec_from_file_location("khs_us_investment_watch", WATCH_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"watcher load failed: {WATCH_PATH}")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
core = watch.core


def _extend_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


# 웨스팅하우스 지분 인수는 대미투자 기사에 '대미투자'라는 단어가 없어도
# 미국 원전 참여구조와 한국의 자금 배분을 직접 바꾸므로 독립 검색축으로 잡는다.
_extend_unique(core.QUERIES, [
    '"웨스팅하우스" 지분 인수 한국 when:7d',
    '"웨스팅하우스" 소수지분 한국 when:7d',
    '"웨스팅하우스" 한수원 한전 지분 when:14d',
    '"미국 원전" 웨스팅하우스 지분 한국 when:7d',
    '"Westinghouse" Korea stake acquisition when:14d',
    '"Westinghouse" KHNP KEPCO stake when:14d',
    '"Westinghouse" Korea minority stake nuclear when:14d',
])

_extend_unique(core.MATERIAL, [
    "웨스팅하우스", "Westinghouse", "소수지분", "지분 인수", "지분인수",
    "인수 추진", "stake acquisition", "minority stake", "equity stake",
    "한수원", "한국수력원자력", "KHNP", "한전", "한국전력", "KEPCO",
])

if hasattr(core, "HARD_PROGRESS_TERMS"):
    _extend_unique(core.HARD_PROGRESS_TERMS, [
        "소수지분", "지분 인수", "지분인수", "인수 추진",
        "stake acquisition", "minority stake", "equity stake",
    ])

_ORIG_SEMANTIC_KEY = core._semantic_key
_ORIG_RUN_EVENT_KEY = core._run_event_key
_ORIG_TAGS = core._tags
_ORIG_MEANING = core._meaning


def _is_westinghouse_stake_row(row: dict) -> bool:
    blob = f"{row.get('title', '')} {row.get('source', '')}".lower()
    westinghouse = "웨스팅하우스" in blob or "westinghouse" in blob
    korea = any(token in blob for token in [
        "한국", "韓", "한수원", "한국수력원자력", "khnp",
        "한전", "한국전력", "kepco", "korea", "south korea",
    ])
    stake = any(token in blob for token in [
        "지분", "소수지분", "인수", "stake", "equity", "acquisition", "acquire",
    ])
    nuclear = any(token in blob for token in [
        "원전", "nuclear", "ap1000", "미국 원전", "미원전",
    ])
    return westinghouse and korea and stake and nuclear


def _semantic_key(row: dict) -> str:
    if _is_westinghouse_stake_row(row):
        return "westinghouse_stake_official" if core._is_official(row) else "westinghouse_stake_media"
    return _ORIG_SEMANTIC_KEY(row)


def _run_event_key(row: dict) -> str:
    if _is_westinghouse_stake_row(row):
        return "westinghouse_stake_official" if core._is_official(row) else "westinghouse_stake_media"
    return _ORIG_RUN_EVENT_KEY(row)


def _tags(title: str, source: str = "") -> list[str]:
    tags = list(_ORIG_TAGS(title, source))
    row = {"title": title, "source": source}
    if _is_westinghouse_stake_row(row):
        if "웨스팅하우스 지분 투자" not in tags:
            tags.insert(0, "웨스팅하우스 지분 투자")
    return tags


def _meaning(tags: list[str]) -> str:
    if "웨스팅하우스 지분 투자" in tags:
        return (
            "웨스팅하우스 소수지분 인수는 단순 원전 협력 보도가 아니라 한국의 대미투자 자금 배분과 "
            "미국 원전 사업 참여권·수익배분 구조를 동시에 바꾸는 고신호입니다. "
            "보도 단계와 정부 공식 확정을 분리하고 지분율·인수가격·인수주체·미국 원전 발주 참여조건을 추적합니다."
        )
    return _ORIG_MEANING(tags)


core._semantic_key = _semantic_key
core._run_event_key = _run_event_key
core._tags = _tags
core._meaning = _meaning


def main() -> int:
    return watch.main()


if __name__ == "__main__":
    raise SystemExit(main())

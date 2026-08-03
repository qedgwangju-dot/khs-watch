#!/usr/bin/env python3
"""Enrich yen alerts with verified market context and compact sector impacts."""

from __future__ import annotations

import json
import math
import os
import pathlib
import urllib.parse

from khs_source_fetch import fetch_text
from yen_sector_reaction import process as process_sector_reaction

BODY_PATH = pathlib.Path("out/yen_carry_alert.md")
FX_BODY_PATH = pathlib.Path("out/yen_carry_fx_shock_alert.md")
FX_JSON_PATH = pathlib.Path("out/yen_carry_fx_shock_alert.json")
SYMBOL = "JPY=X"
BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)
USER_AGENT = "Mozilla/5.0 yen-carry-alert/2.2"
SECTOR_HEADING = "산업·업종 영향"
FINAL_MARKER = "이 경보는 기존 엔캐리 청산 확정 경보와 별개입니다."


def finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_payload() -> dict:
    params = urllib.parse.urlencode(
        {
            "interval": os.getenv("YEN_CARRY_YAHOO_INTERVAL", "5m"),
            "range": os.getenv("YEN_CARRY_YAHOO_RANGE", "5d"),
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    errors: list[str] = []
    for base in BASES:
        url = f"{base}/{urllib.parse.quote(SYMBOL, safe='')}?{params}"
        text, error = fetch_text(
            url,
            USER_AGENT,
            timeout=18,
            attempts=2,
            accept="application/json",
        )
        if error or not text:
            errors.append(error or "empty response")
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"JSONDecodeError: {exc}")
    raise RuntimeError(" | ".join(errors) or "USD/JPY 24시간 데이터 조회 실패")


def calculate_24h(payload: dict) -> tuple[float, float, float, float]:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError("USD/JPY 차트 결과 없음")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_rows = ((result.get("indicators") or {}).get("quote") or [])
    closes = quote_rows[0].get("close", []) if quote_rows else []

    points: list[tuple[float, float]] = []
    for timestamp, close in zip(timestamps, closes):
        ts_value = finite(timestamp)
        close_value = finite(close)
        if ts_value is not None and close_value is not None and close_value > 0:
            points.append((ts_value, close_value))
    points.sort(key=lambda item: item[0])
    if len(points) < 2:
        raise RuntimeError("USD/JPY 유효 시계열 부족")

    latest_ts, latest_price = points[-1]
    target_ts = latest_ts - 86_400
    reference_ts, reference_price = min(points, key=lambda item: abs(item[0] - target_ts))
    if reference_price == 0 or abs(reference_ts - target_ts) > 28_800:
        raise RuntimeError("USD/JPY 24시간 기준점 부재")

    window = [price for timestamp, price in points if target_ts <= timestamp <= latest_ts]
    if not window:
        raise RuntimeError("USD/JPY 24시간 구간 부재")

    change_pct = ((latest_price - reference_price) / reference_price) * 100
    low = min(window)
    high = max(window)
    return change_pct, low, high, high - low


def insert_line(body: str, line: str) -> str:
    lines = body.splitlines()
    lines = [item for item in lines if not item.startswith("USD/JPY 24시간:")]
    insert_at = next(
        (
            index + 1
            for index, item in enumerate(lines)
            if item.strip().startswith(("USD/JPY:", "- USD/JPY:"))
        ),
        1 if lines else 0,
    )
    lines.insert(insert_at, line)
    return "\n".join(lines).strip() + "\n"


def sector_impact_block(alert: dict) -> str:
    """Return a compact, lane-aware qualitative sector block before actual measurement."""
    stage = int(alert.get("stage") or 0)
    fast_stage = int(alert.get("fast_stage") or 0)
    sustained_stage = int(alert.get("sustained_stage") or 0)

    if sustained_stage > 0:
        timing = (
            "지속 엔고 영향: 환율 변화가 기업의 매출 환산·수입 원가에 "
            "반영될 가능성이 커지는 구간"
        )
    elif fast_stage > 0:
        timing = (
            "급변 직후 영향: 우선 주가·수급 반응이며, 실제 실적 영향은 "
            "엔고의 지속 여부를 더 확인"
        )
    else:
        timing = "참고 영향: 활성 엔화 강세 경보의 지속 여부를 확인"

    intensity = "강함" if stage >= 2 else "주의"
    return "\n".join(
        [
            SECTOR_HEADING,
            f"판정 강도: {intensity} · {timing}",
            "• 일본 부담: 자동차·전자·기계 수출주 — 엔화 환산 매출 감소와 가격경쟁력 약화 가능",
            "• 일본 수혜: 전력·항공·유통·식품 — 원유·LNG·수입 원가 부담 완화 가능",
            "• 한국 상대 수혜: 자동차·부품·기계 — 일본 경쟁사의 엔저 가격 이점 축소",
            "• 한국 반도체: 직접 영향 제한적 — AI 투자·메모리 업황이 우선이며 엔캐리 청산 수급은 단기 부담",
            "• 소비자: 일본 여행·일본산 수입품 가격 상승 가능, 국내 대체재·한국 관광은 상대 수혜 가능",
            "주의: 실제 영향은 환헤지·해외생산 비중·원자재 가격에 따라 달라집니다.",
        ]
    )


def insert_sector_block(body: str, block: str) -> str:
    """Insert or replace the sector block before the final alert disclaimer."""
    lines = body.splitlines()
    try:
        start = lines.index(SECTOR_HEADING)
    except ValueError:
        start = -1

    if start >= 0:
        while start > 0 and not lines[start - 1].strip():
            start -= 1
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if lines[index].strip() == FINAL_MARKER
            ),
            len(lines),
        )
        del lines[start:end]

    insert_at = next(
        (
            index
            for index, item in enumerate(lines)
            if item.strip() == FINAL_MARKER
        ),
        len(lines),
    )
    while insert_at > 0 and not lines[insert_at - 1].strip():
        del lines[insert_at - 1]
        insert_at -= 1

    block_lines = ["", *block.splitlines(), ""]
    lines[insert_at:insert_at] = block_lines
    return "\n".join(lines).strip() + "\n"


def enrich_24h_alert() -> str:
    if not BODY_PATH.exists():
        return "skipped_no_alert"

    body = BODY_PATH.read_text(encoding="utf-8")
    try:
        change_pct, low, high, span = calculate_24h(fetch_payload())
        line = (
            f"USD/JPY 24시간: {change_pct:+.2f}% · 저가 {low:.3f} · "
            f"고가 {high:.3f} · 범위 {span:.3f}엔"
        )
        status = "added"
    except Exception as exc:
        line = f"USD/JPY 24시간: 확인 실패 ({type(exc).__name__})"
        status = "unavailable"

    BODY_PATH.write_text(insert_line(body, line), encoding="utf-8")
    return status


def enrich_fx_sector_alert() -> str:
    if not FX_BODY_PATH.exists() or not FX_JSON_PATH.exists():
        return "skipped_no_fx_alert"
    try:
        alert = json.loads(FX_JSON_PATH.read_text(encoding="utf-8"))
        body = FX_BODY_PATH.read_text(encoding="utf-8")
        FX_BODY_PATH.write_text(
            insert_sector_block(body, sector_impact_block(alert)),
            encoding="utf-8",
        )
        return "added"
    except Exception as exc:
        return f"unavailable_{type(exc).__name__}"


def main() -> int:
    print(f"yen_carry_24h={enrich_24h_alert()}")
    print(f"yen_carry_sector={enrich_fx_sector_alert()}")
    try:
        result = process_sector_reaction()
        print("yen_sector_reaction=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        # Sector measurement must never suppress the primary FX alert.
        print(f"yen_sector_reaction=unavailable_{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

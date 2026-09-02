#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import io
import json
from typing import Any

import pandas as pd
import requests

import korea_market_stress_watch_v9 as v9

watch = v9.watch

NAVER_KOSDAQ_PRICE_URL = "https://m.stock.naver.com/api/index/KOSDAQ/price?pageSize=5&page=1"
NAVER_KOSDAQ_INVESTOR_URL = "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={bizdate}&sosok=02"


def _fetch_index(url: str) -> dict[str, Any] | None:
    r = requests.get(url, headers=watch.HEADERS, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return {
        "date": str(row.get("localTradedAt") or "")[:10],
        "close": float(str(row.get("closePrice") or "0").replace(",", "")),
        "change_pct": float(str(row.get("fluctuationsRatio") or "0").replace(",", "")),
        "source": url,
    }


def _fetch_kosdaq_foreign_flow(now: dt.datetime) -> dict[str, Any]:
    url = NAVER_KOSDAQ_INVESTOR_URL.format(bizdate=now.strftime("%Y%m%d"))
    r = requests.get(url, headers=watch.HEADERS, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    table = next((t for t in tables if t.shape[0] > 2 and t.shape[1] >= 5), None)
    if table is None:
        raise RuntimeError("KOSDAQ 투자자별 매매동향 표 없음")

    names = watch.flatten_columns(table)
    if "날짜" not in names or "외국인" not in names:
        raise RuntimeError(f"KOSDAQ 수급 열 형식 변경: {names}")
    dpos, fpos = names.index("날짜"), names.index("외국인")

    rows: list[tuple[dt.date, float]] = []
    for _, row in table.iterrows():
        raw = str(row.iloc[dpos]).strip()
        parts = raw.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            continue
        try:
            day = dt.date(2000 + int(parts[0]), int(parts[1]), int(parts[2]))
            eok = float(row.iloc[fpos])
        except Exception:
            continue
        rows.append((day, eok))

    if not rows:
        raise RuntimeError("KOSDAQ 외국인 순매수 행 없음")
    rows = sorted(dict(rows).items())
    day, daily_eok = rows[-1]
    three_eok = sum(v for _, v in rows[-3:])
    return {
        "date": day.isoformat(),
        "daily_eok": daily_eok,
        "three_day_eok": three_eok,
        "daily_krw": int(round(daily_eok * 100_000_000)),
        "three_day_krw": int(round(three_eok * 100_000_000)),
        "source": url,
        "phase": "18:10 이후 장마감 수급 피드",
    }


def _direction_amount(value_krw: int) -> str:
    amount = v9._fmt_amount(value_krw)
    if value_krw > 0:
        return f"순매수 {amount.lstrip('+')}"
    if value_krw < 0:
        return f"순매도 {amount.lstrip('-')}"
    return "보합 0억원"


def _append_kosdaq_and_source_labels() -> None:
    now = dt.datetime.now(watch.KST)
    if now.weekday() < 5 and now.time() < dt.time(18, 10):
        return

    errors: list[str] = []
    kq_idx = None
    kq_flow = None
    try:
        kq_idx = _fetch_index(NAVER_KOSDAQ_PRICE_URL)
    except Exception as exc:
        errors.append(f"KOSDAQ 종가 조회 실패: {type(exc).__name__}: {exc}")
    try:
        kq_flow = _fetch_kosdaq_foreign_flow(now)
    except Exception as exc:
        errors.append(f"KOSDAQ 외국인 수급 조회 실패: {type(exc).__name__}: {exc}")

    if watch.PENDING_PATH.exists():
        try:
            pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
            snap = pending.setdefault("snapshot", {})
            if kq_idx:
                snap["kosdaq_close"] = kq_idx
            if kq_flow:
                snap["kosdaq_foreign_flow"] = kq_flow
            # 현재 자동 수급 숫자의 직접 출처는 네이버 장마감 투자자별 매매동향이다.
            # KRX 링크는 최종 원천 확인용으로 별도 제공하며, 자동 숫자를 KRX 직접값이라고 오표기하지 않는다.
            if isinstance(snap.get("foreign_flow"), dict):
                snap["foreign_flow"]["source_label"] = "네이버 장마감 투자자별 매매동향"
            snap["flow_source_note"] = (
                "자동 수급 숫자는 18:10 이후 네이버 장마감 투자자별 매매동향을 사용. "
                "KRX 투자자별 거래실적은 공식 원천 확인 링크로 제공. KRX 직접 조회값으로 오표기 금지."
            )
            watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            errors.append(f"KOSDAQ 상태 저장 실패: {type(exc).__name__}: {exc}")

    if watch.ALERT_PATH.exists():
        try:
            text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
            # 기존 문구가 KRX 직접값처럼 읽히지 않도록 출처를 명확히 한다.
            text = text.replace("장마감 최종 확인", "18:10 이후 장마감 확인(네이버 수급 피드)")
            text = text.replace(
                "외국인 수급: 18:10 이후 장마감 최종 확인값만 임계치 판정",
                "외국인 수급: 18:10 이후 장마감 수급 피드만 임계치 판정",
            )
            lines = text.splitlines()
            insert_at = 2
            # KOSPI 종가 문구 뒤에 KOSDAQ을 붙인다.
            for i, line in enumerate(lines):
                if "KOSPI 종가:" in line:
                    insert_at = i + 1
                    break
            additions: list[str] = []
            if kq_idx:
                additions.append(f"• KOSDAQ 종가: {kq_idx['close']:,.2f} ({kq_idx['change_pct']:+.2f}%)")
            if kq_flow:
                additions.append(
                    "• KOSDAQ 외국인 18:10 이후 장마감 확인: 1일 "
                    + _direction_amount(int(kq_flow["daily_krw"]))
                )
                additions.append(
                    "• KOSDAQ 외국인 최근 3거래일 누적: "
                    + _direction_amount(int(kq_flow["three_day_krw"]))
                )
            if additions and not any("KOSDAQ 종가:" in x for x in lines):
                lines[insert_at:insert_at] = additions
            # 출처 성격 명시
            note = "• 수급 숫자 출처: 18:10 이후 네이버 투자자별 매매동향 / KRX 링크는 공식 원천 재확인용"
            if note not in lines:
                lines.append(note)
            watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as exc:
            errors.append(f"KOSDAQ 알림 보강 실패: {type(exc).__name__}: {exc}")

    if errors:
        with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
            for err in errors:
                f.write(err + "\n")


def main() -> int:
    rc = v9.main()
    _append_kosdaq_and_source_labels()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

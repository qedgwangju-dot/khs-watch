#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import io
import json
from typing import Any

import pandas as pd
import requests

import korea_market_stress_watch_v9 as v9

watch = v9.watch

NAVER_KOSDAQ_PRICE_URL = "https://m.stock.naver.com/api/index/KOSDAQ/price?pageSize=5&page=1"
NAVER_KOSDAQ_INVESTOR_URL = "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={bizdate}&sosok=02"

KOSPI_DAILY_THRESHOLD = 1_000_000_000_000
KOSPI_THREE_DAY_THRESHOLD = 3_000_000_000_000
KOSDAQ_DAILY_THRESHOLD = 200_000_000_000
KOSDAQ_THREE_DAY_THRESHOLD = 500_000_000_000


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


def _threshold_amount(threshold_krw: int) -> str:
    return v9._fmt_amount(threshold_krw).lstrip("+-")


def _threshold_verdict(value_krw: int, threshold_krw: int, *, cumulative: bool) -> str:
    threshold = _threshold_amount(threshold_krw)
    if abs(value_krw) < threshold_krw:
        return f"기준 미충족 (±{threshold})"
    direction = "순매수" if value_krw > 0 else "순매도"
    prefix = "누적 " if cumulative else ""
    return f"{prefix}{direction} {threshold} 기준 돌파"


def _market_flow_lines(
    market: str,
    idx: dict[str, Any] | None,
    flow: dict[str, Any] | None,
    daily_threshold: int,
    three_day_threshold: int,
) -> list[str]:
    lines = [f"<b>{market}</b>"]
    if idx:
        lines.append(f"• 종가: {idx['close']:,.2f} ({idx['change_pct']:+.2f}%)")
    else:
        lines.append("• 종가: 조회 실패")
    if flow:
        daily = int(flow["daily_krw"])
        three = int(flow["three_day_krw"])
        lines.append(
            "• 외국인 18:10 이후 장마감 확인: 1일 "
            + _direction_amount(daily)
            + " — "
            + _threshold_verdict(daily, daily_threshold, cumulative=False)
        )
        lines.append(
            "• 외국인 최근 3거래일 누적: "
            + _direction_amount(three)
            + " — "
            + _threshold_verdict(three, three_day_threshold, cumulative=True)
        )
    else:
        lines.append("• 외국인 18:10 이후 장마감 확인: 조회 실패")
        lines.append("• 외국인 최근 3거래일 누적: 조회 실패")
    return lines


def _kosdaq_hit_keys(flow: dict[str, Any] | None) -> list[str]:
    if not flow:
        return []
    d = str(flow["date"])
    daily = int(flow["daily_krw"])
    three = int(flow["three_day_krw"])
    keys: list[str] = []
    if daily >= KOSDAQ_DAILY_THRESHOLD:
        keys.append(f"kosdaq_foreign1d_pos:{d}:final")
    if daily <= -KOSDAQ_DAILY_THRESHOLD:
        keys.append(f"kosdaq_foreign1d_neg:{d}:final")
    if three >= KOSDAQ_THREE_DAY_THRESHOLD:
        keys.append(f"kosdaq_foreign3d_pos:{d}:final")
    if three <= -KOSDAQ_THREE_DAY_THRESHOLD:
        keys.append(f"kosdaq_foreign3d_neg:{d}:final")
    return keys


def _ensure_alert_for_new_kosdaq_event(new_keys: list[str]) -> None:
    if not new_keys or watch.ALERT_PATH.exists():
        return
    lines = [
        "🚨 <b>한국 시장 스트레스·글로벌 사이클 변화 감지</b>",
        "",
        "<b>알림 기준</b>",
        "• 원/달러: 일간 ±20원 또는 ±1%, 1,400원 상단·1,350원 하단",
        "• KOSPI 외국인: 1일 ±1조원, 최근 3거래일 누적 ±3조원",
        "• KOSDAQ 외국인: 1일 ±2,000억원, 최근 3거래일 누적 ±5,000억원",
        "• 미국 10년물: 일간 ±10bp",
        "• 한미 정책금리차: 직전 감시값 대비 ±25bp",
        "• BofA Global Wave: 독점 수치 추정 금지, 최근 공개자료의 방향 전환만 감지",
        "• 하이퍼스케일러 AI 설비투자: ±10% 이상 수치가 명시된 최근 신규자료",
        "",
        "<b>원문</b>",
    ]
    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _remove_old_market_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    skip_labels = (
        "<b>KOSPI</b>",
        "<b>KOSDAQ</b>",
        "• KOSPI 종가:",
        "• KOSDAQ 종가:",
        "• KOSPI 외국인",
        "• KOSDAQ 외국인",
        "• 외국인 수급:",
        "• 수급 판정:",
        "• 수급 숫자 출처:",
    )
    for line in lines:
        if line.startswith(skip_labels):
            continue
        if "KRX 투자자별 거래실적" in line:
            continue
        if "investorDealTrendDay.naver" in line and ("sosok=01" in line or "sosok=02" in line):
            continue
        out.append(line)
    return out


def _rewrite_alert(
    kp_idx: dict[str, Any] | None,
    kp_flow: dict[str, Any] | None,
    kq_idx: dict[str, Any] | None,
    kq_flow: dict[str, Any] | None,
) -> None:
    if not watch.ALERT_PATH.exists():
        return

    lines = watch.ALERT_PATH.read_text(encoding="utf-8").strip().splitlines()
    lines = _remove_old_market_lines(lines)

    if not any("KOSDAQ 외국인: 1일 ±2,000억원" in line for line in lines):
        for i, line in enumerate(lines):
            if line.startswith("• KOSPI 외국인:"):
                lines.insert(i + 1, "• KOSDAQ 외국인: 1일 ±2,000억원, 최근 3거래일 누적 ±5,000억원")
                break

    block = [
        *_market_flow_lines("KOSPI", kp_idx, kp_flow, KOSPI_DAILY_THRESHOLD, KOSPI_THREE_DAY_THRESHOLD),
        "",
        *_market_flow_lines("KOSDAQ", kq_idx, kq_flow, KOSDAQ_DAILY_THRESHOLD, KOSDAQ_THREE_DAY_THRESHOLD),
        "• 수급 판정: 두 시장 모두 18:10 이후 장마감 수급 피드로 임계치 판정",
        "",
    ]
    insert_at = 2 if len(lines) >= 2 else len(lines)
    lines[insert_at:insert_at] = block

    kp_source = str((kp_flow or {}).get("source") or "")
    kq_source = str((kq_flow or {}).get("source") or "")
    if kp_source:
        lines.append(f'• <a href="{html.escape(kp_source, quote=True)}">KOSPI 수급 원문</a>')
    if kq_source:
        lines.append(f'• <a href="{html.escape(kq_source, quote=True)}">KOSDAQ 수급 원문</a>')
    lines.append(f'• <a href="{html.escape(v9.KRX_FLOW_PAGE, quote=True)}">KRX 투자자별 거래실적</a>')
    lines.append("• 수급 숫자 출처: 18:10 이후 네이버 투자자별 매매동향 / KRX 링크는 공식 원천 재확인용")
    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_status(kq_idx: dict[str, Any] | None, kq_flow: dict[str, Any] | None) -> None:
    if not watch.STATUS_PATH.exists():
        return
    text = watch.STATUS_PATH.read_text(encoding="utf-8").rstrip()
    additions: list[str] = []
    if kq_idx and "- KOSDAQ 종가:" not in text:
        additions.append(f"- KOSDAQ 종가: {kq_idx['close']:,.2f} ({kq_idx['change_pct']:+.2f}%), 기준일 {kq_idx['date']}")
    if kq_flow and "- KOSDAQ 외국인:" not in text:
        additions.append(
            f"- KOSDAQ 외국인: 1일 {_direction_amount(int(kq_flow['daily_krw']))}, "
            f"3거래일 {_direction_amount(int(kq_flow['three_day_krw']))}, 기준일 {kq_flow['date']}"
        )
    if additions:
        watch.STATUS_PATH.write_text(text + "\n" + "\n".join(additions) + "\n", encoding="utf-8")


def _append_kosdaq_and_source_labels() -> None:
    now = dt.datetime.now(watch.KST)
    if now.weekday() < 5 and now.time() < dt.time(18, 10):
        return

    errors: list[str] = []
    kq_idx: dict[str, Any] | None = None
    kq_flow: dict[str, Any] | None = None
    try:
        kq_idx = _fetch_index(NAVER_KOSDAQ_PRICE_URL)
    except Exception as exc:
        errors.append(f"KOSDAQ 종가 조회 실패: {type(exc).__name__}: {exc}")
    try:
        kq_flow = _fetch_kosdaq_foreign_flow(now)
    except Exception as exc:
        errors.append(f"KOSDAQ 외국인 수급 조회 실패: {type(exc).__name__}: {exc}")

    pending: dict[str, Any] | None = None
    kp_idx: dict[str, Any] | None = None
    kp_flow: dict[str, Any] | None = None
    old_seen = set((watch.load_state() or {}).get("seen_event_keys") or [])
    hit_keys = _kosdaq_hit_keys(kq_flow)
    new_keys = [key for key in hit_keys if key not in old_seen]

    if watch.PENDING_PATH.exists():
        try:
            pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
            snap = pending.setdefault("snapshot", {})
            kp_idx = snap.get("kospi_close") if isinstance(snap.get("kospi_close"), dict) else None
            kp_flow = snap.get("foreign_flow") if isinstance(snap.get("foreign_flow"), dict) else None
            if kq_idx:
                snap["kosdaq_close"] = kq_idx
            if kq_flow:
                snap["kosdaq_foreign_flow"] = kq_flow
            if isinstance(kp_flow, dict):
                kp_flow["source_label"] = "네이버 장마감 투자자별 매매동향"
            if isinstance(kq_flow, dict):
                kq_flow["source_label"] = "네이버 장마감 투자자별 매매동향"
            snap["flow_source_note"] = (
                "KOSPI·KOSDAQ 자동 수급 숫자는 18:10 이후 네이버 장마감 투자자별 매매동향을 사용. "
                "KRX 투자자별 거래실적은 공식 원천 확인 링크로 제공하며 자동 숫자를 KRX 직접 조회값이라고 오표기하지 않는다."
            )
            seen = list(pending.get("seen_event_keys") or [])
            pending["seen_event_keys"] = list(dict.fromkeys(seen + hit_keys))[-500:]
            active = list(pending.get("active_keys") or [])
            pending["active_keys"] = list(dict.fromkeys(active + hit_keys))
            watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            errors.append(f"KOSDAQ 상태 저장 실패: {type(exc).__name__}: {exc}")

    _ensure_alert_for_new_kosdaq_event(new_keys)

    if watch.ALERT_PATH.exists():
        try:
            if kp_idx is None:
                try:
                    kp_idx = v9._fetch_kospi_close()
                except Exception as exc:
                    errors.append(f"KOSPI 종가 보강 실패: {type(exc).__name__}: {exc}")
            if kp_flow is None and pending:
                snap = pending.get("snapshot") or {}
                kp_flow = snap.get("foreign_flow") if isinstance(snap.get("foreign_flow"), dict) else None
            _rewrite_alert(kp_idx, kp_flow, kq_idx, kq_flow)
        except Exception as exc:
            errors.append(f"KOSPI·KOSDAQ 알림 형식 통일 실패: {type(exc).__name__}: {exc}")

    try:
        _append_status(kq_idx, kq_flow)
    except Exception as exc:
        errors.append(f"KOSDAQ 상태 요약 보강 실패: {type(exc).__name__}: {exc}")

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

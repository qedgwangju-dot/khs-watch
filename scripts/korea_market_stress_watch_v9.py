#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any

import requests

import korea_market_stress_watch_v6 as v6

watch = v6.watch
_original_add_event = watch.add_event
_original_fetch_flow = watch.fetch_kospi_foreign_flow

NAVER_KOSPI_PRICE_URL = "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=5&page=1"
KRX_FLOW_PAGE = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT022"


def _fmt_amount(value_krw: int) -> str:
    eok = int(round(abs(value_krw) / 100_000_000))
    jo, rem = divmod(eok, 10_000)
    if jo and rem:
        amount = f"{jo}조{rem:,}억원"
    elif jo:
        amount = f"{jo}조원"
    else:
        amount = f"{rem:,}억원"
    if value_krw > 0:
        return "+" + amount
    if value_krw < 0:
        return "-" + amount
    return "0억원"


def _final_window(now: dt.datetime) -> bool:
    return now.weekday() >= 5 or now.time() >= dt.time(18, 10)


def fetch_flow(now: dt.datetime) -> dict[str, Any]:
    flow = _original_fetch_flow(now)
    flow["phase"] = "장마감 최종 재확인" if _final_window(now) else "장중 참고"
    return flow


def _rewrite_foreign_text(text: str) -> str:
    text = re.sub(r"KOSPI 외국인 1일 순매수 -([^—]+)", r"KOSPI 외국인 장마감 최종 재확인: 1일 순매도 \1", text)
    text = re.sub(r"KOSPI 외국인 1일 순매수 \+([^—]+)", r"KOSPI 외국인 장마감 최종 재확인: 1일 순매수 \1", text)
    text = re.sub(r"KOSPI 외국인 최근 3거래일 누적 -([^—]+)", r"KOSPI 외국인 장마감 최종 재확인: 최근 3거래일 누적 순매도 \1", text)
    text = re.sub(r"KOSPI 외국인 최근 3거래일 누적 \+([^—]+)", r"KOSPI 외국인 장마감 최종 재확인: 최근 3거래일 누적 순매수 \1", text)
    text = text.replace("— -1조원 기준 돌파", "— 순매도 1조원 기준 돌파")
    text = text.replace("— +1조원 기준 돌파", "— 순매수 1조원 기준 돌파")
    text = text.replace("— -3조원 기준 돌파", "— 누적 순매도 3조원 기준 돌파")
    text = text.replace("— +3조원 기준 돌파", "— 누적 순매수 3조원 기준 돌파")
    return text


def add_event_final_only(events, key: str, text: str, source: str) -> None:
    now = dt.datetime.now(watch.KST)
    if key.startswith("foreign1d_") or key.startswith("foreign3d_"):
        # 사용자 기준: 외국인 수급 임계치 경보는 장중 잠정치가 아니라 장마감 이후 재확인값으로만 판정한다.
        # KRX는 당일 최종 투자자별 매매내역을 오후 6시 이후 제공한다고 명시한다.
        if now.weekday() < 5 and now.time() < dt.time(18, 10):
            return
        text = _rewrite_foreign_text(text)
        key = f"{key}:final"
    _original_add_event(events, key, text, source)


def _fetch_kospi_close() -> dict[str, Any] | None:
    r = requests.get(NAVER_KOSPI_PRICE_URL, headers=watch.HEADERS, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    close = float(str(row.get("closePrice") or "0").replace(",", ""))
    pct = float(str(row.get("fluctuationsRatio") or "0").replace(",", ""))
    return {
        "date": str(row.get("localTradedAt") or "")[:10],
        "close": close,
        "change_pct": pct,
        "source": NAVER_KOSPI_PRICE_URL,
    }


def _append_final_context() -> None:
    now = dt.datetime.now(watch.KST)
    if now.weekday() < 5 and now.time() < dt.time(18, 10):
        return
    try:
        idx = _fetch_kospi_close()
        if watch.PENDING_PATH.exists():
            pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
            if idx:
                pending.setdefault("snapshot", {})["kospi_close"] = idx
            pending.setdefault("snapshot", {})["flow_finality_note"] = (
                "외국인 임계치 경보는 18:10 이후 재조회한 마감값으로만 판정. "
                "KRX는 당일 최종 투자자별 매매내역을 오후 6시 이후 제공하며, 자동화에서는 접근 가능한 KRX 기반 네이버 국내증시 데이터를 재조회해 사용."
            )
            pending.setdefault("snapshot", {})["krx_flow_info_url"] = KRX_FLOW_PAGE
            watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if not watch.ALERT_PATH.exists() or not idx:
            return
        text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
        if "KOSPI 종가:" in text:
            return
        lines = text.splitlines()
        insert_at = 2 if len(lines) >= 2 else len(lines)
        lines.insert(insert_at, f"• KOSPI 종가: {idx['close']:,.2f} ({idx['change_pct']:+.2f}%)")
        lines.insert(insert_at + 1, "• 외국인 수급: 18:10 이후 마감값 재확인 후 임계치 판정")
        lines += ["", f'• <a href="{html.escape(KRX_FLOW_PAGE, quote=True)}">KRX 투자자별 거래실적</a>']
        watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
            f.write(f"장마감 종가 확인 실패: {type(exc).__name__}: {exc}\n")


watch.fmt_eok = _fmt_amount
watch.fetch_kospi_foreign_flow = fetch_flow
watch.add_event = add_event_final_only


def main() -> int:
    rc = watch.main()
    _append_final_context()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

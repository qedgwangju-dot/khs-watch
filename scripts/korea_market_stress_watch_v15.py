#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

import korea_market_stress_watch_v14 as v14

watch = v14.watch
core = v14.v13.core

FINAL_FLOW_SEED = {
    "KOSPI": {
        "2026-09-15": -15458.0,
        "2026-09-16": -16726.0,
    },
    "KOSDAQ": {
        "2026-09-15": 272.0,
        "2026-09-16": -272.0,
    },
}


def _load_final_history(market_name: str) -> list[dict[str, Any]]:
    try:
        state = watch.load_state() or {}
    except Exception:
        state = {}
    root = state.get("final_flow_history") or {}
    rows = root.get(market_name) or []
    by_date: dict[str, float] = dict(FINAL_FLOW_SEED.get(market_name) or {})
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            d = str(row.get("date") or "")
            v = float(row.get("daily_eok"))
        except Exception:
            continue
        if d:
            by_date[d] = v
    return [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items())][-10:]


def _persist_final_history() -> None:
    if not watch.PENDING_PATH.exists():
        return
    try:
        pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
        old = watch.load_state() or {}
    except Exception:
        return

    root: dict[str, list[dict[str, Any]]] = {}
    old_root = old.get("final_flow_history") or {}
    for market in ("KOSPI", "KOSDAQ"):
        by_date: dict[str, float] = dict(FINAL_FLOW_SEED.get(market) or {})
        for row in old_root.get(market) or []:
            if not isinstance(row, dict):
                continue
            try:
                d = str(row.get("date") or "")
                v = float(row.get("daily_eok"))
            except Exception:
                continue
            if d:
                by_date[d] = v
        snap = pending.get("snapshot") or {}
        flow_key = "foreign_flow" if market == "KOSPI" else "kosdaq_foreign_flow"
        flow = snap.get(flow_key) or {}
        try:
            d = str(flow.get("date") or "")
            v = float(flow.get("daily_eok"))
            checked = dt.datetime.fromisoformat(str(snap.get("checked_at_kst")))
        except Exception:
            d = ""
            v = 0.0
            checked = dt.datetime.now(watch.KST)
        if d and checked.time() >= dt.time(18, 10):
            by_date[d] = v
        root[market] = [{"date": d, "daily_eok": v} for d, v in sorted(by_date.items())][-10:]
    pending["final_flow_history"] = root
    watch.PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_persist_ls_history() -> None:
    now = dt.datetime.now(watch.KST)
    original_updates = dict(core._ls_history_updates)
    try:
        if now.time() < dt.time(18, 10):
            core._ls_history_updates.clear()
        else:
            for market in list(core._ls_history_updates):
                status = (core._validation.get(market) or {}).get("status")
                if status not in {"matched", "ls_fallback"}:
                    core._ls_history_updates.pop(market, None)
        _ORIGINAL_PERSIST_LS()
    finally:
        core._ls_history_updates.clear()
        core._ls_history_updates.update(original_updates)


def _fetch_same_day_1530_close(day: dt.date) -> dict[str, Any] | None:
    candidates: list[tuple[int, str, str]] = []
    for page in range(1, 8):
        try:
            r = requests.get(v14.KSURE_FX_LIST.format(page=page), headers=watch.HEADERS, timeout=20)
            r.raise_for_status()
        except Exception:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "")
            m = re.search(r"fxview\?id=(\d{12,})", href)
            if not m:
                continue
            item_id = m.group(1)
            if item_id[:8] != day.strftime("%Y%m%d"):
                continue
            try:
                hhmm = int(item_id[8:12])
            except Exception:
                continue
            if not (1500 <= hhmm <= 1605):
                continue
            title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            if not any(k in title for k in ("외국환시세", "달러-원", "원/달러", "[외환]")):
                continue
            candidates.append((hhmm, item_id, title))
        if candidates:
            break
    for _, item_id, title in sorted(candidates, reverse=True):
        rate = v14._extract_krw_rate(title)
        detail_url = v14.KSURE_FX_VIEW.format(id=item_id)
        if rate is None:
            try:
                rr = requests.get(detail_url, headers=watch.HEADERS, timeout=20)
                rr.raise_for_status()
                txt = BeautifulSoup(rr.text, "html.parser").get_text(" ", strip=True)
                rate = v14._extract_krw_rate(txt)
            except Exception:
                continue
        if rate is not None and 900.0 <= rate <= 2500.0:
            return {"value": float(rate), "source": detail_url, "title": title}
    return None


def _correct_fx_direction_text(text: str) -> str:
    if "원/달러 상승 = 원화 약세" not in text:
        return text
    replacements = {
        "항공유·리스·정비 등 달러 비용의 원화 환산 부담 감소":
            "항공유·리스·정비 등 달러 비용의 원화 환산 부담 증가",
        "철광석·원료탄 등 달러 결제 수입 원재료의 원화 비용 감소":
            "철광석·원료탄 등 달러 결제 수입 원재료의 원화 비용 증가",
        "연료·에너지 수입 비용의 원화 환산 부담 감소":
            "연료·에너지 수입 비용의 원화 환산 부담 증가",
        "상반기 해외매출 비중 83% → 같은 달러 매출의 원화 환산액 감소 부담. 수입 원재료 비용 감소가 일부 상쇄":
            "상반기 해외매출 비중 83% → 같은 달러 매출의 원화 환산액 증가에 우호적. 수입 원재료 비용 증가는 일부 상쇄",
        "수출·해외 판매의 달러 매출을 원화로 환산할 때 매출·이익 부담":
            "수출·해외 판매의 달러 매출을 원화로 환산할 때 매출·이익에 우호적. 해외·수입 비용과 환헤지는 상쇄 요인",
        "달러 매출 비중이 크고 원화 비용이 존재해 원화 강세가 단기 이익 역풍으로 작용 가능":
            "달러 매출 비중이 크고 원화 비용이 존재해 원화 약세가 원화 환산 실적에 우호적일 수 있음. 수입 장비·소재와 환헤지는 일부 상쇄",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _rewrite_afterhours_fx_label(text: str) -> str:
    try:
        pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
        snap = pending.get("snapshot") or {}
        checked = dt.datetime.fromisoformat(str(snap.get("checked_at_kst")))
        fx = snap.get("usdkrw") or {}
        cur = float(fx["value"])
        prev = float(fx["prev_value"])
    except Exception:
        return text
    if checked.time() <= dt.time(15, 35):
        return text
    if "원/달러 일간 급등:" not in text and "원/달러 일간 급락:" not in text:
        return text

    direction = "급등" if "원/달러 일간 급등:" in text else "급락"
    text = text.replace(f"원/달러 일간 {direction}:", f"원/달러 장마감 이후 현재 {direction}:")
    close = _fetch_same_day_1530_close(checked.date())
    if not close:
        return text
    close_val = float(close["value"])
    close_krw = close_val - prev
    close_pct = (close_val / prev - 1.0) * 100.0
    regular_hit = abs(close_krw) >= 20.0 or abs(close_pct) >= 1.0
    verdict = "정규장 임계치 충족" if regular_hit else "정규장 임계치 미충족"
    marker = next((line for line in text.splitlines() if f"원/달러 장마감 이후 현재 {direction}:" in line), None)
    if marker:
        extra = (
            f"\n  ↳ 서울외환시장 15:30 공식 마감: <b>{prev:,.1f}원 → {close_val:,.1f}원 "
            f"({close_krw:+,.1f}원, {close_pct:+.2f}%)</b> · {verdict}"
            f" / <a href=\"{html.escape(str(close['source']), quote=True)}\">15:30 공식 근거</a>"
        )
        text = text.replace(marker, marker + extra, 1)
    return text


def _postprocess_alert() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8")
    text = _correct_fx_direction_text(text)
    text = _rewrite_afterhours_fx_label(text)
    watch.ALERT_PATH.write_text(text, encoding="utf-8")


_ORIGINAL_LOAD_HISTORY = core._load_history
_ORIGINAL_PERSIST_LS = core._persist_ls_history_and_source_note


def main() -> int:
    core._load_history = _load_final_history
    core._persist_ls_history_and_source_note = _safe_persist_ls_history
    try:
        rc = v14.main()
    finally:
        core._load_history = _ORIGINAL_LOAD_HISTORY
        core._persist_ls_history_and_source_note = _ORIGINAL_PERSIST_LS
    _persist_final_history()
    _postprocess_alert()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

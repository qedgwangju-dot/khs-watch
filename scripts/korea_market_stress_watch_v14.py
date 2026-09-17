#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import korea_market_stress_watch_v13 as v13

watch = v13.watch

KSURE_FX_LIST = "https://ksureapi.einfomax.co.kr/v2/datafeed/ksure/fxlist?page={page}"
KSURE_FX_VIEW = "https://ksureapi.einfomax.co.kr/v2/datafeed/ksure/fxview?id={id}"
_original_fetch_usdkrw = watch.fetch_usdkrw


def _extract_krw_rate(text: str) -> float | None:
    # Prefer explicit 1,xxx원 values in headlines such as
    # '원/달러 환율 9.2원 오른 1,368.6원' or '달러-원 ... 1,368.60원'.
    vals = re.findall(r"(?<!\d)([12],\d{3}(?:\.\d+)?)\s*원", text)
    if vals:
        try:
            return float(vals[-1].replace(",", ""))
        except Exception:
            pass
    # Foreign-exchange table detail: '미국 달러* | 1,368.60'.
    m = re.search(r"미국\s*달러\*?.{0,80}?([12],\d{3}(?:\.\d+)?)", text, re.S)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except Exception:
            pass
    return None


def fetch_seoul_prev_close(now: dt.datetime | None = None) -> dict[str, Any]:
    """Find the latest Seoul USD/KRW 15:30 close before today.

    Source is KSURE's public FX news feed, which republishes Seoul Foreign
    Exchange Brokerage / Infomax close data. We deliberately reject 06:00
    night-session closes and use the 15:30 Seoul session close only.
    """
    now = now or dt.datetime.now(watch.KST)
    today = now.date()
    candidates: list[tuple[dt.date, int, str, str]] = []

    for page in range(1, 13):
        r = requests.get(KSURE_FX_LIST.format(page=page), headers=watch.HEADERS, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        page_candidates: list[tuple[dt.date, int, str, str]] = []
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "")
            m = re.search(r"fxview\?id=(\d{12,})", href)
            if not m:
                continue
            item_id = m.group(1)
            if len(item_id) < 12:
                continue
            try:
                day = dt.datetime.strptime(item_id[:8], "%Y%m%d").date()
                hhmm = int(item_id[8:12])
            except Exception:
                continue
            if day >= today or not (1500 <= hhmm <= 1605):
                continue
            title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            if not any(k in title for k in ("외국환시세", "달러-원", "원/달러")):
                continue
            if not any(k in title for k in ("15:30", "15.30", "서울장 마감", "마감", "기준가")):
                continue
            page_candidates.append((day, hhmm, item_id, title))
        if page_candidates:
            candidates.extend(page_candidates)
            # List is reverse chronological; once a prior-day close appears,
            # the latest valid prior session is already represented.
            break

    if not candidates:
        raise RuntimeError("KSURE에서 전일 서울 15:30 달러-원 종가를 찾지 못함")

    for day, hhmm, item_id, title in sorted(candidates, reverse=True):
        rate = _extract_krw_rate(title)
        detail_url = KSURE_FX_VIEW.format(id=item_id)
        detail_text = ""
        if rate is None:
            rr = requests.get(detail_url, headers=watch.HEADERS, timeout=25)
            rr.raise_for_status()
            detail_text = BeautifulSoup(rr.text, "html.parser").get_text(" ", strip=True)
            rate = _extract_krw_rate(detail_text)
        if rate is not None and 900.0 <= rate <= 2500.0:
            return {
                "date": day.isoformat(),
                "value": float(rate),
                "title": title,
                "source": detail_url,
                "basis": "서울외환시장 15:30 USD/KRW 종가",
            }

    raise RuntimeError("KSURE 서울 15:30 종가 숫자 파싱 실패")


def fetch_usdkrw_seoul_basis() -> dict[str, Any]:
    live = _original_fetch_usdkrw()
    # Preserve Naver's previous published value for diagnostics only; it is not
    # the Seoul 15:30 spot close and must not drive the ±20원/±1% market alert.
    naver_prev_date = live.get("prev_date")
    naver_prev_value = live.get("prev_value")
    try:
        ref = fetch_seoul_prev_close()
    except Exception as exc:
        live["comparison_basis"] = "Naver 시계열 대체 — 서울 15:30 종가 조회 실패"
        live["seoul_close_error"] = f"{type(exc).__name__}: {exc}"
        return live

    current = float(live["value"])
    prev = float(ref["value"])
    live["naver_prev_date"] = naver_prev_date
    live["naver_prev_value"] = naver_prev_value
    live["prev_date"] = ref["date"]
    live["prev_value"] = prev
    live["change_krw"] = round(current - prev, 4)
    live["change_pct"] = round((current / prev - 1.0) * 100.0, 4)
    live["comparison_basis"] = ref["basis"]
    live["seoul_close_source"] = ref["source"]
    live["seoul_close_title"] = ref["title"]
    return live


def _korean_news_title(title: str) -> str:
    raw = html.unescape(title).strip()
    low = raw.lower()
    if not raw or re.search(r"[가-힣]", raw):
        return raw

    company = "해외 하이퍼스케일러"
    if "meta" in low:
        company = "Meta(META)"
    elif "microsoft" in low:
        company = "Microsoft"
    elif "alphabet" in low or "google" in low:
        company = "Alphabet(Google)"
    elif "amazon" in low or "aws" in low:
        company = "Amazon(AWS)"

    pcts = re.findall(r"-?\d+(?:\.\d+)?%", raw)
    pct_text = " · ".join(pcts[:3])

    if "meta" in low and ("crash" in low or "crashing" in low) and "capex" in low:
        return (
            f"{company}: 실적 발표 후 주가 급락 · 주당순이익 예상 하회 · "
            "잉여현금흐름 감소 · 설비투자 가이던스 재상향"
            + (f" ({pct_text})" if pct_text else "")
        )
    if any(x in low for x in ("raise", "raised", "raises", "increase", "increased", "boost")) and any(
        x in low for x in ("capex", "capital spending", "capital expenditure")
    ):
        return f"{company}: 인공지능·데이터센터 설비투자 전망 상향" + (f" ({pct_text})" if pct_text else "")
    if any(x in low for x in ("cut", "cuts", "lower", "reduced", "reduce")) and any(
        x in low for x in ("capex", "capital spending", "capital expenditure")
    ):
        return f"{company}: 인공지능·데이터센터 설비투자 전망 하향" + (f" ({pct_text})" if pct_text else "")
    if "global wave" in low:
        return "BofA Global Wave: 최근 공개자료에서 경기·이익수정 방향 전환 신호 감지"
    if any(x in low for x in ("capex", "capital spending", "capital expenditure", "data center", "ai infrastructure")):
        return f"{company}: 인공지능·데이터센터 설비투자 관련 신규자료" + (f" ({pct_text})" if pct_text else "")
    return "해외 영문 신규자료: 핵심 내용 한국어 검토 필요"


def _translate_english_alert_lines() -> None:
    if not watch.ALERT_PATH.exists():
        return
    lines = watch.ALERT_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        prefixes = (
            "• 하이퍼스케일러 AI 설비투자 ±10% 이상 수치 포함 신규자료: ",
            "• BofA Global Wave 방향 전환 공개자료: ",
            "• BofA Global Wave 방향 전환 관련 신규 공개자료: ",
        )
        replaced = False
        for prefix in prefixes:
            if line.startswith(prefix):
                title = line[len(prefix):]
                out.append(prefix + html.escape(_korean_news_title(title)))
                replaced = True
                break
        if not replaced:
            out.append(line)
    watch.ALERT_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def _append_fx_basis_note() -> None:
    if not watch.ALERT_PATH.exists() or not watch.PENDING_PATH.exists():
        return
    try:
        import json
        pending = json.loads(watch.PENDING_PATH.read_text(encoding="utf-8"))
        fx = (pending.get("snapshot") or {}).get("usdkrw") or {}
    except Exception:
        return
    if not fx.get("comparison_basis"):
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8").rstrip()
    note = (
        f"\n• 환율 일간 비교 기준: <b>{html.escape(str(fx['comparison_basis']))}</b>"
        f" — 전일 {float(fx['prev_value']):,.1f}원 → 현재 {float(fx['value']):,.1f}원"
    )
    src = str(fx.get("seoul_close_source") or "")
    if src:
        note += f' / <a href="{html.escape(src, quote=True)}">전일 서울 종가 근거</a>'
    watch.ALERT_PATH.write_text(text + note + "\n", encoding="utf-8")


def main() -> int:
    # Replace the old Naver day-row comparison with Seoul 15:30 spot-close basis.
    original_fx_fetcher = watch.fetch_usdkrw
    watch.fetch_usdkrw = fetch_usdkrw_seoul_basis

    # v12 has a legacy direct Telegram sender. Suppress it here so LS/source
    # post-processing and Korean headline translation finish before the workflow
    # sends the final artifact through the configured target bot.
    legacy_module = v13.core.v12
    original_sender = legacy_module._send_market_alert_to_target
    legacy_module._send_market_alert_to_target = lambda: None
    try:
        rc = v13.main()
    finally:
        legacy_module._send_market_alert_to_target = original_sender
        watch.fetch_usdkrw = original_fx_fetcher
    _translate_english_alert_lines()
    _append_fx_basis_note()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

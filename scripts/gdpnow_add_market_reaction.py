#!/usr/bin/env python3
"""Add verified, time-stamped market observations to the GDPNow rate alert.

The FRED page "Updated" clock is a *data-feed update* time, not necessarily the
release of the underlying economic report. This formatter never calls it a Fed
announcement or asserts causality. Quotes use their own actual timestamps and
no later quote is substituted as if it were an earlier observation.
"""
from __future__ import annotations
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "gdpnow_long_rates_alert.html"
REACTION = ROOT / "out" / "gdpnow_intraday_rate_reaction.json"

def when(p: dict | None) -> str:
    if not p:
        return "시각 미확인"
    raw = str(p.get("timestamp_kst") or "")
    return (raw[11:16] + " KST") if len(raw) >= 16 else "시각 미확인"

def fmt_yield(p: dict | None) -> str:
    if not p or p.get("yield_pct") is None:
        return "확인 불가"
    return f"{float(p['yield_pct']):.4f}% ({when(p)})"

def fmt_oil(p: dict | None) -> str:
    if not p or p.get("price_usd") is None:
        return "확인 불가"
    return f"{float(p['price_usd']):.2f}달러/배럴 ({when(p)})"

def fmt_bp(val) -> str:
    return "확인 불가" if val is None else f"{float(val):+.2f}bp"

def fmt_pct(val) -> str:
    return "확인 불가" if val is None else f"{float(val):+.2f}%"

def main() -> int:
    if not ALERT.exists():
        return 0
    text = ALERT.read_text(encoding="utf-8").strip()
    if not REACTION.exists():
        data = {"error":"발표 당시 시장 원자료 파일 없음"}
    else:
        try:
            data = json.loads(REACTION.read_text(encoding="utf-8"))
        except Exception as e:
            data = {"error":f"시장 자료 형식 오류 {type(e).__name__}"}

    kst = str(data.get("release_timestamp_kst") or "")
    event_label = (kst.replace("T", " ")[:16] + " KST") if kst else "확인 불가"
    ten = data.get("ten_year") or {}
    thirty = data.get("thirty_year") or {}

    block = [
        "",
        "⏱ <b>GDPNow 데이터 갱신 전후 금리</b>",
        f"• FRED 데이터 갱신 기록: <b>{html.escape(event_label)}</b>",
        "• 주의: FRED 갱신 시각은 최초 GDPNow 공개 또는 원천 경제지표 발표 시각과 다를 수 있습니다.",
    ]

    if ten or thirty:
        for title, v in (("미국 10년물",ten),("미국 30년물",thirty)):
            block += [
                f"• {title}",
                f"  직전: {fmt_yield(v.get('pre'))}",
                f"  기준 시각 인근: {fmt_yield(v.get('at_release'))} ({fmt_bp(v.get('change_at_bp'))})",
                f"  +5분 관측: {fmt_yield(v.get('plus_5m'))} ({fmt_bp(v.get('change_5m_bp'))})",
                f"  +30분 관측: {fmt_yield(v.get('plus_30m'))} ({fmt_bp(v.get('change_30m_bp'))})",
            ]
        confirmation = data.get("market_confirmation_30m") or data.get("market_confirmation_5m") or "확인 불가"
        predicted = ""
        if "장기금리 상승" in text[:850]:
            predicted = "상승"
        elif "장기금리 하락" in text[:850]:
            predicted = "하락"
        actual = "상승" if "상승 확인" in confirmation else ("하락" if "하락 확인" in confirmation else "")
        if actual and predicted:
            agreement = "일치" if actual == predicted else "불일치"
            block += [f"• GDP 구성 압력 {predicted} / 동시간대 관측 {actual}: <b>{agreement}</b> (인과관계 미확인)"]
        else:
            block += [f"• 동시간대 금리 반응: <b>{html.escape(str(confirmation))}</b>"]
    else:
        block += ["• 당시 10년물·30년물 관측값 <b>확인 불가</b> — 현재 금리로 대체하지 않음"]

    brent, wti = data.get("brent") or {}, data.get("wti") or {}
    block += ["","🛢 <b>유가 변화가 금리 압력을 강화했나</b>"]
    if brent or wti:
        for label, oil in (("Brent 선물",brent),("WTI 선물",wti)):
            block += [
                f"• {label}",
                f"  이전 거래일 종가: {fmt_oil(oil.get('previous_close'))}",
                f"  GDPNow 데이터 갱신 인근: {fmt_oil(oil.get('at_release'))}",
                f"  전일 종가 대비: {fmt_pct(oil.get('day_change_at_pct'))}",
                f"  +30분: {fmt_oil(oil.get('plus_30m'))} (직전 대비 {fmt_pct(oil.get('change_30m_pct'))})",
            ]
        signal = data.get("oil_rate_signal") or "판정 보류"
        block += [
            f"• <b>전일 대비 유가 압력</b>: {html.escape(str(signal))}",
            "• 전일 대비 유가 방향과 데이터 갱신 후 30분 변화는 별개입니다. 유가의 상승·하락이 다른 원인일 수도 있습니다.",
        ]
    else:
        block += ["• Brent·WTI 당시값 확인 불가 — 현재 선물가격으로 대체하지 않음"]
    if data.get("error"):
        block += ["",f"• 일부 원자료 조회 실패: {html.escape(str(data['error']))}"]
    block += [
        "",
        "• 인용 시장값: 1분 단위 Cboe 금리지수(^TNX/^TYX) 및 Brent/WTI 선물 근접 관측. 각 괄호에 실제 관측 시각 표기.",
        "• 미 재무부 공식 금리 종가는 같은 날 일일 기준 별도 검산용이며, 당시 1분 금리를 대체하지 않습니다.",
        "• GDP 구성의 이론상 금리 방향과 실제 금리 움직임을 구분합니다. 다른 경제지표·FOMC 발언·유가·국채수급이 동시에 움직일 수 있습니다.",
    ]
    lines = text.splitlines()
    location = min(4,len(lines))
    ALERT.write_text("\n".join(lines[:location]+block+lines[location:]).strip()+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

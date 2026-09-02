#!/usr/bin/env python3
"""Insert exact event-time 10Y/30Y and oil values into the GDPNow Telegram alert."""
from __future__ import annotations

import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "gdpnow_long_rates_alert.html"
REACTION = ROOT / "out" / "gdpnow_intraday_rate_reaction.json"


def fmt_yield_point(p: dict | None) -> str:
    if not p:
        return "확인 불가"
    return f"{float(p['yield_pct']):.4f}%"


def fmt_price_point(p: dict | None) -> str:
    if not p:
        return "확인 불가"
    return f"${float(p['price_usd']):.2f}"


def fmt_bp(v) -> str:
    if v is None:
        return "확인 불가"
    return f"{float(v):+.2f}bp"


def fmt_pct(v) -> str:
    if v is None:
        return "확인 불가"
    return f"{float(v):+.2f}%"


def main() -> int:
    if not ALERT.exists() or not REACTION.exists():
        return 0
    text = ALERT.read_text(encoding="utf-8").strip()
    try:
        data = json.loads(REACTION.read_text(encoding="utf-8"))
    except Exception:
        return 0

    kst = str(data.get("release_timestamp_kst") or "")
    et = str(data.get("release_timestamp_et") or "")
    kst_short = kst.replace("T", " ")[:16] + " KST" if kst else "확인 불가"
    et_short = et.replace("T", " ")[:16] + " ET" if et else "확인 불가"

    block: list[str] = ["", "⏱ <b>발표 당시 시장값 · 정확한 시각 기준</b>"]
    if kst:
        block.append(f"• GDPNow 확인시각: <b>{html.escape(kst_short)}</b> ({html.escape(et_short)})")

    ten = data.get("ten_year") or {}
    thirty = data.get("thirty_year") or {}
    have_rates = bool(ten) and bool(thirty)
    if have_rates:
        mat = str(data.get("market_confirmation_at") or "확인 불가")
        m5 = str(data.get("market_confirmation_5m") or "확인 불가")
        m30 = str(data.get("market_confirmation_30m") or "확인 불가")

        predicted = ""
        if "장기금리 상승" in text[:700]:
            predicted = "상승"
        elif "장기금리 하락" in text[:700]:
            predicted = "하락"

        confirm_source = m30 if m30 != "확인 불가" else (m5 if m5 != "확인 불가" else mat)
        actual = ""
        if "상승 확인" in confirm_source:
            actual = "상승"
        elif "하락 확인" in confirm_source:
            actual = "하락"

        if predicted and actual:
            if predicted == actual:
                consistency = f"✅ GDP 구성 판정({predicted})과 실제 동시간대 금리 반응({actual}) <b>일치</b>"
            else:
                consistency = f"❌ GDP 구성 판정({predicted})과 실제 동시간대 금리 반응({actual}) <b>불일치</b>"
        else:
            consistency = f"⚪ 실제 동시간대 시장 반응: <b>{html.escape(confirm_source)}</b>"

        block += [
            "• 10Y: "
            f"직전 <b>{fmt_yield_point(ten.get('pre'))}</b> → 발표시각 <b>{fmt_yield_point(ten.get('at_release'))}</b> ({fmt_bp(ten.get('change_at_bp'))}) "
            f"→ +5분 <b>{fmt_yield_point(ten.get('plus_5m'))}</b> ({fmt_bp(ten.get('change_5m_bp'))}) "
            f"→ +30분 <b>{fmt_yield_point(ten.get('plus_30m'))}</b> ({fmt_bp(ten.get('change_30m_bp'))})",
            "• 30Y: "
            f"직전 <b>{fmt_yield_point(thirty.get('pre'))}</b> → 발표시각 <b>{fmt_yield_point(thirty.get('at_release'))}</b> ({fmt_bp(thirty.get('change_at_bp'))}) "
            f"→ +5분 <b>{fmt_yield_point(thirty.get('plus_5m'))}</b> ({fmt_bp(thirty.get('change_5m_bp'))}) "
            f"→ +30분 <b>{fmt_yield_point(thirty.get('plus_30m'))}</b> ({fmt_bp(thirty.get('change_30m_bp'))})",
            f"• 발표시각 금리 확인: <b>{html.escape(mat)}</b> · +5분 <b>{html.escape(m5)}</b> · +30분 <b>{html.escape(m30)}</b>",
            f"• {consistency}",
        ]
    else:
        block += [
            "• 10Y·30Y 정확한 당시값 확인 불가 — <b>현재값으로 대체하지 않음</b>",
        ]

    brent = data.get("brent") or {}
    wti = data.get("wti") or {}
    have_oil = bool(brent) and bool(wti)
    block += ["", "🛢 <b>유가 · 금리 방향 보정</b>"]
    if have_oil:
        oil_signal = str(data.get("oil_rate_signal") or "유가 방향 확인 불가")
        block += [
            "• Brent: "
            f"전일 종가 <b>{fmt_price_point(brent.get('previous_close'))}</b> → 발표시각 <b>{fmt_price_point(brent.get('at_release'))}</b> "
            f"(<b>{fmt_pct(brent.get('day_change_at_pct'))}</b>) → +30분 <b>{fmt_price_point(brent.get('plus_30m'))}</b>",
            "• WTI: "
            f"전일 종가 <b>{fmt_price_point(wti.get('previous_close'))}</b> → 발표시각 <b>{fmt_price_point(wti.get('at_release'))}</b> "
            f"(<b>{fmt_pct(wti.get('day_change_at_pct'))}</b>) → +30분 <b>{fmt_price_point(wti.get('plus_30m'))}</b>",
            f"• 유가 판정: <b>{html.escape(oil_signal)}</b>",
            "• 유가가 급등하면 GDPNow와 별개로 기대인플레이션·Fed 긴축 기대를 통해 장기금리 상승 압력을 더할 수 있음.",
            "• 반대로 유가가 크게 하락하면 강한 GDP의 금리 상승 효과를 일부 상쇄할 수 있음.",
        ]
    else:
        block += [
            "• 발표 당시 Brent·WTI 정확한 값 확인 불가 — <b>현재 유가로 대체하지 않음</b>",
        ]

    if data.get("error"):
        block += ["", f"• 부분 확인 오류: {html.escape(str(data.get('error')))}"]

    block += [
        "",
        "• 금리 당시값: Cboe TNX/TYX 1분 데이터 기반, 유가는 Brent/WTI 선물 1분 데이터 기반. 미 재무부 공식 일일 금리는 사후 종가 검산.",
        "• 같은 시각 유가·Fed 발언·국채수급·지정학 뉴스가 함께 움직일 수 있으므로 GDP 효과와 외생 요인을 분리해서 판정.",
    ]

    lines = text.splitlines()
    insert_at = min(4, len(lines))
    out = lines[:insert_at] + block + lines[insert_at:]
    ALERT.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

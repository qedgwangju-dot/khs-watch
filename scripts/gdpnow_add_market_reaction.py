#!/usr/bin/env python3
"""Insert exact event-time 10Y/30Y values into the formatted GDPNow Telegram alert."""
from __future__ import annotations

import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "gdpnow_long_rates_alert.html"
REACTION = ROOT / "out" / "gdpnow_intraday_rate_reaction.json"


def fmt_point(p: dict | None) -> str:
    if not p:
        return "확인 불가"
    return f"{float(p['yield_pct']):.4f}%"


def fmt_bp(v) -> str:
    if v is None:
        return "확인 불가"
    return f"{float(v):+.2f}bp"


def main() -> int:
    if not ALERT.exists() or not REACTION.exists():
        return 0
    text = ALERT.read_text(encoding="utf-8").strip()
    try:
        data = json.loads(REACTION.read_text(encoding="utf-8"))
    except Exception:
        return 0

    # Never substitute a current/latest rate when the exact event-time observation failed.
    if data.get("error"):
        block = [
            "",
            "⏱ <b>발표 당시 금리</b>",
            "• 정확한 당시값 확인 불가 — <b>현재값으로 대체하지 않음</b>",
            f"• 사유: {html.escape(str(data.get('error')))}",
        ]
    else:
        ten = data.get("ten_year") or {}
        thirty = data.get("thirty_year") or {}
        kst = str(data.get("release_timestamp_kst") or "")
        et = str(data.get("release_timestamp_et") or "")
        kst_short = kst.replace("T", " ")[:16] + " KST" if kst else "확인 불가"
        et_short = et.replace("T", " ")[:16] + " ET" if et else "확인 불가"

        mat = str(data.get("market_confirmation_at") or "확인 불가")
        m5 = str(data.get("market_confirmation_5m") or "확인 불가")
        m30 = str(data.get("market_confirmation_30m") or "확인 불가")

        predicted = ""
        if "장기금리 상승" in text[:700]:
            predicted = "상승"
        elif "장기금리 하락" in text[:700]:
            predicted = "하락"

        # Prefer +5m for a prompt confirmation; use +30m only when already available.
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

        block = [
            "",
            "⏱ <b>발표 당시 금리 · 정확한 시각값</b>",
            f"• GDPNow 확인시각: <b>{html.escape(kst_short)}</b> ({html.escape(et_short)})",
            "• 10Y: "
            f"직전 <b>{fmt_point(ten.get('pre'))}</b> → 발표시각 <b>{fmt_point(ten.get('at_release'))}</b> ({fmt_bp(ten.get('change_at_bp'))}) "
            f"→ +5분 <b>{fmt_point(ten.get('plus_5m'))}</b> ({fmt_bp(ten.get('change_5m_bp'))}) "
            f"→ +30분 <b>{fmt_point(ten.get('plus_30m'))}</b> ({fmt_bp(ten.get('change_30m_bp'))})",
            "• 30Y: "
            f"직전 <b>{fmt_point(thirty.get('pre'))}</b> → 발표시각 <b>{fmt_point(thirty.get('at_release'))}</b> ({fmt_bp(thirty.get('change_at_bp'))}) "
            f"→ +5분 <b>{fmt_point(thirty.get('plus_5m'))}</b> ({fmt_bp(thirty.get('change_5m_bp'))}) "
            f"→ +30분 <b>{fmt_point(thirty.get('plus_30m'))}</b> ({fmt_bp(thirty.get('change_30m_bp'))})",
            f"• 발표시각 시장 확인: <b>{html.escape(mat)}</b>",
            f"• +5분 시장 확인: <b>{html.escape(m5)}</b>",
            f"• +30분 시장 확인: <b>{html.escape(m30)}</b>",
            f"• {consistency}",
            "• 당시값: Cboe TNX/TYX 1분 데이터 기반. 미 재무부 공식 일일 종가는 별도 검산.",
            "• 같은 시각 다른 뉴스도 금리에 영향을 줄 수 있어 ‘동시간대 반응’으로 표시하며 인과를 단정하지 않음.",
        ]

    lines = text.splitlines()
    # Put the event-time market block immediately after the headline thesis, before detail sections.
    insert_at = min(4, len(lines))
    out = lines[:insert_at] + block + lines[insert_at:]
    ALERT.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

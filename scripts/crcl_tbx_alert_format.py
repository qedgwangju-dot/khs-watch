#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "crcl_usdc_rate_watch_telegram.txt"
PENDING_PATH = ROOT / "out" / "crcl_usdc_rate_watch_pending_state.json"
STATE_PATH = ROOT / "data" / "crcl_usdc_rate_watch_state.json"


def load_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def carry_previous_distinct(new: dict, old: dict, section: str, fields: list[str]) -> None:
    """Persist the prior *source observation*, not the prior hourly watcher snapshot."""
    n = new.get(section) or {}
    o = old.get(section) or {}
    if not n:
        return

    previous = o.get("_previous_distinct")
    if o.get("date") and n.get("date") and o.get("date") != n.get("date"):
        previous = {"date": o.get("date")}
        for field in fields:
            previous[field] = o.get(field)

    if previous:
        n["_previous_distinct"] = previous
        new[section] = n


def signed_bp(value: float) -> str:
    return f"{value:+.1f}bp"


def rewrite_comparisons(text: str, pending: dict, old: dict) -> str:
    circle = pending.get("circle") or {}
    usdxx = pending.get("usdxx") or {}
    sofr = pending.get("sofr") or {}
    treasury = pending.get("treasury") or {}

    # Circle: do not call an unchanged hourly snapshot a +0.0 official comparison.
    circle_prev = circle.get("_previous_distinct") or {}
    if circle_prev.get("circulation_usd_b") is not None:
        old_v = float(circle_prev["circulation_usd_b"])
        new_v = float(circle.get("circulation_usd_b", old_v))
        delta = new_v - old_v
        pct = (delta / old_v * 100.0) if old_v else 0.0
        circle_cmp = (
            f"  직전 공식공개({circle_prev.get('date')}) 대비 {delta:+.1f}십억달러 ({pct:+.2f}%)"
            " · Circle 공식 공개는 0.1십억달러 단위"
        )
    else:
        circle_cmp = (
            f"  새 공식 유통량 업데이트 없음 · 현재 공식 기준일 {circle.get('date', 'N/A')}"
            " · Circle 공식 공개는 0.1십억달러 단위"
        )
    text = re.sub(
        r"^\s*직전 대비 [^\n]+Circle 공식 공개는 0\.1십억달러 단위$",
        circle_cmp,
        text,
        flags=re.M,
    )

    # BlackRock USDXX: compare with the previous distinct official publication when available.
    usdxx_prev = usdxx.get("_previous_distinct") or {}
    if usdxx_prev.get("sec_yield_7d") is not None:
        delta_bp = (float(usdxx.get("sec_yield_7d")) - float(usdxx_prev["sec_yield_7d"])) * 100.0
        usdxx_suffix = f"직전 공식일({usdxx_prev.get('date')}) 대비 {delta_bp:+.1f}bp"
    else:
        usdxx_suffix = "이번 조회 새 공식 수익률 업데이트 없음"
    text = re.sub(
        r"(• <b>Circle Reserve Fund 7일 SEC 수익률</b> [\d.]+% · \d{4}-\d{2}-\d{2}) \| 직전 저장값 대비 [+-][\d.]+bp",
        rf"\1 | {usdxx_suffix}",
        text,
    )

    # SOFR and Treasury already contain their own source-defined previous observation.
    if sofr.get("prev_date") and sofr.get("daily_bp") is not None:
        text = re.sub(
            r"(• <b>SOFR</b> [\d.]+% · \d{4}-\d{2}-\d{2}) \| 직전 저장값 대비 [+-][\d.]+bp",
            rf"\1 | 직전 공식일({sofr['prev_date']}) 대비 {float(sofr['daily_bp']):+.1f}bp",
            text,
        )

    if treasury.get("prev_date"):
        text = re.sub(
            r"(• <b>미 국채 3개월</b> [\d.]+% · \d{4}-\d{2}-\d{2}) \| 직전 저장값 대비 [+-][\d.]+bp",
            rf"\1 | 직전 공식일({treasury['prev_date']}) 대비 {float(treasury.get('daily_3m_bp', 0.0)):+.1f}bp",
            text,
        )
        text = re.sub(
            r"(• <b>미 국채 10년</b> [\d.]+% · \d{4}-\d{2}-\d{2}) \| 직전 저장값 대비 [+-][\d.]+bp",
            rf"\1 | 직전 공식일({treasury['prev_date']}) 대비 {float(treasury.get('daily_10y_bp', 0.0)):+.1f}bp",
            text,
        )

    # Rebuild the investment interpretation from source-to-source deltas.
    short_parts: list[str] = []
    if sofr.get("daily_bp") is not None:
        short_parts.append(f"SOFR {float(sofr['daily_bp']):+.1f}bp")
    if treasury.get("daily_3m_bp") is not None:
        short_parts.append(f"미 국채 3개월 {float(treasury['daily_3m_bp']):+.1f}bp")

    short_negative = any(x < 0 for x in [float(sofr.get("daily_bp", 0.0)), float(treasury.get("daily_3m_bp", 0.0))])
    short_positive = any(x > 0 for x in [float(sofr.get("daily_bp", 0.0)), float(treasury.get("daily_3m_bp", 0.0))])

    if short_negative and not short_positive:
        earnings_view = "소폭 불리 — 단기금리 하락(" + ", ".join(short_parts) + ")으로 준비금 수익률 압력"
    elif short_positive and not short_negative:
        earnings_view = "우호적 — 단기금리 상승(" + ", ".join(short_parts) + ")으로 준비금 수익률에 유리"
    else:
        earnings_view = "혼조 — 단기금리 지표 방향이 엇갈림(" + ", ".join(short_parts) + ")"

    t10bp = float(treasury.get("daily_10y_bp", 0.0))
    if t10bp < 0:
        discount_view = f"우호적 — 미 국채 10년물 {treasury.get('prev_ten_year', 'N/A')}% → {treasury.get('ten_year', 'N/A')}% ({t10bp:+.1f}bp), 할인율 부담 완화"
    elif t10bp > 0:
        discount_view = f"불리 — 미 국채 10년물 {treasury.get('prev_ten_year', 'N/A')}% → {treasury.get('ten_year', 'N/A')}% ({t10bp:+.1f}bp), 할인율 부담 확대"
    else:
        discount_view = "중립 — 미 국채 10년물 전일 대비 변화 없음"

    judgment = (
        "<blockquote><b>판단</b>\n"
        f"실적 축: {earnings_view}\n"
        f"할인율 축: {discount_view}\n"
        "CRCL의 직접 실적 변수는 TBX가 아니라 <b>USDC 유통량 × 단기금리(USDXX·SOFR·3개월 국채)</b>입니다.</blockquote>"
    )
    text = re.sub(r"<blockquote><b>판단</b>.*?</blockquote>", judgment, text, flags=re.S)
    return text


def add_tbx_interpretation(text: str, pending: dict) -> str:
    if "<b>TBX → CRCL 쉽게 해석</b>" in text:
        return text

    crcl = pending.get("crcl") or {}
    tbx = pending.get("tbx") or {}
    crcl_pct = crcl.get("daily_pct")
    tbx_pct = tbx.get("daily_pct")
    if crcl_pct is None or tbx_pct is None:
        return text
    crcl_pct = float(crcl_pct)
    tbx_pct = float(tbx_pct)

    if tbx_pct > 0:
        tbx_line = f"• <b>TBX {tbx_pct:+.2f}% 상승</b> → 7~10년 미 국채 가격 하락 → 중장기 금리 상승"
        base_line = "  → <b>CRCL에는 할인율 부담 확대</b>라 주가 측면에서는 기본적으로 불리"
        if crcl_pct < 0:
            compare_line = f"• <b>CRCL {crcl_pct:+.2f}% 하락</b> → TBX가 가리키는 할인율 부담과 주가 방향이 일치"
        elif crcl_pct > 0:
            compare_line = f"• <b>그런데 CRCL은 {crcl_pct:+.2f}% 상승</b> → 장기금리 부담보다 USDC·실적·개별 촉매가 더 강하게 작용한 것으로 해석"
        else:
            compare_line = "• CRCL 보합 → 장기금리 부담이 주가에 뚜렷하게 반영됐다고 보기 어려움"
    elif tbx_pct < 0:
        tbx_line = f"• <b>TBX {tbx_pct:+.2f}% 하락</b> → 7~10년 미 국채 가격 상승 → 중장기 금리 하락"
        base_line = "  → <b>CRCL에는 할인율 부담 완화</b>라 주가 측면에서는 기본적으로 우호적"
        if crcl_pct > 0:
            compare_line = f"• <b>CRCL도 {crcl_pct:+.2f}% 상승</b> → TBX가 가리키는 할인율 완화와 주가 방향이 일치"
        elif crcl_pct < 0:
            compare_line = f"• <b>그런데 CRCL은 {crcl_pct:+.2f}% 하락</b> → 할인율 호재보다 USDC·단기금리·개별 악재가 더 강하게 작용한 것으로 해석"
        else:
            compare_line = "• CRCL 보합 → 할인율 완화가 주가 상승으로 연결됐다고 보기 어려움"
    else:
        tbx_line = "• <b>TBX 보합</b> → 7~10년 미 국채 가격·중장기 금리 방향 신호가 제한적"
        base_line = "  → CRCL 할인율 측면 영향도 제한적"
        compare_line = f"• CRCL {crcl_pct:+.2f}% → 이날 주가는 TBX보다 다른 요인의 설명력이 더 큼"

    block = "\n".join([
        "<b>TBX → CRCL 쉽게 해석</b>",
        tbx_line,
        base_line,
        compare_line,
        "• ※ <b>TBX는 CRCL 실적의 직접 지표가 아님</b> — 준비금 이익은 USDC 유통량 × 단기금리(USDXX·SOFR·미 국채 3개월)로 별도 판정",
        "",
    ])
    marker = "<blockquote><b>판단</b>"
    if marker in text:
        return text.replace(marker, block + marker, 1)
    return text


def main() -> None:
    if not ALERT_PATH.exists() or not PENDING_PATH.exists():
        return

    text = ALERT_PATH.read_text(encoding="utf-8")
    pending = load_json(PENDING_PATH)
    old = load_json(STATE_PATH)

    carry_previous_distinct(pending, old, "circle", ["circulation_usd_b"])
    carry_previous_distinct(pending, old, "usdxx", ["sec_yield_7d", "fund_size_usd_m", "fund_size_date"])

    text = rewrite_comparisons(text, pending, old)
    text = add_tbx_interpretation(text, pending)

    ALERT_PATH.write_text(text, encoding="utf-8")
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

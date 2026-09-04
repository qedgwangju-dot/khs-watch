#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "crcl_usdc_rate_watch_telegram.txt"
PENDING_PATH = ROOT / "out" / "crcl_usdc_rate_watch_pending_state.json"
STATE_PATH = ROOT / "data" / "crcl_usdc_rate_watch_state.json"
ET = ZoneInfo("America/New_York")


def load_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def carry_previous_distinct(new: dict, old: dict, section: str, fields: list[str]) -> None:
    """Persist the prior source observation, not the prior hourly watcher snapshot."""
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


def watcher_now_et(pending: dict) -> dt.datetime:
    raw = pending.get("updated_at_kst")
    try:
        return dt.datetime.fromisoformat(str(raw)).astimezone(ET)
    except Exception:
        return dt.datetime.now(ET)


def quote_phase(pending: dict, section: str) -> str:
    """Classify a Yahoo daily bar as intraday when the US regular session is still open."""
    q = pending.get(section) or {}
    raw_date = q.get("date")
    if not raw_date:
        return "확인값"
    try:
        qd = dt.date.fromisoformat(str(raw_date))
    except Exception:
        return "확인값"

    now_et = watcher_now_et(pending)
    market_open = dt.time(9, 30)
    market_close = dt.time(16, 0)
    if qd == now_et.date() and now_et.weekday() < 5 and market_open <= now_et.time().replace(tzinfo=None) < market_close:
        return "장중 현재가"
    return "마감값"


def earnings_summary(pending: dict, old: dict) -> tuple[str, str]:
    circle = pending.get("circle") or {}
    usdxx = pending.get("usdxx") or {}
    sofr = pending.get("sofr") or {}
    treasury = pending.get("treasury") or {}
    old_circle = old.get("circle") or {}
    old_usdxx = old.get("usdxx") or {}

    circle_changed = (
        circle.get("date") != old_circle.get("date")
        or circle.get("circulation_usd_b") != old_circle.get("circulation_usd_b")
    )
    usdxx_changed = usdxx.get("date") != old_usdxx.get("date")

    circle_delta = 0.0
    if circle_changed and old_circle.get("circulation_usd_b") is not None and circle.get("circulation_usd_b") is not None:
        circle_delta = float(circle["circulation_usd_b"]) - float(old_circle["circulation_usd_b"])

    usdxx_delta_bp = 0.0
    if usdxx_changed and old_usdxx.get("sec_yield_7d") is not None and usdxx.get("sec_yield_7d") is not None:
        usdxx_delta_bp = (float(usdxx["sec_yield_7d"]) - float(old_usdxx["sec_yield_7d"])) * 100.0

    sofr_bp = float(sofr.get("daily_bp", 0.0) or 0.0)
    t3_bp = float(treasury.get("daily_3m_bp", 0.0) or 0.0)

    # Direct Circle earnings variables get priority. Short-rate proxies are secondary.
    if circle_delta > 0 and usdxx_delta_bp >= 0:
        return "우호적", f"USDC 유통량 증가{f' +{circle_delta:.1f}십억달러' if circle_delta else ''}와 준비금 수익률이 우호적"
    if circle_delta < 0 and usdxx_delta_bp <= 0:
        return "불리", f"USDC 유통량 감소{f' {circle_delta:.1f}십억달러' if circle_delta else ''}와 준비금 수익률이 불리"
    if usdxx_delta_bp > 0:
        return "우호적", f"Circle Reserve Fund 7일 SEC 수익률 상승 {usdxx_delta_bp:+.1f}bp"
    if usdxx_delta_bp < 0:
        return "불리", f"Circle Reserve Fund 7일 SEC 수익률 하락 {usdxx_delta_bp:+.1f}bp"

    if not circle_changed and not usdxx_changed:
        if sofr_bp > 0 and t3_bp > 0:
            return "소폭 우호적", f"USDC·USDXX 새 변화는 없지만 단기금리 프록시 상승(SOFR {sofr_bp:+.1f}bp, 3개월 {t3_bp:+.1f}bp)"
        if sofr_bp < 0 and t3_bp < 0:
            return "소폭 불리", f"USDC·USDXX 새 변화는 없지만 단기금리 프록시 하락(SOFR {sofr_bp:+.1f}bp, 3개월 {t3_bp:+.1f}bp)"
        return "거의 중립", "USDC 유통량·Circle Reserve Fund 수익률 새 변화 없음"

    return "혼조", f"직접 실적 변수와 단기금리 방향이 엇갈림(SOFR {sofr_bp:+.1f}bp, 3개월 {t3_bp:+.1f}bp)"


def current_discount_summary(pending: dict) -> tuple[str, str, str]:
    treasury = pending.get("treasury") or {}
    tbx = pending.get("tbx") or {}
    tbx_pct = tbx.get("daily_pct")
    phase = quote_phase(pending, "tbx")

    # During the US session, TBX is the fresher directional proxy than yesterday's Treasury official curve.
    if phase == "장중 현재가" and tbx_pct is not None:
        p = float(tbx_pct)
        if p > 0:
            return "불리", "오늘 장중", f"TBX {p:+.2f}% 상승 → 7~10년 국채가격 하락 → 중장기 금리 상승 방향"
        if p < 0:
            return "우호적", "오늘 장중", f"TBX {p:+.2f}% 하락 → 7~10년 국채가격 상승 → 중장기 금리 하락 방향"
        return "중립", "오늘 장중", "TBX 보합 → 중장기 금리 방향 신호 제한"

    t10bp = float(treasury.get("daily_10y_bp", 0.0) or 0.0)
    if t10bp > 0:
        return "불리", "최근 공식 마감", f"미 국채 10년 {treasury.get('prev_ten_year', 'N/A')}% → {treasury.get('ten_year', 'N/A')}% ({t10bp:+.1f}bp)"
    if t10bp < 0:
        return "우호적", "최근 공식 마감", f"미 국채 10년 {treasury.get('prev_ten_year', 'N/A')}% → {treasury.get('ten_year', 'N/A')}% ({t10bp:+.1f}bp)"
    return "중립", "최근 공식 마감", "미 국채 10년 전일 대비 변화 없음"


def overall_verdict(earnings: str, discount: str) -> str:
    e_good = "우호적" in earnings and "불리" not in earnings
    e_bad = "불리" in earnings
    d_good = discount == "우호적"
    d_bad = discount == "불리"

    if d_bad and not e_good:
        return "단기 불리"
    if d_good and not e_bad:
        return "단기 우호적"
    if e_bad and d_bad:
        return "불리"
    if e_good and d_good:
        return "우호적"
    return "혼조"


def one_line_take(earnings: str, discount: str, discount_when: str, pending: dict) -> str:
    crcl = pending.get("crcl") or {}
    crcl_pct = crcl.get("daily_pct")
    stock_phase = quote_phase(pending, "crcl")

    if "중립" in earnings and discount == "불리":
        base = f"본업은 거의 그대로인데 {discount_when} 금리 방향이 올라 CRCL 주가에는 불리"
    elif "중립" in earnings and discount == "우호적":
        base = f"본업은 거의 그대로지만 {discount_when} 금리 하락이 CRCL 할인율에는 우호적"
    elif "우호적" in earnings and discount == "불리":
        base = "본업 개선과 할인율 부담이 충돌하는 구간"
    elif "불리" in earnings and discount == "우호적":
        base = "본업 악화와 할인율 완화가 충돌하는 구간"
    elif "우호적" in earnings and discount == "우호적":
        base = "본업과 할인율이 동시에 CRCL에 우호적"
    elif "불리" in earnings and discount == "불리":
        base = "본업과 할인율이 동시에 CRCL에 불리"
    else:
        base = "본업과 금리 신호가 엇갈려 방향 확인이 필요"

    if crcl_pct is not None:
        base += f" · CRCL {float(crcl_pct):+.2f}% {stock_phase}"
    return base


def add_current_verdict(text: str, pending: dict, old: dict) -> str:
    if "<b>현재 결론</b>" in text:
        return text

    earnings, earnings_reason = earnings_summary(pending, old)
    discount, discount_when, discount_reason = current_discount_summary(pending)
    verdict = overall_verdict(earnings, discount)

    crcl = pending.get("crcl") or {}
    crcl_pct = crcl.get("daily_pct")
    stock_phase = quote_phase(pending, "crcl")
    stock_line = "확인 불가"
    if crcl_pct is not None:
        p = float(crcl_pct)
        direction = "상승" if p > 0 else "하락" if p < 0 else "보합"
        stock_line = f"CRCL {p:+.2f}% {stock_phase} · {direction}"

    take = one_line_take(earnings, discount, discount_when, pending)
    block = "\n".join([
        f"<blockquote><b>현재 결론</b> · <b>{html.escape(verdict)}</b>",
        f"• <b>돈 버는 능력 → {html.escape(earnings)}</b> · {html.escape(earnings_reason)}",
        f"• <b>할인율 → {html.escape(discount)}</b> · {html.escape(discount_when)} · {html.escape(discount_reason)}",
        f"• <b>주가 → {html.escape(stock_line)}</b>",
        f"• <b>한마디로</b> {html.escape(take)}</blockquote>",
        "",
    ])

    marker = "<b>핵심 변화</b>"
    if marker in text:
        return text.replace(marker, block + marker, 1)
    return block + text


def rewrite_market_labels(text: str, pending: dict) -> str:
    crcl = pending.get("crcl") or {}
    tbx = pending.get("tbx") or {}
    crcl_phase = quote_phase(pending, "crcl")
    tbx_phase = quote_phase(pending, "tbx")

    if crcl_phase == "장중 현재가":
        text = re.sub(r"CRCL 새 종가:", "CRCL 장중 현재가:", text)
    elif crcl_phase == "마감값":
        text = re.sub(r"CRCL 새 종가:", "CRCL 새 마감값:", text)

    if crcl.get("date"):
        text = re.sub(
            r"(• <b>CRCL</b> \$[\d.]+ · \d{4}-\d{2}-\d{2}) \| 일간 ([+-][\d.]+%)",
            rf"\1 | {crcl_phase} \2",
            text,
        )
    if tbx.get("date"):
        text = re.sub(
            r"(• <b>TBX</b> \$[\d.]+ · \d{4}-\d{2}-\d{2}) \| 일간 ([+-][\d.]+%)",
            rf"\1 | {tbx_phase} \2",
            text,
        )
    return text


def rewrite_comparisons(text: str, pending: dict, old: dict) -> str:
    circle = pending.get("circle") or {}
    usdxx = pending.get("usdxx") or {}
    sofr = pending.get("sofr") or {}
    treasury = pending.get("treasury") or {}

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

    earnings, earnings_reason = earnings_summary(pending, old)
    discount, discount_when, discount_reason = current_discount_summary(pending)
    verdict = overall_verdict(earnings, discount)

    treasury_official = ""
    if treasury.get("date") and treasury.get("daily_10y_bp") is not None:
        t10bp = float(treasury.get("daily_10y_bp", 0.0))
        official_view = "우호적" if t10bp < 0 else "불리" if t10bp > 0 else "중립"
        treasury_official = (
            f"최근 공식 마감({treasury.get('date')}): {official_view} — "
            f"10년물 {treasury.get('prev_ten_year', 'N/A')}% → {treasury.get('ten_year', 'N/A')}% ({t10bp:+.1f}bp)"
        )

    tbx = pending.get("tbx") or {}
    market_line = ""
    if quote_phase(pending, "tbx") == "장중 현재가" and tbx.get("daily_pct") is not None:
        p = float(tbx["daily_pct"])
        intraday_view = "불리" if p > 0 else "우호적" if p < 0 else "중립"
        market_line = f"오늘 장중: {intraday_view} — TBX {p:+.2f}%"

    judgment_lines = [
        "<blockquote><b>판단</b>",
        f"<b>현재 판정: {html.escape(verdict)}</b>",
        f"실적 축: {html.escape(earnings)} — {html.escape(earnings_reason)}",
    ]
    if treasury_official:
        judgment_lines.append(html.escape(treasury_official))
    if market_line:
        judgment_lines.append(html.escape(market_line))
    judgment_lines += [
        f"현재 할인율 축: {html.escape(discount)} — {html.escape(discount_when)} · {html.escape(discount_reason)}",
        f"<b>한마디로:</b> {html.escape(one_line_take(earnings, discount, discount_when, pending))}",
        "CRCL 직접 실적 변수는 TBX가 아니라 <b>USDC 유통량 × 단기금리(USDXX·SOFR·3개월 국채)</b>입니다.</blockquote>",
    ]
    judgment = "\n".join(judgment_lines)
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
    tbx_phase = quote_phase(pending, "tbx")
    crcl_phase = quote_phase(pending, "crcl")

    if tbx_pct > 0:
        tbx_line = f"• <b>TBX {tbx_pct:+.2f}% 상승</b> ({tbx_phase}) → 7~10년 미 국채 가격 하락 → 중장기 금리 상승"
        base_line = "  → <b>CRCL에는 할인율 부담 확대</b>라 주가 측면에서는 기본적으로 불리"
        if crcl_pct < 0:
            compare_line = f"• <b>CRCL {crcl_pct:+.2f}% 하락</b> ({crcl_phase}) → 오늘 할인율 부담과 주가 방향이 일치"
        elif crcl_pct > 0:
            compare_line = f"• <b>그런데 CRCL은 {crcl_pct:+.2f}% 상승</b> ({crcl_phase}) → 금리 부담보다 USDC·실적·개별 촉매가 더 강한 것으로 해석"
        else:
            compare_line = "• CRCL 보합 → 금리 부담이 주가에 뚜렷하게 반영됐다고 보기 어려움"
    elif tbx_pct < 0:
        tbx_line = f"• <b>TBX {tbx_pct:+.2f}% 하락</b> ({tbx_phase}) → 7~10년 미 국채 가격 상승 → 중장기 금리 하락"
        base_line = "  → <b>CRCL에는 할인율 부담 완화</b>라 주가 측면에서는 기본적으로 우호적"
        if crcl_pct > 0:
            compare_line = f"• <b>CRCL도 {crcl_pct:+.2f}% 상승</b> ({crcl_phase}) → 오늘 할인율 완화와 CRCL 주가 방향이 일치"
        elif crcl_pct < 0:
            compare_line = f"• <b>그런데 CRCL은 {crcl_pct:+.2f}% 하락</b> ({crcl_phase}) → 할인율 호재보다 USDC·단기금리·개별 악재가 더 강한 것으로 해석"
        else:
            compare_line = "• CRCL 보합 → 할인율 완화가 주가 상승으로 연결됐다고 보기 어려움"
    else:
        tbx_line = f"• <b>TBX 보합</b> ({tbx_phase}) → 7~10년 미 국채 가격·중장기 금리 방향 신호가 제한적"
        base_line = "  → CRCL 할인율 측면 영향도 제한적"
        compare_line = f"• CRCL {crcl_pct:+.2f}% ({crcl_phase}) → 이날 주가는 TBX보다 다른 요인의 설명력이 더 큼"

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

    text = rewrite_market_labels(text, pending)
    text = rewrite_comparisons(text, pending, old)
    text = add_tbx_interpretation(text, pending)
    text = add_current_verdict(text, pending, old)

    ALERT_PATH.write_text(text, encoding="utf-8")
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

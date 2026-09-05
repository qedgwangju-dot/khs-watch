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
ET = ZoneInfo("America/New_York")


def load_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fbp(v: float) -> str:
    return f"{v:+.1f}bp"


def quote_phase(pending: dict, section: str) -> str:
    q = pending.get(section) or {}
    raw_date = q.get("date")
    raw_now = pending.get("updated_at_kst")
    if not raw_date or not raw_now:
        return "확인값"
    try:
        qd = dt.date.fromisoformat(str(raw_date))
        now_et = dt.datetime.fromisoformat(str(raw_now)).astimezone(ET)
    except Exception:
        return "확인값"
    if qd == now_et.date() and now_et.weekday() < 5 and dt.time(9, 30) <= now_et.time().replace(tzinfo=None) < dt.time(16, 0):
        return "장중 현재가"
    return "마감값"


def direct_earnings(pending: dict) -> tuple[str, str, int]:
    circle = pending.get("circle") or {}
    usdxx = pending.get("usdxx") or {}
    cp = circle.get("_previous_distinct") or {}
    up = usdxx.get("_previous_distinct") or {}

    c_now = circle.get("circulation_usd_b")
    c_prev = cp.get("circulation_usd_b")
    y_now = usdxx.get("sec_yield_7d")
    y_prev = up.get("sec_yield_7d")

    c_delta = None if c_now is None or c_prev is None else float(c_now) - float(c_prev)
    y_bp = None if y_now is None or y_prev is None else (float(y_now) - float(y_prev)) * 100.0

    parts: list[str] = []
    score = 0
    if c_delta is None:
        parts.append(f"USDC {float(c_now):.1f}십억달러" if c_now is not None else "USDC 확인 불가")
    elif abs(c_delta) < 0.05:
        parts.append(f"USDC {float(c_now):.1f}십억달러 · 변화 없음")
    else:
        parts.append(f"USDC {float(c_prev):.1f}→{float(c_now):.1f}십억달러 ({c_delta:+.1f})")
        score += 1 if c_delta > 0 else -1

    if y_bp is None:
        parts.append(f"준비금 수익률 {float(y_now):.2f}%" if y_now is not None else "준비금 수익률 확인 불가")
    else:
        parts.append(f"준비금 수익률 {float(y_prev):.2f}%→{float(y_now):.2f}% ({fbp(y_bp)})")
        if y_bp >= 1.0:
            score += 1
        elif y_bp <= -1.0:
            score -= 1

    if score >= 2:
        label = "우호적"
    elif score == 1:
        label = "소폭 우호적"
    elif score == 0:
        label = "거의 중립"
    elif score == -1:
        label = "소폭 불리"
    else:
        label = "불리"
    return label, " · ".join(parts), score


def proxy_rates(pending: dict) -> tuple[str, str, int]:
    sofr = pending.get("sofr") or {}
    treasury = pending.get("treasury") or {}
    s = float(sofr.get("daily_bp", 0.0) or 0.0)
    t3 = float(treasury.get("daily_3m_bp", 0.0) or 0.0)
    text = f"SOFR {fbp(s)} · 미 국채 3개월 {fbp(t3)}"
    if s > 0 and t3 > 0:
        return "소폭 우호적", text + " → 향후 준비금 수익률 하락을 일부 완충할 수 있는 방향", 1
    if s < 0 and t3 < 0:
        return "소폭 불리", text + " → 향후 준비금 수익률에는 하방 압력 방향", -1
    return "중립·혼조", text + " → 선행 단기금리 방향이 엇갈림", 0


def discount_view(pending: dict) -> tuple[str, str, int]:
    treasury = pending.get("treasury") or {}
    t10 = float(treasury.get("daily_10y_bp", 0.0) or 0.0)
    prev = treasury.get("prev_ten_year")
    now = treasury.get("ten_year")
    base = f"미 국채 10년 {prev}%→{now}% ({fbp(t10)})"
    if t10 > 0:
        label = "불리" if abs(t10) >= 3 else "소폭 불리"
        return label, base + " → 주식 할인율 부담 확대", -1
    if t10 < 0:
        label = "우호적" if abs(t10) >= 3 else "소폭 우호적"
        return label, base + " → 주식 할인율 부담 완화", 1
    return "중립", base + " → 할인율 영향 제한", 0


def verdict_label(direct_score: int, proxy_score: int, discount_score: int) -> str:
    # Direct reserve economics and equity discount rate dominate; proxy rates are secondary.
    total = direct_score * 1.5 + proxy_score * 0.5 + discount_score
    if total >= 2.0:
        return "우호적"
    if total >= 0.75:
        return "소폭 우호적"
    if total <= -2.0:
        return "불리"
    if total <= -0.75:
        return "소폭 불리"
    return "중립·혼조"


def build_summary(pending: dict) -> tuple[str, str]:
    direct_label, direct_text, direct_score = direct_earnings(pending)
    proxy_label, proxy_text, proxy_score = proxy_rates(pending)
    disc_label, disc_text, disc_score = discount_view(pending)
    verdict = verdict_label(direct_score, proxy_score, disc_score)

    crcl = pending.get("crcl") or {}
    p = crcl.get("daily_pct")
    phase = quote_phase(pending, "crcl")
    if p is None:
        stock = "CRCL 주가 확인 불가"
        stock_take = "주가 확인 불가"
    else:
        p = float(p)
        direction = "하락" if p < 0 else "상승" if p > 0 else "보합"
        stock = f"CRCL {p:+.2f}% {phase} · {direction}"
        if verdict in {"불리", "소폭 불리"} and p < 0:
            stock_take = "현재 펀더멘털·할인율 판정과 주가 방향이 일치하지만, 금리만이 하락 원인이라고 단정하지 않음"
        elif verdict in {"우호적", "소폭 우호적"} and p > 0:
            stock_take = "현재 펀더멘털·할인율 판정과 주가 방향이 일치하지만, 금리만이 상승 원인이라고 단정하지 않음"
        else:
            stock_take = "주가와 펀더멘털·할인율 신호가 엇갈려 다른 개별 요인의 영향도 확인 필요"

    if direct_score < 0 and discount_score < 0:
        take = "실제 이익 변수와 할인율이 모두 약하게 악화. 단기금리 선행지표 반등이 일부 완충하지만 현재는 악재가 조금 우세"
    elif direct_score > 0 and discount_score > 0:
        take = "실제 이익 변수와 할인율이 함께 개선돼 현재는 호재가 우세"
    elif direct_score < 0 and proxy_score > 0:
        take = "현재 준비금 수익률은 약해졌지만 단기금리 선행지표는 반등. 아직 실적 개선으로 확인된 것은 아니며 할인율까지 보면 방향은 보수적으로 판단"
    elif direct_score > 0 and discount_score < 0:
        take = "본업 개선은 맞지만 장기금리 상승이 밸류에이션을 누르는 구간"
    elif direct_score == 0 and discount_score < 0:
        take = "본업 변화는 제한적인데 장기금리가 올라 주가에는 소폭 불리"
    else:
        take = f"직접 실적은 {direct_label}, 선행 단기금리는 {proxy_label}, 할인율은 {disc_label} → 종합 {verdict}"

    top = "\n".join([
        f"<blockquote><b>현재 결론 · {html.escape(verdict)}</b>",
        f"• <b>실제 돈 버는 능력 → {html.escape(direct_label)}</b> · {html.escape(direct_text)}",
        f"• <b>앞으로의 단기금리 방향 → {html.escape(proxy_label)}</b> · {html.escape(proxy_text)}",
        f"• <b>주가 할인율 → {html.escape(disc_label)}</b> · {html.escape(disc_text)}",
        f"• <b>주가 확인 → {html.escape(stock)}</b> · {html.escape(stock_take)}",
        f"• <b>한마디로</b> · {html.escape(take)}</blockquote>",
        "",
        "<b>SOFR 방향 읽는 법 — 고정</b>",
        "• <b>SOFR 상승</b> → 단기 달러금리 상승 → Circle 준비금 수익률도 올라갈 가능성 → <b>Circle 이자수익에 유리</b>",
        "• <b>SOFR 하락</b> → 단기 달러금리 하락 → Circle 준비금 수익률도 내려갈 가능성 → <b>Circle 이자수익에 불리</b>",
        "• ※ SOFR은 <b>선행·보조지표</b>입니다. 실제 실적 판정은 <b>USDC 유통량 × 실제 준비금 수익률</b>을 우선합니다.",
        "",
    ])

    judgment = "\n".join([
        "<blockquote><b>판단</b>",
        f"<b>{html.escape(verdict)}</b> — {html.escape(take)}",
        "실제 실적은 <b>USDC 유통량 × 실제 준비금 수익률</b>을 우선하고, SOFR·3개월 국채는 다음 준비금 수익률 방향을 보는 보조지표로 구분합니다.",
        "TBX·10년물은 실적이 아니라 <b>CRCL 주가 할인율</b>을 보는 지표입니다.</blockquote>",
    ])
    return top, judgment


def main() -> None:
    if not ALERT_PATH.exists() or not PENDING_PATH.exists():
        return
    text = ALERT_PATH.read_text(encoding="utf-8")
    pending = load_json(PENDING_PATH)
    if not pending:
        return

    top, judgment = build_summary(pending)
    text = re.sub(r"<blockquote><b>현재 결론</b>.*?</blockquote>\n*", top, text, count=1, flags=re.S)
    text = re.sub(r"<blockquote><b>현재 결론 · .*?</blockquote>\n*", top, text, count=1, flags=re.S)
    text = re.sub(r"<blockquote><b>판단</b>.*?</blockquote>", judgment, text, count=1, flags=re.S)
    ALERT_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

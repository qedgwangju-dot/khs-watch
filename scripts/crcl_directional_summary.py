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
    usdxx_failed = any(str(x).startswith("usdxx:") for x in (pending.get("errors") or []))

    c_now = circle.get("circulation_usd_b")
    c_prev = cp.get("circulation_usd_b")
    y_now = usdxx.get("sec_yield_7d")
    y_prev = up.get("sec_yield_7d")

    parts: list[str] = []
    if c_now is not None:
        if c_prev is not None:
            c_delta = float(c_now) - float(c_prev)
            parts.append(f"USDC {float(c_prev):.1f}→{float(c_now):.1f}십억달러 ({c_delta:+.1f})")
        else:
            parts.append(f"USDC {float(c_now):.1f}십억달러")
    else:
        parts.append("USDC 확인 불가")

    if y_now is not None:
        if y_prev is not None:
            y_bp = (float(y_now) - float(y_prev)) * 100.0
            parts.append(f"준비금 수익률 {float(y_prev):.2f}%→{float(y_now):.2f}% ({fbp(y_bp)})")
        else:
            parts.append(f"준비금 수익률 {float(y_now):.2f}%")
    else:
        parts.append("준비금 수익률 확인 불가")

    if usdxx_failed:
        parts.append("BlackRock 공식 원문 재조회 실패 · 직전 성공값 사용")
        return "판정 보류", " · ".join(parts), 0

    # Primary earnings test: USDC circulation × actual Circle Reserve Fund 7-day SEC yield.
    # This follows the direct reserve-economics hierarchy instead of scoring volume and yield separately.
    if None not in (c_now, c_prev, y_now, y_prev):
        now_proxy = float(c_now) * float(y_now)
        prev_proxy = float(c_prev) * float(y_prev)
        proxy_pct = (now_proxy / prev_proxy - 1.0) * 100.0 if prev_proxy else 0.0
        parts.append(f"USDC×실제 수익률 프록시 {proxy_pct:+.2f}%")
        if proxy_pct >= 1.0:
            return "우호적", " · ".join(parts), 2
        if proxy_pct >= 0.25:
            return "소폭 우호적", " · ".join(parts), 1
        if proxy_pct <= -1.0:
            return "불리", " · ".join(parts), -2
        if proxy_pct <= -0.25:
            return "소폭 불리", " · ".join(parts), -1
        return "거의 중립", " · ".join(parts), 0

    # If one prior official leg is unavailable, do not fabricate a combined earnings delta.
    return "판정 보류", " · ".join(parts) + " · 직전 공식 조합 부족", 0


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
    crcl = pending.get("crcl") or {}
    tbx = pending.get("tbx") or {}

    treasury_date = str(treasury.get("date") or "")
    crcl_date = str(crcl.get("date") or "")
    tbx_date = str(tbx.get("date") or "")

    if (
        treasury_date
        and crcl_date
        and tbx_date
        and treasury_date < crcl_date
        and tbx_date == crcl_date
        and tbx.get("daily_pct") is not None
    ):
        p = float(tbx.get("daily_pct") or 0.0)
        phase = quote_phase(pending, "tbx")
        latest_official = (
            f"최신 공식 10년 {float(treasury.get('ten_year', 0.0)):.2f}%"
            f" · {treasury_date}"
        )
        if p > 0:
            return (
                "불리",
                f"TBX {p:+.2f}% {phase} → 7~10년 국채 가격 하락·금리 상승 신호"
                f" · {latest_official}",
                -1,
            )
        if p < 0:
            return (
                "우호적",
                f"TBX {p:+.2f}% {phase} → 7~10년 국채 가격 상승·금리 하락 신호"
                f" · {latest_official}",
                1,
            )
        return "중립", f"TBX 보합 {phase} · {latest_official}", 0

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
        if disc_score < 0 and p < 0:
            stock_take = "주가 하락은 할인율 부담과 같은 방향 · 다만 본업·단기금리까지 같은 방향이라고 단정하지 않음"
        elif disc_score > 0 and p > 0:
            stock_take = "주가 상승은 할인율 완화와 같은 방향 · 다만 본업·단기금리까지 같은 방향이라고 단정하지 않음"
        elif disc_score < 0 and p > 0:
            stock_take = "할인율은 불리하지만 주가는 상승 → 다른 본업·개별 촉매의 영향 확인 필요"
        elif disc_score > 0 and p < 0:
            stock_take = "할인율은 우호적이지만 주가는 하락 → 다른 본업·개별 악재의 영향 확인 필요"
        elif verdict in {"불리", "소폭 불리"} and p < 0:
            stock_take = "종합 판정과 주가 하락 방향이 일치하지만 단일 요인으로 원인을 단정하지 않음"
        elif verdict in {"우호적", "소폭 우호적"} and p > 0:
            stock_take = "종합 판정과 주가 상승 방향이 일치하지만 단일 요인으로 원인을 단정하지 않음"
        else:
            stock_take = "주가와 본업·단기금리·할인율 신호가 혼재 → 개별 요인 확인 필요"

    if direct_score < 0 and disc_score < 0:
        take = "실제 이익 변수와 할인율이 모두 약하게 악화. 단기금리 선행지표 반등이 일부 완충하지만 현재는 악재가 조금 우세"
    elif direct_score > 0 and disc_score > 0:
        take = "실제 이익 변수와 할인율이 함께 개선돼 현재는 호재가 우세"
    elif direct_score < 0 and proxy_score > 0:
        take = "현재 준비금 수익률은 약해졌지만 단기금리 선행지표는 반등. 아직 실적 개선으로 확인된 것은 아니며 할인율까지 보면 방향은 보수적으로 판단"
    elif direct_score > 0 and disc_score < 0:
        take = "본업 개선은 맞지만 장기금리 상승이 밸류에이션을 누르는 구간"
    elif direct_score == 0 and disc_score < 0:
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


def _fmt_krw_from_usd_m(value_usd_m: float, rate: float) -> str:
    eok = value_usd_m * rate / 100.0
    sign = "-" if eok < 0 else "+" if eok > 0 else ""
    rounded = int(round(abs(eok)))
    jo, rem = divmod(rounded, 10000)
    if jo:
        body = f"{jo:,}조{rem:,}억원" if rem else f"{jo:,}조원"
    else:
        body = f"{rounded:,}억원"
    return f"약 {sign}{body}"


def _extract_changes(text: str) -> list[str]:
    m = re.search(
        r"<b>핵심 변화</b>\s*(.*?)(?=\n\s*<b>돈 버는 능력|\n\s*<b>할인율|\n\s*<blockquote|\Z)",
        text,
        flags=re.S,
    )
    if not m:
        return []
    changes = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("• "):
            changes.append(line)
    return changes[:4]


def _source_href(text: str, label_fragment: str) -> str | None:
    for line in text.splitlines():
        if label_fragment not in line:
            continue
        m = re.search(r'href="([^"]+)"', line)
        if m:
            return m.group(1)
    return None


def _direct_proxy_pct(pending: dict) -> float | None:
    circle = pending.get("circle") or {}
    usdxx = pending.get("usdxx") or {}
    cp = circle.get("_previous_distinct") or {}
    up = usdxx.get("_previous_distinct") or {}
    vals = (
        circle.get("circulation_usd_b"),
        cp.get("circulation_usd_b"),
        usdxx.get("sec_yield_7d"),
        up.get("sec_yield_7d"),
    )
    if any(v is None for v in vals):
        return None
    c_now, c_prev, y_now, y_prev = map(float, vals)
    prev_proxy = c_prev * y_prev
    if not prev_proxy:
        return None
    return (c_now * y_now / prev_proxy - 1.0) * 100.0


def build_compact_alert(pending: dict, original_text: str) -> str:
    direct_label, _, direct_score = direct_earnings(pending)
    proxy_label, _, proxy_score = proxy_rates(pending)
    disc_label, disc_text, disc_score = discount_view(pending)
    verdict = verdict_label(direct_score, proxy_score, disc_score)

    if direct_score > 0 and disc_score < 0:
        take = "본업 개선은 맞지만 장기금리 상승이 밸류에이션을 누르는 구간"
    elif direct_score > 0 and disc_score > 0:
        take = "본업과 할인율이 함께 개선돼 현재는 우호 신호가 우세"
    elif direct_score < 0 and disc_score < 0:
        take = "본업과 할인율이 함께 악화돼 현재는 부담이 우세"
    elif direct_score < 0 and proxy_score > 0:
        take = "현재 본업은 약하지만 단기금리 선행지표는 개선 중"
    else:
        take = f"본업 {direct_label} · 단기금리 {proxy_label} · 할인율 {disc_label}"

    updated = str(pending.get("updated_at_kst") or "")
    lines = [
        "<b>CRCL · USDC 변화</b>",
        f"<code>조회 {html.escape(updated)}</code>" if updated else "",
        "",
        f"<blockquote><b>판정 · {html.escape(verdict)}</b>\n{html.escape(take)}</blockquote>",
    ]

    changes = _extract_changes(original_text)
    if changes:
        lines += ["", "<b>이번 변화</b>", *changes]

    circle = pending.get("circle") or {}
    usdxx = pending.get("usdxx") or {}
    sofr = pending.get("sofr") or {}
    treasury = pending.get("treasury") or {}
    crcl = pending.get("crcl") or {}
    fx = pending.get("fx") or {}
    fx_rate = float(fx.get("rate", 0.0) or 0.0)

    cp = circle.get("_previous_distinct") or {}
    up = usdxx.get("_previous_distinct") or {}

    lines += ["", "<b>핵심 숫자</b>"]

    c_now = circle.get("circulation_usd_b")
    c_prev = cp.get("circulation_usd_b")
    y_now = usdxx.get("sec_yield_7d")
    y_prev = up.get("sec_yield_7d")
    if c_now is not None:
        c_now_f = float(c_now)
        if c_prev is not None:
            c_prev_f = float(c_prev)
            c_pct = ((c_now_f / c_prev_f) - 1.0) * 100 if c_prev_f else 0.0
            usdc_text = f"USDC {c_prev_f:.1f}→{c_now_f:.1f}십억달러 ({c_pct:+.2f}%)"
        else:
            usdc_text = f"USDC {c_now_f:.1f}십억달러"
        if fx_rate:
            usdc_text += f" · {_fmt_krw_from_usd_m(c_now_f * 1000.0, fx_rate)}"

        reserve_text = ""
        if y_now is not None:
            if y_prev is not None:
                y_bp = (float(y_now) - float(y_prev)) * 100.0
                reserve_text = f" | 준비금 {float(y_prev):.2f}→{float(y_now):.2f}% ({y_bp:+.1f}bp)"
            else:
                reserve_text = f" | 준비금 {float(y_now):.2f}%"

        proxy_pct = _direct_proxy_pct(pending)
        proxy_text = f" | 이익 프록시 {proxy_pct:+.2f}%" if proxy_pct is not None else ""
        lines.append(f"• <b>본업</b> · {html.escape(usdc_text + reserve_text + proxy_text)}")

    if sofr or treasury:
        s_text = (
            f"SOFR {float(sofr.get('rate', 0.0)):.2f}% ({float(sofr.get('daily_bp', 0.0)):+.1f}bp)"
            if sofr else "SOFR 확인 불가"
        )
        t3_text = (
            f"3M {float(treasury.get('three_month', 0.0)):.2f}% ({float(treasury.get('daily_3m_bp', 0.0)):+.1f}bp)"
            if treasury else "3M 확인 불가"
        )
        lines.append(f"• <b>단기금리</b> · {html.escape(s_text)} | {html.escape(t3_text)}")

    if treasury:
        treasury_date = str(treasury.get("date") or "")
        crcl_date = str(crcl.get("date") or "")
        if treasury_date and crcl_date and treasury_date < crcl_date and "TBX" in disc_text:
            lines.append(f"• <b>할인율</b> · {html.escape(disc_text)}")
        else:
            lines.append(
                f"• <b>할인율</b> · 10Y {float(treasury.get('ten_year', 0.0)):.2f}%"
                f" ({float(treasury.get('daily_10y_bp', 0.0)):+.1f}bp)"
            )

    if crcl and crcl.get("close") is not None:
        phase = quote_phase(pending, "crcl")
        lines.append(
            f"• <b>CRCL</b> · ${float(crcl.get('close')):.2f}"
            f" · {float(crcl.get('daily_pct', 0.0)):+.2f}% {html.escape(phase)}"
        )

    if fx_rate:
        lines += [
            "",
            f"• 환율 · 1달러={fx_rate:,.2f}원 · {html.escape(str(fx.get('date') or ''))}"
            f" · {html.escape(str(fx.get('source') or ''))}",
        ]

    links = []
    for frag, label in (
        ("Circle USDC", "Circle"),
        ("Circle Reserve Fund", "BlackRock"),
        ("SOFR", "NY Fed"),
        ("미 국채 금리", "미 재무부"),
        ("Circle 2Q26 10-Q", "SEC"),
    ):
        href = _source_href(original_text, frag)
        if href:
            links.append(f'<a href="{href}">{label}</a>')
    if links:
        lines.append("<b>원문</b> · " + " · ".join(links))

    compact: list[str] = []
    for line in lines:
        if not line and compact and compact[-1] == "":
            continue
        compact.append(line)
    return "\n".join(compact).strip() + "\n"


def main() -> None:
    if not ALERT_PATH.exists() or not PENDING_PATH.exists():
        return
    original_text = ALERT_PATH.read_text(encoding="utf-8")
    pending = load_json(PENDING_PATH)
    if not pending:
        return
    ALERT_PATH.write_text(build_compact_alert(pending, original_text), encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reformat GDPNow Telegram HTML around the actual investment question: rate direction."""
from __future__ import annotations

import pathlib
import re

from gdpnow_long_rates_watch import fetch_contrib_rows

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / "out" / "gdpnow_long_rates_alert.html"


def take(lines: list[str], prefix: str) -> str | None:
    return next((x for x in lines if x.startswith(prefix)), None)


def clean_bullet(line: str) -> str:
    return re.sub(r"^•\s*", "", line).strip()


def section(lines: list[str], heading: str, next_headings: tuple[str, ...]) -> list[str]:
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return []
    end = len(lines)
    for h in next_headings:
        try:
            idx = lines.index(h, start)
            end = min(end, idx)
        except ValueError:
            pass
    return [x for x in lines[start:end] if x.strip()]


def private_final_contribution(row) -> float | None:
    values = [row.pce, row.equipment, row.ipp, row.nonres, row.residential]
    if any(v is None for v in values):
        return None
    return float(sum(values))


def rate_signal(latest, prev) -> tuple[str, str, list[str]]:
    """Return label, one-line thesis, and reasons.

    Weight private domestic final demand most heavily because headline GDP can be
    distorted by inventories and net exports. This is an analytical rate-pressure
    signal, not a claim that Treasury yields must move one-for-one.
    """
    if prev is None:
        return (
            "⚪ 금리 영향 판단 유보",
            "직전 GDPNow 구성 비교가 없어 방향 판정을 보류합니다.",
            ["첫 관측치는 기준점으로 저장하고 다음 업데이트부터 방향을 판정합니다."],
        )

    gdp_d = latest.gdp - prev.gdp
    inv_d = latest.cipi - prev.cipi
    final_d = (latest.gdp - latest.cipi) - (prev.gdp - prev.cipi)
    latest_private = private_final_contribution(latest)
    prev_private = private_final_contribution(prev)
    private_d = (latest_private - prev_private) if latest_private is not None and prev_private is not None else None
    net_d = (latest.net_exports - prev.net_exports) if latest.net_exports is not None and prev.net_exports is not None else None

    score = 0
    reasons: list[str] = []

    # Core: private domestic demand (PCE + private fixed investment).
    if private_d is not None:
        if private_d >= 0.50:
            score += 4
            reasons.append(f"민간소비+고정투자 기여도가 직전보다 {private_d:+.2f}%p 크게 강화")
        elif private_d >= 0.20:
            score += 3
            reasons.append(f"민간소비+고정투자 기여도가 직전보다 {private_d:+.2f}%p 강화")
        elif private_d <= -0.50:
            score -= 4
            reasons.append(f"민간소비+고정투자 기여도가 직전보다 {private_d:+.2f}%p 크게 약화")
        elif private_d <= -0.20:
            score -= 3
            reasons.append(f"민간소비+고정투자 기여도가 직전보다 {private_d:+.2f}%p 약화")
        else:
            reasons.append(f"민간소비+고정투자 변화는 {private_d:+.2f}%p로 제한적")

    # Headline GDP is supportive but deliberately lower weight.
    if gdp_d >= 0.30:
        score += 1
        reasons.append(f"GDPNow가 {prev.gdp:.2f}% → {latest.gdp:.2f}%로 상향")
    elif gdp_d <= -0.30:
        score -= 1
        reasons.append(f"GDPNow가 {prev.gdp:.2f}% → {latest.gdp:.2f}%로 하향")
    else:
        reasons.append(f"GDPNow 변화는 {gdp_d:+.2f}%p로 작음")

    # Final sales helps distinguish repeatable demand from inventory noise.
    if final_d >= 0.30:
        score += 1
        reasons.append(f"재고 제외 최종판매도 직전보다 {final_d:+.2f}%p 강화")
    elif final_d <= -0.30:
        score -= 1
        reasons.append(f"재고 제외 최종판매는 직전보다 {final_d:+.2f}%p 약화")

    # Inventory should not turn a weak-demand print into a hawkish signal.
    if inv_d >= 0.50 and (private_d is None or private_d < 0.20):
        score -= 1
        reasons.append(f"재고 기여도 {inv_d:+.2f}%p 확대가 헤드라인을 부풀리는 요인")
    elif inv_d <= -0.50 and private_d is not None and private_d > 0.20:
        score += 1
        reasons.append(f"재고 기여도 {inv_d:+.2f}%p 악화가 강한 최종수요를 가리는 요인")

    # Net exports are shown as a composition warning, not treated as domestic demand.
    if net_d is not None and abs(net_d) >= 0.40:
        direction = "악화" if net_d < 0 else "개선"
        reasons.append(f"순수출 기여도는 직전보다 {net_d:+.2f}%p {direction} — 국내수요와 분리해서 봐야 함")

    if score >= 4:
        label = "🔴 장기금리 상승 압력 강"
    elif score >= 2:
        label = "🟠 장기금리 상승 압력"
    elif score <= -4:
        label = "🔵 장기금리 하락 압력 강"
    elif score <= -2:
        label = "🟦 장기금리 하락 압력"
    else:
        label = "⚪ 장기금리 영향 혼합"

    if private_d is not None:
        if score >= 2:
            thesis = f"핵심 최종수요가 {private_d:+.2f}%p 강화돼, 이번 GDPNow 업데이트는 금리 상승 쪽으로 해석합니다."
        elif score <= -2:
            thesis = f"핵심 최종수요가 {private_d:+.2f}%p 약화돼, 이번 GDPNow 업데이트는 금리 하락 쪽으로 해석합니다."
        else:
            thesis = "헤드라인 GDP와 최종수요·재고가 엇갈려 금리 방향 신호가 뚜렷하지 않습니다."
    else:
        thesis = "GDPNow의 방향은 확인되지만 핵심 민간 최종수요 비교가 불완전해 신호 강도를 낮춥니다."

    return label, thesis, reasons


def main() -> int:
    if not PATH.exists():
        return 0
    raw = PATH.read_text(encoding="utf-8").strip()
    lines = raw.splitlines()

    meta_lookup = {
        "조회": take(lines, "조회:"),
        "분기": take(lines, "분기:"),
        "업데이트": take(lines, "업데이트:"),
    }
    key = section(lines, "<b>핵심 숫자</b>", ("<b>장기금리 확인</b>", "<b>판정</b>", "<b>주의</b>", "<b>공식 출처</b>"))
    rates = section(lines, "<b>장기금리 확인</b>", ("<b>판정</b>", "<b>주의</b>", "<b>공식 출처</b>"))
    cautions = section(lines, "<b>주의</b>", ("<b>공식 출처</b>",))
    sources = section(lines, "<b>공식 출처</b>", tuple())
    if not key:
        return 0

    gdp = take(key, "• GDPNow:")
    cipi = take(key, "• 재고 기여도(CIPI):")
    final_sales = take(key, "• 재고 제외 최종판매:")
    cipi_share = take(key, "• 재고가 헤드라인 성장에서 차지하는 비중:")
    pce = take(key, "• 민간소비 기여도:")
    private_final = take(key, "• 민간소비+고정투자 기여 합계")
    net_exports = take(key, "• 순수출 기여도:")

    try:
        rows = fetch_contrib_rows()
        latest = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else None
        signal_label, signal_thesis, signal_reasons = rate_signal(latest, prev)
        latest_private = private_final_contribution(latest)
        prev_private = private_final_contribution(prev) if prev else None
        private_delta = (latest_private - prev_private) if latest_private is not None and prev_private is not None else None
        net_delta = (latest.net_exports - prev.net_exports) if prev and latest.net_exports is not None and prev.net_exports is not None else None
    except Exception as exc:
        signal_label = "⚪ 장기금리 영향 판단 유보"
        signal_thesis = f"GDP 구성 재검증 실패로 방향을 단정하지 않습니다: {type(exc).__name__}"
        signal_reasons = []
        latest_private = prev_private = private_delta = net_delta = None

    def value_after_colon(line: str | None) -> str:
        if not line:
            return "확인 불가"
        return clean_bullet(line).split(":", 1)[1].strip() if ":" in line else clean_bullet(line)

    rate_lines = ["• " + clean_bullet(x) for x in rates]
    risk_line = next((clean_bullet(x) for x in cautions if "최대 반전 경로" in x), None)
    caution_regular = [clean_bullet(x) for x in cautions if "최대 반전 경로" not in x and "다음 Atlanta Fed 업데이트" not in x]
    next_update = next((clean_bullet(x) for x in cautions if "다음 Atlanta Fed 업데이트" in x), None)

    out: list[str] = [
        "📊 <b>미국 GDPNow → 장기금리 방향</b>",
        "━━━━━━━━━━━━━━━━",
        f"<b>{signal_label}</b>",
        signal_thesis,
    ]

    meta_bits = []
    if meta_lookup["분기"]:
        meta_bits.append(meta_lookup["분기"].replace("분기:", "").strip())
    if meta_lookup["업데이트"]:
        meta_bits.append(meta_lookup["업데이트"].replace("업데이트:", "").strip())
    if meta_bits:
        out += ["", "<code>" + " | ".join(meta_bits) + "</code>"]

    out += ["", "🎯 <b>왜 금리가 이 방향인가</b>"]
    for idx, reason in enumerate(signal_reasons[:5], start=1):
        out.append(f"{idx}. {reason}")

    out += ["", "📌 <b>핵심 숫자</b>"]
    if gdp:
        out.append("• " + clean_bullet(gdp))
    if latest_private is not None:
        text = f"• 민간 최종수요 기여도: <b>{latest_private:+.2f}%p</b>"
        if prev_private is not None and private_delta is not None:
            text += f" (직전 {prev_private:+.2f}%p → {private_delta:+.2f}%p 변화)"
        out.append(text)
    elif private_final:
        out.append("• " + clean_bullet(private_final))
    if final_sales:
        out.append("• " + clean_bullet(final_sales))
    if cipi:
        out.append("• " + clean_bullet(cipi))
    if cipi_share:
        out.append("• " + clean_bullet(cipi_share))
    if net_exports:
        net_text = "• " + clean_bullet(net_exports)
        if net_delta is not None:
            net_text += f" (직전 대비 {net_delta:+.2f}%p)"
        out.append(net_text)
    if pce:
        out.append("• " + clean_bullet(pce))

    out += ["", "📈 <b>현재 장기금리 확인</b>"] + rate_lines
    out += [
        "",
        "🧭 <b>해석 원칙</b>",
        "• GDPNow 상승 자체보다 <b>민간소비+민간 고정투자</b>가 같이 강해졌는지를 가장 크게 봅니다.",
        "• 재고만 늘어 GDP가 높아지면 금리 상승 신호를 약하게 봅니다.",
        "• 순수출 악화로 GDP가 낮아져도 미국 내수가 강하면 금리 하락 신호로 단정하지 않습니다.",
        "• 따라서 알림의 결론은 ‘GDP 구성 변화가 장기금리에 주는 상승/하락 압력’이며 실제 시장금리 움직임은 물가·Fed·국채수급과 별도로 확인합니다.",
    ]

    if risk_line:
        risk_text = risk_line.split(":", 1)[1].strip() if ":" in risk_line else risk_line
        out += ["", "⚠️ <b>반전 조건</b>", risk_text]

    if caution_regular:
        out += ["", "ℹ️ <b>주의</b>"] + ["• " + x for x in caution_regular]
    if next_update:
        out += ["", "🗓 <b>다음 확인</b>", "• " + next_update]
    if sources:
        out += ["", "🔗 <b>공식 출처</b>"] + sources

    PATH.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

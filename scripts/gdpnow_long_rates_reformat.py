#!/usr/bin/env python3
"""Reformat GDPNow Telegram HTML for scanability without dropping information."""
from __future__ import annotations

import pathlib
import re

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
    verdicts = section(lines, "<b>판정</b>", ("<b>주의</b>", "<b>공식 출처</b>"))
    cautions = section(lines, "<b>주의</b>", ("<b>공식 출처</b>",))
    sources = section(lines, "<b>공식 출처</b>", tuple())

    if not key or not verdicts:
        return 0

    gdp = take(key, "• GDPNow:")
    cipi = take(key, "• 재고 기여도(CIPI):")
    final_sales = take(key, "• 재고 제외 최종판매:")
    cipi_share = take(key, "• 재고가 헤드라인 성장에서 차지하는 비중:")
    pce = take(key, "• 민간소비 기여도:")
    private_final = take(key, "• 민간소비+고정투자 기여 합계")
    net_exports = take(key, "• 순수출 기여도:")

    # Build a compact dashboard line from existing values, without changing the numbers.
    def value_after_colon(line: str | None) -> str:
        if not line:
            return "확인 불가"
        return clean_bullet(line).split(":", 1)[1].strip() if ":" in line else clean_bullet(line)

    headline_items = []
    if gdp:
        headline_items.append("GDPNow " + value_after_colon(gdp))
    if final_sales:
        final_value = re.sub(r"\s*=.*", "", value_after_colon(final_sales)).strip()
        headline_items.append("최종판매 " + final_value)

    growth_lines: list[str] = []
    if cipi:
        growth_lines.append("🟡 " + clean_bullet(cipi))
    if cipi_share:
        growth_lines.append("↳ " + clean_bullet(cipi_share))
    if pce:
        growth_lines.append("🟢 " + clean_bullet(pce))
    if private_final:
        growth_lines.append("🟢 " + clean_bullet(private_final))
    if net_exports:
        growth_lines.append("🔴 " + clean_bullet(net_exports))
    # Keep the full formula/detail line as a dedicated calculation row.
    if final_sales:
        growth_lines.append("🧮 " + clean_bullet(final_sales))

    rate_lines = ["• " + clean_bullet(x) for x in rates]
    verdict_lines = [f"{idx}. {clean_bullet(x)}" for idx, x in enumerate(verdicts, start=1)]

    risk_line = next((clean_bullet(x) for x in cautions if "최대 반전 경로" in x), None)
    caution_regular = [clean_bullet(x) for x in cautions if "최대 반전 경로" not in x and "다음 Atlanta Fed 업데이트" not in x]
    next_update = next((clean_bullet(x) for x in cautions if "다음 Atlanta Fed 업데이트" in x), None)

    out: list[str] = [
        "📊 <b>미국 GDPNow · 장기금리 업데이트</b>",
        "━━━━━━━━━━━━━━━━",
    ]
    meta_bits = []
    if meta_lookup["분기"]:
        meta_bits.append(meta_lookup["분기"].replace("분기:", "").strip())
    if meta_lookup["업데이트"]:
        meta_bits.append(meta_lookup["업데이트"].replace("업데이트:", "").strip())
    if meta_bits:
        out.append("<code>" + " | ".join(meta_bits) + "</code>")
    if meta_lookup["조회"]:
        out.append("조회 " + meta_lookup["조회"].replace("조회:", "").strip())

    out += ["", "🔎 <b>한눈에</b>"]
    if headline_items:
        out.append(" · ".join(headline_items))
    if cipi:
        cipi_short = value_after_colon(cipi).split("(", 1)[0].strip()
        out.append("재고 " + cipi_short + (" · " + value_after_colon(cipi_share) if cipi_share else ""))

    out += ["", "📦 <b>성장 구성</b>"] + growth_lines
    out += ["", "📈 <b>장기금리</b>"] + rate_lines
    out += ["", "🧭 <b>판정</b>"] + verdict_lines

    if risk_line:
        risk_text = risk_line.split(":", 1)[1].strip() if ":" in risk_line else risk_line
        out += ["", "⚠️ <b>최대 반전 경로</b>", risk_text]

    out += ["", "ℹ️ <b>해석 기준</b>"]
    out += ["• " + x for x in caution_regular]
    if next_update:
        out += ["", "🗓 <b>다음 확인</b>", "• " + next_update]

    if sources:
        out += ["", "🔗 <b>공식 출처</b>"] + sources

    PATH.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

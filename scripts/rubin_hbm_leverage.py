from __future__ import annotations

import html
import pathlib
import re

ALERT = pathlib.Path("out/rubin_hbm_alert.md")

ACCELERATOR_GROWTH = 0.17
HBM_CONTENT_LOW = 0.25
HBM_CONTENT_HIGH = 0.30
SUPPLY_LOW = 0.50
SUPPLY_HIGH = 0.60
ASP_SCENARIOS = (0.00, 0.15, 0.25, 0.50)


def revenue_growth(volume_growth: float, asp_growth: float) -> float:
    return (1 + volume_growth) * (1 + asp_growth) - 1


def fmt_pct(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%"


def fix_source_links(text: str) -> str:
    pattern = re.compile(r"(?m)^\s*-?\s*\[원문\]\((https?://[^\s)]+)\)\s*$")
    return pattern.sub(
        lambda m: f'<a href="{html.escape(m.group(1), quote=True)}"><b>원문</b></a>',
        text,
    )


def main() -> None:
    if not ALERT.exists():
        return

    text = ALERT.read_text(encoding="utf-8").strip()
    if not text:
        return

    text = fix_source_links(text)
    if "[HBM 수요·가격 레버리지]" in text:
        ALERT.write_text(text.strip() + "\n", encoding="utf-8")
        return

    bit_low = (1 + ACCELERATOR_GROWTH) * (1 + HBM_CONTENT_LOW) - 1
    bit_high = (1 + ACCELERATOR_GROWTH) * (1 + HBM_CONTENT_HIGH) - 1

    scenario_lines: list[str] = []
    for asp in ASP_SCENARIOS:
        low = revenue_growth(bit_low, asp)
        high = revenue_growth(bit_high, asp)
        scenario_lines.append(
            f"• 평균판매단가 <b>{fmt_pct(asp)}</b>  →  HBM 매출 <b>+{low*100:.0f}~{high*100:.0f}%</b>"
        )

    block = [
        "",
        "📈 <b>[HBM 수요·가격 레버리지]</b>",
        f"• <b>비트 수요</b>  +{bit_low*100:.0f}~{bit_high*100:.0f}%  =  AI 가속기 +17% × GPU당 HBM +25~30%",
        f"• <b>비트 공급</b>  TrendForce 2027 +{SUPPLY_LOW*100:.0f}~{SUPPLY_HIGH*100:.0f}% 전망에도 수요를 못 따라갈 가능성",
        "",
        "<b>매출 민감도</b>",
        *scenario_lines,
        "",
        "<b>핵심 판정</b>",
        "• <b>HBM 가격 +50%가 아니어도 강세 가능</b> — 물량 증가만으로도 매출 성장 가능",
        "• 가격까지 오르면 SK하이닉스·삼성전자·Micron의 실적 레버리지 확대",
        "• <b>GPU당 HBM 구매비 증가율 ≠ GB당 HBM 평균판매단가 상승률</b>",
        "",
        "<blockquote expandable><b>레버리지 판정 자세히</b>\n"
        "강한 호재: 2027 HBM 계약가격 상승 + 계약물량 유지·증가 / HBM4E 고객 인증 완료 + 양산 일정 확정 / GPU 출하 증가 + GPU당 HBM 탑재량 증가 동시 확인\n\n"
        "실패 경로: HBM 공급 증가가 수요를 앞지르거나 AI 서버 가격 상승으로 GPU 설비투자가 둔화되면 비트 수요 성장률이 낮아질 수 있습니다.</blockquote>",
    ]

    marker = "\n━━━━━━━━━━━━━━━━\n<b>[상세 근거]</b>"
    if marker in text:
        text = text.replace(marker, "\n" + "\n".join(block) + marker, 1)
    else:
        text = text + "\n" + "\n".join(block)

    ALERT.write_text(text.strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

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
    """HTML parse_mode에서 Markdown 원문 링크가 글자로 노출되지 않도록 인라인 HTML 링크로 고친다."""
    pattern = re.compile(
        r"(?m)^\s*-?\s*\[원문\]\((https?://[^\s)]+)\)\s*$"
    )
    return pattern.sub(
        lambda m: f'<a href="{html.escape(m.group(1), quote=True)}">원문</a>',
        text,
    )


def main() -> None:
    if not ALERT.exists():
        return

    text = ALERT.read_text(encoding="utf-8").strip()
    if not text:
        return

    # pretty 단계가 처리하지 못한 [원문](URL) 형식도 최종 Telegram HTML 형식으로 보정한다.
    text = fix_source_links(text)

    # 같은 알림을 재처리하더라도 링크 보정은 유지하고 레버리지 블록만 중복 삽입하지 않는다.
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
            f"• 평균판매단가 {fmt_pct(asp)} → HBM 매출 <b>+{low*100:.0f}~{high*100:.0f}%</b>"
        )

    block = [
        "",
        "📈 <b>[HBM 수요·가격 레버리지]</b>",
        "• <b>LS증권 가정:</b> AI 가속기 <b>+17%</b> × GPU당 HBM 탑재량 <b>+25~30%</b>",
        f"  → HBM 비트 수요 <b>+{bit_low*100:.0f}~{bit_high*100:.0f}%</b>",
        f"• <b>TrendForce 2027:</b> HBM 비트 공급 <b>+{SUPPLY_LOW*100:.0f}~{SUPPLY_HIGH*100:.0f}%</b> 전망에도 수요를 못 따라갈 가능성",
        "",
        "<b>비트 수요가 +46~52%일 때 매출 민감도</b>",
        *scenario_lines,
        "",
        "<b>해석</b>",
        "• <b>HBM 가격 +50%가 반드시 필요한 강세 논리는 아님</b>",
        "• 가격이 그대로여도 탑재량·가속기 증가만으로 HBM 매출이 크게 성장 가능",
        "• 가격 상승까지 붙으면 SK하이닉스·삼성전자·Micron의 실적 레버리지 확대",
        "• <b>GPU당 HBM 구매비 증가율 ≠ GB당 HBM 평균판매단가 상승률</b>",
        "",
        "<b>강한 호재 확인 조건</b>",
        "• 2027 HBM 계약가격 상승 + 계약물량 유지·증가",
        "• HBM4E 고객 인증 완료 + 양산 일정 확정",
        "• GPU 출하 증가 + GPU당 HBM 탑재량 증가가 동시에 확인",
        "",
        "<b>실패 경로</b>",
        "• HBM 공급 증가가 수요를 앞지르거나",
        "• AI 서버 가격 상승으로 GPU 설비투자가 둔화되면 비트 수요 성장률 하향",
    ]

    marker = "\n━━━━━━━━━━━━━━━━\n<b>[상세 근거]</b>"
    if marker in text:
        text = text.replace(marker, "\n" + "\n".join(block) + marker, 1)
    else:
        text = text + "\n" + "\n".join(block)

    ALERT.write_text(text.strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

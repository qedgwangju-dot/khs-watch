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

    # A hybrid-bonding process-risk alert must not inherit generic Rubin
    # 288→192GB GPU/demand scenarios. Source-only corrections likewise.
    if text.lstrip().startswith((
        "<b>🚨 HBM 하이브리드 본딩",
        "🚨 <b>HBM 하이브리드 본딩",
        "🚨 HBM 하이브리드 본딩",
        "<b>🚨 NVHBM 베이스 다이",
        "🚨 NVHBM 베이스 다이",
    )):
        return

    text = fix_source_links(text)
    # Append model assumptions only to actual Rubin/HBM quantity or pricing
    # stories, never to a generic event or a hybrid-bonding-only notice.
    evidence_topics = (
        "■ Rubin Ultra 최종 HBM 사양",
        "■ Rubin Ultra·NVL576 실제 출하",
        "■ 2027 HBM 계약가격·물량",
        "■ HBM↔DDR5 웨이퍼 경제성",
        "■ Rubin Ultra HBM4/HBM4E 옵션 변화",
    )
    if not any(topic in html.unescape(re.sub(r"</?b>", "", text)) for topic in evidence_topics):
        ALERT.write_text(text.strip() + "\n", encoding="utf-8")
        return
    if "[HBM 수요·가격 레버리지]" in text or "[HBM 적층·GPU·전력 교차판정]" in text:
        ALERT.write_text(text.strip() + "\n", encoding="utf-8")
        return


    # A stack-height change may REDUCE installed bits despite more accelerators.
    # The +17% acceleration and +10~20%/Gb examples are scenario inputs,
    # never evidence of actual GPU shipments, energization or signed memory ASP.
    normalized = html.unescape(re.sub(r"</?b>", "", text))
    if any(topic in normalized for topic in (
        "■ Rubin Ultra 최종 HBM 사양",
        "■ Rubin Ultra HBM4/HBM4E 옵션 변화",
    )):
        ratio_12_to_8 = 8 / 12
        assumed_gpu_ratio = 1 + ACCELERATOR_GROWTH
        bits_delta = (assumed_gpu_ratio * ratio_12_to_8 - 1) * 100
        revenue_low = (assumed_gpu_ratio * ratio_12_to_8 * 1.10 - 1) * 100
        revenue_high = (assumed_gpu_ratio * ratio_12_to_8 * 1.20 - 1) * 100
        block = [
            "",
            "<b>[HBM 적층·GPU·전력 교차판정]</b>",
            "• 구조 변화 시나리오(미확정): 동일 다이 용량·GPU당 스택 수를 가정하면 12단→8단은 스택당 HBM 비트 -33.3%, 반대로 8단→12단은 +50.0%입니다.",
            "• 12단→8단 시 GPU 출하가 +50.0% 증가해야 전체 HBM 비트 총수요가 유지됩니다. 실제 GPU 출하량·GPU당 용량은 별도 확인 대상입니다.",
            f"• 가정 예시: GPU 출하 +17%와 12단→8단 변화가 함께 일어날 경우 총 HBM 비트 수요 {bits_delta:+.1f}%(이는 실제 전망·출하가 아닙니다).",
            f"• 같은 가정에 Gb당 가격 +10~20%를 적용한 HBM 매출은 {revenue_low:+.1f}~{revenue_high:+.1f}%(계약가·실적 미확인).",
            "• 판정 보류: GPU 실제 출하·GPU당 스택 수·다이 용량·8/12/16단 혼합 및 공급사별 가격이 공개되지 않으면 실제 총 비트 수요 증가·감소를 확정할 수 없습니다.",
            "• 전력 교차확인: 데이터센터 발표·착공 GW와 전력 접속·전원 인가·실제 가동 GW를 구분합니다. 전력 부족으로 칩 사용이 늦어질 위험과 HBM 발주 물량 변화는 별개로 검증합니다.",
            "• 시장 전체 2028년 공급 부족 전망도 개별 GPU의 적층 확정 사양이나 특정 공급사의 확정 매출로 승격하지 않습니다.",
        ]
        marker = "\n━━━━━━━━━━━━━━━━\n<b>[상세 근거]</b>"
        if marker in text:
            text = text.replace(marker, "\n" + "\n".join(block) + marker, 1)
        else:
            text = text + "\n" + "\n".join(block)
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

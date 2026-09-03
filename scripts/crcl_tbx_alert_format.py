#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "crcl_usdc_rate_watch_telegram.txt"


def main() -> None:
    if not ALERT_PATH.exists():
        return

    text = ALERT_PATH.read_text(encoding="utf-8")
    crcl_m = re.search(r"• <b>CRCL</b> \$[\d.]+ · [^|\n]+\| 일간 ([+-]?\d+(?:\.\d+)?)%", text)
    tbx_m = re.search(r"• <b>TBX</b> \$[\d.]+ · [^|\n]+\| 일간 ([+-]?\d+(?:\.\d+)?)%", text)
    if not crcl_m or not tbx_m:
        return

    crcl_pct = float(crcl_m.group(1))
    tbx_pct = float(tbx_m.group(1))

    if tbx_pct > 0:
        tbx_line = (
            f"• <b>TBX {tbx_pct:+.2f}% 상승</b> → 7~10년 미 국채 가격 하락 → 중장기 금리 상승"
        )
        base_line = "  → <b>CRCL에는 할인율 부담 확대</b>라 주가 측면에서는 기본적으로 불리"
        if crcl_pct < 0:
            compare_line = (
                f"• <b>CRCL {crcl_pct:+.2f}% 하락</b> → TBX가 가리키는 할인율 부담과 주가 방향이 일치"
            )
        elif crcl_pct > 0:
            compare_line = (
                f"• <b>그런데 CRCL은 {crcl_pct:+.2f}% 상승</b> → 장기금리 부담보다 USDC·실적·개별 촉매가 더 강하게 작용한 것으로 해석"
            )
        else:
            compare_line = "• CRCL 보합 → 장기금리 부담이 주가에 뚜렷하게 반영됐다고 보기 어려움"
    elif tbx_pct < 0:
        tbx_line = (
            f"• <b>TBX {tbx_pct:+.2f}% 하락</b> → 7~10년 미 국채 가격 상승 → 중장기 금리 하락"
        )
        base_line = "  → <b>CRCL에는 할인율 부담 완화</b>라 주가 측면에서는 기본적으로 우호적"
        if crcl_pct > 0:
            compare_line = (
                f"• <b>CRCL도 {crcl_pct:+.2f}% 상승</b> → TBX가 가리키는 할인율 완화와 주가 방향이 일치"
            )
        elif crcl_pct < 0:
            compare_line = (
                f"• <b>그런데 CRCL은 {crcl_pct:+.2f}% 하락</b> → 할인율 호재보다 USDC·단기금리·개별 악재가 더 강하게 작용한 것으로 해석"
            )
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
    if marker in text and "<b>TBX → CRCL 쉽게 해석</b>" not in text:
        text = text.replace(marker, block + marker, 1)
        ALERT_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

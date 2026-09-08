#!/usr/bin/env python3
from __future__ import annotations

import html

import korea_market_stress_watch_v12 as v12

watch = v12.watch

AUTO_FX_NEWS = "https://www.yna.co.kr/view/AKR20260907020500008"
AUTO_FX_SECONDARY = "https://www.fnnews.com/news/202609070837421236"


def _fx_direction(text: str) -> str | None:
    head = text.split("<b>알림 기준</b>", 1)[0]
    if "원/달러 일간 급락:" in head or "원/달러 1,350원 하단 진입:" in head:
        return "down"
    if "원/달러 일간 급등:" in head or "원/달러 1,400원 상단 진입:" in head:
        return "up"
    return None


def _append_auto_fx_timing() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
    if _fx_direction(text) != "down" or "<b>완성차 환율 영향 시간차</b>" in text:
        return

    lines = text.splitlines()
    insert_at = next((i for i, line in enumerate(lines) if "<b>알림 기준</b>" in line), len(lines))
    additions = [
        "<b>완성차 환율 영향 시간차</b>",
        "🔻 <b>환율 하락 충격은 3분기보다 4분기에 더 직접 반영될 가능성</b>",
        "• 유안타증권 시나리오: 7월 평균 1,490원 · 8월 1,404원 · 9월 1,350원 가정 → <b>3분기 평균 약 1,415원</b>",
        "• 3분기: 기말 환율이 전분기 1,549원보다 <b>192원 하락</b>하면 외화 충당부채 설정액 감소가 수출 수익성 악화를 일부 상쇄",
        "• 4분기: 환율이 <b>1,350원 수준에 머물면</b> 충당금 감소라는 방어 효과가 사라져 수출 채산성 하락이 실적에 더 온전히 반영될 수 있음",
        "• 반대로 4분기 환율이 반등해도 외화 충당부채 설정액이 다시 늘어 영업이익 개선 폭을 제한할 수 있다는 점이 변수",
        "• 과거 환율 수혜 규모 추정(2023년 1분기~2026년 2분기): 현대차 <b>+3조7천억원</b> · 기아 <b>+4조3천억원</b> 영업이익 효과",
        "• 따라서 알림 해석은 ‘당일 주가 반응’과 ‘4분기 실적 반영 시점’을 분리해 표시",
        "• 상방 대안: 글로벌 점유율 확대 · 보스턴 다이내믹스 지분가치 재평가 · 환율 급반등",
        "• 하방 위험: 원화 강세 지속 · 원자재 가격 상승 · 전기차 경쟁 심화에 따른 인센티브 증가",
        "",
    ]
    lines[insert_at:insert_at] = additions

    source_lines = [
        f'• <a href="{html.escape(AUTO_FX_NEWS, quote=True)}">유안타증권 완성차 환율 영향 전망</a>',
        f'• <a href="{html.escape(AUTO_FX_SECONDARY, quote=True)}">완성차 환율·주가 보조 확인</a>',
    ]
    if "<b>원문</b>" in lines:
        src_idx = lines.index("<b>원문</b>") + 1
        for item in reversed(source_lines):
            if item not in lines:
                lines.insert(src_idx, item)
    else:
        lines.extend(["", "<b>원문</b>", *source_lines])

    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rc = v12.main()
    _append_auto_fx_timing()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

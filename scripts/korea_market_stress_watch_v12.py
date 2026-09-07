#!/usr/bin/env python3
from __future__ import annotations

import html

import korea_market_stress_watch_v11 as v11

watch = v11.watch

COSMETICS_FX_NEWS = "https://v.daum.net/v/20260908060206042"
SOL_COSMETICS_OFFICIAL = "https://www.soletf.co.kr/ko/fund/etf/211080"
HANARO_KBEAUTY_OFFICIAL = "https://www.hanaroetf.com/investment/insight/LeI7APPY1L8osQSG"
TIGER_SECTOR_LIST = "https://investments.miraeasset.com/tigeretf/ko/pension/sector-country/list.do"

COSMETICS_ETFS = [
    ("SOL 화장품TOP3플러스", "0008T0"),
    ("TIGER 화장품", "228790"),
    ("HANARO K-뷰티", "479850"),
]

COSMETICS_EXPORT_LEADERS = [
    ("실리콘투", "257720"),
    ("한국콜마", "161890"),
    ("에이피알", "278470"),
    ("코스맥스", "192820"),
    ("코스메카코리아", "241710"),
]


def _fx_direction(text: str) -> str | None:
    head = text.split("<b>알림 기준</b>", 1)[0]
    if "원/달러 일간 급락:" in head or "원/달러 1,350원 하단 진입:" in head:
        return "down"
    if "원/달러 일간 급등:" in head or "원/달러 1,400원 상단 진입:" in head:
        return "up"
    return None


def _quote_line(name: str, code: str) -> tuple[str, str | None]:
    try:
        q = v11.fetch_stock_quote(code)
        actual_name = str(q.get("name") or name)
        return (
            f"• {html.escape(actual_name)}: <b>{q['price']:,.0f}원 ({q['change_pct']:+.2f}%)</b>",
            None,
        )
    except Exception as exc:
        return (f"• {html.escape(name)}: 시세 확인 실패", f"{name}({code}): {type(exc).__name__}: {exc}")


def _append_cosmetics_fx_context() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
    direction = _fx_direction(text)
    if direction is None or "<b>화장품·K-뷰티 환율 민감도</b>" in text:
        return

    errors: list[str] = []
    etf_lines: list[str] = []
    stock_lines: list[str] = []
    for name, code in COSMETICS_ETFS:
        line, err = _quote_line(name, code)
        etf_lines.append(line)
        if err:
            errors.append(err)
    for name, code in COSMETICS_EXPORT_LEADERS:
        line, err = _quote_line(name, code)
        stock_lines.append(line)
        if err:
            errors.append(err)

    if direction == "down":
        verdict = "원화 강세 → 달러 수출 매출의 원화 환산액 감소 → 수출 비중 높은 화장품 기업의 매출·영업이익률 부담"
        impact = "🔻 <b>환율 하락 시 실적 부담 민감 업종</b>"
    else:
        verdict = "원화 약세 → 달러 수출 매출의 원화 환산액 증가 → 수출 비중 높은 화장품 기업의 원화 환산 실적에 우호적"
        impact = "🔺 <b>환율 상승 시 원화 환산 실적 수혜 가능 업종</b>"

    additions = [
        "<b>화장품·K-뷰티 환율 민감도</b>",
        impact,
        f"• 구조: {verdict}",
        "• 한국투자증권 추정: 원/달러가 <b>5% 하락하면 화장품 업종 영업이익률 약 0.7~0.8%p 하락 가능</b>",
        "• 2026년 7월 화장품 수출 중 미국 비중: <b>21.8%</b>",
        "",
        "<b>화장품 ETF 현재 반응</b>",
        *etf_lines,
        "",
        "<b>대표 수출주 현재 반응</b>",
        *stock_lines,
        "",
        "• 최근 확인 사례(2026-09-08): 지난 1주 SOL 화장품TOP3플러스 -12.70%, TIGER 화장품 -11.64%, HANARO K-뷰티 -9.87%로 국내 ETF 수익률 하위 1~3위",
        "• 반대 신호도 확인: 같은 1주 TIGER 화장품에는 270억원, SOL 화장품TOP3플러스에는 138억원 순유입 → 환율 부담과 장기 K-뷰티 성장 기대가 동시에 존재",
        "• 해석: 주가 하락을 환율 하나로만 단정하지 않고 수출 성장률·제품 믹스·현지 가격 인상·환헤지 여부까지 같이 확인",
        "",
    ]

    lines = text.splitlines()
    insert_at = next((i for i, line in enumerate(lines) if "<b>알림 기준</b>" in line), len(lines))
    lines[insert_at:insert_at] = additions

    source_lines = [
        f'• <a href="{html.escape(COSMETICS_FX_NEWS, quote=True)}">화장품 ETF 환율 급락 실제 반응</a>',
        f'• <a href="{html.escape(SOL_COSMETICS_OFFICIAL, quote=True)}">SOL 화장품TOP3플러스 공식</a>',
        f'• <a href="{html.escape(HANARO_KBEAUTY_OFFICIAL, quote=True)}">HANARO K-뷰티 공식</a>',
        f'• <a href="{html.escape(TIGER_SECTOR_LIST, quote=True)}">TIGER 화장품 공식 상품 목록</a>',
    ]
    if "<b>원문</b>" in lines:
        src_idx = lines.index("<b>원문</b>") + 1
        for item in reversed(source_lines):
            if item not in lines:
                lines.insert(src_idx, item)
    else:
        lines.extend(["", "<b>원문</b>", *source_lines])

    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if errors:
        with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
            for err in errors:
                f.write("화장품 환율 영향 시세 조회 실패: " + err + "\n")


def main() -> int:
    rc = v11.main()
    _append_cosmetics_fx_context()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

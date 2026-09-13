#!/usr/bin/env python3
from __future__ import annotations

import html
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "khs_us_investment_alert.html"

LOW_VALUE_TERMS = [
    "고래사냥", "내일장", "오늘장", "내일 장", "오늘 장", "종목은?!", "종목은?",
    "주식방송", "매매전략", "급등주", "추천종목",
]
HARD_PROGRESS_TERMS = [
    "계약", "체결", "수주", "구매주문", "발주", "po", "ppa", "허가", "착공",
    "전원 인가", "energized", "확정", "선정", "제조사", "fid", "financial close",
]


def _clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def _remove_low_value_items(text: str) -> tuple[str, int]:
    """Remove stock-show/listicle items after the normal readability finalizer."""
    block_re = re.compile(
        r'(?P<block><b>\d+\.\s*<a href="[^"]+">(?P<title>.*?)</a></b>\n'
        r'(?:•[^\n]*\n){1,5}(?:\n|$))',
        re.S,
    )
    removed = 0

    def drop(match: re.Match) -> str:
        nonlocal removed
        title = _clean(match.group("title")).lower()
        low_value = any(term.lower() in title for term in LOW_VALUE_TERMS)
        hard_progress = any(term.lower() in title for term in HARD_PROGRESS_TERMS)
        if low_value and not hard_progress:
            removed += 1
            return ""
        return match.group("block")

    cleaned = block_re.sub(drop, text)

    # Renumber the remaining visible news items after a removal.
    head_re = re.compile(r'<b>\d+\.\s*<a href="(?P<link>[^"]+)">(?P<title>.*?)</a></b>', re.S)
    counter = 0

    def renumber(match: re.Match) -> str:
        nonlocal counter
        counter += 1
        return f'<b>{counter}. <a href="{match.group("link")}">{match.group("title")}</a></b>'

    cleaned = head_re.sub(renumber, cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned, removed


def _current_change_area(text: str) -> str:
    # The mandatory project-cost block contains Encinal/gas-turbine context on every alert.
    # Do not use that fixed baseline to decide whether the alternative-power block is relevant.
    marker = "<b>💰 대미투자 프로젝트 기준 사업비</b>"
    return text.split(marker, 1)[0] if marker in text else text


def main() -> int:
    if not ALERT.exists():
        print("altpower_finalize=none")
        return 0

    text = ALERT.read_text(encoding="utf-8")
    text, removed = _remove_low_value_items(text)

    # Remove a legacy long block if an older formatter left one in the file.
    for marker in [
        "<b>♨️ 가스터빈 병목·대체전원 기준선</b>",
        "<b>♨️ 가스터빈 병목·대체전원</b>",
    ]:
        if marker in text:
            text = text.split(marker, 1)[0].rstrip() + "\n"

    current = _current_change_area(text).lower()
    relevant = any(
        token in current
        for token in [
            "가스터빈", "gas turbine", "hrsg", "스팀터빈", "증기터빈", "steam turbine",
            "보일러", "babcock", "base electron", "ge vernova", "siemens energy",
            "두산에너빌리티", "비에이치아이", "snt에너지",
        ]
    )

    if not relevant:
        ALERT.write_text(text, encoding="utf-8")
        print(f"altpower_finalize=not_relevant low_value_removed={removed}")
        return 0

    block = [
        "",
        "<b>♨️ 가스터빈 병목·대체전원</b>",
        "• <b>병목</b>: GE Vernova 공식 기준 가스발전 수주잔고+슬롯예약 <b>116GW → 2026년 말 125GW+</b>; 생산능력 <b>20GW(3Q26) → 24GW(2028) → 30GW(2030)</b>.",
        "• <b>대체전원</b>: B&W–Base Electron <b>1.2GW·24억달러</b> = 300MW 가스보일러 4기 + Siemens Energy 증기터빈. 추가 <b>1.2GW</b> 옵션 평가 중.",
        "• <b>증기터빈 선점</b>: B&W는 Siemens Energy <b>50MW급 20기 = 1GW</b>를 FastPower용으로 선발주.",
        "• <b>국내 영향</b>: 두산의 북미 증기터빈 레퍼런스는 확인되지만 Base Electron·Encinal 공급은 미확정. 직화보일러+증기터빈 확산 시 HRSG를 생략할 수 있어 비에이치아이·SNT에너지는 수혜와 역풍을 함께 확인.",
        "• <b>먼저 볼 것</b>: 제조사·구매주문(PO)·PPA·허가·착공·전원 인가. 병목이 가스터빈에서 증기터빈·보일러·가스관·허가로 이동하는지 추적.",
        "",
        '<b>대체전원 원천</b> · <a href="https://www.gevernova.com/news/articles/ge-vernova-releases-second-quarter-2026-financial-results">GE Vernova</a> · <a href="https://www.babcock.com/home/about/corporate/news/babcock-and-wilcox-receives-full-notice-to-proceed-on-24-billion-power-generation-project-for-base-electron-to-supply-power-to-applied-digital-ai-factory-campuses">B&W 1.2GW</a> · <a href="https://www.babcock.com/home/about/corporate/news/babcock-and-wilcox-signs-agreement-with-siemens-energy-to-commence-work-on-20-steam-turbines-for-data-center-power-generation">B&W 증기터빈 1GW</a>',
    ]

    ALERT.write_text(text.rstrip() + "\n" + "\n".join(block) + "\n", encoding="utf-8")
    print(f"altpower_finalize=compact_appended low_value_removed={removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

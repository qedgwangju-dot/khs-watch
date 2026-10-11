#!/usr/bin/env python3
"""Preserve natural Telegram wrapping for Starlink Mobile alerts.

Do not pre-wrap lines to an imagined mobile screen width. Telegram chooses
line breaks based on the reader's device, font size and accessibility settings.
No substantive characters, original URLs or numbers may be changed here.
"""
from __future__ import annotations

from collections import Counter
import pathlib
import re
import sys

SOURCE = re.compile(r"^• 원문:\s*(https://\S+)\s*$")


def raw_urls(text: str) -> list[str]:
    return [m.group(1) for line in text.splitlines()
            if (m := SOURCE.fullmatch(line.strip()))]


def regular_content(text: str) -> str:
    return "".join(re.sub(r"\s+", "", line) for line in text.splitlines()
                   if not SOURCE.fullmatch(line.strip()))


def verify(original: str, result: str) -> None:
    if raw_urls(original) != raw_urls(result):
        raise AssertionError("A source URL was lost, changed or reordered")
    if regular_content(original) != regular_content(result):
        raise AssertionError("A substantive alert character was altered")
    if Counter(re.findall(r"\d[\d,.]*", regular_content(original))) != Counter(
       re.findall(r"\d[\d,.]*", regular_content(result))
    ):
        raise AssertionError("A reported number was altered")
    if "• 원문: 아래 링크 버튼" in result:
        raise AssertionError("Legacy Telegram button text detected")
    if result != original.rstrip() + "\n":
        raise AssertionError("Do not insert manual screen-width line breaks")


def format_mobile(original: str) -> str:
    if not original.strip():
        raise ValueError("Empty alert")
    # No line splitting, no hardcoded 44-cell screen, no truncation.
    result = original.rstrip() + "\n"
    verify(original, result)
    return result


def self_test() -> int:
    original = (
        "📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시\n"
        "기준: 2026-10-11 16:13 KST\n\n"
        "[주가 기준 정정] 미국 통신 3사\n"
        "AT&T(T) 22.18달러 · -10.82%  배당락 조정: -9.81%. "
        "이 문장은 일부러 길게 유지해 모바일 운영체제가 알아서 줄바꿈하게 합니다.\n"
        "• 원문: https://example.com/a?x=1&y=2\n\n"
        "[발사] Falcon 9 페어링 외경 5.2m·높이 약 13.1m\n"
    )
    formatted = format_mobile(original)
    assert formatted == original
    assert len(formatted.splitlines()) == len(original.splitlines())
    assert raw_urls(formatted) == ["https://example.com/a?x=1&y=2"]
    assert "이 문장은 일부러 길게 유지" in formatted

    from starlink_mobile_d2d_watch import price_dividend_display_correction
    report = price_dividend_display_correction()
    fitted = format_mobile(report)
    assert fitted.count("• 원문: ") == report.count("• 원문: ") == 8
    assert len(fitted.splitlines()) == len(report.splitlines())
    for needle in ("22.18달러", "-10.82%", "-9.81%", "41.65달러", "-10.14%",
                   "-8.75%", "148.58달러", "-13.27%", "0.2775달러", "0.7075달러",
                   "5.2m", "13.1m", "9억4,600만 달러", "1조2,685억원",
                   "2030년", "FCC 이전 승인", "Starship", "Raptor"):
        assert needle in report and needle in fitted, needle
    print("starlink_mobile_readability_self_test=ok forced_wrap=0 source_links=8 fact_loss=0")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()
    if len(sys.argv) != 3:
        print("Usage: starlink_mobile_d2d_readability.py SOURCE OUTPUT | --self-test", file=sys.stderr)
        return 2
    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])
    dst.write_text(format_mobile(src.read_text(encoding="utf-8")),
                   encoding="utf-8")
    print("starlink_mobile_readability=ok forced_wrap=0")


if __name__ == "__main__":
    raise SystemExit(main())

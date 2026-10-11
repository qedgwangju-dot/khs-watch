#!/usr/bin/env python3
"""Lossless Telegram mobile-line formatter for the Starlink D2D watch only.

All original non-URL characters are preserved in order. Only whitespace and
visual line breaks are changed. Source URLs remain byte-for-byte unchanged,
then the sender converts them to compact clickable in-message labels.
"""
from __future__ import annotations

from collections import Counter
import pathlib
import re
import sys
import unicodedata

SOURCE = re.compile(r"^• 원문:\s*(https://\S+)\s*$")
MAX_CELLS = 44
CONTINUATION = "  "


def width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)


def is_source(line: str) -> bool:
    return bool(SOURCE.fullmatch(line.strip()))


def raw_urls(text: str) -> list[str]:
    return [m.group(1) for line in text.splitlines() if (m := SOURCE.fullmatch(line.strip()))]


def regular_content(text: str) -> str:
    # Lossless comparison excludes source lines, which are rendered as linked labels.
    return "".join(re.sub(r"\s+", "", line) for line in text.splitlines() if not is_source(line))


def split_long_token(token: str, prefix: str) -> list[str]:
    output: list[str] = []
    current = prefix
    for char in token:
        if width(current + char) > MAX_CELLS and current.strip():
            output.append(current)
            current = CONTINUATION
        current += char
    if current.strip():
        output.append(current)
    return output


def wrap_line(line: str) -> list[str]:
    if not line or is_source(line):
        return [line]
    if width(line) <= MAX_CELLS:
        return [line]

    leading = line[:len(line) - len(line.lstrip())]
    words = line.strip().split()
    if not words:
        return [line]
    rows: list[str] = []
    current = leading
    for token in words:
        sep = " " if current.strip() else ""
        candidate = current + sep + token
        if width(candidate) <= MAX_CELLS:
            current = candidate
            continue
        if current.strip():
            rows.append(current.rstrip())
            current = CONTINUATION + token
        else:
            current = CONTINUATION + token
        if width(current) > MAX_CELLS:
            token_rows = split_long_token(token, CONTINUATION)
            if not token_rows:
                raise AssertionError("Unexpected empty wrapped token")
            rows.extend(token_rows[:-1])
            current = token_rows[-1]
    if current.strip():
        rows.append(current.rstrip())
    return rows


def format_mobile(raw: str) -> str:
    if not raw.strip():
        raise ValueError("Missing alert")
    lines = []
    for line in raw.splitlines():
        lines.extend(wrap_line(line))
    result = "\n".join(lines).rstrip() + "\n"
    verify(raw, result)
    return result


def verify(original: str, formatted: str) -> None:
    if raw_urls(original) != raw_urls(formatted):
        raise AssertionError("Source URL was lost or changed")
    if regular_content(original) != regular_content(formatted):
        raise AssertionError("A factual character changed or disappeared")
    if Counter(re.findall(r"\d[\d,.]*", regular_content(original))) != Counter(
        re.findall(r"\d[\d,.]*", regular_content(formatted))
    ):
        raise AssertionError("A numeric value changed")
    for line in formatted.splitlines():
        if not is_source(line) and width(line) > MAX_CELLS:
            raise AssertionError("Text line wider than mobile display budget")
    if "• 원문: 아래 링크 버튼" in formatted:
        raise AssertionError("Legacy Telegram button placeholder found")


def self_test() -> int:
    original = (
        "📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시\n"
        "기준: 2026-10-11 16:13 KST\n\n"
        "[주가 기준 정정·가독성 개선] 10월 9일 미국 통신 3사와 발사체\n"
        "• AT&T(T) 22.18달러 -10.82%, 배당락 조정 -9.81%, 버라이즌(VZ) 41.65달러 -10.14% (배당락 조정 -8.75%).\n"
        "• 원문: https://example.com/big/long?amount=1&flag=2\n\n"
        "[발사] Falcon 9는 페어링 외경 5.2m, 높이 약 13.1m입니다."
    )
    result = format_mobile(original)
    assert raw_urls(result) == ["https://example.com/big/long?amount=1&flag=2"]
    assert len(result.splitlines()) > len(original.splitlines())
    assert "[발사]" in result
    assert not any(width(s) > MAX_CELLS for s in result.splitlines() if not is_source(s))

    from starlink_mobile_d2d_watch import price_dividend_display_correction
    report = price_dividend_display_correction()
    fitted = format_mobile(report)
    assert fitted.count("• 원문: ") == report.count("• 원문: ") == 8
    for needle in ("22.18달러", "-10.82%", "-9.81%", "41.65달러", "-10.14%",
                   "-8.75%", "148.58달러", "-13.27%", "0.2775달러", "0.7075달러",
                   "5.2m", "13.1m", "9억4,600만 달러", "1조2,685억원",
                   "2030년", "FCC 이전 승인", "Starship", "Raptor"):
        assert needle in report, needle
        assert needle in fitted, needle
    print("starlink_mobile_readability_self_test=ok mobile_width=44 source_links=8 fact_loss=0")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()
    if len(sys.argv) != 3:
        print("Usage: starlink_mobile_d2d_readability.py SOURCE OUTPUT | --self-test", file=sys.stderr)
        return 2
    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])
    text = src.read_text(encoding="utf-8")
    reformatted = format_mobile(text)
    dst.write_text(reformatted, encoding="utf-8")
    print(f"starlink_mobile_readability=ok lines={len(reformatted.splitlines())} sources={len(raw_urls(reformatted))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

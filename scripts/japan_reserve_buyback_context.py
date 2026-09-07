#!/usr/bin/env python3
"""Append U.S. Treasury buyback context and enforce KRW conversion.

Buyback context is not proof that Treasury increased buybacks because of Japan.
Every monetary amount in the user-facing alert must also show a KRW equivalent.
If validated FX data cannot be obtained, the workflow fails before Telegram send.
"""
from __future__ import annotations

import html
import pathlib
import re

from bs4 import BeautifulSoup

from khs_source_fetch import fetch_text, record_source_failure
from krw_fx import format_krw, latest_jpy_krw

URL = "https://home.treasury.gov/news/press-releases/sb0607"
OUT = pathlib.Path("out/japan_reserve_funding_alert.html")
UA = "Mozilla/5.0 khs-japan-reserve-buyback-context/1.1"

MONEY_RE = re.compile(
    r"(?P<value>[+\-]?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>억달러|십억달러|조달러|조엔)"
)


def _won_for(value: float, unit: str, quote) -> float:
    if unit == "억달러":
        return value * 100_000_000.0 * quote.usdkrw
    if unit == "십억달러":
        return value * 1_000_000_000.0 * quote.usdkrw
    if unit == "조달러":
        return value * 1_000_000_000_000.0 * quote.usdkrw
    if unit == "조엔":
        return value * 1_000_000_000_000.0 * quote.krw_per_yen
    raise ValueError(unit)


def _already_converted(line: str, start: int, end: int) -> bool:
    # Existing formatter can place </b> between the currency amount and '(약 ...원)'.
    tail = re.sub(r"</?[^>]+>", "", line[end : end + 96])
    if re.match(r"\s*\(약\s+[^)]*원", tail):
        return True

    # Do not reconvert the secondary dollar value inside
    # '(약 132조원 · 98.6십억달러)' generated for a yen amount.
    prefix = line[:start]
    open_pos = prefix.rfind("(")
    close_pos = prefix.rfind(")")
    if open_pos > close_pos:
        inside = re.sub(r"</?[^>]+>", "", prefix[open_pos:])
        if "약" in inside and "원" in inside:
            return True
    return False


def _enforce_krw(body: str) -> str:
    try:
        quote = latest_jpy_krw()
    except Exception as exc:
        raise RuntimeError("원화 환산용 검증 환율 확보 실패 — 미환산 알림 발송을 차단합니다") from exc

    converted_lines: list[str] = []
    for line in body.splitlines():
        matches = list(MONEY_RE.finditer(line))
        for match in reversed(matches):
            if _already_converted(line, match.start(), match.end()):
                continue
            raw_value = match.group("value")
            value = float(raw_value.replace(",", ""))
            unit = match.group("unit")
            won = _won_for(value, unit, quote)
            original = match.group(0)
            replacement = f"{original} (약 {format_krw(won)})"
            line = line[: match.start()] + replacement + line[match.end() :]
        converted_lines.append(line)

    result = "\n".join(converted_lines).rstrip()
    basis_marker = "<b>원화 환산 기준</b>"
    if basis_marker not in result:
        source_label = "미 연준 H.10·FRED" if quote.source == "Fed H.10/FRED" else "검증 환율 API"
        basis = (
            f"{basis_marker}\n"
            f"• 1달러 = <b>{quote.usdkrw:,.2f}원</b> · 100엔 = <b>{quote.krw_per_100_yen:,.2f}원</b>\n"
            f"• 환율 기준일: {html.escape(quote.date)} · 출처: {source_label}\n"
        )
        marker = "\n<b>원문</b>"
        if marker in result:
            result = result.replace(marker, "\n\n" + basis.rstrip() + marker, 1)
        else:
            result += "\n\n" + basis.rstrip()
    return result + "\n"


def _append_buyback_context(body: str) -> str:
    text, error = fetch_text(URL, UA, timeout=15, attempts=2)
    if error or not text:
        record_source_failure(
            lane="japan_reserve_funding_buyback_context",
            source_name="US Treasury long-end buyback",
            source_url=URL,
            error=error or "empty response",
        )
        return body

    plain = " ".join(BeautifulSoup(text, "html.parser").stripped_strings)
    effective = bool(re.search(r"September\s+9,\s+2026", plain, re.I))
    four = bool(re.search(r"(?:at least\s+)?\$?4\s*billion\s+per\s+operation", plain, re.I))
    two = bool(re.search(r"\$?2\s*billion\s+per\s+operation", plain, re.I))
    if not (effective and four):
        return body

    marker = "<b>미 재무부 장기채 바이백 완충</b>"
    if marker in body:
        return body

    block = [
        "",
        marker,
        "• 2026년 9월 9일부터 10~20년·20~30년 명목채 유동성 지원 바이백은 회당 <b>최소 40억달러</b>로 확대.",
    ]
    if two:
        block.append("  └ 기존 최대 20억달러 대비 최소 두 배")
    block += [
        "• <b>해석 주의:</b> 미 재무부 공식 사유는 장기물 시장 유동성 지원이며, 일본의 미국채 매도에 대응한 조치라고 단정하지 않음.",
        f"• <a href=\"{html.escape(URL)}\">미 재무부 장기채 바이백 발표</a>",
    ]
    return body.rstrip() + "\n" + "\n".join(block) + "\n"


def main() -> int:
    if not OUT.exists():
        return 0

    body = OUT.read_text(encoding="utf-8")
    body = _append_buyback_context(body)
    body = _enforce_krw(body)
    OUT.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

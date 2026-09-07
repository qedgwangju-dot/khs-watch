#!/usr/bin/env python3
"""Append official U.S. Treasury long-end buyback context to Japan funding alerts.

This is context, not proof that Treasury increased buybacks because of Japan.
"""
from __future__ import annotations

import html
import pathlib
import re

from bs4 import BeautifulSoup

from khs_source_fetch import fetch_text, record_source_failure

URL = "https://home.treasury.gov/news/press-releases/sb0607"
OUT = pathlib.Path("out/japan_reserve_funding_alert.html")
UA = "Mozilla/5.0 khs-japan-reserve-buyback-context/1.0"


def main() -> int:
    if not OUT.exists():
        return 0
    text, error = fetch_text(URL, UA, timeout=15, attempts=2)
    if error or not text:
        record_source_failure(
            lane="japan_reserve_funding_buyback_context",
            source_name="US Treasury long-end buyback",
            source_url=URL,
            error=error or "empty response",
        )
        return 0

    plain = " ".join(BeautifulSoup(text, "html.parser").stripped_strings)
    effective = bool(re.search(r"September\s+9,\s+2026", plain, re.I))
    four = bool(re.search(r"(?:at least\s+)?\$?4\s*billion\s+per\s+operation", plain, re.I))
    two = bool(re.search(r"\$?2\s*billion\s+per\s+operation", plain, re.I))
    if not (effective and four):
        return 0

    body = OUT.read_text(encoding="utf-8").rstrip()
    marker = "<b>미 재무부 장기채 바이백 완충</b>"
    if marker in body:
        return 0

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
    OUT.write_text(body + "\n" + "\n".join(block) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

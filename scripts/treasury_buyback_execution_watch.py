#!/usr/bin/env python3
"""Execution wrapper for Treasury buyback watcher v2.

Keeps an always-present baseline Treasury signal so official schedule/results changes
can trigger an alert even when the related media reports have aged out of the 2-day RSS window.
Also enforces KRW companion values for foreign-currency amounts shown to the user.
"""
from __future__ import annotations

import re

import treasury_buyback_media_watch_v2 as watcher

_original_news_items = watcher.news_items
_original_build_alert = watcher.build_alert

# Force one refreshed alert after the KRW-display rule changes.
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 7)


def news_items_with_official_baseline() -> list[dict]:
    items = _original_news_items()
    items.append({
        "title": "Treasury official buyback execution baseline",
        "link": watcher.MARKETWATCH_TGA,
        "description": "Treasury general account TGA buyback official execution monitoring baseline",
        "source": "Treasury execution monitor",
        "pubDate": "",
    })
    return items


def _fmt_krw_from_usd(usd: float, fx: float) -> str:
    krw = usd * fx
    if krw >= 1_000_000_000_000:
        return f"약 {krw / 1_000_000_000_000:,.1f}조원"
    if krw >= 100_000_000:
        return f"약 {krw / 100_000_000:,.0f}억원"
    if krw >= 10_000:
        return f"약 {krw / 10_000:,.0f}만원"
    return f"약 {krw:,.0f}원"


def _fmt_usd_krw(usd: float, fx: float) -> str:
    return f"${usd:,.0f}({_fmt_krw_from_usd(usd, fx)})"


def _append_krw_to_unconverted_amounts(text: str, fx: float) -> str:
    """Add KRW to USD amounts that were not already paired with a parenthesized conversion."""
    def repl_jo(match: re.Match[str]) -> str:
        raw = match.group(1).replace(",", "")
        usd = float(raw) * 1_000_000_000_000
        return f"{match.group(1)}조달러({_fmt_krw_from_usd(usd, fx)})"

    def repl_eok(match: re.Match[str]) -> str:
        raw = match.group(1).replace(",", "")
        usd = float(raw) * 100_000_000
        return f"{match.group(1)}억달러({_fmt_krw_from_usd(usd, fx)})"

    def repl_million(match: re.Match[str]) -> str:
        raw = match.group(1).replace(",", "")
        usd = float(raw) * 1_000_000
        return f"{match.group(1)}백만달러({_fmt_krw_from_usd(usd, fx)})"

    def repl_dollar_sign(match: re.Match[str]) -> str:
        raw = match.group(1).replace(",", "")
        usd = float(raw)
        return f"${match.group(1)}({_fmt_krw_from_usd(usd, fx)})"

    # Negative lookahead avoids duplicating amounts already written as 달러(약 ...원).
    text = re.sub(r"([0-9][0-9,]*(?:\.[0-9]+)?)조달러(?!\s*\()", repl_jo, text)
    text = re.sub(r"([0-9][0-9,]*(?:\.[0-9]+)?)억달러(?!\s*\()", repl_eok, text)
    text = re.sub(r"([0-9][0-9,]*(?:\.[0-9]+)?)백만달러(?!\s*\()", repl_million, text)
    text = re.sub(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)(?!\s*\()", repl_dollar_sign, text)
    return text


def build_alert_with_krw(*args, **kwargs):
    title, body, detail = _original_build_alert(*args, **kwargs)
    fx = float(detail.get("fx") or 0)
    if fx <= 0:
        raise RuntimeError("원화 환산용 USD/KRW 환율이 없습니다.")

    # Official buyback results are published in raw dollars. Show those amounts
    # alongside KRW before the ratio interpretation so the scale is immediately visible.
    stats = detail.get("buyback_stats") or {}
    max_amt = stats.get("max")
    accepted = stats.get("accepted")
    offered = stats.get("offered")
    if max_amt and accepted is not None and offered:
        amount_line = (
            f"• 공식 결과 금액: 총 제시액 {_fmt_usd_krw(float(offered), fx)} · "
            f"실제 매입액 {_fmt_usd_krw(float(accepted), fx)} · "
            f"매입상한 {_fmt_usd_krw(float(max_amt), fx)}"
        )
        marker = "• 공식 결과 감지:"
        if marker in body and amount_line not in body:
            body = body.replace(marker, amount_line + "\n" + marker, 1)

    body = _append_krw_to_unconverted_amounts(body, fx)
    detail["krw_display_enforced"] = True
    detail["format_revision"] = watcher.FORMAT_REVISION
    return title, body, detail


watcher.news_items = news_items_with_official_baseline
watcher.build_alert = build_alert_with_krw

if __name__ == "__main__":
    raise SystemExit(watcher.main())

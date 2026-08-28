#!/usr/bin/env python3
"""Operational wrapper for yen_carry_composite_watch.

CFTC migrated the Socrata dataset to API v3 in 2026. To avoid depending on an
app token or a deprecated /resource endpoint, this wrapper reads the official
CFTC Traders in Financial Futures current report page directly and derives the
previous week's leveraged-fund net position from the published change row.
It also normalizes MOF weekly date labels when the legacy CSV arrives with a
Shift-JIS separator decoded imperfectly by the HTTP server.

All monetary JPY amounts exposed in the Telegram body are paired with a KRW
conversion using the latest same-date Federal Reserve H.10 USD/KRW and USD/JPY
observations. If that conversion cannot be verified, the monetary alert is not
allowed to advance state or send.
"""
from __future__ import annotations

import datetime as dt
import html
import pathlib
import re
import sys

import yen_carry_composite_watch as base
from khs_source_fetch import fetch_text
from krw_fx import FRED_USDJPY, FRED_USDKRW, JpyKrwQuote, format_krw, latest_jpy_krw, yen_to_krw

CFTC_TFF_REPORT = "https://www.cftc.gov/dea/futures/financial_lf.htm"
KRW_FAILURE_PATH = pathlib.Path("out/yen_carry_krw_conversion_failed.txt")

_original_parse_mof_week_csv = base.parse_mof_week_csv
_original_build_message = base.build_message


def normalize_mof_week_label(value: str) -> str:
    nums = [int(x) for x in re.findall(r"\d+", value or "")]
    if len(nums) >= 5 and nums[0] >= 2000:
        year, m1, d1, m2, d2 = nums[:5]
        return f"{year:04d}-{m1:02d}-{d1:02d}~{m2:02d}-{d2:02d}"
    return (value or "").strip()


def parse_mof_week_csv(text: str) -> base.MofOutwardFlow:
    result = _original_parse_mof_week_csv(text)
    return base.MofOutwardFlow(
        latest_week=normalize_mof_week_label(result.latest_week),
        previous_week=normalize_mof_week_label(result.previous_week),
        latest_two_week_trillion_yen=result.latest_two_week_trillion_yen,
        previous_two_week_trillion_yen=result.previous_two_week_trillion_yen,
        outward_buying=result.outward_buying,
        outward_accelerating=result.outward_accelerating,
    )


def _ints(text: str) -> list[int]:
    return [int(token.replace(",", "")) for token in re.findall(r"[+-]?\d[\d,]*", text)]


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value.strip(), "%B %d, %Y").date()


def parse_cftc_tff_html(text: str) -> base.CftcPosition:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    plain = plain.replace("\xa0", " ")
    start = re.search(
        r"JAPANESE\s+YEN\s*-\s*CHICAGO\s+MERCANTILE\s+EXCHANGE.*?CFTC\s+Code\s*#?097741",
        plain,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not start:
        raise RuntimeError("CFTC TFF Japanese Yen block not found")
    block = plain[start.start() : start.start() + 7000]

    oi_match = re.search(r"Open\s+Interest\s+is\s*([\d,]+)", block, flags=re.IGNORECASE)
    positions_match = re.search(
        r"Positions\s+((?:[\s,+-]*\d[\d,]*){14})\s+Changes\s+from:",
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    changes_match = re.search(
        r"Changes\s+from:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+Total\s+Change\s+is:\s*[+-]?[\d,]+\s+((?:[\s,+-]*\d[\d,]*){14})\s+Percent",
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not oi_match or not positions_match or not changes_match:
        raise RuntimeError("CFTC TFF Japanese Yen positions/change fields not found")

    positions = _ints(positions_match.group(1))
    changes = _ints(changes_match.group(2))
    if len(positions) != 14 or len(changes) != 14:
        raise RuntimeError(f"CFTC TFF Japanese Yen field count mismatch: positions={len(positions)} changes={len(changes)}")

    leveraged_long = positions[6]
    leveraged_short = positions[7]
    previous_long = leveraged_long - changes[6]
    previous_short = leveraged_short - changes[7]
    net = leveraged_long - leveraged_short
    net_short = max(leveraged_short - leveraged_long, 0)
    previous_net_short = max(previous_short - previous_long, 0)
    previous_date = _parse_date(changes_match.group(1))
    report_date = previous_date + dt.timedelta(days=7)
    open_interest = int(oi_match.group(1).replace(",", ""))

    return base.CftcPosition(
        report_date=report_date.isoformat(),
        open_interest=open_interest,
        leveraged_long=leveraged_long,
        leveraged_short=leveraged_short,
        net=net,
        net_short=net_short,
        net_short_pct_oi=(net_short / open_interest * 100.0) if open_interest else 0.0,
        previous_report_date=previous_date.isoformat(),
        previous_net_short=previous_net_short,
        short_covering=net_short < previous_net_short,
    )


def fetch_cftc(now: dt.datetime) -> base.CftcPosition:
    text, error = fetch_text(
        CFTC_TFF_REPORT,
        base.USER_AGENT,
        timeout=20,
        attempts=2,
        accept="text/html,text/plain,*/*",
    )
    if error or not text:
        raise RuntimeError(error or "empty CFTC TFF report")
    return parse_cftc_tff_html(text)


def enrich_krw_lines(body: str, mof: base.MofOutwardFlow | None, quote: JpyKrwQuote) -> str:
    if mof is None:
        return body

    latest_won = yen_to_krw(mof.latest_two_week_trillion_yen * 1_000_000_000_000.0, quote)
    prior_won = yen_to_krw(mof.previous_two_week_trillion_yen * 1_000_000_000_000.0, quote)
    latest_sign = "+" if mof.latest_two_week_trillion_yen >= 0 else ""
    prior_sign = "+" if mof.previous_two_week_trillion_yen >= 0 else ""
    replacement = (
        f"- 일본 거주자 해외주식+장기채: 최근 2주 {latest_sign}{mof.latest_two_week_trillion_yen:.2f}조엔 "
        f"(약 {format_krw(latest_won)}) / 직전 2주 {prior_sign}{mof.previous_two_week_trillion_yen:.2f}조엔 "
        f"(약 {format_krw(prior_won)}) (순매수 +)"
    )

    lines = body.splitlines()
    converted = False
    output: list[str] = []
    for line in lines:
        if line.startswith("- 일본 거주자 해외주식+장기채:"):
            output.append(replacement)
            converted = True
        else:
            output.append(line)
    if not converted:
        raise RuntimeError("MOF outward-flow monetary line missing; refusing unconverted alert")

    basis = (
        f"- 원화 환산 기준: 1엔={quote.krw_per_yen:.4f}원 / 100엔={quote.krw_per_100_yen:,.2f}원 "
        f"(FRED H.10 동일 기준일 {quote.date}, USD/KRW {quote.usdkrw:,.2f} ÷ USD/JPY {quote.usdjpy:.2f})"
    )
    try:
        source_index = output.index("출처")
    except ValueError:
        source_index = len(output)
    output[source_index:source_index] = [basis, ""]
    if source_index < len(output):
        output.extend([
            f"- FRED USD/KRW: {FRED_USDKRW}",
            f"- FRED USD/JPY: {FRED_USDJPY}",
        ])
    return "\n".join(output)


def build_message(*args, **kwargs):
    title, body, payload = _original_build_message(*args, **kwargs)
    mof = kwargs.get("mof")
    if mof is None:
        return title, body, payload
    try:
        quote = latest_jpy_krw()
        body = enrich_krw_lines(body, mof, quote)
    except Exception as exc:
        KRW_FAILURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        KRW_FAILURE_PATH.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise
    payload["krw_conversion"] = {
        "required": True,
        "date": quote.date,
        "usdkrw": quote.usdkrw,
        "usdjpy": quote.usdjpy,
        "krw_per_yen": quote.krw_per_yen,
        "method": "FRED H.10 same-date DEXKOUS / DEXJPUS",
    }
    return title, body, payload


def install() -> None:
    base.CFTC_TFF_API = CFTC_TFF_REPORT
    base.parse_mof_week_csv = parse_mof_week_csv
    base.fetch_cftc = fetch_cftc
    base.build_message = build_message


install()


def main() -> int:
    if "--finalize" in sys.argv and KRW_FAILURE_PATH.exists():
        print("KRW conversion failed; yen-carry state intentionally not advanced")
        return 1
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Common quantity x unit-price enrichment for the existing Physical-AI alert route.

Whenever a rendered high-signal alert contains a material physical quantity, add a
per-unit price/value view before the total. Use live official product pages where a
clean public price exists; otherwise state that a defensible unit price is not public
instead of inventing one. This is a presentation/enrichment layer only and does not
change the underlying alert trigger or Telegram route.
"""
from __future__ import annotations

import html
import re
import urllib.request

import physical_ai_watch_tesla_order_dedupe as current

base = current.base

QTY_RE = re.compile(
    r"(?<![\d,])(\d{1,3}(?:,\d{3})+|\d+)\s*(대|개|셀|랙|서버|MW|GW|km|킬로미터)",
    re.I,
)

PRICE_PAGES = {
    "microduck": "https://pollen-robotics.com/microduck/",
    "reachy": "https://pollen-robotics.com/reachy-mini/blog/reachy-mini-announcement/",
    "xl330": "https://www.robotis.us/xl/",
}

FALLBACK_USD = {
    "microduck": 399.0,
    "reachy_lite": 399.0,
    "reachy_wireless": 499.0,
    "xl330": 27.49,
}


def _http_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/2.0"})
    with urllib.request.urlopen(req, timeout=7) as r:
        return html.unescape(r.read().decode("utf-8", "ignore"))


def _official_prices() -> tuple[dict[str, float], dict[str, bool]]:
    prices = dict(FALLBACK_USD)
    fresh = {k: False for k in prices}

    try:
        text = _http_text(PRICE_PAGES["microduck"])
        m = re.search(r"(?:Pre-order(?:\s+for)?|price(?:d)?(?:\s+from)?)\s*\$\s*(399(?:\.00)?)", text, re.I)
        if m:
            prices["microduck"] = float(m.group(1))
            fresh["microduck"] = True
    except Exception:
        pass

    try:
        text = _http_text(PRICE_PAGES["reachy"])
        if re.search(r"Lite[^$]{0,180}\$\s*399", text, re.I | re.S):
            prices["reachy_lite"] = 399.0
            fresh["reachy_lite"] = True
        if re.search(r"Wireless[^$]{0,180}\$\s*499", text, re.I | re.S):
            prices["reachy_wireless"] = 499.0
            fresh["reachy_wireless"] = True
    except Exception:
        pass

    try:
        text = _http_text(PRICE_PAGES["xl330"])
        m = re.search(r"XL330-M288-T[\s\S]{0,800}?\$\s*(27\.49)", text, re.I)
        if m:
            prices["xl330"] = float(m.group(1))
            fresh["xl330"] = True
    except Exception:
        pass

    return prices, fresh


def _num(v: str) -> int:
    return int(v.replace(",", ""))


def _fmt_krw_per(value: float) -> str:
    if value >= 100_000_000:
        return f"약 {value / 100_000_000:,.2f}억원"
    if value >= 10_000:
        return f"약 {value / 10_000:,.1f}만원"
    return f"약 {value:,.0f}원"


def _fmt_krw_total(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"약 {value / 1_000_000_000_000:,.2f}조원"
    if value >= 100_000_000:
        return f"약 {value / 100_000_000:,.1f}억원"
    if value >= 10_000:
        return f"약 {value / 10_000:,.1f}만원"
    return f"약 {value:,.0f}원"


def _fmt_usd(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f}십억달러"
    if value >= 1_000_000:
        return f"{value / 1_000_000:,.2f}백만달러"
    if value >= 1_000:
        return f"{value / 1_000:,.1f}천달러"
    return f"{value:,.2f}달러"


def _largest_qty(block: str, unit: str) -> int | None:
    vals = [_num(n) for n, u in QTY_RE.findall(block) if u.lower() == unit.lower()]
    return max(vals) if vals else None


def _qty_summary(block: str) -> str:
    found: list[str] = []
    seen: set[tuple[int, str]] = set()
    for n, unit in QTY_RE.findall(block):
        key = (_num(n), unit.lower())
        if key in seen:
            continue
        seen.add(key)
        found.append(f"{_num(n):,}{unit}")
        if len(found) >= 4:
            break
    return ", ".join(found)


def _microduck_block(block: str, rate: float, prices: dict[str, float], fresh: dict[str, bool]) -> str | None:
    if not re.search(r"마이크로덕|Microduck", block, re.I):
        return None
    qty = _largest_qty(block, "대")
    if not qty:
        return None

    p = prices["microduck"]
    unit_krw = p * rate
    total_usd = qty * p
    total_krw = total_usd * rate
    src_note = "폴렌 로보틱스 공식페이지 현재가" if fresh["microduck"] else "폴렌 로보틱스 공식 예약가 기준"
    lines = [
        "💰 <b>대당·물량 환산</b>",
        f"• <b>완제품 대당</b>  {p:,.0f}달러 → {_fmt_krw_per(unit_krw)}/대 ({src_note})",
        f"• <b>{qty:,}대 완제품 가치</b>  {qty:,}대 × {p:,.0f}달러 = {_fmt_usd(total_usd)} → {_fmt_krw_total(total_krw)}",
    ]

    if re.search(r"XL330|액추에이터|모터", block, re.I):
        motor_count = qty * 15
        xl = prices["xl330"]
        xl_krw = xl * rate
        xl_total_usd = motor_count * xl
        xl_total_krw = xl_total_usd * rate
        xl_note = "로보티즈 미국 공식페이지 현재 소매가" if fresh["xl330"] else "로보티즈 미국 공식 소매가 기준"
        lines.extend([
            f"• <b>액추에이터 물량</b>  15개/대 × {qty:,}대 = {motor_count:,}개",
            f"• <b>XL330-M288-T 개당</b>  {xl:,.2f}달러 → {_fmt_krw_per(xl_krw)}/개 ({xl_note})",
            f"• <b>{motor_count:,}개 소매가 단순환산</b>  {_fmt_usd(xl_total_usd)} → {_fmt_krw_total(xl_total_krw)}",
            "• <b>주의</b>  XL330 소매가 단순환산은 대량 OEM 납품단가·로보티즈 실제 매출이 아닙니다. 완제품 판매가와 비교해 경제적으로 맞지 않으면 실제 OEM 단가는 훨씬 낮다고 봐야 합니다.",
        ])
    return "\n".join(lines)


def _reachy_block(block: str, rate: float, prices: dict[str, float], fresh: dict[str, bool]) -> str | None:
    if not re.search(r"리치\s*미니|Reachy\s*Mini", block, re.I):
        return None
    qty = _largest_qty(block, "대")
    if not qty:
        return None
    lo, hi = prices["reachy_lite"], prices["reachy_wireless"]
    lo_krw, hi_krw = lo * rate, hi * rate
    total_lo, total_hi = qty * lo, qty * hi
    fresh_note = "폴렌 로보틱스 공식페이지 현재가" if fresh["reachy_lite"] and fresh["reachy_wireless"] else "폴렌 로보틱스 공식 공개가 기준"
    return "\n".join([
        "💰 <b>대당·물량 환산</b>",
        f"• <b>완제품 대당</b>  Lite {lo:,.0f}달러→{_fmt_krw_per(lo_krw)}, Wireless {hi:,.0f}달러→{_fmt_krw_per(hi_krw)} ({fresh_note})",
        f"• <b>{qty:,}대 완제품 가치</b>  {_fmt_usd(total_lo)}~{_fmt_usd(total_hi)} → {_fmt_krw_total(total_lo * rate)}~{_fmt_krw_total(total_hi * rate)}",
        "• <b>주의</b>  공개 소비자가 기준이며 대량 공급계약 단가·실제 매출 인식액은 다를 수 있습니다.",
    ])


def _xl330_block(block: str, rate: float, prices: dict[str, float], fresh: dict[str, bool]) -> str | None:
    if not re.search(r"XL330", block, re.I) or re.search(r"마이크로덕|Microduck", block, re.I):
        return None
    qty = _largest_qty(block, "개")
    if not qty:
        return None
    p = prices["xl330"]
    total_usd = qty * p
    note = "로보티즈 미국 공식페이지 현재 소매가" if fresh["xl330"] else "로보티즈 미국 공식 소매가 기준"
    return "\n".join([
        "💰 <b>개당·물량 환산</b>",
        f"• <b>개당</b>  {p:,.2f}달러 → {_fmt_krw_per(p * rate)}/개 ({note})",
        f"• <b>{qty:,}개 소매가 단순환산</b>  {_fmt_usd(total_usd)} → {_fmt_krw_total(total_usd * rate)}",
        "• <b>주의</b>  소매가 기준이며 대량 OEM 단가·실제 공급계약 매출은 별도 확인이 필요합니다.",
    ])


def _unknown_block(block: str) -> str | None:
    summary = _qty_summary(block)
    if not summary:
        return None
    return "\n".join([
        "💰 <b>대당·물량 환산</b>",
        f"• <b>확인 물량</b>  {summary}",
        "• <b>단가</b>  현재 공개·신뢰 자료에서 직접 적용할 단위단가를 확인하지 못해 총액을 임의 추정하지 않습니다.",
        "• <b>후속</b>  공식 단가·계약금액·동일 규격 조달가가 확인되면 단위당 원화와 물량×단가 총액을 함께 계산합니다.",
    ])


def _insert_after_core(block: str, value_block: str) -> str:
    lines = block.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().startswith("💡 <b>핵심</b>"):
            out.append(value_block)
            inserted = True
    if not inserted:
        out.append(value_block)
    return "\n".join(out)


def enrich_quantity_values() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding="utf-8")
    if not QTY_RE.search(text):
        return

    rate, _fresh_fx = current._usdkrw()
    prices, fresh = _official_prices()
    parts = text.split("\n──────────────────\n")
    changed = False
    enriched: list[str] = []
    for block in parts:
        if not QTY_RE.search(block) or "💰 <b>대당·물량 환산</b>" in block or "💰 <b>물량 환산</b>" in block or "💰 <b>개당·물량 환산</b>" in block:
            enriched.append(block)
            continue
        value_block = (
            _microduck_block(block, rate, prices, fresh)
            or _reachy_block(block, rate, prices, fresh)
            or _xl330_block(block, rate, prices, fresh)
            or _unknown_block(block)
        )
        if value_block:
            block = _insert_after_core(block, value_block)
            changed = True
        enriched.append(block)

    if changed:
        base.ALERT_PATH.write_text("\n──────────────────\n".join(enriched).strip(), encoding="utf-8")


if __name__ == "__main__":
    pre_state = base.load_state()
    base.main()
    current.opt.current.fig.legacy.repair_pending_seen(pre_state)
    current.opt._finalize_alert_text()
    current._append_value_estimate()
    enrich_quantity_values()

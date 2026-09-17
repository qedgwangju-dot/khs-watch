#!/usr/bin/env python3
"""Semantic dedupe guard for the existing Tesla Optimus China supply-chain lane.

The same underlying ~5,000-unit procurement/audit event is often rewritten with
some details omitted. Collapse those rewrites into one event while preserving
true progression milestones such as audit pass, supplier nomination, shipment,
or Tesla official confirmation as independent alerts.

For meaningful scale-order alerts, append a user-visible quantity x estimated
unit-price calculation in KRW. The calculation is explicitly a finished-robot
value reference, not the supplier purchase-order value.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request

import physical_ai_watch_tesla_china_guard as opt

base = opt.base

_orig_key = base.key
_orig_load_state = base.load_state

AUDIT_PASS = re.compile(
    r'审厂通过|審廠通過|审核通过|審核通過|通过审核|通過審核|audit\s+(?:passed|approved)|'
    r'passed\s+(?:the\s+)?audit|심사\s*통과|실사\s*통과',
    re.I,
)
SUPPLIER_SELECTED = re.compile(
    r'定点|定點|供应商确定|供應商確定|供应商选定|供應商選定|正式供应商|正式供應商|'
    r'supplier\s+(?:selected|nominated|awarded)|nomination|정식\s*공급업체|공급업체\s*선정|공급사\s*선정',
    re.I,
)
SHIPMENT = re.compile(
    r'开始出货|開始出貨|正式出货|正式出貨|交付|发货|發貨|shipment|shipped|delivery|deliveries|'
    r'출하\s*시작|출하\s*개시|납품\s*시작|납품\s*개시|실제\s*출하',
    re.I,
)

PARENT_KEY = hashlib.sha256(b'tesla-optimus|2026q3|scale-order-5000-and-supplier-audit').hexdigest()
OLD_KEYS = {
    hashlib.sha256(b'tesla-optimus|scale-order-5000|supplier-audit').hexdigest(),
    hashlib.sha256(b'tesla-optimus|scale-order-5000').hexdigest(),
    hashlib.sha256(b'tesla-optimus|supplier-audit').hexdigest(),
}

# Elon Musk's public long-term Optimus price target, used only as a value reference.
# This is not treated as current supplier PO value or current manufacturing cost.
OPTIMUS_TARGET_PRICE_USD = (20_000, 25_000)
FX_FALLBACK_USDKRW = 1380.0


def _is_parent_story(text: str) -> bool:
    if not (opt.TESLA_OPT.search(text) and opt.OPTIMUS.search(text)):
        return False
    scaled_order = bool(opt.SCALE_ORDER.search(text) and opt.ORDER.search(text))
    linked_audit = bool(
        opt.AUDIT.search(text)
        and (opt.SCALE_ORDER.search(text) or opt.TRIAL.search(text) or opt.CN_LOCATIONS.search(text))
    )
    return scaled_order or linked_audit


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    if not _is_parent_story(text):
        return _orig_key(item)

    # True state transitions get new semantic keys. These are deliberately checked
    # before the umbrella 5,000-order/audit event so real progress can alert again.
    if opt.OFFICIAL_CONFIRM.search(text) and opt.SCALE_ORDER.search(text) and opt.ORDER.search(text):
        return hashlib.sha256(b'tesla-optimus|official-confirmation|scale-order-5000').hexdigest()
    if SHIPMENT.search(text):
        return hashlib.sha256(b'tesla-optimus|scale-order-5000|shipment-start').hexdigest()
    if SUPPLIER_SELECTED.search(text):
        return hashlib.sha256(b'tesla-optimus|scale-order-5000|supplier-selected').hexdigest()
    if AUDIT_PASS.search(text):
        return hashlib.sha256(b'tesla-optimus|scale-order-5000|audit-passed').hexdigest()

    return PARENT_KEY


def load_state() -> dict:
    state = _orig_load_state()
    seen = list(state.get('seen', []))
    seen_set = set(seen)
    # Migrate already-delivered variants of the same September 2026 story so the
    # new umbrella key does not generate one more alert merely because code changed.
    if seen_set.intersection(OLD_KEYS) and PARENT_KEY not in seen_set:
        seen.append(PARENT_KEY)
    state['seen'] = seen[-3500:]
    return state


def _usdkrw() -> tuple[float, bool]:
    """Best-effort fresh USD/KRW with safe fallback; never break the alert route."""
    endpoints = [
        (
            'https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?range=1d&interval=1d',
            lambda d: float(d['chart']['result'][0]['meta']['regularMarketPrice']),
        ),
        (
            'https://open.er-api.com/v6/latest/USD',
            lambda d: float(d['rates']['KRW']),
        ),
    ]
    for url, parser in endpoints:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 khs-watch/2.0'})
            with urllib.request.urlopen(req, timeout=6) as r:
                rate = parser(json.loads(r.read().decode('utf-8')))
            if 500.0 < rate < 3000.0:
                return rate, True
        except Exception:
            continue
    return FX_FALLBACK_USDKRW, False


def _krw_eok(value: float) -> str:
    eok = value / 100_000_000
    return f"{eok:,.0f}억원"


def _append_value_estimate() -> None:
    """Insert quantity x target-price value under the matching Optimus alert only."""
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    if '💰 <b>물량 환산</b>' in text:
        return
    if not re.search(r'테슬라옵티머스.*(?:5,000|5000)대|테슬라\s*옵티머스.*(?:5,000|5000)대', text, re.I | re.S):
        return

    rate, fresh = _usdkrw()
    qty = 5_000
    low_usd = qty * OPTIMUS_TARGET_PRICE_USD[0]
    high_usd = qty * OPTIMUS_TARGET_PRICE_USD[1]
    low_krw = low_usd * rate
    high_krw = high_usd * rate
    fx_note = f"1달러={rate:,.2f}원" if fresh else f"환율 조회 실패로 1달러={rate:,.0f}원 가정"
    value_line = (
        f"💰 <b>물량 환산</b>  5,000대 × 장기 목표 판매가 2만~2만5천달러 = "
        f"1억~1억2,500만달러 → 약 {_krw_eok(low_krw)}~{_krw_eok(high_krw)} ({fx_note}). "
        "이는 완제품 장기 목표 판매가 기준 환산이며 실제 공급업체 부품 발주액은 아닙니다."
    )

    lines = text.splitlines()
    out: list[str] = []
    in_target = False
    inserted = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^<b>\d+\.', stripped):
            in_target = bool(
                re.search(r'테슬라옵티머스|테슬라\s*옵티머스', stripped, re.I)
                and re.search(r'(?:5,000|5000)대', stripped)
            )
        out.append(line)
        if in_target and not inserted and stripped.startswith('💡 <b>핵심</b>'):
            out.append(value_line)
            inserted = True
        if stripped == '──────────────────':
            in_target = False

    if inserted:
        base.ALERT_PATH.write_text('\n'.join(out).strip(), encoding='utf-8')


base.key = key
base.load_state = load_state

if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    opt.current.fig.legacy.repair_pending_seen(pre_state)
    opt._finalize_alert_text()
    _append_value_estimate()

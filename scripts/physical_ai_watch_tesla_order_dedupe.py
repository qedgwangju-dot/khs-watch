#!/usr/bin/env python3
"""Semantic dedupe guard for the existing Tesla Optimus China supply-chain lane.

The same underlying ~5,000-unit procurement/audit event is often rewritten with
some details omitted. Collapse those rewrites into one event while preserving
true progression milestones such as audit pass, supplier nomination, shipment,
or Tesla official confirmation as independent alerts.

For meaningful scale-order alerts, append a user-visible quantity x estimated
unit-price calculation in KRW. The calculation separates finished-robot target
selling price from an older research BoM estimate; neither is presented as the
actual supplier purchase-order value.
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

AUDIT_CAMPAIGN = re.compile(
    r'(?:宁波|寧波|상하이|上海|杭州|항저우|厦门|廈門|샤먼).{0,120}'
    r'(?:审厂|審廠|生产审核|生產審核|양산\s*심사|생산\s*심사|供应链|供應鏈|공급망)|'
    r'(?:审厂|審廠|生产审核|生產審核|양산\s*심사|생산\s*심사).{0,120}'
    r'(?:宁波|寧波|上海|杭州|厦门|廈門|상하이|항저우|샤먼)|'
    r'(?:5,?000|5000)\s*(?:台|대).{0,100}(?:订单|訂單|발주|주문|审厂|審廠)',
    re.I | re.S,
)

PARENT_KEY = hashlib.sha256(b'tesla-optimus|2026q3|scale-order-5000-and-supplier-audit').hexdigest()
OLD_KEYS = {
    hashlib.sha256(b'tesla-optimus|scale-order-5000|supplier-audit').hexdigest(),
    hashlib.sha256(b'tesla-optimus|scale-order-5000').hexdigest(),
    hashlib.sha256(b'tesla-optimus|supplier-audit').hexdigest(),
}

# Elon Musk's public long-term Optimus selling-price target.
# Value reference only; not a current supplier PO or current manufacturing cost.
OPTIMUS_TARGET_PRICE_USD = (20_000, 25_000)

# Morgan Stanley Optimus Gen 2 ex-software BoM estimate. This is an older
# component-quote-based reference and is deliberately labelled as such.
OPTIMUS_GEN2_BOM_USD = (50_000, 60_000)
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


def _weekly_units(text: str) -> int | None:
    pats = [
        r'(?:周产|週產|每周生产|每週生產)[^\d]{0,24}(\d{2,5})\s*台',
        r'(\d{2,5})\s*台\s*/?\s*(?:周|週)',
        r'(\d{2,5})\s*(?:units?|robots?)\s*(?:per\s+week|weekly)',
        r'주당\s*(\d{2,5})\s*대',
        r'주간\s*(?:완제품\s*)?(?:생산|목표)[^\d]{0,16}(\d{2,5})\s*대',
    ]
    for pat in pats:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    stage = opt._stage(text)
    if stage == 'app_generation_asset':
        return hashlib.sha256(b'tesla-optimus|gen3-apk-assets|4.60.5-4573').hexdigest()
    if stage == 'home_app_integration':
        return hashlib.sha256(b'tesla-optimus|home-app|charger-integration').hexdigest()
    if stage == 'korea_supplier_scouting':
        return hashlib.sha256(b'tesla-optimus|2026-h1|korea-supplier-scouting').hexdigest()
    if stage == 'factory_structure':
        return hashlib.sha256(b'tesla-optimus|giga-texas|factory-structure').hexdigest()
    if stage == 'factory_tooling':
        return hashlib.sha256(b'tesla-optimus|giga-texas|factory-tooling').hexdigest()
    units = _weekly_units(text)
    if opt.ACTUAL_WEEKLY.search(text):
        return hashlib.sha256(f'tesla-optimus|actual-weekly-production|{units or "unknown"}'.encode()).hexdigest()
    if opt.WEEKLY_TARGET.search(text):
        return hashlib.sha256(f'tesla-optimus|weekly-capacity-target|{units or "unknown"}'.encode()).hexdigest()
    if opt.PRODUCTION_STARTED.search(text):
        return hashlib.sha256(b'tesla-optimus|actual-production-started').hexdigest()
    if opt.NAMED_OPTIMUS_SUPPLIERS.search(text) and opt.NAMED_SUPPLIER_ORDER.search(text) and opt.AUDIT.search(text):
        return hashlib.sha256(b'tesla-optimus|2026-09-21|named-suppliers-orders-audit|tuopu-sanhua-joyson').hexdigest()
    if AUDIT_CAMPAIGN.search(text):
        return hashlib.sha256(b'tesla-optimus|2026-09|supplier-production-audit-campaign').hexdigest()
    if not _is_parent_story(text):
        return _orig_key(item)

    # True state transitions get new semantic keys. These are deliberately checked
    # before the umbrella 5,000-order/audit event so real progress can alert again.
    if opt.AUDIT_STARTED.search(text):
        return hashlib.sha256(b'tesla-optimus|2026-09-17|supplier-production-audit-started').hexdigest()
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
    return f"{value / 100_000_000:,.0f}억원"


def _krw_unit(value: float) -> str:
    # Humanoid unit values are naturally readable in 만원 units.
    return f"{value / 10_000:,.0f}만원"


def _usd_m(value: float) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2g}억달러"
    if value >= 10_000_000:
        return f"{value / 10_000_000:.2g}천만달러"
    return f"{value:,.0f}달러"


def _append_value_estimate() -> None:
    """Insert per-unit detail first, then quantity x price totals."""
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    if '💰 <b>대당·물량 환산</b>' in text:
        return
    if not re.search(r'테슬라옵티머스.*(?:5,000|5000)대|테슬라\s*옵티머스.*(?:5,000|5000)대', text, re.I | re.S):
        return

    rate, fresh = _usdkrw()
    qty = 5_000

    sell_low_usd, sell_high_usd = OPTIMUS_TARGET_PRICE_USD
    bom_low_usd, bom_high_usd = OPTIMUS_GEN2_BOM_USD

    sell_low_unit_krw = sell_low_usd * rate
    sell_high_unit_krw = sell_high_usd * rate
    bom_low_unit_krw = bom_low_usd * rate
    bom_high_unit_krw = bom_high_usd * rate

    sell_low_total_usd = qty * sell_low_usd
    sell_high_total_usd = qty * sell_high_usd
    bom_low_total_usd = qty * bom_low_usd
    bom_high_total_usd = qty * bom_high_usd

    sell_low_total_krw = sell_low_total_usd * rate
    sell_high_total_krw = sell_high_total_usd * rate
    bom_low_total_krw = bom_low_total_usd * rate
    bom_high_total_krw = bom_high_total_usd * rate

    fx_note = f"1달러={rate:,.2f}원" if fresh else f"환율 조회 실패로 1달러={rate:,.0f}원 가정"

    value_lines = [
        '💰 <b>대당·물량 환산</b>',
        (
            f"• <b>장기 목표 판매가</b>  대당 {sell_low_usd/1000:.0f}천~{sell_high_usd/1000:.0f}천달러 "
            f"→ 약 {_krw_unit(sell_low_unit_krw)}~{_krw_unit(sell_high_unit_krw)}/대"
        ),
        (
            f"• <b>5,000대 완제품 가치</b>  {_usd_m(sell_low_total_usd)}~{_usd_m(sell_high_total_usd)} "
            f"→ 약 {_krw_eok(sell_low_total_krw)}~{_krw_eok(sell_high_total_krw)}"
        ),
        (
            f"• <b>참고 하드웨어 원가</b>  Morgan Stanley의 Optimus Gen 2 소프트웨어 제외 BoM 추정은 "
            f"대당 {bom_low_usd/1000:.0f}천~{bom_high_usd/1000:.0f}천달러 "
            f"→ 약 {_krw_unit(bom_low_unit_krw)}~{_krw_unit(bom_high_unit_krw)}/대"
        ),
        (
            f"• <b>이를 5,000대에 단순 적용</b>  {_usd_m(bom_low_total_usd)}~{_usd_m(bom_high_total_usd)} "
            f"→ 약 {_krw_eok(bom_low_total_krw)}~{_krw_eok(bom_high_total_krw)}"
        ),
        (
            f"• <b>환율</b>  {fx_note} · 판매가와 Gen 2 BoM은 참고 기준이며, "
            "현재 Gen 3 실제 원가·공급업체 부품 발주액·테슬라의 5,000대 공식 확정 금액과는 다릅니다."
        ),
    ]

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
            out.extend(value_lines)
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

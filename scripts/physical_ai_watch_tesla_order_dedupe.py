#!/usr/bin/env python3
"""Semantic dedupe guard for the existing Tesla Optimus China supply-chain lane.

The same underlying ~5,000-unit procurement/audit event is often rewritten with
some details omitted. Collapse those rewrites into one event while preserving
true progression milestones such as audit pass, supplier nomination, shipment,
or Tesla official confirmation as independent alerts.
"""
from __future__ import annotations

import hashlib
import re

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


base.key = key
base.load_state = load_state

if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    opt.current.fig.legacy.repair_pending_seen(pre_state)
    opt._finalize_alert_text()

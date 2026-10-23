"""Delivery decisions for the daily US positioning snapshot."""

from datetime import date


def daily_digest_due(state, delivery_date_kst):
    """Allow one scheduled daily digest per Korea calendar date."""
    if isinstance(delivery_date_kst, date):
        target = delivery_date_kst.isoformat()
    else:
        target = date.fromisoformat(str(delivery_date_kst)[:10]).isoformat()
    return not isinstance(state, dict) or state.get("daily_digest_sent_date_kst") != target


def daily_event_label(updates, correction=False):
    """Describe a daily snapshot without calling an unchanged report new."""
    if correction:
        detail = "정정·보강"
    elif updates:
        detail = "신규 변화"
    else:
        return "일일 정기 현황"
    return f"일일 정기 현황 · {detail}"

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


# AAII / Conference Board official monthly retail-crowding overlay. The two
# surveys have different populations and horizons. No trading signal is
# generated from either survey alone; no percentage is inferred from a chart.
import re
from datetime import datetime


def parse_aaii_allocation(text):
    """Parse AAII's dated five-component survey, not the weekly bull/bear poll."""
    month = re.search(r"Asset Allocation Results for\s+([A-Z][a-z]+)\s+(20\d{2})", text)
    if not month:
        raise ValueError("AAII monthly asset-allocation period missing")
    observed = datetime.strptime(month.group(1) + " " + month.group(2), "%B %Y").date()
    section = text[month.end():month.end() + 1800]

    def field(pattern):
        m = re.search(pattern, section, flags=re.I)
        if not m:
            raise ValueError("AAII official survey component missing")
        return float(m.group(1))

    stocks = field(r"\bStocks Total\s+([\d.]+)\s*%")
    stock_funds = field(r"\bStock Funds\s+(?:Image\s+)?([\d.]+)\s*%")
    direct = field(r"\bStocks\s+(?:Image\s+)?([\d.]+)\s*%")
    bonds = field(r"\bBonds Total\s+([\d.]+)\s*%")
    cash = field(r"\bCash\s+(?:Image\s+)?([\d.]+)\s*%")
    if not all(0 <= x <= 100 for x in (stocks, stock_funds, direct, bonds, cash)):
        raise ValueError("AAII percentage outside 0–100")
    if abs((stock_funds + direct) - stocks) > 0.15 or abs((stocks + bonds + cash) - 100) > 0.3:
        raise ValueError("AAII stock components or three-way allocation inconsistent")
    return {
        "period": observed.strftime("%Y-%m"),
        "stocks_pct": stocks, "stock_funds_pct": stock_funds,
        "direct_stock_pct": direct, "bonds_pct": bonds, "cash_pct": cash,
    }


def parse_conference_board_confidence(text):
    """Only public headline/index and qualitative stock expectation; no fake %."""
    m = re.search(r"Updated:\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday),?\s+"
                  r"([A-Z][a-z]+\s+\d{1,2},\s*20\d{2})", text)
    if not m:
        raise ValueError("Conference Board updated release date missing")
    release = datetime.strptime(m.group(1), "%B %d, %Y").date()
    headline = re.search(r"Consumer Confidence Index.{0,120}?"
                         r"(?:rose|increased|fell|declined|decreased) by\s+([\d.]+)"
                         r"\s+points to\s+([\d.]+)", text, re.I | re.S)
    if not headline:
        raise ValueError("Conference Board headline index and monthly move unavailable")
    change_points = float(headline.group(1))
    value = float(headline.group(2))
    if not (1 <= value <= 200) or not (0 <= change_points <= 100):
        raise ValueError("Conference Board index out of bounds")
    exp = re.search(r"Expectations Index.{0,220}?\bto\s+([\d.]+)", text, re.I | re.S)
    if not exp:
        raise ValueError("Conference Board expectations index unavailable")
    expectation_value = float(exp.group(1))
    if not 1 <= expectation_value <= 200:
        raise ValueError("Conference Board expectations index outside plausible range")
    bull_phrase = re.search(r"more consumers(?:\s+in\s+\w+)?\s+expected stock prices"
                            r"\s+to increase rather than decrease", text, re.I)
    bear_phrase = re.search(r"more consumers(?:\s+in\s+\w+)?\s+expected stock prices"
                            r"\s+to decrease rather than increase", text, re.I)
    stock_up_majority = True if bull_phrase else False if bear_phrase else None
    return {
        "period": release.strftime("%Y-%m"), "published_date": release.isoformat(),
        "confidence_index": value, "headline_move_abs_points": change_points,
        "expectations_index": expectation_value,
        "stock_up_vs_down_majority": stock_up_majority,
    }


def evaluate_retail_crowding(previous, aaii, conference, on_date):
    """Silent first baseline; subsequent *new release* may notify once per pair."""
    previous = previous if isinstance(previous, dict) else {}
    observed_date = date.fromisoformat(str(on_date)[:10])
    aaii_day = date.fromisoformat(aaii["period"] + "-01")
    conference_day = date.fromisoformat(conference["published_date"])
    if (not 0 <= (observed_date - aaii_day).days <= 75
            or not 0 <= (observed_date - conference_day).days <= 50):
        raise ValueError("AAII/Conference Board survey is stale or future-dated")
    old_a, old_c = previous.get("aaii") or {}, previous.get("conference") or {}
    if old_a.get("period") and aaii["period"] < old_a["period"]:
        raise ValueError("AAII official period rolled back")
    if old_c.get("period") and conference["period"] < old_c["period"]:
        raise ValueError("Conference Board official period rolled back")
    crowded = aaii["stocks_pct"] >= 70 and aaii["cash_pct"] <= 15
    up = conference["stock_up_vs_down_majority"]
    # Absence of an official numeric stock-expectations table is NOT ATH evidence.
    regime = "동반 높은 주식노출·상승기대" if crowded and up is True else (
        "개인 주식 비중 높음·기대 정밀확인 대기" if crowded else "주식비중 경계 완화")
    pair = aaii["period"] + "|" + conference["period"]
    old_pair = str(previous.get("pair") or "")
    prior_initialized = bool(old_pair and old_a and old_c)
    notify = bool(prior_initialized and pair != old_pair and
                  (crowded and up is True or previous.get("regime") == "동반 높은 주식노출·상승기대"))
    upcoming = {
        "aaii": aaii, "conference": conference, "pair": pair,
        "regime": regime,
    }
    return {"state": upcoming, "alert": notify, "baseline": not prior_initialized,
            "source_period_changed": bool(prior_initialized and pair != old_pair)}

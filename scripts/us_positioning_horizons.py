"""Calendar-month comparisons with explicit observation dates and no gap filling."""

from calendar import monthrange
from datetime import date
from math import isfinite


def months_before(day, months):
    month_index = day.year * 12 + day.month - 1 - months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    return day.replace(year=year, month=month, day=min(day.day, monthrange(year, month)[1]))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _day(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _close_rows(rows):
    result = {}
    for day, close in rows:
        day = _day(day)
        if day in result and result[day] != close:
            raise ValueError(f"Conflicting same-date closes: {day}")
        result[day] = close
    return result


def price_month_windows(end_date, end_close, yahoo_rows, nasdaq_rows):
    """Use calendar cutoffs, cross-check both dated base closes, then calculate.

    The latest official close is already cross-checked by the collector. A missing
    or conflicting older official close leaves that window unavailable.
    """
    end_date = _day(end_date)
    windows = {}
    try:
        yahoo, nasdaq = _close_rows(yahoo_rows), _close_rows(nasdaq_rows)
    except ValueError as exc:
        yahoo = nasdaq = {}
        row_error = str(exc)
    else:
        row_error = None
    for months in (1, 3):
        cutoff = months_before(end_date, months)
        item = {
            "calendar_months": months, "cutoff_date": cutoff.isoformat(),
            "end_date": end_date.isoformat(), "end_close": end_close,
            "basis": "calendar months; latest observed close on or before cutoff",
            "status": "unavailable",
        }
        candidates = [day for day in yahoo if day <= cutoff]
        if row_error:
            item["reason"] = row_error
        elif not _finite(end_close) or end_close <= 0:
            item["reason"] = "Official ending close unavailable"
        elif not candidates:
            item["reason"] = "Yahoo baseline history unavailable"
        else:
            base_date = max(candidates)
            base_yahoo, base_official = yahoo[base_date], nasdaq.get(base_date)
            item.update(base_date=base_date.isoformat(), yahoo_base_close=base_yahoo,
                        nasdaq_base_close=base_official, cutoff_gap_days=(cutoff - base_date).days)
            if (cutoff - base_date).days > 7:
                item["reason"] = "Baseline observation gap exceeds seven calendar days"
            elif not _finite(base_yahoo) or base_yahoo <= 0:
                item["reason"] = "Yahoo baseline close invalid"
            elif not _finite(base_official) or base_official <= 0:
                item["reason"] = "Same-date Nasdaq baseline close unavailable"
            elif abs(base_yahoo - base_official) > 0.10:
                item["reason"] = "Nasdaq/Yahoo baseline close conflict exceeds 0.10 points"
            else:
                item.update(status="verified", base_close=base_official,
                            base_crosscheck_diff=base_official - base_yahoo,
                            return_pct=(end_close / base_official - 1) * 100)
        windows[f"{months}m"] = item
    return windows


def position_month_windows(rows, end_date, current_nq=None):
    """NQ E-mini only: last published weekly observation at/before each cutoff."""
    end_date = _day(end_date)
    dated = {}
    for row in rows:
        day = _day(row["date"])
        if day > end_date:
            continue
        if day in dated and dated[day] != row:
            raise ValueError(f"Conflicting same-date NQ observations: {day}")
        dated[day] = row
    current = dated.get(end_date)
    if current_nq and current:
        for field, key in (("lev_long", "leveraged_long"), ("lev_short", "leveraged_short"), ("oi", "open_interest")):
            if current.get(field) != current_nq.get(key):
                raise ValueError(f"NQ current/history mismatch for {field}")
    windows = {}
    for months in (1, 3):
        cutoff = months_before(end_date, months)
        item = {
            "calendar_months": months, "cutoff_date": cutoff.isoformat(),
            "end_date": end_date.isoformat(), "market": "NASDAQ MINI", "cftc_code": "209742",
            "basis": "CFTC TFF futures-only; latest weekly observation on or before calendar cutoff",
            "status": "unavailable", "actors": {},
        }
        candidates = [day for day in dated if day <= cutoff]
        if not current:
            item["reason"] = "Same-date current NQ observation unavailable"
        elif not candidates:
            item["reason"] = "Historical NQ baseline unavailable"
        else:
            base_date = max(candidates)
            baseline = dated[base_date]
            item.update(base_date=base_date.isoformat(), cutoff_gap_days=(cutoff - base_date).days)
            if (cutoff - base_date).days > 14:
                item["reason"] = "Weekly baseline observation gap exceeds fourteen calendar days"
            else:
                for prefix, label in (("asset", "asset_manager"), ("lev", "leveraged_funds")):
                    fields = [baseline.get(prefix + "_long"), baseline.get(prefix + "_short"),
                              current.get(prefix + "_long"), current.get(prefix + "_short")]
                    if not all(_finite(value) and value >= 0 for value in fields):
                        item["actors"][label] = {"status": "unavailable", "reason": "Long/short fields unavailable"}
                        continue
                    before_long, before_short, after_long, after_short = fields
                    base_net, current_net = before_long - before_short, after_long - after_short
                    item["actors"][label] = {
                        "status": "verified", "base_long": before_long, "base_short": before_short,
                        "end_long": after_long, "end_short": after_short, "base_net": base_net,
                        "end_net": current_net, "net_change": current_net - base_net,
                        "long_change": after_long - before_long, "short_change": after_short - before_short,
                    }
                item["status"] = "verified" if item["actors"].get("leveraged_funds", {}).get("status") == "verified" else "unavailable"
        windows[f"{months}m"] = item
    return windows


def verified_price_return(window, end_date=None, end_close=None):
    """Recheck saved operands before a renderer may use a directional label."""
    if not window or window.get("status") != "verified":
        return None
    try:
        end = _day(window["end_date"])
        months = window["calendar_months"]
        cutoff = months_before(end, months)
        base = _day(window["base_date"])
        official, yahoo, final = [window[key] for key in ("nasdaq_base_close", "yahoo_base_close", "end_close")]
        if months not in (1, 3) or _day(window["cutoff_date"]) != cutoff or not 0 <= (cutoff - base).days <= 7:
            return None
        if not all(_finite(value) and value > 0 for value in (official, yahoo, final)):
            return None
        if abs(official - yahoo) > 0.10 or window.get("base_close") != official:
            return None
        if end_date is not None and end != _day(end_date):
            return None
        if end_close is not None and final != end_close:
            return None
        computed = (final / official - 1) * 100
        reported = window.get("return_pct")
        return computed if _finite(reported) and abs(computed - reported) < 1e-8 else None
    except (KeyError, TypeError, ValueError):
        return None


def verified_position_change(window, actor, end_date=None):
    if not window or window.get("status") != "verified" or window.get("cftc_code") != "209742":
        return None
    values = window.get("actors", {}).get(actor, {})
    if values.get("status") != "verified":
        return None
    try:
        end = _day(window["end_date"])
        cutoff = months_before(end, window["calendar_months"])
        if window["calendar_months"] not in (1, 3) or _day(window["cutoff_date"]) != cutoff:
            return None
        if not 0 <= (cutoff - _day(window["base_date"])).days <= 14:
            return None
        if end_date is not None and end != _day(end_date):
            return None
        operands = [values[key] for key in ("base_long", "base_short", "end_long", "end_short")]
        if not all(_finite(value) and value >= 0 for value in operands):
            return None
        before, after = operands[0] - operands[1], operands[2] - operands[3]
        if values.get("base_net") != before or values.get("end_net") != after or values.get("net_change") != after - before:
            return None
        return after - before
    except (KeyError, TypeError, ValueError):
        return None

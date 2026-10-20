"""Choose configured read-only market supplements for existing alert routes."""
import market_kiwoom_flow as kiwoom
import market_namuh_flow as namuh


def optional_cash(market):
    if namuh.configured():
        try:
            return namuh.current(market)
        except Exception:
            return {"provider": "Namuh", "market": market, "status": "held"}
    return kiwoom.optional_cash(market)


def enrich_snapshot(snapshot, market):
    if namuh.configured():
        return namuh.enrich_snapshot(snapshot, market)
    return kiwoom.enrich_snapshot(snapshot, market)


def cash_lines(block, market, now_ts=None):
    if block and block.get("provider") == "Namuh":
        return namuh.lines(block, market, now_ts)
    return kiwoom.cash_lines(block, market, now_ts)

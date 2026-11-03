"""Offline checks for official-period arithmetic and unavailable-history gates."""

import ast
import datetime as dt
from datetime import date, datetime
import json
import math
from pathlib import Path
import re
import unittest

from bs4 import BeautifulSoup
from market_time_windows import select_monthly_anchors, subtract_calendar_months
from kofia_liquidity_source_guard import month_horizons, SIDS


def us_functions(*names):
    tree = ast.parse(Path("scripts/us_fund_flow_watch.py").read_text(encoding="utf-8"))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(selected) == len(names)
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    scope = {
        "date": date, "datetime": datetime, "math": math, "re": re,
        "BeautifulSoup": BeautifulSoup,
        "clean_text": lambda html: " ".join(
            BeautifulSoup(html, "html.parser").get_text(" ", strip=True).split()
        ),
        "parse_num": lambda value: float(str(value).replace(",", "")),
        "subtract_calendar_months": subtract_calendar_months,
    }
    exec(compile(module, "scripts/us_fund_flow_watch.py", "exec"), scope)
    return scope


def etf_monthly_function():
    tree = ast.parse(Path("scripts/treasury_etf_flow_watch.py").read_text(encoding="utf-8"))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "cumulative_monthly_flows"]
    assert len(selected) == 1
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    scope = {"dt": dt, "math": math, "select_monthly_anchors": select_monthly_anchors}
    exec(compile(module, "scripts/treasury_etf_flow_watch.py", "exec"), scope)
    return scope["cumulative_monthly_flows"]


class FundHorizonMath(unittest.TestCase):
    def test_kofia_calendar_month_balance_deltas_use_common_official_anchor(self):
        series = {
            SIDS["deposit"]: [
                {"TMPV1": "20261102", "TMPV2": "90460000"},
                {"TMPV1": "20261002", "TMPV2": "88000000"},
                {"TMPV1": "20260731", "TMPV2": "86000000"},
            ],
            SIDS["credit"]: [
                {"TMPV1": "20261102", "TMPV2": "29220000"},
                {"TMPV1": "20261002", "TMPV2": "30000000"},
                {"TMPV1": "20260731", "TMPV2": "31000000"},
            ],
        }
        point = {}
        for anchor, mmf, cma in (
            ("20261002", "260000000", "100000000"),
            ("20260731", "250000000", "99000000"),
        ):
            point[SIDS["mmf"], anchor] = [{"TMPV1": "합계", "TMPV2": mmf}]
            point[SIDS["cma"], anchor] = [{"TMPV1": "합계", "TMPV8": cma}]
        current = {key: {"value": value} for key, value in {
            "deposit": 90460000, "mmf": 272710000,
            "cma": 102130000, "credit": 29220000,
        }.items()}
        windows = month_horizons("20261102", series, point, current, set(), [])
        self.assertEqual(windows["m1"]["anchor_date"], "20261002")
        self.assertEqual(windows["m1"]["changes"]["mmf"]["delta"], 12710000)
        self.assertEqual(windows["m3"]["target_date"], "20260802")
        self.assertEqual(windows["m3"]["anchor_date"], "20260731")
        self.assertEqual(windows["m3"]["changes"]["credit"]["delta"], -1780000)

    def test_ici_domestic_one_month_uses_each_official_week_once(self):
        scope = us_functions("_ici_weekly_history", "_ici_weekly_flow_horizon")
        # Values and dates are from ICI's October 28, 2026 combined release,
        # whose October 14 value includes unusual collective-trust activity.
        page = """<table><tr><th></th><th>10/21/2026</th><th>10/14/2026</th>
          <th>10/7/2026</th><th>9/30/2026</th><th>9/23/2026</th></tr>
          <tr><td>Domestic</td><td>7,090</td><td>-479,390</td>
          <td>-18,073</td><td>-7,282</td><td>5,696</td></tr></table>"""
        rows = scope["_ici_weekly_history"](page, ("domestic",))["domestic"]
        weekly = [{"date": row["date"], "value": row["value"] / 1000} for row in rows]
        one = scope["_ici_weekly_flow_horizon"](weekly, date(2026, 10, 21), 1)
        three = scope["_ici_weekly_flow_horizon"](weekly, date(2026, 10, 21), 3)
        self.assertEqual(one["observation_count"], 5)
        self.assertAlmostEqual(one["value_bn"], -491.959)
        self.assertIsNone(three["value_bn"])
        self.assertEqual(three["reason"], "weekly_history_does_not_cover_target_window")

    def test_ici_collective_trust_caveat_stays_with_affected_month(self):
        scope = us_functions("_ici_collective_trust_note", "_monthly_horizon_snapshot")
        weekly = [{"date": date(2026, 10, 14), "value": -479.390}]
        official_text = (
            "The outflows from domestic equity mutual funds for the week ending "
            "October 14 were primarily driven by activity in collective investment trusts, "
            "rather than by redemptions from individual investors."
        )
        note_week = scope["_ici_collective_trust_note"](official_text, weekly)
        self.assertEqual(note_week, "2026-10-14")
        self.assertIsNone(scope["_ici_collective_trust_note"]("", weekly))
        scope["_horizon_window_text"] = lambda *args, **kwargs: "comparison"
        ici = {"metrics": {
            "domestic_collective_trust_note_week": note_week,
            "domestic_flow_horizons": {
                "m1": {"value_bn": -491.959, "start_week_ended": "2026-09-23",
                       "end_week_ended": "2026-10-21"},
                "m3": {"value_bn": None},
            },
        }}
        lines = scope["_monthly_horizon_snapshot"](
            ici, None, None, None, None, None, None, None, 1341.0
        )
        self.assertTrue(any("집합투자신탁 활동" in line for line in lines))
        ici["metrics"]["domestic_flow_horizons"]["m1"]["start_week_ended"] = "2026-10-21"
        lines = scope["_monthly_horizon_snapshot"](
            ici, None, None, None, None, None, None, None, 1341.0
        )
        self.assertFalse(any("집합투자신탁 활동" in line for line in lines))

    def test_ici_mmf_balance_keeps_billion_dollar_units(self):
        scope = us_functions("_ici_weekly_history", "_ici_balance_change_horizon",
                             "parse_ici_mmf")
        page = """<p>Total money market fund assets decreased by $43.29 billion
          to $7.90 trillion for the week ended Wednesday, October 28</p>
          <table><tr><th></th><th>10/28/2026</th><th>10/21/2026</th>
          <th>10/14/2026</th><th>10/7/2026</th><th>9/30/2026</th>
          <th>9/23/2026</th></tr><tr><td>Total</td><td>7,901.28</td>
          <td>7,944.57</td><td>7,923.08</td><td>7,850.00</td>
          <td>7,825.00</td><td>7,800.00</td></tr></table>"""
        scope.update({
            "browser_html": lambda url: page,
            "ICI_MMF": "https://www.ici.org/research/stats/mmf",
            "_ici_table_rows": lambda html, labels: (
                date(2026, 10, 28),
                {"total": {"cells": ["Total", "7901.28", "7944.57", "-43.29", "7923.08"]}},
            ),
            "_ici_period_from_prose": lambda text: date(2026, 10, 28),
            "_ici_published_date": lambda text: "October 29, 2026",
            "semantic_fingerprint": lambda value: "offline",
        })
        parsed = scope["parse_ici_mmf"]()
        self.assertEqual(parsed["metrics"]["assets_bn"], 7901.28)
        one = parsed["metrics"]["asset_balance_horizons"]["m1"]
        self.assertEqual(one["anchor_date"], "2026-09-23")
        self.assertAlmostEqual(one["change_bn"], 101.28)
        self.assertIsNone(parsed["metrics"]["asset_balance_horizons"]["m3"]["change_bn"])

    def test_etf_one_month_estimate_requires_daily_history(self):
        cumulative_monthly_flows = etf_monthly_function()
        source = "https://www.ishares.com/us/products/example"
        history = []
        for observed, flow in (
            ("2026-10-02", None), ("2026-10-09", 10_000_000),
            ("2026-10-16", 20_000_000), ("2026-10-23", -5_000_000),
            ("2026-10-30", 5_000_000), ("2026-11-02", 0),
        ):
            history.append({
                "ticker": "SHY", "source": source,
                "date": observed, "nav_date": observed, "shares_date": observed,
                "nav": 80.0, "shares": 300_000_000, "flow_usd": flow,
            })
        windows = cumulative_monthly_flows(history, "2026-11-02")
        self.assertEqual(windows[1]["value_usd"], 30_000_000)
        self.assertIsNone(windows[3]["value_usd"])
        broken = [dict(row) for row in history]
        broken[3]["flow_usd"] = None
        self.assertIsNone(cumulative_monthly_flows(broken, "2026-11-02")[1]["value_usd"])


if __name__ == "__main__":
    unittest.main()

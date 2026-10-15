"""Execute changed collectors against frozen source data, with HTTP forbidden."""
import ast
import copy
import csv
import hashlib
import json
import re
import sys
import unittest
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

try:
    import pandas as pd
    from bs4 import BeautifulSoup
except ImportError:
    pd = BeautifulSoup = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from us_positioning_horizons import months_before, price_month_windows, position_month_windows


def fixture():
    return json.loads((ROOT / "tests/fixtures/us_positioning_month_horizons_20261015.json").read_text(encoding="utf-8"))


def functions(names, env):
    tree = ast.parse((ROOT / "scripts/us_positioning_watch.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "actual-collector", "exec"), env)
    return env


@unittest.skipUnless(pd is not None and BeautifulSoup is not None, "collector parser dependencies are installed in CI")
class CollectorParserTests(unittest.TestCase):
    def test_real_sox_collector_keeps_old_official_baselines_when_current_history_row_is_delayed(self):
        saved = fixture()
        rows = saved["yahoo_rows"] + [["2026-10-15", 99999.0]]
        yahoo = {"chart": {"result": [{
            "meta": {"symbol": "^SOX"},
            "timestamp": [int(datetime.fromisoformat(day).replace(hour=16, tzinfo=ZoneInfo("America/New_York")).timestamp()) for day, _ in rows],
            "indicators": {"quote": [{"close": [close for _, close in rows]}]},
        }]}}
        nasdaq = {"data": {"symbol": "SOX", "tradesTable": {"rows": [
            {"date": date.fromisoformat(day).strftime("%m/%d/%Y"), "close": f"{close:,.2f}"}
            for day, close in saved["nasdaq_rows"]
        ]}}}
        queried = []

        def get(url, timeout=35):
            queried.append(url)
            if "finance.yahoo.com" in url:
                self.assertIn("range=6mo", url)
                return SimpleNamespace(json=lambda: yahoo)
            if "api.nasdaq.com" in url:
                params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                self.assertLessEqual(params["fromdate"][0], "2026-07-14")
                self.assertEqual(params["limit"], ["200"])
                return SimpleNamespace(json=lambda: nasdaq)
            if url == "https://indexes.nasdaq.com/Index/History/SOX":
                return SimpleNamespace(text="DATA AS OF 10/14/2026 11,684.38 -524.41 -4.30%")
            raise AssertionError("Unexpected source call: " + url)

        env = functions({"parse_num", "fp", "_nasdaq_sox_historical", "parse_sox"}, {
            "get": get, "re": re, "json": json, "hashlib": hashlib, "urllib": urllib,
            "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
            "BeautifulSoup": BeautifulSoup, "NY": ZoneInfo("America/New_York"),
            "months_before": months_before, "price_month_windows": price_month_windows,
            "_expected_completed_us_session": lambda: date(2026, 10, 14),
            "SOX_YAHOO": "https://query1.finance.yahoo.com/v8/finance/chart/%5ESOX?range=6mo&interval=1d",
            "SOX_NASDAQ_HIST_API": "https://api.nasdaq.com/api/quote/SOX/historical",
            "SOX": "https://indexes.nasdaq.com/Index/History/SOX", "SOX_OVERVIEW": "unused", "SOX_OVERVIEW_FALLBACK": "unused",
        })
        result = env["parse_sox"]()
        self.assertEqual(result["period"], "10/14/2026")
        self.assertEqual(result["metrics"]["value"], 11684.38)
        self.assertEqual(result["metrics"]["month_windows"], saved["expected_price_windows"])
        self.assertEqual(len(queried), 3)

    def cftc_rows(self):
        # Older synthetic rows supply the existing 3Y/10Y sample gates. Every
        # operand used for the new 1M/3M comparisons is an actual saved CFTC row.
        actual = {row["date"]: row for row in fixture()["nq_rows"]}
        result = []
        current = date(2016, 10, 11)
        while current <= date(2026, 10, 6):
            value = actual.get(current.isoformat(), {
                "date": current.isoformat(), "oi": 200000,
                "asset_long": 80000, "asset_short": 20000, "lev_long": 40000, "lev_short": 70000,
            })
            result.append(value)
            current += timedelta(days=7)
        return result

    def cftc_environment(self):
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 15, tzinfo=timezone.utc).astimezone(tz)
        env = functions({"_socrata_nq_history_frame", "cftc_nq_history_3y"}, {
            "pd": pd, "datetime": FrozenDatetime, "timezone": timezone, "BytesIO": BytesIO,
            "CFTC_HISTORY_TEMPLATE": "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip",
            "CFTC_HISTORY_INDEX": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm",
            "NQ_CFTC_CODE": "209742", "position_month_windows": position_month_windows,
        })
        return env

    def public_rows(self):
        return [{
            "report_date_as_yyyy_mm_dd": row["date"] + "T00:00:00.000",
            "open_interest_all": str(row["oi"]), "lev_money_positions_long": str(row["lev_long"]),
            "lev_money_positions_short": str(row["lev_short"]), "asset_mgr_positions_long": str(row["asset_long"]),
            "asset_mgr_positions_short": str(row["asset_short"]),
        } for row in self.cftc_rows()]

    def test_real_cftc_public_reporting_fallback_preserves_asset_fields_and_monthly_scope(self):
        env = self.cftc_environment()
        env["get"] = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fixture annual source unavailable"))
        env["_socrata_rows"] = lambda *args, **kwargs: self.public_rows()
        result = env["cftc_nq_history_3y"]({"open_interest": 283586, "leveraged_long": 51349, "leveraged_short": 70561}, "October 6, 2026")
        self.assertEqual(result["month_windows"], fixture()["expected_position_windows"])
        self.assertEqual(result["leveraged_net_4w_change"], 12660)

    def test_real_cftc_annual_csv_path_has_the_same_monthly_values(self):
        env = self.cftc_environment()
        rows = self.cftc_rows()

        def get(url, timeout=35):
            year = int(re.search(r"(\d{4})\.zip$", url).group(1))
            stream = StringIO()
            writer = csv.writer(stream)
            writer.writerow(["CFTC_Contract_Market_Code", "Report_Date_as_YYYY-MM-DD", "Open_Interest_All", "Lev_Money_Positions_Long_All", "Lev_Money_Positions_Short_All", "Asset_Mgr_Positions_Long_All", "Asset_Mgr_Positions_Short_All"])
            for row in rows:
                if row["date"].startswith(str(year)):
                    writer.writerow(["209742", row["date"], row["oi"], row["lev_long"], row["lev_short"], row["asset_long"], row["asset_short"]])
            archive = BytesIO()
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("FinFutYY.txt", stream.getvalue())
            return SimpleNamespace(content=archive.getvalue())

        env["get"] = get
        result = env["cftc_nq_history_3y"]({"open_interest": 283586, "leveraged_long": 51349, "leveraged_short": 70561}, "October 6, 2026")
        self.assertEqual(result["month_windows"], fixture()["expected_position_windows"])

    def test_missing_asset_field_does_not_drop_valid_leveraged_fund_rows_in_dataframe(self):
        env = self.cftc_environment()
        rows = self.public_rows()
        for row in rows:row.pop("asset_mgr_positions_long")
        env["_socrata_rows"] = lambda *args, **kwargs: rows
        frame = env["_socrata_nq_history_frame"]()
        self.assertEqual(len(frame), len(rows))
        self.assertTrue(frame["Asset_Mgr_Positions_Long_All"].isna().all())


if __name__ == "__main__":
    unittest.main()

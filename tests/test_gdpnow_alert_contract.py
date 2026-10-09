#!/usr/bin/env python3
"""Offline contracts for GDPNow rate alerts, data validation and outage detection."""
import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
import gdpnow_long_rates_watch as watch
import gdpnow_long_rates_reformat as formatter
import gdpnow_watch_health as health

SERIES=[
    "GDPNOW","PCECONTRIBNOW","EQUIPCONTRIBNOW","IPPCONTRIBNOW",
    "STRUCTCONTRIBNOW","RESCONTRIBNOW","GOVCONTRIBNOW",
    "CHNGNETEXPORTSCONTRIBNOW","CHNGNETINVENTCONTRIBNOW",
]

class WatchContractTests(unittest.TestCase):
    def row(self, date, gdp, cipi, pce=2., equipment=1., ipp=.4, nonres=.2, residential=-.1, govt=.3, net_exports=-.6):
        return watch.GdpRow(date,"test",gdp,pce,equipment,ipp,nonres,residential,govt,net_exports,cipi)

    def test_net_growth_boost_increases_rate_pressure(self):
        a=self.row("2026-10-01",3.,.5,pce=2,equipment=.4)
        b=self.row("2026-10-08",4.,.5,pce=2.8,equipment=.7)
        label, _, reasons=formatter.rate_signal(b,a)
        self.assertIn("상승",label)
        self.assertTrue(reasons)

    def test_weak_private_demand_lowers_rate_pressure(self):
        a=self.row("2026-10-01",4.,.5,pce=2.6,equipment=.9)
        b=self.row("2026-10-08",3.,.5,pce=1.6,equipment=.3)
        label, _, _=formatter.rate_signal(b,a)
        self.assertIn("하락",label)

    def test_missing_private_data_must_not_be_certain(self):
        a=self.row("2026-10-01",4.,1.,pce=None,equipment=None,ipp=None,nonres=None,residential=None)
        b=self.row("2026-10-08",3.,1.,pce=None,equipment=None,ipp=None,nonres=None,residential=None)
        label, _, _=formatter.rate_signal(b,a)
        self.assertNotIn("압력 강",label)

    def test_empty_history_neutral(self):
        label,_,_=formatter.rate_signal(self.row("2026-10-08",3.,1.),None)
        self.assertIn("유보",label)

    def test_fred_component_crosscheck_and_date(self):
        # Synthetic complete official-via-FRED data with exact component sum 3.6.
        vals={"GDPNOW":3.6,"PCECONTRIBNOW":2.0,"EQUIPCONTRIBNOW":.6,
              "IPPCONTRIBNOW":.3,"STRUCTCONTRIBNOW":.1,"RESCONTRIBNOW":-.1,
              "GOVCONTRIBNOW":.2,"CHNGNETEXPORTSCONTRIBNOW":-.9,
              "CHNGNETINVENTCONTRIBNOW":1.4}
        self.assertAlmostEqual(sum(v for k,v in vals.items() if k!="GDPNOW"),3.6)
        head="observation_date,"+",".join(SERIES)+"\n"
        data="2026-07-01,"+",".join(str(vals[x]) for x in SERIES)+"\n"
        page="<p>Updated: Oct 8, 2026 11:02 AM CDT</p>"
        def fake_get(url,timeout=30):
            return (page if "/series/GDPNOW" in url else head+data).encode("utf-8")
        with patch.object(watch,"http_get",side_effect=fake_get),patch.object(watch,"load_state",return_value={}):
            row=watch.fetch_contrib_rows_fred()[-1]
        self.assertAlmostEqual(row.gdp,3.6)
        self.assertEqual(row.date,"2026-10-08")
        self.assertAlmostEqual(row.cipi,1.4)

    def test_inconsistent_component_vintages_refused(self):
        values=["3.6","2.0",".6",".3",".1","-.1",".2","-.9",".1"]
        txt="observation_date,"+",".join(SERIES)+"\n"+"2026-07-01,"+",".join(values)+"\n"
        with patch.object(watch,"http_get",return_value=txt.encode()),patch.object(watch,"load_state",return_value={}):
            with self.assertRaisesRegex(RuntimeError,"reconciliation"):
                watch.fetch_contrib_rows_fred()

    def test_health_no_spam_same_day(self):
        with tempfile.TemporaryDirectory() as t:
            state=pathlib.Path(t)/"prior.json"
            p=pathlib.Path(t)/"pending.json"
            with patch.object(health,"STATE",state),patch.object(health,"PENDING",p),patch.dict("os.environ",{"SOURCE_OUTCOME":"failure","SEND_OUTCOME":"skipped"}),patch.object(health,"send_message",return_value=981) as send:
                self.assertEqual(health.main(),0)
                first=json.loads(p.read_text(encoding="utf-8"))
                self.assertTrue(first["failing"])
                state.write_text(json.dumps(first),encoding="utf-8")
                self.assertEqual(health.main(),0)
                self.assertEqual(send.call_count,1)

if __name__=="__main__":
    unittest.main()

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
import gdpnow_intraday_rate_reaction as intraday

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
        # Use a rolling fixture date. Historical canned dates must not cause
        # an otherwise healthy production pipeline to fail its preflight tests.
        today=dt.datetime.now(watch.KST).date()
        qmonth=((today.month-1)//3)*3+1
        quarter_date=f"{today.year}-{qmonth:02d}-01"
        data=quarter_date+","+",".join(str(vals[x]) for x in SERIES)+"\n"
        page=f"<p>Updated: {today.strftime('%b')} {today.day}, {today.year} 11:02 AM CDT</p>"
        def fake_get(url,timeout=30):
            return (page if "/series/GDPNOW" in url else head+data).encode("utf-8")
        with patch.object(watch,"http_get",side_effect=fake_get),patch.object(watch,"load_state",return_value={}):
            row=watch.fetch_contrib_rows_fred()[-1]
        self.assertAlmostEqual(row.gdp,3.6)
        self.assertEqual(row.date,today.isoformat())
        self.assertEqual(row.quarter,f"{today.year}-Q{(qmonth-1)//3+1}")
        self.assertAlmostEqual(row.cipi,1.4)

    def test_stale_fred_timestamp_is_rejected_as_a_separate_test(self):
        # Verify the REAL staleness guard with a deliberately old fixture,
        # rather than allowing the normal success fixture to age and break CI.
        old_date=dt.datetime.now(watch.KST).date()-dt.timedelta(days=20)
        qmonth=((old_date.month-1)//3)*3+1
        quarter_date=f"{old_date.year}-{qmonth:02d}-01"
        values=["3.6","2.0",".6",".3",".1","-.1",".2","-.9","1.4"]
        csv="observation_date,"+",".join(SERIES)+"\n"+quarter_date+","+",".join(values)+"\n"
        page=f"<p>Updated: {old_date.strftime('%b')} {old_date.day}, {old_date.year} 11:02 AM CDT</p>"
        def fake_get(url,timeout=30):
            return (page if "/series/GDPNOW" in url else csv).encode("utf-8")
        with patch.object(watch,"http_get",side_effect=fake_get),patch.object(watch,"load_state",return_value={}):
            with self.assertRaisesRegex(RuntimeError,"stale"):
                watch.fetch_contrib_rows_fred()

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


    def test_same_gdpnow_headline_with_changed_consumption_not_repeated(self):
        old=self.row("2026-10-20",3.50,1.90,pce=2.0)
        state={"observation_key":"2026-10-20|3.5000|1.9000",
               "latest":old.__dict__}
        self.assertTrue(watch.equivalent_gdpnow_observation(
            state,old,formatter.private_final_contribution(old)))
        changed=self.row("2026-10-20",3.50,1.90,pce=2.25)
        self.assertFalse(watch.equivalent_gdpnow_observation(
            state,changed,formatter.private_final_contribution(changed)))
        # Once the component update has been sent and persisted, a 15-minute
        # scheduled recheck must not re-send the same observation.
        updated={"observation_key":state["observation_key"],"latest":changed.__dict__}
        self.assertTrue(watch.equivalent_gdpnow_observation(
            updated,changed,formatter.private_final_contribution(changed)))

    def test_source_name_change_does_not_trigger_false_alert(self):
        row=self.row("2026-10-20",3.50,1.90)
        state={"observation_key":"2026-10-20|3.5000|1.9000|legacy source",
               "latest":row.__dict__}
        rerouted=self.row("2026-10-20",3.50,1.90)
        rerouted.release="FRED restored"
        self.assertTrue(watch.equivalent_gdpnow_observation(
            state,rerouted,formatter.private_final_contribution(rerouted)))

    def test_health_alert_identifies_preflight_failure_not_atlanta_data(self):
        with tempfile.TemporaryDirectory() as t:
            state=pathlib.Path(t)/"prior.json"; pending=pathlib.Path(t)/"pending.json"
            env={"VALIDATION_OUTCOME":"failure","SOURCE_OUTCOME":"skipped",
                 "HAS_ALERT":"no","SEND_OUTCOME":"skipped"}
            with patch.object(health,"STATE",state),patch.object(health,"PENDING",pending),patch.dict("os.environ",env),patch.object(health,"send_message",return_value=541) as send:
                self.assertEqual(health.main(),0)
                self.assertEqual(send.call_count,1)
                self.assertIn("자동 회귀검증 실패",send.call_args.args[0])
                self.assertNotIn("상태: GDPNow 공식 자료 조회 단계 실패",send.call_args.args[0])
                self.assertEqual(json.loads(pending.read_text())["last_validation_outcome"],"failure")

    def test_quarter_rollover_does_not_create_false_rate_pressure(self):
        old=self.row("2026-10-28",3.6,1.8,pce=2.7)
        new=self.row("2026-10-29",1.2,0.3,pce=0.8)
        old.quarter="2026-Q3"; new.quarter="2026-Q4"
        label, thesis, _=formatter.rate_signal(new, old)
        self.assertIn("분기 전환",label)
        self.assertIn("서로 다른 경제기간",thesis)
        self.assertNotIn("하락 압력 강",label)

    def test_same_quarter_change_is_still_classified(self):
        old=self.row("2026-10-15",3.2,1.7,pce=2.2)
        new=self.row("2026-10-20",3.7,1.7,pce=2.9)
        old.quarter=new.quarter="2026-Q3"
        label, _, _=formatter.rate_signal(new, old)
        self.assertIn("상승",label)

    def test_yield_units_cboe_and_yahoo_normalized(self):
        self.assertAlmostEqual(intraday.normalize_yahoo_yield(52.94), 5.294)
        self.assertAlmostEqual(intraday.normalize_yahoo_yield(5.294), 5.294)
        with self.assertRaises(ValueError):
            intraday.normalize_yahoo_yield(0.0)
        with self.assertRaises(ValueError):
            intraday.normalize_yahoo_yield(-2.)

    def test_event_quotes_cannot_use_two_minutes_later(self):
        base=dt.datetime(2026,10,8,16,2,tzinfo=dt.timezone.utc)
        points=[(base+dt.timedelta(minutes=3),5.34),
                (base+dt.timedelta(minutes=1),5.31)]
        self.assertIsNone(intraday.point_nearest(points,base,max_gap_min=0))
        self.assertAlmostEqual(intraday.point_nearest(points,base,max_gap_min=1)[1],5.31)

    def test_health_when_alert_exists_and_sender_skipped_is_failure(self):
        with tempfile.TemporaryDirectory() as t:
            state=pathlib.Path(t)/"prior.json"; p=pathlib.Path(t)/"pending.json"
            env={"SOURCE_OUTCOME":"success","HAS_ALERT":"yes",
                "EVENT_OUTCOME":"success","FORMAT_OUTCOME":"success",
                "ENRICH_OUTCOME":"success","ROUTE_OUTCOME":"success",
                "SEND_OUTCOME":"skipped"}
            with patch.object(health,"STATE",state),patch.object(health,"PENDING",p),patch.dict("os.environ",env),patch.object(health,"send_message",return_value=999):
                self.assertEqual(health.main(),0)
                self.assertTrue(json.loads(p.read_text())["failing"])

    def test_health_nominal_poll_does_not_commit_churn(self):
        with tempfile.TemporaryDirectory() as t:
            state=pathlib.Path(t)/"prior.json"; p=pathlib.Path(t)/"pending.json"
            state.write_text('{"failing":false}')
            env={"SOURCE_OUTCOME":"success","HAS_ALERT":"no","SEND_OUTCOME":"skipped"}
            with patch.object(health,"STATE",state),patch.object(health,"PENDING",p),patch.dict("os.environ",env),patch.object(health,"send_message") as sender:
                self.assertEqual(health.main(),0)
                self.assertFalse(p.exists())
                sender.assert_not_called()

if __name__=="__main__":
    unittest.main()

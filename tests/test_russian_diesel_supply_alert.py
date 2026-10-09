import datetime as dt
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import russian_diesel_supply_alert as WATCH

UTC=dt.timezone.utc

class RussianDieselWatchTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,10,1,0,tzinfo=UTC)

    def test_official_parser_matches_gl135_not_gl134(self):
        html="""<html><body>10/09/2026 Issuance of Russia-related General License
        Office of Foreign Assets Control is issuing Russia-related General License 135,
        Authorizing Transactions Related to the Sale, Delivery, Offloading, and Importation
        of Diesel Fuel of Russian Federation Origin.</body></html>"""
        row=WATCH.official_item(html,self.now)
        self.assertTrue(row["official"])
        self.assertEqual(row["url"],WATCH.OFAC_URL)
        for bad in (html.replace("135","134"),html.replace("10/09/2026","10/08/2026"),
                    html.replace("Diesel Fuel","Crude Oil")):
            with self.assertRaises(ValueError):
                WATCH.official_item(bad,self.now)

    def test_distinguishes_promise_from_actual_cargo(self):
        self.assertTrue(WATCH.policy_headline("Trump says Russia will immediately supply 300,000 tons of diesel"))
        self.assertFalse(WATCH.actual_shipment("Trump says Russia will immediately supply 300,000 tons of diesel"))
        self.assertFalse(WATCH.actual_shipment("Russia agrees diesel will be loaded next week"))
        self.assertFalse(WATCH.policy_headline("Iran exports diesel"))
        self.assertTrue(WATCH.actual_shipment("Russian diesel cargoes loaded on tankers, Reuters reports"))

    def test_same_reuters_wire_is_one_publisher(self):
        title="Trump says Russia to immediately supply 300,000 tons of diesel - Reuters"
        self.assertEqual(WATCH.publisher("Reuters",title),WATCH.publisher("MarketScreener",title))
        self.assertNotEqual(WATCH.publisher("Associated Press",title),WATCH.publisher("Reuters",title))

    def test_event_stage_keys_unique_and_repeatable(self):
        self.assertEqual(WATCH.event_key("license_issued"),WATCH.event_key("license_issued"))
        self.assertNotEqual(WATCH.event_key("license_issued"),WATCH.event_key("agreement_reported"))
        self.assertNotEqual(WATCH.event_key("license_issued"),WATCH.event_key("shipment_confirmed"))

    def test_rss_discards_stale_and_unrelated_titles(self):
        pub="Sat, 10 Oct 2026 00:40:00 +0000"
        older="Tue, 06 Oct 2026 00:40:00 +0000"
        rss=f"""<rss><channel>
          <item><title>Trump and Putin agree Russia supplies diesel - Reuters</title><source>Reuters</source><link>https://reuters.com/a</link><pubDate>{pub}</pubDate></item>
          <item><title>Trump and Putin agree Russia supplies diesel - Reuters</title><source>Reuters</source><link>https://reuters.com/b</link><pubDate>{older}</pubDate></item>
          <item><title>Iran exports diesel</title><source>Reuters</source><link>https://reuters.com/c</link><pubDate>{pub}</pubDate></item>
        </channel></rss>""".encode()
        rows=WATCH.parse_rss(rss,self.now)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["url"],"https://reuters.com/a")

    def test_body_clearly_marks_4800000_tonnes_as_plan(self):
        class Stub:
            @staticmethod
            def _source_name_ko(name):
                return "로이터" if "Reuters" in name else name
        rows=[{"official":True,"source":"OFAC","title":"general license",
               "url":WATCH.OFAC_URL,"time":self.now.timestamp()},
              {"official":False,"source":"Reuters","title":"Trump announces Russia diesel deal",
               "url":"https://reuters.com/a","time":self.now.timestamp()}]
        body=WATCH.make_body(Stub(),"license_issued",rows,self.now)
        self.assertIn("총 480만 톤",body)
        self.assertIn("실제 선적·수입항 도착 미검증",body)
        self.assertIn("조건부",body)
        self.assertIn("원문: "+WATCH.OFAC_URL,body)
        self.assertIn("인도 확정 물량이 아닙니다",body)
        self.assertLessEqual(len(body.splitlines()),36)

if __name__=="__main__":
    unittest.main()

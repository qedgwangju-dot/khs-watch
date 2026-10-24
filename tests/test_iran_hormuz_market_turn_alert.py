import datetime as dt
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iran_hormuz_market_turn_alert.py"
SPEC = importlib.util.spec_from_file_location("iran_hormuz_market_turn_alert", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class IranHormuzMarketTurnTests(unittest.TestCase):
    def test_all_google_rss_queries_use_short_bounded_timeout(self):
        import inspect
        body=inspect.getsource(MODULE.fetch_news)
        self.assertIn("fetch_bytes(google_news_url(query), timeout=4, attempts=1)",body)
        self.assertNotIn("fetch_bytes(google_news_url(query))",body)


    def test_aramco_official_rss_requires_real_first_party_article_link(self):
        now=dt.datetime(2026,10,12,10,0,tzinfo=dt.timezone.utc)
        stamp="Mon, 12 Oct 2026 08:30:00 GMT"
        content=f"""<rss><channel>
            <item><title>Saudi Aramco awards pipeline contract for new Hormuz bypass alternative route</title>
            <link>https://www.aramco.com/en/news-media/news/2026/new-hormuz-bypass-project</link>
            <pubDate>{stamp}</pubDate></item>
            <item><title>Saudi Aramco awards pipeline contract for new Hormuz bypass alternative route</title>
            <link>https://news.google.com/rss/articles/unverified</link>
            <pubDate>{stamp}</pubDate></item>
            <item><title>Saudi Aramco awards pipeline contract for new Hormuz bypass alternative route</title>
            <link>https://example.com/fake-aramco</link>
            <pubDate>{stamp}</pubDate></item></channel></rss>"""
        parsed=MODULE.parse_aramco_bypass_official_rss(content.encode(),now)
        self.assertEqual(len(parsed),1)
        self.assertTrue(MODULE._saudi_bypass_first_party_proof(parsed[0]))
        self.assertEqual(MODULE._saudi_bypass_stage(parsed[0].title),"contract_awarded")
        self.assertEqual(parsed[0].published_utc,"2026-10-12T08:30:00Z")

    def test_aramco_official_rss_rejects_bad_dates_and_stale_reports(self):
        now=dt.datetime(2026,10,12,10,0,tzinfo=dt.timezone.utc)
        def feed(timestamp):
            return f"""<rss><channel><item>
              <title>Saudi Aramco awards pipeline contract for new Hormuz bypass alternative route</title>
              <link>https://www.aramco.com/en/news-media/news/2026/new-hormuz-bypass-project</link>
              <pubDate>{timestamp}</pubDate>
            </item></channel></rss>""".encode()
        self.assertEqual(MODULE.parse_aramco_bypass_official_rss(feed("Mon, 01 Jun 2026 12:00:00 GMT"),now),[])
        self.assertEqual(MODULE.parse_aramco_bypass_official_rss(feed("garbage date"),now),[])
        self.assertEqual(MODULE.parse_aramco_bypass_official_rss(feed("Tue, 13 Oct 2026 12:00:00 GMT"),now),[])

    def test_aramco_official_article_must_corroborate_exact_stage(self):
        from unittest import mock
        now=dt.datetime(2026,10,12,10,0,tzinfo=dt.timezone.utc)
        url="https://www.aramco.com/en/news-media/news/2026/new-hormuz-bypass-project"
        rss=(f"""<rss><channel><item><title>Saudi Aramco awards pipeline contract for new Hormuz bypass alternative route</title>
            <link>{url}</link><pubDate>Mon, 12 Oct 2026 08:30:00 GMT</pubDate></item></channel></rss>""").encode()
        article=b"<html><body>Saudi Aramco awards pipeline contract for new Hormuz bypass alternative route. The new pipeline construction procurement award is signed.</body></html>"
        def fake_fetch(got_url, **kwargs):
            if got_url==MODULE.ARAMCO_OFFICIAL_RSS_URL: return rss
            if got_url==url: return article
            raise RuntimeError("unknown URL")
        with mock.patch.object(MODULE,"fetch_bytes",side_effect=fake_fetch):
            rows=MODULE.fetch_aramco_bypass_official_news(now)
        self.assertEqual(len(rows),1)
        self.assertIsNotNone(MODULE.confirm_event(rows))
        forged_article=b"<html><body>Aramco reports old East-West pipeline operation, not a new award.</body></html>"
        with mock.patch.object(MODULE,"fetch_bytes",side_effect=lambda got_url,**kw: rss if got_url==MODULE.ARAMCO_OFFICIAL_RSS_URL else forged_article):
            rows=MODULE.fetch_aramco_bypass_official_news(now)
        self.assertEqual(rows,[])

    def test_aramco_rss_is_discovery_not_spoofable_company_proof(self):
        self.assertFalse(MODULE._aramco_official_url("http://www.aramco.com/en/news"))
        self.assertFalse(MODULE._aramco_official_url("https://www.aramco.com.evil.example/en/news"))
        self.assertFalse(MODULE._aramco_official_url("https://news.google.com/rss/articles/abc"))
        self.assertTrue(MODULE._aramco_official_url("https://www.aramco.com/en/news-media/news"))

    def test_saudi_bypass_new_plan_separate_from_existing_pipeline_operations(self):
        self.assertEqual(
            MODULE.classify_event("Saudi Arabia builds additional pipelines as alternative routes to Hormuz: Minister"),
            "saudi_bypass_investment"
        )
        self.assertEqual(
            MODULE.classify_event("Saudi East-West Pipeline transport hits 5.8 million barrels per day"),
            "east_west_pipeline_recovery"
        )

    def test_saudi_bypass_speech_direct_source_has_stable_original_date(self):
        raw = """<html><body>11/10/2026 Argaam
        Saudi Arabia builds additional pipelines as alternative routes to Hormuz: Minister
        Prince Abdulaziz bin Salman said Saudi Arabia is developing additional pipelines
        to provide alternative routes that bypass the Strait of Hormuz.
        Building alternative routes is far lower in cost than not having them.
        </body></html>"""
        now=dt.datetime(2026,10,12,9,20,tzinfo=dt.timezone.utc)
        row=MODULE.parse_saudi_bypass_strategy_source(raw,now)
        self.assertEqual(row.event_kind,"saudi_bypass_investment")
        self.assertEqual(MODULE._saudi_bypass_stage(row.title),"strategy_announced")
        self.assertEqual(row.published_utc,"2026-10-11T00:00:00Z")
        self.assertEqual(row.link,MODULE.SAUDI_BYPASS_STRATEGY_URL)
        a=MODULE.event_id(row.event_kind,[row])
        reprint=MODULE.NewsItem(row.title,row.source,row.link,row.published_utc,row.published_epoch+7200,row.event_kind)
        self.assertEqual(a,MODULE.event_id(reprint.event_kind,[reprint]))
        found=MODULE.confirm_event([row])
        self.assertIsNotNone(found)
        body=MODULE.build_physical_flow_alert_body(row.event_kind,[row],None,now)
        self.assertIn("1,000만 배럴/일·2~3년설은 총용량/증분·기산일 공식 미확인",body)
        self.assertIn("세계 전망",body)
        self.assertNotIn("사업비 확정",body)
        self.assertLessEqual(len(body.splitlines()),34)

    def test_saudi_bypass_unverified_10m_and_2years_not_confirmed(self):
        headline="Saudi Arabia pipeline capacity expansion 10 million bpd in 2-3 years"
        self.assertIsNone(MODULE._saudi_total_pipeline_target_mbd(headline))
        self.assertNotEqual(MODULE._saudi_bypass_stage(headline),"target_total_confirmed")
        now=dt.datetime(2026,10,12,9,20,tzinfo=dt.timezone.utc)
        row=MODULE.NewsItem(
            "Saudi developing additional pipelines; total pipeline capacity to 10 million barrels per day",
            "Argaam","https://www.argaam.com/en/article/articledetail/id/1943047",
            now.isoformat(),now.timestamp(),"saudi_bypass_investment"
        )
        self.assertEqual(MODULE._saudi_bypass_stage(row.title),"target_total_confirmed")
        self.assertIsNone(MODULE.confirm_event([row]))
        self.assertFalse(MODULE._saudi_bypass_first_party_proof(row))
        with self.assertRaisesRegex(ValueError,"공식 원문"):
            MODULE.event_id(row.event_kind,[row])

    def test_saudi_bypass_first_party_milestone_and_new_stage(self):
        now=dt.datetime(2026,10,12,9,20,tzinfo=dt.timezone.utc)
        plan=MODULE.NewsItem(
            "Saudi Arabia developing additional pipelines as alternative routes bypassing Hormuz",
            "Argaam",MODULE.SAUDI_BYPASS_STRATEGY_URL,
            now.isoformat(),now.timestamp(),"saudi_bypass_investment"
        )
        award=MODULE.NewsItem(
            "Saudi Aramco awards pipeline contract for new Hormuz bypass alternative route",
            "Saudi Aramco","https://www.aramco.com/en/news-media/news/2026/hormuz-bypass",
            now.isoformat(),now.timestamp(),"saudi_bypass_investment"
        )
        self.assertEqual(MODULE._saudi_bypass_stage(award.title),"contract_awarded")
        self.assertTrue(MODULE._saudi_bypass_first_party_proof(award))
        self.assertIsNotNone(MODULE.confirm_event([award]))
        self.assertNotEqual(MODULE.event_id(plan.event_kind,[plan]),MODULE.event_id(award.event_kind,[award]))
        spoof=MODULE.NewsItem(award.title,"Saudi Aramco","https://example.com/fake",
                              award.published_utc,award.published_epoch,award.event_kind)
        self.assertFalse(MODULE._saudi_bypass_first_party_proof(spoof))
        self.assertIsNone(MODULE.confirm_event([spoof]))

    def test_saudi_bypass_dated_plan_immutably_deduped_after_100_days(self):
        now=dt.datetime(2026,10,12,9,20,tzinfo=dt.timezone.utc)
        row=MODULE.NewsItem(
            "Saudi Arabia developing additional pipelines as alternative routes bypassing Hormuz",
            "Argaam",MODULE.SAUDI_BYPASS_STRATEGY_URL,
            now.isoformat(),now.timestamp(),"saudi_bypass_investment"
        )
        eid=MODULE.event_id(row.event_kind,[row])
        state={"alerted_events":{eid:now.astimezone(MODULE.KST).isoformat()}}
        later=now+dt.timedelta(days=100)
        self.assertTrue(MODULE.event_recently_alerted(state,eid,later))
        updated=MODULE.build_pending_state(state,"another_event","other",later,{})
        self.assertIn(eid,updated["alerted_events"])
        self.assertIsNone(MODULE.select_unalerted_event(state,[(row.event_kind,[row])],later)[0])

    def test_opec_23percent_june2026_is_not_new_investment_project(self):
        self.assertEqual(MODULE.OPEC_WOO2026_ENERGY_GROWTH_PCT,23)
        self.assertEqual(MODULE.OPEC_WOO2026_OIL_INVESTMENT_USD_TRILLION,17.7)
        self.assertIsNone(MODULE.classify_event(
            "OPEC secretary general: world primary energy needs rise 23% by 2050"
        ))

    @staticmethod
    def _venezuela_reuters_fixture():
        return """<html><body><article>
        Reuters CARACAS - Venezuela expects nearly $76 billion in oil investment
        over the next five years, acting President Delcy Rodriguez said,
        as a bilateral agreement with the US includes plans to drill 250 rigs
        across 17 oil fields. The parties signed 61 agreements.
        Zulia output rose from 70,000 bpd to 370,000 bpd with
        a goal of 400,000 bpd by end of year. Period unspecified.
        </article></body></html>"""

    @staticmethod
    def _venezuela_ministry_fixture():
        return """<html><body>
        Delcy Rodríguez informó que Petróleos de Venezuela (PDVSA)
        ha suscrito 61 acuerdos y mantiene en negociación otros 44,
        para un total proyectado de 105 convenios.
        </body></html>"""

    @staticmethod
    def _nabep_press_fixture():
        return """<html><body>
        North American Blue Energy Partners (NABEP) Boosts Operations with New Workover and Drilling Rigs.
        Eleven new 550-horsepower workover rigs are being deployed.
        Two new 1,500-horsepower drilling rigs arrived on October 7 for NABEP.
        Separately, the company has purchased 60 rigs, 30 steam boilers and 70 pieces of heavy machinery.
        NABEP has increased production from 18,000 to more than 200,000 barrels per day
        by investing about $1 billion of its own money.
        </body></html>"""

    @staticmethod
    def _nabep_trade_fixture():
        return """<html><body>
        NABEP adds workover, drilling rigs in Venezuela as it targets 1 MMbpd.
        Deploying 11 new 550-hp workover rigs and two new 1,500-hp drilling rigs arrived Oct. 7.
        Separately the company has purchased 60 rigs, 30 steam boilers and 70 pieces of heavy machinery.
        Production rose from 18,000 bpd to more than 200,000 bpd with $1 billion in capital invested.
        </body></html>"""

    def test_nabep_equipment_company_and_trade_require_both(self):
        original=MODULE.parse_nabep_oct13_equipment_release(
            self._nabep_press_fixture(), MODULE.VENEZUELA_NABEP_COMPANY_URLS[0],
            MODULE.VENEZUELA_NABEP_COMPANY_SOURCE)
        independent=MODULE.parse_nabep_oct13_equipment_release(
            self._nabep_trade_fixture(), MODULE.VENEZUELA_NABEP_TRADE_URLS[0],
            MODULE.VENEZUELA_NABEP_TRADE_SOURCE)
        self.assertIsNone(MODULE.confirm_event([original]))
        self.assertIsNone(MODULE.confirm_event([independent]))
        self.assertIsNotNone(MODULE.confirm_event([original,independent]))
        self.assertEqual(MODULE.event_id("venezuela_nabep_equipment",[original,independent]),
                         MODULE.VENEZUELA_NABEP_20261013_EVENT_ID)
        self.assertEqual(MODULE._nabep_milestone_numbers(original.title),(2,11,60,30,70))

    def test_nabep_equipment_not_assumed_250_order_or_funded_76b(self):
        now=dt.datetime(2026,10,18,6,tzinfo=dt.timezone.utc)
        a=MODULE.parse_nabep_oct13_equipment_release(
            self._nabep_press_fixture(),MODULE.VENEZUELA_NABEP_COMPANY_URLS[0],
            MODULE.VENEZUELA_NABEP_COMPANY_SOURCE)
        b=MODULE.parse_nabep_oct13_equipment_release(
            self._nabep_trade_fixture(),MODULE.VENEZUELA_NABEP_TRADE_URLS[0],
            MODULE.VENEZUELA_NABEP_TRADE_SOURCE)
        body=MODULE.build_physical_flow_alert_body("venezuela_nabep_equipment",[a,b],None,now)
        for phrase in ("1,500마력 2기","550마력 11기","장비 60기",
                       "증기보일러 30기","중장비 70대","760억 달러","250기 대비 이행률"):
            self.assertIn(phrase,body)
        self.assertIn("구매/도착/배치/시추 가동은 서로 다릅니다",body)
        self.assertNotIn("전량 가동 확인",body)
        self.assertLessEqual(len(body.splitlines()),31)
        fx=MODULE.Quote("KRW=X","원·달러","원/달러",1334.61,1334.61,0,0,"",now.timestamp())
        priced=MODULE.build_physical_flow_alert_body("venezuela_nabep_equipment",[a,b],None,now,fx)
        self.assertIn("약 1.3346조원",priced)

    def test_nabep_equipment_rejects_unverified_numbers_and_spoofs(self):
        a=MODULE.parse_nabep_oct13_equipment_release(
            self._nabep_press_fixture(),MODULE.VENEZUELA_NABEP_COMPANY_URLS[0],
            MODULE.VENEZUELA_NABEP_COMPANY_SOURCE)
        forged=MODULE.NewsItem(a.title,"NABEP blog",a.link,a.published_utc,a.published_epoch,a.event_kind)
        self.assertFalse(MODULE._nabep_milestone_evidence([a,forged]))
        self.assertIsNone(MODULE.confirm_event([a,forged]))
        with self.assertRaisesRegex(RuntimeError,"미승인"):
            MODULE.parse_nabep_oct13_equipment_release(
                self._nabep_trade_fixture(),"https://example.com/fake",MODULE.VENEZUELA_NABEP_TRADE_SOURCE)
        with self.assertRaisesRegex(RuntimeError,"원문 검증 실패"):
            MODULE.parse_nabep_oct13_equipment_release(
                self._nabep_trade_fixture().replace("60 rigs","600 rigs"),
                MODULE.VENEZUELA_NABEP_TRADE_URLS[0],MODULE.VENEZUELA_NABEP_TRADE_SOURCE)

    def test_nabep_equipment_is_deduplicated_by_original_date(self):
        now=dt.datetime(2026,10,18,6,tzinfo=dt.timezone.utc)
        original=MODULE.parse_nabep_oct13_equipment_release(
            self._nabep_press_fixture(),MODULE.VENEZUELA_NABEP_COMPANY_URLS[0],
            MODULE.VENEZUELA_NABEP_COMPANY_SOURCE)
        trade=MODULE.parse_nabep_oct13_equipment_release(
            self._nabep_trade_fixture(),MODULE.VENEZUELA_NABEP_TRADE_URLS[0],
            MODULE.VENEZUELA_NABEP_TRADE_SOURCE)
        eid=MODULE.event_id("venezuela_nabep_equipment",[original,trade])
        self.assertTrue(MODULE.event_recently_alerted(
            {"alerted_events":{eid:now.astimezone(MODULE.KST).isoformat()}},eid,now))
        self.assertEqual(original.published_epoch, trade.published_epoch)
        self.assertEqual(original.published_epoch,MODULE.VENEZUELA_NABEP_EVENT_DATE.timestamp())

    def test_venezuela_plan_requires_reuters_full_and_official_agreement_count(self):
        now=dt.datetime(2026,10,18,5,tzinfo=dt.timezone.utc)
        r=MODULE.parse_venezuela_reuters_plan(
            self._venezuela_reuters_fixture(),now,MODULE.VENEZUELA_20261017_SOURCE_URLS[1]
        )
        g=MODULE.parse_venezuela_government_agreements(self._venezuela_ministry_fixture(),now)
        self.assertEqual(MODULE.classify_event("Venezuela expects nearly $76 billion oil investment over five years"),"venezuela_oil_investment")
        self.assertEqual(MODULE._venezuela_investment_stage(r.title),"plan_announced")
        self.assertEqual(MODULE._venezuela_investment_stage(g.title),"official_agreements_context")
        self.assertIsNone(MODULE.confirm_event([r]))
        self.assertIsNone(MODULE.confirm_event([g]))
        confirmed=MODULE.confirm_event([r,g])
        self.assertIsNotNone(confirmed)
        self.assertEqual(MODULE.event_id("venezuela_oil_investment",[r,g]),MODULE.VENEZUELA_PLAN_EVENT_ID)
        self.assertTrue(MODULE._venezuela_plan_summary([r,g])["zulia_claim"])

    def test_venezuela_primary_source_preserved_despite_newer_reprints(self):
        now=dt.datetime(2026,10,18,5,tzinfo=dt.timezone.utc)
        original=MODULE.parse_venezuela_reuters_plan(
            self._venezuela_reuters_fixture(),now,MODULE.VENEZUELA_20261017_SOURCE_URLS[1]
        )
        official=MODULE.parse_venezuela_government_agreements(self._venezuela_ministry_fixture(),now)
        copies=[
            MODULE.NewsItem(
                "Venezuela expects nearly $76 billion oil investment over five years",
                name,"https://example.com/"+str(i),now.isoformat(),now.timestamp()+i,
                "venezuela_oil_investment"
            )
            for i,name in enumerate(("Reuters","Financial Times","Associated Press","Bloomberg"),start=1)
        ]
        candidates=MODULE.confirm_events(copies+[original,official])
        one=[rows for kind,rows in candidates if kind=="venezuela_oil_investment"]
        self.assertEqual(len(one),1)
        self.assertTrue(MODULE._venezuela_has_verified_reuters(one[0]))
        self.assertTrue(MODULE._venezuela_has_official_61(one[0]))
        self.assertEqual(MODULE.event_id("venezuela_oil_investment",one[0]),MODULE.VENEZUELA_PLAN_EVENT_ID)

    def test_invalid_event_id_does_not_block_valid_oil_alert(self):
        now=dt.datetime(2026,10,18,5,tzinfo=dt.timezone.utc)
        bogus=[
            MODULE.NewsItem("Venezuela expects nearly $76 billion oil investment over five years",
                "Reuters","https://example.org/unverified",now.isoformat(),now.timestamp(),"venezuela_oil_investment")
        ]
        good=[
            MODULE.NewsItem(
                "Gulf of Oman ship-to-ship record surge","Kpler","https://example.com/kpler",
                now.isoformat(),now.timestamp()-60,"sts_reroute_expansion")
        ]
        selected,_=MODULE.select_unalerted_event(
            {},[("venezuela_oil_investment",bogus),("sts_reroute_expansion",good)],now
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0],"sts_reroute_expansion")

    def test_venezuela_false_rig_contract_claim_rejected(self):
        now=dt.datetime(2026,10,18,5,tzinfo=dt.timezone.utc)
        invalid=self._venezuela_reuters_fixture().replace("250 rigs","250 rigs signed as completed purchase")
        with self.assertRaisesRegex(RuntimeError,"원문|Reuters"):
            MODULE.parse_venezuela_reuters_plan(invalid.replace("76 billion","75 billion"),now,MODULE.VENEZUELA_20261017_SOURCE_URLS[1])
        with self.assertRaisesRegex(RuntimeError,"원문|61건"):
            MODULE.parse_venezuela_government_agreements("<html>61 agreements were rumored</html>",now)
        with self.assertRaisesRegex(RuntimeError,"미승인"):
            MODULE.parse_venezuela_reuters_plan(self._venezuela_reuters_fixture(),now,"https://untrusted.example/ven")
        self.assertEqual(MODULE._venezuela_investment_stage("Venezuela 250 rigs planned in 17 fields; financing not yet funded"),"unclassified")

    def test_venezuela_dedup_reprints_and_stage_separation(self):
        now=dt.datetime(2026,10,18,5,tzinfo=dt.timezone.utc)
        r=MODULE.parse_venezuela_reuters_plan(self._venezuela_reuters_fixture(),now,MODULE.VENEZUELA_20261017_SOURCE_URLS[1])
        g=MODULE.parse_venezuela_government_agreements(self._venezuela_ministry_fixture(),now)
        later=MODULE.NewsItem(r.title,r.source,r.link,r.published_utc,r.published_epoch+86400,r.event_kind)
        self.assertEqual(MODULE.event_id("venezuela_oil_investment",[r,g]),MODULE.event_id("venezuela_oil_investment",[later,g]))
        state={"alerted_events":{MODULE.VENEZUELA_PLAN_EVENT_ID:"2026-10-18T14:00:00+09:00"}}
        self.assertTrue(MODULE.event_recently_alerted(state,MODULE.VENEZUELA_PLAN_EVENT_ID,now+dt.timedelta(days=90)))
        follow="Venezuela oil financing closed, funding disbursed to operators"
        self.assertEqual(MODULE._venezuela_investment_stage(follow),"funding_reported")
        self.assertNotEqual(MODULE.classify_event(follow),None)

    def test_venezuela_alert_contains_dated_fx_and_separate_61_agreements(self):
        now=dt.datetime(2026,10,18,5,tzinfo=dt.timezone.utc)
        r=MODULE.parse_venezuela_reuters_plan(self._venezuela_reuters_fixture(),now,MODULE.VENEZUELA_20261017_SOURCE_URLS[1])
        g=MODULE.parse_venezuela_government_agreements(self._venezuela_ministry_fixture(),now)
        body=MODULE.build_physical_flow_alert_body("venezuela_oil_investment",[r,g],None,now)
        self.assertIn("정부 예상 투자계획 발표",body)
        self.assertIn("약 101조",body)
        self.assertIn("10월 16일 기준",body)
        self.assertIn("61건 기존 협정",body)
        self.assertIn("자금 집행 확정 아님",body)
        self.assertIn("정부 주장/증가 기간 미공개",body)
        self.assertIn("250기 실제 발주",body)
        self.assertLessEqual(len(body.splitlines()),36)

    def test_final_ceasefire_is_classified(self):
        title = "US and Iran agree to ceasefire agreement, officials say - Reuters"
        self.assertEqual(MODULE.classify_event(title), "ceasefire")

    def test_ceasefire_hopes_are_rejected(self):
        title = "Markets rally on Iran ceasefire hopes - Reuters"
        self.assertIsNone(MODULE.classify_event(title))

    def test_temporary_attack_pause_is_rejected(self):
        title = "US and Iran pause strikes in hope of quick deal - Reuters"
        self.assertIsNone(MODULE.classify_event(title))

    def test_hormuz_normalization_is_classified(self):
        title = "Shipping resumes through the Strait of Hormuz as traffic returns to normal - Reuters"
        self.assertEqual(MODULE.classify_event(title), "hormuz_normalization")

    def test_event_needs_two_unique_sources(self):
        now = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "a", now.isoformat(), now.timestamp(), "ceasefire"),
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "b", now.isoformat(), now.timestamp(), "ceasefire"),
        ]
        self.assertIsNone(MODULE.confirm_event(rows))
        rows.append(MODULE.NewsItem("Iran ceasefire agreement takes effect", "Associated Press", "c", now.isoformat(), now.timestamp(), "ceasefire"))
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "ceasefire")
        self.assertEqual(len(result[1]), 2)

    def test_market_requires_both_yield_and_dollar_down(self):
        now = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc).timestamp()
        down_yield = MODULE.Quote("^UST2Y", "미국 2년물 국채금리", "%", 4.20, 4.25, -0.05, -1.176, "", now)
        down_dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 99.50, 100.00, -0.50, -0.50, "", now)
        up_dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 100.20, 100.00, 0.20, 0.20, "", now)
        self.assertTrue(MODULE.market_confirms(down_yield, down_dxy))
        self.assertFalse(MODULE.market_confirms(down_yield, up_dxy))

    def test_physical_oil_flow_recovery_is_classified(self):
        title = "Saudi Arabia ramps up Gulf oil exports after pipeline attack, data shows - Reuters"
        self.assertEqual(MODULE.classify_event(title), "oil_flow_recovery")

    def test_gulf_of_oman_sts_expansion_is_classified(self):
        title = "Saudi export rerouting amid Gulf of Oman STS bottlenecks amplify VLCC intensity - Kpler"
        self.assertEqual(MODULE.classify_event(title), "sts_reroute_expansion")

    def test_kpler_primary_data_can_confirm_flow_event(self):
        now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "Saudi export rerouting amid Gulf of Oman STS bottlenecks amplify VLCC intensity",
                "Kpler",
                "a",
                now.isoformat(),
                now.timestamp(),
                "sts_reroute_expansion",
            )
        ]
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "sts_reroute_expansion")

    def test_flow_event_id_is_stable_across_reprints(self):
        now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        rows_a = [
            MODULE.NewsItem(
                "Saudi Arabia ramps up Gulf oil exports after pipeline attack",
                "Reuters",
                "a",
                now.isoformat(),
                now.timestamp(),
                "oil_flow_recovery",
            )
        ]
        rows_b = [
            MODULE.NewsItem(
                "Aramco boosts Saudi crude exports from Ras Tanura",
                "Bloomberg",
                "b",
                (now + dt.timedelta(hours=8)).isoformat(),
                (now + dt.timedelta(hours=8)).timestamp(),
                "oil_flow_recovery",
            )
        ]
        self.assertEqual(MODULE.event_id("oil_flow_recovery", rows_a), MODULE.event_id("oil_flow_recovery", rows_b))

    def test_generic_oil_flow_alert_is_compact(self):
        current = dt.datetime(2026, 10, 1, 15, 40, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem(
                "Oil prices settle down on signs Middle East exports recovering",
                "Reuters",
                "https://example.com/reuters",
                current.isoformat(),
                current.timestamp(),
                "oil_flow_recovery",
            ),
            MODULE.NewsItem(
                "Oil prices settle down on signs Middle East exports recovering",
                "BNN Bloomberg",
                "https://example.com/bnn",
                current.isoformat(),
                current.timestamp(),
                "oil_flow_recovery",
            ),
        ]
        oil = MODULE.Quote("BZ=F", "Brent", "달러/배럴", 101.81, 98.03, 3.78, 3.86, "", current.timestamp())
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1364.24, 1356.54, 7.70, 0.57, "", current.timestamp())
        body = MODULE.build_physical_flow_alert_body("oil_flow_recovery", news, oil, current, fx)
        self.assertIn("[한눈에]", body)
        self.assertIn("실물          중동 원유 수출 회복", body)
        self.assertIn("시장          Brent USD 101.81", body)
        self.assertIn("[핵심]", body)
        self.assertIn("유가 ↑ + 원화 약세", body)
        self.assertIn("[다음 확인]", body)
        self.assertIn("원문: https://example.com/reuters", body)
        self.assertLessEqual(len(body.splitlines()), 25)
        self.assertNotIn("[병목]", body)
        self.assertNotIn("[다음 체크]", body)

    def test_rss_older_than_24h_is_rejected(self):
        current = dt.datetime(2026, 10, 1, 15, 40, tzinfo=dt.timezone.utc)
        old = current - dt.timedelta(hours=38)
        rss = f"""<?xml version="1.0"?>
        <rss><channel><item>
          <title>Oil prices settle down on signs Middle East exports recovering - Reuters</title>
          <link>https://example.com/old</link>
          <source>Reuters</source>
          <pubDate>{old.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>
        </item></channel></rss>""".encode()
        rows = MODULE.parse_rss(rss, current, 24)
        self.assertEqual(rows, [])

    def test_saudi_minister_target_is_not_contract_or_confirmed_build(self):
        current=dt.datetime(2026,10,13,12,tzinfo=dt.timezone.utc)
        page="""<html><body>12/10/2026 Abdulaziz bin Salman says Saudi Arabia could
        raise oil pipeline capacity to 10 million barrels per day within three years.
        A gas pipeline could carry 1.2 million barrels per day before returning to gas.
        </body></html>"""
        row=MODULE.parse_saudi_10m_minister_report(page,current)
        self.assertEqual(row.event_kind,"saudi_bypass_investment")
        self.assertEqual(MODULE._saudi_bypass_stage(row.title),"minister_target_reported")
        self.assertNotEqual(MODULE._saudi_bypass_stage(row.title),"target_total_confirmed")
        body=MODULE._build_saudi_bypass_investment_alert_body([row],None,current,None)
        self.assertIn("2~3년 목표",body)
        self.assertIn("확정 수주 업체 없음",body)
        self.assertIn("하루 총 1,000만 배럴",body)
        self.assertIsNotNone(MODULE.confirm_event([row]))
        self.assertNotIn("공식 최종 총수송능력",body)

    def test_saudi_minister_report_rejects_unsubstantiated_number(self):
        current=dt.datetime(2026,10,13,12,tzinfo=dt.timezone.utc)
        with self.assertRaises(RuntimeError):
            MODULE.parse_saudi_10m_minister_report(
                "Abdulaziz bin Salman plan 10 million within three years",
                current
            )

    def test_saudi_osp_reuters_parser(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        Saudi Arabia unexpectedly cut November crude oil prices for Asia.
        The November Arab Light crude oil official selling price to Asia was set at $5 a barrel
        below the average of Oman and Dubai prices, down $3 from the previous month.
        State oil company Saudi Aramco made deeper cuts of $5 a barrel for the November OSPs
        of heavier grades - Arab Medium and Arab Heavy - sold to Asia.
        NOVEMBER OCTOBER CHANGE
        SUPER LIGHT -3.35 -0.35 -3.00
        EXTRA LIGHT -4.50 -1.50 -3.00
        LIGHT -5.00 -2.00 -3.00
        MEDIUM -6.00 -1.00 -5.00
        HEAVY -7.35 -2.35 -5.00
        Saudi Aramco raised the November OSPs for northwest Europe by $3 a barrel.
        Aramco kept prices unchanged for buyers in the United States.
        The discount is the widest since June 2020.
        </body></html>
        """
        item = MODULE.parse_saudi_osp_snapshot(html, now, "https://example.com", "Reuters via BOE Report")
        self.assertEqual(item.event_kind, "saudi_asia_osp_change")
        self.assertIn("Arab Light -5.00 MoM -3.00", item.title)
        self.assertIn("Arab Medium -6.00 MoM -5.00", item.title)
        self.assertIn("Arab Heavy -7.35 MoM -5.00", item.title)
        self.assertIn("NW Europe MoM +3.00", item.title)
        self.assertIn("US unchanged", item.title)

    def test_saudi_osp_cross_check_requires_two_sources(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        one = [MODULE.NewsItem(
            "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00 MoM -3.00; Arab Medium -6.00 MoM -5.00; Arab Heavy -7.35 MoM -5.00; NW Europe MoM +3.00; US unchanged; widest Asia Light discount since June 2020",
            "Reuters via BOE Report", "a", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        )]
        self.assertIsNone(MODULE.confirm_event(one))
        one.append(MODULE.NewsItem(
            "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00; Arab Medium -6.00; Arab Heavy -7.35",
            "Saudi Aramco via Argaam", "b", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        ))
        result = MODULE.confirm_event(one)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "saudi_asia_osp_change")

    def test_saudi_osp_alert_is_compact_and_precise(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00 MoM -3.00; Arab Medium -6.00 MoM -5.00; Arab Heavy -7.35 MoM -5.00; NW Europe MoM +3.00; US unchanged; widest Asia Light discount since June 2020",
                "Reuters via BOE Report", "https://example.com/reuters", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
            ),
            MODULE.NewsItem(
                "Saudi OSP November Asia: Super Light -3.35; Extra Light -4.50; Arab Light -5.00; Arab Medium -6.00; Arab Heavy -7.35",
                "Saudi Aramco via Argaam", "https://example.com/argaam", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
            ),
        ]
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1350.0, 1360.0, -10.0, -0.735, "", now.timestamp())
        body = MODULE.build_physical_flow_alert_body("saudi_asia_osp_change", rows, None, now, fx)
        self.assertIn("Oman/Dubai 평균 대비 -5.00달러/배럴", body)
        self.assertIn("전월 대비 -3.00달러", body)
        self.assertIn("Arab Medium -6.00", body)
        self.assertIn("Arab Heavy -7.35", body)
        self.assertIn("서북유럽 전월 대비 +3달러 · 미국 동결", body)
        self.assertIn("약 6,750원/배럴", body)
        self.assertIn("절대가격이 아니라 Oman/Dubai 기준 대비 공식판매가격 차등", body)
        self.assertIn("배럴당 5달러에 판매한다는 뜻이 아닙니다", body)
        self.assertLessEqual(len(body.splitlines()), 34)

    def test_saudi_osp_next_month_creates_new_event(self):
        now = dt.datetime(2026, 10, 5, 11, 0, tzinfo=dt.timezone.utc)
        nov = [MODULE.NewsItem(
            "Saudi OSP November Asia: Arab Light -5.00 MoM -3.00; Arab Medium -6.00; Arab Heavy -7.35",
            "Reuters", "a", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        )]
        dec = [MODULE.NewsItem(
            "Saudi OSP December Asia: Arab Light -4.00 MoM +1.00; Arab Medium -5.00; Arab Heavy -6.35",
            "Reuters", "b", now.isoformat(), now.timestamp(), "saudi_asia_osp_change"
        )]
        self.assertNotEqual(
            MODULE.event_id("saudi_asia_osp_change", nov),
            MODULE.event_id("saudi_asia_osp_change", dec),
        )

    @staticmethod
    def _eia_weekly_fixture():
        return """<html><body>
        Spot Prices (Crude Oil in Dollars per Barrel, Products in Dollars per Gallon)
        Product by Area 08/28/26 09/04/26 09/11/26 09/18/26 09/25/26 10/02/26
        Crude Oil
        WTI - Cushing, Oklahoma 84.62 91.18 99.08 103.54 93.57 98.07
        Brent - Europe 89.73 99.09 111.83 124.15 117.08 120.03
        Conventional Gasoline
        New York Harbor, Regular 3.370 3.266 3.361 3.542 3.580 3.433
        U.S. Gulf Coast, Regular 3.564 3.494 3.629 3.888 3.945 3.672
        RBOB Regular Gasoline
        Los Angeles 3.854 3.860 3.941 4.123 4.294 4.438
        No. 2 Heating Oil
        New York Harbor 4.163 4.508 4.802 5.025 4.745 4.661
        Ultra-Low-Sulfur No. 2 Diesel Fuel
        New York Harbor 4.262 4.604 4.928 5.223 4.955 4.871
        U.S. Gulf Coast 4.274 4.612 4.882 5.128 4.870 4.731
        Kerosene-Type Jet Fuel
        U.S. Gulf Coast 3.715 4.082 4.418 4.584 4.351 4.416
        </body></html>"""

    def test_eia_weekly_refining_crack_official_table_and_units(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        self.assertEqual(row.event_kind, "eia_refining_crack_watch")
        self.assertEqual(row.link, MODULE.EIA_REFINING_WEEKLY_URL)
        self.assertEqual(row.source, MODULE.EIA_REFINING_SOURCE)
        m = MODULE._extract_eia_refining_metrics([row])
        self.assertIsNotNone(m)
        self.assertEqual(m["week"], "2026-10-02")
        self.assertAlmostEqual(float(m["latest"]), 66.25, places=2)
        self.assertAlmostEqual(float(m["previous"]), 76.04, places=2)
        self.assertAlmostEqual(float(m["move"]), -9.79, places=2)
        self.assertAlmostEqual(float(m["gas"]), 3.433, places=3)
        self.assertAlmostEqual(float(m["diesel"]), 4.871, places=3)

    def test_eia_refining_alert_keeps_bloomberg_separate_and_krw(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1350.0, 1355.0, -5, -0.37, "", now.timestamp())
        body = MODULE.build_physical_flow_alert_body("eia_refining_crack_watch", [row], None, now, fx)
        self.assertIn("66.25달러/배럴", body)
        self.assertIn("-9.79달러 축소", body)
        self.assertIn("Bloomberg 선물 3-2-1·Shell 회사별 정제마진과 다른 지표", body)
        self.assertIn("원화 환산", body)
        self.assertIn("52주 신고가", body)
        self.assertIn("원문: https://www.eia.gov", body)
        self.assertLessEqual(len(body.splitlines()), 29)

    def test_eia_refining_official_one_source_confirms_and_dedupes(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        self.assertIsNotNone(MODULE.confirm_event([row]))
        first = MODULE.event_id("eia_refining_crack_watch", [row])
        reprint = MODULE.NewsItem(row.title, row.source, row.link, row.published_utc, row.published_epoch + 7200, row.event_kind)
        self.assertEqual(first, MODULE.event_id("eia_refining_crack_watch", [reprint]))
        state = {"alerted_events": {first: now.astimezone(MODULE.KST).isoformat()}}
        self.assertIsNone(MODULE.select_unalerted_event(state, [("eia_refining_crack_watch", [row])], now)[0])

    def test_eia_refining_rejects_stale_and_missing_rows(self):
        now = dt.datetime(2026, 10, 28, 5, 0, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError, "오래된"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        with self.assertRaisesRegex(RuntimeError, "개수 불일치"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture().replace("3.433", ""), dt.datetime(2026, 10, 8, 5, tzinfo=dt.timezone.utc))

    def test_eia_refining_rejects_unrealistic_units_and_small_change(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(ValueError, "가격 범위"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture().replace("98.07", "999.07"), now)
        with self.assertRaisesRegex(RuntimeError, "기준 미충족"):
            MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture().replace("4.871", "5.550"), now)

    def test_eia_refining_wrong_source_cannot_claim_official(self):
        now = dt.datetime(2026, 10, 8, 5, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_eia_weekly_refining_snapshot(self._eia_weekly_fixture(), now)
        forged = MODULE.NewsItem(row.title, "blog", "https://example.com", row.published_utc, row.published_epoch, row.event_kind)
        self.assertIsNone(MODULE._extract_eia_refining_metrics([forged]))
        self.assertIsNone(MODULE.confirm_event([forged]))

    def test_kpler_prewar_export_parser(self):
        now = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        At least 16.5 mbd left the region between 1 and 28 September, matching the pre-war average excluding Iran.
        40% of the region's crude now leaves without crossing Hormuz, against 17% before the war.
        In September, 60% physically crossed Hormuz, 9.9 mbd, mostly using shuttle tankers.
        In August, more than 70% of the crude crossing the strait changed tankers off Fujairah or Sohar.
        </body></html>
        """
        item = MODULE.parse_kpler_prewar_export_snapshot(html, now)
        self.assertEqual(item.event_kind, "ex_iran_crude_prewar_recovery")
        self.assertIn("16.5 Mbd", item.title)
        self.assertIn("Hormuz 9.9 Mbd 60%", item.title)
        self.assertIn("bypass 40% vs pre-war 17%", item.title)
        self.assertIn("STS over 70%", item.title)

    def test_ex_iran_prewar_body_calculates_route_substitution(self):
        now = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Kpler Gulf crude excluding Iran 16.5 Mbd, 100% pre-war average; Hormuz 9.9 Mbd 60%; bypass 40% vs pre-war 17%; STS over 70%",
            "Kpler", "https://example.com/kpler", now.isoformat(), now.timestamp(), "ex_iran_crude_prewar_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("ex_iran_crude_prewar_recovery", rows, None, now)
        self.assertIn("이란 제외 원유  16.5 Mbd · 전쟁 전 평균의 100%", body)
        self.assertIn("호르무즈      9.9 Mbd · 전체의 60%", body)
        self.assertIn("우회          40% · 전쟁 전 17%", body)
        self.assertIn("호르무즈 약 3.8 Mbd 감소", body)
        self.assertIn("우회 약 3.8 Mbd 증가", body)
        self.assertIn("60% → 70% → 전쟁 전 83%", body)
        self.assertIn("Reuters의 2월 단일월 19.513 Mbd 비교와 분모가 다릅니다", body)

    def test_ex_iran_prewar_event_id_changes_when_route_normalizes(self):
        now = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)
        a = [MODULE.NewsItem(
            "Kpler Gulf crude excluding Iran 16.5 Mbd, 100% pre-war average; Hormuz 9.9 Mbd 60%; bypass 40% vs pre-war 17%; STS over 70%",
            "Kpler", "a", now.isoformat(), now.timestamp(), "ex_iran_crude_prewar_recovery"
        )]
        b = [MODULE.NewsItem(
            "Kpler Gulf crude excluding Iran 16.5 Mbd, 100% pre-war average; Hormuz 12.0 Mbd 73%; bypass 27% vs pre-war 17%; STS over 40%",
            "Kpler", "b", now.isoformat(), now.timestamp(), "ex_iran_crude_prewar_recovery"
        )]
        self.assertNotEqual(
            MODULE.event_id("ex_iran_crude_prewar_recovery", a),
            MODULE.event_id("ex_iran_crude_prewar_recovery", b),
        )

    def test_physical_flow_body_separates_sts_from_hormuz_volume(self):
        current = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem(
                "Gulf of Oman STS volumes surge to a record",
                "Kpler",
                "a",
                current.isoformat(),
                current.timestamp(),
                "sts_reroute_expansion",
            )
        ]
        body = MODULE.build_physical_flow_alert_body("sts_reroute_expansion", news, None, current)
        self.assertIn("STS는 같은 배럴이 여러 번 이송될 수 있어", body)
        self.assertIn("합산하지 않습니다", body)
        self.assertIn("정책 발언 처리", body)

    def test_physical_flow_alert_is_glanceable(self):
        current = dt.datetime(2026, 9, 28, 11, 34, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem(
                "Kpler Gulf of Oman STS record 7.2 Mbd as of 2026-09-26; since-war average 3.7 Mbd; 2025 average 0.16 Mbd; Saudi 3 Mbd requires 36-40 additional VLCCs",
                "Kpler",
                "https://example.com/kpler",
                current.isoformat(),
                current.timestamp(),
                "sts_reroute_expansion",
            )
        ]
        oil = MODULE.Quote("BZ=F", "Brent", "달러/배럴", 100.55, 103.08, -2.53, -2.45, "", current.timestamp())
        body = MODULE.build_physical_flow_alert_body("sts_reroute_expansion", news, oil, current)
        self.assertIn("[한눈에]", body)
        self.assertIn("원유 공급     회복 ↑", body)
        self.assertIn("물류 효율     병목 심화 ↓", body)
        self.assertIn("GoO STS       7.2 Mbd", body)
        self.assertIn("전쟁 후 평균의 1.9배", body)
        self.assertIn("2025 평균의 45배", body)
        self.assertIn("VLCC 수요     Saudi +3 Mbd 처리 시 +36~40척", body)
        self.assertIn("[핵심 의미]", body)
        self.assertIn("[병목]", body)
        self.assertIn("[다음 체크]", body)
        self.assertNotIn("Kpler Gulf of Oman STS record 7.2 Mbd as of", body)
        self.assertLessEqual(len(body.splitlines()), 36)
        self.assertIn("시장          Brent USD 100.55", body)
        self.assertIn("실물          호르무즈 통과량", body)
        self.assertIn("원문: https://example.com/kpler", body)

    def test_east_west_pipeline_recovery_is_classified(self):
        title = "Saudi East-West Pipeline transport hits 3.5 million barrels per day - Reuters"
        self.assertEqual(MODULE.classify_event(title), "east_west_pipeline_recovery")

    def test_pipeline_event_id_uses_material_rate_bands(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        a = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        b = [MODULE.NewsItem(
            "East-West Pipeline flow reaches 3.6 million bpd",
            "Bloomberg", "b", (now + dt.timedelta(hours=2)).isoformat(),
            (now + dt.timedelta(hours=2)).timestamp(), "east_west_pipeline_recovery"
        )]
        c = [MODULE.NewsItem(
            "East-West Pipeline flow reaches 4.0 million bpd",
            "Reuters", "c", (now + dt.timedelta(hours=4)).isoformat(),
            (now + dt.timedelta(hours=4)).timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertEqual(MODULE.event_id("east_west_pipeline_recovery", a), MODULE.event_id("east_west_pipeline_recovery", b))
        self.assertNotEqual(MODULE.event_id("east_west_pipeline_recovery", a), MODULE.event_id("east_west_pipeline_recovery", c))

    def test_pipeline_body_separates_flow_from_yanbu_exports(self):
        current = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("east_west_pipeline_recovery", news, None, current)
        self.assertIn("East-West     3.5 Mbd", body)
        self.assertIn("vs 4Mbd      약 88% 회복", body)
        self.assertIn("Yanbu 수출     실제 선적 별도 확인 필요", body)
        self.assertIn("선적 재개 확인 전 수출 정상화로 단정하지 않습니다", body)

    def test_pipeline_single_media_source_does_not_confirm(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertIsNone(MODULE.confirm_event(rows))

    def test_pipeline_two_sources_confirm(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
                "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
            ),
            MODULE.NewsItem(
                "Saudi East-West Pipeline flow reaches 3.5 million bpd",
                "Bloomberg", "b", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
            ),
        ]
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "east_west_pipeline_recovery")

    def test_yanbu_export_resume_is_classified_without_rate(self):
        title = "Saudi Arabia resumes oil exports via East-West Pipeline from Yanbu after repairs - Bloomberg"
        self.assertEqual(MODULE.classify_event(title), "east_west_pipeline_recovery")

    def test_pipeline_export_resume_is_new_stage(self):
        now = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        rate_only = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        export_resume = [MODULE.NewsItem(
            "Saudi Arabia resumes oil exports via East-West Pipeline from Yanbu after repairs",
            "Bloomberg", "b", (now + dt.timedelta(hours=1)).isoformat(),
            (now + dt.timedelta(hours=1)).timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertNotEqual(
            MODULE.event_id("east_west_pipeline_recovery", rate_only),
            MODULE.event_id("east_west_pipeline_recovery", export_resume),
        )

    def test_pipeline_body_marks_yanbu_exports_resumed(self):
        current = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Saudi Arabia resumes oil exports via East-West Pipeline from Yanbu after repairs",
            "Bloomberg", "a", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("east_west_pipeline_recovery", news, None, current)
        self.assertIn("Yanbu 수출     재개 확인", body)
        self.assertIn("실제 수출로 연결되기 시작했습니다", body)

    def test_regional_export_recovery_is_classified(self):
        title = "Middle East crude exports reach 12.8 million bpd, highest since the war - Reuters"
        self.assertEqual(MODULE.classify_event(title), "regional_export_recovery")

    def test_jpmorgan_98pct_headline_is_classified(self):
        title = 'JPMorgan says Middle East crude flows hit 98% of pre-war level'
        self.assertEqual(MODULE.classify_event(title), "crude_product_divergence")

    def test_korean_jpmorgan_98pct_headline_is_classified(self):
        title = 'JP모건 "중동 원유 수출량, 이란戰 발발 이전 98% 복구"'
        self.assertEqual(MODULE.classify_event(title), "crude_product_divergence")

    def test_crude_product_gap_event_id_moves_on_product_recovery_band(self):
        now = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
        a = [MODULE.NewsItem("JPMorgan Middle East crude/product snapshot crude 17.5 Mbd 98% pre-war; products 3.0 Mbd 58% pre-war; overall 89% of 2025; Hormuz 13.0 Mbd","JPMorgan via Bloomberg","a",now.isoformat(),now.timestamp(),"crude_product_divergence")]
        b = [MODULE.NewsItem("JPMorgan Middle East crude/product snapshot crude 17.6 Mbd 99% pre-war; products 3.4 Mbd 66% pre-war; overall 92% of 2025; Hormuz 13.1 Mbd","JPMorgan via Bloomberg","b",now.isoformat(),now.timestamp(),"crude_product_divergence")]
        self.assertNotEqual(MODULE.event_id("crude_product_divergence", a), MODULE.event_id("crude_product_divergence", b))

    def test_crude_product_gap_body_keeps_crude_and_products_separate(self):
        now = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem("JPMorgan Middle East crude/product snapshot crude 17.5 Mbd 98% pre-war; products 3.0 Mbd 58% pre-war; overall 89% of 2025; Hormuz 13.0 Mbd","JPMorgan via Bloomberg","https://example.com/jpm",now.isoformat(),now.timestamp(),"crude_product_divergence")]
        body = MODULE.build_physical_flow_alert_body("crude_product_divergence", rows, None, now)
        self.assertIn("원유          17.5 Mbd · 전쟁 전의 98%", body)
        self.assertIn("정제품        3.0 Mbd · 전쟁 전의 58%", body)
        self.assertIn("회복 격차     40%p", body)
        self.assertIn("원유 정상화 ≠ 연료시장 정상화", body)
        self.assertIn("정제품        58% → 70% → 85% → 95%", body)

    def test_us_diesel_policy_classification_and_stage_ids(self):
        now = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
        denied = MODULE.NewsItem("White House denies report US is considering a diesel export ban","Reuters","a",now.isoformat(),now.timestamp(),"us_diesel_export_policy")
        considering = MODULE.NewsItem("Trump says he is still considering diesel export ban","Reuters","b",now.isoformat(),now.timestamp(),"us_diesel_export_policy")
        self.assertEqual(MODULE.classify_event(denied.title), "us_diesel_export_policy")
        self.assertEqual(MODULE.classify_event(considering.title), "us_diesel_export_policy")
        self.assertNotEqual(MODULE.event_id("us_diesel_export_policy", [denied]), MODULE.event_id("us_diesel_export_policy", [considering]))

    def test_english_news_headlines_are_rendered_in_korean(self):
        now = dt.datetime(2026, 10, 2, 6, 13, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "VIEW Chinese refiners suspend October fuel exports, sources say - Reuters",
                "Reuters",
                "https://example.com/reuters",
                now.isoformat(),
                now.timestamp(),
                "china_fuel_export_policy",
            ),
            MODULE.NewsItem(
                "Chinese refiners suspend October fuel exports, says report: Which other countries plan curbs amid Iran, Ukraine war",
                "Livemint",
                "https://example.com/livemint",
                now.isoformat(),
                now.timestamp(),
                "china_fuel_export_policy",
            ),
        ]
        body = MODULE.build_physical_flow_alert_body("china_fuel_export_policy", rows, None, now)
        self.assertIn("로이터 ·", body)
        self.assertIn("라이브민트 ·", body)
        self.assertIn("중국 정유사, 10월 정제품 수출 중단", body)
        self.assertNotIn("Chinese refiners suspend", body)
        self.assertNotIn("Which other countries", body)

    def test_us_diesel_english_headline_is_rendered_in_korean(self):
        now = dt.datetime(2026, 10, 2, 6, 13, tzinfo=dt.timezone.utc)
        row = MODULE.NewsItem(
            "Trump says he is still considering diesel export ban",
            "Reuters",
            "https://example.com/reuters",
            now.isoformat(),
            now.timestamp(),
            "us_diesel_export_policy",
        )
        self.assertEqual(MODULE._news_title_ko(row), "백악관, 미국 디젤 수출금지 여부 검토")

    def test_euronews_direct_reserve_parser(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        EU Energy Commissioner Dan Jorgensen said releasing strategic reserves is a possibility
        as the diesel squeeze bites. Member states are discussing a coordinated release.
        </body></html>
        """
        item = MODULE.parse_eu_diesel_reserve_snapshot(html, now)
        self.assertEqual(item.event_kind, "eu_diesel_reserve_policy")
        self.assertEqual(item.source, "Euronews")
        self.assertIn("strategic diesel reserves", item.title)

    def test_g7_100m_agreement_is_classified(self):
        title = "G7 agrees to release 100mn barrels of diesel and crude under pressure from Trump"
        self.assertEqual(MODULE.classify_event(title), "g7_reserve_release_agreement")

    def test_europe_immediate_diesel_agreement_is_classified(self):
        title = "Trump: Europe agrees to release diesel reserves immediately as fuel prices hover near record highs"
        self.assertEqual(MODULE.classify_event(title), "g7_reserve_release_agreement")

    def test_g7_event_requires_two_unique_sources(self):
        now = dt.datetime(2026, 10, 2, 14, 0, tzinfo=dt.timezone.utc)
        one = [MODULE.NewsItem(
            "G7 agrees to release 100mn barrels of diesel and crude under pressure from Trump",
            "Financial Times", "a", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
        )]
        self.assertIsNone(MODULE.confirm_event(one))
        one.append(MODULE.NewsItem(
            "Trump: Europe agrees to release diesel reserves immediately as fuel prices hover near record highs",
            "Associated Press", "b", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
        ))
        result = MODULE.confirm_event(one)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "g7_reserve_release_agreement")

    def test_g7_agreement_body_preserves_split_and_caution(self):
        now = dt.datetime(2026, 10, 2, 14, 0, tzinfo=dt.timezone.utc)
        rows = [
            MODULE.NewsItem(
                "G7 agrees to release 100mn barrels of diesel and crude under pressure from Trump",
                "Financial Times", "a", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
            ),
            MODULE.NewsItem(
                "Trump: Europe agrees to release diesel reserves immediately as fuel prices hover near record highs",
                "Associated Press", "b", now.isoformat(), now.timestamp(), "g7_reserve_release_agreement"
            ),
        ]
        body = MODULE.build_physical_flow_alert_body("g7_reserve_release_agreement", rows, None, now)
        self.assertIn("1억 배럴", body)
        self.assertIn("경유 5,000만 배럴 + IEA 원유 5,000만 배럴", body)
        self.assertIn("1억 배럴 전체가 경유라는 뜻은 아닙니다", body)
        self.assertIn("공개 G7·IEA 공식문서", body)
        self.assertIn("파이낸셜타임스", body)
        self.assertIn("AP", body)

    def test_eu_diesel_reserve_considering_is_classified(self):
        title = 'EU energy chief says releasing strategic diesel reserves is a possibility'
        self.assertEqual(MODULE.classify_event(title), "eu_diesel_reserve_policy")

    def test_eu_diesel_reserve_stage_changes_create_new_event(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        considering = [MODULE.NewsItem(
            "EU energy chief considers release of strategic diesel reserves",
            "Euronews", "a", now.isoformat(), now.timestamp(), "eu_diesel_reserve_policy"
        )]
        approved = [MODULE.NewsItem(
            "EU members approved strategic diesel reserve release",
            "Reuters", "b", now.isoformat(), now.timestamp(), "eu_diesel_reserve_policy"
        )]
        self.assertNotEqual(
            MODULE.event_id("eu_diesel_reserve_policy", considering),
            MODULE.event_id("eu_diesel_reserve_policy", approved),
        )

    def test_eu_diesel_reserve_body_is_compact(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "EU energy chief says releasing strategic diesel reserves is a possibility",
            "Euronews", "https://example.com/eu", now.isoformat(), now.timestamp(), "eu_diesel_reserve_policy"
        )]
        body = MODULE.build_physical_flow_alert_body("eu_diesel_reserve_policy", rows, None, now)
        self.assertIn("EU 정책", body)
        self.assertIn("전략비축", body)
        self.assertIn("5,000만 배럴", body)
        self.assertLessEqual(len(body.splitlines()), 30)

    def test_east_west_80pct_is_new_material_stage(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        old = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 4.0 million barrels per day",
            "Reuters", "a", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        new = [MODULE.NewsItem(
            "Saudi Arabia Hikes Oil Flow on Key Pipeline to Over 80% Capacity",
            "Bloomberg", "b", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        self.assertEqual(MODULE.classify_event(new[0].title), "east_west_pipeline_recovery")
        self.assertNotEqual(
            MODULE.event_id("east_west_pipeline_recovery", old),
            MODULE.event_id("east_west_pipeline_recovery", new),
        )

    def test_east_west_80pct_body_calculates_lower_bound(self):
        now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Saudi Arabia Hikes Oil Flow on Key Pipeline to Over 80% Capacity",
            "Bloomberg", "https://example.com/bloomberg", now.isoformat(), now.timestamp(), "east_west_pipeline_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("east_west_pipeline_recovery", rows, None, now)
        self.assertIn("80% 이상", body)
        self.assertIn("최소 5.6 Mbd", body)
        self.assertIn("80% → 90% → 95%", body)

    def test_china_resume_planned_vs_actual_shipment(self):
        title="China to resume October fuel exports after brief halt, four trade sources say"
        self.assertEqual(MODULE.classify_event(title),"china_fuel_export_policy")
        self.assertEqual(MODULE._china_fuel_export_stage(title),"planned_resume")
        self.assertEqual(MODULE._china_fuel_export_stage("China fuel cargoes departed from port"),"physical_resumed")
        self.assertEqual(MODULE._china_fuel_export_stage("China resumed exports of refined fuel"),"resumption_reported")
        self.assertEqual(MODULE._china_fuel_export_stage("China suspended fuel exports"),"suspended")

    def test_china_planned_resume_key_stable_after_source_volume_omitted(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        row_with=MODULE.NewsItem(
          "China to resume October fuel exports, four trade sources say; approved 3.7 million metric tons",
          "Reuters",MODULE.CHINA_REUTERS_20261009_URL,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        row_without=MODULE.NewsItem(
          "China to resume October fuel exports, four trade sources say",
          "Reuters",MODULE.CHINA_REUTERS_20261009_URL,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        a=MODULE.event_id("china_fuel_export_policy",[row_with])
        b=MODULE.event_id("china_fuel_export_policy",[row_without])
        self.assertEqual(a,b)
        old_basis="china_fuel_export_policy|2026-10|planned_resume|quantity_3.7"
        import hashlib
        legacy_id="china_fuel_export_policy:"+hashlib.sha256(old_basis.encode("utf-8")).hexdigest()[:16]
        state={"alerted_events":{legacy_id:now.astimezone(MODULE.KST).isoformat()}}
        self.assertTrue(MODULE.event_recently_alerted(state,a,now))

    def test_china_future_month_is_new_event_without_reusing_october_baseline(self):
        now=dt.datetime(2026,11,5,12,tzinfo=dt.timezone.utc)
        oct_row=MODULE.NewsItem(
            "China to resume October fuel exports, four trade sources say",
            "Reuters","a",now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        nov_row=MODULE.NewsItem(
            "China to resume November fuel exports, four trade sources say",
            "Reuters","b",now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        self.assertEqual(MODULE._china_policy_period([oct_row]),"2026-10")
        self.assertEqual(MODULE._china_policy_period([nov_row]),"2026-11")
        self.assertNotEqual(
            MODULE.event_id("china_fuel_export_policy",[oct_row]),
            MODULE.event_id("china_fuel_export_policy",[nov_row])
        )
        body=MODULE.build_physical_flow_alert_body("china_fuel_export_policy",[nov_row],None,now)
        self.assertNotIn("10월 7일 연휴 종료",body)

    def test_china_new_reopening_does_not_combine_old_suspension(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        rows=[
          MODULE.NewsItem("Chinese refiners suspend October fuel exports","Reuters","a",now.isoformat(),now.timestamp()-3600,"china_fuel_export_policy"),
          MODULE.NewsItem("China to resume October fuel exports, four trade sources say","Reuters",
            MODULE.CHINA_REUTERS_20261009_URL,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        ]
        events=MODULE.confirm_events(rows)
        self.assertTrue(events)
        self.assertEqual(MODULE._china_fuel_export_stage(events[0][1]),"planned_resume")
        self.assertTrue(all(MODULE._china_fuel_export_stage(r.title)=="planned_resume" for r in events[0][1]))

    def test_china_reuters_snapshot_370m_tons_is_not_actual_exports(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        html="""<html>China is set to resume October refined fuel exports after a brief halt
        during Golden Week, four traders said Friday. China approved October exports
        of gasoline diesel and jet fuel combined at around 3.7 million metric tons.</html>"""
        row=MODULE.parse_china_reuters_resumption(html,now)
        self.assertEqual(MODULE._china_resumption_volume([row]),3.7)
        body=MODULE.build_physical_flow_alert_body("china_fuel_export_policy",[row],None,now)
        self.assertIn("재개 예정",body)
        self.assertIn("370만 톤",body)
        self.assertIn("실제 출항",body)
        self.assertLessEqual(len(body.splitlines()),34)

    def test_china_syndicated_reuters_not_two_independent_sources(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        rows=[
          MODULE.NewsItem("China to resume October fuel exports","Reuters","a",now.isoformat(),now.timestamp(),"china_fuel_export_policy"),
          MODULE.NewsItem("China to resume October fuel exports","MarketScreener","b",now.isoformat(),now.timestamp(),"china_fuel_export_policy"),
        ]
        self.assertIsNone(MODULE.confirm_event(rows))

    def test_hormuz_seven_day_is_conditional_not_seven_days_open(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        title="Iran Araghchi reviewing US views on seven-day plan to reopen Strait of Hormuz within seven days"
        self.assertEqual(MODULE.classify_event(title),"hormuz_7day_diplomacy")
        row=MODULE.NewsItem(title,"Xinhua",MODULE.HORMUZ_7DAY_XINHUA_URL,now.isoformat(),now.timestamp(),"hormuz_7day_diplomacy")
        body=MODULE.build_physical_flow_alert_body("hormuz_7day_diplomacy",[row],None,now)
        self.assertIn("7일 이내",body)
        self.assertIn("7일 동안 개방 확정",body)
        self.assertIn("실제 통항",body)

    def test_mma_official_url_and_dynamic_report_date_guards(self):
        a=MODULE.MMA_OIL_ISAIAS_OCT9_URL
        self.assertTrue(MODULE._is_official_mma_isaias_url(a))
        self.assertFalse(MODULE._is_official_mma_isaias_url("https://www.bsee.gov.evil.example/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias4"))
        self.assertFalse(MODULE._is_official_mma_isaias_url("http://www.bsee.gov/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias4"))
        self.assertEqual(MODULE._mma_report_date("<h1>MMA Isaias</h1><p>Friday, October 9, 2026</p>"),dt.date(2026,10,9))
        self.assertEqual(MODULE._discover_mma_isaias_urls('<a href="/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias3">Oct9</a>'),[a])

    def test_mma_fetch_advances_to_latest_official_date(self):
        # Fixtures use genuine Oct7/Oct8 style with controlled Oct9 numbers; numbers are not live market assertions.
        import unittest.mock
        m=MODULE
        base="Marine Minerals Administration Isaias. {date}. evacuated from a total of {platforms} production platforms. " + (
            "approximately {pct:.2f}% of the current oil production and {gas:.2f}% of the current natural gas production. "
            "Oil, BOPD** Shut-in {bpd:,}"
        )
        pages={
            m.MMA_OIL_ISAIAS_OCT7_URL:base.format(date="October 7, 2026",platforms=8,pct=25.08,gas=16.37,bpd=511619),
            m.MMA_OIL_ISAIAS_OCT8_URL:base.format(date="October 8, 2026",platforms=121,pct=62.90,gas=44.00,bpd=1280000),
            m.MMA_OIL_ISAIAS_OCT9_URL:base.format(date="October 9, 2026",platforms=129,pct=71.50,gas=58.90,bpd=1450000),
            m.MMA_ISAIAS_NEWS_INDEX_URL:'<a href="/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias3">Oct9</a>'
        }
        def fetch(url,timeout=16,attempts=1):
            return pages[url].encode()
        with unittest.mock.patch.object(m,"fetch_bytes",side_effect=fetch):
            row=m.fetch_mma_isaias_snapshot(dt.datetime(2026,10,10,0,0,tzinfo=dt.timezone.utc))
        self.assertEqual(row.event_kind,"us_gulf_isaias_shutin")
        self.assertIn("date=2026-10-09",row.title)
        self.assertIn("previous_bpd=1280000",row.title)
        self.assertEqual(row.link,m.MMA_OIL_ISAIAS_OCT9_URL)
        parsed=m._extract_mma_isaias_data([row])
        self.assertIsNotNone(parsed)
        body=m._build_us_gulf_isaias_alert_body([row],None,dt.datetime(2026,10,10,tzinfo=dt.timezone.utc),None)
        self.assertIn("2026-10-09",body)
        self.assertIn("isaias3",body)

    def test_mma_fetch_fails_closed_on_stale_official_report(self):
        import unittest.mock
        m=MODULE
        pages={}
        for url,d,p in (
            (m.MMA_OIL_ISAIAS_OCT7_URL,"October 7, 2026",25.08),
            (m.MMA_OIL_ISAIAS_OCT8_URL,"October 8, 2026",62.9),
            (m.MMA_OIL_ISAIAS_OCT9_URL,"October 9, 2026",71.5),
        ):
            pages[url]=f"Marine Minerals Administration Isaias {d} evacuated from a total of 129 production platforms. approximately {p:.2f}% of the current oil production and 58.90% of the current natural gas production. Oil, BOPD** Shut-in 1,450,000"
        def fetch(url,timeout=16,attempts=1):
            if url==m.MMA_ISAIAS_NEWS_INDEX_URL: return b"<html></html>"
            return pages[url].encode()
        with unittest.mock.patch.object(m,"fetch_bytes",side_effect=fetch):
            with self.assertRaisesRegex(RuntimeError,"경과"):
                m.fetch_mma_isaias_snapshot(dt.datetime(2026,10,16,tzinfo=dt.timezone.utc))

    def test_china_resumption_delay_overrides_future_plan(self):
        self.assertEqual(MODULE._china_fuel_export_stage("China's fuel exports set to resume but resumption postponed after port delays"),"resumption_delayed")
        self.assertEqual(MODULE.classify_event("China fuel exports resumption delayed for October after postponement"),"china_fuel_export_policy")

    def test_china_physical_shipments_need_independent_tracking(self):
        now=dt.datetime(2026,10,10,tzinfo=dt.timezone.utc)
        def make(name,url):
            return MODULE.NewsItem("China fuel cargoes departed port after October restart",name,url,now.isoformat(),now.timestamp(),"china_fuel_export_policy")
        row=make("Reuters","https://www.reuters.com/example")
        self.assertEqual(MODULE._china_fuel_export_stage(row.title),"physical_resumed")
        self.assertFalse(MODULE._china_physical_shipment_evidence([row]))
        self.assertIsNone(MODULE.confirm_event([row]))
        duplicate=make("Reuters via MarketScreener","https://www.marketscreener.com/example")
        self.assertIsNone(MODULE.confirm_event([row,duplicate]))
        tracker=make("Kpler","https://www.kpler.com/blog/actual-cargo-shipments")
        self.assertTrue(MODULE._china_physical_shipment_evidence([row,tracker]))
        self.assertIsNotNone(MODULE.confirm_event([row,tracker]))

    def test_mma_official_shutin_source_and_change(self):
        def page(day,oil_pct,gas_pct,bpd,platforms):
            return f"""<html>Marine Minerals Administration Isaias Thursday, October {day}, 2026
            The Marine Minerals Administration estimates that approximately {oil_pct}% of the
            current daily oil production and {gas_pct}% of the current daily natural gas production.
            Personnel have been evacuated from a total of {platforms} production platforms.
            Total Shut-in Percentage of GOA Production Oil, BOPD** Shut-in {bpd} (BOPD).</html>"""
        old=MODULE._parse_mma_isaias_report(page(7,25.08,16.37,"511,619",8),"2026-10-07")
        new=MODULE._parse_mma_isaias_report(page(8,62.89,57.35,"1,282,879",121),"2026-10-08")
        self.assertEqual(new["oil_bpd"]-old["oil_bpd"],771260)
        self.assertEqual(new["oil_pct"],62.89)

    def test_mma_cannot_use_news_claim_without_official_url(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        row=MODULE.NewsItem(
            "MMA Isaias date=2026-10-08; oil_bpd=1282879; oil_pct=62.89; gas_pct=57.35; platforms=121; previous_bpd=511619; previous_pct=25.08",
            "Blog","https://fake.com",now.isoformat(),now.timestamp(),"us_gulf_isaias_shutin"
        )
        self.assertIsNone(MODULE._extract_mma_isaias_data([row]))
        self.assertIsNone(MODULE.confirm_event([row]))

    @staticmethod
    def _tanker_7country_html(post_id="7890", pub="2026-10-13T22:06:41+00:00", extra=""):
        return f"""
        <div class="tgme_widget_message js-widget_message" data-post="tankertrackers/{post_id}">
        <div class="tgme_widget_message_text js-message_text">
        2026 Middle East Crude Oil Exports
        Countries: Iran, Iraq, Kuwait, Qatar, Saudi Arabia, UAE, Oman {extra}
        January: 18.335<br>February: 19.434<br>March: 8.712<br>
        April: 8.501<br>May: 6.488<br>June: 11.087<br>
        July: 12.939<br>August: 13.896<br>September: 14.652<br>
        October: 17.273
        </div>
        <time datetime="{pub}">14 Oct</time>
        </div>
        """

    def test_tanker_monthly_original_scope_and_month_to_date(self):
        now=dt.datetime(2026,10,14,2,0,tzinfo=dt.timezone.utc)
        row=MODULE.parse_tankertrackers_seven_country_mtd(self._tanker_7country_html(), now)
        self.assertEqual(row.source,"TankerTrackers")
        self.assertEqual(row.event_kind,"tankertrackers_7country_crude_mtd")
        self.assertEqual(row.link,"https://t.me/tankertrackers/7890")
        self.assertTrue(MODULE._is_tankertrackers_direct_message(row))
        self.assertIn("feb=19.434",row.title)
        self.assertIn("latest=17.273",row.title)
        m=MODULE._extract_tankertrackers_7country_metrics([row])
        self.assertIsNotNone(m)
        self.assertEqual(m["month"],10)
        self.assertAlmostEqual(m["latest_mbd"]/m["feb_mbd"]*100,88.88,places=2)
        self.assertIsNotNone(MODULE.confirm_event([row]))
        body=MODULE.build_physical_flow_alert_body(
            "tankertrackers_7country_crude_mtd",[row],None,now)
        self.assertIn("88.9%",body)
        self.assertIn("17.273백만 배럴/일",body)
        self.assertIn("하루 +262.1만 배럴 변화",body)
        self.assertIn("월중 잠정",body)
        self.assertIn("Kpler의 이란 제외",body)
        self.assertNotIn("전쟁 전 평균의 100%",body)
        self.assertLessEqual(len(body.splitlines()),29)

    def test_tanker_november_updates_month_and_compares_october(self):
        # November must not be mislabeled October or compare against September.
        now=dt.datetime(2026,11,4,12,tzinfo=dt.timezone.utc)
        html=self._tanker_7country_html(
            post_id="8001",pub="2026-11-04T11:06:41+00:00"
        ).replace("October: 17.273","October: 17.273<br>November: 18.000")
        row=MODULE.parse_tankertrackers_seven_country_mtd(html,now)
        data=MODULE._extract_tankertrackers_7country_metrics([row])
        self.assertIsNotNone(data)
        self.assertEqual(data["month"],11)
        self.assertEqual(data["prev_mbd"],17.273)
        body=MODULE.build_physical_flow_alert_body(
            "tankertrackers_7country_crude_mtd",[row],None,now)
        self.assertIn("11월 잠정",body)
        self.assertIn("10월 비교",body)
        self.assertIn("하루 +72.7만 배럴 변화",body)
        self.assertNotIn("9월 비교",body)

    def test_tanker_monthly_rejects_mismatched_countries_or_weekly(self):
        now=dt.datetime(2026,10,14,2,0,tzinfo=dt.timezone.utc)
        for bad in ("Israel","Yemen","Bahrain","Syria","Egypt"):
            with self.subTest(extra_country=bad):
                with self.assertRaisesRegex(RuntimeError,"검증 불가"):
                    MODULE.parse_tankertrackers_seven_country_mtd(
                        self._tanker_7country_html(extra=bad),now)
        with self.assertRaisesRegex(RuntimeError,"검증 불가"):
            MODULE.parse_tankertrackers_seven_country_mtd(
                self._tanker_7country_html(extra="7 complete days"),now)

    def test_tanker_monthly_rejects_spoof_and_image_only_and_staleness(self):
        now=dt.datetime(2026,10,14,2,0,tzinfo=dt.timezone.utc)
        item=MODULE.parse_tankertrackers_seven_country_mtd(self._tanker_7country_html(),now)
        for invalid_url in (
            "http://t.me/tankertrackers/7890",
            "https://t.me.attacker.example/tankertrackers/7890",
            "https://t.me/anotherchannel/7890",
            "https://t.me/tankertrackers/7890?redirect=1",
        ):
            forged=MODULE.NewsItem(
                item.title,"TankerTrackers",invalid_url,
                item.published_utc,item.published_epoch,item.event_kind)
            self.assertIsNone(MODULE.confirm_event([forged]))
            self.assertIsNone(MODULE._extract_tankertrackers_7country_metrics([forged]))
        with self.assertRaisesRegex(RuntimeError,"검증 불가"):
            MODULE.parse_tankertrackers_seven_country_mtd(
                self._tanker_7country_html().replace("October: 17.273","<img src='chart.png'>"),now)
        with self.assertRaisesRegex(RuntimeError,"검증 불가"):
            MODULE.parse_tankertrackers_seven_country_mtd(
                self._tanker_7country_html(),now+dt.timedelta(days=4))

    def test_tanker_monthly_stable_dedup_vs_material_change(self):
        now=dt.datetime(2026,10,14,2,0,tzinfo=dt.timezone.utc)
        a=MODULE.parse_tankertrackers_seven_country_mtd(self._tanker_7country_html(),now)
        copy=MODULE.parse_tankertrackers_seven_country_mtd(
            self._tanker_7country_html(post_id="7891"),now)
        self.assertEqual(MODULE.event_id(a.event_kind,[a]),MODULE.event_id(copy.event_kind,[copy]))
        updated=MODULE.parse_tankertrackers_seven_country_mtd(
            self._tanker_7country_html(post_id="7892").replace("17.273","18.273"),now)
        self.assertNotEqual(MODULE.event_id(a.event_kind,[a]),MODULE.event_id(updated.event_kind,[updated]))
        state={"alerted_events":{MODULE.event_id(a.event_kind,[a]):now.astimezone(MODULE.KST).isoformat()}}
        selected,_=MODULE.select_unalerted_event(state,[(a.event_kind,[copy])],now)
        self.assertIsNone(selected)

    def test_tanker_monthly_no_source_feed_without_real_tables(self):
        now=dt.datetime(2026,10,14,2,0,tzinfo=dt.timezone.utc)
        forged="""
        <div class="tgme_widget_message" data-post="tankertrackers/33">
        <div class="tgme_widget_message_text">2026 Middle East Crude Oil Exports
        Iran Iraq Kuwait Qatar Saudi Arabia UAE Oman October 17.273 February 19.434
        </div><time datetime="2026-10-13T22:06:41+00:00"></time></div>
        """
        with self.assertRaisesRegex(RuntimeError,"검증 불가"):
            MODULE.parse_tankertrackers_seven_country_mtd(forged,now)

    def test_immutable_historical_sources_not_polled_after_expiry(self):
        # Old Reuters/Xinhua stories should not be fetched every hour indefinitely.
        before=dt.datetime(2026,10,8,13,tzinfo=dt.timezone.utc)
        inside=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        after=dt.datetime(2026,10,14,2,tzinfo=dt.timezone.utc)
        self.assertEqual(MODULE._historical_direct_loaders(before),())
        self.assertEqual(
            set(name for name,_ in MODULE._historical_direct_loaders(inside)),
            {"중국 Reuters 거래 관계자 보도","호르무즈 신화통신·타스님 인용 보도"}
        )
        self.assertEqual(MODULE._historical_direct_loaders(after),())

    def test_direct_historical_sources_expire(self):
        # Historical expiry tests must never read current live MMA reports. New official
        # releases make a fixed simulated October 16 date nondeterministic otherwise.
        import unittest.mock
        now=dt.datetime(2026,10,16,13,tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError,"유효기간"):
            MODULE.parse_china_reuters_resumption("",now)
        with self.assertRaisesRegex(RuntimeError,"신선도"):
            MODULE.parse_hormuz_xinhua_review("",now)

        pages={}
        for url,date,percent in (
            (MODULE.MMA_OIL_ISAIAS_OCT7_URL,"October 7, 2026",25.08),
            (MODULE.MMA_OIL_ISAIAS_OCT8_URL,"October 8, 2026",62.90),
            (MODULE.MMA_OIL_ISAIAS_OCT9_URL,"October 9, 2026",71.50),
        ):
            pages[url]=(
                f"Marine Minerals Administration Isaias {date} "
                "evacuated from a total of 129 production platforms. "
                f"approximately {percent:.2f}% of the current oil production "
                "and 58.90% of the current natural gas production. "
                "Oil, BOPD** Shut-in 1,450,000"
            )
        def offline_mma_fetch(url,timeout=16,attempts=1):
            if url==MODULE.MMA_ISAIAS_NEWS_INDEX_URL:
                return b"<html><body>No newer report</body></html>"
            if url in pages:
                return pages[url].encode("utf-8")
            raise RuntimeError("Unmocked test network access")
        with unittest.mock.patch.object(MODULE,"fetch_bytes",side_effect=offline_mma_fetch):
            with self.assertRaisesRegex(RuntimeError,"신선도"):
                MODULE.fetch_mma_isaias_snapshot(now)

    def test_hormuz_direct_source_requires_original_text(self):
        now=dt.datetime(2026,10,9,13,tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError,"미검증"):
            MODULE.parse_hormuz_xinhua_review("Hormuz opened for 7 days",now)
        row=MODULE.parse_hormuz_xinhua_review(
          "Araghchi seven-day plan Hormuz currently reviewing the US reply",now)
        self.assertEqual(row.event_kind,"hormuz_7day_diplomacy")

    def test_russia_diesel_announcement_and_license_are_separate_stages(self):
        promise = "Trump says Russia to immediately supply 300,000 tons of diesel fuel"
        gl = "OFAC Russia General License 135 issued 2026-10-09 authorizing Russian diesel transactions"
        self.assertEqual(MODULE.classify_event(promise), "russia_diesel_supply_transition")
        self.assertEqual(MODULE.classify_event(gl), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(promise), "deal_announced")
        self.assertEqual(MODULE._russian_diesel_supply_stage(gl), "us_license_issued")
        self.assertNotEqual(MODULE.classify_event(promise), "us_diesel_export_policy")

    def test_russia_diesel_real_ofac_primary_and_spoof_rejected(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        html = """
        <h1>Issuance of Russia-related General License</h1>
        <p>10/09/2026</p>
        <p>The Department of the Treasury's Office of Foreign Assets Control (OFAC)
        is issuing Russia-related General License 135, Authorizing Transactions
        Related to the Sale, Delivery, Offloading, and Importation of Diesel Fuel of Russian Federation Origin.</p>
        """
        row = MODULE.parse_ofac_russian_diesel_license(html, now)
        self.assertTrue(MODULE._russian_license_is_official(row))
        self.assertIsNotNone(MODULE.confirm_event([row]))
        bad = MODULE.NewsItem(row.title, row.source, "https://fake-ofac.example/recent-actions/20261009_33",
                              row.published_utc, row.published_epoch, row.event_kind)
        self.assertFalse(MODULE._russian_license_is_official(bad))
        self.assertIsNone(MODULE.confirm_event([bad]))
        with self.assertRaisesRegex(RuntimeError, "검증 실패"):
            MODULE.parse_ofac_russian_diesel_license(html.replace("135", "134"), now)

    def test_russia_rss_syndication_not_two_independent_sources(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        title = "Trump says Russia to immediately supply 300,000 tons of diesel fuel"
        rows = [
            MODULE.NewsItem(title, "Reuters", "https://www.reuters.com/business/energy/test",
                            now.isoformat(), now.timestamp(), "russia_diesel_supply_transition"),
            MODULE.NewsItem(title + " - Reuters", "MarketScreener", "https://marketscreener.com/reuters-test",
                            now.isoformat(), now.timestamp(), "russia_diesel_supply_transition"),
        ]
        self.assertIsNone(MODULE.confirm_event(rows))
        rows.append(MODULE.NewsItem("Trump strikes deal with Putin for Russian diesel",
                                   "Associated Press", "https://apnews.com/article/test",
                                   now.isoformat(), now.timestamp(), "russia_diesel_supply_transition"))
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "russia_diesel_supply_transition")

    def test_russia_rhetoric_never_proves_cargo_departure(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        title = "Trump says Russia to immediately supply 300,000 tons of diesel fuel"
        r = MODULE.NewsItem(title, "Reuters", "https://www.reuters.com/business/energy/test",
                            now.isoformat(), now.timestamp(), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(title), "deal_announced")
        self.assertNotIn("shipment_verified", [MODULE._russian_diesel_supply_stage(r.title)])
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([r]))
        bad = MODULE.NewsItem("Russia diesel shipments loaded onto tanker according to sources",
                              "Reuters", r.link, r.published_utc, r.published_epoch, r.event_kind)
        self.assertIsNone(MODULE.confirm_event([bad]))
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([bad]))

    def test_russia_same_license_not_sent_again_but_new_stage_can_alert(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_ofac_russian_diesel_license(
            "10/09/2026 Russia-related General License 135 authorizing transactions related to"
            " sale delivery offloading and importation of Diesel Fuel of Russian Federation Origin",
            now)
        eid = MODULE.event_id("russia_diesel_supply_transition", [row])
        state = {"alerted_events":{eid:now.astimezone(MODULE.KST).isoformat()}}
        result, duplicates = MODULE.select_unalerted_event(
            state, [("russia_diesel_supply_transition", [row])], now)
        self.assertIsNone(result)
        self.assertTrue(duplicates)

    def test_russia_alert_krw_and_conditional_volume_not_claimed_delivered(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_ofac_russian_diesel_license(
            "10/09/2026 Russia-related General License 135 authorizing transactions related to"
            " sale delivery offloading and importation of Diesel Fuel of Russian Federation Origin",
            now)
        body = MODULE.build_physical_flow_alert_body("russia_diesel_supply_transition",
                                                     [row], None, now)
        self.assertIn("30만 톤 초과", body)
        self.assertIn("480만 톤 초과", body)
        self.assertIn("정유시설 조건부 300만 톤", body)
        self.assertIn("실제 수출량 아님", body)
        self.assertIn("OFAC 제135호", body)
        self.assertNotIn("러시아 경유 실제 선적 복수 자료 확인", body)
        self.assertLessEqual(len(body.splitlines()), 38)

    def test_russia_license_is_not_resent_after_14_or_45_days(self):
        now = dt.datetime(2026, 10, 10, 0, tzinfo=dt.timezone.utc)
        row = MODULE.parse_ofac_russian_diesel_license(
            "10/09/2026 Russia-related General License 135 authorizing transactions related to"
            " sale delivery offloading and importation of Diesel Fuel of Russian Federation Origin",
            now
        )
        eid = MODULE.event_id("russia_diesel_supply_transition", [row])
        old_date = (now - dt.timedelta(days=70)).astimezone(MODULE.KST).isoformat()
        state = {"alerted_events": {eid: old_date}}
        self.assertTrue(MODULE.event_recently_alerted(state, eid, now))
        new_state = MODULE.build_pending_state(
            state, "another:event", "other", now, {}
        )
        self.assertIn(eid, new_state["alerted_events"])
        self.assertIsNone(
            MODULE.select_unalerted_event(
                new_state, [("russia_diesel_supply_transition", [row])], now
            )[0]
        )

    def test_russia_ap_original_title_independent_agreement(self):
        title = "Trump strikes deal with Putin for Russian diesel ahead of midterms"
        self.assertEqual(MODULE.classify_event(title), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(title), "deal_announced")

    def test_russia_novak_lifts_restrictions_but_not_loaded(self):
        title = "Novak says Russia starting to lift restrictions on diesel exports"
        self.assertEqual(MODULE.classify_event(title), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(title), "russian_ban_lifting_reported")
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([
            MODULE.NewsItem(title, "Reuters", "https://www.reuters.com/test", "2026-10-10T00:00Z", 0, "russia_diesel_supply_transition")
        ]))

    def test_russia_physical_requires_date_volume_and_two_independent_providers(self):
        now = dt.datetime(2026, 10, 12, 15, tzinfo=dt.timezone.utc)
        def row(title,source,url):
            return MODULE.NewsItem(title,source,url,now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        k = row("Kpler Russia diesel cargoes loaded 2026-10-12 300,000 metric tons IMO 1234567 Primorsk",
                "Kpler","https://www.kpler.com/reports/real-track")
        r = row("Reuters Russia diesel cargo departed 2026-10-12 300000 tonnes IMO 1234567 Primorsk",
                "Reuters","https://www.reuters.com/business/energy/real-report")
        self.assertEqual(MODULE.classify_event(k.title), "russia_diesel_supply_transition")
        self.assertEqual(MODULE._russian_diesel_supply_stage(k.title), "shipment_verified")
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k]))
        self.assertTrue(MODULE._russian_physical_shipment_confirmed([k,r]))
        self.assertIsNotNone(MODULE.confirm_event([k,r]))
        fp=MODULE._russian_shipment_fingerprint([k,r])
        self.assertEqual(fp,("2026-10-12",6,"1234567"))
        different_day = row(r.title.replace("2026-10-12","2026-10-13"),r.source,r.link)
        different_qty = row(r.title.replace("300000","600000"),r.source,r.link)
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,different_day]))
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,different_qty]))
        no_date = row(r.title.replace("2026-10-12",""),r.source,r.link)
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,no_date]))

    def test_russia_matching_date_volume_different_vessel_does_not_verify(self):
        now=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)
        make=lambda title,src,url: MODULE.NewsItem(title,src,url,now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        one=make("Kpler Russia diesel cargoes loaded 2026-10-12 300000 tonnes IMO 1234567 Primorsk","Kpler","https://www.kpler.com/reports/one")
        another=make("Reuters Russia diesel cargo departed 2026-10-12 300000 tonnes IMO 1234579 Primorsk","Reuters","https://www.reuters.com/business/energy/another")
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([one,another]))
        self.assertIsNone(MODULE.confirm_event([one,another]))

    def test_russia_matching_volume_date_different_port_does_not_verify(self):
        now=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)
        k=MODULE.NewsItem("Kpler Russia diesel cargoes loaded 2026-10-12 300000 tonnes IMO 1234567 Primorsk","Kpler","https://kpler.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        r=MODULE.NewsItem("Reuters Russia diesel cargo departed 2026-10-12 300000 tonnes IMO 1234567 Novorossiysk","Reuters","https://reuters.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,r]))

    def test_russia_shipments_require_imo_checksum_and_not_predeal(self):
        now=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)
        make=lambda title,src,url: MODULE.NewsItem(title,src,url,now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        k=make("Kpler Russia diesel cargoes loaded 2026-10-12 300000 tonnes IMO 1234567 Primorsk","Kpler","https://kpler.com/report")
        r=make("Reuters Russia diesel cargo departed 2026-10-12 300000 tonnes IMO 1234567 Primorsk","Reuters","https://reuters.com/report")
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,make(r.title.replace("1234567","1234568"),"Reuters",r.link)]))
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([k,make(r.title.replace("IMO 1234567",""),"Reuters",r.link)]))
        old_k=make(k.title.replace("2026-10-12","2026-10-08"),"Kpler",k.link)
        old_r=make(r.title.replace("2026-10-12","2026-10-08"),"Reuters",r.link)
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([old_k,old_r]))

    def test_russia_planned_loading_is_not_physical_and_late_reports_expire(self):
        now=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)
        k=MODULE.NewsItem("Kpler Russia diesel cargoes loaded 2026-10-12 300000 tonnes IMO 1234567 Primorsk","Kpler","https://kpler.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        plan="Reuters Russia will load diesel cargo 2026-10-12 300000 tonnes IMO 1234567 Primorsk"
        self.assertNotEqual(MODULE._russian_diesel_supply_stage(plan),"shipment_verified")
        r=MODULE.NewsItem("Reuters Russia diesel cargo departed 2026-10-12 300000 tonnes IMO 1234567 Primorsk","Reuters","https://reuters.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
        very_late=(now+dt.timedelta(days=9)).timestamp()
        late_k=MODULE.NewsItem(k.title,k.source,k.link,k.published_utc,very_late,k.event_kind)
        late_r=MODULE.NewsItem(r.title,r.source,r.link,r.published_utc,very_late,r.event_kind)
        self.assertFalse(MODULE._russian_physical_shipment_confirmed([late_k,late_r]))

    def test_russia_distinct_vessels_create_distinct_physical_event_ids(self):
        now=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)
        def cargo(imo):
            return [
                MODULE.NewsItem(f"Kpler Russia diesel cargoes loaded 2026-10-12 300000 tonnes IMO {imo} Primorsk","Kpler","https://kpler.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition"),
                MODULE.NewsItem(f"Reuters Russia diesel cargo departed 2026-10-12 300000 tonnes IMO {imo} Primorsk","Reuters","https://reuters.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
            ]
        self.assertNotEqual(
            MODULE.event_id("russia_diesel_supply_transition",cargo("1234567")),
            MODULE.event_id("russia_diesel_supply_transition",cargo("1234579")),
        )

    def test_russia_actual_shipments_dedup_by_observed_date_and_tons(self):
        now=dt.datetime(2026,10,12,15,tzinfo=dt.timezone.utc)
        def pair(day, qty):
            return [
                MODULE.NewsItem(f"Kpler Russia diesel cargoes loaded {day} {qty} tonnes IMO 1234567 Primorsk",
                    "Kpler","https://kpler.com/report",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition"),
                MODULE.NewsItem(f"Reuters Russia diesel cargo departed {day} {qty} tonnes IMO 1234567 Primorsk",
                    "Reuters","https://reuters.com/article",now.isoformat(),now.timestamp(),"russia_diesel_supply_transition")
            ]
        a=MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-12",300000))
        b=MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-13",300000))
        c=MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-12",400000))
        self.assertNotEqual(a,b)
        self.assertNotEqual(a,c)
        self.assertEqual(a,MODULE.event_id("russia_diesel_supply_transition",pair("2026-10-12",300000)))

    def test_china_fuel_export_suspension_classified(self):
        title = "Chinese refiners suspend October fuel exports, PetroChina cancels cargoes - Reuters"
        self.assertEqual(MODULE.classify_event(title), "china_fuel_export_policy")

    def test_china_fuel_export_resume_is_new_stage(self):
        now = dt.datetime(2026, 10, 8, 1, 0, tzinfo=dt.timezone.utc)
        suspended = MODULE.NewsItem(
            "Chinese refiners suspend October fuel exports outside Hong Kong and Macau",
            "Reuters", "a", now.isoformat(), now.timestamp(), "china_fuel_export_policy"
        )
        resumed = MODULE.NewsItem(
            "China resumes refined product exports after Beijing gives green light",
            "Reuters", "b", now.isoformat(), now.timestamp(), "china_fuel_export_policy"
        )
        self.assertNotEqual(
            MODULE.event_id("china_fuel_export_policy", [suspended]),
            MODULE.event_id("china_fuel_export_policy", [resumed]),
        )

    def test_china_fuel_export_body_keeps_official_status_cautious(self):
        now = dt.datetime(2026, 10, 1, 7, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Chinese refiners suspend October fuel exports, PetroChina cancels cargoes",
            "Reuters", "https://example.com/reuters", now.isoformat(), now.timestamp(), "china_fuel_export_policy"
        )]
        body = MODULE.build_physical_flow_alert_body("china_fuel_export_policy", rows, None, now)
        self.assertIn("중국 정책", body)
        self.assertIn("기존 10월 선적 취소", body)
        self.assertIn("10월 7일", body)
        self.assertIn("공식 전면 금지로 표현하지 않습니다", body)

    def test_india_gulf_import_recovery_is_classified(self):
        title = "Gulf crude imports to India recover to 1.52 mb/d in September - Kpler"
        self.assertEqual(MODULE.classify_event(title), "india_gulf_import_recovery")

    def test_regional_recovery_body_does_not_call_it_full_normalization(self):
        current = dt.datetime(2026, 9, 29, 4, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Middle East crude exports reach 12.8 million bpd, highest since the war",
            "Reuters", "a", current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("regional_export_recovery", news, None, current)
        self.assertIn("중동 수출     전쟁 후 최고 수준", body)
        self.assertIn("12.800 Mbd", body)
        self.assertIn("잠정 선박추적치는 확인이 붙으며 수정될 수 있음", body)
        self.assertIn("고정 숫자를 재사용하지 않고", body)

    def test_india_flow_body_uses_separate_baseline(self):
        current = dt.datetime(2026, 9, 29, 4, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Gulf crude imports to India recover to 1.52 mb/d in September",
            "Kpler", "a", current.isoformat(), current.timestamp(), "india_gulf_import_recovery"
        )]
        body = MODULE.build_physical_flow_alert_body("india_gulf_import_recovery", news, None, current)
        self.assertIn("인도 유입     걸프산 1.52 Mbd", body)
        self.assertIn("2025 평균 2.24 Mbd", body)
        self.assertIn("완전 정상화는 아닙니다", body)

    def test_distinct_event_not_blocked_by_recent_other_event(self):
        current = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        old_rows = [MODULE.NewsItem(
            "Kpler Gulf of Oman STS record 7.2 Mbd as of 2026-09-26; since-war average 3.7 Mbd; 2025 average 0.16 Mbd",
            "Kpler", "a", current.isoformat(), current.timestamp(), "sts_reroute_expansion"
        )]
        new_rows = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "b", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        old_id = MODULE.event_id("sts_reroute_expansion", old_rows)
        state = {
            "last_alert_at_kst": current.astimezone(MODULE.KST).isoformat(),
            "last_event_id": old_id,
            "alerted_events": {old_id: current.astimezone(MODULE.KST).isoformat()},
        }
        selected, duplicates = MODULE.select_unalerted_event(
            state,
            [
                ("sts_reroute_expansion", old_rows),
                ("east_west_pipeline_recovery", new_rows),
            ],
            current,
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected[0], "east_west_pipeline_recovery")
        self.assertIn("걸프오브오만 STS 우회 물류 급증·병목", duplicates)

    def test_doe_oct22_funding_no_delek_attribution_and_first_party_gate(self):
        now=dt.datetime(2026,10,25,1,tzinfo=dt.timezone.utc)
        html="""<html><body>October 22, 2026
        Energy Department to Use Defense Production Act Funding to Restart American Refinery and Expand Refining Capacity.
        up to $150 million in Defense Production Act Title III funding for refining, storage, logistics.
        $1 billion has been appropriated for energy-related projects.
        The selection process is ongoing and will be announced in the near future.
        </body></html>"""
        row=MODULE.parse_doe_oct22_refinery_program(html,now)
        self.assertEqual(row.event_kind,"us_dpa_refinery_funding_oct22")
        self.assertEqual(MODULE.event_id(row.event_kind,[row]),MODULE.DOE_OCT22_REFINERY_EVENT_ID)
        self.assertEqual(MODULE.confirm_event([row])[0],row.event_kind)
        body=MODULE.build_physical_flow_alert_body(row.event_kind,[row],None,now)
        self.assertIn("Delek 타일러 공장의 확정 수령액",body)
        self.assertIn("아직 선정 중",body)
        forged=MODULE.NewsItem(row.title,"인터넷 게시글","https://example.com",row.published_utc,row.published_epoch,row.event_kind)
        self.assertIsNone(MODULE.confirm_event([forged]))
        with self.assertRaises(ValueError):
            MODULE.event_id(row.event_kind,[forged])
        with self.assertRaises(RuntimeError):
            MODULE.parse_doe_oct22_refinery_program(html.replace("selection process is ongoing","recipients were selected"),now)

    def test_doe_oct22_funding_immutable_100days(self):
        now=dt.datetime(2027,2,20,tzinfo=dt.timezone.utc)
        old=dt.datetime(2026,10,25,tzinfo=dt.timezone.utc)
        eid=MODULE.DOE_OCT22_REFINERY_EVENT_ID
        self.assertTrue(MODULE.event_recently_alerted(
            {"alerted_events":{eid:old.astimezone(MODULE.KST).isoformat()}},eid,now))

    @staticmethod
    def _eia_2026_oct16_reversal_fixture():
        return """<html><body>Weekly Stocks Thousand Barrels
        09/11/26 09/18/26 09/25/26 10/02/26 10/09/26 10/16/26
        Total Crude Oil and Petroleum Products (Incl. SPR)
        1,536,205 1,535,908 1,528,080 1,520,383 1,506,999 1,498,245
        Crude Oil (Including SPR) 708,386 710,950 711,087 707,117 698,560 695,200
        Commercial Crude Oil (Excl. Lease Stock)
        423,429 426,398 427,320 424,134 415,577 412,517
        SPR 284,957 284,552 283,767 282,983 282,983 282,683
        Total Motor Gasoline 207,732 206,046 204,362 204,744 208,262 205,310
        Distillate Fuel Oil 107,859 107,431 105,180 105,138 102,611 104,286
        </body></html>"""

    def test_eia_oct16_inventory_reversal_is_meaningful(self):
        now=dt.datetime(2026,10,22,10,tzinfo=dt.timezone.utc)
        row=MODULE.parse_eia_weekly_stock_balance(self._eia_2026_oct16_reversal_fixture(),now)
        m=MODULE._eia_stock_metrics([row])
        self.assertEqual((m["c_delta"],m["g_delta"],m["d_delta"],m["spr_delta"]),
                         (-3060,-2952,1675,-300))

    def test_eia_oct16_old_news_cannot_fire_on_oct25(self):
        now=dt.datetime(2026,10,25,1,tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError,"기간 초과"):
            MODULE.parse_eia_weekly_stock_balance(self._eia_2026_oct16_reversal_fixture(),now)

    def test_iea_secondary_evidence_requires_two_publishers(self):
        now = dt.datetime(2026, 10, 17, 8, tzinfo=dt.timezone.utc)
        report = (
            "<html><body>PARIS, Oct 15 (Reuters) - The International Energy Agency "
            "(IEA) agreed on Thursday to accelerate release of remaining March "
            "stocks including over 20 million barrels of diesel; approximately "
            "330 million barrels released and 100 million barrels still expected. "
            "</body></html>"
        )
        a_source, a_url = MODULE.IEA_OCT15_REPORT_URLS[0]
        b_source, b_url = MODULE.IEA_OCT15_REPORT_URLS[2]
        a = MODULE.parse_iea_oct15_secondary_report(report, now, a_source, a_url)
        b = MODULE.parse_iea_oct15_secondary_report(report, now, b_source, b_url)
        kind = "iea_oct15_reserve_execution"
        self.assertIsNone(MODULE.confirm_event([a]))
        self.assertIsNotNone(MODULE.confirm_event([a, b]))
        self.assertTrue(MODULE.event_id(kind, [a,b]).startswith(kind+":"))
        self.assertIn("더내셔널", MODULE._build_iea_reserve_body([a,b],None,now,None))
        bad = MODULE.NewsItem(b.title,"개인 블로그","https://example.com",
                             b.published_utc,b.published_epoch,b.event_kind)
        self.assertIsNone(MODULE.confirm_event([a,bad]))
        with self.assertRaises(ValueError):
            MODULE.event_id(kind,[a,bad])

    def test_iea_secondary_rejects_missing_figures_and_unauthorized_url(self):
        now = dt.datetime(2026, 10, 17, 8, tzinfo=dt.timezone.utc)
        source, url = MODULE.IEA_OCT15_REPORT_URLS[2]
        with self.assertRaises(RuntimeError):
            MODULE.parse_iea_oct15_secondary_report("IEA diesel release",now,source,url)
        with self.assertRaises(RuntimeError):
            MODULE.parse_iea_oct15_secondary_report(
                "IEA October 15 March 2026 330 million 20 million diesel release",
                now,source,"https://example.com/blog")

    def test_historical_static_reports_stay_deduped_after_90_days(self):
        early = dt.datetime(2026, 10, 4, 1, tzinfo=dt.timezone.utc)
        later = early + dt.timedelta(days=90)
        for kind, event_id in (
            ("ex_iran_crude_prewar_recovery", "ex_iran_crude_prewar_recovery:unchanged"),
            ("saudi_asia_osp_change", "saudi_asia_osp_change:november2026"),
            ("eia_refining_crack_watch", "eia_refining_crack_watch:week20261009"),
            ("iea_oct15_reserve_execution", "iea_oct15_reserve_execution:2026-10-15-330-100-20plus"),
        ):
            state = {"alerted_events": {event_id: early.astimezone(MODULE.KST).isoformat()}}
            self.assertTrue(MODULE.event_recently_alerted(state, event_id, later))
            updated = MODULE.build_pending_state(state, "unrelated:new",
                                                "oil_flow_recovery", later, {})
            self.assertIn(event_id, updated["alerted_events"])
        changed = "saudi_asia_osp_change:december2026"
        state = {"alerted_events": {"saudi_asia_osp_change:november2026":
                                   early.astimezone(MODULE.KST).isoformat()}}
        self.assertFalse(MODULE.event_recently_alerted(state, changed, later))

    def test_same_event_is_suppressed_but_new_stage_passes(self):
        current = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        rate35 = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 3.5 million barrels per day",
            "Reuters", "a", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        rate40 = [MODULE.NewsItem(
            "Saudi East-West Pipeline transport hits 4.0 million barrels per day",
            "Reuters", "b", current.isoformat(), current.timestamp(), "east_west_pipeline_recovery"
        )]
        id35 = MODULE.event_id("east_west_pipeline_recovery", rate35)
        state = {"alerted_events": {id35: current.astimezone(MODULE.KST).isoformat()}}
        self.assertTrue(MODULE.event_recently_alerted(state, id35, current))
        selected, _ = MODULE.select_unalerted_event(
            state,
            [
                ("east_west_pipeline_recovery", rate35),
                ("east_west_pipeline_recovery", rate40),
            ],
            current,
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(MODULE.event_id(selected[0], selected[1]), MODULE.event_id("east_west_pipeline_recovery", rate40))

    def test_regional_single_reuters_does_not_confirm(self):
        now = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Middle East crude exports reach 12.8 million bpd, highest since the war",
            "Reuters", "a", now.isoformat(), now.timestamp(), "regional_export_recovery"
        )]
        self.assertIsNone(MODULE.confirm_event(rows))

    def test_regional_single_kpler_primary_can_confirm(self):
        now = dt.datetime(2026, 9, 29, 6, 0, tzinfo=dt.timezone.utc)
        rows = [MODULE.NewsItem(
            "Middle East crude exports reach 12.8 million bpd, highest since the war",
            "Kpler", "a", now.isoformat(), now.timestamp(), "regional_export_recovery"
        )]
        result = MODULE.confirm_event(rows)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "regional_export_recovery")

    def test_reuters_kpler_revised_snapshot_parser(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        html = """
        <html><body>
        Crude oil exports from key Middle East producers rebounded in September to
        16.328 million barrels per day (bpd), the highest since the war began.
        Exports via the Strait of Hormuz were set to hit about 9.719 million bpd this month.
        Regional exports were still about 3.2 million bpd down from 19.513 million bpd in February.
        Saudi Arabia was on track to ship about 5.4 million bpd this month.
        September shipments from Ras Tanura jumped to about 3.25 million bpd.
        </body></html>
        """
        item = MODULE.parse_mideast_export_snapshot(html, current, "https://example.com/reuters")
        self.assertEqual(item.event_kind, "regional_export_recovery")
        self.assertIn("16.328 Mbd", item.title)
        self.assertIn("9.719 Mbd", item.title)
        self.assertIn("19.513 Mbd", item.title)
        self.assertIn("83.7%", item.title)

    def test_regional_body_uses_revised_snapshot_not_hardcoded_old_value(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Middle East crude exports snapshot 16.328 Mbd; Hormuz 9.719 Mbd; February 19.513 Mbd; gap 3.185 Mbd; recovery 83.7%; Saudi 5.400 Mbd; RasTanura 3.250 Mbd; preliminary Kpler data may revise",
            "Reuters/Kpler",
            "https://example.com/reuters",
            current.isoformat(),
            current.timestamp(),
            "regional_export_recovery",
        )]
        body = MODULE.build_physical_flow_alert_body("regional_export_recovery", news, None, current)
        self.assertIn("16.328 Mbd", body)
        self.assertIn("9.719 Mbd", body)
        self.assertIn("19.513 Mbd", body)
        self.assertIn("83.7%", body)
        self.assertNotIn("12.8 Mbd", body)
        self.assertNotIn("18.8 Mbd", body)

    def test_regional_revision_creates_new_stage(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        old = [MODULE.NewsItem(
            "Middle East crude exports snapshot 12.800 Mbd; Hormuz 7.400 Mbd; February 18.800 Mbd; gap 6.000 Mbd; recovery 68.1%; preliminary Kpler data may revise",
            "Reuters/Kpler", "a", current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        revised = [MODULE.NewsItem(
            "Middle East crude exports snapshot 16.328 Mbd; Hormuz 9.719 Mbd; February 19.513 Mbd; gap 3.185 Mbd; recovery 83.7%; preliminary Kpler data may revise",
            "Reuters/Kpler", "b", current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        self.assertNotEqual(
            MODULE.event_id("regional_export_recovery", old),
            MODULE.event_id("regional_export_recovery", revised),
        )

    def test_usdkrw_format_marks_won_direction(self):
        now = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc).timestamp()
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1360.0, 1340.0, 20.0, 1.4925, "", now)
        text = MODULE.fmt_quote_line(fx)
        self.assertIn("1,360.00원", text)
        self.assertIn("원화 약세", text)

    def test_korea_transmission_block_oil_down_won_weak(self):
        current = dt.datetime(2026, 9, 29, 10, 0, tzinfo=dt.timezone.utc)
        news = [MODULE.NewsItem(
            "Middle East crude exports snapshot 16.328 Mbd; Hormuz 9.719 Mbd; February 19.513 Mbd; gap 3.185 Mbd; recovery 83.7%; preliminary Kpler data may revise",
            "Reuters/Kpler", "https://example.com/reuters",
            current.isoformat(), current.timestamp(), "regional_export_recovery"
        )]
        oil = MODULE.Quote("BZ=F", "Brent", "달러/배럴", 100.0, 103.0, -3.0, -2.91, "", current.timestamp())
        fx = MODULE.Quote("KRW=X", "원·달러", "원/달러", 1360.0, 1340.0, 20.0, 1.49, "", current.timestamp())
        body = MODULE.build_physical_flow_alert_body("regional_export_recovery", news, oil, current, fx)
        self.assertIn("[한국 전이]", body)
        self.assertIn("유가 ↓ 하지만 원화 약세", body)
        self.assertIn("실적 시즌", body)
        self.assertIn("원가 민감", body)
        self.assertIn("금리 경로", body)

    def test_alert_body_contains_required_market_values(self):
        current = dt.datetime(2026, 8, 2, 12, 0, tzinfo=dt.timezone.utc)
        news = [
            MODULE.NewsItem("US and Iran agree to ceasefire agreement", "Reuters", "a", current.isoformat(), current.timestamp(), "ceasefire"),
            MODULE.NewsItem("Iran ceasefire agreement takes effect", "Associated Press", "b", current.isoformat(), current.timestamp(), "ceasefire"),
        ]
        us2y = MODULE.Quote("^UST2Y", "미국 2년물 국채금리", "%", 4.20, 4.25, -0.05, -1.176, "", current.timestamp())
        dxy = MODULE.Quote("DX-Y.NYB", "달러인덱스", "", 99.50, 100.00, -0.50, -0.50, "", current.timestamp())
        oil = MODULE.Quote("CL=F", "WTI", "달러/배럴", 80.00, 85.00, -5.00, -5.882, "", current.timestamp())
        body = MODULE.build_alert_body("ceasefire", news, us2y, dxy, oil, current)
        self.assertIn("미국 2년물 국채금리: 4.200%", body)
        self.assertIn("달러인덱스: 99.50", body)
        self.assertIn("WTI: $80.00/배럴", body)
        self.assertIn("실패 경로", body)


    def test_oil_rate_treasury_parse_dates_and_reject_bad_table(self):
        table = ("<table><tr><th>Date</th><th>2 Yr</th><th>10 Yr</th></tr>"
                 "<tr><td>10/22/2026</td><td>4.6</td><td>5.12</td></tr>"
                 "<tr><td>10/23/2026</td><td>4.5</td><td>4.97</td></tr></table>")
        rows = MODULE.parse_treasury_ten_year_rows(table)
        self.assertEqual(rows[dt.date(2026,10,23)],4.97)
        with self.assertRaises(RuntimeError):
            MODULE.parse_treasury_ten_year_rows("<table><tr><td>10/23/2026</td><td>4.97</td></tr></table>")

    def test_oil_rate_brent_parsing_does_not_reuse_live_meta(self):
        import calendar
        t=lambda day:calendar.timegm(dt.datetime(2026,10,day,18).timetuple())
        payload={"chart":{"result":[{
            "meta":{"exchangeTimezoneName":"Europe/London","regularMarketPrice":200},
            "timestamp":[t(22),t(23)],
            "indicators":{"quote":[{"close":[110.0,114.0]}]},
        }]}}
        row=MODULE.parse_daily_brent_yahoo(payload)
        self.assertEqual(row["date"],"2026-10-23")
        self.assertEqual(row["prev_date"],"2026-10-22")
        self.assertEqual(row["price"],114.0)

    def test_oil_rate_signal_future_only_and_dates_must_match(self):
        ny=MODULE.ZoneInfo("America/New_York")
        now=dt.datetime(2026,10,26,18,tzinfo=ny)
        b={"date":"2026-10-22","prev_date":"2026-10-21","price":114.0,"prev_price":110.0}
        t={"date":"2026-10-22","prev_date":"2026-10-21","yield":4.90,"prev_yield":5.05}
        self.assertIsNone(MODULE.detect_oil_treasury_risk_signal(b,t,{},now))
        b["date"]="2026-10-26"
        self.assertIsNone(MODULE.detect_oil_treasury_risk_signal(b,t,{},now))

    def test_oil_rate_signal_reversal_needs_prior_confirmed_event(self):
        ny=MODULE.ZoneInfo("America/New_York")
        now=dt.datetime(2026,10,26,18,tzinfo=ny)
        b={"date":"2026-10-26","prev_date":"2026-10-23","price":116.0,"prev_price":112.0}
        t={"date":"2026-10-26","prev_date":"2026-10-23","yield":4.80,"prev_yield":4.96}
        first=MODULE.detect_oil_treasury_risk_signal(b,t,{},now)
        self.assertEqual(first["regime"],"안전자산선호")
        self.assertEqual(first["event_id"],"oil_treasury_regime:2026-10-26:안전자산선호")
        self.assertIn("27달러 위험 프리미엄",MODULE.oil_treasury_risk_alert_text(first,now,None))
        nextday=now+dt.timedelta(days=1)
        b.update(date="2026-10-27",prev_date="2026-10-26",price=116.5,prev_price=116.0)
        t.update({"date":"2026-10-27","prev_date":"2026-10-26","yield":4.92,"prev_yield":4.80})
        self.assertIsNone(MODULE.detect_oil_treasury_risk_signal(b,t,{},nextday))
        state={"alerted_events":{first["event_id"]:now.astimezone(MODULE.KST).isoformat()}}
        second=MODULE.detect_oil_treasury_risk_signal(b,t,state,nextday)
        self.assertEqual(second["regime"],"금리반등")
        self.assertFalse(MODULE.event_recently_alerted(state,second["event_id"],nextday))

    def test_oil_rate_physical_alert_only_on_material_divergence(self):
        now=dt.datetime(2026,10,26,18,tzinfo=dt.timezone.utc)
        oil=MODULE.Quote("BZ=F","Brent","달러/배럴",116,111,5,4.50,"",now.timestamp())
        text=MODULE.enhance_physical_oil_alert("ex_iran_crude_prewar_recovery","본문",oil)
        self.assertIn("원유 물량·가격 괴리",text)
        self.assertEqual(MODULE.enhance_physical_oil_alert("delek_tyler_dpa","본문",oil),"본문")


    def test_oil_rate_future_partial_candle_excluded_by_treasury_day(self):
        import calendar
        stamp=lambda day:calendar.timegm(dt.datetime(2026,10,day,18).timetuple())
        chart={"chart":{"result":[{
            "meta":{"exchangeTimezoneName":"Europe/London"},
            "timestamp":[stamp(23),stamp(26),stamp(27)],
            "indicators":{"quote":[{"close":[112.0,116.0,123.0]}]},
        }]}}
        selected=MODULE.parse_daily_brent_yahoo(chart,target_date="2026-10-26")
        self.assertEqual(selected["date"],"2026-10-26")
        self.assertEqual(selected["prev_date"],"2026-10-23")
        self.assertEqual(selected["price"],116.0)
        self.assertEqual(MODULE.parse_daily_brent_yahoo(chart)["date"],"2026-10-27")


    def test_google_rss_parallelism_bounded_preserves_queries_and_timeout(self):
        import inspect
        body=inspect.getsource(MODULE.fetch_news)
        self.assertIn("ThreadPoolExecutor(max_workers=6)",body)
        self.assertIn("pool.map(_one_news_feed, NEWS_QUERIES)",body)
        self.assertIn("fetch_bytes(google_news_url(query), timeout=4, attempts=1)",body)


if __name__ == "__main__":
    unittest.main()

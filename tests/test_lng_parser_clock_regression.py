"""Historical parser fixtures never disable live-source freshness guards."""
import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import lng_supply_crisis_alert_v34 as monitor

FIXTURE_NOW = dt.datetime(2026, 9, 25, 12, tzinfo=dt.timezone.utc)
TTF = '''실제 이전 최고 최저 날짜 단위 업데이트 주기 71.89 74.94 345 3.37
유럽연합 가스 71.89 -3.05 -4.07%
2026년 9월 25일 EU 가스는'''
JKM = '''실제 이전 최고 최저 날짜 단위 업데이트 주기 25.82 26.385 69.96 2.00
LNG JKM 25.82 -0.57 -2.14%
2026년 9월 25일 LNG JKM'''


class GIEStorageAlertRegressionTest(unittest.TestCase):
    @staticmethod
    def fixture(date="21/10/2026", eu_pct="74.62"):
        return f"""<html><body><h1>Welcome at GIE - Gas Infrastructure Europe</h1>
        <p>Status on {date} at 6AM CEST</p>
        <div>EU 0.01 845.02 TWh stored {eu_pct}% full</div>
        <div>AT -0.10 69.28 TWh stored 69.09% full</div>
        <div>DE 0.04 151.36 TWh stored 61.19% full</div>
        <div>NL 0.09 93.12 TWh stored 64.65% full</div>
        <div>Country Trend Gas In Storage</div></body></html>"""

    def test_gie_official_same_row_and_date_parsed(self):
        now=dt.datetime(2026,10,23,0,tzinfo=dt.timezone.utc)
        p=monitor._parse_gie_storage_homepage_v34(self.fixture(),now=now)
        self.assertEqual(p["date"],"2026-10-21")
        self.assertAlmostEqual(p["eu_pct"],74.62)
        self.assertAlmostEqual(p["de_pct"],61.19)
        self.assertAlmostEqual(p["nl_pct"],64.65)
        self.assertAlmostEqual(p["eu_twh"],845.02)

    def test_gie_stale_future_or_incomplete_blocks(self):
        now=dt.datetime(2026,10,23,0,tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(RuntimeError,"기준일 지연"):
            monitor._parse_gie_storage_homepage_v34(self.fixture("10/10/2026"),now=now)
        with self.assertRaisesRegex(RuntimeError,"기준일 지연"):
            monitor._parse_gie_storage_homepage_v34(self.fixture("31/10/2026"),now=now)
        with self.assertRaisesRegex(RuntimeError,"DE 저장량"):
            monitor._parse_gie_storage_homepage_v34(self.fixture().replace("DE 0.04 151.36 TWh stored 61.19% full",""),now=now)
        with self.assertRaisesRegex(RuntimeError,"저장용량 검산"):
            monitor._parse_gie_storage_homepage_v34(self.fixture(eu_pct="5.00"),now=now)

    def test_storage_risk_enter_and_recovery_dedupe(self):
        now=dt.datetime(2026,10,23,0,tzinfo=dt.timezone.utc)
        p=monitor._parse_gie_storage_homepage_v34(self.fixture(),now=now)
        with patch.object(monitor.core,"now_utc",return_value=now):
            q=monitor._gie_storage_quote_v34(p)
        entered=monitor._signals_with_storage_v34({"eu_storage":q},set())
        self.assertIn("eu_storage_below_75",entered)
        self.assertIn("eu_storage_below_80",entered)
        self.assertIn("de_storage_below_65",entered)
        self.assertIn("nl_storage_below_65",entered)
        self.assertEqual(monitor._signals_with_storage_v34({"eu_storage":q},entered),entered)
        self.assertEqual(monitor._signals_with_storage_v34({},entered),entered)
        self.assertTrue(monitor._should_alert_with_storage_v34([],set(),{"eu_storage_below_75"}))

    def test_price_90_100_and_150_are_not_forecast_alerts(self):
        thresholds=monitor.core.PRICE_SPECS["ttf"]["levels"]
        self.assertTrue(all(x in thresholds for x in (90.0,100.0,120.0,150.0)))
        self.assertIn("TTF 추종",monitor._signal_label_with_storage_v34("ttf_above_90"))
        self.assertIn("150유로",monitor._signal_label_with_storage_v34("ttf_above_150"))

    def test_ecb_official_rate_and_risk_scenario_context(self):
        now=dt.datetime(2026,10,23,0,tzinfo=dt.timezone.utc)
        sample='''<Envelope xmlns="http://www.gesmes.org/xml/2002-08-01">
          <Cube><Cube time="2026-10-22"><Cube currency="KRW" rate="1489.15"/></Cube></Cube>
          </Envelope>'''
        r=monitor._parse_ecb_eurkrw_v34(sample,now=now)
        self.assertEqual(r["rate"],1489.15)
        self.assertEqual(r["date"],"2026-10-22")
        p=monitor._parse_gie_storage_homepage_v34(self.fixture(),now=now)
        with patch.object(monitor.core,"now_utc",return_value=now):
            storage=monitor._gie_storage_quote_v34(p)
        fx=monitor._ecb_quote_v34(r)
        title,body,meta=monitor._build_with_gie_storage_v34(
            [],{"eu_storage":storage,"eurkrw":fx},
            {"eu_storage_below_75"},set()
        )
        self.assertIn("저장률 경보",title)
        self.assertIn("74.62%",body)
        self.assertIn("61.19%",body)
        self.assertIn("150유로/MWh",body)
        self.assertIn("25% 이하",body)
        self.assertIn("GIE AGSI+",body)
        self.assertEqual(meta["europe_gas_storage_v34"]["storage_source_date"],"2026-10-21")


class ParserClockRegressionTest(unittest.TestCase):
    def test_historical_fixture_self_validation_survives_clock_rollover(self):
        for year in (2026, 2036):
            with self.subTest(year=year), patch.object(monitor.core, 'now_utc', return_value=dt.datetime(year, 10, 11, tzinfo=dt.timezone.utc)):
                monitor._self_validate_canonical_price_parsers_v34()

    def test_default_live_clock_still_rejects_stale_prices(self):
        with patch.object(monitor.core, 'now_utc', return_value=dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)):
            for key, fixture in [('ttf', TTF), ('jkm', JKM)]:
                with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'stale source date=2026-09-25'):
                    monitor._parse_te_korean_detail_v34(fixture, key)

    def test_freshness_boundary_and_future_dates(self):
        for key, fixture in [('ttf', TTF), ('jkm', JKM)]:
            for age in (-1, 0, monitor.TE_MAX_AGE_DAYS_V34, monitor.TE_MAX_AGE_DAYS_V34 + 1):
                with self.subTest(key=key, age=age):
                    now = FIXTURE_NOW + dt.timedelta(days=age)
                    if age < 0 or age > monitor.TE_MAX_AGE_DAYS_V34:
                        with self.assertRaisesRegex(RuntimeError, 'stale source date'):
                            monitor._parse_te_korean_detail_v34(fixture, key, now=now)
                    else:
                        self.assertEqual(monitor._parse_te_korean_detail_v34(fixture, key, now=now)['source_date'], dt.date(2026, 9, 25))

    def test_same_page_arithmetic_disagreement_remains_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'internal values disagree'):
            monitor._parse_te_korean_detail_v34(TTF.replace('-4.07%', '+4.07%'), 'ttf', now=FIXTURE_NOW)

    def test_missing_date_remains_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'source date not found'):
            monitor._parse_te_korean_detail_v34(TTF.replace('2026년 9월 25일 EU 가스는', ''), 'ttf', now=FIXTURE_NOW)

class LNGMaritimeEvidenceRegressionTest(unittest.TestCase):
    @staticmethod
    def item(title, source="Reuters", polarity="worsening", day=19, hour=11, subtype="reroute", official=False):
        date = dt.datetime(2026, 10, day, hour, tzinfo=dt.timezone.utc)
        return monitor.core.NewsItem(
            category="hormuz_shipping",
            polarity=polarity,
            subtype=subtype,
            title=title,
            source=source,
            link=f"https://news.google.com/rss/articles/fixture-{source.replace(' ', '-')}",
            published_utc=date.isoformat(),
            published_epoch=date.timestamp(),
            official=official,
            event_id=f"fixture-{source}-{day}-{hour}",
        )

    def test_rare_qatar_red_sea_delivery_not_an_LNG_worsening(self):
        item = self.item("Qatar LNG Cargo Makes Rare Red Sea Journey to Get Gas to Europe", "gCaptain")
        self.assertIsNone(monitor._hormuz_lng_claim_v34(item))
        self.assertFalse(monitor._is_lng_relevant_item_v34(item))

    def test_container_ship_attacks_are_not_LNG_shortage_proof(self):
        item = self.item("Strait of Hormuz scoured for spilt cargo after Iran attacks container ships", "The Guardian")
        self.assertIsNone(monitor._hormuz_lng_claim_v34(item))
        self.assertFalse(monitor._is_lng_relevant_item_v34(item))

    def test_the_two_october_19_articles_cannot_confirm_LNG_shortage(self):
        candidates = [
            self.item("Qatar LNG Cargo Makes Rare Red Sea Journey to Get Gas to Europe", "gCaptain"),
            self.item("Strait of Hormuz scoured for spilt cargo after Iran attacks container ships", "The Guardian"),
        ]
        self.assertFalse(any(g.get("category") == "hormuz_shipping" for g in monitor.confirmed_news_groups_v34(candidates)))

    def test_two_distinct_LNG_shipping_stories_are_not_the_same_event(self):
        candidates = [
            self.item("Qatar LNG tanker struck in Gulf off Qatar", "Reuters"),
            self.item("Qatar LNG shipping disruption at Strait of Hormuz keeps LNG vessels blocked", "The Guardian"),
        ]
        self.assertFalse(any(g.get("category") == "hormuz_shipping" for g in monitor.confirmed_news_groups_v34(candidates)))

    def test_two_independent_same_LNG_shipping_disruption_can_confirm(self):
        a = self.item("LNG shipping disruption at Strait of Hormuz keeps Qatar LNG vessels outside the strait", "Reuters")
        b = self.item("Qatar LNG tanker traffic remains disrupted through Strait of Hormuz", "S&P Global Commodity Insights", hour=12)
        groups = monitor.confirmed_news_groups_v34([a, b])
        matches = [g for g in groups if g.get("category") == "hormuz_shipping"]
        self.assertEqual(len(matches), 1)
        self.assertIn("원문 본문 미열람", matches[0]["verification"])
        labels = [monitor._title_ko_v34(row) for row in matches[0]["evidence"]]
        self.assertTrue(all("호르무즈" in label and "LNG" in label for label in labels))
        self.assertTrue(all("관련 확정 변화" not in label for label in labels))

    def test_stable_fingerprint_across_reprints(self):
        a = self.item("LNG shipping disruption at Strait of Hormuz keeps Qatar LNG vessels outside the strait", "Reuters")
        b = self.item("Qatar LNG tanker traffic remains disrupted through Strait of Hormuz", "S&P Global Commodity Insights", hour=12)
        original = monitor.confirmed_news_groups_v34([a, b])
        followup = monitor.confirmed_news_groups_v34([
            self.item(a.title, "Reuters", day=20),
            self.item(b.title, "S&P Global Commodity Insights", day=20, hour=12),
        ])
        self.assertEqual(original[0]["event_id"], followup[0]["event_id"])

    def test_unknown_shipping_title_blocks_generic_korean_certainty(self):
        row = self.item("Qatar LNG Cargo Makes Rare Red Sea Journey to Get Gas to Europe", "gCaptain")
        with self.assertRaisesRegex(RuntimeError, "실제 LNG 사건"):
            monitor._title_ko_v34(row)

    def test_google_news_redirect_is_labeled_as_indirect_source(self):
        a = self.item("LNG shipping disruption at Strait of Hormuz keeps Qatar LNG vessels outside the strait", "Reuters")
        b = self.item("Qatar LNG tanker traffic remains disrupted through Strait of Hormuz", "S&P Global Commodity Insights")
        groups = monitor.confirmed_news_groups_v34([a, b])
        body = "\n".join(monitor._evidence_lines_v34(groups))
        self.assertIn("기사 확인(뉴스 경유)", body)
        self.assertNotIn("관련 확정 변화", body)

    def test_official_one_source_requires_real_LNG_event(self):
        unrelated = self.item("Oil tankers attacked near Hormuz, gas shipping remains uncertain", "UKMTO", official=True)
        self.assertFalse(any(g.get("category") == "hormuz_shipping" for g in monitor.confirmed_news_groups_v34([unrelated])))

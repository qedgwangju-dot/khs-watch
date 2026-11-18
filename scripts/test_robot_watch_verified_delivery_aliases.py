"""Regression evidence for the five actually delivered Nov 16 ESS reprints."""
from __future__ import annotations

import copy
import hashlib
import html
from types import SimpleNamespace
import unittest

import robot_watch_verified_delivery_aliases as aliases
import robotis_physical_ai_watch as original


# Report positions 1, 5, 6, 7, 8; last_selected in the verified run artifact.
DELIVERED = (
    ("'脫중국' 앞세운 삼성SDI… 美서 수조원대 ESS 배터리 수주", "파이낸셜뉴스", "2026-11-16T09:21:00+00:00"),
    ("[ET특징주]삼성SDI, 수조원대 ESS 배터리 수주에 상승세", "전자신문", "2026-11-16T04:28:00+00:00"),
    ("삼성SDI, 美서 수조원대 ESS 수주…LFP로 영역 확장", "서울경제TV", "2026-11-16T09:20:00+00:00"),
    ("삼성SDI, 수조원대 美 ESS 배터리 공급 계약", "뉴스톱", "2026-11-16T06:28:00+00:00"),
    ("삼성SDI, 미국서 수조원대 에너지저장장치 배터리 수주", "연합뉴스TV", "2026-11-15T23:35:00+00:00"),
)
DAILYMAKER_TITLE = "북미 ESS 시장 '뭉칫돈'…삼성SDI, 16GWh 공급 계약"
SEOUL_TITLE = "삼성SDI, 美 LFP 양산하자마자 4조 대형수주…ESS 공급망 넓힌다"


def daily_row():
    return dict(title=DAILYMAKER_TITLE + " - 데일리메이커", source="데일리메이커",
                published="2026-11-18T02:18:21+00:00", description=DAILYMAKER_TITLE + " 데일리메이커",
                link="https://news.google.com/rss/articles/verified-dailymaker",
                group="ess_battery", score=30)


def seoul_row():
    return dict(title=SEOUL_TITLE + " - 서울이코노미뉴스", source="서울이코노미뉴스",
                published="2026-11-16T02:08:30+00:00", description=SEOUL_TITLE + " 서울이코노미뉴스",
                link="https://news.google.com/rss/articles/verified-seoul",
                group="ess_battery", score=30)


def rows():
    return [dict(title=t, source=s, published=d, description=t + " " + s,
                 link="https://news.google.com/rss/articles/example",
                 group="ess_battery", score=30)
            for t, s, d in DELIVERED]


def upstream_key(item):
    # Preserve the production fallback's title-only collision, so tests catch
    # the real issue where new facts appear only in the RSS description.
    for (title, source, _), key in zip(DELIVERED, aliases.DELIVERED_KEYS):
        if item["title"] in (title, title + " - " + source) and item["source"] == source:
            return key
    if item["title"] in (DAILYMAKER_TITLE, DAILYMAKER_TITLE + " - 데일리메이커") and item["source"] == "데일리메이커":
        return aliases.DAILYMAKER_DELIVERED_KEY
    if item["title"] in (SEOUL_TITLE, SEOUL_TITLE + " - 서울이코노미뉴스") and item["source"] == "서울이코노미뉴스":
        return aliases.SEOUL_DELIVERED_KEY
    return hashlib.sha256((item["title"] + "|" + item["source"]).encode()).hexdigest()


class VerifiedDeliveryAliasesTest(unittest.TestCase):
    def setUp(self):
        self.base = SimpleNamespace(
            key=upstream_key, select_diverse=original.select_diverse,
            score=lambda item: item["score"], topic_group=lambda text: "ess_battery",
            load_state=lambda: {"seen": list(aliases.DELIVERED_KEYS), "seeded": True},
            QUERIES=["existing query"], FORCE=False, MAX_ALERTS=8,
        )
        self.before = vars(self.base).copy()
        aliases.install(self.base)

    def selected(self, items, seen):
        enriched = [dict(item, key=self.base.key(item)) for item in items]
        return self.base.select_diverse(enriched, seen, False, 8)

    def test_five_delivered_publishers_share_existing_key(self):
        for item in rows():
            with self.subTest(source=item["source"]):
                self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)
        self.assertIn(aliases.CANONICAL_KEY, aliases.DELIVERED_KEYS)

    def test_existing_seen_means_no_alert_and_is_not_rewritten(self):
        seen = set(aliases.DELIVERED_KEYS) | {"unrelated-existing-key"}
        saved = seen.copy()
        self.assertEqual(self.selected(rows(), seen), [])
        self.assertEqual(seen, saved)
        self.assertTrue(set(aliases.DELIVERED_KEYS).issubset(seen))

    def test_unseen_event_produces_one_item_not_five(self):
        self.assertEqual(len(self.selected(rows(), set())), 1)

    def test_article_and_score_group_are_not_mutated(self):
        item = rows()[0]
        saved = copy.deepcopy(item)
        self.base.key(item)
        self.assertEqual(item, saved)
        for name, value in self.before.items():
            if name != "key":
                self.assertIs(getattr(self.base, name), value, name)

    def test_install_is_idempotent(self):
        installed = self.base.key
        aliases.install(self.base)
        self.assertIs(self.base.key, installed)

    def test_html_rss_and_publisher_suffix_are_reprints(self):
        for item in rows():
            item["title"] += " - " + item["source"]
            item["description"] = ('<a href="https://example.com">' +
                                   html.escape(item["title"]) +
                                   '</a>&nbsp;&nbsp;<font>' + item["source"] + '</font>')
            self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)

    def test_precise_same_event_new_publisher_is_aliased(self):
        item = dict(rows()[4], source="다른 신뢰 매체", description="")
        self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)

    def test_ambiguous_no_us_country_is_not_aliased_for_new_publisher(self):
        item = dict(rows()[1], source="다른 매체", description="")
        self.assertEqual(self.base.key(item), upstream_key(item))

    def test_other_dates_and_unknown_date_keep_upstream_key(self):
        for date in ("2026-11-15T00:00:00+09:00", "2026-11-19T00:00:00+09:00",
                     "2025-11-16T09:00:00+09:00", None, "bad-date",
                     "2026-11-16T09:00:00"):
            item = dict(rows()[3], published=date)
            with self.subTest(date=date):
                self.assertEqual(self.base.key(item), upstream_key(item))

    def test_publication_dates_use_kst(self):
        self.assertEqual(self.base.key(rows()[4]), aliases.CANONICAL_KEY)
        item = dict(rows()[3], published="2026-11-18T14:59:59Z")
        self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)
        item["published"] = "2026-11-18T15:00:00Z"
        self.assertEqual(self.base.key(item), upstream_key(item))

    def test_new_headline_facts_keep_their_upstream_identity(self):
        additions = (
            "…미국 신규 고객 Blue Valley Energy 공개",
            "…계약금액 3조원 확정", "…계약물량 20GWh 공개",
            "…추가 수주", "…첫 납품 완료", "…공식 공시 확정",
        )
        seen = set(aliases.DELIVERED_KEYS)
        for extra in additions:
            item = dict(rows()[3], title=rows()[3]["title"] + extra, description="")
            with self.subTest(extra=extra):
                self.assertEqual(self.base.key(item), upstream_key(item))
                self.assertEqual(len(self.selected([item], seen)), 1)

    def test_new_description_facts_escape_old_title_key_collision(self):
        facts = (
            "신규 고객은 Blue Valley Energy로 확인됐다.",
            "계약금액 3조원, 계약물량 20GWh가 공개됐다.",
            "추가 수주 계약을 체결했다.",
            "첫 납품을 완료하고 매출 인식을 시작했다.",
            "삼성SDI가 공식 공시를 통해 계약물량 20GWh를 확정했다.",
        )
        seen = set(aliases.DELIVERED_KEYS)
        for description in facts:
            item = dict(rows()[3], description=description)
            with self.subTest(description=description):
                self.assertIn(upstream_key(item), seen)
                self.assertNotIn(self.base.key(item), seen)
                self.assertEqual(len(self.selected([item], seen)), 1)
                self.assertEqual(self.base.key(item), self.base.key(dict(item)))

    def test_primary_grade_alone_is_not_new_after_company_confirmed_baseline(self):
        for change in (
            {"source": "삼성SDI"},
            {"source_url": "https://www.samsungsdi.com/newsroom"},
            {"link": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=example"},
            {"primary_feed": "Samsung SDI newsroom"},
        ):
            item = dict(rows()[3], description="", **change)
            with self.subTest(change=change):
                self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)

    def test_actual_dailymaker_reprint_uses_original_delivered_key(self):
        item = daily_row()
        self.assertEqual(upstream_key(item), aliases.DAILYMAKER_DELIVERED_KEY)
        self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)
        self.assertEqual(self.selected([item], set(aliases.DELIVERED_KEYS)), [])

    def test_second_actual_seoul_reprint_uses_original_key(self):
        item = seoul_row()
        self.assertEqual(upstream_key(item), aliases.SEOUL_DELIVERED_KEY)
        self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)
        self.assertEqual(self.selected([item], set(aliases.DELIVERED_KEYS)), [])
        changed = dict(item, description="주피터파워 계약물량을 20GWh로 변경했다.")
        self.assertNotIn(self.base.key(changed), aliases.HISTORICAL_EVENT_KEYS)

    def test_reported_estimate_and_previous_order_are_not_new_contract_price(self):
        item = dict(daily_row(), title="삼성SDI, 주피터파워 16GWh ESS 계약",
                    description="계약 규모는 3조~4조원으로 알려졌다. 2029년부터 3년간 공급하며, "
                                "앞서 11GWh 계약을 포함한 누적 물량은 27GWh다.")
        self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)
        item["description"] = "회사가 계약금액 3조원을 공식 확정했다. 2029년부터 3년간 공급한다."
        self.assertNotEqual(self.base.key(item), aliases.CANONICAL_KEY)

    def test_jupiter_named_customer_quantity_period_and_cumulative_are_old_facts(self):
        baseline = ("삼성SDI의 신규 고객은 주피터파워로 확인됐다. 계약물량 16GWh가 공개됐다. "
                    "2029년부터 3년간 공급하며 양사 누적 공급계약은 27GWh, 금액은 수조원 추산이다.")
        for item in (dict(rows()[0], description=baseline), dict(daily_row(), description=baseline),
                     dict(daily_row(), title="삼성SDI, 주피터파워와 16GWh ESS용 공급 계약", source="삼성SDI", description=baseline),
                     dict(daily_row(), title="Samsung SDI secures 16 GWh LFP battery order from Jupiter Power", source="Samsung SDI",
                          description="Supply 16 GWh over three years starting in 2029; total orders 27GWh including previous deal.")):
            with self.subTest(title=item["title"]):
                self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)

    def test_verified_official_release_does_not_create_primary_upgrade(self):
        item = dict(rows()[0], source="Samsung SDI Newsroom",
                    link="https://news.samsungsdi.com/global/articleView?seq=477",
                    description="Jupiter Power signed an agreement for 16 GWh LFP batteries over three years starting in 2029. "
                                "Total orders reach 27GWh. Its project pipeline includes 19,700 MWh operating and 110,000 MWh in development.")
        self.assertEqual(self.base.key(item), aliases.CANONICAL_KEY)

    def test_changed_contract_values_period_and_actual_delivery_escape_daily_key(self):
        changes = ("주피터파워 계약물량을 20GWh로 변경했다.",
                   "주피터파워 누적 계약물량은 30GWh로 확대됐다.",
                   "주피터파워 공급은 2030년부터 3년간 진행한다.",
                   "주피터파워 공급기간은 2029~2032년으로 변경됐다.",
                   "주피터파워에 2029년부터 4년간 공급한다.",
                   "주피터파워 계약금액은 3조원으로 확정됐다.",
                   "주피터파워 초도 납품을 완료했다.",
                   "주피터파워와 추가 16GWh 별도 계약을 체결했다.")
        seen = set(aliases.HISTORICAL_EVENT_KEYS)
        for change in changes:
            item = dict(daily_row(), description=change)
            with self.subTest(change=change):
                self.assertNotIn(self.base.key(item), seen)
                self.assertEqual(len(self.selected([item], seen)), 1)

    def test_known_original_title_also_preserves_changed_date_or_counterparty(self):
        for description in ("주피터파워 공급은 2030년부터 3년간 진행한다.",
                            "계약 상대방은 Blue Valley Energy다.",
                            "주피터파워 계약물량은 20GWh다."):
            item = dict(rows()[3], description=description)
            with self.subTest(description=description):
                self.assertNotIn(self.base.key(item), aliases.HISTORICAL_EVENT_KEYS)

    def test_another_customer_or_separate_contract_is_not_consumed(self):
        for customer in ("Tesla", "Blue Valley Energy", "Alpha Omega Power"):
            item = dict(daily_row(), description=f"이번 계약 상대방은 {customer}다. 기존 주피터파워 계약과는 별도 계약이다.")
            self.assertNotIn(self.base.key(item), aliases.HISTORICAL_EVENT_KEYS)
            item = dict(daily_row(), title=f"삼성SDI, {customer}와 16GWh ESS 공급 계약",
                        description="기존 주피터파워와 16GWh, 누적 27GWh 계약도 보유하고 있다.")
            self.assertEqual(self.base.key(item), upstream_key(item))
            self.assertNotEqual(self.base.key(item), aliases.CANONICAL_KEY)

    def test_unverified_generic_16gwh_and_other_dates_remain_conservative(self):
        item = dict(daily_row(), source="미확인 매체", description="")
        self.assertEqual(self.base.key(item), upstream_key(item))
        item = dict(daily_row(), published="2027-11-18T02:18:21+00:00")
        self.assertEqual(self.base.key(item), upstream_key(item))

    def test_unknown_body_is_conservatively_left_to_upstream(self):
        item = dict(rows()[3], description="기업 실적에 대한 새로운 상세 해설입니다.")
        self.assertEqual(self.base.key(item), upstream_key(item))

    def test_plans_and_negations_do_not_create_achieved_stage(self):
        for description in (
            "신규 고객 공개 예정입니다.", "신규 고객은 아직 미공개입니다.",
            "계약금액 3조원 공개 계획입니다.", "추가 수주 계약 체결을 협의 중입니다.",
            "첫 납품 완료 예정입니다.", "공식 공시로 확정하지 않았습니다.",
        ):
            item = dict(rows()[3], description=description)
            with self.subTest(description=description):
                self.assertEqual(self.base.key(item), upstream_key(item))

    def test_other_sdi_events_and_other_companies_untouched(self):
        for title in (
            "삼성SDI, 헝가리 ESS 공장 가동 중단", "삼성SDI, 미국 전기차 배터리 수주",
            "삼성SDI, 국내 수조원대 ESS 수주", "삼성SDI, 미국 ESS 10GWh 수주",
            "LG에너지솔루션, 미국 수조원대 ESS 배터리 수주",
        ):
            item = dict(rows()[3], title=title, description="")
            with self.subTest(title=title):
                self.assertEqual(self.base.key(item), upstream_key(item))


if __name__ == "__main__":
    unittest.main()

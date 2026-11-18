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
            "삼성SDI가 공식 공시를 통해 공급 계약을 확정했다.",
        )
        seen = set(aliases.DELIVERED_KEYS)
        for description in facts:
            item = dict(rows()[3], description=description)
            with self.subTest(description=description):
                self.assertIn(upstream_key(item), seen)
                self.assertNotIn(self.base.key(item), seen)
                self.assertEqual(len(self.selected([item], seen)), 1)
                self.assertEqual(self.base.key(item), self.base.key(dict(item)))

    def test_primary_evidence_never_collapses_into_press_alias(self):
        for change in (
            {"source": "삼성SDI"},
            {"source_url": "https://www.samsungsdi.com/newsroom"},
            {"link": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=example"},
            {"primary_feed": "Samsung SDI newsroom"},
        ):
            item = dict(rows()[3], **change)
            with self.subTest(change=change):
                self.assertNotIn(self.base.key(item), aliases.DELIVERED_KEYS)

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

import datetime as dt
import unittest

from scripts import france_credit_carry_overlay as watch

EXAMPLE_EN = """
<table><thead><tr><th>Agency</th><th>Rating</th><th>Outlook</th><th>Last rating</th><th>Next date</th></tr></thead>
<tbody>
<tr><td><a href="#">Fitch</a></td><td>A+</td><td>Stable</td><td>28 August 2026</td><td>-</td></tr>
<tr><td><a href="#">Moody's</a></td><td>Aa3</td><td>Negative</td><td>10 April 2026</td><td>23 October 2026</td></tr>
<tr><td>Standard &amp; Poor's</td><td>A+</td><td>Stable</td><td>29 May 2026</td><td>27 November 2026</td></tr>
</tbody></table>
"""
EXAMPLE_FR = """
<table><tr><td>Moody's</td><td>Aa3</td><td>Négative</td><td>10 avril 2026</td><td>23 octobre 2026</td></tr></table>
"""


class FranceCreditCarryOverlayTests(unittest.TestCase):
    def test_english_rating_table_parsed(self):
        r = watch.parse_moodys(EXAMPLE_EN)
        self.assertEqual(r["rating"], "Aa3")
        self.assertEqual(r["outlook"], "Negative")
        self.assertEqual(r["decision_date"], "2026-04-10")
        self.assertEqual(r["next_review"], "2026-10-23")

    def test_french_rating_table_parsed(self):
        r = watch.parse_moodys(EXAMPLE_FR)
        self.assertEqual(r["outlook"], "Négative")
        self.assertEqual(r["next_review"], "2026-10-23")

    def test_bad_table_fails_closed(self):
        with self.assertRaises(ValueError):
            watch.parse_moodys("<div>Moody's Aa3 Negative 23 October 2026</div>")
        with self.assertRaises(ValueError):
            watch.parse_moodys("<table><tr><td>Moody's</td><td>unknown</td><td>Stable</td><td>1 April 2026</td><td>23 October 2026</td></tr></table>")

    def test_milestones_are_not_downgrade_forecasts(self):
        rating = watch.parse_moodys(EXAMPLE_EN)
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 14), {}, rating), [])
        milestone = watch.credit_events(dt.date(2026, 10, 16), {}, rating)
        self.assertEqual(milestone[0]["key"], "milestone:2026-10-23:D-7")
        self.assertEqual(milestone[0]["kind"], "milestone")
        old = {"sent_keys": [milestone[0]["key"]]}
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 16), old, rating), [])
        one_day = watch.credit_events(dt.date(2026, 10, 22), old, rating)
        self.assertEqual(one_day[0]["key"], "milestone:2026-10-23:D-1")
        three_day = watch.credit_events(dt.date(2026, 10, 20), old, rating)
        self.assertEqual(three_day[0]["key"], "milestone:2026-10-23:D-3")

    def test_official_rating_downgrade_requires_changed_official_row(self):
        old = {"last_official": watch.parse_moodys(EXAMPLE_EN)}
        newest = {**old["last_official"], "rating": "A1", "decision_date": "2026-10-23", "next_review": None, "source_kind": "official_document"}
        events = watch.credit_events(dt.date(2026, 10, 24), old, newest)
        self.assertEqual(events, [{"kind": "decision", "key": "decision:2026-10-23:A1:Negative"}])
        old["sent_keys"] = [events[0]["key"]]
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 24), old, newest), [])

    def test_rating_unchanged_but_review_done_generates_one_verified_result(self):
        old = {"last_official": watch.parse_moodys(EXAMPLE_EN)}
        new = {**old["last_official"], "decision_date": "2026-10-23", "next_review": None, "source_kind": "official_document"}
        event = watch.credit_events(dt.date(2026, 10, 24), old, new)
        self.assertEqual(len(event), 1)
        self.assertEqual(event[0]["kind"], "decision")

    def test_rescheduled_review_does_not_send_false_october_milestones(self):
        rating = {**watch.parse_moodys(EXAMPLE_EN), "next_review": "2026-11-10"}
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 22), {}, rating), [])

    def test_spread_requires_matching_source_dates(self):
        pending = {"last_values": {"fr_mkt": 4.91, "de_mkt": 3.47},
                   "last_source_dates": {"fr_mkt": "2026-10-13", "de_mkt": "2026-10-13"}, "stale": []}
        self.assertEqual(watch.money_spread(pending), ("144.0bp", "2026-10-13"))
        pending["last_source_dates"]["de_mkt"] = "2026-10-12"
        self.assertEqual(watch.money_spread(pending)[0], "확인 불가(동일 기준일 자료 부족)")

    def test_message_says_not_a_forced_liquidation_deadline(self):
        rating = {**watch.parse_moodys(EXAMPLE_EN), "url": watch.AFT_EN}
        events = [{"kind": "milestone", "key": "milestone:2026-10-23:D-1", "days": 1}]
        _, msg = watch.format_event(rating, events, {}, dt.datetime(2026, 10, 22, 12, 0, tzinfo=watch.KST))
        self.assertIn("등급 강등 확정이 아닌", msg)
        self.assertIn("포지션 청산 마감일도 아닙니다", msg)
        self.assertIn("메모리주 영향은 조건부", msg)
        self.assertIn("AFT France Moody's rating calendar:", msg)

    def test_dated_official_snapshot_can_remind_but_not_assert_downgrade(self):
        snapshot = dict(watch.VERIFIED_AFT_SNAPSHOT)
        old = {"last_official": snapshot}
        event = watch.credit_events(dt.date(2026, 10, 16), old, snapshot)
        self.assertEqual([x["kind"] for x in event], ["milestone"])
        changed = {**snapshot, "rating": "A1", "decision_date": "2026-10-23"}
        self.assertFalse(any(x["kind"] == "decision" for x in watch.credit_events(
            dt.date(2026, 10, 24), old, changed
        )))
        _, msg = watch.format_event(snapshot, event, {}, dt.datetime(
            2026, 10, 16, tzinfo=watch.KST))
        self.assertIn("최신 일정 변경 여부는 확인 불가", msg)

    def test_outage_alert_is_labeled_source_failure_not_rating_result(self):
        snapshot = dict(watch.VERIFIED_AFT_SNAPSHOT)
        _, msg = watch.format_event(
            snapshot, [{"kind": "source_outage", "key": "official_rating_source_unavailable:2026-10"}],
            {}, dt.datetime(2026, 10, 14, tzinfo=watch.KST))
        self.assertIn("조회 장애", msg)
        self.assertIn("등급 변경이나 시장의 강등 가능성을 확정", msg)

    def test_source_attributed_text_recovery_only_schedules_not_downgrades(self):
        sample = (
            "Title: France's credit ratings\n"
            "URL Source: https://www.aft.gouv.fr/en/frances-credit-ratings\n"
            "| Agency | Rating | Outlook | Latest rating | Next rating date |\n"
            "| Moody's | Aa3 | Negative | 10 April 2026 | 23 October 2026 |\n"
        )
        row = watch.parse_aft_text_recovery(sample)
        self.assertEqual(row["rating"], "Aa3")
        self.assertEqual(row["source_kind"], "secondary_text_recovery")
        events = watch.credit_events(dt.date(2026, 10, 16), {}, row)
        self.assertEqual(len(events), 1)
        old = {"last_official": watch.parse_moodys(EXAMPLE_EN)}
        changed = {**row, "rating": "A1", "decision_date": "2026-10-23", "next_review": None}
        self.assertEqual(watch.credit_events(dt.date(2026, 10, 24), old, changed), [])

    def test_text_recovery_wrong_origin_is_rejected(self):
        sample = "URL Source: https://fake.example/rating\n| Moody's | A1 | Negative | 23 October 2026 | - |"
        with self.assertRaises(ValueError):
            watch.parse_aft_text_recovery(sample)

    def test_existing_market_alert_gets_carry_context_without_new_event(self):
        pending = {"last_values": {"fr_mkt": 4.88, "de_mkt": 3.45},
                   "last_source_dates": {"fr_mkt": "2026-10-13", "de_mkt": "2026-10-13"}, "stale": []}
        original = "🔴 [유럽 국채금리 경보]\n■ 시장 영향\n• 주식 영향"
        changed = watch.add_market_carry_context(original, pending, dt.date(2026, 10, 14))
        self.assertIn("■ 캐리·레버리지 전염 확인", changed)
        self.assertIn("직접 영향을 줬는지는 미확인", changed)
        self.assertEqual(watch.add_market_carry_context(changed, pending, dt.date(2026, 10, 14)), changed)

    def test_context_not_added_to_low_or_uncomparable_spreads(self):
        original = "■ 시장 영향"
        empty = {"last_values": {}, "last_source_dates": {}, "stale": []}
        self.assertEqual(watch.add_market_carry_context(original, empty, dt.date(2026, 10, 14)), original)
        pending = {"last_values": {"fr_mkt": 4.60, "de_mkt": 3.50},
                   "last_source_dates": {"fr_mkt": "2026-10-13", "de_mkt": "2026-10-13"}, "stale": []}
        self.assertEqual(watch.add_market_carry_context(original, pending, dt.date(2026, 10, 14)), original)

    def test_milestone_telegram_has_two_clickable_verified_source_links(self):
        from scripts.europe_sovereign_yield_telegram_html import render_chunks
        snapshot = dict(watch.VERIFIED_AFT_SNAPSHOT)
        _, msg = watch.format_event(
            snapshot,
            [{"kind": "milestone", "key": "milestone:2026-10-23:D-7", "days": 7}],
            {"last_values": {"fr_mkt": 4.84, "de_mkt": 3.46},
             "last_source_dates": {"fr_mkt": "2026-10-13", "de_mkt": "2026-10-13"},
             "stale": []},
            dt.datetime(2026, 10, 16, 8, 0, tzinfo=watch.KST),
        )
        chunks = render_chunks(msg)
        html = "\n".join(chunks)
        self.assertEqual(html.count("<a href="), 2)
        self.assertEqual(html.count("</a>"), 2)
        self.assertIn("프랑스 국채관리청 Moody’s 공식 신용등급 일정", html)
        self.assertIn("프랑스 헤지펀드 캐리 청산 보도", html)
        self.assertTrue(all(len(x) <= 3900 for x in chunks))


    def test_sp_direct_official_table_parses_actual_rating_and_date(self):
        sp = watch.parse_sp_official(EXAMPLE_EN)
        self.assertEqual(sp["rating"], "A+")
        self.assertEqual(sp["outlook"], "Stable")
        self.assertEqual(sp["decision_date"], "2026-05-29")
        self.assertEqual(sp["next_review"], "2026-11-27")
        with self.assertRaises(ValueError):
            watch.parse_sp_official("<p>Standard &amp; Poor's downgraded France to BBB</p>")

    def test_sp_live_result_requires_new_official_date_and_only_once(self):
        prev = dict(watch.VERIFIED_SP_SNAPSHOT)
        row = {**prev, "rating": "A", "outlook": "Negative",
               "decision_date": "2026-11-27", "next_review": None,
               "source_kind": "official_document"}
        events = watch.sp_review_events(dt.date(2026, 11, 28), set(), row, prev)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "sp_decision")
        self.assertEqual(events[0]["rating"], "A")
        self.assertEqual(
            watch.sp_review_events(dt.date(2026, 11, 28), {events[0]["key"]}, row, row), []
        )
        reported = {**row, "rating": prev["rating"],
                    "outlook": prev["outlook"]}
        unchanged = watch.sp_review_events(dt.date(2026, 11, 28),
                                           set(), reported, prev)
        self.assertEqual(unchanged[0]["kind"], "sp_decision")
        self.assertEqual(watch.sp_review_events(dt.date(2026, 11, 28),
                                               set(), row, row), [])

    def test_simultaneous_official_rating_and_government_notice_kept(self):
        rating = dict(watch.VERIFIED_AFT_SNAPSHOT)
        rating.update({"rating": "A1", "outlook": "Negative",
                       "decision_date": "2026-10-23", "source_kind": "official_document"})
        events = [
            {"kind": "decision", "key": "decision:2026-10-23:A1:Negative"},
            {"kind": "government_rating_notice", "key": "government_notice:x",
             "date": "2026-10-23", "url": "https://presse.economie.gouv.fr/notation-moodys-test/",
             "title": "Réponse de la France"},
        ]
        name, msg = watch.format_event(rating, events, {}, dt.datetime(2026, 10, 24, tzinfo=watch.KST))
        self.assertIn("Moody’s 공식 신용등급", name)
        self.assertIn("프랑스 재무부의 별도 공식 대응", msg)
        self.assertIn("government Moody press: ", msg)

    def test_simultaneous_sp_official_rating_and_government_notice_kept(self):
        rating = dict(watch.VERIFIED_AFT_SNAPSHOT)
        events = [
            {"kind": "sp_decision", "key": "sp_decision:2026-11-27:A:Stable",
             "rating": "A", "outlook": "Stable", "decision_date": "2026-11-27"},
            {"kind": "government_rating_notice", "key": "government_notice:y",
             "date": "2026-11-27", "url": "https://presse.economie.gouv.fr/notation-moodys-test/",
             "title": "Réponse du gouvernement"},
        ]
        name, msg = watch.format_event(rating, events, {},
                                       dt.datetime(2026, 11, 28, tzinfo=watch.KST))
        self.assertIn("S&P 공식 신용등급", name)
        self.assertIn("프랑스 재무부의 별도 공식 대응", msg)
        self.assertIn("AFT France S&P rating calendar:", msg)

    def test_sp_unverified_news_cannot_claim_official_downgrade(self):
        prev = dict(watch.VERIFIED_SP_SNAPSHOT)
        rumored = {**prev, "rating": "A", "outlook": "Negative",
                   "decision_date": "2026-11-27",
                   "source_kind": "secondary_text_recovery"}
        event = watch.sp_review_events(dt.date(2026, 11, 28), set(), rumored, prev)
        self.assertEqual(event[0]["kind"], "sp_review_overdue")

    def test_fetch_rating_attaches_live_sp_only_for_verified_official_html(self):
        rating, errs = watch.fetch_rating(fetch=lambda url: EXAMPLE_EN)
        self.assertEqual(errs, [])
        self.assertEqual(rating["sp_rating"]["rating"], "A+")
        self.assertEqual(rating["sp_rating"]["source_kind"], "official_document")

    def test_sp_november_review_milestones_are_deduplicated(self):
        first = watch.sp_review_events(dt.date(2026, 11, 20), set())
        self.assertEqual(first, [{"kind": "sp_milestone",
                                  "key": "sp_milestone:2026-11-27:D-7",
                                  "days": 7}])
        self.assertEqual(watch.sp_review_events(dt.date(2026, 11, 20),
                                                {first[0]["key"]}), [])
        same_day = watch.sp_review_events(dt.date(2026, 11, 27), set())
        self.assertEqual(same_day[0]["days"], 0)
        overdue = watch.sp_review_events(dt.date(2026, 11, 28), set())
        self.assertEqual(overdue[0]["kind"], "sp_review_overdue")
        self.assertEqual(watch.sp_review_events(dt.date(2026, 11, 28),
                                                {overdue[0]["key"]}), [])

    def test_sp_alert_uses_attributed_historical_rating_and_clickable_link(self):
        from scripts.europe_sovereign_yield_telegram_html import render_chunks
        rating = dict(watch.VERIFIED_AFT_SNAPSHOT)
        e = [{"kind": "sp_milestone", "key": "sp_milestone:2026-11-27:D-1",
              "days": 1}]
        _, body = watch.format_event(
            rating, e,
            {"last_values": {"fr_mkt": 5.06, "de_mkt": 3.35},
             "last_source_dates": {"fr_mkt": "2026-10-22",
                                   "de_mkt": "2026-10-22"}, "stale": []},
            dt.datetime(2026, 11, 26, 12, 0, tzinfo=watch.KST))
        self.assertIn("S&P 2026-11-27", body)
        self.assertIn("S&P 2026년 11월 27일 평가 일정", body)
        self.assertNotIn("프랑스 10월 23일 공식 신용등급", body)
        self.assertIn("날짜 변경 여부와 새 결정", body)
        self.assertIn("다음 경계 175bp", body)
        msg = "\\n".join(render_chunks(body))
        self.assertIn("프랑스 국채관리청 S&amp;P 공식 신용등급 일정</a>", msg)
        self.assertIn("프랑스 헤지펀드 캐리 청산 보도</a>", msg)

    def test_government_notice_does_not_claim_moodys_rating_result(self):
        snapshot = dict(watch.VERIFIED_AFT_SNAPSHOT)
        event = [{"kind": "government_rating_notice",
                  "key": "government_notice:2026-10-24:test",
                  "date": "2026-10-24",
                  "url": "https://presse.economie.gouv.fr/notation-moodys-france/",
                  "title": "Notation Moody's : réaction du gouvernement"}]
        _, msg = watch.format_event(
            snapshot, event, {}, dt.datetime(2026, 10, 24, tzinfo=watch.KST))
        self.assertIn("직접 발표", msg)
        self.assertIn("검증 전", msg)
        self.assertIn("France government Moody press:", msg)
        from scripts.europe_sovereign_yield_telegram_html import render_chunks
        rendered = "\n".join(render_chunks(msg))
        self.assertIn('>프랑스 재무부 Moody’s 공식 입장</a>', rendered)

    def test_official_fetch_fallback(self):
        def fetch(url):
            if "/en/" in url:
                raise ConnectionError("en blocked")
            return EXAMPLE_FR
        rating, errors = watch.fetch_rating(fetch=fetch)
        self.assertEqual(rating["next_review"], "2026-10-23")
        self.assertEqual(rating["url"], watch.AFT_FR)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()

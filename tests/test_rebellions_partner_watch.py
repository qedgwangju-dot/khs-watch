"""Regression tests for Rebellions Telegram partner watcher event deduplication."""
import datetime as dt
import contextlib
import io
import json
import os
import pathlib
import tempfile
import textwrap
import unittest
import urllib.error
from unittest import mock
from zoneinfo import ZoneInfo

from scripts import rebellions_partner_watch as watcher
from scripts.rebellions_partner_watch import (
    article_age_minutes,
    capital_event_kind,
    classify,
    domestic_candidate,
    event_signature,
    find_duplicate_event,
    material_stage,
    norm_title,
)


class RebellionsWatcherRegressionTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 9, 17, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    def prior(self, title, url="https://publisher.example/a", stage=None, stored_signature=None):
        return {
            "title": title,
            "url": url,
            "first_seen_kst": self.now.isoformat(timespec="seconds"),
            "material_stage": material_stage(title) if stage is None else stage,
            "event_signature": stored_signature or event_signature(title),
            "alerted": True,
        }

    def item(self, title, url="https://publisher.example/b"):
        return {"title": title, "url": url, "summary": ""}

    def test_kepco_mou_and_same_day_poc_are_one_event(self):
        a = "한전, 리벨리온·TTA와 국산 NPU 기반 AI 영상분석 협력 - 뉴스락"
        b = "한전 변전소 AI 관제에 국산 NPU 투입...리벨리온 현장 실증 - zdnet.co.kr"
        self.assertEqual(event_signature(a), event_signature(b))
        self.assertEqual(event_signature(a), "kepco|npu|power_video")
        self.assertTrue(find_duplicate_event(self.item(b), {"a": self.prior(a)}, self.now).startswith("same_event:"))

    def test_cck_existing_mou_is_not_new_equity_investment(self):
        mou = "리벨리온, CCK솔루션과 국산 NPU 협력 업무협약"
        investment = "리벨리온, CCK솔루션에 전략적 투자 참여 - 머니투데이"
        self.assertNotEqual(event_signature(mou), event_signature(investment))
        self.assertEqual(event_signature(investment), "cck|capital|equity")
        self.assertEqual(material_stage(investment), 5)
        self.assertEqual(classify(investment), "투자·지분")
        self.assertIsNone(find_duplicate_event(self.item(investment), {"mou": self.prior(mou)}, self.now))

    def test_different_outlet_same_new_investment_is_suppressed(self):
        first = "리벨리온, CCK솔루션에 전략적 투자 참여 - 머니투데이"
        second = "CCK솔루션, 리벨리온 투자 유치…국산 AI 풀스택 강화 - 이데일리"
        old = self.prior(first, stored_signature="cck|general|general", stage=0)
        self.assertEqual(event_signature(second), "cck|capital|equity")
        self.assertEqual(find_duplicate_event(self.item(second), {"first": old}, self.now), "same_event:cck|capital|equity")

    def test_identical_google_news_link_different_publisher_names(self):
        same_url = "https://news.google.com/rss/articles/example-id?oc=5"
        a = "리벨리온, CCK솔루션에 전략적 투자 참여 - 머니투데이"
        b = "리벨리온, CCK솔루션에 전략적 투자 참여 - mt.co.kr"
        self.assertEqual(norm_title(a), norm_title(b))
        self.assertEqual(find_duplicate_event(self.item(b, same_url), {"a": self.prior(a, same_url)}, self.now), "same_url")

    def test_stale_duplicate_older_than_14_days_does_not_block_new_event(self):
        title = "리벨리온, CCK솔루션에 전략적 투자 참여"
        entry = self.prior(title)
        entry["first_seen_kst"] = (self.now - dt.timedelta(days=15)).isoformat()
        different = "CCK솔루션, 리벨리온 투자 유치 완료"
        self.assertIsNone(find_duplicate_event(self.item(different), {"a": entry}, self.now))

    def test_investment_proposal_is_not_alertable(self):
        title = "리벨리온, CCK솔루션 전략적 투자 추진"
        self.assertFalse(domestic_candidate(title))
        self.assertIsNone(capital_event_kind(title))

    def test_publisher_to_detection_delay_is_measured(self):
        checked = dt.datetime.fromisoformat("2026-10-09T01:55:00+09:00")
        self.assertEqual(article_age_minutes("2026-10-08T19:00+09:00", checked), 415)
        self.assertIsNone(article_age_minutes(None, checked))

    def test_named_acquisition_has_material_stage(self):
        title = "리벨리온, AI 최적화 기업 스퀴즈비츠 인수"
        self.assertEqual(capital_event_kind(title), "acquisition")
        self.assertEqual(classify(title), "인수·합병")
        self.assertEqual(material_stage(title), 5)
        self.assertEqual(event_signature(title), "squeezebits|capital|acquisition")

    def test_second_equity_round_is_distinct(self):
        first = "리벨리온, CCK솔루션에 전략적 투자 참여"
        follow_on = "리벨리온, CCK솔루션에 후속 투자 단행"
        self.assertNotEqual(event_signature(first), event_signature(follow_on))
        self.assertIsNone(find_duplicate_event(self.item(follow_on), {"first": self.prior(first)}, self.now))


class RebellionsSourceHealthTests(unittest.TestCase):
    RSS = '<rss version="2.0"><channel><title>Google News</title></channel></rss>'

    def setUp(self):
        watcher.reset_fetch_stats()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        for name, filename in (
            ("STATE", "state.json"), ("ALERT", "alert.md"),
            ("PENDING", "pending.json"), ("STATUS", "status.md"),
            ("SOURCE_HEALTH", "source_health.json"),
        ):
            patch = mock.patch.object(watcher, name, self.root / filename)
            patch.start()
            self.addCleanup(patch.stop)
        # No test is allowed to escape its fixtures and make a network request.
        patch = mock.patch.object(watcher.urllib.request, "urlopen", side_effect=AssertionError("network forbidden"))
        patch.start()
        self.addCleanup(patch.stop)

    def http_error(self, code):
        return urllib.error.HTTPError("https://news.google.com/rss/search", code, "private response", {}, None)

    def test_access_blocks_open_provider_circuit_without_retry(self):
        for code in (401, 403, 429):
            with self.subTest(code=code):
                watcher.reset_fetch_stats()
                with mock.patch.object(watcher, "fetch_text", side_effect=self.http_error(code)) as fetch, \
                     mock.patch.object(watcher.time, "sleep") as sleep:
                    self.assertEqual(watcher.collect_google_news(), [])
                self.assertEqual(fetch.call_count, 1)
                sleep.assert_not_called()
                self.assertTrue(watcher.FETCH_STATS["google_blocked"])
                self.assertEqual(watcher.FETCH_STATS["google_ok"], 0)
                self.assertEqual(watcher.FETCH_STATS["google_errors"][0]["http_status"], code)
                self.assertEqual(sum(r["status"] == "skipped_provider_block" for r in watcher.FETCH_STATS["google_results"]), 5)

    def test_html_challenge_stops_remaining_provider_requests(self):
        body = '<html><body>Our systems have detected unusual traffic. /sorry/</body></html>'
        with mock.patch.object(watcher, "fetch_text", return_value=body) as fetch:
            watcher.collect_google_news()
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(watcher.FETCH_STATS["google_blocked"])

    def test_official_access_block_stops_other_pages_and_labels_transport_only(self):
        for code in (401, 403, 429):
            with self.subTest(code=code):
                watcher.reset_fetch_stats()
                with mock.patch.object(watcher, "fetch_text", side_effect=self.http_error(code)) as fetch:
                    self.assertEqual(watcher.collect_official(), [])
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(watcher.FETCH_STATS["official_skipped"], 9)
                self.assertTrue(watcher.FETCH_STATS["official_blocked"])
                watcher.FETCH_STATS["google_ok"] = 6
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertFalse(watcher.write_source_health(watcher.now_kst()))
                health = json.loads(watcher.SOURCE_HEALTH.read_text())
                self.assertEqual(health["outcome"], "partial")
                self.assertEqual(health["official_validation"], "transport_only")
                self.assertFalse(health["official_content_validated"])

    def test_transient_server_error_retries_once_then_recovers(self):
        with mock.patch.object(watcher, "fetch_text", side_effect=[self.http_error(503)] + [self.RSS] * 6) as fetch, \
             mock.patch.object(watcher.time, "sleep") as sleep:
            watcher.collect_google_news()
        self.assertEqual(fetch.call_count, 7)
        sleep.assert_called_once_with(1)
        self.assertEqual(watcher.FETCH_STATS["google_ok"], 6)
        first = watcher.FETCH_STATS["google_results"][0]
        self.assertEqual(first["attempts"], 2)
        self.assertEqual(first["errors"][0]["http_status"], 503)

    def test_repeated_transient_errors_have_bounded_attempts(self):
        with mock.patch.object(watcher, "fetch_text", side_effect=self.http_error(503)) as fetch, \
             mock.patch.object(watcher.time, "sleep") as sleep:
            watcher.collect_google_news()
        self.assertEqual(fetch.call_count, 12)
        self.assertEqual(sleep.call_count, 6)
        self.assertEqual(watcher.FETCH_STATS["google_ok"], 0)
        self.assertTrue(all(r["attempts"] == 2 for r in watcher.FETCH_STATS["google_results"]))

    def test_timeout_is_retried_but_other_url_errors_are_not(self):
        self.assertTrue(watcher.is_transient_source_error(urllib.error.URLError(TimeoutError())))
        self.assertFalse(watcher.is_transient_source_error(urllib.error.URLError("certificate verification failed")))
        self.assertFalse(watcher.is_transient_source_error(self.http_error(404)))

    def test_valid_empty_rss_counts_as_success(self):
        with mock.patch.object(watcher, "fetch_text", return_value=self.RSS):
            self.assertEqual(watcher.collect_google_news(), [])
        self.assertEqual(watcher.FETCH_STATS["google_ok"], 6)

    def test_non_rss_or_malformed_documents_never_count_as_success(self):
        for body in ('<html><body>No results</body></html>', '<rss/>', '<rss><channel>'):
            with self.subTest(body=body):
                watcher.reset_fetch_stats()
                with mock.patch.object(watcher, "fetch_text", return_value=body) as fetch, \
                     mock.patch.object(watcher.time, "sleep") as sleep:
                    watcher.collect_google_news()
                self.assertEqual(watcher.FETCH_STATS["google_ok"], 0)
                self.assertEqual(fetch.call_count, 6)
                sleep.assert_not_called()

    def test_failure_keeps_state_and_writes_diagnostics_before_raising(self):
        original = {"initialized": True, "last_checked_kst": "2026-10-11T19:00:00+09:00", "seen": {}}
        watcher.STATE.write_text(json.dumps(original))
        for path in (watcher.ALERT, watcher.PENDING, watcher.STATUS):
            path.write_text("stale output")
        # A stale process-global success count must not turn this failed run green.
        watcher.FETCH_STATS["google_ok"] = 6
        with mock.patch.object(watcher, "collect_official", return_value=[]), \
             mock.patch.object(watcher, "fetch_text", side_effect=self.http_error(429)), \
             contextlib.redirect_stdout(io.StringIO()) as logs:
            with self.assertRaisesRegex(RuntimeError, "source-health diagnostics"):
                watcher.main()
        self.assertEqual(json.loads(watcher.STATE.read_text()), original)
        self.assertFalse(watcher.ALERT.exists())
        self.assertFalse(watcher.PENDING.exists())
        health = json.loads(watcher.SOURCE_HEALTH.read_text())
        self.assertTrue(health["collection_attempted"])
        self.assertEqual(health["outcome"], "failed")
        self.assertEqual(health["google_ok"], 0)
        self.assertIn('"http_status": 429', logs.getvalue())
        self.assertNotIn("private response", logs.getvalue())
        self.assertIn("확인 불가", watcher.STATUS.read_text())

    def test_provider_block_fails_closed_even_after_two_successes(self):
        with mock.patch.object(watcher, "fetch_text", side_effect=[self.RSS, self.RSS, self.http_error(403)]):
            watcher.collect_google_news()
        self.assertEqual(watcher.FETCH_STATS["google_ok"], 2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(watcher.write_source_health(watcher.now_kst()))
        self.assertEqual(json.loads(watcher.SOURCE_HEALTH.read_text())["outcome"], "failed")

    def test_existing_minimum_coverage_guard_is_preserved(self):
        watcher.FETCH_STATS["google_ok"] = 1
        self.assertTrue(watcher.write_source_health(watcher.now_kst()))
        watcher.FETCH_STATS["google_ok"] = 2
        self.assertFalse(watcher.write_source_health(watcher.now_kst()))
        self.assertEqual(json.loads(watcher.SOURCE_HEALTH.read_text())["outcome"], "partial")

    def test_successful_fixture_collection_resets_stats_and_bootstraps(self):
        official = '<a href="/company/newsroom/new-deal/">리벨리온 코난테크놀로지 국산 NPU 협력</a>'
        def fetch(url, timeout=25):
            return self.RSS if "news.google.com" in url else official
        with mock.patch.object(watcher, "fetch_text", side_effect=fetch), contextlib.redirect_stdout(io.StringIO()):
            watcher.main()
            watcher.main()
        health = json.loads(watcher.SOURCE_HEALTH.read_text())
        self.assertEqual(health["outcome"], "passed")
        self.assertEqual((health["official_ok"], health["google_ok"]), (10, 6))
        self.assertEqual(len(json.loads(watcher.PENDING.read_text())["seen"]), 1)
        self.assertFalse(watcher.ALERT.exists())

    def test_stale_article_guard_is_unchanged(self):
        watcher.STATE.write_text(json.dumps({
            "initialized": True, "last_checked_kst": "2026-10-11T19:00:00+09:00", "seen": {},
        }))
        rss = ('<rss><channel><item><title>리벨리온 코난테크놀로지 국산 NPU 협력</title>'
               '<link>https://publisher.example/old</link><pubDate>Mon, 05 Oct 2026 00:00:00 GMT</pubDate>'
               '</item></channel></rss>')
        with mock.patch.object(watcher, "collect_official", return_value=[]), \
             mock.patch.object(watcher, "fetch_text", return_value=rss), \
             mock.patch.object(watcher, "resolve_original_url") as resolve, \
             contextlib.redirect_stdout(io.StringIO()):
            watcher.main()
        self.assertFalse(watcher.ALERT.exists())
        resolve.assert_not_called()
        seen = json.loads(watcher.PENDING.read_text())["seen"]
        self.assertTrue(next(iter(seen.values()))["suppressed_stale"])
        self.assertIn("부분 조회 · 일부 원천 미확인", watcher.STATUS.read_text())

    def test_cadence_skip_has_explicit_unchecked_artifact(self):
        workflow = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/rebellions-partner-watch-telegram.yml"
        text = workflow.read_text()
        source = textwrap.dedent(text.split("python3 - <<'PY'\n", 1)[1].split("          PY", 1)[0])
        (self.root / "data").mkdir()
        (self.root / "data/rebellions_partner_watch_state.json").write_text(json.dumps({
            "last_checked_kst": watcher.now_kst().isoformat(),
        }))
        old_cwd = pathlib.Path.cwd()
        try:
            os.chdir(self.root)
            with mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run", "GITHUB_OUTPUT": str(self.root / "github_output")}), \
                 contextlib.redirect_stdout(io.StringIO()):
                exec(compile(source, "cadence-workflow", "exec"), {})
        finally:
            os.chdir(old_cwd)
        health = json.loads((self.root / "out/rebellions_partner_watch_source_health.json").read_text())
        self.assertFalse(health["collection_attempted"])
        self.assertEqual(health["outcome"], "skipped_recent_check")
        self.assertEqual((self.root / "github_output").read_text(), "run=false\n")
        self.assertIn("원천 건강 상태: 확인하지 않음", (self.root / "out/rebellions_partner_watch_status.md").read_text())

    def test_review_publication_cannot_activate_production(self):
        workflow = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/rebellions-partner-watch-telegram.yml"
        text = workflow.read_text()
        triggers = text.split("permissions:", 1)[0]
        self.assertIn("  push:\n    branches: [main]\n", triggers)
        self.assertIn("  pull_request:\n    branches: [main]\n", triggers)
        self.assertIn("group: rebellions-partner-watch-telegram${{ github.event_name == 'pull_request' && format('-pr-{0}', github.event.pull_request.number) || '' }}", text)
        regression = text.split("  offline-regressions:\n", 1)[1].split("  monitor:\n", 1)[0]
        self.assertIn("if: github.event_name == 'pull_request'", regression)
        self.assertIn("    permissions:\n      contents: read\n", regression)
        self.assertIn("persist-credentials: false", regression)
        self.assertNotIn("ref: main", regression)
        self.assertNotIn("secrets.", regression)
        self.assertNotIn("sendMessage", regression)
        self.assertIn("python -m unittest discover", regression)
        monitor_guard = text.split("  monitor:\n", 1)[1].splitlines()[0]
        self.assertIn("github.event_name != 'pull_request'", monitor_guard)
        self.assertIn("github.event_name != 'push' || github.ref == 'refs/heads/main'", monitor_guard)


if __name__ == "__main__":
    unittest.main()


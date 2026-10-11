import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import lng_collection_budget as budget


def quiet(*args, **kwargs):
    pass


class CollectorTest(unittest.TestCase):
    def test_fast_success_retains_every_task_and_empty_value(self):
        tasks = [(str(i), lambda i=i: b'' if i == 0 else i) for i in range(125)]
        values, coverage = budget.collect(tasks, deadline=time.monotonic() + 2, progress=quiet)
        self.assertEqual(len(values), len(tasks))
        self.assertEqual(values['0'], b'')
        self.assertTrue(all(r['status'] == 'ok' for r in coverage.values()))

    def test_concurrency_is_bounded_and_parallel(self):
        lock=threading.Lock()
        gate=threading.Event()
        active=0
        high=0
        def fetch():
            nonlocal active,high
            with lock:
                active+=1
                high=max(high,active)
                if active==3:
                    gate.set()
            if not gate.wait(1):
                raise AssertionError('collector did not start workers concurrently')
            with lock:
                active-=1
            return 'ok'
        values,coverage=budget.collect([(str(i),fetch) for i in range(12)],
            deadline=time.monotonic()+2,workers=3,progress=quiet)
        self.assertEqual(high,3)
        self.assertEqual(len(values),12)

    def test_source_error_distinct_from_empty_success(self):
        def fail():
            raise TimeoutError('fixture')
        values, coverage = budget.collect([('empty', lambda: b''), ('failed', fail)],
                                          deadline=time.monotonic() + 2, progress=quiet)
        self.assertEqual(values, {'empty': b''})
        self.assertEqual(coverage['failed']['status'], 'error')
        self.assertIn('TimeoutError', coverage['failed']['error'])

    def test_deadline_returns_without_waiting_and_late_results_are_isolated(self):
        release = threading.Event()
        started = threading.Event()
        def slow():
            started.set()
            release.wait(2)
            return 'late'
        before = time.monotonic()
        try:
            values, coverage = budget.collect([('running', slow), ('queued', lambda: 'unused')],
                deadline=before + 0.04, workers=1, progress=quiet)
            self.assertTrue(started.is_set())
            self.assertLess(time.monotonic() - before, 0.5)
            self.assertEqual(values, {})
            self.assertEqual(coverage['running']['status'], 'deadline')
            self.assertEqual(coverage['queued']['status'], 'not_started_deadline')
            snapshot = json.dumps(coverage, sort_keys=True)
        finally:
            release.set()
        time.sleep(0.01)
        self.assertEqual(values, {})
        self.assertEqual(json.dumps(coverage, sort_keys=True), snapshot)

    def test_expired_total_budget_starts_nothing(self):
        call = Mock()
        values, coverage = budget.collect([('unstarted', call)], deadline=5, clock=lambda: 5, progress=quiet)
        call.assert_not_called()
        self.assertEqual(coverage['unstarted']['status'], 'not_started_deadline')

    def test_duplicate_key_rejected(self):
        with self.assertRaises(ValueError):
            budget.collect([('x', lambda: 1), ('x', lambda: 2)], deadline=time.monotonic()+1)


class RunGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        spec = importlib.util.spec_from_file_location('lng_budget_test_core', ROOT/'scripts/lng_supply_crisis_alert_v2.py')
        self.core = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.core
        spec.loader.exec_module(self.core)
        c = self.core
        c.OUT_DIR = pathlib.Path(self.tmp.name)/'out'
        c.STATE_PATH = pathlib.Path(self.tmp.name)/'state.json'
        c.STATE_PATH.write_text('{"sentinel": true}\n')
        for name in ('TITLE_PATH','BODY_PATH','ALERT_JSON_PATH','SUMMARY_PATH','PENDING_STATE_PATH','TELEGRAM_CONFIRMED_PATH'):
            setattr(c,name,c.OUT_DIR/getattr(c,name).name)
        c.NEWS_QUERIES = (('qatar_lng','query one'), ('qatar_lng','query two'))
        c.fetch_bytes = Mock(return_value=b'<rss><channel/></rss>')
        c.apply_hysteresis = Mock(return_value=set())
        c.should_alert = Mock(return_value=False)
        c.write_alert = Mock()
        c.write_summary = Mock()
        self.market = Mock(return_value={k: object() for k in ('ttf','jkm','brent','bund10','us10')})
        c.clean_outputs()
        # Failed runs must not leave artifacts from a prior invocation.
        for p in (c.PENDING_STATE_PATH,c.BODY_PATH,c.ALERT_JSON_PATH,c.TELEGRAM_CONFIRMED_PATH):
            p.write_text('stale')

    def install(self, **kwargs):
        budget.install(self.core, early_queries=(), market_sources={'canonical':self.market}, **kwargs)

    def assert_failed_closed(self):
        c=self.core
        self.assertFalse(c.PENDING_STATE_PATH.exists())
        self.assertFalse(c.BODY_PATH.exists())
        self.assertFalse(c.ALERT_JSON_PATH.exists())
        self.assertFalse(c.TELEGRAM_CONFIRMED_PATH.exists())
        self.assertEqual(c.STATE_PATH.read_text(), '{"sentinel": true}\n')
        c.write_alert.assert_not_called()
        c.apply_hysteresis.assert_not_called()
        self.assertEqual(c.finalize(), 0)
        self.assertEqual(c.STATE_PATH.read_text(), '{"sentinel": true}\n')
        report=json.loads((c.OUT_DIR/'lng_collection_coverage.json').read_text())
        self.assertFalse(report['complete'])
        self.assertIn('No alert or pending state created',c.SUMMARY_PATH.read_text())
        return report

    def test_empty_valid_rss_is_complete_and_all_queries_fetched(self):
        self.install()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(False),0)
        self.assertEqual(self.core.fetch_bytes.call_count,2)
        self.assertTrue(self.core.PENDING_STATE_PATH.exists())
        self.assertTrue(json.loads((self.core.OUT_DIR/'lng_collection_coverage.json').read_text())['complete'])

    def test_news_failure_never_reaches_market_or_state_even_in_setup_mode(self):
        self.core.fetch_bytes.side_effect=TimeoutError('unavailable')
        self.install()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(True),1)
        report=self.assert_failed_closed()
        self.market.assert_not_called()
        self.assertEqual(len(report['news']),2)
        self.assertTrue(all(x['status']=='error' for x in report['news'].values()))

    def test_malformed_or_non_rss_success_is_not_empty_coverage(self):
        self.core.fetch_bytes.return_value=b'<html>blocked</html>'
        self.install()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(False),1)
        self.assert_failed_closed()

    def test_market_failure_never_advances_state(self):
        self.market.side_effect=RuntimeError('stale source')
        self.install()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(False),1)
        report=self.assert_failed_closed()
        self.assertIn('stale source',report['market']['canonical']['error'])

    def test_market_missing_required_quote_fails_closed(self):
        self.market.return_value={'ttf': object()}
        self.install()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(False),1)
        self.assert_failed_closed()

    def test_total_deadline_fails_before_source_work_or_state(self):
        self.install(total_seconds=0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(False),1)
        self.core.fetch_bytes.assert_not_called()
        self.assert_failed_closed()

    def test_market_deadline_returns_and_finalization_cannot_use_stale_state(self):
        release=threading.Event()
        self.market.side_effect=lambda: release.wait(2) or {}
        self.install(market_seconds=0.03)
        try:
            before=time.monotonic()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.core.run(False),1)
            self.assertLess(time.monotonic()-before,0.5)
            report=self.assert_failed_closed()
            self.assertEqual(report['market']['canonical']['status'],'deadline')
        finally:
            release.set()


    def test_unexpected_parser_exception_fails_closed_with_diagnostic(self):
        self.core.fetch_news_item_set=Mock(side_effect=ValueError('unexpected parse failure'))
        self.install()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(False),1)
        report=self.assert_failed_closed()
        self.assertIn('ValueError: unexpected parse failure',report['error'])

    def test_post_collection_failure_cleans_pending_and_preserves_coverage_status(self):
        self.core.write_summary.side_effect=ValueError('formatter failed')
        self.install()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.core.run(False),1)
        self.assertFalse(self.core.PENDING_STATE_PATH.exists())
        self.assertFalse(self.core.BODY_PATH.exists())
        self.assertEqual(self.core.STATE_PATH.read_text(), '{"sentinel": true}\n')
        report=json.loads((self.core.OUT_DIR/'lng_collection_coverage.json').read_text())
        self.assertTrue(report['complete'])
        self.assertIn('formatter failed',report['error'])


class V34WiringTest(unittest.TestCase):
    def test_current_query_enumeration_and_parser_urls_match(self):
        import lng_supply_crisis_alert_v34 as monitor
        import lng_supply_crisis_alert_v10 as news
        urls=budget.news_urls(monitor.core, news.EARLY_ALASKA_QUERIES)
        self.assertEqual(len(urls),len(monitor.core.NEWS_QUERIES)+len(news.EARLY_ALASKA_QUERIES))
        called=[]
        def empty(url,*args,**kwargs):
            called.append(url)
            return b'<rss><channel/></rss>'
        # Exercise the unchanged full v10 parser chain, not the new cache wrapper.
        with patch.object(monitor.core,'fetch_bytes',side_effect=empty):
            items,errors=news.fetch_news_item_set_v10()
        self.assertEqual(errors,[])
        self.assertEqual(items,[])
        self.assertEqual(called,[url for _,url in urls])

    def test_v34_does_not_install_superseded_market_fetch_chain(self):
        import lng_supply_crisis_alert_v34 as monitor
        self.assertEqual(monitor.core.fetch_market_quotes.__module__,'lng_collection_budget')
        # Canonical bond helper retains original official parser and conversion.
        with patch.object(monitor._bonds_v20,'fetch_official_bond_snapshots',return_value=('bund','us')) as fetch, patch.object(monitor._bonds_v20,'_make_quote',side_effect=lambda key,snap:(key,snap)):
            self.assertEqual(monitor._official_bond_quotes_v34(),{'bund10':('bund10','bund'),'us10':('us10','us')})
            fetch.assert_called_once_with()

    def test_actual_v34_run_uses_only_canonical_market_sources(self):
        import lng_supply_crisis_alert_v34 as monitor
        core=monitor.core
        expected={key:object() for key in ('ttf','jkm','brent','bund10','us10')}
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            out=pathlib.Path(temp)/'out'
            stack.enter_context(patch.object(core,'OUT_DIR',out))
            stack.enter_context(patch.object(core,'STATE_PATH',pathlib.Path(temp)/'state.json'))
            for name in ('TITLE_PATH','BODY_PATH','ALERT_JSON_PATH','SUMMARY_PATH','PENDING_STATE_PATH','TELEGRAM_CONFIRMED_PATH'):
                stack.enter_context(patch.object(core,name,out/getattr(core,name).name))
            def response(*args,**kwargs):
                return contextlib.closing(io.BytesIO(b'<rss><channel/></rss>'))
            stack.enter_context(patch('urllib.request.urlopen',side_effect=response))
            te=stack.enter_context(patch.object(monitor,'_fetch_te_korean_detail_quote_v34',side_effect=lambda key:expected[key]))
            brent=stack.enter_context(patch.object(monitor,'_fetch_yahoo_brent_daily_close_v34',return_value=expected['brent']))
            bonds=stack.enter_context(patch.object(monitor._bonds_v20,'fetch_official_bond_snapshots',return_value=('bund','us')))
            convert=stack.enter_context(patch.object(monitor._bonds_v20,'_make_quote',side_effect=lambda key,snap:expected[key]))
            old=stack.enter_context(patch.object(monitor,'_BASE_FETCH_MARKET_QUOTES_V34',side_effect=AssertionError('superseded chain called')))
            hysteresis=stack.enter_context(patch.object(core,'apply_hysteresis',return_value=set()))
            stack.enter_context(patch.object(core,'should_alert',return_value=False))
            stack.enter_context(patch.object(core,'write_summary'))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(core.run(False),0)
            self.assertEqual(hysteresis.call_args.args[0],expected)
            self.assertEqual(te.call_count,2)
            brent.assert_called_once_with()
            bonds.assert_called_once_with()
            self.assertEqual(convert.call_count,2)
            old.assert_not_called()
            report=json.loads((out/'lng_collection_coverage.json').read_text())
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['news']), len(core.NEWS_QUERIES)+len(monitor._news_v10.EARLY_ALASKA_QUERIES))

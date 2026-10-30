"""Bounded collection without changing query, parser, or delivery semantics.

Linux/GitHub Actions only. Fetch in isolated processes, then replay identical HTTP
responses through the existing parser chain in its original query order. Network
workers never write state or alert files. The supervisor covers rendering and
verification too, including stalled non-daemon article-enrichment threads.
"""
from __future__ import annotations

import json
import hashlib
import base64
import datetime as dt
import multiprocessing as mp
from multiprocessing.connection import wait
import os
import shutil
import signal
import time
import urllib.parse
import xml.etree.ElementTree as ET


class IncompleteCoverage(RuntimeError):
    pass


class RecordedSourceError(OSError):
    pass


# A successful search or alternate feed does not establish that a failed
# explicitly configured source was covered over the same population/window.
_DIRECT_SOURCE_HOSTS = {
    'direct-kremlin-news': 'en.kremlin.ru',
    'direct-kremlin-transcripts': 'en.kremlin.ru',
    'direct-kremlin-telegram': 't.me',
    'direct-interfax-top': 'interfax.com',
    'direct-tass-home': 'tass.com',
    'direct-gdelt-ukraine': 'api.gdeltproject.org',
    'direct-gdelt-iran': 'api.gdeltproject.org',
    'ap-direct-world-rss': 'apnews.com',
    'ap-direct-top-rss': 'apnews.com',
    '__TRUMP_TRUTH_SOCIAL_ENERGY_CEASEFIRE__': 'truthsocial.com',
}


def _unverified_direct_fallback(query, attempts):
    """Return the failed direct host when only another host succeeded."""
    direct = _DIRECT_SOURCE_HOSTS.get(query)
    if not direct:
        return None
    direct_attempts = [a for a in attempts if a.get('host') == direct]
    if not direct_attempts or any(a.get('status') == 'ok' for a in direct_attempts):
        return None
    if any(a.get('host') != direct and a.get('status') == 'ok' for a in attempts):
        return direct
    return None


def _save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def _clean(watch):
    for path in (watch.ALERT, watch.PENDING, getattr(watch, 'AUDIT', None),
                 watch.OUT / 'war_peace_reconstruction_stage_alert.txt',
                 watch.OUT / 'war_peace_reconstruction_stage_evidence.json'):
        if path is None:
            continue
        path.unlink(missing_ok=True)


def _rejected_paths(watch):
    return (
        ('alert', watch.ALERT, watch.OUT / 'war_peace_reconstruction_rejected_alert.txt'),
        ('pending', watch.PENDING, watch.OUT / 'war_peace_reconstruction_rejected_pending.json'),
        ('evidence', getattr(watch, 'AUDIT', None), watch.OUT / 'war_peace_reconstruction_rejected_evidence.json'),
        ('stage_alert', watch.OUT / 'war_peace_reconstruction_stage_alert.txt',
         watch.OUT / 'war_peace_reconstruction_rejected_stage_alert.txt'),
        ('stage_evidence', watch.OUT / 'war_peace_reconstruction_stage_evidence.json',
         watch.OUT / 'war_peace_reconstruction_rejected_stage_evidence.json'),
    )


def _clean_rejected(watch):
    for _, _, target in _rejected_paths(watch):
        target.unlink(missing_ok=True)


def _preserve_rejected(watch, report):
    """Keep failed render evidence under names excluded from all send/state steps."""
    if report.get('phase') != 'parse_render_verify':
        return
    retained = []
    for role, source, target in _rejected_paths(watch):
        if source is None or not source.is_file():
            continue
        if source.resolve().parent != watch.OUT.resolve():
            raise ValueError('rejected diagnostic source must be within the output directory')
        raw = source.read_bytes()
        shutil.copyfile(source, target)
        retained.append({'role': role, 'path': target.name, 'bytes': len(raw),
                         'sha256': hashlib.sha256(raw).hexdigest(), 'verified': False})
    if retained:
        report['rejected_artifacts'] = retained


class _ProviderBlocks:
    """Small shared-memory registry; callers hold the collection's process lock."""
    def __init__(self, context):
        self.buffer = context.RawArray('c', 65536)
        self.buffer.value = b'{}'

    def snapshot(self):
        return json.loads(self.buffer.value)

    def __contains__(self, host):
        return host in self.snapshot()

    def setdefault(self, host, reason):
        current = self.snapshot()
        current.setdefault(host, reason)
        encoded = json.dumps(current).encode('utf-8')
        if len(encoded) >= len(self.buffer):
            raise IncompleteCoverage('provider circuit registry capacity exceeded')
        self.buffer.value = encoded


def _source_worker(connection, watch, blocked, gate_lock):
    """A private copy of every parser/global; return only an HTTP transcript."""
    original_req = watch.req
    original_hook = getattr(watch, '_before_source_request', None)

    def provider(url):
        return (urllib.parse.urlparse(url).hostname or '').lower().removeprefix('www.')

    def admit(url):
        with gate_lock:
            if provider(url) in blocked:
                raise RecordedSourceError('provider access circuit is open')

    def mark_block(url, exc):
        if getattr(exc, 'provider_blocked', False) or getattr(exc, 'code', None) in (401, 403, 429):
            with gate_lock:
                blocked.setdefault(provider(url), {
                    'reason': type(exc).__name__, 'code': getattr(exc, 'code', None),
                    'observed_monotonic': time.monotonic(),
                })

    # Also gate a retry already inside the shared HTTP helper.
    watch._before_source_request = admit
    try:
        while True:
            task = connection.recv()
            if task is None:
                return
            index, query, successful_snapshot = task
            trace = []
            reused = []
            cached = {}
            for url, _, value, error in successful_snapshot:
                if error is None:
                    cached.setdefault(url, []).append(value)

            def record(url, timeout=20):
                available = cached.get(url)
                if available:
                    value = available.pop(0)
                    trace.append((url, timeout, value, None))
                    reused.append(True)
                    return value
                reused.append(False)
                try:
                    admit(url)
                    value = original_req(url, timeout)
                except Exception as exc:
                    mark_block(url, exc)
                    trace.append((url, timeout, getattr(exc, 'response_body', None), type(exc).__name__ + ': ' + str(exc)))
                    raise
                trace.append((url, timeout, value, None))
                return value

            watch.req = record
            start = time.monotonic()
            try:
                rows, error = watch.google_news(query)
                failed = [entry for entry in trace if entry[3]]
                if trace and len(failed) == len(trace):
                    error = error or 'all source HTTP requests failed'
                # Axios direct RSS is required and must be parseable. A retired,
                # undated World HTML scrape is not a live monitoring requirement.
                # The legacy RSS helper swallows transport/XML exceptions.
                if query == '__AXIOS_DIRECT_WAR_PEACE__':
                    if failed:
                        error = error or 'Axios direct RSS source failed'
                    if not any(url == 'https://api.axios.com/feed/' for url, _, _, _ in trace):
                        error = error or 'Axios RSS source was not requested'
                    for url, _, raw, failure in trace:
                        if url == 'https://api.axios.com/feed/' and not failure:
                            try:
                                root = ET.fromstring(raw)
                                if not ((root.tag == 'rss' and root.find('channel') is not None)
                                        or root.tag == '{http://www.w3.org/2005/Atom}feed'):
                                    raise ValueError('not an RSS/Atom feed')
                            except (ET.ParseError, ValueError, TypeError):
                                error = error or 'Axios feed is not valid RSS/Atom'
                result = {'error': str(error) if error else None, 'rows': len(rows), 'trace': trace,
                          'reused': reused}
            except Exception as exc:
                result = {'error': type(exc).__name__ + ': ' + str(exc), 'rows': 0, 'trace': trace,
                          'reused': reused}
            connection.send((index, time.monotonic() - start, result))
    finally:
        watch._before_source_request = original_hook
        connection.close()


def _http_record(url, value, error):
    item = {'url': url, 'status': 'error' if error else 'ok'}
    if error:
        item['error'] = error
    if value is not None:
        item.update(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
        if error:
            item['response_body_base64'] = base64.b64encode(value[:65536]).decode('ascii')
            item['response_body_truncated'] = len(value) > 65536
    return item


def _payload_retry_eligible(record, blocked):
    http = record.get('http', [])
    failures = [item for item in http if item.get('status') == 'error']
    if record.get('status') != 'error' or not failures:
        return False

    def malformed_rss(item):
        parsed = urllib.parse.urlparse(item['url'])
        host = (parsed.hostname or '').lower().removeprefix('www.')
        query = urllib.parse.parse_qs(parsed.query)
        rss = str((query.get('format') or [''])[0]).lower() == 'rss' or (
            parsed.hostname == 'news.google.com' and '/rss/' in parsed.path)
        return (item.get('error', '').startswith('SourcePayloadError:')
                and rss and host not in blocked)

    # Keep recovery of grouped RSS queries whose later requests succeeded.
    # Those good responses are reused from the initial execution transcript.
    if all(malformed_rss(item) for item in failures):
        return True
    # A denied primary must stay blocked; its already-configured RSS fallback
    # can still recover. The final FAILED source itself must be malformed RSS.
    if not malformed_rss(failures[-1]):
        return False
    for item in failures[:-1]:
        if malformed_rss(item):
            continue
        host = (urllib.parse.urlparse(item['url']).hostname or '').lower().removeprefix('www.')
        denial = blocked.get(host) or {}
        if (denial.get('code') not in (401, 403, 429)
                or not item.get('error', '').startswith(('HTTPError:', 'RecordedSourceError:'))):
            return False
    return True


def prefetch(watch, report, report_path, *, seconds=360, workers=8, payload_retry_delay=0.5):
    """Every configured query must complete, including its existing fallbacks."""
    if seconds <= 0 or workers < 1 or payload_retry_delay < 0:
        raise ValueError('collection budget and workers must be positive')
    queries = list(watch.QUERIES)
    if not queries:
        raise IncompleteCoverage('no source queries configured')
    report['news'] = [dict(index=i, query=q, status='not_started') for i, q in enumerate(queries)]
    report['query_count'] = len(queries)
    _save(report_path, report)
    context = mp.get_context('fork')
    deadline = time.monotonic() + seconds
    blocked, gate_lock = _ProviderBlocks(context), context.RLock()
    active, processes, traces = {}, [], {}
    failed_transcripts = {}
    pending_indices = list(range(len(queries)))
    next_index = 0
    try:
        for _ in range(min(workers, len(queries))):
            parent, child = context.Pipe()
            process = context.Process(target=_source_worker, args=(child, watch, blocked, gate_lock), daemon=True)
            process.start()
            child.close()
            processes.append((process, parent))

        def submit(connection):
            nonlocal next_index
            if next_index >= len(pending_indices) or time.monotonic() >= deadline:
                return
            index = pending_indices[next_index]
            next_index += 1
            reusable = [entry for entry in failed_transcripts.get(index, []) if entry[3] is None]
            connection.send((index, queries[index], reusable))
            active[connection] = index
            report['news'][index]['status'] = 'running'
            report['news'][index]['started_at_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
            print(f'war_collection_start index={index}', flush=True)

        def drain():
            while active and time.monotonic() < deadline:
                ready = wait(list(active), timeout=min(0.2, max(0, deadline - time.monotonic())))
                for connection in ready:
                    index = active.pop(connection)
                    record = report['news'][index]
                    try:
                        returned, elapsed, result = connection.recv()
                        if returned != index:
                            raise IncompleteCoverage('source worker returned wrong query index')
                        if time.monotonic() >= deadline:
                            record['status'] = 'deadline'
                            continue
                        record.update(status='error' if result['error'] else 'ok',
                                      elapsed_seconds=round(elapsed, 3), rows=result['rows'],
                                      requests=len(result['trace']),
                                      finished_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
                        record['http'] = [_http_record(url, value, error)
                                          for url, _, value, error in result['trace']]
                        for item, reused in zip(record['http'], result['reused']):
                            if reused:
                                item['reused_from_initial_attempt'] = True
                                item['initial_collection_started_at_utc'] = record['initial_attempt']['started_at_utc']
                                item['initial_collection_finished_at_utc'] = record['initial_attempt']['finished_at_utc']
                        record['reused_success_requests'] = sum(result['reused'])
                        record['fallback_recovered'] = bool(
                            not result['error'] and any(entry[3] for entry in result['trace']))
                        if result['error']:
                            record['error'] = result['error']
                            if 'initial_attempt' not in record:
                                failed_transcripts[index] = result['trace']
                        else:
                            record.pop('error', None)
                            traces[index] = result['trace']
                            attempts = [
                                {'host': (urllib.parse.urlparse(item.get('url', '')).hostname or '').lower().removeprefix('www.'),
                                 'status': item.get('status')}
                                for item in record['http']
                            ]
                            direct = _unverified_direct_fallback(record['query'], attempts)
                            if direct:
                                record['status'] = 'partial'
                                record['coverage_issue'] = {
                                    'original_host': direct,
                                    'reason': 'fallback_scope_not_verified',
                                }
                                record['error'] = 'original source unavailable; fallback scope unverified'
                        print(f"war_collection_done index={index} status={record['status']} elapsed={elapsed:.3f}s", flush=True)
                    except (EOFError, OSError) as exc:
                        record.update(status='worker_error', error=type(exc).__name__)
                        continue
                    submit(connection)
                _save(report_path, report)

        for _, connection in processes:
            submit(connection)
        _save(report_path, report)
        drain()
        # After the initial batch drains, retry only malformed RSS queries once.
        # Reuse only verified responses from this SAME execution, so formerly
        # healthy endpoints cannot create new failures during a whole-query retry.
        # Keep the same URL/identity, denial circuits and original total deadline.
        # The original failed response remains visible alongside the recovery.
        if not active:
            blocked_now = blocked.snapshot()
            retry = [r['index'] for r in report['news'] if _payload_retry_eligible(r, blocked_now)]
            if retry and deadline - time.monotonic() > payload_retry_delay:
                time.sleep(payload_retry_delay)
                pending_indices, next_index = retry, 0
                report['payload_retry_queries'] = retry
                for index in retry:
                    record = report['news'][index]
                    record['initial_attempt'] = dict(record)
                    record['payload_retry_attempts'] = 1
                    record['status'] = 'retry_waiting'
                for _, connection in processes:
                    submit(connection)
                drain()
            _save(report_path, report)
    finally:
        for process, connection in processes:
            # No atexit wait on hung network calls, and no abandoned workers.
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join()
            connection.close()
        # Workers are stopped; never wait on a lock held by a terminated worker.
        try:
            report['blocked_providers'] = blocked.snapshot()
        except (ValueError, UnicodeError):
            report['provider_circuit_error'] = 'interrupted registry update'
        report['max_inflight_source_requests'] = min(workers, len(queries))
        for record in report['news']:
            if record['status'] == 'running':
                record['status'] = 'deadline'
            elif record['status'] == 'not_started':
                record['status'] = 'not_started_deadline'
            elif record['status'] == 'retry_waiting':
                record['status'] = 'retry_not_started_deadline'
        _save(report_path, report)
    if any(record['status'] != 'ok' for record in report['news']):
        raise IncompleteCoverage('one or more configured queries did not complete')
    return queries, traces


def install_replay(watch, queries, traces):
    """Replay in base run's original order; never fetch silently on a cache miss."""
    original_news, original_req = watch.google_news, watch.req
    next_index = 0

    def news(query):
        nonlocal next_index
        index = next_index
        next_index += 1
        if index >= len(queries) or queries[index] != query:
            raise IncompleteCoverage('query order changed after collection')
        trace = iter(traces[index])
        violations = []

        def cached(url, timeout=20):
            try:
                expected, expected_timeout, value, error = next(trace)
            except StopIteration:
                violations.append('parser requested an uncollected HTTP request')
                raise IncompleteCoverage(violations[-1]) from None
            if (url, timeout) != (expected, expected_timeout):
                violations.append('parser HTTP request changed after collection')
                raise IncompleteCoverage(violations[-1])
            if error:
                raise RecordedSourceError(error)
            return value

        watch.req = cached
        try:
            rows, error = original_news(query)
            if violations:
                raise IncompleteCoverage(violations[0])
            if error:
                raise IncompleteCoverage('parser replay returned incomplete coverage: ' + str(error))
            if next(trace, None) is not None:
                raise IncompleteCoverage('parser skipped a collected HTTP request')
            return rows, None
        finally:
            watch.req = original_req

    def restore():
        watch.google_news = original_news
        watch.req = original_req

    def verify():
        if next_index != len(queries):
            raise IncompleteCoverage('base run skipped a configured query')

    watch.google_news = news
    return restore, verify


def _child_run(watch, run_and_verify, report_path, seconds, workers):
    os.setsid()
    report = {'complete': False, 'phase': 'collection', 'collection_budget_seconds': seconds}
    try:
        queries, traces = prefetch(watch, report, report_path, seconds=seconds, workers=workers)
        report['phase'] = 'parse_render_verify'
        _save(report_path, report)
        restore, verify_replayed = install_replay(watch, queries, traces)
        try:
            run_and_verify()
            verify_replayed()
        finally:
            restore()
        report.update(complete=True, phase='verified')
        _save(report_path, report)
    except BaseException as exc:
        try:
            _preserve_rejected(watch, report)
        except (OSError, ValueError) as capture_error:
            report['rejected_capture_error'] = type(capture_error).__name__ + ': ' + str(capture_error)
        _clean(watch)
        report.update(complete=False, phase='failed', error=type(exc).__name__ + ': ' + str(exc))
        _save(report_path, report)
        raise


def run_bounded(watch, run_and_verify, *, total_seconds=540, collection_seconds=360, workers=8):
    """No Telegram calls here; only verified complete runs leave send artifacts."""
    if total_seconds <= collection_seconds or collection_seconds <= 0:
        raise ValueError('total budget must exceed positive collection budget')
    watch.OUT.mkdir(parents=True, exist_ok=True)
    _clean(watch)
    _clean_rejected(watch)
    report_path = watch.OUT / 'war_peace_reconstruction_coverage.json'
    _save(report_path, {'complete': False, 'phase': 'starting', 'total_budget_seconds': total_seconds})
    process = mp.get_context('fork').Process(
        target=_child_run, args=(watch, run_and_verify, report_path, collection_seconds, workers))
    process.start()
    process.join(timeout=total_seconds)
    timed_out = process.is_alive()
    if timed_out:
        # The child owns its own process group, including fetch descendants.
        if os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.join()
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        report = {}
    report['total_budget_seconds'] = total_seconds
    if timed_out or process.exitcode != 0 or report.get('complete') is not True:
        if not report.get('rejected_artifacts'):
            try:
                _preserve_rejected(watch, report)
            except (OSError, ValueError) as capture_error:
                report['rejected_capture_error'] = type(capture_error).__name__ + ': ' + str(capture_error)
        _clean(watch)
        report.update(complete=False, exit_code=process.exitcode)
        if timed_out:
            report['error'] = 'total collection/render/verification deadline exceeded'
            for record in report.get('news', []):
                if record['status'] == 'running':
                    record['status'] = 'deadline'
                elif record['status'] == 'not_started':
                    record['status'] = 'not_started_deadline'
        report['phase'] = 'failed'
        _save(report_path, report)
        watch.SUMMARY.write_text(
            '# War watch incomplete\n\nCollection/render/verification did not complete. '
            'No alert or pending state retained. See war_peace_reconstruction_coverage.json.\n',
            encoding='utf-8')
        print('war_collection_incomplete=' + report.get('error', 'child failed'), flush=True)
        return 1
    _save(report_path, report)
    return 0

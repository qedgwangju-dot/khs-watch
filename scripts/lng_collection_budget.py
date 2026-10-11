"""Bounded read-only collection. Incomplete coverage cannot advance alert state."""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET


class IncompleteCoverage(RuntimeError):
    pass


def collect(tasks, *, deadline, workers=8, clock=time.monotonic, progress=print):
    """Return isolated results and complete coverage, without waiting for late I/O.

    Worker callbacks must be read-only and must not mutate shared application state.
    Daemon workers publish only into this invocation's queue; late results are ignored.
    """
    tasks = list(tasks)
    if workers < 1:
        raise ValueError("workers must be positive")
    if len({key for key, _ in tasks}) != len(tasks):
        raise ValueError('duplicate collection key')
    pending = queue.Queue()
    results = queue.Queue()
    stop = threading.Event()
    for task in tasks:
        pending.put(task)
    coverage = {key: {'status': 'not_started', 'elapsed_seconds': 0.0} for key, _ in tasks}
    values = {}

    def worker():
        while not stop.is_set() and clock() < deadline:
            try:
                key, fetch = pending.get_nowait()
            except queue.Empty:
                return
            if stop.is_set() or clock() >= deadline:
                return
            start = clock()
            results.put(('started', key, start, None))
            try:
                value = fetch()
                result = ('ok', value)
            except Exception as exc:
                result = ('error', type(exc).__name__ + ': ' + str(exc))
            results.put(('finished', key, clock(), (start, result)))

    for _ in range(min(workers, len(tasks))):
        threading.Thread(target=worker, daemon=True, name='lng-source').start()
    completed = 0
    while completed < len(tasks):
        remaining = deadline - clock()
        if remaining <= 0:
            break
        try:
            event, key, at, payload = results.get(timeout=min(remaining, 0.2))
        except queue.Empty:
            continue
        if event == 'started':
            coverage[key] = {'status': 'running', 'started': at, 'elapsed_seconds': 0.0}
            progress(f'collection_start source={key}', flush=True)
            continue
        start, (status, value) = payload
        if at > deadline:
            continue
        coverage[key] = {'status': status, 'elapsed_seconds': round(at - start, 3)}
        if status == 'ok':
            values[key] = value
        else:
            coverage[key]['error'] = value
        completed += 1
        progress(f'collection_done source={key} status={status} elapsed={at-start:.3f}s', flush=True)
    stop.set()
    for record in coverage.values():
        if record['status'] == 'running':
            record['status'] = 'deadline'
            record['elapsed_seconds'] = round(max(0, clock() - record.pop('started')), 3)
        elif record['status'] == 'not_started':
            record['status'] = 'not_started_deadline'
    return values, coverage


def news_urls(core, early_queries):
    sources = []
    for index, (category, query) in enumerate(core.NEWS_QUERIES):
        params = urllib.parse.urlencode({'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
        sources.append((f'news_en_{index:03d}_{category}', 'https://news.google.com/rss/search?' + params))
    for index, query in enumerate(early_queries):
        params = urllib.parse.urlencode({'q': query, 'hl': 'ko', 'gl': 'KR', 'ceid': 'KR:ko'})
        sources.append((f'news_ko_{index:03d}_alaska', 'https://news.google.com/rss/search?' + params))
    return sources


def install(core, *, early_queries, market_sources, total_seconds=420, news_seconds=300,
            market_seconds=90, workers=8, clock=time.monotonic):
    original_run = core.run
    original_news = core.fetch_news_item_set
    original_fetch = core.fetch_bytes
    report = {}
    deadline = 0.0

    def save_report():
        core.OUT_DIR.mkdir(parents=True, exist_ok=True)
        (core.OUT_DIR / 'lng_collection_coverage.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def check_phase(name, coverage):
        report[name] = coverage
        save_report()
        failed = [key for key, result in coverage.items() if result['status'] != 'ok']
        if failed:
            raise IncompleteCoverage(f'{name}: {len(failed)}/{len(coverage)} sources incomplete')
        if clock() >= deadline:
            raise IncompleteCoverage('total collection deadline exceeded')

    def fetch_news(max_age_hours=84):
        sources = news_urls(core, early_queries)
        def fetch(url):
            raw = original_fetch(url, timeout=8, attempts=2)
            root = ET.fromstring(raw)
            if root.tag != 'rss' or root.find('channel') is None:
                raise ValueError('source is not an RSS channel')
            return raw
        tasks = [(key, lambda url=url: fetch(url)) for key, url in sources]
        values, coverage = collect(tasks, deadline=min(deadline, clock() + news_seconds),
                                   workers=workers, clock=clock)
        for key, url in sources:
            coverage[key]['url'] = url
        check_phase('news', coverage)
        cached = {url: values[key] for key, url in sources}
        def cache_only(url, *args, **kwargs):
            if url not in cached:
                raise IncompleteCoverage('parser requested an uncollected source')
            return cached[url]
        # Preserve the existing parser, source aliases, cutoff and deduplication.
        core.fetch_bytes = cache_only
        try:
            items, errors = original_news(max_age_hours=max_age_hours)
        finally:
            core.fetch_bytes = original_fetch
        if errors:
            report['news_parser_errors'] = errors
            save_report()
            raise IncompleteCoverage('news parser reported incomplete coverage')
        return items, []

    def fetch_market():
        values, coverage = collect(list(market_sources.items()),
                                   deadline=min(deadline, clock() + market_seconds),
                                   workers=workers, clock=clock)
        check_phase('market', coverage)
        quotes = {}
        for result in values.values():
            quotes.update(result)
        missing = {'ttf', 'jkm', 'brent', 'bund10', 'us10'} - quotes.keys()
        if missing:
            raise IncompleteCoverage('required market quotes missing: ' + ', '.join(sorted(missing)))
        report["complete"] = True
        save_report()
        return quotes, []

    def run(setup_test):
        nonlocal deadline, report
        deadline = clock() + total_seconds
        report = {'complete': False, 'budget_seconds': total_seconds}
        core.clean_outputs()  # Remove stale pending/send artifacts even if collection fails.
        save_report()
        try:
            result = original_run(setup_test)
        except Exception as exc:
            core.clean_outputs()
            report['error'] = type(exc).__name__ + ': ' + str(exc)
            save_report()
            core.SUMMARY_PATH.write_text(
                '# LNG run failed\n\n' + type(exc).__name__ + ': ' + str(exc) +
                '\n\nNo alert or pending state created. See lng_collection_coverage.json.\n',
                encoding='utf-8')
            print(f'collection_incomplete: {exc}', flush=True)
            return 1
        report['run_exit_code'] = result
        save_report()
        return result

    core.fetch_news_item_set = fetch_news
    core.fetch_market_quotes = fetch_market
    core.run = run

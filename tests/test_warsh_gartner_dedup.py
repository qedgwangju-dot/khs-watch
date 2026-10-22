#!/usr/bin/env python3
"""Gartner official-item dedup and delivery contract (offline)."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import warsh_ai_taskforce_watch as base
import warsh_ai_taskforce_watch_v2 as watcher


def article(slug, published_date=None, suffix=""):
    d = published_date or datetime.now(timezone.utc).date()
    path = f"2026-{d.month:02d}-{d.day:02d}-{slug}"
    return {
        'title': "Gartner Survey Finds 38% of CHROs and CIOs Share an Understanding of AI Workforce",
        'url':f"https://www.gartner.com/en/newsroom/press-releases/{path}{suffix}",
        'published':datetime(d.year,d.month,d.day,tzinfo=timezone.utc).isoformat(),
    }


class GartnerDedupTests(unittest.TestCase):
    def setUp(self):
        self.state = {'fed_fingerprint':'frozen'}
        self.sent = []
        self.items = []
        self.patches = [
            patch.object(base,'load_state',side_effect=lambda:copy.deepcopy(self.state)),
            patch.object(base,'save_state',side_effect=self.save),
            patch.object(base,'fetch',return_value='AI productivity jobs policy updated.'),
            patch.object(base,'gartner_items',side_effect=lambda:self.items),
            patch.object(base,'send',side_effect=self.deliver),
        ]
        for p in self.patches:p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.state['fed_fingerprint'] = base.fingerprint(base.meaningful_text(base.clean_text(
            'AI productivity jobs policy updated.'
        )))

    def save(self,new):
        self.state=copy.deepcopy(new)

    def deliver(self,msg):
        self.sent.append(msg)
        return 900+len(self.sent)

    def test_migration_seeds_without_resending_old_headlines(self):
        old=article("gartner-identifies-four-shifts-shaping-the-future-of-work")
        self.items=[old]
        base.main()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.state['gartner_dedup_version'], 2)
        self.assertEqual(len(self.state['gartner_seen_keys']), 1)
        # Google query-parameter variants and a timestamp-only change
        # do not create new story keys.
        self.items=[{**old,'published':datetime.now(timezone.utc).isoformat(),
            'url':old['url']+'?utm_source=google&oc=5'}]
        base.main()
        self.assertEqual(self.sent, [])

    def test_only_genuine_new_article_once(self):
        self.items=[article('old-headline')]
        base.main()
        self.items=[article('old-headline'),article('new-policy-and-workforce-change')]
        base.main()
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.state['gartner_deliveries'][-1]['message_id'],901)
        base.main()
        self.assertEqual(len(self.sent),1)

    def test_old_resurfaced_article_cannot_trigger(self):
        self.items=[article('old-headline')]
        base.main()
        self.items=[article('old-headline'), article(
            'resurfaced-old-report',datetime.now(timezone.utc).date()-timedelta(days=44))]
        base.main()
        self.assertEqual(len(self.sent),0)

    def test_feed_failure_preserves_last_success(self):
        self.items=[article('old-headline')]
        base.main()
        previous=set(self.state['gartner_seen_keys'])
        self.items=[]
        base.main()
        self.assertEqual(set(self.state['gartner_seen_keys']),previous)
        self.assertEqual(len(self.sent),0)

    def test_failed_delivery_not_marked_seen(self):
        self.items=[article('old-headline')]
        base.main()
        self.items.append(article('new-workforce-news'))
        with patch.object(base,'send',side_effect=RuntimeError("Telegram failed")):
            with self.assertRaisesRegex(RuntimeError,'Telegram failed'):
                base.main()
        self.assertEqual(len(self.state['gartner_seen_keys']),1)
        base.main()
        self.assertEqual(len(self.sent),1)

    def test_unverified_google_link_never_passes(self):
        unverified=article('dummy-story')
        unverified['url']='https://news.google.com/rss/articles/fake?oc=5'
        self.assertIsNone(base.canonical_gartner_item(unverified))

    def test_official_rss_does_not_key_on_google_pubtime(self):
        old=article('a-real-newsroom-story')
        self.assertEqual(base.canonical_gartner_item(old)['key'],
                         base.canonical_gartner_item({
                             **old,'published':datetime.now(timezone.utc).isoformat(),
                             'url':old['url']+'?ref=feed'
                         })['key'])


if __name__ == '__main__': unittest.main()

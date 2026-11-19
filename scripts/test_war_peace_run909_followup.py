"""Run 909 headline and redacted fixture; never use network or live state."""
import base64
import copy
import hashlib
import html
import json
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import war_peace_reconstruction_watch_integrity as stage
import war_peace_reconstruction_watch_two_color as presentation


FIXTURE = Path(__file__).parent / 'test_fixtures' / 'war_run909_semantic_failure.json'


class Run909PendingDecision(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.alert = base64.b64decode(self.data['semantic_snapshot']['alert_utf8_base64'])
        self.evidence = base64.b64decode(self.data['semantic_snapshot']['evidence_utf8_base64'])
        self.pending = base64.b64decode(self.data['pending_utf8_base64'])
        self.row = json.loads(self.evidence)['articles'][0]

    def test_saved_title_through_presentation_gate(self):
        proof = self.data['semantic_proof']
        self.assertEqual(hashlib.sha256(self.alert).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(self.evidence).hexdigest(), proof['evidence_sha256'])
        self.assertEqual(self.row['id'], 'd4da223f5231b9b84670')
        self.assertFalse(self.row['body_verified'])
        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            for name, filename in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                                   'AUDIT': 'evidence.json', 'PENDING': 'pending.json'}.items():
                stack.enter_context(patch.object(stage.watch, name, folder / filename))
            stage.watch.STATE.write_text('{"seen": [], "source_aliases": {}}', encoding='utf-8')
            state = stage.watch.STATE.read_bytes()
            stage.watch.ALERT.write_bytes(self.alert)
            stage.watch.AUDIT.write_bytes(self.evidence)
            stage.watch.PENDING.write_bytes(self.pending)
            stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden')))
            presentation.Presenter(stage).verify_alert()
            shown = html.unescape(stage.watch.ALERT.read_text(encoding='utf-8'))
            receipt = json.loads(stage.watch.AUDIT.read_text(encoding='utf-8'))
            row = receipt['articles'][0]
            self.assertIn('<b>참고 1. 이란 대응 결정 발언 · 본문 미확인</b>', shown)
            self.assertIn(self.row['title_ko'], shown)
            self.assertIn(self.row['link'], shown)
            self.assertNotIn('🔴 [속보] <b>1. 이란·호르무즈</b>', shown)
            self.assertNotIn(' · 확전 · Axios', shown)
            self.assertIsNone(row['classification_color'])
            self.assertEqual(row['display_section'], 'context_reference')
            self.assertEqual(row['semantic_classification_color'], 'red')
            originals = json.loads(self.evidence)['articles']
            for old, actual, expected_color in zip(
                    originals[1:], receipt['articles'][1:], ('green', 'green', 'red')):
                self.assertEqual(actual['classification_color'], expected_color)
                self.assertEqual(actual['title_original'], old['title_original'])
                self.assertIn(old['link'], shown)
            self.assertIn('🔴 [신규] <b>3. 우크라이나·러시아</b>', shown)
            self.assertIn('시장 반응', shown)
            self.assertEqual(receipt['semantic_proof'], proof)
            self.assertEqual(stage.watch.PENDING.read_bytes(), self.pending)
            self.assertEqual(stage.watch.STATE.read_bytes(), state)

    def test_independent_actions_are_not_hidden(self):
        for suffix in ('; he orders an attack', '; forces launched missiles',
                       '; forces struck and attacked targets',
                       '; he threatens sanctions', '; peace talks resume'):
            with self.subTest(suffix=suffix):
                row = copy.deepcopy(self.row)
                row['title_original'] += suffix
                self.assertFalse(presentation._iran_not_rushing_decision(stage, row))

    def test_verified_body_retains_existing_classification(self):
        row = copy.deepcopy(self.row)
        row['body_verified'] = True
        self.assertFalse(presentation._iran_not_rushing_decision(stage, row))


if __name__ == '__main__':
    unittest.main()

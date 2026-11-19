"""Run 901 headline and reduced fixture; no network, send, or live state."""
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


FIXTURE = Path(__file__).parent / 'test_fixtures' / 'war_run901_semantic_failure.json'


class Run901SummitPresentation(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.snapshot = self.data['semantic_snapshot']
        self.alert = base64.b64decode(self.snapshot['alert_utf8_base64'])
        self.evidence = base64.b64decode(self.snapshot['evidence_utf8_base64'])
        self.row = json.loads(self.evidence)['articles'][1]

    def test_run901_headline_through_full_presentation_gate(self):
        proof = self.data['semantic_proof']
        self.assertEqual(hashlib.sha256(self.alert).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(self.evidence).hexdigest(), proof['evidence_sha256'])
        self.assertEqual(self.row['id'], '55778891d0aeb3fec572')
        pending = base64.b64decode(self.data['pending_utf8_base64'])
        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            for name, filename in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                                   'AUDIT': 'evidence.json', 'PENDING': 'pending.json'}.items():
                stack.enter_context(patch.object(stage.watch, name, folder / filename))
            stage.watch.STATE.write_text('{"seen": [], "source_aliases": {}}', encoding='utf-8')
            state = stage.watch.STATE.read_bytes()
            stage.watch.ALERT.write_bytes(self.alert)
            stage.watch.AUDIT.write_bytes(self.evidence)
            stage.watch.PENDING.write_bytes(pending)
            stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden')))
            presentation.Presenter(stage).verify_alert()
            shown = html.unescape(stage.watch.ALERT.read_text(encoding='utf-8'))
            receipt = json.loads(stage.watch.AUDIT.read_text(encoding='utf-8'))
            row = receipt['articles'][1]
            self.assertIn('🟢 [신규] <b>2. 미국·중국·러시아 · 정상회담 시간 배정 보도</b>', shown)
            self.assertIn(self.row['title_original'], shown)
            self.assertIn(self.row['link'], shown)
            self.assertNotIn('🔴 [신규] <b>2. 우크라이나·러시아</b>', shown)
            self.assertEqual(row['classification_color'], 'green')
            self.assertEqual(row['title_original'], self.row['title_original'])
            self.assertEqual(receipt['semantic_proof'], proof)
            self.assertEqual(stage.watch.PENDING.read_bytes(), pending)
            self.assertEqual(stage.watch.STATE.read_bytes(), state)

    def test_attack_and_failed_summit_are_not_hidden_as_diplomatic_allocation(self):
        for title in (
            '미·중·러 정상회담에 1시간 배정, 러시아군이 우크라이나를 공격했다',
            '미·중·러 정상회담에 1시간 배정됐으나 회담 결렬',
        ):
            with self.subTest(title=title):
                row = copy.deepcopy(self.row)
                row.update(title_original=title, title_ko=title, description=title)
                self.assertFalse(presentation._trilateral_summit_time_allocation(title))
                self.assertEqual(presentation.direction(stage, row), 'red')

    def test_ambiguous_attack_wording_does_not_enter_new_exception(self):
        # Broader untyped, compressed attack headlines remain a separate open
        # issue; this narrow fix must not add a new reason to classify them green.
        title = '미·중·러 정상회담에 1시간 배정, 러시아가 우크라이나 공습'
        self.assertFalse(presentation._trilateral_summit_time_allocation(title))

    def test_verified_red_event_still_has_priority(self):
        self.assertTrue(presentation._trilateral_summit_time_allocation(self.row['title_original']))
        with patch.object(stage, 'final_color', return_value='red'):
            self.assertEqual(presentation.direction(stage, copy.deepcopy(self.row)), 'red')


if __name__ == '__main__':
    unittest.main()

"""Run 899's saved semantic input, without network, sending, or live state."""
import base64
import copy
import hashlib
import html
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import war_peace_reconstruction_watch_integrity as stage
import war_peace_reconstruction_watch_two_color as presentation


FIXTURE = Path(__file__).parent / 'test_fixtures' / 'war_run899_semantic_failure.json'


class Run899SemanticChecks(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.snapshot = self.data['semantic_snapshot']
        self.alert = base64.b64decode(self.snapshot['alert_utf8_base64'])
        self.evidence = base64.b64decode(self.snapshot['evidence_utf8_base64'])
        self.row = json.loads(self.evidence)['articles'][0]

    def test_real_saved_input_through_presentation_gate(self):
        proof = self.data['semantic_proof']
        self.assertEqual(hashlib.sha256(self.alert).hexdigest(), proof['alert_sha256'])
        self.assertEqual(hashlib.sha256(self.evidence).hexdigest(), proof['evidence_sha256'])
        self.assertEqual(self.row['id'], 'f80df96a77d4652c6265')
        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            for name, filename in {'OUT': '.', 'STATE': 'state.json', 'ALERT': 'alert.txt',
                                   'AUDIT': 'evidence.json', 'PENDING': 'pending.json'}.items():
                stack.enter_context(patch.object(stage.watch, name, folder / filename))
            stage.watch.STATE.write_text('{"seen": [], "source_aliases": {}}', encoding='utf-8')
            original_state = stage.watch.STATE.read_bytes()
            stage.watch.ALERT.write_bytes(self.alert)
            stage.watch.AUDIT.write_bytes(self.evidence)
            stage.watch.PENDING.write_bytes(base64.b64decode(self.data['pending_utf8_base64']))
            stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network/send forbidden')))
            presentation.Presenter(stage).verify_alert()
            shown = html.unescape(stage.watch.ALERT.read_text(encoding='utf-8'))
            receipt = json.loads(stage.watch.AUDIT.read_text(encoding='utf-8'))
            row = receipt['articles'][0]
            self.assertIn(self.row['title_original'], shown)
            self.assertIn('APEC 정상회의·북미 접촉 전망', shown)
            self.assertIn('회의·접촉 전망', shown)
            self.assertNotIn('이란·호르무즈 · 우크라이나·러시아', shown)
            self.assertNotIn(' · 종전·협상 · ', shown)
            self.assertNotIn('🔴', shown)
            self.assertIsNone(row['classification_color'])
            self.assertEqual(row['display_section'], 'context_reference')
            self.assertEqual(receipt['semantic_proof'], proof)
            self.assertEqual(stage.watch.STATE.read_bytes(), original_state)

    def test_separate_attack_and_peace_action_are_not_hidden_as_outlook(self):
        for title, expected in (
            ('APEC 개막...북미 접촉 여부 촉각, 이란 공습 재개', 'red'),
            ('APEC 개막...북미 접촉 여부 촉각, 우크라 휴전 협상 합의', 'green'),
        ):
            with self.subTest(title=title):
                row = copy.deepcopy(self.row)
                row.update(title_original=title, title_ko=title)
                self.assertFalse(presentation._apec_contact_outlook(stage, row))
                self.assertEqual(presentation.direction(stage, row), expected)


if __name__ == '__main__':
    unittest.main()

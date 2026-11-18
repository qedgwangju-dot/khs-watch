"""Run 3448 provenance check using retained metadata; no real Telegram calls."""
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import preopen_daily_status as status

FIXTURE = Path(__file__).parent / 'fixtures/kofia_preopen_run3448_provenance.json'


class KofiaPreopenRun3448Provenance(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.cfg = {k: root / (k + '.json') for k in ('state', 'receipt', 'pending')}
        self.now = dt.datetime(2026, 11, 19, 7, 13, 37, tzinfo=status.KST)
        # The complete historical Telegram message was not retained. Only this
        # saved status line is real; the surrounding text is local test data.
        self.message = 'synthetic heading\nsynthetic context\n' + self.case['saved_receipt']['status']

    def emit_receipt(self, topic, runtime):
        env = {
            'GITHUB_SHA': self.case['saved_receipt']['code_sha'],
            'GITHUB_RUN_ID': self.case['provenance']['run_id'],
            'TELEGRAM_BOT_TOKEN': 'LOCAL_MOCK_TOKEN',
            'TELEGRAM_CHAT_ID': '-12345',
            'EXPECTED_TELEGRAM_BOT_USERNAME': 'local_mock_bot',
        }
        if runtime is not None:
            env['KOFIA_CODE_SHA'] = runtime
        ack = {'ok': True, 'result': {'message_id': self.case['saved_receipt']['message_id'],
               'date': 1795030417, 'from': {'username': 'local_mock_bot'},
               'chat': {'id': -12345}, 'text': self.message}}
        with patch.dict(os.environ, env, clear=True), \
             patch('urllib.request.urlopen', side_effect=AssertionError('network prohibited')), \
             patch.object(status, '_telegram_json', side_effect=[{'ok': True, 'result': {'username': 'local_mock_bot'}}, ack]) as api, \
             contextlib.redirect_stdout(io.StringIO()):
            status.send_message(topic, self.cfg, self.message, self.now)
            self.assertEqual(api.call_count, 2)
        receipt = json.loads(self.cfg['receipt'].read_text(encoding='utf-8'))
        pending = json.loads(self.cfg['pending'].read_text(encoding='utf-8'))
        self.assertEqual(receipt, pending)
        self.assertEqual(receipt['run_id'], self.case['provenance']['run_id'])
        self.assertEqual(receipt['message_sha256'], hashlib.sha256(self.message.encode('utf-8')).hexdigest())
        self.assertEqual(receipt['status'], self.case['saved_receipt']['status'])
        return receipt

    def test_actual_run_metadata_uses_post_refresh_runtime(self):
        self.assertNotEqual(self.case['saved_receipt']['code_sha'], self.case['actual_post_refresh_code_sha'])
        receipt = self.emit_receipt('kofia', self.case['actual_post_refresh_code_sha'])
        self.assertEqual(receipt['code_sha'], self.case['actual_post_refresh_code_sha'])

    def test_missing_runtime_does_not_claim_header_is_runtime(self):
        receipt = self.emit_receipt('kofia', None)
        self.assertIsNone(receipt['code_sha'])

    def test_us_family_retains_existing_header_behavior(self):
        receipt = self.emit_receipt('us', self.case['actual_post_refresh_code_sha'])
        self.assertEqual(receipt['code_sha'], self.case['saved_receipt']['code_sha'])


if __name__ == '__main__':
    unittest.main()

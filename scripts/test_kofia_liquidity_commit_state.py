import copy
import hashlib
import json
from pathlib import Path
import unittest

from kofia_liquidity_commit_state import keep_incoming

BASE = json.loads(Path('tests/fixtures/kofia_source_20261012.json').read_text(encoding='utf-8'))['pending']
BASE['delivery_receipt'] = {'message_id': 352, 'timestamp_utc': '2026-10-13T11:41:59+00:00'}


class CommitTests(unittest.TestCase):
    def setUp(self):
        self.current = copy.deepcopy(BASE)
        self.incoming = copy.deepcopy(BASE)
        self.incoming['prior_fingerprint'] = BASE['fingerprint']
        self.incoming['delivery_receipt'] = {'message_id': 1, 'timestamp_utc': '2026-10-13T23:00:00+00:00'}

    def test_confirmed_same_value_correction_can_advance_version(self):
        self.assertTrue(keep_incoming(self.current, self.incoming))

    def test_unconfirmed_candidate_cannot_advance(self):
        self.incoming['delivery_receipt'] = {}
        with self.assertRaises(RuntimeError): keep_incoming(self.current, self.incoming)

    def test_newer_snapshot_is_preserved(self):
        self.current['snapshot_date'] = '20261013'
        self.assertFalse(keep_incoming(self.current, self.incoming))

    def test_newer_same_date_receipt_is_preserved(self):
        self.current['delivery_receipt']['timestamp_utc'] = '2026-10-14T00:00:00+00:00'
        self.assertFalse(keep_incoming(self.current, self.incoming))

    def test_same_date_value_race_is_not_overwritten(self):
        self.current['values']['deposit']['value'] += 1
        self.current['fingerprint'] = hashlib.sha256(json.dumps(self.current['values'], separators=(',', ':')).encode()).hexdigest()
        with self.assertRaisesRegex(RuntimeError, 'changed during delivery'): keep_incoming(self.current, self.incoming)

    def test_boolean_confirmation_id_is_not_an_acknowledgement(self):
        self.incoming['delivery_receipt']['message_id'] = True
        with self.assertRaisesRegex(RuntimeError, 'no confirmed delivery'): keep_incoming(self.current, self.incoming)


if __name__ == '__main__':
    unittest.main()

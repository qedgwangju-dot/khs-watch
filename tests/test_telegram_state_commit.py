import base64
import json
import os
import pathlib
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from scripts import telegram_state_commit as saver


class TelegramStateCommitTests(unittest.TestCase):
    def test_newer_remote_wins(self):
        incoming = {"last_checked_kst": "2026-10-08T23:50:00+09:00"}
        remote = {"last_checked_kst": "2026-10-08T23:55:00+09:00"}
        self.assertTrue(saver.incoming_superseded(incoming, remote))
        self.assertFalse(saver.incoming_superseded(remote, incoming))

    def test_conflict_refetch_uses_latest_sha_and_succeeds(self):
        path = pathlib.Path("data/europe_sovereign_yield_state.json")
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as dirname:
            try:
                os.chdir(dirname)
                path.parent.mkdir()
                incoming = {"last_checked_kst": "2026-10-08T23:56:00+09:00", "active": {"fr": True}}
                path.write_text(json.dumps(incoming), encoding="utf-8")
                calls = []
                def api(url, token, payload=None):
                    calls.append(payload)
                    if payload is None:
                        version = "old_sha" if calls.count(None) == 1 else "new_sha"
                        remote = {"last_checked_kst": "2026-10-08T23:55:00+09:00"}
                        return {"sha": version,
                                "content": base64.b64encode(json.dumps(remote).encode()).decode()}
                    if payload["sha"] == "old_sha":
                        raise urllib.error.HTTPError(url, 409, "conflict", None, None)
                    self.assertEqual(payload["sha"], "new_sha")
                    self.assertEqual(json.loads(base64.b64decode(payload["content"])), incoming)
                    return {"commit": {"sha": "abcdef1234567890"}}
                with patch.object(saver, "_api", side_effect=api):
                    result = saver.persist(path, "owner/repo", "test_token", sleep=lambda _: None)
                self.assertEqual(result, "saved")
                self.assertEqual(len(calls), 4)
            finally:
                os.chdir(old_cwd)

    def test_rejects_unexpected_state_file(self):
        with self.assertRaises(ValueError):
            saver.persist(pathlib.Path("data/other_state.json"), "owner/repo", "token")

    def test_existing_newer_remote_does_not_write(self):
        path = pathlib.Path("data/ecb_policy_watch_state.json")
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as dirname:
            try:
                os.chdir(dirname)
                path.parent.mkdir()
                path.write_text(json.dumps({"last_checked_kst": "2026-10-08T23:50:00+09:00"}))
                remote = {"last_checked_kst": "2026-10-08T23:58:00+09:00"}
                def api(url, token, payload=None):
                    self.assertIsNone(payload)
                    return {"sha": "newer", "content": base64.b64encode(json.dumps(remote).encode()).decode()}
                with patch.object(saver, "_api", side_effect=api):
                    self.assertEqual(saver.persist(path, "owner/repo", "token"), "skip_newer_remote")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()

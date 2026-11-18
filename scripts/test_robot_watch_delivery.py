"""No-network fault injection for complete-article delivery and recovery."""
import base64
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import zipfile

import robot_watch_delivery as delivery


CHAT = "-123456789"
RUN_ID = 9001


def fixture(size=1900):
    keys = [hashlib.sha256(f"event-{i}".encode()).hexdigest() for i in range(2)]
    events = [{"key": key, "link": f"https://example.org/article/{i}?a=1&b=2"}
              for i, key in enumerate(keys)]
    blocks = [f'<b>{i + 1}. Event {i}</b>\n' + "가" * size +
              f'\n<a href="https://example.org/article/{i}?a=1&amp;b=2">원문</a>'
              for i in range(2)]
    text = "<b>Robot report</b>\n\n" + "\n\n".join(blocks) + "\n<b>판정 기준</b> 새 사실"
    return text, {"seeded": True, "updated_at": "2026-11-18T00:00:00+00:00",
                  "last_selected": keys, "last_selected_events": events, "seen": ["historic"] + keys}


class Transport:
    def __init__(self, second="success", wrong_recipient=False, wrong_bot=False):
        self.calls = []
        self.sends = 0
        self.second = second
        self.wrong_recipient = wrong_recipient
        self.wrong_bot = wrong_bot

    def __call__(self, method, payload=None):
        self.calls.append(method)
        if method == "getMe":
            return {"ok": True, "result": {"username": "unexpected_bot" if self.wrong_bot else delivery.EXPECTED_BOT}}
        self.sends += 1
        if self.sends == 2 and self.second == "timeout":
            raise TimeoutError("injected timeout; fixture must not leak")
        if self.sends == 2 and self.second == "reject":
            return {"ok": False, "error_code": 400}
        return {"ok": True, "result": {"message_id": 100 + self.sends,
                                        "chat": {"id": 987 if self.wrong_recipient else int(CHAT)}}}


def pack(files, run_id=RUN_ID):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    raw = buffer.getvalue()
    metadata = {"id": 7001, "name": f"robotis-physical-ai-{run_id}", "expired": False,
                "size_in_bytes": len(raw), "digest": "sha256:" + hashlib.sha256(raw).hexdigest()}
    return raw, metadata


def failed_run(run_id=RUN_ID):
    return {"id": run_id, "status": "completed", "conclusion": "failure", "head_branch": "main",
            "path": ".github/workflows/" + delivery.WORKFLOW, "updated_at": "2026-11-18T01:00:00Z"}


class FakeAPI:
    repository = "owner/repo"

    def __init__(self, runs=None, files=None, skipped=False, conflict=False):
        self.state = {"seeded": True, "updated_at": "2026-11-16T12:00:00+00:00",
                      "seen": ["historic"], "other_metadata": {"preserve": [1, 2]}}
        self.sha = "sha-initial"
        self.runs = runs if runs is not None else [failed_run()]
        self.skipped = skipped
        self.conflict = conflict
        self.calls = []
        self.puts = []
        self.downloads = 0
        self.archive, self.metadata = pack(files or {})

    def json(self, path, method="GET", data=None):
        self.calls.append((path, method))
        if "/contents/" in path:
            if method == "GET":
                return {"sha": self.sha, "encoding": "base64",
                        "content": base64.b64encode(json.dumps(self.state).encode()).decode()}
            self.puts.append(copy.deepcopy(data))
            if self.conflict:
                self.conflict = False
                self.state["seen"].append("concurrent-existing")
                self.state["concurrent_metadata"] = "keep"
                self.sha = "sha-concurrent"
                raise delivery.APIError(409)
            if data["sha"] != self.sha:
                raise AssertionError("CAS must reread SHA")
            self.state = json.loads(base64.b64decode(data["content"]))
            self.sha = "sha-saved"
            return {"content": {"sha": self.sha}}
        if "/actions/workflows/" in path:
            return {"total_count": len(self.runs), "workflow_runs": copy.deepcopy(self.runs)}
        if "/jobs?" in path:
            return {"total_count": 1, "jobs": [{"status": "completed", "steps": [
                {"name": delivery.SEND_STEP, "status": "completed", "conclusion": "skipped" if self.skipped else "failure"}]}]}
        if "/artifacts?" in path:
            return {"total_count": 1, "artifacts": [copy.deepcopy(self.metadata)]}
        raise AssertionError("Unexpected API path")

    def download(self, artifact_id):
        self.downloads += 1
        return self.archive


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"GITHUB_RUN_ATTEMPT": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.receipt = self.directory / "receipts.json"
        self.attempt = self.directory / "attempts.json"
        self.text, self.pending = fixture()
        self.route = delivery.route_fingerprint(CHAT)

    def send(self, transport, text=None, pending=None):
        return delivery.send_alert(self.text if text is None else text,
                                   self.pending if pending is None else pending,
                                   "fake-token-no-network", CHAT, receipt_path=self.receipt,
                                   attempt_path=self.attempt, run_id=RUN_ID, transport=transport)

    def files(self):
        return {delivery.ALERT_PATH.name: self.text, delivery.PENDING_PATH.name: json.dumps(self.pending),
                delivery.RECEIPTS_PATH.name: self.receipt.read_text(),
                delivery.ATTEMPTS_PATH.name: self.attempt.read_text()}

    def test_complete_blocks_form_two_chunks_and_full_success(self):
        chunks = delivery.build_chunks(self.text, self.pending)
        self.assertEqual(len(chunks), 2)
        self.assertEqual([c["event_keys"] for c in chunks], [[k] for k in self.pending["last_selected"]])
        self.assertTrue(all(len(c["text"]) <= 3500 for c in chunks))
        self.assertEqual(self.send(Transport()), set(self.pending["last_selected"]))
        receipts = json.loads(self.receipt.read_text())
        self.assertEqual(delivery.check_receipts(self.text, self.pending, receipts, self.route), set(self.pending["last_selected"]))
        self.assertNotIn(CHAT, self.receipt.read_text())

    def test_second_timeout_keeps_first_receipt_and_marks_only_second_ambiguous(self):
        with self.assertRaises(delivery.DeliveryError):
            self.send(Transport(second="timeout"))
        receipts = json.loads(self.receipt.read_text())
        self.assertEqual(len(receipts), 1)
        self.assertEqual(delivery.check_receipts(self.text, self.pending, receipts, self.route), {self.pending["last_selected"][0]})
        attempts = json.loads(self.attempt.read_text())
        self.assertEqual([a["status"] for a in attempts], ["passed", "confirmed", "ambiguous"])
        self.assertEqual(delivery.artifact_delivery(self.files(), RUN_ID, self.route), ({self.pending["last_selected"][0]}, True))

    def test_explicit_rejection_is_not_an_ambiguous_post(self):
        with self.assertRaises(delivery.DeliveryError):
            self.send(Transport(second="reject"))
        self.assertEqual(delivery.artifact_delivery(self.files(), RUN_ID, self.route), ({self.pending["last_selected"][0]}, False))

    def test_entire_report_is_preflighted_before_any_api_call(self):
        self.text, self.pending = fixture(size=3600)
        transport = Transport()
        with self.assertRaises(delivery.DeliveryError):
            self.send(transport)
        self.assertEqual(transport.calls, [])
        self.assertEqual(json.loads(self.attempt.read_text())[0]["status"], "failed")
        self.assertEqual(delivery.artifact_delivery(self.files(), RUN_ID, self.route), (set(), False))

    def test_bad_bot_preflight_is_safe_to_retry_without_ambiguity(self):
        transport = Transport(wrong_bot=True)
        with self.assertRaises(delivery.DeliveryError):
            self.send(transport)
        self.assertEqual(transport.calls, ["getMe"])
        self.assertEqual(delivery.artifact_delivery(self.files(), RUN_ID, self.route), (set(), False))

    def test_missing_duplicate_and_cross_block_mapping_are_rejected(self):
        mutations = [self.text.replace("/article/1?", "/unknown/1?"),
                     self.text.replace("/article/1?", "/article/0?"),
                     self.text.replace("<b>2. ", "<b>1. "), self.text + '</b>']
        for text in mutations:
            with self.subTest(text=text[-50:]), self.assertRaises(delivery.DeliveryError):
                delivery.build_chunks(text, self.pending)
        pending = copy.deepcopy(self.pending)
        pending["last_selected_events"][1]["link"] = pending["last_selected_events"][0]["link"]
        with self.assertRaises(delivery.DeliveryError):
            delivery.build_chunks(self.text, pending)

    def test_wrong_recipient_never_produces_confirmed_keys(self):
        with self.assertRaises(delivery.DeliveryError):
            self.send(Transport(wrong_recipient=True))
        self.assertEqual(json.loads(self.receipt.read_text()), [])
        self.assertEqual(delivery.artifact_delivery(self.files(), RUN_ID, self.route), (set(), True))

    def test_modified_text_route_key_and_run_are_rejected(self):
        self.send(Transport())
        receipts = json.loads(self.receipt.read_text())
        for field, value in (("sha256", "0" * 64), ("route_fingerprint", "1" * 64),
                             ("event_keys", [self.pending["last_selected"][1]])):
            changed = copy.deepcopy(receipts)
            changed[0][field] = value
            with self.subTest(field=field), self.assertRaises(delivery.DeliveryError):
                delivery.check_receipts(self.text, self.pending, changed, self.route)
        with self.assertRaises(delivery.DeliveryError):
            delivery.check_receipts(self.text.replace("Robot report", "Changed report"), self.pending, receipts, self.route)
        with self.assertRaises(delivery.DeliveryError):
            delivery.artifact_delivery(self.files(), RUN_ID + 1, self.route)

    def test_archive_hash_name_path_and_size_are_checked(self):
        self.send(Transport())
        raw, metadata = pack(self.files())
        self.assertEqual(delivery.read_artifact(raw, metadata, RUN_ID), self.files())
        bad = copy.deepcopy(metadata)
        bad["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(delivery.DeliveryError):
            delivery.read_artifact(raw, bad, RUN_ID)
        bad = copy.deepcopy(metadata)
        bad["name"] = "other-workflow"
        with self.assertRaises(delivery.DeliveryError):
            delivery.read_artifact(raw, bad, RUN_ID)
        raw, metadata = pack({"../escape.json": "{}"})
        with self.assertRaises(delivery.DeliveryError):
            delivery.read_artifact(raw, metadata, RUN_ID)
        raw, metadata = pack({delivery.PENDING_PATH.name: "x" * (delivery.MAX_MEMBER + 1)})
        with self.assertRaises(delivery.DeliveryError):
            delivery.read_artifact(raw, metadata, RUN_ID)

    def test_recover_partial_confirmation_preserves_all_existing_state(self):
        with self.assertRaises(delivery.DeliveryError):
            self.send(Transport(second="reject"))
        api = FakeAPI(files=self.files())
        old = copy.deepcopy(api.state)
        result = delivery.recover(api, CHAT, state_path=self.directory / "state.json")
        self.assertEqual(result["confirmed_event_keys_recovered"], 1)
        self.assertEqual(set(api.state["seen"]), {"historic", self.pending["last_selected"][0]})
        for key in ("seeded", "updated_at", "other_metadata"):
            self.assertEqual(api.state[key], old[key])

    def test_recover_saves_confirmed_prefix_but_blocks_ambiguous_resend(self):
        with self.assertRaises(delivery.DeliveryError):
            self.send(Transport(second="timeout"))
        api = FakeAPI(files=self.files())
        with self.assertRaisesRegex(delivery.RecoveryBlocked, "Ambiguous"):
            delivery.recover(api, CHAT, state_path=self.directory / "state.json")
        self.assertIn(self.pending["last_selected"][0], api.state["seen"])
        self.assertNotIn(self.pending["last_selected"][1], api.state["seen"])

    def test_recovery_cas_conflict_rereads_and_preserves_concurrent_metadata(self):
        api = FakeAPI(conflict=True)
        result = delivery.merge_recovered(api, [{"run_id": RUN_ID, "event_keys": ["confirmed"]}])
        self.assertEqual(len(api.puts), 2)
        self.assertEqual(api.puts[1]["sha"], "sha-concurrent")
        self.assertEqual(set(result["seen"]), {"historic", "concurrent-existing", "confirmed"})
        self.assertEqual(result["concurrent_metadata"], "keep")
        self.assertEqual(result["other_metadata"], {"preserve": [1, 2]})

    def test_pre_send_guard_failures_need_no_artifact_and_do_not_use_twenty_send_limit(self):
        api = FakeAPI(runs=[failed_run(10000 + i) for i in range(25)], skipped=True)
        result = delivery.recover(api, CHAT, state_path=self.directory / "state.json")
        self.assertEqual(result["failed_send_runs_checked"], 0)
        self.assertEqual(api.downloads, 0)
        self.assertEqual(api.puts, [])

    def test_more_than_twenty_attempted_send_runs_is_not_silently_truncated(self):
        api = FakeAPI(runs=[failed_run(10000 + i) for i in range(21)])
        with self.assertRaisesRegex(delivery.RecoveryBlocked, "20 failed send"):
            delivery.recover(api, CHAT, state_path=self.directory / "state.json")
        self.assertEqual(api.downloads, 0)

    def test_previous_day_created_but_later_failed_run_is_inspected(self):
        run = failed_run()
        run["created_at"] = "2026-11-17T23:59:00Z"
        run["updated_at"] = "2026-11-18T00:05:00Z"
        api = FakeAPI(runs=[run], skipped=True)
        since = dt.datetime(2026, 11, 18, 0, 1, tzinfo=dt.timezone.utc)
        delivery._failed_runs(api, since)
        queries = [urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["created"][0]
                   for path, _ in api.calls if "/workflows/" in path]
        self.assertTrue(any(first <= "2026-11-17" <= last
                            for first, last in (value.split("..") for value in queries)))
        self.assertTrue(any(f"/runs/{RUN_ID}/jobs" in path for path, _ in api.calls))

    def test_same_run_rerun_is_blocked_before_api_or_send(self):
        api, transport = FakeAPI(), Transport()
        with patch.dict("os.environ", {"GITHUB_RUN_ATTEMPT": "2"}):
            with self.assertRaisesRegex(delivery.RecoveryBlocked, "rerun"):
                delivery.recover(api, CHAT, state_path=self.directory / "state.json")
            with self.assertRaisesRegex(delivery.RecoveryBlocked, "rerun"):
                self.send(transport)
        self.assertEqual(api.calls, [])
        self.assertEqual(transport.calls, [])

    def test_old_created_rerun_window_is_not_limited_to_thirty_five_days(self):
        run = failed_run()
        run["created_at"] = "2026-09-14T00:00:00Z"
        run["run_attempt"] = 2
        run["updated_at"] = "2026-11-18T00:05:00Z"
        api = FakeAPI(runs=[run], skipped=True)
        since = dt.datetime(2026, 11, 18, 0, 1, tzinfo=dt.timezone.utc)
        delivery._failed_runs(api, since)
        queries = [urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["created"][0]
                   for path, _ in api.calls if "/workflows/" in path]
        self.assertTrue(any(first <= "2026-09-14" <= last
                            for first, last in (value.split("..") for value in queries)))
        self.assertTrue(any(f"/runs/{RUN_ID}/jobs" in path for path, _ in api.calls))

    def test_existing_evidence_is_not_overwritten(self):
        self.send(Transport())
        before = self.receipt.read_bytes(), self.attempt.read_bytes()
        transport = Transport()
        with self.assertRaises(delivery.DeliveryError):
            self.send(transport)
        self.assertEqual(transport.calls, [])
        self.assertEqual((self.receipt.read_bytes(), self.attempt.read_bytes()), before)

    def test_storage_redirect_never_receives_github_authorization(self):
        requests = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return b"archive"
        class Opener:
            def open(self, request, timeout):
                requests.append(request)
                if len(requests) == 1:
                    raise urllib.error.HTTPError(request.full_url, 302, "Found",
                                                 {"Location": "https://example.blob.core.windows.net/artifact?signed=fixture"}, None)
                return Response()
        api = delivery.GitHubAPI("owner/repo", "test-secret")
        api.opener = Opener()
        self.assertEqual(api.download(7001), b"archive")
        self.assertIsNotNone(requests[0].get_header("Authorization"))
        self.assertIsNone(requests[1].get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()

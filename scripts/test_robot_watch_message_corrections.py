#!/usr/bin/env python3
"""Offline correction regressions; every network boundary is a test double."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import zipfile

import robot_watch_delivery as d
import robot_watch_message_corrections as c

CHAT = "123456789"
REPO = "fixture/repository"


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as value:
        for name, text in files.items():
            value.writestr(name, text)
    return stream.getvalue()


def fixture(run_id=44240720425, message_ids=(376, 377)):
    keys = [d._digest(f"fixture-{run_id}-{index}") for index in range(4)]
    events = [{"key": key, "link": f"https://example.invalid/{run_id}/{index}", "title": f"기사 {index}"}
              for index, key in enumerate(keys)]
    pending = {"last_selected": keys, "last_selected_events": events}
    blocks = [f'<b>{index + 1}. 기사 {index}</b>\n<a href="{events[index]["link"]}">원문</a>\n'
              + "검증 자료 " * 240 + "\n──────────────────" for index in range(4)]
    tail = "<b>판정 기준</b> 실제 자료\n환율 기준: 원본의 검증 환율 보존"
    text = "<b>원본 4건</b>\n\n" + "\n\n".join(blocks) + "\n" + tail
    chunks = d.build_chunks(text, pending)
    assert len(chunks) == 2
    route = d.route_fingerprint(CHAT)
    receipts = [{"schema_version": 1, "run_id": run_id, "attempt_id": f"send-{index}",
                 "chunk_index": index, "sha256": chunk["sha256"], "event_keys": chunk["event_keys"],
                 "route_fingerprint": route, "delivered_at_utc": "2026-11-18T04:58:00+00:00",
                 "chat_verification": "numeric_id_equal", "message_id": message_ids[index], "message_thread_id": None}
                for index, chunk in enumerate(chunks)]
    attempts = [{"schema_version": 1, "kind": "preflight", "run_id": run_id, "status": "passed",
                 "started_at_utc": "2026-11-18T04:57:00+00:00", "alert_sha256": d._digest(text.strip()),
                 "pending_sha256": d._pending_digest(pending), "route_fingerprint": route}]
    attempts.extend({**row, "kind": "send", "status": "confirmed", "started_at_utc": row["delivered_at_utc"]}
                    for row in receipts)
    files = {d.ALERT_PATH.name: text, d.PENDING_PATH.name: json.dumps(pending),
             d.RECEIPTS_PATH.name: json.dumps(receipts), d.ATTEMPTS_PATH.name: json.dumps(attempts)}
    raw = archive(files)
    artifact_id = run_id + 100
    metadata = {"id": artifact_id, "name": f"robotis-physical-ai-{run_id}", "expired": False,
                "digest": "sha256:" + hashlib.sha256(raw).hexdigest(), "size_in_bytes": len(raw),
                "workflow_run": {"id": run_id}}
    new_events = [copy.deepcopy(row) for index, row in enumerate(events) if index != 1]
    corrected_pending = {"last_selected": [row["key"] for row in new_events], "last_selected_events": new_events}
    new_blocks = [block for index, block in enumerate(blocks) if index != 1]
    new_blocks[0] = new_blocks[0].replace("검증 자료 ", "정정 자료 ", 1)
    new_blocks = [__import__("re").sub(r"^<b>\d+\.", f"<b>{index}.", block)
                  for index, block in enumerate(new_blocks, 1)]
    corrected = "✏️ <b>정정</b> 중복 제외·출처 정정\n\n<b>확인 3건</b>\n\n" + "\n\n".join(new_blocks) + "\n" + tail
    new_chunks = d.build_chunks(corrected, corrected_pending)
    assert len(new_chunks) == 2
    batch = {"batch_id": f"correction-fixture-{run_id}", "source_run_id": run_id,
             "artifact_id": artifact_id, "artifact_digest": metadata["digest"], "route_fingerprint": route,
             "message_ids": list(message_ids), "original_alert_sha256": d._digest(text.strip()),
             "original_pending_sha256": d._pending_digest(pending), "original_receipts_sha256": c.object_sha(receipts),
             "original_chunk_sha256": [row["sha256"] for row in receipts], "removed_event_keys": [keys[1]],
             "article_changes": {keys[0]: "replace_article"}, "corrected_text": corrected,
             "corrected_pending": corrected_pending, "corrected_chunk_sha256": [row["sha256"] for row in new_chunks]}
    batch["payload_sha256"] = c.payload_sha(batch, [dict(chunk, message_id=mid) for chunk, mid in zip(new_chunks, message_ids)])
    state = {"seeded": True, "updated_at": "2026-11-18T05:00:00+00:00",
             "seen": [d._digest(f"historic-{i}") for i in range(938)] + keys,
             "groups": ["unchanged"], "other_metadata": {"preserve": [1, 2, 3]},
             "delivery_history": [{"run_id": run_id, "outcome": "sent", "message_ids": list(message_ids),
                                   "recipient_verified": True, "confirmed_event_keys": keys}]}
    manifest = {"schema_version": 1, "repository": REPO, "expected_bot": d.EXPECTED_BOT, "batches": [batch]}
    return manifest, state, files, raw, metadata


class API:
    repository = REPO

    def __init__(self, data, *, conflict=False):
        manifest, state, files, raw, metadata = data
        self.state, self.sha = copy.deepcopy(state), "state-1"
        self.artifacts = {metadata["id"]: [copy.deepcopy(metadata), raw]}
        self.run_ids = {manifest["batches"][0]["source_run_id"]}
        self.calls, self.puts, self.downloads = [], [], []
        self.conflict = conflict

    def json(self, path, method="GET", data=None):
        self.calls.append((path, method))
        if "/contents/" in path:
            if method == "GET":
                return {"encoding": "base64", "content": base64.b64encode(json.dumps(self.state).encode()).decode(), "sha": self.sha}
            self.puts.append(copy.deepcopy(data))
            if self.conflict:
                self.conflict = False
                self.state["seen"].append("concurrent-key")
                self.state["concurrent_metadata"] = {"keep": True}
                self.sha = "state-concurrent"
                raise d.APIError(409)
            if data["sha"] != self.sha:
                raise AssertionError("CAS must use the newly read SHA")
            self.state = json.loads(base64.b64decode(data["content"]))
            self.sha += "x"
            return {"content": {"sha": self.sha}}
        if "/actions/artifacts/" in path:
            return copy.deepcopy(self.artifacts[int(path.rsplit("/", 1)[1])][0])
        if "/actions/runs/" in path:
            run_id = int(path.rsplit("/", 1)[1])
            assert run_id in self.run_ids
            return {"id": run_id, "status": "completed", "conclusion": "success", "head_branch": "main",
                    "path": ".github/workflows/" + d.WORKFLOW}
        raise AssertionError("Unexpected GitHub API path")

    def download(self, artifact_id):
        self.downloads.append(artifact_id)
        return self.artifacts[artifact_id][1]


class Telegram:
    def __init__(self, modes=(), stored=None, bad_bot=False):
        self.modes, self.stored, self.bad_bot = list(modes), stored if stored is not None else {}, bad_bot
        self.calls, self.edits = [], []

    def __call__(self, method, payload=None):
        self.calls.append(method)
        if method == "getMe":
            return {"ok": True, "result": {"username": "wrong" if self.bad_bot else d.EXPECTED_BOT, "id": 7}}
        assert method == "editMessageText", "Sending or deleting a message is forbidden"
        self.edits.append(copy.deepcopy(payload))
        mode = self.modes.pop(0) if self.modes else "auto"
        mid, text = payload["message_id"], c.plain_text(payload["text"])
        if mode in {"not_modified", "bad_not_modified", "http_not_modified"} or (mode == "auto" and self.stored.get(mid) == text):
            error = {"ok": False, "error_code": 400, "description": c.NOT_MODIFIED_DESCRIPTION}
            if mode == "bad_not_modified":
                error["description"] = "Bad Request: message is not modified"
            if mode == "http_not_modified":
                raise urllib.error.HTTPError("https://example.invalid/without-secrets", 400, "Bad Request", {}, io.BytesIO(json.dumps(error).encode()))
            return error
        if mode == "reject":
            return {"ok": False, "error_code": 400, "description": "Bad Request: invalid message"}
        if mode == "timeout_before":
            raise TimeoutError()
        self.stored[mid] = text
        if mode == "timeout_after":
            raise TimeoutError()
        return {"ok": True, "result": {"message_id": mid + 1 if mode == "wrong_id" else mid,
                                         "chat": {"id": 1 if mode == "wrong_recipient" else int(CHAT)},
                                         "text": text + " changed" if mode == "wrong_text" else text}}


class CorrectionTest(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.manifest = self.data[0]
        self.api = API(self.data)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "receipts.json"

    def apply(self, telegram, **kwargs):
        return c.apply_corrections(kwargs.pop("manifest", self.manifest), kwargs.pop("api", self.api),
                                   "offline-token", kwargs.pop("chat", CHAT), receipt_path=self.output,
                                   transport=telegram, **kwargs)

    def test_success_preserves_942_keys_and_unrelated_metadata(self):
        original = copy.deepcopy(self.api.state)
        telegram = Telegram()
        result = self.apply(telegram)
        self.assertEqual(result["messages_edited"], 2)
        self.assertEqual([p["message_id"] for p in telegram.edits], [376, 377])
        self.assertEqual(len(self.api.state["seen"]), 942)
        self.assertEqual({k: v for k, v in self.api.state.items() if k != "message_corrections"}, original)
        record = next(iter(self.api.state["message_corrections"].values()))
        self.assertEqual(record["completed_message_ids"], [376, 377])
        self.assertEqual(record["status"], "completed")

    def test_completed_batch_causes_no_telegram_or_artifact_requests(self):
        self.apply(Telegram())
        downloads, writes = len(self.api.downloads), len(self.api.puts)
        telegram = Telegram()
        result = self.apply(telegram)
        self.assertTrue(result["already_completed"])
        self.assertEqual(telegram.calls, [])
        self.assertEqual(len(self.api.downloads), downloads)
        self.assertEqual(len(self.api.puts), writes)

    def test_partial_confirmed_record_cannot_skip_without_full_evidence(self):
        with self.assertRaises(c.CorrectionError):
            self.apply(Telegram(["auto", "timeout_after"]))
        record = next(iter(self.api.state["message_corrections"].values()))
        del record["messages"]["376"]["response_text_sha256"]
        telegram = Telegram()
        with self.assertRaisesRegex(c.CorrectionError, "evidence"):
            self.apply(telegram)
        self.assertEqual(telegram.calls, [])

    def test_missing_original_chunk_hashes_fail_before_network(self):
        manifest = copy.deepcopy(self.manifest)
        del manifest["batches"][0]["original_chunk_sha256"]
        telegram = Telegram()
        with self.assertRaisesRegex(c.CorrectionError, "chunk hashes"):
            self.apply(telegram, manifest=manifest)
        self.assertEqual(self.api.calls, [])
        self.assertEqual(telegram.calls, [])

    def test_second_failure_retry_only_sets_the_same_second_message(self):
        first = Telegram(["auto", "timeout_after"])
        with self.assertRaises(c.CorrectionError):
            self.apply(first)
        record = next(iter(self.api.state["message_corrections"].values()))
        self.assertEqual(record["completed_message_ids"], [376])
        retry = Telegram(stored=first.stored)
        self.apply(retry)
        self.assertEqual([p["message_id"] for p in retry.edits], [377])
        self.assertEqual(retry.edits[0], first.edits[1])
        record = next(iter(self.api.state["message_corrections"].values()))
        self.assertEqual(record["messages"]["377"]["verification"], "prior_identical_request_exact_not_modified")

    def test_exact_http_not_modified_after_saved_intent_is_supported(self):
        with self.assertRaises(c.CorrectionError):
            self.apply(Telegram(["timeout_after"]))
        self.apply(Telegram(["http_not_modified", "auto"]))
        self.assertTrue(c._completed(self.api.state, c.validate_manifest(self.manifest)[0]))

    def test_not_modified_on_first_attempt_is_not_unearned_confirmation(self):
        with self.assertRaises(c.CorrectionError):
            self.apply(Telegram(["not_modified"]))
        record = next(iter(self.api.state["message_corrections"].values()))
        self.assertEqual(record["completed_message_ids"], [])

    def test_similar_error_string_cannot_confirm_a_retry(self):
        with self.assertRaises(c.CorrectionError):
            self.apply(Telegram(["timeout_after"]))
        with self.assertRaises(c.CorrectionError):
            self.apply(Telegram(["bad_not_modified"]))

    def test_wrong_recipient_id_and_reply_text_are_rejected(self):
        for mode in ("wrong_recipient", "wrong_id", "wrong_text"):
            with self.subTest(mode=mode):
                api = API(self.data)
                telegram = Telegram([mode])
                with self.assertRaises(c.CorrectionError):
                    self.apply(telegram, api=api)
                record = next(iter(api.state["message_corrections"].values()))
                self.assertEqual(record["completed_message_ids"], [])
                self.assertEqual(len(telegram.edits), 1)

    def test_wrong_route_and_bot_fail_before_edit(self):
        telegram = Telegram()
        with self.assertRaises(c.CorrectionError):
            self.apply(telegram, chat="987654321")
        self.assertEqual(telegram.calls, [])
        telegram = Telegram(bad_bot=True)
        with self.assertRaises(c.CorrectionError):
            self.apply(telegram)
        self.assertEqual(telegram.calls, ["getMe"])
        self.assertEqual(self.api.puts, [])

    def test_original_archive_digest_and_alert_tampering_fail_before_telegram(self):
        artifact_id = self.manifest["batches"][0]["artifact_id"]
        self.api.artifacts[artifact_id][1] += b"tampered"
        telegram = Telegram()
        with self.assertRaises(d.DeliveryError):
            self.apply(telegram)
        self.assertEqual(telegram.calls, [])
        files = copy.deepcopy(self.data[2])
        files[d.ALERT_PATH.name] = files[d.ALERT_PATH.name].replace("원본", "변조")
        raw = archive(files)
        api = API(self.data)
        api.artifacts[artifact_id][1] = raw
        api.artifacts[artifact_id][0]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        manifest = copy.deepcopy(self.manifest)
        manifest["batches"][0]["artifact_digest"] = api.artifacts[artifact_id][0]["digest"]
        with self.assertRaisesRegex(c.CorrectionError, "modified"):
            self.apply(telegram, api=api, manifest=manifest)
        self.assertEqual(telegram.calls, [])

    def test_modified_replacement_or_history_fails_before_edit(self):
        changed = copy.deepcopy(self.manifest)
        changed["batches"][0]["corrected_text"] += "변조"
        telegram = Telegram()
        with self.assertRaises(c.CorrectionError):
            self.apply(telegram, manifest=changed)
        self.api.state["delivery_history"][0]["message_ids"] = [1, 2]
        with self.assertRaises(c.CorrectionError):
            self.apply(telegram)
        self.assertEqual(telegram.calls, [])

    def test_cas_conflict_keeps_concurrent_keys_and_metadata(self):
        api = API(self.data, conflict=True)
        self.apply(Telegram(), api=api)
        self.assertIn("concurrent-key", api.state["seen"])
        self.assertEqual(api.state["concurrent_metadata"], {"keep": True})
        self.assertEqual(api.puts[1]["sha"], "state-concurrent")
        self.assertEqual(api.state["other_metadata"], self.data[1]["other_metadata"])

    def test_two_batches_edit_only_the_four_approved_ids(self):
        second = fixture(44241145265, (378, 379))
        manifest = copy.deepcopy(self.manifest)
        manifest["batches"].extend(second[0]["batches"])
        self.api.artifacts[second[4]["id"]] = [second[4], second[3]]
        self.api.run_ids.add(second[0]["batches"][0]["source_run_id"])
        self.api.state["seen"].extend(second[1]["delivery_history"][0]["confirmed_event_keys"])
        self.api.state["delivery_history"].extend(second[1]["delivery_history"])
        telegram = Telegram()
        result = self.apply(telegram, manifest=manifest)
        self.assertEqual(result["batches_completed"], 2)
        self.assertEqual([row["message_id"] for row in telegram.edits], [376, 377, 378, 379])

    def test_html_reply_comparison_decodes_entities(self):
        self.assertEqual(c.plain_text('<b>A &amp; B</b>\n<a href="https://example.invalid/?x=1&amp;y=2">원문</a>'), "A & B\n원문")

    def test_reviewed_actual_manifest_has_two_seven_article_two_message_batches(self):
        path = Path(__file__).resolve().parents[1] / c.MANIFEST_PATH
        manifest = json.loads(path.read_text(encoding="utf-8"))
        plans = c.validate_manifest(manifest)
        self.assertEqual([p["batch"]["source_run_id"] for p in plans], [44240720425, 44241145265])
        self.assertEqual([p["batch"]["message_ids"] for p in plans], [[376, 377], [378, 379]])
        for plan in plans:
            self.assertEqual(len(plan["batch"]["corrected_pending"]["last_selected"]), 7)
            self.assertEqual(len(plan["messages"]), 2)
            self.assertTrue(all(len(m["text"]) <= d.MAX_CHARS for m in plan["messages"]))
            self.assertEqual(len(plan["batch"]["removed_event_keys"]), 1)
        self.assertIn("한화투자증권", plans[0]["batch"]["corrected_text"])
        self.assertNotIn("CFO", plans[0]["batch"]["corrected_text"])
        self.assertIn("1,336.2100원", plans[0]["batch"]["corrected_text"])
        self.assertIn("1,468.3600원", plans[1]["batch"]["corrected_text"])
        self.assertIn("6,266.4억원", plans[1]["batch"]["corrected_text"])
        self.assertNotIn("21:29 KST", plans[1]["batch"]["corrected_text"])


if __name__ == "__main__":
    unittest.main()

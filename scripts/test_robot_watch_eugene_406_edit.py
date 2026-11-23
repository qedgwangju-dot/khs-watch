#!/usr/bin/env python3
"""Network-free tests for the one-message, no-send Eugene 406 correction."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import robot_watch_delivery as d
import robot_watch_message_corrections as c
import robot_watch_eugene_406_edit as e

CHAT = "1234567890"
SOURCE = 'https://www.eugenefn.com/common/files/amail/20261123_B2030_syyang0901_576.pdf'
OLD = (
    "🚨 <b>피지컬AI·로봇 공급망 구조 변화 감지</b>\n"
    "<b>신규 고신호 1건</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "<b>1. 유진 휴머노이드 산업 전망 유진투자증권 산업 분석</b>\n"
    "<b>분류</b>  유진투자증권 · 휴머노이드 밸류체인 단계별 선호도 전망\n"
    "<b>출처</b>  유진투자증권 · 2026-11-23 KST · "
    f'<a href="{SOURCE}"><b>원문</b></a>\n'
    "<b>확인</b>  원자료 대조\n"
    "💡 <b>핵심</b>  옛 요약입니다.\n"
    "⚠️ <b>체크</b>  옛 위험입니다.\n\n"
    "──────────────────\n"
    "<b>판정 기준</b>  검증된 새 사실만 알림."
)
PENDING = {
    "last_selected": [e.REPORT_KEY],
    "last_selected_events": [{
        "key": e.REPORT_KEY, "title": "유진 휴머노이드 산업 전망",
        "link": SOURCE,
    }],
}


class FakeAPI:
    repository = "fixture/robot-watch"

    def __init__(self, state):
        self.state = copy.deepcopy(state)
        self.sha = "initial-sha"

    def json(self, path, method="GET", data=None):
        if not path.endswith(d.STATE_PATH.as_posix()) and "/contents/" not in path:
            raise AssertionError("Unexpected API path")
        if method == "GET":
            raw = json.dumps(self.state, ensure_ascii=False).encode()
            return {"encoding": "base64", "content": base64.b64encode(raw).decode(),
                    "sha": self.sha}
        if method == "PUT":
            if data.get("sha") != self.sha:
                raise AssertionError("CAS must use current revision SHA")
            self.state = json.loads(base64.b64decode(data["content"]))
            self.sha = hashlib.sha256(data["content"].encode()).hexdigest()
            return {"content": {"sha": self.sha}}
        raise AssertionError("Other writes forbidden")


class ScopedEditTest(unittest.TestCase):

    def setUp(self):
        self.fake_sha = d._digest(OLD.strip())
        self.source_receipt = {
            "message_id": e.MESSAGE_ID, "chat_verification": "numeric_id_equal",
            "message_thread_id": None,
        }
        self.row = {
            "seeded": True, "seen": [e.REPORT_KEY, "historical-key"],
            "updated_at": "2026-11-23T12:06:00+00:00",
            "delivery_history": [{"run_id": e.SOURCE_RUN_ID, "outcome": "sent",
                                   "message_ids": [e.MESSAGE_ID], "recipient_verified": True,
                                   "confirmed_event_keys": [e.REPORT_KEY]}],
            "other_metadata": {"must_survive": True},
        }

    @contextmanager
    def fixture(self):
        with patch.object(e, "ORIGINAL_TEXT_SHA", self.fake_sha):
            with patch.object(e, "_check_original", return_value=(OLD, PENDING, self.source_receipt)):
                with tempfile.TemporaryDirectory() as td:
                    yield Path(td) / "receipt.json"

    def test_html_chunk_one_and_full_details(self):
        with self.fixture():
            new = e.replacement(OLD, PENDING)
        self.assertLessEqual(len(new), d.MAX_CHARS)
        self.assertLessEqual(len(c.plain_text(new)), 4096)
        chunks = d.build_chunks(new, PENDING)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["event_keys"], [e.REPORT_KEY])
        for required in ("2030년 13만", "2035년 170만", "2040년 787만",
                         "개발용 부품", "단순 모듈", "SI 프로젝트", "SI 운영",
                         "중국 166만", "2026년 1~3분기", "환산", "원문"):
            self.assertIn(required, new)
        self.assertNotIn("옛 요약입니다", new)
        self.assertEqual(new.count(SOURCE), 1)


    def test_pinned_archive_reader_accepts_only_original_seven_members(self):
        def mkzip(names):
            stream = io.BytesIO()
            with __import__("zipfile").ZipFile(stream,"w",__import__("zipfile").ZIP_DEFLATED) as z:
                for k in names:
                    z.writestr(k, "recovery file")
            return stream.getvalue()
        payload = mkzip(sorted(e.SOURCE_MEMBERS))
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        meta = {"name":f"robotis-physical-ai-{e.SOURCE_RUN_ID}",
                "digest":digest,"size_in_bytes":len(payload),"expired":False}
        with patch.object(e, "SOURCE_ARTIFACT_DIGEST",digest):
            self.assertEqual(set(e._read_source_members(payload,meta)),e.SOURCE_MEMBERS)
            with self.assertRaises(d.DeliveryError):
                e._read_source_members(mkzip(sorted(e.SOURCE_MEMBERS)+["unexpected.txt"]),meta)
            with self.assertRaises(d.DeliveryError):
                e._read_source_members(payload,{**meta,"digest":"sha256:"+("0"*64)})
            path_bytes=mkzip([k if k!="robotis_physical_ai_watch_status.md" else "unsafe/../robotis_physical_ai_watch_status.md"
                              for k in sorted(e.SOURCE_MEMBERS)])
            pathmeta={**meta,"digest":"sha256:"+hashlib.sha256(path_bytes).hexdigest(),
                      "size_in_bytes":len(path_bytes)}
            with patch.object(e,"SOURCE_ARTIFACT_DIGEST",pathmeta["digest"]):
                with self.assertRaises(d.DeliveryError):
                    e._read_source_members(path_bytes,pathmeta)

    def test_different_original_text_rejected_without_api(self):
        with self.fixture():
            with self.assertRaises(d.DeliveryError):
                e.replacement(OLD + " tampered", PENDING)

    def test_confirmed_edit_verification_and_repeat_noop(self):
        api = FakeAPI(self.row)
        methods = []
        def transport(method, payload=None):
            methods.append(method)
            if method == "getMe":
                return {"ok": True, "result": {"username": d.EXPECTED_BOT}}
            self.assertEqual(method, "editMessageText")
            self.assertEqual(payload["message_id"], 406)
            self.assertEqual(payload["chat_id"], CHAT)
            return {"ok": True, "result": {
                "chat": {"id": int(CHAT)},
                "message_id": 406, "message_thread_id": None,
                "text": c.plain_text(payload["text"])
            }}
        with self.fixture() as report_path:
            result = e.edit_once(api, "fake_token", CHAT, transport=transport,
                                 receipt_path=report_path)
            self.assertEqual(result["messages_edited"], 1)
            self.assertTrue(result["route_verified"])
            self.assertEqual(api.state["other_metadata"], {"must_survive": True})
            self.assertEqual(api.state["seen"], self.row["seen"])
            rec = api.state["eugene_message_edits"][e.CHECKPOINT]
            self.assertEqual(rec["status"], "confirmed")
            self.assertEqual(rec["verified_method"], "reply_message_id_recipient_text_equal")
            again = e.edit_once(api, "fake_token", CHAT, transport=transport,
                                receipt_path=report_path)
            self.assertTrue(again["already_confirmed"])
            self.assertEqual(again["messages_edited"], 0)
            self.assertEqual(methods, ["getMe", "editMessageText"])

    def test_unknown_edit_reply_marks_ambiguous_and_does_not_replay(self):
        api = FakeAPI(self.row)
        methods = []
        def transport(method, payload=None):
            methods.append(method)
            if method == "getMe":
                return {"ok": True, "result": {"username": d.EXPECTED_BOT}}
            raise TimeoutError("uncertain response")
        with self.fixture() as output:
            with self.assertRaises(d.DeliveryError):
                e.edit_once(api, "fake_token", CHAT, transport=transport,
                            receipt_path=output)
            self.assertEqual(api.state["eugene_message_edits"][e.CHECKPOINT]["status"], "ambiguous")
            with self.assertRaises(d.DeliveryError):
                e.edit_once(api, "fake_token", CHAT, transport=transport,
                            receipt_path=output)
        self.assertEqual(methods, ["getMe", "editMessageText"])

    def test_wrong_recipient_must_not_mark_confirmed(self):
        api = FakeAPI(self.row)
        def transport(method, payload=None):
            if method == "getMe":
                return {"ok": True, "result": {"username": d.EXPECTED_BOT}}
            return {"ok": True, "result": {
                "chat": {"id": 99}, "message_id": 406, "message_thread_id": None,
                "text": c.plain_text(payload["text"])}}
        with self.fixture() as output:
            with self.assertRaises(d.DeliveryError):
                e.edit_once(api, "fake_token", CHAT, transport=transport,
                            receipt_path=output)
        self.assertEqual(api.state["eugene_message_edits"][e.CHECKPOINT]["status"], "ambiguous")


if __name__ == "__main__":
    unittest.main()

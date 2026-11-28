#!/usr/bin/env python3
"""FX rotation-only durable delivery, using the existing Telegram route.

Commit an in-flight marker before POST. Promote the verified receipt and the
target delivery state atomically. Never retry an ambiguous response. GitHub is
public: store only keyed receipt proofs, not raw destination IDs or messages.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import hmac
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = "data/fx_sector_rotation_state.json"
LEDGER = "data/fx_sector_rotation_delivery.json"
PENDING = "out/fx_sector_rotation_pending_state.json"
ALERT = "out/fx_sector_rotation_alert.html"
DELIVERY_FIELDS = ("sent_level", "sent_weakening", "last_signal")
STATES = {"in_flight", "uncertain", "rejected", "confirmed"}


class DeliveryError(RuntimeError):
    pass


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def load_object(raw, label):
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise DeliveryError(label+" 형식 오류") from None
    if not isinstance(value, dict):
        raise DeliveryError(label+" 객체 형식 오류")
    return value


def read_local(root, path):
    try:
        return (root/path).read_bytes()
    except FileNotFoundError:
        return None


class Publisher:
    """CAS-style isolated Git index: no reset, force or broad git add."""
    def __init__(self, root, expected):
        self.root = Path(root)
        self.expected = dict(expected)

    def git(self, *args, data=None, env=None, check=True):
        try:
            r = subprocess.run(["git", *args], cwd=self.root, input=data,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=30, env=env)
        except (OSError, subprocess.TimeoutExpired):
            raise DeliveryError("Git 상태 저장 통신·실행 실패") from None
        if check and r.returncode:
            raise DeliveryError("Git 상태 저장 실패: "+args[0])
        return r

    def head(self):
        self.git("fetch", "--no-tags", "origin", "refs/heads/main")
        return self.git("rev-parse", "FETCH_HEAD").stdout.decode().strip()

    def at(self, head, path):
        if not self.git("ls-tree", "-z", head, "--", path).stdout:
            return None
        return self.git("show", head+":"+path).stdout

    def save(self, state, ledger):
        changes = {STATE: encoded(state), LEDGER: encoded(ledger)}
        wanted = {**self.expected, **changes}
        for attempt in range(3):
            head = self.head()
            current = {path: self.at(head, path) for path in self.expected}
            if current == wanted:
                self.expected = wanted
                return
            if current != self.expected:
                raise DeliveryError("원격 로테이션 상태 변경 감지 — 덮어쓰기 및 발송 중단")
            with tempfile.TemporaryDirectory(prefix="fx-rotation-index-") as temp:
                env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp)/"index"),
                           GIT_AUTHOR_NAME="fx-rotation-state[bot]",
                           GIT_AUTHOR_EMAIL="fx-rotation-state[bot]@users.noreply.github.com",
                           GIT_COMMITTER_NAME="fx-rotation-state[bot]",
                           GIT_COMMITTER_EMAIL="fx-rotation-state[bot]@users.noreply.github.com")
                self.git("read-tree", head, env=env)
                for path, raw in changes.items():
                    blob = self.git("hash-object", "-w", "--stdin", data=raw, env=env).stdout.decode().strip()
                    self.git("update-index", "--add", "--cacheinfo", "100644,"+blob+","+path, env=env)
                tree = self.git("write-tree", env=env).stdout.decode().strip()
                commit = self.git("commit-tree", tree, "-p", head,
                                  "-m", "Persist FX rotation observation and delivery ledger", env=env).stdout.decode().strip()
                # Non-force push preserves unrelated commits.
                p = self.git("push", "origin", commit+":refs/heads/main", check=False)
            if p.returncode == 0:
                verified = self.head()
                if {path:self.at(verified,path) for path in wanted} != wanted:
                    raise DeliveryError("로테이션 상태 원격 저장 재확인 실패")
                self.expected = wanted
                return
            time.sleep(attempt+1)
        head = self.head()
        if {path:self.at(head,path) for path in wanted} == wanted:
            self.expected = wanted
            return
        raise DeliveryError("로테이션 상태 원격 저장 재시도 소진")


def validate_book(book):
    if not book:
        return {"schema": 1, "events": {}}
    if book.get("schema") != 1 or not isinstance(book.get("events"), dict):
        raise DeliveryError("발송 원장 형식 오류")
    for key, entry in book["events"].items():
        if not isinstance(entry, dict) or entry.get("status") not in STATES or entry.get("event") != key:
            raise DeliveryError("발송 원장 훼손 — 자동 재발송 금지")
    return copy.deepcopy(book)


def delivery_fields(state, day):
    if state.get("date") != day:
        return {"sent_level": 0, "sent_weakening": False, "last_signal": None}
    value = {k: state.get(k) for k in DELIVERY_FIELDS}
    if type(value["sent_level"]) is not int or value["sent_level"] not in (0,1,2) or type(value["sent_weakening"]) is not bool:
        raise DeliveryError("기존 발송 키 형식 오류")
    return value


def event_key(old, pending):
    day = pending.get("date")
    try:
        if not isinstance(day, str) or dt.date.fromisoformat(day).isoformat() != day:
            raise ValueError()
        if old.get("date") and dt.date.fromisoformat(old["date"]) > dt.date.fromisoformat(day):
            raise ValueError()
    except (ValueError, TypeError):
        raise DeliveryError("관측일 역전 또는 형식 오류") from None
    before, after = delivery_fields(old, day), delivery_fields(pending, day)
    if after == before:
        return None
    level = after["sent_level"]
    sig = after["last_signal"]
    if level > before["sent_level"] and not after["sent_weakening"] and isinstance(sig, dict) and sig.get("level") == level:
        return f"{day}:level:{level}"
    if (level > 0 and level == before["sent_level"] and after["sent_weakening"]
            and not before["sent_weakening"] and sig == before["last_signal"]):
        return f"{day}:weakening:{level}"
    raise DeliveryError("예상하지 못한 발송 키 변경 — 발송 보류")


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def rendered(body):
    p = Visible()
    p.feed(body)
    p.close()
    return "".join(p.parts)


def check_body(body):
    visible = rendered(body)
    if not visible or len(visible.encode("utf-16-le"))//2 > 4000:
        raise DeliveryError("로테이션 본문 길이 초과 또는 공백 — 자동 분할·중복 발송 금지")
    return visible


def route():
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    configured = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token or not configured or not expected:
        raise DeliveryError("기존 Telegram 수신 경로 설정 누락")
    def read(method, payload):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload,
                              timeout=(5,15), allow_redirects=False)
            data = r.json()
            if r.status_code != 200 or data.get("ok") is not True or not isinstance(data.get("result"), dict):
                raise ValueError()
            return data["result"]
        except Exception:
            raise DeliveryError("Telegram "+method+" 읽기 전용 검증 실패") from None
    identity = read("getMe", {})
    if str(identity.get("username") or "").casefold() != expected.casefold():
        raise DeliveryError("기존 Telegram 봇 불일치")
    chat = read("getChat", {"chat_id": configured})
    cid = chat.get("id")
    if type(cid) is not int or not cid:
        raise DeliveryError("Telegram 실제 chat.id 미확인")
    if re.fullmatch(r"-?[0-9]+", configured):
        matched = cid == int(configured)
    else:
        matched = configured.startswith("@") and str(chat.get("username") or "").casefold() == configured[1:].casefold()
    if not matched:
        raise DeliveryError("Telegram 지정 수신처 불일치")
    return token, cid


def response_result(http, data, token, cid, body, started, ended):
    if not isinstance(data, dict):
        return {"status": "uncertain", "reason": "응답 형식 오류"}
    if data.get("ok") is False and data.get("error_code") in (400,401,403,429) and data["error_code"] == http:
        return {"status": "rejected", "reason": f"Telegram 명시적 거절 HTTP {http}"}
    message = data.get("result")
    if http != 200 or data.get("ok") is not True or not isinstance(message, dict):
        return {"status": "uncertain", "reason": "Telegram 성공 응답 미확인"}
    chat = message.get("chat") or {}
    mid, stamp = message.get("message_id"), message.get("date")
    if (not isinstance(chat, dict) or type(chat.get("id")) is not int or chat.get("id") != cid
            or type(mid) is not int or mid <= 0 or type(stamp) is not int
            or not started-120 <= stamp <= ended+120
            or message.get("text") != rendered(body)
            or message.get("message_thread_id") not in (None, 1)):
        return {"status": "uncertain", "reason": "Telegram 목적지·메시지·시각·본문·주제 응답 불일치"}
    proof = hmac.new(token.encode(), f"{cid}:{mid}:{stamp}:{digest(body)}".encode(), hashlib.sha256).hexdigest()
    return {"status": "confirmed", "receipt_proof": proof,
            "chat_match": True, "message_id_valid": True, "text_match": True,
            "telegram_date_utc": dt.datetime.fromtimestamp(stamp, dt.timezone.utc).isoformat()}


def transmit(route_value, body):
    token, cid = route_value
    started = time.time()
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": cid, "text": body, "parse_mode": "HTML",
                                "disable_web_page_preview": True},
                          timeout=(5,30), allow_redirects=False)
        try:
            data = r.json()
        except ValueError:
            return {"status": "uncertain", "reason": "Telegram 응답 해석 실패"}
        return response_result(r.status_code, data, token, cid, body, started, time.time())
    except Exception as exc:
        return {"status": "uncertain", "reason": "Telegram 응답 불명확: "+type(exc).__name__}


def process(old, pending, book, body, save, verify=route, send=transmit):
    book = validate_book(book)
    key = event_key(old, pending)
    if key is None:
        if body:
            raise DeliveryError("발송 키 없는 본문 — 오발송 방지")
        save(pending, book)
        return "no_new_signal"
    if not body:
        raise DeliveryError("발송 키만 존재하고 본문 누락")
    check_body(body)
    observed = copy.deepcopy(pending)
    observed.update(delivery_fields(old, pending["date"]))
    previous = book["events"].get(key) or {}
    if previous.get("status") in ("in_flight", "uncertain", "confirmed"):
        observed["delivery_status"] = {"event": key, "status": "unconfirmed_hold" if previous["status"] != "confirmed" else "inconsistent_hold"}
        save(observed, book)
        return "held_no_resend"
    try:
        dest = verify()
    except DeliveryError:
        observed["delivery_status"] = {"event": key, "status": "not_sent_route_unavailable"}
        save(observed, book)
        raise
    record = {"event": key, "status": "in_flight", "attempt": int(previous.get("attempt") or 0)+1,
              "body_sha256": digest(body), "observed_at": pending.get("latest", {}).get("checked_at"),
              "run_id": os.getenv("GITHUB_RUN_ID", "offline"),
              "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    book["events"][key] = record
    observed["delivery_status"] = {"event": key, "status": "in_flight"}
    save(observed, book)  # remotely verified before POST
    result = send(dest, body)
    status = result.get("status")
    if status not in ("confirmed","uncertain","rejected"):
        result = {"status": "uncertain", "reason": "전송 결과 상태 오류"}
        status = "uncertain"
    if status == "confirmed" and not (result.get("chat_match") is True
            and result.get("message_id_valid") is True and result.get("text_match") is True
            and re.fullmatch(r"[0-9a-f]{64}", str(result.get("receipt_proof") or ""))):
        result = {"status": "uncertain", "reason": "검증된 전송 증거 누락"}
        status = "uncertain"
    book["events"][key] = {**record, **result}
    final = copy.deepcopy(pending) if status == "confirmed" else observed
    final["delivery_status"] = {"event": key, "status": status}
    if status == "confirmed":
        print("fx_rotation_telegram_response_verified=true event="+key+" chat_id_match=true message_id_valid=true", flush=True)
    save(final, book)  # atomic receipt and state, or retain in-flight marker
    return status


def run():
    raw = {path: read_local(ROOT,path) for path in (STATE, LEDGER)}
    pending_raw, body_raw = read_local(ROOT,PENDING), read_local(ROOT,ALERT)
    if pending_raw is None:
        if body_raw:
            raise DeliveryError("대기 상태 없이 알림 본문 발견")
        print("fx_rotation_delivery=normal_skip_no_pending")
        return 0
    if raw[STATE] is None:
        raise DeliveryError("기존 운영 상태 파일 누락 — 초기화 금지")
    old = load_object(raw[STATE], "기존 상태")
    pending = load_object(pending_raw, "대기 상태")
    book = load_object(raw[LEDGER], "발송 원장")
    body = body_raw.decode().strip() if body_raw else ""
    pub = Publisher(ROOT, raw)
    status = process(old, pending, book, body, pub.save)
    print("fx_rotation_delivery="+status+"; remote_state_verified=true", flush=True)
    return 0 if status in ("no_new_signal","confirmed") else 2


class Tests(unittest.TestCase):
    def setUp(self):
        self.day = "2026-11-27"
        self.old = {"date":self.day,"sent_level":0,"sent_weakening":False,"last_signal":None}
        self.new = {**self.old,"sent_level":1,"last_signal":{"level":1},"latest":{"checked_at":"2026-11-27T12:00:00+09:00"}}
        self.body = "<b>테스트</b> &amp; 확인"
        self.calls = []
        self.saved = []
        self.receipt = {"status":"confirmed","chat_match":True,"message_id_valid":True,
                        "text_match":True,"receipt_proof":"a"*64}
    def save(self, state, book):
        self.saved.append((copy.deepcopy(state),copy.deepcopy(book)))
    def verify(self):
        return ("offline", 42)
    def send(self, dest, body):
        self.calls.append(body)
        self.assertEqual(self.saved[-1][0]["sent_level"],0)
        self.assertEqual(next(iter(self.saved[-1][1]["events"].values()))["status"],"in_flight")
        return self.receipt
    def test_confirmed_atomic(self):
        self.assertEqual(process(self.old,self.new,{},self.body,self.save,self.verify,self.send),"confirmed")
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.saved[-1][0]["sent_level"],1)
        self.assertEqual(next(iter(self.saved[-1][1]["events"].values()))["status"],"confirmed")
    def test_uncertain_blocks_retry(self):
        def unknown(*_):
            self.calls.append("one")
            return {"status":"uncertain"}
        self.assertEqual(process(self.old,self.new,{},self.body,self.save,self.verify,unknown),"uncertain")
        old,book=self.saved[-1]
        self.assertEqual(process(old,self.new,book,self.body,self.save,self.verify,unknown),"held_no_resend")
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.saved[-1][0]["sent_level"],0)
    def test_crash_after_post(self):
        def fail_final(state,book):
            if self.saved:
                raise DeliveryError("simulated commit failure")
            self.save(state,book)
        with self.assertRaises(DeliveryError):
            process(self.old,self.new,{},self.body,fail_final,self.verify,self.send)
        old,book=self.saved[-1]
        self.assertEqual(process(old,self.new,book,self.body,self.save,self.verify,self.send),"held_no_resend")
        self.assertEqual(len(self.calls),1)
    def test_explicit_reject_retry(self):
        def reject(*_): return {"status":"rejected"}
        self.assertEqual(process(self.old,self.new,{},self.body,self.save,self.verify,reject),"rejected")
        old,book=self.saved[-1]
        self.assertEqual(process(old,self.new,book,self.body,self.save,self.verify,self.send),"confirmed")
    def test_no_signal(self):
        self.assertEqual(process(self.old,self.old,{},"",self.save,self.verify,self.send),"no_new_signal")
        self.assertFalse(self.calls)
    def test_keys_and_regression(self):
        self.assertEqual(event_key(self.old,self.new),self.day+":level:1")
        self.assertEqual(event_key(self.new,{**self.new,"sent_weakening":True}),self.day+":weakening:1")
        self.assertEqual(event_key(self.new,{**self.new,"sent_level":2,"last_signal":{"level":2}}),self.day+":level:2")
        with self.assertRaises(DeliveryError): event_key(self.new,self.old)
        with self.assertRaises(DeliveryError): process(self.old,self.old,{},self.body,self.save,self.verify,self.send)
    def test_route_and_body_verification(self):
        t=int(time.time())
        message={"chat":{"id":42},"message_id":123,"date":t,"text":"테스트 & 확인"}
        good={"ok":True,"result":message}
        self.assertEqual(response_result(200,good,"offline",42,self.body,t,t)["status"],"confirmed")
        for bad in (dict(message,chat={"id":43}),dict(message,message_id=0),
                    dict(message,text="다름"),dict(message,message_thread_id=8),dict(message,date=t-999)):
            self.assertEqual(response_result(200,{"ok":True,"result":bad},"offline",42,self.body,t,t)["status"],"uncertain")
        self.assertEqual(response_result(429,{"ok":False,"error_code":429},"offline",42,self.body,t,t)["status"],"rejected")
        self.assertEqual(response_result(500,{},"offline",42,self.body,t,t)["status"],"uncertain")
        with self.assertRaises(DeliveryError): check_body("x"*4001)
    def test_missing_receipt_never_promotes(self):
        self.receipt={"status":"confirmed"}
        self.assertEqual(process(self.old,self.new,{},self.body,self.save,self.verify,self.send),"uncertain")
        self.assertEqual(self.saved[-1][0]["sent_level"],0)
    def test_no_send_if_marker_not_persisted(self):
        def fail(*_): raise DeliveryError("simulated push failure")
        with self.assertRaises(DeliveryError):
            process(self.old,self.new,{},self.body,fail,self.verify,self.send)
        self.assertFalse(self.calls)
    def test_git_isolated_publish_and_stale_state(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); remote=root/"remote"; local=root/"local"
            def g(cwd,*args):
                subprocess.run(["git",*args],cwd=cwd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            g(root,"init","--bare","--initial-branch=main",str(remote))
            g(root,"clone",str(remote),str(local))
            g(local,"config","user.name","offline");g(local,"config","user.email","offline@example.invalid")
            (local/"data").mkdir(); (local/STATE).write_bytes(encoded(self.old))
            (local/"other.txt").write_text("keep",encoding="utf-8")
            g(local,"add",".");g(local,"commit","-m","fixture");g(local,"push","origin","HEAD:main")
            raw={STATE:encoded(self.old),LEDGER:None}
            pub=Publisher(local,raw)
            pub.save(self.new,{"schema":1,"events":{}})
            remote_head=pub.head()
            self.assertEqual(pub.at(remote_head,STATE),encoded(self.new))
            self.assertEqual(pub.at(remote_head,"other.txt"),b"keep")
            stale=Publisher(local,raw)
            with self.assertRaises(DeliveryError):
                stale.save(self.old,{"schema":1,"events":{}})
            self.assertEqual(pub.at(pub.head(),STATE),encoded(self.new))


def main():
    try:
        if "--self-test" in sys.argv:
            suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
            result=unittest.TextTestRunner(verbosity=2).run(suite)
            print(f"fx_rotation_delivery_regressions={result.testsRun} success={result.wasSuccessful()}; no Telegram or operational state writes")
            return 0 if result.wasSuccessful() else 2
        if "--verify-route" in sys.argv:
            route()
            print("fx_rotation_route_readonly=ok bot_match=true chat_id_match=true no_message_sent")
            return 0
        return run()
    except DeliveryError as exc:
        print("fx_rotation_delivery=unavailable reason="+str(exc),flush=True)
        return 2
    except Exception as exc:
        print("fx_rotation_delivery=unavailable reason="+type(exc).__name__,flush=True)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

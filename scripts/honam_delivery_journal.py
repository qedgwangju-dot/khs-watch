#!/usr/bin/env python3
"""Honam-only durable Telegram receipt journal. No blind retry on ambiguity."""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "data/honam_semiconductor_delivery_journal.json"
STATE = ROOT / "data/honam_semiconductor_watch_state.json"
OUT = ROOT / "out"


def read_record():
    if not JOURNAL.exists():
        return None
    obj = json.loads(JOURNAL.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("Malformed Honam delivery journal; hold")
    return obj


def decision(record):
    if record is None:
        return "clear"
    ids, total = record.get("message_ids"), record.get("total_parts")
    if record.get("status") == "confirmed" and type(total) is int and total > 0 and isinstance(ids, list) and len(ids) == total and all(type(x) is int for x in ids) and len(set(ids)) == total and isinstance(record.get("pending_state"), dict):
        return "recover_confirmed"
    return "hold_uncertain"


def recipient_matches(chat, configured):
    return (str(chat.get("username") or "").casefold() == configured[1:].casefold()
            if configured.startswith("@") else configured.lstrip("-").isdigit() and str(chat.get("id")) == configured)


def verified_receipt(payload, configured):
    result = payload.get("result") or {}
    chat = result.get("chat") or {}
    if not payload.get("ok") or type(result.get("message_id")) is not int or type(chat.get("id")) is not int or not recipient_matches(chat, configured):
        raise RuntimeError("Telegram receipt missing or recipient mismatch")
    return result["message_id"], chat["id"]


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check)


def publish(mutator, message):
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for _ in range(3):
        git("fetch", "--no-tags", "--depth=1", "origin", "main")
        git("reset", "--hard", "FETCH_HEAD")
        if not mutator():
            return
        git("add", "-A", "--", str(STATE.relative_to(ROOT)), str(JOURNAL.relative_to(ROOT)))
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        git("commit", "-m", message)
        if git("push", "origin", "HEAD:main", check=False).returncode == 0:
            return
    raise RuntimeError("Honam journal/state persistence failed; no automatic resend")


def replace_record(new, old):
    def mutate():
        current = read_record()
        if current == new:
            return False
        if current != old:
            raise RuntimeError("Honam journal conflict; hold")
        JOURNAL.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
    publish(mutate, "Record Honam Telegram delivery journal")


def finalize():
    def mutate():
        record = read_record()
        if record is None:
            return False
        if decision(record) != "recover_confirmed":
            raise RuntimeError("Honam send outcome unresolved; do not advance state")
        with tempfile.TemporaryDirectory() as temp:
            pending = pathlib.Path(temp) / "pending.json"
            pending.write_text(json.dumps(record["pending_state"], ensure_ascii=False), encoding="utf-8")
            subprocess.run(["python", str(ROOT / "scripts/merge_honam_state.py"), str(STATE), str(pending), str(STATE)], check=True, cwd=ROOT)
        JOURNAL.unlink()
        return True
    publish(mutate, "Finalize confirmed Honam Telegram delivery and state")
    print("honam_delivery_finalized=true")


def preflight():
    status = decision(read_record())
    if status == "hold_uncertain":
        raise RuntimeError("Honam previous delivery uncertain; reconcile before any resend")
    if status == "recover_confirmed":
        finalize()
        print("honam_confirmed_receipt_recovered_without_resend=true")
    else:
        print("honam_delivery_journal_clear=true")


def api(token, method, fields):
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=urllib.parse.urlencode(fields).encode("utf-8"), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Telegram {method} result unavailable ({type(exc).__name__})") from None


def deliver():
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"].strip(), os.environ["TELEGRAM_CHAT_ID"].strip()
    chunks = json.loads((OUT / "honam_semiconductor_telegram_chunks.json").read_text(encoding="utf-8"))
    pending = json.loads((OUT / "honam_semiconductor_pending_state.json").read_text(encoding="utf-8"))
    alert = json.loads((OUT / "honam_semiconductor_alert.json").read_text(encoding="utf-8"))
    if not chunks or any(not isinstance(x, str) or not x.strip() or len(x) > 3900 for x in chunks):
        raise RuntimeError("Invalid Honam message chunks; nothing sent")
    if read_record() is not None:
        raise RuntimeError("Honam delivery journal occupied")
    destination = api(token, "getChat", {"chat_id": chat})
    if not destination.get("ok") or not recipient_matches(destination.get("result") or {}, chat):
        raise RuntimeError("Honam destination verification failed; nothing sent")
    events = alert.get("new_items", []) + alert.get("official_changes", [])
    keys = sorted(str(event["event_key"]) for event in events if event.get("event_key"))
    if not keys or len(keys) != len(events):
        raise RuntimeError("Incomplete Honam event keys; nothing sent")
    batch = hashlib.sha256(json.dumps({"keys": keys, "chunks": chunks}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    record = {"schema_version": 1, "batch_id": batch, "status": "sending", "total_parts": len(chunks),
              "message_ids": [], "event_keys": keys, "pending_state": pending}
    replace_record(record, None)
    chats = set()
    for chunk in chunks:
        try:
            mid, actual = verified_receipt(api(token, "sendMessage", {"chat_id":chat,"text":chunk,"parse_mode":"HTML","disable_web_page_preview":"true"}), chat)
        except Exception:
            replace_record(dict(record, status="uncertain"), record)
            raise RuntimeError("Honam send outcome unresolved; journal preserved; no automatic resend") from None
        chats.add(actual)
        ids = record["message_ids"] + [mid]
        next_record = dict(record, message_ids=ids, status="confirmed" if len(ids) == len(chunks) else "sending")
        replace_record(next_record, record)
        record = next_record
    (OUT / "honam_semiconductor_telegram_confirmed.json").write_text(json.dumps({"status":"confirmed","message_ids":record["message_ids"],"chat_ids":sorted(chats),"batch_id":batch,"confirmed_at_kst":dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"telegram_delivery_confirmed=true message_ids={record['message_ids']} recipient_match=true")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "deliver", "finalize"))
    {"preflight":preflight, "deliver":deliver, "finalize":finalize}[parser.parse_args().command]()

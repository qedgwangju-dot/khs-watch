#!/usr/bin/env python3
"""Correct just the confirmed duplicate fifth article in ROBOTIS message 404.

No new Telegram messages. Only edits the one message whose run/artifact,
receipt, recipient, original text and new text match pinned evidence.
An unacknowledged edit remains in-flight and is never replayed automatically.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import io
import json
import os
import re
import sys
import zipfile

import robot_watch_delivery as d
import robot_watch_message_corrections as c

RUN_ID=45103989370
ARTIFACT_ID=14787125421
ARTIFACT_SHA="sha256:26c0dc391f643c5d748ef15c607a17b7a6fbf61cf74393ce86cbceddcdef2cbe"
MESSAGE_ID=404
ORIGINAL_SHA="8cc07a14fd3fe269cea67c330f22dd732d4cdd53ff8afa76de9f1c3fcd18151c"
ORIGINAL_PENDING_SHA="11404db2f0fda27fc63c6bafb17f2acfe9e52d746e1d94549ec7ec1996763dbc"
ORIGINAL_RECEIPTS_SHA="d1f824ee705fdc19978d73abe92f7787b1e88ccf6d75ad4de7f9ee2010ac89f2"
CORRECTED_SHA="69020e06483d335f78d6a2b8bd39a48ed3abbc7a23415283f2f736fb1cfb825b"
DUPLICATE_KEY="44e38c418d8b62458b41aa67ae9be72a3fc361ba0f1d5fc57866229df34dd4cb"
EXISTING_KEY="44e38c418d8b624501e53e833075280cbb24234df30454c4e1425da953799ffb"
BATCH="robot-message404-reprint-correction-20261123-v1"
ALLOWED={p.name for p in (
    d.ALERT_PATH,d.PENDING_PATH,d.RECEIPTS_PATH,d.ATTEMPTS_PATH,
)}
ALLOWED.update({"robotis_physical_ai_watch_status.md","robotis_physical_ai_watch_candidates.json",
                "robot_watch_message_correction_receipts.json"})

def parse_artifact(raw,metadata):
    if metadata.get("name")!=f"robotis-physical-ai-{RUN_ID}" or metadata.get("expired"):
        raise d.DeliveryError("Original artifact identity or retention is invalid")
    if metadata.get("digest") != ARTIFACT_SHA or hashlib.sha256(raw).hexdigest()!=""+ARTIFACT_SHA[7:]:
        raise d.DeliveryError("Original delivery artifact digest differs")
    files={}
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        if len(zipped.infolist())>len(ALLOWED):
            raise d.DeliveryError("Original delivery archive has extra files")
        total=0
        for info in zipped.infolist():
            if info.filename not in ALLOWED or info.filename in files or info.file_size>3_000_000:
                raise d.DeliveryError("Original artifact file validation failed")
            total+=info.file_size
            if total>5_000_000:raise d.DeliveryError("Oversized original artifact")
            files[info.filename]=zipped.read(info).decode("utf-8")
    return files

def corrected_text(original):
    matches=list(re.finditer(r"(?m)^<b>(\d+)\.\s",original))
    if [int(m.group(1)) for m in matches] != [1,2,3,4,5]:
        raise d.DeliveryError("Original five article boundaries are not intact")
    footer=original.find("<b>판정 기준</b>",matches[4].start())
    if footer<0 or original.count("<b>신규 고신호 5건</b>")!=1:
        raise d.DeliveryError("Pinned alert header/footer missing")
    new=(original[:matches[4].start()].rstrip()+"\n"+
         original[footer:]).replace("<b>신규 고신호 5건</b>","<b>신규 고신호 4건</b>",1)
    if d._digest(new)!=CORRECTED_SHA:
        raise d.DeliveryError("Correction text differs from reviewed replacement")
    return new

def checked_original(api,chat):
    run=api.json(f"/repos/{api.repository}/actions/runs/{RUN_ID}")
    if (run.get("id")!=RUN_ID or run.get("status")!="completed" or run.get("conclusion")!="success"
        or run.get("head_branch")!="main"
        or str(run.get("path") or "").split("@")[0]!=".github/workflows/"+d.WORKFLOW):
        raise d.DeliveryError("Original ROBOTIS run is not the recorded successful run")
    metadata=api.json(f"/repos/{api.repository}/actions/artifacts/{ARTIFACT_ID}")
    if metadata.get("id")!=ARTIFACT_ID or (metadata.get("workflow_run") or {}).get("id")!=RUN_ID:
        raise d.DeliveryError("Original artifact run identity differs")
    files=parse_artifact(api.download(ARTIFACT_ID),metadata)
    try:
        original=files[d.ALERT_PATH.name]
        pending=json.loads(files[d.PENDING_PATH.name])
        receipts=json.loads(files[d.RECEIPTS_PATH.name])
    except (KeyError,TypeError,ValueError):
        raise d.DeliveryError("Original alert, selection or delivery receipts missing") from None
    if (d._digest(original.strip())!=ORIGINAL_SHA or d._pending_digest(pending)!=ORIGINAL_PENDING_SHA
        or c.object_sha(receipts)!=ORIGINAL_RECEIPTS_SHA):
        raise d.DeliveryError("Original alert or delivery mapping differs from pinned evidence")
    route=d.route_fingerprint(chat)
    keys=d.check_receipts(original,pending,receipts,route)
    if (len(receipts)!=1 or receipts[0].get("message_id")!=MESSAGE_ID
        or receipts[0].get("run_id")!=RUN_ID or receipts[0].get("chat_verification")!="numeric_id_equal"
        or receipts[0].get("message_thread_id") is not None
        or keys!=set(pending["last_selected"]) or len(keys)!=5
        or pending["last_selected"][-1]!=DUPLICATE_KEY):
        raise d.DeliveryError("Message 404 proof or last duplicate event differs")
    new=corrected_text(original)
    corrected_pending=dict(pending,
                           last_selected=pending["last_selected"][:-1],
                           last_selected_events=pending["last_selected_events"][:-1])
    chunks=d.build_chunks(new,corrected_pending)
    if (len(chunks)!=1 or len(chunks[0]["event_keys"])!=4 or
        set(chunks[0]["event_keys"])!=keys-{DUPLICATE_KEY} or
        chunks[0]["sha256"]!=CORRECTED_SHA):
        raise d.DeliveryError("Corrected message did not retain exactly four original events")
    return new,route,keys

def _persist(api,route,status,**facts):
    for i in range(5):
        state,sha=d._load_remote_state(api)
        record=(state.get("message_corrections") or {}).get(BATCH)
        if record and (record.get("original_sha")!=ORIGINAL_SHA
                       or record.get("corrected_sha")!=CORRECTED_SHA
                       or record.get("message_id")!=MESSAGE_ID
                       or record.get("route_fingerprint")!=route):
            raise d.DeliveryError("Existing correction evidence disagrees")
        if status=="in_flight" and record:
            raise d.DeliveryError("Prior correction attempt unresolved; manual verification is required")
        if status=="confirmed" and (not record or record.get("status")!="in_flight"):
            raise d.DeliveryError("Correction confirmation lacks a durable pre-send intent")
        new=dict(state)
        corrections=dict(state.get("message_corrections") or {})
        corrections[BATCH]={
            "status":status,"original_sha":ORIGINAL_SHA,"corrected_sha":CORRECTED_SHA,
            "message_id":MESSAGE_ID,"route_fingerprint":route,
            **({"intent_at_utc":d._now()} if status=="in_flight" else {"intent_at_utc":record["intent_at_utc"]}),
            **facts,
        }
        new["message_corrections"]=corrections
        payload=base64.b64encode((json.dumps(new,ensure_ascii=False,indent=2)+"\n").encode()).decode()
        try:
            api.json(f"/repos/{api.repository}/contents/{d.STATE_PATH.as_posix()}","PUT",{
                "message":"Record one verified ROBOTIS message edit [skip ci]",
                "content":payload,"sha":sha,"branch":"main"})
            return new
        except d.APIError as exc:
            if exc.status not in (409,422):raise
    raise d.DeliveryError("State CAS not persisted after five attempts")

def main():
    if os.getenv("GITHUB_RUN_ATTEMPT","1")!="1":
        raise d.DeliveryError("Workflow rerun requires prior delivery review")
    api=d.GitHubAPI(os.environ.get("GITHUB_REPOSITORY",""),os.environ.get("GH_TOKEN",""))
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    route=d.route_fingerprint(chat)
    state,_=d._load_remote_state(api)
    prior=(state.get("message_corrections") or {}).get(BATCH)
    if prior:
        if (prior.get("status")=="confirmed" and prior.get("original_sha")==ORIGINAL_SHA
            and prior.get("corrected_sha")==CORRECTED_SHA
            and prior.get("route_fingerprint")==route and prior.get("message_id")==MESSAGE_ID):
            print("ROBOTIS message404 correction already confirmed; Telegram API not called")
            return
        raise d.DeliveryError("Prior message404 correction unverified; stop without replay")
    new,route,keys=checked_original(api,chat)
    original_history=[x for x in state.get("delivery_history",[])
                      if isinstance(x,dict) and x.get("run_id")==RUN_ID]
    if (len(original_history)!=1 or original_history[0].get("outcome")!="sent"
        or original_history[0].get("message_ids")!=[MESSAGE_ID]
        or original_history[0].get("recipient_verified") is not True
        or set(original_history[0].get("confirmed_event_keys") or [])!=keys
        or not keys<=set(state.get("seen") or []) or EXISTING_KEY not in state.get("seen",[])):
        raise d.DeliveryError("Current history, seen state or original Nov20 canonical contract key differs")
    account=d._telegram(token,"getMe")
    if (not account.get("ok") or (account.get("result") or {}).get("username","").casefold()
            !=d.EXPECTED_BOT.casefold()):
        raise d.DeliveryError("Telegram bot identity differs; no edit attempted")
    _persist(api,route,"in_flight",run_id=RUN_ID)
    try:
        response=d._telegram(token,"editMessageText",{
            "chat_id":chat,"message_id":MESSAGE_ID,"text":new,"parse_mode":"HTML",
            "disable_web_page_preview":"true"})
        reply=response.get("result") or {}
        if (not response.get("ok") or type(reply.get("message_id")) is not int
            or reply["message_id"]!=MESSAGE_ID
            or d._recipient(reply,chat)!="numeric_id_equal"
            or reply.get("text")!=c.plain_text(new)
            or reply.get("message_thread_id") is not None):
            raise d.DeliveryError("Telegram edit response identity/recipient/body differs")
    except Exception:
        # This intent remains ambiguous; never retry or guess.
        raise d.DeliveryError("Telegram edit unconfirmed; in-flight marker preserved; no auto replay") from None
    _persist(api,route,"confirmed",run_id=RUN_ID,confirmed_at_utc=d._now(),
             response_plain_sha=d._digest(c.plain_text(new)),removed_duplicate_key=DUPLICATE_KEY)
    print("ROBOTIS message404 duplicate removed: exact original message ID, recipient and corrected body confirmed")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("ROBOTIS message404 correction stopped: "+(str(exc) if isinstance(exc,d.DeliveryError) else type(exc).__name__),file=sys.stderr)
        raise SystemExit(1) from None

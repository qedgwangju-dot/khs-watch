"""Regression for first-run baseline and high-signal alert overflow dedup."""
from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

def run():
    import physical_ai_watch_airan_guard as watcher
    base=watcher.base
    keys=(
        "STATE_PATH","PENDING_PATH","OUT_DIR","ALERT_PATH","STATUS_PATH",
        "QUERIES","FORCE","MAX_ALERTS","NOW",
        "query_news","topic_group","key","score","select_diverse",
        "category","tag_for","verification","meaning","risk"
    )
    saved={k:getattr(base,k) for k in keys}
    try:
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            base.STATE_PATH=root/"state.json"
            base.PENDING_PATH=root/"pending.json"
            base.OUT_DIR=root
            base.ALERT_PATH=root/"message.txt"
            base.STATUS_PATH=root/"status.md"
            base.QUERIES=["offline_fixture"]
            base.FORCE=False
            base.MAX_ALERTS=2
            base.NOW=dt.datetime(2026,11,14,14,0,tzinfo=dt.timezone.utc)
            fixtures=[{
                "title":f"Robotis approved milestone {i}",
                "description":"Confirmed physical-AI deployment contract",
                "source":"ROBOTIS",
                "link":"https://example.com/milestone",
                "published":"2026-11-14T13:50:00+00:00",
            } for i in range(1,4)]
            base.query_news=lambda _: [dict(x) for x in fixtures]
            base.topic_group=lambda _: "robotis"
            base.key=lambda x: "fixture-"+x["title"].split()[-1]
            base.score=lambda _: 21
            base.select_diverse=lambda rows,seen,force,limit: [x for x in rows if x["key"] not in seen][:limit]
            base.category=lambda text,group: "확인된 사건"
            base.tag_for=lambda _: "로보티즈"
            base.verification=lambda row,g,text: "오프라인 검증용"
            base.meaning=lambda cat: "실제 사건 확인"
            base.risk=lambda cat: "추가 고객 확인"
            base.STATE_PATH.write_text(json.dumps({"seeded":True,"seen":["existing-delivered"]}),encoding="utf-8")
            base.main()
            pending=json.loads(base.PENDING_PATH.read_text(encoding="utf-8"))
            assert {"existing-delivered","fixture-1","fixture-2"}.issubset(set(pending["seen"])),pending["seen"]
            assert {"fixture-1","fixture-2"}.issubset(set(pending["last_selected"])),pending["last_selected"]
            assert "fixture-3" not in pending["seen"],"Overflow must remain eligible for next run"
            # First execution must preserve the historic no-alert seed behavior.
            base.STATE_PATH.write_text(json.dumps({"seeded":False,"seen":[]}),encoding="utf-8")
            base.main()
            seed=json.loads(base.PENDING_PATH.read_text(encoding="utf-8"))
            assert seed["last_selected"]==[]
            assert {"fixture-1","fixture-2","fixture-3"}.issubset(set(seed["seen"])),seed["seen"]
            assert not base.ALERT_PATH.read_text(encoding="utf-8").strip()
    finally:
        for k,value in saved.items():
            setattr(base,k,value)
    print("ROBOTIS selection-only dedup and first-seed regression: PASS")

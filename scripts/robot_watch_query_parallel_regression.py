"""Offline guard for bounded concurrent source fetching and ordered dedup."""
from __future__ import annotations
import datetime as dt
import json
import tempfile
import threading
import time
from pathlib import Path
import physical_ai_watch_airan_guard as watcher

def run():
    base=watcher.base
    keys=("STATE_PATH","PENDING_PATH","OUT_DIR","ALERT_PATH","STATUS_PATH",
          "QUERIES","FORCE","MAX_ALERTS","NOW","query_news","topic_group",
          "key","score","select_diverse","category","tag_for",
          "verification","meaning","risk")
    saved={k:getattr(base,k) for k in keys}
    try:
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            base.STATE_PATH=root/"state.json"
            base.PENDING_PATH=root/"pending.json"
            base.OUT_DIR=root
            base.ALERT_PATH=root/"telegram.txt"
            base.STATUS_PATH=root/"status.md"
            base.QUERIES=["offline_first","offline_second","offline_third"]
            base.FORCE=False
            base.MAX_ALERTS=2
            base.NOW=dt.datetime(2026,11,16,0,0,tzinfo=dt.timezone.utc)
            base.STATE_PATH.write_text(json.dumps({"seeded":True,"seen":[]}),encoding="utf-8")
            sync=threading.Lock()
            running=[0]
            peak=[0]
            def slow_query(q):
                with sync:
                    running[0]+=1
                    peak[0]=max(peak[0],running[0])
                time.sleep(0.10)
                with sync:
                    running[0]-=1
                return [{"title":q,"description":"actual new verified deployment",
                         "source":"ROBOTIS","link":"https://example.org/robot",
                         "published":"2026-11-15T23:30:00+00:00"}]
            base.query_news=slow_query
            base.topic_group=lambda _: "robotis"
            base.key=lambda item:item["title"]
            base.score=lambda _:30
            base.select_diverse=lambda rows,seen,force,limit:[x for x in rows if force or x["key"] not in seen][:limit]
            base.category=lambda text,group:"확인된 사건"
            base.tag_for=lambda _: "로보티즈"
            base.verification=lambda item,group,text:"테스트"
            base.meaning=lambda cat:"테스트"
            base.risk=lambda cat:"테스트"
            base.main()
            pending=json.loads(base.PENDING_PATH.read_text(encoding="utf-8"))
            assert peak[0]>=2, "RSS discovery must overlap independent reads"
            assert pending["last_selected"]==["offline_first","offline_second"],pending["last_selected"]
            assert set(pending["seen"])=={"offline_first","offline_second"},pending["seen"]
            assert "offline_third" not in pending["seen"],"Overflow must remain eligible"
            assert base.ALERT_PATH.read_text(encoding="utf-8").count("offline_")==2
    finally:
        for key,value in saved.items():
            setattr(base,key,value)

print("Bounded parallel source fetch / deterministic selection regression: import ready")

if __name__ == "__main__":
    run()

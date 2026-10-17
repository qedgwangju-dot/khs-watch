#!/usr/bin/env python3
"""Validate and clean space launch alert contents before Telegram sending."""
from __future__ import annotations
import pathlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from space_launch_event_guard import eligible, correction_notices

CRITICAL=re.compile(r"neutron|morgan stanley|pivotal research|citizens",re.I)
BROKER=re.compile(r"price target|목표주가|analyst|citizens|morgan stanley|pivotal research",re.I)
DELAY=re.compile(r"delay|postpone|2027|연기|지연",re.I)
ARTICLE_DATE=re.compile(r"\b(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*KST\b")

def clean_blocks(text,now):
    blocks=text.strip().split("\n\n")
    if not blocks:return ""
    output=[blocks[0]]
    for block in blocks[1:]:
        first=block.splitlines()[0].strip().lower()
        title=next((x for x in block.splitlines() if x.startswith("• ")),first)
        lowered=block.lower()
        if first.startswith("[계약]") and BROKER.search(title):
            continue
        if first.startswith("[계약]") and "neutron" in lowered and DELAY.search(title):
            continue
        if first.startswith("[증권사]") and BROKER.search(title):
            continue
        # Old RSS headlines are not new events; standalone government notices
        # are kept regardless of age.
        if not any(x in first for x in ("[발사허가","[국내","[우주투자")):
            m=ARTICLE_DATE.search(block)
            if m:
                published=datetime.strptime(m[1]+" "+m[2],"%Y-%m-%d %H:%M")
                published=published.replace(tzinfo=timezone(timedelta(hours=9)))
                if now-published.astimezone(timezone.utc)>timedelta(hours=48):
                    continue
        kept=[x for x in block.splitlines()
              if "제목·공개요약에서 핵심 수치 미추출" not in x]
        if kept:output.append("\n".join(kept))
    return "\n\n".join(output).rstrip()+"\n" if len(output)>1 else ""

def process(alert_path,pending_path,now,fetch,rate):
    raw=alert_path.read_text(encoding='utf-8') if alert_path.exists() else ''
    filtered=clean_blocks(raw,now) if raw else ''
    state=json.loads(pending_path.read_text(encoding='utf-8'))
    if not isinstance(state.get('seen'),dict):raise RuntimeError('State schema invalid')
    notices,errors=correction_notices(state['seen'],fetch,rate)

def main():
    if len(sys.argv)!=2:
        raise SystemExit("Expected alert file path")
    target=pathlib.Path(sys.argv[1])
    original=target.read_text(encoding="utf-8") if target.exists() else ""
    changed=clean_blocks(original,datetime.now(timezone.utc)) if original else ""
    if changed:target.write_text(changed,encoding="utf-8")
    else:target.unlink(missing_ok=True)
    print("space_launch_alert_filter=ok alert="+str(bool(changed)))
if __name__=="__main__":main()

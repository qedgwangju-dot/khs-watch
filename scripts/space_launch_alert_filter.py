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

def self_test():
    now=datetime(2026,10,17,10,tzinfo=timezone.utc)
    doc=("🚀 우주 발사 병목 웹감시\n기준: 2026-10-17 19:00 KST\n\n"
         "[계약] Rocket Lab Electron·Neutron\n"
         "• Rocket Lab Neutron debut delayed to 2027 - Bloomberg\n"
         "• 검증: 복수 신뢰보도 | 2026-10-15 06:10 KST\n\n"
         "[증권사] SpaceX\n"
         "• Morgan Stanley raises SpaceX price target - Investing.com\n"
         "• 검증: 복수 신뢰보도 | 2026-10-14 19:48 KST\n\n"
         "[계약] Electron 공급\n"
         "• Rocket Lab signs Electron satellite launch contract\n"
         "• 검증: 복수 신뢰보도 | 2026-10-17 17:10 KST\n")
    out=clean_blocks(doc,now)
    assert "Neutron debut" not in out
    assert "Morgan Stanley raises" not in out
    assert "signs Electron" in out
    assert "🚀 우주 발사 병목 웹감시" in out
    print("space_launch_filter_self_test=ok misclassified=blocked valid_contract=retained")

def main():
    if len(sys.argv)!=2:
        raise SystemExit("Expected alert file path")
    target=pathlib.Path(sys.argv[1])
    original=target.read_text(encoding="utf-8") if target.exists() else ""
    changed=clean_blocks(original,datetime.now(timezone.utc)) if original else ""
    from space_launch_bottleneck_watch import PENDING_STATE_PATH,request_bytes,fetch_usdkrw,NOW,KST
    pending=json.loads(PENDING_STATE_PATH.read_text(encoding='utf-8'))
    notes,errors=correction_notices(pending['seen'],request_bytes,fetch_usdkrw())
    if notes:
        header="🚀 우주 발사 병목 웹감시\n기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
        changed=(changed.rstrip() if changed else header)+"\n\n"+"\n\n".join(text for _,text in notes)+"\n"
        for key,_ in notes:pending['seen'][key]=NOW.isoformat()
        PENDING_STATE_PATH.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if changed:target.write_text(changed,encoding="utf-8")
    else:target.unlink(missing_ok=True)
    print("space_launch_alert_filter=ok alert="+str(bool(changed)))
if __name__=="__main__":main()


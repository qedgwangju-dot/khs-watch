#!/usr/bin/env python3
"""Cboe SPX+SPXW put/call + VIX joint stress; event-only Telegram alerts.

Do not infer crash risk from put *notional* (methodology unknown), put-volume alone,
or old 2008 recovery graphs. All stored points are fresh, dated, source-checked.
"""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

NY=ZoneInfo("America/New_York")
KST=ZoneInfo("Asia/Seoul")
ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/"data/spx_put_vix_joint_stress_state.json"
OUT=ROOT/"out/spx_put_vix_joint_stress"
REPORT=OUT/"report.html"
PENDING=OUT/"pending_state.json"
RECEIPT=OUT/"telegram_receipt.json"
AUDIT=OUT/"audit.json"
EXPECTED_BOT="khs8879887988798879_bot"
CBOE_URL="https://www.cboe.com/markets/us/options/market-statistics/daily?dt={date}"
VIX_URL="https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
STAGES=("안정","주의","악화","심각")
# Illustrative independent monitoring thresholds, NOT exchange or regulator grades.
# Joint confirmation avoids converting a record notional chart into a crisis claim.
DOWN={1:(1.30,23.0),2:(1.50,28.0),3:(1.80,35.0)}
MIN_HISTORY=3
MAX_CHARS=1500

def parse_cboe_page(content, expected_date):
    from bs4 import BeautifulSoup
    day=dt.date.fromisoformat(str(expected_date))
    soup=BeautifulSoup(content,"html.parser")
    dates=[]
    for node in soup.select("input[value]"):
        try: dates.append(dt.datetime.strptime(node["value"],"%d %B %Y").date())
        except (ValueError,KeyError): pass
    if dates != [day]:
        raise ValueError(f"Cboe 화면 기준일 검증 실패: 기대={day}, 화면={dates}")
    text=re.sub(r"\s+"," ",soup.get_text(" ",strip=True))
    pm=re.search(r"\bSPX\s*\+\s*SPXW PUT/CALL RATIO\s+(\d+(?:\.\d+)?)",text,re.I)
    if not pm: raise ValueError("Cboe SPX+SPXW 풋/콜 비율 누락")
    ratio=float(pm.group(1))
    occurrences=list(re.finditer(r"\bSPX\s*\+\s*SPXW\b",text,re.I))
    if len(occurrences)<2: raise ValueError("Cboe SPX+SPXW 거래량 표 구역 누락")
    section=text[occurrences[-1].end():]
    before_next=re.search(r"\bOEX\b",section)
    if not before_next: raise ValueError("Cboe SPX 거래량 표 종료 표식 누락")
    section=section[:before_next.start()]
    v=re.search(r"\bVOLUME\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",section)
    oi=re.search(r"\bOPEN INTEREST\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",section)
    if not v or not oi: raise ValueError("Cboe SPX 거래량 또는 미결제약정 없음")
    calls,puts,total=(int(x.replace(",","")) for x in v.groups())
    c_oi,p_oi,t_oi=(int(x.replace(",","")) for x in oi.groups())
    if calls<=0 or puts<0 or calls+puts!=total or c_oi+p_oi!=t_oi:
        raise ValueError("Cboe SPX 거래량/미결제약정 내부 합계 오류")
    if not math.isfinite(ratio) or abs(puts/calls-ratio)>.015:
        raise ValueError("Cboe SPX 풋/콜 비율과 계약 건수 불일치")
    return dict(date=day.isoformat(),calls=calls,puts=puts,total=total,
                ratio=round(puts/calls,4),oi_puts=p_oi,oi_calls=c_oi,
                source=CBOE_URL.format(date=day.isoformat()))

def parse_vix_csv(raw):
    rows={}
    txt=raw.decode("utf-8-sig") if isinstance(raw,bytes) else str(raw)
    reader=csv.DictReader(io.StringIO(txt))
    if not reader.fieldnames or "CLOSE" not in [str(x).strip().upper() for x in reader.fieldnames]:
        raise ValueError("Cboe VIX CSV 헤더 불일치")
    for r in reader:
        fields={k.strip().upper():v for k,v in r.items() if isinstance(k,str)}
        try:
            rawdate=fields["DATE"].strip()
            try: d=dt.date.fromisoformat(rawdate)
            except ValueError: d=dt.datetime.strptime(rawdate,"%m/%d/%Y").date()
            val=float(fields["CLOSE"])
            if not math.isfinite(val) or not 0<=val<=150: continue
        except (KeyError,ValueError):
            continue
        if d.isoformat() in rows and rows[d.isoformat()]!=val:
            raise ValueError("Cboe VIX 같은 기준일 숫자 충돌")
        rows[d.isoformat()]=val
    if len(rows)<30: raise ValueError("Cboe VIX CSV 표본 부족")
    return rows

def stage(ratio,vix):
    if ratio>=2.00 and vix>=40: return 3
    if ratio>=1.70 and vix>=30: return 2
    if ratio>=1.40 and vix>=25: return 1
    return 0

def choose_stage(history,old):
    latest=history[-1]
    actual=stage(latest["ratio"],latest["vix"])
    if old is None:
        return (actual if actual>0 else 0,"새 위험 신호" if actual>0 else "기준선만 기록")
    old=int(old)
    if old not in range(4): raise ValueError("기존 상태 위험 단계 손상")
    if actual>old: return actual,"악화"
    if actual==old: return old,"유지"
    if len(history)<3: return old,"회복 검증 부족"
    # Recover only if all three prior *published* US market sessions meet both limits.
    target=old
    for candidate in range(old-1,-1,-1):
        p,v=DOWN[candidate+1]
        if all(x["ratio"]<p and x["vix"]<v for x in history[-3:]):
            target=candidate
    return (target,"정상화 확인") if target<old else (old,"회복 관찰")

def render(latest,history,old,target,event,now,sample=False):
    if not sample and event in ("유지","회복 관찰","기준선만 기록","회복 검증 부족"):
        return ""
    date=latest["date"]
    pv=history[-2]["ratio"] if len(history)>=2 else None
    dd=f"{latest['ratio']-pv:+.2f}" if pv is not None else "자료 부족"
    txt=[]
    if sample: txt.append("<b>[전송 양식 검증: 새 시장 경보 아님]</b>")
    txt.extend([
      f"<b>미국 SPX 풋옵션·변동성 동반위험 | {STAGES[target]}</b>",
      f"<b>방향: {event}</b> | 미국 거래일 {date}",
      f"SPX·SPXW 풋/콜 비율 <b>{latest['ratio']:.2f}</b> (직전 {dd})",
      f"풋 {latest['puts']:,}계약 / 콜 {latest['calls']:,}계약",
      f"풋 미결제약정 {latest['oi_puts']:,}계약",
      f"VIX(30일 예상 변동성) <b>{latest['vix']:.2f}</b>",
      "풋 명목금액 최고치 주장: 산식·공식 원자료 불명, 경보 판단 제외",
      "위험도는 풋/콜·VIX 동시 충족시에만 상승(자체 기준)",
    ])
    if old is not None and target!=old:
        txt.append(f"단계: {STAGES[old]} → {STAGES[target]}")
    if target<3:
        n=target+1
        pc,vv={1:(1.40,25.0),2:(1.70,30.0),3:(2.00,40.0)}[n]
        txt.append(f"다음 악화: 풋/콜 {pc:.2f} 이상 + VIX {vv:.0f} 이상")
    if target>0:
        pc,vv=DOWN[target]
        txt.append(f"하향: 풋/콜 {pc:.2f} 미만 + VIX {vv:.0f} 미만 3영업일")
    txt.extend([
        "풋 매수·신규 공매도 확정 아님; 개시/청산·매도 거래 구분 불가",
        f"Cboe 옵션: {latest['source']}",
        f"Cboe VIX: {VIX_URL}",
        f"조회 {now:%Y-%m-%d %H:%M} 한국시간"
    ])
    message="\n".join(txt)
    if len(message)>MAX_CHARS or re.search(r"<(?!/?b>)[^>]*>",message):
        raise ValueError("메시지 초과/허용되지 않은 태그: 임의 절단 금지")
    return message

def session_dates(now,n):
    # Derived using XNYS trading calendar, not simple weekday (US holidays).
    import exchange_calendars as xcals
    ny=now.astimezone(NY)
    anchor=ny.date() if ny.hour>=20 else ny.date()-dt.timedelta(days=1)
    cal=xcals.get_calendar("XNYS")
    dates=cal.sessions_in_range(str(anchor-dt.timedelta(days=35)),str(anchor))
    vals=[d.date() for d in dates]
    if len(vals)<n: raise RuntimeError("거래 달력 표본 부족")
    return vals[-n:]

def browser_fetch(dates):
    from playwright.sync_api import sync_playwright
    executable=next((p for p in ("/usr/bin/google-chrome","/usr/bin/google-chrome-stable",
                                 "/usr/bin/chromium","/usr/bin/chromium-browser") if os.path.exists(p)),None)
    if not executable: raise RuntimeError("GitHub Runner Chrome/Chromium 없음")
    found={}
    with sync_playwright() as pw:
        b=pw.chromium.launch(executable_path=executable,headless=True,
                           args=["--no-sandbox","--disable-dev-shm-usage"])
        page=b.new_page(locale="en-US")
        for d in dates:
            url=CBOE_URL.format(date=d.isoformat())
            page.goto(url,wait_until="domcontentloaded",timeout=45000)
            try: page.get_by_text("SPX + SPXW PUT/CALL RATIO").first.wait_for(timeout=15000)
            except Exception: pass
            # The visible date in the returned HTML is the decisive freshness gate.
            found[d.isoformat()]=parse_cboe_page(page.content(),d)
        b.close()
    return found

def fetch_vix():
    req=urllib.request.Request(VIX_URL,headers={"User-Agent":"Mozilla/5.0","Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=45) as r:
        raw=r.read()
    return parse_vix_csv(raw)

def changed_metrics(previous, latest):
    # 공식기관이 같은 거래일 통계를 정정하면 조용히 무시하지 않고 업데이트한다.
    if not previous: return False
    keys=("calls","puts","total","ratio","oi_puts","oi_calls","vix")
    return any(previous.get(k)!=latest.get(k) for k in keys)

def load_state():
    if not STATE.exists(): return {"history":[],"alert_level":0}
    obj=json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(obj.get("history"),list): raise ValueError("기존 상태 history 손상")
    return obj

def prepare(now):
    OUT.mkdir(parents=True,exist_ok=True)
    for x in (REPORT,PENDING,RECEIPT,AUDIT): x.unlink(missing_ok=True)
    state=load_state()
    old=int(state.get("alert_level",0))
    days=session_dates(now,6)
    by_date={x["date"]:x for x in state["history"]}
    prior_latest=by_date.get(days[-1].isoformat())
    # Recheck latest day even if in history, to detect source corrections; backfill gaps.
    need=[d for d in days if d.isoformat() not in by_date or d==days[-1]]
    recent=browser_fetch(need)
    vix=fetch_vix()
    for d in need:
        date=d.isoformat()
        if date not in vix:
            raise RuntimeError(f"Cboe VIX 공식 발표 {date} 아직 없음; 이전 값 대체 금지")
        by_date[date]={**recent[date],"vix":vix[date],"vix_source":VIX_URL}
    hist=sorted(by_date.values(),key=lambda r:r["date"])[-90:]
    latest=hist[-1]
    if latest["date"]!=days[-1].isoformat():
        raise RuntimeError("최신 미국 거래일과 옵션/변동성 기준일 불일치")
    # Last six calendar sessions must all be present, never silently ignore gaps.
    if any(d.isoformat() not in by_date for d in days):
        raise RuntimeError("공식 시장 영업일 시계열 누락: 경보 미전송")
    if not 0<latest["calls"] or latest["puts"]<0 or not math.isfinite(latest["ratio"]):
        raise RuntimeError("옵션 수치 오류")
    if old not in range(4): raise RuntimeError("경보 상태 손상")
    target,event=choose_stage(hist,old)
    fresh=state.get("last_source_date")!=latest["date"]
    revised=changed_metrics(prior_latest,latest)
    sample=os.environ.get("FORMAT_SAMPLE_SEND","false").lower()=="true"
    preview=os.environ.get("FORMAT_PREVIEW","false").lower()=="true"
    if not fresh and not revised and not sample and not preview:
        REPORT.unlink(missing_ok=True)
        print("spx_watch_same_date=true unchanged=true alert=false")
        return
    # Deduplication includes official corrected values, never the image's unknown notional.
    revision_hash=hashlib.sha256(json.dumps({
       k:latest[k] for k in ("calls","puts","ratio","vix","oi_puts")},
       sort_keys=True).encode()).hexdigest()[:12]
    if revised and target!=old:
        event="공식 정정으로 "+event
    key=f"{latest['date']}:{old}:{target}:{event}:{revision_hash}"
    fire=(fresh or revised) and (target!=old) and key!=state.get("last_alert_key")
    msg=render(latest,hist,old,target,event,now,sample=sample)
    if not fire and not sample and not preview: msg=""
    new={**state,
        "history":hist,"alert_level":target if fire else old,
        "last_source_date":latest["date"],
        "last_checked_kst":now.isoformat(timespec="seconds"),
        "last_was_revision":revised,
        "last_alert_key":key if fire else state.get("last_alert_key")}
    AUDIT.write_text(json.dumps({"source_date":latest["date"],"is_new":fresh,
        "official_revision":revised,"old_level":old,
        "actual_level":stage(latest["ratio"],latest["vix"]),"next_level":target,"event":event,
        "alert":fire,"sample":sample,"preview":preview,"urls":[latest["source"],VIX_URL],
        "data":latest},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if msg:
        REPORT.write_text(msg+"\n",encoding="utf-8")
    if not preview and not sample:
        PENDING.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"spx_source_valid=true date={latest['date']} PCR={latest['ratio']:.4f} VIX={latest['vix']:.2f} level={target} alert={fire} sample={sample}")

def telegram_call(token,action,params=None):
    url=f"https://api.telegram.org/bot{token}/{action}"
    req=urllib.request.Request(url,method="POST" if params is not None else "GET",
             data=urllib.parse.urlencode(params).encode() if params is not None else None)
    with urllib.request.urlopen(req,timeout=30) as f: return json.loads(f.read())

def send(now):
    sample=os.environ.get("FORMAT_SAMPLE_SEND","false").lower()=="true"
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat or not REPORT.exists() or (not sample and not PENDING.exists()):
        raise RuntimeError("봇·대화방·검증된 메시지 중 누락")
    me=telegram_call(token,"getMe")
    got=str((me.get("result") or {}).get("username") or "")
    if me.get("ok") is not True or got.lower()!=EXPECTED_BOT.lower():
        raise RuntimeError(f"예상 봇과 불일치: {got or 'unknown'}")
    msg=REPORT.read_text(encoding="utf-8").strip()
    expected=html.unescape(re.sub(r"</?b>","",msg))
    if not msg or len(msg)>MAX_CHARS: raise ValueError("텔레그램 메시지 길이 오류")
    out=telegram_call(token,"sendMessage",{"chat_id":chat,"text":msg,
           "parse_mode":"HTML","disable_web_page_preview":"true"})
    sent=out.get("result") or {}
    if out.get("ok") is not True or sent.get("text")!=expected:
        raise RuntimeError("Telegram 수신 텍스트 원문 불일치")
    if re.fullmatch(r"-?\d+",chat) and str((sent.get("chat") or {}).get("id"))!=chat:
        raise RuntimeError("Telegram 수신 대화방 불일치")
    if not isinstance(sent.get("message_id"),int): raise RuntimeError("Telegram 전송 확인번호 누락")
    receipt=dict(bot=got,message_id=sent["message_id"],source_date=json.loads(AUDIT.read_text())["source_date"],
        verified=True,at_kst=now.isoformat(timespec="seconds"),sample=sample)
    RECEIPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not sample:
        state=json.loads(PENDING.read_text(encoding="utf-8"))
        state["last_delivery"]=receipt
        PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"telegram_receipt_confirmed=true sample={sample} bot=@{got} message_id={sent['message_id']} full_text=true")

if __name__=="__main__":
    now=dt.datetime.now(KST)
    try:
        if sys.argv[1:]==["--send"]: send(now)
        else: prepare(now)
    except Exception as e:
        print("spx_watch_error="+type(e).__name__+": "+str(e),file=sys.stderr)
        sys.exit(1)

# 검증용 시점: 2026-10-25. 한 번만 발송하는 형식 시험이며 실제 시장위험 경보 상태는 불변.

# 최초 운용 기준선 검증: 공식 동일 날짜 옵션·VIX 실측값만 기록. 새 경보가 없으면 텔레그램 미발송.

#!/usr/bin/env python3
"""국내 CP–CD 및 AA- 회사채 신용스프레드: ECOS 공식자료 검증 후 단계별 텔레그램 경보."""
import datetime as dt
import hashlib
import html
import json
import math
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TABLE="817Y002"
SOURCE="https://ecos.bok.or.kr/#/SearchStat"
BOT="khs8879887988798879_bot"
STATE=pathlib.Path("data/korea_credit_spread_watch_state.json")
ALERT=pathlib.Path("out/korea_credit_spread_watch_alert.html")
PENDING=pathlib.Path("out/korea_credit_spread_watch_pending.json")
ACK=pathlib.Path("out/korea_credit_spread_watch_confirmed.json")
STATUS=pathlib.Path("out/korea_credit_spread_watch_status.md")
LEVELS=("안정","관찰","주의","악화","심각")
UP=((0,0),(30,70),(50,80),(70,90),(100,120))
DOWN={0:(30,70,5),1:(40,75,3),2:(60,85,3),3:(90,110,3)}
KINDS=("cp","cd","corp","gov")
LABELS={"cp":"CP(A1·91일)","cd":"CD(91일)","corp":"회사채(AA-·3년)","gov":"국고채(3년)"}

def normal(s):
    return re.sub(r"\s+","",str(s).upper().replace("−","-").replace("–","-"))

def name_kind(name):
    s=normal(name)
    if re.search(r"CP\(?91일",s): return "cp"
    if re.search(r"CD\(?91일",s): return "cd"
    if "회사채" in s and "3년" in s and "AA-" in s: return "corp"
    if "국고채" in s and "3년" in s: return "gov"
    return None

def codes_for(rows):
    names={k:set() for k in KINDS}
    for row in rows:
        k=name_kind(row.get("ITEM_NAME1",""))
        if k:
            code=str(row.get("ITEM_CODE1") or "").strip()
            if not re.fullmatch(r"[A-Z0-9]+",code):
                raise ValueError("공식 통계 항목코드 이상")
            names[k].add(code)
    if any(len(names[k])!=1 for k in KINDS):
        raise ValueError("CP·CD·회사채·국고채 공식 항목의 고유 식별 실패: "+str({k:len(v) for k,v in names.items()}))
    return {k:next(iter(names[k])) for k in KINDS}

def ecos(key,start,end,code=""):
    u=f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/{TABLE}/D/{start:%Y%m%d}/{end:%Y%m%d}"
    if code: u+="/"+code
    try:
        req=urllib.request.Request(u,headers={"User-Agent":"khs-watch/1.0"})
        with urllib.request.urlopen(req,timeout=35) as resp:
            data=json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"ECOS HTTP {exc.code}; 인증키 주소 비공개") from None
    except (urllib.error.URLError,TimeoutError,ValueError) as exc:
        raise RuntimeError("ECOS 응답 수신 실패: "+type(exc).__name__) from None
    body=data.get("StatisticSearch")
    if not isinstance(body,dict) or not isinstance(body.get("row"),list):
        raise RuntimeError("공식 ECOS 응답에서 검증된 값 없음")
    count=int(body.get("list_total_count",-1))
    if count<1 or count>len(body["row"]):
        raise RuntimeError("ECOS 페이지 잘림/통계 누락")
    return body["row"]

def fetch_rates(key,now):
    today=now.date()
    codes=codes_for(ecos(key,today-dt.timedelta(days=9),today))
    series={}
    for kind,code in codes.items():
        rows=ecos(key,today-dt.timedelta(days=50),today,code)
        vals={}
        for row in rows:
            if str(row.get("ITEM_CODE1","")).strip()!=code or name_kind(row.get("ITEM_NAME1",""))!=kind:
                raise ValueError("ECOS 출처 항목 불일치")
            day=str(row.get("TIME",""))
            if not re.fullmatch(r"\d{8}",day): raise ValueError("ECOS 날짜 오류")
            if normal(row.get("UNIT_NAME","")) not in ("연%","%"):
                raise ValueError("ECOS 금리 단위 검증 실패")
            rate=float(row["DATA_VALUE"])
            if not math.isfinite(rate) or not 0<=rate<=30: raise ValueError("ECOS 금리 이상값")
            if day in vals and vals[day]!=rate: raise ValueError("ECOS 중복 통계 충돌")
            vals[day]=rate
        series[kind]=vals
    return series,codes

def level(cp_cd,credit):
    for k in (4,3,2,1):
        x,y=UP[k]
        if cp_cd>=x or credit>=y: return k
    return 0

def aligned(series,now):
    days=sorted(set.intersection(*(set(series[k]) for k in KINDS)))
    if len(days)<7: raise ValueError("동일 날짜 4종 금리 7회 미만")
    result=[]
    for day in days:
        rates={k:series[k][day] for k in KINDS}
        cp_cd=round(100*(rates["cp"]-rates["cd"]),3)
        credit=round(100*(rates["corp"]-rates["gov"]),3)
        if not -150<cp_cd<1000 or not -150<credit<1000: raise ValueError("스프레드 상식범위 이탈")
        result.append({"date":day,"rates":rates,"cp_cd":cp_cd,"credit":credit,"rank":level(cp_cd,credit)})
    latest=dt.datetime.strptime(days[-1],"%Y%m%d").date()
    if latest>now.date() or (now.date()-latest).days>7: raise ValueError("공식자료 시점이 오래됨")
    for a,b in zip(days[-7:],days[-6:]):
        d1=dt.datetime.strptime(a,"%Y%m%d").date()
        d2=dt.datetime.strptime(b,"%Y%m%d").date()
        if (d2-d1).days>5: raise ValueError("중간 공표일 누락 가능성")
    return result

def recovery(old,rows):
    for target in range(old):
        a,b,count=DOWN[target]
        if len(rows)>=count and all(r["cp_cd"]<a and r["credit"]<b for r in rows[-count:]):
            return target
    return old

def early(rows):
    now,prev,ago=rows[-1],rows[-2],rows[-6]
    events=[]
    if len(rows)>=7:
        prev_ago=rows[-7]
        if now["cp_cd"]-ago["cp_cd"]>=10 and prev["cp_cd"]-prev_ago["cp_cd"]<10:
            events.append("CP–CD 금리 차이 5영업일 10bp 이상 급확대")
        if (now["rates"]["cp"]-ago["rates"]["cp"])*100>=15 and (prev["rates"]["cp"]-prev_ago["rates"]["cp"])*100<15:
            events.append("CP 금리 5영업일 15bp 이상 상승")
    for boundary in (3.80,4.00):
        if now["rates"]["cp"]>=boundary>prev["rates"]["cp"]:
            events.append(f"CP {boundary:.2f}% 신규 상향 돌파(보조 경보)")
    return events

def decide(rows,state):
    actual=rows[-1]["rank"]
    old=state.get("notified_rank")
    events=early(rows)
    if old is None: transition,target="최초 기준선",actual
    else:
        old=int(old)
        if old not in range(5): raise ValueError("이전 경보 단계 잘못됨")
        if actual>old: transition,target="위험 상승",actual
        elif actual<old:
            target=recovery(old,rows)
            transition="회복 확인" if target<old else "유지"
        else: transition,target="유지",old
    raw=json.dumps({"date":rows[-1]["date"],"old":old,"new":target,
                    "transition":transition,"events":events},ensure_ascii=False,sort_keys=True)
    signature=hashlib.sha256(raw.encode()).hexdigest()
    send=(transition!="유지" or bool(events)) and signature!=state.get("last_alert_signature")
    return {"send":send,"rank":target,"previous_rank":old,"transition":transition,
            "events":events,"signature":signature}

def render(rows,decision,now):
    latest,prev,week=rows[-1],rows[-2],rows[-6]
    stage=LEVELS[decision["rank"]]
    date=dt.datetime.strptime(latest["date"],"%Y%m%d").strftime("%Y-%m-%d")
    signed=lambda v:f"{v:+.1f}bp"
    lines=[f"<b>[국내 CP·신용스프레드 | {stage} | {decision['transition']}]</b>",
           f"공식 자료 기준일: {date} | 조회 {now:%Y-%m-%d %H:%M} KST",
           "금리 연% / 금리 차이 bp (1bp=0.01%포인트)",""]
    for k in KINDS:
        v=latest["rates"][k]
        lines.append(f"• {html.escape(LABELS[k])}: {v:.3f}% | 전일 {signed((v-prev['rates'][k])*100)} / 5영업일 {signed((v-week['rates'][k])*100)}")
    for k,label in (("cp_cd","CP–CD 금리 차이"),("credit","회사채 AA- 3년−국고채 3년 금리 차이")):
        lines.append(f"• {label}: {latest[k]:.1f}bp | 전일 {signed(latest[k]-prev[k])} / 5영업일 {signed(latest[k]-week[k])}")
    if decision["previous_rank"] is not None:
        lines.append(f"단계 변경: {LEVELS[decision['previous_rank']]} → {stage}")
    if decision["events"]:
        lines.append("조기경보: "+" / ".join(html.escape(x) for x in decision["events"]))
    ups={0:"관찰: CP–CD 30bp 또는 AA- 70bp",1:"주의: CP–CD 50bp 또는 AA- 80bp",
         2:"악화: CP–CD 70bp 또는 AA- 90bp",3:"심각: CP–CD 100bp 또는 AA- 120bp"}
    if decision["rank"] in ups: lines.append("다음 악화선: "+ups[decision["rank"]])
    if decision["rank"]>0:
        a,b,n=DOWN[decision["rank"]-1]
        lines.append(f"회복선: CP–CD {a:g}bp 미만, AA- {b:g}bp 미만 <b>동시</b> {n}영업일 연속")
    lines+=["의미: 기업 차환금리 및 회사채 발행 여건에 주의. 금리 상승 자체와 신용위험 프리미엄 확대는 구분해야 합니다.",
            "이 단계는 자체 감시 기준이며 금융당국의 공식 위기 등급이 아닙니다.",
            f"공식 원천: 한국은행 경제통계시스템(ECOS), 시장금리(일별) {TABLE}",
            SOURCE]
    return "\n".join(lines)

def telegram(url,params=None):
    req=urllib.request.Request(url,method="POST" if params else "GET",
         data=urllib.parse.urlencode(params).encode() if params else None)
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Telegram HTTP {exc.code} (인증정보 비공개)") from None
    except urllib.error.URLError as exc:
        raise RuntimeError("Telegram 연결 실패: "+type(exc).__name__) from None

def send(now):
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("기존 GLOBAL_RATES 텔레그램 보안 설정 누락")
    if not ALERT.exists() or not PENDING.exists(): raise RuntimeError("검증된 신규 경보 없음")
    who=telegram(f"https://api.telegram.org/bot{token}/getMe")
    got=str((who.get("result") or {}).get("username") or "")
    if who.get("ok") is not True or got.lower()!=BOT.lower():
        raise RuntimeError(f"잘못된 텔레그램 봇: expected @{BOT} got @{got or 'unknown'}")
    message=ALERT.read_text(encoding="utf-8").strip()
    if not message or len(message)>4096: raise ValueError("메시지 길이 또는 공백 오류")
    reply=telegram(f"https://api.telegram.org/bot{token}/sendMessage",
                   {"chat_id":chat,"text":message,"parse_mode":"HTML","disable_web_page_preview":"true"})
    obj=reply.get("result") or {}
    mid=obj.get("message_id")
    if reply.get("ok") is not True or not isinstance(mid,int) or mid<1 or not str(obj.get("text") or "").strip():
        raise RuntimeError("Telegram 실제 메시지 수신 확인 실패")
    if re.fullmatch(r"-?\d+",chat) and str((obj.get("chat") or {}).get("id"))!=chat:
        raise RuntimeError("Telegram 수신 대화방 불일치")
    receipt={"status":"confirmed","bot_username":got,"message_id":mid,
             "delivered_at_kst":now.isoformat(timespec="seconds"),
             "message_sha256":hashlib.sha256(message.encode()).hexdigest(),
             "run_id":os.environ.get("GITHUB_RUN_ID","local")}
    state=json.loads(PENDING.read_text(encoding="utf-8"))
    state["delivery_receipt"]=receipt
    ACK.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"telegram_delivery_confirmed=true bot=@{got} message_id={mid}")

def watch(now):
    ALERT.parent.mkdir(parents=True,exist_ok=True)
    for p in (ALERT,PENDING,ACK): p.unlink(missing_ok=True)
    key=os.environ.get("ECOS_API_KEY","").strip()
    if not key: raise RuntimeError("기존 ECOS_API_KEY 보안 설정 누락")
    values,codes=fetch_rates(key,now)
    rows=aligned(values,now)
    state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    action=decide(rows,state)
    latest=rows[-1]
    STATUS.write_text("\n\n".join([
        "# 국내 CP·회사채 신용스프레드",
        f"공식 기준일: {latest['date']}",
        f"실측 단계: {LEVELS[latest['rank']]}",
        f"CP–CD {latest['cp_cd']:.1f}bp / 회사채 AA- {latest['credit']:.1f}bp",
        "공식 항목코드: "+", ".join(k+"="+v for k,v in codes.items()),
        "알림 상태: "+("새 경보 검증됨" if action["send"] else "새 경보 없음"),
        "원천: "+SOURCE])+"\n",encoding="utf-8")
    print(f"credit_source_valid=true day={latest['date']} cp_cd={latest['cp_cd']} credit={latest['credit']} alert={action['send']}")
    if action["send"]:
        ALERT.write_text(render(rows,action,now)+"\n",encoding="utf-8")
        new={"notified_rank":action["rank"],"last_source_date":latest["date"],
             "last_alert_signature":action["signature"],"transition":action["transition"],
             "last_alert_at_kst":now.isoformat(timespec="seconds"),
             "cp_cd_bp":latest["cp_cd"],"aa_spread_bp":latest["credit"],
             "source":SOURCE,"stat_code":TABLE}
        PENDING.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    try:
        now=dt.datetime.now(ZoneInfo("Asia/Seoul"))
        send(now) if sys.argv[1:]==["--send"] else watch(now)
    except Exception as exc:
        print(f"credit_watch_failed={type(exc).__name__}: {exc}",file=sys.stderr)
        sys.exit(1)

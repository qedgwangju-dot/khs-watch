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
HEALTH=pathlib.Path("data/korea_credit_spread_watch_health.json")
HEALTH_PENDING=pathlib.Path("out/korea_credit_spread_watch_health_pending.json")
LEVELS=("안정","관찰","주의","악화","심각")
UP=((0,0),(30,70),(50,80),(70,90),(100,120))
DOWN={0:(30,70,5),1:(40,75,3),2:(60,85,3),3:(90,110,3)}
KINDS=("cp","cd","corp","gov")
LABELS={"cp":"기업어음(CP·91일)","cd":"양도성예금증서(CD·91일)","corp":"회사채(AA-·3년)","gov":"국고채(3년)"}
# 표시용 방향은 5영업일 신용스프레드 변화가 ±2bp를 넘어야 실질 변화로 표시한다.
# 이는 모니터링 자체 판정선이며 한국은행·금융당국의 공식 위험 기준이 아니다.
FLAT_BP=2.0
MAX_MESSAGE_CHARS=1600

def normal(s):
    return re.sub(r"\s+","",str(s).upper().replace("−","-").replace("–","-"))

def name_kind(name):
    s=normal(name)
    if re.search(r"CP\(?91일",s): return "cp"
    if re.search(r"CD\(?91일",s): return "cd"
    if s=="회사채(3년,AA-)": return "corp"  # 민평(010310000)은 별도 계열이므로 섞지 않음
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
        raise ValueError("CP·CD·회사채·국고채 공식 항목의 고유 식별 실패: "+str({k:len(v) for k,v in names.items()})+" / 이름·코드: "+str([(row.get("ITEM_NAME1"),row.get("ITEM_CODE1")) for row in rows if name_kind(row.get("ITEM_NAME1",""))=="corp"]))
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
    # 네 금리 중 어느 하나만 신규 공표되었을 때 오래된 공통 날짜로 후퇴하지 않는다.
    latest_by_kind={k:max(series[k]) if series.get(k) else None for k in KINDS}
    if None in latest_by_kind.values() or len(set(latest_by_kind.values()))!=1:
        raise ValueError("네 계열의 최신 공식 기준일 불일치: "+str(latest_by_kind))
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
    # 장 종료 후 평일에는 당일 공표가 늦어지는 경우 과거 거래일의 경보를
    # 최신 경보로 재발송하지 않는다. 한국 휴장일에는 일시적인 조회 실패가
    # 될 수 있으나 잘못된 시장경보 발송보다 안전한 실패방식이다.
    if now.weekday()<5 and now.hour>=18 and latest!=now.date():
        raise ValueError("장 종료 후 공식 금리 기준일 지연 또는 휴장: 당일 미공표 데이터를 경보에 사용하지 않음")
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

def signed(v):
    # 반올림으로 생기는 -0.0bp 표시를 제거한다.
    z=round(float(v),1)
    return f"{0.0:+.1f}" if z==0 else f"{z:+.1f}"

def direction(delta):
    if delta>=FLAT_BP: return ("악화","↑","확대")
    if delta<=-FLAT_BP: return ("개선","↓","축소")
    return ("보합","→","보합")

def day_word(delta):
    # 계산 정밀도 아래의 소수 변화는 실무상 변화 없음으로 표시한다.
    d=round(float(delta),1)
    return "확대" if d>0 else ("축소" if d<0 else "불변")

def spread_bucket(metric,value):
    """한 곳의 UP 임계값에서 숫자 옆에 표시할 단계와 정확한 반개구간을 도출한다."""
    if metric not in ("cp_cd","credit"):
        raise ValueError("지원하지 않는 신용스프레드")
    if not math.isfinite(float(value)):
        raise ValueError("유효하지 않은 신용스프레드")
    col=0 if metric=="cp_cd" else 1
    rank=next((k for k in (4,3,2,1) if value>=UP[k][col]),0)
    if rank==0:
        span=f"{UP[1][col]:g} 미만"
    elif rank==4:
        span=f"{UP[4][col]:g} 이상"
    else:
        span=f"{UP[rank][col]:g} 이상·{UP[rank+1][col]:g} 미만"
    return LEVELS[rank],span

def spread_legend(metric):
    """부문별 전체 5단계 기준을 기존 UP 상수에서 자동 생성한다."""
    if metric not in ("cp_cd","credit"):
        raise ValueError("지원하지 않는 신용스프레드")
    col=0 if metric=="cp_cd" else 1
    parts=[]
    for k in range(5):
        lo,hi=(UP[k][col] if k else None),(UP[k+1][col] if k<4 else None)
        if lo is None: span=f"{hi:g}미만"
        elif hi is None: span=f"{lo:g}이상"
        else: span=f"{lo:g}~{hi:g}미만"
        parts.append(f"{LEVELS[k]}:{span}")
    return " · ".join(parts)

def direction_overview(rows):
    if len(rows)<6: raise ValueError("방향 분석을 위한 5영업일 기준 데이터 부족")
    latest,week=rows[-1],rows[-6]
    cp_delta=round(latest["cp_cd"]-week["cp_cd"],3)
    aa_delta=round(latest["credit"]-week["credit"],3)
    cp,aa=direction(cp_delta),direction(aa_delta)
    return {"cp":cp,"aa":aa,"cp_delta":cp_delta,"aa_delta":aa_delta,
            "summary":f"단기 {cp[0]}{cp[1]} · 회사채 {aa[0]}{aa[1]}"}

def recovery_streak(rows,target):
    cp_cap,aa_cap,n=DOWN[target]
    count=0
    for row in reversed(rows):
        if row["cp_cd"]<cp_cap and row["credit"]<aa_cap: count+=1
        else: break
    return min(count,n),n

def next_boundary(latest):
    k=latest["rank"]
    if k>=4: return "심각 단계 기준 충족(추가 악화는 절대 수준·상승 속도 추적)"
    cp_lim,aa_lim=UP[k+1]
    cp_gap=max(0,cp_lim-latest["cp_cd"])
    aa_gap=max(0,aa_lim-latest["credit"])
    return (f"{LEVELS[k+1]}: CP–CD {cp_lim:.0f}bp(+{cp_gap:.1f}bp) "
            f"또는 AA- {aa_lim:.0f}bp(+{aa_gap:.1f}bp)")

def verified_health_snapshot(rows,codes,now,decision):
    """경보가 없는 날도 공식자료 성공을 기록하되 같은 자료는 새 상태로 만들지 않는다."""
    latest=rows[-1]
    if len(rows)<7: raise ValueError("공식 금리 비교 자료 부족")
    values={"date":latest["date"],"cp":latest["rates"]["cp"],
            "cd":latest["rates"]["cd"],"corp":latest["rates"]["corp"],
            "gov":latest["rates"]["gov"],"cp_cd_bp":latest["cp_cd"],
            "aa_spread_bp":latest["credit"],"observed_rank":latest["rank"]}
    fingerprint=hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {"official_date":latest["date"],"rate_values":values,
            "fingerprint":fingerprint,"alert_rank":decision["rank"],
            "verified_at_kst":now.isoformat(timespec="seconds"),
            "source":SOURCE,"stat_code":TABLE,
            "codes":codes,"note":"원자료 검증 성공 기록. 텔레그램 발송 확인과는 별개"}

def render(rows,decision,now,sample=False):
    if len(rows)<7: raise ValueError("원문 통계가 7공표일 미만이라 메시지 생성 불가")
    latest,prev,week=rows[-1],rows[-2],rows[-6]
    measured=LEVELS[latest["rank"]]
    applied=LEVELS[decision["rank"]]
    d=direction_overview(rows)
    cp_bucket,cp_band=spread_bucket("cp_cd",latest["cp_cd"])
    aa_bucket,aa_band=spread_bucket("credit",latest["credit"])
    date=dt.datetime.strptime(latest["date"],"%Y%m%d").strftime("%Y-%m-%d")
    diff1=lambda key:latest[key]-prev[key]
    diff5=lambda key:latest[key]-week[key]
    rate_delta=lambda key,past:(latest["rates"][key]-past["rates"][key])*100
    lines=[]
    if sample: lines.append("<b>[양식 검증 · 새 경보가 아닙니다]</b>")
    lines += [
        f"<b>국내 신용금리 경보 | {applied}</b>",
        f"<b>5영업일 방향: {d['summary']}</b>",
        f"전일: CP–CD {signed(diff1('cp_cd'))}bp {day_word(diff1('cp_cd'))} / "
        f"AA-금리차 {signed(diff1('credit'))}bp {day_word(diff1('credit'))}",
        f"공식 기준일 {date} · 확대=상대 조달부담 증가",
    ]
    if applied!=measured:
        lines.append(f"실측 {measured} / 경보 {applied}(회복 연속 확인 중)")
    if decision["transition"]!="유지":
        lines.append(f"단계 판정: {html.escape(decision['transition'])}")
    lines += [
        "",
        "<b>① 핵심 신용스프레드</b>",
        "CP(기업어음: 기업의 단기 자금조달)",
        "CD(양도성예금증서: 은행의 단기 자금조달)",
        f"CP–CD <b>{latest['cp_cd']:.1f}bp</b> [{cp_bucket}: {cp_band}] {d['cp'][1]} {d['cp'][2]}",
        f"  전일 {signed(diff1('cp_cd'))} / 5일 {signed(diff5('cp_cd'))}bp",
        f"AA- 회사채–국고채 <b>{latest['credit']:.1f}bp</b> [{aa_bucket}: {aa_band}] {d['aa'][1]} {d['aa'][2]}",
        f"  전일 {signed(diff1('credit'))} / 5일 {signed(diff5('credit'))}bp",
        "CP–CD 구간(bp): "+spread_legend("cp_cd"),
        "AA- 구간(bp): "+spread_legend("credit"),
        "<b>② 실제 금리 (연% · 전일/5일 변화)</b>",
    ]
    for kind,short in (("cp","CP 91일"),("cd","CD 91일"),
                       ("corp","회사채 AA- 3년"),("gov","국고채 3년")):
        lines.append(f"{short} {latest['rates'][kind]:.3f}% | "
                     f"{signed(rate_delta(kind,prev))}/{signed(rate_delta(kind,week))}bp")
    lines += [
        "<b>③ 다음 경계</b>",
        next_boundary(latest)
    ]
    if decision["rank"]>0:
        t=decision["rank"]-1
        cp_cap,aa_cap,n=DOWN[t]
        streak,_=recovery_streak(rows,t)
        lines.append(f"하향: CP–CD {cp_cap:.0f}bp 미만 + AA- {aa_cap:.0f}bp 미만")
        lines.append(f"  두 조건 동시 {n}영업일 연속 (현재 {streak}/{n})")
    if decision["events"]:
        lines.append("추가 신호: "+"; ".join(html.escape(x) for x in decision["events"]))
    if d["cp"][0]=="악화" and d["aa"][0]=="보합":
        reading="단기 기업자금 압력 상승, AA- 회사채 전반 확산은 아직 확인되지 않음"
    elif d["cp"][0]=="악화" and d["aa"][0]=="악화":
        reading="단기·회사채 신용위험 프리미엄 동반 확대"
    elif d["cp"][0]=="개선" and d["aa"][0]=="개선":
        reading="두 시장의 신용위험 프리미엄 동반 축소"
    elif d["cp"][0]=="보합" and d["aa"][0]=="보합":
        reading="두 스프레드 모두 최근 5영업일 거의 보합"
    else:
        reading=f"단기는 {d['cp'][0]}, 회사채는 {d['aa'][0]}: 부문별 방향이 다름"
    lines += [
        "<b>해석:</b> "+reading,
        "방향은 5일 변화 ±2bp 기준; 단계는 자체 감시 기준(공식 위기등급 아님)",
        f"한국은행 ECOS {TABLE} · 조회 {now:%m/%d %H:%M} KST",
        SOURCE,
    ]
    message="\n".join(lines)
    # 텔레그램 한 메시지에 원문 그대로 표시해야 하므로 초과 시 잘라 보내지 않는다.
    if len(message)>MAX_MESSAGE_CHARS or len(html.unescape(re.sub(r"</?b>","",message)))>MAX_MESSAGE_CHARS:
        raise ValueError("알림 최대 표시길이 초과: 임의 잘라내기 금지")
    return message

def telegram_plaintext(message):
    """허용된 <b> 태그만 사용하고 수신 확인 시 원문 전부를 대조한다."""
    if re.search(r"<(?!/?b>)[^>]*>",message):
        raise ValueError("텔레그램 미허용 HTML 태그")
    return html.unescape(re.sub(r"</?b>","",message))

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

def verify_telegram_route():
    """실제 메시지를 보내지 않고 현재 봇·수신대화방 권한을 재확인한다."""
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("텔레그램 봇·수신 대화방 인증정보 누락")
    who=telegram(f"https://api.telegram.org/bot{token}/getMe")
    got=str((who.get("result") or {}).get("username") or "")
    if who.get("ok") is not True or got.lower()!=BOT.lower():
        raise RuntimeError("예상 텔레그램 봇과 현재 인증계정 불일치")
    response=telegram(f"https://api.telegram.org/bot{token}/getChat",{"chat_id":chat})
    target=response.get("result") or {}
    if response.get("ok") is not True or not target.get("id"):
        raise RuntimeError("Telegram getChat으로 수신 대화방 접근 확인 실패")
    if re.fullmatch(r"-?\d+",chat) and str(target.get("id"))!=chat:
        raise RuntimeError("Telegram 수신 대화방 ID 불일치")
    print(f"telegram_route_verified=true bot=@{got} destination_accessible=true no_message_sent=true")

def send(now):
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("기존 GLOBAL_RATES 텔레그램 보안 설정 누락")
    sample=os.environ.get("FORMAT_SAMPLE_SEND","").strip().lower()=="true"
    if not ALERT.exists() or (not sample and not PENDING.exists()):
        raise RuntimeError("검증된 신규 경보 없음")
    who=telegram(f"https://api.telegram.org/bot{token}/getMe")
    got=str((who.get("result") or {}).get("username") or "")
    if who.get("ok") is not True or got.lower()!=BOT.lower():
        raise RuntimeError(f"잘못된 텔레그램 봇: expected @{BOT} got @{got or 'unknown'}")
    message=ALERT.read_text(encoding="utf-8").strip()
    if not message or len(message)>MAX_MESSAGE_CHARS:
        raise ValueError("메시지 길이 또는 공백 오류")
    expected_text=telegram_plaintext(message)
    reply=telegram(f"https://api.telegram.org/bot{token}/sendMessage",
                   {"chat_id":chat,"text":message,"parse_mode":"HTML","disable_web_page_preview":"true"})
    obj=reply.get("result") or {}
    mid=obj.get("message_id")
    if reply.get("ok") is not True or not isinstance(mid,int) or mid<1 or not str(obj.get("text") or "").strip():
        raise RuntimeError("Telegram 실제 메시지 수신 확인 실패")
    if obj.get("text")!=expected_text:
        raise RuntimeError("Telegram 응답 본문과 발송 원문이 다름: 내용 보존 미확인")
    if re.fullmatch(r"-?\d+",chat) and str((obj.get("chat") or {}).get("id"))!=chat:
        raise RuntimeError("Telegram 수신 대화방 불일치")
    receipt={"status":"confirmed","bot_username":got,"message_id":mid,
             "delivered_at_kst":now.isoformat(timespec="seconds"),
             "message_sha256":hashlib.sha256(message.encode()).hexdigest(),
             "run_id":os.environ.get("GITHUB_RUN_ID","local")}
    ACK.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not sample:
        state=json.loads(PENDING.read_text(encoding="utf-8"))
        state["delivery_receipt"]=receipt
        PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"telegram_delivery_confirmed=true full_text_verified=true sample={sample} bot=@{got} message_id={mid}")

def watch(now):
    ALERT.parent.mkdir(parents=True,exist_ok=True)
    for p in (ALERT,PENDING,ACK,HEALTH_PENDING): p.unlink(missing_ok=True)
    key=os.environ.get("ECOS_API_KEY","").strip()
    if not key: raise RuntimeError("기존 ECOS_API_KEY 보안 설정 누락")
    values,codes=fetch_rates(key,now)
    rows=aligned(values,now)
    state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    action=decide(rows,state)
    health=verified_health_snapshot(rows,codes,now,action)
    prior=json.loads(HEALTH.read_text(encoding="utf-8")) if HEALTH.exists() else {}
    if prior.get("fingerprint")!=health["fingerprint"] or prior.get("alert_rank")!=health["alert_rank"]:
        HEALTH_PENDING.write_text(json.dumps(health,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    latest=rows[-1]
    d=direction_overview(rows)
    sample=os.environ.get("FORMAT_SAMPLE_SEND","").strip().lower()=="true"
    preview=os.environ.get("PREVIEW_FORMAT","").strip().lower()=="true"
    STATUS.write_text("\n\n".join([
        "# 국내 CP·회사채 신용스프레드",
        f"공식 기준일: {latest['date']}",
        f"데이터 지문: {health['fingerprint'][:12]} / 상태 저장 필요: {HEALTH_PENDING.exists()}",
        f"실측 단계: {LEVELS[latest['rank']]} / 경보 단계: {LEVELS[action['rank']]}",
        f"단기 방향: {d['cp'][0]} / 회사채 방향: {d['aa'][0]} (5영업일 기준)",
        f"추가 신호: {'; '.join(action['events']) or '없음'}",
        f"CP–CD {latest['cp_cd']:.1f}bp / 회사채 AA- {latest['credit']:.1f}bp",
        "공식 항목코드: "+", ".join(k+"="+v for k,v in codes.items()),
        "알림 상태: "+("형식 시험(실제 새 경보 아님)" if sample else ("새 경보 검증됨" if action["send"] else "새 경보 없음")),
        "원천: "+SOURCE])+"\n",encoding="utf-8")
    print(f"credit_source_valid=true day={latest['date']} cp_cd={latest['cp_cd']} credit={latest['credit']} alert={action['send']}")
    if action["send"] or sample or preview:
        ALERT.write_text(render(rows,action,now,sample=sample)+"\n",encoding="utf-8")
    if action["send"] and not sample and not preview:
        new={"notified_rank":action["rank"],"last_source_date":latest["date"],
             "last_alert_signature":action["signature"],"transition":action["transition"],
             "last_alert_at_kst":now.isoformat(timespec="seconds"),
             "cp_cd_bp":latest["cp_cd"],"aa_spread_bp":latest["credit"],
             "source":SOURCE,"stat_code":TABLE}
        PENDING.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    try:
        now=dt.datetime.now(ZoneInfo("Asia/Seoul"))
        if sys.argv[1:]==["--probe"]:
            verify_telegram_route()
        elif sys.argv[1:]==["--send"]:
            send(now)
        elif not sys.argv[1:]:
            watch(now)
        else:
            raise ValueError("알 수 없는 실행 인자; 경보 중단")
    except Exception as exc:
        print(f"credit_watch_failed={type(exc).__name__}: {exc}",file=sys.stderr)
        sys.exit(1)

# 검증 기록: 실제 발송 시험은 명시적 커밋 표시를 사용하며 신규 신용경보로 기록하지 않는다.
# 2026-10-27: 봇·대화방·본문 무손실 전송을 실측하는 1회 시험. 경보 상태 변경 금지.

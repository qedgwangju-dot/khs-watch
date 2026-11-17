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
CHART=pathlib.Path("out/korea_credit_spread_watch_chart.png")
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
    # 종합 등급이 다른 지표 때문에 유지되어도 개별 신용위험 상승은 알린다.
    # 단순 가격 변경이나 회복은 이 선행경보에 포함하지 않는다.
    for metric,label in (("cp_cd","CP–CD"),("credit","AA- 회사채–국고채")):
        previous,_=spread_bucket(metric,prev[metric])
        current,_=spread_bucket(metric,now[metric])
        if LEVELS.index(current)>LEVELS.index(previous):
            events.append(f"{label} 개별 구간 {previous}→{current} 상향(선행경보)")
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

def delivery_kst_date(now):
    """실제 실행시각을 한국시간 날짜로 정규화."""
    if now.tzinfo is None: raise ValueError("한국시간 날짜 판정에 시간대 정보 필요")
    return now.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()

def last_delivery_kst_date(state):
    """기존 수신 확인 기록까지 이용하여 마이그레이션 시에도 중복을 차단."""
    dates=[str(state.get("last_sent_kst_date") or "")]
    for key in ("last_delivery_receipt","last_daily_report_receipt","delivery_receipt"):
        record=state.get(key)
        if not isinstance(record,dict): continue
        value=record.get("delivered_at_kst")
        if not value: continue
        try: dates.append(delivery_kst_date(dt.datetime.fromisoformat(str(value))))
        except (ValueError,TypeError): continue
    return max(dates)

def delivery_plan(rows,state,decision,now):
    """한국시간 하루 최대 1개 메시지: 정기보고·상향경보 합산."""
    if last_delivery_kst_date(state)>=delivery_kst_date(now):
        return None,False
    latest_date=rows[-1]["date"]
    last_daily=str(state.get("last_daily_report_date") or "")
    daily_due=latest_date>last_daily
    if decision["send"]: return "alert",daily_due
    if daily_due: return "daily",True
    return None,False

def pending_delivery_state(state,decision,latest,now,kind,daily_due):
    """실제 전송 전에는 커밋하지 않으며 기존 경보 기록도 보존."""
    if kind not in ("alert","daily"): raise ValueError("잘못된 발송 종류")
    new=dict(state)
    if kind=="alert":
        new.update({"notified_rank":decision["rank"],"last_source_date":latest["date"],
                    "last_alert_signature":decision["signature"],"transition":decision["transition"],
                    "last_alert_at_kst":now.isoformat(timespec="seconds"),
                    "cp_cd_bp":latest["cp_cd"],"aa_spread_bp":latest["credit"],
                    "source":SOURCE,"stat_code":TABLE})
    if daily_due: new["last_daily_report_date"]=latest["date"]
    # 상태 파일은 실제 Telegram 응답 검증 후에만 커밋된다.
    new["last_sent_kst_date"]=delivery_kst_date(now)
    new["_pending_message_kind"]=kind
    new["_pending_daily_due"]=daily_due
    return new

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


def overall_trend(rows):
    """종합 위험 절대수준과 최근 5영업일 추세는 별도로 표현한다."""
    d=direction_overview(rows)
    a,b=d["cp"][0],d["aa"][0]
    if a==b=="개선": return "동반 개선"
    if a==b=="악화": return "동반 악화"
    if a==b=="보합": return "보합"
    if "악화" in (a,b) and "개선" in (a,b): return "혼조"
    return "부분 악화" if "악화" in (a,b) else "부분 개선"

def photo_caption(rows,decision,now,daily=False,sample=False):
    """한 장의 사진과 함께 전송할 짧은 텔레그램 캡션."""
    latest,prev,week=rows[-1],rows[-2],rows[-6]
    risk=LEVELS[decision["rank"]]
    trend=direction_overview(rows)
    cp_band,_=spread_bucket("cp_cd",latest["cp_cd"])
    aa_band,_=spread_bucket("credit",latest["credit"])
    day=dt.datetime.strptime(latest["date"],"%Y%m%d").strftime("%Y-%m-%d")
    lines=[]
    if sample: lines.append("<b>[양식 검증 · 시장 경보 아님]</b>")
    lines += [
        f"<b>국내 신용금리 {'일일 보고' if daily else '경보'} | 종합 위험: {risk}</b>",
        f"<b>최근 방향: {overall_trend(rows)} (단기 {trend['cp'][0]} / 회사채 {trend['aa'][0]})</b>",
        "위험 등급과 변화 방향은 별개 · 주의는 정상 회복을 뜻하지 않음",
        f"CP–CD {latest['cp_cd']:.1f}bp [{cp_band}] "
        f"전일 {signed(latest['cp_cd']-prev['cp_cd'])}bp / 5일 {signed(latest['cp_cd']-week['cp_cd'])}bp",
        f"AA- 회사채 차이 {latest['credit']:.1f}bp [{aa_band}] "
        f"전일 {signed(latest['credit']-prev['credit'])}bp / 5일 {signed(latest['credit']-week['credit'])}bp",
        f"실제 금리: CP {latest['rates']['cp']:.3f}% · CD {latest['rates']['cd']:.3f}% · "
        f"회사채 AA- {latest['rates']['corp']:.3f}% · 국고채 {latest['rates']['gov']:.3f}%",
    ]
    if LEVELS[latest["rank"]]!=risk:
        lines.append(f"실측 {LEVELS[latest['rank']]} / 경보 {risk}(회복 연속 확인 중)")
    if decision["transition"]!="유지": lines.append("단계 변경: "+html.escape(decision["transition"]))
    lines.append("다음 위험 경계: "+html.escape(next_boundary(latest)))
    if decision["rank"]>0:
        low_cp,low_aa,n=DOWN[decision["rank"]-1]
        count,_=recovery_streak(rows,decision["rank"]-1)
        lines.append(f"하향: CP–CD {low_cp:g}bp·AA- {low_aa:g}bp 미만 동시 {n}영업일({count}/{n})")
    if decision["events"]:
        lines.append("선행경보: "+"; ".join(html.escape(x) for x in decision["events"]))
    lines += [f"공식 기준일 {day} · 한국은행 ECOS {TABLE} (자체 위험 기준)",SOURCE]
    caption="\n".join(lines)
    if len(telegram_plaintext(caption))>1024 or len(caption)>1150:
        raise ValueError("Telegram 사진 설명 길이 초과: 생략 없이 발송 차단")
    return caption

def _kr_font(size,bold=False):
    from PIL import ImageFont
    name="NanumGothicBold.ttf" if bold else "NanumGothic.ttf"
    alt="NanumBarunGothicBold.ttf" if bold else "NanumBarunGothic.ttf"
    for filename in (name,alt):
        candidate=pathlib.Path("/usr/share/fonts/truetype/nanum")/filename
        if candidate.is_file(): return ImageFont.truetype(str(candidate),size)
    raise RuntimeError("한글 이미지 차트 글꼴 없음: 발송 중단")

def render_chart(rows,decision,now,target):
    """두 개의 별도 시계열 차트·위험 단계·상승/개선 추세를 한 PNG에 표현."""
    from PIL import Image,ImageDraw
    if len(rows)<7: raise ValueError("차트 공표일 7개 미만")
    W,H=1440,1580
    pic=Image.new("RGB",(W,H),"#F4F7FB")
    draw=ImageDraw.Draw(pic)
    font=lambda n:_kr_font(n)
    bold=lambda n:_kr_font(n,True)
    navy="#12243D"; gray="#50647B"
    colors={"안정":("#DDF5E9","#166948"),"관찰":("#FFF2CA","#806208"),
            "주의":("#FFE4C6","#A45D08"),"악화":("#FBD7DA","#AC303E"),
            "심각":("#F4B9C1","#841525")}
    risk=LEVELS[decision["rank"]]
    d=direction_overview(rows)
    latest,prev=rows[-1],rows[-2]
    day=dt.datetime.strptime(latest["date"],"%Y%m%d").strftime("%Y-%m-%d")
    draw.rectangle((0,0,W,261),fill=navy)
    draw.text((62,30),"국내 신용금리 · 위험 추세 차트",font=bold(50),fill="#FFFFFF")
    draw.text((63,99),f"한국은행 ECOS {TABLE} · 공식 기준일 {day}",font=font(29),fill="#CAD7E9")
    bg,fg=colors[risk]
    draw.rounded_rectangle((61,163,660,237),radius=15,fill=bg)
    draw.text((87,174),f"현재 종합 위험: {risk}",font=bold(45),fill=fg)
    draw.rounded_rectangle((683,163,1380,237),radius=15,fill="#E3EBF7")
    draw.text((709,179),f"최근 방향: {overall_trend(rows)}",font=bold(40),fill="#254D7C")
    def card(x0,label,value,bucket,change,trend):
        x1=x0+644
        draw.rounded_rectangle((x0,291,x1,497),radius=20,fill="#FFFFFF")
        draw.text((x0+28,316),label,font=bold(34),fill=navy)
        draw.text((x0+28,369),f"{value:.1f} bp",font=bold(62),fill=navy)
        bb,ff=colors[bucket]
        draw.rounded_rectangle((x1-177,387,x1-24,446),radius=14,fill=bb)
        draw.text((x1-147,399),bucket,font=bold(33),fill=ff)
        draw.text((x0+28,457),f"전일 {signed(change)}bp · 5일 {trend}",
                  font=font(27),fill=gray)
    cp,_=spread_bucket("cp_cd",latest["cp_cd"])
    aa,_=spread_bucket("credit",latest["credit"])
    card(60,"CP–CD · 기업 단기자금",latest["cp_cd"],cp,
         latest["cp_cd"]-prev["cp_cd"],d["cp"][0])
    card(737,"AA- 회사채 · 국고채",latest["credit"],aa,
         latest["credit"]-prev["credit"],d["aa"][0])
    def panel(top,metric,title,bucket,trend,color,bands):
        draw.rounded_rectangle((60,top,1380,top+438),radius=19,fill="#FFFFFF")
        draw.text((90,top+25),title,font=bold(35),fill=navy)
        fill,fg=colors[bucket]
        draw.rounded_rectangle((1020,top+28,1343,top+84),radius=12,fill=fill)
        draw.text((1040,top+40),f"{bucket} · {trend}",font=bold(27),fill=fg)
        hist=rows[-15:]
        vals=[float(z[metric]) for z in hist]
        lower,upper=min(vals),max(vals)
        pad=max(1.5,(upper-lower)*0.3)
        lower-=pad;upper+=pad
        xL,xR=153,1310; yT,yB=top+105,top+283
        def to_y(v): return round(yB-(v-lower)/(upper-lower)*(yB-yT))
        for k in range(3):
            v=lower+(upper-lower)*k/2
            y=to_y(v)
            draw.line((xL,y,xR,y),fill="#DDE6F0",width=2)
            draw.text((81,y-17),f"{v:.1f}",font=font(22),fill=gray)
        pts=[(round(xL+i*(xR-xL)/max(1,len(vals)-1)),to_y(v))
             for i,v in enumerate(vals)]
        if len(pts)>1: draw.line(pts,fill=color,width=7)
        for x,y in pts[:-1]: draw.ellipse((x-5,y-5,x+5,y+5),fill=color)
        x,y=pts[-1]
        draw.ellipse((x-13,y-13,x+13,y+13),outline=color,fill="#FFFFFF",width=6)
        for xpos,at in ((xL,hist[0]),(xR-100,hist[-1])):
            val=at["date"]
            draw.text((xpos,yB+14),val[4:6]+"/"+val[6:8],font=font(23),fill=gray)
        seg=(xR-xL)/5
        for idx,(name,range_txt) in enumerate(zip(LEVELS,bands)):
            l=round(xL+idx*seg); r=round(xL+(idx+1)*seg)-5
            bb,ff=colors[name]
            draw.rounded_rectangle((l,top+345,r,top+396),radius=9,fill=bb,
                                   outline=ff if name==bucket else None,
                                   width=5 if name==bucket else 1)
            draw.text((l+9,top+356),name+" "+range_txt,font=bold(21),fill=ff)
        draw.text((89,top+407),"위험 구간은 별도 기준 · 추세선 세로축은 최근 값에 맞춰 표시",
                  font=font(20),fill=gray)
    panel(523,"cp_cd","① CP–CD 금리차 (bp)",cp,d["cp"][0],"#C56A19",
          ["30미만","30~50","50~70","70~100","100이상"])
    panel(977,"credit","② AA- 회사채 금리차 (bp)",aa,d["aa"][0],"#226BB2",
          ["70미만","70~80","80~90","90~120","120이상"])
    draw.rounded_rectangle((61,1437,1380,1555),radius=18,fill="#E7EDF5")
    draw.text((90,1458),
              f"5영업일: 단기 {d['cp'][0]} ({signed(d['cp_delta'])}bp) · "
              f"회사채 {d['aa'][0]} ({signed(d['aa_delta'])}bp)",
              font=bold(28),fill=navy)
    draw.text((90,1508),"위험 단계는 자체 감시 기준이며 금융당국 공식 위기등급이 아님",
              font=font(25),fill=gray)
    path=pathlib.Path(target)
    path.parent.mkdir(parents=True,exist_ok=True)
    pic.save(path,format="PNG",optimize=True)
    if not 100<path.stat().st_size<=9_000_000:
        raise ValueError("차트 이미지 크기 이상")
    return path

def render(rows,decision,now,sample=False,daily=False):
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
        f"<b>국내 신용금리 {'일일 보고' if daily else '경보'} | {applied}</b>",
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

def telegram(url,params=None,photo=None):
    """1개의 sendPhoto 응답으로 이미지와 한국어 설명을 동시에 확인."""
    if photo is None:
        req=urllib.request.Request(url,method="POST" if params else "GET",
             data=urllib.parse.urlencode(params).encode() if params else None)
    else:
        if not isinstance(photo,bytes) or not photo.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG가 아닌 파일은 사진으로 전송할 수 없음")
        boundary="----CreditWatch"+os.urandom(12).hex()
        chunks=[]
        for key,value in (params or {}).items():
            chunks.append((f'--{boundary}\r\n'
                           f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                           f'{value}\r\n').encode("utf-8"))
        chunks.append((f'--{boundary}\r\n'
                       'Content-Disposition: form-data; name="photo"; filename="credit_spread.png"\r\n'
                       'Content-Type: image/png\r\n\r\n').encode("utf-8"))
        chunks.append(photo)
        chunks.append(("\r\n--"+boundary+"--\r\n").encode("utf-8"))
        req=urllib.request.Request(
            url,method="POST",data=b"".join(chunks),
            headers={"Content-Type":"multipart/form-data; boundary="+boundary})
    try:
        with urllib.request.urlopen(req,timeout=35) as response:
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
        raise RuntimeError("검증된 신규 경보 또는 정기 보고 없음")
    pending=None
    if not sample:
        pending=json.loads(PENDING.read_text(encoding="utf-8"))
        if pending.get("_pending_message_kind") not in ("alert","daily"):
            raise RuntimeError("검증된 보고 종류 없음: Telegram 전송 중단")
        if not isinstance(pending.get("_pending_daily_due"),bool):
            raise RuntimeError("정기 보고 중복 방지 상태 누락")
        if pending.get("last_sent_kst_date")!=delivery_kst_date(now):
            raise RuntimeError("자정 경과로 발송 예정일 변경: 재조회 후 재판정 필요")
    who=telegram(f"https://api.telegram.org/bot{token}/getMe")
    got=str((who.get("result") or {}).get("username") or "")
    if who.get("ok") is not True or got.lower()!=BOT.lower():
        raise RuntimeError(f"잘못된 텔레그램 봇: expected @{BOT} got @{got or 'unknown'}")
    message=ALERT.read_text(encoding="utf-8").strip()
    if not message or len(telegram_plaintext(message))>1024:
        raise ValueError("Telegram 사진 설명 1024자 초과 또는 내용 오류")
    if not CHART.exists(): raise RuntimeError("한글 추세 차트 PNG가 없어 전송 중단")
    photo=CHART.read_bytes()
    if not photo.startswith(b"\x89PNG\r\n\x1a\n") or not 100<len(photo)<=9_000_000:
        raise ValueError("차트 PNG 포맷·크기 이상")
    expected_text=telegram_plaintext(message)
    reply=telegram(f"https://api.telegram.org/bot{token}/sendPhoto",
                   {"chat_id":chat,"caption":message,"parse_mode":"HTML",
                    "show_caption_above_media":"true"},photo=photo)
    obj=reply.get("result") or {}
    mid=obj.get("message_id")
    if reply.get("ok") is not True or not isinstance(mid,int) or mid<1:
        raise RuntimeError("Telegram 사진 메시지 수신 확인 실패")
    if obj.get("caption")!=expected_text:
        raise RuntimeError("Telegram 사진 설명 원문과 응답 불일치")
    if not isinstance(obj.get("photo"),list) or not any(
            isinstance(p,dict) and p.get("file_id") for p in obj["photo"]):
        raise RuntimeError("Telegram 사진 실제 첨부 확인 실패")
    if re.fullmatch(r"-?\d+",chat) and str((obj.get("chat") or {}).get("id"))!=chat:
        raise RuntimeError("Telegram 사진 수신 대화방 불일치")
    receipt={"status":"confirmed","bot_username":got,"message_id":mid,
             "delivered_at_kst":now.isoformat(timespec="seconds"),
             "message_sha256":hashlib.sha256(message.encode()).hexdigest(),
             "chart_sha256":hashlib.sha256(photo).hexdigest(),"photo_verified":True,
             "run_id":os.environ.get("GITHUB_RUN_ID","local")}
    ACK.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not sample:
        kind=pending.pop("_pending_message_kind")
        daily_due=pending.pop("_pending_daily_due")
        pending["last_delivery_receipt"]=receipt
        if kind=="alert": pending["delivery_receipt"]=receipt
        if daily_due: pending["last_daily_report_receipt"]=receipt
        PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"telegram_delivery_confirmed=true full_text_verified=true sample={sample} bot=@{got} message_id={mid}")

def watch(now):
    ALERT.parent.mkdir(parents=True,exist_ok=True)
    for p in (ALERT,CHART,PENDING,ACK,HEALTH_PENDING): p.unlink(missing_ok=True)
    key=os.environ.get("ECOS_API_KEY","").strip()
    if not key: raise RuntimeError("기존 ECOS_API_KEY 보안 설정 누락")
    values,codes=fetch_rates(key,now)
    rows=aligned(values,now)
    state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    action=decide(rows,state)
    kind,daily_due=delivery_plan(rows,state,action,now)
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
        "알림 상태: "+("형식 시험(실제 새 경보 아님)" if sample else ("신규 경보" if kind=="alert" else ("공식 기준일 신규 일일 보고" if kind=="daily" else "중복 기준일·신규 경보 없음"))),
        "원천: "+SOURCE])+"\n",encoding="utf-8")
    print(f"credit_source_valid=true day={latest['date']} cp_cd={latest['cp_cd']} credit={latest['credit']} alert={action['send']} daily_due={daily_due} message_kind={kind}")
    if kind or sample or preview:
        ALERT.write_text(photo_caption(rows,action,now,sample=sample,daily=(kind=="daily"))+"\n",encoding="utf-8")
        render_chart(rows,action,now,CHART)
    if kind and not sample and not preview:
        new=pending_delivery_state(state,action,latest,now,kind,daily_due)
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

#!/usr/bin/env python3
import os, re, json, hashlib, html
from pathlib import Path
from datetime import datetime, timezone, timedelta
from io import StringIO

import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT=Path.cwd()
OUT=ROOT/"out"; DATA=ROOT/"data"
OUT.mkdir(exist_ok=True); DATA.mkdir(exist_ok=True)
ALERT=OUT/"us_positioning_alert.html"
STATUS=OUT/"us_positioning_status.md"
PENDING=OUT/"us_positioning_pending_state.json"
STATE=DATA/"us_positioning_state.json"
for p in (ALERT,STATUS,PENDING):
    try:p.unlink()
    except FileNotFoundError:pass

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
S=requests.Session(); S.headers.update({"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"})

CFTC="https://www.cftc.gov/dea/futures/financial_lf.htm"
CBOE="https://www.cboe.com/us/options/market_statistics/market/"
SOX="https://indexes.nasdaq.com/Index/History/SOX"

def get(url,timeout=35):
    r=S.get(url,timeout=timeout,allow_redirects=True); r.raise_for_status(); return r

def browser_html(url):
    exe=next((p for p in ["/usr/bin/google-chrome","/usr/bin/google-chrome-stable","/usr/bin/chromium","/usr/bin/chromium-browser"] if os.path.exists(p)),None)
    if not exe: raise RuntimeError("system Chrome/Chromium not found")
    with sync_playwright() as pw:
        b=pw.chromium.launch(executable_path=exe,headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        page=b.new_page(user_agent=UA,locale="en-US")
        page.goto(url,wait_until="domcontentloaded",timeout=60000)
        try: page.wait_for_load_state("networkidle",timeout=12000)
        except Exception: pass
        page.wait_for_timeout(1000)
        h=page.content(); b.close(); return h

def load_state():
    try:return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:return {"seen":{},"values":{}}

def fp(core):
    return hashlib.sha256(json.dumps(core,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def parse_num(x):
    if x is None:return None
    s=str(x).replace(",","").replace("%","").strip()
    m=re.search(r"[-+]?\d+(?:\.\d+)?",s)
    return float(m.group()) if m else None

def fetch_fx():
    key=(os.getenv("ECOS_API_KEY") or "").strip()
    if not key:return None
    now=datetime.now(timezone(timedelta(hours=9))).date()
    st=(now-timedelta(days=12)).strftime("%Y%m%d"); en=now.strftime("%Y%m%d")
    url=f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/731Y001/D/{st}/{en}/0000001"
    try:
        rows=((get(url).json().get("StatisticSearch") or {}).get("row") or [])
        vals=[(str(r.get("TIME")),parse_num(r.get("DATA_VALUE"))) for r in rows if parse_num(r.get("DATA_VALUE")) is not None]
        vals.sort()
        if vals:return {"date":vals[-1][0],"usdkrw":vals[-1][1]}
    except Exception: pass
    return None

def parse_cftc():
    text=get(CFTC).text
    plain=BeautifulSoup(text,"html.parser").get_text("\n")
    m=re.search(r"Positions as of ([A-Za-z]+ \d{1,2}, 20\d{2})",plain)
    period=m.group(1) if m else "latest"
    block_m=re.search(r"NASDAQ-100 Consolidated.*?Positions\s+([\s\S]*?)Changes from:",plain,re.I)
    if not block_m: raise RuntimeError("NASDAQ-100 CFTC block not found")
    nums=[int(x.replace(",","")) for x in re.findall(r"\b\d{1,3}(?:,\d{3})+\b",block_m.group(1))]
    if len(nums)<15: raise RuntimeError("NASDAQ-100 CFTC positions parse failed")
    # after open interest, 15 position fields: dealer3, asset3, leveraged3, other3, nonreportable2
    # identify open interest as first large integer, then take following 15.
    oi=nums[0]; pos=nums[1:16]
    asset_long,asset_short=pos[3],pos[4]
    lev_long,lev_short=pos[6],pos[7]
    asset_net=asset_long-asset_short; lev_net=lev_long-lev_short

    ch_m=re.search(r"Changes from:.*?\n([\s\S]*?)Percent of Open Interest",plain,re.I)
    ch=[]
    if ch_m:
        ch=[int(x.replace(",","")) for x in re.findall(r"[-+]?\d{1,3}(?:,\d{3})+",ch_m.group(1))]
    metrics={"open_interest":oi,"asset_long":asset_long,"asset_short":asset_short,"asset_net":asset_net,
             "lev_long":lev_long,"lev_short":lev_short,"lev_net":lev_net}
    if len(ch)>=9:
        metrics.update({"asset_long_wow":ch[3],"asset_short_wow":ch[4],"lev_long_wow":ch[6],"lev_short_wow":ch[7],
                        "asset_net_wow":ch[3]-ch[4],"lev_net_wow":ch[6]-ch[7]})
    core={"source":"CFTC","kind":"cot","period":period,"metrics":metrics}
    return {**core,"url":CFTC,"fingerprint":fp(core)}

def parse_cboe():
    h=browser_html(CBOE)
    tables=pd.read_html(StringIO(h))
    target=None
    for t in tables:
        flat=" ".join(map(str,t.astype(str).values.flatten()))
        if "P/C RATIO" in flat and "CALLS" in flat and "PUTS" in flat:
            target=t; break
    if target is None: raise RuntimeError("Cboe market statistics table not found")
    # Flatten headers and use last row from Total table.
    target.columns=[str(c[-1] if isinstance(c,tuple) else c).strip() for c in target.columns]
    last=target.dropna(how="all").iloc[-1]
    cols={c.upper():c for c in target.columns}
    ratio=parse_num(last[cols.get("P/C RATIO")])
    calls=parse_num(last[cols.get("CALLS")]); puts=parse_num(last[cols.get("PUTS")])
    txt=BeautifulSoup(h,"html.parser").get_text(" ",strip=True)
    dm=re.search(r"Market Statistics for ([A-Za-z]+,? [A-Za-z]+ \d{1,2}, 20\d{2})",txt)
    period=dm.group(1) if dm else datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d")
    metrics={"total_pc_ratio":ratio,"calls":calls,"puts":puts}
    core={"source":"Cboe","kind":"options","period":period,"metrics":metrics}
    return {**core,"url":CBOE,"fingerprint":fp(core)}

def parse_sox():
    h=browser_html(SOX)
    txt=BeautifulSoup(h,"html.parser").get_text(" ",strip=True)
    m=re.search(r"DATA AS OF\s+(\d{1,2}/\d{1,2}/20\d{2})\s+([\d,]+\.\d+)\s+([+-]?[\d,]+\.\d+)\s+([+-]?\d+(?:\.\d+)?)%",txt,re.I)
    if not m:
        raise RuntimeError("SOX headline parse failed")
    period=m.group(1); value=float(m.group(2).replace(",","")); chg=float(m.group(3).replace(",","")); pct=float(m.group(4))
    # try performance table for recent dates
    tables=pd.read_html(StringIO(h))
    series=[]
    for t in tables:
        flat=" ".join(map(str,t.astype(str).values.flatten()))
        if "Trade Date" in flat and "Index Value" in flat:
            tt=t.copy(); tt.columns=[str(c[-1] if isinstance(c,tuple) else c).strip() for c in tt.columns]
            for _,r in tt.head(10).iterrows():
                d=str(r.get("Trade Date","")).strip(); v=parse_num(r.get("Index Value"))
                if d and v is not None: series.append((d,v))
            if series: break
    metrics={"value":value,"net_change":chg,"pct":pct}
    if len(series)>=2:
        metrics["d1_pct"]=(series[0][1]/series[1][1]-1)*100
    if len(series)>=4:
        metrics["d3_pct"]=(series[0][1]/series[3][1]-1)*100
    if len(series)>=6:
        metrics["d5_pct"]=(series[0][1]/series[5][1]-1)*100
    core={"source":"Nasdaq SOX","kind":"sox","period":period,"metrics":metrics}
    return {**core,"url":SOX,"fingerprint":fp(core)}

def pct_word(x):
    if x is None:return "확인 대기"
    return f"{x:+.2f}%"

def explain(cftc,cboe,sox):
    lines=[]; summary=[]
    if sox:
        m=sox["metrics"]
        lines.append(f"• 반도체(SOX): {m['value']:,.2f} / 당일 {m['pct']:+.2f}%"
                     + (f" / 5거래일 {m.get('d5_pct'):+.2f}%" if m.get("d5_pct") is not None else ""))
        summary.append("SOX 강세" if m["pct"]>0 else "SOX 약세" if m["pct"]<0 else "SOX 보합")
    if cftc:
        m=cftc["metrics"]
        aw=m.get("asset_net_wow"); lw=m.get("lev_net_wow")
        lines.append(f"• 기관(Asset Manager) 나스닥100 순포지션 {m['asset_net']:+,}계약"
                     + (f" / 주간 {aw:+,}" if aw is not None else ""))
        lines.append(f"• 헤지펀드성(Leveraged Funds) 나스닥100 순포지션 {m['lev_net']:+,}계약"
                     + (f" / 주간 {lw:+,}" if lw is not None else ""))
        if lw is not None:
            summary.append("헤지펀드 순포지션 개선" if lw>0 else "헤지펀드 순포지션 악화" if lw<0 else "헤지펀드 변화 제한")
    if cboe:
        r=cboe["metrics"].get("total_pc_ratio")
        lines.append(f"• Cboe 전체 풋/콜 비율 {r:.2f}" if r is not None else "• Cboe 풋/콜 비율 확인 대기")
        if r is not None:
            summary.append("콜 우위 성향" if r<0.8 else "중립권" if r<=1.0 else "풋 우위 성향")
    # Easy directional synthesis
    sox_up=sox and sox["metrics"].get("pct",0)>0
    lev_up=cftc and cftc["metrics"].get("lev_net_wow") is not None and cftc["metrics"]["lev_net_wow"]>0
    pc_low=cboe and cboe["metrics"].get("total_pc_ratio") is not None and cboe["metrics"]["total_pc_ratio"]<0.8
    if sox_up and lev_up and pc_low:
        overall="반도체 가격·헤지펀드 포지션·옵션 수요가 모두 상방 쪽으로 맞물림 → 상방 추격 위험 확대"
    elif sox_up and lev_up:
        overall="SOX가 오르고 헤지펀드 나스닥100 순포지션도 개선 → 가격 상승을 포지션이 따라붙는 흐름"
    elif sox_up and not lev_up:
        overall="SOX는 강하지만 헤지펀드 포지션 확인이 덜 따라옴 → 아직 숏커버·만기수급 가능성 점검 필요"
    elif not sox_up and lev_up:
        overall="가격은 약한데 헤지펀드 포지션은 개선 → 선행 포지셔닝인지 실패 신호인지 다음 거래일 확인 필요"
    else:
        overall="가격·포지션·옵션 방향이 한쪽으로 정렬되지 않아 추세 확정 전"
    return lines,overall

state=load_state(); results=[]; errors=[]
for name,fn in [("CFTC",parse_cftc),("Cboe",parse_cboe),("SOX",parse_sox)]:
    try: results.append(fn())
    except Exception as e: errors.append(f"{name}: {type(e).__name__}: {e}")

updates=[]
for x in results:
    key=f"{x['source']}|{x['kind']}"
    if state.get("seen",{}).get(key)!=x["fingerprint"]: updates.append(x)

cftc=next((x for x in results if x["kind"]=="cot"),None)
cboe=next((x for x in results if x["kind"]=="options"),None)
sox=next((x for x in results if x["kind"]=="sox"),None)
lines,overall=explain(cftc,cboe,sox)

STATUS.write_text("\n".join([
    "# US Positioning Watch","",
    f"- parsed sources: {len(results)}",f"- updates: {len(updates)}",
    *[f"- {x['source']} {x['period']} {x['fingerprint'][:12]}" for x in results],
    *[f"- error: {e}" for e in errors]
])+"\n",encoding="utf-8")

force=(os.getenv("FORCE_SEND") or "").lower() in ("1","true","yes")
if updates or force:
    body=["🇺🇸 <b>[미국 상방 포지셔닝 추적 | 신규 변화]</b>","",
          "<b>한눈에 보기</b>",*lines,
          f"→ <b>종합</b>: {html.escape(overall)}","",
          "<b>무엇을 의미하나</b>",
          "• SOX↑ + 헤지펀드 순포지션 개선 → 상승을 실제 포지션이 따라붙는지 확인",
          "• 풋/콜 비율 하락 → 상대적으로 콜 수요가 강해지는 방향",
          "• 세 지표가 동시에 상방으로 정렬될 때만 상방 추격 신호를 강하게 판정",
          "",
          "<b>이번에 실제로 바뀐 값</b>"]
    for x in (updates if updates else results):
        body.append(f"• {html.escape(x['source'])} | {html.escape(str(x['period']))} | <a href=\"{html.escape(x['url'],quote=True)}\">원천</a>")
    if errors:
        body+=["","<b>확인 대기</b>"]
        for e in errors: body.append("• "+html.escape(e.split(":",1)[0])+" 최신값 자동 재확인 중")
    ALERT.write_text("\n".join(body)+"\n",encoding="utf-8")
    ns=state; ns.setdefault("seen",{}); ns.setdefault("values",{})
    for x in results:
        key=f"{x['source']}|{x['kind']}"; ns["seen"][key]=x["fingerprint"]; ns["values"][key]=x
    ns["updated_at_kst"]=datetime.now(timezone(timedelta(hours=9))).isoformat()
    PENDING.write_text(json.dumps(ns,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"us_positioning_alert_ready=true updates={len(updates)}")
else:
    print("us_positioning_alert_ready=false unchanged=true")

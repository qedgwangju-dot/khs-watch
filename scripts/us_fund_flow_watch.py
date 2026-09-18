#!/usr/bin/env python3
import os, re, json, hashlib, html, time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
import pandas as pd
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

ROOT = Path.cwd()
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)
ALERT = OUT / "us_fund_flow_alert.html"
STATUS = OUT / "us_fund_flow_status.md"
PENDING = OUT / "us_fund_flow_pending_state.json"
STATE = DATA / "us_fund_flow_state.json"

for p in (ALERT, STATUS, PENDING):
    try: p.unlink()
    except FileNotFoundError: pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

ICI_COMBINED = "https://www.ici.org/research/stats/combined_flows"
ICI_MMF = "https://www.ici.org/research/stats/mmf"
FINRA_MARGIN = "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"
REUTERS_Q_BofA = 'site:reuters.com BofA "US stocks" "money market" investors'
REUTERS_Q_LIPPER = 'site:reuters.com LSEG Lipper "U.S. equity funds" "money market funds"'

def get(url, timeout=35):
    r = S.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r

def load_state():
    try: return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception: return {"seen": {}, "values": {}}

def parse_num(x):
    if x is None: return None
    if isinstance(x, (int, float)) and pd.notna(x): return float(x)
    s = str(x).replace(",", "").replace("$", "").replace("%", "").strip()
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None

def clean_text(x):
    return re.sub(r"\s+", " ", BeautifulSoup(str(x), "html.parser").get_text(" ", strip=True)).strip()

def fetch_fx():
    key = (os.getenv("ECOS_API_KEY") or "").strip()
    if not key: return None
    today = datetime.now(timezone(timedelta(hours=9))).date()
    start = (today - timedelta(days=12)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/731Y001/D/{start}/{end}/0000001"
    try:
        j = get(url).json()
        rows = (j.get("StatisticSearch") or {}).get("row") or []
        vals = []
        for row in rows:
            v = parse_num(row.get("DATA_VALUE"))
            t = str(row.get("TIME") or "")
            if v and t: vals.append((t, v))
        if vals:
            vals.sort()
            return {"date": vals[-1][0], "usdkrw": vals[-1][1]}
    except Exception:
        pass
    return None

def krw_trillion(bn_usd, fx):
    if bn_usd is None or not fx: return None
    return bn_usd * fx["usdkrw"] / 1000.0

def fmt_bn(x):
    if x is None: return "확인 불가"
    return f"{x:+,.2f}억달러".replace("억달러", "0억달러") if False else f"{x:+,.2f}B달러"

def fmt_usd_bn_kr(x, fx):
    if x is None: return "확인 불가"
    base = f"{x:+,.2f}B달러"
    if fx:
        kr = krw_trillion(x, fx)
        base += f"(약 {kr:+,.2f}조원, USD/KRW {fx['usdkrw']:,.2f})"
    return base

def parse_ici_combined():
    r = get(ICI_COMBINED)
    text = clean_text(r.text)
    pub = None
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}", text)
    if m: pub = m.group(0)
    tables = pd.read_html(r.text)
    target = None
    for t in tables:
        flat = " ".join(map(str, t.astype(str).values.flatten()))
        if "Domestic" in flat and "Equity" in flat:
            target = t.copy(); break
    if target is None: raise RuntimeError("ICI combined flows table not found")
    # Normalize first column as category, retain date columns.
    target.columns = [str(c[1] if isinstance(c, tuple) else c).strip() for c in target.columns]
    first = target.columns[0]
    target[first] = target[first].astype(str).str.strip()
    date_cols = [c for c in target.columns[1:] if re.search(r"\d{1,2}/\d{1,2}/\d{4}", c)]
    if not date_cols:
        # fallback: any non-first numeric-ish columns
        date_cols = list(target.columns[1:])[:5]
    cur_col = date_cols[0]
    def rowval(label):
        hit = target[target[first].str.fullmatch(label, case=False, na=False)]
        if hit.empty:
            hit = target[target[first].str.contains(label, case=False, na=False)]
        if hit.empty: return None
        return parse_num(hit.iloc[0][cur_col])
    current = {
        "equity": rowval("Equity"),
        "domestic": rowval("Domestic"),
        "world": rowval("World"),
        "bond": rowval("Bond"),
        "hybrid": rowval("Hybrid"),
    }
    # ICI tables are millions USD.
    current = {k: (v/1000.0 if v is not None else None) for k,v in current.items()}
    four_week_domestic = None
    vals=[]
    for c in date_cols[:4]:
        hit = target[target[first].str.fullmatch("Domestic", case=False, na=False)]
        if not hit.empty:
            v=parse_num(hit.iloc[0][c])
            if v is not None: vals.append(v/1000.0)
    if vals: four_week_domestic=sum(vals)
    period = cur_col
    key = f"ici_combined:{period}:{current}"
    return {
        "source":"ICI", "kind":"combined", "period":period, "published":pub,
        "url":ICI_COMBINED, "metrics":current, "domestic_4w":four_week_domestic,
        "fingerprint":hashlib.sha256(key.encode()).hexdigest()
    }

def parse_ici_mmf():
    r = get(ICI_MMF)
    text = clean_text(r.text)
    # latest release wording
    pat = re.compile(
        r"Total money market fund assets.*?(increased|decreased) by \$([\d.]+) billion to \$([\d.]+) trillion for the week ended Wednesday,? ([A-Za-z]+ \d{1,2})",
        re.I)
    m=pat.search(text)
    if not m:
        # Site can surface current release deeper; search main research page for latest release URL is not enough, so fail closed.
        raise RuntimeError("ICI MMF latest release values not found")
    direction = 1 if m.group(1).lower()=="increased" else -1
    chg = direction*float(m.group(2))
    assets = float(m.group(3))
    period = m.group(4)
    pubm = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}", text)
    pub=pubm.group(0) if pubm else None
    key=f"ici_mmf:{period}:{assets}:{chg}"
    return {
        "source":"ICI", "kind":"mmf", "period":period, "published":pub, "url":ICI_MMF,
        "metrics":{"assets_trillion":assets, "weekly_change_bn":chg},
        "fingerprint":hashlib.sha256(key.encode()).hexdigest()
    }

def parse_finra():
    r=get(FINRA_MARGIN)
    tables=pd.read_html(r.text)
    t=None
    for x in tables:
        if any("Debit Balances" in str(c) for c in x.columns):
            t=x.copy(); break
    if t is None: raise RuntimeError("FINRA margin table not found")
    cols=[str(c) for c in t.columns]
    t.columns=cols
    t=t.dropna(how="all")
    latest=t.iloc[0]
    prev=t.iloc[1] if len(t)>1 else None
    period=str(latest.iloc[0])
    debit=parse_num(latest.iloc[1]); cash=parse_num(latest.iloc[2]); margin_credit=parse_num(latest.iloc[3])
    prev_debit=parse_num(prev.iloc[1]) if prev is not None else None
    metrics={
        "margin_debt_bn": debit/1000.0 if debit is not None else None,
        "cash_free_bn": cash/1000.0 if cash is not None else None,
        "margin_free_bn": margin_credit/1000.0 if margin_credit is not None else None,
        "margin_debt_mom_bn": (debit-prev_debit)/1000.0 if debit is not None and prev_debit is not None else None,
    }
    key=f"finra:{period}:{metrics}"
    return {"source":"FINRA","kind":"margin","period":period,"published":None,"url":FINRA_MARGIN,
            "metrics":metrics,"fingerprint":hashlib.sha256(key.encode()).hexdigest()}

def news_rss(query):
    url="https://news.google.com/rss/search?q="+quote(query)+"&hl=en-US&gl=US&ceid=US:en"
    root=ET.fromstring(get(url).content)
    out=[]
    for item in root.findall(".//item")[:20]:
        title=(item.findtext("title") or "").strip()
        link=(item.findtext("link") or "").strip()
        pub=(item.findtext("pubDate") or "").strip()
        desc=clean_text(item.findtext("description") or "")
        out.append({"title":title,"link":link,"pub":pub,"desc":desc})
    return out

def extract_article_body(url):
    try:
        r=get(url, timeout=25)
        final=r.url
        soup=BeautifulSoup(r.text,"html.parser")
        bodies=[]
        for s in soup.find_all("script", attrs={"type":"application/ld+json"}):
            try:
                j=json.loads(s.string or "")
                stack=j if isinstance(j,list) else [j]
                for o in stack:
                    if isinstance(o,dict) and o.get("articleBody"): bodies.append(str(o["articleBody"]))
                    if isinstance(o,dict) and isinstance(o.get("@graph"),list):
                        for q in o["@graph"]:
                            if isinstance(q,dict) and q.get("articleBody"): bodies.append(str(q["articleBody"]))
            except Exception: pass
        text=max(bodies,key=len) if bodies else clean_text(r.text)
        return final, text
    except Exception:
        return url, ""

def signed_flow(text, anchor_patterns):
    # Search sentences containing anchors and billion amounts, infer in/out wording.
    sentences=re.split(r"(?<=[.!?])\s+", text)
    for sent in sentences:
        low=sent.lower()
        if all(re.search(p, low, re.I) for p in anchor_patterns):
            m=re.search(r"\$([\d.]+)\s*billion", sent, re.I)
            if m:
                v=float(m.group(1))
                if re.search(r"outflow|outflows|withdrawn|pulled|redemption|redemptions", low): v=-v
                elif re.search(r"inflow|inflows|received|attracted|bought|poured", low): v=abs(v)
                return v, sent[:600]
    return None, None

def parse_reuters(kind):
    q=REUTERS_Q_BofA if kind=="bofa" else REUTERS_Q_LIPPER
    items=news_rss(q)
    cutoff=datetime.now(timezone.utc)-timedelta(days=10)
    for it in items:
        if "Reuters" not in it["title"] and "reuters" not in it["desc"].lower(): continue
        if kind=="bofa" and "bofa" not in (it["title"]+" "+it["desc"]).lower() and "bank of america" not in (it["title"]+" "+it["desc"]).lower(): continue
        if kind=="lipper" and "lipper" not in (it["title"]+" "+it["desc"]).lower() and "global equity fund" not in it["title"].lower(): continue
        final, body=extract_article_body(it["link"])
        combined=(it["title"]+" "+it["desc"]+" "+body)
        if kind=="bofa":
            # Must explicitly identify BofA/EPFR in body or title.
            if not re.search(r"Bank of America|BofA|EPFR", combined, re.I): continue
            us, ussent=signed_flow(combined,[r"u\.?s\.?|united states",r"equity|stock"])
            mmf, mmfsent=signed_flow(combined,[r"money market"])
            glob, glsent=signed_flow(combined,[r"global",r"equity|stock"])
            if us is None and mmf is None: continue
            metrics={"us_equity_bn":us,"global_equity_bn":glob,"mmf_bn":mmf}
        else:
            if not re.search(r"LSEG|Lipper", combined, re.I): continue
            us, ussent=signed_flow(combined,[r"u\.?s\.?|united states",r"equity fund"])
            mmf, mmfsent=signed_flow(combined,[r"money market"])
            glob, glsent=signed_flow(combined,[r"global equity"])
            if us is None and mmf is None and glob is None: continue
            metrics={"us_equity_bn":us,"global_equity_bn":glob,"mmf_bn":mmf}
        article_key=final or it["link"]
        fp=hashlib.sha256((kind+article_key+json.dumps(metrics,sort_keys=True)).encode()).hexdigest()
        return {"source":"BofA/EPFR via Reuters" if kind=="bofa" else "LSEG Lipper via Reuters",
                "kind":kind,"period":it["pub"],"published":it["pub"],"url":article_key,
                "title":it["title"],"metrics":metrics,"fingerprint":fp}
    return None

def flow_direction(us, mmf):
    if us is None or mmf is None:
        return "주식과 MMF를 같은 기준으로 동시에 확인할 수 없어 방향 판정 보류"
    if us>0 and mmf<0:
        return "미국 주식 유입 + MMF 유출 → 현금성 주차자금에서 위험자산으로 기울 가능성이 강화된 조합"
    if us<0 and mmf>0:
        return "미국 주식 유출 + MMF 유입 → 위험자산 축소·현금성 주차 강화 조합"
    if us>0 and mmf>0:
        return "미국 주식과 MMF가 동반 유입 → 유동성 총량 확대 가능성은 있지만 단순 위험선호 이동으로 단정 불가"
    if us<0 and mmf<0:
        return "미국 주식과 MMF가 동반 유출 → 채권·해외자산·결제 등 다른 목적지 확인 필요"
    return "방향 혼재"

def source_block(x, fx):
    m=x["metrics"]
    lines=[]
    if x["kind"]=="combined":
        lines.append(f"• 미국 국내주식형(뮤추얼펀드+ETF) {fmt_usd_bn_kr(m.get('domestic'),fx)}")
        lines.append(f"• 세계주식형 {fmt_usd_bn_kr(m.get('world'),fx)} / 채권형 {fmt_usd_bn_kr(m.get('bond'),fx)}")
        if x.get("domestic_4w") is not None:
            lines.append(f"• 미국 국내주식형 최근 4주 합계 {fmt_usd_bn_kr(x['domestic_4w'],fx)}")
    elif x["kind"]=="mmf":
        ch=m["weekly_change_bn"]; a=m["assets_trillion"]
        krtxt=""
        if fx:
            kr=krw_trillion(ch,fx); krtxt=f"(약 {kr:+,.2f}조원)"
        lines.append(f"• MMF(단기 현금 주차성 펀드) 총자산 {a:,.2f}조달러 / 주간 {ch:+,.2f}B달러 {krtxt}")
    elif x["kind"]=="margin":
        lines.append(f"• 마진부채(주식담보 신용거래 차입) {m['margin_debt_bn']:,.1f}B달러 / 전월 {m['margin_debt_mom_bn']:+,.1f}B달러")
        lines.append(f"• 현금계좌 가용현금 {m['cash_free_bn']:,.1f}B달러 / 마진계좌 가용현금 {m['margin_free_bn']:,.1f}B달러")
    else:
        lines.append(f"• 미국 주식형 {fmt_usd_bn_kr(m.get('us_equity_bn'),fx)}")
        if m.get("global_equity_bn") is not None: lines.append(f"• 글로벌 주식형 {fmt_usd_bn_kr(m.get('global_equity_bn'),fx)}")
        if m.get("mmf_bn") is not None: lines.append(f"• MMF {fmt_usd_bn_kr(m.get('mmf_bn'),fx)}")
        lines.append("• 판정: "+flow_direction(m.get("us_equity_bn"),m.get("mmf_bn")))
    return "\n".join(lines)

state=load_state()
fx=fetch_fx()
results=[]; errors=[]
for name,fn in [
    ("ICI 장기펀드+ETF",parse_ici_combined),
    ("ICI MMF",parse_ici_mmf),
    ("FINRA 마진",parse_finra),
    ("BofA/EPFR Reuters",lambda:parse_reuters("bofa")),
    ("LSEG Lipper Reuters",lambda:parse_reuters("lipper")),
]:
    try:
        x=fn()
        if x: results.append(x)
    except Exception as e:
        errors.append(f"{name}: {type(e).__name__}: {e}")

updates=[]
for x in results:
    k=f"{x['source']}|{x['kind']}"
    old=state.get("seen",{}).get(k)
    if old != x["fingerprint"]:
        updates.append(x)

# Cross-source comparison: never average unlike universes.
bofa=next((x for x in results if x["kind"]=="bofa"),None)
lipper=next((x for x in results if x["kind"]=="lipper"),None)
ici=next((x for x in results if x["kind"]=="combined"),None)
cross=[]
if bofa and ici:
    bu=bofa["metrics"].get("us_equity_bn"); iu=ici["metrics"].get("domestic")
    if bu is not None and iu is not None and bu*iu<0:
        cross.append("BofA/EPFR와 ICI의 미국 주식 흐름 방향이 반대입니다. 모집단·분류 차이로 보고 합산하지 않습니다.")
if bofa and lipper:
    bu=bofa["metrics"].get("us_equity_bn"); lu=lipper["metrics"].get("us_equity_bn")
    if bu is not None and lu is not None and bu*lu<0:
        cross.append("BofA/EPFR와 LSEG Lipper의 미국 주식 흐름 방향이 반대입니다. 서로 다른 데이터셋이므로 어느 한쪽으로 덮어쓰지 않습니다.")

# Overall interpretation uses same-source pairs first, then official ICI/FINRA separately.
interpret=[]
if bofa and bofa["metrics"].get("us_equity_bn") is not None and bofa["metrics"].get("mmf_bn") is not None:
    interpret.append("BofA/EPFR: "+flow_direction(bofa["metrics"]["us_equity_bn"], bofa["metrics"]["mmf_bn"]))
if lipper and lipper["metrics"].get("us_equity_bn") is not None and lipper["metrics"].get("mmf_bn") is not None:
    interpret.append("LSEG Lipper: "+flow_direction(lipper["metrics"]["us_equity_bn"], lipper["metrics"]["mmf_bn"]))
if ici:
    d=ici["metrics"].get("domestic")
    if d is not None:
        interpret.append("ICI 공식: 미국 국내주식형 순유입" if d>0 else "ICI 공식: 미국 국내주식형 순유출")
finra=next((x for x in results if x["kind"]=="margin"),None)
if finra:
    md=finra["metrics"].get("margin_debt_mom_bn")
    if md is not None:
        interpret.append("FINRA 월간: 마진부채 증가 → 레버리지 확대" if md>0 else "FINRA 월간: 마진부채 감소 → 레버리지 축소")

status_lines=["# US Fund Flow Watch", "", f"- parsed sources: {len(results)}", f"- updates: {len(updates)}"]
for x in results:
    status_lines.append(f"- {x['source']} {x['kind']} | {x['period']} | {x['fingerprint'][:12]}")
for e in errors: status_lines.append(f"- error: {e}")
if fx: status_lines.append(f"- USD/KRW: {fx['usdkrw']} ({fx['date']})")
STATUS.write_text("\n".join(status_lines)+"\n",encoding="utf-8")

force=(os.getenv("FORCE_SEND") or "").lower() in ("1","true","yes")
if updates or force:
    body=["🇺🇸 <b>[미국 증시 자금흐름 추적 | 신규 변화]</b>",
          "출처별 모집단이 달라 수치는 합산하지 않고 각각의 방향을 따로 판정합니다.",""]
    selected=updates if updates else results
    for x in selected:
        label=x["source"]
        period=x.get("period") or ""
        body += [f"<b>{html.escape(label)} | {html.escape(str(period))}</b>", source_block(x,fx),
                 f'• 원천: <a href="{html.escape(x["url"],quote=True)}">열기</a>',""]
    body += ["<b>현재 판정</b>"]
    for s in interpret: body.append("• "+html.escape(s))
    for s in cross: body.append("• ⚠️ "+html.escape(s))
    if not cross: body.append("• 출처 간 방향 충돌이 확인되지 않았거나 비교 가능한 동시값이 부족합니다.")
    body += ["", "<b>해석 원칙</b>",
             "• 미국주식↑·MMF↓ 같은 조합은 같은 출처 안에서만 위험자산 이동 신호로 해석",
             "• ICI·BofA/EPFR·LSEG Lipper는 모집단이 달라 서로 합산·평균하지 않음",
             "• FINRA 마진부채는 월간 레버리지 확인용이며 주간 펀드 흐름과 기간을 혼합하지 않음"]
    if fx: body.append(f"• 원화 환산: 한국은행 ECOS USD/KRW {fx['usdkrw']:,.2f} ({fx['date']})")
    ALERT.write_text("\n".join(body)+"\n",encoding="utf-8")

    newstate=state
    newstate.setdefault("seen",{})
    newstate.setdefault("values",{})
    for x in results:
        k=f"{x['source']}|{x['kind']}"
        newstate["seen"][k]=x["fingerprint"]
        newstate["values"][k]=x
    newstate["updated_at_kst"]=datetime.now(timezone(timedelta(hours=9))).isoformat()
    PENDING.write_text(json.dumps(newstate,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"us_fund_flow_alert_ready=true updates={len(updates)}")
else:
    print("us_fund_flow_alert_ready=false unchanged=true")

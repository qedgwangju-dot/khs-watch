#!/usr/bin/env python3
import csv
import hashlib
import html
import io
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

STATE_PATH = Path("data/warsh_new_axes_watch_state.json")
UA = "Mozilla/5.0 (compatible; khs-watch/1.2; +https://github.com/qedgwangju-dot/khs-watch)"
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
EXPECTED_BOT = (os.getenv("EXPECTED_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "0") == "1"

H6_URL = "https://www.federalreserve.gov/releases/h6/current/"
H8_URL = "https://www.federalreserve.gov/releases/h8/current/"
SLOOS_INDEX = "https://www.federalreserve.gov/data/sloos.htm"
BLS_PROD_URL = "https://www.bls.gov/news.release/prod2.nr0.htm"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
FRED_PROD = "https://fred.stlouisfed.org/series/OPHNFB"
FRED_ULC = "https://fred.stlouisfed.org/series/ULCNFB"

MONTHS = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"June":6,"Jul":7,"July":7,"Aug":8,"Sep":9,"Sept":9,"Oct":10,"Nov":11,"Dec":12}

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.table=[]
        elif tag == 'tr' and self.table is not None: self.row=[]
        elif tag in ('td','th') and self.row is not None: self.cell=[]
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        elif tag == 'tr' and self.row is not None:
            if any(self.row): self.table.append(self.row)
            self.row=None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table); self.table=None


def fetch(url):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":"en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace'), r.geturl()


def clean_text(raw):
    raw=re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>"," ",raw)
    raw=re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>","\n",raw)
    raw=re.sub(r"(?s)<[^>]+>"," ",raw)
    t=html.unescape(raw).replace('\xa0',' ')
    t=re.sub(r"[ \t]+"," ",t)
    return re.sub(r"\n\s*\n+","\n",t).strip()


def parse_num(s): return float(s.replace(',','').replace('%','').strip())
def pct(a,b): return (a/b-1)*100 if b else None
def annualize(a,b,months): return ((a/b)**(12/months)-1)*100 if b and a>0 and b>0 else None

def release_date(text):
    m=re.search(r"Release Date:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2})", text, re.I)
    return m.group(1) if m else None

def table_rows(raw):
    p=TableParser(); p.feed(raw); return p.tables

def month_key(label):
    m=re.match(r"([A-Za-z]+)\.?\s+(20\d{2})", label)
    if not m: return None
    mon=MONTHS.get(m.group(1)[:4].rstrip('.')) or MONTHS.get(m.group(1)[:3]) or MONTHS.get(m.group(1))
    return (int(m.group(2)), mon) if mon else None


def h6_snapshot():
    raw, final=fetch(H6_URL); text=clean_text(raw); candidates=[]
    for table in table_rows(raw):
        for row in table:
            if len(row) >= 10 and month_key(row[0]):
                try: candidates.append((month_key(row[0]), row[0], parse_num(row[2])))
                except Exception: pass
    if len(candidates) < 4: raise RuntimeError('H6 M2 rows not parsed')
    candidates.sort(key=lambda x:x[0]); ymap={k:v for k,_,v in candidates}
    k,label,m2=candidates[-1]; prev3=candidates[-4][2]; yoy=ymap.get((k[0]-1,k[1]))
    return {'release':release_date(text) or label,'period':label,'m2':m2,
            'm2_3m_ann':annualize(m2,prev3,3),'m2_yoy':pct(m2,yoy) if yoy else None,'url':final}


def h8_snapshot():
    raw, final=fetch(H8_URL); text=clean_text(raw); chosen=None
    for table in table_rows(raw):
        joined=' '.join(' '.join(r) for r in table[:4]).lower()
        if 'week ending' not in joined: continue
        ci=next((r for r in table if any('commercial and industrial loans' in c.lower() for c in r)),None)
        bc=next((r for r in table if any(c.strip().lower()=='bank credit' for c in r)),None)
        if ci and bc: chosen=(ci,bc); break
    if not chosen: raise RuntimeError('H8 weekly table not parsed')
    ci,bc=chosen
    nums_ci=[]; nums_bc=[]
    for c in ci:
        try: nums_ci.append(parse_num(c))
        except: pass
    for c in bc:
        try: nums_bc.append(parse_num(c))
        except: pass
    if len(nums_ci)<4 or len(nums_bc)<4: raise RuntimeError('H8 values too short')
    ci4=pct(nums_ci[-1],nums_ci[-4]); bc4=pct(nums_bc[-1],nums_bc[-4])
    if ci4 >= 0.75 and bc4 >= 0: regime='신용 확장'
    elif ci4 <= -0.75 and bc4 <= 0: regime='신용 긴축'
    else: regime='중립'
    return {'release':release_date(text) or 'H8 current','ci_latest':nums_ci[-1],'ci_4wk_pct':ci4,
            'bank_credit_latest':nums_bc[-1],'bank_credit_4wk_pct':bc4,'regime':regime,'url':final}


def latest_sloos_url():
    raw,_=fetch(SLOOS_INDEX)
    links=re.findall(r'href=["\']([^"\']*sloos[-_/]?20\d{4}[^"\']*\.htm)["\']',raw,re.I)
    urls=[]
    for h in links:
        u=urllib.parse.urljoin(SLOOS_INDEX,h); m=re.search(r'sloos[-_/]?(20\d{4})',u,re.I)
        if m: urls.append((m.group(1),u))
    return max(urls)[1] if urls else "https://www.federalreserve.gov/data/sloos/sloos-202607.htm"


def sloos_snapshot():
    url=latest_sloos_url(); raw,final=fetch(url); text=clean_text(raw); core=[]
    for s in re.split(r'(?<=[.!?])\s+|\n+',text):
        low=s.lower()
        if 'c&i' in low and ('standards' in low or 'demand' in low or 'terms' in low): core.append(' '.join(s.split()))
    core='\n'.join(dict.fromkeys(core[:12])); low=core.lower()
    ease=sum(low.count(x) for x in ['stronger demand','eased standards','easier standards','narrower loan rate spreads'])
    tight=sum(low.count(x) for x in ['weaker demand','tightened standards','tighter standards','wider loan rate spreads'])
    regime='신용 완화' if ease>=tight+2 else ('신용 긴축' if tight>=ease+2 else '혼합/중립')
    m=re.search(r'(20\d{4})',final)
    return {'key':m.group(1) if m else final,'regime':regime,'url':final,
            'fingerprint':hashlib.sha256(core.encode()).hexdigest()}


def fred_series(series):
    raw,_=fetch(FRED_CSV.format(series)); rows=[]
    for r in csv.DictReader(io.StringIO(raw)):
        v=r.get(series)
        if not v or v=='.': continue
        try: rows.append((r['observation_date'],float(v)))
        except Exception: pass
    if len(rows)<5: raise RuntimeError(f'FRED {series} rows not parsed')
    return rows


def _signed_word(word, val):
    v=float(val)
    return -v if str(word).lower().startswith('decreas') else v


def _search_num(text, pattern, flags=re.I):
    m=re.search(pattern,text,flags)
    return float(m.group(1)) if m else None


def bls_prod_snapshot():
    raw, final=fetch(BLS_PROD_URL); text=clean_text(raw)
    rel=release_date(text) or 'BLS current'
    # Current BLS release language; fall back to FRED only if the official page changes materially.
    p=_search_num(text,r"nonfarm business sector labor productivity (?:increased|rose)\s+([\d.]+)\s+percent in the second quarter of 2026")
    if p is None:
        p=_search_num(text,r"labor productivity (?:increased|rose)\s+([\d.]+)\s+percent in the second quarter of 2026")
    py=_search_num(text,r"From the same quarter a year ago, nonfarm business sector labor productivity (?:increased|rose)\s+([\d.]+)\s+percent")
    m=re.search(r"Unit labor costs in the nonfarm business sector\s+(increased|decreased)\s+([\d.]+)\s+percent in the second quarter of 2026",text,re.I)
    uq=_signed_word(m.group(1),m.group(2)) if m else None
    uy=_search_num(text,r"Unit labor costs increased\s+([\d.]+)\s+percent over the last four quarters")
    share=_search_num(text,r"labor share.*?was\s+([\d.]+)\s+percent in the second quarter of 2026",re.I|re.S)
    mp=_search_num(text,r"(?:Manufacturing sector|Total manufacturing sector) labor productivity (?:increased|rose)\s+([\d.]+)\s+percent in the second quarter of 2026")
    mm=re.search(r"Unit labor costs in the total manufacturing sector\s+(increased|decreased)\s+([\d.]+)\s+percent in the second quarter of 2026",text,re.I)
    mulc=_signed_word(mm.group(1),mm.group(2)) if mm else None
    cycle=_search_num(text,r"current business cycle.*?labor productivity has grown at an annualized rate of\s+([\d.]+)\s+percent",re.I|re.S)
    realcomp=None
    mr=re.search(r"Real hourly compensation.*?\s+(increased|decreased)\s+([\d.]+)\s+percent in the second quarter of 2026",text,re.I|re.S)
    if mr: realcomp=_signed_word(mr.group(1),mr.group(2))
    if p is None or uq is None:
        raise RuntimeError('BLS productivity release not parsed')
    if p>=1.3 and uq<=2.0 and (mulc is None or mulc<=1.0):
        regime='생산성 개선·비용 압력 완화 — AI 공급효과에 유리'
    elif p<=1.0 and uq>=3.0:
        regime='생산성 둔화·비용 압력 확대 — AI 수요·물가 위험'
    else:
        regime='혼합 — 생산성 효과 추가 확인'
    return {'source_kind':'BLS','key':'2026년 2분기 수정치','date':rel,
            'productivity_qoq_saar':p,'productivity_yoy':py,'ulc_qoq_saar':uq,'ulc_yoy':uy,
            'labor_share':share,'manufacturing_productivity':mp,'manufacturing_ulc':mulc,
            'cycle_productivity_ann':cycle,'real_hourly_comp':realcomp,'regime':regime,'url':final}


def prod_snapshot():
    try:
        return bls_prod_snapshot()
    except Exception:
        p=fred_series('OPHNFB'); u=fred_series('ULCNFB')
        pm=dict(p); um=dict(u); dates=sorted(set(pm)&set(um)); d=dates[-1]; i=dates.index(d)
        prev=dates[i-1]; yearago=dates[i-4]
        prod_q=((pm[d]/pm[prev])**4-1)*100; ulc_q=((um[d]/um[prev])**4-1)*100
        prod_y=pct(pm[d],pm[yearago]); ulc_y=pct(um[d],um[yearago])
        dt=datetime.strptime(d,'%Y-%m-%d'); q=(dt.month-1)//3+1; key=f"{dt.year}년 {q}분기"
        if prod_q>=2.0 and ulc_q<=2.0: regime='생산성 우위 — AI 공급효과에 유리'
        elif prod_q<=1.0 and ulc_q>=3.0: regime='비용 우위 — AI 수요·물가 위험'
        else: regime='혼합'
        return {'source_kind':'FRED-대체','key':key,'date':d,'productivity_qoq_saar':prod_q,
                'ulc_qoq_saar':ulc_q,'productivity_yoy':prod_y,'ulc_yoy':ulc_y,
                'labor_share':None,'manufacturing_productivity':None,'manufacturing_ulc':None,
                'cycle_productivity_ann':None,'real_hourly_comp':None,'regime':regime,'url':FRED_PROD}


def load_state():
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except: return {}
def save_state(s):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True); s['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def get_bot_username():
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getMe",timeout=20) as r:
        d=json.loads(r.read().decode())
    return str((d.get('result') or {}).get('username') or '')

def link(label,url):
    return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'

def send(msg):
    if not TOKEN or not CHAT_ID: raise RuntimeError('Telegram token/chat id missing')
    u=get_bot_username()
    if u.lower()!=EXPECTED_BOT.lower(): raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{u}')
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data=data,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'): raise RuntimeError(f'Telegram send failed: {out}')


def money_message(h6,h8,sl):
    return '\n'.join([
        '[Warsh 새 정보축] 통화·신용',
        '',
        '<b>핵심 판정</b>',
        f"• 은행 신용: <b>{html.escape(h8['regime'])}</b>",
        f"• 대출기준·수요: <b>{html.escape(sl['regime'])}</b>",
        '',
        '<b>현재 숫자</b>',
        f"• M2 통화량 {html.escape(h6['period'])}: {h6['m2']/1000:.3f}조달러 · 3개월 연율 {h6['m2_3m_ann']:+.1f}% · 전년 대비 {h6['m2_yoy']:+.1f}%",
        f"• 기업대출(C&amp;I): {h8['ci_latest']/1000:.3f}조달러 · 약 4주 {h8['ci_4wk_pct']:+.1f}%",
        f"• 은행 전체 신용: {h8['bank_credit_latest']/1000:.3f}조달러 · 약 4주 {h8['bank_credit_4wk_pct']:+.1f}%",
        '',
        '<b>해석</b>',
        '• 실제 통화·신용이 계속 늘면 기준금리 숫자와 별개로 금융여건이 충분히 긴축적이지 않다는 워시의 논리가 강화됩니다.',
        '• 반대로 기업대출·은행신용이 함께 줄고 대출기준까지 강화되면 시장이 스스로 긴축해 추가 금리인상 필요성이 낮아질 수 있습니다.',
        '',
        '<b>원천</b>',
        f"{link('연준 H.6 통화량',h6['url'])} · {link('연준 H.8 은행신용',h8['url'])} · {link('연준 SLOOS',sl['url'])}",
    ])


def prod_message(pr):
    lines=[
        '[Warsh 새 정보축] 생산성·단위노동비용',
        f"기준: {html.escape(pr['key'])}",
        '',
        '<b>핵심 판정</b>',
        f"• <b>{html.escape(pr['regime'])}</b>",
        '',
        '<b>현재 숫자</b>',
        f"• 비농업 노동생산성: {pr['productivity_qoq_saar']:+.1f}% 전분기 대비 연율" + (f" · {pr['productivity_yoy']:+.1f}% 전년 대비" if pr.get('productivity_yoy') is not None else ''),
        f"• 단위노동비용: {pr['ulc_qoq_saar']:+.1f}% 전분기 대비 연율" + (f" · {pr['ulc_yoy']:+.1f}% 전년 대비" if pr.get('ulc_yoy') is not None else ''),
    ]
    if pr.get('labor_share') is not None:
        lines.append(f"• 노동소득분배율: <b>{pr['labor_share']:.1f}%</b> · BLS 통계 시작 이후 최저 여부 확인")
    if pr.get('manufacturing_productivity') is not None:
        lines.append(f"• 제조업 노동생산성: {pr['manufacturing_productivity']:+.1f}% 전분기 대비 연율")
    if pr.get('manufacturing_ulc') is not None:
        lines.append(f"• 제조업 단위노동비용: <b>{pr['manufacturing_ulc']:+.1f}%</b> 전분기 대비 연율")
    if pr.get('cycle_productivity_ann') is not None:
        lines.append(f"• 2019년 4분기 이후 생산성 추세: 연율 {pr['cycle_productivity_ann']:+.1f}%")
    lines += [
        '', '<b>해석</b>',
        '• 생산성 상승과 단위노동비용 둔화가 함께 나오면 AI·설비투자가 공급능력을 높여 물가 압력을 낮추는 경로에 유리합니다.',
        '• 노동소득분배율이 낮아지는 경우 생산성 이익이 임금보다 기업·자본 쪽에 더 많이 귀속되는지 별도로 확인해야 합니다. 이는 AI 효과라고 단정하지 않습니다.',
        '• 제조업 단위노동비용까지 하락하면 단순 서비스업 착시보다 실물 생산비 개선 신호가 강해집니다.',
        '', '<b>원천</b>', f"{link('BLS 생산성·비용 공식자료',pr['url'])}"
    ]
    return '\n'.join(lines)


def main():
    old=load_state(); h6=h6_snapshot(); h8=h8_snapshot(); sl=sloos_snapshot(); pr=prod_snapshot()
    new={'h6':h6,'h8':h8,'sloos':sl,'productivity':pr}; first_run=not bool(old)
    money_changed=(old.get('h6',{}).get('release') not in (None,h6['release']) or
                   old.get('h8',{}).get('regime') not in (None,h8['regime']) or
                   old.get('sloos',{}).get('fingerprint') not in (None,sl['fingerprint']))
    migrating_prod=old.get('productivity',{}).get('source_kind') != pr.get('source_kind')
    prod_changed=(not migrating_prod and (
                  old.get('productivity',{}).get('date') not in (None,pr['date']) or
                  old.get('productivity',{}).get('regime') not in (None,pr['regime']) or
                  old.get('productivity',{}).get('labor_share') not in (None,pr.get('labor_share'))))

    if FORCE_NOTIFY or (not first_run and money_changed): send(money_message(h6,h8,sl))
    if FORCE_NOTIFY or (not first_run and prod_changed): send(prod_message(pr))

    save_state(new)
    print(json.dumps({'first_run':first_run,'money_changed':money_changed,'prod_changed':prod_changed,
                      'productivity_source':pr.get('source_kind'),'h8_regime':h8['regime'],
                      'sloos_regime':sl['regime'],'prod_regime':pr['regime']},ensure_ascii=False))

if __name__=='__main__': main()
